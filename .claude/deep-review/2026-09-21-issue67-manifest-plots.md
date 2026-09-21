# Issue #67 — manifest-driven plot rendering in the preview (UI-stage first slice)

Date: 2026-09-21
Status: design (no source mutated). Scope: the first UI-stage slice — a renderer that
consumes manifest `plots` (hinted or not) in the SDK preview, the end-to-end hint-transport
fork resolved, the FC6 theme-token drive-by fix, and activation of drift obligation #12
(the UI doc-home row). Presentation interactions (legend re-show, persisted visibility
overrides, wider colour vocabulary) are separable, expected to defer, and deferred here
with reopen triggers.

Reading verified on `main` at `4d06960` (2026-09-21). Every load-bearing claim cites the
file and anchor it was read at; anchors re-verified this session, not inherited from the
row-C record (whose line numbers were taken at `8bc83a5`).
**Review tier: Tier 3** — the change touches `standards/` (a plugin-ui-preview PATCH
bump), edits JSON Schema, and advances the `packages/sdk` submodule pointer. The refute
pass and standards-governor review are mandatory for the build.

---

## 1. Problem and root framing

Issue #67 (GO'd by the 2026-09-20 triage council): the plot model stays unvalidated
doctrine until a renderer consumes it. Today no renderer consumes manifest `plots`:

- The preview workbench synthesizes traces from observations —
  `ui/src/compositions/fixtures.ts` `scenarioToWorkbenchFixture` builds degenerate
  two-point traces (`values: [[-1, value], [0, value]]`) from each numeric observation,
  and `DeviceWorkbench.tsx` renders exactly one hardcoded plot ("Output activity",
  threshold `{value: 1.9, "Current warning limit"}`) from them.
- Manifest pages pass through opaquely:
  `packages/sdk/src/benchweave_sdk/fixtures.py` `build_preview_model` sets
  `pages=tuple(candidate.manifest.get("pages", []))`; `ui/src/preview/api.ts`
  `decodePreview` keeps them as `Record<string, unknown>[]`, requiring only that each
  page be an object with an `id`.

### 1.1 Root cause — there are three blockers, not one

**(1) Resolution.** A manifest plot carries exactly
`{kind, binding_id, x, y, channel_hints}` (verified: `$defs.plot` in
`standards/plugin-ui/0.2.0/ui-manifest.schema.json` — no title, no threshold, no axis
labels; those live in the binding catalogue's variables, `$defs.variable`
`{id, type, unit, shape, axis_role}`). Resolving `x`/`y` ids to unit-carrying channels
requires the binding catalogue — trusted *host* metadata (`standards/plugin-ui/0.2.0/README.md`
"The catalogue and schema corpus come from the trusted host"; `contracts.py` docstring) —
which the browser never receives. `_plot_findings`
(`src/benchweave/presentation/contracts.py:469`, mirrored byte-for-byte in the SDK's
vendored copy) is the only in-tree implementation of that resolution.

**(2) Previewability — a defect this increment must fix, not work around.**
`fixtures.py` `_variable` (refusals at `:84`, `:87`) requires every catalogue target to
carry EXACTLY ONE scalar variable. But:

- A *valid* `time_series` plot REQUIRES its target to carry a receipt-time axis variable:
  `_plot_findings` enforces `x` with `axis_role == "receipt_time"` and `unit == "s"`, and
  `_target_findings` (`contracts.py`) permits observation targets of exactly one
  value variable plus at most one receipt-time scalar. The repo's own canonical valid
  shape — the bundle in `tests/unit/test_presentation_manifest.py` (target `voltage` with
  variables `time` (receipt_time, s) + `value` (V)) — has TWO variables.
- `generate_baselines` iterates ALL catalogue targets through `_variable`, so any target
  it refuses kills the ENTIRE preview build (`preview_unsupported_shape` →
  `ClickException` via `_domain_errors`).

Therefore, today, **a plugin that declares a legal time_series plot cannot run the
preview server at all** — and neither can any plugin with a dataset target (vector
variables; the waveform specimens `scope_specimen` and `multi_channel_specimen` in
`tests/unit/test_presentation_specimens.py` are both un-previewable). The plot-rendering
feature's own primary case is unreachable without relaxing `_variable`. This is the
load-bearing discovery of this design; everything else composes with proven mechanisms.

**(3) Rendering.** No composition maps plot structures into `EngineeringPlot` under the
row-C contract (two-pass styling, hint bias, stable indices — `.claude/deep-review/2026-09-19-issue6-rowC-display-hints.md` §2.4).

### 1.2 FC6 root cause, at line level

`ui/src/components/plots/EngineeringPlot.tsx`:

- The legend `useMemo` (`:119`) resolves tokens via
  `getComputedStyle(document.documentElement)` with deps `[traces, hints, threshold]`.
- The chart `useEffect` resolves via `getComputedStyle(element)` (the canvas div) with
  deps `[kind, threshold, traces, x, hints]`.
