# L15 — the inverted direction: `otdp.electronic_load` class reference, the §C.1 sink ruling (mockup authored)

**Date:** 19 October 2026
**Slot:** L15 of the class-reference train (parent gateway issue #463; program record
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` §7A row L11–L21, §8's
RC-1/D-1 row; the sweep order L11 dc_psu → L12 dmm → L13 oscilloscope → L14
function_generator → **L15 electronic_load** → L16 smu … L21 vna, verified against §7A
AND the workbench §8 table `docs/internal/ui-styleguide-workbench-design.md:320`
("electronic load"), fifth position).
**Branch:** `feat/l15-eload-classref` (design record only; no build in this slot).
**Worktree:** `.wt/l15-q8n3/`, off `origin/feat/l11-dcpsu-classref` `c64f3d05` (the
L11-rebase-union tip — the same base the L13 lane designs on; the L12/L13/L14 lanes'
heads are unmerged, so the batch's true tip is still moving and this slice rebases onto
it at build time, the L13 §7 choreography terms).
**Evidence baseline:** gateway branch head `c64f3d05`; gitlink `9e0449ef` (= SDK
v0.16.0 per the L13 record's verification at the same base commit; this pass's submodule
is uninitialized so the tag is cited, not re-verified — and v0.16.0's vendored classref
tree is `{0.1.0, 0.2.0}` per the same verification: **the 0.3.0 SDK leg is
outstanding**); plugin-ui 0.4.0 active; plugin-ui-class-reference **0.3.0 active on the
branch, unreleased** (manifest verified: 5 files, 4 corpus rows; range
`>=0.1.0,<0.4.0` verified; main independently verified to still serve 0.2.0 at range
`>=0.1.0,<0.3.0`); OTDP 0.2.3 active; `class-dmm.json` NOT yet on this base (the L12
build's corpus commit is pending — consistent with the batch state this pass observed).
**Binding design points:** the program record D1–D14 (esp. D2 structure-not-data, D7
run-group safety, D13/D14 effective capability and coverage); the L11 record in full —
**§2.2 named this slot in advance** ("The same action shape recurs at L14
function_generator, **L15 electronic_load** and L16 smu; whatever that slice lands
becomes their surface too") and §9's deferral row armed the L15 reopen trigger; the L12
record (the in-window batch law, the shared census helper, the series-required
settlement, the forbid-drop reasoning); the L13 record (the in-window landing shape,
the per-idiom answers §5 answers against, the banked-RED convention); GOVERNANCE's
train rule, G-5 pacing, copy-never-move.

## 0. Summary and design thesis

L15 authors the sixth class reference — `class-electronic_load.json`, binding
`otdp.electronic_load/1.0.0` — and authors the mockup it is validated against (no
`class-electronic_load.html` exists; the mockup index carries `class-logic_analyser`,
`class-dc_psu`, and the dmm/scope mockups are this batch's own authored artifacts). The
thesis in one line:

> The electronic load is the sweep's first **energy-admitting** class — the instrument
> whose engage action starts energy flow *into itself*, inverting the PSU's direction —
> so the class's one hard question is not presentation vocabulary (it needs **zero
> family-schema surface**: its page is dc_psu's own composition over sink-role channels)
> but **which side of §C.1 the input-enable sits on**; this record reads the rule, rules
> the direction, pins it in machine-checkable reference data, and names the rule's
> letter-gap for the slice that owns it.

Three grounding facts fix the scope, each verified in the worktree this pass:

1. **The OTDP class contract is complete, scalar-shaped, and sink-role.** The profile
   (`standards/otdp/0.2.3/device-profile-catalog.json`, `otdp.electronic_load/1.0.0`):
   `required_actions: [configure, output, measure]`, `optional_actions: []`,
   `channel_roles: ["sink"]` — the dc_psu action triple verbatim over inverted-role
   channels. The example (`standards/otdp/0.2.3/examples/class-electronic_load.json`)
   declares 2 sink channels (`ch1`/`ch2`), each `quantities: [voltage, current,
   power]` — the dc_psu example's mirror. `measure`'s output is the measurement-model
   dataset (`urn:otdp:measurement:0.2.3#/$defs/dataset`); device-classes §9 is
   normative on its sense: "**positive current/power representing energy absorbed from
   the DUT**. This is not interchangeable with the PSU sign convention; quantity
   context includes direction."
2. **The corpus itself burdens the engage direction — twice.** The `output` action's
   input schema carries `channel` (pattern string), `enabled` (boolean) and
   `configuration_id` (string) with an `allOf/if/then`: **`configuration_id` is
   required iff `enabled: true`** — the draw must name the commissioned configuration
   it will sink at; the disengage direction is bare `channel` + `enabled`. And
   device-classes §3, class-generic: "An enable action requires a current configuration
   ID. **An authorised protective disable does not require that token and must not be
   blocked merely because it expired.**" The OTDP layer thus encodes the same
   directional asymmetry §C.1 encodes at the presentation layer — independent
   corroboration, not inference.
3. **The family vocabulary is already ahead of everything the load asks for.** Post-L12
   semantics (`series` required on `time_series`), post-L13 enum (`waveform` — not
   needed here), `where_role` a free string (`"sink"` needs no widening), the
   `readings` page kind, the `reading-tile`/`engineering-plot`/`data-table` census
   arms, the layout `reading` nodes, `host_supplied` structural field names, and the
   §E.1 inventory — all shipped or batch-designed. The load reference is expressible
   **without widening anything**, and unlike L12 (which at least settled F4's schema
   edit) this slice moves **no schema byte at all**.

**The belongs-in-batch check (the dispatch's standing exit):** the evidence says this
class belongs in this batch — the profile is complete in the ACTIVE corpus version
(not a promotion case like E-1), the fixture exists and is sufficient (2 × 3 tiles at
expansion; the mockup is authored to the example's own shape so no derived fixture is
needed — L12's good shape, second application), and the vocabulary covers the page.
What would have falsified membership: an optional action needing `when_declared`
presentation structure (the profile has none), a measure output that is not the scalar
dataset shape (it is the shared `$defs.dataset`), or a plot kind the family lacks (the
trend is `time_series`). None fired. Proceed.

## 1. The safety shape first — the directional question, read and ruled

This is the question the dispatch flagged as mattering more here than usual, and it is
the reason this record exists in this form. **Read §C.1 precisely** (all three rules,
verbatim from `docs/internal/ui-contract.md:201-203`):

- `R-ENERGISE-1`: "An action is **energy-sourcing iff it closes a path for energy to
  reach the DUT**: enabling an output, or changing a setpoint of a currently-energised
  output. An energy-sourcing action requires a confirmation step whose text states (i)
  the effect — the output will be energised, (ii) the exact values to be applied, with
  value and unit, and (iii) the target — which output or channel. The initial control
  only stages intent; the confirm is a second explicit action."
- `R-DEENERGISE-1`: "An **energy-removing action (output off)** is one action, never
  confirmed, never gated. Nothing in the presentation may stand between the operator
  and de-energising (decision A04)."
- `R-PROTECT-1`: "Energy-sourcing actions are disabled with reason `protection-active`
  while a protective trip is active."

**What a load's input-enable does.** The load's channels are sinks; the DUT is the
energy source. `output enabled: true` engages the input: the load begins drawing per
its configured mode (CC/CV/CR/CP) and setpoint; energy flows **DUT → load**, dissipated
as heat in the instrument. `enabled: false` disengages: the draw stops, the circuit
returns to no-flow.

**Applying the letter — and finding the load on neither side of it:**

- Input-engage is **not energy-sourcing under R-ENERGISE-1's iff**: it closes no path
  for energy to *reach the DUT* — energy *leaves* the DUT and reaches the load. The
  rule's two named examples ("enabling an output", "setpoint of a currently-energised
  output") are source-instrument sentences; §C.1 is written in PSU voice, because the
  PSU was the energy class that existed when it was written (the L11 record §0.3 said
  so: "ui-contract §C.1 is written in PSU language").
- Input-engage is **not energy-removing under R-DEENERGISE-1**: that rule's
  parenthetical "(output off)" pins the *flow-stopping* action; the load's
  flow-stopping action is input-DISENGAGE.
- **The misread this section exists to kill:** "a load removes energy from the DUT, so
  its engage action is the energy-removing one, so engage is the ungated action." That
  reading inverts the rule's safety direction — it makes the hazard-STARTING action
  frictionless and, by symmetry, buries the stop behind whatever confirmation the
  engage direction no longer needs. The correct classification keys on **whether the
  action starts or stops the circuit's bulk energy flow**, not on which box the energy
  lands in. `R-DEENERGISE-1`'s own parenthetical is the disambiguator: "(output off)"
  — the de-energising side is always the *off*, the flow-stop, never "the action that
  drains".

**Applying the substance — the ruling, with its three corpus corroborations (each
verified this pass):**

> **The load's input-ENGAGE sits on the R-ENERGISE-1 side in substance and outside its
> letter.** It is the flow-starting, hazard-creating action: engaging the input starts
> bulk energy flow through the DUT, the cabling, and the load's dissipating elements;
> device-classes §9's required failure cases (undervoltage cutoff, loss of control
> while sinking, excessive dissipation, failed disengagement) are engage-direction
> hazards. Its compliant presentation is therefore the R-ENERGISE-1 form — the initial
> control only stages intent; the confirm is a second explicit action naming (i) the
> effect (the input will engage; the load will draw), (ii) the exact values (the named
> configuration's mode and setpoint, with units), and (iii) the target (which
> input/channel). The three corroborations: (a) the hazard analysis above; (b) the
> OTDP output schema's conditional — `configuration_id` required **iff** `enabled:
> true` — which forces the confirm's clause (ii) to have a value to name, exactly as
> R-ENERGISE-1 demands; (c) device-classes §3's asymmetry: the enable requires a
> current configuration token, the protective disable "does not require that token and
> must not be blocked".
>
> **The load's input-DISENGAGE sits on R-DEENERGISE-1's side literally and exactly:**
> one action, never confirmed, never gated, nothing intermediated — and R-PROTECT-1's
> load reading follows: the ENGAGE control is disabled with reason
> `protection-active` while a trip is active; the DISENGAGE control stays enabled
> (ui-html's `_check_r_protect` already pins this pair shape for the PSU control).

**The letter-gap, named — not amended.** §C.1's iff defines the confirm-required class
as "energy-sourcing" in source-instrument voice; an energy-ADMITTING instrument's
flow-starting action escapes the definition's letter while carrying its entire safety
substance. That is a wording finding in `docs/internal/ui-contract.md`, and this
record does not touch that file: ui-contract is not this family's artifact, the §C.1
preamble assigns its renderer enforcement to the safety-behaviours slice (issue #242
slice 2), and principle 9 plus L11 §2.2's no-preemption posture govern — the same
hand-off L11 made, now with the second class that needs it and the wording fix named.
Candidate wording for that slice's landing (recorded for it, not executed): classify
by flow direction — "an action is flow-starting iff it causes bulk energy flow to
begin through the test circuit, in either direction; a flow-starting action requires
the R-ENERGISE-1 confirmation; a flow-stopping action is R-DEENERGISE-1's one ungated
action" — which subsumes sourcing and admitting and removes the trap. **L16 smu will
need this answered too** (a source AND sink in one instrument); the finding is framed
so that slice inherits it whole.

**How the class reference expresses the ruling — dc_psu's shape, second instance,
with the direction pinned in data:**

1. The one `output` action carries both directions with opposite presentation rules;
   the per-action `expect.controls` vocabulary (`button|staging|preset|deviation`)
   cannot split them — so `otdp.electronic_load.output/1.0.0: "deviation"`, with
   `cannot_derive: input-control` whose `reason` names the inversion in the record's
   own words (the load-side twin of dc_psu's `output-control` row).
2. `forbid` carries `intermediated-energy-removing-action` with load-specific content:
   the never-intermediated action is the DISENGAGE. After dc_psu this is the id's
   second true home (dmm dropped it — no energy action possible; the scope carried it
   abort-adjacent — the acquisition lifecycle's stop). The load is the class where the
   id's subject is a bulk-energy flow-stop.
3. The slot makes the corpus's conditional structural: `output` is a `procedure` slot
   with `host_supplied: ["configuration_id"]` — the analyser's `arm` convention
   (gateway-issued token, structural field name, D2-clean), applied to the field the
   OTDP schema requires on the engage direction only.
4. The hand-author risk is disclosed, not solved by parallel machinery: an overlay
   staging `output` in both directions — or worse, gating the disengage — passes
   today's gate (the D7 slug set names `abort`; the load's `output` is not in it),
   exactly as L11 §2.2/R5 disclosed for the PSU. The class's UI-GUIDE text names the
   load's inverted direction explicitly so no overlay author reads "energy-removing"
   the wrong way round. The enforcement slice owns the fix; **this record adds one
   thing L11 could not: a machine-checkable pin (A8) so the dangerous "fix" — mapping
   `output` to `button` (ungated engage) or `staging` (gated disengage) — is a visible
   red, not a silent choice.**

## 2. The mockup (authored spec — the build's first artifact)

`docs/internal/ui-styleguide-mockups/class-electronic_load.html` is authored to the
dc_psu/dmm/scope convention — one composition, two `data-theme` sections (light/dark)
over the shipped token set (the embedded `bw-shipped:` blocks), self-contained,
~13 KB, invented identifiers only (`ELOAD-01`, `BENCH A`; public-repo discipline paid
at authoring). The L11 lessons are built in from birth (no hook-pass debt, no
placement debt), per the convention L12 codified and L13 extended:

- **§E.1 component hooks from birth**: `bw-reading` on the reading `article` cards,
  `bw-alert-bubble` on the alert `aside`, `bw-plot` on the trend `section`,
  `bw-data-table` on the `table` — hooks on their §E.1 ROOT elements.
- **The F1 placement contract from birth**: every hook on its root tag,
  container-scoped hooks inside their containers (`bw-reading` only in the readings
  row, `bw-plot` only in the lower grid), and the staged-draw control card carrying
  NO `bw-` hook — a cannot-derive surface must never present as a reading.

**What an electronic load's class page shows, and why** (each element traced to the
class's nature — a programmable dissipator whose observable is what it draws, and
whose hazard is that drawing):

| element | disposition |
|---|---|
| title row + `Controls` button (`Electronic load · ELOAD-01`) | page chrome/navigation — host territory, as every class |
| readings row: 6 `bw-reading` cards (ch1/ch2 × voltage/current/power), one carrying the `warning` variant (ch1 current), each with a quality line | **derives**: one reading-tile per (channel, quantity) variable of the `measure` dataset — the example's own 2 × 3 shape, so the A3 census resolves over the committed example directly and no derived fixture exists; the count is an expression at expansion, never the literal 6; severity is runtime observation state — structure renders the variant, data decides it |
| quality lines (`✓ NORMAL · 84 ms`) | observation quality/freshness (§B/ST-4 machinery; runtime data) |
| alert aside: "△ Sinking margin — ch1 draw approaching configured current maximum · ELOAD-01" | **cannot_derive** `sink-margin-alert` — the condition (draw vs configured `max_current_a`/`max_power_w`) is commissioned policy (A02); dc_psu's `margin-alert` shape with the load's own quantity and sense (absorbed, not delivered) |
| lower grid: staged-draw control card (`STAGED DRAW`, mode/setpoint line `CR · 3.05 Ω`, `STAGED · APPLY REQUIRED`) — NO `bw-` hook | **cannot_derive** `draw-staging` — configure is preset-mediated at birth; the mode/setpoint pair is the load's setpoint surface; presets are commissioned evidence (A02). The illustrative story is internally consistent: CR mode at 3.05 Ω over a DUT at ~11.98 V draws ~3.93 A against a configured 4.00 A maximum — the margin alert's condition, painted in its threshold-neighbourhood; the policy decides the threshold, the mockup paints one instance |
| recessed trend plot "INPUT · LAST 60 SECONDS": ch1 voltage + ch1 current traces, dashed configured-maximum line on the current trace | **derives**: one `time_series` plot over the measure slot, one series per numeric scalar variable (6 variables derive; the mockup's two-trace choice is an author `channel_hints` matter — L11's disclosed posture, second application). The dashed line is **cannot_derive** `limit-overlay` — a runtime join against the active configuration |
| Channel / Reading / Quality table (6 rows — ch1/ch2 × V/I/P) | **derives**: one `data-table` reading node over the same dataset, one row per (channel, quantity) |

The layout is the dc_psu ratio — readings 12 raised, trend 7 recessed, table 5 raised —
a deliberate authoring choice: the load is the PSU's mirror (a scalar/readings-shaped
class whose trend is the operating story), and the class's difference from dc_psu is
**content and direction, not geometry**. The styleguide's mockup index line gains
`class-electronic_load.html`; `docs/internal/ui-styleguide.md` gains the
electronic-load class-page row beside dc_psu's.

**The §B.3 observation, honestly placed.** §B.3's `limiting` state ("A limit, not the
set-point, is constraining the value (**constant-current operation**; a channel near
full scale)") is the load's signature reading state — the class where
constant-current/constant-voltage regulation IS the operating mode, and where the
undervoltage floor (device-classes §9) constrains the draw below setpoint. It is a §B
contract row (renderer/host machinery, already normative), **not** an RC-L5-1 idiom
and **not** a reference surface — and the mockup does not paint it (the convention —
dc_psu and dmm painted severity variants only; §B.3's no-glow/no-alert composition
rules make a hand-painted instance easy to get wrong). Recorded here as the named
observation: the first renderer-side exercise of `limiting` on real data is expected
on this class; nothing in this slice depends on it or builds for it.

## 3. The reference, derived from the mockup

`standards/plugin-ui-class-reference/0.3.0/class-electronic_load.json` —
structure-not-data (D2), dc_psu's posture applied to its mirror class: authored
structural strings only; every count an expression; every quantity name arriving via
the descriptor at expansion. The complete designed document:

```json
{
  "contract_version": "0.3.0",
  "profile_id": "otdp.electronic_load/1.0.0",
  "title": "Electronic load",
  "targets": { "plugin_ui": ">=0.4.0" },
  "slots": {
    "inputs": {
      "kind": "channels", "where_role": "sink", "key": "id", "label": "label"
    },
    "measure": {
      "kind": "dataset",
      "action": "otdp.electronic_load.measure/1.0.0",
      "schema_source": "output_measurement"
    },
    "configure": {
      "kind": "configuration",
      "action": "otdp.electronic_load.configure/1.0.0",
      "schema_source": "input_schema"
    },
    "output": {
      "kind": "procedure",
      "action": "otdp.electronic_load.output/1.0.0",
      "host_supplied": ["configuration_id"]
    },
    "vendor_actions": { "kind": "vendor_actions" }
  },
  "pages": [
    {
      "id": "input", "title": "Input", "kind": "readings",
      "binding_slots": ["measure"],
      "plot": { "kind": "time_series", "over_slot": "measure", "series": "numeric_variables" }
    },
    {
      "id": "configuration", "title": "Configuration", "kind": "configuration",
      "binding_slots": ["configure"]
    },
    {
      "id": "device-features", "title": "Device features", "kind": "configuration",
      "binding_slots": ["vendor_actions"], "vendor_features": true
    }
  ],
  "layouts": [
    {
      "page_id": "input",
      "sections": [
        { "id": "readings", "title": "Readings", "surface": "raised", "span": 12,
          "children": [ { "binding_id": "measure", "kind": "reading-tile" } ] },
        { "id": "trend", "title": "Trend", "surface": "recessed", "span": 7,
          "children": [ { "plot_index": 0 } ] },
        { "id": "table", "title": "Table", "surface": "raised", "span": 5,
          "children": [ { "binding_id": "measure", "kind": "data-table" } ] }
      ]
    }
  ],
  "expect": {
    "components": {
      "reading-tile": { "count": "{n_reading_tiles}", "per_page": "input" },
      "data-table": { "count": "1", "per_page": "input" },
      "engineering-plot": { "count": "1", "per_page": "input" },
      "panel": { "count": "{n_pages}" },
      "mode-banner": { "count": "1", "per_page": "*" }
    },
    "controls": {
      "otdp.electronic_load.configure/1.0.0": "preset",
      "otdp.electronic_load.output/1.0.0": "deviation"
    },
    "forbid": [
      "confirm-wrapped-run-action",
      "color-role-hint-on-lane",
      "untraceable-lane-label",
      "intermediated-energy-removing-action"
    ]
  },
  "cannot_derive": [
    { "id": "input-control",
      "aspect": "the input engage/disengage control",
      "reason": "the directional section C.1 presentation is inverted for a sink: engage is the energy-admitting, flow-starting direction (stage then confirm naming effect, values and target); disengage is the one ungated action (R-DEENERGISE-1); the per-action control vocabulary cannot split them; renderer enforcement belongs to the safety-behaviours slice",
      "author_action": "none until that slice lands; the deviation is REPORTED, never silent" },
    { "id": "draw-staging",
      "aspect": "the staged mode/setpoint draw control",
      "reason": "configure is preset-mediated at birth; presets are commissioned evidence (A02)",
      "author_action": "author ui/presets/*.json via check-preset; the expander emits the scaffold" },
    { "id": "sink-margin-alert",
      "aspect": "the sinking-margin alert",
      "reason": "the alert condition (draw vs configured current or power maximum) is commissioned policy (A02)",
      "author_action": "bench policy at commissioning; the alert-bubble renders from host-observed conditions" },
    { "id": "limit-overlay",
      "aspect": "the trend's dashed configured-maximum line",
      "reason": "the limit value is runtime configuration data; the overlay is a runtime join",
      "author_action": "host composition where a configured limit is active" },
    { "id": "presets",
      "aspect": "preset settings values",
      "reason": "presets are commissioned evidence, never derived (A02 unamended)",
      "author_action": "check-preset" },
    { "id": "channel-names",
      "aspect": "input names beyond descriptor labels",
      "reason": "the descriptor owns channel identity",
      "author_action": "label channels in the descriptor" }
  ]
}
```

**Naming, each choice grounded.** The channels slot key is `inputs` with
`where_role: "sink"` — the role-named-key convention (dc_psu `outputs`/source, dmm
`inputs`/measure, scope `channels`/analogue_input); the load's terminals are inputs.
The readings page is `Input` — the page presents the input terminals' readings, and
device-classes' own §1 row names the class's action pair "**input enable/disable**"
while §9 says "`output enabled` means the load input is engaged": the corpus itself
distinguishes the ACTION name (`output`, kept verbatim in every URN) from the TERMINAL
name (input). The cannot_derive id `input-control` follows the corpus's phrase. The
`targets` floor is `>=0.4.0` — dc_psu's own floor (the readings/time_series machinery
consumes 0.4.0 vocabulary), consistent with both cross-constraints rows.

**Slots, each verified against the catalog this pass.** No `when_declared` slots (the
profile has no optional actions). `host_supplied` is empty on `measure` (its optional
`configuration_id` is a caller input, the dc_psu posture) and on `configure` (its
`configuration_id` is issued at configuration time, not control time), and carries
exactly `["configuration_id"]` on `output` — §1.3's structural marker. **Build-time
verification named (the one expander risk this class adds):** the SDK's
`_derive_controls` treatment of that conditional field must not promote a control
surface for `output` — the dc_psu §2.2 analysis (both rejected paths) holds
identically here, and the deviation posture is the design's claim; if the build
falsifies it, the fix lands inside the batched SDK widening with the finding
re-disclosed on the PR.

**expect.components**: `reading-tile` `{n_reading_tiles}` on the input page (resolves
as `n_sink_channels` × per-channel declared-quantity count over the descriptor — the
role-generic counter beside `n_source_channels`/`n_measure_channels`/
`n_analogue_channels`, sharing `n_scalar_variables`, `n_reading_tiles`, `n_pages`;
closure discipline is the invariant, exact names are build detail, L11 §3 item 5's
posture, fourth application); `data-table` `1` on the input page (plus the settings
table on the configuration page, pooled per the gate's existing counting); `engineering-plot`
`1` on the input page; `panel` `{n_pages}`; `mode-banner` `1` per page. **controls**:
`configure → "preset"`, `output → "deviation"` — §1's ruling in vocabulary form.
`measure` needs no row (dataset slots are page-covered, `fetch`'s own shape). **forbid**:
all four ids, §1.2's reasoning — the three family-generic carries plus
`intermediated-energy-removing-action` with its second true home.

## 4. The widening answer: nothing — and this time not even a settlement

Stated and defended, the L12 §3 posture with a stronger claim. The differences from
dc_psu are all inside the existing vocabulary: the channel role (`where_role` is a
free string — `"sink"`); the conditional `configuration_id` (`host_supplied` names,
existing field); the load-specific cannot_derive set; the page named for the input
instead of the output. **No family-schema byte moves in this slice** — unlike L11
(plot widening), L12 (series-required) and L13 (waveform member), which each carried a
schema motion inside the same window; the load is the first sweep class since the
analyser that needs none, which is the honest result of dc_psu having already paid the
scalar/readings widening this class rides. If the build falsifies this (a load surface
the vocabulary cannot express), that is the disclosed underpowered branch and it comes
back as evidence, never as silent scope creep.

## 5. The five display idioms (RC-L5-1): read L13's answers — none land here

L13's §4 is the standing per-idiom audit; this record read it and applies it:

| idiom | L13's verdict | the load's call |
|---|---|---|
| the waveform canvas | LANDS at L13 (`engineering-plot` over `waveform`) | **not needed** — the load's trend is `time_series` (the dc_psu arm) |
| the capture-context strip | LANDS BY USE (§E.2.5, per-trace, decimation-gated) | **not exercised** — §E.2.5's disclosure fires on decimated capture traces; a 60-second scalar trend is not a decimated capture; no motion, no painting |
| cursor/trigger markers | DEFERRED BY NAME (no marker attributes on `engineering-plot`) | **not needed** — no markers on a scalar trend |
| grouped label column | HONEST NEGATIVE (lanes-only) | **not needed** — no lanes |
| annotation chips | HONEST NEGATIVE at birth (decode-sourced) | **not needed** — no decode |
| position badges | HONEST NEGATIVE (lanes identity rule) | **not needed** |
| derived frequency | HONEST NEGATIVE (§E.2.6 machinery, host-side) | **not needed** — `power` is a first-class declared quantity in the OTDP model (the example's channels declare it), so no derived-looking tile exists; L11's own note, second application |

**None land; no bump is called; the deferral stands with its triggers armed.** The
nearest load-specific candidate — §B.3's `limiting` state — is §B machinery, not an
RC-L5-1 idiom (§2's observation); conflating the two lists would be a category error,
and this section records that they were checked separately.

## 6. The A3 extension — the shared census, and the direction pin

`tests/ui_html/test_classref_electronic_load.py` extends the shared instrument
(`tests/ui_html/classref_census.py` — landing with the L12 build; the fourth consumer
after dc_psu's import switch, dmm and scope; if this slice's build runs before the
helper exists, the lift is this slice's disclosed mechanical motion, L12 §6's terms
verbatim). The arms, the L12/L13 seven plus this class's own:

1. **Hooks in both themes** — every hook family ≥1 per theme section.
2. **Hook counts EQUAL the resolved expectation over the committed OTDP example**
   (2 channels × 3 declared quantities = 6 `bw-reading` cards, 1 `bw-plot`,
   1 `bw-data-table`, 1 `bw-alert-bubble`; no derived fixture — the mockup is authored
   to the example's shape). Both kill directions by construction: a mockup edit that
   changes a count reds against the resolved side; a reference edit that changes the
   derivation (a count expression, the plot binding, the channels slot's role) reds
   against the mockup's counts. A mockup edit that does NOT redden the test is the
   instrument failing — report, never a quiet pass.
3. **Placement, including the count-conserving-move kill**: every hook occurrence on
   its §E.1 root tag (`bw-reading` → `article`, `bw-alert-bubble` → `aside`, `bw-plot`
   → `section`, `bw-data-table` → `table`), the container-scoped hooks inside their
   containers (readings row, lower grid), and the staged-draw control card carrying NO
   `bw-` hook. The RED arm moves a hook count-conservingly (a `bw-reading` onto the
   control card; a `bw-plot` out of the lower grid) and the placement assertions red
   while the count arm stays green under the move — the mutation is demonstrated to
   kill, not assumed.
4. **Theme-invariance** — the census is identical across themes.
5. **The alert is one per theme and a named cannot_derive** (`sink-margin-alert`).
6. **Selection RED-to-green** — banked at design time this pass (executed, recorded):
   gateway-side `select_references(corpus, descriptor)` on the branch head `c64f3d05`
   returns `None` for the electronic_load example while `class-dc_psu` →
   `['otdp.dc_psu/1.0.0']` and `class-logic_analyser` → `['otdp.logic_analyser/1.0.0']`
   resolve (`class-dmm.json` absent on this base — consistent with the L12 build's
   pending corpus commit). The slice greens the electronic_load half only.
7. **The pattern-page arms** (the drift guard over the load input composer): 6 tiles
   derived from the corpus pair (2 × 3, never literals); labels are corpus strings
   (channel labels × quantities); one plot, the two author-chosen traces; the table's
   body one row per pair; the sections mirror the reference layout block's surfaces
   and spans; only §E.1 partials compose; no control surface fabricated (no button, no
   knob-as-applied, no confirm); the PATTERNS census entry is `kind: class-page`,
   `row_id: plugin-ui-class-reference::class-electronic_load`, `fixture_id: input`;
   both themes export.
8. **The direction pin (this class's own arm — A8's test-side twin).** The module
   asserts over the committed reference document: `expect.controls
   ["otdp.electronic_load.output/1.0.0"] == "deviation"`; `cannot_derive` carries
   `input-control`; `forbid` carries `intermediated-energy-removing-action`. The RED
   demonstrations: mutating the control to `"button"` (the ungated-engage misread)
   reds; mutating it to `"staging"` (the gated-disengage misread) reds; dropping the
   forbid id reds. **The pin's purpose is narrow and stated:** it does not enforce
   §C.1 (nothing this side of the safety-behaviours slice can); it makes the two
   dangerous simplifications of this class's ruling visible as test failures instead
   of silent authoring choices.

## 7. Choreography — landing inside the open window

1. **Gateway branch content** (this slice): the §8 corpus motion + this record + the
   census module + the input-page composer + the mockup + the styleguide rows.
   Stacked on the batch line (rebased from `c64f3d05` onto the then-current batch tip
   at build time — L14 designs in parallel and §7A orders it before L15; the shared
   prose files (family README files-table row, styleguide index line, class-page rows)
   are adjacent-line edits the stacking order resolves; no semantic collision exists —
   the class files, census modules and composer functions are per-class named).
2. **The L12 batched promotion leg is the slice's only cross-repo dependency**: the
   load's SDK needs (fixtures, counter names, the conditional-`host_supplied` field
   treatment) fold into that leg's widening build the way L13's waveform arms fold —
   designed here, built there; if the leg has already cut when this build runs, the
   load SDK arms become the leg's own follow-up under then-current train rules (L13 §7
   item 2's terms, second application).
3. **The #408 order for the batch as a whole** stands: ui-html 0.3.1 → SDK PR →
   release cut → pointer advance (gitlink + `.gitmodules` pin + mirror + matrix in one
   commit) → merge on the full rollup (`scripts/merge-verified.sh`), zero fail, zero
   pending. This slice performs none of those legs (design only; the dispatch's
   no-push/no-PR/no-SDK-sync instruction).
4. The standards tripwire fires by design (non-empty `standards/` diff); this record
   is the named sanction. Standards-governor lane mandatory; two-lane adversary pass
   on the built slice.

## 8. Corpus-motion census (exact bytes)

Gateway repo, `standards/`:
- **Added** `standards/plugin-ui-class-reference/0.3.0/class-electronic_load.json` —
  one new corpus row, `source` citing the authoring staging path
  `docs/plugin-ui-class-reference-v2/class-electronic_load.json` (removed in-PR — the
  founding convention, dc_psu's row shape, third application).
- **Edited**: NOTHING in `standards/` — no schema byte, no manifest byte, no policy
  byte, no cross-constraints byte (§4's answer made exact: the version entry, the
  range `>=0.1.0,<0.4.0`, and both cross-constraints rows already serve this landing;
  the load consumes plugin-ui 0.4.0 vocabulary the 0.3.0 row already floors).
- **Unchanged**: `class-reference.schema.json`, `layout.schema.json`,
  `class-logic_analyser.json`, `class-dc_psu.json`, and — from the moment they exist
  on the branch — `class-dmm.json`, `class-oscilloscope.json`,
  `class-function_generator.json` (byte-identical through this slice, A5); every
  0.2.0/0.1.0 byte (zero frozen-row rewrites, A7).
- **Unpinned prose**: the family `README.md` files-table row; the styleguide's mockup
  index line + the electronic-load class-page row.

Gateway repo, docs/tests (no corpus impact):
`docs/internal/ui-styleguide-mockups/class-electronic_load.html` (new,
prose-adjacent — no corpus rows, no governance event); `tests/ui_html/
test_classref_electronic_load.py` (the shared-census fourth instance; the
`classref_census.py` lift itself is L12's disclosed motion or this slice's if it
builds first).

`packages/ui-html`: the electronic-load input-page composer + PATTERNS entry (rides
the batch's ui-html release, F2's bounded-divergence ruling).

SDK (inside the batched leg): the load fixtures (the OTDP example as F-eload-1;
refusal fixtures: zero sink channels → the channels-slot refusal; absent required
action → `classref_required_action_absent`), the counter names, the
conditional-`host_supplied` field treatment (§3's named verification), the vendored
0.3.0 ingest picking up the new class file. **No otdp motion of any kind.**

## 9. Deferrals, each with a home and an observable reopen trigger

| defers | home | reopen trigger |
|---|---|---|
| the directional input control (engage staged+confirm / disengage ungated) | the §C.1 safety-behaviours enforcement slice + the per-action control vocabulary's directional split, in the next wall-payment event | that slice landing; **L16 smu hits the same shape from both directions at once — its design inherits this ruling and stress-tests it** |
| the §C.1 letter-gap (energy-sourcing iff written in source-instrument voice; the admitting case escapes the letter) | ui-contract's maintenance event, carried by the safety-behaviours slice | that slice's landing, or an owner ruling on the wording — §1's candidate text stands recorded for it |
| the staged mode/setpoint draw idiom | the staging-over-preset capability (L5's batching rule family) | a class whose configure is field-stageable, or the owner calling the load's draw surface |
| sink-margin-alert / limit-overlay derivations | host composition + commissioned policy | the D13 policy seam at preview |
| multi-input coupled presentation (series/parallel load banking) | per-device constraints + the descriptor (device-classes §2: coupling "cannot be inferred from channel numbering") | a real admitted descriptor declaring coupled sink channels |
| dynamic/load-step operation | OUT OF PROFILE by device-classes §9 itself ("dynamic/load-step functions are excluded through device constraints or separate profiles") | an OTDP catalog revision minting the named profile — this family prices its landing then |
| the §B.3 `limiting` state's first renderer-side exercise on real data | the renderer/host §B machinery (already normative) | the first real bench observation of a floor-limited draw — an observation trigger, not a build item |

## 10. Acceptance rules (pre-committed — written before any build output)

Deterministic census over the fixed fixture set (the committed OTDP electronic_load
example, the refusal fixtures, the banked baselines). Denominators named; both kill
directions stated; the underpowered branch named. These rules bind the build agent.

- **A1 — expansion is valid and example-shaped.** `benchweave-sdk derive-ui` on the
  electronic_load example produces a manifest set passing `validate_presentation`,
  with the input page carrying an observation binding, a `time_series` plot over the
  measure slot with `series: numeric_variables`, and 6/6 derived reading tiles
  (2 channels × 3 declared quantities — counts from the derivation, never literals).
  Kill: any count off, any validation failure, or a tile variable not traceable to a
  (channel, quantity) pair.
- **A2 — the gate passes with the birth deviations REPORTED.** `verify-ui` on the
  example exits 0 with REPORTED (not silent) deviations for `configure`
  (preset-mediated) and `output` (the directional deviation), and censuses on the
  input page: `reading-tile` 6/6, `data-table` ≥1, `engineering-plot` 1/1, `panel`
  `{n_pages}`, `mode-banner` per page; configuration page: the settings data-table.
  Kill: any census delta, any undeclared divergence, or the measure action uncovered
  (`classref_gate_uncovered`) — the L4 test must cover it via the plot figure.
- **A3 — the mockup-consistency arm (the namesake).** §6's arms 1–7 over
  `class-electronic_load.html` × the reference × the example, with the count kill
  both ways and the count-conserving-move kill demonstrated RED (a hook moved to the
  staged-draw control card or out of its container reds while counts conserve).
  **The falsifier: any disagreement between the mockup's counts or placements and the
  resolved expectation; a mockup edit that does NOT redden the test is the instrument
  failing — reported, never a pass.**
- **A4 — RED control (banked at design time, executed this pass).** On the branch head
  `c64f3d05`: gateway-side `select_references` on the electronic_load example →
  `None`, with dc_psu and logic_analyser resolving (§6 arm 6's recorded execution;
  class-dmm absent, consistent with the batch state). The slice greens the
  electronic_load half only. Kill: either control half green before its landing
  commit exists.
- **A5 — the predecessors are untouched.** `class-logic_analyser.json` and
  `class-dc_psu.json` byte-identical through the slice (sorted-key diff = empty);
  `class-dmm.json`/`class-oscilloscope.json`/`class-function_generator.json`
  byte-identical from the moment they exist on the branch; the only prior-test motion
  is the shared-census import (assertions byte-identical); the L11/L12 (/L13/L14 when
  present) test modules re-run green. Kill: any byte beyond the disclosed motions, or
  any prior acceptance rule flipping.
- **A6 — D2 census on the load reference.** No numeric literals outside the structural
  set (spans ≤12, plot indices); no data strings — no values, units, channel names,
  quantity names, **and no mode enum values (`cc`/`cv`/`cr`/`cp` appear nowhere in the
  reference — the mode is descriptor-side configuration data)**. Machine-checked
  census. Kill: any authored data string.
- **A7 — corpus and version gates.** `benchweave.standards check` clean; `repin`
  writes exactly ONE new row (`class-electronic_load.json`) and moves ZERO existing
  rows' digests (no schema edit exists in this slice — the strictest form of the L12
  A7), with ZERO frozen-row rewrites (every 0.2.0/0.1.0 row byte-identical); `matrix
  --check` clean; the served set and range unchanged. Kill: any row motion beyond the
  one addition, or any frozen-row motion.
- **A8 — the direction pin (this record's own arm).** §6 arm 8's assertions hold over
  the committed reference, and each RED demonstration fires: control → `"button"`
  reds; control → `"staging"` reds; the forbid id dropped reds. **Kill (the
  falsifier the dispatch's safety question deserves): any of the three mutations
  passing — which would mean the class's directional ruling is not actually pinned,
  and the dangerous misread is available to the next editor without a red.**
- **A9 — order gates.** The batch's #408 order held (ui-html release → SDK PR →
  release cut → pointer advance in one commit → merge on the full rollup); this
  slice's own legs (no push, no PR, no SDK sync at design time) respected. Kill: any
  inversion, or a merge with red/pending lanes.

**Underpowered branch:** if the input page cannot be composed from §E.1 partials the
renderer already ships (the claim is strong — it IS dc_psu's composition), that
falsifies §4's widening answer and the finding comes back with evidence, priced then,
never silently absorbed. If the expander's treatment of the conditional
`host_supplied` field promotes a control for `output` (§3's named verification), the
deviation posture is falsified at build — the fix lands inside the batched SDK
widening and the finding is re-disclosed on the PR. If the census cannot key on
contract surfaces the preview host emits, that is an instrument failure — reported,
not a verdict.

## 11. Review tier and Step-1 keyword scan

Tier 3 — touches `standards/` (a corpus row); rides a batch that edits JSON Schema
and advances the submodule pointer; diff text carries `sha256` (the corpus row,
sync/fixture tests, this record). Two-lane adversary pass and the standards-governor
lane mandatory. **The refute lane's first question is written for it: attack §1's
directional ruling — the finding that would matter here is a corpus or contract
citation classifying engage as ungated; the design's claim is that none exists in the
tree (§1's three corroborations are the searched space).**

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~8–15 | 1 new corpus row, sync/fixture tests, this record |
| `hashlib` | ~2–4 | SDK derivation tests |
| `protection` | ~3–5 | this record's §C.1 prose and the direction-pin test's naming; zero in production code (the load's protective surface is the §C.1 slice's, disclosed) |
| `threading` / `asyncio` / `subprocess` / `migrate` / `recovery` | 0 | in-process render; derivation, not migration |

## 12. Top risks, each with its falsifier

- **R1 — the directional ruling is wrong.** The design's strongest risk: §1's reading
  of §C.1 is this record's own construction (substance-side R-ENERGISE-1, letter-side
  neither). Falsifier: the refute lane or the owner producing a citation that reads
  "energy-removing" as drain-from-DUT (making engage the ungated action) — the corpus
  search this pass found the opposite in three independent places (the conditional,
  §3's token asymmetry, §9's sign convention). If the owner rules otherwise, the
  reference change is one controls value plus one cannot_derive row — and A8 makes
  that change a visible red, by design.
- **R2 — the expander promotes an output control from the conditional field.** §3's
  named build-time verification; falsified by `derive-ui` emitting any control surface
  bound to `output`; the fix is inside the batched widening.
- **R3 — the batch window closes before the corpus lands.** L12's promotion leg merges
  first → the in-window option is gone → the fallback pricing is the L13 §1
  arithmetic: class-only = PATCH 0.3.1, G-5-gated on the 0.3.0 SDK leg. Legal but
  more expensive; the standing recommendation is the L13 one — land the corpus on the
  stacked branch before the batch's promotion leg.
- **R4 — mockup drift.** Intended: the mockup is the spec; edits force re-derivation
  and the census reds (A3).
- **R5 — public-repo discipline.** `ELOAD-01` and every fixture name invented; no
  real bench, vendor or corpus identifier (paid at authoring, not audited later).
- **R6 — L14 same-window adjacency.** The function_generator lane designs in parallel
  and shares three prose files' vicinities (README files table, styleguide index,
  class-page rows). Stacking order (L14 before L15) resolves adjacent-line edits;
  falsified only by an out-of-order same-file landing, which is rebase-level, not
  semantic. The design-level interface is named: neither slice's schema answer depends
  on the other's (the load widens nothing; whatever L14 needs is L14's motion).
- **R7 — the §B.3 observation is mistaken for a commitment.** §2 records `limiting`
  as an observation with no surface authored; if review wants it painted, that is a
  mockup-local edit plus census expectations — no widening either way.

## 13. Row-calls (numbered; the principal alone decides)

- **RC-L15-1 — the direction ruling (§1).** Input-ENGAGE = the staged+confirm
  direction (R-ENERGISE-1's substance: effect, values, target — with the corpus's own
  conditional forcing the values clause); input-DISENGAGE = the one ungated action
  (R-DEENERGISE-1, literally); the misread (drain-from-DUT ⇒ ungated engage) named
  and killed; the §C.1 letter-gap named for the safety-behaviours slice with
  candidate wording recorded, NOT amended here. Recommend ACCEPT.
- **RC-L15-2 — the zero-widening landing.** `class-electronic_load.json` added to the
  unreleased 0.3.0 batch window; one corpus row; no schema/manifest/policy/
  cross-constraints byte moves (§4, §8). Recommend ACCEPT.
- **RC-L15-3 — the direction-pin test arm (A8).** The machine-checkable guard on
  RC-L15-1: the control value, the cannot_derive id, and the forbid id pinned, with
  the two dangerous mutations RED-demonstrated. Recommend ACCEPT.
- **RC-L15-4 — the mockup authored to the example's shape.** 2 channels × 3
  quantities = 6 tiles; no derived fixture (RC-L11-4/L12's ruling, applied); the
  staged-draw control card and the margin alert carry the disclosed placement
  contract from birth. Recommend ACCEPT.

## 14. Precedent map (principle 9)

| L15 surface | in-tree precedent | why it fits |
|---|---|---|
| the directional deviation (`output → "deviation"` + cannot_derive) | dc_psu §2.2 (`output-control`) | the same both-directions action, the same vocabulary wall — L11's §9 deferral row named L15 as its inheritor |
| the in-window zero-widening class landing | L12's §1 four grounds (re-verified, not re-argued) | same unmerged batch, same bump, no new version directory |
| the banked design-time RED pair | L12 §6 arm 6, L13 §6 arm 6 | `select_references` None-for-this / resolving-for-predecessors, executed and recorded |
| mockup authored with hooks + placement from birth | L12 §2 (the codified convention), L13 §2 | the fourth authored mockup; no retrofit debt |
| forbid id carried with class-specific reason | dc_psu (carried), dmm (dropped, with reason), scope (carried, abort-adjacent) | the per-reference authored-data posture — this class carries it with its truest content since dc_psu |
| `host_supplied` structural field names | the analyser's `arm` slot | the gateway-issued token convention, applied to the OTDP conditional |
| the shared-census consumer | `test_classref_dc_psu.py`'s import switch, dmm, scope | the fourth instance of one instrument, not a fork (F1's lesson) |
| the composer + PATTERNS entry riding the batch's ui-html release | F2's bounded-divergence ruling | the load composer lands beside dc_psu's, in `classref.py`'s standing per-class shape |

## 15. Appendix — evidence, disclosures, and the pre-flight record

**Pre-flight (the #181 R2 discipline):** `git fetch origin` ran (the worktree-add
fetch); no open PRs in either repo per the L13 record's same-window check, and no
remote branch has moved since (`origin/feat/l11-dcpsu-classref` still `c64f3d05`).
The parallel lanes this session (L12 build, L13 design, L14 design) are worktree
peers, not remote rivals; the design-level interfaces are §12 R6's.

**Gortex:** AVAILABLE to this subagent — the probe read
(`BenchWeave/.wt/l15-q8n3/standards/plugin-ui-class-reference/0.3.0/class-dc_psu.json`)
succeeded with the worktree-prefixed path, and every named-file source read after it
went through `mcp__gortex__read`/`search` (the search that located ui-contract §C.1
served the rule rows at their exact lines). The PreToolUse hook was active — it
blocked two shell greps on indexed source (both re-served through gortex or the
native Read of non-indexed docs) and attached calibration guidance on the reads. One
`search(operation:"symbols")` call exceeded its deadline and was abandoned (the graph
was busy); the session continued on file reads and the follow-up text search
succeeded. The L12/L13 design records were read from git (`git show` on the branch)
and from the L13 lane's worktree respectively — the latter read-only, no writes
outside `.wt/l15-q8n3/`. No daemon restart, no tracking change.

**Paths read as evidence:** `standards/plugin-ui-class-reference/0.3.0/` (all five
files — the schema in full, the dc_psu reference in full, the README files table);
`standards/standards-manifest.json` (branch + main — the serving-state pair);
`standards/dependency_policy` block (range); `standards/corpus-manifest.json` (the
four 0.3.0 rows and their `source` citations); `standards/cross-constraints.json`
(both family rows); `standards/otdp/0.2.3/device-profile-catalog.json` (the
electronic_load profile entry and all three action schemas — the conditional verified
in the JSON itself); `standards/otdp/0.2.3/device-classes.md` (§1 coverage table,
§2 common contract, §3 lifecycle — the token asymmetry, §9 electronic load in full);
`standards/otdp/0.2.3/examples/class-electronic_load.json`; `docs/internal/
ui-contract.md` (§B.3, §C.1, §C.2, §D — the rules verbatim);
`docs/internal/ui-styleguide.md` (the mockup index line, the dc_psu class-page rows);
`docs/internal/ui-styleguide-workbench-design.md:320` (the sweep order);
`docs/internal/ui-styleguide-mockups/class-dc_psu.html` (in full — the authoring
convention); `.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md` (in full,
addendum and refute fold); `.claude/deep-review/2026-10-19-classref-l12-dmm-design.md`
(in full, from the L12 branch); `.claude/deep-review/
2026-10-19-classref-l13-oscilloscope-design.md` (§0–§6 and the acceptance/idiom
sections, from the L13 lane's worktree — uncommitted at read time);
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` (§7A, §8);
`packages/ui-html/src/benchweave_ui_html/artifacts.py` (the `_check_r_energise` /
`_check_r_deenergise` / `_check_r_protect` bodies, via the search excerpts — the
PSU-direction enforcement shape the §C.1 slice will widen); the A4 execution
(`select_references` over four descriptors on the branch head, recorded in §6).

**Honest disclosures to the dispatch:** (a) the dispatch's grounding was correct on
every point checked — no mockup exists, the OTDP example is at 0.2.3 and canonical,
L11's refute fold is committed at `647af01d`, and the batch's shared context (L12's
series-required, L13's waveform) matched the lanes' records; (b) the dispatch's §C.1
framing — "an energy-REMOVING action is one action and is never confirmed" — needed
the direction settled, not assumed: on a literal drain-from-DUT reading the load's
ENGAGE is the "energy-removing" action, and §1 exists precisely because that reading
inverts the rule; the record rules engage as the confirmed direction and disengage as
the ungated one, with the corpus's conditional as independent corroboration; (c) one
design-time execution beyond reading was performed — the A4 RED pair (`select_references`
`None` for electronic_load with two predecessors resolving on `c64f3d05`) — because a
pre-committed acceptance rule that can be banked before the build should be; it wrote
nothing; (d) the first `git show` of the L12 record captured a truncation banner from
a shell-alias residue (rtk's git-show truncation, live despite the 2026-10-15
unwiring) — the record was re-extracted with `/usr/bin/git` in full; queued as a
ledger proposal (tags: gotcha, tooling).

**Worktree fold note:** this lane's worktree is `.wt/l15-q8n3/` and is removed only
by this lane (`git worktree list` ran before any work — twelve live worktrees
observed, all named peers).
