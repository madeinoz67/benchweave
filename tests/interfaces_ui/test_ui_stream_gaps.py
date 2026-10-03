"""The G2c gate-G arms: event_gap and cursor_expired, induced and
rendered (design §7-G, §2.5).

Three induction lanes, each honest about what it proves:

- **Generator-level, real seam** — ``_bridge_events`` driven directly
  with an injected instant sleep (deterministic: the test interleaves
  emissions and trims between ``__anext__`` calls, no timing). The
  event_gap induction is the seam's REAL raise path — emissions driven,
  ``Store.trim_stream`` past the bridge's cursor (the same induction the
  seam's own suite uses). Pinned: the ``bw-gap`` event carries the
  failure's exact closed six-key details; the restart lists from
  ``after=None``; no sequence is delivered twice; the persistent §C.3
  ``event_gap`` warning names the watermarks (GW-31); coalescing is one
  message event per poll batch (GW-34).
- **Generator-level, seam double** — ``cursor_expired`` has NO emitter
  in the seam (``docs/compatibility.md`` D-final: trim deletes
  contiguous prefixes, so the overtake branch is always ``event_gap``).
  The design resolves the exit item as test-boundary induction: a
  wrapper over the real operations object raises it at the bridge
  boundary (the only call the bridge makes) and delegates everything
  else. This proves the bridge's BEHAVIOUR (restart, dedupe, advisory);
  it does not claim an emission exists.
- **Route-level, real server** — the real induction through HTTP: a
  dedicated fixture whose ``min_poll_ms`` is 5 s, so the trim lands
  inside one poll window deterministically (the default 100 ms fixture
  would race the poll). The stream yields the ``bw-gap`` event over the
  wire; the page-facing fragment renders the warning; the continuation
  is deduped.

The I09 extension (cursor privacy): no response body on any ``/ui``
route — pages and stream alike — contains a cursor-shaped value, with
the detector proven against a real REST cursor first (an arm that
cannot detect cannot pass).
"""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from ui_gateway_support import NOW_EPOCH, boot, live_session, stop

from benchweave.content.store import ContentStore
from benchweave.interfaces import errors
from benchweave.interfaces import operations as operations_module
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.errors import OperationFailure
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import SessionStore
from benchweave.interfaces.ui import _ENV
from benchweave.interfaces.ui_stream import _bridge_events
from benchweave.interfaces.validation import SeamValidator
from benchweave.state.store import Store

BENCH_ID = "sim-bench"
STREAM_ID = "bench.sim-bench"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
CORPUS = Path(__file__).resolve().parents[2] / "standards" / "interface" / "0.1.0"
IDENT = Identity("p1", "stg", frozenset({"stg:observe"}), 2**31)
PROBE_MARKER = 'data-bw-event-kind="run_changed"'


def _render(template: str, **context: Any) -> str:
    return _ENV.get_template(template).render(**context)


async def _instant_sleep(seconds: float) -> None:
    """The injected sleep: yields control, never waits — the test owns
    time (each ``__anext__`` is exactly one poll)."""
    import asyncio

    await asyncio.sleep(0)


def _seam(tmp_path: Path) -> tuple[Operations, Store, SessionStore, str]:
    """A real seam + store + a live session (the seam suite's shape, plus
    the session store the bridge resolves against)."""
    store = Store.open(tmp_path / "state.db", check_same_thread=False)
    content = ContentStore(store)
    admit_startup_bench(store, content, FIXTURES, now="2026-10-03T00:00:00Z")
    ops = Operations(
        store,
        content,
        gateway_id="g2c-gaps",
        validator=SeamValidator(CORPUS),
        limits={
            "max_json_bytes": 1048576,
            "max_page_size": 1000,
            "max_chunk_bytes": 65536,
            "max_lease_ms": 600000,
            "min_poll_ms": 100,
            "max_admission_ms": 5000,
        },
        now_iso=lambda: "2026-10-03T00:00:00Z",
    )
    sessions = SessionStore(now_epoch=lambda: NOW_EPOCH)
    code = sessions.mint_login_code(
        Identity("p1", "stg", frozenset({"stg:observe"}), 2**31)
    )
    record = sessions.exchange(code)
    return ops, store, sessions, record.session_id


