# OTDP measurement and dataset model 0.2.1

**Normative schema:** `otdp-measurement.schema.json` (`urn:otdp:measurement:0.2.1`)  
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

## 7. Mandatory dataset checks M01–M15

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
| M15 | Derived-variable declarations parse under the section 8 grammar, resolve in declaration order, and evaluate with in-band quality loss — see section 8 |

These semantic checks supplement the JSON Schema. They are author/host conformance obligations, not proof that a validator or driver already implements them.

## 8. Derived variables

A device descriptor may declare, in its optional top-level `derived_variables`
array, dataset variables computed from other dataset variables by a
fixed-grammar arithmetic expression. The execution-side device descriptor
carries the same array verbatim; both are validated by the same checks at
their own admission seams (S19). The declaration names `id`, `quantity`,
`unit` and `expression`; `dtype`, `dimensions`, `channel_ids`, `values`,
`uncertainty`, `calibration`, `status` and the `derivation` marker are
produced by evaluation, never declared.

### 8.1 Grammar

```
expression := term (("+" | "-") term)*
term       := factor (("*" | "/") factor)*
factor     := ("+" | "-") factor | atom
atom       := number | identifier | "(" expression ")"
number     := digits ["." digits] | "." digits        ; finite decimal, no exponent
digits     := [0-9]+
identifier := [a-z][a-z0-9_]*                          ; dataset variable id
```

Tokens are exactly `+ - * / ( )`, decimal numbers and identifiers; space is
whitespace. No functions, no `**`, no `%`, no commas, no strings, no
assignment, no exponent notation (`1e3` is a syntax error). Precedence and
associativity are standard and unambiguous: `*` `/` bind tighter than
`+` `-`, all binary operators are left-associative, unary signs bind
tighter than binary operators. An expression must reference at least one
identifier (constant-only expressions cannot carry the marker's
`operand_ids`). Expressions are at most 256 characters with parenthesis
nesting at most 32; unary operator chains recurse against the length cap
(a 255-character chain, not the parenthesis depth), still bounded and
microsecond-scale. The machine truth for this grammar — including every
reject class — is `examples/derivation-vectors.json`.

### 8.2 Operands and static checks

Operands are **dataset variable ids**, not channel ids: a channel is a
source that may carry several quantities (a channel reference names no
value and cannot be unit-checked), while a variable carries the values,
units, dtype and dimensions the checks need, and dataset variable ids are
unique by M01. An expression may reference an original variable or an
earlier-declared derived variable; declaration order is the evaluation
order, which is what makes evaluation deterministic. Self-reference,
duplicate derived ids, forward references and cycles are admission
failures. An operand that names no variable in a given dataset is NOT an
admission failure (datasets vary by action): it degrades in-band at
evaluation.

### 8.3 Evaluation and failure semantics

Evaluation is IEEE-754 binary64 over the grammar's fixed operation
sequence; numeric literals are parsed once, decimal text to binary64, at
parse time. Declaration order is the evaluation order. Re-evaluating a
recorded expression over the recorded operand values reproduces the
recorded values exactly (replay); the `derivation` marker carries the
expression and operand ids beside the values, and this schema's URN pins
the grammar version.

At evaluation, per derived variable: every operand must resolve in the
dataset under derivation, be inline `float64` with finite-or-null elements
(artifact-backed, non-float64 or non-numeric operands refuse — no
broadcasting in this revision), and all operands must carry exactly equal
`dimensions` lists and equal value counts. Integer elements are read only
when exactly representable in binary64 (magnitude at most 2^53): a larger
integer refuses as a dtype mismatch rather than being silently rounded by
the conversion — a representation change the record never consented to. At `+` and `-` nodes whose two
operands are both identifiers, the operand variables' `unit` strings must
be exactly equal; a numeric literal or a nested sub-expression carries no
trackable unit and is not compared (the residual), and `*` and `/` impose
no operand-unit rule — the derived variable's declared `quantity`/`unit`
is author responsibility.

Elementwise: a null operand element yields a null result element; division
by zero and any non-finite intermediate or result yield a null result
element — never `inf`/`NaN` (section 3). If any element became null for
these reasons the variable's status is `partial` with a `status_reason`
naming the failing operations and operands; if every element failed it is
`invalid`. An unresolved operand yields an `invalid` variable whose
`status_reason` names the operand, with empty `values` and `dimensions` —
no element is fabricated for a shape that could not be established. M02's flattened-count agreement presumes the
variable's shape was established; for these records the shape is unknown,
and the empty `values` with empty `dimensions` suspend M02 count-agreement
(no element count is asserted for a shape that was never established).
Structural contradictions refuse the whole derivation loudly (a
descriptor/dataset structural lie is a conformance failure, and the raw
dataset stays in scope as evidence): a derived id already present in the
dataset, a malformed `variables` list, duplicate variable ids in the
dataset (operand resolution must never silently select an arbitrary
duplicate — M01), or a recorded `derivation` marker that is forged
(non-parseable expression, `operand_ids` violating their declared shape,
or disagreeing with the parsed expression).

Evaluation is IEEE-754 honest about signed zero: negating a
positive zero records `-0.0`, deterministically and replay-stably — the
value is not normalized, because normalizing post-hoc would change the
arithmetic semantics the expression pinned (a future second
implementation that serializes differently must answer for its own
encoding, not change this one's).

The derived variable's `channel_ids` is the ordered union of its operand
variables' `channel_ids` (provenance by construction); `dtype` is
`float64`; `uncertainty` and `calibration` are structurally `unknown` — a
propagated bound would presume operand-error independence the contract
cannot evidence, and `applied` calibration would fabricate a reference and
method the combination does not have. A consumer requiring known
uncertainty therefore refuses a derived-variable sample: an honest
refusal, not a defect.
