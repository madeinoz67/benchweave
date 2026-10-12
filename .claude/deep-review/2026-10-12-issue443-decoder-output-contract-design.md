# Issue #443 — the OTDP decoder-output contract (design record)

**Date:** 2026-10-12
**Branch:** `feat/issue443-decoder-output-contract`
**Issue:** madeinoz67/benchweave#443 (`gateway`)
**Verdict:** BUILD — as a purely additive OTDP 0.2.3 standards motion, with the issue's
premise corrected (see §1) and the SDK leg as a named, ordered follow-on.
**Review tier (design-time call, rubric #254):** **Tier 3** — the build diff touches
`standards/` and adds JSON Schema files (the path rule fires before any keyword rule).
The standards-governor mandate applies (any `standards/` touch). Keyword-scan result in
§11.

---

## 0. Summary

OTDP 0.2.2 already has a decoder-output surface — the optional
`otdp.logic_analyser.decode/1.0.0` action — but it is a **closed trio** (uart/i2c/spi,
corpus-embedded settings) whose output is a **byte-flattened** `event_log`
(`start_s`, `end_s`, `payload_hex`, `status`). It cannot carry annotation-class
identity, non-byte events (start/stop/ack/nack/warnings), row structure, or any decoder
outside the trio; adding a decoder today requires a catalog revision. The gap the issue
names is real once stated precisely: **there is no declarative decoder surface** — no
plugin-declared class/row model a generic renderer can draw from, and no
declaration-driven decode dispatch.

This design closes that gap the way the corpus already points to
("Other framing conventions need a named extension" — device-classes.md §7): a new
**decoder-declaration document family** (`otdp-decoder.schema.json` +
`protocol-decoders.md`), a new optional descriptor field (`decoders`, the provider
triple shape verbatim), a new optional catalog action
(`otdp.logic_analyser.decode_annotated/1.0.0`), and an **annotation-form `event_log`**
dataset shape (class-bearing string variables — no measurement-schema structural
change). Everything is optional and additive: no previously-valid descriptor, dataset
or document is refused, so the bump class is **PATCH (0.2.2 → 0.2.3)** under
GOVERNANCE's change-class table, argued with the same template the 0.2.2 errata commit
used (`a103a4cf`).

The contract shape is extracted from three real decoders of the public sigrok decoder
corpus (i2c, spi, uart — the issue's own candidates), with a fourth decoder outside the
extraction set (onewire_link) as the genericity control. Stacking and binary emission
defer; annotation records, class/row declarations and channel binding — the
UI-rendering core — are the first slice.

## 1. What 0.2.2 actually has — the premise correction

The issue states "OTDP 0.2.2 defines no surface for decoder output". Reading the corpus
says otherwise, and the correction changes the design for the better:

- **The action exists.** `device-profile-catalog.json` carries
  `otdp.logic_analyser.decode/1.0.0` (optional): input `{acquisition_id, protocol
  (enum uart|i2c|spi), line_map (role→channel-name map), settings (closed per-protocol
  union)}`, output `$ref urn:otdp:measurement:0.2.2#/$defs/dataset`, `side_effect:
  none`, `lifecycle: direct`.
- **The output form exists.** device-classes.md §7 (lines 89–97): the decoded
  `event_log` has an event-index axis and variables `start_s`, `end_s`, `payload_hex`,
  `status`; i2c additionally `address` (uint64) and `direction` (string); "Decoder
  identity/version and settings are recorded"; the worked example lives in
  `examples/class-action-vectors.json` (dataset `dataset-decode`: quantities
  `time/s`, `protocol_payload/1`, `protocol_status/1`; context carries
  `decoder_id: "reference-uart/1.0.0"`).
- **The corpus anticipated this exact question.** measurement-model.md §6, event_log
  bullet: "such as **the decoder fields in the logic-analyser profile**"; §7 M13:
  "**decoder**, waveform-upload or other class-specific dataset rules hold".
- **The pointer to this design is in the prose.** device-classes.md §7: "Other framing
  conventions need **a named extension**."

What 0.2.2 lacks, mapped to the issue's five surfaces:

| # | Surface (issue) | 0.2.2 status |
|---|---|---|
| 1 | Annotation records (start/end sample, decoder id, class, payload) | **Partial.** `start_s`/`end_s` exist (float64 s, capture-clock referenced); class identity, non-byte events and multi-text do not; the decoder id is dataset context, not per-record |
| 2 | Class and row declarations (render without decoder knowledge) | **Absent.** The trio's variables are fixed corpus prose; each new decoder is a catalog revision |
| 3 | Channel bindings onto the descriptor's channel list | **Closed form exists** (`line_map`, role→channel, C04-checked); not declaration-driven |
| 4 | Binary outputs | Absent for the declarative path (the trio's `payload_hex` covers byte export narrowly) |
| 5 | Decoder stacking (i2c feeds EEPROM-class) | Absent |

So the design does not invent a surface; it **generalises the existing one** from a
closed trio to a declared model, exactly along the seam the corpus names.

## 2. Evidence base — the extraction (real decoders, not imagination)

Source: the public sigrok decoder corpus (132 protocol decoders). The class-surface
declarations and `put()` payload shapes of the three candidates, read in full:

- **i2c** (`decoders/i2c/pd.py`): 2 required channels (`scl`, `sda`), no optional; 1
  option (`address_format`, string with values); **11 annotation classes** in 3 rows
  (`bits`, `addr-data`, `warnings`); 4 binary classes; PYTHON payload
  `[ptype, pdata]` (`['ADDRESS WRITE', 0x50]`); ANN payload `[class_idx, [texts...]]`
  with texts pre-rendered longest-first from the PD's own template table (`proto`,
  lines 55–67); META output (bitrate).
- **spi** (`decoders/spi/pd.py`): 1 required channel (`clk`) + 3 optional
  (`miso`, `mosi`, `cs`); 5 options including a **free-numeric** one (`wordsize`,
  default 8, no values list); **7 annotation classes** in 7 rows; 2 binary classes;
  PYTHON payload `[ptype, data1, data2]` with per-field `None` for unsupplied optional
  channels.
- **uart** (`decoders/uart/pd.py`): **0 required channels** + 2 optional (`rx`, `tx`);
  13 options including **float-valued** `stop_bits` (0.0–2.0), sentinel-default
  integers (`rx_packet_delim: -1`) and unconstrained numerics (`sample_point: 50`);
  **18 annotation classes** in 10 rows; PYTHON payload `[ptype, rxtx, pdata]` with
  tuple payloads.
- **Stacking evidence** (`decoders/eeprom24xx/pd.py`): `inputs = ['i2c']`, **no
  channels at all**, `decode(ss, es, data)` invoked from the lower decoder's
  OUTPUT_PYTHON `put` — the shape surface 5 must eventually carry.

Cross-checks that pinned the model (from the accompanying decoder-integration
analysis, 2026-10-12, over all 132 PDs): the complete PD runtime surface is 7 module
names + 6 instance members; the four output kinds are ANN / PYTHON / BINARY / META;
annotation texts are always pre-rendered strings ordered longest-first; row grouping
references classes **by positional index** in sigrok (a Python-interface artifact this
design replaces with stable ids, §3.1).

## 3. The mechanism

All new bytes land in `standards/otdp/0.2.3/` (a copy-never-move of 0.2.2 plus the
additions below; the version sweep follows the 0.2.2 train's own pattern — schema
`$id`s/consts, `catalog_version`/`otdp_version`, the 12 measurement `$refs`, example
urns).

### 3.1 The decoder-declaration document family

Two new corpus files:

- **`otdp-decoder.schema.json`** (`urn:otdp:decoder:0.2.3`) — validates a declaration
  document:
  - `id` (`^[[a-z][a-z0-9_]*$`), `version` (three-component semver — the declaration's
    own version, so dataset context can record `"i2c/1.0.0"` exactly like the existing
    example's `"reference-uart/1.0.0"`), `name`, `longname?`, `desc?`, `tags?`
  - `channels: [{id, name?, desc?}]` (required, may be empty — uart has none),
    `optional_channels` (same shape)
  - `options: [{id, desc?, default, values?}]` — `default` is required and carries the
    JSON type (`string` | `number` | `boolean`); `values`, when present, is an array
    all of whose items match `default`'s type (uart's float `stop_bits` and spi's
    free-numeric `wordsize` are both representable — the extraction proved the need
    for both shapes)
  - `annotations: [{id, label}]` — the class declarations (i2c: 11, spi: 7, uart: 18)
  - `annotation_rows: [{id, label, annotation_ids: [...]}]` — grouping **by class id,
    not positional index** (the sigrok index is a Python-interface artifact; OTDP's
    corpus convention is stable snake_case ids — channels, parameters, line_map roles
    all follow it). Translation from a real PD is mechanical: index *i* →
    `annotations[i].id`.
  - `binary: [{id, label}]` — declared for surface honesty (i2c: 4, spi: 2); **emission
    is deferred** (§6), so nothing consumes it in 0.2.3 beyond shape validation
  - `additionalProperties: false` throughout; no `inputs`/`outputs` fields (stacking
    defers — no dead fields)
- **`protocol-decoders.md`** — the normative prose: declaration semantics, the
  admission posture (§3.2), the annotation-form dataset rules (§3.4), and the PD-checks
  (§3.5). The `transport-providers.md` document is the structural precedent — a
  mid-version named extension with its own schema and rules.

### 3.2 The descriptor surface

A new **optional** root field on `otdp-device-descriptor.schema.json`:

```json
"decoders": [{
  "id":   "i2c",
  "path": "decoders/i2c.json",
  "sha256": "<64 hex>"
}]
```

— the root `contracts` item shape **verbatim** (`{id, path, sha256}`;
extension-contract.md §1), the same shape the 0.2.1 provider object embedded. The
document is package-relative, digest-pinned, resolved inside the admitted bundle, and
validated against `otdp-decoder.schema.json`. The descriptor's own digest pin covers
the reference; admission verifies the declaration's bytes against its sha256 (the
CON-1 family discipline).

**Admission posture — deliberately lighter than transport providers.** A provider
contract is an operator-admitted commissioning-class act because transport authority
flows through it. A decoder declaration gates no physical access: the action that
consumes it is `side_effect: none` over a **completed, retained** acquisition (the
existing decode action's own posture — "consumes a completed retained acquisition; it
does not re-acquire"). Admission is therefore digest + schema + semantic checks
(PD1–PD6), with no operator commissioning step. This distinction is stated in
`protocol-decoders.md` so the asymmetry is a recorded decision, not an oversight.

**Zero gateway code in this slice.** Descriptor admission resolves the schema by the
descriptor's own `otdp_version` pin (CON-1's #215/#217 amendments), so a 0.2.3-pinned
descriptor carrying `decoders` is structurally admissible the moment the corpus lands;
0.2.2-pinned descriptors are untouched. The gateway-side semantic mirrors (pin
verification, channel_map resolution, option validation at the admission seam) are the
named slice-2 follow-on (§6), mirroring how the provider lane landed corpus-first with
admission hardening in its own increment.

### 3.3 The catalog action

`device-profile-catalog.json` gains one optional action,
**`otdp.logic_analyser.decode_annotated/1.0.0`**, and the `otdp.logic_analyser/1.0.0`
profile's `optional_actions` grows to name it. Input:

- `acquisition_id` (string) — same posture as decode/1.0.0
- `decoder` (string, snake_case) — must name an id in the descriptor's `decoders`
  array (PD3)
- `channel_map` (object, decoder channel id → device channel id) — generalises
  `line_map`; every **required** declaration channel must be mapped (PD3); mapped
  device channels must exist in the descriptor's `channels` (C04's existing rule);
  unmapped **optional** channels are legal (the spi/uart posture — the decoder reads
  them as absent)
- `options` (object) — free-form in the catalog schema, validated **semantically**
  against the declaration's option specs (PD4), because the specs are declaration
  data, not catalog bytes

Output: `$ref urn:otdp:measurement:0.2.3#/$defs/dataset` — an `event_log` in the
annotation form (§3.4). `side_effect: none`, `lifecycle: direct`, `retry:
idempotent` (deterministic reinterpretation of retained evidence).

The existing `decode/1.0.0` is **untouched** — the trio remains the zero-declaration
path; the new action is the declared-decoder path. No previously-valid binding is
refused.

### 3.4 The dataset form — annotation `event_log`

**No structural change to `otdp-measurement.schema.json`** beyond the version sweep.
The annotation form is prose + checks, exactly like the existing byte form (the corpus
pattern: kind semantics live in measurement-model.md §6 + M-checks, not schema
conditionals — the dataset def's only kind conditional today is the status/status_reason
pair). The form:

- kind `event_log`; event-index axis (quantity `index`/1, regular 0..N-1)
- variables, all dimensions `["event"]`:
  - `start_s`, `end_s` — `float64`, `time`/`s` (the existing decode's own
    representation; §6 defers tick-exact integer coordinates with the arithmetic that
    shows float64 is sample-exact at the catalog's bounds: 1e6 samples at any rate
    keep the sample period ≥ ~1e-6 of the span, ~10 orders inside float64's relative
    precision)
  - `class` — `string`, quantity `annotation_class`/1 — **every value must resolve to
    an annotation id of the named decoder's declaration** (PD5; the M13 carrier)
  - `text` — `string`, quantity `annotation_text`/1 — the record's primary
    (longest) pre-rendered text; the declaration's class labels are the generic
    fallback label (multi-text zoom fidelity defers, §6)
- `context` carries `decoder_id` (`"<id>/<version>"`), the effective options, and the
  channel_map — mirroring the existing example's `decoder_id` context field and §7's
  "decoder identity/version and settings are recorded"
- dataset-level `status` carries decoder failure honestly (`partial`/`invalid` with
  reasons) — A06's in-band quality-loss posture, same as the existing decode's
  required "decoder errors" case

The renderer's row grouping comes from the **declaration** (`annotation_rows`), not the
dataset — which is the point of surface 2: the UI reads one pinned declaration and one
generic dataset form, and needs zero decoder-specific code.

### 3.5 The PD-checks (semantic, in `protocol-decoders.md`)

| ID | Check |
|---|---|
| PD1 | Declaration documents are digest-pinned, package-relative, schema-valid; decoder ids unique across the descriptor's `decoders` array |
| PD2 | `annotation_rows.annotation_ids` resolve in `annotations`; no annotation id appears in two rows |
| PD3 | `decode_annotated.decoder` names a declared decoder; `channel_map` covers every required channel; mapped targets exist in the descriptor's channels |
| PD4 | `options` keys exist in the declaration; values match the declared type; values present in `values` when the spec declares them |
| PD5 | Output dataset: kind event_log, annotation variable set present, every `class` value resolves against the declaration, `start_s ≤ end_s`, event-axis length equals the variable lengths (M02) |
| PD6 | Declaration binary classes are shape-valid but unconsumed (the honest disclosure that binary emission is out of scope in 0.2.3) |

The devices architecture validator (`scripts/architecture/check_devices.py`) gains the
census arms over the new examples plus mutation rows (broken pin, unresolved row class,
duplicate decoder id, unknown option, unresolvable dataset class) — each RED-proven
against the pre-mechanism tree, the 0.2.1 RED-commit shape (`5af97935`).

### 3.6 What does NOT move

- `otdp-runtime.schema.json` — operationResult is generic over invoke action outputs;
  no envelope change, so **no REST/openapi or MCP motion** (A13: the one core contract
  absorbs this without transport edits)
- `otdp-measurement.schema.json` — structurally unchanged (§3.4)
- The existing `decode/1.0.0` action, its vectors, and every 0.2.2 example byte
- Gateway source (`src/benchweave/`) — zero lines; structural admission is
  schema-resolved per-pin, semantic mirrors are slice 2
- The in-tree plugin descriptors/locks — they stay 0.2.2-pinned and remain admissible
  (per-pin admission, R-2); no re-stamping is required (contrast the 0.2.1-era
  `b99b47b4` stamping, which predates multi-version serving)

## 4. Version semantics and governance

**Class call: PATCH (0.2.2 → 0.2.3).** GOVERNANCE's table: "Additive machine errata
(backwards-compatible) → PATCH". Every motion is optional-additive — new optional
descriptor field, new optional action, new documents, prose extensions. **No
previously-valid document is refused**: a 0.2.3 descriptor without `decoders`
validates identically; a 0.2.2-pinned descriptor is admitted unchanged under per-pin
resolution; every existing dataset and vector stays valid. This is the same template
the 0.2.2 errata commit used to hold a tighten at PATCH (`a103a4cf`: "no admissible
document is refused → PATCH; the #64 MINOR precedent refused previously-valid
documents"). If review finds any input that 0.2.3 refuses and 0.2.2 admitted, the
class flips to MINOR — that is the falsifier, stated in advance.

The issue's "0.2.2 → 0.3.0 (additive MINOR)" suggestion reads the *significance* of
the surface, not the *class* of the change; GOVERNANCE classes mechanisms, and this
one is additive. (Owner may overrule for signalling reasons — fork F3, §13.)

**Copy-never-move:** 0.2.3 is a copy of 0.2.2 with edits only in the copy; 0.2.2's dir
and rows stay digest-frozen; new rows cite their 0.2.2 sources; the two new files'
rows cite the active-version sibling pattern per repin. Digests move only through
`benchweave.standards repin`.

**Window:** 0.2.2's directory was created 2026-09-22; the 24-hour window is long
clear. No OTDP dev head exists (only execution's `0.2.0-dev`, a different standard) —
the motion is a direct bump, not a promotion.

## 5. Minimal first increment — scope

One gateway PR, standards-side only:

1. `standards/otdp/0.2.3/` — full copy + version sweep + the §3 additions
   (`otdp-decoder.schema.json`, `protocol-decoders.md`, catalog action, descriptor
   `decoders` field, measurement-model §6 event_log annotation bullet, device-classes
   §7 extension, extension-contract cross-reference)
2. `examples/decoder-i2c.json`, `examples/decoder-spi.json`, `examples/decoder-uart.json`
   — declaration documents extracted from the real PDs (public shapes; hygiene: no
   licence headers copied, structure only) — plus `examples/decoder-onewire-link.json`,
   the genericity control from outside the extraction set
3. `examples/class-action-vectors.json` — `decode_annotated` vectors derived from the
   real `put()` payload shapes documented in the PD docstrings
4. `scripts/architecture/check_devices.py` — PD-check arms + mutation rows;
   validation-report regeneration into 0.2.3 (obligation 13; the report writer refuses
   on any failing check)
5. Manifests in-arc: `standards-manifest.json` (otdp@0.2.3, supersedes, normative
   paths + the four new example files and two new corpus files),
   `corpus-manifest.json` (identity.otdp + rows via repin), bundle re-export
6. Docs in-arc sweeps (obligation 18): the baseline lines (device-developer-guide,
   ai-device-reviewer, development.md, architecture v1.5 §21) via
   `--refresh-docs-baseline` (diff = review surface), `docs/project-index.md`
   standards-links, `docs/README.md` report rows; the device-developer-guide gains a
   decoder-declaration section (obligation 3 — plugin-visible behaviour)
7. Tests: corpus regression arms in `tests/contract/` (declaration schema vectors,
   mutation rows, per-pin sweep) — RED commit first, the `5af97935` shape

## 6. Deferrals (each with home + reopen trigger)

| # | Deferral | Home | Reopen trigger (observable) |
|---|---|---|---|
| D1 | **Binary outputs** (surface 4): declaration classes are shape-validated, emission absent | `protocol-decoders.md` PD6 | A plugin authors a decode action whose contract requests decoded byte-stream export beyond the trio's `payload_hex` — an admission/design request naming binary arrives on the tracker |
| D2 | **Decoder stacking** (surface 5): no `inputs`/`outputs`, no inter-decoder PYTHON-payload dataset form | `protocol-decoders.md` (scope statement) | A stacked-decode need is filed (the memory-over-i2c-class case) — a tracker issue naming two decoders where one consumes the other's output |
| D3 | **Tick-exact integer sample coordinates** (variables `start_sample`/`end_sample` uint64) | measurement-model.md §6 annotation bullet | A renderer or decoder demonstrates misplacement at legal catalog bounds (sample_count ≤ 1e6 with rates where float64 seconds lose the sample period) — a filed repro with the arithmetic |
| D4 | **Multi-text zoom fidelity** (shortest-text variants per record) | same bullet | A UI contract row requires zoom-dependent short labels — the ui-contract table gains the row |
| D5 | **META numeric outputs** (decoder-emitted bitrate-class measurements) | `protocol-decoders.md` scope | A consumer requests decoder-emitted numeric measurements as data (not context) — tracker issue naming the consumer |
| D6 | **Gateway semantic mirrors** (admission-seam PD-checks in `control/documents.py`, the #63/#147 pattern) | this record §3.2 | The first 0.2.3-pinned descriptor carrying `decoders` is presented to gateway admission — the arrival itself |
| D7 | **SDK leg** (vendoring/lock sync, SDK release cut, gateway pointer PR — the #408 order) | this record §12 | Slice 1 merges — the merge event |
| D8 | **Generic renderer leg** (gateway UI drawing annotation logs from declarations) | the UI contract surface (`docs/internal/ui-contract.md` family) | Slice 1 + the real device plugin's decode action both land — both merges exist |

## 7. Precedent citations

- **The named-extension precedent (primary):** the 0.2.1 transport-provider lane —
  `340fda2d` (mechanism: the optional descriptor object embedding the root contracts
  triple verbatim), `7946dd9a` (prose: `transport-providers.md` +
  `otdp-transport-provider.schema.json`), `5af97935` (RED first). This design is the
  same shape one more time: pinned document family + optional descriptor reference +
  admission rules, with the commissioning asymmetry recorded (§3.2).
- **The dataset precedent:** the existing decode action's event_log —
  `device-classes.md` §7, the `class-action-vectors.json` worked example, quantities
  `protocol_payload`/`protocol_status` sanctioning invented quantities for string
  columns (measurement-model.md §4: "A profile may introduce another explicit
  quantity/unit pair").
- **The bump-class precedent:** `a103a4cf`'s refused-none template; `05354b4b`'s
  full PATCH in-arc sweep checklist (version sweep, examples re-pin fixpoint,
  manifests, export, report, docs rows).
- **The corpus's own pointers:** device-classes.md §7 "named extension";
  measurement-model.md §6 "decoder fields"; M13.
- **The consumer:** a real device plugin, OTDP 0.2.2-pinned, carrying
  `otdp.logic_analyser/1.0.0` with configure/arm/fetch/abort and 34 digital channels —
  and **no decode action**: today it has nowhere to emit decoder output, and its
  pinned `contracts` array (vendor profile + vendored measurement schema) is the
  triple shape in live use.

## 8. Invariant impacts (A01–A14 walk)

- **A02 (qualified, not assumed):** decoder options are interpretive parameters over
  retained evidence — no energisation path, so no commissioned numeric envelope
  applies; the acquisition itself stays bounded by the catalog's existing
  `sample_count`/byte backstops. Recorded in `protocol-decoders.md` so the asymmetry
  is a decision, not a gap.
- **A04 (protection independent of AI):** untouched — no protective transition, lease
  or deadline changes; decode is post-acquisition. Rendering may be AI-driven; the
  contract itself is machine-checkable (PD1–PD6), so correctness never rests on
  judgement.
- **A05 (bounded procedures):** `decode_annotated` is an ordinary invoke action under
  operation policy (timeout, side_effect none, retry idempotent); procedures reference
  it like any action; no envelope rewriting.
- **A06 (evidence over assertion):** annotation datasets are evidence — digest-pinned
  artifacts where artifact-backed, M-checks enforced, decoder failure degrades in-band
  (`partial`/`invalid` with reasons), never fabricated rows.
- **A10 (bounded classes):** an optional action on an existing profile; not a new
  family; the catalog revision is reviewed by the ordinary train gates.
- **A12 (bounded procedures):** unchanged.
- **A13 (one core contract):** the surface lands in the one corpus; REST/MCP need no
  motion (§3.6) — the strongest signal this is the right attachment point.
- **A14:** nothing.
- **CTL/STO/REG:** untouched — no control, state or registry code moves.
- **CON:** no invariant gains an amendment in this slice. CON-2 (fixture lattice) and
  CON-11 (report regen) move mechanically; CON-1's per-pin resolution is what makes
  zero gateway code possible (cited, not changed). **No new invariant is needed**: the
  declaration-resolution rule (class values resolve against the pinned declaration)
  is a corpus conformance check (PD5), carried by the census and the SDK checker —
  the derived_variables precedent (S19/M15 as corpus checks, not invariants) is the
  model. If slice 2 lands gateway admission mirrors, CON-10's amendment style is the
  carrier then.

## 9. Measurable proof — pre-committed acceptance rule

**Metrics (all fixed before any number is looked at):**

- **M-A Expressiveness:** 3/3 extraction declarations (i2c, spi, uart — from the real
  PD class surfaces) validate against `otdp-decoder.schema.json` and pass PD1–PD2,
  PD6. Sample: the three named decoders, no substitution.
- **M-B Genericity (the control):** the fourth declaration (onewire_link — outside
  the extraction set, different family) validates clean with zero schema motion.
- **M-C Record fidelity, before/after:** vector fixtures derived from the real
  documented `put()` payload shapes map to schema-valid annotation event_logs with
  100% `class` resolution. The **before** side is the RED control: the same records
  under 0.2.2's decode variable set — `payload_hex` carries only byte-bearing events
  and **no class identity exists**, so a generic renderer can identify 0 of the
  declared classes and draw 0 rows; under 0.2.3 the same renderer identifies every
  class and draws every declared row from the declaration alone (i2c 11 classes/3
  rows, spi 7/7, uart 18/10 — 36 classes, 20 rows across the three, plus the control
  decoder's own).
- **M-D No-regression:** the devices suite census green with the new arms; every
  0.2.2 example byte unchanged; a 0.2.2-pinned descriptor and a 0.2.3 descriptor both
  validate per-pin.

**SHIP if** M-A, M-B, M-D all hold and M-C shows class resolvability 0 → all-declared
with the variable set exactly as designed.

**KILL if** any extraction declaration requires a per-decoder schema exception
(M-A contortion), the control decoder fails (M-B — trio shape leaked into the schema),
records cannot carry class identity without variable-model changes (M-C structural
failure), or any 0.2.2-valid document is refused (M-D regression — also flips the bump
class per §4).

**UNDERPOWERED if** the extraction set turns out structurally homogeneous (all
two-channel, all-string-options decoders) — M-B on one control cannot then certify
genericity; the widening obligation is named: extend the extraction set to decoders
exercising distinct declaration shapes before judging. (The three candidates already
span 0/1/2 required channels, free-numeric and float-valued options, and 7–18 classes,
so the underpowered outcome would itself be a finding about the corpus, not the
extraction.)

## 10. Top risks, each with its falsifier

1. **The trio's shadow** — the declaration schema accidentally encodes i2c/spi/uart
   shapes. Falsified by M-B failing; guarded by the control decoder and the
   extraction's deliberate shape spread.
2. **Text determinism** — records carry pre-rendered text produced by plugin code;
   a decoder rendering locale- or version-dependent text puts non-deterministic bytes
   in evidence. Mitigation: vectors pin exact text; PD5 could grow a determinism note;
   falsified if vector re-runs disagree.
3. **Variable-set ambiguity** — two event_log decode forms (byte-form vs
   annotation-form) under one kind. Mitigated by scoping the variable set per action
   in device-classes §7 prose + PD5; falsified if a mixed-form dataset validates.
4. **Train-surface cost** — the in-arc sweep is wide (obligations 6/8/13/18/20/21);
   a missed surface reds late. Mitigated by the 0.2.2 checklist as the literal
   template; the governor + tripwires are the net.
5. **SDK same-version trap** (obligation 15) — a corpus edit after an SDK sync cannot
   re-vendor same-version. Mitigated by train order (§12); falsified only by order
   violation.
6. **Class-ID translation drift** — extracting positional-index rows to id-referenced
   rows is mechanical but hand-done; a wrong row mapping renders truthfully wrong
   groupings. Mitigated by vectors pinning row membership; falsified by a vector
   mismatch against the PD source.

## 11. Review tier and the Step-1 keyword scan

**Tier 3**, path rule: the build diff touches `standards/` and adds JSON Schema files.
The standards-governor pass is mandatory. Two-lane adversarial refute applies (the
standing Tier-3 doctrine).

**Keyword scan (the eight Step-1 words) over the expected diffs:**

- *This record's commit (the only diff this pass commits — the record file itself;
  word-boundary counts over the final committed text, which this section is part of —
  stating counts changes them, so these are the fixed-point numbers):* `threading` 2,
  `asyncio` 2, `subprocess` 2, `sha256` 6, `hashlib` 2,
  `migrate` 2, `recovery` 2, `protection` 4. Most of these
  hits are this section and the build-diff bullet naming the keywords themselves (the
  rubric's intended self-fire); the substantive hits elsewhere in the record are
  `sha256` in the mechanism text (the example triple and its pin sentence) and
  `protection` once in the invariant walk. The tier is 3 by the path rule regardless;
  the keyword hits ride along as disclosed.
- *The expected slice-1 build diff (0.2.3 corpus + catalog + examples + validator +
  tests + manifest/docs sweeps):* `sha256` ≈ 15–30 (schema patterns, descriptor
  example, repin-touched manifest rows, test digest arms, commit-message conventions),
  `hashlib` ≈ 2–4 (test digest computations), `threading`/`asyncio`/`subprocess`/
  `migrate`/`recovery`/`protection` ≈ 0 each (no code, no migration — per-pin
  admission means nothing migrates). The build lane re-runs the scan over the real
  diff and reports actual counts; the tier cannot drop below 3 either way.

## 12. Train shape

**Slice 1 — this PR (gateway repo, `feat/issue443-decoder-output-contract` → one PR
against main, linked to issue #443):**

1. `docs(design)` — this record (first commit; the pre-commitment ordering)
2. `test(standards)` — RED: PD-check arms + mutation rows against the pre-mechanism
   tree (`5af97935` shape)
3. `feat(standards)` — OTDP 0.2.3: copy + sweep + mechanism (schema, prose, catalog,
   descriptor field, examples, vectors) + manifests in-arc + repin + export + report
   regen + docs sweeps
4. Fold waves as review requires (batched per the one-bump-per-train rule; anything
   queued mid-train batches into 0.2.3 or waits for the next window per GOVERNANCE)

Reviews before open: resident code-reviewer (Tier 3 protocol) + standards-governor
(mandatory) + two independent adversarial lanes (Tier-3 doctrine). Merge on the full
rollup.

**Follow-on train (named, ordered per the #408 rule — not part of this slice):**

5. SDK repo: `make sync-sdk-standards`-driven sync (lock + vendored tree at 0.2.3),
   SDK PR → merge → SDK release cut
6. Gateway: the pointer PR (gitlink + `.gitmodules` pin in the same commit, the
   sdk-drift pairing rule)

The 0.2.2 landing proves the gateway-first shape stays green between steps 4 and 6
(`05354b4b` landed 2026-09-22; the 0.2.2 vendor pointer advanced later via SDK PR
#47's train). The build lane verifies `make check-sdk-standards` immediately after
the export in step 3 — that is the one empirical check this ordering relies on.

## 13. Forks needing the owner's word

- **F1 — action naming:** new optional `decode_annotated/1.0.0` (recommended — leaves
  the shipped trio path untouched) vs revising `decode` to 2.0.0 with a widened input
  (one action, but deprecates a shipped surface and complicates the vectors).
- **F2 — row referencing:** class **ids** (recommended — corpus convention, stable
  under declaration edits) vs sigrok's positional indexes (cheaper shim translation,
  fragile under class insertion).
- **F3 — bump class:** PATCH per the refused-none template (recommended) vs MINOR
  0.3.0 for signalling a new sub-capability (the issue's phrasing leans this way;
  GOVERNANCE classes it additive either way — an owner signalling preference is a
  legitimate override to record in the PR body).
- **F4 — declaration admission weight:** digest+schema+semantic only (recommended,
  §3.2's reasoning) vs provider-parity operator admission (heavier; would make
  decoder declarations commissioning-class acts with no transport authority to
  justify it).
