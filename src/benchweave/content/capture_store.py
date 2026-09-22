"""The staged-append capture writer (issue #43 slice 1, Decision 3).

``ContentStore.put_artifact`` is whole-blob and content-addressed — you
cannot append to an ``art-<sha256>`` row that does not exist yet. This
module is the designed staged writer over the v5 capture-staging tables:
chunked appends under a per-capture reservation, an incremental in-memory
digest as chunks arrive, and a finalise that is ONE explicit transaction
(artifact insert → staging flip → chunk deletes) publishing the
content-addressed row through the store's own id construction.

All writes run on the store's single writer connection under the
caller-held write gate (the ContentStore precedent). One instance per
session, injected into both the composing services bundle and the bridge
controller; the startup sweep constructs its own, without a quota envelope
(it only reclaims).

The G3 allowance formula (the record's Decision 3, verbatim): refuse an
open iff ``max_bytes > min(max_capture_bytes, max_dataset_bytes − used)``,
where ``used`` is Σ reserved over staged + Σ charged over finalised rows
for the context key — ``used`` appears ONLY in the dataset term.

Every exception this writer raises is writer-stamped (``writer_stamp``):
the bridge's non-poisoning classification catches require the stamp, so a
bare raise of the same class from adapter code keeps the poison posture.
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from benchweave.content.store import ContentStore
from benchweave.host.types import CaptureFinaliseRejected, CaptureQuotaExceeded
from benchweave.state.store import Store

_STATE_STAGED = "staged"
_STATE_FINALISED = "finalised"
_STATE_ABORTED = "aborted"


class CaptureStagingStore:
    """Staged capture lifecycle over the v5 tables.

    States: ``staged`` from open, ``finalised`` by finalise (the row stays —
    it carries the charged-bytes ledger and the capture→artifact linkage),
    ``aborted`` transiently inside the crash-recovery sweep; a normal-path
    abort deletes chunks and entry in one transaction. The vocabulary is
    code-enforced (no CHECK constraint — the migration chain carries zero
    CHECKs and SQLite cannot ALTER one without a table rebuild).
    """

    def __init__(
        self,
        store: Store,
        *,
        max_capture_bytes: int | None = None,
        max_dataset_bytes: int | None = None,
    ) -> None:
        self._conn = store.connection
        self._content = ContentStore(store)
        self._max_capture_bytes = max_capture_bytes
        self._max_dataset_bytes = max_dataset_bytes
        # C3: the stamp every writer-raised exception carries. A unique
        # object per writer instance; classification catches require it.
        self._stamp = object()
        self._hashers: dict[str, Any] = {}

    # --- internal helpers ---------------------------------------------------

    def _reject(self, exception: CaptureFinaliseRejected) -> CaptureFinaliseRejected:
        exception.writer_stamp = self._stamp
        return exception

    def _quota(self, exception: CaptureQuotaExceeded) -> CaptureQuotaExceeded:
        exception.writer_stamp = self._stamp
        return exception

    def _restamp(self, exception: BaseException) -> None:
        """Stamp a writer-originated ``sqlite3.OperationalError`` (B1/C2):
        lock contention is a resource condition the bridge classifies —
        but only when the record proves the writer raised it."""
        if isinstance(exception, sqlite3.OperationalError):
            exception.writer_stamp = self._stamp  # type: ignore[attr-defined]

    def _staged_row(self, capture_id: str) -> tuple[Any, ...] | None:
        found: tuple[Any, ...] | None = self._conn.execute(
            "SELECT context_key, state, reserved_bytes, format, sample_count"
            " FROM capture_staging WHERE capture_id = ?",
            (capture_id,),
        ).fetchone()
        return found

    # --- open ----------------------------------------------------------------

    def open_capture(
        self,
        *,
        capture_id: str,
        context_key: str,
        fmt: str,
        sample_count: int | None,
        max_bytes: int,
        now: str,
    ) -> None:
        """Reserve and open a capture under BEGIN IMMEDIATE (check-then-
        reserve is atomic), refusing quota per the record's G3 formula."""
        if self._max_capture_bytes is None or self._max_dataset_bytes is None:
            raise RuntimeError(
                "capture quota envelope not configured for this writer: "
                "max_capture_bytes and max_dataset_bytes are required at "
                "every construction site that opens captures"
            )
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            # The BEGIN itself can lose the lock race — stamp it too (the
            # writer-originated record the bridge's classification reads).
            self._restamp(error)
            raise
        try:
            existing = self._conn.execute(
                "SELECT 1 FROM capture_staging WHERE capture_id = ?", (capture_id,)
            ).fetchone()
            if existing is not None:
                raise self._reject(
                    CaptureFinaliseRejected(
                        f"capture id already exists: {capture_id!r}"
                    )
                )
            used = self._used_bytes_locked(context_key)
            allowance = min(
                self._max_capture_bytes, self._max_dataset_bytes - used
            )
            if max_bytes > allowance:
                raise self._quota(
                    CaptureQuotaExceeded(
                        f"capture allowance {allowance} bytes exceeded for "
                        f"{context_key!r}: requested {max_bytes} "
                        f"(min(max_capture_bytes={self._max_capture_bytes}, "
                        f"max_dataset_bytes−used={self._max_dataset_bytes}−{used}))"
                    )
                )
            self._conn.execute(
                "INSERT INTO capture_staging"
                " (capture_id, context_key, state, reserved_bytes, charged_bytes,"
                " format, sample_count, artifact_id, started_at, created_at,"
                " updated_at)"
                " VALUES (?, ?, ?, ?, 0, ?, ?, NULL, ?, ?, ?)",
                (
                    capture_id,
                    context_key,
                    _STATE_STAGED,
                    max_bytes,
                    fmt,
                    sample_count,
                    now,
                    now,
                    now,
                ),
            )
        except BaseException as error:
            self._restamp(error)
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        # B3: ALWAYS (re)initialise the hasher entry for this id — a
        # reused-after-abort id starts a fresh digest, never a stale one.
        self._hashers[capture_id] = hashlib.sha256()

    def _used_bytes_locked(self, context_key: str) -> int:
        """Σ reserved over staged + Σ charged over finalised (the record's
        ``used``; aborted rows are excluded from both terms, so the sweep's
        mark transaction alone refunds the ledger)."""
        reserved = self._conn.execute(
            "SELECT COALESCE(SUM(reserved_bytes), 0) FROM capture_staging"
            " WHERE context_key = ? AND state = ?",
            (context_key, _STATE_STAGED),
        ).fetchone()[0]
        charged = self._conn.execute(
            "SELECT COALESCE(SUM(charged_bytes), 0) FROM capture_staging"
            " WHERE context_key = ? AND state = ?",
            (context_key, _STATE_FINALISED),
        ).fetchone()[0]
        return int(reserved) + int(charged)

    # --- append ---------------------------------------------------------------

    def staged_bytes(self, capture_id: str) -> int:
        """Bytes staged so far for a capture (the append-path truth)."""
        found = self._conn.execute(
            "SELECT COALESCE(SUM(byte_length), 0) FROM capture_chunks"
            " WHERE capture_id = ?",
            (capture_id,),
        ).fetchone()
        return int(found[0])

    def staged_capture(self, capture_id: str) -> dict[str, Any] | None:
        """The staged (open) capture's row: format and declared sample_count,
        the host-side authority the manifest's echo fields derive from —
        None when the id is unknown or no longer staged."""
        found = self._conn.execute(
            "SELECT format, sample_count, reserved_bytes FROM capture_staging"
            " WHERE capture_id = ? AND state = ?",
            (capture_id, _STATE_STAGED),
        ).fetchone()
        if found is None:
            return None
        return {
            "format": found[0],
            "sample_count": found[1],
            "reserved_bytes": int(found[2]),
        }

    def append(self, capture_id: str, data: bytes, context_key: str) -> None:
        """Append one ordered chunk under the capture's reservation."""
        if not data:
            raise self._reject(
                CaptureFinaliseRejected("empty append refused (A4 parity)")
            )
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            # The BEGIN itself can lose the lock race — stamp it too (the
            # writer-originated record the bridge's classification reads).
            self._restamp(error)
            raise
        try:
            staged = self._staged_row(capture_id)
            if staged is None:
                raise self._reject(
                    CaptureFinaliseRejected(f"unknown capture id: {capture_id!r}")
                )
            row_context, state, reserved, _fmt, _count = staged
            if state != _STATE_STAGED:
                raise self._reject(
                    CaptureFinaliseRejected(
                        f"capture {capture_id!r} is terminal ({state}): "
                        "appends are refused"
                    )
                )
            if row_context != context_key:
                raise self._reject(
                    CaptureFinaliseRejected(
                        f"wrong session for capture {capture_id!r}: "
                        f"opened by {row_context!r}, append from {context_key!r}"
                    )
                )
            already = self.staged_bytes(capture_id)
            if already + len(data) > int(reserved):
                raise self._quota(
                    CaptureQuotaExceeded(
                        f"capture reservation exceeded for {capture_id!r}: "
                        f"{already} + {len(data)} > {reserved} bytes"
                    )
                )
            seq = self._conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 FROM capture_chunks"
                " WHERE capture_id = ?",
                (capture_id,),
            ).fetchone()[0]
            self._conn.execute(
                "INSERT INTO capture_chunks (capture_id, seq, data, byte_length)"
                " VALUES (?, ?, ?, ?)",
                (capture_id, int(seq), data, len(data)),
            )
        except BaseException as error:
            self._restamp(error)
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        hasher = self._hashers.get(capture_id)
        if hasher is not None:
            hasher.update(data)

    # --- finalise ---------------------------------------------------------------

    def finalise(self, capture_id: str, now: str) -> dict[str, Any]:
        """Publish the capture as one explicit transaction (A2).

        Under BEGIN IMMEDIATE: read the ordered chunks, cross-check the
        running in-memory digest against a streaming recompute (store
        corruption refuses publication), validate the byte count against
        the declared sample_count (spec §7: byte length equals
        sample_count×8), insert the content-addressed artifact row
        (participating in this transaction), flip the staging row to
        ``finalised`` with ``charged_bytes`` and ``artifact_id``, delete
        the chunk rows, COMMIT.
        """
        hasher = self._hashers.get(capture_id)
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            # The BEGIN itself can lose the lock race — stamp it too (the
            # writer-originated record the bridge's classification reads).
            self._restamp(error)
            raise
        try:
            staged = self._staged_row(capture_id)
            if staged is None:
                raise self._reject(
                    CaptureFinaliseRejected(f"unknown capture id: {capture_id!r}")
                )
            _context, state, _reserved, fmt, sample_count = staged
            if state != _STATE_STAGED:
                raise self._reject(
                    CaptureFinaliseRejected(
                        f"capture {capture_id!r} is terminal ({state}): "
                        "finalise is refused"
                    )
                )
            if hasher is None:
                # A staged row whose writer session died: the startup sweep
                # owns reclamation, never publication.
                raise self._reject(
                    CaptureFinaliseRejected(
                        f"capture {capture_id!r} has no live digest in this "
                        "writer session (restarted mid-capture?)"
                    )
                )
            recompute = hashlib.sha256()
            payload = bytearray()
            for chunk in self._conn.execute(
                "SELECT data FROM capture_chunks WHERE capture_id = ?"
                " ORDER BY seq",
                (capture_id,),
            ).fetchall():
                recompute.update(bytes(chunk[0]))
                payload.extend(bytes(chunk[0]))
            digest = recompute.hexdigest()
            if digest != hasher.hexdigest():
                raise self._reject(
                    CaptureFinaliseRejected(
                        f"digest cross-check failed for {capture_id!r}: stored "
                        "bytes do not hash to the running capture digest"
                    )
                )
            byte_length = len(payload)
            if byte_length == 0:
                raise self._reject(
                    CaptureFinaliseRejected(
                        f"zero-byte finalise refused for {capture_id!r}: "
                        "failed/incomplete captures are aborted, not published"
                    )
                )
            if (
                fmt == "waveform_f64le"
                and sample_count is not None
                and byte_length != int(sample_count) * 8
            ):
                raise self._reject(
                    CaptureFinaliseRejected(
                        f"short capture {capture_id!r}: {byte_length} bytes "
                        f"staged but sample_count {sample_count} declares "
                        f"{int(sample_count) * 8} (spec §7: byte length "
                        "equals sample_count×8)"
                    )
                )
            # The artifact row joins this transaction (same connection).
            artifact_id = self._content.put_artifact(bytes(payload), now)
            self._conn.execute(
                "UPDATE capture_staging SET state = ?, charged_bytes = ?,"
                " artifact_id = ?, updated_at = ? WHERE capture_id = ?",
                (_STATE_FINALISED, byte_length, artifact_id, now, capture_id),
            )
            self._conn.execute(
                "DELETE FROM capture_chunks WHERE capture_id = ?", (capture_id,)
            )
        except BaseException as error:
            self._restamp(error)
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        # B3: finalise removes the hasher entry.
        self._hashers.pop(capture_id, None)
        return {
            "artifact_id": artifact_id,
            "sha256": digest,
            "byte_length": byte_length,
        }

    def finalise_record(self, capture_id: str) -> dict[str, Any] | None:
        """The writer's published record for a finalised capture (G4's
        cross-check source), or None when unknown or not finalised."""
        found = self._conn.execute(
            "SELECT artifact_id, charged_bytes, format, sample_count"
            " FROM capture_staging WHERE capture_id = ? AND state = ?",
            (capture_id, _STATE_FINALISED),
        ).fetchone()
        if found is None:
            return None
        artifact_id = str(found[0])
        return {
            "artifact_id": artifact_id,
            "sha256": artifact_id.removeprefix("art-"),
            "byte_length": int(found[1]),
            "format": found[2],
            "sample_count": found[3],
        }

    # --- abort -----------------------------------------------------------------

    def abort(self, capture_id: str) -> bool:
        """Delete chunks and entry in ONE transaction (§0.4: R2's zero
        staging rows holds literally). A no-op (False) for unknown ids and
        after finalise — the no-op-retract pin: a published capture
        stands."""
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            # The BEGIN itself can lose the lock race — stamp it too (the
            # writer-originated record the bridge's classification reads).
            self._restamp(error)
            raise
        try:
            staged = self._staged_row(capture_id)
            if staged is None or staged[1] != _STATE_STAGED:
                self._conn.execute("ROLLBACK")
                return False
            self._conn.execute(
                "DELETE FROM capture_chunks WHERE capture_id = ?", (capture_id,)
            )
            self._conn.execute(
                "DELETE FROM capture_staging WHERE capture_id = ?", (capture_id,)
            )
        except BaseException as error:
            self._restamp(error)
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        # B3: abort removes the hasher entry.
        self._hashers.pop(capture_id, None)
        return True

    # --- the crash-recovery sweep -------------------------------------------------

    def reclaim_orphans(self, now: str) -> list[str]:
        """Reclaim staging orphaned by host death, in TWO transactions.

        tx1 marks ``staged`` → ``aborted`` (the durable forensic record —
        and the refund: ``used`` excludes aborted rows, so tx1 alone frees
        the quota even if tx2 dies). tx2 deletes the marked rows
        (idempotent — a later sweep completes it). NEVER collapse the two
        transactions into one: the mark-time refund is the property that
        bounds the quota-hostage window to one startup.
        """
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            # The BEGIN itself can lose the lock race — stamp it too (the
            # writer-originated record the bridge's classification reads).
            self._restamp(error)
            raise
        try:
            rows = self._conn.execute(
                "SELECT capture_id FROM capture_staging WHERE state = ?",
                (_STATE_STAGED,),
            ).fetchall()
            ids = [str(row[0]) for row in rows]
            for capture_id in ids:
                self._conn.execute(
                    "UPDATE capture_staging SET state = ?, updated_at = ?"
                    " WHERE capture_id = ?",
                    (_STATE_ABORTED, now, capture_id),
                )
        except BaseException as error:
            self._restamp(error)
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        self._delete_aborted_rows()
        for capture_id in ids:
            self._hashers.pop(capture_id, None)
        return ids

    def _delete_aborted_rows(self) -> None:
        """tx2: delete EVERY aborted row (idempotent by state filter).

        Not only this run's marked ids: a process death between tx1 and
        tx2 leaves aborted rows behind, and the next sweep's tx1 marks
        nothing — deleting by state, not by id list, is what makes the
        sweep complete a predecessor's interrupted reclamation.
        """
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as error:
            # The BEGIN itself can lose the lock race — stamp it too (the
            # writer-originated record the bridge's classification reads).
            self._restamp(error)
            raise
        try:
            self._conn.execute(
                "DELETE FROM capture_chunks WHERE capture_id IN"
                " (SELECT capture_id FROM capture_staging WHERE state = ?)",
                (_STATE_ABORTED,),
            )
            self._conn.execute(
                "DELETE FROM capture_staging WHERE state = ?", (_STATE_ABORTED,)
            )
        except BaseException as error:
            self._restamp(error)
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    # --- the ledger ---------------------------------------------------------------

    def used_bytes(self, context_key: str) -> int:
        """The capture-byte ledger read for a context key."""
        return self._used_bytes_locked(context_key)
