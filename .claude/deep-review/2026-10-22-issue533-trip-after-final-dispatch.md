# Issue #533 — trip after the final dispatch: the completed body with an observed violation

- **Tracker:** madeinoz67/benchweave#533 (this repo's single issue stream; no SDK-side
  issue exists by design — gateway-only diff).
- **Branch:** `fix/trip-after-final-dispatch` (worktree `.wt/ap-trip-5n8c`), cut from
  `origin/main` at `4b5b2646`; the designer's cites were verified at `aa8cd5ca` and
  `git diff --stat aa8cd5ca..4b5b2646 -- src/benchweave/control/ tests/faults/
  docs/internal/invariants.md standards/` is empty (0 files), so every cite below holds
  against this branch's bytes.
- **Date:** 2026-10-22. This record lands as the arc's FIRST commit, before any test or
  measurement in this increment has run.
- **Evidence basis:** every file:line cite below was read this session against THIS
  worktree's bytes. The gortex daemon served `coordinator.py` but returned no
  `freshness`/`actual_view` object, so view identity is established by content identity
  (served bytes == worktree disk bytes, 67845, exact string equality) plus the empty
  base-to-tip diff above; edits route natively under the CLAUDE.md edit-routing table's
  worktree row (no freshness object ⇒ the gortex edit is not granted; the bypass names
  this caveat).
