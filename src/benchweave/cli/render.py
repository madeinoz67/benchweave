"""The Task 12 view layer: Textual on a TTY, plain lines everywhere else.

Routing (beside :mod:`benchweave.cli.output`, which stays the single
routing point):

- ``--json``          → untouched: ``output.emit``'s machine contract.
- TTY, no ``--json``  → the command's Textual view (one ``App`` per command
  view, run by ``TextualRenderer``). ``status`` rides ``emit``'s TTY branch
  on the render callable (``StatusRender.textual_view``); ``demo`` runs its
  LIVE view while the drive is in flight (the command feeds it events as
  they arrive) and ``emit``'s TTY branch then prints the plain summary.
- non-TTY             → untouched: ``output.emit``'s generic plain dump —
  the machine-adjacent surface piped scripts consume (byte-stability
  ruling: its strings are not changed by this layer).

One-REST-path discipline (controller ruling): views RECEIVE their data —
snapshots, a report mapping, an event feed — and never drive the gateway.
The demo feed is produced by :func:`benchweave.cli.demo.live_feed` polling
``events_get`` and consumed here.

The demo feed contract (producer ``demo.live_feed``): an opening banner
record ``{"demo_banner": {"label", "bench_id", "run_id"}}`` — ``label`` is
``SIMULATION`` in fresh-install mode, ``None`` against a live gateway —
then bench event mappings as they arrive, and — only on a failed drive — a
closing ``{"demo_error": message}`` record. The feed ENDING is the terminal
signal: ``DemoApp`` closes itself (``auto_exit``). Feeds may expose
``close()`` (``demo.LiveFeed`` does): the app closes the feed when the
operator quits, so the worker consuming it unblocks within one poll
interval — never the drive timeout.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Protocol, cast, runtime_checkable

import click
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from benchweave.cli.demo import FEED_BANNER, FEED_ERROR, SIMULATION_LABEL


@runtime_checkable
class Renderer(Protocol):
    """A command view renderer: one view method per live command."""

    def status_view(
        self, info: dict[str, object], benches: Sequence[Mapping[str, object]]
    ) -> None: ...

    def report_view(self, report: Mapping[str, object]) -> None: ...

    def demo_view(self, events: Iterable[Mapping[str, object]]) -> None: ...


# --- plain formatting (shared by every plain surface) ---------------------------


def _status_header(gateway: Mapping[str, object], count: int) -> list[str]:
    """The status header block (identical on the plain and Textual surfaces)."""
    return [
        f"gateway_id:        {gateway['gateway_id']}",
        f"interface_version: {gateway['interface_version']}",
        f"mcp_version:       {gateway['mcp_version']}",
        f"benches:           {count}",
    ]


def render_status(data: Mapping[str, object]) -> str:
    """Plain-text status rendering (moved from ``commands._render_status``
    unchanged — the TTY plain fallback beside the Textual view)."""
    gateway = cast(Mapping[str, object], data["gateway"])
    benches = cast(Mapping[str, object], data["benches"])
    items = cast(Sequence[Mapping[str, object]], benches["items"])
    lines = _status_header(gateway, len(items))
    for item in items:
        lines.append(
            "  {bench_id}  generation={generation} "
            "qualification={qualification} busy={busy} tripped={tripped}".format_map(
                {k: str(v) for k, v in item.items()}
            )
        )
    return "\n".join(lines)


def _mappings(value: object) -> list[Mapping[str, object]]:
    """A report field's mapping entries ([] when absent or ill-shaped)."""
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _digest_of(entry: Mapping[str, object]) -> str:
    """An evidence entry's digest (Task 13 pins the model key; ``digest``
    and ``sha256`` both accepted so the view tolerates the final choice)."""
    for key in ("digest", "sha256"):
        value = entry.get(key)
        if isinstance(value, str):
            return value
    return ""


def _demo_record_lines(record: Mapping[str, object]) -> list[str]:
    """One plain line(s) per demo feed record (shared by the TUI banner and
    the plain renderer's live feed)."""
    if FEED_BANNER in record:
        raw = record[FEED_BANNER]
        info = raw if isinstance(raw, Mapping) else {}
        if info.get("label"):
            return [
                f"=== {SIMULATION_LABEL} — ephemeral scratch bench, "
                "no hardware was driven ==="
            ]
        return [f"live gateway — bench {info.get('bench_id')} run {info.get('run_id')}"]
    if FEED_ERROR in record:
        return [f"failed: {record[FEED_ERROR]}"]
    return [
        f"event {record.get('sequence', '')} {record.get('kind', '')} "
        f"{record.get('run_id') or ''}"
    ]


