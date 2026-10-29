# Issue #568 — the gateway commissioned provider runtime (executor + grant seam)

**Date:** 2026-10-28
**Scope:** the gateway-side half of issue #568: the commissioned runtime that
serves admitted transport-provider transactions on commissioned hardware, and
the grant seam that bounds its authority. The SDK-side live FTDI transport is
the sibling lane (`benchweave-sdk/.wt/568-live-c26b`,
`2026-10-28-issue568-live-provider-transport.md`) and is depended on, not
designed here. Recorded replay (#564) and the provider-contract mechanism
(#147 increment 3) are landed and untouched except where named.
**Verdict up front:** BUILD — and the gateway's half is smaller than the
issue's phrasing suggests, because the gateway already owns the two hard
halves: admission (the `provider_not_admitted:` row, `connections[]`
resolution, approval expiry — all landed) and the enforcement envelope (the
bridge's dispatch markers, deadlines, cancellation, poison discipline — all
landed). What does not exist is (1) any runtime behind
`ProviderTransport`'s `runtime` slot (constructed `None` at
`provider_transport.py:257` — every provider transaction today raises
`NotImplementedError` at first transfer), (2) any commissioned binding from a
`connection_key` to a physical USB identity, and (3) any run-window arithmetic
over the provider approval (expiry is judged at admission against `now_wall`
only). All three are buildable on in-tree precedent with zero corpus motion
and zero interface motion.

**Triage:** PUBLIC. No person, client, bench name, serial, commercial term, or
one-install operational specifics below; example identities in fixtures are
invented. Same register as the #562/#564/#568-SDK records this continues.

---

## 0. Grounding — what was verified, against which bytes

Every code claim below was read this session at gateway `origin/main` =
`23f40ed1` (the lane base, confirmed on the branch
`feat/568-gateway-provider-runtime`). Line numbers are from that commit. The
SDK claims were read at the SDK repository's `origin/main` = `2b0dd75`
(v0.23.0+6, the #562 provider-replay merge) and at the gateway's pinned
gitlink `4675162` (v0.23.0) via the SDK's object store.

1. **Admission exists end to end and refuses today.**
   - `src/benchweave/control/provider_settings.py:239`
     `load_transport_settings` — exact-byte decode, the identity-only schema
     (`additionalProperties: false` throughout, `:66-124`), per-admission
     digest verification against the settings-relative contract document
     (`settings_digest_mismatch:`, `:316`), duplicate-admission and
     rival-bytes refusals (`:276-293`), connection-key uniqueness and
     admitted-provider consistency (`:345-361`).
   - `src/benchweave/control/documents.py:1345` `_check_provider_admission`
     — the `provider_not_admitted:` row: exact triple (`:1384`), approval
     expiry judged against a caller-supplied `now_wall` — a missing
     `now_wall` refuses (`:1392`) — and the S12-extended `connection_key`
     resolution (`:1416`).
   - The run path re-admits per start: `src/benchweave/interfaces/app.py:234`
     finds `transport-settings.json` in the fixtures dir and `app.py:259`
     passes it (when present) with `now_wall=now_iso()` into
     `admit_documents` — so expiry is re-judged per run start today, against
     the START instant only, never against the run's whole window.
2. **The grant object exists; the runtime slot is empty.**
   `src/benchweave/content/provider_transport.py:61` — `ProviderTransport(
     contract=…, runtime: Any = None)`; `:124-129` — with no runtime,
     `transfer` refuses `NotImplementedError` naming the implementation lane;
   `:189` `provider_transport_for` runs the three grant checks (permission
   `scoped_transport`, exact admitted triple, connection-key resolution) and
   returns `ProviderTransport(contract=entry.document)` — **no runtime is
   ever injected in production** (the module docstring says so outright:
   "Nothing in production constructs these objects yet"). The corpus agrees
   this is gateway territory: `standards/otdp/0.2.4/transport-providers.md`
   §7 — "Only the gateway can prove the grant … Commissioned state and the
   provider runtime live there."
3. **The production call site passes no registry at all.**
   `src/benchweave/interfaces/app.py:847` calls `build_capture_services(...)`
   with neither `providers=` nor `transport=` — so a provider-declaring
   descriptor on a commissioned run gets `provider_transport_for(descriptor,
   None)` → the bound refusal "no provider contracts are admitted at all".
   `ProviderRegistry` is consumed by `admit_documents` and `AdmittedDocuments`
   (`documents.py:167-189`) carries no provider fields: **the registry never
   reaches the run's services bundle.** That threading gap is this design's
   first motion.
4. **The gateway has no transport implementation of any kind.**
   No pyserial/pyftdi/USB code exists under `src/benchweave/` (verified:
   `rg pyserial src/` returns nothing; `pyproject.toml` dependencies carry no
   transport backend). Every plugin's `services.transfer` raises
   `NotImplementedError("…no transport is bound…")`
   (`capture_services.py:137-141`) unless a transport was injected. The
   provider runtime is therefore the gateway's FIRST live transport, not an
   addition to a family.
5. **Provider transactions ride ordinary verb dispatches, and protection
   rides them too.** The plugin adapter reaches the device only through
   `context.services.transfer(...)` inside `adapter.execute` — wrapped by the
   bridge's deadline, cancellation and poison discipline
   (`host/otdp_bridge.py:460-469`, the `_Context.dispatched` marker `:121`).
   The protective transition dispatches safe actions through the SAME
   `plugin.dispatch` path (`control/protection.py:324`, `protect:` operation
   ids at `:357`), so a provider-backed device's safe actions ride the same
   transport — the runtime must stay alive through protection, which the
   worker's ordering already guarantees (plugins close after the coordinator
   finishes; the F1 comment at `app.py` names every exit path).
6. **The corpus makes the gateway serve BOTH transaction families on a
   provider connection.** `otdp-specification.md` §8.1 (`:228-246`): the
   generic table (`stream_send`/`stream_receive`/`stream_exchange` + the
   reserved can/i2c/spi kinds) is the transfer ABI every adapter speaks, and
   "stream_send/exchange support LAN/USB/serial adapters with the selected
   backend semantics"; the provider grammar "extends this table for that
   provider only … additive and disjoint". The LogicPort adapter this whole
   arc serves reaches the device "ONLY through these [seven control ops] and
   the two generic stream kinds" (#562 record §0.3). So the commissioned
   runtime serves the admitted grammar's kinds AND the §8.1 stream trio over
   one commissioned device — exactly the composition the SDK's
   `FtdiCaptureServices` ladder implements (grammar kinds → provider path;
   otherwise → the §8.1 parent).
7. **The two-layer refusal shape is in place to join.**
   `interfaces/operations.py:2120` is the seam's runnability pre-check
   (`_check_run_floor`, best-effort over stored documents);
   `app.py:783` is the worker's authoritative call. The unattended grant uses
   the same shape (`_check_unattended_grant`, `documents.py:1596`, called at
   both layers). The provider grant's window arithmetic joins this family.
8. **The run-stream evidence precedent.** `coordinator.py:1357-1366`
   `devices_pinned` — per-device pin facts land as the FIRST event on the
   run's stream, digest-covered by the terminal record's `events:{run_id}`
   ref, because the run-record document is schema-frozen. The provider grant
   facts ride the same mechanism.
9. **SDK-side dependency status, verified in the SDK object store.** The
   gateway pin `4675162` = SDK v0.23.0: `ftdi.py` ABSENT,
   `providers/ftdi-control-1.0.0.json` ABSENT. SDK `origin/main` `2b0dd75`
   (v0.23.0+6): `ftdi.py` ABSENT (the sibling #568 lane is building it now —
   its task list shows "Implement ftdi.py module per §2" in flight),
   `providers/ftdi-control-1.0.0.json` PRESENT (landed with the #562 replay
   merge). The gateway submodule is uninitialized in this lane clone
   (`git submodule status` shows `-4675162`), so nothing in this design was
   read from the working-tree submodule; SDK facts come from the SDK
   repository's own checkout at those commits.
10. **No rival work.** Pre-flight (#181 R2) run this session: `git fetch`
    origin, remote branch list (newest: `feat/556-*`, `feat/560-*`, `pr-561`
    — no provider-runtime branch), and `gh pr list` on the gateway tracker
    returned no open PRs. The tracker's #568 rows name this lane as the
    gateway-side design.

**Inference, not verified this session (flagged):** the pyftdi API surface
(the call names the SDK's `FtdiDriver` Protocol spells, and pyftdi's
open-failure classes) — pyftdi is not installed in this venv and was not
imported; the build verifies both, mirroring the SDK record's own §0 flag.
Everything else above was read in the source this session.

---

## 1. The seven rulings

### 1.1 Executor placement — it rides the existing dispatches; there is no new
operation class

A provider transaction is not a step kind and never becomes one. It is
transport-plane traffic inside an ordinary verb dispatch: the procedure
executor dispatches invoke/write/read/capture (`control/executor.py`, the
nine-kind interpreter), the plugin adapter serves the verb by speaking its
wire protocol through `services.transfer`, and `ProviderTransport` guards
each transaction against the admitted grammar before the runtime sees it
(`provider_transport.py:99-142` — the guard is landed). The corpus states
this composition as the rule: "Provider transactions are `transfer` calls on
the commissioned connection: they inherit transfer's deadline, cancellation
and evidence enforcement unconditionally" (transport-providers §3; §8.1's
closing paragraph repeats it).

Consequences, each structural:

- **A03 holds unchanged.** The transport is constructed inside the run
  worker's device-plan loop (one bundle per device session,
  `build_capture_services`), opened with the plugin, and closed with it. One
  controlling procedure per bench already means one live run; the transport
  has no existence outside a run because nothing outside the worker ever
  constructs it.
