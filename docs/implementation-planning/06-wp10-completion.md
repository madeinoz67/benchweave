# WP10 Completion — DPS-150 Discovery: Evidence, Profile Decision, WP11 Handoff

> Records the state the WP10 discovery branch landed against (2026-09-15),
> reconciles the delivery plan's WP10 row with the repository that now exists,
> and hands off to WP11. Companion to `01-delivery-plan.md` and
> `02-hardware-discovery.md`; those documents remain the controlling scope and
> are intentionally left unedited (delivery-plan WP rows are frozen;
> completions are recorded in companion docs, per the `04-wp01-completion.md`
> precedent).

## Branch and commit range

Branch `wp10-dps150-discovery` off the G2-accepted baseline (`5b39972`,
2026-09-14). Seventeen commits `0bab412..63e4ed9` — one supervised bench day
plus the plugin work it grounded.

## What shipped

| Delivery-plan WP10 row | Reality on the branch |
|---|---|
| `docs/devices/dps150/` | [`compatibility-record.md`](../devices/dps150/compatibility-record.md) v1.0.0 — HW-01–HW-05 evidence, HW-04 profile matrix, panel/local-control note, per-capture provenance, explicit non-claims |
| `fixtures/protocols/dps150/` | Ten committed captures plus `README.md`: first-contact negative, connect, five HW-04 legs, two HW-05 link-loss legs, one live adapter stream |
| `docs/devices/esp32-selection.md` | HW-06 board selection companion |
| `plugins/fnirsi/dps150/` (WP11 scope in the plan) | Session/adapter work shipped early as discovery tooling (961 insertions across 7 plugin files): evidence-backed `session.py` (`b2e7ce6`), handshake-demanding mock pinning the captured negative (`fc3d3d3`), adapter session establishment + telemetry drain/route (`4e5ec60`), correlated-wire trailing-telemetry fix (`16295ab`) |

The plugin's codec and client pre-existed on `main` (colocated in `084df2b`);
this branch added the session layer, the mock that pins the hardware negative,
and the adapter's live-wire behaviour. WP10's gate — "HW-01–06 evidence;
audit community reuse before coding; decide full PSU profile versus explicitly
limited profile" — is closed by the compatibility record plus the ESP32
selection.

## Evidence summary (one supervised session, 2026-09-15)

- **HW-01 identity**: one unit, serial `135DD2594096`, HW V1.0 / FW V1.2;
  idVendor 0x2E3C on file; idProduct not captured.
- **HW-02/HW-03 transport + session**: the handshake (`C1`/`B0`, ~50 ms
  pacing, RTS/CTS) is required — a 12-query negative across six bauds × two
  dialects drew zero bytes; the woken device answers amid a ~2 Hz five-field
  telemetry cycle; both GET dialects live-verified post-handshake.
- **HW-04 profile matrix**: writes sent, captured, restored and verified —
  setpoints 193/194, OVP/OCP 209/210 (independently programmable numeric
  thresholds, binary32-exact snapshot readback), output toggle at 1.00 V
  unloaded. Snapshot field 255 is the setpoint/protection readback; fields
  226/227 are ceiling reports, not setpoint registers.
- **HW-05 link loss**: wake survives port close, host process death and USB
  replug without re-handshake; the wake boundary is device power
  (power-cycle side inferred from the first-contact negative, not captured).
- **Adapter on the real wire**: the live stream poisoned the library's strict
  one-frame-per-chunk rule — trailing telemetry legitimately enters the
  commanded reply window, invisible to the mock. Fixed by correlation
  (`_CorrelatedWire`, `16295ab`); verified 165/165 clean reads over 60 s
  (`5dfc64a`).

## Profile decision

**Full `otdp.dc_psu/1.0.0` profile, honest for this unit on this evidence.**
Every required action (`configure`, `output`, `measure`) has a live-verified
device path, and the base profile's protection requirement is met by
independently programmable OVP/OCP with exact readback — no limited profile is
needed. The scoped limits of that sentence (one unit, unloaded, ≤ 1.00 V; no
accuracy, load, trip or firmware-generality claim; no captured power-cycle
leg) are recorded in the compatibility record's "What this record does not
claim".

## What remains for WP11

- Profile conformance against the required `device-classes.md` §4
  failure-mode cases (invalid coupled settings, failed output-disable
  acknowledgement, readback mismatch, front-panel change, channel-coupled
  failures) — this record's evidence is happy-path.
- Load behaviour: regulation, transients, protection trips under real fault,
  ramp under load — every output proof so far ran unloaded at ≤ 1.00 V.
- Commissioning decisions: input-supply choice (the product page's 32 V/30 V
  conflict is unresolved and field 226 tracks the input rail), attachment and
  local-lock effects, and concurrent local operation treated as a live failure
  mode (panel V-set/I-set displays track the local encoder, not remote
  writes).
- A captured power-cycle leg to close the wake-boundary inference.
- The ESP32 controller plugin and optional reference firmware per the WP11 row
  (PRD-13/14, board/power-path review, independent measurement/protection and
  timing evidence; G3).

## Sequencing

WP10 ran alongside the PoC line and closed the day after G2 acceptance
(2026-09-14). WP11 may proceed per the delivery plan once its remaining
dependency is met: "WP09/10 and approved commissioning setup" — WP09 and WP10
are done; the approved commissioning setup is the open gate.
