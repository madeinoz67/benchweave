"""The G2c event bridge: ``events_get`` → SSE (design §2.5, GW-30–34).

One bridge per (session, bench): the route claims the pair in the
session store's registry (a held pair renders the ``conflict`` §C.3 row;
the per-session cap renders it too), and the generator's ``finally``
releases it — a closed tab ends every read made on its behalf (GW-33).
Logout and expiry end the stream the same way: every poll re-resolves
the session, and a dead session ends the loop.

All reads run on the session's Identity, and the listing cursor is
SERVER-HELD: it advances inside the generator and is never serialized
into any response body (I09 — the browser holds no cursor to leak or
replay). The payload provenance is pinned server-side: the only bytes
that ride the stream's swap channel are fragments THIS gateway rendered
through its own Jinja environment (autoescaped) or the package's own
§C.3 partials — the G2a review's bw-host.js innerHTML finding closes
here, at the producer, not in the shipped host script.

The wire protocol (SSE):

- ``retry: <min_poll_ms>`` — the poll floor, advertised first;
- unnamed ``message`` events — one per poll batch, the whole batch as
  ONE event (GW-34's coalescing half; the host script's per-frame swap
  batching is the other half), data the gateway-templated fragment;
- ``bw-gap`` — ``event_gap`` with the failure's closed six-key
  ``details`` object (the §7/§10 watermarks), then a restart from
  ``after=None`` with server-side dedupe: no sequence is delivered twice
  after either restart (the kill criterion), and the persistent §C.3
  ``event_gap`` warning naming the watermarks rides the next fragment;
- ``bw-cursor`` — ``cursor_expired`` (which the seam cannot emit — no
  emitter exists by construction, ``docs/compatibility.md`` D-final; the
  behaviour is proven at the bridge boundary, not an emission claimed),
  then the same restart with the advisory riding the next fragment;
- ``bw-end`` — any other seam failure terminates the stream honestly
  (the code's own envelope rides the event; nothing is softened).

``events_get`` is blocking SQLite called from the serving event loop —
D13's disclosed single-loop posture, unchanged by this slice.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from benchweave_ui_html.partials import render_refusal
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from markupsafe import Markup, escape
from starlette.responses import StreamingResponse

from benchweave.interfaces import ui_refusals
from benchweave.interfaces.errors import OperationFailure, failure
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import (
    BridgeRefused,
    SessionRecord,
    SessionStore,
)

#: The poll tick drains the retained window to a short page before
#: flushing ONE message event (GW-34 coalescing + FOLD-1: no row cap —
#: each seam read is bounded by ``max_page_size``, and the drain loop
#: bounds the tick by the window itself; every drained row renders).


def sse_message(data: str) -> str:
    """One unnamed SSE event whose data is ``data`` (multi-line data
    rides one ``data:`` line per line, per the SSE grammar)."""
    lines = data.splitlines() or [""]
    return "".join(f"data: {line}\n" for line in lines) + "\n"


def sse_named(event: str, data: str) -> str:
    return f"event: {event}\n" + sse_message(data)


def sse_retry(ms: int) -> str:
    """The poll floor as the SSE retry hint — the advertised limit."""
    return f"retry: {ms}\n\n"


def _watermark_html(code: str, details: Mapping[str, Any]) -> Markup:
    """The §C.3 row for a restart code plus the watermarks line naming
    the retained window. Trusted package-rendered HTML over escaped
    interpolables (the ``render_no_response`` rule) — the watermark
    values are seam-provided strings, escaped at construction."""
    row = ui_refusals.row_for(code)
    oldest = escape(str(details.get("oldest_sequence") or "?"))
    current = escape(str(details.get("current_sequence") or "?"))
    stream = escape(str(details.get("stream_id") or "?"))
    return Markup(  # noqa: S704
        render_refusal(row)
        + '<p class="bw-refusal__watermarks" data-bw-restart-watermarks>'
        f"Retained window: sequences {oldest}–{current} on {stream}."
        "</p>"
    )


def _fresh(
    events: list[dict[str, Any]], delivered: dict[str, int]
) -> list[dict[str, Any]]:
    """The events this bridge has not delivered yet — a PURE filter (the
    caller advances the mark over what it actually emits).

    Dedupe is by ``(stream_id, sequence)`` — realized as the highest
    delivered sequence per stream (sequences are per-stream monotonic
    from ``append_event``'s MAX+1 and reads are sequence-ordered, so the
    max filter is membership for ordered delivery: a sequence is
    delivered exactly when it is not above the high-water mark)."""
    fresh: list[dict[str, Any]] = []
    for event in events:
        stream = str(event.get("stream_id", ""))
        try:
            sequence = int(str(event.get("sequence", "0")))
        except ValueError:
            continue  # a sequence-less row cannot be paged honestly
        if sequence > delivered.get(stream, 0):
            fresh.append(event)
    return fresh


def _advance(delivered: dict[str, int], emitted: list[dict[str, Any]]) -> None:
    """Advance the dedupe high-water mark over the rows an emit actually
    carried — never past rows that were read but not emitted (the FOLD-1
    rule: the mark follows the wire, not the read)."""
    for event in emitted:
        stream = str(event.get("stream_id", ""))
        sequence = int(str(event.get("sequence", "0")))
        delivered[stream] = max(delivered.get(stream, 0), sequence)


async def _bridge_events(
    *,
    operations: Operations,
    sessions: SessionStore,
    session_id: str,
    bench_id: str,
    probe: Mapping[str, Any],
    page_limit: int,
    poll_ms: int,
    render: Callable[..., str],
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> AsyncIterator[str]:
    """The bridge loop. The cursor is a local: it advances here and is
    never serialized (I09). Session death, client disconnect (via
    cancellation) and generator close all land in the ``finally``."""
    delivered: dict[str, int] = {}
    gap: Mapping[str, Any] | None = None
    advisory: Mapping[str, Any] | None = None
    pending_fragment = True  # the probe batch always flushes
    cursor: str | None = None
    try:
        yield sse_retry(poll_ms)
        fresh = _fresh(list(probe["events"]), delivered)
        fragment = render(
            "event-batch.j2",
            events=fresh,
            gap_html=None,
            advisory_html=None,
        )
        yield sse_message(fragment)
        _advance(delivered, fresh)
        # The probe's cursor seeds the loop — the listing continues from
        # where the probe stopped (a forgotten seed makes every poll run
        # from after=None, which can never gap and re-pages the head).
        cursor = probe["cursor"] if probe["events"] else None
        while True:
            await sleep(poll_ms / 1000)
            record = sessions.resolve(session_id)
            if record is None:
                break  # logout or expiry: teardown (GW-33)
            identity = Identity(
                principal=record.principal,
                audience=record.audience,
                scopes=record.scopes,
                expires_at=record.expires_at,
            )
            try:
                # One poll tick owns the WHOLE backlog: read pages with
                # the returned cursor until a short/empty page, so a
                # burst spanning pages still flushes as one boundary and
                # no row is silently dropped (FOLD-1). Each read is
                # bounded by ``page_limit``; the drain is bounded by the
                # retained window (every full page strictly advances the
                # cursor). A restart-class failure mid-drain discards the
                # partial batch — the mark never advanced, and the
                # restart's from-None listing re-delivers whatever
                # retention still holds.
                batch: list[dict[str, Any]] = []
                poll_cursor: str | None = cursor
                while True:
                    result = operations.events_get(
                        identity, bench_id, after=poll_cursor, limit=page_limit
                    )
                    batch.extend(_fresh(list(result["events"]), delivered))
                    poll_cursor = result["cursor"]
                    if len(result["events"]) < page_limit:
                        break  # short or empty page: the window is drained
            except OperationFailure as fail:
                code = fail.failure.code
                if code in ("event_gap", "cursor_expired"):
                    # §2.5: restart the listing from after=None. The
                    # failure's own closed details object rides the
                    # named event; the §C.3 warning/advisory rides the
                    # NEXT fragment (the retained window re-read), so
                    # the page renders it even when dedupe leaves the
                    # replay without a single fresh row.
                    if code == "event_gap":
                        gap = dict(fail.failure.details)
                        yield sse_named("bw-gap", json.dumps(gap, sort_keys=True))
                    else:
                        advisory = dict(fail.failure.details)
                        yield sse_named(
                            "bw-cursor", json.dumps(advisory, sort_keys=True)
                        )
                    cursor = None
                    pending_fragment = True
                    continue
                yield sse_named(
                    "bw-end", json.dumps(fail.failure.body()["error"], sort_keys=True)
                )
                break
            cursor = poll_cursor
            if batch or pending_fragment:
                fragment = render(
                    "event-batch.j2",
                    events=batch,
                    gap_html=_watermark_html("event_gap", gap) if gap else None,
                    advisory_html=(
                        _watermark_html("cursor_expired", advisory)
                        if advisory
                        else None
                    ),
                )
                yield sse_message(fragment)
                _advance(delivered, batch)
                # The gap warning is persistent (GW-31); the advisory is
                # one-shot (its §C.3 severity).
                advisory = None
                pending_fragment = False
            else:
                yield ": keep-alive\n\n"
    finally:
        sessions.deregister_bridge(session_id, bench_id)


def register_stream_route(
    router: APIRouter,
    *,
    operations: Operations,
    sessions: SessionStore,
    limits: Mapping[str, int],
    resolve_session: Callable[[Request], SessionRecord | None],
    session_identity: Callable[[SessionRecord], Identity],
    failure_page: Callable[[OperationFailure], HTMLResponse],
    unauthenticated_page: Callable[[], HTMLResponse],
    render: Callable[..., str],
) -> None:
    """Register the SSE route on the UI router (before its catch-all).

    The helpers are ``build_ui_router``'s own closures — one session
    resolution, one refusal translation, one template environment for
    every page and fragment the adapter serves.
    """
    max_page_size = int(limits.get("max_page_size", 1000))
    poll_ms = int(limits.get("min_poll_ms", 100))
    max_bridges = int(limits.get("ui_max_bridges_per_session", 4))

    @router.get(
        "/benches/{bench_id}/events/stream", include_in_schema=False
    )
    async def events_stream(bench_id: str, request: Request) -> Response:
        """One bench's event stream over the seam, session-scoped.

        The probe read runs BEFORE the stream starts so the route's own
        refusals (unauthenticated, forbidden, not_found — the I02
        cross-bench arm included) render as pages with honest statuses;
        the bridge claim runs under the same try so a held pair or a
        capped session renders ``conflict`` instead of a second stream.
        """
        record = resolve_session(request)
        if record is None:
            return unauthenticated_page()
        try:
            probe = operations.events_get(
                session_identity(record), bench_id, after=None, limit=max_page_size
            )
            sessions.register_bridge(record.session_id, bench_id, cap=max_bridges)
        except OperationFailure as fail:
            return failure_page(fail)
        except BridgeRefused as refused:
            return failure_page(
                OperationFailure(
                    failure(
                        "conflict",
                        f"stream refused: {refused.reason}",
                    )
                )
            )
        return StreamingResponse(
            _bridge_events(
                operations=operations,
                sessions=sessions,
                session_id=record.session_id,
                bench_id=bench_id,
                probe=probe,
                page_limit=max_page_size,
                poll_ms=poll_ms,
                render=render,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store"},
        )