- **A13 holds with zero interface motion.** No REST operation, no MCP tool,
  no openapi/mcp-tools byte moves — pinned by the corpus trees staying
  byte-identical (acceptance arm C1). An operator cannot "poke" a provider op
  outside a commissioned procedure; all provider traffic rides commissioned
  procedures and the protective transition. That is the A04-consistent
  answer, not a limitation to lift later.
- **A04 holds by construction.** The runtime is a plain object under the
  bridge's existing deadline/cancel/poison envelope; nothing about it needs
  an agent, and no client can reach it — the wire surface for it does not
  exist.
- **The single-writer store hold is untouched.** The runtime does no store
  I/O on the dispatch path (its evidence rows ride the existing
  `record_evidence` member, below); the store's one-writer discipline
  (`state/hold.py`, STO-3) sees no new acquirer.

The alternative — a tenth step kind (`provider_transaction` steps in
procedure bodies) — is refused on in-tree evidence: the procedure language is
bounded and device-agnostic (A12; CTL-7's lexical scoping exists so procedures
stay reviewable), and putting wire dialects into procedures would make every
procedure plugin-coupled and every grammar change a procedure-language event.
The corpus's own design (grammar extends the TRANSFER table, not the step
kinds) is the settled answer; this design follows it.

### 1.2 The grant seam — what confers bounded authority

Today's grant is the construction gate (`provider_transport_for`'s three
checks) plus admission's `provider_not_admitted:` row. A run may legally
start with all of that satisfied and STILL have no execution authority,
because nothing binds the connection to a physical device and nothing injects
a runtime. The completed grant is a conjunction of five facts, four of which
exist:

1. **The declared triple is exactly an admitted triple** (landed:
   `provider_not_admitted:` at admission, re-checked at the construction
   gate).
2. **The connection key resolves to the same admitted contract** (landed:
   S12-extended, both layers).
3. **The approval has not expired at run start** (landed: judged against
   `now_wall` per admission call).
4. **The scoped_transport permission is held** (landed: the construction
   gate's first check).
5. **NEW — the run-window bound:** the run's whole window
   (`now_wall + max_body_ms + max_protection_ms`, the CTL-10 arithmetic)
   cannot exceed the admitted approval's `expires_at`. A compliant start
   cannot straddle approval expiry — CTL-10's own sentence, applied to the
   provider approval. Typed refusal
   `provider_grant_window_exceeded:` carrying both timestamps.
6. **NEW — the endpoint identity:** the connection key resolves to exactly
   one commissioned USB identity (§1.3). Typed refusals
   `provider_grant_endpoint_absent:` / `provider_grant_endpoint_conflict:`.
7. **NEW — a runtime is constructed behind the guard**, and its op table
   covers every op the admitted grammar's request schema discriminates
   (§2.2). Typed refusal `provider_runtime_op_unsupported:` at construction
   — the grant fails BEFORE the device is opened, not at first transfer.

**Bounded in time:** the transport's life is the run's life — constructed in
the worker's device loop, opened with the plugin session, closed at
`plugin_close` after the protective transition completes (the worker's
existing ordering). The run lease (`run:{run_id}`, expiry = acceptance +
max_body + max_protection, STO-4) is the binding budget; item 5 makes the
approval window a second, admission-time bound so the lease can never outlive
the approval. There is no mid-run approval timer for the same reason CTL-10
has none: the acceptance-time arithmetic makes straddling unrepresentable.

**Bounded in scope:** per device session; the admitted grammar's kinds plus
the §8.1 stream trio only (the can/i2c/spi reserved kinds refuse typed —
`provider_runtime_kind_unsupported:` — they carry gateway-authorisation
semantics the corpus has not designed and this runtime does not serve); the
contract's `security_scope` is `commissioned_connection` by admission, and
the runtime's only capability is the device handle the endpoint names.

**What refuses when it is absent or expired:** three layers, the #260/#316
shape. Admission (startup and per-run, landed) refuses items 1-3. The seam's
runnability pre-check (`operations.py:2120` family) gains a best-effort
provider-grant pass over stored documents — the wire-visible early refusal
before any lease is consumed. The worker's grant construction
(`build_capture_services` with the threaded registry, §1.4) is authoritative:
a refusal there lands in the worker's poison guard (202 → `outcome_unknown`
at the projection) with the typed reason on the gateway log — the same
disclosed shape as the run floor's and the unattended grant's worker legs.

