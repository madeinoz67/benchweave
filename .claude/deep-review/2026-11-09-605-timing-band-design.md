# Issue #605 — the control-arm timing band: can #576's clock seam apply?

Public tier. No client, bench, operator, or corpus names; the CI observations
below are venue-neutral runner noise on synthetic fixtures.

Verdict: **the mechanism cannot be applied to this arm — close #605 with that
finding.** The issue's own charter ("say so and close this issue with that
finding rather than raising the bound") names this as a first-class outcome.

Verified against `origin/main` at `16ff3c94`, with one disclosure about the
checkout: the primary checkout's `main` sits BEHIND origin at `084c5e6c` (the
#608/#610/#611/#612 merges are not checked out here). That does not touch the
analysis: `tests/integration/test_cross_instance_continuity.py` — the whole
subject of §2–§3 — is byte-identical between `084c5e6c` and `16ff3c94`
(`git diff main origin/main -- <file>` is empty), and §1's seam description is
verified against the `origin/main:...` blobs directly (the stale checkout
predates the seam).

Review tier (per #254, stated at design time): **Tier 3** — the slice's entire
expected diff is this record (docs only), and its text carries Step-1 keywords
(exact counts and their provenance in §8). The rubric's interplay rule says a
docs-only diff that carries the keywords still takes the Tier-3 lane; the deep
lane is bought by what the text carries.

## 0. The question and the answer

#605's "Fixed means" prescribes #576's mechanism — a virtual clock threaded
through the ports, not a raised bound — and asks, in effect: does that mechanism
reach `test_control_arm_and_separation`?

**Mechanically, yes: every clock the rig reads is already an injected port, and
a `TestClock` can be threaded with zero production change. Semantically, no: the
assert the flake reddens is a measured-latency magnitude, and a virtual clock
cannot make a magnitude load-insensitive without making it authored — at which
point it detects nothing.** The seam de-times orderings, outcomes, and budget
expiries (what #576's control asserts). It has no purchase on magnitude
separation (what this control asserts). The distinction, in one sentence:
virtual time advances either by test authorship (the reading becomes a
tautology of the authored schedule) or by the real clock (nothing was de-timed);
there is no third way for a value that is defined as real elapsed time.

## 1. What #576's mechanism is, as landed (PR #600, `50cb6fec` + `ed487297`)

- A clock seam on the composition factory: `_build_run_factory` in
  `src/benchweave/interfaces/app.py` gained `clock: CompositionClock | None =
  None` (`:781` on origin/main; `SystemClock()` when unset), so the monotonic
  the whole run derives from became injectable.
- The demo control moved onto one `TestClock` (`src/benchweave/control/clocking.py:69`
  on origin/main) threaded through both factory ports, with its authored
  budgets commissioned
  for real-time headroom — because the bridge's deadline wrapper enforces
  virtual deadline *values* as real seconds (`asyncio.timeout`,
  `src/benchweave/host/otdp_bridge.py:241`; the vault pins this residual).
- A timebase pin: every stamp must land inside the virtual window, so any
  reintroduced real-clock stamp self-reddens.

What made that work: the demo control asserts **outcomes and orderings**
(`outcome == "passed"`, `"ended" in kinds`). Orderings become deterministic
virtual arithmetic; outcome budgets get venue headroom. Neither lever touches a
measured magnitude.

## 2. The arm, read against the tree

`tests/integration/test_cross_instance_continuity.py` — the module is one of
the two real-paced rigs by design (header, lines 81–85; `pytest.mark.timing` at
line 86; the placement ruling is #241 slice 1, recorded in
`docs/internal/drift-and-obligations.md:767`).

The rig constructs the production objects **directly** — it never calls
`build_run`, so #576's landed seam does not reach it. What it does use are the
same ports, injected:

- `ContinuityRig.__init__` (`:598`): `self.clock = SystemClock()` (`:616`),
  `self.wall = SystemClock()` (`:617`), a `StretchedWall` for the divergent-wall
  probe (`:618`) — proof by existence that wall injection through these ports
  works on this rig today.
- `build_capture_services(clock=time.monotonic, wall=self.wall.now_iso, ...)`
  for both devices (`:650`, `:673`); `build_stream_services(wall=...)` (`:682`);
  the protection engine gets `rig.clock, rig.wall` (`:1433`).

The flaked assert (`:2321`): `assert control_x3 <= 3 * POLL_MS` — POLL_MS = 50
(`:115`), bound 150 ms. Recorded exceedances: 301.068 ms (2026-11-07, six-way
parallel load, a diff touching no control code) and 196.33247 ms (PR #612's
`timing` lane; the same run's long arms reached dispatch scale, so the rig
paced correctly — the landing was late, not the emission). Same bytes green on
re-run both times: load, not regression.

X3's construction (`:1377–1400`): for every in-window frame,
`latency_ms = (landing_ns − emit_ns) / 1e6` where

- `emit_ns` is authored schedule arithmetic — `subscribe_mono_ns + delivered ×
  FRAME_PERIOD_MS` (`:572`), stamped in-event as `x-rig-emit-ns` (`:582`), with
  `subscribe_mono_ns` from `services.monotonic()` (`:465–466`);
- `landing_ns` is `self.clock.now_ns()` at the `_on_event` seam (`:812`).

So X3 = the real delivery lateness of the poll path against an authored
schedule. The bound's regression target is exactly that: the landing path
sitting on a frame for more than ~3 poll rounds.

## 3. Why the mechanism cannot apply — three grounds

**Ground 1 — the quantity is real elapsed time by definition.** Under a
`TestClock` threaded through every port above (mechanically: swap `:616`'s
clock, the `clock=`/`wall=` arguments at `:650`/`:673`/`:682`, and the adapter
schedule follows via `services.monotonic`), `now_ns()` returns
`start_ns + elapsed`, and `elapsed` moves only when something calls
`advance`/`wait_ns` (`clocking.py`, `TestClock`). Nobody advances virtual time
between emission and landing except the test's own authorship — so control X3
reads whatever the author advanced: a tautology of the schedule being asserted
against itself. Keep any real term in either stamp and the real load term is
back. The 301 ms and 196 ms exceedances are the real event loop's delivery
delay; a seam that hides them hides every real delay of that shape.

**Ground 2 — the arm's whole point is magnitude separation.** The docstring
(`:2298–2301`): "a control that passes both ways proves nothing." The test
asserts the long arm's X2/X3/X4 *reach* dispatch scale (`:2318`, `:2320`,
`:2322`) while the matched short-T control stays under floors (`:2319`,
`:2321`, `:2323`) and must FAIL its acquisition (`:2305`). Under a virtual
clock the long arm reaches 200 virtual ms by construction — always, even if the
pacing machinery broke — and the separation the instrument exists to demonstrate
becomes authored. #576's own record is explicit that its fix works because
"no amount of real CPU starvation can compress virtual ordering" — ordering,
not magnitude.

**Ground 3 — the placement was already ruled, and the residual is already
disclosed.** `docs/internal/drift-and-obligations.md:767`: a real-clock ms bound
either carries the `timing` marker in the dedicated serialized lane **or** the
quantity moves to an injected clock. This bound followed the first clause. The
lane's row (`:737`) discloses what that buys: "Does NOT catch: a guarantee of a
quiet host — a noisy neighbor can still stretch a band." Instance A is that
disclosed residual, not an unaddressed gap. And where de-timing *was* possible
in this rig family, it was already done: the 2026-10-20 plan-reading slice
moved the range gate onto the load-immune `pacing_plan_ms` recording ("the
recording has no clock in its path") and retired the axis test's absolute wall
ceilings in favor of one-sided couplings/floors/wiring pins. The ceilings that
survived on the control arm survived because a landing latency has no
clock-free recording to read — every recording seam here (`tick_times` `:803`,
`snapshots` `:808`, `events` `:812`) is stamped by the injected clock.

The minimal diff, named for completeness: thread one `TestClock` through
`ContinuityRig.__init__` (`:616–618`, `:650`, `:673`, `:682`), derive the
adapter schedule from it (`:465`), and author the drain (`:869–936`) as virtual
advances. That diff builds; Grounds 1–2 are why building it produces an
instrument that cannot fail for the reason it exists.

## 4. Proof — deterministic probes, RED-first

Load-shaped failures cannot be reproduced on demand, so the evidence is a
matched probe pair on scratch worktrees (the F5-margin-bracket idiom), run solo
on a quiet host. Nothing commits.

- **Probe A — the bound detects today.** Inject a fixed 400 ms delay into B's
  delivery path (the `next_event` seam of the B adapter, or the `_on_event`
  landing wrapper). Run
  `test_control_arm_and_separation` unmodified. **Expected: RED at `:2321`
  with control X3 ≥ ~400 ms** — the fixed sleep dominates the 150 ms bound
  deterministically (400 ≫ 150 + any solo-run jitter). This states what fails
  today: the current ceiling catches a delivery delay of the class it exists
  for.
- **Probe B — the de-timed bound cannot detect.** The identical delay
  injection, onto the §3 de-timed variant (TestClock through every stamping
  port; the harness's real `time.sleep` calls stay — they advance nothing
  virtual). **Expected: GREEN at `:2321`** — emission and landing are both
  authored virtual arithmetic; a real 400 ms stall moves no virtual reading;
  control X3 reads ~0 while the regression Probe A caught sits there invisibly.

## 5. Pre-committed acceptance rule (written before any probe runs)

- **CLOSE #605 WITH THE FINDING if** Probe A reds (X3 in the ≥ 400 ms class)
  **and** Probe B greens under the identical injection. The finding then holds:
  a measured-latency magnitude cannot be both load-insensitive and
  regression-detecting under a clock seam.
- **REOPEN TOWARD A BUILD if** Probe B reds under the injection — the de-timed
  variant still detects the real delay. My structural claim ("virtual time
  advances only by authorship or by the real clock") is then wrong somewhere;
  the design reopens with the probe transcript as first evidence.
- **DIFFERENT FINDING, STILL CLOSE, if** the de-timed variant cannot complete a
  trial at all (freshness verdicts rejecting virtual stamps; the drain capping
  on virtual arithmetic) — that is an independent inapplicability: the seam
  cannot even express the rig. The issue closes naming *that*, with Probe A
  still establishing the current bound's detection power.
- **#605's own measurement shape, and why it cannot attach:** the issue's
  acceptance form — a stated execution count across at least two venues, KILL
  if the flake rate does not fall — presupposes a mechanism that lands and
  changes a per-run probability. A closure-by-finding lands nothing; there is
  no post-fix rate, and the KILL condition is discharged vacuously by not
  starting the work. The deterministic pair above is the honest substitute. A
  rate *census* of the residual is a different question with its own carrier
  (deferral 4).

The finding generalizes to the class #605 tracks: any future Instance-A red on
this rig family's magnitude bands is the lane's disclosed noisy-neighbor
residual, and the doctrine's other clause (TestClock for order/budget
quantities) already governs everything that *can* move.

## 6. The two `gates` failures: out of scope, and the carrier they need

Both PR #611 failures (same commit re-ran green) are **not** Instance A and do
not belong in #605.

- `test_l11_two_concurrent_stops_one_action_truthful_reports`
  (`tests/cli/test_lifecycle.py:886`): a `supervision_hold_desync` error where
  a typed refusal was expected. The asserted quantity is a protocol outcome —
  a report shape — not a band. This is #605's Instance B verbatim ("a run
  outcome that differs from the expected outcome"), and it is a supervision
  doorbell interleaving question needing its own investigation.
- `test_abort_deregisters_and_the_pair_starts_clean`
  (`tests/interfaces_ui/test_ui_stream.py:259`): the fired assert (`:286`) is a
  wait-for-observable loop — poll the registry every 20 ms up to a 5 s budget.
  The budget is synchronization, not a measured band: the quantity under test
  is a state transition (the generator's `finally` deregisters; the next stream
  starts clean). A starved async deregistration on a loaded runner exhausts the
  sync budget and the outcome assert fires. This is outcome-class like Instance
  B, and — decisively — it has an honest cheap fix #605's charter forbids for
  itself: commission the sync budget (or make the drain event-driven) without
  losing any detection, since the observable assert catches a genuinely broken
  deregistration on first poll. Absorbing it would either block that fix or
  blur the issue's charter.

**The separate carrier** (one issue, consolidating #605's own two Instance-B
records — the missing evidence-gap row and the `outcome_unknown` — with
tonight's two): name it **"Loaded-runner outcome divergences: the #605
Instance-B ledger"**. Claim: four gates-lane reds on diffs that touch nothing
on the failing path, same-commit re-runs green, all four present as an expected
result failing to materialize (a typed refusal replaced by a supervision
desync; a teardown observable starved past its sync budget; an evidence row
absent; a body outcome `unknown` instead of `passed`). The investigation
question: one mechanism (loaded-runner scheduling starving async completion
paths) or several. Explicitly not the timing-band class; explicitly not
treatable by the clock seam; each member's disposition is its own call, and the
abort arm's sync budget is commissionable without detection loss.

## 7. Invariant, drift, and surface impacts; deferrals

- **Invariants:** none touched, none amended. A02 stands as the module header
  states it (`:88–94` — every number is a fixture discriminability parameter,
  never a commissioned bound); CTL-8's wrapped-monitor seams are what the rig
  arms; CON-2's digest lattice untouched (no fixture bytes move). No schema,
  no persisted format, no registry motion, no SDK surface.
- **Obligations walk:** row 767 (real-clock doctrine) is followed, not amended
  — the bound already lives in the timing lane under the row's first clause,
  and this record documents why the row's second clause is unavailable for this
  quantity class. Row 737's disclosed "no guarantee of a quiet host" is the
  finding's home; the closure motion may append one clause there pointing at
  the #605 finding — that lands with the closure, not with this record. No MCP
  / REST / CLI / operator-doc / device-guide / vendored-standards / fixture-
  lattice / SDK surface moves. CI cost: zero (the only diff is this record;
  probes are scratch).
- **Named deferrals:** (1) a load-cancelling re-band of the control-X3 ceiling
  (couple it to the same run's realized dispatch scale, the #241 one-sided-
  coupling idiom, under the A/A-floor discipline) — its own carrier if the
  owner wants the residual gone; #605's charter forbids it here. (2) a
  count-domain axis ("every frame lands within N poll rounds" — a clock-free
  quantity the plan-reading idiom could carry) — named only, not designed.
  (3) the Instance-B carrier of §6. (4) a residual flake-rate census of the
  lane's noisy-neighbor exposure, only if the owner wants it quantified.
  (5) #576's own deferral 4 (gateway-level clock injection through the
  server-side run construction) stays deferred — its trigger, a gateway-path
  control proving load-flaky, did not fire: this rig constructs the production
  objects directly and is not a gateway-path control.

## 8. Tier and keyword scan (Step 1, #254)

Tier 3, keyword rule, first-match-wins: the slice's whole expected diff is this
record, and its text carries the keywords. Measured counts over the record
(case-insensitive substring, the whole file): `asyncio` 2; `protection` 4;
`migrate` 2; `threading` 1; `subprocess` 1; `sha256` 1; `hashlib` 1;
`recovery` 1. Of these, the content-bearing occurrences are `asyncio` (§1, the
bridge deadline-wrapper residual), `protection` (§2, the engine citation), and
`migrate` (§9, "migrates to the band class") — every other count is this
paragraph's own enumeration, which self-fires by construction, the outcome the
rubric's interplay clause names as intended. Either way the rule fires and the
lane is deep: this record discusses why a protective-path magnitude bound (X4's
hazard-to-action latency shares the finding) cannot be de-timed, which is
precisely the content the deep lane exists to check.

## 9. Top risks to the finding, each with its falsifier

1. **The structural claim is wrong** — some construction makes a de-timed
   magnitude still detect real delay. Falsifier: Probe B redding under the
   injection (acceptance-rule reopen branch).
2. **A clock-free recording of landing latency exists** that I did not find —
   the plan-reading idiom extended to delivery. Falsifier: locate a recording
   seam on the delivery path with no clock in it; I checked the rig's three
   recordings (`:803`, `:808`, `:812`) — all stamped by the injected clock. If
   found, deferral 1 becomes buildable as a re-band, not a de-timing.
3. **The gates-failure classification is wrong** — e.g. the supervision desync
   turns out to be a wall-clock budget inside the doorbell. Falsifier: the
   Instance-B carrier's own investigation; if it holds, that member migrates to
   the band class and #605's closure text gains a caveat, not a reopen.

## 10. Addendum (2026-11-09, post-merge): the probes were executed

§4 committed a pre-committed probe pair with its predictions. This addendum
records what the runs actually showed. It is an addition, not an edit: rewriting
§4 after the runs would destroy the proof that the predictions preceded them.

Both probes ran solo on a quiet host in a scratch worktree at `origin/main`
(`16ff3c94`), nothing committed, the primary checkout untouched.

**Probe A — RED, as pre-committed.** A fixed 400 ms delay injected at the
landing seam (`_on_event`, gated to the first landings of the X3 drain), the
test unmodified:

```
AssertionError: control X3 exceeded 3x poll_ms
separation: long X2 median 218.0 vs control 39.0; X3 worst 1386.1 vs 436.5
```

Control X3 measured 436.5 ms against the 150 ms bound; the long arms reached
1386.1. The current ceiling catches a delivery delay of the class it exists for.
Site note: a delay inside `next_event` breaches the poll's own 50 ms budget in
the bridge's real-seconds deadline wrapper and reads as session-poison
infrastructure, not as a band; the landing seam sits after delivery, outside
every poll deadline.

**Probe B — the seam cannot express the rig.** The §3 minimal diff was applied
and the identical 400 ms delay left in place. The first control trial dies at the
snapshot-bracket pin (`:1357`):

```
AssertionError: the pre-dispatch snapshot was retained before the measured
dispatch began — the wrapper's pre-tick did not retain
assert 1116000000 > 1116000000
```

Two real events read the identical virtual nanosecond: between real events
nothing advances virtual time, so the tick → block → dispatch → tick bracket
cannot be expressed. That is the third branch of §5's pre-committed rule, which
already names it as a close.

The forced walk completes the argument. The control's required
`status == "unknown"` is produced by the real-seconds deadline wrapper cutting a
200 ms-paced acquisition at 20 ms; instant virtual pacing erases that cut, so
pacing must stay real, and real pacing forces real window stamps. Virtualising
only the X3 stamps yields a domain-mismatched negative or authored values. Every
completion route is authorship (a tautology) or real coupling (nothing
de-timed).

**Consequence for the finding.** It stands, and it no longer rests on structure
alone: A establishes the bound detects today, B establishes that the seam cannot
express the rig, and the only green route is to write the numbers the asserts
read. The §5 acceptance rule fired on its third branch rather than its first,
and both branches close the issue.
