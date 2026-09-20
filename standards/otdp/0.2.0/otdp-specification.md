# Open Test Device Protocol — Specification 0.2.0

**Status:** Core and twelve device-class design profiles; implementation and hardware qualification remain separate  
**Date:** 9 September 2026  
**Supersedes:** OTDP 0.2.0 for new integrations in this architecture package  
**Plugin API:** 1.1  
**Schemas:** `otdp-device-descriptor.schema.json` and `otdp-runtime.schema.json`, distributed alongside this file

## 1. Purpose and authority

OTDP describes device capabilities and provides a precise contract for translating authorised gateway operations into device protocols. It does not replace bench safety profiles, instrument manuals, access control, ownership or independent protection.

This core specification, device-classes.md, measurement-model.md, extension-contract.md, the pinned device-profile catalog and accompanying schemas are the required inputs for an AI coding agent creating a class-capable device plugin. The agent also needs the target device's protocol documentation, model/firmware information and any captured reference exchanges. Those device-specific facts cannot be inferred from OTDP. Missing command meanings, limits, identity responses or transaction details must be reported as missing inputs, not invented.

MUST/MUST NOT express requirements of this contract. SHOULD identifies a default with a documented exception. MAY identifies a permitted option. A discrepancy between prose and schema is a contract defect; neither may silently override the other.

This is a design contract, not a claim that an STG SDK or plugin loader already exists. An author targets the ABI in §8. The ABI deliberately uses standard Python types and duck-typed host interfaces so no undocumented SDK import is necessary.

## 2. Agent authoring procedure and deliverables

1. Identify exact device models, firmware, available protocols, side effects and supported commands from supplied evidence.
2. Choose `declarative` if §6 completely expresses the required operations. Otherwise choose `adapter`. Custom branding alone does not require an adapter.
3. Describe only verified capabilities. Required unsupported operations are missing integration work, not fictional capabilities.
4. Produce `descriptor.json`, validate it against the descriptor schema, and check every semantic rule S01–S19 in §10.
5. For an adapter, produce a Python package implementing §8, an exact-version dependency declaration, and tests using the scoped host interfaces. Import and construction MUST perform no I/O.
6. Supply referenced test vectors covering successful operation and applicable failure paths in §11. Every provenance reference must resolve within the package or to supplied authoritative device documentation.
7. Document the connection key, intended firmware, transport settings, limitations, safe commissioning prerequisites and evidence not yet verified on hardware.

A complete package contains `descriptor.json`, `README.md`, referenced vectors and, for adapter mode, `pyproject.toml`, the package containing the entry-point factory, and executable conformance tests. The README identifies the descriptor/spec/API versions and separates simulated evidence from hardware evidence. Paths in `provenance.test_vectors` are relative to `descriptor.json` and MUST remain inside the package.

The reference descriptors in `examples/` describe synthetic protocols defined in §12. They are suitable authoring examples; they are not validated drivers for similarly shaped commercial devices.

The agent MUST NOT create or widen bench limits, auto-install a descriptor-advertised package, access arbitrary host files/network destinations or call raw instruments outside the scoped host transport. A plugin translates approved operations; it does not grant them approval.

## 3. Descriptor model

The descriptor schema is Draft 2020-12, identified by `urn:otdp:device-descriptor:0.2.0`. It is a local artefact identifier, not a URL to fetch. `otdp_version` is exactly `0.2.0`. `descriptor_version` uses `major.minor.patch` with nonnegative integers and no leading zeroes. This revision does not accept prerelease/build suffixes.

Required top-level information is version, namespaced model `id`, display name, description, identity contract, integration mode, transport, capabilities, operation policies, parameters, required features and provenance. Exact field types and conditional requirements are in the schema. Numeric conformance levels are removed: implementation mode and capability availability are independent.

`id` identifies a model/integration, never a physical bench instance. `transport.connection_key` resolves through commissioned gateway configuration to one scoped connection. A descriptor cannot provide credentials, grant an endpoint or become trusted through self-description. Fixed transport settings describe the integration; conflicts with commissioned settings must be resolved before opening the device.

`identity` defines expected manufacturer/model and firmware policy. `listed` requires exact supported firmware values. `commissioned` requires a bench-maintained accepted identity/firmware record before control. Identity strategy `commissioned` is permitted for passive devices that do not expose a protocol identity; its results must identify that source honestly. Per-instance serial selection remains gateway configuration.