### 1.3 USB identity versus the identity-only settings schema — the ruling

The #562 record deferral 1 names this as the gateway-side question the live
executor triggers. The ruling has three parts.

**(a) transport-settings.json stays identity-only, byte-untouched.**
Obligation 16's refusal is not a style preference: "an endpoint field would
put extension-contract §6's no-direct-access sentence one schema-edit away
from false" (`drift-and-obligations.md` §16). The settings schema's whole
review value is that it CANNOT express an endpoint; this design does not edit
it. `provider_settings.py`'s own module docstring states where the endpoint
was always going to arrive: "Endpoint and secret configuration arrives with
the first runtime implementation through the deferred operator admission
surface, never here." This design is that surface.

**(b) The commissioned endpoint lives in a second gateway-owned operator
document — `provider-connections.json` — in the fixtures directory, beside
the settings file.** The precedent is exact: `transport-settings.json` itself
is "gateway-local validated configuration — the #43 retention-policy
precedent (owner call 2): gateway-local carrier today, commissioning promotion
on a named trigger" (`provider_settings.py` docstring). The connections
document is the same carrier class, one scope narrower: it binds
`connection_key` → USB identity and expresses NOTHING else.

```json
{
  "config_version": "1",
  "connections": [
    {"connection_key": "fpga_prog",
     "usb": {"vendor_id": 1027, "product_id": 24593,
              "serial": "FT-A11-0042", "interface": 1}}
  ]
}
```

Schema in gateway source (NOT corpus — the corpus owns the provider CONTRACT
schema; endpoint identity is host commissioning state, deliberately outside
the vendored tree like the settings schema is). Identity-shaped by schema,
not policy, in the settings file's own discipline:

- `additionalProperties: false` throughout; `vendor_id`/`product_id`
  integers in [0, 65535]; `interface` integer in [1, 8]; `serial` a non-empty
  patterned string `^[A-Za-z0-9._-]{1,64}$`.
- **`serial` is REQUIRED.** A commissioning identity without a serial is
  ambiguous the moment two same-model devices are attached, and pyftdi's
  first-match resolution would silently pick one — wrong-device actuation is
  precisely the hazard the identity binding exists to close (A02: qualified,
  not assumed). With a unique serial in the identity, ambiguity is
  unrepresentable at the schema level. Devices without readable serials
  cannot be commissioned for provider transport in this revision (open
  decision 2).
- No field of any other shape can appear: a URL, path, host, port, credential
  or process reference is schema-unrepresentable. The one thing this document
  can grant is "this logical connection is that physical USB interface" —
  which is exactly the commissioned fact the runtime needs.
