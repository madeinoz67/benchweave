"""The built-in simulator demonstration (Task 11): one drive path, two modes.

Gateway mode (``--gateway URL``) drives the operator's LIVE gateway over the
same REST surface every other client uses — ``run_start`` with the fixture
lattice's valid binding (exactly how the parity/integration suites build
binding refs: the sha256 of ``run-binding.json``, and the binding document's
own ``request_id``, which the coordinator's acceptance key requires), a §9
``run_find`` cross-check, ``run_get`` polling bounded by a configurable
timeout, then the outcome plus the terminal record's evidence digests.

Fresh-install mode (no ``--gateway``) boots an EPHEMERAL gateway in-process
on a SCRATCH directory — never the daemon's data dir — drives the identical
path over loopback REST, labels every rendered surface ``SIMULATION`` (the
bench is the executable simulator fixture, not hardware), and tears down:
app shutdown, then the scratch tree is removed unless ``--keep`` (a scratch
directory that pre-existed is itself never deleted — only the demo's own
store files are).

Anti-coordinate rule (ISC-12): fresh-install mode REFUSES to compose if
:func:`benchweave.cli.atrest.daemon_holds` reports any live coordinator on
any store under the scratch dir — checked BEFORE the app (a second
coordinator over one store) is ever constructed. The ephemeral app is then
the single coordinator of its own scratch store, exactly like a serving
gateway.

The heavy app stack (uvicorn/fastapi/create_app) imports lazily inside the
fresh-install path so ``benchweave --help`` never pays for the demo.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from benchweave.cli.atrest import DB_NAME, daemon_holds
from benchweave.cli.client import GatewayClient, GatewayError

if TYPE_CHECKING:
    import uvicorn
    from fastapi import FastAPI

#: The binding document inside the fixture lattice (the suites' name).
BINDING_FILE = "run-binding.json"
#: The repository execution lattice, resolved like ``app_entry`` does.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURES = _REPO_ROOT / "fixtures" / "execution"
#: The demo's ephemeral gateway identity (visible in status/refusals).
GATEWAY_ID = "gw-cli-demo"
#: The principal the demo's own ephemeral token is issued to.
PRINCIPAL = "benchweave-demo"
#: The same limits block every composed test gateway uses.
DEFAULT_LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}
#: Default seconds to wait for the demonstration run to reach terminal.
DEFAULT_TIMEOUT_S = 120.0
POLL_INTERVAL_S = 0.2
#: The label every fresh-install surface carries (ruling: no exceptions).
SIMULATION_LABEL = "SIMULATION"
#: Feed record keys (the demo_view contract, producer here / consumer in
#: ``benchweave.cli.render``): an opening banner record, and — only on a
#: failed drive — a closing error record carrying the truthful message.
FEED_BANNER = "demo_banner"
FEED_ERROR = "demo_error"
#: A live-view feed consumer: receives the feed; the view never drives
#: the gateway itself (one-REST-path discipline, Task 12 ruling).
View = Callable[[Iterable[Mapping[str, object]]], None]


class DemoError(RuntimeError):
    """A truthful demo failure (the CLI shows it and exits non-zero)."""


class RunReader(Protocol):
    """The one operation the terminal poll needs (unit-testable without a
    gateway: a stub implementing ``run_get`` satisfies it structurally)."""

    def run_get(self, run_id: str) -> dict[str, Any]: ...


class DriveClient(Protocol):
    """The REST surface a live drive needs (``GatewayClient`` satisfies it
    structurally; test stubs implement it the same way — the RunReader
    precedent, widened to the whole drive path)."""

    def bench_get(self, bench_id: str) -> dict[str, Any]: ...

    def run_check(
        self, bench_id: str, *, binding_ref: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    def run_start(
        self,
        bench_id: str,
        *,
        request_id: str,
        binding_ref: Mapping[str, Any],
        expected_generation: int,
    ) -> dict[str, Any]: ...

    def run_find(self, request_id: str) -> dict[str, Any]: ...

    def run_get(self, run_id: str) -> dict[str, Any]: ...

    def events_get(
        self, bench_id: str, *, after: str = "", limit: int = 100
    ) -> dict[str, Any]: ...


# --- fixture binding ------------------------------------------------------------


def resolve_fixtures(explicit: Path | None) -> Path:
    """The fixture lattice to drive: ``explicit``, ``BENCHWEAVE_FIXTURES``,
    or the repository execution lattice."""
    fixtures = explicit or Path(os.environ.get("BENCHWEAVE_FIXTURES", str(DEFAULT_FIXTURES)))
    if not (fixtures / BINDING_FILE).is_file():
        raise DemoError(
            f"fixture lattice not found at {fixtures} — pass --fixtures (or set "
            f"BENCHWEAVE_FIXTURES) pointing at a directory carrying {BINDING_FILE}"
        )
    return fixtures


def fixture_binding(fixtures: Path) -> dict[str, Any]:
    """The valid binding pin + ids from the lattice (the suites' recipe).

    ``request_id`` is the binding document's OWN request id — the
    coordinator's acceptance key is the binding's request id, so any other
    choice is the repeated-binding trap (accepted by the seam, rejected by
    the worker). ``ref.id`` mirrors the parity/rest-route suites' literal
    construction.
    """
    raw = (fixtures / BINDING_FILE).read_bytes()
    document: dict[str, Any] = json.loads(raw)
    version = str(document.get("version") or document.get("contract_version", "1"))
    return {
        "request_id": str(document["request_id"]),
        "bench_id": str(document["bench"]["id"]),
        "procedure_id": str(document["procedure"]["id"]),
        "ref": {
            "id": str(document["request_id"]),
            "version": version,
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
    }


# --- the drive path (identical for both modes) ------------------------------------


def poll_to_terminal(
    reader: RunReader, run_id: str, *, timeout_s: float, poll_s: float = POLL_INTERVAL_S
) -> dict[str, Any]:
    """Poll ``run_get`` until ``state == terminal``; a timeout fails
    truthfully, naming the run and its last observed state."""
    deadline = time.monotonic() + timeout_s
    while True:
        run = reader.run_get(run_id)
        if run.get("state") == "terminal":
            return run
        if time.monotonic() >= deadline:
            raise DemoError(
                f"run {run_id} did not reach a terminal state within "
                f"{timeout_s:g}s (last state: {run.get('state')!r})"
            )
        time.sleep(poll_s)


def _terminal_evidence(run: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """The terminal-record ref and the evidence digests it carries.

    The REST surface serves the run record as a closed ``{id, version,
    sha256}`` ref — the sha256 IS the digest of the evidence-bearing run
    record (outcome, reasons, and the full ``evidence_refs`` lattice live
    inside that document). An uncertain terminal (``outcome_unknown`` /
    ``interrupted``) legitimately carries no record and no digest.
    """
    terminal_ref = run.get("terminal_record")
    if not isinstance(terminal_ref, dict) or not terminal_ref.get("sha256"):
        return None, []
    return dict(terminal_ref), [str(terminal_ref["sha256"])]


def _start_run(client: DriveClient, fixtures: Path) -> dict[str, Any]:
    """The shared start of both drive orchestration paths: resolve the
    binding, advisory-preflight it, start the run, and §9-cross-check that
    the request resolves to the run that was just accepted."""
    binding = fixture_binding(fixtures)
    bench_id = binding["bench_id"]
    bench = client.bench_get(bench_id)
    # Advisory preflight: the gateway must hold the binding and its pinned
    # documents, and it reports the same canonical generation the fence
    # reads — both computed where the truth lives, not on the client.
    preflight = client.run_check(bench_id, binding_ref=binding["ref"])
    if preflight.get("valid") is not True:
        raise DemoError(
            f"run_check preflight failed for bench {bench_id}: "
            f"{preflight.get('findings')!r} — is the gateway bootstrapped "
            "with the fixture lattice?"
        )
    generation = int(preflight.get("generation") or bench["generation"])
    started = client.run_start(
        bench_id,
        request_id=binding["request_id"],
        binding_ref=binding["ref"],
        expected_generation=generation,
    )
    run_id = str(started["run_id"])
    # §9 cross-check: the request must resolve, for this principal, to the
    # run that was just accepted.
    found = client.run_find(binding["request_id"])
    if str(found.get("run_id")) != run_id:
        raise DemoError(
            f"run_find({binding['request_id']!r}) resolved {found.get('run_id')!r}, "
            f"not the started run {run_id!r}"
        )
    return {"binding": binding, "bench_id": bench_id, "run_id": run_id}


def drive_gateway(
    client: DriveClient, fixtures: Path, *, timeout_s: float
) -> dict[str, Any]:
    """Start the fixture run on the gateway's bench and drive it to terminal."""
    started = _start_run(client, fixtures)
    binding = dict(started["binding"])
    bench_id = str(started["bench_id"])
    run_id = str(started["run_id"])
    run = poll_to_terminal(client, run_id, timeout_s=timeout_s)
    terminal_ref, digests = _terminal_evidence(run)
    events = client.events_get(bench_id)
    event_items = events.get("events")
    return {
        "bench_id": bench_id,
        "procedure_id": binding["procedure_id"],
        "request_id": binding["request_id"],
        "run_id": run_id,
        "state": str(run["state"]),
        "outcome": run.get("outcome"),
        "safe_state": run.get("safe_state"),
        "terminal_record": terminal_ref,
        "evidence_digests": digests,
        "events_observed": len(event_items) if isinstance(event_items, list) else 0,
    }


class LiveDrive:
    """One drive, observable live: the identical one-REST-path start as
    :func:`drive_gateway`, then a poll-cycle API the live feed drives —
    ``poll()`` (run_get + cursor-paged ``events_get``),
    ``wait_poll_interval()`` (a stop-aware wait), and ``result()``.

    ``stop()`` ends the drive promptly (the operator closed the live view):
    a poll loop observing it unblocks within ONE poll interval — never the
    drive timeout. The live view (Task 12) consumes :func:`live_feed`; the
    view never drives the gateway — the polling lives here, in the command
    layer.
    """

    def __init__(self, client: DriveClient, fixtures: Path, *, timeout_s: float) -> None:
        self._client = client
        self._fixtures = fixtures
        self._timeout_s = timeout_s
        self._stop = threading.Event()
        self._binding: dict[str, Any] | None = None
        self._bench_id = ""
        self._run_id = ""
        self._after = ""
        self._run: dict[str, Any] | None = None
        self._last_run: dict[str, Any] | None = None
        self._seen: list[dict[str, Any]] = []
        self._failure: DemoError | GatewayError | None = None
        self._deadline = 0.0

    @property
    def bench_id(self) -> str:
        return self._bench_id

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def terminal(self) -> bool:
        return self._run is not None

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def stop(self) -> None:
        """Signal the poll loop to end promptly (the live view was closed)."""
        self._stop.set()

    def wait_poll_interval(self) -> bool:
        """Wait one poll interval; True when ``stop()`` was observed — the
        bounded, stop-aware replacement for ``time.sleep`` in poll loops."""
        return self._stop.wait(POLL_INTERVAL_S)

    def start(self) -> None:
        """binding → preflight → run_start → §9 cross-check (truthful errors)."""
        started = _start_run(self._client, self._fixtures)
        self._binding = dict(started["binding"])
        self._bench_id = str(started["bench_id"])
        self._run_id = str(started["run_id"])

    def poll(self) -> list[dict[str, Any]]:
        """One REST cycle: ``run_get`` + the next ``events_get`` page
        (cursor-paged). Records the observation and the new events; returns
        the NEW events ([] when none). Raises the truthful timeout error
        once the deadline passes without a terminal state."""
        if not self._run_id:
            raise DemoError("LiveDrive.poll() before start()")
        if self._deadline == 0.0:
            self._deadline = time.monotonic() + self._timeout_s
        run = self._client.run_get(self._run_id)
        self._last_run = run
        page = self._client.events_get(self._bench_id, after=self._after)
        new: list[dict[str, Any]] = []
        items = page.get("events")
        if isinstance(items, list):
            for event in items:
                if isinstance(event, dict):
                    new.append(event)
        cursor = page.get("cursor")
        if isinstance(cursor, str) and cursor:
            self._after = cursor
        self._seen.extend(new)
        if run.get("state") == "terminal":
            self._run = run
        elif time.monotonic() >= self._deadline:
            raise DemoError(
                f"run {self._run_id} did not reach a terminal state within "
                f"{self._timeout_s:g}s (last state: {run.get('state')!r})"
            )
        return new

    def fail(self, error: DemoError | GatewayError) -> None:
        """Record a truthful drive failure (surfaced by ``result()``)."""
        self._failure = error

    def result(self) -> dict[str, Any]:
        """The drive summary — the full drive_gateway-shaped payload once the
        feed ran to exhaustion (the run is terminal); an operator-close
        payload when the live view was closed early (a clean close, not a
        failure); a failed drive re-raises here."""
        if self._binding is None:
            raise DemoError("LiveDrive.result() before start()")
        if self._failure is not None:
            raise self._failure
        if self._run is not None:
            terminal_ref, digests = _terminal_evidence(self._run)
            return {
                "bench_id": self._bench_id,
                "procedure_id": self._binding["procedure_id"],
                "request_id": self._binding["request_id"],
                "run_id": self._run_id,
                "state": str(self._run["state"]),
                "outcome": self._run.get("outcome"),
                "safe_state": self._run.get("safe_state"),
                "terminal_record": terminal_ref,
                "evidence_digests": digests,
                "events_observed": len(self._seen),
            }
        if self.stopped:
            last = self._last_run or {}
            return {
                "bench_id": self._bench_id,
                "procedure_id": self._binding["procedure_id"],
                "request_id": self._binding["request_id"],
                "run_id": self._run_id,
                "state": str(last.get("state", "unknown")),
                "outcome": last.get("outcome"),
                "safe_state": last.get("safe_state"),
                "terminal_record": None,
                "evidence_digests": [],
                "events_observed": len(self._seen),
                "closed_by_operator": True,
            }
        raise DemoError(
            "the live drive has not reached a terminal state — "
            "consume the feed to exhaustion first"
        )


class LiveFeed:
    """The demo_view feed: an opening banner record (carrying the
    SIMULATION label in fresh-install mode, ``None`` against a live
    gateway), then bench events as they arrive. The feed ENDS when the run
    is terminal — or, on a failed drive, after one ``demo_error`` record
    carrying the truthful message.

    Unlike a bare generator, the poll loop waits in poll-interval-bounded
    increments and observes ``close()`` (the live view was closed) within
    one poll interval — an operator quit never blocks on the drive timeout
    (a running generator cannot be closed; an iterator can).
    """

    def __init__(self, drive: LiveDrive, *, label: str | None) -> None:
        self._drive = drive
        self._banner: dict[str, Any] = {
            FEED_BANNER: {
                "label": label,
                "bench_id": drive.bench_id,
                "run_id": drive.run_id,
            }
        }
        self._pending: deque[dict[str, Any]] = deque()
        self._served_banner = False
        self._done = False

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return self

    def close(self) -> None:
        """End the feed promptly (the operator closed the live view)."""
        self._drive.stop()

    def __next__(self) -> dict[str, Any]:
        if not self._served_banner:
            self._served_banner = True
            return self._banner
        while not self._pending:
            if self._done or self._drive.stopped:
                raise StopIteration
            try:
                self._pending.extend(self._drive.poll())
            except (DemoError, GatewayError) as error:
                self._drive.fail(error)
                self._done = True
                return {FEED_ERROR: str(error)}
            if self._drive.terminal:
                self._done = True
                if not self._pending:
                    raise StopIteration
                break  # serve this cycle's events, then end
            if self._drive.wait_poll_interval():
                raise StopIteration  # the operator closed the live view
        return self._pending.popleft()


def live_feed(drive: LiveDrive, *, label: str | None) -> LiveFeed:
    """The demo_view feed (see :class:`LiveFeed`): banner record + bench
    events as they arrive; ends at terminal, on a ``demo_error`` record
    (failed drive), or promptly on ``close()`` (operator closed the view)."""
    return LiveFeed(drive, label=label)


def _drive_with_view(
    client: DriveClient,
    fixtures: Path,
    *,
    timeout_s: float,
    view: View | None,
    label: str | None,
) -> dict[str, Any]:
    """Drive to terminal — plainly, or through a live view the command
    feeds events to as they arrive (the view consumes; it never drives).
    The view returning early (the operator closed it) stops the drive
    promptly and yields the operator-close summary — a clean exit, not a
    failure."""
    if view is None:
        return drive_gateway(client, fixtures, timeout_s=timeout_s)
    drive = LiveDrive(client, fixtures, timeout_s=timeout_s)
    drive.start()
    view(live_feed(drive, label=label))
    drive.stop()  # the view returned: release the poll loop promptly
    return drive.result()


# --- mode payloads ----------------------------------------------------------------


def drive_live_gateway(
    base_url: str,
    token: str,
    *,
    fixtures: Path | None,
    timeout_s: float,
    view: View | None = None,
) -> dict[str, Any]:
    """Gateway mode: drive the operator's live gateway; the report is NEVER
    labelled a simulation (the bench may be real hardware). With a ``view``,
    the drive feeds it the live event stream (Task 12)."""
    fixtures_dir = resolve_fixtures(fixtures)
    client = GatewayClient(base_url, token=token)
    payload = _drive_with_view(
        client, fixtures_dir, timeout_s=timeout_s, view=view, label=None
    )
    payload.update(
        {
            "mode": "gateway",
            "simulation": False,
            "label": None,
            "gateway": base_url.rstrip("/"),
        }
    )
    return payload


# --- fresh-install mode -------------------------------------------------------------


def held_stores(root: Path) -> list[Path]:
    """Every store under ``root`` a live coordinator holds (ISC-12).

    Candidates: the at-rest canonical ``state.sqlite`` plus every sqlite/db
    file discovered in the directory — so pointing the scratch at a live
    gateway's data directory refuses however that gateway's store is named.
    """
    root = Path(root)
    candidates: list[Path] = [root / DB_NAME]
    try:
        discovered = sorted({*root.glob("*.sqlite"), *root.glob("*.sqlite3"), *root.glob("*.db")})
    except OSError:
        # An unreadable/non-directory root simply has no discoverable
        # stores; the canonical probe below still runs.
        discovered = []
    for path in discovered:
        if path not in candidates:
            candidates.append(path)
    return [path for path in candidates if daemon_holds(path)]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _now_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


def _boot(app: FastAPI) -> tuple[uvicorn.Server, threading.Thread, int]:
    """The loopback boot the CLI test suites use: real port, lifespan-run."""
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="benchweave-demo")
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    servers = server.servers if getattr(server, "started", False) else None
    if servers is None:
        # The app's lifespan StoreHold is the loudest reason this happens:
        # a store grabbed between the anti-coordinate gate and composition
        # fails loudly here instead of silently double-coordinating.
        server.should_exit = True
        thread.join(timeout=5.0)
        raise DemoError("the ephemeral gateway did not start within 10s")
    port = int(servers[0].sockets[0].getsockname()[1])
    return server, thread, port