The new `invoke` verb dispatches only locally admitted versioned actions as specified in extension-contract.md. Its inputs and outputs require both runtime-envelope and action-specific validation. Every advertised verb has exactly one `operations` policy. No policies for unadvertised verbs are allowed. `identify` is mandatory; it may return commissioned rather than device-reported identity where declared. Readability/writability, capability lists and implemented behaviour must agree. An empty parameter list is permitted for an operation-only device.

`required_features` contains `otdp.core/0.1.0`, plus `otdp.adapter/0.1.0` for adapters and `otdp.passive_can/0.1.0` for declarative CAN. Class integrations additionally require otdp.profile_actions/0.1.0, otdp.measurement/0.1.0 and their exact profile IDs. An unsupported feature or version is an admission failure. Optional namespaced `x-vendor-name` fields may be ignored at schema extension points; required semantics MUST NOT depend on them.

`derived_variables` optionally declares dataset variables the host computes
from other dataset variables by fixed-grammar arithmetic expressions over
dataset variable ids (not channel ids — a channel may carry several
quantities). The grammar, static checks and evaluation semantics are
normative in measurement-model.md section 8 (M15); the machine census
`examples/derivation-vectors.json` pins both independent checkers to one
truth. An execution-side device descriptor carries the same array
verbatim and is validated by the same checks where it is admitted.

`provenance` links protocol evidence and conformance vectors. A source title is not proof of a claim: the documented revision must support the implemented operation and device version.

## 4. Parameters and write verification

Each parameter has a stable snake_case name, description, type, access, semantic role and binding. Numeric units are explicit (`1` for dimensionless values). `measurement`, `setpoint`, `state` and `configuration` distinguish meanings. A measured output cannot be substituted for a configured setpoint under one ambiguous parameter.

`float` accepts finite JSON numbers; `int` accepts mathematical integers; `bool` accepts only JSON booleans; `enum` accepts an exact declared string; `string` satisfies its length and optional pattern constraints. No implicit coercion is allowed. Strict JSON excludes NaN and Infinity. Integer encodings and cross-language transport values must remain exactly representable; values outside the interoperable integer range −(2^53−1) through 2^53−1 require another declared representation and are unsupported by this revision's numeric interface.

Writable numeric ranges are inclusive and ordered; integer ranges have integer endpoints. Enum values are nonempty and unique. Strings have finite maximum lengths. Where a string pattern is used, it must be an anchored portable expression supported by the host; unsupported expressions are admission errors. String bounds are Unicode code-point counts before protocol encoding.

Readable parameters declare `max_age_ms` and whether reading consumes or changes device state. Zero age requests a newly acquired value, not an arbitrary cached value. A passive receiver with zero age must wait for a new matching frame within the operation deadline. A positive age permits an existing sample within that age. Safety policy may impose stricter freshness.

Writes declare effect, completion requirement and retry eligibility. `hazard_class` is mandatory for writes; `unknown` is a valid honest classification. None of these fields can relax a bench envelope. The effect category is conservative for the parameter; protective actions are separately authorised by the gateway and cannot be blocked merely because ordinary writes to the same parameter may energise equipment.

`readback` verification refers to a readable compatible setting/state parameter. `physical` verification refers to a readable measurement/state supporting the claimed condition. Numeric verification requires `absolute_tolerance`; enum/bool/string verification is exact. The verification deadline is the earlier of the operation deadline and `settling_timeout_ms` after dispatch. A verified write reports the effective value and reading. Lower assurance must not be reported as success when higher assurance was required. Cross-instrument or independent verification remains a gateway procedure responsibility.

An integration MUST NOT silently round or clamp an unsupported requested value. Nonrepresentable requests are rejected. Device behaviour that rounds must be documented and confirmed by readback; it cannot be disguised as the requested value.

## 5. Runtime envelopes and operation policies

Use `otdp-runtime.schema.json#/$defs/operationRequest`, `operationResult` and `event` for machine validation. Requests carry `operation_id`, `verb` and typed `arguments`. Results repeat both identity fields. The gateway supplies operation IDs; an adapter must never replace them.

| Verb | Arguments | Successful data |
|---|---|---|
| `identify` | Empty object | Manufacturer, model, nullable serial/firmware, source |
| `read` | `parameter` | Reading with value, unit, observed time, age, quality and source |
| `write` | `parameter`, `value` | Requested/effective values, achieved assurance and optional verification |
| `self_test` | Empty object | Diagnostic verdict, summary and details |
| `get_errors` | Empty object | Error entries plus `more` flag |
| `capture` | Host capture ID, format, sample count, maximum bytes | Finalised capture manifest |
| `stream_subscribe` | Host subscription ID, parameter names, minimum interval | Subscription ID |
| `stream_unsubscribe` | Subscription ID | Subscription ID |
| `reset` | Empty object | Explicit acknowledgement |

