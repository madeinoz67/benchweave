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
  device and the exact action id (invoke) or parameter (write), and every matching rule's
  constraints hold conjunctively — no order-dependent overrides. Rejections carry
  machine-matchable prefixes (`no_matching_rule:`, `input_constraint:`, `value_constraint:`)
  — `src/benchweave/control/policy.py` `check_allowed`. *An allow-list cannot be widened by
  rule ordering, and a refused action must be greppable in evidence.*
- **[CTL-5]** The executor answers every re-entry from the occurrence ledger without
  re-dispatching, appends one step event per occurrence, and runs under a fixed monotonic
  body deadline — `src/benchweave/control/executor.py`. *A06: physical work is never
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
  marks issued for that exact action — `src/benchweave/control/semantics.py`. *Scoping is
  what makes a bounded, reviewable procedure language out of JSON (A12); a reference that
  can see sideways or forwards is an unreviewable one.*
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
- **[REG-3]** Registry admission pins the complete dependency closure; publication and
  installation never authorize control (A11) — `src/benchweave/registry/admission.py`,
  pinned by `tests/contract/test_registry_admission.py`. *A downloaded package is data
  until commissioned locally; an install path that grants authority is the whole security
  model inverted.*

---

## Known open wounds

Some invariants sit next to known-imperfect code. Track the individual issue in the repo
tracker and cite it in review rather than building a consolidated weakness list here — a
one-stop map is more useful to an attacker than to a reviewer, who is only ever looking at
one diff. If a PR touches a wound, fix it or at least do not widen it, and say which.
