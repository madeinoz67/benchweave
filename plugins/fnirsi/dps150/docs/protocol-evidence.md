# DPS-150 protocol library

Status: source-supported protocol subset, qualified with synthetic mock exchanges plus supervised live-hardware captures (2026-09-15, `fixtures/protocols/dps150/` at the repository root) that ground the session layer, identity answers, GET dialects and write behaviour cited below. Supervised writes were sent and captured: voltage and current setpoints (fields 193/194), numeric OVP/OCP (fields 209/210) and the output toggle (field 219) at 1.00 V unloaded, each leg under the principal's per-leg approval recorded in the capture provenance headers, with every setting restored and verified afterwards by snapshot readback. Both GET dialects are live-verified post-handshake. No DUT was commissioned; no firmware compatibility beyond the captured unit, physical protection, measurement accuracy or OTDP profile conformance is claimed.

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

Explicitly unsupported: unknown C0/field 225, reset, firmware update, direct setpoint/protection GETs, preset programming, display/audio settings, metering controls, OPP/OTP/LVP writes, sweeps and streaming subscriptions. Some exist in upstream code but are deliberately outside this reviewed subset. The evidence-backed session handshake below is the sole initialise/synchronise mechanism, and it deliberately stays outside `encode_packet`; no other commands are invented to initialise or synchronise the device.

## Evidence-backed session layer

The device does not answer a clean transport: it must be woken first. This area has direct live-hardware corroboration, and it is kept outside the codec's reviewed subset on purpose.

Upstream provenance: cho45/fnirsi-dps-150 at 6107bd34 opens every session with CMD_SESSION (`0xC1`) then CMD_BAUD (`0xB0`) as fire-and-forget frames paced ~50 ms apart, over a port with RTS/CTS hardware flow control. Neither frame draws a reply of its own; wake is proven only by the traffic that follows.

Live corroboration, first contact 2026-09-15 (supervised, read-only; committed at `fixtures/protocols/dps150/`, repository commit `0bab412`): twelve bare identity queries — both GET dialects across six bauds (115200, 9600, 19200, 38400, 57600, 230400), without flow control — drew zero reply bytes (`first-contact-negative.jsonl`). On a port with RTS/CTS enabled, sending session-open `F1 C1 00 01 01 02` then, after ~50 ms, baud negotiation `F1 B0 00 01 05 06` woke the device: it answered subsequent GETs and streamed an unsolicited ~2 Hz telemetry cycle of fields 195, 192, 226, 227, 196 around them (`connect-v2.jsonl`). The negative capture lacked both the handshake and flow control, so it does not separate the two requirements; both are treated as preconditions.

`session.open_session(transport, delay_s=0.05)` sends those two captured frames with the captured pacing; `session.drain_telemetry(transport, window_s=...)` empties the unsolicited stream around commanded calls. The drain window is RECEIVE-ATOMIC (WP11 W1): it decides when the drain stops starting receives, and a receive in flight when the window closes runs to completion — at most one receive's data of overshoot (one frame for the frame-granular receives the adapter's drain view provides), bounded by the caller's operation deadline — so the window edge can never abandon a receive mid-call and desync later readers. A raw chunked Transport may still split a frame across receives; the decoder's trailing partial is discarded, as before. The frames are hand-derived constants, deliberately not routed through `encode_packet` — the codec's supported-subset guard still rejects C1/B0, so the reviewed subset above is unchanged. The handshake is fire-and-forget: `open_session` receives nothing and establishes no session state, and a failed wake is indistinguishable from a dead link until a commanded call times out.

Transport preconditions: an exclusively owned, already-established session with RTS/CTS hardware flow control enabled, and ~50 ms pacing between the two frames. The captures do not settle the dialect as a firmware property: both ZERO-payload and EMPTY GETs are live-verified post-handshake (EMPTY by `hw04-leg34-current-protection.jsonl`, step `leg6-dialect-EMPTY`), and qualification must still select one explicitly.

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

All fixtures in `tests/test_protocol.py` are explicitly synthetic. Literal golden frames check requests/responses independently of the production encoder. The ALL fixture is assembled from documented byte offsets, not captured hardware. The handshake-demanding mock in `tests/conftest.py` is synthetic too: its silence rule, reply table and five-frame telemetry cycle are transcribed from the live capture, not replayed hardware.

| Requirement | Tests |
|---|---|
| Exact GET/SET requests and typed responses | test_literal_frames_and_minimum_frame, test_exact_queries, test_write_dispatch_only, test_explicit_zero_get_dialect |
| Fragmentation, frame boundaries, bounds | test_every_fragment_boundary, test_multiple_frames, test_fragmented_client_reply, test_buffer_limits_and_noise, test_decoder_cannot_grow_after_error |
| Invalid inputs produce no I/O | test_invalid_write_has_no_io, test_invalid_timeout_has_no_io, test_unsupported_read_is_rejected_before_io |
| Malformed replies never become measurements | test_malformed_packets, test_malformed_values, test_bad_exchange_blocks_reuse |
| Combined-state field mapping | test_combined_snapshot_preserves_unknown_bytes |
| Total deadlines, no resend/reconnection | test_receive_timeout_blocks_reuse, test_send_timeout_and_no_replay, test_overall_deadline_does_not_restart_per_fragment |
| Single flight, cancellation, link failure | test_cancellation_and_concurrent_calls, test_transport_failure_blocks_reuse |
| Handshake frames and pacing; bounded drain windows | tests/test_session.py: test_open_session_sends_evidence_frames_in_order, test_open_session_default_pacing_uses_real_sleep, test_drain_consumes_all_offered_frames_until_eof, test_drain_reassembles_fragmented_frames, test_drain_discards_partial_tail, test_drain_stops_at_eof_before_window_edge, test_drain_window_edge_is_frame_atomic, test_invalid_window_has_no_io |
| Window-edge straddle never poisons the session; same-field telemetry IS the reply | tests/test_adapter.py: test_drain_edge_straddle_never_poisons_the_session, test_same_field_telemetry_frame_is_the_reply |
| Captured negative pinned: no answer without the exact handshake | tests/test_session.py: test_client_read_times_out_without_handshake, test_wrong_preamble_keeps_the_device_silent |
| Woken device answers GETs amid the telemetry cycle | tests/test_session.py: test_client_read_answers_after_handshake |

Run `uv run --no-sync pytest tests/test_protocol.py tests/test_session.py`; this plugin's own test discovery, ruff and mypy configuration cover its source and tests. Setup and contract bootstrap commands are in the project README.

This work supports future OTDP S02/S09/S10/S17 validation, but is not an adapter API 1.1 implementation. Configuration tokens, authorisation, scoped HostServices, readback verification, datasets and complete dc_psu profile actions remain separate integration work. Hardware qualification must verify firmware identity, selected GET dialect, attachment/local-lock effects, readback, link loss and protection behaviour. Hardware operation and publication each require separate explicit authorisation.
