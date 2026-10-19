# Issue #241 row 22 — F5 saturated window: root cause and the fixture's return-margin fix

**Date:** 2026-10-19
**Slice of:** issue #241 (timing-fragile tests under host load), census row 22 (`test_f5_measurement_seams...`, listed there as "stable (lower-bound-only)")
**Observed failure:** `tests/integration/test_run_activation.py::test_f5_measurement_seams_tick_times_and_saturated_polls` —
`AssertionError: no events landed in the saturated window`, observed 2026-10-17 in 2 of 4
full-suite batteries under `-n auto`; passes in isolation; test code unchanged between runs.
Bulk lane (no `timing` marker), not the serialized timing lane.
**Status:** design only — no code written. Branch named at build time.

**Placement note (the triage rule):** public, deliberately promoted from the `private/`
default. Same content class as the two adjacent public #241 records this design cites
(measurements on an unnamed development host, an honest kill direction — first-class
public per the README), no person/client/bench/commercial identifiers, and the
pre-committed acceptance rule below must be provably pre-committed in git history before
the post-merge window opens — `private/` is gitignored and cannot carry that proof.

---

## 1. Mechanism, confirmed against the code and against runs (not assumed)

F5 drives one saturated-stream scenario and reads four measurement seams. The scenario and
its asserts (`tests/integration/test_run_activation.py:1376-1417`):

1. a commissioned harness (fixture `commissioned`, `:1038-1041`) whose bench declares one
   signal at `poll_ms=50` (`:683-697`, harness default `signal_poll_ms: int = 50`, `:802`),
   so `bench_poll_ns` derives a 50 ms slice (`src/benchweave/control/protection.py:52-64`);
