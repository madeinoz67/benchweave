# OTDP measurement and dataset model 0.3.0

**Normative schema:** `otdp-measurement.schema.json` (`urn:otdp:measurement:0.3.0`)  
**Purpose:** Describe measurement meaning independently of instrument command syntax or file transport.

## 1. Supported representations

The standard dataset kinds are scalar_set, waveform, digital_trace, spectrum, iq, table, event_log, network_parameters and image. The kind identifies meaning; dimensions and variables describe actual data. A representable dataset does not imply a complete control profile exists for the producing device.

Each dataset carries a host-scoped ID, configuration/acquisition references where applicable, acquisition time, clock provenance, axes, variables, trigger context, completion status and context. Context contains the effective acquisition configuration and relevant device/firmware/processing information. Required meaning must be expressed in standard fields or a required recognised profile, not merely free text in context.

Variables carry ID, physical quantity, unit, channel IDs, datatype, dimension IDs, data, uncertainty, calibration and quality status. A scalar variable has dimensions `[]` and exactly one element. A table has an index axis and one variable per column. A multi-channel waveform normally has a time axis and one variable per channel. Distinct channel timing requires distinct axes or explicitly characterised skew.

## 2. Axes, dimensions and storage

An axis has an ID, quantity/unit, positive length and either regular coordinates (`start + i×step`) or explicit numeric coordinates. A regular axis of more than one element must have nonzero step. Time/frequency axes used by standard profiles are increasing. Explicit coordinate count equals axis length. Index axes use unit 1; time axes use seconds relative to the dataset origin.

Variable dimension IDs refer to axes in order. The flattened element count is the product of axis lengths, with scalar product one. Storage is row-major: the last dimension varies fastest. An example image may use dimensions `[y,x]`; an RF array may use `[frequency]` with one variable per port pair. Do not infer channel interleaving from file size.

Exactly one of inline `values` or an `artifact` reference is present. Artifact IDs are host-issued, scoped to the dataset/owner and validated before access. SHA-256 and byte length describe exactly those bytes, without invisible headers or compression. Compression/container formats require an explicit new encoding contract.

| Datatype | Inline representation | Artifact encoding |
|---|---|---|
| float64 | Finite JSON number | f64le, 8 bytes per element |
| int64 | Canonical signed decimal string | i64le, 8 bytes |
| uint64 | Canonical unsigned decimal string | u64le, 8 bytes |
| uint8 | Integer 0–255 | u8, 1 byte |
| bool | JSON boolean | bool_u8: 0/1, 1 byte |
| logic | String 0/1/x/z | logic_u8: 0/1/2/3 respectively |
| string | JSON string | utf8_json array |
| complex128 | `[real,imaginary]`, each finite | complex_f64le, real then imaginary, 16 bytes |

64-bit integers use strings inline to preserve precision across JSON clients. Enforce signed/unsigned 64-bit bounds; `-0` and leading-zero forms are rejected. This is a new typed dataset representation, not a change to the core scalar number's interoperable range. Complex samples are Cartesian, never implicitly polar.

For fixed-width encodings, byte length equals element count times width. `utf8_json` is one strict UTF-8 JSON array with the same inline datatype rules, no BOM or framing terminator. It may be used for null-bearing partial arrays of any datatype; its exact byte length and digest are still checked. Endianness is fixed by encoding. No interpretation is inferred from a vendor filename.

Coordinates are small inline metadata in this base format. Extremely large/irregular coordinate vectors need a separately versioned coordinate-artifact feature before use; an agent must not invent a layout under the current fields.

## 3. Quality, uncertainty and calibration

Variable status is valid, partial or invalid. Partial/invalid require a reason. Inline null represents unavailable/invalid elements; nulls are not permitted in a valid variable. A partial variable must contain both available and unavailable values unless the reason explicitly describes a different quality loss such as dropped samples with otherwise valid retained values. Invalid numeric values never use NaN/Infinity or fabricated zeros.

Datasets returned complete contain the full requested acquisition, even if some measurements are invalid; variable quality remains visible. A dataset missing requested samples is partial, records why, and reports actual axes/shapes. It must not preserve the requested shape by inserting unmarked samples. A consumer distinguishes incomplete acquisition from a complete acquisition that detected invalid/overload conditions.

Uncertainty status is known, unknown or not_applicable. Known requires nonnegative absolute uncertainty in the variable's declared unit. With no coverage factor it is standard uncertainty (factor 1); a supplied factor describes expanded uncertainty. Confidence is reported only when supported by evidence. Unknown is not zero. For logarithmic values, uncertainty is in that logarithmic unit unless an understood profile states otherwise.

The base uncertainty field describes a bound/model applying to all values of the variable. Heterogeneous per-point uncertainty requires a named companion uncertainty variable linked through a recognised profile; it must not be hidden in arbitrary context. Resolution is the reported quantisation increment and is not interchangeable with accuracy or uncertainty.

