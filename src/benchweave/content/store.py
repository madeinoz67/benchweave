"""Content-addressed document/artifact/evidence storage over the WP03 store.

Lives beside json_document (the loader/verifier): this module stores and
serves; json_document proves bytes. All writes run under the caller-held
write gate on the store's single writer connection.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from benchweave.host.services import HostServices, QuotaState
from benchweave.state.store import Store

MAX_CHUNK_BYTES = 65536


class EvidenceQuotaExceeded(RuntimeError):
    """Context-keyed evidence entries reached the configured quota.

    Instances raised by a capture-services bundle carry ``writer_stamp``
    (the bundle-originated record the bridge's non-poisoning
    classification catches require); the bare class keeps its old shape.
    """

    writer_stamp: object | None = None


class ContentStore:
    """Stores and serves rows on the store v2 content tables.

    Documents and artifacts are content-addressed (the id is a type tag plus
    the digest of the bytes, so re-putting identical bytes is a no-op);
    evidence rows are one-per-retention so the per-context quota counts
    retentions, not distinct contents. All ids match the contract id shape
    ^[a-z][a-z0-9_.-]*$ (no colons).
    """

    def __init__(self, store: Store) -> None:
        self._conn: sqlite3.Connection = store.connection

    # --- documents ---------------------------------------------------------

    def put_document(
        self, raw: bytes, sha256: str, content: dict[str, Any], schema_id: str, now: str
    ) -> None:
        digest = hashlib.sha256(raw).hexdigest()
        if digest != sha256:
            raise ValueError(f"document bytes do not hash to {sha256}")
        self._conn.execute(
            "INSERT OR REPLACE INTO documents"
            " (sha256, raw_bytes, content_json, schema_id, stored_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (sha256, raw, json.dumps(content, sort_keys=True), schema_id, now),
        )

    def get_document(self, sha256: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT raw_bytes, content_json, schema_id FROM documents WHERE sha256 = ?",
            (sha256,),
        ).fetchone()
        if row is None:
            return None
        return {
            "sha256": sha256,
            "raw_bytes": row[0],
            "content": json.loads(row[1]),
            "schema_id": row[2],
        }

    # --- artifacts -----------------------------------------------------------

    def put_artifact(self, data: bytes, now: str) -> str:
        # Contract id shape ^[a-z][a-z0-9_.-]*$ forbids colons: tag, not scheme.
        artifact_id = "art-" + hashlib.sha256(data).hexdigest()
        self._conn.execute(
            "INSERT OR REPLACE INTO artifacts (artifact_id, data, stored_at) VALUES (?, ?, ?)",
            (artifact_id, data, now),
        )
        return artifact_id

    def artifact_chunk(self, artifact_id: str, offset: int, length: int) -> dict[str, Any]:
        if length < 1:
            raise ValueError("length must be >= 1")
        # Interface contract clamps (never rejects) lengths above the chunk
        # ceiling, so callers can pass a page size unconditionally.
        length = min(length, MAX_CHUNK_BYTES)
        row = self._conn.execute(
            "SELECT data FROM artifacts WHERE artifact_id = ?", (artifact_id,)
        ).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        data = row[0]
        # D11 (interface contract §8): "At EOF an offset equal to size
        # yields zero bytes; offsets beyond size fail." Python slicing would
        # silently clamp a beyond-size offset to the empty tail — the seam
        # maps this ValueError to invalid_request.
        if offset > len(data):
            raise ValueError(
                f"offset {offset} is beyond the artifact size {len(data)}"
            )
        window = data[offset : offset + length]
        return {
            "artifact_id": artifact_id,
            "offset": offset,
            "bytes": len(window),
            "total_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "data": window,
            "eof": offset + len(window) >= len(data),
        }

    # --- evidence --------------------------------------------------------------

    def put_evidence(
        self,
        kind: str,
        content_ref: dict[str, Any],
        artifact_id: str | None,
        context_key: str | None,
        now: str,
        *,
        quota: int | None = None,
    ) -> str:
        if quota is not None and context_key is not None:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE context_key = ?", (context_key,)
            ).fetchone()[0]
            if count >= quota:
                raise EvidenceQuotaExceeded(
                    f"evidence quota {quota} reached for {context_key!r}"
                )
        # One evidence id per retention: the quota counts retentions per
        # context key, so identical payloads must still occupy distinct rows.
        # Content addressing lives in artifact_id and content_ref's digest.
        evidence_id = "ev-" + uuid.uuid4().hex
        self._conn.execute(
            "INSERT OR REPLACE INTO evidence"
            " (evidence_id, kind, content_ref_json, artifact_id, context_key, stored_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                evidence_id,
                kind,
                json.dumps(content_ref, sort_keys=True),
                artifact_id,
                context_key,
                now,
            ),
        )
        return evidence_id

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT kind, content_ref_json, artifact_id, context_key FROM evidence"
            " WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "evidence_id": evidence_id,
            "kind": row[0],
            "content_ref": json.loads(row[1]),
            "artifact_id": row[2],
            "context_key": row[3],
        }


class RetainingServices(HostServices):
    """The real HostServices evidence implementation (retain_evidence).

    Explicitly inherits the protocol so mypy pins full conformance here.
    Only retain_evidence is live in this slice; the remaining members raise
    loudly (never silently no-op) until their owning slices land.
    """

    def __init__(self, content: ContentStore, *, quota: int, now: str) -> None:
        self._content = content
        self._quota = quota
        self._now = now

    def retain_evidence(self, key: str, payload: object) -> str:
        blob = json.dumps(payload, sort_keys=True, default=str).encode()
        artifact_id = self._content.put_artifact(blob, self._now)
        ref = {"id": key, "version": "1", "sha256": hashlib.sha256(blob).hexdigest()}
        return self._content.put_evidence(
            "dataset", ref, artifact_id, key, self._now, quota=self._quota
        )

    def resolve_content(self, content_id: str) -> bytes:
        raise NotImplementedError(
            f"resolve_content ({content_id!r}) is not part of the retention slice"
        )

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        raise NotImplementedError(f"emit_event ({kind!r}) is not part of the retention slice")

    def quota_state(self) -> QuotaState:
        raise NotImplementedError("quota_state is not part of the retention slice")

    def register_reading_sink(self, sink: Any) -> None:
        raise NotImplementedError("register_reading_sink is not part of the retention slice")
