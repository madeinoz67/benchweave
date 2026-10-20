# Issue #241 — the belt cell's both-generations red: root cause, and the driving-signal reading

**Date:** 2026-10-20
**Slice of:** issue #241 (timing-fragile tests under host load), the one-shot cell belt's
readers — the range gate and the axis upper bands
**Observed failure:** `test_axis_trials_complete_all_four_axes[capture-unbuffered]` and
`test_instrument_range_gate_per_axis_per_cell`, both redding through
`_certified_cell` at `tests/integration/test_cross_instance_continuity.py:1972` (the
`raise AssertionError` inside the belt; the `<= 1` generation bound it is named for sits at
:1961). Two consecutive main executions, runs 39358368822 (both tests, key
`capture/unbuffered`) and the pre-restart run (same class, key `capture/buffered`), on
merge `ea04094f` (#503), whose diff touches no timing path. Serial local runs on the same
commit exit 0.
**Status:** design only — no code written. Branch `design/241-belt-cell-plan-reading`,
this record is the worktree's first commit.

**Placement note (the triage rule):** public, deliberately promoted from the `private/`
default. Same content class as the adjacent public #241 records it cites (CI timings on
synthetic rigs, a false-verdict correction, an honest kill direction — first-class public
per the README), no person/client/bench/device/commercial identifiers, and the
pre-committed acceptance rule below must be provably pre-committed in git history before
the post-merge window opens — `private/` is gitignored and cannot carry that proof.

---

## 0. State established from the runner, not assumed

### 0.1 The failure renders, read in full (not the first line)

The CI log carries both generations' values — the diagnosis lives there, not in the
assert's own text. Run 39358368822, key `capture/unbuffered`:

| generation | trial | X1 | X2 | X3 | X4 | dispatch dur |
|---|---|---|---|---|---|---|
| gen-1 | 10 | 51.8 | 1.0 | 48.5 | 78.0 | 52.0 |
| gen-1 | 20 | 51.7 | 1.0 | 48.4 | 78.0 | 51.8 |
| gen-1 | 30 | 51.4 | 1.0 | 48.2 | 77.7 | 51.6 |
| gen-1 | 40 | 98.5 | 1.0 | 95.3 | 129.0 | 98.8 |
| gen-1 | 50 | 199.9 | 1.0 | 199.6 | 226.4 | 200.2 |
| fresh | 510 | 106.6 | 1.0 | 103.3 | 241.8 | 106.8 |
| fresh | 520 | 125.0 | 1.0 | 121.7 | 150.7 | 125.2 |
| fresh | 530 | 101.3 | 1.0 | 102.4 | 242.7 | 102.1 |
| fresh | 540 | 51.3 | 1.0 | 51.6 | 77.4 | 51.5 |
| fresh | 550 | 214.6 | 1.0 | 211.6 | 241.2 | 214.8 |

Four facts, each load-bearing for what follows:

1. **The fixture is tight.** Four of eleven trials cut at 51.3–52.0 ms against the 50 ms
   budget (1.03–1.04x), on BOTH generations; X2 is pinned at 1.0 ms on the unbuffered
   class (immediate conversion, pacing-free) in every trial. A systematically-loose
   fixture scatters every trial and every axis; this cell's pack is tight with episodic
   outliers. The assert's own verdict — "a systematically-loose fixture, not a transient
   host stall" — is falsified by its own render.
2. **The breach margins are knife-edge.** Gen-1's axis-reader breach is trial 50 at
   200.2 ms against the `[0, 50+150]` band — over by 0.2 ms. The range-gate gen-1 breach
   is X4 trimmed spread 51.3 against the 50 ms bound — over by 1.3 ms. Neither reading
   carries margin; both sit at the edge of the load distribution.
3. **The outlier trials inflate common-mode.** In every stretched trial X1, X3, X4 and
   the dispatch duration move together (X1 within 0.8 ms of the duration in ALL eleven
   trials, loaded or not; X3 within 3.5 ms below it; X4 = duration + a small offset
   except fresh trials 510/530, whose X4 exceeds duration by 135.0/140.6 ms — a stall in
   a leg AFTER the cut, see §1.2). The serial model never breaks in these renders; the
   values move together past the bands.
4. **Two belt readers, one cell.** The axis reader reddened first (the upper-band
   evaluator at :2039); the range gate reddened minutes later on the SAME certified
   fresh generation (the belt memo — one certification, two failing readers). Any fix
   that touches only one evaluator leaves the other redding main.

### 0.2 What the 2-of-2 CI red with serial-local green means

