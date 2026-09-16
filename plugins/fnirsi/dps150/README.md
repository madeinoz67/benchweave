# FNIRSI DPS-150 local BenchWeave adapter

This is an unpublished, read-only adapter for **OTDP 0.1.0 / adapter API 0.1.0**, descriptor and implementation **0.1.0**, against BenchWeave revision `230acefc88c2e7d5d1dfc07100344fdc564ea404` and its device developer guide. All qualification evidence is **simulated with mocks**. No physical firmware has been qualified. No hardware was opened or operated, and nothing was published.

The reviewed factory is `benchweave_fnirsi_dps150.adapter:create_plugin`. This independent project owns the injectable protocol library, adapter, descriptor, evidence and tests. Its Python distribution is `benchweave-fnirsi-dps150`; it imports no BenchWeave core implementation and has no runtime dependencies. See [LICENSE](LICENSE) and [protocol evidence](docs/protocol-evidence.md) for selective reuse of cho45's MIT framing algorithms and KochC's corroborating evidence. It is not a published registry release. The descriptor ID remains `org.benchweave.fnirsi-dps150`.

## Independent development

This directory is the project root. It can be developed in place under `plugins/fnirsi/dps150/` or copied unchanged to a separate repository. It requires Python 3.13 or later and uv; it does not require a BenchWeave installation, parent checkout, board toolchain or serial backend.

