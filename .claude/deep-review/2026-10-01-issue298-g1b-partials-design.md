# G1b — partials and canonical artifacts (issue #298, PRD 12 G1 partials slice)

**Status:** design record, 2026-10-01 · **Base:** main at `be294d3` · **Parent records:**
G1a `2026-10-01-issue297-g1a-contract-gate-design.md` (harness, registry, manifest),
G1c `2026-10-01-issue299-g1c-proofs-design.md` (decimate.py, proofs; §9 fork 1 ruled to
G1b: the reading-tile CSS pins). **PRD anchors:** UR-01, UR-07, UR-11, UR-12; §9 Q5;
§10 G1 row; R-1's red half already proven by G1a.

## 0. What G1b is, in one paragraph

G1a landed a fail-closed gate: 28 pin items (parse integrity) and 168 row items
(one per contract body row) that all RED today with `no canonical artifact for
<row-id>`, because `registry.REGISTRY` is empty and `evaluate_row`
(`packages/ui-html/src/benchweave_ui_html/registry.py:120`) refuses an unregistered
row. G1b makes 158 of those rows green by registering one canonical artifact per row,
backed by real Jinja partials (UR-01), a server-side plot-computation module whose
output is emitted as data attributes (UR-07), inline-SVG icon partials (UR-12), and
G1a's own `tokens.py`/`roles.py` mechanisms for the token and role rows. Ten
`rule_proof` rows — the §B.2/§B.4/§C.1 behaviour rules — are named deferrals to the
G1d compositions slice (R-3's ported proofs). No `standards/` byte moves, no
`ui-contract.md` byte moves, and the React tree stays exactly as it is (deletion is
G1e, gated on the FULL 168).

## 1. Mechanism

### 1.1 The artifact/fixture architecture (one canonical artifact per row)

Everything lands in `packages/ui-html/src/benchweave_ui_html/` (wheel packaging rides
the existing `[tool.hatch.build.targets.wheel] packages = ["src/benchweave_ui_html"]`):

| New module | Owns |
| --- | --- |
| `items.py` | The §E micro-syntax parser (Authoring rule, ui-contract.md:22-34): split an attribute/role/class-hook/required-text cell on ` ~ `; parse `name`, `name=value`, `name~=substring`; a `name=value` value containing a quote or backslash **fails loud** (the authoring rule excludes them — a parser that silently mis-issued such a selector would be a silent pass upstream). |
| `assertions.py` | HTML assertions over the rendered string, stdlib `HTMLParser`: root-element check (first start tag), attribute present/`=`/`~=` items, class-hook containment over any element's `class`, required-text substring over decoded text. Roles go through G1a's `roles.ImplicitRoleResolver` (UR-05's G1a authority). |
| `data.py` | Frozen plain-data dataclasses, one per component (`ButtonData`, `ReadingData`, `PlotData`, `LaneCapture`, …) — UR-01's "plain data, never host objects". Closed enums as `Literal` (reading state, lane state, provenance kind) so bad states are unrepresentable rather than validated. |
| `env.py` | `Environment(loader=PackageLoader("benchweave_ui_html", "templates"), autoescape=True, undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)`, built by a module-level factory (strict-undefined = a partial called with missing data reds loudly, never renders a hole). |
| `templates/` | One Jinja file per §E.1 component (`button.j2` … `confirm-action.j2`), `refusal.j2`, `disabled-label.j2`, `icon/*.j2` (10), `sequence/*.j2` (dash-2 + 8 symbols; dash-1 is the no-dasharray default). Under `src/` so the existing wheel config ships them; a test pins the template directory's contents via `importlib.resources` (packaging guard). |
| `partials.py` | `render_button(data: ButtonData) -> str` etc. — typed functions, dataclass in, HTML string out. |
| `plot.py` | UR-07 server-side computation: `assign_slots` (bytewise sort, `((i mod 8)+1)`, dash/symbol wrap at 8), `assign_axes` (§E.2.3: trimmed-unit exact-match grouping, 1/2/>2 cases, visibility filters after), `resolve_hints` (§E.2.0 pass-2), reference-line binding, acquisition counts, provenance markers. Pure functions in, an emit-model out. |
| `lanes.py` | `digital-lanes` composition over G1c's `decimate.reduce_lane`: lane rows, bus lanes (§E.4.3), decoder spans (§E.4.6), trigger/cursor/axis model (§E.4.5). |
| `fixtures.py` | The canonical fixture instances (one per row's needs), values taken from the contract's own canonical literals (§E.1 Notes) and the React compositions as semantic reference only — the contract rows are normative. |
| `artifacts.py` | The 14 artifact classes (one per registry kind) + `ensure_registered()` (idempotent: no-ops once the sentinel row-id `§E.1 Components::button` is present; duplicate registration is already refused by `ArtifactRegistry.register`). |

The harness hook: `contract_harness/plugin.py:ContractFile.collect` currently parses,
orphan-checks, yields. G1b inserts `artifacts.ensure_registered()` **after** the parse
and **before** the orphan check — so the orphan check (F1 fold) polices the
registrations it is about to consume. Import direction keeps UR-11: the plugin (a
pytest11 entry point, inert outside pytest) imports `artifacts` → `partials` → `env` →
jinja2; a host importing `benchweave_ui_html` for rendering imports jinja2 (a declared
runtime dep, `packages/ui-html/pyproject.toml:14-17` — already declared by G1a, G1b
only wires the import; **no dependency is added or re-pinned, uv.lock does not move**)
and never pytest. Jinja2/MarkupSafe are the declared set per UR-11; this slice is
wiring, not new dependencies.

### 1.2 Which kinds G1b registers — and the named split

Registration is per row-id `<table-slug>::<key-cell>` against the manifest's ordered
keys (`manifest.py` — these, not a recount, are the row-ids). By kind:

| Kind | Rows | Satisfied by |
| --- | --- | --- |
| `component_render` | 11 (§E.1) | Canonical partial render; `satisfies(row)` splits the row's own attribute/role/class/text cells via `items.py`, asserts via `assertions.py`+`roles`. Canonical fixtures follow the §E.1 Notes: reading-tile renders WITH the limiting state and set evidence (the all-modes precedent), mode-banner renders all four modes, engineering-plot is the 100→2 voltage decimation, digital-lanes the 1000→12 capture at 1 MHz, confirm-action carries the exact armed literals incl. `PSU-07 output` (an invented name that is the contract's own canonical literal). |
| `refusal_render` | 15 (§C.3) | `refusal.j2` per code. The fixture chooses the code; the assertions compare the rendered severity/what-happened/sent-status/operator-action against **the parsed row's own cells** — the row is the data, so fixture-text drift from the contract is structurally impossible. `no-response` renders sent status `UNKNOWN` (A06). |
| `label_render` | 5 (§C.2) | `disabled-label.j2`: asserts `data-bw-disabled-reason="<key>"`, visible `data-bw-disabled-label` text (not aria-only); `device-state` canonical parameter `idle` → `Device must be idle`. |
| `token_pair` / `token_value` | 25 + 10 (§A) | Thin artifacts over G1a's `tokens.theme_colour_mismatches` / `token_value_mismatches` scoped to the single row. The CSS path constants stay pointed at `ui/src/styles/` until G1e's re-point (G1a deferral D3 discipline). |
| `severity_row` | 6 (§B.1) | Alert-bubble canonical fixture per severity: `data-severity`, live-region role per the row's Live-region cell (`alert` for critical/trip, else `status`), dismiss affordance present iff the Dismissal class is `dismissible`. |
| `mode_row` | 4 (§D.1) | All-modes banner fixture; per row: entry `data-bw-mode="<mode>"` + the fixed wording text (from the row cell). |
| `state_row` | 1 (§B.3 `limiting`) | The canonical reading-tile fixture: `data-bw-reading-state="limiting"`, visible `Limiting` label in `bw-reading__state`, and the negative arms — no `alert` role, no dismiss affordance (never an alert-bubble pattern). |
| `triad_row` | 3 (§E.3) | measured/set/staged placements: `Set {value} {unit}` in `bw-reading__set` with `data-bw-reading-role="set"`; `Staged` only in the staging inputs; staged text absent from the tile. |
| `slot_value` | 16 (§E.2.1) | `plot.py.assign_slots` over a canonical 16-id declared set; the slot-i row asserts its legend row's emitted triple equals the row's Colour/Dash/Symbol cells. |
| `hint_row` | 4 (§E.2.0) | Pass-2 resolution over canonical hinted sets; asserts the Effect cell's consequence (accent→`--bw-series-1` repaint with slot-1 first-claim, muted→`--bw-text-muted` fallback, `visible:false`→`data-hidden` with slot unchanged, no-hint→slot attrs). |
| `sequence_partial` | 10 (§E.2.2) | Renders the dash/symbol SVG fragments; asserts structure (dash-1 no `stroke-dasharray`, dash-2 has one, symbols are geometry) **plus injectivity**: the 10 renders are pairwise distinct bytes — the copy-paste-icon failure class dies here. |
| `icon_partial` | 10 (§F.1) | Hand-authored minimal geometric SVG from §F.1's shape descriptions (any icon set can bind from the descriptions; the lucide names are the reference binding, and **no lucide path data is copied** — geometry is authored, keeping provenance clean). Asserts class hook (`severity`/`state`), `aria-hidden="true"` beside text, non-empty viewBox+shape, and the same 10-way injectivity. |
| `rule_proof` | **38 of 48** | See the split below. |

**The rule_proof split (the design's one real scoping decision).** 48 rows carry kind
`rule_proof`. G1b registers the 38 whose rule is a property of a single component's
rendering computation, provable on a canonical fixture without behaviour composition:

- §E.2.3 y-axis (4), §E.2.4 reference lines (4), §E.2.5 acquisition (3), §E.2.6
  provenance (4) — pure `plot.py` functions asserted through the emitted vocabulary.
- §E.4.1 layout (4), §E.4.2 states (4), §E.4.3 buses (4), §E.4.4 decimation (3 — the
  partial's emitted columns equal `reduce_lane`'s output for the canonical capture;
  G1c already property-proves the function itself), §E.4.5 axis/trigger/cursors (4),
  §E.4.6 decoder lanes (4) — `lanes.py` structure over the canonical capture.

The 10 deferrals to **G1d** (R-3's compositions lane): §B.2 SR-B1/B2/B3, §B.4
ST-1/ST-2/ST-3/ST-4, §C.1 R-ENERGISE-1/R-DEENERGISE-1/R-PROTECT-1. These are behaviour
rules across components and time (where a message may appear; the staleness predicate
and cadence semantics; the confirm guard **at fire time**, including a guard arriving
while armed). Satisfying them in G1b with single-fixture structure checks would be
prose-laundering — asserting that rule text renders — which the acceptance rule
explicitly kills. They stay red with the honest `no canonical artifact` message until
G1d's compositions land; the G1 exit gate ("green on every pinned table") is therefore
met at G1d, not G1b. This split is disclosed on the tracker so red rows read as
deferral, not breakage.

### 1.3 The UR-07 plot wrapper — emitted vocabulary, no draw claims

`engineering-plot.j2` renders the **semantic skeleton**: `figure[role=img]` +
`bw-plot__canvas` (empty hydrate target) + the visible Traces legend whose rows carry
the computation's output, + `bw-visually-hidden` chart description + the
`bw-plot__acquisition` line. The chart library (ECharts 6.1.0 initially, Q12-swappable)
hydrates later **from these same attributes** — one source of truth, and the harness
asserts attributes, never pixels. Vocabulary emitted by `plot.py` (each name is
asserted by at least one row):

- per legend/trace row: `data-bw-series-slot="N"` (pass-1), `data-bw-resolved-series`
  (pass-2 post-hint colour), `data-line="solid|dashed"` (resolved dash),
  `data-bw-symbol="symbol-N"` (time_series canonical fixture), `data-bw-axis="1|2"`,
  `data-bw-trace-provenance="<kind>"` (marked kinds only), `data-hidden`.
- plot root: `data-bw-axes="unit1;unit2"`; the >2-units refusal renders **no traces**
  plus the `bw-plot__refusal` `role="status"` note (fires only on the declared set);
  `data-bw-acquired` / `data-bw-plotted` back the disclosure text
  `Acquired {n} samples · plotted {m}` (m = drawn count, never caller-supplied).
- reference lines: `data-bw-ref-line` + `data-bw-ref-unit` + dotted/`--bw-border`
  styling hook; renders even when its targets are hidden.

Honest minimal markup: the canvas carries no fake pixels and G1b makes **no
draw-visibility claim** (rubric G-render's line: payload/attribute pins cannot falsify
draw claims — so none are made; geometric realization is asserted in G1d's
axe/screenshot lane). The same posture governs lanes segments: each carries
`data-bw-state` plus `data-bw-state-kind="<high|low|hatch|midline>"`, the monochrome
discriminability residual disclosed rather than pixel-asserted.

### 1.4 The reading-tile CSS pins (G1c deferral-1, ruled to G1b)

New `tests/ui_html/test_reading_tile_css_pins.py` pins
`ui/src/components/readings/reading-tile.css` structure through a module-level path
constant (G1a's `tokens.py` pattern — fail loud if absent): (1) the ordered list of
top-level selector blocks equals the pinned order (S1 fold-row 5); (2) no
glow-carrying declaration (`box-shadow`) in the normal/success blocks (fold-row 11;
SR-B2); (3) `--bw-limiting` is the limiting block's border-colour declaration (label
token). A mutation arm asserts a doctored copy reds all three. The pin **dies with
`ui/` at G1e** unless re-pointed at the vendored asset — recorded as a named G1e
checklist row here (companion to G1c deferral 3's rows), so the deletion cannot lose
it silently.

### 1.5 Harness-suite arms (G1a's meta-acceptance extended)

- **Auto-registration completeness:** after `ensure_registered()`, the registry holds
  exactly the 158 expected row-ids (set equality against a manifest-derived
  expectation — no orphan, no gap).
- **Idempotence:** a second `ensure_registered()` is a no-op (duplicate registration
  would raise).
- **Fail-closed preserved:** with `REGISTRY.clear()`, `evaluate_row` returns
  `no canonical artifact …` for every row — G1a's empty-registry control keeps its
  teeth after the plugin starts auto-registering (the control shape moves from
  collection-level to the pure function, which G1a already isolated for exactly this).

## 2. Root cause / premise check (why this is the right slice)

Verified on the landed surface: `registry.KNOWN_KINDS` already enumerates all 14 kinds
including `sequence_partial`; `KIND_BY_SLUG` already maps all 28 tables; the manifest's
ordered key lists ARE the row-ids; `evaluate_row` already enforces kind match; the
plugin already yields one row item per body row with the orphan check in place. Nothing
in G1a's contract needs to change for G1b — the slice is purely additive registration
plus the partials that back it. The item micro-syntax is normative in the contract's
Authoring rule but has no parser in the landed package (grammar.py owns cells, not
` ~ ` items) — `items.py` is therefore new load-bearing surface, named here as such.

## 3. Minimal first increment and named deferrals

**In (build slices, each with RED evidence per slice, stacked per doctrine):**
1. `items.py` + `assertions.py` + `env.py` + `data.py` + `templates/button.j2` +
   `partials.render_button` + `ComponentRenderArtifact` + plugin registration wiring +
   the one-artifact control + the three meta-acceptance arms. (Proof slice: red→1
   green.)
2. Structural families: panel, data-table, alert-bubble (+`severity_row`),
   mode-banner (+`mode_row`), numeric-input, rotary-control, reading-tile
   (+`state_row`, +`triad_row`), confirm-action, `label_render`, `refusal_render`,
   icons (`icon_partial`), sequences (`sequence_partial`), token artifacts
   (`token_pair`/`token_value`), the reading-tile CSS pins test.
3. Plot lane: `plot.py` + `engineering-plot.j2` + `slot_value` + `hint_row` + §E.2.3–
   §E.2.6 rule rows.
4. Lanes lane: `lanes.py` + `digital-lanes.j2` + §E.4.1–§E.4.6 rule rows. End state:
   158/168 green, 10 named red.

**Deferred, each with its owner:**
- §B.2/§B.4/§C.1 rule_proof rows (10) → G1d compositions (R-3), incl. guard-while-armed.
- Pattern library pages, static export, screenshots, axe (UR-06/09/13) → G1d.
- Chart pixel rendering, host script, vendored assets + inventory hashing (UR-10 /
  G1a D3), htmx/SSE → G1e / PRD 11 lane.
- `ui/` deletion, obligation-12 rewrite, token-path + CSS-pin re-point rows → G1e.
- §F state-key icon bindings beyond the ten §F.1 rows (§F's own note: open binding
  lands with safety-behaviours stories) → G1d.
- Playwright/axe role resolver upgrade behind the `RoleResolver` protocol → G1d.

## 4. Precedent

Extends G1a's own proven mechanisms — the registry protocol, `evaluate_row`, the
plugin's collection shape, `roles.ImplicitRoleResolver`, `tokens.py`'s CSS-by-path
pattern (reused verbatim for the CSS pins), and G1c's `decimate.reduce_lane` (consumed
as-is). The per-row-artifact-with-own-cells-as-data trick follows G1a's design-record
§2 (fail-closed on unknown/unregistered). Jinja partials are new in-tree architecture,
mandated by PRD 12 §9 Q5 + UR-01 — the ruling, not this record, is the justification.

## 5. Invariant, drift, tier

- **Invariants:** no CTL/STO/CON/REG group is touched (no `control/`, `state/`,
  `contracts/`, `registry/` bytes). No new invariant proposed; UR-03's
  rows-cannot-exist-without-implementations gains its positive enforcement half.
- **On-disk formats/schemas:** none changed. `standards/` untouched (no
  standards-governor dispatch). `docs/internal/ui-contract.md` untouched (authoring
  rule: editing it means editing pins in the same change — not this slice).
- **Drift:** obligation 12 unchanged until G1e. The G1c record's §9 fork 1 is
  discharged here; G1e's checklist gains the CSS-pin re-point row.
- **Tier 3 — keyword rule.** Trigger: the expected diff text contains `protection`
  (case-insensitive) — the §C.2 `protection-active` label fixture and its assertions
  (code/tests ≈ 5 occurrences) plus this record's own text (see scan). No path rule
  fires: no `standards/`, no persisted formats, no dependency motion (jinja2/
  markupsafe already declared, `packages/ui-html/pyproject.toml:14-17`), no submodule
  pointer. Consequence: two-lane adversarial refute (Tier-3 doctrine) + cold full
  battery.
- **Keyword scan (Step-1 protocol, whole expected diff — code, tests, templates,
  record):** `protection` = 9 expected (measured: this record itself carries 4 — 3
  lowercase `protection-active` mentions in §5, 1 capitalized `Protection trip
  active` label literal in §1.2, counted 2026-10-01; code/tests estimated 5: the
  label-render fixture key, the visible label text, two test assertions) — final
  count re-run at review over the actual diff. `threading` 0,
  `asyncio` 0, `subprocess` 0, `sha256` 0, `hashlib` 0, `migrate` 0, `recovery` 0 —
  rendering and assertions are pure string work; no hashing ships in G1b (UR-10 is
  G1a-D3/G1e). The review re-derives the scan; a >20% count deviation from these
  numbers is a finding to explain, not a failure by itself.
- **CI cost:** no new job. The ~168 generated items + ~40 unit tests ride the existing
  ui-html gate invocation; no Playwright (G1d).

## 6. Measurable proof — pre-committed acceptance rule

**Population (no sampling — the gate is the population):** 28 pin items + 168 row
items, plus the unit/meta tests. Every count read from `--junitxml` attributes or true
exit codes, never a filtered summary (rtk lesson, OPERATIONAL_RULES).

- **RED half (before any registration, on the branch):** 168/168 row items red with
  `no canonical artifact` — re-proves G1a's R-1 arm on this branch.
- **One-artifact control (the fluff-killer):** registering exactly the button family
  greens exactly `row::§E.1 Components::button` (1 row) and changes no other item.
  Generalized per slice: each family's registration greens exactly its own rows
  (±0 others). A control that greens anything beyond its family = harness leak = KILL.
- **SHIP (all must hold):** 158/168 green; the 10 deferred rows red with exactly
  `no canonical artifact for <row-id>` (the message class is itself asserted — a red
  from `unsatisfied contract items` there means something satisfied-and-failed, i.e.
  a cheap-satisfaction attempt); pin layer 28/28 green; orphan check clean
  (collection succeeds); registration completeness set-equality green; UR-11 boundary
  green (import the package + render one partial per family → `pytest` absent from
  `sys.modules`, jinja2 present); template-packaging guard green; the three mutation
  controls RED when their mechanism is neutralized — (a) drop
  `data-bw-reading-state` from the fixture → the reading-tile rows red naming that
  item; (b) break the dash wrap (i≥8 keeps `dash-1`) → exactly the i=8..15 slot rows
  red; (c) doctor the CSS copy → all three CSS-pin assertions red. Fast lane per
  commit; full battery + both tripwires before push; ruff + strict mypy (fresh cache)
  clean. Re-run the row layer 3× — any flake is a kill.
- **KILL:** any claimed-green row red on re-run; any of the 10 deferred rows going
  green on a structural/prose assertion instead of a G1d composition; any orphan; any
  pin defect; any mutation control that stays green (assertions don't discriminate);
  the one-artifact control leaking; pytest entering the import boundary.
- **UNDERPOWERED (not conclusive):** mutation controls unrunnable (fixtures not
  parameterizable) or the one-artifact control not isolatable — then the 158 count is
  unproven and the slice does not ship on the aggregate alone; fix isolation first.

## 7. Top risks and falsifiers

1. **Silent-pass assertions** — a `satisfies()` weaker than its row's items. Falsifier:
   the per-item failure messages + mutation controls (a)/(b); the review lane re-derives
   one row's item set by hand against the rendered fixture.
2. **Vocabulary drift between `plot.py` emitters and what a future host script
   consumes** (G1e/PRD-11). Falsifier: every emitted name is asserted by ≥1 row
   (slot/hint/axis/provenance/acquisition rows), so any rename reds the harness — the
   single source of truth is `plot.py`'s emit model.
3. **Auto-registration erodes G1a's fail-closed proof** (the empty-registry control
   stops being reachable via collection). Falsifier: the pure-function clear() arm and
   the REQUIRE_ARTIFACT toggle (still the only switch) remain pinned in
   meta-acceptance.
4. **Template packaging works from source, breaks from wheel.** Falsifier: the
   `importlib.resources` contents guard + the existing CI wheel job; if that job
   doesn't install-and-import, add a render smoke there (one line, no new job).
5. **The 10-row deferral reads as breakage** to a contributor running the gate.
   Falsifier/mitigation: the tracker note and this record name the rows and the G1d
   owner; the row names themselves appear in the red output, which is the honest
   state.

## 8. Open items (marked, not searched — time-boxed reading)

- **O1:** the exact shapes of G1a's meta-acceptance controls
  (`tests/ui_html/test_meta_acceptance.py` — not read this session, time budget); the
  three new arms in §1.5 must be reconciled with, not bolted beside, the existing
  controls.
- **O2:** `grammar.Row` field names (`cells`, `row_id`, `table_slug`) are taken from
  their use sites in `registry.py`/`plugin.py`; builder verifies against
  `grammar.py:101` before first import.
- **O3:** React components were skimmed by directory only; the port treats
  `ui/src/components/**` as semantic reference at build time (contract rows normative)
  — deliberate, per the brief.
- **O4:** hatchling ships non-`.py` files under a `packages` target by default;
  confirm with one wheel build in CI (risk 4's guard) rather than trusting this
  record's reading of the build backend.

## 9. Environment note

This design session hit the known gortex daemon state where a stale in-session
localization blocks `read(operation:"file")` for some files
(`error_code: localization_complete … required_action: wait`); reads were completed
via the hook-sanctioned `editing_context` route and file reads that succeeded. Native
Read of indexed `.py` source is hook-blocked in this checkout — expected posture, not
worked around. No gortex discovery ops were run, per the dispatch discipline.
