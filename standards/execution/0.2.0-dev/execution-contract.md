# STG procedure and bench contracts 1.0.0

**Architecture companion:** STG 1.5; OTDP 0.2.2; adapter API 0.1.0; registry contract 0.1.0.  
**Status:** Architecture/schema baseline for bounded sequential tests. No procedure engine, policy evaluator or hardware driver is implemented.

## 1. Responsibilities and selected scope

A portable procedure defines what to test. A bench definition identifies equipment, wiring, shared resources and evidence inputs. A safety policy defines the commissioned operating envelope and protective response. A commissioning record binds their exact revisions and qualification evidence. The run record preserves the accepted binding, outcomes and physical-state assurance.

| Choice | Consequence |
|---|---|
| Bounded structured procedure — selected | Static admission, explicit state and finite execution budget; constrained portability |
| General Python or script procedure | Broad flexibility, but arbitrary behaviour cannot be admitted using this contract |
| Full workflow language with distributed/parallel branches | Additional scheduling and recovery semantics beyond the initial one-procedure bench |

The initial language supports class invocation, scalar core read/write, delay, scalar dataset selection, assertions, conditional branches and fixed-count loops; the reviewed language extension this revision adds is single-channel core capture, which dispatches a bounded capture request through the retained core capture verb and lands the capture manifest as the step's result. It excludes arbitrary code, external network requests, dynamic discovery, recursion, unbounded loops, concurrent branches and cross-gateway execution. Array analytics, free-form expressions, interactive human steps, streaming loops and arbitrary core maintenance verbs require a later reviewed language extension. Exclusions do not remove underlying instrument capabilities.

JSON is the normative representation. Parsers reject duplicate keys, nonfinite numbers and unknown ordinary fields. Every referenced contract resolves from an admitted local immutable artefact using ID, version and SHA-256; no runtime download is permitted. Versions match exactly. Schemas establish structure; semantic rules below are also mandatory.

## 2. Portable procedure and binding

`procedure.schema.json` defines a versioned procedure, required role/profile combinations, ordered steps, execution mode, body deadline and separately bounded safe-transition budget. A procedure lists the safety-policy ID/version it was reviewed against. Portability means the same procedure can be bound to another separately qualified bench satisfying that contract; it does not mean any similar power supply is interchangeable.

Each role binds to one commissioned instrument instance. Role channel aliases bind to actual declared device channel IDs. Required profiles must be present in the pinned descriptor and all invoked actions must be declared. Devices sharing resources are not made independent by assigning different role names. The bench coordinator reserves the transitive closure of all role resources and protective dependencies before accepting a run; partial reservations are released if admission fails. The existing one-active-controlling-procedure rule remains in force.

Procedure contents cannot embed network endpoints, credentials, instrument discovery patterns or policy updates. The run admission request supplies logical-role bindings, a local package-lock reference, bench/policy/commissioning references and a principal. The host authenticates the principal; a value in a document is not proof of identity. Every reference is pinned before execution. Runtime changes invalidate the affected admission rather than reinterpreting an active run.

## 3. Step language

Step IDs are unique across the whole procedure, including nested bodies. Each invocation receives a stable occurrence identity `(run_id, step_id, loop-index-path)`. Reconnect/repeated submission returns the existing occurrence; it does not repeat physical work. Repeating a step in a fixed loop intentionally creates a new occurrence.

| Kind | Contract |
|---|---|
| `invoke` | Dispatch an exact OTDP class action on a bound role, with a positive timeout and structured input |
| `read` | Read one named scalar parameter through the existing core read operation |
| `write` | Write one named scalar parameter through the existing core write operation; policy checks apply |
| `delay` | Wait a finite duration using the host monotonic clock; monitoring remains active |
| `sample` | Extract one scalar variable from an earlier successful class dataset, with explicit unit, freshness and uncertainty requirements; no new I/O |
| `assert` | Evaluate a numeric sample against inclusive lower/upper bounds; false terminates the body as a test failure |
| `if` | Evaluate the same predicate and execute exactly one statically declared branch |
| `repeat` | Execute a nonempty body exactly count times unless interrupted; positive fixed count and nested expansion limits apply |
| `capture` | Dispatch a single-channel core capture on a bound role with a capture-scaled timeout; the capture manifest lands in scope as the step's result |

