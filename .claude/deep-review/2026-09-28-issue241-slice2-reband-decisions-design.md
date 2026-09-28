# Issue #241 slice 2 — the re-band decisions: classify the drain cap, hold or re-band from evidence, mark the stragglers

Design record for the second stabilization increment of the #240 red-lane class.
Tree: `main` at `4d44f3b` (slice 1 merged as #246 `d9b1924`; the #247 gate-efficiency
train #248–#251 landed after). Standards-bump hold (#203 window): this design moves no
standards bytes — `git diff origin/main...HEAD -- standards/` is a standing build-gate
check and is expected empty; any standards-byte involvement is HOLD-and-report, not
proceed.

**Pre-commitment protocol (disclosed).** Slice 1's record was committed before any lane
number existed. Slice 2's inputs are measurements taken while this record was being
designed, so the provability of pre-commitment is weaker and is carried explicitly: the
disposition thresholds in §5 were fixed and messaged to the team lead (timestamped
SendMessage, 2026-09-28) BEFORE the measurer reported any number; the measurer collected
independently and had received only the measurement brief, not the thresholds. The
residual — that the designer could in principle have seen a number before writing the
rule — is mitigated by the timestamped message and named here rather than hidden. The
builder's FIRST commit on the branch is this record, complete with the numbers and the
selected arms; every later commit cites it.

## 0. Root cause and state, established from the tree (not assumed)

**D1 — the drain cap is the last loud, unclassified failure in the delivery path.**
`ContinuityRig.drain_until_quiet`
(`tests/integration/test_cross_instance_continuity.py:814`) ends in a plain
`assert quiet` whose message is `drain_until_quiet hit its {cap_ms:.0f} ms cap with N
frame(s) still due` (line ~874). Three facts make the fragility precise:

- All three call sites — the pre-settle drain, the post-settle drain, and the
  post-dispatch X3 drain (lines 1148, 1150, 1259) — sit INSIDE `_run_trial_once`'s
  `try`, inside `run_trial`'s fixed three-attempt loop. A `TrialInfrastructureError`
  raised anywhere in there rides the existing fresh-rig retry and the F3'/F4 failure
  belt; the plain assert raises straight through (`run_trial` catches only
  `TrialInfrastructureError` — `test_cross_instance_continuity.py:1105`).
- The helper ALREADY classifies one of its own failures as infrastructure: the
  post-trip poll-door dead session raises `TrialInfrastructureError(...,
  site="drain-poll-door")` (line ~858). The cap assert is the one remaining failure in
  the helper that presents host starvation as a trial verdict.
- The sweep's gates-era evidence: the cap fired with **39 frames due** after 2000 ms —
  at the 20 ms frame period that is ~780 ms of backlog, which a 2.5–3x-stretched host
  cannot deliver inside 2000 ms even though nothing is wrong with the fixture. That is
  the F4 class verbatim (the docstring's own words: "the delivery path starved") — the
  class `TrialInfrastructureError` was built for on PR #236, extended by slice 1
  (priming block-refusal + signal-validity), and simply not yet wired at this site.

Clock-domain check (the slice-1 F2b lesson, applied): the cap reads `time.monotonic()`
— the REAL clock — and `due_count()`/delivery pacing are real-clock too; the
divergent-wall probe injects the MONITOR wall, which does not enter this assert. No
wall-rate guard is needed at this site, and none is added.

**D2 — the range gate after #217/#245.** The spread reading
`_underpowered_range_ms` (line 1891) is TRIMMED of the single most-extreme trial per
axis over the 5-trial cells; bound `0.25 * T_ACQ_MIN_MS` = 50 ms; both directions pinned
by `test_range_gate_tolerance_both_directions` (line 2305: the contended replay
[78.0, 78.1, 77.9, 150.9, 77.6] must NOT read UNDERPOWERED; a systematically-spread
fixture and a double-spiked shape MUST). The three historical range-gate reds were
pre-trim, pre-lane, gates-era bulk-suite residue. The #247 xdist trial saw raw spread
113.9 ms under deliberate 10-way contention — an environment now structurally excluded
(the test is `timing`-marked; gates runs `-n auto -m "not timing"`). What slice 2 owes
D2 is the reopen trigger's own demand: "slice 2's measurement pass opening" — the pass
itself, with the distributions recorded and a decision.

**D3 — control_x2's ceiling is a median, not a spike gate.** `test_control_arm_and_
separation` asserts `control_x2 <= 50` where `control_x2` is the MEDIAN of 5 control
trials (`test_cross_instance_continuity.py:1861`). A red therefore requires ≥3 of 5
trials reading > 50 ms — sustained stretch, not a single stall (a lone spike cannot move
a 5-median past its bound). Quiet median 38.0 ms (the sweep). The sibling
`unbuffered_x2 < 50` (fresh-conversion collapse) rides the same quantity family. The
separation semantics (long-arm X2 ≥ 150) live in the same test and are untouched by any
arm of this slice.

**The #247 handoff — three spike-brittle gates routed here by the gate-efficiency
design's own deferral D1** (`.claude/deep-review/2026-09-28-issue247-gate-efficiency-
design.md` §3; the promised issue-#241 handoff comment was never posted — this record
absorbs the disposition and slice 2's outcome comment posts it):

1. The per-trial upper band — `test_axis_trials_complete_all_four_axes` (line 1786):
   `x1_ms <= dispatch_ms + 150` and `dispatch_duration_ms <= dispatch_ms + 150`, per
   trial, 4 cells × 5 trials.
2. The row-B clamp bands in `tests/unit/test_otdp_bridge.py`:
   `test_row_b_clamp_bounds_the_mid_capture_wait_by_the_step_deadline` (marked,
   `120 <= append_wait_ms <= 450`, nominal ~200) and
   `test_row_b_clamp_negative_injected_remaining_clamps_to_zero` (line ~2836,
   **UNMARKED**, `100 <= windows[0] <= 150` — the audit's tightest: 50 ms headroom,
   LOWER-bound trip, single reading, so the trim pattern cannot apply).

The row-17 test is the one slice-1 left unmarked ("per the sweep's keep-and-document
disposition"). That disposition predates two environment changes: the testing-convention
line this repo now carries ("a wall-clock bound assert on a real clock … carries the
`timing` marker", `docs/internal/drift-and-obligations.md`) and gates going xdist
(`-n auto`) — an unmarked real-clock band now runs under exactly the contention class
the convention exists to remove it from. Row 17's band derives from injected-clock
remaining minus REAL elapsed between the deadline stamp and clamp entry — scheduler
jitter walks the value straight at the 100 ms floor. Marking it is conformance to the
convention the tree already ships, not a new judgement.

**The slice-1 post-merge rule is in force and slice 2 is the measurement pass it
anticipated.** Unit: one `timing` job execution; ship at ≤1 marked-set red in the first
20 executions, kill the isolation claim at ≥2, underpowered below 20. The lane
counter's count at design time: **N_A = 12, R_A = 0** (Evidence A, §6) — UNDERPOWERED
arm selected: isolation stands so far, no flake conclusion is drawn, and the counter
continues unchanged post-merge (8 more executions close the rule's window).

## 1. Mechanism — what slice 2 changes

Four things, one of them conditional on pre-committed arms:

1. **D1 classification (behavior change, test-side).** The cap assert becomes
   `raise TrialInfrastructureError(<same diagnostic text>, site="drain-cap")`. The
   carrying-site list in `run_trial`'s docstring gains "the delivery-drain cap — frames
   still due at the 2000 ms cap, the sweep's 39-frames-due gates failure (issue #241
   slice 2)". Two pin tests land beside the F4 pins, in the slice-1 counter shape
   (`_install_priming_starvation`'s `counting_init`/`counting_b_init` wrapping, patch
   scoped to `adapters[:1]`): a TYPE arm — a direct `drain_until_quiet(cap_ms=<short>)`
   call on a rig whose adapter's `due_count` reports frames perpetually due; the real
   loop spins to its real (short) cap; assert the raise is `TrialInfrastructureError`
   with `site == "drain-cap"` — cheap, no full-cap burn — and an INTEGRATION arm — the
   first construction's adapter patched via the counter shape, the trial path's first
   drain hits the default cap, `run_trial` retries on a fresh unpatched rig, the
   outcome carries `retries == 1` and `retry_sites == ["drain-cap"]`. Site-level
   exhaustion is NOT re-pinned: the integration arm proves the raise reaches the retry
   loop, and the three-attempt exhaustion machinery is site-agnostic and already pinned
   (`len(rigs) == 3`). The patch is faithful by construction — `due_count > 0` keeps
   delivery working (frames still emit on schedule; only the quiet guard never sees
   zero), the healthy-path-under-starvation shape, and the first drain call site
   precedes `settle` and the measured dispatch, so the patched rig dies at the intended
   site with nothing downstream running. The cap VALUE stays 2000 ms unless §5's D-max
   arm fires. The sibling `assert not outcome.session_failed` in the
   post-trip poll stays plain — that is the poll-poisoned-the-session class already
   disclosed as a starvation-shaped NON-retryable at `_poll_found_dead_session`; D1
   widens the retryable class by exactly one site.
2. **Row-17 marker (selection change, one line).** `@pytest.mark.timing` on
   `test_row_b_clamp_negative_injected_remaining_clamps_to_zero` — conformance to the
   testing-conventions line; NO band change; the slice-1 row-17 clause is overridden on
   the changed-environment evidence and the override is disclosed here and in the issue
   comment.
3. **Documentation with denominators.** The measured distributions (quiet/loaded, per
   gate, with trial counts and host conditions) land in this record's §6 and in the
   #241 outcome comment — including the #247 handoff disposition the gate-efficiency
   record promised. Where an arm holds a bound unchanged, the record states the margin
   the measurement found; where an arm moves a number, the record carries the quiet and
   loaded distributions that licensed it.
4. **Conditional re-band arms (D3, D-max, #247 bands)** per §5 — each pre-committed
   before the numbers, each with its kill direction. **None fired** (§6 final
   selections: D3 HOLD at M_q = 38.0; D-max 102.3 ≤ 1200; #247 quiet values inside
   their documentation windows) — this item resolves to documentation only.

What slice 2 does NOT do: no re-band of the range gate's denominator or fraction in any
arm (§5 D2 explains why that is not re-bandable from load evidence); no virtual-clock
migration (D4 unchanged); no marker-rot guard (D5 unchanged — and its trigger is now
MORE live under xdist gates, noted); no bound moves anywhere unless a §5 arm fires on
quiet-host evidence.

## 2. Minimal increment scope

Build order (each RED-first where behavior changes, one slice per commit):

1. Commit 1: this design record (complete, with numbers and selected arms).
2. D1 classification + the two pin tests (RED on unmodified `main`: the integration
   arm errors with the plain `AssertionError` propagating out of `run_trial`).
3. Row-17 marker + the AR-2 partition re-proof.
4. Any fired §5 arm (D3 re-band, D-max cap raise, #247 band amendment) — its own
   commit, its own RED where a pin asserts the old number. **None fired — this
   step is empty.**
5. Docs sweep (G5): prose that names the marked set's membership (CI-map row, the
   conventions line's examples if it enumerates) gets the row-17 note; nothing else.

### Deferral table

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D2-fixture | fixture-pacing investigation (if any cell's QUIET trimmed spread exceeds the §5 D2 threshold — the gate's own prescription "fix fixture pacing, decide nothing") | follow-on issue #241 slice (opened only if the arm fires) | the investigation's own findings; opened by this slice's outcome comment if fired |
| D2-trim | trim depth / trial-count revisit | documentation in this record | ≥2 in-lane range-gate reds with log lines naming the cell and values (the double-stall shape the one-trial trim cannot tolerate) |
| D3-sibling | unbuffered_x2 quiet median (uncollected — the flag reached the measurer mid-collection; moot under the selected HOLD arm because the sibling moves only in a D3 re-band commit, and no such commit exists) | documentation in this record | D3 re-entering (42, 50] on a future M_q measurement — collect the sibling's own quiet median BEFORE any unbuffered_x2 move (it moves only if that median > 40 ms) |
| D4 | virtual-clock migration of the sequential-model quantities | issue #241 (slice-3 posture, documented on the issue) | a second in-lane red of the sequential-model 200 ms family (`BUDGET_MS + TOLERANCE_MS = 200` ms bounds) AFTER this slice's arms land — pre-landing reds feed the baseline, they do not fire it |
| D5 | marker-rot guard (automated check that a new real-clock ms-bound test carries `timing`) | documentation in the slice-1 record | a `gates` red on an unmarked test whose failure is a ms-bound assert — MORE live now that gates runs `-n auto`, not less |
| D6 | keep-and-document clusters (sweep rows 8/9/17/18/19 + row 20) — row 17's MARKER moves this slice; its band disposition stays keep-and-document | issue #241 closure pass | each row's own recurrence: a second CI flake of that test id |
| D7 | plugin-lane paced tests (sweep row 26) | issue #241 closure pass (documented out-of-lane) | a plugin lane entering CI |
| #247-D2 | rtk binary-side filter fix (upstream) | documentation in the #247 record | only if the gate.py wrapper proves insufficient |
| #247-D3 | benchweave-sdk AGENTS.md doctrine mirror | the #247 record's own row | checked at increment-1 build (already done — not mirrored); re-fires only if the SDK repo adds the line |

## 3. Precedent (all in-tree, all extended not invented)

- **The F4 retry classification** (PR #236; extended by slice 1 twice and by the
  drain-poll-door site): `TrialInfrastructureError` + `run_trial`'s TYPE-based matcher
  + the `site=` keyword discipline (critic F3: every raise labelled, no defaults) +
  `outcome["retry_sites"]`. D1 adds exactly one labelled site to the enumerated list —
  the same shape slice 1's record used, with the same exhaustion-still-reds property.
- **The #217/#245 one-trial trim** (`_underpowered_range_ms`): the tolerance precedent
  for D2 — evidence-backed, licensed by item 7's own rationale, pinned BOTH directions
  so tolerance cannot become looseness. D2's no-denominator-move stance extends the
  same discipline: tolerance for host stalls, teeth for fixture looseness, and the
  commissioned clause (25% of dispatch duration) is not load-renegotiable.
- **The slice-1 `timing` marker itself**: row 17 joining the marked set is the
  marker mechanism doing what its convention line says — no new machinery.
- **`scripts/gate.py`** (#247 increment 3): the build protocol's evidence wrapper —
  every gate line the builder reports comes from the wrapper's machine-readable output
  or junitxml attributes, never a piped summary.

## 4. Invariant and drift impacts

- **A06 (evidence over assertion) — load-bearing, both directions.** The D1
  classification is A06 in the small: a host-starved delivery path presented as a trial
  verdict launders an environment artifact into a measurement record; the retryable
  class widens by one STRUCTURALLY-typed, site-labelled site, exhaustion still reds,
  and `retry_sites` keeps the composition visible (a lane that routinely exhausts
  drain-cap is a lane-health signal, not a hidden pass). The documentation arms are
  A06's other direction: every held or moved number carries its measured distribution
  and denominator, so the next reader can tell evidence from assertion.
- **No CTL/STO/CON/REG invariant is touched.** No `src/` byte moves; no store,
  executor, protection, admission, or standards path. No new invariant needed — this is
  test infrastructure; the CI map and the conventions line are the governing docs.
- **Tier**: no on-disk format or schema; not Tier-3. The #203 standards hold is
  satisfied mechanically (empty `standards/` diff expected and checked at push).
- **Obligations walked**: 4 (operator-visible CI set membership — the AR-2 partition
  re-proof is recorded in the PR body; prose naming the marked set swept), 5 (no
  workflow change; the marker moves set membership only — but a cold local unfiltered
  run is included in acceptance as the union proof), 14 (no agent grant changes).

## 5. Measurable proof and the pre-committed acceptance rules

### 5.1 Inputs and the slice-1 post-merge rule (arm selected on Evidence A: UNDERPOWERED)

Inputs: **N_A/R_A** = timing-lane executions / marked-set reds since #246 (per test
id); **S_q** = max trimmed range-gate spread over the 4 (arm, class) cells × 4 axes
(16 readings), quiet host;
**M_q** = control-arm buffered X2 median-of-5, quiet; **D_max** = max observed
successful-drain duration, quiet+loaded; row-B band quantities quiet
(append_wait_ms, windows[0], pre_begin_ms, busy_wait_ms).

- If N_A ≥ 20: R_A ≤ 1 → isolation stands (record it); R_A ≥ 2 → the kill arm — the
  "green lane by isolation" claim is dead and this slice's evidence-backed arms become
  #241's mandatory path (which they already are — this design IS that response).
- **SELECTED — N_A = 12 < 20: UNDERPOWERED.** Stated, not worked around: R_A = 0 in 12
  executions (0 runner startup failures across all 26 ci runs in the window), so
  isolation stands SO FAR, but no flake conclusion is drawn from the partial sample.
  The lane counter continues unchanged post-merge — 8 more clean executions close the
  rule's window — and the dispositions ride the quiet-host rules below. No marked-set
  red has occurred, so slice 1's induced-load-study provision is not triggered.

### 5.2 Disposition rules (fixed 2026-09-28, before any number was read — timestamped message to the team lead on record)

**D1 (drain cap): BUILD unconditionally.** Classification, not a band. Acceptance is
RED→GREEN (AR-1 below), not a number. Cap value: stays 2000 ms **unless D_max >
1200 ms** (60% of cap) → 3000 ms in the same commit, telemetry disclosed. Kill
direction for the raise arm: D_max ≤ 1200 ms with the raise applied anyway would be an
unforced widening — the arm is refused in that case.

**D2 (range gate): NO bound bytes move in any arm.**
- SHIP-AS-IS (document distributions) iff S_q ≤ 40 ms AND R_A(range-gate) = 0.
- R_A(range-gate) = 1 with S_q ≤ 40 ms: the slice-1 post-merge rule's tolerated single
  red — document, continue the counter (this is slice 1's own pre-committed threshold,
  not a new one).
- Fixture-pacing investigation (follow-on; bound untouched) iff any cell S_q > 40 ms —
  a quiet host at ≥80% of the bound is fixture looseness, and the gate's prescription
  for that is "fix fixture pacing, decide nothing".
- Trim depth / trial count revisited ONLY on R_A(range-gate) ≥ 2 with log lines naming
  cell and values (the double-stall shape). The denominator (25% of the 200 ms dispatch
  duration) is a commissioned clause — not re-bandable from load evidence; a precision
  gate reading underpowered under load is the gate working.

**D3 (control_x2 50 ms ceiling):**
- HOLD 50 iff M_q ≤ 42 ms AND R_A(control-x2) = 0.
- Evidence-backed re-band 50 → 60 iff M_q ∈ (42, 50] — shipped with quiet+loaded
  distributions and denominators; the separation assert (`long_x2 ≥ 150`) untouched, so
  the re-banded gate still proves ≥2x separation.
- M_q > 50 = fixture regression investigation, NOT a re-band (a bound that a quiet host
  already reds is a fixture defect wearing a gate's clothes).
- The `unbuffered_x2 < 50` sibling rides the same inputs; it moves in the same commit
  only if its own quiet median exceeds 40 ms.

**#247 handoff gates:**
- Row 17 gains the `timing` MARKER unconditionally (conformance; see §0) — no band
  change; measured headroom recorded either way.
- The 120..450 band and the per-trial upper band: document iff quiet values inside
  [150, 350] / ≤ dispatch+100 respectively; a wider-band amendment to the #146 row-B
  record fires only if a QUIET host exceeds those — never load evidence.

### 5.3 Build-time acceptance (the PR's own gates)

- **AR-1 (D1 RED→GREEN):** the integration pin shown failing on unmodified `main`
  (the plain `AssertionError` propagates out of `run_trial`; collected-count check per
  the RED-sanity convention) and passing on the branch with `retries == 1`,
  `retry_sites == ["drain-cap"]`. The type arm pins the raise's TYPE and `site` label
  directly (TYPE-matched — no test matches on message text); exhaustion stays covered by
  the existing site-agnostic pin (`test_infrastructure_marker_exhausts_at_two_retries`,
  `len(rigs) == 3`).
- **AR-2 (partition integrity):** the §5 AR-1 collect-diff re-recorded in the PR body
  with row 17 counted in T (Evidence A's tip baseline: T=61 → 62, G shrinks by one, U
  unchanged — union and intersection re-proven by the recorded collect diff, not
  asserted).

  *Erratum (2026-09-28, wave-1 review fold — adversary F4; history above not
  rewritten): the prediction was made before the D1 pins were counted as marked-set
  members. The ACTUALS, measured at the pre-fold branch tip and now the
  outcome-of-record: **T=64, G=2396, U=2460** (T = 61 + 1 row-17 + 2 D1 pins;
  G = 2397 − 1 row-17; U = 2458 + 2 pins), `T∪G == U` and `T∩G == ∅` re-proven by
  collected-id set diff. The PR body carries the actuals, including the wave-1 fold's
  own recount (two further marked-set members: the mixed-composition arm and the
  drain-cap exhaustion arm, both in the timing-marked continuity file).*
- **AR-3 (both lanes green, full rollup):** `gates` (`-n auto -m "not timing"`) and
  `timing` (`-m timing`) green on the PR, read from the COMPLETE `gh pr checks` output
  (zero fail, zero pending — never a piped view; `scripts/merge-verified.sh`).
- **AR-4 (cold union run):** one local cold unfiltered `uv run pytest -q` green — the
  marker move changed membership, and the union executing green in one process is the
  no-coverage-lost proof at build time.
- **AR-5 (evidence discipline):** every gate number the builder reports comes from
  `uv run python scripts/gate.py --fast|--full` output or junitxml attributes.

### Build protocol (the #247 gate doctrine, superseding the old per-commit full battery)

Branch `feat/issue241-slice2-<slug>` off `origin/main`; the builder works in
`.wt/issue241-slice2-<agent>-<nonce>` (in-repo worktree, gortex overlay kept).
Per-commit FAST lane, no exemptions:
`UV_PROJECT_ENVIRONMENT=venv uv run python scripts/gate.py --fast <touched test paths>`
(ruff + fresh-cache mypy + focused pytest inside the wrapper). Per-push FULL battery
once: `uv run python scripts/gate.py --full` (xdist `-n auto -m "not timing"`), plus a
local serialized `uv run pytest -q -m timing` (CI runs the lane too), plus the #203
standards tripwire (`git diff origin/main...HEAD -- standards/` empty — reported either
way). `set -o pipefail` gates before every push; no commits to `main`.

## 6. Evidence appendix (verbatim from the measurer's reports; filled before commit 1)

### Evidence A — timing-lane CI history (2026-09-28)

12 executions of the `timing` job since it first appeared (PR #246's first CI run
2026-09-27T16:46:59Z) through 01:48Z 2026-09-28. **All 12 green, R_A = 0.**

- PR #246's own merge-ref runs: 36334503958, 36335742748, 36360912724 (pre-merge
  re-run) — green.
- Merge-commit main push: 36361185809 — green.
- Post-merge PR merge-refs (issue247-* branches): 36366322143, 36366364025,
  36366365512, 36366368731 — green.
- Post-merge main pushes (#250/#251 landing window): 36367378977, 36367386405,
  36367394803, 36367403570 — green.

Runner startup failures: 0 (startup_failure/cancelled scanned across every job of all
26 ci runs in the window). Set size 58 → 59 → 61 during the PR's life, stable at 61 for
the last 10 executions, zero skips/failures. Job wall 42–52 s including uv sync; pytest
portion ~35 s serialized. No `timing` job exists in any run before 2026-09-27T16:46Z
(the branch's earlier 12:50Z push, run 36320315011, predates the job).

**Pre-committed rule at 12/20: PASS so far; UNDERPOWERED until 20 executions.**

### Evidence B — drain-cap telemetry (CI side)

**0 cap-hits in 12/12 timing logs.** Instrument verified not blind: the cap-hit is a
hard `assert quiet` (AssertionError carrying "hit its 2000 ms cap with N frame(s) still
due") — any hit reddens the job and prints, so a green log proves absence. Old-regime
control: 30 pre-merge gates executions (2026-09-25T02:31Z → 2026-09-26T23:34Z, the
xdist bulk-suite regime with the continuity tests in-suite): 0 cap-hits; the single red
there (36098732003, an unrelated branch) contains no cap-hit. The sweep's 39-frames-due
observation therefore predates every reachable CI execution: **no cap-hit has ever
appeared in the 42 reachable CI executions.** D1's CI evidence base is zero-frequency —
its justification is the mechanism (§0) plus local provocation (Evidence C digest 2),
and the classification is robustness-by-class-charter, not frequency-driven. Disclosed
honestly: a skeptic can read D1 as insurance whose triggering load the lane has (so
far) structurally removed; the counter-price is one labelled site plus two pins, and
exhaustion still reds.

### Evidence C — local distributions and provocation (digests 2+3 + post-lift collection, 2026-09-28; local macOS 10-core host, per-run load-avg stamps)

**C.1 Threshold disclosure (load-bearing).** The measurer's digests classify trimmed
spreads against a 5.0 ms working threshold — a misread of the gate. The code's bound
is `spread <= 0.25 * _RANGE_GATE_DENOMINATOR_MS` with `_RANGE_GATE_DENOMINATOR_MS =
T_ACQ_MIN_MS = 200.0` (`test_instrument_range_gate_per_axis_per_cell`,
`tests/integration/test_cross_instance_continuity.py:1931`; constant at :1888 and
:102) — **50.0 ms**, uniform over the four measurement cells (the short-dispatch
control cell is deliberately outside the gate per that test's docstring). The
measurer's spread VALUES are the measurements and stand; only their in/out-of-bound
counts used the 10x-tighter threshold, and those counts are reclassified below. No
arm selection differs under either reading: the worst quiet spread (6.0 ms) clears
the letter's 40 ms ship condition by 6.7x, and zero quiet readings approach the
code's 50.0 ms bound.

**C.2 Drain-cap provocation (digest 2; D1).** CI: 0 cap-hits ever in the 42 reachable
CI executions (12 timing + 30 gates-era). Local, by host-load bin: load 60–160 —
0 hits over several thousand drain calls, including 2 whole-file green passes under
10 deliberate spinners at load ~95; load ~200–330 — 1 hit/12 separation invocations,
99 frames due; load ~375–454 — 5 hits/12 range-driver passes (frame-due 20, 2, 6,
103, 3) with 2 rig protection trips co-occurring (the real-paced rig itself degrades
at that saturation). Frame-due at hit, full set {2, 3, 6, 20, 99, 103}: bimodal —
2–3 frames is a marginal miss (40–60 ms short; one retry or a small re-band clears),
20–103 frames is total starvation (the backlog GROWS through the cap; delivery ~0;
no re-band can rescue — only a retry-on-transiency can). The cap-hit is one symptom
of host starvation (protections trip alongside it): an environment condition in the
F4 class, not a fixture defect — retry-once via `TrialInfrastructureError` matches
the failure shape and covers BOTH subclasses when transient.

**C.3 control_x2 by load bin (digest 3; D3 diagnostics — loaded context, not M_q).**
23 green invocations of `test_control_arm_and_separation`: load 63–92 median 38.5 /
max 40.0 (n=12; matches slice-1's quiet 38.0 baseline); load 141–182 median 40.0 /
max 43.0 (n=12); load 202–326 median 43.0 / max 46.0 (n=11 — the 12th was the C.2
drain-cap red, not a ceiling breach). The 50 ms ceiling was never breached in any
green run; stretch ~+1.5 ms per +100 load-avg; values quantize at whole ms
(pacing-bound, not scheduler-bound). Control X3 max 103.3 against its 3x POLL_MS
bound — passed.

**C.4 Quiet-arm collection (post-lift; quiet bin = load 27.0–52.2, best obtainable
window — truly idle unobtainable with peers; stated plainly per the measurer's
commitment).** Worktree off origin/main @ 4d44f3b, /tmp venv, per-run load stamps,
self-limiting spinners with 0 survivors verified per loaded batch.

- **M_q** (control_x2 median-of-5 per invocation; n=12 at load 27.0–37.6, 12/12
  green): values [38×7, 39, 40×3, 41] → median **38.0**, max 41.0 — matches slice-1's
  quiet 38.0 exactly; 9 ms margin at max under the 50 ceiling.
- **S_q** (max trimmed spread over the 16 cell/axis readings; n=24 passes at load
  39.8–52.2, 384 readings): worst **6.0 ms** (non_capture/buffered x2 = 6.0 and
  x3 = 5.95 — the only two over the measurer's informal 5.0; ZERO over the code's
  50.0 bound). Raw range > 5 ms in 57/384; the #217 trim absorbed 55/57 (96%),
  including a capture/unbuffered x3 raw 69.1 → trimmed 3.79. Pooled trimmed-spread
  worst by load: 40–52 → 6.0; 80–130 → 5.1 (digest 3: 191/192 under the informal
  5.0); 148–269 → 12.1; ~400 → genuine > 50 reads appear (56 ms observed) — the gate
  reading UNDERPOWERED under real starvation, which is the gate working. CI: 12/12
  timing greens prove every reading under even the informal 5.0 on every CI
  execution to date.
- **D_max** (wrapper-timed successful drains): quiet n=720 at load 39.9–51.4 →
  median 45.7 / p95 46.6 / max 88.2; loaded n=720 at load 148–269 → median 46.0 /
  p95 51.9 / max 102.3, 0 failures. **D_max (quiet+loaded) = 102.3 ms** — 22.6x
  headroom under the 2000 ms cap; the §5.2 raise trigger (D_max > 1200) is
  decisively not met.
- **Row-B quiet bands** (n=12 per condition; driver replicates each test's
  measurement section verbatim over the module's own helpers; quiet load 39–55,
  loaded ~120): append_wait_ms [120,450] quiet 236.2–267.4 (median ~259), loaded
  239.2–264.7 — ~185 to the upper / ~116 to the lower, load-robust; pre_begin_ms
  [900,1400] quiet 1001.4–1022.6 — pinned at ~1003, ~375 both sides; busy_wait_ms
  [1300,1700] quiet 1605.4–1669.3 (1669.3 = 30.7 under the upper bound, the set's
  tightest), loaded 1605.4–1643.6; fail_delta_ms 2639–2672, comfortably inside
  (1500, 1500+pre+300]; windows[0] [100,150] = **149 in all 24 replications both
  conditions** (integer-quantized, load-insensitive at load ≤ 120; trip direction is
  the LOWER bound — stamp-to-clamp-entry delay > 50 ms — not induced even at load
  120). Per-trial x1/dispatch_duration maxima (n=120 trials per arm per condition):
  capture x1 max 99.1 / dur max 112.2 (dispatch 50); non_capture x1 max 223.4 /
  dur max 223.9 (dispatch 200) — all 50–130 ms under the dispatch+150 axis bound and
  inside the ≤ dispatch+100 documentation window.
- **unbuffered_x2 quiet median: NOT collected** (the sibling-quantity flag reached
  the measurer mid-collection). Moot under the selected HOLD arm — the sibling
  moves only in a D3 re-band commit, and none exists. Tracked as deferral
  D3-sibling.

**C.5 Capture-sequential 200 ms family (digest 3; n=12 at load 147–330, all
green).** Monitor gap 50.7–52.2 (band 10–200), lock-block 50.1–52.3 (20–200), queued
delay 56.4–59.6 (10–350), contention stretch 401–505 (≥ 110 only) — deadline-capped
by construction and load-insensitive at these levels. Slice-1's 5.4x quiet-to-CI
stretch is NOT reproducible by ambient host load — consistent with the intra-suite
residue thesis; honest negative: the actual same-VM xdist-residue shape was not
reproduced locally (the measurer's contention is external processes, not same-VM
residue).

**C.6 Confounders (the measurer's own statements, carried verbatim in substance).**
(1) Ambient peer-agent load uncontrolled and bursty (load-avg 59→453 across the
first window); mitigated by per-run/per-pass load stamps and binning; bins are
coarse. (2) The spinner-leak window (10–20 procs, ~14 min) contaminates the 141–182
and 202–326 bins in the MORE-load direction — conservative for every held bound.
(3) Local macOS 10-core host ≠ CI ubuntu VM: magnitudes not transferable;
failure-mode shapes and directions are. (4) The distribution drivers call the
run_trial machinery directly (bypassing `_cell` memoization) — the same machinery
the tests use; 2 whole-file green passes corroborate. (5) Quiet bin = load 27–52,
best obtainable, not idle. (6) The row-B drivers are verbatim replications of each
test's measurement section, not the tests themselves.

### Arm selections (FINAL — Evidence C complete, 2026-09-28; every deciding input measured on the quiet arm)

- Slice-1 post-merge rule: **UNDERPOWERED stands** (N_A = 12 < 20, R_A = 0); the
  counter continues unchanged post-merge — 8 more clean executions close the window.
- D1: **BUILD** — `TrialInfrastructureError(site="drain-cap")`. Cap **STAYS
  2000 ms**: D_max = 102.3 ms (quiet 88.2 / loaded 102.3) ≤ 1200 decisively — the
  raise arm is refused by its own pre-committed kill direction (an unforced
  widening).
- D2: **SHIP-AS-IS** — S_q = 6.0 ms ≤ 40 with R_A(range-gate) = 0; distributions
  documented in C.4; no bound byte moves; the trim keeps its commissioned depth
  (0 in-lane range-gate reds — the trim-depth revisit trigger never fired).
- D3: **HOLD 50** — M_q = 38.0 ms ≤ 42 with R_A(control-x2) = 0; the ceiling is
  untouched (9 ms margin at the quiet max 41.0); the re-band window (42, 50] was
  never entered; the separation asserts are untouched by construction.
- #247 bands: **document-only** — quiet append_wait_ms inside [150, 350]
  (236.2–267.4) and every per-trial maximum ≤ dispatch+100 (capture dur 112.2 ≤ 150;
  non_capture dur 223.9 ≤ 300); no amendment to the #146 row-B record; row-17 marker
  unconditional (headroom recorded: windows[0] = 149, lower-bound trip direction,
  49 ms over the floor, not induced at load ≤ 120).

**No numeric bound moves anywhere in this slice.** The build is D1 + the two pins,
the row-17 marker, and documentation with denominators.

## 7. Top risks and their falsifiers

1. **The D1 retry masks a real delivery defect.** A fixture that generates frames
   faster than delivery drains would burn three rigs per trial before reding.
   Falsifier/mitigation: exhaustion still reds; the site-agnostic exhaustion machinery
   (already pinned) proves the red survives. The visible signature — a lane log
   showing `drain-cap` repeated to exhaustion — required the wave-1 fold (critic F1)
   to exist: pre-fold the exhaustion re-raise carried only the LAST attempt's site
   and dropped the composition; post-fold it renders the full site sequence into the
   message (pinned MIXED — drain-cap, priming-validity, drain-cap — and homogeneous).
   Green-path retries are outcome-recorded (`outcome["retry_sites"]`) but NOT
   lane-visible — `pytest -q` swallows the per-trial print — so the lane-health
   signal is exhaustion-only, and the fold is what makes that signal carry the
   composition (wave-1 disclosure, critic F2).
2. **The row-17 override is contested** (slice 1 said "stays unmarked"). The override
   is evidence-based (convention line + xdist environment change post-dating the
   disposition), disclosed here and in the issue comment. Falsifier: the owner's
   explicit call to keep it unmarked — an owner-fired reversal is legitimate and
   recorded as such.
3. **Local quiet host ≠ lane VM** (slice-1 risk 5): the quiet-host rules decide the
   pre-lane posture; the lane counter (R_A) is the ongoing falsifier and continues
   unchanged. A lane red against a locally-held bound is recorded, not re-tuned — the
   D2-trim/D4/D5 triggers name their own reopen paths.
4. **Underpowered lane sample (N_A < 20).** Disclosed in §5.1; no flake conclusion is
   drawn from a partial sample; the counter continues.
5. **The D3 re-band arm weakens the control.** Constrained to M_q ∈ (42, 50] (a quiet
   host within 16% of the bound), ships distributions, leaves separation untouched.
   Falsifier: M_q > 50 (regression arm) or M_q ≤ 42 (hold arm) — the arm cannot fire
   outside its window.
6. **Pin-test runtime.** The D1 integration arm burns one real 2000 ms cap spin
   (~2–4 s in the lane). Accepted, disclosed; the type arm uses a short explicit
   `cap_ms` so the classification itself is pinned cheaply. Wave-1 fold arithmetic
   (critic F3, reviewer's numbers; measured where noted): per cap-hit attempt
   ~2.35 s = 2000 ms cap + ~300 ms construction + ~50 ms belt; an exhaustion reds
   at ×3.0 time-to-red — the wave-1 drain-cap exhaustion arm measured **6.02 s**
   (junitxml time attribute, one local serialized run; three cap spins) against the
   reviewer's ~7 s estimate; a worst-case all-starved lane adds ~3.5 min to the
   ~35 s pytest portion (Evidence A: 12 timing executions, job wall 42–52 s
   including uv sync, pytest portion ~35 s serialized) — the GHA default 360-min
   job timeout is nowhere near conversion. REOPEN TRIGGER: the first timing-lane
   wall ≥ 2x baseline with drain-cap retries visible in the log — retry cost has
   then become a lane-shape change, not a transient.
7. **Measurement-vs-rule ordering** (the pre-commitment residual of §0's protocol).
   Mitigated by the timestamped rules message and the measurer's independence; named,
   not hidden.

## 8. File-level change list

| file | change |
|---|---|
| `tests/integration/test_cross_instance_continuity.py` | D1: cap assert → `TrialInfrastructureError(site="drain-cap")`; `run_trial` docstring carrying-site list gains the site; two pin tests beside the F4 pins (type arm + integration arm). RESOLVED: D3 HOLD (M_q = 38.0 ≤ 42, R_A = 0) — no bound change; the `control_x2` 50 ms ceiling and the `unbuffered_x2` bound are untouched |
| `tests/unit/test_otdp_bridge.py` | row-17 test gains `@pytest.mark.timing` (no band change). RESOLVED: document-only — quiet append_wait_ms 236.2–267.4 inside the [150, 350] window; no band change |
| `drain cap value` | RESOLVED: unchanged at 2000 ms — D_max = 102.3 ms (max over quiet 88.2 / loaded 102.3), 22.6x headroom; the raise refused as an unforced widening (§5.2 D1 kill direction) |
| `.claude/deep-review/2026-09-28-issue241-slice2-reband-decisions-design.md` | this record, commit 1 on the branch, §6 filled |
| `docs/internal/drift-and-obligations.md` | G5 sweep only if a bound moved or prose names the marked-set membership (the CI-map row's "the row-B contention cells" phrasing stays true — row 17 is a row-B clamp test). *Wave-1 fold (adversary F3): the pre-adjudication is superseded — the phrase now reads "the contention and clamp cells", because row 17 moved the marked set's membership and G4 named-set regenerability outweighs the row-B taxonomy reading* |
| issue #241 | outcome comment: per-gate verdicts with numbers, the slice-1 post-merge counter status, the #247 handoff disposition (the promised handoff, now posted), the row-17 override disclosure |

No `src/` bytes. No `standards/` bytes. Every numeric bound in the marked set is
byte-identical after this slice — no §5.2 arm fired, and the measured distributions
that licensed each hold live in §6 Evidence C.
