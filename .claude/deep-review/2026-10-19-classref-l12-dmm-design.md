# L12 — the class sweep continues: `otdp.dmm` class reference + the batched promotion leg (mockup authored)

**Date:** 19 October 2026
**Slot:** L12 of the class-reference train (parent gateway issue #463; program record
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` §7A row L12, §8's
RC-1/E-1 rows; the sweep order L11 dc_psu → **L12 dmm** → L13 oscilloscope … L21 vna,
verified this pass against BOTH §7A and the workbench §8 table
(`docs/internal/ui-styleguide-workbench-design.md` §8: "DC power supply; **digital
multimeter**; oscilloscope; …", the analyser delivered earlier by the program itself).
**Branch:** `feat/l12-dmm-classref`, cut from `origin/feat/l11-dcpsu-classref` `96c8dd9d`
(held stacked, unmerged — the batch stacks on it by design).
**Worktree:** `.wt/l12-d4m9/`. Evidence baseline: the L11 branch head `96c8dd9d`, SDK
pinned at `fca9c415` = v0.15.0 (L11's verification stands), plugin-ui 0.4.0 active,
plugin-ui-class-reference **0.3.0 active on the branch** (range `>=0.1.0,<0.4.0`,
unreleased — no SDK leg yet, per RC-L11-2's batching), OTDP 0.2.3 active,
`benchweave-ui-html==0.3.0` published, 0.3.1 ruled by L11's F2 to cut with this batch.
**Binding design points:** the program record D1–D14 (esp. D2 structure-not-data, D13
effective capability, D14 coverage); the L11 record in full including its addendum
(RC-L11-1..4 rulings) and its refute fold (F1 placement-aware census, F2 ui-html 0.3.1,
F3 cross-constraints retention, F4 the `series` deferral whose recorded home is "the L12
batched SDK widening design" — this record); GOVERNANCE's bump-minimization train rule
and G-5 pacing.

## 0. Summary and design thesis

L12 authors the third class reference — `class-dmm.json`, binding `otdp.dmm/1.0.0` —
**and authors the mockup it is validated against** (there is no `class-dmm.html` today;
`docs/internal/ui-styleguide-mockups/` holds only `class-logic_analyser.html` and
`class-dc_psu.html`), then performs the batched promotion leg L11 deferred here
(RC-L11-2): the SDK widening build, SDK 0.16.0, ui-html 0.3.1, the pointer advance. The
thesis in one line:

> The DMM is the first **observation-pure** class — no sourcing action, no directional
> safety surface, no capture view — so everything its page needs is already in the 0.3.0
> vocabulary dc_psu widened to; dmm adds **zero family-schema surface** and exactly one
> corpus file, while the slice's only schema motion is the F4 settlement (`series`
> becomes required on `time_series`), made inside the same unreleased 0.3.0 window.

Three grounding facts fix the scope, each verified in the worktree this pass:

1. **The dmm profile is two required actions and nothing else**
   (`standards/otdp/0.2.3/device-profile-catalog.json`, profile `otdp.dmm/1.0.0`):
   `required_actions: [configure, measure]`, `optional_actions: []`,
   `channel_roles: ["measure"]`. There is no output/energise action — the §C.1
   directional problem that shaped dc_psu's birth deviations (§2.2 of the L11 record)
   **does not exist for this class**. Its `configure` input requires
   `configuration_id` (string), `channel` (pattern string), `function` (an 11-value
   enum: voltage_dc … diode, **including `frequency`**), `range` (auto|fixed object),
   `aperture` (seconds|nplc object) and `autozero` (boolean) — L3
   configuration-shaped, preset-mediated at birth exactly like dc_psu's. Its `measure`
   input requires `channels` (array) + `configuration_id`; its output is the
   measurement-model dataset (`urn:otdp:measurement:0.2.3#/$defs/dataset`) — the same
   scalar shape dc_psu's widening already derives.
2. **The OTDP class example exists and is sufficient as the sole expansion fixture**
   (`standards/otdp/0.2.3/examples/class-dmm.json`): 2 `measure`-role channels
   (`ch1`/`ch2`), each declaring `quantities: [voltage]`; both actions declared with
   empty `input_constraints`; pinned contracts for the catalog and the measurement
   schema. Per RC-L11-4's ruling this is the canonical expansion fixture (F-dmm-1);
   unlike L11, **no derived single-channel fixture is needed** — the mockup is authored
   to the example's own shape (2 channels × 1 quantity = 2 tiles), so the A3 census
   resolves over the committed example directly and F-dmm-2 does not exist.
3. **The family vocabulary is ahead of what dmm asks for.** The 0.3.0 schema's
   `page_template.plot` already carries `time_series` with the `numeric_variables`
   series rule dc_psu added; `slot.when_declared` (boolean, on dataset/configuration/
   procedure slots) already exists for a future optional-action landing; page kind
   `readings` and the layout `reading` nodes (reading-tile, data-table) are in
   vocabulary; the §E.1 inventory ships every component the page composes
   (reading-tile, engineering-plot, data-table, alert-bubble, mode-banner, panel). The
   dmm reference is expressible **without widening anything** — the good result §3
   states and defends.

## 1. The governance answer first: adding to the unreleased 0.3.0 is the batch rule, not a copy-never-move violation

The dispatch asked this reading verified against `standards/GOVERNANCE.md`. It holds,
on four independent grounds:

- **The train rule is explicit.** "Queued changes to the SAME standard that share a
  train batch into a single bump (one copy step from the current active version, one
  repin); a batch's bump follows the highest change class it contains." L11's PR is
  held unmerged; L12 opens against the same merge window stacked on L11's branch. The
  0.3.0 copy step already happened (L11); `class-dmm.json` and the §5 schema
  tightening join the SAME bump. "Never stack a bump on an unmerged bump" governs a
  SECOND bump (a 0.4.0) on top of an unmerged 0.3.0 — L12 creates no new version
  directory, so the rule is not engaged. The batch's highest class remains MINOR (the
  plot widening; everything L12 adds is inside that MINOR).
