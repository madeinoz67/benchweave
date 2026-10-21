# Issue #507 — Recovery containment unwedge: close the contained run's projection

Tracker: madeinoz67/benchweave#507 (single issue stream; gateway-only diff)

## The finding (verified in this worktree at 05958386; the brief's line
numbers were pinned at b905b19a and shift by a few lines — same code)

A run the startup sweep CONTAINS (issue #260's narrowed class: doc/echo
disagreement, an unjudgeable doc const, an echo the corpus disowns, an
unrowed run-record schema) is left with a live queue-state row forever:

- Both live containment legs log-and-continue with no record and no
  report: the lease leg (coordinator.py:860-869) and the run-state/ghost
  leg (coordinator.py:946-957). The stop-sweep leg does the same
  (coordinator.py:1072-1078). Per-run terminalization failures are also
  log-only (coordinator.py:910-915, 999-1004, 1113-1118).
- The interface's recovery loop closes projections only for ids in
  `recovered` (app.py:354-380: `put_run_state(..., "terminal")` inside
  `for run_id in recovered`). Contained ids are excluded from
  `recovered`, so their `running`/`accepted` row never closes.
- The §5 busy oracle reads exactly `LIVE_RUN_STATES = {accepted,
  running, protecting}` (operations.py:83) and refuses run_start
  (operations.py:2268-2275) and lease_create (operations.py:1115-1123)
  with `conflict: bench busy with run` while any live row exists. The
  same stale row also blocks config activation (`_live_lease`,
  operations.py:2009), the stop window's live read
  (supervision.py:366-384), and the CLI busy surfaces.
- Nothing else clears the row: `_stop_time_sweep` finalizes `accepted`
  ghosts only and its containment branch also skips
  (supervision.py:847-889 + coordinator.py:1062-1078); the containment
  decision is deterministic per boot over durable bytes, so every
  restart re-contains and the wedge never self-heals.

Blast radius is therefore larger than "the run stays non-terminal": the
bench is unbookable (runs, leases, config activation) until an operator
hand-edits the store. The pinning fault tests assert `recovered == []`
and `terminal is None` (tests/faults/test_recovery_sweep_faults.py:421-424,
583-586) — neither pins bench-busy, which is exactly the gap that let
this ship.

## The mechanism — two in-tree precedents, no new architecture

1. **Precedent A — the #156 projection-ownership split.**
   `recover_interrupted`'s docstring already rules that reported ids
   "get their projection closed by the interface's recovery loop, which
   owns the queue projection" (coordinator.py:825-843). Extend the same
   split to contained ids: `recover_interrupted` returns
   `RecoverySweep(recovered, contained)` (a frozen dataclass beside
   `_RecoveryDecision`); both live containment legs append to
   `contained`; the ghost leg skips ids already in `contained`, which
   also dedupes today's double ERROR log (one boot currently logs the
   same lease-held contained run at coordinator.py:865-869 and again at
   :952-956).
2. **Precedent B — the contract's terminal-evidence-gap vocabulary.**
   interface-contract.md §6: "A storage failure may leave
   terminal_record null only for outcome_unknown or interrupted. That
   null explicitly means final evidence is missing... recovery reports
   interruption/unknown rather than inventing a prior record."
   `_run_projection` already renders state=terminal + record=None as
   outcome `outcome_unknown` / safe_state `unknown` /
   terminal_record `null` (operations.py:1970-1977). The app-level
   recovery loop closes each contained id's projection `terminal` with
   a new `RECOVERY_CONTAINED_REASON` run_changed — the same loop idiom
   as app.py:354-380. The durable record stays absent.
3. **This is not the laundering the ghost-leg comment rejects**
   (coordinator.py:946-953). Laundering is a DURABLE record without
   evidence. Projection-terminal-with-null-record is the contract's
   sanctioned uncertainty shape: the wire says "over, evidence
   missing" (`outcome_unknown`), never `interrupted`/`passed`, and the
   containment ERROR log remains the operator's evidence. The comment
   is rewritten to draw exactly that line.

## Scope

- `coordinator.py`: `RecoverySweep` return shape; contained collection
  in BOTH live legs (lease leg + ghost leg); ghost-leg skip of
  already-contained ids (log dedup); docstring + ghost-leg comment
  updates.
