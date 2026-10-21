# The class-sweep SDK leg: render-verify the active family (gateway issue #463, gap 2)

Status: designed 2026-10-21 in `.wt/gate-k9x2` (branch `feat/classref-promotion`,
merged at `origin/main` tip `5ff6668b`; SDK submodule at `a6a1292`, the v0.17.0
release cut). No build in this slot. The design answers the dispatch question —
"design the smallest mechanism that closes 'no step verifies what RENDERS'" — and
its headline finding is a **scope correction**: the rendered-output gate already
exists, is released, and is wired into the author workflow; what does not exist is
its coverage of the corpus. The smallest mechanism is therefore **no new gate**:
widen the SDK expander and gate census to the 0.3.0 vocabulary the corpus already
authors, and pin every class of the active family with a render arm through the
real preview host.

Triage check (`.claude/deep-review/README.md`): public. Invented fixture names
only; the community plugin cited below is already-public provenance named in-tree
(`tests/ui_html/test_classref_daq.py`), cited as provenance per CLAUDE.md §4.

## 1. What gap 2 demands, and what already exists

Issue #463's gap 2 (filed 2026-10-14 against SDK 0.12.0):

> No step verifies what RENDERS. The workflow and the plugin-ui skill stop at
> schema gates (`check-ui`, `check-preset`). A manifest can pass and still render
> an incomplete page. Nothing compares served pages against the pattern library.

Since that filing, the L2 and L5 events built and released the mechanism the gap
asked for. All verified in the pinned tree (SDK submodule `a6a1292`, v0.17.0):

- **The rendered-output gate exists.**
  `packages/sdk/src/benchweave_sdk/classref_gate.py::verify_ui` — validate,
  derive, render, census the served HTML on the ui-contract §E.1 surfaces,
  assert the numeric expectation, the forbid arms (D7 confirm-wrap,
  color-role-hint, untraceable-lane-label, intermediated-energy-removing),
  the always-on D14 per-action coverage arm, and the A11 layout-order arm.
  Findings are typed (`classref_gate_*`); the module docstring carries the
  standing honesty line ("A clean gate is never admission…").
