# L11 — the class sweep opens: `otdp.dc_psu` class reference, mockup-validated

**Date:** 18 October 2026
**Slot:** L11 of the class-reference train (parent gateway issue #463; program record
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` §7A row L11, §8's
RC-1/D-1 row; the sweep order continues L12 dmm … L21 vna per the workbench §8 table).
**Branch:** `feat/l11-dcpsu-classref` (design record only; no build in this slot).
**Worktree:** `.wt/l11-x7q9/`, off `origin/main` `49b4b65e`; submodule pinned at
`fca9c415` = SDK **v0.15.0** (verified: tag commit and `pyproject.toml` 0.15.0; the
worktree's submodule is uninitialized — SDK source reads were served by gortex from the
primary checkout's submodule at the same pin, content identity verified).
**Evidence baseline:** gateway `49b4b65e`, SDK v0.15.0, plugin-ui 0.4.0 active,
plugin-ui-class-reference 0.2.0 active (range `>=0.1.0,<0.3.0`, no dev heads),
OTDP 0.2.3 active, `benchweave-ui-html==0.3.0` (the SDK `[server]` extra).
**Binding design points:** the program record D1–D14 (esp. D2 structure-not-data, D7
run-group safety, D13/D14 effective capability and coverage), its §7A-L11 row
("validated against the existing mockup"), the L5 record's RC-L5-1 (the five display
idioms deferred to the sweep, reopen trigger "the first sweep design record that needs
an idiom"), and GOVERNANCE's change-class table, copy-never-move, and G-5 pacing.

## 0. Summary and design thesis

L11 authors the second class reference — `class-dc_psu.json`, binding
`otdp.dc_psu/1.0.0` — with the existing mockup
(`docs/internal/ui-styleguide-mockups/class-dc_psu.html`) as the acceptance anchor, and
widens the family's plot vocabulary so the class's trend view is expressible at all.
The thesis in one line:

> The PSU is the first **scalar/readings-shaped** class (the analyser was
> lanes-shaped), so the landed expander and gate — which hard-code the analyser's
> string-lane dataset, its `digital_lanes`-only plot emission, and its `abort`-slug
> safety set — need a **class-shape widening**, while the plugin-ui manifest, the
> renderer and the layout vocabulary already carry everything the mockup shows.

Three grounding facts fix the scope, each verified in the landed tree:

1. **The manifest and renderer vocabularies are ahead of the family schema.**
   plugin-ui 0.4.0's `$defs.plot.kind` enum is `["time_series", "waveform",
   "digital_lanes"]`; binding and target kinds include `observation`; page kinds
   include `readings`; §E.1's 15-row inventory ships `reading-tile`, `engineering-plot`
   (root `figure`, hooks `bw-plot ~ bw-plot__canvas ~ …`), `data-table`, `alert-bubble`,
   `rotary-control`. ui-html 0.3.0 renders them. The **family's** 0.2.0 schema is the
   narrow gate: `page_template.plot.kind` is the const `"digital_lanes"` and nothing
   else (`class-reference.schema.json:230`).
2. **The expander is analyser-shaped end to end.** `_finish` builds the FIRST dataset
   slot as the capture slot with string-typed lane variables and emits
   `"kind": "digital_lanes"` regardless of the template
   (`packages/sdk/src/benchweave_sdk/classref.py`, `_finish`); the readings page admits
   only `observation` bindings and nothing in the expander builds any
   (`allowed_by_kind["readings"] = {"observation"}`); the gate's `census_map` counts
   nine components and none of them is `reading-tile` or `engineering-plot`
   (`classref_gate.py::_assert_expect`); the D14 coverage arm's L4 test requires a
   `bw-lanes` figure (`_coverage_findings`).
3. **The class's safety shape is directional and the landed machinery is not.**
   ui-contract §C.1 is written in PSU language — `R-ENERGISE-1`: "enabling an output,
   or changing a setpoint of a currently-energised output" requires stage + a confirm
   naming effect, values and target; `R-DEENERGISE-1`: "An energy-removing action
   (output off) is one action, never confirmed, never gated." The one OTDP action
   `otdp.dc_psu.output/1.0.0` (boolean `enabled`) carries BOTH directions with opposite
   presentation rules; the per-action `expect.controls` vocabulary
   (button|staging|preset|deviation) cannot split them; the gate's D7 set is the slug
   `"abort"` and its confirm arm is a blanket `bw-confirm` ban. §C.1's own preamble
   assigns renderer enforcement to the safety-behaviours slice — L11 must not preempt
   it, and must not derive a non-compliant control either.

## 1. The governance answer first: no in-place add; a version event (0.3.0 MINOR)

**Can `class-dc_psu.json` be added to the existing 0.2.0 directory? No.** Three
independent kills, each from GOVERNANCE text:

- "Immutability starts at release: a version directory with no `-dev` suffix is frozen
  exactly as before" (the dev-stage section). 0.2.0 has no `-dev` suffix.
- The change-class table routes additive machine changes through a bump ("Additive
  machine errata (backwards-compatible) | PATCH of that standard"); the drift gates
  exist to refuse the alternative ("normative bytes changing without a version bump is
  refused — `normative_hash_mismatch`, `content_drift_without_version`"), and repin's
  coverage is fail-closed both directions, so the new file needs a row and a row on a
  released version is corpus motion on frozen bytes.
- R-2 multi-version serving resolves a consumer's pin digest-verified from the
  retained corpus; mutating 0.2.0 after release breaks that promise for every
  0.2.0-pinned consumer.

**PATCH 0.2.1 or MINOR 0.3.0?** A pure class-file addition (nothing removed or
retyped, old documents still valid) is errata-class and would be **0.2.1** — and the
current served range `>=0.1.0,<0.3.0` already admits it, so no policy motion. But L11
needs one schema delta the 0.2.0 vocabulary cannot express: a plot template whose kind
is not `digital_lanes` (§0.1). A vocabulary widening is **MINOR by this family's own
precedent** — the L5 record's version-arithmetic table classed the 0.1.0→0.2.0 layout
widening as MINOR, not errata. So:

- **Shape A (recommended): MINOR 0.3.0** — copy-never-move from 0.2.0, widen
  `page_template.plot` (§2), re-stamp the two schemas and the analyser reference,
  add `class-dc_psu.json`. Costs: 4 corpus rows, a dependency_policy range widening
  `>=0.1.0,<0.3.0` → `>=0.1.0,<0.4.0` (a G-3 coordinator decision; this record is the
  linked ruling), the cross-constraints row amending in place, the full L1/L5
  choreography (SDK widening + release 0.16.0 + pointer advance).
- **Shape B (fallback): PATCH 0.2.1, plot deferred** — class file only, readings page
  (tiles + table via the layout vocabulary's existing `reading` nodes), trend plot
  deferred to the first waveform class (L13). Cheaper version event; the mockup
  validation then covers only the tile/table subset. Adopted only if the build falsifies
  Shape A's series-derivation rule (R1 below).

**Sweep cadence (the coordinator's lever):** each class landing promotes its own bump —
11 classes, 11 SDK legs — OR the owner batches adjacent classes into one train (the
bump-minimization rule already governs batching: same-standard changes sharing a merge
window batch into one bump). A sweep-wide `0.3.0-dev` head promoted once is legal but
withholds every landed class from digest-served consumers until promotion and makes the
SDK's served-set exactness churn per edit; per-class promotion is recommended (row-call
RC-L11-2). **G-5 pacing is satisfied for this bump:** the commit adding 0.3.0 arrives on
a tree whose SDK lock already carries 0.2.0 (the v0.15.0 pin, verified); L12's bump then
waits for 0.3.0's own SDK leg — the choreography serializes this by construction.

**The OTDP `dc_psu` example, and how it relates.**
`standards/otdp/0.2.3/examples/class-dc_psu.json` is the OTDP family's class-contract
fixture — a descriptor exemplar (two `source` channels `ch1`/`ch2`, each declaring
quantities `[voltage, current, power]`; the three required actions declared with empty
`input_constraints`). It is NOT a presentation reference and never becomes one: OTDP
answers what a device of the class must admit; this family answers how the class
presents. It informs L11 as exactly what the analyser's example informed L1 — the
canonical expansion fixture (the styleguide's "Class-reference capture pages" rule: the
class page's data is the committed expansion of the family reference against the OTDP
reference descriptor). The 0.1.2 copy the dispatch named is a retained digest-frozen
predecessor under multi-version serving; the active 0.2.3 example is the one to use.

## 2. The `dc_psu` reference, derived from the mockup

The mockup is the spec. Its composition (one composition, two themes): a title row with
a `Controls` button; a readings row of three cards (Voltage, Current — warning variant,
Power) each with a quality line; an alert aside ("Operating margin — current
approaching configured limit"); a lower grid with a staged-output control card (knob,
setpoint, `STAGED · APPLY REQUIRED`) and a recessed trend plot ("OUTPUT · LAST 60
SECONDS", two traces plus a dashed limit line); a Channel|Reading|Quality table. Cards
are raised surfaces, the plot recessed; the lower grid splits ≈5/7 of 12.

Every element maps to structure the reference may author, data it may not, or a named
gap:

| mockup element | disposition |
|---|---|
| readings cards (3, one warning variant) | **derives**: one `reading-tile` per (channel, quantity) variable of the `measure` dataset; the count is an expression, never the literal 3 |
| quality lines (`✓ NORMAL · 84 ms`) | derives from observation quality/freshness (§B/ST-4 machinery; data at runtime) |
| warning variant card | severity is runtime observation state — structure renders the variant, data decides it |
| alert aside | **cannot_derive** `margin-alert` (§2.3) — the condition is commissioned policy (A02) |
| staged-output knob + setpoint | **cannot_derive** `setpoint-staging` — `configure` is L3 preset-mediated at birth; the knob is the styleguide's staging idiom, deferred |
| trend plot, two traces | **derives**: one `time_series` plot over the measure slot; one series per numeric scalar variable (V and I for the mockup's channel; power included by rule — the mockup's two-trace choice is an author `channel_hints` matter, disclosed) |
| dashed limit line | **cannot_derive** `limit-overlay` — a runtime join against the active configuration |
| Channel/Reading/Quality table | **derives**: one `data-table` reading node over the same dataset |
| title row, `Controls` button | page chrome/navigation — host territory |
| `STAGED · APPLY REQUIRED` line | the §E.1 staging disclosure text — renders on preset/staging surfaces by contract |

**Slots** (all URNs verified against `standards/otdp/0.2.3/device-profile-catalog.json`,
profile `otdp.dc_psu/1.0.0`: required `configure`/`output`/`measure`, optional none,
`channel_roles: ["source"]`):

| key | kind | resolves |
|---|---|---|
| `outputs` | `channels`, `where_role: source` | the declared source outputs, declaration order |
| `measure` | `dataset`, action `otdp.dc_psu.measure/1.0.0`, `schema_source: output_measurement` | the scalar_set dataset (§3.1); one numeric variable per (channel, declared quantity); `x` = the time axis |
| `configure` | `configuration`, action `otdp.dc_psu.configure/1.0.0`, `schema_source: input_schema` | settings schema = the action input (`configuration_id`, `channel`, `voltage_v`, `current_limit_a`, `ovp_v`, `ocp_a`) |
| `output` | `procedure`, action `otdp.dc_psu.output/1.0.0` | the energy toggle — **no derived control at birth** (§2.2) |
| `vendor_actions` | `vendor_actions` | D14 hook for unclaimed URNs |

No `when_declared` slots — the profile has no optional actions. `host_supplied` is
empty on every slot: `output`'s `channel`/`enabled` are real caller inputs, and
`measure`'s `channels` resolves from the descriptor's declared outputs (structural).

**Pages** (three, mirroring the analyser's count):

1. **Output** (`kind: readings`, `binding_slots: [measure]`) — the mockup's overview:
   readings section (raised, span 12), trend section (recessed, span 7) carrying the
   `time_series` plot over `measure`, table section (raised, span 5) carrying the
   `data-table` reading node. The 5/7 split is the mockup's own ratio expressed in the
   vocabulary's structural spans (≤12).
2. **Configuration** (`kind: configuration`, `binding_slots: [configure]`) — the L3
   preset-mediated settings surface (the settings data-table + preset wiring;
   `preset_asset_ids: []` at birth).
3. **Device features** (`kind: configuration`, `binding_slots: [vendor_actions]`,
   `vendor_features: true`) — D14's placement row, the analyser's own shape.

**The schema widening (the MINOR's substance), minimal:** `page_template.plot.kind`
widens const → enum `["digital_lanes", "time_series"]` with per-kind conditionals —
`digital_lanes` keeps its group machinery exactly as-is (the analyser's bytes must
re-stamp and nothing else, the L5 shape); `time_series` adds one optional structural
field `series: "numeric_variables"` (the closed derivation rule: every numeric scalar
variable of the over-slot's dataset becomes a series; the reference authors no variable
names — D2). `waveform` is deliberately NOT admitted — no class in this slice needs it;
L13 oscilloscope widens again on its own evidence (the family's per-need widening
precedent). `expect.attribute`'s selector closure stays lane-only — the PSU reference
asserts counts only.

**expect.components** (count expressions resolved by the widened inventory, §3.4):
`reading-tile` `{n_reading_tiles}` on the output page; `data-table` `1` on the output
page (plus the L3 settings table on the configuration page — pooled per the gate's
existing counting); `engineering-plot` `1` on the output page; `panel` `{n_pages}`;
`mode-banner` `1` per page (`per_page: "*"`). **expect.controls**:
`otdp.dc_psu.configure/1.0.0: "preset"`, `otdp.dc_psu.output/1.0.0: "deviation"`.
`measure` needs no controls row (dataset slots are page-covered, `fetch`'s own shape).
**forbid**: the analyser's four ids stand (`confirm-wrapped-run-action` is vacuously
true at birth — no confirm surface derives; `intermediated-energy-removing-action`
declares the class's intent even though the gate's slug set does not yet name `output`
— §2.2).

### 2.2 The output action: why nothing renders at birth

`output`'s effective schema requires `channel` (pattern-narrowed string —
inexpressible; the RC-L5-3 deferral bites exactly here) and `enabled` (boolean,
expressible since L5). Two paths were rejected:

- **L2 staging** (boolean + Apply) — the natural post-L5 render — violates
  `R-DEENERGISE-1`'s letter for the `enabled=false` direction: staging stands between
  the operator and de-energising. Rejected on the contract's own words.
- **Descriptor-derived channel enum** (intersect `channel` with the resolved source
  channel ids — D2-clean, and it would promote `output` to L2) — rejected for the same
  reason: it makes the non-compliant render derivable.

So `output` declares a **deviation at birth** with `cannot_derive: output-control`:
the compliant surface is direction-split (stage+confirm on energise per `R-ENERGISE-1`;
one ungated action on de-energise per `R-DEENERGISE-1`), the per-action control
vocabulary cannot express it, §C.1's renderer enforcement belongs to the
safety-behaviours slice, and no §E.1 surface today can render an output-off control
that complies. The deviation is downgradable in today's ledger (the D7 set is the
`abort` slug — verified), which is correct: it names a missing surface, not a
downgraded safety reachability. The hand-author risk (an overlay staging the output
binding in both directions) is disclosed in the UI-GUIDE text and left to §C.1's
enforcement slice — recorded as the handoff, not solved by a parallel mechanism
(principle 9). The same action shape recurs at L14 function_generator, L15
electronic_load and L16 smu; whatever that slice lands becomes their surface too.

### 2.3 cannot_derive (each traceable to a mockup element)

| id | aspect | reason | author_action |
|---|---|---|---|
| `output-control` | the output on/off control | directional §C.1 presentation (energise stage+confirm, de-energise ungated) is beyond the per-action control vocabulary; enforcement is the safety-behaviours slice's | none until that slice lands; the deviation is REPORTED, never silent |
| `setpoint-staging` | the staged knob/Apply setpoint idiom | `configure` is preset-mediated at birth; presets are commissioned evidence (A02) | author `ui/presets/*.json` via check-preset; the expander emits the scaffold |
| `margin-alert` | the operating-margin alert | the alert condition (reading vs configured limit) is commissioned policy (A02) | bench policy at commissioning; the alert-bubble renders from host-observed conditions |
| `limit-overlay` | the trend's dashed configured-limit line | the limit value is runtime configuration data; the overlay is a runtime join | host composition where a configured limit is active |
| `presets` | preset settings values | commissioned evidence, never derived (A02 unamended) | check-preset |
| `channel-names` | output names beyond descriptor labels | the descriptor owns channel identity | label channels in the descriptor |

### 2.4 The five display idioms (RC-L5-1): none land at L11

The canonical styleguide list ("Class-reference capture pages") is six class-generic
**capture-view** idioms: the waveform canvas, the grouped label column with brackets,
the annotation-chip rows, the cursor and trigger markers with readout, the
capture-context strip, and the position badges. The handoff's five (group bracket,
annotation chips, on-axis markers, derived frequency, position badges) are that set's
permutation (the L5 record's §1 reconciliation, standing). dc_psu needs none of them:

- it has no lanes capture view — its plot is the **existing** `engineering-plot` §E.1
  component (15-row inventory, renderer ships it), which is not an idiom;
- its "derived-looking" power tile is not derived at the UI at all — `power` is a
  first-class declared quantity in the OTDP model (`examples/class-dc_psu.json`
  channels declare `quantities: [voltage, current, power]`), so the tile binds a
  dataset variable like any other.

The deferral stands with its reopen triggers armed; the first waveform-capture sweep
class (L13 oscilloscope) is the expected caller. This record is the "first sweep design
record" the reopen rule names — it looked, and the answer is none (an honest negative,
first-class).

## 3. Expansion and gate semantics (SDK 0.16.0 — the widening inventory)

The command surface already exists and is pinned: `benchweave-sdk derive-ui <project>`
and `benchweave-sdk verify-ui <project>` (console scripts verified in the SDK
`pyproject.toml`; the command set is pinned by `test_registry_census.py`;
`verify-ui` renders through the standalone host pinned to `benchweave-ui-html==0.3.0`
via the `[server]` extra). `find_reference` globs `class-*.json` in the vendored
family tree and matches `profile_id` — **no SDK enumeration of classes exists to
extend**; the new file is discovered by the sync. The widening is additive, all in the
expander/gate:

1. **Dataset variables by shape** (`_finish`): the first-dataset-slot capture
   special-case generalizes — the page template's plot kind drives it.
   `digital_lanes` keeps today's string-lane derivation byte-for-byte (B1-parity
   discipline); `time_series` derives one numeric variable per (channel, quantity)
   from the channels slot's resolved outputs × their declared `quantities`, plus the
   `t` axis variable. The OTDP measurement model supports this shape natively
   (`otdp-measurement.schema.json` `$defs.variable`: `quantity`, `unit`,
   `channel_ids`, `dtype: float64`; dataset `kind: scalar_set`).
2. **Observation targets and bindings** on `readings` pages (the manifest vocabulary
   already admits both kinds — verified in `$defs.binding`/`$defs.target`;
   `allowed_by_kind["readings"] = {"observation"}` already in the expander).
3. **Plot emission arm**: `time_series` plots (`kind`, `binding_id`, `x`, `y` from the
   derived numeric variables) — the analyser's group machinery untouched.
4. **Layout reading nodes**: `_build_layout` emits `reading` nodes
   (`reading-tile`, `data-table`) bound to the observation binding — the layout
   vocabulary has carried both kinds since 0.1.0 (verified in `layout.schema.json`
   `$defs.reading`); the expander simply never had a class that used them.
5. **Expect inventory names**: the closed `_EXPECT_NAMES` set gains the PSU's
   structural counters — `n_source_channels`, `n_scalar_variables` (so
   `n_reading_tiles = n_source_channels × per-channel quantity count` resolves; exact
   names are build detail, the closure discipline is not).
6. **Gate census arms**: `census_map` gains `reading-tile` → `bw-reading` (section
   root) and `engineering-plot` → `bw-plot` (figure root); the `_CensusParser` counts
   the two hooks. Unknown component names keep refusing
   (`classref_gate_unknown_component`) — the closure moves with the inventory.
7. **Coverage L4 test widens**: a dataset action is covered by its page's rendered
   dataset surface — `lanes_figures` for lanes-shaped plots, the plot figure for
   `time_series` (the plan row already carries the render surface; the test consults
   it instead of assuming lanes).
8. **D2 census guard** (the program record §3.5 pattern, extended): a test asserts the
   reference document carries no numeric literals outside the structural set
   {spans ≤12, plot_index} and no pure-numeric strings beyond count arity — the PSU
   reference's only numbers are layout spans.

**Gateway side: no code motion.** The L4 landing's consumption is generic — the
no-manifest fallback derives from (descriptor × reference) through
`src/benchweave/presentation/classref.py`, the production host composes the layout
block, and the PSU needs no `class_panel` (its pages are standard kinds; the analyser
panel stays the only registered one). Readings render read-only from
gateway-observed values (GW-22 unchanged). Build-time verification: the gateway's
`compose_layout_sections` renders `reading` nodes (the vocabulary predates L4; the
analyser layout never exercised them) — if an arm is missing it lands in the same
slice as a gateway-side add, disclosed on the PR.

## 4. Corpus-motion census (exact bytes)

Gateway repo, `standards/`:

- **Added** `standards/plugin-ui-class-reference/0.3.0/`: `class-reference.schema.json`
  (the §2 plot widening + re-stamp), `layout.schema.json` (re-stamp only),
  `class-logic_analyser.json` (re-stamp only — zero content change, the L5 shape),
  **`class-dc_psu.json` (new)**. Plus unpinned prose: `README.md` (files table row,
  from-predecessor note; also fixes the README's stale three-id forbid list — the
  committed analyser reference carries four).
- **Changed** `standards-manifest.json`: family entry 0.2.0 → 0.3.0 (`supersedes:
  "0.2.0"`, released date, normative = the four 0.3.0 machine paths).
- **Changed** `dependency_policy.standards."plugin-ui-class-reference"`: range
  `>=0.1.0,<0.3.0` → `>=0.1.0,<0.4.0`; `versions` map gains the 0.3.0 migration row.
  (G-3: a range change is a coordinator decision — this record is the linked ruling;
  the L5 bump performed the identical motion.)
- **Added** corpus rows: exactly **4** — the three re-stamps citing the 0.2.0 paths as
  `source`, and the new class file citing an authoring staging path
  (`docs/plugin-ui-class-reference-v2/class-dc_psu.json`, removed in-PR — the founding
  convention; build-time verification: mirror whatever `source` convention otdp's
  newest added example rows used, if a closer precedent exists). Digests only via
  `benchweave.standards repin`.
- **Changed** `standards/cross-constraints.json`: the family row amends in place —
  `plugin-ui-class-reference 0.3.0 requires plugin-ui >=0.4.0,<0.5.0` (floor
  unchanged: the widening consumes vocabulary plugin-ui 0.4.0 already ships), evidence
  re-cited to this record. One row, amended, not added (the file's own honest-window
  note).

Gateway repo, docs/tests (no corpus impact): the pattern-library `dc_psu` composition
page data + its drift guard (`tests/ui_html/test_classref_page.py` pattern, re-derived
from the 0.3.0 corpus files × the OTDP example); the mockup-consistency test (§6 A3);
`docs/internal/ui-styleguide.md` gains the dc_psu class-page row beside the analyser's.
The mockup itself gains §E.1 component hooks (RC-L11-3): `bw-reading` on the cards,
`bw-alert-bubble` on the aside, `bw-plot` on the trend figure, `bw-data-table` on the
table — the analyser mockup's own convention (verified: it carries `bw-reading`,
`bw-panel`, `bw-button`), so the consistency check keys on contract surfaces, not
bespoke selectors. Mockups are docs/internal prose-adjacent artifacts — no corpus rows,
no governance event.

SDK repo (v0.16.0): the §3 widening; `standards/` vendored tree + lock ingest 0.3.0
(`active` marker moves; 0.2.0/0.1.0 rows retained); fixtures — the OTDP class example
as the canonical expansion fixture (F-psu-1) plus one invented single-channel fixture
matching the mockup (F-psu-2: one source channel, the three quantities — for the
mockup-count assertions); refusal fixtures (zero source channels → `classref_no_lanes`;
absent required action → `classref_required_action_absent`); `pyproject.toml` 0.16.0;
lock anchor `compatibility.sdk = "0.16.0"` before the tag. **No ui-html motion** — the
renderer already ships every component the page composes (§0.1), so no
`ui-html-v*` release and no `[server]` pin change rides this train.

## 5. Choreography (the L1/L5-proven order)

1. **Gateway PR** (`feat/l11-dcpsu-classref` from main): the §4 corpus motion + this
   record + the drift guard + the mockup-consistency test + the pattern-page data +
   the styleguide row + the mockup hook pass. Standards-governor mandatory. The
   branch is red on `served_set_drift` during authoring — the disclosed, disclosed
   branch-internal window (red-main doctrine: never merged red).
2. On the branch: submodule init; `make sync-sdk-standards`; SDK PR opened NOW
   (body notes gateway #463; no SDK-side issue by design): the §3 widening +
   fixtures + tests + version 0.16.0 + lock anchor + docs (AI-GUIDE/UI-GUIDE
   `cannot_derive` text via the house doc lane).
3. `make release-cut VERSION=v0.16.0` in the SDK repo.
4. Pointer-advance commit on the gateway branch (gitlink → the v0.16.0 tag commit;
   `.gitmodules` `pin`; `sdk_compatibility` mirror; matrix render as its own commit) —
   branch green → merge.
5. The standards tripwire fires BY DESIGN (non-empty `standards/` diff); this record
   is the named sanction.

## 6. Acceptance rules (pre-committed — written before any build output)

Deterministic census on the fixed fixture set (F-psu-1 the OTDP class example,
F-psu-2 the mockup-matching single-channel fixture, the refusal fixtures, the banked
baseline). Denominators named; both kill directions stated; the underpowered branch
named. These rules bind the build agent.

- **A1 — expansion is valid and mockup-shaped.** `benchweave-sdk derive-ui` on F-psu-1
  produces a manifest set that passes the canonical validator
  (`validate_presentation` → valid), with the output page carrying an observation
  binding, a `time_series` plot over the measure slot, and 6/6 derived reading tiles
  (2 channels × 3 declared quantities — the count from the derivation, never a
  literal). Kill: any count off, validation failure, or a tile variable not traceable
  to a (channel, quantity) pair.
- **A2 — the gate passes and asserts the mockup inventory.** `benchweave-sdk
  verify-ui` on F-psu-1 exits 0 with REPORTED (not silent) deviations for `output`
  and `configure` (preset-mediated birth), and censuses on the output page:
  `reading-tile` 6/6, `data-table` ≥1, `engineering-plot` 1/1, `panel` `{n_pages}`,
  `mode-banner` per page; configuration page: the L3 settings data-table. Kill: any
  census delta, any undeclared divergence, or the measure action uncovered
  (`classref_gate_uncovered`) — the widened L4 test must cover it via the plot figure.
- **A3 — the mockup-consistency arm (the L11 namesake).** A gateway test parses
  `docs/internal/ui-styleguide-mockups/class-dc_psu.html` with the stdlib parser,
  counts the contract hooks (post-RC-L11-3: `bw-reading`, `bw-alert-bubble`,
  `bw-plot`, `bw-data-table`) per theme section, and asserts the per-channel structure
  EQUALS the reference's resolved expectation over F-psu-2 (the mockup's single
  channel × 3 quantities = 3 tiles, 1 plot, 1 table, 1 alert surface present in the
  mockup and named by `cannot_derive.margin-alert`). **Kill (the falsifier the
  dispatch asked for): any disagreement between the mockup's counts and the resolved
  expectation — edit the mockup's card count and the test reds; edit the reference's
  derivation so the counts diverge and the test reds.** A mockup edit that does NOT
  redden the test is the instrument failing (report, don't pass).
- **A4 — RED control (pre-committed).** On today's main the same test file reds
  (`find_reference("otdp.dc_psu/1.0.0")` → None — verified: no class file exists), and
  `verify-ui` on a hand-minimal dc_psu baseline manifest FAILS with coverage findings
  naming configure/output/measure. The slice greens exactly these.
- **A5 — the analyser is untouched (byte-parity discipline).** The 0.3.0
  `class-logic_analyser.json` differs from 0.2.0's by the `contract_version` re-stamp
  only (sorted-key diff, the L5 verification method); the LA expansion fixtures
  regenerate byte-equal modulo version stamps; A1–A10/A11 of the program record and
  B1–B8 of the L5 record re-run green on the re-stamped corpus. Kill: any byte beyond
  the re-stamp, or any prior acceptance rule flipping.
- **A6 — D2 census.** The reference contains no numeric literals outside the
  structural set (layout spans, plot indices) and no data strings (no values, units,
  channel names, quantities — the quantity NAMES arrive via the descriptor at
  expansion, never authored in the reference). Machine-checked grep-level census. Kill:
  any authored data string.
- **A7 — corpus and version gates.** `benchweave.standards check` clean; `repin`
  wrote exactly the 4 new rows, 0 frozen-row rewrites; `matrix --check` clean; the
  served range admits all three family versions; the cross-constraints row names
  0.3.0. Kill: any frozen-row motion or served-set disagreement.
- **A8 — order gates.** The #408 order held (SDK PR → release cut → pointer commit →
  gateway merge); the lock anchor verified before the tag; gitlink and `.gitmodules`
  pin in one commit. Kill: any inversion.

**Underpowered branch:** if the census cannot key `reading-tile`/`engineering-plot` on
the contract surfaces the preview host actually emits (the §E.1 rows are the
authority; a renderer change that moves them reddens the harness first), that is a
measurement-instrument failure — reported, not a pass/fail on the increment. If the
series-derivation rule cannot stay D2-clean at build (a quantity-level selection the
descriptor cannot express structurally), **Shape B** activates (§1) and the plot
defers — that outcome is a result, not a failure.

## 7. Review tier and Step-1 keyword scan

**Tier 3** — touches `standards/` + JSON Schema files; advances the submodule pointer;
diff text carries `sha256` (4 corpus rows, sync/lock tests, this record). Two-lane
adversary pass and the standards-governor lane mandatory.

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~15–25 | 4 corpus rows, sync/fixture tests, this record |
| `hashlib` | ~2–4 | SDK derivation tests |
| `protection` | ~2–3 | this record's §C.1 prose only; zero in code |
| `threading` / `asyncio` / `subprocess` / `migrate` / `recovery` | 0 | in-process render; derivation, not migration |

## 8. Top risks, each with its falsifier

- **R1 — the series rule needs data.** If "every numeric scalar variable" cannot be
  derived structurally (a quantity selection with no structural basis), Shape A is
  falsified → Shape B (PATCH 0.2.1, plot deferred), disclosed on the PR.
- **R2 — the preview host's readings surface.** If the SDK host renders no
  reading-tile/plot surface the census can key on (the gateway's G2 page renders tiles
  from observations; the SDK host's readings-page composition is the build's
  verification), A2's census reds on instrument grounds — the underpowered branch, not
  a quiet pass.
- **R3 — the analyser regresses.** Any `_finish` generalization that shifts the LA
  derivation. Mitigated by A5's byte-parity arm; falsified by any LA fixture delta
  beyond version stamps.
- **R4 — mockup restyle breaks the consistency test.** Intended: the mockup is the
  spec, an edit forces re-derivation. The hook pass (RC-L11-3) moves the key from
  bespoke selectors to contract surfaces, shrinking accidental reds.
- **R5 — the directional-control gap is hand-authored around.** An overlay staging the
  output binding in both directions passes today's gate (the D7 slug set names only
  `abort`). Disclosed (§2.2), assigned to §C.1's enforcement slice, and named in the
  UI-GUIDE text — L11 does not build parallel safety machinery. Falsified only by
  that slice's own acceptance arms when it lands.
- **R6 — public-repo discipline.** The mockup's "PSU-01"/"BENCH A" and all fixture
  names are invented; no real bench, vendor or corpus identifier enters any committed
  file (the mockup predates this slice and already complies).

## 9. Deferrals, each with a home and a reopen trigger

| defers | home | reopen trigger |
|---|---|---|
| the directional output control (§2.2) | the §C.1 safety-behaviours enforcement slice + a family vocabulary widening in the next wall-payment event | that slice landing; or L14/L15/L16 (function_generator, electronic_load, smu) hitting the same toggle shape — they inherit whatever it builds |
| the staged setpoint knob idiom | the staging-over-preset capability (L5's batching rule family) | a class whose configure is field-stageable, or the owner calling the PSU setpoint surface |
| `waveform` plot kind | the family schema, on evidence | L13 oscilloscope |
| the five RC-L5-1 display idioms | unchanged (styleguide rule) | the first sweep class needing one — expected L13 |
| descriptor-derived channel enums (RC-L5-3 adjacent) | the expander's derivation vocabulary, WITH the directional control (they are only safe together) | same trigger as the directional control |
| the margin-alert and limit-overlay derivations | host composition + commissioned policy | a bench-supplied policy seam at preview (the D13 policy seam) |

## 10. Row-calls (numbered; the principal alone decides)

- **RC-L11-1 — the shape.** Shape A: MINOR 0.3.0 with the `time_series` plot template
  (recommended — the mockup's centerpiece is the trend, the widening is family-cheap,
  and L13 reuses the arm). Shape B: PATCH 0.2.1, plot deferred. Recommend ACCEPT A.
- **RC-L11-2 — the sweep cadence.** Per-class promotions (each landed class
  digest-served immediately; 11 SDK legs), the owner free to batch adjacent classes
  per the standing train rules; the dev-head alternative recorded and not recommended.
  Recommend ACCEPT.
- **RC-L11-3 — the mockup gains §E.1 component hooks.** A docs-side mockup edit
  making the consistency check contract-keyed (the analyser mockup's own convention).
  Recommend ACCEPT.
- **RC-L11-4 — the OTDP class example as the canonical expansion fixture.** The
  styleguide's analyser pairing, extended (an invented fixture only where the mockup's
  single-channel shape needs one). Recommend ACCEPT.

## 11. Precedent map (principle 9)

| L11 surface | in-tree precedent | why it fits |
|---|---|---|
| family MINOR widening by copy-never-move | 0.1.0→0.2.0 (L5) | same data-only multi-serving family, same re-stamp+one-widening shape |
| cross-constraints row amended in place | the RC-5 row's L5 motion | one honest window, re-cited |
| class page = committed expansion + drift guard | the analyser class-capture page (`tests/ui_html/test_classref_page.py`) | the styleguide's own rule, extended per class |
| expansion fixture = OTDP class example | the analyser pairing | same two-corpus-file contract |
| expander per-kind arms | L5's `_field_rows`/`_build_layout` kind mapping | additive arms beside untouched paths |
| gate census closure widening | L5's `census_map` trio additions | the closure moves with the inventory |
| pointer-in-the-corpus-PR | L1 PR #464, L5 PR-2 | zero observable served-set window |

## 12. Appendix — evidence and disclosures

**Pre-flight (the #181 R2 discipline):** `git fetch origin`; no open PRs in either
repo (gateway and SDK both queried); no remote branch touches
`standards/plugin-ui-class-reference/`, the mockups, or the sweep; the nearest live
branches (`fix/issue241-*`) are timing-test work touching test paths only.

**Gortex:** AVAILABLE to this subagent — the probe read
(`BenchWeave/standards/GOVERNANCE.md`) succeeded, diverging from the dispatch's
expectation and from the L5 session's #831-class refusal. The PreToolUse hook was
active (it blocked one symbol-colliding `grep` and attached read-calibration guidance);
all source reads after the probe went through `mcp__gortex__read`/`search`. The
worktree's `packages/sdk` is uninitialized; SDK source was served from the primary
checkout's submodule at pin `fca9c415` (= the v0.15.0 tag commit; `pyproject.toml`
0.15.0) — content identity holds for every SDK claim. No daemon restart, no tracking
change.

**Paths read as evidence:** `standards/GOVERNANCE.md`;
`standards/standards-manifest.json`; `standards/corpus-manifest.json` (family rows);
`standards/cross-constraints.json`; `standards/plugin-ui-class-reference/0.2.0/`
(`class-reference.schema.json`, `layout.schema.json`, `class-logic_analyser.json`,
`README.md`); `standards/plugin-ui/0.4.0/ui-manifest.schema.json` ($defs plot,
binding, target, page); `standards/otdp/0.2.3/device-profile-catalog.json` (the
dc_psu profile + three action schemas); `standards/otdp/0.2.3/examples/class-dc_psu.json`;
`standards/otdp/0.2.3/otdp-measurement.schema.json` ($defs dataset/variable);
`standards/otdp/0.2.3/device-classes.md` (§1 coverage table);
`docs/internal/ui-styleguide-mockups/class-dc_psu.html` and `class-logic_analyser.html`;
`docs/internal/ui-styleguide.md` ("Class-reference capture pages");
`docs/internal/ui-contract.md` (§C.1, §E.1); `packages/sdk/src/benchweave_sdk/
classref.py` (`find_reference`, `_resolve_channels`, `_ladder_level`,
`_build_expectation`, `_assemble`, `_finish`, `_derive_controls`) and
`classref_gate.py` (in full); `packages/sdk/pyproject.toml`;
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` (in full),
`2026-10-15-classref-l4-gateway-runtime-design.md` (header + §0–1),
`2026-10-16-classref-l5-plugin-ui-0-4-0-design.md` (in full); gateway issue #463
(all comments).

**Honest corrections to the dispatch's framing:** (a) the mockup carries zero §E.1
component hooks today — its 101 `bw-` occurrences are all CSS custom properties — so
"validated against the existing mockup" is only machine-checkable after the RC-L11-3
hook pass (or against bespoke selectors, strictly worse); (b) the dispatch named the
OTDP example at 0.1.2 — the active 0.2.3 copy is the right fixture, 0.1.2 being a
retained frozen predecessor; (c) the family range already admits a PATCH (`<0.3.0`),
so the version-event cost asymmetry is MINOR-vs-PATCH, not range-motion-vs-none —
recorded in §1 because it changes what Shape B costs.


---

## Addendum — the principal's row-call rulings and the build's landing shape (18 October 2026, post-build)

Recorded after the build pass; the body above is the frozen pre-committed
design and is not rewritten. The rulings:

- **RC-L11-1 — ACCEPTED, Shape A.** MINOR 0.3.0 with the `time_series`
  plot template: `page_template.plot.kind` widens const → enum
  `["digital_lanes", "time_series"]` with per-kind conditionals
  (`digital_lanes` keeps its group machinery and may not carry `series`;
  `time_series` adds `series: "numeric_variables"` and may not carry the
  group machinery); `waveform` deliberately not admitted.
- **RC-L11-2 — BATCHING chosen, not per-class promotion.** This slice
  lands the corpus (the 0.3.0 family version), the `class-dc_psu.json`
  reference, the pattern-library output page, the mockup hook pass and
  the gateway-side tests, and does NOT cut the SDK release and does NOT
  advance the gateway pointer — the version promotion's SDK leg (the §3
  widening inventory, the vendored ingest, the 0.16.0 release) batches
  with the adjacent class (L12 `dmm`) per the bump-minimization train
  rule. Consequence, disclosed: the branch carries the sync-pair reds
  (`served_set_drift`, `sdk_version_mismatch`, `policy_mirror_drift`,
  the stale-generated family) for the batch's authoring window — the L5
  precedent's branch-internal red, now longer-lived by the owner's
  batching decision, never merged red; the merge gate is the batched
  promotion's pointer leg, per issue #408's order. A4's `verify-ui`
  coverage half defers with the same leg (the SDK's vendored corpus
  carries no dc_psu reference until then); A4's `find_reference` RED was
  demonstrated on today's tree (SDK-side `None`, gateway-side
  `select_references` → `None`) and greens gateway-side in this slice.
- **RC-L11-3 — ACCEPTED.** The mockup carries the §E.1 component hooks
  (`bw-reading` on the cards, `bw-alert-bubble` on the aside, `bw-plot`
  on the trend figure, `bw-data-table` on the table); the
  consistency check keys on the contract surfaces.
- **RC-L11-4 — ACCEPTED.** The ACTIVE `standards/otdp/0.2.3/examples/
  class-dc_psu.json` is the canonical expansion fixture (F-psu-1); the
  mockup-shaped single-channel fixture (F-psu-2) derives from it in-test.

Build-time verifications this addendum records (each with its evidence in
the build log/commit message): the analyser re-stamp is exactly one line
(`/contract_version`, sorted-key diff); the copy-never-move proof holds
(six predecessor files byte-identical to the pre-change tree); repin
wrote exactly 4 rows with 0 frozen-row rewrites; the parity fixtures
regenerated stamp-only (8 lines across 8 files), with the SDK derivation
at the pin reproducing the pre-bump committed bytes exactly before the
regeneration; the gateway's `compose_layout_sections` already renders
`reading-tile` and `data-table` nodes with the ghost-binding honesty arm
(the design's §3 build-time verification — the arm is NOT missing; no
gateway runtime motion rides this slice); the mockup's existing test arms
all stay green through the hook pass (nothing weakened).


### Refute fold (18 October 2026, post-review)

The adversary pass returned no CRITICAL; the corpus motion and
copy-never-move survived independent re-execution. Four findings folded:

- **F1 — the A3 census was placement-blind.** The count arms conserved
  under a structural lie: `bw-reading` moved off a readings card onto the
  staged-control card (a `cannot_derive` surface that must never present
  as a reading) kept every count and every test green. The census now
  records each hook's tag and ancestors and asserts the placement
  contract — every hook on its §E.1 root element (`bw-reading` article,
  `bw-alert-bubble` aside, `bw-plot` section, `bw-data-table` table),
  the container-scoped hooks in their mockup containers (readings row,
  lower grid), and the staged-control card carrying NO `bw-` hook. The
  reviewer's mutation now reds (`assert 'section' == 'article'`) while
  the count arm stays green under it — the hole is closed, demonstrated.
- **F2 — the body's "No ui-html motion" sentence, corrected here rather
  than rewritten above.** The RENDERER claim is true (the §E.1 partials
  pre-exist, `partials.py` untouched, no renderer change), but the arc
  lands +204/+23 in `packages/ui-html` (the pattern-page composition
  module and its PATTERNS entry), so the repo's benchweave-ui-html 0.3.0
  exceeds the published 0.3.0. **RULING: cut benchweave-ui-html 0.3.1
  with the batched promotion leg** (the SDK `[server]` extra's exact pin
  moves with it); the divergence is bounded by that leg, never
  indefinite.
- **F3 — RULING (a convention for every later bump): a cross-constraints
  row is RETAINED while its version stays served.** This bump ADDS the
  0.3.0 row beside the 0.2.0 row instead of amending it away — the L5
  in-place amendment left 0.2.0-pinned consumers with no plugin-ui
  requirement (the loader skips rows whose version differs from the
  resolved pin), and the loader admits both rows, so the safer direction
  is free. A served pin never loses its constraint.
- **F4 — named deferral: `series` is optional on `time_series` with
  exactly one legal value, and its semantics live in the unbuilt SDK
  expander — a series-less `time_series` document is schema-valid today
  with undefined expansion behaviour.** Home: the L12 batched SDK
  widening design, where the expander is built and the field is made
  required or its absent-semantics pinned. Not changed in this bump (a
  schema motion here would be a second bite at the widening).