- Theme switching changes NO dependency: `PreviewApp.tsx` sets
  `document.documentElement.dataset.theme` from React state; `App.tsx` sets
  `data-theme` on the `<main>` wrapper. Neither mutation touches any prop — tokens
  resolve once and go stale until a data dep changes. That is FC6.

The same two reads use **different elements**, which is a second, switch-independent
manifestation of the family: `ui/src/styles/themes.css` defines light tokens at
`:root, [data-theme="light"]`, so in the gateway app (`App.tsx` shape) the legend —
reading `documentElement` — always resolves LIGHT tokens while the chart — reading the
themed subtree — resolves dark in dark mode. Legend swatch and chart line colours
disagree in the gateway app today regardless of switching. The FC6 fix must unify the
read source, not merely add a re-trigger.

---

## 2. The transport fork — decided

The issue names two options for carrying plots (and their hints) to the renderer. Both
were costed honestly.

### Option (a) — the browser sees the catalogue

Serve catalogue-derived variable metadata (per binding: target variables with
id/unit/axis_role) in the preview document; the browser resolves plots itself.

Costs:

- **Schema bump either way.** The served document's root def is
  `additionalProperties: false` (`standards/plugin-ui-preview/0.1.0/preview-document.schema.json`),
  so ANY new top-level field is a schema edit → a plugin-ui-preview bump. Riding the
  projection inside the existing `pages` passthrough instead would exploit the page def's
  open world (only `id` required) — precisely the "normative data in a non-normative
  escape hatch" shape row C §1 rejected (unvalidatable-by-schema, silently droppable).
