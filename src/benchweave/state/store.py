"""Durable run/lease/request/event state over SQLite (WP03).

Single-writer store: WAL journal, synchronous=FULL, explicit transactions.
Timestamps are caller-supplied (no clock reads); no device, network or
plugin I/O lives here. Sequence authorities (per-bench lease sequence,
per-stream event sequence) are assigned under BEGIN IMMEDIATE, which makes
them monotonic and gap-free by construction.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchweave.state.migrations import MIGRATIONS


class Duplicate(Exception):
    """Idempotent replay: same key, same body, already accepted."""


class Conflict(Exception):
    """Same key, different body: not a replay, a client bug or a race."""


@dataclass(frozen=True)
class AcceptResult:
    outcome: str  # "accepted" | "duplicate"
    run_id: str


@dataclass(frozen=True)
class Lease:
    lease_id: str
    bench_id: str
    sequence: int
    holder: str
    expires_at: str
    state: str


def accept_result(result: AcceptResult) -> str:
    return result.outcome


class Store:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    # --- lifecycle ---------------------------------------------------------

    @classmethod
    def open(cls, path: str | Path) -> Store:
        connection = sqlite3.connect(str(path), isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=5000")
        store = cls(connection)
        store._apply_migrations()
        return store

    def close(self) -> None:
        self._conn.close()

    def _apply_migrations(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for migration in MIGRATIONS:
            applied = self._conn.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?", (migration.version,)
            ).fetchone()[0]
            if applied:
                continue
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in migration.statements:
                    self._conn.execute(statement)
                self._conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (migration.version, "applied-by-migration"),
                )
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0)

    # --- request idempotency -------------------------------------------------

    def accept_request(self, key: str, body_sha256: str, run_id: str, now: str) -> AcceptResult:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT body_sha256, run_id FROM requests WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if row is not None:
                self._conn.execute("ROLLBACK")
                if row[0] == body_sha256:
                    return AcceptResult(outcome="duplicate", run_id=row[1])
                raise Conflict(f"idempotency key {key!r} reused with a different body")
            self._conn.execute(
                "INSERT INTO requests (idempotency_key, body_sha256, run_id, accepted_at)"
                " VALUES (?, ?, ?, ?)",
                (key, body_sha256, run_id, now),
            )
        except BaseException:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return AcceptResult(outcome="accepted", run_id=run_id)

    # --- runs -----------------------------------------------------------------

    def create_run(self, run_id: str, binding: dict[str, Any], principal_id: str, now: str) -> None:
        existing = self._conn.execute(
            "SELECT tombstoned FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if existing is not None:
            if existing[0]:
                raise ValueError(f"run {run_id!r} is tombstoned; ids are never reusable")
            raise ValueError(f"run {run_id!r} already exists")
        self._conn.execute("BEGIN IMMEDIATE")
        self._conn.execute(
            "INSERT INTO runs (run_id, binding_json, principal_id, started_at)"
            " VALUES (?, ?, ?, ?)",
            (run_id, json.dumps(binding, sort_keys=True), principal_id, now),
        )
        self._conn.execute("COMMIT")

    def finalize_run(self, run_id: str, terminal: dict[str, Any]) -> None:
        cursor = self._conn.execute(
            "UPDATE runs SET terminal_json = ? WHERE run_id = ? AND tombstoned = 0",
            (json.dumps(terminal, sort_keys=True), run_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"run {run_id!r} not found or tombstoned")

    def delete_run(self, run_id: str, now: str) -> None:
        cursor = self._conn.execute(
            "UPDATE runs SET tombstoned = 1, tombstoned_at = ? WHERE run_id = ? AND tombstoned = 0",
            (now, run_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"run {run_id!r} not found or already tombstoned")

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT binding_json, principal_id, started_at, terminal_json, tombstoned,"
            " tombstoned_at FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "run_id": run_id,
            "binding": json.loads(row[0]),
            "principal_id": row[1],
            "started_at": row[2],
            "terminal": json.loads(row[3]) if row[3] is not None else None,
            "tombstoned": bool(row[4]),
            "tombstoned_at": row[5],
        }

    # --- leases -----------------------------------------------------------------

    def next_lease(self, bench_id: str, lease_id: str, holder: str, expires_at: str) -> Lease:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT MAX(sequence) FROM leases WHERE bench_id = ?", (bench_id,)
            ).fetchone()
            sequence = int(row[0] or 0) + 1
            self._conn.execute(
                "INSERT INTO leases (bench_id, sequence, lease_id, holder, expires_at, state)"
                " VALUES (?, ?, ?, ?, ?, 'active')",
                (bench_id, sequence, lease_id, holder, expires_at),
            )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return Lease(
            lease_id=lease_id,
            bench_id=bench_id,
            sequence=sequence,
            holder=holder,
            expires_at=expires_at,
            state="active",
        )

    def release_lease(self, bench_id: str, sequence: int, now: str) -> None:
        cursor = self._conn.execute(
            "UPDATE leases SET state = 'released', expires_at = ? "
            "WHERE bench_id = ? AND sequence = ? AND state = 'active'",
            (now, bench_id, sequence),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"no active lease {sequence} on bench {bench_id!r}")

    def get_active_lease(self, bench_id: str) -> Lease | None:
        row = self._conn.execute(
            "SELECT lease_id, bench_id, sequence, holder, expires_at, state"
            " FROM leases WHERE bench_id = ? AND state = 'active'"
            " ORDER BY sequence DESC LIMIT 1",
            (bench_id,),
        ).fetchone()
        if row is None:
            return None
        return Lease(
            lease_id=row[0], bench_id=row[1], sequence=row[2], holder=row[3],
            expires_at=row[4], state=row[5],
        )

    def list_leases(self, bench_id: str) -> list[Lease]:
        rows = self._conn.execute(
            "SELECT lease_id, bench_id, sequence, holder, expires_at, state"
            " FROM leases WHERE bench_id = ? ORDER BY sequence",
            (bench_id,),
        ).fetchall()
        return [
            Lease(
                lease_id=row[0], bench_id=row[1], sequence=row[2], holder=row[3],
                expires_at=row[4], state=row[5],
            )
            for row in rows
        ]

    # --- events -------------------------------------------------------------------

    def append_event(self, stream_id: str, event: dict[str, Any]) -> int:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT MAX(sequence) FROM events WHERE stream_id = ?", (stream_id,)
            ).fetchone()
            sequence = int(row[0] or 0) + 1
            envelope = dict(event)
            envelope["sequence"] = str(sequence)
            self._conn.execute(
                "INSERT INTO events (stream_id, sequence, event_json) VALUES (?, ?, ?)",
                (stream_id, sequence, json.dumps(envelope, sort_keys=True)),
            )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return sequence

    def read_events(self, stream_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT event_json FROM events WHERE stream_id = ? ORDER BY sequence",
            (stream_id,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    # --- fault-injection window (test support) --------------------------------------

    def begin_kill_window(self) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        self._conn.execute(
            "INSERT INTO runs (run_id, binding_json, principal_id, started_at)"
            " VALUES ('kill-window-run', '{}', 'fault-injector', '1970-01-01T00:00:00Z')"
        )
        self._conn.execute(
            "INSERT INTO leases (bench_id, sequence, lease_id, holder, expires_at, state)"
            " VALUES ('kill-bench', 1, 'kill-lease', 'fault-injector',"
            " '1970-01-01T00:00:00Z', 'active')"
        )

    def commit_kill_window(self) -> None:
        self.begin_kill_window()
        self._conn.execute("COMMIT")
