# STG REST and MCP interface contract 0.1.0

**Baseline:** STG 1.5 · OTDP 0.1.0 · execution 0.1.0 · registry 0.1.0.  
**Status:** Architectural interface definition, not a deployed or tested server.

## 1. Selected boundaries and artefacts

REST and MCP are adapters to the same local authorised control core. They share typed requests/results, permission checks, deduplication, procedure lifecycle and evidence. The operation catalog is normative; OpenAPI 3.1.0 describes the REST surface and mcp-tools.json describes the advertised tools. Common schemas are embedded in each generated tool schema for local resolution. Neither surface accepts arbitrary device commands, code, endpoint URLs, credentials or caller-provided principal identities.

Manual control uses a short approved procedure and a renewable bench lease. This initial surface does not add an ad-hoc OTDP passthrough that could escape the procedure contract. Large document/payload ingestion, commissioning authoring, identity-provider configuration and registry publication remain local administrative or separately specified registry workflows. This API can inspect admitted content and submit/apply reviewed local changes; it cannot create its own approval evidence.

Use the accompanying operation-catalog.json for exact inputs, success bodies, permissions and routes; interface.schema.json for shared types. All JSON rejects duplicate keys, unknown ordinary fields and nonfinite numbers before dispatch. Contract versioning is independent of OTDP and MCP versions. REST v1 rejects incompatible input rather than interpreting it as another version. A major wire change requires a new route prefix/tool-name version.

## 2. Protocol baseline