- **The render happens through the real preview host.**
  `packages/sdk/src/benchweave_sdk/classref_gate_render.py::render_pages` serves
  the plugin project in-process: `benchweave_sdk_server.web.build_app` over a
  `StandaloneSeam` with `PluginSession` + `LoopingMockHost(mock_exchanges(...))`,
  exercised through starlette's `TestClient` — the same server `preview-ui` and
  `serve` use (issue #463's own evidence: "preview-ui and serve are the same
  server with different transports. Rendering parity holds by construction").
  No browser, no Playwright, no reimplementation.
- **It is a shipped CLI command with workflow wiring.**
  `packages/sdk/src/benchweave_sdk/cli.py:577` (`verify-ui`); the scaffolded
  plugin-ui skill instructs authors "Verify the derived set with `verify-ui`"
  (`packages/sdk/tests/fixtures/scaffold_expected/ui/.claude/skills/
  benchweave-plugin-ui/SKILL.md:21`); CHANGELOG line 54 records the L2 landing.

So the gate, the render half, and the author-facing wiring all exist. What does
NOT exist is coverage of the corpus PR #516 just landed — and the corpus outran
the expander. The evidence, each point verified in the tree:

1. **The SDK expander resolves a closed six-counter grammar; the corpus authors
   eleven.** `packages/sdk/src/benchweave_sdk/classref.py:63` (`_EXPECT_NAMES`)
   admits exactly `n_lanes, n_groups, n_decoders, n_run_actions,
   n_configure_fields, n_pages`; `_build_expectation` (same file, lines
   1491–1547) computes exactly that inventory and raises
   `classref_expect_expression` for any other name. The 0.3.0 corpus's README
   (lines 240–242) authors five more — `{n_source_channels}`,
   `{n_scalar_variables}`, `{n_reading_tiles}`, `{n_analogue_channels}`,
   `{n_trace_variables}` — and the class files use them: `class-dc_psu.json:110`,
   `class-dmm.json:106`, `class-electronic_load.json:113`, `class-smu.json:110`
   all carry `"count": "{n_reading_tiles}"`. Zero hits for any of the five names
   anywhere under `packages/sdk/`.
2. **The expander emits no plot kind but `digital_lanes`.** The strings
   `time_series` and `waveform` appear nowhere in
   `packages/sdk/src/benchweave_sdk/classref.py` (search census, 0 hits), while
   the corpus's seven post-founding classes author `time_series` or `waveform`
   plots (the 0.3.0 vocabulary widening; README lines 22–34).
3. **The gate census has no surface for the readings-class components.**
   `classref_gate.py`'s `census_map` (inside `_assert_expect`) knows nine
   component names; `reading-tile` and `engineering-plot` are not among them —
   an expect row naming either refuses with `classref_gate_unknown_component`
   even if the count were an integer.
4. **Consequence:** `derive-ui` and `verify-ui` on a project whose descriptor
   matches any of the seven classes added since the founding reference FAIL
   (best case `classref_expect_expression`, worst a silently wrong derivation
   path). The gate's own test suite exercises exactly one class —
   `packages/sdk/tests/helpers_classref.py` hardcodes
   `find_reference("otdp.logic_analyser/1.0.0")` and `descriptor-f1.json`; all
   18 `verify_ui`/`verify-ui` call sites in `test_classref_gate.py` ride that
   one project. Render verification today covers **1 of the 8 classes of the
   active family** — the founding class whose 0.1.0-era vocabulary the expander
   still speaks.
5. **This exact leg was pre-assigned by the sweep.** Every gateway-side class
   test defers it by name — e.g. `tests/ui_html/test_classref_dc_psu.py:20`:
   "The expansion side (derive-ui/verify-ui censuses) is the SDK widening's";
   `test_classref_daq.py:49` carries the same deferral, and its docstring is
   explicit that the real-consumer conformance arm runs a structural acceptance
   rule encoded in-test (`_acceptance`), never the production derivation. The
   L11 record named the arms: "dataset variables by shape, observation bindings
   on readings pages, plot emission, reading layout nodes, the widened expect
   inventory and census … are the SDK widening's work and ride that train."
   The train's promotion (PR #516, SDK 0.17.0) landed the corpus bytes and the
   version sync; the widening never rode.

**Root cause, one sentence:** the class sweep landed corpus, mockups, pattern
pages and a document-level composition gate gateway-side while the SDK-side
expander — the only consumer that executes the production render path — stayed
at the founding class's vocabulary, so the gate that closes gap 2 exists but
cannot run on 7/8 of the family it must verify.

### 1.1 The four design questions, answered from the code

**Q1 — What is compared, against what source of truth?** The rendered page's
§E.1 component census is compared against the class reference's `expect` block,
resolved over the descriptor by the expander's counter inventory. The expect
block is authoritative: it is data in the digest-pinned, copy-never-move
governed corpus, schema-validated by `class-reference.schema.json`, and the
README says what it is for ("**Expect** declares the gate's assertions"). The
pattern library is NOT the oracle — its class pages are hand-composed display
compositions whose own module discloses the posture
(`packages/ui-html/src/benchweave_ui_html/classref.py`: "RENDER-TIME EXPANSION
(disclosed) … presentation values are fixture choices"); the mockups are
hand-authored HTML — the spec for those pages, one step removed from production.
Those two stay exactly where they are (the design/visual lock); this slice adds
the production-path lock, which nothing else holds.

**Q2 — Where does the render happen?** The real preview host, in-process:
`render_pages` → `build_app` → `TestClient.get(f"/pages/{page_id}")`. Not a
Quarto build (no such path exists for plugin UI), not the gateway composer (the
gateway's `benchweave.presentation` internals are not a supported API — the
package boundary PR #516's release just made explicit), not a reimplementation.
The host already declares the needed render features:
`benchweave_sdk_server/presentation.py` `SUPPORTED_FEATURES` includes
`plots.time-series`, `plots.waveform`, `plots.digital-lanes`, and reading tiles
render through the installed `benchweave-ui-html` partials (`render_reading`) —
the renderer package is untouched by this slice.

**Q3 — What is the falsifier?** See §4 (the exact failure shape) — a
schema-valid, `check-ui`-clean manifest whose render is stripped must fail with
`classref_gate_missing: <component> on <page>: expected N, censused M`.

**Q4 — Is a rendered comparison necessary at all, or would the composer plus a
component inventory prove it more cheaply?** The rendered comparison is
necessary and already built; what would NOT prove it: the composer (pattern
pages) pins hand-authored HTML against hand-derived counts — it executes
neither the derivation nor the host; the mockup census likewise; the
composition gate proves identifier hygiene at the document level only. The
cheapest mechanism that actually tests production is the existing gate plus the
expander widening — **no new gate is built by this slice.**

## 2. New findings from this design pass (reported, not fixed here)

### 2.1 The gateway L4 fallback mis-derives every non-founding plot kind

`src/benchweave/presentation/classref.py::_assemble_documents` (lines
1136–1450) emits the page plot **unconditionally as `digital_lanes`** (the
`plots.append({... "kind": "digital_lanes" ...})` at line ~1401): the emission
reads `plot_spec["over_slot"]` and `plot_spec["group_radix"]` but never reads
`plot_spec["kind"]` — `time_series` and `waveform` have zero occurrences in the
module. The gateway-side derive tests exercise selection over all eight classes
(`tests/presentation/test_classref_derive.py`) but pin no waveform/time_series
derivation. Consequence: the no-manifest fallback — which the L17 record says
makes the class reference "the plugin's served presentation the moment the
batch lands" for a real shipped daq plugin — serves a `digital_lanes` plot over
a waveform dataset (six analogue voltage channels as hex lane groups). This is
a live, unpinned mis-derivation on the gateway's serving path. It is NOT this
slice's motion: gateway serving is production motion, the finding needs the
owner's call, and this slice's gate runs SDK-side (where the same widening must
land anyway — the two derivations are deliberate mirrors, the composition
record's `_urn_for_binding` note being the precedent). **Deferral D2.**

### 2.2 The scaffolded UI-GUIDE omits verify-ui

`UI-GUIDE.md` documents `check-ui` and `preview-ui` but not `verify-ui` (only
the plugin-ui SKILL.md carries it). Gap 2's "workflow stops at schema gates" is
half-addressed in the human-facing guide. **Deferral D3.**

## 3. The mechanism

One slice, two repos, ordered by the #408 rule (SDK PRs merge → SDK release cut
→ gateway pointer PR).

### 3.1 SDK: widen the expander (the gap-1 dependency, accounted for)

`packages/sdk/src/benchweave_sdk/classref.py`:

1. **Counter inventory.** Extend `_EXPECT_NAMES` and `_build_expectation`'s
   inventory with the five corpus counters. Derivation rules, pinned from the
   corpus's own semantics (README 0.3.0 §Class reference documents) and
   cross-checked against the gateway tests' `_structural_counters`
   derivations (`tests/ui_html/test_classref_dc_psu.py:71-77`,
   `test_classref_daq.py`'s capture variant), computed over the real
   derivation inputs — never test-side:
   - `n_source_channels` — the channels slot's role-resolved channel count
     (the `_resolve_channels` output);
   - `n_scalar_variables` — one per (channel, declared quantity) of the
     dataset slot's resolved channels (scalar variables of the measure/
     capture dataset);
   - `n_reading_tiles` — equals `n_scalar_variables` (one tile per scalar
     variable; the L11 rule the corpus authors);
   - `n_analogue_channels` — the capture classes' role-resolved channel count;
   - `n_trace_variables` — one per (channel, declared quantity) of the
     waveform dataset's array-valued trace variables.
2. **Plot emission by kind.** The page-template plot emission reads
   `plot_spec["kind"]`: `digital_lanes` keeps its existing machinery verbatim;
   `time_series` emits the plot over the dataset slot with one series per
   scalar variable (`series: "numeric_variables"` — the closed rule);
   `waveform` emits over the dataset slot with one trace per (channel,
   declared quantity) array-valued variable over the explicit time axis. The
   manifest schema admits all three (`standards/plugin-ui/0.4.0/
   ui-manifest.schema.json:184` — `waveform` in the plot kind enum), the
   scaffold's own manifest already ships a `time_series` plot
   (`scaffold_expected/.../ui/manifest.json:23`), and the host declares the
   features (`SUPPORTED_FEATURES`). No schema motion, no host motion.
3. **Readings-page derivation.** Observation bindings on readings pages and
   the reading-tile layout expansion (one rendered tile per scalar variable —
   the layout child `{"binding_id": "measure", "kind": "reading-tile"}` expands
   to `n_reading_tiles` rendered tiles), mirroring the reference layout
   blocks' authored structure.
4. **Refusals stay closed.** An expect expression outside the widened set
   still refuses `classref_expect_expression` (the grammar is corpus-defined;
   the SDK adds no names the corpus does not carry).

### 3.2 SDK: widen the gate census

`packages/sdk/src/benchweave_sdk/classref_gate.py`:

- `_CensusParser` counts the `bw-reading` and `bw-plot` class hooks (the §E.1
  roots `render_reading`/`render_plot` emit);
- `census_map` gains `reading-tile` → the reading count and `engineering-plot`
  → the plot count (the §E.1 component names the corpus's expect blocks use).

### 3.3 SDK: the per-class render arms (the gap-2 core)

Parameterise `packages/sdk/tests/helpers_classref.py::build_classref_project`
by `(profile_id, descriptor_fixture)` — the scaffold/swap/derive shape it
already has, minus the hardcoded analyser pair. New test module (shape:
`test_classref_render_arms.py`), one arm family per class over the eight
vendored OTDP examples (`packages/sdk/src/benchweave_sdk/standards/otdp/0.2.3/
examples/class-*.json` — all eight exist in-tree):

1. **Clean arm** — scaffold the synthetic project, swap in the class example
   descriptor, derive, write the derived set, run `verify-ui` through the CLI:
   zero findings (the rendered census equals the resolved expect; the coverage
   arm clean; reported deviations exactly the birth ledger's).
2. **Strip falsifier** (per class, at least one primary surface) — mutate the
   DERIVED manifest (never the corpus, never the descriptor: both sides derive
   from those, so mutating them moves expectation and render together): remove
   the layout section that places the plot, or the layout's reading-tile
   children. The mutant stays schema-valid and `check-ui`-clean — gap 2's
   premise verbatim — and renders an incomplete page.
3. **Reference-side kill** — flip one count expression in a copy of the
   reference (e.g. `1` → `2` on a data-table row): the clean arm reds. This is
   the direction that catches a render that quietly OVER-delivers or an
   instrument that rubber-stamps.
4. **RED-sanity** — run the falsifier arms once against a neutralized detector
   (the census patched to count nothing): they must go green, proving the arms
   discriminate (G3; the composition gate's precedent, §3 of that record).
5. **Specificity** — the smu arm additionally asserts the sweep-block absence
   (no sweep surface renders; the deferred actions surface as Device-features
   REPORTED rows), carrying the L16 record's named deferral as a live
   assertion; the function_generator arm asserts no plot and no reading tile
   renders (the measurement-free class).

The arms discover the family the way the composition gate does — by walking
the ACTIVE family's `class-*.json` (the census instrument's
`family_profile_ids` pattern), never a frozen list: a ninth class joins the
arm set automatically, and its absent arm is a coverage failure, not silence.

### 3.4 Gateway: pointer only

The design record (this file), then after the SDK release cut: the pointer PR
advancing the gitlink and the `.gitmodules` pin in the SAME commit (#408;
`sdk-drift` reds otherwise; the release-time pairing walk reads the
`::warning::`).

## 4. The exact failure shape (the falsifier, written down before it runs)

A page that renders wrong fails `verify-ui` with one typed finding per
divergence, each naming the component, the page, the expected count and the
censused count — the existing `_assert_expect` emission, now reachable for the
readings/capture components:

```
classref_gate_missing: reading-tile on output: expected 6, censused 0
classref_gate_missing: engineering-plot on output: expected 1, censused 0
```

(and the mirrored `classref_gate_excess` for over-rendering; the coverage arm's
`classref_gate_uncovered: <urn> renders no control at <level>` unchanged). The
premise arm demonstrates, on today's gate, that the stripped mutant passes
`check-ui` — that demonstration is part of the falsifier test, so the gap the
issue named stays visible in the suite.

## 5. Pre-committed acceptance rule (written before any arm ran)

Metric: `verify-ui`'s rendered-census-vs-expect assertion, per class, through
the real standalone host. Sample: the whole active family — 8 classes, stated
by assertion over the discovered family, never a literal (a ninth class widens
the sample by itself).

**SHIPS if all five hold:**
1. Every class's clean arm is green through the real host (zero findings,
   reported deviations exactly the birth ledger).
2. Every class's strip falsifier REDS with the §4 shape (component + page +
   expected + censused).
3. Every reference-side count-flip kill REDS the clean arm.
4. RED-sanity: the neutralized detector turns every falsifier green (the arms
   discriminate).
5. The founding class's existing gate tests (`test_classref_gate.py`,
   `test_classref_cli.py`, `test_classref_expand.py`) pass unchanged — no
   assertion weakened, no fixture edited.

**KILLS if any of:**
- (a) a clean arm cannot go green without editing a corpus byte or weakening
  an existing gate assertion — the expander cannot derive what the reference
  authors; that is a corpus/expander design conflict for the owner, not a test
  to tune;
- (b) any strip falsifier passes the gate — the gate is a claim, not a guard,
  and the slice has failed its purpose;
- (c) the arms pass only by pinning integer literals where the corpus authors
  expressions — instrument failure, not conformance.

**UNDERPOWERED, not conclusive:** a clean arm reds because the HOST cannot
render a surface the schema admits (a §E.1 partial absent, a feature refused
at load). That is a discovered host defect, not evidence about the gate; the
class's acceptance converts to that defect's finding and escalates — the rule
is never tuned to make it pass. Same ruling if the neutralized detector fails
to turn a falsifier green (the neutralization itself is broken — fix the
harness, re-run, then judge).

## 6. Deferrals (the deferral-row contract, `.claude/deep-review/README.md`)

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | Composed (multi-class) render verification — the gate still derives `references[0]` (`classref_gate.py::_derive_for_project`); the three composition-record §4 hazards (first-channels-slot, global slug resolution, expect overwrite) stay ungated | follow-on work under issue #500's reported-hazards ruling | the owner's ruling on the composition record §4 rows arriving, or the fix train that ruling opens |
| D2 | The gateway L4 fallback's unconditional `digital_lanes` emission (§2.1) — gateway serving motion | follow-on gateway issue, filed on this tracker at build time | the owner's call on this record's §2.1 finding; nearest plausible carrier: the daq consumer's serving leg |
| D3 | `verify-ui` in the scaffolded `UI-GUIDE.md` (§2.2) | documentation — the scaffold-guide leg of issue #463 row 3 | the next scaffold/docs motion touching `UI-GUIDE.md` |
| D4 | The smu sweep-block surfaces | the corpus's own named deferral (`sweep-surfaces` ledger row, L16 record) | the sweep landing slice (the corpus record's own trigger) |

## 7. Precedent

No new architecture. Every piece extends a proven in-tree mechanism: the gate
itself and its render half (L2/L5, released); the per-class arm shape
(`helpers_classref.py`, parameterised); the counter derivations (the gateway
tests' `_structural_counters`, now computed expander-side over the real
derivation); the family-discovery pattern (`classref_census.py::
family_profile_ids`, the composition gate's rotation rule); the RED-sanity
discipline (composition record §3, rubric G3). The one precedent question —
why not gate the composed devices now — is answered by the composition record
itself: gating on readings the owner has not ruled on was refused there, and
this slice inherits that refusal (D1).

## 8. Invariant and drift impacts

- **No CTL/STO/CON/REG invariant changes and no new invariant.** The slice is
  SDK presentation tooling; the gate's existing honesty lines carry (clean is
  never admission; unknown names refuse; the D7 carve-out untouched). CON-12
  (the SDK mirror) rides the pointer-PR mechanics as on every SDK bump.
- **Surfaces that move:** SDK package (`classref.py`, `classref_gate.py`,
  tests, CHANGELOG, version 0.17.0 → 0.18.0 — a MINOR: new capability, no
  breaking face); gateway pointer (gitlink + pin, same commit). No
  `standards/` byte moves; no `docs/` obligation fires; the ui-html package
  and both hosts are untouched; MCP/REST/CLI gateway surfaces untouched.
- **Obligations walked:** #408 order rule (SDK merge → release cut → pointer);
  `make check-sdk-standards` unaffected but run on the pointer PR;
  `sdk-drift` lane green with pin == the released tag (a `::warning::
  pairing pending` is expected until the release-time walk); the
  gateway-side class tests' deferral notes ("the SDK widening's") become
  stale in the happy direction — updating them is NOT an obligation, noted as
  courtesy for the pointer PR.
- **CI cost:** ~16–24 additional in-process ASGI renders in the SDK's test
  lane (each a `TestClient` over `build_app`, sub-second — the existing 18
  `verify-ui` test calls already set the cost shape); gateway CI gains only
  the pointer lane's usual run. No new job, no browser, no network.

## 9. Tier statement (Step 1, rule #254)

**Gateway-side diff: Tier 3** — first match on "advances the `packages/sdk`
submodule pointer" (the pointer PR); the design record itself is docs-only
Tier 1. The standards-governor pass is owed on the pointer/release leg (the
SDK release's version strings and the gitlink), regardless of tier.
**SDK-side diff:** its own repository's review under its rules; expected
Tier-2-shaped (production + test code under its `src/`/`tests/`).

Keyword scan over the expected diff text (this record — the docs half of the
expected diff, docs and code prose alike — scanned 2026-10-21): the eight
Step-1 keywords occur exactly in this section's own enumeration (the #254
self-fire, intended); zero occurrences elsewhere in the record. The expected
CODE half (the expander/census widening, the arms, the pointer commit)
carries all eight keywords zero times by design — no hashlib/sha256 hunk in
the widening (the existing digest lines are not in the expected hunks), no
threading/asyncio/subprocess/migrate/recovery/protection text. The build leg
re-runs the scan over the actual committed diff before review; the review
re-derives the tier independently (rubric #254).

## 10. Top risks, each with what would falsify the design

1. **The expander widening discovers the corpus references are not derivable
   as authored** (a counter's derivation rule ambiguous across classes, a
   readings-page binding shape the manifest cannot express). Falsifier:
   acceptance-rule kill (a). Mitigation: the corpus records pinned each
   class's derivation arms by name (L11 §"the expansion-side arms"), and the
   gateway pattern pages already hand-computed every class's expansion — the
   rules exist in committed prose; the widening implements them, and any
   residue escalates rather than tunes.
2. **The strip falsifier cannot stay `check-ui`-clean** (a schema wrinkle
   makes the layout-strip mutant invalid). Falsifier: the premise arm fails
   its own setup. Mitigation: the strip targets the layout block (extension,
   canonical-validator-blind) — the degrade-by-ignoring seam the host already
   documents; if a chosen strip cannot stay clean, the arm switches surface
   (plot placement vs tiles), and the premise demonstration moves with it.
3. **Mock-exchange coverage gaps** — `mock_exchanges(plugin)` may not feed
   the readings pages of the new classes (empty tiles render, census counts
   still assert — counts are structural, values are not). Falsifier: clean
   arms red on `classref_gate_missing` with a host-side cause (the
   UNDERPOWERED clause). This is the designed escalation path, not a failure
   of the rule.
4. **The two derivations diverge** (SDK widened, gateway left behind — the
   §2.1 finding made structural). Accepted for this slice by design (D2);
   the risk is drift amnesia, mitigated by the finding being carried in two
   deferral tables (D1's record and D2's issue at build time).

## 11. The gate commands the build must run

SDK repository (its lanes, `UV_PROJECT_ENVIRONMENT=venv`, evidence from true
exit codes / junitxml — never a filtered summary line):

```
UV_PROJECT_ENVIRONMENT=venv uv run ruff check .
rm -rf .mypy_cache && UV_PROJECT_ENVIRONMENT=venv uv run mypy   # bare, fresh cache
UV_PROJECT_ENVIRONMENT=venv uv run pytest packages/sdk/tests/test_classref_gate.py \
  packages/sdk/tests/test_classref_expand.py packages/sdk/tests/test_classref_cli.py \
  packages/sdk/tests/test_classref_render_arms.py -v           # focused, then
UV_PROJECT_ENVIRONMENT=venv uv run pytest                       # the SDK full battery before the release cut
```

Gateway repository (the record commit, then the pointer PR):

```
UV_PROJECT_ENVIRONMENT=venv uv run ruff check .
rm -rf .mypy_cache && UV_PROJECT_ENVIRONMENT=venv uv run mypy
UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/ui_html tests/presentation   # FAST-lane focused set
UV_PROJECT_ENVIRONMENT=venv uv run pytest                                     # full battery + both standards tripwires before the pointer PR
make check-sdk-standards                                                      # on the pointer PR
```

The pointer PR merges on the full `gh pr checks` rollup — zero fail, zero
pending — per CLAUDE.md §3.5.