- **G-5 pacing governs new version directories, not in-window edits.** "The commit
  adding a new version directory of standard S must arrive on a tree whose SDK lock
  already carries S's previous released version." The 0.3.0 directory was added by
  L11's commit on a tree whose lock carries 0.2.0 (verified at L11). L12 adds no
  directory; its batch performs 0.3.0's outstanding SDK leg — the leg G-5 exists to
  pace.
- **Copy-never-move protects retained versions, and 0.3.0 is not one yet.** "The old
  dir and its corpus-manifest rows stay in place, digest-frozen" — the old dir is
  0.2.0, untouched by this slice (byte-parity asserted, A5). 0.3.0's rows exist only
  on the unmerged branch; "immutability starts at release", and under R-2 multi-version
  serving no consumer can pin 0.3.0 until the batch merges and serves it — there is no
  digest promise to break. Editing 0.3.0 bytes in-window is the ordinary edit → repin
  loop the dev-stage section describes for pre-release authoring ("pre-release
  authoring accumulated on a dev head is not a bump and waits for nothing" — the same
  principle, here on a stacked branch instead of a `-dev` directory).
- **The L11 rulings already walked this path.** RC-L11-2 batched the SDK leg into L12
  by name; F2 cut ui-html 0.3.1 "with the batched promotion leg"; F3 added the 0.3.0
  cross-constraints row beside 0.2.0's — all post-cut motions to the same unreleased
  surfaces. This record extends the same window once, then closes it: **after the
  batch merges, 0.3.0 is frozen like every released version, and L13's class lands in
  the next bump under its own train rules.**

What the window does NOT license: any motion touching 0.2.0/0.1.0 bytes (A7 asserts
zero frozen-row rewrites), any new family version (no 0.4.0 is invented), and any edit
to the two already-committed 0.3.0 class documents beyond what the F4 settlement
itself requires (none — `class-dc_psu.json` and `class-logic_analyser.json` are
byte-identical through this slice, A5; the dc_psu reference already carries
`series: "numeric_variables"`, verified this pass, so the tightening breaks no
committed document).

**No manifest, range, or cross-constraints motion rides L12.** 0.3.0 is already the
active entry on the branch; the dependency_policy range `>=0.1.0,<0.4.0` already
admits it; F3's retention keeps both the 0.2.0 and 0.3.0 cross-constraints rows and
dmm changes the 0.3.0 row's substance not at all (the plugin-ui floor is unchanged —
dmm consumes vocabulary 0.4.0 already ships, like dc_psu). One corpus row is added
(`class-dmm.json`); one existing row's digest moves (the schema edit, §5).

**The OTDP `dmm` example, and how it relates.** Same relationship L11 established:
`standards/otdp/0.2.3/examples/class-dmm.json` is the canonical expansion fixture —
the descriptor the reference is expanded against in tests and the pattern page — never
a presentation reference itself. OTDP answers what a dmm must admit; this family
answers how the class presents.

## 2. The dmm mockup (authored — the spec this time, not the inherited one)

L11 inherited its mockup; L12 writes one. `docs/internal/ui-styleguide-mockups/
class-dmm.html` is authored to the dc_psu convention — one composition, two
`data-theme` sections (light/dark) over the shipped token set, self-contained, ~13 KB,
invented identifiers only (`DMM-01`; public-repo discipline) — with the two L11
lessons built in from birth so **no hook-pass follow-up is owed**:

- **§E.1 component hooks from birth** (RC-L11-3's convention, not its retrofit):
  `bw-reading` on the reading `article` cards, `bw-alert-bubble` on the alert
  `aside`, `bw-plot` on the trend `section`, `bw-data-table` on the `table` — hooks on
  their §E.1 ROOT elements, keying the consistency check on contract surfaces.
- **The F1 placement contract from birth**: every hook on its root tag, the
  container-scoped hooks inside their containers (`bw-reading` only in the readings
  row, `bw-plot` only in the lower grid), and the preset-preview control card carrying
  NO `bw-` hook — a cannot-derive surface must never present as a reading.

**What a digital multimeter's class page shows, and why** (each element traced to the
class's nature — a multi-function measuring instrument whose channels observe one
selected function at a time):

