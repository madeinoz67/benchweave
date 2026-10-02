# Issue #301 — G1e: the React cutover (PRD 12 G1, final slice) — design record

Status: DESIGN (increment-designer, 2026-10-02). Base read at `main` `3f4ad11`.
Parent: PRD 12 `docs/implementation-planning/12-gateway-web-ui-prd.md` §6 R-4–R-8, §10 G1 exit,
§5 UR-10, §9 Q4/Q5. One increment, no sub-slices (PRD §6: "The cutover is one increment").

## 0. Tier call (pre-committed, #254)

**Tier 3.** Triggers, over the EXPECTED diff (deletions dominate: the whole `ui/` tree + the
ci.yml `ui` job; edits: `pyproject.toml`, `packages/ui-html` artifacts/staleness,
`docs/internal/{ui-contract,ui-styleguide,drift-and-obligations}.md`, `README.md`,
`docs/development.md`, `tests/ui_html/*`; additions: vendored CSS assets + inventory +
verify function + tests):

- **Keyword density (#254 keyword rule)** — measured over `ui/src` (the dominant diff text):
  `protection` ×31, `protective` ×14, `auth` ×39, `timeout` ×3, `credential` ×0, `secret` ×0,
  `sha256` ×0. The protection/trust vocabulary class is present at >0 counts in the diff
  text — the elevated tier triggers. The PR body re-runs the scan over the ACTUAL diff
  (docs and code alike) and records the counts; a >20% deviation from these numbers
  re-derives the tier call (G1b precedent).
- **CI topology change** — a gate lane (the `ui` job) is deleted; the root-suite default
  collection gains 196 items.
- **Safety-bearing enforcement surface swaps homes** — the TS gates that enforced §C/§E die;
  the Python gate goes live in the same commit (the R-4 "same change" requirement).

NOT Tier-3-on-disk-format: no on-disk schema or format version changes — the vendored CSS is
new package data (no schema), the inventory follows the existing `preview_assets/inventory.json`
shape (`api_version: 1`), and **zero `standards/` bytes move** (tripwire
`git diff origin/main...HEAD -- standards/` stays empty; the plugin-ui-preview schema and the
Python emitter conformance are untouched — only the TS decoder half of that conformance dies).

**Two adversary lanes** (standing Tier-3 rule, 2026-09-24 R3).

## 1. The F-A wiring — the decision this slice exists to make

### 1.1 Mechanism

`pyproject.toml [tool.pytest.ini_options]`:

```toml
testpaths = ["tests", "docs/internal/ui-contract.md"]
```

The contract FILE itself as a second testpath entry. The pytest11 collector
(`packages/ui-html/src/benchweave_ui_html/contract_harness/plugin.py:41`,
`pytest_collect_file` claiming files named `ui-contract.md`) already generates the two item
families when pytest is invoked on that path — measured at design time:
`uv run pytest --collect-only -q docs/internal/ui-contract.md` → **196 items (28 pin + 168
row), exit 0** (rtk's filtered "No tests collected" was the documented summary-line lie; the
count is from the raw redirected file, exit code separate). With the file in `testpaths`,
the no-args default run — exactly the invocation CI's `gates` job uses
(`pytest -q -n auto -m "not timing and not browser"`) — collects it.

### 1.2 Why testpaths, not the alternatives

- **Not a conftest registration.** G1a's recorded ruling (restated in
  `packages/ui-html/pyproject.toml` entry-point comment): collection-time generation over a
  non-Python target file is the pytest11 plugin's job; the plugin already claims the
  filename. A root `conftest.py` adding a second claimant duplicates the collector and
  re-litigates a closed decision without new evidence.
