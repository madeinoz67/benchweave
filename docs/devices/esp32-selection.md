# ESP32 Reference DUT — Board Selection (HW-06, provisional)

> Status: **provisional selection, not final.** This document records the
> WP10 doc-work deliverable for HW-06: a candidate analysis and a provisional
> board, plus the explicit criteria that finalise (or displace) the selection
> at WP11. No hardware was purchased, powered or measured for this document.
> Source basis: the
> [hardware discovery brief](../implementation-planning/02-hardware-discovery.md)
> and the Espressif documentation it cites.

## What the reference DUT must do

From the PRD and the discovery brief, the ESP32 reference DUT is the
*embedded-controller-class device under test*, not an instrument and not a
protection element:

- Expose **identity plus correlated numeric telemetry** (the PRD names
  numeric uptime in seconds with explicit identity/correlation) over a
  serial link, mapped into the `otdp.embedded_controller/1.0.0` profile
  (whose one required action is `telemetry`).
- Be **powered by the DPS-150 output** in the fixture, so gateway-driven
  output control actually controls the DUT: a PSU-off test must remove DUT
  power, not be defeated by another supply path (discovery brief, HW-07
  concern).
- Run a **small separately versioned firmware only if no existing firmware
  supplies that contract**; firmware boot logs must not be confused with
  protocol frames. The firmware is part of the DUT and is not independent
  protection for itself.

The DPS-150 side of the pairing — transport, session behaviour and the full
`otdp.dc_psu/1.0.0` evidence — is recorded in
[`dps150/compatibility-record.md`](dps150/compatibility-record.md).

## Candidate space

The planning documents name exactly one board-level candidate: the
**ESP32-DevKitC V4** ([Espressif user
guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)),
recorded in the discovery brief as "one candidate board, not a selection".
No other specific board is evidenced anywhere in the planning pack, so this
document does not invent competitors; the honest option space is the fork the
brief itself warns about — UART-bridge boards (DevKitC-class, USB arrives via
a USB-to-UART bridge chip) versus ESP32 variants with native USB, whose USB
hardware differs board-to-board ("do not assume all ESP32 variants have the
same USB hardware"). Which side of that fork wins is decided by the power-path
review below, not by preference.

## Power-path analysis (DevKitC V4, documented facts)

Espressif documents for the DevKitC V4:

- A single Micro-USB port, used **both** for board power (the default
  supply) **and** communication with the ESP32 module through a single
  USB-to-UART bridge chip (up to 3 Mbps).
- **Three mutually exclusive power options**: the Micro-USB port; the 5V and
  GND header pins; the 3V3 and GND header pins — with the explicit warning
  that power must be provided by *one and only one* of them, otherwise the
  board and/or the supply can be damaged.

That documented exclusivity collides directly with the fixture's core
requirement. The fixture needs, **concurrently**:

1. DUT power sourced from the DPS-150 output (so output-off removes DUT
   power), and
2. a live telemetry link to the host during powered phases.

On a DevKitC V4 those two share a connector: the only documented data path
(the Micro-USB UART bridge) is also the default *power* path. Powering the
board from the DPS-150 via the 5V/GND header while the USB cable is
connected would present USB VBUS as a second supply — exactly the
mutual-exclusion violation Espressif warns about, and exactly the defeated
PSU-off test the discovery brief forbids (USB would keep the board alive
when the PSU output drops).

The resolution directions WP11 must evaluate against the board's published
schematic (linked from the user guide; obtain and pin the exact revision
there — this document deliberately does not guess a PDF URL):

- **VBUS-isolated data link.** Establish whether the schematic's VBUS entry
  can be isolated (e.g. a VBUS-cut / power-only-blocked USB cable or
  equivalent bench practice) so the UART bridge carries data with the PSU as
  the sole power source, and prove it by measurement: PSU off ⇒ DUT
  telemetry stops and uptime resets on restore.
- **5 V header injection with measured back-feed check.** If VBUS cannot be
  cleanly isolated, measure whether USB VBUS actually back-feeds the 5 V
  rail on the specific revision before ruling the approach in or out — the
  damage warning forbids assuming it is benign.
- **3V3 header injection** is noted for completeness only: it bypasses the
  onboard regulator and is the least forgiving option; it should not survive
  WP11 review unless the schematic and measurements say otherwise.
- **Displacement criterion.** If no clean data-only path exists on this
  board, the selection moves to a variant whose USB hardware separates data
  from power (native-USB ESP32 variants exist; their suitability is an
  WP11 schematic review, not a claim made here) or to an external
  UART-isolating arrangement. That switch is a documented fallback, not a
  pending preference.

Grounding between the PSU output negative, the board's GND, and the host
side of the telemetry link is part of the same HW-07 review; this document
flags it and does not solve it.

## Provisional selection

**ESP32-DevKitC V4** (module variants per the user guide; ESP32-WROOM-32E
shown as the current functional default), provisionally selected on:

- It is the only board-level candidate the planning pack evidences, with
  vendor-documented USB-to-UART communication and explicit power-option
  documentation to analyse against.
- Its documented 5 V header input matches a DPS-150 output envelope
  (the compatibility record's ceiling evidence caps output near
  input − 0.2 V; a 5 V program point is far inside it and inside the
  board's documented 5 V input option — the exact DUT envelope and current
  draw are HW-08 measurements, not claims).
- The UART bridge provides a conventional byte-stream telemetry path for
  the identity/uptime firmware contract.

## What finalises the selection at WP11

The selection becomes final when, on the physical board and its pinned
schematic revision:

1. **Telemetry firmware contract fit (HW-06):** identity + correlated
   numeric uptime telemetry over the UART link maps cleanly into the
   embedded-controller profile, with firmware boot logs demonstrably
   separated from protocol frames (the DPS-150 record's session/telemetry
   work is the model: negative evidence for what the link does *not* do
   without framing).
2. **Power-path review passed (HW-07):** the fixture netlist shows the
   DPS-150 as the DUT's sole power path with the telemetry link
   concurrently live, verified by measurement (PSU-off ⇒ DUT loses power;
   no USB back-feed), and grounding/return paths reviewed.
3. **DUT envelope approved (HW-08):** commissioning voltage/current values
   and timing approved against both the board's documented input ratings
   and the DPS-150's evidenced envelope.

Failure on (2) displaces the board per the criterion above; failure on (1)
is a firmware-contract question first (the PRD's "only if existing firmware
cannot supply the contract" ordering) and a board question only after that.

No firmware exists for this DUT yet (`firmware/esp32_reference/` remains
optional planning scope); nothing here authorises flashing or energisation —
those are WP11 commissioning steps under their own approvals.
