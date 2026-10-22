# OTDP protocol decoders 0.2.4

**Status:** Declarative decoder surface for the logic-analyser profile; declaration admission is offline, rendering is any consumer's  
**Companions:** `otdp-decoder.schema.json`, `device-classes.md` (§7), `measurement-model.md` (§6), `extension-contract.md` (§1, §6), `examples/decoder-i2c.json`, `examples/decoder-spi.json`, `examples/decoder-uart.json`, `examples/decoder-onewire-link.json`

## 1. What a decoder declaration is

A **decoder declaration** is a JSON document validated by `otdp-decoder.schema.json`
(`urn:otdp:decoder:0.2.4`). It names a protocol decoder's interpretive surface — the
channels it reads, the options that steer its interpretation, the annotation classes it
emits, and the rows a renderer groups those classes into — so a generic consumer can
draw decoded output without any decoder-specific code. The schema is structure only:
it grants no authority, and it gates no physical access.

The declaration's `version` is the declaration's own version, not a corpus version.
Dataset context records decoder identity as `<id>/<version>` (for example
`i2c/1.0.0`), exactly the shape the closed-trio decode action's vectors already used
for `reference-uart/1.0.0`. A declaration revision that changes class ids, row
membership or option meaning is a version bump of the declaration; digests move only
through a new pin, never by editing pinned bytes.

`annotation_rows` reference classes **by id**, never by positional index. Positional
indexes are an artifact of the Python decoder interface this surface was extracted
from; ids stay stable under class insertion, and the corpus convention (channels,
parameters, line roles) is snake_case ids throughout. Translating a positional row
from such a decoder is mechanical: index *i* resolves to `annotations[i].id`.

`options` carry a required `default` whose JSON type is one of string, number or
boolean. `values`, when present, is an array every one of whose items matches the
default's type — both free-numeric options (no `values`) and enumerated float options
are representable, because real decoder surfaces need both. The declaration's own
`channels` may be empty: a decoder that reads whichever optional lines are supplied
declares no required channels, and every required channel must be mapped at the
action boundary (§3).

`binary` classes are declared for surface honesty — a declaration states what its
decoder can emit — but **emission is out of scope in 0.2.4** (PD6). Nothing consumes
the field beyond shape validation; the named reopen trigger is a decode request that
needs byte-stream export beyond the closed trio's `payload_hex`.

## 2. Declaring one

A descriptor may carry an optional root `decoders` array:

```json
"decoders": [
  {
    "id": "i2c",
    "path": "decoder-i2c.json",
    "sha256": "<64-hex digest of the pinned bytes>"
  }
]
```

`{id, path, sha256}` is the contract-reference shape `extension-contract.md` §1 states
for the root `contracts` array, verbatim. The path resolves relative to the declaring
descriptor's own package (the same descriptor-relative rule the transport-provider
object's pin follows), must remain inside the admitted bundle after symlink
resolution, and cannot name a URL or executable module. The descriptor's own digest
pin covers the reference; admission verifies the declaration's bytes against its
`sha256` — the CON-1 family discipline, applied to interpretive documents.

**Admission posture — deliberately lighter than transport providers, a recorded
asymmetry.** A transport-provider contract is an operator-admitted commissioning-class
act because transport authority flows through it. A decoder declaration gates no
physical access: the only action that consumes it is `side_effect: none` over a
**completed, retained** acquisition — the existing decode action's own posture. A
descriptor's decoder declarations are therefore admitted by digest pinning, schema
validation and the PD1–PD6 semantic checks below, with **no operator commissioning
step**. If a future decoder-consuming action gains a side effect, this posture is the
row to re-derive, not silently inherit.

Decoder admission resolves the schema by the descriptor's own `otdp_version` pin, so a
0.2.4-pinned descriptor carrying `decoders` is structurally admissible the moment this
corpus lands; 0.2.2-pinned descriptors are untouched and remain admissible per-pin.
The gateway-side semantic mirrors (pin verification, channel_map resolution and option
validation at the admission seam) are the named slice-2 follow-on on the issue this
revision ships for — the corpus rules below are the authority those mirrors implement.

## 3. The action

`otdp.logic_analyser.decode_annotated/1.0.0` is an optional action on the
logic-analyser profile. Input:

- `acquisition_id` (string) — the completed retained acquisition, the same posture as
  the closed-trio decode action; it does not re-acquire.
- `decoder` (string, snake_case) — must name an `id` in the declaring descriptor's
  `decoders` array (PD3).
- `channel_map` (object, decoder channel id → device channel id) — generalises the
  trio's `line_map`: every **required** declaration channel must be mapped, every
  mapped target must exist in the descriptor's `channels` (the C04 rule), and
  unmapped **optional** channels are legal — the decoder reads them as absent.
