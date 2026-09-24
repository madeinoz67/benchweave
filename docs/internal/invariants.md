# Hard invariants

Testable assertions a PR must never violate. Anchors are on `main`. When an anchor's line
number drifts, the symbol name is the source of truth — re-locate by grep, don't trust the
number. If the live code disagrees with an assertion here, the code wins: flag the stale
invariant, don't enforce it.

Format: **[ID]** assertion — `file:anchor` — *why it matters / what breaks if violated.*

These start life anchored on module contracts (docstrings that state behavior as a
promise) and the architectural decision record (`docs/smart-test-gateway-decisions.md`
A01–A14). When a review fixes or sharpens one, append the amendment with its evidence
rather than rewriting the history — that is how this file earns trust.

---

## Control & execution invariants

- **[CTL-1]** The protective deadline is fixed at the FIRST entry to protecting —
  `entered_at_ns + safe_transition.max_duration_ms` of monotonic time — and is never
  extended and never restarted; later entries append reasons only —
  `src/benchweave/control/protection.py`. *A14: repeated trips cannot restart a protective
  deadline. A re-arming transition is an unbounded one wearing a timer.*
- **[CTL-2]** Every safe action is dispatched under `min(action timeout, remaining
  protection budget)`, and final verification polls the bench signals until the whole
  conjunction holds CONTINUOUSLY for `stable_for_ms` within that budget — `protection.py`.
  *Nothing outruns the protective budget, and "safe now" means "stably safe", not "safe at
  the instant of the last poll".*
- **[CTL-3]** Safe actions are the policy's own protective authority, admitted with the
  policy at commissioning time with literal arguments, and are dispatched WITHOUT
  re-evaluation against the body's allow rules — `protection.py`. *The shutdown path must
  not be vetoable by the rules that govern productive work; a policy check that could deny
  the safe transition is a fuse that blows by design.*
