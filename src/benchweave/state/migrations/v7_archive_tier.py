"""Archive-tier disposition columns (issue #199: the archival tier).

Four additive ``ALTER TABLE dispositions ADD COLUMN``s — all nullable,
zero CHECKs, no new table, no new index (the chain's code-enforced
vocabulary discipline; the columns are never probed by the artifact GC,
whose live-reference predicate is deliberately UNCHANGED — see
``state/dispositions.py::_LIVE_REFERENCE_SQL``).

Design notes pinned by the issue #199 record:

- ``ADD COLUMN`` rewrites no data and adds no constraint — additive in
  exactly the sense v6's own widening already established (v6 indexed
  pre-existing tables from a new migration; schema-object addition to an
  existing table was already judged additive when it rewrites no data).
  SQLite's ``ALTER TABLE ... ADD COLUMN`` has no ``IF NOT EXISTS``
  spelling; the migration engine's per-version rows make re-application
  unnecessary, and the never-migrate prechecks (``refuse_schema_mismatch``)
  refuse holey stores before any at-rest open.
- ``archived_artifact_id`` is a RECORD, never a live reference — the
  archived twin of ``deleted_artifact_id``'s grammar. It is the *binding*:
  the content address the destination object was re-read and re-hashed
  against, pre-commit. Counting it in the GC's live references would keep
  every archived artifact in the store forever and defeat the move: the
  offline object is the surviving copy, and the trail row plus its
  decision artifact stay in the store as the finder's index.
- ``deleted_artifact_id`` stays NULL and ``deleted_byte_length`` 0 on
  archived rows (nothing was destroyed); delete-tier rows keep the four
  archive columns NULL — the two-shape envelope rule is
  ``archive fields present iff outcome == 'archived'`` (STO-5's
  amendment).
- ``archive_destination`` records the RESOLVED target at archive time
  (deployment configuration is per-invocation, ``--archive-target``; the
  row names where the survivor went, not a live mount).
- ``archive_verified_at`` is the STO-1 instant the destination re-read
  matched the content address (caller-supplied, one instant per
  invocation — the plan instant, disclosed like ``executed_at``).
"""

from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE dispositions ADD COLUMN archived_artifact_id TEXT",
    "ALTER TABLE dispositions ADD COLUMN archived_byte_length INTEGER",
    "ALTER TABLE dispositions ADD COLUMN archive_destination TEXT",
    "ALTER TABLE dispositions ADD COLUMN archive_verified_at TEXT",
)
