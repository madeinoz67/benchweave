"""The G2c event bridge's route arms (design §2.5, gate §7-G).

``GET /ui/benches/{id}/events/stream`` — one SSE bridge per (session,
bench), all reads on the session's Identity, the cursor SERVER-HELD (it
never appears in any response body — the I09 arm pins that). The
gap/cursor_expired restart arms live in ``test_ui_stream_gaps.py``; this
suite pins composition, ownership, teardown and the refusals the route
itself renders.

Two fixtures, one file:

- ``refusals`` — the TestClient gateway. Every arm here ends in a plain
  rendered response (the refusal pages), which the in-memory transport
  serves fine.
- ``live`` — a REAL uvicorn thread (the parity suite's boot): the 200
  stream is an infinite async generator, and the in-memory ASGI
  transports (TestClient and httpx ASGITransport alike) run the app to
  completion before returning a response — an infinite stream can never
  surface through them (the receive side waits on ``response_complete``,
  which only an ended response sets). A real socket streams the bytes as
  they are produced and delivers real disconnects, which is what the
  teardown arms assert.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient
from ui_gateway_support import (
    LIMITS,
    NOW_EPOCH,
    boot,
    build_ui_gateway,
    live_session,
    stop,
)

from benchweave.interfaces.identity import Identity

BENCH_ID = "sim-bench"
STREAM_PATH = f"/ui/benches/{BENCH_ID}/events/stream"
#: The probe batch's in-fragment marker (what stream reads wait for).
PROBE_MARKER = 'data-bw-event-kind="run_changed"'


def _cookie(session_id: str) -> dict[str, str]:
    return {"bw_session": session_id}


@pytest.fixture(scope="module")
def refusals(tmp_path_factory: pytest.TempPathFactory) -> Any:
    data_dir = tmp_path_factory.mktemp("ui-stream-refusals")
    app = build_ui_gateway(data_dir, name="stream-refusals")
    session = live_session(app)
    with TestClient(app, base_url="http://testserver:8125") as client:
        yield SimpleNamespace(app=app, client=client, session=session)


@pytest.fixture(scope="module")
def live(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    data_dir = tmp_path_factory.mktemp("ui-stream-live")
    app = build_ui_gateway(data_dir, name="stream-live")
    operations = app.state.ui_operations
    session = live_session(app)
    server, thread, port = boot(app)

    def plain(method: str, path: str, **kwargs: Any) -> httpx.Response:
        """One plain request on a THROWAWAY connection. A concurrent
        plain request on a client that also holds an open SSE stream
        deadlocks here: the vendored httpx pool hands the held streaming
        connection to the second request (observed: the GET reads the
        SSE body forever while the server waits for the infinite
        response to finish). One connection per request closes that
        class entirely."""
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as one:
            return one.request(method, path, **kwargs)

    def stream(
        session_id: str, *, bench: str = BENCH_ID
    ) -> tuple[Any, httpx.Client]:
        """An SSE stream's context manager on its own throwaway client —
        the caller runs ``with cm as response:`` and closes the client
        after (both must stay in the caller's scope: the vendored httpx
        closes a stream whose context object is dropped)."""
        holder = httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=10.0
        )
        context = holder.stream(
            "GET",
            f"/ui/benches/{bench}/events/stream",
            cookies=_cookie(session_id),
        )
        return context, holder

    try:
        # After the lifespan's startup admission (the bench and its
        # configuration exist from here — emitting before admission has
        # no document anchor to resolve, by design).
        for _ in range(3):
            operations._emit("run_changed", BENCH_ID, "run-1")
        yield SimpleNamespace(
            app=app,
            plain=plain,
            stream=stream,
            session=session,
            operations=operations,
        )
    finally:
        stop(server, thread)


def _stream_body(
    live: SimpleNamespace,
    session_id: str,
    *,
    until: str,
    bench: str = BENCH_ID,
    timeout: float = 10.0,
    before_close: Any = None,
) -> tuple[str, int]:
    """Open the real stream, accumulate raw bytes until ``until`` is
    seen, optionally run ``before_close(body)`` INSIDE the open-response
    window, and close (the abort). Returns (accumulated text, status).

    ``before_close`` is the deterministic observation point because it
    runs INSIDE the read loop, before the ``break``: the iterator is
    still held by this frame there, the connection is genuinely open,
    and no disconnect teardown can be in flight. The old shape (running
    it after the break) was structurally already the abort — breaking
    out of ``iter_raw`` drops the iterator's last reference, CPython
    finalizes the abandoned httpcore iterator, and that finalization
    CLOSES the connection (the FIN leaves before ``before_close`` ran),
    so the bridge's deregistration raced the caller's assert and lost on
    loaded runners (issue #384's CI signature). After this helper
    returns the stream is CLOSED, and the registry is then only
    observable by draining it (the deregistration is async)."""
    context, holder = live.stream(session_id, bench=bench)
    with context as response:
        status = response.status_code
        if status != 200:
            response.read()
            return response.text, status
        accumulated: list[str] = []
        deadline = time.monotonic() + timeout
        found = False
        for chunk in response.iter_raw():
            accumulated.append(chunk.decode("utf-8", errors="replace"))
            if until in "".join(accumulated):
                found = True
                # The observation point rides the read loop, BEFORE the
                # break — see the docstring: past the break the iterator
                # is finalized and the connection is already closing.
                if before_close is not None:
                    before_close("".join(accumulated))
                break
            if time.monotonic() > deadline:
                break
        assert found, f"stream never carried {until!r}: {''.join(accumulated)!r}"
        result = ("".join(accumulated), status)
    holder.close()
    return result


# --- the 200 stream, over the real server --------------------------------------


def test_stream_is_event_stream_with_probe_batch_and_retry(
    live: SimpleNamespace,
) -> None:
    """The happy path: 200 text/event-stream, the poll floor advertised
    as the SSE retry, and the PROBE batch as ONE message event whose
    payload is the gateway-templated fragment (three emitted events ride
    it — the server-templated provenance pin, G2a NIT: only fragments
    this gateway rendered ever ride the stream)."""
    body, status = _stream_body(live, live.session.session_id, until=PROBE_MARKER)
    assert status == 200
    assert f"retry: {LIMITS['min_poll_ms']}" in body
    # One message event carrying all three probe rows (coalescing: one
    # poll = one flush boundary = one SSE message).
    messages = [block for block in body.split("\n\n") if block.startswith("data: ")]
    assert len(messages) == 1, body
    data = "".join(line.removeprefix("data: ") for line in messages[0].splitlines())
    assert data.count('data-bw-event-kind="run_changed"') == 3
    assert data.count("<script") == 0  # only the template's own markup


def test_second_stream_for_the_same_pair_renders_conflict(
    live: SimpleNamespace,
) -> None:
    """GW-33: while a bridge holds the pair, a second stream for the
    same (session, bench) renders the §C.3 conflict row — an HTML
    refusal with a real status, not a second stream.

    The held pair is registered directly in the store (the authoritative
    mechanism the route calls) because this client stack cannot hold a
    stream open across a second request: the vendored httpx closes the
    response the moment ``iter_raw`` is broken (traced: the server sees
    the disconnect and the bridge deregisters before the next request
    lands). The pair rule itself — register, refuse, free — is pinned
    store-level in ``test_session_bridges.py``; this arm pins the route's
    translation of the refusal it raises."""
    sessions = live.app.state.ui_sessions
    record = live_session(live.app, principal="pair-arm")
    sessions.register_bridge(record.session_id, BENCH_ID, cap=4)
    refused = live.plain(
        "GET", STREAM_PATH, cookies=_cookie(record.session_id)
    )
    assert refused.status_code == 409
    assert 'data-bw-refusal-code="conflict"' in refused.text
    assert "stream refused: conflict" in refused.text
    sessions.deregister_bridge(record.session_id, BENCH_ID)


def test_logout_ends_the_stream_and_frees_the_pair(
    live: SimpleNamespace,
) -> None:
    """Teardown on session death: logout ends the generator's reads (the
    stream terminates server-side) and frees the pair — a NEW session's
    stream for the same bench starts clean, 200 not 409."""
    sessions = live.app.state.ui_sessions
    record = live_session(live.app, principal="logout-arm")

    def while_open(_body: str) -> None:
        # Inside the open-response window (deterministic): the bridge
        # holds the pair, the session is alive — and LOGOUT fires while
        # the stream is genuinely OPEN, which is this test's subject
        # (the abort twin covers the close path). The old shape asserted
        # the registry AFTER the helper had already closed the stream,
        # racing the async disconnect teardown — the CI-red shape
        # (frozenset() at the precondition on a loaded runner).
        assert sessions.bridge_benches(record.session_id) == frozenset({BENCH_ID})
        sessions.logout(record.session_id)

    body, status = _stream_body(
        live, record.session_id, until=PROBE_MARKER, before_close=while_open
    )
    assert status == 200
    # The generator notices the dead session within one poll interval;
    # drain on the observable (bounded wait on the registry, not a
    # sleep-assert).
    deadline = time.monotonic() + 5.0
    while sessions.bridge_benches(record.session_id) != frozenset():
        assert time.monotonic() < deadline, "bridge outlived its session"
        time.sleep(0.02)
    fresh = live_session(live.app, principal="logout-arm-2")
    again, again_status = _stream_body(live, fresh.session_id, until=PROBE_MARKER)
    assert again_status == 200
    assert "retry:" in again


def test_abort_deregisters_and_the_pair_starts_clean(
    live: SimpleNamespace,
) -> None:
    """GW-33: a closed tab (the aborted request) ends every read made on
    its behalf — the generator's ``finally`` deregisters, so the next
    stream for the same pair starts clean."""
    sessions = live.app.state.ui_sessions
    record = live_session(live.app, principal="abort-arm")

    def while_open(_body: str) -> None:
        # Deterministic precondition: while_open runs INSIDE the read
        # loop (the helper still holds the iterator), so the stream is
        # genuinely open here. The bounded pause is the issue-#384
        # regression arm: the CI red was the abort teardown overtaking
        # the snapshot on a loaded runner; a teardown in flight during
        # this pause would empty the registry under the assert.
        time.sleep(0.5)
        assert sessions.bridge_benches(record.session_id) == frozenset({BENCH_ID})

    body, status = _stream_body(
        live, record.session_id, until=PROBE_MARKER, before_close=while_open
    )
    assert status == 200
    # The stream context closed inside _stream_body (the abort). The
    # deregistration is async — drain on the observable.
    deadline = time.monotonic() + 5.0
    while sessions.bridge_benches(record.session_id) != frozenset():
        assert time.monotonic() < deadline, "abort did not tear the bridge down"
        time.sleep(0.02)
    again, again_status = _stream_body(live, record.session_id, until=PROBE_MARKER)
    assert again_status == 200, "the pair did not start clean after the abort"


# --- the rendered refusals (plain responses) -----------------------------------


def test_cap_refusal_renders_conflict_for_the_fifth(
    refusals: SimpleNamespace,
) -> None:
    """The per-session cap (``ui_max_bridges_per_session`` = 4 here): a
    session already holding four bridges (registered directly in the
    store — the authoritative mechanism the route calls; the fixture
    admits one bench, so four real streams cannot exist on it) has a
    fifth refused, rendered. The store-level cap semantics are pinned in
    ``test_session_bridges.py``; this arm pins the route's translation."""
    sessions = refusals.app.state.ui_sessions
    code = sessions.mint_login_code(
        Identity(
            principal="capped",
            audience="stg",
            scopes=frozenset({"stg:observe"}),
            expires_at=NOW_EPOCH + 12 * 3600,
        )
    )
    capped = sessions.exchange(code)
    for index in range(4):
        sessions.register_bridge(capped.session_id, f"other-bench-{index}", cap=4)
    refused = refusals.client.get(STREAM_PATH, cookies=_cookie(capped.session_id))
    assert refused.status_code == 409
    assert 'data-bw-refusal-code="conflict"' in refused.text
    assert "cap" in refused.text


