# Issue #156 — RunWorker unguarded success-path emit: design record

Date: 2026-09-23. Branch for build: `fix/issue156-unguarded-emit`. Base: `main` @
`cb836e4`. Tracker: madeinoz67/benchweave#156.

## 1. Root cause (verified in code, not taken from the issue text)

`RunWorker._drain_with` (`src/benchweave/interfaces/worker.py:135-183`) runs each job
under `try / except BaseException / else / finally`. The `except` arm is the Task-11
poison guard: it projects `terminal`, logs, and wraps its own `append_bench_event` in
`try/except Exception` + `_LOG.exception` (worker.py:168-176) — "a raising call inside
the poison handler would defeat the guard."

The `else` arm (worker.py:171-173) has no such guard:

```python
else:
    store.put_run_state(run_id, bench_id, "terminal", self._now_iso())
    self._emit_completion(store, coordinator, run_id, bench_id)
```

`_emit_completion` (worker.py:185-207) calls `store.get_run` and up to three
`append_bench_event` calls. `append_bench_event`
(`src/benchweave/interfaces/operations.py:176-218`) resolves evidence via
`_resolve_event_evidence` (operations.py:143-173), which **raises
`ValueError("no document anchor …")` by design** when neither the run's binding nor
the bench's commissioned configuration resolves — the docstring: "a programming error
raised loudly, never a schema-violating empty evidence object on the wire." The raise
is correct; the unguarded call site is the defect. Any `Exception` from the emit (the
`ValueError`, a sqlite `OperationalError`, a `KeyError`) escapes the `while True`
loop, unwinds `_drain`'s `finally` (`store.close()` runs), and kills the thread.

Precise blast radius (from the loop structure): the dying job's own `finally` DOES
run — `self._done += 1; self._queue.task_done()` (worker.py:174-176) — so the current
job's queue accounting balances, but every **queued, not-yet-started** job is never
`get()`: `queue.join()` then blocks forever, and `RunWorker.join` (worker.py:100-111)
calls `self._queue.join()` **first, unconditionally**:

```python
def join(self, timeout: float | None = None) -> None:
    self._queue.join()
    if not self._stopping.is_set() and self._done == self._submitted_count:
        return
    self._thread.join(timeout=timeout)
```

Second finding, load-bearing for scope: **`join(timeout=...)` has never bounded the
queue wait.** `queue.Queue.join()` accepts no timeout; the caller's `timeout` only
bounds the trailing `_thread.join`. The sole production caller already asks for a
bound — `_lifespan` (`src/benchweave/interfaces/app.py:431`) calls
`worker.join(timeout=5.0)` at shutdown — so today a wedged worker hangs gateway
shutdown indefinitely while the code claims a 5-second bound. The fix makes the
caller's existing stated intent true; it does not invent a new deadline.

The repro is real, not hypothetical: the #155 measurement branch hit it during G7
debugging, and
`tests/integration/test_capture_sequential_model.py::test_queued_run_delay_behind_a_capture`
(lines 327-330) already seeds a bench configuration row *specifically because*
`_resolve_event_evidence` refuses an anchor-less event — the refusal is a known,
reachable worker-side outcome, not an exotic one.

## 2. Mechanism

Two production edits, both extending the containment pattern the file already
carries, plus one caller change.

**Edit A — success-path containment** (`worker.py:171-173`). Wrap the `else` body as
a unit (terminal projection + completion emit) in `try/except Exception` with
`_LOG.exception`, mirroring the poison-path emit guard (same catch width, same log
channel):

```python
else:
    # Contained per job, symmetric with the poison guard's own emit
    # guard: no completion-bookkeeping failure may kill the drain.
    # Catches Exception (precedent width): a BaseException during
    # completion bookkeeping still ends the drain — stated residual.
    try:
        store.put_run_state(run_id, bench_id, "terminal", self._now_iso())
        self._emit_completion(store, coordinator, run_id, bench_id)
    except Exception:
        _LOG.exception(
            "run_worker completion close failed run_id=%s", run_id
        )
```

