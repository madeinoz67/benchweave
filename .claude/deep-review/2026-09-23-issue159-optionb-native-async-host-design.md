# Option B, native async host — row-1 activation review (issue #159)

**Date:** 2026-09-23 · **Issue:** [#159](https://github.com/madeinoz67/benchweave/issues/159) (deferral row 1 of
`.claude/deep-review/2026-09-21-issue43-capture-streaming-design.md`)
**Parent record:** the #43 design of record through Amendment 3 + the 2026-09-22 slice-2 errata.
**Review battery:** adversarial REFUTE + mechanism critique (2026-09-23), 15 findings — 2 critical,
4 high, 5 medium, 4 low — integrated in this revision. The refute lane's standing: "not defended as
written; the DON'T-BUILD-now verdict survives the attack." Every low finding folded into the same
edits that closed its higher-tier neighbour (dispositions ride the PR body).
**Corpus:** no standards bytes move; no SDK touch. `make check-sdk-standards` stays green trivially.
**Triage:** public — no person, client, bench, serial, commercial term, or install-specific
operational detail appears; every number below comes from the committed synthetic test rig's
invented fixtures (`bench.seq-model`, `dev-1`) or from a named record, never from a real bench.

**Verdict: DON'T-BUILD the native async host — now.** Three independent grounds (§1): the one
family of quantities a host could move is unmeasured and its decision denominator is uncommissioned;
the issue's own disclosure set is mispriced (three of four quantities no host model moves); and the
activation/sequencing facts deny a build today (no run-path caller, capture verbs inexpressible, the
exposure surfaces held by in-flight trains). What #159 honestly earns is this record — the buy-ledger
correction, the widened exposure finding, and a pre-committed decision rule (§6) — plus one named
measurement follow-on. The owner directive is answered by making row 1 *decidable*, not by building
the thing row 1 was deferred to decide about.

## 0. Root cause — the issue's own disclosure set is not an Option-B instrument

Verified against the spec's §8 scheduling model and the live code, not the issue prose.

**§8 per-instance serialization is preserved under Option B by the issue's own definition.**
The host is "a single async host/scheduler multiplexing N adapters' `execute`/`next_event`
calls" — multiplexing *across instances*. Spec §8 ("Host scheduling allows at most one
execute/next_event call in flight **on the instance**"; "One returned object serves one commissioned
physical instance") is the normative scheduling model and is enforced in-tree by the bridge's
per-instance lock + one `asyncio.Runner` per instance (`src/benchweave/host/otdp_bridge.py`
docstring: "Each bridge owns one event loop and serialises its lifecycle and dispatch"). A read,
a write, a protective action and a capture on the *same* instance serialize whether the host is
serial or async.