def _teardown_scratch(root: Path, *, remove_root: bool, keep: bool) -> None:
    """Remove the demo's footprint: the tree it created, or in a pre-existing
    directory exactly its own store files (never the operator's directory)."""
    if keep:
        return
    if remove_root:
        shutil.rmtree(root, ignore_errors=True)
        # The advisory hold marker is a sibling of the data dir, not inside
        # it (see state/hold.hold_path) — sweep it too.
        with contextlib.suppress(OSError):
            root.parent.joinpath(root.name + ".hold").unlink()
        return
    for suffix in ("", "-wal", "-shm"):
        with contextlib.suppress(OSError):
            (root / (DB_NAME + suffix)).unlink()
    with contextlib.suppress(OSError):
        root.parent.joinpath(root.name + ".hold").unlink()


def run_simulation(
    scratch: Path | None,
    *,
    keep: bool,
    fixtures: Path | None,
    timeout_s: float,
    view: View | None = None,
) -> dict[str, Any]:
    """Fresh-install mode: an ephemeral labelled simulation on a scratch dir.
    With a ``view``, the drive feeds it the live event stream, banner
    labelled SIMULATION (Task 12)."""
    # Lazy heavy imports: only the demo pays for the app stack.
    from benchweave.content.store import ContentStore
    from benchweave.interfaces.app import create_app
    from benchweave.interfaces.identity import issue
    from benchweave.state.store import Store

    fixtures_dir = resolve_fixtures(fixtures)
    # The demo owns (and on teardown removes) exactly the tree IT creates:
    # the mkdtemp default, or a --scratch path that did not exist yet. A
    # pre-existing --scratch directory is never deleted itself — only the
    # demo's own store files inside it are.
    if scratch is not None:
        root = Path(scratch)
        # T11 review carry: unusable --scratch paths are truthful refusals,
        # never sqlite3/OSError tracebacks (the setup/verify precedent).
        if root.exists() and not root.is_dir():
            raise DemoError(
                f"cannot use --scratch {root}: it exists and is not a directory"
            )
        created_root = not root.exists()
        if created_root:
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                # e.g. a parent that is a file, or an unwritable parent.
                raise DemoError(
                    f"cannot create scratch directory {root}: {error}"
                ) from error
    else:
        root = Path(tempfile.mkdtemp(prefix="benchweave-demo-"))
        created_root = True
    # Anti-coordinate gate (ISC-12): refuse BEFORE composing anything —
    # there is no in-process-composition-against-a-held-store path.
    held = held_stores(root)
    if held:
        raise DemoError(
            "refusing: a live gateway holds "
            + ", ".join(str(path) for path in held)
            + f" under {root} — the demo never composes a second coordinator "
            "over a held store; stop that gateway first"
        )

    try:
        store = Store.open(root / DB_NAME, check_same_thread=False)
    except sqlite3.OperationalError as error:
        # e.g. a pre-existing scratch directory the operator cannot write to.
        raise DemoError(
            f"cannot open a store under --scratch {root}: {error}"
        ) from error
    content = ContentStore(store)
    secret = secrets.token_bytes(32)
    app = create_app(
        store=store,
        content=content,
        secret=secret,
        limits=DEFAULT_LIMITS,
        gateway_id=GATEWAY_ID,
        fixtures_dir=fixtures_dir,
        now_iso=_now_iso,
        now_epoch=_now_epoch,
    )
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    port = 0
    try:
        server, thread, port = _boot(app)
        token = issue(
            secret,
            principal=PRINCIPAL,
            audience="stg",
            scopes={"stg:control"},
            expires_at=_now_epoch() + 3600,
        )
        client = GatewayClient(f"http://127.0.0.1:{port}", token=token)
        payload = _drive_with_view(
            client,
            fixtures_dir,
            timeout_s=timeout_s,
            view=view,
            label=SIMULATION_LABEL,
        )
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5.0)
        store.close()
        _teardown_scratch(root, remove_root=created_root, keep=keep)
    payload.update(
        {
            "mode": "simulation",
            "simulation": True,
            "label": SIMULATION_LABEL,
            "gateway": f"http://127.0.0.1:{port}",
            "scratch_dir": str(root),
        }
    )
    if keep:
        payload["kept"] = True
    return payload


