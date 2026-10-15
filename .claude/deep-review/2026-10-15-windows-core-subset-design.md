# Windows CI core subset — design of record (issue #471)

**Date:** 2026-10-15
**Issue:** [madeinoz67/benchweave#471](https://github.com/madeinoz67/benchweave/issues/471)
**Directive:** owner, 2026-10-15 — scope the Windows CI lane to the cross-platform
core subset (the tests POSIX runs cannot substitute); the full suite stays on the
Linux lane and local runs.
**Status:** design only — no build in this record. This record is the branch's
first commit (`feat/windows-core-subset` off `origin/main` at `1a2e3b0b`), design-of-record
convention.

---

## 0. Pre-commitment protocol

The acceptance rules (§7) were fixed in this record BEFORE any post-design
measurement runs. Every number already present was measured BEFORE this record was
written and carries its measurement source inline (whose machine, whose checkout,
whose command). No mechanism below is sized from a number it also promises to
deliver: the §7 budget rule (AR-3) is stated from measured setup/step/parallelism
data, and the thing it judges (the built lane's wall-clock) is a future
measurement. The 44-vs-10 failure classification (§4.2) is an evidence
classification of an already-collected artifact, not a rule tuned after the fact —
the classes were derived from the issue's own class list and the artifact's failure
texts, both pre-existing.

## 0.0 Tier statement and Step-1 keyword scan (#254)

**Tier: 3** — triggered by the keyword rule (Step-1, first-match-wins: "the diff
text contains any of …"), not a path rule. Scan over the WHOLE expected diff
(docs and code alike):

| keyword | expected hits | where |
|---|---|---|
| `recovery` | ≥2 | `tests/win_core_manifest.json` rows for `tests/faults/test_state_recovery.py` and `tests/integration/test_event_recovery.py` (the manifest pins ALL files' totals); the `pytestmark` edit in `tests/faults/test_state_recovery.py` |
| `subprocess` | ≥1 | the manifest generator shells out to pytest (`scripts/ci/win_core_manifest.py`) |
| `sha256` | 0 | — |
| `hashlib` | 0 | — |
| `threading` | 0 | — |
| `asyncio` | 0 | — |
| `migrate` | 0 | — |
| `protection` | 0 | — |

The manifest pins all 228 test files' totals, so the file NAMES of fault/recovery
suites ride the diff text no matter what is marked — the keyword rule is
text-based by design and the honest result is Tier 3. Per the standing rule for
Tier 3 (and retro 2026-09-24 R3), the build's review battery runs TWO independent
adversary lanes. Path-tier rules that would have said Tier 2 (`.github/`,
`pyproject.toml`, `tests/`) do not fire first; the keyword rule wins by
first-match-wins. The standards-governor mandate does NOT apply (zero
`standards/` bytes move; tripwire asserted at push).

## 1. Thesis

The Windows evidence lane runs the full 3,879-test selection (`-m "not timing and
not browser"`) and costs 18m28s per PR (PR #464, run 38661209859: setup ~20s,
test step 17m56s). Scoping it to a written-down, mechanically selected,
mechanically verifiable core subset cuts the job to a target ≤ 10 minutes while
keeping every genuinely Windows-only code path and every Windows-differing
semantic the POSIX lanes cannot substitute, corroborated on Windows — and makes
the complement a recorded, enumerable, owner-visible decision instead of an
accident.

The lane's evidence posture is unchanged: `continue-on-error` stays, the junitxml
artifact and failing-id summary stay, graduation (slice 2, delete one line) stays
an owner call.

## 2. What the code says (verified this session)

### 2.1 The lane today

`.github/workflows/ci.yml` `windows` job: runs the SAME selection as `gates` (`-m
"not timing and not browser"`) on `windows-latest`, `timeout-minutes: 45`,
`continue-on-error: true` on the test step only, junitxml evidence uploaded, an
`Evidence summary` step rendering counts + failing ids from the junit, and fixture
keys materialised exactly as `gates`. The byte-exactness posture rides
`.gitattributes` `* text=auto eol=lf` in both repos; a digest-mismatch red on
Windows is the canary for that posture.

### 2.2 Where the 18 minutes actually go (measured)

Per-test timings from the run's own `windows-evidence.xml` artifact (run
38661209859, PR #464 head `c796ea30`; 4,044 testcases, 54 failures, 16 skipped,
wall 1,073s, summed per-test 3,766s — xdist parallel efficiency ≈ 3.5×):

- Setup steps: ~20s total (checkout 12s, uv install 1s, keys 1s, `uv sync --locked` 5s).
  **The setup is nearly free; the test step is the whole cost.**
- Top Windows-cost files: `tests/cli/test_dispose.py` 691s (50 tests, ~14s/test —
  archive fsync/staging legs), `tests/standards/test_promotion.py` 366s,
  `tests/standards/test_dev_pins.py` 266s, `tests/cli/test_lifecycle.py` 175s,
  `tests/standards/test_check.py` 170s, `tests/contracts/test_architecture.py` 140s,
  `tests/standards/test_why.py` 129s, `tests/cli/test_retention.py` 107s.
- None of the top-3 cost hogs is a Windows-only code path. The 18-minute cost is
  dominated by cross-platform suites whose cost is fsync/subprocess/git-in-tmp —
  not by the platform-shaped tests. **This is the root cause of the directive's
  cost, and it is why a core subset works: the platform-shaped set is small
  (~5-6% of the selection) and cheap relative to the bulk.**

### 2.3 The genuinely Windows-shaped surface (the classes' subject matter)

Verified in `src/benchweave` this session (`1a2e3b0b`):

- `src/benchweave/state/hold.py:38` — the STO-3 store hold: `msvcrt.locking` vs
  `fcntl.flock`. Only a Windows process executes the `msvcrt` branch; POSIX
  cannot substitute (the portable contract tests run the real branch only on
  Windows).
- `src/benchweave/supervision.py` — win32 arms at :213 (`_probe_windows`, ctypes
  liveness), :581/:607/:616 (`TerminateProcess` via `os.kill(pid, 9)`, the
  truthful signal name), the doorbell owner-skip; `interfaces/supervision.py:223`
  — the POSIX-only SIGTERM handler install.
- `src/benchweave/cli/lifecycle.py:105` — the `_POSIX` flag.
- `src/benchweave/cli/diagnose.py:272`, `cli/atrest.py:166` (the 0600/ACL
  credential posture, #137), `cli/commands.py:139` (the setup message),
  `cli/env_file.py:96` — win32 arms.
- Test-side platform constructs: `tests/cli/test_render.py:96` (probe-gated
  skipifs), `tests/cli/test_retention.py:754-826` (the `time.tzset` guard).

### 2.4 The failure census is the empirical core-class map

> **Addendum (refute fold, 2026-10-15):** the bullet families below itemize 41
> of the 44 core-class failures this narrative claims (13 promotion + 7
> dev_pins + 6 check_sdk_submodule_drift + 4 zero_literal + 2 atrest + 5
> lifecycle + 4 sqlite = 41). The unlisted 3 include the 2 diagnose failures
> the founding arithmetic counts (tests/cli/test_diagnose.py — the W1 map's
> cli/diagnose.py row; whole-module marks count every test in the file); the
> third unlisted failure is itemized nowhere in this record.

The 54 Windows failures in the #464-run artifact classify by the issue's own
classes (native separators, CRLF writes, encoding defaults, file-locking, sqlite
I/O):

- Native-separator leak in a constructed message: `promotion_sweep_violation:
  otdp/0.4.0/examples\class-action-vectors.json` (13 promotion failures).
- Windows file-locking in cleanup: `PermissionError: [WinError 5] …
  .git\objects\pack\pack-*.idx` on `shutil.rmtree` (7 dev_pins failures).
- CRLF canonical-file writes: `fatal: bad config line 2 in file .gitmodules`
  (6 `check_sdk_submodule_drift` failures) and the #207 repin family
  (`corpus_manifest_not_canonical`).
- Encoding defaults: `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb7`
  in a zero-literal scratch run (4 zero_literal failures — docs written with
  default encoding on Windows = cp1252).
- Windows-only platform APIs: `time.tzset` absence (#207), the datetime-range
  limit (#207), the 0600-mode/ACL credential arms (2 atrest failures), the
  pidfile/spawn/signal-path arms (4 lifecycle + 1 lifecycle_faults failures).
- sqlite disk-I/O intermittents: 3 disposition_faults + 1 state_recovery
  (the #207 census family).

**44 of the 54 are core-class by this classification; 10 are borderline
(§4.2).** A founding core that ignored the observed failure families would gut
the lane's evidence value — the failing platform tests ARE the evidence stream
the lane exists to carry.

## 3. Precedent extended (and what loses)

1. **The gates/timing/browser complementary-marker partition** (issue #241 slice 1,
   #300 G1d slice 4) — the proven in-tree shape: complementary markers,
   union-equal/pairwise-empty proof at PR time. The core subset is a SUBSET
   relation, not a partition member, so the new proof is: wincore ⊆ gates-selection,
   wincore ∩ timing = ∅, wincore ∩ browser = ∅ — pinned by a test, not prose.
2. **The #221 docs-baseline ratchet** (`scripts/standards/docs-literal-baseline.json`
   + `--refresh-docs-baseline`, growth AND shrinkage refuse, the refresh diff is
   the review surface) — the proven no-silent-drop shape. The core manifest is
   this ratchet applied to the test partition: every test file's (total, core)
   counts pinned; growth/shrinkage refuse; refresh is an explicit flag whose diff
   is the review surface.
3. **The #207 platform-conditional simulation doctrine** — POSIX-side simulation
   keeps Windows shapes covered on Linux; this design does not weaken it. The
   core subset's job is the RESIDUAL the doctrine cannot buy: the real `msvcrt`
   branch, real TerminateProcess, real CRLF-on-disk defaults, real case-mapping,
   real sqlite-on-Windows — the things a simulated arm cannot execute.
4. **#254 design-time tier call** — §0.0.

**Alternatives that lose:**

- **Pure marker, no manifest** (a bare `wincore` marker): new tests inherit
  complement by default with nothing to catch a Windows-relevant test landing
  unmarked — a silent drop by construction. Loses on rule 2.
- **Pure file-path manifest, no marker**: zero per-test precision (a whole-file
  rule drags 60-test files onto Windows for 2 relevant tests, e.g.
  `test_retention.py`: 60 tests / 107s for 2 core rows), and the selector is a
  path list in CI YAML — churn lives in the workflow, the least reviewable diff.
- **Per-test marker + count-ratchet manifest (SELECTED)**: per-test precision for
  W2/W3, whole-module marks only where the W1 map says so; every partition change
  is a visible manifest diff; new tests inherit complement by default AND are
  visible (total-count ratchet); misclassification is caught by the probe (W1),
  the count ratchet (additions), and the owner's manifest-diff review (marking).

## 4. The selection rule (written down)

A test is **core** iff it satisfies **W1**, **W2**, or **W3**:

### W1 — platform-branching source units (whole-module, probe-mechanical)

Every test in a module that exercises a `src/benchweave` module carrying a
`sys.platform == "win32"` / `!= "win32"` / `msvcrt` branch. Selected WHOLE-MODULE
(`pytestmark = [pytest.mark.wincore]`), because the branch executes at
module-level call depth that per-test curation cannot bound honestly. The map is
carried in the manifest's `w1_map` section and pinned by a source-probe test:

| src module (probe hit) | test module(s) |
|---|---|
| `state/hold.py` | `tests/unit/test_store_hold_portable.py` |
| `supervision.py` | `tests/cli/test_lifecycle.py`, `tests/faults/test_lifecycle_faults.py` |
| `cli/lifecycle.py` | `tests/cli/test_lifecycle.py` |
| `interfaces/supervision.py` | `tests/cli/test_lifecycle.py` |
| `cli/diagnose.py` | `tests/cli/test_diagnose.py` |
| `cli/atrest.py` | `tests/cli/test_atrest.py` |
| `cli/commands.py` | `tests/cli/test_commands.py` |
| `cli/env_file.py` | `tests/cli/test_env_file.py` |

### W2 — platform-sensitive semantics (per-test, evidence-based)

A test whose execution exercises OS-differing behavior the Linux run cannot
substitute, with a platform-attributable failure observed in CI (or the #207
contributor census) as its evidence. Founding members (all measured on Windows in
the #464-run artifact; ids abbreviated `...::<name>`):

| family | tests | evidence | summed cost |
|---|---|---|---|
| `tests/standards/test_promotion.py` | 13 failing | native-separator sweep-violation messages | 157.1s |
| `tests/standards/test_dev_pins.py` | 7 failing | rmtree WinError 5 on `.git` pack idx | 118.1s |
| `tests/unit/test_check_sdk_submodule_drift.py` | 6 failing | `.gitmodules` CRLF (`bad config line 2`) | 8.7s |
| `tests/standards/test_zero_literal_gate.py` | 4 failing | cp1252-vs-utf-8 scratch-run decode | 5.0s |
| `tests/faults/test_disposition_faults.py` | 3 failing | sqlite disk-I/O kill-mid arms (#207 family) | 3.2s |
| `tests/faults/test_state_recovery.py` | 1 failing | sqlite kill-after-commit arm | 0.5s |
| `tests/cli/test_retention.py` | 2 (#207) | `time.tzset` absence; datetime-range | 3.8s |
| `tests/control/test_corpus_seam.py` | 1 (#207) | native backslash in refusal | 0.02s |
| `tests/standards/test_export.py` | 1 (#207) | backslash keys vs POSIX listing | 0.08s |
| `tests/standards/test_repin.py` | 2 (#207) | CRLF canonical-JSON writes | 3.4s |

### W3 — byte-exactness / digest canary (named, small)

A named set of digest-verification tests keeping the `.gitattributes` `eol=lf`
posture canaried on Windows. Founding: `tests/contract/test_registry_fixtures.py::test_builder_is_deterministic`
(3.8s — it FAILED on Windows in the #464 run: the canary class FIRING, exactly
the digest-canary evidence the lane exists to carry), plus the digest rows of
`test_repin.py`/`test_export.py` already marked W2 above. **The core always
carries ≥1 digest-read test, so the eol=lf canary survives the subset.**

### 4.2 The borderline rows (disclosed, excluded from founding core)

> **Addendum (refute fold, 2026-10-15):** the run_activation row misnames 3 of
> its 4 ids: the #464 artifact's four run_activation failures are `d1`, `f5`,
> `r14` ×2 — the table's `test_f5_…` ×4 shorthand wrongly implies four f5
> runs. Reopen triggers cite ids, so this correction is load-bearing.

Ten of the 54 observed failures are NOT founding-core, with per-row reasons:

| test (abbrev) | failures | why excluded |
|---|---|---|
| `render::test_live_drive_feeds_events_until_terminal` | 1 | SSE streaming — flake signature, no platform attribution |
| `run_activation::test_f5_…` ×4 | 4 | timing-flake class (#207: f5 failed 3/3 isolated on Linux too) |
| `event_recovery::test_evidence_storage_failure_emits_evidence_gap` | 1 | fault-injected storage failure — attribution uncertain |
| `demo_lattice_streaming::test_demo_lattice_admits_and_streams` | 1 | single-run evidence |
| `gate_wrapper::test_piped_summary…`, `::test_mypy_pass_path…` | 2 | CI-script semantics, attribution unproven |
| `why::test_m2_the_dev_refusal_propagates_verbatim` | 1 | corpus-message path, attribution unproven |

Reopen trigger for every row: a second CI Windows run exhibiting the same failing
id (observable on the artifact).

## 5. The mechanism

### 5.1 Selector

A new pytest marker **`wincore`**, registered in `pyproject.toml`
`[tool.pytest.ini_options].markers` beside `timing`/`browser`/`slow`:

```
wincore: cross-platform-critical Windows evidence subset (issue #471) — W1
platform-branching source units (whole-module), W2 platform-sensitive semantics
and W3 byte-exactness/digest canary (per-test); runs in the windows CI lane
(`-m wincore`) and in the default gates run like every other test. Deselect
locally with -m 'not wincore'.
```

CI: the windows job's test step becomes `uv run pytest -q -n auto -m wincore
--junitxml=windows-evidence.xml`. `timeout-minutes: 45 → 20` (measured expected
~4-5 min; 4× headroom; R5). Fixture-keys step: KEPT (harmless; W3 may grow
signing rows later — disclosed). The Evidence summary step: unchanged code; its
message text notes the core selection.

### 5.2 The no-silent-drop mechanism (rule 2)

> **Addendum (refute fold, 2026-10-15):** the closing cost note ("the check
> adds ~5-10s to gates") names `--check` alone (5.8s, the refute lanes'
> measurement). The partition MODULE costs more in gates: ~15 subprocess
> pytest collections, 39.1s suite time / 39.6s wall at the post-fold
> 11-test module (this machine, 2026-10-15; the lanes measured ~33-35s over
> 12 collections pre-fold). AR-3's budget walk carries the file-level
> number.

Three machines, all test-side (pre-merge, on Linux in `gates`):

1. **The ratchet manifest** — `tests/win_core_manifest.json`, committed,
   generated by `scripts/ci/win_core_manifest.py` (`--check` / `--refresh`):
   per-file `{total, core}` for ALL test files (228 today), plus the `w1_map`.
   Growth AND shrinkage of any file's counts refuse (`--check` exit 1) until
   `--refresh` moves the file — **the refresh diff is the review surface, the
   #221 shape**. A test added anywhere is a visible manifest diff; a marking
   decision is a visible `core`-count bump; nothing about the partition can move
   silently.
2. **The source probe** — a partition test pins the win32/msvcrt-branching src
   file set (text scan of `src/benchweave`, the #207 probe-doctrine shape): a
   NEW win32 branch in an unmapped src file reds the probe until the file joins
   `w1_map` (and its tests are marked) — a visible diff; a mapped src file whose
   probe hit disappears reds the dead-row check.
3. **The partition proof** — pinned by a test in `tests/contract/test_win_core_partition.py`:
   wincore ⊆ gates-selection (every wincore id appears in the unfiltered
   collect), wincore ∩ timing = ∅, wincore ∩ browser = ∅, and `--check` exits 0
   on the committed manifest. Detection teeth: the test runs `--check` against a
   doctored manifest (one row dropped) in `tmp_path` via a `--manifest` override
   flag and asserts nonzero exit — **the RED proof lives in the suite, not in a
   PR-body claim**.

Collection is 2.5s measured (this machine; `time uv run pytest --collect-only -q`
= 2.5s wall for 4,030 tests across 228 files), so the check adds ~5-10s to gates
— no budget concern.

### 5.3 Files moved by the build slice

| file | change |
|---|---|
| `.github/workflows/ci.yml` | windows test step `-m wincore`; timeout 45→20; job comment rewritten (classes, manifest, obsoleted retro row); Evidence-summary message text notes the core selection |
| `pyproject.toml` | `wincore` marker registration |
| 7 W1 test files | `pytestmark = [pytest.mark.wincore]` |
| ~9 W2/W3 test files | per-test `@pytest.mark.wincore` on the founding rows |
| `scripts/ci/win_core_manifest.py` | NEW — `--check`/`--refresh`/`--manifest <path>` |
| `tests/win_core_manifest.json` | NEW — the committed ratchet (228 file rows + `w1_map`) |
| `tests/contract/test_win_core_partition.py` | NEW — partition proof + probe pin + teeth |
| `docs/internal/drift-and-obligations.md` | CI map `windows` row moves (obligation 4 / G5 walk) |
| `docs/development.md` | :146-147 windows-lane sentence moves |

Zero `standards/` bytes; no dependency change (no `uv.lock` move); no src change.

### 5.4 Degrade / graduation interaction (rule 3)

- **Evidence posture unchanged**: `continue-on-error` stays on the test step;
  junitxml + failing-id summary stay; merge-verified's zero-red rollup rule
  unchanged. Graduation (slice 2, delete one line) stays an owner call — the
  subset changes the lane's SCOPE, never its POSTURE.
- **#207 census discipline**: the failing-id summary is unchanged mechanically;
  the census's denominator narrows from the full selection's failures to the
  core's (~44 known platform-attributable failures at founding). The complement's
  failures leave the per-PR census — that is the visible trade; R1 is the owner
  lever for it.
- **W1 doctrine**: "Windows surfaces = CI-corroborated" holds BY CONSTRUCTION for
  Windows-only code paths — W1 is probe-mechanical, so a Windows-only branch
  cannot exist without its tests being map-visible; the W2/W3 classes keep the
  semantics + canary corroboration. Post-merge Windows runs stay evidence; the
  evidence is now scoped and recorded.

## 6. Census (the design's denominator; every number says whose measurement)

> **Addendum (refute fold, 2026-10-15):** census reconciliation. The record's
> full-collection row (4,030/228) EXCLUDED the ui-contract.md contract gate
> the manifest pins (`docs/internal/ui-contract.md`, 196 items — manifest
> row core 0 / total 196). Reconciled at the #471 tip: full 4,226/229
> (+196 from the md), gates selection 4,075/222 (measured this session; the
> record's 3,879/221 excluded the md), core 214 (manifest sum), complement
> 3,861 (= 4,075 − 214). The record's complement (~3,661 = 3,879 − 218
> estimated core) and the reconciled one name different denominators — the
> record's is the design-time estimate, the reconciled one is the
> manifest-pinned tip; both stand as labeled.

All collection counts: THIS checkout, `origin/main` `1a2e3b0b`, macOS arm64,
`venv`, `UV_PROJECT_ENVIRONMENT=venv uv run pytest --collect-only -q`, counts
read from the raw per-file lines (junitxml/exit-code evidence protocol — the rtk
filter's summary line is untrustworthy, 5 documented instances):

| quantity | value |
|---|---|
| full collection | 4,030 tests / 228 files |
| gates selection (`not timing and not browser`) | 3,879 / 221 files |
| timing | 77 · browser: 74 (3879+77+74 = 4030, union equal) |
| slow | 6 (4 integration files) |
| founding core | **~218 tests** (W1 172 + W2 41 + W3 ~5, overlap-adjusted) |
| complement | **~3,661 tests** (3,879 − 218) |
| founding-core summed Windows cost | ~560-570s (measured per-test, #464 artifact) |
| estimated core test-step wall | ~2.7-3.8 min (sum ÷ measured 2.5-3.5× xdist efficiency) |
| estimated job total | **~3.5-5 min** (vs 18m28s today) |
| observed-failure classification | 44 core-class / 10 borderline-excluded (of 54) |

## 7. Acceptance rules (pre-committed)

> **Addendum (refute fold, 2026-10-15):** AR-2's second sentence names the
> wrong direction: removing a `w1_map` row with its probe hit intact fires
> the UNMAPPED check (a live win32/msvcrt hit with no map row). The
> dead-row check fires when a map row exists with NO live hit — an ADDED
> fake row (pinned in-suite by `test_teeth_added_fake_w1_map_row_refuses`)
> or a row whose src branch disappeared. The deletion tooth
> (`test_teeth_dropped_w1_map_row_refuses`) fires the unmapped direction;
> its docstring's "(AR-2 dead-row)" citation is corrected in-suite.

- **AR-1 (partition integrity + teeth).** At build: the partition test is GREEN
  on the branch (manifest `--check` exit 0; subset/disjointness holds); and its
  detection teeth RED — the doctored-manifest arm exits nonzero, and
  de-marking one W1 test reds `--check`. Kill: if the teeth cannot be made to
  red, the ratchet does not detect — redesign before landing.
- **AR-2 (probe teeth).** Planting a `sys.platform == "win32"` branch in an
  unmapped `src/benchweave` file (scratch, reverted) reds the probe test;
  removing a `w1_map` row with its probe hit intact reds the dead-row check.
  Kill: either fails to red → the W1 map is not mechanical → redesign.
- **AR-3 (budget, 3-run rule).** Post-landing, the windows job total on 3
  consecutive main-branch CI runs: TARGET ≤ 10 min. Kill: > 12 min sustained on
  3 consecutive runs → the core is over-broad or the cost model is wrong → trim
  W2 marks or re-scope per the classes. If ≤ 4 min sustained, the owner may
  revisit scope (under-scoped, add classes deliberately).
- **AR-4 (ratchet live behavior).** Over the first 10 PRs after landing: every
  test-adding PR reds `--check` until refreshed (visible diffs — the mechanism
  working); more than 1 spurious red not attributable to a real collection
  change = mechanism noise → fix the mechanism before any scope growth.
- **AR-5 (evidence stream is not silently green).** The FIRST core-subset run
  carries ≈ 44 known platform-attributable failures (from the #464-run census,
  §4.2/§6; fewer only if upstream #207-family fixes landed in between — each
  such fix is a visible PR). All-green on the first run with no census
  explanation = the founding selection missed the failing platform tests →
  investigate before any further change.
- **AR-6 (complement recorded).** The manifest + this record enumerate the
  complement (~3,661) and the 10 borderline exclusions with reopen triggers
  (§4.2). A future test landing in the complement is visible via the total-count
  ratchet; promoting it into core is a marking diff reviewed against the classes.

## 8. Row-calls for the owner (numbered; none written by default)

- **R1 — scheduled weekly full-selection Windows run (complement corroboration).**
  The complement (3,661 tests) leaves per-PR Windows evidence; a weekly cron lane
  (~20 runner-min/week) keeps the #207 census's whole-run comparability and the
  W1 doctrine's "post-merge Windows runs ARE the test" honest for the
  complement. RECOMMEND FOR — but it works against the directive's letter ("the
  full suite stays on the Linux lane and local runs"); owner's call. Reopen
  trigger if DEFERRED: the second CI Windows run in which a complement-id
  failure that W2's evidence bar would have admitted goes unrecorded for a full
  week.
- **R2 — the ten borderline exclusions (§4.2).** RECOMMEND DEFER (stay
  complement). Reopen trigger per row: a second CI Windows run exhibiting the
  same failing id.
- **R3 — the standing retrospective row** ("splitting the lifecycle/diagnose arms
  onto their own lane", the 45m-timeout durable-fix idea in the windows job
  comment): **OBSOLETED/SUBSUMED by this design** — the timeout pressure was the
  full selection's bulk; the core subset removes it (~4-5 min expected, 20-min
  timeout = 4× headroom). RECOMMEND: close the row when this lands.
- **R4 — W3 founding membership** (the named digest-canary rows, §4/W3).
  RECOMMEND FOR as listed.
- **R5 — timeout 45 → 20 min.** RECOMMEND FOR.
- **R6 — DISSOLVED.** The gates cost add for the partition check was a
  candidate row-call; measured 2.5s collection (§5.2) — non-cost, folded here.

## 9. Top risks (each with its falsifier)

- **Over-marking flake noise into W2** (the census is ONE CI run):
  falsified by a W2 row that never reds again after upstream fixes land —
  mitigated by R2's evidence bar, the borderline table, and reopen-on-recurrence.
- **Windows runner variance**: the cost model's 2.5-3.5× xdist efficiency is one
  run's measurement; a quieter/louder hosted runner shifts it — AR-3's 3-run
  rule absorbs this; falsified if AR-3's kill direction fires.
- **Ratchet friction** (every test-adding PR refreshes the manifest): accepted —
  the #221 ratchet set the precedent and its friction is the point; falsified if
  AR-4's spurious-red rate exceeds the bar.
- **Under-selection** (a genuinely platform-sensitive test marked nowhere,
  never failed yet): the probe covers src-side only; test-side constructs
  (tzset-guarded tests in files with no src win32 branch) are caught only when
  they fail — on Windows CI per-PR only if marked, weekly if R1 lands. Residual
  named; the classes + owner-reviewed manifest diffs are the boundary.
- **Marker rot** (a W2 row's platform-sensitivity dissolves after a fix):
  visible via the manifest diff + AR-5's shrinking-failure expectation; the fix
  PR should remove the mark (visible diff) or re-cite evidence (owner row).
- **Review-cost false economy**: Tier 3 (keyword-triggered) buys a two-lane
  adversary battery for a CI-config change — unavoidable under the rubric's own
  text-based rule; skipping it is the finding, not the cost.

## 10. Explicit deferrals

Nothing else deferred. The minimal first increment is the whole mechanism
(selector + manifest + probe + partition test + CI + docs); it defers only the
owner row-calls (§8) and any scope GROWTH (new W2 rows beyond the founding
census, new W3 rows, R1's scheduled lane), each of which rides a named trigger
(R2's reopen trigger per row; R1's trigger; the manifest-diff review surface).
