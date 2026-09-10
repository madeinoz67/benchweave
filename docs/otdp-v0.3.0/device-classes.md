# OTDP device-class profiles 1.0.0

**Baseline:** OTDP 0.3.0 · adapter API 1.1  
**Scope:** Twelve explicitly defined device classes. This is a class-contract specification, not a claim that every instrument feature or transport is implemented.

Read this document with `device-profile-catalog.json`, its schema, `measurement-model.md`, `extension-contract.md` and the core specification. The catalog contains the exact input/output schemas for 50 versioned actions; this document defines their physical meaning, state transitions and required evidence. Both are normative within this design package.

## 1. Coverage and composition

| Profile | Complete base action set | Optional standard actions/features |
|---|---|---|
| `otdp.dc_psu/1.0.0` | Configure, output control, measure | Model-dependent channel count and supported settings |
| `otdp.dmm/1.0.0` | Configure function/range/aperture, measure | Supported measurement functions are explicitly constrained |
| `otdp.oscilloscope/1.0.0` | Configure, arm, fetch, abort | Software trigger when supported |
| `otdp.logic_analyser/1.0.0` | Configure, arm, fetch, abort | Software trigger; UART/I²C/SPI decode |
| `otdp.function_generator/1.0.0` | Configure, output control | Arbitrary waveform upload |
| `otdp.electronic_load/1.0.0` | Configure, input enable/disable, measure | Supported CC/CV/CR/CP modes are constrained |
| `otdp.smu/1.0.0` | Configure, output control, measure | Bounded sweep with arm/fetch/abort and optional software trigger |
| `otdp.daq/1.0.0` | Configure, arm, fetch, abort | Software trigger; simultaneous or characterised multiplexed acquisition |
| `otdp.embedded_controller/1.0.0` | Typed telemetry | Verified control writes |
| `otdp.switch_matrix/1.0.0` | Set routes, read routes, open all | Only explicitly described permitted topology |
| `otdp.spectrum_analyser/1.0.0` | Configure, arm, fetch, abort | Software trigger; frequency sweep and declared zero-span mode |
| `otdp.vna/1.0.0` | Configure ports/sweep, arm, fetch, abort | Software trigger; declared port pairs |

An instrument can advertise several profiles. A mixed-signal scope combines oscilloscope and logic-analyser profiles; an integrated fixture may combine DC supply, switching and controller telemetry. Shared physical resources remain one ownership domain. Separate profile names never permit independent clients to drive the same underlying hardware concurrently.

Claiming a profile requires all its base actions and all applicable semantics. Optional actions are absent unless actually supported. Action schemas describe the standard vocabulary; they do not require every device to support every function enum, trigger mode or range. Per-device `input_constraints`, channel metadata and protocol evidence narrow the supported subset. The gateway validates the intersection of standard contract, device constraints and bench policy.

A device missing a base operation must remain an unclassified core integration or use a separately named limited profile. It must not claim the full class and return unsupported for a base operation under every valid configuration. Optional software-trigger action is required if `software` is admitted as a trigger kind.

These profiles do not yet define AC power sources, RF up/downconverters, RF signal-generator modulation families, cameras, environmental chambers, mechanical motion, medical instruments or every specialised analyser. Their measurements may fit the shared data model, but complete control profiles require separately reviewed contracts. Generic `raw_binary` storage is not proof of class support.

## 2. Common channel and action contract

Class descriptors declare physical/logical channels with stable IDs, labels, roles, quantities and any linked scalar parameters. Channel IDs are scoped to a commissioned instrument instance. A function using multiple terminals must document terminal roles; it cannot treat four-wire sensing or a port pair as interchangeable unnamed channels.

Actions are invoked using the core `invoke` verb with `{action_id, input}`. The result echoes action_id and contains the action's typed result. Action IDs include profile name, verb and exact version, for example `otdp.dc_psu.configure/1.0.0`. The gateway resolves schemas from the locally admitted hashed catalog, never from arbitrary remote references. Missing/unsupported actions are rejected before device I/O.

All channel references must exist and have appropriate roles. Arrays of channels are unique unless an action explicitly defines repeated samples. A descriptor must specify real instrument bounds through `input_constraints`; `{}` in a structural reference fixture is not sufficient evidence to commission a source or arbitrary acquisition size.

