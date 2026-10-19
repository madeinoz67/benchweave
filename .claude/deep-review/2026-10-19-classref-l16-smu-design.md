# L16 — the sourcing class that measures: `otdp.smu` class reference, the sweep deferred by name (mockup authored)

**Date:** 19 October 2026
**Slot:** L16 of the class-reference train (parent gateway issue #463; program record
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` §7A row L11–L21's
order "L14 function_generator, L15 electronic_load, **L16 smu**, L17 daq … L21 vna",
§8's RC-1 sweep row; verified against the workbench §8 table
(`docs/internal/ui-styleguide-workbench-design.md` §8), where the source-measure unit
follows the electronic load).
**Branch:** `feat/l16-smu-classref`, cut from `origin/feat/l11-dcpsu-classref`
`c64f3d05` (the L11 rebase resolution; the L11 refute fold's motions verified present —
the 0.3.0 cross-constraints row and the 0.3.0 dependency_policy version map entry are
both on this base). The batch context dispatches L16 as designing concurrent with the
L12/L13/L14/L15 lanes; this record assumes the L11→L12→L13 line lands in the same
unreleased-0.3.0 merge window ahead of promotion (the batched-SDK-leg world L12 §7 and
L13 §1 established), and every vocabulary claim below names which landing it depends on.
**Worktree:** `.wt/l16-smu-x9k4/`. Evidence baseline: the branch head `c64f3d05`; SDK
gitlink `9e0449ef` = **v0.16.0** (pyproject verified by the L13 pass; the vendored
classref tree at the pin is `{0.1.0, 0.2.0}` — 0.3.0's SDK leg is the batch's
outstanding promotion, L13 §1's load-bearing fact, unchanged here); plugin-ui 0.4.0
active; plugin-ui-class-reference **0.3.0 active on the branch** (range
`>=0.1.0,<0.4.0`, unreleased; dependency_policy carries both the 0.2.0 and 0.3.0
migration rows; cross-constraints carries both classref rows — F3's retention,
re-verified this pass); OTDP 0.2.3 active; `benchweave-ui-html==0.3.0` published, the
0.3.1 cut ruled by L11's F2 to ride the batched promotion leg. **Binding design
points:** the program record D1–D14 (esp. D2 structure-not-data, D7 run-group safety,
D13 effective capability, D14 coverage and its §2.5 ladder); the L11 record in full
(its §2.2 directional-output verdict names L16 by name: "The same action shape recurs
at L14 function_generator, L15 electronic_load and L16 smu; whatever that slice lands
becomes their surface too"); the L12 record in full (the authored-mockup convention,
the shared census, the E-1 evidence-driven-landing pattern this design invokes for the
sweep); the L13 record in full (the when_declared layout reading, the per-idiom
answers, the waveform arm's "any later waveform class (smu captures …) reuses the same
arm" note); GOVERNANCE's batch rule and G-5 pacing.

## 0. Summary and design thesis

L16 authors the sixth class reference — `class-smu.json`, binding `otdp.smu/1.0.0` —
and authors the mockup it is validated against (there is no `class-smu.html`; the
mockup directory holds the analyser, dc_psu, and the dmm/oscilloscope files the L12/L13
lanes are authoring). The thesis in one line:

> The SMU's birth surface is the PSU's shape worn over a different contract —
> a **third channel role** (`source_measure`), a function-selected source, and a
> five-action optional sweep block — and the sweep block is **deferred by name**, not
> because it is hard but because its dataset is `table`-kind (an expander arm that
> exists nowhere, designed or built), its signature plot is an I-V curve (a kind
> plugin-ui 0.4.0 does not carry at all), and its composition is procedure-owned by
> device-classes §10's own sentence ("continued output requires a separately approved
> enclosing procedure owning that state") — so the class's first slice is
> **zero family-schema surface**, one corpus file, and the honest negative that the
> sweep's presentation is not this slice's to build.

Three grounding facts fix the scope, each verified in the worktree this pass:

1. **The required-three is dc_psu's exact action set over a third channel role, and
   the optional five are a coherent acquisition block.** The profile
   (`device-profile-catalog.json`, `otdp.smu/1.0.0`): `required_actions` =
   configure/output/measure — dc_psu's set verbatim — but over
   `channel_roles: ["source_measure"]`, a role neither `source` (dc_psu) nor `measure`
   (dmm); `optional_actions` = configure_sweep/arm/trigger/fetch/abort, all five
   `lifecycle: "acquisition"` except configure_sweep (`direct`, a second
   configuration action). Device-classes §10 is normative on what makes the class its
   own: configure selects "voltage/current sourcing, signed level, opposite-quantity
   absolute compliance" (compliance units are A when sourcing V, V when sourcing I);
   scalar results include voltage, current and a **compliance_active boolean**;
   sign carries direction (positive delivered, negative absorbed); and the sweep block
   carries its own safety sentence — "completion and successful abort must execute the
   commissioned source-safe transition before releasing control … continued output
   requires a separately approved enclosing procedure owning that state."
2. **The OTDP class example declares all eight actions over two `source_measure`
   channels** (`standards/otdp/0.2.3/examples/class-smu.json`: ch1/ch2, each
   `quantities: [voltage, current, power]`, all eight actions with empty
   `input_constraints`). Per RC-L11-4's ruling it is the canonical expansion fixture
   (F-smu-1). It is sourcing-shaped like the PSU's example — and unlike the analyser's
   committed reference (which slots every action its example declares), a birth smu
   reference that defers the sweep leaves five declared example actions unslotted: the
   FIRST reference in the family whose fixture exercises the vendor_actions coverage
   path for profile-standard optional actions (§3, R2).
3. **Everything the birth surface needs is already in the post-batch vocabulary.**
   With L12's `series`-required settlement and L13's `waveform` member assumed landed
   in the same unreleased 0.3.0: the readings page, the `time_series` plot over the
   measure slot with `series: "numeric_variables"`, the reading-tile/data-table/
   engineering-plot census keys, the preset-mediated configuration page, and the
   `deviation` control value dc_psu coined for its directional output — all ship. The
   measurement model carries `dtype: bool` (compliance-shaped variables are
   expressible) and `dataset.kind: "table"` (the sweep fetch's shape is expressible)
   — the MODEL admits both; the EXPANDER arms and the plugin-ui plot kinds do not
   (§3's widening table). The smu reference authors no schema motion at all.

## 1. The governance answer first: one file, in the open window, no schema motion

**Can `class-smu.json` join the unreleased 0.3.0? Yes — the L12/L13 in-window
grounds, re-verified, carry it.** The train rule batches same-standard changes that
share a merge window into one bump; L11's, L12's and L13's PRs are unmerged and
**zero PRs are open in either repo** (verified this pass: `gh pr list` empty, gateway
and SDK); the 0.3.0 copy step happened once (L11); L14/L15 are designing into the same
window. L16 adds one corpus file to the SAME bump and creates no version directory,
so "never stack a bump on an unmerged bump" is not engaged and G-5 (which governs new
directories — and whose blocking evidence, the outstanding 0.3.0 SDK leg at gitlink
`9e0449ef`, is unchanged) admits nothing else anyway: the batch is the only legal
corpus landing before the promotion leg, exactly as L13 §1 argued. Copy-never-move
protects 0.2.0/0.1.0 (untouched, A7); 0.3.0 is not yet releasable-pinned, so no
digest promise breaks. The window does NOT license any motion touching the two
committed class documents (`class-logic_analyser.json`, `class-dc_psu.json`
byte-identical through this slice, A5) or, when they exist on the branch,
`class-dmm.json`/`class-oscilloscope.json` (byte-identical, A5).

**No schema edit rides this slice — the good result, stated.** L11 widened (the
`time_series` member); L12 tightened (series-required); L13 widened again (the
`waveform` member). L16 widens nothing: the smu's birth surface is expressible in the
vocabulary as the batch leaves it. This is L12's "zero family-schema surface" result,
second application, and stronger — not even a settlement-class schema edit rides
here. The one corpus motion is `class-smu.json` itself (one new row); no manifest,
range, or cross-constraints motion (0.3.0 already active; the range already admits it;
the 0.3.0 cross-constraints row's substance is unchanged — the smu consumes plugin-ui
0.4.0 vocabulary the row already floors).

**The OTDP `smu` example, and how it relates.** Same relationship every sweep slot
holds: `class-smu.json` at 0.2.3 is the canonical expansion fixture (RC-L11-4, fifth
application) — the descriptor the reference expands against in tests and the pattern
page, never a presentation reference. OTDP answers what an smu must admit; this
family answers how the class presents.

**The class-identity question, answered with the falsifier checked (the dispatch's
invitation).** Is the smu too close to dc_psu to justify its own class rather than a
profile? **No — BUILD, on three structural grounds, each machine-checkable:**

- The OTDP catalog is the authority on class identity, and it mints
  `otdp.smu/1.0.0` as a distinct profile with a distinct channel role. The family's
  references bind `profile_id` exactly; a "profile of dc_psu" has no mechanism here.
- The roles do not interoperate: an smu descriptor expanded against the dc_psu
  reference finds zero channels at the `where_role: "source"` slot (the example's
  channels are `source_measure`) and refuses at the channels slot — the same refusal
  arm L12's fixture set pins (`zero measure channels → the channels-slot refusal`),
  run in the other direction. The dc_psu reference is structurally unusable for smu
  descriptors; the classes are not presentation-interchangeable.
- The reference content genuinely differs: the settings surface's effective schema
  (function/level/compliance/sense/range vs the PSU's four fixed quantity fields),
  the compliance-state deviation, the sweep deferral with its vendor_actions birth
  surface, and the sink-adjacent forbid reasoning (§4) — none of which a dc_psu
  profile could carry without becoming the smu reference in fact.

## 2. The mockup (authored — the spec, per the convention's third authored instance)

`docs/internal/ui-styleguide-mockups/class-smu.html` is authored to the dc_psu/dmm
convention — one composition, two `data-theme` sections (light/dark) over the shipped
token set, self-contained, ~13 KB, invented identifiers only (`SMU-01`;
public-repo discipline paid at authoring). The two L11 lessons are built in from
birth, plus the L13 generalization:

- **§E.1 component hooks from birth**: `bw-reading` on the reading `article` cards,
  `bw-alert-bubble` on the alert `aside`, `bw-plot` on the trend `section`,
  `bw-data-table` on the `table` — hooks on their root elements per the mockup
  convention the L11/L12 instruments key on, keying the consistency check on contract
  surfaces.
- **The F1 placement contract from birth**: every hook on its root tag,
  container-scoped hooks inside their containers (`bw-reading` only in the readings
  row, `bw-plot` only in the lower grid), and the staged-source control card carrying
  NO `bw-` hook — a cannot-derive surface must never present as a reading (L13's
  generalization: a non-contract surface must never present as a contract component).

**What a source-measure unit's class page shows, and why** (each element traced to
the class's nature — a source whose terminals are also the meter, so the page's
readings are the output's own live state):

| element | disposition |
|---|---|
| title row + `Controls` button | page chrome/navigation — host territory, as every class |
| readings row: 6 `bw-reading` cards (ch1/ch2 × V/I/P), one carrying the `warning` variant, each with a quality line | **derives**: one reading-tile per (channel, quantity) variable of the `measure` dataset (2 × 3 on the example's shape; the count is an expression at expansion, never the literal 6); severity is runtime observation state — structure renders the variant, data decides it |
| quality lines (`✓ NORMAL · 84 ms`) | observation quality/freshness (§B/ST-4 machinery; runtime data) |
| alert aside: "Compliance active — current held at configured compliance" | **cannot_derive** `compliance-alert` — the condition is the device-reported compliance state, runtime observation data (device-classes §10's compliance_active), not reference structure (§3) |
| lower grid: staged-source control card (`FUNCTION · V SRC / LEVEL 3.000 V / COMP 100 mA / SENSE 2-WIRE`, `PRESET · APPLY REQUIRED` line) | **cannot_derive** `source-settings` — configure is preset-mediated at birth; the function-selected face (source_function + level + opposite-quantity compliance) is configure input schema, rendered at expansion as data; presets are commissioned evidence (A02) |
| recessed trend plot "SOURCE + MEASURE · LAST 60 SECONDS": two traces (ch1 voltage, ch1 current) + a dashed compliance bound | **derives**: one `time_series` plot over the measure slot; one series per numeric scalar variable (the two-trace choice is an author `channel_hints` matter, disclosed — the dc_psu precedent); the dashed bound is **cannot_derive** `compliance-overlay` — a runtime join against the active configuration |
| Channel / Reading / Quality table (6 rows) | **derives**: one `data-table` reading node over the same dataset, one row per (channel, quantity) |
| NO run buttons, NO sweep panel | the honest birth surface: nothing on this page is runnable — the output control is a named deviation (§4) and the sweep block is a named deferral (§3); the mockup paints neither, and the census asserts the absence (§6) |

The layout is the dc_psu ratio — readings 12 raised, trend 7 recessed, table 5
raised — the L12 precedent's reasoning, third application: the smu's difference from
dc_psu is content (the control card's function-selected face, the compliance alert,
the absent output staging), not geometry. The styleguide's mockup index line gains
`class-smu.html`; `docs/internal/ui-styleguide.md` gains the smu class-page row.

**Why no derived fixture this time — the census resolves over the committed example.**
L12 and L13 authored their mockups to the example's shape so no F-…-2 fixture was
needed; L16 does the same with one more move: the five declared sweep actions add
ZERO components to the signature page (they surface via vendor_actions on the Device
features page, which no mockup in the family paints), so the mockup's counts resolve
against the expansion of F-smu-1 directly — 2 channels × 3 quantities = 6 tiles,
1 plot, 1 table — while simultaneously proving the sweep URNs' coverage path (§6
arm 6, A1's second kill direction). The absence of a sweep panel in a mockup whose
fixture declares the sweep is the design's central honesty claim, and the census
makes it machine-checkable rather than asserted.

## 3. The reference, derived from the mockup — and the differences answer

`standards/plugin-ui-class-reference/0.3.0/class-smu.json` — structure-not-data (D2),
the dc_psu posture: authored structural strings only; every count an expression;
every quantity name arriving via the descriptor at expansion.

**Slots** (URNs and inputs verified against the catalog this pass):

| key | kind | resolves |
|---|---|---|
| `channels` | `channels`, `where_role: "source_measure"` | the declared source_measure channels, declaration order (the scope's generic key convention — neither dc_psu's `outputs` nor dmm's `inputs` names a role that both sources and measures) |
| `measure` | `dataset`, action `otdp.smu.measure/1.0.0`, `schema_source: "output_measurement"` | the scalar dataset; one numeric variable per (channel, declared quantity); `x` = the time axis — dc_psu's derivation verbatim |
| `configure` | `configuration`, action `otdp.smu.configure/1.0.0`, `schema_source: "input_schema"` | the settings schema (configuration_id, channel, source_function, level, compliance_abs, sense, range) |
| `output` | `procedure`, action `otdp.smu.output/1.0.0` | the energy toggle — **no derived control at birth** (§4) |
| `vendor_actions` | `vendor_actions` | D14's hook — and, at birth, the honest coverage surface for the five declared sweep URNs on full descriptors (§3.1) |

No `when_declared` slots at birth — the optional five defer as a block (§3.1).
`host_supplied` is empty on every slot: `output`'s `channel`/`enabled`/
`configuration_id` are real caller inputs (the conditional: `configuration_id`
required iff `enabled: true` — same shape as dc_psu's output, verified this pass),
and `measure`'s `channels` resolves from the declared channels (structural).

**Pages** (three, the family's standing count):

1. **Output** (`kind: readings`, `binding_slots: [measure]`, `plot: {kind:
   time_series, over_slot: measure, series: numeric_variables}`) — the mockup's
   composition: readings section (raised, 12), trend section (recessed, 7) carrying
   the plot, table section (raised, 5) carrying the data-table node. The page id and
   title follow dc_psu: the readings ARE the output's live state — the class's
   source-and-measure-at-the-same-terminals nature is the page's whole point.
2. **Configuration** (`kind: configuration`, `binding_slots: [configure]`) — the
   preset-mediated settings surface; `preset_asset_ids: []` at birth (the RC-6
   scaffold rule).
3. **Device features** (`kind: configuration`, `binding_slots: [vendor_actions]`,
   `vendor_features: true`) — D14's placement row, every precedent's shape; on full
   descriptors (the example among them) it carries the sweep URNs.

**expect.components**: `reading-tile` `{n_reading_tiles}` (`per_page: "output"`);
`data-table` `1` (`per_page: "output"`); `engineering-plot` `1`
(`per_page: "output"`); `panel` `{n_pages}`; `mode-banner` `1` per page
(`per_page: "*"`). **expect.controls**: `otdp.smu.configure/1.0.0: "preset"`,
`otdp.smu.output/1.0.0: "deviation"`. `measure` needs no controls row (dataset slots
are page-covered, fetch's own shape). Counter closure names:
`n_source_measure_channels` beside dc_psu's `n_source_channels`, dmm's
`n_measure_channels`, the scope's `n_analogue_channels`; `n_scalar_variables`,
`n_reading_tiles`, `n_pages` shared. Closure discipline is the invariant; exact names
are build detail (L11 §3 item 5's posture, fourth application).

**forbid**: dc_psu's four ids verbatim — `confirm-wrapped-run-action`
(family-generic carry), `color-role-hint-on-lane` and `untraceable-lane-label`
(family-generic carries, both precedents' convention),
`intermediated-energy-removing-action` **CARRIED** (dc_psu's reasoning verbatim and
stronger: the smu owns an energy-removing direction on `output`, AND — when the sweep
block is declared — its `abort` is the source-safe-transition action device-classes
§10 itself names, so the intent declaration arms the safety-behaviours slice for a
class whose stop-path is energy-adjacent twice over; dmm's drop reasoning cannot
apply).

**cannot_derive** (six rows, each traced to a mockup element or a named deferral):

| id | aspect | reason | author_action |
|---|---|---|---|
| `output-control` | the output on/off control | the directional §C.1 presentation (energise stage+confirm naming effect, values and target; de-energise one ungated action) is beyond the per-action control vocabulary; renderer enforcement belongs to the safety-behaviours slice (L11 §2.2's verdict, inherited verbatim) | none until that slice lands; the deviation is REPORTED, never silent |
| `source-settings` | the function/level/compliance/sense/range selection surface | configure is preset-mediated at birth; the function-selected source (source_function + level + opposite-quantity compliance) is configure input schema — data at expansion, never reference structure; presets are commissioned evidence (A02) | author `ui/presets/*.json` via check-preset; the expander emits the scaffold |
| `compliance-alert` | the compliance-active alert | the condition is the device-reported compliance state — runtime observation data (device-classes §10), not a declared channel quantity and not commissioned policy; structure renders the alert variant, data decides it | bench observation; the alert-bubble renders from host-observed conditions |
| `compliance-overlay` | the trend's dashed compliance bound | the compliance value is runtime configuration data; the overlay is a runtime join (dc_psu's `limit-overlay` shape with the smu's own quantity) | host composition where compliance is active |
| `sweep-surfaces` | the sweep configuration, run and results surfaces (configure_sweep/arm/trigger/fetch/abort) | the optional block defers as a unit: the fetch dataset is `table`-kind (an expander arm that exists nowhere — L11 designed scalar, L13 waveform, neither table); the signature I-V presentation needs a plot kind plugin-ui 0.4.0 does not carry (x is a measured variable, not time); the block's composition is procedure-owned (A12; §10's enclosing-procedure clause); the run controls inherit the source-safe-transition disclosure (§4) | the sweep landing slice, on evidence (§9's trigger); until then, declared sweep URNs surface via Device features — REPORTED, never silent |
| `channel-names` | channel names beyond descriptor labels | the descriptor owns channel identity | label channels in the descriptor |

(`presets` is folded into `source-settings`' author_action, the L13 authoring choice,
second application.)

### 3.1 The sweep deferral — the design's load-bearing call, argued

The when_declared seam exists (verified in the 0.3.0 schema) and would admit five
conditional slots tomorrow. Deferring the block anyway is deliberate, on four
grounds:

1. **The fetch dataset has no derivation arm — designed or built.** The expander
   arms this train has specified are `digital_lanes` (string lanes, the analyser),
   `time_series` scalars (L11 §3 item 1), and `waveform` arrays (L13 §5).
   Device-classes §10 pins the sweep fetch's shape: "table data with point index,
   commanded source level, measured voltage/current and compliance_active" —
   `dataset.kind: "table"` in the measurement model (the enum is verified). Slotting
   fetch at birth would author a slot whose expansion behaviour is undefined — the
   exact shape L11's F4 deferral was cut to avoid, one level up.
2. **The signature presentation is beyond the manifest vocabulary entirely.** An
   operator reads a sweep as an I-V (or I-vs-t) curve: x is a MEASURED variable.
   plugin-ui 0.4.0's `$defs.plot.kind` is `["time_series", "waveform",
   "digital_lanes"]` — every kind's x is an axis, not a measured series. The family
   schema following plugin-ui cannot admit what plugin-ui itself lacks; the widening
   chain (plugin-ui first, then this family) is a wall-payment event RC-L5-1's
   batching rule governs, priced when the sweep lands, not speculated now (principle
   9; no descriptor in the registry asks for it — the L12 §4 E-1 evidence argument,
   second application).
3. **The block is procedure-owned by the class contract's own words.** §10: "Arm
   does not authorise an unbounded repeat"; "for a source sweep, completion and
   successful abort must execute the commissioned source-safe transition before
   releasing control … continued output requires a separately approved enclosing
   procedure owning that state." A12's bounded-procedure machinery (fixed-count
   loops, explicit deadlines, the approved safe transition at every ending) IS the
   sweep's execution model. The class reference presents; the procedure executor
   composes. At birth nothing composes, so nothing presents.
4. **The birth surface stays honest without it.** The vendor_actions slot is D14's
   coverage hook for unclaimed URNs; a full descriptor's sweep actions surface on
   the Device features page — reported, visible, and named by this record as the
   deferred block's waiting room — rather than silently absent. The alternative
   (authoring five when_declared slots whose fetch cannot expand and whose run page
   exists for no registry descriptor) is speculative structure the family's
   per-need-widening discipline exists to refuse.

**The falsifier for this call is pre-committed in A1**: if the gate REFUSES
declared-but-unslotted profile actions despite the vendor_actions slot
(`classref_gate_uncovered` naming any sweep URN over F-smu-1), the deferral posture
falsifies at the coverage layer — the analyser precedent slots everything its
example declares, so the unslotted-optional path is genuinely unexercised in the
family (verified this pass: the LA example declares seven actions, the LA reference
slots seven). The named fallback: the slice's scope grows to whatever the gate
demands — the minimum being when_declared slots for the procedure-shaped actions
(arm/trigger/abort as `procedure` slots, configure_sweep as a second
`configuration` slot) with the fetch question re-priced on the refusal's actual
text — still zero schema motion, disclosed on the PR as a design falsified, never
silently absorbed.

### 3.2 How the smu differs from dc_psu — the differences answer, per axis

The dispatch's question, answered axis by axis: which differences the 0.3.0
vocabulary already expresses, which need a `cannot_derive`, which need a widening.

| difference | disposition | the structural reason |
|---|---|---|
| function-selected sourcing (source_function/level/compliance_abs vs the PSU's four fixed fields) | **expressed, zero motion** | configure is one `configuration` slot either way; the settings data-table renders the effective schema at expansion — field-level shape is descriptor DATA (D2-clean by construction). The surface selection is `cannot_derive: source-settings`, the same preset-mediated birth as dc_psu's |
| measures at the same terminals | **expressed, zero motion** | the readings derivation is identical: one tile per (channel, declared quantity); the example's channels declare [voltage, current, power] and the tiles bind them like any scalar class |
| compliance_active in scalar results | **cannot_derive** (`compliance-alert`) | the measurement model admits the variable (`dtype: bool`, verified) and the numeric series rule structurally excludes bools from trends (a compliance flag is not a trace); the descriptor declares no compliance quantity (the example's `quantities` carry none, `parameter_names: []`), so the derivation never sees it — the honest render path is the alert surface from host-observed state |
| the sweep (five optional actions) | **deferred by name** (§3.1) | slots expressible via `when_declared`; the fetch derivation and the I-V presentation are NOT expressible at any layer (expander arm absent; plugin-ui plot kind absent); composition is procedure-owned |
| sign convention (delivered vs absorbed) | **expressed, zero motion** | signed values are data rendered by the existing tile; no presentation structure depends on sign |
| quadrants (source/sink capability) | **not a reference concern at birth** | §10: "bipolar numbers alone do not prove four-quadrant support" — capability is device-constraint DATA; the sink-side presentation is L15 electronic_load's parallel answer (§4), and no mockup element at birth demands a quadrant surface (an honest negative, recorded, not a cannot_derive) |
| sense wiring (two/four-wire) | **expressed, zero motion** | configure input data; "remote-sense loss must not be hidden" is adapter/gateway behaviour, not presentation structure |

**No widening is requested by this class.** If the build falsifies that (an smu
birth surface the post-batch vocabulary cannot express), the finding comes back with
evidence and is priced then — the disclosed underpowered branch, never silent scope
creep.

## 4. The safety shape: sourcing under §C.1 (and the sweep's own sentence)

§C.1 read in full this pass (the two definition rows and the `confirm-action` row's
contract text). The smu sources, so the energise rules apply, and the class
expresses them exactly as dc_psu did — with two smu-specific wrinkles recorded for
the slices that inherit them:

1. **The output action inherits L11 §2.2's verdict verbatim.** The input schema is
   the PSU's shape (channel + enabled + `configuration_id` required iff enabled —
   verified identical this pass), so it carries BOTH directions with opposite
   presentation rules: L2 staging violates R-DEENERGISE-1's letter for the off
   direction (staging stands between the operator and de-energising); a
   descriptor-derived channel enum promotes the non-compliant render. Birth
   posture: `expect.controls["otdp.smu.output/1.0.0"] = "deviation"` +
   `cannot_derive: output-control`, REPORTED, never silent. The deviation is
   downgradable in today's ledger (the D7 slug set names only `abort` — verified at
   L11) which is correct: it names a missing surface, not a downgraded safety
   reachability. The hand-author risk (an overlay staging the output in both
   directions) is disclosed in the UI-GUIDE text and left to §C.1's enforcement
   slice — the handoff L11 recorded with L16 named in it.
2. **The energise confirm's values are function-dependent — recorded for that
   slice.** R-ENERGISE-1(ii) demands the confirm state "the exact values to be
   applied, with value and unit". On a PSU the values are the configured V and I.
   On an smu the pair the operator must read is selected by `source_function`:
   level in V with compliance in A when sourcing voltage, the transpose when
   sourcing current (device-classes §10's units rule). This is a confirm-text
   derivation against the active configuration — runtime data, the same join class
   dc_psu's confirm will need — but the safety-behaviours slice's smu arm must pair
   the units by function or the confirm names the wrong quantity. Disclosed here as
   the slice's input, not solved by parallel machinery (principle 9).
3. **The sweep's own safety sentence — the deferral's second reason.** §10:
   completion and successful abort of a source sweep "must execute the commissioned
   source-safe transition before releasing control; they cannot simply stop
   collecting data while leaving an unowned output active." The sweep's stop-path
   is therefore energy-adjacent in a way the scope's abort never is: presenting run
   controls for it is a step beyond presenting an output toggle, and the honest
   order is the §C.1 enforcement slice first (or together), not a birth run panel
   the D7 slug set cannot yet reason about. The forbid carry (§3) and the
   `sweep-surfaces` deferral row both point at this.
4. **In-place live reconfiguration stays refused** (§3 of device-classes: source
   configuration requires an approved non-energised/safe transition; the gateway
   sequences disable → configure → verify → enable) — which is WHY configure is
   preset-mediated and the staged-source card stages intent only. Same as dc_psu;
   carried by the `source-settings` deviation.
5. **The L15 coordination point.** The sinking side (quadrants, absorbed-power
   presentation) is the electronic_load lane's parallel answer; this reference
   takes no position on sink presentation beyond the signed-data note (§3.2), and
   the shared directional-control deferral home (the §C.1 safety-behaviours slice)
   is the coordination seam — whatever L14/L15/that slice land, the smu's
   `output-control` deviation downgrades into it. No dependency either way at
   birth; both classes' references are valid independently.

## 5. The five display idioms (RC-L5-1): none land at L16 — the honest negatives, fourth application

L13 answered per idiom; this record applies the answers and records one nuance.

| idiom | verdict | the structural reason |
|---|---|---|
| the waveform canvas | **AVAILABLE, NOT EXERCISED** | L13 landed it class-generic and named "smu captures" among the future reusers — but the birth smu plots no waveform: `measure` is a scalar time series and the sweep's table fetch defers (§3.1). The arm sits ready for the sweep landing; exercising it is that slice's evidence, not this one's. Recorded so the reuse path is on the record, not lost |
| the capture-context strip | **HONEST NEGATIVE** | §E.2.5's acquisition disclosure rides decimated captures; the birth trend is live scalars — nothing is decimated, no strip renders |
| the cursor and trigger markers | **HONEST NEGATIVE** (deferral extended by name) | no canvas cursor surface at birth; the host-knowledge seam stands. The sweep's I-V curve will want cursors — named in the `sweep-surfaces` deferral's home, alongside L13's marker sub-row candidate for the next wall-payment event |
| the grouped label column / position badges | **HONEST NEGATIVE** | lanes-shaped machinery; the smu has no lanes (third application of L13's reasoning) |
| the annotation-chip rows | **HONEST NEGATIVE** | decode-shaped content source; the smu profile has no decode action |
| ("derived frequency" — the handoff's fifth) | **HONEST NEGATIVE** | the example's power tile binds a DECLARED quantity (L11 §2.4's exact reasoning, second application); no derived variables are declared, and §E.2.6's provenance machinery is contracted for the day one is |

**No wall-payment bump is called at L16.** The one forward item this class adds to
the eventual bump's queue — the xy/I-V plot kind the sweep presentation needs — is
named in §3.1 and §9 with its plugin-ui-first chain, priced when the sweep's
evidence fires.

## 6. The A3 extension — the shared census, fourth instance, with the count-conserving-move kill

`tests/ui_html/test_classref_smu.py` extends the shared instrument
(`tests/ui_html/classref_census.py`, landing with the L12 build — the fourth
importer; if the L16 build runs before that lift exists, the lift is this slice's
disclosed mechanical motion on the L12 terms). The arms, the L12 seven with this
class's own:

1. **Hooks in both themes** — every hook family ≥1 per theme section: `bw-reading`
   (6 cards), `bw-alert-bubble` (1), `bw-plot` (1), `bw-data-table` (1).
2. **Hook counts EQUAL the resolved expectation over the committed OTDP example**
   (F-smu-1: 2 channels × 3 declared quantities = 6 tiles, 1 plot, 1 table; panel
   3 = `{n_pages}`; mode-banner per page — the census may assert the per-page
   families on the signature page the mockup paints). Both kill directions by
   construction: a mockup edit that changes a count reds against the resolved side;
   a reference edit that changes the derivation (a count expression, the plot
   binding, the channels slot's role) reds against the mockup's counts. A mockup
   edit that does NOT redden the test is the instrument failing — report, never a
   quiet pass.
3. **Placement, including the count-conserving-move kill**: every hook occurrence
   on its root tag (`bw-reading` → `article`, `bw-alert-bubble` → `aside`,
   `bw-plot` → `section`, `bw-data-table` → `table`), the container-scoped hooks
   inside their containers (readings row, lower grid), and the staged-source
   control card carrying NO `bw-` hook. The RED arms move a hook
   count-conservingly — a `bw-reading` onto the control card; a `bw-plot` out of
   the lower grid — and the placement assertions red while the count arm stays
   green under the move; the reverse-plant (a `bw-` class planted on the control
   card's preset line) reds too. The mutations are demonstrated to kill, not
   assumed.
4. **Theme-invariance** — the census is identical across themes.
5. **The alert is one per theme and a named cannot_derive** (`compliance-alert`).
6. **Selection RED-to-green, banked at design time this pass (executed, recorded)**:
   gateway-side `select_references` over the worktree corpus returns `None` for the
   smu example while `class-dc_psu` → `['otdp.dc_psu/1.0.0']` resolves (and
   `class-oscilloscope` → `None`, consistent with the L13 build's pending state on
   this head `c64f3d05` — the head predates it). The slice greens the smu half
   only.
7. **The sweep-absence arm (this class's addition to the instrument)**: the
   expansion of F-smu-1 over the birth reference carries NO sweep-derived
   component — no button, no second plot, no run panel — and the five sweep URNs
   resolve under the vendor_actions coverage (the Device features page). Kill (the
   deferral's falsifier, pre-committed): any sweep URN surfacing as uncovered
   (`classref_gate_uncovered`), or any sweep-derived component appearing on the
   signature page. This arm is what makes §3.1's honesty machine-checkable.
8. **The pattern-page arms** (the drift guard over the smu composer): tiles 2 × 3
   derived from the corpus pair, never literals; labels are corpus strings (channel
   labels × quantities); one plot with the channel traces; the table's body one row
   per pair; the sections mirror the reference layout block's surfaces and spans;
   only §E.1 partials compose; no control surface fabricated (no button, no rotary,
   no confirm — the staged-source card is mockup-only and the composer paints
   none of it); the PATTERNS census entry is `kind: class-page`, `row_id:
   plugin-ui-class-reference::class-smu`, `fixture_id: readings`; both themes
   export.

## 7. Choreography — riding the batch

1. **Gateway branch content** (this slice): the §8 corpus motion + this record +
   the census module + the composer + PATTERNS entry + the mockup + the styleguide
   rows. Stacked on the L11/L12/L13 line (`feat/l16-smu-classref`; the base is
   `c64f3d05` today and the L13 head when it exists — the batch context dispatches
   L12/L13 to land in the same window, and this design depends on nothing later
   than the vocabulary they widen). The branch-internal sync-pair reds the batch
   disclosed continue until the promotion's pointer leg (never merged red).
2. **SDK side: counter names only** (`n_source_measure_channels` in the
   `_EXPECT_NAMES` closure; the smu fixtures — F-smu-1 the committed example, the
   refusal fixtures: zero source_measure channels → the channels-slot refusal;
   absent required action → `classref_required_action_absent` naming
   `otdp.smu.measure/1.0.0`). These fold into the batched SDK widening (the L12 leg)
   at zero marginal version cost — the same fold L13 designed for its waveform arm.
   No smu-driven release, no ui-html motion of its own: the smu composer +
   PATTERNS entry ride whatever ui-html release the batch cuts (F2's
   bounded-divergence ruling, third application).
3. **The batch's #408 order stands** for the promotion as a whole: ui-html release
   → SDK PR → release cut → pointer advance (gitlink + `.gitmodules` pin + mirror +
   matrix in one commit) → merge on the full rollup (`scripts/merge-verified.sh`),
   zero fail, zero pending.
4. The standards tripwire fires by design (non-empty `standards/` diff); this
   record is the named sanction. Standards-governor lane mandatory; two-lane
   adversary pass on the built slice, explicitly invited to kill §3.1's deferral
   (R2) and the four-id forbid carry (R4).

## 8. Corpus-motion census (exact bytes)

Gateway repo, `standards/`:
- **Added** `standards/plugin-ui-class-reference/0.3.0/class-smu.json` — one new
  corpus row, `source` citing the authoring staging path
  `docs/plugin-ui-class-reference-v2/class-smu.json` (removed in-PR — the founding
  convention `class-dc_psu.json`'s row set, fourth application).
- **Unchanged**: `class-reference.schema.json` (the zero-widening result, §3.2),
  `layout.schema.json`, `standards-manifest.json`, `dependency_policy` (range
  already `<0.4.0`), `cross-constraints.json` (both classref rows stand; the 0.3.0
  row's substance is unchanged), the four committed class documents
  (`class-logic_analyser.json`, `class-dc_psu.json`, and — when on-branch —
  `class-dmm.json`, `class-oscilloscope.json`: byte-identical, A5), every
  0.2.0/0.1.0 byte (zero frozen-row rewrites, A7).
- **Unpinned prose**: the family `README.md` files-table row;
  `docs/internal/ui-styleguide.md` (the smu class-page row; the mockup index line
  gains `class-smu.html`).

Gateway repo, docs/tests (no corpus impact):
`docs/internal/ui-styleguide-mockups/class-smu.html` (new, prose-adjacent — no
corpus rows, no governance event); `tests/ui_html/test_classref_smu.py` (the
shared-census fourth instance).

`packages/ui-html`: the smu composer + PATTERNS entry (rides the batch's ui-html
release).

SDK (inside the batched leg): the counter name + the smu fixtures + the vendored
0.3.0 ingest picking up the new class file. **No otdp motion of any kind.**

## 9. Deferrals, each with a home and an observable reopen trigger

| defers | home | reopen trigger |
|---|---|---|
| the sweep block: five `when_declared` slots, the run surface, the `table`-dataset derivation arm, the I-V presentation | the sweep landing slice (its own design record); the I-V plot kind's chain is plugin-ui first, then this family (RC-L5-1's batching rule) | the first real admitted smu descriptor declaring any of the five; or the owner calling the sweep surface; or A1's falsifier firing (the gate refusing the vendor_actions birth surface — §3.1's named fallback). §10's own advertising rule (configure_sweep ⇒ arm/fetch/abort) is the coherence constraint that landing must honor |
| the directional output control (both classes' shared shape) | the §C.1 safety-behaviours enforcement slice + the family vocabulary widening in the next wall-payment event (L11's deferral row, L16 named in it) | that slice landing; L14/L15 landing the same toggle shape first changes nothing but the order the shared surface arrives |
| the function-dependent confirm-text pairing (R-ENERGISE-1(ii)'s values with units by `source_function`) | the safety-behaviours slice's smu arm | that slice's design pass (recorded here as its input, §4.2) |
| the staged setpoint knob idiom (the function/level/compliance face is its prime candidate) | the staging-over-preset capability (L5's batching rule family) | a class whose configure is field-stageable, or the owner calling the smu setpoint surface |
| contract-grade markers/cursors on the sweep's curve presentation | the RC-L5-1 wall-payment event (L13's named marker sub-row candidate, extended to the xy kind when it exists) | the sweep landing needing wire-carried markers |
| quadrant/sink presentation | L15 electronic_load's parallel answer + host composition | L15's landing; a real four-quadrant smu descriptor |
| compliance-state as a declared variable/trend | the descriptor contract (a declared quantity or parameter name) | a real smu descriptor declaring compliance among its quantities — the derivation's first real exercise |

## 10. Acceptance rules (pre-committed — written before any build output)

Deterministic census over the fixed fixture set (the committed OTDP smu example
F-smu-1, the refusal fixtures, the banked baselines). Denominators named; both kill
directions stated; the underpowered branch named. These rules bind the build agent.

- **A1 — expansion is valid, example-shaped, and sweep-honest.** `benchweave-sdk
  derive-ui` on F-smu-1 produces a manifest set passing `validate_presentation`,
  with the output page carrying an observation binding, a `time_series` plot over
  the measure slot with `series: numeric_variables` (required — the L12
  settlement), and 6/6 derived reading tiles (2 channels × 3 declared quantities —
  counts from the derivation, never literals). AND the five declared sweep URNs
  resolve under vendor_actions coverage — no sweep slot exists, no sweep-derived
  component appears, nothing fails. **Kill (both directions): any count off, any
  validation failure, a tile variable untraceable to a (channel, quantity) pair —
  or any sweep URN surfacing as uncovered (`classref_gate_uncovered`), which
  falsifies §3.1's deferral posture and activates the named fallback.** The
  sweep-honesty half is the falsifier the dispatch asked for: it can fire, and its
  firing is a real result (the design's central call, wrong at the coverage layer),
  not a build failure to be quietly patched around.
- **A2 — the gate passes with the birth deviations REPORTED.** `verify-ui` on
  F-smu-1 exits 0 with REPORTED deviations for `configure` (preset-mediated) and
  `output` (the directional deviation), none silent; the census on the output page
  reads `reading-tile` 6/6, `data-table` ≥1, `engineering-plot` 1/1, `panel`
  `{n_pages}`, `mode-banner` per page; the configuration page reads the settings
  data-table; the Device features page carries the five sweep URNs. `measure` is
  covered via the plot figure (the widened L4 arm). Kill: any census delta, any
  undeclared divergence, or `classref_gate_uncovered` naming measure or any sweep
  URN.
- **A3 — the mockup-consistency arm (the namesake).** §6's arms over
  `class-smu.html` × the reference × F-smu-1, with the count kill both ways, the
  count-conserving-move kill demonstrated RED (a hook moved to the control card or
  out of its container reds while counts conserve), the reverse-plant kill
  demonstrated RED, and the sweep-absence arm green. **The falsifier: any
  disagreement between the mockup's counts or placements and the resolved
  expectation; a mockup edit that does NOT redden the test is the instrument
  failing — reported, never a pass.**
- **A4 — RED control (banked at design time, executed this pass).** On the branch
  head `c64f3d05`: gateway-side `select_references` on the smu example → `None`,
  with dc_psu resolving (`['otdp.dc_psu/1.0.0']`) — executed and recorded (§6 arm
  6; oscilloscope → `None` on the same head, consistent with the L13 build's
  pending state). The slice greens the smu half only. Kill: either half green
  before its landing commit exists.
- **A5 — the predecessors are untouched.** `class-logic_analyser.json` and
  `class-dc_psu.json` byte-identical through the slice (sorted-key diff = empty);
  `class-dmm.json` and `class-oscilloscope.json` byte-identical from the moment
  they exist on the branch; the only prior-test motion is the shared-census import
  (assertions byte-identical); the full L11/L12/L13 test modules re-run green.
  Kill: any byte beyond the disclosed motions, or any prior acceptance rule
  flipping.
- **A6 — D2 census on the smu reference.** No numeric literals outside the
  structural set (layout spans ≤12, plot indices); no data strings — no values,
  units, channel names, quantity names, AND no field names from the configure
  schema (source_function/level/compliance_abs/sense/range arrive via the
  descriptor at expansion; the reference authors none of them — the function-
  selected source is §3.2's expressed-with-zero-motion difference precisely
  because the reference never names it). Machine-checked census. Kill: any
  authored data string.
- **A7 — corpus and version gates.** `benchweave.standards check` clean; `repin`
  writes exactly ONE new row (`class-smu.json`) with ZERO existing-row digest
  motions and ZERO frozen-row rewrites (every 0.2.0/0.1.0 row byte-identical);
  `matrix --check` clean; the served set and range unchanged; both cross-constraints
  classref rows standing. Kill: any frozen-row motion, any digest motion (a digest
  motion would mean a schema edit rode along — the zero-widening claim falsified),
  or an unexpected row count.
- **A8 — order gates.** The batch's #408 order held (ui-html release → SDK PR →
  release cut → pointer advance in one commit → merge on the full rollup); the
  branch's sync-pair reds go green at the pointer leg and not before. Kill: any
  inversion, or a merge with red/pending lanes.

**Underpowered branch:** if the census cannot key on contract surfaces the preview
host emits, that is an instrument failure — reported, not a verdict. If the build
reveals a birth-surface component the post-batch vocabulary cannot express (§3.2's
claim falsified), the widening is priced on the evidence and the claim's falsity is
the finding — never silently absorbed. If A1's sweep half fires, §3.1's named
fallback activates with its scope re-priced on the refusal's text.

## 11. Review tier and Step-1 keyword scan

Tier 3 — touches `standards/`; rides a batch that advances the submodule pointer;
diff text carries `sha256` (one corpus row, sync tests, this record). Two-lane
adversary pass and the standards-governor lane mandatory.

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~8–15 | 1 new corpus row, sync/fixture tests, this record |
| `hashlib` | ~0–2 | none gateway-side; the SDK legs ride the batch's own tests |
| `protection` | ~1–3 | this record's §C.1 prose only; zero in code (the smu's only protective-adjacent surface — the sweep's abort — is deferred, the honest note) |
| `threading` / `asyncio` / `subprocess` / `migrate` / `recovery` | 0 | in-process render; derivation, not migration |

## 12. Top risks, each with its falsifier

- **R1 — the timing dependency (the batch assumption).** This design assumes the
  L12/L13 corpus edits (series-required; the waveform member) land in the same
  unreleased 0.3.0 window before promotion. If the batch merges before L16's corpus
  lands, the landing reprices per L13 §1's fallback arithmetic (class-file-only =
  PATCH; any later smu-driven schema motion = its own MINOR — but §3.2 claims there
  is none, so the fallback is the PATCH alone). Falsified by checking branch state
  at build start; recorded for the coordinator, not enforceable here.
- **R2 — the sweep deferral is wrong at the coverage layer.** The analyser
  precedent slots every action its example declares; the unslotted-optional path is
  unexercised. If the gate refuses declared-but-unslotted profile actions despite
  vendor_actions, A1 fires and §3.1's fallback activates. Falsified by A1's
  sweep half — the design's central claim put where a test can kill it.
- **R3 — the vendor_actions birth surface is honest but too thin.** Review may hold
  that profile-standard optional actions presenting as "Device features" misleads
  an operator reading the page (they are not vendor extensions). The counter is
  that D14's row is the family's unclaimed-URN hook and the deferral is REPORTED in
  the reference itself (`sweep-surfaces` names the waiting room); if the owner
  still holds it too thin, the fallback is R2's, not a third path. Falsified by the
  adversary lane or the owner at the row-call.
- **R4 — the four-id forbid carry is wrong for the sweep-deferred class.** If
  review holds `intermediated-energy-removing-action` vacuous while the sweep
  (whose abort is the energy-adjacent one) is deferred — the energy-removing
  direction DOES exist on `output` (dc_psu's verbatim ground), so the carry is
  defensible either way; the drop is a one-line edit with the recorded-reason
  method. Falsified by the adversary lane or the owner.
- **R5 — mockup drift.** Intended: the mockup is the spec; edits force
  re-derivation and the census reds (A3).
- **R6 — public-repo discipline.** `SMU-01`, the mockup's invented values, and
  every fixture name invented; no real bench, vendor or corpus identifier (paid at
  authoring — the mockup's `3.000 V / 100 mA` faces are the dc_psu `12.5 V`
  convention, disclosed).
- **R7 — the shared-census import races sibling lanes.** L12 owns the lift; if the
  L16 build runs first the lift is its disclosed motion; concurrent modification
  is the dev-stage rule's ordinary merge resolution (L13's R7, verbatim). Falsified
  by CI; mitigated by byte-identical assertions by design.

## 13. Row-calls (numbered; the principal alone decides)

- **RC-L16-1 — the sweep deferral.** Defer the five optional actions as a block
  (vendor_actions birth surface, `sweep-surfaces` cannot_derive, A1's falsifier
  armed, the named fallback recorded). Alternative: author five `when_declared`
  slots now — rejected: the fetch cannot expand (no table arm), the signature plot
  is beyond plugin-ui's vocabulary, the composition is procedure-owned, and no
  registry descriptor asks for it. Recommend ACCEPT the deferral.
- **RC-L16-2 — zero schema motion.** The birth surface is expressible in the
  post-batch vocabulary unchanged; this slice adds one corpus file and nothing
  else to `standards/`. (No alternative exists unless the build falsifies §3.2 —
  the underpowered branch.) Recommend ACCEPT as the recorded result.
- **RC-L16-3 — no derived fixture.** The census resolves over the committed
  example F-smu-1 because the declared sweep actions add no signature-page
  components; the mockup is authored to the example's channel shape (2 × 3).
  Alternative: an L11-style F-smu-2 minimal descriptor — rejected as unnecessary
  (the counts coincide). Recommend ACCEPT.
- **RC-L16-4 — the four-id forbid carry** (§3), `intermediated-energy-removing-
  action` included on the output-direction ground with the sweep-abort adjacency
  noted for the deferral's landing. Alternative: dmm's three-id drop. Recommend
  ACCEPT the carry; the refute lane is explicitly invited to kill it (R4).

## 14. Precedent map (principle 9)

| L16 surface | in-tree precedent | why it fits |
|---|---|---|
| class file added to an in-window unreleased bump | the batch rule (GOVERNANCE), L11's addendum motions, L12 §1, L13 §1 | same train, same bump, no new version directory — fourth application |
| zero-widening class landing | L12's dmm ("zero family-schema surface") | the same result class, stronger: not even a settlement edit rides |
| mockup authored with hooks + placement from birth | L12's `class-dmm.html` design, L13's `class-oscilloscope.html` | the convention's third authored-from-birth instance |
| optional-action block deferred on evidence | L12 §4's E-1 analysis (the frequency-counter criterion) | the evidence-driven-landing pattern, applied to a block instead of an action |
| unclaimed URNs covered by vendor_actions | D14's placement row (every committed reference carries the slot) | first exercise with declared profile-standard optionals — the falsifier armed (A1) |
| directional output deviation, REPORTED | L11 §2.2 (dc_psu) | the verdict inherited verbatim; L11's deferral row names L16 |
| counter names role-generic per class | `n_source_channels` (L11), `n_measure_channels` (L12), `n_analogue_channels` (L13) | `n_source_measure_channels`, fourth in the set |
| shared census fourth instance | `classref_census.py` (L12 §6's lift) | the instrument must not fork between classes (F1's lesson) |
| per-class composer in `classref.py` | `render_capture_page`, `render_output_page`, the dmm/scope composers | the module's standing shape, sixth instance |
| expansion fixture = the OTDP class example | RC-L11-4's ruling | fifth application; no derived fixture (RC-L16-3) |

## 15. Appendix — evidence, disclosures, and the pre-flight record

**Pre-flight (the #181 R2 discipline):** `git fetch origin`; `gh pr list` — **zero
open PRs in the gateway repo and zero in the SDK repo** this pass. `git worktree
list` run before any tree action; the sibling lanes' trees (`l11-x7q9`, `l12-d4m9`,
`l12b-k7q2`, `l13-t4k9`, the designer/land159 trees) untouched — this lane's tree is
`.wt/l16-smu-x9k4`, created off `c64f3d05` as dispatched. No remote branch touches
`standards/plugin-ui-class-reference/`, the mockups, or the sweep beyond the L11
line this design stacks on.

**Gortex:** AVAILABLE to this subagent — the probe read
(`BenchWeave/.wt/l16-smu-x9k4/standards/otdp/0.2.3/examples/class-smu.json`) was
served with the worktree-prefixed path; source reads went through `mcp__gortex__read`
(ui-contract in full, the dc_psu reference, the family schema, `select_references`
source). The PreToolUse hook was active (it blocked two shell greps on indexed
source — the ui-contract heading scan and the programme-record row scan — both
re-served, the first through gortex, the second through native Read at known
offsets); JSON extraction over the 136 KB catalog ran through `python3 json.load`
(data processing on a gortex-served file's path, no text search). Session start
reported checkout discovery `view_building, retryable=true`; it cleared within the
first reads. No daemon restart, no tracking change.

**Design-time execution beyond reading (one, disclosed):** the A4 RED pair —
`select_references` run in the primary checkout's venv with the corpus path pointed
at this worktree's standards tree (nothing written outside the worktree) — because a
pre-committed acceptance rule that can be banked before the build should be (the
L12/L13 §15 precedent, same reasoning, third application).

**Paths read as evidence:** `standards/GOVERNANCE.md` (via the L12/L13 records'
quotations, re-verified where load-bearing); `standards/standards-manifest.json` +
`dependency_policy` (the classref range `<0.4.0`, both migration rows);
`standards/cross-constraints.json` (both classref rows);
`standards/plugin-ui-class-reference/0.3.0/` (`class-reference.schema.json` in full,
`class-dc_psu.json` in full, `class-logic_analyser.json` slots/actions);
`standards/otdp/0.2.3/device-profile-catalog.json` (the smu profile entry and all
eight action schemas, extracted; the dc_psu output schema, the analyser/
function_generator/electronic_load profile partitions);
`standards/otdp/0.2.3/examples/class-smu.json` (in full), `class-dc_psu.json`,
`class-logic_analyser.json` (actions declared);
`standards/otdp/0.2.3/otdp-measurement.schema.json` (`$defs.dataset` — the
nine-kind enum including `table`; `$defs.variable` — the dtype enum including
`bool`); `standards/otdp/0.2.3/device-classes.md` §3 (the configuration and
acquisition lifecycle) and §10 (Source-measure unit, in full);
`docs/internal/ui-contract.md` (§C.1, §E.1 all 15 rows, §E.3);
`.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md` (in full, addendum
and refute fold), `2026-10-19-classref-l12-dmm-design.md` (in full, from the l12
lane's branch `e4573525` — read-only, the lane's tree untouched),
`2026-10-19-classref-l13-oscilloscope-design.md` (in full, from the l13 lane's
worktree — read-only, uncommitted, the lane's tree untouched),
`2026-10-14-classref-logic-analyser-design.md` (§7A, §8);
`src/benchweave/presentation/classref.py::select_references` (source);
SDK pin state (gitlink `9e0449ef`, the L13 pass's v0.16.0 verification carried).

**Honest disclosures to the dispatch:** (a) the dispatch's grounding held on every
point checked — no smu mockup exists, the OTDP example is at 0.2.3 with
`otdp.smu.configure/1.0.0` and `otdp.smu.output/1.0.0` among its sourcing-shaped
actions (though the example declares EIGHT actions, not two: configure/output/
measure plus the five-action sweep block — the dispatch's "sourcing-shaped like the
PSU" is true of the REQUIRED set, and the optional five are the design's load-
bearing fact); (b) the profile's `channel_roles` is `["source_measure"]` — a third
role, which settles the slot-key naming (`channels`, the scope's generic convention)
and supplies the machine-checkable distinctness argument of §1; (c) the electronic
load profile (L15's class) carries the SAME required-three over its own role — the
two lanes' birth references will be near-isomorphic modulo role and cannot_derive
set, which is the family's per-profile contract working as designed, not
duplication to be deduplicated; (d) the design record is written and left
UNCOMMITTED in this lane's worktree — the dispatch said design only with no push
and no PR, and the commit decision belongs to the coordinator folding the batch.
