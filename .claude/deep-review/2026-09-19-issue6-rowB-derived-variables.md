# Issue #6 Row B — Declarative derived variables in the measurement model

**Date:** 2026-09-19
**Status:** Design (pre-implementation). Row B of issue #6, descriptor-authored form, per the
maintainer's fork recommendation. Rows A (settings-as-presets) and C (display hints) are
designed separately; D (runtime switching) is deferred by the issue.
**Repo state verified against:** `main` at `8bc83a5` (2026-09-19). The issue's "verified
current state" section cites the pre-reset `contracts/` OTDP 0.3.0 layout (checked
2026-09-14); every claim below was re-verified against the post-reset corpus
(`standards/otdp/0.1.1`, the byte-errata of the 2026-09-16 0.1.0 reset).

---

## 0. Premise verification (what the code actually says)

| Premise from the issue | Verified | Evidence |
|---|---|---|
| `otdp-measurement` variables require `id, quantity, unit, channel_ids, dtype, dimensions, uncertainty, calibration, status` | yes | `standards/otdp/0.1.1/otdp-measurement.schema.json:296-307` |
| Zero derived/computed/expression/virtual concepts in the schemas | yes | grep over both 0.1.1 schemas and 0.1.0 copies |
| Imperative adapter-side derivation is expressible today | yes | sim PSU `measure` invoke returns a full dataset; `tests/contract/test_sim_plugins.py:453-488` validates it against the vendored measurement schema |
| A variable is closed to new fields | yes | `$defs.variable` has `additionalProperties: false` (`otdp-measurement.schema.json:307`) — Row B is a schema bump, not an extension-key patch |
| The OTDP bump precedent exists | yes | otdp 0.1.1 is a PATCH errata of 0.1.0; `standards/corpus-manifest.json` row `otdp/0.1.1/otdp-measurement.schema.json` cites `source: standards/otdp/0.1.0/otdp-measurement.schema.json` — copy, never move, already practised |

Facts the issue could not have stated because they are only visible in the code:

1. **Datasets enter the gateway only as invoke action results.** The plugin ABI carries them
   (`host/plugin.py:45` `dispatch`); the executor's `_step_invoke` sends the request
   (`control/executor.py:795-827`) and `select_sample` consumes `data.result` as a dataset
   (`executor.py:444-532`). The OTDP bridge supports only identify/read/write today
   (`host/otdp_bridge.py:180-183`) — "Dataset, profile and stream semantics need a native
   async host" (`otdp_bridge.py:3-4`).
2. **There are two device-descriptor shapes, not one.** The full OTDP descriptor
   (`otdp_version`, channels, parameters-as-objects; e.g.
   `plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.json`) is plugin-package
   content, validated by the SDK check lane (`packages/sdk/src/benchweave_sdk/validation.py:138`)
   and pinned per-plugin. The execution-side descriptor that the bench digest-pins and the
   executor consults is a **slim projection** — `id, version, profiles, actions[{action_id,
   issued}], parameters` as a string list (`control/documents.py:111-131`; live example
   `plugins/benchweave/sim_psu/src/benchweave_sim_psu/descriptor.json`). Control admission
   applies a code-level structural check to it, deliberately not a vendored schema
   (`documents.py` module docstring). An OTDP-shaped descriptor would fail
   `_require_string_list(descriptor, "parameters")`.
3. **No in-tree expression evaluator exists.** The nearest machinery is
   `control/policy.py` (constraint evaluation; conservative uncertainty-aware product
   bounds at `policy.py:20-24`), `control/semantics.py` (admission-time reference-graph
   validation: uniqueness, lexical scoping, no forward/self reference), and
   `executor.py resolve_value` (RFC 6901 pointers). Row B extends these patterns; it does
   not reuse a parser because none exists.
4. **The profile catalog does not pin dataset variable names.**
   `device-profile-catalog.json` action `otdp.dc_psu.measure/1.0.0` `output_schema` is a
   bare `$ref` to `urn:otdp:measurement:0.1.1#/$defs/dataset`. Variable ids are convention,
   not contract — which shapes the operand-resolution design below.
5. **Channels carry multiple quantities.** `standards/otdp/0.1.1/examples/class-dc_psu.json`
   channel `ch1` declares quantities `["voltage","current","power"]`; in
   `examples/measurement-vectors.json` the dc_psu dataset has three variables all sourced
   from `ch1`. A "channel reference" is therefore not a value reference — see §2.2.

**Verdict: BUILD.** The gap is real (the schema is closed; nothing declarative exists), the
grammar is a finite token set safely checked by a hand-written parser (no `eval`, no
`ast.parse` on descriptor text), and there is a runtime consumer today (the executor
invoke seam) so the mechanism is not vocabulary without behavior.

---

## 1. Mechanism overview