The action's declared timeout is bounded by the envelope timeout and host deadline. Long work uses acquisition state; a single request cannot extend its lease indefinitely. Idempotence is decided per action, not inferred from the word configure or from use of invoke. Every action, including rejected actions, remains linked to principal, operation ID, profile/schema version and configuration evidence.

## 3. Configuration and acquisition lifecycle

`configuration_id` is issued by the gateway and supplied with configuration input. An adapter must not invent or reuse it. Success returns that ID and the effective configuration actually accepted/read back. The gateway stores it with the device instance generation, channel set, ownership and policy versions. If a multi-channel configuration partly succeeds, report failure/unknown with evidence and invalidate the proposed ID; do not represent it as atomic success.

Source, load and routing configuration requires an approved non-energised/safe transition. In-place live reconfiguration is outside these base profiles. A profile implementation must refuse it rather than silently disable/re-enable hardware. The gateway can sequence disable → configure → verify → enable explicitly. An enable action requires a current configuration ID. An authorised protective disable does not require that token and must not be blocked merely because it expired.

Acquisition progression is **configured → armed → running → complete**, with **aborted** and **outcome unknown** branches. `arm` has a host-issued acquisition ID and maximum duration; it may return running/complete when an immediate or fast hardware trigger has already occurred. `trigger` is valid only for an armed software-trigger configuration. A duplicate trigger must not create another acquisition. `fetch` waits only within its call budget and returns the same acquisition's immutable data; fetching must not re-trigger hardware.

A fetch timeout while a known acquisition is still running is an operation timeout, not automatically an unknown physical acquisition. The acquisition remains subject to its maximum duration. `abort` returns success only after the acquisition is confirmed stopped. Loss of communication during abort is unknown. Abort does not automatically imply PSU output removal: source-bearing classes define additional behaviour below, while independent protection remains authoritative.

Only one acquisition per claimed channel/resource set is active at a time. Completion must retain data until the published retention/quota boundary; an instrument with destructive retrieval needs the adapter/gateway to retain the first result for later fetches. Reset, replacement, local takeover or material configuration change invalidates outstanding live IDs. Archived datasets retain their original provenance.

`allow_partial: false` rejects an incomplete fetch result. If true, partial data must identify missing/invalid values, preserve actual axis lengths and carry status partial and a reason. No zero-padding or false complete status is permitted. Max byte allowances cover all variable payloads, coordinates and published artifacts.

## 4. DC power supply

The channel role is source. Configure uses voltage V, current limit A, overvoltage threshold V and overcurrent threshold A. Numeric polarity/ranges, channel coupling, series/parallel modes and protection availability come from the device evidence and constraints. The base profile requires the configured protection functions; a supply without them cannot pretend they exist. A limited core integration or separate reviewed profile may use external protection.

`output` controls one channel and returns the observed enabled state with readback or physical assurance; an echoed request is insufficient. `measure` returns a scalar_set containing voltage, current and power for every requested channel, in V/A/W. Power may be derived from V×I only if the samples are sufficiently aligned and that derivation and timing uncertainty are recorded. Positive current/power means delivered from the supply to the DUT.

Required failures include invalid coupled V/I/power combinations, missing protection, failed output-disable acknowledgement, readback mismatch, front-panel change and one-channel failure while another remains active. Channel tracking or series/parallel grouping requires explicit per-device constraints and cannot be inferred from channel numbering.

## 5. Digital multimeter

Configure selects a declared function, range, aperture and autozero behaviour. Range values are expressed in the selected function's canonical unit. Aperture is either seconds or NPLC plus explicit 50/60 Hz line frequency; these alternatives cannot be mixed. Devices without a given setting must constrain the profile to a supported documented value or use a limited profile, never silently ignore it.

`measure` requires the current configuration ID and returns scalar_set readings. Canonical function quantities/units are voltage_dc/ac → voltage/V; current_dc/ac → current/A; resistance_2w/4w → resistance/Ohm; capacitance → capacitance/F; frequency → frequency/Hz; temperature → temperature/K; continuity → continuity/1 boolean; diode → voltage/V. Temperature conversion must retain sensor/compensation metadata. AC readings identify RMS/detector and bandwidth conditions in context.