- **[CTL-4]** `check_allowed` is deny-by-default and the executor consults it before EVERY
  state-changing dispatch: allowed only when at least one allow rule matches the actual
  device and the exact action id (invoke), parameter (write) or format (capture — the
  third allow-rule kind, issue #176 increment 2), and every matching rule's constraints
  hold conjunctively — no order-dependent overrides. Rejections carry
  machine-matchable prefixes (`no_matching_rule:`, `input_constraint:`, `value_constraint:`
  and the capture family's `capture_constraint:`)
  — `src/benchweave/control/policy.py` `check_allowed`. *An allow-list cannot be widened by
  rule ordering, and a refused action must be greppable in evidence.*
- **[CTL-5]** The executor answers every re-entry from the occurrence ledger without
  re-dispatching, appends one step event per occurrence, and runs under a fixed monotonic
  body deadline — `src/benchweave/control/executor.py`. Capture occurrences join the
  mint-retained-invalidated id mold (issue #176 increment 2): the host-minted
  `cap:{run_id}:{step_id}{.index-suffix}` id is retained in the ledger entry's
  `issued_ids` and invalidated when the capture's operation does not succeed — a failed
  or policy-denied capture can never leave a live id behind. *A06: physical work is never
  repeated because its acknowledgement was lost; the ledger is the only "did this happen"
  authority.*
- **[CTL-6]** Every invoke input, every write value and every read parameter flows through
  `resolve_value` BEFORE the policy check and before dispatch; `$stg_ref` resolves as an
  RFC 6901 pointer with exact types against earlier successful results only — `executor.py`
  `resolve_value`. *Values the policy checked are the values that get dispatched, and a
  reference cannot smuggle type coercion past admission.*
- **[CTL-7]** Semantic admission enforces step-ID uniqueness across the whole procedure
  (nested blocks included) and lexical scoping of result references: a step may reference
  an earlier sibling of its own block or the visible prefix inherited from enclosing
  blocks — never a later sibling, never itself, never a step inside a branch body from
  outside it, never a repeat iteration's results from outside the loop or from another
  iteration. `$stg_issue` appears only at invoke input keys the role's device descriptor
  marks issued for that exact action. Capture steps carry literals only (the corpus's
  closed branch admits no reference positions), and their admission-time descriptor
  mirror refuses `capture_undeclared:` when the bound device does not declare
  `artifact_writer` with `capture_formats`/`capture_limits`, a declared format, or limits
  covering the requested `sample_count`/`max_bytes` —
  `src/benchweave/control/semantics.py`. *Scoping is what makes a bounded, reviewable
  procedure language out of JSON (A12); a reference that can see sideways or forwards is
  an unreviewable one, and a capture an unqualified device cannot serve is refused at
  admission rather than at dispatch.*
- **[CTL-8]** Monitoring wraps every plugin dispatch with a tick before and after, slices
  every monotonic wait at the bench poll cadence, and stays single-threaded and
  deterministic on the injected clocks. A condition violation during the body blocks the
  NEXT dispatch as a protective failure (the body ends `tripped`); a cancellation in the
  accepted-but-dispatchable window blocks it the same way (`cancelled`) —
  `src/benchweave/control/coordinator.py`. *A violation must never be observed and then
  worked around; it ends the body.*
- **[CTL-9]** One coordinator owns one run end to end — idempotent request acceptance,
  semantic admission, the run lease, run creation, monitored body, protective transition on
  ANY body end, terminal record, durable events, lease release. A run found at recovery
  records `interrupted`; it never fabricates a terminal outcome, and the protective
  transition still applies — `coordinator.py`, pinned by `tests/faults/`
  (`test_protection.py`, `test_state_recovery.py`). *A12: all endings require the approved
  safe transition; terminal pass requires verified final safety. An interrupted run
  reported as anything else is a lie in the evidence record.*

## State & persistence invariants

- **[STO-1]** The store is single-writer SQLite — WAL journal, `synchronous=FULL`,
  explicit transactions. Timestamps are caller-supplied (no clock reads) and no device,
  network or plugin I/O lives in the store — `src/benchweave/state/store.py`. *Determinism
  and testability: anything that can read a clock or a socket cannot be replayed.*
- **[STO-2]** Sequence authorities (per-bench lease sequence, per-stream event sequence)
  are assigned under `BEGIN IMMEDIATE`, making them monotonic and gap-free by construction
  — `store.py`. *Event-stream consumers can rely on "no number was ever skipped or
  reused"; a gap-free sequence is what makes a missing event detectable as a fault rather
  than an artifact.*
- **[STO-3]** One coordinator per store file, enforced by an exclusive `flock` on
  `<db>.hold`: live gateways hold it for their app lifespan; at-rest commands (backup,
  restore) acquire the same lock and REFUSE, naming the holder, while a live coordinator
  owns it. The lock itself — never the lockfile body — is the truth —
  `src/benchweave/state/hold.py`. *A03's one-active-procedure rule needs exactly one
  writer; `flock` dies with the process, so a crashed gateway can never leave a false
  "held" behind.*
- **[STO-4]** The run's bench lease is held as `run:{run_id}` with expiry =
  acceptance + max_body + max_protection; binding takes `expires_at` and `now_wall` as
  caller-supplied values and never reads a clock — `src/benchweave/control/binding.py`,
  `coordinator.py`. *A04: bounded continuity is arithmetic on declared values, not on
  ambient time; the run's authority expires exactly when its declared budget does.*

## Contracts & standards invariants

- **[CON-1]** Every admission input is decoded with the exact-byte JSON decoder and
  digest-verified (`expected_sha256`, `max_bytes`) before any schema validation; rejections
  carry machine-matchable prefixes (`schema:`, `digest_mismatch:`, `pin_absent:`) —
  `src/benchweave/control/documents.py` `AdmissionRejected`,
  `src/benchweave/content/json_document.py` `load_document`. *A14: the interface preserves
  original document bytes for digest verification — validation operates on the bytes that
  were pinned, not on a re-serialization of them.*
  Amendment (2026-09-19, issue #63): device descriptors — previously "no vendored schema,
  minimal structural check" — now validate against the **active vendored OTDP descriptor
  schema** at admission (packaged-first via `contract_family`, active version derived from
  the vendored standards manifest, never a hardcoded gateway constant; the schema's
  `otdp_version` const enforces corpus alignment). Exact-byte decode and digest pins
  unchanged; see CON-10 for the projection.
  Amendment (2026-09-20, issue #85): startup/bootstrap joins execution and recovery as the
  third admission caller — `bootstrap.admit_fixture_lattice` (the recovery path's
  resolution+admission body, extracted) runs before any store write, so a lattice that
  fails admission refuses gateway startup (`startup_admission_rejected:` carries the typed
  prefixes; uvicorn fails the lifespan) leaving the store untouched — no bench row, no
  device row, no content row, no generation bump. Device rows iterate the bench's pinned
  set through the CON-10 projection (descriptor-id keying preserved); the descriptor
  family stays cache-only in the content store and meets the gate when a binding pins it.
  Amendment (2026-09-23, issue #147 increment 3): descriptor admission gains the provider
  rows — the census mirror (`_check_provider_mirror`, the SDK's five refusals
  refusal-for-refusal and in order, over the two-layer known-features union:
  corpus-derived layer 1 swept from the vendored tree + host-admitted layer 2 — the
  union serves the `unknown_otdp_feature:` closure ONLY; admission proof is the
  triple row below, which never consults the union), the
  descriptor-relative pin verification (`_verify_provider_pin`: strict no-follow, hash,
  exact-byte decode — strict UTF-8, BOM/UTF-16 refused there — the vendored provider
  schema resolved manifest-derived, grammar meta-validation, kind uniqueness,
  reserved-seven disjointness, the identity equalities plus the declaration-agreement
  pair), and the gateway-only admission row (`provider_not_admitted:`: exact triple,
  approval expiry judged against a caller-supplied `now_wall` — A04 arithmetic, a missing
  `now_wall` refuses — and the S12-extended `connection_key` binding). The
  machine-matchable refusal set gains the six SDK prefixes riding inside the existing
  family prefixes (`provider_transport_undeclared:`, `provider_feature_missing:`,
  `unknown_otdp_feature:`, `provider_contract_missing:`,
  `provider_contract_hash_mismatch:`, `provider_contract_invalid:`) plus the
  gateway-owned `provider_not_admitted:`. Provider documents and the operator's
  `transport-settings.json` (validated before any descriptor is projected, identity-only
  by schema — `src/benchweave/control/provider_settings.py`) decode through the
  exact-byte decoder; the settings validator's own prefixes (`settings_schema:`,
  `settings_digest_mismatch:`) join the same list.
- **[CON-2]** The digest pin lattice between the execution-contract documents is verified
  at admission; the fixture lattice moves in lockstep (`fixtures/registry/` ↔
  `scripts/registry/build_fixtures.py` ↔ `catalogue.json` ↔ the digest-pinning tests),
  pinned by `tests/contract/test_registry_fixtures.py`. *A pin that lags the bytes it names
  is silent drift: yesterday's guarantees presented as today's.*
- **[CON-3]** The 17 MCP tools are vendored-exact: each registered via
  `mcp.tool(fn, name=..., description=...)` with `parameters`/`output_schema`/annotations
  pinned to the vendored corpus verbatim; the function signature remains only the callable.
  fastmcp signature inference must never define the wire schema (pydantic never emits an
  empty `required` and unconditionally prunes unreferenced `$defs`) —
  `src/benchweave/interfaces/mcp.py`. *The vendored `mcp-tools.json` is the authority
  (A09); schema inference drift would put the gateway out of conformance with its own
  standard.*
- **[CON-4]** Vendored trees resolve packaged-first (`benchweave/_vendored/` via hatch
  `force-include`), dev-checkout fallback — one source of truth, no copies under `src/` —
  `src/benchweave/vendoring.py`; `make check-sdk-standards` (CI `gates` job) refuses drift
  between the main-repo standards, the SDK lock and the vendored tree. *Two copies of a
  standard disagree the moment one is edited; the check keeps the disagreement out of
  `main`.*
  Amendment (2026-09-23, issue #158): the same gate carries the manifest
  `sdk_compatibility` mirror ↔ SDK-lock comparison (CON-12) — the mirror is
  a derived copy whose authority stays with the lock.
- **[CON-5]** REST v1 and MCP share typed operation/result contracts and durable core run
  identity (A13: 20 REST operations, 17 MCP tools — three administration operations are
  REST-only by design). Transport adapters are adapters: behavior is pinned against the
  frozen contract (`standards/interface/0.1.0/interface-contract.md`), never against the
  sibling transport. *The WP07 lesson: a parity suite that compares REST to MCP proves
  only transport symmetry — both can carry the same wrong behavior invisibly.*
- **[CON-6]** MCP auth is fail-closed at two layers — an `StgTokenVerifier` (FastMCP
  `TokenVerifier` over `benchweave.interfaces.identity.validate`) plus the layer beneath
  it — `src/benchweave/interfaces/mcp.py`. *An auth gap on the tool surface hands a caller
  the bench.*
- **[CON-7]** Corpus-manifest sha256 rows are machine-rewritten only by
  `benchweave.standards repin`, which rewrites existing rows' digests, never rows
  themselves (`path`/`source` byte-preserved, byte-identical formatter), refuses
  structural surprises fail-closed before any write, and verifies-but-never-rewrites
  superseded-version rows — `src/benchweave/standards/repin.py`, pinned by
  `tests/standards/test_repin.py`. *Without it, the next contributor's fastest path is
  another hand-splice, and the frozen-row guarantee lives only in prose.*
  Amendment (2026-09-23, the devstage design record): corpus rows carry a third
  fate — **dev** (repin-mutable while a head is open: the head's `standards/`
  paths join the regenerable set, so the edit → repin loop is the accumulation
  flow), deleted with their directory at promotion or abandonment. The
  "machine-rewritten only by repin" clause and the superseded-row freeze are
  unchanged. A dev row whose block is gone classifies frozen (the
  orphan-teardown catch); a leftover block after promotion refuses at load
  (`dev_target_not_greater`; the class-escalated form `dev_head_stale`); the
  active entry's version must be pure semver
  (`standards_entry_version_invalid`) — a `-dev` suffix there would add a
  release directory the train-window collector cannot count.
- **[CON-8]** The corpus identity block is closed-world and derived-checked against
  its machine authorities at every export/check — an unknown key is refused
  (`identity_key_unknown`; a new key is a standards-governance event, not an
  additive edit), `adapter_api` must equal the active OTDP descriptor schema's
  `$defs.adapter.properties.api_version` const (absence fails
  `identity_adapter_api_absent`; disagreement or a missing const fails
  `identity_adapter_api_mismatch`), and each standards-manifest id among
  otdp/registry/execution/interface must be declared in the block at exactly that
  manifest's version, with a standard the manifest does not carry refused
  (`identity_standard_absent` / `identity_standard_mismatch`) —
  `src/benchweave/standards/manifest.py` `validate_identity`, wired once in
  `export.py:export_bundle` after `validate_manifest`, with duplicate standard ids
  structurally unrepresentable past `load_manifest` (`standards_entry_duplicate`).
  The authorities are the schema const and the standards manifest; the identity block
  is a declaration that is verified, never trusted. *Without it the identity block
  stays decorative and the next reset sweep re-creates prose-vs-machine version drift
  main-side (issue #44: three doc surfaces carried a stale adapter API version with
  every gate green).*

- **[CON-9]** Derived-variable evaluation is a pure post-dispatch function of
  the plugin-returned dataset and the digest-pinned descriptor declaration:
  it never mutates plugin-returned data, never re-dispatches, appends
  variables carrying the closed `derivation` marker (expression + operand
  ids, verified against the parse — a forged marker refuses), emits
  structurally-unknown uncertainty and calibration, degrades elementwise
  failures (null operands, division by zero, non-finite results) as
  in-band partial/invalid variables with `null` elements — never
  `inf`/`NaN` — emits unresolved operands as invalid variables with EMPTY
  values (no element is fabricated for a shape that was never
  established) — and treats structural contradictions
  (derived-id collision, malformed or duplicate-variable-id dataset,
  dtype/shape disagreement, and `+`/`-` unit mismatch between
  identifier-leaf operand pairs — sub-expression and literal operands
  carry no trackable unit) as step failures (`DERIVATION_INVALID`, body `execution_error`, raw
  dataset kept in scope) — `src/benchweave/measurement/derivation.py`,
  `control/documents.py _check_descriptor`, `control/executor.py
  _apply_derivation`, pinned by `tests/unit/test_derivation.py`,
  `tests/faults/test_derivation_faults.py`,
  `tests/control/test_documents_derivation.py`,
  `tests/control/test_executor_derivation.py`, and the census execution in
  `scripts/architecture/check_devices.py`. *M15/S19; A02 (unknown is not
  fabricated qualification), A06 (loud structural refusal, in-band quality
  loss), A12 (declaration order is the evaluation order — the admission
  acyclicity check makes it total).*

- **[CON-10]** One descriptor dialect, projected (2026-09-19, issue #63): a device
  descriptor is a full-form OTDP document; execution admission validates it against
  the active vendored OTDP schema plus the S01/S02 semantic mirrors (the SDK's
  checks mirrored at the gateway — the SDK is not a gateway dependency, REG-4's
  read-not-import pattern), validates the gateway-owned `x-stg-issued-inputs`
  extension (shape, declared actions, and fields the target action itself
  declares in `input_constraints.properties` — an action with no declared
  properties names no issuable fields; refusal prefix `issued_map:`), and
  projects a total execution view (`{id, version = descriptor_version, profiles
  (absent → []), parameter names, actions + issued, derived_variables
  passthrough, artifact_writer permission flag, capture_formats/capture_limits
  when the descriptor carries BOTH capture keys — the projection's
  both-or-neither conjunction, not a schema-forced pairing: OTDP 0.2.2
  requires the pair only under the `capture` capability, so a half-declared
  surface is schema-legal and the gateway's conservative choice projects
  nothing}`) that binding, semantics and the
  coordinator read; the bench pin
  verifies against the RAW document's `id`/`descriptor_version` and the raw bytes'
  digest — `src/benchweave/control/documents.py` `_project_descriptor`. The slim
  list dialect (`id`/`version`/string-lists) is refused: `check`-clean is a
  necessary condition for admissibility. Gateway admission and `benchweave-sdk
  check` are pinned equivalent over the in-tree descriptor corpus × mutation
  matrix by `tests/sdk/test_descriptor_equivalence.py`, whose two sanctioned
  gateway-stricter cells are named there (the x- key, ignorable by contract, and
  the S02 array-form range the SDK's dict-only branch cannot reach on 0.2.0-valid
  documents); the census covers that corpus and matrix, not all possible
  descriptors. *Two gates built against two notions of "a descriptor" with no
  shared authority is how zero of four in-tree descriptors were both check-clean
  and admissible (#63 §1); one dialect plus a projection is the structural fix,
  and sim_scope admitting with zero byte changes was the proof the mechanism,
  not a rewrite, closed the fork.*
  Amendment (2026-09-23, issue #147 increment 3): the equivalence census extends to the
  provider lattice (the record §4 metric-1 fixtures: 4 valid + 8 single-fault, both legs
  in-process), and the sanctioned gateway-stricter cells grow to FOUR, each named in the
  census module docstring — `issued_map:`; `provider_not_admitted:` (admission is
  gateway-only: the SDK cannot see commissioned state, so no offline prefix exists);
  the strict-UTF-8 decode (a BOM'd or UTF-16 provider document whose pin covers its
  bytes is SDK-clean and gateway `invalid_json` inside `provider_contract_invalid:`);
  and the duplicate-key decode (a contract whose bytes carry a duplicate key is
  SDK-clean under `json.loads`'s last-value collapse and gateway-refused by the
  exact-byte decoder's `duplicate_key` gate — gateway-stricter is the honest
  direction: the reviewed bytes are the pinned bytes). Two alignment notes: the
  provider-pin read cap mirrors the SDK's 262144-byte bounded-read `INPUT_BYTE_LIMIT`
  (pinned equal across lanes; before the mirror the size window (262144, 1048576]
  admitted gateway-side only), and symlinked ANCESTORS of the descriptor's package
  are an environment-conditional divergence (the SDK's no-follow reader refuses them;
  the gateway checks sub-package segments — both hold strict no-follow inside the
  package).
  A set-equality arm pins the gateway's corpus-known feature derivation equal to the
  SDK's at the same vendored version (layer 1 of the two-layer union cannot drift
  silently). The projection itself is UNCHANGED: transport and provider stay
  unprojected; the grant seam (`build_capture_services`) re-derives the raw form by
  digest exactly as the permissions precedent does.

- **[CON-11]** The active OTDP validation report
  (`standards/otdp/0.2.0/validation-report.md`) is machine-written by its own
  validator (`render_report` in `scripts/architecture/check_devices.py`; the
  author-side path `--write-report` refuses to write when any check fails and
  the pytest harness cannot reach it — `runpy.run_path` executes the module
  body, never the `__main__` block) and byte-pinned to a live devices-suite
  run by `tests/contracts/test_architecture.py::test_validation_report_matches_live_run`
  (sorted rendering, so the pinned bytes are a function of the check set only,
  not platform glob order; three tamper cases prove the comparison detects a
  flipped line, a reordered check list, and a bumped headline, and the
  `docs/README.md` row is tied to
  the headline count). Superseded versions' reports are frozen historical
  evidence, never regenerated. *A hand-transcribed count beside the corpus it
  claims to verify is an assertion; before the pin, in-place edits to the
  report landed gate-free (tier-2 prose is not digest-pinned by design —
  exactly the hole for a report that carries a measured count). The pin does
  not catch in-prose numbers ("Twelve class profiles", "fifty … contracts")
  drifting while the check lines stay right — that residual is deferred and
  review-guarded.*

  *Amendment (#102 D1):* the machine-written report family now covers the
  four standards suites — OTDP (`check_devices.py`), registry, execution,
  interface — and the closure docs-surface report
  (`docs/acceptance/validation-report.md` via `check_closure.py`). Each is
  written only by its own validator's `--write-report` epilogue (the shared
  module `scripts/architecture/_validation_report.py`; refuses on any
  failing check; structurally unreachable from the `runpy` harness — the
  argv gate sits in each script's `__main__` block, and `runpy.run_path`
  executes the module body with `__name__ == "<run_path>"`, so the harness
  never enters it. Residual: the shared MODULE is directly callable — the
  refuse pin itself calls `main()` — and refuse-on-red is the guard on
  that path) and byte-pinned to a
  live sorted render by the parametrized
  `test_validation_report_matches_live_run` and tamper arms. In-prose counts
  are now DERIVED from the values the suite computes (f-strings over
  `len(profile_map)`/`len(covered)`, the named schema tuples, `len(vec)`,
  the closure scenario-count variables) — the residual disclosed above is
  closed. Check names must stay path-portable (no absolute tree roots —
  `test_check_names_are_path_portable` anchors it), because sorted-render
  byte equality is only sound over host-independent names.
  `standards/plugin-ui/*/validation-report.md` are train evidence records,
  not suite renderings, and stay hand-committed historical evidence by
  design (issue #102 D1 design record §10: no checks-list substrate, the
  substance is not recomputable, and the live claims are already pinned by
  the pytest suites in gates).

- **[CON-12]** The compatibility-matrix render is a pure function of committed
  state — no remote URL, no submodule init or working-tree state enters it;
  the manifest's `sdk_compatibility` mirror equals the `compatibility` block
  of the SDK lock at the pinned gitlink commit — enforced wherever the
  submodule working tree sits at that pin (CI both lanes); a working tree
  away from the pin is refused by name before any comparison, never mirrored
  from — and the render fails closed rather than degrading when a committed
  source is absent — `src/benchweave/standards/matrix.py` `render_matrix` (rows from
  the standards manifest, SDK version/range/notes from the mirrored
  `sdk_compatibility` block, Sources from `pyproject.toml`
  `[project.urls] Repository` and the committed `.gitmodules`), the mirror
  comparison in `src/benchweave/standards/check.py` `run_check`
  (`sdk_compatibility_drift`), pinned by `tests/standards/test_matrix.py`
  and `tests/standards/test_check.py`. *A staleness gate that renders
  working-tree or remote state reds on correct committed files and teaches
  its readers to ignore it or "fix" it by committing checkout-state bytes
  (issue #158: a fork's `matrix --check` failed on a correct file, fork
  regeneration poisoned the Sources cells, and a moved submodule working
  tree reds the maintainer's own clone).*

## Registry & plugin invariants

- **[REG-1]** A plugin is imported with no side effects, then explicitly opened with a
  scoped `HostServices` instance, then dispatched against with typed requests carrying
  monotonic deadlines — `src/benchweave/host/plugin.py` `DevicePlugin`. *A05: trusted
  plugins are still contained by lifecycle; import-time work escapes every gate that
  follows.*
- **[REG-2]** The timeout-after-dispatch rule: when a deadline passes, the plugin reports
  TIMEOUT with dispatch state DISPATCHED or UNKNOWN — never silently retries, and never
  claims `not_dispatched` for work already sent — `host/plugin.py`. *A06 made explicit:
  the ambiguity is preserved, not laundered into a clean answer.*
  Amendment (2026-09-19, issue #63, R1 from #66): dispatch-state honesty is a typing
  boundary too — `not_dispatched` is reserved for failures that precede any device
  evaluation, and an argument that violates its action's input typing (the profile
  catalog types the field) never reaches device evaluation: a wrong-typed argument can
  never yield `DEVICE_REJECTED`. A well-typed argument rejected against device state or
  envelope stays `DEVICE_REJECTED`/`dispatched`. Pinned by the sim_psu fault matrix
  (`write_wrong_type_invalid_framing`, `invoke_measure/output_nonstring_token_*`).
- **[REG-3]** Registry admission pins the complete dependency closure; publication and
  installation never authorize control (A11) — `src/benchweave/registry/admission.py`,
  pinned by `tests/contract/test_registry_admission.py`. *A downloaded package is data
  until commissioned locally; an install path that grants authority is the whole security
  model inverted.*
- **[REG-4]** The gateway's OTDP adapter mirror is pinned three-way in every CI run —
  expected literals ↔ the pinned SDK submodule's protocol
  (`packages/sdk/src/benchweave_sdk/interfaces.py`) ↔ gateway code
  (`src/benchweave/host/otdp_bridge.py`: `_Context`, the AST-extracted `self._adapter`
  call set, the enforced envelope key sets) ↔ the active corpus schema (`$defs`
  envelopes and the four vocabularies in `src/benchweave/host/types.py`) — by
  `tests/sdk/test_adapter_agreement.py`, whose documented gaps (the HostServices
  transport/evidence members, CaptureServices, dataset_id, the error
  `^x-` extension-key delta) carry their own presence assertions so silent narrowing
  becomes a visible diff. Structure only, not semantics: names, arity,
  keyword-only-ness, coroutine-ness, key/enum sets. *The hand-mirror is otherwise
  checked only at release smoke (the installed distribution), so protocol-shape drift
  between the two repos is invisible in CI until this pin.*

---

## Known open wounds

Some invariants sit next to known-imperfect code. Track the individual issue in the repo
tracker and cite it in review rather than building a consolidated weakness list here — a
one-stop map is more useful to an attacker than to a reviewer, who is only ever looking at
one diff. If a PR touches a wound, fix it or at least do not widen it, and say which.
