# UI contract follow-on — limiting state, setpoint triad, staleness, plot rules, processed data — design of record (issue #243)

**Date:** 2026-09-29
**Status:** Design complete — build may start on slice 1
**Issue:** madeinoz67/benchweave#243
**Scope of this record:** the five presentation-contract extensions of the #243 issue
(regulating/limiting state; measured/set/staged triad; staleness semantics; plot rules
for real instruments; processed-data marking), as two serialized slices over
`docs/internal/ui-contract.md` and the reference renderer.
**Triage:** public-safe — no person, client, bench, DUT serial, commercial term, or
install-specific operational detail appears in this record. All fixture identities stay
invented (`PSU-07`, `DAQ-47` family). Promoted to the public directory deliberately on
that basis, per the #242 precedent.

**Branch plan:** `feat/issue243-*` off `main` @ `08e1f67`. This record is committed in
the FIRST commit of slice 1's branch, before any acceptance test lands — that ordering
is what makes the acceptance rules in §6 provably pre-committed.

**Reading note (tooling disclosure):** the gortex MCP facade wedged mid-session during
this design pass (an abandoned `explore(localize)` left the session in
`localization_in_progress` with `allowed_tool_calls: 0`, refusing every read/search;
daemon itself healthy but `BenchWeave` DEGRADED with 8 failed files). Indexed-source
reads for this record went through `git show HEAD:<path>` on a clean tree — byte-exact
with the working tree, verified by `git status` (no tracked modifications). Corpus
JSON/MD reads went through native Read (not symbol-indexed paths).

---

## 0. Verdict and headline decisions

BUILD, as two serialized slices. The issue's five gaps are real and verified in source
(§2); all five are presentation-layer rules over wire shapes that already exist — no
standards bytes move, so the work is CLEAN under the #203 hold window (§9).

Seven headline decisions, each with its evidence section:

1. **`limiting` is a READING STATE, not a severity** (§1.1). The severity enum (§B.1)
   stays closed at six; `limiting` joins a new closed §B.3 state set and the §F.1 icon
   table's `state` class (beside `busy`/`hidden`/`staged`). One state, not two — the
   split is owner fork F1. It gets its own token `--bw-limiting` carrying computed
   non-confusion proofs against the six severity hues (the series-token precedent,
   applied to a state colour; §6/§7).
2. **The setpoint triad is a role table over the existing reading-tile** (§1.2): the
   measured value stays the tile's primary; the device-set value renders adjacent,
   labelled `Set {value} {unit}`, from gateway-observed state only; the staged value
   lives only in the staging input (already contract-labelled). The wire distinction
   the host derives this from already exists — OTDP parameter *semantic roles*
   (`measurement` vs `setpoint`, spec §4) — no wire change.
3. **Staleness is pre-committed arithmetic over committed wire values**
   (§1.3): stale iff `freshness_ms > 2 × cadence_ms`, strict, where the cadence is the
   descriptor's own committed field — `stream_limits.min_interval_ms` for streaming
   observations, the parameter's `max_age_ms` for polled reads (descriptor schema
   `otdp-device-descriptor.schema.json` lines 218/992, cited not restated). No known
   cadence ⇒ **no staleness verdict renders** — an honest negative, never a fabricated
   fresh verdict. The multiple 2× is owner fork F2.
4. **Plot axis assignment is a pure function of the declared channel set's units**
   (§1.4), the §E.2 set-derived discipline applied to axes: ≤2 distinct units among
   declared traces → one axis per unit in first-declaration order; **>2 distinct units
   → the plot refuses to draw traces** and renders a naming refusal note — the current
   renderer conflates V and A onto one value axis today (§2, verified), and silently
   conflate-anything is the wrong fix as much as no fix.
5. **Reference lines are a new neutral kind, never severity-coloured** (§1.4): an
   applied limit is a labelled reference line (border token, dotted), structurally
   distinct from the severity threshold markLine (severity hue, dashed).
6. **Decimation disclosure is required OUTSIDE the canvas** with fixed wording
   (`Acquired {n} samples · plotted {m}`), the styleguide's existing "freshness and
   partial-data state visible outside the chart canvas" rule made contractual and
   testable.
7. **Processed-data marking is a closed four-kind provenance classification**
   (§1.5): `measured` (default, unmarked), `derived` (OTDP measurement-model §8 —
   carries the expression and the structurally-unknown uncertainty marker), `device-averaged`
   (descriptor configure `averaging_count`, oscilloscope profile `[1, 64]` — the depth
   disclosed), `display-processed` (host display pipeline — processing name + window
   disclosed, source trace must remain available). Device averaging and display
   processing never share a label. The classification is host-supplied (the host knows
   from the descriptor's `derived_variables`, the applied configure echo, or its own
   pipeline); the preview wire carries no provenance field and moves nothing.

---

## 1. Mechanism

All tables below are the expected contract text (the load-bearing cells the L1/L2 pins
will parse). Row counts are pre-committed here and in §6.

### 1.1 Item 1 — the limiting state (§B.3, §A.1, §F.1, §E.1 reading-tile)

