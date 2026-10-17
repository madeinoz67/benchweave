# Issue #241 row 12, attempt 2 — arm-1 deadline: the attempt-1 kill, and deadline-timebase dilation

**Date:** 2026-10-17
**Slice of:** issue #241 (timing-fragile tests under host load), census row 12, second
disposition of arm 1
**Supersedes:** `.claude/deep-review/2026-10-17-issue241-row12-arm1-deadline-design.md`
(attempt 1, merged as PR #494, `34c19f52`) — its own pre-committed KILL clause fired.
**Status:** design only — no code written. Branch named at build time.

**Placement note (the triage rule):** public, deliberately promoted from the `private/`
default. Same content class as the adjacent public attempt-1 record it supersedes
(mechanism, measurements, an honest kill — first-class public per the README), no
person/client/bench/commercial identifiers, and the pre-committed acceptance rule below
must be provably pre-committed in git history before the 40-execution window opens —
`private/` is gitignored and cannot carry that proof.

---

## 1. The kill, read from the record it killed

Attempt 1's pre-committed rule said: *any row-12 red with the arm-1 UNKNOWN signature in
the window = the fix failed.* It fired. PR #480 (a `setup-uv` version bump; zero diff
overlap with any timing path) was refreshed by merging `main` after `34c19f52`, so its
timing lane ran **with the fix present** (verified: `34c19f52` is an ancestor of
`origin/main` `3ad8a31b`, and the failing frame cites test line 609 — the post-fix
numbering of the arm-1 OK assert; the pre-fix assert lived ~30 lines higher). Run
38995012011, timing job, 2026-10-17T02:29:41Z, signature byte-identical to attempt 1's
CI failure: `UNKNOWN`, `message='Invalid, failed or late adapter result; no replay'`,
`dispatch_state=UNKNOWN` at the arm-1 OK assert. The attempt-1 reference assert (line 577)
appears in the served traceback's source excerpt, so the reference capture ran and passed.

The same job also failed two `test_cross_instance_continuity.py` range-gate tests, whose
own one-shot belt re-measured and found the breach held **on both generations** — its
rendered verdict: "a systematically-loose fixture, not a transient host stall …
underpowered, decide nothing". That file's own docstring records the lane's runner class:
"a 2–3-stall host shape among tight trials is the runner, not the fixture; every in-lane
range-gate red since slice 2 was that shape". So the KILL run's host was in a **sustained
stretched regime**, demonstrated by a second, independent measurement family in the same
process.

### 1.1 Why the kill could not be diagnosed from its own logs (defect 2)

The lane runs `uv run pytest -q -m timing` (`.github/workflows/ci.yml:117`) with
`addopts = "-q -p no:cacheprovider"` (`pyproject.toml:113`) — no `-rA`, no `-s`. Under
pytest's default capture, **captured stdout is replayed only for failing tests**, and a
green test's prints are invisible. Attempt 1 placed its only diagnostic print
(`budget X ms from reference Y ms` plus the stretch) at the current line 611 — **after**
the assert at line 609. On a red run the print never executes; the served log for run
38995012011 contains no budget, reference, or stretch datum anywhere (verified in the
fetched log: the contention test's failure section carries the traceback and nothing
else, while the continuity failures do show their captured belt prints — the replay
mechanism works; our print was simply unreachable). Consequently the kill cannot be
classified as either:

- **Branch A** — reference ≤ 566.67 ms: the lift never engaged
  (`max(2000.0, 3.0·r + 300.0) > 2000.0` iff `r > (2000−300)/3 = 566.67`), the budget sat
  at exactly the historical 2000 ms, and arm 1 exceeded 2000 ms while a nearly identical
  capture had just finished in under ~0.57 s — a within-process differential of ≥ 3.5x
  about two seconds apart; or
- **Branch B** — reference > 566.67 ms: the budget lifted to `3r + 300` and arm 1 still
  exceeded it — the workload out-stretched a 3x-scaled reference.

