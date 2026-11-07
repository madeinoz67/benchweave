# Issue #576 — the demo lattice streaming control under load: de-timing design

Public tier. No client, bench, operator, or corpus names; all timing values below are
the synthetic simulation lattice's own authored numbers or venue-neutral CI
observations.

## 0. Summary

`test_demo_lattice_admits_and_streams` carries **two independent load races**, both
rooted in the run's real-clock timebase, not in the streaming logic:

- **Family A — the body-dispatch budget race** (issue #576's presentation,
  `outcome_unknown`): a step dispatch that misses its 500 ms `timeout_ms` under CPU
  contention terminates the body honestly unknown at `executor.py:1255-1260`. The
  timeout is enforced on the **event loop's real clock** (`asyncio.timeout` at
  `otdp_bridge.py:241`) even though every deadline computation reads the injected
  monotonic.
- **Family B — the terminal-event consumption race** (issue #532's presentation,
  run `passed` but no `ended` kind): the sim emits its terminal `ended` event only
  after a fixed 4-event telemetry budget at a wall cadence (`adapter.py:124-135`);
  if body-end teardown runs before the poll engine lands that event, teardown's
  `stream_unsubscribe` closes the still-live subscription via `mark_closed`, which
  writes **no** `event_log` row (`stream_services.py:214-221`, teardown at
  `stream_host.py:281-316`). The pending `ended` is destroyed with the subscription.

The fix is disposition 2 (source-level de-timing), realized as one increment:

1. A **clock seam**: `_build_run_factory`/`build_run` hardcodes
   `clock = SystemClock()` at `app.py:802` — the monotonic clock is the one engine
   port the composition never injects. Make it a keyword parameter
   (`clock: MonotonicClock = SystemClock()`), default-preserving.
2. The demo test moves onto **one `TestClock`** threaded through both factory ports
   (`clock=tc`, `now_iso=tc.now_iso`). Every timebase in the run — executor
   deadlines, monitor freshness, poll-engine slicing, the sim's emission cadence,
   `observed_at`/`host_received_at` stamps — then derives from one virtual clock
   (wiring verified: bridge services bundle `monotonic`/`utc_now` derive from the
   composition clock and the factory `now_iso`, `capture_services.py:89-95`;
   adapter stamps `observed_at` from `services.utc_now()`, `adapter.py:195`).
3. **Commission the harness budgets with real-time headroom**: under `TestClock` the
   only residual real-clock enforcement is `asyncio.timeout` at `otdp_bridge.py:241`
   (virtual deadline value, real seconds). Raise the test-authored step
   `timeout_ms` 500→10000 and the chained envelopes (`max_body_ms` 8000→45000,
   domain `max_energised_ms` 10000→50000) so a real event-loop stall cannot trip
   them. Costs zero test wall-time (virtual deadlines are never waited out).
4. A **deterministic timebase pin** in the test (§6) — the RED discriminator.

Family-level budget commissioning for the two other test-authored family members
(`test_run_activation.py` D1, `test_issue146_e2e.py`) rides the same slice (§4).
The N-times-under-load CI lane is **declined** with numbers (§5). #532 collapses
into this change (§3).

## 1. Root causes, established in source

### 1.1 Family A — `outcome_unknown` under load (#576)

Chain, verified line by line:

- The test authors step budgets `timeout_ms: 500` and `max_body_ms: 8000`
  (`test_demo_lattice_streaming.py:261-287`).
- `_dispatch` computes `deadline_ns = min(now + timeout_ns, body_deadline_ns)` from
  the injected clock and hands it to the plugin (`executor.py:1218-1221`).
- The bridge wraps the adapter awaitable in
  `async with asyncio.timeout(max(0, remaining))` (`otdp_bridge.py:237-248`).
  `remaining` derives from the injected monotonic, but **`asyncio.timeout` enforces
  against the event loop's real clock**. Under a starved `-n auto` runner, a trivial
  adapter coroutine can take > 0.5 real seconds to complete; the timeout fires; the
  late-result check (`otdp_bridge.py:243`) classifies it dispatched-then-uncertain.