Operation policy sets a positive timeout, side-effect class, cancellation support, retry eligibility and required completion. The host supplies an absolute monotonic deadline no later than its own remaining budget. The plugin must not extend it. The policy is an outer limit, not a recommended blocking duration.

`ok` means the verb's declared criterion was met. `error` means a known failure and does not imply that no physical action occurred. `unknown` means the physical outcome is indeterminate. `cancelled` means cancellation was handled and is not a promise of rollback. Non-ok results contain a stable error code, concise message and dispatch state (`not_dispatched`, `dispatched`, `unknown`). If cancellation or timeout leaves physical effects uncertain, return `unknown`, not a reassuring failure or cancellation.

Error codes are `INVALID_ARGUMENT`, `UNSUPPORTED`, `IDENTITY_MISMATCH`, `DEVICE_REJECTED`, `TRANSPORT_ERROR`, `TIMEOUT`, `PROTOCOL_ERROR`, `RESOURCE_LIMIT`, `CANCELLED` and `INTERNAL_ERROR`. Authentication, policy and ownership errors belong to the gateway, before dispatch. Unexpected adapter exceptions become internal errors with conservative outcome handling; secrets must not enter results.

`retry: idempotent` only makes an operation eligible for a gateway-controlled retry. The adapter does not retry complete state-changing operations automatically. Host duplicate suppression does not promise exactly-once physical execution. The plugin never replays work after reconnect without a fresh authorised invocation.

Readings use RFC3339 UTC `observed_at`, integer `age_ms` and `quality` valid/stale/invalid. Receipt time is used when a trustworthy acquisition timestamp is unavailable and that limitation is documented. Durations and freshness decisions use the monotonic clock. UTC clock corrections must not renew leases or freshness. Invalid values use null; stale/invalid readings cannot satisfy verification.

`self_test` returns an operation result separately from verdict pass/fail/unknown. A test timeout does not fabricate a failing DUT verdict. `get_errors` consumes device errors where the protocol does, so it is state-changing; gateway user-facing logs are retained observations of that collection.

## 6. Declarative transports

### 6.1 SCPI over LAN, USBTMC or UART

Supported declarative SCPI verbs are identify/read/write/self_test/get_errors. Class-profile invoke actions require an adapter in this revision. Capture, reset and streaming on SCPI equipment require an adapter in this revision. This is a bounded initial contract, not a claim that SCPI lacks those functions.

Transport settings specify protocol, byte limits and LF/CRLF termination. `transport_eom` uses the backend's message boundary and is valid only for USBTMC or VXI-11. Raw TCP and serial require an explicit LF/CRLF boundary. A raw socket port is literal; VXI-11 endpoint resolution uses its protocol binding, with the configured port identifying the RPC service endpoint expected by the qualified backend. Host/USB instance/serial path come from the connection key.

Descriptor commands contain no CR/LF, NUL or command separators. A getter contains no placeholders. A setter contains exactly one `{value}` and no other brace expressions. The transport appends exactly one configured terminator. Multi-command sequences belong in an adapter or approved procedure.

`codec.kind` equals parameter type. Numeric tokens are finite ASCII decimal, optionally signed and with exponent for floats; integers have no decimal point or exponent. Whitespace around the response token is stripped; units, mixed text and trailing tokens are errors. Numeric output uses a locale-independent ASCII representation preserving the requested numeric value; comma decimal separators and nonfinite values are forbidden.

Boolean tokens use explicit distinct true/false strings. Enum maps cover every logical value exactly once and have unique wire tokens. Strings and mapped tokens cannot contain CR/LF, NUL, semicolons, quotes, braces or commas; more complex SCPI quoting requires an adapter. After applying the codec, validation still checks the logical parameter type and constraints.

Identification issues `*IDN?`, parses exactly four comma-separated fields (manufacturer, model, serial, firmware), strips surrounding spaces and compares commissioned expectations. Devices with a different identity format require an adapter.

A transport send does not acknowledge a SCPI write. Pure-send writes can achieve only `dispatched`; higher assurance requires declared readback/physical verification or an adapter with a documented completion mechanism. SCPI readback is a separate query within the same scheduled operation. Native parsing failure, timeout or mismatch must not become verified success.