| element | disposition |
|---|---|
| title row + `Controls` button | page chrome/navigation — host territory, as dc_psu |
| readings row: 2 `bw-reading` cards (ch1 · voltage, ch2 · voltage), one carrying the `warning` variant, each with a quality line | **derives**: one reading-tile per (channel, quantity) of the example's declared measure channels (2 × 1); the count is an expression at expansion, never the literal 2; severity is runtime observation state — structure renders the variant, data decides it |
| quality lines (`✓ NORMAL · 84 ms`) | observation quality/freshness (§B/ST-4 machinery; runtime data) |
| alert aside: "Range margin — reading approaching configured range limit" | **cannot_derive** `range-margin-alert` — the condition (reading vs configured range) is commissioned policy (A02), the exact shape of dc_psu's `margin-alert` with the dmm's own quantity |
| lower grid: preset-preview control card (`FUNCTION · V DC / AUTO / 1 PLC`, `PRESET · APPLY REQUIRED` line) | **cannot_derive** `function-selection` — configure is preset-mediated at birth (its `function` enum, `range`/`aperture` objects and `autozero` boolean are inexpressible at L2; presets are commissioned evidence, A02) |
| recessed trend plot "READINGS · LAST 60 SECONDS": two traces (ch1/ch2 voltage) + a dashed range-bound line | **derives**: one `time_series` plot over the measure slot, one series per numeric scalar variable (2 variables → 2 traces); the dashed bound is **cannot_derive** `range-overlay` — a runtime join against the active configuration |
| Channel / Reading / Quality table (2 rows) | **derives**: one `data-table` reading node over the same dataset, one row per (channel, quantity) |