Every result records actual range when known, aperture, overload/under-range/open-sensor conditions and uncertainty/calibration state. An overload is invalid with a reason, not infinity. Resistance, continuity and diode functions may stimulate the circuit; configure/measure side effects and bench policy must reflect this. Terminal selection and two/four-wire sense requirements are documented in the channel mapping.

Required cases include autorange change, overload, aperture timeout, disconnected sense lead and function-dependent unit validation.

## 6. Oscilloscope

Configuration specifies channels, coupling, input range, offset, probe ratio, sample rate, count, pretrigger fraction and trigger. Range and offset use values referred to the probe tip after the declared probe ratio; an adapter must translate the instrument's convention without multiplying twice. Hardware limitations on shared sample memory/rate or active channel count are device constraints.

Fetch returns waveform datasets with one variable per enabled analogue channel and explicit time axes. Samples are calibrated into volts, not undocumented ADC counts. Channels with distinct timing use separate axes or an explicit characterised offset; a shared axis must not falsely imply synchronisation. Probe/coupling/bandwidth/acquisition-mode metadata is retained in context.

Pretrigger fraction is bounded to [0,1] but must also satisfy actual hardware restrictions. Trigger edge sources must be admitted channels; external trigger connectors are commissioned channel resources. Trigger position is relative to the dataset time origin and may be unknown. Unsupported pulse-width, protocol, pattern, segmented or equivalent-time modes require an additional profile, not a misleading edge-trigger declaration.

Required cases include no trigger, trigger before arm response, changing sample rate when channels are enabled, truncated transfer, per-channel skew and interrupted acquisition.

## 7. Logic analyser and protocol decoding

Configure declares digital channels, thresholds, sample rate/count and supported trigger. Fetch returns digital_trace: each line is a logic-typed variable with values 0/1/x/z and a time axis. Devices that cannot distinguish x or z must not manufacture them. Input threshold and electrical voltage tolerance are separate facts; both must be captured in device/bench constraints.

Optional `decode` consumes a completed retained acquisition; it does not re-acquire. UART settings require rx, baud, data bits, parity and stop bits. I²C requires scl/sda and no extra settings. SPI requires clk/cs/mosi/miso, CPOL/CPHA, bit order and word length; this base decoder uses active-low CS. Reject extraneous line roles or settings instead of guessing. Other framing conventions need a named extension.

Decoded event_log has an event-index axis and variables start_s, end_s, payload_hex and status; I²C additionally has address (uint64) and direction (string). The payload is ordered complete bytes as lowercase hexadecimal; non-byte-aligned SPI words require a separate documented representation and are outside this base decode action. Status includes ok or the actual parity/framing/nack/truncation reason. Start/end reference the same capture clock. Decoder identity/version and settings are recorded.

Required cases include unknown levels, sample-rate insufficiency, frame split at the capture boundary, decoder errors and mismatched line maps. Decode is optional; raw digital acquisition is the base capability.

## 8. Function/arbitrary waveform generator

Configure uses explicit frequency Hz, amplitude V peak-to-peak, DC offset V, phase degrees and load impedance Ohm; null load means high impedance. The output convention must state the voltage at that declared load, avoiding the common 50-Ohm/high-impedance factor-of-two ambiguity. For DC, frequency and amplitude are zero and offset is the DC value. Square/pulse require duty cycle; unsupported pulse/ramp shape details are rejected rather than implied.

Supported functions are narrowed by device constraints. Noise generation is bounded by the declared device bandwidth, recorded in effective configuration context through an approved extension if necessary; devices requiring additional mandatory shaping inputs need a richer named profile rather than accepting unspecified behaviour. Live reconfiguration is not part of the base contract.

Optional upload consumes an already validated, authorised dataset with one normalised waveform variable, unit 1, finite values in [−1,1], and explicit sample rate. It returns a host-scoped waveform ID, accepted count and rate. Upload does not enable output. Selecting arbitrary mode requires a valid uploaded waveform ID bound to that instance/channel; reset invalidates volatile assets. The profile's frequency field represents waveform repetition frequency, while upload sample rate describes playback samples; the requested combination must be physically consistent with point count and device capabilities.

