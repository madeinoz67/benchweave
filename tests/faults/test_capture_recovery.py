"""Crash recovery for the staged capture writer (issue #43 slice 1).

The sweep reclaims staging orphaned by host death mid-capture, mirroring
``Store.reconcile_dangling_requests`` (the record's Decision 3). It rides
the app lifespan's ONE recovery entrypoint on BOTH branches — the
lattice-failed early path and the normal path — exactly beside the two
``reconcile_dangling_requests()`` calls, and is two transactions (mark
aborted → delete) so a death between them still refunds the ledger.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from benchweave.content import capture_store as capture_module
from benchweave.interfaces.app import _recover_interrupted_runs
from benchweave.state.migrations import MIGRATIONS
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
NOW = "2026-09-22T00:00:00Z"
LATER = "2026-09-22T00:01:00Z"


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = Store.open(tmp_path / "capture-recovery.db")
    yield opened
    opened.close()


def seed_staged(a_store: Store, capture_id: str, context_key: str = "session-a") -> None:
    """A staged capture a dead host left behind (committed rows)."""
    a_store.connection.execute(
        "INSERT INTO capture_staging (capture_id, context_key, state,"
        " reserved_bytes, charged_bytes, format, sample_count, started_at,"
        " created_at, updated_at)"
        " VALUES (?, ?, 'staged', 32, 0, 'waveform_f64le', 4, ?, ?, ?)",
        (capture_id, context_key, NOW, NOW, NOW),
    )
    a_store.connection.execute(
        "INSERT INTO capture_chunks (capture_id, seq, data, byte_length)"
        " VALUES (?, 0, ?, 16)",
        (capture_id, b"\x01" * 16),
    )


def staged_count(a_store: Store) -> int:
    return int(
        a_store.connection.execute(
            "SELECT COUNT(*) FROM capture_staging WHERE state = 'staged'"
        ).fetchone()[0]
    )


def a_v4_database(tmp_path: Path) -> Path:
    """A database left at v4 by an older gateway (hand-applied v1..v4, the
    store's own discipline — the migration list itself stays untouched)."""
    path = tmp_path / "v4.db"
    connection = sqlite3.connect(str(path), isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for migration in MIGRATIONS[:4]:
        connection.execute("BEGIN IMMEDIATE")
        for statement in migration.statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at)"
            " VALUES (?, 'applied-by-migration')",
            (migration.version,),
        )
        connection.execute("COMMIT")
    connection.close()
    return path


# --- the sweep itself ----------------------------------------------------------


def test_sweep_on_a_fresh_database_is_a_noop(store: Store) -> None:
    assert capture_module.CaptureStagingStore(store).reclaim_orphans(LATER) == []


def test_sweep_on_a_v4_upgraded_database_reclaims(tmp_path: Path) -> None:
    path = a_v4_database(tmp_path)
    upgraded = Store.open(path)  # applies v5
    try:
        seed_staged(upgraded, "cap-orphan")
        reclaimed = capture_module.CaptureStagingStore(upgraded).reclaim_orphans(LATER)
        assert reclaimed == ["cap-orphan"]
    finally:
        upgraded.close()


def test_the_kill_window_reclaims_and_a_second_sweep_is_idempotent(
    store: Store, tmp_path: Path
) -> None:
    """The kill shape: rows committed by a host that died mid-capture (the
    process is gone; reopening is the 'restart'). The sweep reclaims them,
    refunds the ledger, and a second sweep is a no-op."""
    seed_staged(store, "cap-dead-1", "session-a")
    seed_staged(store, "cap-dead-2", "session-b")
    db_path = store.connection.execute("PRAGMA database_list").fetchone()[2]
    store.close()  # the host dies; committed staging persists

    restarted = Store.open(str(db_path))
    try:
        writer = capture_module.CaptureStagingStore(
            restarted, max_capture_bytes=1000, max_dataset_bytes=1000
        )
        assert sorted(writer.reclaim_orphans(LATER)) == ["cap-dead-1", "cap-dead-2"]
        assert staged_count(restarted) == 0
        chunks = restarted.connection.execute(
            "SELECT COUNT(*) FROM capture_chunks"
        ).fetchone()[0]
        assert chunks == 0
        assert writer.used_bytes("session-a") == 0  # the ledger refunded
        assert writer.reclaim_orphans(LATER) == []  # idempotent
    finally:
        restarted.close()


# --- the app-lifespan wiring (both branches) -------------------------------------


def test_recovery_sweeps_staging_on_the_lattice_failed_early_path(
    store: Store, tmp_path: Path
) -> None:
    """Startup survives a poisoned lattice: the early path still reclaims
    orphaned capture staging (a wedged capture quota is repairable
    regardless of document admission)."""
    seed_staged(store, "cap-orphan-early")
    db_path = store.connection.execute("PRAGMA database_list").fetchone()[2]
    store.close()
    reopened = Store.open(str(db_path))
    try:
        recovered = _recover_interrupted_runs(
            reopened, tmp_path / "no-such-lattice", emit_keep=100, now_iso=lambda: NOW
        )
        assert recovered == []  # the early path recovers no runs
        assert staged_count(reopened) == 0  # but it still swept the staging
    finally:
        reopened.close()


def test_recovery_sweeps_staging_on_the_normal_path(store: Store) -> None:
    seed_staged(store, "cap-orphan-normal")
    db_path = store.connection.execute("PRAGMA database_list").fetchone()[2]
    store.close()
    reopened = Store.open(str(db_path))
    try:
        _recover_interrupted_runs(
            reopened, FIXTURES, emit_keep=100, now_iso=lambda: NOW
        )
        assert staged_count(reopened) == 0
    finally:
        reopened.close()