Re-priced against that, the #159 body's four disclosure quantities
(`tests/integration/test_capture_sequential_model.py`; re-run 2026-09-23: gap 50.9 ms, queued
57.7 ms, lock-block 50.2 ms — same class as the issue's 51.0/56.1/50.6):

| Quantity | Measured | What actually bounds it | Option-B lever? |
|---|---|---|---|
| 1. Monitor gap during a deadline-max capture | 51.0 ms over a 10.0 ms poll-cadence **floor** (5.1x — see the denominator note below) | today: the worker thread is blocked inside `OTDPBridge.dispatch`, so `_MonitoringPlugin.dispatch` (`control/coordinator.py`, the `tick -> block_result -> inner.dispatch -> tick` wrapper) cannot tick | **partially** — the tick-gap axis moves only under a *skip-busy-instance* tick semantic (§2); the capturing device's own signal freshness does **not** move (§8) |
| 2. Queued-run delay behind a capture | 56.1 ms behind a 50 ms capture | A03 / `interfaces/worker.py` `RunWorker` — "Drains the accepted-run queue FIFO; exactly one run is ever active" | **no** — one active controlling procedure per bench survives every host model |
| 3. Second-dispatch lock-block | 50.6 ms | §8 — the helper dispatches to the **capturing** bridge and blocks on its per-instance lock | **no** |
| 4. Store-contention stretch | 10.73 s at 2x `busy_timeout` (5 s default) — **provenance-corrected, see below** | SQLite single-writer busy-retry (append `BEGIN` + abort-epilogue `BEGIN`, gate region a third stretch) | **no** — row-9 clamp territory (#167 Decision 7) |

**Number provenance (measured-claims rule: every figure carries its denominator and whose
measurement it is).**

- The 5.1x ratio's denominator is `_DEFAULT_POLL_MS = 10` (`control/protection.py:49,66`), a host
  default-floor — the fixture (`BENCH_SIGNALS`) declares `max_age_ms` but **no** `poll_ms`. On a
  bench declaring `poll_ms: 50` the same gap reads 1.02x. All gap comparisons in this record are
  **absolute milliseconds**; ratios are illustrative only.
- The 10.73 s figure originates in the #167 record's contention analysis at `Store.open`'s
  `busy_timeout=5000` default with a hold past the timeout horizon. The committed contention test
  runs `PRAGMA busy_timeout=300` and asserts `>= 110` ms (2026-09-23 re-run: 453.5 ms,
  release-before-timeout). The 2x-stretch class at the 5 s default is real; the committed test does
  not parameterize it.
- Saturated-polling class (slice-2 measurement table, #161 — series sizes as recorded there):
  tick gap max 26.0 ms across the 8 recorded gap observations ("worst-of-8"); ~12.5 ms p95 over
  that same 8-observation series (slice + overshoot class); delivery median 152.5 events/s across
  the active subscriptions of that run.

So three of four quantities are structurally outside Option B's reach (A03, §8, store), and the
fourth moves only with a named new tick semantic, not with the host alone.

**The exposure class is long dispatches, not capture (refute F1).** `_MonitoringPlugin` wraps
**every** dispatch `tick -> dispatch -> tick` — verb-agnostic. The blackout tracks dispatch
duration regardless of verb (the fixture's own docstring: with `bounded()` disabled "the gap tracks
the adapter's natural duration"). `read`/`write` steps are corpus-expressible **today**
(`standards/execution/0.1.0/procedure.schema.json` `$defs/step` closes at exactly eight kinds —
`invoke, read, write, delay, sample, assert, if, repeat`, each `additionalProperties: false`; the
executor dispatches read/write already) and bridge-supported. Spec-normative slow reads exist: OTDP §4's
passive receiver "must wait for a new matching frame within the operation deadline" (0.2.2 at line
68, wording unchanged since 0.2.0), and integration-time scalar measurements are ordinary physics.
Consequences, stated honestly:

- The X1/X3/X4 exposure activates at **#167's Decision-1 merge** (run-path bridge construction for
  read/write), not at the execution train. The corpus gate holds only the capture *verbs*.
- Capture is one instance of the class — this record's rule (§6) is written against
  **acquisition-minimum dispatches**, with a non-capture arm mandatory in the measurement rig.
- For an acquisition-minimum long dispatch, policy-side remediation is **unavailable by
  construction**: tightening `timeout_ms` below the acquisition minimum fails the measurement, and a
  scalar read has no split. The prior draft's "has not been shown to lack headroom" clause was an
  argument from silence and is withdrawn (critique C8 + F1).

**The "budget 50 ms" in the issue body is a test constant, not a policy bound.** `BUDGET_MS = 50`
and `TOLERANCE_MS = 150` in `test_capture_sequential_model.py:71-72` are test-rig scaffolding. Under
A02 a monitoring envelope is commissioned per bench from qualification evidence — a missing
requirement blocks, it does not default to a constant. Arm 2 of the reopen trigger ("breach the
capture-deadline policy bound **against a commissioned bench cadence**") is therefore
*structurally unevaluable* today: the denominator does not exist.

**Trigger-arm status at this review (the 2026-09-23T02:48Z comment's evaluation, re-checked against
the in-flight #167 record):**

1. **Poll-slice contracts** — unfired. Slice 2 shipped holding them (gates 1659 -> 1670/0/0).
2. **Monitor-gap/queued-delay vs commissioned cadence** — unevaluable (above). The numbers in hand
   point away from firing on the movable axis (saturated-polling class above).
3. **Clamp design review** — **default-unfired, not permanently closed** (refute F2). #167's
   Decision 7 closes the busy-timeout clamp's six-point review within the serial model and defers
   the clamp's *build* to the capture train; #167's pre-committed M-B keeps the firing rule live —
   "Arm 3 FIRES only if the six-point review cannot hold … firing the arm is a written conclusion
   against these pre-committed bounds, **posted to #159**." Arm 3 therefore stays in this record's
   reopen set (§3) as a live arm with the #159 hand-off. Erratum to #167's M-B: its second firing
   condition borrows the 50 ms slice-1 budget class as a policy bound — the very constant this
   record's A02 ruling declares inadmissible (§9(c)).

## 1. Verdict and its evidence

**DON'T-BUILD — now.** Three independent grounds (the prior draft's four were not independent:
ground 4's "headroom" clause was the un-fired FIRE arm restated — critique C8):

1. **The value is undecidable as the tree stands.** The movable share (X2-X4) has no instrumentation
   (the rig is single-instance; its sole monitored signal `sig-temp` is sourced from the capturing
   device `dev-1`, so the measured tick gap cannot separate the §8-bound share from the movable
   share). Arm 2's denominator is A02 commissioning that does not exist — and the rule's own
   comparison set needs three commissioned bounds (monitoring gap `G`, protective response `P`, and
   X3's telemetry-continuity bound — critique C8/F3b), not two. A missing denominator reads
   UNDERPOWERED; it never defaults. *This is the brief's own DON'T-BUILD condition: the value cannot
   be measured.*
2. **The premise is mispriced.** The issue prices Option B against quantities 2-4, which no host
   model moves (A03, §8, SQLite busy-retry). Building against an immovable baseline would produce a
   mechanism that "fails" its own disclosure numbers. The one axis a host moves (quantity 1's
   movable share) additionally requires the skip-busy-instance tick semantic of §2 — whose
   representation the current evaluator cannot express (critique C2), i.e. the lever is a design
   cost of its own, not a scheduling swap.
3. **Activation and sequencing deny a build today.** No run-path caller exists (enumeration below);
   capture verbs are inexpressible (`$defs/step` closure, verified in full against the schema); and
   the surfaces this would touch are held — #167 (run-engine capture & streaming activation) is
   paused mid-fix-wave on `host`/`bridge`/`run-engine`, and #147's transport-provider train landed
   mid-review (PR #171, OTDP 0.2.2, with the devstage stack as PR #169) — the corpus-bump window is
   no longer a constraint, the execution procedure schema is unchanged, and no PR stands open
   against main; the held surface is #167 alone. Per F1 the read/write long-dispatch exposure
   activates at #167's Decision-1 merge regardless — so this ground is a *now* ground (park behind
   #167), not a claim that nothing is live.

**Caller enumeration (mechanism-derived — refute F4; the prior "zero production callers" phrasing
was not regenerable).** `load_otdp_plugin`'s call set is `src/benchweave/registry/otdp_loading.py`
(definition), `tests/integration/test_otdp_loading.py`, and `scripts/sdk_smoke.py:86,186,210`
(release smoke). **Zero run-path callers** — nothing wires a bridge into `build_run`/the coordinator;
that wiring is #167, mid-flight. The test suite proves the real load path hands the adapter its
capture bundle (slice 1, capture PR `1f7fd2a`), and the stream stack is on main — bridge-level
capture/stream capability exists; run-level activation does not.

**What would change the answer** is exactly the pre-committed rule in §6: a commissioned bench whose
acquisition-minimum dispatch budget cannot be tightened or split to fit its commissioned bounds,
with the cross-instance axes measured on the instrumented rig. That is a small, named amount of
work away (§3 row 2) — and it is the work #159 earns.

## 2. Mechanism — what the host *would* be here (the reopen's designed target)

Designed now so the reopen is a build, not a redesign. Concrete against this tree:

- **What it replaces:** engine-wide caller-side serialization. Today exactly one dispatch is in
  flight engine-wide because the `RunWorker` thread blocks inside
  `_MonitoringPlugin.dispatch` -> `OTDPBridge.dispatch` -> `_run` (the per-instance
  `asyncio.Runner`). The host keeps up to N instance-calls in flight — one per instance.
- **Shape (selected):** one host-owned asyncio loop on one thread, owning all adapters'
  coroutines (adapters are already `async def`); per-instance serialization moves from "the
  caller is single-threaded" to an explicit per-instance queue/lock — the bridge's existing
  lock discipline, kept. **Why not a dispatch thread pool:** the store is thread-affine
  single-writer (`interfaces/worker.py`: "sqlite3 connections are thread-affine, so the worker
  re-opens the store's database on its own connection"); N dispatcher threads mean N
  connections and Nx the busy-retry contention that already stretches a failed dispatch.
- **The store seam, stated honestly (critique C6 — the prior "STO-1/STO-3 by construction"
  overclaim is withdrawn).** Composed with the kept `RunWorker` seam, **two** store connections
  exist: the worker's thread-affine re-open (run records) and the loop's (capture staging writes
  run inside the coroutines). Quantity-4-class `BEGIN` contention is therefore live at one instance
  unless writes are routed. STO-3 is process-level flock (any in-process shape passes); STO-1 is
  transaction discipline, not connection count. The reopen design must pick: a single writer thread
  for all store writes (preferred — keeps quantity 4 flat in N), or an accepted, documented
  two-connection contention profile. **Which thread owns the store is an open design decision of
  the reopen**, and a connection census (exactly one store-opening thread in a 2-instance run) is a
  build gate.
- **What it does not touch:** the sequential procedure walk (A12), one active run (A03), the
  per-instance §8 discipline, the protective transition's authority (CTL-1-CTL-3).
- **The tick semantic that makes quantity 1 move — the real design cost (critique C2).**
  `_RunMonitor.tick`'s signal reads must *skip a busy instance* and represent the skipped signal's
  reading honestly, never block and never launder staleness into freshness (A06). The current
  evaluator cannot express this: `SignalValue` is `{value, unit, age_ms, valid, absolute_error}`
  (`control/policy.py:56`), `valid` is fixed at snapshot build as `age_ms <= max_age_ms` — inclusive
  (`control/protection.py:169-171`), and `evaluate_conditions` reads `age_ms` only in
  `_product_violation`'s skew path (`policy.py:206`) — numeric/boolean trips use `valid` alone, so
  an in-bound aged reading currently evaluates as a **clean current answer**. Pinned for the reopen:
  - **Bound ownership:** the monitor's freshness bound is the bench signal's `max_age_ms`
    (`bench.schema.json`, commissioned). The procedure `sample` step's `max_age_ms`
    (`procedure.schema.json`) is a different contract with a different owner and is **not** the
    monitor's bound. The prior draft conflated the two.
  - **Representation:** no reading may evaluate as clean without its age. A skipped-without-value
    signal is `valid=False` (fail-safe direction). An aged-in-bound reading carries its age into
    evaluation (the representation change — an explicit aged/stale visibility on `SignalValue` and
    the trip evaluator — is designed with its own RED controls; the aging removal must flip those
    controls).
  - **Direction fork, default taken:** aged = not-clean for confirmation purposes (A06/A04
    direction). The alternative — bounded carry-forward with trip-suppression during a declared
    dispatch window — trades a missed excursion for run continuity and needs its own design before
    it could be preferred. Reopening may revisit; this record pins the safe default.
  - **Boundaries and fixtures:** `max_age_ms` boundary is inclusive-valid today (pin −1 / 0 / +1
    semantics in the reopen's tests). The rig fixture's `max_age_ms: 600_000` makes aging vacuous
    at 50-200 ms dispatch scales — the instrument's fixtures must declare dispatch-scale bounds.
- **Interrupt path unchanged:** the only in-flight interruption remains the `bounded()`
  deadline + the bridge's bounded abort epilogue.

**Precedent (principle 9 — extend, don't invent):** the `StreamPollEngine`
(`control/stream_polling.py`) is already "mini-Option-B machinery inside the executor's wait-slice
rhythm" — its round-robin + poll-slice bounding + between-poll ticks is the multiplexing shape to
generalize to N instances; `_MonitoringClock.wait_ns`'s deadline-sliced wait with a tick per
slice is the interleaving discipline to extend to dispatches; the bridge's per-instance
lock/Runner is the §8 enforcement to *keep*; `MonitoredHarness`/`test_capture_sequential_model.py`
is the disclosure-rig shape the instrument extends. No second scheduler, no new concurrency
primitive.

## 3. Minimal first increment and deferrals

**This record is the increment** (docs-only; lands as commit one on the working branch). One
follow-on is named — the instrument — and parks per §8 below.

| # | Deferred | Carrier | Reopen trigger |
|---|---|---|---|
| 1 | **Native async host** (the mechanism of §2, incl. the skip-busy-instance tick semantic and the store-ownership decision) | This record | The §6 FIRE arm, or the three original arms restated: poll engine cannot hold poll-slice contracts; the movable axes breach commissioned bounds on an acquisition-minimum budget; or arm 3 fires (default-unfired — M-B's live rule posts fires here; the clamp review cannot close) |
| 2 | **Cross-instance continuity instrument** (X2-X4 on a two-instance rig, plus the mandatory non-capture long-dispatch arm and the machine checks of §6) | One follow-on issue at this PR's open, plus this record §6 | Lands behind #167 (shared measurement surface — §8); its own completion trigger is "first commissioned bench" for the denominator |
| 3 | Busy-timeout clamp build | #167 Decision 7 + its train issue | #167's row-B trigger (already carried) |
| 4 | Invoke/dataset scheduling | #146 (row 2 — separate carrier) | unchanged |
| 5 | Tick-boundary polling (#167 residual E) | #167 Decision 3's deferral table | unchanged — "or Option B (#159)" still stands, now pointing at §6 |

## 4. Invariant and drift impacts

No invariant changes in this increment (docs-only). What the serial model guarantees and
concurrency would endanger — recorded so the future build is held to them:

- **STO-1/STO-3 (single-writer, one coordinator per store file):** see §2's store seam — the
  composed shape carries two connections today; the build gate is a connection census, and the
  preferred shape routes all store writes through one writer thread.
- **CTL-8 (monitoring wraps every dispatch, single-threaded and deterministic on the injected
  clocks):** the fracture point is the **wait-primitive protocol**, not only await-point
  interleaving (critique C5): `MonotonicClock.wait_ns` is synchronous `-> None`
  (`control/clocking.py:29-34`) and `TestClock.wait_ns` advances virtual time instantly without
  yielding (`clocking.py:73`) — an asyncio host needs a suspension point, so no "pinned scheduling
  discipline" preserves the fault suite's instant-advance semantics without virtualizing the
  loop's own scheduler. The reopen therefore forces a `MonotonicClock` protocol change; the
  determinism claim is scoped to what is preservable under that change (bit-identical `TestClock`
  fault-suite runs are the gate), or CTL-8 is amended with evidence — never silently flaked.
- **CTL-5/CTL-9 (occurrence ledger; one coordinator owns one run):** unchanged — the host sits
  below the coordinator. The FIFO `RunWorker` and its thread-affine store re-open are the
  seam the host must compose with, not replace.
- **REG-2 / §8 (per-instance serialization, timeout-after-dispatch honesty):** preserved and
  now *load-bearing for the buy-ledger* — it is why quantity 3 (and the capturing device's
  half of 1) cannot move. The skip-busy-instance tick semantic must not create a second
  in-flight call on a busy instance (it must skip, never queue behind and never race).
- **A04 (protection never depends on continued AI judgement):** the host *strengthens* A04 for
  non-capturing devices (safe actions stop waiting out foreign captures) but leaves the
  priced residual for the capturing device (consequence 3 of #43 Decision 1) — §8-bound.
  A build that claims A04 gains without naming that residual is overclaiming.
- **A06 (ambiguous outcomes stay ambiguous):** the skip-busy tick semantic's aged-reading
  honesty is the new hazard (§2's representation pin); a skipped reading recorded as fresh is
  the exact laundering A06 forbids.
- **A02/A09 (qualified, not assumed; device facts from protocol evidence):** the acquisition
  minimum (`T_acq_min`) is a device/qualification fact — the rig's pacing is never its authority
  (§6).
- **Cross-surface:** none this increment — no MCP/REST/CLI surface, no operator or
  device-developer guide change, no vendored byte, no fixture lattice, no SDK pointer.
  The follow-on instrument touches `tests/integration/` only (obligation list not triggered).

## 5. Measurable proof — baselines and the instrumentation gap

**Baselines (reused from the #159 body and the slice-2 comment; all from the committed synthetic
test rig, none from a real bench; provenance in §0):** tick gap 51.0 ms over the 10.0 ms poll-floor
(single-instance); queued-run delay 56.1 ms (A03-bound — retained as disclosure, not a row-1
input); lock-block 50.6 ms (§8-bound — same); contention stretch 10.73 s class at 2x
`busy_timeout` (row-9 input; committed test parameterizes the 300 ms class instead). Saturated-
polling class: tick gap max 26.0 ms worst-of-8, p95 ~ 12.5 ms, delivery 152.5 events/s shared.

**Instrumentation the committed rig lacks** (the recorded gotcha — pre-committed axes need their
instrumentation landed with the rig): the tick seam and the overrun fixture *exist*
(`MonitoredHarness._recording_tick`, `CapturingAdapter`'s paced over-budget capture); what is
absent is a **second instance** and the cross-instance axes — X2 (per-signal freshness gap
for a non-capturing device), X3 (events emitted vs landed on a non-capturing subscription during
a long dispatch), X4 (protective-action latency to a non-capturing device). X1 (tick gap) exists
but its fixture's sole signal is sourced from the capturing device, so it cannot separate the
§8-bound share from the movable share. Also absent per F1: a **non-capture long-dispatch arm**
(a slow `read`/`write` at acquisition minimum). The instrument is test-only and buildable against
today's tree (`read_signal_values` is already multi-device-keyed; `build_capture_services`/
`build_stream_services` compose) — it parks behind #167 by the shared-surface rule (§8), not
because it is structurally blocked. The instrument lands **before any row-1 number is looked at** —
that ordering is the point.

## 6. Pre-committed acceptance rule — the row-1 decision rule

Written 2026-09-23 and revised after the review battery, **before any cross-instance axis has
produced a number** (the instrument does not exist). This rule may not be tuned after the data
arrives.

- **Axes** (per trial; >=5 trials per axis) — each pinning its clock domain (critique C5/C11):
  - **X1** tick-gap class — absolute milliseconds on the monotonic clock (`SystemClock.now_ns` class),
    bound `G1` (commissioned monitoring gap bound). Ratios to poll cadence are never the axis.
  - **X2** non-capturing-signal freshness gap at dispatch end — the `max(host-computed age,
    device-reported age)` envelope `read_signal_values` already computes (wall-derived age domain),
    bound `G2`. Buffered and unbuffered device classes must report the same axis quantity.
  - **X3** poll stall (events emitted vs landed) on a non-capturing subscription during a long
    dispatch, bound `TB` — the bench's **telemetry continuity bound** (now a named denominator
    input; critique C8/F3b).
  - **X4** protective-action latency to a non-capturing device — absolute milliseconds on the
    monotonic clock, bound `P` (commissioned protective response bound).
  - **Dispatch arms:** a **capture** arm and a mandatory **non-capture** arm (a slow `read`/`write`
    at acquisition minimum — F1). Both arms run on a two-instance rig (A dispatches, B streams +
    carries a bench signal + a protective write path).
- **Denominator (A02):** `G1`, `G2`, `P`, and `TB`, from the bench's qualification evidence. The
  rig's `BUDGET_MS` / `poll_ms` constants may never substitute; a missing bound for **any** axis
  blocks that axis's decision (UNDERPOWERED), it does not default.
- **`T_acq_min` authority (critique C4/F3):** the acquisition-minimum dispatch budget is a
  device/qualification fact (declared limits / protocol evidence — A09), never the rig's pacing.
  Asserted **conjunctively** by two rig-consistency controls, which are consistency checks only and
  never the authority: (i) a matched short-`T` control that fails the acquisition; (ii) a
  split-refusal control asserting the dispatch cannot be split without failing it (for a scalar
  read this is definitional; for a capture it is asserted against the fixture).
- **Breach comparator (critique C10):** a breach is **strictly greater than** the bound; equality
  passes. Trial-quality gate: per-axis trial range (`max - min`) **>25% of that axis's own bound**
  is UNDERPOWERED (critique C9: the statistic is the range; "the bound" is that axis's `G`/`TB`/`P`).
  A bound tighter than achievable rig precision reads UNDERPOWERED **by design** — decide nothing
  without better instrumentation; a breach-heavy underpowered series escalates instrumentation
  priority, it does not decide.
- **Arms — a total classification in this precedence order** (critique C1: the prior draft left the
  modal outcome — 2 of 5 breaches, the most likely single outcome at a true rate of 0.4 —
  unclassified):
  1. **UNDERPOWERED** — any axis missing its commissioned bound; single-instance rig (X2-X4
     unmeasurable); or any axis's trial range >25% of its own bound. Result: decide nothing, change
     no posture; the instrument's trigger gains "re-run with a commissioned bench".
  2. **FIRE** — at `T_acq_min` (both controls asserted), any axis breaches its bound in **>=3 of 5**
     trials. Result: the §2 host proceeds to build; the policy-side alternative is documented as
     tried-and-insufficient.
  3. **KILL** — across >=2 device classes x >=5 dispatches each (**including >=1 non-compositional,
     un-splittable class** — critique C4/F3), every dispatch admits `T`-tightening or splitting
     until all axes fit their bounds. `T_acq_min` dispatches are KILL-exempt by construction (their
     controls assert neither tightening nor splitting is available), so FIRE and KILL cannot arm on
     the same set. Result: row 1 closes; the serial model plus the capture-deadline policy is the
     answer; this record is the negative result's home.
  4. **INCONCLUSIVE** — everything else, including 2-of-5 and 1-of-5 breach series with tight
     spread and commissioned bounds. Result: raise n and re-run; no posture change.
- **RED control (for the mechanism, when built):** multiplexing disabled (engine-wide
  serialization restored) -> X2-X4 return to the dispatch-duration class; enabled -> they drop to
  the cadence/response class. Matched control fixture: same rig with a short dispatch (all axes
  track the short duration). Per the #43 floor, a control that passes both ways proves nothing; no
  underpowered mode applies to the controls.
- **Machine checks — the instrument's acceptance tests** (deferred with it, named now so the rule is
  executable when it matters): (1) table-driven classifier test over (breach count x splittable x
  spread x bounds present) asserting every cell maps to exactly one arm — RED on the 2-of-5 cell and
  on any both-armed cell today; (2) aged-reading representation test + `max_age_ms` boundary table
  (−1/0/+1) — RED when the aging is removed; (3) provenance test: every record-quoted figure cites
  a reproducing command and parameterization; (4) store-connection census in a 2-instance run;
  (5) divergent-wall-clock test (X2 moves, X1 must not); (6) bit-identical `TestClock` fault-suite
  run under the host's wait primitive; (7) non-capture arm fixtures (buffered/unbuffered pair).

## 7. Top risks and what falsifies this design

| Risk | Falsifier |
|---|---|
| The premise is wrong and cross-instance degradation is not safety-relevant — benches simply commission dispatch budgets that fit `G` | The KILL arm fires (§6): every acquisition fits after tightening/splitting. That is the intended honest negative, not a failure |
| The long-dispatch exposure activates at #167's Decision-1 merge (slow reads) while the instrument and any host remain unbuilt — the monitoring blackout becomes a live gap for the read/write class | The instrument's non-capture arm measures it (§6); the interim bound is the step `timeout_ms` under the existing capture-deadline arithmetic (`min(now + timeout_ms, body_deadline)`, shortened only) |
| The skip-busy-instance tick semantic launders staleness into freshness (A06) | A control asserting a skipped reading lands as aged/invalid (never fresh) must go RED when the aging is removed — absence-presence, both directions (§2's representation pin) |
| A single loop widens one wedged adapter's blast radius from one instance to all (R6 generalizes: "deadlines require cooperative async code") | The instrument's X3 axis with a deliberately non-yielding adapter on A stalls B's polls beyond the bound — measured, not argued |
| Concurrency multiplies store contention (quantity 4 grows with instance count; §2's seam leaves two connections) | The connection census + X4/the contention axis re-run at 2 and 3 instances; a stretch growing with N kills the single-loop shape's premise |
| CTL-8 determinism erodes because the wait primitive must change (`MonotonicClock.wait_ns` sync -> async suspension; `TestClock` instant-advance) | Bit-identical `TestClock` fault-suite runs under the host's scheduler (or a CTL-8 amendment with evidence) — machine check 6 |
| §8 misread — if it permitted concurrent in-flight calls per instance, quantities 1/3 would move and the buy-ledger would change | A spec reading showing §8 allows concurrent execute/next_event on one instance invalidates §0; the bridge's lock is the enforced discipline today regardless |

## 8. Surface collision

**This increment: proceed, no park.** The deliverable is one file under `.claude/deep-review/` —
zero files in common with #167's surface (`src/benchweave/interfaces/app.py`,
`control/coordinator.py`, its tests, two guides). #147's corpus + SDK-pointer train landed
mid-review (PR #171; devstage as PR #169) and shares nothing either — no PR stands open against
main at this record's landing. No standards byte, no SDK touch, no source touch.

**Follow-on instrument: parks behind #167.** It extends the sequential-model measurement rig
(`tests/integration/test_capture_sequential_model.py` or a sibling) — the same measurement surface
#167's pre-committed M-A/M-B/M-C pass drives ("the `test_capture_sequential_model.py` shape"
is named in M-B). Per the surface-serialization rule the second increment parks at
review-complete and rebases onto merged #167 exactly once. This also sequences correctly with F1's
horizon: #167's Decision-1 merge is what activates the read/write long-dispatch class worth
measuring. (The instrument is technically buildable against today's tree — §5 — so the park is
sequencing, not structure.)

## 9. The loose threads

- **(a) TIMEOUT-on-cut classification — leave out; already disposed.** #167's Decision 8 (folded
  2026-09-23) closed it: a poll cut by the asyncio timeout at its slice deadline classifies as
  session poison — the as-is posture stands on A06 grounds (the system records evidence; the
  caller concludes; a cut poll cannot prove the adapter did not hang), the alternative is
  rejected, and **no #43-record byte contradicts it, so no erratum rides and no byte moves.** It
  was never a row-1 trigger (the 2026-09-23 comment is right) and the question is now closed.
  Re-opening it here would be duplication, not diligence.
- **(b) Arm 2's missing prerequisite (commissioned bounds) — folded in as §6's denominator clause.**
  This is A02 territory and cannot be closed by code: the monitoring envelope comes from a bench's
  qualification evidence, never a hardcoded constant. The rule names `G1`/`G2`/`P`/`TB` as
  commissioned inputs (the third bound added after review) and makes any absence the underpowered
  reading rather than a default. The instrument follow-on supplies the numerator so the ratio is
  computable the day a bench commissions the denominator. Until then arm 2 is structurally
  unevaluable — stated here so no future run mistakes a green rig constant for a commissioning.
- **(c) Erratum to #167's M-B — the 50 ms policy-bound tension (refute F2 sub-point; owner-visible).**
  M-B's second arm-3 firing condition measures "the monitor gap during the stretched dispatch …
  (slice-1 budget class, 50 ms)" as a policy bound. Under this record's A02 ruling that 50 ms is
  test-rig scaffolding and cannot bound anything: if it may not bound, M-B's second condition is
  unevaluable until commissioned; if it may, arm 2's "structurally unevaluable" softens. Either way
  the two records must not diverge silently. Recommendation: M-B's condition restates against a
  commissioned bound (and reads underpowered without one). Posted to #167 with this record's PR.

## One correction to the brief's framing (code and record win)

The brief describes #167 as wiring "procedure-step shapes for capture verbs". The record and the
corpus disagree: #167's Decision 6 *designs* the capture step shape but defers it to the
execution-contract train (three corpus surfaces: `procedure.schema.json`, `safety-policy.schema.json`,
`execution-contract.md`), and the live schema still closes `step` at eight kinds with
`additionalProperties: false` — no capture step is expressible. The brief's "budget 50 ms" is
likewise rig scaffolding (`BUDGET_MS = 50`), not a commissioned bound. Both corrections were
integrated above (§0, §1.3); per F1 the exposure horizon is nonetheless earlier than this draft
first claimed (Decision-1 merge for read/write), which narrows the verdict's third ground to a
parking argument rather than an activation-deferral argument.
