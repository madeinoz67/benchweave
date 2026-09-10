"""Versioned migrations for the durable state store.

Each migration is a Migration(version, statements) from this package; the
store applies them in order inside explicit transactions and records them in
schema_migrations. Adding schema: append a new module, register it below.
"""

from __future__ import annotations

from .v1_initial import V1_INITIAL, Migration

MIGRATIONS: tuple[Migration, ...] = (V1_INITIAL,)

__all__ = ["MIGRATIONS", "Migration"]