Self-test runs the declared command and compares the stripped response to `pass_response`; another valid response is a fail verdict with raw detail. Error collection parses `integer,"message"` records until `no_error_code` or the declared maximum entries. Quoted doubled quotes are decoded; embedded line breaks or malformed records are protocol errors. Reaching the bound before the sentinel sets `more: true` and preserves already-collected entries through the gateway evidence path. It does not imply the queue is empty.

### 6.2 Native UART JSON

The wire format is UTF-8 NDJSON: one strict JSON envelope followed by LF. No BOM or embedded literal line breaks are allowed. A receiver may strip a single CR immediately before LF. Descriptor `max_frame_bytes` includes the terminator. Invalid UTF-8, oversized frames, nonfinite JSON and incomplete frames are protocol failures.

Requests and responses use exactly §5's schemas, including `operation_id` and `verb`. Events use the event schema and are distinguishable by `subscription_id` plus `kind`. Responses are matched to outstanding IDs; stale responses cannot satisfy new requests. The initial binding schedules one request at a time per connection, while separating unsolicited events. Late unmatched responses are retained as diagnostics or discarded, never reassigned.

Identify returns the runtime identity shape with `source: device`. Reads, writes, self-tests, error collection and reset use their exact runtime result shapes. A device can expose any supported subset. Capture requires an adapter in this revision, even on UART JSON, because binary artifact transfer is not part of the native envelope contract.

A timed-out or malformed legacy device without this correlation contract requires an adapter and an explicit resynchronisation strategy. No state-changing request is resent blindly. Reset is only advertised after its output effects and expected loss/re-establishment of communication are documented; acknowledgement alone is not evidence of a safe post-reset condition.

### 6.3 Passive CAN

Declarative CAN receives frames only; it never transmits queries or writes. Match CAN ID, standard/extended format, FD flag and exact payload length. Standard IDs are 0–2047; extended IDs are 0–536870911. Classic payloads are 1–8 bytes for this binding. FD payload lengths are 1–8, 12, 16, 20, 24, 32, 48 or 64. Error, remote-request and mismatched frames do not update samples.

Decode bytes at `byte_offset` for `length_bytes`, then interpret signedness/endianness and multiply by nonzero finite scale. A sub-byte field requires length one, both bit fields and offset+length≤8; extract with bit zero at the least-significant bit, then apply signed interpretation using the extracted width. Bounds must fit the payload. Decoded integers/numbers must satisfy §4's representability rules. Invalid frames do not refresh freshness.

Identify returns commissioned identity with `source: commissioned`; it must not claim a device identity exchange. Streaming forwards qualified new samples at no more than the requested rate. Generic CAN writes, requested sampling, multiplexed frames, counters/checksums and CANopen/J1939/ISO-TP semantics require an adapter unless a separately supported complete binding defines them.

### 6.4 Adapter transports

`serial`, `i2c`, `spi` and `custom` require adapter mode. Existing SCPI/UART/CAN transports may also use adapters. Descriptor settings do not define complete I²C/SPI transactions: register width, addressing, repeated starts, SPI commands and dummy clocks come from documented adapter logic.

Raw serial settings establish baud/parity/data/stop bits, flow control and frame limit. Opening any device must not assume an electrically harmless transition; modem-line or device-reset effects are part of commissioning. The adapter cannot turn a descriptor connection key into arbitrary host access.

## 7. Capture and subscriptions

Capture requests are bounded by sample count, format, byte allowance and deadline. Unsupported limits are rejected before triggering the instrument when possible. The retained core capture verb has one channel per capture. Multi-channel, irregularly sampled, digital, spectral, tabular and complex results use typed class-profile invoke actions and the measurement schema.

Descriptors advertising capture require `capture_formats` and `capture_limits.max_samples/max_bytes`. Requests must satisfy both descriptor and host limits. Streaming descriptors require `stream_limits.min_interval_ms/max_subscriptions`; requested intervals cannot be shorter, and admitted subscription count cannot exceed the limit. These are device integration capacities, not bench safety limits.

`waveform_f64le` is contiguous IEEE-754 little-endian 64-bit finite samples, no header, with one unit and uniform positive sample interval. Byte length equals sample_count×8. `raw_binary` is uninterpreted bytes whose meaning must be documented by that integration. Manifests carry host-managed artifact ID, length, SHA-256 and start time; waveform metadata is mandatory. Artifacts are downloaded outside MCP text payloads using gateway access controls.

