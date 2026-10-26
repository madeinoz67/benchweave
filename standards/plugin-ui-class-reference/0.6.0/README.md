# plugin-ui-class-reference 0.5.0

One reference presentation per device class, written as **data** in this
standards family. One class reference is the single source for three
consumers: the pattern-library class page, an SDK expander that turns a
class-conformant descriptor into a normal plugin-ui 0.4.0 manifest set, and
an SDK gate that renders the result through the real preview host and
compares the rendered component inventory against the reference's `expect`
block. The gateway application is untouched.

Design records: `.claude/deep-review/2026-10-14-classref-logic-analyser-design.md`
(the founding program),
`.claude/deep-review/2026-10-16-classref-l5-plugin-ui-0-4-0-design.md` (the
0.2.0 MINOR),
`.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md` (this bump —
the L11 `dc_psu` class, gateway issue #463) and
`.claude/deep-review/2026-10-20-classref-composition-gate-design.md` (the
cross-class composition gate, gateway issue #500).
`.claude/deep-review/2026-10-22-issue541-classref-composition.md` (the
three-layer action resolution — the 0.4.0 program),
`.claude/deep-review/2026-10-22-issue541-s2-standards-design.md` (the 0.4.0
bump) and `.claude/deep-review/2026-10-25-issue556-track-b-vocabularies.md`
(the composed-member mechanism — this bump).

## From-predecessor note (0.4.0 → 0.5.0, MINOR)

One new schema plus the re-stamp; nothing existing widens. The new
`composed-member-declaration.schema.json` defines the layer-2 document of the
composed-member mechanism (gateway #556 track B): a vendor-authored
declaration that supplies the reference side — one slot per member, its page
placement, and optionally one vendor profile row — for a device whose class
reference covers only part of what the device declares (see the normative
section below). Every closed set in it is lifted from an owner that already
ships it, so this bump introduces no new vocabulary: the member kinds,
channels fields and action fields are this directory's own
`class-reference.schema.json` `$defs.slot`; the plot block is its
`page_template.plot` block verbatim, per-kind conditionals included; the
claim pattern is `composed-action-class.schema.json` `$defs.claimed_action_urn`;
the optional vendor profile row is
`standards/otdp/0.2.4/device-profile-catalog.schema.json`
`properties.profiles.items` verbatim. Its documents carry their OWN dialect
version (`contract_version` const `0.1.0`), decoupled from this directory's
version on the composed-action-class precedent: a declaration is pinned by
digest in a descriptor's `contracts[]`, and a family bump must not invalidate
pinned bytes. The eight class files and the three family schemas re-stamp with
zero content change (exactly the `contract_version` line for a class file and
the version-bearing lines for a schema — the L5 shape).

Copy-never-move: 12 new corpus rows — the eleven re-stamps cite
`standards/plugin-ui-class-reference/0.4.0/*` as `source` (`README.md` is
prose and never a row), the new schema cites its authoring staging path
`docs/plugin-ui-class-reference-v4/composed-member-declaration.schema.json`
(the founding `source`-provenance convention; the staging tree was never
committed, and `source` is provenance, never required to resolve on disk);
digests moved only by `benchweave.standards repin`; the predecessor trees are
untouched and their 27 rows verified frozen by the same command. The served
range widens `>=0.1.0,<0.5.0` → `>=0.1.0,<0.6.0`; a NEW cross-constraints row
names 0.5.0 (floor unchanged — the composed-member schema consumes no
plugin-ui vocabulary beyond what the family already requires).

## From-predecessor note (0.3.0 → 0.4.0, MINOR)

One new schema plus the re-stamp; nothing existing widens. The new
`composed-action-class.schema.json` defines the layer-2 document of the
three-layer action resolution (gateway #541): a vendor-authored action class
claiming action URNs no served catalog describes and supplying the catalogue
side of the D13 intersection (see the normative section below). Its
documents carry their OWN dialect version (`contract_version` const
`0.1.0`), decoupled from this directory's version on purpose: a composed
class is pinned by digest in a descriptor's `contracts[]`, and a family bump
must not invalidate pinned bytes (the descriptor/`otdp_version` precedent).
The eight class files and the two family schemas re-stamp with zero content
change (exactly the `contract_version` line — the L5 shape).

Copy-never-move: 11 new corpus rows — the ten re-stamps cite
`standards/plugin-ui-class-reference/0.3.0/*` as `source` (`README.md` is
prose and never a row), the new schema cites its authoring staging path
`docs/plugin-ui-class-reference-v3/composed-action-class.schema.json`
(the founding `source`-provenance convention; the staging tree was never
committed, and `source` is provenance, never required to resolve on disk); digests moved
only by `benchweave.standards repin`; the predecessor trees are untouched
and their 16 rows verified frozen by the same command. The served range
widens `>=0.1.0,<0.4.0` → `>=0.1.0,<0.5.0`; a NEW cross-constraints row
names 0.4.0 (floor unchanged — the composed schema consumes no plugin-ui
vocabulary beyond what 0.3.0 already requires).

## From-predecessor note (0.2.0 → 0.3.0, MINOR)

One vocabulary widening plus the second class file; everything else the
re-stamp. `page_template.plot.kind` widens from the `digital_lanes` const
to the enum `["digital_lanes", "time_series"]` with per-kind conditionals:
`digital_lanes` keeps its group machinery exactly as it was (group_size 8,
label pattern `D{first}-D{last}`, radix hex/decimal — and may not carry
`series`), `time_series` requires the one structural field
`series: "numeric_variables"` (the closed derivation rule: every numeric
scalar variable of the over-slot's dataset becomes a series) and may not
carry the group machinery. `waveform` was NOT admitted in the L11 slice
(the oscilloscope class widens on its own evidence) and the L13
oscilloscope class landed it in the same unreleased window (see the L13
note below). The founding reference re-stamps with zero content change
(exactly the `contract_version` line — the L5 shape).

The new `class-dc_psu.json` is the first scalar/readings-shaped class: the
`otdp.dc_psu/1.0.0` profile with `source`-role output channels, a
`measure` dataset (one numeric variable per channel and declared
quantity), preset-mediated `configure`, and the `output` energy toggle as
a declared deviation at birth — the directional §C.1 presentation
(energise stages then confirms; de-energise is one ungated action) is
beyond the per-action control vocabulary, and renderer enforcement belongs
to the safety-behaviours slice. The expansion-side arms (dataset
variables by shape, observation bindings on readings pages, plot
emission, reading layout nodes, the widened expect inventory and census)
are the SDK widening's work and ride that train; this corpus lands the
vocabulary and the reference first.

Copy-never-move: 4 new corpus rows — the three re-stamps cite
`standards/plugin-ui-class-reference/0.2.0/*` as `source`, the new class
file cites its authoring staging path
`docs/plugin-ui-class-reference-v2/class-dc_psu.json` (removed in the
same pull request — the founding convention); digests moved only by
`benchweave.standards repin`; the predecessor trees are untouched and
their rows verified frozen by the same command. The served range widens
`>=0.1.0,<0.3.0` → `>=0.1.0,<0.4.0` (multi-serving; the
cross-constraints row amends in place with the floor unchanged — the
widening consumes vocabulary plugin-ui 0.4.0 already ships — evidence
re-cited to this bump's design record).

## L13 note (in-window: the `waveform` widening + the oscilloscope class)

The 0.3.0 window was still open when the L13 class landed (the batch's
promotion leg unbuilt), so the one vocabulary motion joined the same
bump: `page_template.plot.kind` admits `waveform`, with a conditional
mirroring `time_series` (`series: "numeric_variables"` required, the
group machinery banned). The semantic difference from `time_series`
lives in the DATASET kind at expansion — the waveform dataset's trace
variables are array-valued numeric variables (one per channel and
declared quantity) over an explicit time axis — never in a new series
rule. The `class-oscilloscope.json` reference rides the same bump, its
row citing the authoring staging path
`docs/plugin-ui-class-reference-v2/class-oscilloscope.json` (removed in
the same pull request — the founding convention).

## L14 note (in-window: the `function_generator` class, nothing widened)

The 0.3.0 window was still open when the `function_generator` class
landed (the batch's promotion leg unbuilt), so the fifth class file
joined the same bump with ZERO vocabulary motion — no schema byte, no
count expression beyond the closure the 0.2.0 bump already carried, no
layout block, no numeric literal. The profile is measurement-free
(required `configure` + `output`, optional `upload`, `source` channels
only), so the reference owns TWO pages (Configuration, Device
features): no observation binds, no plot template names an over-slot,
and an output-shaped third page would render panels and a mode-banner
around two REPORTED deviations — placement-by-anticipation, refused.
`upload` is the `when_declared` seam's second use and its first
non-lifecycle optional action. Its row cites the authoring staging
path `docs/plugin-ui-class-reference-v2/class-function_generator.json`
(removed in the same pull request — the founding convention).

## L15 note (in-window: the `electronic_load` class, nothing widened — not even a settlement)

The 0.3.0 window was still open when the `electronic_load` class landed,
so the sixth class file joined the same bump with ZERO vocabulary motion
— and unlike L11/L12/L13, which each carried a schema motion inside the
window, this slice moves NO family-schema byte at all: the load is
dc_psu's mirror (the same `configure`/`output`/`measure` action triple
over `sink`-role channels — `where_role` is a free string, so `"sink"`
widens nothing), its page is dc_psu's own composition over inverted-role
channels, and the class's one hard question is DIRECTIONAL, not
presentational: which side of ui-contract §C.1 the input-enable sits on.
The reference pins the ruling in data — `output` is a declared
`deviation` with the `input-control` cannot_derive row naming the
inversion (engage is the energy-admitting, flow-starting direction:
stage then confirm naming effect, values and target; disengage is the
one ungated action, R-DEENERGISE-1), `forbid` carries
`intermediated-energy-removing-action` with its second true home (the
never-intermediated action is the DISENGAGE — a bulk-energy flow-stop),
and the `output` slot marks the OTDP conditional (`configuration_id`
required iff `enabled: true`) structural via
`host_supplied: ["configuration_id"]`. Its row cites the authoring
staging path
`docs/plugin-ui-class-reference-v2/class-electronic_load.json` (removed
in the same pull request — the founding convention).

## L16 note (in-window: the `smu` class, nothing widened — and the sweep block DEFERRED BY NAME)

The 0.3.0 window was still open when the `smu` class landed, so the
seventh class file joined the same bump with ZERO vocabulary motion —
L12's zero-surface result, second application and stronger: not even a
settlement-class schema edit rides here, because the post-batch
vocabulary expresses the whole birth surface. The class is the PSU's
shape over a THIRD channel role (`source_measure` — `where_role` is a
free string, so the role widens nothing; the generic slot key
`channels` names a role that both sources and measures), its
required-three is dc_psu's action set verbatim, and its page is
dc_psu's own composition. The class's one hard question is the
profile's five-action SWEEP BLOCK (configure_sweep/arm/trigger/fetch/
abort), and it is deferred AS A UNIT with the deferral named in the
reference's own deviation ledger (`sweep-surfaces`): the fetch dataset
is `table`-kind — a derivation arm this train has designed nowhere;
the signature I-V presentation needs a plot kind whose x axis is a
measured variable, which plugin-ui 0.4.0 does not carry; and the
block's composition is procedure-owned by device-classes §10's own
sentence (completion and abort must execute the commissioned
source-safe transition). Until the sweep landing slice, the declared
sweep actions of a full descriptor surface via the Device features
page (the `vendor_actions` coverage home) — REPORTED, never silent —
and the sweep-absence arm in `tests/ui_html/test_classref_smu.py`
makes the absence a live assertion over the real expansion. Its row
cites the authoring staging path
`docs/plugin-ui-class-reference-v2/class-smu.json` (removed in the
same pull request — the founding convention).

## L17 note (in-window: the `daq` class, nothing widened — the sweep's first real consumer)

The 0.3.0 window was still open when the `daq` class landed, so the
eighth class file joined the same bump with ZERO vocabulary motion —
the cheapest member of the family: not even a settlement-class schema
edit rides here, because the batch's own widenings carry the whole
birth surface (the `waveform` plot kind is L13's; without it this
reference is schema-invalid — the batch-state dependency is
load-bearing, not decorative). The class is the oscilloscope's
action-identical sibling with a different substance: the lifecycle
quartet is structurally identical while `configure` differs materially
(per-channel quantity/unit/range plus the `sampling` mode, against the
scope's probe-scaled display semantics), and the family keeps TWO
classes because `profile_id` binds exactly one OTDP profile — a merged
document is not an expressible object. This is also the sweep's first
class with a real, shipped consumer: a public community plugin
declares `otdp.daq/1.0.0` with six analogue voltage channels and no
`ui/` manifest, so the L4 no-manifest fallback makes this reference
the plugin's served presentation the moment the batch lands; the
conformance claim is executable and lives in
`tests/ui_html/test_classref_daq.py` over a vendored byte-copy of the
public descriptor (source commit named in-file; no network in CI).
The class's honesty row is `calibration-context`: the real consumer
streams raw counts with calibration `not_applied`, and the class
presents the unit the dataset carries — `count`, never a nicer one —
until an upstream measurement-profiles layer exists. Its row cites
the authoring staging path
`docs/plugin-ui-class-reference-v2/class-daq.json` (removed in the
same pull request — the founding convention).

## Files

| File | What it is |
|---|---|
| `class-reference.schema.json` | The class-reference document schema: slots, page templates, expectations, declared gaps |
| `layout.schema.json` | The namespaced layout block vocabulary that rides the plugin-ui `extensions` seam under the key `plugin-ui-class-reference:layout` |
| `composed-action-class.schema.json` | The composed action-class declaration schema (dialect 0.1.0): layer-2 action classes, gateway #541 |
| `composed-member-declaration.schema.json` | The composed member-declaration schema (dialect 0.1.0): layer-2 member surfaces for the procedure, settings, dataset, channels and plot-kind vocabularies, gateway #556 |
| `class-logic_analyser.json` | The founding reference for the `otdp.logic_analyser/1.0.0` class |
| `class-dc_psu.json` | The reference for the `otdp.dc_psu/1.0.0` class (L11) |
| `class-dmm.json` | The reference for the `otdp.dmm/1.0.0` class (L12) |
| `class-oscilloscope.json` | The reference for the `otdp.oscilloscope/1.0.0` class (L13) |
| `class-function_generator.json` | The reference for the `otdp.function_generator/1.0.0` class (L14) |
| `class-electronic_load.json` | The reference for the `otdp.electronic_load/1.0.0` class (L15) |
| `class-smu.json` | The reference for the `otdp.smu/1.0.0` class (L16) |
| `class-daq.json` | The reference for the `otdp.daq/1.0.0` class (L17) |

## The structure rule (D2)

The reference authors **structure, not data**. It may name page ids and
titles, slot keys, binding ids, the group label pattern, section ids and
titles, and the layout spans. It may author only these structural numbers:
`group_size` 8, `plot_index` (a placement index), and layout spans (at most
12). It authors no values, units, thresholds, voltage or rate limits,
channel names, or parameter names. Every data item resolves at expansion
time from the descriptor and the OTDP action schemas. The schema carries no
data-bearing field: no `default`, no `value`, no `unit`, no numeric bound
fields. An author who reaches for a data field gets a schema refusal, not a
silently-carried value.

## Class reference documents

A reference document binds one OTDP profile (`profile_id`) and speaks the
plugin-ui vocabulary it targets (`targets.plugin_ui`, for example
`">=0.4.0"`).

**Slots** map roles to derivation inputs. A `channels` slot resolves an
ordered channel list from the descriptor's declared channels with the named
role. An action slot (`dataset`, `configuration`, `procedure`) binds an
OTDP action URN; `when_declared: true` marks an optional action — it binds
only when the descriptor declares that action. `host_supplied` names the
input fields the host owns (the OTDP acquisition lifecycle assigns
`acquisition_id` and the active `configuration_id` to host ownership) —
field names, never values (D2-clean). The `vendor_actions` slot is the D14
coverage hook: it covers every declared action URN that no named slot
claims.

**Pages** are page templates. `binding_slots` lists the slot keys a page
binds; optional-action slots bind only when the descriptor declares them.
A `binding_slots` entry that names no key in the reference's `slots`
refuses at expansion (`classref_unknown_slot:`). `vendor_features: true`
marks the page that hosts the Device-features section. The `plot` block
declares the page's plot: a `digital_lanes` plot over a dataset slot
(group of 8 with label pattern `D{first}-D{last}`, radix `hex` (default)
or `decimal`; labels are decimal positional always, the radix formats
rendered values, never labels), a `time_series` plot over a dataset slot
(the 0.3.0 widening; `series: "numeric_variables"` names the closed
derivation rule), or a `waveform` plot over a dataset slot (the L13
widening; the same `series` rule — the waveform dataset's trace
variables are array-valued numeric variables over an explicit time
axis; the group machinery is banned exactly as for `time_series`).

**Expect** declares the gate's assertions. `components` maps a component
name to a `count` — an integer or a closed expression (`{n_lanes}`,
`{n_groups}`, `{n_decoders}`, `{n_run_actions}`, `{n_configure_fields}`,
`{n_pages}`, the L11 counters `{n_source_channels}`, `{n_scalar_variables}`,
`{n_reading_tiles}`, the L13 counters `{n_analogue_channels}`,
`{n_trace_variables}`, integer literals, `+`); `attribute` maps a
`"name=value"` selector to a count expression; the selector set is closed:
the three `data-bw-lane-kind` selectors (channel, group, decoder) and
nothing else. `per_page` names a page id, or `*` for every page, or is
absent for a count pooled across the render. `controls` maps a class
action URN to its reachability level: `button` (L1, no required inputs
after host-owned fields), `staging` (L2, required inputs in {numeric,
text, enum, boolean}), `preset` (L3, configuration-shaped), `deviation`
(a declared deviation at the reference level). `forbid` names the gate's
closed check set: `confirm-wrapped-run-action` (D7 — the de-energising
action is one action, never confirmed), `color-role-hint-on-lane` (belt
over the manifest schema's own refusal), `untraceable-lane-label` (every
lane label traces to the descriptor or the group pattern),
`intermediated-energy-removing-action` (any intermediating control on an
energy-removing action).

## Composed action classes (normative, gateway issue #541)

A composed action class is a versioned JSON document validated by
`composed-action-class.schema.json` (dialect `0.1.0`). It exists so a plugin
whose device is mostly a class but carries vendor operations no served
catalog describes gets those operations derived — styled, gated,
provenance-labelled — with no refusal and no upstream request. It is layer 2
of the three-layer action resolution: **layer 2 is layer 1 with the catalogue
side supplied by the composed document.**

**What `claims` may name.** A claim is a versioned action key:
`^[A-Za-z0-9][A-Za-z0-9._:-]*/[0-9]+\.[0-9]+\.[0-9]+$`. This vocabulary is
deliberately at least as permissive at the naming seam as the two layers it
sits between — the OTDP descriptor puts no pattern on its action keys, and a
layer-1 pinned vendor catalog serves any key shape — so `com.vendor.op/1.0.0`,
`urn:otdp:acme:op/1.0.0` and `otdp.acme.op/1.0.0` all claim. A stricter
pattern here would have made the composed path unusable for exactly the
naming conventions found in the wild, and would have forced an already
shipped plugin to rename its descriptor actions. Class-action URNs in a
reference's `expect.controls` stay `otdp.`-namespaced: that set is the
family's own vocabulary, not a vendor's. (Owner ruling, 2026-10-23.) The D13 narrowing intersection, the
reachability ladder and the field-row derivation run unchanged; the plan row
carries `resolution: "composed"` and the class it resolved through.

**The document.** `urn` (`otdp.action.<name>/<version>`) names the class; the
name is globally unique by convention (a vendor prefixes its namespace, for
example `otdp.action.<namespace>_<name>`), and corpus promotion refuses a
class urn a served class already carries. `claims` names the action URNs the
class presents — explicit binding, never a name-derivation guess; one class
may claim many actions (that is what "composed" buys), at most 64, unique. A
claim naming an URN a served catalog row (OTDP or a pinned vendor catalog)
already describes, an URN another composed class claims, or a second pinned
document carrying one class urn refuses typed
(`classref_composed_claim_conflict`) — sort order never picks a winner.
`input_schema` is a JSON Schema object, carried loose exactly as the OTDP
catalog carries action input schemas: the closed field-row vocabulary lives
in the consuming derivation, not in this schema, so a vocabulary widening
never invalidates pinned documents. `side_effect` states the class's claim
about what its actions do, from the closed set below.

**No component key.** The declaration supplies `input_schema` and nothing
presentational. The ladder (`_ladder_level` and `_row_mode` in the SDK
expander) still decides which section E control renders and at what
reachability: a declaration that could assert "render this as a button" for
an action with required numeric inputs would silently drop those inputs. "A
component key from the fixed inventory" resolves to: the component inventory
is the existing one, applied by the existing rule. A `component` field is
refused by the schema (`additionalProperties: false`).

**The closed `side_effect` set.** `none` and `state_change` — the OTDP
action vocabulary verbatim (the device descriptor's action enum; the served
catalog's action rows carry the same field) — plus `energy_removing`, a
refinement of `state_change` that names the D7 class: the gate's
`confirm-wrapped-run-action`, `intermediated-energy-removing-action` and
deviation-downgrade (D7) arms protect an `energy_removing` claimed action
exactly as they protect the `abort` slug today — declared evidence replacing
the name-derivation guess. Against the descriptor's own per-action
`side_effect` declaration the class value obeys the S20 direction, applied
at the class layer: over-classification is legal, under-classification
refuses (`classref_composed_side_effect_under`) — a class may claim
`state_change` or `energy_removing` where the descriptor says `none`, says
`state_change` or says nothing, and must not claim `none` where the
descriptor says `state_change`.

**Two sources; one resolver in this version.** The plugin-package source
rides the existing `descriptor.contracts[]` pin seam: path plus sha256,
resolved descriptor-relative by the SDK (`_vendor_catalogs`) — there a
pinned document that is neither a vendor action catalog nor a
schema-valid composed class refuses typed. The gateway's admission-bytes
mirror (`_vendor_catalog_documents`) is deferred to the named follow-on:
this version's gateway still reads only vendor action catalogs, so a
composed pin's bytes are digest-verified yet contribute no actions —
`derive_attachment` keeps refusing `classref_unknown_action` for a
claimed action, and a gateway today refuses what the SDK resolves.
Corpus promotion is literally a file move from the plugin's declaration
directory into a corpus version directory — maintainer curation that
never blocks authoring.

**Versioning.** The document's `contract_version` is the dialect version
(`0.1.0`), not the family version: pinned vendor bytes survive family bumps
by construction. The project conformance ledger (`ui/class-reference.json`)
records each consumed class (the `composed_classes` rows, each carrying the
class urn and the family version it `validated_against`), and `migrate-ui`
re-stamps those stamps — never a class urn's own version, which is content —
refusing (`migrate_ui_composed_unresolved`) whenever a claimed class's pinned
bytes cannot be re-resolved and re-validated under the target version.

**The next bump must carry this line:** if the closed `side_effect` set
widens — `energy_admitting` is the expected candidate, admissible only when
a gate arm consumes it (the directional section C.1 rule belongs to the
safety-behaviours slice) — the bump carries the consuming arm and the SDK
cross-check in the same change, and its cross-constraints row re-cites the
evidence. A value with no consumer is not admissible.

## Composed member declarations (normative, gateway issue #556)

A composed member declaration is a versioned JSON document validated by
`composed-member-declaration.schema.json` (dialect `0.1.0`). It exists so a
plugin whose device is mostly a class, but additionally binds procedures,
settings surfaces, capture datasets or channel lanes the served reference does
not place, gets those surfaces derived from its own declaration — with no
refusal and no upstream request. It is **layer 2** in the action pattern's own
sense: it supplies the reference side (slots and placement) that the served
corpus does not, and the existing derivation arms run unchanged on the injected
rows. No new component, page, plot kind or node kind is introduced: the
component inventory is the existing one, applied by the existing rule.

**What the document states — two things.** `contract_version` is the document's
dialect version (`0.1.0`), decoupled from this directory's version so a pinned,
digest-verified document survives family bumps (the composed-action-class
precedent). `members` is the declaration proper: at least one, at most 64 —
the reference's own `slots` ceiling (`maxProperties: 64`), since every member
injects one slot.
Optionally, `profiles` states ONE vendor profile row — an array of exactly
one row (`minItems: 1`, `maxItems: 1`), each row `id`, `title`,
`channel_roles`, `required_actions`, `optional_actions` — in the
device-profile-catalog's own row shape verbatim, under the PLURAL `profiles`
key because that is the spelling the canonical validator's profile map reads
(`documents[*].profiles`); the descriptor makes the profile claimable by
listing its id in its namespace-open `profiles[]`, which is
what lets a composed target resolve under the canonical validator's existing
profile rule rather than a widened one. A declaration is therefore both
schema-valid and validator-readable at once — a singular `profile` object is
refused by this schema (a key no reader owns), and the seam is proven by an
arm that drives a schema-valid declaration through the real validator to a
resolved vendor target with zero target findings.

**What a member states.** `slot` is the slot key the member injects;
`kind` is one of the four values this directory's `$defs.slot` already closes —
`channels` (the channels branch) and `dataset`, `configuration`, `procedure`
(the action branch's enum); `page` names an EXISTING page of the reference the
declaration composes with. The rest of a member is the reference's own slot
vocabulary, unchanged:

- **`channels`** carries the channels branch's `where_role`, and its `key`
  (`const "id"`) and `label` (`const "label"`) structural markers. A channels
  member places lanes in a named page's plot; it claims no action.
- **`dataset`, `configuration`, `procedure`** carry `claims` — one or more
  versioned action keys, validated by the composed action class's own
  `$defs.claimed_action_urn` pattern, so the naming seam is exactly as permissive
  as the pin seam the two document kinds share. A member carries no singular
  `action` field: a claim set is the member's vocabulary, and the reference
  slot's singular `action` is not silently inherited. `when_declared`,
  `schema_source` and `host_supplied` are the action branch's fields verbatim,
  with their own closed sets and bounds.
- **`dataset`** may additionally carry `plot`, the `page_template.plot` block
  verbatim: a `digital_lanes`, `time_series` or `waveform` plot with the same
  per-kind conditionals (the group machinery on `digital_lanes` alone; the
  `series: "numeric_variables"` rule required on the two analog kinds and
  banned on lanes). `plot.over_slot` names the member's own slot key — a
  mismatch is the document referring to itself inconsistently and refuses
  typed `classref_composed_plot_slot_mismatch` (rule 2 below). The plot
  field belongs to a dataset member and to no other kind — a configuration or
  procedure member carrying one is refused by the schema. A fourth plot kind is
  a dual-family standards motion (this family plus plugin-ui, whose consuming
  render arms the project does not ship), not a member field. One placement
  outcome is disclosed, not refused: a `plot` on a page whose class template
  already hosts a plot is admissible (the declaration contradicts nothing the
  schema can see), and the page keeps the class's plot — the member's plot
  derives nothing and every run REPORTS it: `composed plot <slot>: page <page>
  already hosts a plot (the page keeps the class's plot)`. A refusal is for a
  declaration conflict; a placement limit the declaration cannot see is a
  disclosure.

**What the schema cannot catch, and where the rule lives instead.** Four rules
are relations between documents or between a document and its consumers, and no
JSON Schema can express them. Three refuse typed in the consuming derivation,
never silently merged:

1. `page` must name a page the composed reference actually declares — a
   violation refuses `classref_composed_slot_conflict`.
2. `plot.over_slot` must equal the member's own `slot` (draft 2020-12 cannot
   compare two instance values) — a violation is a declaration conflict, a
   document referring to itself inconsistently, and refuses
   `classref_composed_plot_slot_mismatch`.
3. A member's slot key or a claimed action URN must not collide with a
   reference slot, another member, or a composed action class's claim — a
   violation refuses `classref_composed_slot_conflict`.

The fourth is a disclosure, not a refusal:

4. A dataset member's `plot` on a page whose class template already hosts a
   plot is ADMISSIBLE — the declaration contradicts nothing the schema can
   see, so it does not refuse. The page keeps the class's plot, the member's
   plot derives nothing, and every run REPORTS the row `composed plot <slot>:
   page <page> already hosts a plot (the page keeps the class's plot)`. The
   boundary, as ruled for this mechanism: a refusal is for a declaration
   conflict; a capacity or placement limit where the declaration is admissible
   is disclosed on the REPORTED channel.

**Shape discrimination on the pin seam.** A declaration rides the existing
`descriptor.contracts[]` path plus sha256 seam, and is discriminated from its
siblings by document shape: a document carrying `members` is a member
declaration, one carrying `urn` plus `claims` is an action class, one carrying
`actions` is a vendor catalog. The schema's `additionalProperties: false`
refuses a document carrying a sibling's key set as well, but the ambiguity
refusal is the derivation's, not the schema's — a key set is not a shape claim.

**Versioning.** The document's `contract_version` is the dialect version
(`0.1.0`), not this directory's version, for the pinned-bytes reason above. A
dialect bump is a standards motion of its own.

**The ledger's posture.** The composed-member mechanism's provenance surface is
the project conformance ledger (`ui/class-reference.json`): the applied member
set per vocabulary, one writer, and a gate read-back in both directions
including the member-to-slot mapping — sets alone have already been proved
insufficient once in this family's composed action classes. As with the composed
action-class rows, no schema governs the ledger's key set: the consuming tools
read it back, and the prose here is its contract. A pinned declaration whose
members apply nowhere is a REPORTED row on every run, never drift.

## Cross-class composition (normative, gateway issue #500)

Every class in this family must compose with every other class. A
device may claim several class profiles — the descriptor's `profiles`
array has no maximum — and the gateway merges the selected references
(parent §3.8): profile ids sorted bytewise, the first reference's slot
ids and page ids kept bare, every later reference's prefixed
`{slug}-` (the profile id's namespace with dots as dashes: the `daq`
class composes second as `otdp-daq-capture`).

Two rules bind every class reference, existing and new:

1. **Never author an identifier in another class's prefixed namespace.**
   A slot key, page id or layout page id shaped `otdp-<class>-…` collides
   with that class's own ids the moment both classes compose on one
   device. The merge overwrites such a collision silently; the schema
   cannot see it (the id pattern admits the literal).
2. **Never assume the class is the only profile, or that it sorts
   first.** An identifier that composes only when this class is the bare
   (first) profile breaks the device that claims it alongside any class
   sorting before it. An action URN belongs to one class: two classes
   claiming one URN in `expect.controls` is a duplicate control
   identifier no prefixing can separate.

The rule is enforced, not written down:
`tests/ui_html/test_classref_composition.py` composes every unordered
pair of the active family through the real selection and merge
(`select_references` + `_merge_references`) and refuses any identifier
the composed document would carry twice — slot keys, page template ids,
authored layout page ids, and `expect.controls` action URNs, each
refusal naming the colliding profiles. A class added to the family joins
the pair set automatically. A composition gate that has never refused
anything is a claim, not a guard: the refusal arms demonstrate a
deliberately colliding class — schema-valid, silently accepted by the
bare merge — refused from both directions (a new class colliding with
an existing one, and an existing class edited so a new one collides),
under either sort order.

## The layout vocabulary

A layout block composes the §E components the renderer already ships:
sections (panel composition), controls (`button`, `numeric`, `rotary`,
`text`, `select`, `boolean` — the 0.2.0 widening), reading tiles and data
tables, text bodies (author capability only — the class reference authors
no text nodes), and plot references that place a page's declared plot.

Bounds: at most 16 pages, 16 sections per page, section nesting depth at
most 3 (by construction), grid span at most 12, text bodies at most 512
characters. A section's children carry no ceiling: a vendor feature
surface adds children (staging nodes and buttons grow with the action
count), never pages or sections, so its density is a renderer concern,
not a validation one. One vocabulary,
two writers: a class reference may author structure-only layouts (its
`layouts` entries ride the same `layout.schema.json` through the family
schema's cross-file `$ref`), and an author may hand-write the same block
into a manifest's `extensions` map under
`plugin-ui-class-reference:layout`. Identical validation (A11).

The canonical plugin-ui validator is extension-blind: it validates a
manifest carrying the block exactly like one without it. This family
schema is the block's only validation authority. A host that does not know
the namespace ignores the block and serves the manifest's plain pages —
degrade by ignoring, never an error.

## The deviation ledger contract

A project declares conformance state in an author-owned
`ui/class-reference.json`: the references the project follows (`profile_ids`,
with `contract_version` and `reference_version` naming the family version the
document was derived against) and four inventories. The declared-deviation
ledger `deviations: [{expectation_id, reason}]` is the conformance record
proper. An `expectation_id` outside the reference's expect vocabulary is
refused (`classref_unknown_expectation:`) — an unknown id cannot launder a
divergence. A declared deviation downgrades exactly that expectation's
failure to a REPORTED row in the gate output; an undeclared divergence FAILS
the gate. D7-class expectations are non-downgradable: a deviation may never
name an energy-removing action's reachability — the ledger refuses
(`classref_deviation_forbidden:`); nothing may stand between the operator and
abort.

The other three inventories record what the reference never claimed, so the
project's own conformance record states it from birth and never loses it:

- `custom_actions: [{action, resolution: "custom", reason}]` — the residual
  members: every declared action no served catalog and no composed class
  described. The reason is level-aware — it names what actually derives
  (controls from the descriptor's own `input_constraints`, or nothing).
- `composed_actions: [{action, resolution: "composed", class}]` — every
  declared action a composed class claimed, carrying the action-to-class
  mapping.
- `composed_classes: [{class, validated_against}]` — each consumed class urn
  and the family version it was validated against. **The ledger records the
  classes the derivation applied:** a class applies when at least one of its
  claims names an action the descriptor declares. A pinned class that applied
  nowhere is disclosed by the gate's REPORTED channel on every run and stays
  out of the ledger by design. A class urn's own version is content and is
  never re-stamped.

Both tools key to that set. `verify-ui` reads the authored inventories back
against the derivation — both directions, including the action-to-class
mapping — and reports every mismatch as a REPORTED row, never a findings
failure. `migrate-ui` re-stamps `contract_version`, `reference_version` and
each `composed_classes[].validated_against` to the target family version,
re-resolving and re-validating every ledger-named class from its pin first,
and refuses (`migrate_ui_composed_unresolved` / `migrate_ui_ledger_drift`)
with nothing written whenever the ledger's inventories disagree with set
arithmetic over the current descriptor and pins. No schema governs this
document's key set — the deviation vocabulary is validated, and the
inventories are read back by the tools named above.

## Authoring path and provenance

Founding-family convention: the family's founding bytes were staged at
`docs/plugin-ui-class-reference-v1/` on the admitting branch, the corpus
rows cite that authoring path as `source`, and the staging directory was
removed in the same pull request. Provenance lives in git history and in
the corpus manifest's `source` fields — the plugin-ui-preview founding
families' own shape. The 0.2.0 and 0.3.0 rows cite their predecessor
corpus paths (the supersession-copy convention every later row follows);
the 0.3.0 class file cites its `docs/plugin-ui-class-reference-v2/`
staging path the same way.

## The plugin-ui floor (cross-constraints)

The family's cross-constraints rows name the plugin-ui floor:
`plugin-ui >=0.4.0,<0.5.0` for each of family versions 0.2.0, 0.3.0, 0.4.0
and 0.5.0. A bump ADDS its row and never amends a predecessor's away (the
refute fold's F3 ruling: a served pin never loses its constraint), so the
floor is stated once per released version, each row firing for its own
resolved pin. The floor is unchanged across all four — each bump consumes
vocabulary plugin-ui 0.4.0 already ships. The row is vacuous while plugin-ui
serves a single version, and the family goes to review at every plugin-ui
bump — a plugin-ui bump carries vocabulary the reference may silently
mis-derive, so the reference re-proves its derivation per bump (design
record R2).

## Names

All fixture names are invented. "Veridian", "PSU-01", "DMM-01", "OSC-01",
"FGEN-01", "ELOAD-01", "SMU-01", "DAQ-01" and the `ch1`/`ch2` channel naming are fixture vocabulary, not real
products, vendors, or benches.
