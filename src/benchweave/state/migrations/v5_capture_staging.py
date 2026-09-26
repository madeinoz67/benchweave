"""Capture staging tables (issue #43 slice 1, Decision 3's staged writer).

Two additive tables plus the sweep's serving index; every statement is
``IF NOT EXISTS`` like all prior migrations, applied under the store's
one-BEGIN-IMMEDIATE-per-migration discipline (a failed migration rolls back
whole). Purely additive: no existing table is altered.

Design notes pinned by the surrounding slice:

- ``state`` carries the three-value vocabulary ``staged | finalised |
  aborted`` with NO CHECK constraint — zero CHECKs exist in the migration
  chain, state vocabulary is code-enforced everywhere else, and SQLite
  cannot ALTER a CHECK without a table rebuild (a later 'disposed'
  widening). The vocabulary is pinned by a writer test, and raw-SQL
  fixtures can insert any state.
- ``artifact_id`` and ``started_at`` are nullable on purpose: the
  capture→artifact linkage must survive chunk deletion (slice 3's charter
  needs it; it is unrecoverable once the chunks are gone). ``started_at``
  is stamped at open; ``artifact_id`` is set inside the finalise
  transaction.
- STO-1: no clock reads; all timestamps are caller-supplied. Chunk ``seq``
  is assigned ``MAX(seq)+1`` per capture under BEGIN IMMEDIATE by the
  writer (STO-2 precedent).

Payload-lane addendum (issue #146 slice 3, no STATEMENTS change — the
dual-use is within this table's contract, governor-ruled): the dataset
lane's staged payloads ride the SAME rows through the writer's
``open_payload`` — ``capture_id`` carries the ``pay:{op}:{n}`` staging
id, ``format`` carries the payload encoding (the manifest artifact
enum), and ``sample_count`` is NULL (the raw_binary captures already
open with ``sample_count=None``). No migration: the columns admit both
lanes as declared, and the retention report labels the lanes apart
(``dataset:<encoding>`` vs ``capture:<format>``).
"""

from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS capture_staging ("
    " capture_id TEXT PRIMARY KEY,"
    " context_key TEXT NOT NULL,"
    " state TEXT NOT NULL,"
    " reserved_bytes INTEGER NOT NULL,"
    " charged_bytes INTEGER NOT NULL DEFAULT 0,"
    " format TEXT,"
    " sample_count INTEGER,"
    " artifact_id TEXT,"
    " started_at TEXT,"
    " created_at TEXT NOT NULL,"
    " updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS capture_chunks ("
    " capture_id TEXT NOT NULL,"
    " seq INTEGER NOT NULL,"
    " data BLOB NOT NULL,"
    " byte_length INTEGER NOT NULL,"
    " PRIMARY KEY (capture_id, seq))",
    "CREATE INDEX IF NOT EXISTS idx_capture_staging_state ON capture_staging (state)",
)