def test_cross_bench_stream_renders_not_found(
    refusals: SimpleNamespace,
) -> None:
    """I02's stream half: a bench the caller cannot address renders
    not_found as unavailable-to-caller — the probe's own failure through
    the shared refusal page, never a stream."""
    response = refusals.client.get(
        "/ui/benches/other-bench-9/events/stream",
        cookies=_cookie(refusals.session.session_id),
    )
    assert response.status_code == 404
    assert 'data-bw-refusal-code="not_found"' in response.text


def test_scopeless_session_renders_forbidden(
    refusals: SimpleNamespace,
) -> None:
    """The tier rule (§C.3): events_get requires the observe tier — a
    session whose projection carries no tier scope renders the forbidden
    row. (Control satisfies observe; the control-tier hierarchy satisfies
    observe too — pinned by the seam's TIER_SATISFIES.)"""
    sessions = refusals.app.state.ui_sessions
    code = sessions.mint_login_code(
        Identity(
            principal="no-tier",
            audience="stg",
            scopes=frozenset(),
            expires_at=NOW_EPOCH + 12 * 3600,
        )
    )
    scopeless = sessions.exchange(code)
    response = refusals.client.get(STREAM_PATH, cookies=_cookie(scopeless.session_id))
    assert response.status_code == 403
    assert 'data-bw-refusal-code="forbidden"' in response.text