The runner was in a sustained multi-x stretch regime for the whole lane window: the
capture arm's deadline-max cut (a 50 ms budget) was delivered 48–165 ms late on episodic
trials — roughly one and three enforcement periods late, the ladder {~52, ~100–125,
~200–215} — on BOTH of the belt's generations, because the load persists across the
tens of seconds between them. This is the same regime class that killed the row-12
attempt-1 fix on 2026-10-17 (run 38995012011 — whose co-failures were these same belt
readers, both generations; that record's §1 names it "a sustained stretched regime,
demonstrated by a second, independent measurement family in the same process"). Local
serial runs pass because a quiet host delivers the cut at ~51.5 ms with ~148 ms of band
headroom. The two runs naming different keys is the same regime landing on different
cells' draws. It is a loaded-host measurement, not a property of the fixture and not a
property of the merge (which touched no timing path).

### 0.3 Slice 3's own pre-committed rule says this design is owed

Slice 3 §5.2 pre-committed: "a belted test redding on a single-stall shape (the belt
failed to absorb a transient) ... is a mechanism kill regardless of the count. A kill
does not revert the slice blind; it reopens #241 with the failing log as the next
slice's Evidence A." The axis reader's breach shape here is ONE trial per generation
(gen-1: trial 50 alone over the band; fresh: trial 550 alone) — the single-stall shape
the belt was built to absorb. The belt failed to absorb it not because the belt is
broken but because its absorption model assumed the stall clears between generations;
under sustained load it does not. This record is that reopened slice; §0.1's table is
its Evidence A.

### 0.4 Rival work already pushed (the #181 R2 pre-flight, done)

PR #504 (`fix/issue241-belt-starvation`, pushed 2026-10-20T02:51Z) targets the same red
with a starvation-exclusion patch: trials whose `dispatch_duration_ms` exceeds 1.5x the
arm budget are excluded from the range reading; below three usable trials the row
refuses as UNDER-EXAMINED; the belt message stops asserting looseness. Assessment,
evidence-first (§6 of PR #504's own numbers):

- **Convergent and right about the verdict.** Its diagnosis ("that verdict was false")
  matches §0.1.1 — independent confirmation, and its message de-fanging is a correct
  subset of this design's §4.
- **It does not fix the first-failing reader.** The diff touches `_range_gate_breaches`
  only; `_axis_upper_band_breaches` (the axis test's upper bands, the FIRST failure in
  the log at :2039) is untouched — the next sustained-load run reds main through the
  axis test identically (a 214.8 ms trial breaches the 200 band per-trial, both
  generations, belt reds). Its focused run (`-k "range_gate or belt or instrument"`)
  never collects the axis test, so its green evidence does not cover the exposed
  surface.
- **Its 1.5x threshold is the killed attempt-1 shape.** A wall-magnitude constant tuned
  between two observed samples (1.04x pacing overshoot below, 1.98x/4.0x starvation
  above) is exactly what row-12 attempt 1 died of: "no multiplier on an uncontended
  reference delivers the property — never bind on any legitimate host". A moderate
  stall of 1.2–1.4x is neither excluded (under 1.5x) nor trimmed (two such trials
  breach the spread after the one-trial trim) — the both-generations red returns with a
  nicer message. §0.1.2's knife-edge margins are why tuned constants cannot hold here.
- **It keeps main red under the heavy shape.** Four-of-five starved on both
  generations → UNDER-EXAMINED is a breach list → belt re-measures → fresh also
  UNDER-EXAMINED → both-generations red. Relabeled, not retired.

Disposition: this design SUBSUMES #504's message correction (§4) and replaces its
tuned-threshold mechanism (§2). The recommendation to the maintainer is to close #504
in favor of this slice's PR, or fold its message text in; carrying both would leave the
axis reader exposed under #504's threshold and the plan reading under this design.

### 0.5 The composition question (posed mid-design; answered from the code and the render)

A competing structural hypothesis was raised against this record's load reading: the
renders' duration ladder {~52, ~52, ~52, 98.8, 200.2} looks like "a cell whose five
trials sit at different acquisition classes", which would make the range gate
ill-posed on the cell (measuring class separation, not looseness). Refuted on four
independent grounds; the ladder is late cut DELIVERY, not class identity:

1. **No class parameter exists.** `run_trial`'s signature (:1085-1093) takes
   `arm`, `device_class`, `trial_index` and two probe flags — nothing selects a
   duration; `_run_trial_once` maps `trial_index = trial_index * 10 + attempt`
   (:1161), and the index feeds exactly two things: the per-rig db filename
   (`rig-{arm}-{device_class}-{trial_index}.db`, :1197) and the outcome's `trial`
   label. `ContinuityRig.__init__` constructs `ARigAdapter()` bare (:639) — every
   trial in a cell runs the same chunk plan (100 x 2 ms) under the same 50 ms
   budget. The five gen-1 indices 10/20/30/40/50 are the labels 1-5 at attempt 0;
   the belt's 510-550 are labels 51-55 (slice 3's no-collision range).
2. **Every rendered trial, including the 200.2 and 214.8 ones, records
   `status: 'unknown'`** — the deadline-max CUT. A trial running a longer
   acquisition class to completion returns OK; only the cut produces UNKNOWN. The
   200 ms "class" is the cut firing a full natural duration late (§1.2's worst
   ladder step), not a different dispatch.
