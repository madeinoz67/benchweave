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

import pytest

from benchweave.control.coordinator import build_terminal_record
from benchweave.interfaces.app import _recover_interrupted_runs
from benchweave.interfaces.operations import LIVE_RUN_STATES
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
BENCH_ID = "sim-bench"  # the bootstrap bench (fixtures/execution/bench.json)
NOW = "2026-09-23T00:00:00Z"
#: Synthetic closed binding ref — invented names, never a real corpus. The
#: version agrees with the composition the sweep admits through (the sweep
#: mechanics arms below pin discovery/terminalisation/projection-close, not
#: version agreement; DISAGREEMENT is its own pinned behavior — the era
#: cohort arms at the bottom, issue #220 fold).
BINDING: dict[str, Any] = {"id": "req-sweep-ghost", "version": "0.2.0", "sha256": "0" * 64}


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


# --- the era cohort: a stored run older than the composition (issue #220 fold) ---

#: The pre-promotion cohort (execution 0.1.0 ran on this store before 54a59fa
#: promoted 0.2.0): an upgrade brings the OLD lattice in fixtures and the NEW
#: gateway. The stored binding's version is the era's fact — recovery must
#: neither rewrite it into the active record dialect (laundering) nor crash.
ERA_BINDING: dict[str, Any] = {"id": "req-era-1", "version": "0.1.0", "sha256": "0" * 64}
LATTICE_010 = ROOT / "tests" / "fixtures" / "lattice-execution-0.1.0"

#: The typed containment reason (the poison-path log channel).
SKIP_LOG = "recovery_execution_version_not_runnable"


def _era_sweep(store: Store) -> list[str]:
    """The sweep over the 0.1.0 lattice — the upgrade path's own posture
    (post-slice the lattice ADMITS at startup; recovery is the remaining
    record-writer)."""
    return _recover_interrupted_runs(store, LATTICE_010, emit_keep=100, now_iso=lambda: NOW)


def test_era_lease_held_run_is_skipped_not_laundered(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Fold row 1: a store holding a non-terminal 0.1.0-era run (binding
    version 0.1.0, an active run: lease) recovers against the 0.1.0 lattice
    — terminalising it would persist binding.version 0.1.0 beside the
    record lane's literal contract_version 0.2.0, the internally
    contradictory evidence record (F3's KILL condition, on an ordinary
    upgrade path). The honest wedge: NO terminal record, the run stays
    non-terminal, the typed reason is logged, the lease is released."""
    import logging

    store = Store.open(tmp_path / "era-lease.db")
    try:
        store.create_run("run-era-1", ERA_BINDING, "p1", NOW)
        store.put_run_state("run-era-1", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-era-1", holder="run:run-era-1", expires_at=NOW
        )
        with caplog.at_level(logging.ERROR, logger="benchweave.control.coordinator"):
            recovered = _era_sweep(store)
        assert recovered == [], (
            f"an era run must not be reported for projection close; "
            f"recovered={recovered}"
        )
        run = store.get_run("run-era-1")
        assert run is not None
        assert run["terminal"] is None, (
            "no terminal record may be persisted for an era run — the "
            "record dialect disagrees with the run's own binding"
        )
        assert any(
            SKIP_LOG in record.message and "run-era-1" in record.message
            for record in caplog.records
        ), f"the typed containment reason must be logged: {[r.message for r in caplog.records]}"
    finally:
        store.close()


def test_era_ghost_run_is_skipped_not_laundered(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Fold row 1, second leg: the same era cohort through the run-state
    leg (no lease — the queued-ghost shape). Same honest wedge: the run is
    neither terminalised nor reported for projection close, and the typed
    reason is logged — idempotently, every restart, until the lattice is
    upgraded or E1 threads the record lane."""
    import logging

    store = Store.open(tmp_path / "era-ghost.db")
    try:
        store.create_run("run-era-2", ERA_BINDING, "p1", NOW)
        store.put_run_state("run-era-2", BENCH_ID, "accepted", NOW)
        with caplog.at_level(logging.ERROR, logger="benchweave.control.coordinator"):
            recovered = _era_sweep(store)
        assert recovered == [], f"recovered={recovered}"
        run = store.get_run("run-era-2")
        assert run is not None
        assert run["terminal"] is None
        assert _busy(store) is True, (
            "the honest wedge stays visible: the non-terminal row keeps the "
            "bench busy (E1's lifter), never silently cleared"
        )
        assert any(
            SKIP_LOG in record.message for record in caplog.records
        ), f"the typed containment reason must be logged: {[r.message for r in caplog.records]}"
        # Idempotent: a second restart skips again, never crashes.
        assert _era_sweep(store) == []
    finally:
        store.close()


def test_caller_data_ref_version_terminalizes_as_before(tmp_path: Path) -> None:
    """Fold row 1's boundary, the other side: the stored binding version is
    the §5 ref's caller-supplied echo (D4 — the frozen contract types it as
    any non-empty string), so it is JUDGED, never trusted. A version the
    corpus never carried as a served dialect ("1.0.0" is RETIRED — no
    gateway ever ran it) is caller data, not an era fact: the sweep
    terminalises exactly as before the fold, and the record's
    contract_version literal beside it faithfully records the ref. (The
    real-path twin: the child-process kill-mid-run suite posts exactly such
    a ref and must keep recovering.)"""
    store = Store.open(tmp_path / "caller-data.db")
    try:
        store.create_run("run-cd-1", BINDING, "p1", NOW)
        store.put_run_state("run-cd-1", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-cd-1", holder="run:run-cd-1", expires_at=NOW
        )
        recovered = _sweep(store)
        assert recovered == ["run-cd-1"], f"recovered={recovered}"
        run = store.get_run("run-cd-1")
        assert run is not None
        assert run["terminal"] is not None, (
            "a caller-data version is not an era fact — the honest "
            "interrupted record still lands"
        )
        assert run["terminal"]["binding"]["version"] == BINDING["version"]
        assert run["terminal"]["contract_version"] == "0.2.0"
    finally:
        store.close()