- **A third implementation of plot resolution.** Binding→target→variable resolution and
  the axis rules would be re-implemented in TypeScript, unpinned. The Python pair
  (`src/benchweave/presentation/contracts.py` ↔ the SDK's vendored copy) is held in
  lockstep by CON-4/`make check-sdk-standards`; a TS mirror has no possible byte-pin and
  is exactly the REG-4 hand-mirror drift class — minus the pin test that discipline
  required. Every future plot-model change becomes a three-place obligation.
- **Catalogue disclosure.** Host-trusted, descriptor-derived metadata would enter a
  document the renderer must parse and re-derive semantics from, widening the wire
  contract the decoder owns.

### Option (b) — SDK-side projection into a renderer-ready shape (SELECTED)

`build_preview_model` gains a projection step: from the validated `(manifest, binding
catalogue)` it emits `plot_views[]` — one per declared manifest plot — carrying
everything the renderer needs: kind, binding_id, derived title, `x {label, unit}`,
and per-channel `{variable_id, label, unit, color_role?, visible?}` with row-C hints
already merged in. The browser decodes a typed view, joins channels to scenario
observations by `binding_id` (the join key it already uses), and composes through the
EXISTING `EngineeringPlot` contract unchanged. The browser stays dumb; plot resolution
stays in exactly one language, on the trusted side, where the corpus pins live.

**Rationale, grounded in the authority split:** the catalogue is host metadata and hints
are plugin preferences — under (b), catalogue-derived labels/units are projected by the
SDK (the trusted side of the preview tool) into a schema-validated field, and hints ride
as projected preferences composable under host theme authority, which is the row-C
composition contract verbatim. Both options cost the same PATCH bump; (a) buys nothing
with that bump and additionally owes an unpinned TS semantic mirror. Neither option
forces a plugin-ui change: hints and the plot shape are already in the 0.2.0 schema
(verified in `$defs.plot`), and the projection only *consumes* them.

---

## 3. Mechanism

### 3.1 plugin-ui-preview 0.1.0 → 0.1.1 (PATCH — additive optional field)

Governance class: "additive machine errata, backwards-compatible → PATCH"
(`standards/GOVERNANCE.md` change-class table; the interface `approver_token` pattern).
Bump window clear: the standard was admitted 2026-09-16 and has not bumped since.

- `standards/plugin-ui-preview/0.1.1/` is a **copy** of `0.1.0/` with edits only in the
  copy: both schemas' `$id` URLs and `title`s move to `0.1.1`, and
  `fixture.schema.json`'s `contract_version` const (`"0.1.0"`) moves to `"0.1.1"` — the
  row-C/OTDP precedent is that version consts move in the copy (row-C §2.2: "the four
  contract_version consts move to 0.1.1"). `preview-document.schema.json` additionally
  gains, in the copy:

```json
"plot_views": {
  "type": "array", "maxItems": 1024,
  "items": {"$ref": "#/$defs/plot_view"}
}
```

  (optional at root — absence means "no plots", so older documents stay valid), with
  closed defs:

```json
"plot_view": {
  "type": "object", "additionalProperties": false,
  "required": ["page_id", "kind", "binding_id", "title", "x", "channels"],
  "properties": {
    "page_id": {"type": "string", "minLength": 1},
    "kind": {"enum": ["time_series", "waveform"]},
    "binding_id": {"type": "string", "minLength": 1},
    "title": {"type": "string", "minLength": 1},
    "x": {"$ref": "#/$defs/axis"},
    "channels": {"type": "array", "minItems": 1, "maxItems": 16,
                  "items": {"$ref": "#/$defs/channel"}}
  }
},
"axis": {"type": "object", "additionalProperties": false,
  "required": ["label", "unit"],
  "properties": {"label": {"type": "string", "minLength": 1},
                  "unit": {"type": ["string", "null"], "maxLength": 64}}},
"channel": {"type": "object", "additionalProperties": false,
  "required": ["variable_id", "label", "unit"],
  "properties": {
    "variable_id": {"type": "string", "minLength": 1},
    "label": {"type": "string", "minLength": 1},
    "unit": {"type": ["string", "null"], "maxLength": 64},
    "color_role": {"enum": ["accent", "muted"]},
    "visible": {"type": "boolean"}
  }}
```

  `maxItems: 1024` = pages (≤64) × plots (≤16). `color_role` mirrors the plugin-ui hint
  enum exactly — severity roles stay outside (row-C §2.1: a plugin preference must never
  fake alarm semantics).
- `standards/plugin-ui-preview/0.1.0/` stays in place, digest-frozen; new corpus rows
  cite the 0.1.0 corpus paths as `source` (current rows cite the pre-corpus
  `docs/plugin-ui-preview-v1/...` history; new rows follow the current convention).
- `standards/standards-manifest.json`: plugin-ui-preview → `0.1.1`, `supersedes:
  "0.1.0"`, normative paths repointed.
- **No identity event**: `IDENTITY_STANDARD_KEYS = ("otdp", "registry", "execution",
  "interface")` (`src/benchweave/standards/manifest.py:13`) — plugin-ui-preview is not
  an identity key; the CON-8 chain is untouched.
- Consequence of the fixture-const flip: author fixture documents must declare
  `contract_version: "0.1.1"`. In-tree that is `_preview_fixture` in
  `packages/sdk/src/benchweave_sdk/presentation.py` (the `"0.1.0"` literal row C §4
  item 13 noted as "stays 0.1.0" — this bump is the event that moves it), the
  `author_fixture()` builder in `tests/sdk/test_preview_fixtures.py`, and the
  scaffold-generated example fixtures. All move in-arc.

### 3.2 The projection (SDK)

- `preview_models.py` gains frozen `PlotView` / `PlotChannel` / axis dataclasses with
  `to_document()`; `PreviewModel` gains `plot_views: tuple[PlotView, ...]` and emits it
  in `to_document()`.
- `fixtures.py` gains `project_plot_views(manifest, catalogue) -> tuple[PlotView, ...]`,
  called from `build_preview_model` next to the existing pages passthrough. It reuses
  `_target_index` and re-derives binding→target→variables by plain dict lookup.
- Determinism rules (specified now, not at build time):
  - one view per manifest plot, in page order then plot order;
  - `title` = the page's `title` when the page declares exactly one plot, else
    `f"{page.title} ({index + 1}/{count})"` — manifest plots carry no title of their own;
  - `label`s are variable ids verbatim (prettification is a UI concern — the browser
    already owns `titleFor`);
  - `unit`s come from the catalogue variables (nullable → `null`);
  - `channel_hints` merge onto the matching channel objects (membership and duplicates
    were already enforced by `_plot_findings` at validation time).
- **The projection validates nothing and invents nothing.** Its input type is
  `ValidatedPreviewInputs` (frozen dataclass, produced only by
  `load_validated_preview_inputs` after a clean report) — an unvalidated manifest is
  structurally unrepresentable as its input. It reads already-validated structure; it is
  not a second copy of `_plot_findings` semantics. This is the design's answer to the
  "third implementation" drift risk that killed option (a).

### 3.3 Previewability relaxation (SDK)

`_variable` becomes `_observation_value_variable(target)`:

- Observation targets may carry `{value}` or `{receipt_time, value}` — the value variable
  is the single non-receipt-time scalar; at most one receipt-time scalar (number, s).
  Both shapes feed baselines and author fixtures (unit/type checks run against the VALUE
  variable). This is precisely the shape `_target_findings` already admits, so the
  preview stops being stricter than the contract in a way that blocks the contract's own
  canonical plot.
- `generate_baselines` SKIPS non-observation targets (dataset / configuration /
  procedure): they contribute no synthetic observations. Today they kill the preview;
  after, the preview serves with the plugin's observation surface — a disclosed
  degradation replacing a hard failure. Author fixtures referencing non-observation
  bindings still refuse (`preview_unsupported_shape`) — the snapshot data model cannot
  express them.

### 3.4 The renderer seam (ui)

- New `ui/src/preview/PreviewPlots.tsx`: renders one `EngineeringPlot` per decoded
  `plot_view`. A pure join function `plotTraces(view, scenario)`:
  - `observation = scenario.observations.find(o => o.binding_id === view.binding_id)`;
  - feedable iff the observation exists and its value is a finite number;
  - one trace per channel: `{id: variable_id, label: prettify(variable_id),
    unit: channel.unit ?? "", values: [[0, value]]}` — a single point, honestly: the
    preview data model is one simulated value per binding per scenario, NOT observation
    history. The panel carries the standing disclosure line: "Preview scenarios carry
    one simulated value per binding — not observation history."
  - the hints `ReadonlyMap` is built from channels carrying `color_role`/`visible`.
- Zero feedable channels (waveform/dataset plots, loading/disconnected scenarios): the
  figure STILL renders — structure, axes, legend — with a visible "no preview data"
  row. A declared plot is never silently dropped (the C2 no-laundering principle applied
  to whole plots: "no data rendered" must not be laundered into "no plot declared").
- **No threshold is passed.** `$defs.plot` carries none; row-C pinned that hints never
  touch the threshold; the preview must not fabricate a limit line. The workbench's
  hardcoded threshold stays where it is — `DeviceWorkbench` is host chrome and is
  unchanged by this slice. For a plot-declaring plugin the preview will show both the
  host workbench plot and the plugin's declared plots, each labeled; consolidation is a
  product call recorded as a deferral, not taken silently here.
- `PreviewApp.tsx` renders the panel from the decoded document. The two-pass
  composition contract is untouched — `EngineeringPlot` is consumed as-is.

### 3.5 FC6 drive-by (EngineeringPlot)

1. **Unify the token read source.** Both the legend and the chart resolve tokens from
   the component's own root (`<figure>` ref) — the subtree that inherits the active
   theme whichever ancestor carries `data-theme`. The legend styles move from a
   render-time `useMemo` to state set in a layout effect keyed
   `[traces, hints, threshold, themeVersion]` (refs are not attached during render, so
   the read must happen post-attach). This also fixes the switch-independent gateway-app
   manifestation (legend always light) as a side effect — a behavior change, pinned by
   test, disclosed here.
2. **Reactive trigger.** A `MutationObserver` (`attributeFilter: ["data-theme"]`) on the
   element's closest `[data-theme]` ancestor (falling back to `documentElement`, deduped
   when identical — covers both the `App.tsx` and `PreviewApp.tsx` shapes) bumps a
   `themeVersion` state; the legend resolution and the chart effect both gain
   `themeVersion` as a dep. The chart re-renders through the existing effect path
   (dispose/re-init) — rare event, one code path; no `setOption`-diffing variant is
   invented.
3. jsdom supports `MutationObserver`; token VALUES are supplied by the established
   `vi.stubGlobal("getComputedStyle", ...)` idiom (`EngineeringPlot.test.tsx`
   `stubMutedToken` — "jsdom's getComputedStyle returns no custom properties"), so the
   RED check does not depend on jsdom CSS-variable support.

### 3.6 Scaffold example (SDK)

`create_ui_resources` (`presentation.py`) gains: the receipt-time variable on its first
observation target, one `time_series` plot (with a `channel_hints` entry) on the
readings page, fixture/guide text at the new `0.1.1` const, and the generated
conformance test asserting `plot_views` is present and non-empty. Every new plugin then
ships with a working plot example, and the sdk-smoke path exercises the projection
end-to-end. This is the one item cuttable under scope pressure — the projection is
proven by main-side tests regardless.

---

## 4. Precedent (principle 9 — extend proven mechanisms)

| Mechanism reused | Precedent |
| --- | --- |
| Copy-never-move PATCH bump, frozen old tree, `source`-cited corpus rows, consts move in the copy | OTDP 0.1.0→0.1.1; plugin-ui 0.1.1 (row C §2.2); registry 0.1.1 |
| Additive-optional-field PATCH class | interface `approver_token` (`GOVERNANCE.md` change-class table) |
| Served-document model + `to_document` + two-side schema conformance | `preview_models.PreviewModel`, `ui/src/preview/wire-schema.test.ts`, `tests/sdk/test_preview_fixtures.py` |
| Catalogue indexing + deterministic preview model build | `fixtures.py` `_target_index`, `generate_baselines`, `build_preview_model` |
| Hint composition under host theme authority (consumed, not changed) | `EngineeringPlot` two-pass `resolveStyles`; row-C §2.4 + C1–C4/W1/W2/FC1–FC4 rulings |
| Unmocked real-echarts render tests as the bar for renderer claims | `EngineeringPlot.render.test.tsx` (FC1) |
| `getComputedStyle` stub idiom for token-dependent assertions | `EngineeringPlot.test.tsx` `stubMutedToken` |
| Disclosed degradation over silent drop | `unavailable_pages` posture; the C2 threshold carrier ("no limit plotted" never laundered into "no limit configured") |
| Server-side projection of trusted metadata into a typed wire field | the pages/scenarios projection `build_preview_model` already performs |

New architecture invented: none. The genuinely new decisions are (i) the projection
shape (`plot_views`) — justified by the authority split and the no-TS-mirror argument —
and (ii) the `_variable` relaxation — justified by `_target_findings` already admitting
the shape the preview refused.

---

## 5. Cross-surface sync list (everything that moves)

**Main repository** (one working branch; design record is commit one, per the #62
precedent; commits land main-side first):

1. `standards/plugin-ui-preview/0.1.1/` — new: both schemas (copied, edited in copy).
2. `standards/plugin-ui-preview/0.1.0/` — untouched (verify by corpus pin, not by eye).
3. `standards/standards-manifest.json` — plugin-ui-preview → 0.1.1, `supersedes`,
   normative paths.
4. `standards/corpus-manifest.json` — via `repin` only: +2 machine rows.
5. `docs/compatibility-matrix.md` — regenerated (`benchweave.standards matrix`; the
   plugin-ui-preview row at `:19` moves 0.1.0 → 0.1.1).
6. `docs/project-index.md:22` — the fixture-schema link repoints to 0.1.1.
7. `ui/src/preview/wire-schema.test.ts` — schema import path → 0.1.1; sample document
   gains a `plot_views` case; poisoned-plot_views arms (unknown `color_role`, extra
   channel key) rejected by Ajv AND the decoder.
8. `tests/sdk/test_preview_fixtures.py` — `FIXTURE_SCHEMA`/`DOCUMENT_SCHEMA` paths
   (`:16-17`) and the `$id` assertion (`:82`) → 0.1.1; `author_fixture()`'s
   `contract_version` → 0.1.1; served-document conformance case extended to assert
   `plot_views` validates.
9. `ui/src/preview/api.ts` — decode `plot_views` (typed error codes
   `preview_invalid_plot_view` / `..._channel` / `..._axis`), optional field.
10. `ui/src/preview/PreviewPlots.tsx` — new composition + pure join.
11. `ui/src/preview/PreviewApp.tsx` — render the panel.
12. `ui/src/components/plots/EngineeringPlot.tsx` — FC6 fix (§3.5).
13. `ui/package.json` — `0.1.1` → `0.1.2` (FC5 ruling: behavior-changing renderer
    refresh bumps the version `renderer_version` stamps from).
14. ui tests/stories: PreviewPlots component tests, EngineeringPlot theme re-resolution
    tests (mocked option-level + unmocked render-level), a hinted manifest-plot story;
    existing PreviewApp tests updated.
15. Version-literal sweep of `tests/sdk/test_preview_server.py`, `test_preview_cli.py`
    (census below — none expected beyond the files above).
16. `docs/device-developer-guide.md` — presentation/preview section: manifest plots and
    hints render in the preview; preview values are per-scenario snapshots, not history;
    unfeedable plots render a no-data disclosure (obligation #3).
17. `docs/internal/drift-and-obligations.md` — **obligation #12 activates**: the
    reserved row becomes the UI/preview-renderer doc-home row (proposed text in §6).
18. New tests per §8.

**SDK repository** (`packages/sdk` — commit and PUSH there first; SDK PR opened at
pointer-commit time, stacked if a predecessor is in flight — never end-of-run):

19. Vendored tree via `benchweave-sdk sync-standards .standards-bundle`:
    `src/benchweave_sdk/standards/plugin-ui-preview/0.1.1/*`; `standards-lock.json`.
20. `fixtures.py` — `_schema_path` → 0.1.1 (checkout fallback path at `:47`); the
    `_variable` relaxation (§3.3); `project_plot_views`; `build_preview_model` wiring.
21. `preview_models.py` — PlotView family + `PreviewModel.plot_views` + `to_document`.
22. `presentation.py` — `_preview_fixture` `contract_version` → 0.1.1; scaffold plot
    example (§3.6); UI-GUIDE text.
23. `packages/sdk/src/benchweave_sdk/preview_assets/` — rebuilt renderer committed with
    the SDK change (the ui job's freshness gate fails on any diff; renderer_version
    reads 0.1.2 from the rebuilt inventory).
24. SDK user-guide prose (`user_guide/plugin-sdk.qmd` and generated site copies): the
    standard is referenced version-free as "plugin-ui-preview-v1" (census-verified — no
    literal to move); add one sentence that previews render declared plots and hints.
25. Main repo: submodule pointer commit after the SDK push.

**Generated artifacts NOT hand-edited:** `packages/sdk/.docs-assembly/`,
`_great_docs_build/`, `site/`, `great-docs/` (regenerated); the stale linked worktree
under `.claude/worktrees/issue35-fold` carries duplicate matches and is out of scope.

**Obligations walk** (`docs/internal/drift-and-obligations.md`): #3 yes
(device-developer guide — plugin-visible preview behavior); #6 yes (vendored bytes +
repin + `make check-sdk-standards`); #7 yes (pointer push-first + renderer freshness);
**#12 activated by this change** (the row lands with the surface, per its own
principle); #1/#2 no (no MCP tool, no openapi — plugin-ui-preview is not the interface
standard); #5 no (registry fixture lattice untouched); #8 no (adapter surface
untouched); #13 no (plugin-ui-preview has no validation-report family member; the
family's plugin-ui exclusion is unchanged).

