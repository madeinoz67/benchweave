# Issue #299 — PRD 12 slice G1c: computed proofs port + the host-side lane decimator (design of record)

**Date:** 2026-10-01 · **Issue:** #299 (parent: the PRD 12 epic) · **PRD:** `docs/implementation-planning/12-gateway-web-ui-prd.md` §5 UR-08, §6 R-2 · **Exit-gate clause this slice owns:** "series-colour, lane and LTTB proofs green with unchanged thresholds".
**Triage:** public record — mechanisms, thresholds and citations taken from this repository's own committed records; no person, client, bench or device identifiers.

## 0. Premise check — verified against the code, with one honest negative

R-2's premise ("the proofs are about token values, not React, so they port without semantic change") is TRUE as stated: `ui/src/series-colors.test.ts` touches exactly two renderer files — `ui/src/styles/themes.css` (token parsing, lines 219-260) and `ui/src/components/readings/reading-tile.css` (the two CSS-structure its at 565-590). Everything else is pure arithmetic over hex strings. The lane tests import the reducer (`ui/src/components/plots/lane-reduction.ts`) and recompute the survival property independently of it (`checkSurvival`, lane-reduction.test.ts:60-153).

**The honest negative (correcting the dispatch brief's premise):** there is NO Python colourimetry or CVD prior art in this repository, its git history, or the SDK repo. Searched: `src/`, `tests/`, `plugins/` (only `tests/architecture/test_plugin_ui_contracts.py:104-118`, which refuses literal colours BY SCHEMA SHAPE — a contract test, not colourimetry); `git log --all -S` over `*.py` for `ciede`/`Machado`/`deuteranopia` — zero hits; the SDK source tree — zero. The project's only CVD instrument is `ui/src/series-colors.test.ts` itself: hand-rolled, zero dependencies, introduced in `02cb878`, its instrument corrected in four places by the #258 review fold (`3adf3b7`). The #242 §7 feasibility script (`/tmp/bw-series-feasibility.py`) was deliberately never committed ("the build's tests are the durable artefact"). Consequence for this slice: the port is a FIRST Python implementation of the instrument, so the instrument pins (§2 group iii) are not decoration — they are the only proof the ported maths is the same maths, and they port verbatim.

§E.4.4 is NOT underspecified: its three normative rows state the property (every transition survives; glitch on >1; sample-dropping non-conforming), `reduceLane` is the in-tree reference implementation, and the lane tests are the conformance oracle. Buildable as specified in §1.2.

## 1. The mechanism

### 1.1 HOME — inside `packages/ui-html`, additive-only, PR-stacked on G1a

Recommendation: **the proofs and the decimator land inside `packages/ui-html` from G1c's first commit; G1c never creates the package skeleton if G1a is live.** "Proceed without waiting" is satisfied by the PR-stack mechanism (#69, the proven in-tree pattern for parallel slices with ordered landing): development proceeds now against the file contract below; G1c's PR opens with `base` = G1a's scaffold branch (or main once G1a merges); merge is bottom-up. G1c's diff is then purely additive — no `pyproject.toml` touch, no lockfile motion.

The rejected alternative (a standalone module that moves in later) loses three ways: the decimator is RUNTIME code both hosts import (UR-08 — "host-side in Python"; the shared package is the only import surface both the gateway and the PRD 11 standalone host see), so a later move is a public-API migration with a second full review; the G1 exit gate runs these proofs at cutover — running them against a home known to be temporary proves nothing about the end state; and a temporary home in `src/benchweave/` would give the standalone host a dependency on the gateway wheel, against UR-11's architecture.

G1c's whole expected diff (module names follow G1a's scaffold if it differs — a rename, no logic):

| File | Content |
|---|---|
| `packages/ui-html/src/benchweave_ui_html/decimate.py` | the §E.4.4 reducer (runtime, pure stdlib) |
| `packages/ui-html/tests/colour_instrument.py` | the ported instrument (§1.3) |
| `packages/ui-html/tests/thresholds.py` | the §2 ledger as named constants, each citing its ledger row |
| `packages/ui-html/tests/test_series_colour_proofs.py` | S3-A1, S3-A2, S3-D2, S3-A3, S1-A3 + the instrument pins |
| `packages/ui-html/tests/test_lane_reduction.py` | the four property arms, the LTTB control, the PRNG vectors |
| `packages/ui-html/tests/test_threshold_verbatim.py` | the three-arm verbatim check (§1.5) |
| `.claude/deep-review/2026-10-01-issue299-g1c-proofs-design.md` | this record |

