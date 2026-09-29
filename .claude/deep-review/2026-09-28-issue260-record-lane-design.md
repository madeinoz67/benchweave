# Issue #260 — #220 Slice 6 Follow-on: The Record Lane — Design Record

**Status:** Design (builder-ready, queued behind #221's landing) · **Tracking issue:**
madeinoz67/benchweave#260 (follow-on of #220, sub-issue family of #203) · **Parent design:**
`.claude/deep-review/2026-09-28-issue220-execution-pin-design.md` §3 row E1 and §1.2 fold
corrections (the wire-posture and recovery disclosures this slice owns), plus §6 Risk 1 (the
floor attack, named there as this slice's design constraint) · **Evidence baseline:** gateway
`main` at `37c18b0` (PR #261 merged as `e5fee07`; the post-fold #220 record is tracked on
main). Branch will be `feat/issue260-record-lane`, **rebased onto #221's landing** (the
in-progress note on the issue serializes the two — they share `control/coordinator.py`;
see §7 Fork 4 for the exact hand-off point).

---

## 0. Premises verified — all four of the issue's constraints ground in code

- **The run-record corpus is version-complete and const-only apart.** Both served execution
  versions carry a `run-record.schema.json` with a corpus-manifest row
  (`execution/0.1.0/run-record.schema.json` and `execution/0.2.0/…` — 12 rows each version,
  verified in `standards/corpus-manifest.json`). A full schema diff shows the two documents
  differ in exactly two bytes-classes: `$id` and the `contract_version` **const**. Every
  field `build_terminal_record` emits is identical in shape across versions — threading the
  version is therefore structurally safe with zero record-field changes: stamp the pinned
  version's const, validate against the pinned version's digest-verified schema.
- **The guard is worker-side, which is the entire wire gap.** `app.py:717`
  (`if docs.execution_version != contracts.name: raise AdmissionRejected(...)`) fires inside
  `build_run` — the worker thread's construction path, submitted after `run_start` returns
  its 202 (`operations.py:702` `self._worker.submit(...)` at the tail of the §5 flow). The
  worker's poison guard (`worker.py:46-47`, `:188-221`) closes the queue state `terminal`
  without a terminal record — the client sees `terminal / outcome_unknown /
  terminal_record: null`; the typed message lives only in the gateway error log. The
  synchronous refusal home — the §5 pre-checks inside `_assert_bench_acceptable`
  (`operations.py:646` call site, body `:1687-1810`) — runs BEFORE the request key is
  written and already raises typed `errors.failure(<code>, …)` envelopes from the frozen
  14-code set (`errors.py:23-38`, mirrored verbatim by
  `standards/interface/0.1.0/operation-catalog.json` `error_http_status`).
- **The startup admission's result is discarded — and does not need persisting.**
  `bootstrap.admit_startup_bench` (`bootstrap.py:147-171`) admits the lattice then writes
  bench/content/device rows and a generation bump; `AdmittedDocuments.execution_version`
  goes nowhere. Persisting it would be a store-schema motion answering the WRONG question:
  a run binds the BINDING's lattice (`_spool_documents`, `app.py:174-233`, resolves
  `binding["bench"]["sha256"]` from the content store), not necessarily the startup
  lattice's. The §5 pre-check already resolves the binding document by digest for the
  request-id match (`operations.py:1788-1798`) — two more content-store reads (bench doc,
  then each descriptor doc) reach the run's OWN version facts, digest-addressed, with no
  TOCTOU (the bytes the pre-check reads are the exact bytes the worker will admit — same
  digests). **Re-read wins over persist**: no store change, per-run exact, right question.
