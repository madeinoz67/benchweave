"""Task 12: Textual rendering — pilot-rendered views + plain-text fallback.

The brief's RED tests plus the controller-ruling pins:

- **Pilot tests** (``App.run_test()`` headless, asserting on widget CONTENT —
  table row counts and label text, never pixels): the status view shows the
  gateway id and one row per bench; the report view shows the evidence
  digest entries; the demo view is live-updating — it consumes the demo feed
  (an opening banner record carrying the SIMULATION label, then bench events
  as they arrive), appends a row per event, records a failed drive as a
  failure line (never a traceback), and closes itself when the feed ends.
- **Plain lines**: ``PlainTextRenderer`` — the non-TTY renderer — emits the
  same three views as plain text (string content asserted).
- **emit routing** (Task 12 wiring): a render callable that carries a
  ``textual_view`` runs it on the TTY branch instead of printing; a plain
  render callable still prints; the non-TTY plain dump is byte-unchanged.
- **LiveDrive** (the live demo feed's producer, unit of the one-REST-path
  discipline): against a real composed gateway it yields the banner first,
  bench events as they arrive, ends exactly at terminal, and ``result()``
  carries the drive payload; ``events_get`` polling happens HERE, never in
  the view.
- The three T11 review carries: the demo evidence-digest render names where
  the digest is readable; unusable ``--scratch`` paths refuse truthfully;
  mode-crossed options carry a one-line "ignored in this mode" help note.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import uvicorn
from click.testing import CliRunner, Result
from fastapi import FastAPI
from textual.pilot import Pilot
from textual.widgets import DataTable, Static

from benchweave.cli.client import GatewayClient
from benchweave.cli.commands import cli
from benchweave.cli.demo import (
    FEED_BANNER,
    FEED_ERROR,
    SIMULATION_LABEL,
    DemoError,
    LiveDrive,
    live_feed,
    render_demo,
)
from benchweave.cli.output import emit
from benchweave.cli.render import (
    DemoApp,
    PlainTextRenderer,
    Renderer,
    ReportApp,
    StatusApp,
    StatusRender,
    TextualRenderer,
    render_status,
)
from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import issue
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
SECRET = b"wp08-task-twelve-secret"
NOW_ISO = "2026-09-14T00:00:00Z"
NOW_EPOCH = 1_800_000_000
GATEWAY_ID = "gw-task12-render"
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _combined(result: Result) -> str:
    """stdout + stderr, robust to click < 8.2's mixed-stream Result."""
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


def _handled(result: Result) -> None:
    """The failure was handled (exit + message), not a traceback-class exception."""
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"must be a handled error, not a traceback: {result.exception!r}"


# --- shared view fixtures ------------------------------------------------------


def _info() -> dict[str, object]:
    return {
        "gateway_id": GATEWAY_ID,
        "interface_version": "1.1.1",
        "mcp_version": "2026-07-28",
        "limits": {"max_page_size": 1000},
    }


def _benches() -> list[dict[str, object]]:
    return [
        {
            "bench_id": "sim-bench",
            "generation": 1,
            "qualification": "qualified",
            "busy": False,
            "tripped": False,
        },
        {
            "bench_id": "bench-two",
            "generation": 3,
            "qualification": "qualified",
            "busy": True,
            "tripped": True,
        },
    ]


def _report() -> dict[str, object]:
    # The Task 13 canonical model shape (build_report's output): run keys
    # ``id``/``bench``, evidence digest key ``digest`` — the settled keys
    # the view must render, no tolerances.
    return {
        "generated_at": "2026-09-14T00:00:00Z",
        "simulation": True,
        "benches": [
            {"id": "sim-bench", "busy": False, "generation": 2, "simulation": True}
        ],
        "runs": [
            {
                "id": "run-1",
                "bench": "sim-bench",
                "state": "terminal",
                "outcome": "passed",
                "principal": "benchweave-demo",
                "simulation": True,
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev-1",
                "kind": "run_record",
                "digest": DIGEST_A,
                "present": True,
            },
            {
                "evidence_id": "ev-2",
                "kind": "artifact",
                "digest": DIGEST_B,
                "present": False,
            },
        ],
        "missing_evidence": [
            {
                "evidence_id": "ev-2",
                "kind": "artifact",
                "digest": DIGEST_B,
                "present": False,
            }
        ],
    }