**Coordination points (three, all named):**
1. **Skeleton ownership.** `packages/ui-html/pyproject.toml`, the src layout and the uv-workspace wiring are G1a's (Q5 ruling: plain directory + workspace member). G1c contributes files only. If G1a has not opened when G1c is ready, G1c holds at PR-open with the build complete; only if G1a is cancelled does G1c create the minimal skeleton itself — that fallback shape is Tier 3 by the rubric's dependency rule (see §6) and is disclosed, not planned.
2. **Test collection.** Root pytest `testpaths = ["tests"]` does not collect `packages/ui-html/tests/`. G1a's harness needs the same wiring; G1c rides it (testpaths extension or the scaffold's own test lane — G1a's choice, G1c's tests are plain pytest either way).
3. **Token source.** The proofs read `ui/src/styles/themes.css` (the file the TS test reads — same bytes) via one module-level path constant, failing loud if absent. G1e's deletion change re-points it to the package's vendored `themes.css` (UR-10's asset home) — a named G1e checklist row (§3), never a silent fallback.

**UR-11 ruling (the brief's explicit question).** The proofs need NO colour library and NO CVD package; there are ZERO new dependencies, runtime or test-time. The instrument is hand-rolled in the TS file and ports as hand-rolled stdlib `math` — which is correctness, not frugality: the thresholds were pre-committed and the palette was selected against THIS instrument, and the #258 fold proved that ΔE00 implementations diverge precisely on the mean-hue wraparound and the half-plane selector; substituting a library would swap the instrument out from under the thresholds and make the Sharma-table pin meaningless. Letter of UR-11 (runtime deps Jinja2+MarkupSafe only): untouched — the decimator is pure stdlib and test-time imports never enter the wheel. Spirit (lean, host-free, reproducible on any host): upheld — stdlib alone, no new supply-chain surface.

### 1.2 The decimator (UR-08) — precise spec

The column shape mirrors `LaneColumn` (lane-reduction.ts:17-33) exactly — `first` (inclusive), `last` (exclusive; the columns partition `[0, len(states))`), `state` (= `states[first]`, drawn across the column when it carries no interior transition), `transitions` (count of interior transitions), `glitch` (True iff `transitions > 1` — §E.4.4's multi-edge flag), `edge` (the from/to pair, set iff `transitions == 1`). No per-transition index list: the TS shape carries none, and §E.4's contract rows need none (segments carry `data-bw-state`; multi-edge columns carry `data-bw-glitch`). If G1b's partial later needs the interior edge's sample index to draw it, the derivation is on hand (`states[first:last]` is the ground truth; the single interior transition index is computed in the loop) — extending the shape is a named deferral owned by G1b, not invented here.

```python
LaneState = Literal["0", "1", "x", "z"]          # the four-state logic alphabet, verbatim on the OTDP wire

def reduce_lane(states: Sequence[LaneState], columns: int) -> list[LaneColumn]:
    if not states:            return []
    if columns < 1:           raise ValueError("lane_columns_invalid: at least one column required")
    target = min(columns, len(states))
    out = []
    for b in range(target):
        first = (b * len(states)) // target       # the uniform floor grid
        last  = ((b + 1) * len(states)) // target
        if b == target - 1:  last = len(states)   # tail span covers the remainder
        if last <= first:    continue             # empty span: unreachable when target <= N
                                                  # (consecutive floors differ by >= 1); ports verbatim
                                                  # as defensive dead code — a guard states what it does not catch
        transitions = 0; single = -1
        for t in range(first, last - 1):          # interior pairs only
            if states[t] != states[t + 1]:
                transitions += 1; single = t
        col = LaneColumn(first, last, states[first], transitions, transitions > 1, None)
        if transitions == 1:
            col = replace(col, edge=LaneEdge(states[single], states[single + 1]))
        out.append(col)
    return out
```

Semantics carried verbatim from lane-reduction.ts:41-79: a transition AT a column boundary (the pair straddling two adjacent spans) is interior to neither column and survives AS the drawn step between them — the ported checker counts it via `t + 1 == column.last` (lane-reduction.test.ts:107-108). A single interior transition renders as the pre/post edge; more than one renders the glitch mark and NO fabricated edges. Integer floor division is exact for the non-negative operands.

**Relationship to what the TS lane tests pin.** The tests pin the PROPERTY, not the grid: survival (recomputed independently by `checkSurvival`), partition (contiguous, non-empty, covering), glitch exactness (fold F3a: glitch iff interior transitions > 1), edge direction (fold F3b: from/to are the actual neighbouring states), the adversarial all-glitch fixture, the permutation null, and the LTTB RED control (a sample-dropping reducer MUST violate survival on the same fixture — the proof the checker has teeth). §E.4.4's contract-level freedom (any reducer passing the property conforms) remains: G1c ports the reference grid for continuity with the fixtures; the property tests, not the grid, are the conformance oracle. Cross-language output parity is deliberately NOT built (it would put Node inside the Python test lane, against US10's no-Node-toolchain rule); the shared PRNG streams, shared fixtures and identical property oracle are the parity proof, with the printed margins cross-checked once at port time (§7 pass condition B).

### 1.3 The colour instrument port

Constants carried VERBATIM from series-colors.test.ts:14-216 with the four #258-fold corrections already in the TS source: the M_RGB_XYZ matrix and WHITE_D65 [0.95047, 1.0, 1.08883]; the sRGB transfer breakpoints (0.04045/12.92, 0.0031308/1.055/2.4) with the [0,1] clamp on the inverse; fLab's (6/29)^3 breakpoint; CIEDE2000 in the Sharma et al. 2005 form with eq. (14)'s mean hue (halve, THEN add ±360 — porting the pre-fold post-halving form is exactly the bug the 33-row reference table catches); the MACHADO severity-1.0 matrices, the VIENOT prot/deut replacements, M_LMS, M_XYZ_RGB and its Cramer-rule inverse, CMF_575 [0.8425, 0.9152, 0.0] (the corrected y-bar), CMF_475; the Brettel half-plane selector on the L/M-side excess `q·(w × e_S)` (NOT the raw S coordinate); WCAG luminance weights 0.2126/0.7152/0.0722 with the (hi+0.05)/(lo+0.05) ratio. Arithmetic notes: Python 3.13's `math.cbrt` matches `Math.cbrt`; the TS hue normalisation `x % 360 + (x % 360 < 0 ? 360 : 0)` (JS remainder keeps the dividend's sign) is provably equal to Python's `x % 360` (always non-negative for positive modulus) — port as the direct modulo with the equivalence stated in a comment. The dual-arm disagreement rule ports as the record's underpowered direction: both arms are asserted per pair (a one-arm failure is a RED, which IS the escalation — the suite never passes a disagreement).

Token parsing ports `themeTokens` (series-colors.test.ts:219-233): block scan `([^{}]*)\{([^{}]*)\}`, declarations `(--[\w-]+)\s*:\s*([^;]+);`, selector contains `data-theme="light"` / `data-theme="dark"`; the `^#[0-9a-f]{6}$` value validation and every fail-loud message port unchanged (`--bw-series-N missing or malformed in themes.css` etc.). The §A-table equality cross-check (the record's S3-A1 underpowered control) rides G1a's UR-04 harness; if that has not landed when G1c runs, the proofs carry a minimal parsed-CSS == §A-table equality check for the ~20 tokens they consume (retired as redundant when UR-04 lands).

### 1.4 The PRNG port — validated at design time, golden vectors embedded

The fixtures' identity rests on `mulberry32`. JS `Math.imul` (32-bit multiply) and `>>> 0` (ToUint32) semantics port as: every intermediate masked `& 0xFFFFFFFF`; `imul(a, b) = (a * b) & 0xFFFFFFFF`; and the one subtle step — JS `t = (t + Math.imul(...)) ^ t` adds in float64 then truncates at the XOR — becomes `(t + imul(...)) & 0xFFFFFFFF` BEFORE the XOR. **Validated 2026-10-01 by running the TS body under node against the Python port: the three seeds' first 8 outputs are bit-identical (24 values, embedded in §2 group iv).** The ported test pins these 24 values as literals; a one-bit mask perturbation reds the pin (RED witness class). If the vectors could not have been captured (no JS runtime at port time), the "fixtures unchanged" claim is DROPPED and disclosed — never silently kept (§7 underpowered column C).

### 1.5 The threshold-verbatim check — three arms, fail-closed everywhere

The UR-02 mechanism (fail-closed parsing of committed prose/tables) applied to the frozen records:
- **Arm (a), durable:** parse the #242 record's §6 threshold sentence and S3-A1/A2/A3 rows for T1 3.0 / T2 10.0 / T3 8.0 and the four-condition set; assert equality with `thresholds.py`. The record is frozen history — parse-shape drift risk is nil, and a parse miss REDS (fail-closed), never skips.
- **Arm (b), durable:** parse the #243 record's S1-A3 row for the limiting values (3.0 both surfaces, 10.0); assert the VALUES only — its "48 values" count is stale against the code's 7-comparator loop (§2 flag) and asserting it would be asserting a known defect. Separately assert the comparator SET equals {advisory, warning, critical, trip, success, text-muted, border} exactly — the pinned-set guard against silently dropping the fold-added border comparator.
- **Arm (c), port-time:** while `ui/` lives, extract the TS file's `toBeGreaterThanOrEqual(...)` threshold literals (3.0, 10.0, 8.0, 11.0, 9.0) and assert set-equality with the carried constants — the machine proof that "unchanged" means unchanged. Retires in G1e's deletion change, its evidence already transcribed into §2 with line citations.

## 2. The threshold ledger — every threshold, verbatim, with provenance flags

Group i — record-backed hard thresholds (#242 §6, lines 418-431; TS assertions agree):

| id | value | enumeration (pairs / arm-assertions) | record citation | TS citation |
|---|---|---|---|---|
| T1 | contrast >= 3.0:1 (WCAG 2.2 non-text) vs `--bw-surface-recessed` | 16 ratios (8 tokens x 2 themes; single-arm) | #242 §6 S3-A1 + threshold sentence | series-colors.test.ts:440 |
| T2 | dE00 >= 10.0 per pair per condition | 320 pairs / 640 arm-values (8 x 5 hues x 4 x 2) | #242 §6 S3-A2 + sentence | :453-454 |
| T3 | dE00 >= 8.0, ADJACENT slots | 56 pairs / 112 arm-values (7 x 4 x 2) | #242 §6 S3-A3 + sentence | :600-601 |
| CVD | Machado 2009 sev-1.0 primary; Vienot 1999 prot/deut + Brettel 1997 trit secondary; both arms asserted every pair; disagreement = inconclusive, escalate, never pass | — | #242 §6 threshold sentence | :63-71, 380-430 |
| DIST | CIEDE2000 on CIELAB (D65) | — | #242 §6 sentence | :56-152 |
| COND | {normal, deuteranopia, protanopia, tritanopia} | — | #242 §6 sentence | :216 |

Group ii — TS-embedded, ABSENT from #242 §6 (each FLAGGED, never silently reconciled):

| id | value | enumeration | provenance | flag |
|---|---|---|---|---|
| T2-ENG | >= 11.0 (= threshold + 1.0) engineering floor, per-theme dual-arm min | 2 (one per theme) | TS :477; #243 record line 481 ("search screens T1 >= 3.3, T2 >= 11.0 are STANDING pre-commit doctrine"); #242 §7 prose | absent from #242 §6's threshold sentence — carried, flagged |
| CENSUS-HARD | ALL 28 same-dash pairs dE00 >= 8.0 (the "waveform monochrome arm") | 224 pairs / 448 arm-values (C(8,2) x 4 x 2) | TS :482-507, label "S3-D2" | NO row of that id exists in #242 §6 (which enumerates S3-A1..A7); provenance is the slice-3 review fold (PR #263 owner row) — carried, flagged; this ledger row becomes its durable citation home at cutover |
| CENSUS-ENG-DARK | dark census min >= 9.0 | 1 | TS :506 | TS-only — carried, flagged |
| CENSUS-LIGHT | light census hard floor 8.0 ONLY; measured min 8.19 is BELOW the +1.0 floor | 1 | TS comment :486-489; PR #263 owner row (accept-recommended) | the dark/light asymmetry is DELIBERATE — porting a symmetric >= 9.0 would red at 8.19 and invite forbidden threshold relaxation |
| LIM-T1 | contrast >= 3.0:1 vs BOTH `--bw-surface` AND `--bw-surface-recessed` | 4 ratios (1 token x 2 surfaces x 2 themes) | #243 §6 S1-A3 row | record-backed; TS :544-545 agrees |
| LIM-T2 | dE00 >= 10.0 vs the comparator set | CODE: 7 comparators = 56 pairs / 112 arm-values (7 x 4 x 2) | #243 §6 S1-A3 row + TS :551-552 | THREE counts disagree: record "6 severity keys / 48 values"; TS it()-name "24 pairs x both arms"; TS CODE loops severityAll = 5 hues + `--bw-text-muted` + `--bw-border` = 7 comparators (:525-539). The border comparator was fold-added ("measured safe, pinned anyway") without updating either count. The port carries the CODE's 7-comparator superset and asserts the set exactly (arm (b)); the stale counts are documented here, and the frozen record is never retrofitted |
| LIM-T2-ENG | >= 11.0 | 2 | TS :559 | TS-only, consistent with #243:481 doctrine — carried, flagged |
| (search screens) | T1 >= 3.3, T2 >= 11.0 | asserted NOWHERE | #243:481 | search-time doctrine for future slots — do NOT port 3.3 as an assertion; the TS does not |

Group iii — instrument pins (TS-only; the port's only proof its maths is the same maths):

| id | pin | citation |
|---|---|---|
| I1 | Sharma et al. 2005 reference table, 33 rows, abs(dE00 - expected) < 1e-4 (the published 34th row omitted with the reason stated in-file) | TS :287-330 |
| I2 | each Brettel anchor assigned to its own half plane; fixed points at 9 decimals; white fixed under both planes | :332-360 |
| I3 | 575nm y-bar strictly inside (0.8700, 0.9520) and close to 0.915 at 1 decimal (CIE 1931 2-deg 5nm-table bracket) | :363-368 |
| I4 | last-digit sensitivity: a 5% perturbation of the 575nm y-bar moves a measured distance > 0.1 dE00 | :384-386 |
| I5 | every Machado row sums to 1 within 1e-5 (6-decimal published rounding) | :391-396 |
| I6 | Vienot third row is exactly [0,0,1]; rows sum to 1 within 1e-5 | :398-407 |
| I7 | the two arms measure DIFFERENT distances on the reference pair (#917f5f vs #a92858, deuteranopia): abs(primary - secondary) > 5 (measured ~12.4 vs ~3.4) | :409-413 |
| I8 | white round-trips to white under every matrix and Brettel within 1e-5 | :415-428 |

Group iv — lane/LTTB constants (UR-08: "fixtures and thresholds unchanged"; lane-reduction.test.ts / lane-reduction.lttb.control.test.ts):

| id | constant | citation |
|---|---|---|
| L1 | property arm: 240 runs (>= 200 checked), lengths 2..5001, widths 1..64, four-state alphabet, seed 0x2445220; per run: missing == [], unmarkedMultiEdge == [], overmarkedSingleEdge == [], reversedEdges == [], survived == total | :118-146 |
| L2 | partition arm: 60 runs, lengths 2..501, widths 1..64, seed 0x2445221; first==0, last==N, contiguous, non-empty | :150-163 |
| L3 | adversarial: 257-sample alternating 0101 fixture, 16 columns, ALL columns glitch, survival complete | :166-176 |
| L4 | permutation null: 50 Fisher-Yates copies (seed 0x2445222) of the 257-sample base at 16 columns; every transition of EACH ordering survives | :179-200 |
| L5 | LTTB control: 200-sample fixture `i%40<20 ? (i%2==0?"0":"1") : "0"`, 12 columns; the LTTB-shaped reducer loses > 0 transitions; reduceLane loses none | lttb.control:52-61 |
| L6 | mulberry32 golden vectors (first 8 outputs x 3 seeds, captured at design time from the TS body — node vs the Python port compared identical): seed 0x2445220: 0.9652225237805396, 0.4304069571662694, 0.725462764268741, 0.36950787785463035, 0.15731652243994176, 0.9143903909716755, 0.0463623246178031, 0.9720222509931773 · seed 0x2445221: 0.4868193008005619, 0.4788632411509752, 0.7096924297511578, 0.15034811082296073, 0.36186491628177464, 0.04382433579303324, 0.6783437498379499, 0.6790179717354476 · seed 0x2445222: 0.7662574690766633, 0.8407656361814588, 0.7420316401403397, 0.012470268877223134, 0.559661966515705, 0.7370667946524918, 0.6548893116414547, 0.491069600218907 | design-time capture, this record |

Denominator convention (claim discipline): "values" in the #242 record counts pair-cells; every dE00 cell here is asserted under BOTH arms, so assertion counts are double the pair counts. The colour census totals 1,312 dE00 arm-values over 656 pair-cells plus 20 contrast ratios = 1,332 assertions, plus the group-iii pins and the lane arms.

## 3. Minimal first slice — scope and deferrals

IN: `decimate.py`; the four lane property arms + partition + adversarial + permutation + the LTTB control + the PRNG vectors; the instrument with all group-iii pins; S3-A1, S3-A2 with its engineering floor, the S3-D2 census with its ASYMMETRIC floors, S3-A3; the S1-A3 limiting block (T1 both surfaces, the 7-comparator T2, its floor); the three-arm verbatim check; margins reported via `record_property` (the repo's established measurement channel) and printed in the TS format for cross-implementation comparison. The S1-A3 block is IN because it lives in the named file, uses the same instrument, and would otherwise be deleted unpinned at G1e — the thinner reading of R-2's parenthetical is a maintainer fork (§9), not this design's call.

DEFERRED, each with its owner and landing place:
1. The S1 fold-rows 5+11 CSS structure pins (reading-tile.css block order, no-glow, label token) — G1a/G1b's asset-pinning lane; they pin CSS source order, not token values, and in the HTMX world that CSS is a vendored asset. MUST land before G1e or be consciously dropped (§9 fork 1). Named so the deletion does not lose them silently.
2. S3-A4 (assignment pin, 16-ceiling, hide/reorder invariance) and S3-A5 (severity-hue discipline on the DAQ fixture) — they live in OTHER TS files (the series/assignment and contract tests), outside R-2's named families; they port with their own slices (G1b/G1d). §2 records vice-versa: these record rows have no home in the ported file.
3. G1e checklist rows owed by this design: re-point the token path constant to the vendored asset; retire verbatim arm (c); obligation 12's rewrite (R-6) names the Python proof home.
4. Harness/pattern-library integration, axe, screenshots — G1a/G1d, untouched here.
5. Cross-language output-parity harness — rejected by design (§1.2), not merely deferred.

## 4. In-tree precedent

- The TS instrument itself is the port source and the precedent for the proof shape: hand-rolled maths, published-reference pins, dual independent models with disagreement-as-inconclusive (series-colors.test.ts; history `02cb878`, fold `3adf3b7`).
- Fail-closed parsing of committed prose/tables by tests: the UR-02 harness direction (G1a) and today's `ui/src/contract-coverage.test.ts` (L1) on the TS side; `tests/architecture/test_website_stamps.py` is the Python precedent for tests reading committed docs as machine sources.
- Property test + RED control + permutation null: the lane tests themselves — the port preserves this shape exactly rather than inventing a Python idiom.
- Measurement recording via pytest `record_property`: the fault-leg suite's established channel (root pyproject comment).
- PR stacks (#69) for the G1a coordination; the stacked-PR and merge-bottom-up doctrine in both slices' issue bodies.
- The honest negative stands: there is no Python colourimetry precedent (§0) — this port establishes it, and the instrument pins are its verification.

## 5. Invariant, drift and CI impacts

Invariants: NONE of CTL/STO/CON/REG is touched. The decimator is a pure function from an in-memory state list to display columns — no store, no control path, no contract decoding, no registry, no persisted format; the proofs are test-time assertions over CSS token strings and that pure function. §E.4.4 is a presentation contract row (ui-contract.md:496-504) — its rows do NOT move in this slice (no ui-contract.md edit). The four-state alphabet travels as string literals; no OTDP schema byte changes. One deliberate note so nobody misreads the floors: the colour thresholds are pre-committed DISPLAY-legibility thresholds from the design records; they are not bench-safety envelopes, and nothing here is a commissioned-per-bench parameter (A02 is not engaged).

Drift obligations: obligation 12 is rewritten at G1e (R-6), not here — the TS proofs still exist and still run. The one real drift exposure G1c creates is the two-home window (TS and Python proofs both green until G1e); verbatim arm (c) pins the two homes' thresholds equal for the window's life, and G1e closes the window.

CI cost: +5 pytest modules riding whatever collection G1a wires — no new jobs, no dependency motion, no lockfile churn on the recommended shape. Runtime measured by construction: ~1,300 dE00 evaluations (microseconds each) plus 240 property runs over <= 5000-sample arrays — order 1-2 s in pure Python, xdist-safe (pure functions, read-only file access).

## 6. Review tier and the Step-1 keyword scan (#254)

**Tier: 2** on the recommended shape (the diff of §1.1: new source + test files under `packages/ui-html/`, plus this record). Path rules: no Tier-3 path is touched — no `standards/` bytes, no JSON Schema, no `src/benchweave/contracts/`, no state or registry surface, no fixture lattice, no `packages/sdk` pointer; the diff is production-and-test code matching no Tier-3 rule, so the default Tier-2 clause carries it (test-only changes sit at Tier 2 by the rubric's own text). No dependency is added, removed or re-pinned, so the dependency rule does not fire.

**Disclosed conditional:** if the fallback shape is taken (G1a cancelled; G1c creates the package manifest declaring Jinja2+MarkupSafe), the dependency rule makes THAT shape Tier 3 — the second adversarial reviewer is then owed. The design's recommendation avoids it.

**Step-1 keyword scan, run at design time over the assembled expected diff text** (this record's full text plus the planned module/test files as specified in §1 — the same corpus shape the #244 record scanned):

`threading: 0 · asyncio: 0 · subprocess: 0 · sha256: 0 · hashlib: 0 · migrate: 0 · recovery: 0 · protection: 0`

No keyword appears in any planned code, comment or record prose. The scan-report line above necessarily names the eight keys once each (the reporting artefact itself); following the #244 precedent it is excluded from the counts — a reviewer whose derivation includes it finds eight mechanical self-mentions and the keyword rule firing on reporting artefacts, disclosed here rather than discovered. Substance note, stated rather than hidden: the T2 non-confusion proof is safety-ADJACENT (a series trace mistakable for the trip hue is the operator-confusion hazard #242 §7 calls the safety property); the mechanical tier is 2, and severity can go up, not down — the reviewer may take the deeper lane on that substance, and this record invites it.

## 7. Measurable proof and the PRE-COMMITTED acceptance rule

Written before any ported number is looked at. Kill directions are binary per row; "underpowered" means the measurement cannot decide — never a pass. Thresholds are never tuned to make a row green: a red row means the port is wrong or the tokens moved, and either way it ships nothing.

| # | Metric | Effect size (N) | Pass (ship) | Kill | Underpowered |
|---|---|---|---|---|---|
| A | Threshold fidelity | the §2 ledger — 22 rows across groups i-iii — parsed and compared, both directions; plus arm (c)'s TS-literal set | 22/22 rows: every carried constant equals its ledger value; arms (a), (b), (c) all green | any mismatch (fix the COPY, never the threshold) | a record-parse miss REDS fail-closed (fix the parser first); it never skips |
| B | Colour census | 1,332 assertions (1,312 dE00 arm-values over 656 pair-cells + 20 contrast ratios) on the shipped tokens, both themes | every value >= its threshold at UNCHANGED constants; every printed margin ([series-margins]/[limiting-margins]) equals the TS suite's printed margin at the same commit, at the printed 2 decimals | any value below threshold; any margin line disagreeing with the TS run | a dual-arm disagreement on any pair = INCONCLUSIVE for that pair: escalate the slot or the threshold, never pass; if the TS suite cannot run at port time, the margin-parity clause drops to the §2 ledger's transcribed values — disclosed, not silent |
| C | Lane property | 240 + 60 + 1 + 50 seeded runs, 4 sub-assertions each where applicable; the LTTB control's 2 assertions; 24 PRNG golden values | all arms green; the LTTB-shaped reducer loses > 0 transitions on the fixture where reduce_lane loses 0; all 24 golden values exact | any property list non-empty; the control PASSING the survival property (a toothless checker); any golden value off | if the golden vectors lack capture provenance, the "fixtures unchanged" claim is DROPPED and disclosed (the property arms still run on the port's own stream) — never silently kept |
| D | RED witnesses | 5 | all five witnessed red in the PR message with pre-fix output | any witness that stays green | n/a |

The five RED witnesses: (1) stub `reduce_lane` as the LTTB-shaped sample-dropper — the property arm reds (transitions missing); (2) perturb a ledger constant DOWN (8.0 -> 0.8) — the value census stays green and the verbatim arms red, proving the verbatim check is the load-bearing guard against relaxed thresholds; (3) perturb a constant UP (10.0 -> 30.0) — the census reds on shipped tokens; (4) perturb a token value in themes.css — T1/T2 red (the S3-A6 witness, ported); (5) transcribe CIEDE2000's mean hue the pre-fold way (add ±360 AFTER halving) — the Sharma reference rows red on the wraparound pairs (the #258 witness, re-run).

A reviewer runs: `UV_PROJECT_ENVIRONMENT=venv uv run pytest packages/ui-html/tests -q` (exit 0; counts from junitxml, never a filtered summary line); `npm --prefix ui test -- series-colors lane-reduction` at the same commit (exit 0 — the parity precondition and the two-home drift guard); the five witnesses as PR-message evidence.

## 8. Top risks and their falsifiers

1. **Threshold transcription error** — a relaxed threshold (8.0 copied as 0.8) passes the value census silently. Falsifier: verbatim arms (a)/(c) red on any mismatch; witness (2) proves the arm live. What would falsify the design: frozen-record prose drifting out of parse shape (nil risk — records are frozen history); then arm (a) degrades to review-only and the disclosure duty moves to §2, which already carries every value.
2. **CIEDE2000 mean-hue re-break** — a hand port can reintroduce the pre-fold form; verdicts shift exactly on wraparound pairs. Falsifier: the 33-row Sharma pin at 1e-4 (rows 11/12/15/16/17/19 are the wraparound rows); witness (5).
3. **PRNG semantic drift** — a masking slip changes the fixture streams while every test stays green (the property is stream-agnostic). Falsifier: the 24 golden values; a one-bit mask perturbation reds them.
4. **The S1-A3 comparator-count trap** — porting the record's "6 keys / 48 values" (or the it()-name's "24 pairs") silently drops the fold-added `--bw-border` comparator. Falsifier: arm (b)'s exact-set assertion {5 hues, text-muted, border}; the §2 LIM-T2 row carrying all three counts.
5. **The census light-fork asymmetry** — a tidy-up that asserts dark's >= 9.0 floor on light reds at the measured 8.19 and invites relaxing a threshold, which is forbidden. Falsifier: the port asserts the hard 8.0 on light and the >= 9.0 floor on dark ONLY, with the owner-fork comment carried; §2's census rows pin the asymmetry, and the PR #263 owner row is its provenance.
6. **G1a collision** (named here though outside the mechanism): both slices creating `packages/ui-html/pyproject.toml`. Falsifier: the second PR's diff touching the first's files. Mitigation: §1.1's additive-only rule and the PR stack.

## 9. Forks for the maintainer

1. The reading-tile.css structure pins (deferral 1): G1a/G1b's lane, or a conscious drop recorded in R-6's obligation-12 rewrite. G1c does not carry them.
2. Slice thickness: S1-A3 is IN on this design's reasoning (same file, same instrument, deleted unpinned at G1e otherwise). The thinner R-2-literal slice (S3 families only) is defensible; if taken, the limiting block needs its own pre-G1e landing or an explicit drop.
3. The #243 record's stale "48 values" count and the #242 §6-absent thresholds (§2 group ii): records are frozen history; this ledger is the documentation. Ratification, if wanted, is a fold note in a FUTURE record — never an edit.
4. S3-D2's provenance (review fold, PR #263) has no §6 row anywhere; after G1e this record's §2 is its citation home. If the maintainer prefers a standing record for the census + engineering floors, that is a small docs increment, not a G1c blocker.

— end of record —

> Post-assembly note (controller, 2026-10-01): the maintainer rulings resolve §9 — fork 1 → G1b owns the reading-tile pins; fork 2 → S1-A3 stays IN; forks 3–4 → documented-as-found stands. G1a's layout is confirmed (`packages/ui-html`, distribution `benchweave-ui-html`, `contract_harness/`, import root `benchweave_ui_html`), making §1.1's "a rename, no logic" clause moot. The rulings live on the tracker (#299); §9's text is the pre-commitment artefact and is not edited.
