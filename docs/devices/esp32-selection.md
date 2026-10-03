# ESP32 Reference DUT: Board Selection (HW-06, provisional)

> Status: **provisional selection, not final.** This document records the
> WP10 doc-work deliverable for HW-06: a candidate analysis and a provisional
> board, plus the explicit criteria that finalise (or displace) the selection
> at WP11. No hardware was purchased, powered or measured for this document.
> Source basis: the
> [hardware discovery brief](../implementation-planning/02-hardware-discovery.md)
> and the Espressif documentation it cites.

## What the reference DUT must do

From the product requirements document (PRD) and the discovery brief, the ESP32 reference DUT is the
*embedded-controller-class device under test*, not an instrument and not a
protection element:

- Expose **identity plus correlated numeric telemetry** over a serial link,
  mapped into the `otdp.embedded_controller/1.0.0` profile (whose one
  required action is `telemetry`). The PRD names numeric uptime in seconds.
  It also names explicit identity and correlation.
- Be **powered by the DPS-150 output** in the fixture, so gateway-driven
  output control actually controls the DUT: a PSU-off test must remove DUT
  power, not be defeated by another supply path (discovery brief, HW-07
  concern).
- Run a **small separately versioned firmware only if no existing firmware
  supplies that contract**. Firmware boot logs must not be confused with
  protocol frames. The firmware is part of the DUT and is not independent
  protection for itself.

The DPS-150 side of the pairing is transport, session behaviour and the full
`otdp.dc_psu/1.0.0` evidence.
[`dps150/compatibility-record.md`](dps150/compatibility-record.md) records it.

## Candidate space

The planning documents name exactly one board-level candidate: the
**ESP32-DevKitC V4** ([Espressif user
guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)),
recorded in the discovery brief as "one candidate board, not a selection".
The planning pack gives evidence for no other specific board. This document
does not invent competitors. The honest option space is the fork the brief
itself warns about. One side is UART-bridge boards (DevKitC-class; USB
arrives through a USB-to-UART bridge chip). The other side is ESP32 variants
with native USB. Their USB hardware differs board to board ("do not assume
all ESP32 variants have the same USB hardware"). The power-path review
below, not preference, decides which side of that fork wins.

## Power-path analysis (DevKitC V4, documented facts)

Espressif documents for the DevKitC V4:

- A single Micro-USB port, used **both** for board power (the default
  supply) **and** communication with the ESP32 module through a single
  USB-to-UART bridge chip (up to 3 Mbps).

> **CAUTION:** PROVIDE POWER FROM *ONE AND ONLY ONE* OF THE THREE OPTIONS.
> IF TWO SUPPLIES FEED THE BOARD, THE BOARD AND/OR THE SUPPLY CAN BE
> DAMAGED.

- **Three mutually exclusive power options**: the Micro-USB port; the 5V and
  GND header pins; the 3V3 and GND header pins (see the CAUTION above).

That documented exclusivity collides directly with the fixture's core
requirement. The fixture needs, **concurrently**:

1. DUT power sourced from the DPS-150 output (so output-off removes DUT
   power), and
2. a live telemetry link to the host during powered phases.

On a DevKitC V4 those two share a connector. The only documented data path,
the Micro-USB UART bridge, is also the default *power* path. If the board
gets power from the DPS-150 via the 5V/GND header while the USB cable is
connected, the cable presents USB VBUS as a second supply. That is exactly
the mutual-exclusion violation Espressif warns about. It is also exactly the
defeated PSU-off test the discovery brief forbids. USB would keep the board
alive when the PSU output drops.

WP11 must evaluate these resolution directions against the board's published
schematic. The user guide links to the schematic. Get and pin the exact
revision there. This document deliberately does not guess a PDF URL:

- **VBUS-isolated data link.** Establish whether the VBUS entry of the
  schematic can be isolated. For example, use a VBUS-cut cable or a
  power-blocked USB cable, or an equivalent bench practice. The UART bridge
  then carries data with the PSU as the sole power source. Prove the
  isolation by measurement: PSU off ⇒ DUT telemetry stops. Uptime resets on
  restore.
- **5 V header supply with a measured back-feed check.** If VBUS cannot be
  cleanly isolated, measure whether USB VBUS actually back-feeds the 5 V
  rail on the specific revision before you rule the approach in or out.
  The damage warning forbids the assumption that the back-feed is benign.
- **3V3 header supply** is noted for completeness only. It bypasses the
  onboard regulator. It is the option with the least tolerance. It should
  not survive WP11 review unless the schematic and measurements say
  otherwise.
- **Displacement criterion.** If no clean data-only path exists on this
  board, the selection moves to a variant whose USB hardware separates data
  from power. Native-USB ESP32 variants exist. Their suitability is a WP11
  schematic review, not a claim made here. The selection can also move to
  an external arrangement that isolates the UART link. That switch is a
  documented fallback, not a pending preference.

Ground connections between the PSU output negative, the board's GND, and the
host side of the telemetry link are part of the same HW-07 review. This
document flags them and does not solve them.

## Provisional selection

**ESP32-DevKitC V4** (module variants per the user guide; ESP32-WROOM-32E
shown as the current functional default), provisionally selected on:

- It is the only board-level candidate the planning pack evidences, with
  vendor-documented USB-to-UART communication and explicit power-option
  documentation to analyse against.
- Its documented 5 V header input matches a DPS-150 output envelope. The
  compatibility record's ceiling evidence caps output near input − 0.2 V.
  A 5 V program point is far inside that cap and inside the board's
  documented 5 V input option. The exact DUT envelope and current draw are
  HW-08 measurements, not claims.
- The UART bridge provides a conventional byte-stream telemetry path for
  the identity and uptime firmware contract.

## What finalises the selection at WP11

The selection becomes final when, on the physical board and its pinned
schematic revision:

1. **Fit of the telemetry firmware contract (HW-06):** identity and
   correlated numeric uptime telemetry over the UART link maps cleanly into
   the embedded-controller profile, with firmware boot logs demonstrably
   separated from protocol frames. The DPS-150 record's session and
   telemetry work is the model. It gives negative evidence for what the
   link does *not* do without framing.
2. **Power-path review passed (HW-07):** the fixture netlist shows the
   DPS-150 as the DUT's sole power path with the telemetry link
   concurrently live, verified by measurement (PSU-off ⇒ DUT loses power;
   no USB back-feed), and grounding and return paths reviewed.
3. **DUT envelope approved (HW-08):** commissioning voltage and current
   values and timing approved against both the board's documented input
   ratings and the DPS-150's evidenced envelope.

Failure on (2) displaces the board per the criterion above. Failure on (1)
is a firmware-contract question first (the PRD's "only if existing firmware
cannot supply the contract" ordering). It becomes a board question only
after that.

No firmware exists for this DUT yet. The retired `firmware/esp32_reference/`
placeholder was removed 2026-09-16. Any future reference-DUT firmware belongs
in the device plugin's own project. Nothing here authorises firmware flashing
or energisation. Those are WP11 commissioning steps under their own approvals.
