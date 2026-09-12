"""The core-operations seam: both adapters dispatch here and nowhere else."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from benchweave.content.store import ContentStore
from benchweave.control.clocking import SystemClock
from benchweave.control.coordinator import _iso_plus_ms
from benchweave.interfaces import errors
from benchweave.interfaces.identity import Identity
from benchweave.state.store import Conflict, Lease, LeaseNotActive, Store

if TYPE_CHECKING:
    from benchweave.interfaces.worker import RunWorker

PERMISSION_SCOPES = {
    "observe": "stg:observe",
    "control": "stg:control",
    "admin": "stg:admin",
}
# Permission tiers are a hierarchy: a permission name is the MINIMUM tier.
# An identity passes iff it holds any scope at or above that tier
# (observe ⊆ control ⊆ admin).
TIER_SATISFIES: dict[str, frozenset[str]] = {
    "observe": frozenset({"stg:observe", "stg:control", "stg:admin"}),
    "control": frozenset({"stg:control", "stg:admin"}),
    "admin": frozenset({"stg:admin"}),
}
_CURSOR_SECRET = b"wp07-cursor-v1"  # principal-binding only, not an auth secret


def require_permission(identity: Identity, permission: str) -> None:
    if identity.scopes.isdisjoint(TIER_SATISFIES[permission]):
        raise errors.OperationFailure(
            errors.failure(
                "forbidden", f"missing scope {PERMISSION_SCOPES[permission]}", retry="never"
            )
        )


def scoped_request_key(principal: str, operation: str, request_id: str) -> str:
    """§9 request scoping: identical request ids in different principal
    namespaces (or under different operations) never collide."""
    return hashlib.sha256(f"{principal}|{operation}|{request_id}".encode()).hexdigest()


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


def append_bench_event(
    store: Store,
    kind: str,
    bench_id: str,
    run_id: str | None,
    evidence: dict[str, Any] | None = None,
    *,
    keep: int | None,
    now_iso: Callable[[], str],
) -> None:
    """Append one bench-stream event and apply retention (Task 6).

    Shared by the seam (main-thread store) and the run worker (its own
    thread-affine store) so both writers produce the identical envelope
    under the same seven-kind fence. ``keep`` is the per-stream retention
    window; ``None`` appends untrimmed — the next seam-side emit re-trims.
    """
    if kind not in Operations.EVENT_KINDS:
        raise ValueError(f"unknown event kind {kind!r}")
    stream_id = f"bench:{bench_id}"
    envelope = {
        "stream_id": stream_id,
        "at": now_iso(),
        "kind": kind,
        "run_id": run_id,
        "evidence": evidence or {},
    }
    store.append_event(stream_id, envelope)
    if keep is not None:
        store.trim_stream(stream_id, keep)


class Operations:
    EVENT_KINDS = {
        "run_changed", "lease_changed", "bench_changed", "trip",
        "authority_changed", "registry_status_changed", "evidence_gap",
    }
    def __init__(
        self,
        store: Store,
        content: ContentStore,
        *,
        gateway_id: str,
        limits: dict[str, int],
        worker: RunWorker | None = None,
        now_iso: Callable[[], str] | None = None,
    ) -> None:
        self._store = store
        self._content = content
        self._gateway_id = gateway_id
        self._limits = limits
        self._worker = worker
        self._now_iso = now_iso if now_iso is not None else SystemClock().now_iso

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

    def events_get(
        self, identity: Identity, bench_id: str, *, after: str | None, limit: int
    ) -> dict[str, Any]:
        """Bench event stream read (observe): principal-bound cursor
        paging with honest watermarks. A cursor the retention window has
        overtaken is ``cursor_expired`` — never a silent truncation."""
        require_permission(identity, "observe")
        stream = f"bench:{bench_id}"
        oldest, current = self._store.stream_watermarks(stream)
        if oldest is None and self._store.get_bench(bench_id) is None:
            raise errors.OperationFailure(errors.failure("not_found", f"bench {bench_id}"))
        after_sequence: str | None = None
        if after is not None:
            decoded = decode_cursor(after, identity.principal)
            if decoded is None or decoded[0] != stream:
                raise errors.OperationFailure(
                    errors.failure("invalid_request", "cursor does not address this stream")
                )
            try:
                after_int = int(decoded[1])
            except ValueError:
                raise errors.OperationFailure(
                    errors.failure("invalid_request", "cursor sequence is not numeric")
                ) from None
            if oldest is not None and after_int < int(oldest) - 1:
                raise errors.OperationFailure(errors.failure(
                    "cursor_expired", f"retention overtook sequence {decoded[1]}"))
            after_sequence = decoded[1]
        events = self._store.read_events_after(stream, after_sequence, limit)
        cursor = (
            encode_cursor(stream, str(int(events[-1]["sequence"])), identity.principal)
            if events
            else (after or encode_cursor(stream, "0", identity.principal))
        )
        return {
            "events": events,
            "cursor": cursor,
            "stream_id": stream,
            "oldest_sequence": oldest or "0",
            "current_sequence": current or "0",
        }

    # --- control: runs ---------------------------------------------------------

    def run_check(
        self, identity: Identity, bench_id: str, binding_ref: dict[str, Any]
    ) -> dict[str, Any]:
        """Advisory preflight (interface-v1.1.0 run_check): does the stored
        binding document name this bench, and are its pinned documents
        present? No reservation, no device I/O; never an admission token."""
        require_permission(identity, "control")
        bench = self._store.get_bench(bench_id)
        if bench is None:
            raise errors.OperationFailure(errors.failure("not_found", f"bench {bench_id}"))
        findings: list[dict[str, str]] = []
        sha = str(binding_ref.get("sha256", ""))
        document = self._content.get_document(sha) if sha else None
        if document is None:
            findings.append(
                {
                    "field": "binding_ref.sha256",
                    "reason": f"binding document {sha} is not stored",
                }
            )
        else:
            binding = document["content"]
            named = str(binding.get("bench", {}).get("id", ""))
            if named != bench_id:
                findings.append(
                    {
                        "field": "binding.bench.id",
                        "reason": f"binding names bench {named!r}, not {bench_id!r}",
                    }
                )
            for logical in ("procedure", "bench", "policy", "commissioning"):
                # package_lock is pinned by the binding but deliberately not
                # admitted to the content store (bootstrap contract); the
                # spooling build_run (Task 8) resolves it from disk.
                pin = binding.get(logical)
                if not isinstance(pin, dict):
                    findings.append(
                        {"field": f"binding.{logical}", "reason": "pin is missing"}
                    )
                    continue
                pin_sha = str(pin.get("sha256", ""))
                if not self._content.get_document(pin_sha):
                    findings.append(
                        {
                            "field": f"binding.{logical}.sha256",
                            "reason": f"pinned document {pin_sha} is not stored",
                        }
                    )
        return {
            "valid": not findings,
            # Report the same canonical authority the run_start fence reads.
            "generation": self._store.current_generation(bench_id),
            "findings": findings,
        }

    def run_start(
        self,
        identity: Identity,
        bench_id: str,
        request_id: str,
        binding_ref: dict[str, Any],
        expected_generation: int,
        lease_id: str | None,
    ) -> dict[str, Any]:
        """Accept a run and enqueue it; returns the contract ``run`` in state
        ``accepted`` (202-accept semantics).

        §9 idempotency: the key is scoped to principal + operation + request
        id, and the request body is the binding pin — a replay returns the
        original run and NEVER enqueues again; the same key with a different
        binding is a conflict. ``lease_id`` names a pre-held lease for
        commissioned takeover (Task 7); it takes no part in acceptance.
        """
        require_permission(identity, "control")
        if self._store.get_bench(bench_id) is None:
            raise errors.OperationFailure(errors.failure("not_found", f"bench {bench_id}"))
        # Decision 4: the generations table is the canonical authority — the
        # bench row's copy can lag a bare bump until Task 7 syncs them.
        generation = self._store.current_generation(bench_id)
        if expected_generation != generation:
            raise errors.OperationFailure(
                errors.failure(
                    "conflict",
                    f"bench {bench_id} is at generation {generation},"
                    f" not {expected_generation}",
                )
            )
        if self._worker is None:
            raise errors.OperationFailure(
                errors.failure("not_ready", "no run worker is configured on this gateway")
            )
        now = self._now_iso()
        run_id = f"run-{uuid.uuid4().hex[:16]}"
        key = scoped_request_key(identity.principal, "run_start", request_id)
        # The idempotent request body is the whole binding pin: any change to
        # id, version OR digest is a different body (same key → conflict).
        body_sha = hashlib.sha256(
            json.dumps(binding_ref, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        try:
            accepted = self._store.accept_request(key, body_sha, run_id, now)
        except Conflict:
            raise errors.OperationFailure(
                errors.failure(
                    "conflict", f"request_id {request_id!r} reused with a different binding"
                )
            ) from None
        if accepted.outcome == "duplicate":
            return self._run_projection(accepted.run_id)  # replay: never enqueue
        self._store.create_run(
            run_id,
            binding={
                "id": str(binding_ref.get("id", "")),
                "version": str(binding_ref.get("version", "")),
                "sha256": body_sha,
            },
            principal_id=identity.principal,
            now=now,
        )
        self._store.put_run_state(run_id, bench_id, "accepted", now)
        # Read the projection BEFORE submitting: the worker races this call
        # to flip the state to "running", and 202 semantics return "accepted".
        projection = self._run_projection(run_id)
        self._worker.submit(run_id, identity.principal, binding_ref, bench_id)
        self._emit("run_changed", bench_id, run_id)
        return projection

    def run_get(self, identity: Identity, run_id: str) -> dict[str, Any]:
        require_permission(identity, "control")
        return self._run_projection(run_id)

    def run_find(self, identity: Identity, request_id: str) -> dict[str, Any]:
        """§9: the lookup is principal-scoped — replaying another
        principal's request id can never discover their runs."""
        require_permission(identity, "control")
        key = scoped_request_key(identity.principal, "run_start", request_id)
        request = self._store.find_request(key)
        if request is None:
            raise errors.OperationFailure(
                errors.failure("not_found", f"no run accepted for request {request_id!r}")
            )
        return self._run_projection(str(request["run_id"]))

    def run_cancel(
        self, identity: Identity, run_id: str, request_id: str, reason: str
    ) -> dict[str, Any]:
        """Request cancellation, honoured by the coordinator at its next
        monitor tick while the body is still dispatchable (§5: cancellation
        never suppresses the safe transition). The coordinator API takes
        run and principal only — this wraps it and records the caller's
        reason and request id in the run_changed event."""
        require_permission(identity, "control")
        if self._store.get_run(run_id) is None:
            raise errors.OperationFailure(errors.failure("not_found", f"run {run_id}"))
        if self._worker is not None:
            self._worker.cancel(run_id, identity.principal)
        state = self._store.get_run_state(run_id)
        if state is not None:
            # A run row without a queue state has no bench to name; a
            # bench-less event would mint a junk ``bench:`` stream.
            self._emit(
                "run_changed",
                state["bench_id"],
                run_id,
                evidence={"reason": reason, "request_id": request_id},
            )
        return self._run_projection(run_id)

    # --- control: leases --------------------------------------------------------

    def lease_create(
        self,
        identity: Identity,
        bench_id: str,
        request_id: str,
        expected_generation: int,
        duration_ms: int,
    ) -> dict[str, Any]:
        """Mint a bench lease (holder = principal; fencing sequence from the
        store's per-bench authority). The lease id is derived from the §9
        scoped key, so one request id names one lease identity; renewal
        re-issues the SAME id at a new sequence."""
        require_permission(identity, "control")
        bench = self._store.get_bench(bench_id)
        if bench is None:
            raise errors.OperationFailure(errors.failure("not_found", f"bench {bench_id}"))
        # Same canonical fence as run_start (Decision 4).
        generation = self._store.current_generation(bench_id)
        if expected_generation != generation:
            raise errors.OperationFailure(
                errors.failure(
                    "conflict",
                    f"bench {bench_id} is at generation {generation},"
                    f" not {expected_generation}",
                )
            )
        now = self._now_iso()
        lease_id = (
            f"lease-{scoped_request_key(identity.principal, 'lease_create', request_id)[:16]}"
        )
        lease = self._store.next_lease(
            bench_id,
            lease_id,
            holder=identity.principal,
            expires_at=_iso_plus_ms(now, duration_ms),
        )
        self._emit("lease_changed", bench_id, lease.lease_id,
                   evidence={"request_id": request_id})
        return self._lease_projection(lease)

    def lease_renew(
        self,
        identity: Identity,
        lease_id: str,
        request_id: str,
        sequence: int,
        duration_ms: int,
    ) -> dict[str, Any]:
        """Re-issue a lease's expiry at a new fencing sequence. Same holder
        only until Task 7 reads the commissioning doc for takeover roles;
        a stale sequence is a conflict (the caller's lease view is fenced)."""
        require_permission(identity, "control")
        lease = self._find_lease(lease_id)
        if lease is None or lease.state != "active":
            raise errors.OperationFailure(errors.failure("not_found", f"lease {lease_id}"))
        if lease.holder != identity.principal:
            raise errors.OperationFailure(
                errors.failure("forbidden", "only the lease holder may renew")
            )
        if lease.sequence != sequence:
            raise errors.OperationFailure(
                errors.failure(
                    "conflict",
                    f"lease {lease_id} is at sequence {lease.sequence}, not {sequence}",
                )
            )
        now = self._now_iso()
        successor = self._store.next_lease(
            lease.bench_id,
            lease.lease_id,
            holder=lease.holder,
            expires_at=_iso_plus_ms(now, duration_ms),
        )
        self._store.release_lease(lease.bench_id, lease.sequence, now)
        self._emit("lease_changed", lease.bench_id, lease.lease_id,
                   evidence={"request_id": request_id})
        return self._lease_projection(successor)

    def lease_release(
        self, identity: Identity, lease_id: str, request_id: str, reason: str
    ) -> dict[str, Any]:
        """Release a lease. Releasing during a live run needs no special
        code here: the WP05 monitor already ends the body as ``cancelled``
        on lease loss at its next tick."""
        require_permission(identity, "control")
        lease = self._find_lease(lease_id)
        if lease is None:
            raise errors.OperationFailure(errors.failure("not_found", f"lease {lease_id}"))
        if lease.holder != identity.principal:
            raise errors.OperationFailure(
                errors.failure("forbidden", "only the lease holder may release")
            )
        try:
            self._store.release_lease(lease.bench_id, lease.sequence, self._now_iso())
        except LeaseNotActive:
            raise errors.OperationFailure(
                errors.failure("not_found", f"lease {lease_id} is not active")
            ) from None
        self._emit(
            "lease_changed",
            lease.bench_id,
            lease.lease_id,
            evidence={"reason": reason, "request_id": request_id},
        )
        return self._lease_projection(replace(lease, state="released"))

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
        try:
            return int(raw)
        except ValueError:
            raise errors.OperationFailure(
                errors.failure("invalid_request", "cursor sequence is not numeric")
            ) from None

    # --- control helpers --------------------------------------------------------

    def _emit(self, kind: str, bench_id: str, run_id: str | None,
              evidence: dict[str, Any] | None = None) -> None:
        """Durable bench event stream (Task 6): kind from the seven, append
        to ``bench:{bench_id}``, retention-trimmed after every emit."""
        append_bench_event(
            self._store, kind, bench_id, run_id, evidence,
            keep=self._limits["max_page_size"] * 10, now_iso=self._now_iso,
        )

    def _emit_evidence_gap(self, bench_id: str, run_id: str, failures: int) -> None:
        """One ``evidence_gap`` per drain when monitor retention failed —
        evidence write failures are loud, never dropped (invariant 6)."""
        self._emit("evidence_gap", bench_id, run_id,
                   {"retention_failures": failures})

    def _run_projection(self, run_id: str) -> dict[str, Any]:
        """Contract ``run`` object (interface-v1.1.0 ``run`` def: closed,
        seven fields; outcome/safe_state/terminal_record are null until
        terminal, and terminal-without-a-durable-record is honest
        uncertainty — outcome_unknown/unknown, never a fabricated pass)."""
        run = self._store.get_run(run_id)
        if run is None:
            raise errors.OperationFailure(errors.failure("not_found", f"run {run_id}"))
        state_row = self._store.get_run_state(run_id)
        if state_row is None:
            # Seam-visible runs carry a queue-state row (run_start always
            # writes one); there is no bench_id source without it.
            raise errors.OperationFailure(
                errors.failure("not_found", f"run {run_id} has no queue state")
            )
        record = run["terminal"]
        if state_row["state"] != "terminal":
            outcome = None
            safe_state = None
            terminal_record = None
        elif record is None:
            outcome = "outcome_unknown"
            safe_state = "unknown"
            terminal_record = None
        else:
            outcome = str(record["outcome"])
            safe_state = str(record["safe_state"])
            terminal_record = {
                "id": str(record["run_id"]),
                "version": str(record["contract_version"]),
                "sha256": hashlib.sha256(
                    json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            }
        return {
            "run_id": run_id,
            "bench_id": state_row["bench_id"],
            "revision": state_row["revision"],
            "state": state_row["state"],
            "outcome": outcome,
            "safe_state": safe_state,
            "terminal_record": terminal_record,
        }

    def _lease_projection(self, lease: Lease) -> dict[str, Any]:
        """Contract lease object (interface-v1.1.0 ``lease`` def: closed,
        five fields — the holder is deliberately not exposed)."""
        return {
            "lease_id": lease.lease_id,
            "bench_id": lease.bench_id,
            "sequence": lease.sequence,
            "expires_at": lease.expires_at,
            "state": lease.state,
        }

    def _find_lease(self, lease_id: str) -> Lease | None:
        """Locate a lease by id across benches, preferring the active row
        with the highest sequence (renewal re-issues the same lease id)."""
        found: Lease | None = None
        offset = 0
        while True:
            rows, has_more = self._store.list_benches(limit=100, offset=offset)
            for row in rows:
                for lease in self._store.list_leases(str(row["bench_id"])):
                    if lease.lease_id != lease_id:
                        continue
                    if found is None or (
                        (lease.state == "active" and found.state != "active")
                        or (lease.state == found.state and lease.sequence > found.sequence)
                    ):
                        found = lease
            if not has_more:
                return found
            offset += len(rows)
