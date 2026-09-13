"""Versioned migrations for the durable state store.

Each migration is a Migration(version, statements) from this package; the
store applies them in order inside explicit transactions and records them in
schema_migrations. Adding schema: append a new module, register it below.
"""

from __future__ import annotations

from .v1_initial import V1_INITIAL, Migration
from .v2_interfaces import STATEMENTS as V2_STATEMENTS
from .v3_run_authority import STATEMENTS as V3_STATEMENTS

MIGRATIONS: tuple[Migration, ...] = (
    V1_INITIAL,
    Migration(version=2, statements=V2_STATEMENTS),
    Migration(version=3, statements=V3_STATEMENTS),
)

__all__ = ["MIGRATIONS", "Migration"]