Calibration status is applied, not_applied or unknown. Applied requires a reference and method; dates are supplied when known. The reference identifies retained calibration evidence, not an unauthenticated URL to fetch or a claim that the gateway performed calibration. A reported factory calibration does not by itself qualify the complete measurement chain, probes or fixture.

## 4. Quantities, units and logarithmic values

Standard profiles use voltage/V, current/A, power/W, resistance/Ohm, capacitance/F, frequency/Hz, temperature/K, time/s, phase/deg, digital_level/1, continuity/1, connection_state/1 and scattering_parameter/1. A profile may introduce another explicit quantity/unit pair; consumers must not infer dimensional compatibility from similar labels.

Temperature readings preserve the applied conversion and compensation in context. Celsius may be a documented extension quantity/unit representation, but the standard DMM temperature profile normalises to K. Numeric prefixes are converted by the adapter before publication so one standard profile does not mix V and mV without explicit units.

Logarithmic values require `log_reference`. For dBm power this is value 0.001, unit W, plus impedance when relevant. dB is not meaningful without its ratio/reference definition in the recognised profile. Power, power spectral density and voltage spectral density are separate quantities. A spectrum plotted against frequency does not make them interchangeable.

Direction is part of class semantics: PSU/SMU positive means delivered to the DUT; electronic-load positive means absorbed. Dataset context records the convention when presenting combined results. Consumers cannot add signed values across these classes without applying the declared convention.

## 5. Time, triggers and synchronisation

Clock metadata identifies a domain, timestamp source, synchronisation status and uncertainty in seconds or null. `started_at` is RFC3339 UTC or null. Host receipt time is not silently described as device acquisition time. A host timestamp may be used only with timestamp_source host and documented latency/uncertainty.

Axis time is relative to the dataset start/origin. Trigger time is a relative number or null; unknown is not zero. Sharing an acquisition ID or a time axis does not prove cross-device synchronisation. Hardware clock/trigger distribution and skew evidence remain necessary where comparisons depend on timing.

For multiplexed channels, context includes `channel_time_offsets_s` mapping every sampled channel to a known offset or null, and `channel_skew_uncertainty_s` as a known nonnegative value or null. If offsets vary materially over time, use explicit per-channel axes. Consumers cannot claim simultaneous sampling when the dataset reports unknown skew.

Segmented acquisitions can be represented as separate datasets linked by a required segment-profile contract; this revision does not standardise the segmented-control profile. Integer tick clocks or absolute nanosecond axes also require a defined extension. Do not mislabel approximate float seconds as exact tick timing.

## 6. Kind-specific semantics

- **scalar_set:** No axes for scalar values; one element per variable. Repeated observations use a table/time axis.
- **waveform:** At least one time axis and one measured variable. Multiple units/channels remain separate variables.
- **digital_trace:** Time axes with logic variables. x/z retain their electrical meaning and are not numeric amplitudes.
- **spectrum:** Frequency axis plus explicitly identified spectral quantities/references. Zero-span power-versus-time uses waveform.
- **iq:** Time axis and complex128 samples, with centre frequency, sample rate and IQ scaling convention in the required RF context/profile.
- **table:** Index or explicit independent-variable axes; columns retain individual datatypes and units.
- **event_log:** Event index and explicit event timing fields, such as the decoder fields in the logic-analyser profile.
- **network_parameters:** Frequency axis, dimensionless complex variables and response/stimulus port pairs. Reference impedance and correction/calibration state are explicit.
- **image:** Explicit spatial axes and pixel variables; colour-space/pixel interpretation requires a recognised image profile. No camera control profile is claimed here.

The data model can carry these forms, but only the twelve published class profiles have defined control operations in this package. IQ/image representations are extension foundations, not complete RF receiver/camera drivers.

## 7. Mandatory dataset checks M01–M14

| ID | Check |
|---|---|
| M01 | Unique axis/variable IDs; every dimension and channel reference exists |
| M02 | Coordinate lengths, dimension products, flattened value counts and byte lengths agree |
| M03 | Inline types, integer bounds, complex ordering and artifact encodings match dtype |
| M04 | All ordinary numeric data/coordinates are finite; invalid elements are explicit |
| M05 | Quality/completion status, reasons and nulls agree with actual data and requested acquisition |
| M06 | Quantity/unit pairs and required class outputs match the selected profile/configuration |
| M07 | Logarithmic quantities have appropriate references; no undocumented unit conversion |
| M08 | Uncertainty/calibration status and values are coherent; unknown is not a zero value |
| M09 | UTC/relative time, clock source, synchronisation and trigger provenance are coherent |
| M10 | Configuration/acquisition IDs belong to the caller, device generation and requested channel set |
| M11 | Artifact identities, hashes, lengths, authorisation and quotas are valid before use |
| M12 | Multiplexed/skewed channels do not falsely claim simultaneous sample timing |
| M13 | Port-pair, decoder, waveform-upload or other class-specific dataset rules hold |
| M14 | Unknown required dataset/profile/encoding contracts are rejected, not treated as opaque success |

These semantic checks supplement the JSON Schema. They are author/host conformance obligations, not proof that a validator or driver already implements them.