Required cases include clipped offset/amplitude combinations, insufficient device memory, malformed uploaded samples, stale waveform IDs, output-load convention and upload interruption. Add artifact_reader permission only when upload is advertised.

## 9. Electronic load

Configure declares mode CC/CV/CR/CP, setpoint and protective minimum input voltage, maximum current and maximum power. Setpoint units are A/V/Ohm/W respectively. Zero resistance is invalid. Unsupported modes and dynamic/load-step functions are excluded through device constraints or separate profiles.

`output enabled` means the load input is engaged. Measure returns input voltage/current/power in V/A/W, with positive current/power representing energy absorbed from the DUT. This is not interchangeable with the PSU sign convention; quantity context includes direction. Bidirectional regenerative equipment requires an SMU or a separate bidirectional power profile.

Acquisition of input values must not imply that the load is inactive. Undervoltage cutoff, loss of control while sinking and cooling/thermal limitations require explicit behaviour and bench protection.

Required cases include insufficient input voltage, protection trip, excessive dissipation, failed disengagement and signed-measurement consistency.

## 10. Source-measure unit

Configure selects voltage/current sourcing, signed level, opposite-quantity absolute compliance, sense wiring and range. Compliance units are A for voltage sourcing and V for current sourcing. Device constraints declare allowed source/sink quadrants; bipolar numbers alone do not prove four-quadrant support.

Output and measure follow the source lifecycle. Scalar results include voltage, current and compliance_active boolean. Positive current/power means delivered to the DUT; negative means absorbed. Remote-sense loss must not be hidden by locally valid readback.

Optional configure_sweep supplies a finite explicit list of level/dwell points, compliance, sense and trigger. Advertising it requires arm/fetch/abort; software trigger is required only if that trigger mode is admitted. Arm does not authorise an unbounded repeat. Fetch returns table data with point index, commanded source level, measured voltage/current and compliance_active. Actual point times are retained where timing is material.

For a source sweep, completion and successful abort must execute the commissioned source-safe transition before releasing control; they cannot simply stop collecting data while leaving an unowned output active. Continued output requires a separately approved enclosing procedure owning that state.

Required cases include compliance at a point, partial sweep, prohibited quadrant, sense failure, abort under load and dwell/deadline exhaustion.

## 11. Data acquisition/digitiser

Configure supplies channels with quantity/unit/range, sample rate/count, sampling mode and trigger. Values must be converted to declared engineering units using documented scaling and calibration; raw counts require a specifically described variable and scale, not an ambiguous voltage label.

Simultaneous sampling requires supporting evidence. Multiplexed acquisition records per-channel offsets/skew and their uncertainty, or uses separate explicit axes if timing is irregular. A multiplexed scan is not represented as a simultaneous sample merely because it has one row. Heterogeneous channels retain their own quantities, units and calibration.

Fetch returns waveform or table datasets. Digital DAQ channels use the logic datatype. Sensor excitation, bridge completion, thermocouple cold-junction compensation and similar features require explicit per-device setup contracts if relevant; they are not inferred from `quantity: temperature`.

Required cases include mixed units, scan skew, sample-clock drift/loss, overflow, conversion/scaling errors and partial buffers.

## 12. Embedded-controller telemetry/control

Base telemetry reads explicitly requested channels and returns a scalar_set or table with stable quantities, units, timestamps, quality and firmware provenance. A structured compound telemetry payload is represented as named typed variables, not a JSON string requiring the AI to invent a parser.

Optional set_control maps a channel and declared scalar parameter to an exact typed value. The parameter must appear in that channel's parameter_names and in the descriptor; access, range and verification rules from the core contract apply. Success reports an effective value with readback/physical assurance. Firmware-specific business operations use versioned vendor actions rather than arbitrary command strings.

Reset and firmware upload are not implied by this class. Reset may be separately advertised through the qualified core operation. Firmware installation requires a separate lifecycle/security contract and remains outside this profile.

Required cases include stale telemetry, firmware mismatch, malformed compound data, invalid control values and a controller reboot during an operation.

## 13. Relay fixture/switch matrix

