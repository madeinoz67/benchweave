# DPS-150 protocol library

Status: source-supported protocol subset, validated with synthetic mock exchanges only. No hardware was connected or operated. No firmware compatibility, physical protection, measurement accuracy or OTDP profile conformance is claimed.

## Design and reuse

The approved design is selective protocol reuse plus an injectable transport. Import `benchweave_fnirsi_dps150` from this independent `benchweave-fnirsi-dps150` distribution (Python >=3.13). The protocol code and adapter belong to this plugin project, with no core runtime dependency; use this project's uv.lock.

Framing, checksum, float byte order and field layouts are ported from [cho45/fnirsi-dps-150 at 6107bd34531aa52692d757e3b82d9573750311ac](https://github.com/cho45/fnirsi-dps-150/blob/6107bd34531aa52692d757e3b82d9573750311ac/dps-150.js). Its MIT copyright/permission notice is retained in `LICENSE`. No browser UI, serial reader loop, sleeps, session startup or automatic state management are reused.

Cross-check evidence: [KochC constants](https://github.com/KochC/DPS-150-python-library/blob/ae1df445d5993bdc0839d863ac1ba25d9d1bbfae/dps150/constants.py), [codec](https://github.com/KochC/DPS-150-python-library/blob/ae1df445d5993bdc0839d863ac1ba25d9d1bbfae/dps150/protocol.py) and [device mappings](https://github.com/KochC/DPS-150-python-library/blob/ae1df445d5993bdc0839d863ac1ba25d9d1bbfae/dps150/device.py). KochC declares MIT in its README/setup metadata but the referenced licence file was not available; its implementation is not copied. It also credits cho45. Agreement between related implementations is not independent hardware evidence.

Manufacturer evidence: [FNIRSI product page](https://www.fnirsi.com/products/dps-150), [software instructions](https://www.fnirsi.com/pages/software-downloads), and [manual reproduction, pages 18, 21–25](https://manualzz.com/doc/87002906/fnirsi-dps-150-dc-power-supply-owner-manual). Exact manual revision and device applicability remain unresolved. Product input ratings conflict (32 V table versus 30 V caution); this library does not choose an input supply or commission a DUT.

## Wire contract and explicit dialect

Outgoing frame: `F1 command field length payload checksum`. Incoming supported responses: `F0 A1 field length payload checksum`. Checksum is `(field + length + sum(payload)) mod 256`; it excludes header and command. Floats are IEEE-754 binary32 little-endian. The length byte bounds payloads to 255 bytes and frames to 260 bytes.

KochC emits an empty GET payload; cho45 emits one zero byte. `Client` requires `get_payload=GetPayload.EMPTY` or `GetPayload.ZERO`. There is no default, auto-detection, fallback request or retry. These are two source-supported dialects, not two proven firmware variants. Qualification must select one explicitly.

The decoder handles arbitrary fragmentation and multiple frames within bounded chunks. It rejects noise, wrong headers/commands, unknown fields, bad checksums, wrong lengths, nonfinite interpreted floats and invalid enums/identity text. Identity accepts strict UTF-8 with trailing NUL padding only. Extra complete or partial bytes in a client's response chunk are errors; they are never cached for the next call. The low-level decoder clears partial state on errors; only the client imposes session failure state.

## Supported subset

Field numbers are protocol identifiers, not a generic arbitrary-command API. `READ_FIELDS` and `WRITE_FIELDS` expose the immutable implemented sets; unsupported fields/directions raise `UnsupportedCommand` before transport I/O.

| Read field | Result | Units/meaning |
|---|---|---|
| 192 | float | Input voltage, V |
| 195 | three-float tuple | Output voltage/current/power, V/A/W |
| 196 | float | Internal temperature, degrees C |
| 217 / 218 | float | Capacity Ah / energy Wh |
| 219 | bool | Reported output enabled state |
| 220 | string | normal, OVP, OCP, OPP, OTP, LVP or REP |
| 221 | string | CC or CV |
| 222 / 223 / 224 | string | Model / hardware / firmware identity |
| 226 / 227 | float | Reported upper voltage/current limit |
| 255 | immutable Snapshot | Known subset of exactly 139 bytes |

ALL maps the first seven floats to input/set/output/temperature values; protection floats are at offsets 76–95; enabled/protection/mode bytes are at 107–109. The entire original payload is retained as `raw_payload`. Presets, metering values, limits and unknown/reserved fields in this combined record are not interpreted by Snapshot. Unknown tail bytes are not labelled as measurements. Other ALL lengths are rejected rather than guessed.

| Write field | Accepted value | Completion |
|---|---|---|
| 193 | Voltage 0–30 V, multiples of 0.01 V | Dispatch only |
| 194 | Current limit 0–5 A, multiples of 0.001 A | Dispatch only |
| 209 | Numeric OVP 0–30 V | Dispatch only |
| 210 | Numeric OCP 0–5.1 A | Dispatch only |
| 219 | Strict Python bool | Dispatch only |

The write envelope follows the reviewed manual ranges; it is not a safe DUT envelope. 5.1 A OCP is a protection setting, not an expanded 5 A output rating. Zero protection values are merely encodable source settings; their disable/trip semantics are unknown. OVP/OCP resolution is not asserted. Binary32 rounding is inherent in the wire representation, never proof of an effective setting. `write_payload` rejects setpoint quantisation violations before encoding. `encode_packet` is the lower-level byte codec; it validates payload shape/finite range but does not establish engineering-unit quantisation or assurance.

Explicitly unsupported: session/baud commands B0/C1, unknown C0/field 225, reset, firmware update, direct setpoint/protection GETs, preset programming, display/audio settings, metering controls, OPP/OTP/LVP writes, sweeps and streaming subscriptions. Some exist in upstream code but are deliberately outside this reviewed subset. No commands are invented to initialise or synchronise the device.

## Injected transport and lifecycle

`Transport` requires `async send(data: bytes) -> None` and `async receive(max_bytes: int) -> bytes`. The caller supplies a clean, exclusively owned, already-established session. Receive returns no more than the requested byte count; empty bytes mean EOF. Send accepts every byte or raises, possibly after partial physical dispatch. Implementations must cooperate with cancellation and must not block the event loop or hide retries/reconnection.

```python
from benchweave_fnirsi_dps150 import Client, GetPayload

# transport is supplied by the caller; the package provides no hardware backend.
client = Client(transport, get_payload=GetPayload.EMPTY)
values = await client.read(195, timeout=1.0)
# values is the newly received V/A/W tuple, not a cached default.
```

Construction performs no I/O. Each operation has one total timeout (positive, finite, <=3600 seconds), covering send and every response fragment. Concurrent calls reject with OperationBusy rather than queue. There is no background task, sleep-based settling, automatic reconnection, full-operation retry or implicit handshake.

A write returns `DispatchReceipt(request=..., assurance='dispatched')`. It does not wait for or invent an acknowledgement. Firmware that emits SET acknowledgements requires additional reviewed handling; unexpected responses cause the next read to fail closed. The library does not assert that a successful write changed the output.

Timeout raises OperationTimeout with conservative `dispatch_started` evidence. Connection/protocol failures propagate; cancellation propagates CancelledError. All failures after starting I/O mark the client unusable, and later calls raise SessionUnusable without transmission. Recovery belongs to the caller. Merely creating another client over the same dirty transport does not constitute recovery.

The protocol has no operation IDs. Matching command/field after a send cannot distinguish an identical delayed or unsolicited frame already in the underlying transport. The clean-session/no-unsolicited-data precondition must be established externally; arbitrary firmware telemetry is not supported here. Firmware-specific correlation/resynchronisation evidence remains required before hardware use.

## Requirements and tests

All fixtures in `tests/test_protocol.py` are explicitly synthetic. Literal golden frames check requests/responses independently of the production encoder. The ALL fixture is assembled from documented byte offsets, not captured hardware.

| Requirement | Tests |
|---|---|
| Exact GET/SET requests and typed responses | test_literal_frames_and_minimum_frame, test_exact_queries, test_write_dispatch_only, test_explicit_zero_get_dialect |
| Fragmentation, frame boundaries, bounds | test_every_fragment_boundary, test_multiple_frames, test_fragmented_client_reply, test_buffer_limits_and_noise, test_decoder_cannot_grow_after_error |
| Invalid inputs produce no I/O | test_invalid_write_has_no_io, test_invalid_timeout_has_no_io, test_unsupported_read_is_rejected_before_io |
| Malformed replies never become measurements | test_malformed_packets, test_malformed_values, test_bad_exchange_blocks_reuse |
| Combined-state field mapping | test_combined_snapshot_preserves_unknown_bytes |
| Total deadlines, no resend/reconnection | test_receive_timeout_blocks_reuse, test_send_timeout_and_no_replay, test_overall_deadline_does_not_restart_per_fragment |
| Single flight, cancellation, link failure | test_cancellation_and_concurrent_calls, test_transport_failure_blocks_reuse |

Run `uv run --no-sync pytest tests/test_protocol.py`; this plugin's own test discovery, ruff and mypy configuration cover its source and tests. Setup and contract bootstrap commands are in the project README.

This work supports future OTDP S02/S09/S10/S17 validation, but is not an adapter API 1.1 implementation. Configuration tokens, authorisation, scoped HostServices, readback verification, datasets and complete dc_psu profile actions remain separate integration work. Hardware qualification must verify firmware identity, selected GET dialect, attachment/local-lock effects, readback, link loss and protection behaviour. Hardware operation and publication each require separate explicit authorisation.
