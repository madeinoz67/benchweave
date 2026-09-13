"""The core-operations seam: both adapters dispatch here and nowhere else."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from benchweave.content.store import ContentStore
from benchweave.control.clocking import SystemClock
from benchweave.control.coordinator import _iso_plus_ms, _parse_utc
from benchweave.interfaces import errors
from benchweave.interfaces.identity import Identity, IdentityRejected, validate
from benchweave.interfaces.validation import SeamValidator
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

# §5 live-run states (interface-v1.1.0 run.state enum): a run owns its bench
# from acceptance until its queue state closes terminal — the D9 busy oracle
# reads exactly these states via Store.list_run_states.
LIVE_RUN_STATES = frozenset({"accepted", "running", "protecting"})


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


def is_owner_or_admin(identity: Identity, owner: str) -> bool:
    """§6 owner-or-admin: the resource owner, or any admin-tier identity.

    The ONE predicate behind both §6 non-holder denials on this seam —
    run_cancel's scoping and the D12 takeover holder check — shared, never
    forked, so the two can never drift apart.
    """
    return identity.principal == owner or not identity.scopes.isdisjoint(
        TIER_SATISFIES["admin"]
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


def _default_now_epoch() -> int:
    """Wall-clock epoch default for approval-token validation; deployments
    inject their own clock (WP08 wiring), tests inject a fixed one."""
    return int(time.time())


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
    # Stream naming: "bench.{bench_id}" — the dot form is the one the
    # vendored event def's stream_id pattern (^[a-z][a-z0-9_.-]*$)
    # admits; the colon form was a live contract violation (fix wave).
    stream_id = f"bench.{bench_id}"
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

    # The three admin change kinds (contract §9); submit rejects others.
    CHANGE_KINDS = frozenset(
        {"package_admission", "configuration_activation", "trip_reset"}
    )
    def __init__(
        self,
        store: Store,
        content: ContentStore,
        *,
        validator: SeamValidator,
        gateway_id: str,
        limits: dict[str, int],
        worker: RunWorker | None = None,
        now_iso: Callable[[], str] | None = None,
        issuer_secret: bytes | None = None,
        now_epoch: Callable[[], int] | None = None,
    ) -> None:
        self._store = store
        self._content = content
        # D8: vendored-corpus input admission — every public method validates
        # its payload (built from its own kwargs) as the first statement after
        # require_permission; shape/type violations are ``invalid_request``.
        self._validator = validator
        self._gateway_id = gateway_id
        self._limits = limits
        self._worker = worker
        self._now_iso = now_iso if now_iso is not None else SystemClock().now_iso
        # Approval-issuer wiring (Task 7): the test issuer's secret and the
        # epoch clock token validation reads. A ``None`` secret disables
        # approval verification entirely (fail-closed ``not_ready``);
        # production deployment config is the WP08 surface.
        self._issuer_secret = issuer_secret
        self._now_epoch = now_epoch if now_epoch is not None else _default_now_epoch

    # --- observe -------------------------------------------------------------

    def gateway_info(self, identity: Identity) -> dict[str, Any]:
        require_permission(identity, "observe")
        self._validator.validate("gateway_info", {})
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
        self._validator.validate("bench_list", {"limit": limit, "cursor": cursor})
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
        self._validator.validate("bench_get", {"bench_id": bench_id})
        row = self._store.get_bench(bench_id)
        if row is None:
            raise errors.OperationFailure(errors.failure("not_found", f"bench {bench_id}"))
        return self._bench_projection(row)

    def device_list(
        self, identity: Identity, bench_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        require_permission(identity, "observe")
        self._validator.validate("device_list", {
            "bench_id": bench_id, "limit": limit, "cursor": cursor,
        })
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
        self._validator.validate("device_get", {
            "bench_id": bench_id, "device_id": device_id,
        })
        row = self._store.get_device(device_id)
        if row is None or row["bench_id"] != bench_id:
            raise errors.OperationFailure(
                errors.failure("not_found", f"device {device_id} on {bench_id}")
            )
        return self._device_projection(row)

    def document_get(self, identity: Identity, sha256: str) -> dict[str, Any]:
        require_permission(identity, "observe")
        self._validator.validate("document_get", {"sha256": sha256})
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
        # Offset floor at the SEAM (final-fix wave): a negative offset must
        # never reach the store's Python slicing (wrong-window tail bytes);
        # flooring here makes both adapters correct by construction. D8/D11
        # ordering: the floor stays clamp-not-reject for a negative INTEGER
        # (the pinned behavior), while a non-integer offset falls through to
        # the validator below (invalid_request) instead of raising here.
        if isinstance(offset, int) and not isinstance(offset, bool) and offset < 0:
            offset = 0
        self._validator.validate("artifact_read", {
            "artifact_id": artifact_id, "offset": offset, "length": length,
        })
        try:
            chunk = self._content.artifact_chunk(artifact_id, offset, length)
        except KeyError:
            raise errors.OperationFailure(
                errors.failure("not_found", f"artifact {artifact_id}")
            ) from None
        except ValueError as invalid:
            # D11: the §8 letter's "offsets beyond size fail" — a window that
            # cannot exist in this artifact is a bad request, not a missing
            # artifact (the caller already holds its size from any chunk).
            raise errors.OperationFailure(
                errors.failure("invalid_request", str(invalid))
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
        self._validator.validate("evidence_get", {"evidence_id": evidence_id})
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
        overtaken is ``event_gap`` carrying the retained watermarks in
        ``details`` (§7/§10: the raise preempts the response, so the
        watermarks the caller needs to rejoin the stream ride the failure)
        — never a silent truncation."""
        require_permission(identity, "observe")
        self._validator.validate("events_get", {
            "bench_id": bench_id, "after": after, "limit": limit,
        })
        stream = f"bench.{bench_id}"
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
                # §7 events paragraph: retention overtake is event_gap, with
                # the retained watermarks in details (§10) — the raise
                # preempts the response, so the rejoin point must ride the
                # failure itself; cursor_expired has no emitting path by
                # construction.
                raise errors.OperationFailure(errors.failure(
                    "event_gap",
                    f"retention overtook sequence {decoded[1]}",
                    details={
                        "oldest_sequence": oldest or "0",
                        "current_sequence": current or "0",
                    },
                ))
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
        self._validator.validate("run_check", {
            "bench_id": bench_id, "binding_ref": binding_ref,
        })
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

        §5 pre-checks (D9, spec Decision 3) run synchronously BEFORE the
        request key is written: a bench with a live run conflicts (no queue
        waits for control), and the binding document's own ``request_id``
        must match the §9 request id. §9 idempotency stays ahead of both:
        the key is scoped to principal + operation + request id, the request
        body is the binding pin — a replay returns the original run and
        NEVER enqueues again (even while that run keeps the bench busy);
        the same key with a different binding is a conflict. ``lease_id``
        names a pre-held ACTIVE lease and asserts commissioned takeover of
        the bench (D12): it is validated and CONSUMED inside the §5
        pre-check flow — resolution, bench identity, expiry and §6
        owner-or-admin holder identity — so a run only ever reaches
        acceptance behind a real validated lease, and the run row's
        ``authority='lease'`` is exactly that evidence.
        """
        require_permission(identity, "control")
        self._validator.validate("run_start", {
            "bench_id": bench_id,
            "request_id": request_id,
            "binding_ref": binding_ref,
            "expected_generation": expected_generation,
            "lease_id": lease_id,
        })
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
        # §9 replay beats §5 contention: resolve an already-filed request
        # BEFORE the busy/binding pre-checks, so a retry of the same
        # request id while its run is active still returns that run. The
        # peek writes nothing; accept_request below remains the atomic
        # authority for any race the peek cannot see.
        filed = self._store.find_request(key)
        if filed is not None:
            if filed["body_sha256"] != body_sha:
                raise errors.OperationFailure(
                    errors.failure(
                        "conflict",
                        f"request_id {request_id!r} reused with a different binding",
                    )
                )
            return self._run_projection(str(filed["run_id"]))  # replay: never enqueue
        self._assert_bench_acceptable(
            bench_id, binding_ref, request_id, identity, lease_id
        )
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
        # D12 lease-authority: a named lease can only reach this point
        # through the validated, consumed takeover path inside
        # _assert_bench_acceptable — authority "lease" is evidence a real
        # lease was presented (never an unvalidated string).
        self._store.set_run_authority(
            run_id, "lease" if lease_id is not None else "gateway"
        )
        if lease_id is not None:
            # The commissioned handoff, made durable on the bench stream:
            # manual lease authority passed to the run, pinned to the
            # binding document that commissioned it. The event def's
            # evidence is a CLOSED {id, version, sha256} ref, so the
            # binding pin — not a free-form dict — is the payload.
            self._emit(
                "authority_changed",
                bench_id,
                run_id,
                evidence={
                    "id": str(binding_ref.get("id", "")),
                    "version": str(binding_ref.get("version", "")),
                    "sha256": str(binding_ref.get("sha256", "")),
                },
            )
        # Read the projection BEFORE submitting: the worker races this call
        # to flip the state to "running", and 202 semantics return "accepted".
        projection = self._run_projection(run_id)
        self._worker.submit(run_id, identity.principal, binding_ref, bench_id)
        self._emit("run_changed", bench_id, run_id)
        return projection

    def run_get(self, identity: Identity, run_id: str) -> dict[str, Any]:
        # Catalog authority (operation-catalog.json declares run_get observe,
        # interface-v1.1.0): the read tier, with control/admin admitted via
        # the hierarchy — the Task 10 parity ledger's tier-drift fix.
        require_permission(identity, "observe")
        self._validator.validate("run_get", {"run_id": run_id})
        return self._run_projection(run_id)

    def run_find(self, identity: Identity, request_id: str) -> dict[str, Any]:
        """§9: the lookup is principal-scoped — replaying another
        principal's request id can never discover their runs."""
        require_permission(identity, "control")
        self._validator.validate("run_find", {"request_id": request_id})
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
        reason and request id in the run_changed event.

        §6 owner scoping (final-fix wave): the control tier alone is not
        authority over someone else's run — a control-tier principal may
        cancel only runs they own; the admin tier may cancel any run."""
        require_permission(identity, "control")
        self._validator.validate("run_cancel", {
            "run_id": run_id, "request_id": request_id, "reason": reason,
        })
        run = self._store.get_run(run_id)
        if run is None:
            raise errors.OperationFailure(errors.failure("not_found", f"run {run_id}"))
        if not is_owner_or_admin(identity, str(run["principal_id"])):
            raise errors.OperationFailure(errors.failure(
                "forbidden", f"run {run_id} belongs to principal {run['principal_id']!r}"
            ))
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
        self._validator.validate("lease_create", {
            "bench_id": bench_id,
            "request_id": request_id,
            "expected_generation": expected_generation,
            "duration_ms": duration_ms,
        })
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
        self._validator.validate("lease_renew", {
            "lease_id": lease_id,
            "request_id": request_id,
            "sequence": sequence,
            "duration_ms": duration_ms,
        })
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
        self._validator.validate("lease_release", {
            "lease_id": lease_id, "request_id": request_id, "reason": reason,
        })
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
        # D12: releasing manual authority is an authority transition too.
        # The event def's evidence is a CLOSED {id, version, sha256} ref, so
        # the emit pins the commissioned bench configuration — the same
        # ref the bench projection serves — with no run attached.
        bench = self._store.get_bench(lease.bench_id)
        if bench is not None:
            self._emit(
                "authority_changed",
                lease.bench_id,
                None,
                evidence=self._bench_projection(bench)["configuration"],
            )
        return self._lease_projection(replace(lease, state="released"))

    # --- admin: two-phase changes (Task 7) --------------------------------------

    def change_submit(
        self,
        identity: Identity,
        request_id: str,
        bench_id: str,
        kind: str,
        target_ref: dict[str, Any],
        expected_generation: int,
        reason: str,
    ) -> dict[str, Any]:
        """Phase 1 (contract §9): record a proposed change, nothing else.

        No fence fires here — a proposal made against a stale generation
        view is simply a change that can never apply; the fence belongs to
        ``change_apply``. §9 idempotency: the scoped key is principal +
        operation + request id and the request body is the whole change
        candidate — a replay returns the original change; the same key with
        a different candidate is a conflict.
        """
        require_permission(identity, "admin")
        self._validator.validate("change_submit", {
            "request_id": request_id,
            "bench_id": bench_id,
            "kind": kind,
            "target_ref": target_ref,
            "expected_generation": expected_generation,
            "reason": reason,
        })
        if kind not in self.CHANGE_KINDS:
            raise errors.OperationFailure(
                errors.failure("invalid_request", f"unknown change kind {kind!r}")
            )
        if self._store.get_bench(bench_id) is None:
            raise errors.OperationFailure(errors.failure("not_found", f"bench {bench_id}"))
        now = self._now_iso()
        change_id = f"chg-{uuid.uuid4().hex[:16]}"
        key = scoped_request_key(identity.principal, "change_submit", request_id)
        body_sha = hashlib.sha256(
            json.dumps(
                [bench_id, kind, target_ref, expected_generation, reason],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        try:
            accepted = self._store.accept_request(key, body_sha, change_id, now)
        except Conflict:
            raise errors.OperationFailure(
                errors.failure(
                    "conflict", f"request_id {request_id!r} reused with a different change"
                )
            ) from None
        if accepted.outcome == "duplicate":
            return self._change_projection(str(accepted.run_id))
        self._store.put_change(
            change_id,
            bench_id,
            kind,
            json.dumps(target_ref, sort_keys=True, separators=(",", ":")),
            expected_generation,
            reason,
            now,
        )
        return self._change_projection(change_id)

    def change_apply(
        self,
        identity: Identity,
        request_id: str,
        change_id: str,
        expected_generation: int,
        approval_ref: dict[str, Any],
        approver_token: str | None = None,
    ) -> dict[str, Any]:
        """Phase 2: verify the independent approval, then apply once.

        The order is load-bearing: permission, the change record, the
        approval (the approver is authenticated independently of the
        applier's admin identity), the two-phase state check, the canonical
        generation fences, the per-kind checks — only then the commit
        (bump + bench-row refresh + ``applied`` + event). Every decided
        failure records ``failed``; an undecided crash records ``unknown``
        and surfaces as ``unavailable`` (uncertainty is never erased).
        """
        require_permission(identity, "admin")
        # The validated payload is the corpus's REST body for this route:
        # ``change_id`` is a path param the body schema does not declare,
        # and ``approver_token`` is the D2 detached credential outside the
        # corpus until the interface-v1.1.1 amendment folds it in.
        self._validator.validate("change_apply", {
            "request_id": request_id,
            "expected_generation": expected_generation,
            "approval_ref": approval_ref,
        })
        change = self._store.get_change(change_id)
        if change is None:
            raise errors.OperationFailure(errors.failure("not_found", f"change {change_id}"))
        now = self._now_iso()
        try:
            approver = self.verify_approval(
                approval_ref,
                change_id=change_id,
                expected_generation=expected_generation,
                approver_token=approver_token,
            )
            if approver.principal == identity.principal:
                raise errors.OperationFailure(
                    errors.failure(
                        "forbidden",
                        "approval must be authenticated by a principal"
                        " other than the applier",
                    )
                )
            if change["state"] != "proposed":
                raise errors.OperationFailure(
                    errors.failure(
                        "conflict",
                        f"change {change_id} is {change['state']}, not proposed",
                    )
                )
            stored_generation = int(change["expected_generation"])
            if expected_generation != stored_generation:
                raise errors.OperationFailure(
                    errors.failure(
                        "conflict",
                        f"change {change_id} was proposed at generation"
                        f" {stored_generation}, not {expected_generation}",
                    )
                )
            bench_id = str(change["bench_id"])
            current = self._store.current_generation(bench_id)
            if expected_generation != current:
                raise errors.OperationFailure(
                    errors.failure(
                        "conflict",
                        f"bench {bench_id} is at generation {current},"
                        f" not {expected_generation}",
                    )
                )
            self._dispatch_change(change, request_id, now)
        except errors.OperationFailure as fail:
            self._record_change_outcome(change_id, "failed", fail.failure.message, now)
            raise
        except BaseException as crash:
            self._record_change_outcome(
                change_id,
                "unknown",
                f"apply crashed before a decision was recorded: {crash!r}",
                now,
            )
            raise errors.OperationFailure(
                errors.failure(
                    "unavailable",
                    f"change {change_id} apply did not complete; state is unknown",
                    # D13 retry honesty: re-entering change_apply on an
                    # unknown change is the two-phase ``conflict`` (the
                    # state is no longer proposed), so ``same_request`` lied
                    # about re-entry semantics. The truthful advice is
                    # ``never`` (contract §10: reconciliation/correction —
                    # change_get, then a NEW change if warranted).
                    retry="never",
                )
            ) from crash
        return self._change_projection(change_id)

    def change_get(self, identity: Identity, change_id: str) -> dict[str, Any]:
        """Admin-tier read of one change record in any state."""
        require_permission(identity, "admin")
        self._validator.validate("change_get", {"change_id": change_id})
        return self._change_projection(change_id)

    def verify_approval(
        self,
        approval_ref: dict[str, Any],
        *,
        change_id: str,
        expected_generation: int,
        approver_token: str | None = None,
    ) -> Identity:
        """Independent approval authentication (PRD-12; design Decision 7).

        An approval is two things that must agree: a stored, sha-pinned
        document binding {change_id, expected_generation, approver_principal,
        policy_version}, and a detached HMAC token issued to the named
        approver (audience ``gateway-admin``, scope ``stg:admin``). The
        applier's own admin identity authorizes nothing here — a stored
        document without its token, a token without its document, a token
        for anyone other than the documented approver, or a binding for any
        other change+generation all fail closed. Rejections map per WP02:
        a missing token is ``forbidden`` (a document alone is not approval,
        contract §3); malformed/bad-signature/expired tokens are
        ``unauthenticated``; wrong audience or scope is ``forbidden``.
        """
        if self._issuer_secret is None:
            raise errors.OperationFailure(
                errors.failure("not_ready", "no approval issuer is configured")
            )
        sha = str(approval_ref.get("sha256", ""))
        doc = self._content.get_document(sha)
        if doc is None:
            raise errors.OperationFailure(
                errors.failure("not_found", "approval document not stored")
            )
        if hashlib.sha256(doc["raw_bytes"]).hexdigest() != sha:
            raise errors.OperationFailure(
                errors.failure("forbidden", "approval document bytes do not match its digest")
            )
        body = doc["content"]
        if (
            body.get("change_id") != change_id
            or body.get("expected_generation") != expected_generation
        ):
            raise errors.OperationFailure(
                errors.failure("forbidden", "approval does not bind this change+generation")
            )
        if approver_token is None:
            raise errors.OperationFailure(
                errors.failure("forbidden", "approval token rejected: missing_token")
            )
        try:
            approver = validate(
                self._issuer_secret,
                approver_token,
                audience="gateway-admin",
                required_scopes=("stg:admin",),
                now=self._now_epoch(),
            )
        except IdentityRejected as rejected:
            code = (
                "forbidden"
                if rejected.reason in {"wrong_audience", "insufficient_scope"}
                else "unauthenticated"
            )
            raise errors.OperationFailure(
                errors.failure(code, f"approval token rejected: {rejected.reason}")
            ) from None
        if approver.principal != str(body.get("approver_principal", "")):
            raise errors.OperationFailure(
                errors.failure(
                    "forbidden", "approval token principal is not the documented approver"
                )
            )
        return approver

    def _dispatch_change(
        self, change: dict[str, Any], request_id: str, now: str
    ) -> None:
        """Run the kind's checks, then commit exactly once: bump the
        canonical generation, refresh the bench-row projection (Task-5
        mandate — observe must never lag the authority), mark the change
        applied, and emit the kind's event (Task 6)."""
        kind = str(change["kind"])
        bench_id = str(change["bench_id"])
        handler: Callable[[dict[str, Any], str], str] = {
            "package_admission": self._apply_package_admission,
            "configuration_activation": self._apply_configuration_activation,
            "trip_reset": self._apply_trip_reset,
        }[kind]
        event_kind = handler(change, bench_id)
        new_generation = self._store.bump_generation(bench_id, now)
        row = self._store.get_bench(bench_id)
        if row is not None:
            self._store.put_bench(
                bench_id,
                new_generation,
                row["qualification"],
                row["configuration_json"],
                row["licence"],
                now,
            )
        self._store.set_change_state(str(change["change_id"]), "applied", [], now)
        self._emit(
            event_kind,
            bench_id,
            None,
            evidence={
                "change_id": str(change["change_id"]),
                "kind": kind,
                "request_id": request_id,
                "generation": new_generation,
            },
        )

    def _apply_trip_reset(self, change: dict[str, Any], bench_id: str) -> str:
        """Trip reset requires no live trip condition on the bench projection
        (contract: reset cannot re-arm or restart a test — reconciled
        physical state); a tripped bench is ``policy_denied``."""
        bench = self._store.get_bench(bench_id)
        if bench is None:
            raise errors.OperationFailure(errors.failure("not_found", f"bench {bench_id}"))
        if self._bench_projection(bench)["tripped"]:
            raise errors.OperationFailure(
                errors.failure(
                    "policy_denied", f"bench {bench_id} is tripped; reset is refused"
                )
            )
        return "bench_changed"

    def _apply_configuration_activation(
        self, change: dict[str, Any], bench_id: str
    ) -> str:
        """Idle boundary first: a live bench lease refuses activation —
        registry.activation.activate's ``not_idle``, surfaced as
        ``not_ready``.

        WP07 disclosure: the registry leg — ``activate(admitted, *,
        bench_generation, bench_has_live_lease, records_dir, activated_at)
        -> ActivationRecord`` — needs an ``Admitted`` closure only a
        configured registry session can produce; this gateway runs the PoC
        fixture bench with no registry session (WP08 deployment surface), so
        an otherwise-valid idle activation records ``failed``/``not_ready``
        rather than fabricating an activation record."""
        if self._live_lease(bench_id) is not None:
            raise errors.OperationFailure(
                errors.failure("not_ready", f"bench {bench_id} holds a live lease; not idle")
            )
        raise errors.OperationFailure(
            errors.failure("not_ready", "registry activation is not configured")
        )

    def _apply_package_admission(self, change: dict[str, Any], bench_id: str) -> str:
        """package_admission: registry admission of the target package.

        WP07 disclosure: ``registry.admission.admit(closure, *, cache_root,
        lock_path, limits: AdmissionLimits, approval: Approval(principal_id,
        approved_at, policy_id, policy_version), now_ns, roots,
        high_water=None) -> Admitted`` consumes a ``ResolvedClosure`` from
        the resolver session plus per-release trust roots. No registry
        session is configured on this gateway (the PoC fixture bench
        bypasses the registry), so the kind records ``failed``/
        ``not_ready`` instead of admitting anything; WP08 wires the resolver
        session and this becomes a real admit + ``registry_status_changed``."""
        raise errors.OperationFailure(
            errors.failure("not_ready", "registry admission is not configured")
        )

    def _record_change_outcome(
        self, change_id: str, state: str, reason: str, now: str
    ) -> None:
        """Record a failed/unknown outcome — never over an already-applied
        change (a post-commit crash leaves the applied record truthful)."""
        change = self._store.get_change(change_id)
        if change is not None and change["state"] != "applied":
            self._store.set_change_state(change_id, state, [reason], now)

    def _change_projection(self, change_id: str) -> dict[str, Any]:
        """Contract change object; ``get_change`` returns the target ref as
        stored JSON text and the reasons as a parsed list (Task 2 pins)."""
        change = self._store.get_change(change_id)
        if change is None:
            raise errors.OperationFailure(
                errors.failure("not_found", f"change {change_id}")
            )
        return {
            "change_id": change["change_id"],
            "bench_id": change["bench_id"],
            "kind": change["kind"],
            "target_ref": json.loads(str(change["target_ref_json"])),
            "expected_generation": int(change["expected_generation"]),
            "reason": change["reason"],
            "state": change["state"],
            "reasons": change["reasons"],
            "created_at": change["created_at"],
            "updated_at": change["updated_at"],
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
            "busy": self._live_lease(row["bench_id"]) is not None,
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
        to ``bench.{bench_id}``, retention-trimmed after every emit."""
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
        # The worker persists the terminal record before publishing terminal
        # queue state. Read that state first: a terminal observation must then
        # see its record, while an earlier running observation can stay pending.
        state_row = self._store.get_run_state(run_id)
        run = self._store.get_run(run_id)
        if run is None:
            raise errors.OperationFailure(errors.failure("not_found", f"run {run_id}"))
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

    def _live_lease(self, bench_id: str) -> Lease | None:
        """The bench's ACTIVE lease, iff its stored ``expires_at`` is still
        in the future at the seam's injected clock (D13).

        The stored stamp is the read-time oracle — ``limits.max_lease_ms``
        bounds what ``lease_create`` may mint, never what a read decides —
        and ``now >= expires_at`` means the unreleased row pins nothing:
        the bench stops reading busy and new runs/leases are admissible.
        An unparseable stamp fails the same direction (no deadline can be
        established, so the row cannot hold the bench; the takeover path
        already refuses such a row closed ``not_found``). This clears only
        the LEASE-side busy: the §5 run-side oracle stays
        ``LIVE_RUN_STATES`` over ``Store.list_run_states``.
        """
        lease = self._store.get_active_lease(bench_id)
        if lease is None:
            return None
        expiry = _parse_utc(lease.expires_at)
        now_moment = _parse_utc(self._now_iso())
        if expiry is None or now_moment is None or now_moment >= expiry:
            return None
        return lease

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

    def _assert_bench_acceptable(
        self,
        bench_id: str,
        binding_ref: dict[str, Any],
        request_id: str,
        identity: Identity,
        lease_id: str | None,
    ) -> None:
        """§5 accept-time pre-checks (D9) with the D12 takeover woven in:
        commissioned-lease validation, synchronous contention and binding
        identity, all raised BEFORE the request key is written (no dangling
        idempotency tombstone on a refused run — and no lease consumed for
        a start that is refused).

        Takeover (D12): a non-null ``lease_id`` asserts authority over the
        bench via the caller's pre-held manual lease. It is validated HERE
        — resolved through ``_find_lease``, ACTIVE on THIS bench, unexpired
        at the seam clock, holder §6 owner-or-admin — and then CONSUMED
        (store state → released), which is what lets the worker's
        ``reserve`` see an idle bench instead of ``bench_busy`` and what
        makes the lease single-shot: a consumed lease can never authorize
        a second takeover (a §9 replay of the same request never reaches
        this branch — the peek returns the existing run first). A
        VALIDATED lease is the sanctioned override of the caller's OWN
        manual authority; it never waives contention with another live
        run or another owner. Failure codes (the catalog's global 14-code
        set, per the controller ruling): unknown/expired/consumed lease
        ``not_found``; wrong-bench lease ``conflict``; non-holder
        ``forbidden``.

        Busy oracle: the store's run-state view — any run still in a live
        state (``LIVE_RUN_STATES``) owns the bench. There is no separate
        live-run registry, so activity is derived from run_states via the
        store's query surface (``list_run_states``, the read-only accessor
        added for this check). Catalog pin: operation-catalog.json declares
        no busy-specific failure code for run_start — its global
        error_http_status map gives contention the 409 ``conflict`` vehicle
        (``not_ready`` is also 409 but names a gateway-capability failure,
        not a busy bench).

        Binding match: the binding document's own top-level ``request_id``
        must equal the §9 request id, resolved exactly as ``run_check``
        resolves binding refs (content-store lookup by digest). An unstored
        digest is NOT decided here — that failure stays asynchronous (the
        worker's poison guard owns it) — so only a resolvable document can
        conflict at accept time. Note the inverted guard: an unstored
        binding still CONSUMES a presented lease, because acceptance
        itself proceeds and the run needs the bench the lease was holding.
        """
        lease: Lease | None = None
        if lease_id is not None:
            lease = self._find_lease(lease_id)
            if lease is None or lease.state != "active":
                # Unknown, released, expired-away or already consumed: the
                # lease names no authority this start can ride (§6's "a
                # late renewal cannot revive an expired lease" family).
                raise errors.OperationFailure(
                    errors.failure(
                        "not_found",
                        f"lease {lease_id} is not an active lease",
                    )
                )
            if lease.bench_id != bench_id:
                raise errors.OperationFailure(
                    errors.failure(
                        "conflict",
                        f"lease {lease_id} is held on bench {lease.bench_id},"
                        f" not {bench_id}",
                    )
                )
            expiry = _parse_utc(lease.expires_at)
            now_moment = _parse_utc(self._now_iso())
            if expiry is None or now_moment is None:
                # A corrupt row/stamp is not an expiry claim: fail closed
                # with a truthful message, never a fabricated deadline.
                raise errors.OperationFailure(
                    errors.failure(
                        "not_found",
                        f"lease {lease_id} expiry {lease.expires_at!r} is not"
                        f" a parseable timestamp",
                    )
                )
            if now_moment >= expiry:
                raise errors.OperationFailure(
                    errors.failure(
                        "not_found",
                        f"lease {lease_id} expired at {lease.expires_at}",
                    )
                )
            if not is_owner_or_admin(identity, lease.holder):
                raise errors.OperationFailure(
                    errors.failure(
                        "forbidden",
                        f"lease {lease_id} is held by principal {lease.holder!r}",
                    )
                )
        for row in self._store.list_run_states(bench_id):
            if row["state"] in LIVE_RUN_STATES:
                raise errors.OperationFailure(
                    errors.failure(
                        "conflict",
                        f"bench {bench_id} is busy with run {row['run_id']}"
                        f" (state {row['state']})",
                    )
                )
        document = self._content.get_document(str(binding_ref.get("sha256", "")))
        if document is not None:
            bound_request_id = str(document["content"].get("request_id", ""))
            if bound_request_id != request_id:
                raise errors.OperationFailure(
                    errors.failure(
                        "conflict",
                        f"binding document names request_id {bound_request_id!r},"
                        f" not {request_id!r}",
                    )
                )
        if lease is not None:
            # Consume LAST: every refusal above leaves the holder's lease
            # untouched, and consumption still precedes the request key —
            # nothing persists for a refused run, so no partially-taken-
            # over state can survive a refused start.
            try:
                self._store.consume_lease(
                    lease.bench_id, lease.sequence, self._now_iso()
                )
            except LeaseNotActive:
                raise errors.OperationFailure(
                    errors.failure(
                        "conflict",
                        f"lease {lease_id} was released while the start was"
                        f" being decided",
                    )
                ) from None
