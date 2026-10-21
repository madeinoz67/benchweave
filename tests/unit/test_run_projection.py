"""Run projections must not invent uncertainty while a worker completes."""

from pathlib import Path
from typing import Any

import pytest

from benchweave.interfaces.operations import Operations
from benchweave.state.store import Store


@pytest.mark.parametrize("completion_after", ["get_run", "get_run_state"])
def test_completion_between_projection_reads_keeps_terminal_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, completion_after: str
) -> None:
    """Publish the record then queue state between the reader's two queries."""
    reader = Store.open(tmp_path / "state.db")
    writer = Store.open(tmp_path / "state.db")
    run_id = "run-concurrent-completion"
    now = "2026-09-13T00:00:00Z"
    record = {
        "run_id": run_id,
        "contract_version": "1.0.0",
        "outcome": "passed",
        "safe_state": "verified",
    }
    try:
        writer.create_run(
            run_id,
            binding={"id": "binding", "version": "1.0.0", "sha256": "a" * 64},
            principal_id="operator",
            now=now,
        )
        writer.put_run_state(run_id, "bench", "running", now)
        original = getattr(Store, completion_after)
        completed = False

        def read_then_complete(store: Store, requested_run: str) -> Any:
            nonlocal completed
            snapshot = original(store, requested_run)
            if store is reader and not completed:
                completed = True
                writer.finalize_run(run_id, record)
                writer.put_run_state(run_id, "bench", "terminal", now)
            return snapshot

        monkeypatch.setattr(Store, completion_after, read_then_complete)
        operations = Operations.__new__(Operations)
        operations._store = reader
        projection = operations._run_projection(run_id)
        assert completed
        if projection["state"] == "terminal":
            assert projection["outcome"] == "passed", projection
            assert projection["safe_state"] == "verified"
            assert projection["terminal_record"] is not None
        else:
            assert projection["state"] == "running"
            assert projection["outcome"] is None
            assert projection["terminal_record"] is None
        final = operations._run_projection(run_id)
        assert final["state"] == "terminal"
        assert final["outcome"] == "passed"
        assert final["terminal_record"] is not None
    finally:
        writer.close()
        reader.close()


def test_terminal_projection_without_a_record_is_outcome_unknown(
    tmp_path: Path,
) -> None:
    """Issue #507 pin: a contained run's closed projection (terminal queue
    row, NO durable record — the frozen contract's terminal-evidence-gap
    shape, interface-contract §6) reads outcome_unknown/unknown/null on
    the wire, never a fabricated outcome. The recovery sweep's contained
    close (app.py) lands exactly this store shape; this pin holds the
    projection side of the bargain."""
    store = Store.open(tmp_path / "state.db")
    try:
        now = "2026-10-21T00:00:00Z"
        store.create_run(
            "run-contained",
            binding={"id": "binding", "version": "1.0.0", "sha256": "a" * 64},
            principal_id="operator",
            now=now,
        )
        store.put_run_state("run-contained", "bench", "terminal", now)
        operations = Operations.__new__(Operations)
        operations._store = store
        projection = operations._run_projection("run-contained")
        assert projection["state"] == "terminal", projection
        assert projection["outcome"] == "outcome_unknown", projection
        assert projection["safe_state"] == "unknown", projection
        assert projection["terminal_record"] is None, projection
    finally:
        store.close()
