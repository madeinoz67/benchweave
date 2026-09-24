"""Versioned migrations for the durable state store.

Each migration is a Migration(version, statements) from this package; the
store applies them in order inside explicit transactions and records them in
schema_migrations. Adding schema: append a new module, register it below.
"""

from __future__ import annotations

from .v1_initial import V1_INITIAL, Migration
from .v2_interfaces import STATEMENTS as V2_STATEMENTS
from .v3_run_authority import STATEMENTS as V3_STATEMENTS
from .v4_events_index import STATEMENTS as V4_STATEMENTS
from .v5_capture_staging import STATEMENTS as V5_STATEMENTS
from .v6_dispositions import STATEMENTS as V6_STATEMENTS

MIGRATIONS: tuple[Migration, ...] = (
    V1_INITIAL,
    Migration(version=2, statements=V2_STATEMENTS),
    Migration(version=3, statements=V3_STATEMENTS),
    Migration(version=4, statements=V4_STATEMENTS),
    Migration(version=5, statements=V5_STATEMENTS),
    Migration(version=6, statements=V6_STATEMENTS),
)

__all__ = ["MIGRATIONS", "Migration"]
