"""Disposition audit-trail tables (issue #194: the audited delete tier).

Two additive history tables plus the target lookup index; every statement
is ``IF NOT EXISTS`` like all prior migrations, applied under the store's
one-BEGIN-IMMEDIATE-per-migration discipline. Purely additive: no existing
table is altered.

Design notes pinned by the issue #194 record:

- The dispositions tables are HISTORY, never deleted — the
  ``leases``/``changes`` precedent. The audit trail must not be governed
  by the policy it audits (self-reference); its growth is bounded by
  disposition activity and disclosed (record deferral D7).
- Zero CHECK constraints (the chain's discipline): ``row_kind``,
  ``on_disposition`` (``delete`` — the only executable tier), ``outcome``
  and every other vocabulary column is code-enforced by the writer
  (``state/dispositions.py``).
- ``deleted_artifact_id`` is a HISTORICAL record, not a live reference:
  it preserves the digest of the deleted bytes (the forensic
  "what was deleted" proof) without retaining them, and artifact garbage
  collection counts only live references (``evidence.artifact_id``,
  ``capture_staging.artifact_id``, ``dispositions.decision_artifact_id``)
  — counting the historical column would keep every deleted artifact
  alive forever and defeat reclamation.
- ``decision_artifact_id``/``decision_sha256`` pin the full decision
  envelope (canonical JSON, content-addressed through
  ``ContentStore.put_artifact`` INSIDE the disposition transaction — the
  ``finalise`` precedent); STO-1: no clock reads, all timestamps
  caller-supplied, uuid ids (the evidence precedent, STO-2 unamended).
- The three artifact-GC live-reference columns are INDEXED here
  (``evidence.artifact_id``, ``capture_staging.artifact_id``,
  ``dispositions.decision_artifact_id``): the GC probes each dropped
  artifact once under flock + BEGIN IMMEDIATE, and unindexed probes scan
  their whole table per artifact — quadratic in governed rows (measured
  4.24x wall time per row-doubling on the no-index code, fold fix 4).
  Indexing PRE-EXISTING tables from a new migration is additive (an
  index is not a table alteration) and one-time at upgrade: the build
  cost is O(rows log rows) paid once, disclosed in the fold
  measurements.
"""

from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS disposition_invocations ("
    " invocation_id TEXT PRIMARY KEY,"
    " invoked_at TEXT NOT NULL,"
    " actor TEXT NOT NULL,"
    " policy_path TEXT NOT NULL,"
    " policy_sha256 TEXT NOT NULL,"
    " bench_filter TEXT,"
    " counts_json TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS dispositions ("
    " disposition_id TEXT PRIMARY KEY,"
    " invocation_id TEXT NOT NULL,"
    " row_kind TEXT NOT NULL,"
    " target_id TEXT NOT NULL,"
    " context_key TEXT,"
    " bench TEXT,"
    " data_class TEXT NOT NULL,"
    " matched_selector TEXT,"
    " matched_scope TEXT NOT NULL,"
    " matched_rule TEXT NOT NULL,"
    " on_disposition TEXT NOT NULL,"
    " anchor_kind TEXT NOT NULL,"
    " anchor_at TEXT,"
    " disposal_date TEXT NOT NULL,"
    " bytes INTEGER NOT NULL,"
    " deleted_artifact_id TEXT,"
    " deleted_byte_length INTEGER NOT NULL,"
    " decision_artifact_id TEXT NOT NULL,"
    " decision_sha256 TEXT NOT NULL,"
    " executed_at TEXT NOT NULL,"
    " outcome TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_dispositions_target"
    " ON dispositions (row_kind, target_id)",
    "CREATE INDEX IF NOT EXISTS idx_evidence_artifact"
    " ON evidence (artifact_id)",
    "CREATE INDEX IF NOT EXISTS idx_capture_staging_artifact"
    " ON capture_staging (artifact_id)",
    "CREATE INDEX IF NOT EXISTS idx_dispositions_decision"
    " ON dispositions (decision_artifact_id)",
)