- **Not plugin-side self-registration** (the plugin adding the contract to any run it sees).
  Structurally wrong and disqualifying: the wheel is published and consumed at a pinned
  version by the SDK repository's standalone host (PRD §9 Q5, NFR-P2), and `package.yml`
  proves the installed set is exactly `{benchweave-ui-html, jinja2, markupsafe}`. A plugin
  that injects collection into every pytest run sharing the venv would hijack foreign test
  suites (the SDK's own CI installs this wheel). The contract bytes live in THIS repository,
  not in the wheel — the wiring must live in this repository's pytest config.
- **testpaths is the config pytest already consults for precisely the invocation that must
  change**: the no-args default. Explicit invocations (the F2 mixed-invocation shape) already
  work and keep working.

### 1.3 Fail-closed: no config edit can remove the contract from the default run

Honest structural limit first: pytest offers no mechanism to make ini-config un-editable.
"Fail-closed" here is the repo's established class (obligation 20's register): removal
necessarily reds the suite CI runs, and the only way past is a visible editorial diff.

The pin: a new arm in `tests/ui_html/test_harness.py` —
`test_default_invocation_collects_the_contract` — which runs the BARE default invocation
(`uv run pytest --collect-only -q`, NO path args, `cwd=REPO_ROOT`,
`UV_PROJECT_ENVIRONMENT=venv`) and asserts all 196 contract nodeids (28 `pin::<slug>` +
168 `row::…`) appear in the collected list. Then:

- Editing `testpaths` back to `["tests"]` reds the pin (0 contract items collected).
- The pin lives in `tests/` — always collected by the default run, inside the very
  collection it pins.
- CI's `gates` job runs the default invocation, so the pin runs in CI on every push.
- Deleting the pin itself is a visible diff; this slice's drift row (§4) names it as the
  enforcement home, so the G5 obligation walk catches its deletion.

### 1.4 Consistency with G1a's arms (no re-litigation)

- `test_harness.py:73` (deselect-resistance: `-m contract` keeps all 196; `-m 'not contract'`
  deselects all, exit 5) — untouched; marker semantics do not change.
- `test_meta_acceptance.py:643` (F2 mixed invocation: explicit
  `pytest tests/… docs/internal/ui-contract.md` carries the gate) — untouched; G1e adds the
  no-args shape beside it, it does not replace it.
- The disclosed PYTEST_ADDOPTS=`-m 'not contract'` env attack on explicit invocations
  remains G1a's disclosed residual — not reopened: G1e's requirement is
  config-removal fail-closed-ness, and CI supplies no PYTEST_ADDOPTS. The default-run pin
  shrinks the residual's reach (the default run, the shape CI actually gates, is now pinned).
- `test_no_environment_variable_flips_the_gate` and the registration/toggle arms — untouched.

### 1.5 xdist and marker interaction (verified by acceptance, not argument)

The 196 items carry only the `contract` marker — not `timing`, not `browser` — so the gates
filter `-m "not timing and not browser"` admits them, and the browser/timing lanes exclude
them by the same complementary-partition logic. xdist distribution of generated `Item`s is
proven by the CI-shaped AFTER acceptance run (§6), never assumed. The three-lane AR-1
collected-id partition proof (ci.yml `gates` comment) is recomputed at PR time with the 196
in the gates set — recorded in the PR body, per the established doctrine.

## 2. R-4 — the deletion's blast radius (the census)

Everything that dies or moves, enumerated; each row's disposition:

| Surface | What happens |
|---|---|
| `ui/` whole tree | Deleted: `src/`, `scripts/write-preview-inventory.mjs`, `.storybook/`, `package.json`, `package-lock.json`, `eslint.config.js`, `tsconfig*.json`(+`.tsbuildinfo`), `vite.config.ts`, `vite.preview.config.ts`, `index.html` |
| `.github/workflows/ci.yml` | The entire `ui` job (setup-node, npm ci, typecheck, lint, unit tests, Storybook build, renderer-freshness gate, npm audit) deleted |
| `.github/workflows/package.yml` | **No change** — read at design time: it contains no Node step and no `ui/` reference (the ui-html wheel proof and `sdk_smoke` are Python/uv) |
| `.gitignore:25-26` | The dead `ui/vite.config.js`/`.d.ts` entries removed |
| `README.md:64` (`npm run storybook`), `docs/development.md:47,144` (build-storybook command; the ui-job CI description) | Rewritten to the Python/pattern-library workflow |
| `docs/internal/ui-contract.md` | §3 below (minimal edits: dead paths + enforcement naming) |
| `docs/internal/ui-styleguide.md` | §5 below (R-7 rewrite) |
| `docs/internal/drift-and-obligations.md` | Rows 7, 12, 24, 26 + the CI-map `ui` row (§4) |
| `packages/ui-html/.../artifacts.py:76-82` | `_STYLES_DIR`/`TOKENS_CSS`/`THEMES_CSS`/`GLOBALS_CSS` re-point to the vendored assets (§6 UR-10) |
| `packages/ui-html/.../staleness.py:2` | Docstring's "verbatim from the semantic reference `ui/src/components/readings/staleness.ts`" — the ported module BECOMES the semantic reference; docstring rewritten to say so |
| `tests/ui_html/test_threshold_verbatim.py` | Arms (b) and (c) retire — G1c's erratum row: arm (c) (TS threshold literals 3.0/10.0/8.0/11.0/9.0) retires with its transcription evidence already in G1c §2 (line-cited); arm (b) parsed the TS `severityAll` loop and cannot parse a deleted file. The Python thresholds' own pre-committed constants and tests remain the live pin |
| `tests/ui_html/test_harness.py` | GAINS the default-run pin (§1.3) |
| New (UR-10) | `packages/ui-html/src/benchweave_ui_html/assets/{tokens,themes,globals}.css` + `inventory.json` + the verify function + tests (§6) |

**Final sweep (build-agent checklist, every hit dispositioned in the PR body):**

```
grep -rn "ui/\|storybook\|npm\b\|node" README.md docs/ .github/ Makefile scripts/ .gitignore CLAUDE.md AGENTS.md
grep -rn "ui/src" packages/ tests/ src/ scripts/
git ls-files | grep -i "package.json\|package-lock\|storybook\|vite\|eslint"
```

Design-time census found no other consumer: `Makefile` and `scripts/` carry no `ui/`
reference; no root `package.json` exists; `scripts/sdk_smoke.py`'s `ui` hits are
`plugin-ui/contracts.py` (the standards corpus, untouched).

**Proof nothing outside `ui/` imports from `ui/`:** (a) the static census above; (b) the
load-bearing mechanical proof — `artifacts.py` path constants fail loud when absent (G1c
design §3: "failing loud if absent"), the pattern export refuses loudly on missing inputs
(`PatternExportRefused`, pinned by `tests/ui_html/test_patterns.py`, obligation 24) — so
after the re-points, the post-deletion FULL suite green is positive evidence no live
reference remains; a missed reference reds, it cannot pass silently.