2. the mock adapter's slow-poll mode ON: `module.SLOW_NEXT_EVENT_MS = 100`
   (`:1399`), so every `next_event` poll sleeps
   `max(0.0, min(SLOW_NEXT_EVENT_MS/1000.0, remaining - 0.005))` where
   `remaining = context.deadline_monotonic - context.services.monotonic()`
   (`:246-253`) — i.e. it consumes **nearly the whole poll deadline, then returns an event**
   (the mock's own comment, `:248-250`), leaving a **fixed 5 ms cushion** before the deadline;
3. the run executes the default procedure whose `settle` step is a 200 ms `delay` (`:525`) —
   four 50 ms wait slices, each driving one poll round
   (`src/benchweave/control/coordinator.py:741-752` →
   `src/benchweave/control/stream_host.py:245-258` → `StreamPollEngine.poll_round`,
   `src/benchweave/control/stream_polling.py:107-145`);
4. asserts: `len(tick_times) >= 5` (tick rhythm), `worst tick gap >= 0.040` (a saturated
   round), `landing_times` non-empty (**events land in the saturated window**), engine
   present, and a `next_event` dispatch span `>= 0.040` (an overrun poll recorded).

**The delivery chain, read line by line.** `poll_round` hands each poll a deadline of at most
one slice (`stream_polling.py:129`), calls the bridge's `poll_event`, and — only if the
outcome carries an event — fires `on_event` (`stream_polling.py:139-141`), which is the
test's `landing_times.append` via `_contained_on_event`
(`stream_host.py:260-276`). `poll_event` runs the adapter call inside the bridge's deadline
bracket `_run`/`bounded()` (`src/benchweave/host/otdp_bridge.py:238-254`): a runner timeout
over the remaining deadline, then a post-await check that raises `TimeoutError("late adapter
result")` (`otdp_bridge.py:244`) when the return lands at or after the deadline. That
`TimeoutError` is caught by `poll_event`'s catch-all
(`otdp_bridge.py:1118-1130`) which — unlike a poll-deadline entry refusal — sets
`self._failed`, sweeps every live subscription (`_stream_clear`), and returns
`session_failed=True`. `poll_round` then latches the engine
(`stream_polling.py:134-137`) and every later round returns immediately.

**So one late poll does not lose one event — it kills the whole window.** The first saturated
poll that returns at/after its deadline poisons the session; no later poll runs; the run's
remaining steps still tick (the monitor keeps ticking around dispatches), so the tick-based
asserts pass and the failure lands exactly on `assert landing_times`.

**Fingerprint (deterministic, this designer's worktree off `origin/main` `b905b19a`,
scratch probe, deleted after).** The mock's sleep forced 20 ms past its cushion on the
**unfixed** test — no load applied — reddens byte-identically to the CI failure:

```
AssertionError: no events landed in the saturated window
assert []
tests/integration/test_run_activation.py:1407
```

with the pre-assert stamps showing the chain end to end:

```
{'outcome': 'outcome_unknown', 'engine': True, 'session_failed': True,
 'bridge_failed': True, 'next_event_spans': [50.7], 'ticks': 85,
 'worst_ms': 57.7, 'landings': 0}
```

one cut poll span (50.7 ms — the deadline, not the 45 ms design), session poisoned, zero
landings, run terminalized `outcome_unknown`. True exit 1. This is the signature map: the
observed CI failure IS this mechanism's output.

**Healthy shape (same probe, unmodified, quiet host):** `session_failed: False`,
`next_event` spans 46.7 / 46.7 / 44.8 / 46.6 ms, `landings: 4`, `ticks: 30`, outcome
`passed` (n=2 runs; span range across them 44.8-47.1 ms). The mock's nominal cushion is 5 ms;
the **realized** return margin against the ~50 ms poll deadline is **~3 ms** (span 44.8-47.1
ms against a 50 ms budget; the cushion is computed at the mock's entry, and the span adds the
dict build, the span append, and the bridge's return path).

**Wake-overshoot distribution (the load-sensitive quantity).** A 45 ms pacing sleep measured
on this host under 8 CPU burners, n=40: median overshoot **1.79 ms**, p90 **6.40 ms**, max
**14.80 ms**. Against a ~3 ms realized margin, a substantial fraction of polls return late —
the right order for the observed ~50% per-battery red rate. The repo's own recorded
overshoot class points the same way: M-A's posture names "26.0 ms worst-of-8 at a 10 ms
slice" as the measured overshoot class (`.claude/deep-review/2026-09-23-issue167-run-engine-activation-design.md:436-445`,
its top-risks table at `:484`). A 3 ms margin sits *inside* this repo's own measured
overshoot class; it is not a legitimate execution margin.

**Battery evidence (disclosed denominators).** Baseline reported by the brief: 2 of 4
full-suite `-n auto` batteries red with this signature (2026-10-17). This designer's
pristine full-suite `-n auto` battery on this host: F5 green (1 of 1; the battery also
carried two unrelated collection errors in `tests/standards/` and `tests/contract/` that are
environment-local to a fresh worktree venv and out of scope). The 2-of-4 rate is **consistent
with** "the first saturated poll's wake overshoot exceeded the ~3 ms realized margin":
per-poll late probability of order 0.3-0.5 under full-suite contention, first poll decides
(the poison latches), P(battery red) ≈ that number. **Falsifiers of this root cause, named
so a red can kill it on sight:** a red whose pre-assert stamps show `session_failed: False`
with polls present and zero landings (a delivery-path drop, not a late return); or
`engine: False` (a refused `stream_subscribe`, `stream_host.py:215-230` — a different
mechanism with the same landing signature); or a red at `worst >= 0.040` instead (no wait
slices ran at all). The diagnostic print specified in §4 is what makes these readable on a
red.

## 2. Root cause

F5's survival half — "the saturated slow-poll mode overruns most of each slice **while
SURVIVING**" — rides a fixture constant that is a **fixed 5 ms wall cushion** between the
mock's return and the poll deadline (`test_run_activation.py:253`,
`remaining - 0.005`). The realized margin is ~3 ms once the mock's own overhead is counted.
Host load stretches timer wakes (measured median 1.79 ms / p90 6.40 ms / max 14.80 ms, n=40
under 8 burners; the repo's own recorded overshoot class is 26 ms worst-of-8), so the return
lands at/after the deadline; the bridge then does exactly what it is specified to do — a late
adapter result is not evidence (A06 posture) — cuts it, and `poll_event` poisons the session
(`otdp_bridge.py:1118-1130`), latching the engine (`stream_polling.py:134-137`) so the whole
saturated window delivers nothing.

This is the #241 class verbatim, one level down from the arm-1 rows: **an absolute wall bound
riding a workload the host stretches.** For arm-1 the bound was a dispatch deadline; here it
is the fixture's return cushion. The census's row-22 classification ("stable,
lower-bound-only, no action") missed it because every assert is a lower bound — but
`assert landing_times` is a lower bound on a **count collected inside a host-stretched
window**, and the count can be driven to zero by the deadline race. "Lower-bound-only" is
load-tolerant only when the counted quantity grows with load; here it shrinks.

**The arithmetic that rules out a same-cadence fix (load-bearing).** The poll budget is
`min(now + bench_poll_ns, slice_end)` (`stream_polling.py:129`) — 50 ms at the 50 ms cadence.
Assert 5 requires a `next_event` span `>= 40 ms`; assert 3 requires the return to beat the
deadline. Both together leave at most ~10 ms of return margin (and ~8 ms if the span sits
exactly on the 40 ms floor, which also makes assert 2 marginal). 10 ms is inside the
overshoot class above. **No mock arithmetic stabilizes F5 at the 50 ms cadence** — the
fixture's declared `poll_ms` (the cadence) must rise so the margin is a large fraction of
the budget while the span still overruns most of it.

## 3. Relation to the two merged precedents (and why neither is duplicated)

- **PR #494 (arm-1 in-run budget derivation, `.claude/deep-review/2026-10-17-issue241-row12-arm1-deadline-design.md`)** —
  killed by its own pre-committed rule; its premise (an uncontended reference predicts the
  contended run) was wrong. Not re-proposed here in any form: F5's fix derives nothing from a
  reference and tunes no multiplier.
- **PR #495 (arm-1 deadline-timebase dilation, `2026-10-17-issue241-row12-arm1-rederivation-design.md`)** —
  the timebase move ("the deadline's clock must not be the clock the host load stretches")
  is the right doctrine for **scaffolding deadlines that must never bind**. It does not
  transfer to F5, and this is the design's central judgment:
  **arm-1's dispatch deadline was pure scaffolding; F5's poll deadline is the property under
  test.** F5 asserts a poll that *overruns most of its slice* still *returns inside that
  slice's budget*. Dilating the deadline timebase would decouple the bridge's enforced budget
  from the slice (the cut would land seconds later while the engine still slices at 50 ms), so
  the assert would pass even for a poll that returns many slices late — the check's
  sensitivity to the budget race is exactly what the RED control exercises (§8), and dilation
  relocates that sensitivity to a budget the test no longer means. A *small* dilation is just
  the cushion constant by another name.
  So this slice takes #495's own designated **fallback (c)** — "sizing the constant against
  the largest legitimate execution" — which #495 recorded as legitimate but inferior for
  arm-1. Here it is the only sound option, and its sizing basis is measured: the fixture's
  saturation is re-cut at a cadence whose return margin is ~3x the measured local overshoot
  max and ~1.8x the repo's recorded overshoot class.

## 4. The fix (minimal first increment)

One file: `tests/integration/test_run_activation.py`, the F5 test body only. **The five
asserts stay byte-identical; no `src/` byte moves.** Four coupled edits:

1. **F5 constructs its own harness with a 200 ms signal poll** (the shared `commissioned`
   fixture is parameterless, `:1038-1041`, so the kwarg needs a local construction — the
   `tmp_path` shape test_f3/test_f4 already use). Signature
   `commissioned: _CommissionedHarness` → `tmp_path: Path`; body adds
   `harness = _CommissionedHarness(tmp_path, "req-activation-f5", signal_poll_ms=200)` and
   calls `_coordinator(harness, run_id, QUOTA_LIMITS)`. This is the ONE knob the arithmetic
   in §2 names: `bench_poll_ns` becomes 200 ms, so the poll budget is 200 ms.

2. **The saturation constant follows the budget:** `module.SLOW_NEXT_EVENT_MS = 100` →
   `= 150` (`:1399`), comment `# slice is 50 ms -> ~45 ms per poll` →
   `# slice is 200 ms -> ~150 ms per poll`. The mock's own arithmetic (`:253`) is
   **untouched** — with `remaining ≈ 199 ms` the `remaining - 0.005` cap no longer binds, so
   the sleep is 150 ms: **75% of the budget ("overruns most of each slice") with ~45 ms of
   return margin** (25% of the budget).

3. **Diagnostics before asserts (the #495 §4.1 lesson — a print after an assert is
   unreachable on exactly the runs it exists for).** Capture
   `record = coordinator.start_run(...)`, and before the first assert print one line carrying
   the classification stamps: `outcome`, `engine` present, `session_failed`, the `next_event`
   span ms list, tick count, worst gap ms, landing count. The lane replays captured stdout
   for failing tests, so every future red is classifiable on sight (late-poll poison vs
   refused subscribe vs no-window).

4. **Docstring sentence** (the only prose): name the 200 ms slice, the 150 ms poll (75% of
   the budget), and the ~45 ms return margin as the fixture's saturation constants.

**Parameter arithmetic, pre-committed.** Budget 200 ms; sleep `min(150 ms, remaining − 5 ms)`
= 150 ms; span ≈ 152-159 ms measured (n=5, this host, under 8 burners); realized return
margin ≈ 40-48 ms = **~3.2x the measured local overshoot max (14.8 ms, n=40)** and **~1.85x
the repo's recorded overshoot class (26 ms)**; gap/span evidence 151-168 ms against the
`>= 0.040` literals (**3.8x**). The delay step (200 ms) is exactly one slice at the 200 ms
cadence → one saturated round per window (see D1). The mock's 5 ms cushion is retained as the
fallback cap for `SLOW >= remaining − 5 ms` and is now non-binding at this cadence (see D5).

**Measured proof of the fix (design-time, this designer's worktree).** The fixed body run 5
consecutive times under 8 CPU burners: 5/5 green (`session_failed: False`, spans 151.1 /
151.2 / 152.8 / 154.7 / 159.2 ms, `worst_ms` 152.4-167.7, `landings: 1` each, `ticks: 19`,
outcome `passed`). **RED control on the fixed code:** the same body with the mock's sleep
forced 80 ms past its cushion (past the 200 ms budget) reds with the exact signature,
**true exit 1** (unpiped), stamps `session_failed: True`, one 200.3 ms cut span,
`landings: 0` — the fix did **not** numb the check's sensitivity to a late poll. Two full-suite
`-n auto` batteries with the fixed body in place (real edit, not a scratch copy) also read
F5 **green in 2 of 2** (`--junitxml`); their suite exit was 1 from two unrelated collection
errors (`tests/standards/test_scenarios.py`, `tests/contract/test_win_core_partition.py`)
that are present in the pristine battery too and are environment-local to a fresh worktree
venv — disclosed, out of scope, and not this slice's evidence.

## 5. Alternatives weighed

- **(a) Deadline-timebase dilation (PR #495's §4.2 shape).** Rejected with the §3 argument:
  F5's deadline is asserted, not scaffolding; dilation decouples the enforced budget from the
  slice and numbs the survival assert. It would also need a services-clock split that
  `build_run` does not expose (`clock = SystemClock()` feeds both the engine and the services
  clock, `src/benchweave/interfaces/app.py:758, 808-811`) — production bytes, or private
  surgery on the host's services object from the adapter fixture (a layering break that
  would also split the M2 timebase identity R12 pins).
- **(b) Widen the cushion only, keep the 50 ms cadence.** Ruled out by the §2 arithmetic:
  span ≥ 40 ms on a 50 ms budget caps the margin at ~10 ms — inside the measured overshoot
  class. Would flake again.
- **(c) Soften the saturation (sleep 50-60% of the budget) at the 50 ms cadence to buy
  margin.** Rejected: the span assert (`>= 0.040`) would then sit at its own floor (40.0 ms)
  or fail — the check's saturation gate goes marginal or red. That is a scenario weakening
  wearing a margin improvement.
- **(d) Make the mock return before sleeping / land events from a fast poll.** Rejected: the
  landing must occur *while* the poll mode is saturated — a fast-poll landing launders the
  assert ("no events landed in the saturated window" would hold vacuously). The rule
  "stabilization never weakens what a check asserts" forbids it.
- **(e) Extend the settle step via `steps=` to get 3 rounds at the 200 ms cadence.** Better
  round fidelity, ~20 lines of fixture copy; deferred as D1 (no assert needs ≥2 rounds).
- **(f) Restate `worst >= 0.040` as a slice fraction (0.8 × slice).** Rejected and disclosed:
  at the 200 ms cadence 0.8 × slice = 160 ms, above the measured 152-168 ms gaps — it would
  tighten the assert beyond what the fixture delivers and marginal-fail. The literal stays.

## 6. What this increment defers

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | round fidelity: one saturated round per window at the 200 ms cadence (the delay step is one slice), vs four today | follow-on work on issue #241 | the M-A measurer lane reporting the smoke no longer exercises multi-round rotation; then extend `settle` via `steps=` to 600 ms (3 slices, same slack) |
| D2 | the residual is still an absolute wall margin (~45 ms, not a timebase separation) | follow-on work on issue #241 | a post-merge red with the landing signature whose stamps show a span past the budget (wake latency > ~45 ms): escalate to the lane/runner class (PR #495's K2 posture — **not** more slack), or re-cut at a coarser cadence |
| D3 | census row 22's "stable (lower-bound-only), no action" classification of this test is wrong — its landing assert is load-fragile through the fixture's deadline race | documentation on issue #241 (comment at PR time; no code) | n/a — a correction, carried by this record |
| D4 | the assert-message overclaim already present: `worst >= 0.040`'s message says "saturated rounds absent", but the wait-slice rhythm satisfies that literal at any cadence even with zero saturation — the real saturation guard is the span assert | follow-on work on issue #241 (claim discipline, G4) | a review finding on the message; restating it is a claim fix, not a stabilization |
| D5 | the mock's `remaining - 0.005` cushion stays a razor-thin fallback for any future `SLOW_NEXT_EVENT_MS >= remaining - 5 ms` at a small cadence — the flake class is latent in the fixture | follow-on work on issue #241 | a sibling test adopting `SLOW_NEXT_EVENT_MS` at a cadence where the cap binds again |
| D6 | the run-activation step-deadline rows (census rows 8/9/18) and the rest of row 22's family | issue #241's standing per-row loop | the row's own trigger |

## 7. Invariant, cross-surface, and measurement-semantics impacts

- **Invariants: none touched.** No `src/`, `standards/`, or fixture-lattice bytes move.
  CTL-8 (monitoring wraps every dispatch, slices every monotonic wait at the bench poll
  cadence, single-threaded on the injected clocks) is exercised exactly as before — the
  cadence it slices at is a bench property the fixture already parameterizes
  (`signal_poll_ms`), and the change is to the fixture's declaration, not to the derivation
  (`bench_poll_ns` unchanged). M2 timebase identity untouched — no clock surgery (contrast
  §5(a)). STO/CON/REG untouched. No on-disk format, schema, MCP/REST/CLI surface, operator
  doc, device-developer guide, vendored standard, or SDK surface moves.
- **Drift obligations:** none fire. The `timing` marker partition is untouched (this test
  stays in the bulk lane); `docs/internal/drift-and-obligations.md`'s lane row describes the
  lane, not per-test fixture constants; no obligation in that doc names this test's cadence.
- **Measurement semantics — the repository rule, applied explicitly.** Stabilization never
  weakens what a check asserts. The five asserts are **byte-identical** (the unchanged-assert
  control in §8). What changes is the fixture's *scenario* arithmetic: the bench's declared
  `poll_ms` (50 → 200) and the saturation constant (100 → 150). The survival property remains
  under test and remains sensitive — the RED control proves a late poll still reddens. The
  saturation gate remains real — a regression that stops saturating (e.g. the constant
  dropping to 30) fails both the span assert (30 < 40) and the gap assert. Two disclosed
  softnesses, both pre-existing and not introduced here: (i) the gap/span literals (40 ms)
  were calibrated as 80% of the 50 ms slice and are 20-25% of the 200 ms budget now — they
  still gate saturation absolutely, just not slice-relatively (restating them as a slice
  fraction is alternative (f), rejected); (ii) the gap assert's message overclaims (D4).
  The M-A regime class is preserved: M-A's tick-gap posture is "≤ ~2.6× slice" with
  "S_eff incl. sleep overshoot" (`2026-09-23-issue167-run-engine-activation-design.md:436-445`);
  the fixed gaps are 0.76-0.84× the slice, in class alongside today's ~0.9×, and the
  measurement's `S_eff` component (sleep overshoot) is now 25% of the budget instead of 10% —
  the same regime, at a coarser commissioned cadence.

## 8. Proof plan and builder pre-merge obligations

1. **Signature map on the UNFIXED code (done, deterministic, §1):** the mock's sleep forced
   20 ms past its cushion reddens byte-identically to the CI failure, zero load. Conclusive
   for "this mechanism produces that failure".
2. **Mechanism fingerprint (done, §1):** the forced-late run's stamps show
   `session_failed: True`, one cut `next_event` span, zero landings, `outcome_unknown`.
3. **Healthy shape + margin arithmetic (done, §1/§4):** quiet spans 44.8-47.1 ms on a 50 ms
   budget (~3 ms realized margin); measured wake-overshoot distribution (median 1.79 /
   p90 6.40 / max 14.80 ms, n=40, 8 burners) and the repo's recorded 26 ms overshoot class.
4. **Fix verification (done, design-time):** 5 consecutive runs of the fixed body green under
   8 CPU burners (spans 151.1-159.2 ms, 1 landing each, sessions alive), plus 2 consecutive
   full-suite `-n auto` batteries with the fixed body in place — F5 green in 2 of 2 (read
   from `--junitxml`; those batteries' suite exit was 1 from two unrelated, pre-existing
   collection errors noted in §4).
5. **RED control on the FIXED code (done, design-time):** forced 80 ms past the budget reddens
   with the exact signature, true exit 1, stamps `session_failed: True` / `landings: 0` —
   sensitivity preserved.
6. **Unchanged-assert control (builder):** the diff moves no asserted magnitude — the five
   assert lines byte-identical (only `entry = host.devices[DEVICE_ID]` relocates above the
   print).
7. **Load reproduction (attempted, honest negative):** 1 pristine full-suite `-n auto`
   battery on this host stayed green for F5 (1 of 1); the brief's 2-of-4 is the evidence
   base. This host did not reach the CI contention regime; no claim of local reproduction is
   made.
8. **Builder pre-merge runs:** 5 consecutive full-suite batteries with the fixed body in
   place, the test green in every one, read from `--junitxml` (not a summary line):

   ```
   UV_PROJECT_ENVIRONMENT=venv uv run pytest -n auto -q --junitxml=/tmp/f5-fix-bN.xml
   ```

   plus the two scratch-copy controls above (§1 signature map and §4/§5 RED control), each
   with its true exit code, then the FAST lane per CLAUDE.md §3 (bare `uv run ruff check .`,
   fresh-cache bare `uv run mypy`, focused `uv run pytest` for this file) and the full
   battery before push.

## 9. Pre-committed acceptance rule (written before any post-merge number is read)

**Metric:** bulk-lane executions in which `test_f5_measurement_seams_tick_times_and_saturated_polls`
runs (the observed condition: full-suite `-n auto`), classified for the landing signature
(`AssertionError: no events landed in the saturated window`). Local runs satisfy nothing
post-merge; every clause references CI bulk-lane executions. Baseline for effect size: 2 of 4
batteries red (50%, the brief's observation). Nesting: the slice-4 live window rule
(≤2 red executions per 40, every red in a named family) continues; this rule nests inside it.

- **Ship:** 5 consecutive pre-merge full-suite `-n auto` runs green (§8.8), AND zero
  landing-signature reds in the **40-execution** post-merge window, AND the live ≤2/40 family
  rule holds. Effect size, stated up front: 50% observed → 0/40 post-merge (0/40 places a
  ~7% 95% upper bound on the residual rate; 2^-40 rejects the 50% baseline decisively).
- **Kill (any one fires):**
  - **K1 — the fix failed:** any landing-signature red in the window. Read the red's §4
    stamps first: a span past the 200 ms budget (wake latency > ~45 ms) is D2's escalation
    trigger (lane/runner class — **not** more slack, per PR #495's K2 posture); a span inside
    the budget with zero landings is a delivery-path defect and reopens the mechanism read.
  - **K2 — the fix numbed the check:** the RED control (§8.5) fails to red on the scratch
    copy (the forced-late return still lands). The slice is then a weakening and must not
    ship; revert and re-derive.
  - **K3 — the mechanism read is wrong:** a red whose stamps show `engine: False` (refused
    `stream_subscribe`) or `session_failed: False` with polls present. The fix addresses the
    wrong cause; re-open from the stamp timeline, never from the margin arithmetic.
  - The live rules inherit: any red of a touched mechanism; ≥3/40 overall.
- **Underpowered, not conclusive (decide nothing; collect and extend):** fewer than 40
  executions sampled when a candidate red arrives; the raw Actions log truncated before the
  failing assert's identity and the §4 stamps are readable (pull the raw log BEFORE any
  rerun — the AR-7 lesson); a job-level timeout kill (lane-infra, never a family red); or a
  red whose captured stdout lacks the §4 stamps (only possible if the prints themselves
  failed — a build defect: fix the prints, restart the window). A red classified without the
  stamps is automatically underpowered.

**Diagnostic evidence requirement, named:** every red in this window must be read from a raw
log that contains the §4 pre-assert stamps for the failing test.

## 10. Top risks, each with its falsifier

- **R1 — the ~45 ms margin is still absolute (D2).** Falsifier: any K1 red whose stamps show
  a span past the budget. Pre-committed response is escalation to the lane/runner class, not
  more slack — 45 ms is already ~1.85x the repo's recorded overshoot class and one test
  owning a larger slice budget starts to own the lane's wall clock.
- **R2 — the mechanism read is wrong for the natural flake.** Falsifier: a K3 red (stamps
  show a refused subscribe, or a live session with polls present and zero landings). The §4
  stamps discriminate on sight; the signature map only proves this mechanism *can* produce
  the failure, not that it always does.
- **R3 — regime fidelity (one round per window, 75% saturation).** Falsifier: the M-A
  measurer lane reporting the smoke no longer exercises the regime it certifies (D1's
  trigger), or a review ruling that "saturated" must mean ≥90% of the budget — which at 200 ms
  would leave only ~20 ms margin and re-open R1; the two cannot both be had at this cadence
  and the trade is disclosed here so the ruling is made against the arithmetic.
- **R4 — a reviewer reads the cadence change as weakening.** Counter-evidence in the diff:
  the five asserts byte-identical (control 8.6); the RED control proves sensitivity (8.5);
  the span assert still fails a non-saturating regression; gap/span evidence is 3.8x the
  literals. What moved is a fixture declaration the harness already parameterized.
- **R5 — the latent razor cushion in the mock (D5).** Falsifier: a sibling red with this
  signature at a cadence where `SLOW >= remaining − 5 ms` binds again. The mock's comment
  (`:248-250`) names the regime; this record names the trap.
- **R6 — the gap assert's message overclaims (D4).** Disclosed as pre-existing; falsifier for
  "the message is fine": any future red at that assert caused by an absent window rather than
  an absent saturated round.

## 11. Tier and the Step-1 keyword scan (#254)

Expected diff: this record (new `.md`) plus the `tests/integration/test_run_activation.py`
F5-body edit of §4 (signature parameter, one harness construction with
`signal_poll_ms=200`, the saturation constant and its comment, a pre-assert diagnostic
print, one docstring sentence, one call-site argument).

**Tier: Tier 3 — deep, mandatory second adversarial reviewer (G6).**
**Rule that triggered it:** the Step-1 keyword rule — "the diff text contains any of: …
`protection`" — first-match-wins, text-based by design. The whole expected diff (docs and
code alike) carries **one** occurrence of that literal: a `file:anchor` citation to
`src/benchweave/control/protection.py:52-64`, the home of the poll-cadence derivation
`bench_poll_ns` §4's fix names. Per the rubric's own interplay paragraph ("a docs-only
change whose diff text merely mentions a protection-related key … still takes the Tier-3
lane"), a mention fires the rule regardless of file type or of whether the text carries
protective behaviour — so this slice takes the Tier-3 lane even though the hit is a module
path and the diff touches neither protective behaviour nor any Tier-3 path.

Disclosed for the review's independent re-derivation: the **path** rules alone give Tier 2
(a test-code change under `tests/` plus a docs/record file — no `contracts/`, `standards/`,
persisted-format, registry, fixture-lattice, dependency, or submodule match). The gap
between the two readings is exactly the one citation above; if the repo's convention decides
a path citation to an existing module is not "the diff text carrying the key", the downgrade
to Tier 2 is a one-line reviewer note. This record states the **conservative** tier so that
no "stated tier disagrees with the rules" finding can arise from it, and so the adversarial
pass runs rather than being argued away. The G6 two-lane adversary applies either way — the
standing 2026-09-24 R3 rule for #241-family timing slices already requires it.

### 11.1 Scan result (mechanical, over the whole expected diff — this record's full text plus the expected added lines)

Measured with the issue-422 method (`grep -oiw <kw> <record> | wc -l`, per keyword; this
record's text does not spell the keyword list out, so no legend exclusion is needed), counts
in the rubric's Step-1 order — **1: 0 · 2: 0 · 3: 0 · 4: 0 · 5: 0 · 6: 0 · 7: 0 · 8: 1** —
first-match-wins fires on the eighth. The expected test-file **added** lines score 0/8
independently (one integer kwarg, one integer constant, a print, and prose — no concurrency
primitive, no digest arithmetic, no persistence surface), so the single hit is this record's
own path citation. Mechanically scanned 2026-10-19; the review re-derives over the real
diff, where hunk CONTEXT lines in the test file carry the module's own embedded adapter
source (its library imports) — already disclosed by the rubric's own note, and not added
lines. If the real diff's added lines carry any of the eight, the Tier-3 lane stands
unchanged and the builder re-runs this scan pre-PR and records it.

Method note, for the record's honesty: the mechanism prose in §1 paraphrases the run-loop
library names ("the pacing sleep", "the timer wake", "the runner's deadline cut") rather
than spelling them — the convention the two adjacent #241 records used (their §10.1/§12.1)
— and the precise mechanism is carried by `file:line` citations instead. That convention is
why the count is 1 and not higher; it is disclosed here rather than leaned on, because the
one remaining hit is load-bearing for a build agent (it is where `bench_poll_ns` lives) and
eliding it to reach 0/8 would be the wrong trade.