def test_sessionless_stream_renders_unauthenticated(
    refusals: SimpleNamespace,
) -> None:
    response = refusals.client.get(STREAM_PATH)
    assert response.status_code == 401
    assert 'data-bw-refusal-code="unauthenticated"' in response.text


# --- the page wiring -------------------------------------------------------------


def test_session_death_inside_the_probe_renders_unauthenticated(
    refusals: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FOLD-4 (two-lane NIT): a session that dies inside the probe window
    (between the route's resolve and its bridge claim) renders the 401
    unauthenticated row — not conflict. The probe-window death is the
    one timing window where the old mapping showed 409 for a dead
    session; the refusal must not depend on WHERE the session died.

    Induced on the adapter's own seam object (the refused-code matrix's
    idiom — the router closes over THIS object): the wrapper kills the
    session inside ``events_get``; the route's own register call then
    refuses ``unauthenticated`` for real."""
    sessions = refusals.app.state.ui_sessions
    record = live_session(refusals.app, principal="probe-death")
    operations = refusals.app.state.ui_operations
    original = operations.events_get

    def killing_probe(*args: object, **kwargs: object) -> object:
        sessions.logout(record.session_id)  # the session dies mid-probe
        return original(*args, **kwargs)

    monkeypatch.setattr(operations, "events_get", killing_probe)
    response = refusals.client.get(STREAM_PATH, cookies=_cookie(record.session_id))
    assert response.status_code == 401
    assert 'data-bw-refusal-code="unauthenticated"' in response.text
    assert sessions.bridge_benches(record.session_id) == frozenset()


def test_bench_page_wires_the_stream_and_the_live_region(
    refusals: SimpleNamespace,
) -> None:
    """The bench page carries the host script's contract: the stream URL
    on a data-bw-live-events region with its swap target, so the shipped
    bw-host.js (untouched in G2c) connects one EventSource per page."""
    page = refusals.client.get(
        f"/ui/benches/{BENCH_ID}", cookies=_cookie(refusals.session.session_id)
    )
    assert page.status_code == 200
    assert f'data-bw-stream-url="/ui/benches/{BENCH_ID}/events/stream"' in page.text
    assert 'data-bw-stream-target="[data-bw-live-events]"' in page.text
    assert "data-bw-live-pending" in page.text


def test_served_host_script_announces_stream_termination(
    refusals: SimpleNamespace,
) -> None:
    """FOLD-3(b): the shipped bw-host.js carries a ``bw-end`` listener
    announcing stream termination through the existing ARIA channel —
    without it the browser's stream stops silently. This arm pins the
    listener's PRESENCE and its announcement wording in the served
    bytes (there is no JS unit lane; the browser lane exercises the
    asset end-to-end on the pages)."""
    asset = refusals.client.get("/ui/assets/bw-host.js")
    assert asset.status_code == 200
    assert 'addEventListener("bw-end"' in asset.text
    assert "Event stream ended" in asset.text


def test_the_announce_region_is_the_only_live_region(
    refusals: SimpleNamespace,
) -> None:
    """GW-34/SW-26 as a template assertion (no sample lane exists to
    drive it live): state changes announce through the page's ONE ARIA
    live region (base.j2's data-bw-announce); no other element on any
    page is a live region — a reading or sample element can never be
    announced, because nothing but the announce region is live."""
    cookie = _cookie(refusals.session.session_id)
    pages = (
        "/ui/",
        f"/ui/benches/{BENCH_ID}",
        "/ui/runs/run-1",
        "/ui/requests/req-1",
    )
    for path in pages:
        page = refusals.client.get(path, cookies=cookie)
        assert page.text.count("aria-live") == 1, path
        assert "data-bw-announce" in page.text, path