Channels name commissioned terminals or endpoints. Route supplies the complete desired set of connections and requires break-before-make. The gateway validates it against the device's permitted routing graph, electrical limits and fixture policy before dispatch. Edges are unique, endpoints exist and no self-loop is accepted by this base contract.

The adapter opens conflicting routes, verifies the break, establishes the requested routes and verifies final state. A partial change is not atomic success; the observed partial topology is retained as evidence. Relay coil state may provide readback but must not be described as independent contact continuity verification.

open_all is an authorised protective operation and requires no prior configuration ID. read_routes reports observed connections and assurance. A device unable to verify routing does not meet this base profile; it may use a separately documented limited core interface.

Required cases include forbidden paths, stuck contacts, failed break, partial make, loss of control mid-route and local manual override. Switching can connect external energy even if the relay board itself uses low voltage.

## 14. Spectrum analyser

Configure explicitly declares centre/span Hz, RBW/VBW Hz, detector, reference level dBm, attenuation dB, preamp state, point count and trigger. Device constraints bound all values and identify the input impedance and maximum input conditions separately from display reference level.

Fetch returns spectrum data with a frequency axis and measured power values carrying an explicit logarithmic reference (dBm = 1 mW reference). Detector/RBW/VBW, impedance, averaging and corrections remain in context. Power-per-bin and power spectral density must not share an unlabeled quantity; PSD requires an explicit quantity/unit/reference contract.

Zero span, if supported, returns a time-axis waveform of detected power at the configured centre frequency. It must not publish a zero-step frequency axis as a normal swept spectrum. Trigger timeout, overload, preamp compression risk and an incomplete sweep are distinct outcomes.

Required cases include zero-span versus swept axes, wrong log reference, input overload, interrupted sweep and calibration/correction status.

## 15. Vector network analyser

Configure declares physical ports, start/stop frequency, points, IF bandwidth, source power and requested response/stimulus port pairs. Stop must exceed start for the base sweep. Every port pair must refer to declared requested ports. Device power and connected-DUT constraints apply before arming because measurement itself can emit RF energy.

Fetch returns network_parameters with a frequency axis and complex128 dimensionless variables. Each variable explicitly names its response and stimulus ports; naming a variable S21 alone is insufficient for arbitrary port layouts. Complex values are real/imaginary pairs, not magnitude/phase with undisclosed units. Reference impedance and active calibration/correction/de-embedding state are retained in context.

Calibration acquisition and user-defined de-embedding are not operations in this base profile. The adapter reports whether an existing documented calibration is applied. Unknown/not-applied status must remain visible; it must not fabricate a calibrated measurement.

Completion/abort must leave the RF source in the commissioned idle/protective state unless an enclosing approved procedure explicitly owns continued emission. Required cases include mismatched port maps, inactive calibration, complex-data ordering, partial sweeps and failure to stop emission.

## 16. Class conformance and extension boundary

The author must provide action-schema validation, input-constraint intersection checks, real channel/terminal mapping, mandatory/optional membership checks, typed dataset validation and applicable failures above. Positive structural vectors are examples, not evidence of an implemented driver or safe bench.

For each real action, input_constraints must describe supported modes and finite hardware limits. Schema expressible independent limits go there; coupled power, amplitude/offset, routing and timing requirements are explicit semantic rules backed by device evidence. An agent cannot leave these implicit and call a source-capable plugin complete.

Optional features outside the published contracts use a namespaced versioned profile with input/output schemas, lifecycle, safety effects, state/ownership rules and conformance evidence. Unknown required profiles are rejected. No new class gets a free pass by hiding an untyped command in a string or raw binary artifact.

## 17. Design references

The separation between base class and extension capabilities follows an established instrument-driver approach described by the [IVI Foundation](https://www.ivifoundation.org/About-IVI/Instrument-Classes.html). These OTDP profiles do not claim IVI compliance or interchangeability with an IVI driver.

Multi-channel acquisition needs explicit sampling and signal metadata; [sigrok's documented data formats](https://sigrok.org/wiki/Formats_and_structures) provide relevant examples. Complex sample representation and capture metadata are also documented by [SigMF](https://sigmf.org/). OTDP uses its own typed dataset envelope; format export requires an explicit compatible mapping.
