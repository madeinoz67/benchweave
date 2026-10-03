"""The G2b read pages: every route is the rest.py three-step translation
with the Identity source swapped (design §2.4).

Session cookie → ``SessionStore.resolve`` → seam call → render. Nothing
here constructs an ``Identity`` from request data; the server-side
session record is the only source (CON-15, the rest.py rule). Failures
render through the shared failure page — the code's OWN §C.3 row with
the message and correlation id (GW-11), ``not_found`` wording "unavailable
to this caller" (GW-14). No page renders a mutating control: G2 is
read-only, pinned by the observe-scope suite (GW-55's render half —
status, ownership and terminal state exactly as ``run_get`` reports
them; the cancel control is G3's).

The artifact download (GW-60/61) loops ``artifact_read`` within
``max_chunk_bytes`` — the interface's own chunk limits — and verifies the
COMPLETE digest before the response completes; the reassembly is bounded
by ``max_json_bytes`` (the adapter's one payload ceiling — an artifact
larger than the ceiling is refused ``payload_too_large``, never streamed
unverified or reassembled unbounded).
"""

from __future__ import annotations

import base64
import hashlib
import logging
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from benchweave.content.store import ContentStore
from benchweave.interfaces.errors import OperationFailure, failure
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import SessionRecord
from benchweave.interfaces.ui_presentation import compose_device_presentation

_LOG = logging.getLogger(__name__)

#: The bench page's first events page — a presentation bound (how many
#: rows a page carries), not a protective envelope; it never exceeds the
#: adapter's ``max_page_size``.
_EVENTS_FIRST_PAGE = 20


