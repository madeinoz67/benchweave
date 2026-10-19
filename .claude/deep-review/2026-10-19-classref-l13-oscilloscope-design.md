# L13 — the first waveform class: `otdp.oscilloscope` class reference, the `waveform` plot widening, and the RC-L5-1 idioms answered (mockup authored)

**Date:** 19 October 2026
**Slot:** L13 of the class-reference train (parent gateway issue #463; program record
`.claude/deep-review/2026-10-14-classref-logic-analyser-design.md` §7A row L13, §8's
RC-1 sweep row; the sweep order L11 dc_psu → L12 dmm → **L13 oscilloscope** → L14
function_generator … L21 vna, verified against §7A and the workbench §8 table).
**Branch:** `feat/l13-oscilloscope-classref`, cut from `origin/feat/l11-dcpsu-classref`
`c64f3d05` (the L11 rebase resolution — the union of #498 and the classref bump; the
L11 refute fold's motions verified present on this base: the 0.3.0 cross-constraints
row is in `standards/cross-constraints.json` here).
**Worktree:** `.wt/l13-t4k9/`. Evidence baseline: the branch head `c64f3d05`; SDK
pinned at gitlink `9e0449ef` = **v0.16.0** (pyproject verified) — whose vendored
classref tree is `{0.1.0, 0.2.0}` (**0.3.0's SDK leg is OUTSTANDING** — the load-bearing
fact of §1); plugin-ui 0.4.0 active, plugin-ui-class-reference **0.3.0 active on the
branch** (range `>=0.1.0,<0.4.0`, unreleased — no SDK leg yet, per RC-L11-2's batching
into L12); OTDP 0.2.3 active; `benchweave-ui-html==0.3.0` published, 0.3.1 ruled by
L11's F2 to cut with the L12 batched promotion leg. Served set **17** of **27**
retained version directories, cross-constraints **3 rows** — each re-derived this pass
from `standards/standards-manifest.json` + `dependency_policy` + on-disk dirs, not
carried from any dispatch.
**Binding design points:** the program record D1–D14 (esp. D2 structure-not-data, D13
effective capability, D14 coverage and its §2.5 ladder); the L11 record in full
(addendum + refute fold F1–F4); the L12 record in full (its §1 four grounds for
in-window edits, its §5 F4 settlement design, its §6 shared census); the L5 record §1
(the RC-L5-1 idiom deferral, its batching rule and reopen trigger); GOVERNANCE's
bump-minimization train rule and G-5 sync-completion pacing.

## 0. Summary and design thesis

L13 authors the fourth class reference — `class-oscilloscope.json`, binding
`otdp.oscilloscope/1.0.0` — **and authors the mockup it is validated against** (there
is no `class-oscilloscope.html`; the mockup directory holds the analyser, dc_psu, and
the dmm file the L12 lane is authoring now). It is the sweep's first
**waveform-shaped** class and the slot the whole train has been pointing at: L11
deliberately refused `waveform` ("L13 oscilloscope widens again on its own evidence"),
L12's deferral table names L13 twice (the `waveform` plot kind; the five RC-L5-1
display idioms). The thesis in one line:

> The oscilloscope needs exactly **one vocabulary motion** — the family plot enum
> admits `waveform`, the kind plugin-ui 0.4.0 already defines, the renderer already
> computes kind-blindly, and the SDK already types — and **no §E.1 contract row at
> all**: every idiom the class page shows either has an existing contract home (the
> waveform canvas IS `engineering-plot` over a `waveform` plot; the capture-context
> strip IS §E.2.5) or is a named cannot-derive at the host seam (cursor/trigger
> markers), so **the wall-payment bump RC-L5-1 anticipated is not called by this
> class**.

Three grounding facts fix the scope, each verified in the worktree this pass:

1. **The OTDP class contract is capture-shaped and waveform-native.** The profile
   (`device-profile-catalog.json`, `otdp.oscilloscope/1.0.0`) requires
   `configure/arm/fetch/abort`, optionally `trigger`, over `channel_roles:
   ["analogue_input"]` — the analyser's action set minus `decode`, and `device-classes.md`
   §6 is normative: "Fetch returns **waveform datasets** with one variable per enabled
   analogue channel and explicit time axes… Trigger position is relative to the dataset
   time origin and may be unknown." The measurement model (`otdp-measurement.schema.json`)
   carries `dataset.kind: waveform`, array-dimensioned numeric variables, and a
   structural `trigger` object (`source` enum + `time_relative_s`).
2. **Every layer above the family schema already ships `waveform`.** plugin-ui 0.4.0's
   `$defs.plot.kind` is `["time_series", "waveform", "digital_lanes"]`, and the
   `waveform` arm is structurally identical to `time_series` (`kind, binding_id, x,
   y[]`, optional `channel_hints`; no group machinery). The renderer contract
   distinguishes them exactly once — the §E.2 disclosed residual: "symbols render on
   `time_series` plots only; in `waveform` plots identity is carried by colour and dash
   alone… an owner fork, not part of this contract." The ui-html compute layer
   (`packages/ui-html/src/benchweave_ui_html/plot.py`, read in full) is
   **plot-kind-blind** — `compose_plot` never reads a kind; a repo-scoped text search
   finds **zero** `waveform` occurrences under `packages/ui-html` — and the SDK's
   `preview_models.py` already types `PlotKind = Literal["time_series", "waveform",
   "digital_lanes"]`. The family's 0.3.0 `page_template.plot.kind` enum
   `["digital_lanes", "time_series"]` is the only narrow gate left.
3. **The scope was a designed-for case of the current contract, not an afterthought.**
   §E.2.6's `device-averaged` provenance row cites "the descriptor configure
   `averaging_count`, **oscilloscope profile**" — verified present in the configure
   action schema (optional integer, [1,64]). §E.2.5's acquisition disclosure
   ("Acquired {n} samples · plotted {m} at {rate}", per-trace, the M1 fold) and §E.2.6's
   `derived` provenance (derivation expression + `uncertainty unknown`) are the
   contract homes the scope's capture-context and derived-trace idioms ride.

## 1. The governance answer first: one in-window widening, priced; the fallback priced too

**Can the widening stay inside the unreleased 0.3.0 window? Yes — and that is the
recommended landing.** The L12 record's four grounds (§1 there) hold unchanged for
this slice, re-verified against GOVERNANCE text rather than re-argued:

