# Interface architecture review scenarios

These are contract walkthroughs, not executed tests. They identify the required decisions at each boundary and remain inputs to the later integrated acceptance review.

| Scenario | Contract result | Evidence/owner |
|---|---|---|
| REST start response lost, client retries through MCP | Same principal/actor, operation and request ID resolve to the original run; no second dispatch | Durable core request association |
| Client changes binding under the same request ID | Conflict; no new acceptance | Canonical input digest and original association |
| run_check succeeds, fixture generation changes | run_start rejects stale generation after repeating checks | Coordinator and immutable bench binding |
| Access token expires during gateway-owned run | New remote calls fail; approved local work remains bounded by its original authority | Authentication/core authority separation |
| Manual lease expires during an operation | Body stops as possible; unknown dispatched outcome is retained; protection runs | Lease deadline and execution protection evidence |
| Client reconnects after lease expiry | Renewal cannot revive authority; new lease requires reconciliation/normal admission | Lease sequence/state |
| MCP request stream closes during start | Before commit: abort acceptance if possible. After commit: durable run remains queryable; manual lease still governs manual work | Commit boundary and request ID |
| Cancellation arrives after completion | Existing terminal state returned; no invented reversal | Run revision and terminal record |
| Event cursor falls behind retention | event_gap; client refreshes run snapshots/evidence before resuming | Stream identity and watermarks |
| Observer obtains another bench's digest | Document/evidence read denied or concealed as not_found | Per-resource authorisation |
| Download crosses chunk boundary or retention expiry | Exact offset/length/EOF rules, or gone; never return replacement bytes under the old ID | Immutable artifact digest |
| AI control caller tries to apply configuration | Admin operation unavailable through MCP and rejected without independent authority/approval | Core permission and authenticated approval record |
| Admin approval is valid but bench is active | Explicit not_ready/conflict; no deferred surprise activation | Safe-boundary and generation checks |
| Test assertions pass but shutdown cannot be verified | Terminal outcome_unknown, never passed | Execution record and interface terminal schema |
| Gateway restored without event continuity | New stream identity and explicit resynchronisation; no automatic body replay | Restore/reconciliation process |

The STG 1.5 integrated review includes physical command uncertainty, local takeover, registry revocation, audit failure and whole-system recovery. Schema examples alone cannot validate these behaviours.