A plugin author declares, in the device descriptor, that measurement datasets from this
device include variables computed from other variables by a fixed-grammar arithmetic
expression. Two carriers, one grammar, one validator:

- **Authoring home (canonical):** the OTDP device descriptor, new optional top-level
  `derived_variables[]` array — OTDP 0.1.1 → **0.1.2** (additive PATCH per
  `standards/GOVERNANCE.md` change-class table).
- **Execution carrier:** the slim execution-side device descriptor (the one the bench
  digest-pins and the executor holds via `AdmittedDocuments.descriptors`) gains the same
  optional array, verbatim. This is the only descriptor the gateway evaluates from today,
  and the only one control admission sees — so this is where "validated at admission"
  is enforced in the gateway.
- **Dataset provenance:** `otdp-measurement` 0.1.2 variables gain an optional closed
  `derivation` marker recording the expression and operand ids, so a recorded dataset is
  self-contained for replay.
- **One shared pure module** (`benchweave.measurement.derivation`) parses/validates and
  evaluates; the gateway calls it at control admission (grammar/static checks) and at the
  executor invoke seam (evaluation); the SDK check lane re-implements the grammar/static
  subset offline and is pinned to the gateway by a shared, corpus-vendored vector census
  (the established two-repo pattern, REG-4 discipline).

### 1.1 Why the execution-side carrier exists at all

The alternative — OTDP-descriptor-only — has no consumer in increment 1: the gateway never
reads the full OTDP descriptor at run time (fact 2), and the bridge does not carry invoke
(fact 1). A mechanism nothing invokes would make the acceptance criteria vacuous (see the
RED checks in §7). The cost of the second carrier is bounded: the array shape, the grammar
and the validator are identical by construction, and both are digest-pinned in their own
lattices. The un-built projection-agreement check between the two carriers is a named
deferral (§5).

---

## 2. The contract changes (OTDP 0.1.2)

### 2.1 Descriptor schema — `derived_variables[]`

New optional top-level property in `standards/otdp/0.1.2/otdp-device-descriptor.schema.json`
(copied from 0.1.1; `$id`/`title`/`otdp_version` const bumped to 0.1.2):

```json
"derived_variables": {
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "id":         {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
      "quantity":   {"type": "string", "minLength": 1},
      "unit":       {"type": "string", "minLength": 1},
      "expression": {"type": "string", "minLength": 1, "maxLength": 256,
                     "pattern": "^[0-9a-z_+\\-*/(). ]*$"}
    },
    "required": ["id", "quantity", "unit", "expression"],
    "additionalProperties": false
  },
  "uniqueItems": true,
  "minItems": 0
}
```

Notes, claim-disciplined:

- The `pattern` bounds the **character surface only**. It cannot express the grammar
  (balanced parentheses, token formation); the grammar is prose + code + vectors (§2.3).
  The schema says so in a `description`.
- No `uncertainty`, `calibration`, `dtype`, `dimensions`, `channel_ids`, `status` here:
  those are either structurally pinned by the evaluator (§4) or computed at evaluation.
  An author cannot declare an uncertainty for a computed value — see §4.4.
- `maxLength: 256` bounds parse cost and evidence verbosity; the parser additionally caps
  parenthesis nesting at 32 (§4.2).

The same array, byte-for-byte the same shape, is legal in the execution-side descriptor.
That descriptor has no schema (code-checked), so the carrier costs no contract change —
only the `_check_descriptor` extension in §3.1.

### 2.2 Expression operands are variable ids, not channel ids

The issue's parenthetical says "channel refs", following the motivating external plugin
where one channel is one scalar stream. In OTDP a channel is a *source* that may carry
several quantities (fact 5): `(ch1 - ch2)` names no quantity and cannot be evaluated or
unit-checked. The well-typed reference target is the **dataset variable id**:

- variables are the things that carry values, units, dtypes and dimensions;
- M01 already guarantees variable-id uniqueness within a dataset;
- `select_sample` already addresses dataset contents by `variable_id` + `unit`
  (`executor.py:458-459`) — a derived variable becomes samplable by exactly the existing
  mechanism, no new procedure vocabulary;
- the derived variable's required `channel_ids` metadata is recovered honestly as the
  union of operand variables' `channel_ids` (provenance by construction — impossible with
  bare channel refs on multi-quantity channels).

This is a deliberate, disclosed deviation from the issue's wording, taken because the
issue's own acceptance criteria ("derived variables carry full variable metadata") are
only satisfiable with variable-typed operands. The motivating expression
`(a0 - a1) / .1` is representable verbatim with variable ids `a0`, `a1`.

### 2.3 Grammar

```
expression := term (("+" | "-") term)*
term       := factor (("*" | "/") factor)*
factor     := ("+" | "-") factor | atom
atom       := number | identifier | "(" expression ")"
number     := digits ["." digits] | "." digits        ; finite decimal, no exponent
digits     := [0-9]+
identifier := [a-z][a-z0-9_]*                          ; dataset variable id
```