**New §A.1 row** (colour palette grows 24 → 25 rows):

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--bw-limiting` | *(build-chosen under §6/§7 constraints)* | *(same)* | Limiting/regulating reading-state border and label |

**New section §B.3 Reading states**, schema `State key | Meaning | Rendering | Announcement` — 1 row:

| State key | Meaning | Rendering | Announcement |
| --- | --- | --- | --- |
| `limiting` | A limit, not the set-point, is constraining the value (constant-current operation; a channel near full scale). Significant, not abnormal. | Icon + visible label `Limiting` + border in `--bw-limiting`, on the affected reading. No glow (SR-B2 reserves glow for advisory–trip SEVERITIES). Never dismissible while active; never rendered via the alert-bubble pattern; never enters a live region `alert`. Composes with any severity (both render; the severity keeps its glow rights). | Entry announces once via a `status` live region, coalesced; exit is silent. |

`limiting` is NOT a severity key (§B.1 unchanged), NOT a disabled reason (§C.2
unchanged), and MUST NOT be counted, aggregated or announced as an alert anywhere a
host summarises alerts. Distinct from `protection-active`: a limiting reading is
operating normally inside its envelope; `protection-active` is a control-disabled
reason tied to a protective trip.

**§F.1 icons grows 9 → 10 rows:**

| Icon key | Class | Shape description | Reference binding |
| --- | --- | --- | --- |
| `limiting` | `state` | Vertical arrow rising to meet a horizontal ceiling bar | `ArrowUpToLine` |

**§E.1 `reading-tile` row gains** (attributes) `data-bw-reading-state`, (class hooks)
`bw-reading__state`; the enforcement fixture renders the canonical tile WITH the state
(the mode-banner all-modes precedent — one fixture carries every row requirement).

### 1.2 Item 2 — the setpoint triad (§E.3)

**New section §E.3 Setpoint presentation (reading-tile sub-rows)**, schema
`Role | Placement | Required labelling | Never` — 3 rows:

| Role | Placement | Required labelling | Never |
| --- | --- | --- | --- |
| `measured` | The tile's primary value position (`bw-reading__value`) | — | Never sourced from a requested or staged value; a reading does not become verified because it rendered |
| `set` | Adjacent to the measured value, in the same tile (`bw-reading__set`), carrying `data-bw-reading-role="set"` | `Set {value} {unit}` — visible text, data font | Never derived from a staged input; renders only from gateway-observed device state (a setpoint-parameter read or a verified write's reported effective value) |
| `staged` | Only in the staging input (`numeric-input` / `rotary-control` rows already carry the `Staged` required text) | `Staged` (existing pins) | Never rendered inside a reading tile; never copied into the `measured` or `set` role |

The host derives role eligibility from the descriptor's parameter semantic roles (OTDP
spec §4: `measurement`/`setpoint`/`state`/`configuration` distinguish meanings — cited
from the corpus, not restated): an observation bound to a `setpoint`-role parameter
supplies the `set` role; a `measurement`-role parameter supplies `measured`.

### 1.3 Item 3 — staleness (§B.4)

**New section §B.4 Staleness**, schema `Rule id | Requirement` — 4 rows:

| Rule id | Requirement |
| --- | --- |
| `ST-1` | The staleness cadence is the descriptor's own committed value: for a streaming observation, `stream_limits.min_interval_ms`; for a polled read, the parameter's `max_age_ms`. The cadence is host-supplied configuration from the descriptor/profile — never invented, never a renderer default. |
| `ST-2` | A reading is stale iff `freshness_ms > 2 × cadence_ms` (strictly greater; equality is not stale). The predicate is a pure function of the wire's `freshness_ms` and the commissioned cadence. |
| `ST-3` | No known cadence (the descriptor/profile supplies none for that binding) ⇒ NO staleness verdict renders — the reading renders without a stale marker, which asserts freshness NOWHERE. `freshness_ms: null` renders `Unavailable` (existing behaviour) and is not stale. A device-declared quality string renders verbatim in the quality slot and is never overwritten or augmented by the computed verdict — two channels, never laundered into one. |
| `ST-4` | A stale reading renders dimmed (muted text treatment) and carries `data-bw-stale="true"` plus the visible marker `stale` appended to the quality line; it renders at reduced prominence, never at normal reading prominence. The fresh→stale transition announces once via a `status` live region, coalesced. A stale reading never renders without its marker (the OTDP §5 rule that stale readings cannot satisfy verification, at the presentation boundary). |

### 1.4 Item 4 — plot axes, reference lines, decimation (§E.2.3–§E.2.5, §E.1 engineering-plot)

**New §E.2.3 Y-axis assignment**, schema `Condition | Rendering` — 4 rows:

| Condition | Rendering |
| --- | --- |
| One distinct unit among the declared traces | One y-axis, named with the unit |
| Two distinct units among the declared traces | Two y-axes, first-declaration order (axis 1 = the earliest declared trace's unit, axis 2 = the other); every trace binds to its own unit's axis; each axis is named with its unit |
| More than two distinct units among the declared traces | The plot draws NO traces and renders a visible refusal note naming the condition (the manifest admits the declaration; the renderer refuses to conflate incommensurable units on shared axes) |
| Every trace bound to an axis is presentation-hidden | That axis does not render — but axis assignment never reshuffles: assignment is computed over the declared set, visibility filters after (the §E.2 styling discipline applied to axes) |

**New §E.2.4 Reference lines**, schema `Property | Requirement` — 4 rows:

| Property | Requirement |
| --- | --- |
| Labelling | Every reference line is labelled with its meaning and value (e.g. `Current limit · 2 A`); the label renders in the plot |
| Neutrality | Reference lines render in the border token (`--bw-border`), dotted — never a severity hue, never a series token |
| Distinctness | A reference line is a distinct kind from a severity threshold (§E.1 `engineering-plot` threshold: severity hue, dashed): an applied or configured limit is a reference line, not a threshold; the two never share colour or dash |
| Carrier | A reference line whose target traces are all hidden still renders (the threshold-carrier rule applied: hiding data must not launder away a configured limit) |

**New §E.2.5 Acquisition disclosure**, schema `Property | Requirement` — 3 rows:

| Property | Requirement |
| --- | --- |
| When required | Whenever the host draws fewer points than it acquired for a trace (decimation, downsampling, windowing-in), the plot MUST disclose it |
| Placement | Outside the canvas element, visible text (class hook `bw-plot__acquisition`, attribute `data-bw-acquisition`) — never inside the chart image, never tooltip-only |
| Wording | `Acquired {n} samples · plotted {m}` — counts from the host's own acquisition pipeline; an acquisition rate may be appended when known (`at {rate}`) |

**§E.1 `engineering-plot` row gains** (attributes) `data-bw-trace-provenance`,
`data-bw-acquisition`, (class hooks) `bw-plot__acquisition`. Y-axis and reference-line
drawing claims are enforced by the real-render companion (`EngineeringPlot.render.test.tsx`,
SSR echarts — the G-render rule), not by jsdom DOM pins.

### 1.5 Item 5 — processed data (§E.2.6)

**New §E.2.6 Trace provenance**, schema `Provenance | Required marker | Disclosure | Constraint` — 4 rows:

| Provenance | Required marker | Disclosure | Constraint |
| --- | --- | --- | --- |
| `measured` | none (default) | — | Never marked; a trace with no host knowledge renders as measured and asserts nothing more |
| `derived` | `derived` | The derivation expression (from the dataset's `derivation` marker, OTDP measurement-model §8) and `uncertainty unknown` — the §8 structural unknown rendered, never hidden | A derived trace always carries the uncertainty-unknown marker; its displayed precision never exceeds its sources' |
| `device-averaged` | `device averaging {n}` | The applied device averaging depth `{n}` (the descriptor configure `averaging_count`, oscilloscope profile) | The depth is the applied configured value from the observed echo — never a default; marker text never uses the display-processing vocabulary |
| `display-processed` | `display processing: {name} {window}` | The processing name and window | Never silently replaces the source: the source trace (or its min/max envelope) remains rendered or revealable in the same plot; marker text never uses the device-averaging vocabulary |

Legend items carry `data-bw-trace-provenance="<kind>"`. The classification is
host-supplied at the composition layer (a `provenance` field on the trace prop — the
same host-knowledge seam as `channel_hints`); the preview wire carries no provenance
field and no standards byte moves. OUT OF SCOPE per the issue: which processing
functions a host offers and how it computes them.

**Renderer changes** (both slices): `ReadingTile` gains `set`, `state`, `stale` props;
a pure `staleness.ts` module (the ST-2 predicate — property-tested, no React);
`EngineeringPlot` gains `yAxes` derivation from trace units, `referenceLines`,
`acquisition`, and per-trace `provenance`; `PlotTrace` grows the provenance field;
`tokens.css`/`themes.css` gain `--bw-limiting`; proof fixtures and stories grow
accordingly (guide rule 5); `ui-styleguide.md` gains the presentation rules as
implementation guidance; `docs/device-developer-guide.md` presentation section moves
(obligations 3/12).

---

## 2. Root cause — verified in source

The issue's five premises, each confirmed against `main` @ `08e1f67`:

1. **No slot for regulating/limiting:** §B.1 is the closed six-key severity enum; §F.1
   has exactly three `state` keys (`busy`, `hidden`, `staged`). A constant-current
   supply reading must today borrow `advisory`/`warning` (wrong semantics, wrong
   dismissal class) or render unmarked. Confirmed in `docs/internal/ui-contract.md` §B.1/§F.1.
2. **No set display:** `ReadingTile` renders label/value/unit/quality/freshness only
   (`ui/src/components/readings/ReadingTile.tsx`); `DeviceWorkbench` stages
   `stagedVoltage` in `RotaryControl`/`NumericInput` and displays no device-set value
   anywhere. Confirmed.
3. **Staleness undefined:** the served wire's `quality` is an unconstrained string and
   `freshness_ms` an integer with no attached semantics
   (`standards/plugin-ui-preview/0.1.1/preview-document.schema.json` `$defs/observation`);
   `fixtures.ts` renders them as display strings (`freshness_ms === null ?
   "Unavailable" : "${freshness_ms} ms"`). Nothing anywhere defines when a reading is
   stale. Confirmed. (Distinct wire, distinct vocabulary: the OTDP runtime envelope's
   reading `quality` is the closed `valid/stale/invalid` (spec §5) — device-declared
   staleness exists at that layer and renders verbatim; the undefined part is the
   PRESENTATION-side computation from age vs cadence, which is what §B.4 defines.)
4. **Plot rules insufficient:** `EngineeringPlot.tsx` builds exactly one `yAxis`
   (type value) — the `voltageTrend`+`currentTrend` fixtures (V and A) draw on ONE
   shared axis today. Exactly one `threshold` (severity-coloured dashed markLine), no
   reference-line concept, no acquisition/decimation disclosure anywhere in the
   component. Confirmed (`ui/src/components/plots/EngineeringPlot.tsx`, `setOption`
   xAxis/yAxis/series/markLine).
5. **Processed data indistinguishable:** `PlotTrace` carries id/label/unit/values
   only; the preview wire `channel` carries variable_id/label/unit/color_role/visible
   only. An OTDP-derived variable (uncertainty structurally unknown, measurement-model
   §8), a device-averaged trace (`averaging_count` [1,64], catalog lines 733/886) and
   a host-smoothed trace all render identically to a measured trace. Confirmed.

---

## 3. Slice plan

Slices share `ui-contract.md`, `contract-coverage.test.ts` and
`contract-enforcement.test.ts`, so they serialize (#242 precedent): slice 2 parks at
review-complete and rebases once after slice 1 merges. Each slice is independently
landable, two-repo (the renderer moves ⇒ `build:preview` rebuild ⇒ committed
`preview_assets` in the SDK ⇒ SDK PR first, then the main-side pointer — the #242
slice-2/3 shape), and carries its own acceptance rule.

### Slice 1 — presentation states, setpoint triad, staleness (issue items 1–3)

Scope: §A.1 `--bw-limiting` row (+ tokens.css/themes.css values chosen under §6/§7);
§B.3 (1 row); §B.4 (4 rows); §E.3 (3 rows); §F.1 `limiting` (10 rows total); §E.1
`reading-tile` row extensions; `ReadingTile` props (`set`, `state`, `stale`);
`staleness.ts` pure predicate + property tests; `--bw-limiting` computed proofs
(T1/T2-limiting, §6) in `series-colors.test.ts` (the colour-proof home); L1 count pins
(§A.1 24→25; §F.1 9→10; the definition-row arithmetic 45→54) and L2 fixtures/blocks
(§B.3, §E.3 per-row renders; the extended reading-tile fixture); proof-fixture growth
(the PSU fixture gains a setpoint tile with set+limiting, a stale variant, and a
2×-boundary control) + stories; styleguide deltas; device-developer-guide pointer.

**Defers to slice 2:** everything in §1.4/§1.5. **Defers to rows:** §11.

### Slice 2 — plot axes, reference lines, decimation, provenance (issue items 4–5)

Scope: §E.2.3 (4 rows), §E.2.4 (4 rows), §E.2.5 (3 rows), §E.2.6 (4 rows); §E.1
`engineering-plot` row extensions; `EngineeringPlot` multi-axis + referenceLines +
acquisition disclosure + trace provenance markers; real-render test growth
(`EngineeringPlot.render.test.tsx`: second axis present, reference line neutral +
labelled, >2-unit refusal draws no series, threshold keeps severity hue); L1
arithmetic 54→69 and the §E.2 sub-table pins; L2 provenance per-row block; proof
fixtures (DAQ-derived trace, device-averaged trace, display-processed-with-source) +
stories; styleguide plot-section deltas; device-developer-guide pointer.

**Defers:** §11.

---

## 4. Precedent

1. **The #242 pin families (L1/L2/L3)** — `contract-coverage.test.ts` /
   `contract-enforcement.test.ts` / the token-equality arm: every new table lands with
   its count pin and per-row enforcement in the same change. Directly extended; no new
   machinery.
2. **§C.2/§C.3 per-row L2 blocks** — `contract-enforcement.test.ts` renders the
   disabled-reason keys and refusal codes key-by-key in their own describe blocks: the
   shape §B.3, §E.3 and §E.2.6 per-row enforcement copies (a table row family with
   per-key rendering, not one overloaded fixture).
3. **`series-colors.test.ts`** — computed proofs (contrast, CIEDE2000 non-confusion,
   dual CVD models, pre-committed thresholds) on values parsed from the CSS: the exact
   machinery `--bw-limiting` proofs reuse (fewer pairs, same arms).
4. **§E.2's set-derived discipline** — assignment as a pure function of the declared
   channel set, visibility filtering after: extended to y-axis assignment (§E.2.3).
5. **The threshold-carrier rule** (`EngineeringPlot.tsx`, all-channels-hidden carrier
   series) — extended to reference lines (§E.2.4 carrier row).
6. **`EngineeringPlot.render.test.tsx`** — real-render (SSR echarts) companions for
   draw-visibility claims (the G-render rule): the enforcement home for axis/reference/
   refusal drawing claims.
7. **The mode-banner all-modes fixture** — one enforcement fixture carrying every
   variant a row requires: the extended reading-tile fixture's shape.
8. **OTDP corpus citations** — parameter semantic roles (spec §4), reading
   quality/age (§5), `stream_limits.min_interval_ms` / `max_age_ms` (descriptor
   schema), `averaging_count` [1,64] (device-profile catalog), derived-variable
   `derivation` marker + structurally-unknown uncertainty (measurement-model §8):
   cited from the vendored bytes, never restated as our own definitions.

---

## 5. Invariant and cross-surface impacts

- **Decisions touched:** A02 (the staleness cadence is commissioned host
  configuration from the descriptor — never a renderer default; a missing requirement
  blocks the verdict rather than defaulting to fresh); A06 (the no-cadence honest
  negative; device-declared vs computed staleness never laundered into one channel);
  A04 unchanged (limiting blocks nothing — it is presentation of normal operation; the
  disabled-reason and confirm machinery are untouched); A13's renderer-neutral analogue
  (one presentation contract behind any host renderer — the state these rows add is
  renderer-neutral vocabulary, not reference-renderer behaviour).
- **Invariants:** no new CTL/STO/CON/REG number. The staleness predicate is a pure
  function of committed wire + commissioned values (the CON-12 family shape), carried
  as a definition row + test, not an invariant statement — the #242 posture unchanged.
- **`docs/internal/invariants.md`:** untouched.
- **Drift-and-obligations:** row 12 already names the contract and its gates; both
  slices are the row-12 motion (contract-table edit + pins in one change). Row 3
  (device-developer-guide presentation text) moves in both slices. Row 7
  (renderer freshness / SDK pointer) fires for both slices. No other rows fire.
- **Review-rubric Step 1:** both slices carry design-time tier calls with keyword-scan
  results — §12 of this record.
- **CI map:** no new jobs. The `ui` job grows test time (property + colour-math tests
  are pure computation, milliseconds); two SDK CI runs (one per slice's preview_assets
  commit); `gates` unaffected beyond the pointer-advance checkout. The colour-proof
  arm adds ~50 CIEDE2000 evaluations per theme — noise.
- **SDK blast radius:** ONLY `src/benchweave_sdk/preview_assets/` (committed renderer
  bytes) + the main-side pointer, per slice. No corpus, manifest, lock, vendored-tree
  or version-string motion. `ui/package.json` NOT bumped (the #242 D5 posture rides).

---

## 6. Pre-committed acceptance rules

Written before any build measurement. The enumerations below ARE the pre-commit: the
L1/L2 fixtures must cover AT LEAST these sets (superset allowed, subset is a kill).
Kill directions are binary per row; "underpowered" means the measurement cannot decide
the claim and is NEVER a pass.

**Common to both slices (gate doctrine, unchanged from #242):** every acceptance item
carries a RED witness in the PR (the mechanism disabled — row deleted, attribute
dropped, token value changed, predicate mutated — turns the check red before the fix);
gates read TRUE exit codes (unpiped/PIPESTATUS/output-to-file), bare `uv run mypy`
fresh-cache, bare `uv run ruff check .`; ui: bare `npm --prefix ui` exit codes for
test/typecheck/lint; counts from junitxml attributes or exit codes, never a filtered
summary line. Standards-hold tripwire at design AND push:
`git diff origin/main...HEAD -- standards/` empty, no version-string touches, SDK diff
limited to `src/benchweave_sdk/preview_assets/`.

### Slice 1

| # | Metric | Effect size (N) | Pass (ship) | Kill | Underpowered |
|---|---|---|---|---|---|
| S1-A1 | L1 row presence | §A.1 25 rows incl. `--bw-limiting` (hex, both themes); §B.3 exactly 1 row (`limiting`); §B.4 exactly 4 rows (`ST-1..ST-4`); §E.3 exactly 3 rows (`measured`/`set`/`staged`); §F.1 exactly 10 rows (incl. `limiting`, class `state`); definition-row arithmetic 5+15+4+3+3+6+10+1+4+3 = 54 | 100% present and parsable, counts exact | any missing/unparsable row, or any count off | if the fixture could shrink with the doc — controlled by this enumeration; reviewer verifies fixture ⊇ this list |
| S1-A2 | L3 token equality | `--bw-limiting` vs `themes.css`, both themes, both directions | equal both ways | any mismatch | a token in CSS outside the §A.1 table (the existing reverse-direction arm already refuses this) |
| S1-A3 | Computed proofs for `--bw-limiting` | T1 contrast ≥ 3.0:1 vs `--bw-surface` AND `--bw-surface-recessed` (1 token × 2 surfaces × 2 themes = 4 ratios); T2-limiting ΔE00 ≥ 10.0 vs all 6 severity hues × 4 viewing conditions × 2 themes = 48 values, dual CVD models (Machado + Viénot/Brettel), both must pass every pair | all thresholds met, both models agree everywhere | any value below threshold; any model disagreement (escalate/redesign, never pass) | a model disagreement on any pair is INCONCLUSIVE for that pair — the slot is redesigned, not waved through |
| S1-A4 | L2 rendering | §B.3 per-row block: reading-tile with `state=limiting` renders the `Limiting` label, the icon, `data-bw-reading-state="limiting"`, the `bw-reading__state` hook, and NONE of role=`alert`/alert-bubble classes; §E.3 per-row block: setpoint tile renders `Set 12.5 V` adjacent with `data-bw-reading-role="set"`; the plain tile renders NO set element; base reading-tile fixture carries every extended attribute/hook | 100% of the enumerated assertions | any missing element; any `set` element on a tile without set evidence | as S1-A1 |
| S1-A5 | Staleness predicate (property test) | grid: cadence ∈ {100, 1000} ms × freshness ∈ {0.5×, 1.9×, 2.0×, 2.1×, 10×} plus {null} plus no-cadence; mutants: `>=` for `>`, 3× for 2×, cadence/freshness swapped, no-cadence→fresh | all 10 grid cells correct (2.0× NOT stale; 2.1× stale; null → no verdict; no-cadence → no verdict); every mutant reds ≥ 1 cell that the true predicate passes | any cell wrong; any mutant that survives | if a mutant is indistinguishable on the whole grid — the grid is underpowered and must grow (add cells), never pass |
| S1-A6 | Composition proof (PSU fixture) | 5 properties: (a) limiting tile: icon+label+border token, no alert role, no glow class; (b) setpoint tile: measured primary + `Set 12.5 V` adjacent + staged value ONLY in the input; (c) stale variant: dimmed + `stale` marker + `data-bw-stale`; (d) fresh control: unmarked; (e) 2.0×-boundary control: unmarked | 5/5 | any property failing | a fixture that could pass vacuously — each variant must be present in the fixture definition (enumerated) |
| S1-A7 | RED witnesses | row deletion (L1 red), attribute drop (L2 red), token value perturbation (S1-A2/A3 red), each predicate mutant (S1-A5 red) | ≥ 4 distinct witnessed mutations in the PR message | any check without a witness | — |
| S1-A8 | Cross-surface | SDK preview_assets committed + SDK PR open/pushed BEFORE pointer; main pointer advance; `standards/` diff empty; device-developer-guide presentation text updated; `ui/package.json` version unchanged | all hold | any fails | — |

### Slice 2

| # | Metric | Effect size (N) | Pass (ship) | Kill | Underpowered |
|---|---|---|---|---|---|
| S2-A1 | L1 row presence | §E.2.3 exactly 4 rows; §E.2.4 exactly 4 rows; §E.2.5 exactly 3 rows; §E.2.6 exactly 4 rows; arithmetic 54+15 = 69; §E.1 row count stays 10 with the extended cells | 100% present, counts exact | any missing row / count off | as S1-A1 |
| S2-A2 | L2 rendering | §E.2.6 per-row block: each provenance kind renders its required marker (`derived`, `uncertainty unknown`, `device averaging 8`, `display processing: {name} {window}`) and `data-bw-trace-provenance`; `measured` renders NO marker; acquisition disclosure element (`bw-plot__acquisition`, `data-bw-acquisition`, text `Acquired 1000 samples · plotted 25`) present when decimated, ABSENT when not (control) | 100% | any missing/mislabelled marker; disclosure present on a non-decimated plot | as S1-A1 |
| S2-A3 | Real-render (SSR echarts) — axes | V+A fixture (2 distinct units): SVG carries 2 y-axis name texts (V and A); voltage series binds axis 1, current axis 2; single-unit fixture: exactly 1 y-axis | all hold | any unit sharing an axis with a different unit; any missing second axis | if jsdom-only assertions are substituted for the SVG evidence — the G-render rule forbids it; a payload-pinned test cannot falsify a draw claim |
| S2-A4 | Real-render — reference lines & refusal | reference line: SVG label text present, stroke resolves to the border token (NOT any severity hue — asserted against all six); threshold control keeps its severity hue; >2-unit fixture: NO series drawn + refusal note rendered; hidden-target reference line still renders (carrier) | all hold | reference line carrying a severity/series colour; a drawn series on a >2-unit plot; a vanished hidden-target reference line | as S2-A3 |
| S2-A5 | Provenance composition proof (DAQ fixture) | 5 properties: (a) derived trace carries `derived` + its expression + `uncertainty unknown`; (b) device-averaged carries `device averaging {n}` with n from the fixture's applied echo; (c) display-processed carries its name+window AND the source trace remains present in the same plot's declared set; (d) no two kinds share marker vocabulary (device averaging ≠ display processing text prefixes); (e) a processed value renders no more decimal places than its source fixture value | 5/5 | any property failing | vacuous-pass control: the fixture must contain all four kinds + a source/processed pair (enumerated) |
| S2-A6 | RED witnesses | axis rule reverted to single-axis (S2-A3 red); reference line recoloured to a severity hue (S2-A4 red); disclosure line deleted (S2-A2 red); provenance marker dropped (S2-A2 red) | ≥ 4 witnessed mutations | any missing | — |
| S2-A7 | Cross-surface | as S1-A8 | all hold | any fails | — |

**Pre-committed thresholds (stated before any computation runs):** T1 ≥ 3.0:1 (WCAG
2.2 non-text contrast, both surfaces); T2-limiting CIEDE2000 ≥ 10.0 per pair per
condition {normal, deuteranopia, protanopia, tritanopia}, both CVD-model arms must
pass every pair (machinery and constants identical to `series-colors.test.ts`).
Staleness multiple 2×, strict inequality. These numbers are not relaxable at build
time; severity may go up, not down.

---

## 7. Feasibility — prior measured evidence, no new measurement

No colour search was run for this record (pre-commit discipline: thresholds first,
numbers later). The feasible space is known non-empty from #242's §7 measurement
(2026-09-28, this repository's tokens): 342 light / 479 dark LCh candidates cleared
T1+T2 simultaneously for series slots, where T2 there demanded ΔE00 ≥ 10 versus FIVE
severity hues — the T2-limiting arm here demands the same bound versus all six, one
more hue, from the same search space; the space is not knife-edge. The build chooses
`--bw-limiting` under §6's constraints; if NO hue clears both themes at those
thresholds, the kill path fires (redesign the slot — e.g., a bordered-neutral treatment
carrying no hue at all — and bring the negative result back; that is a legitimate
outcome, not a failure to ship).

---

## 8. Top risks

| Risk | Falsifier / mitigation |
|---|---|
| **R1 — ECharts multi-axis interplay with the threshold/reference carriers.** The existing threshold carrier relies on series[0] and axis auto-extent; a second yAxis changes extent and markLine binding behaviour. | Real-render tests are the acceptance (S2-A3/A4); the carrier row is pinned (hidden-target reference still draws). Falsified if SSR shows a markLine clipped by the wrong axis extent — the carrier gains explicit axis pinning. |
| **R2 — The >2-unit refusal breaks existing served previews.** A plugin preview declaring 3+ units in one plot renders a refusal note after slice 2. | The build sweeps the in-tree preview documents/fixtures for multi-unit plots before landing (the refusal is per-plot, visible, and names the condition — degrade-loudly, not silent). Any real hit is disclosed in the PR; the plugin-ui validation side (warning at authoring time) is a deferral row (D6), out of this increment's presentation-only scope. |
| **R3 — Staleness overreach: presentation verdicts could be read as device truth.** | §B.4 ST-3 keeps the two channels structurally separate (verbatim quality string vs computed marker); the contract text says the computed verdict asserts freshness nowhere and overrides nothing. Falsified if any rendering path lets the computed marker replace or edit the quality string — S1-A4/S1-A6 pin the separation. |
| **R4 — `--bw-limiting` infeasible at T2-limiting in both themes (6 hues, dual models).** | §7's prior evidence says the space is large; the kill path is pre-committed (redesign to a hue-less treatment + honest negative). Falsified by the build's own computed proof failing. |
| **R5 — One reading-tile fixture carrying every variant weakens the base-row pin** (a plain tile regresses invisibly). | The §E.3 per-row block includes the PLAIN tile (no set element) as a control (S1-A4); the mode-banner precedent's all-modes fixture is the shape, and its control is the negative assertion. |
| **R6 — The preview renderer cannot demo staleness/provenance from the wire** (no cadence, no provenance field on the preview document) — the served preview shows none of it. | By design: the composition layer is the host-knowledge seam, proofs run on composition fixtures + stories, and the preview's silence is the honest no-cadence negative (ST-3). Disclosed residual; wire fields are deferral row D2/D3 territory, never this increment. |
| **R7 — Announcement rules ("once, coalesced") are not mechanically pinnable in jsdom.** | The contract states them; enforcement pins the PRESENCE of the status-region announcement (S1-A4/S1-A6), and the once/coalesced behaviour stays story + browser-review — the disclosed boundary, same class as the CSS-hidden-label residual in §C.2's enforcement. |

---

## 9. Standards-involvement verdict: **CLEAN**

Both slices, both directions:

- No corpus bytes, manifest rows, contract locks, version strings, or SDK vendored
  tree move. SDK diffs limited to `src/benchweave_sdk/preview_assets/` (built
  renderer) + the main-side pointer (a SHA, not a version string). `ui/package.json`
  unbumped.
- Everything OTDP-side is CITED, never restated: parameter semantic roles and
  reading quality/age (spec §4/§5); `stream_limits.min_interval_ms` and `max_age_ms`
  (`otdp-device-descriptor.schema.json`); `averaging_count` bounds (device-profile
  catalog, oscilloscope configure input); the `derivation` marker and
  structurally-unknown uncertainty (measurement-model §8). The preview wire's
  `quality`/`freshness_ms` free shapes are consumed as-is — no decoder change to
  `ui/src/preview/api.ts` is required by either slice (provenance/staleness ride the
  composition layer, not the wire).
- The staleness cadence is host configuration derived from the descriptor/profile —
  A02's commissioned-value posture; no default cadence is invented anywhere.
- Tripwire per slice: `git diff origin/main...HEAD -- standards/` empty; SDK diff
  limited to `preview_assets/`.

---

## 10. Owner decision rows

Two forks. Everything else is decided with stated evidence.

| Row | Question | Default taken | Why | Kill/change path |
|---|---|---|---|---|
| F1 | `limiting` as ONE state, or a `limiting`/`regulating` PAIR (CV regulation vs a limit binding)? | ONE key, `limiting` | Both issue cases share the operator meaning — "a limit, not the set-point, constrains this value"; the wire carries no field distinguishing control mode today, so a split invents vocabulary nothing can feed; one marker set keeps the non-confusion proofs and the icon table minimal | A wire field naming control mode (or a descriptor surface distinguishing regulation from limiting) arrives — split is a one-row §B.3 addition + icon row + proofs, additive |
| F2 | The staleness multiple: 2× (the issue's example), or another value? | 2×, strict | At 2× the reading has missed at least one entire emission/refresh interval with margin; smaller marks stale earlier (more conservative), larger later; the issue's own example adopted with the mechanism owned here | One-line §B.4 change + the S1-A5 boundary cell moves with it — row-level, no mechanism change; owner may tighten to 1.5× (conservative direction) without redesign |

---

## 11. Deferral table

All rows use the `.claude/deep-review/README.md` deferral-row contract.

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | Wire-carried staleness inputs (cadence on the preview document or binding catalogue) so non-descriptor hosts can compute ST-2 without host configuration | documentation here | a plugin-ui-preview or interface train opens that adds a cadence/freshness-policy field to a served wire document — the train's PR is the arrival |
| D2 | Wire-carried trace provenance (a preview/interface channel field naming derived/processed kind) replacing the composition-layer classification | documentation here | the same train as D1, or a plugin-ui train touching the plot channel shape |
| D3 | A `regulating` state key split from `limiting` (fork F1's alternative) | documentation here | a descriptor/profile/wire surface distinguishing constant-voltage regulation from limit binding arrives — its admission PR is the arrival |
| D4 | Min/max envelope GENERATION for display-processed traces (data processing, out of the issue's presentation scope); the contract carries only the source-remains-available rule | documentation here | a host implements envelope generation and needs its rendering rules — the implementing PR is the arrival |
| D5 | Authoring-time validation guidance for >2-unit single plots (a plugin-ui validator warning; renderer-side refusal lands now) | documentation here | a plugin-ui standards train opens that touches plot validation — the train's PR is the arrival |
| D6 | `ui/package.json` bump + `inventory.json` renderer_version for this increment's additions (the #242 D5 posture) | documentation here | the next ui release train opens (a version-bump commit in `ui/package.json`) |
| D7 | Numeric-precision enforcement beyond the fixture-level rule (a general significant-figures checker for processed readings) | documentation here | a second processed-reading surface arrives (an admin or dataset view rendering processed scalars) — its PR is the arrival |

---

## 11a. Review fold (2026-09-29, slice 1) — the staleness premise amended

The S1 review battery's owner-worded premise row amends §1.3's arithmetic (the
record's §1.3 text stays frozen above; THIS note governs the landed contract):
`max_age_ms` is the polled read-acceptance window — stale iff
`freshness_ms > max_age_ms` (1×, STRICT — the descriptor's own disavowal
boundary; the 2× rationale dies with the premise). Streaming
`min_interval_ms` is a rate CAP (spec §158): silence is healthy — a
stream-cadence source renders NO staleness verdict; the missed-data signal is
the gap event. The grid gains max_age {0,1} cells (zero-age =
fresh-acquisition-only, correct semantics per the 7-of-9 corpus case). The
comparator for the limiting proofs is `--bw-text-muted` (the neutral severity's
actual rendering), with `--bw-border` pinned alongside; light re-derived to
`#274076` under the extended census (the shipped `#877085` red it at 5.44).
The search screens (T1 ≥ 3.3, T2 ≥ 11.0) are STANDING pre-commit doctrine for
every future token slot.