Core read maps to arguments {parameter}; write maps to {parameter, value}. Invoke maps to {action_id, input}. Capture maps to {format, sample_count, max_bytes}; the capture id is not authored — the host mints it per occurrence and returns it in the capture manifest. Action input channel aliases are role-scoped; scalar parameters retain their exact descriptor names. An empty required_profiles list is permitted for a core-only role.

Every action is validated twice: structural/profile/device checks during admission wherever values are known, then fully after references resolve and immediately before dispatch against current policy and state. The scheduler may shorten a timeout to the remaining body deadline but never extend it. The procedure language never enables automatic state-changing retries; transient polling/recovery must not become a hidden replay of an action.

### Input references and host-issued IDs

JSON action input permits literal JSON, or reserved reference objects, recursively at any value position:

- `{"$stg_ref":{"step":"configure","pointer":"/configuration_id"}}` selects from the earlier step's successful `data.result` for invoke, or `data` for scalar core operations. A pointer into a capture step's result addresses the capture manifest the step landed: the six members every capture manifest must carry — `capture_id`, `format`, `artifact_id`, `byte_length`, `sha256` and `started_at` — are present and resolve as typed members (so `/capture_id`, `/artifact_id` and `/sha256` always resolve), and the waveform-conditional members `sample_count`, `sample_interval_s` and `unit` resolve when the landed manifest carries them (presence-filtered — the schema requires them only for `waveform_f64le`). Pointers use RFC 6901 syntax and exact types; no string interpolation, coercion, arithmetic or evaluated code exists.
- `{"$stg_channel":"output"}` resolves a channel alias for the current action's role.
- `{"$stg_issue":"configuration_id"}` or acquisition_id requests a fresh gateway-issued ID for the current occurrence, scoped to device generation and ownership. Admission permits each only at the corresponding required input field of a configuring or arming action; never as an arbitrary replacement for another action's token.

Objects containing a reserved key must match that reference form exactly. Ordinary input cannot smuggle unrecognised `$stg_` directives. Resolve first, then validate against OTDP schemas. Issued IDs are retained with the operation occurrence and echoed/verified by results. A failed/unknown configuration invalidates its issued ID. Any failed reference resolution terminates the body before dispatch; null/missing/wrong-type values do not receive defaults.

References may address only an earlier sibling in the current block or an earlier step in an enclosing block. Inside repeat they refer to the current iteration's preceding results. Results defined inside a repeat or branch are not visible outside that block; no implicit “last iteration” or branch merge exists. References across future steps, sibling branches or previous iterations are rejected at admission. No mutable variable store is provided. Typed result references in read/write are available to later action input but are not directly scalar assertion samples in this revision; class datasets provide the assertion path.

## 4. Assertions and trustworthy samples

`sample` accepts a previous invoke step whose typed result is an admitted `scalar_set` dataset. Select exactly one variable by ID; it must contain one finite numeric inline value with no dimensions. Other dataset kinds, multiple values, encoded payloads and missing variables are rejected by this initial scalar assertion contract. The variable's unit must exactly equal the requested canonical unit; no implicit scale or temperature conversion occurs.

Sample validity requires valid dataset/variable status, correct source/configuration provenance and a known conservative age. Freshness is measured from acquisition, not from the time sample is selected or fetch completed. The host uses a qualified device-to-host clock mapping, or a documented bound on acquisition-to-receipt age; unknown timing cannot satisfy a finite max_age_ms. Source uncertainty and clock uncertainty are retained independently. Host receive time alone cannot refresh an old instrument buffer.