The host supplies capture ID and writer allowance. Plugins do not choose filesystem paths. Failed/incomplete captures are aborted, not published as complete. The host computes length/digest during finalisation; plugin-supplied metadata cannot override them.

Subscriptions are explicitly opened and closed with paired capabilities. `min_interval_ms` is a maximum emission rate, not a guarantee of hardware sample rate. Sequence starts at zero per subscription, increments for every emitted event, and resets only for a new subscription. A plugin that detects discarded telemetry emits `gap` before subsequent telemetry when capacity permits. The gateway also records its own delivery gaps; protection cannot rely on lossy client delivery.

`stream_unsubscribe` is idempotent for an already-closed known subscription. Unknown subscriptions owned by another connection/principal are rejected by the host. Close/reset cancels local subscription state. Ended streams emit an `ended` event when possible. No stream outlives its host-owned subscription authority or survives plugin replacement automatically.

## 8. Python adapter ABI 1.1

`integration.adapter.entry_point` has form `package.module:create_plugin`. The host imports a reviewed installed distribution, resolves that factory and calls it with no arguments. One returned object serves one commissioned physical instance. No singleton/shared mutable device session is permitted.

The following base signatures are normative, expressed using standard Python typing. They describe the API to implement; they are not a supplied SDK:

```python
def create_plugin() -> DevicePlugin: ...

class DevicePlugin:
    async def open(self, descriptor: dict, services: HostServices,
                   context: OperationContext) -> None: ...
    async def execute(self, request: dict,
                      context: OperationContext) -> dict: ...
    async def next_event(self, subscription_id: str,
                         context: OperationContext) -> dict | None: ...
    async def close(self, context: OperationContext) -> None: ...
```

`open` attaches the host-provided scoped services and initialises local parsing state. It sends no output-enable, reset or self-test commands. Transport-attachment side effects must be identified and qualified separately; a serial open is not assumed to leave control lines unchanged. Commissioning/identity checking occurs through explicit `identify`. `execute` accepts validated operationRequest objects and returns operationResult objects. The adapter still validates direct invocation against its descriptor; host policy checks do not justify accepting arbitrary arguments. Unsupported verbs return `UNSUPPORTED` before I/O.

`next_event` is host-driven, returns one valid event or None if no event arrives before its deadline, and creates no hidden background task. It raises no timeout error solely because a healthy quiet stream produced no data. If no streaming capability exists, the method returns None without I/O. Host scheduling allows at most one execute/next_event call in flight on the instance. Calls to next_event have a bounded polling budget so control is not blocked indefinitely.

`close` is idempotent, bounded, releases local subscription/parser state and asks the scoped transport to close. It is cleanup, not the bench's safety shutdown mechanism. Gateway protective action is an explicit prior/independent operation. Failed open must permit close. No I/O occurs after successful close; reopen requires a new object instance.

```python
class OperationContext:
    operation_id: str
    dataset_id: str | None  # Host reservation for data-producing profile actions
    deadline_monotonic: float  # seconds on services.monotonic() clock
    def is_cancelled(self) -> bool: ...
    async def mark_dispatch_started(self) -> None: ...

class HostServices:
    def monotonic(self) -> float: ...
    def utc_now(self) -> str: ...  # RFC3339 UTC
    async def transfer(self, transaction: dict,
                       context: OperationContext) -> dict: ...
    async def close_transport(self, context: OperationContext) -> None: ...
    async def record_evidence(self, entry: dict,
                              context: OperationContext) -> None: ...
    async def artifact_append(self, capture_id: str, data: bytes,
                              context: OperationContext) -> None: ...
    async def artifact_finalise(self, capture_id: str, metadata: dict,
                                context: OperationContext) -> dict: ...
    async def artifact_abort(self, capture_id: str) -> None: ...
```

The host supplies a monotonic clock, cancellation signal, scoped transport and optional capture writer; it never supplies unrestricted filesystem or network credentials. Services retain commissioned settings internally. Plugins must not import a nonexistent SDK: structural compatibility with these signatures is sufficient.

Before the first device transmission of an operation, call `mark_dispatch_started`. The host durably records that dispatch is beginning; this is conservative intent, not proof that a byte reached the device. `transfer` also verifies the context and records transmission evidence. An I/O exception after this point may require `unknown`. Pure receive operations need no dispatch marker. Contexts cannot be retained for later calls.