Deferral row (added by the fold): wire-side staleness spacing bounds — a
future corpus field bounding acceptable inter-sample spacing above the rate cap
reopens streaming staleness; its train's PR is the arrival.

## 12. Tier call and Step-1 keyword scan (the #254 rule)

**Tier: both slices TIER 3 — slice 1 on two triggers, slice 2 on one.**

1. **Path rule (BOTH slices):** both slices advance the `packages/sdk` submodule
   pointer (preview_assets + pointer is the two-repo renderer shape) — "advances the
   `packages/sdk` submodule pointer" is a named Tier-3 trigger, and it is the ONLY
   trigger slice 2 trips.
2. **Keyword rule (slice 1 only):** slice 1's expected diff text carries the keyword
   `protection` — the §B.3 limiting row must distinguish the state from the disabled
   reason `protection-active` and from protective trips (the vocabulary is
   load-bearing, not incidental; the rubric's keyword-rule-interplay paragraph names
   exactly this shape as Tier-3 by design). **Slice 2's expected diff text carries
   ZERO of the eight keywords** (measured, below) — the rubric's disclosed residual
   applies: its Tier-3 depth is bought by the pointer path rule, not by keywords, and
   the tier (and with it the standing two-lane adversary) still holds.

Consequence: the standing two-lane adversary applies to both slices (the Tier-3 /
trust-boundary standing rule), and the standards-governor mandate does NOT fire (no
`standards/` touch — §9).