When require_known_uncertainty is true, an absolute uncertainty satisfying the measurement-model contract is required. The predicate uses a conservative interval [value − absolute uncertainty, value + absolute uncertainty]; pass requires the whole interval inside the inclusive bounds. If uncertainty is unknown and the sample explicitly permits it, nominal-value comparison is allowed and the result records that limitation. This comparison is a test criterion, not a substitute for independent protection or a metrology conformity standard.

Predicates have three outcomes: true, false or invalid. Invalid/stale/wrong-unit/unknown-required-uncertainty evidence terminates the body with execution_error; it never selects the false branch or becomes a passing assertion. Freshness is rechecked at predicate evaluation. A false assert yields assertion_failed. A false if selects else; both branches must have been admitted in advance. No branch may expand authority beyond the reviewed procedure/policy.

## 5. Run lifecycle and budgets

`accepted → running → protecting → terminal` is the normal lifecycle. Before acceptance, failures are admission rejections and do not create an energising run. Accepted but undispatched runs can be cancelled. Admission alone never energises a device. Manual mode requires an active client lease; lease loss ends the body and invokes protection. Gateway-owned mode may continue through client disconnect only within the approved unattended record and body deadline.

The body budget starts at acceptance, including any delay before dispatch. The protective budget starts when protecting begins. started_at in the terminal record is the acceptance wall time; phase timestamps are retained in event evidence. The host uses monotonic elapsed time for body and protection deadlines. Wall time is for audit and external freshness mapping, never elapsed-time enforcement. The worst-case static body bound is the sum of invocation/read/write/capture timeouts and delays, multiplied through repeat counts, taking the larger if branch. Sample/assert processing remains subject to the overall deadline and configured step/CPU limits. Admission requires the calculated wait/I/O bound to fit max_body_ms, with commissioned scheduling overhead also accounted for. Hosts set finite maximum nesting, expanded steps and document size; exceeding a limit is an explicit rejection, not truncation. Step timeouts and the body and protection budgets are additionally bounded by the schema's contract ceiling (86400000 ms — one day): a finite authoring bound that makes a day-scale budget an authoring error on a local bench and keeps the host's nanosecond-to-seconds deadline conversion orders of magnitude inside float64's finite range.