def register_read_pages(
    router: APIRouter,
    *,
    operations: Operations,
    content: ContentStore | None,
    limits: Mapping[str, int],
    resolve_session: Callable[[Request], SessionRecord | None],
    session_identity: Callable[[SessionRecord], Identity],
    page: Callable[..., HTMLResponse],
    failure_page: Callable[[OperationFailure], HTMLResponse],
    unauthenticated_page: Callable[[], HTMLResponse],
) -> None:
    """Register the read routes on the UI router (before its catch-all).

    The helpers are ``build_ui_router``'s own closures — the same
    session resolution, page shell and failure translation the index
    uses, so every page shares one refusal shape and one chrome.
    """
    max_page_size = int(limits.get("max_page_size", 1000))
    max_chunk_bytes = int(limits.get("max_chunk_bytes", 65_536))
    max_json_bytes = int(limits.get("max_json_bytes", 1_048_576))

    def _authed(request: Request) -> tuple[SessionRecord, Identity] | None:
        """The live session and its seam identity, or ``None`` (the
        caller renders the unauthenticated refusal — the page's own
        shape, never a redirect that leaks where sessions exist)."""
        record = resolve_session(request)
        if record is None:
            return None
        return record, session_identity(record)

    def _strip(record: SessionRecord) -> dict[str, Any]:
        """The base-template context every authed page shares: gateway
        identity from ``gateway_info`` (GW-81), the session's principal
        and scopes, no mode-banner entries (GW-80: no gateway-reported
        fact fires one on these pages today — the wire carries no
        lease-holder or policy-engine fact; absence asserts full-authority
        presentation per §D), and the CSRF token (NFR-S4 machinery)."""
        identity = session_identity(record)
        info = operations.gateway_info(identity)
        return {
            "gateway_id": str(info["gateway_id"]),
            "principal": record.principal,
            "scopes": sorted(record.scopes),
            "mode_banner": None,
            "csrf_token": record.csrf_token,
        }

    # --- benches (GW-20) --------------------------------------------------------

    @router.get("/benches/{bench_id}", include_in_schema=False)
    async def bench_page(bench_id: str, request: Request) -> Response:
        """One bench: the projection, its devices, and the first events
        page (design §2.4) — three read calls on the session's identity."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page()
        record, identity = authed
        try:
            bench = operations.bench_get(identity, bench_id)
            devices, _next = operations.device_list(
                identity, bench_id, limit=max_page_size, cursor=None
            )
            events = operations.events_get(
                identity, bench_id, after=None, limit=_EVENTS_FIRST_PAGE
            )
        except OperationFailure as fail:
            return failure_page(fail)
        return page(
            "bench.j2",
            title=f"Bench {bench_id}",
            bench=bench,
            devices=devices,
            events=events["events"],
            **_strip(record),
        )

    # --- devices and the plugin presentation page (GW-21/22/23) --------------

    @router.get(
        "/benches/{bench_id}/devices/{device_id}", include_in_schema=False
    )
    async def device_page(
        bench_id: str, device_id: str, request: Request
    ) -> Response:
        """One device's projection plus its plugin presentation pages,
        resolved from admitted documents and validated through the
        gateway's own validator (GW-21 — SW-41's parity surface). The
        descriptor bytes come through the SEAM (``document_get`` on the
        device's pinned digest); the presentation resolution reads the
        admitted-document store the same admission wrote."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page()
        record, identity = authed
        try:
            device = operations.device_get(identity, bench_id, device_id)
            document = operations.document_get(
                identity, str(device["descriptor"]["sha256"])
            )
        except OperationFailure as fail:
            return failure_page(fail)
        descriptor_raw = base64.b64decode(document["original_utf8_base64"])
        presentation = compose_device_presentation(content, descriptor_raw)
        return page(
            "device.j2",
            title=f"Device {device_id}",
            device=device,
            presentation=presentation,
            **_strip(record),
        )

    # --- runs and reconcile (GW-55 render half, GW-12's view) ------------------

    @router.get("/runs/{run_id}", include_in_schema=False)
    async def run_page(run_id: str, request: Request) -> Response:
        """A run exactly as ``run_get`` reports it: state, revision,
        outcome, safe state, terminal record. No cancel control (G3's),
        no inferred outcome — an absent terminal record renders absent."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page()
        record, identity = authed
        try:
            run = operations.run_get(identity, run_id)
        except OperationFailure as fail:
            return failure_page(fail)
        return page("run.j2", title=f"Run {run_id}", run=run, **_strip(record))

    @router.get("/requests/{request_id}", include_in_schema=False)
    async def request_page(request_id: str, request: Request) -> Response:
        """The reconcile view (GW-12): resolve a §9 ``request_id`` to the
        run it accepted. ``run_find`` is control-tier in the frozen
        catalog, so an observe session renders the ``forbidden`` §C.3
        row — the honest tier refusal, never a softened rewrite."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page()
        record, identity = authed
        try:
            run = operations.run_find(identity, request_id)
        except OperationFailure as fail:
            return failure_page(fail)
        return page(
            "request.j2", title=f"Request {request_id}", run=run, **_strip(record)
        )

    # --- evidence, artifacts, documents (GW-60/61) ------------------------------

    @router.get("/evidence/{evidence_id}", include_in_schema=False)
    async def evidence_page(evidence_id: str, request: Request) -> Response:
        """One evidence record: kind, content ref digest, artifact link."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page()
        record, identity = authed
        try:
            evidence = operations.evidence_get(identity, evidence_id)
        except OperationFailure as fail:
            return failure_page(fail)
        return page(
            "evidence.j2",
            title=f"Evidence {evidence_id}",
            evidence=evidence,
            **_strip(record),
        )

    @router.get("/artifacts/{artifact_id}", include_in_schema=False)
    async def artifact_download(artifact_id: str, request: Request) -> Response:
        """The artifact download (GW-60/61): chunked ``artifact_read``
        within ``max_chunk_bytes``, the COMPLETE digest verified before
        the response completes, reassembly bounded by ``max_json_bytes``
        (over the bound is ``payload_too_large`` — the adapter's one
        payload ceiling — never an unbounded reassembly)."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page()
        _record, identity = authed
        try:
            first = operations.artifact_read(
                identity, artifact_id, 0, max_chunk_bytes
            )
            total_bytes = int(first["total_bytes"])
            if total_bytes > max_json_bytes:
                raise OperationFailure(
                    failure(
                        "payload_too_large",
                        f"artifact {artifact_id} is {total_bytes} bytes; the UI's"
                        f" reassembly bound is {max_json_bytes}",
                    )
                )
            expected_digest = str(first["sha256"])
            data = bytearray(base64.b64decode(first["base64"]))
            while not first["eof"]:
                # The loop is bounded by construction: each iteration
                # consumes a full chunk or ends at eof, and total_bytes
                # is already under the reassembly bound above.
                first = operations.artifact_read(
                    identity, artifact_id, len(data), max_chunk_bytes
                )
                data += base64.b64decode(first["base64"])
        except OperationFailure as fail:
            return failure_page(fail)
        actual_digest = hashlib.sha256(bytes(data)).hexdigest()
        if actual_digest != expected_digest:
            # Integrity failure on the gateway's own read path: refuse
            # with the correlation-id-bearing internal row rather than
            # serve unverified bytes.
            artifact_id_for_log = artifact_id.replace("\r", "\\r").replace("\n", "\\n")
            _LOG.error(
                "artifact digest mismatch on read: artifact=%s expected=%s",
                artifact_id_for_log,
                expected_digest,
            )
            return failure_page(
                OperationFailure(
                    failure(
                        "internal_error",
                        f"artifact {artifact_id} failed digest verification",
                    )
                )
            )
        # artifact ids are gateway-minted; the filename is the id when it
        # is filename-safe and a fixed name otherwise (never other bytes).
        tail = artifact_id.removeprefix("art-")
        safe = artifact_id if tail.isalnum() else "artifact"
        return Response(
            content=bytes(data),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{safe}.bin"',
                "X-BenchWeave-Sha256": actual_digest,
            },
        )

    @router.get("/documents/{sha256}", include_in_schema=False)
    async def document_page(sha256: str, request: Request) -> Response:
        """A stored document by content hash, digest shown (GW-60); the
        original bytes render when they fit the page bound, and beyond it
        the page states the bound instead of shipping megabytes of
        ``<pre>`` (the digest is the verifiable identity either way)."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page()
        record, identity = authed
        try:
            document = operations.document_get(identity, sha256)
        except OperationFailure as fail:
            return failure_page(fail)
        raw = base64.b64decode(document["original_utf8_base64"])
        return page(
            "document.j2",
            title="Document",
            document=document,
            content=(
                raw.decode("utf-8", errors="replace")
                if len(raw) <= max_json_bytes
                else None
            ),
            content_bytes=len(raw),
            page_bound=max_json_bytes,
            **_strip(record),
        )
