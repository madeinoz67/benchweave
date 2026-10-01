# G1d — pattern library + the ten behaviour compositions (issue #300, PRD 12 G1 patterns slice)

**Status:** design record, 2026-10-02 · **Base:** main at `0e6774e` · **Parent records:**
G1a `2026-10-01-issue297-g1a-contract-gate-design.md` (harness/registry/manifest; deferrals
D2/D4/D5, risk 4's disagreement check, §4's marker boundary), G1b
`2026-10-01-issue298-g1b-partials-design.md` (the 158/10 split and its kill rule; §10 fold),
G1c `2026-10-01-issue299-g1c-proofs-design.md`, REL
`2026-10-01-issue302-rel-pipeline-design.md` (the ui-html wheel proof in package.yml).
**PRD anchors:** §5 UR-06, UR-09, UR-13 (and UR-05's browser Direction); §6 R-3; §9 Q6;
§10 G1 row.

## 0. What G1d is, in one paragraph

G1b left exactly ten `rule_proof` rows red with the honest `no canonical artifact`
message — §B.2 SR-B1/B2/B3, §B.4 ST-1..ST-4, §C.1 R-ENERGISE-1/R-DEENERGISE-1/
R-PROTECT-1 (`artifacts.py:62` `DEFERRED_SLUGS`) — because they are behaviour rules
across components and time, and G1b's kill rule forbids satisfying them with
single-fixture structure checks. G1d discharges them with a **composition state
machine**: a small reducer over a frozen workbench state (`reduce(state, event)`),
a scene renderer that composes the G1b partials at each state, and a **fire path**
that re-evaluates guards server-side before dispatching — so a checker can arm a
confirm, move the guard state, attempt the fire, and assert the refusal, which is
the TS tests' shape ported faithfully. The same fixture registry backs UR-06's
**pattern library** (one page per component, both themes, every §B state, §C.2
reason and §C.3 refusal), UR-09's **axe-in-CI** lane (G1a D2 landing), and UR-13's
**static HTML export + screenshots** published to the docs site's user guides.
End state: the registry at **168/168**, the G1 gate's "green on every pinned
table" met, nothing Storybook offered going dark before G1e deletes `ui/`.

## 1. Mechanism

### 1.1 The composition state machine (`compositions.py`, new)

All in `packages/ui-html/src/benchweave_ui_html/`:

| New module | Owns |
| --- | --- |
| `staleness.py` | The §B.4 ST-2 predicate ported verbatim from `ui/src/components/readings/staleness.ts` (the TS is the semantic reference; the §B.4 rows are normative): `staleness(freshness_ms: float \| None, max_age_ms: float \| None) -> Literal["stale","fresh","no-verdict"]` — null/absent/non-finite/negative window ⇒ no-verdict; null/garbage freshness ⇒ no-verdict; strictly-greater comparison (equality fresh); `max_age_ms == 0` valid fresh-acquisition-only semantics. |
| `compositions.py` | `WorkbenchState` (frozen dataclass: `output: OutputState(energised, trip)`, `authority: bool`, `staged_value`, `confirm: Literal["idle","armed"]`, `messages` with per-message dismissed/acknowledged bits, readings with staleness verdicts + a `last_transition` announcement ledger), `reduce(state, event) -> WorkbenchState` (arm, cancel, trip-arrives, trip-clears, authority-lost/regained, reading-went-stale, dismiss-message, acknowledge-attempt, unrelated re-render), `render_workbench(state) -> str` (a `workbench.j2` scene over the G1b partials + mode banner), and `attempt_fire(state) -> FireResult` — a `dispatched(action, value)` \| `refused(reason)` union that **re-evaluates the guards against `state` at fire time, before any dispatch callback exists to call**. Toast channel typed `Literal["neutral","success","advisory"]` — SR-B1's toast restriction is unrepresentable-bad-state, not policy-checked. |
| `patterns.py` | The pattern library: a frozen `PATTERNS` registry of `PatternEntry(row_id, fixture_id, kind, render) -> str`, the page/index assembly (`pattern-page.j2`, `pattern-index.j2`), and `export(dest: Path) -> ExportResult` writing the static tree. One registry serves BOTH the row checkers' fixtures and the library pages (no second mirror to drift). |

`WorkbenchState` ports `DeviceWorkbenchFixture` from `ui/src/compositions/fixtures.ts`
(`psu-07` / `daq-47`, the contract's own invented identities) as the two canonical
composition scenes, plus the guard variants the TS tests synthesise by rerender
(`trip: true`, `requestEnabled: false`). Import direction keeps UR-11:
`compositions` → `partials`/`fixtures`/`data` → jinja2; Playwright appears only in
`tests/ui_html/`; the runtime dep set stays exactly {jinja2, markupsafe} so
package.yml's installed-set proof (`package.yml:99-108`) keeps passing.

**Why a reducer and not events-on-a-page:** the renderer is server-rendered; there
is no client state. "An event" IS a state transition followed by a re-render, and
"guard at fire time" IS the fire path consulting current state before dispatch.
The TS tests modelled exactly this at component level (injected callbacks, rerender
with mutated fixture); the reducer is the same model with the React runtime
replaced by pure functions. Disclosed honestly: compositions prove the
**presentation state machine** — what renders at each state and what the fire path
permits. Host wiring (routes, leases, real `run_check`/`run_start`) is G2/G3's
seam; nothing here claims it.

### 1.2 The ten checkers (extending `artifacts.py`)

Three new registrar entries fill `DEFERRED_SLUGS` (`b-2-state-rules`,
`b-4-staleness`, `c-1-safety-rules`) with `RuleProofArtifact` checkers that DRIVE
the state machine, each ported assertion-for-assertion from the TS bodies read
this session (`safety-proof.test.tsx`, `reading-states-proof.test.tsx`,
`DeviceWorkbench.test.tsx`):

- **R-ENERGISE-1** (`c-1-safety-rules::R-ENERGISE-1`): vacuous-pass control first
  (both scenes contain an energy-sourcing and an energy-removing action — the
  control that kills empty-page passes). Arm the energise control ⇒ no dispatch;
  the confirm text carries the effect (`the output will be energised` — the row's
  own §E.1 confirm-action literals), the exact value+unit, and the target; the
  second explicit action dispatches with the staged value. A set-point change on
  an ENERGISED output is energy-sourcing (arm/confirm); on a de-energised output
  it applies in one action with no confirm subtree.
- **R-DEENERGISE-1**: `attempt_fire(de-energise)` dispatches in one action in
  EVERY guard state (healthy, trip, no-authority, trip+no-authority); no state's
  render contains a confirm pattern for the off action (`bw-confirm` subtree
  absent, no `Confirm: De-energise` text); the control is never disabled by any
  guard reason.
- **R-PROTECT-1**: trip ⇒ the energise control renders disabled with
  `data-bw-disabled-reason="protection-active"` and its §C.2 visible label;
  de-energise stays enabled. **Guard-while-armed** (the §E.1 confirm-action
  Notes' fire-time rule, the TS `armed guard` describe block): arm, then
  `trip-arrives` ⇒ the ARMED confirm button itself is disabled with
  protection-active + the visible label, `attempt_fire` REFUSES without dispatch;
  combined trip+authority-lost presents protection-active and NOT the
  no-authority label (the trip is the present blocker); no auto-disarm (armed
  state survives the guard), Cancel stays enabled, `trip-clears` re-enables and
  the fire then dispatches. Property (e) rides here: EVERY
  `[data-bw-disabled-reason]` element in the trip render and in the no-authority
  render carries its key's visible `data-bw-disabled-label` text.
- **SR-B1**: the warning message renders anchored in its affected context (panel)
  across an unrelated re-render (persistence), the toast channel accepts only
  neutral/success/advisory severities (typed shut; the mutation arm loosens the
  type and must red), and warning/critical/trip messages never route to the
  transient channel.
- **SR-B2**: the warning/critical/trip composition states each carry icon + explicit
  label + border hook + text on the affected reading; normal/success render no
  glow-carrying vocabulary — cross-referenced to the G1b CSS pin
  (`test_reading_tile_css_pins.py`, fold-row 11) which stays the structural half.
- **SR-B3**: `dismiss-message` removes the bubble while the condition bit stays
  set and re-renders on the next transition; `acknowledge-attempt` without
  authority refuses — acknowledgement is a separately labelled, authorised act,
  never a side effect of dismissal.
- **ST-1**: the verdict's cadence input is the polled `max_age_ms` only; a
  stream-cadence source (no window supplied) renders NO staleness verdict in any
  render and asserts freshness nowhere; the missed-data signal never
  silence-infers (no marker, no stale attr, in steady state or after transitions).
- **ST-2**: the boundary arms — `staleness(150,150)=="fresh"`,
  `staleness(151,150)=="stale"` (strictly greater; the TS e-folded control),
  `max_age_ms=0` ⇒ `staleness(1,0)=="stale"`, non-finite/negative age or window ⇒
  no-verdict (a fabricated `fresh` is the lie class), each asserted through the
  rendered tile (no marker for fresh/no-verdict, marker for stale).
- **ST-3**: no known cadence ⇒ no verdict and no freshness claim anywhere in the
  render; `freshness_ms is None` renders `Unavailable`; a device quality string
  renders verbatim in the quality slot with the stale marker as a SEPARATE element
  (`bw-reading__stale-marker` span — two channels, the TS narrow-reading arm).
- **ST-4**: a stale tile carries the dimming class hook + `data-bw-stale="true"` +
  the visible `stale` marker appended to the quality line; the marker never
  missing while the attribute renders; the fresh→stale transition render carries
  exactly ONE `status` live-region announcement (the `last_transition` ledger —
  announcement on the crossing render, absent on the steady stale re-render and
  on a duplicate no-change event: coalesced, once). The data-table row arm
  (`tr[data-bw-stale]` + row dimming + marker; fresh rows unmarked) rides the
  same checker.

Template arms added (additive, G1b templates): the reading-tile stale arm
(dimmed hook, marker span, `Unavailable`), the data-table stale-row arm, and the
confirm-action armed-button guard fields (already pinned by §E.1's
`data-bw-confirm=armed` row; the armed confirm carries
`data-bw-disabled-reason` + visible label per the Notes). `ReadingData` gains a
computed-verdict field (`Literal["stale","fresh","no-verdict"] | None`) so the
tile renders verdicts from `staleness.py`, never a caller-supplied boolean alone.
The §F state icons bind at their composition sites (staged beside the Staged pin,
hidden with hidden markers, busy on `aria-busy` controls) — G1b's named deferral.

### 1.3 The pattern library and its export (UR-06, UR-13)

`patterns.PATTERNS` enumerates every visual fixture: the 11 §E.1 canonical
fixtures with their state variants, all §B.1 severities, the §B.3 state, the §B.4
variants (fresh/stale/no-cadence/null-freshness), all §C.2 reasons (on their
control pages), all §C.3 refusals, all §D.1 modes, and the composition scenes
(armed, guarded-while-armed, trip, no-authority) on their component pages. The
export writes a static tree — **plain rendered HTML files, no server**: Playwright
navigates `file://` URLs; nothing in the package serves anything.

- Layout: `patterns/<theme>/<page>.html` + `index.html`, themes `light|dark` via
  the `data-theme` root attribute; **one page per §E.1 component (11) + one
  refusal page = 12 pages × 2 themes**; every page root carries
  `data-bw-pattern-library`.
- Styling: the pages inline/link the real token CSS read through G1a's existing
  path constants (`artifacts.TOKENS_CSS`/`THEMES_CSS` → `ui/src/styles/` until
  G1e's re-point). One mirror, no copy; the export **reds loudly when the styles
  are absent** (the token rows' own fail-loud shape), and this record adds the
  named G1e checklist row: *pattern-library CSS source re-point* (beside the
  token-path and CSS-pin re-point rows G1b/G1c already recorded).
- Screenshots: PNG at a fixed viewport (**Direction, non-binding:** 1280×1024),
  `patterns/screenshots/<theme>/<row-id>__<fixture-id>.png` — keyed by contract
  row + fixture so guide links survive re-export (the brief's direction, adopted).
- Dev-mount-only guard, structural: the package ships render functions and a
  static-file writer ONLY — there is no app/ASGI/route object to mount; serving
  is a host concern. `docs/internal/drift-and-obligations.md` gains a G2 row: the
  gateway's GW-04 routing test must pin that no `/ui` path serves the pattern
  library. Honest limit: this cannot stop a future host from choosing to serve
  generated HTML; the obligation row + GW-04 are the enforcement, stated as such.

### 1.4 The browser lane (UR-09/Q6, G1a D2) and the RoleResolver disagreement check

- **Dependencies:** `packages/ui-html/pyproject.toml` gains
  `[project.optional-dependencies] browser = ["playwright>=1.49", "axe-playwright-python>=4"]`
  (G1a §4's named shape; the default install set stays
  {benchweave-ui-html, jinja2, markupsafe} so package.yml's proof is untouched).
  The ROOT dev group carries the same pins so `uv sync --locked` resolves them
  (uv.lock moves — counted in the tier call). CI installs browsers with
  `playwright install chromium` and caches `~/.cache/ms-playwright`.
  **Fork F-D1** if the maintainer prefers vendoring `axe.min.js` bytes over the
  pip wrapper (provenance note either way).
- **Marker partition, the #241 precedent:** browser tests carry the `browser`
  marker; ci.yml's `gates` job becomes `-m "not timing and not browser"` and a
  new serialized `browser` job runs `-m browser` — a third complementary lane in
  the exact shape the timing lane set (`ci.yml:55-68`, `75-106`). The
  deselect-by-default hole G1a forbids stays shut: no config deselects browser;
  the AR-1 collect-id proof (three lanes' union == unfiltered collection,
  pairwise intersections empty) is recorded in the PR body. Fast lane
  (`-m "not browser"`) keeps per-commit cost flat.
- **What the lane runs (one Playwright run, UR-13):** for every page × both
  themes — axe at WCAG 2.2 AA, zero violations; the export written into the run's
  output root; one screenshot per `PATTERNS` entry per theme; and the
  **disagreement check** (G1a risk 4): the roles the §E.1 Required-roles cells
  name are queried through the browser's accessibility tree on the library pages
  and compared against `roles.ImplicitRoleResolver`'s verdicts — any disagreement
  reds and must be resolved before ship (it retro-challenges G1a's resolver).
- **Publish (UR-13):** docs.yml's `build-docs` job gains the browser deps + the
  export run (output root staged into the site tree under the user guides;
  `assemble_docs_site.py` owns the tree — exact destination path is O2), so the
  Pages publish on main carries the current library and screenshots; neither is
  ever committed (a repo-side guard refuses a `patterns/` dir at the tracked
  root). "On each package release" (Q6) is satisfied by that main-push publish —
  a release is a main state and the site at the tag already carries the export;
  **Fork F-D2** if the maintainer wants an explicit tag-triggered republish.

## 2. Root cause / premise check

Verified on the landed surface, not assumed: `DEFERRED_SLUGS` names exactly the
three tables and `ensure_registered()` skips them (`artifacts.py:62`,
`1717-1725`); the registrar/factory protocol takes any callable
`key -> Artifact` so the ten land with zero registry-machinery change; the TS
assertion bodies were read (not skimmed) and define "equivalent assertions"
(cited per checker above); `staleness.ts`'s predicate is 20 lines and ports
verbatim; ci.yml already carries the complementary-marker partition precedent;
docs.yml assembles + publishes on main; package.yml's installed-set proof pins
the runtime dep set G1d must not move. The G1b kill rule (structural
satisfaction of the ten = prose-laundering) is the binding constraint this
design answers with state-machine checkers whose mutations change BEHAVIOUR
(guards, dispatch, transitions), not markup literals.

## 3. Minimal first increment and named deferrals

**In (stacked slices, each RED-first):**
1. `staleness.py` + `compositions.py` core (state, reduce, render, attempt_fire)
   + `workbench.j2` + unit tests porting the TS assertion bodies as plain pytest
   (no registry yet). RED: the tests fail against a stub scene renderer.
2. The ten `RuleProofArtifact` checkers + registrar wiring + the meta-acceptance
   completeness arm updated from the 158 set to the full 168 (deriving from the
   registrars, not a new hand count). RED: pre-wiring run shows the ten failing
   with exactly `no canonical artifact`.
3. `patterns.py` + page/index templates + the census test + export guard.
4. The browser lane: extra + dev pins, marker partition, ci.yml job, docs.yml
   step, axe + screenshots + disagreement check + planted-violation control.

**Deferred, each with its owner:**
- Host wiring of any composition into real routes — G2/G3 (compositions are the
  presentation model, not the host).
- Visual-regression baselines off the screenshots (PRD 11 Q2's option) — not
  taken up here; the PNGs are the baseline when it is.
- Vendored assets + inventory hashing + the CSS re-point — G1e (this record adds
  its checklist row).
- `ui/` deletion, obligation-12 rewrite — G1e; until then the TS proofs still
  run in the `ui` CI lane (unchanged).
- SDK-side publication of the library (R-9/standalone lane) — PRD 11.
- An explicit release-tag republish — F-D2.

## 4. Precedent

The registry/factory protocol, `RuleProofArtifact`, `ensure_registered`, the
M3 enum-membership arms, and the fixtures-as-row-data trick are all G1a/G1b's
proven mechanisms, extended not replaced. The complementary-marker CI lane is
#241 slice 1's shipped pattern. The optional-extra shape is G1a §4's own named
deferral. `lanes.py` composing over `decimate.reduce_lane` is the in-tree
precedent for a composition module over partials. New architecture — the reducer
and the fire path — is justified by R-3 itself: the registry protocol is
stateless per row, and behaviour rules need a state to traverse; no in-tree
mechanism supplies one.

## 5. Invariant, drift, tier

- **Invariants:** none of CTL/STO/CON/REG touched (presentation-layer package +
  tests + CI only). No new invariant proposed. Noted: R-DEENERGISE-1's "nothing
  stands between the operator and de-energising" mirrors A04 at the presentation
  boundary — this slice ENFORCES that contract rule; it touches no control-core
  protective machinery.
- **On-disk formats/schemas:** none changed. `standards/` bytes: zero. `ui-contract.md`
  bytes: zero. uv.lock moves (dependency motion — in the tier call below).
- **Drift:** obligation 12 unchanged until G1e. `docs/internal/drift-and-obligations.md`
  gains two rows: the G1e pattern-library CSS re-point checklist item, and the G2
  GW-04 never-served-by-production row.
- **Tier 3.** Keyword rule: the expected diff contains `protection`
  (case-insensitive) — the `protection-active` reason key in guard mappings,
  checkers, tests, fixture labels and this record. Path rules that ALSO fire:
  dependency motion (root + ui-html pyproject, uv.lock) and CI-workflow edits.
  No `standards/`, no persisted schema, no submodule pointer, no trust boundary
  in the security sense (file:// static pages, loopback-only dev posture). Per
  Tier-3 doctrine: two independent adversarial refute lanes + cold full battery
  + fresh-cache mypy.
- **Keyword scan (whole expected diff — code, tests, templates, workflows,
  record), estimated at design time, re-run at review:** `protection` ≈ 40
  (compositions ~6, checkers ~10, tests ~12, patterns/labels ~4, record ~8);
  `trust` 0, `credential` 0, `sha256`/`hashlib` 0 (UR-10 hashing stays G1e),
  `migrate` 0, `threading` 0, `asyncio` 0, `subprocess` 0 (Playwright spawns
  browsers internally; the diff never names it). A >20% deviation from these
  counts is a finding to explain, not a failure by itself.
- **CI cost:** one new serialized `browser` job (~3-5 min cold, ~2 min warm with
  the ms-playwright cache: 24 pages × axe + ~60+ fixtures × 2 screenshots on
  file:// URLs); docs.yml gains the same deps + export (~+2-3 min); `gates`
  unchanged in time (marker carve-out). No new matrix.

## 6. Measurable proof — pre-committed acceptance rule

**Population (no sampling):** 196 contract items (28 pin + 168 row), the
composition unit tests, the census/guard tests, and the browser lane's items.
Counts from `--junitxml` attributes or true exit codes, never a filtered
summary line.

- **RED half (on-branch, before the registrar wiring):** the ten rows fail with
  exactly `no canonical artifact for <row-id>` (the message class asserted, as
  G1b's rule requires — a red from `unsatisfied contract items` there means
  something satisfied-and-failed, i.e. a cheap-satisfaction attempt).
- **SHIP (all must hold):** 168/168 row items green; the completeness meta arm
  green at the registrar-derived 168 (set equality, no orphan); pin layer 28/28;
  the browser lane green — axe zero violations on all 24 page-renders, screenshot
  count == `len(PATTERNS)` × 2, export census == the manifest-derived minimum
  coverage (every §C.3 code, §C.2 reason, §B.1 severity, §D.1 mode, §B.3 state
  present as a fixture id; 12 pages × 2 themes); the disagreement check green;
  UR-11 boundary green (render one composition + one export with `pytest` absent
  from `sys.modules`); fast lane green per commit; cold full battery + both
  tripwires before push; ruff + fresh-cache strict mypy clean.
- **Behavioural teeth (the R-3 kill class) — mutation controls, each must RED
  its row and no other:** (m1) delete the fire-time guard re-check in
  `attempt_fire` ⇒ R-PROTECT-1 reds (dispatch happened while armed+tripped);
  (m2) `>=` for `>` in `staleness.py` ⇒ ST-2 reds at the 150/150 boundary;
  (m3) apply the trip guard to the de-energise control ⇒ R-DEENERGISE-1 reds;
  (m4) derive the tile's set line from the staged input ⇒ the SR/triad
  laundering witness reds; (m5) dismissal sets the acknowledged bit ⇒ SR-B3
  reds; (m6) drop the stale marker while keeping `data-bw-stale` ⇒ ST-4 reds;
  (m7) loosen the toast severity type to admit warning ⇒ SR-B1 reds.
- **Axe RED control:** a planted-violation fixture (a button stripped of its
  accessible name on a scratch page) MUST produce an axe violation — proving the
  axe configuration actually detects in this file:// setup; a clean run against
  the planted page means the measurement is broken, not the library.
- **KILL:** any of the ten green on render-only assertions (no transition, no
  fire attempt, no refusal observed — the review lane re-derives one checker per
  table by hand); any mutation control that stays green; any claimed-green row
  red on re-run (3× like G1b); any orphan; the planted-violation control passing
  clean; the disagreement check red without resolution; pytest entering the
  runtime import boundary.
- **UNDERPOWERED (not conclusive):** if the mutation controls cannot be run
  (checkers not parameterizable) or the browser lane cannot produce the
  planted-violation red, the behavioural claim is unproven and the slice does
  not ship on green counts alone; fix the controls first.

## 7. Top risks and falsifiers

1. **Composition checkers degenerate into structure checks** (the G1b kill
   class). Falsifier: the seven mutation controls — each mutates behaviour, not
   literals — plus the review lane hand-deriving one checker per table.
2. **The reducer model diverges from what a real HTMX host will do** (G2/G3).
   Falsifier/mitigation: the model is the TS tests' own model ported; the
   record's §1.1 disclosure is the boundary; G3's exit gate (confirm refuses at
   fire time when a trip arrives while armed) re-proves it on the real seam.
3. **axe passes clean because it measured nothing** (file://, injection, config).
   Falsifier: the planted-violation control, run in the same lane.
4. **The disagreement check retro-challenges G1a's resolver** (its risk 4). This
   is the mechanism working, not failing: a disagreement blocks ship until
   resolved and the resolution is recorded in this record's fold note.
5. **Playwright flake/cost in CI.** Falsifier: static file:// pages, serialized
   lane, cached browsers; a flake is a kill on the 3× re-run rule like any other.
6. **The export's `ui/src/styles` dependency breaks at G1e.** Falsifier: the
   export reds loudly on absent styles (asserted by a unit arm that hides the
   path); the named G1e checklist row rides drift-and-obligations.
7. **Two fixture populations drift** (row checkers vs library pages). Falsifier:
   one `PATTERNS` registry serves both; the census test derives its expectation
   from the manifest keys, not a hand count.

## 8. Open items (marked, not searched — time-boxed reading)

- **O1:** the meta-acceptance file's exact 158-set arm shape
  (`tests/ui_html/test_meta_acceptance.py` — named by the G1b record, not read
  this session); slice 2 must update it in place, not beside.
- **O2:** `scripts/assemble_docs_site.py`'s user-guides tree convention (the
  export's destination directory name inside the site); builder confirms before
  the docs.yml step lands.
- **O3:** ci.yml's `gates` marker string change (`not timing` →
  `not timing and not browser`) needs the AR-1 collect-id proof refreshed for
  THREE lanes — the #241 slice-1 precedent covers the mechanics.
- **O4:** `axe-playwright-python` vs vendored `axe.min.js` bytes — F-D1, the
  maintainer's packaging call.
- **O5:** whether the §E.1 confirm-action row's own attribute items need a
  guarded-variant canonical fixture registered for the §E.1 row itself (the
  guarded scene renders on the confirm-action page; the §E.1 row's artifact
   still asserts the unguarded canonical — believed sufficient, builder
  confirms no §E.1 item references the armed+guarded state).
- **O6:** the REL record's release-hook detail for F-D2 was not re-read this
  session; the main-push-reading is the design's default.

## 9. Environment note

Native Read of indexed `.py`/`.tsx` source is hook-blocked in this checkout;
those reads went through direct gortex `read` (file bodies) and
`read(operation:"editing_context")` per the hook's own remediation text — the
G1b record §9 posture. No gortex explore/localize/discovery ops were run, per
the dispatch discipline. Markdown and workflow files read natively.