- Tokens: exactly `+ - * / ( ) <number> <identifier>` and space (space is whitespace, not
  a token). Nothing else: no functions, no `**`, no `%`, no commas, no strings, no
  assignment, no exponent notation (`1e3` is a syntax error — exponent literals invite
  platform parse ambiguity and buy nothing over `1000`).
- Precedence and associativity: standard (`*//` bind tighter than `+/-`; left-associative;
  unary minus/plus bind tighter than binary operators). One answer, no ambiguity.
- The evaluator is a **hand-written tokenizer + recursive-descent parser + evaluator over
  the resulting AST**. `eval`, `compile`, `ast.parse` and any string-to-code path are
  structurally absent — this is the sandbox. The token set is finite, identifiers match
  the variable-id grammar, and numbers are `decimal`-parsed then converted once to
  binary64, so a literal's value is fixed by its digits.

**Where the grammar lives, and why:**

| Artifact | Carries | Pinned how |
|---|---|---|
| `standards/otdp/0.1.2/measurement-model.md` new §8 | EBNF, evaluation order, failure/null semantics, unit/dtype/shape rules (the M15 prose) | versioned prose (not digest-pinned — same as M01–M14 today) |
| `standards/otdp/0.1.2/otdp-specification.md` §3 + §10 | the descriptor-side declaration and a new row **S19** in the mandatory-semantic-checks table | versioned prose |
| `standards/otdp/0.1.2/examples/derivation-vectors.json` (new, normative) | the machine census: accept/reject grammar vectors + evaluation vectors with expected outputs | digest-pinned corpus row (like `class-action-vectors.json`) |
| the schemas | character surface + length only | digest-pinned |

Rationale: JSON Schema cannot express a grammar; every existing semantic rule of this
corpus (M01–M14, S01–S18, procedure lexical scoping) lives in versioned prose enforced by
code; the vectors file gives the grammar machine teeth and pins the two implementations to
each other. Putting an EBNF "appendix" inside the schema JSON would be unreadable and
still unenforceable — prose + census is the established, stronger split.

### 2.4 Measurement schema — the `derivation` marker

In `standards/otdp/0.1.2/otdp-measurement.schema.json` (copied from 0.1.1, `$id`/`title`
bumped), `$defs.variable` gains:

```json
"derivation": {
  "type": "object",
  "properties": {
    "kind":        {"const": "expression"},
    "expression":  {"type": "string", "minLength": 1, "maxLength": 256,
                    "pattern": "^[0-9a-z_+\\-*/(). ]*$"},
    "operand_ids": {"type": "array", "minItems": 1, "uniqueItems": true,
                    "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"}}
  },
  "required": ["kind", "expression", "operand_ids"],
  "additionalProperties": false
}
```

- `operand_ids` is the parsed projection of `expression`'s identifiers. It is required so
  the dependency graph is machine-readable without a parser, and so a forged record is
  detectable: the evaluator refuses a marker whose `operand_ids` disagree with the parsed
  expression (a liar-check, not a trust decision).
- New `allOf` on `variable`: `derivation` present ⇒ `values` present and `artifact`
  absent (derived variables are inline in increment 1).
- The marker is **provenance, not authority**: it records how values were produced. An
  adapter may truthfully emit it for a code-computed variable (the imperative path is
  unchanged); nothing grants it by existence. Whether the value was computed by the
  gateway is verifiable by re-evaluation, which is the point.

### 2.5 Corpus examples

- `examples/measurement-vectors.json` (0.1.2 copy): one dataset gains one gateway-derived
  variable with the marker — the canonical shape in situ.
- `examples/derivation-vectors.json` (new): §7's census, consumed by both repos' tests.

---

## 3. Admission enforcement

Three seams, one validator (`check_derived_variables`, §4.1):

1. **Gateway control admission** — `control/documents.py _check_descriptor` gains: if the
   descriptor carries `derived_variables`, run the grammar + static checks. Rejections
   raise `AdmissionRejected` with prefix `schema: descriptor[<device_id>] derivation:`
   followed by the machine reason (`derivation_grammar:`, `derivation_duplicate_id:`,
   `derivation_self_reference:`, `derivation_cycle:`, `derivation_bad_operand_unit:` …).
   This is the enforcement point the issue's "validated at admission" names for the
   gateway: a malformed expression cannot reach a run.
2. **SDK authoring admission** — `packages/sdk/src/benchweave_sdk/validation.py
   validate_descriptor` gains **S19**: schema shape + the same grammar/static subset
   (re-implemented offline; the repo is self-contained by PKG-1 and cannot import the
   gateway). Agreement with the gateway is pinned by the shared vectors file (vendored
   with the corpus) and tested main-side in `tests/sdk/`.