**CI cost:** no new jobs. `gates` (repin/export/check, SDK-sync lanes), `ui`
(typecheck/lint/tests/freshness gate) and `package` run as today; the freshness gate's
`preview_assets` diff is satisfied by item 23, in-arc.

---

## 6. Minimal first increment — and what it DEFERS

**Increment 1 ships:** the plugin-ui-preview 0.1.1 bump with `plot_views` (§3.1); the
projection (§3.2); the previewability relaxation (§3.3); the preview plot panel with
honest snapshot data and no-data disclosure (§3.4); the FC6 fix (§3.5); the scaffold
plot example (§3.6); obligation #12's row; the device-developer-guide section; the full
sync list §5; both repos green.

**Obligation #12 row (proposed text, landing in `drift-and-obligations.md`):**

> 12. **The UI/preview renderer surface** (ui components + compositions, the SDK preview
> stack, and the served wire document) → plugin-visible rendering behavior:
> `docs/device-developer-guide.md` (presentation section); component behavior: the ui
> component tests and Storybook stories; the wire shape:
> `standards/plugin-ui-preview/<active>/preview-document.schema.json`, conformance-tested
> from both the Python emitter and the TS decoder. The renderer freshness gate
> (obligation 7) carries the committed `preview_assets` half.

**Deferral table** (per the amended 2026-09-20 rule: at most one follow-on issue per
merged PR — this slice needs ZERO; every deferral lives here with its reopen trigger):

