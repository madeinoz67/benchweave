"""WP03 fault and semantics tests for the durable state store.

Kill-safety is proven with real SIGKILL against a child process holding an
open SQLite transaction; semantics tests prove idempotency, conflict,
tombstone retention, per-bench lease sequence and per-stream event
continuity, matching the delivery plan's WP03 verification list.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchweave.state.migrations import MIGRATIONS
from benchweave.state.store import (
    Conflict,
    Store,
    accept_result,
)

ROOT = Path(__file__).resolve().parents[2]
CHILD = ROOT / "tests" / "faults" / "_kill_child.py"
NOW = "2026-09-10T00:00:00Z"


def binding_body(procedure: str = "proc-a") -> dict[str, Any]:
    return {
        "procedure": {"id": procedure, "version": "1.0.0"},
        "bench": "bench-1",
        "policy": "standard",
    }


def body_hash(body: dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = Store.open(str(tmp_path / "state.db"))
    yield opened
    opened.close()


# --- request idempotency and conflict --------------------------------------


def test_accept_then_same_key_same_body_is_duplicate(store: Store) -> None:
    body = binding_body()
    first = store.accept_request("req-1", body_hash(body), "run-1", NOW)
    second = store.accept_request("req-1", body_hash(body), "run-1", NOW)
    assert accept_result(first) == "accepted"
    assert accept_result(second) == "duplicate"
    assert first.run_id == second.run_id == "run-1"


def test_same_key_different_body_conflicts(store: Store) -> None:
    store.accept_request("req-1", body_hash(binding_body("proc-a")), "run-1", NOW)
    with pytest.raises(Conflict):
        store.accept_request("req-1", body_hash(binding_body("proc-b")), "run-2", NOW)


# --- D13 crash-window: accept_request without create_run -------------------


def test_crash_window_split_state_reconciles_never_wedges(store: Store) -> None:
    """A process death between ``accept_request`` and ``create_run``
    leaves a §9 key pointing at a run that never materialized — every
    same-body replay resolves the key and then fails on the ghost. The
    recovery sweep (the store leg of the lifespan's recovery entrypoint)
    purges exactly those keys: healthy keys — including a tombstoned
    run's — survive, the sweep is idempotent, and the same request id
    proceeds afterwards."""
    body = body_hash(binding_body())
    # The split state, written directly over the store's sqlite3
    # connection: the committed requests row, no runs row behind it.
    store.connection.execute(
        "INSERT INTO requests (idempotency_key, body_sha256, run_id, accepted_at)"
        " VALUES (?, ?, ?, ?)",
        ("key-dangling", body, "run-never-created", NOW),
    )
    # Healthy shapes the sweep must NOT touch: a live key+run pair, and a
    # key whose run was tombstoned (the run row still exists).
    store.accept_request("key-live", body, "run-live", NOW)
    store.create_run("run-live", binding_body(), "engineer-a", NOW)
    store.accept_request("key-tomb", body, "run-tomb", NOW)
    store.create_run("run-tomb", binding_body(), "engineer-a", NOW)
    store.delete_run("run-tomb", NOW)

    # The durable wedge, pre-recovery: the key exists, its run does not.
    assert store.find_request("key-dangling") is not None
    assert store.get_run("run-never-created") is None
    replay = store.accept_request("key-dangling", body, "run-never-created", NOW)
    assert accept_result(replay) == "duplicate"  # the ghost keeps answering

    purged = store.reconcile_dangling_requests()
    assert purged == ["key-dangling"]
    assert store.find_request("key-dangling") is None
    assert store.find_request("key-live") is not None
    assert store.find_request("key-tomb") is not None
    assert store.get_run("run-live") is not None

    # Idempotent, and the same request id proceeds once reconciled.
    assert store.reconcile_dangling_requests() == []
    again = store.accept_request("key-dangling", body, "run-retry-1", NOW)
    assert accept_result(again) == "accepted"


# --- runs and retained tombstones ------------------------------------------


def test_create_and_finalize_run(store: Store) -> None:
    store.create_run("run-1", binding_body(), "engineer-a", NOW)
    terminal = {"outcome": "passed", "safe_state": "verified"}
    store.finalize_run("run-1", terminal)
    run = store.get_run("run-1")
    assert run is not None
    assert run["terminal"] == terminal


def test_delete_run_retains_tombstone_and_blocks_reuse(store: Store) -> None:
    store.create_run("run-1", binding_body(), "engineer-a", NOW)
    store.delete_run("run-1", NOW)
    tombstone = store.get_run("run-1")
    assert tombstone is not None, "tombstone must remain readable"
    assert tombstone["tombstoned"] is True
    with pytest.raises(ValueError, match="tombstoned"):
        store.create_run("run-1", binding_body(), "engineer-a", NOW)


# --- leases: per-bench monotonic sequence ----------------------------------


def test_lease_sequence_monotonic_per_bench(store: Store) -> None:
    first = store.next_lease("bench-1", "lease-a", "engineer-a", NOW)
    second = store.next_lease("bench-1", "lease-b", "engineer-a", NOW)
    third = store.next_lease("bench-1", "lease-c", "engineer-b", NOW)
    assert (first.sequence, second.sequence, third.sequence) == (1, 2, 3)
    other = store.next_lease("bench-2", "lease-x", "engineer-a", NOW)
    assert other.sequence == 1


def test_lease_state_transitions(store: Store) -> None:
    lease = store.next_lease("bench-1", "lease-a", "engineer-a", NOW)
    assert lease.state == "active"
    store.release_lease("bench-1", lease.sequence, NOW)
    released = store.get_active_lease("bench-1")
    assert released is None
    rows = store.list_leases("bench-1")
    assert len(rows) == 1 and rows[0].state == "released"


# --- events: per-stream gap-free continuity --------------------------------


def test_event_sequence_is_gap_free_across_reopen(store: Store, tmp_path: Path) -> None:
    for index in range(1, 4):
        store.append_event(
            "stream-1",
            {
                "stream_id": "stream-1",
                "sequence": str(index),
                "at": NOW,
                "kind": "run_changed",
                "run_id": "run-1",
                "evidence": {"id": "ev", "version": "1", "sha256": "0" * 64},
            },
        )
    store.close()
    reopened = Store.open(str(tmp_path / "state.db"))
    reopened.append_event(
        "stream-1",
        {
            "stream_id": "stream-1",
            "sequence": "4",
            "at": NOW,
            "kind": "run_changed",
            "run_id": "run-1",
            "evidence": {"id": "ev", "version": "1", "sha256": "0" * 64},
        },
    )
    sequences = [event["sequence"] for event in reopened.read_events("stream-1")]
    assert sequences == ["1", "2", "3", "4"]
    reopened.close()


def test_event_sequences_are_per_stream(store: Store) -> None:
    for stream in ("stream-1", "stream-2"):
        store.append_event(
            stream,
            {
                "stream_id": stream,
                "sequence": "1",
                "at": NOW,
                "kind": "trip",
                "run_id": None,
                "evidence": {"id": "ev", "version": "1", "sha256": "0" * 64},
            },
        )
    assert len(store.read_events("stream-1")) == 1
    assert len(store.read_events("stream-2")) == 1


# --- migrations -------------------------------------------------------------


def test_migrations_apply_once_and_are_idempotent(store: Store, tmp_path: Path) -> None:
    assert store.schema_version() == MIGRATIONS[-1].version
    store.close()
    reopened = Store.open(str(tmp_path / "state.db"))
    assert reopened.schema_version() == MIGRATIONS[-1].version
    reopened.close()


# --- no device I/O inside state code (structural) ---------------------------


def test_store_module_has_no_device_or_host_imports() -> None:
    source = (ROOT / "src" / "benchweave" / "state" / "store.py").read_text(encoding="utf-8")
    for banned in ("benchweave.host", "benchweave.interfaces", "plugins", "socket", "urllib"):
        assert banned not in source, f"state code must not import {banned}"


# --- real SIGKILL fault injection -------------------------------------------


def _spawn(mode: str, path: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, str(CHILD), mode, str(path)],
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
    )


def _await_marker(process: subprocess.Popen[bytes], marker: str) -> None:
    assert process.stdout is not None
    line = process.stdout.readline().decode().strip()
    assert line == "OPENED", f"unexpected child output: {line}"
    if marker != "OPENED":
        line = process.stdout.readline().decode().strip()
        assert line == marker, f"waiting for {marker}, got {line}"


def test_kill_before_commit_loses_nothing_partial(tmp_path: Path) -> None:
    path = tmp_path / "kill.db"
    child = _spawn("hold", path)
    try:
        _await_marker(child, "READY")
    finally:
        child.kill()
        child.wait(timeout=10)
    store = Store.open(str(path))
    assert store.get_run("kill-window-run") is None, "uncommitted writes must vanish"
    assert store.list_leases("kill-bench") == [], "uncommitted lease must vanish"
    store.close()
    survivor = Store.open(str(path))  # db still usable after the kill
    assert survivor.schema_version() == MIGRATIONS[-1].version
    survivor.close()


def test_kill_after_commit_state_survives(tmp_path: Path) -> None:
    path = tmp_path / "kill.db"
    child = _spawn("commit", path)
    try:
        _await_marker(child, "COMMITTED")
    finally:
        child.kill()
        child.wait(timeout=10)
    store = Store.open(str(path))
    assert store.get_run("kill-window-run") is not None, "committed writes must survive SIGKILL"
    store.close()