- `options` (object) — free-form at the catalog surface and validated **semantically**
  against the declaration's option specs: keys must exist, values must carry the
  declared JSON type, and values must appear in `values` where the spec declares them
  (PD4). The specs are declaration data, not catalog bytes.

Output is a dataset `$ref` to the measurement schema's dataset definition, in the
annotation event_log form (§4). The action is `side_effect: none`, `lifecycle:
direct`, and a declaring descriptor marks it `retry: idempotent` — a deterministic
reinterpretation of retained evidence. The existing `decode/1.0.0` is untouched: the
closed trio remains the zero-declaration path, this action is the declared-decoder
path, and no previously-valid binding is refused.

Decoder options are interpretive parameters over retained evidence: no energisation
path exists, so no commissioned numeric envelope applies (decision A02's posture for
post-acquisition interpretation). The acquisition itself stays bounded by the
catalog's existing sample-count and byte backstops.

## 4. The dataset form — annotation event_log

The output dataset is an `event_log` in the **annotation form**: an event-index axis
(quantity `index`/1, regular, 0..N−1) and variables, all dimensions `["event"]`:

- `start_s`, `end_s` — `float64`, `time`/`s`, capture-clock referenced (the closed
  trio's own representation; sample-exact integer coordinates are a named deferral
  with the arithmetic that shows float64 seconds keep the sample period at the
  catalog's bounds).
- `class` — `string`, quantity `annotation_class`/1 — every value must resolve to an
  annotation id of the named decoder's declaration (PD5).
- `text` — `string`, quantity `annotation_text`/1 — the record's primary pre-rendered
  text: the longest variant the decoder's own annotation table offers. Multi-text
  zoom fidelity (shortest variants per record) is a named deferral; the declaration's
  class labels are the generic fallback label.

`context` carries `decoder_id` (`"<id>/<version>"`), the effective options and the
channel_map — decoder identity, settings and binding are recorded, the same
obligation the closed trio's section states. Decoder failure degrades in-band: the
dataset's `status` becomes `partial` with `status_reason` carrying the reason(s), and
records that could not be decoded are omitted, never fabricated (A06's quality-loss
posture — the dataset status vocabulary is the schema's existing
complete/partial pair).

The renderer's row grouping comes from the **declaration** (`annotation_rows`), not
from the dataset. That is the point of the surface: a generic renderer reads one
pinned declaration and one generic dataset form, and needs zero decoder-specific
code. The byte form (the trio's `payload_hex`/`status` variable set) and this
annotation form are scoped per action in `device-classes.md` §7 — a dataset carries
one form, named by the action that produced it; a mixed-form dataset is a PD5
refusal.

## 5. The PD-checks

Semantic, enforced by the corpus census and (in slice 2) by the gateway admission
seam:

| ID | Check |
|---|---|
| PD1 | Declaration documents are digest-pinned, package-relative and schema-valid; decoder ids are unique across the descriptor's `decoders` array |
| PD2 | `annotation_rows.annotation_ids` resolve in `annotations`; no annotation id appears in two rows |
| PD3 | `decode_annotated.decoder` names a declared decoder; `channel_map` covers every required channel; mapped targets exist in the descriptor's `channels` |
| PD4 | `options` keys exist in the declaration; values carry the declared type; values appear in `values` when the spec declares them |
| PD5 | Output dataset: kind `event_log`, the annotation variable set present, every `class` value resolves against the declaration, `start_s ≤ end_s`, event-axis length equals the variable lengths (M02's shape) |
| PD6 | Declaration binary classes are shape-valid but unconsumed — binary emission is out of scope in 0.2.4 |

## 6. Scope and named deferrals

In scope for this revision: declaration documents, descriptor pins, the
`decode_annotated` action, the annotation event_log form, and the checks above. Out
of scope, each with its reopen trigger on the owning issue: binary outputs (PD6),
decoder stacking (no `inputs`/`outputs` fields exist — a stacked-decode filing opens
it), sample-exact integer coordinates, multi-text zoom fidelity, decoder-emitted
numeric measurements, and the gateway admission mirrors (slice 2, on the first
0.2.4-pinned descriptor carrying `decoders` that is presented to gateway admission).

## 7. The offline boundary and provenance

Offline checks prove a declaration **well-formed and self-consistent**: the schema
shape, the row resolution, the pin resolving inside the package to bytes that hash to
`sha256`, and the vectors' class values resolving per-pin. Only a consuming host
proves the **render**: that decoded output actually matches the declaration's
classes for a given acquisition. The corpus examples' class surfaces are extracted
from the public sigrok decoder corpus (i2c, spi, uart — the extraction set — plus
onewire_link as the genericity control from outside it); structure only, no licence
text, and the declarations carry the extracted facts, not the source project's
implementation.
