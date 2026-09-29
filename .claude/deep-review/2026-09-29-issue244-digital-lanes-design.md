# plugin-ui `digital_lanes` plot kind — design of record (issue #244)

**Date:** 2026-09-29
**Status:** Design complete — build may start on slice 1
**Issue:** madeinoz67/benchweave#244
**Scope of this record:** a new `digital_lanes` plot kind for the plugin-ui
standard (0.2.0 → 0.3.0) and the plugin-ui-preview wire (0.1.1 → 0.2.0), its
validator semantics, its renderer-neutral contract rows, the reference
renderer, and the decoder-annotation surface, as three serialized slices.
**Triage:** public-safe — no person, client, bench, DUT serial, commercial
term, or install-specific operational detail appears in this record. All
fixture identities are invented (`LA-01`, channel ids `ch1…chN`, decoder
names `UART-REF`/`SPI-REF`). Promoted to the public directory deliberately,
per the #242/#243 precedent.

**Branch plan:** `feat/issue244-*` off `origin/main` (post-#243-S2 landing;
the design was verified against `origin/main`, which the local checkout
trailed by 31 commits — see the reading note). This record is committed in
the FIRST commit of slice 1's branch, before any acceptance test lands —
that ordering is what makes the acceptance rules in §6 provably pre-committed.