Check cancellation and remaining time before each transfer and bounded processing step. Do not sleep or block past the deadline. If policy says cancellation is unsupported, the host may cease waiting but the deadline still applies; the adapter must report the eventual conservative outcome. No automatic operation retry, host reconnection, process spawning or plugin installation occurs inside the adapter.

`artifact_append` is permitted only for the current capture ID and quota. `artifact_finalise` accepts format/start time and optional waveform metadata, validates actual bytes, and returns the complete captureManifest. `artifact_abort` is idempotent local cleanup and cannot contact a device or publish data; it remains callable for cleanup after a capture deadline. Only `artifact_writer` permission grants these services. Event production uses next_event and requires `event_sink` permission for streaming adapters.

Host transport failures raise `TimeoutError` for deadline expiry, `ConnectionError` for transport loss, `ValueError` for rejected transaction shape, or `RuntimeError` for host resource/internal failure. Adapters map those to runtime error codes and conservative dispatch state. Other exceptions are caught by the host as internal failures. These exception classes form the minimal mock-host contract for agent tests.

`record_evidence` accepts `{kind: "device_error", entry: {code: str, message: str}}`. It preserves each consumed device error as it is parsed, before another queue entry is requested, so a later malformed response cannot erase earlier evidence. The host adds identity, operation and timestamp metadata, bounds message size and handles retention. Failure to retain an entry stops further ordinary collection; it never prevents independent protection. All admitted integrations have this scoped evidence service; it does not grant arbitrary log/file access. Open/close failures raise the documented host exception classes; the gateway retains the instance as unverified/failed and still attempts bounded cleanup.

### 8.1 Scoped transfer grammar

All transaction objects reject unspecified fields. Data is a Python `bytes` value, never base64 or text; these are internal ABI calls, not runtime JSON envelopes. Each call is limited by context and descriptor byte bounds. Host methods enforce transport type and the commissioned connection; transaction objects contain no host/path/credential fields.

| `kind` | Required fields besides kind | Result |
|---|---|---|
| `stream_send` | `data: bytes` | `{}` after transport acceptance |
| `stream_receive` | `max_bytes: int`, `termination: lf/crlf/eom`, `exact_bytes: int or None` | `data: bytes` including terminator when present |
| `stream_exchange` | `data: bytes`, same receive fields | `data: bytes` |
| `can_receive` | `max_bytes: int` | `id: int`, `extended: bool`, `fd: bool`, `data: bytes`, `received_at: str`, `received_monotonic: float` |
| `can_send` | `id: int`, `extended: bool`, `fd: bool`, `data: bytes` | `{}` |
| `i2c_transfer` | `segments: list` of `{write: bytes}` or `{read_length: int}` | `reads: list[bytes]` in read-segment order |
| `spi_transfer` | `data: bytes` | `data: bytes` of equal length |

`stream_send/exchange` support LAN/USB/serial adapters with the selected backend semantics; the adapter supplies terminators explicitly. `stream_receive` supports the same transports. If exact_bytes is positive, it takes precedence over terminator detection and must be ≤max_bytes; otherwise termination applies. Incomplete frames never return as complete. Serial/raw TCP do not support eom. Byte counts include framing. For native SCPI declarative mode the host constructs these transactions itself.

CAN receive is scoped to the admitted integration's bus and authorised filter; error/RTR frames are not returned as ordinary data. CAN send requires adapter mode and gateway authorisation. I²C segments use repeated starts between segments and one final STOP at the commissioned seven-bit address; unusual transaction behaviour requires a future supported host-service extension, not direct OS access. SPI asserts the commissioned chip select for the entire full-duplex transfer, returns one byte per transmitted byte and then deasserts it. Register bytes and dummy clocks are adapter responsibility.

The initial generic HostServices has no `custom` transaction kind. An integration declaring transport custom must reference a separately documented and admitted host-service extension. An agent cannot mark it complete using these generic services alone. The core never falls back to unrestricted I/O.

## 9. Lifecycle, ownership and security invariants

The host validates structure, semantics, installed entry point, permissions and firmware before admission. It creates one plugin, opens it, checks identity, then invokes authorised work. Removal follows stop admission → bounded cancellation/protective transition → close → release ownership. An unresponsive plugin can be isolated/restarted by the host, but independent protection is what covers hazardous host failure.

Descriptors are version-pinned for a run. Executable plugin replacement is a reviewed release change. No hot reload mutates active parser or mapping state. Secrets are excluded from descriptors and logs. Runtime data and vendor responses are untrusted text when shown to AI clients.

