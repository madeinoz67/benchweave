# FNIRSI DPS-150 Compatibility Record — WP10 Discovery

> Record version 1.0.0 (2026-09-15). Evidence window: 2026-09-15, one
> supervised session (07:54–10:57 local) plus one adapter-path stream run
> (10:47). Every claim below cites a committed capture under
> [`fixtures/protocols/dps150/`](../../../fixtures/protocols/dps150/) or the
> commit that introduced it. All live passes ran under the principal's
> per-leg approval recorded in each capture's provenance header.

## Decision

**The full `otdp.dc_psu/1.0.0` profile is honest for this unit, on this
evidence.** Every required action — `configure` (voltage, current limit,
numeric OVP, numeric OCP), `output`, `measure` — has a live-verified device
path, and the base profile's protection requirement is met by independently
programmable OVP/OCP thresholds with binary32-exact snapshot readback. The
scoped limits of that sentence are recorded below ("What this record does not
claim"); the profile's required failure-mode cases from
[`device-classes.md` §4](../../otdp-v0.3.0/device-classes.md) remain WP11
conformance work, not discovery claims.

## Identity (HW-01)

| Source | Value | Evidence |
|---|---|---|
| USB vendor | Artery "AT32 Virtual Com Port", idVendor 11836 (0x2E3C) | first-contact session log, [`README.md`](../../../fixtures/protocols/dps150/README.md) |
| USB serial | `135DD2594096`, stable across the session and across USB re-enumeration (node name unchanged: `/dev/cu.usbmodem135DD25940961`) | [`hw05-leg3-replug.jsonl`](../../../fixtures/protocols/dps150/hw05-leg3-replug.jsonl) |
| Wire field 222 | Model `DPS-150` | [`connect-v2.jsonl`](../../../fixtures/protocols/dps150/connect-v2.jsonl) step `identity-222` |
| Wire field 223 | Hardware `V1.0` | `connect-v2.jsonl` step `identity-223` |
| Wire field 224 | Firmware `V1.2` | `connect-v2.jsonl` step `identity-224` |
| Adapter identify | `manufacturer: FNIRSI, model: DPS-150, firmware: V1.2` in 425.4 ms | [`live-stream.jsonl`](../../../fixtures/protocols/dps150/live-stream.jsonl) step `identify` |

One unit is evidenced: serial `135DD2594096`, HW V1.0 / FW V1.2. Nothing in
this record extends to another serial, hardware revision or firmware without
re-qualification.

## Transport (HW-02)

- USB 2.0 Full-Speed CDC (`usbmodem`), 115200 8N1, **hardware flow control
  (RTS/CTS) required** per upstream and carried as a precondition by every
  live pass in this record.
- The 12-silence negative (below) was captured **without** flow control and
  **without** the handshake, so it does not separate the two requirements;
  both are treated as preconditions (stated first in
  [`protocol-evidence.md`](../../../plugins/fnirsi/dps150/docs/protocol-evidence.md)).
- ~50 ms pacing between the two handshake frames and after every write
  (upstream-verified; the captured connect sequence uses it).
- Baud is not auto-detected in any useful sense: bare queries at 115200,
  9600, 19200, 38400, 57600 and 230400 all drew zero bytes before the
  handshake ([`first-contact-negative.jsonl`](../../../fixtures/protocols/dps150/first-contact-negative.jsonl)).
- The `/dev` node name is stable across USB unplug/replug
  (`hw05-leg3-replug.jsonl`: `old_node` == `new_node`).

## Session behaviour (HW-03, HW-05)

**The handshake is required.** Twelve bare field-222 queries — both GET
dialects (EMPTY and ZERO) across six bauds, no flow control — produced zero
reply bytes (`first-contact-negative.jsonl`, commit `0bab412`). After
session-open `F1 C1 00 01 01 02` and, ~50 ms later, baud negotiation
`F1 B0 00 01 05 06`, the device answered GETs and streamed telemetry
(`connect-v2.jsonl`). Neither handshake frame draws a reply of its own; wake
is proven only by the traffic that follows.

**Wake is power-cycle-bound.** The wake state survived every link-level event
tested and requires no re-handshake on reconnect:

| Event | Cold query, no re-handshake | Capture |
|---|---|---|
| Port close and reopen | answered (`DPS-150`) | [`hw05-leg12-linkloss.jsonl`](../../../fixtures/protocols/dps150/hw05-leg12-linkloss.jsonl) L1 |
| Host process death mid-session (fresh process) | answered | `hw05-leg12-linkloss.jsonl` L2 |
| USB unplug + physical replug | answered | `hw05-leg3-replug.jsonl` L3 |

The device is silent after power-up (that is the first-contact state), so the
wake boundary is device power, not the USB link. No capture in this record
power-cycles the unit; the power-cycle side of that sentence is inference
from the first-contact negative, not a captured leg.

**GET dialects.** ZERO-payload GETs are live-verified post-handshake
throughout; EMPTY was exercised only in the silent pre-handshake phase until
HW-04 leg 6 ran one EMPTY GET 222 post-handshake and received `DPS-150`
(`hw04-leg34-current-protection.jsonl`, step `leg6-dialect-EMPTY`). Both
dialects are live; the shipped `Client` still requires the caller to select
one explicitly.

## Telemetry

Once woken, the device emits an unsolicited periodic cycle: five fields per
cycle — **195 (output V/A/W), 192 (input voltage), 226 (reported upper
voltage limit), 227 (reported current limit), 196 (internal temperature)** —
at roughly 2 Hz per cycle (`README.md`; field sequence captured verbatim in
`hw04-leg1-baseline.jsonl` step `telemetry-sample`). The cycle interleaves
with request/response: a commanded reply typically arrives as the first frame
of a window with telemetry frames around and **trailing into** it
(`connect-v2.jsonl` identity reads: 16 frames per reply window).

**Consequence (live-only defect, fixed).** The protocol library's strict
one-frame-per-chunk rule — extra bytes in a response chunk are an error — is
correct on a drained session but false on the live device, where trailing
telemetry legitimately enters the commanded reply window. This poisoned live
sessions while remaining invisible to the mock (whose stream pauses around
commanded replies). Fix commit `16295ab` consumes each commanded reply window
by correlation — first frame matching the requested field is the reply, every
other frame is telemetry, buffered into the adapter's measurement surface
(`_CorrelatedWire` in
[`adapter.py`](../../../plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/adapter.py)).
Post-fix verification: **165/165 reads ok over 60 s, p50 162.1 ms, max
195.5 ms, identify ok (425.4 ms), no bad values**
([`live-stream.jsonl`](../../../fixtures/protocols/dps150/live-stream.jsonl),
commit `5dfc64a`).

First live values (output off, unloaded bench): input 20.06–20.07 V; output
0/0/0; temperature 21.4–21.5 °C; field 226 = 19.86–19.87 V — **the reported
ceiling tracks input minus ~0.2 V, not a fixed 30 V**; field 227 = 5.10 A
(`README.md`). Fields 226/227 are *ceiling reports*, not setpoint readbacks
(HW-04 legs 2–3 below).

## HW-04 profile matrix

Normative source: `otdp.dc_psu/1.0.0` requires `configure`, `output`,
`measure` (contracts `otdp-v0.3.0/device-profile-catalog.json`);
[`device-classes.md` §4](../../otdp-v0.3.0/device-classes.md) requires the
configured protection functions and observed-state output assurance.

| Profile requirement | Device path | Live evidence | Capture |
|---|---|---|---|
| `configure`: `voltage_v` | Write field 193 | Accepted; applies at terminals — 1.00 V commanded, output sampled 0.834 V (ramp) then 1.000 V; snapshot `set_voltage=1.0` | [`hw04-leg5-output-toggle.jsonl`](../../../fixtures/protocols/dps150/hw04-leg5-output-toggle.jsonl) 5b |
| `configure`: `current_limit_a` | Write field 194 | Accepted; snapshot `set_current=0.5` after SET 0.500 A; restore 5.0 verified | [`hw04-leg3b-setcurrent-snapshot.jsonl`](../../../fixtures/protocols/dps150/hw04-leg3b-setcurrent-snapshot.jsonl) |
| `configure`: `ovp_v` | Write field 209 | Programmable numeric threshold; snapshot `ovp=5.5` exactly after SET 5.5 V; restore 30.0 verified | [`hw04-leg34-current-protection.jsonl`](../../../fixtures/protocols/dps150/hw04-leg34-current-protection.jsonl) leg 4 |
| `configure`: `ocp_a` | Write field 210 | Programmable numeric threshold; snapshot `ocp=0.05000000074505806` (binary32 of 0.05) after SET 0.050 A; restore 5.1 verified | `hw04-leg34-current-protection.jsonl` leg 4 |
| `configure`: `effective_configuration` | Snapshot read (field 255) | Setpoints and protections read back binary32-exact via the combined 139-byte record | legs 3b/4/5b |
| `output`: enable/disable | Write field 219 | ON at 0 V (enabled, output 0/0/0) and ON at 1 V (ramp then 1.0 V at terminals); OFF returns `enabled=false`; assurance is observed state (snapshot `enabled` + field 195/219), not an echo | `hw04-leg5-output-toggle.jsonl` 5a/5b |
| `measure` | Field 195; snapshot 255 | Live V/A/W tuple on request and as the ~2 Hz stream; combined snapshot adds input voltage, temperature, setpoints, protections | `hw04-leg1-baseline.jsonl`; `live-stream.jsonl` |

**Protection tuple (snapshot baseline, leg 4):** OVP 30.0 V, OCP 5.1 A,
OPP 150 W, OTP 80 °C, LVP 5 V; protection state `normal`, mode `CV`,
`enabled=false`. Only OVP/OCP are writable in the reviewed protocol subset;
OPP/OTP/LVP are reported values with no write path exposed. The discovery
brief's standing worry — "an enable/disable protection toggle is not
necessarily an independently programmable threshold" — is resolved on
evidence: OVP and OCP **are** independently programmable numeric thresholds
with exact readback.

**Readback path resolution (recorded honestly).** HW-04 leg 2 (SET 193 =
5.00 V → GET 226 still ~19.87 V) and leg 3 (SET 194 = 0.100 A → GET 227
still 5.1 A) first looked like "write accepted, no readback": fields 226/227
are ceiling reports, not setpoint registers. Legs 3b/4/5b then established
snapshot field 255 as the setpoint/protection readback. The earlier
"dispatch-only" reading in commit `01cc7e2` was correct at the time and is
superseded by this record.

## Panel and local control (human-factors note for WP11)

Observed by the principal during the register-write legs
(`hw04-leg5-output-toggle.jsonl`, panel-observation entries, commits
`b349e11` + correction `62b9e79`):

- The panel **output display mirrors live output state** — the 1 V appeared
  and disappeared with the remote toggle and restore.
- The panel **V-set/I-set displays track the local encoder, not remote
  writes** — the V-set display never moved from 0 while the device was
  commanded to and delivering 1.00 V, and the principal's mid-session local
  5.0 A entry showed on the panel while remote writes did not.
- **Local control remains live during an active PC session.** FNIRSI's
  documented button-lock is behaviour of their PC software, not a hardware or
  protocol guarantee; a bare protocol session does not invoke it.

Consequence: panel setpoint displays are **not** authoritative for
remote-set verification — wire readback (snapshot 255) is. WP11 commissioning
must treat concurrent local operation as a live failure mode (the
`device-classes.md` §4 "front-panel change" case), not a locked-out one.

## Provenance

| Capture | Commit | Establishes |
|---|---|---|
| `first-contact-negative.jsonl` | `0bab412` | 12-silence negative: no handshake (and/or no RTS/CTS) → zero bytes, six bauds × two dialects |
| `connect-v2.jsonl` | `0bab412` | Successful connect sequence byte-verbatim; identity strings; interleaved reply windows; unsolicited tail |
| `hw04-leg1-baseline.jsonl` | `64a95c8` | Read-only baseline through the shipped session layer; telemetry field sequence |
| `hw04-leg2-voltage.jsonl` | `01cc7e2` | Field-193 write accepted; 226 is not a setpoint readback |
| `hw04-leg34-current-protection.jsonl` | `1f0b7f4` | 227 is not a setpoint readback; snapshot setpoint readback; programmable exact OVP/OCP; protection tuple; EMPTY dialect live post-handshake |
| `hw04-leg3b-setcurrent-snapshot.jsonl` | `1f0b7f4` | Snapshot `set_current` readback, restore verified |
| `hw04-leg5-output-toggle.jsonl` | `b1a720a` | Output toggle proof (0 V and 1 V incl. ramp), snapshot assurance, restores; panel observations + correction (`b349e11`, `62b9e79`) |
| `hw05-leg12-linkloss.jsonl` | `a97d04e` | Session survives port close and process death, no re-handshake |
| `hw05-leg3-replug.jsonl` | `4994187` | Session survives USB replug; node name stable |
| `live-stream.jsonl` | `aae2088` → `5dfc64a` | Adapter-path stream: poisoning diagnosis in history, post-fix 165/165 clean run |

Software provenance: captures were driven by the shipped
`benchweave_fnirsi_dps150` codec for GET/SET framing and decoding (scratch
harness scripts under gitignored session paths; approvals recorded in the
capture provenance headers). Protocol source pinning, licence attribution and
the supported-subset definition live in
[`protocol-evidence.md`](../../../plugins/fnirsi/dps150/docs/protocol-evidence.md).
Commit `b1a720a` additionally records a mid-run harness crash during leg 5,
emergency-restored and re-run clean within the codec's 260-byte feed bound.

## What this record does not claim

- **No measurement accuracy or calibration.** Live values are wire decodes,
  not traceable measurements; nothing here qualifies the DPS-150 as a
  reference instrument.
- **No load behaviour.** Every output proof ran unloaded at ≤ 1.00 V.
  Regulation, transients, protection *trip* behaviour (OVP/OCP/OPP/OTP/LVP
  under real fault) and the ramp under load are WP11/WP12 work; protection
  state was observed `normal` throughout.
- **No input-supply choice.** The product page's input-rating conflict
  (32 V table vs 30 V caution) is unresolved, and field 226 shows the
  output ceiling following the input rail; selecting the input source is a
  commissioning decision, not made here.
- **No firmware generality.** One unit, HW V1.0 / FW V1.2. Setpoint
  quantisation (0.01 V / 0.001 A) is enforced client-side from reviewed
  manual ranges; device-side resolution beyond the 1.00 V exact apply is not
  separately asserted.
- **No profile conformance run.** The required failure-mode cases of
  `device-classes.md` §4 (invalid coupled settings, failed output-disable
  acknowledgement, readback mismatch, front-panel change, channel-coupled
  failures) are WP11 conformance tests against this record's happy-path
  evidence.
- **No power-cycle leg.** The power-cycle boundary of the wake is inferred
  (first-contact silence + link-loss survival), not captured.

Companion document: [`esp32-selection.md`](../esp32-selection.md) (HW-06).
The delivery plan's WP10 gate is closed by this record plus that selection;
the plan document itself is intentionally left unedited (its WP rows are
frozen; completions are recorded in companion evidence docs).
