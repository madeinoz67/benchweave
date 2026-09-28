# Issue #221 — #203 Slice 7: The Zero-Literal End State (SM-2 = 0) and the Ratchet Flip — Design Record

**Status:** Design (builder-ready) · **Tracking issue:** madeinoz67/benchweave#221 (sub-issue of #203) ·
**Parent design:** `docs/implementation-planning/09-standards-dependency-design.md` §4 Slice 7, §3.7
(the arc record — its acceptance rule G is pre-committed there and is elaborated here, never rewritten) ·
**Evidence baseline:** gateway `main` at `6582651` (in sync with origin; slices 1–5 merged, slice 6 = #220
building on `feat/issue220-execution-pin` — NOT read past its committed design record; this design works
against main and is correct whether #220 lands before or after) · SDK pinned at gitlink `0e6c4d7`,
SDK `origin/main` at `445580d` (the pin is an ancestor of the tip; both measured — §0).

---

## 0. Premise verified — and four premises CORRECTED by measurement

1. **The gateway census: 12 sites, matching the committed baseline.**
   `scripts/standards/count_version_literals.py --json` at `6582651` reports count 12 = baseline 12.
   The per-site table is §1.4's input. Nothing silently appeared or vanished since slice 1.
2. **The SDK census in the arc record is stale in BOTH its numbers.** The arc says "17 SDK sites at
   `1b2cc74`" (PRD §1.5 hand count) and projects "the remaining ten — scaffold/presentation/fixtures —
   are slice 7". Re-measured with the counter's own committed definition (AST walk, Pattern A + BARE,
   docstrings excluded) at three refs: **22 sites at `1b2cc74`** (the hand count's 17 is superseded the
   same way the gateway's 13→12 was — script measurement is the authority, and the 17's missing five are
   unnameable from committed evidence, exactly the honest-partial posture of the 13-to-12 note in the
   script's docstring), **12 sites at the pin `0e6c4d7`, and the same 12 at SDK `origin/main` `445580d`.**
   The slice-1 retirements close the arithmetic: 22 − 10 (`validation.py` ×7, `__init__.py` ×1,
   `fixtures.py` ×2, all now derived from the lock) = 12 today. The honest SDK denominator for G1 is **12**,
   identical at the pin and the tip — the pointer bump lands whichever is tip at merge.
3. **The plugin-tree census is 3 sites under a scope the design must define.** Bare `rglob` over
   `plugins/` finds 19: 14 inside `plugins/fnirsi/dps150/venv/` (a stray environment — third-party bytes,
   never project code), 2 in dps150's test tree, 3 in
   `plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.py` (`otdp_version` "0.2.2",
   `descriptor_version` "0.2.0", adapter `version` "0.1.0"). The sims carry zero. The gateway counter
   scopes `src/` only (gateway tests are not counted; their literals are legitimate test data) — the
   plugin scope mirrors that posture: **every `*.py` under a `plugins/**/src/**` path**, ignoring any path
   carrying a `venv`/`.venv`/`node_modules`/`site-packages` component (defense in depth: a venv created
   inside `src/` makes zero-mode FAIL loudly, never silently pass). Denominator: **3**. The two test-tree
   sites and the 14 venv sites are named here precisely so the shrinking denominator cannot be silent
   (arc risk 7's class).
4. **`user_guide/` does not exist.** VR-24's Accept names `docs/`, `user_guide/` and plugin READMEs; the
   repo has no `user_guide/` today. The gate's source set is defined so the tree joins the set the day it
   appears (one constant), and this absence is recorded rather than papered over.
5. **The dev-head const fact that decides the coordinator literal.** During the entire execution
   `0.2.0-dev` head period, the dev corpus's `contract_version` consts held the ACTIVE version
   ("0.1.0" at the opening `4bfbf88` and still at the last content commit `53d700d`; `0608490` even pins
   head-opening const equality by test) — the promotion `54a59fa` is what swept them to "0.2.0". A dev
   composition's schema directory is named `0.3.0-dev` while its consts say the active version. This is
   why §1.2 derives the terminal record's version from the SCHEMA'S CONST and not from the corpus
   directory's name.
6. **The lock-version literal has already caused one sweep miss.** `registry/admission.py:342`
   (`"lock_version": "0.1.1"`) is governed by `standards/registry/0.1.1/package-lock.schema.json`'s
   `const "0.1.1"`, and commit `88b64f1` ("fix(registry): sweep miss — gateway lock emitter and test pins
   for 0.1.1") is the recorded instance of the hand sweep missing it. VR-21's *why* line ("hand sweeps
   miss sites") is this site's own history.

## 1. The mechanism, file by file

### 1.1 Gateway active-family derivation — one new loader, one new resolver

**`src/benchweave/standards/manifest.py` — `active_version_from_corpus(corpus, standard_id) -> str`.**
The fourth corpus-shaped twin in the family slice 1/#217 established
(`load_dependency_policy_from_corpus` :407, `retained_versions_from_corpus` :553,
`served_versions_from_corpus` :580, `declared_dev_head` :329): read
`<corpus>/standards-manifest.json`, check `manifest_version`, walk `standards[]` to the entry, return its
`version` after the SAME `ACTIVE_VERSION_PATTERN` guard `declared_dev_head` applies (:348). Refusals:
`standards_manifest_version_unsupported` and a new loud `standards_entry_absent: <id>` when no entry
matches (a countable-standards manifest always carries all six; absence is corruption, refused, never
defaulted — the loader family's posture). The identity block IS the active authority (CON-8); this twin
is the only missing read.

**`src/benchweave/vendoring.py` — `corpus_root() -> Path` and `active_contract_family(standard_id) -> Path`.**
`corpus_root()` = `_PACKAGED_ROOT/"contracts"` when it is a directory, else `_REPO_ROOT/"standards"` —
naming once the packaged-first root that `_otdp_corpus()` (documents.py:214) re-derives today as
`contract_family(_OTDP).parent`. `active_contract_family(sid)` =
`contract_family(f"{sid}/{active_version_from_corpus(corpus_root(), sid)}")`. Because
`hatch_build.py:_contracts_rows` maps `standards/` top-level files one-for-one, the manifest exists at
`_vendored/contracts/standards-manifest.json` in every wheel — the derivation works identically in the
repo checkout and the wheel (the `load_dependency_policy_from_corpus` precedent, which documents the same
two-layout contract). Import-time use is loud on corruption (`StandardsError` at import — degrade loudly;
the manifest is committed and packaged, and `contract_family` already does import-time I/O).

### 1.2 The nine gateway derivations and three register rows (disposition of all 12)

| # | Site (at `6582651`) | Today | Disposition |
|---|---|---|---|
| 1 | `control/documents.py:78` `_CONTRACTS = contract_family("execution/0.2.0")` | import-time module default | **DERIVE** — `active_contract_family("execution")` (#220 E4, assigned here; same value "0.2.0") |
| 2 | `control/coordinator.py:88` same shape | import-time module default | **DERIVE** — same call. A separate constant from documents.py's by address, identical by value; both derive independently (no cross-module ordering) |
| 3 | `control/coordinator.py:171` `"contract_version": "0.2.0"` in `build_terminal_record` | per-call record stamp, validated against the `contracts` param | **DERIVE from the validated schema's const** — see below. NOT a registered exception: coordinator.py is gateway-owned code, and the VR-25 register is for corpus-owned/authored-data files; exempting gateway code is the laundering SM-2 exists to prevent. NOT derived from `contracts.name`: §0.5's evidence — a dev composition's directory is `0.3.0-dev` while its schema consts hold the active version, so `.name` would stamp a label the schema refuses (a behavior regression in the devstage posture). The const derivation stamps exactly what the validating schema demands in every composition: identical behavior wherever today's record validates, and self-consistent by construction where today's literal could disagree with a swept schema (the A06 window closes mechanically). E1 keeps its lane unchanged: the #220 run guard stays the authority for WHEN a pinned-old lattice may run; E1 threads the run's own `execution_version` as an explicit parameter when it lifts the guard, replacing the derived default — recorded as E1's design constraint here so the record lane cannot silently re-widen |
| 4 | `interfaces/app.py:998` `FastAPI(version="0.1.0")` | app construction | **DERIVE** — `version=__version__` from `benchweave/__init__.py:6` (`importlib.metadata.version("benchweave")`, the proven in-tree mechanism; `pyproject.toml:7` is "0.1.0", so installed contexts are byte-identical; the `PackageNotFoundError` fallback "0.0.0+editable" fires only outside an installed environment — disclosed, not a regression) |
| 5 | `interfaces/mcp.py:52` `_VENDORED_PATH = contract_family("interface/0.1.0") / "mcp-tools.json"` | import-time | **DERIVE** — `active_contract_family("interface") / "mcp-tools.json"` |
| 6 | `interfaces/validation.py:37` `VENDORED_CORPUS_ROOT = contract_family("interface/0.1.0")` | import-time | **DERIVE** — `active_contract_family("interface")`; export beside it `VENDORED_INTERFACE_VERSION = VENDORED_CORPUS_ROOT.name` (the derived family dir's name IS the active version — one derivation site per family) |
| 7 | `interfaces/operations.py:326` `"interface_version": "0.1.0"` in `gateway_info` | per-call wire field | **DERIVE** — `VENDORED_INTERFACE_VERSION` (validation.py imports nothing from operations; no cycle). Moves with the interface bump exactly as the sweep moved it — one bump, one manifest edit, both surfaces together |
| 8 | `registry/schemas.py:22` `_CONTRACTS = contract_family("registry/0.1.1")` | import-time | **DERIVE** — `active_contract_family("registry")` |
| 9 | `registry/admission.py:342` `"lock_version": "0.1.1"` in `_lock_document` | per-call document stamp, validated by `load_lock_document` | **DERIVE from the lock schema's const** — a cached `lock_version()` in `registry/schemas.py` (which owns schema loading, `_load_schema_bytes`) reading `package-lock.schema.json`'s `properties.lock_version.const`; refuses loudly if the const is absent (a count that cannot be computed is a refusal). The emitter can then never disagree with the validator it is validated by — closing the `88b64f1` sweep-miss class mechanically |
| 10–12 | `presentation/contracts.py:20,247,358` | corpus-owned code (byte-identical to the SDK copy; identity pinned by `tests/sdk/test_presentation_packaging.py:70-75` against the lock's file map) | **REGISTER** — VR-25 branch 2: the exception is recorded with the D2 pointer (the policy block's plugin-ui note names the file and D2; the script's DECLARED_FILES comment cites VR-25/D2). The arc's alternative (derive the comparison via the policy block) is REJECTED on evidence: the file is one live object frozen at plugin-ui 0.2.0 bytes — deriving its comparison from a mutable policy block would make frozen code behave per a block it cannot re-derive against, a drift hazard VR-25 explicitly permits avoiding by recording the exception. D2's reopen trigger (first plugin-ui bump after the arc, or the owner's F1 call) is unchanged |

**The coordinator cache shape.** `_RUN_RECORD_VALIDATORS` (coordinator.py:89, populated by
`_record_validator` :135-144) becomes a cache of `(validator, contract_version_const)` per resolved
contracts directory — the const is read from the same schema bytes the validator is built from, once per
directory; `build_terminal_record` stamps the cached const. Recovery terminalization and every other
caller of `build_terminal_record` inherit (they thread `contracts`).

### 1.3 `scripts/standards/count_version_literals.py` — scopes, register, zero-mode, docs scope

The committed DEFINITION block is unchanged for executable code; the slice's editorial re-baseline (the
docstring's own rule: "changing it re-baselines by editorial decision, not silently" — this record is that
decision) adds:

- **Scopes.** `--scope {gateway,plugins,sdk,docs,all}` (default `all`). `gateway` = `src/benchweave/`
  (unchanged). `plugins` = every `*.py` under `plugins/**/src/**` with the environment-component ignores
  (§0.3). `sdk` = `packages/sdk/src/benchweave_sdk/` — an absent tree for a REQUESTED scope is a refusal
  (`sdk_tree_absent:` exit 1), never a silent skip (the primary checkout keeps the submodule deinitialized
  by convention; local runs use `--scope gateway,plugins,docs` — disclosed, and every CI lane that runs
  the default checks out `submodules: recursive`). Paths relativize per-scope (gateway/plugins to the repo
  root; sdk to `packages/sdk/`) so register rows are checkout-independent.
- **The register (declared data files) becomes the exemption list with teeth.** Each entry is
  `(path, reason, expected_sites)`. Zero-mode exempts registered files from the count but asserts each
  registered file's literal count EQUALS `expected_sites` — a new literal inside a registered file fails
  the gate until the register row is edited, which is a visible editorial diff. This is the ratchet
  discipline applied within the register; it is the register's anti-laundering defense (Risk 1).
  Register contents at the slice head:
  - gateway: `src/benchweave/presentation/contracts.py` — VR-25/D2 corpus-owned code — expects **3**;
  - sdk: `src/benchweave_sdk/standards/plugin-ui/contracts.py` — the byte-identical D2 twin — expects **3**;
  - sdk: `src/benchweave_sdk/scaffold.py` — authored example-template fields that are not standards
    references (`descriptor_version`, firmware, adapter `version`, provenance revision) — expects **4**;
  - plugins: `plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.py` — "a plugin's own pin
    declaration is data, not a literal" (VR-21's own sentence) plus its document-format and adapter
    declarations — expects **3**.
- **Zero-mode.** `BASELINE = 12` is retired; the script asserts, per requested scope, count-outside-register
  == 0 AND every register row's expectation holds. `--json` still prints every site, exempt rows marked
  `exempt: true` with the register reason — the display never hides what the gate forgives.
- **The docs scope (VR-24).** A prose scan over the VR-24 class set: `docs/*.md` at the repo root, the
  plugin READMEs, and `user_guide/**` if it appears — EXCLUDING, by named constants in the script (never
  silently): `docs/internal/`, `docs/implementation-planning/`, `docs/superpowers/` (internal and
  historical records whose frozen version citations are the point) and `docs/compatibility-matrix.md`
  (machine-rendered; CON-12's own gate owns it). Today's prose corpus is large (measured: 216
  three-component literals across the twelve root `docs/*.md`, 18 across the four plugin READMEs) and most
  of it is legitimate copy-never-move path citation — so the docs scope runs in **RATCHET mode against a
  committed machine-generated snapshot** (`scripts/standards/docs-literal-baseline.json`, regenerated only
  by an explicit `--refresh-docs-baseline` whose diff is the review surface): the gate refuses any literal
  NOT in the snapshot; removals only lower the count. This extends the proven mechanism (the counter's own
  slice-1 ratchet) rather than demanding the user-docs tree be re-authored; VR-24's letter demands a gate
  COVER the trees, and VR-24 carries no zero clause. The zero end-state for prose rides the
  render-from-the-lock work D4/18(m) already own (deferral table).

### 1.4 The literal-by-literal ledger (every site, every tree — none silently vanishes)

Gateway 12: nine derived (§1.2 rows 1–9), three registered (rows 10–12). SDK 12:
`presentation.py:515` preview fixture → **DERIVE** `served.active_version("plugin-ui-preview")`
(lock active 0.1.1 — identical value); `presentation.py:692,700,706` generated plugin-ui documents →
**DERIVE** `served.active_version("plugin-ui")` (0.2.0); `scaffold.py:530` example descriptor's
`otdp_version` → **DERIVE** `served.active_version("otdp")` — the exact call
`validation.py::_resolve_otdp_pin` already makes for an unpinned descriptor (validation.py:53): the
scaffold generates what the SDK validates today, and the SDK's state choosing a version is code, not an
author's declaration; `scaffold.py:531,540,547,581` → **REGISTER** (authored example content; the otdp
descriptor schema PATTERNs `descriptor_version` rather than const-ing it — verified — so nothing derives
them); `standards/plugin-ui/contracts.py:20,247,358` → **REGISTER** (D2 twin).
Plugins 3: all **REGISTER** (§1.3; a real plugin's declaration is authored data — deriving dps150's pin
from any served set would let gateway state rewrite the plugin's declaration).
Totals: **27 sites; 14 derived away; 13 registered (3 + 7 + 3); 0 outside registers at the slice head.**

### 1.5 The three CI lanes (G2's denominator) and the two-repo shape

- **Gateway lane (existing).** ci.yml's "Standards sync check" step runs `make check-sdk-standards`, whose
  counter line is UNCHANGED — the script's default now covers gateway+plugins+sdk+docs (submodules are
  recursive in that job, so the sdk scope resolves). Zero Makefile motion.
- **Plugin lane (D8, completing #233's row).** device-plugins.yml's `dps150-independent` job gains one
  step before isolation: `python3 scripts/standards/count_version_literals.py --scope plugins,docs`
  (the script is stdlib-only — `ast/json/re/argparse` — no environment needed; the checkout is present
  at job start; isolation of the plugin's own test run is untouched).
- **SDK lane (new, two-sided).** The SDK repo carries a twin counter
  (`scripts/count_version_literals.py`, definition copied verbatim, one scope: its own
  `src/benchweave_sdk/`, its own register rows from §1.3) and one ci.yml step
  `python3 scripts/count_version_literals.py` — so an SDK-only PR cannot add a literal between gateway
  pointer bumps. The gateway's sdk scope re-checks the same tree at every bump: the A6 two-sided posture
  (a plant in SDK src fails the SDK lane immediately and the gateway lane at the next pointer bump). A
  new drift-and-obligations row (obligation-19 shape) binds the two copies: a change to either counter's
  DEFINITION or register semantics re-syncs the other in the same work.

**Two-repo PR shape (AGENTS.md order; no SDK PRs are open today, so no stack):**
1. SDK PR (base main): five derivations (`presentation.py` ×4, `scaffold.py:530`), the twin counter +
   its register, the ci step, SDK tests. Commit → push → PR first.
2. Gateway PR (base main, links #221): the nine derivations, the two schema-const caches, the counter's
   scopes/register/zero-mode/docs scope + snapshot, the device-plugins step, the tests, the
   drift-and-obligations edits (obligation 18 closing clause + the counter-sync row + the CI map), and
   the submodule pointer to the SDK PR's head. CI checks the pointer out by SHA, so the gateway PR's
   gates run the SDK's post-derivation bytes; merge SDK first, then gateway (the pinned-SHA lineage
   rule). The work is complete only when BOTH merge.

### 1.6 Tests

Extend the proven pins in `tests/standards/test_dependency_policy.py` (the double-run and the
scratch-copy plant, :263-317) to the new shape, plus a new focused module:
`tests/standards/test_zero_literal_gate.py` — per-scope zero assertions with the register; the
register-tamper arm (a planted literal INSIDE a registered scratch file fails via `expected_sites`);
`active_version_from_corpus` unit arms (happy path over the real corpus; `standards_entry_absent` over a
fixture manifest; version-invalid refusal); the coordinator const derivation (record validates under the
active composition; the const equals the schema's, asserted against the vendored bytes); `lock_version()`
equals the schema const; the docs snapshot ratchet (a planted prose literal in a scratch docs tree fails;
a removal passes); reproducibility n=2 for every scope including docs. SDK-side: derivation parity arms
(scaffold descriptor validates; preview fixture validates; the generated plugin-ui documents validate —
each against the lock's active version), the twin's own plant arm. Existing suites are the no-regression
net: `tests/standards/`, `tests/control/` (documents/coordinator), `tests/unit/`, `tests/faults/`
(control/ + registry/ touched → faults lane per the CI map), `tests/sdk/` (the twin-identity pin at
`test_presentation_packaging.py:70-75` stays green untouched).

## 2. Precedents — each verified in current main

| Mechanism reused | Precedent, cited |
|---|---|
| Corpus-shaped manifest twin loaders | `manifest.py` `load_dependency_policy_from_corpus` :407, `declared_dev_head` :329, `retained_versions_from_corpus` :553 — the new loader is the fourth sibling, same walk, same guards |
| Packaged-first corpus root + manifest readable in both layouts | `vendoring.contract_family` :50-55; `hatch_build._contracts_rows` maps `standards/` top-level files one-for-one (manifest ships in wheels); `_otdp_corpus()` documents.py:214 names the root idiom |
| SDK derived constants from the lock | `served.py::active_version` (lock's exactly-one active row, packaged-first `_lock_document`); consumed by `validation.py:53` — the scaffold/preview derivations are the same call |
| Const-from-schema derivation (stamp what validates) | `_record_validator` coordinator.py:135-144 (schema bytes already loaded per directory); `registry/schemas.py::_load_schema_bytes`/`_make_validator`; the lock schema's `lock_version` const verified at `standards/registry/0.1.1/package-lock.schema.json` |
| Package version via importlib.metadata | `benchweave/__init__.py:3-8` |
| Ratchet with committed baseline + plant proof + double-run reproducibility | the counter itself (slice 1, A4) and `tests/standards/test_dependency_policy.py:263-317` |
| Docs hygiene pin (the pattern VR-24 extends) | `tests/contract/test_website_stamps.py` (class-11 source set, three-component refusal); obligation 18(d) `drift-and-obligations.md:188-194` |
| Two-repo twin copies synced by obligation | obligation 19 (shared skills, `drift-and-obligations.md:247+`) — the counter twin follows the same shape |
| Two-sided cross-repo gate | A6 (slice 1): a planted disagreement fails BOTH repos' CI |

## 3. Minimal first-increment scope and deferrals

**In scope:** the one manifest loader + the two vendoring helpers; the nine gateway derivations and two
schema-const caches; the counter's scopes/register/zero-mode/docs scope + committed snapshot; the SDK's
five derivations, twin counter, register, and ci step; the device-plugins lane step; the tests; the
drift-and-obligations edits (obligation 18 closing clause gains the enforcement pointer; the counter-sync
row; the CI-map row). No standards/ bytes move (derivations READ the manifests; the registers live in the
scripts); the SDK's vendored standards tree (`src/benchweave_sdk/standards/`) is untouched — its one code
file is registered, not edited, and the twin-identity pin stays green.

**Deferrals** (each with a home and a reopen trigger, per `.claude/deep-review/README.md`):

| # | Deferred | Home | Reopen trigger |
|---|---|---|---|
| Z1 | The src comment/docstring half of VR-24 (the Accept letter covers user docs; a comment gate over src would churn frozen historical docstrings — e.g. `registry/schemas.py`'s "vendored 1.0.0 schemas" module line, which is ambiguous prose naming the URN identity axis, deliberately untouched) | Documentation here + the slice PR's follow-on issue | The first review finding of a stale-comment defect class (a docstring naming a superseded version as current), or the owner's explicit call for the comment gate |
| Z2 | Zero-mode for prose (tokenizing/rendering the docs corpus from the lock) | Documentation here (obligation 18(m)'s in-arc sweep posture stands; D4 owns website) | The next bump of any standard a baseline line names (the existing 18(m) trigger), or the owner's call to render docs versions from the lock |
| Z3 | Plugin descriptor declarations as data files (moving dps150's descriptor dict to authored JSON the code reads — the stronger reading of VR-21's "data, not a literal") | Follow-on issue (the slice PR opens it) | The first contributor-lane plugin (#209's registry service standing up) or the owner's call for descriptors-as-data |
| Z4 | The wire-level plant probes (pushing the three plants through the real CI lanes on a probe branch, versus the command-identical local runs G2 mandates) | The slice PR body | The owner's call at review (both G2 evidence shapes are pre-accepted below) |
| Z5 | The coordinator const derivation under a mid-head swept dev corpus (unsupported state today — dev consts hold the active value by the `0608490` pin; if a future head pre-sweeps consts to the target, the derivation follows the schema where today's literal would refuse) | Documentation here | The next execution dev-head declaration |
| Z6 | D2 itself (plugin-ui corpus-owned code multi-serving) — unchanged | #233 row D2 | The first plugin-ui bump after this arc, or the owner's F1 call |

## 4. Invariant, governance, and drift impacts

- **Obligation 18 (drift-and-obligations.md:183-246):** the closing clause ("a new version-bearing literal
  anywhere is a defect — make it a derived surface or register it here with its motion mechanism") GAINS
  its enforcement pointer: the "here" is the counting script's register, whose entries carry reason and
  `expected_sites` (an append to the clause's text, evidence line `issue #221`). Rows (e)/(g)/(m) gain the
  note that their surfaces are now inside a gated tree where applicable.
- **D8 (#233):** completed — the plugin lane lands here; the row's disposition is recorded in the slice PR
  (the issue stays open for its other rows).
- **invariants.md:** NO new CON row, NO amendment — the derivations are CON-9's domain extended (the arc's
  §5 "unamended" list already holds CON-9 untouched), VR-22's zero-mode transition is written into VR-22's
  own text ("until SM-2 reaches 0, the gate MAY run in ratchet mode"), and CON-1's per-pin admission is
  untouched (every derivation is of the ACTIVE/composition family; per-pin resolution keeps its own
  machinery). CON-2/CON-4/CON-8/CON-10/CON-12/CON-14: untouched (no served-set, manifest, projection,
  matrix, or resolver change). One honest note: `docs/internal/drift-and-obligations.md` rows (h)/(i) name
  versioned live-authority pointers (`standards/interface/0.1.0/…`) — those are PROSE pointers in that doc,
  inside the docs scope's excluded internal set; their motion stays the in-arc sweep those rows already
  record.
- **GOVERNANCE:** no G-item; no policy-block, yank, retirement, or promotion-record change.
- **Standards bytes: none move.** The design reads `standards/standards-manifest.json` (identity block)
  and the two schemas whose consts are derived; it writes nothing under `standards/` in either repo
  (the #203-related hold-window exemption is not even needed; the tripwire
  `git diff origin/main...HEAD -- standards/` stays empty). No new manifest field is required — if a future
  derivation wants one, that is a governance question and a fork, not this slice.
- **Surfaces that move:** `standards/manifest.py`, `vendoring.py`, `control/{documents,coordinator}.py`,
  `interfaces/{app,mcp,validation,operations}.py`, `registry/{schemas,admission}.py` (all Tier-3 paths per
  the rubric — documents.py and registry loading are explicit Tier-3 rules), `scripts/standards/` (+ the
  committed docs snapshot), `.github/workflows/device-plugins.yml`, the SDK repo's
  `src/benchweave_sdk/{presentation,scaffold}.py` + `scripts/` + `.github/workflows/ci.yml`, both test
  trees, `docs/internal/drift-and-obligations.md`. MCP tools / REST / openapi / CLI: no wire change (the
  one wire-adjacent field, `gateway_info`'s `interface_version`, emits the same bytes today and moves only
  at an interface bump, exactly as the sweep moved it). Operator docs: the counter's docstring + this
  record. **CI cost:** negligible — one stdlib-only sub-second step in each of two existing lanes; no new
  lanes; a handful of focused tests.

**Tier call (Step-1 rules + the #254 design-time keyword scan, run on the planned diff shape):**
**Tier 3.** Path rules fire first: the diff touches `src/benchweave/control/documents.py` (an explicit
Tier-3 rule) and `src/benchweave/registry/` loading (`schemas.py` is registry loading). The keyword scan
over the expected diff text: `recovery` PRESENT (coordinator/recovery-terminalization prose in tests and
comments), `sha256` PRESENT (the register-reason prose and the twin-identity assertions cite digests),
`hashlib` likely present in the byte-identity test if re-asserted; `threading`/`asyncio`/`subprocess`/
`migrate`/`protection` absent from new code. First-match-wins ⇒ Tier 3 regardless of order; the mandatory
second adversarial lane applies (standing two-lane rule).
**Standards-governor: FIRES by the letter.** The mandate (review-rubric.md:56-58, quoted):
"any diff touching `standards/` (corpus, prose, or either manifest), plugin contract locks, the SDK
vendored tree, or standard-version strings dispatches the `standards-governor` agent as a mandatory
pre-merge pass — the same standing as the Tier-3 refute." This slice touches none of the first three
(standards/ untouched; no plugin contract lock; the SDK's vendored standards tree untouched) — but the
diff's entire subject is **standard-version strings** (removing/deriving them), which the fourth clause
names squarely. Dispatch the governor; a governance review that never ran is a skipped gate.

## 5. Measurable proof — acceptance rule G (pre-committed in the arc record) elaborated

The arc record's G1/G2/G3 and KILL are quoted verbatim and elaborated with named arms; nothing is rewritten.

> **G1** — "the committed script reports 0 executable literals outside the declared data files across
> gateway src/, SDK src/, and in-tree plugins (denominator: the three trees; baseline 13 + 17 +
> plugin-count, plugin count re-measured at slice 1)." **G2** — "a planted literal in each tree fails CI
> (three plants, three red lanes)." **G3** — "corpus-owned code (presentation/contracts.py) either follows
> VR-21 or carries its registered exception with the D2 pointer (VR-25)." **KILL:** "any plant passing;
> any count not reproducible twice."

- **G1a (the census, committed before the mechanism lands).** The honest re-measured baselines with
  denominators, committed in this record and re-asserted at the slice head: gateway 12 (of 12), SDK 12 at
  pin `0e6c4d7` AND at `origin/main` `445580d` (the arc's 17-at-`1b2cc74` hand count superseded by the
  script's 22-at-`1b2cc74`; slice 1 retired 10; both today-refs measured twice), plugins 3 under the
  §1.3 scope (out-of-scope named: 2 test sites, 14 venv sites). SHIP: at the slice head, per scope,
  count-outside-register == 0; the registers enumerate exactly 13 exempt sites (3 gateway + 7 SDK +
  3 plugins) with reasons and expectations; `--json` reproducible twice byte-identical per scope.
  KILL: any scope > 0 outside the registers (a derivation missed a site — the site table §1.4 is the
  checklist); any two consecutive runs differing (the A4 discipline — fix the script before trusting it).
- **G2a (the three plants).** Gateway: a bare literal planted in a non-registered gateway file (e.g.
  `src/benchweave/interfaces/operations.py` gains `_PLANT = "9.9.9"`) fails `make check-sdk-standards`
  in ci.yml. SDK: `src/benchweave_sdk/packaging.py` gains `_PLANT = "9.9.9"` — fails the SDK lane.
  Plugins: `plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/adapter.py` gains `_PLANT = "9.9.9"` —
  fails the device-plugins step. Evidence shape (pre-committed, both accepted): command-identical local
  runs of each lane's exact command against the planted trees (mandatory), and, at the owner's option (Z4),
  probe branches pushed through the real lanes. KILL: any plant passing its lane.
- **G2b (the register-tamper arm — elaboration, additive).** A literal planted INSIDE a registered file
  (e.g. `scaffold.py` in the SDK scratch tree) fails via the `expected_sites` assertion — the register
  cannot become a laundering list without a visible register edit. KILL: the plant passing with the
  register unchanged.
- **G3a.** Both `contracts.py` copies carry registered exceptions citing VR-25 + D2; the policy block's
  plugin-ui note names the file (verified present in `dependency_policy.standards["plugin-ui"].note`);
  the byte-identity of the two copies stays pinned by the existing
  `tests/sdk/test_presentation_packaging.py:70-75` digest assertion (cited, not re-built); the register
  expectation is exactly 3 per copy, so a fourth site in either copy fails until D2's trigger is honestly
  met. SHIP: all four facts asserted by test. KILL: either copy accepting a new literal without a register
  edit.

Underpowered-measurement rule (pre-committed): every arm is a deterministic single-cell check; if a RED
arm cannot be reproduced at the merge base (a plant that already passes; a scope that already reads 0),
the fixture or scope definition is wrong, not the mechanism — stop and re-baseline the fixture before
building. No statistical arms exist; the only n>1 requirement is the reproducibility double-run (n=2,
byte-identical), which G1's KILL already governs.

## 6. Top risks — and what an adversary attacks first

1. **The register as a laundering list.** A future PR adds its file to the register to dodge derivation —
   SM-2's headline becomes a bookkeeping lie. MITIGATION: register rows carry reason AND `expected_sites`
   (a new literal in a registered file fails until the row is edited — a visible editorial diff); the
   obligation 18 closing clause names the register as THE sanctioned home, making off-register additions
   a review-visible defect. FALSIFIER: G2b's plant passing with the register unchanged.
2. **Definition drift between the two counter copies.** The gateway and SDK counters could diverge in
   definition, each honestly gating a different language. MITIGATION: the twin's definition is copied
   verbatim; the new obligation row (obligation-19 shape) binds re-sync into the same work; the two-sided
   plant coverage. FALSIFIER: a plant passing one side and failing the other on the same tree state.
3. **Import-time derivation adds a failure mode.** A corrupt or absent manifest turns an import into a
   `StandardsError` where the literal never failed. MITIGATION: this is the designed loud-degradation
   posture (a count/refusal that cannot be computed is never a guess); the manifest is committed and
   wheel-packaged, and a test pins the refusal prefix. FALSIFIER: none that should pass — a test asserting
   silent fallback anywhere in the derivation chain would be the defect.
4. **The scope definitions quietly shrinking** (arc risk 7). Excluding the venv, the plugin test tree, or
   the internal docs could hide future literals. MITIGATION: every exclusion is a named constant with its
   reason in the script and in this record; the denominators are committed (G1a); a test pins the
   class-set file census (the count of scanned files per scope) so silent shrinkage fails.
   FALSIFIER: removing an exclusion without the census test failing.
5. **The dev-composition edge on the coordinator derivation** (§3 Z5). MITIGATION: the dev corpus const
   discipline is pinned by the `0608490`-era test and the promotion-sweep design; the derivation follows
   the schema's own demand wherever it goes. FALSIFIER: none constructible today (no head declared);
   reopen at the next head declaration.
6. **Stale display after derivation.** `gateway_info`'s `interface_version` and the scaffold's pin now
   move with the manifest; a bump that forgets nothing still changes wire/scaffold output silently.
   MITIGATION: that IS the motion mechanism working (one manifest edit moves every surface together —
   the entire point of VR-21); the bump arc's existing tests (interface conformance, SDK suite) catch a
   disagreeing consumer. FALSIFIER: a bump where a derived surface disagrees with the schema family it
   was derived from (should be impossible — one source).

## 7. Forks for the maintainer

- **Fork 1 — the docs gate's mode.** Recommended (designed): ratchet against a committed snapshot — the
  corpus is ~234 legitimate citations today; a zero-mode prose gate would demand re-authoring the user
  docs mid-arc. Alternative: zero-mode over a narrowed claim-position pattern (fragile text-matching), or
  tokenizing docs now (D4-adjacent scope creep). VR-24's letter is satisfied by the ratchet; the zero
  end-state stays D4/18(m)'s lane.
- **Fork 2 — the plant evidence depth (Z4).** Command-identical local runs are pre-accepted; wire-level
  probe branches through the three real lanes are available on the owner's call (one extra probe push per
  lane, ~minutes of CI).
- **Fork 3 — the SDK twin versus gateway-side-only enforcement.** Recommended: the twin (immediate
  enforcement on SDK-only PRs; two-sided A6 posture). Alternative: gateway-side-only (one script, no
  copy — but SDK-only PRs gate nothing until a pointer bump, and the SDK repo's own CI loses the lane
  G2 names). The arc's G2 ("three red lanes") reads as requiring the twin; flagged because it is the one
  place this design adds a repo file that duplicates another.

## 8. DISCLOSED UNVERIFIED

- **The exact docs snapshot contents.** The 216+18 figure is a `grep -c` survey; the committed snapshot's
  per-file rows are generated at build time by the script itself (reproducibility governed by G1a's
  double-run). If generation proves noisy across line endings or path order, the builder fixes the
  generator before trusting the snapshot — the underpowered rule applies.
- **`importlib.metadata` in every lane.** The `__version__` derivation is asserted in the normal installed
  contexts (uv sync in CI, the wheel); the `PackageNotFoundError` fallback path is disclosed but not
  exercised by a test (a bare-checkout-without-install context the repo does not use).
- **SDK tip motion.** The SDK's `origin/main` (`445580d`) was measured at design time; if it advances
  before the slice lands, the SDK PR re-measures at its own merge base — the 12-at-both-refs claim is
  re-asserted there (the per-site table is the checklist).
- **The device-plugins lane's checkout shape.** The new step reads the repo checkout before isolation;
  if that job's future shape removes the checkout (full isolation), the step moves to a job that keeps it
  — the lane's ownership of the plugins+docs scopes is the invariant, not the step's address.

---

*Design record for issue #221 (#203 slice 7 of 7). No standards bytes move in either repository. The arc
record's §3.7 site list and both stale SDK counts are corrected by script measurement in §0; the
pre-committed acceptance rule G is elaborated, never rewritten; deferral table §3 follows the
`.claude/deep-review/README.md` contract. SM-2's zero is 27 sites = 14 derivations + 13 registered
exemptions, every one accounted for in §1.4.*
