"""The core-operations seam: both adapters dispatch here and nowhere else."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from benchweave.content.store import ContentStore
from benchweave.interfaces import errors
from benchweave.interfaces.identity import Identity
from benchweave.state.store import Store

PERMISSION_SCOPES = {
    "observe": "stg:observe",
    "control": "stg:control",
    "admin": "stg:admin",
}
_CURSOR_SECRET = b"wp07-cursor-v1"  # principal-binding only, not an auth secret


def require_permission(identity: Identity, permission: str) -> None:
    scope = PERMISSION_SCOPES[permission]
    if scope not in identity.scopes and "stg:admin" not in identity.scopes:
        raise errors.OperationFailure(
            errors.failure("forbidden", f"missing scope {scope}", retry="never")
        )


def encode_cursor(stream: str, sequence: str, principal: str) -> str:
    payload = json.dumps([stream, sequence, principal]).encode()
    mac = hmac.new(_CURSOR_SECRET, payload, hashlib.sha256).digest()[:8]
    return base64.urlsafe_b64encode(mac + payload).decode()


def decode_cursor(token: str, principal: str) -> tuple[str, str] | None:
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        mac, payload = raw[:8], raw[8:]
        stream, sequence, bound = json.loads(payload)
    except Exception:
        return None
    expected = hmac.new(_CURSOR_SECRET, payload, hashlib.sha256).digest()[:8]
    if not hmac.compare_digest(mac, expected):
        return None
    if bound != principal:
        return None
    return stream, sequence


class Operations:
    def __init__(
        self, store: Store, content: ContentStore, *, gateway_id: str, limits: dict[str, int]
    ) -> None:
        self._store = store
        self._content = content
        self._gateway_id = gateway_id
        self._limits = limits

    # --- observe -------------------------------------------------------------

    def gateway_info(self, identity: Identity) -> dict[str, Any]:
        require_permission(identity, "observe")
        return {
            "gateway_id": self._gateway_id,
            "interface_version": "1.1.0",
            "mcp_version": "2026-07-28",
            "limits": dict(self._limits),
        }

    def bench_list(
        self, identity: Identity, *, limit: int, cursor: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        require_permission(identity, "observe")
        offset = self._cursor_offset(identity.principal, cursor, "benches")
        rows, has_more = self._store.list_benches(limit=limit, offset=offset)
        items = [self._bench_projection(row) for row in rows]
        next_cursor = (
            encode_cursor("benches", str(offset + len(items)), identity.principal)
            if has_more
            else None
        )
        return items, next_cursor

    def bench_get(self, identity: Identity, bench_id: str) -> dict[str, Any]:
        require_permission(identity, "observe")
        row = self._store.get_bench(bench_id)
        if row is None:
            raise errors.OperationFailure(errors.failure("not_found", f"bench {bench_id}"))
        return self._bench_projection(row)

    def device_list(
        self, identity: Identity, bench_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        require_permission(identity, "observe")
        stream = f"devices:{bench_id}"
        offset = self._cursor_offset(identity.principal, cursor, stream)
        rows, has_more = self._store.list_devices(bench_id, limit=limit, offset=offset)
        if not rows and self._store.get_bench(bench_id) is None:
            raise errors.OperationFailure(errors.failure("not_found", f"bench {bench_id}"))
        items = [self._device_projection(row) for row in rows]
        next_cursor = (
            encode_cursor(stream, str(offset + len(items)), identity.principal)
            if has_more
            else None
        )
        return items, next_cursor

    def device_get(self, identity: Identity, bench_id: str, device_id: str) -> dict[str, Any]:
        require_permission(identity, "observe")
        row = self._store.get_device(device_id)
        if row is None or row["bench_id"] != bench_id:
            raise errors.OperationFailure(
                errors.failure("not_found", f"device {device_id} on {bench_id}")
            )
        return self._device_projection(row)

    def document_get(self, identity: Identity, sha256: str) -> dict[str, Any]:
        require_permission(identity, "observe")
        doc = self._content.get_document(sha256)
        if doc is None:
            raise errors.OperationFailure(errors.failure("not_found", f"document {sha256}"))
        return {
            "document": {"id": doc["content"].get("id", sha256),
                         "version": str(doc["content"].get("version", "1")),
                         "sha256": sha256},
            "schema_id": doc["schema_id"],
            "content": doc["content"],
            "original_utf8_base64": base64.b64encode(doc["raw_bytes"]).decode(),
        }

    def artifact_read(
        self, identity: Identity, artifact_id: str, offset: int, length: int
    ) -> dict[str, Any]:
        require_permission(identity, "observe")
        try:
            chunk = self._content.artifact_chunk(artifact_id, offset, length)
        except KeyError:
            raise errors.OperationFailure(
                errors.failure("not_found", f"artifact {artifact_id}")
            ) from None
        return {
            "artifact_id": chunk["artifact_id"],
            "offset": chunk["offset"],
            "bytes": chunk["bytes"],
            "total_bytes": chunk["total_bytes"],
            "sha256": chunk["sha256"],
            "base64": base64.b64encode(chunk["data"]).decode(),
            "eof": chunk["eof"],
        }

    def evidence_get(self, identity: Identity, evidence_id: str) -> dict[str, Any]:
        require_permission(identity, "observe")
        row = self._content.get_evidence(evidence_id)
        if row is None:
            raise errors.OperationFailure(errors.failure("not_found", f"evidence {evidence_id}"))
        return {
            "evidence_id": row["evidence_id"],
            "kind": row["kind"],
            "content_ref": row["content_ref"],
            "artifact_id": row["artifact_id"],
        }

    # --- projections and helpers ---------------------------------------------

    def _bench_projection(self, row: dict[str, Any]) -> dict[str, Any]:
        """Contract bench object; the stored configuration text is the ref source.

        Task 2 rows are storage-shaped (``configuration_json`` etc.) and the
        vendored bench $def is closed (``additionalProperties: false``, no
        licence field), so the seam owns the contract projection.
        """
        configuration_text = row["configuration_json"]
        configuration = json.loads(configuration_text)
        return {
            "bench_id": row["bench_id"],
            "generation": row["generation"],
            "qualification": row["qualification"],
            "tripped": False,
            "busy": self._store.get_active_lease(row["bench_id"]) is not None,
            "configuration": {
                "id": str(configuration.get("id", row["bench_id"])),
                "version": str(configuration.get("version", "1")),
                "sha256": hashlib.sha256(configuration_text.encode()).hexdigest(),
            },
        }

    def _device_projection(self, row: dict[str, Any]) -> dict[str, Any]:
        """Contract device object; descriptor ref from the stored raw text."""
        descriptor_text = row["descriptor_json"]
        descriptor = json.loads(descriptor_text)
        return {
            "device_id": row["device_id"],
            "generation": row["generation"],
            "profiles": json.loads(row["profiles_json"]),
            "descriptor": {
                "id": str(descriptor.get("id", row["device_id"])),
                "version": str(descriptor.get("version", "1")),
                "sha256": hashlib.sha256(descriptor_text.encode()).hexdigest(),
            },
            "identity_state": row["identity_state"],
        }

    def _cursor_offset(self, principal: str, cursor: str | None, stream: str) -> int:
        if cursor is None:
            return 0
        decoded = decode_cursor(cursor, principal)
        if decoded is None or decoded[0] != stream:
            raise errors.OperationFailure(
                errors.failure("invalid_request", "cursor is not valid for this request")
            )
        _, raw = decoded
        return int(raw)
