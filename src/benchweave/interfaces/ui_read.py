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
import json
import logging
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from markupsafe import Markup

from benchweave.content.store import ContentStore
from benchweave.interfaces.errors import OperationFailure, failure
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import TIER_SATISFIES, Operations
from benchweave.interfaces.sessions import SessionRecord, SessionStore
from benchweave.interfaces.ui_control import ControlViews, mode_banner_markup
from benchweave.interfaces.ui_presentation import compose_device_presentation
from benchweave.interfaces.ui_readings import latest_retained_readings, populate_tiles
from benchweave.state.store import Store

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
    store: Store | None,
    limits: Mapping[str, int],
    now_epoch: Callable[[], int],
    resolve_session: Callable[[Request], SessionRecord | None],
    session_identity: Callable[[SessionRecord], Identity],
    page: Callable[..., HTMLResponse],
    failure_page: Callable[[OperationFailure], HTMLResponse],
    unauthenticated_page: Callable[[Request], HTMLResponse],
    controls: ControlViews | None = None,
    sessions: SessionStore | None = None,
) -> None:
    """Register the read routes on the UI router (before its catch-all).

    The helpers are ``build_ui_router``'s own closures — the same
    session resolution, page shell and failure translation the index
    uses, so every page shares one refusal shape and one chrome.
    ``store`` (the single-writer state store) and ``now_epoch`` (the
    resolved render clock) feed the device page's reading-tile join
    (#369); both stay None/unused wherever the join is not composed.
    ``controls`` (the G3a control views) feeds the bench page's
    control-region embed, the bench- and device-scoped ``no-lease``
    banner, and the shell's session-expiry warning; ``None`` keeps the
    G2 shape (no region, no banner, no warning).
    """
    max_page_size = int(limits.get("max_page_size", 1000))
    max_chunk_bytes = int(limits.get("max_chunk_bytes", 65_536))
    max_json_bytes = int(limits.get("max_json_bytes", 1_048_576))
    reading_scan_rows = int(limits.get("ui_reading_scan_rows", 200))

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
        and scopes, the shell's session-expiry warning (D1; ``None``
        outside its windows), no mode-banner entries (GW-80: no
        gateway-reported fact fires one on these pages — bench-scoped
        pages set their own when ``controls`` is composed), and the CSRF
        token (NFR-S4 machinery)."""
        identity = session_identity(record)
        info = operations.gateway_info(identity)
        return {
            "gateway_id": str(info["gateway_id"]),
            "principal": record.principal,
            "scopes": sorted(record.scopes),
            "mode_banner": None,
            "session_warning": (
                controls.session_warning(record) if controls is not None else None
            ),
            "csrf_token": record.csrf_token,
        }

    # --- benches (GW-20) --------------------------------------------------------

    @router.get("/benches/{bench_id}", include_in_schema=False)
    async def bench_page(bench_id: str, request: Request) -> Response:
        """One bench: the projection, its devices, and the first events
        page (design §2.4) — three read calls on the session's identity."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page(request)
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
        context = _strip(record)
        if controls is not None:
            # GW-42's bench-scoped mode entry + the control region
            # embedded at first render (the poll re-fetches it).
            mode = controls.bench_mode(record, bench_id)
            if mode is not None:
                context["mode_banner"] = mode_banner_markup(mode)
            # Trusted host-rendered fragment markup (the module's own
            # escaped composition; S704's hatch not in play). The page's
            # own first events page feeds the staging panel's selector
            # refs; the trip predicate walks the tail itself.
            context["controls_html"] = Markup(  # noqa: S704
                controls.render(record, bench, events["events"])
            )
        return page(
            "bench.j2",
            title=f"Bench {bench_id}",
            bench=bench,
            devices=devices,
            events=events["events"],
            **context,
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
            return unauthenticated_page(request)
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
        if store is not None and content is not None:
            # The reading-tile join (#369, Fork A): composition-time,
            # read-only, bench-scoped — the CON-5 amendment's ruled
            # boundary. Failures NEVER fail the page: an exception here
            # renders the conservative tile and logs loudly (GW-22's
            # honest floor is the join's failure mode too).
            try:
                devices, _next = operations.device_list(
                    identity, bench_id, limit=max_page_size, cursor=None
                )
                owners: dict[str, int] = {}
                for item in devices:
                    if str(item["device_id"]) == device_id:
                        item_document = document
                    else:
                        item_document = operations.document_get(
                            identity, str(item["descriptor"]["sha256"])
                        )
                    item_raw = base64.b64decode(
                        item_document["original_utf8_base64"]
                    )
                    for parameter in json.loads(item_raw).get("parameters", []):
                        owner_key = str(parameter.get("name", ""))
                        owners[owner_key] = owners.get(owner_key, 0) + 1
                # The census is bench-CURRENT: a sibling that declared the
                # parameter at run time but is no longer commissioned
                # escapes the count (design D7 — historic cross-device
                # ambiguity is not caught here). Does NOT catch either:
                # a sibling bound by the same run whose plugin STREAMS a
                # parameter it does not declare (refute lane 1, F1) — the
                # landing lane records subscription_id on the evidence
                # reference but no device identity (every run device
                # shares the one run:<id> context key; the subscription
                # registry is in-memory), so attribution is
                # parameter-name-only and cannot distinguish the
                # streamer. The guard needs a persisted
                # subscription->device resolution — an interface/host
                # slice; carried by the #369 fold addendum
                # (.claude/deep-review/2026-10-04-issue369-fold-addendum.md).
                now_epoch_ms = now_epoch() * 1000
                presentation = populate_tiles(
                    presentation,
                    latest_retained_readings(
                        store,
                        content,
                        bench_id=bench_id,
                        device_id=device_id,
                        sibling_parameter_owners=owners,
                        now_epoch_ms=now_epoch_ms,
                        scan_rows=reading_scan_rows,
                    ),
                    json.loads(descriptor_raw),
                    now_epoch_ms=now_epoch_ms,
                )
            except Exception:
                _LOG.exception(
                    "reading-tile join failed for bench %s device %s;"
                    " rendering conservative tiles",
                    bench_id,
                    device_id,
                )
        context = _strip(record)
        if controls is not None:
            # GW-42 fires on the device page too (the bench's authority
            # posture is the device's).
            mode = controls.bench_mode(record, bench_id)
            if mode is not None:
                context["mode_banner"] = mode_banner_markup(mode)
        return page(
            "device.j2",
            title=f"Device {device_id}",
            device=device,
            presentation=presentation,
            **context,
        )

    # --- runs and reconcile (GW-55 render half, GW-12's view) ------------------

    @router.get("/runs/{run_id}", include_in_schema=False)
    async def run_page(run_id: str, request: Request) -> Response:
        """A run exactly as ``run_get`` reports it: state, revision,
        outcome, safe state, terminal record. G3b adds the cancel
        region (GW-53/55): one action, ungated, and the pending-cancel
        marker that gives way to the state once the run reports
        terminal. No inferred outcome — an absent terminal record
        renders absent."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page(request)
        record, identity = authed
        try:
            run = operations.run_get(identity, run_id)
        except OperationFailure as fail:
            return failure_page(fail)
        terminal = str(run.get("state", "")) == "terminal"
        cancel_requested = False
        if sessions is not None:
            if terminal:
                # GW-55: the marker gives way to the state itself once
                # run_get reports terminal.
                sessions.clear_cancel_request(record.session_id, run_id)
            else:
                cancel_requested = sessions.cancel_requested(
                    record.session_id, run_id
                )
        return page(
            "run.j2",
            title=f"Run {run_id}",
            run=run,
            run_id=run_id,
            run_terminal=terminal,
            cancel_requested=cancel_requested,
            has_control=bool(record.scopes & TIER_SATISFIES["control"]),
            **_strip(record),
        )

    @router.get("/requests/{request_id}", include_in_schema=False)
    async def request_page(request_id: str, request: Request) -> Response:
        """The reconcile view (GW-12): resolve a §9 ``request_id`` to the
        run it accepted. ``run_find`` is control-tier in the frozen
        catalog, so an observe session renders the ``forbidden`` §C.3
        row — the honest tier refusal, never a softened rewrite."""
        authed = _authed(request)
        if authed is None:
            return unauthenticated_page(request)
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
            return unauthenticated_page(request)
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
            return unauthenticated_page(request)
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
            # H2 (#368): the verdict references the ADMISSION identity —
            # the digest embedded in the artifact id (art-<sha256>, minted
            # at put_artifact) — never the chunk response's own sha256,
            # which the store derives from the same row being read: a
            # store-row corruption is internally consistent and would
            # pass a self-referential check (the lane's tamper repro).
            expected_digest = artifact_id.removeprefix("art-")
            data = bytearray(base64.b64decode(first["base64"]))
            while not first["eof"]:
                # H3 (#368, G4 accuracy): the loop's boundedness rests on
                # the SEAM's honest eof/total_bytes reporting — each pass
                # consumes a full chunk or ends at eof, and total_bytes is
                # already under the reassembly bound above. The adapter
                # does NOT defend against a seam that reports eof=false
                # forever; that is a seam defect outside this adapter's
                # threat model, surfaced by its own suites.
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
            return unauthenticated_page(request)
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
