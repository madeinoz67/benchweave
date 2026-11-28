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
  collect (the 16 full-lane-only rows, from the `windows` job's view) is inert for
  that lane — not "healed".
- A **skipped** testcase is inert for both directions: skip ≠ fail and skip ≠ pass.
  This also keeps fork PRs green where the fixture-signing secrets are absent and
  the `@requires_signing_keys` rows (e.g. `test_builder_is_deterministic`) skip
  instead of fail. Residual: a row that goes failing→skipped does not red; the
  win-core ratchet (`tests/win_core_manifest.json`) and the census discipline
  (record on #207) carry selection changes, not this gate.

## 4. Row kinds

- `strict` (default): deterministic platform truths and fixture-error rows — 57 of
  61 at landing.
- `non-strict`: the kill-family intermittents — `sqlite3.OperationalError: disk
  I/O error` under child-kill fault injection (4 rows: `test_disposition_faults`
  ×3, `test_state_recovery::test_kill_after_commit_state_survives`). Failing or
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
  32 teardown hold on `state.sqlite`; failed both Nov runs, passed Oct — if it
  flaps it joins the non-strict family) and
  `test_f5_measurement_seams_tick_times_and_saturated_polls` (timing-shaped
  "saturated window" empty; failed both observed full-lane runs).

## 5. Census provenance (the artifacts are the authority)

- `windows` job, run **45557882139** (ci.yml main push 2026-11-25, head 68710455),
  artifact `windows-evidence-junit`: 215 tests, **44 failing ids** — the wincore
  census. Newest main-push run at build time.
- `windows-full` job, run **45100708153** (scheduled 2026-11-23), artifact
  `windows-evidence-full-junit`: 4,786 tests, **60 failing ids**.
- Union: **61 rows** (43 common; `test_kill_after_commit_state_survives` wincore-only).
- Drift reference, run **36967753302** (2026-10-02, the AR-2 plant branch): 37
  failing ids including `test_ar2_plant_canary` — that id is NOT manifested (it is
  a deliberate plant, never a platform truth). The four #329 deterministic ids
  (fw5, fold2-wedge, fold1-fsync, fold2-durability) passed both Nov runs and stay
  unmanifested (#207 AC-2 expects them to keep passing).
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

## 8. Deferrals (each rides #207, the standing census home — no orphan deferrals)

1. CRLF fixture repins (the `dev_pin_drift` digest family; `test_builder_is_
   deterministic`) — the #237 "repin LF fixtures" line.
2. Promotion-sweep separator handling (the 13-row `promotion_sweep_violation`
   family) — possible product bug, same family as #237/#238.
3. `.gitmodules` fixture CRLF (the 6-row `fatal: bad config line` family).
4. Teardown chmod-before-delete for read-only `.git` objects (the WinError 5
   family: `test_d1_wheel_posture_*`, `test_m2_the_dev_refusal_propagates_
   verbatim`) — #457's own named class-2 fix, separable, NOT widened into here.
5. Kill-family strict/non-strict reclassification once ~50 executions exist.
6. The `windows-full` weekly comparison is wire-proven only by its first
   post-merge scheduled run (it cannot fire at PR time; the step is identical
   code over a sibling artifact).

## 9. Review tier (design-time call, #254)

Tier 3 — path rules: `.github/workflows/`, `tests/`, `scripts/` (Tier 2 triggers);
keyword rule (first-match-wins, text-based): the expected diff text carries
`recovery` (the `tests/faults/test_state_recovery.py` and
`tests/faults/test_recovery_sweep_faults.py` row ids — unavoidable, the ids are
the manifest keys) and `subprocess` (the zero-literal-gate rows' reasons and the
test file's black-box arms). Step-1 scan over the whole expected diff at commit
time, this record included: `recovery` ×9, `subprocess` ×9, `threading` ×1,
`asyncio` ×1, `sha256` ×1, `hashlib` ×1, `migrate` ×2, `protection` ×1 — the
singles and the migrate pair are this §9's own quoting of the keyword list (the
rubric's self-fire clause, intended). The Tier-3 second adversarial pass (G6) is
dispatched before the PR opens.