def _event(sequence: str, kind: str, run_id: str | None = "run-1") -> dict[str, object]:
    return {
        "stream_id": "bench.sim-bench",
        "sequence": sequence,
        "at": NOW_ISO,
        "kind": kind,
        "run_id": run_id,
        "evidence": None,
    }


def _banner(label: str | None = SIMULATION_LABEL) -> dict[str, object]:
    return {FEED_BANNER: {"label": label, "bench_id": "sim-bench", "run_id": "run-1"}}


async def _until(pilot: Pilot[None], condition: Callable[[], bool], tries: int = 250) -> None:
    """Wait (bounded) for the demo worker to marshal records to the UI."""
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.02)
    raise AssertionError("pilot wait budget exhausted before the condition held")


# --- pilot tests: widget content, never pixels ----------------------------------


@pytest.mark.anyio
async def test_status_app_shows_gateway_id_and_bench_rows() -> None:
    app = StatusApp(_info(), _benches())
    async with app.run_test() as pilot:
        await pilot.pause()
        header = app.query_one("#gateway", Static)
        header_text = str(header.content)
        assert GATEWAY_ID in header_text
        assert "benches:           2" in header_text  # the pinned plain header block
        table = app.query_one("#benches", DataTable)
        assert table.row_count == 2
        first = table.get_row(next(iter(table.rows)))
        assert str(first[0]) == "sim-bench"
        assert str(first[1]) == "1"
        assert str(first[4]) == "False"


@pytest.mark.anyio
async def test_report_app_shows_digest_entries() -> None:
    app = ReportApp(_report())
    async with app.run_test() as pilot:
        await pilot.pause()
        header = app.query_one("#report-header", Static)
        header_text = str(header.content)
        assert "2026-09-14T00:00:00Z" in header_text
        assert SIMULATION_LABEL in header_text  # simulated reports stay labelled
        evidence = app.query_one("#evidence", DataTable)
        assert evidence.row_count == 2
        digests = {str(evidence.get_row(key)[1]) for key in evidence.rows}
        assert digests == {DIGEST_A, DIGEST_B}
        runs = app.query_one("#runs", DataTable)
        assert runs.row_count == 1
        assert str(runs.get_row(next(iter(runs.rows)))[0]) == "run-1"


@pytest.mark.anyio
async def test_demo_app_is_live_updating_with_the_simulation_banner() -> None:
    feed = [
        _banner(),
        _event("1", "run_changed"),
        _event("2", "lease_changed"),
        _event("3", "run_changed", run_id=None),
    ]
    app = DemoApp(feed, auto_exit=False)
    async with app.run_test() as pilot:
        await _until(pilot, lambda: app.feed_done)
        banner = app.query_one("#demo-banner", Static)
        assert SIMULATION_LABEL in str(banner.content)
        table = app.query_one("#demo-events", DataTable)
        assert table.row_count == 3  # one row per event, appended live
        kinds = [str(table.get_row(key)[2]) for key in table.rows]
        assert kinds == ["run_changed", "lease_changed", "run_changed"]
        status = app.query_one("#demo-status", Static)
        assert "terminal" in str(status.content)
        app.exit()


@pytest.mark.anyio
async def test_demo_app_closes_itself_when_the_feed_ends() -> None:
    """The feed ending IS the terminal signal: the production app (default
    ``auto_exit``) closes itself so the command can print its summary."""
    app = DemoApp([_banner(label=None), _event("1", "run_changed")])
    async with app.run_test() as pilot:
        await _until(pilot, lambda: app.feed_done)
        await pilot.pause()
        assert "live gateway" in str(app.query_one("#demo-banner", Static).content)
    assert app.feed_done  # the context exited cleanly after the self-exit


@pytest.mark.anyio
async def test_demo_app_records_a_failed_feed_as_a_failure_line() -> None:
    message = "run run-x did not reach a terminal state within 0.1s (last state: 'running')"
    feed: list[Mapping[str, object]] = [
        _banner(),
        _event("1", "run_changed"),
        {FEED_ERROR: message},
    ]
    app = DemoApp(feed, auto_exit=False)
    async with app.run_test() as pilot:
        await _until(pilot, lambda: app.feed_done)
        assert message in app.failure_text
        status = app.query_one("#demo-status", Static)
        assert "failed" in str(status.content)
        assert app.query_one("#demo-events", DataTable).row_count == 1
        app.exit()