```sh
uv sync --locked --dev
uv run python scripts/fetch_contracts.py
uv run python scripts/fetch_contracts.py --check
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

The explicit contract bootstrap downloads eight immutable, SHA-256-pinned OTDP documents/schemas from the revision in `contracts/lock.json`. It is a development dependency fetch, not runtime I/O; tests only verify/read local copies and fail clearly if they are absent or altered. Once dependencies and contracts are present, checks run offline. Contract upgrades require reviewing new bytes and updating the lock explicitly. For an offline handoff, retain the fetched `contracts/otdp-0.1.0/` directory with the project.

The project has its own `uv.lock`. Wheels contain the Python package, descriptor, vectors, licence and evidence documentation. Source distributions contain source, tests, tools, contract lock and docs; a fresh extraction can bootstrap its pinned contract inputs without the core checkout. Build success is not registry admission: registry manifests, provenance/SBOM, review and installation remain separate release work. No package is published or installed into a gateway by these commands.

The repository's device-plugin CI job exercises this project outside the checkout. Core tests do not import this plugin. No compatibility shim is retained at the former `benchweave.devices.fnirsi.dps150` import; consumers of this unpublished integration must update the import and descriptor entry point together.

Custom-device firmware belongs to its plugin developer and would live under this project in `firmware/`, with its own toolchain and tests. DPS-150 firmware source is not supplied or maintained here, so no firmware subtree, toolchain or flashing operation is added.

## Scope and identity

`identify` queries model (222) and firmware (224); `read` exposes voltage, current and power (195), input voltage (192), internal device temperature (196), output state (219), protection state (220), and CC/CV mode (221). A matching explicit identify is required before reads. Model must equal `DPS-150`; there is no evidenced serial-number query. Manufacturer is a descriptor attribution to FNIRSI, not a field returned by the protocol. Identity `source: device` refers to the queried model/firmware. Firmware `1.0` in tests is a synthetic response, not an accepted firmware list. The host must match a separately reviewed commissioned identity/firmware record; this adapter does not grant commissioning or control authority.

No profile is advertised. The mandatory `otdp.dc_psu/1.0.0` actions cannot be claimed by this integration:

| Mandatory action | Missing support/assurance |
|---|---|
| `configure` | Wire setters only establish dispatch. Protection semantics, safe transition ordering, complete effective configuration and required verification are not qualified. |
| `output` | Output-enable encoding exists in the library, but the required configured-state association and assured output transition are not implemented/qualified. |
| `measure` | Core scalar readings are implemented; the profile's typed scalar-set dataset, host dataset identity and configuration linkage are not implemented. |

All write/invoke/reset/self-test/error-queue/capture/stream operations return `UNSUPPORTED` before I/O. Protection state is a status enum, not a self-test or consumed error queue. Invalid or unexpected replies are protocol failures; no undocumented device rejection code is invented.

## Transport and lifecycle

The host resolves `connection_key: dps150` to exactly one commissioned instance. Settings follow pinned KochC `constants.py` and `transport.py`: serial 115200 baud, 8 data bits, no parity, 1 stop bit, RTS/CTS enabled; maximum framed packet 260 bytes. No VID/PID, serial path or network address is guessed. Attachment/modem-line effects, flow control, firmware, input supply and device PC mode must be independently qualified before hardware use.

This adapter fixes **KochC's empty GET payload**. cho45's zero-byte GET variant is not automatically tried — both dialects are live-verified on hardware (see `docs/protocol-evidence.md`). Opening sends nothing; the session-establishment commands (`0xC1`/`0xB0`) are sent by the adapter itself at first commanded use: the evidence-backed handshake captured live 2026-09-15 (`fixtures/protocols/dps150/` at the repository root — the device is silent without it). The library still deliberately excludes undocumented `0xC0` and flash commands.

The scoped bridge uses `stream_send`, then exact 4-byte header and payload-plus-checksum receives. `exact_bytes` overrides the required `lf` grammar field; no line terminator is appended or consumed. Host exact receives must either return exactly the requested bytes or raise. Unsolicited or delayed same-field responses cannot be distinguished on this uncorrelated wire protocol: the adapter drains a bounded telemetry window before each commanded call and consumes the commanded reply window by correlation — the first frame matching the requested field is the reply, and every other frame in the window is treated as telemetry and buffered — so the captured unsolicited ~2 Hz stream is tolerated rather than required to be absent. The honest limits stay: a same-field telemetry frame is accepted as the reply, and frames outside the codec's read fields still fail the exchange. A failed exchange permanently blocks the instance. The drain and correlated consumption are explicit, evidence-backed behaviors; no retry, reconnect or replay is hidden in the adapter.

Import, construction and open perform no device I/O. The original operation context accompanies each scoped transfer and the dispatch marker is awaited once before any transmission. One absolute host/policy budget spans both identity queries. Deadlines and cancellation are checked between transfers; cooperative host services must enforce them while awaiting I/O. Dispatch uncertainty is retained after transmission begins, including partial-send failures. Result messages omit host exception text. Close is bounded and idempotent, including failed-open cleanup; it never changes output state. Reopening requires a fresh instance and host admission. No context is retained between calls.

## Measurement limitations

These are core scalar readings, not OTDP typed datasets. Units are V, A, W and Cel; boolean and enum states have null units. Numeric values are finite IEEE-754 little-endian float32 values. No accuracy, calibration, physical range guarantee, sampling interval or independent protection is claimed. Negative measurements remain representable; setpoint limits are not applied as measurement limits. Temperature describes the device, not the DUT.

Every read sends a fresh request (`max_age_ms: 0`) and retains no sample cache. Time is host receipt time in RFC3339 UTC, because no trusted acquisition timestamp exists. Age uses the host monotonic clock. A fresh response cannot establish physical acquisition age or distinguish an undetectable delayed same-field response. A parsed response satisfies `acknowledged` data completion only, never physical verification.

## Conformance trace

From this project root run the independent setup/check commands below. Scalar request/response/result vectors are `src/benchweave_fnirsi_dps150/adapter-vectors.json`; replayable failure cases are `src/benchweave_fnirsi_dps150/adapter-failure-vectors.json` (read cases start after the mock identity exchange). Identity and additional boundary stimuli are explicit literals/mock injections in the tests. Plugin tests validate locally pinned descriptor and runtime schemas without network resolution. The explicit bootstrap downloads and verifies the contract inputs once; it is not part of plugin import or test execution.

| Requirement | Evidence / tests |
|---|---|
| S01, S03 | Descriptor schema/package test: exactly identify/read, eight unique read-only parameters; unsupported-operation tests prevent hidden writes/actions. |
| S02 | No writable ranges; protocol finite-number tests plus scalar vectors cover float32 representability. No rounding/clamping or integer fields. |
| S04 | Exact descriptor admission rejects version/feature/profile drift; serial adapter bindings only. |
| S05 | Not applicable: no SCPI. |
| S06 | Protocol bool/enum decoding rejects unknown values; declared choices correspond to wire maps. SCPI token safety is not applicable. |
| S07 | No string parameters or patterns. Protocol identity text is bounded by the 255-byte wire length, strict UTF-8 and no controls. |
| S08 | Not applicable: no writes or verification targets. |
| S09 | Completed reads only; retry never; open/close have no device commands. Timeout/cancellation/dispatch tests prevent fabricated assurance. |
| S10 | Protocol exact width, little endian, checksum and finite-value tests; scalar vectors exercise all adapter projections. |
| S11 | Not applicable: no CAN. |
| S12 | Scoped transaction-shape tests enforce byte limits/exact framing and context; settings pinned to source. Physical connection-key resolution and RTS/CTS qualification remain host/hardware responsibilities. |
| S13 | Identity/factory tests, model mismatch, firmware parsing and commissioned policy; actual accepted unit/firmware is still unknown. |
| S14 | Schema/package test checks vector containment/existence; immutable source pins and bundled dependency policy. No downloads or installation at runtime. |
| S15 | Async factory/open/execute/next_event/close; scoped_transport only; factory isolation and lifecycle tests. |
| S16 | Not applicable: capture and streaming absent; unsupported calls perform no I/O and next_event returns None. |
| S17 | Runtime schema/format validation, exact result vectors, operation-ID mismatch, input rejection, freshness and uncertainty tests. |
| S18 | Exact descriptor admission, scoped-only mock interface, no optional extension carrying required semantics or policy relaxation. |
| C01–C12 | Profile actions, profile schemas and profile datasets are not advertised. These checks are not claimed as passed for a PSU profile. Descriptor and unsupported invoke tests enforce that boundary. |
| M01–M14 | Typed measurement datasets are not produced or advertised, so dataset/axis/artifact/metrology checks do not apply. Core scalar format/freshness requirements remain covered by S10/S17 above. |

Remaining qualification work includes an authorised clean-session protocol capture, exact physical model/firmware acceptance, acquisition-age characterisation, flow-control and attachment behaviour, and any independently reviewed write/profile extension. Hardware operation and publication each require separate explicit authorisation.
