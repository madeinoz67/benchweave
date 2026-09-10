# First hardware target — FNIRSI DPS-150 and provisional ESP32

**Decision:** DPS-150 is selected by the user. ESP32 is provisional; no exact board or firmware has been selected. This is a discovery and qualification brief, not permission to energise a fixture.

## Evidence gathered

FNIRSI lists the DPS-150 as an adjustable 0–30 V, 0–5 A supply, with PC software and protection features. These are manufacturer product claims, not a commissioned DUT envelope. The product page contains inconsistent input-voltage wording; resolve the actual revision's manual/rating before choosing its input source. Do not design the first ESP32 test around the supply's maximum output. [FNIRSI product page](https://www.fnirsi.com/products/dps-150)

FNIRSI's software page documents a USB data connection and selection of a communication port, and lists Windows/Linux software. It states that device buttons are locked while connected to the PC software. This makes connection/disconnection and local-stop behaviour material qualification items. The page does not establish a complete wire-level API or prove SCPI/USBTMC support. [FNIRSI software instructions](https://www.fnirsi.com/pages/software-downloads)

Two primary community projects are reuse candidates. The JavaScript implementation documents a serial protocol but explicitly labels its protocol description speculative; the Linux C utility exposes control/monitoring and protection options. Inspect exact revisions and licence files before reuse, and independently verify exchanges on the actual hardware. Neither project establishes STG conformance. [cho45/fnirsi-dps-150](https://github.com/cho45/fnirsi-dps-150), [svenk123/dps150tool](https://github.com/svenk123/dps150tool)

For a possible ESP32-DevKitC V4, Espressif documents USB-to-UART communication and mutually exclusive power options. That is one candidate board, not a selection. The eventual fixture must account for USB/serial power paths so a PSU-off test cannot be defeated by another supply path. Review the selected board's schematic; do not assume all ESP32 variants have the same USB hardware. [Espressif DevKitC V4 guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html)

## Proposed integration direction

Use an adapter-backed DPS-150 plugin through the scoped serial host provider if actual enumeration and protocol evidence confirm that path. Do not invoke a community executable as an unrestricted subprocess inside the gateway: reuse an audited codec/behaviour with attribution, or document a reviewed provider boundary. The plugin must preserve host ownership, deadlines, dispatch evidence and no automatic command replay.

Advertise `otdp.dc_psu/1.0.0` only if all required configure/output/measure semantics are satisfied. In particular, verify whether the device can configure and read back the required voltage, current-limit, OVP and OCP values. An enable/disable protection toggle is not necessarily an independently programmable threshold. If the base profile cannot be met, document a narrowly named limited profile or propose a reviewed profile correction; do not manufacture support to satisfy a schema.

For the ESP32 reference DUT, plan a small versioned firmware only if existing firmware cannot supply an appropriate contract. Prefer identity plus correlated numeric uptime telemetry over UART/USB serial, mapped into the embedded-controller profile. Firmware boot logs must not be confused with protocol frames. The firmware is part of the test DUT and cannot be treated as independent protection for itself.

## Discovery checklist and deliverables

| ID | Required observation | Deliverable / decision |
|---|---|---|
| HW-01 | Exact DPS-150 hardware/firmware, labels and connector revision | Versioned device compatibility record |
| HW-02 | Host USB enumeration, transport class, port settings, identity stability | Scoped connection/provider specification; no assumed VID/PID/baud |
| HW-03 | Framing, payload encoding, checksum, correlation and unsolicited telemetry | Reviewed protocol document plus captured positive/negative vectors |
| HW-04 | Configure/readback/output-off/measurement semantics, OVP/OCP support | Profile compatibility matrix; limited profile if necessary |
| HW-05 | Connection handshake, local-button lock, link loss, reconnect and restart behaviour | Failure evidence and ownership/takeover rules |
| HW-06 | Selected ESP32 board/module, schematic, firmware and serial framing | DUT identity/telemetry contract and explicit board selection |
| HW-07 | PSU/DUT/USB power paths, grounding, return paths and independent sensing | Reviewed fixture netlist and protective design |
| HW-08 | Actual DUT envelope, safe condition and timing | Approved commissioning values and measured qualification |

Protocol discovery should start with documentation and passive/read-only evidence where possible. Any live command testing follows an approved supervised commissioning setup. Firmware flashing and output enable are not part of this planning activity. Record source revisions and captured byte exchanges; source snippets alone do not qualify hardware.

## Milestone impact

Simulator development and contract/core work proceed immediately when implementation is authorised. HW-01–HW-05 can run as an early bounded discovery work package once equipment/evidence is available. DPS-150 uncertainty must be resolved before committing the hardware profile and before MVP control qualification. HW-06–HW-08 gate the real DUT and unattended stages, without delaying PoC software fault tests.