`except Exception`, not `BaseException`, matching the in-tree precedent (the poison
handler's inner emit guard catches `Exception`): operational failures of projection
and emit are contained; a `BaseException` during completion bookkeeping still kills
the drain (stated residual, same as today for every other unguarded line). Wrapping
the pair rather than only `_emit_completion` closes the identical two-line hole
directly above the named defect (`put_run_state` raising kills the thread the same
way); containing it can only improve on a dead worker.

Symmetry widening in the same edit: the poison handler's own first
`store.put_run_state` (worker.py:159) gets the same 3-line guard. Leaving it
unguarded while guarding its success-path twin is an asymmetry the review would
rightly flag — it is the same defect class, four lines away, same cost. The poison
handler's already-guarded `append_bench_event` is unchanged.

Semantics after Edit A, on a contained completion failure: the run's durable record is
already complete and truthful — the coordinator wrote its terminal record during
`start_run` (CTL-9), and only the bench-stream events (`run_changed`, possibly
`trip`/`evidence_gap`) are lost, with a gateway-log ERROR carrying the failure (the
D4-sanctioned home for worker operational context). The drain continues.
(Fix-wave amendment: this paragraph is false for the sub-case where the failing
line is the terminal `put_run_state` itself — the projection then stays `running`
over the completed durable record until the startup sweep's run-state-aware leg
reconciles it; see §11, F2.)

**Edit B — bounded join** (`worker.py:100-111`). Return `bool`, bound the whole join
when a timeout is given, and surface a dead worker immediately:

```python
def join(self, timeout: float | None = None) -> bool:
    """Wait for the queue to drain. True: drained (and, after stop(),
    the thread exited within bounds). False: the queue did not drain in
    bounds, or the worker thread is gone with work outstanding — nothing
    will ever drain it; hanging would be a lie.
    """
    deadline = None if timeout is None else time.monotonic() + timeout
    while self._queue.unfinished_tasks:
        if not self._thread.is_alive():
            return False
        if deadline is not None and time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    if not self._stopping.is_set() and self._done == self._submitted_count:
        return True  # fast path: worker parked on its next poll
    if deadline is not None:
        timeout = max(0.0, deadline - time.monotonic())
    self._thread.join(timeout=timeout)
    return not self._thread.is_alive()
```

`unfinished_tasks` is the exact predicate `queue.join()` waits on and a
typeshed-declared `queue.Queue` attribute (amended in the fix wave — it is not
queue-module-documented); polling at 50 ms keeps the existing fast-path pin green
(`tests/unit/test_seam_control.py:286-289` asserts join returns in <5 s when drained —
the loop exits before its first sleep when the queue is empty). `timeout=None`
preserves today's graceful unbounded drain for a LIVE worker, but a dead worker now
surfaces immediately on both paths (was: hang forever). The trailing thread join
spends the deadline's remainder, so the total respects one bound. `worker.py` gains
`import time`; no other imports move.

**Edit C — the caller surfaces it** (`app.py:431`). `_lifespan` consumes the return
value and degrades loudly instead of silently proceeding:

```python
worker.stop()
if not worker.join(timeout=5.0):
    _LOG.error(
        "run worker did not drain at shutdown (submitted=%d); "
        "outstanding runs are recorded interrupted at next startup",
        worker.submitted,
    )
```

The 5.0 value is untouched — it is the caller's already-expressed intent; this
increment makes it real. Disclosure (not silent): at shutdown with an in-flight run
longer than the bound, the gateway now proceeds after 5 s instead of waiting out the
run; the startup recovery sweep (`_recover_interrupted_runs`, app.py:206) records the
run `interrupted` — CTL-9's honest unwind, the same one the issue names as the
stranded-state unwinder. The worker thread is `daemon=True`; an external supervisor
was always the real bounder of a long graceful shutdown. A short paragraph lands in
`docs/operator-guide.md` (obligation 4 — service behavior; the guide currently has no
shutdown section, so this adds one: bounded drain at shutdown, outstanding runs
unwind as `interrupted` at next start).

## 3. Minimal first increment, and the deferrals

All three issue-named parts are ONE increment (one RED→GREEN slice, one commit plus
the design record committed first): the fault arm is the RED proof of both production
halves, and it is only hang-safe with the bounded join in place. Splitting them would
ship a fault arm that can hang the suite in RED.

| # | Deferred | Why | Reopen trigger |
|---|---|---|---|
| D1 | Replay/outbox for the missed bench event | New architecture, no in-tree precedent; the run record + gateway log are the honest record (A06) | An operator or client report of a consumer wedged on a missing `run_changed` |
| D2 | Tuning / commissioning the shutdown drain bound (5.0) | It is the caller's existing number; whether it is the right grace is an operator question, not this fix's | Operator-guide review, or an observed shutdown that abandoned an in-flight run that mattered |
| D3 | Persistent-emit-failure alarm (counter/metric on repeated "completion close failed") | One ERROR line per run is the D4 posture; alerting is a monitoring feature | Repeated `run_worker completion close failed` lines in an operator's gateway log |
| D4 | `submit()` queue depth bound | Different defect class (unbounded growth), not named by #156 | Any report of unbounded accepted-run backlog |
| D5 | Cancellation of the in-flight run at shutdown (stop currently means finish-or-abandon) | Commissioning-adjacent posture change (A04), out of #156's scope | D2 reopening, or a bench whose runs exceed realistic shutdown grace |
| D6 | The `create_run`→`put_run_state` crash-window residual | Already ledgered in `docs/compatibility.md` D13 batch B; adjacent, untouched | As ledgered there |

## 4. Precedent (all extended, none invented)

- **The poison-path emit guard** (worker.py:168-176): same file, same catch width,
  same `_LOG.exception` channel, same rationale in its own comment. Edit A is that
  pattern applied to the sibling branch.
- **`tests/integration/test_event_recovery.py::test_worker_survives_poisoned_build_run`**
  (WP08 Task 8, watch-flake closure in `docs/compatibility.md`): the survival
  assertion shape — poisoned job lands terminal `outcome_unknown`, worker keeps
  serving later runs. The new arm mirrors it at the emit seam.
- **`tests/integration/test_capture_sequential_model.py::test_queued_run_delay_behind_a_capture`**:
  the direct-worker harness shape (real `Store`, no-op fake coordinators, multiple
  `submit`s, bounded `join`, store-seeded bench row) — the fault arm is this harness
  plus an injected emit failure.
- **`tests/unit/test_seam_control.py::seam_control` / the fast-path join pin
  (lines 286-289)**: the no-regression control for Edit B, already green and required
  to stay green unmodified.

## 5. Invariant impacts

Checked against `docs/internal/invariants.md` and
`docs/smart-test-gateway-decisions.md`.

- **A06 (evidence over assertion) — preserved, and restored.** With a contained emit
  failure the durable run record is complete (coordinator-written terminal record);
  what is missing is a derived bench-stream event, disclosed as a gateway-log ERROR.
  Today's behavior — a stranded queue of runs frozen in `accepted` forever — is the
  actual A06 violation (outcomes neither terminal nor uncertain, just stuck).
- **A04 (protection/completion never depend on continued AI judgement) — untouched.**
  No AI involvement anywhere in the path. The bounded join makes shutdown
  deterministic without depending on any agent: expiry routes to the deterministic
  recovery sweep, which records `interrupted` and applies the protective transition
  (CTL-9).
- **A03 / one controlling procedure — restored.** A dead worker with a queued backlog
  leaves runs that never start and are never refused; containment returns those runs
  to the FIFO one-active-run discipline.
- **CTL-9 — not amended.** Run ownership, terminal records, and the interrupted
  recovery idiom are unchanged; Edit C only routes to the existing sweep.
- **STO-1/STO-2 — untouched, one disclosure.** No store write patterns change.
  STO-2's gap-free per-stream sequence is about numbers never skipped or reused; a
  never-attempted event shortens the stream without creating a detectable sequence
  gap — the residual is the missing event itself, carried by the ERROR log (D1 is the
  reopen for making it detectable on the wire).
- **A07 (audit failure constrains new work) — consistent, no amendment.** A failed
  completion emit does not erase the run's durable evidence; the seven-kind bench
  stream is a projection. The poison path already holds exactly this posture for its
  own emit.
- **STO-3 (single-writer hold) — no interaction.** The hold is process-level
  (`_lifespan`); the worker's thread-affine connection serializes via WAL +
  busy timeout, unchanged.
- **New invariant? No.** The containment contract already exists as the Task-11
  poison-guard contract in the `RunWorker` docstring; this increment completes that
  contract's scope (the docstring gains one sentence: completion bookkeeping is
  contained the same way). Codifying it as a CTL row is not warranted for a
  completion-of-scope, not a new mechanism; the fault arm is the pin either way.

