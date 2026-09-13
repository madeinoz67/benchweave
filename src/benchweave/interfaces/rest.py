"""REST routers: translation only — raw body in, seam call, status out.

The 20 catalog operations (operation-catalog.json) as FastAPI routes. Every
handler is the same three-step translation: decode (raw ``request.body()``
JSON, the body-ceiling check, typed query params — no request-schema
validation, the seam stays the sole authority), authenticate (the Bearer
header through ``identity.validate`` — adapters never construct an Identity
from request data), then one seam call wrapped for the write gate where the
seam mutates. Success is the contract envelope at the catalog's
``success_status``; an ``OperationFailure`` is ``failure.body()`` at
``FAILURE_HTTP[code]`` — the full 14-code map, including the 403 semantics
the MCP transport cannot express.

Write gate (Task 7 carry): ``change_apply``'s fence-then-bump is
check-then-act, so it runs under the app's ``WriteGate`` — and so does every
other seam-mutating handler (run_start/run_cancel/lease_create/renew/
release/change_submit). Today a single serving loop already serialises
async handlers, but that is incidental: one ``async def`` -> ``def`` edit
puts a FastAPI handler in the threadpool, and the gate's invariant is
process-wide single-writer discipline, not event-loop goodwill. Read-only
and advisory handlers (run_check) stay ungated — they mutate nothing.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from benchweave.interfaces import errors
from benchweave.interfaces.errors import OperationFailure
from benchweave.interfaces.identity import Identity, IdentityRejected, validate
from benchweave.interfaces.operations import Operations

# WP02 rejection map at the REST layer: token-shaped failures are 401;
# audience/scope failures are 403 (expressible here, unlike MCP transport).
_AUTH_401_REASONS = frozenset({"malformed_token", "bad_signature", "expired"})


def _default_now_epoch() -> int:
    return int(time.time())


def build_router(
    operations: Operations,
    gate: Any,
    *,
    secret: bytes,
    limits: dict[str, int],
    audience: str = "stg",
    now_epoch: Callable[[], int] | None = None,
) -> APIRouter:
    """All 20 routes over the seam; ``gate`` is the app's ``WriteGate``.

    ``Any`` for the gate keeps the import graph acyclic (``app`` imports
    this module; the gate type lives there). ``limits`` is the adapter's
    clamp/ceiling table, mirroring the MCP adapter: page sizes clamp to
    ``max_page_size`` (floor 1 — SQLite reads ``LIMIT < 0`` as UNLIMITED),
    artifact lengths to ``max_chunk_bytes`` (floor 1), offsets floor at 0,
    and request bodies over ``max_json_bytes`` are ``payload_too_large``
    before any decode.
    """
    epoch = now_epoch if now_epoch is not None else _default_now_epoch
    max_page_size = limits["max_page_size"]
    max_chunk_bytes = limits["max_chunk_bytes"]
    max_json_bytes = limits["max_json_bytes"]
    router = APIRouter()

    def _reply(result: dict[str, Any], status: int) -> JSONResponse:
        return JSONResponse({"ok": True, "data": result}, status_code=status)

    def _identity(request: Request) -> Identity:
        """Mint the caller's Identity from the Authorization header only.

        Manual header extraction (not FastAPI's HTTPBearer): its missing-
        credential rejection is a Starlette 403 detail body, and the WP02
        map requires our own 401 ``unauthenticated`` envelope.
        """
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise OperationFailure(
                errors.failure("unauthenticated", "bearer token required")
            )
        try:
            return validate(secret, token, audience=audience, now=epoch())
        except IdentityRejected as rejected:
            code = (
                "unauthenticated" if rejected.reason in _AUTH_401_REASONS else "forbidden"
            )
            raise OperationFailure(
                errors.failure(code, f"token rejected: {rejected.reason}")
            ) from None

    def _guard[**P](handler: Callable[P, Awaitable[JSONResponse]]) -> Callable[
        P, Awaitable[JSONResponse]
    ]:
        """Translate the seam's failures onto the wire; never leak a 500
        stack — an unexpected crash is the contract ``internal_error``."""

        @wraps(handler)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> JSONResponse:
            try:
                return await handler(*args, **kwargs)
            except OperationFailure as fail:
                return JSONResponse(
                    fail.failure.body(),
                    status_code=errors.FAILURE_HTTP[fail.failure.code],
                )
            except Exception as crash:
                # D13: the ONE internal_error construction site — identical
                # message text on both transports, correlation_id minted per
                # envelope; the crash itself is logged server-side by the
                # factory, keyed by that correlation_id.
                return JSONResponse(
                    errors.internal_failure(crash).body(),
                    status_code=errors.FAILURE_HTTP["internal_error"],
                )

        return wrapped

    async def _json_body(request: Request) -> dict[str, Any]:
        """Raw body -> object dict, enforcing the ``max_json_bytes`` ceiling
        before any decode (Content-Length pre-check plus a post-read size
        check for chunked bodies)."""
        declared = request.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > max_json_bytes:
            raise OperationFailure(
                errors.failure(
                    "payload_too_large", f"body exceeds max_json_bytes ({max_json_bytes})"
                )
            )
        raw = await request.body()
        if len(raw) > max_json_bytes:
            raise OperationFailure(
                errors.failure(
                    "payload_too_large", f"body exceeds max_json_bytes ({max_json_bytes})"
                )
            )
        if not raw:
            raise OperationFailure(errors.failure("invalid_request", "body required"))
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise OperationFailure(
                errors.failure("invalid_request", "body is not valid JSON")
            ) from None
        if not isinstance(parsed, dict):
            raise OperationFailure(
                errors.failure("invalid_request", "body must be an object")
            )
        return parsed

    def _field(body: dict[str, Any], name: str) -> Any:
        """A required body field is ``invalid_request`` when absent — a
        missing field is a bad request, never a KeyError 500."""
        if name not in body:
            raise OperationFailure(
                errors.failure("invalid_request", f"{name} is required")
            )
        return body[name]

    def _int_param(request: Request, name: str) -> int:
        raw = request.query_params.get(name)
        if raw is None or raw == "":
            raise OperationFailure(
                errors.failure("invalid_request", f"{name} is required")
            )
        try:
            return int(raw)
        except ValueError:
            raise OperationFailure(
                errors.failure("invalid_request", f"{name} must be an integer")
            ) from None

    def _nullable_param(request: Request, name: str) -> str | None:
        raw = request.query_params.get(name)
        return raw if raw else None

    # --- observe --------------------------------------------------------------

    @router.get("/v1")
    @_guard
    async def gateway_info(request: Request) -> JSONResponse:
        return _reply(operations.gateway_info(_identity(request)), 200)

    @router.get("/v1/benches")
    @_guard
    async def bench_list(request: Request) -> JSONResponse:
        identity = _identity(request)
        limit = max(1, min(_int_param(request, "limit"), max_page_size))
        items, next_cursor = operations.bench_list(
            identity, limit=limit, cursor=_nullable_param(request, "cursor")
        )
        return _reply({"items": items, "next_cursor": next_cursor}, 200)

    @router.get("/v1/benches/{bench_id}")
    @_guard
    async def bench_get(bench_id: str, request: Request) -> JSONResponse:
        return _reply(operations.bench_get(_identity(request), bench_id), 200)

    @router.get("/v1/benches/{bench_id}/devices")
    @_guard
    async def device_list(bench_id: str, request: Request) -> JSONResponse:
        identity = _identity(request)
        limit = max(1, min(_int_param(request, "limit"), max_page_size))
        items, next_cursor = operations.device_list(
            identity, bench_id, limit=limit, cursor=_nullable_param(request, "cursor")
        )
        return _reply({"items": items, "next_cursor": next_cursor}, 200)

    @router.get("/v1/benches/{bench_id}/devices/{device_id}")
    @_guard
    async def device_get(bench_id: str, device_id: str, request: Request) -> JSONResponse:
        return _reply(
            operations.device_get(_identity(request), bench_id, device_id), 200
        )

    @router.get("/v1/documents/{sha256}")
    @_guard
    async def document_get(sha256: str, request: Request) -> JSONResponse:
        return _reply(operations.document_get(_identity(request), sha256), 200)

    @router.get("/v1/runs/{run_id}")
    @_guard
    async def run_get(run_id: str, request: Request) -> JSONResponse:
        return _reply(operations.run_get(_identity(request), run_id), 200)

    @router.get("/v1/benches/{bench_id}/events")
    @_guard
    async def events_get(bench_id: str, request: Request) -> JSONResponse:
        identity = _identity(request)
        limit = max(1, min(_int_param(request, "limit"), max_page_size))
        return _reply(
            operations.events_get(
                identity,
                bench_id,
                after=_nullable_param(request, "after"),
                limit=limit,
            ),
            200,
        )

    @router.get("/v1/evidence/{evidence_id}")
    @_guard
    async def evidence_get(evidence_id: str, request: Request) -> JSONResponse:
        return _reply(operations.evidence_get(_identity(request), evidence_id), 200)

    @router.get("/v1/artifacts/{artifact_id}/chunks")
    @_guard
    async def artifact_read(artifact_id: str, request: Request) -> JSONResponse:
        offset = max(0, _int_param(request, "offset"))
        length = max(1, min(_int_param(request, "length"), max_chunk_bytes))
        return _reply(
            operations.artifact_read(_identity(request), artifact_id, offset, length),
            200,
        )

    # --- control: runs ----------------------------------------------------------

    @router.post("/v1/benches/{bench_id}/run-checks")
    @_guard
    async def run_check(bench_id: str, request: Request) -> JSONResponse:
        body = await _json_body(request)
        return _reply(
            operations.run_check(_identity(request), bench_id, _field(body, "binding_ref")),
            200,
        )

    @router.post("/v1/benches/{bench_id}/runs", status_code=202)
    @_guard
    async def run_start(bench_id: str, request: Request) -> JSONResponse:
        body = await _json_body(request)
        with gate:
            result = operations.run_start(
                _identity(request),
                bench_id,
                _field(body, "request_id"),
                _field(body, "binding_ref"),
                _field(body, "expected_generation"),
                body.get("lease_id"),
            )
        return _reply(result, 202)

    @router.get("/v1/requests/{request_id}")
    @_guard
    async def run_find(request_id: str, request: Request) -> JSONResponse:
        return _reply(operations.run_find(_identity(request), request_id), 200)

    @router.post("/v1/runs/{run_id}/cancellations")
    @_guard
    async def run_cancel(run_id: str, request: Request) -> JSONResponse:
        body = await _json_body(request)
        with gate:
            result = operations.run_cancel(
                _identity(request),
                run_id,
                _field(body, "request_id"),
                _field(body, "reason"),
            )
        return _reply(result, 200)

    # --- control: leases --------------------------------------------------------

    @router.post("/v1/benches/{bench_id}/leases", status_code=201)
    @_guard
    async def lease_create(bench_id: str, request: Request) -> JSONResponse:
        body = await _json_body(request)
        with gate:
            result = operations.lease_create(
                _identity(request),
                bench_id,
                _field(body, "request_id"),
                _field(body, "expected_generation"),
                _field(body, "duration_ms"),
            )
        return _reply(result, 201)

    @router.post("/v1/leases/{lease_id}/renewals")
    @_guard
    async def lease_renew(lease_id: str, request: Request) -> JSONResponse:
        body = await _json_body(request)
        with gate:
            result = operations.lease_renew(
                _identity(request),
                lease_id,
                _field(body, "request_id"),
                _field(body, "sequence"),
                _field(body, "duration_ms"),
            )
        return _reply(result, 200)

    @router.post("/v1/leases/{lease_id}/releases")
    @_guard
    async def lease_release(lease_id: str, request: Request) -> JSONResponse:
        body = await _json_body(request)
        with gate:
            result = operations.lease_release(
                _identity(request),
                lease_id,
                _field(body, "request_id"),
                _field(body, "reason"),
            )
        return _reply(result, 200)

    # --- admin: two-phase changes (REST-only per the catalog) ---------------------

    @router.post("/v1/admin/changes", status_code=201)
    @_guard
    async def change_submit(request: Request) -> JSONResponse:
        body = await _json_body(request)
        with gate:
            result = operations.change_submit(
                _identity(request),
                _field(body, "request_id"),
                _field(body, "bench_id"),
                _field(body, "kind"),
                _field(body, "target_ref"),
                _field(body, "expected_generation"),
                _field(body, "reason"),
            )
        return _reply(result, 201)

    @router.post("/v1/admin/changes/{change_id}/apply")
    @_guard
    async def change_apply(change_id: str, request: Request) -> JSONResponse:
        body = await _json_body(request)
        with gate:
            result = operations.change_apply(
                _identity(request),
                _field(body, "request_id"),
                change_id,
                _field(body, "expected_generation"),
                _field(body, "approval_ref"),
                body.get("approver_token"),
            )
        return _reply(result, 200)

    @router.get("/v1/admin/changes/{change_id}")
    @_guard
    async def change_get(change_id: str, request: Request) -> JSONResponse:
        return _reply(operations.change_get(_identity(request), change_id), 200)

    return router