# --- the plain-text renderer (non-TTY) ------------------------------------------


def test_plain_renderer_status_lines_match_the_plain_surface(
    capsys: pytest.CaptureFixture[str],
) -> None:
    PlainTextRenderer().status_view(_info(), _benches())
    expected = render_status({"gateway": _info(), "benches": {"items": _benches()}})
    assert capsys.readouterr().out == expected + "\n"


def test_render_status_lines_are_unchanged() -> None:
    """Byte-parity with the T9/T11 plain formatter (the byte-stability ruling)."""
    text = render_status({"gateway": _info(), "benches": {"items": _benches()}})
    assert text.splitlines() == [
        f"gateway_id:        {GATEWAY_ID}",
        "interface_version: 1.1.1",
        "mcp_version:       2026-07-28",
        "benches:           2",
        "  sim-bench  generation=1 qualification=qualified busy=False tripped=False",
        "  bench-two  generation=3 qualification=qualified busy=True tripped=True",
    ]


def test_plain_renderer_report_lines_show_digests(capsys: pytest.CaptureFixture[str]) -> None:
    PlainTextRenderer().report_view(_report())
    out = capsys.readouterr().out
    assert "generated_at: 2026-09-14T00:00:00Z" in out
    assert SIMULATION_LABEL in out
    assert DIGEST_A in out and DIGEST_B in out
    # Task 13 settlement: missing entries render in the canonical named
    # form (evidence_id + kind + digest), like the markdown emitter.
    assert f"missing evidence: ev-2 kind=artifact digest={DIGEST_B}" in out


def test_plain_renderer_demo_lines_stream_the_feed(capsys: pytest.CaptureFixture[str]) -> None:
    feed: list[Mapping[str, object]] = [
        _banner(),
        _event("1", "run_changed"),
        {FEED_ERROR: "boom"},
    ]
    PlainTextRenderer().demo_view(iter(feed))
    lines = capsys.readouterr().out.splitlines()
    assert SIMULATION_LABEL in lines[0]  # the banner is the first line
    assert any("run_changed" in line for line in lines)
    assert lines[-1] == "failed: boom"


def test_both_renderers_satisfy_the_renderer_protocol() -> None:
    assert isinstance(TextualRenderer(), Renderer)
    assert isinstance(PlainTextRenderer(), Renderer)


# --- emit routing (the Task 12 wiring) -------------------------------------------


class _StubRender:
    """A render callable carrying a textual_view, recording the dispatch."""

    def __init__(self) -> None:
        self.view_calls = 0

    def textual_view(self) -> None:
        self.view_calls += 1

    def __call__(self, data: Mapping[str, object]) -> str:
        return "PLAIN"


def test_emit_tty_branch_runs_the_carried_textual_view(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    stub = _StubRender()
    emit({"gateway": _info()}, render=stub)
    assert stub.view_calls == 1
    assert capsys.readouterr().out == ""  # the view ran; emit printed nothing


def test_emit_tty_branch_still_prints_plain_renderers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    emit({"gateway": _info()}, render=lambda data: "PLAIN")
    assert capsys.readouterr().out == "PLAIN\n"


def test_emit_non_tty_plain_dump_is_byte_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    emit({"gateway": {"gateway_id": "gwx"}, "benches": {"items": []}})
    assert capsys.readouterr().out == "gateway:\n  gateway_id: gwx\nbenches:\n  items:\n"


def test_status_render_carries_the_textual_view(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Mapping[str, object], Sequence[Mapping[str, object]]]] = []
    monkeypatch.setattr(
        TextualRenderer,
        "status_view",
        lambda self, info, benches: seen.append((info, list(benches))),
    )
    info = _info()
    benches = _benches()
    StatusRender(info, benches).textual_view()
    assert seen == [(info, benches)]
    # the plain fallback renders the same block as the shared formatter
    payload = {"gateway": info, "benches": {"items": benches}}
    assert StatusRender(info, benches)(payload) == render_status(payload)


# --- LiveDrive: the live feed producer (one REST path, never the view) ----------


