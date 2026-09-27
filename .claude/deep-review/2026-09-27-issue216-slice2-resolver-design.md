# Issue #216 — #203 Slice 2: Resolver Surface and Plugin Constraint/Lock Carriers — Design Record

**Status:** Design (builder-ready; owner-pass defaults recorded below) · **Tracking issue:** madeinoz67/benchweave#216 (parent #203) · **Design of record:** `docs/implementation-planning/09-standards-dependency-design.md` §3.4, §4 Slice 2 (acceptance rule B, pre-committed — not weakened anywhere below)

**Evidence baseline:** local checkout `b4708f7` on `feat/issue216-resolver-surface`. Slice 1 (#215) is merged (PR #234): the `dependency_policy` block, its loader/validator, carried/served derivation, and the export/check lanes are all landed and green. All citations below were read at this commit unless marked otherwise.

**Owner-pass fork rulings (controller, 2026-09-27):** F-A standalone `standards/cross-constraints.json` (follows the design of record); F-C `--locked` is a `pin` flag, `check`'s dependency lane runs the same comparison unconditionally (follows the issue body's F3 lean); F-B `policy_change_unruled:` deferred as D10, with obligation 21's "landing with slice 2" sentence amended in this PR — the owner's merge is the blessing; F-D `pin` bootstrap deferred as D9 (keeps the resolver git-free).

---

## 0. Premise verified — the slice is buildable exactly as the design record scopes it

| Assumption | Verified at |
|---|---|
| Policy block landed with the seed ranges/yank/retired sets | `standards/standards-manifest.json` (otdp `>=0.2.0,<0.3.0`, 0.2.1 yanked, retired `["0.3.0"]`, …) |
| Loader + served/carried derivation exist | `src/benchweave/standards/manifest.py` — `load_dependency_policy`, `served_versions`, `carried_versions`, `validate_dependency_policy` |
| Served set at the seed | `tests/standards/test_dependency_policy.py::test_policy_block_loads_and_derives_the_served_set` (10 served across 6 ids, per-id sets pinned) |
| DPS-150 lock v1 shape | `plugins/fnirsi/dps150/contracts/lock.json` — exactly `repository, revision, directory, otdp_version ("0.2.2"), adapter_api_version ("1.1"), sha256` (8 files, 4 of them `.md` prose companions **not** in corpus rows) |
| Registry lock-writer precedent | `src/benchweave/registry/admission.py` — `_canonical` (`json.dumps(sort_keys=True, separators=(",",":")) + b"\n"`) and `_lock_document`, which validates through `load_lock_document(raw, sha, max_bytes=…)` **before** writing |
| Canonical-JSON helper already in the standards package | `src/benchweave/standards/export.py::canonical_json` — byte-identical idiom to `_canonical` |
| CLI family | `src/benchweave/standards/__main__.py` — export/check/matrix/versions/repin; `check` = SDK-pairing drift check (VR-38: keep it, extend it) |
| SDK lock row shape (the v2 sibling) | standalone SDK checkout `standards-lock.json`: `{id, version, active, yanked, status, files:[{path,sha256}]}`, canonical-compact bytes |
| B6 discriminator | verified live: `otdp/0.2.0` `$defs.customTransport` has **no** `provider` (props: connection_key/settings/type, `additionalProperties:false`); 0.2.1 and 0.2.2 have `provider`; the 0.2.1↔0.2.2 descriptor diff is **exactly 4 lines, all version strings** (const, `$id`, title, description) |

One design-record drift found and designed around (not a blocker): **a new `standards/cross-constraints.json` trips two hard-coded exemption lists today.** `repin.py::_check_coverage` refuses any `*.json` under `standards/` lacking corpus rows unless its **basename** is in `_MANIFESTS = {corpus-manifest.json, standards-manifest.json}` (`corpus_file_unpinned:`), and `tests/contract/test_baseline.py::test_manifest_lists_every_contract_file` (tests/contract/test_baseline.py:99-103) fails the same file as "manifest drift". §3.3's "lives OUTSIDE the corpus like the policy block" is true semantically but not mechanically — the policy block lives *inside* an already-exempt filename. Slice 2 must extend the exemption mechanism (§1.4). This also serves slice 4's `standards/promotion-records.json`.

---

## 1. The mechanism, file by file

### 1.1 `src/benchweave/standards/dependency.py` (new module)