**Scan method and measured results:** each slice's expected diff text was assembled
from §1's verbatim table rows and Notes cells for that slice (slice 1 = §1.1–§1.3,
slice 2 = §1.4–§1.5) plus the §6-named test-wording literals, extracted from this
record to a temp file, and grepped case-insensitively for the eight Step-1 keywords
(measured 2026-09-29, before any build diff exists):

| Keyword | Slice 1 expected diff (§1.1–§1.3 + tests) | Slice 2 expected diff (§1.4–§1.5 + tests) |
|---|---|---|
| `threading` | 0 | 0 |
| `asyncio` | 0 | 0 |
| `subprocess` | 0 | 0 |
| `sha256` | 0 | 0 |
| `hashlib` | 0 | 0 |
| `migrate` | 0 | 0 |
| `recovery` | 0 | 0 |
| `protection` | 2 (both inside `protection-active`, in §B.3's distinctness prose) | 0 |

**Record-inclusive note:** this design record commits with slice 1's first commit and
is itself part of slice 1's committed diff; record-wide it carries `protection` ×8
(`protection-active` ×5 — the distinctness prose, risk R3's vocabulary, and this
keyword table itself). The counts above are the CONTRACT-ROW scan (the rubric's
subject); the committed-diff total for slice 1 is therefore ~10. Counts growing
during build keep the Tier-3 call true; for slice 2, even all-zero keywords leave the
pointer-advance trigger holding Tier 3.

---

## 13. Finding summary (for the ledger)

1. **The preview wire meets the renderer with two different quality vocabularies:**
   the plugin-ui-preview `observation.quality` is an unconstrained free string, while
   the OTDP runtime envelope's reading quality is the closed `valid/stale/invalid` —
   the renderer renders the free string verbatim and (after §B.4) computes its own
   staleness verdict in a structurally separate channel. Durable, non-obvious, and the
   reason staleness had to be defined as arithmetic rather than a mapping.
2. **The gortex localize-wedge trap** (tooling, session-level): an abandoned
   `explore(localize)` call leaves the session's MCP facade in
   `localization_in_progress` with `allowed_tool_calls: 0` — every subsequent
   read/search/explore/wakeup refuses with `localization_complete` while the daemon
   itself reports healthy; `git show HEAD:<path>` on a clean tree is the sanctioned
   escape (Bash git is allowed; native Read is hook-blocked on symbol-indexed paths).
   Both proposed to the memory ledger.
