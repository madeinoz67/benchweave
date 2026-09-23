"""Fault arms for the startup sweep's run-state-aware leg (issue #156 fix wave).

The refute pass executed two wedges the lease-held sweep cannot see:

- F1 — a queued ghost (an ``accepted`` projection over a durable run row,
  never started, no lease) survives every restart in LIVE_RUN_STATES, so
  the §5 busy oracle (any live row owns the bench,
  ``Operations._assert_bench_acceptable``) refuses every future run_start
  on that bench, forever. Reachable since the shutdown drain bound became
  real: a queued-not-started run is abandoned at the bound and the worker
  never opens it.
- F2 — a stale ``running`` projection over a DURABLE terminal record (the
  worker's contained close failed at ``put_run_state`` after the
  coordinator's ``finalize_run``) wedges the same way: no lease, so the
  lease scan is blind to it.

Both arms seed the split state directly over a real Store and drive the
app-level sweep (``_recover_interrupted_runs``, the lifespan's ONE
recovery entrypoint), mirroring ``tests/faults/test_capture_recovery.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from benchweave.control.coordinator import build_terminal_record
from benchweave.interfaces.app import _recover_interrupted_runs
from benchweave.interfaces.operations import LIVE_RUN_STATES
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
BENCH_ID = "sim-bench"  # the bootstrap bench (fixtures/execution/bench.json)
NOW = "2026-09-23T00:00:00Z"
#: Synthetic closed binding ref — invented names, never a real corpus.
BINDING: dict[str, Any] = {"id": "req-sweep-ghost", "version": "1.0.0", "sha256": "0" * 64}


def _busy(store: Store) -> bool:
    """The busy oracle's own predicate: any live row owns the bench."""
    return any(row["state"] in LIVE_RUN_STATES for row in store.list_run_states(BENCH_ID))


def _states(store: Store) -> list[tuple[str, str]]:
    return [(str(row["run_id"]), str(row["state"])) for row in store.list_run_states(BENCH_ID)]


def _sweep(store: Store) -> list[str]:
    return _recover_interrupted_runs(store, FIXTURES, emit_keep=100, now_iso=lambda: NOW)


def _run_changed(store: Store, run_id: str) -> bool:
    return any(
        event.get("kind") == "run_changed" and event.get("run_id") == run_id
        for event in store.read_events(f"bench.{BENCH_ID}")
    )


# --- F1: the queued ghost --------------------------------------------------------


def test_sweep_records_queued_ghost_interrupted_and_unwedges_bench(
    tmp_path: Path,
) -> None:
    """Accepted projection + durable run row + never started + no lease:
    the sweep must record it ``interrupted`` (the CTL-9 honest record,
    never a fabricated outcome) and clear the busy oracle — the refute
    pass left this row wedged in LIVE_RUN_STATES forever."""
    store = Store.open(tmp_path / "queued-ghost.db")
    try:
        store.create_run("run-q1", BINDING, "p1", NOW)
        store.put_run_state("run-q1", BENCH_ID, "accepted", NOW)
        assert _busy(store) is True  # pre-condition: the wedge is real

        recovered = _sweep(store)

        assert recovered == ["run-q1"], (
            f"sweep missed the queued ghost; recovered={recovered},"
            f" run_states={_states(store)}"
        )
        run = store.get_run("run-q1")
        assert run is not None
        terminal = run["terminal"]
        assert terminal is not None, "the ghost must gain a durable terminal record"
        assert terminal["body_outcome"] == "interrupted"
        assert terminal["safe_state"] == "unknown"
        assert terminal["outcome"] == "interrupted"
        assert _busy(store) is False, (
            f"queued ghost left the bench busy forever; run_states={_states(store)}"
        )
        assert _run_changed(store, "run-q1"), "the recovery state change is on the stream"
        assert _sweep(store) == [], "a second restart must find nothing left to sweep"
    finally:
        store.close()


# --- F2: the stale projection over a durable terminal ----------------------------


def test_sweep_reconciles_stale_running_projection_over_durable_terminal(
    tmp_path: Path,
) -> None:
    """Durable terminal record + stale ``running`` projection + no lease
    (the contained worker close failed at ``put_run_state``): the sweep
    must reconcile the projection to terminal and NEVER interrupt a run
    whose durable record says it completed."""
    record = build_terminal_record(
        run_id="run-q3",
        binding_pin=BINDING,
        principal_id="p1",
        started_at=NOW,
        ended_at=NOW,
        body_outcome="completed",
        safe_state="verified",
        reasons=["synthetic completed run"],
        evidence_refs=[BINDING],
    )
    store = Store.open(tmp_path / "stale-projection.db")
    try:
        store.create_run("run-q3", BINDING, "p1", NOW)
        store.finalize_run("run-q3", record)
        store.put_run_state("run-q3", BENCH_ID, "running", NOW)
        assert _busy(store) is True

        recovered = _sweep(store)

        assert recovered == ["run-q3"], (
            f"sweep left the stale projection untouched; recovered={recovered},"
            f" run_states={_states(store)}"
        )
        run = store.get_run("run-q3")
        assert run is not None
        assert run["terminal"] == record, "the durable record is the truth — untouched"
        row = store.get_run_state("run-q3")
        assert row is not None and row["state"] == "terminal"
        assert _busy(store) is False, (
            f"stale projection left the bench busy forever; run_states={_states(store)}"
        )
        assert _run_changed(store, "run-q3"), "the reconciled state change is on the stream"
        assert _sweep(store) == [], "a second restart must find nothing left to sweep"
    finally:
        store.close()


# --- order/edge probe: durable terminal + active lease + live projection ---------


def test_sweep_probe_terminal_with_stale_lease_and_live_projection(
    tmp_path: Path,
) -> None:
    """Order/edge probe (fix-wave instruction): a durable terminal record
    with an ACTIVE ``run:`` lease and a live projection. CTL-9's ordering
    (finalize_run → lease release → projection close) makes the window
    narrow, not impossible — a crash between ``finalize_run`` and the
    coordinator's lease release lands exactly here. Documented behavior of
    the composed sweep: the lease leg releases the stale lease without
    interrupting (the durable record already ends the run), then the
    run-state leg reconciles the projection — the bench un-wedges either
    way, and the completed record is never rewritten."""
    record = build_terminal_record(
        run_id="run-q4",
        binding_pin=BINDING,
        principal_id="p1",
        started_at=NOW,
        ended_at=NOW,
        body_outcome="completed",
        safe_state="verified",
        reasons=["synthetic completed run"],
        evidence_refs=[BINDING],
    )
    store = Store.open(tmp_path / "terminal-stale-lease.db")
    try:
        store.create_run("run-q4", BINDING, "p1", NOW)
        store.finalize_run("run-q4", record)
        store.put_run_state("run-q4", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-stale", holder="run:run-q4", expires_at="2030-01-01T00:00:00Z"
        )
        assert _busy(store) is True

        recovered = _sweep(store)

        assert recovered == ["run-q4"], (
            f"composed sweep left the wedge; recovered={recovered},"
            f" run_states={_states(store)}"
        )
        run = store.get_run("run-q4")
        assert run is not None
        assert run["terminal"] == record, "a terminal run is never re-finalised"
        assert store.get_active_lease(BENCH_ID) is None, "the stale lease is released"
        row = store.get_run_state("run-q4")
        assert row is not None and row["state"] == "terminal"
        assert _busy(store) is False
        assert _sweep(store) == []
    finally:
        store.close()