- **Tier (design-time call, #254):** Tier 3 — the diff text contains `protection`
  (review-rubric Step 1's keyword list). The record's expected-diff keyword scan:
  `protection` ≥ 8 (test file path `tests/faults/test_protection.py`, module docstring,
  `_body_truth` docstring, design-record prose), `recovery` 0, `threading` 0,
  `asyncio` 0, `subprocess` 0, `sha256` 0, `hashlib` 0, `migrate` 0. No Tier-3 file-set
  rule triggers (no `standards/` edit, no schema edit, no `state/` or `documents.py`
  edit, no fixture lattice, no dependency, no SDK pointer). The review re-derives the
  tier independently; the scan is re-run on the actual diff at report time.

## 1. Verified finding (truth-table defect, protection not compromised)

The chain, verified at source in this worktree:

- `blocked=True` is set at exactly one site — `block_result`,
  `coordinator.py:682` — reachable only from `_MonitoringPlugin.dispatch`'s
  pre-dispatch arm (`coordinator.py:718`).
- `tick` (`coordinator.py:648-649`) sets `cause="tripped"` for a fresh violation in
  body phase WITHOUT the latch. The first observer of a violation armed during the
  final dispatched action is that action's post-dispatch tick (`coordinator.py:722`)
  or the post-body tick (`coordinator.py:1304`) — no next dispatch exists to refuse,
  so `blocked` never becomes true.
- `_body_truth` (`coordinator.py:1418`) requires `blocked and cause`, so the
  fall-through (`coordinator.py:1422-1425`) appends the trip as a bare reason over the
  executor's own body outcome.
- `terminal_outcome` (`coordinator.py:130-134`) with
  `_OUTCOME_BY_BODY["completed"]="passed"` (`coordinator.py:111`, the sole "passed"
  row) yields outcome **`passed`** with the measured violation sitting in the reasons
  list.
- `_finish_run` (`coordinator.py:1339,1352-1353`) still feeds the trip into
  `engine.enter` (`enter_reasons = body_reasons if monitor.cause is not None else []`),
  so the protective transition is NOT compromised — the defect is truth-table only.
- CTL-8's rider already convicts the record (`docs/internal/invariants.md:87-88`:
  "A violation must never be observed and then worked around; it ends the body").

The run-record schema in BOTH vendored execution versions sanctions the fixed cell
(`body_outcome` "tripped" → `outcome` ∈ {tripped, outcome_unknown}; verified by reading
`standards/execution/0.1.0/run-record.schema.json` and `0.2.0/…` allOf rows this
session; the active family resolves to 0.2.0), and the execution contract's §5 table
("Protection trip | tripped") makes `passed` conditional on the continuous condition
having held — the fix aligns the code with the vendored contract; no schema, corpus or
manifest motion.

## 2. Mechanism — one widened condition in `_body_truth`

Replace

```python
if monitor.blocked and monitor.cause == "tripped":
    return "tripped", list(monitor.cause_reasons)
```

with

```python
if monitor.cause == "tripped" and (
    monitor.blocked or body.body_outcome == "completed"
):
    reasons = list(monitor.cause_reasons)
    for reason in body.reasons:
        if reason not in reasons:
            reasons.append(reason)
    return "tripped", reasons
```

Why sound: `cause=="tripped"` is set only in body phase (`coordinator.py:648-649`
guards on `self.phase == "body"`), so it always denotes a violation observed during
the body; `completed` is the ONLY body outcome mapping to `passed` (`:111` is the sole
"passed" row). The cancel branch (`:1420`) and the never-downgrade fall-through
(`:1422-1425`) are unchanged.

**Vocabulary:** the record carries `body_outcome` "tripped" and `outcome` "tripped" —
NOT `outcome_unknown`. This is a measured violation with a completed body, not an
ambiguity.

## 3. Files — exactly three production/test/doc files

1. `src/benchweave/control/coordinator.py` — the `_body_truth` edit, one sentence in
   the module docstring (the `:13-17` block sentence, which says the violation "blocks
   the next dispatch"), the module docstring's terminal-truth sentence (`:24-27`,
   which says a cause replaces the body outcome "only when its block terminated the
   body" — it drifts otherwise), and `_body_truth`'s own docstring (`:1407-1417`,
   which says reclassification exists for "exactly one case").
2. `tests/faults/test_protection.py` — one new test beside the never-reclassify pair
   (`:884-:924`).
3. `docs/internal/invariants.md` — a CTL-8 amendment appended after `:88`, dated, in
   the same form as the existing amendments at `:97` and `:105`, reading: "the block
   is the mechanism, not the definition — a violation observed during the body ends
   the body `tripped` whatever the dispatch ordering. When no next dispatch exists to
   refuse (the violation is first observed by the final action's post-dispatch tick,
   coordinator.py:722, or the post-body tick, coordinator.py:1304), the coordinator's
   body truth takes `tripped` over the executor's `completed`: an observed
   continuous-condition violation can never produce a `passed` record. Uncertain,
   failed, timed-out and cancelled bodies are untouched — the cause stays an appended
   reason, never a reclassification. Pinned by tests/faults/test_protection.py."

Nothing else: no schema, no SDK pointer, no fixtures, no CI workflow.

## 4. Substrate — the named arm and a pre-committed contingency

The designed substrate is the existing `_harness` (`test_protection.py:428`) with
TestClock and the fault PSU; `fault.trip_after_measure = True` (declared `:178`,
effect `:330`); the measure assertion untampered.

**Static-analysis prediction, read-verified before any measurement:** the plain
`trip_after_measure` arm CANNOT decide the cell with this procedure. The fixture
procedure (`fixtures/execution/procedure-voltage-check.json`) runs a `repeat` loop of
three `remeasure` invokes after the first `measure`; arming the forced 5.9 V on the
FIRST measure means the first remeasure's pre-dispatch tick (`coordinator.py:717-718`)
latches the block (`block_result` returns DEVICE_REJECTED/NOT_DISPATCHED), and the
executor's `_dispatch` terminates the body `execution_error` on exactly that shape
(`executor.py:1238-1254`) — which `_body_truth`'s existing blocked branch already
reclassifies to `tripped`, pre-fix AND post-fix alike. The `sample`/`assert` steps
between never dispatch through the plugin (`executor.py:905-919`: only
invoke/read/write/capture dispatch), so no observation point sits between the first
measure and the blocked remeasure. The neighbour
`test_assertion_failed_body_is_never_reclassified_to_tripped` (`:905-:924`) reaches a
non-blocking cause only because its tampered assertion ends the body at `check`,
before the loop.

**Pre-committed contingency (this record, before measurement):** if the RED control
confirms the prediction — the plain substrate produces outcome `tripped` WITHOUT the
fix — the substrate arms the SAME forced 5.9 V on the body's fourth and final measure
invoke (the loop's third remeasure; 1 + 3 = 4 PSU_MEASURE body dispatches in the
happy path, `test_protection.py:854-856`'s 21-event body) through the fault PSU's
existing `on_invoke` seam (`:179`, `:314-315` — the `:860` test's own pattern). The
fault class, the violating value and the observed cell are unchanged; only the arming
order moves to the final dispatch, which is exactly the ordering the defect lives in.
Both runs (plain and contingency) are reported; the acceptance's KILL clause names
"underpowered — fix the fixture" as the sanctioned response.

## 5. Pre-committed acceptance rule

SHIP iff ALL of:

- (a) the new test asserts `body_outcome=="tripped"` AND `outcome=="tripped"` AND a
  reason naming the violated condition AND the safe transition dispatched AND the
  record validates;
- (b) RED control — revert ONLY the `_body_truth` edit (a `cp` backup), keep the test:
  it must FAIL showing outcome `passed`, and that failure is pasted;
- (c) restore: GREEN pasted;
- (d) the neighbouring pins stay green (`:452` trip-mid-body, `:884` uncertain
  never-reclassified, `:905` assertion-failed never-reclassified);
- (e) fast lane and full battery green before push.

KILL iff: the RED control stays green without the fix on BOTH substrates (the
contingency arm included — then the measurement cannot decide and the fix does not
ship on it); any (d) pin breaks (rule too broad — narrow to exactly
blocked-or-completed or abandon); or the reclassified record fails validation or the
schema in either execution version.

UNDERPOWERED, distinct from KILL: the RED control records the same outcome with and
without the fix — then the measurement cannot decide and we do not ship on it (the
§4 contingency is the designed escape, and it is itself under this rule).

NOT MEASURABLE here: real trip-onset timing on hardware. No hardware claim is made.

## 6. Gates

FAST lane every commit — bare `uv run ruff check .`, fresh-cache bare `uv run mypy`,
focused pytest plus `tests/faults/` (mandatory: `control/` is touched); full battery
ONCE before push. TRUE exit codes; junitxml counts, never a summary line. One
RED→GREEN slice per commit, the RED evidence in the commit message.

## 7. Deferrals

None. (Real trip-onset timing on hardware is out of scope by the NOT-MEASURABLE rule,
not deferred work.)

## Addendum (2026-10-22, post-measurement — the §1–§7 text above is frozen as authored)

The §4 prediction was CONFIRMED by measurement, and the contingency ran. Attribution of
every number to its substrate — the record never implies the plain arm decided anything:

- **Plain `trip_after_measure` arm (predicted underpowered — measured GREEN pre-fix):**
  `test_trip_after_final_dispatch_still_ends_body_tripped` with the plain arm, pre-fix,
  PASSED (exit 0, junit tests=1 failures=0). The first remeasure's pre-dispatch tick
  latched the block and the body ended `tripped` the classic way, fix or no fix — the
  arm measures the blocked cell, not the completed-body cell.
- **Contingency arm (the deciding substrate — armed on the 4th/final measure invoke via
  `on_invoke`):** pre-fix RED — `assert record["outcome"] == "tripped"` /
  `AssertionError: assert 'passed' == 'tripped'` (exit 1, junit tests=1 failures=1);
  pre-fix portrait probe: `outcome: passed`, `body_outcome: completed`,
  `safe_state: verified`, `reasons: ['dut-voltage-bounds: interval_escape: [5.85, 5.95]
  escapes [-0.1, 5.5]']`, schema-valid. Post-fix GREEN: exit 0, junit tests=1
  failures=0. RED control (revert ONLY the `_body_truth` condition, `cp` backup,
  docstrings kept): the same `assert 'passed' == 'tripped'` failure (exit 1, junit
  tests=1 failures=1) — the test discriminates the mechanism, not the fixture.
- **Neighbour pins (all green on the post-fix tree, focused `tests/control/` +
  `tests/faults/` 347/0/0):** `:452` trip-mid-body, `:884` uncertain never-reclassified,
  `:905` assertion-failed never-reclassified, `:860` no-false-passed (its violation is
  observed in protection phase, so no cause is ever set — untouched by the widened
  condition).
- **Gates:** ruff exit 0 and fresh-cache bare mypy exit 0 (447 files) on both commits;
  full battery third run exit 0, junit 4501/0/0/11 skipped (run 1 red on the
  win-core-manifest ratchet — `tests/faults/test_protection.py` 38→39 moved by the
  ratchet's own `--refresh`, one visible row, recorded as the brief's fourth file;
  run 2 red only on the disclosed #532 demo-lattice under-load flake — serially green
  1/0/0 on this tree, failure mode `outcome_unknown`, not this change); sdk-drift exit
  0, `make check-sdk-standards` exit 0.
- **Keyword scan on the actual diff (re-run as the brief requires):** `protection` 2
  added lines (the CTL-8 amendment's pin line and the test file's diff header; 7 over
  the whole diff text), all of `threading`/`asyncio`/`subprocess`/`sha256`/`hashlib`/
  `migrate`/`recovery` 0 on added lines. Tier 3 by the `protection` keyword, as
  designed.

## Fold addendum (2026-10-22, the refute lanes' rows — one wave, per-row RED)

**F1 (lane A, MEDIUM — accepted, fixed):** the shipped universal ("an observed
continuous-condition violation can never produce a ``passed`` record") was FALSE.
Composite, previously undisclosed: a principal cancel and the violation arm together
on the body's final dispatch — the post-dispatch tick honours the cancel BEFORE the
signals (`_check_body_phase` runs first) and `_set_cause` is first-wins
(`coordinator.py`, `if self.cause is None:`), so `cancelled` owns the cause, the trip
never latches, no next dispatch exists to refuse, and the record read `outcome:
passed` with the violation ABSENT FROM REASONS ENTIRELY (probe, pre-fold: reasons =
`['cancelled by principal for run run-x']` only) — worse than the defect this issue
convicted. Fold: `_body_truth`'s fall-through now appends `monitor.violations` when
the cause is not `tripped` (outranked is not absent); the outcome is untouched —
a cancel is principal intent, and the composite's mapping stays the cancel window's
own (`passed`). RED (pre-fold): `assert False` on the violation-missing `any`
(`tests/faults/test_protection.py:996`, junit 3/2/0); GREEN post-fold: exit 0, the
record carries `['cancelled by principal for run run-x',
'dut-voltage-bounds: interval_escape: [5.85, 5.95] escapes [-0.1, 5.5]']`. The
universal is narrowed in the module docstring, `_body_truth`'s docstring, and the
CTL-8 amendment.

**F2 (lane B, LOW — accepted, deduped):** commit `6181e820`'s reasons merge regressed
the classic blocked-trip cell — the executor's blocking-proxy reason repeats the
violation verbatim, so the record carried it twice (probe: 2 reasons). Fold: the
merge runs only on the completed arm (`if not monitor.blocked:`), so the blocked
cell's record is byte-identical to its pre-#533 shape (probe: 1 reason). RED
(pre-fold): `assert 2 == 1` on the tightened exactly-once pin in
`test_condition_violation_trips_and_safe_transition_verifies` (`:465`); GREEN
post-fold: exit 0.

**F3 (lane B, MINOR — accepted):** the amendment's `coordinator.py:722`/`:1304` cites
were six lines stale (the own docstring growth moved them). Re-pointed BY NAME
(`_MonitoringPlugin.dispatch`'s post-dispatch arm; the post-body tick in
`_run_and_record`) so they cannot drift again.

**F4 (lane B, MINOR — accepted):** the amendment now carries the narrowed bound with
its mechanism inline (cancel-before-signals + first-wins) plus the `completed`-is-the-
only-passed-producer clause, pinned by
`test_passed_is_reachable_from_exactly_one_body_outcome` — the body-outcome set is
derived from the vendored run-record schema's enum, not hand-copied, so a second
passed-producing row reddens instead of silently falsifying the sentence.

Manifest: `tests/win_core_manifest.json` 39→41 (the ratchet's own `--refresh`, two
new tests). Gates: ruff 0, fresh-cache bare mypy 0 (447 files), focused
`tests/control/` + `tests/faults/` 349/0/0 exit 0; full battery recorded in the
fold commit's message.