## 6. Surfaces (drift walk, `docs/internal/drift-and-obligations.md`)

- Obligation 4 fires: `docs/operator-guide.md` gains the shutdown-drain paragraph
  (Edit C disclosure). README has no shutdown coverage — no change.
- No wire surface moves: no MCP tool, no REST/openapi path, no event payload, no
  standards byte, no SDK touch, no fixture-lattice move, no submodule pointer. The
  join signature is not on the wire. `docs/compatibility.md` needs no row (no wire
  change; the D4 log posture already covers worker operational context).
- `tests/faults/` gains one file (`test_worker_drain_faults.py`); the full suite plus
  faults already runs in the CI `gates` job — CI cost is the two new tests' runtime
  (sub-second; the arms are event/poll driven with generous slack, not sleeps).
- CHANGELOG renders from conventional commits (machine-driven, no hand edit).

## 7. Measurable proof — pre-committed acceptance rule

Committed here BEFORE any run. Numbers fixed now: fault on job **3** of **6**;
poll slice 0.05 s; observation window **T_obs = 30 s** (no-op fake coordinators drain
in milliseconds — 30 s is three orders of magnitude of slack); watchdog window **5 s**
per bounded-join call; **3 consecutive runs** required on a healthy checkout; RED
shown once per production half by revert-in-place.