3. **Corpus architecture validator** — `scripts/architecture/check_devices.py` validates
   the 0.1.2 corpus examples' derived declarations (GOVERNANCE gate 3). It pins its own
   light-weight grammar check or imports the gateway module (it already runs in the repo;
   importing `benchweave.measurement.derivation` is the non-duplicating choice).

Static checks performed at all three seams (the semantics.py pattern applied to a new
graph):

- identifiers parse; the expression is non-empty, within length, nesting ≤ 32;
- derived ids are unique within the array and match the variable-id grammar;
- no derived id appears in its own expression (self-reference);
- the operand dependency graph over derived variables is acyclic — a derived variable may
  reference an earlier-declared derived variable (declaration order is the evaluation
  order, which is what makes evaluation deterministic), never a later or cyclic one;
- `+`/`-` unit consistency that is *statically knowable* is checked at evaluation (§4.3),
  not admission, because operand units live in datasets, not descriptors (fact 4). The
  admission guard states this residual in its docstring.

---

## 4. Evaluation

### 4.1 The module

New pure package `src/benchweave/measurement/` with `derivation.py`:

- `check_derived_variables(derived: list[dict[str, Any]]) -> None`
  grammar + static checks; raises `DerivationRejected` with `derivation_:`-prefixed,
  machine-matchable reasons (the repo's prefix discipline — STD-4's main-side twin).
- `derive_dataset_variables(dataset: dict[str, Any], derived: list[dict[str, Any]])
  -> dict[str, Any]`
  pure: returns a **new** dataset dict (copied variable list, derived variables appended);
  never mutates the plugin-returned object (pinned by test, §7); no I/O, no clock, no
  plugins — caller-supplied inputs only (the STO-1 purity discipline applied to a control
  path).

### 4.2 Determinism

- Derivation order is declaration order; each expression's operands resolve only against
  the dataset's original variables plus previously derived ones — the admission DAG check
  makes this a total order.