Disclosure (fold wave, issue #176 increment 2 — F11): a wall timestamp with no UTC offset (a naive ISO-8601 stamp) is read as UTC. An offset-less stamp denotes an instant only up to the sender's UTC offset, so a device that stamps local time shifts every freshness comparison by that offset, with no refusal on the stamp itself — 8 hours for a UTC+8 sender: an AWST-local `started_at` reads 8 hours late, understating acquisition age by 8 hours so stale evidence can satisfy a finite `max_age_ms`. Commissioned devices must emit `+00:00`/`Z` for offset-exact evidence; the parse fix (refuse the naive stamp, or capture its offset) is deferred with the clock/time-seam row, its dissent recorded in the design record.

Every operation and data producer has independent output/storage quotas enforced by the host and existing OTDP limits. Time limits alone do not bound dataset size. The policy's maximum energised duration applies across delay, polling and fetch and may be shorter than the overall body budget. Admission conservatively requires max_body_ms plus the protective budget to fit every relevant domain's max_energised_ms unless a separately qualified tighter energisation analysis is provided; this revision supplies no such analysis extension.

Body completion, false assertion, execution error, cancellation, deadline, trip, lease expiry or takeover initiates the approved safe transition. No user-authored finally/cleanup block can replace it. Future procedures needing a persistent energised terminal condition require a separately reviewed extension; this initial contract always ends in the policy's verified safe condition.

The first entry to protecting fixes its deadline. Further faults append/escalate reasons and do not restart the transition or extend its deadline. Safe transition has its own bounded budget and protective authority so body deadline/cancellation cannot suppress it. On ordinary completion it executes before terminal success. On trip, independent protection acts immediately as qualified; software transition is supplementary. Local takeover prevents software fighting the operator; protective response still follows the commissioned takeover plan. Scheduler priority never bypasses physical-resource reality, and a hung transport cannot be assumed pre-emptible.

Terminal outcome and final physical assurance are separate:

| Body outcome | Recorded terminal outcome, if safe condition verified |
|---|---|
| All steps completed and assertions passed | passed |
| Assertion false | assertion_failed |
| Cancellation or manual lease expiry | cancelled |
| Deadline | timed_out |
| Protection trip | tripped |
| Invalid evidence/protocol/other error | execution_error |

An uncertain operation remains recorded as outcome_unknown even if subsequent protection verifies safe; later safety does not erase uncertainty about the test. If safe condition cannot be verified, terminal outcome is outcome_unknown regardless of an apparently passing body. The body outcome and all reasons are retained. No report can say passed while final safety is unknown.

After gateway restart, durable runs that were not terminal are recovered as interrupted with unknown physical assurance until reconciliation. Body execution and energisation never resume automatically. Retained operation identities suppress replay but do not promise exactly-once physical execution. Final evidence may be appended after reconciliation without rewriting the original interrupted record.

## 6. Bench configuration

`bench.schema.json` defines immutable configuration identity/revision, gateway and fixture identity, DUT qualification class, pinned descriptors, device generations, channel maps, shared resources, wiring endpoints, monitored signals and references to policy/package lock/commissioning.

Devices use a commissioned identity record ID and locally configured connection_key. The connection key resolves through administrator-owned transport settings and secret storage; it is not an endpoint supplied by the procedure. Serial-less/passive equipment uses a documented identity method and replacement detection in that record. Swapping a device, firmware, fixture revision, policy or admitted implementation invalidates affected qualification and creates a new configuration generation.

The bench lists DUT identities and protection mechanisms with resource IDs and implementation-evidence references. Each signal names its resource so monitoring/protection dependencies participate in reservation. Independent-protection evidence describes the physical mechanism; its presence is not a claim that software controls or supplies that mechanism.

Every terminal has an owner (device instance or DUT), channel ID where applicable, terminal name and electrical domain. Nets explicitly list connected terminals. All references resolve; a terminal appears in at most one net. Potentially shared paths, buses, outputs, loads and protection equipment are grouped into named resources. Reservation uses the transitive dependency closure, and cycles/conflicting identities are rejected. A wiring diagram reference is useful evidence but does not replace the machine-readable connections. The topology records declared connections; it does not prove continuity or isolation.

Signals are read-only evidence bindings: an OTDP scalar parameter or a locally admitted host-input contract. A signal declares quantity, unit, polling period, maximum age, absolute_error and authoritative source. Numeric protective inputs require a finite nonnegative absolute_error justified by qualification evidence; null means unknown and cannot satisfy a numeric protective condition. Boolean signals use null and a qualified discrete-state/failure contract. The error bound includes the admitted measurement chain and operating conditions, not a guessed instrument resolution. Polling periods must fit freshness limits and bus/scheduler capacity. Destructive reads and stimulus-producing reads require explicit policy/ownership and cannot be silently used as passive interlocks. A host-input contract must already specify typed value, timestamps, invalidity, isolation/failure behaviour and permissions; merely naming GPIO is insufficient.

## 7. Safety policy and protective response

`safety-policy.schema.json` is gateway-owned and immutable. It records an envelope for each electrical domain (absolute voltage/current, power, stored-energy bounds and maximum energised duration), per-device action allow rules, continuous conditions, independent-protection evidence, ordered software safe actions and verifiable final conditions.

Numeric envelope entries are requirements to be supplied by commissioning; they are not default instrument ratings. They must be physically supported by the declared fixture and protection evidence. Domain values alone cannot establish that wiring, current direction, isolation or fault energy is acceptable. Mains qualification remains a separate class. The supplied example is synthetic and grants no real control authority.

Every state-changing action, including a measurement with stimulus or destructive read behaviour, is ordinary control and is denied unless a rule matches the actual device and exact action/parameter; a capture is state-changing for the same reason (it arms an acquisition) and its rule matches the actual device and exact format. For invoke, input_constraints is an additional locally admitted JSON Schema intersected with the standard action and device constraints. Scalar write rules constrain the actual value. For capture, capture_constraints is an additional locally admitted JSON Schema intersected with the descriptor's declared capture envelope (its declared capture_formats and capture_limits). Admission meta-validates every allow-rule constraint document (input_constraints, value_constraints, capture_constraints) as Draft 2020-12 schema and refuses a malformed one before any run exists — "locally admitted" is a checked property; a constraint schema that cannot be evaluated at the policy boundary denies with the kind's refusal prefix, never an exception past the boundary. All matching rules apply conjunctively; no order-dependent allow override exists. Profiles and rules cannot weaken core policy. A core read with state-changing behaviour is excluded from this procedure revision; use an admitted typed invoke action with an explicit allow rule. Non-state-changing observation is scheduled within ownership and measurement requirements, not through a control allow rule.

Coupled input constraints may be expressed with JSON Schema where possible. Continuous measured conditions support numeric bounds, Boolean expected state, or the absolute product of two numeric signals with an explicit derived unit. Product is initially restricted to V × A → W (either order), with timing skew bounded by the condition. Numeric bounds must contain the full interval [value − absolute_error, value + absolute_error]. For the product, conservatively use (abs(value1) + error1) × (abs(value2) + error2) for the upper bound. Values have to be fresh and valid together; acquisition skew includes the known clock-mapping uncertainty. Unknown required timing or error bounds invalidate the condition. Missing/stale signals, unknown units or unsupported expressions invalidate the condition and trigger the protective response. This deliberately bounded rule set does not claim to express every physical hazard; a bench needing another invariant must have a reviewed, pinned policy extension before control qualification.

Continuous conditions apply from acceptance until the final safe condition is verified. Monitor latency, polling contention, filtering, clock uncertainty and protective response bounds are part of commissioning evidence. No implicit debounce or grace period exists. A commissioned startup that cannot meet these conditions needs explicitly reviewed staging semantics in a future policy revision, rather than disabling monitoring in the procedure.

Safe actions identify a commissioned device, exact OTDP action or scalar write, literal arguments and timeout. They are evaluated/admitted with the policy and do not depend on body outputs or valid configuration tokens for disable. They must be qualified as protective in the relevant state; a name such as output is not sufficient. Safe actions are attempted in order. A failed/unknown action is recorded, independent protection is invoked as commissioned, and remaining nonconflicting safe actions are attempted within the remaining budget. Protection must not block indefinitely on a lost device. A failed device response does not establish whether a contact opened.

Final verification is a conjunction of declared signal conditions held continuously for stable_for_ms within the protection budget. Missing/stale verification yields unknown, not safe. Signal evidence and the achieved protection mechanism are recorded. Empty safe-action lists are permitted only when commissioned independent protection performs the transition; nonempty final verification is always required for control qualification.

## 8. Commissioning and approval evidence

`commissioning.schema.json` binds the exact bench content digest, policy digest, package lock, approved procedure digests and qualification modes to named owners and evidence reports. Its ID can be referenced from the bench without embedding the commissioning record digest in the bench, avoiding circular hashes. The record is immutable and locally authenticated; its textual approval fields are not signatures.

Record fixture/identity checks, protocol/firmware qualification, operating envelope, protection-loss tests, timing/freshness, safe-transition verification, audit/storage failure and unattended disconnect/restart behaviour. Each report has a local reference and digest, test date, scope, outcome and limitations. Grant a mode only when all applicable evidence passes; a syntactically complete record with failed evidence grants nothing. Qualification expires at the recorded time and is invalidated by relevant changes even before expiry. Admission checks expiration before each run; the full body plus protective budget cannot exceed the valid qualification interval without a separately defined policy (not provided here).

Observation, supervised and unattended modes are distinct grants. Unattended requires a gateway-owned bounded procedure and its own evidence. Mains-powered DUTs require a mains-class record and applicable independent-protection evidence. Offline registry freshness remains an explicit local requirement; include maximum permitted status age in the commissioning settings. Bench-specific numerical values and actual owner identities are deployment inputs and remain unset for real hardware in this design package.

## 9. Run evidence and conformance

`run-binding.schema.json` defines the admission document described in §2. Its request_id is the artefact identity when referenced from a run; the host binds that document to authenticated principal, approval and accepted configuration generation. Within the authenticated subject/actor scope, reusing a request_id with different contents is rejected. Another principal cannot retrieve or reuse that existing association; identical textual IDs in separate authorised subject namespaces do not grant access to each other.

`run-record.schema.json` defines immutable terminal evidence with run and procedure identity, bench/policy/package-lock/commissioning references, principal, bindings, timestamps, body/terminal outcomes, final safe-state assurance and ordered operation/evidence references. Step event evidence records occurrence identity, resolved input hash, operation ID, authorisation, acquired data and outcome. Reports preserve invalid/unknown/skipped steps and reasons rather than treating missing output as pass. Skipped branch steps and unexecuted iterations are explainable from control-flow evidence.

The event log and full measurement artefacts remain separate immutable evidence objects with digests. Terminal summary fields cannot override them. Protective work remains possible during audit storage failure; incomplete terminal persistence is recovered as an evidence gap, never fabricated later as a complete successful audit.

Required semantic checks P01–P10: role/profile/action binding; unique IDs and lexical reference scope; exact typed reference resolution and issued-ID placement; static/dynamic budgets; ownership closure; trustworthy scalar selection and three-valued predicates; allowed action/policy intersection; cancellation/trip/cleanup precedence; immutable run evidence and no restart replay; accurate outcome versus safe-state reporting.

Required bench checks B01–B10: pinned identity/descriptor/lock consistency; terminal/net references; resource closure and monitor scheduling; required envelope domains; signal types/units/freshness; conjunctive allow rules; conservative coupled conditions; protective action and verification qualification; exact commissioning approvals/expiry/invalidation; offline/mains/unattended mode gates.

Before implementation conformance is claimed, exercise normal completion, false assertion, invalid sample, both branches, bounded repeated acquisition, configuration failure, timeout after dispatch, device disconnect, interlock trip, client loss, takeover, gateway restart, failed safe transition, registry revocation, evidence-storage failure and identity replacement. The included document checker covers only selected structural/semantic cases. A complete engine or hardware qualification suite is not supplied.

## 10. Distribution and remaining boundaries

The current registry defines first-class profile, descriptor and implementation packages. It does not yet define a first-class procedure package kind. A procedure can be exchanged as a pinned local document under this execution contract; catalogue discovery of procedures is an explicit future registry extension. Bench, policy, commissioning and run-binding records remain local administrative artefacts and must not be published as a side effect of sharing a device plugin.

This revision closes the bounded sequential procedure and bench-document design at the stated scope. The companion interface contract 0.1.0 defines REST/MCP wire contracts. STG 1.5 records the integrated architectural review and consolidation; implementation/qualification evidence remains separate. Host implementations must still supply the explicitly referenced input/provider contracts, configured resource limits and verification evidence before claiming support for a bench.

The interface may expose terminal uncertainty without a stored run record after evidence-storage failure. This does not weaken this document's immutable-record requirements: a record claimed to exist must validate and be retained; missing evidence is explicitly a gap and cannot support passed.
