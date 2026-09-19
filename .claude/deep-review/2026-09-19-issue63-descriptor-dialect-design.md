# Issue #63 — descriptor dialect reconciliation (+ R1/R2 absorbed from #66)

Date: 2026-09-19
Status: design for review. Main-repo only: **no standards bytes move, no SDK
submodule change, no pointer commit**. Everything below was verified against the
working checkout (`main`, commit `11d9480`) by reading the code and running the
real lanes (SDK checker, gateway admission, schema enumeration) — the baseline
numbers in §8 were measured after the acceptance rule in §8 was drafted, and the
rule's controls were specified before any fix exists. Baseline exit codes were
measured independently twice (this session and the controller's session; they
agree).

Scope (issue #63 + maintainer in-progress note):

1. **Dialect reconciliation**: one descriptor form that is both
   `benchweave-sdk check`-clean AND execution-admissible.
2. **R1** (from #66): `sim_psu` `_action_measure` fuses token-type with
   token-mismatch — a non-string `configuration_id` reports
   DEVICE_REJECTED/dispatched while `_action_configure` refuses the same input
   as INVALID_ARGUMENT/not_dispatched. Reconcile per the ABI + A06.
3. **R2** (from #66): fault-matrix vector `write_wrong_type_invalid_framing` —
   name says invalid-framing, expectation says DEVICE_REJECTED/dispatched.
4. **dps150 re-version to OTDP 0.2.0** (absorbed 2026-09-19 on measurement,
   §9.2 slice 5 + §10: the #64 stranding tail, untracked on the board, whose
   migration measured one line).

## 1. Problem, stated as measured fact

The runtime descriptor gate `_check_descriptor`
(`src/benchweave/control/documents.py:111-150`) requires a "slim" dialect:
non-empty string `id` + `version`; `profiles`/`parameters` lists of strings;
`actions` a list of `{action_id, issued?}` objects; optional
`derived_variables`. Descriptors have no schema on this path — exact-byte
decode plus that structural gate only. The OTDP toolchain
(`benchweave-sdk check` → `validate_descriptor`,
`packages/sdk/src/benchweave_sdk/validation.py:365-416`) validates the
full-form OTDP 0.2.0 descriptor schema
(`otdp/0.2.0/otdp-device-descriptor.schema.json`) plus semantic checks S01
(capabilities ↔ operations match; unique parameter names) and S02 (bounds not
reversed).

Measured this session (real CLI exit codes, real admission path):

| Plugin | `benchweave-sdk check` | execution admission |
|---|---|---|
| `sim_psu` | **FAIL (exit 1)** — 47 schema errors in two headline classes: (1) `id` `"descriptor-sim-psu"` violates `^[a-z0-9]+(\.[a-z0-9-]+)+$`; (2) `parameters` items must be objects (`name`/`type`/`access`/…) — bare strings rejected. The rest: missing `otdp_version`, `descriptor_version`, `display_name`, `description`, `identity`, `integration`, `transport`, `capabilities`, `operations`, `required_features`, `provenance`; `actions` must be an object; `version` matches no `^x-…` pattern | ADMITS (slim) |
| `sim_controller` | **FAIL (exit 1)** — 24 errors, the same two headline classes (plus `profiles: []` violating minItems 1) | ADMITS (slim) |
| `sim_scope` | passes (exit 0; full-form 0.2.0) | **REFUSED** — `schema: descriptor[psu] requires non-empty string version` (measured by swapping sim_scope's descriptor into the fixture graph through `admit_documents`) |
| `dps150` (reference, not a sim) | **FAIL (exit 1)** — `otdp_version` const is 0.2.0, descriptor declares 0.1.0 (stranded by the #64 bump). Its `id` (`org.benchweave.…` dot-form) already passes the pattern — the const is the only failure (probe-measured, §10.2) | n/a (not in the execution lattice) |

So zero of four in-tree descriptors are both check-clean and admissible; the
three simulators split 2 admissible-not-checkable vs 1 checkable-not-admissible.
The fork was disclosed by the #6 row A design §8 risk 1 and is tracked as #63.
(The row A record's "1 of 3 plugins pass check" baseline was measured before
#64 bumped the corpus — dps150 lost that property at #64 and nothing tracked
it.)

**Root cause.** Two gates were built by two work packages against two different
notions of "a descriptor", with no shared authority: the execution path grew a
hand-rolled structural check (WP04/05, module docstring: "device descriptors
have no vendored schema this work package") while OTDP later shipped a real
schema and checker (A09/A10). Neither gate consults the other; the slim
`issued` annotation has no full-form home, so the two shapes cannot even be
mechanically translated without deciding where issued-ness lives.

## 2. What the runtime actually needs from a descriptor (complete census)

Every consumer of the admitted descriptor after admission, verified by
searching all reads of `docs.descriptors` / `descriptor["..."]` in `src/`:

| Consumer | Field(s) read | Slim shape used | Full-form shape | Projection needed |
|---|---|---|---|---|
| `documents.admit_documents` `_verify_pin` (`documents.py:292-300`) | `id`, `version` | both strings | `id` ✓; `version` absent — full-form has `descriptor_version` | `version ← descriptor_version` |
| `binding._resolve_roles` (`binding.py:105-110`) | `profiles` | list[str] | list[str], **optional** (absent for profile-less devices; minItems 1 when present) | absent → `[]` |
| `binding._check_declared_usage` (`binding.py:153-164`) | `actions` (as `{action_id}` set), `parameters` (as name set) | list[{action_id}], list[str] | `actions` a **dict** keyed by action id; `parameters` list of objects with `name` | actions → list of `{action_id, issued?}`; parameters → names |
| `semantics._issued_fields` (`semantics.py:140-165`) | `actions` + per-action `issued` | list with `issued` | **no `issued` anywhere** — the full-form action object is closed (`additionalProperties: false`, exactly six properties: binding, input_constraints, timeout_ms, side_effect, cancellable, retry); the dict key is the action id | issued map from a descriptor-root `x-` extension key |
| `coordinator._run_and_record` (`coordinator.py:601-604`) | `derived_variables` | optional list | same key, same shape (OTDP 0.2.0 carries it; S19/M15) | passthrough |
| `bootstrap.admit_startup_bench` (`interfaces/bootstrap.py:66-76`) | `id`, `profiles` | — | `descriptor.get("profiles", [])` — **already dialect-tolerant** | none |
| `interfaces.Operations._device_projection` (`interfaces/operations.py:1448-1462`) | `id`, `version` | `descriptor.get("version", "1")` | `version` absent → **silently fabricates `"1"` on the wire** (latent defect, D4 doc-ref-honesty family) | `version ← descriptor_version` |

The executor reads no descriptor fields directly (its derived-variable input is
pre-extracted by the coordinator). Tests follow the fixture bytes
(`tests/control/_harness.py` re-admits the fixture graph and repoints pins);
**no test constructs a slim descriptor from scratch** (verified by search — the
slim dialect exists only in the two plugin descriptors and their
`fixtures/execution/` byte-copies, the latter pinned equal by
`tests/contract/test_sim_layout.py:15`).

## 3. Where `issued` lives in full form — the decision the fork turns on

The slim `issued` list marks which invoke input keys accept the gateway-issued
token (`$stg_issue`, CTL-7). Candidates:

1. **A descriptor-root `x-` extension key** (chosen). The OTDP schema admits
   root keys matching `^x-[a-z0-9]+-[a-z0-9_-]+$` unconstrained
   (`patternProperties`, `additionalProperties: false` otherwise), and the
   extension contract explicitly blesses the mechanism: "Unknown optional `x-`
   metadata remains ignorable and cannot change required behaviour"
   (`standards/otdp/0.2.0/extension-contract.md:13`). Verified accepted by
   `validate_descriptor` with an `x-` key present. OTDP tooling ignores it; the
   STG runtime reads it — the same authority relationship as today (the plugin
   author declares what their adapter expects as gateway-issued), relocated to
   the contracted extension point. This also matches OTDP's own framing that
   host-owned metadata rides separately
   (`otdp-specification.md:319`: bench/policy/commissioning metadata "remain
   host-owned and separate from shared device descriptors").
2. **Derive from the profile catalog** — falsified: the catalog contains no
   machine-readable issued marker (verified: the strings "issued"/"gateway"
   do not occur in `device-profile-catalog.json`). Deriving would mean
   hardcoding device-class prose as gateway constants — the A02 universal-
   assumption sin, plus profile satisfaction is explicitly a later admission
   stage.
3. **The bench/commissioning documents** — falsified: their schemas are the
   vendored execution/0.1.0 corpus; adding a field there is an
   execution-contract version bump, i.e. the standards train this increment
   must not board.

Chosen name: **`x-stg-issued-inputs`**, a root object
`{action_id: [input field, ...]}`, read only by the gateway. It must name only
actions the descriptor declares; anything else is an admission refusal
(§6).

## 4. Mechanism

### 4.1 The choice

**(a) Runtime admits full-form by projecting to its slim needs** — and the
tree converts to full-form so one dialect remains.

`_check_descriptor` becomes a validating projection
(`_project_descriptor(device_id, descriptor) -> dict`):

1. Validate against the **active** vendored OTDP descriptor schema — resolved
   the way the gateway already resolves it for identity derivation
   (`standards/manifest.py:11` `DESCRIPTOR_SCHEMA_NAME` +
   `_descriptor_relative`; `vendoring.contract_family` gives the packaged-first
   path; validator cached exactly like `_validator` in `documents.py:73-84`).
   The schema's `otdp_version` const means corpus alignment is enforced by the
   schema itself, not by a gateway constant.
2. Apply the S01/S02 semantic mirrors (unique parameter names — load-bearing:
   `binding.py:164` builds a `set()` from the names, so duplicates must be
   structurally refused, not silently deduped; capabilities ↔ operations set
   equality; no reversed `range` bounds) — a ~10-line mirror of
   `validation.py:403-414`, pinned equivalent by the census test (§8).
3. Read `x-stg-issued-inputs`; refuse unless it is an object of
   action_id → list-of-strings whose keys are all declared `actions`
   (`schema: descriptor[<id>] issued_map: …` machine-matchable prefix).
4. Project the execution view and return it:

```python
{
  "id": descriptor["id"],
  "version": descriptor["descriptor_version"],
  "profiles": list(descriptor.get("profiles", [])),
  "parameters": [p["name"] for p in descriptor["parameters"]],
  "actions": [{"action_id": aid, **({"issued": fields} if fields else {})}
              for aid, fields in issued_projection],
  # derived_variables passed through verbatim when present (check_derived_variables as today)
}
```

`admit_documents` stores the **view** in `AdmittedDocuments.descriptors` and
verifies the pin against the RAW document's `id`/`descriptor_version` and the
RAW bytes' digest. Consumers (`binding`, `semantics`, `coordinator`) are
untouched — the view is exactly the shape they read today. The projection is
total (the schema guarantees every field it reads) and runs after validation,
so nothing downstream can see an unvalidated shape.

The slim dialect **dies at the end of the increment** (slice 4): after the
tree converts, nothing in-tree is slim, and no test constructs slim bytes —
refusing it is the "make bad states unrepresentable" close. A descriptor that
is not OTDP-valid is not execution-admissible, and `check`-clean becomes a
necessary condition for admissibility (modulo the x- key, which check ignores
by contract).

### 4.2 Why the alternatives lost

- **(b) Toolchain dual-emit from one source** (SDK emits a slim execution
  descriptor alongside the full-form one): two artifacts per plugin, a new
  generator with its own tests and determinism burden, a second pin target in
  the bench lattice, and a standing drift surface (full-form says X, emitted
  projection says Y — the exact "silent drift" CON-2 exists to prevent, one
  level down). sim_scope would ALSO need a slim emission, so the fork survives
  de jure forever. It reconciles nothing; it accommodates the fork.
- **Keep both dialects as legitimate kinds** (execution descriptor ≠ OTDP
  descriptor as a matter of policy): the #63 acceptance ("both check-clean AND
  admissible") is then unreachable by construction for any single document;
  this is the status quo renamed.
- **Runtime imports the SDK's validator**: the gateway does not depend on the
  SDK package (REG-4 pins the protocol by reading the SDK tree in tests, not
  by importing it). A runtime dependency inversion for 10 lines of semantic
  checks is not justified; the census test pins the mirror instead — the
  REG-4 pattern applied to descriptor semantics.

### 4.3 What does NOT change

- The five contract documents, their schemas, the pin-lattice mechanics, the
  exact-byte decoder (CON-1: the digest is of raw bytes; schema validation
  operates on the decoded pinned content, same as the contract docs).
- The procedure language, `$stg_issue` semantics (CTL-7 — issued fields still
  come from the descriptor, now via the projected view), policy, protection,
  the store (the `devices` table keeps raw `descriptor_json` + `profiles_json`;
  bootstrap is already tolerant).
- `standards/` bytes, the corpus manifest, `make check-sdk-standards`, the SDK
  submodule pointer. **Main-repo only.**

## 5. Consumer-by-consumer outcome

| Surface | Gets |
|---|---|
| `binding`, `semantics`, `coordinator` | the projected view (byte-for-byte the shape they read today; zero code change) |
| Pin lattice (`bench.devices[].descriptor`) | raw `id` + `descriptor_version` + raw-bytes sha256 |
| Store/bootstrap | raw bytes; `profiles_json` via `get("profiles", [])` (unchanged) |
| `_device_projection` (REST/MCP device inventory) | fixed to report `descriptor_version` — removes the silent `"1"` fabrication (`operations.py:1458`; read `version` first for pre-conversion rows, else `descriptor_version`) |
| `benchweave-sdk check` | nothing (the x- key is ignorable OTDP metadata) |
| Evidence records | unchanged — descriptors were never embedded in run records; the content store keeps raw bytes |

## 6. Migration surface — every file and pinned digest that moves

Plugin sources (each moves its payload+manifest sha256 in the registry
lattice, rebuilt same-commit via `scripts/registry/build_fixtures.py` —
deterministic, keys committed — the #66 lesson `3fab509`):

1. `plugins/benchweave/sim_psu/src/benchweave_sim_psu/descriptor.json` —
   full-form rewrite on the sim_scope pattern: `otdp_version "0.2.0"`,
   `descriptor_version "1.0.0"`, id **`dev.benchweave.sim-psu`** (schema
   pattern), display_name/description/identity (listed firmware
   `sim-0.1.0` — what the plugin's identify reports), integration adapter
   (entry_point `benchweave_sim_psu.plugin:create_plugin`, api_version `1.1`),
   declarative serial transport, capabilities `[identify, read, write,
   invoke]` + matching `operations`, 11 parameter objects (each with
   binding/read_policy/write_policy mirroring the sim's actual bounds — the
   WRITABLE_BOUNDS tables in `plugin.py:29-41` become the declared `range`s),
   `required_features` `[otdp.core, otdp.adapter, otdp.profile_actions,
   otdp.measurement, otdp.dc_psu/1.0.0]`, provenance (synthetic vectors),
   `channels [ch1]`, `profiles ["otdp.dc_psu/1.0.0"]`, contracts pinning the
   catalog + measurement schema, `actions` dict for configure/output/measure,
   and **`x-stg-issued-inputs: {"otdp.dc_psu.configure/1.0.0":
   ["configuration_id"]}`**.
2. `plugins/benchweave/sim_controller/src/benchweave_sim_controller/descriptor.json`
   — full-form, **core-only**: no `profiles` key (schema forbids empty; the
   projection yields `[]`), no `actions` key (schema forbids empty; projection
   yields `[]`), 3 parameter objects (`uptime_s` ro, `identity_model` ro,
   `operator_note` rw), capabilities `[identify, read, write]`. Id
   `dev.benchweave.sim-controller`.
3. `plugins/benchweave/sim_psu/src/benchweave_sim_psu/plugin.py` — the R1
   fixes (§7).
4. `plugins/benchweave/sim_psu/src/benchweave_sim_psu/vectors.json` — R2
   expectation flip + two new vectors (§7).

Execution fixture lattice (digest cascade; `tests/contract/test_sim_layout.py`
pins plugin↔snapshot byte-equality, `test_registry_fixtures.py` recomputes):

5. `fixtures/execution/descriptor-sim-psu.json`,
   `descriptor-sim-controller.json` — byte-copies of the new descriptors.
6. `fixtures/execution/bench.json` — both device descriptor pins move
   (id, version, sha256).
7. `fixtures/execution/commissioning.json` — pins bench sha256.
8. `fixtures/execution/run-binding.json` — pins bench + commissioning sha256.
9. `fixtures/registry/origin-main/**` + `origin-b/**` + `catalogue.json` —
   rebuilt: the four sim packages' payload bytes change (descriptor/plugin
   members), and because `_payload()` embeds each member's sha256 in the
   manifest, **both** `payload_sha256` and `manifest_sha256` move. One
   decoupling worth stating so nobody hunts phantoms: the manifests'
   `descriptor_ids` (`provides` and `device_targets[]`,
   `scripts/registry/registry_common.py:_device_target`) are **synthesized
   fixture identities** (`benchweave:sim-psu:1.0.0`,
   `build_fixtures.py:203,227`) — they do NOT carry the descriptor document's
   `id`, so the id rename moves no manifest metadata beyond the embedded
   payload digests. Pre-existing fixture-manifest staleness
   (`compatibility.otdp_versions: ["0.1.0"]` while the corpus is 0.2.0) is
   unvalidated by anything in `src/` (verified by search) and is deliberately
   left alone — fixture-catalogue metadata, not this increment's claim.

Tests:

10. `tests/integration/test_procedures.py` — `DESCRIPTOR_FAULTS` (6 mutations,
    `test_procedures.py:241-260`) rewritten to full-form equivalents with the
    schema's own messages (still `schema:`-prefixed): profiles scalar,
    actions-as-list, `descriptor_version` pattern violation, duplicate
    parameter name (S01 mirror), reversed range (S02 mirror), issued-map
    naming an unknown action. Count parity kept.
11. `tests/integration/test_rest_routes.py:74`,
    `test_interface_parity.py:168`, `test_poc_acceptance.py` (device-id
    lists) — wire device ids follow the descriptor ids
    (`descriptor-sim-controller` → `dev.benchweave.sim-controller`; bootstrap
    keys rows by descriptor id, `bootstrap.py:69`).
12. `plugins/benchweave/sim_controller/tests/test_vectors.py:58` —
    `descriptor["profiles"] == []` → `descriptor.get("profiles", []) == []`
    (sim_psu's twin assertion at its `:58` still passes as-is).
13. `tests/contract/test_sim_plugins.py:276-291` — the D1 pin flips with R1
    (docstring rewritten; see §7).
14. New `tests/sdk/test_descriptor_equivalence.py` (census, §8) and
    `tests/control/test_documents_fullform.py` (projection unit controls).

Runtime:

15. `src/benchweave/control/documents.py` — the projection gate (slice 2),
    slim refusal (slice 4), module docstring rewrite ("descriptors have no
    vendored schema" is no longer true).
16. `src/benchweave/interfaces/operations.py:1458` — version fix.

Docs:

17. `docs/device-developer-guide.md` — descriptor authoring section: full-form
    is the execution-admitted form; the `x-stg-issued-inputs` contract (shape,
    gateway-only reader, refuse-on-unknown-action); "check-clean is necessary
    for admissibility".
18. `docs/internal/invariants.md` — amendments (§8.4 below).

dps150 (slice 5, §9.2 — absorbed; NOT in the registry lattice or execution
fixtures, so no lattice cascade):

19. `plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.json` —
   `otdp_version` "0.1.0"→"0.2.0", `descriptor_version` "0.1.0"→"0.2.0"
   (measured: these are the ONLY changes the document needs — with the const
   fixed it produces 0 schema errors and passes `validate_descriptor`).
20. The plugin's `build_descriptor()` (its test asserts
   `descriptor.json == build_descriptor()`, `tests/test_adapter.py:176`) —
   synced with the two version fields.
21. `plugins/fnirsi/dps150/contracts/otdp-0.2.0/` — new vendored copy of the
   eight corpus files (the old `contracts/otdp-0.1.0/` dir STAYS: plugin-level
   copy-never-move, preserving the evidence trail of what 0.1.0 validated
   against).
22. `plugins/fnirsi/dps150/contracts/lock.json` — repointed at
   `standards/otdp/0.2.0` with the corpus digests; `revision` cites the commit
   that introduced the 0.2.0 corpus (#80 merge `64f64a9`). Amendment
   (2026-09-19, builder follow-up): the lock's `otdp_version` field — stale
   at `"0.3.0"`, a version that never existed as a corpus (a relic of the
   pre-consolidation `standards/otdp-v0.3.0` naming) — is corrected to
   `"0.2.0"` with the repoint; nothing reads the field, and a contradicting
   version beside the machine authority inside one document is
   prose-vs-machine drift.
23. `plugins/fnirsi/dps150/tests/test_adapter.py:32` — `SCHEMAS` literal →
   `contracts/otdp-0.2.0` (plus any lock-verification assertions the file
   carries — the builder walks them).

Deliberately NOT moving: `plugins/benchweave/sim_scope/**` (already full-form
and already check-clean; it becomes admissible with zero byte changes — the
cleanest possible proof the mechanism, not a rewrite, closed the fork; its own
`x-stg-issued-inputs` declaration is §10-deferred), `standards/**`,
`packages/sdk/**`, `docs/smart-test-gateway-decisions.md` (no decision
record changes — A09's annotations already carry the corpus versions).

## 7. R1/R2 — the classification and its fix

### 7.1 The taxonomy (decided on evidence, not preference)

**An argument that violates its action's input typing is a framing failure:
INVALID_ARGUMENT / not_dispatched. An argument that is well-typed but rejected
against device state or envelope is a device evaluation: DEVICE_REJECTED /
dispatched.**

Evidence, in order of authority:

1. **The profile catalog types the fields** — `configuration_id` is
   `type: string` on all three dc_psu actions
   (`device-profile-catalog.json` actions; measured). A non-string token is a
   schema violation of the action input contract: the request is malformed
   before any device-state semantics exist. A06: `dispatch_state` is evidence
   — `dispatched` asserts the device evaluated the request. A Python
   `123 != "cfg-1"` comparison is not a device judgment.
2. **The plugin's own doctrine** — `_state_reject`'s docstring
   (`plugin.py:166-176`): "Input validation failures before any handler state
   is touched keep the NOT_DISPATCHED form via _reject."
3. **In-tree precedent** — `_action_configure` refuses non-string tokens as
   INVALID_ARGUMENT (`plugin.py:427-431`); `_write`'s `output_enabled` /
   `operator_note` type checks are INVALID_ARGUMENT (`plugin.py:249-253`);
   `read_missing_parameter_invalid_framing` and
   `write_missing_value_partial_delivery` pin missing/malformed arguments as
   INVALID_ARGUMENT/not_dispatched.
4. **The fault-matrix naming convention** — the `_invalid_framing` suffix
   means INVALID_ARGUMENT/not_dispatched (pinned by the read-vector sibling).
   R2's vector name was always right; the classification was wrong.

### 7.2 The fixes (all four fused sites, for consistency)

- **`_action_measure`** (`plugin.py:478-482`): split the fused check —
  non-string/empty `configuration_id` → `_reject(INVALID_ARGUMENT, "measure
  requires configuration_id")`; string mismatch → `_state_reject` (unchanged;
  still pinned by `invoke_measure_requires_current_configuration` as
  DEVICE_REJECTED/dispatched).
- **`_action_output`** (`plugin.py:455-459`): `token is not None and not
  isinstance(token, str)` → INVALID_ARGUMENT (the catalog makes the token
  optional on output; absence stays legal, mismatched string stays
  `_state_reject`).
- **`_write` bounds branch** (`plugin.py:234-244`): type split from range —
  non-numeric (or bool) value for a bounded parameter → `_reject(
  INVALID_ARGUMENT, "bad type for …")`; numeric out-of-bounds →
  `_state_reject` (unchanged; still pinned by
  `write_setpoint_out_of_bounds` as DEVICE_REJECTED/dispatched).
- **R2**: `vectors.json:51` `write_wrong_type_invalid_framing` expectation
  flips to `INVALID_ARGUMENT` / `not_dispatched` — the name becomes honest
  with no rename. The dispatched-refusal class keeps coverage via
  `write_setpoint_out_of_bounds` and the OVP vectors.

New vectors (RED against the current plugin — the R1 proof):

- `invoke_measure_nonstring_token_invalid_argument` — measure with
  `configuration_id: 123` → INVALID_ARGUMENT/not_dispatched.
- `invoke_output_nonstring_token_invalid_argument` — output with
  `configuration_id: 123` → INVALID_ARGUMENT/not_dispatched.

Pinned surfaces that flip with the fix: `vectors.json` (above),
`test_sim_plugins.py:276` (docstring: wrong type no longer "lands in the
envelope branch"; the envelope now evaluates only well-typed values), and the
registry payload digests that carry them (already in §6 item 9). The
`_write_parameter` re-homing (`plugin.py:373-397`) is untouched: an inner
write failure still reports DISPATCHED from the invoke — correct, because by
then the invoke WAS dispatched; the inner failure's code now simply carries
the reconciled classification upward.

## 8. Invariant impacts

- **CON-1 amendment**: descriptor admission gains a real schema — the active
  vendored OTDP descriptor schema (packaged-first via `contract_family`,
  active version derived from the standards manifest, never a hardcoded
  version) — replacing the "minimal structural check" language. Exact-byte
  decode + digest pins unchanged.
- **New CON-10 (single dialect + projection)**: a device descriptor is an
  OTDP full-form document; execution admission validates it against the
  active vendored schema plus the S01/S02 mirrors, validates the
  gateway-owned `x-stg-issued-inputs` extension (shape + declared-actions
  only), and projects a total execution view (`{id, version =
  descriptor_version, profiles (absent→[]), parameter names, actions +
  issued, derived_variables passthrough}`); the slim list dialect is refused.
  Gateway admission and `benchweave-sdk check` are pinned equivalent over the
  in-tree descriptor corpus × mutation matrix by
  `tests/sdk/test_descriptor_equivalence.py`.
- **REG-2 amendment (dispatch-state honesty, A06)**: `not_dispatched` is
  reserved for failures that precede any device evaluation — argument
  presence AND argument typing included; a wrong-typed argument can never
  yield DEVICE_REJECTED. (Pins the R1 taxonomy as an invariant, not a sim
  quirk.)
- **CTL-7**: mechanically unchanged — issued fields still come from the
  descriptor; the view carries them. The wording "the role's device descriptor
  marks issued" remains true (the x- key is part of the descriptor).
- **CON-2 / fixture lattice**: the digest cascade in §6 items 5-9 is exactly
  this obligation discharged same-commit.
- Tier: on-disk formats change (plugin descriptors, fixture lattice bytes,
  registry payloads) but no gateway schema or store migration — descriptors
  are admitted documents, not a store format. Not Tier 3.

## 9. Measurable proof — pre-committed acceptance rule

Written before any fix exists. Baseline numbers in §1 were measured after this
rule was drafted; every control below is specified against the current tree.

### 9.1 The rule

Population: census, not sample — the 3 in-tree simulators plus dps150, each ×
(clean + 6 mutations), plus the admission graphs and RED controls below.
Metrics are process exit codes / admission outcomes / finding prefixes, never
output-filter text.

**SHIP iff all hold:**

1. **Both-properties count = 3 of 3 simulators**: each (a) exits 0 under
   `benchweave_sdk.cli.main(["check", <descriptor>])` in-process
   (syspath-prepend precedent `tests/sdk/test_presentation_cli.py`), and (b)
   admits through the REAL `admit_documents` — psu/controller via the standing
   fixture lattice, sim_scope via a minimal harness graph (the
   `tests/control/_harness.py` pattern with the psu descriptor swapped —
   exactly the probe used for the §1 baseline). dps150's leg is check-only
   (exit 0) — it is not execution-wired and does not become so.
2. **Dialect-death RED control**: the old slim sim_psu bytes (committed as a
   control fixture, e.g. `tests/control/fixtures/descriptor-slim-control.json`)
   are REFUSED by admission with a `schema:` prefix after slice 4 (before it,
   they still admit — that asymmetry is the slice-4 RED).
3. **Projection controls** (each refuses with the stated prefix):
   x-map naming an undeclared action → `schema: … issued_map:`; duplicate
   parameter name → S01-mirror refusal; reversed range → S02-mirror refusal;
   `otdp_version` stale → schema const refusal (dps150's pre-slice-5 condition
   is the living example, pinned by its own check run) — proving the gate,
   not the fixture conversion, does the work.
4. **Equivalence census**: for corpus {sim_psu, sim_controller, sim_scope,
   dps150} × matrix {clean, id-pattern violation, profiles scalar,
   actions-as-list, duplicate parameter name, reversed range, issued-map
   unknown action} (dps150 cells: actions-as-list and issued-map mutations
   add the minimal object/map — its core-only shape is the interesting
   boundary): `gateway-admissible(descriptor) == sdk-check-clean(descriptor)`
   — 28 cells, symmetric. Gateway leg runs through `admit_documents` (not the
   projection function directly), so the pin lattice is exercised.
5. **R1/R2 RED controls**: the two new vectors fail against the pre-fix
   plugin (watched RED) and pass after; `write_wrong_type_invalid_framing`
   expectation flip is watched RED first; the mismatched-STRING token still
   DEVICE_REJECTED/dispatched (pins no over-rotation); out-of-bounds numeric
   write still DEVICE_REJECTED/dispatched; `test_sim_plugins.py` D1 test
   flipped in the same slice.
6. **Structure pins hold**: `test_sim_layout.py` byte-equality;
   `test_registry_fixtures.py` rebuilt-lattice equality (rebuild leaves git
   diff empty after commit); wire device ids updated in the three literal
   sites; `_device_projection` reports `descriptor_version` (a wire assertion
   on the device inventory's descriptor.version — the anti-fabrication pin);
   dps150's `test_adapter.py` suite green against the re-versioned descriptor
   and the repointed contracts lock.

**KILL iff:** any RED control in 2-5 passes when it should fail (the
mechanism is not load-bearing); or the census can only be made symmetric by
editing bytes under `standards/` (falsifies the no-standards-change premise —
park the increment on the standards train with this document as evidence);
or sim_scope's admission requires ANY change to sim_scope's bytes (would mean
the projection is not actually generic).

**UNDERPOWERED iff:** the census mutations never reach the S01/S02/x- layers
(every mutation only exercises schema structure — each layer needs its own
breaker, which is why 3/4/5 name them per-layer); or any admission leg runs
against `_project_descriptor` directly rather than through `admit_documents`
(then "admissible" was not proven end-to-end — the pin lattice was skipped).

### 9.2 Slice plan (one RED→GREEN per commit)

1. **R1/R2** (independent, smallest): vectors RED → plugin taxonomy fix →
   test flips. De-risks the rest.
2. **Gate learns full-form** (dual-accept interim): projection + S01/S02
   mirrors + x- validation, with sim_scope-admission and issued-map controls
   RED first (the sim_scope control is RED today — measured in §1).
3. **The tree converts**: descriptors, fixture cascade, registry rebuild,
   fault-matrix rewrite, wire-id literals, `_device_projection` fix, census
   test (RED against the still-slim tree, GREEN same slice), docs +
   invariant amendments.
4. **Slim dies**: remove the slim branch; the control fixture flips
   admitted→refused (RED first). documents.py docstring rewrite lands here.
5. **dps150 re-version** (independent of 1-4): RED = its check run fails
   today (measured, exit 1, const-only); GREEN = the two version fields +
   `build_descriptor()` sync + `contracts/otdp-0.2.0/` copy + lock repoint +
   `SCHEMAS` literal, verified by its own test suite and an exit-0 check run.

### 9.3 Why dps150 is absorbed rather than filed (the measured call)

The deferral directive says absorb small items rather than park them. The
measurement that makes this small: with `otdp_version` set to "0.2.0" in a
scratch copy, dps150's descriptor produces **0 schema errors and passes
`validate_descriptor`** (S01/S02 included) — the #64 tightening is
class-bounded (oscilloscope configure `averaging_count`, oscilloscope/LA/DAQ
`sample_count` ceilings) and dps150 is a core-only identify/read descriptor
with no profiles, actions, or acquisition inputs, so the re-version asserts
nothing new about the device. The provenance risk I first suspected
(re-versioning a real-adapter document) dissolves on that measurement — the
descriptor's own description declares it mock-qualified, and the schema it
must satisfy changed only in ways provably irrelevant to its class. Cost: two
JSON fields, one code sync, one vendored-dir copy (8 files, old dir kept),
one lock repoint, one test literal — all verified by the plugin's own suite.
It is untracked on the board (verified against the open issues), and leaving
it dirty would make this increment's own claim ("check-clean is necessary for
admissibility", demonstrated over the in-tree corpus) ship with a standing
counterexample in the tree.

## 10. Deferrals (each with a proposed issue title, created at PR-open)

1. **"sim_scope issued-token declaration + execution wiring"** — sim_scope's
   own `x-stg-issued-inputs` key (needed the day a procedure `$stg_issue`s its
   configure) and optionally wiring it into the execution fixture bench.
   Folds naturally into #65 (sim_scope polish). Kept out so sim_scope's
   zero-byte-change admissibility stays the clean mechanism proof.
2. **"Issued-field existence check against the profile catalog"** — the x-
   map's field names are shape-checked only (list of strings); verifying they
   are real action input fields requires the catalog in admission, which is
   the deferred profile-satisfaction stage (C01-C12 territory). Residual is
   loud at runtime (plugins reject unknown keys) and at semantics
   (`issue_placement:`).
3. **"Bootstrap routes descriptors through the admission gate"** —
   `admit_startup_bench` json.loads descriptors without validation today;
   after this increment the gate exists and bootstrap could call it. Wiring
   change with failure-mode questions (startup on invalid lattice) of its own.
4. **"Fixture-manifest compatibility metadata refresh"** — the fixture
   registry manifests' `compatibility.otdp_versions: ["0.1.0"]` staleness
   (§6 item 9): unvalidated, cosmetic, and touching it would churn every
   committed manifest for no tested property.

## 11. Top risks, each with its falsifier

1. **The S01/S02 mirror drifts from the SDK's semantics** (the WP07 lesson:
   duplicated logic pinned twice wrong). *Falsifier:* the census (§9.1.4) —
   any semantic-layer divergence between gateway and check shows as an
   asymmetric cell in CI. Residual: the census covers the in-tree corpus and
   the named matrix, not all possible descriptors; a future SDK-only check
   (S03+) appears as asymmetry only when a descriptor exercises it — the
   census file is the place that surfaces, and the CON-10 wording claims
   equivalence "over the in-tree corpus × mutation matrix", no more.
2. **Wire device-id churn** (`descriptor-sim-psu` → `dev.benchweave.sim-psu`)
   breaks a consumer we didn't find. *Falsifier:* the grep census in §2/§6
   found three literal sites, all in-tree tests; the interface contract's own
   examples never name the sims (verified — no standards move). The deeper
   conflation (bootstrap keying inventory rows by descriptor id at all) is
   pre-existing WP08 wiring, unchanged in kind by this increment.
3. **Full-form conversion drags provenance claims** — a full-form descriptor
   asserts operations policies, transport, firmware lists; a sloppy
   conversion could overclaim (e.g. firmware the sim doesn't report).
   *Falsifier/mitigation:* the conversion spec in §6 item 1 derives every
   declared value from the plugin's actual behavior (identify's firmware
   string, WRITABLE_BOUNDS as ranges); the census + `test_sim_plugins`
   CONFORMING suite re-run against the same plugin binaries; A05 unchanged
   (executable plugin changes are release changes — this IS the release-train
   change).
4. **The x- key is mistaken for an OTDP contract change** (review friction,
   or a future contributor "cleans" it away). *Mitigation:* CON-10 names it
   gateway-owned; the developer guide states OTDP tooling ignores it; the
   census proves check stays clean with it present. *Falsifier if wrong:*
   any `benchweave-sdk check` refusal caused by the key (would falsify the
   extension contract's own text — verified it passes today).
5. **Registry rebuild collateral** — the same-commit rebuild is mandatory
   (#66) and deterministic; if `build_fixtures.py` output drifts (key
   regeneration invalidates every committed signature — its own docstring),
   the rebuild is uncommittable. *Falsifier:* `test_registry_fixtures.py`
   asserts rebuilt == committed; run the rebuild first thing in slice 3 to
   surface any key/toolchain problem before the descriptor edits stack on it.
6. **dps150's vendored-contracts copy desyncs from the lock or the corpus** —
   the plugin pins its own evidence (8 files + digests), and a sloppy
   re-version could leave `contracts/otdp-0.2.0/` bytes disagreeing with the
   lock or the main tree's corpus. *Falsifier:* the plugin's own
   `test_descriptor_schema_and_package_evidence` (validates the descriptor
   against the SCHEMAS dir and asserts package evidence) plus a
   digest-equality assertion between the vendored copy and
   `standards/otdp/0.2.0/` — the CON-4 one-source-of-truth posture at plugin
   level; the census's dps150 row adds the gateway-side leg.