- Arithmetic is IEEE-754 binary64 (`float`), one evaluation order (the grammar's), no
  fused operations, no summation tricks. CPython `float` is C `double`; the operation
  sequence is fixed by the AST, so the result is a function of the operand values alone.
- Numeric literals are parsed once, decimal-string → binary64, at parse time; the same
  literal text always yields the same value.
- Replay rule (measurement-model.md §8, normative text): re-evaluating the recorded
  expression over the recorded operand values reproduces the derived values exactly. The
  `derivation` marker in the recorded dataset carries the expression; the schema URN
  (`urn:otdp:measurement:0.1.2`) pins the grammar version; the vectors file pins
  cross-implementation agreement.

### 4.3 Runtime compatibility checks (loud, per variable)

For each derived variable, at evaluation:

- every operand id resolves to a variable **in the dataset under derivation** (original or
  previously derived). Unresolved operand ⇒ the derived variable is emitted with
  `status: "invalid"`, `status_reason` naming the missing operand, and `values` of a
  single `null` is **not** fabricated — see below;
- all operands have `dtype: "float64"`, inline `values`, finite elements (nulls allowed,
  M04/M05 semantics), and identical `dimensions` lists (exact equality; no broadcasting);
- `+`/`-` nodes compare units **between identifier-leaf operand pairs only** (machine
  reason `derivation_unit_mismatch:`): ``a + c`` with (V, A) refuses, but
  ``a + b + c`` with (V, V, A) computes, because the outer node's left operand is a
  sub-expression that carries no trackable unit in increment 1 — a numeric literal
  likewise. Whole-subexpression unit algebra stays deferred (§5). `*` and `/` impose no
  operand-unit rule: the declared `quantity`/`unit` of the derived variable is the
  author's responsibility. This residual is stated in the guard's docstring and in M15
  (claim discipline: the guard says what it does not catch).

Failure semantics, elementwise (mirroring M05's partial-variable rules):

- null operand element ⇒ null result element (nulls propagate as "unavailable");
- division by zero, or any non-finite intermediate/result ⇒ null result element —
  **never** `inf`/`NaN` (measurement-model.md §3: invalid numeric values never use
  NaN/Infinity);
- if any element became null for these reasons, the derived variable's `status` is
  `"partial"` with a `status_reason` naming the failing operation and operands; if every
  element failed, `"invalid"`. Otherwise `"valid"`.

Two structural contradictions are not per-variable quality failures and raise
`DerivationRefused` instead (the executor records `error_code: "DERIVATION_INVALID"` on
the step event and ends the body `execution_error` — a descriptor/dataset structural lie
is a conformance failure, and A06 wants it loud, while the raw dataset stays in scope as
evidence):

- the dataset already carries a variable with the derived id (a collision cannot be
  expressed: M01 forbids duplicate ids, and silently treating the plugin's variable as
  the derived one would launder provenance);
- the dataset is malformed where derivation must read (`variables` not a list, a variable
  entry not an object).

If the invoke result carries no dataset shape at all (e.g. a boolean action result),
derivation is skipped: the declaration is device-level and simply has nothing to derive
from for that action. `_step_invoke` applies derivation only when
`isinstance(data.get("result"), dict) and isinstance(result.get("variables"), list)`.

### 4.4 Metadata the evaluator emits

| Field | Value | Why |
|---|---|---|
| `id`, `quantity`, `unit` | from the descriptor declaration | author metadata, acceptance criterion |
| `dtype` | `"float64"` | the only dtype the grammar produces in increment 1; int/bool/logic arithmetic and coercion semantics are deferred (§5) |
| `dimensions` | the operands' common dimensions list | shape agreement is checked, so this is derived, not declared |
| `channel_ids` | ordered union of operand variables' `channel_ids` | honest provenance by construction (§2.2) |
| `values` | computed, inline | the `allOf` in §2.4 pins inline-only |
| `uncertainty` | `{"status": "unknown"}` — structurally, always | A02: a propagated bound presumes uncorrelated operand errors (same instrument, same aperture — the common case here!); the contract carries no independence evidence, so a "known" uncertainty would be fabricated qualification. Also: measurement-model.md §3 permits `known` only with evidence. The policy engine's conservative product bounds (`policy.py:20-24`) exist to *refuse work*, which is the safe direction; a dataset claim is an assertion, which is the unsafe direction |
| `calibration` | `{"status": "unknown"}` — structurally, always | `applied` requires a reference and method the combination does not have; `not_applied` would falsely describe the raw chain. Operands keep their own calibration records |
| `status` / `status_reason` | per §4.3 | M05 alignment |
| `derivation` | the closed marker (§2.4) | replay |

Consequence, intended and disclosed: a procedure `sample` step with
`require_known_uncertainty: true` refuses a derived-variable sample
(`executor.py:520-521`). That is A02 behaving correctly — an honest refusal, not a defect.

### 4.5 Gateway wiring (the runtime consumer)

In `control/executor.py _step_invoke`, after `self._dispatch(...)` returns with status
`ok`:

```python
derived = self._docs.descriptors[device_id].get("derived_variables")
if derived and <dataset-shaped result>:
    result = <rebuilt OperationResult with data["result"] =
              derive_dataset_variables(data["result"], derived)>
```

`OperationResult` is frozen; the rebuild constructs a new one (the `ok` classmethod
pattern at `executor.py`/`types.py:221-223`). Placement rationale:

- after dispatch success — derivation never re-dispatches, never extends deadlines, and
  the policy check has already governed the *input* (`check_allowed` at
  `executor.py:816`); derivation adds no physical work;
- before scope retention — so `select_sample`, predicates and any downstream consumer see
  derived variables exactly like plugin-emitted ones;
- transport-agnostic — when the async host/bridge gains invoke, the same seam applies
  (derivation at the executor, not the bridge, keeps one evaluation site).

A `DerivationRefused` propagates as a step failure (`error_code: "DERIVATION_INVALID"`,
body `execution_error`) — the existing `_dispatch` failure handling shape, no new body
outcome.

---

## 5. Minimal first increment and deferrals

**In scope (one RED→GREEN slice per commit):**

1. OTDP 0.1.2 bump: copy `standards/otdp/0.1.1/` → `0.1.2/`; edit in-copy only
   descriptor schema, measurement schema, `measurement-model.md` (§8 + M15 row),
   `otdp-specification.md` (§3 mention + S19 row), `examples/measurement-vectors.json`
   (one derived variable), new `examples/derivation-vectors.json`; bump `$id` URNs and
   the `otdp_version` const inside the copies; update `standards-manifest.json` (otdp →
   0.1.2, `supersedes: "0.1.1"`, normative list re-pathed + the new vectors file);
   `uv run python -m benchweave.standards repin`; export; `make check-sdk-standards`.
2. `src/benchweave/measurement/derivation.py` (+ package `__init__.py`), pure, strict
   mypy.
3. `control/documents.py`: `_check_descriptor` grammar/static admission.
4. `control/executor.py`: `_step_invoke` derivation application + refusal handling.
5. SDK: corpus sync (pushed first, then pointer — two-repo discipline),
   `validation.py` `sets` literal → `("otdp", "0.1.2")` and S19 in
   `validate_descriptor`; `OTDP_VERSION` constant if it tracks the corpus version
   (`packages/sdk/src/benchweave_sdk/__init__.py:12`).
6. Tests per §7; docs: `docs/device-developer-guide.md` §7 gains derived-variable
   authoring (links move to 0.1.2).

**Explicit deferrals (each names its seam):**

| Deferral | Why deferred / where it lands |
|---|---|
| OTDP↔execution descriptor projection-agreement check | needs both descriptors co-admitted; belongs to the binding-completeness stage that does not exist yet. Both carriers share one validator now; content drift is the disclosed residual |
| Artifact-backed operand derivation | inline `values` only in increment 1; artifacts need byte-level decode at the evaluation seam |
| Non-float64 dtypes, broadcasting, int arithmetic | coercion semantics are a grammar extension; refuse loudly today |
| Dimensional analysis for `*` `/` (unit algebra) | a unit algebra is its own standard; the declared unit is author responsibility, disclosed in M15 |
| Uncertainty propagation model | separately qualified extension (A02); would need correlation evidence the contract cannot carry |
| `evaluated_by` provenance field on the marker | replay does not need it (re-evaluation verifies); adds a trust claim without a verifier |
| Stream/capture derivation | those paths don't exist in the gateway yet (bridge limitation, fact 1) |
| Bridge/async-host invoke wiring | executor seam is transport-agnostic; bridge invoke is its own work package |
| Presentation/UI reading of derived variables | Row C's lane; the plugin-ui `dataset` binding already addresses variables generically |
| Interface contract (REST/MCP/openapi) changes | none needed — derived variables are dataset-internal; run records and evidence shapes are unchanged |

---

## 6. Cross-surface sync list (the 0.1.2 bump touch-set)

Main repository:

1. `standards/otdp/0.1.2/**` (copy-never-move from 0.1.1; 0.1.1 rows stay digest-frozen).
2. `standards/standards-manifest.json` — otdp entry: version, `supersedes`, normative
   list (re-path + `examples/derivation-vectors.json`).
3. `standards/corpus-manifest.json` — new 0.1.2 rows via repin only
   (`source: standards/otdp/0.1.1/<same-relative-path>`; the genuinely new vectors file
   cites its authoring path per the reset precedent — repin's fail-closed structural
   rules decide the exact acceptable form at build time); `identity.otdp: "0.1.2"`.
4. Version-literal sweep (verified sites, `grep "otdp/0.1.1"`):
   `src/benchweave/host/types.py:4` (docstring),
   `tests/contract/test_baseline.py:26,109` (version list + identity pin),
   `tests/contracts/test_architecture.py:79` (pinned-file table),
   `tests/contract/test_sim_plugins.py:34` (`CONTRACTS` path),
   `tests/contract/test_host_abi.py:4` (docstring),
   `tests/unit/test_presentation_specimens.py:27,34,168` (paths + the
   `urn:otdp:measurement:0.1.1` specimen),
   `tests/unit/test_presentation_presets.py:29`,
   `tests/unit/test_presentation_manifest.py:28`,
   `scripts/architecture/check_devices.py:15` (`OUT`),
   `scripts/architecture/check_execution.py:303`,
   `scripts/registry/registry_common.py:219`,
   `scripts/sdk_smoke.py:220` (`otdp_version` literal),
   `scripts/assemble_docs_site.py:437`.
5. New code: `src/benchweave/measurement/`, `control/documents.py`,
   `control/executor.py`.
6. Docs: `docs/device-developer-guide.md` (§7 + 0.1.1→0.1.2 links, M01–M14 → M15
   mention), `README.md`/operator guide only if they cite the OTDP version (grep at
   build time).
7. `docs/internal/invariants.md`: proposed new entry (§8 below).
8. Compatibility matrix: `matrix --check` must match a fresh render (GOVERNANCE gate 5).

SDK repository (commit + push FIRST, then the main-repo pointer):

9. `standards-lock.json`, stamps, `src/benchweave_sdk/standards/**` — via
   `sync-standards` from the exported bundle (never hand-edited, STD-5).
10. `src/benchweave_sdk/validation.py:26` — the hard-coded `("otdp", "0.1.1")` set
    literal → 0.1.2; S19 added to `validate_descriptor`.
11. `packages/sdk/src/benchweave_sdk/__init__.py:12` `OTDP_VERSION` if corpus-tracking.
12. SDK test literals: `tests/sdk/test_standards_sync.py:49`
    ("Generated from otdp@0.1.1"), `tests/sdk/test_adapter_agreement.py:607`
    (`_load_active("otdp-device-descriptor.schema.json")` — resolves via the active
    version, verify no literal break).

Not touched (verified no impact): interface 0.1.0 (no REST/MCP/openapi change),
execution 0.1.0 (the slim descriptor has no schema; `_check_descriptor` is code),
plugin-ui 0.1.0 (`measurement_schema_id` is a free-form id — `$defs/id` pattern, no enum —
so existing manifests citing the 0.1.1 URN stay valid; new manifests should cite 0.1.2,
a docs note not a schema change), registry 0.1.0, UI renderer, deploy templates.

**Tier:** 3 (on-disk schema change) — full test suite + the G6 independent second review
pass. **CI cost:** no new jobs; `gates` (repin/check-sdk-standards/mypy/pytest) and the
existing architecture-validator invocation cover it. Runtime cost: one descriptor parse
at admission; per invoke-with-dataset, one evaluation — CPU-only, bounded by
`maxLength`/nesting caps, no I/O.

**Invariant impacts:** no CTL/STO/CON/REG row changes (derivation is post-dispatch,
pre-scope; it does not touch policy checks, deadlines, the protective transition, the
store, or plugin admission). Proposed **new** invariants.md entry (Contracts family,
CON-9 candidate), to be added by the build with its test anchors:

> Derived-variable evaluation is a pure post-dispatch function of the plugin-returned
> dataset and the digest-pinned descriptor declaration: it never mutates
> plugin-returned data, never re-dispatches, appends variables carrying the closed
> `derivation` marker, emits structurally-unknown uncertainty and calibration, refuses
> unit/dtype/shape mismatches as in-band invalid/partial variables, and treats
> structural contradictions (id collision, malformed dataset) as step failures —
> `benchweave/measurement/derivation.py`, pinned by `tests/unit/test_derivation.py`,
> `tests/faults/test_derivation_faults.py`, `tests/control/test_documents_derivation.py`.

---

## 7. Measurable proof — pre-committed acceptance rule

Written before any test was run. The measured quantities are deterministic functions, so
the rule is a census, not a sample: every vector must agree; there is no effect-size
estimation to underpower. What CAN be underpowered is lane coverage — the rule therefore
names the lanes that must each produce evidence.

**Fixtures first:** `standards/otdp/0.1.2/examples/derivation-vectors.json` contains —

- **Grammar census (≥ 30 rows, ≥ 15 accept / ≥ 15 reject).** Reject classes, each
  represented ≥ 1: unbalanced parentheses; illegal character (including `e`-notation,
  uppercase, comma); empty/whitespace-only; over-length (> 256); nesting > 32; malformed
  number (`.`, `1.2.3`); identifier shape violation (`1a`, `_x`); trailing operator;
  self-referencing expression (static); cyclic derived-from-derived pair (static);
  duplicate derived ids (static).
- **Evaluation census (≥ 12 datasets):** scalar_set arithmetic; waveform (non-empty
  dimensions); nested unary (`-(-x) + +y`); derived-from-derived; null propagation;
  division-by-zero → null + partial + reason; overflow-to-non-finite → null + partial;
  unit mismatch on `+` → refusal; dtype mismatch (int64 operand) → refusal; shape
  (dimensions) mismatch → refusal; missing operand → invalid variable with reason;
  operand_ids/expression disagreement → refusal; id collision → refusal.

**SHIP if all of the following hold:**

1. Grammar census: 100% of accept rows accepted, 100% of reject rows refused with the
   expected `derivation_*:` reason prefix — in BOTH implementations (gateway module and
   SDK S19 lane) run over the same vendored file.
2. Evaluation census: 100% of expected outputs reproduced byte-identically (canonical
   JSON of derived variables), and re-evaluation of recorded outputs is a fixed point
   (replay check).
3. RED control A (admission is load-bearing): with the `check_derived_variables` call in
   `_check_descriptor` disabled, the admission test suite FAILS (the malformed
   descriptors are admitted); restored, it passes.
4. RED control B (evaluation is load-bearing): with the derivation application in
   `_step_invoke` disabled, the executor end-to-end test (a procedure `sample` step
   selecting a derived variable from an invoke dataset) FAILS with `SAMPLE_MISSING`;
   restored, it returns the computed value through `select_sample` with
   `configuration_id` provenance intact.
5. No-mutation pin: the plugin-returned dataset object deep-equals its pre-derivation
   snapshot after evaluation.
6. Gates: `uv run ruff check .`; bare `uv run mypy`; focused `uv run pytest` for touched
   modules + `tests/faults/`; full suite (Tier 3); `make check-sdk-standards`;
   `uv run python -m benchweave.standards` export/check; `matrix --check`; both repos'
   gates green with the SDK pushed before the pointer.

**KILL if:** any legal-expression class cannot be admitted without also admitting a
reject class (grammar unimplementable as specified); or evaluation determinism cannot be
guaranteed on the fixed operation sequence (float divergence between the platforms where the census actually runs — Linux and macOS; no Windows lane exists);
or the schema bump cannot pass `check-sdk-standards`/identity derivations without
touching the interface standard (scope explosion). Any of these means the design's core
claim is false — stop and record the negative.

**UNDERPOWERED (do not ship; add lanes, do not relax the rule) if:** only the unit lane
ran (no executor RED control B) — the wiring claim is then unproven; or the SDK lane ran
against a locally-edited vendored tree rather than a synced one — the two-repo agreement
claim is then unproven.

**RED-first test files to create:**

- `tests/unit/test_derivation.py` — grammar/static censes + evaluation censes +
  determinism/replay fixed-point + no-mutation pin (table-driven from the vendored
  vectors file, plus module-local edge cases).
- `tests/faults/test_derivation_faults.py` — div-zero/null/non-finite propagation,
  collision/malformed refusals, derived-from-derived ordering under repeated evaluation.
- `tests/control/test_documents_derivation.py` — admission accept/reject through
  `admit_documents` with descriptors carrying `derived_variables` (RED control A).
- `tests/control/test_executor_derivation.py` — end-to-end invoke→derive→`select_sample`
  against a sim plugin fixture whose slim descriptor declares a derived variable
  (RED control B); `DerivationRefused` → step `error_code: DERIVATION_INVALID` + body
  `execution_error`.
- `tests/sdk/test_derivation_agreement.py` (main-side) — SDK `validate_descriptor` S19
  over the same vendored census, agreeing with the gateway module on every row.
- `tests/contract/test_baseline.py` / `tests/contracts/test_architecture.py` — extended
  pins for the 0.1.2 corpus (version-list and pinned-file rows).

---

## 8. Top risks, each with its falsifier

1. **Two-carrier drift** (the OTDP declaration and the execution-side declaration
   diverge in content). Shared validator bounds the grammar risk to zero; content drift
   is real until the projection check exists (deferred, §5). *Falsifier for the design:*
   a build-agent demonstration that the execution-side carrier can be admitted with a
   derived id whose OTDP-side expression differs while both parse — if that turns out to
   be load-bearing for a run's meaning, the projection check must move into increment 1.
2. **Version-literal blast radius** (13+ literal sites). *Falsifier:* any gate still
   green with a stale `0.1.1` literal — the pins exist to make exactly this fail; sweep
   is mechanical (`grep -rn "otdp/0.1.1"`), and `test_baseline`'s identity assertion is
   the backstop.
3. **`urn:otdp:measurement` URN bump strands consumers.** Verified non-structural
   (`measurement_schema_id` is a free-form id; no enum). Residual: stale docs/copy —
   swept with the docs obligation.
4. **Float determinism across platforms.** The census pins one operation sequence; CPython
   floats are C doubles and none of the four operators are platform-variant in practice.
   *Coverage, stated honestly (2026-09-19 fix-wave amendment):* the census runs on Linux
   (CI `gates`) and macOS (dev), plus the dedicated OS-matrix lane added with this branch
   — no Windows lane exists, so cross-platform agreement is proven where the census runs
   and beyond that rests on the structural argument (IEEE-754 binary64,
   single-operation semantics with a fixed evaluation order), not on measurement.
   *Falsifier:* the census itself (kill direction 2) — this is precisely why the
   acceptance rule runs both implementations over one vendored vector file rather than
   trusting the argument.
5. **Executor couples to dataset shape.** `_step_invoke` grows a
   `variables`-list-shaped branch. *Falsifier:* the bridge/async-host work later needing
   a different seam — mitigated by keeping derivation in the pure module and the wiring
   to a rebuild-after-ok one-liner, movable wholesale.
6. **Security review flags any expression surface.** The parser is hand-written over a
   closed token set with no code-execution path, length- and nesting-capped; identifiers
   are data, never looked up as code. *Falsifier:* an accepted vector that drives the
   parser to non-linear time or unbounded recursion — the census + caps exist to make
   this testable.

---

## 9. Decisions taken (summary)

1. Operands are **dataset variable ids**, not channel refs — channels carry multiple
   quantities; variables carry the values, units and dtypes the checks need; provenance
   (`channel_ids`) is recoverable only via operands (§2.2).
2. Grammar lives in **versioned prose (M15/S19) + a digest-pinned vectors census**; the
   schema bounds only the character surface — the split every other semantic rule in this
   corpus already uses (§2.3).
3. **Execution-side slim descriptor carries the declaration verbatim** alongside the
   canonical OTDP home, because it is the only descriptor the gateway reads at run time —
   this is what makes "validated at admission" and the executor RED control real rather
   than aspirational (§1.1, §3).
4. **Uncertainty and calibration are structurally `unknown`** on gateway-derived
   variables — propagated bounds would fabricate the independence evidence A02 demands
   (§4.4).
5. Division by zero and non-finite results are **null + partial/invalid**, never
   NaN/Infinity — the measurement model's own §3 rule (§4.3).
6. Structural contradictions (id collision, malformed dataset) are **step failures**,
   not silent skips — A06 loud degradation while raw evidence stays intact (§4.3).
7. Replay is pinned by the **digest-pinned descriptor (expression bytes) + the in-dataset
   `derivation` marker (expression + operand ids beside the values)** + the URN's grammar
   version + the cross-implementation census (§4.2).
