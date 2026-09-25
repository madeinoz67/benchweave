"""The disposition audit trail's transactional writer (issue #194).

``DispositionLog`` executes ONE ``BEGIN IMMEDIATE`` invocation transaction
carrying the complete audit record — the invocation row, one audit row per
disposed governed row (its decision envelope content-addressed through
``ContentStore.put_artifact`` inside this transaction, the ``finalise``
precedent), the guarded exact-row deletions, and the reference-checked
artifact garbage collection — so a committed deletion without its audit row
is UNREPRESENTABLE (STO-5). A crash or refusal anywhere in the window
disposes nothing: the whole transaction rolls back and a re-run re-plans
cleanly, since deleted rows simply vanish from the report.

Layering: the ``CaptureStagingStore`` precedent — a writer class over the
store's single writer connection, no store of its own. The PLAN is never
derived here: the caller hands in the rows ``build_retention_report``
selected (``scheduled ∧ overdue ∧ on_disposition=delete``), so selection,
scoping and matched-rule identity stay the slice-3 contract with zero
formula drift.

Guarded deletes (the ``_close_lease`` exact-row precedent): each deletion
carries the row's identifying columns and checks ``rowcount == 1`` — a row
that vanished or drifted under the plan (a non-flock concurrent writer;
the disclosed row-16 residual) refuses typed as
:class:`StoreChangedUnderPlan`, never a wrong-row deletion. The guard
values are read inside the transaction and, where the plan carries the
same stamp (``anchor_kind == "landing"`` — the report's landing anchor IS
the row's own ``stored_at``/``updated_at``), cross-checked against the
plan's copy.

Artifact GC counts LIVE references only — ``evidence.artifact_id``,
``capture_staging.artifact_id``, ``dispositions.decision_artifact_id``.
The historical ``deleted_artifact_id`` is a record, never a reference:
counting it would keep every deleted artifact alive forever and defeat
reclamation.

STO-1: no clock reads — ``now`` is caller-supplied for the invocation row
and every audit row. STO-2 unamended: uuid ids, no new sequence
authority. The dispositions tables are history, never deleted (the
``leases``/``changes`` precedent); this module provides no delete path
for them.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from typing import Any

from benchweave.content.store import ContentStore
from benchweave.state.store import Store

#: The audit row's outcome vocabulary (code-enforced, zero CHECKs): the
#: delete tier and — since issue #199 — the archive tier (``archived``:
#: the governed row moved offline through a verified content-addressed
#: copy; ``blocked_archive`` stays a PLAN classification in
#: ``cli/dispose.py``, never an audit outcome — a blocked row writes
#: nothing).
_OUTCOME_DELETED = "deleted"
_OUTCOME_ARCHIVED = "archived"


class StoreChangedUnderPlan(ValueError):
    """A guarded delete found the row not exactly as the plan selected it
    (vanished, state-drifted, or its landing stamp moved). The whole
    invocation rolls back — the operator re-runs and the fresh plan
    reflects the changed store."""


def new_invocation_id() -> str:
    """A disposition invocation id (contract id shape, no colons)."""
    return "dsp-inv-" + uuid.uuid4().hex


def new_disposition_id() -> str:
    """One audit row's id (contract id shape, no colons)."""
    return "dsp-" + uuid.uuid4().hex


#: The envelope fields, in the ``dispositions`` column order minus the two
#: digest columns (which are derived FROM the envelope — including them
#: would be circular). The blob is the store's canonical JSON form.
_ENVELOPE_FIELDS = (
    "disposition_id",
    "invocation_id",
    "row_kind",
    "target_id",
    "context_key",
    "bench",
    "data_class",
    "matched_selector",
    "matched_scope",
    "matched_rule",
    "on_disposition",
    "anchor_kind",
    "anchor_at",
    "disposal_date",
    "bytes",
    "deleted_artifact_id",
    "deleted_byte_length",
    "executed_at",
    "outcome",
)

