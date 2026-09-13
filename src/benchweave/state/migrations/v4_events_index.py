"""WP08 Task 4 (D13 batch A): events cursor-read index.

The events table's paging read (``Store.read_events_after`` —
``WHERE stream_id = ? AND sequence > ? ORDER BY sequence LIMIT ?``) rides
an explicit, migration-tracked index. The v1 composite PRIMARY KEY
already implies an equivalent autoindex; the explicit index makes the
serving structure a declared artifact of the schema, and SQLite's planner
prefers it — pinned by EXPLAIN QUERY PLAN in
``tests/unit/test_store_hygiene.py`` (an index that exists but is not
used fails that pin).
"""

from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_events_stream_seq ON events (stream_id, sequence)",
)
