# Issue #102 D1+D3 — the validation-report family + derived in-prose numbers (design)

**Date:** 2026-09-21 · **Issue:** [#102](https://github.com/madeinoz67/benchweave/issues/102) (D1 + D3; D2 closed by PR #120)
**Status:** design, pre-build · **Verdict:** BUILD for registry / execution / interface / closure (writer + pin); **DON'T-BUILD** for
plugin-ui machine-writing (§7, evidenced). D3 lands inside the same family (digits, derived).
**Baseline:** worktree `feat/issue102-d1-report-family` at `5345f01` (= `origin/main`). Template: the #79 design
(`.claude/deep-review/2026-09-20-issue79-machine-written-validation-report-design.md`) and its D2 extension
(`2026-09-20-issue102-d2-manifest-version-discovery-design.md`).

## 1. Root cause (established, not assumed — all measured this session at `5345f01`)

The #79 defect statement generalizes, and is **not hypothetical right now**: two of the four remaining
reports are demonstrably stale with every gate green.

1. **Live staleness, measured** (sorted live check-set vs committed `- PASS:` lines):

   | Suite | Live checks | Committed report | Delta |
   |---|---|---|---|
   | registry | 64/64 | 64 | set-equal (verified: 0 live-only, 0 committed-only) |
   | execution | 150/150 | 150 | set-equal |
   | interface | 256/256 | **254** | +2: both `Stored fixture agrees:` checks |
   | closure | 17/17 | **16** | +1: `Stored fixture agrees:` (composition-fixtures) |

   The stored-fixture agreement checks were added to the suites after those reports were last hand-updated;
   nothing compared the artifacts, exactly the hole #79 closed for otdp. The `docs/README.md:20` interface
   row also says 254. This is tier-2 prose drifting gate-free (precedent class `a245090`) in the wild.
2. **Portability blocker, measured**: the check names that make interface/closure stale embed **absolute
   paths** — `check_interface.py` builds `"Stored fixture agrees: " + str(CONTRACT_DIR / "examples/operation-vectors.json")`
   (two names), `check_closure.py` one more. A byte-pin over names containing `/Users/...` or a CI checkout
   path cannot be byte-stable across platforms; normalization is a precondition for the family, not a nicety.
   `check_planning.py` carries the same pattern (out of family scope — §5).
3. **D3, measured**: word-form numbers in report prose are template constants decoupled from the measured
   values: otdp coverage "Twelve class profiles and fifty … action contracts"; registry "Checked three Draft
   2020-12 schemas"; execution "Checked six …"; interface "twenty synthetic operation vectors"; closure
   "Sixteen composition and twenty-six integrated scenarios". Every one of those quantities is computed by
   the suite that renders the paragraph (e.g. `len(profile_map)`, `len(covered)`, the R\d\d/E\d\d regex
   counts in `check_closure.py`). #79's risk table named this residual; CON-11's rationale still discloses it.
4. **plugin-ui**: no checks-list substrate exists and the report is a different kind of artifact — §7.

A06 framing unchanged from #79: a hand-maintained count beside the corpus it claims to verify is an
assertion; two of four are already wrong.

## 2. The mechanism — one shared writer/pin, five suites

### 2.1 Shared module `scripts/architecture/_validation_report.py` (new)

Three functions, no state:

- `active_standard_version(standards_root, standard_id) -> str` — the D2 `_active_otdp_version`
  generalized. Refusal prefix is `f"{standard_id}_manifest_absent:"`, which reproduces the existing
  `otdp_manifest_absent:` bytes exactly for devices (no churn in #119/#125 regression surfaces).
- `render(checks, *, marker, title, coverage, limit) -> str` — the #79 template, verbatim: generated marker
  first line, title, `**Result: {passed}/{total} checks passed; {failed} failed.**`, coverage paragraph,
  limit paragraph, `## Checks`, then check lines **sorted lexicographically** (glob-order immunity, #79 §2).
- `main(checks, out_path, *, script, title, coverage, limit)` — the shared `__main__` epilogue: print
  failures, print the count, and only when `--write-report` is in `sys.argv[1:]` write the report —
  **refusing (exit 1) when any check fails**, writing with `newline="\n"`. Same output strings as today's
  devices epilogue.

**Import mechanics (measured, not assumed):** `runpy.run_path` does **not** put the script's directory on
`sys.path` (probe at this baseline: sibling import under `run_path` fails; `__name__` is `<run_path>`).
Each family script therefore bootstraps:

```python
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import _validation_report
```

`__file__` is set in both execution modes (direct `python scripts/architecture/check_X.py` and
`runpy.run_path(..., init_globals={...})`), so the bootstrap works for the author and the harness. The
mutation of `sys.path` is not a docs/standards write; `test_validation_is_read_only` is unaffected. The
module caches in `sys.modules` across suite runs — it is stateless, so that is safe.

### 2.2 Per-script changes (the four + devices)

Each family script gains:

- derived corpus root: `CONTRACT_DIR = (STANDARDS / "<id>" / _validation_report.active_standard_version(STANDARDS, "<id>")).resolve()`
  (replaces the hardcoded `registry/0.1.1`, `execution/0.1.0`, `interface/0.1.0`; resolve-once per the #119
  lesson). Cross-standard reads derive too: `check_execution.py`'s otdp catalog path (currently hardcoded
  `otdp/0.2.0/device-profile-catalog.json`) and `check_closure.py`'s execution/interface contract-MD paths.
- prose constants `REPORT_TITLE`, `REPORT_COVERAGE`, `REPORT_LIMIT` carrying today's bytes verbatim **except
  the D3 numbers** (below);
- a one-line `render_report(checks)` wrapper delegating to `_validation_report.render` with its constants
  (devices keeps its existing namespace shape — its pin test's `render_report in namespace` assertion is
  untouched);
- `__main__` reduced to `_validation_report.main(CHECKS, CONTRACT_DIR / "validation-report.md", ...)` — the
  argv gate stays inside `__main__`, so `runpy.run_path` (run_name `<run_path>`) remains structurally unable
  to reach the writer from CI.

**Check-name normalization (interface + closure only):** the three `Stored fixture agrees:` names move from
`str(CONTRACT_DIR / ...)` absolute paths to root-relative: `Stored fixture agrees:
interface/0.1.0/examples/operation-vectors.json`, `…/mcp-start-exchange.json`, and (closure)
`acceptance/composition-fixtures.json`. Only the name string changes; the compared fixture paths in the
check bodies are unchanged. Consumer check: the only in-tree matcher is the `"Stored fixture agrees"`
substring in `test_contract_regressions_are_detected` (text-searched), which the rename preserves.

**D3 mechanics — digits, derived at module scope.** Each quoted count becomes an f-string over the value
the suite already computed:

| Report | Constant today | Derived from |
|---|---|---|
| otdp coverage | "Twelve class profiles and fifty input/output action contracts" | `len(profile_map)` (12), `len(covered)` (50) |
| registry coverage | "Checked three Draft 2020-12 schemas" | the 3-name schema tuple |
| execution coverage | "Checked six Draft 2020-12 schemas" | the 6-name schema tuple |
| interface coverage | "twenty synthetic operation vectors" | `len(vec)` (20) |
| closure coverage | "Sixteen composition and twenty-six integrated scenarios" | new `composition_scenarios` / `integrated_scenarios` vars (the regex counts the checks already compute; `check_closure.py` stores them in variables, the `== 16`/`== 26` pins unchanged) |

Word form is dropped for digits. An int→word helper would be unbounded vocabulary serving only the
aesthetics of a generated artifact; digits are grep-able, locale-free, and the convergent in-tree form
(interface's own check names already say "20 unique REST operations" while its prose said "twenty").
**Byte-stability expectation, pre-committed:** every derived value equals today's live value (12, 50, 3, 6,
20, 16, 26 — all measured §1), so the regen diff per report is the word→digit edit and nothing more. If a
derived number ever *differs* from the committed prose, that diff is the drift-catch working — but at this
baseline none does, and the acceptance rule (§7) pins that.

**Check names stay static** ("Twelve distinct profiles", "20 unique REST operations", "16 composition
scenarios" …). Names are pinned identities referenced by mutation-fixture expectations; the count inside a
name is already enforced by the check's own comparison, and the silently-lying surface was the prose, not
the names. Residual: a name can go stale-descriptive while its check still pins the right number —
cosmetic, review-guarded, disclosed here rather than churned.

### 2.3 Template unification (deliberate, listed diffs)

All five reports take the #79 shape: generated marker line, `**Result: N/M checks passed; X failed.**`
headline, `## Checks` heading before the sorted list. The four new reports today carry `**N/N checks
passed.**` and no `## Checks` heading — the regen diff for each therefore includes the headline-form and
heading change (pre-committed in §7's table). One template, no per-suite knobs.

### 2.4 The pin (CI-side, read-only) — `tests/contracts/test_architecture.py`

- `report_failures` generalizes over a `REPORT_SPECS` table: suite → (root kind, report relative path,
  regen command). Standards suites derive their path from the manifest via a generalized
  `_active_report_path(standard_id)` (D2 shape); closure is `(DOCS, "acceptance/validation-report.md")`.
  Each entry loads the suite namespace, asserts `render_report`/constants are present (clean failure
  naming the missing writer), renders, byte-compares.
- `test_validation_report_matches_live_run` parametrizes over the five suites, keeping the otdp README
  exactly-once/count assert and adding the same for the registry/execution/interface rows (all three exist
  in `docs/README.md` today; closure has no row and none is added).
- `test_validation_report_tampering_is_detected` parametrizes (suite × {flip_pass, bump_count,
  reorder_lines}) with **one suite execution per suite**: copy trees, render the live bytes once on the
  pristine tmp tree, then for each mode mutate the committed report and assert the comparison reports
  drift (naming the per-suite regen command). Render-before-mutate is the faithful order — it stays
  correct even if a suite ever read its own report.
- **Portability guard (new, RED arm):** for each family suite on the real tree, assert no check name
  contains `str(DOCS)`/`str(STANDARDS)` (an absolute path). Fails today on interface (2 names) and
  closure (1) — the measured §1.2 blocker — and passes only once normalization lands. This anchors the
  sorted-render soundness property inside CON-11's amendment.
- **Writer-refuse pin (new):** call the shared `main` with `--write-report` and a failing checks list
  against a tmp path; expect `SystemExit(1)` and the file absent. One test covers all five suites because
  the refuse path is the shared module's.
- The registry/execution/interface rows of `test_contract_regressions_are_detected` derive their fixture
  paths from the manifest (same D2 F1 fix the devices rows already received — otherwise the family rebuilds
  the sweep-miss class one file over).

## 3. Precedent (extended, not invented)

- `check_devices.py` writer + `test_architecture.py` pin (#79, merged) and its D2 manifest derivation
  (PR #120) — this design transplants both to the sibling suites and factors the shared parts into one
  module instead of five copies.
- `src/benchweave/standards/matrix.py` render/check pair with a generated marker — the original template.
- The `runpy.run_path` + tmp-copy harness (`run_checks`, `test_contract_regressions_are_detected`,
  `test_validation_is_read_only`) — reuse point for pin, tamper and guard.
- The sys.path bootstrap is new to `scripts/architecture/` (no script imports a sibling today); it is the
  smallest mechanism that keeps the renderer in scripts-land next to its checks rather than shipping it in
  the wheel (#79 §3 rejected the package-side home for exactly that reason).

## 4. Minimal first increment (file-by-file)

| File | Change |
|---|---|
| `scripts/architecture/_validation_report.py` | NEW — `active_standard_version`, `render`, `main` (refuse-on-failure writer). |
| `scripts/architecture/check_devices.py` | Use shared module (`_active_otdp_version` deleted, prefix bytes preserved); coverage constants become D3 f-strings; `render_report` becomes the wrapper; `__main__` delegates. No check changes. |
| `scripts/architecture/check_registry.py` | Derived `CONTRACT_DIR`; constants + wrapper + `__main__`; coverage "three"→derived "3". |
| `scripts/architecture/check_execution.py` | Same; plus derived otdp-catalog read; coverage "six"→derived "6". |
| `scripts/architecture/check_interface.py` | Same; coverage "twenty"→derived "20"; the two `Stored fixture agrees` names normalized root-relative. |
| `scripts/architecture/check_closure.py` | Same; execution/interface contract paths derived; scenario-count vars; coverage numbers derived; the `Stored fixture agrees` name normalized. |
| `standards/{registry/0.1.1,execution/0.1.0,interface/0.1.0}/validation-report.md`, `docs/acceptance/validation-report.md` | Regenerated once by each writer (expected diffs pre-committed in §7). |
| `standards/otdp/0.2.0/validation-report.md` | Regenerated — expected diff is exactly the two D3 digit edits. |
| `tests/contracts/test_architecture.py` | §2.4: family pin, tamper, portability guard, writer-refuse pin, README row asserts, generalized report-path + regression-fixture derivations. |
| `docs/README.md` | Interface row count 254→256 (the only stale count; registry/execution rows already match). |
| `docs/internal/invariants.md` | CON-11 **amendment** (appended, per this file's own convention): scope extends to the four standards suites + the closure docs-surface report; in-prose counts are derived (the disclosed residual closes); check names are path-portable (guard-anchored); plugin-ui train records explicitly excluded with the §7 reason. |
| `docs/internal/drift-and-obligations.md` | Row 13 rewritten as the family obligation (per-suite regen; closure triggers on docs/acceptance content changes; README rows move with counts; EVIDENCE re-point clause). |
| `standards/GOVERNANCE.md` | Bump-mechanics clause: regeneration duty generalized to any bumped standard with a machine-written report; derivation sentence generalized from "the script's `OUT`" (otdp) to the family; **fix the dangling "By convention the bump" fragment** left by the D2 edit. |
| `docs/architecture-validation.md` | The "other suites' reports remain historical review evidence" sentence replaced with the family statement; `--write-report` named per-suite. |
| `EVIDENCE-annotations-and-versions.md` | Re-point the 3 execution-report line citations (its rows at lines 109/110 + the narrative at 886 cite `validation-report.md:128/129`, which the regen moves). Content quoted in those rows is unchanged; this is an anchor re-point in a frozen sweep document, diff-visible — no re-sweep. |

**No standards bump** (tier-2 prose edits inside active version dirs; precedent `a245090`; no
corpus-manifest rows move — reports are not digest-pinned by design). **No CI workflow change** (rides
`gates` via pytest). **No SDK/submodule change** — verified: the SDK lock's file lists carry no
`validation-report.md` rows for any standard, so nothing syncs outward.

## 5. Deferrals (rule 3 — design-record table; one follow-on issue maximum)

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| D1-a | plugin-ui report family — machine-writing + pin. **DON'T-BUILD**, §7. | This record §7 (reasoning committed). | A checks-list plugin-ui suite ever lands (then its report joins the family with per-suite prose constants). |
| D1-b | plugin-ui test-path literals (`tests/architecture/test_plugin_ui_contracts.py` `DIRECTORY`, `tests/standards/test_scenarios.py` `NORMATIVE`/`PIN_KEY` hardcode `plugin-ui/0.2.0`) — post-bump they would validate the frozen tree silently (D2's F1 class, different files). | **The one follow-on issue** (if the maintainer wants it tracked; otherwise this row). | Next plugin-ui bump. |
| D1-c | `check_planning.py`'s absolute-path `Stored fixture agrees` name — same normalization, no report consumer exists; guard scope stays family-only. | This row. | Planning gains a report/pin consumer, or its next touch. |
| D3-a | Count-bearing **check names** stay static (scope decision, §2.2). | This record §2.2. | A stale-name incident, or a rename-tolerant window. |
| D3-b | Hand-written doc numbers stay review-guarded: `docs/architecture-validation.md` coverage table ("twelve profiles, fifty action contracts", "Twenty REST operations, seventeen MCP tools", historical "978"), `docs/README.md` execution row's "six linked synthetic examples". Machine derivation is only sound in machine-written files. `docs/README.md`'s baseline-verification sentence ("OTDP 495, registry 64, execution 150, interface 254 and closure 16") is FROZEN HISTORY — the 0.1.0 architecture-review baseline, explicitly "not results from the repository CI" — and is never "corrected" when live counts move (review NIT-2). | This row. | Any doc-number drift incident; then reword to mechanism-names or add row asserts. |

## 6. Invariant, drift and tier impact

- **CON-11 amended** (append, not rewrite): family scope, derived prose numbers, path-portable names,
  plugin-ui exclusion. No other CTL/STO/CON/REG invariant touched. Read-only doctrine preserved (writer
  stays structurally `__main__`-only; `test_validation_is_read_only` continues to cover all suites).
- **Tier**: no on-disk machine format or schema changes; regenerated artifacts are prose (unpinned by
  design, now writer-pinned). Not Tier 3. No standards train — explicitly no version bump.
- **Surfaces moved**: 5 scripts + 1 new module, 5 regenerated reports, pin tests, `docs/README.md` row,
  invariants, drift-and-obligations, GOVERNANCE, architecture-validation, EVIDENCE re-point. Docs-site
  assembly remains content-agnostic (ranks by filename).
- **CI cost**: measured standalone suite times (process incl. interpreter): registry 0.92 s, execution
  0.23 s, interface 0.84 s, closure 0.04 s, devices 0.48 s. The pin design adds **one clean + one
  tmp-tree execution per new suite** (tamper shares one execution across its three modes; devices tamper
  drops from three executions to one) — worst case ≈ +2.5 s in-process against a measured module baseline
  of 8.28 s / 23 tests. No session fixture needed at this size; #79's adjustment lever stays available.

## 7. Pre-committed acceptance rule (numbers below were measured BEFORE this record was written; the rule is committed before any writer lands)

**Metric** — per suite: byte-equality between the committed report and a fresh sorted render of a live
run; the three designed failure modes of that equality; the portability guard; the README row counts;
writer refuse-on-red; determinism across platforms (CI is the ongoing instrument).

1. **RED (ships nothing until seen)**, on the unmodified `5345f01` tree with only the new tests added:
   - `test_validation_report_matches_live_run[registry|execution|interface|closure]` all FAIL on byte
     mismatch;
   - the portability guard FAILS naming interface's two and closure's one absolute-path check names;
   - the interface README count assert FAILS (254 vs live 256).
   Collected counts shown; `no tests ran` is a FAILED RED check.
2. **GREEN** and the **pre-committed expected regen diffs** — any deviation from this table is a stop, not
   a fix-the-prose moment:

   | Report | Expected diff, nothing else |
   |---|---|
   | otdp 0.2.0 | coverage paragraph only: "Twelve"→"12", "fifty"→"50" |
   | registry 0.1.1 | + marker; headline → `**Result: 64/64 checks passed; 0 failed.**`; + `## Checks`; "three"→"3"; check lines re-sorted (64-line permutation, set-equal) |
   | execution 0.1.0 | marker; headline form (150/150); `## Checks`; "six"→"6"; re-sort (set-equal) |
   | interface 0.1.0 | marker; headline `**Result: 256/256 …**`; `## Checks`; "twenty"→"20"; re-sort; **+2** lines (the normalized `Stored fixture agrees:` names); README row 254→256 |
   | docs/acceptance | marker; headline `**Result: 17/17 …**`; `## Checks`; "Sixteen"→"16", "twenty-six"→"26"; re-sort; **+1** line (normalized name) |

   `pytest tests/contracts/test_architecture.py` green locally AND in CI; writer idempotence (run
   `--write-report` twice → zero diff); writer-refuse pin green.
3. **Ship direction**: RED observed → GREEN local + CI, with the PR showing each regen diff matching its
   table row (reviewer verifies `sorted(old) == sorted(new)` for the permutation claims).
4. **Kill directions**:
   - CI (ubuntu) render ≠ macOS-authored bytes for any family report → the byte-pin is wrong for the
     family; fall back to count+membership assertions and record the honest negative here.
   - The otdp regen diff is anything beyond the two digit edits → the shared-renderer refactor is not
     representation-stable; STOP and reconcile the template, never the report prose.
   - Any table row's diff shows a check line not listed in that row → the tree moved mid-arc; re-measure
     and re-commit the table BEFORE regenerating.
   - Added module time > 10 s (ceiling ≈ 18.3 s vs the 8.28 s baseline) → mechanical adjustment first
     (share suite executions, #79 rule 7.4); if irreducible, rotate tamper modes per suite and record the
     weakening.
   - The writer writes on a failing run by any path → the refuse pin must fail first; a bypass in the
     shared module is a design failure, not a bug to patch quietly.
5. **Underpowered criterion**: determinism evidence is 2 platforms × ongoing CI renders. A future platform
   disagreement MUST surface as a loud pin failure with a diff; if it ever surfaces as a flake instead,
   the pin is underpowered and is replaced by the count+membership fallback.

## 8. RED→GREEN commit slicing (one slice per commit)

1. This design record.
2. RED: all new tests (family pin, tamper, portability guard, README asserts, writer-refuse pin) +
   manifest-derived regression-fixture rows — watched failing with collected counts.
3. Shared module + `check_devices.py` delegation — devices pin stays green throughout (byte-neutrality of
   the refactor, D2-style), everything else still red.
4. Registry slice: writer + regen + README/none → its params green.
5. Execution slice (+ EVIDENCE re-point).
6. Interface slice (+ name normalization, README 254→256).
7. Closure slice (+ name normalization).
8. otdp D3 slice (two digit edits) — if slice 3 left devices green, this lands the f-strings and the regen.
9. Docs surfaces: CON-11 amendment, drift row 13, GOVERNANCE (incl. dangling-sentence fix),
   architecture-validation.

One PR (`feat/issue102-d1-report-family`), no stack — no SDK PR, no cross-repo pointer, no bump.

## 9. Top risks and falsifiers

| Risk | Falsifier |
|---|---|
| `runpy.run_path` import mechanics differ somewhere (the bootstrap breaks a lane) | Measured probe at this baseline (§2.1); CI is the cross-lane check — an ImportError is loud, not silent. |
| The normalized `Stored fixture agrees` names have a hidden consumer | Text-searched at this baseline: only the substring matcher in `test_contract_regressions_are_detected`, preserved by the rename. |
| Duplicate check names make sorted rendering ambiguous | Set-equality verified per suite (§1); duplicates would still render deterministically (tuple sort). |
| EVIDENCE re-point misses rows | Measured: exactly 3 citations of the execution report (lines 109/110/886); registry/interface/closure reports have zero line citations. |
| The frozen-sweep EVIDENCE doc is treated as living, laundering history | The rows' quoted content is unchanged; only the anchor moves; the diff shows it; the header's "DATA ONLY at `8bec884`" framing is untouched. |
| plugin-ui DON'T-BUILD is challenged as scope-dodging | §7's evidence: no checks-list substrate; train-record substance; live claims already pinned by pytest suites in gates. |
| Line-ending drift on regen (LF vs platform) | `write_text(..., newline="\n")` + gitattributes LF (established #79 behavior, otdp report pinned in CI since). |

## 10. DON'T-BUILD — plugin-ui machine-writing (evidenced)

`standards/plugin-ui/0.2.0/validation-report.md` is not a suite rendering; it is the **train evidence
record** for the 0.2.0 increment (issue #62). Verified at this baseline:

1. **No substrate.** No `check_plugin_ui.py` exists; the live validation surface is pytest assertions
   (`tests/architecture/test_plugin_ui_contracts.py` — 8 tests over the four schemas; plus
   `tests/standards/test_scenarios.py` and the presentation unit suites). There is no accumulated
   `(name, bool)` checks list to render; converting pytest into one is new architecture, and principle 9
   demands a justification the value cannot supply (next point).
2. **The substance is not recomputable.** The report cites the design record, commit SHAs, a RED census
   (35 collected / 11 failed), gate outcomes, SDK-repo state and key-material notes — historical facts of
   a past run. Template-izing them would fabricate "evidence" from constants — precisely the laundering
   the writer pattern exists to prevent (the system records evidence; it must not manufacture it).
3. **The live claims are already machine-pinned elsewhere**: schema validity/versioning/closed-world by
   `test_plugin_ui_contracts.py`, scenario behavior by `test_scenarios.py`, SDK↔corpus agreement by
   `make check-sdk-standards` — all in `gates`. The residual a writer+pin would add is protection against
   hand-edits to historical narrative, the same class design records carry (committed, review-guarded).
4. **CON-11 already treats such reports correctly**: superseded versions' reports are frozen historical
   evidence — plugin-ui 0.1.1's is the 0.1.1 train record. The active one is the same kind of artifact;
   the family invariant wording says so explicitly rather than by omission.

A pin to nothing is worse than no pin; this is a reasoned exclusion, not a deferral of work someone
forgot. Its reopen trigger is structural (D1-a).

## 11. Maintainer decisions (appended pre-build)

Three row calls made by the maintainer loop before the build started; the build applies them
rather than re-litigating (the D2 record's appended-corrections pattern).

1. **D3 = digits — confirmed as designed (§2.2).** Word form drops for digits; the numbers
   are derived at module scope from the values the suites already compute.
2. **The EVIDENCE re-point is DROPPED.** §4's row for `EVIDENCE-annotations-and-versions.md`
   is removed: that file is untracked local-only data in the maintainer's main checkout
   (absent from `origin/main`), so a PR cannot carry the edit and the file is not this
   build's to touch. Accepted consequence, recorded here instead of in code: the file's
   three execution-report line citations (its rows at its lines 109/110 and the narrative
   at 886, citing `validation-report.md:128/129`) go stale when the execution report
   regenerates; the quoted content in those rows is unchanged.
3. **D1-b (plugin-ui test-path literals) becomes a follow-on issue**, filed by the
   maintainer loop at PR-open time — not part of this build.

## 12. Review folds (appended)

Corrections from the first review wave (mechanism-critic 8 findings, standards-governor
LOW + NITs), appended per the D2 appended-corrections pattern — committed history above
is not rewritten.

- **F5 (wording):** §2.1's "reproduces the existing `otdp_manifest_absent:` bytes exactly
  for devices" overstated: only the refusal PREFIX is byte-stable; the message text after
  the prefix is generic lowercase ("active otdp", not the historical "active OTDP"). The
  shared module's docstring now says exactly that, and a new pin covers the second
  refusal branch (manifest present, entry missing → `registry_manifest_absent` through
  the registry script).
- **F3 (lens):** §2.2's interface row derived the prose count from `len(vec)` (a list)
  while the pin checked the name-set cardinality — equal today, divergent under a
  duplicate catalog entry. Both now read one `unique_operations` var (closure's pattern);
  the regen diff after the change was empty (byte stability proven by the pin).
- **F1 (rebase):** main's #125 run landed mid-review; the branch rebased cleanly onto it
  with one semantic adaptation (#125's zero-arg `_active_report_path()` call takes
  `"otdp"` now). The rebase moved no report bytes (pre/post-rebase diff over standards/
  and docs/acceptance/ empty).
- **NIT-2 (frozen history):** `docs/README.md`'s baseline-verification sentence ("OTDP
  495, registry 64, execution 150, interface 254 and closure 16") is named in the D3-b
  deferral row as frozen 0.1.0-review history that is never "corrected" when live counts
  move.
- **F6/LOW-1 (GOVERNANCE precision):** the derivation sentence now distinguishes the
  four standards-tree scripts' manifest-derived corpus directories (devices' variable is
  `OUT`) from their version-free title constants (devices' title alone embeds the
  version), and carries the closure carve-out (docs-rooted `CONTRACT_DIR`; cross-standard
  reads manifest-derived).
- Also folded without record-level correction (code/test-side only): F2 census guard
  (writers ↔ REPORT_SPECS symmetry + full artifact classification with the plugin-ui
  train-record exclusion), F4 duplicate-name census, F7 byte-for-byte drift comparison
  (CRLF can no longer launder through universal newlines), F8 POSIX-absoluteness arm on
  the portability guard with its not-caught disclosure.