| Deferral | Reopen trigger |
| --- | --- |
| Legend re-show interaction (hidden rows disclosed but not clickable) | an interactions increment is commissioned |
| Per-user / persisted visibility overrides outranking author hints | a host user-state model exists |
| Wider colour-role vocabulary beyond {accent, muted} | the host palette exceeds two trace colours |
| Waveform/dataset preview DATA (vector values in the fixture model — makes dataset plots feedable) | plugin-ui-preview gains a vector values shape; until then waveform views render structure + no-data disclosure |
| Consolidating the host workbench's synthetic plot with plugin plots in the preview | product call on the preview's information architecture |
| Gateway host UI consuming manifest plots beyond the preview | the gateway UI grows a plugin-page surface |
| Multi-plot page layout beyond simple stacking | a real manifest declares >1 plot per page and stacking proves wanting |

---

## 7. Invariant impacts

- **CTL/STO/REG: untouched.** No control, state, or plugin-lifecycle code changes; the
  preview path remains simulation-only with no gateway, registry or hardware reach.
- **CON-2** (pin lattice): +2 corpus rows via repin with `source` provenance; the frozen
  0.1.0 rows remain (pinned by `tests/standards/test_repin.py` superseded-row
  verification); registry fixture lattice untouched.
- **CON-4** (packaged-first vendoring): SDK lock/tree/stamps move only through
  sync-standards; `make check-sdk-standards` stays green.