The layout is the dc_psu ratio — readings 12 raised, trend 7 recessed, table 5 raised —
a deliberate authoring choice: the digit trend earns the wide span on a bench DMM
(watching drift is the trend's whole job), and the class's difference from dc_psu is
content, not geometry. The styleguide's mockup index line gains `class-dmm.html`
beside the existing two; the styleguide gains the dmm class-page row beside dc_psu's.

**The function-exclusivity question, answered honestly and deferred by name.** A DMM's
declared quantities are alternative functions, not concurrent measurements — unlike a
PSU's V/I/P. The structural derivation (one tile per declared (channel, quantity))
does not distinguish: for a descriptor declaring many functions it renders many tiles
with at most one live per channel, and the inactive ones render through the
ghost-binding honesty arm already shipped in the gateway composition (the L11
addendum's verification). That is honest at this fixture's shape (1 quantity per
channel — no exclusivity tension displays at all), and the deeper presentation
question — whether a many-function descriptor wants a function-switched single-reading
view instead of a tile per function — is **not** settled here: it is a named deferral
(§9) with the real-descriptor trigger. No widening is speculated for it (principle 9:
no class in this slice needs it).

## 3. The reference, derived from the mockup

`standards/plugin-ui-class-reference/0.3.0/class-dmm.json` — structure-not-data (D2),
same posture as dc_psu: authored structural strings only; every count an expression;
every quantity name arriving via the descriptor at expansion.

**Slots** (URNs verified against the catalog this pass):

| key | kind | resolves |
|---|---|---|
| `inputs` | `channels`, `where_role: "measure"` | the declared measure channels, declaration order (the role-named-key convention dc_psu's `outputs` set) |
| `measure` | `dataset`, action `otdp.dmm.measure/1.0.0`, `schema_source: "output_measurement"` | the scalar dataset; one numeric variable per (channel, declared quantity); `x` = the time axis — identical derivation to dc_psu's |
| `configure` | `configuration`, action `otdp.dmm.configure/1.0.0`, `schema_source: "input_schema"` | the settings schema (configuration_id, channel, function, range, aperture, autozero) |
| `vendor_actions` | `vendor_actions` | D14 hook for unclaimed URNs |

No `when_declared` slots (the profile has no optional actions — verified). No
procedure slot (no output action exists). `host_supplied` empty on every slot, the
dc_psu posture: dataset slots derive no control, and configure is preset-mediated
outright.

**Pages** (three, the family's standing count):

1. **Readings** (`kind: readings`, `binding_slots: [measure]`, `plot: {kind:
   time_series, over_slot: measure, series: numeric_variables}`) — the mockup's
   composition: readings section (raised, 12), trend section (recessed, 7) carrying
   the plot, table section (raised, 5) carrying the data-table node.
2. **Configuration** (`kind: configuration`, `binding_slots: [configure]`) — the
   preset-mediated settings surface; `preset_asset_ids: []` at birth (the RC-6
   scaffold rule).
3. **Device features** (`kind: configuration`, `binding_slots: [vendor_actions]`,
   `vendor_features: true`) — D14's placement row, both precedents' shape.

**expect.components**: `reading-tile` `{n_reading_tiles}` on the readings page;
`data-table` `1` on the readings page; `engineering-plot` `1` on the readings page;
`panel` `{n_pages}`; `mode-banner` `1` per page (`per_page: "*"`). **expect.controls**:
one row — `otdp.dmm.configure/1.0.0: "preset"`. `measure` needs no controls row
(dataset slots are page-covered, fetch's own shape). The counter closure names are
role-generic (`n_measure_channels` beside dc_psu's `n_source_channels`;
`n_scalar_variables`, `n_reading_tiles`, `n_pages` shared) — the SDK's `_EXPECT_NAMES`
closure gains the names; the closure discipline is the invariant, exact names are
build detail (L11 §3 item 5's posture).

**forbid**: three ids — `confirm-wrapped-run-action` (vacuously true at birth, the
family-generic carry), `color-role-hint-on-lane`, `untraceable-lane-label` (carried as
family-generic, both precedents' convention). `intermediated-energy-removing-action`
is **dropped, with the reason recorded**: dc_psu's carrying it was a class-intent
declaration ("declares the class's intent even though the gate's slug set does not yet
name output" — L11 §2); dmm has no energy-removing action and cannot acquire one
within its profile, so the intent declaration would be vacuous about a surface that
cannot exist. Forbid is per-reference authored data; the set is not family-fixed.

**cannot_derive** (five rows, each traced to a mockup element):

| id | aspect | reason | author_action |
|---|---|---|---|
| `function-selection` | the function/range/aperture/autozero selection surface | configure is preset-mediated at birth; presets are commissioned evidence (A02) | author `ui/presets/*.json` via check-preset; the expander emits the scaffold |
| `range-margin-alert` | the range-margin alert | the alert condition (reading vs configured range) is commissioned policy (A02) | bench policy at commissioning; the alert-bubble renders from host-observed conditions |
| `range-overlay` | the trend's dashed range-bound line | the range value is runtime configuration data; the overlay is a runtime join | host composition where a fixed range is active |
| `presets` | preset settings values | commissioned evidence, never derived (A02 unamended) | check-preset |
| `channel-names` | input names beyond descriptor labels | the descriptor owns channel identity | label channels in the descriptor |

**How dmm differs from dc_psu, and the widening answer: nothing — a good result,
stated.** The differences are all inside the existing vocabulary: the channel role
(`where_role` is a free string); two actions instead of three (fewer slots, no
procedure slot); no energy action, hence no directional §C.1 surface, hence no
`output-control` deviation and no energy forbid id; one controls row instead of two;
the class-specific cannot_derive set. The family schema, the layout vocabulary, the
plugin-ui manifest vocabulary and the renderer all carry what the page composes
unchanged. The SDK expander/gate inventory L11 designed (§3 items 1–8 of the L11
record) is class-shape-generic once built — dmm exercises the same
dataset-by-shape/observation/readings/time_series arms dc_psu drives, and adds only
counter names. **No family widening is requested; if the build falsifies this (a dmm
surface the vocabulary cannot express), that is the disclosed underpowered branch and
it comes back as evidence, not as a silent scope creep.**

## 4. E-1: L12 is NOT the slot where the promotion evidence is checkable — and what L12 owes it instead

The program record ties an optional-action promotion to registry evidence at the dmm
profile (§2.5, the frequency-counter criterion): promotion to a dmm optional action
requires "at least one real admitted plugin whose frequency surface's action I/O maps
1:1 onto the dmm profile's scalar measurement model", landing as an OTDP catalog
revision with vectors. Checked against this pass's evidence:

- **The evidence lives in the production registry, not in this tree.** The registry
  corpus carries zero frequency surfaces (searched this pass); the tree's registry
  fixtures are invented specimens by design, and the workbench's own §8 caveat ("They
  do not claim that runtime bridges or physical hardware implement every illustrated
  action") bars minting "real admitted plugin" evidence from fixtures. A sweep design
  slot cannot create the evidence; only an admitted plugin can.
- **The promotion lands in a different standard.** An OTDP catalog revision (dmm
  gains an optional action + vectors) is an otdp-family bump with its own train
  rules — not a plugin-ui-class-reference motion. E-1 is a **standing, event-driven
  slot** by the program record's own wording ("the dmm-optional / new-class landings
  mint when their evidence conditions fire"), not a numbered landing.
- **The evidence question is narrower than it reads.** dmm's `configure.function`
  enum already includes `frequency` (verified this pass) — a plugin whose frequency
  surface maps onto configure(function=frequency) + measure needs NO promotion at all;
  it conforms today. The E-1 evidence concerns vendor frequency-counter profiles
  whose action I/O does NOT fit the required pair.

What L12 owes E-1, and delivers in this design: (a) the **landing seam already
exists** — the 0.3.0 schema's `when_declared` boolean on action slots (verified) means
the promoted optional action lands in `class-dmm.json` as a `when_declared: true`
slot, with a family bump only if it needs presentation structure the vocabulary lacks;
(b) a **recorded reopen trigger** (§9): when the OTDP dmm profile gains an optional
action, the reference gains the slot and the mockup/composition decide its surface,
under the then-current train rules; (c) this section itself — the slot where the
question was checked and answered, so E-1's minting moment finds the record.

## 5. The `series` deferral (L11 F4) — settled: required

F4's record: `series` is optional on `time_series` with exactly one legal value, its
semantics live in the unbuilt SDK expander, so a series-less document is schema-valid
today with undefined expansion behaviour; home "the L12 batched SDK widening design".
This is that design, and the ruling is **make `series` required on `time_series`**:

- The expander objection dissolves in this very batch — the SDK widening (L11 §3
  item 3) is built here, so the field's semantics stop living anywhere but code and
  schema at merge time.
- **Zero committed documents break.** The only time_series documents in the corpus —
  dc_psu's committed reference and this slice's dmm reference — both carry
  `series: "numeric_variables"` (dc_psu's verified this pass). The analyser's
  `digital_lanes` plot forbids the field by its existing conditional. The tightening
  changes validity for exactly the documents that do not exist.
- The schema's own style is const-pinned explicitness (`contract_version`, `key`,
  `label`, `group_size` are const-required); a one-legal-value field that may be
  silently omitted is the odd shape, and absent-semantics (the alternative) would
  leave two spellings of one meaning and push a default into every consumer — the
  ambiguity F4 named, resolved by convention instead of constraint.
- Future widening (a second series rule, e.g. for a waveform class) is an ordinary
  MINOR enum-widening of the field — no breaking motion is created.

**The motion**: one conditional edit in `class-reference.schema.json`'s
`page_template.plot.allOf` — the `time_series` branch adds `"required": ["series"]`
beside its existing group-machinery ban. The row's digest moves via repin (the row
exists; no new row). The RED arm is pre-committed below (A9): a time_series plot
template without `series` must FAIL validation after the edit, and both committed
class documents must still pass.

## 6. The A3 extension for dmm — one instrument, not a second

`tests/ui_html/test_classref_dmm.py` extends L11's instrument rather than inventing a
parallel one. Mechanics: the placement-aware `_HookCensus`, the `HOOKS` tuple and the
placement contract lift into a non-test helper module
`tests/ui_html/classref_census.py` — the suite's existing idiom for exactly this
(`colour_instrument.py`, `thresholds.py` are non-test helpers imported by test
modules; `tests/ui_html` has no `__init__.py`, so helper imports are the established
path, not cross-test-module imports). `test_classref_dc_psu.py` switches to the
import: **one mechanical L11-file motion inside the batch window, every L11 assertion
byte-identical** — disclosed here, justified by the alternative being worse (a forked
census is F1's lesson generalized: the instrument itself must not drift between
classes). The dmm module then carries the arms:

1. **Hooks in both themes** — every hook family ≥1 per theme section.
2. **Hook counts EQUAL the resolved expectation over the committed OTDP example**
   (2 channels × 1 declared quantity = 2 tiles, 1 plot, 1 table; no derived fixture —
   the mockup is authored to the example's shape). Both kill directions by
   construction: a mockup edit that changes a count reds against the resolved side; a
   reference edit that changes the derivation (a count expression, the plot binding,
   the channels slot's role) reds against the mockup's counts. A mockup edit that
   does NOT redden the test is the instrument failing — report, never a quiet pass.
3. **Placement, including the count-conserving-move kill L11's refute proved
   necessary**: every hook occurrence on its §E.1 root tag (`bw-reading` → `article`,
   `bw-alert-bubble` → `aside`, `bw-plot` → `section`, `bw-data-table` → `table`),
   the container-scoped hooks inside their containers (readings row, lower grid), and
   the preset-preview control card carrying NO `bw-` hook. The RED arm moves a hook
   count-conservingly (a `bw-reading` onto the control card; a `bw-plot` out of the
   lower grid) and the placement assertions red while the count arm stays green under
   the move — the mutation is demonstrated to kill, not assumed.
4. **Theme-invariance** — the hook census is identical across themes.
5. **The alert is one per theme and a named cannot_derive** (`range-margin-alert`).
6. **Selection RED-to-green** — `select_references` over the dmm example returns one
   reference, `otdp.dmm/1.0.0` (None today: verified on the L11 branch head this
   pass, with dc_psu resolving at the same time — the pair that banks A4's RED half).
7. **The pattern-page arms** (the drift guard over `render_dmm_readings_page`):
   tiles 2 × 1 derived from the corpus pair, never literals; labels are corpus
   strings (channel labels × quantities); one plot, both channel traces; the table's
   body one row per pair; the sections mirror the reference layout block's surfaces
   and spans; only §E.1 partials compose; no control surface fabricated (no button,
   no rotary, no confirm); the PATTERNS census entry is `kind: class-page`, `row_id:
   plugin-ui-class-reference::class-dmm`, `fixture_id: readings`; both themes export.

## 7. The batched promotion leg (RC-L11-2's leg, performed here)

The L11 batch deferred the SDK leg to L12; this slice performs it, in the #408 order:

1. **Gateway branch content** (this slice's corpus + docs + tests, §8 below), with
   the branch-internal sync-pair reds L11 disclosed continuing until the pointer leg
   (never merged red).
2. **ui-html 0.3.1** (F2's ruling): the dmm composition page + PATTERNS entry land in
   `packages/ui-html` (`classref.py` gains the dmm composer beside the analyser and
   dc_psu ones — the module's standing per-class shape); the version motion and its
   release event ride this batch. The dc_psu composition's +204/+23 divergence from
   published 0.3.0 is bounded here, as F2 ruled.
3. **SDK PR, opened NOW** (stacked per #69 where a predecessor lives; body notes
   gateway #463, no SDK-side issue by design): the L11 §3 widening inventory
   (dataset-by-shape, observation targets/bindings, time_series emission, layout
   reading nodes, counter closure incl. the role-generic names, gate census arms for
   `reading-tile`/`engineering-plot`, the L4 coverage widening, the D2 census guard),
   the vendored ingest of the amended 0.3.0 (four files + `class-dmm.json`; the
   `active` marker already points at 0.3.0's row set in the ingest), dmm fixtures
   (the OTDP example as F-dmm-1; refusal fixtures: zero measure channels → the
   channels-slot refusal; absent required action → `classref_required_action_absent`),
   `pyproject.toml` 0.16.0, the `[server]` extra's `benchweave-ui-html` pin → 0.3.1,
   the lock anchor `compatibility.sdk = "0.16.0"` before the tag.
4. **SDK release cut** `v0.16.0` (`make release-cut VERSION=v0.16.0`, with the
   release-review matrix walked).
5. **Pointer-advance commit on the gateway branch** (gitlink → the v0.16.0 tag
   commit; `.gitmodules` `pin`; `sdk_compatibility` mirror; matrix render) — the
   branch goes green; merge under the full-rollup gate (`scripts/merge-verified.sh`),
   zero fail, zero pending.

The standards tripwire fires by design (non-empty `standards/` diff); this record is
the named sanction. Standards-governor lane mandatory; two-lane adversary pass on the
built slice (the refuted-then-folded posture L11 ended on, from birth this time).

## 8. Corpus-motion census (exact bytes)

Gateway repo, `standards/`:
- **Added** `standards/plugin-ui-class-reference/0.3.0/class-dmm.json` — one new
  corpus row, `source` citing the authoring staging path
  `docs/plugin-ui-class-reference-v2/class-dmm.json` (removed in-PR — the founding
  convention `class-dc_psu.json`'s row set).
- **Edited** `standards/plugin-ui-class-reference/0.3.0/class-reference.schema.json`
  — the §5 conditional only; the row's digest moves via repin, no new row.
- **Unchanged**: `standards-manifest.json` (0.3.0 already active on the branch — no
  motion), `dependency_policy` (range already `<0.4.0`),
  `cross-constraints.json` (both rows stand, F3), `class-logic_analyser.json` and
  `class-dc_psu.json` (byte-identical, A5), every 0.2.0/0.1.0 byte (zero frozen-row
  rewrites, A7).
- **Unpinned prose**: the family `README.md` (files-table row for `class-dmm.json`;
  the forbid-list prose needs no motion — it documents the mechanism, not a fixed
  id set); `docs/internal/ui-styleguide.md` (the dmm class-page row; the mockup
  index line gains `class-dmm.html`).

Gateway repo, docs/tests (no corpus impact): `docs/internal/ui-styleguide-mockups/
class-dmm.html` (new, prose-adjacent — no corpus rows, no governance event);
`tests/ui_html/classref_census.py` (the shared census helper); `tests/ui_html/
test_classref_dmm.py`; the `test_classref_dc_psu.py` import switch.

`packages/ui-html`: the dmm composer + PATTERNS entry (rides the 0.3.1 cut).

SDK repo (v0.16.0): the §7 item-3 set. **No otdp motion of any kind** — E-1's
promotion is not this train's to land (§4).

## 9. Deferrals, each with a home and an observable reopen trigger

| defers | home | reopen trigger |
|---|---|---|
| multi-quantity/function-exclusivity presentation (tile-per-function vs function-switched view) | the expander's derivation vocabulary + this family, on evidence | the first real admitted dmm descriptor declaring ≥2 quantities on one channel — the moment the uniform-tile presentation meets its operator test |
| aggregate readings presentation (min/max/avg tiles) | host composition / dataset variables | a class page whose example declares aggregate variables, or an owner call at a real bench |
| E-1's dmm-optional promotion | the registry evidence event + an OTDP catalog revision; the family landing is the `when_declared` seam (§4) | the evidence condition firing on real admitted plugins |
| the five RC-L5-1 display idioms | unchanged (the styleguide rule) | L13 oscilloscope remains the expected caller — dmm has no lanes/capture view and needs none (honest negative, stated) |
| `waveform` plot kind | the family schema, on evidence | L13 oscilloscope |
| range-margin-alert / range-overlay derivations | host composition + commissioned policy | the D13 policy seam at preview |

## 10. Acceptance rules (pre-committed — written before any build output)

Deterministic census over the fixed fixture set (the committed OTDP dmm example, the
refusal fixtures, the banked baselines). Denominators named; both kill directions
stated; the underpowered branch named. These rules bind the build agent.

- **A1 — expansion is valid and example-shaped.** `derive-ui` on the dmm example
  produces a manifest set passing `validate_presentation`, with the readings page
  carrying an observation binding, a `time_series` plot over the measure slot with
  `series: numeric_variables`, and 2/2 derived reading tiles (2 channels × 1 declared
  quantity — counts from the derivation, never literals). Kill: any count off, any
  validation failure, or a tile variable not traceable to a (channel, quantity) pair.
- **A2 — the gate passes with the birth deviations REPORTED.** `verify-ui` on the
  example exits 0 with a REPORTED deviation for `configure` (preset-mediated), none
  silent; the census on the readings page reads `reading-tile` 2/2, `data-table` ≥1,
  `engineering-plot` 1/1, `panel` `{n_pages}`, `mode-banner` per page; `measure` is
  covered via the plot figure (the widened L4 arm). Kill: any census delta, any
  undeclared divergence, or `classref_gate_uncovered` naming measure.
- **A3 — the mockup-consistency arm (the namesake).** §6's arms over
  `class-dmm.html` × the reference × the example, with the count kill both ways and
  the count-conserving-move kill demonstrated RED (a hook moved to the control card
  or out of its container reds while counts conserve). **The falsifier: any
  disagreement between the mockup's counts or placements and the resolved
  expectation; a mockup edit that does NOT redden the test is the instrument
  failing — reported, never a pass.**
- **A4 — RED control (banked at design time).** On the L11 branch head
  `96c8dd9d`: gateway-side `select_references` on the dmm example → None, with
  dc_psu resolving — executed and recorded this pass (the pair, not a claim). SDK-side
  `find_reference("otdp.dmm/1.0.0")` → None until the ingest; the slice greens both
  halves. Kill: either half green before its landing commit exists.
- **A5 — the predecessors are untouched.** `class-logic_analyser.json` and
  `class-dc_psu.json` byte-identical through the slice (sorted-key diff = empty); the
  only `test_classref_dc_psu.py` motion is the census import (assertions
  byte-identical); the full L11 test module re-runs green. Kill: any byte beyond the
  disclosed motions, or any prior acceptance rule flipping.
- **A6 — D2 census on the dmm reference.** No numeric literals outside the structural
  set (spans ≤12, plot indices); no data strings (no values, units, channel names,
  quantity names). Machine-checked census. Kill: any authored data string.
- **A7 — corpus and version gates.** `benchweave.standards check` clean; `repin`
  writes exactly ONE new row (`class-dmm.json`) and moves exactly ONE existing row's
  digest (the schema edit), with ZERO frozen-row rewrites (every 0.2.0/0.1.0 row
  byte-identical); `matrix --check` clean; the served set and range unchanged. Kill:
  any frozen-row motion or an unexpected row count.
- **A8 — order gates.** ui-html 0.3.1 → SDK PR → release cut 0.16.0 → pointer
  advance (gitlink + `.gitmodules` pin + mirror + matrix in one commit) → merge on
  the full rollup. The branch's sync-pair reds go green at the pointer leg and not
  before. Kill: any inversion, or a merge with red/pending lanes.
- **A9 — the F4 settlement's own arms.** After the schema edit: a time_series plot
  template WITHOUT `series` FAILS schema validation (the tightening RED — demonstrated
  against a scratch document), and both committed time_series documents (dc_psu, dmm)
  PASS. Kill: the scratch document validating, or either committed document failing.

**Underpowered branch:** if the dmm page cannot be composed from §E.1 partials the
renderer already ships (a surface the vocabulary genuinely lacks), that falsifies
§3's widening answer — the finding comes back with evidence and the widening is priced
on it, never silently absorbed. If the census cannot key on contract surfaces the
preview host emits, that is an instrument failure — reported, not a verdict.

## 11. Review tier and Step-1 keyword scan

Tier 3 — touches `standards/` + JSON Schema; advances the submodule pointer; diff text
carries `sha256` (corpus rows, sync tests, this record). Two-lane adversary pass and
the standards-governor lane mandatory.

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~10–20 | 1 new corpus row + 1 digest motion, sync/fixture tests, this record |
| `hashlib` | ~2–4 | SDK derivation tests |
| `protection` | ~1–2 | this record's prose only; zero in code (dmm has no protective surface — the honest note) |
| `threading` / `asyncio` / `subprocess` / `migrate` / `recovery` | 0 | in-process render; derivation, not migration |

## 12. Top risks, each with its falsifier

- **R1 — the shared-census extraction destabilizes L11's arms.** Mitigated by
  byte-identical assertions and A5's re-run; falsified by any L11 assertion delta
  beyond imports.
- **R2 — the batch's merge-window risk.** dmm + the SDK widening + ui-html 0.3.1 +
  the pointer is the largest single merge of the train; mitigated by the #408 order,
  the full-rollup merge gate, and A8. Falsified by any red or pending lane at merge.
- **R3 — the function-exclusivity presentation is wrong at birth.** The uniform-tile
  derivation is honest at this fixture's shape; if review holds it is misleading even
  here, the fix is mockup+reference-local (no widening). Falsified by the §9 trigger
  or an owner call.
- **R4 — mockup drift.** Intended: the mockup is the spec; edits force re-derivation
  and the census reds (A3).
- **R5 — public-repo discipline.** `DMM-01` and every fixture name invented; no real
  bench, vendor or corpus identifier (the mockup is authored fresh — the discipline is
  paid at authoring, not audited later).
- **R6 — the E-1 seam is underspecified and a future promotion lands badly.** The
  `when_declared` seam exists and §4 records the trigger; if the promotion's shape
  needs more (a new page kind, a conditional layout), that landing prices its own
  bump under the train rules then in force. Not this slice's risk to carry.

## 13. Row-calls (numbered; the principal alone decides)

- **RC-L12-1 — author mockup and reference in one slice.** Recommended: the A3
  namesake needs the mockup, and authoring both together is what makes the reference
  "derived from the mockup" true rather than asserted. Alternative: reference-only,
  mockup later — rejected (it re-creates L11's hook-pass debt with extra steps).
- **RC-L12-2 — settle F4 by REQUIRING `series`** (§5). Recommended ACCEPT.
  Alternative: pin absent-semantics — rejected as the ambiguity F4 named, resolved by
  convention instead of constraint.
- **RC-L12-3 — the shared-census helper** (`classref_census.py`, the suite's helper
  idiom; one disclosed mechanical motion to the L11 test file inside the batch
  window). Recommended ACCEPT. Alternatives: import-from-test-module (fragile,
  unidiomatic) or a duplicated census (an instrument fork — F1's lesson violated).
- **RC-L12-4 — confirm the batched promotion leg rides L12** as L11's RC-L11-2
  ruled (SDK 0.16.0 + ui-html 0.3.1 + pointer, §7). A confirmation of the standing
  ruling, recorded here because L12 is the slot that performs it.

## 14. Precedent map (principle 9)

| L12 surface | in-tree precedent | why it fits |
|---|---|---|
| class file added to an in-window unreleased bump | the batch rule itself (GOVERNANCE), exercised by L11's addendum motions | same train, same bump, no new version directory |
| mockup authored to the dc_psu convention | `class-dc_psu.html` (and the analyser mockup before it) | the third mockup in the index, hooks and placement from birth |
| class page = committed expansion + drift guard | the analyser capture page, the dc_psu output page | the styleguide's own rule, third instance |
| expansion fixture = the OTDP class example | RC-L11-4's ruling | same two-corpus-file contract, no derived fixture needed |
| per-class composer in `classref.py` | `render_capture_page`, `render_output_page` | the module's standing shape, third instance |
| non-test helper imported by test modules | `colour_instrument.py`, `thresholds.py` | the suite's idiom for shared instruments |
| const-required single-value field | `contract_version`, `key`, `label`, `group_size` | the schema's own explicitness style (the F4 ruling) |

## 15. Appendix — evidence, disclosures, and the pre-flight record

**Pre-flight (the #181 R2 discipline):** `git fetch origin`; gateway open PRs: #498
only (interface 0.1.1 — no path overlap with this family, the mockups, or the sweep);
SDK open PRs: none. No remote branch touches `standards/plugin-ui-class-reference/`,
the mockups, or the class sweep. The worktree was cut from
`origin/feat/l11-dcpsu-classref` `96c8dd9d` as dispatched.

**The slotted-set check (the dispatch's warning verified):** §7A's sweep order was
checked against both the program record AND the workbench §8 table — dmm is genuinely
the second sweep class. The slotted issues L6–L10 were spot-checked against their
trackers: #460 matches its row ("upgrade artifact migration" — the title says
"upgrade does not migrate plugin-ui contract artifacts"); #461's row ("venv symlink
damage") mischaracterizes its tracker title ("upgrade writes conflict markers into the
project virtual environment" — conflict-marker corruption of the referenced
interpreter, not symlink damage per se; #463's own row 5 says "through the virtual
environment symlinks", so the shorthand is defensible but lossy). #463's rows 3/7/8
match their slots. None of L6–L10 gates dmm; the sweep order stands regardless of the
row-wording corrections.

**Gortex:** AVAILABLE to this subagent for the worktree — every source read went
through `mcp__gortex__read` with the worktree-prefixed path
(`BenchWeave/.wt/l12-d4m9/...`), and content identity was verified against the branch
(the 0.3.0 family exists only on `feat/l11-dcpsu-classref`, and the daemon served
it — the view is the worktree's, not main's). The PreToolUse hook was active (it
blocked two shell greps on indexed source; both re-served through gortex). No daemon
restart, no tracking change. One caveat recorded: at session start the server
reported checkout discovery "view_building, retryable" — it cleared within the first
reads; no fallback was needed.

**Paths read as evidence:** `standards/GOVERNANCE.md`; `standards/standards-manifest.json`
(both the main checkout's — confirming main still serves 0.2.0, range `<0.3.0` — and
the branch's); `standards/corpus-manifest.json` (the four 0.3.0 rows and their
`source` citations); `standards/cross-constraints.json` (both family rows);
`standards/plugin-ui-class-reference/0.3.0/` (`class-reference.schema.json` in full,
`class-logic_analyser.json`, `class-dc_psu.json`, `README.md`);
`standards/otdp/0.2.3/device-profile-catalog.json` (the dmm and dc_psu profile entries;
both dmm action schemas); `standards/otdp/0.2.3/examples/class-dmm.json` and
`class-dc_psu.json`; `docs/internal/ui-styleguide-workbench-design.md` (§8's class
order); `docs/internal/ui-styleguide.md` (the class-reference family section, the
mockup index line); `docs/internal/ui-styleguide-mockups/class-dc_psu.html` (the
per-theme structural skeleton — readings row, alert aside, lower grid with control
card + plot + table); `tests/ui_html/test_classref_dc_psu.py` (in full — the A3
instrument extended here); `packages/ui-html/src/benchweave_ui_html/classref.py`
(compressed — the per-class composer shape); `tests/ui_html/` inventory (the
helper-module idiom; no `__init__.py`); `.claude/deep-review/
2026-10-18-classref-l11-dc-psu-design.md` (in full, addendum and refute fold
included); `.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` (§0, §2.5,
§5.1, §7A, §8 — extracted in full); tracker: gateway issues #463 (body), #460, #461
(titles); `gh pr list` both repos.

**Honest disclosures to the dispatch:** (a) the dispatch's grounding was correct on
every point checked — no dmm mockup exists, the OTDP example is at 0.2.3, L11 cut
0.3.0 unreleased, the A3 instrument records tags and ancestors, and F4's home is this
design; (b) the two "misstated rows" in the slotted set are L6/L7-adjacent wordings,
not sweep-order facts — §7A's order needed no correction (the appendix records the
check); (c) one design-time execution beyond reading was performed — the A4 RED pair
(`select_references` None for dmm / resolving for dc_psu on the L11 branch head) —
because a pre-committed acceptance rule that can be banked before the build should
be; it wrote nothing.