#: The archive-tier envelope fields (v7), present iff the row's outcome
#: is ``archived`` — the two-shape rule (issue #199 §2.3): delete-tier
#: blobs stay byte-identical to v6's 19-field canonical form, archived
#: blobs carry the four archive fields. Writer and recomputation derive
#: from the same rule, so the shapes cannot drift.
_ARCHIVE_ENVELOPE_FIELDS = (
    "archived_artifact_id",
    "archived_byte_length",
    "archive_destination",
    "archive_verified_at",
)


def _envelope_fields(outcome: str) -> tuple[str, ...]:
    """The canonical-JSON field set for an audit envelope of the given
    outcome — the two-shape rule's single derivation point (archive
    fields join the envelope iff the outcome is ``archived``)."""
    if outcome == _OUTCOME_ARCHIVED:
        return _ENVELOPE_FIELDS + _ARCHIVE_ENVELOPE_FIELDS
    return _ENVELOPE_FIELDS


#: The three live-reference columns artifact GC counts (§2.1's predicate).
_LIVE_REFERENCE_SQL = (
    "SELECT (SELECT COUNT(*) FROM evidence WHERE artifact_id = ?)"
    " + (SELECT COUNT(*) FROM capture_staging WHERE artifact_id = ?)"
    " + (SELECT COUNT(*) FROM dispositions WHERE decision_artifact_id = ?)"
)


def _artifact_length(conn: sqlite3.Connection, artifact_id: str | None) -> int:
    """The artifact's byte length (the forensic ``deleted_byte_length``),
    0 for rows that reference no artifact."""
    if artifact_id is None:
        return 0
    row = conn.execute(
        "SELECT LENGTH(data) FROM artifacts WHERE artifact_id = ?", (artifact_id,)
    ).fetchone()
    return int(row[0]) if row is not None and row[0] is not None else 0


