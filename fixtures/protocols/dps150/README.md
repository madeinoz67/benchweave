# DPS-150 captured protocol evidence (real hardware)

First contact 2026-09-15, supervised by the principal (approval on record in
the session log): the documented connect sequence (session-open `0xC1`,
baud negotiation `0xB0`), then read-only identity queries. No setpoint,
protection, or output writes were sent at any point in this capture.

## Device identity (HW-01)

| Source | Value |
|---|---|
| USB vendor / product | Artery "AT32 Virtual Com Port", idVendor 11836 (0x2E3C) |
| USB serial | 135DD2594096 (stable across the session; macOS node `usbmodem135DD25940961`) |
| Model (field 222) | `DPS-150` |
| Hardware (field 223) | `V1.0` |
| Firmware (field 224) | `V1.2` |
| Transport | USB 2.0 Full-Speed CDC (usbmodem), 115200 8N1, hardware flow control (RTS/CTS required per upstream; see negatives) |

## Session behaviour (HW-03/HW-05 first observations)

- **The device is silent until the session-open command.** Twelve bare
  field queries across six bauds x two GET dialects (2026-09-15 first
  contact, `first-contact-negative.jsonl` in this directory) produced
  zero bytes. After session-open + baud negotiation, the device answers and
  streams.
- After the session opens, the device emits a **periodic unsolicited
  telemetry cycle**: a repeating five-frame burst, roughly 2 Hz per cycle —
  field 195 (output V/A/W), 192 (input voltage), 226 (reported upper
  voltage limit), 227 (reported current limit), 196 (internal temperature).
- Request/response coexists with the stream: the identity reply arrives as
  the first frame of the window, telemetry continues around it. The plugin
  library's one-frame-per-chunk session rule is therefore right for
  commanded calls on a clean session — but any real transport session must
  expect interleaved telemetry frames.

## First live values (output off, unloaded bench, 2026-09-15 ~07:58 local)

| Field | Meaning | Observed |
|---|---|---|
| 192 | Input voltage | 20.06–20.07 V (stable to ~4 mV across samples) |
| 195 | Output V/A/W | 0.0 / 0.0 / 0.0 |
| 196 | Internal temperature | 21.4–21.5 degC |
| 226 | Reported upper voltage limit | 19.86–19.87 V — **tracks input minus ~0.2 V**; the advertised ceiling follows the input rail, it is not a fixed 30 V |
| 227 | Reported current limit | 5.10 A |

## Files

- `first-contact-negative.jsonl` — the 12 silent bare-query attempts
  (6 bauds x EMPTY/ZERO dialects), no-flow-control: the negative evidence
  that the session handshake (and/or RTS/CTS) is required.
- `connect-v2.jsonl` — the successful connect sequence: every exchange
  byte-verbatim (session-open, baud negotiation, three identity reads, the
  unsolicited tail), decoded views in the session log.

## Provenance and limits

Captured by `.superpowers/sdd/dps150-first-contact.py` and
`dps150-connect-v2.py` (session scratch, gitignored) driving the shipped
`benchweave_fnirsi_dps150` codec for GET framing/decoding; the two session
commands were hand-framed in the discovery script because the library's
supported subset deliberately excludes them (the codec's guard fired as
designed). Framing/checksum agreement between the shipped codec and the
live device is proven by these decodes. Nothing here commissions output,
chooses an input supply, or claims measurement accuracy.