MCP is pinned to **2026-07-28**, which the official versioning page identifies as current at the design review date. Compatibility with earlier revisions is not claimed by this baseline. [MCP versioning](https://modelcontextprotocol.io/docs/2026-07-28/learn/versioning)

Expose MCP at POST /mcp using Streamable HTTP. Follow the pinned revision's per-request metadata, matching version/method/name headers and Origin validation. Protocol sessions, a GET event stream and Last-Event-ID resumption are not part of this revision. STG leases and event cursors are application resources, independent of the transport. Request-stream closure cancels that request; an already committed durable run remains a separately managed resource. [MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)

Support the revision's mandatory discovery RPC and tools/list/tools/call. Only advertised capabilities are supported; this baseline does not require sampling, elicitation, MCP task augmentation or server notifications for reliable bench operation. Tool results use resultType complete and structuredContent containing the same STG result as REST, with matching text for compatibility. STG application errors set isError true; protocol errors retain MCP's native error envelope. Tool annotations describe effects, but never grant permission. [MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)

## 3. Authentication and authority

Network interfaces require TLS. MCP implements the pinned OAuth resource-server requirements, protected-resource discovery and intended-audience validation. Invalid/expired credentials yield 401; insufficient scope yields 403 with the required challenge. Tokens are not passed through to instruments or registry origins. [MCP authorisation](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)

REST uses bearer access tokens issued for its configured resource audience. The deployment records trusted issuers, allowed algorithms, audience, token lifetime/skew and revocation behaviour. MCP and REST may share a resource audience only if deliberately configured as one resource. Otherwise each audience is distinct; a trusted broker must obtain the right delegated token. No subject/principal header or document field can impersonate a user. Identity is established from validated claims and server-side mappings.

Permissions are `observe`, `control` and `admin`, intersected with server-side bench/device scope. Artifact, document, request-ID and cursor access are checked on every call, not just at creation. Shared technical service identities do not erase the initiating subject; broker deployments retain a verified actor/subject chain. Delegation may only narrow authority. A deployment without such a broker does not invent delegated identity from user text.

The three administration operations are REST-only and require separately assigned administrative authority. Standard MCP tool lists omit them. A control identity cannot approve its own package, configuration or trip reset. An admin apply request references an independently authenticated local approval record that authorises the exact change and expected generation; it is not a Boolean approved flag. Tool visibility is convenience only: the core repeats authorisation on every invocation.

A lost or expired client access token prevents new client requests, including lease renewal. It does not erase an accepted gateway-owned procedure's pre-authorised local execution authority. Explicit server-side revocation of an active authority triggers the commissioned protective response. Leased manual work terminates on expiry even when the client cannot reauthenticate. Protective execution by the gateway never depends on obtaining a fresh user token.

## 4. Discovery, documents and observations

Gateway info reports contract/protocol versions and finite supported limits. Bench/device listing returns only authorised resources and contains configuration generation, qualification/trip state, profile IDs and descriptor references; connection secrets and sensitive raw endpoint details are never returned. Reachability and a ready-looking UI do not imply permission to start a run.

Documents are addressed by SHA-256 and returned only from admitted local storage with ID/version/schema identity. original_utf8_base64 carries the exact stored JSON bytes: decoding and SHA-256 must match document.sha256, and parsing those bytes must equal content and satisfy schema_id. The server must retain original bytes; reserialising content is not a valid substitute for integrity verification. The configured JSON limit includes base64 overhead. Read permission must apply to both the document and its associated bench; knowing a digest is not access. Document size above the published JSON limit returns payload_too_large; larger binary evidence uses the chunk operation. Sensitive administrative approvals/credentials are excluded from the control document view.

Observation endpoints return retained records. They do not trigger instrument reads, drain device queues or take ownership. Fresh data acquisition requires an approved procedure and applicable ownership. Signal monitoring remains local and independent of observer polling frequency.

## 5. Check, start and durable run identity

run_check evaluates a locally stored run-binding document, schema/semantic compatibility, qualifications, limits and current generation without reserving resources or sending device I/O. It returns valid or rejected with findings and the inspected generation. It is advisory, not an admission token or permission grant. Metadata describing a physical fixture must already be qualified; the check does not probe it implicitly.

run_start supplies request_id, binding_ref, bench_id, expected_generation and a lease ID or null. Binding document request_id must match the request. Manual mode requires the caller's unexpired bench lease; gateway-owned mode requires null and the approved unattended grant. Start repeats all checks, including live protective readiness, package status age, approval expiry, fixed procedure digest, role/channel binding, resource capacity and logging capacity. The caller's own valid manual lease is the required authority, not a conflicting busy owner; another active controlling run or another owner still conflicts. A generation mismatch or conflicting busy bench fails before acceptance; no queue waits indefinitely for control.

Acceptance atomically reserves ownership, persists the principal/request/binding/run association and records intent before physical dispatch. It returns a durable run ID, revision and current state; HTTP 202 means accepted, never passed. The host-issued run ID is opaque and unique within the gateway's persistent identity. The response may already show a later state if execution progressed rapidly.

Deduplication scope is `(gateway identity, authenticated subject/actor chain, operation name, request_id)`, shared by REST and MCP. An identical repeated start returns the same run. The canonical request includes all input fields and referenced content digests; reordered JSON object keys are equivalent, arrays preserve order and JSON numeric values are compared without lossy conversion. Different content under the same key yields conflict. JSON-RPC IDs, network sessions and access-token strings are not deduplication keys.

Persist compact deduplication tombstones for the lifetime of the gateway identity: operation/subject scope, request ID, canonical input digest and resulting resource identity. Full request/result payloads may expire under retention policy; a retained tombstone then returns gone or the retained resource status, never new execution. Tombstones are included in backup/recovery. Capacity pressure blocks new admission before this guarantee is lost. A reset identity/store requires explicit recommissioning and does not accept old-identity recovery requests as new work. run_find searches the caller's run_start association, not a separate lookup-operation namespace. Clients generate globally unique request IDs and never intentionally reuse them.

If a start response is lost, use run_find with the same request_id or repeat the exact start. A not_found response is not proof that an in-flight request cannot still commit; repeating with the same key remains the safe recovery. Do not generate a fresh request ID to “retry” uncertain start. Disconnect before commit aborts acceptance if it can still be rolled back; after commit, cancellation of the request stops response work but not the durable run. Manual lease expiry and explicit run cancellation retain their separate effects.

## 6. Leases, cancellation and state

Lease creation reserves manual bench authority, not an energising state. The core rejects conflicts with existing manual or gateway-owned authority. Lease duration is bounded by commissioned policy and published server limits. Renewal requires the same authenticated owner, exact lease ID and current sequence. Each renewal increments sequence; a duplicate request returns the same renewal, not an extra extension. A late renewal cannot revive an expired lease. The expiry field is an audit wall-time representation of a monotonic deadline.

Lease release is idempotent and triggers the approved safe transition for associated manual work. Lease loss/release cannot terminate another principal's gateway-owned run. Other principals require an independently authorised takeover/protective role as commissioned; this surface does not supply a generic override flag.

run_cancel requires the run owner with current control permission or a separately authorised administrator. It is durable, idempotent and records a reason. It requests body termination and protection, not reversal of device commands or immediate physical safety. A terminal run returns its existing state. Cancellation does not require an unexpired controlling lease. An unauthenticated or unauthorised remote caller cannot invoke it; independent/local protective mechanisms remain available without that caller.

run_get returns a monotonically increasing revision and accepted/running/protecting/terminal state. Terminal body outcome and physical safety follow execution contract 0.1.0. Nonterminal outcome and safe-state fields are null; terminal outcome/safe-state values are required. A storage failure may leave terminal_record null only for outcome_unknown or interrupted. That null explicitly means final evidence is missing; even physically verified safety cannot produce passed without a retained terminal record. After a crash the summary may itself be unavailable; recovery reports interruption/unknown rather than inventing a prior record. A retrieved failed test is a successful read response with its failed outcome, not an HTTP transport failure. Clients must wait for terminal evidence before asserting completion. Busy loops or lost MCP requests cannot release ownership; only the coordinator performs the defined transition.

## 7. Pagination, events and reconnect

For REST, omit nullable cursor/after query parameters to mean null; do not send the string "null". Path fields come from the route, other GET fields from query parameters, and other POST fields from the JSON body. MCP arguments contain the complete catalog input object. The adapter reconstructs that object before shared validation.

List operations use an opaque cursor bound to principal/scope, query filters, gateway identity, dataset and snapshot. First request uses cursor null. Next cursor null marks end. A changed filter or principal cannot reuse a cursor. Expired snapshots return cursor_expired; clients restart a list and deduplicate by stable resource ID/revision. Pagination never grants access to resources removed from the principal's current scope.

Events are read with bench_id, after cursor or null, and limit. Null starts at the earliest retained authorised event, not an implicit “now”. Each event has a persistent stream ID, decimal-string sequence, timestamp, kind, optional run ID and evidence reference. Numeric strings avoid precision loss. Sequences are ordered within a stream, not across gateways. Responses include the newest issued cursor and oldest/current retained sequence watermarks. The cursor is an opaque access-scoped position, not a resource URL.

Delivery is at least once: clients deduplicate `(stream_id, sequence)`. An empty page preserves a usable cursor and clients poll no faster than the advertised interval. If retention overtakes a cursor, return event_gap with retained watermarks and require re-reading affected run snapshots/terminal evidence before continuing from a new cursor. Do not silently skip the gap. A restore that cannot preserve stream continuity changes stream ID and forces this recovery.

Both REST and MCP use this event-page contract; application recovery does not rely on a resumable MCP stream. No unsolicited notifications are required for correctness. A future push transport may accelerate updates but must preserve the same event identities, authorisation and gap behaviour.

## 8. Evidence and binary access

Evidence metadata references immutable locally retained documents/datasets/artifacts and their digests. Chunk reads take artifact_id, nonnegative offset and positive length no larger than 65536 bytes or the server's lower advertised limit. They return base64, actual bytes, total size, complete-artifact SHA-256 and EOF. At EOF an offset equal to size yields zero bytes; offsets beyond size fail. The last chunk may be shorter; intermediate chunks must supply the requested bytes or fail.

Offsets/sizes are nonnegative integers no larger than 2^53−1. The client validates decoded length, offsets, EOF and the complete digest after assembly. A whole-file digest does not authenticate an isolated chunk by itself. Artefacts remain immutable; no arbitrary paths, remote URLs or cloud credentials are accepted. Retention expiry yields gone, not a different file under the same ID. Downloads and observers cannot consume the reserved capacity needed for active protection and audit.

## 9. Administration and optimistic concurrency

change_submit records a candidate of kind package_admission, configuration_activation or trip_reset, its immutable target reference, expected bench generation and reason. It returns a change ID and proposed state; it performs no installation, activation or trip clearing. Packages/configuration/qualification records must already exist in reviewed local staging.

change_apply names that change, expected generation and a pinned approval record. It verifies independent approval, current scope, complete dependencies, relevant evidence and a safe idle boundary. If busy, stale or unqualified, it fails explicitly rather than queueing future automatic activation. Successful application increments configuration generation where relevant and records audit evidence. Trip reset requires reconciled physical state; it cannot re-arm or restart a test. A failed or uncertain application leaves an explicit failed/unknown change record and inhibits affected control until reconciled.

Administrative request deduplication follows the same rules as start. change_get reports proposed/applied/failed/unknown, current generation and reasons. The approval authoring UI/CLI and evidence authenticity belong to the local administrative boundary; a coding agent cannot supply a self-authored JSON file and treat its text as authenticated approval.

## 10. Errors, limits and transport mapping

REST successful reads/checks/renewals/cancellation use 200; lease/change creation uses 201; committed run start uses 202. Application failures use the catalog's error status mapping and a shared `{ok:false,error}` body. MCP successful tool calls use the same `{ok:true,data}` content; application failures use `{ok:false,error}` and isError true. Authentication and MCP protocol failures remain transport/protocol-native. Unknown tool methods are not fabricated as successful STG results.

Error codes distinguish invalid_request, unauthenticated, forbidden, not_found, conflict, policy_denied, not_ready, gone, cursor_expired, event_gap, payload_too_large, rate_limited, unavailable and internal_error. Details have only typed field findings, relevant revision/stream watermarks and retry_after_ms; secrets, raw device traffic and stack traces are excluded. Resource invisibility uses not_found where revealing existence would breach scope. A correlation ID links internal diagnostics.

Retry guidance is never permission to repeat physical work: same_request permits only identical content/key for a mutation, read permits repeating a read, and never requires reconciliation/correction. A 5xx or dropped connection after a mutation is potentially committed regardless of generic client retry advice; use durable lookup/same key. HTTP status alone cannot establish a physical outcome. Retry-After, where supplied, matches retry_after_ms rounded up to seconds.

The server publishes finite JSON/document limits, list page limits, chunk size, lease maxima, poll interval and admission latency budget. Excess input fails before allocation/dispatch. A reverse proxy must preserve identity and the MCP-required headers and use timeouts compatible with bounded admission; it must not retry mutations with new IDs. Numeric safety limits and procedure durations remain in commissioning, not HTTP defaults.

## 11. Acceptance and remaining work

Required interface checks I01–I12: REST/MCP request/result equivalence; no principal spoofing or cross-bench reads; audience/expiry/delegation checks; lost-start response deduplication; generation/qualification races; lease expiry/renewal order; cancellation versus transport disconnect; nonterminal/terminal consistency; event gaps and scope-bound cursors; chunk limits/digests; independently approved safe administration; and exact pinned MCP interoperability.

The supplied verification checks schemas, catalog/OpenAPI/tool mappings and selected examples. It does not run an HTTP server, OAuth flow, MCP client, event store or device. The STG 1.5 acceptance documents record registry composition and integrated scenario review. Those are architectural walkthroughs, not live conformance evidence. This interface contract intentionally does not claim older MCP clients interoperate without a separately qualified compatibility adapter.

## 12. Revision history

Supersedes interface 1.0.0 in the design package. Adds original_utf8_base64 to document results and permits a missing terminal record only for explicit uncertain/interrupted outcomes. REST v1/tool names remain; clients inspect the advertised interface version and validate against this exact catalog. This unreleased design revision makes no deployed-client compatibility claim.