def _boot(app: FastAPI) -> tuple[uvicorn.Server, threading.Thread, int]:
    """The parity-suite loopback boot: real port, lifespan-run."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn did not start"
    servers = server.servers
    assert servers is not None, "uvicorn did not bind within 10s"
    return server, thread, servers[0].sockets[0].getsockname()[1]


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """One live composed gateway (bootstrap admits the sim-bench)."""
    store_dir = tmp_path_factory.mktemp("task12-render")
    store = Store.open(store_dir / "state.db", check_same_thread=False)
    content = ContentStore(store)
    app = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=LIMITS,
        gateway_id=GATEWAY_ID,
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )
    server, thread, port = _boot(app)
    token = issue(
        SECRET,
        principal="task12-render",
        audience="stg",
        scopes={"stg:control"},
        expires_at=NOW_EPOCH + 3600,
    )
    yield SimpleNamespace(base=f"http://127.0.0.1:{port}", token=token)
    server.should_exit = True
    thread.join(timeout=5)
    store.close()


def test_live_drive_feeds_events_until_terminal(gateway: SimpleNamespace) -> None:
    client = GatewayClient(gateway.base, token=gateway.token)
    drive = LiveDrive(client, FIXTURES, timeout_s=30.0)
    drive.start()
    records = list(live_feed(drive, label=SIMULATION_LABEL))
    assert FEED_BANNER in records[0]
    banner = cast(Mapping[str, object], records[0][FEED_BANNER])
    assert banner["label"] == SIMULATION_LABEL
    assert banner["run_id"] == drive.run_id
    events = [record for record in records[1:] if "kind" in record]
    assert events, "the fixture run emits at least one bench event"
    payload = drive.result()
    assert payload["state"] == "terminal"
    assert payload["outcome"] == "passed"
    assert payload["safe_state"] == "verified"
    assert payload["run_id"] == drive.run_id
    assert payload["bench_id"] == "sim-bench"
    assert payload["events_observed"] == len(events)
    assert payload["evidence_digests"], "the terminal record's digest is carried"


def test_live_drive_result_refuses_before_terminal(gateway: SimpleNamespace) -> None:
    client = GatewayClient(gateway.base, token=gateway.token)
    drive = LiveDrive(client, FIXTURES, timeout_s=30.0)
    drive.start()
    with pytest.raises(DemoError, match="consume the feed"):
        drive.result()


def test_run_simulation_threads_the_view_through_the_drive(tmp_path: Path) -> None:
    """The full live wiring, end to end, against the ephemeral simulation
    gateway with a non-TTY view standing in for the TUI: the command feeds
    the view the banner (SIMULATION-labelled) and the events as they arrive,
    then returns the terminal payload."""
    from benchweave.cli.demo import run_simulation

    seen: list[Mapping[str, object]] = []

    def view(events: Iterable[Mapping[str, object]]) -> None:
        seen.extend(events)

    payload = run_simulation(
        scratch=tmp_path / "live-view",
        keep=False,
        fixtures=None,
        timeout_s=60.0,
        view=view,
    )
    assert payload["state"] == "terminal"
    assert payload["label"] == SIMULATION_LABEL
    assert seen, "the view consumed the feed"
    banner = cast(Mapping[str, object], seen[0][FEED_BANNER])
    assert banner["label"] == SIMULATION_LABEL
    assert any("kind" in record for record in seen[1:]), "events arrived at the view"


# --- I1: the operator-close (quit) path of the live demo view --------------------


class _StalledFeed:
    """A demo-feed stand-in that serves the banner then stalls (no more
    records) until ``close()`` — the quit-mid-feed scenario. Self-terminates
    after ``abort_s`` so a regression fails fast instead of hanging the
    suite on an abandoned worker."""

    def __init__(self, *, abort_s: float = 6.0) -> None:
        self.closed = threading.Event()
        self.ended = threading.Event()
        self._abort_at = time.monotonic() + abort_s
        self._banner_done = False

    def close(self) -> None:
        self.closed.set()

    def __iter__(self) -> Iterator[Mapping[str, object]]:
        return self

    def __next__(self) -> Mapping[str, object]:
        if not self._banner_done:
            self._banner_done = True
            return _banner()
        while not self.closed.is_set():
            if time.monotonic() >= self._abort_at:
                break
            # poll-like bounded wait: a close must end this within one cycle
            self.closed.wait(0.2)
        self.ended.set()
        raise StopIteration


@pytest.mark.anyio
async def test_demo_app_quit_mid_feed_closes_the_stalled_feed() -> None:
    """I1: quitting the live view mid-feed must CLOSE the feed so the app's
    worker (and its executor thread) unblocks within ~one poll interval —
    never the drive timeout — and the app exits cleanly."""
    feed = _StalledFeed()
    app = DemoApp(feed)  # production default: auto_exit on feed end
    async with app.run_test() as pilot:
        await pilot.pause(0.1)  # banner marshalled; worker stalled in next()
        await pilot.press("q")  # the operator quits mid-feed
    # Bounded waits (fail fast on regression — never the timeout):
    assert feed.closed.wait(timeout=5.0), "quit must close the stalled feed"
    assert feed.ended.wait(timeout=5.0), (
        "the stalled feed must end within ~one poll interval of the close"
    )


class _StalledGateway:
    """A drive-client stub (the RunReader precedent, full drive surface):
    the run never leaves ``running`` and event pages stay empty — a stalled
    feed with no gateway and no fixture execution."""

    def __init__(self) -> None:
        self.run_get_calls = 0

    def bench_get(self, bench_id: str) -> dict[str, object]:
        return {"bench_id": bench_id, "generation": 1}

    def run_check(
        self, bench_id: str, *, binding_ref: Mapping[str, object]
    ) -> dict[str, object]:
        return {"valid": True, "generation": 1}

    def run_start(
        self,
        bench_id: str,
        *,
        request_id: str,
        binding_ref: Mapping[str, object],
        expected_generation: int,
    ) -> dict[str, object]:
        return {"run_id": "run-stalled-1"}

    def run_find(self, request_id: str) -> dict[str, object]:
        return {"run_id": "run-stalled-1"}

    def run_get(self, run_id: str) -> dict[str, object]:
        self.run_get_calls += 1
        return {
            "run_id": run_id,
            "state": "running",
            "outcome": None,
            "safe_state": None,
            "terminal_record": None,
        }

    def events_get(
        self, bench_id: str, *, after: str = "", limit: int = 100
    ) -> dict[str, object]:
        return {
            "events": [],
            "cursor": after or "cursor-0",
            "stream_id": f"bench.{bench_id}",
            "oldest_sequence": "0",
            "current_sequence": "0",
        }


def test_live_feed_close_ends_the_stalled_feed_within_one_poll_interval() -> None:
    """I1: a consumer blocked mid-poll (the view's worker) must be released
    by ``close()`` within ~one poll interval — bounded, not the 30s timeout —
    and the drive reports an operator close, not a failure."""
    stub = _StalledGateway()
    drive = LiveDrive(stub, FIXTURES, timeout_s=30.0)
    drive.start()
    feed = live_feed(drive, label=SIMULATION_LABEL)
    assert FEED_BANNER in next(iter(feed))
    ended = threading.Event()

    def consume() -> None:  # the view's worker: stalled inside next()
        for _record in feed:
            pass
        ended.set()

    worker = threading.Thread(target=consume, daemon=True)
    worker.start()
    time.sleep(0.6)  # the worker is stalled in next() on the empty pages
    assert not ended.is_set(), "precondition: the feed is genuinely stalled"
    calls_before = stub.run_get_calls
    feed.close()  # the operator closed the live view
    assert ended.wait(timeout=2.0), (
        "close() must end the stalled feed within ~one poll interval "
        "(2s), not the 30s timeout"
    )
    payload = drive.result()
    assert payload["closed_by_operator"] is True
    assert payload["run_id"] == "run-stalled-1"
    assert payload["state"] == "running"  # the last observed state, truthfully
    assert stub.run_get_calls >= calls_before  # it WAS polling, then stopped


def test_drive_with_view_operator_close_is_a_clean_truthful_exit() -> None:
    """I1: a view that returns mid-feed (the operator closed it) produces a
    clean exit-0-shaped payload and a mode-truthful summary line — never a
    DemoError traceback-class refusal."""
    from benchweave.cli.demo import _drive_with_view

    def quitting_view(events: Iterable[Mapping[str, object]]) -> None:
        iterator = iter(events)
        next(iterator)  # the banner; the operator quits here

    payload = _drive_with_view(
        _StalledGateway(), FIXTURES, timeout_s=30.0, view=quitting_view, label=None
    )
    assert payload["closed_by_operator"] is True
    gateway_text = render_demo(
        {**payload, "mode": "gateway", "simulation": False, "label": None,
         "gateway": "http://127.0.0.1:1"}
    )
    assert "closed by operator" in gateway_text
    assert "continues on the gateway" in gateway_text  # gateway-mode truth
    fresh_text = render_demo(
        {**payload, "mode": "simulation", "simulation": True,
         "label": SIMULATION_LABEL, "gateway": "http://127.0.0.1:1",
         "scratch_dir": "/tmp/x"}
    )
    assert "closed by operator" in fresh_text
    assert "torn down" in fresh_text  # fresh-mode truth: the ephemeral run ends


# --- the three T11 review carries ------------------------------------------------


def test_carry_a_demo_digest_names_where_it_is_readable() -> None:
    text = render_demo(
        {
            "mode": "simulation",
            "simulation": True,
            "label": SIMULATION_LABEL,
            "gateway": "http://127.0.0.1:1",
            "bench_id": "sim-bench",
            "procedure_id": "voltage-check",
            "request_id": "req-voltage-check-1",
            "run_id": "run-1",
            "state": "terminal",
            "outcome": "passed",
            "safe_state": "verified",
            "terminal_record": {"id": "doc", "version": "1", "sha256": DIGEST_A},
            "evidence_digests": [DIGEST_A],
            "events_observed": 3,
        }
    )
    digest_lines = [line for line in text.splitlines() if line.startswith("evidence digest:")]
    assert len(digest_lines) == 1
    # GET /v1/documents/<sha> 404s — the line must name where it IS readable.
    assert "benchweave report" in digest_lines[0]


def test_carry_b_scratch_under_a_file_refuses_truthfully(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file", encoding="utf-8")
    result = CliRunner().invoke(cli, ["demo", "--scratch", str(blocker / "x"), "--json"])
    _handled(result)
    assert result.exit_code != 0
    combined = _combined(result)
    assert str(blocker) in combined
    assert "cannot create" in combined


def test_carry_b_scratch_is_a_file_refuses_truthfully(tmp_path: Path) -> None:
    blocker = tmp_path / "scratch-file"
    blocker.write_text("file", encoding="utf-8")
    result = CliRunner().invoke(cli, ["demo", "--scratch", str(blocker), "--json"])
    _handled(result)
    assert result.exit_code != 0
    combined = _combined(result)
    assert str(blocker) in combined
    assert "not a directory" in combined


def test_carry_b_unwritable_scratch_parent_refuses_truthfully(tmp_path: Path) -> None:
    parent = tmp_path / "locked"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        result = CliRunner().invoke(cli, ["demo", "--scratch", str(parent / "x"), "--json"])
        _handled(result)
        assert result.exit_code != 0
        combined = _combined(result)
        assert str(parent) in combined
        assert "cannot create" in combined
    finally:
        parent.chmod(0o700)


def test_carry_b_unwritable_preexisting_scratch_dir_refuses_truthfully(
    tmp_path: Path,
) -> None:
    """M1 (review fold): the one carry-(b) branch with no pin — a pre-existing
    unwritable scratch directory reaches ``Store.open``, whose
    sqlite3.OperationalError must map to a truthful DemoError refusal."""
    scratch = tmp_path / "locked-scratch"
    scratch.mkdir()
    scratch.chmod(0o500)
    try:
        result = CliRunner().invoke(cli, ["demo", "--scratch", str(scratch), "--json"])
        _handled(result)
        assert result.exit_code != 0
        combined = _combined(result)
        assert str(scratch) in combined
        assert "cannot open a store" in combined
    finally:
        scratch.chmod(0o700)


def test_carry_c_mode_crossed_options_note_their_mode_in_help() -> None:
    result = CliRunner().invoke(cli, ["demo", "--help"])
    assert result.exit_code == 0
    # Whitespace-normalized: click wraps help text at the terminal width, so
    # the one-line note is asserted as a phrase, not a literal line.
    help_text = " ".join(result.output.split()).lower()
    assert help_text.count("ignored with --gateway") >= 2  # --scratch / --keep
    assert "ignored in fresh-install mode" in help_text  # --token
