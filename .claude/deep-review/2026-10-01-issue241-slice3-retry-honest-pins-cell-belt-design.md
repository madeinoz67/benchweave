# Issue #241 slice 3 — load-honest retry pins and the one-shot cell belt

Design record for the third stabilization increment of the #240 red-lane class.
Tree: `origin/main` at `f3c023d` (worktree `.wt/f241-design-322`). Branch:
`feat/issue241-timing-stabilization`; this record is commit 1. Standards
tripwire: this design moves no `standards/` bytes and no version strings
(`git diff origin/main...HEAD -- standards/` expected empty, checked at push).

**Pre-commitment protocol (same disclosure as slice 2).** The lane counter and
failure logs below were collected BEFORE this record was written, but the
post-merge acceptance rule (§5) was fixed before any post-merge number can
exist by construction. The in-window numbers (§6) are inputs, not tuned-to
outputs: no mechanism below was sized from a number it also promises to
deliver — the belt is bounded at ONE re-run by design analogy to the
three-attempt trial budget, not by fitting the observed red rate.

## 0. State established from the runner, not assumed

### 0.1 The slice-1 kill arm has FIRED — this slice is the response that rule made mandatory

Slice 1 pre-committed: at most 1 marked-set red in the first 20 timing-lane
executions keeps the isolation claim; **2 or more kills the "green lane by
isolation" claim and makes evidence-backed stabilization mandatory**. Slice 2
found `N_A = 12, R_A = 0` (UNDERPOWERED) and posted its outcome comment at
2026-09-28T08:15Z. **The first post-slice-2 red run had already happened at
08:08Z** — seven minutes before that comment posted. The counter, re-run for
this design (§6, Evidence A), now reads:

- **≈ 74 timing-lane executions** since the slice-2 evidence cut
  (2026-09-28T01:48Z) through 2026-10-01T11:00Z (every `ci` workflow run
  executes the `timing` job; 4 non-timing-lane failures excluded by job-level
  inspection).
- **7 red executions, 16 red test-events** (all on merges/diffs that never
  touched a timing path: a standards train merge, an i1-skeleton merge, a
  website-status merge, a spec-09 review-fold PR).
- Red-execution rate ≈ 9.5% (7/74). The kill arm fired at the very first red
  execution (3 red events in run 36395616332 alone).

No numeric bound moves in this slice either. What the census adds beyond
slices 1–2 is a NEW fragility class neither prior record inventoried (§0.3),
plus the decisive firing of the D2-trim reopen trigger (§0.2).

### 0.2 D2-trim's reopen trigger fired: the range gate reds are MULTI-stall shapes

Slice 2's D2-trim trigger: "trim depth / trial count revisited ONLY on ≥2
in-lane range-gate reds with log lines naming the cell and values (the
double-stall shape the one-trial trim cannot tolerate)". The lane has since
produced **five** range-gate reds on five different (cell, axis) combinations,
every one a 2–3-stall shape among tight trials (§6 Evidence B for all five
value sets, e.g. `[51.8, 267.8, 374.2, 51.5, 51.5]` — trim removes 375.0's
sibling, 267.8 remains against 51.5). The one-trial trim is working as
pinned; the shapes it cannot absorb are host stalls, not fixture looseness —
but §2 of the #217 tolerance pin forbids deepening the trim ("a double-spiked
shape must still fire"), and slice 2's rule holds the denominator
non-negotiable. So the absorption must happen at a level that does not touch
the READING. §1.2 is that mechanism.

### 0.3 A class the sweep never inventoried: exact-count retry pins are load-fragile by construction

Three of the 16 red events are tests asserting the retry machinery's
bookkeeping exactly — and host load legitimately moves that bookkeeping:

1. `test_drain_cap_starvation_retries_on_a_fresh_rig`
   (`test_cross_instance_continuity.py:2884`, asserts `retries == 1` and
   `retry_sites == ["drain-cap"]` at :2906) — slice 2's own integration pin,
   red **three times** (runs 36452983841, 36817483120, 36852240046), each
   `AssertionError: 2`. Mechanism: the pin starves construction #1 (attempt 0
   dies at `drain-cap`, deterministic); under load the UNPATCHED attempt 1 can
   hit a real starvation site (pre-flight staleness, a real drain-cap,
   priming) — the retry budget legitimately absorbs it, the trial completes
   on attempt 2, and `retries` is 2 with a longer `retry_sites`. **The
   property the pin guards (a drain-cap starvation is classified and retried,
   and the unpatched retry completes the trial) held in all three reds.** The
   exact-count assertion is what failed.
