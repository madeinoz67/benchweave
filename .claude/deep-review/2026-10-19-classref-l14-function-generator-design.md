# L14 — the pure source: `otdp.function_generator` class reference, nothing widened (mockup authored)

**Date:** 19 October 2026
**Slot:** L14 of the class-reference train (parent gateway issue #463; program record
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` §7A row L14, §8's
RC-1 sweep row; the sweep order L11 dc_psu → L12 dmm → L13 oscilloscope → **L14
function_generator** → L15 electronic_load … L21 vna, verified against §7A and the
workbench §8 table).
**Branch:** `feat/l14-fungen-classref`, cut from `origin/feat/l11-dcpsu-classref`
`c64f3d05` (the L11 rebase resolution; the L11 refute fold's motions verified present:
the 0.3.0 cross-constraints row, the placement-aware dc_psu census).
**Worktree:** `.wt/l14-r9k4/`. Evidence baseline: the branch head `c64f3d05`; SDK
pinned at gitlink `9e0449ef` = **v0.16.0** (tag verified in this lane's initialized
submodule), whose vendored classref tree is `{0.1.0, 0.2.0}` — 0.3.0's SDK leg is
OUTSTANDING (RC-L11-2's batching, to be performed by the L12 batched promotion leg);
plugin-ui 0.4.0 active; plugin-ui-class-reference **0.3.0 active on the branch**
(released 2026-10-18 on-branch, unmerged; main still serves 0.2.0 — verified from the
primary checkout's manifest); OTDP 0.2.3 active; `benchweave-ui-html==0.3.0` published,
0.3.1 ruled by L11-F2 to cut with the batched promotion leg. On-branch family state,
re-derived this pass: **4 corpus rows** for 0.3.0 (three re-stamps + dc_psu), the
manifest's **normative array enumerating all four 0.3.0 machine paths**, **2**
cross-constraints family rows (0.2.0 retained beside 0.3.0, F3's ruling).
**Batch context assumed, not on this base:** L12 (`class-dmm.json`, `series` required
on `time_series`) and L13 (`class-oscilloscope.json`, the `waveform` enum member and
its conditional) land BEFORE this slice on the shared line and are designed, not
committed, at `c64f3d05` — this record designs against their union and duplicates
neither.
**Binding design points:** the program record D1–D14 (esp. D2 structure-not-data, D13
effective capability, D14 coverage and its §2.5 ladder); the L11 record in full
(addendum + refute fold F1–F4 — its §2.2 directional deviation names this slot:
"the same action shape recurs at L14 function_generator, L15 electronic_load and L16
smu"); the L12 record in full (its §1 in-window grounds, its §6 shared census); the L13
record in full (its §1 window analysis — the timing argument this record inherits
sharpened, its §4 idioms answers); the L5 record's RC-L5-1; GOVERNANCE's
bump-minimization train rule and G-5 pacing.

## 0. Summary and design thesis

L14 authors the fifth class reference — `class-function_generator.json`, binding
`otdp.function_generator/1.0.0` — **and authors the mockup it is validated against**
(no `class-function_generator.html` exists; the mockup directory holds the analyser,
dc_psu, and the dmm/scope files the L12/L13 lanes are authoring). The thesis in one
line:

> The function generator is the sweep's first **pure source** — no measurement action
> at all (the profile requires only `configure` + `output`, optionally `upload`) — so
> its class page has **no observation to bind and no dataset to plot**: the reference
> widens **nothing**, authors its smallest document yet (two pages, no layout block,
> zero numeric literals), and the class's operator-recognizable surfaces — the waveform
> preview, the per-channel configured-function cards, the output toggle — are all
> named cannot-derive at the host seam, each for a structural reason this record
> traces to contract text.

Three grounding facts fix the scope, each verified in the worktree this pass:

1. **The OTDP class contract is source-shaped and measurement-free.** The profile
   (`device-profile-catalog.json`, `otdp.function_generator/1.0.0`): required
   `configure`/`output`, optional `upload`, `channel_roles: ["source"]`. The committed
   example declares 2 `source` channels (`ch1`/`ch2`), each `quantities: [voltage]`,
   and all three actions. `device-classes.md` §8 is normative on the physics:
   explicit frequency/amplitude-Vpp/offset/phase/load fields (null load = high
   impedance; "the output convention must state the voltage at that declared load");
   DC is frequency 0, amplitude 0; square/pulse require duty cycle; arbitrary mode
   requires a valid uploaded waveform ID; **"upload does not enable output"**; the
   uploaded dataset is one normalised variable, unit 1, finite values in [−1,1], with
   an explicit sample rate; reset invalidates volatile assets.
2. **The ladder places every action outside the derived-control reach, mechanically.**
   `configure` is L3 (configuration-shaped — the first-match rule; its 8 required
   fields include the `function` enum, a pattern-narrowed `channel`, and conditional
   requirements): preset-mediated at birth, the posture of every precedent.
   `output` requires `channel` (pattern-narrowed — the §E.1 `text-input` row's own
   text: "a pattern-narrowed string is NOT this component") and `enabled` (boolean;
   the §E.1 `boolean-input` row exists since L5, but the boolean is not the blocker):
   **L0**. `upload` requires `channel` (pattern-narrowed), `dataset_id` (a pattern-free
   string — text-expressible) and `sample_rate_hz` (numeric): **L0 via the channel
   field alone**. Both L0 actions take declared deviations at birth; `_derive_controls`
   mints the divergence rows against the `expect.controls` entries
   (`classref.py:596-619`, verified at the pin).
3. **The vocabulary is already ahead of everything this class asks for.** The 0.3.0
   schema admits `when_declared` on procedure slots (the seam L13 exercised for the
   scope's optional `trigger`; `upload` is its second use and the first NON-lifecycle
   optional action). Page kind `configuration` admits procedure bindings
   (`allowed_by_kind["configuration"] = {"configuration", "procedure"}`,
   `classref.py:1114-1118`). The §E.1 inventory ships every component the page
   composes (`data-table`, `alert-bubble`, `panel`, `mode-banner`). The expander is
   class-generic post-L11's widening design; the counter closure already carries
   `n_pages`. Nothing in this slice needs a schema byte, an expander arm, a renderer
   motion, or a gateway runtime motion.

## 1. The governance answer first: one class file inside the open window; the fallback priced

**Can this landing stay inside the unreleased 0.3.0 window? Yes — and it must.** The
L13 record's §1 four grounds hold unchanged for a fourth class (the batch rule's "same
standard, same train, one bump"; G-5's evidence — the branch's SDK v0.16.0 vendored
tree is `{0.1.0, 0.2.0}`, so a NEW version directory is G-5-blocked today regardless
of change class; copy-never-move protects 0.2.0/0.1.0 only, and 0.3.0 is unmerged; the
L11/L12/L13 rulings walked the path). L14's motion inside the window is the smallest
of the train: **one new corpus file, zero schema edits, zero digest motions** — plus
the manifest enumeration append this record adds to the motion census (§8; a finding
the L12/L13 records missed — their "standards-manifest.json unchanged" lines are
incomplete, and their builds must append their class paths to the normative array
too, or `benchweave.standards check` reddens on the directory/manifest disagreement).

**The timing dependency, sharper than L13's.** After the batch's promotion leg merges,
0.3.0 is released and frozen; adding `class-function_generator.json` to it is then
corpus motion on frozen bytes — refused (`content_drift_without_version`) — and the
fallback becomes an additive-errata **PATCH 0.3.1** with its own SDK ingest leg
(L11 §1's Shape-B arithmetic: legal, strictly more expensive, two version events
where the batch needed one). So the landing order within the batch is load-bearing:
**L14's corpus commit lands on the stacked line before the batch's pointer leg**,
joining the files the batch's SDK vendored ingest picks up. If the window is already
closed when the L14 build runs, the design does not force it open — the fallback is
priced above and the row-call records the sequencing recommendation (RC-L14-1).

**The OTDP example, and how it relates.**
`standards/otdp/0.2.3/examples/class-function_generator.json` is the canonical
expansion fixture (RC-L11-4's ruling, fourth application): 2 `source` channels ×
1 declared quantity, all three actions declared with empty `input_constraints`,
contracts pinning the catalog and the measurement schema. OTDP answers what a
generator must admit; this family answers how the class presents. Like dmm and the
scope (and unlike dc_psu), **no derived fixture is needed** — the mockup is authored
to the example's own shape, so the A3 census resolves over the committed example
directly. One derived-in-test fixture DOES exist for the when_declared arm (A8): the
example minus its `upload` action, derived in-test — the descriptor shape a real
generator without arbitrary-waveform support presents.

## 2. The mockup (authored — the spec)

`docs/internal/ui-styleguide-mockups/class-function_generator.html`, authored to the
dc_psu/dmm convention: **one composition, two `data-theme` sections** (light/dark) over
the shipped token set, self-contained, ~13 KB, invented identifiers only (`FGEN-01`,
`Reference channel 1/2`; public-repo discipline paid at authoring). The L11 lessons are
built in from birth — §E.1 component hooks on their root elements only, the F1
placement contract, and L13's extension: **idiom surfaces that are not contract
surfaces carry NO `bw-` hook at all**.

**Which page the mockup composes — the decision this class forces.** Every prior
mockup composed the class's primary DATA page (dc_psu output/readings; dmm readings;
scope capture). The generator has no data page: no measurement action exists, so no
observation binds, no plot template can name an over-slot, and §C.1's directional
split (L11 §2.2, inherited verbatim — see §3) bars the output control from deriving.
The mockup therefore composes **the Configuration page** — the one page whose content
derives — and carries the class's operator idioms around it as hook-less surfaces.
This is not a demotion; it is the class's honest structural statement: a pure source
presents mostly intent, and the mockup says so in its hook distribution.

**The composition** (the dc_psu geometry, re-weighted to the class's ontology):

| element | disposition |
|---|---|
| title row + `Controls` button | page chrome/navigation — host territory, as every class |
| function cards row: 2 per-channel cards (`Reference channel 1 · SINE · 1 kHz · 2.5 Vpp · +125 mV · 50 Ω · OUTPUT ON`; channel 2 square, output off) | **cannot_derive** `function-summary` — configuration echo, not observation. The contract's own `reading-tile` row bars this surface: "do not optimistically copy a requested value into an applied reading." These are REQUESTED values; presenting them as readings would be exactly that lie. **NO `bw-` hook** — the first sweep class whose summary cards cannot be readings |
| alert aside: "Load convention — voltage is specified at the declared 50 Ω load; high-impedance operation changes the delivered amplitude" (warning variant) | structure **derives** (`bw-alert-bubble`, hooked); the condition is **cannot_derive** `load-convention-alert` — commissioned policy + runtime configuration (A02), dc_psu's `margin-alert` shape with this class's own §8-required case (the output-load convention ambiguity the normative prose names) |
| recessed waveform preview panel: one canvas, two painted traces (the sine and the square), a painted legend with slot colours and dash forms | **cannot_derive** `waveform-preview` — the preview is a runtime join against the effective configuration (standard functions compute from configured values; arbitrary mode needs the uploaded dataset's CONTENT, referenced only by `waveform_id`). NO `bw-plot` hook — L13's rule: a non-contract idiom must never present as a contract component. This panel is where L13's waveform-canvas idiom lands for this class (§4) |
| raised settings data-table: Field / Kind / Notes — `function` (selection), `frequency_hz`, `amplitude_vpp`, `offset_v`, `phase_deg`, `load_ohm`, `duty_cycle` (required when square/pulse), `waveform_id` (required when arbitrary) | **derives** (`bw-data-table`, hooked): the L3 settings surface's field rows, from the effective configure schema (catalog × the example's empty constraints) — field names are corpus strings, resolved at expansion; the mockup's Notes column carries only structural wording ("required when function is square or pulse") |
| preset-preview control card (`FUNCTION · SINE / 1 kHz / 2.5 Vpp`, `PRESET · APPLY REQUIRED`) | **cannot_derive** `function-selection` — configure is preset-mediated at birth; presets are commissioned evidence (A02). NO hook, dmm's own shape |
| staged output control card: the §C.1 directional idiom — the enable arm painted as stage-then-confirm (an armed line naming effect, value and target), the disable arm painted as one ungated action | **cannot_derive** `output-control`, L11 §2.2 verbatim (the deviation this slot was named to inherit). NO hook, no `bw-confirm` — painting the idiom records presentation intent; fabricating the contract component on a cannot-derive surface is the F1-generalized lie |

The layout keeps the dc_psu ratios where they still apply (cards row raised 12, lower
grid recessed-dominant) with one honest inversion: the preview panel takes the
recessed span the dc_psu trend held, and the settings table the raised span — the
class's one derivable dense surface. The styleguide's mockup index line gains
`class-function_generator.html`; `docs/internal/ui-styleguide.md` gains the
function-generator class-page row beside the others.

## 3. The reference, derived from the mockup

`standards/plugin-ui-class-reference/0.3.0/class-function_generator.json` —
structure-not-data (D2), the family posture applied to a pure source: authored
structural strings only, **zero numeric literals** (no layout block, no plot, no
spans), every count an expression, every field name arriving via the catalog at
expansion.

**Slots** (URNs and inputs verified against the catalog and the action schemas this
pass):

| key | kind | resolves |
|---|---|---|
| `outputs` | `channels`, `where_role: "source"` | the declared source outputs, declaration order (dc_psu's own key) |
| `configure` | `configuration`, action `otdp.function_generator.configure/1.0.0`, `schema_source: input_schema` | the settings schema (configuration_id, channel, function enum, frequency_hz, amplitude_vpp, offset_v, phase_deg, load_ohm nullable; duty_cycle and waveform_id conditionally required) |
| `output` | `procedure`, action `otdp.function_generator.output/1.0.0` | the energy toggle — **no derived control at birth** (§3.1) |
| `upload` | `procedure`, action `otdp.function_generator.upload/1.0.0`, `when_declared: true` | the arbitrary-waveform install — **no derived control at birth** (§3.2); the optional-action seam, second use, first non-lifecycle |
| `vendor_actions` | `vendor_actions` | D14 hook for unclaimed URNs (none on the example — the page still authors, every precedent's shape) |

`host_supplied` is empty on every slot, and that is a verified decision, not an
omission: the universal set (`acquisition_id`, `configuration_id`) is replaced by the
slot's own list when a slot exists (`classref.py:599-604`), but neither name helps
here — `output`'s `configuration_id` is optional (not required, so removal is moot),
and `upload`'s `dataset_id` is a caller-chosen reference into host-validated stores;
classifying it host-supplied would invent an OTDP ownership ruling this design has no
basis for. The deviation reason carries the artifact semantics instead (§3.2).

**Pages — two, and why not three.** A third, output-shaped page was considered and
rejected on mechanism: `allowed_by_kind` would admit it (a `configuration` page may
bind procedure slots), but nothing on it derives — both procedure controls are L0 —
so it would render panels and a mode-banner around two REPORTED deviations. That is
placement-by-anticipation: a page whose entire content is "controls land here
eventually" fabricates structure the ladder refuses, the same fabrication the
pattern-library rule bars ("no control surface fabricated beyond the ladder's"). The
reference owns what renders:

1. **Configuration** (`kind: configuration`, `binding_slots: [configure]`) — the L3
   preset-mediated settings surface (settings data-table + preset scaffold;
   commissioned presets absent at birth, A02).
2. **Device features** (`kind: configuration`, `binding_slots: [vendor_actions]`,
   `vendor_features: true`) — D14's placement row.

**Layouts: none authored** — the first sweep reference with no layout block, for a
mechanical reason: the layout vocabulary's derivable node kinds are reading nodes
(observation-bound), control nodes (ladder-derived) and plot refs (plot-bound); the
fg's derivable page composes none of them (its settings table is the expander's own
L3 emission, not a layout reading node). Authoring an empty shell would be the same
fabrication as the empty page.

**expect.components**: `data-table` `"1"` (`per_page: "configuration"` — the settings
table); `panel` `{n_pages}`; `mode-banner` `"1"` per page (`per_page: "*"`). That is
the whole census — no tiles, no plot, no run buttons: the class's derivable surface,
stated. **expect.controls** (three rows — the most a sweep class has carried, each an
honest divergence the gate REPORTS): `otdp.function_generator.configure/1.0.0:
"preset"`, `otdp.function_generator.output/1.0.0: "deviation"`,
`otdp.function_generator.upload/1.0.0: "deviation"`.

**forbid** — dc_psu's four ids verbatim, with the reasoning re-derived rather than
copied: `confirm-wrapped-run-action` (family-generic; this class HAS an energy
action, and §8's own "upload does not enable output" sequencing makes an
upload-then-confirm wrapping exactly the confusion the id bars);
`color-role-hint-on-lane` and `untraceable-lane-label` (family-generic carries, both
precedents' convention); `intermediated-energy-removing-action` — CARRIED with L11's
reasoning intact: the class owns an energy action (`output`), so the intent
declaration arms the safety-behaviours slice for a class that actually has the
surface (dmm's drop reasoning does not apply; dmm has no energy action).

**cannot_derive** (six rows, each traced to a mockup element):

| id | aspect | reason | author_action |
|---|---|---|---|
| `output-control` | the output on/off control | directional §C.1 presentation (energise stage+confirm naming effect, values, target; de-energise one ungated action) is beyond the per-action control vocabulary; renderer enforcement is the safety-behaviours slice's (L11 §2.2 verbatim — the slot that ruling named) | none until that slice lands; the deviation is REPORTED, never silent |
| `waveform-upload` | the arbitrary-waveform upload surface | the `channel` field is pattern-narrowed (inexpressible at the §E.1 trio), and `dataset_id` names a host-validated artifact — a selection the derived-control vocabulary does not model; the channel-enum widening is paired with the directional control by L11's ruling | host composition / procedure execution until the channel-enum + artifact-selection surfaces land; upload then derives at L2 (§9's trigger) |
| `waveform-preview` | the emitted-shape preview panel | the preview is a runtime join against the effective configuration; arbitrary mode requires the uploaded dataset's content, referenced only by `waveform_id` — no dataset action exists for a plot template to bind | host composition where an active configuration exists; a contract preview surface is a named wall-payment item (§4) |
| `function-selection` | the function/frequency/amplitude/offset/phase/load selection surface | configure is preset-mediated at birth; presets are commissioned evidence (A02) | author `ui/presets/*.json` via check-preset; the expander emits the scaffold |
| `load-convention-alert` | the load-convention alert | the condition (delivered amplitude at the declared load vs the display convention) is commissioned policy (A02), §8's own required case | bench policy at commissioning; the alert-bubble renders from host-observed conditions |
| `channel-names` | output names beyond descriptor labels | the descriptor owns channel identity | label channels in the descriptor |

(`presets` is folded into `function-selection`'s author_action — dmm's authoring
choice, second application, disclosed as such.)

### 3.1 The output action: L11's deviation, inherited unchanged

`output`'s effective schema requires `channel` (pattern-narrowed, inexpressible) and
`enabled` (boolean) — mechanically L0 — and beyond the mechanics sits the directional
§C.1 problem L11 §2.2 settled for the identical action shape: an L2 boolean staging
pair violates `R-DEENERGISE-1`'s letter for the disable direction, and making the
compliant split derivable is the safety-behaviours slice's work, not a class
reference's. One fg-specific strengthening noted for that slice: the fg's `output`
input makes `configuration_id` **conditionally required when `enabled: true`** — the
§3 lifecycle's "an enable action requires a current configuration ID" stated in the
schema. Whatever directional surface that slice builds should carry the
enable-requires-configuration coupling natively; this record flags it, builds nothing.

### 3.2 The upload action: the sweep's first optional non-lifecycle action

`upload` is `when_declared: true` (descriptors without arbitrary-waveform support
simply do not declare it; the expander skips the slot — `classref.py:1083-1085`,
verified) and L0 at birth for the pattern-narrowed `channel` alone. Two facts make
it worth its own section rather than a line:

- **It is the first action where the channel-enum widening would be immediately
  useful and safety-uncontroversial.** If `channel` resolved its options from the
  descriptor's declared source channels (the RC-L5-3-adjacent widening L11 paired
  with the directional control), upload's required set becomes
  select-expressible + text-expressible + numeric — **L2 staging** — with no §C.1
  exposure (upload installs an asset; "upload does not enable output"). The pairing
  L11 ruled stands (a blanket channel-enum derivation would also promote dc_psu's
  and fg's `output` to a non-compliant L2 — the exact rejection), but upload is the
  widening's first named beneficiary the day it lands. Recorded as the reopen
  trigger (§9), not preempted (principle 9).
- **Its output is metadata, not a dataset** (`waveform_id`, `sample_count`,
  `sample_rate_hz`) — the second reason the waveform-preview cannot ride a plot
  template: even the upload path puts no plottable dataset on this class's side of
  the wire.

### 3.3 How the generator differs from dc_psu — and the widening answer, stated

The differences are all inside the existing vocabulary: no `measure` slot (dc_psu's
output page had an observation to bind; the fg's page set drops to two); an optional
`upload` slot (the `when_declared` seam, second use); a bigger conditional configure
schema (still L3, still preset-mediated); a sixth cannot_derive row
(`waveform-preview`) and a renamed alert; zero authored layouts; zero numeric
literals. **The widening this class needs is NOTHING — no family-schema byte, no
expander arm, no counter beyond `n_pages`, no renderer motion, no gateway runtime
motion, no ui-html version event beyond the composition module every class adds.**
That is the good result the dispatch asked to be stated plainly, and it is defended
against the obvious counter: a generator's "core view is an arbitrary waveform", and
L13's §4 explicitly anticipated "function_gen outputs" reusing the `waveform` arm.
The correction, stated honestly: **the reuse is idiom-level, not arm-level.** The
`waveform` plot arm binds a DATASET slot (`over_slot` over a dataset action's
measurement output); the generator has no dataset action, and its preview is a
runtime join against configuration state (and, for arbitrary mode, against content
reachable only by `waveform_id`). L13's sentence survives as the mockup statement —
the waveform CANVAS idiom lands here class-generic, painted — while the plot-template
arm stays unreachable for any source class until a contract preview surface exists
(§4's wall-payment item). If the build falsifies this (a derivable surface the
vocabulary cannot express), that is the disclosed underpowered branch and it comes
back as evidence with a price, never silently absorbed.

## 4. The five display idioms (RC-L5-1): answered per idiom — none land; one L13 anticipation refined

RC-L5-1's rule stands (each sweep landing that needs an idiom builds it class-generic;
§E.1 rows the idioms need batch into ONE contract bump). L11 looked and answered
none; L12 looked and answered none; L13 looked, landed the canvas and context strip on
existing homes, and deferred the markers. L14 has now looked:

| idiom | verdict | the structural reason |
|---|---|---|
| **the waveform canvas** | **LANDS IN THE MOCKUP, not the contract** — L13's own ruling, corrected one notch | its contract home (`engineering-plot` over a `waveform`-kind plot) is unreachable for this class: no dataset action, no over-slot (§3.3). The mockup paints the canvas class-generic so the presentation intent stays on record; the contract arm waits for a class that acquires waveforms |
| **the capture-context strip** | honest negative | §E.2.5's acquisition disclosure is meaningless for a preview — nothing is acquired or decimated; the preview's "1 kHz · 2.5 Vpp" line is configuration echo |
| **the cursor and trigger markers** | honest negative, deferral untouched | the markers' wall-payment item (the §E.2 engineering-plot marker sub-row) is unchanged; a marker on a cannot-derive preview surface raises no contract question. NOTE: if the owner ever calls the preview bump, preview markers join that same wall-payment batch |
| **the grouped label column with brackets** | honest negative | lanes-group machinery; two analogue output channels carry no positional grouping semantics |
| **the annotation-chip rows** | honest negative | decode-sourced; the profile has no decode family |
| **the position badges** | honest negative | identity-by-position is the lanes rule; the preview's trace identity is legend-carried paint |
| ("derived frequency" — the handoff's fifth) | honest negative | no derived traces; the generator's frequency is an INPUT, not a derivation |

**The ruling this section records: no §E.1 contract row is needed for this class's
first slice; the wall-payment event remains uncalled; and the candidate list for
whenever it is called gains one item — the configuration-derived preview surface**
(joining L13's marker sub-row). An honest negative about a bump is a result.

## 5. The A3 extension — the shared census, fourth instance

`tests/ui_html/test_classref_function_generator.py` extends the shared instrument
(`tests/ui_html/classref_census.py`, landing with the L12 build; if the L14 build
runs before it exists, the lift is the L14 build's disclosed mechanical motion, L12
§6's terms verbatim). The arms:

1. **Hooks in both themes** — every hook family ≥1 per theme section. The families
   are two (`bw-data-table`, `bw-alert-bubble`) — the thinnest census of the sweep,
   which is itself the assertion: this class derives two contract surfaces on its one
   derivable page.
2. **Hook counts EQUAL the resolved expectation over the committed OTDP example** —
   `bw-data-table` 1 (the settings table, `per_page: "configuration"` resolved from
   the reference's expect block), `bw-alert-bubble` 1 (asserted with arm 5, dc_psu's
   shape). Both kill directions by construction: a mockup edit that changes a count
   reds against the resolved side; a reference edit that changes the derivation
   (the expect row's `per_page`, the slots, the page set) reds against the mockup's
   counts. A mockup edit that does NOT redden the test is the instrument failing —
   report, never a quiet pass.
3. **Placement, including the count-conserving-move kill** — every hook occurrence on
   its §E.1 root (`bw-data-table` → `table`, `bw-alert-bubble` → `aside`),
   container-scoped hooks inside their containers (the settings region, the alert
   slot). The RED arms: move `bw-data-table` onto the preview panel (count conserved)
   — placement reds while the count arm stays green under the move; AND — the arm
   this class weights most, with four idiom surfaces where dc_psu had one —
   reverse-plant a `bw-` class on the preview canvas, a function card, the preset
   card, or the output-control card, and each plants reds (L13's no-hook-on-idiom
   kill, multiplied across this class's larger idiom surface). Both mutations are
   demonstrated to kill, not assumed.
4. **Theme-invariance** — the census is identical across themes.
5. **The alert is one per theme and a named cannot_derive** (`load-convention-alert`).
6. **Selection RED-to-green** — banked at design time this pass (executed, recorded):
   gateway-side `select_references(corpus_root(), descriptor)` on the branch head
   `c64f3d05` returns `None` for the function_generator example while
   `class-dc_psu` → `['otdp.dc_psu/1.0.0']` and `class-logic_analyser` →
   `['otdp.logic_analyser/1.0.0']` resolve (`dmm`/`oscilloscope` → consistent with
   their lanes' pending builds). The slice greens the fg half only.
7. **The pattern-page arms** (the drift guard over the fg configuration composer in
   `packages/ui-html/.../classref.py`): the settings table's field-row set derives
   from the catalog's configure input schema × the example's constraints (field names
   are corpus strings — `function`, `frequency_hz`, `amplitude_vpp`, `offset_v`,
   `phase_deg`, `load_ohm`, and the two conditional rows — never literals); the
   conditional Notes wording derives from the schema's `allOf` conditions; the alert
   carries the mockup's wording; the idiom surfaces (preview, function cards, preset
   card, output-control card) render with NO `bw-` hook and no fabricated control
   (no `bw-rotary`, no `bw-confirm`, no `<button>`, no `bw-plot`); the PATTERNS census
   entry is `kind: class-page`, `row_id:
   plugin-ui-class-reference::class-function_generator`, `fixture_id: configuration`
   (page id `class-configuration` unless the library already owns the name — build
   detail; the census entry is the invariant); both themes export.

## 6. Proof — the pre-committed acceptance rules (written before any build output)

Deterministic census over the fixed fixture set (the committed OTDP fg example, the
upload-less derived fixture, the refusal fixtures, the banked baselines).
Denominators named; both kill directions stated; the underpowered branch named. These
rules bind the build agent.

- **A1 — expansion is valid and example-shaped.** `benchweave-sdk derive-ui` on the fg
  example produces a manifest set passing `validate_presentation`, with: exactly 2
  pages (Configuration, Device features); zero observation bindings; zero plots; the
  controls plan reading configure L3 / output L0 / upload L0 (levels from the
  derivation, never literals). Kill: any count off, any validation failure, or any
  page/binding/plot appearing beyond the designed set.
- **A2 — the gate passes with the birth deviations REPORTED, none silent.**
  `benchweave-sdk verify-ui` on the example exits 0 with REPORTED deviations for
  `configure` (preset-mediated), `output`, `upload`; the census reads `data-table`
  1/1 on the configuration page, `panel` `{n_pages}` = 2, `mode-banner` per page.
  Kill: any census delta, any undeclared divergence, or `classref_gate_uncovered`
  naming any of the three actions.
- **A3 — the mockup-consistency arm (the namesake).** §5's arms over
  `class-function_generator.html` × the reference × the example, with the count kill
  both ways, the count-conserving-move kill demonstrated RED (a `bw-data-table` moved
  to the preview panel reds while counts conserve), AND each no-hook-on-idiom plant
  demonstrated RED (four plants: preview canvas, function card, preset card,
  output-control card). **The falsifier: any disagreement between the mockup's counts
  or placements and the resolved expectation; a mockup edit that does NOT redden the
  test is the instrument failing — reported, never a pass.**
- **A4 — RED control (banked at design time, executed this pass).** On the branch head
  `c64f3d05`: gateway-side `select_references` on the fg example → `None`, with dc_psu
  and the analyser resolving — executed and recorded above (§5 arm 6). The slice greens
  the fg half. Kill: either half green before its landing commit exists.
- **A5 — the predecessors are untouched.** `class-logic_analyser.json`,
  `class-dc_psu.json`, and — from the moment they exist on the line —
  `class-dmm.json` and `class-oscilloscope.json` byte-identical through the slice
  (sorted-key diff = empty); the only prior-test motion is the shared-census import
  where the lift applies; the full prior test modules re-run green. Kill: any byte
  beyond the disclosed motions, or any prior acceptance rule flipping.
- **A6 — D2 census on the fg reference.** Zero numeric literals (the document has no
  layout, no plot, no spans — the census asserts the absence, not just the legality);
  no data strings (no values, units, channel names, function names, field names —
  everything arrives via the descriptor and catalog at expansion). Machine-checked
  census. Kill: any authored data string or any numeral at all.
- **A7 — corpus and version gates.** `benchweave.standards check` clean; `repin`
  writes exactly ONE new row (`class-function_generator.json`, source citing the
  authoring staging path `docs/plugin-ui-class-reference-v2/
  class-function_generator.json`, removed in-PR) and moves ZERO existing digests
  (no schema edit rides this slice); the standards-manifest's 0.3.0 `normative` array
  gains exactly the one new class path (the in-window enumeration append — §8's
  finding); `matrix --check` clean; served set and range unchanged. Kill: any digest
  motion, any frozen-row rewrite, or an unexpected row count.
- **A8 — the when_declared arm (this class's own).** On the upload-less derived
  fixture (the example minus `upload`, derived in-test): derivation still valid, 2
  pages, controls plan configure L3 / output L0, deviations `configure` + `output`
  ONLY (no upload divergence — the ledger tracks declared actions); `select_references`
  still resolves the reference. Kill: any upload-shaped finding on an undeclared
  action, or the derivation failing.
- **A9 — order gates.** The batch's #408 order held (ui-html release → SDK PR →
  release cut → pointer advance in one commit → merge on the full rollup); the lock
  anchor verified before the tag; the branch's sync-pair reds go green at the pointer
  leg and not before. Kill: any inversion, or a merge with red/pending lanes.

**Underpowered branch:** if the configuration page cannot be composed from §E.1
partials the renderer already ships (a surface the vocabulary genuinely lacks — the
design's claim is the settings table and alert suffice, §5's evidence), that falsifies
§3.3's widening answer and the finding comes back priced, never silently absorbed. If
the census cannot key on contract surfaces the preview host emits, that is an
instrument failure — reported, not a verdict.

## 7. Choreography — landing inside the open window, before the pointer leg

1. **Gateway branch content** (this slice): the §8 corpus motion + this record + the
   census module instance + the composer + the mockup + the styleguide rows. Stacked
   on the L11/L12/L13 line; the branch-internal sync-pair reds L11 disclosed continue
   until the batch's pointer leg (never merged red).
2. **Timing dependency (RC-L14-1):** the corpus commit lands BEFORE the batch's
   promotion leg merges — after the merge, 0.3.0 is frozen and the landing degrades
   to PATCH 0.3.1 + its own SDK ingest leg (§1's priced fallback). Checked at build
   start; a closed window activates the fallback, disclosed on the PR.
3. **SDK side: fixtures + ingest only.** The expander/gate need nothing (§3.3). The
   SDK leg (the L12 batch, or its follow-up under then-current train rules if the leg
   has cut) carries: the fg fixtures (the committed OTDP example; the upload-less
   derived fixture; refusal fixtures — absent required action `configure` →
   `classref_required_action_absent`, zero source channels → the channels-slot
   refusal) and the vendored 0.3.0 ingest picking up the new class file. No otdp
   motion of any kind.
4. The standards tripwire fires by design (non-empty `standards/` diff); this record
   is the named sanction. Standards-governor lane mandatory; two-lane adversary pass
   on the built slice.

## 8. Corpus-motion census (exact bytes)

Gateway repo, `standards/`:
- **Added** `standards/plugin-ui-class-reference/0.3.0/class-function_generator.json`
  — one new corpus row, `source` citing the authoring staging path (removed in-PR, the
  founding convention).
- **Edited** `standards/standards-manifest.json` — the 0.3.0 family entry's
  `normative` array gains exactly the new class path. **A finding the prior records
  missed:** the array enumerates every normative machine path (verified: the branch's
  entry lists all four 0.3.0 paths), so each class file the batch adds needs its
  append — the L12/L13 records' "standards-manifest.json unchanged" lines are
  incomplete, and their builds must make the same one-line motion or the checker's
  manifest/directory agreement reddens. In-window, same batch terms; no version
  motion.
- **Unchanged**: `class-reference.schema.json` and `layout.schema.json` (zero schema
  edits — the slice's headline), `dependency_policy` (range already `<0.4.0`),
  `cross-constraints.json` (both family rows stand — the fg consumes vocabulary
  plugin-ui 0.4.0 already ships), `corpus-manifest.json` beyond the one new row,
  every committed class document (A5), every 0.2.0/0.1.0 byte (zero frozen-row
  rewrites, A7).
- **Unpinned prose**: the family `README.md` files-table row; the styleguide's mockup
  index line + the function-generator class-page row.

Gateway repo, docs/tests (no corpus impact):
`docs/internal/ui-styleguide-mockups/class-function_generator.html` (new,
prose-adjacent — no corpus rows, no governance event);
`tests/ui_html/test_classref_function_generator.py` (the shared-census fourth
instance; the `classref_census.py` lift itself is L12's disclosed motion or this
slice's if it builds first).

`packages/ui-html`: the fg configuration composer + PATTERNS entry (rides whatever
ui-html release the batch cuts, F2's bounded-divergence ruling extended — the same
class of motion as dc_psu's composition module).

SDK (inside the batched leg): the §7 item-3 fixture/ingest set.

## 9. Deferrals, each with a home and an observable reopen trigger

| defers | home | reopen trigger |
|---|---|---|
| the directional output control (§3.1) | the §C.1 safety-behaviours enforcement slice + the family vocabulary widening in the next wall-payment event | that slice landing — fg is its second named caller (after dc_psu), with L15 electronic_load and L16 smu coming; the slice should also carry the enable-requires-configuration coupling (§3.1's flag) |
| the channel-enum widening for `upload` (→ L2 staging) + an artifact-selection surface | the RC-L5-3-adjacent widening, paired with the directional control per L11's ruling | that widening landing — upload is its first named beneficiary; or a real bench uploading arbitrary waveflows demanding the surface |
| the contract waveform-preview surface | the next plugin-ui wall-payment event (RC-L5-1's batching rule — joins L13's marker sub-row on the candidate list) | the owner calling the bump; or a real bench workflow where the preview is load-bearing |
| the five RC-L5-1 display idioms | unchanged (styleguide rule; §4's table) | the next capture-shaped class (L17 daq, L20 spectrum, L21 vna) — the expected callers |
| `function-selection` / preset values | check-preset commissioned evidence (A02) | commissioned presets at a real bench |
| `load-convention-alert` | bench policy at commissioning (A02) | the D13 policy seam at preview |
| per-channel output-state presentation (the cards' ON/OFF line) | host composition over output-action results | a readings-capable fg profile (an OTDP catalog revision adding a measure/fetch action to the class) — that landing prices its own family motion under then-current train rules |

## 10. Row-calls (numbered; the principal alone decides)

- **RC-L14-1 — the shape.** One class file + the manifest enumeration append inside
  the open 0.3.0 window, landing on the stacked line BEFORE the batch's promotion leg
  (recommended — zero schema motion, zero SDK arms, the cheapest class of the train;
  the window is the only timing constraint). Alternative: wait for the merge and land
  PATCH 0.3.1 + its SDK ingest leg — legal after the leg, strictly more expensive,
  recorded as the fallback.
- **RC-L14-2 — two pages, no fabricated third.** The reference owns Configuration +
  Device features; the output-shaped page is refused as placement-by-anticipation
  (§3). The mockup carries the class's operator idioms hook-less around the
  configuration composition. Recommend ACCEPT (the honest thin page set is the
  class's structural statement).
- **RC-L14-3 — the widening answer NOTHING, with L13's anticipation refined.** No
  family-schema byte; the waveform-canvas reuse is idiom-level (mockup paint), the
  plot arm unreachable for a source class with no dataset action (§3.3); the preview
  joins the wall-payment candidate list. Recommend ACCEPT (an honest negative,
  first-class).
- **RC-L14-4 — the manifest `normative` append, surfaced for the whole batch.** This
  slice appends its class path; the L12/L13 builds must make the same motion their
  records omitted (§8's finding). Recommend ACCEPT + relay to the L12/L13 lanes.

## 11. Review tier and Step-1 keyword scan

Tier 3 — touches `standards/` (corpus row, manifest enumeration); rides a batch that
advances the submodule pointer; diff text carries `sha256` (the corpus row, sync
tests, this record). Two-lane adversary pass and the standards-governor lane
mandatory.

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~5–10 | 1 new corpus row, sync/fixture tests, this record |
| `hashlib` | ~1–2 | SDK fixture tests |
| `protection` | ~1–2 | this record's §C.1 prose only; zero in code (the fg's only safety-relevant action is the output toggle — the honest note) |
| `threading` / `asyncio` / `subprocess` / `migrate` / `recovery` | 0 | in-process render; derivation, not migration |

## 12. Top risks, each with its falsifier

- **R1 — the window closes first.** The batch's promotion leg merges before the fg
  corpus commit lands → the PATCH 0.3.1 fallback activates (two version events).
  Falsified by checking branch state at build start; RC-L14-1 records the sequencing
  call for the coordinator.
- **R2 — the thin census under-powers A3.** Two hook families give the count arm less
  surface than any prior class; the placement and no-hook plants carry the load. If
  review holds the instrument too weak to catch a structural lie, the arm to add is a
  settings-table ROW-set assertion (field rows derived from the catalog schema —
  already arm 7's drift guard), not more hooks on idiom surfaces. Falsified by the
  adversary lane mutating the mockup in ways no arm reddens on.
- **R3 — the two-page reading is wrong at review.** If review holds the class owes an
  output page (placement for the coming directional control), the motion is small
  (one page, kind configuration, binding [output, upload], no layout) but re-opens
  RC-L14-2 — a row-call re-derivation, not a silent absorb. Falsified by the owner or
  the adversary lane arguing placement-by-anticipation is actually wanted.
- **R4 — the when_declared skip diverges from the design's reading.** A8's
  upload-less fixture exercises it; if the expander's skip leaves residue (a ghost
  page section, a stray divergence), the fix lands in the batched SDK leg's own arm
  and is re-disclosed. Falsified by A8.
- **R5 — mockup drift.** Intended: the mockup is the spec; edits force re-derivation
  and the census reds (A3).
- **R6 — public-repo discipline.** `FGEN-01` and every displayed value invented; no
  real bench, vendor or corpus identifier (paid at authoring).
- **R7 — the manifest-append finding is wrong.** If `benchweave.standards check`
  proves the normative array advisory (not checked against the directory), the append
  is still correct bookkeeping and the L12/L13 omission harmless — the finding
  downgrades, it does not retract. Falsified by reading the checker's manifest arm at
  build time.

## 13. Precedent map (principle 9)

| L14 surface | in-tree precedent | why it fits |
|---|---|---|
| class file added to an in-window unreleased bump | the batch rule (GOVERNANCE), L11's addendum, L12 §1, L13 §1 | same train, same bump, no new version directory |
| mockup authored with hooks + placement from birth | L12's `class-dmm.html` (§2 there), L13's §2 | the convention's third authored-from-birth instance |
| deviation inherited unchanged from a named predecessor | L11 §2.2's forward clause ("recurs at L14") | the slot the ruling named; zero re-derivation of settled ground |
| optional-action slot via `when_declared` | the scope's `trigger` slot (L13 §3) | the seam's second use; first non-lifecycle optional |
| no-widening landing with the honest statement | dmm's §3 ("nothing — a good result, stated") | the same result shape, now with zero schema edits |
| host-knowledge seam for non-wire presentation data | §E.2.6 provenance, L13's trigger-marker | the preview and function-summary deferrals' structural home |
| shared census instance | `classref_census.py` (L12 §6's lift) | the instrument must not fork between classes (F1's lesson) |
| per-class composer in `classref.py` | `render_output_page`, the dmm/scope composers | the module's standing shape, fifth instance |
| expansion fixture = the OTDP class example | RC-L11-4's ruling | fourth application; the upload-less fixture derives in-test |

## 14. Appendix — evidence, disclosures, and the pre-flight record

**Pre-flight (the #181 R2 discipline):** `git fetch origin`; the L11 branch tip is
`c64f3d05` (dispatch-matched); `git worktree list` run before any tree action; other
lanes' trees untouched (the L12/L13 design records were read read-only from their
lanes' trees — `.wt/l12-d4m9`, `.wt/l13-t4k9` — both uncommitted working files at
read time); this lane's tree is `.wt/l14-r9k4`, write-only-in-own-tree honored. No
remote branch touches `standards/plugin-ui-class-reference/` or the mockups beyond
the L11 line this design stacks on. (Open-PR state is being re-derived by the
coordinator for the whole batch this session; L13's zero-open-PRs reading is the
latest on record.)

**Gortex:** AVAILABLE to this subagent — the probe read
(`.wt/l14-r9k4/.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md`) was
served with the worktree path (unprefixed `.wt/l14-r9k4/...`; a `benchweave/`-prefixed
form failed with a stat error — the lane's working spelling is recorded here for the
build). Session start reported checkout discovery `view_building, retryable=true`; it
cleared within the first reads. One structured extraction went through python over a
gortex-persisted tool result (the 150KB catalog read the tool itself persisted and
sanctioned for jq/python querying) — no raw grep/cat on indexed source. The worktree's
submodule was initialized at the pinned `9e0449ef` (= v0.16.0, tag verified in-lane)
for the A4 execution; SDK source claims rest on that pin. No daemon restart, no
tracking change.

**Design-time execution beyond reading (two, disclosed):** (a) the A4 RED pair —
`select_references` run gateway-side in the worktree venv (uv bootstrapped;
`git submodule update --init packages/sdk` at the pin; `uv sync` — nothing written
outside the gitignored venv and the submodule checkout at its pinned SHA); (b) the
branch-state derivations (manifest normative array, corpus rows, cross-constraints
counts) via python over JSON in the worktree. Both follow the L12/L13 precedent: a
pre-committed acceptance rule that can be banked before the build should be.

**The slotted-set check:** §7A row L14 verified against the program record AND the
workbench §8 order ("… oscilloscope; **function generator**; electronic load …") —
the generator is genuinely the fourth sweep class. Nothing in L6–L10 gates it.

**Paths read as evidence:** `standards/GOVERNANCE.md` (via the L11/L12/L13 records'
citations, re-verified in substance); `standards/standards-manifest.json` +
`corpus-manifest.json` + `cross-constraints.json` (branch state, this pass);
`standards/plugin-ui-class-reference/0.3.0/` (`class-reference.schema.json` in full,
`layout.schema.json` in full, `class-dc_psu.json` in full, `class-logic_analyser.json`
via the census conventions); `standards/otdp/0.2.3/device-profile-catalog.json` (the
function_generator profile + all three action input/output schemas, extracted from
the persisted read); `standards/otdp/0.2.3/examples/class-function_generator.json`
(in full); `standards/otdp/0.2.3/device-classes.md` (in full — §1 coverage, §2 common
contract, §3 lifecycle, §8 the generator's normative section);
`docs/internal/ui-contract.md` (§E.1 all 15 rows — the text/select/boolean/confirm
rows load-bearing for the ladder analysis; §C.1); `docs/internal/ui-styleguide.md`
(the class-reference section + the idioms paragraph);
`docs/internal/ui-styleguide-workbench-design.md` §8;
`docs/internal/ui-styleguide-mockups/class-dc_psu.html` (structural skeleton);
`packages/sdk/src/benchweave_sdk/classref.py` (at the pin — `allowed_by_kind`,
`_ladder_level`, `_derive_controls`, the when_declared skip, `_HOST_SUPPLIED_UNIVERSAL`
slot-replacement semantics); `tests/ui_html/test_classref_dc_psu.py` (in full — the
A3 instrument this design's §5 extends);
`.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md` (in full, addendum and
refute fold), `2026-10-19-classref-l12-dmm-design.md` (in full, from the l12 lane's
tree), `2026-10-19-classref-l13-oscilloscope-design.md` (in full, from the l13 lane's
tree), `2026-10-14-classref-logic-analyser-design.md` (§0, §2.5, §7A, §8); the branch
git history (`fa9cfc63`'s corpus diff — the 4-row verification and the
manifest-enumeration finding).

**Honest disclosures to the dispatch:** (a) the dispatch's grounding held — no mockup
exists, the OTDP example is at 0.2.3 with the exact shape described, the inherited
vocabulary is `{digital_lanes, time_series(+series required), waveform}` per the
batch context; (b) the dispatch's suggestion that "L13's `waveform` arm may cover it
exactly" is REFUTED on mechanism, not taste — the arm binds dataset slots and the
generator has no dataset action; the reuse survives at idiom level only (§3.3, RC-L14-3);
(c) the dispatch's "needs nothing, that is a good result" is the confirmed answer,
with the one-enum-member-per-batch instinct now measured: L14 needs zero; (d) one
finding beyond the dispatch's frame: the manifest `normative` enumeration append the
prior two records missed (§8, RC-L14-4) — relayed, not silently absorbed; (e) the
two-page shape (RC-L14-2) is this design's one genuine departure from sweep
convention (every prior class authored three pages), and it is argued from mechanism
(§3), flagged as R3, and left to the owner's row-call.
