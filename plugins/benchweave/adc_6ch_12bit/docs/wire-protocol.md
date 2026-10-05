# ADC 6-channel 12-bit board — wire protocol v2

Status: normative for protocol version 2. Supersedes-but-cites the v1
wire family (the public contributor fork's 2026-09-11 UART driver design,
cited as provenance in the issue #393 design record); v1 frames remain
valid on the wire at all times until negotiated away. Every rate figure
in these documents is MODELLED or ESTIMATE — see `rate-model.md`.

## Frame shape (shared by v1 and v2)

    [0xAA 0x55][type][seq][len][payload(0..len-1)][crc16 LE]

- CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflect, no xorout)
  over `type..payload`, little-endian on the wire. The firmware and this
  project's host codec compute it through the same 16-entry nibble table
  (pinned to the bitwise reference by the codec tests).
- `len` is the payload length; a frame is `11 + len` bytes on the wire.

## Frame types

`0x01` SET_AVERAGING (u16 LE) · `0x02` SET_CHANNELS (u8 mask) · `0x03`
SET_SAMPLE_MODE (u8) · `0x04` START_STREAM · `0x05` STOP_STREAM · `0x06`
SAMPLE_ONCE · `0x07` RESET · `0x08` IDENTIFY · `0x09` ARM_TRIGGER
(reserved) · `0x81` ACK (echo type + u16 LE value) · `0x82` NAK (echo
type + error code) · `0x83` IDENTIFY_RSP · `0x90` SAMPLE.

v2 adds:

| type | name | payload | direction |
|------|------|---------|-----------|
| `0x0A` | SET_BAUD | u32 LE baud | host -> device |
| `0x0B` | SET_FRAME_FORMAT | u8: 0 = legacy fixed, 1 = mask-sized | host -> device |

A v1 device answers `0x0A`/`0x0B` with NAK (bad command) — the host
fallback path is identical to a v2 refusal.

## IDENTIFY_RSP

5 B payload reads as proto 1: `proto, fw_major, fw_minor, n_channels,
resolution` (all u8). A 7 B payload reads as proto 2: the same five plus
`caps u16 LE` — bit0 = SET_BAUD supported, bit1 = slim (mask-sized)
frames supported; all other bits reserved zero. A v2 reader parses
`proto` first and then by declared length, so a 5 B payload is proto 1.

## SAMPLE payload

- Legacy (fixed, v1): `4 + 2*6` B — u32 LE counter + six u16 LE values,
  disabled channels carried as zero. The frame is always 23 B.
- Mask-sized (slim, v2): `4 + 2*n_active` B — u32 LE counter + one u16
  LE per ACTIVE channel, canonical channel order. The `len` byte already
  encodes the width; a decoder cross-checks `len` against the negotiated
  mask popcount and treats a mismatch as a protocol error (resync
  downstream, surface the event).

## Baud

Boot state is 2 Mbps, 8N1, legacy frames — always. A v1 host talking to
a v2 device changes nothing (it never sends 0x0A/0x0B). The
device-supported set is {2,000,000; 3,000,000} baud — anything else is
NAK(bad parameter). The ceiling is the CH32V006 USART's documented
3 Mbps (fractional generator, up to 3 Mbps; 16x oversampling only, so
baud = PCLK2/(16*USARTDIV) with USARTDIV >= 1; at 48 MHz PCLK2 the
3 Mbps point is USARTDIV = 1.0 exact, zero baud-rate error). The
CH343G bridge's sustained 3 Mbps behaviour is a bench-checklist item,
not a spec claim.

## Negotiation (host side)

One attempt, no silent retry loop:

1. IDENTIFY at the boot baud (the only frame permitted before its
   response; non-mutating).
2. If proto >= 2 with the SET_BAUD and slim capability bits set:
   SET_BAUD(target) -> the ACK arrives at the CURRENT baud in the
   pre-switch format (the device applies the switch only after the ACK
   has fully left the wire) -> the host reopens the port at the new baud
   -> SET_FRAME_FORMAT(slim) -> the ACK arrives at the new baud in the
   legacy format -> stream slim.
3. Failure at any step after IDENTIFY: fall back to the legacy path
   (2 Mbps, fixed frames), surface the fallback as an event + evidence
   entry, never retry the switch.
4. `T_switch` (host, hint 500 ms): if SET_FRAME_FORMAT is not ACKed
   within it after the reopen, the host reopens at 2 Mbps, re-IDENTIFYs
   to confirm the legacy path, and reports (a failed confirm is reported
   as unresolved — the fallback still reports).

## Device revert guard

After applying a baud switch, if no CRC-valid frame arrives within
`T_revert` (hint 250 ms; commissioned per bench per A02), the device
reverts to boot state (2 Mbps + legacy) on its own. Any CRC-valid frame
disarms the guard. The guard is the device's own action; the master
re-IDENTIFYs on its fallback path and finds the boot state.

## Timing basis

The device carries no clock. Nominal timestamps are host-derived:
`t_sample(counter_i) = t_stream_start + counter_i * T_nominal` with
`T_nominal = 1 / SPS_model(current config)` from `rate-model.md`. Every
such timestamp is labelled nominal — model-derived, never
device-measured. A gap keeps the nominal grid.

## Sequence gaps

On decode, `counter != prev + 1` (mod 2^32) emits one gap record (last
seen, first after, missed = delta - 1) into the stream's event/evidence
channel. Gaps are never silently skipped; ring overflow (drop-oldest)
therefore surfaces as gaps — visible, counted, bounded per capture.

## Averaging, reserved fields

Averaging (SET_AVERAGING u16 LE: 0 = raw, else power-of-two counts) and
the reserved modes/trigger fields keep their v1 semantics; the
free-running u32 counter remains the drop-detection basis.
