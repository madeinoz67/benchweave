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
  `<db>.hold`: live gateways hold it for their app lifespan; every StoreHold site —
  the gateway itself, setup, report, retention (read-only), dispose (write), backup,
  restore — acquires
  the same lock and REFUSE, naming the holder, while a live coordinator
  owns it. The lock itself — never the lockfile body — is the truth —
  `src/benchweave/state/hold.py`. *A03's one-active-procedure rule needs exactly one
  writer; `flock` dies with the process, so a crashed gateway can never leave a false
  "held" behind.*
- **[STO-4]** The run's bench lease is held as `run:{run_id}` with expiry =
  acceptance + max_body + max_protection; binding takes `expires_at` and `now_wall` as
  caller-supplied values and never reads a clock — `src/benchweave/control/binding.py`,
  `coordinator.py`. *A04: bounded continuity is arithmetic on declared values, not on
  ambient time; the run's authority expires exactly when its declared budget does.*
- **[STO-5]** Every disposition execution is ONE `BEGIN IMMEDIATE` transaction
  carrying its complete audit record — the invocation row, one audit row per disposed
  governed row (its decision envelope canonical-JSON content-addressed through
  `put_artifact` inside the same transaction, digest pinned in the row), the guarded
  exact-row deletions (rowcount-checked), and reference-checked artifact GC (live
  references: `evidence.artifact_id`, `capture_staging.artifact_id`,
  `dispositions.decision_artifact_id` — the historical `deleted_artifact_id` is a
  record, never a reference). A committed deletion without its audit row is
  unrepresentable; `review`-tier rows are never deleted; the
  dispositions tables have no delete path — `src/benchweave/state/dispositions.py`,
  `src/benchweave/cli/dispose.py`, pinned by `tests/cli/test_dispose.py` +
  `tests/faults/test_disposition_faults.py`. *Decision 8's sequencing invariant and
  A07 made structural: audit capacity is not a dependent of the action, it is the
  action's transaction.*
  Amendment (2026-09-25, issue #199 — the archive tier): the outcome vocabulary
  gains `'archived'`, and the ONE transaction covers both tiers of a mixed
  invocation (a crash or refusal disposes nothing of either). An archived row's
  envelope carries the four archive fields (`archived_artifact_id`,
  `archived_byte_length`, `archive_destination`, `archive_verified_at`) **iff**
  its outcome is `'archived'` (the two-shape rule: delete-tier envelopes stay
  byte-identical to v6's 19-field canonical form; one field-set derivation shared
  by writer and recomputation). `deleted_artifact_id` is NULL and
  `deleted_byte_length` 0 on archived rows (nothing was destroyed), and
  `archived_artifact_id` is a **record, never a live reference** — the archived
  twin of `deleted_artifact_id`'s grammar: counting it in the GC would keep every
  archived artifact in the store forever and defeat the move. Archived rows are
  still deleted from their governed tables by the same guarded deletes (archive
  relieves the G3 ledger exactly like delete); only with `--archive-target` does
  an overdue archive-tier row execute — without one it stays `blocked_archive`,
  never deleted.
- **[STO-6]** An archival disposition stages every archived object at the
  destination and re-verifies it against its content address — re-read from the
  destination, fsynced — BEFORE the store transaction opens; a crash may leave
  the destination over-preserved (verified objects no committed trail row
  references), never the trail referencing bytes not verified present at the
  destination by the executing process; re-runs are idempotent
  (content-addressed objects verify-and-skip; committed rows cannot be
  re-selected) — `src/benchweave/cli/dispose.py` (`_stage_archive_objects`,
  `_place_object`, `_write_archive_manifest`), pinned by
  `tests/cli/test_dispose.py` + `tests/faults/test_disposition_faults.py`.
  *Why: the offline filesystem is outside the SQLite transaction, so ordering —
  not atomicity — is what makes the move's crash story honest; A06's
  evidence-over-assertion applied to a filesystem claim. Boundary (disclosed):
  the trail proves the copy at `archive_verified_at`, not destination health
  afterwards — `--verify-archive` re-proves on demand; destination-byte
  verification never trusts a write syscall's return or the trail's recorded
  length.*

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
  Amendment (2026-09-26, issue #215, parent #203): under multi-version serving the
  descriptor's own `otdp_version` pin selects the vendored schema — the pin's bytes,
  not the active's — resolved from the CARRIED set (retained ∧ in-range; a yanked
  pin stays conforming, so the resolution domain is the carried set, never the
  served set). LANDED NOW on the SDK side: `benchweave_sdk.validate_descriptor`
  validates a pinned descriptor against the pinned version's digest-verified
  bytes; a pin outside the carried set refuses `version_not_served:` carrying the
  five VR-37 fields; a retired identifier refuses `retired_identifier:` (distinct
  from `version_unknown:`); a yanked pin validates with a deprecation warning
  naming the derived move-to. The same per-pin selection at GATEWAY admission
  (`control/documents.py`, whose descriptor validator is active-only at this
  slice) lands with slice 3 and becomes true then (CON-12's disclosure style;
  design §4 Slice 3 names it) — at this slice a 0.2.0-pinned descriptor is
  SDK-validate-clean and gateway-refused by the ACTIVE schema's const. Exact-byte
  decode, digest pins, and every existing prefix unchanged.
  Amendment (2026-09-27, issue #217 — slice 3 LANDED): the gateway half is true
  now — `_descriptor_validator(version)` resolves the pin's own digest-verified
  bytes (cache keyed by corpus directory + schema filename); classification is
  the Q6 table (`classify_descriptor_pin`: served → conforming; yanked →
  conforming with the recorded deprecation warning naming the derived move-to;
  retained-out-of-range → non-conforming, loaded only behind a recorded
  per-device operator acknowledgement naming that pin — the refusal carrying
  `operator_ack_required:` with `standard_nonconforming:` and the five VR-37
  fields; retired/never-carried → `retired_identifier:` / `version_unknown:`).
  The gateway deliberately splits the SDK's `version_not_served:` fold three
  ways (the resolver's documented convergence); the census pins the split. The
  pairwise bench check refuses a device outside the bench's execution version's
  declared cross-constraint range (`cross_constraint_violation:`, naming both
  versions and the row's evidence) — an ack authorises the otdp-window load,
  never the execution runtime interface. `AdmittedDocuments.pins` is the
  admission-record surface; run evidence carries the pins + classes as the
  run stream's first event (`devices_pinned`, digest-covered by the terminal
  record's `events:{run_id}` ref — the run-record document itself is
  schema-frozen); the API view derives the class at the projection and logs a
  non-conforming derivation server-side (the wire's device object is
  contract-closed; the wire field lands with the next interface bump).
  Amendment (2026-09-28, issue #220, parent #203 slice 6): under
  per-document execution pinning, the bench document's own
  `contract_version` selects the vendored execution corpus version all
  five documents validate against — the pin's digest-verified bytes,
  never the ambient composition's (the descriptor lane's VR-13 rule
  applied to the lattice; classification is the same Q6 table re-keyed to
  `standard="execution"`, the standard riding the classification cache
  key so otdp and execution never share an entry). The Q6 classes and
  prefixes apply verbatim (`version_unknown:` / `retired_identifier:` /
  `standard_nonconforming:` with the five VR-37 fields); a non-conforming
  execution pin refuses OUTRIGHT — the acknowledgement authorises
  otdp-window loads, never the execution runtime interface — and an
  unclassifiable pin keeps the composition posture (the schema's own
  const error names it). The pairwise cross-constraint check reads the
  BENCH'S PINNED version, not the composition directory's name (a
  version with no row constrains nothing it has no evidence for).
  Running is a composition-version fact, not the pin's: a run start over
  a non-active-pinned lattice refuses `execution_version_not_runnable:`
  before any device plan or bridge is constructed (the terminal record's
  `contract_version` is the record lane's literal — E1 threads it); a
  pinned-old lattice still validates and loads at startup (the
  procedure-author story). Exact-byte decode, digest pins, and every
  existing prefix unchanged.
  Amendment (2026-09-29, issue #260, the record lane — superseding the
  #220 amendment's "Running is a composition-version fact" sentence
  in-place above; append-only history): Running is an
  IMPLEMENTED-DIALECT fact, not a composition-VERSION fact — the
  composition's cross-constraint row governs every run's device pins
  whatever the lattice pins (`_check_run_floor`, two layers one rule one
  vocabulary: the §5 seam pre-check is the wire-visible early refusal,
  best-effort over stored documents, the worker check over the full
  admission result is authoritative; both call the one helper; a
  rowless composition asserts no floor — the honest negative per-version,
  admission's own doctrine extended to running). Terminal records carry
  the run's own validated execution version, stamped from and validated
  against the PINNED version's digest-verified run-record schema
  (`_versioned_schema_path` — the corpus row exists for both served
  versions; the const-stamp derivation generalizes from the composition's
  schema to the version's schema, and a differing lattice version rides
  the record's reasons as `implementation_disclosure:`). Recovery
  terminalizes era runs against their own version — doc-first (the stored
  binding document's const, digest-pinned bytes), echo-judged fallback
  when the doc is absent (carried dialects thread, caller data does not),
  disagreement and unjudgeable doc const contained under
  `recovery_execution_version_unresolved:` with NO record;
  `recovery_execution_version_not_runnable:` retires with the skip that
  emitted it and `execution_version_not_runnable:` retires with the guard
  that emitted it. CTL-9 unchanged: era records are
  `interrupted`/`unknown`; recovery never resumes bodies, never
  dispatches.
  Fold clarification (2026-09-29, issue #260 fold): the containment
  denominator is {doc/echo disagreement, an unjudgeable OR const-less doc
  const, or a terminalization failure (per-run, never startup)}. The
  doc-absent echo is judged THREE ways: carried → the era record;
  retired-but-RETAINED → the era record stamped from the retained bytes
  (a later retirement neither flips an era run to a composition stamp nor
  wedges it — copy-never-move keeps the directory); no retained bytes →
  caller data, the composition record exactly as before. The
  doc-resolved path stamps the record's binding block FROM THE DOCUMENT,
  so a record self-consistently names one artifact and a disagreeing
  carried echo rides as `implementation_disclosure:`, not as a silent
  contradiction. The seam's classification refusal (step 2) is DECIDED —
  `_refuse_execution_pin` fires it at the POST — and the floor shape-gates
  every raw pin before the interval comparator (typed-or-pass, never
  ValueError).
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
  Amendment (2026-09-26, issue #215, parent #203): the round-trip gate additionally refuses
  served-set disagreement (`served_set_drift:`) and dependency-policy mirror disagreement
  (`policy_mirror_drift:`) across manifest ↔ export ↔ SDK lock ↔ vendored tree, offline on both
  sides. The SDK-side load path carries the same discipline inward: every document the SDK
  serves is digest-checked against its lock row at load — planted or unrecorded vendored bytes
  refuse `vendored_digest_mismatch:` by name (issue #215 fix F1, wiring design §3.2's
  digest-checked load); a lock row whose vendored directory is missing refuses
  `served_set_drift:` instead of crashing the import. The gateway-side export/check path
  carries the mirror of the same discipline for the corpus itself: every carried
  version's corpus rows are compared against their corpus pins and a mismatch refuses
  `corpus_pin_mismatch:` (#215 fold-wave F-B) — a tampered superseded version can no
  longer export clean with the tampered digest as its authority.
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
  Amendment (2026-10-01, issue #288 M1+M2): the promotion sweep's line
  rules are RULES, not tokens — admission is identity-residual equality
  (the same line with its version-like substrings moved), a VERIFIED
  PAIRED digest re-stamp (every digest on the line names a real file of
  the right tree AND, when the positional counterpart line also carries
  digests, the same relative path on both sides of the pair), or the
  sanctioned `validation-report.md` regeneration; CONTAINING a transition
  token admits nothing (the tokens are remediation vocabulary only).
  The no-record trigger gains its object-store derivation alongside the
  `-dev` citation: a retained version whose introducing commit's parent
  declared the standard's dev head at exactly `<version>-dev` requires
  its record even when the corpus rows cite a released predecessor (the
  laundered source); unresolvable history refuses
  `promotion_history_unavailable:` rather than silently passing, and a
  root that is not a git repository has no history to consult (the
  current-tree derivation governs there).
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
  Amendment (2026-09-26, issue #215, parent #203): the identity block's
  authority and active-entry derivation are UNCHANGED. The served-set
  admission the design once named for `validate_manifest` is carried by its
  real mechanisms, not that function — `validate_manifest` pin-checks only the
  ACTIVE and dev normative paths, deliberately: its `repin.py` caller must keep
  admitting the tree repin is about to rewrite. The carriers are the
  export-time `validate_dependency_policy` (policy block against the retained
  tree: unresolved yank/retired entries, retired-active conflicts, and status
  conflicts refuse with `policy_*` prefixes), the export/check-time
  `validate_carried_corpus_pins` (every carried version's corpus rows against
  their pins; a mismatch refuses `corpus_pin_mismatch:` — #215 fold-wave F-B),
  the per-CARRIED-(id, version) row enumeration in `export_bundle`, and the
  bundle-bytes-to-pins pin
  `tests/standards/test_export.py::test_bundle_served_rows_match_corpus_digests`.
  Declarations verified, never trusted — unchanged.

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
  Amendment (2026-09-26, issue #215, parent #203): "the active vendored OTDP schema" reads "the
  vendored OTDP schema of the descriptor's pinned carried version" wherever admission resolves
  it (carried, not served — a yanked pin resolves its schema too); the projection itself is
  unchanged; the equivalence census extends across the served set
  (clean cells + named faults per served version; the 28-cell mutation matrix remains
  active-version); the sanctioned gateway-stricter cells are unchanged and re-pinned per served
  version where they are version-sensitive (the strict-UTF-8 and duplicate-key decode cells are
  version-independent by mechanism). This amendment lands with slice 3 and becomes true
  then (CON-12's disclosure style; design §4 Slice 3 names it) — at this slice gateway
  admission still resolves the ACTIVE schema only and the census pins the active version;
  the slice-1 mechanism that IS landed is the SDK-side per-pin validation (CON-1's
  amendment).
  Amendment (2026-09-27, issue #217 — slice 3 LANDED): the census sweeps the
  served set on both lanes (34 clean cells over the native example sets of
  {0.2.0, 0.2.2}, per-version id-pattern fault arms, the 0.1.2 prefix-split
  cell, and a teeth arm re-deriving the pre-slice ACTIVE-const refusal);
  gateway admission resolves the PIN's schema (CON-1's landing note above);
  the 28-cell mutation matrix stays ACTIVE-version; the dialect test
  (`tests/contract/test_plugin_descriptor_dialect.py`) goes within-range
  (`lock == descriptor == a-served-pin`, VR-45) with the retired `== active`
  form kept visibly failing against an advanced fixture.

- **[CON-11]** The OTDP validation report of the active version — its path is
  derived, never hardcoded: the live pin resolves
  `standards/otdp/<active>/validation-report.md` from the standards manifest
  (`_active_standard_dir`) — is machine-written by its own
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

  *Amendment (2026-09-24, issue #187 class closure): the lock's
  `compatibility.sdk` is itself anchored — it must equal the pinned SDK's
  own `pyproject.toml` version. Amendment (2026-09-25, in-fold mechanism
  upgrade): the version is read from the PINNED COMMIT's bytes via git
  (`git show <gitlink>:pyproject.toml` through the submodule's object
  store), never the working tree — the original wording trusted the pin's
  working-tree content and carried a disclosed dirt-at-pin residual (D5);
  both review lanes observed a dirt-at-pin false verdict, firing D5's own
  revisit trigger, and the mechanism closed it: a dirty checkout can
  neither false-red a healthy pairing nor false-green the both-sides-stale
  defect. Roots recording no gitlink read the working tree (no pin exists
  to diverge from). Refused by name when the pinned bytes are unreadable
  or the field undeclared (`sdk_version_unanchored`); the render's purity
  clause is unchanged — `render_matrix` still never reads the SDK's
  pyproject. The authority chain is pyproject@pin → lock → mirror.*
  Amendment (2026-09-26, issue #215, parent #203): the matrix renders one row
  per retained version from the policy block and promotion records; the purity clause (committed
  state only, no checkout/remote reads) is unchanged and extends to the new inputs.
  This amendment lands with slice 5 and becomes true then (CON-14's disclosure
  style) — the slice-1 mechanism mirrors the policy block; it does not yet
  render per-version rows.
  Amendment (2026-09-28, issue #219 — slice 5 LANDED): the per-version table
  is true now. `render_matrix` renders one row per retained version —
  stage (naming a recorded promotion where the promotion records carry
  one), range membership, yank with the derived move-to, and the
  from-predecessor migration-note pointer — from the policy block and
  the promotion records, and every render input (the two manifests, the
  promotion records, `pyproject.toml`, `.gitmodules`) is read from the
  commit HEAD records through a temp committed-view staging, falling
  back to the working tree only where the root carries no committed
  copy to diverge from (the `check.py` pyproject@pin dual posture), so
  an uncommitted edit moves no rendered byte — pinned by E3's
  working-tree-only-edit control. The SM-5 gate
  (`benchweave.standards.migration_notes`, suite-run like the train
  window and self-anchored on its own arrival the same way) refuses a
  post-adoption MINOR-or-greater bump whose from-predecessor note row is
  absent (`migration_note_missing:`) or whose pointer does not resolve
  to a file under the root (`migration_note_unresolved:`); the note
  carrier is the policy block's per-version row, and pre-adoption
  releases carry none by design (D6).
  Fold-wave correction (2026-09-28, #219 refute FIX B/F4): the committed
  read's fallback breadth is narrower than first written, and now stated
  exactly — wherever HEAD verifies, a path it does not carry is
  COMMITTED-ABSENT (required inputs refuse; the optional promotion-records
  input skips staging), never a working-tree read; the working tree is read
  only where no committed copy can exist to diverge from (a non-git root,
  or a repository with an unborn HEAD); a repository that exists but cannot
  be read refuses `matrix_committed_state_unreadable:` rather than
  substituting working-tree bytes. The git invocations scrub GIT_*
  environment variables, so a caller's environment cannot redirect the
  committed read. Pinned by the untracked-promotion-record and
  poisoned-GIT_DIR repros (`tests/standards/test_matrix.py`).

- **[CON-13]** Website version stamps are a pure function of committed state —
  claim sites in `website/index.html` carry `{{stg-*}}` tokens and never
  three-component version literals (T2 refuses `\d+\.\d+\.\d+` over the
  class-11 source set, the `website/` tree plus `index.qmd`; residual:
  two-component prose claims, issue #188 design deferral 5);
  `website_stamp_map` derives from the standards manifest's active versions
  and the `sdk_compatibility` mirror (CON-12's authority chain); substitution
  happens only in the assembly copy and `verify_tree` refuses any `{{`
  residue in any copied static-site file —
  `scripts/assemble_docs_site.py` `website_stamp_map`/`stamp_website`, pinned
  by `tests/contract/test_website_stamps.py`. The badge/href pair of a card
  carries one token twice, so a claim/link version disagreement is
  unrepresentable at the value level. *CON-12's #158 lesson applied to the
  public site (issue #188: hand-stamped versions sat on the site with every
  gate green — the CON-8 defect class on the one un-mechanised version-bearing
  surface; a stamp that read checkout or remote state would red on correct
  committed bytes).*
  Amendment (2026-10-02, issue #224, parent #209; rewritten to the pivot the
  same day): the plugin catalogue is generated and served from the registry
  repository; the gateway website carries no registry-derived bytes. The
  catalogue page is a deploy-time artifact of the registry repository's own
  Pages pipeline (a deploy of commit X serves X's catalogue by construction,
  with the generating commit stamped on the page), so there is no committed
  page, no gateway mirror, no pin and no generated panel block to drift —
  the entire cross-repo sync apparatus this amendment first drafted is
  deleted, not delegated. The gateway's plugins panel is a static teaser —
  timeless prose plus one outbound link, string-pinned, zero
  catalogue-derived data (no counts, no names, no versions) — pinned by
  `tests/contract/test_website_plugins_teaser.py`. With no mirror there is
  nothing to exempt: the class-11 literal scan returns to zero exemptions
  (its pre-slice shape), and `tests/standards/test_zero_literal_gate.py`
  returns to main's bytes.

- **[CON-14]** Dependency resolution is a pure function of committed bytes plus
  authored constraints; locks are canonical-JSON and byte-identical on
  re-resolution; single-standard upgrade moves exactly one row; pre-releases
  never auto-select; dev pins are content-addressed (git sha + per-file
  digests), opt-in per plugin, and never resolve from a wheel; retired
  identifiers never resolve; cross-standard constraint rows are committed
  side-table data enforced pairwise at bench admission —
  `src/benchweave/standards/` (the dependency-policy block and its loader,
  issue #215, parent #203; the resolver lands with slice 2 and makes these clauses
  true). *The registry lock-writer precedent (`registry/admission.py`
  `_lock_document`) is the shape; resolution must never depend on network,
  working-tree state, or an LLM in the control path (A04).*
  Amendment (2026-09-27, issue #216, parent #203 slice 2): the resolution
  clauses are TRUE as of this slice — `src/benchweave/standards/dependency.py`
  (intervals and caret expansion at the authoring boundary, the three-answer
  classification, minimal-motion resolution, the canonical lock v2 writer,
  `pin --locked`, and check's plugin dependency lane; `standards/cross-constraints.json`
  is the committed side table, enforced pairwise at resolve time). The dev
  clauses (content-addressed dev pins, wheel refusal) remain slice-4 future
  and become true there — CON-12's disclosure style.
  Recorded ruling (2026-09-26, VR-47 points 1–2 of the parent arc #203;
  landed by #215) — carried VERBATIM here and in `standards/GOVERNANCE.md`
  ("Recorded ruling — VR-47 points 1 and 2"), not paraphrased:

**R-1 (reopen, VR-47.1).** Issue #97's withdrawal of "range pins, a resolver,
lock formats, a mutable `-dev` stage, forward-compat tolerance" is superseded
in part. REOPENED: range pins, the resolver, lock formats, and multi-version
serving of retained versions — the out-of-tree breakage axis (a plugin
outside the tree cannot move in-arc with a bump) post-dates the #97 closure
and is new evidence. The `-dev` record's "Not in scope, ever" (issue #97, the
dev-stage row) is superseded for the serving/pinning question only, on the
same evidence, joining the earlier sanctioned reopen of the mutable `-dev`
stage (#168/#169). NOT reopened: cross-version tolerance (PR #59's rejection
stands — serving retained versions EXACTLY is the only tolerance; ranges
never fuzzy-match) and external standards indexes (the PRD's non-goal,
unchanged).

**R-2 (CON-10 amendment, VR-47.2).** CON-10 keeps what it protects — one
shared authority (the retained corpus and its manifests), one descriptor
dialect, one projection — and drops what it never needed: the singularity of
the served pointer. A descriptor validates against exactly one OTDP version
— its own pin — resolved from the retained corpus, digest-verified. PR #174's
rejection of version-matched schema resolution is superseded on both its
stated grounds together: multi-version serving answers the single-version-tree
ground (the manifest, export, sync and wheel now carry every served version),
and wheel-bundling of the served set answers the "structurally unbuildable"
SDK leg (the SDK validates offline against the pinned version's bundled
bytes; PRD VR-32, owner Q8). The one-entry-per-id manifest shape is
undisturbed; the equivalence census extends across the served set. CON-1's
#63 amendment and CON-8 each gain the dated amendments in
`docs/internal/invariants.md`. Nothing in PR #59 moves (VR-47.5):
per-plugin exactness relocates one global gate to N per-pin gates;
out-of-range stays non-conforming, unretained stays refused.

Amendment (2026-10-01, issue #288 M4 + LOWs 1/2, NIT-3): the move-to
derivation is ONE canonical pure function — `dependency.derive_move_to(row,
served, pin) -> MoveTo(version, downgrade, guidance_only)` — consumed by
every gateway surface (the resolver's yank warning and VR-37 field, the
admission classifier's yank note, the matrix yank cell) and
re-implemented SDK-side, pinned by twin tests asserting the same literal
expected strings in both repos. The warning formatters append
` (a downgrade — no served version is newer)` when the derived version
orders below the pin, and ` (guidance only — no version is served)` on the
empty-served fallback — design §3.3's "highest served non-yanked version
>= pin" rule is vacuous wherever its filter is nonempty (max(candidates
>= pin) IS max(served)) and is superseded by this annotation. Design
§3.5's removal-point sentence (deprecation warnings naming the range's
next lower bound after narrowing) is recorded as DISSOLVED by the landed
move-to posture (issue #288 LOW 1): naming the concrete move-to version
is strictly more actionable than naming where the range floor went.
LOW 2 annotation: the R-1/R-2 rulings above are carried verbatim in
`standards/GOVERNANCE.md` modulo line rewrapping and one phrase — this
copy says the dated amendments land "in `docs/internal/invariants.md`"
where GOVERNANCE's lift phrases the carrier as the invariants path from
the other side; both texts are frozen history and this note is the
disclosure, not an edit of either. NIT-3: the original CON-14 row above
carries no inline date on its face; this amendment carries its own
(2026-10-01) and names the omission rather than backfilling the row.


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

- **[REG-5]** Publishing-lane records are canonical, schema-validated JSON
  committed in the registry repository of record (benchweave-registry), the
  review block rides inside the origin-signed manifest (registry standard
  0.1.2; one signature attests release and review together), and the gateway
  never consults it — admission validates structure and verifies the four
  pillars and nothing else (CR-13 held, Q12); lane gates refuse dev-unsigned
  lineage (``dev_lineage_refused:``), mutable source refs
  (``source_ref_mutable:``), declaration-less submissions
  (``capability_declaration_absent:``) and closure-diff-less publish records
  (``closure_diff_absent:``) at packaging time, SDK-side; the records-validity
  gate (registry-repo CI) refuses changes-requested-without-failure (CR-10),
  findings-less reviews (CR-60), kind-less records (CR-56) and closure-digest
  disagreement (CR-38); every publish record's sign-off names the closure
  digest the release actually carries, and the signed manifest's review block
  pins the review record's own digest (the review-to-sign swap defense,
  CR-11/CR-14) — `benchweave-registry/scripts/validate_records.py` +
  `scripts/registry/sign_release.py`, pinned by the registry repo's validity
  suite and `tests/contract/test_sign_release.py`. *Disclosure clause (Q16):
  per-plugin isolation, the evidence MAC and the plugin-independent safe state
  are recorded residuals — the lane never claims them (NFR-S1); kind tags are
  machine-checked at write time from slice 1, with `community-shared` records
  activating in slice 5.*
  Amendment (2026-10-02, issue #224 slice 2; rewritten to the pivot the
  same day): the clause "the generated index is never hand-edited on
  either side" now has one side — the registry repository, where the
  committed index stays pinned to regeneration from records by the
  `--check` (`index_drift:`) discipline and the catalogue page is a
  deploy-time artifact of that repository's Pages pipeline. The gateway
  mirror and its three gates (render guard, authority pin, registry-side
  `mirror_drift:` refusal) are deleted with the pivot — there is no second
  copy to keep honest. The generator's yank arm remains the single source
  of what the catalogue offers: a release whose status document carries
  `yanked` or `revoked` drops out of the index at regeneration (CR-25's
  "no stale rows survive a yank"), while the record and git history
  retain it.

## Known open wounds

Some invariants sit next to known-imperfect code. Track the individual issue in the repo
tracker and cite it in review rather than building a consolidated weakness list here — a
one-stop map is more useful to an attacker than to a reviewer, who is only ever looking at
one diff. If a PR touches a wound, fix it or at least do not widen it, and say which.