def _stream(gen: Any) -> str:
    """Advance the bridge by one poll and return its chunk."""
    import asyncio

    chunk: str = asyncio.run(gen.__anext__())
    return chunk


def _close(gen: Any) -> None:
    """Close the bridge generator (its ``finally`` deregisters)."""
    import asyncio

    async def _aclose() -> None:
        await gen.aclose()

    asyncio.run(_aclose())


def _parse_sse(body: str) -> list[tuple[str | None, str]]:
    """(event name, joined data) per SSE event block, in order."""
    events: list[tuple[str | None, str]] = []
    for block in body.split("\n\n"):
        if not block or block.startswith(":"):
            continue
        name: str | None = None
        data: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data.append(line.removeprefix("data: "))
        events.append((name, "\n".join(data)))
    return events


# --- generator-level: the real event_gap induction ------------------------------


def test_event_gap_real_induction_restart_and_dedupe(
    tmp_path: Path,
) -> None:
    """§7-G's core arm, at the seam's real raise path: emissions driven,
    ``trim_stream`` past the bridge's cursor → the ``bw-gap`` SSE event
    carries the failure's EXACT closed six-key details; the restart
    lists from ``after=None``; no sequence is delivered twice; the
    continuation delivers the post-trim sequences exactly once."""
    ops, store, _sessions, session_id = _seam(tmp_path)
    for _ in range(6):
        ops._emit("run_changed", BENCH_ID, "run-1")

    gen = _bridge_events(
        operations=ops,
        sessions=_sessions,
        session_id=session_id,
        bench_id=BENCH_ID,
        probe=ops.events_get(IDENT, BENCH_ID, after=None, limit=4),
        page_limit=4,
        poll_ms=100,
        render=_render,
        sleep=_instant_sleep,
    )
    body = _stream(gen)  # the retry preamble
    assert "retry: 100" in body
    first = _stream(gen)  # the probe batch (page 1: sequences 1-4)
    assert first.count('data-bw-event-sequence="') == 4

    second = _stream(gen)  # the next poll: sequences 5-6, cursor now 6
    assert second.count('data-bw-event-sequence="') == 2

    # The retention window overtakes the cursor: two unseen emissions
    # land (7, 8), then only the newest survives the trim — oldest=8 is
    # past cursor+1, so the seam raises event_gap with the retained
    # watermarks (§7: the raise preempts the response).
    ops._emit("run_changed", BENCH_ID, "run-1")  # 7, unseen
    ops._emit("run_changed", BENCH_ID, "run-1")  # 8, unseen
    store.trim_stream(STREAM_ID, keep=1)  # retained [8], oldest=8
    ops._emit("run_changed", BENCH_ID, "run-1")  # 9, retained

    gap = _stream(gen)
    assert gap.startswith("event: bw-gap\n")
    gap_data = json.loads(gap.removeprefix("event: bw-gap\ndata: ").strip())
    assert gap_data == {
        "findings": [],
        "current_revision": None,
        "stream_id": STREAM_ID,
        "oldest_sequence": "8",
        "current_sequence": "9",
        "retry_after_ms": None,
    }

    # The restart: the listing runs from after=None over the retained
    # window [8, 9]. Sequence 7 is honestly LOST (retention deleted it —
    # GW-31: the warning does not skip the gap); 8 and 9 were never
    # delivered, so both render; nothing already delivered re-renders
    # (1-6 are gone from the window by construction of the gap — the
    # multiset check below is the dedupe proof).
    after_gap = _stream(gen)
    assert 'data-bw-refusal-code="event_gap"' in after_gap
    assert "Retained window: sequences 8" in after_gap
    assert 'data-bw-event-sequence="8"' in after_gap
    assert 'data-bw-event-sequence="9"' in after_gap

    # Continuation: the next poll keeps the persistent warning and
    # delivers nothing old.
    ops._emit("run_changed", BENCH_ID, "run-1")  # sequence 10
    later = _stream(gen)
    assert 'data-bw-refusal-code="event_gap"' in later  # persistent (GW-31)
    assert 'data-bw-event-sequence="10"' in later

    # No sequence delivered twice across the WHOLE stream (the kill
    # criterion): the delivered multiset has no duplicates.
    delivered = re.findall(
        r'data-bw-event-sequence="(\d+)"',
        "".join([first, second, after_gap, later]),
    )
    assert len(delivered) == len(set(delivered)), delivered
    _close(gen)


