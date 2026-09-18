"""Issue #48: outcome-mismatch failures must be self-describing.

The intermittent ubuntu CI failure (run 35328823772) landed two runs
``terminal``/``execution_error`` whose asserts truncated the run record to
``{...}`` — nothing in the log said WHAT errored. These tests pin the
diagnostic helpers the integration suites now attach to their outcome
asserts (``tests/integration/_failure_detail.py``): a pure formatter over
the terminal record's reasons and the run's error events, and an at-rest
sqlite dump for the subprocess-driven suites that hold no in-process
store handle. The next CI occurrence must report its own root cause.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from _failure_detail import dump_at_rest_runs, format_run_failure

_TERMINAL = {
    "run_id": "run-b2c0e3a03f724215",
    "body_outcome": "execution_error",
    "safe_state": "verified",
    "reasons": [
        "step measure: ValueError('simulated boom')",
        "protection: no violations",
    ],
}

_EVENTS = [
    {
        "occurrence": 1,
        "kind": "step",
        "operation_id": "otdp.dc_psu.measure/1.0.0",
        "status": "ok",
    },
    {
        "occurrence": 2,
        "kind": "step",
        "operation_id": "otdp.dc_psu.measure/1.0.0",
        "status": "unknown",
        "error_code": "TRANSPORT_ERROR",
    },
]


def test_format_run_failure_carries_reasons_and_error_events() -> None:
    """The message names the run, every terminal reason, and each error
    event's operation/status/error_code — the exception the executor
    mapped is visible verbatim."""
    detail = format_run_failure("run-b2c0e3a03f724215", _TERMINAL, _EVENTS)
    assert "run-b2c0e3a03f724215" in detail
    assert "ValueError('simulated boom')" in detail, "the terminal reasons ride the message"
    assert "TRANSPORT_ERROR" in detail, "error events ride the message"
    assert "unknown" in detail
    # The healthy event is context, not noise: it is not individually featured.
    assert detail.count("otdp.dc_psu.measure/1.0.0") == 1


def test_format_run_failure_survives_a_missing_terminal_record() -> None:
    """An honest-unknown run (poison guard) has no terminal record; the
    formatter still names the run and says so instead of raising."""
    detail = format_run_failure("run-poisoned", None, [])
    assert "run-poisoned" in detail
    assert "no terminal record" in detail


def test_dump_at_rest_runs_reads_terminal_json(tmp_path: Path) -> None:
    """The subprocess suites read the kept store at rest: stdlib sqlite3,
    read-only, no benchweave imports (the clean-install gate's rule) —
    every run's terminal_json rides the dump."""
    db = tmp_path / "state.sqlite"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            binding_json TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            terminal_json TEXT,
            tombstoned INTEGER NOT NULL DEFAULT 0,
            tombstoned_at TEXT
        );
        INSERT INTO runs (run_id, binding_json, principal_id, started_at, terminal_json)
        VALUES ('run-x', '{}', 'p', '2026-09-18T00:00:00Z',
                '{"body_outcome": "execution_error", "reasons": ["TimeoutError: dispatch"]}');
        INSERT INTO runs (run_id, binding_json, principal_id, started_at, terminal_json)
        VALUES ('run-open', '{}', 'p', '2026-09-18T00:00:01Z', NULL);
        """
    )
    connection.commit()
    connection.close()

    dump = dump_at_rest_runs(db)
    assert "run-x" in dump
    assert "TimeoutError: dispatch" in dump, "the terminal record's reasons ride the dump"
    assert "run-open" in dump
    assert "no terminal record" in dump


def test_dump_at_rest_runs_is_read_only(tmp_path: Path) -> None:
    """The dump never writes: a missing store reports itself truthfully,
    and an existing store is opened mode=ro (no -wal/-shm side files)."""
    missing = dump_at_rest_runs(tmp_path / "absent.sqlite")
    assert "absent.sqlite" in missing

    db = tmp_path / "state.sqlite"
    db.write_bytes(b"not a database")
    broken = dump_at_rest_runs(db)
    assert "not a database" in broken or "unreadable" in broken
