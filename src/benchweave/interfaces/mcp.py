"""FastMCP server: the 17 vendored-exact ``stg_v1`` tools over the seam.

Construction is the Task 1 spike's AMENDED verdict: fastmcp 4.0.3 signature
inference cannot reproduce the vendored schemas (pydantic never emits an
empty ``required`` and unconditionally prunes unreferenced ``$defs``), so
each tool is registered via ``mcp.tool(fn, name=..., description=...)`` and
its ``parameters``/``output_schema``/annotations are pinned to the vendored
corpus verbatim; the function signature remains only the callable.

Auth is fail-closed at two layers: a :class:`StgTokenVerifier` (FastMCP
``TokenVerifier`` over :func:`benchweave.interfaces.identity.validate`)
gates the transport (a rejected token never reaches a tool), and every tool
body re-derives its :class:`Identity` from the request-context token via
``identity.validate`` — the same mint-everything-through-validate rule that
keeps §9 pipe-safety intact — before calling the one seam method. Tier
enforcement is the seam's ``require_permission`` (observe ⊆ control ⊆
admin), surfaced as the contract ``forbidden`` envelope.

Wire disclosure (Task 1 spike): serve-time dereference middleware prunes
the corpus's unreferenced ``$defs`` from ``tools/list`` — the served wire
schema is vendored-minus-``$defs`` with everything else byte-exact. The
outputSchema pin adds the single top-level ``type: "object"`` that
``mcp_types``' Tool model requires on the wire (the vendored schema is a
bare ``oneOf`` whose branches are all objects — semantically a no-op).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token

from benchweave.interfaces.errors import OperationFailure, failure
from benchweave.interfaces.identity import Identity, IdentityRejected, validate
from benchweave.interfaces.operations import Operations

# The vendored corpus lives at the repo root beside the tests that pin it
# (src/benchweave/interfaces/mcp.py -> parents[3] is the repository root).
_VENDORED_PATH = (
    Path(__file__).resolve().parents[3] / "contracts" / "interface-v1.1.0" / "mcp-tools.json"
)
_vendored_cache: dict[str, dict[str, Any]] | None = None


def vendored_tools() -> dict[str, dict[str, Any]]:
    """The 17 vendored tool specs by name (loaded once, then cached)."""
    global _vendored_cache
    if _vendored_cache is None:
        document = json.loads(_VENDORED_PATH.read_text(encoding="utf-8"))
        raw = document["tools"] if isinstance(document, dict) and "tools" in document else document
        _vendored_cache = {tool["name"]: tool for tool in raw}
    return _vendored_cache


class StgTokenVerifier(TokenVerifier):
    """FastMCP ``TokenVerifier`` over the local test issuer (fail-closed).

    Every :class:`IdentityRejected` reason collapses to ``None`` here — the
    MCP bearer middleware can only express 401 at the transport. The WP02
    403 semantics for ``wrong_audience``/``insufficient_scope`` surface one
    layer up, where they are expressible: the tool-level envelope (via the
    seam's ``require_permission``) and the REST adapter's status mapping.
    """

    def __init__(
        self, secret: bytes, *, audience: str = "stg", now_epoch: Callable[[], int]
    ) -> None:
        super().__init__()
        self._secret = secret
        self._audience = audience
        self._now_epoch = now_epoch

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            identity = validate(
                self._secret, token, audience=self._audience, now=self._now_epoch()
            )
        except IdentityRejected:
            return None
        return AccessToken(
            token=token,
            client_id=identity.principal,
            scopes=sorted(identity.scopes),
            expires_at=identity.expires_at,
            claims={"principal": identity.principal, "audience": identity.audience},
        )


def build_mcp(
    operations: Operations,
    *,
    secret: bytes,
    now_epoch: Callable[[], int],
    limits: dict[str, int],
    audience: str = "stg",
) -> FastMCP:
    """Register exactly the 17 ``stg_v1_*`` tools, each schema-pinned verbatim.

    ``limits`` is the adapter's clamp table: page sizes are clamped to
    ``max_page_size`` and artifact chunk lengths to ``max_chunk_bytes``
    HERE, before the seam's unbounded SQL LIMIT / chunk window sees them
    (the vendored schemas declare the same bounds declaratively; the
    adapter enforces them imperatively for clients that ignore them).
    """
    mcp = FastMCP(
        name="benchweave-gateway",
        auth=StgTokenVerifier(secret, audience=audience, now_epoch=now_epoch),
    )
    vendored = vendored_tools()
    max_page_size = limits["max_page_size"]
    max_chunk_bytes = limits["max_chunk_bytes"]

    async def _identity() -> Identity:
        """Mint the caller's Identity from the request-context token only.

        Adapters never construct Identity from request data — §9 pipe-safety
        depends on every identity passing through ``identity.validate``.
        """
        access = get_access_token()
        if access is None:
            raise OperationFailure(
                failure("unauthenticated", "no bearer token on the request")
            )
        try:
            return validate(secret, access.token, audience=audience, now=now_epoch())
        except IdentityRejected as rejected:
            code = (
                "forbidden"
                if rejected.reason in {"wrong_audience", "insufficient_scope"}
                else "unauthenticated"
            )
            raise OperationFailure(
                failure(code, f"token rejected: {rejected.reason}")
            ) from None

    def _dispatch(call: Callable[[], Any]) -> dict[str, Any]:
        """One seam call wrapped in the contract envelope; app failures are
        the failure body, never an exception over the wire."""
        try:
            return {"ok": True, "data": call()}
        except OperationFailure as fail:
            return fail.failure.body()

    def _paged(call: Callable[[], tuple[list[dict[str, Any]], str | None]]) -> dict[str, Any]:
        """List endpoints: the seam's (items, next_cursor) tuple becomes the
        contract ``items``/``next_cursor`` data object."""

        def go() -> dict[str, Any]:
            items, next_cursor = call()
            return {"items": items, "next_cursor": next_cursor}

        return _dispatch(go)

    registered_names: set[str] = set()

    def _register[**P](fn: Callable[P, Any]) -> Callable[P, Any]:
        """Register ``fn`` under ``stg_v1_<fn.__name__>`` with the vendored
        description and annotations (the direct-call form returns the
        function, not the Tool — schemas are pinned on the registry's Tool
        object by ``_pin_all`` below)."""
        name = f"stg_v1_{fn.__name__}"
        spec = vendored[name]
        mcp.tool(
            fn,
            name=name,
            description=spec["description"],
            annotations=spec.get("annotations"),
        )
        registered_names.add(name)
        return fn

    # --- observe --------------------------------------------------------------

    @_register
    async def gateway_info() -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(lambda: operations.gateway_info(identity))

    @_register
    async def bench_list(limit: int = 1, cursor: str | None = None) -> dict[str, Any]:
        identity = await _identity()
        page = min(limit, max_page_size)
        return _paged(lambda: operations.bench_list(identity, limit=page, cursor=cursor))

    @_register
    async def bench_get(bench_id: str = "") -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(lambda: operations.bench_get(identity, bench_id))

    @_register
    async def device_list(
        bench_id: str = "", limit: int = 1, cursor: str | None = None
    ) -> dict[str, Any]:
        identity = await _identity()
        page = min(limit, max_page_size)
        return _paged(
            lambda: operations.device_list(identity, bench_id, limit=page, cursor=cursor)
        )

    @_register
    async def device_get(bench_id: str = "", device_id: str = "") -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(lambda: operations.device_get(identity, bench_id, device_id))

    @_register
    async def document_get(sha256: str = "") -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(lambda: operations.document_get(identity, sha256))

    @_register
    async def events_get(
        bench_id: str = "", after: str | None = None, limit: int = 1
    ) -> dict[str, Any]:
        identity = await _identity()
        page = min(limit, max_page_size)
        return _dispatch(
            lambda: operations.events_get(identity, bench_id, after=after, limit=page)
        )

    @_register
    async def evidence_get(evidence_id: str = "") -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(lambda: operations.evidence_get(identity, evidence_id))

    @_register
    async def artifact_read(
        artifact_id: str = "", offset: int = 0, length: int = 1
    ) -> dict[str, Any]:
        identity = await _identity()
        chunk = min(length, max_chunk_bytes)
        return _dispatch(
            lambda: operations.artifact_read(identity, artifact_id, offset, chunk)
        )

    # --- control: runs ----------------------------------------------------------

    @_register
    async def run_check(bench_id: str = "", binding_ref: dict[str, Any] | None = None) -> dict[
        str, Any
    ]:
        identity = await _identity()
        return _dispatch(
            lambda: operations.run_check(identity, bench_id, binding_ref or {})
        )

    @_register
    async def run_start(
        bench_id: str = "",
        request_id: str = "",
        binding_ref: dict[str, Any] | None = None,
        expected_generation: int = 1,
        lease_id: str | None = None,
    ) -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(
            lambda: operations.run_start(
                identity,
                bench_id,
                request_id,
                binding_ref or {},
                expected_generation,
                lease_id,
            )
        )

    @_register
    async def run_get(run_id: str = "") -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(lambda: operations.run_get(identity, run_id))

    @_register
    async def run_find(request_id: str = "") -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(lambda: operations.run_find(identity, request_id))

    @_register
    async def run_cancel(
        run_id: str = "", request_id: str = "", reason: str = ""
    ) -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(
            lambda: operations.run_cancel(identity, run_id, request_id, reason)
        )

    # --- control: leases --------------------------------------------------------

    @_register
    async def lease_create(
        bench_id: str = "",
        request_id: str = "",
        expected_generation: int = 1,
        duration_ms: int = 1,
    ) -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(
            lambda: operations.lease_create(
                identity, bench_id, request_id, expected_generation, duration_ms
            )
        )

    @_register
    async def lease_renew(
        lease_id: str = "", request_id: str = "", sequence: int = 1, duration_ms: int = 1
    ) -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(
            lambda: operations.lease_renew(
                identity, lease_id, request_id, sequence, duration_ms
            )
        )

    @_register
    async def lease_release(
        lease_id: str = "", request_id: str = "", reason: str = ""
    ) -> dict[str, Any]:
        identity = await _identity()
        return _dispatch(
            lambda: operations.lease_release(identity, lease_id, request_id, reason)
        )

    assert registered_names == set(vendored), "registration table drifted from the corpus"

    async def _pin_all() -> None:
        """The mandated construction (Task 1 spike): fetch each registered
        Tool via the public async ``get_tool`` and pin the vendored
        inputSchema/outputSchema verbatim — the signature stays only the
        callable. ``build_mcp`` runs on no event loop, so one ``asyncio.run``
        covers all 17."""
        for name in sorted(vendored):
            tool = await mcp.get_tool(name)
            assert tool is not None, f"{name} not registered"
            tool.parameters = vendored[name]["inputSchema"]
            # MCP-wire requirement (mcp_types' Tool model): outputSchema
            # carries a top-level ``type``. The vendored outputSchema is a
            # bare ``oneOf`` whose branches are all objects, so the pin adds
            # the one required key — semantically a no-op, everything else
            # verbatim.
            pinned_output = {**vendored[name]["outputSchema"], "type": "object"}
            tool.output_schema = pinned_output
            # Build-time self-check: the pin took (same object the server
            # serves from — the fidelity test re-proves it end to end).
            assert tool.parameters == vendored[name]["inputSchema"]
            assert tool.output_schema == pinned_output

    asyncio.run(_pin_all())
    return mcp