def test_coalescing_one_message_per_poll_batch(tmp_path: Path) -> None:
    """GW-34's server half: a burst of N events landing in one poll
    window flushes as ONE message event carrying all N rows — one flush
    boundary per batch."""
    ops, _store, sessions, session_id = _seam(tmp_path)
    probe = ops.events_get(IDENT, BENCH_ID, after=None, limit=4)
    gen = _bridge_events(
        operations=ops,
        sessions=sessions,
        session_id=session_id,
        bench_id=BENCH_ID,
        probe=probe,
        page_limit=4,
        poll_ms=100,
        render=_render,
        sleep=_instant_sleep,
    )
    _stream(gen)  # retry
    _stream(gen)  # probe batch
    for _ in range(4):  # exactly one page: the burst fits one poll
        ops._emit("run_changed", BENCH_ID, "run-1")
    burst = _stream(gen)
    events = _parse_sse(burst)
    messages = [(name, data) for name, data in events if name is None]
    assert len(messages) == 1, events
    assert messages[0][1].count('data-bw-event-sequence="') == 4
    _close(gen)


def test_stream_payload_escapes_hostile_event_data(tmp_path: Path) -> None:
    """The provenance pin's teeth: event data carrying markup renders
    ESCAPED — the swap channel cannot carry markup the gateway did not
    put in its own template, whatever the seam rows contain."""
    ops, _store, sessions, session_id = _seam(tmp_path)
    store_row = {
        "stream_id": STREAM_ID,
        "at": "2026-10-03T00:00:00Z",
        "kind": 'run_changed"><script>alert(1)</script>',
        "run_id": 'x" onmouseover="alert(2)',
        "evidence": {"id": "doc-1", "version": "1", "sha256": "0" * 64},
        "sequence": "1",
    }
    probe = {"events": [store_row], "cursor": "unused", "stream_id": STREAM_ID}
    gen = _bridge_events(
        operations=ops,
        sessions=sessions,
        session_id=session_id,
        bench_id=BENCH_ID,
        probe=probe,
        page_limit=4,
        poll_ms=100,
        render=_render,
        sleep=_instant_sleep,
    )
    _stream(gen)
    fragment = _stream(gen)
    # The markup renders as TEXT: the angle brackets and the quoting are
    # escaped, so nothing the rows carry becomes markup of their own.
    assert "<script>" not in fragment
    assert "&lt;script&gt;" in fragment
    assert 'onmouseover="' not in fragment  # the raw attribute form
    assert "onmouseover=" in fragment  # escaped, as inert text
    _close(gen)


# --- generator-level: the cursor_expired seam double ----------------------------


class _CursorExpiredOnce:
    """The DISCLOSED seam double: ``cursor_expired`` has no emitter in
    the seam, so this wrapper raises it at the bridge boundary (the one
    call the bridge makes — the first cursor-bearing poll) and delegates
    everything else to the real seam object."""

    def __init__(self, real: Operations) -> None:
        self._real = real
        self.raised = False

    def events_get(
        self, identity: Identity, bench_id: str, *, after: str | None, limit: int
    ) -> dict[str, Any]:
        if after is not None and not self.raised:
            self.raised = True
            raise OperationFailure(
                errors.failure(
                    "cursor_expired",
                    "induced cursor_expired at the bridge boundary",
                )
            )
        return self._real.events_get(identity, bench_id, after=after, limit=limit)