# --- Textual Apps (pilot-tested headless; widget content, never pixels) ---------


class StatusApp(App[None]):
    """Gateway identity + the bench inventory (one-shot snapshot view)."""

    def __init__(
        self, info: dict[str, object], benches: Sequence[Mapping[str, object]]
    ) -> None:
        super().__init__()
        self._info = info
        self._benches = list(benches)

    def compose(self) -> ComposeResult:
        yield Static("\n".join(_status_header(self._info, len(self._benches))), id="gateway")
        yield DataTable(id="benches")

    def on_mount(self) -> None:
        table = self.query_one("#benches", DataTable)
        table.add_columns("bench", "generation", "qualification", "busy", "tripped")
        for item in self._benches:
            table.add_row(
                str(item.get("bench_id", "")),
                str(item.get("generation", "")),
                str(item.get("qualification", "")),
                str(item.get("busy", "")),
                str(item.get("tripped", "")),
            )


class ReportApp(App[None]):
    """Run-evidence report view. The report MODEL lands in Task 13; the view
    renders the mapping defensively — header (``generated_at`` + the
    ``SIMULATION`` banner when the report covers simulated benches/runs),
    a runs table, and one row per evidence digest entry."""

    def __init__(self, report: Mapping[str, object]) -> None:
        super().__init__()
        self._report = report

    def compose(self) -> ComposeResult:
        yield Static(self._header(), id="report-header")
        yield DataTable(id="runs")
        yield DataTable(id="evidence")

    def _header(self) -> str:
        lines = [f"generated_at: {self._report.get('generated_at')}"]
        if self._report.get("simulation"):
            lines.append(
                f"{SIMULATION_LABEL} — the report includes simulated benches/runs"
            )
        missing = self._report.get("missing_evidence")
        if isinstance(missing, Sequence) and not isinstance(missing, str | bytes):
            lines.append(f"missing_evidence: {len(missing)}")
        return "\n".join(lines)

    def on_mount(self) -> None:
        runs = self.query_one("#runs", DataTable)
        runs.add_columns("run", "bench", "state", "outcome")
        for run in _mappings(self._report.get("runs")):
            runs.add_row(
                str(run.get("run_id", run.get("id", ""))),
                str(run.get("bench_id", run.get("bench", ""))),
                str(run.get("state", "")),
                str(run.get("outcome", "")),
            )
        evidence = self.query_one("#evidence", DataTable)
        evidence.add_columns("kind", "digest", "present")
        for entry in _mappings(self._report.get("evidence")):
            evidence.add_row(
                str(entry.get("kind", "")), _digest_of(entry), str(entry.get("present", ""))
            )


class DemoApp(App[None]):
    """The live-updating demo view: consumes the demo feed (banner record,
    then bench events as they arrive) on a worker thread, appends one table
    row per event, records a failed drive as a failure line, and — the feed
    ENDING is the terminal signal — closes itself when it ends."""

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(
        self, events: Iterable[Mapping[str, object]], *, auto_exit: bool = True
    ) -> None:
        super().__init__()
        self._events = events
        self._auto_exit = auto_exit
        self.banner_text = ""
        self.failure_text = ""
        self.terminal_text = ""
        self.feed_done = False

    def compose(self) -> ComposeResult:
        yield Static("", id="demo-banner")
        yield DataTable(id="demo-events")
        yield Static("", id="demo-status")

    def on_mount(self) -> None:
        table = self.query_one("#demo-events", DataTable)
        table.add_columns("seq", "at", "kind", "run")
        # The worker THREAD iterates the feed (the command polls the gateway
        # — the view only consumes); records are marshalled to the UI thread.
        self.run_worker(self._consume, thread=True, name="demo-feed")

    def on_unmount(self) -> None:
        # The operator closed the view: CLOSE the feed so the worker (and
        # the app's executor thread, joined at App.run shutdown) unblocks
        # within one poll interval — never the drive timeout. Textual's
        # Worker.cancel() only sets an event a blocked worker never checks,
        # so the feed itself must be closeable. Feeds without close() (plain
        # lists, generators) are unaffected.
        close: Callable[[], None] | None = getattr(self._events, "close", None)
        if close is not None:
            # ValueError only for a RUNNING generator's close() (an embedder
            # passing a bare generator) — the abandoned generator is then
            # closed by GC; LiveFeed.close() cannot raise here.
            with contextlib.suppress(ValueError):
                close()

    def _consume(self) -> None:
        """Iterate the feed on the worker thread until it ends or the app
        was closed under it (an early quit abandons the feed cleanly)."""
        iterator = iter(self._events)
        while self.is_running:
            try:
                record = next(iterator)
            except StopIteration:
                break
            try:
                self.call_from_thread(self._apply, record)
            except RuntimeError:
                return  # the app closed under the feed — stop with it
        if not self.is_running:
            return
        with contextlib.suppress(RuntimeError):
            self.call_from_thread(self._finish)

    def _apply(self, record: Mapping[str, object]) -> None:
        lines = _demo_record_lines(record)
        if FEED_BANNER in record:
            self.banner_text = "\n".join(lines)
            self.query_one("#demo-banner", Static).update(self.banner_text)
        elif FEED_ERROR in record:
            self.failure_text = "\n".join(lines)
            self.query_one("#demo-status", Static).update(self.failure_text)
        elif "kind" in record:
            self.query_one("#demo-events", DataTable).add_row(
                str(record.get("sequence", "")),
                str(record.get("at", "")),
                str(record.get("kind", "")),
                str(record.get("run_id") or ""),
            )

    def _finish(self) -> None:
        self.feed_done = True
        if not self.failure_text:
            self.terminal_text = "run terminal — closing (summary below)"
            self.query_one("#demo-status", Static).update(self.terminal_text)
        if self._auto_exit:
            self.exit()


