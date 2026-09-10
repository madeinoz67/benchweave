# Integrated architecture acceptance review — STG 1.5

**Method:** Trace each scenario through interface, coordinator, OTDP integration, policy/protection, evidence and recovery. This is design review, not an executed behavioural test.

## Resolved cross-contract findings

| Finding | Resolution |
|---|---|
| Manual lease counted as a conflicting owner during its own run start | The same principal's valid lease is the authority for that manual run. Other leases/runs conflict; the lease is not a second procedure |
| Terminal status required a persisted record during an audit/storage failure | Interface 1.1.0 permits a missing terminal_record only with outcome_unknown/interrupted; passed still requires retained terminal evidence. The summary explicitly exposes the evidence gap |
| Parsed document content could not reproduce a byte-addressed SHA-256 | Interface 1.1.0 additionally returns original_utf8_base64; its exact bytes must hash to document.sha256 and parse to the returned content |
| Procedure budget could finish before qualification expiry but protection could run past it | Admission requires the body plus full protection budget to fit the qualification validity interval |
| Repeated monitor faults could repeatedly restart the protective deadline | First protective entry fixes the deadline; later faults append/escalate evidence without renewing the budget |
| Shared/wrapper descriptors risked duplicate profile definitions or circular dependencies | Distinguish profile ownership from consumption, allow one-way wrapper dependencies and enforce one physical instrument instance |
| Observer summaries did not explain absent terminal evidence | A null terminal_record is an explicit unrecoverable/pending evidence gap, never an implied successful final report |

## Scenario matrix

| ID | Trigger | Required response | Evidence and recovery | Acceptance owner |
|---|---|---|---|---|
| E01 | Discover and adopt a shared plugin | Resolve verified compatible closure; local approval and qualification before activation | Exact release/lock/configuration pins | Registry + bench owners |
| E02 | Valid unattended run | Reserve resources, persist acceptance, execute bounded body, verify safe ending | Passed only with complete terminal record and verified safe state | Coordinator + test owner |
| E03 | REST start response lost, retry via MCP | Return the same run under identical deduplication scope/key | Request tombstone; no second physical dispatch | Interface + coordinator |
| E04 | Check passes, fixture changes before start | Recheck generation/identity/qualification and reject | Admission finding; no energising operation | Coordinator |
| E05 | Manual run starts using its own valid lease | Reuse that authority; exclude other controlling work | Lease/run association and expiry deadline | Coordinator |
| E06 | Manual lease expires during dispatched work | Stop body when possible; preserve uncertain operation; execute protection | Unknown outcome retained; expired lease cannot revive | Coordinator + protection |
| E07 | Client/token lost during gateway-owned run | Continue only the already approved bounded local run | No expanded authority; local monitoring and final evidence | Identity + coordinator |
| E08 | Stale, wrong-unit or invalid measurement | Invalid predicate terminates body; no false-branch fallback | Acquisition age/quality and safe transition | Evidence + policy |
| E09 | Assertion false | Stop body and protect | assertion_failed only if final safety verified; otherwise outcome_unknown | Procedure engine |
| E10 | Configuration partly applied/acknowledgement lost | Invalidate configuration token; no dependent action/replay | Partial/unknown operation evidence and reconciliation | Integration + coordinator |
| E11 | Interlock trips; repeats every poll | Immediate qualified protection; first deadline remains fixed | Latched reasons; escalation never resets timeout | Protection |
| E12 | Software disable times out | Independent response as qualified; remaining safe steps bounded | Final safety verified independently or outcome_unknown | Protection + bench owner |
| E13 | Local takeover | Revoke remote execution; software must not fight operator control | Takeover authority, reconciliation and separately qualified protection | Bench owner |
| E14 | Cancel races with terminal completion | Retain the first established terminal result; cancel cannot reverse actions | Ordered occurrence/event history | Coordinator |
| E15 | Gateway process/host restarts | No body resume or automatic energisation; reconcile physical state | Interrupted/unknown evidence, durable request IDs | Runtime + bench owner |
| E16 | Active dependency becomes revoked | Block subsequent starts; active work follows pre-approved protective response without mid-call plugin replacement | Status sequence/digest, affected closure, protective outcome | Registry + coordinator |
| E17 | Registry unavailable or freshness exceeded | Existing qualified work stays bounded; new starts obey offline freshness gate | Cached approval/status age; no invented freshness | Registry + bench owner |
| E18 | Audit storage fills before acceptance | Refuse new energising run; protect existing work independently | Capacity fault and available retained evidence | Evidence service |
| E19 | Audit storage fails after acceptance | Protect regardless of storage; report evidence gap and never passed without terminal record | In-memory status may be lost; recovered unknown/interrupted record does not fabricate history | Evidence + coordinator |
| E20 | Event cursor overtaken by retention | Explicit gap; re-read run snapshots and available final evidence | Stream/watermark recovery, at-least-once deduplication | Interface |
| E21 | Admin applies change while busy/stale | Reject, do not queue surprise activation | Approval target/generation and rejection | Administration |
| E22 | Firmware/fixture/device replacement | Invalidate relevant qualification and arming | New identity/configuration generation and new evidence | Bench owner |
| E23 | Declared qualification expires before worst-case protection ends | Reject before acceptance | Conservative body + protection time calculation | Admission |
| E24 | Restored store loses deduplication/event continuity | No ambiguous replay; new identity/stream only through documented recommissioning/reconciliation | Restore record and prior-run uncertainty | Runtime + administrator |
| E25 | Two selected descriptors name the same physical device | One instance/ownership domain; reject conflicting configuration | Resolved identity and resource closure | Integration + coordinator |
| E26 | Raw document bytes are changed without updating the digest | Reject document integrity before binding/admission | Original-byte SHA-256 mismatch | Content/evidence store |

## Required acceptance evidence

For each scenario, future implementation verification must record exact software/contract revisions, setup, fault injection, observed state/command trace, timing, expected versus actual result and reviewer. Runtime mocks can demonstrate software logic; physical timing, isolation, contact state and independent protection require appropriate bench evidence. All applicable cases must pass before the relevant support/qualification claim.

No scenario is marked hardware-passed by this document. Architectural closure means its trigger, responsible component, mandatory response, retained evidence and recovery are now defined. Numeric timing, safe limits, provider contracts and identity/signing deployment values remain mandatory qualification inputs.