def test_cursor_expired_restarts_dedupes_and_renders_advisory(
    tmp_path: Path,
) -> None:
    """GW-32, test-boundary induced (no emitter exists — §1 disclosure):
    the bridge restarts from ``after=None``, dedupes by
    ``(stream_id, sequence)``, and the §C.3 ``cursor_expired`` advisory
    rides the next fragment ONCE (advisory severity, not a persistent
    warning)."""
    ops, _store, sessions, session_id = _seam(tmp_path)
    for _ in range(4):
        ops._emit("run_changed", BENCH_ID, "run-1")
    double = _CursorExpiredOnce(ops)
    gen = _bridge_events(
        operations=cast(Any, double),
        sessions=sessions,
        session_id=session_id,
        bench_id=BENCH_ID,
        probe=ops.events_get(IDENT, BENCH_ID, after=None, limit=4),
        page_limit=4,
        poll_ms=100,
        render=_render,
        sleep=_instant_sleep,
    )
    _stream(gen)  # retry
    _stream(gen)  # probe: sequences 1-4

    ops._emit("run_changed", BENCH_ID, "run-1")  # sequence 5, unseen
    notice = _stream(gen)  # the first cursor-bearing poll raises
    assert notice.startswith("event: bw-cursor\n")
    notice_data = json.loads(
        notice.removeprefix("event: bw-cursor\ndata: ").strip()
    )
    assert set(notice_data) == {
        "findings",
        "current_revision",
        "stream_id",
        "oldest_sequence",
        "current_sequence",
        "retry_after_ms",
    }

    restarted = _stream(gen)  # poll from after=None: the replay's page
    assert 'data-bw-refusal-code="cursor_expired"' in restarted
    for old in ("1", "2", "3", "4"):
        assert f'data-bw-event-sequence="{old}"' not in restarted  # dedupe

    # The replay pages forward and delivers the unseen sequence 5; the
    # advisory is one-shot — this fragment carries no refusal row.
    caught_up = _stream(gen)
    assert 'data-bw-event-sequence="5"' in caught_up
    assert "data-bw-refusal-code" not in caught_up

    ops._emit("run_changed", BENCH_ID, "run-1")  # sequence 6
    next_fragment = _stream(gen)
    assert 'data-bw-event-sequence="6"' in next_fragment
    assert "data-bw-refusal-code" not in next_fragment

    delivered = re.findall(
        r'data-bw-event-sequence="(\d+)"',
        "".join([restarted, caught_up, next_fragment]),
    )
    assert len(delivered) == len(set(delivered)), delivered
    _close(gen)


# --- route-level: the real induction through HTTP -------------------------------


@pytest.fixture(scope="module")
def slow_poll_gateway(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Any]:
    """A live server whose bridge polls every 5 s: the trim lands inside
    one poll window deterministically (the default 100 ms fixture would
    race the poll for the unconsumed emissions)."""
    from ui_gateway_support import LIMITS

    from benchweave.interfaces.app import create_app

    data_dir = tmp_path_factory.mktemp("ui-stream-gap")
    limits = dict(LIMITS)
    limits["min_poll_ms"] = 5000
    store = Store.open(
        str(data_dir / "state-gap.sqlite"), check_same_thread=False
    )
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=b"g2a-ui-suite-secret",
        limits=limits,
        gateway_id="ui-gap",
        fixtures_dir=FIXTURES,
        now_iso=lambda: "2026-10-03T00:00:00Z",
        now_epoch=lambda: NOW_EPOCH,
        ui_enabled=True,
    )
    operations = app.state.ui_operations
    session = live_session(app)
    server, thread, port = boot(app)
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30.0)
    try:
        for _ in range(4):
            operations._emit("run_changed", BENCH_ID, "run-1")
        yield SimpleNamespace(
            app=app,
            client=client,
            session=session,
            operations=operations,
            limits=limits,
        )
    finally:
        client.close()
        stop(server, thread)


def _read_until(gen: Any, marker: str, *, deadline_s: float = 30.0) -> str:
    """Accumulate chunks from the open stream's raw generator until
    ``marker`` appears."""
    accumulated = ""
    deadline = time.monotonic() + deadline_s
    for chunk in gen:
        accumulated += str(chunk.decode("utf-8", errors="replace"))
        if marker in accumulated:
            return str(accumulated)
        if time.monotonic() > deadline:
            break
    raise AssertionError(f"stream never carried {marker!r}: {accumulated!r}")