- `app.py`: `RECOVERY_CONTAINED_REASON` constant (beside
  `RECOVERY_RUN_CHANGED_REASON` / `RECOVERY_PROJECTION_REASON`); the
  contained-close loop after the recovered loop. The app-level
  `_recover_interrupted_runs` keeps returning `list[str]` (recovered)
  — its callers discard or assert on recovered only.
- `tests/faults/test_recovery_sweep_faults.py`: both containment
  fixtures gain the busy metric, projection-terminal, wire-shape,
  stream, and idempotency asserts; the unrowed fixture moves to the
  app-level sweep (a corpus-parameterised `_era_sweep` shape) so the
  busy oracle is measured through the real entrypoint.
- `tests/unit/test_run_projection.py`: the wire pin — terminal state
  row + no durable record renders outcome_unknown/unknown/null.
- `tests/faults/test_protection.py:823/840` and the
  `tests/unit/test_seam_control.py:118` stub: return-shape callers
  updated.
- `docs/internal/invariants.md`: append-only amendment to the
  containment block (invariants.md:366-391).
- Drift obligations 3 and 4: `docs/device-developer-guide.md` and
  `docs/operator-guide.md` rows.

NOT in scope: `standards/` (no wire value changes — the shape already
exists in the frozen contract), `state/store.py`, the SDK submodule,
`openapi.json`, `mcp-tools.json`, no new CI lane.

## Pre-committed acceptance (prove it, do not fluff it)

- Substrate: `tests/faults/test_recovery_sweep_faults.py` through the
  app-level `_recover_interrupted_runs` (the `_era_sweep` shape,
  :241-245); fixtures = both in-tree containment classes (:383
  doc/echo disagreement, :527 unrowed schema). Metric: post-sweep busy
  rate via `_busy` (:49-51).
- SHIP iff: after the fix, 0/2 fixtures busy; `run["terminal"] is
  None` on both; the wire projection reads state `terminal` / outcome
  `outcome_unknown` / terminal_record `None`; the UNSOLVED log
  (`recovery_execution_version_unresolved:`) fired; a second sweep is
  idempotent (still 0 busy, still no record).
- KILL if any fixture is still busy, or any fixture gains a durable
  record or a wire outcome other than `outcome_unknown` (that would be
  laundering — worse than the bug).
- UNDERPOWERED if the RED run does not show busy=True on ALL fixtures
  — those fixtures cannot measure the fix and must be replaced, not
  shipped around.
- RED check: with the fix reverted (only the contained-projection-close
  removed), the `_busy` asserts must redden. Fluff control: flattening
  `decision.containment` to None (terminalize everything) must redden
  the `terminal is None` asserts.
- The actual before/after numbers go in the commit message.

## Deferrals

| Row | Deferred | Home | Reopen trigger |
|---|---|---|---|
| a | The stop-sweep containment leg (coordinator.py:1072-1078) — a contained queued run at stop time keeps its `accepted` row until next boot, when the ghost leg contains it and the projection closes | This record, row a | A stop-to-start window where an operator must book the bench before the next boot completes |
| b | Terminalization-failure runs (the per-run excepts) stay non-terminal and unreported — the store-failure world, where A06/A07 forbid inventing the projection close without knowing the record never landed | This record, row b | A store-recovery path that can distinguish "finalize refused" from "finalize outcome unknown" |
| c | The re-judgment door after corpus repair: the ghost leg's `state=="terminal"` skip (coordinator.py:933) means a corpus fix cannot retro-terminalize a contained run | This record, row c | An operator workflow demand to convert outcome_unknown containment into a judged record |
| d | Durable surfacing of the containment reason beyond the run_changed reason + the ERROR log line (e.g. a queryable containment table) | This record, row d | A second incident where the log line was not enough to route the repair |

## Invariant amendment (append-only, lands with the code)

Into the containment block at invariants.md:366-391, appended after the
existing fold clarification: a contained run's queue projection closes
`terminal` with NO durable record at the next recovery sweep; the wire
reads `outcome_unknown`/`unknown`/`terminal_record: null` per the
frozen interface contract's terminal-evidence-gap clause; the §5 busy
oracle releases; CTL-9 is untouched (no terminal record is written, so
no outcome is invented — the projection is the queue's view, not a
record). The containment log line stays the operator's evidence.