Both branches falsify attempt 1's premise (§2), but which one fired is unknowable from
the evidence the design left behind. A fix whose kill cannot be classified has failed
twice: once mechanically, once forensically.

## 2. The team-lead's hypothesis, confirmed and corrected against the code

Stated: *the reference is structurally not a predictor of arm 1 — the reference is a
plain uncontended capture, while arm 1 runs mid-capture with a holder taking the write
lock, so arm 1's extra cost is the SQLite busy-retry path, which is precisely what
degrades under host load; the reference can be cheap in a loaded regime while arm 1 is
expensive. If that is right, no multiplier on an uncontended reference will bound arm 1,
and the fix's whole shape is wrong.*

**Confirmed — the conclusion, and the structural asymmetry.** Code evidence:

- The reference (test lines 572-578) is the same paced workload with **no** holder, no
  event wrapper, running on the test thread. Arm 1 (lines 583-608) adds: the wrapper, a
  background capture thread, the holder helper's `BEGIN IMMEDIATE` + 150 ms hold +
  rollback on a second connection (lines 554-561), and — on the colliding append — the
  store's busy-retry episode under the commissioned `busy_timeout_ms=300` window
  (`capture_store.py:139-141`, the clamp's `min(open default, remaining)`).
- Every load-shaped term that distinguishes arm 1 from the reference (the holder's own
  wake latency, the busy handler's twelve count-based wakes, thread scheduling at two
  boundaries, and the episodic-stall exposure of ~100 serialized store transactions) is
  **absent from the reference**. Under uniform dilation both scale by k and a multiple
  bounds; under any differential or episodic stall the reference measures nothing about
  arm 1's excess. The KILL run's co-failures (§1) show the lane's stalls are sustained
  and multi-x — and the attempt-1 arithmetic itself conceded a ~1.9x differential
  cushion (its §4), which Branch A's ≥ 3.5x differential crosses.
- The one attempt-1 sentence the refute had already falsified (addendum F1: hosts in the
  566.67–667 ms reference band receive a lifted budget while passing today) is consistent
  with this: the derivation's model of arm 1's need was `≈ reference + 150 ms` — no term
  for any load-shaped differential.

**Corrected — the dominant term.** "Arm 1's extra cost is the SQLite busy-retry path" is
true but cannot be the whole mechanism: the busy horizon is ~350 ms median (n=5, loaded
host, attempt-1 §1.1; count-based nominal ~328 ms, additive per-wake drift), a bounded,
sub-second class. For arm 1 to cross 2000 ms from a 416.3 ms quiet total
(issue #241 sweep, row 12) needs a multi-x stretch of the **whole paced workload** — 100
pacing sleeps plus 100 transactions all dilating — with the busy episode and wake
latencies adding on top. The KILL run's regime evidence (§1) supports exactly that shape.
The structural conclusion survives the correction unchanged: whether the differential is
episodic (Branch A) or proportional-but-deeper-than-3x (Branch B), **no multiplier on an
uncontended reference delivers the property the scaffolding needs — never bind on any
legitimate host** — because the reference shares no load-shaped term with arm 1's
distinct costs and no term at all with episodic stalls.

**Verdict: the attempt-1 shape (in-run multiplicative derivation) is wrong, not merely
mistuned.** Attempt 2 replaces the shape; it does not re-tune k.

## 3. Root cause, restated

Arm 1's dispatch deadline is fixture scaffolding whose only job is to never bind on the
success path (the census disposition, unchanged). Attempt 1 kept it an absolute-cut
arithmetic question — "how much wall can this host take?" — and tried to answer it from a
predictor. The KILL shows the answer is not derivable from an uncontended reference at
any k, and the print placement shows the answer was not even observable when it mattered.
The property "never binds" is not a magnitude relationship at all; it is a **timebase
relationship**: the deadline's clock must not be the clock the host load stretches. The
repo already has that separation as a designed, pinned seam (§4.2).

## 4. The fix (minimal first increment)

One file: `tests/integration/test_capture_sequential_model.py`, the
`MonitoredHarness.__init__` signature and the
`test_store_contention_mid_capture_stretches_then_classifies` body only. Three coupled
changes:

### 4.1 Diagnostics before asserts (the forensic fix — applies whatever else changes)

Every stamp is computed and printed **before** the assert it can diagnose, because the
lane replays captured stdout only for failing tests (§1.1) — a print after an assert is
unreachable on exactly the runs it exists for.

- After the reference dispatch: print its measured wall.
- Arm 1: stamp `start` (as today); the `observed_append` wrapper additionally stamps the
  first-append time and counts appends; after `t1.join`, compute the stretch and print
  realized wall, first-append latency, append count, the deadline literal and dilation in
  force, and the reference wall — **then** assert OK, **then** assert `stretch >= 110`
  (today's post-assert print moves up, before both).
- Arm 2: stamp dispatch start/end and the appended-event time; print before its asserts.
- Hang guard: after `t1.join(timeout=30)`, `if "result" not in arm1_result:
  pytest.fail("arm 1 dispatch did not return within the 30 s join — hung, not cut")` —
  a real hang then reds loudly by name instead of a KeyError on the assert line.

### 4.2 Deadline-timebase dilation through the existing injection seam (the mechanism fix)

`MonitoredHarness` gains a keyword param, default preserving today's behavior:

```python
def __init__(self, db_path, *, chunks=400, busy_timeout_ms=None,
             services_clock: Callable[[], float] | None = None):
    ...
    bundle, controller = build_capture_services(
        ...,
        clock=services_clock if services_clock is not None else time.monotonic,
        ...
    )
```

The contention test constructs its harness with
`services_clock=lambda: time.monotonic() - 20.0`. **Every deadline literal stays
byte-identical** — reference 10 s, arm 1 2000 ms, arm 2 2000 ms, follow-read 2000 ms —
and `deadline_ns()` (lines 263-266) keeps its real `time.monotonic` base. The divergence
is the mechanism: the bridge consumes every deadline on the **services** clock, which the
harness has always injected (`clock=time.monotonic`, test line 210; the bundle's fresh
per-call `monotonic()`, `capture_services.py:89-91`; the bridge validates only that it is
callable, `otdp_bridge.py:192-193`). With the services clock running 20 s behind the real
base, each dispatch deadline's **real-time equivalent** becomes nominal + 20 s:

- entry expiry check (`otdp_bridge.py:372`) and the async entry (`:1005`): remaining ≈ 20 s;
- the dispatch clamp's `now_ns` (`:385`): `min(300, ~20 s) = 300` — **the commissioned
  open default, with more margin than today** (today's 2 s literal already left it at 300);
- `bounded()`'s remaining (`:240`) and late-result check (`:243`): cut at real ≈ 22 s;
- the paced loop's cooperative cancellation check (`_Context`, `:122`): fires at real ≈ 22 s;
- lifecycle contexts (`:233`) are internally consistent (deadline and now both injected).

**This is a proven, pinned in-tree mechanism, not new architecture:** the row-B unit
family already injects exactly this shape — `test_row_b_clamp_reads_the_injected_clock_no_
hidden_second_clock` (`tests/unit/test_otdp_bridge.py:2839-2874`) runs
`clock=lambda: time.monotonic() - 60.0` with a real-based deadline and pins
`windows == [5000]` (the open default caps; a hidden second clock would clamp to ~150 ms),
and its sibling (`:2877-2911`) pins the +60 s direction. That pin is the structural
reason the whole row-B deadline path — clamp, entry checks, bounded, cancellation — reads
the injected clock with no hidden real clock anywhere. CTL-8's own text ("single-threaded
and deterministic on the injected clocks") is the standing posture; the census's row 22
names the virtual-clock families as "the migration target for stabilization work".

**What stays real — and therefore still measured:** the pacing sleeps, the holder's
sleeps and lock, SQLite's busy handler (real-time, connection-level), the test's stretch
measurement (test-side `time.monotonic`, untouched), the monitor's clock (separate
`SystemClock`), and the capture records' wall ISO (`capture_services.py` passes `wall`
to the controller; the controller never sees the monotonic — verified
`capture_services.py:255-304`). The store reads no clock at all (STO-1; the clamp
docstring's own statement, `capture_store.py:122-126`).

**Arithmetic (DILATION_S = 20.0, arm-1 cut at real ≈ 22 s):**
52x the 416.3 ms quiet total (issue #241 row 12, quiet figure); ~10x the census's own
worst documented quiet-to-CI stretch for this file, 5.4x (rows 3/4: 56.2 → 302.4 ms and
52.3 → 353.3 ms, PR #240 / run 35832745149) applied to arm 1 (~2.25 s stretched); ≥ 11x
the 2.0 s the KILL run's arm 1 demonstrably exceeded. Anti-hang is preserved and stays
gateway-owned: a genuinely stuck dispatch still returns cut-UNKNOWN at real ≈ 22 s —
**before** the test's `t1.join(timeout=30)` — so the failure shape is unchanged (red at
the OK assert with the §4.1 stamps now actually printed). Worst-case deep-stall wall for
the whole test: reference ≤ 30 s + arm 1 ≤ 22 s + arm 2 ≤ 22 s + joins ≈ 75 s against the
lane's 15-minute bound — vs today's joins-dominated worst case of ~40 s; disclosed.

**Arm 2 is retired in the same move.** Attempt 1's D1 deferral (arm 2's own 2000 ms
literal cutting before the classified `RESOURCE_LIMIT` lands — the same load shape, one
assert later) dissolves: arm 2's classification comes from the stamped writer error
after the busy horizon (~350 ms measured, n=5, attempt-1 §1.1), which now races a
real ≈ 22 s cut instead of 2 s. The 1.2 s hold clears the horizon with ~3.4x nominal
margin, unchanged.

### 4.3 The reference survives as a probe, not a budget source

The reference capture **stays** (same 10 s literal — real cut ≈ 30 s; same "degenerate"
assert; still before the wrapper installation, attempt-1 R3's ordering) but the budget
line (`arm1_budget_ms = max(...)`, line 579) is **deleted** — it is the killed premise —
and arm 1's dispatch returns to the literal 2000 ms (real ≈ 22 s cut). The reference's
remaining job is the §1.1 lesson made structural: its printed wall is the regime datum
that classifies any future red (uniform vs differential). Quota arithmetic for keeping
it (the corrected F2 form): the gate compares the request's `max_bytes=1024` against
`allowance = min(max_capture_bytes=8192, max_dataset_bytes − used)`; with reference +
arm 1 finalised, `used = 1600`, allowance `= 6592 ≥ 1024` — arm 2 admitted exactly as
today (today: `used = 800`, allowance `= 7392`).

## 5. Alternatives weighed (the four the brief named, plus the record's own prior rejection)

- **(a) A contended reference** (reference capture with its own holder). Rejected: it
  refines the predictor without fixing the premise. The contention term is bounded
  (~350 ms class, §2), so it cannot explain — or bound — a multi-x differential or an
  episodic stall; and it doubles the holder/hold failure surfaces inside one test. It
  predicts the load-shaped term arm 1 *shares*, not the ones it does not.
- **(b) Budget from arm 1's own observed progress** (a liveness watchdog on append
  counts). Right semantics for anti-hang, wrong layer here: the deadline is enforced
  inside the bridge, so progress-derived budgeting means a bridge change (the
  per-BEGIN re-derivation already recorded as a deferral in `capture_store.py:133-134`)
  or a second, parallel watchdog in the test that duplicates the gateway cut's job.
  Deferred as D3' (production-side); not this slice.
- **(c) Order-of-magnitude constant** (deadline 20-30 s real). Explicit weighing, as
  instructed: attempt 1 rejected "raising the constant" because "still absolute …
  nothing bounds tomorrow's [stretch]". That reasoning targeted a bound asked to
  **track** a workload — correct to reject there. Scaffolding asked to **never bind** is
  sized differently: against the largest legitimate execution, which is an operational
  judgment floored by the lane's job bound, not a multiple of a predictor. So the prior
  rejection does **not** transfer as stated, and (c) is a legitimate fallback. It loses
  to §4.2 on every axis nonetheless: the same one-line cost, a smaller diff (literals
  untouched), D1 retired in the same move, a pinned injection contract (F6) instead of a
  new 20-30 s constant to maintain, and it *is* the census's stated migration direction
  rather than a step away from it. (c) is designated the fallback if the F6 contract
  proves narrower than the bridge's dispatch path (risk R3).
- **(d) Family-wide injected clock (census D4 as written).** Rejected as the blanket
  form, with evidence: **the contention test is the only member of this file's family
  whose deadlines are pure scaffolding.** The monitor-gap quantity *asserts the cut*
  (`status is UNKNOWN` at `BUDGET_MS=50`), and the lock-block quantity asserts the cut
  the same way; dilating their harnesses would delete the mechanism under assertion.
  Their load fixes were the D4' in-run-relative ceilings (landed, slices 3-4). D4 also
  must not be read as "virtualize the pacing" for row 12: the 2 ms pacing creates the
  mid-capture window the holder must win, and the `stretch >= 110` floor's meaning rides
  real pacing against a real 150 ms hold — de-pacing trades this back-end stability for
  a front-end holder race (attempt 1's own rejected alternative). The correct narrow D4
  is the **deadline-timebase** injection, which is §4.2.

## 6. Minimal vs correct, and the per-test boundary

Minimal first increment: §4 as one slice (contention test + the harness param the other
three tests never pass). Correct long-term direction, now stated precisely: *de-clock
the scaffolding, keep the measured quantity real* — deadline-timebase injection for
tests whose deadlines must never bind; mechanism-timeline asserts (the issue's 2026-10-10
stop-settle direction) for tests that measure wall as their quantity. Should this stop
being a per-test patch? **No — the per-test scope is the correct boundary, not a
workaround** (§5(d): two of the four family members assert the cut). The family-wide fold
that remains legitimate is hoisting `services_clock` plumbing (already done by §4.2) and
offering it to future tests by need; nothing further to fold today.

## 7. What this increment defers

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1' | the family-wide deadline-timebase pass (monitor-gap, queued-run, lock-block keep real clocks — their asserts require the cut or measure the wait) | follow-on work on issue #241 | a timing-lane red on any of the file's other three quantities whose captured stdout shows the measured quantity breaching its D4' ceiling while the realized dispatch also exceeded its deadline literal — the scaffolding then shaped the measurement and the fold carries |
| D2' | arm-1 Path-A hardening (holder release after busy give-up → ERROR/RESOURCE_LIMIT at the arm-1 assert) | follow-on work on issue #241 | an arm-1 red whose result shows status ERROR with code RESOURCE_LIMIT (the differential-stall shape of attempt-1 §1.1) |
| D3' | bridge-level progress-derived anti-hang (per-BEGIN clamp re-derivation or liveness-based cut) | follow-on work on issue #241 | a K1-class kill below (UNKNOWN with realized under the dilated cut — a non-deadline poison path), or a production hang report against the capture dispatch |
| D4' | the census comment's stale "633 ms" horizon (measured ~350 ms, attempt-1 §1.1) — still uncorrected in the arm-2 comment (test line 638) | documentation on issue #241 | n/a — a standing correction, carried since attempt 1's D3 |

## 8. Invariant, cross-surface, and CI impacts

- **Invariants: none amended.** No `src/` or `standards/` bytes move. STO-1 untouched —
  the store reads no clock and the clamp arithmetic is caller-side on the injected
  monotonic (`capture_store.py:122-126`, the docstring's own statement). The row-B
  commissioning contract is preserved with **more** margin: the clamp evaluates to
  `min(300, ~20 s) = 300`, the open default, so "the clamp IS the open default" holds by
  the same floor argument attempt 1 used, now against a 20 s remaining instead of 2 s.
  CTL-8's injected-clock posture is the precedent, not a change. A13 untouched (no
  transport surface).
- **Cross-surface: none.** No MCP tools, REST/openapi, CLI, operator docs,
  device-developer guide, vendored standards, fixture lattice, or SDK motion. The
  `timing` marker stays whole-module; the drift-and-obligations lane row describes the
  lane, not per-test scaffolding, and needs no edit. No on-disk format or schema.
- **CI cost:** unchanged lane composition — same test count; the reference probe keeps
  attempt 1's ~0.3-0.5 s quiet cost (§4.3 justifies it as the regime datum); no new jobs,
  no marker-partition change.

## 9. Proof plan and builder pre-merge obligations

The G3 adaptation for a scaffolding fix (attempt 1's shape, plus the control it lacked):

1. **RED control (mechanism sensitivity):** a scratch copy with `DILATION_S = 0.0` in the
   harness call **and** arm 1's deadline literal forced 2000 → 250 must red with the
   canonical UNKNOWN signature — proving the dilation did not numb the OK assert to a
   real exhaustion. Note both knobs are required: with dilation present, a 250 ms
   literal still cuts at real ≈ 20.25 s, so forcing the literal alone no longer reddens.
2. **Diagnostic control (new — attempt 1's missing control):** the same red run's output
   must contain the pre-assert stamps (reference wall, arm-1 realized, first-append
   latency, append count, literals + dilation) in the captured stdout — the channel
   proven open exactly when needed. A red without them is a failed build check, not a
   lane event.
3. **Equivalence control:** a quiet run with `DILATION_S = 20.0` is green with printed
   realized wall in today's class (~0.4-0.6 s), and three consecutive runs print the
   reference wall (floor behavior evidence).
4. **Clamp control (scratch, one paste):** the F6 recording-window pattern over the
   contention harness prints the clamp window during arm 1 — expect `[300]`, the open
   default, evidence for §8's row-B claim.
5. **Unchanged-assert control:** the diff moves no asserted magnitude — OK, `>= 110`,
   `busy_timeout_ms=300`, arm-2's literals and asserts byte-identical.
6. **FAST lane** per CLAUDE.md §3 (bare ruff; fresh-cache bare mypy; focused pytest for
   this file), full battery before push.

## 10. Pre-committed acceptance rule (written before any post-merge number is read)

Metric: **CI timing-lane executions only** (the lane of `.github/workflows/ci.yml:84-117`)
in the slice-4 live window (≤2 red executions per 40, every red in a named family).
**Local runs satisfy nothing** — every clause below references lane executions; local
greens are not evidence for or against any direction. Classified for row-12 arm-1
recurrences: UNKNOWN at the arm-1 OK assert.

- **Ship:** the first post-merge timing execution is green, AND zero arm-1-signature
  reds in the 40-execution window, AND the live ≤2/40 family rule holds.
- **Kill (any one fires):**
  - **K1 — mechanism read falsified:** an arm-1 UNKNOWN red whose printed stamps show
    realized **< 20 s** (under the dilated cut): a non-deadline poison path exists.
    Attempt 3 starts from the printed stamp timeline (first-append latency and append
    count localize the stall), never from budget arithmetic. D3' opens.
  - **K2 — runner regime beyond per-test scaffolding:** an arm-1 UNKNOWN red with
    realized **> 22 s** AND reference wall **≤ 700 ms**: an episodic differential stall
    deeper than 20 s of dilation in a run whose own probe reads quiet. The pre-committed
    response is escalation (lane/runner class review — the census's lane-infra
    category), **not more dilation**: 22 s is already ~10x the census-worst documented
    stretch and one test owning more than that threatens the 15-minute lane bound.
  - **K3 — arm-2 classification disturbed:** any red of arm 2's
    RESOURCE_LIMIT/DISPATCHED/staging/forensic asserts (especially an UNKNOWN there):
    falsifies "dilation cannot disturb arm 2" (§4.2). Response: revert §4.2, fall back
    to alternative (c) for arm 1 only, re-derive from the stamps.
  - The live rules inherit: any red of a touched mechanism; ≥3/40 overall.
- **Underpowered, not conclusive (decide nothing; collect and extend):** fewer than 40
  executions sampled when a candidate red arrives; the raw Actions log truncated before
  the failing test's captured-stdout block (pull the raw log BEFORE any rerun — the AR-7
  lesson); a job-level timeout kill (lane-infra per slice 4, never a family red); or a
  red whose captured stdout lacks the pre-assert stamps (only possible if the prints
  themselves failed — a build defect: fix the prints, restart the window).

**Diagnostic evidence requirement, named:** every red in this window must be read from a
raw log that contains, for the failing test, the §4.1 stamps printed before the failing
assert. A red classified without them is automatically the fourth underpowered case.

## 11. Top risks, each with its falsifier

- **R1 — the injected clock reaches further than audited.** The bridge's complete
  services-clock surface is eight call sites (`otdp_bridge.py:122, 233, 240, 243, 372,
  385, 399, 1005`), all deadline-side; the controller sees only `wall`
  (`capture_services.py:255-304`); the store sees no clock (STO-1). Falsifier: a K3
  red — arm 2's classification moving under dilation would mean an unaudited consumer.
- **R2 — 22 s is still not enough for this lane's stalls.** The kill direction is K2,
  pre-committed to escalation rather than dilation. Falsifier: any K2 red.
- **R3 — the F6 pin covers the clamp, not the whole dispatch path.** The unit family
  pins the clamp's clock domain; `bounded()`/entry checks are audited here by reading
  (§4.2 list) but not separately pinned. Falsifier: a K1 red localized by the stamps to
  a real-clock cut before 20 s — then the fallback (c) replaces §4.2 and a bridge-level
  clock-domain pin becomes its own slice.
- **R4 — the hang guard masks a cut-shaped red.** The guard fires only when the dispatch
  did not return by the 30 s join; the dilated cut returns at ≈ 22 s, so a cut still
  reaches the OK assert and reds there with stamps. Falsifier: a red at the guard's
  message itself — which is, by construction, a named hang, not an ambiguity.
- **R5 — reviewer over-reads the dilation as weakening the test.** Counter-evidence in
  the diff: every asserted magnitude byte-identical (control 5); the cut mechanism
  itself remains exercised for real by this file's monitor-gap and lock-block tests and
  by the unit row-B family. What changes is only which clock the scaffolding rides.

## 12. Tier and the Step-1 keyword scan (#254)

Expected diff: this record (new `.md`) plus the test-file edit of §4 (a harness keyword
param with a `lambda` default-preserving default, stamps, prints, a hang guard, one
docstring sentence, deletion of the budget line, and a construction-site literal). Tier
by the rubric's path rules: **Tier 2** — a test-code change under `tests/` plus a
docs/record file; no Tier-3 path matches (no `src/benchweave/contracts/`, nothing under
`standards/`, no persisted-format surface, no registry, no fixture lattice, no dependency
or submodule motion). The review re-derives the tier over the real diff; context lines
in the test file can carry a Tier-3 keyword (its imports do), and if any **added** line
carries one of the eight, the slice takes the Tier-3 lane — the builder re-runs the scan
pre-PR and records it. The expected added lines introduce no concurrency primitive the
file does not already use (the `lambda` and arithmetic only).

### 12.1 Scan result (mechanical, over this record's full text)

**0/8** — all eight rubric keywords count zero as literals on this record's lines
(mechanically scanned after drafting; the count line deliberately does not spell them
out — the rubric's Step-1 list is the authority). The §4 sketch adds none of the eight
(a callable default, arithmetic, prints). The expected test-file edit's added lines:
0/8 by construction.