3. **The index-to-duration mapping is NOT preserved across generations** — fixed
   per-trial classes are impossible. Gen-1's fourth trial (40) ran 98.8; the fresh
   generation's fourth trial (540) ran 51.5, while fresh 510/530 (~102-107) have no
   gen-1 counterpart except 40. Both draws sample the SAME quantization lattice
   (~52 / ~100-125 / ~200-215) at DIFFERENT counts — the signature of a stochastic
   delivery process over a fixed lattice, not of five fixed classes.
4. **The ladder is host-dependent.** The same five trials run serially on a quiet
   host all cut at ~51.5-52.0 (the lead's own local green, and slice 2's quiet
   evidence). A structural composition is host-independent and would reproduce
   locally; it does not.

So: the cell is homogeneous BY CONSTRUCTION; the fresh generation mirrors gen-1's
PARAMETERS (same code path) but not its stall episodes; and the spread reading over
the five trials is coherent as a reading — it is simply reading the host's delivery
variance under load instead of the fixture's pacing. That is §1.3's
indistinguishability, not an ill-posed composition. The design consequence the
hypothesis would have forced ("compare like with like" across classes) does not
arise; §2 stands.

## 1. Root cause, traced to the line

### 1.1 Why trials 51-55 re-measure, and what the belt is for

`_certified_cell` (:1930) is slice 3's mechanization of the frozen #159 rule's arm 4
("raise n and re-run") for the #172 record's §5 underpowered clause: evaluate the shared
cached cell (`_cell`, :1834 — five `run_trial`s on fresh rigs, the module memo); a
non-empty breach list certifies ONE fresh generation (`_belt_fresh_generation`, :1906 —
`run_trial` at `trial_index` 51–55, a range no other caller uses); `_BELT_GENERATION_RUNS`
(:1903) counts certifications and asserts `<= 1` (:1961) so a future widening of the memo
guard trips the assert instead of silently re-rolling. What it protects against, by
design (slice 3 §1.2): the TRANSIENT host stall — a 2–3-stall shape among tight trials,
absorbed by one re-measure, with a second breach redding both generations as the kill
direction against re-roll-until-green. The failure at :1972 is the kill direction firing
on a shape it was never able to discriminate: sustained load breaches both generations,
and the message asserts the one diagnosis ("systematically-loose fixture") its own
render disproves.

### 1.2 Why the capture arm's trials stretch under CI load (the physics)

The capture arm dispatches with `deadline_ns = rig.deadline_ns(CAPTURE_BUDGET_MS)` — a
50 ms budget — and expects `OperationStatus.UNKNOWN` (:1255–1259): the deadline-max cut.
The cut is enforced in the bridge's runner bracket, `_run`/`bounded()`
(`src/benchweave/host/otdp_bridge.py:237–254`): the adapter's awaitable runs under a
runner timeout of the remaining deadline; when the timer fires, the in-flight await is
cancelled and the dispatch resolves indeterminate/UNKNOWN. The device side of the rig
(`ARigAdapter.execute`, capture arm, :359–365) appends an artifact and sleeps 2 ms a
hundred times; the cancel lands at the current await point. The timer callback runs on
the runner's event loop, which is the same loop (and the same host cores) doing the
per-chunk store appends. So the cut's WALL delivery time is bounded below by the
deadline (50 ms — hence the tight 51.3–52.0 trials) and above by NOTHING the rig
controls: a starved loop or a slow store append delays the cancel's delivery, and the
dispatch runs one or three more enforcement-periods' worth of chunks. The observed
ladder {51.5, ~100–125, ~200–215} is that delay quantized by chunk-pacing and store
stalls; the natural acquisition is ~200 ms (100 chunks x 2 ms plus appends), so the
worst shape lands at ~200–215 — just past the axis band's 200 ms edge and just far
enough apart to breach the trimmed spread after one trial is trimmed.

Every recorded axis follows the cut's delivery: X1 is the max tick gap over the dispatch
window (== the duration, ±0.8 ms in all eleven rendered trials); X3 is the max in-window
landing latency (== the duration, −0.3 to −3.5 ms — frames land when the cut returns);
X4 adds the post-cut legs, which have their OWN stall exposure — fresh trials 510/530
show X4 exceeding the duration by 135.0/140.6 ms while their X1 equals the duration,
i.e. a stall in the observing tick or the safe-transition legs AFTER the cut. X2 on the
unbuffered class is an immediate conversion (1.0 ms, load-immune). The retry taxonomy
never sees any of this: a late cut is a "successful" UNKNOWN trial, `retries: 0` in
every stretched trial — nothing failed, the wall values are just inflated.

### 1.3 The structural fact that forces the design