**§C.2/§C.3 handoff verification (build-agent sub-task, blocker-not-deferral):** walk every
§C.2 disabled-reason and §C.3 refusal assertion in the deleted
`ui/src/contract-enforcement.test.ts` and check each against its Python home —
`tests/ui_html/test_families.py` (G1b M3's enum arms), `tests/ui_html/test_compositions.py`,
and the refusal/disabled-label partial renders pinned by the UR-11 probe
(`test_meta_acceptance.py`, `render_refusal`/`render_disabled_label`). The checklist lands
in the PR body; any TS assertion with no Python counterpart is a BLOCKER — it means G1b's
handoff was incomplete and the cutover would lose enforcement.

**KNOWN-REACT-BUGS — closed by deletion:** the reference renderer's three known defects —
the order-dependent double-emphasis (G1c record §3, M2 corner: accent-hinted trace first
loses to slot 1 by bytewise sort), the untrimmed-unit axis binding, and `data-bw-lane`
renumbering on hidden lanes — die with `ui/`. The Python proofs pin the correct behaviour
(`tests/ui_html/test_plot.py:104` renumber test; `plot.py:201-232` axis remap; the §E.2.3
trimmed-unit grouping). Recorded here as closed-by-deletion; no action beyond this record.

## 3. `docs/internal/ui-contract.md` — minimal edits (dead paths + enforcement naming)

The contract is normative and stays; only what dies changes:

1. **Lines 16-20 (authoring rule):** the enforcement tests named as
   `ui/src/contract-coverage.test.ts` / `ui/src/contract-enforcement.test.ts` rewrite to the
   Python gate: the `benchweave-ui-html` contract harness (pytest11 collector; pin layer =
   parse integrity per pinned table, row layer = canonical-artifact requirement per parsed
   row), **live in the default root-suite run** (`testpaths`, §1). The "pin failure, not a
   silent skip" sentence and the cell micro-syntax stay verbatim.
2. **§A executable mirror:** "`ui/src/styles/tokens.css` and `ui/src/styles/themes.css` are
   their executable mirror" → the package's vendored assets
   (`packages/ui-html/src/benchweave_ui_html/assets/`), inventory-verified (§6); the
   bidirectional same-commit pin sentence stays.
3. **§A plot-series tokens:** "computed proofs in `ui/src/series-colors.test.ts`" →
   `tests/ui_html/test_series_colour_proofs.py`.
4. **§F:** the reference-binding column keeps the lucide names as the FROZEN reference's
   bindings (the parenthetical `ui/src/components/feedback/severity.tsx` citation re-worded
   to "the deleted React reference renderer"); the shape descriptions remain the normative
   binding surface (already renderer-neutral). §E.2.2's ECharts bindings: unchanged
   (implementation guidance by the contract's own words).

## 4. Drift-and-obligations rewrites (R-5, R-6, and the accumulated checklist rows)

**Row 7 (R-5, the freeze record).** The "Renderer freshness" sentence (the `ui` job rebuilds
and fails on `preview_assets` diff) is replaced by the frozen-bundle exception:

> **Frozen preview bundle (G1e, R-5):** the SDK's committed `preview_assets` React bundle is
> FROZEN at its last build (`renderer_version 0.1.2`, inventory at freeze commit `<sha>` —
> recorded at landing): shippable, NEVER rebuilt — the toolchain that built it (`ui/`,
> `write-preview-inventory.mjs`, the Node CI lane) is deleted, so no path exists that
> regenerates it. The SDK's `hatch_build` inventory-vs-committed-bytes verification REMAINS
> the integrity check (frozen ≠ rot: byte drift still reds the SDK build). Exit: dependency
> 4a — the PRD 11 standalone host with mock transport (SA-PREVIEW, #309) — at which point
> `preview_assets` is deleted from the SDK and `preview-ui` becomes a shim (R-9).

**Row 12 (R-6).** Rewritten to name, verbatim set: the Python harness
(`packages/ui-html` — the pytest11 contract gate, pin+row layers, LIVE in the default
root-suite run since G1e, enforced by the default-run pin in `tests/ui_html/test_harness.py`);
the pattern library (static export, docs-site staging at build, the browser lane's axe/
screenshot set); the ported proofs (`tests/ui_html/`: series-colour proofs, token/CSS pins,
threshold constants, lane reduction, staleness predicate); the wire shape
`standards/plugin-ui-preview/<active>/preview-document.schema.json` conformance-tested from
the **Python emitter only** (the TS decoder half is deleted with `ui/`). Plugin-visible
rendering behavior → `docs/device-developer-guide.md` presentation section (unchanged);
component behavior → the harness rows + the pattern-library pages (the Storybook reference
is gone). The vendored-asset inventory + serve-time verification (UR-10) is named with its
package-side verify function and the host-call documentation.

**Row 24.** The "At G1e the CSS re-points" sentence flips to the landed state: the export's
CSS inputs are the package's vendored assets (§6); the `PatternExportRefused` guard and the
never-committed-`patterns/` guard unchanged; the staleness semantic reference is now
`packages/ui-html/.../staleness.py` itself.

**Row 26.** Tense flip only: the real UI's 24px target-size obligation was inherited by
G2/G3 at this slice ("ride `ui/src/components/**/*.css` today — which G1e DELETES" →
"which G1e deleted"); the G2/G3 host-design inheritance clause is unchanged and still open.

**CI map.** The `ui` row is deleted; the `gates` row gains the contract items ("including
the 196 contract-gate items collected from `docs/internal/ui-contract.md` via `testpaths`").
Rows 24/25 stay as landed by G1d.

## 5. R-7 — `docs/internal/ui-styleguide.md` rewrite (shape)

The authority chain is unchanged (the contract wins; the workbench-design doc stays
historical). The rewrite re-frames React-specific guidance as Jinja/HTMX implementation
guidance, with this section mapping (every current heading survives, maps, or records an
exception — the reviewer walks this table):

| Current section | Disposition |
|---|---|
| Non-negotiable rules, Tokens, Borders/typography, Controls, Motion, Layered Precision, Choosing a component, Observation and control, Alerts, Numbers, Plots, Administrative consistency, Accessibility, Plugin presentation | Stay as renderer-neutral behaviour guidance; implementation references re-point (tokens executable mirror → vendored assets + Python pins; component CSS file references → the partials/templates) |
| Local commands (`npm …`, storybook) | Rewritten to the Python workflow: `uv run pytest docs/internal/ui-contract.md`, the default root-suite run, the pattern-library export + docs-site staging, the browser lane |
| Required stories (§241) | Maps to the canonical fixtures + the pattern-library pages census (the `PATTERNS` export census and the browser-lane screenshot set are the successor of "required stories") |
| **Exceptions (§271)** | Gains the recorded exceptions: **(E1, R-8)** severity label wording — `success` → "Normal" was the reference renderer's choice; the HTMX renderer keeps the CURRENT labels so the cutover is invisible to operators (severity keys, icons, colours, dismissal classes — all contract — unchanged); **(E2)** the contract's lucide/ECharts "reference binding" columns name the FROZEN React reference; the Jinja renderer binds from the shape descriptions; **(E3)** React-specific implementation mechanics (component-scoped CSS, Storybook workflows) are recorded as historical, not guidance |

R-8 itself is a no-code-change ruling: nothing in the Python surface relabels anything; the
exception record above is its entire landing.

## 6. UR-10 — the vendored-asset inventory (G1a's D3 deferral lands here)

- **Asset set:** `ui/src/styles/{tokens,themes,globals}.css` → vendored at
  `packages/ui-html/src/benchweave_ui_html/assets/` — inside the wheel's packaged tree
  (`packages = ["src/benchweave_ui_html"]`), so the wheel ships them and the `package.yml`
  installed-set proof is untouched (package data, not dependencies; UR-11's
  runtime-deps-only posture is unchanged).
- **Byte identity:** the vendored bytes are the LAST REACT BUILD's bytes — moved, never
  edited. Proven at landing: sha256 of each vendored file equals the sha256 of the
  `ui/src/styles/` file at the parent commit (recorded in the PR body), and the G1c census
  margins re-run against the vendored bytes reproduce the recorded margins exactly (delta 0
  — any movement means the bytes changed, which is the kill, §7).
- **Inventory format** (the preview-assets/corpus-manifest precedent — G1c's note):
  `assets/inventory.json`, shape of `packages/sdk/src/benchweave_sdk/preview_assets/inventory.json`
  (`api_version: 1`; per-asset `path` (package-relative), `sha256`, `size`). One inventory,
  two future hosts: the gateway host (G2) and the SDK standalone host (PRD 11) both consume
  the wheel's assets through it.
- **Verify function:** `benchweave_ui_html` gains `verify_vendored_assets()` — recomputes
  each asset's sha256 against the inventory and refuses BY NAME
  (`vendored_asset_mismatch:<path>`; absent asset = `vendored_asset_absent:<path>`). Tests:
  (i) the live tree verifies; (ii) a corrupted COPY (tmp dir) reds with the refusal name —
  the RED control; (iii) a missing-entry/extra-file disagreement reds (the inventory is an
  exhaustive census, not a sample).
- **Serve-time verification:** the hosts don't exist yet — this lands as the package-side
  verify function + its tests, with the HOST CALL documented (docstring + the obligation-12
  rewrite: a host verifies the inventory before serving the assets). Same honest-limit shape
  as obligation 25: enforcement-by-host lands with the host, and G2's design inherits the
  named obligation.
- **Re-points:** `artifacts.py` `TOKENS_CSS`/`THEMES_CSS`/`GLOBALS_CSS` → the vendored paths
  (G1c's token-path row + G1b's CSS-pin row land here); `patterns` export CSS input follows
  (obligation 24); thresholds and proofs are UNTOUCHED.

## 7. Pre-committed acceptance rule (written before any number is looked at again)

**Metric:** contract items collected by the DEFAULT root-suite invocation, and the gate
topology, across ONE commit pair (parent → cutover commit). Sample size: the single cutover
commit (this is a deterministic collection/mechanism proof, not a statistic — one
measurement per state is the sample; the suite adds its per-push repetition).

**SHIP if all hold at the cutover commit:**
1. **Atomic swap, BEFORE half** (parent commit, recorded in the PR body):
   `uv run pytest --collect-only -q` (no path args) → **0** contract items; the parent's CI
   `ui` job green (the React gates' last green run).
2. **AFTER half:** same command → **exactly 196** contract items (28 pin + 168 row); and the
   CI-shaped run `uv run pytest -q -n auto -m "not timing and not browser"` GREEN including
   the 196 (xdist proof, §1.5); junitxml attributes read (never a summary line).
3. **No Node toolchain remains:** `git ls-files` contains no `package.json`,
   `package-lock.json`, `.storybook/`, `vite.config.*`, `eslint.config.*`;
   `grep -rn "setup-node\|node-version\|npm " .github/` → 0 hits; no root `package.json`.
4. **Inventory verifies:** live tree green; corrupted-copy arm reds with
   `vendored_asset_mismatch:` (RED control run at the cutover commit, not assumed from
   design-time).
5. **Re-points are byte-identical:** vendored sha256 == parent `ui/src/styles` sha256 (three
   files); the G1c census margins re-run against vendored bytes reproduce recorded margins
   (delta 0); thresholds unchanged (constants untouched in the diff).
6. **Obligation rewrites landed:** row 7 names the freeze + `<sha>` + exit (#309); row 12
   names packages/ui-html, tests/ui_html, the pattern library, the Python emitter (and NOT
   the TS decoder); CI map has no `ui` row; rows 24/26 flipped to landed tense.
7. **§C.2/§C.3 handoff checklist complete** (§2) — every deleted TS assertion mapped to a
   live Python arm, in the PR body.
8. Full battery green at the cutover commit (fast triple + full suite + both standards
   tripwires; the `#247` lanes); `gh pr checks` rollup read in full: zero fail, zero
   pending, and NO `ui` job present.

**KILL if:**
- The AFTER default run collects ≠196, or any contract item reds → the swap is not atomic;
  fix forward only if the cause is collection mechanics (§1) with the pin proving it;
  otherwise kill the cutover and re-land G1a's dormancy disclosure.
- Any census margin moves, or any vendored sha256 ≠ parent's → the bytes are not the last
  build's bytes — kill (re-vendor from the true last build; do not edit assets to fit).
- The §2 census finds a live `ui/` consumer outside the enumerated set, or the §C.2/§C.3
  walk finds an uncovered assertion → blocker: the design's blast radius was wrong — extend
  the design, do not merge with a silent loss.

**UNDERPOWERED (measurement broken, not mechanism):** if the BEFORE half shows ≠0 contract
items in the default run (testpaths file-entry semantics differ from this design's reading),
stop — the measurement setup is wrong; re-derive the wiring on evidence before proceeding.
Same ruling if the pin itself cannot discriminate (a sabotage arm — comment out the
testpaths entry — must red the pin; run it once at landing as the pin's own RED control).

## 8. Deferrals (explicit, with reopen triggers)

- **D1 — the host call for serve-time verification** (G2 gateway host; PRD 11 standalone):
  the verify function + tests + documentation land now; the host wiring lands with the
  hosts (obligation-25 shape). Reopen: the G2 routing-test design.
- **D2 — R-9 `preview-ui` shim + `preview_assets` deletion from the SDK**: lands with
  dependency 4a (SA-PREVIEW #309) — the freeze's exit, not this slice.
- **D3 — the Jinja renderer's icon bindings** (§F): shape descriptions are normative and
  bindable; the concrete icon set choice belongs to the host that renders icons.
- **D4 — device-badge / mode-banner unification** (#242 row D4): untouched.
- **D5 — the AR-1 three-lane partition re-proof**: performed at PR time per doctrine
  (ci.yml comment), not automated here.

CI cost: the `gates` job gains 196 fast items (parse + registry + evaluate; the parent's
explicit invocation runs them in seconds); the `ui` job (npm ci + typecheck + lint + tests +
Storybook build + freshness rebuild + audit — minutes) is DELETED. Net CI time DOWN.

## 9. Top risks and their falsifiers

1. **A live `ui/` consumer outside the census** (the big one). Falsifier: the §2 static
   census + the post-deletion full-suite green (loud-fail constants, `PatternExportRefused`)
   + the §7 kill direction. The design's confidence rests on every consumer being
   fail-loud — the census proves the quiet ones absent.
2. **`testpaths` file-entry semantics** differ (a file as a testpath not collected on some
   pytest path). Falsifier: the default-run pin reds at the cutover commit — the mechanism
   cannot ship broken; pytest≥8 pinned; the F2 arm already proves file-arg collection.
3. **xdist mishandles the generated items.** Falsifier: acceptance §7.2 runs the CI-shaped
   command, not bare pytest.
4. **The freeze is quietly violated later** (someone hand-edits `preview_assets`). The
   SDK's `hatch_build` inventory check reds on byte drift; the obligation-7 rewrite states
   "never rebuilt" and names the exit; no CI path writes the tree anymore.
5. **Vendoring copies the wrong bytes** (e.g. uncommitted working-tree CSS). Falsifier:
   sha256-vs-parent equality (§7.5) + the margins re-run.
6. **The styleguide rewrite loses normative content.** Falsifier: the §5 mapping table —
   every heading survives, maps, or records an exception; the reviewer walks it against the
   pre-rewrite file.
7. **The contract items green-under-registration masks a parse regression at the moment of
   wiring.** Falsifier: this is exactly what the pin layer exists for (28 pins red on any
   table defect, mutation-tested in `test_metric_b_fail_closed_mutations` and the F1
   identity arms); no new exposure is created by changing WHERE the file is collected from.

## 10. Surfaces moved (the G5 walk for this slice)

`docs/internal/ui-contract.md` (naming + paths), `docs/internal/ui-styleguide.md` (rewrite),
`docs/internal/drift-and-obligations.md` (rows 7/12/24/26 + CI map), `README.md` +
`docs/development.md` (workflow text), `pyproject.toml` (testpaths — no dependency change;
`uv.lock` UNTOUCHED), `.github/workflows/ci.yml` (job deletion), `.gitignore`,
`packages/ui-html` (artifacts re-point, staleness docstring, new assets/inventory/verify +
tests), `tests/ui_html/` (default-run pin; threshold-verbatim arms b/c retire). MCP tools,
REST/openapi, CLI, operator docs' CLI tables: untouched. Standards corpus: untouched
(tripwire proves it). The SDK submodule pointer: NOT advanced (the freeze changes no SDK
bytes; D2 is the SDK-touching event).

No on-disk schema or format version changes; no new invariants required — CON/REG untouched;
the drift rows carry the new obligations (the default-run pin's home is row 12's rewrite).