- **The recovery wedge's cause is the record builder's composition-schema validation.**
  `build_terminal_record` stamps the literal `"contract_version": "0.2.0"`
  (`coordinator.py:232`) and validates against `_record_validator(contracts)`
  (`coordinator.py:196-205`) — the composition directory's schema, read blindly (no digest
  verification). `_is_other_carried_dialect` (`coordinator.py:110-137`) therefore SKIPS
  terminalization for the era cohort (a stored binding naming a corpus-carried dialect
  other than the composition's), logged
  `recovery_execution_version_not_runnable:` (`coordinator.py:140-157`), leaving the run
  non-terminal and the bench-busy wedge holding (`tests/faults/test_recovery_sweep_faults.py:206-297`).
  With the record threadable, the skip's reason evaporates for the judgeable cohort — the
  schema diff above proves an era record validates at 0.1.0 unchanged.
- **The floor's honest negative is total.** `standards/cross-constraints.json` carries
  exactly one row (execution 0.2.0 → otdp `>=0.2.0,<0.3.0` + `adapter_api 1.1`, evidence
  PR #201) and its own note records 0.1.0's absence as deliberate. The file has exactly one
  commit (`57edaa3`, slice 2) — no 0.1.0 row ever existed. GOVERNANCE G-4
  (`standards/GOVERNANCE.md:265-274`) requires each row to carry **citable evidence a
  reviewer can locate**; the 0.1.0-era history provides none — through execution 0.1.0's
  whole life (pre-`54a59fa`, 2026-09-25) OTDP moved 0.1.0 → 0.2.2 (`ea70c6a` reset, then
  `82c73b3` … the promotion-era pins) with no coupling declared anywhere, and the only
  0.1.0-era lattices that ever ran (the recovered `4743bd4` set) pin otdp **0.2.2**.
  A retrofitted 0.1.0 row would assert a coupling the version never declared — G-4's own
  letter refuses it (§1.1, Fork 1).
- **Slice 7 (#221) has already reserved this exact seam.** The zero-literal design record
  (untracked in the primary, its literal-table row 3) derives
  `coordinator.py:232`'s const from the validated schema's own const and records, verbatim
  intent: "E1 threads the run's own `execution_version` as an explicit parameter when it
  lifts the guard, replacing the derived default". This slice does exactly that; §1.3
  states what survives of the derivation.

## 1. The mechanism, file by file

### 1.1 The floor first — Fork 1's decision, designed as recommended (the owner calls it at review)

**The rule (recommended option (a)): every run's device pins must satisfy the COMPOSITION's
cross-constraint row.** `_check_cross_constraints` (`documents.py:1342-1400`) already
implements the row check over `pins: dict[str, DescriptorPin]`; today its `execution_version`
argument is the bench's OWN pin (admission's fact). The run side calls the same building
blocks with the composition's version: a sibling helper
`_check_run_floor(pins, contracts)` in `documents.py` loads
`load_cross_constraints_from_corpus(_corpus_root_of(contracts))` (the loader,
`standards/dependency.py:869`), selects rows for `contracts.name`, and applies the same
interval (`parse_interval(...).contains(record.otdp_version)`) and `adapter_api`
(`_adapter_api_const`) legs with the same dev/rc skip, refusing:

```
cross_constraint_violation: descriptor[<id>] pins otdp@<v> but this gateway
runs execution@<contracts.name>, whose implemented-dialect row requires
otdp <range> (<row.evidence>)
```

— the row's own existing prefix (one vocabulary entry, already in both guides), the subject
rewritten from "this bench validates against" to "this gateway runs" because for a
pinned-old bench the bench's own row is a different (here absent) row. The structural
reason this floor is the gateway's to assert (G4 discipline, stated for the invariant):
the gateway's adapter implementation is bound to the ACTIVE corpus by REG-4's three-way
pin (`tests/sdk/test_adapter_agreement.py`), so a device dialect outside the composition's
row is one this gateway has **no implementation agreement for** — running it would produce
checks whose results mean different things on hosts implementing different compositions,
the exact inversion of the one-line promise. The composition's row IS the
"gateway-side implemented-dialect minimum" the #220 record's Risk-1 mitigation named.
No standards bytes move. A composition version carrying no row asserts no floor (the
honest negative, per-version, disclosed) — including a DEV_HEAD composition, whose dev
label matches no released row by construction.

Options (b) and (c), with the evidence, are §7 Fork 1 — (b) is evidence-dead under G-4
(§0), (c) punts the decision into a row-posession proxy. The recommendation is (a); the
fork is presented because it sets runnability policy for every future version pair.

### 1.2 `src/benchweave/interfaces/operations.py` — the synchronous §5 runnability pre-check

One new private helper on `Operations`, called from `_assert_bench_acceptable` after the
binding request-id match and BEFORE lease consumption (a refused start consumes nothing,
keeping the existing "no lease consumed for a start that is refused" discipline; the
existing inverted guard is mirrored — an UNSTORED binding or descriptor silently skips the
pre-check and stays asynchronous under the worker's authority, never admissive early):

1. Resolve the binding document by digest (the pre-check's own existing read) →
   `binding["bench"]["sha256"]` → the bench document from the content store.
2. `_classify_execution_pin(bench["contract_version"], corpus=...)` —
   retired/unknown/nonconforming refuse SYNCHRONOUSLY with the VR-37 vocabulary verbatim
   (the run-path admission refuses them anyway; this surfaces the same refusal at the POST
   instead of 202-then-outcome_unknown). A classifying pin proceeds.
3. The floor: for each `bench["devices"]` descriptor, resolve the descriptor document by
   digest, classify its `otdp_version` pin, and run `_check_run_floor(pins, contracts)`.
   Below-floor devices refuse `cross_constraint_violation:` (§1.1's message), typed as
   `errors.failure("policy_denied", …)` — the 14-code set's constraint-refusal vehicle
   (403, `retry: never`; the one existing precedent is the tripped-bench refusal,
   `operations.py:1300-1307`: a declared policy fact refusing an operation — not
   contention, not capability-absence). Fork 2 records the alternative (`conflict`).

`Operations` gains a `contracts: Path` constructor parameter — `create_app` passes the
directory it already resolved once (`app.py:906-909`); the seam never re-resolves (the
compose-once, thread-everywhere rule). MCP inherits the refusal through the same
`Operations.run_start` — one core contract, both transports (A13); no wire-schema bytes
move (the message rides inside the existing failure envelope; `policy_denied` is already
in the catalog's map).

### 1.3 `src/benchweave/control/coordinator.py` — the record threads the run's own version

- **`build_terminal_record` gains `execution_version: str | None = None`.** When threaded,
  the record's `contract_version` is stamped from the PINNED version's own run-record
  schema const, and the record validates against that schema — resolved DIGEST-VERIFIED
  through `_versioned_schema_path(corpus_root, "execution", execution_version,
  "run-record.schema.json")` (`documents.py:604-635`; the corpus row exists for both
  served versions, §0), replacing the blind `contracts / "run-record.schema.json"` read.
  `None` keeps the composition path — which ALSO moves to the digest-verified resolution
  (uniform mechanism; a dev composition's dev rows cover its directory). Stamping from
  the schema's const — not from the threaded label, not from `contracts.name` — keeps the
  dev-composition hazard #221's record documented (a dev directory is `X-dev` while its
  consts hold the active value): the record always claims exactly what its validating
  schema demands. This generalizes #221's row-3 derivation from "the composition's schema"
  to "the version's schema"; the derivation itself is #221's to land first, and this slice
  rebases onto it (Fork 4).
- **`_RUN_RECORD_VALIDATORS`** (`coordinator.py:94`) keys by resolved path — per-version
  keys fall out; the cache gains the const beside the validator (or a parallel const cache,
  builder's pick by diff weight — #221's landing decides the shape being generalized).
- **The normal path threads `self._docs.execution_version`** (`_finish_run`'s call,
  `coordinator.py:829-841`): a 0.1.0-lattice run's record carries
  `contract_version "0.1.0"`, its `binding.version` is the validated binding document's
  own const (`_binding_pin`, `coordinator.py:623-630` — already honest), and the record
  validates against `execution/0.1.0/run-record.schema.json`. When
  `docs.execution_version != contracts.name`, one disclosure reason is appended (the
  `_RetainingCoordinator._body_truth` precedent, `app.py:418-427`):
  `implementation_disclosure: gateway composition execution@<contracts.name> executed
  lattice execution@<docs.execution_version>` — the composition fact rides the record's
  open reasons list without any schema motion (the record schema is closed; reasons
  strings are not).
- **Recovery: the skip becomes an era-consistent terminalization — with the D4 discipline
  carried over, source-upgraded.** `_is_other_carried_dialect` is replaced by
  `_recovery_record_version(run_binding_row) -> str | None`:
  - **Doc first:** `run["binding"]["sha256"]` → the content store's binding document →
    its `contract_version` (the validated artifact's own const — the strongest surviving
    evidence of the run's admitted dialect; D4 never trusted the echo and neither does
    this, it reads the digest-pinned bytes).
  - **Echo fallback:** when the doc is absent (pre-D4 rows, disposed content — the era
    test fixtures carry `"0"*64` digests), the stored echo `run["binding"]["version"]`,
    JUDGED through `_classify_execution_pin` exactly as the fold taught (caller data is
    not era fact until it classifies as a carried dialect).
  - Carried dialect (either source) → that version threads into
    `build_terminal_record` (era record: `interrupted` / `unknown`, CTL-9 unchanged —
    recovery still dispatches nothing). Composition version or caller-data echo with no
    stored doc → the composition record exactly as before the fold. **Doc/echo
    disagreement when both resolve, or an unjudgeable doc const, is containment**: no
    record, the run stays non-terminal, logged under a narrowed, honestly-named prefix
    `recovery_execution_version_unresolved:` (VR-38-additive; the old
    `recovery_execution_version_not_runnable:` RETIRES — the runs it named are now
    terminalized, and the containment class that remains is "unresolvable", not "not
    runnable"). Both recovery legs (`coordinator.py:466-486` lease leg,
    `:527-560` ghost leg) call the same helper; era runs enter `recovered` and the
    projection closes (the bench-busy wedge clears — the upgrade-path win).
- **The literal `"0.2.0"` at `coordinator.py:232` disappears** (threaded-or-derived
  stamp). The counter (`scripts/standards/count_version_literals.py`, BASELINE 12) reads
  11 ≤ 12 and passes untouched; the re-baseline DOWN is #221's train, not this slice's.

### 1.4 `src/benchweave/interfaces/app.py` — the guard is REPLACED, not kept

`app.py:717`'s inequality guard would refuse exactly the runs this slice legalizes; it is
replaced in place (same position: after the run-path `admit_documents`, before device
plans/bridges) by the authoritative floor check over the ALREADY-CLASSIFIED pins:
`_check_run_floor(docs.pins, contracts)` — zero extra reads at the worker (admission
produced `AdmittedDocuments.pins`), refusing `AdmissionRejected` with §1.1's message
before any device plan or bridge exists. Two layers, ONE vocabulary and ONE rule: the
seam pre-check is the wire-visible early refusal (best-effort, skipping unstored
documents), the worker check is the authority over the full admission result — the same
seam/worker split the binding request-id match already uses. There is no third class of
"not runnable version" left to guard: unclassifiable pins keep the composition posture at
admission, classifying pins are runnable subject to the floor. The stale in-code comment
at `app.py:700-716` (which still asserts "Recovery cannot bypass it: no pinned-old run can
exist in any store" — the claim the #220 fold corrected) is rewritten with the mechanism.

### 1.5 The rider — the OTDP double-colon splice

`documents.py:540`: `f"{prefix}: {logical} {rest}"` renders `retired_identifier:: …`
(the prefix constant already ends in a colon). Aligned to the execution lane's
single-colon shape (`documents.py:1649-1650`): `f"{prefix} {logical} {rest}"`, with the
provider/descriptor test assertions that pin the old rendering updated in the same fold.
One line plus its pins; rides this slice's PR because `documents.py` moves anyway
(the governor's NIT disposition from PR #261).

### 1.6 Tests and fixtures

- `tests/control/test_record_lane.py` (new): the G-arms of §5 over the existing
  `tests/fixtures/lattice-execution-0.1.0/` (unchanged — the recovered bytes are already
  in the tree) and the F1b below-floor lattice (built in-test the way
  `test_execution_pin.py:283` builds it).
- `tests/control/test_execution_pin.py`: `test_f3_run_start_on_pinned_old_lattice_refuses`
  (`:570-616`) FLIPS to the floor refusal's arms; F1b's admitting cell gains a
  run-side-refusing companion assertion; the no-regression arms stay.
- `tests/faults/test_recovery_sweep_faults.py`: the two era arms
  (`:226-297`) flip to era-terminalization; the caller-data boundary arm keeps its
  expectation; a new disagreement arm and a lying-echo arm (stored 0.2.0 doc beside a
  "0.1.0" echo → doc-first composition terminalization, not a skip).
- Existing suites stay the no-regression net: `tests/control/`, `tests/unit/`,
  `tests/faults/` (control/ + concurrency touched), `tests/integration/test_procedures.py`
  (the run path).

### 1.7 `docs/internal/invariants.md` — CON-1 amendment (append)

One appended amendment (evidence line `issue #260, 2026-09-29`), appended AFTER the #220
amendment: running is an IMPLEMENTED-DIALECT fact, not a composition-VERSION fact — the
composition's cross-constraint row governs every run's device pins whatever the lattice
pins (the honest negative per-version: a rowless composition asserts no floor); terminal
records carry the run's own validated execution version, stamped from and validated
against the pinned version's digest-verified run-record schema; recovery terminalizes
era runs against their own version (doc-first, echo-judged fallback, disagreement and
unjudgeable const contained under `recovery_execution_version_unresolved:` with no
record); `execution_version_not_runnable:` retires with the guard that emitted it.

## 2. Precedents — each verified in current main

| Mechanism reused | Precedent, cited |
|---|---|
| Row check over classified pins (interval + adapter_api + dev/rc skip) | `_check_cross_constraints` documents.py:1342-1400 (#217, threaded by #220) |
| Digest-verified per-version corpus resolution, `version_unknown`/`corpus_file_unpinned`/`corpus_pin_mismatch` | `_versioned_schema_path` documents.py:604-635 (#220's generalization of #217) |
| Judged-never-trusted classification of stored caller echoes | `_is_other_carried_dialect` coordinator.py:110-137 + `test_caller_data_ref_version_terminalizes_as_before` (#220 fold, D4) |
| Synchronous §5 refusal typed from the frozen 14-code set, before the request key / lease consumption | `_assert_bench_acceptable` operations.py:1687-1810; the D9/§5 discipline (`no dangling idempotency tombstone`) |
| `policy_denied` as a declared-policy refusal (not contention) | the tripped-bench reset refusal operations.py:1300-1307 |
| Seam-early / worker-authority split over one rule | the binding request-id match: pre-check operations.py:1788-1798 vs the run-path admission |
| Implementation facts riding the record's open reasons list | `_RetainingCoordinator._body_truth` app.py:418-427 (F3 disclosures) |
| Compose-once `contracts` threading into a consumer | `create_app` app.py:906-909 → `_build_run_factory`/bootstrap/recovery (#176 increment 2) |
| Cache keyed by resolved corpus path | `_RUN_RECORD_VALIDATORS` coordinator.py:94; `_validator` documents.py:195-207 |
| One vocabulary entry reused across surfaces | `cross_constraint_violation:` (admission #217 → run-side #260), the CON-1 grep surface |
| Recovery arms rebuilt as behavior flips, wedge-to-terminal | the #156 fix wave's ghost-leg pattern in `recover_interrupted` coordinator.py:527-560 |

## 3. Minimal first-increment scope and deferrals

**In scope (the increment):** the run-side floor check (worker + seam, one rule, one
vocabulary); `Operations(contracts=…)` threading; the §5 runnability pre-check; the
record threading (`execution_version` param, digest-verified schema resolution,
const-stamp); the recovery terminalization upgrade (`_recovery_record_version`,
doc-first/echo-fallback/containment); the guard's replacement; the disclosure reason;
the rider splice; CON-1's appended amendment; both guides' prefix lists (retire
`execution_version_not_runnable:`, retire `recovery_execution_version_not_runnable:`,
add `recovery_execution_version_unresolved:`, document the run-side
`cross_constraint_violation:` subject); the test motions of §1.6. No standards bytes. No
SDK bytes. No interface-schema/openapi bytes. No CLI.

**Deferrals** (each with a home and a reopen trigger):

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| L1 | A wheel-install end-to-end run on a pinned-old lattice (the #220 record §8 already parked it "with E1"; the packaged-first resolution is inherited — the whole retained tree ships and `_corpus_root_of` serves the wheel layout) | Documentation here | The first operator-facing pinned-old run, or the next packaging-lane review |
| L2 | A run-evidence/public surface for the lattice's execution class and full pin record (E3 of #220, unchanged) | #220's record §3 E3 | The first consumer surface requesting the lattice's execution class |
| L3 | Extending the run-side floor to non-run energizing paths (change kinds that dispatch device work) — `change_apply`'s own admission governs today; the grep surface is the CON-1 amendment's rule sentence | Documentation here | The first change kind that dispatches through a device plan |
| L4 | A synchronous §5 pre-check for the non-bench admission classes (procedure/policy/binding pin faults surface asynchronously under the worker's poison guard) | Documentation here | Operator feedback that an async admission refusal class is operationally confusing at run start |

## 4. Invariant, governance, and drift impacts

- **CON-1:** one appended amendment (§1.7). The #220 amendment's sentence "Running is a
  composition-version fact" is superseded inside the new amendment's text (append-only;
  the history stays).
- **CTL-9:** untouched — era records are `interrupted`/`unknown`; recovery still never
  resumes bodies, never dispatches, still releases leases.
- **CON-14 / GOVERNANCE G-4:** zero bytes; the floor consumes the existing row. No row is
  retrofitted (Fork 1's (b) is not taken by this design).
- **CON-2, CON-4/8/10/12/13:** untouched — no corpus, manifest, lock, matrix, site, or
  projection bytes move. The literal counter reads 11 ≤ 12 (§1.3).
- **Obligations (drift-and-obligations.md):** 3+4 (both guides' machine-matchable prefix
  lists — §1.7's retire/add set); 20 is satisfied passively (count falls, baseline
  untouched); no fixture-lattice, SDK-pointer, or dependency motion. The standards-hold
  window's tripwire (`git diff origin/main...HEAD -- standards/`) reads empty — this is
  #203-family work and moves no standards bytes regardless.
- **Surfaces that move:** `control/documents.py` (floor helper + splice),
  `control/coordinator.py` (record + recovery), `interfaces/operations.py` (pre-check +
  constructor), `interfaces/app.py` (guard replacement, comment rewrite),
  `docs/internal/invariants.md` (append), `docs/operator-guide.md`,
  `docs/device-developer-guide.md`, the test tree. MCP/REST/openapi/CLI: no schema or
  enumeration motion (message text inside existing envelopes; existing failure code).
  SDK repo: none (the SDK validates descriptors, not run records — the run-record
  schemas are execution-corpus, and the SDK does not vendor a record builder).
- **CI cost:** one new focused test module + edits to three; full battery once before
  push; no new lanes; negligible wall-time.

**Tier call (Step-1 rules, #254, run on the expected diff): TIER 3** — primary path rules:
touches `src/benchweave/control/documents.py` (persisted-format surface row) and
`src/benchweave/control/coordinator.py` (run/record schema validation). The keyword scan
over the expected diff text (all added lines, docs and code): `recovery` PRESENT —
estimated ≥ 25 occurrences (the `recover_interrupted` rewrite in coordinator.py ~8, the
recovery test motions ~12, the invariants amendment ~3, both guides ~2); `sha256` PRESENT —
estimated ~8 (binding/bench digest resolution in the pre-check, record-schema resolution
prose, test assertions); `hashlib`, `threading`, `asyncio`, `subprocess`, `migrate`,
`protection` ABSENT from added text (the protection vocabulary sits in unchanged adjacent
code). Both hits independently force Tier 3; the two-lane adversary rule applies.
**Standards-governor:** the mandate's letter does not fire (no `standards/` path, no
locks, no SDK tree, no version strings in the diff); dispatched anyway as the conservative
reading — the diff's subject is standards-version semantics (the #220 precedent, recorded
either way in the PR body).

## 5. Measurable proof — acceptance rule G (pre-committed here; #260's issue body carried the constraints, this record binds the arms)

All arms are single-cell deterministic tests; counts and exit codes from junitxml/true
exits, never a filtered summary. RED proofs neutralize ONE mechanism at a time.

- **G1 (the run, RED today at the guard).** A run start over the recovered 0.1.0 lattice
  (`tests/fixtures/lattice-execution-0.1.0/`, devices pinning otdp 0.2.2 — in-floor)
  completes end to end; the persisted terminal record carries
  `contract_version == "0.1.0"`, `binding.version == "0.1.0"`, the disclosure reason
  naming both versions, and the test RE-VALIDATES the persisted record bytes against the
  digest-verified `execution/0.1.0/run-record.schema.json`. RED at base: `app.py:717`
  refuses (`test_f3_…`'s current expectation). KILL: a 0.1.0-lattice run producing a
  record stamped anything but "0.1.0", or one that fails 0.1.0-schema validation.
- **G2 (the wire, RED today as 202+outcome_unknown).** `run_start` over the below-floor
  lattice (the F1b shape: acked otdp-0.1.2 descriptor on the 0.1.0 bench — admits at
  startup) refuses SYNCHRONOUSLY: an `errors.OperationFailure` with code `policy_denied`,
  the message beginning `cross_constraint_violation:` and naming the device, the
  composition version, the row's range and its PR #201 evidence; NO run row, NO §9
  request key (the D9 discipline), the REST call is NOT 202. RED at base: the call
  202-accepts. KILL: any 202-accept of a below-floor run, or an untyped/uncoded refusal.
- **G3 (the floor's own RED, neutralized mechanism).** With ONLY the floor check
  neutralized (worker + seam sites), G2's fixture STARTS (the guard no longer refuses on
  version inequality) — proving the floor is the refusing mechanism, not incidental
  plumbing. KILL: the neutralized run still refusing (another silent gate exists — find
  it or the design is wrong).
- **G4 (era terminalization, RED today as the skip).** Both era arms flip: the stored
  0.1.0-era run (lease leg and ghost leg) terminalizes with
  `contract_version == "0.1.0"` validating against the 0.1.0 schema, is reported for
  projection close, and the bench-busy wedge clears (`LIVE_RUN_STATES` empty). RED at
  base: the skip leaves `terminal` None. KILL: an era record stamped "0.2.0" (the
  original F3 launder), or a caller-data echo ("9.9.9", unresolvable doc) changing
  outcome — it still terminalizes against the composition, exactly as before.
- **G5 (the D4 upgrade's own arms).** (a) Lying echo: stored binding doc const "0.2.0"
  beside echo "0.1.0" → doc-first: the NORMAL composition terminalization fires (RED at
  base: the base classifies the echo and skips). (b) Disagreement containment: doc const
  classifies carried "0.1.0", echo "0.2.0" → NO record, the run stays non-terminal,
  logged `recovery_execution_version_unresolved:` (RED: without the containment check the
  record would carry the doc's version beside a contradicting row echo).
- **G6 (no-regression, the KILL arm).** Every active-version run's record is unchanged:
  `contract_version == "0.2.0"`, validated against the 0.2.0 schema, no disclosure
  reason; the full existing run-path, faults, and integration suites green; F1b's
  admitting cell still admits; the ratchet reads ≤ 12. KILL: any behavior change for
  composition-version runs beyond the record's unchanged bytes.
- **G7 (the rider).** No `retired_identifier::` double-colon rendering remains anywhere
  the provider/descriptor arms assert; single-colon pinned. RED: trivial (today's
  rendering carries `::`).

Underpowered rule (pre-committed): if any RED cell cannot be reproduced at the merge base
(G1 at the guard, G2 at the 202, G4 at the skip, G5a at the base's echo-classifying skip),
the FIXTURE is wrong, not the mechanism — stop, re-baseline the fixture, and re-run the
RED before building. No statistical arms exist; nothing here depends on sample size.

## 6. Top risks — and what an adversary attacks first

1. **The floor can be routed around by a rowless future composition.** A composition
   version whose standard declares no cross-constraint row asserts no run-side floor —
   the honest negative extended from admission to running. MITIGATION: disclosed in the
   CON-1 amendment (per-version honesty, same doctrine as admission's); the row is the
   evidence carrier, and inventing one where the standard declares none is Fork 1(b)'s
   fabrication. FALSIFIER: a future composition landing rowless while devices below any
   prior floor run — the governor lane's standing question at that bump.
2. **The seam pre-check's skip-on-unstored is an early-refusal gap, not an admission.**
   An unstored binding or descriptor silently defers to the worker's poison path (202 →
   outcome_unknown), unchanged. An adversary calls this a wire-surfacing hole; it is the
   pre-existing inverted-guard doctrine, now documented in the helper. FALSIFIER: G2's
   fixture with an unstored descriptor — the run 202s and dies at admission (asserted as
   the disclosed residual, not as a passing floor).
3. **Era-record version laundering through a planted doc.** The doc-first source reads
   the content store by the run row's stored digest — an adversary who can write content
   rows could plant a doctored "binding document" to steer an era record's version.
   Contained: content rows are digest-addressed and append-only through the admission
   path; a planted row's bytes must hash to the digest the ERA seam already stored
   (pre-D4 rows excepted, where the echo-judged fallback governs and caller data never
   upgrades to era fact without classifying carried). FALSIFIER: a test planting a
   disagreeing doc/echo pair expecting containment (G5b's shape) — a planted row that
   DOES hash to the stored digest is the original document by definition.
4. **Two refusal sites drift apart.** The seam pre-check and the worker floor check are
   two calls to one helper — but a future edit that touches one site only splits the
   rule. MITIGATION: both sites call `_check_run_floor` (no duplicated row logic); the
   CON-1 amendment names both layers. FALSIFIER: a test asserting the seam and worker
   refusals are byte-identical for the same lattice.
5. **The recovery flip un-wedges stores an operator deliberately kept wedged.** An
   operator holding an era cohort open (audit in progress) restarts and finds them
   terminalized. MITIGATION: the terminalization is `interrupted/unknown` — the honest
   recovery outcome CTL-9 always prescribed; the wedge was containment-for-lack-of-a-
   record-dialect, not a policy tool. The amendment and the guide say so. FALSIFIER:
   none mechanical; operator objection at review is the real one (name it there).
6. **Rebase collision with #221 on `coordinator.py`.** Both slices rewrite the record
   stamp. The serialization is already declared (in-progress note); this record's §1.3
   states exactly what supersedes what (the threading supersedes the derived DEFAULT;
   the const-stamp derivation survives inside the threaded path). FALSIFIER: a merge
   that leaves both a threaded param and a composition-only stamp (review catches by
   the amendment's wording).

## 7. Forks for the maintainer

- **Fork 1 — the floor (the genuine product fork; #260's constraint 1).**
  **(a) RECOMMENDED — the composition's row as the run-side implemented-dialect floor**
  (§1.1): evidence-cited (PR #201 + REG-4's structural pin), zero standards motion, lets
  the real recovered lattice run (its 0.2.2 devices are in-floor), refuses exactly the
  below-floor attack, and completes the standing doctrine ("an ack authorises the
  otdp-window load, never the execution runtime interface" — a RUN is that interface).
  **(b) retrofit a 0.1.0 row** — REFUTED on evidence: G-4 requires citable evidence; the
  0.1.0 era declared no coupling anywhere (§0), and history's only 0.1.0-era lattices pin
  otdp 0.2.2 — a row asserting anything would be fabrication, the exact failure the
  file's honest-negative note guards against. **(c) refuse runs on versions without
  rows** — punts: runnability becomes row-possession, refuses the recovered lattice's
  real runs, and reopens the same fight at the next rowless version. If the owner rejects
  (a), (c) is the fallback and the record lane's threading work stands unchanged (only
  the refusal predicate narrows) — name the pick at review and the builder adjusts one
  helper.
- **Fork 2 — the floor refusal's failure code.** `policy_denied` (403, recommended — the
  declared-policy-refusal class, tripped-bench precedent) vs `conflict` (409 — the
  contention vehicle; a below-floor start is not contention). Both are in the frozen
  14-code set; the choice rides inside `errors.failure(...)` — one token at one site.
- **Fork 3 — retiring `recovery_execution_version_not_runnable:` vs keeping it for the
  narrowed containment class.** Recommended: retire and add
  `recovery_execution_version_unresolved:` (the contained class is "unresolvable", not
  "not runnable"; an honest name beats grep continuity). The conservative alternative
  keeps the old prefix over the narrowed class. Guides move either way.
- **Fork 4 — landing order vs #221.** Already serialized behind #221 (the in-progress
  note); this record's §1.3 defines the rebase contract: the threading replaces the
  derived default for the record field, generalizing the const-stamp to the version's
  own schema. If the owner prefers to reverse the order, #221 rebases onto this slice
  instead and its row-3 note already says so.

## 8. DISCLOSED UNVERIFIED

- **The pre-check's content-read cost** is two-to-N SQLite point lookups plus cached
  classifications per run_start — asserted negligible, not measured. If the review wants
  a number, the builder measures before landing (a one-line timing log, removed with the
  branch's scratch).
- **`_adapter_api_const` availability at the seam**: the adapter leg of the floor reads
  the pinned otdp schema's const through the existing cached helper — assumed
  import-clean from `operations.py` (it lives in `documents.py`); the builder verifies
  the import graph and, if it drags heavyweight module state into the seam, moves the
  seam-side floor call behind the existing `documents` import the seam already makes.
- **Pre-D4 era rows** (2026-09-11..09-17) may carry binding digests that resolve to a
  DIFFERENT document than the run's true binding (the D4 fix's own subject). The design
  treats a resolving doc as authoritative over the echo; if the review judges pre-D4
  stores too ambiguous, the containment class widens by one condition (digest resolves
  but predates D4 — undetectable from the row alone; the honest widening is
  echo-judged-only for rows whose doc's `contract_version` disagrees with a CARRIED
  echo, i.e. exactly the G5b containment). Disclosed, not decided.
- **The guides' exact wording** for the retired/added prefixes is drafted at build time
  against the final Fork 1/3 calls; the record fixes the prefix set, not the prose.

---

*Design record for issue #260 (#220 slice-6 follow-on, the E1 record lane). No standards
bytes move under the recommended Fork 1(a). The four issue constraints are elaborated into
the pre-committed arms G1–G7, never rewritten. Deferral table §3 follows the
`.claude/deep-review/README.md` contract.*

---

## ADDENDUM — the fold wave (2026-09-29, issue #260's refute slate)

Corrections and rider rows the four-lane fold added to this record. Each
names its row; nothing above is rewritten (append-only).

- **Row 5 (gov-M1) — the ack-threading rider, declared.** The run path
  threads an optional ``operator-acknowledgements.json`` beside the
  lattice documents into admission (``_spool_documents``, the
  transport-settings precedent). WHY: G2's below-floor fixture (and any
  real below-floor lattice) carries a retained-out-of-range pin that only
  admits behind its recorded acknowledgement — without the threading the
  worker admission refuses ``operator_ack_required:`` before the floor can
  run, and the slice's own G-arms are unrunnable. RUN-PATH AUTHORITY
  EXPANSION, disclosed: the run path now honors operator acknowledgements
  the same way startup and recovery already did. TRUE POSTURE (the
  built comment): the file is RE-READ per run start — not digest-pinned to
  the startup admission — and a malformed file fails inside the worker's
  build (202 → ``outcome_unknown`` under the poison guard), never as a
  POST refusal; the startup lane's loader failure remains the startup
  refusal. The two failure shapes are disclosed, not shared.
- **Row 4 correction — the §1.3 sentence "the skip's reason evaporates for
  the judgeable cohort" is overstated and is superseded by policy
  relativity:** an echo is judged against TODAY's policy, and an echo the
  corpus no longer carries (a later retirement) is CONTAINMENT, never a
  composition-flip stamp. Doc-first stays era-stable; the judgeable cohort
  that evaporates is the doc-resolved one.
- **NIT-2:** §1.3's "The counter reads 11 ≤ 12" predates #221's landing —
  the counter is ZERO-MODE (0 outside the register); this slice's
  threading moves no literal and the reading is unchanged.
- **NIT-3:** §1.3's "a dev composition's dev rows cover its directory" is
  conditional on the dev head's corpus rows being repin-current — a
  partially-rowed dev directory refuses ``corpus_file_unpinned:`` (row 7's
  containment class).
- **NIT-5:** §5 G1's "the test RE-VALIDATES the persisted record bytes
  against the digest-verified schema" overclaimed nothing; but the
  arbiter arm's "the manifest is the independent arbiter" comment is
  superseded by row 11's runtime swept-const arbiter (the record build
  itself refuses; the manifest remains the independent second layer).
- **DEFERRED (homes and reopen triggers per the README contract):**
  (a) the content-store corruption crash class in recovery's doc-first
  read (pre-existing store posture; trigger: the first direct-SQLite
  writer or a corrupt-row incident); (b) the $id-conventions corpus fact
  (execution 0.1.0's run-record ``$id`` says 1.0.0 — inert, out of scope,
  ledgered here); (c) the seam pre-check's read-cost measurement (§8's
  disclosed-unmeasured; trigger: a review that wants the number).