def test_route_level_event_gap_over_the_wire(
    slow_poll_gateway: SimpleNamespace,
) -> None:
    """§7-G's route-level arm: the REAL induction (drive emissions,
    ``trim_stream`` past the cursor) through HTTP — the SSE stream
    yields the ``bw-gap`` event with the failure's exact watermarks, the
    page-facing fragment renders the persistent warning naming them,
    and the stream continues from the restarted listing with dedupe (no
    sequence delivered twice)."""
    ops = slow_poll_gateway.operations
    store: Store = ops._store
    context = slow_poll_gateway.client.stream(
        "GET",
        f"/ui/benches/{BENCH_ID}/events/stream",
        cookies={"bw_session": slow_poll_gateway.session.session_id},
    )
    with context as response:
        assert response.status_code == 200
        raw = response.iter_raw()
        head = _read_until(raw, PROBE_MARKER)  # probe: sequences 1-4
        assert head.count('data-bw-event-sequence="') == 4

        # Inside one poll window (5 s): emit past the cursor, then trim
        # so the retention window overtakes it — the seam's raise path.
        ops._emit("run_changed", BENCH_ID, "run-1")  # 5
        ops._emit("run_changed", BENCH_ID, "run-1")  # 6
        store.trim_stream(STREAM_ID, keep=1)  # retained [6], oldest=6
        ops._emit("run_changed", BENCH_ID, "run-1")  # 7, retained

        gap = _read_until(raw, "event: bw-gap")
        assert '"oldest_sequence": "6"' in gap
        assert '"stream_id": "bench.sim-bench"' in gap

        continued = _read_until(raw, 'data-bw-event-sequence="7"')
        assert 'data-bw-refusal-code="event_gap"' in continued
        assert "Retained window: sequences 6" in continued
        # Dedupe: nothing delivered twice across the whole stream.
        delivered = re.findall(
            r'data-bw-event-sequence="(\d+)"', head + gap + continued
        )
        assert len(delivered) == len(set(delivered)), delivered


# --- I09's cursor half, extended to /ui ------------------------------------------


def _cursor_shaped(token: str) -> bool:
    """Does ``token`` decode to the cursor shape (8-byte MAC + a JSON
    [stream, sequence, principal] triple)? Structure only — the MAC key
    is not the detector's business."""
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode())
    except Exception:
        return False
    if len(raw) <= 8:
        return False
    try:
        payload = json.loads(raw[8:])
    except Exception:
        return False
    return (
        isinstance(payload, list)
        and len(payload) == 3
        and all(isinstance(item, str) for item in payload)
    )


def test_cursor_detector_fires_on_a_real_cursor(tmp_path: Path) -> None:
    """The detector's control: a REAL seam cursor is cursor-shaped — an
    I09 arm that cannot detect cannot pass."""
    token = operations_module.encode_cursor(STREAM_ID, "7", "p1")
    assert _cursor_shaped(token)
    assert not _cursor_shaped("not-a-cursor-at-all-xxxxx")


def test_no_ui_response_body_contains_a_cursor(tmp_path: Path) -> None:
    """I09's /ui extension (NFR-Q3; invariants.md: 'I09's cursor half
    lands with the G2c bridge'): the bridge's cursor is server-held —
    no response body on any ``/ui`` route contains a cursor-shaped
    value. Every rendered page and a live stream body are scanned with
    the detector proven above."""
    from ui_gateway_support import build_ui_gateway

    data_dir = tmp_path / "i09"
    data_dir.mkdir()
    app = build_ui_gateway(data_dir, name="stream-i09")
    operations = app.state.ui_operations
    session = live_session(app)
    server, thread, port = boot(app)
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10.0)
    try:
        for _ in range(3):
            operations._emit("run_changed", BENCH_ID, "run-1")
        cookie = {"bw_session": session.session_id}
        pages = (
            "/ui/",
            f"/ui/benches/{BENCH_ID}",
            "/ui/runs/run-1",
            "/ui/requests/req-1",
            "/ui/evidence/ev-1",
            "/ui/documents/" + "0" * 64,
        )
        bodies: list[str] = [
            client.get(path, cookies=cookie).text for path in pages
        ]
        # A stream body that crossed a batch boundary (the cursor
        # advances server-side between polls — the scan covers it).
        with client.stream(
            "GET",
            f"/ui/benches/{BENCH_ID}/events/stream",
            cookies=cookie,
        ) as stream_response:
            assert stream_response.status_code == 200
            raw = stream_response.iter_raw()
            body = _read_until(raw, PROBE_MARKER)
        bodies.append(body)
        for text in bodies:
            for token in re.findall(r"[A-Za-z0-9_\-]{24,}", text):
                assert not _cursor_shaped(token), text[:200]
    finally:
        client.close()
        stop(server, thread)