class DispositionLog:
    """The audit-trail writer over the store's single writer connection."""

    def __init__(self, store: Store) -> None:
        self._conn = store.connection
        self._content = ContentStore(store)

    # --- the guarded deletes -------------------------------------------------

    def _current_row(self, plan: dict[str, Any]) -> tuple[str | None, str, tuple[Any, ...]]:
        """Read the target row's current guard columns inside the open
        transaction and build the exact-row delete (the design's SQL
        verbatim). Raises :class:`StoreChangedUnderPlan` when the row
        vanished or drifted; the landing-stamp cross-check catches a row
        whose stamp moved between plan and execution even though the
        in-transaction read is self-consistent."""
        if plan["row_kind"] == "evidence":
            row = self._conn.execute(
                "SELECT kind, stored_at, artifact_id FROM evidence"
                " WHERE evidence_id = ?",
                (plan["id"],),
            ).fetchone()
            if row is None:
                raise StoreChangedUnderPlan(
                    f"dispose: store changed under the plan — evidence row "
                    f"{plan['id']!r} vanished before its guarded delete"
                )
            kind, stored_at, artifact_id = row[0], row[1], row[2]
            expected_kind = str(plan["data_class"]).removeprefix("evidence:")
            if kind != expected_kind:
                raise StoreChangedUnderPlan(
                    f"dispose: store changed under the plan — evidence row "
                    f"{plan['id']!r} kind drifted from {expected_kind!r} "
                    f"to {kind!r}"
                )
            if plan["anchor_kind"] == "landing" and stored_at != plan["anchor_at"]:
                raise StoreChangedUnderPlan(
                    f"dispose: store changed under the plan — evidence row "
                    f"{plan['id']!r} landing stamp moved from "
                    f"{plan['anchor_at']!r} to {stored_at!r}"
                )
            return (
                artifact_id if isinstance(artifact_id, str) else None,
                "DELETE FROM evidence WHERE evidence_id = ? AND kind = ?"
                " AND stored_at = ?",
                (plan["id"], kind, stored_at),
            )
        row = self._conn.execute(
            "SELECT state, updated_at, artifact_id FROM capture_staging"
            " WHERE capture_id = ?",
            (plan["id"],),
        ).fetchone()
        if row is None:
            raise StoreChangedUnderPlan(
                f"dispose: store changed under the plan — capture row "
                f"{plan['id']!r} vanished before its guarded delete"
            )
        state, updated_at, artifact_id = row[0], row[1], row[2]
        if state != "finalised":
            raise StoreChangedUnderPlan(
                f"dispose: store changed under the plan — capture row "
                f"{plan['id']!r} is no longer finalised ({state!r})"
            )
        if plan["anchor_kind"] == "landing" and updated_at != plan["anchor_at"]:
            raise StoreChangedUnderPlan(
                f"dispose: store changed under the plan — capture row "
                f"{plan['id']!r} landing stamp moved from "
                f"{plan['anchor_at']!r} to {updated_at!r}"
            )
        return (
            artifact_id if isinstance(artifact_id, str) else None,
            "DELETE FROM capture_staging WHERE capture_id = ?"
            " AND state = 'finalised' AND updated_at = ?",
            (plan["id"], updated_at),
        )

    def _collect_unreferenced(self, dropped: set[str]) -> tuple[int, int]:
        """GC artifacts whose live references are all gone (§2.1's
        predicate); returns the number actually deleted — a shared
        artifact survives, decision artifacts are live references by
        construction, and a dropped id referenced by two deleted rows is
        visited exactly once (the set).

        Deletion verifies first (the ``finalise`` mirror): the bytes are
        re-read and re-hashed against the content address embedded in the
        id, and a mismatch refuses typed — stored bytes are verified,
        never trusted. The check rides the invocation transaction, so the
        refusal rolls the whole disposition back.

        Returns ``(collected, freed_bytes)`` — the count of artifacts
        deleted and their byte total (the DISK unit; a shared artifact
        counts nowhere, a deleted one exactly once)."""
        collected = 0
        freed_bytes = 0
        for artifact_id in sorted(dropped):
            live = int(
                self._conn.execute(
                    _LIVE_REFERENCE_SQL, (artifact_id, artifact_id, artifact_id)
                ).fetchone()[0]
            )
            if live == 0:
                row = self._conn.execute(
                    "SELECT data FROM artifacts WHERE artifact_id = ?", (artifact_id,)
                ).fetchone()
                if row is not None and hashlib.sha256(bytes(row[0])).hexdigest() != (
                    artifact_id.removeprefix("art-")
                ):
                    raise StoreChangedUnderPlan(
                        f"dispose: store changed under the plan — artifact "
                        f"{artifact_id!r} bytes do not hash to their content "
                        f"address (corrupt or tampered store); refusing to "
                        f"collect it"
                    )
                if row is not None:
                    freed_bytes += len(bytes(row[0]))
                collected += int(
                    self._conn.execute(
                        "DELETE FROM artifacts WHERE artifact_id = ?", (artifact_id,)
                    ).rowcount
                )
        return collected, freed_bytes

    # --- the one invocation transaction ----------------------------------------

    def execute_invocation(
        self,
        selected: list[dict[str, Any]],
        *,
        invocation_id: str,
        actor: str,
        policy_path: str,
        policy_sha256: str,
        bench_filter: str | None,
        counts: dict[str, int],
        now: str,
        archive_rows: list[dict[str, Any]] | None = None,
        archive_figures: dict[str, int] | None = None,
        mid_hook: Callable[[int], None] | None = None,
    ) -> dict[str, Any]:
        """Execute the whole invocation as ONE ``BEGIN IMMEDIATE``
        transaction: invocation row → per disposed row (audit envelope
        artifact + audit row + guarded delete) → reference-checked artifact
        GC → COMMIT.

        Two tiers share the one window (issue #199 §2.2 Phase B):
        ``selected`` are the delete-tier rows and ``archive_rows`` the
        archive-tier rows, each carrying the Phase-A staged facts (the
        ``archived_*``/``archive_*`` keys). The archive objects were
        staged and re-verified at the destination BEFORE this transaction
        opened — inside it both tiers are the same motion (envelope →
        guarded delete → GC drop), so a refusal or crash disposes NOTHING
        of either tier. ``archive_figures`` carries the stager's measured
        copy figures (``archive_objects_placed``/``deduped``/
        ``archive_bytes_copied``) into ``counts_json``.

        ``counts`` is the caller's complete per-outcome classification;
        the invocation row's ``counts_json`` adds the byte figures:
        ``bytes_reclaimed`` (Σ the disposed rows' bytes figures — the
        disposal-rows method sum, both tiers), ``charged_ledger_bytes``
        (Σ over disposed CAPTURE rows only, both tiers — the G3 ledger
        relief; archive relieves it exactly like delete, §2.4) and
        ``artifact_bytes_freed`` (bytes physically removed by GC — the
        disk unit; evidence rows sharing artifacts make the row-bytes sum
        double-count and diverge from disk, so the units are named
        separately). ``now`` stamps ``invoked_at`` and every row's
        ``executed_at`` (STO-1: caller-supplied, one instant per
        invocation — and, on archived rows, ``archive_verified_at``: the
        plan instant, not a per-object measurement).

        ``mid_hook`` is TEST SUPPORT (the ``begin_kill_window``
        precedent): called with each row's index inside the open
        transaction — the fault suite's kill window. Production callers
        never pass it.

        Returns the execution summary (deleted and archived ids,
        artifacts collected, the three byte figures).
        """
        archived_rows = list(archive_rows) if archive_rows else []
        # The unified worklist: delete-tier rows first, then archive-tier
        # rows, each carrying its outcome. Order inside the one
        # transaction does not change durability — it only keeps the
        # audit trail's row order deterministic.
        worklist = [(plan, _OUTCOME_DELETED) for plan in selected]
        worklist += [(plan, _OUTCOME_ARCHIVED) for plan in archived_rows]
        bytes_reclaimed = sum(int(row["bytes"]) for row in selected) + sum(
            int(row["bytes"]) for row in archived_rows
        )
        charged_ledger_bytes = sum(
            int(row["bytes"])
            for row in [*selected, *archived_rows]
            if row["row_kind"] == "capture"
        )
        dropped: set[str] = set()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for index, (plan, outcome) in enumerate(worklist):
                artifact_id, delete_sql, delete_args = self._current_row(plan)
                disposition_id = new_disposition_id()
                envelope: dict[str, Any] = {
                    "disposition_id": disposition_id,
                    "invocation_id": invocation_id,
                    "row_kind": plan["row_kind"],
                    "target_id": plan["id"],
                    "context_key": plan["context_key"],
                    "bench": plan["bench"],
                    "data_class": plan["data_class"],
                    "matched_selector": plan["matched_selector"],
                    "matched_scope": plan["matched_scope"],
                    "matched_rule": plan["matched_rule"],
                    "on_disposition": plan["on_disposition"],
                    "anchor_kind": plan["anchor_kind"],
                    "anchor_at": plan["anchor_at"],
                    "disposal_date": plan["disposal_date"],
                    "bytes": int(plan["bytes"]),
                    "executed_at": now,
                    "outcome": outcome,
                }
                if outcome == _OUTCOME_ARCHIVED:
                    # Nothing was destroyed: the offline object is the
                    # survivor, and the four archive fields ARE the
                    # binding — the content address the destination copy
                    # was re-read and re-hashed against, pre-commit
                    # (§2.3's opposite epistemics).
                    envelope["deleted_artifact_id"] = None
                    envelope["deleted_byte_length"] = 0
                    envelope["archived_artifact_id"] = plan["archived_artifact_id"]
                    envelope["archived_byte_length"] = int(
                        plan["archived_byte_length"]
                    )
                    envelope["archive_destination"] = plan["archive_destination"]
                    envelope["archive_verified_at"] = plan["archive_verified_at"]
                else:
                    envelope["deleted_artifact_id"] = artifact_id
                    envelope["deleted_byte_length"] = _artifact_length(
                        self._conn, artifact_id
                    )
                blob = json.dumps(
                    {field: envelope[field] for field in _envelope_fields(outcome)},
                    sort_keys=True,
                ).encode()
                decision_sha256 = hashlib.sha256(blob).hexdigest()
                # The artifact row joins this transaction (the finalise
                # precedent); put_artifact content-addresses, so the id IS
                # the digest.
                decision_artifact_id = self._content.put_artifact(blob, now)
                self._conn.execute(
                    "INSERT INTO dispositions"
                    " (disposition_id, invocation_id, row_kind, target_id,"
                    " context_key, bench, data_class, matched_selector,"
                    " matched_scope, matched_rule, on_disposition,"
                    " anchor_kind, anchor_at, disposal_date, bytes,"
                    " deleted_artifact_id, deleted_byte_length,"
                    " decision_artifact_id, decision_sha256, executed_at,"
                    " outcome, archived_artifact_id, archived_byte_length,"
                    " archive_destination, archive_verified_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
                    " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        disposition_id,
                        invocation_id,
                        envelope["row_kind"],
                        envelope["target_id"],
                        envelope["context_key"],
                        envelope["bench"],
                        envelope["data_class"],
                        envelope["matched_selector"],
                        envelope["matched_scope"],
                        envelope["matched_rule"],
                        envelope["on_disposition"],
                        envelope["anchor_kind"],
                        envelope["anchor_at"],
                        envelope["disposal_date"],
                        envelope["bytes"],
                        envelope["deleted_artifact_id"],
                        envelope["deleted_byte_length"],
                        decision_artifact_id,
                        decision_sha256,
                        envelope["executed_at"],
                        outcome,
                        envelope.get("archived_artifact_id"),
                        envelope.get("archived_byte_length"),
                        envelope.get("archive_destination"),
                        envelope.get("archive_verified_at"),
                    ),
                )
                if plan["row_kind"] == "capture":
                    # Chunks belong to the capture (gone after finalise on
                    # the real path; the abort precedent deletes them
                    # before the row regardless).
                    self._conn.execute(
                        "DELETE FROM capture_chunks WHERE capture_id = ?",
                        (plan["id"],),
                    )
                cursor = self._conn.execute(delete_sql, delete_args)
                if cursor.rowcount != 1:
                    raise StoreChangedUnderPlan(
                        f"dispose: store changed under the plan — guarded "
                        f"delete of {plan['row_kind']} {plan['id']!r} "
                        f"matched {cursor.rowcount} row(s), expected 1"
                    )
                if artifact_id is not None:
                    # Both tiers drop the in-store content artifact: an
                    # archived row's survivor lives offline, and
                    # ``archived_artifact_id`` is a RECORD, never a live
                    # reference — the GC's predicate is unchanged (§2.4).
                    dropped.add(artifact_id)
                if mid_hook is not None:
                    mid_hook(index)
            collected, freed_bytes = self._collect_unreferenced(dropped)
            # The invocation row lands LAST, carrying the complete counts:
            # the transaction is all-or-nothing, so ordering inside it does
            # not change durability — and this keeps the fold's
            # ``artifact_bytes_freed`` in ``counts_json`` without a
            # post-GC UPDATE ("update nothing else" holds: audit rows and
            # deletions are the only writes before this insert).
            self._conn.execute(
                "INSERT INTO disposition_invocations"
                " (invocation_id, invoked_at, actor, policy_path,"
                " policy_sha256, bench_filter, counts_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    invocation_id,
                    now,
                    actor,
                    policy_path,
                    policy_sha256,
                    bench_filter,
                    json.dumps({
                        **counts,
                        "archived": len(archived_rows),
                        **(archive_figures or {
                            "archive_objects_placed": 0,
                            "archive_objects_deduped": 0,
                            "archive_bytes_copied": 0,
                        }),
                        "bytes_reclaimed": bytes_reclaimed,
                        "charged_ledger_bytes": charged_ledger_bytes,
                        "artifact_bytes_freed": freed_bytes,
                    }),
                ),
            )
        except BaseException:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return {
            "invocation_id": invocation_id,
            "deleted": [str(plan["id"]) for plan in selected],
            "archived": [str(plan["id"]) for plan in archived_rows],
            "artifacts_collected": collected,
            "bytes_reclaimed": bytes_reclaimed,
            "charged_ledger_bytes": charged_ledger_bytes,
            "artifact_bytes_freed": freed_bytes,
        }