Only the gateway owns control leases, commissioning, arming, trip recovery and procedure authority. An adapter cannot report these policy decisions as device capabilities or auto-clear a safety trip. Unattended procedures are bounded and execute locally; no plugin relies on ongoing AI judgement for protection.

## 10. Mandatory semantic checks

The schema enforces structural rules; an author and host must also perform all applicable checks below. These cannot be assumed to be implemented merely because a schema exists.

| ID | Admission requirement |
|---|---|
| S01 | Unique parameter names; capability set exactly matches implemented operations; policies exist only for advertised verbs |
| S02 | Numeric bounds ordered, finite and appropriately integral; interoperable numeric range respected |
| S03 | Read/write capabilities agree with parameter access; no hidden writable binding or undeclared destructive read |
| S04 | Transport, integration mode, identity strategy and bindings agree; unknown required features fail admission |
| S05 | SCPI codec matches parameter type; commands and placeholder counts satisfy §6.1 |
| S06 | Bool tokens distinct; enum map covers values bijectively; unsafe protocol characters rejected |
| S07 | String bounds ordered; patterns supported and anchored; unrelated type constraints rejected |
| S08 | Verification target exists, is readable, has compatible type/unit and suitable semantics; numeric tolerance present |
| S09 | Operation completion and retry claims are achievable; pure SCPI send cannot claim acknowledgement; non-parameter side effects documented |
| S10 | Binary offsets/width fit payload, bit fields fit one byte, scaling is finite/nonzero, decoded type is representable |
| S11 | CAN ID format, FD/DLC rules and freshness valid; declarative CAN cannot write or request samples |
| S12 | Connection key resolves to the expected commissioned instance; transport boundaries, flow control and frame limits are supported |
| S13 | Identity/firmware match exact reviewed evidence; commissioned-only identity is explicitly labelled |
| S14 | Referenced sources/vectors exist, package-relative paths cannot escape, dependencies are exactly pinned and admitted |
| S15 | Adapter capabilities have methods/permissions; capture requires artifact_writer; streaming requires event_sink and paired verbs |
| S16 | Captures obey format/sample/byte/time bounds; subscriptions obey rate, sequence, ownership and lifetime rules |
| S17 | Results/events match schema and request IDs, requested parameters, descriptor types/units and achieved assurance; UTC formats checked |
| S18 | No credentials, automatic module installation, safety-critical ignored extensions or implicit policy relaxation |
| S19 | `derived_variables` entries are uniquely identified, well-typed and parse under the section 8 grammar of measurement-model.md with no self-reference, forward reference or cycle (operand existence and unit agreement are evaluation-time, not admission-time) |

Write operation policy is a minimum across writable parameters; a parameter may demand stronger completion, never weaker. For data-producing reads/captures/tests, `acknowledged` means a well-formed completed result, not necessarily physical verification. State-changing get_errors/self_test/reset/stream setup policies must reflect actual effects. Conservative state_change classification is allowed.

## 11. Required conformance evidence

An author supplies schema-valid descriptors and runtime vectors, semantic checks, and adapter tests where applicable. The minimum behavioural cases are identity match/mismatch; valid and invalid typed inputs; bounds/enum/string rejection before I/O; normal response; device rejection; malformed/truncated/oversized response; timeout before dispatch and after dispatch; cancellation; stale data; unsupported verb; repeated close; failed open cleanup; and no automatic replay after reconnect.

Additional required cases are readback mismatch and uncertain write outcome for writes; signed/endianness/payload/staleness checks for binary decoding; ID correlation and unsolicited events for UART JSON; quota/partial capture/manifest checks for capture; and ordering, gap, teardown and unsubscribe behaviour for streams.

Vectors record stimulus, expected outbound bytes or envelope, supplied response and expected result. No test may energise a real DUT merely to establish software conformance. Live-device qualification is explicitly labelled, authorised by the bench process and separate from deterministic mock evidence.

An agent may report a plugin ready for hardware qualification after mock conformance. It cannot report a bench safe for unattended use from these tests. The gateway's independent protection and numeric commissioning inputs are outside plugin conformance.

## 12. Reference protocols

The accompanying examples are fully specified synthetic authoring targets. Values and limits here belong to these examples only; they are not the user's bench limits. `examples/reference-vectors.json` gives exact representative exchanges and results.