**Arm 1 — emit fault (primary).** Direct `RunWorker` (sequential-model harness
shape): real `Store`, seeded bench row, `build_run` returns a no-op fake (no terminal
record, no monitor, so exactly one `append_bench_event` per job). Monkeypatch
`benchweave.interfaces.worker.append_bench_event` (the module-level import both
worker paths call) with a counting wrapper that raises
`ValueError("no document anchor …")` — the real refusal's class and text — on call 3
only, passing through otherwise and recording completed calls. Submit 6 jobs.

PASS iff all four hold:
1. All 6 runs reach `state == "terminal"` in `Store.list_run_states(bench)`
   (`state/store.py:735`) within T_obs of the last submit (**6/6** — the
   recorded-terminal metric).
2. Exactly **5** of 6 completion emits completed (job 3's event is honestly missing);
   jobs 1, 2, 4, 5, 6 each emitted.
3. After the drain, a 7th submit reaches `terminal` within 10 s (**liveness past the
   fault** — the worker survived, not just the queue).
4. `worker.join(timeout=30)` — called inside a daemon watchdog thread, main waiting
   bounded — returned `True`.

**Arm 2 — bounded join (two sub-arms, both watchdog-shaped so RED cannot hang the
suite).** (i) *Dead worker*: construct, do NOT `start()`, submit 2 jobs;
`join(timeout=0.5)` in a watchdog — PASS iff it returns within the 5 s watchdog
window AND returns `False` (a dead thread surfaces, it does not hang). (ii)
*Live-but-stuck*: coordinator blocks on an unreleased `threading.Event`, submit 1
job, `join(timeout=0.5)` — PASS iff `False` within the watchdog window while the
thread is verifiably alive (the deadline branch, not the death branch).

**Control.** `test_run_state_reaches_terminal_after_worker_drains` (fast-path pin,
<5 s) and `test_worker_survives_poisoned_build_run` stay green UNMODIFIED — the
control that the join rewrite changed nothing it did not need to.

**RED checks (G3).** Revert Edit A only (keep Edit B): Arm 1 must fail with exactly
**3/6** terminal (job 3's `finally` ran; jobs 4-6 never started) and assertion 3
fails; worker thread dead. Revert Edit B only (keep Edit A): Arm 2(i) fails cleanly
at the 5 s watchdog (`queue.join()` hangs), Arm 1 stays green (guard holds, queue
drains). Restore both: all green.

**Kill directions.** *Ships*: both arms 3/3 green with the fix, both RED shapes
shown, control pins and the full cold suite green (Tier 3). *Kills the fix*: Arm 1
fails with the fix in place (containment does not hold — diagnose, do not tune).
*Kills the measurement, not the fix*: Arm 1 passes with Edit A reverted (the
injection measures nothing — fix the test before shipping anything); any flake in
the 3 consecutive runs (timing underpowered — widen T_obs/watchdog observation
bounds, never the production bound, and re-run; treat as inconclusive, not as a
pass).

## 8. Top risks, each with its falsifier

1. **Swallowing the emit exception hides a systemic event-stream failure** (every
   run's `run_changed` silently missing; only log lines remain). Falsified/observed
   by: the per-run ERROR line is caplog-assertable in Arm 1 and greppable
   operationally; D3 is the reopen. The alternative (killing the worker) is strictly
   worse — it loses the runs too.
2. **The shutdown posture change** (5.0 now real: an in-flight run longer than the
   bound is abandoned to `interrupted` instead of awaited). Falsified by: D2's reopen
   trigger; meanwhile the unwind is CTL-9's honest `interrupted`, never a fabricated
   outcome, and the external supervisor was always the effective bounder.
3. **Polling `unfinished_tasks` races a concurrent `submit`** (join may return just
   before a freshly-put item is observed). Not reachable for the real callers —
   submits strictly precede join in every caller (tests) or have ceased (shutdown,
   server stopped accepting first). Disclosed in the code comment.
4. **`join` return-type change breaks a caller.** Audit: `app.py:431` (consumes the
   new value), three test call sites (statement-position, value ignored —
   source-compatible), `seam_control` teardown. Mypy strict gate is the falsifier.
5. **Containment interacts with store/thread lifecycle.** It does not touch
   connection ownership (thread-affine store unchanged, `_drain`'s `close()` finally
   unchanged, STO-3 hold process-level). The full cold suite + `tests/faults/` is
   the falsifier.
6. **`BaseException` residual**: a `KeyboardInterrupt`/`SystemExit`/`MemoryError`
   inside completion bookkeeping still kills the drain (same as today). Deliberate —
   precedent width (`except Exception`), stated in the guard comment; a stopping
   process should not be swallowed per-job.

## 9. Tier and review slate

**Tier 3** (review-rubric Step 1): the diff text contains `threading` and touches
concurrency-shaped code in `src/benchweave/interfaces/worker.py`; `tests/faults/` is
in scope. Consequences: full cold suite, G3 RED-sanity mandatory, G6 adversarial
refute mandatory.

- **Adversary (G6): fires** — Tier 3. Attack surface to hand it: revert-in-place RED
  proofs, the watchdog shapes, the fast-path pin, shutdown semantics.
- **Standards-governor: does NOT fire** — no `standards/` byte, no contract lock, no
  SDK surface, no vendored tree, no version string.
- **Mechanism-critic: fires, scoped** — Edit B introduces a new time bound and
  return semantics in the concurrency path (deadline accounting across two waits,
  dead-thread detection, the shutdown posture flip). The critic lane is warranted
  for that half; Edit A extends an existing guarded pattern and needs no bound
  critique.

## 10. Build notes

- Branch `fix/issue156-unguarded-emit` off `origin/main` (`cb836e4`). Design record
  committed first (pre-commitment provability), then one RED→GREEN slice: Edits
  A/B/C + `tests/faults/test_worker_drain_faults.py` + the operator-guide paragraph.
- Gates, with `UV_PROJECT_ENVIRONMENT=venv`: `uv run ruff check .`; `uv run mypy`
  (bare); focused `uv run pytest tests/faults/test_worker_drain_faults.py
  tests/unit/test_seam_control.py tests/integration/test_event_recovery.py
  tests/integration/test_capture_sequential_model.py`; then the full cold suite
  (Tier 3). Counts from `--junitxml` attributes / exit codes, never a filtered
  summary line. RED proofs run before merge and land in the review evidence.

## 11. Fix-wave amendments (2026-09-23, post-refute)

The adversarial refute pass executed two wedges the mechanism above left open,
plus claim defects; all folded on `fix/issue156-unguarded-emit` with RED arms in
`tests/faults/test_recovery_sweep_faults.py` (the adversary's executed probes as
acceptance predicates).

- **F1 (MEDIUM) — queued ghost wedges the bench forever.** Edit B/C make the
  bounded shutdown drain abandon queued-not-started runs at 5 s; the startup
  sweep discovered only active-lease holders, so an `accepted` projection with
  no lease and no terminal survived every restart in `LIVE_RUN_STATES` and the
  §5 busy oracle refused every future `run_start` on that bench, permanently.
  **Fix (R1):** `recover_interrupted` gains a run-state-aware leg AFTER the
  lease leg — live projection rows (non-terminal; the complement of the seam's
  `{accepted, running, protecting}`) with no active `run:` lease and a durable
  run row are interrupted (`body_outcome=interrupted`,
  `safe_state=unknown`, the same record path, evidence refs and ledger
  semantics as the lease-held leg) or, when a durable terminal already exists,
  reported for projection reconcile only (the record is never rewritten).
  Rows with no durable run behind them stay out of scope: that is the
  `create_run`→`put_run_state` crash window already ledgered in
  `docs/compatibility.md` D13 batch B (and D6 here). Tombstoned runs are
  skipped — the tombstone owns that run's end.
- **F2 (MEDIUM-LOW) — stale `running` projection over a durable terminal.**
  Edit A's containment unit wraps `put_run_state` too; if that write fails the
  projection stays `running` with the lease already released — invisible to
  the lease scan, same wedge. Same fix leg (the reconcile arm).
- **Order/edge probe (instruction):** durable terminal + active `run:` lease +
  live projection — CTL-9's ordering (finalize → release → project) makes the
  window narrow, not impossible (a crash between `finalize_run` and the lease
  release lands there). Probed and pinned: the lease leg releases the stale
  lease without interrupting; the run-state leg then reconciles the
  projection; the bench un-wedges; the completed record is untouched.
- **F3 (LOW) — `join(timeout=None)` fallthrough.** Docstring-only: names the
  permanent-hang consequence of the fast-path fallthrough under `None`
  (trailing `thread.join(None)` on a parked worker only `stop()` ends). No
  current caller passes `None`.
- **Critic MOVE — operator-guide over-claim.** "applies the protective
  transition before anything new executes" removed: recovery records
  `safe_state="unknown"` and never touches a device; the guide now says
  exactly that and tells the operator to verify the bench's physical state.
- **Critic LOW — shutdown log conflates join's two False meanings.** The
  `_lifespan` ERROR line now reports `(submitted=%d done=%d)` via a new
  read-only `RunWorker.done` property.
- **NIT** — §2's "a documented `queue.Queue` attribute" corrected to
  "typeshed-declared" (this section's Edit B paragraph, amended in place).
- **Interface disposition (app.py):** the recovery loop distinguishes the two
  legs by reading the durable record's `body_outcome` (the authority):
  interrupted runs keep `RECOVERY_RUN_CHANGED_REASON`; reconciled runs log
  the new `RECOVERY_PROJECTION_REASON`. Both close the queue projection and
  emit one `run_changed`.