- **CON-7** (repin is the only pin writer): no hand-spliced digests anywhere.
- **CON-8**: no identity event (plugin-ui-preview not an identity key —
  `src/benchweave/standards/manifest.py:13`).
- **No new invariant row is proposed.** The renderer-side guarantees this slice relies on
  (index stability, no-cascade) are already pinned as ui component tests by row C; the
  new "projection reads, never validates nor invents" property is structural (frozen
  `ValidatedPreviewInputs` input type) plus metric A — a component-level guard, not a
  cross-cutting mechanism, following the row-C §6 precedent.

---

## 8. Measurable proof — pre-committed acceptance rule

Written before any number below was looked at. All counts are this design's own
commitments, measured by the named tests. The RED arms for metrics B, C, D must be
DEMONSTRATED FAILING (for the stated reason) before the GREEN implementation is claimed
— a RED arm that cannot be made to fail means the measurement, not the feature, is
broken.

**Metric A — projection coverage and fidelity (Python).** Corpus: four manifest shapes —
(1) the manifest-bundle time_series (single y, receipt_time x —
`test_presentation_manifest.py` bundle), (2) `scope_specimen` waveform (dataset, 1 y),
(3) `multi_channel_specimen` waveform (2 y), (4) shape 1 with `channel_hints` on its y
channel. `project_plot_views` must yield exactly one view per declared plot (4/4), each
carrying kind/binding_id/title/x{label,unit}/channels with channel count == len(y) and
units from the catalogue; the hinted pair (4 vs 1) may differ ONLY in the hinted
channel's hint fields.
**Ship:** 4/4 exact. **Kill:** any missing/extra view or any field mismatch. **Underpowered, not conclusive:** if the corpus lacked a multi-y plot at measurement time, equivalence would be unproven for the multi-channel case — shape 3 exists precisely to prevent that; do not delete it to make a failure disappear.

**Metric B — end-to-end render, RED and GREEN (browser, UNMOCKED echarts per the FC1
bar).** Fixture document: one `plot_view` (time_series, one channel, muted hint) + one
scenario with a numeric observation for the binding. GREEN: exactly 1 `.bw-plot` figure
renders; the real SVG/legend contains the channel row (`{variable} · V`) and the
muted-token colour. RED: remove `plot_views` from the served document → 0 figures
render (the mechanism is the only path to a plot).
**Ship:** GREEN 1/1 and RED 0/1. **Kill:** the RED arm renders a plot anyway. **Underpowered:** an assertion satisfied by a mock recording `setOption` without rendering does not count — the unmocked file is the bar for this metric.

