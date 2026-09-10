"""Schema v1: requests, runs, leases, events, schema_migrations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    statements: tuple[str, ...]


V1_INITIAL = Migration(
    version=1,
    statements=(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS requests (
            idempotency_key TEXT PRIMARY KEY,
            body_sha256 TEXT NOT NULL,
            run_id TEXT NOT NULL,
            accepted_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            binding_json TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            terminal_json TEXT,
            tombstoned INTEGER NOT NULL DEFAULT 0,
            tombstoned_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS leases (
            bench_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            lease_id TEXT NOT NULL,
            holder TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            state TEXT NOT NULL,
            PRIMARY KEY (bench_id, sequence)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS events (
            stream_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            event_json TEXT NOT NULL,
            PRIMARY KEY (stream_id, sequence)
        )
        """,
    ),
)
