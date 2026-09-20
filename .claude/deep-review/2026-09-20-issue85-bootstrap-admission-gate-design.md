# Issue #85 — Bootstrap routes descriptors through the admission gate (absorbing #78)

**Date:** 2026-09-20
**Status:** Design complete, verdict BUILD. Deferral homes: #63 design §10 row 3 (issue #85's
origin) and #64 design §8.3 row 3 (issue #78's origin).
**Tree examined:** `main` at `3b06072` (post-#87 descriptor-dialect merge). All anchors cite
that tree; symbol names are the source of truth when lines drift.
**Planned branch:** `feat/issue85-bootstrap-admission` (design record committed on-branch as
commit one, per the #62/#64 convention).

---

## 1. Root cause, verified

`admit_startup_bench` (`src/benchweave/interfaces/bootstrap.py:36`) loads the startup lattice
with bare `json.loads` and subscripts: `bench["id"]`, `descriptor["id"]`,
`descriptor.get("profiles", [])`. Nothing validates structure, the OTDP schema, the S01/S02
mirrors, the issued-input extension, or the digest-pin lattice. Its single production caller
is `_lifespan` (`src/benchweave/interfaces/app.py:424`), which runs it under the write gate
with **no exception handling** — so today's failure mode splits by defect class:

- **Gross breakage already refuses boot, untyped.** A missing `bench.json` /
  `commissioning.json` / lattice extra raises `FileNotFoundError`; malformed JSON raises
  `JSONDecodeError`; a missing `id` key raises `KeyError`. All propagate out of the lifespan;
  uvicorn reports "Application startup failed" and the process exits.
- **Semantic breakage boots and launders.** A schema-invalid descriptor, a drifted bench
  pin, or a wrong descriptor set sails through. Three laundering surfaces are written:
  1. `store.put_device(..., "matched", ...)` (`bootstrap.py:71-80`, signature at
     `src/benchweave/state/store.py:531` — the parameter is `identity_state`). The store
     asserts a verified identity match that nothing verified. `Operations.device_list` /
     `device_get` project `identity_state` to operators
     (`src/benchweave/interfaces/operations.py:294`, `_device_projection` at `:1448`).
  2. `content.put_document(..., schema_id)` with the fallback `urn:stg:admitted`
     (`bootstrap.py:content_sha`) labels unvalidated bytes as admitted.
  3. The device-row set comes from the `descriptor-*.json` glob, not from `bench.devices`
     pins — a missing pinned file silently drops a row; an unpinned extra file gains one.
     `admit_documents` refuses both directions (`pin_absent:`).
- **Partial-write hazard.** `store.bump_generation` and `put_bench` run *before* the
  descriptor loop (`bootstrap.py:56-63`), so a mid-loop crash leaves a bumped generation and
  a half-populated inventory.

Meanwhile the real gate exists and is proven over **this exact lattice**: `_recovery_documents`
(`app.py:169-205`) resolves the binding-pinned procedure and the bench-pinned descriptors from
the same `fixtures/execution/` and calls `admit_documents` — on **every app startup**. It runs
green in CI (every app-startup test exercises it). That is the empirical proof the committed
fixture lattice passes the gate today with zero byte changes — the same proof shape #63 used
for `sim_scope`.

**Why the bypass matters even though runs re-admit:** `build_run` re-admits at run time
(`app.py:328`), so execution is protected — but the operator surface (`device_list`) and the
store's own inventory were never gated, and startup is the one path that writes `"matched"`
rows. A gateway that boots on an invalid lattice serves evidence rows it cannot stand behind.

## 2. Behavior table (before → after)

| Lattice defect under `fixtures/` | Today | After this increment |
|---|---|---|
| Missing `bench.json` / `commissioning.json` / extras | `FileNotFoundError`, boot refuses (untyped) | unchanged (file-level errors keep propagating — `admit_documents` contract) |
| Malformed JSON, duplicate keys, non-finite numbers | raw `JSONDecodeError` traceback, boot refuses | `AdmissionRejected` carrying `schema:` (the exact-byte decoder's gates) |
| Descriptor schema-invalid (incl. slim dialect, S01/S02) | **boots**; `identity_state="matched"` row; runs fail later | refuses boot, `schema: descriptor[…] …` |
| Bench descriptor pin digest drift | **boots**; "matched" | refuses boot, `digest_mismatch:` |
| Pinned descriptor file absent from lattice | **boots**; row silently missing | typed `FileNotFoundError` naming device + sha |
| Binding-pinned procedure absent | **boots** (bootstrap never reads the pin; recovery logs `recovery_skipped`) | typed `FileNotFoundError` |

## 3. Mechanism

### 3.1 One admission path, two callers

Extract the resolution+admission body of `_recovery_documents` into
`bootstrap.admit_fixture_lattice(fixtures_dir: Path) -> AdmittedDocuments`:

1. Read `run-binding.json`; resolve the pinned procedure by sha256 over the
   `procedure-*.json` glob family (absent → `FileNotFoundError`, the existing
   missing-document contract).
2. Read `bench.json`; map each `bench.devices[].descriptor.sha256` to its file over the
   `descriptor-*.json` glob (absent → `FileNotFoundError` naming the device and sha
   prefix). `descriptor_paths` is keyed by bench device id — exactly the mapping
   `_recovery_documents` builds today.
3. Call `control.documents.admit_documents(procedure_path, policy_path, bench_path,
   binding_path, commissioning_path, descriptor_paths)`. Typed refusals
   (`schema:` / `digest_mismatch:` / `pin_absent:`) and file-level errors propagate.

`_recovery_documents` becomes a thin containment wrapper over it (try/except → log
`recovery_admission_rejected` → `None`); its behavior is unchanged. Bootstrap gets the
strict caller.

### 3.2 `admit_startup_bench` rewired

- **Admission first, writes second.** `docs = admit_fixture_lattice(fixtures_dir)` is the
  first statement; no `bump_generation`, no `put_bench`, no content row exists before
  admission succeeds. Refusal leaves the store untouched — all-or-nothing for admission
  refusals: they precede every write. (Fold F1, 2026-09-20: this does NOT close the whole
  of §1's partial-write hazard — a write-phase failure *after* admission, e.g. a truncated
  unpinned family member crashing the cache loop's parse mid-write, remains possible;
  pre-existing, now D6 below. Refute reproduced it: benches 1, devices 2, generations 1.)
- Bench/commissioning handling, generation logic, and the `put_bench` line stay verbatim
  (the read bytes are still needed for the content store).
- **Device rows now iterate `docs.bench["devices"]`** (the pinned set), not the glob:
  `view = docs.descriptors[bench_device_id]`;
  - `device_id = str(view["id"])` — **preserves today's descriptor-id keying** (the
    projection's `id` is the descriptor's own id, e.g. `dev.benchweave.sim-psu`). The
    deeper conflation is pre-existing and deferred (D1).
  - `profiles_json = json.dumps(view["profiles"])` — identical bytes to today's
    `descriptor.get("profiles", [])` on valid documents (projection: absent → `[]`).
  - `descriptor_json` = the raw file text (unchanged — the run path's spool re-admits raw
    bytes by digest), and the raw doc remains the source for `licence`.
  - `identity_state="matched"` is now an **evidenced** claim: `admit_documents` verified the
    bench's `{id, version, sha256}` pin against the actual document
    (`_verify_pin` per descriptor).
- **Content-store writes are unchanged in set and shape** — the whole procedure family, all
  globbed descriptors, and the extras still land in the content store (cache-by-digest;
  `_spool_documents` resolves runs from it). Unpinned family members remain cache-only and
  meet the gate at run admission when a binding pins them (accepted residual, D5).
- **Refusal surface:** log
  `_LOG.error("startup_admission_rejected: %s: %s", type(error).__name__, error)` then
  re-raise — mirroring `recovery_admission_rejected`. The machine-matchable prefixes ride
  inside the message; uvicorn turns the lifespan exception into a startup failure the
  service manager can act on.

### 3.3 Why the full lattice, not per-descriptor `_project_descriptor`

Per-descriptor projection alone (the narrow reading of #85) would close only the schema
cell: pin-lattice drift and the glob-vs-pins set inconsistency would survive, and
`"matched"` would still be unverified. The full `admit_documents` call is the same code the
recovery path already proves on every startup, costs seven schema validations (~ms), and
makes bootstrap exactly as strict as execution and recovery — one gate, three callers.

**Precedent extended:** `_recovery_documents` (in-tree, exercised on every app start). No
new architecture.

## 4. Refuse vs degrade — DECIDED: refuse (fail-fast)

The fork is decided on evidence, not preference:

1. **Determinism (A04) does not discriminate.** Both postures are deterministic code paths;
   neither depends on judgement. Recorded so nobody re-litigates on A04 grounds.
2. **Today's own stance is already refuse-on-gross-breakage.** Missing files and malformed
   JSON crash startup today. A degrade gate would *newly boot* lattices that currently
   crash — a posture regression against the one-line promise (checks that mean the same
   thing on any host).
3. **STO-3 makes a degraded live gateway anti-repair.** A live gateway holds the flock on
   `<db>.hold` for its lifespan, and at-rest commands (backup, restore) **refuse** while it
   lives. A bootless process gets out of the way of repair; a booted gateway with no
   admitted bench blocks the repair tools while serving nothing (one bench per gateway —
   `admit_startup_bench` reads exactly one `bench.json`).
4. **A07 alignment: no evidence rows for an unadmitted lattice.** Refusal is the no-write
   outcome. The store cannot audit a bench it could not admit, and must not write
   `"matched"`, a bench row, or a bumped generation for one. (No new audit obligation is
   created at startup: there is nothing to record against, and the log line carries the
   typed reason.)
5. **No physical-safety cost.** Startup constructs no plugins; recovery never touches
   devices by design, and *already* skips on lattices that fail admission
   (`recovery_skipped`). Today an invalid lattice boots a gateway that skips recovery with
   a poisoned inventory; refusing loses nothing physical and drops the poison.
6. **Supervised-service detection favors refusal.** Under systemd (`Type=simple`), a
   degraded boot shows "active" while broken; a refused boot is a restart loop with a
   typed, greppable log line.

**Why the recovery degrade precedent does not transfer (the reusable rule):** recovery is a
repair *action over existing state* where doing nothing is safe and reversible. Bootstrap is
*construction of the working state* — there is no "nothing" to fall back to; the gateway's
purpose is the bench it admits. Containment is the right shape for the former, fail-fast for
the latter.

**Degrade shapes considered and killed:** (A) boot with no inventory — loses on STO-3 and
detection, serves nothing; (B) store inventory anyway flagged unverified — that is the
laundering #85 exists to close, and `device_list` would show unverifiable devices; (C) skip
only the failed document — silent partial inventory plus late, confusing run-time
`pin_absent` refusals.

## 5. #78 — `ADMITTED_DIRS`: remove, replaced by a derived closed-world guard

**Measured first (2026-09-20, `main` `3b06072`).** The tuple
(`tests/contract/test_baseline.py:25`) lists **6** dirs. The corpus carries **11**:
`otdp/0.1.0` (retained), `plugin-ui/0.1.0`, `plugin-ui/0.1.1`, `plugin-ui/0.2.0`,
`plugin-ui-preview/0.1.0` are all absent from it. Wiring the tuple as-is would fail on the
real corpus — the dead variable was hiding four version-dirs of drift, which is itself the
strongest argument that a hand-list cannot be the maintained authority.

**The dir set is fully machine-derivable.** Measured derivation:

- **Active dirs** = version-dirs of `standards-manifest.json` normative paths that live
  under `standards/` (plugin-ui's non-`standards/` normative paths, e.g.
  `src/benchweave/presentation`, are ignored).
- **Retained dirs** = closure of `corpus-manifest.json` `source` fields that resolve under
  `standards/` (the copy-never-move chain: `otdp/0.2.0 → 0.1.2 → 0.1.1 → 0.1.0 → docs/`).

Result: `derived == actual`, both diffs empty, 11 dirs on each side.

**Mechanism.** Delete `ADMITTED_DIRS`. Add to `test_baseline.py` a pure helper
`_derived_corpus_dirs(standards_manifest, corpus_rows) -> set[str]` and:

1. `test_corpus_dirs_match_derived_closed_world` — equality as **two directed assertions**
   with distinct messages:
   - `actual − derived` → "corpus dir not justified by the standards manifest or any source
     chain (stray family/version)";
   - `derived − actual` → "justified dir missing from the corpus (copy-never-move deletion
     or broken source chain)".
2. Unit tests of the helper on synthetic inputs (the matched control fixtures): stray dir,
   missing retained dir, active version move, chain gap, and the plugin-ui
   non-`standards/`-path tolerance.

**What the guard does not catch** (stated inline, per claim discipline): file-vs-manifest
drift — `test_manifest_lists_every_contract_file` and the hash tests own that. This guard
owns **dir-level justification** only. Side benefit: it mechanically enforces
`standards/GOVERNANCE.md`'s "rows cite the old corpus path as `source`" — a future bump
that breaks the chain fires the guard in one of the two directions.

**Why removal beats wiring the hand-list:** claim discipline — a set named in prose is
regenerable from a mechanism; here the mechanism exists and already agrees with reality
(measured). The hand-list went stale once while dead; a wired hand-list adds one more
in-tree literal to every standards bump's touch-set (the #64 sweep already had to edit it)
with no property the derivation cannot express.

## 6. Minimal first increment

1. `src/benchweave/interfaces/bootstrap.py` — `admit_fixture_lattice` extraction +
   rewired `admit_startup_bench` + `startup_admission_rejected` log line.
2. `src/benchweave/interfaces/app.py` — `_recovery_documents` delegates to
   `admit_fixture_lattice`; containment wrapper unchanged.
3. `tests/unit/test_bootstrap_admission.py` (new) — five poisoned-lattice variants
   (§10), all-or-nothing store assertions, happy-path identity against the committed
   fixtures.
4. One integration test (the `poc_app` pattern, own temp Store/fixtures): poisoned lattice
   through `create_app`'s lifespan → startup raises, store stays empty.
5. `tests/contract/test_baseline.py` — delete the tuple, add the derived guard + helper
   unit tests.
6. Docs: `docs/operator-guide.md` §3 (serve behavior) + §9 (troubleshooting entry for
   `startup_admission_rejected:`); `docs/develop-your-device.md` bootstrap paragraph
   (~:87) — startup now requires gate-valid descriptors.

One RED→GREEN slice per commit: commit 1 = design record (this file); commit 2 = the #78
guard (control fixtures are its RED); commit 3 = RED poisoned-lattice tests against the
pre-fix tree; commit 4 = the wiring (GREEN); commit 5 = docs sweep.

## 7. Deferrals (each with a home; **zero** new follow-on issues)

- **D1 — device-row keying conflation** (rows keyed by descriptor id, not the bench's
  device id; two bench devices pinning one descriptor collide on
  `ON CONFLICT(device_id)`). Home: #63 design §11 risk 2 — named pre-existing WP08 wiring,
  unchanged in kind by this increment (and deliberately preserved to keep this wiring
  behavior-neutral on valid lattices).
- **D2 — double admission at startup** (bootstrap and recovery admit the same bytes).
  Home: this record §7. Cost is seven schema validations; dedupe only if startup latency
  ever becomes a measured problem.
- **D3 — content-store `schema_id` labeling** (the `urn:stg:admitted` fallback).
  Home: this record §7. Informational field; no reader gates on it; `_spool_documents`
  resolves by digest only.
- **D4 — `str(bench.get("qualification", "observation"))` coercion** if the key is
  present-but-null. Home: this record §7; unchanged by this increment.
- **D5 — unpinned procedure/descriptor family members** stored cache-only, validated when
  a binding pins them (run admission). Home: this record §7; the run-time gate is the
  backstop.
- **D6 — write-phase failure after admission** (added by fold F1, 2026-09-20, from refute):
  an unpinned family member that is not valid exact-byte JSON (truncated, duplicate-keyed
  in a way the cache loop's bare `json.loads` rejects) crashes bootstrap's cache loops
  AFTER admission has passed and rows are already written — refute reproduced benches 1,
  devices 2, generations 1 on such a lattice. Pre-existing shape (the loops predate #85);
  the admission gate cannot catch it because the document is unpinned by definition.
  Home: this record §7. Take it up when the first consumer decodes unpinned family
  members, or alongside the D5 run-gate work (exact-byte-decode the cache-loop parses, or
  defer their writes).

## 8. Invariant impacts

- **CON-1 — amendment (issue #85):** startup/bootstrap joins execution and recovery as the
  third admission caller: every execution-contract document enters the store only through
  `admit_documents`; a lattice that fails admission refuses gateway startup before any
  store write, with the typed prefixes carried in `startup_admission_rejected:`. (Exact-byte
  decode, digest pins, and CON-10's projection unchanged — bootstrap consumes the
  projection for `id`/`profiles` and keeps raw bytes for the store, mirroring the
  VIEW-vs-RAW settlement.)
- **A04:** the startup gate is deterministic code; no judgement anywhere in the refusal
  path. Non-discriminating between refuse/degrade (§4.1) — recorded.
- **A07:** alignment only (no inventory/evidence rows for unadmitted lattices); no new
  startup audit requirement — there is no admitted bench to audit against, and the typed
  log line is the operator surface.
- No CTL/STO/REG invariant changes. No new invariant — the CON-1 amendment carries the
  property.
- **Tier:** not Tier 3 — no on-disk format, no schema or corpus bytes, no openapi/MCP/SDK
  surface, store schema unchanged.

## 9. Surfaces & CI cost

| Surface | Moves? |
|---|---|
| MCP tools / REST / openapi / operation-catalog | No (refusal precedes serving; `device_list` output unchanged on valid lattices) |
| Vendored standards / corpus-manifest / SDK submodule | No bytes move |
| Store schema / migrations | No |
| `docs/operator-guide.md` §3, §9 | Yes — startup refusal behavior + troubleshooting entry |
| `docs/develop-your-device.md` | Yes — one paragraph (descriptors must be gate-valid at startup) |
| Fixture lattice (`fixtures/execution/`) | No byte changes (recovery path already proves admissibility) |
| CI | All inside the existing `gates` pytest lane; ~12 new tests, no new job; one cold full-suite run pre-merge per convention |

## 10. Pre-committed acceptance rule

Written before any after-measurement runs. The BEFORE measurement (§10.1) is also the RED
control.

**Metric:** categorical boot/refuse over five poisoned-lattice variants, each a tempdir copy
of `fixtures/execution/` with exactly one mutation:

V1 S01 — descriptor `capabilities`/`operations` set mismatch;
V2 S02 — parameter `range` reversed (`[max, min]`);
V3 — `bench.json` device pin `sha256` drifted;
V4 — pinned descriptor file removed from the lattice;
V5 — binding-pinned procedure file removed.

**10.1 BEFORE (pre-fix tree, measured before the fix lands):** expect **5/5 BOOT** with
store rows present (`identity_state="matched"` wherever a device row exists; V4/V5 boot with
the row/Procedure silently absent). The new refusal tests, run here, must FAIL by booting —
that is the RED; the collected count must be > 0 (pytest exit nonzero, counts read from
`--junitxml` attributes). If a variant already refuses pre-fix, it is uninformative and is
excluded and reported as-is — **if fewer than 3 variants remain informative, the
measurement was UNDERPOWERED** (the bypass was narrower than designed): report that, do not
substitute new variants after looking.

**10.2 AFTER (fix tree):** all informative variants (expected 5/5):

- refuse startup with `AdmissionRejected` matching `schema:` / `digest_mismatch:` /
  `pin_absent:` (V4/V5: the typed `FileNotFoundError` naming device+sha / pinned procedure);
- leave the store with **zero** bench rows, **zero** device rows, and **no generation
  bump** (all-or-nothing);
- the happy path is unchanged: the committed fixture lattice admits byte-identically (no
  fixture edits), and all ~20 existing `admit_startup_bench` test callers stay green
  unmodified.

**10.3 #78 guard:** equality holds on the real corpus at merge time (measured 2026-09-20:
`derived == actual`, 11 dirs); the helper's synthetic controls each flip the verdict in
exactly one direction (stray → `actual−derived`; deletion/chain-gap → `derived−actual`).

**SHIP if:** 10.2 all-informative refuse + zero partial writes + happy path green + 10.3
holds, with gates re-run 3× (house convention).

**KILL if:** any informative variant still boots post-fix (wiring wrong — fix, don't
argue); OR the committed fixture lattice itself refuses (falsifies "recovery proves
admissibility" — stop and re-derive; **do not edit fixtures to fit the gate**); OR the #78
guard cannot reach equality without corpus-manifest surgery (then the fully-derived claim is
killed: land only the `actual ⊆ derived` direction and record the gap — that fallback is a
negative result about the source-chain discipline, reported as such).

## 11. Top risks, each with its falsifier

1. **A working deployment bootstraps a lattice the gate refuses.** The admitted set is
   byte-identical to what `_recovery_documents` already admits on every startup — any
   lattice that admits for recovery today admits for bootstrap tomorrow. Residual cohort:
   deployments currently booting with `recovery_skipped` logged — exactly the poisoned
   cohort this increment intends to refuse. *Falsifier:* a lattice that passes
   `_recovery_documents` but fails `admit_fixture_lattice` (impossible — same function
   after the extraction; that is the point of the extraction).
2. **The derived guard false-fires at a future standards bump** (source chain not updated).
   That is the guard working — GOVERNANCE requires the chain; the bump PR sees a named,
   two-direction message. Friction, not failure; the helper's unit tests document the
   contract.
3. **Descriptor-id keying preservation extends the D1 conflation.** Unchanged in kind,
   cited to #63 §11 risk 2; a future consumer needing bench-device identity hits it loudly
   (`device_list` shows descriptor ids today already).
4. **Startup latency grows by a second admission.** Seven schema validations + file reads
   (~ms, measured informally by the recovery path running in every startup test). If it
   ever matters measurably, D2 names the dedupe.
5. **Test isolation.** Poisoned-lattice tests must build tempdir copies and their own
   `Store` — never the repo's fixtures or db. The app-level test constructs `create_app`
   directly (the `poc_app` pattern), never `app_entry.build()` against repo state.
