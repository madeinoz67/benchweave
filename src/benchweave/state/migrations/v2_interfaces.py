"""WP07 interface-layer migration: generation authority, bench inventory,
run-state projection, admin change records. Additive only."""

from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS benches (
        bench_id TEXT PRIMARY KEY,
        generation INTEGER NOT NULL,
        qualification TEXT NOT NULL,
        configuration_json TEXT NOT NULL,
        licence TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS devices (
        device_id TEXT PRIMARY KEY,
        bench_id TEXT NOT NULL,
        generation INTEGER NOT NULL,
        profiles_json TEXT NOT NULL,
        descriptor_json TEXT NOT NULL,
        identity_state TEXT NOT NULL,
        licence TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS generations (
        bench_id TEXT PRIMARY KEY,
        generation INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_states (
        run_id TEXT PRIMARY KEY,
        bench_id TEXT NOT NULL,
        state TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS changes (
        change_id TEXT PRIMARY KEY,
        bench_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        target_ref_json TEXT NOT NULL,
        expected_generation INTEGER NOT NULL,
        reason TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'proposed',
        reasons_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        sha256 TEXT PRIMARY KEY,
        raw_bytes BLOB NOT NULL,
        content_json TEXT NOT NULL,
        schema_id TEXT NOT NULL,
        stored_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        data BLOB NOT NULL,
        stored_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence (
        evidence_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        content_ref_json TEXT NOT NULL,
        artifact_id TEXT,
        context_key TEXT,
        stored_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_devices_bench ON devices (bench_id)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_context ON evidence (context_key)",
)