2. `test_measured_dispatch_device_refusal_with_latched_staleness_never_retries`
   (:3249, asserts `len(rigs) == 1` at :3272) — red twice (36395616332 with 3
   rigs, 36818395071 with 2). Mechanism: the injected device refusal is NOT
   rig-keyed (every rig's `op-acq` refuses), so the refusal fired on whichever
   rig reached it and raised its plain `AssertionError` — the no-retry
   property held. What failed is `len(rigs) == 1`: an EARLIER infrastructure
   site (pre-flight staleness / drain-cap) consumed attempt 0 first.
3. `test_transient_device_write_refusal_cannot_launder_into_clean_verdict`
   (:3219) — red once (36817483120, `DID NOT RAISE`). Mechanism: this
   injection IS rig-keyed (`if request["verb"] == "write" and len(rigs) == 1`,
   :3235). An infrastructure retry moved the write leg to rig 2, where the
   injection no longer fires; rig 2 measured clean and returned a clean
   verdict. The no-laundering property was never in danger (no refusal
   occurred to launder), but the test cannot see that — the rig-keying makes
   an infra retry and a real laundering regression present IDENTICALLY
   (`DID NOT RAISE`), which is the pin losing its discriminating power to
   load.

The unred siblings `test_priming_signal_starvation_is_infrastructure_and_
retries` (:2627, asserts `retries == 1`, `retry_sites == ["priming-validity"]`)
and `test_priming_read1_starvation_routes_the_block_refusal_to_retry` (:2669,
`retries == 1`) carry the same shape and are fixed pre-emptively in the same
commit (one line each, same mechanism, disclosed).

### 0.4 What did NOT fire

- **D4** (virtual-clock migration of the sequential-model family): its letter
  asks for "a second in-lane red of the sequential-model 200 ms family
  (`BUDGET_MS + TOLERANCE_MS = 200` ms bounds)". Post-slice-2 reds in that
  file: monitor-gap 206.4 vs 200 (the 200-family, red #1), queued-run 484.9
  and 371.8 vs 350 (the `BUDGET_MS + 300` band — same file, same mechanism,
  different band). **By the letter: 1 of 2. By the mechanism: 3 reds.** Both
  readings recorded; this slice defers the migration either way (§2 deferral
  D4', with the trigger tightened to any second red of ANY sequential-model
  band) and carries a fully specified payload.
- **D6 row 16** (row-B `busy_wait` overshoot): the brief reports a 1732.5 vs
  ≤1700 red ("the #288 run"); that run is NOT locatable in the reachable ci
  history (§6 Evidence D — every timing-job failure in the window was pulled;
  none is it; PR #288 does not resolve on this tracker). The sweep recorded
  row 16 as never-CI-failed, so even taken at face value this would be the
  test id's FIRST flake — keep-and-document stands, recurrence trigger armed.
  The exposure is real regardless: quiet max 1669.3 leaves 30.7 ms of upper
  headroom (slice 2 Evidence C.4, n=12), and the band's fail direction
  (busy-wait unbounded past entry-remaining) is pinned by `fail_delta_ms ≤
  1500 + pre_begin_ms + 300` — a band ALREADY relativized to an in-run
  measured quantity, which is the precedent a future fix would extend.
- **Slice-2 risk-6** (lane wall ≥ 2x baseline with drain-cap retries
  visible): the three drain-cap PIN reds are assertion failures, not lane
  wall growth; not fired.
- **D5** (marker-rot guard): every red test id carries the `timing` marker;
  not fired.

## 1. Mechanism — two mechanisms, one doctrine

The doctrine is the one F4 established on PR #236 and slices 1–2 extended:
**transient host starvation retries on a fresh unit with the retry recorded;
chronic starvation exhausts and still reds; nothing about the measurement
semantics moves.** Slice 3 applies it at the two levels it is missing:

### 1.1 Load-honest retry pins (de-clocking, class (a))

The pins stop asserting WHICH attempt the property held on, and assert the
property:

- **Composition/membership instead of exact counts.**
  `test_drain_cap_starvation_retries_on_a_fresh_rig` asserts
  `outcome["retries"] >= 1` and `"drain-cap" in outcome["retry_sites"]`
  (the machinery's `retries <= 2` cap is pinned where it always was, on the
  axis trials). The membership form is airtight under load-additional retries:
  attempt 0 deterministically dies at `drain-cap` (the patch starves
  construction #1's delivery; the first drain call precedes settle and the
  measured dispatch), so `"drain-cap"` is in the sites unless attempt 0's
  construction itself starved at priming first — a residual named in §7 risk 2.
  Same shape for the two priming pins (`retries >= 1` +
  `"priming-validity" in retry_sites`; the block-refusal pin checks
  `"priming-block-refusal" in retry_sites`).
- **Type pins instead of rig counts; any-rig injections instead of
  first-rig-only.** The two F1 lanes keep their `pytest.raises(AssertionError)`
  and gain `type(raised.value) is AssertionError` as the load-invariant
  carrier of "the device refusal itself was never classified" —
  `TrialInfrastructureError` SUBCLASSES `AssertionError`, so `type() is`
  discriminates the laundering regression (a classified refusal retries,
  exhausts, and re-raises as `TrialInfrastructureError` — the type pin reds)
  while remaining indifferent to how many infrastructure retries preceded the
  refusal. The write-refusal injection drops its `len(rigs) == 1` key and
  refuses the write leg on EVERY rig — the first rig to reach the write leg
  refuses and raises; an infrastructure retry can no longer dodge the
  injection (which also removes the red's ambiguity with real laundering,
  §0.3.3). The `len(rigs) == N` asserts are deleted, not re-banded.

Nothing in `run_trial`, the classifier, or any production seam moves. The
classifier-table pins (:3006–:3132) already carry the no-retry property at the
unit level; these end-to-end pins keep their RED direction via the classifier
monkeypatch arm (§5 AR-2).

### 1.2 The one-shot cell belt (class (b): the band stays, the variance is absorbed honestly)

The instrument's §5 acceptance rule (the #172 record §5, cl. 7 — cited by the
range gate's own assert message) reads a cell's trial range against 25% of
the dispatch duration, trimmed of one trial, and an over-bound reading is
UNDERPOWERED: "fix fixture pacing, decide nothing". The frozen #159 §6 rule's
own arm 4 for underpowered series is **"raise n and re-run"**. The belt
mechanizes exactly that prescription, bounded and recorded:

- The reading (`_underpowered_range_ms`, the 25% clause, the denominator,
  the one-trial trim) is untouched, byte-identical.
- `test_instrument_range_gate_per_axis_per_cell` and the two observed-red
  per-trial UPPER bands of `test_axis_trials_complete_all_four_axes`
  (`dispatch_duration_ms <= dispatch_ms + 150`, `x1_ms <= dispatch_ms + 150`)
  move their breach evaluation behind a helper,
  `_certified_cell(tmp_path, arm, device_class, evaluate)`:
  1. evaluate the shared cached cell (the existing `_cell` gen-1);
  2. if the breach list is non-empty, run ONE fresh generation (five fresh
     `run_trial` invocations, `trial_index` 51–55 — a range no other caller
     uses: the module's direct `trial_index=` callers, grep-verified at build,
     are 1, 3, 6, 7, 8, 9, 11, 44, 45, 46, 99. Refute-fold correction C1:
     the original enumeration here — "cells use 10–14/…, pins 70–92/110–112,
     census 99, F1 lanes 440/450" — did not regenerate from the file; this
     set does);
  3. evaluate the fresh cell; if it also breaches, FAIL, rendering BOTH
     generations' values and both breach lists (the §6-arm-1 kill direction —
     a systematically-loose fixture is caught twice);
  4. the belt's generation count is recorded per key and asserted `<= 1`,
     and printed in the trial line (the same lane-health posture as
     `outcome["retry_sites"]`). Refute-fold clarification (mech-F5): the
     `<= 1` counts CERTIFICATIONS — a key entering the memo — not evaluator
     executions; a later belt reader re-evaluates the certified generation
     without any second generation run.
- Belt discipline, structural not policy-checked:
  - **ONE re-run per (arm, class) key, shared by every belt reader** (a
    module-level memo beside `_TRIAL_CELLS`). Whichever reader breaches first
    certifies the generation; later readers evaluate the certified
    generation. Reader verdicts are therefore order-independent: every reader
    evaluates the newest certified cell at its own runtime.
  - **Only the two named band families re-run.** The belt takes an explicit
    `evaluate` function returning a breach list — it never sniffs exception
    types. Structural asserts (axes recorded, `in_window_frames >= 1`,
    `retries <= 2`, snapshot brackets) and every FLOOR stay inline and hard:
    host load inflates, it does not deflate, so lower bounds and structural
    wiring are not the flake class and must not gain a re-roll.
    Refute-fold disclosure (adv-F1/mech-F3): the inline asserts evaluate
    whichever generation the belt RETURNS — an absorbed gen-1 band breach
    therefore skips gen-1's floor/structural verdicts — EXCEPT the
    load-safe X1 floor, which the axis test asserts on BOTH generations
    (load inflates X1, so its lower bound cannot false-red);
    `retries <= 2`, `in_window_frames >= 1`, and the write-leg gap band
    stay return-generation-only: re-asserting gen-1's load-inflated upper
    quantities would reintroduce the flake class this slice retires, and
    `in_window_frames` is load-deflatable.
  - **The raw cell cache is never rewritten.** The trial-log test and the
    control/separation test keep reading gen-1 (`_cell`); the belt's fresh
    generation lives in its own memo. What was measured stays what is logged;
    the belt's generations are printed, not laundered into the log.
- Why this is not "re-roll until green": the bound is one re-run (vs the
  trial level's two retries), the second breach reds with both generations
  rendered, structural failures never re-run, and the sustained-stretch
  execution reds on BOTH generations (the 2026-09-28T22:10 shape — axis band
  268.1, range gate 216.3, queued 484.9 in one run — would still red under
  the belt, correctly: that runner could not measure, and §5's honest verdict
  for it is exactly "underpowered, decide nothing" as a red lane).
  The disclosed price: for a fixture loose enough to pass any single 5-trial
  draw with per-generation probability p, the belt raises the per-execution
  pass probability from p to `1-(1-p)^2`. With the quiet evidence (worst
  quiet trimmed spread 6.0 ms against the 50 ms bound, 8.3x margin, slice 2
  Evidence C.4, 384 readings) a detectably-loose fixture sits far from
  marginal; the power loss is immaterial for looseness that matters and the
  teeth pin (§5 AR-1) proves a systematically-loose cell still reds.

### 1.3 Considered and rejected (with reasons, so nobody re-litigates them blind)

- **Deepening the one-trial trim to two trials:** violates the
  `test_range_gate_tolerance_both_directions` still-catches pin (the
  double-spike `[78.0, 78.1, 150.9, 151.0, 77.6]` must fire). A §5 reading
  change is an owner fork; not taken. The belt absorbs the transient class
  without touching the reading.
- **pytest-level reruns (`pytest-rerunfailures`, `--reruns`, a CI retry
  step):** a blanket retry re-rolls logic reds and the workflow-parse class
  too; it is the laundering shape this repo refuses, at job granularity, with
  the retry invisible. Rejected.
- **CI-side CPU pinning / nice / lane reordering:** the lane already runs
  serialized on a fresh VM within ~2 min of boot; hosted 2-core runners offer
  no noisy-neighbor control that changes the dice. Rejected (documented).
- **Widening any numeric bound:** zero bounds move, per the standing #241
  discipline; §5 clauses are not load-renegotiable (slice 2 §5.2 D2).

## 2. Minimal increment scope

Build order (RED-first where behavior changes, one slice per commit):

1. Commit 1: this design record.
2. The belt (`_certified_cell` + the two `evaluate` breach functions) re-homing
   the range-gate spread loop and the two per-trial upper bands; the three
   belt pins (§5 AR-1). RED: the forced-loose arm reds on the pre-belt code
   AND on the belt (it is the standing behavior); the single-stall-absorption
   and no-structural-rerun arms are new-mechanism pins.
3. The pin de-clocking (five tests: drain-cap pin, two F1 lanes, two priming
   pins) + the two classifier-regression RED arms (§5 AR-2).
4. Docs sweep (G5): the drift-and-obligations testing-conventions line gains
   the belt sentence; the range-gate docstring names the belt (reading
   unchanged, re-measure named); no CI-map change (no job shape moves).
5. Issue #241 outcome comment: the census, the kill-arm statement, per-item
   verdicts, the D4-by-letter-vs-mechanism fork named for the owner.

### Deferral table

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D4' | sequential-model migration: relativize the monitor-gap ceiling (`gap <= realized-dispatch-duration + TOLERANCE_MS`, both measured in-run; the UNKNOWN status + the `>= BUDGET_MS-40` floor keep the cut's own proof — the reverted-`bounded()` arm is still caught by the status assert) and the queued-run ceiling (`delay <= measured-run-1-start-to-end + 300` — the band's own comment says the tolerance exists for run-1's init; measure it instead of guessing 300); `test_second_dispatch_lock_block` keeps its absolute band as the family's one real-clock representative (D4's own letter) | issue #241 slice 4 (payload above; ~2 tests, one file) | any second red of ANY sequential-model band in-lane (tightened from "the 200 ms family" — the queued reds are the same mechanism); or the owner calling D4 fired-by-mechanism now (3 reds stand) |
| D-rowB | row-B `busy_wait` ceiling [1300,1700]: relativize to the recorded clamp value (`busy_wait_ms <= clamp_value + 300`, the same +300 slop `fail_delta_ms` already uses — capture the clamp via a recording `busy_timeout_window` wrapper, the shape `test_row_b_sweep_and_startup_reclaim_never_enter_a_window` already uses at :2703) | issue #241 (with or after slice 4) | a CI-verified red of `test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot` (the brief-reported 1732.5 is unlocated — Evidence D — and would be the id's FIRST flake; sweep row 16 = keep-and-document) |
| D5 | marker-rot guard | unchanged (slice-1 row) | a `gates` red on an unmarked ms-bound test |
| D6/D7 | keep-and-document clusters; plugin-lane paced tests | unchanged (slice-1 rows) | each row's own recurrence |
| D3-sibling | `unbuffered_x2` quiet median | unchanged (slice-2 row) | D3 re-entering (42, 50] |
| belt-visibility | belt usage is print-visible only (pytest -q swallows per-trial prints) — same disclosed gap as `run_trial`'s green-path retries (slice-2 risk 1); the loud signals are the second-breach red and exhaustion | documentation here | a need arising from a belt-related incident |

Out of scope entirely (no trigger): the control-arm ceilings
(`control_x2 <= 50` median-of-5, `control_x3 <= 3*POLL_MS` max,
`control_x4 <= 1000`, `unbuffered_x2 < 50` — medians need ≥3 stretched
trials, not observed red; the X3 max is single-stall exposed with 46.7 ms
quiet margin, watch), `test_eight_separation` (b ≤ 100 ms, 2.5x quiet
headroom, unfailed), the write-leg gap band, the generous-deadline family
(sweep rows 18–23), and every floor everywhere (load-safe direction).

## 3. Precedent (all in-tree, extended not invented)

- **The F4 `TrialInfrastructureError` retry doctrine** (PR #236; slices 1–2
  extended it to priming ×2, pre-flight, dispatch-door, drain-poll-door,
  drain-cap): the belt is the same bounded-retry-with-recorded-composition
  lifted one level (trial → cell), with the same exhaustion-still-reds
  property. The de-clocked pins follow the doctrine's own evidence rule —
  assert the classification fact, not the attempt bookkeeping.
- **The frozen #159 §6 arm 4** ("everything else … raise n and re-run"): the
  belt's semantic license, in the corpus's own words, for underpowered
  series.
- **The #217 one-trial trim + `test_range_gate_tolerance_both_directions`**:
  the tolerance precedent the belt preserves verbatim — tolerance for host
  stalls, teeth for fixture looseness; the belt adds the same both-direction
  discipline at cell granularity (AR-1's forced-loose arm).
- **The in-run-relative band precedent**: `fail_delta_ms <= 1500 +
  pre_begin_ms + 300` (`test_otdp_bridge.py:2685`) already relativizes a
  ceiling to an in-run measured quantity — the pattern D4'/D-rowB extend.
- **The membership/type pin shapes**: `test_plain_assertion_with_legacy_
  wording_never_retries` pins `type(raised.value) is AssertionError` (:2393)
  — the exact type-pin mechanism the F1 lanes gain; `outcome["retry_sites"]`
  (critic F3, slice 2) is the membership evidence the drain-cap pin gains.

## 4. Invariant and drift impacts

- **A06 (evidence over assertion), both directions.** The belt records both
  generations on a second breach and never rewrites the raw cell cache; the
  de-clocked pins stop letting an environment artifact (a load-added retry)
  present as a property of the machinery — and stop letting the rig-keyed
  injection's `DID NOT RAISE` present a load artifact as the laundering
  hazard. Disclosed widenings: the retry-pins' assertions get weaker in
  count-discrimination and stronger in property-discrimination (§7 risk 2);
  the belt's detection-power arithmetic is disclosed (§1.2).
- **No CTL/STO/CON/REG invariant is touched.** No `src/` byte, no
  `standards/` byte, no schema, no workflow. The #172 record §5 reading is
  unchanged (the belt re-measures; it does not re-read); the frozen #159 §6
  classifier is untouched.
- **Obligations walked:** 4 (CI shape unchanged — no CI-map edit owed; the
  conventions line gains the belt sentence), 5 (no workflow change; a cold
  unfiltered union run is in acceptance anyway), 10 (no dependency change —
  the belt is pure stdlib-pattern test code, no new plugins).
- **Tier and the Step-1 keyword scan (#254).** Expected diff: this record,
  `tests/integration/test_cross_instance_continuity.py` (belt helper + two
  breach functions + re-homed assertions + five pin edits + three belt pins +
  two classifier-regression arms), `docs/internal/drift-and-obligations.md`
  (one line). Design-time scan over the expected added/removed text:
  `threading` 0, `asyncio` 0, `subprocess` 0, `sha256` 0, `hashlib` 0,
  `migrate` 0, `recovery` 0, `protection` 0 → **Tier 2** (test-code change
  under `tests/`, no Tier-3 path or keyword). Caveat, disclosed: the review
  re-derives the tier over the REAL diff — hunk context lines in the
  continuity file can carry a keyword (the file imports `threading`/
  `asyncio` and names `ProtectionEngine` in nearby code); if the actual diff
  text trips a keyword, the slice takes the Tier-3 lane and the standing
  adversarial review covers it. The builder re-runs the scan pre-PR and
  records counts.

## 5. Measurable proof and the pre-committed acceptance rules

### 5.1 Build-time (PR) acceptance

- **AR-1 (belt teeth, all three arms RED-first where applicable):**
  1. *Forced-loose arm* — a patched `ARigAdapter._pace` scattering `acq_ms`
     per trial (systematic looseness) breaches gen-1 AND gen-2; the test
     fails rendering both generations. RED on pre-belt code is the standing
     behavior (the same fixture reds today's gate); on the belt it must STILL
     red — this arm is the kill direction for "re-roll until green".
  2. *Single-stall absorption arm* — a belt-level pin with synthetic
     evaluators: gen-1 evaluation returns one breach, the fresh generation's
     evaluation returns none, the helper returns the certified cell with
     generation-retries 1 recorded.
  3. *No-structural-rerun arm* — a synthetic evaluator that raises a plain
     structural `AssertionError` (not a band breach) propagates immediately:
     zero fresh generations (pinned via the memo), proving the belt's
     re-roll scope is the two band families only.
  Collected-count check per the RED-sanity convention.
- **AR-2 (de-clocked pins keep their RED):** two classifier-regression arms
  run on the branch and shown failing against the sabotaged machinery —
  (a) monkeypatch `_dispatch_failure_is_infrastructure` to also classify
  `DEVICE_REJECTED`+`NOT_DISPATCHED` (the cause-adjacency bug F1 fixed): both
  F1 lanes' `type(raised.value) is AssertionError` pins red (the refusal
  exhausts as `TrialInfrastructureError`); (b) revert the drain-cap raise to
  a plain `assert` on the branch, in place: the drain-cap membership pin reds
  (the plain assert propagates out of `run_trial`). Green on the unsabotaged
  branch both times.
- **AR-3 (partition integrity):** markers unchanged; the collect diff
  re-recorded in the PR body (T grows by the new pins' count from slice-2's
  T=64 actuals; union/intersection re-proven by collected-id diff).
- **AR-4 (both lanes green, full rollup + cold union):** `gates` and `timing`
  green read from the COMPLETE `gh pr checks` output
  (`scripts/merge-verified.sh`); one cold local unfiltered `uv run pytest -q`
  green. The belt's worst-case lane cost (four re-run cells ≈ +20–25 s on a
  ~35 s pytest portion) disclosed in the PR body.
- **AR-5 (evidence discipline):** every gate number from
  `uv run python scripts/gate.py --fast|--full` output or junitxml
  attributes.

### 5.2 Post-merge acceptance — pre-committed BEFORE any post-merge number exists

Unit of observation: one `timing` job execution (main pushes and PR runs both
count). Red: a failing test id inside the marked set. Runner-level
startup failures categorized separately, never silently counted.

- **SHIP (the class this slice targets is dead):** over the first **40**
  timing-lane executions post-merge, at most **2** red executions, AND every
  red that occurs lies in a NAMED residual family (the sequential-model
  bands — slice 4's lane; or the sustained-stretch shape: ≥3 distinct
  band-families breaching in one execution, the 2026-09-28T22:10 pattern).
- **KILL:** ≥3 red executions in 40, **or ANY single red of a mechanism this
  slice touched** — a belted test redding on a single-stall shape (the belt
  failed to absorb a transient), or any de-clocked pin redding on retry
  composition, is a mechanism kill regardless of the count. A kill does not
  revert the slice blind; it reopens #241 with the failing log as the next
  slice's Evidence A.
- **UNDERPOWERED, not conclusive:** fewer than 40 executions accumulate
  before the next #241 slice opens → no flake conclusion from the partial
  sample; the counter continues. Every published claim carries its
  denominator ("N timing-lane executions, R red executions, E red events").
- **Baseline honesty:** the pre-merge rate this slice inherits is 7 red
  executions / ~74 executions (§6). The ship bar (≤2/40 ≈ 5%) is NOT a
  promise of order-of-magnitude improvement: the residual families
  (sequential ×3 events, sustained-stretch runs) plausibly account for 2–4 of
  the 7 red executions; the bar says the TRANSIENT classes (the other ~12
  events) stop redding, and nothing else starts.

## 6. Evidence appendix (collected 2026-10-01, before this record was written)

### Evidence A — the timing-lane red census, post-slice-2 (job-level, every failing ci run inspected)

| run | when | trigger context | timing-job reds |
|---|---|---|---|
| 36395616332 | 09-28 08:08 | main, merge #252 (standards train) | monitor-gap 206.4 vs ≤200; range-gate capture/buffered X4 trimmed 123.3 (raw 141.1) `[78.3, 102.7, 218.9, 201.0, 77.8]`; never-retries pin 3 rigs |
| 36452983841 | 09-28 16:42 | main | drain-cap pin `retries` 2≠1 |
| 36490822976 | 09-28 22:10 | main | queued 484.9 vs ≤350; axis capture/buffered `dispatch_duration` 268.1 vs ≤200; range-gate capture/buffered X1 trimmed 216.3 (raw 322.7) `[51.8, 267.8, 374.2, 51.5, 51.5]` — the sustained-stretch shape |
| 36510740468 | 09-29 02:02 | main | axis capture/unbuffered `dispatch_duration` 205.7 vs ≤200; range-gate non_capture/buffered X3 trimmed 85.2 (raw 177.3) `[197.7, 199.8, 197.8, 282.9, 375.0]` |
| 36817483120 | 10-01 04:57 | main, merge #313 | range-gate capture/unbuffered X1 trimmed 53.8 (raw 109.8) `[161.1, 75.4, 51.3, 51.9, 105.1]`; drain-cap pin 2≠1; transient-refusal pin DID-NOT-RAISE |
| 36818395071 | 10-01 05:08 | PR #315 branch (issue-#288 fold) | queued 371.8 vs ≤350; range-gate capture/buffered X4 trimmed 53.4 (raw 95.5) `[97.8, 94.5, 77.8, 173.3, 131.1]`; never-retries pin 2 rigs |
| 36852240046 | 10-01 10:56 | main, merge #322 | drain-cap pin 2≠1 |

7 red executions / ~74 executions in the window (2026-09-28T01:48Z →
2026-10-01T11:00Z); 16 red test-events. Class totals: range-gate 5 (five
different cell/axis combinations, all multi-stall), retry-exact-count pins 6
(drain-cap ×3, never-retries ×2, transient-refusal ×1), sequential-model 3
(monitor-gap ×1, queued ×2), axis per-trial bands 2. All 7 red executions
passed on subsequent runs of the same or successor trees; no diff in the
window touched a timing path. Zero cap-hit (`drain-cap` site) reds occurred
as TRIAL failures — the D1 classification itself has not once misfired in
lane; its PIN is what reds.

### Evidence B — the five range-gate reds' shapes (from the failure logs above)

Trimmed spreads 53.4, 53.8, 85.2, 123.3, 216.3 against the 50 ms bound;
2–3 trials stretched 2–7× among tight siblings in every set. None is a
systematically-spread shape (which would breach far past these margins on
every trial). Slice 2's quiet evidence (worst trimmed spread 6.0 ms, n=384
readings; the #217 trim absorbing 55/57 raw excursions) still stands as the
fixture-quality baseline: the fixture is tight; the runner is not.

### Evidence C — slice-2 measurements carried forward (not re-measured; quiet/loaded distributions are slice 2's Evidence C, n and denominators there)

`M_q` 38.0 (D3 hold), `S_q` 6.0, `D_max` 102.3, row-B quiet bands — none
re-opened by this slice; cited where they license holds.

### Evidence D — the unlocated busy_wait red (honest negative)

The brief's `test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot`
1732.5 vs ≤1700 red: PR #288 does not resolve on this tracker; the branch
that became PR #315 (`feat/issue288-spec09-review-fold`) has exactly three ci
runs (05:03 gates-red/timing-green, 05:08 the 3-red timing run above, 05:18
green) — none contains it; no other timing-job failure in the reachable
window does. Carried as brief-reported with unlocated provenance; the row-B
disposition (§2 D-rowB) does not depend on it (quiet margin 30.7 ms documents
the exposure; the sweep recorded the id as never-CI-failed, so first-flake
keep-and-document governs either way).

## 7. Top risks and their falsifiers

1. **The belt is re-roll-until-green in disguise** (the adversary's first
   attack). Bounded: one re-run, shared per key; second breach reds with both
   generations rendered; structural failures never re-run (pinned, AR-1.3);
   systematically-loose still reds (pinned, AR-1.1); detection-power
   arithmetic disclosed (§1.2). Falsifier: AR-1.1 failing, or any post-merge
   single-stall-shaped red of a belted test (the §5.2 mechanism kill).
2. **The membership pins are weaker than the count pins.** A regression that
   moves attempt 0's death from `drain-cap` to an earlier site would pass the
   membership pin. Accepted: the classification machinery itself is pinned by
   the type arm, the exhaustion arms, and the classifier tables; what the
   membership pin loses in attempt-discrimination it gains in load-truth
   (three false reds say the exact counts were wrong, not the machinery).
   Falsifier: the AR-2 sabotage arms failing to red.
3. **The belt's interaction with the module cell cache creates
   order-dependence** (the #280 class). Structural answer: readers evaluate
   the newest certified generation; the raw cache is never rewritten; the
   trial-log test reads gen-1 as today. Falsifier (refute-fold correction,
   mech-F4 — the original text named `-p no:randomly` order permutations,
   but pytest-randomly is not a dependency of this tree): a belt-reader
   verdict that differs between the serialized timing-lane run and the
   cold unfiltered union run — both ran green in file collection order at
   build (timing lane 70/0/0; union 2722/0/0/11); no order-randomizing
   plugin exists, so file order is the only order the lane executes in,
   and order-independence is structural: each reader evaluates gen-1,
   then the memoized certified generation, at its own runtime.
4. **Retry-composition visibility gap** (carried from slice 2, unchanged):
   green-path belt usage is print-only. Falsifier/watch: a belt-related
   incident whose log lacks the usage line — then the belt-visibility
   deferral opens.
5. **The residual families keep the lane red often enough to fire §5.2's
   kill on volume.** The sequential family (3 events) is slice 4's payload,
   pre-specified in §2 — if the kill fires on it, slice 4 opens immediately
   with its design already written. Falsifier: ≥3 reds/40.
6. **The D4 letter/mechanism fork is decided wrong.** Both readings recorded
   (§0.4); the owner can call it fired now — the payload is specified either
   way. Not a design risk; a sequencing call.
7. **Local/host transferability.** All Evidence A/B numbers are runner-side;
   slice 2's local distributions are macOS. The mechanisms (bounded retry,
   membership pins) are shape-transferable; no local number licenses a bound
   here — no bound moves.

## 8. File-level change list

| file | change |
|---|---|
| `tests/integration/test_cross_instance_continuity.py` | the `_certified_cell` belt + memo beside `_TRIAL_CELLS` (:1794); `_axis_upper_band_breaches` / `_range_gate_breaches` (the re-homed upper-band and spread loops, values byte-identical); range-gate and axis tests read through the belt (floors/structural asserts stay inline); three belt pins; five pin de-clocks (drain-cap :2906, F1 lanes :3242/:3272, priming pins :2643/:2690) + the any-rig write injection; two AR-2 sabotage arms |
| `docs/internal/drift-and-obligations.md` | the testing-conventions line gains the belt sentence (band readings that absorb transient stalls re-measure once through the belt; systematic looseness still reds) |
| `.claude/deep-review/2026-10-01-issue241-slice3-retry-honest-pins-cell-belt-design.md` | this record, commit 1 |
| issue #241 | outcome comment: the census, the kill-arm statement, per-item verdicts, the D4 fork named |

No `src/` bytes. No `standards/` bytes. No workflow bytes. No numeric bound
moves anywhere — the reading, the trim depth, the denominator, every ceiling
and floor in the marked set are byte-identical after this slice.

Refute-fold correction (2026-10-01, mech-F6): the file-level list above
overcounts the AR-2 arms — ONE committed test shipped (the
classifier-regression arm, now a two-row table with the displaced-site
row); AR-2(b) shipped as an in-place RED demonstration recorded in the
fold commit's ancestor message, not a committed test. The same fold adds:
the X1-floor both-generations fix with its pin (adv-F1/mech-F3), the
AR-2a site-membership form (mech-F1), and claim corrections C1–C5 at
their sites above.

## D4' folded by trigger (2026-10-01, post-refute)

The deferral table's D4' reopen trigger — "any second red of ANY
sequential-model band in-lane" — FIRED: PR #324's timing lane redded
`test_monitor_gap_during_a_deadline_max_capture` at gap 354.6 vs the
absolute 200 ms ceiling (`assert gap_ms <= BUDGET_MS + TOLERANCE_MS`),
on top of the census's prior sequential reds (Evidence A: monitor-gap
206.4 on run 36395616332; queued 484.9 on 36490822976 and 371.8 on
36818395071) and issue #207's row-B corroboration. The pre-specified
payload executed verbatim on this branch:

- monitor-gap ceiling: `gap <= realized-dispatch-duration +
  TOLERANCE_MS`, both measured in-run; the UNKNOWN-status assert and the
  `>= BUDGET_MS - 40` floor unchanged — the reverted-`bounded()` arm
  (the timeout disabled; the run then completes past the budget, natural
  or quota-terminated — observed ~330 ms at fold) is still caught by the
  status assert (verified at fold: the deadline-relaxed shape reds on
  the status assert, not on any band).
- queued-run ceiling: `delay <= measured-run-1-start-to-end + 300` —
  run-1's init is measured, not guessed; a synthetic worst-case pin
  (`test_queued_delay_band_refuses_a_delay_past_run1_plus_slop`) holds
  the form's teeth, the family having no planted arm.
- `test_second_dispatch_lock_block` keeps its absolute band (D4's own
  letter: the family's one real-clock representative).
