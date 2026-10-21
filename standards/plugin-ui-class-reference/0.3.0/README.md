# plugin-ui-class-reference 0.3.0

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

Bounds: at most 16 sections per page and 16 children per section, section
nesting depth at most 3 (by construction), grid span at most 12, text
bodies at most 512 characters. The per-page node ceiling of 64 is a
gate-time census: the schema bounds each array, never the page total — a
block the schema admits can still fail the gate census. One vocabulary,
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
`ui/class-reference.json`: the reference the project follows (`profile_id`
and family version) and the declared-deviation ledger
`deviations: [{expectation_id, reason}]`. An `expectation_id` outside the
reference's expect vocabulary is refused (`classref_unknown_expectation:`) —
an unknown id cannot launder a divergence. A declared deviation downgrades
exactly that expectation's failure to a REPORTED row in the gate output;
an undeclared divergence FAILS the gate. D7-class expectations are
non-downgradable: a deviation may never name an energy-removing action's
reachability — the ledger refuses (`classref_deviation_forbidden:`);
nothing may stand between the operator and abort.

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

The family's cross-constraints row names the plugin-ui floor:
`plugin-ui >=0.4.0,<0.5.0` for family version 0.3.0 (the row amends in
place with this bump, evidence re-cited; the floor is unchanged — the
widening consumes vocabulary plugin-ui 0.4.0 already ships). The row is
vacuous while plugin-ui serves a single version, and the family goes to
review at every plugin-ui bump — a plugin-ui bump carries vocabulary the
reference may silently mis-derive, so the reference re-proves its
derivation per bump (design record R2).

## Names

All fixture names are invented. "Veridian", "PSU-01", "DMM-01", "OSC-01",
"FGEN-01", "ELOAD-01", "SMU-01", "DAQ-01" and the `ch1`/`ch2` channel naming are fixture vocabulary, not real
products, vendors, or benches.