- Internal consistency, refused typed (`connections_schema:` /
  `connections_digest_mismatch:`, the settings prefixes' twins): every
  `connection_key` must be one the settings document binds (an endpoint for
  an unadmitted connection is dead config — refused, the settings file's own
  internal-consistency posture); no key carries two identities; **no two keys
  share one USB identity** (a USB interface is single-client; two device
  sessions interleaving on one handle is the corrupt-conversation hazard —
  refused as `provider_grant_endpoint_conflict:` at load).
- **Presence rule:** the document is REQUIRED iff `transport-settings.json`
  binds any connection. A settings document with connections and no endpoints
  document refuses at load — the closed default (A02), and the operator
  learns it at startup, not at first run.
- Decode through the exact-byte decoder with the same 1 MiB cap; loaded by
  the same admission path (`admit_documents` gains the sibling-path
  parameter, auto-discovered beside the settings file, both at bootstrap and
  on the run path's re-admission — the same two lanes the settings file
  already rides).

**(c) Promotion into the commissioning document remains the designed end
state, and this design does not attempt it.** Obligation 16's promotion
sentence ("pinned, expiring with the commissioning") is the destination; the
path there is an execution-standard revision (the commissioning schema is
corpus-validated, `standards/execution/0.2.0/`), which drags the full bump
obligation set (6/8/13/21, the governor, the SDK lock, the served set). That
train is not this increment's to open, and nothing in the runtime's mechanism
depends on the document's HOME: the grant check consumes a resolved
`(connection_key → usb identity)` mapping either way. The reopen trigger is
the next execution-standard head-opening train; the mechanical signal that
promotion is due is the first time an operator must re-state the same USB
identity in two commissioning-adjacent documents for one bench.

### 1.4 Admission coupling — how the pieces compose so refusal lands at the
gateway

The composition, in the order a run experiences it:

1. **Bootstrap/startup admission** (`interfaces/bootstrap.py:130` family):
   settings load → connections document load (new) → descriptor projection
   with the `provider_not_admitted:` row (landed). A provider-descriptor
   bench whose settings are absent/mis-admitted refuses STARTUP — landed and
   unchanged. NEW: the connections document's own refusals join the startup
   set.
2. **Run acceptance, seam pre-check** (`operations.py:2120` family,
   best-effort over stored documents): the provider-grant pre-check — window
   arithmetic (item 5) and endpoint resolution (item 6) — beside the run
   floor and the unattended grant. Wire-visible typed refusal BEFORE any
   lease is consumed.
3. **Run build, worker** (`app.py`'s `_run_worker`): `admit_documents`
   returns `AdmittedDocuments` which NOW carries `providers:
   ProviderRegistry | None` and `provider_endpoints` (the threading change —
   the registry currently dies inside `admit_documents`, §0.3). The device
   loop passes them to `build_capture_services(providers=…,
   provider_endpoints=…)`, `provider_transport_for` gains the runtime
   factory, and the grant is constructed authoritatively here (items 5-7).
   A refusal fails the run build with the typed reason — the poison-guard
   shape every other worker-layer gate uses.
4. **Per-transaction, forever after:** `ProviderTransport.transfer`'s
   grammar gate (landed) → the runtime's own ladder (§2.3). An un-admitted
   contract never gets this far (step 1 refused it); a mid-air settings edit
   cannot widen a running session because the session holds its constructed
   grant object, and the NEXT run's re-admission re-reads both files — the
   #260 fold's disclosed re-read posture, inherited verbatim.

The SDK's pin verification composes by NOT being re-implemented: the gateway
admitted the contract bytes against the vendored provider schema and the
triple's digest (`provider_settings.py:311-333`); the grammar the guard
enforces is compiled from those same admitted bytes (`provider_transport.py:
62-65`); the runtime's op table is checked against the grammar's own `oneOf`
op consts at construction (§2.2). One authority — the admitted bytes — three
consumers. Nothing re-derives identity from the plugin side at runtime.

### 1.5 Audit before actuation (A07) — which provider ops energise, and what
the mechanism is

**The unit of A07 audit is the dispatch, and that does not change.** The run
record already answers "what did the gateway command" at the granularity the
gateway commands: one step event per occurrence (CTL-5), the invoke's action
id and resolved input (CTL-6), the error/dispatch-state honesty (REG-2).
Provider ops are wire traffic beneath that, like SCPI bytes over a serial
port — the gateway has never recorded those either, and the corpus's own
posture is that wire-level authorship is review surface, not runtime
guarantee (transport-providers §4).

**The one place the provider layer adds an A07 obligation is the actuarial
control act itself.** The brief's framing is right: a bitmode/purge/reset/
baud on commissioned hardware is a control act whose intent the gateway CAN
record cheaply (the bundle's `record_evidence` member exists,
`capture_services.py:97-133`, landing content-addressed rows under the run's
context key). The mechanism:

- **Intent-first evidence for ENERGISING provider ops.** For each energising
  op, the runtime lands one `event_log` evidence row — the transaction
  (kind, op, params), the operation id, the monotonic stamp — BEFORE the
  driver call. If the row cannot land (quota exhausted, store failure), the
  op refuses typed (`provider_runtime_audit_refused:`) and the driver is
  never called: intent that cannot be recorded is not actuated. This is A07's
  sentence made ordering — record-after cannot implement "refuse when intent
  cannot be recorded".
- **The protective carve-out, exactly A07's own.** "Protective action and
  the approved active-procedure response continue." The runtime recognises
  protective dispatches by the operation-id convention (`protect:` — minted
  at `protection.py:357`, a stable in-tree convention, not a new protocol):
  for those, an intent-row failure does NOT veto the driver call — the safe
  action dispatches, and the runtime records the failed-intent disclosure on
  a per-session list that `close_transport` flushes as one best-effort
  summary row. Evidence storage is never a dependency of protection.
- **Energising classification, with reasoning:**

  | Op | Class | Reasoning |
  |---|---|---|
  | `set_bitmode` | energising | drives the parallel-interface pins; can source/sink current on bench wiring — the one op whose direct physical effect is pin energy |
  | `reset_device` | energising (state-changing) | returns pin state to reset defaults; a pin the bench relied on being driven changes physical state |
  | `set_baud`, `set_latency`, `set_timeouts` | not energising | interface configuration; no pin state, no DUT energy path — control acts, but the dispatch that carries them is the audited intent |
  | `purge` | not energising | host/FIFO buffer state only |
  | `read_pins` | observation | reads pin state; records nothing (the dispatch is the record) |
  | §8.1 `stream_send`/`stream_exchange` | delivery, not transport-energising | the BYTES may command anything, but that command's intent is the dispatch's (the invoke's input, CTL-6-recorded) — wire-level intent is review surface (the residual stated, transport-providers §4's own posture) |
  | §8.1 `stream_receive` | observation | — |

  The classification is a module contract constant, not a per-call judgement
  (A04); the two energising names are the only ops the intent-first rule
  covers. Residual, stated: a future contract revision adding an op leaves
  the runtime's table frozen — the new op refuses at construction
  (`provider_runtime_op_unsupported:`), so an unclassified energising op
  cannot silently skip the rule; re-classification is a code change with
  review.

### 1.6 Honesty on the wire (A06) — what the record carries, what the client
sees

The bridge's envelope is inherited whole: the runtime never fabricates, never
retries (one bounded attempt per transaction, the REG-2 posture), and the
adapter owns `dispatch_state`. The table the design is accountable for:

| Failure | Run record / client sees |
|---|---|
| pyftdi absent (install shape) | grant construction refuses `provider_runtime_backend_missing:` naming the install extra; a provider-descriptor bench refuses at STARTUP admission-adjacent load — never mid-run |
| Device absent / busy / permission / no libusb | the driver factory's open failure maps to `provider_runtime_device_unavailable:` naming the exception class; the grant construction fails; the run build refuses with the typed reason — one attempt, no scan, no retry |
| Un-admitted / wrong-digest contract | `provider_not_admitted:` / `provider_contract_hash_mismatch:` at admission (landed) — the run never starts |
| Approval expiry inside the run window | `provider_grant_window_exceeded:` at the seam pre-check (wire-visible) or the worker (authoritative) |
| Endpoint absent / duplicated / mismatched | `connections_schema:` at load; `provider_grant_endpoint_absent:` / `provider_grant_endpoint_conflict:` at the grant |
| Grammar op outside the runtime's table | `provider_runtime_op_unsupported:` at grant construction — before the device opens |
| Transaction violates the admitted grammar | `provider_transaction:` refusal (landed, `provider_transport.py`) — never dispatched |
| Device unplugged mid-conversation | the next driver call faults → the runtime maps the fault to `ConnectionError` naming the class; the adapter's dispatch after entry → the bridge's poison posture → step `unknown`, body `outcome_unknown` (executor's §5 mapping); a faulted runtime stays faulted — reconnect is a new run, a fresh session |
| Deadline / cancellation mid-transaction | the bridge's `asyncio.timeout` fires; the driver call runs on `asyncio.to_thread` so the thread may orphan-complete — the DISPATCH record stays honest (`TIMEOUT`/`UNKNOWN`), never "not_dispatched" for work sent (REG-2); the orphaned completion is the disclosed serial-lane residual, one lane over |
| Driver answers a malformed result | `provider_transaction:` result-grammar refusal (landed) — the live device is untrusted against its own pinned contract |
| Partial completion | a control op is discrete — completed or raised, and the step event says which; a §8.1 receive never returns an incomplete frame as complete (§8.1's own rule; the runtime's receive ladder enforces exact_bytes/terminator) |

Never, on any path: a fabricated `ok`, a silent fallback (there is no second
transport to fall back to — §0.4), or a retry.

### 1.7 The mock parity rule on this lane

**The gateway ships its own scripted driver double in its test tree, driven
by the same #564 journal-row evidence the SDK's `ScriptedFtdiDriver`
consumes; the SDK-double agreement test rides the pointer-advance leg.**
Reasoning:

- The double must sit at the DRIVER boundary (the injectable
  `FtdiDriver` Protocol), not at the transaction boundary — a bitmode call
  is a device-boundary act, not a transaction shape (the sibling record §3's
  own argument, which this design adopts rather than re-litigating).
- The production path the double exercises is the full gateway ladder:
  admission (settings + connections + descriptor pin) → seam pre-check →
  worker grant construction (grammar/table check, runtime injection) →
  bridge dispatch → `ProviderTransport` grammar gate → runtime ladder
  (intent-first evidence, op dispatch, result validation) → driver. Nothing
  but the USB boundary is mocked.
- The script derives from the provider rows of a #564-format journal — one
  evidence document drives the SDK's rehearsal and the gateway's, so the two
  rehearsals cannot drift apart without a visible disagreement. The journal
  FORMAT is landed SDK-side (the replay transport at `2b0dd75`); the gateway
  test authors fixture journals directly against that row shape.
- Why a gateway-local double rather than importing the SDK's
  `ScriptedFtdiDriver`: the gateway does not import the SDK at runtime
  (REG-4's read-not-import posture — verified: no `benchweave-sdk` in
  gateway `pyproject.toml` dependencies), and test-time import is impossible
  at this pin anyway (`ftdi.py` absent at `4675162` AND at SDK main — §0.9).
  The pointer-advance leg (standing #408 order, after the SDK release cut)
  adds the agreement test: the gateway double's op-call sequence equals the
  SDK `ScriptedFtdiDriver`'s over the same journal, and the gateway's op
  table equals the SDK's `_OPS` — the `tests/sdk/test_adapter_agreement.py`
  shape, one lane over. That leg is the pointer discipline's own motion, not
  a deferral of this repo's work.

---

## 2. The mechanism

New module `src/benchweave/content/provider_runtime.py` (the transport-plane
content family, beside `provider_transport.py`); the connections document in
`provider_settings.py`'s family; the wiring at four existing sites.

### 2.1 The driver protocol and the device boundary (injectable)

```python
class FtdiDriver(Protocol):
    def reset_device(self) -> None: ...
    def set_timeouts(self, read_ms: int, write_ms: int) -> None: ...
    def set_latency(self, ms: int) -> None: ...
    def set_baud(self, baud: int) -> None: ...
    def purge(self, queue: str) -> None: ...          # "tx" | "rx"
    def set_bitmode(self, mask: int, mode: int) -> None: ...
    def read_pins(self) -> int: ...
    def write_data(self, data: bytes) -> int: ...
    def read_data(self, size: int) -> bytes: ...
    def close(self) -> None: ...
```

The ten calls the seven contract ops plus the data pipe need, nothing else —
the sibling record §2.1's shape, mirrored gateway-side (the REG-4 hand-mirror
posture; the agreement test at the pointer leg pins the two tables equal).
`open_ftdi(identity)` is the only pyftdi import site: lazy, function-local,
`# type: ignore[import-untyped]` (the in-tree idiom for untyped backends),
composing the pyftdi URL from the commissioned identity
(`ftdi://<vid>:<pid>:<serial>/<interface>`); an `ImportError` maps to
`provider_runtime_backend_missing:` (naming the install extra), any open
failure to `provider_runtime_device_unavailable:` naming the exception
class.

### 2.2 The grant construction (the op table against the grammar)

`provider_transport_for(raw_descriptor, providers, *, endpoints=None,
runtime_factory=None)` — the landed three checks unchanged, then:

1. resolve the connection's endpoint from the connections document
   (`provider_grant_endpoint_absent:` when the key has no identity);
2. build the runtime via the factory (production: `FtdiRuntime` over
   `open_ftdi`; tests: any driver double) — the factory receives the
   admitted contract document and the endpoint identity;
3. **the table-vs-grammar check:** compile the grammar's request-schema
   `oneOf` branch `op` consts (the ftdi-control grammar is one kind with an
   op discriminator — the #562 record §1's ruling, landed in the banked
   contract) and require the runtime's dispatch table to cover every op —
   `provider_runtime_op_unsupported:` naming the op, BEFORE the device is
   opened. Version skew (a future 1.1.0 grammar's eighth op) refuses the
   GRANT, not the mid-run transaction: an un-runnable procedure refuses at
   build, the honest #260 posture.

`build_capture_services` gains `providers` (already in its signature,
currently unused by production callers) and `provider_endpoints`; the
runtime factory is constructed in app.py's device loop and threaded in.
`AdmittedDocuments` gains `providers: ProviderRegistry | None` and
`provider_endpoints: ProviderConnections | None` (populated by
`admit_documents` from the two files it already discovers).

### 2.3 The runtime ladder (per transaction)

`FtdiRuntime.transfer(transaction, context)` — called by
`ProviderTransport.transfer` AFTER the grammar gate (so grammar kinds arrive
pre-validated; the runtime re-derives nothing):

1. **Kind split.** A grammar kind → the provider path (2). A §8.1 stream
   kind (`stream_send`/`stream_receive`/`stream_exchange` — the gateway's
   field-set twin of the SDK's `_FIELDS`, hand-carried and pinned against
   the corpus §8.1 table by a spelling test, obligation 17's family) → the
   stream path (5). Any other reserved kind → `provider_runtime_kind_
   unsupported:` (the can/i2c/spi kinds are reserved but unserved). Anything
   else → the guard already refused it upstream.
2. **Provider path.** `op = transaction["op"]`; dispatch through the table,
   one `asyncio.to_thread` call into the driver, one bounded attempt. For
   the two energising ops (`set_bitmode`, `reset_device`): the intent-first
   evidence row lands BEFORE the driver call; a row failure refuses
   `provider_runtime_audit_refused:` — except the `protect:`-prefix carve-out
   (§1.5). Driver exceptions map to `ConnectionError` naming the class (a
   faulted runtime stays faulted).
3. **Result validation.** The grammar's `result_schema` over the driver's
   answer (`read_pins`' one base64 byte; actuation ops' empty object) —
   `ProviderTransport`'s landed result gate does this on the way out
   (`provider_transport.py:136-141`); the runtime returns raw and lets the
   guard refuse. The live device is untrusted against its own contract.
4. **§8.1 stream path.** The data pipe (`write_data`/`read_data`) with the
   §8.1 receive semantics: `exact_bytes` precedence over terminator
   detection, `exact_bytes ≤ max_bytes`, incomplete frames never returned as
   complete, byte counts include framing (the corpus §8.1 row's own rules).
   The receive loop is deadline-aware (the context's `deadline_monotonic`),
   paced by a small idle read quantum so it never hot-spins.
5. **Close.** `close_transport` closes the driver — one handle, one close.
   The worker holds a per-device runtime reference and closes it in the
   teardown finally beside `plugin_close` (the host-side guarantee for
   anything still open — the §0.3 posture; an adapter that never calls
   `close_transport` cannot leak the handle).

### 2.4 The window arithmetic and the seam pre-check

`_check_provider_grant_window(docs, now_wall)` — the CTL-10 helper's shape:
the run window (`now_wall + procedure.max_body_ms +
commissioning-derived max_protection_ms`, the same inputs `_check_unattended_
grant` already reads) cannot exceed the admitted approval's `expires_at`
across every provider-declaring device in the lattice. Called at the seam
pre-check (best-effort, `operations.py:2120` family) and inside the worker's
grant construction (authoritative). One helper, one vocabulary, two layers.

### 2.5 The run-stream evidence event

A `provider_granted` event lands on the run's stream beside `devices_pinned`
(`coordinator.py:1357`'s mechanism, the same append-before-body discipline):
per provider-declaring device — `{feature_id, id, version, sha256,
connection_key, usb: {vendor_id, product_id, serial, interface}}` — the
grant's exact facts, digest-covered by the terminal record's `events:{run_id}`
ref. The run record can always answer "which physical interface did this
run's connection resolve to, under which contract revision".

### 2.6 The connections document

`PROVIDER_CONNECTIONS_FILENAME = "provider-connections.json"` in
`provider_settings.py`; `load_provider_connections(path,
registry: ProviderRegistry) -> ProviderConnections` — exact-byte decode, the
§1.3 schema, cross-file consistency against the loaded registry (keys ⊆ the
settings' bound keys, one identity per key, no shared identity). Loaded by
`admit_documents` beside the settings file (both bootstrap and run lanes);
`SettingsRejected`-class refusals with the `connections_schema:` /
`connections_digest_mismatch:` prefixes.

---

## 3. What is generic, what lives where

| Part | Home |
|---|---|
| Connections document schema + loader | gateway, `provider_settings.py` (new) |
| Driver Protocol + op table + URL open + runtime ladder | gateway, `content/provider_runtime.py` (new) |
| Grant construction (checks 5-7) + registry threading | gateway, `provider_transport.py` / `capture_services.py` / `documents.py` / `app.py` (wiring) |
| Window arithmetic helper + seam/worker calls | gateway, `documents.py` / `operations.py` / `app.py` |
| `provider_granted` run-stream event | gateway, `coordinator.py` |
| pyftdi dependency | gateway `pyproject.toml` (an extra — open decision 1) |
| The ftdi-control contract instance | plugin packages + the SDK's banked copy (landed; the gateway admits operator-supplied bytes, banks nothing) |
| The live FTDI transport for the STANDALONE host | SDK repo, the sibling #568 lane |
| The scripted driver double (gateway tests) | gateway `tests/` (new), journal-driven |
| The SDK-double + op-table agreement tests | gateway `tests/sdk/`, the pointer-advance leg |
| The live-device proof | NOT THIS REPO — one real-bench run, evidence recorded then (the sibling record's own closure condition; this design claims the same bound) |
| Commissioning-shape promotion (endpoint into the commissioning document) | a future execution-standard train, named reopen trigger (§1.3c) |

**No in-repo deferrals.** The complete runtime — document, loader, grant,
runtime, wiring, evidence, tests, docs — lands in this repo in this work. The
only things outside it are the four rows above that genuinely cannot live
here (hardware, the sibling repo's transport, a corpus train this increment
does not open, and the pointer leg the #408 order rule already sequences).

Landing order (one RED→GREEN slice per commit, the FAST lane each):

1. the connections document + loader + schema (+ tests; RED: the absent
   document with bound keys refuses);
2. the runtime module + grant construction + registry threading (+ tests;
   RED: the runtime-less posture — today's `NotImplementedError` — is the
   B0 control's starting red);
3. the window arithmetic + seam pre-check + `provider_granted` event
   (+ tests);
4. the intent-first evidence rows + the full integration run over the
   scripted double (+ the honesty arms); docs legs (operator guide,
   device-developer guide) ride their commits; the full battery once,
   immediately before push.

---

## 4. Invariant impacts

- **NEW [CTL-12] — the provider grant gate.** A provider-declaring device's
  run is granted a provider transport only when: the declared triple is
  exactly an admitted triple with an unexpired approval; the run's whole
  window (`now_wall + max_body_ms + max_protection_ms`) cannot exceed the
  approval's `expires_at`; the connection key resolves to exactly one
  commissioned USB identity not shared with any other connection; and a
  runtime whose op table covers the admitted grammar's every op is
  constructed. Refusals are typed (`provider_grant_window_exceeded:`,
  `provider_grant_endpoint_absent:`, `provider_grant_endpoint_conflict:`,
  `provider_runtime_op_unsupported:`, `provider_runtime_backend_missing:`,
  `provider_runtime_device_unavailable:`) and land at two layers (seam
  best-effort, worker authoritative) — the #260/#316 shape. The transport's
  life is the run's life; the run lease remains the binding budget (STO-4
  unchanged). *A02/A04: the grant is commissioned identity plus arithmetic on
  declared values; nothing about it is inferred, and no client can reach the
  transport — the wire surface for provider ops does not exist.*
- **[CTL-10] — no text moves; the new helper is its sibling, not its
  amendment.** The window-arithmetic PATTERN is CTL-10's; the rule is
  distinct and gets its own row (CTL-12).
- **[CON-1] amendment — the connections document joins the exact-byte
  admission family.** The settings family's twin: decode through the exact-
  byte decoder, schema in gateway source (not corpus), typed prefixes
  (`connections_schema:`, `connections_digest_mismatch:`), loaded before any
  descriptor is projected at BOTH admission lanes (bootstrap, run), required
  iff the settings bind any connection. The identity-only guarantee of the
  SETTINGS schema is restated for the connections schema in its own
  vocabulary: the only grantable fact is connection_key → USB identity.
- **[CON-10] — unchanged.** The projection still drops transport/provider;
  the grant re-derives the raw form by digest (the landed pattern).
- **[STO-*] — untouched.** No new tables, no new lock holders; evidence rows
  ride `record_evidence`; the grant event rides `append_event`.
- **[REG-2] — extended, one line:** the runtime contributes
  never-fabricate/never-retry beneath the bridge's existing dispatch-state
  honesty; the orphaned-thread residual on timeout is disclosed (§1.6).
- **[REG-4] extension — the op-table agreement test** joins the pinned
  mirror family at the pointer-advance leg (the ftdi driver table twin of
  the adapter-protocol agreement pin).
- **A-decisions:** A02 (§1.3's serial-required ruling; closed defaults), A03
  (§1.1), A04 (§1.1, §1.2, §1.5 — the classification is a constant, not a
  judgement), A06 (§1.6), A07 (§1.5), A12 (no envelope motion), A13 (zero
  interface motion, arm C1).
- **Obligations walked:** 3 (device-developer guide: the refusal family the
  adapter sees, the intent-first rows), 4 (operator guide + README: the
  connections document, its schema posture, the refusal family, the install
  extra), 10 (pyftdi dependency — pyproject + uv.lock together), 16 (THIS
  DESIGN is the row's reopen trigger answered; the row's text gains a pointer
  to this record — the endpoint surface exists now, the promotion sentence
  stands), 17 (the §8.1 stream-trio field set joins the hand-carried
  twin family with its own spelling test), 20 (no new version literals — the
  connections schema carries none), 6/8/13/21 (NOT touched — zero corpus
  motion; stated because the design considered and rejected the commissioning
  promotion, §1.3c).
- **CI cost:** `gates` gains pyftdi's install (an extra — open decision 1)
  and the new tests; no new lane; no timing-lane motion (all injected
  clocks/doubles — no real-clock bounds); `windows`/`win-core` untouched
  (USB device code is CI-absent by the double; the import probe is the only
  platform-adjacent arm and is typed-refusal-shaped).

---

## 5. Pre-committed acceptance rule

Written before any measurement ran. All arms are deterministic conformance
over the scripted driver double; no arm exercises a device, and neither this
record nor the PR body may be written so a reader concludes otherwise. All
measurements are this lane's, on this machine.

**Metric A — the commissioned run over the double (the demo).** A fixture
lattice (in-test: a provider-declaring descriptor pinning the ftdi-control
contract bytes, settings admitting the exact triple, the connections
document binding the key to an invented USB identity, and a one-invoke
procedure whose adapter performs the recorded bring-up conversation) runs
through the FULL worker path — admission, seam pre-check, grant
construction, bridge dispatch — with `ScriptedGatewayDriver` (the
journal-derived double) at the driver boundary: every step event `ok`, the
run completes with the protective transition verified, the double's op-call
sequence equals the journal's provider rows exactly (op, params, order), and
the `provider_granted` event carries the triple and the endpoint identity.
Denominator: the journal's provider-row count, stamped in the fixture.

**Metric B — the RED controls (6/6 must fail loudly; each reddens its named
test with the production mechanism reverted or the fault planted):**
- **B0 — the mechanism-disabled control (the non-gameable core):** with the
  runtime injection reverted (runtime=None — today's posture), the SAME
  fixture run refuses at first transfer (`NotImplementedError`, no provider
  runtime) and no step completes. The effect disappears when the mechanism
  does.
- B1: an un-admitted triple (one hex flipped in the settings' sha256) →
  `provider_not_admitted:` at admission; the run never starts.
- B2: the approval expires inside the run window (expires_at = start +
  max_body/2) → `provider_grant_window_exceeded:` at the seam pre-check and
  at the worker.
- B3: two connection keys sharing one USB identity → `connections_schema:`
  at load; one key with no identity → `provider_grant_endpoint_absent:`.
- B4: a contract whose grammar carries an eighth op →
  `provider_runtime_op_unsupported:` at grant construction, before the
  device opens (the double records zero calls).
- B5: the driver faults mid-conversation → the dispatch after entry poisons
  (`unknown`), the body ends `outcome_unknown`, and the double records
  exactly one call (no retry).

**Metric C — the honesty arms (6/6 must pass):**
- C1: zero interface motion — `standards/interface/0.1.1/` byte-identical
  (the existing corpus-pin tests stay green untouched; no new REST operation,
  no MCP tool).
- C2: the refusal-prefix family is machine-matchable — a spelling test pins
  every prefix named in §1.2/§2 against the emitters.
- C3: the connections schema refuses every non-identity shape — planted
  `url`, `path`, `host`, `port`, `token`, `command` fields all refuse
  `connections_schema:` (the identity-only pin, tested by plantation).
- C4: intent-first — an energising op whose evidence write fails (a
  store-failure double) records ZERO driver calls and refuses
  `provider_runtime_audit_refused:`.
- C5: the protective carve-out — the SAME store failure under a `protect:`
  operation dispatches the safe action (the driver call happens), and the
  disclosure lands at close.
- C6: the run record answers the grant question — `provider_granted` carries
  `{feature_id, id, version, sha256, connection_key, usb identity}` for
  every provider-declaring device, before any body event.

**Ship direction:** A, B (6/6) and C (6/6) pass.
**Kill direction:** any B control passes clean (the grant or its refusals
are not pinned — the increment's core claim is false; kill the design, not
the test); any C arm fails (an honesty surface is missing; blocker, the ship
claim is dead until it holds).
**Underpowered direction:** A fails on an unmutated, journal-derived script →
the SCRIPT or its conversion is wrong evidence, not the mechanism (diagnose
by the first divergent op; the journal is the arbiter); B1 failing would mean
the settings fixture never loaded — a fixture bug, re-derive the control.
**Denominators:** B = 6 controls; C = 6 arms; A = the journal's provider-row
count. Whose measurement: this lane's, this machine, deterministic,
double-driven — the only live-environment arm is the pyftdi import probe
(B-class, refusal-shaped), which proves a refusal, never a device answer.

---

## 6. Risks, ranked, with falsifiers

1. **The gateway mirror drifts from the SDK executor** (op table, URL
   semantics, receive ladder). The contract's grammar is the shared
   authority both compile against (B4/arm-2); the pointer-leg agreement test
   pins table equality. Until the pointer advances, drift is caught only by
   the grammar check — DISCLOSED RESIDUAL. Falsifier: the agreement test,
   when it lands.
2. **pyftdi under strict mypy / API drift** (the sibling record's risk 4,
   shared): the Protocol isolates the import to one function; the bounded
   range `pyftdi>=0.56,<1` is the drift fence. Falsifier: fresh-cache bare
   `uv run mypy`.
3. **The intent-first row adds latency to energising ops** (one
   content-addressed store write before each). The ops are bring-up-class
   (single-digit per run), not per-sample. Falsifier: none needed at this
   count; re-open if a per-sample energising op ever exists.
4. **The orphaned-thread timeout residual** (§1.6): a driver call that
   orphan-completes after the deadline fired. Inherited from the serial-lane
   posture; the record stays honest (UNKNOWN). Falsifier for the honesty
   half: B5.
5. **The connections document becomes the de-facto commissioning surface and
   rots** (the promotion never happens). Mitigated by the named reopen
   trigger (§1.3c) and the `provider_granted` event making the split visible
   per run. Human-lane residual.
6. **A second provider family arrives and the FTDI-specific shape
   misfits.** The runtime is one family's executor, deliberately (the
   sibling record's row e); the registry question re-opens on the second
   family. Low.
7. **Lane collision:** none (pre-flight §0.10); the SDK lane touches only
   the SDK repo; no gateway branch or open PR carries provider-runtime work.
   The pointer leg is sequenced by the standing #408 order rule.

---

## 7. Review tier and the Step-1 keyword scan (#254)

**Tier: 3**, several independent triggers, any one sufficient:
- *adds a dependency* — pyftdi joins `pyproject.toml` and `uv.lock` (an
  extra, still a dependency row);
- *touches the persisted-format surfaces* — `src/benchweave/control/
  documents.py` (the threading + window helper + admission extension);
- *adds refusal paths* — the `provider_grant_*:` / `provider_runtime_*:` /
  `connections_*:` families extend the machine-matchable prefix surface;
- *diff text keywords* — `sha256`, `asyncio`, `threading`, `protection`
  (below).

No standards-governor trigger: zero `standards/` bytes, no vendored-tree
motion, no submodule pointer inside this slice (the pointer leg is the
standing release-train discipline, not this design's diff). G6 adversarial
refute is mandatory at review.

**Keyword scan** — `re.findall` over this record's §1-§6 (the mechanism,
ruling, and acceptance text the diff will implement). The counts below are
that run's ACTUAL output (run 2026-10-28, after the record was written; the
review re-derives the scan over the real diff, whose counts will be higher
where code and tests repeat the sites):

| Keyword | Measured over §1-§6 | Source in the expected diff |
|---|---|---|
| `sha256` | 3 | the triple/digest sites (§1.4's one authority, §2.2, §2.5's event); the real diff's loader, grant event and B1/C6 tests multiply them |
| `hashlib` | 0 | no import site named — the digest rides the existing exact-byte decoder; the real diff's loader may carry one |
| `asyncio` | 3 | the `asyncio.to_thread` driver calls (§2.3) and the bridge-timeout discussion (§1.6); the real diff's tests import it |
| `threading` | 3 | the orphaned-thread residual discussions (§1.6, §6.4); no reader thread is built — the receive loop is deadline-paced |
| `subprocess` | 0 | rejected boundary; keep it out of the diff |
| `migrate` | 0 | — |
| `recovery` | 0 | recovery semantics untouched (a found run records `interrupted`; no resume) |
| `protection` | 6 | the protective carve-out and transition discussions (§1.1, §1.5, C5, §6) — protective content in the diff text by construction |

`sha256` alone settles Tier 3 under first-match; the path rules reach it
independently (documents.py, pyproject/uv.lock).

---

## 8. Open decisions for the maintainer

1. **pyftdi's install shape:** a gateway extra (`benchweave[provider]`,
   recommended — benches without USB devices carry no transitive
   pyusb/libusb, and a provider-descriptor lattice on an extra-less install
   refuses `provider_runtime_backend_missing:` at startup admission, loud and
   early) vs an unconditional dependency (simpler, heavier default install).
2. **Serial REQUIRED in the USB identity** (recommended, §1.3b — ambiguity
   unrepresentable) vs optional-with-first-match (lighter, silent
   wrong-device risk). The reopen for optional: a real bench presenting an
   unserialised device the operator must commission.
3. **The connections document's filename** (`provider-connections.json`,
   recommended — pairs with `transport-settings.json`) and whether it loads
   only beside a settings file that binds connections (recommended — §1.3b's
   presence rule).
4. **Whether `stream_send`/`stream_exchange` join the intent-first family**
   (recommended NO — delivery class, the dispatch is the audited intent, the
   residual stated in §1.5's table; changing this later is additive).

**Maintainer rulings, 2026-10-28 — all four recommendations adopted.** These
are decisions, not options:

1. **pyftdi rides a `benchweave[provider]` extra.** A bench without USB
   devices carries no transitive pyusb/libusb, and a provider-descriptor
   lattice on an extra-less install refuses `provider_runtime_backend_missing:`
   at startup admission — loud and early, not at first transfer.
2. **`serial` is REQUIRED in the USB identity.** Wrong-device ambiguity is
   unrepresentable rather than mitigated. The recorded reopen for the optional
   shape: a real bench presenting an unserialised device an operator must
   commission.
3. **The document is `provider-connections.json`,** pairing with
   `transport-settings.json`, and it loads only beside a settings file that
   binds connections.
4. **`stream_send`/`stream_exchange` stay OUT of the intent-first family.**
   The dispatch is the audit unit and CTL-6 already records the invoke's
   resolved input; wire-level intent beneath it is review surface, and the
   residual is stated in §1.5 rather than papered over. Widening later is
   additive.

**Owner posture for this lane: NO DEFERRALS.** The runtime lands whole in this
slice. Nothing is filed as an issue and nothing is parked; the only work that
stays outside is what cannot live in this repository.

## 9. What this design could not resolve

- **The pyftdi call surface is inference** (§0 flag) — the Protocol mirrors
  the sibling record's spelling, which is itself in flight; the first build
  run falsifies or corrects it, and the pointer-leg agreement test holds it
  after.
- **The live-device acceptance stays open and unclaimed**, exactly as the
  sibling record bounds it: nothing here exercises the seven control calls
  against hardware, and closure is one real-bench run's recorded evidence —
  the increment ships on the double-driven arms alone.