- **The train rule is explicit.** "Queued changes to the SAME standard that share a
  train batch into a single bump… a batch's bump follows the highest change class it
  contains." L11's and L12's PRs are unmerged and unpushed (verified: `gh pr list` —
  **zero open PRs in either repo** this pass); L13 opens against the same merge window
  stacked on the L11/L12 line. The 0.3.0 copy step happened once (L11); the `waveform`
  enum member, its conditional, and `class-oscilloscope.json` join the SAME bump. "Never
  stack a bump on an unmerged bump" governs a second version directory — L13 creates
  none. The batch's highest class remains MINOR (the L11 plot widening; the waveform
  member is another additive arm of the same widening).
- **G-5 pacing governs new version directories, not in-window edits — and its evidence
  is on the record.** "The commit adding a new version directory of standard S must
  arrive on a tree whose SDK lock already carries S's previous released version." The
  branch's gitlink is `9e0449ef` = SDK v0.16.0, and v0.16.0's vendored classref tree is
  `{0.1.0, 0.2.0}` (directory listing, this pass) — **the 0.3.0 SDK leg is
  outstanding**, so a NEW directory (0.3.1 or 0.4.0) is G-5-BLOCKED today regardless of
  change class. The only legal corpus landing before that leg completes is the batch.
  This is the strongest form of the in-window answer: not merely cheaper, but the only
  motion governance admits on this tree.
- **Copy-never-move protects retained versions, and 0.3.0 is not one yet.** 0.2.0/0.1.0
  bytes are untouched (A7 asserts zero frozen-row rewrites). 0.3.0's rows exist only on
  the unmerged branch; no consumer can pin it until the batch merges (R-2 multi-version
  serving resolves from the retained corpus — main still serves classref 0.2.0,
  verified from the main checkout's manifest).
- **The L11/L12 rulings walked this path.** RC-L11-2 batched the SDK leg; F2 cut
  ui-html 0.3.1 with it; F3 added the 0.3.0 cross-constraints row beside 0.2.0's; L12
  §1 closed its own window question the same way and then said "after the batch merges,
  0.3.0 is frozen… and L13's class lands in the next bump under its own train rules."
  That sentence assumed L13 designs after the merge; the actual dispatch runs L13's
  design concurrent with L12's build (both lanes live this session), which is exactly
  why the in-window answer is worth having now — the window is still open, and the L12
  batched SDK widening (not yet built) can absorb the `waveform` expander arm at zero
  marginal version cost.

**The fallback, priced honestly (the post-merge world).** If the L12 batch merges
before L13's corpus motion lands, the in-window option is gone and the landing becomes:
`class-oscilloscope.json` alone = additive errata = **PATCH 0.3.1**; the `waveform`
widening = **MINOR 0.4.0** by the family's own precedent (the L5 layout widening and
the L11 plot widening were both MINOR) — two version events, two SDK-leg waits, where
one batched bump sufficed. G-5 then gates BOTH on 0.3.0's SDK leg — which the L12
batch performs — so the fallback is legal but strictly more expensive. The design's
standing recommendation: **land L13's corpus on the stacked branch before the batch's
promotion leg** (§7). Nothing in this record licenses any motion touching
0.2.0/0.1.0 bytes, any new family version, or any edit to the committed
`class-logic_analyser.json`/`class-dc_psu.json` beyond none-at-all (A5). One
disclosed interaction: L12's §5 settlement (making `series` required on `time_series`)
is designed but NOT committed on this base — the two schema edits (series-required;
waveform member) land as the batch's accumulated 0.3.0 edits, order-independent by
construction (different conditional branches).

**The OTDP `oscilloscope` example, and how it relates.**
`standards/otdp/0.2.3/examples/class-oscilloscope.json` is the canonical expansion
fixture (RC-L11-4's ruling, third application): 2 `analogue_input` channels
(`ch1`/`ch2`), each `quantities: [voltage]`; all five actions declared with empty
`input_constraints`; contracts pinning the catalog and the measurement schema. OTDP
answers what a scope must admit; this family answers how the class presents. Like dmm
(and unlike dc_psu), **no derived fixture is needed** — the mockup is authored to the
example's own shape (2 channels × 1 quantity = 2 traces; all five actions declared =
3 run buttons), so the A3 census resolves over the committed example directly.

## 2. The mockup (authored — the spec, per the dispatch's finding that none exists)

`docs/internal/ui-styleguide-mockups/class-oscilloscope.html` is authored to the
dc_psu/dmm convention — one composition, two `data-theme` sections (light/dark) over
the shipped token set, self-contained, ~13 KB, invented identifiers only (`OSC-01`;
public-repo discipline paid at authoring). The two L11 lessons are built in from birth
(no hook-pass debt, no placement debt), plus one extension this class adds to the
convention:

- **§E.1 component hooks from birth**: `bw-plot` on the capture plot `section`
  (`<section class="plot bw-plot">` — the dc_psu mockup's own placement, verified),
  `bw-button` on each run `button` (the analyser mockup's convention — the scope is
  the first sweep class with rendered run controls), `bw-alert-bubble` on the alert
  `aside`. Hooks on their root elements, keying the consistency check on contract
  surfaces.
- **The F1 placement contract from birth**: every hook on its root tag,
  container-scoped hooks inside their containers (`bw-plot` only in the capture
  region, `bw-button` only in the run panel), and — the extension — **the idiom
  surfaces that are NOT contract surfaces carry NO `bw-` hook at all**: the trigger
  marker (a vertical dashed line at the trigger time with its readout chip) and the
  cursor pair with the Δ readout are painted as styleguide idioms over
  host-knowledge, exactly as the dc_psu staged-control card carried no hook (a
  cannot-derive surface must never present as a reading — here generalized to: a
  non-contract idiom must never present as a contract component).

**What an oscilloscope's class page shows, and why** (each element traced to the
class's nature — an acquisition instrument whose observable is the captured waveform
itself):