# --- rendering -----------------------------------------------------------------------


def render_demo(data: Mapping[str, object]) -> str:
    """Plain-text TTY rendering (the Textual renderer lands in Task 12)."""
    lines: list[str] = []
    simulation = bool(data.get("simulation"))
    if simulation:
        lines.append(
            f"=== {SIMULATION_LABEL} — ephemeral scratch bench, no hardware was driven ==="
        )
    lines.append(f"mode:            {data.get('mode')}")
    lines.append(f"gateway:         {data.get('gateway')}")
    if simulation:
        lines.append(f"scratch:         {data.get('scratch_dir')}")
    lines.append(f"bench:           {data.get('bench_id')}")
    lines.append(f"procedure:       {data.get('procedure_id')}")
    lines.append(f"request:         {data.get('request_id')}")
    lines.append(f"run:             {data.get('run_id')}")
    lines.append(f"state:           {data.get('state')}")
    lines.append(f"outcome:         {data.get('outcome')}")
    lines.append(f"safe_state:      {data.get('safe_state')}")
    if data.get("closed_by_operator"):
        # The operator closed the live view early — a clean exit, with the
        # mode's truth: a live-gateway run keeps running; the ephemeral
        # simulation was torn down with its gateway.
        if str(data.get("mode")) == "gateway":
            lines.append("closed by operator — the run continues on the gateway")
        else:
            lines.append(
                "closed by operator — the ephemeral simulation run was torn down"
            )
    terminal = data.get("terminal_record")
    if isinstance(terminal, Mapping):
        lines.append(f"terminal_record: {terminal.get('sha256')}")
    digests = data.get("evidence_digests")
    printed = 0
    if isinstance(digests, list):
        for digest in digests:
            if isinstance(digest, str):
                printed += 1
                # T11 review carry: GET /v1/documents/<sha> 404s — the line
                # names where the digest IS readable (the run record, via
                # the report command).
                lines.append(
                    f"evidence digest: {digest}  "
                    "(the run record — read it via 'benchweave report')"
                )
    if printed == 0:
        lines.append("evidence digest: (none — uncertain terminal carries no record)")
    lines.append(f"events_observed: {data.get('events_observed')}")
    if data.get("kept"):
        lines.append(f"scratch kept at: {data.get('scratch_dir')}")
    return "\n".join(lines)