**Reading note (tooling disclosure):** the gortex MCP facade was unavailable
to this design pass (checkout-discovery timeout, then "repository not
tracked"); indexed-source reads went through `git show origin/main:<path>`
on a fetched, clean tree — byte-exact, verified by `git status`. The rtk
output filter also truncated one `git show` (140 of 485 lines) — the
`rtk proxy` bypass was used for full-file reads thereafter.

---

## 0. Verdict and headline decisions

BUILD, as three serialized slices (one standards train: plugin-ui 0.3.0 MINOR
+ plugin-ui-preview 0.2.0 MINOR, bumping together as one increment per
GOVERNANCE "different standards may share a merge only when they are one
increment"). The premise verified in source: a 32-channel logic capture is
unrepresentable today — `$defs/plot.properties.kind` is
`time_series | waveform` and `y`/`channel_hints` cap at 16
(`standards/plugin-ui/0.2.0/ui-manifest.schema.json:32`), the preview wire
mirrors both (`standards/plugin-ui-preview/0.1.1/preview-document.schema.json`
`plot_view.kind`, `channels.maxItems: 16`), and the colour/dash/symbol slot
math caps analog identity at 16 BY CONSTRUCTION (ui-contract §E.2: "a 17th
declared id would collide with slot 8's pair; it is refused by the wire
schema (the ceiling), not by the renderer"). Colour cannot carry identity at
32+ channels; lane layout is the correct substitute, exactly as the issue
states. The wire already carries everything the lanes grammar needs (§2).

Seven headline decisions, each with its evidence section:

1. **plugin-ui 0.2.0 → 0.3.0, MINOR — and the served range slides narrow:
   `>=0.2.0,<0.3.0` → `>=0.3.0,<0.4.0`.** The MINOR case: a new enum member
   plus new per-kind grammar plus NORMATIVE renderer behaviour (the
   edge-preserving decimation rule) is new normative capability, not the
   `approver_token` additive-optional-field PATCH shape (GOVERNANCE change-class
   table). The narrow slide is FORCED — by policy + the one-live-object rule +
   the manifest's own F1/D2 note (`standards/standards-manifest.json:49`) —
   with this mechanism (amended 2026-09-29 per the governor ruling; the
   earlier "0.2.0 corpus row pins the digest" claim was wrong in mechanism —
   `contracts.py` carries NO corpus-manifest row): the version's normative
   bundle row lists the one live code object
   (`src/benchweave/presentation/contracts.py`) in EVERY carried version's
   row, so carrying 0.2.0 beside 0.3.0 would serve 0.3.0 code bytes under a
   0.2.0 pin. Single-serving is the only honest posture until D2 closes
   (multi-serving the code row — a separate increment with its own design,
   named here as D-1). The plugin-ui slide therefore runs BELOW the
   two-release support-window floor by design (F1, issue #203; the floor is
   PRD Q3: a declared range covers at least the two most recent released
   versions), exactly as 0.2.0's own range did. The range change is a
   coordinator decision (VR-43/G-3): the PR body carries the linked ruling
   reference — OBLIGATION-ONLY (`policy_change_unruled` is deferred; no
   mechanical lane catches its absence).
   **plugin-ui-preview 0.1.1 → 0.2.0, MINOR — the range does NOT slide
   narrow:** it moves to the floor-compliant `>=0.1.1,<0.3.0` (carries 0.1.1
   + 0.2.0, the two most recent released versions). A narrow `>=0.2.0,<0.3.0`
   would drop 0.1.1 from the support window and violate the floor —
   preview's multi-serving is already its established shape, and it has no
   one-live-object wall (no code row). (Governor ruling 2026-09-29; this
   supersedes the first-draft claim that both slides were "structurally
   required" and narrow.)
2. **The lanes grammar is wire-derived, not invented.** Channel states are the
   OTDP `dtype: "logic"` alphabet `"0","1","x","z"` carried verbatim in fetch
   results; the time base is the dataset's regular axis (`coordinates.start`
   / `step` — the sample rate IS the wire's step); the trigger marker is the
   dataset's `trigger.time_relative_s`; decoder lanes bind the decode action's
   `event_log` datasets (`start_s`/`end_s`/`payload_hex`/`status` variables
   carrying `channel_ids`). §2 cites every field.
3. **Identity is lane position; colour carries NOTHING in a lanes view.** No
   new colour tokens (§A.1 unchanged). A group lane's identity is its label
   and position. Per-channel `color_role` hints are REFUSED for this kind
   (schema `if/then`) — admitting them would re-open the exact
   colour-as-identity failure the kind exists to escape.
4. **The renderer is a new sibling component, hand-drawn SVG — not an
   EngineeringPlot kind branch.** The existing component's whole architecture
   (echarts line series, slot styling, numeric `values`) is the analog
   machinery; a lane view needs uniform-height lane bands, pinned labels,
   state patterns and glitch marks — geometry a line-chart library fights.
   A pure-SVG `DigitalLanesPlot` gives deterministic SSR (real-render arms
   without an echarts harness) and precise `<pattern>` hatches. The contract
   stays renderer-neutral (shape descriptions, not implementation); §E.2.2's
   two custom SVG paths are the in-tree precedent for leaving echarts where
   echarts fits.
5. **Edge-preserving decimation is a NORMATIVE pure function with a RED
   control that LTTB fails.** The reducer is specified and tested as a
   property: every transition in the acquired states survives to the drawn
   output (as an edge or a glitch mark); any pixel column containing more
   than one transition renders a multi-edge/glitch mark; sample-dropping
   reducers (LTTB-style) are non-conforming BY TEST — the acceptance runs an
   LTTB-shaped reducer against the same fixture and shows it RED (§6 A2.2).
6. **`channel_hints.visible` and the §E.2.5 acquisition-disclosure family are
   REUSED, not duplicated.** Hiding a lane, the hidden-marker disclosure,
   `Acquired {n} samples · plotted {m}` (with its `at {rate}` suffix — already
   in the contract) all apply to lanes unchanged; the sample rate derives from
   the wire axis step.
7. **Slices 1→3: grammar+validator → renderer+preview wire → decoder lanes.**
   The standard bumps ONCE (slice 1 carries the complete grammar including
   decoder-lane declarations, so no second plugin-ui bump ever results from
   this issue); the renderer lands in two reviewable slices. Between slice 1
   and slice 2 the renderer honestly refuses the kind (a visible
   unsupported-kind note — the §E.2.3 >2-units refusal precedent: the manifest
   admits, the renderer refuses visibly, never silently).

---

## 1. Mechanism

### 1.1 The plugin-ui 0.3.0 manifest grammar (`$defs/plot`)

Copy `standards/plugin-ui/0.2.0/` → `standards/plugin-ui/0.3.0/` (copy, never
move; the four schemas + README + a hand-committed train
`validation-report.md`; corpus rows cite the 0.2.0 paths as `source`). Edit
the copy's `ui-manifest.schema.json` `$defs/plot` to:

- `kind` enum: `["time_series", "waveform", "digital_lanes"]`
- `contract_version` const, `$id`, `title`: `0.3.0` (the version sweep)
- per-kind constraints via `allOf`/`if-then` on `kind`:
  - `digital_lanes`: `y` `maxItems: 64` (analog kinds keep 16 — unchanged);
    `channel_hints` `maxItems: 64` with items carrying `visible` ONLY
    (`color_role` refused: `not: {required: ["color_role"]}`); MAY declare
    `lane_groups` and `decoder_lanes`.
  - `time_series`/`waveform`: `not: {required: ["lane_groups"]}` and
    `not: {required: ["decoder_lanes"]}` — the lanes fields cannot leak into
    the analog kinds.
- new optional `lane_groups` (maxItems 16), items
  `{id: $defs/id, label?: $defs/title, member_ids: ids (minItems 2,
  maxItems 64), radix: enum ["hex","decimal"] (default "hex" — omitted means
  hex; an explicit field overrides), default_collapsed?: boolean}` —
  `additionalProperties: false` throughout, per the schema's house style.
- new optional `decoder_lanes` (maxItems 8), items
  `{id, label?, decoder: string 1..64, settings?: object (free-form,
  disclosed verbatim), source_channel_ids: ids (minItems 1, maxItems 4),
  binding_id: $defs/id}` — `binding_id` names a manifest binding whose target
  is the decode action's `event_log` dataset target.
- `y` stays `uniqueItems: true` (ids unique on the wire — §E.2's existing
  discipline); `x` stays required (see §1.3 for the x-derivation rule).

**Cap provenance, stated for the governor (fork F1):** OTDP's descriptor
`channels` array carries NO `maxItems` (verified,
`otdp-device-descriptor.schema.json` — unbounded), so the ceiling cites no
upstream number; 64 is justified on presentation grounds — it admits the
issue's 32-channel case with headroom to pro-grade 64-channel instruments,
and unlike the analog 16 (forced by the 8×2 style-pair identity math), a
lanes ceiling is a declaration bound, not an identity bound. Alternative
calls (32 tight / 96 / 128) are recorded as fork F1.

### 1.2 The validator semantics (`src/benchweave/presentation/contracts.py`)

`_plot_findings` (line 469 on the pre-train tree) gains a `digital_lanes`
branch beside the `time_series` receipt-time row, reusing the existing
finding codes exactly:

- `invalid_plot` — "Plot axes are incompatible" family: the bound target's
  kind must be `dataset` (a streamed scalar observation cannot serve a
  capture view); every `y` variable must be `type: "string"` (the wire's
  logic states), `shape: "vector"`; `x` must be `type` `number`/`integer`,
  `shape: "vector"`, `unit: "s"`; `x` must not appear in `y` (existing rule,
  reused verbatim).
- `unresolved_reference` — a `lane_groups.member_id` outside this plot's `y`;
  a `decoder_lanes.source_channel_id` outside `y`; a `decoder_lanes.binding_id`
  that is not a manifest binding whose target kind is `dataset`.
- `invalid_plot` — a group with fewer than 2 member ids; a `y` id claimed by
  more than one group (a channel is its own lane OR in exactly one collapsed
  group lane).
- `invalid_document` — duplicate identifiers across `y` ∪ group ids ∪ decoder
  lane ids (the `_unique_rows` discipline).

No new finding code is introduced — the issue's "diagnostics follow existing
codes" is satisfied by construction: schema-level refusals (the 64-cap, the
kind enum, the per-kind shape rules) surface as `invalid_document` through
`_schema_findings`, exactly as the 16-cap does today; the semantic refusals
above carry `invalid_plot`/`unresolved_reference`.

The corpus-owned code row carries **THREE** version-literal sites (amended
2026-09-29 per the governor ruling; the first draft said one): the
path-shaped `SCHEMA_ROOT` literal at line 20, and the two bare
`contract_version` consts at lines 247 and 358. The sweep moves ALL THREE
0.2.0 → 0.3.0 — a one-site move would leave the consts refusing 0.3.0
documents and the A1.1 vectors go red on the validator's own const checks.
The zero-literal register's row for this file
(`scripts/standards/count_version_literals.py`, `REGISTER` —
scope → path → (reason, `expected_sites`, `expected_values`)) is edited
in-arc with `expected_sites` staying **3** (three sites move, count
unchanged) — the visible editorial diff the zero gate requires. The row
carries no value pin because the copy is digest-pinned whole against its
SDK twin (`tests/sdk/test_presentation_packaging.py`).

### 1.3 The x variable and the time base (wire-first, no invention)

The fetch result's time base is the dataset's regular AXIS
(`axes[0].coordinates = {kind: "regular", start, step}`), not a variable. The
binding catalogue's author-declared `x` variable (number, s, vector) is
EXACTLY derived from that axis (t_i = start + i·step — pure arithmetic, not
fabrication), and this derivation is stated in the plugin-ui 0.3.0 README:
the catalogue's `x` row for a digital capture names the regular time axis.
Sample index mode is the same arithmetic with the index shown; the trigger
marker's position is the dataset's `trigger.time_relative_s` (null ⇒ no
marker renders and no position is fabricated). The renderer contract rows
(§1.5) require the disclosure of the axis mode via the host-supplied axis
label and the sample rate via the §E.2.5 `at {rate}` suffix
(rate = 1/step).

### 1.4 The plugin-ui-preview 0.2.0 wire

Copy `standards/plugin-ui-preview/0.1.1/` → `0.2.0/`; both schema files gain:

- `plot_view.kind` enum + `"digital_lanes"`; `channels.maxItems` per-kind
  (64 for `digital_lanes`, 16 otherwise — the same `if/then` shape);
- `plot_view.lane_groups` / `plot_view.decoder_lanes` mirroring §1.1's
  structures (the preview wire mirrors manifest structure; it carries no
  capture data today and gains none — see below);
- the wire's `channel` keeps `visible`; `color_role` is refused for lanes-kind
  views (schema `if/then`).

Preview data honesty (the standing discipline,
`ui/src/preview/PreviewPlots.tsx`: "one simulated value per observation
target per scenario — not observation history"): a lanes view renders its
DECLARED STRUCTURE (lane labels, groups, decoder lanes) with a deterministic
synthetic state pattern exercising all four wire states, adjacent to a
standing disclosure line naming the simulation — the mode-banner posture
(everything in preview is labelled simulation) extended to lane activity.
No observation-history laundering.

### 1.5 The renderer-neutral contract rows (docs/internal/ui-contract.md)

**§E.1 grows 10 → 11 rows** — new component row `digital-lanes`:

| Component | Root element | Required attributes | Required roles | Required class hooks | Required text | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `digital-lanes` | `figure` | `role=img ~ aria-label ~ aria-describedby ~ data-bw-lane ~ data-bw-lane-kind ~ data-bw-state ~ data-bw-glitch ~ data-bw-trigger ~ data-bw-cursor ~ data-hidden` | `img` | `bw-lanes ~ bw-lanes__canvas ~ bw-lanes__lane ~ bw-lanes__label ~ bw-lanes__group ~ bw-lanes__glitch ~ bw-plot__acquisition` | `hidden ~ Acquired 1000 samples · plotted 12 at 1 MHz` | Lane identity is position: uniform lane height, labels pinned left, always visible. `data-bw-lane` is the lane's declared index; `data-bw-lane-kind` is `channel` \| `group` \| `decoder`; state segments carry `data-bw-state` (`0`/`1`/`x`/`z`); multi-edge columns carry `data-bw-glitch`; the trigger marker `data-bw-trigger` renders only from a non-null trigger time. |

**New §E.4 Digital lanes (`digital-lanes` sub-rows)** — six rule tables
(pre-committed row counts; the L1/L2 pins parse these):

- **§E.4.1 Lane layout** (4 rows): uniform lane height across the plot; the
  label column pinned left and always visible; hosts may reorder or hide
  lanes (hiding disclosed via `data-hidden` + the hidden marker text + the
  "(hidden by presentation preference)" aria-label — the engineering-plot
  row's wording, reused); a hidden lane's band renders collapsed with its
  label retained.
- **§E.4.2 State rendering** (4 rows): `1` high level / `0` low level within
  the lane band; `x` renders a HATCH fill (a diagonal cross-hatch pattern,
  described shape-neutral); `z` renders a MID-LEVEL line (half the band
  height, distinct from both levels and from the hatch). The four states are
  mutually discriminable without colour (the §E.2.2 monochrome-reproduction
  discipline applied to states).
- **§E.4.3 Groups and buses** (4 rows): a declared group may render collapsed
  as ONE bus lane; the bus value renders in the group's radix — hex default
  (width = the group's bit width in nibbles, zero-padded), decimal opt-in;
  member order is DECLARATION ORDER with the first declared member the LSB
  (pinned — bus values are a pure function of (member states, member order));
  a bus lane's identity is its label and position — colour carries nothing.
- **§E.4.4 Edge-preserving decimation** (3 rows, NORMATIVE): reduction keeps
  EVERY transition — a drawn column always contains every state change of the
  acquired states it covers, as an edge or a glitch mark; any column covering
  more than one transition renders a multi-edge/glitch mark
  (`data-bw-glitch`); sample-dropping reduction (LTTB-style point selection)
  is NON-CONFORMING for this kind.
- **§E.4.5 Time axis** (4 rows): the axis renders the host-supplied label and
  unit (sample-index or seconds mode is the host's choice, disclosed BY the
  label); the sample rate discloses via §E.2.5's `at {rate}` suffix (rate =
  1/axis step); the trigger marker renders from a non-null trigger time, at
  its time, labelled `trigger`; ≥2 cursors are supported with a Δt readout —
  `Δt = {value} {unit}`, the value = |x_b − x_a| in the view's axis mode
  (presentation-only in this increment: cursor positions are host-supplied;
  the interactive drag model is deferred, D-3).
- **§E.4.6 Decoder lanes** (4 rows): a decoder lane renders beneath its
  source channel lane(s) as annotation spans — each span's x-extent is the
  event's [start, end); the span carries the payload text in the declared
  radix; the lane's disclosure line names the decoder and its settings
  verbatim (`{decoder} · {settings}` — e.g. the canonical fixture's
  `UART-REF · 115200 8N1`); decoder annotations never render without their
  source lane (an event whose source channel is hidden waits, it does not
  orphan).

**§E.2 is untouched** (analog identity unchanged); `docs/internal/
ui-styleguide.md:181`'s deferral sentence updates (digital traces now in the
catalogue; spectrum, sweeps, polar/Smith remain deferred) and gains the
implementation guidance for the SVG lane renderer.

### 1.6 The reference renderer

`ui/src/components/plots/DigitalLanesPlot.tsx` (new) + CSS + stories +
`DigitalLanes.render.test.tsx` (real-render arms) + a pure
`ui/src/components/plots/lane-reduction.ts` (the §E.4.4 reducer as a tested
pure function, consumed by the component). Props mirror the engineering-plot
host-knowledge seam: `{title, x, lanes: Lane[], groups?, decoderLanes?,
triggerTime?, cursors?, hints?}` where `Lane = {id, label, states: readonly
("0"|"1"|"x"|"z")[], axis: {start, step}}`. The unsupported-kind interim
(slice 1 → 2): `PreviewPlots`/compositions render the visible
unsupported-kind note (`bw-plot__refusal`, `role="status"`) for
`digital_lanes` — honest refusal, never a silent blank.

---

## 2. Root cause and the wire evidence (why 16, and what the wire carries)

The defect is a ceiling mismatch plus an identity-model mismatch, both
verified:

1. `$defs/plot.properties.y.maxItems: 16` and `channel_hints.maxItems: 16`
   (`ui-manifest.schema.json:32`) cap any multi-channel view at 16; the
   preview wire mirrors it (`preview-document.schema.json` channels
   `maxItems: 16`). A 32-channel capture is unrepresentable at the schema
   level — refusal before any renderer question.
2. The 16 ceiling is not arbitrary for the analog kinds — it is the identity
   budget: §E.2.1's slots give 16 distinct (colour, dash) pairs from
   8 series tokens × 2 dashes, and the contract states the 17th id "would
   collide with slot 8's pair". Raising y's cap on `time_series` (the
   rejected alternative) would break that math — colour identity saturates;
   the issue's rejection of that alternative stands.
3. The wire already carries the lanes model — every element of the wanted
   contract traces to a field (all citations from
   `standards/otdp/0.2.2/examples/class-action-vectors.json`,
   `logic_analyser-fetch` / `logic_analyser-decode` vectors, and
   `otdp-measurement.schema.json`):
   - states: fetch variables carry `dtype: "logic"` (schema enum member) with
     `values: ["0","1","x","z"]` — the four-state alphabet IS the wire;
   - sample rate: `axes[0].coordinates = {kind: "regular", start: 0,
     step: 1e-06}`;
   - channel identity: each variable's `channel_ids` names the descriptor's
     channel (`role: "digital_input"`, label carried on the channel);
   - trigger: the dataset's `trigger.time_relative_s` (nullable);
   - binary form: the artifact encoding enum includes `logic_u8` (the
     large-capture form; this increment renders the inline values form —
     artifact-referenced digital captures are D-4);
   - decoders: the decode action returns a `kind: "event_log"` dataset with
     `start_s`/`end_s` (`dtype: float64`), `payload_hex` (`string`),
     `status`, each variable carrying `channel_ids` — annotation lanes are a
     projection of exactly these fields, nothing invented.

## 3. Slice plan

One standards train; serialized slices; each slice one RED→GREEN arc per
commit, full battery before push; the SDK rides per the two-repo discipline
(submodule commit → push → SDK PR stacked, then the pointer commit).

- **Slice 1 — the grammar and the validator (plugin-ui 0.3.0).** The schema
  grammar complete (lanes + groups + decoder declarations — §1.1), the
  contracts.py semantics (§1.2), the range slide + migration note + policy
  rows (§8), the register row edit, the corpus copy + repin + export, the
  version sweep of in-tree artifacts (the presentation test fixtures and the
  SDK vendored tree), the SDK sync + lock + SDK PR + pointer. RED-first:
  schema vectors + semantic vectors (§6 A1). The renderer honestly refuses
  the kind (the unsupported-kind note, tested).
- **Slice 2 — the renderer and the preview wire (plugin-ui-preview 0.2.0).**
  The wire grammar (§1.4) + preview_models/fixture schema; the contract rows
  §E.4.1–§E.4.5 + §E.1's row (with L1/L2 pins in the same change —
  obligation 12); `DigitalLanesPlot` + `lane-reduction.ts` + real-render
  arms + stories; the preview synthesis + disclosure line; preview_assets
  rebuild (renderer-freshness) + SDK PR + pointer.
- **Slice 3 — decoder lanes (rendering + disclosure).** §E.4.6's rows + pins;
  the decoder-lane renderer arms (annotation spans, payload radix, disclosure
  line, source-hidden waiting behaviour); preview decoder fixtures;
  preview_assets + SDK PR + pointer. (The GRAMMAR admitted decoders in
  slice 1 — this slice renders them; if the event_log wire proves unable to
  drive annotations, slice 3 dies alone and the deferral is recorded — the
  kill direction is in §6.)

The issue closes after slice 3 merges. Deferrals are §11.

## 4. Precedent

- **The incremental standards train:** issues #62/#64/#66 (design record
  first, RED-first through endpoint pins, governor MINOR-CONFIRMED on
  reproduced evidence, copy-never-move) — this is the #62 shape applied to a
  new kind: the schema vectors reproduce both refusal deltas (0.2.0 refuses
  the new kind; 0.3.0 admits it).
- **The UI-contract slicing and acceptance discipline:** the #242 and #243
  design records (`.claude/deep-review/2026-09-28-issue242-ui-contract-design.md`,
  `2026-09-29-issue243-ui-followon-design.md`) — definition rows with
  pre-committed counts, L1/L2 pins landing with the rows, real-render arms
  for every draw claim (the #243 incident's lesson, now the G-render gate).
- **The honest-refusal interim:** §E.2.3's >2-units refusal note — a manifest
  the renderer cannot serve draws a visible refusal, never a silent blank.
- **The pure-SVG escape from the chart library:** §E.2.2's two custom SVG
  paths — the reference binding leaves echarts where echarts lacks the shape.

## 5. Invariant and cross-surface impacts

No CTL/STO/REG invariant is touched (no control, state, or registry surface).
CON-side:

- **CON-7** (repin is the only pin writer): the new version's rows move via
  `edit → repin → export`; 0.2.0's rows verify-frozen (the derived corpus-dir
  guard walks the new `source` edges).
- **CON-8**: unchanged — plugin-ui/plugin-ui-preview are not identity-block
  standards; no identity motion.
- **CON-12/CON-14**: the compatibility matrix renders the new retained rows
  from the policy block (per-version row + range membership; the migration
  note's pointer rides the policy row); `matrix --check` stays
  committed-state pure.
- **CON-4**: `make check-sdk-standards` carries the sync (main standards ↔
  SDK lock ↔ vendored tree, served-set + policy-mirror lanes).

Obligations walked (`docs/internal/drift-and-obligations.md`, origin/main):
6 (corpus rows + repin + the dev-head clause N/A — no head), 7 (SDK pointer
existence-push BEFORE the pointer commit, three times — once per renderer
slice; renderer freshness each time), 12 (ui-contract rows + BOTH pin
suites + the preview wire conformance from the Python emitter AND the TS
decoder + the device-developer-guide presentation section gains the lanes
authoring rows), 18 (the new version dirs register their motion mechanisms;
the range/manifest move by their own mechanisms), 20 (the register row edit
— the visible editorial diff), 21 (the policy block motion: range + the two
migration-note rows, one arc). Obligation 13 does NOT apply (plugin-ui's
validation reports are train records, hand-committed — the 0.3.0 report is
new train evidence, not a family regeneration). Obligation 19 not touched.

CI cost: no new jobs; the `gates` battery grows the vector/semantic tests
(~seconds), `ui` grows the lanes suites (~seconds); `package`'s
check-sdk-standards and the clean-venv control re-run mechanically. The
timing lane is untouched.

## 6. Pre-committed acceptance rules

Written before any measurement. Counts read from junitxml attributes or exit
codes, never a filtered summary. Every RED arm is demonstrated in the PR body
(revert the production change, keep the test, show red, restore, show green).

### Slice 1 (grammar + validator)

- **A1.1 Schema vectors (RED-first).** 12 valid vectors (minimal 2-lane; the
  64-lane boundary exactly; groups hex/decimal; a decoder lane; hints
  visible-only; x-unit seconds) validate against 0.3.0, and the
  pre-train tree refuses the digital_lanes vectors with a kind-enum
  `invalid_document` (the reproduced refusal delta — the #62 governor
  evidence shape). ≥10 invalid vectors each name their code: 65 lanes
  (schema `invalid_document`), analog plot carrying `lane_groups`
  (`invalid_document`), a lanes plot carrying a `color_role` hint
  (`invalid_document`), non-string y type (`invalid_plot`), scalar y shape
  (`invalid_plot`), x∈y (`invalid_plot`), observation-kind binding
  (`invalid_plot`), group member outside y (`unresolved_reference`),
  decoder source outside y (`unresolved_reference`), decoder binding absent
  or non-dataset (`unresolved_reference`), 1-member group (`invalid_plot`),
  duplicate ids (`invalid_document`).
- **A1.2 Semantic RED control.** With the contracts.py branch reverted, the
  semantic vectors (non-string type, group-outside-y, decoder-unresolved)
  pass wrongly — RED demonstrated; with the branch, they refuse — GREEN.
- **A1.3 Copy-never-move.** 0.2.0's corpus rows and directory bytes are
  unchanged (the frozen-row tests + `repin` verify pass); the derived
  corpus-dir guard walks the new `source` edges.
- **A1.4 Governance gates green.** train-window (both standards' last
  version-dir creations — plugin-ui 2026-09-19, plugin-ui-preview
  2026-09-21 — are >24h before any landing); SM-5 with BOTH migration-note
  rows present (repo-relative, root-resolving pointers on the retained
  versions; RED arm demonstrated in the PR body for each row: removing the
  plugin-ui row fires `migration_note_missing:`, removing the preview row
  fires it likewise); zero-literal gate green over the edited register row
  (three sites moved, `expected_sites` 3); `standards check` + export + `make
  check-sdk-standards` green (the served set is exactly {0.3.0} for plugin-ui
  and {0.1.1, 0.2.0} for plugin-ui-preview after the range motions — the
  drift lanes refuse a straggler).
- **Kill directions.** If a valid vector also validates under the pre-train
  semantics, the vectors are underpowered — widen them, do not proceed. If
  0.2.0's pins cannot stay frozen while the code row moves, STOP: that is the
  D2 wall and the range slide is the only sanctioned crossing (§8).

### Slice 2 (renderer + preview wire)

- **A2.1 REAL-render arms (G-render; the #243 lesson).** SSR against the real
  component, asserting on the rendered SVG/DOM: lane count == declared
  (hidden lanes collapsed-but-labelled); every lane label present; the four
  states discriminable by STRUCTURE (the x hatch and z mid-level are distinct
  geometries, not colour variants — asserted by distinct SVG pattern/element
  presence); a group lane renders its bus value in the declared radix with
  the pinned LSB order (fixture: members [a,b,c] states [1,0,1] → hex `0x5`);
  the trigger marker present iff triggerTime non-null; cursors at samples 3
  and 10 with step 1e-6 render `Δt = 7 µs` (exact arithmetic, pre-committed
  fixture numbers); `Acquired 1000 samples · plotted 12 at 1 MHz` renders
  outside the canvas.
- **A2.2 The decimation property (the normative rule).** A property test over
  `lane-reduction.ts`: for ≥200 random state arrays (lengths 2..5000, all
  four states) and reduction widths 1..64 — every input transition index
  survives in the output (as an edge boundary or a glitch-marked column);
  every output column covering >1 transition carries the glitch mark.
  **RED control:** an LTTB-shaped sample-dropping reducer run against the
  SAME test fails (a dropped transition is detected) — this control is
  committed as a test fixture proving the property has teeth, and its
  failure output pasted in the PR body. **Permutation null:** for 50
  randomly-permuted copies of one adversarial fixture (0101… at sub-column
  spacing — every column multi-edge), the reducer marks every column
  glitch and preserves every transition; the permuted runs' survive-counts
  equal the unpermuted run's (the property is ordering-independent, so a
  fixture-specific pass cannot masquerade as mechanism).
- **A2.3 Contract pins + freshness.** L1 fixture pins (the §E.4 rows cannot
  vanish) + L2 rendered-attribute pins for the §E.1 row, landing with the
  rows (obligation 12); renderer freshness — `build:preview` produces the
  committed `preview_assets` diff (zero-diff gate).
- **A2.4 Preview conformance both sides.** The Python emitter and the TS
  decoder both validate against the 0.2.0 wire schema (the fixture.schema
  scenarios carry lanes declarations); the disclosure line renders.
- **Kill directions.** If the four states cannot be made structurally
  discriminable in machine-checkable SVG (hatch vs mid-level collapse to the
  same geometry), the DRAW claims are unmeasurable — fix the markers before
  shipping, never weaken the claim to colour. If the property test cannot
  distinguish the LTTB control, the test is underpowered — strengthen before
  proceeding.

### Slice 3 (decoder lanes)

- **A3.1 REAL-render arms.** Annotation spans render beneath their source
  lane with x-extents = [start,end) in the view's axis mode (fixture:
  events [0, 0.0001] and [0.001, 0.0011] at step 1e-6 — span boundaries
  asserted at the exact sample indices 0, 100, 1000, 1100); payload text in
  the declared radix; the disclosure line `UART-REF · 115200 8N1` renders;
  an event whose source lane is hidden does NOT render and does NOT orphan
  onto a neighbour (asserted by absence).
- **A3.2 Semantic RED.** The slice-1 decoder vectors re-run green (they
  landed in slice 1); the source-hidden waiting behaviour is the new RED arm
  (revert the guard, the orphan renders, RED; restore, GREEN).
- **Kill direction.** If the event_log wire cannot drive the annotations
  (e.g., channel binding unresolvable to a lane), slice 3 DIES ALONE: record
  the wire gap as an honest negative, keep slices 1–2, file the wire gap
  against the OTDP lane. Do not invent a side channel.

## 7. Top risks and falsifiers

1. **The range slide strands 0.2.0-pinned plugins** (out-of-carried ⇒ the
   SDK's per-pin resolution refuses `version_not_served:`-family; at the
   gateway, non-conforming loads need operator acknowledgement). Falsifier /
   mitigation: the in-tree corpus carries NO plugin-authored ui-manifests
   (verified — only test fixtures), so the sweep is mechanical; the
   consequence is disclosed in the migration note, and the out-of-tree
   population is the ADC-control shape (re-stamp, as #203's slice-1 control
   proved). If a real 0.2.0-pinned plugin surfaces, that is the D2-closure
   trigger, not a reason to widen the range without closing D2.
2. **echarts-free rendering diverges from the plot family's look.** The
   contract is renderer-neutral; the risk is reviewer churn, not conformance.
   Falsifier: the L2 pins — if the rows pin attributes the SVG renderer
   cannot carry, the ROWS are wrong, not the renderer choice.
3. **The 64-cap guess is wrong** (too small for a future 128-channel class).
   Falsifier: the first real >64-channel descriptor — a cap change is then a
   PATCH-easy schema edit (widening an admission ceiling is additive errata
   UNLESS renderer behaviour is re-derived — the decimation rule is
   width-independent by construction, so the edit stays PATCH-class).
4. **Slice-1-lands-but-slice-2-slips** leaves an admitted-but-unrendered kind
   live in the corpus. Mitigated by the honest refusal note (tested in
   slice 1); if slice 2 does not follow within the train, the migration note
   and README disclose the interim state explicitly.
5. **SM-5/train-window surprises.** Both are mechanically checked at push
   (A1.4); the 24h floors are clear by 8+ days on the evidence (release
   dates in the manifest). A mid-train rival bump would force the re-copy
   rule (GOVERNANCE bump minimization) — the pre-flight check re-runs at
   each slice's branch point.

## 8. Standards-movement statement and the bump-class case (for the governor)

**Bytes moved, by file:** `standards/plugin-ui/0.3.0/` (all four schemas —
kind enum, per-kind caps/shape rules, `lane_groups`, `decoder_lanes`,
version consts — + README + a new hand-committed train
`validation-report.md`); `standards/plugin-ui-preview/0.2.0/` (both schemas
+ the train record); `standards/standards-manifest.json` (two active entries,
two dependency-policy range motions `>=0.2.0,<0.3.0`→`>=0.3.0,<0.4.0`
(plugin-ui, narrow) and `>=0.1.0,<0.2.0`→`>=0.1.1,<0.3.0`
(plugin-ui-preview, floor-compliant — 0.1.1 stays carried; 0.1.0 drops as
the older-than-floor release), two migration-note rows with repo-relative,
root-resolving pointers on the retained versions); `standards/corpus-manifest.json` (new rows via repin; 0.2.0/0.1.1
rows frozen); `src/benchweave/presentation/contracts.py` (the semantic
branch + all THREE version-literal sites — §1.2); the register row edit; the
migration-note files themselves; the in-tree fixture sweep; the SDK vendored
tree + lock + preview_assets (mechanically, per slice).

**Bump class:** MINOR for both standards. The case: a new enum member plus
new per-kind required-consumer behaviour (normative decimation, lane layout)
is new normative capability — beyond the PATCH class's "new optional field,
nothing removed or retyped" (a 0.3.0 document is not interpretable by a
0.2.0-pinned consumer, which is the tolerance line: serving retained
versions EXACTLY is the only tolerance, R-1). Nothing is removed or retyped;
no previously-valid 0.2.0 document becomes invalid under its own frozen
schema — MINOR, not MAJOR. The governor confirms at review; the reproduced
refusal deltas (A1.1) are the evidence, the #62 MINOR-CONFIRMED shape.

**Range motion (VR-43 coordinator decision; the ruling reference rides the
PR body — OBLIGATION-ONLY, `policy_change_unruled` is deferred):** plugin-ui
slides narrow `>=0.2.0,<0.3.0`→`>=0.3.0,<0.4.0` — FORCED by policy + the
one-live-object bundle honesty + the manifest's F1/D2 note (headline 1's
amended mechanism), below the two-release support-window floor by design;
widening would demand closing D2 (multi-serving the live code row) — a
separate increment with its own design, named here as D-1. plugin-ui-preview
does NOT slide narrow: `>=0.1.0,<0.2.0`→`>=0.1.1,<0.3.0`, the floor-compliant
motion (PRD Q3's support-window floor: a declared range covers at least the
two most recent released versions — 0.1.1 and 0.2.0; a narrow
`>=0.2.0,<0.3.0` would drop 0.1.1 and violate the floor). Preview's
multi-serving is its established shape and it has no code row to multi-serve.
(Governor ruling 2026-09-29 — the first draft's "slide narrow, both
standards, structurally required" was wrong for preview.)

**Dev head:** NOT opened — DIRECT BUMP, confirmed by the governor ruling
(2026-09-29): the devstage default is `-dev` accumulation, but this train's
SDK sync (vendored tree + lock + preview_assets) requires RELEASED bytes at
slice 1 — the roll-up trigger fires with slice 1, so a head would protect
zero edits and defer the release past the need. Build exactly as dispatched.

**Promotion records:** `promotion-records.json` records NONE for this train —
deliberately: the structure is dev-head-scoped (it records promotions from a
dev head to released bytes), and a direct bump records none — a decision, not
an oversight. These are direct bumps, not dev promotions; plugin-ui 0.2.0's
own bump predates the mechanism (grandfathered by SM-5's self-anchor; its
2026-09-19 release precedes `migration_notes.py`'s arrival).

**Cross-constraints:** `standards/cross-constraints.json` gains NO row for
either bump — its own honest-absence note names plugin-ui and
plugin-ui-preview among the deliberate "no evidence is recorded for them
(honest negatives, first-class)" rows. The absence continues to hold; add a
row only with its citation.

**Migration notes (SM-5 MUST — grandfathering ENDED; both new bumps are
judged):** one per standard, from-predecessor, authored at the bump: the new
kind and its authoring grammar, the per-kind caps, the visible-only hints,
the range consequence for 0.2.0 pins (plugin-ui: re-stamp) and for 0.1.1
(preview: REMAINS served) / 0.1.0 (drops out of the window) pins, and the
interim renderer-refusal state.

## 9. Owner forks

| # | Fork | Recommendation | The alternative |
| --- | --- | --- | --- |
| F1 | The lane cap | **64** — admits 32-channel captures with headroom to pro-grade 64-channel instruments; a declaration bound (position-identity has no style-exhaustion math forcing it) | 32 (tight to today's hardware; a near-certain follow-up bump) or 96/128 (speculative) |
| F2 | Bus value radix default | **hex**, width = group bit-width in nibbles, zero-padded; decimal per-group opt-in (`radix: "decimal"`) — instrument convention | decimal default (unusual for logic analysers; hex is the domain default) |

Marked defensible defaults (not forks): LSB = first-declared group member
(pinned, disclosed); cursors presentation-only this increment (interactive
drag model deferred, D-3); preview lane activity is a labelled synthetic
pattern (the mode-banner honesty posture); decoder-lane cap 8 and group cap
16 (proportionate to the page caps family).

## 10. Deferral table

| # | Deferral | Reopen trigger |
| --- | --- | --- |
| D-1 | D2 unclosed: plugin-ui remains single-served; the range slides at every bump. The register's named D2 reopen trigger — "the first plugin-ui bump after the arc" — **FIRED with this bump** (the 0.3.0 motion is that first bump); D2 stays OPEN, and the reopen conditions re-record here narrower than the register's spent trigger | A real 0.2.0-pinned plugin needing carried 0.2.0 bytes, or a design that multi-serves the code row (per-version resolver objects) |
| D-2 | Interactive cursor model (drag, snap-to-edge, keyboard) | The presentation-only rows landing (slice 2) + an operator-facing consumer |
| D-3 | Artifact-referenced digital captures (`logic_u8` binary form) in the renderer | The first capture whose inline values exceed the document budget |
| D-4 | In-protocol decoder catalogues (named decoders with typed settings schemas — UART/SPI/I²C as corpus vocabulary rather than free-form `settings`) | A second consumer of decoder lanes, or a plugin authoring need beyond disclosure |
| D-5 | Spectrum / sweeps / polar-Smith plot kinds (the styleguide's remaining deferral) | Their own issues; this record's §E.4 pattern is the template |

## 11. Design-time tier call (rubric #254)

**Tier 3, by three independent rules** (the review re-derives; this is the
record's call): (1) the path rule — the diff touches `standards/` (schema
JSON files, both manifests) and any JSON Schema file; (2) the same rule's
submodule clause — the diff advances `packages/sdk` (three times, once per
renderer slice); (3) the keyword rule — see the scan. The standards-governor
mandate applies regardless of tier (any `standards/` touch).

**Step-1 keyword scan, run at design time over the assembled expected diff
text** (the two schema files that will be copied and edited — the full
current bytes of `ui-manifest.schema.json` and `preview-document.schema.json`
— plus the planned contracts.py additions and the planned contract-row text;
15,233 bytes scanned):

`threading: 0 · asyncio: 0 · subprocess: 0 · sha256: 12 · hashlib: 0 ·
migrate: 0 · recovery: 0 · protection: 0`

The twelve `sha256` hits are the copied schemas' existing field names
(`descriptor_sha256`, `settings_schema.sha256` — byte-identical copies carry
their contexts); no keyword appears in any PLANNED addition. Per-slice tier:
all three slices Tier 3 (each touches `standards/` or the submodule pointer);
slice 2 additionally carries the `ui/` Tier-2 surfaces inside its Tier-3
lane.

## 12. Finding summary (for the ledger)

1. The plugin-ui served range MUST slide narrow at every bump until D2
   closes: the version's normative bundle row lists the one live code object
   (`src/benchweave/presentation/contracts.py`) in every carried version's
   row, so carrying the predecessor beside the bump would serve the bumped
   code bytes under the predecessor's pin — single-serving is the only honest
   posture, and the F1/D2 policy note sanctions the below-floor range. (The
   earlier "edit breaks the predecessor's digest pin" mechanism was wrong:
   `contracts.py` carries no corpus-manifest row. Amended per the governor
   ruling 2026-09-29.) (proposed to the ledger)
2. SM-5's grandfathering ended for plugin-ui: any future MINOR-line motion
   (including this one) is judged and MUST carry a from-predecessor
   migration-note row in the dependency-policy block. (proposed to the
   ledger)
3. The OTDP wire already carries the full digital-lanes model — the `logic`
   dtype's four-state alphabet, the regular-axis step as sample rate,
   `trigger.time_relative_s`, and the decode action's `event_log` shape
   (start/end/payload per event with `channel_ids`) — so the lanes contract
   invents nothing. (design-record §2 is the citation home)

---

## 13. Build fold (2026-09-29, slice 1) — the ≥2-member floor and the per-kind caps

Three build-time findings from the RED runs; the record's text above stays
frozen, THIS note governs the landed contract (#243's §11a precedent):

1. **The ≥2-member floor is a SCHEMA rule, not a semantic one.** §1.2's
   semantic bullet and A1.1's "1-member group (`invalid_plot`)" contradict
   §1.1's grammar (`member_ids` `minItems: 2`): `_checked_document` fails
   closed on schema findings, so the schema refuses a one-member group with
   `invalid_document` BEFORE `_plot_findings` runs — §1.2's semantic `<2`
   check would be unreachable dead code. Resolution: the schema owns item
   counts (the channel_hints house rule: "shape, enum, booleans and item
   counts are the schema's job in the corpus"; §1.2's own taxonomy puts
   per-kind shape rules on the `invalid_document` side), the semantic `<2`
   check is NOT implemented, and A1.1's vector names `invalid_document`.
   Prose defers to the machine source — the schema keeps `minItems: 2`.
   The cross-group double-claim rule stays semantic (`invalid_plot`).
2. **Per-kind caps cannot ride a base cap.** §1.1's "per-kind constraints
   via allOf/if-then" requires the base `y`/`channel_hints` (and the
   preview wire's `channels`) to DROP their `maxItems: 16` — JSON Schema
   intersects a branch cap with a base cap instead of relaxing it, so the
   first draft's shape would have refused every 17+-lane plot. The caps
   live ONLY in the kind branches (64 for `digital_lanes`, 16 for the
   analog kinds); the A1.1 64-lane boundary vector caught this.
3. **An injected `not: {required: [variables]}` in the 0.3.0 copy's
   dataset-target clause** (absent from 0.2.0's frozen def) made every
   dataset target unsatisfiable — every vector refused at the catalogue
   before the plot walk. Removed; the 0.3.0 dataset clause is again
   byte-equivalent to 0.2.0's.

Slice-2 constraint (fold row A8, watch item): the design's bumps-ONCE
claim (headline 7) rides on slice 2 NOT needing fixture-side lanes
fields — the 0.2.0 preview dir is released with this train, so any
fixture-schema change slice 2 discovers it needs forces ANOTHER
plugin-ui-preview bump. Slice 2's lanes activity must live in fixture
DATA the existing wire admits, not new schema fields.

Slice-1 landing note: the plugin-ui-preview 0.2.0 bump (wire grammar +
range motion + migration note) rides THIS slice per the governor ruling
("the preview range … changes your S1 diff"; the S1 PR body carries both
SM-5 rows), superseding §3's slice-2 line "the wire grammar (§1.4)" — a
released version dir cannot be edited after landing, so the wire grammar
ships complete with its bump; slice 2 renders it.
