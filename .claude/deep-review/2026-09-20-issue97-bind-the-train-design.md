# Issue #97 — Bind the release train: a prescriptive per-standard bump window with a mechanical enforcement point

- Date: 2026-09-20
- Status: design (pre-implementation; this record is committed before the fix commits on `feat/issue97-bind-the-train`)
- References: gateway issue #97 (re-scope comment 5748876078), GOVERNANCE.md §Bump minimization, issue #102 (D2 — separate, later), measurement comment 5748545727
- Severity: governance doctrine + mechanical check; no corpus bytes move, no digest model change, no invariant change

## 1. Root cause — verified against the file and the history

GOVERNANCE.md:32-34 defines a release train descriptively — "one merge window of a run:
PRs opened concurrently against the same `origin/main`". Nothing opens a train, nothing
closes one, nobody decides. Measured consequence (comment 5748545727): sequential merges
make every bump trivially its own train, so "one bump per (standard, release train)" is
satisfied by definition. The 4.8-hour otdp 0.1.2→0.2.0 pair did not violate the rule —
it satisfied it. That is the whole churn mechanism, and no amount of batching language
fixes it, because the batching condition ("share a train") is never false.

## 2. Mechanism

Three coordinated changes. No more.

### M1 — GOVERNANCE.md: the prescriptive window paragraph

Directly after the train definition sentence in §Bump minimization, one new paragraph:

> **Bump window (#97).** The train rule is prescriptive, not descriptive: a standard
> may not bump more than once per **48-hour window**, measured between the committer
> timestamps of the commits that added each new version directory. A queued change to a
> standard still inside its window WAITS — it batches into the next bump of that
> standard (the highest-class rule above already governs what the batch becomes). The
> window is per standard: bumping otdp does not open or close a window for registry.
> Exempt: a standard's first version (admission), and a reset-class commit (one commit
> adding version directories for three or more standards — the 2026-09-16 signature).
> The 48-hour floor is a starting figure ratified with this rule; it is revisited after
> three windows, not silently.

The existing train/batching sentences stay; the paragraph converts their shared
condition into something that can be false.

### M2 — the enforcement point: `src/benchweave/standards/train_window.py` + `tests/standards/test_train_window.py`

The check the re-scope comment calls "not optional". Two layers:

- **Pure logic** (`train_window.py`): `window_violations(entries, floor_seconds)` over
  `BumpEntry(standard, version, commit_timestamp)` tuples, sorted chronologically.
  Per standard: consecutive bumps with `next - prev < floor` are violations, carried as
  `train_window_violation: <standard> <prev> -> <next> (<gap>h < floor>h)` entries.
  Exemptions applied by the collector, not the pure function: admission (first version
  dir for the id) and reset-class (≥3 standards' version dirs in one commit) never
  enter the pair sequence.
- **Repo integration** (the test): `collect_bump_entries(root)` reads
  `git log --diff-filter=A --format=%ct%x00<paths>` over `standards/<id>/<version>/`
  additions (subprocess with an argument array; never shell interpolation). The
  **clock anchor is self-locating**: only version-dir additions whose committer
  timestamp is at or after the commit that added `train_window.py` itself are checked
  — the rule's clock starts at the rule's arrival, so all prior history (the 4.8-hour
  pair included) is grandfathered by mechanism, not by a hand-maintained date
  constant. A tree where the module has just been added (this PR) sees one bump (none
  yet after the anchor) and passes.

The integration test asserts: (a) the real repo's post-anchor bump sequence has zero
violations at the 48h floor; (b) a synthetic violating sequence produces exactly the
prefixed refusal (the RED-honesty arm — proves the check can fire, so a passing
integration row can never be vacuous); (c) admission and reset-class exemptions hold
(synthetic); (d) the boundary case — second bump exactly at the floor — passes.

### M3 — CI legs that run the test get full history

`ci.yml` gates job checks out shallow by default (no `fetch-depth`); the test reads
git history, so the job gains `fetch-depth: 0` — the same setting `changelog.yml:45`
and `docs.yml:37` already run. No new job.

## 3. What this increment is NOT

- Not D2 (manifest-driven version discovery) — that is #102's D2, explicitly ordered
  after this by the re-scope ("1 first — it binds immediately and changes what 2 is
  worth").
- Not the `description`-guard side item (separate small row; the re-scope names both
  side items "not churn fixes").
- Not any dependency-management machinery — withdrawn in the re-scope comment.

## 4. Minimal first increment

1. Commit 1 — this design record.
2. Commit 2 — RED: `tests/standards/test_train_window.py` importing the not-yet-existing
   module (watched failing collection; the pure-logic arms fail on import), plus the
   synthetic violation/admission/reset/boundary tests written against the intended API.
3. Commit 3 — GREEN: `src/benchweave/standards/train_window.py` (pure function +
   collector), GOVERNANCE paragraph (M1), `ci.yml` fetch-depth (M3). Integration arm
   green on the real tree.

## 5. Invariant impacts

- No CON-* text changes. CON-7/CON-2 untouched (no manifest rows move). The check adds
  a NEW refusal surface (`train_window_violation:` joins the machine-matchable family)
  without touching existing prefixes.
- GOVERNANCE.md is tier-2 prose (not digest-pinned — measured: 0 of 42 md files are
  manifest rows), so the paragraph lands without a bump. The corpus is untouched.
- standards-governor review is mandatory (repo rule: any `standards/` change).

## 6. Measurable proof — pre-committed acceptance rule

Written before any test runs.

- RED: `uv run pytest tests/standards/test_train_window.py` fails on import of
  `benchweave.standards.train_window` (watched error, not a silent no-run;
  `--collect-only` shows the 4 tests).
- GREEN: all 4 tests pass; `tests/standards/` suite passes; bare `uv run mypy` clean;
  `uv run ruff check .` clean; full `uv run pytest -q` green (the gates battery).
- Kill-directions: if the integration arm cannot see git history locally (worktree
  path handling), that is a collector defect to fix, not a reason to skip the arm.
  If the 48h floor fails the REAL tree post-anchor (it cannot — the anchor is this
  PR and no post-anchor bump exists yet), the anchor mechanism is wrong: kill and
  report, do not patch around.

## 7. Top risks

1. **Committer-timestamp games** (rebase refreshes committer dates, potentially
   stretching an apparent gap). Mitigation: committer timestamp is what CI's
   merge-result sees and is the landing time the window means; author dates are
   forgeable and ignored. Residual stated, not guarded.
2. **The reset-class heuristic** (≥3 standards in one commit) mis-exempts a
   deliberately coordinated multi-standard bump that is not a reset. Disclosed in the
   paragraph; resets are executive-rare; the heuristic errs open on exactly one shape.
3. **Shallow clones elsewhere**: any future lane that runs this test without
   fetch-depth gets an empty history read. Collector fails LOUD on zero readable
   history when the module anchor commit exists but no log output is retrievable
   (distinct message, so a silent skip cannot masquerade as a pass).

## 8. DON'T-BUILD check

Triggered once, resolved: the first sketch of this design re-used the bump metadata in
`standards-manifest.json` (released dates) as the clock — rejected because those dates
are hand-maintained prose-grade fields (the measurement showed them honest so far, but
nothing pins them), while git committer timestamps are the actual landing record the
window is about. The git-history form is the one that cannot drift from reality.

## 9. Corrections (fold wave, post-review — appended, §1-8 above left as written)

Both pre-merge reviews (standards-governor: FIX FIRST; code-reviewer: NEEDS WORK)
found the GREEN collector structurally dead and more behind it. Folded on-branch:

- **C1 (their CRITICAL/HIGH, both reviews):** `--name-only` emits FILE paths, never
  bare directories — the anchored `$` regex matched 0 of 192 real path lines and the
  collector returned `()` on all real input; the suite was vacuously green. Fixed:
  prefix-match file paths. §2's "collector" description above was written against
  directories; the mechanism as shipped matches files.
- **C2 (HIGH, both):** `git log` walks newest-first, so the admission pass exempted
  each standard's NEWEST addition. Fixed: chronological processing; admission is the
  standard's first version over ALL history (exempt flag included — a version that
  arrived in a reset-class commit is still the standard's first, so the bump after a
  reset is judged, not silently admitted).
- **C3 (MEDIUM, code-reviewer only):** no (standard, version) dedup — the real corpus
  straddles otdp 0.1.2 across two commits 26 seconds apart, a false 0.01h violation
  once C1 unmasked. Fixed: one entry per (standard, version) at its earliest commit.
- **C4 (MEDIUM):** the shallow-clone guard as designed fires on the wrong signal (and
  a shallow boundary lists every standards file as Added at one timestamp → fabricated
  gap-0 verdicts, not the distinct refusal). Fixed: raise when the anchor is
  unreachable while the module exists on disk; §7 risk 3's claim is thereby honest.
- **C5 (MEDIUM):** the promised exemption arms were not shipped; the grandfather arm
  encoded its own vacuity (`or entries == ()`). Fixed: a scratch-repository family
  (git init in tmp_path, committer dates pinned via env) drives the REAL collector —
  non-empty collection asserted, refusal, admission, reset-opens-fresh-windows,
  straddle-counts-once. The real-tree row now states it pins deployment state, with
  the scratch family carrying non-vacuity.
- **C6 (both):** strict-mypy errors (dict mistyped tuple). Fixed; scoped strict
  `mypy src/benchweave/standards/train_window.py` clean.
- **C7:** §1 and the test comment's "4.8-hour otdp pair" was author-date arithmetic;
  the committer timestamps (what the window measures) read 09:15:27 → 12:10:40
  +08 = **2.92h** (`709de25a`/`30a775b7`). Direction unchanged, number corrected
  here and in the test comment.
- **C8:** §6's "all 4 tests" — 5 shipped then, 8 after the fold. Count drift noted;
  the acceptance rule's substance (RED watched, GREEN full) held.
- **C9:** the governor's device-plugins fetch-depth concern resolved factually: that
  job's pytest runs inside the isolated `plugins/fnirsi/dps150` copy
  (`device-plugins.yml:21,33`), never the gateway suite — gates remains the only
  lane needing `fetch-depth: 0`.
- **C10:** reset-class exemption reworded in GOVERNANCE as a shape heuristic with its
  accepted residual (the governor's F4) — a coordinated 3-standard increment of that
  shape also escapes; disclosed in the ratified text.