- `_dispatch` maps a dispatched/unknown failure to `BODY_OUTCOME_UNKNOWN`
  (`executor.py:1255-1260`); `terminal_outcome` keeps it unknown
  (`coordinator.py:142-143`). The run is honestly indeterminate — evidence over
  assertion (A06) working as designed. The control fails at
  `assert record["outcome"] == "passed"` (`test_demo_lattice_streaming.py:443`).

This is the same mechanism the vault already pins for the #146 E2E (one run of
thirty, 2026-10-05) and the concurrent-battery flakes (2026-10-09): a post-dispatch
stall exceeding a step budget, real-clock-enforced. **Family A cannot be
synchronized away**: the preemption must stay real-time (a hung adapter on a real
bench must be cut on wall time; replacing `asyncio.timeout` with a purely
cooperative virtual check would let a blocking adapter hang the run thread — a CTL
disaster). The honest lever is removing the *margin*, not the mechanism: budgets
commissioned for the venue (the #241 doctrine's A/A-floor rule: an absolute
wall bound tighter than the venue's stall floor is a coin-flip gate).

### 1.2 Family B — missing `ended` kind (#532)

- The sim adapter emits 4 telemetry events per subscription at the subscribed
  cadence (descriptor floor `min_interval_ms: 20`), then a terminal `ended` on the
  next eligible poll (`adapter.py:44, 115-135`).
- The bench's signals declare `poll_ms: 50` → poll slice 50 ms
  (`bench.json` signals; `bench_poll_ns`, `protection.py:63-77`). Rounds during the
  400 ms `settle` delay normally land the terminal event around 200–250 ms in.
- Under load, rounds stretch; if body end (teardown,
  `app.py:481-504` → `stream_host.teardown:281`) is reached while the subscription
  is still ACTIVE, teardown dispatches `stream_unsubscribe`; the bridge closes it
  with `mark_closed` (`otdp_bridge.py:467-477`), which records **no evidence row**
  ("the unsubscribe result is the record", `stream_services.py:214-221`). The
  device's already-emitted `ended` is destroyed with the subscription.
- Evidence for that subscription shows telemetry only →
  `assert "ended" in kinds` fails at line 462 with every other assertion green —
  exactly #532's recorded presentation.

Note the sweep path (`stream_host.py:311`, `sweep()` at `stream_services.py:262-275`)
writes a `host_ended` **marker** row — but marker references carry no
`kind`/`sequence` fields (`_marker`, `stream_services.py:377-399`), so a swept
subscription would fail the test earlier with a `KeyError` on `row["sequence"]`.
The observed clean assert-failure confirms the failing path is `mark_closed`, not
the sweep. No drain-before-unsubscribe is available: A12's teardown ruling
explicitly refuses it ("the teardown marker is the record").

**Family B's de-timing is structural**: under one virtual clock the poll rounds,
the emission cadence, and the delay wait all advance on virtual time — the 5th
round (terminal event) at ~250 ms virtual strictly precedes body end at 400 ms
virtual, and no amount of real CPU starvation can compress virtual ordering.

## 2. Family classification of every named observation

| Observation | Family | Mechanism site |
|---|---|---|
| `test_demo_lattice_admits_and_streams` `outcome_unknown` (#576, 2026-10-29 trigger) | A | `otdp_bridge.py:241` real-clock `asyncio.timeout` vs 500 ms step budget |
| same test, `passed` but no `ended` (#532, two CI reds on untouching diffs) | B | `stream_host.py:281-316` teardown consumes a still-live subscription before the terminal event lands |
| `test_timing_generator_smoke_against_in_process_gateway` (`execution_error`, acceptance sample run) | A | same budget race through the **committed** fixture procedure (`fixtures/execution/procedure-voltage-check.json`: 500 ms steps, 8000 ms body; consumed by the ephemeral gateway, `evidence.py:833-847`) — entry-reject presentation (`executor.py:1238-1249`) |
| `test_issue146_e2e` thirty-run E2E | A | same race; harness authors 1900 ms steps, `max_body_ms` 8000 with the disclosed scheduling-overhead arithmetic (`test_issue146_e2e.py:212, 227-262`) |
| `test_run_activation.py` D1 | A | same race; harness authors 500 ms steps (`test_run_activation.py:500-531`) |
| SDK `windows-latest` stop-settle wall-clock bound | wall-clock-budget family, **SDK repo** — out of scope here; named for the record |

One mechanism (family A: real-clock step/body budgets vs venue scheduling) covers
four of the five gateway-side observations; the fifth is family B in the same test
as the issue's own control. Designing for the family is therefore justified, and
the family's shared lever is budget commissioning; the named control additionally
takes the clock seam, which is what kills family B.

## 3. Why #532 collapses into this change

Same test file, same run, two presentations of one property: the control observes
stream completion through real-time windows. The de-timing makes the terminal-event
ordering deterministic (virtual arithmetic, §1.2) and the body outcome
deadline-safe (commissioned budgets, §1.1), so the test satisfies #532's primary
acceptance arm ("observe the end event deterministically") by construction; the
fallback arm ("record why the stream can end without an end event, and assert that
condition") is not needed and is **not** built (deferral discipline: no speculative
disjunction assert). Both issues close on the one increment.

## 4. The increment

### 4.1 Mechanism, concretely

**Seam (production, ~4 lines):** `_build_run_factory` gains
`clock: MonotonicClock | None = None`; `build_run` uses
`clock = clock or SystemClock()` at the current `app.py:802` site. Nothing else
changes: every downstream consumer already receives the clock object
(`stream_host` at 825, capture bundle at 854, sim plugins at 929, coordinator at
945-946, `RetainingServices.wall` keeps the `now_iso` param). Default behavior is
byte-identical for all five existing callers (verified: `test_run_activation.py`
×2, `test_capture_run.py`, `test_execution_pin`, the demo test).

**Demo test (the named control):**

- Construct `tc = TestClock(wall_start="2026-09-14T00:00:00Z")` (inside every
  fixture validity window, matching the registry freeze `NOW_ISO`), pass
  `clock=tc, now_iso=tc.now_iso`. One clock object for both ports — this is the M2
  timebase-identity pin extended to the composition seam (today the factory wall
  and the composition monotonic are two separate `SystemClock` instances that
  agree only because both are real).
- Commission the authored envelopes: step `timeout_ms` 500→10000 (three dispatch
  steps), `max_body_ms` 8000→45000 (worst-case sum 3×10000 + 400 delay + 100
  declared overhead = 30500 ≤ 45000, satisfying `_check_body_budget`,
  `semantics.py:365-375`), domain `max_energised_ms` 10000→50000 (energised check:
  45000 + 2000 transition ≤ 50000, `semantics.py:377-383`). `duration_ms: 400`
  settle unchanged — under `TestClock` it is instant.
- Update the docstring: the wall-clock-sensitivity disclosure is replaced by the
  de-timing statement (the deferral in the docstring is resolved by this design).
- Add the timebase pin (§6).

**Family budget commissioning (same slice, test-authored values only):**

- `test_run_activation.py` D1: step `timeout_ms` 500→10000, `max_body_ms`
  8000→45000, policy envelope raised to match (the harness authors its policy;
  apply the same arithmetic).
- `test_issue146_e2e.py`: step `timeout_ms` 1900→10000, `max_body_ms` raised per
  the same arithmetic, and the scheduling-overhead comment at line 212 recomputed
  to the new values (the comment IS the arithmetic disclosure).

These two stay on `SystemClock` (they exercise the real activation path on purpose;
their delays are unchanged so their wall time does not move). They are in-slice
because they are two-value edits to test-authored dicts with an existing disclosed
arithmetic — the same mechanism, the same RED shape, no fixture or digest motion.

### 4.2 What this increment DEFERS

1. **Committed-fixture budget commissioning** (`fixtures/execution/procedure-voltage-check.json`
   500 ms steps → the timing generator's family-A exposure). Requires the
   `commissioning.json`/`run-binding.json` digest re-pin chain (CON-2's lattice)
   and a consumer census (parity-suite seeded runs, adapter agreement). Named
   trigger: the next gates-lane red on `test_timing_generator_smoke` — or fold
   into the next slice that touches the execution lattice anyway.
2. **The N-times-under-load CI lane** — declined now, with the numbers (§5). Revisit
   trigger: a post-fix family-signature red under load (the deferral-trigger
   discipline this issue itself used).
3. **The SDK `windows-latest` stop-settle bound** — different repo, named for the
   record only.
4. **Gateway-level clock injection** (threading a clock through `worker.py`'s
   server-side run construction so gateway-path tests can de-time like the demo
   test). Only worth building if a gateway-path control proves load-flaky after
   budget commissioning; the seam added here is the factory leg of that path.

## 5. Disposition costs — and why the N-lane is declined

An N×-under-load lane is detection, not removal. Its per-PR detection power against
the measured rate: the docstring's own measurement is 1/27 under load (~3.7%/run);
the CI reds (two PRs) and the 2026-10-29 local battery red have unknown
denominators and are recorded as occurrences, not rates. Detecting a 3.7% flake
with 90% probability needs N ≥ 60 repetitions (1−(26/27)^60 ≈ 0.90); at ~5–8 s per
bootstrap+run, that is 5–8 minutes of serial CI per PR, forever, to catch a class
the de-timing removes structurally. Post-fix, the named control has no load-sensitive
surface left for the lane to catch — the lane would be a regression tripwire priced
at ~6 minutes/PR. The honest standing guard already exists: the doctrine row
(real-clock bounds carry the `timing` marker or move to an injected clock) plus the
timebase pin, which reddens any real-clock reintroduction deterministically. If a
post-fix load red with the family signature appears, the lane question reopens with
a measured post-fix rate to size N against.

## 6. Proof — RED-first plan and the pre-committed acceptance rule

### 6.1 RED discipline (deterministic, not load-shaped)

A load-shaped failure cannot be reproduced on demand, so the RED artifact is
structural, and the brief's demand — "prove the test changed rather than merely
re-ran" — is met by a discriminator no re-run can pass:

- **Timebase pin (new assert in the demo test):** every landed `event_log` row's
  `host_received_at` (and every step event stamp in the run record) lies within the
  virtual window `[tc.wall_start, tc.wall_start + 10 min virtual]`. A run on any
  real clock stamps the actual date — 2026-11 or later — and the pin fails. RED
  check: revert ONLY the test's clock arguments back to `SystemClock()` (fix
  neutralization), run the test → the pin reds deterministically; restore → green.
  Paste both. This proves the run's entire stamping surface derives from the one
  injected clock; a mixed-timebase regression (someone adds a real-clock stamp
  anywhere in the path) self-reddens the same pin.
- **Ordering pin (family B):** the existing `"ended" in kinds` assert becomes
  deterministic by virtual arithmetic (terminal event lands ≤ ~300 ms virtual;
  body ends at ≥ 400 ms virtual). Its RED is the same neutralization: on
  `SystemClock` the pin is load-shaped (may pass), so the *proof* of the mechanism
  is the timebase pin plus the acceptance measurement, not a forced red — stated
  plainly rather than claimed otherwise.
- **Budget arithmetic:** raising values without updating the #146 arithmetic
  comment, or violating `_check_body_budget`/`energised_budget`, reds at admission
  — deterministic by construction.

### 6.2 Pre-committed acceptance rule (written before any post-fix number is looked at)

Metric: family-signature failures of the named control and the two commissioned
family members, where family signature = `outcome_unknown`/`execution_error` body
outcome or a missing `ended` kind, with the timebase pin green (i.e. not a
mechanism reintroduction, which the pin would catch separately).

Sample: ≥ 300 executions of the named control under load — load shape = the
project's own battery idiom (`pytest -n auto` full battery alongside, matching the
2026-10-29 trigger shape), spread over ≥ 3 battery runs and ≥ 2 venues (local
parallel battery, CI gates lane across subsequent merged PRs) — plus ≥ 3 full
gates-lane runs post-merge.

- **SHIP if:** 0 family-signature failures in ≥ 300 control executions AND all
  deterministic pins green. (Rule of three: 0/300 bounds the residual per-run rate
  < 1.0% at 95%; against the pre-fix 3.7%, P(0 in 300 | unchanged) ≈ 1.2e-5 — the
  unchanged-rate hypothesis is killed outright.)
- **KILL (revert to design) if:** ≥ 2 family-signature failures in the 300 — the
  residual rate is not meaningfully below pre-fix; the mechanism analysis is wrong
  somewhere and the design reopens (first suspects: a second real-clock enforcement
  site, or a family-B path through the sweep marker).
- **UNDERPOWERED (extend, do not conclude) if:** exactly 1 failure in 300, or the
  venue count < 2, or control executions < 300 — extend to 600 executions before
  any ship/kill claim. A 10×-reduced rate (~0.4%) is not distinguishable from
  < 0.2% at N=300; say so rather than ship on the smaller number.
- **Honesty bound on "gone":** 0/300 proves < 1%/run, not zero. The "gone" claim
  rests on structure (no real-clock read left in the path — pinned) plus the
  bounded rate, and both halves are stated wherever the claim is made.

## 7. Invariant, drift, and surface impacts

- **Invariants:** none amended. CTL budgets/deadlines unchanged (values are
  harness-authored documents, admission arithmetic still enforced); CON-2's digest
  lattice untouched (no committed fixture bytes move in this increment); the M2
  timebase-identity fact is *strengthened* (one clock object threaded through both
  ports) — `clocking.py`'s F6 note stays true; no schema, migration, or persisted
  format changes.
- **Drift obligations:** the real-clock doctrine row
  (`drift-and-obligations.md:767`) is followed, not amended — the control moves to
  the injected clock per #241 slice 4's placement ruling; no new real-clock bound
  assert is added, so no `timing` marker is required. No CI lane changes (no
  N-lane). No operator/device-developer docs move (no behavior change).
- **Surfaces:** `src/benchweave/interfaces/app.py` (seam, default-preserving);
  `tests/integration/test_demo_lattice_streaming.py`;
  `tests/integration/test_run_activation.py`; `tests/integration/test_issue146_e2e.py`.
  CI cost: none added; the demo test gets *faster* (the real 400 ms settle becomes
  virtual).

## 8. Review tier (Step 1, design-time call per #254)

**Tier 2.** Trigger: any other change to production or test code under `src/` or
`tests/` (rubric Step 1, Tier-2 rule). No Tier-3 path rule fires: no
`standards/`, no JSON Schema, no `state/migrations`/`documents.py`, no
`registry/` behavior, no `fixtures/registry`/`catalogue.json`/`scripts/registry`,
no dependency or submodule motion.

**Keyword scan over the expected diff text** (the eight Step-1 keywords:
`threading`, `asyncio`, `subprocess`, `sha256`, `hashlib`, `migrate`, `recovery`,
`protection`): expected counts 0 for all eight — the seam hunk adds a clock
parameter (the word `clock`, `MonotonicClock`, `SystemClock`, `TestClock`); the
test hunks change numeric literals in the authored procedure/policy dicts, the
factory-call arguments, the import line, the docstring, and add the timebase pin
(reading `host_received_at` columns — no digest helpers touched; the `_sha`
re-pinning region of the test is not edited). Residual disclosed: the scan is over
the *expected* diff; if the build's actual hunks pick up any of the eight words in
context lines (e.g. a `sha256`-bearing line adjacent to an edit), the tier
self-escalates to 3 mechanically and the deep lane runs — that outcome is the rule
working, not a design defect. If any slice also takes deferred item 1 (committed
fixture budgets), that slice is **Tier 3** by the `sha256` re-pin hunks alone.

## 9. Top risks, each with its falsifier

1. **A composition member reads a real clock outside the ports** (sqlite
   timestamps, an unported `time.*` call), splitting the timebase. Falsifier: the
   timebase pin — any real stamp lands outside the virtual window and reds
   deterministically; discovered at build time, cheaply.
2. **The freshness/monitor verdict rejects virtual-consistent stamps** (the reason
   the current test uses real wall time — its comment names the freshness verdict).
   Under one clock, ages are virtual and bounded by slice waits; if some verdict
   member nevertheless assumes real pacing, the test reds on `signal_invalid`
   deterministically at build time. That failure would say the seam is
   insufficient — escalation path: fix the member or fall back to budget-only
   commissioning for this test and keep the seam for order-pinned tests.
3. **The `asyncio.timeout` residual with 10 s budgets**: a > 10 s real event-loop
   stall still reddens. Bounded by the acceptance rule (< 1%/run claim); if it
   fires, kill-direction 6.2 applies and the suspect list starts at runner-level
   starvation (venue), not the control.
4. **`TestClock` full-composition novelty**: no existing test runs the whole
   coordinator stack on a virtual clock (unit controls run the executor directly).
   Mitigation: the increment is one RED→GREEN slice with the neutralization
   discipline; risk 2's failure mode is a clean deterministic red, not a flake.
5. **Scope creep via the family members**: if D1/#146 budget raises ripple further
   than their arithmetic comments (e.g. a pinned expected-duration assert), those
   rows split out into their own slice rather than dragging this one — the
   acceptance rule covers the named control regardless.

## 10. Addendum — 2026-11-07, the adversarial refute fold

The body above is the frozen pre-build design record; this addendum records the
refute-wave dispositions and their evidence. The refuter confirmed all five of
the build's claims and found no CRITICAL or HIGH defect; the five items below
(1 MEDIUM, 3 LOW, 1 INFO) are folded here.

### 10.1 F1 (MEDIUM) — §5 overstated: four real-clock residuals survive

§5's sentence "Post-fix, the named control has no load-sensitive surface left
for the lane to catch" is **false**. Four real-clock enforcement surfaces remain
in the named control's path, each verified in tip source this date:

1. **The 50 ms poll slice**: `bench.json` signals `poll_ms: 50`
   (`fixtures/execution/bench.json:100,114`) → `bench_poll_ns`
   (`protection.py:63-77`) → `_MonitoringClock.wait_ns`
   (`coordinator.py:845-861`) → `poll_slice` (`stream_host.py:245-258`) →
   `poll_deadline` (`stream_polling.py:132`) → `asyncio.timeout(max(0,
   remaining))` — real seconds, ≤ 50 ms per poll.
2. **The 500 ms policy disable write**: the committed safety policy's `disable`
   action `timeout_ms: 500` (`fixtures/execution/safety-policy.json:119`),
   dispatched under the protective transition (`protection.py:155`).
3. **The 5 s teardown unsubscribe budget**: `_DISPATCH_BUDGET_S = 5.0`
   (`stream_host.py:62`), applied at the stream-end dispatch
   (`stream_host.py:302`).
4. **The 2 s protection envelope over the verify reads**: the committed policy's
   `safe_transition.max_duration_ms: 2000` (`safety-policy.json:108`;
   `coordinator.py:1503`).

**Poison-red signature.** A residual trip — the poll slice is the likeliest —
poisons the session (`otdp_bridge.py:1108-1130`: `_failed = True` +
`_stream_clear()` → sweep writes `host_ended` marker rows that carry no
`sequence` field, `stream_services.py:377-399`), the poll engine latches
`session_failed` (`stream_polling.py:134-138`), the terminal `ended` never
lands, and the named control reds at its row unpack as **`KeyError:
'sequence'`** (`test_demo_lattice_streaming.py`, the `sequences = sorted(...)`
line — a comment there names this signature). The frozen §1.2 already recorded
the same `KeyError` shape for the sweep path; the addendum extends it to the
poison path.

**§6.2 amendment (dated, superseding the frozen signature definition):** a
family-signature failure now ALSO includes the named control redding as
`KeyError: 'sequence'` at that row unpack with the timebase pin green — a
real-clock residual trip, counted by this acceptance rule, not misread as a new
streaming bug.

**§5, corrected:** the de-timing removed the *authored-budget* surface (family
A's 500 ms step window, now 10 s commissioned) and family B's *ordering*
surface (virtual arithmetic). The four residuals above are load-sensitive by
construction, and the N-lane decline no longer rests on "no surface left"; it
rests on the standing guards — the timebase pin plus the §6.2 measurement
(which now counts residual trips via the amended signature) — with the reopen
trigger unchanged: a post-fix load red with the family signature.

### 10.2 F2 (LOW) — dead constant removed

`tests/control/test_provider_grant_window.py` carried
`PROCEDURE_WINDOW_MS = 10_000` beneath the accurate 100000 + 2000 = 102 s
budget note, with zero readers tree-wide (grep this date: the definition was
the only hit). Deleted; the note stays, now a plain comment.

### 10.3 F3 (LOW) — §4.1's caller census was stale

§4.1 said "all five existing callers". The tip census of `_build_run_factory`
is **18 call sites: 1 production (`app.py:1093`) + 17 test sites across 8 test
files** (refuter-enumerated and independently re-checked). The mechanism claim
(default-preserving seam) is unaffected — the refuter verified it — so this is
documentation only. The same 17 test sites already exist on `origin/main` (the
design's own base; `git grep -c` against `origin/main` this date), so the
"five" was an undercount at design time — the design enumerated only the files
it traced — not drift the build introduced.

### 10.4 F4 (LOW) — Tier-3 evidence, now on record

§8 pre-committed that a slice taking the committed-fixture budgets is Tier 3 by
its sha256 hunks; commit 2 (`ed487297`) took them. The Tier-3 lane has run
(performed by the refuter against the pushed tip, this date):

- Every digest re-derived from file bytes; the re-pin order verified.
- Enforcement proven live: one byte mutated in a committed fixture → the
  focused 12-test suite red `8/12 failed` → byte restored → `12/12, exit 0`.
- The caller census (10.3) enumerated independently.
- The timebase pin neutralised (test clock args reverted to `SystemClock`) →
  the pin red for the right reason; restored → green.
- All fifteen moved tests audited for weakened assertions: none found.

### 10.5 F5 (INFO) — the central claim is unfalsifiable at this venue

Both the builder and the refuter independently **failed to reproduce the
pre-fix flake**: 60 pre-fix serial iterations under `-n 10` load → 0 failures;
44 post-fix load executions → 0 failures. With the pre-fix rate p ≈ 3.7%/run,
P(0 failures in 60) ≈ 10% — the reproduction probe cannot discriminate. The
central claim ("the de-timing removed the races") therefore rests on structure
(the pinned timebase, the source-verified chains of §1) plus the §6.2
post-merge measurement, and is NOT a reproduced-then-fixed flake. Recorded
plainly; do not cite the 60-iteration run as reproduction evidence.

### 10.6 Machine pins added by this fold

- The poison-red signature comment at the named control's row unpack (10.1).
- `tests/unit/test_otdp_bridge.py::test_adapter_bound_reads_the_injected_clock_seconds`:
  proves the seconds handed to `asyncio.timeout` at the `_run` bound derive
  from the INJECTED monotonic (deadline 11.0 s − injected now 10.0 s = 1.0 s),
  not the event loop's clock. RED-verified by neutralising the arithmetic to
  `asyncio.get_running_loop().time()` → `assert [0] == [1.0]` → restored →
  green. This pin exists so a later "virtual" rewrite of the bound — which
  would leave no real seconds to cut a blocking adapter on — reds before it
  can hang a real bench.
