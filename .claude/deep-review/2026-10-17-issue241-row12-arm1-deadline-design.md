# Issue #241 row 12 — arm-1 dispatch deadline: root cause and the in-run budget derivation

**Date:** 2026-10-17
**Slice of:** issue #241 (timing-fragile tests under host load), census row 12
**Observed failure:** `tests/integration/test_capture_sequential_model.py::test_store_contention_mid_capture_stretches_then_classifies`, arm 1 — PR #480 (a `setup-uv` version bump; zero diff overlap with any timing path), timing lane, run 38969111512 (attempt 2, log verified; attempt 1 redded identically per the run record):

```
assert arm1_result["result"].status is OperationStatus.OK
AssertionError: assert <OperationStatus.UNKNOWN: 'unknown'> is <OperationStatus.OK: 'ok'>
 +  where <OperationStatus.UNKNOWN: 'unknown'> = OperationResult(operation_id='op-capture',
 verb=<OperationVerb.CAPTURE: 'capture'>, status=<OperationStatus.UNKNOWN: '...OUT'>,
 message='Invalid, failed or late adapter result; no replay',
 dispatch_state=<DispatchState.UNKNOWN: 'unknown'>)).status
```

**Status:** design only — no code written. Branch named at build time.

---

## 1. Mechanism, confirmed against the code (not assumed)

Arm 1 (`tests/integration/test_capture_sequential_model.py:562-593` at `origin/main` `e12ed04b`)
starts a real capture (100 paced chunks, one store transaction per chunk) with a dispatch
deadline of `harness.deadline_ns(2000)` — 2000 ms of wall budget anchored at dispatch-thread
start (`tests/integration/test_capture_sequential_model.py:263-266`). A holder connection
takes the SQLite write lock between appends, sleeps 0.15 s, rolls back. The asserted
property: the mid-capture append waits the hold out, the capture completes OK, and the
stretch is reported (`stretch_ms >= 110`).

The observed outcome is **not** the busy-window-exhaustion path. The classification tree in
`src/benchweave/host/otdp_bridge.py:447-569` has exactly three shapes for this dispatch:

1. **Writer-originated `sqlite3.OperationalError`** (the append's `BEGIN IMMEDIATE` losing
   the lock race past the busy window — stamped by `_restamp`,
   `src/benchweave/content/capture_store.py:420-425`) → `OperationResult.failure(...)` with
   `status=ERROR`, `error.code=RESOURCE_LIMIT`, `dispatch_state=DISPATCHED`
   (`src/benchweave/host/otdp_bridge.py:555-564`). This is arm 2's expected outcome.
2. **`poison(exc)` → `OperationResult.indeterminate(...)`** with `status=UNKNOWN`,
   `dispatch_state=UNKNOWN` and the generic message
   `"Invalid, failed or late adapter result; no replay"` (`src/benchweave/host/otdp_bridge.py:447-458`,
   `src/benchweave/host/types.py:329-350`).
3. Typed gate refusals (ERROR with specific codes) — impossible here; arm 1 passed the gate.

The CI failure is shape 2, byte-for-byte. The only load-shaped route to shape 2 on this
path is the deadline cut in `_run`'s `bounded()` (`src/benchweave/host/otdp_bridge.py:237-254`):
bridge-runner timeout over the remaining deadline, or the post-await
`TimeoutError("late adapter result")`. Every writer-path `OperationalError` is stamped and
bound to the live capture id (all four `BEGIN IMMEDIATE` sites stamp:
`capture_store.py:213-218, 420-425, 523-528, 683-688`), so an unstamped `OperationalError`
is structurally unavailable, and `CaptureFinaliseRejected`'s raise conditions (unknown id,
terminal state, wrong session, digest mismatch, byte-count disagreement) are state
corruption, not load shapes.

**Deterministic proof (run 2026-10-17, this designer's worktree off `origin/main`):** a
scratch copy of the test with arm 1's deadline changed 2000 → 250 ms (one site, the only
site whose request carries `"cap-stretch"`) redded with the identical signature — same
assert, same `UNKNOWN`, same message, same `dispatch_state`:

```
AssertionError: assert <OperationStatus.UNKNOWN: 'unknown'> is <OperationStatus.OK: 'ok'>
 ... message='Invalid, failed or late adapter result; no replay',
 dispatch_state=<DispatchState.UNKNOWN: 'unknown'>)).status
```

True exit 1, reproduced on the first attempt, no load applied. The observed CI failure IS
deadline exhaustion. (Scratch copy deleted after; worktree `git status` clean.)

