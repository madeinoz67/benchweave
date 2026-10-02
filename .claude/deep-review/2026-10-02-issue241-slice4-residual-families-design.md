# Issue #241 slice 4 — the residual flake families: pace-allocated poisoning, in-run-relative ceilings, the classified poll residual

Design record for the fourth stabilization increment of the #240 red-lane
class. Tree: `origin/main` at `0e6774e` (briefed `2970d68`; main moved — the
delta is entirely the #298 ui-html train, `git diff --stat 2970d68..0e6774e`
touches no timing path; both rig files are byte-identical to `0f3b786`, the
commit the belt red landed on, so the working tree IS the code under test).
Branch named at build. Standards tripwire: no `standards/` bytes, no version
strings (`git diff origin/main...HEAD -- standards/` expected empty, checked
at push).

**Pre-commitment protocol (slices 2–3 disclosure, unchanged).** The lane
counter and failure logs below were collected BEFORE this record was written.
The post-merge acceptance rule (§5.2) was fixed before any post-slice-4 number
can exist by construction. No mechanism below was sized from a number it also
promises to deliver.

## 0. State established from the runner, not assumed

### 0.1 The slice-3 kill arm has FIRED — slice 4 is the rule-mandated response

Slice 3 pre-committed (its §5.2): over the first 40 `timing`-lane executions
post-merge, SHIP at ≤2 red executions with every red in a named residual
family; KILL at ≥3/40 **or any single red of a mechanism slice 3 touched**.
The window opened at the merge run itself (`0f3b786`, run 36867869659,
2026-10-01T13:19Z). The count, re-derived for this design from the ci workflow
run list (every run executes the `timing` job; PR runs and main pushes both
count per the rule's unit; a re-run attempt is its own execution):

| # | run | when (Z) | kind | timing result |
|---|---|---|---|---|
| 1 | 36867869659 | 10-01 13:19 | push main (merge #324) | **RED** — `test_belt_swap_still_audits_gen1_x1_floor` `AssertionError: {}` |
| 2 | 36868936614 | 10-01 13:28 | push main (merge #325) | green |
| 3 | 36869092720 | 10-01 13:29 | push main (merge #326) | green |
| 4 | 36882484249 | 10-01 15:12 | PR #302 | green |
| 5 | 36883076723 | 10-01 15:17 | push main (merge #327) | green (its `gates` job failed — §0.5) |
| 6 | 36883152275 | 10-01 15:18 | PR | green |
| 7 | 36883625680 | 10-01 15:21 | push main (merge #328) | green |
| 8 | 36908741739 att.1 | 10-01 ~18:41 | PR #329 | **RED** — `test_axis_trials_complete_all_four_axes[capture-buffered]` retry composition exhausted (pre-flight-staleness -> pre-flight-staleness -> dispatch-door) |
| 9 | 36908741739 att.2 | 10-01 22:31 | PR #329 re-run | **RED** — `test_second_dispatch_lock_block` 258.7 ms vs the 200 ms ceiling |
| 10 | 36937239058 | 10-01 22:48 | PR #330 | green |
| 11 | 36937617333 | 10-01 22:52 | push main (merge #330) | green |

**N = 11 executions, R = 3 red.** 3 ≥ 3/40: the count kill fired. Separately,
red #1 is a red of a test slice 3 itself added (the belt-swap pin from its
refute fold A) — the mechanism-red kill condition — and reds #1 and #8 lie in
NO family slice 3 named (its named residuals were the sequential-model bands
and the sustained-stretch shape), so the SHIP clause's named-family condition
is independently breached. The rule did exactly what it was written to do:
reopen #241 with the failing logs as the next slice's Evidence A. This slice
is that response.

Counting clarifications, so nobody re-derives the window differently:

- **The 10:56 red (36852240046) is NOT in this window.** It is pre-merge
  (slice 3 merged between 10:56 and 13:19); it is slice 3's own Evidence A
  row 7, and the shipped tree already cites it BY RUN ID in the de-clocked
  drain-cap pin's docstring as the third of its three false reds. It is
  dispositioned. The brief carried it as "signature not yet pulled"; pulled,
  it resolves to an already-fixed pin.
- **PR #329's two attempts both count** (each is a timing-job execution), and
  red #9 — the sequential family — is a NAMED residual (slice 4's lane), so it
  is the one red of the three the old rule would have tolerated.
- **The 15:17 gates trio is NOT in this window** (different lane; that run's
  timing job was green — job-level inspection). Its disposition is §0.5.

### 0.2 The belt-swap red diagnosed: pace-ladder poisoning is construction-ordered, and load-added retries shift it — a pin-fixture defect, NOT a belt gap

The merge-run failure (`AssertionError: {}` at
`test_cross_instance_continuity.py:2376`, full traceback pulled from run
36867869659): the nested real axis test DID raise the expected "X1 floor"
AssertionError (the `match=` and the `x1_ms` containment both held — the
traceback starts at the LATER assert), but `_BELT_GENERATION_RUNS` printed as
`{}` — empty. No belt generation was certified for ANY key during the nested
call: the red came through `_assert_x1_floor`'s direct path, not the swapped
verdict, and the pin's "the belt really swapped" post-condition failed.

Mechanism, established from the code (all line numbers at `0f3b786`):

1. The pin poisons gen-1 through a pace ladder over the first five
   `ARigAdapter` constructions — `(0.55, 1.0, 1.9, 0.75, 1.45)`, indexed at
   pace time by `adapters.index(self)`: **construction order**
   (`test_belt_swap_still_audits_gen1_x1_floor`, :2362–:2380).
2. `run_trial` builds ONE rig per attempt (`_run_trial_once` per attempt,
   :1123–:1132): every infrastructure retry is an extra `ARigAdapter`
   construction that consumes a ladder slot.
3. The designed shape needs BOTH the 0.55-paced trial (below the 150 ms X1
   floor: `dispatch_ms - 50`, `_ARM_DISPATCH_MS["non_capture"] = 200`) AND the
   1.9-paced trial (past the 350 ms upper band: `dispatch_ms + 150`) inside
   gen-1's five measured trials: the band breach certifies the fresh
   generation (`_BELT_GENERATION_RUNS[key] == 1`), the clean fresh draw is
   returned, and gen-1's floor audit reds through the swapped verdict.
4. **The elimination argument.** `ARigAdapter._pace` is deadline-driven and
   converges to its target (:262–:275) — a 1.9-paced MEASURED trial's
   acquisition takes ≥ ~380 ms, so its `x1_ms` and `dispatch_duration_ms`
   both exceed the 350 ms band BY CONSTRUCTION, load or no load. A band
   breach therefore guarantees a certification entry. The observed run has an
   EMPTY generation map — so the 1.9-paced adapter never paced a measured
   trial. The only way that happens is a construction-order shift: an
   infrastructure retry discarded the 1.9-position rig (or a rig before it)
   pre-acquisition, and gen-1's measured five drew a floor-only allocation
   (e.g. 0.55, 1.0, 0.75, 1.45, healthy). The belt then correctly engaged
   nothing — no band breach — and gen-1's floor audit correctly redsed on the
   0.55-paced trial. Which is exactly the observed `{}`: floor red, zero
   certifications.
5. **The belt and the floor behaved to spec.** The floor is "asserted, never
   belt-evaluated" (:1842–:1854); a floor-only violation with no band breach
   redding directly is the specified behavior. What failed is the PIN's
   post-condition — its fixture is load-fragile in a way its subject is not.

This is load-shaped (the shifting constructions are infrastructure retries
under the same chronic-load regime as §0.1's reds #1/#8 — the observed
exhaustion composition pre-flight-staleness ×2 shows exactly the retry
pressure), not a belt gap. It also cuts BOTH ways: the same shift can
discard the 0.55-position rig, in which case the pin passes without its
designed floor red — a silent exercise-nothing shape. The pin is fragile in
the red direction and vacuous in the green direction; both are fixed by the
same change (§1.1).

### 0.3 The exhaustion red classified: chronic starvation, honest by doctrine

PR #329 attempt 1: the axis trial exhausted its fixed three-attempt budget
with composition `pre-flight-staleness -> pre-flight-staleness ->
dispatch-door`. This is the F4 doctrine's designed terminal state — "a
chronically starved host must not ship all-green on the retry crutch"
(axis-test docstring), exhaustion still reds. Nothing to fix in the rig: the
three-attempt budget is the bounded authority, and widening it is the
retry-time-multiplier deferral whose reopen trigger (timing-lane wall ≥ 2×
baseline) has NOT fired (recent lane test portions run ~45–66 s against the
~49 s slice-1 baseline). The disposition is to NAME the family — chronic-
starvation exhaustion — in the residual register so the §5.2 accounting can
tolerate it honestly instead of discovering it at the next kill count.

### 0.4 The lock-block red: the sequential family's last absolute ceiling

PR #329 attempt 2: helper wait 258.7 ms vs `BUDGET_MS + TOLERANCE_MS = 200`
(census row 3's exact PR-#240 signature, 302.4 ms then; quiet 56.2 ms). D4's
letter deliberately kept this one band absolute as "the family's one
real-clock representative"; D4' (folded by trigger in slice 3) relativized
the family's OTHER two ceilings (monitor-gap to realized dispatch +
tolerance; queued-run to measured run-1 + 300) and named the mechanism: the
absolute ceiling is the load-fragile form. Red #9 is the second in-lane red
of the absolute band since that fold decided to keep it — the D4' pattern's
own trigger shape, now on the last member. §1.2 finishes the family.

### 0.5 The 15:17 gates trio: rows-8/9 class-recurrence #1, outside this slice's lane

Run 36883076723 (merge #327): `gates` failed on three run-path smokes —
`test_issue146_e2e_thirty_runs_through_the_real_activation_path` (run 12 of
30: `outcome_unknown` vs `passed`), `test_generate_runs_three_run_smoke`
(`execution_error`), `test_timing_generator_smoke_against_in_process_gateway`
(`outcome_unknown`). The 15:21 rerun (36883625680) is green. All three are
outcome degradations of the real run path under `-n auto` — the rows-8/9
step-deadline class ("the degradation is honest evidence-over-assertion
behavior; load-isolate only on recurrence"), NOT the port-bind shape the
2026-10-01 multi-agent-host observation logged, and NOT ms-bound asserts
(the D5 marker-rot trigger does not fire). Two of the three ids are not even
in the census (row 24's issue146 entry is the retired calendar class; the
other two were never inventoried) — this is class-recurrence with new ids,
once, self-resolved in four minutes.

Disposition: **defer with a sharpened trigger and a pre-specified payload**
(§2 deferral table D-gates). Reasons: (a) it is a different lane with no
pre-committed window — folding it in would balloon this slice into CI-shape
surgery with its own partition and cold-union proofs; (b) the honest-outcome
doctrine says these reds are correct behavior — the runs genuinely degraded;
(c) one class-recurrence that cleared on immediate rerun is exactly the
evidence shape the census said to wait on ("load-isolate only on
recurrence" — recurrence, not first new-id expression). The sharpened trigger
and payload are in the deferral table; the issue comment documents the
occurrence.

## 1. Mechanism — four families, four dispositions, one doctrine

The doctrine is unchanged (F4, slices 1–3): transient host starvation retries
on a fresh unit with the retry recorded; chronic starvation exhausts and
still reds; nothing about the measurement semantics moves; no numeric bound
is widened silently — every moved ceiling names what it still proves and
where its cut-proof lives.

### 1.1 Pace-allocated poisoning (fixes the belt-swap pin; class-dead after)

The ladder stops indexing by construction order and indexes by **paced
order**: the pace hook keeps its own list, appends an adapter on its FIRST
pace call, and indexes that list. A rig discarded before its acquisition
(pre-flight staleness, priming, a drained door reject — every carrying site
that precedes the acquisition) never paces and consumes no slot, so the five
measured gen-1 trials draw the designed ladder regardless of how many
attempts starved in front of them. The counting `__init__` stays (it is the
cleanup belt's registry). What still shifts, disclosed: an attempt discarded
AFTER pacing began (a mid-acquisition dispatch-door death) consumes a slot —
residual, named in §7 risk 2, sized by today's evidence as the rarer
presentation (the observed exhaustions starve pre-acquisition). The RED arm
(§5.1 AR-1) is mutation-style: with the pace-order change neutralized (back
to construction order) plus one injected pre-acquisition discard, the
designed allocation breaks and the arm reds — proving the allocation rides
pace events, not constructions.

Nothing the pin PROVES moves: the real axis test still runs, the swap still
happens through the real belt, gen-1's floor still reds through the swapped
verdict, and the swap counter is still asserted exactly 1.

### 1.2 In-run-relative ceilings: the D4' pattern finishes the sequential family (D-rowB moved to PR #329 by the pre-freeze amendment)

**Lock-block** (`test_second_dispatch_lock_block`), mirroring monitor-gap's
D4' fold exactly:

- The capture thread's result gains the cut-proof assert
  `status is OperationStatus.UNKNOWN` — the deterministic, load-immune
  evidence that `bounded()` cut the capture at budget. Today this test's
  ONLY cut evidence is the absolute ceiling; after this change the cut has
  its own assert and the ceiling is free to reference what the run realized.
- The ceiling becomes `wait_ms <= realized_dispatch_ms + TOLERANCE_MS` with
  `realized_dispatch_ms` stamped in-run by the capture thread (start/end on
  the monotonic clock). The helper blocks on a lock the capture holds, so
  its wait cannot exceed the realized dispatch plus its own refusal path —
  under load both stretch together and the ratio holds (observed: 258.7 ms
  wait inside a run whose dispatch realized comparably; quiet 56.2 ms inside
  ~60–100 ms).
- The floor `wait_ms >= 20` stays (a lower bound on a load-inflated
  quantity — load-safe), and the ordering asserts (helper result ERROR, the
  "fresh opened bridge" refusal) stay verbatim.
- The band form becomes a shared helper with a synthetic worst-case pin, the
  `_queued_delay_breaches` precedent: a wait past realized + tolerance must
  breach; the honest shape must clear.
- Disclosed interaction, unchanged: the helper's own dispatch deadline stays
  `BUDGET_MS + TOLERANCE_MS`; both observed red presentations (258.7,
  302.4 ms waits) still returned the refusal message, because the door's
  latched-failure check is evaluated before the deadline branch — the
  observed logs are the evidence, and the docstring says so.

What the family still proves, stated: the floors and UNKNOWN statuses carry
the cut and blackout proofs deterministically; the ceilings carry the
proportionality disclosure (wait/gap/delay ≈ the realized quantity); the
family remains real-clock end to end — it is the DISCLOSURE rig (its module
docstring: the numbers characterize the globally serialized model; row 1's
live reopen arm reads them), not an order-semantics family.

**D-rowB — POINTER (pre-freeze controller amendment): D-rowB is executed by
PR #329 (commit e96e08b, refute-folded there); it lands ahead of this
slice; this slice carries no row-B change.** The text below is #329's
payload context, retained unedited; this slice touches no row-B bytes
(`test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot`,
slice-3's register row, trigger-corroborated by #207's two Windows
observations 1724.55/1734.19 vs 1700):

- The test gains the recording `busy_timeout_window` wrapper (the in-tree
  shape at `tests/unit/test_otdp_bridge.py:2703`/`:2752` — a context manager
  that appends each window's ms and delegates), so the clamp value the
  bracket actually computed is legible in-run: exactly one window per
  dispatch (asserted), its value the reference.
- The ceiling `1300 <= busy_wait_ms <= 1700` becomes
  `busy_wait_ms >= 1300` (floor, load-safe) AND
  `busy_wait_ms <= recorded_clamp_ms + 300` (the +300 slop `fail_delta_ms`
  already uses at :2685). Expected quiet clamp ~1500 → ceiling ~1800, which
  absorbs the corroborated 1724.55/1734.19 shapes while a shortened or
  mis-derived clamp tracks its own value down and reds.
- A synthetic band-form pin refuses a busy-wait past clamp + 300 and clears
  the honest shape, pinning the form against future widening.

### 1.3 The classified poll residual: TIMEOUT-flavor drain-poll poison joins the carrying sites (owner fork, recommended)

Slice 3's named residual, from `_poll_found_dead_session`'s own disclosure
(:1007–:1019): a drain poll whose event delivery outran the poll's 50 ms
deadline under host stall poisons the session with a TIMEOUT-flavor refusal —
starvation-shaped, but currently non-retryable (the predicate matches
INTERNAL_ERROR only), so it reds straight through as a plain assert. One
live observation is already logged (slice-3 outcome comment). The sibling
flavor — the dead-session door reject — is already the retryable
`drain-poll-door` site (:865–:869).

Payload: the drain-poll raise site classifies the TIMEOUT-flavor poison as
`TrialInfrastructureError(site="drain-poll-timeout")`, leaving every
deterministic (protocol-lie) flavor non-retryable exactly as now. This is
the F4 charter's own rule applied to a site its docstring already admits is
starvation-shaped: the host starved the fixture, so the trial retries on a
fresh rig; a DETERMINISTIC timeout defect burns three rigs (~seconds) and
still reds — the exhaustion-still-reds property is what makes the widening
safe, and its proof is the AR-2 sabotage arm (§5.1): a planted deterministic
TIMEOUT poison must still red through exhaustion. Two pins ship with it (the
de-clock doctrine's membership form): retries-on-fresh-rig asserts
`retries >= 1` and `"drain-poll-timeout" in retry_sites`; the
deterministic-poison arm asserts exhaustion with the composition rendered.
The carrying-site list in `run_trial`'s docstring gains the row; the
classifier-table pins gain the cell.

The other half of that residual sentence — entry-timeout at the dispatch
door — has NO live observation; it stays a disclosed owner row, untouched.

**This sub-fork is the maintainer's to confirm** (slice 3 chose "owner row
rather than widened here"): widen now (recommended, per the doctrine and the
safety argument above) or keep the disclosed row with its trigger (a second
live observation). The payload is fully specified either way.

### 1.4 The named-residual register: two families, no mechanism

- **Chronic-starvation exhaustion** (§0.3): honest reds; the accounting rule
  (§5.2) tolerates them by name. No mechanism — widening the attempt budget
  is a deferral with an unmet trigger.
- **Sustained-stretch** (slice 3's definition: ≥3 distinct band-families
  breaching in one execution): the belt reds on both generations by design —
  a runner that cannot measure must not ship green; §5's honest verdict for
  it is "underpowered, decide nothing" as a red lane. No mechanism.

### 1.5 The placement fork, resolved on evidence — no TestClock moves in this slice; the migration stays the standing target

The owner's question (timing tests locally-only, relaxed/skipped in CI) and
the standing recommendation (move order/budget-semantics families onto
TestClock; keep a minimal real-clock sentinel set with in-run-relative
ceilings; skip-on-measured-load only as a last resort) were examined against
the actual red set. The evidence forks the recommendation's first clause:

- **No member of the current red set is an order-semantics family.** The
  two rig files are measurement rigs whose outputs are DISCLOSURE quantities
  (the sequential module says so in its own docstring; the continuity cells
  feed the #172/#159 acceptance readings). Their asserted properties ride
  real thread scheduling, real paced captures, and real SQLite busy
  behavior; `TestClock` (`src/benchweave/control/clocking.py` — instant
  waits, recorded) can make the deadline MATH deterministic but cannot
  virtualize a helper's RLock wait or a contender's busy retry — the very
  quantities the bands disclose. A TestClock twin of lock-block would assert
  exactly what its ordering asserts already prove (and never flake); the
  flaking part IS the disclosure quantity. Migrating it would change what
  the test measures, not how.
- **The load-honest form for a disclosure ceiling is the in-run-relative
  reference** (§1.2) — the pattern slices 2–3 already proved three times
  (monitor-gap, queued-run, `fail_delta_ms`). This slice extends it to the
  last two absolute ceilings in the red set's families.
- **The sentinel set already IS minimal and stays whole**: ~64 marked ids,
  one serialized lane, ~45–70 s test portion, no skips. Skipping or
  local-only-ing it is rejected with the standing reasons (it strips the
  only enforced execution surface for contributor PRs, kills the ≤2/40
  health sampling, and would leave the serialized model's disclosure with
  no enforced measurement at all) plus today's counter-example: the rule
  this slice responds to only worked because the lane EXECUTED — three
  load-shaped reds on diffs that never touched a timing path were caught,
  counted, and forced this design.
- **The migration intent is honored as standing policy, not invented
  work**: the conventions line (drift-and-obligations) gains the sentence —
  a NEW test whose asserted property is purely order/budget semantics
  defaults to the injected clock (TestClock); a wall-measured disclosure
  quantity defaults to the timing lane with an in-run-relative ceiling; the
  census's row-22 virtual families remain the reference shape.

### 1.6 Considered and rejected (so nobody re-litigates blind)

- **Moving the run-path smoke trio into the timing lane now** — muddies the
  marker's contract (real-paced ms-bound tests), adds ~15–20 s of non-timing
  wall to the serialized lane, and answers a one-recurrence gates question
  with timing-lane surgery. Deferred with payload (D-gates).
- **Widening the three-attempt trial budget** — the bounded-authority
  doctrine; its trigger (lane wall ≥ 2× baseline) is unmet.
- **Raising the drain cap or any numeric bound** — the standing #241
  discipline; every ceiling change in this slice REPLACES a constant with an
  in-run measurement of the same quantity, which is not a widening (the
  synthetic pins refuse the loosened forms).
- **pytest-level reruns / CI retry steps** — the laundering shape this repo
  refuses (slice-3 §1.3); unchanged.
- **Accepting both belt-swap outcomes (swap or no-swap)** — would make the
  pin vacuous; the fix is the allocation (§1.1), not the post-condition.

### 1.7 The hosting constraint and the external-research mapping (folded mid-design, 2026-10-02)

Owner constraint, recorded: **no self-hosted runners at this point.** The
external consensus shape for timing-critical suites (per-PR deterministic
gates + evidence-grade timing on quieter hardware — the CPython
speed.python.org / rustc-perf pattern) loses its hardware leg on the hosted
pool: a dedicated or scheduled lane on the same pool inherits the pool's
variance, so a nightly/evidence lane is NOT proposed and would have to beat
the same variance to justify itself. The levers the constraint leaves
standing are the three this design already runs on: (1) determinize what is
only incidentally time-dependent — this slice moves cut/order proofs onto
deterministic asserts (§1.2), the state-machine half of every band; (2)
load-honest bands — the in-run-relative form, strictly stronger than a
constant re-derived from ANY distribution because the reference is measured
in the same execution; (3) sampling discipline for the real-clock remainder
(the §5.2 window). Where does evidence-grade pacing proof live, then? Where
the #247 gate line already enforces it: the pre-push LOCAL full battery —
the quiet-host distributions, the census's 3x proofs, and this slice's AR-5
cold union run. Local carries the quiet evidence, CI carries the load-honest
forms, and neither cites the other's denominator — which is finding 1's
point, adopted.

The owner's research pass surfaced five findings (externally sourced and
verified by that pass; mapped here against this slice's mechanisms):

| # | finding | disposition |
|---|---|---|
| 1 | A/A calibration — a bound tighter than the platform's same-code-vs-same-code discrimination floor is a coin-flip gate; derive bands from the runner's OWN distribution, never quiet-machine medians | **ADOPTED as AR-7** (§5.1): an A/A pass on the hosted lane — ≥8 same-tree re-executions of the PR's ci timing job — measures the same-code spread of the in-run quantities. This design introduces NO new constant derived from quiet data; the two inherited slops (+150/+300) are re-validated against the OBSERVED hosted red-census shapes (258.7 and 354.6 inside realized+150; 1724.55/1734.19 inside clamp+300 — §6 Evidence), and AR-7's report becomes the denominator-of-record for every REMAINING constant band (the floors, the out-of-scope control-arm ceilings). Any remaining constant whose A/A spread crosses its margin is named to the register as a coin-flip gate. The post-merge rule itself stays the outcome-rate rule — keying it to A/A would couple two measurements the rule does not need coupled; A/A feeds the CONSTANTS and the telemetry row, not the kill count |
| 2 | best-of-N with MIN; for counts, membership-with-headroom — never exact counts on a starvable host; a same-run ratio is only stable if the design makes it so | **ALREADY SHIPPED, recorded as alignment.** Slices 2–3 de-clocked the retry pins to membership+property; §1.1 removes the last construction-order coupling; the belt and the #172 one-trial trim are the in-tree robust-statistic forms at cell/trial level. Literal min-of-3-per-variant would move the §5 reading (trim depth is pinned by the both-directions tolerance test — a slice-3 owner fork, refused there and here). The ratio caution is answered structurally: every same-run reference in §1.2 is a CONTAINMENT, not a hoped-for correlation — the helper's wait is bounded by the lock-holder's realized dispatch; the queued delay by run-1's measured span; the busy wait by the clamp value the bracket itself computed |
| 3 | determinize the incidental: clock injection, synchronize on events/ordering not elapsed, never lengthen sleeps | **ADOPTED as this slice's own criterion, restated in the finding's vocabulary:** per test, is the asserted property state-machine (move to the injected clock) or stopwatch (keep real, calibrate the band)? §1.5's ruling holds — the red set's bands are stopwatch disclosure quantities; their state-machine halves (cut/order status) already assert deterministically and gain asserts here. The in-tree TestClock is the injection vehicle — no new dependency is added for determinization (principle 9). No sleep is lengthened anywhere in this slice |
| 4 | retry telemetry: per-site aggregate rates escalating to a visible quarantine-with-expiry + owner; never a silent skip, never warn-only | **DEFERRAL ROW (D-telemetry).** The per-trial records exist (`retry_sites`, compositions rendered at exhaustion); the missing piece is the session AGGREGATE with a ceiling. Its data source is AR-7 — a ceiling derived before that report exists would be a quiet-median constant, finding 1's own error. Payload: the trial-log provenance test (which already enumerates the session's cells) gains the per-site aggregate read plus a disclosed ceiling derived from AR-7. The repo's existing analog of quarantine-with-expiry is the KILL clause — visible, owner-actioned, reopens with the log; this project does not skip tests, so no separate quarantine mechanism is built |
| 5 | bound runaway timing tests both ways: job-level timeout + per-test timeout | **PARTIAL THIS SLICE.** `timeout-minutes: 15` lands on the `timing` job (~3x its observed wall incl. setup) — one workflow line, obligations-5 walked, a timeout kill categorized as a lane-infra event in §5.2 (never silently counted; and itself a signal — a hung marked test is exactly the runaway the finding names). Per-test timeouts require a new dependency (a Tier-3 shape under the rubric's dependency rule) — D-pytest-timeout deferral row; the same row carries extending `timeout-minutes` to the other jobs |

## 2. Minimal increment scope

Build order (RED-first where behavior changes, one slice per commit):

1. Commit 1: this design record.
2. The pace-allocation fix + its mutation-style RED arm (§5.1 AR-1) in the
   belt-swap pin.
3. Lock-block: the UNKNOWN cut assert, the in-run stamps, the relativized
   ceiling + shared band helper + synthetic worst-case pin; the
   reverted-cut arm re-proven to red on the STATUS assert in THIS test
   (monitor-gap's proof does not transfer — the assert is new here).
4. D-rowB — POINTER (pre-freeze controller amendment): D-rowB is executed
   by PR #329 (commit e96e08b, refute-folded there); it lands ahead of
   this slice; this slice carries no row-B change. No build step here.
5. The drain-poll-timeout classification + its two pins + classifier-table
   row + docstring row (OWNER FORK §1.3 — build last so a maintainer "keep
   the row" call drops exactly this commit without touching the rest).
6. The workflow line: `timeout-minutes: 15` on the `timing` job (§1.7
   finding 5) — one line, its categorization clause in §5.2.
7. Docs sweep: drift-and-obligations conventions line (named residuals, the
   TestClock standing policy, the no-local-only ruling, the hosting
   constraint); the module docstrings touched above say what they still
   prove.
8. Issue #241 outcome comment: the count table (§0.1), the belt diagnosis
   (§0.2), per-family verdicts, the forks (§1.3, D-gates trigger), the new
   pre-committed rule (§5.2), the hosting constraint + research mapping
   (§1.7), and the #329 landing note (§8).

### Deferral table (the register after this slice)

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D-gates | run-path smoke trio load-isolation (payload: a `runpath` marker registered beside `timing`, gates deselects both, one serialized job runs `-m runpath`; cold-union + partition re-proof per the slice-1 AR shape; ~+1 job, ~+60–90 s) | issue #241 (next slice or closure pass) | a SECOND gates-lane execution redding any member of the outcome-degradation class (outcome_unknown / execution_error under parallel execution), OR any recurrence that survives an immediate rerun |
| D5 | marker-rot guard | unchanged (slice-1 row) | a `gates` red on an unmarked test whose failure is a ms-bound assert — NOT fired by §0.5 (outcome class, not ms-bound) |
| D6/D7 | keep-and-document clusters; plugin-lane paced tests | unchanged; §0.5's occurrence is recorded on the issue as rows-8/9 class-recurrence #1 with new ids | each row's own recurrence; for rows 8/9 the D-gates trigger above supersedes |
| retry time-multiplier | widen the attempt budget | unchanged (slice-2 row) | timing-lane wall ≥ 2× baseline — unmet (§0.3) |
| cap-raise | drain-cap 2000 ms | unchanged (slice-2 refusal, unforced) | the >1200 ms raise trigger |
| D3-sibling / D2-fixture / D2-trim | unchanged (slice-2/3 rows) | unchanged | unchanged |
| belt-visibility | print-only belt usage | unchanged (slice-3 row) | a belt incident whose log lacks the usage line |
| mid-pace discard | a belt-swap ladder slot consumed by an attempt discarded AFTER pacing began (§1.1 residual) | this record | a belt-swap red whose log shows a dispatch-door composition mid-acquisition |
| entry-timeout at the dispatch door | the other named non-retryable starvation residual (§1.3) | the disclosed owner row | a first live observation |
| D-telemetry | per-site retry-rate aggregate over the session's trial records, ceiling derived from AR-7's A/A report; the trial-log provenance test is the reader (§1.7 finding 4) | issue #241 (next slice or closure pass) | AR-7's report landing (its own data source), or a belt-visibility incident |
| D-pytest-timeout | per-test timeouts (a new dependency — Tier-3 by the rubric's dependency rule) + `timeout-minutes` on the non-timing jobs | issue #241 closure pass | a runaway/hang the job-level bound cannot localize (a timing-job timeout kill whose log shows no single hung test) |

Riding this slice (executed, not deferred): the belt-swap pin fix, the sequential family's last
absolute ceiling (D4' completion), the drain-poll residual (§1.3 fork), the
residual register naming, the placement-fork ruling and its conventions
sentence. D-rowB is NOT riding this slice: D-rowB is executed by PR #329
(commit e96e08b, refute-folded there); it lands ahead of this slice; this
slice carries no row-B change.

## 3. Precedent (all in-tree, extended not invented)

- **The D4' in-run-relative ceiling pattern** (slice 3's fold, three prior
  executions: monitor-gap `gap <= realized + TOLERANCE`, queued-run
  `delay <= run1 + 300`, `fail_delta_ms <= 1500 + pre_begin + 300` at
  `test_otdp_bridge.py:2685`): §1.2 is its fourth and fifth applications,
  each keeping the deterministic cut-proof assert beside the relativized
  ceiling.
- **The synthetic band-form pin** (`_queued_delay_breaches` +
  `test_queued_delay_band_refuses_a_delay_past_run1_plus_slop`): the shape
  §1.2's two synthetic pins copy for families with no planted adversarial
  arm.
- **The recording `busy_timeout_window` wrapper**
  (`test_otdp_bridge.py:2703`, `:2752`): the exact in-tree shape D-rowB
  reuses to make the clamp legible in-run.
- **The F4 carrying-site list** (PR #236; slices 1–3 extended it: priming ×2,
  pre-flight, dispatch-door, drain-poll-door, drain-cap): §1.3 adds
  `drain-poll-timeout` by the same charter, with the same
  exhaustion-still-reds safety property and pin shapes (membership form per
  the de-clock doctrine).
- **The pace-allocation fix** extends the pin-discipline slice 3 established
  (assert the property, not the attempt bookkeeping): the belt-swap pin's
  FIXTURE stops asserting which CONSTRUCTION carries the poisoning and keys
  it to the pace events that actually constitute a measured trial.

## 4. Invariant and drift impacts

- **A06 (evidence over assertion), both directions.** The pace-allocation
  fix stops a load artifact (a shifted construction order) presenting as a
  belt-property failure — and stops the same shift silently vacating the
  pin. The relativized ceilings stop a host-stretch artifact presenting as
  a cut failure while the cut gains its own deterministic assert (the
  UNKNOWN status) — strictly MORE evidence, not less. The poll-residual
  classification stops a starvation artifact presenting as a rig defect,
  with the deterministic-defect kill pinned. Disclosed prices: the two
  relativized ceilings lose their constant anchors (their synthetic pins
  and floors carry the teeth; the cut/status asserts carry the proof); the
  classification widening lets a deterministic timeout defect burn three
  rigs before redding (~seconds, pinned by the exhaustion arm).
- **No CTL/STO/CON/REG invariant is touched.** No `src/` byte moves (the
  poll classification lives in the test rig; the bridge's own refusal
  behavior is unchanged). No `standards/` byte, no schema, no workflow, no
  dependency. No on-disk format.
- **Obligations walked:** 4 (no CI-map row change — no job shape moves; the
  conventions section gains the residual/policy sentences and the hosting
  constraint), 5 (ONE workflow line moves — `timeout-minutes: 15` on the
  `timing` job, §1.7 finding 5; the cold unfiltered union run rides §5.1),
  10 (no dependency change). The marked set GROWS by the new pins (~3–4
  ids); the slice-1 AR-1 collect-diff is re-recorded in the PR body
  (T ∪ G == U, T ∩ G == ∅).
- **Tier and the Step-1 keyword scan (#254).** Expected diff: this record,
  `tests/integration/test_cross_instance_continuity.py` (pace-allocation +
  its arm; the poll classification + two pins + classifier row + docstring
  rows), `tests/integration/test_capture_sequential_model.py` (the UNKNOWN
  assert, in-run stamps, the relativized ceiling + helper + synthetic pin),
  `tests/unit/test_otdp_bridge.py` (POINTER: moved to PR #329 by the
  pre-freeze amendment — no change in this slice), `docs/internal/drift-and-obligations.md`
  (conventions sentences). Design-time scan over the expected added/removed
  text, code and docs alike, for the eight Step-1 keywords
  (`thread`-ing, `async`-io, `sub`-process, `sha`-256, `hash`-lib,
  `mig`-rate, `reco`-very, `protec`-tion — spelled here in broken form so
  this record's own text stays scan-clean): **all eight count 0 by
  construction**; this record was written to contain none of them. Path
  rule: test-code change under `tests/` → **Tier 2**. Caveat, disclosed per
  the slice-3 precedent: the review re-derives the tier over the REAL diff —
  hunk CONTEXT lines in the three test files can carry a keyword (their
  imports and neighbor code); if the actual added/removed lines trip a
  keyword the slice takes the Tier-3 lane and the standing adversarial
  review covers it. The builder re-runs the scan pre-PR and records the
  counts.

## 5. Measurable proof and the pre-committed acceptance rules

### 5.1 Build-time (PR) acceptance

- **AR-1 (pace-allocation, mutation-style RED):** an arm that (a) reverts
  the pace hook to construction-order indexing and (b) injects one
  pre-acquisition-discarded construction must RED the allocation post-
  condition (the designed ladder no longer lands on gen-1's measured
  trials); green with the pace-order hook in place under the same injected
  discard. Collected-count check per the RED-sanity convention.
- **AR-2 (poll classification, both directions):** (a) the fresh-rig arm —
  a patched TIMEOUT-flavor poison on the first construction — yields
  `retries >= 1` with `"drain-poll-timeout" in retry_sites` and a completed
  trial; (b) the sabotage arm — a DETERMINISTIC TIMEOUT poison on every
  construction — exhausts three rigs and STILL reds with the composition
  rendered (the widening cannot launder a rig defect). AR-2b is the kill
  direction and is shown RED against a sabotaged-classifier shape at build,
  the slice-3 AR-2 precedent.
- **AR-3 (relativized ceilings keep their teeth):** (a) lock-block: the
  cut-disabled arm (the `bounded()` timeout neutralized in place, the
  slice-3 D4' fold's demonstrated method) must red on the UNKNOWN-status
  assert — the cut-proof lives in THIS test now; the band-form synthetic
  pin refuses a wait past realized + tolerance. (b) row-B — POINTER:
  D-rowB is executed by PR #329 (commit e96e08b, refute-folded there); it
  lands ahead of this slice; this slice carries no row-B change, so AR-3b
  is not an acceptance rule of this slice. (a) is proven RED-first where
  the arm can run.
  recorded window per dispatch (asserted), and the band-form pin refuses a
  busy-wait past clamp + 300 while a shortened recorded clamp (e.g. 500)
  reds the 1300 floor. (row-B half retired by the pointer amendment; (a)
  stands.)
- **AR-4 (partition integrity):** the slice-1 AR-1 collect diff re-recorded
  (T grows by the new pins; T ∪ G == U, T ∩ G == ∅, membership unchanged
  otherwise).
- **AR-5 (both lanes green + cold union):** `gates` and `timing` green from
  the COMPLETE rollup (`scripts/merge-verified.sh`); one cold local
  unfiltered `uv run pytest -q` green. Lane-cost delta disclosed in the PR
  body (the new pins are sub-second except the poll arms' forced spins,
  ~2–3 s each, fired only when they force).
- **AR-6 (evidence discipline):** gate numbers from junitxml attributes or
  true exit codes; the 40-window table (§0.1) re-verified from `gh run
  list` at PR time in the PR body.
- **AR-7 (A/A calibration, the hosted-runner discrimination floor — §1.7
  finding 1):** ≥8 same-tree re-executions of the PR's ci `timing` job
  (`gh run rerun --job`, or run-rerun-all with only the timing log read —
  builder's call, disclosed in the PR body); collect each execution's
  printed in-run quantities (realized dispatch, helper wait, monitor gap,
  the axis cells' x1/duration medians). The report states N, per-quantity
  same-code spread, and names ANY remaining constant band whose observed
  A/A spread crosses its margin (a coin-flip gate) to the register. It is
  the denominator-of-record for future band calls and the D-telemetry
  ceiling's data source. These PR-time attempts are pre-merge and do NOT
  enter the §5.2 window. Cost: ~8 × ~2 min of hosted timing-lane time,
  disclosed.

### 5.2 Post-merge acceptance — pre-committed BEFORE any post-slice-4 number exists

Unit of observation: one `timing` job execution (main pushes and PR runs
both count; a re-run attempt is its own execution; runner-level startup
failures AND the new job-level `timeout-minutes` kill are categorized
separately as lane-infra events, never silently counted — a timeout kill is
itself a signal, the runaway shape §1.7 finding 5 names). The window opens
at slice 4's own merge run. Red: a failing test id inside the marked set.

- **SHIP (the fixed classes are dead; the lane's residual budget is named):
  over the first 40 timing-lane executions post-merge, ≤2 red executions,
  AND every red lies in a named residual family — {chronic-starvation
  exhaustion (retry composition exhausted), sustained-stretch (≥3 distinct
  band-families breaching in one execution), a sequential-family FLOOR
  (load-safe direction; should never fire — a floor red is a mechanism
  signal, see KILL)}.**
- **KILL:** ≥3 red executions in 40; OR any single red of a mechanism this
  slice touched — a re-fixed belt-swap pin redding on any shape (including
  the mid-pace-discard residual, which would mean the residual is live and
  bigger than sized), a relativized lock-block ceiling redding, the
  UNKNOWN-status cut assert redding, or a drain-poll-timeout-classified
  site redding at a NON-exhaustion presentation. A kill reopens #241 with
  the failing log as the next slice's Evidence A; it does not revert blind.
- **UNDERPOWERED, not conclusive:** fewer than 40 executions accumulate
  before the next #241 slice opens — no flake conclusion from the partial
  sample; the counter continues. Every published claim carries its
  denominator ("N timing-lane executions, R red executions, E red events").
- **Baseline honesty:** the inherited post-slice-3 rate is 3/11 (27%, small
  n) against slice 3's own 7/74 (9.5%). Of the 3 inherited reds, this slice
  claims to kill exactly two classes (the belt-swap pin fixture, the
  absolute lock-block ceiling) and to name the third (exhaustion). The ship
  bar is therefore NOT a promise that the lane stops redding — it is a
  promise about WHICH reds remain: only the named starvation-honest ones,
  at ≤2/40.

## 6. Evidence appendix (collected 2026-10-01/02, before this record was written)

### Evidence A — the three post-merge reds (job-level, logs pulled)

1. Run 36867869659 (merge run of slice 3 itself, on `0f3b786`):
   `test_belt_swap_still_audits_gen1_x1_floor` — `AssertionError: {}` /
   `assert 0 == 1` on `_BELT_GENERATION_RUNS.get(("non_capture",
   "buffered"), 0)`; the `pytest.raises(match="X1 floor")` and the `x1_ms`
   containment PASSED before it (traceback starts at the swap assert) —
   §0.2's elimination argument in one line: the floor red was real, the
   swap was not, and a 1.9-paced measured trial makes a swap unavoidable.
2. Run 36908741739 att.1 (PR #329, zero timing-path overlap — verified: 6
   files, none in the failing paths): axis[capture-buffered] retry
   composition exhausted `pre-flight-staleness -> pre-flight-staleness ->
   dispatch-door`.
3. Run 36908741739 att.2 (22:31): `test_second_dispatch_lock_block` —
   `assert 258.735 <= (50 + 150)` at `test_capture_sequential_model.py:464`,
   stdout "helper waited 258.7 ms"; the status and refusal-message asserts
   above it passed.

### Evidence B — the already-dispositioned lookalike

Run 36852240046 (10:56, PRE-merge, slice-3 Evidence A row 7):
`test_drain_cap_starvation_retries_on_a_fresh_rig` `assert 2 == 1` — the
exact-count form slice 3's de-clock replaced; the shipped docstring cites
this run ID as its third false red. Not in the §0.1 window; no action.

### Evidence C — the gates trio (outside the lane, §0.5)

Run 36883076723 (15:17, merge #327): gates red on the three run-path smokes
(outcome_unknown / execution_error / outcome_unknown under `-n auto`, `[gw1]`
in the traceback header); timing job GREEN in the same run (job-level
inspection); 15:21 rerun 36883625680 fully green.

### Evidence D — the count (§0.1's table)

`gh run list --workflow ci.yml --created ">2026-10-01T10:00:00Z"` — 20 runs
through 2026-10-01T22:52Z, none later at design time; 11 post-merge timing
executions by the rule's unit; the pre-merge runs (10:56 back) belong to
slice 3's census.

### Evidence E — the A/A calibration (method pre-committed; numbers land at build, AR-7)

Same tree, same lane, ≥8 executions of the PR's ci `timing` job before
merge; per-quantity same-code spread of the in-run printed quantities; the
hosted reds already in Evidence A are the first three calibration points
(258.7 wait; 354.6 gap — slice 3's fold; 1724.55/1734.19 busy — #207's
corroboration). No number from this pass existed when any mechanism in
§1 was chosen — the collection METHOD is what is pre-committed here, per
the §-header protocol. The quiet-machine census distributions are
explicitly NOT a CI denominator (§1.7 finding 1); they remain the local
pre-push battery's evidence.

## 7. Top risks and their falsifiers

1. **The pace-allocation fix hides a real belt gap** (the adversary's first
   attack: the observed red was a genuine laundering-adjacent defect, and
   the fix entrenches it). Answered by §0.2's elimination argument — the
   belt's no-certification behavior on a floor-only allocation is its spec,
   and the laundering regression the pin guards (gen-1's floor skipped) is
   unreachable in the observed shape (no swap occurred to skip it). The
   pin's RED arm keeps the laundering kill. Falsifier: AR-1 failing, or the
   pin redding post-merge on any shape.
2. **Mid-pace discards shift the ladder anyway.** Disclosed residual
   (§1.1); sized by the observed exhaustion compositions (pre-acquisition
   sites). Falsifier: the D-table's mid-pace-discard trigger firing.
3. **The relativized ceilings admit a slow cut.** With the cut-proof on the
   status assert, a cut that fires LATE (dispatch realizes 400 ms, cut at
   400 not 50) passes lock-block's ceiling (wait ≤ realized + 150). The
   floor family is the counterweight: monitor-gap's `>= BUDGET_MS - 40`
   floor and lock-block's `>= 20` floor survive; a systematically-late cut
   is caught by monitor-gap's floor and the range-gate reading, not by this
   test's ceiling — disclosed here so the reviewer weighs it. Falsifier: a
   planted late-cut arm (a §5.1 optional arm if the refute lane asks).
4. **The poll widening misfires on a deterministic defect** (three wasted
   rigs, slower diagnosis). Bounded: exhaustion reds with the composition
   rendered — the diagnosis is IN the red, richer than today's plain
   assert. Falsifier: AR-2b.
5. **The named-residual budget becomes a dumping ground** — every future
   unexplained red gets called "exhaustion" and tolerated to 2/40. Guarded:
   exhaustion reds must SHOW the composition (the F1 wave-1 fold guarantees
   the rendering); a red without a composition render is NOT in the family
   and hits the KILL clause. Stated in §5.2's family definitions.
6. **The owner forks are decided wrong** (§1.3 widen-vs-row; D-gates
   trigger). Both carry payloads and are cheap to reverse; not design
   risks, sequencing calls.
7. **The A/A pass is underpowered** (N=8 may not resolve a discrimination
   floor for tight quantities — CPython's own calibration needed more).
   Disclosed: AR-7's report states its N and is DIRECTIONAL for any
   quantity whose spread it cannot resolve; it gates nothing by itself, and
   the register entry for a coin-flip suspect requires the spread to
   actually cross, not merely approach. If N=8 is inconclusive for a
   specific bound, that bound keeps its current disposition and the A/A
   finding says so honestly rather than licensing a re-band.

## 8. File-level change list and the landing sequence

| file | change |
|---|---|
| `tests/integration/test_cross_instance_continuity.py` | the belt-swap pin's pace-order allocation + AR-1 arm; the drain-poll TIMEOUT classification (`_poll_found_dead_session` + the raise site) + the `drain-poll-timeout` carrying-site rows (docstring + classifier table) + the two pins; residual-register naming in the axis docstring |
| `tests/integration/test_capture_sequential_model.py` | lock-block: the UNKNOWN cut assert, in-run dispatch stamps, `wait <= realized + TOLERANCE_MS` via a shared helper + synthetic worst-case pin; floor and ordering asserts verbatim; docstring |
| `tests/unit/test_otdp_bridge.py` | POINTER: no change in this slice — D-rowB is executed by PR #329 (commit e96e08b, refute-folded there); it lands ahead of this slice |
| `.github/workflows/ci.yml` | ONE line: `timeout-minutes: 15` on the `timing` job (§1.7 finding 5) |
| `docs/internal/drift-and-obligations.md` | conventions sentences: the named residuals, the TestClock standing policy, the no-local-only ruling, the hosting constraint |
| `.claude/deep-review/2026-10-02-issue241-slice4-residual-families-design.md` | this record, commit 1 |
| issue #241 | outcome comment per §2 step 7 |

No `src/` bytes. No `standards/` bytes. ONE workflow line (the job
timeout). No dependency change. The two ceiling CONSTANTS replaced by
in-run references are the only bound-shaped edits, and each names its
cut-proof and its synthetic pin. No self-hosted runner, scheduled lane, or
new job is proposed anywhere in this slice (§1.7).

**Landing sequence with PR #329** (branch pushed, rollup shows timing
FAILURE from §0.1 reds #8/#9; its diff has zero timing-path overlap —
verified against the failing paths): no dependency either way and no rebase
obligation — the trains are disjoint. Slice 4 opens its own PR and lands on
its full green rollup. #329 needs exactly one green timing execution (its
reds are load-shaped on an unrelated diff — the flake doctrine's
inert-mechanism + rerun-disclosed shape, and the owner's "a green it can
trust" is a green rerun, not a waiver); if slice 4 lands first, #329's
rerun executes on a tree whose fixed classes make that green likelier, and
its merge gate is its own full rollup. Order: whichever is ready; if both
are green simultaneously, land slice 4 first (it carries the rule the lane
is judged by).


## Erratum (2026-10-02, post-refute)

Per the refute lanes (critic + behavioral + premise/evidence): the
mechanisms stand; the findings land here and in the fold commit. Frozen
sections are not edited; this section is the correction of record.

a. **[C-F2] §1.7 finding-5 arithmetic corrected.** Measured hosted
   timing-job walls: 59–94 s cold. `timeout-minutes: 15` is therefore
   ~10× the cold wall — a HANG backstop, not a load bound: the observed
   worst load stretch (~4.6×) cannot reach it, which is why a timeout
   kill is categorized lane-infra (§5.2) rather than read as a band
   breach.

b. **[C-F3] §5.2 kill arithmetic.** The window publishes N/R/E/K —
   executions, red executions, red events, and K timeout kills. A kill
   consumes an execution slot in N; ≥3 kills in the window takes the
   same KILL path as ≥3 reds.

c. **[C-F4] Evidence E wording.** The (258.7, 258.0)-style realized-wait
   pairs are INFERENCE from the lock mechanism (the helper's wait is
   bounded by the realized dispatch plus its own refusal path), not
   measurements — the hosted reds printed waits only. AR-7's A/A pass
   measures the difference-spread directly.

d. **[C-F5] §7.3 counterweight sentence corrected.** Monitor-gap's
   floor catches EARLY/instant cuts; the axis bands counter global
   stretch, but as a non-actionable verdict (underpowered, decide
   nothing). Systematic LATENESS of the cut has no in-lane detector —
   disclosed as a named gap, to be weighed by the refute's owner rows.

e. **[A-F4] §1.3 buildability amendment.** The payload as written (an
   ungated raise site) dies at the drain-cap site — the engine's
   `poll_round` latches `session_failed` and stops silently on a
   pre-trip poison, so the trial dies at `drain-cap` without reaching
   the classification. The LANDED mechanism gates the poison post-trip
   on the owning rig's latched monitor cause (commit a2af05f and the
   fixture docstring carry the detail).

f. **[B-B1] AR-3's orphaned fragment** (the headless tail after
   "proven RED-first where the arm can run.") is known-cosmetic; the
   frozen text stands, this erratum is the correction of record.

g. **[B-B3] Scan counts repaired to the rubric's literal units.** The
   eight Step-1 keywords as LITERALS on added lines: 0/8 (re-verified at
   the fold: threading, asyncio, subprocess, sha256, hashlib, migrate,
   recovery, protection — the "thread 5 / migration 2" substring counts
   were `helper-thread`/`capture thread` prose and a non-keyword, now
   superseded). Context lines carry threading=3 per the refute lane's
   count; Tier 3 stands (the standing adversarial review covers it).