Same package as repin/check/export (no new tool — Q1). Pure over committed bytes; **reads exactly four input kinds and nothing else**: `standards/standards-manifest.json` (policy block), `standards/corpus-manifest.json` (rows), `standards/cross-constraints.json`, and the package's `contracts/{constraints,lock}.json`. Never corpus file bytes, never git, never network, never a clock (A04; the CON-14 second sentence).

**Interval representation.** `@dataclass(frozen=True) class Interval: lower: str; upper: str` — the grammar is exactly the half-open `>=X.Y.Z,<X.Y.Z` the policy block already enforces, so two strings plus `contains(v) -> bool` via `version_tuple` comparison. Version ordering reuses `manifest.py::_version_tuple` — **rename it public `version_tuple`** (one internal caller, `StandardPolicy.in_range` at manifest.py:75; two private version-parsers in one package is drift bait). Version *shape*: pure three-component semver only.

**Caret expansion — one pure function, `expand_caret(value: str) -> Interval`** (Q3, B3):

| Input | Expansion | Rule |
|---|---|---|
| `^0.2` | `>=0.2.0,<0.3.0` | two-component: patch→0; **0.x bumps the MINOR position** (`^0.2` ≠ `>=0.2.0,<1.0.0` — design risk 3) |
| `^0.2.5` | `>=0.2.5,<0.3.0` | 0.x.y: minor position |
| `^0.0.3` | `>=0.0.3,<0.0.4` | 0.0.x bumps the PATCH position |
| `^1.2.3` | `>=1.2.3,<2.0.0` | x≥1 bumps the MAJOR position |
| `^0`, `~1.2`, anything else | refuse `constraint_syntax_unexpanded:` | sugar is authoring input only |

Called at every boundary where authoring input enters: the CLI `--set`/`--precise` argument parser (authoring accepts `^0.2`, writes the expanded interval), and — as a **refusal check, never a silent expansion** — both stored-document loaders (constraints.json, lock.json), mirroring `manifest.py::_parse_range`'s existing `constraint_syntax_unexpanded:` posture. B3's "expands at READ time" is satisfied by the pure function being the only path from authoring to storage; **a caret persisted in any committed file refuses**.

**Classification — yanked/retired/unknown are three answers, one comparator.** `classify_pin(policy, root, standard_id, version)`:

| Pin state | Prefix | Notes |
|---|---|---|
| served (retained ∧ in-range ∧ ¬yanked) | — (resolves) | |
| retained ∧ in-range ∧ yanked | — (resolves) + deprecation warning | warning names the derived move-to = highest served version (`max(served_versions)`), 0.2.2 at the seed; the fold-F-E-10 fallback (range lower bound when nothing is served) applies |
| retained ∧ out-of-range (e.g. otdp 0.1.2) | `version_not_served:` | same meaning as the SDK's prefix (not in the served set) |
| retired identifier (e.g. otdp 0.3.0) | `retired_identifier:` | carries the re-target hint ("0.3.0 is retired; the next minor is 0.4.0") |
| never carried (e.g. 9.9.9) | `version_unknown:` | distinct remediation: publish or widen |
| `-dev` shape | `dev_pin_unsupported:` | clean refusal naming slice 4 as the carrier (dev *resolution* is §3.6/slice 4; this slice only needs VR-28's exclusion and this refusal shape) |
| `rc.N` or other suffix | `version_shape_invalid:` | the `standards_entry_version_invalid` posture extended to pins |

Every refusal message carries the five VR-37 fields inline: standard, pinned version, supported range, move-to, migration-note pointer (today always "migration guidance pending" — the `matrix.py::_guidance` idiom; per-version note pointers are slice 5).

**Resolution algorithm (deterministic, minimal motion — VR-26/VR-27):**

1. Load + schema-validate constraints (§1.2); every named standard must have a policy row (`constraint_standard_unknown:`).
2. Load the prior lock if present (v1 parsed into its otdp projection; v2 into rows).
3. Per constrained standard: **candidate = the prior locked version if it still satisfies the constraint interval and classifies served-or-yanked; else the highest SERVED version in the interval.** Auto-selection never picks yanked (the 0.2.1 rule), never a pre-release (VR-28). No candidate → `constraint_unresolvable:` naming the interval and the served set.
4. Cross-constraint pairwise check over the resolved set (§1.4) — a violating pair refuses `cross_constraint_violation:` naming both versions and the row's evidence.
5. Emit the lock document; canonical bytes (§1.3).

`upgrade <standard> --precise <version> --package <dir>` overrides step 3 for exactly one standard with an explicit classification of the target; **every other row re-emits byte-identical** (B2). A deliberate downgrade is legal — `--precise` names any served (or yanked-with-warning) version; silent rollback is what minimal motion prevents (design risk 2's falsifier: a re-resolve with unchanged constraints moving any row).

**Row digest derivation (exact).** For each resolved standard row: `digest = sha256(canonical_json([[path, sha256] for row in sorted corpus-manifest rows under "<id>/<version>/"]))` — a digest-of-digests over the corpus manifest's own rows (the design's offered option; the per-file truth already lives in the byte authority, and the enumeration-from-corpus-rows derivation is precedented by `export.py::_entry`'s non-active row file set). Compact, minimal-motion friendly, and the lock stays a *claim* every consumer re-derives — the anti-forgery posture of design §7 risk 1.

**`--locked` (VR-30, B5).** A flag on `pin`: resolve in memory, byte-compare against the on-disk lock; equal → exit 0 (printing any yank warnings), different → `plugin_lock_drift:` exit 1. Zero network by construction; the test fixture proves it (§5).

### 1.2 `contracts/constraints.json` — schema home and authoring rules

- **Home of the SCHEMA:** inline Python dict constants in `dependency.py` (`CONSTRAINTS_SCHEMA`, `LOCK_V2_SCHEMA`), validated with `Draft202012Validator(..., format_checker=FormatChecker())` + `check_schema`, cached — the `registry/schemas.py::_make_validator` idiom and the `TRANSPORT_SETTINGS_SCHEMA` precedent (`src/benchweave/control/provider_settings.py:66`, the named in-tree pattern for gateway-side non-corpus schemas). `contracts/` is plugin-authored **data**; the validating schema is gateway machinery and stays in the gateway package. Shape errors refuse `constraint_document_invalid:` / `lock_document_invalid:`.
- **Stored form:** explicit intervals only (a stored caret refuses, §1.1); `constraint_version: 1`; `standards: {<id>: "<interval>"}`; `opt_in: {}` (present now, populated only by slice 4's dev pins).
- **DPS-150's authored file ships with the slice:** `{"constraint_version": 1, "standards": {"otdp": ">=0.2.0,<0.3.0"}, "opt_in": {}}` — otdp only; authoring a plugin-ui constraint DPS-150 does not use would be fake data (B2's plugin-ui control runs on the synthetic fixture, §5).

### 1.3 `contracts/lock.json` v2 writer

- **Canonical bytes — DECIDED: `canonical_json` (sort_keys, compact separators, trailing newline)**, imported from `export.py`. Justification: (a) the design names `_lock_document` as the binding precedent and CON-14 says "locks are canonical-JSON"; (b) the closest sibling artifact, the SDK's `standards-lock.json`, is exactly this form; (c) B1's byte-identity is serialization-independent in principle, but canonical form additionally makes key order a non-issue for review and hand-merges. **Consequence named up front:** DPS-150's lock is indent-2 today; the first `pin` re-serializes the whole file (one-time reformat; *values* kept verbatim, provable via `tests/contract/test_dps150_lock.py` passing unchanged — it reads `directory` + `sha256`, both preserved).
- **Shape:** existing keys kept verbatim in value — `repository`, `revision`, `directory`, `otdp_version`, `adapter_api_version`, `sha256` (the 8-file map, 4 `.md` companions included; it is the fetch-verify set, deliberately *not* the corpus-row set) — plus `lock_version: 2` and `standards: [{"id", "version", "stage": "released", "digest"}]`. The legacy top-level keys are defined as **the otdp projection** (they were otdp-only): re-derived from the resolved otdp row, they move iff it moves. `adapter_api_version` is resolved per Q12 from the **pinned** OTDP version's descriptor schema `$defs.adapter.properties.api_version` const (the `validate_identity` derivation at manifest.py:668-682, relocated to the pinned version — G-2's amendment) — no independent range axis this arc.
- **Write path:** build → `canonical_json` → validate through `LOCK_V2_SCHEMA` **before** writing (the `_lock_document` order) → atomic staged write (`staged.write_bytes` + `os.replace`, the repin/admission staging idiom).
- **Idempotence:** re-`pin` with unchanged inputs writes byte-identical bytes (B1; the write may be skipped when bytes already match — repin's "writes only when a digest changed" idiom).
- **Bootstrap deferral:** `pin` requires an existing lock to extend (the DPS-150 state). A package with constraints but no lock refuses `plugin_lock_absent:` naming manual bootstrap (hand-author the v1 provenance keys, then `pin`). Fresh-lock creation needs `repository/revision/directory` provenance decisions that belong with D1's fetch lane (deferral D9, §3).

### 1.4 `standards/cross-constraints.json` + loader + retrofit rows

- **Home — DECIDED: `standards/cross-constraints.json`** (the design-named home, §3.3 and §5's on-disk inventory), a governance file beside the two manifests, **no corpus-manifest rows, no repin** (the `sdk_compatibility`/`dependency_policy` family, GOVERNANCE "Identity and homes"). To make that placement true mechanically, the exemption mechanism extends once, root-scoped:
  - `repin.py`: `_MANIFESTS` becomes a root-relative-path set — exempt `path.relative_to(corpus).as_posix() in _GOVERNANCE_JSON` where the set is `{"corpus-manifest.json", "standards-manifest.json", "cross-constraints.json"}`. Relative-path membership is **tighter** than the current basename check (a nested same-named file never matches); both existing exemptions live at `standards/` root, so behavior is preserved for them.
  - `tests/contract/test_baseline.py`: the same root-scoped exemption in `_all_corpus_json_files` **and** `_contract_files` (the content tests' `$id` walk must not see it).
  - This one mechanism serves slice 4's `standards/promotion-records.json` (add the name then).
- **Loader:** fail-closed in `dependency.py`: shape errors `cross_constraint_invalid:`; a row naming a version with no retained directory refuses `cross_constraint_unresolved:` (the corrected `policy_entry_unresolved` posture — rows name released versions of their own standard; yanked/retired statuses do not apply here); `requires` values are explicit intervals (`constraint_syntax_unexpanded:` for sugar) or an exact `adapter_api` two-component string.
- **Retrofit rows — enumerated from the tree and the record:** exactly **one** row today, `{standard: "execution", version: "0.2.0", requires: {otdp: ">=0.2.0,<0.3.0", adapter_api: "1.1"}, evidence: "PR #201 prose: preserves the OTDP 0.2.0 and adapter API 1.1 runtime interfaces"}` — internally consistent with the tree (active otdp 0.2.2 sits in the interval; identity `adapter_api` is "1.1"). **The absence of other rows is deliberate and recorded in the file's header comment**: rows require citable evidence; execution 0.1.0, registry, interface, plugin-ui, plugin-ui-preview have none recorded (honest negatives, first-class).
- **Enforcement:** pairwise at resolve time over the resolved lock's standard set (`cross_constraint_violation:`); single-sourced with slice 3's bench-admission check, which consumes the same loader.

### 1.5 CLI — VR-48 siblings in `python -m benchweave.standards`

| Subcommand | Surface |
|---|---|
| `list` | per standard: active, range, retained / carried / served sets, yanked (reason, since), retired — deterministic render from the policy block + corpus rows (the `version_lines` style; no package argument) |
| `pin [--package <dir>] [--locked] [--set <id>=<interval-or-caret>]` | resolve → write/extend `contracts/lock.json`; `--locked` = verify-only (B5); `--set` is the authoring path through `expand_caret` |
| `upgrade <standard> --precise <version> [--package <dir>]` | one standard, exact target, minimal motion; prints the move-to/migration-note pointer ("migration guidance pending" until slice 5) |
| `check` (existing) | **extended, never replaced** (VR-38): after the SDK-pairing lanes, `run_check` gains `_compare_plugin_dependencies(root)` — for every in-tree package under `plugins/*/contracts/`: constraints absent → `plugin_constraints_absent:`; lock absent → `plugin_lock_absent:`; otherwise **re-resolve in memory and byte-compare** (a hand-edited constraint, a hand-forged digest, or a stale lock all surface as `plugin_lock_drift:` — the re-derive-never-trust posture; no new read of anything the resolver doesn't already read) |

Failure styling follows the family idiom: `prefix: detail` lines, `print(f"standards <cmd> error: {exc}", file=sys.stderr)`, exit 1; argparse's exit 2 for unknown subcommands stays distinct from refusals.

## 2. Precedents — each verified in current main

| Precedent | Where | Used for |
|---|---|---|
| `_canonical` / `_lock_document` (canonical bytes, schema-validate **before** write, staged write) | `src/benchweave/registry/admission.py` | lock v2 writer order and byte form |
| `canonical_json` | `src/benchweave/standards/export.py` | the exact bytes helper, reused not duplicated |
| `load_lock_document` through a vendored schema | `src/benchweave/registry/schemas.py` | schema-validation-before-use (inline-schema variant per `provider_settings.py:66`) |
| `load_dependency_policy` / `_parse_range` caret refusal | `src/benchweave/standards/manifest.py` | the `constraint_syntax_unexpanded:` posture, reused verbatim in meaning |
| `_version_tuple` | manifest.py:85 (renamed public) | the one version comparator |
| `_pinned_sdk_package_version` git-show pattern | check.py | **not used this slice** — the resolver is git-free; cited because §3.6's dev pins (slice 4) will need it |
| Refusal-prefix idiom `prefix: detail` | every check.py `_compare_*`; `StandardsError(f"…")` | all new prefixes |
| `_guidance` "migration guidance pending" | `src/benchweave/standards/matrix.py` | upgrade's note pointer until slice 5 |
| `_copy_standards(tmp_path)` fixture idiom | `tests/standards/test_dependency_policy.py` | the synthetic-root test strategy |
| Socket guard | `scripts/adc_conformance_control.py` `SOCKET_GUARD` (patches `socket.socket.connect/connect_ex`, `create_connection`, `getaddrinfo`, `gethostbyname`) | B5's in-process monkeypatched counter fixture (same five names) |
| High-water / lifecycle status vocabulary | `registry/admission.py::_gate_lifecycle`, `standards/registry/0.1.1/release-status.schema.json` | the semantic precedent yank/retired extend (design §3.1) — consumed, not changed |

## 3. Minimal first-slice scope and deferrals

**In scope:** `dependency.py` (intervals, caret, classification, resolution, minimal motion, `--locked`), the two inline schemas, DPS-150's `constraints.json`, the lock v2 writer + the one-time DPS-150 relock, `standards/cross-constraints.json` + loader + the one retrofit row + the root-scoped exemption extension in repin/test_baseline, the three CLI siblings, the `check` dependency lane, the docs/obligations/GOVERNANCE/CON-14-marker text edits (§4), and the test battery (§5).

**Deferred (each with carrier + reopen trigger, joining the design's D1/D5):**

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| D1 (design) | Network fetch for upgrades | `upgrade` resolves offline from served bytes; fetch rides #209 | first externally published standards artifact |
| D5 (design) | VR-40 "why" query | deterministic order makes it derivable; no surface | first confusion report / SDK docs request |
| D9 (new) | `pin` bootstrap for lock-less packages (provenance keys `repository/revision/directory`) | `plugin_lock_absent:` refusal naming manual bootstrap | first new plugin package needing a lock (esp32_controller, or slice 3 admission work) |
| D10 (new) | `policy_change_unruled:` (obligation 21 says it lands "with slice 2's agreement lane") | deferred — Fork F-B; the governor agent lane (mandatory for any `standards/` touch) carries the discipline meanwhile | owner ruling, or the mechanical PR-body-scan slice (needs CI PR-body reading, which no gateway workflow does today — verified: no workflow reads PR bodies) |
| D11 (new) | dev-head pin resolution + `opt_in` population (§3.6) | `dev_pin_unsupported:` clean refusal | slice 4 |
| D12 (new) | per-version migration-note pointers consumed by `upgrade` | "migration guidance pending" | slice 5 |

Explicitly **not** in scope: gateway per-pin admission and the census (slice 3), promotion records (slice 4), any corpus or manifest byte motion, any SDK-side change (the SDK lock/vendored tree are untouched; no submodule pointer moves).

## 4. Invariant, governance, and drift impacts

- **CON-14 (docs/internal/invariants.md:517-528):** the resolution clauses — pure function of committed bytes + authored constraints; canonical byte-identical locks; single-standard upgrade moves exactly one row; pre-releases never auto-select; retired identifiers never resolve; cross-standard rows committed side-table data — **become true this slice**. The dev clauses (content-addressed dev pins, wheel refusal) remain slice-4-future. The row's parenthetical gains one CON-12-style disclosure sentence naming which clauses turned true at slice 2 and that the dev clauses ride slice 4 — a text append, no rewrite.
- **Standards-bump hold window (2026-09-26 directive):** the mechanical tripwire `git diff origin/main...HEAD -- standards/` will be NON-empty (`standards/cross-constraints.json` is new). **Claim: this work is itself #203-related (#216 = "#203 slice 2 of 7") — the directive's express exemption.** Independently, it is not a standards *bump*: no corpus rows, no version directory, no manifest motion, no SDK bytes, no repin — governance data outside the corpus, the same class the owner already ruled non-bump for the slice-1 policy block (GOVERNANCE "Identity and homes"; G-3). The PR body states both; the governor lane reviews it as a `standards/` touch regardless.
- **GOVERNANCE:** one short append beside G-3 naming `standards/cross-constraints.json`'s home, its no-corpus-rows status, and that rows require citable evidence (coordinator-governed). No G-item rewrites.
- **Obligations (drift-and-obligations.md):** extend obligation 21 (or add a row) for the cross-constraints surface (file ↔ loader ↔ resolve-time + slice-3 admission enforcement points); obligation 4 fires (new CLI subcommands → the operator guide's CLI reference); obligation 3 fires (constraints authoring is plugin-visible → device-developer guide); obligation 18(g) already covers plugin contract locks — the v2 motion mechanism ("relock via `benchweave.standards pin` in the bump arc") should be updated in that row. Note: the obligations doc currently has **two rows numbered 19** (pre-existing); this slice's row placement must not deepen that — flagged for the maintainer.
- **Version-literal ratchet (obligation 20):** `count_version_literals.py` counts `src/benchweave/` only; Pattern B is *bare* `X.Y.Z` strings and Pattern A is `<id>/<X.Y.Z>` paths. `dependency.py` carries neither in executable code (ranges arrive from committed files; docstrings are excluded). Tests and `scripts/` are outside the counted tree. **Count stays ≤ 12 — verified against the definition, and the ratchet run is part of the gate battery anyway.**
- **Tier-3 (on-disk formats):** three — `contracts/constraints.json` (new authored), `contracts/lock.json` v2 (additive keys; v1 keys verbatim; pre-v2 consumer `fetch_contracts.py` keeps working — verified it reads only `revision`/`directory`/`sha256`), `standards/cross-constraints.json` (new governance). All versioned, all fail-closed loaders.
- **CI cost:** negligible — pure-function tests (seconds) inside `tests/standards/` (the `gates` job's existing `pytest -q`), the check lane's one extra comparison over one in-tree package. No new workflow lanes, no wheel changes.

## 5. Measurable proof — B1–B6 mapped to tests, fixtures, and RED commands

Test vehicle strategy: unit fixtures are **synthetic packages over a copied real standards tree** (`_copy_standards(tmp_path)` idiom + a synthetic `contracts/` dir) — this carries B2's plugin-ui control without authoring a fake DPS-150 dependency; the **real DPS-150** carries the integration arms. Test files: `tests/standards/test_dependency.py` (new), a `test_cross_constraints.py` section (loader + exemption integration incl. `repin_manifest` returning clean with the file present), extensions to `tests/standards/test_check.py` (the plant lane) and `tests/contract/test_dps150_lock.py` (a v2-row↔corpus-rows agreement test; the existing test passes **unchanged**).

- **B1 determinism** — resolve twice, `n=2`, byte-compare: `test_b1_*` on the synthetic package AND on real DPS-150 (via `pin` into a tmp copy of the package). KILL: any diff.
- **B2 minimal motion** — synthetic package with `{otdp: …, plugin-ui: ">=0.2.0,<0.3.0"}`: `upgrade otdp --precise <other-served>` (0.2.0↔0.2.2) leaves the plugin-ui row and every legacy non-otdp value byte-identical; control: `upgrade plugin-ui --precise 0.2.0` moves only that row. KILL: any collateral row motion. (DPS-150 at 0.2.2 pinning 0.2.2 is the natural no-op arm.)
- **B3 caret** — table-driven `expand_caret` tests incl. the 0.x boundary (`^0.2` ≠ `>=0.2.0,<1.0.0`) and `^0.0.3`; stored-caret refusals in constraints.json **and** lock.json; `--set otdp=^0.2` writes the expanded interval. **RED today:** the tests fail with `ModuleNotFoundError` (no `dependency.py`, no loader — nothing refuses a planted caret; the policy-block half is already green via `test_caret_syntax_in_a_stored_range_refuses`).
- **B4 retired vs unknown** — two fixtures: `--precise 0.3.0` → `retired_identifier:` with the five VR-37 fields and the 0.4.0 re-target hint; `--precise 9.9.9` → `version_unknown:` with the five fields. Assert the prefixes differ. **RED today:** the subcommand does not exist (argparse exit 2), and no gateway code distinguishes the classes (`retired_identifier:` exists only SDK-side).
- **B5 offline/drift** — (i) hand-edit a constraint interval in the tmp copy → `pin --locked` refuses `plugin_lock_drift:`; same plant surfaces in `check`'s new lane. (ii) remove a carried version's rows from the copied `corpus-manifest.json` with a constraint demanding it → named refusal (`constraint_unresolvable:`) with **zero** socket attempts — a pytest fixture monkeypatches the five `adc_conformance_control.py` guard names with a counter and asserts `count == 0`.
- **B6 raw-digest control (Q6 RED)** — `normalized_equal(path_a, path_b, own_version)` canonical-JSONs each subtree, replaces each subtree's OWN version string with a fixed placeholder, compares. Arms, on the real tree bytes: admits `otdp/0.2.1/otdp-device-descriptor.schema.json` ↔ `0.2.2` (verified: 4-line version-strings-only diff); a raw-sha256 comparator on the same pair FAILS (both asserted — the control pair proves the normalization is doing the work); normalized REFUSES `0.2.0` ↔ `0.2.2` (the `provider` element, verified live). KILL: the comparator admitting 0.2.0↔0.2.2.
- **RED-first ordering:** B3 and B4 land first (both RED-provable today), then B1/B2 (writer), B6 (comparator), B5 last (agreement lane). Every behavior test is committed RED and shown failing (collected count read from `--junitxml`, never a summary line; `no tests ran` = failed RED).

Gate commands: `UV_PROJECT_ENVIRONMENT=venv uv run pytest -q tests/standards tests/contract/test_dps150_lock.py`, bare `uv run mypy`, `uv run ruff check .`, `uv run python -m benchweave.standards check`, `make check-sdk-standards`.

## 6. Top risks and what falsifies this design

1. **The exemption-list extension is the one edit to proven refusal machinery** (repin + test_baseline). Falsifier: a behavior change for the two existing exemptions — excluded by the root-scoped tightening (both live at root), but the RED proof is `repin_manifest` + the baseline suite green on a tree carrying `cross-constraints.json` before/after.
2. **Lock reformat churn reads as content change in review.** Mitigation: values verbatim, `test_dps150_lock.py` unchanged, PR body names the one-time reformat. Falsifier: any legacy *value* diff.
3. **Prefix vocabulary drift with the SDK** (`version_not_served:` SDK-side folds unknown; the resolver splits `version_unknown:` out per B4). Documented in the module docstring; slice 3's gateway admission must adopt the same three-way split — flagged in the follow-on issue so gateway and SDK vocabularies converge deliberately.
4. **`policy_change_unruled:` deferral contradicts obligation 21's committed sentence** ("landing with slice 2's agreement lane"). Real obligations-doc amendment the owner blesses via the PR (Fork F-B); silently dropping it would be the worse failure.
5. **Cross-constraints retrofit rows are only as good as their evidence** — exactly one row is evidenced today; the file's honest-negative header guards against rows accreting without citations. Falsifier: a row whose evidence citation cannot be located.

## 7. Forks for the maintainer (defaults chosen, none blocking)

- **F-A — cross-constraints home.** CHOSEN: standalone `standards/cross-constraints.json` + the root-scoped exemption mechanism (design-named; keeps the manifest one-job-per-block; serves slice 4's promotion-records). Alternative: a `cross_constraints` top-level block inside `standards-manifest.json` (zero exemption edits, the exact `dependency_policy` precedent).
- **F-B — `policy_change_unruled:` scope.** CHOSEN: defer (D10) — the "existing check harness pattern" the design cites does not exist (no workflow reads PR bodies; verified), the issue body does not name it, and the governor lane covers the discipline; obligation 21's "landing with slice 2" sentence is amended in this PR (owner-blessed at merge). Alternative: build the minimal CI PR-body scan now.
- **F-C — `--locked` placement.** CHOSEN: a `pin` flag (cargo semantics) with `check`'s dependency lane running the same comparison unconditionally. Alternatives: check-only, or a separate `verify` sibling.
- **F-D — `pin` bootstrap.** CHOSEN: defer (D9). Alternative: derive provenance now (repository from pyproject URLs, revision from HEAD — deterministic per commit but adds git to a git-free resolver).

## 8. DISCLOSED UNVERIFIED

- **SDK source beyond the pin quote:** `packages/sdk` is deinitialized locally and its object store does not carry the pin (`0e6c4d7` unread); `served.py`'s refusal vocabulary (`retired_identifier:`/`version_not_served:`) was read from the **standalone SDK checkout** (`~/Documents/src/benchweave-sdk`), ahead-of/equal-to the pin unverified — the fold record's verbatim quotes corroborate. No slice-2 mechanism depends on SDK internals.
- **PR #201's prose itself** (the retrofit row's evidence) was not re-read; the row is carried as the design records it, and its `requires` values were verified consistent with the live tree.
- **CI wall-clock for the new tests** is an estimate ("negligible"); the gates lane reports the real figure at merge.
- The working tree carries pre-existing unrelated state (untracked `.claude/deep-review/2026-09-22-issue147-…md`, `.codex/`, and the `packages/sdk` modified marker from the deinitialized submodule) — untouched, disclosed for cleanliness only.

---

*Design by the increment-designer lane (MAX), 2026-09-27; owner-pass fork rulings by the controller. Acceptance rule B is pre-committed in `docs/implementation-planning/09-standards-dependency-design.md` §4 Slice 2 and is not weakened anywhere in this record.*

---

## Amendment — refute fold (2026-09-27)

Four M-class findings from the slice's refute lanes, folded RED-first. Acceptance rule B is unchanged.

(a) **§1.1's "highest SERVED version" is ordered by `version_tuple`, not list position or string max.** The record's own `max(served_versions)` phrasing specified the defect: `served_versions` returns a string-sorted tuple, so the first double-digit component (0.2.10) silently selected 0.2.2 at auto-selection and understated both move-to surfaces (the refusal field and the yank warning). Both sites now take `max(..., key=version_tuple)` (critic M1 / adv216a, independently reproduced twice). `served_versions`' own order is unchanged — the slice-1 render and tests consume it.

(b) **§1.3's "the 8-file map kept verbatim / provable via `test_dps150_lock.py` passing unchanged" is corrected.** The writer re-derives directory coverage: all 8 v1 digests are carried verbatim (machine-checked by `test_b1_dps150_pin_is_deterministic_with_values_verbatim`), and the map grew 8→12 repairing under-coverage that existed at the pinned revision itself (governor-verified via `git ls-tree` at `8a080d14`; the test file was extended, not unchanged). Fold F3 additionally tightens the derivation to an ALLOWLIST — corpus-rowed files ∪ the prior lock's map; any other file present in the version directory refuses with a named disposition (remove it, corpus-pin it, or extend the prior map deliberately). This is deliberately stricter than bare directory coverage: a legitimately NEW prose companion (no corpus row, absent from the prior map) refuses until the prior map is extended deliberately, instead of being silently adopted (A02: qualified, not assumed).

(c) **Named residual (adv216b L1):** a hand-edited `standards[].version` that stays inside its constraint interval is adopted by minimal motion and laundered green — accepted, because the constraints and the lock are the same party's authored data; the lane verifies agreement between them, not authorship.

(d) **Fold F2:** check's dependency lane surfaces resolution warnings (a package retained on a yanked pin) as `plugin_deprecation_warning:` lines that do not trip the exit-1 contract — otherwise an unattended surface stays CI-green on a deprecated pin forever.

(e) **Fold F4 (revision scissors):** the write path refuses when a digest VALUE in the derived map moves against the prior map at an UNCHANGED resolved version, unless `--revision <sha>` records the motion's revision alongside it; map additions carry the fetch-existence warning. The same-version gate is the fold's own scenario (a regenerated `validation-report.md` at a pinned version) made precise: under a version MOVE the map's shared names differ because they are different versions' corpus-frozen files, not because bytes moved at the recorded revision — refusing there would break every legitimate upgrade. The check lane does not apply the rule; committed locks are byte-compared as today.