# --- the renderers ---------------------------------------------------------------


class TextualRenderer:
    """The TTY renderer: builds and runs one Textual App per command view.

    On a real terminal ``App.run`` is interactive (it blocks until the app
    closes); the pilot tests drive the same App classes headless instead.
    """

    def status_view(
        self, info: dict[str, object], benches: Sequence[Mapping[str, object]]
    ) -> None:
        StatusApp(info, benches).run()

    def report_view(self, report: Mapping[str, object]) -> None:
        ReportApp(report).run()

    def demo_view(self, events: Iterable[Mapping[str, object]]) -> None:
        DemoApp(events).run()


class PlainTextRenderer:
    """The non-TTY renderer: the same three views as plain lines through
    ``click.echo``. The CLI's own non-TTY path stays ``output.emit``'s
    pinned plain dump (the byte-stability ruling); this renderer is the
    protocol-complete plain view for embedders and tests that hold a
    ``Renderer`` without a terminal."""

    def status_view(
        self, info: dict[str, object], benches: Sequence[Mapping[str, object]]
    ) -> None:
        click.echo(
            render_status({"gateway": dict(info), "benches": {"items": [dict(b) for b in benches]}})
        )

    def report_view(self, report: Mapping[str, object]) -> None:
        lines = [f"generated_at: {report.get('generated_at')}"]
        if report.get("simulation"):
            lines.append(
                f"{SIMULATION_LABEL} — the report includes simulated benches/runs"
            )
        runs = _mappings(report.get("runs"))
        lines.append(f"runs: {len(runs)}")
        for run in runs:
            lines.append(
                "  {run_id}  bench={bench_id} state={state} "
                "outcome={outcome}".format_map({k: str(v) for k, v in run.items()})
            )
        for entry in _mappings(report.get("evidence")):
            lines.append(
                f"evidence {entry.get('kind')}: {_digest_of(entry)} "
                f"present={entry.get('present')}"
            )
        missing = report.get("missing_evidence")
        if isinstance(missing, Sequence) and not isinstance(missing, str | bytes):
            for item in missing:
                detail = item if isinstance(item, str) else _digest_of(item)
                lines.append(f"missing evidence: {detail}")
        click.echo("\n".join(lines))

    def demo_view(self, events: Iterable[Mapping[str, object]]) -> None:
        for record in events:
            click.echo("\n".join(_demo_record_lines(record)))


class StatusRender:
    """The status render callable for :func:`benchweave.cli.output.emit`:
    carries the command's Textual view for ``emit``'s TTY branch (the Task
    12 wiring); ``__call__`` is the plain-text fallback."""

    def __init__(
        self, info: dict[str, object], benches: Sequence[Mapping[str, object]]
    ) -> None:
        self._info = info
        self._benches = benches

    def textual_view(self) -> None:
        TextualRenderer().status_view(self._info, self._benches)

    def __call__(self, data: Mapping[str, object]) -> str:
        return render_status(data)