Per-trial, fixture pacing scatter and host-load stretch enter the recorded wall values
through the SAME door — they both inflate the duration and every duration-coupled axis
common-mode. Four independent quantities (duration, X1, X3, X4-coupled-part) move
together under both causes; the only axis that separates (X2) separates by device
class, not by cause. So NO wall-domain statistic — no spread, no ratio, no threshold on
the duration, no exclusion factor — can tell a loose fixture from a loaded host within
one generation; and across generations (the belt's two draws) the two causes differ
only in persistence, which is exactly what sustained load erases. This is the same
conclusion the row-12 record reached for a different fixture ("the reference shares no
load-shaped term with arm 1's distinct costs"), restated for this one: the
discriminating signal does not exist in the wall domain. It exists in the fixture's own
DRIVING SIGNALS — what the rig asked the pacing to do — which load cannot touch. The
reading must move there.

## 2. The mechanism — the driving-signal reading, with the wall readings kept only in load-safe forms

One new recording seam, two re-derived evaluators, the belt kept as-is. Test code only;
no `src/` byte moves.

### 2.1 The plan recording (new, load-immune by construction)

`ARigAdapter` records its driving signals as it executes:

- `self.pace_log: list[float]` — `_pace` appends the `total_ms` it was asked to pace
  (one entry per call; the read/write/control arms' measured dispatch performs exactly
  one acq pace, so the trial's entry is the new log element between the dispatch's
  start and end stamps);
- `self.capture_plan_ms: float | None` — set at capture entry from the LIVE instance
  state, `self.chunks * self.chunk_ms`.

`_run_trial_once`'s outcome dict gains three deterministic fields:
`pacing_plan_ms` (the measured dispatch's paced total: the acq pace entry, or
`capture_plan_ms` for the capture arm), `dispatch_budget_ms` (the budget literal the
rig passed to `deadline_ns` for the measured dispatch), and `t_cross_offset_ms` (the
trip offset the rig scripted — the arm's constant from :1246). All three are read from
the adapter's live state / the trial's own locals at dispatch time — a fixture whose
pacing parameters regress or scatter lands in the recording by construction; host load
cannot reach any of them (pure bookkeeping, no clock).

### 2.2 The range gate reads the plan (the §5 clause re-derived — OWNER FORK, see §9)

`_range_gate_breaches` keeps its trim (`_underpowered_range_ms`, byte-identical — the
#217 pin `test_range_gate_tolerance_both_directions` is untouched and stays green) and
its 25%-of-200 ms bound, and reads it over the cell's five `pacing_plan_ms` values. The
per-axis loop collapses to the single plan axis, and the design claims this openly: the
four wall axes were four noisy views of ONE fixture property (the driving signals'
cross-trial consistency) plus views of properties better pinned elsewhere (X1/X3's
serial-model structure -> §2.3's couplings; X2's class separation -> the existing §5.2
separation test; X4's fixture-scripted parts -> §2.3's wiring pin). Teeth, checked
against the shapes that must still fire: a parameter-scattered fixture (per-rig ladder
on `acq_ms` or `chunk_ms`) scatters the plan and breaches on gen-1; the forced-loose
pin (§5 AR-1.1) moves its ladder to the construction/call seam, deterministically. A
behavioral pacing regression that changes CALL ARGUMENTS (wrong total, wrong chunk
plan) lands in the recording; the residual blind spot — right arguments, wrong sleeps —
is bounded by the wall floors and couplings and DISCLOSED (§7 D4).

### 2.3 The axis test: the wall upper bands retire, load-safe forms replace them

`_axis_upper_band_breaches` is deleted; the axis test reads `_cell` directly (no belt —
nothing it still asserts is a re-measurable band) and asserts, per trial, inline:

- status UNKNOWN unchanged (:1259's expectation, the cut's existence — catches a
  budget regressed past natural completion, which returns OK);
- NEW floor `dispatch_duration_ms >= _ARM_DISPATCH_MS[arm] - 2` (the cut cannot fire
  before the deadline; the pacer only overshoots — load inflates, it never deflates);
- NEW couplings, ONE-SIDED in the direction load cannot reach:
  `dispatch_duration_ms - x1_ms <= 50` and `dispatch_duration_ms - x3_ms <= 50` (the
  serial model's structural content — the blackout spans the dispatch; a tick inside
  the window or an emission schedule that misses the window start shrinks the gap
  below the duration). The upper sides (`X1 <= dur + k`, `X3 <= dur + k`) are NOT
  asserted: post-cut tick and landing stalls inflate exactly those, the class §1.2
  measured (fresh trials 510/530);
- NEW wiring pins: `dispatch_budget_ms == _ARM_DISPATCH_BUDGET[arm]` and
  `t_cross_offset_ms == _ARM_TRIP_OFFSET[arm]` (deterministic; catch arm/budget wiring
  regressions the retired absolute ceilings used to catch incidentally);
- unchanged: `len(trials) == 5`, all four axes recorded, `in_window_frames >= 1`,
  `retries <= 2`, the write-leg gap band (:2077 — DEFERRED, §7 D2), `_assert_x1_floor`
  on both generations (its capture bound is 0 and stays vacuous, as today).

What retires, named: the absolute wall ceilings `dispatch_duration_ms <= dispatch+150`
and `x1_ms <= dispatch+150`, and with them the post-window tick-rhythm tail the X1
ceiling weakly guarded. The retirement argument: an absolute ceiling on a
load-inflatable quantity is a constant tuned against the host's stall distribution —
the killed attempt-1 shape (§0.4); the couplings are STRICTLY STRONGER on the serial
model's break class (a 120 ms X1 shortfall from a 200 ms non-capture dispatch passes
today's 200 ceiling; the coupling reds at 50), equal on the capture cell (today's
ceiling is as blind there as the coupling — both pass a 25 ms mid-dispatch-tick shape),
and the scale they leave unguarded from above (a moderate budget regression between
budget and natural completion) is caught at its edges — the floor below, the status
assert at completion — with the interior window DISCLOSED (§7 D4's sibling; the
census's watch list owns it).

### 2.4 The belt: kept, not removed — the coverage argument

The lead's question, answered directly: the retry loop is NOT the defect; its INPUT
was. Removing the belt would lose the frozen #159 arm-4 "raise n and re-run" seam and
the both-generations kill direction for the one failure class that still deserves it —
a genuinely-loose fixture. After this slice the belt's evaluators read only the plan
domain (§2.2; the axis test no longer belts anything), so: a transient breach (a fluke
in the recording seam) is absorbed by the one re-measure exactly as designed; a
both-generations plan breach is now REALLY a systematically-loose fixture — the plan
cannot be host-stretched — and reds with both plan vectors rendered. The memo, the
`<= 1` bound (:1961), and the AR-1.2/1.3 belt pins are untouched. Sustained host load
no longer reaches the belt's input at all: the axis reader has no band left to breach
and the range reader's values are load-immune — the belt cannot redden on the host
class, which is the only honest meaning of "removing the load sensitivity".

### 2.5 Considered and rejected: the realized-duration ratio reading

The obvious "make the reading match its own stated semantics" fix — compare each
cell's trimmed spread against 25% of THAT CELL's measured dispatch duration, so
uniform stretch cancels — was computed against the exact CI values before being
rejected. It does not clear the observed red; it makes the reading MORE
load-sensitive:

| generation | axis | trimmed spread | 25% of mean dur | 25% of median dur | old constant 50 |
|---|---|---|---|---|---|
| gen-1 | X1 | 47.1 | 22.7 RED | 13.0 RED | green |
| gen-1 | X4 | 51.3 | 22.7 RED | 13.0 RED | RED |
| fresh | X1 | 73.7 | 30.0 RED | 26.7 RED | RED |
| fresh | X4 | 92.0 | 30.0 RED | 26.7 RED | RED |

(gen-1 durations [52.0, 51.8, 51.6, 98.8, 200.2]: mean 90.9, median 52.0; fresh
[106.8, 125.2, 102.1, 51.5, 214.8]: mean 120.1, median 106.8. Trim per
`_underpowered_range_ms`.) The mechanism of the failure: the CI stretch is EPISODIC
per trial, not uniform — three of five gen-1 trials cut on time, so the denominator
stays near the on-time pack while the spread still carries a stretched trial among
the trimmed remainder. A ratio cancels uniform dilation; it AMPLIFIES episodic
dilation (the numerator's stretched trial survives the one-trial trim; the
denominator's stretched trial is one vote of five). The per-TRIAL normalization
(x_i / dur_i) is load-immune for X1 (0.992-0.999 across both generations, computed)
and X3 (same coupling) but not for X4 (per-trial ratios 1.12-2.38 across the two
generations: the +26-46 ms offset over a varying denominator, plus the post-cut leg
stalls of §1.2's fresh 510/530), and the clause is stated in ms — a ratio band has
no §5 lineage. Both ratio variants therefore fail the AR-0 replay; the driving-signal
reading of §2.2 is the only form that covers all four arms load-immune while keeping
the clause's ms semantics.

## 3. The message correction

The false verdict dies at :1973–1975. The belt's both-generations message becomes a
verdict its reading can actually support: a plan breach renders "the pacing schedule
scattered on both generations — a systematically-loose fixture; §5's honest verdict is
this red (fix fixture pacing, decide nothing)" with both generations' plan values and
the wall renders carried as context (the wall values stay diagnostic — they classify
the host regime for whoever reads the log). The corrected diagnosis of the 2026-10-20
class lands in the range-gate and axis docstrings and here (§0.2): a sustained runner
stretch delivering the capture cut 48–165 ms late on both generations; the old wording
cost the next responder the same investigation twice — PR #504's author and this design
each re-derived it from the same renders within hours. `_render_belt_trial` additionally
gains X4's three-way decomposition legs (onset->obs, obs->enter, enter->action) so the
next both-generations render shows WHICH leg moved — the 510/530 shape (§1.2) is
currently invisible in the render.

## 4. Minimal first increment, and what it defers

Build order (RED-first where behavior changes, one slice per commit):

1. Commit 1: this design record.
2. The plan recording (§2.1) + the re-derived evaluators (§2.2–2.3) + the message
   correction (§3) + the render legs. RED: the CI vectors replayed through the OLD
   evaluators red (scratch fingerprint, §5 AR-0); the plan-ladder pin reds on both
   generations on the new code (AR-1.1).
3. The pins: forced-loose re-planted at the construction/call seam (input-domain —
   deterministic NOW because the reading is load-immune; the #439 lesson in its
   corrected form: that fix moved a PIN's scatter to the output domain because the
   reading was wall-domain; this slice moves the READING to the driving-signal domain,
   so the pin's natural deterministic home is the input domain again);
   the pace-allocation pin re-homed (its belt certification now comes via a plan
   breach; its ladder is call-time, so it lands in `pace_log` by construction); the
   load-shape replay control committed (AR-1.4); the AR-1.2/1.3 belt pins and the #217
   trim pin untouched.
4. Docs: `docs/internal/drift-and-obligations.md` — the conventions line's belt
   sentence gains the plan-reading sentence and the axis-reader retirement; the timing
   lane row's "Does NOT catch" clause updates. The #172 instrument record's §5 note:
   an amendment line pointing here (the reading moved domains; the clause's intent is
   unchanged). Issue #241 outcome comment with §5's numbers.

### Deferral table

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D2 | the write-leg gap band [150, 350] (:2077) — same load exposure, unreddened; re-derive with the same plan+coupling pair once the write leg's own duration and plan are recorded | this issue's next slice | any in-lane red of the write-leg band |
| D3 | the control-arm §5.2 ceilings (medians/maxima, `control_x3 <= 3*POLL_MS` et al.) — unchanged exposure, slice-3's out-of-scope note stands | unchanged | any in-lane red of a §5.2 ceiling |
| D4 | the uniform sleep-behavior blind spot (right plan, wrong sleeps) and the moderate-budget-regression interior window (§2.3) | an injected-clock unit pin of the pacer; the census watch list | a pacing regression that passes this slice's pins |
| D5 | belt visibility (print-only usage) — unchanged from slice 3 | documentation | a belt incident lacking the usage line |

## 5. Measurable proof and the pre-committed acceptance rules

### 5.1 Build-time (PR) acceptance

- **AR-0 (deterministic RED of the failure shape, partly given):** the two CI renders
  ARE the red on unfixed code (runs cited in the header). Additionally, replayed as a
  scratch fingerprint probe: the eleven trials of §0.1's table fed through the OLD
  evaluators redden byte-class-identically (the axis band at 200.2/214.8; the trimmed
  X4 spread at 51.3) — collected count checked, true exit code read per the rtk rule.
- **AR-1 (teeth and load-immunity, all arms):**
  1. *Forced-loose, kill direction:* a construction-seam ladder on the plan
     (per-rig `acq_ms`/`chunk_ms` scatter) breaches gen-1 AND the belt's one fresh
     generation; the test fails rendering BOTH generations' plan vectors;
     `_BELT_GENERATION_RUNS[key] == 1`.
  2. *Belt absorption + no-structural-rerun pins:* unchanged from slice 3, green.
  3. *Neutralized-recording control (scratch):* the plan recording fed constants makes
     AR-1.1 go GREEN — proving the pin reads the plan seam, not the wall (the
     RED-disable check: disable the mechanism, the effect disappears).
  4. *Load-shape replay control (committed):* the §0.1 table's trials — tight plans,
     wall values stretched up to 4.3x — evaluate CLEAN through both new evaluators,
     and `_BELT_GENERATION_RUNS` stays EMPTY (zero certifications: the host class
     never reaches the belt). This is the matched control fluff cannot pass: it is
     the exact CI red, replayed. Two named plants inside the control, per the
     design review's request: (a) UNIFORM stretch — every wall duration and axis
     value scaled by one factor — reds the OLD evaluators (spread inflates against
     the constant band) and evaluates clean on the new ones (the plan is untouched
     by definition); (b) the §0.1 episodic shape itself, which additionally reds
     the §2.5 ratio form on both generations (the table above) — the control pins
     that the new reading is immune to the shape that defeats both wall-domain
     alternatives.
- **AR-2 (five consecutive greens):** the touched tests green 5 consecutive local
  serial runs, each showing zero belt certifications on the quiet host (unchanged
  quiet behavior).
- **AR-3 (partition integrity):** markers unchanged; the collect diff recorded in the
  PR body (net: +1 committed test, the replay control; the pins re-homed in place).
- **AR-4 (both lanes):** `gates` and `timing` green from the COMPLETE
  `scripts/merge-verified.sh` rollup; one cold unfiltered union run green. Lane cost
  DISCLOSED as a reduction: the belt's four-cell re-measure (~20–25 s worst case,
  slice 3 AR-4) no longer fires on loaded hosts; quiet cost unchanged.
- **AR-5 (evidence discipline):** every number from `--junitxml` attributes or true
  exit codes; fresh-cache bare mypy; bare ruff (FAST lane, no docs exemption).

### 5.2 Post-merge acceptance — pre-committed BEFORE any post-merge number exists

Unit of observation: one `timing` job execution (slice 3's rule). Local runs satisfy
nothing.

- **SHIP:** over the first **40** timing-lane executions post-merge: zero
  both-generations belt reds of ANY kind, AND zero axis-test reds, AND the live
  ≤2-red-executions/40 family rule holds (every red in a named family).
- **KILL (any one fires):** a both-generations belt red (after this slice that shape
  means a genuinely-loose fixture OR a broken recording seam — either falsifies the
  slice's central claim); an axis-test red on a load shape (the retirement was
  incomplete — the couplings/floors are load-safe by argument and must prove it in
  lane); ≥3 red executions in 40 (the slice-3 volume kill, inherited).
- **UNDERPOWERED, not conclusive:** fewer than 40 executions sampled when a candidate
  red arrives; a red whose raw log lacks the pre-assert stamps (pull the raw log
  BEFORE any rerun — the row-12 AR-7 lesson); a job-level timeout kill (lane-infra,
  never a family red).
- **Baseline honesty:** the class this slice targets reddened main twice in two days
  (and co-failed a third run on 2026-10-17); the bar says that class stops redding
  entirely, and nothing else starts.

## 6. Precedent (all in-tree, extended not invented)

- **The D4' in-run-relative ceilings (slice 3's fold, landed):** `gap <= realized
  duration + TOLERANCE` re-based a load-hostage absolute ceiling onto the in-run
  measured quantity — §2.3's couplings are the same move per-trial.
- **The row-12 attempt-2 doctrine (2026-10-17, design of record):** "de-clock the
  scaffolding, keep the measured quantity real"; its attempt-1 kill is this slice's
  standing rejection of §0.4's tuned threshold and of any wall-magnitude bound on
  load-inflatable quantities. This slice applies the doctrine's SPIRIT at the READING
  level: the quantity §5 measures (instrument precision) is re-homed to the domain the
  host cannot stretch, because for THIS fixture the wall reading IS the scaffolding.
- **The #439 outcome-domain lesson, corrected application:** pins plant where the
  reading reads. #439's pin plants output-domain because the reading is wall-domain;
  this slice's reading is driving-signal-domain, so its pin plants input-domain —
  both directions of one rule, determinism of the pairing.
- **The #217 one-trial trim + both-directions pin:** kept byte-identical; the trim
  pin stays green untouched.
- **Slice 3's belt machinery (`_certified_cell`, memo, AR-1.2/1.3 pins):** kept
  verbatim; only the evaluators' input moves.

## 7. Invariant, drift, and CI impacts

- **No CTL/STO/CON/REG text moves.** No `src/`, `standards/`, schema, workflow, or
  SDK byte. The rig's production objects are untouched; the recording seam is
  fixture-side bookkeeping only.
- **§5 measurement semantics — the owner fork, stated plainly (the maintainer must
  ratify):** slice 2's standing rule says "§5 clauses are not load-renegotiable" and
  "a §5 reading change is an owner fork". This slice does NOT renegotiate the clause's
  intent (a cell whose trials scatter reads UNDERPOWERED; the trim, the 25%, the
  denominator all stand) but it DOES change the machine-checked reading's domain
  (wall per-axis -> driving-signal plan). The evidence forcing the fork: §1.3's
  indistinguishability proof and §0.1's renders. The alternative — keep the wall
  reading, accept sustained-load reds — is defensible ONLY with its price named: main
  red on no-source-change merges, at the observed rate, indefinitely (§0.2). This
  design recommends the fork; the owner decides.
- **A06 (evidence over assertion):** strengthened — the belt's verdict becomes one its
  reading can support; the false-verdict class (message asserting what the render
  disproves) is eliminated for this reader; the render gains the decomposition legs.
- **Obligations walked:** the timing lane row and the conventions line
  (`drift-and-obligations.md:677, :723–735`) gain their sentences; no CI-map shape
  change; no dependency motion; the #172 instrument record gains an amendment line.
- **CI cost:** a reduction on loaded hosts (no belt re-measure), unchanged otherwise;
  net +1 committed test.

## 8. Tier and the Step-1 keyword scan (#254)

Expected diff: this record, `tests/integration/test_cross_instance_continuity.py`
(recording seam, two evaluators re-derived, inline couplings/floors/wiring pins, belt
message + render legs, pins re-homed, one new replay control),
`docs/internal/drift-and-obligations.md` (two sentence-level edits), and the #172
record's amendment line. Tier by the rubric's path rules: **Tier 2** — a test-code
change under `tests/` plus records/docs; no Tier-3 path matches (no `src/` byte, no
schema, no registry, no fixture lattice, no dependency, no submodule). The review
re-derives the tier over the real diff; if any ADDED line trips a keyword the slice
takes the Tier-3 lane and the builder re-runs the scan pre-PR and records counts — the
file's existing context carries such words, and the added lines are written to avoid
introducing any (the docstring edits say "safe transition", never the engine class's
name; the recording seam is arithmetic and dict fields).

Scan result over this record's full text (mechanical, after drafting): **0/8** — the
count line deliberately does not spell them out; the rubric's Step-1 list is the
authority. The expected code diff's added lines: 0/8 by construction.

## 9. Top risks, each with its falsifier

1. **The plan reading is near-vacuous (reviews hard, adversaries harder).** It reads
   what the fixture asked of itself. Counter-evidence in-diff: AR-1.1 (a scattered
   plan reds both generations), AR-1.3 (neutralizing the recording greens the pin —
   the reading demonstrably reads the seam), and the wall floors/couplings/status
   bounding gross behavior. The honest residual — uniform sleep-behavior regressions —
   is disclosed with its home (D4). Falsifier: a pacing regression that passes every
   pin in this slice.
2. **The §5 fork is decided wrong (the owner keeps the wall reading).** Then this
   slice is not built in this form; the fallback is #504's shape MINUS its tuned
   threshold problem — i.e., message correction + axis-reader fix only, with the
   sustained-load red accepted BY NAME in the residual register. The design's §4
   (message) and §2.3 (axis reader) survive either decision independently.
3. **The one-sided couplings are not actually load-safe.** The argument: load
   inflates X1/X3's inputs; the asserted direction (`dur - X1 <= 50`, `dur - X3 <=
   50`) requires the axis to SHRINK relative to the duration. Falsifier: a lane red of
   a coupling assert on a load shape (the §5.2 mechanism kill).
4. **The recording seam corrupts the trial's timing (observer effect).** `pace_log`
   appends are in-memory list ops on the adapter's own coroutine; `capture_plan_ms`
   is one multiplication. Falsifier: a quiet-host distribution shift in AR-2's five
   runs vs slice 2's Evidence C quiet figures.
5. **Collision with #504 in flight.** Both touch `_range_gate_breaches`; whichever
   lands second rebases. Subsumption disposition in §0.4; the maintainer picks.
6. **The fresh-generation 510/530 shape (post-cut leg stall) hides a real engine
   regression.** This slice renders the decomposition legs (§3) but does not gate
   them. Falsifier/watch: a render whose obs->enter or enter->action leg is
   systematically (not episodically) inflated — that is a new census row, not this
   slice's.

## 10. Verdict

**BUILD** — with the §5 owner fork named for ratification before the build (§7). The
premise is verified (the renders disprove the test's own verdict; the wall domain
provably cannot separate the two causes; the belt's kill arm fired by its own
pre-committed rule); the mechanism extends landed precedent (D4' couplings, the row-12
doctrine, the #439 pairing rule); the acceptance rule is falsifiable in both
directions with a matched control built from the exact CI red. DON'T-BUILD would be
right only under the §9.2 owner decision to keep the wall reading and accept the red
class by name — a defensible call this design does not recommend, with two main reds
in two days as the price already paid.

## 11. Post-review fold amendments (2026-10-20, after the adversarial review)

The body above is frozen history (pushed commits); this section records the
review fold's corrections. One MED executable, two LOW claim defects;
everything else null and freshly enumerated.

1. **MED-1 — §2.3's edges claim was falsified on one class; the plan VALUE
   pin closes it.** §2.3 claimed the scale the couplings leave unguarded
   from above is "caught at its edges — the floor below, the status assert
   at completion". The adversary's probe doubled the read-leg pacing only
   (first `_pace` per adapter, write leg untouched): durations 401.2–403.0
   ms, X1 ~400–403, plan honestly recorded 400.0 — and BOTH live readers
   stayed green (the posture still completes OK under the 700 ms budget,
   the floor passes, the couplings see only the ~0–3 ms gap, the range
   gate reads cross-trial consistency and all five plans sat equal at
   400), while the retired ceiling reded the same outcomes 10/10. The
   write-leg band cannot see it (a different leg); the disclosed D4 window
   covers a moderate budget regression, not a read-dispatch scale
   regression. The fold pins the plan VALUE (`pacing_plan_ms ==
   T_ACQ_MIN_MS`, non_capture only — load-immune by this slice's own
   construction, so it cannot false-red under host load and reds the
   doubled shape deterministically). Capture-side is not value-pinned and
   the asymmetry is explained in the pin's docstring:
   `capture_plan_ms` is computed at capture entry from the same
   attributes the chunk loop iterates — there is no dispatch-time ask
   distinct from the construction parameters, so a value pin there would
   pin the constructor, not witness the dispatch.
