# Issue #513 — the worker poison guard's durable terminal record

- **Tracker:** madeinoz67/benchweave#513 (row D1 of the #506 design record's deferral
  table; the same evidence-gap class #506 closed on the protection path).
- **Date:** 2026-11-08. Design pass only — this record lands as the arc's first commit,
  before any test or measurement in this increment has run.
- **Evidence basis:** every file:line cite below was read this session against this
  checkout (`main` at `084c5e6c`, merge of PR #540) with native reads — the gortex
  daemon reports this cwd untracked (`repo_not_tracked`), so graph tools were
  unavailable by structure, not by choice.
- **Tier call (design-time, #254):** **TIER 3** — by the Step-1 keyword rule, before any
  path rule is needed. See §8.

## 1. Finding, confirmed at source

`RunWorker._drain_with`'s poison guard (`src/benchweave/interfaces/worker.py:254-286`)
catches `BaseException` around the whole per-job arm — the `running` projection write,
`build_run` construction, and `start_run` — and on a poison:

1. closes the queue projection terminal (`worker.py:266`, itself guarded at `:267-273`),
2. logs `run_worker poison` (`worker.py:274-277`),
3. emits `run_changed` (`worker.py:278-286`, guarded),

and writes **no durable terminal record**. The comment block at `worker.py:256-264`
states this as the original Task 11 design: "the queue state closes terminal WITHOUT a
terminal record, so the projection reports outcome_unknown — honest uncertainty, never a
fabricated outcome." The ending reason lives only in the gateway log, which rotates.

Two adjacent facts sharpen why this is a defect class rather than a stance:

- The wire projection's own comment claims an ordering the poison arm violates:
  "The worker persists the terminal record before publishing terminal queue state"
  (`src/benchweave/interfaces/operations.py:1956-1958`). The `else` arm honours it (the
  record lands inside `start_run` before the `terminal` `put_run_state` at
  `worker.py:295`); the poison arm inverts it — projection terminal first, record never.
- The gap is **unhealable**: the next-boot recovery sweep skips rows whose projection
  already reads terminal (`src/benchweave/control/coordinator.py:1069-1075`,
  `state == "terminal"` → `continue`). A poison run's row therefore never gains a
  record — not at poison time, not at recovery time. Contrast the opposite window
  (durable terminal + stale live projection), which the run-state-aware leg explicitly
  heals ("Stale projection over a durable terminal: report it for projection close
  only", `coordinator.py:1164-1167`).

The #506 design record already named this exact site as partial containment — §1 site 4:
"Downstream containment is partial only: `worker.py:254-286` (`_drain_with`'s poison
guard) converts the escape into a terminal PROJECTION with no durable terminal record" —
and deferred it as row D1 with the reopen trigger that became this issue.

## 2. Precedent — #506's belt (what landed) and #507/#260/#534's recovery legs (the shape to mirror)

**The #506 precedent** (`.claude/deep-review/2026-10-21-issue506-protective-raises.md`,
§2 arm 2, landed in `_finish_run` at `coordinator.py:1433-1524`): a `BaseException`-width
belt around the ending's own machinery — on raise, synthesize the honest minimal result
(`safe_state="unknown"`, reason `uncaught_protection_exception: {type}: {exc}`), then
**the record, `finalize_run` and lease release proceed anyway**; a non-Exception pending
re-raises AFTER the record lands. Its invariant motion was a CTL-9 amendment
(`docs/internal/invariants.md:121-138`): "no exception class skips the ending's own
protection half either."

**The recovery precedent** (the machinery #513 mirrors): both recovery legs of
`recover_interrupted` (`coordinator.py:978-1052` lease leg, `:1121-1163` ghost leg)
terminalize a run whose own machinery never landed a record, through:

1. `_recovery_record_version(run, contracts, ContentStore(store))` (`coordinator.py:226`,
   module-level) — the #260/#534 judge: doc-first binding-pin resolution, echo fallback
   with the retained-bytes split, `access_failure` (defer) and `containment` (write
   nothing) classes;
2. `build_terminal_record(...)` (`coordinator.py:532`, module-level) — validates against
   the run's own version's `run-record.schema.json`; `outcome` derived, never input;
3. `finalize_run` (`src/benchweave/state/store.py:351`) — the durable stamp;
   `ValueError` when unknown or tombstoned.

**How closely the poison path can mirror it — and where it cannot:**

| Aspect | Recovery leg | Poison arm (this design) |
|---|---|---|
| Judge | `_recovery_record_version` | same function, unchanged |
| Record builder | `build_terminal_record` | same function, unchanged |
| body_outcome / safe_state | `interrupted` / `unknown` | `outcome_unknown` / `unknown` (§5) |
| Write predicate | `run["terminal"] is None` (legs only process non-terminal rows) | same predicate, made explicit — **never overwrite** (§4) |
| Access failure | defer to next sweep (run untouched) | **cannot defer** — log, write nothing, projection still closes (§6) |
| Containment | write nothing, report `contained` | same: write nothing, log, projection closes |
| Lease release | releases the run lease | **deferred** — the worker never saw the reservation; next boot's lease leg releases it unconditionally over any terminal state (`coordinator.py:1052`) |
| Ledger rebuild | `_rebuild_ledger_from_events` into the boot coordinator's in-memory ledger | **not needed** — a poison-terminal run never re-walks, exactly like any completed run whose coordinator ledger also evaporates |
| Evidence refs | binding pin + `events:{run_id}` digest | same two, digest computed store-side |

## 3. Scope: the branch, not the feeders

#513's fix is the poison **handler**, deliberately feeder-agnostic. Grounds, verified in
source:

- The poison branch is the **only** live-gateway exit that ends a run with no durable
  record. `start_run` returns only after `finalize_run` (`coordinator.py:1507-1524`), so
  the worker's `else` arm (`worker.py:287-300`) always runs over an existing record; a
  completion-close failure there leaves record + live projection, which next boot heals.
  Gateway crashes and never-started ghosts are owned by the recovery sweep and the
  stop-time sweep respectively.
- The #576-context feeder (bridge session poison: `host/otdp_bridge.py:1118-1130` sets
  `_failed=True` + `_stream_clear()`, `control/stream_polling.py:134-138` latches
  `session_failed`) is **contained degradation by design**: `poll_slice` skips failed
  engines (`control/stream_host.py:256-257`), later dispatches on a failed bridge are
  typed refusals, not raises (`otdp_bridge.py:339-340`) — such runs end through
  `_finish_run` **with** a record. If any variant of that class ever escapes as an
  exception, it lands in the poison branch and this fix catches it there — no feeder
  enumeration needed.

**Deferral with trigger:** a dedicated feeder fix is deferred; the trigger is the issue's
own reopen trigger (a second `run_worker poison` line over a run with no durable terminal
row) or any observed no-record ending that did not pass through the poison branch (a new
issue, not #513).

## 4. Mechanism

One new module-level function in `control/coordinator.py`, next to the recovery
machinery it reuses:

```python
def finalize_poisoned_run(
    store: Store, run_id: str, *, error: BaseException, now: str,
    contracts: Path = _CONTRACTS,
) -> bool:
    """Attempt the poison-path terminal record. True iff written."""
```

Body, in order:

1. `run = store.get_run(run_id)`; **write nothing and return False** when `run is None`,
   `run["tombstoned"]`, or `run["terminal"] is not None`. The last guard is
   load-bearing, not defensive: `_finish_run` re-raises a non-Exception pending AFTER
   `finalize_run` (`coordinator.py:1522-1523`), so the poison branch regularly fires
   with a record already landed (a `KeyboardInterrupt`/`CancelledError` belt re-raise is
   an ordinary test-run shape) — an unconditional write would **overwrite the true
   outcome**, the exact laundering this project forbids.
2. `decision = _recovery_record_version(run, contracts, ContentStore(store))`
   — unchanged judge. `access_failure` or `containment` set → log (the recovery
   prefixes) and return False: no record is safe or judgeable, and the poison arm cannot
   defer (requeueing a poisoned job is an infinite poison loop).
3. Else `build_terminal_record(run_id=run_id, binding_pin=decision.binding_pin,
   principal_id=run["principal_id"], started_at=run["started_at"], ended_at=now,
   body_outcome="outcome_unknown", safe_state="unknown",
   reasons=[f"run_worker poison: {type(error).__name__}: {error}", *decision.reasons,
            "run was not terminalised by its own machinery; body execution never resumes"],
   evidence_refs=[binding pin, events digest],  # the `_recovery_evidence_refs` shape,
   contracts=contracts, execution_version=decision.record_version)` then
   `store.finalize_run(run_id, record)`; return True.

`RunWorker` gains a keyword-only `contracts: Path = _CONTRACTS` constructor parameter
(default-preserving — every existing constructor call, including the Task 5 fakes, is
unchanged); `interfaces/app.py:1017` threads the same local `contracts` it already
computes for `_build_run_factory` into the worker. The poison arm becomes:

```python
except BaseException as error:
    try:
        finalize_poisoned_run(store, run_id, error=error, now=self._now_iso(),
                              contracts=self._contracts)
    except Exception:
        _LOG.exception("run_worker poison record failed run_id=%s", run_id)
    try:
        store.put_run_state(run_id, bench_id, "terminal", self._now_iso())
    ...  # existing projection guard, poison log line, guarded emit — unchanged
```

**Ordering — durable record BEFORE projection close**, for the first time on this path.
A crash between the two leaves durable terminal + live projection, which next boot heals
(`coordinator.py:1164-1167`); the current order's window (terminal projection, no record)
is the unhealable one (§1). This also brings the poison arm under the ordering the
projection code already claims (`operations.py:1956-1958`) and matches the
`finalize_run → lease release → projection close` discipline the recovery-sweep faults
test pins (`tests/faults/test_recovery_sweep_faults.py:173-174`).

**First increment ships exactly this.** No CLI surface, no query API, no operator-guide
prose beyond the invariants amendment (§7).

## 5. Vocabulary: `outcome_unknown`, not `interrupted` — decided, with the counter recorded

`terminal_outcome` (`coordinator.py:130-144`) and the run-record schema sanction both
pairs; the choice is semantic, and `outcome_unknown` wins on three grounds:

1. **Contract scoping.** The execution contract defines `interrupted` for the restart
   case: "After gateway restart, durable runs that were not terminal are recovered as
   interrupted" (`standards/execution/0.2.0/execution-contract.md:97`). A live-gateway
   worker poison is outside that definition; repurposing the value would need a corpus
   amendment (a digest-frozen, copy-never-move standards bump) out of all proportion to
   this mechanism.
2. **Wire preservation.** `_run_projection` renders record-present outcome from the
   record (`operations.py:1978-1987`); today's poison runs read `outcome_unknown`
   (`:1974-1977`). `body_outcome="outcome_unknown"` keeps the frozen interface surface
   byte-identical for this path; `interrupted` would flip the wire outcome.
3. **Minimal true claim.** The body verdict genuinely never landed;
   `outcome_unknown` asserts exactly that, and the mechanism — the audit answer #513
   asks for — rides `reasons[0]` (`run_worker poison: {type}: {error}`), durable and
   greppable in the same vocabulary as the log line.

Counter recorded: `interrupted`'s "never resumes" is also true, and it is the vocabulary
the stop-time ghost sweep uses for never-started runs (`interrupt_queued_at_stop`,
`coordinator.py:1185-1188`) — but that writer is explicitly sanctioned by the
2026-10-08 CTL-9 amendment; the poison path has no such sanction, and grounds 1-2 stand.

The null-record fallback keeps its contract sanction untouched: "A storage failure may
leave terminal_record null only for outcome_unknown or interrupted"
(`standards/interface/0.1.0/interface-contract.md`, §6 run_get) — a poison run whose
record write fails still reads outcome_unknown over a null record, exactly as today.

## 6. The write-failure question (A07 lens)

If the record write fails — disk, schema validation, `ValueError` on a tombstone race,
judge containment — **the run's outcome does not change**: the projection still closes
terminal, the poison log line still fires, `run_changed` still emits, the drain still
continues. Evidence storage stays a dependency of neither the containment nor the
worker's liveness — the same independence #506's belt gives the protective ending
(record lands even when the transition raised) and #507 gives the projection close
("closing only the projection invents no evidence… the wire reads outcome_unknown per
the frozen contract", its record §"not laundering"). The #507 KILL boundary carries
over verbatim: a containment-class poison run that gains a durable record or a wire
outcome other than `outcome_unknown` would be laundering — worse than the bug.

## 7. Invariant and drift impacts

- **CTL-9 amendment required.** The 2026-10-08 amendment enumerates terminal-record
  writers: "the supervision ladder never writes terminal records — only the
  coordinator's §5 ending or a recovery-shaped sweep do" (`invariants.md:113-120`). This
  design adds a third writer — the worker's poison record, recovery-shaped,
  judgeable-cohort-only, never over an existing record — and the enumeration must name
  it or the invariant text is falsified by the new code. The amendment rides this diff
  (`docs/internal/invariants.md`).
- **CTL-2 truth table:** unchanged — `outcome_unknown` maps by existing rows; no new
  vocabulary anywhere (run-record schema untouched; reasons are open strings).
- **STO-4 (lease):** unchanged; a poison-escaped reservation's lease is released by the
  next boot's lease leg over any terminal state (`coordinator.py:1052`) — the same
  world as a mid-run gateway crash today.
- **Surfaces that move:** `src/benchweave/interfaces/worker.py`,
  `src/benchweave/control/coordinator.py` (new function),
  `src/benchweave/interfaces/app.py` (one constructor kwarg threaded),
  `tests/faults/` (new file + one deliberate pin update, §9),
  `docs/internal/invariants.md` (CTL-9 amendment), this record.
- **Surfaces that do NOT move:** `standards/` (no wire value changes — the record shape
  and the null-record fallback already exist in the frozen contract), no JSON Schema, no
  on-disk format or migration (`terminal_json` content uses the existing run-record
  schema via the existing `finalize_run`), `state/store.py`, `openapi.json`,
  `mcp-tools.json`, the SDK submodule, the fixture lattice, `.github/` — **no new CI
  lane**. Tier-3 review depth (mandatory second adversarial reviewer) plus the cold
  full battery is the entire CI cost.

## 8. Tier and keyword scan (#254, design-time)

**TIER 3, first-match on the keyword rule** — the expected diff text (code + tests +
invariants amendment + this record, docs and code alike) contains, at minimum:
`recovery` (≥8: `_recovery_record_version` calls, recovery-posture comments, amendment
prose), `protection` (≥2: the CTL-9 amendment quotes the #506 protection belt),
`sha256` (≥3: evidence-refs construction and prose), `hashlib` (1: the events-digest
computation). The record you are reading contains all of them by construction. No path
rule is needed; none is avoided — `state/store.py` and `standards/` are deliberately
untouched.

## 9. Proof plan (RED-first)

New `tests/faults/test_worker_poison_record.py`, harness = the
`test_worker_drain_faults.py` shape (real `Store`, seeded bench row, bounded join), with
run rows created as `Operations.run_start` creates them (`store.create_run` with the
caller-echo binding, `put_run_state` accepted) — the production shape, since acceptance
precedes submit:

- **F1 (the RED row):** fake `build_run` raising `RuntimeError("boom")` → after join:
  `get_run(run_id)["terminal"]` is not None; `outcome == "outcome_unknown"`,
  `safe_state == "unknown"`; `reasons[0] == "run_worker poison: RuntimeError: boom"`;
  `evidence_refs` ≥ 2 entries; projection terminal; drain continued (a second, healthy
  job completes after the poisoned one).
- **F2 (the overwrite guard — GREEN on main, vacuously):** a fake coordinator whose
  `start_run` finalizes a real record then raises `KeyboardInterrupt` (the `_finish_run`
  pending re-raise shape) → the poison branch fires and the ORIGINAL record survives
  byte-for-byte (outcome unchanged, no `run_worker poison` reason present).
- **F3 (the #507 boundary — GREEN on main, must stay green):** the doc/echo-disagreement
  containment fixture (the `test_recovery_sweep_faults.py:383` shape) posted through a
  poison → NO record, projection terminal, wire `outcome_unknown`, the unresolved log
  fired.
- **F4 (A07 — GREEN on main, must stay green):** `finalize_run` monkeypatched to raise →
  projection still closes terminal, drain continues, `run_worker poison record failed`
  logged, nothing raises out of the handler.

**Fluff controls (each neutralization must redden its row):** delete the
`finalize_poisoned_run` call → F1 reddens. Delete the `terminal is not None` early
return → F2 reddens. Flatten `decision` (always write, ignore containment) → F3
reddens. Forcing the poison path in tests never depends on a real race: F1-F3 inject the
raise at the fake seam; no timing, no load.

**One deliberate pin update, named in advance:** `tests/control/test_unattended_grant.py:695-734`
pins the OLD shape — `assert row is not None and row["terminal"] is None  # no fabricated
record` (`:730`) over a real-factory poison. Post-fix that run is judgeable (real
admitted docs), so the pin updates to: terminal present, `outcome_unknown`, reasons
carrying `qualification_window_exceeded`. The docstring's "NO terminal record" clause is
rewritten with it. This is the only existing assertion in the tree that pins the
no-record shape (checked: `test_record_lane.py:452-511` pins only the 202 posture, no
drain; the drain-faults tests pin projection/liveness only).

## 10. Pre-committed acceptance rule

- **SHIP** iff: F1-F4 all green post-fix; F1 RED on main (collected count ≥ 1, failure at
  the `terminal is not None` assert — the right reason); each fluff control reddens only
  its own row; the one disclosed pin update lands and no other existing test reddens;
  fast triple (bare `uv run ruff check .`, fresh-cache bare `uv run mypy`, focused
  pytest incl. `tests/faults/`) and the cold full battery are green.
- **KILL** if F1 passes on main (the test measures nothing), or F3/F4 redden post-fix
  (the mechanism broke the containment boundary or worker liveness — worse than the
  bug), or any CTL-1/CTL-2/CTL-9 pin reddens beyond the disclosed update, or the
  real-factory cohort cannot gain a record while the synthetic cohort does (the judge
  wiring is wrong somewhere only the real factory reaches).
- **UNDERPOWERED** if F2's pre-record-finalize fake cannot be built without new
  production seams — then the overwrite guard ships unpinned-by-F2, is disclosed as a
  named residual in the PR body, and everything else stands.

## 11. Risks and falsifiers

| Risk | Falsified by |
|---|---|
| The overwrite guard misses a shape where a record lands AFTER the poison handler's `get_run` read (a concurrent writer) | Structurally unreachable at this seam: the worker thread is the only writer of `finalize_run` for a run it owns (CTL-9 one-coordinator ownership), and the poison handler runs on that same thread after `start_run` returned or raised. A demonstration otherwise is a new issue, not a design patch. |
| `outcome_unknown` records read as "gateway uncertainty" by auditors who wanted the stronger never-resumes claim | The reasons list carries the exact mechanism; if an audit workflow needs a distinct outcome value, that is a corpus amendment motion with its own record — not this increment. |
| Judge cost per poison (doc read, corpus classification) slows the drain | Measured once in F1's run (milliseconds against a sqlite read); if a poison storm ever makes it material, the observation belongs to the #513 follow-up, not the mechanism. |
| Access-failure poisons keep the null record forever (the projection closes; recovery skips terminal rows) | Accepted and disclosed (§3): it is today's behavior for every poison run, narrowed to a judge-failure subclass; the log line remains the operator's evidence. The reopen trigger would be a judge-failure poison observed in a real log. |
