# Issue #449 — Preview host fidelity: lane data, gateway style, plot controls (design record)

**Date:** 2026-10-12
**Branch:** `feat/issue449-preview-fidelity` (off `origin/main` @ `1e49e2c5`)
**Issue:** madeinoz67/benchweave#449 (`sdk` label)
**Verdict:** BUILD — sliced so the owner's binding fix direction (the standalone host
renders THROUGH ui-html) ships first with **zero standards motion**, and the two
data/vocabulary legs ride named later slices. The issue's third premise (the plot
vocabulary lacks zoom/scroll/trigger fields) is **corrected rather than built**: the
mechanism those features need is host composition over the composer's existing model,
not manifest vocabulary (§3.3, deferral D4).

**Review tier (design-time call, rubric #254):** stated per slice in §9; the maximum
across slices is **Tier 3**. Slice 2 touches `standards/` and adds JSON Schema bytes
(the path rule); slices 1 and 3 are SDK-repo-only but their expected diffs carry the
`sha256` keyword (asset-digest verification code), which fires the Tier-3 keyword rule
there by the gateway rubric's analogy; the gateway-repo pointer commit that eventually
carries slice 2 is Tier 3 by the submodule-pointer rule. The standards-governor mandate
applies to slice 2 and to every pointer motion. Keyword-scan counts in §9.

---

## 0. Summary

The standalone preview host (`benchweave_sdk_server` in the SDK repo) already composes
scalar plots and reading tiles through the installed `benchweave-ui-html` package; the
owner's evidence (issue comment 6123109444) localises the fidelity gap to three exact
places, all verified in this read:

1. **Theme.** The host serves the package's token/theme/global stylesheets byte-for-byte
   (`benchweave_sdk_server/assets.py:31` — `RENDERER_ASSETS = {tokens.css, themes.css,
   globals.css}`, served from the installed package at
   `benchweave_sdk_server/web.py:1770-1774`) but never loads `bw-host.js`, the package's
   host script that sets the root `data-theme` from `prefers-color-scheme`
   (`packages/ui-html/src/benchweave_ui_html/assets/bw-host.js`, theme block). The
   gateway console's shell loads it
   (`src/benchweave/interfaces/ui_templates/base.j2:15`). With `themes.css` keyed on
   `[data-theme]`, preview is structurally always-light.
2. **Lanes.** The host's plot wrapper hardcodes a hand-built digital-lanes skeleton
   (`benchweave_sdk_server/plots.py:173-189`) — the ONLY place the host bypasses the
   package renderer — while the package ships the complete composition module
   (`packages/ui-html/src/benchweave_ui_html/lanes.py` — `compose_lanes` over
   `LaneSpec`/`LanesDeclaration`, bus radix formatting, state segments, decoder spans,
   `trigger_s`, cursors) and template (`templates/digital-lanes.j2`, exposed as
   `partials.render_lanes`). No production consumer of `render_lanes` exists yet; the
   host becomes the first.
3. **Lane data.** The author-fixture loader refuses dataset bindings
   (`benchweave_sdk/src/benchweave_sdk/fixtures.py:136-141`,
   `preview_unsupported_shape`) because the fixture document's binding shape is
   scalar-only by schema (`standards/plugin-ui-preview/0.2.0/fixture.schema.json`,
   `$defs/binding` — `value` is boolean/integer/number/string/null,
   `additionalProperties: false`). Fixtures cannot carry a capture, so preview cannot
   show lane data even as simulation.

The fix is wiring, not capability (the owner's conclusion, confirmed): slice 1 makes
the host render lanes through the package, serve and load the theme script, and gains a
digest-pinned local-override surface scoped to preview. Slice 2 (a `plugin-ui-preview`
0.2.1 PATCH standards motion) lets fixtures carry lane data. Slice 3 adds zoom/scroll as
htmx partial swaps — host-side viewport state, no vocabulary.

## 1. What this design is NOT

- It does not change what the gateway renders. The standalone host is a separate
  package (`benchweave_sdk_server`) in a separate repository; the gateway's `/ui`
  transport never reads a plugin's asset tree, and the local override of §3.1.4 is
  consumed only by the preview host's page composition. "Never changes what the
  gateway renders" is structural (different package, different route tree), not
  policy-checked.
- It does not move `plugin-ui` bytes. The digital_lanes plot vocabulary
  (`standards/plugin-ui/0.3.0/ui-manifest.schema.json` `$defs/plot`: kind, binding_id,
  x, y, channel_hints, lane_groups, decoder_lanes) is untouched by all three slices
  (§3.3 argues why the named "missing fields" are not needed for the features).
- It does not require a `benchweave-ui-html` release. The SDK pins
  `benchweave-ui-html==0.2.1` (`benchweave-sdk/pyproject.toml:55`), and 0.2.1 already
  ships every asset this design serves: `bw-host.js` (added in 0.2.1 per the package
  changelog comment in `packages/ui-html/pyproject.toml:9-10`), `sse.js`, tokens,
  themes, globals — pinned by `tests/ui_html/test_vendored_js.py:34`'s inventory set.
  Obligation 12's pin-mediated motion rule is satisfied by the existing pin; no bump.

## 2. Root cause (established, not assumed)

The host predates the lanes renderer. When `digital_lanes` shipped (issue #244 S2), the
host's wrapper got a disclosure skeleton because captures were deferred to I3
(`plots.py` docstring: "live lane data is I3's (D-I2b) and the wrapper says so"). The
shell likewise predates the package's host script: `bw-host.js` landed with the G2
console (2026-10-03), after the host's own `bw-events.js` (I2) had taken the
first-party-SSE lane because the vendored htmx-1 SSE extension was incompatible with
htmx 2 (`templates/base.html:25-28`). Both divergences are age, not intent — and the
scalar-plot path proves the intended shape: `compose_page_plot` already calls the
package's `compose_plot`/`render_plot` for time_series/waveform
(`benchweave_sdk_server/plots.py:26,156,212-228`). The lanes branch is the one fork in
an otherwise converged path.

The fixture refusal is the same story one layer down: the fixture schema's binding
model was written for the snapshot data model (one simulated scalar per observation
target — `fixtures.py:137-139` states it), and `generate_baselines` already degrades
honestly for non-observation targets (`fixtures.py:258-263`), so the vocabulary for a
capture-shaped fixture simply does not exist yet.

## 3. The mechanism

### 3.1 Slice 1 — the host renders through ui-html (SDK repo only; first increment)

> **Addendum 2026-10-12 (post-refute; frozen-record rule — corrections live here, not in the text above).**
> (1) §3.1.2's "the empty path is total" cites the wrong mechanism: `lanes.py:235` indexes
> `member_states[spec.members[0]]` before `reduce_lane`'s empty-sequence guard, so an unbound
> member KeyErrors even for an empty capture. The host's explicit `()` binding is the actual
> enabler (confirmed independently by the mechanism-critic and code review).
> (2) The §3.1.4 override cascade claim is order-only: "after the token stylesheets" wins at
> equal specificity only; `standalone.css` carries (0,2,0) state-kind rules that beat a
> plugin's (0,1,0) override regardless of order. The specificity floor is documented in the
> fold (R1 docs) and pinned by a lint test.
> (3) The 64 KiB cap is a chosen authoring-scale number, not a derived one. Its boundary is
> now pinned by test (65536 admitted, 65537 refused).
> (4) Owner directive 6127477670 (2026-10-12, live preview review), binding the §3.1.5 page
> composition: WAVEFORM FIRST. A capture page carrying digital_lanes leads with the lane
> traces; reading tiles are the secondary surface in the console's layout. Pages without
> lanes plots keep the tile-first shape. Folded as row F8 with its own DOM-order RED arm.

1. **Theme script.** `RENDERER_ASSETS` gains `bw-host.js` (`assets.py:31`); the asset
   route already serves any member of that set from the installed package's
   inventory-verified root (`web.py:1770-1784`), and the package's own
   `verify_vendored_assets()` already runs at host construction
   (`web.py:98-100`), so the new byte set inherits verification with no second digest
   list (`assets.py:41-55` — "one verifier per byte set"). `templates/base.html` loads
   it deferred beside the stylesheets, exactly as the console's `base.j2:15` does. The
   root theme attribute then follows `prefers-color-scheme` — dark parity with the
   console, the owner's rejected-look complaint closed at its actual cause.
2. **Lanes through the package.** Delete the skeleton branch
   (`plots.py:173-189`). For a `digital_lanes` `PlotView`, build a
   `LanesDeclaration` from the projected view (lane specs in declared order — channel
   lanes from `view.channels`, group lanes from `view.lane_groups` with members and
   radix, decoder lanes from `view.decoder_lanes` with `source_channel` set) with
   `acquired=0`, empty `states`, no events, and compose through
   `compose_lanes` + `partials.render_lanes`. The declaration-only render is honest
   and package-owned: lane rows with labels, no segments, and the package's own
   acquisition line ("Acquired 0 samples · plotted 0") — `reduce_lane([], n)` returns
   no columns (`packages/ui-html/src/benchweave_ui_html/decimate.py:65-66`), so the
   empty path is total. The host's disclosure text ("captures begin at I3") dies with
   the skeleton; the package's wording is the one shown.
3. **Hydrator clean-up.** `ui_assets/bw-plot.js`'s `bwHydrateLanes` branch (which
   draws synthetic columns into the skeleton canvas "so the path is exercised") is
   removed with the skeleton: the lanes figure is the package's semantic HTML, not a
   uPlot canvas. The scalar-plot hydration path is untouched.
4. **Local override (owner directive: gateway styleguide default, per-plugin local
   override, preview only).** Surface: the manifest's EXISTING `assets[]` vocabulary
   (`$defs/asset`: `{id, path, sha256}` — `standards/plugin-ui/0.3.0/ui-manifest.schema.json`,
   root property `assets`). The host convention: a declared asset whose `path` is
   `preview.css` is served as an override stylesheet, inserted AFTER the package's
   token stylesheets, only on the preview host's pages. The manifest's own digest
   discipline verifies the bytes before serving (`hashlib.sha256` against the declared
   pin — same posture as `assets.py`'s existing verifiers), with a size cap (64 KiB)
   and `text/css` content type. A plugin that declares no such asset renders pure
   gateway tokens — the default. This is fork F1 (§10) with the recommended option
   taken: no new vocabulary, digest-pinned, explicit declaration.
5. **Region structure.** The lanes figure moves out of the 2-second readings poll
   region (`templates/page-readings.html:27` renders `plots` inside the polled div;
   `templates/page.html:11-16`). Precedent is the page's own controls rule — "a poll
   must not wipe an operator's in-flight input" (`page.html:18-20`); extended here: a
   poll must not wipe viewport state. The lanes figure gets its own wrapper element
   (no poll trigger) now, so slice 3's zoom/scroll swaps land on a stable target
   without re-deriving page structure. Scalar plots stay in the poll region (their
   data is the ring, which is poll-shaped).
6. **Component CSS.** The lanes realization (segment geometries, glitch marks, bus
   cells) lands in the host's `standalone.css` per obligation 26's inheritance rule —
   hosts design their own component CSS; the pattern library's page CSS is not shipped
   machinery. The §E.4 constraints carry over: monochrome-discriminable state kinds
   (high/low/hatch/midline as geometry, never colour-only), token-referenced colours
   (`var(--bw-*)` only — no literals), no glow on normal readings.

### 3.2 Slice 2 — lane data in preview fixtures (plugin-ui-preview 0.2.1 PATCH train)

> **Addendum 2026-10-12 (slice-2 constraints from the refute; binding at slice 2's build, each
> with its own RED arm in slice 2's pre-committed acceptance rule).**
> (1) Sample rate is REQUIRED whenever `trigger_s` or cursors are present: `compose_lanes`
> maps `round(t * (rate or 0.0))`, so a rate-less trigger silently stacks at sample 0
> (executed: trigger 2.5s, cursors (1.0, 4.0), rate None → all at sample 0).
> (2) An OMITTED capture member must refuse loudly at load — "member missing from the capture"
> must never launder into "member captured empty". The slice-1 empty-binding is correct only
> because fixtures carry no captures.

A new `plugin-ui-preview` corpus version 0.2.1 (copy-never-move of 0.2.0) whose
`fixture.schema.json` gains an OPTIONAL `captures` member: a per-fixture array of
capture blocks keyed by dataset binding id, each carrying the composed-ready lane model
— per-lane state strings over the `LaneState` alphabet (`0`/`1`/`x`/`z`), the sample
count, an optional sample rate, an optional trigger time, bus radix carried by the
manifest's existing `lane_groups`, and decoder events as `(start_s, end_s, payload)`
triples. Additive and optional at the document root: no previously-valid fixture is
refused, so the bump class is PATCH under GOVERNANCE's change-class table — the exact
shape of the plugin-ui-preview 0.1.0→0.1.1 precedent (issue #67, governor verdict
COMPLIANT, "PATCH class additive-only").

The SDK loader (`fixtures.py`) admits capture blocks for bindings whose target kind is
`dataset`, cross-checked against the binding catalogue (unit/rate consistency where the
catalogue declares them), and the host composes `LanesDeclaration` from the selected
scenario's captures — the same `compose_lanes` path as slice 1, now with states. The
served wire document (`preview-document.schema.json`) is NOT extended in this slice:
`plot_views` stays declared-structure-only and scenarios stay scalar-observation-shaped;
captures are a fixture-side input, not a wire surface. This keeps slice 2 to ONE schema
file in ONE family. The wire-side question (should the served document carry capture
data for conformance testing?) is deferral D7.

Two-repo discipline for slice 2 (the standing order, issue #408): gateway-side corpus
motion first (`standards/plugin-ui-preview/0.2.1/` + manifest rows + range slide —
plugin-ui-preview's range is `>=0.1.1,<0.3.0` and multi-serving, so 0.2.1 widens the
window without sliding it), then `make sync-sdk-standards` (SDK lock + vendored tree),
SDK PR merges → SDK release cut (`make release-cut VERSION=x.y.z` in the SDK repo) →
gateway pointer PR advancing gitlink + `.gitmodules` pin in the SAME commit. The
mid-sequence red window (corpus bump red until SDK sync lands) is disclosed, not
adapted around.

### 3.3 Slice 3 — zoom/scroll and the trigger marker (SDK repo only)

Zoom and scroll are VIEWPORT state over composed columns: an htmx partial endpoint
(`/pages/{page_id}/lanes/{view}` with `from`/`to` window parameters) that recomposes
the same declaration against the windowed column budget and swaps the figure — the
server-side-partial architecture the owner directed, and the one the host already uses
for readings (`page.html:11-16`). The trigger marker and cursors are DATA the composer
already models (`LanesDeclaration.trigger_s`, `cursors` — `lanes.py:91-105`,
"presentation-only: positions are host-supplied"): in preview they ride slice 2's
capture blocks; on the live path the acquisition supplies them.

This is why the issue's premise three is corrected rather than built: the plot
vocabulary would only need zoom/scroll/trigger FIELDS if a plugin were to DECLARE
viewport state or trigger positions, which is presentation preference at best and
capture data at worst — neither belongs in a data-declaration vocabulary whose every
existing member (kind, binding, axes, channels, hints, groups, decoders) declares DATA.
`channel_hints` is the precedent for how preferences enter that vocabulary: only with
evidence they are plugin knowledge. Deferral D4 carries the burden of that evidence.

## 4. Minimal first increment and explicit deferrals

**First increment = slice 1 (§3.1), in full.** It is the owner's binding directive,
needs no standards motion, no package release, no train coordination, and is
independently shippable and provable (§7).

Deferrals, each with its carrier:

| # | Deferred | Carrier |
|---|----------|---------|
| D1 | Lane data in preview fixtures (the `captures` extension and loader admission) | Slice 2 of this issue — plugin-ui-preview 0.2.1 PATCH train (§3.2) |
| D2 | Zoom/scroll viewport partials and windowed recomposition | Slice 3 of this issue — SDK repo only (§3.3) |
| D3 | SSE-delivered live lane updates (fragment-push semantics, `data-bw-stream-url` wiring) | Slice 3 or the I3 live-capture work, whichever consumes it first; the host's `/events` advisory stream is unchanged meanwhile |
| D4 | Plot-vocabulary zoom/scroll/trigger DECLARED fields | A future `plugin-ui` bump ONLY with evidence that viewport/trigger defaults are plugin knowledge (§3.3); until then the composer's host-supplied model is the mechanism |
| D5 | Live capture path: dataset→`LaneSpec` projection and decoder-lane events from real acquisitions | #443's SDK follow-on + the I3 capture work (§8, dependency statement) |
| D6 | Gateway-console rendering of digital lanes (the `/ui` transport renders no plots today) | Not this issue; the console's plot surface is its own design when demanded |
| D7 | Serving capture data on the preview wire document | Revisited with the first conformance consumer that needs it; slice 2 deliberately keeps the wire unchanged |

## 5. Precedent

- **Scalar plots through the package**: `compose_page_plot` itself
  (`benchweave_sdk_server/plots.py:26,156,212-228`) — slice 1 generalises its own
  sibling branch.
- **Reading tiles through the package**: `benchweave_sdk_server/presentation.py:28-43`
  imports `benchweave_ui_html` partials/staleness — the convergence pattern exists in
  the same module family.
- **Asset serving from the installed package**: `assets.py:27-55` + `web.py:1770-1784`
  — slice 1 extends the existing `RENDERER_ASSETS` set, one member.
- **Console shell wiring**: `src/benchweave/interfaces/ui_templates/base.j2:15` loads
  `bw-host.js` from the package inventory — the exact wiring copied.
- **Fixed-resource conventions under the plugin resource root**: the fixtures
  directory (`benchweave_sdk/presentation.py:557`, `fixtures.py:222`) — the local
  override's consumption point follows the same resource-root discipline, upgraded to
  manifest-declared digest pinning (fork F1).
- **htmx partial swaps for view state**: the host's own readings partial
  (`page.html:11-16`) and the console's §C.3 partials — slice 3's zoom endpoint is the
  same mechanism with different parameters.
- **Fixture-schema additive PATCH**: plugin-ui-preview 0.1.0→0.1.1 (issue #67) — the
  class argument and governor posture slice 2 reuses.

## 6. Invariant and drift impacts

- **CON-4 / obligation 6** (vendored tree ↔ lock ↔ manifest): slice 2 only; the
  corpus-manifest rows for plugin-ui-preview 0.2.1 move with the vendored bytes in the
  same train, `make check-sdk-standards` green only at train completion (the disclosed
  mid-sequence red window).
- **Obligation 7 / `sdk-drift` lane** (submodule pointer): slice 2's pointer PR
  advances gitlink + pin in one commit; the lane's tag-vs-gitlink equality is the
  mechanical check.
- **Obligation 12** (UI/preview renderer surface): satisfied WITHOUT motion — the
  contract harness (`docs/internal/ui-contract.md` rows collected via `testpaths`)
  pins the lanes HTML shape in the gateway repo; the SDK host renders through the same
  package, so no contract-table edit is needed for slices 1/3. Slice 2's fixture schema
  is a plugin-ui-preview corpus file, not a ui-contract row.
- **Obligation 18** (version-bearing-surface census): slice 2 adds the 0.2.1
  version-bearing rows (corpus manifest, standards manifest range, SDK lock, MIGRATION
  note) — the census row's motion mechanisms apply unchanged.
- **Obligation 20** (version-literal zero gate): slice 2's consts sweep runs in the
  same change (fixture schema `$id`/`contract_version` consts; no executable literals
  introduced by slices 1/3).
- **plugin-ui's narrow-range D2 wall** (vault: "plugin-ui range must slide narrow at
  every bump"): NOT triggered — no plugin-ui motion in any slice. Explicitly recorded
  because the issue's framing ("extend the plot vocabulary") implied one.
- **On-disk formats**: slice 2 introduces a standards corpus version directory
  (JSON Schema) — this is what makes the train Tier 3 in the gateway repo. Slices 1/3
  touch no persisted format.
- **CI cost**: slice 2 pays the standards-train cost (corpus red window, sync, pointer
  lane); slices 1/3 add SDK-repo tests only (~6 focused tests, no new lanes).

## 7. Measurable proof — pre-committed acceptance rule

Written before any build runs. All three slices share AR-1's shape; the numbers below
are slice 1's (the first increment's gate).

**AR-1 (fidelity by construction — primary).** For a fixed authored manifest fixture
declaring 3 channel lanes, 1 bus group (2 members), and 1 decoder lane (declared
structure, no data), render the host's page via the HTML route and extract the
`<figure class="bw-lanes">…</figure>` element; render
`partials.render_lanes(compose_lanes(declaration))` in-test from the same projected
view. Metric: byte equality of the two strings. Sample: the fixture's page across both
generated baselines plus one authored scenario = 3 rendered pages.
- **Ship:** 3/3 byte-equal AND zero occurrences of the string `captures begin at I3`
  anywhere under `benchweave_sdk_server/` AND the extracted figure carries the
  harness-pinned §E.4 literals (`data-bw-lane`, `data-bw-lane-kind`,
  `data-bw-acquisition`, `bw-lanes__label`).
- **Kill:** any byte inequality traced to host-authored lane markup — the host still
  owns presentation bytes; fix before ship or kill the lanes arm (theme + assets still
  ship; the record is amended with the evidence). If the only inequality is
  host-injected wrapper attributes OUTSIDE the figure element, the weakened rule
  applies (all pinned literals present, zero host-authored lane-element children) and
  the weakening is disclosed in the PR body — a silent weakening is the failure this
  rule exists to catch.
- **Underpowered, not conclusive:** if the declaration-only render cannot exercise the
  decoder-lane span arm (empty events), the rule covers channel+group only and the
  decoder arm moves to slice 2's AR with that disclosure — a pass without the decoder
  arm says nothing about decoder rendering.
- **RED control (AR-3, same gate):** revert ONLY the `plots.py` change in place, keep
  the tests: AR-1 must fail (the figure is the hand-built skeleton: byte-diff, missing
  literals) and the no-`I3`-string grep must fail. Restore: both green. A test that
  passes both ways is unproven and blocks ship.
**AR-2 (theme/asset parity).** `GET /assets/bw-host.js` returns 200 with bytes
byte-identical to the installed `benchweave_ui_html` package's asset (read via the
package's `ASSETS_DIR`), and the served page's `<head>` references it. RED control: at
the pre-change commit the route 404s (the asset is not in `RENDERER_ASSETS`), so the
new test reds against HEAD~ without touching the test.
**AR-4 (override scoping).** A plugin declaring `preview.css` in `assets[]` gets it
served on its preview page after the token stylesheets; a tampered `preview.css`
(digest mismatch against the declared `sha256`) refuses serving with a
machine-matchable prefix and the page renders default tokens. The gateway `/ui`
transport is asserted (existing suite shape) to expose no route that serves plugin
assets — the structural preview-only boundary.

Slice 2's AR (same pre-commit discipline, restated at its build): a fixture with a
2-lane capture (states `0011x`-shaped, one decoder event) renders through the same
AR-1 byte-parity over a DATA-BEARING declaration, plus a schema-refusal arm (a 0.2.0
validator refuses the `captures` member; the 0.2.1 validator admits it) — the
issue-#62 governance shape (reproduce both refusal deltas with real validators).
Slice 3's AR: a viewport request windowing to the second half of a capture yields a
figure whose `data-bw-acquisition` reports the windowed counts, and the un-windowed
figure is unchanged — plus a poll-isolation arm (a readings poll swap does not change
the lanes region's DOM identity).

## 8. Issue #443 dependency statement

#443 (OTDP 0.2.3 decoder-output contract) is HELD at its evidence gate. Its record
(`feat/issue443-decoder-output-contract:.claude/deep-review/2026-10-12-issue443-decoder-output-contract-design.md`)
lands an annotation-form `event_log` dataset shape for `decode_annotated/1.0.0`. #449's
dependency on it is REAL but NARROW: the LIVE decoder-lane data path (a real
acquisition's decode events flowing into `DecoderEvent` spans) consumes #443's
contract (deferral D5). Everything in slices 1-3 is structurally independent of it:

- Slice 1 renders DECLARED structure only — no dataset consumed.
- Slice 2's preview decoder events are fixture-supplied `(start_s, end_s, payload)`
  triples, the composed-ready `DecoderEvent` shape. They deliberately do NOT
  re-encode #443's class/row model: in preview the fixture IS the rendered data, so
  the generic-rendering problem #443 solves (drawing without decoder knowledge) does
  not arise. When #443 lands, the live path's projection maps its annotation rows onto
  the same triples — one adapter, carried by D5.
- The channel-lane live path needs only the raw capture dataset form that OTDP 0.2.2
  already defines; it is not blocked by #443 either.

Therefore #449 does NOT wait on #443. The one coupling to watch: if slice 2's capture
block vocabulary and #443's annotation vocabulary drift apart in naming (e.g. payload
encoding), the D5 adapter widens. The design constrains slice 2 to #443's already-filed
names where they exist (`start_s`/`end_s`/payload-as-hex-string), so the adapter stays
a projection, not a translation.

## 9. Tier call and Step-1 keyword scan (rubric #254)

Per slice, maximum Tier 3:

- **Slice 1** (SDK repo): Tier 3 by keyword — the expected diff's override-verification
  code reads the manifest asset's `sha256` and hashes the bytes (`hashlib`), firing the
  keyword rule; no path rule fires (no `standards/`, no schema, no pointer). Scan over
  the expected diff text (plots.py rewrite + assets.py + base.html + standalone.css +
  bw-plot.js + override loader + ~6 test files): `sha256` x6 (asset-row attribute in
  code, verifier, tests), `hashlib` x2, `threading` x0, `asyncio` x0, `subprocess` x0,
  `migrate` x0, `recovery` x0, `protection` x0.
- **Slice 2** (gateway + SDK repos): Tier 3 by path — `standards/` + a new JSON Schema
  file + the eventual submodule pointer. Scan over the expected diff (0.2.1 corpus dir,
  both manifests, MIGRATION.md, lock, vendored copies, loader, tests, pointer commit):
  `sha256` x8 (corpus-manifest and lock rows), `hashlib` x0, `migrate` x2 (MIGRATION.md
  prose verb), `threading`/`asyncio`/`subprocess`/`recovery`/`protection` x0.
- **Slice 3** (SDK repo): Tier 2 by default (production code under `src/`, no rule
  fires). Scan: all eight keywords x0.
- **This design-record commit** (gateway repo, docs-only): Tier 3 by keyword —
  the record's own text carries the scan words themselves (this §9 list and the
  per-slice scan lines), which is the rubric's intended self-fire, plus the
  digest-verification prose (`sha256`, `hashlib`) and slice-2 corpus discussion.
  Counted over the committed record's bytes, not estimated: `sha256` x9,
  `hashlib` x6, `threading` x3, `asyncio` x3, `subprocess` x3, `migrate` x3,
  `recovery` x3, `protection` x3. (Docs-only would otherwise be Tier 1; the
  keyword rule fires first by design — text that names protective machinery buys
  the protective depth. The per-slice estimates above are PRE-build scans over
  expected BUILD diffs, which will not carry the §9 list itself.)

The counts above are the pre-build estimates over expected diffs; the review re-derives
them from the actual diff, and a disagreement beyond ±2 on any keyword is a record
defect to note, not a silent pass.

## 10. Train-map placement

- **Slice 1 + slice 3: no train.** SDK-repo work at the existing
  `benchweave-ui-html==0.2.1` pin and the existing vendored-standards lock; they ship
  on the SDK's own PR flow (gateway issue linked per the single-issue-stream rule) with
  no standards window, no sync, no pointer. The gateway repo sees no diff from them
  beyond this record.
- **Slice 2: a NEW `plugin-ui-preview` 0.2.1 PATCH train.** It cannot batch into the
  in-flight plugin-ui 0.3.1 train (#444 building + #446 slice 2 batching): that train's
  standard is plugin-ui, its window belongs to #444/#446's scope, and joining an
  in-flight train re-rolls its branches. A train MAY carry two standards (the #244
  precedent bumped plugin-ui 0.2.0→0.3.0 and plugin-ui-preview 0.1.1→0.2.0 together), so the
  sequencing fork is real (F2, §11): the recommendation is a standalone 0.2.1 train
  AFTER the 0.3.1 window closes, keeping one bump per train per standard with no
  cross-family entanglement; the alternative — riding the NEXT combined plugin-ui train
  if one forms before slice 2 is ready — saves a window at the cost of coupling
  unrelated scopes. plugin-ui-preview's bump window is clear (0.2.0's directory was
  created 2026-09-29; the 48h GOVERNANCE window is long past).
- **SDK-side order rule (issue #408)** applies to slice 2 verbatim: SDK PR merges →
  SDK release cut → gateway pointer PR (gitlink + pin, one commit).

## 11. Forks surfaced for the owner (not decided here)

- **F1 — local-override declaration surface.** Taken in-design (manifest `assets[]` +
  fixed-path `preview.css` convention + digest verification): no standards motion,
  explicit declaration, reuses the manifest's own pin discipline. Alternatives
  rejected: a new plugin-ui vocabulary field (a standards motion for a
  preview-host-only concern) and an undeclared fixed-path convention (no digest pin —
  silently different trust posture from every other plugin resource). Overridable.
- **F2 — slice 2's train placement** (§10): standalone 0.2.1 train after the 0.3.1
  window (recommended) vs riding the next combined train. Owner sequencing call.
- **F3 — declared viewport/trigger vocabulary (deferral D4).** This design's position
  is that the issue's "extend the plot vocabulary" recommendation is premature: no
  slice needs it, and `channel_hints` is the bar a new preference field must clear
  (evidence that it is plugin knowledge). If the owner wants declared initial
  viewports regardless, that is a plugin-ui 0.3.x motion to commission separately.

## 12. Top risks, each with its falsifier

1. **The declaration-only lanes render looks empty enough that the owner still rejects
   it** — lane labels with no waveform may read as "still broken". Falsifier: AR-1's
   render inspected by the owner against the pattern library's lanes page; if rejected,
   slice 2 (data) is the actual ask and slice 1 ships as the structural prerequisite it
   is — the record's framing already says so.
2. **Byte-parity is brittle to legitimately host-specific wrapper needs** (e.g. an
   htmx target id on the wrapper for slice 3). Mitigated structurally: wrappers are
   OUTSIDE the figure element; the weakened rule (§7) exists for residual cases.
   Falsifier: an AR-1 failure whose diff is inside the figure and not host markup —
   that is a package determinism bug, escalates to ui-html, not a host fix.
3. **The poll-region restructure (§3.1.5) changes behaviour beyond the lanes figure**
   (ordering, no-data notices). Falsifier: the existing server test family
   (`tests/server/`) plus a new poll-isolation arm; any reading-path behavioural change
   reds there.
4. **Slice 2's capture vocabulary drifts from #443's filed names**, widening the D5
   adapter (§8). Falsifier: the slice-2 build's adapter review — if the projection is
   not a renaming, the vocabulary is re-anchored before merge.
5. **Override CSS is an injection surface** (attribute-selector exfiltration is
   possible in principle with same-origin stylesheets). Posture: preview host only,
   author's own machine, digest-pinned to what the manifest declares, size-capped,
   `text/css` only, never imported into the gateway. Falsifier: any demonstration of
   the override escaping the preview host's page (it structurally has no other
   consumer — `web.py`'s asset route is the single serve point).
6. **The `bw-host.js` CSRF-stamping listener conflicts with the host's own CSRF
   flow** (it stamps `x-csrf-token` on every htmx request when a
   `bw-csrf-token` meta exists; the host uses `X-CSRF-Token` via explicit
   `hx-headers`). Harmless by construction (no meta ⇒ no header; the host's
   `hx-headers` keep working), but if the host later adopts the meta, the two must be
   reconciled. Falsifier: an existing host CSRF test failing after the base.html
   change — run the host's guard suite before ship.

## 13. Gates for this commit

Docs-only FAST lane per #247: bare `uv run ruff check .`, fresh-cache bare
`uv run mypy` (`rm -rf .mypy_cache`), no focused pytest (no code modules touched — the
honest minimal set is none; the design record is the diff). TRUE exit codes only, read
from unpiped runs. The standards tripwire
(`git diff origin/main...HEAD -- standards/` empty) asserted before commit.
