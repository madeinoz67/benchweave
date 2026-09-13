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