**Reachability arithmetic.** Arm 1's workload is real-paced: ~100 × `sleep(0.002)` pacing
plus ~100 store transactions plus the 150 ms hold. Measured totals on this designer's host
(darwin, 10 cores, ambient load avg 8-14 from concurrent lanes — disclosed, not quiet):
5 runs, stretch 436.4 / 440.7 / 442.4 / 454.5 / 528.3 ms, all green (n=5, this host;
plus 2 more at 436.4 / 528.3 in a re-run with true-exit discipline — n=7 total). The
census's own quiet figure for this arm is 416.3 ms (issue #241 sweep, row 12). The fixed
deadline is 2000 ms: **4.8x headroom over the census quiet figure**. The same census
measured **5.4x quiet-to-CI stretch in this same file** (rows 3/4: 56.2 → 302.4 ms and
52.3 → 353.3 ms, PR #240 and run 35832745149). A stretch factor that this file has already
demonstrated in CI crosses arm 1's deadline with margin to spare. The failure needs no
exotic mechanism: uniform dilation of a ~416 ms workload past 2000 ms.

**Load reproduction attempt (honest negative):** 6 runs of the unmodified test under 8
added CPU spinners (ambient load avg reached 35.6 on 10 cores): 6/6 green, peak stretch
605.9 ms (range 463.3-605.9). This host's scheduler did not approach the ~4.8x stall the
CI runner exhibited. The causal chain therefore rests on the deterministic signature
mapping (above) plus the reachability arithmetic plus the census's measured CI stretch —
not on a local reproduction. A claim of "reproduced and fixed under load" would be
overclaiming; no such claim is made.

**The team-lead's stated mechanism is corrected on one point:** "the release lands after
the writer's retries are exhausted and the capture classifies UNKNOWN" is wrong in its
classification step. Busy-window exhaustion classifies **ERROR / RESOURCE_LIMIT /
DISPATCHED** (shape 1), not UNKNOWN — an arm-1 red from that route would present
differently (and is the separate residual in §4.1, D2). The observed UNKNOWN is the
deadline cut. Both routes are load-driven; only the deadline route matches the evidence.

### 1.1 Busy-window horizon, measured (feeds §4.1's deferral arithmetic)

Two connections on one WAL database, `busy_timeout=300` on the waiter, holder holds
`BEGIN IMMEDIATE` without releasing: give-up at **340.6 / 341.3 / 350.0 / 361.1 / 368.9 ms
(median 350.0, n=5, this host, ambient load 8-14)**. SQLite's default busy schedule is
count-based on nominal sleeps (~328 ms cumulative at this timeout), so wall-time give-up
drifts by wake latency only — twelve wakes, additive. Two consequences recorded:

- The census comment's "busy_timeout_ms=300 places the final retry near 633 ms" is not
  what this host measures; the horizon is ~350 ms. Arm 2's 1.2 s hold clears it with
  **~3.4x nominal margin** (more than the recorded ~1.9x) — arm 2's hold-vs-horizon
  assumption is stronger than the inventory believed, not weaker.
- Arm 1's Path-A residual (release lands after give-up → shape 1 at the same assert)
  needs the holder's single wake to overshoot by more than ~180 ms **beyond** the writer's
  twelve wakes (release ≈ 150 + L_h vs give-up ≈ 328 + 12·L_w): additive per-wake latency
  widens the writer's lead; only a differential stall of the holder alone fires it.

## 2. Root cause

Arm 1 relates two independent absolute wall magnitudes: a **fixed 2000 ms dispatch
deadline** and a **real-paced workload whose quiet duration is ~416 ms** — 4.8x headroom —
while the file's own CI evidence records 5.4x quiet-to-CI stretch. The deadline is fixture
scaffolding (it must simply never bind on the success path), but it was written as an
absolute constant, so a loaded host can cut a capture whose hold was released exactly as
designed. The cut is honest gateway behavior (the deadline expired; A06 posture) being
tripped by fixture arithmetic, not by the property under test. This is the #241 class
verbatim: an absolute wall bound riding a workload the host stretches.

## 3. Relation to the row-12 pre-committed disposition (a new disposition, recorded here)

The census row 12 disposition — "Keep + document the arm-2 retry-horizon assumption; if it
flakes, fix sequencing (holder starts before the writer's final retry), not bands" — was
written for **arm 2's hold-vs-horizon ordering**. The observed failure is **arm 1's
deadline**, a mechanism that disposition does not cover. This record is therefore a **new
disposition for arm 1**, in the doctrine's own grammar:

> Arm 1's dispatch deadline is scaffolding, not an asserted band. It is derived in-run
> from a measured reference capture (same workload, uncontended), floored at the
> historical 2000 ms, so quiet hosts keep today's exact behavior and loaded hosts scale.
> No asserted magnitude moves: the OK status, the `stretch_ms >= 110` floor, the
> commissioned `busy_timeout_ms=300`, and arm 2's constants are byte-identical.

The pre-commitment's spirit (prefer sequencing and in-run relativization over band edits)
is followed: nothing asserted moves; the scaffolding becomes load-relative — the same move
the D4' family already made three times in this file (monitor-gap, queued-run, lock-block),
applied to the budget side instead of the assert side.

## 4. The fix (minimal first increment)

One file: `tests/integration/test_capture_sequential_model.py`, the
`test_store_contention_mid_capture_stretches_then_classifies` body only.

1. **Before the arm-1 block (and critically, before the `first_append` wrapper
   installation at line 564-571 — if the reference runs after the wrap, its first append
   sets the event and destroys arm 1's mid-capture sequencing)**, run one uncontended
   reference capture on the test thread and measure its wall duration:

   ```python
   ref_started = time.monotonic()
   reference = harness.plugin.dispatch(
       harness.capture_request("cap-ref"),
       deadline_ns=harness.deadline_ns(10_000),
   )
   assert reference.status is OperationStatus.OK, "reference capture degenerate"
   reference_ms = (time.monotonic() - ref_started) * 1000
   arm1_budget_ms = max(2000.0, 3.0 * reference_ms + 300.0)
   ```

   The reference's own deadline is a generous absolute (10 s): it is pure scaffolding
   whose value is only read on success — if one uncontended paced capture cannot finish
   in 10 s the lane is in a regime nothing can measure, and the job-level 15-minute
   bound is the operative backstop.

2. **Arm 1's dispatch uses the derived budget:** `deadline_ns=harness.deadline_ns(arm1_budget_ms)`.

3. **The in-run print gains the derivation evidence** (the AR-7 lesson — print the stamps
   on green, they are the only spread signal green runs emit):
   `contention stretch (release-before-timeout): {stretch_ms:.1f} ms (budget {arm1_budget_ms:.0f} ms from reference {reference_ms:.0f} ms)`.

4. **Docstring sentence update** (the only other edit): the row-B sentence "remaining here
   (2000 ms deadline) exceeds the commissioned default, so the clamp IS the open default"
   becomes the same claim about the floor — the derived budget is floored at 2000 ms,
   always above the commissioned 300, so the clamp still IS the open default. Mechanism
   unchanged; the number it cites is now a floor.

**Parameter arithmetic, pre-committed (k=3, floor=2000, +300):** arm 1's wall need is
`stretch_factor × (reference natural) + stretch_factor × (150 ms hold)` ≈ `1.6 × reference`
under uniform dilation. `3.0 × reference + 300` therefore carries ~1.9x of cushion for a
differential load spike between the reference and arm 1 (a within-run, ~2 s apart,
regime change worse than ~1.9x is required to false-cut). The floor preserves the current
2000 ms exactly wherever the reference measures ≤ ~567 ms — i.e. every host this test has
ever passed on — so **no host where the test passes today behaves differently**, and the
derived term only lifts the budget where today's constant is what kills the run. Row-B
clamp property preserved by construction: `arm1_budget_ms >= 2000 > 300` at bracket entry,
so `dispatch_clamp` still reduces to the open default (`capture_store.py:139-141`).

**Quota check (the reference must not perturb the arms):** each finalised capture charges
800 bytes against the 8192 dataset envelope (`capture_store.py:368-382`); with the
reference plus arm 1 both finalised, `used = 1600`, so arm 2's gate allowance is still
`min(1024, 8192 − 1600) = 1024` — passes as today. Arm 2's `staged == 1` and forensic
`== 1` counts are keyed to `cap-contention` and unaffected (verified against the assert
sites, lines 628-654).

### 4.1 What this increment defers

| id | deferred | home | reopen trigger |
|---|---|---|---|
| D1 | arm 2's dispatch deadline (2000 ms constant stays; its dispatch contains no multiplicative pacing — the second append's busy window is count-based, ~350 ms measured, additive-only growth, ~2x+ deadline headroom quiet) | follow-on work on issue #241 | a timing-lane red on this test whose raw log shows arm 2's `result.error is not None` failing with status UNKNOWN (deadline cut before classification) |
| D2 | arm-1 Path-A hardening (holder release after busy give-up → ERROR/RESOURCE_LIMIT at the same assert) | follow-on work on issue #241 | a timing-lane red at the arm-1 assert whose result shows status ERROR with `RESOURCE_LIMIT` (§1.1's differential-stall shape) |
| D3 | the census comment's "633 ms" horizon correction (measured ~350 ms, §1.1) — stronger arm-2 margin, recorded here | documentation on issue #241 (comment at PR time; no code) | n/a — a correction, carried by this record |
| D4 | migrating the paced sequential-model family onto an injected clock (the census's stated long-term target; would retire this entire class) | issue #241 closure pass | the standing census trigger: another member of this file's family redding in-lane after this slice lands |

## 5. Alternatives considered and rejected

- **`TrialInfrastructureError` classification with retry (the PR #236/#246 pattern).**
  Rejected on three grounds. (i) That pattern classifies host starvation of the fixture
  BEFORE the measured quantity (construction, priming) and retries on a fresh rig; here
  the starvation lands INSIDE the measured dispatch — a retry belt would re-run the very
  race under assertion, and the first attempt's genuine-mechanism red (a real writer hang,
  a broken clamp) would present identically to a load red at attempt 1, spending a retry
  on what may be a real defect — the exact laundering the doctrine warns against. (ii) The
  belt does not exist in this file (no `run_trial`, no classification sites) — porting it
  is a larger surface than the defect. (iii) The relativization removes the load
  sensitivity at its root instead of detecting and retrying its symptom.
- **Raising the constant (2000 → 5000+).** Still absolute; the census documents runner
  regimes that stretch 5.4x today and nothing bounds tomorrow's. The doctrine prefers
  in-run relativization, and the derived form is provably adaptive where a constant is
  provably not.
- **Shrinking the workload (fewer chunks).** Trades the back-end budget fragility for a
  front-end race fragility: the holder must land its `BEGIN IMMEDIATE` inside a much
  shorter mid-capture window, and the `stretch >= 110` floor semantics dilute. Rejected.
- **Touching arm 2 in the same slice.** Its deadline margin is additive-only (§4.1 D1);
  minimal-increment discipline says fix the observed mechanism, document the sibling, and
  carry a trigger.

## 6. Invariant, cross-surface, and CI impacts

- **Invariants: none touched.** The diff contains no `src/` or `standards/` bytes. STO-1
  (single-writer store; the store reads no clock) is untouched — no store code changes.
  The row-B commissioning contract (`busy_timeout` set at open; the dispatch clamp derives
  from the open default) is preserved by the floor argument in §4.
- **Cross-surface: none.** No MCP tools, REST/openapi, CLI, operator docs, device-developer
  guide, vendored standards, fixture lattice, or SDK surfaces move. The `timing` marker
  stays (whole-module, `tests/integration/test_capture_sequential_model.py:82`); the lane
  row in `docs/internal/drift-and-obligations.md` needs no edit — it describes the lane,
  not per-test budgets. No on-disk format or schema is involved.
- **CI cost:** one extra capture per execution of this test on the serialized
  `timing` lane (`ubuntu-latest`, own fresh VM, `timeout-minutes: 15`): ~0.3-0.5 s quiet,
  bounded by the reference's own success. No new jobs, no gates-lane change (the marker
  partition is untouched).

## 7. Proof plan — what is provable and what is not

The prior slices' three-way proof shape, applied honestly to a flake:

1. **Signature mapping (done, deterministic — §1):** deadline exhaustion reproduces the
   CI failure byte-for-byte with zero load. This leg is conclusive.
2. **Load reproduction (attempted, not achieved — §1):** 6 runs at ambient load avg ~35
   stayed green (peak 605.9 ms). This host cannot reach the CI stall depth; the leg is
   disclosed as failed-to-reproduce, not quietly dropped.
3. **Reachability arithmetic (done):** 4.8x headroom vs a file-documented 5.4x CI stretch.

Builder's pre-merge obligations (the G3 adaptation for a scaffolding fix):

- **RED control on the fixed test:** a scratch copy of the FIXED file with the derived
  budget forced to 250 ms must red with the same UNKNOWN signature — proving the fix did
  not numb the assert's sensitivity to a real budget exhaustion.
- **Floor control:** three quiet executions print `budget 2000 ms from reference ...`
  (floor bound, today's exact behavior) — the print from §4.3 is the evidence.
- **Unchanged-assert control:** the diff shows no asserted magnitude moving (OK status,
  110 floor, 300 commissioning, arm-2 constants byte-identical).
- **FAST lane** per CLAUDE.md §3 (ruff; fresh-cache bare mypy; focused pytest for this
  file), full battery before push.

## 8. Pre-committed acceptance rule (written before any post-merge number is read)

Metric: timing-lane executions, classified for row-12 recurrences of the arm-1 signature
(UNKNOWN at the arm-1 OK assert). The slice-4 live window (≤2 red executions per 40 with
every red in a named family) continues; this rule nests inside it.

- **Ship:** the first post-merge timing execution is green, AND zero row-12 arm-1-signature
  reds occur in the 40-execution window, AND the live ≤2/40 family rule holds.
- **Kill:** any row-12 red with the arm-1 UNKNOWN signature in the window (the fix failed);
  OR any red of a touched mechanism (the live rule); OR ≥3/40 overall (the live rule). A
  kill-red whose in-run print shows `budget > 4000 ms` means the workload out-stretched
  even a 3x-scaled reference — that falsifies k=3 specifically: re-derive from the
  recorded reference walls, or move the family to an injected clock (D4) rather than
  re-raising constants.
- **Underpowered, not conclusive:** fewer than 40 executions sampled when a candidate red
  arrives; OR the served log truncates before the failing assert's identity and status are
  readable (the AR-7 lesson: pull the raw Actions log BEFORE any rerun); OR the red is a
  job-level timeout kill (a lane-infra event per slice 4's own categorization — never
  counted as a family red). In these cases: collect the raw log, extend the window, decide
  nothing on the truncated read.

## 9. Top risks, each with its falsifier

- **R1 — the reference capture is a new failure surface.** Its own dispatch could be cut
  under deep load (it has the same real-paced workload). Mitigated in-design by the 10 s
  scaffolding deadline and the loud `reference capture degenerate` assert — if it fires,
  the red is honest and names itself. Falsifier: a lane red at the reference assert on a
  non-timing diff — means 10 s was not enough for one uncontended capture, i.e. a regime
  finding, and D4 (injected clock) becomes the only sound answer.
- **R2 — a within-run differential spike > ~1.9x between reference and arm 1** still cuts
  arm 1. The kill clause covers it; the printed budget makes the arithmetic auditable.
- **R3 — the ordering constraint is missed at build time** (reference installed after the
  `first_append` wrap → arm 1's sequencing silently destroyed). Guarded by the builder
  obligation that three quiet runs print the floor AND pass with `stretch >= 110` (a
  destroyed sequencing fails the floor or the OK assert immediately), plus this record's
  §4 placement note in bold.
- **R4 — the mechanism read is wrong for some future instance** (e.g. Path A, §1.1).
  D2's trigger signature (ERROR/RESOURCE_LIMIT at the arm-1 assert) discriminates it from
  the deadline signature on sight.

## 10. Tier and the Step-1 keyword scan (#254)

Expected diff: this record (new `.md`) plus the test-file edit described in §4. Tier by
the rubric's path rules: **Tier 2** — a test-code change under `tests/` plus a
docs/record file; no Tier-3 path matches (no `src/benchweave/contracts/`, no `standards/`,
no `state/` or migrations, no registry, no fixture lattice, no dependency or submodule
motion).

Design-time scan over the expected added/removed text, code and docs alike, for the eight
Step-1 keywords as literals on added lines — counts recorded in §10.1. Disclosed per the
slice-3/4 precedent: the review re-derives the tier over the REAL diff; hunk CONTEXT
lines in the test file can carry a keyword (the file's imports and the holder helper do),
and if the real diff's added lines carry any of the eight, the slice takes the Tier-3
lane with the standing adversarial review — the builder re-runs the scan pre-PR and
records it. This record's own text was scanned after drafting (§10.1).

### 10.1 Scan result (mechanical, over this record's full text)

**0/8** — all eight rubric keywords count zero as literals on this
record's lines (mechanically scanned 2026-10-17; the count line itself deliberately does
not spell the words out — the rubric's Step-1 list is the authority). The §4 code sketch
adds none of the eight (no thread construction — the reference runs on the test thread).
The expected test-file edit's added lines: same 0/8 by construction (the derivation uses
only `time.monotonic`, arithmetic, and the existing dispatch surface).