**reference-psu:** Raw TCP with LF at the descriptor's port. `*IDN?` returns `OTDP Reference,reference-psu,SIM001,1.0`. `VOLT n` sets a 0–10 V setpoint; `VOLT?` reads it. `OUTP 0/1` sets disabled/enabled; `OUTP?` reads it. `MEAS:VOLT?` returns the setpoint when enabled, otherwise zero. These synthetic settings are exact within the declared readback tolerance; write commands have no direct response. `*TST?` returns `0`; `SYST:ERR?` returns `0,"No error"` when empty. Initial output is disabled and setpoint zero. The model makes no claim about a physical protection circuit.

**reference-controller:** Native UART JSON exactly as §6.2. Identify returns OTDP Reference/reference-controller/SIM002/1.0. `battery_voltage` reads 4.01 V. `led_state` initially off and accepts off/red/green/blue; writes acknowledge the effective value. Self-test returns pass with an empty detail list. One subscription at a time is supported, with an interval of at least 100 ms; subscribed parameters emit their current values at that interval until unsubscribed. Subscription IDs and sequence follow §7. Unadvertised verbs return UNSUPPORTED. Malformed requests do not change state.

**reference-can:** Passive standard CAN frame ID 418, classic CAN, four bytes. Bytes 0–1 are unsigned big-endian hundredths of volts; bytes 2–3 are signed big-endian tenths of amps. `04 D2 FF 9C` therefore yields 12.34 V and −10 A. Frames older than 100 ms do not satisfy the example's read policy. Identity is commissioned and never queried on the bus.

**reference-capture:** A custom line protocol on the declared serial link, demonstrating why an adapter can be read-only yet support capture. `ID?\n` returns `OTDP Reference,reference-capture,SIM003,1.0\n`. `V?\n` returns `3300\n` in millivolts; the adapter reports 3.3 V. `CAP? n\n` accepts integer n=1…1024 and returns one LF-terminated comma-separated line of decimal samples `1,2,…,n`, in volts at a 0.001 s interval. `ERR\n` is a device rejection for an unsupported command/count. Capture starts when CAP is sent and has no cancellation command. A timeout after CAP is dispatched is unknown. The adapter converts exactly n finite numbers to waveform_f64le through the host artifact writer. Capture byte budget must accommodate n×8 before transmission. No escaping, checksums, unsolicited frames, streaming, reset or setters exist in this synthetic protocol. Connection loss requires a fresh host instance; no retry/replay is defined.

## 13. Migration from 0.1

Do not edit a version field and assume compatibility. Review each descriptor: replace numeric levels with integration mode/capabilities, supply operation policies and provenance, split settings from measurements, add type-correct constraints, resolve identity separately from connection, and replace incomplete binary writes with documented adapters.

Map `vendor` into expected identity only after checking actual device responses. Replace `adapter.module` with the reviewed factory entry point and API/version contract. Native JSON devices must implement correlation/runtime envelopes or remain behind a legacy adapter. Preserve original descriptors as migration evidence; unresolved claims remain uncommissioned.

The 0.1.0 schemas reject 0.1 descriptors deliberately. There is no automatic compatibility or conformance claim for the supplied v0.1 examples.


## 14. Class-profile contract and additional host services

The twelve profiles, 50 action schemas and typed dataset contract are normative parts of this version. Read device-classes.md for required quantities and physical semantics, measurement-model.md for axes/encoding/metrology, and extension-contract.md for invoke, local schema resolution, adapter API 0.1.0 dataset/artifact services and C01–C12 checks. Core capture and scalar operations remain available for limited integrations; their existence does not imply a class profile. Firmware installation, arbitrary vendor SDK access and unknown profiles remain outside the base contract.

## 15. Shared repository packaging

STG 1.2 adds the companion [registry contract 0.1.0](../../registry/0.1.0/registry-specification.md). Authors should inspect existing compatible packages before creating a duplicate integration. A shared release includes the registry manifest, licence, immutable source reference, compatibility, permissions, pinned dependencies and applicable evidence. Profiles, declarative descriptors and executable implementations can be published separately with exact relationships. This distribution contract does not change OTDP 0.1.0 runtime envelopes or adapter API 0.1.0 and is not required for an unpublished local-only integration. Registry discovery never authorises automatic installation or device control.

## 16. Procedure and commissioning boundary

STG 1.3 supplies the companion [execution contract 0.1.0](../../execution/0.1.0/execution-contract.md). Its procedure engine maps approved typed steps into these OTDP envelopes. Bench, safety-policy and commissioning metadata remain host-owned and separate from shared device descriptors. Plugins receive already authorised operations and scoped host-issued identities; they do not interpret the procedure language or grant procedure authority. Runtime versions in this document remain unchanged.
