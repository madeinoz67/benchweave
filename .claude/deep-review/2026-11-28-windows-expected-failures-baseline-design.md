# Windows evidence lane: expected-failures baseline (issue #457)

**Status:** Designed 2026-11-28 · **Tracking issue:** madeinoz67/benchweave#457 (this
increment implements its Recommendation) · **Census home:** #207 (the residual known
failures stay ledgered there) · **Lane lineage:** PR #343 (the evidence lane), #471
(the core-subset scoping that split `windows` from `windows-full`)

## 1. Problem

The Windows evidence lanes (`windows` per-PR core subset, `windows-full` weekly
complement) collect failures as data and pass regardless of what fails (PR #343's
deliberate posture: `continue-on-error` on the pytest step only). That posture cannot
separate #457's three classes: known platform truths (data), fixture errors (bugs to
fix), and NEW breakage (indistinguishable from class 1 — the hole: a future Windows
regression concludes success exactly like a known truth).

## 2. Mechanism

1. **Manifest** — `tests/windows_expected_failures.json`, schema
   `benchweave.windows-expected-failures/1`: one row per currently-known
   Windows-failing test id (pytest nodeid form, forward slashes), each carrying
   `kind` (`strict` | `non-strict`) and a one-line `reason`. A header `census`
   field names the CI runs whose junit artifacts evidenced the rows. Diff-reviewable
   JSON beside `tests/win_core_manifest.json` (the ratchet-manifest precedent).
2. **Comparison** — `scripts/ci/windows_expected_failures.py`, run in BOTH lanes
   over the lane's own junit artifact, as a step with NO `continue-on-error`
   (the pytest step keeps its evidence-only forgiveness; the comparison does not):
   - exit 0 — the run matches the manifest;
   - exit 1 — drift: a failing id NOT in the manifest (new Windows breakage), OR
     a `strict` row whose id RAN in this lane's junit and did not fail (healing is
     visible; the row must be removed or updated in the same change);
   - exit 2 — fail-closed: junit unreadable/absent, zero testcases collected,
     duplicate ids, manifest absent/malformed/foreign schema, bad row shape.
3. **The three evidence surfaces of PR #343 are unchanged** — the `::warning::`
   annotation, the junit-parsed job summary, the junitxml artifact. The comparison
   is a fourth, gating consumer of the same artifact, not a replacement surface.

## 2b. Id canonicalization (found by replaying the real artifact)

The manifest keys on the pytest nodeid reconstructed from the junit
attributes (`file` backslashed, `classname` dotted, `name` param-carrying).
For `.py` files the classname prefix is the module-dotted path; for the
ui-contract **markdown** items the classname carries the PATH-dotted form,
extension included (`docs.internal.ui-contract.md.row.e-2-6-...`), so the
prefix strip must keep the row chain — the first implementation collapsed
two distinct `::measured` rows onto one id, and the real full-lane artifact
(2026-11-23) refused it fail-closed as a duplicate rather than silently
mis-reading. That refusal is the canonicalization rule's regression test
(`test_markdown_collected_rows_keep_their_row_chain`).

## 3. Lane-scoping semantics (the necessary refinement of #457's letter)

#457's Recommendation predates #471's lane split: it assumes one lane running one
selection. With the core subset per-PR and the full selection weekly, one manifest
serves two selections, so "a manifest entry passes → fail" is only decidable over
the ids a lane actually ran:

- A `strict` row reds ONLY if its id appears in that lane's junit as a collected,
  non-skipped testcase AND did not fail. An id the lane's selection does not
  collect (the 17 full-lane-only rows, from the `windows` job's view) is inert for
  that lane — not "healed".
- A **skipped** testcase is inert for both directions: skip ≠ fail and skip ≠ pass.
  This also keeps fork PRs green where the fixture-signing secrets are absent and
  the `@requires_signing_keys` rows (e.g. `test_builder_is_deterministic`) skip
  instead of fail. Residual: a row that goes failing→skipped does not red; the
  win-core ratchet (`tests/win_core_manifest.json`) and the census discipline
  (record on #207) carry selection changes, not this gate.

## 4. Row kinds

- `strict` (default): deterministic platform truths and fixture-error rows — 57 of
  62 at landing.
- `non-strict`: the kill-family intermittents — `sqlite3.OperationalError: disk
  I/O error` under child-kill fault injection (5 rows: `test_disposition_faults`
  ×3, BOTH observed `test_state_recovery` members — `test_kill_after_commit_
  state_survives` and `test_kill_before_commit_loses_nothing_partial`; the
  family's failing id drifts between runs, so both census-evidenced members
  are manifested). Failing or
  passing is data either way, per PR #343's "intermittents are pure data until 50
  executions" doctrine. **This is a deliberate, disclosed deviation from the letter
  of #457's xfail-strict shape, for exactly these rows.** Drift evidence: the
  family's ids move between runs (Oct census carried `test_kill_before_commit_
  loses_nothing_partial`; the Nov 25 wincore census carried
  `test_kill_after_commit_state_survives`, which PASSED in the Nov 23 full-lane
  run two days earlier — the intermittence is directly observed, not assumed).
  The disposition trio has failed all three observed runs (Oct 2, Nov 23, Nov 25)
  and is the first candidate for strict reclassification once ~50 executions exist.
- Row calls disclosed for maintainer review (implemented strict, defensible either
  way): `test_pickup_gate_stops_dequeue_and_lets_the_active_job_finish` (WinError
  32 teardown hold on `state.sqlite`; failed both Nov runs — 2/2 observed; no
  earlier observation exists, the test landed 2026-10-08, after the Oct 2
  census — if it flaps it joins the non-strict family) and
  `test_f5_measurement_seams_tick_times_and_saturated_polls` (timing-shaped
  "saturated window" empty; failed both observed full-lane runs).

## 5. Census provenance (the artifacts are the authority)

- `windows` job, run **45557882139** (ci.yml main push 2026-11-25, head 68710455),
  artifact `windows-evidence-junit`: 215 tests, **44 failing ids** — the wincore
  census. Newest main-push run at build time.
- `windows-full` job, run **45100708153** (scheduled 2026-11-23), artifact
  `windows-evidence-full-junit`: 4,786 tests, **60 failing ids**.
- Union: **61 rows**, plus the Oct-evidenced kill-family member
  `test_kill_before_commit_loses_nothing_partial` manifested non-strict
  (**62 rows** total: 57 strict, 5 non-strict) — the family's failing id
  drifts between runs (Oct carried kill_before_commit, Nov 25 carried
  kill_after_commit), so manifesting only the latest member would red the
  lane as "unlisted" whenever the drift recurs; the census header names
  the drift run (36967753302) as that row's evidence — 43 fail-in-both-lanes,
  1 core-lane-only failure
  (`test_kill_after_commit_state_survives`, collected by both lanes: it failed
  Nov 25 and passed Nov 23 — the intermittence evidence), 17 full-lane-only
  failures (the `windows` job's inert count for these is 17, matching the
  gate's own printed line).
- Drift reference, run **36967753302** (2026-10-02, the AR-2 plant branch): 37
  failing ids including `test_ar2_plant_canary` — that id is NOT manifested (it is
  a deliberate plant, never a platform truth). No id of the four #329
  deterministic families (fw5, fold2-wedge, fold1-fsync, fold2-durability)
  appears in either Nov census's failing set; they stay unmanifested (#207
  AC-2 expects them passing — collected where each lane's selection runs
  them).
- Every row's reason is grounded in that run's junit failure text (read from the
  artifact, not from summaries).

## 6. Maintenance flow

- **New failure appears** (comparison exit 1, "unlisted failing id"): fix the
  breakage, or add a reviewed row (id + kind + one-line reason citing the census
  run) in the same change — the red is the forcing function.
- **Row heals** (exit 1, "strict row not failing"): remove or update the row in
  the same change. Non-strict rows healing is data (no red); prune them at census
  time.
- **Census discipline unchanged**: failing ids are still recorded on #207; the
  manifest is the machine-checked distillation of that census, not its replacement.
- Prose defers to machine sources: this design record, `development.md` and the
  CI-map rows describe the mechanism; the manifest JSON and the script are the
  authority.

## 7. Acceptance (pre-committed)

- **Unit canary**: tests for the comparison logic itself
  (`tests/unit/test_windows_expected_failures.py`) — RED on an unlisted failure,
  RED on a healed strict row, GREEN on a matching run, non-strict rows never red
  either way, strict-not-collected inert, skipped inert, fail-closed exits. Each
  shown failing before the implementation exists ( withheld-implementation RED
  evidence recorded in the PR body).
- **Artifact replay** (POSIX-side proof over the real Windows artifacts): the
  Nov 25 wincore junit and the Nov 23 full junit both compare clean (exit 0);
  the Oct 2 plant-branch junit reds (exit 1) naming `test_ar2_plant_canary`.
- **Wire canary** (AR-2 plant precedent, PR #341): one commit on the PR branch
  carrying a deliberate unlisted failing test (win32-gated, wincore-marked, with
  the win-core manifest counts refreshed in the same commit so `gates` stays
  green); the PR's own `windows` job must RED at the comparison step while the
  pytest step stays forgiven; run ID cited in the PR body; plant reverted before
  the final head. Never merged.
- **No gate weakened**: no new `continue-on-error`, no test skipped or deleted to
  fit the manifest, no Action added (the step uses the runner's checked-out tree
  and `uv` already installed by the lane), `permissions:` untouched (least
  privilege already declared per job).

## 7b. Same-commit ratchets the expected diff touches

Adding `scripts/ci/windows_expected_failures.py` and
`tests/unit/test_windows_expected_failures.py` moves two more ratchets,
each updated in the SAME commit per its own discipline: the win-core
manifest counts (`tests/win_core_manifest.json` — the new test file's
(total 18, core 0) row via `--refresh`) and the zero-literal scripts
census (`test_zero_literal_gate.py`'s `scanned` pins, 20 → 21: the new
script joins the scan carrying zero version literals — its manifest ids
are data in `tests/`, not literals in `scripts/`).

## 7c. Invariant impacts

- **A06 evidence over assertion:** unchanged in direction, tightened in
  degree — an ambiguous Windows outcome was previously invisible (any red
  read as data); now only LISTED reds are data and everything else is a
  refusal. The junit artifact remains the single evidence substrate.
- **A07 audit failure constrains new work:** extended to the Windows
  surface — the comparison's fail-closed exit 2 blocks the lane exactly
  when its evidence cannot be read.
- **Claim discipline (G4):** every manifest row names its class and
  cause; the gate's own printed counts (inert rows, strict/non-strict
  split) are the machine source the prose defers to.
- No control-path, state, registry or standards-corpus surface is touched;
  CON/CTL/REG invariants are unaffected by construction.

## 7d. Top risks, each with its falsifier

1. **A hand-typo'd row id silently never reds on healing** (permanently
   inert strict row). Falsifier: the manifest generator refuses any id
   absent from the census artifacts' failing sets — every committed row
   traces to a real artifact id; re-derive with the replay (exit 0 on both
   Nov artifacts exercises all 62 rows).
2. **A canonicalization drift mis-reads future artifacts** (wrong id =
   false green or false red). Falsifier: the fail-closed duplicate-id arm
   plus the canonicalization unit tests; the real-artifact replay over
   both lanes stays green only while ids derive exactly.
3. **The gate becomes merge noise** (a flapping strict row reds every
   PR). Falsifier: the non-strict kind exists for exactly this; a strict
   row that flaps reds, the row moves to non-strict in the same change,
   and the census note records why.
4. **The lane's strictness is silently removed later** (a future edit adds
   continue-on-error or deletes the step). Falsifier: the step-scoped
   contract pins with doctored arms (test_comparison_step_pin_*).

## 8. Deferrals (each rides #207, the standing census home — no orphan deferrals)

Each row: identifier · deferred · home · reopen trigger.

1. **CRLF-fixture-repins** · the `dev_pin_drift` digest family (5 rows) and
   `test_builder_is_deterministic` · #207 (the #237 repin-LF line) · any
   increment touching those fixtures' write paths.
2. **Promotion-sweep-separators** · the 13-row `promotion_sweep_violation`
   family (possible product bug, same family as #237/#238) · #207 · a
   sweep-comparison change or a census run showing the family healed.
3. **Gitmodules-fixture-CRLF** · the 6-row `fatal: bad config line` family ·
   #207 · any increment touching `tests/unit/test_check_sdk_submodule_drift.py`
   fixtures.
4. **Teardown-chmod-before-delete** · the WinError 5 family (both
   `test_d1_wheel_posture_*` rows, `test_m2_the_dev_refusal_propagates_
   verbatim`) — #457's own named class-2 fix, separable, NOT widened into
   here · #207 · any increment touching those teardowns.
5. **Kill-family-classification** · strict/non-strict reclassification of
   the disposition trio · #207 · ~50 cumulative lane executions exist.
6. **Windows-full-wire-proof** · the weekly comparison's first real
   scheduled run · #207 (verification note) · the first post-merge Monday
   02:23 run.
7. **Comparison-coverage-anchor** · assert the lane artifact's collected
   count equals the ratchet-pinned selection count (refute F4) · #207 ·
   any follow-up touching the comparison script.
8. **Renamed-row-pruning** · a strict row whose test renames is inert
   forever (review finding 9) · #207 · a gates-time collect-only row
   existence check, if wanted.

## 8b. Adversarial pass (Tier-3 G6) — findings folded

The REFUTE pass (2026-11-28, pre-PR) confirmed the mechanism on every real
and constructed artifact (all 61 Nov-union rows re-derived exactly; canonicalization
faithful across class chains, params, hostile ids, the markdown rows;
fail-closed family holds incl. a billion-laughs DTD; CI wiring and fork-PR
posture verified) and returned four findings, all folded:

- **F1** census arithmetic — "16 full-lane-only" was wrong; 17 (43/1/17
  taxonomy above). Fixed here and in the PR body.
- **F2** false provenance — `test_pickup_gate` never "passed Oct": the
  test landed 2026-10-08, after the Oct 2 census; observed record is 2/2
  failing. Manifest reason and this record corrected. The #329 sentence
  restated as families over actual failing-set membership.
- **F3** duplicate JSON keys read valid (json last-wins could shadow a
  strict row with a non-strict twin) — the loader now rejects repeated
  keys fail-closed, pinned by test.
- **F4** (disclosed, not fixed — a named follow-up under #207): a
  well-formed junit from an aborted session that contains only listed
  failures reads green; the gate cannot tell "not in this selection" from
  "never got there". The fine-grained anchor (artifact count == the
  win-core ratchet's pinned selection count) is follow-up scope; the
  zero-testcase fail-closed catches the coarser collapse.

The resident code-reviewer pass (Tier 3, pre-PR, same day) returned
NEEDS WORK with the mechanism verified end-to-end; its findings are folded
in the review-fold commit: the duplicate-key test rebuilt as valid JSON
with a genuine repeated key (RED-proven against the pre-hook script: the
row-shadow document loads clean there), non-UTF-8 manifests fail closed
(exit 2, not a drift traceback), skip-first duplicates detected, the two
comparison steps pinned step-scoped with doctored arms (key-line regex, so
comments may discuss the concept), the new script joined the strict-mypy
build, census arithmetic and keyword counts restated regenerably, and the
record gained the invariant-impacts and top-risks sections plus deferral
triggers.

## 9. Review tier (design-time call, #254)

Tier 3 — path rules: `.github/workflows/`, `tests/`, `scripts/` (Tier 2 triggers);
keyword rule (first-match-wins, text-based): the expected diff text carries
`recovery` (the `tests/faults/test_state_recovery.py` and
`tests/faults/test_recovery_sweep_faults.py` row ids — unavoidable, the ids are
the manifest keys) and `subprocess` (the zero-literal-gate rows' reasons and the
test file's black-box arms). Step-1 scan, re-derivable at any commit pair with
`git diff <base>..HEAD | grep -o -E "threading|asyncio|subprocess|sha256|hashlib|migrate|recovery|protection" | sort | uniq -c`;
over 4e375e3f..HEAD at the review fold: `recovery` ×10, `subprocess` ×7,
`threading` ×1, `asyncio` ×1, `sha256` ×1, `hashlib` ×1, `migrate` ×2,
`protection` ×1 — the singles and the migrate pair are this §9's own quoting of
the keyword list (the rubric's self-fire clause, intended). The Tier-3 second
adversarial pass (G6) ran pre-PR: the refute lane (adversary agent, REFUTE
mode) returned the mechanism defended with four findings, folded in §8b and
the review fold commit.

## 10. Owner ruling addendum (2026-11-28, PR #655 fix attempt 1 of 2)

The owner ruled the wheel-posture teardown fix INTO this increment,
superseding §8's deferral row 4 (teardown-chmod-before-delete). The
chmod-before-delete verb is `_drop_git_store` in
`tests/standards/test_dev_pins.py`: it chmods every file under the
planted `.git` store writable before `shutil.rmtree` — a POSIX no-op, the
WinError 5 cure on win32. One helper covers all three teardowns: both
`test_d1_wheel_posture_*` tests and `test_why.py`'s
`test_m2_the_dev_refusal_propagates_verbatim` (which already imports its
`_git_root` from the same module). The three rows left the manifest in
the SAME change (62 → 59 rows; 57 → 54 strict, non-strict unchanged) —
the strict shape's healing rule applied to this PR's own rows. §5's census
arithmetic and the earlier row-call text stand as the historical record
of the pre-ruling shape; §8 row 4 is discharged by this addendum (rows
1–3, 5–8 stand). The fix's Windows proof is the PR's own `windows` run
(contributor-attested POSIX-side only, doctrine W1: no Windows execution
on this machine).