| element | disposition |
|---|---|
| title row + `Controls` button | page chrome/navigation — host territory, as every class |
| recessed capture panel `bw-plot`: graticule canvas, two analog traces (ch1/ch2 voltage), a visible legend ("Traces", slot colours, `data-line` forms), and the acquisition line | **derives**: one `engineering-plot` of kind `waveform` over the capture slot; one trace per (channel, declared quantity) variable of the fetch dataset (2 × 1); the acquisition line IS §E.2.5's normative disclosure, rendered inside the plot family (`Acquired {n} samples · plotted {m} at {rate}` — the capture-context strip, landed by use) |
| trace slot colours/dashes | §E.2's pure function of the declared id set (bytewise sort; ch1 → series-1, ch2 → series-2; the symbols-in-waveform residual stays the disclosed owner fork — the mockup paints colour+dash identity only, no marker symbols) |
| trigger marker: vertical line + readout chip (`TRIG · edge · −2.4 ms`) | **cannot_derive** `trigger-marker` — the dataset carries trigger structurally, but the preview wire (plugin-ui `$defs/plot`) has no trigger field; host-knowledge seam (§E.2.6's precedent: "the preview wire carries no provenance field and no standards byte moves") |
| cursor pair + Δ readout chip (`Δt 40.0 µs · Δv 1.2 V`) | **cannot_derive** `cursor-readout` — cursors are operator runtime state; never on the wire |
| raised run panel: `Arm` (primary `bw-button`), `Trigger` (secondary `bw-button`), `Abort` (secondary `bw-button`) | **derives**: the run controls at their ladder levels — arm L2 (rendered as its staging control per the analyser's convention; the mockup paints the button face), abort L1 button, trigger L1 button (the example declares it; undeclared descriptors render it ghost — §3) |
| alert aside: "Acquisition truncated — partial dataset" (warning variant) | **cannot_derive** `partial-capture-alert` — the condition is the dataset's runtime `status: partial` + `status_reason` (measurement model); structure renders the variant, data decides it — dc_psu's `margin-alert` shape with the capture class's own quantity |
| the probe/coupling context line | dataset `context` retention (device-classes §6: "Probe/coupling/bandwidth/acquisition-mode metadata is retained in context") — runtime data, rendered by host composition where present; not a reference surface |

The layout is the analyser's capture geometry (the capture class's own ratio — plot
recessed and dominant, run controls raised below), not dc_psu's readings/trend/table
grid: the classes differ in kind, and the mockup says so structurally. The styleguide's
mockup index line gains `class-oscilloscope.html`; `docs/internal/ui-styleguide.md`
gains the oscilloscope class-page row beside the others.

## 3. The reference, derived from the mockup

`standards/plugin-ui-class-reference/0.3.0/class-oscilloscope.json` — structure-not-data
(D2), the analyser's posture applied to a second capture class: authored structural
strings only; every count an expression; every quantity name arriving via the
descriptor at expansion.

**Slots** (URNs and inputs verified against the catalog and the action schemas this
pass):

| key | kind | resolves |
|---|---|---|
| `channels` | `channels`, `where_role: "analogue_input"` | the declared analogue channels, declaration order |
| `capture` | `dataset`, action `otdp.oscilloscope.fetch/1.0.0`, `schema_source: output_measurement`, `host_supplied: [acquisition_id]` | the waveform dataset (§5); one array-valued numeric variable per (channel, declared quantity); explicit time axis (per-channel axes where timing differs — the axis derivation follows the dataset); `x` = the time axis |
| `configure` | `configuration`, action `otdp.oscilloscope.configure/1.0.0`, `schema_source: input_schema` | the settings schema (configuration_id, channels[] of coupling/range_v/offset_v/probe_ratio, sample_rate_hz, sample_count, pretrigger_fraction, optional averaging_count, trigger{}) |
| `arm` | `procedure`, action `otdp.oscilloscope.arm/1.0.0`, `host_supplied: [configuration_id, acquisition_id]` | the acquisition start — L2 (`max_duration_ms` numeric; ids host-supplied), the analyser's own arm |
| `abort` | `procedure`, action `otdp.oscilloscope.abort/1.0.0`, `host_supplied: [acquisition_id]` | the acquisition stop — L1 |
| `trigger` | `procedure`, action `otdp.oscilloscope.trigger/1.0.0`, `when_declared: true`, `host_supplied: [acquisition_id]` | the software trigger — L1, optional (the profile's only optional action; the `when_declared` seam verified in the 0.3.0 schema) |
| `vendor_actions` | `vendor_actions` | D14 hook for unclaimed URNs |

`host_supplied` is exactly the §2.5 acquisition-lifecycle set (`acquisition_id` on the
lifecycle actions; `configuration_id` on arm) — structural field NAMES, D2-clean.
`fetch`'s `max_bytes`/`allow_partial` are caller inputs on a dataset action — covered
by the L4 page surface (fetch's own shape, dc_psu's `measure` precedent: no controls
row).

**Pages** (three, the family's standing count):

1. **Capture** (`kind: dataset`, `binding_slots: [capture, arm, abort, trigger]`,
   `plot: {kind: waveform, over_slot: capture, series: numeric_variables}`) — the
   mockup's composition: traces section (recessed, span 12) carrying `plot_index 0`;
   run section (raised, span 12) carrying the arm/abort/trigger button controls.
2. **Configuration** (`kind: configuration`, `binding_slots: [configure]`) — the
   preset-mediated settings surface (the settings data-table + preset wiring;
   `preset_asset_ids: []` at birth, the RC-6 scaffold rule).
3. **Device features** (`kind: configuration`, `binding_slots: [vendor_actions]`,
   `vendor_features: true`) — D14's placement row, every precedent's shape.

**Layouts** — the capture page authors all three run children (`arm`, `abort`,
`trigger`, kind `button`). This deviates deliberately from the analyser's committed
two-child run section, and the deviation is disclosed: the analyser's layout predates
the when_declared machinery's layout treatment, and the gateway's ghost-binding
honesty arm (shipped with the L11-verified composition) renders an undeclared action's
control ghost rather than absent — authoring the third child makes the trigger's
placement reference-owned instead of expander-inferred, and `n_run_actions` then
resolves over DECLARED actions (3 on the example, 2 on a trigger-less descriptor).
Build-time verification named: the expander's when_declared layout treatment matches
this reading (if it does not, the fix lands inside the batched SDK widening — the arm
is being built there anyway — and the deviation is re-disclosed on the PR).

**expect.components**: `engineering-plot` `1` (`per_page: capture`) — the waveform
canvas, the census key dc_psu added; `button` `{n_run_actions}` (`per_page: capture`);
`data-table` `1` (the configuration settings table, pooled per the gate's existing
counting — the capture page has NO table: a table of waveform samples is not a
surface this class presents); `panel` `{n_pages}`; `mode-banner` `1` per page
(`per_page: "*"`). **expect.controls**: `otdp.oscilloscope.configure/1.0.0: "preset"`,
`otdp.oscilloscope.arm/1.0.0: "staging"`, `otdp.oscilloscope.abort/1.0.0: "button"`,
`otdp.oscilloscope.trigger/1.0.0: "button"` — the analyser's four-row set verbatim
(the classes' action maps are identical modulo decode). `fetch` needs no row.

**forbid** — the analyser's four ids, carried whole, with the reason recorded against
dmm's three: `confirm-wrapped-run-action` (family-generic; and least vacuous here —
this class HAS the `abort` slug the gate's D7 set names, the only sweep class besides
the analyser whose action set intersects it); `color-role-hint-on-lane` and
`untraceable-lane-label` (family-generic carries, both precedents' convention — dmm's
reasoning, second application); `intermediated-energy-removing-action` — CARRIED, not
dropped: dmm dropped it because "dmm has no energy-removing action and cannot acquire
one within its profile"; the scope's `abort` is the acquisition-lifecycle stop of the
D7 slug set's own member, so the intent declaration (energy-and-stop-adjacent actions
are never intermediated) arms the safety-behaviours slice for the class that actually
owns one. If the refute lane holds this wrong, the drop is a one-line edit with dmm's
recorded-reason method — the set is per-reference authored data either way.

**cannot_derive** (five rows, each traced to a mockup element):

| id | aspect | reason | author_action |
|---|---|---|---|
| `acquisition-settings` | the coupling/range/offset/probe/sample/trigger selection surface | configure's channels array, closed unions, nested trigger object and conditional requirements are inexpressible at L2; configure is preset-mediated at birth; presets are commissioned evidence (A02) | author `ui/presets/*.json` via check-preset; the expander emits the scaffold |
| `trigger-marker` | the trigger marker and its readout on the waveform canvas | the dataset carries trigger structurally, but the preview wire has no trigger field — host-knowledge seam (§E.2.6's precedent); a contract-grade marker sub-row is the wall-payment item (§4) | host composition where a trigger time is known; the §E.2 marker sub-row when the owner calls the bump |
| `cursor-readout` | the cursor pair and Δ readout | cursors are operator runtime state; never on the wire, never derived | host composition at real benches |
| `partial-capture-alert` | the truncated-acquisition alert | the condition is the dataset's runtime `status: partial` + `status_reason` — observation state, data not structure | bench observation; the alert-bubble renders from host-observed conditions |
| `channel-names` | channel names beyond descriptor labels | the descriptor owns channel identity | label channels in the descriptor |

(`presets` is folded into `acquisition-settings`' author_action rather than carrying
dc_psu's separate row — the settings surface and its values are one deviation here;
disclosed as an authoring choice, not a schema consequence. `arm-safety`-class
sequencing is carried by the D7/forbid machinery + the layout's button set, as the
analyser's committed reference settled it.)

### 3.1 How the scope differs from the analyser — and the widening answer, stated

The differences are all inside the existing vocabulary plus one enum member: the
channel role (`analogue_input`); no `decode` slot (no annotation lanes, no decoder
expectations); the plot kind `waveform` instead of `digital_lanes` (the §5 widening —
the class's one vocabulary motion); no `digital-lanes` component expectation (the
lanes census key is the analyser's own); `engineering-plot` + `button` expectations in
its place. The family schema, the layout vocabulary, the plugin-ui manifest vocabulary,
the renderer and the §E.1 inventory otherwise carry what the page composes unchanged.
**The widening this class needs is exactly one enum member and its conditional —
priced in §5 — and it stays inside the unreleased 0.3.0 window (§1).**

## 4. The five display idioms (RC-L5-1): answered per idiom — and no bump called

RC-L5-1's rule: "each sweep landing that needs an idiom builds it class-generic… any
§E.1 contract rows the idioms eventually need batch into ONE contract bump — the next
wall-payment event after L5… Idioms that are pure host compositions of existing §E.1
components… need no bump at all. Trigger: the first sweep design record that needs an
idiom names it in its scope and calls the bump." This is that record — L11 looked and
answered none; L12 looked and answered none; L13 is the expected caller and has now
looked. The verdict per idiom (the styleguide's canonical six, with the handoff's
permutation noted):

| idiom | verdict | the structural reason |
|---|---|---|
| **the waveform canvas** | **LANDS HERE** — built class-generic | its contract home already exists: the `engineering-plot` §E.1 row + §E.2 rules over a `waveform`-kind plot; what was missing is the FAMILY's admission of the kind (§5). Any later waveform class (smu captures, function_gen outputs, spectrum shapes) reuses the same arm |
| **the capture-context strip** | **LANDS BY USE** | §E.2.5's acquisition disclosure is normative and shipped (per-trace, M1 fold); the scope page exercises it with the class's own numbers (`Acquired {n} samples · plotted {m} at {rate}`). No motion — it lands the moment a visible trace is decimated |
| **the cursor and trigger markers with their readout** | **DEFERRED BY NAME** — mockup-painted, host-side at runtime | `digital-lanes` carries `data-bw-trigger`/`data-bw-cursor` (its own row); `engineering-plot` has NO marker attributes, and the preview wire carries no cursor/trigger field — the host-knowledge seam §E.2.6 established for provenance. A contract-grade §E.2 engineering-plot marker sub-row is the named wall-payment item; this record does NOT call that bump (the class page presents honestly without it: the surfaces are cannot_derive) |
| **the grouped label column with brackets** | **HONEST NEGATIVE** | lanes-group machinery (`digital_lanes` `group_size`/`group_label_pattern`); analogue channels carry no positional grouping semantics. Caller: another lanes class, if the sweep mints one |
| **the annotation-chip rows** (bus values and decode overlays) | **HONEST NEGATIVE at birth** | the chips' content source is decode (the analyser's `decode`/`decode_annotated`); the scope profile has no decode action. Reopen trigger: an OTDP scope protocol/pulse-width profile — device-classes §6 itself says those "require an additional profile" |
| **the position badges** | **HONEST NEGATIVE** | identity-by-position is the lanes rule ("lane identity is position"); the scope's trace identity is legend-carried (§E.2 slots + `data-line`), a different and already-contracted mechanism |
| ("derived frequency" — the handoff's fifth, not in the styleguide's canonical list) | **HONEST NEGATIVE, home named** | §E.2.6's `derived` provenance machinery (derivation expression + `uncertainty unknown`) over a derived dataset variable — host/derivation-supplied, contracted today, exercised when a real bench declares a derived trace; nothing for this family to build |

**The ruling this section records: no §E.1 contract row is needed for this class's
first slice, so the wall-payment event RC-L5-1 anticipated is NOT called at L13** — the
one candidate (contract-grade waveform markers) is named as the batch item for
whenever the owner calls it, with the mockup already painting the idiom so the
presentation intent is on record. An honest negative about a bump is a result, not a
failure to have something to show.

## 5. The `waveform` widening, precisely

**Schema bytes** (one file, `standards/plugin-ui-class-reference/0.3.0/
class-reference.schema.json`, in-window):

- `page_template.plot.kind`: enum `["digital_lanes", "time_series"]` →
  `["digital_lanes", "time_series", "waveform"]`.
- One new `allOf` conditional branch, the time_series branch's mirror: if
  `kind: waveform` then `series` is required (post-L12-settlement semantics) and the
  group machinery (`group_size`, `group_label_pattern`, `group_radix`) is banned.
- `series` keeps its single const `"numeric_variables"` — NO new series rule. The
  D2 reasoning: a waveform dataset's trace variables ARE numeric variables
  (array-valued, dimensions named); the closed derivation "every numeric variable of
  the over-slot's dataset becomes a trace" serves both kinds; the semantic difference
  lives in the DATASET kind at expansion, which the expander checks — `waveform` plot
  templates over non-waveform datasets refuse, and vice versa (the shape-mismatch
  refusal, sibling of `classref_no_lanes`).

**Expander/gate** (SDK, folding into the L12 batched widening — still unbuilt, which
is the entire point of designing L13 now):

- The dataset-by-shape arm (L11 §3 item 1) gains the `waveform` dataset derivation:
  one array-valued numeric variable per (channel, declared quantity), the explicit
  time axis (per-channel axes where the dataset declares them), dataset kind
  `waveform`, the trigger object carried on the dataset (not the wire).
- The plot emission arm gains the `waveform` emission: `kind`, `binding_id`, `x`
  (the time axis), `y` (the trace variables) — the manifest shape plugin-ui 0.4.0
  already defines; `channel_hints` untouched (author/runtime matter).
- The gate's census arms need nothing new: `engineering-plot` → `bw-plot` is the key
  dc_psu added; the L4 coverage arm consults the plan row's render surface (already
  widened off lanes-only at L11's design).
- Counter closure gains `n_analogue_channels` (role-generic naming beside
  `n_source_channels`/`n_measure_channels`) and shares `n_run_actions` (the
  analyser's own), `n_pages`. Closure discipline is the invariant; exact names are
  build detail (L11 §3 item 5's posture, third application).

**Renderer: NO motion, with the evidence.** `plot.py` read in full — `compose_plot`
never reads a plot kind; the emit model (slots, hints, axes, refusal, legend,
acquisition, provenance, reference/threshold lines) is kind-uniform. A scoped text
search finds zero `waveform` occurrences under `packages/ui-html` — there is no branch
to widen. The §E.2 waveform residual (symbols) remains the disclosed owner fork; the
scope's pattern page and mockup paint colour+dash identity only, so nothing in this
slice depends on the fork's resolution. **No ui-html motion rides this class** — not
even the 0.3.1-cut composition divergence class (the scope composer lands in
`packages/ui-html/src/benchweave_ui_html/classref.py` per the standing per-class
shape and rides whatever ui-html release the L12 batch cuts, F2's bounded-divergence
ruling extended once).

**Gateway: no runtime motion.** The capture-page consumption is the analyser's own
path (dataset page, plot block, procedure controls); the scope needs no `class_panel`
(standard page kinds only).

## 6. The A3 extension — the shared census, third instance

`tests/ui_html/test_classref_oscilloscope.py` extends the shared instrument L12
designed (`tests/ui_html/classref_census.py` — landing with the L12 build; if the L13
build runs first, the lift is the L13 build's disclosed mechanical motion, L12 §6's
terms verbatim). The arms, per the L12 seven plus this class's own:

1. **Hooks in both themes** — every hook family ≥1 per theme section.
2. **Hook counts EQUAL the resolved expectation over the committed OTDP example** —
   `bw-plot` 1, `bw-button` 3 (arm/abort/trigger — the example declares all five
   actions), `bw-alert-bubble` 1. Both kill directions by construction: a mockup edit
   that changes a count reds against the resolved side; a reference edit that changes
   the derivation (the plot binding, the channels slot's role, a controls row) reds
   against the mockup's counts. A mockup edit that does NOT redden the test is the
   instrument failing — report, never a quiet pass.
3. **Placement, including the count-conserving-move kill**: every hook occurrence on
   its root tag (`bw-plot` → `section.plot`, `bw-button` → `button`,
   `bw-alert-bubble` → `aside`), the container-scoped hooks inside their containers
   (capture region, run panel), and — **the arm this class adds to the instrument** —
   the idiom surfaces (trigger marker line, cursor chips) carrying NO `bw-` hook. The
   RED arm moves a hook count-conservingly (a `bw-plot` onto the run panel; a
   `bw-button` onto the figure) AND reverse-plants a `bw-` class on a marker chip —
   both red while the count arm stays green under the move. The mutation is
   demonstrated to kill, not assumed.
4. **Theme-invariance** — the census is identical across themes.
5. **The alert is one per theme and a named cannot_derive** (`partial-capture-alert`).
6. **Selection RED-to-green** — banked at design time this pass (executed, recorded):
   gateway-side `select_references(corpus, descriptor)` on the branch head `c64f3d05`
   returns `None` for `class-oscilloscope` while `class-logic_analyser` →
   `['otdp.logic_analyser/1.0.0']` and `class-dc_psu` → `['otdp.dc_psu/1.0.0']`
   resolve (`class-dmm` → `None`, consistent with the L12 build's pending state). The
   slice greens the scope half only.
7. **The pattern-page arms** (the drift guard over the scope capture composer): one
   plot with both channel traces (2 = 2 channels × 1 quantity, derived from the corpus
   pair, never literals); three run buttons from the declared actions; labels are
   corpus strings; the sections mirror the reference layout block's surfaces and
   spans; only §E.1 partials compose; no control surface fabricated beyond the
   ladder's (no numeric field painted as applied, no confirm anywhere); the PATTERNS
   census entry is `kind: class-page`, `row_id:
   plugin-ui-class-reference::class-oscilloscope`, `fixture_id: capture`; both themes
   export.

## 7. Choreography — landing inside the open window

1. **Gateway branch content** (this slice): the §8 corpus motion + this record + the
   census module + the composer + the mockup + the styleguide rows. Stacked on the
   L11/L12 line (`feat/l13-oscilloscope-classref` from `c64f3d05`); the branch-internal
   sync-pair reds L11 disclosed continue until the batch's pointer leg (never merged
   red).
2. **Coordination with the L12 batched promotion leg** (the timing dependency §1
   names): the SDK waveform emission/counters fold into the L12 leg's widening build —
   the leg is designed (L12 §7) and unbuilt; L13's design arriving first is what makes
   the fold free. If the leg has already cut when the L13 build runs, the waveform SDK
   arm becomes the leg's own follow-up under then-current train rules and the fallback
   pricing of §1 applies to nothing else (the corpus still batches, having landed
   before the merge).
3. **The #408 order for the batch as a whole** stands: ui-html 0.3.1 → SDK PR →
   release cut → pointer advance (gitlink + `.gitmodules` pin + mirror + matrix in one
   commit) → merge on the full rollup (`scripts/merge-verified.sh`), zero fail, zero
   pending.
4. The standards tripwire fires by design (non-empty `standards/` diff); this record
   is the named sanction. Standards-governor lane mandatory; two-lane adversary pass
   on the built slice.

## 8. Corpus-motion census (exact bytes)

Gateway repo, `standards/`:
- **Added** `standards/plugin-ui-class-reference/0.3.0/class-oscilloscope.json` — one
  new corpus row, `source` citing the authoring staging path
  `docs/plugin-ui-class-reference-v2/class-oscilloscope.json` (removed in-PR — the
  founding convention).
- **Edited** `standards/plugin-ui-class-reference/0.3.0/class-reference.schema.json`
  — the §5 widening; the row's digest moves via repin, no new row. (If L12's
  series-required edit has not landed when the L13 build runs, the two edits land as
  separate commits on the same file — each with its own RED evidence — and repin runs
  once per commit.)
- **Unchanged**: `standards-manifest.json` (0.3.0 already active on the branch),
  `dependency_policy` (range already `<0.4.0`), `cross-constraints.json` (all 3 rows
  stand — the 0.3.0 row's substance is unchanged: the waveform widening consumes
  plugin-ui 0.4.0 vocabulary the row already floors), `class-logic_analyser.json`,
  `class-dc_psu.json`, and — when it exists on the branch — `class-dmm.json`
  (byte-identical through this slice, A5), every 0.2.0/0.1.0 byte (zero frozen-row
  rewrites, A7).
- **Unpinned prose**: the family `README.md` files-table row; the styleguide's
  mockup index line + the oscilloscope class-page row.

Gateway repo, docs/tests (no corpus impact):
`docs/internal/ui-styleguide-mockups/class-oscilloscope.html` (new, prose-adjacent —
no corpus rows, no governance event); `tests/ui_html/test_classref_oscilloscope.py`
(the shared-census third instance; the `classref_census.py` lift itself is L12's
disclosed motion or this slice's if it builds first).

`packages/ui-html`: the oscilloscope composer + PATTERNS entry (rides the batch's
ui-html release, F2's bounded-divergence ruling).

SDK (inside the batched leg): the §5 expander/gate arms + counter names + the
oscilloscope fixtures (the OTDP example as F-scope-1; refusal fixtures: zero analogue
channels → the channels-slot refusal; a `time_series` template over the waveform
dataset → the shape-mismatch refusal; absent required action →
`classref_required_action_absent`) + the vendored 0.3.0 ingest picking up the widened
schema and the new class file. **No otdp motion of any kind.**

## 9. Deferrals, each with a home and an observable reopen trigger

| defers | home | reopen trigger |
|---|---|---|
| contract-grade cursor/trigger markers on `engineering-plot` (a §E.2 marker sub-row) | the next plugin-ui wall-payment event (RC-L5-1's batching rule — the ONE candidate item this record names) | the owner calling the bump; or the first class needing wire-carried markers (a host that cannot compose them honestly) |
| the §E.2 symbols-in-waveform owner fork | the contract's own disclosed residual | an owner ruling — nothing in this slice depends on it |
| annotation chips on waveform plots (protocol decode overlays) | the OTDP scope profile (device-classes §6's additional-profile clause) + this family's placement when it exists | an OTDP catalog revision giving the scope a decode-family action |
| grouped label column / position badges | unchanged (styleguide idioms; lanes-shaped classes) | another lanes class, if minted (the A10 divergence rule) |
| derived-trace presentation ("derived frequency") | §E.2.6 provenance machinery, host/derivation-supplied | a real bench descriptor declaring a derived variable on a capture class |
| per-channel timing presentation (separate axes vs characterised offset) | the expander's axis derivation follows the dataset; the class reference authors nothing | a descriptor whose fetch dataset declares distinct per-channel axes (the derivation's first real exercise) |
| the trigger-button ghost treatment | the batched SDK widening's when_declared layout arm | the build-time verification of §3's layout reading (re-disclosed on the PR if it falsifies) |

## 10. Acceptance rules (pre-committed — written before any build output)

Deterministic census over the fixed fixture set (the committed OTDP oscilloscope
example, the refusal fixtures, the banked baselines). Denominators named; both kill
directions stated; the underpowered branch named. These rules bind the build agent.

- **A1 — expansion is valid and example-shaped.** `benchweave-sdk derive-ui` on the
  oscilloscope example produces a manifest set passing `validate_presentation`, with
  the capture page carrying a dataset binding, a `waveform` plot over the capture slot
  with `series: numeric_variables`, `x` the time axis and `y` the 2/2 derived trace
  variables (2 channels × 1 declared quantity — counts from the derivation, never
  literals). Kill: any count off, any validation failure, or a trace variable not
  traceable to a (channel, quantity) pair.
- **A2 — the gate passes with the birth deviations REPORTED.** `verify-ui` on the
  example exits 0 with a REPORTED deviation for `configure` (preset-mediated), none
  silent; the census on the capture page reads `engineering-plot` 1/1, `button`
  3/3 (the example's declared arm/abort/trigger), `panel` `{n_pages}`, `mode-banner`
  per page; `fetch` is covered via the plot figure (the widened L4 arm); the
  configuration page reads the settings `data-table`. Kill: any census delta, any
  undeclared divergence, or `classref_gate_uncovered` naming fetch.
- **A3 — the mockup-consistency arm (the namesake).** §6's arms over
  `class-oscilloscope.html` × the reference × the example, with the count kill both
  ways, the count-conserving-move kill demonstrated RED (a hook moved to the run panel
  or out of its container reds while counts conserve), AND the no-hook-on-idiom-surface
  kill demonstrated RED (a `bw-` class planted on the trigger-marker chip reds).
  **The falsifier: any disagreement between the mockup's counts or placements and the
  resolved expectation; a mockup edit that does NOT redden the test is the instrument
  failing — reported, never a pass.**
- **A4 — RED control (banked at design time, executed this pass).** On the branch head
  `c64f3d05`: gateway-side `select_references` on the oscilloscope example → `None`,
  with the analyser and dc_psu resolving — executed and recorded above (§6 arm 6). The
  slice greens the scope half. Kill: either half green before its landing commit
  exists.
- **A5 — the predecessors are untouched.** `class-logic_analyser.json` and
  `class-dc_psu.json` byte-identical through the slice (sorted-key diff = empty);
  `class-dmm.json` byte-identical from the moment it exists on the branch; the only
  prior-test motion is the shared-census import (assertions byte-identical); the full
  L11/L12 test modules re-run green. Kill: any byte beyond the disclosed motions, or
  any prior acceptance rule flipping.
- **A6 — D2 census on the scope reference.** No numeric literals outside the
  structural set (spans ≤12, plot indices); no data strings (no values, units, channel
  names, quantity names, no sample counts or rates — the acquisition numbers are
  runtime data and appear nowhere in the reference). Machine-checked census. Kill: any
  authored data string.
- **A7 — corpus and version gates.** `benchweave.standards check` clean; `repin`
  writes exactly ONE new row (`class-oscilloscope.json`) and moves exactly ONE
  existing row's digest (the schema edit), with ZERO frozen-row rewrites (every
  0.2.0/0.1.0 row byte-identical); `matrix --check` clean; the served set (17) and
  range unchanged. Kill: any frozen-row motion or an unexpected row count.
- **A8 — the widening's own arms.** After the schema edit: a `waveform` plot template
  WITHOUT `series` FAILS validation; a `waveform` template WITH group machinery FAILS;
  a scratch `time_series` template still behaves per the L12 settlement; all committed
  class documents (analyser, dc_psu, dmm when present, oscilloscope) PASS. The
  shape-mismatch refusals fire both directions (a `time_series` template over the
  waveform fixture refuses; a `waveform` template over the dc_psu scalar fixture
  refuses). Kill: any scratch document validating, any committed document failing, or
  either refusal missing.
- **A9 — order gates.** The batch's #408 order held (ui-html release → SDK PR →
  release cut → pointer advance in one commit → merge on the full rollup); the lock
  anchor verified before the tag; the branch's sync-pair reds go green at the pointer
  leg and not before. Kill: any inversion, or a merge with red/pending lanes.

**Underpowered branch:** if the capture page cannot be composed from §E.1 partials the
renderer already ships (a surface the vocabulary genuinely lacks — the design's claim
is it does not, §5's evidence), that falsifies §3.1's widening answer and the finding
comes back with evidence, priced then, never silently absorbed. If the census cannot
key on contract surfaces the preview host emits, that is an instrument failure —
reported, not a verdict.

## 11. Review tier and Step-1 keyword scan

Tier 3 — touches `standards/` + JSON Schema; rides a batch that advances the submodule
pointer; diff text carries `sha256` (corpus rows, sync tests, this record). Two-lane
adversary pass and the standards-governor lane mandatory.

| keyword | expected count | where |
|---|---|---|
| `sha256` | ~10–20 | 1 new corpus row + 1 digest motion, sync/fixture tests, this record |
| `hashlib` | ~2–4 | SDK derivation tests |
| `protection` | ~1–2 | this record's prose only; zero in code (the scope's abort is acquisition lifecycle — the honest note) |
| `threading` / `asyncio` / `subprocess` / `migrate` / `recovery` | 0 | in-process render; derivation, not migration |

## 12. Top risks, each with its falsifier

- **R1 — the timing dependency misses.** The L12 batch merges before L13's corpus
  lands → the fallback pricing of §1 activates (two version events). Falsified by
  checking the branch state at build start; the design's recommendation (land before
  the pointer leg) is a sequencing call recorded for the coordinator, not a gate this
  record can enforce.
- **R2 — the `waveform`-as-`numeric_variables` reuse is wrong at build.** If the
  expander cannot derive waveform traces D2-cleanly under the shared series rule (a
  per-kind selection with no structural basis), the schema motion splits (a
  `trace_variables` enum value joins the const) — still in-window, one more conditional
  branch, re-priced on the evidence. Falsified by A1's trace-variable traceability.
- **R3 — the trigger-button ghost reading falsifies.** The expander's when_declared
  layout treatment may not match §3's authored-three-children reading. Falsified by
  the build-time verification; the fix is the batched SDK widening's own arm (§9's
  deferral row).
- **R4 — the four-id forbid carry is wrong.** If review holds
  `intermediated-energy-removing-action` vacuous for a class whose abort is capture
  lifecycle (dmm's reasoning applied stricter), the drop is one line with the reason
  recorded. Falsified by the adversary lane or the owner at the row-call.
- **R5 — mockup drift.** Intended: the mockup is the spec; edits force re-derivation
  and the census reds (A3).
- **R6 — public-repo discipline.** `OSC-01` and every fixture name invented; no real
  bench, vendor or corpus identifier (paid at authoring).
- **R7 — the shared-census lift races the L12 build.** Two lanes touching
  `test_classref_dc_psu.py`'s import concurrently is a MODIFY-vs-MODIFY merge resolved
  in review (the dev-stage rule's ordinary path). Falsified by CI; mitigated by the
  arms being byte-identical by design.

## 13. Row-calls (numbered; the principal alone decides)

- **RC-L13-1 — the shape.** In-window batching into the unreleased 0.3.0: the
  `waveform` enum member + conditional + `class-oscilloscope.json`, landing on the
  stacked branch before the batch's promotion leg (recommended — G-5 admits nothing
  else today, §1's evidence, and the batch's SDK leg absorbs the expander arm free).
  Alternative: wait for the merge and land 0.3.1 + 0.4.0 separately — legal after the
  leg, strictly more expensive, recorded as the fallback.
- **RC-L13-2 — no wall-payment bump called at L13.** The idioms audit (§4) lands the
  canvas and context strip on existing contract homes, defers markers to the host seam,
  and records honest negatives for the lanes-shaped trio. The one candidate §E.1 item
  (engineering-plot marker sub-row) is named for the NEXT wall-payment event, not
  called now. Recommend ACCEPT (an honest negative, first-class).
- **RC-L13-3 — the layout authors the trigger button.** The capture layout carries
  all three run children; undeclared actions render ghost (the L4/L11-verified arm).
  Alternative: the analyser's two-child layout with expander-inferred trigger
  placement — rejected as expander magic where the vocabulary admits authoring.
  Recommend ACCEPT.
- **RC-L13-4 — the four-id forbid carry** (§3), `intermediated-energy-removing-action`
  included with the D7-slug reasoning. Alternative: dmm's three-id drop with the
  recorded reason. Recommend ACCEPT the carry; the refute lane is explicitly invited
  to kill it (R4).

## 14. Precedent map (principle 9)

| L13 surface | in-tree precedent | why it fits |
|---|---|---|
| class file + schema arm added to an in-window unreleased bump | the batch rule (GOVERNANCE), L11's addendum motions, L12's §1 | same train, same bump, no new version directory |
| plot-kind enum widening with per-kind conditionals | the L11 `time_series` widening (0.3.0's own substance) | the same shape, one more member, mirror conditional |
| mockup authored with hooks + placement from birth | L12's `class-dmm.html` design (§2 there) | the convention's second authored-from-birth instance |
| capture-class reference shape | `class-logic_analyser.json` (slots, pages, controls, D7 forbid set) | the action maps are identical modulo decode |
| shared census third instance | `classref_census.py` (L12 §6's lift of the L11 instrument) | the instrument must not fork between classes (F1's lesson) |
| per-class composer in `classref.py` | `render_capture_page`, `render_output_page`, the dmm composer | the module's standing shape, fourth instance |
| host-knowledge seam for non-wire presentation data | §E.2.6 provenance ("the preview wire carries no provenance field") | the trigger-marker deferral's structural home |
| expansion fixture = the OTDP class example | RC-L11-4's ruling | third application; no derived fixture needed |

## 15. Appendix — evidence, disclosures, and the pre-flight record

**Pre-flight (the #181 R2 discipline):** `git fetch origin`; `gh pr list` — **zero
open PRs in the gateway repo and zero in the SDK repo** (the #498 interface-0.1.1
pairing L12 saw open has merged; main is `b905b19a`). `git worktree list` run before
any tree action; other lanes' trees (`l11-x7q9`, `l12-d4m9`, the designer/land159
trees) untouched; this lane's tree is `.wt/l13-t4k9`. No remote branch touches
`standards/plugin-ui-class-reference/`, the mockups, or the sweep beyond the L11/L12
lines this design stacks on.

**Gortex:** AVAILABLE to this subagent — the probe read
(`BenchWeave/.wt/l13-t4k9/.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md`)
was served with the worktree-prefixed path and content identity verified against the
branch head; source reads went through `mcp__gortex__read`/`search` (one shell grep
on a symbol-colliding pattern was blocked by the PreToolUse hook and re-served
through gortex). Session start reported checkout discovery `view_building,
retryable=true`; it cleared within the first reads. No daemon restart, no tracking
change.

**The slotted-set check:** §7A row L13 verified against the program record AND the
workbench §8 order (`docs/internal/ui-styleguide-workbench-design.md` §8: "DC power
supply; digital multimeter; **oscilloscope**; …") — oscilloscope is genuinely the
third sweep class. Nothing in L6–L10 gates it.

**Design-time execution beyond reading (one, disclosed):** the A4 RED pair —
`select_references` run gateway-side in the worktree venv (bootstrapped `uv`, nothing
written outside the gitignored venv) — because a pre-committed acceptance rule that
can be banked before the build should be (L12's own §15 precedent, same reasoning).

**Paths read as evidence:** `standards/GOVERNANCE.md`;
`standards/standards-manifest.json` + `dependency_policy` + on-disk version dirs (the
17/27 counts); `standards/cross-constraints.json` (3 rows);
`standards/plugin-ui-class-reference/0.3.0/` (`class-reference.schema.json` in full,
`class-logic_analyser.json` in full, `layout.schema.json` $defs in full);
`standards/plugin-ui/0.4.0/ui-manifest.schema.json` (`$defs.plot` in full, the
waveform conditional arm);
`standards/otdp/0.2.3/device-profile-catalog.json` (the oscilloscope profile + all
five action schemas); `standards/otdp/0.2.3/examples/class-oscilloscope.json` (in
full); `standards/otdp/0.2.3/otdp-measurement.schema.json` (`$defs.dataset`,
`$defs.variable`); `standards/otdp/0.2.3/device-classes.md` §6 (Oscilloscope) and §7
(the analyser contrast); `docs/internal/ui-contract.md` (§E.1 all 15 rows; §E.2.0–§E.2.6
in full); `docs/internal/ui-styleguide.md` (the class-reference capture-pages section,
the idioms paragraph at :271); `docs/internal/ui-styleguide-mockups/class-dc_psu.html`
(hook placement) and `class-logic_analyser.html` (capture-page structure);
`packages/ui-html/src/benchweave_ui_html/plot.py` (in full — the kind-blind
evidence); `packages/sdk/src/benchweave_sdk/preview_models.py:13` (PlotKind);
`src/benchweave/presentation/classref.py::select_references` (source);
`.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md` (in full, addendum and
refute fold), `2026-10-19-classref-l12-dmm-design.md` (in full, from the l12 branch
`e4573525` — read-only, the lane's tree untouched),
`2026-10-14-classref-logic-analyser-design.md` (§0, §2.5, §7A, §8, heading map),
`2026-10-16-classref-l5-plugin-ui-0-4-0-design.md` (§1 reconciliation, RC-L5-1);
SDK pin state (gitlink `9e0449ef`, pyproject 0.16.0, the vendored classref listing
{0.1.0, 0.2.0}).

**Honest disclosures to the dispatch:** (a) the dispatch's grounding held on every
point checked — no oscilloscope mockup exists, the OTDP example is at 0.2.3, the
family on the branch is 0.3.0 carrying the re-stamped analyser and dc_psu, the
served/retained/cross-constraint counts re-derive to 17/27/3; (b) one refinement: the
dispatch's "main now serves… the classref family at 0.3.0" conflates the branch with
main — main serves classref **0.2.0** (verified from the main checkout's manifest;
`c64f3d05` is NOT an ancestor of `main`); the 17/27/3 counts are the BRANCH's serving
state, which is the state that matters for this design (the window question turns on
it, §1); (c) the "unreleased 0.3.0 window" is real but time-boxed by the L12 batch's
promotion leg, not by any date — the design's sequencing recommendation (RC-L13-1) is
what keeps the widening inside it; (d) the idioms deferral the dispatch attributed to
the program record's §2.5 lives in the L5 record's §1/RC-L5-1 (the program record
contains no idiom text — searched); §2.5's ladder is what governs the scope's
per-action levels, and both were read.
