# L17 — the sweep's first class with a real consumer: `otdp.daq` class reference, the oscilloscope boundary settled, zero schema motion (mockup authored)

**Date:** 19 October 2026
**Slot:** L17 of the class-reference train (parent gateway issue #463; program record
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` §7A row L17, §8's
RC-1 sweep row; the sweep order L11 dc_psu → L12 dmm → L13 oscilloscope → L14
function_generator → L15 electronic_load → L16 smu → **L17 daq** → L18
embedded_controller … L21 vna, verified against §7A AND the workbench §8 table
`docs/internal/ui-styleguide-workbench-design.md` §8 — "data acquisition" follows
"source-measure unit").
**Branch:** `feat/l17-daq-classref`, cut from `origin/feat/l11-dcpsu-classref`
`c64f3d05` (the L11 rebase resolution; the L11 refute fold's motions verified present
on this base). Design-only slot: no build, no push, no PR, no SDK or pointer work.
**Worktree:** `.wt/l17-m9x4/`. Evidence baseline: the branch head `c64f3d05`;
plugin-ui-class-reference **0.3.0 active on the branch, unreleased** (range
`>=0.1.0,<0.4.0`); the batch-state assumption this design bakes in: **L11 landed
(here), L12's `class-dmm.json` + the series-required settlement, and L13's `waveform`
widening all land in the same unreleased 0.3.0 before this class's build** — the
`waveform` plot kind is load-bearing for daq (P1e below proves it: the daq reference
is schema-INVALID against the committed c64f3d05 schema and valid exactly against
the batch state). OTDP 0.2.3 active (0.2.2 retained and equal where it matters —
§4). Parkview's fork read pull-only via `gh api`; nothing written there.
**Binding design points:** the program record D1–D14 (esp. D2 structure-not-data,
D13 effective capability, D14 coverage); the L11 record in full (addendum + refute
fold F1–F4); the L12 record in full (its §1 four grounds, §5 F4 settlement, §6 shared
census, the batched promotion leg it performs); the L13 record in full (its §4
per-idiom verdicts, §5 the waveform widening, §6 the census's third instance and the
no-hook-on-idiom-surface arm); GOVERNANCE's bump-minimization train rule and G-5.

## 0. Summary and design thesis

L17 authors the eighth class reference — `class-daq.json`, binding
`otdp.daq/1.0.0` — and authors the mockup it is validated against (there is no
`class-daq.html`; the mockup directory holds the analyser, dc_psu, and the dmm/scope
files the L12/L13 lanes are authoring). It is the sweep's first class with a **real,
shipped consumer**: `parkview/benchweave` (public fork, pull-only) carries
`community.benchweave-adc.adc-6ch-12bit` — a CH32V006E8R six-channel 12-bit ADC
board adapter declaring `profiles: ["otdp.daq/1.0.0"]` with all five daq actions
(optional `trigger` declared) and **no `ui/` manifest**, so the L4 no-manifest
fallback makes this reference the plugin's actual served presentation the moment it
lands. The thesis in one line:

> The daq is the oscilloscope's action-identical sibling with a different substance —
> engineering units per channel instead of probe-scaled display, acquisition evidence
> instead of a graticule — and at this slice's evidence that difference costs the
> family **zero schema bytes**: daq reuses L13's `waveform` arm whole, adds exactly
> one corpus file, and the real six-channel consumer resolves cleanly inside the
> §E.2 machinery that already exists (16-id trace ceiling, 8-colour × 2-dash slot
> assignment, the unit-driven y-axis rule with its honest >2-unit refusal).

Three grounding facts fix the scope, each verified in the worktree or over `gh api`
this pass:

1. **The action contracts are identical in four of five verbs and materially
   different in the fifth.** Namespace-normalized structural comparison of the
   catalog's action schemas (executed, not asserted): `arm`, `trigger`, `fetch`,
   `abort` are **byte-structurally identical** between `otdp.oscilloscope` and
   `otdp.daq`. `configure` differs in exactly two dimensions — per-channel, the
   scope carries coupling/range_v/offset_v/probe_ratio (probe-referred display
   semantics) while the daq carries quantity/unit/range **per channel**
   (heterogeneous engineering-unit semantics); class-level, the scope carries
   `pretrigger_fraction` (required) + `averaging_count` (optional, [1,64]) while the
   daq carries `sampling: simultaneous|multiplexed` (required). The profiles also
   differ: `channel_roles` is `["analogue_input"]` for the scope and
   `["analogue_input", "digital_input"]` for the daq — the daq admits a digital face
   the scope does not.
2. **The real consumer's shape fits the batch-state vocabulary with room to
   spare.** Six `analogue_input` channels (ids `a0..a4` and `a7` — the dispatch's
   "a0..a5" is corrected in §4), each declaring `quantities: ["voltage"]`; the
   adapter's fetch drains buffered samples into an **otdp-measurement waveform
   dataset** in raw counts (`unit: "count"`, calibration `not_applied` — its own
   adapter doc says so). Six traces sit at slots 0–5 of a 16-slot assignment
   (§E.2.1); one distinct unit renders one y-axis (§E.2.3); the optional `trigger`
   is declared, so all three run buttons bind live. The plugin declares
   `otdp_version: 0.2.2`, and the retained 0.2.2 catalog's daq profile is identical
   to 0.2.3's (verified: same channel_roles, same required/optional actions).
3. **Every layer the daq page needs is already widened by the batch.** The
   `waveform` plot kind (L13), the `numeric_variables` series rule required (L12),
   the `when_declared` seam (0.3.0 since L11's copy), the §E.1 `engineering-plot` /
   `button` / `alert-bubble` census keys (L11/L13), the capture-page geometry (the
   analyser's, re-proven by L13), and the four-id forbid set with `abort` in the D7
   slug set — the daq reference is expressible **without widening anything**, the
   good result §3 states and defends, proven executable in §6's P1.

## 1. The governance answer first: one class file, zero schema bytes, two priced landings

**Can `class-daq.json` join the unreleased 0.3.0 window? Yes, if the batch has not
merged — and that is the recommended landing.** The L12 record's four grounds and
the L13 record's re-verification hold unchanged for this slice (train rule: same
standard, same merge window, no new version directory; G-5: governs new directories,
not in-window edits, and the 0.3.0 SDK leg is outstanding on this base either way;
copy-never-move: 0.2.0/0.1.0 bytes untouched; the L11/L12/L13 rulings walked the same
window three times). What is NEW in this slot: **daq requests no schema motion at
all** — unlike L12 (the series-required settlement) and L13 (the waveform member +
conditional), L17's entire corpus motion is one new class file. The batch's highest
change class remains MINOR (the L11 plot widening); daq adds no class.

**The fallback, priced (the post-merge world).** If the batch merges before L17's
corpus motion lands, a pure class-file addition with zero schema delta is additive
errata by L11's own §1 arithmetic — **PATCH 0.3.1** — exactly the shape L13 priced
for its class-file-only branch of the fallback, at the errata class rather than the
MINOR class because this slot widens nothing. G-5 gates even a PATCH on 0.3.0's SDK
leg (the L12 batched promotion performs it), so the fallback remains legal-but-
serialised. Standing recommendation mirrors L13's: land the corpus on the stacked
branch before the batch's promotion leg.

**The OTDP `daq` example, and how it relates.**
`standards/otdp/0.2.3/examples/class-daq.json` is the canonical expansion fixture
(RC-L11-4's ruling, fourth application): 2 `analogue_input` channels (`ch1`/`ch2`),
each `quantities: [voltage]`; all five actions declared with empty
`input_constraints`; contracts pinning the catalog and the measurement schema. Same
relationship every sweep class holds: OTDP answers what a daq must admit; this
family answers how the class presents. Unlike dmm and like dc_psu, **a second,
derived fixture is needed** — the mockup reflects the class's real consumer shape
(six channels), so the A3 census resolves over **F-daq-2**, a six-channel fixture
derived in-test from the committed example (channel list widened to six invented
ids, quantities unchanged) — L11's two-fixture pattern (F-psu-1/F-psu-2), not L12's
one-fixture shape. The real Parkview descriptor is a THIRD fixture the build's
conformance arm consumes (§6 P2, A10) — fetched at test time over `gh api` is wrong
(network in CI); the build vendors a byte-copy as a test fixture with its source
named, or regenerates it from the pinned commit — a build-detail row-call (RC-L17-4).

## 2. The mockup (authored — the spec, per the dispatch's finding that none exists)

`docs/internal/ui-styleguide-mockups/class-daq.html` is authored to the
dc_psu/dmm/scope convention — one composition, two `data-theme` sections (light/dark)
over the shipped token set (the drift-guarded `bw-shipped:` blocks copied from the
committed dc_psu mockup verbatim), self-contained, ~14 KB, invented identifiers only
(`DAQ-01`, `ch1..ch6`; public-repo discipline paid at authoring — the six-channel
COUNT reflects the real consumer's shape; its identity, pin map and channel meanings
do not appear). The L11 lessons and the L13 extension are built in from birth:

- **§E.1 component hooks from birth**: `bw-plot` on the capture `section`,
  `bw-button` on each run `button` (all three), `bw-alert-bubble` on the alert
  `aside`. Hooks on their §E.1 ROOT elements.
- **The F1 placement contract from birth**: container-scoped hooks inside their
  containers; and the L13 extension — **the idiom surfaces carry NO `bw-` hook**:
  the trigger marker line + its `TRIG · edge · −1.2 ms` chip, the cursor pair +
  `Δt 4.0 ms · Δv 213 count` chip, and the unit/calibration context line are painted
  as styleguide idioms over host knowledge. A non-contract idiom must never present
  as a contract component (L13's generalisation, second application).
- **The §E.2.5 acquisition disclosure painted with its contract hook** (class
  `bw-plot__acquisition`, `data-bw-acquisition`): `Acquired 19,800 samples ·
  plotted 6,600` — the capture-context strip landing by use, now for a class whose
  streaming rate makes decimation certain (six channels at ksamples/s against a
  canvas that plots thousands).

**What a data-acquisition board's class page shows, and why** (each element traced
to the class's nature — an acquisition backplane whose observable is the streamed
sample set, not a probe-scaled picture of one edge):

| element | disposition |
|---|---|
| title row + `Controls` button | page chrome/navigation — host territory, as every class |
| recessed capture panel `bw-plot`: graticule, **six** traces (ch1..ch6), a legend strip (six chips, slot colours via `--bw-series-1..6`), the acquisition line, y-axis note `count` | **derives**: one `engineering-plot` of kind `waveform` over the capture slot; one trace per (channel, declared quantity) variable of the fetch dataset (6 × 1); the y-axis names the dataset's unit — which for a raw-counts digitiser is `count`, honestly |
| slot colours/dashes | §E.2's pure function of the declared id set (bytewise sort; six ids → slots 0–5, series-1..6, all dash-1; the waveform identity residual — symbols do not render — is the disclosed owner fork; six distinct colours carry identity, backed by the ≥8 ΔE00 same-dash separation proofs §E.2 cites) |
| trigger marker + readout chip | **cannot_derive** `trigger-marker` — host-knowledge seam (§E.2.6 precedent; the dataset carries trigger structurally, the wire does not) |
| cursor pair + Δ readout chip | **cannot_derive** `cursor-readout` — operator runtime state |
| acquisition line | **derives by use** — §E.2.5's normative disclosure, rendered inside the plot family |
| `UNIT COUNT · CALIBRATION NOT APPLIED` context line | **cannot_derive** `calibration-context` — the dataset's unit and calibration state are runtime data; the class presents the unit the dataset carries, never a nicer one (the real consumer streams raw counts with calibration `not_applied` — its own docs flag gain/offset as an upstream gap) |
| raised run panel: `Arm` (primary `bw-button`), `Trigger` (`bw-button`), `Abort` (`bw-button`) | **derives**: the run controls at their ladder levels — arm L2 staging, abort L1, trigger L1 (declared on both fixtures; undeclared descriptors render it ghost, §3) |
| alert aside: "Buffer overflow — partial dataset retained" (warning) | **cannot_derive** `partial-capture-alert` — the dataset's runtime `status: partial` + `status_reason`; structure renders the variant, data decides it |

The layout is the analyser/scope capture geometry (plot recessed and dominant, run
controls raised below) — the second capture class after L13 re-proves it. **No
table on the capture page** (L13's scope ruling, carried: a table of streamed
samples is not a surface this class presents), **no reading tiles** (reading tiles
derive from scalar variables; waveform variables carry no scalar-extraction rule —
the streaming-latest monitor strip is a named deferral, §9). The styleguide's mockup
index line gains `class-daq.html`; `docs/internal/ui-styleguide.md` gains the daq
class-page row.

## 3. The reference, derived from the mockup

`standards/plugin-ui-class-reference/0.3.0/class-daq.json` (authored this pass at
the staging path `docs/plugin-ui-class-reference-v2/class-daq.json`, the founding
convention; the build moves it to the version directory and adds its corpus row) —
structure-not-data (D2), the scope's sibling posture: authored structural strings
only; every count an expression; every quantity and unit arriving via the descriptor
and the fetch dataset at expansion.

**Slots** (URNs and inputs verified against the 0.2.3 catalog this pass):

| key | kind | resolves |
|---|---|---|
| `channels` | `channels`, `where_role: "analogue_input"` | the declared analogue channels, declaration order |
| `capture` | `dataset`, action `otdp.daq.fetch/1.0.0`, `schema_source: output_measurement`, `host_supplied: [acquisition_id]` | the fetch dataset — waveform-shaped on both fixtures and the real consumer; one array-valued numeric variable per (channel, declared quantity); explicit time axis (per-channel axes where timing differs — the derivation follows the dataset) |
| `configure` | `configuration`, action `otdp.daq.configure/1.0.0`, `schema_source: input_schema` | the settings schema (configuration_id, channels[] of quantity/unit/range, sample_rate_hz, sample_count ≤ 1e6, sampling, trigger{}) |
| `arm` | `procedure`, action `otdp.daq.arm/1.0.0`, `host_supplied: [configuration_id, acquisition_id]` | the acquisition start — L2 (`max_duration_ms` numeric; ids host-supplied) |
| `abort` | `procedure`, action `otdp.daq.abort/1.0.0`, `host_supplied: [acquisition_id]` | the acquisition stop — L1 |
| `trigger` | `procedure`, action `otdp.daq.trigger/1.0.0`, `when_declared: true`, `host_supplied: [acquisition_id]` | the software trigger — L1, optional (binds only when declared; Parkview and both fixtures declare it) |
| `vendor_actions` | `vendor_actions` | D14 hook for unclaimed URNs |

`host_supplied` is exactly the acquisition-lifecycle set — structural field NAMES,
D2-clean. `fetch`'s `max_bytes`/`allow_partial` are caller inputs on a dataset
action, page-covered (dc_psu's `measure` / L13's `fetch` precedent: no controls row).

**Pages** (three, the family's standing count): **Capture** (`kind: dataset`,
`binding_slots: [capture, arm, abort, trigger]`, `plot: {kind: waveform, over_slot:
capture, series: numeric_variables}`) — traces section (recessed, span 12, plot_index
0), run section (raised, span 12) carrying the three button children (the trigger
child authored, RC-L13-3's ruling — undeclared renders ghost); **Configuration**
(`kind: configuration`, `binding_slots: [configure]`, preset-mediated,
`preset_asset_ids: []` at birth); **Device features** (`kind: configuration`,
`binding_slots: [vendor_actions]`, `vendor_features: true`).

**expect.components**: `engineering-plot` `1` (per_page capture); `button`
`{n_run_actions}` (per_page capture); `data-table` `1` (the configuration settings
table, pooled — the capture page carries no table); `panel` `{n_pages}`;
`mode-banner` `1` per page. **expect.controls**: `configure → preset`, `arm →
staging`, `abort → button`, `trigger → button` — the scope's four-row set verbatim
(the lifecycle quartet is action-identical, §3.1). **Counter closure**: nothing new
— `n_analogue_channels` (L13's role-generic name) resolves the channels slot,
`n_run_actions` and `n_pages` are shared; trace counts are derivations at expansion
(one per (channel, declared quantity)), never authored literals.

**forbid** — the four ids, L13's carry whole, with the same recorded reasoning:
`confirm-wrapped-run-action` (family-generic, and daq owns the `abort` slug the D7
set names); `color-role-hint-on-lane` and `untraceable-lane-label` (family-generic);
`intermediated-energy-removing-action` (carried, not dropped — dmm's drop reasoning
does not apply to a class with a live `abort`; the intent declaration arms the
safety-behaviours slice). The refute lane is invited to kill the carry exactly as
L13 invited it (R4 there); the drop is one line with the recorded reason if it
lands.

**cannot_derive** (six rows, each traced to a mockup element): `acquisition-settings`
(per-channel quantity/unit/range, sampling mode, trigger — inexpressible at L2,
preset-mediated, A02), `trigger-marker` (host seam), `cursor-readout` (operator
state), `partial-capture-alert` (runtime dataset status), `calibration-context`
(the daq's own row — the dataset's unit/calibration are runtime data; present the
unit the dataset carries), `channel-names` (descriptor owns identity). `presets` is
folded into `acquisition-settings`' author_action (L13's authoring choice, second
application).

### 3.1 The oscilloscope-versus-daq distinction, settled — and why the family keeps two classes

The dispatch's question: the two class contracts are action-identical (verified:
true for the lifecycle quartet, false for configure — §0.1), so what actually
separates them in the class reference, and should the family carry one class where
it now carries two? The answer has three layers, each structural:

1. **The family CANNOT merge them: `profile_id` binds exactly one OTDP profile.**
   The schema's `$defs.profile_id` pattern names one profile; `find_reference` /
   `select_references` match descriptor profiles to reference `profile_id`s. A
   merged document is not an expressible object in this family — a daq descriptor
   would simply resolve nothing. Merging would mean deleting one class reference
   and leaving one profile unrepresented (a D14 coverage hole by the program
   record's own §2.5 ladder), not saving a file.
2. **The boundary the merge question really names is OTDP's, and OTDP drew it
   deliberately.** The catalog separates the profiles with different
   `channel_roles`, different configure semantics (probe-scaled display vs
   per-channel engineering units), and different dataset freedom — device-classes
   §6 mandates the scope "returns waveform datasets" (display instrument,
   probe-referred, pretrigger view) while §11 mandates the daq "returns waveform or
   table datasets", admits digital channels with the logic datatype, and imposes
   the multiplexed-timing evidence obligation ("a multiplexed scan is not
   represented as a simultaneous sample merely because it has one row"). §17 cites
   the IVI class architecture this separation follows. An OTDP-level merge is a
   different standard's reviewed revision — not this train's motion, and the
   distinction there is real, not nomenclature.
3. **What the family owns is the honest consequence: the two references are
   structural siblings BY DESIGN, and the daq's real differences are armed
   deferrals, not presentational divergence.** At this slice's evidence (both
   fixtures and the real consumer are single-unit analogue waveform captures) the
   daq page IS the scope page with different URNs, a different preset text, and one
   extra cannot_derive row (`calibration-context`). The substance differences —
   heterogeneous units past two (the §E.2.3 refusal boundary), the digital face,
   the table-dataset face, streaming-latest presentation — are each a named
   deferral with an observable reopen trigger (§9). If none ever fires, the
   references remain twins, and that is the family working as intended:
   presentation follows class substance, and the substances coincide at this
   evidence. **The verdict: keep two classes; do not fork machinery between them.**
   The honest "should merge" is answered where it is actionable — at OTDP — and
   recorded here as a non-motion with the reason.

## 4. The real consumer: Parkview's `community.benchweave-adc.adc-6ch-12bit`

Read pull-only over `gh api` (descriptor, `docs/adapter.md`, plugin README, repo
tree). The conformance statement this section makes is **executable** — §6 P2 runs
the structural acceptance rule over the descriptor bytes and reports ACCEPTS with
every finding surfaced:

- **Profile match**: `profiles: ["otdp.daq/1.0.0"]` selects `class-daq.json`
  (today: `None` — the banked RED, §6 P3). The plugin pins `otdp_version: 0.2.2`
  with digest-pinned 0.2.2 contracts; the retained 0.2.2 catalog's daq profile is
  identical to 0.2.3's (verified this pass: same roles, same required/optional
  actions) — the reference binds the profile, not the catalog version.
- **Channels**: six `analogue_input`, each `quantities: ["voltage"]` → the channels
  slot resolves 6; the derivation yields 6 array-valued variables → 6 traces, slots
  0–5, within the 16-id ceiling. **Dispatch correction, recorded: the sixth channel
  id is `a7`, not `a5`** — the ids run `a0..a4` plus `a7` (the board's pin map:
  index 5 is PD4, ADC channel A7). No conformance consequence (ids are
  descriptor-scoped and pattern-valid); the dispatch's "a0..a5" was a shape
  approximation, corrected here because the record reports bytes.
- **Actions**: all five declared, `trigger` included → every slot binds; the three
  run buttons render live. `input_constraints: {}` on every action — a commissioning
  evidence matter (device-classes §2: structural vectors are not commissioning
  evidence), not a presentation one; noted, not smoothed.
- **Dataset**: the adapter drains buffered samples into an otdp-measurement
  **waveform** dataset bounded by `max_bytes`/`allow_partial`, in **raw counts**
  (`unit: "count"`, calibration `not_applied` — its own adapter doc). One distinct
  unit → one y-axis named `count`. The class presents the unit the dataset carries:
  the page will say `count`, not `V`, until their proposed measurement-profiles
  layer (their `feature-request-measurement-profiles.md`) exists upstream. That is
  the honest face, and `calibration-context` is the cannot_derive row that names it.
- **The no-manifest path is the load-bearing one**: the plugin tree ships no `ui/`
  directory — the L4 no-manifest fallback derives its presentation from
  (descriptor × `class-daq.json`). This reference is not illustrative for this
  consumer; it IS the consumer's UI when the batch lands.

**Does the reference accept the plugin? YES** — with the two disclosed notes above
(empty input_constraints; raw-counts unit honesty) and one boundary demonstrated by
falsifier: a daq descriptor whose channels carried three or more distinct units
would hit §E.2.3's honest refusal (no silent conflation) — Parkview's does not.

## 5. The widening answer: NOTHING — stated with the palette evidence

The dispatch asked honestly whether six channels of streamed samples stress the plot
and layout vocabulary more than two traces did. They do not, and the reason is
measured, not assumed:

- **Trace ceiling**: §E.2's assignment ceiling is 16 declared ids (plugin-ui
  `$defs.plot.y.maxItems: 16`); six traces occupy slots 0–5 with six distinct
  colours and no dash reuse (the 8-colour × 2-dash product carries 16 distinct
  pairs; the ≥8 ΔE00 same-dash separation proofs are the load-bearing arm for
  waveform identity, since symbols do not render on waveform plots — the disclosed
  owner fork).
- **Axis rule**: §E.2.3 assigns y-axes by the declared trace set's units — one unit
  (both fixtures, the real consumer) → one axis; two → two axes; **three or more →
  the plot draws no traces and renders a visible refusal naming the condition**.
  The heterogeneous daq's honest boundary is already contracted. What is NOT
  expressible today: per-unit plot **splitting** (a `page_template` carries exactly
  one `plot` object), which is the presentation a 3-unit daq would deserve — a
  named deferral (§9), priced on the first descriptor that needs it, not speculatively.
- **Layout**: no stress — six traces add legend rows inside the plot family, not
  layout nodes; the capture page's node count is the scope's own.
- **Streaming volume**: the acquisition disclosure (§E.2.5) is the contracted
  answer to decimation, and the mockup exercises it; sample counts and rates are
  runtime data and appear nowhere in the reference (A6).

**No family widening is requested.** If the build falsifies this (a daq surface the
batch-state vocabulary cannot express), that is the disclosed underpowered branch
and it comes back as evidence — the schema-validation proof (§6 P1) is the
design-time half of that claim.

## 6. Proof — executed at design time, pre-committed for the build

Deterministic, all executed this pass on the worktree with the primary checkout's
venv (read-only; nothing written outside the worktree and `/tmp/l17proof`):

- **P1 — the reference is valid against the batch state and nothing else.**
  Constructed the batch-state schema (the committed 0.3.0 schema + L12's §5
  series-required edit + L13's §5 waveform member and mirror conditional, exactly
  as those records specify them) in `/tmp/l17proof`; validated with the layout
  cross-`$ref` resolved through a registry. Results: `class-daq.json` **PASS (0
  errors)**; the committed `class-dc_psu.json` **PASS** (the constructed edits
  break no committed document); a daq-shaped document **without** `series` FAILS
  (the L12 tightening bites); a daq-shaped document **with** group machinery FAILS
  (the L13 conditional bites); and — the falsifier for this design's own claim —
  `class-daq.json` against the **committed** c64f3d05 schema FAILS on the `waveform`
  enum: **L13's widening is load-bearing for daq**, which is precisely why this
  design assumes L13 lands first.
- **P2 — the conformance statement is executable.** The structural acceptance rule
  (profile match; required-slot actions present; `when_declared` binding; channel
  role resolution; one trace per (channel, declared quantity) against the 16-id
  ceiling; the §E.2.3 unit rule) run over the real Parkview descriptor bytes:
  **ACCEPTS** — 6 channels, 6 traces, the optional trigger bound, one y-axis,
  `units=["count"]`, findings none. Kill arms, all fired: profiles flipped to
  `otdp.oscilloscope/1.0.0` → **None** (no reference selected); the optional
  `trigger` removed → **still ACCEPTS** with the trigger slot unbound (acceptance
  is trigger-independent — the negative-direction proof); a three-distinct-unit
  mutant → the honest **REFUSAL** arm reports (no silent conflation).
- **P3 — the RED pair, banked.** Gateway-side `select_references(corpus,
  descriptor)` on the branch head `c64f3d05` (the primary venv, corpus = the
  worktree's `standards/`): the **Parkview descriptor → `None`** and the **OTDP
  daq example → `None`**, with the dc_psu control resolving
  `['otdp.dc_psu/1.0.0']` — executed and recorded (L12/L13's banked-RED precedent;
  `None` is also the honest fail-open signal: today this real plugin gets no
  reference-derived presentation at all). The build greens the daq half only.
- **P4 — the mockup census, design-time half of A3.** A stdlib-parser census over
  the authored `class-daq.html`: per theme, `bw-plot` 1 (on `section`), `bw-button`
  3 (on `button`), `bw-alert-bubble` 1 (on `aside`), zero `bw-reading`/`bw-data-table`
  — EQUAL to the resolved expectation over F-daq-2 (six channels × one quantity →
  one plot with six traces; all five actions declared → three run buttons; one
  alert surface); placements on root tags; **the idiom surfaces (trigger chip,
  cursor chip, context line) carry no root hook**; theme-invariant across the two
  sections.

**Pre-committed acceptance rules (they bind the build agent; denominators named,
both kill directions stated, the underpowered branch named):**

- **A1 — expansion is valid and example-shaped.** `derive-ui` on F-daq-1 (the
  committed OTDP example) produces a manifest set passing `validate_presentation`,
  with the capture page carrying a dataset binding, a `waveform` plot over the
  capture slot with `series: numeric_variables`, `x` the time axis, `y` the 2/2
  derived trace variables; F-daq-2 (six-channel derived fixture) yields 6/6. Counts
  from the derivation, never literals. Kill: any count off, any validation failure,
  or a trace variable not traceable to a (channel, quantity) pair.
- **A2 — the gate passes with the birth deviations REPORTED.** `verify-ui` on
  F-daq-1 exits 0 with a REPORTED deviation for `configure` (preset-mediated), none
  silent; the census on the capture page reads `engineering-plot` 1/1, `button`
  3/3, `panel` `{n_pages}`, `mode-banner` per page; `fetch` covered via the plot
  figure (the widened L4 arm); the configuration page reads the settings
  `data-table`. Kill: any census delta, any undeclared divergence, or
  `classref_gate_uncovered` naming fetch.
- **A3 — the mockup-consistency arm (the namesake), fourth census instance.**
  `tests/ui_html/test_classref_daq.py` over the shared `classref_census.py`
  (L12 §6's lift; if the L13 build has not landed it, the lift is this slice's
  disclosed mechanical motion on the same terms): hooks in both themes; counts
  EQUAL the resolved expectation over F-daq-2; **placement including the
  count-conserving-move kill demonstrated RED** (a `bw-button` moved onto the
  figure; a `bw-plot` onto the run panel — counts conserve, placements red) AND the
  no-hook-on-idiom-surface kill demonstrated RED (a `bw-` class planted on the
  trigger chip or the context line reds); theme-invariance. The falsifier: any
  disagreement between the mockup's counts or placements and the resolved
  expectation; a mockup edit that does NOT redden the test is the instrument
  failing — reported, never a pass.
- **A4 — RED control (banked at design time, P3 above).** `select_references` on
  the branch head: Parkview descriptor and daq example → `None`, dc_psu resolving.
  The slice greens the daq half only. Kill: either half green before its landing
  commit exists.
- **A5 — the predecessors are untouched.** `class-logic_analyser.json`,
  `class-dc_psu.json`, and every class file that exists on the branch when the
  build runs (`class-dmm.json`, `class-oscilloscope.json`, and any L14–L16 files)
  byte-identical through the slice; the only prior-test motion, if any, is the
  shared-census import; the prior test modules re-run green. Kill: any byte beyond
  the disclosed motions, or any prior acceptance rule flipping.
- **A6 — D2 census on the daq reference.** No numeric literals outside the
  structural set (spans ≤12, plot indices); no data strings (no values, units,
  channel names, quantity names, no sample counts or rates). Machine-checked. Kill:
  any authored data string.
- **A7 — corpus and version gates.** `benchweave.standards check` clean; `repin`
  writes exactly ONE new row (`class-daq.json`, source citing the staging path,
  removed in-PR) and moves ZERO existing-row digests (**this slice edits no schema
  byte — a moved digest is a finding**); `matrix --check` clean; the served set and
  range unchanged. Kill: any frozen-row motion, any schema diff, or an unexpected
  row count.
- **A8 — order gates.** Whatever window the landing catches: in-window (stacked
  branch, before the batch's promotion leg) or post-merge PATCH 0.3.1 under the
  then-current train rules — either way the #408 order holds for any SDK leg and
  the merge is on the full rollup, zero fail, zero pending. Kill: any inversion or
  red/pending merge.
- **A9 — the batch-state dependency is explicit.** The build does not start before
  L13's `waveform` widening and L12's `series`-required settlement are on its base
  (P1e is the standing proof of why: the daq reference is schema-invalid without
  them). Kill: a daq corpus landing on a base whose schema admits no `waveform`.
- **A10 — the real-consumer conformance arm.** P2's acceptance rule as a test over
  a vendored byte-copy of the Parkview descriptor (fixture source named in-file;
  no network in CI — RC-L17-4): profile match, 6/6 channels/traces, optional
  trigger bound, one y-axis, `units={"count"}`; the three kill arms (profile flip
  → None; trigger-less mutant still accepts; three-unit mutant → the refusal arm)
  as RED-proof mutations. Kill: any arm that does not fire.

**Underpowered branch:** if the capture page cannot be composed from §E.1 partials
the renderer ships (falsifying §5's widening answer), the finding comes back with
evidence, priced then, never silently absorbed. If the census cannot key on
contract surfaces the preview host emits, that is an instrument failure — reported,
not a verdict.

## 7. Choreography

1. **Gateway branch content** (the build slice): move the staged
   `class-daq.json` into `standards/plugin-ui-class-reference/0.3.0/`, repin (one
   new row), the mockup (committed here), `tests/ui_html/test_classref_daq.py` +
   the Parkview fixture, the styleguide rows (mockup index line + daq class-page
   row), the family README files-table row, this record. The daq composer +
   PATTERNS entry in `packages/ui-html` ride whatever ui-html release the batch
   cuts (F2's bounded-divergence ruling, third extension).
2. **The SDK leg**: daq needs NO new expander arm beyond what L11 designed and L12/
   L13 extend — the waveform dataset derivation, the waveform plot emission, the
   `engineering-plot`/`button` census keys, `when_declared`, and `n_run_actions`
   all exist in the batched widening by the time this lands. The daq's SDK-side
   cost is fixtures only (F-daq-1, F-daq-2, the refusal fixtures: zero analogue
   channels → the channels-slot refusal; a `time_series` template over the waveform
   dataset → the shape-mismatch refusal; absent required action →
   `classref_required_action_absent`) plus the vendored ingest picking up the new
   class file.
3. The standards tripwire fires by design; this record is the named sanction.
   Standards-governor lane mandatory; two-lane adversary pass on the built slice.

## 8. Corpus-motion census (exact bytes)

Gateway repo, `standards/`:
- **Added** `standards/plugin-ui-class-reference/0.3.0/class-daq.json` — ONE new
  corpus row, `source` citing the authoring staging path
  `docs/plugin-ui-class-reference-v2/class-daq.json` (removed in-PR — the founding
  convention; the file is authored there on this branch today).
- **Edited: nothing.** Zero schema bytes, zero manifest motion (0.3.0 already
  active on the branch), zero dependency_policy motion (range already `<0.4.0`),
  zero cross-constraints motion (the 0.3.0 row's floor is unchanged — daq consumes
  vocabulary plugin-ui 0.4.0 already ships), zero digest motions of existing rows.
- **Unpinned prose**: the family `README.md` files-table row;
  `docs/internal/ui-styleguide.md` (the daq class-page row; the mockup index line
  gains `class-daq.html`).

Gateway repo, docs/tests (no corpus impact): the mockup (committed with this
design); `tests/ui_html/test_classref_daq.py`; the Parkview descriptor fixture;
possibly the shared-census lift (§6 A3's terms).

`packages/ui-html`: the daq composer + PATTERNS entry (rides the batch's ui-html
release).

## 9. Deferrals, each with a home and an observable reopen trigger

| defers | home | reopen trigger |
|---|---|---|
| heterogeneous-unit presentation past two units (per-unit plot splitting; needs multi-plot pages — a `page_template` carries one `plot`) | the family schema, on evidence; the interim behaviour is §E.2.3's honest refusal | the first admitted daq descriptor whose fetch dataset carries ≥3 distinct units |
| the digital face (mixed-signal daq: a second `channels` slot over `digital_input`, lane/trace mixed presentation) | the family schema + expander, on evidence | the first admitted daq descriptor declaring `digital_input` channels |
| the table-dataset face (daq §11: "waveform or table"; a `waveform` template over a table dataset refuses — the shape-mismatch arm) | the expander's dataset-by-shape derivation, a `table` presentation arm if ever needed | an owner call or a real daq whose default fetch is table-shaped and whose operator wants tabular presentation |
| streaming-latest presentation (latest-sample-per-channel monitor tiles) | the expander (a scalar-extraction rule over waveform variables) or host composition | a real streaming bench wanting the monitor strip; or an owner call |
| multiplexed-timing presentation (per-channel skew/offset visualisation) | host composition from dataset context (the offsets are dataset metadata, not wire fields) | a real multiplexed descriptor where timing is operator-relevant; or the §E.2 marker wall-payment event |
| contract-grade cursor/trigger markers (§E.2 marker sub-row) | the next plugin-ui wall-payment event (RC-L5-1's batching rule — L13's named item, unchanged) | the owner calling the bump |
| raw-counts→engineering-units presentation (the real consumer's measurement-profiles gap) | upstream OTDP/the plugin's own proposal (their feature-request doc); this family presents the dataset's unit | the upstream contract landing; until then `calibration-context` names the honesty |

## 10. Review tier and Step-1 keyword scan

Tier 3 — touches `standards/` (one corpus file); rides a batch that advances the
submodule pointer; diff text carries `sha256` (the corpus row, this record).

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~5–10 | 1 new corpus row, this record |
| `hashlib` | 0 | no code in this slice |
| `protection` | ~1 | this record's prose only; zero in code |
| `threading` / `asyncio` / `subprocess` / `migrate` / `recovery` | 0 | design-only slot |

## 11. Top risks, each with its falsifier

- **R1 — the batch merges before L17's corpus lands.** The PATCH 0.3.1 fallback
  activates (§1) — legal, serialised, more expensive. Falsified by checking branch
  state at build start; the sequencing call is the coordinator's.
- **R2 — the sibling-twin reading is wrong.** If review holds that a class whose
  reference is byte-for-byte the scope's shape modulo URNs should not exist, the
  honest fix is the OTDP-level conversation §3.1 names, not a forked family
  mechanism. Falsified by the owner at the row-call.
- **R3 — the real consumer drifts.** Parkview's fork is pull-only and live; a
  descriptor change (channels, actions, units) moves the conformance answer.
  Mitigated by A10's fixture naming its pinned commit; falsified by the fixture
  drifting from upstream (a regenerable check, not a silent pass).
- **R4 — the four-id forbid carry is wrong for daq** (L13's R4, inherited).
  Falsified by the adversary lane; the drop is one line with the reason recorded.
- **R5 — mockup drift.** Intended: the mockup is the spec; edits force
  re-derivation and A3 reds.
- **R6 — public-repo discipline.** `DAQ-01`, `ch1..ch6` invented; the Parkview
  identity appears in the design record and the TEST FIXTURE source note only —
  both name a public repository's public plugin id, not a bench, client or corpus;
  the mockup copies none of its identity.
- **R7 — the parallel-lane stack.** L14/L15/L16 design concurrently on the same
  base; any of their corpus motions landing first changes the "files that exist on
  the branch" list A5 protects. Mitigated by A5's phrasing ("every class file that
  exists when the build runs"); falsified by CI.

## 12. Row-calls (numbered; the principal alone decides)

- **RC-L17-1 — the landing shape.** In-window: one class file, zero schema bytes,
  stacked before the batch's promotion leg (recommended — §1). Alternative:
  post-merge PATCH 0.3.1 under then-current train rules (recorded, more
  expensive). Recommend ACCEPT in-window.
- **RC-L17-2 — the widening verdict: nothing.** §5's measured answer (16-id
  ceiling, slot assignment, axis rule) with the heterogeneous deferrals armed.
  Recommend ACCEPT (an honest nothing, third of its kind — dc_psu widened, dmm
  nothing, scope one member, daq nothing).
- **RC-L17-3 — keep two classes.** §3.1's three-layer settlement; the OTDP-level
  merge question recorded as a non-motion with the reason. Recommend ACCEPT.
- **RC-L17-4 — the Parkview fixture's vendoring rule for A10.** A byte-copy
  fixture naming its source commit and regenerable from it, no network in CI.
  Alternative: skip the real-consumer arm (rejected — this slot exists because of
  the real consumer; the arm is the train's first executable conformance claim
  against shipped bytes). Recommend ACCEPT.

## 13. Precedent map (principle 9)

| L17 surface | in-tree precedent | why it fits |
|---|---|---|
| class file added to an in-window unreleased bump, zero schema motion | the batch rule (GOVERNANCE), L11's addendum motions, L12 §1, L13 §1 | same train, same bump, the cheapest member of the family |
| capture-class reference shape | `class-oscilloscope.json` (L13's design; the analyser's committed shape) | the lifecycle quartet is action-identical; §3.1 |
| mockup authored with hooks + placement + hookless idioms from birth | L12's `class-dmm.html`, L13's `class-oscilloscope.html` designs | the convention's third authored-from-birth instance |
| two-fixture expansion (committed example + derived mockup-shaped fixture) | L11's F-psu-1/F-psu-2 | the mockup reflects the real consumer's six-channel count, the committed example has two |
| shared census instance | `classref_census.py` (L12 §6) | the instrument must not fork between classes (F1's lesson), fourth instance |
| real-descriptor conformance arm | the registry-evidence posture of E-1 (§2.5's ladder) — but executable at design time because the bytes are public | the sweep's first conformance claim against a shipped plugin |
| host-knowledge seam for non-wire presentation data | §E.2.6 provenance, L13's trigger-marker | `calibration-context`'s structural home |

## 14. Appendix — evidence, disclosures, and the pre-flight record

**Pre-flight (the #181 R2 discipline):** `git fetch origin`; `git worktree list`
run before any tree action (nine trees listed; other lanes' trees untouched; this
lane's is `.wt/l17-m9x4`, branch `feat/l17-daq-classref` at `c64f3d05`); the
parallel design lanes (l14/l15/l16 worktrees present) share the base by design —
no remote branch of either repo touches `standards/plugin-ui-class-reference/`
beyond the L11 line this stack builds on. Parkview's fork: two branches (`main`,
`plugins/emeet-c960`); read via `gh api` only; nothing written.

**Gortex:** AVAILABLE to this subagent — every source read went through
`mcp__gortex__read` with worktree-prefixed paths (`BenchWeave/.wt/l17-m9x4/...`),
content identity verified where it discriminates (the 0.3.0 family and the L11
refute-fold motions exist only on this line, and the daemon served them); one
shell grep on an indexed source file was blocked by the PreToolUse hook (the
signature it refused to serve was re-obtained from the hook's own guidance text —
`select_references(corpus: Path, descriptor: Mapping) -> list | None`, corpus = the
standards root). Session start reported checkout discovery `view_building,
retryable`; `gortex repos reconcile` bound the new worktree (`l17-m9x4
ready_confirmed`) and the first reads cleared it. No daemon restart, no tracking
change. Large reads (the profile catalog, ui-contract, the L13 record) were
served to persisted files and decoded with python — 100% of each was consumed.

**Paths read as evidence:** `standards/GOVERNANCE.md` (via the L12/L13 records'
quoted rulings, re-verified against the file's sections named there);
`standards/otdp/0.2.3/device-profile-catalog.json` (the daq + oscilloscope +
logic_analyser profiles; all five daq action schemas in full; the namespace-
normalized structural comparison executed);
`standards/otdp/0.2.3/examples/class-daq.json` and `class-oscilloscope.json` (in
full); `standards/otdp/0.2.3/device-classes.md` (§1 coverage, §2 common contract,
§6, §11, §16, §17); `standards/otdp/0.2.3/otdp-measurement.schema.json` (in full);
`standards/otdp/0.2.2/device-profile-catalog.json` (the daq profile — the pin
check); `standards/plugin-ui-class-reference/0.3.0/` (`class-reference.schema.json`
in full, `layout.schema.json` in full, `class-dc_psu.json` in full, `README.md` in
full); `docs/internal/ui-contract.md` (§E.1 header, §E.2.0–§E.2.6 in full — the
series-assignment ceiling, slot mapping, y-axis rule, acquisition disclosure,
provenance); `docs/internal/ui-styleguide-mockups/class-dc_psu.html` (in full —
the authoring template); `docs/internal/ui-styleguide-workbench-design.md` (§8);
`.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md` (in full, addendum
and refute fold), `2026-10-19-classref-l12-dmm-design.md` (in full, from the l12
worktree — read-only), `2026-10-19-classref-l13-oscilloscope-design.md` (in full,
from the l13 worktree — read-only, uncommitted there), `2026-10-14-classref-
logic-analyser-design.md` (§7A, §8 — extracted in full). Parkview (gh api, pull-
only): `plugins/adc_6ch_12bit/descriptor.json` (in full), `docs/adapter.md` (in
full), `plugins/adc_6ch_12bit/README.md` (the hardware/wire sections), the repo
tree listing.

**Design-time executions beyond reading (three, all disclosed):** the A4 RED pair
(P3 — `select_references` via the primary checkout's venv against the worktree
corpus; wrote nothing outside `/tmp`); the P1/P2/P4 proof scripts (python over the
authored artifacts, the committed schema, and the fetched Parkview bytes; wrote
only `/tmp/l17proof/*`); and `gortex repos reconcile` (the CLAUDE.md-mandated
worktree binding).

**Honest disclosures to the dispatch:** (a) **the dispatch's channel list was
wrong in one id** — the sixth channel is `a7`, not `a5` (§4; no conformance
consequence, but the record reports bytes); (b) the dispatch's "action-identical"
claim is true for the lifecycle quartet and **false for `configure`** — the daq's
per-channel quantity/unit/range and the `sampling` field are materially different
from the scope's probe-scaled channels with `pretrigger_fraction`/`averaging_count`
(§0.1; this difference is exactly what §3.1's settlement rests on); (c) the
dispatch's framing "the distinction is capability profile and display" is
sharpened here to four structural differences (configure semantics, dataset
freedom, channel-role breadth, timing-evidence obligation) — two of which are
visible in today's reference (preset text, the calibration-context deviation) and
two of which are armed deferrals; (d) the real consumer streams **raw counts**
(`unit: "count"`, calibration `not_applied`), so the page this reference yields
will name `count` on its axis — the honest face, named as `calibration-context`,
not smoothed to volts; (e) no mockup existed (confirmed — the mockup directory
holds only the analyser and dc_psu committed files plus the lanes' in-flight
work), so the mockup is authored here per the convention, hooks and placement from
birth; (f) the L13 record was read from its lane's uncommitted worktree state —
its rulings (waveform widening, the third census instance, RC-L13-3's authored
trigger child) are treated as landing before this class per the batch-state
assumption, and P1e makes that dependency explicit and falsifiable.