**Metric C — hint transport, RED and GREEN.** Two documents identical except the
hinted channel's `color_role`: hinted resolves to the stubbed muted token; unhinted
resolves the pass-1 accent. RED: strip the hint fields in the decoder join → hinted
renders accent → fails.
**Ship:** 2/2 documents, both directions. **Kill:** either document's resolved colour is wrong or hint-removal changes anything else. **Underpowered:** if the muted token is absent from the stub (falls back per C4), the test proves nothing — the stub must supply the token.

**Metric D — FC6 theme re-resolution, RED and GREEN.** `getComputedStyle` stubbed to
return theme token values keyed off the element's closest `[data-theme]` (light accent
`#0b7181`, dark accent `#42cee2`): render; assert the light resolution (option payload
axis/series colours AND the unmocked SVG); flip the container's `data-theme` to dark;
assert re-resolution to the dark tokens in a fresh `setOption` and in the rendered SVG.
RED (the bug): no second resolution occurs — colours stay light. Control: with no
attribute flip, the option payload is stable (no spurious re-resolution churn).
**Ship:** flip pair + control, all three asserted. **Kill:** the flip produces no new resolution, OR the control shows resolution churn without a cause. **Underpowered:** a stub not keyed to the DOM attribute would decouple the input from the mutation — the test must flip the DOM, not the stub.

**Metric E — previewability relaxation (Python).** (i) The two-variable observation
target (receipt_time + value — the manifest-bundle shape) builds a preview model without
`preview_unsupported_shape`, baselines generated from the value variable; (ii) a
vector-variable dataset target no longer kills the preview: baselines skip it and
`project_plot_views` still projects its waveform plot; (iii) an author fixture
referencing a dataset binding still refuses.
**Ship:** 3/3. **Kill:** any of the three behaves differently. **Underpowered:** (ii) without an asserted waveform view would only prove "no crash", not disclosed degradation — assert the view exists.

**Metric F — wire conformance, both sides.** The emitter's document (scaffold plugin
with plots) validates against the 0.1.1 schema from Python
(`test_preview_fixtures.py`) and the TS decoder+Ajv agree on a valid sample and on
poisoned `plot_views` (unknown `color_role` rejected by both).
**Ship:** 2/2 sides × {valid passes, invalid rejected}. **Kill:** either side disagrees with the schema.

**Overall pre-committed rule:** SHIP only if A–F are all green AND the B/C/D RED arms
were shown failing first. KILL the increment if any RED arm cannot be made to fail, or
any GREEN arm fails, or metric A's hinted-pair equivalence breaks. A metric that passes
for the wrong reason (wrong code, mock-only satisfaction, stub not coupled to the DOM)
is an UNDERPOWERED measurement: fix the measurement and re-run — never rationalize the
number.

---

## 9. Top risks, each with its falsifier

1. **The projection drifts into a second validator.** It must read, never check. If a
   reviewer finds validation logic (findings, refusal codes) in `project_plot_views`,
   the design is violated — fold the check into `_plot_findings` (plugin-ui) instead.
   Structural guard: the input type is `ValidatedPreviewInputs`.
2. **Schema-bump ripple missed.** The census (§5) was made by repo-wide search on
   `4d06960`; 91 raw matches reduce to the listed surfaces once generated artifacts and
   the stale worktree are excluded. Falsifier: `make check-sdk-standards`,
   `matrix --check`, the SDK sync lanes, and a review-time grep for
   `plugin-ui-preview/0.1.0`.
3. **Snapshot data mistaken for history.** Single-point traces on a receipt-time axis
   could read as a trend. Mitigation: the standing disclosure line (§3.4), x label
   naming receipt time, and the device-developer-guide section. Falsifier: preview
   review by the maintainer; if the disclosure is judged insufficient, add the
   history-shaped fixture model (the deferred vector-values trigger) rather than
   fabricating trends.
4. **FC6 MutationObserver gaps** (env without MutationObserver; theme attr on an
   unobserved ancestor). Falsifier: metric D's RED arm; the fallback ancestor
   (`documentElement`) plus the closest `[data-theme]` covers both in-tree app shapes —
   a third shape would need its own test.
5. **Renderer freshness gate trips late** — the `preview_assets` refresh discovered in
   CI rather than in-arc. Named in §5 item 23 so it is committed with the SDK change
   (row-C risk 6, same mitigation).
6. **Baseline scenario content change** (non-observation targets now skipped instead of
   fatal). Existing pinned baselines use all-observation catalogues and are unaffected
   (cited: `test_preview_fixtures.py` `catalogue()`); mixed catalogues were un-previewable
   before, so no pinned expectation can move. Falsifier: any existing preview test whose
   observation tuples change.
7. **Standards-train collision** — another PR bumping plugin-ui-preview in the same
   merge window. None queued today; if one appears, batch per the bump-minimization rule
   (highest class wins, one copy step from the live predecessor).
8. **The fixture-const flip strands external author fixtures** declaring 0.1.0. Bounded:
   the preview fixture surface is SDK-tooling-local (loopback, simulation-only), the
   compatibility matrix renders "Supersedes 0.1.0" automatically, and the migration is a
   one-line const edit. If external breakage proves larger than acceptable, the fallback
   is dual-version acceptance in `load_author_fixtures` — a deliberate governance
   change to commission separately, not a patch here.

---

## 10. DON'T-BUILD assessment

Not triggered. The mechanism extends proven in-tree patterns on every axis (§4), touches
no control path, and is measurable with non-gameable RED checks (§8). The stop-conditions
were checked and cleared:

- *Could the preview render plots at all without a new data model?* Yes — single-channel
  time_series plots are feedable from per-scenario snapshot values once `_variable` stops
  refusing the contract's own canonical target shape; the relaxation is evidence-backed
  (§1.1), not invented capability.
- *Is the transport honest?* Yes — server-side projection keeps host metadata
  server-side, plugin hints as projected preferences, and adds no third implementation
  of plot resolution.
- *Would a DON'T-BUILD have been warranted if preview data could not feed any plot?*
  Yes — if the only previewable shapes had been dataset/waveform plots (no data model),
  rendering them would have required fabricating data or shipping empty charts as a
  "feature", and the honest answer would have been to defer until a vector fixture model
  existed. The observation time_series case is what makes the slice real.

---

## Amendment 2026-09-21 — review-wave corrections (governor / reviewer / refute / RedTeam)

Appended, not rewritten, per the invariants-file convention. These corrections carry the
same authority as the body; where they contradict it, they win.

1. **§3.2's "structural guard" is overstated (refute Finding 2, LOW).**
   `ValidatedPreviewInputs` is a public constructible dataclass: `_load_ui_candidate`
   builds it before validity is known, the CLI re-constructs it via `type(candidate)(...)`
   for the fixtures override, and the metric tests construct it directly. The guard is
   call-site discipline — the sanctioned path (`load_validated_preview_inputs`) gates on
   a clean report — not structure. The input-type convention still earns its keep (it
   makes the discipline the path of least resistance); the claim no longer says
   "structurally unrepresentable."
2. **§5's single matrix regeneration is wrong sequencing (governor ruling).** The matrix
   derives its SDK column from the submodule's `standards-lock.json`, so it regenerates
   at BOTH the standards commit (row moves; SDK column stays at the then-pinned lock —
   0.0.2 at `1553d4f`) AND the pointer commit (SDK column moves — 0.0.4). Each commit's
   committed matrix equals a fresh render of its own tree; a bisect never sees a lying
   matrix. The design's implied one-shot regen would have left the standards commit
   failing `matrix --check`.
3. **Claim scoping on "a renderer consumes the model" (RedTeam PT-2).** What renders FED
   this slice is the single-channel time_series path — decoding, projection, join,
   composition. Waveform and multi-channel views render structure-plus-disclosure; their
   semantics stay doctrine until the deferred vector-values fixture model exists. The
   honest close-out phrase is "the plot model is rendered," not "validated" in full.
   Corollaries: the TS decoder + Ajv ARE a second, bounded, conformance-pinned SHAPE
   mirror — only RESOLUTION stays single-language; and in a loopback preview the
   authority-split framing of §2 is rhetoric (one principal on both sides) — the
   drift/pinning leg is what actually carried the fork decision.
4. **§3.4's snapshot datum (RedTeam PT-2, recorded).** `values: [[0, value]]` places the
   single point at x = 0 on a receipt-time axis — an arbitrary-but-labeled datum,
   disclosed by the standing line. The no-fabrication principle this design states is
   scoped to thresholds and severity; kept as-is, recorded so the scoping is visible.
5. **The PATCH class stands (governor, COMPLIANT).** The fixture-const flip's document
   incompatibility was weighed against the OTDP tightening→MINOR precedent; the ruling
   follows the row-C/plugin-ui-0.1.1 in-tree precedent (versioned documents declare
   their version; old documents stay valid against the frozen old tree) — a version-key
   mechanism, not a validation-semantics tightening.
6. **§3.6's scaffold example pinned to `targets[0]` — reproduced HIGH, fixed (refute).**
   The scaffold emitted a plot its own check-ui rejected whenever the descriptor's
   first readable parameter was bool or string (`targets[0]` selection vs
   `_plot_findings`' number/integer axis rule); the committed tests covered only the
   float-first starter — the coverage gap that let it ship. Fixed at SDK `4263cc3`:
   plot target selection is the first observation target whose value variable is
   number/integer (the validator's own test), with the receipt-time axis and the hinted
   plot bound there; a descriptor with no numeric observation target ships no example
   plot (no `plots` key, a conditional generated conformance assertion, and a UI-GUIDE
   disclosure). RED: 3/3 new tests failed against `168cefb` (bool-first, string-first,
   all-non-numeric); GREEN at `4263cc3`.
