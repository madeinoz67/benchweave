"""WP07 Task 11 event-recovery suite: restart honesty through the HTTP surface.

PRD-05/07/08/09 evidence — every scenario is driven and asserted over the
real composed app (``create_app``: bootstrap, REST/``/v1``, worker, sim
plugins) on a loopback uvicorn port:

- Kill mid-run → restart: the run is recovered ``interrupted``/``unknown``
  through the interface, the bench stream shows the gap visibly (a
  ``run_changed`` for the recovery, nothing invented), and the same-request
  retry returns the SAME run (occurrence/request suppression — no second
  dispatch). Two variants: a child-process variant (real uvicorn, real
  SIGKILL mid-body, real restart; ``@pytest.mark.slow``) and a CI-stable
  in-process variant that stages the exact durable state a mid-body kill
  leaves (accepted request row + run row without a terminal record + queue
  state ``running`` + active lease held by ``run:{id}``) through the real
  Store APIs — the sanctioned ``begin_kill_window`` analog — then boots a
  fresh app whose startup recovery must close it.
- §144 device-disconnect (execution-contract line 144): a transport fault
  mid-run (TRANSPORT_ERROR indeterminate on the measure dispatch) yields a
  terminal ``execution_error``/``outcome_unknown`` — never ``passed``. The
  run's durable events carry the disconnect as the step's ``error_code``
  (``TRANSPORT_ERROR``, status ``unknown``); the full human reason lives in
  the terminal record's reasons — the event carries the machine code, the
  record carries the message.
- §144 evidence-storage-failure: with the retention quota exceeded mid-run
  (``max_page_size=1`` ⇒ app quota 10 < monitor ticks), the bench stream
  carries exactly one ``evidence_gap`` event, the evidence store holds
  exactly the quota-bound rows, and the terminal record survives with its
  evidence refs intact.
- Retention overtake: reading with a cursor the window has passed is 410
  ``event_gap`` — never a silent truncation (§7 events paragraph,
  final-fix-wave correction from the wrong ``cursor_expired`` pin).
- Worker poison guard: a run whose coordinator construction raises must not
  kill the worker thread — the poisoned run lands terminal with honest
  unknown truth (no fabricated record) and a later good run still completes.
- Queued-cancel semantics (Task 5's deferred decision, SUPERSEDED by
  D9/WP08 Task 2): a second ``run_start`` on a bench with a live run is
  now refused synchronously (409 ``conflict`` — "no queue waits
  indefinitely for control"), so the old queued-run premise (cancel a
  run still queued behind a held one = recorded no-op) is unreachable
  through the interface; the pin was replaced by the §5 contention test
  below. The worker's FIFO drain remains as an internal residual
  (observable only in a single run's accept→dispatch window).

One binding document executes exactly once per database (the coordinator's
acceptance is idempotent on the binding document's own ``request_id``; run
ids are never reusable) — the queued-run test therefore stores a second
binding variant (same pin lattice, different ``request_id``) in the content
store before boot.

Pins/deviations inherited or extended from the Task 10 parity ledger:
D4 free-form event evidence (``{"worker_error": ...}`` joins the family);
recovery emits ``run_changed`` evidence
``{"reason": RECOVERY_RUN_CHANGED_REASON}`` (same D4 family).
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import httpx
import pytest
import uvicorn
from jsonschema import Draft202012Validator

from benchweave.content.store import ContentStore
from benchweave.control.executor import canonical_json
from benchweave.host.plugin import DevicePlugin
from benchweave.host.services import HostServices
from benchweave.host.types import (
    ErrorCode,
    OperationRequest,
    OperationResult,
    OperationVerb,
)
from benchweave.interfaces import app as app_module
from benchweave.interfaces.app import create_app
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.identity import issue
from benchweave.interfaces.operations import scoped_request_key
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
CHILD = Path(__file__).resolve().parent / "_event_recovery_child.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

SECRET = b"wp07-task-eleven-secret"
NOW_ISO = "2026-09-13T00:00:00Z"
NOW_EPOCH = 1_800_000_000
PRINCIPAL = "recovery"
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}
SMALL_LIMITS: dict[str, int] = {**LIMITS, "max_page_size": 1}  # quota/keep = 10
BENCH = "sim-bench"
PSU_MEASURE = "otdp.dc_psu.measure/1.0.0"
PSU_CONFIGURE_PREFIX = "otdp.dc_psu.configure"
BINDING_SHA = hashlib.sha256((FIXTURES / "run-binding.json").read_bytes()).hexdigest()
BINDING_REF = {"id": "req-voltage-check-1", "version": "1.0.0", "sha256": BINDING_SHA}
BODY_SHA = hashlib.sha256(
    json.dumps(BINDING_REF, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
POISON_REF = {"id": "req-poisoned", "version": "1.0.0", "sha256": "e" * 64}
DISCONNECT_MESSAGE = "device disconnect: transport link lost during dispatch"

# The second-binding variant: same pin lattice, a distinct document-level
# request_id, so the coordinator's per-binding acceptance dedup permits a
# second execution on the same database.
_variant_binding = json.loads((FIXTURES / "run-binding.json").read_bytes())
_variant_binding["request_id"] = "req-voltage-check-2"
SECOND_BINDING_BYTES = json.dumps(_variant_binding, indent=2).encode()
SECOND_BINDING_SHA = hashlib.sha256(SECOND_BINDING_BYTES).hexdigest()
SECOND_REF = {"id": "req-voltage-check-2", "version": "1.0.0", "sha256": SECOND_BINDING_SHA}

TOKEN = issue(
    SECRET, principal=PRINCIPAL, audience="stg",
    scopes={"stg:admin"}, expires_at=NOW_EPOCH + 3600,
)


def _bearer() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


# --- fault wrappers (WP04 fault-matrix plugin-wrapper pattern) ----------------


class _HoldPsu:
    """Parks the body's first configure dispatch on an event.

    The configure INVOKE is the body's first device operation, so it runs
    strictly after ``_prepare_run`` has reserved the run's bench lease —
    parking there is mid-body with a held lease by construction.
    """

    def __init__(self, inner: DevicePlugin, release: threading.Event) -> None:
        self._inner = inner
        self._release = release
        self._parked_once = False

    @property
    def simulation(self) -> Any:
        return self._inner.simulation

    def plugin_open(self, services: HostServices) -> None:
        self._inner.plugin_open(services)

    def plugin_close(self) -> None:
        self._inner.plugin_close()

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        action = str(request.arguments.get("action_id", ""))
        if (
            not self._parked_once
            and request.verb is OperationVerb.INVOKE
            and action.startswith(PSU_CONFIGURE_PREFIX)
        ):
            self._parked_once = True
            self._release.wait()
        return self._inner.dispatch(request, deadline_ns=deadline_ns)


class _DisconnectPsu:
    """Transport fault mid-run: the measure dispatch dies on the wire.

    One indeterminate TRANSPORT_ERROR — the honest dispatch state after a
    link loss (the command may or may not have reached the device).
    """

    def __init__(self, inner: DevicePlugin) -> None:
        self._inner = inner
        self._faulted = False

    @property
    def simulation(self) -> Any:
        return self._inner.simulation

    def plugin_open(self, services: HostServices) -> None:
        self._inner.plugin_open(services)

    def plugin_close(self) -> None:
        self._inner.plugin_close()

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        action = str(request.arguments.get("action_id", ""))
        if not self._faulted and request.verb is OperationVerb.INVOKE and action == PSU_MEASURE:
            self._faulted = True
            return OperationResult.indeterminate(
                request.operation_id,
                request.verb,
                code=ErrorCode.TRANSPORT_ERROR,
                message=DISCONNECT_MESSAGE,
            )
        return self._inner.dispatch(request, deadline_ns=deadline_ns)


@contextmanager
def _wrapped_psu(
    build_wrapper: Callable[[DevicePlugin], DevicePlugin],
) -> Iterator[None]:
    """Patch the app module's sim-plugin loader to wrap the PSU plugin.

    ``build_run`` re-loads the sim plugins per run on the worker thread and
    resolves ``_load_sim_plugin`` from the module globals at call time, so
    the patch applies to every run started while it is active.
    """
    original = app_module._load_sim_plugin

    def loader(name: str) -> ModuleType:
        module = original(name)
        if name != "sim_psu":
            return module

        class _Shim:
            @staticmethod
            def create_plugin(
                *, now_fn: Callable[[], str], monotonic_ns_fn: Callable[[], int]
            ) -> DevicePlugin:
                inner = module.create_plugin(now_fn=now_fn, monotonic_ns_fn=monotonic_ns_fn)
                return build_wrapper(inner)

        return cast(ModuleType, _Shim())

    app_module._load_sim_plugin = loader
    try:
        yield
    finally:
        app_module._load_sim_plugin = original


# --- gateway launcher (Task 8/10 boot pattern) --------------------------------


def _launch(
    tmp_path: Path,
    *,
    limits: dict[str, int] = LIMITS,
    gateway_id: str = "gw-task11",
    db_name: str = "state.db",
) -> SimpleNamespace:
    """Boot one live app over ``tmp_path / db_name`` (fresh store handle)."""
    store = Store.open(tmp_path / db_name, check_same_thread=False)
    content = ContentStore(store)
    app = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=limits,
        gateway_id=gateway_id,
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )
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
    port = int(servers[0].sockets[0].getsockname()[1])
    base = f"http://127.0.0.1:{port}"
    return SimpleNamespace(
        client=httpx.Client(base_url=base, timeout=30.0),
        base=base,
        port=port,
        store=store,
        content=content,
        server=server,
        thread=thread,
    )


def _shutdown(gateway: SimpleNamespace) -> None:
    gateway.server.should_exit = True
    gateway.thread.join(timeout=10.0)
    gateway.client.close()
    gateway.store.close()


# --- HTTP helpers --------------------------------------------------------------


def _run_get(gateway: SimpleNamespace, run_id: str) -> dict[str, Any]:
    resp = gateway.client.get(f"/v1/runs/{run_id}", headers=_bearer())
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


def _start_run(
    gateway: SimpleNamespace, request_id: str, binding_ref: dict[str, Any]
) -> str:
    resp = gateway.client.post(
        f"/v1/benches/{BENCH}/runs",
        headers=_bearer(),
        json={
            "request_id": request_id,
            "binding_ref": binding_ref,
            "expected_generation": 1,
            "lease_id": None,
        },
    )
    assert resp.status_code == 202, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return str(data["run_id"])


def _poll_run(
    gateway: SimpleNamespace, run_id: str, *, want: str, timeout: float = 45.0
) -> dict[str, Any]:
    """Poll run_get until ``state == want``; bounded, with a loud failure."""
    deadline = time.monotonic() + timeout
    data: dict[str, Any] = {}
    while True:
        data = _run_get(gateway, run_id)
        if data["state"] == want:
            return data
        assert time.monotonic() < deadline, f"run never reached {want}: {data}"
        time.sleep(0.2)


def _bench_events(gateway: SimpleNamespace) -> list[dict[str, Any]]:
    """Walk the whole bench event stream via cursor pages."""
    events: list[dict[str, Any]] = []
    after: str | None = None
    for _ in range(100):
        resp = gateway.client.get(
            f"/v1/benches/{BENCH}/events",
            headers=_bearer(),
            params={"after": after or "", "limit": 1000},
        )
        assert resp.status_code == 200, resp.text
        data: dict[str, Any] = resp.json()["data"]
        page: list[dict[str, Any]] = data["events"]
        if not page:
            return events
        events.extend(page)
        after = str(data["cursor"])
    raise AssertionError("bench event stream did not terminate within 100 pages")


def _stage_crashed_run(store: Store, run_id: str, request_id: str) -> None:
    """Stage exactly the durable state a mid-body kill leaves behind.

    The real Store APIs write what a crashed process had committed: an
    accepted (principal, operation, request) dedup row, a run row without a
    terminal record, queue state ``running``, and an active bench lease
    held by ``run:{run_id}`` (reserved before the body's first dispatch).
    """
    key = scoped_request_key(PRINCIPAL, "run_start", request_id)
    store.accept_request(key, BODY_SHA, run_id, NOW_ISO)
    store.create_run(
        run_id,
        binding={"id": BINDING_REF["id"], "version": BINDING_REF["version"], "sha256": BODY_SHA},
        principal_id=PRINCIPAL,
        now=NOW_ISO,
    )
    store.next_lease(BENCH, f"lease-{run_id}", f"run:{run_id}", f"{NOW_ISO}T+10s")
    store.put_run_state(run_id, BENCH, "running", NOW_ISO)


# --- worker poison guard -------------------------------------------------------


def test_worker_survives_poisoned_build_run(tmp_path: Path) -> None:
    """A coordinator-construction failure must not kill the worker thread.

    The poisoned run (a binding whose pinned document is not stored) lands
    terminal with honest unknown truth — no fabricated terminal record —
    and a ``run_changed`` carries the worker error; a subsequent good run
    still executes to ``passed``.
    """
    gateway = _launch(tmp_path)
    try:
        poisoned = _start_run(gateway, "req-poison", POISON_REF)
        _poll_run(gateway, poisoned, want="terminal")
        honest = _run_get(gateway, poisoned)
        assert honest["outcome"] == "outcome_unknown"
        assert honest["safe_state"] == "unknown"
        assert honest["terminal_record"] is None, "no record may be fabricated"

        good = _start_run(gateway, "req-voltage-check-1", BINDING_REF)
        final = _poll_run(gateway, good, want="terminal", timeout=30.0)
        assert final["outcome"] == "passed", final

        events = _bench_events(gateway)
        poisoned_events = [e for e in events if e.get("run_id") == poisoned]
        assert any(
            e["kind"] == "run_changed" and "worker_error" in str(e.get("evidence", {}))
            for e in poisoned_events
        ), "the poison must be visible on the bench stream"
    finally:
        _shutdown(gateway)


# --- kill mid-run: in-process staged crash (CI-stable) -------------------------


def test_kill_mid_run_staged_crash_recovers_interrupted(tmp_path: Path) -> None:
    """A fresh gateway's startup recovery closes a crashed run honestly.

    Staging the mid-body kill state through the Store, then booting the app
    (whose lifespan runs ``recover_interrupted``): the run reads terminal
    ``interrupted``/``unknown`` through the interface with a real terminal
    record, the lease is released, and the bench stream shows the gap
    visibly — one recovery ``run_changed``, nothing invented.
    """
    store = Store.open(tmp_path / "state.db", check_same_thread=False)
    content = ContentStore(store)
    admit_startup_bench(store, content, FIXTURES, now=NOW_ISO)
    crashed = "run-crashed-mid-body"
    _stage_crashed_run(store, crashed, "req-crashed")

    gateway = _launch(tmp_path)
    try:
        final = _poll_run(gateway, crashed, want="terminal", timeout=10.0)
        assert final["outcome"] == "interrupted", final
        assert final["safe_state"] == "unknown"
        assert final["terminal_record"] is not None, "recovery writes a real record"

        events = _bench_events(gateway)
        assert [e["kind"] for e in events] == ["run_changed"], events
        assert all(e.get("run_id") == crashed for e in events)
        reason = app_module.RECOVERY_RUN_CHANGED_REASON
        assert reason in str(events[0].get("evidence", {})), events[0]
        assert "trip" not in [e["kind"] for e in events], "no invented protective event"
    finally:
        _shutdown(gateway)
    store.close()

    reopened = Store.open(tmp_path / "state.db")
    leases = reopened.list_leases(BENCH)
    assert all(lease.state == "released" for lease in leases), leases
    reopened.close()


def test_same_request_retry_after_recovery_returns_existing_run(tmp_path: Path) -> None:
    """§9 replay after a kill: the SAME run comes back, nothing re-dispatches.

    After recovery finalised the crashed run, replaying the identical
    run_start returns the original run_id in its recovered terminal state,
    run_find resolves the same run, and neither the queue-state revision
    nor the bench event stream moves — the retry neither re-enqueues nor
    re-dispatches (the recovered occurrence identities stay suppressed).
    """
    store = Store.open(tmp_path / "state.db", check_same_thread=False)
    content = ContentStore(store)
    admit_startup_bench(store, content, FIXTURES, now=NOW_ISO)
    crashed = "run-crashed-retry"
    _stage_crashed_run(store, crashed, "req-retry")

    gateway = _launch(tmp_path)
    try:
        recovered = _poll_run(gateway, crashed, want="terminal", timeout=10.0)
        assert recovered["outcome"] == "interrupted"

        events_before = _bench_events(gateway)
        resp = gateway.client.post(
            f"/v1/benches/{BENCH}/runs",
            headers=_bearer(),
            json={
                "request_id": "req-retry",
                "binding_ref": BINDING_REF,
                "expected_generation": 1,
                "lease_id": None,
            },
        )
        assert resp.status_code == 202, resp.text
        replayed: dict[str, Any] = resp.json()["data"]
        assert replayed["run_id"] == crashed
        assert replayed["state"] == "terminal"
        assert replayed["outcome"] == "interrupted"

        found = gateway.client.get("/v1/requests/req-retry", headers=_bearer())
        assert found.status_code == 200, found.text
        assert found.json()["data"]["run_id"] == crashed

        after = _run_get(gateway, crashed)
        assert after["revision"] == recovered["revision"], "replay wrote no state"
        assert _bench_events(gateway) == events_before, "replay emitted no events"
    finally:
        _shutdown(gateway)
    store.close()


# --- kill mid-run: child process (real SIGKILL, slow) --------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _spawn_child(
    tmp_path: Path, db: Path, port: int, *, hold: bool
) -> tuple[subprocess.Popen[bytes], Path]:
    stderr_path = tmp_path / f"child-{port}.stderr.log"
    handle = stderr_path.open("wb")
    proc = subprocess.Popen(
        [sys.executable, str(CHILD), str(db), str(port), *(["--hold"] if hold else [])],
        cwd=str(REPO_ROOT),
        env={
            **os.environ,
            "BENCHWEAVE_DB": str(db),
            "BENCHWEAVE_PORT": str(port),
            "BENCHWEAVE_SECRET": SECRET.decode(),
        },
        stdout=subprocess.DEVNULL,
        stderr=handle,
    )
    return proc, stderr_path


def _wait_child_ready(
    base_url: str, stderr_path: Path, timeout: float = 30.0
) -> httpx.Client:
    client = httpx.Client(base_url=base_url, timeout=10.0)
    deadline = time.monotonic() + timeout
    last_error = "child never became ready"
    while time.monotonic() < deadline:
        try:
            resp = client.get("/v1", headers=_bearer())
            if resp.status_code == 200:
                return client
            last_error = f"gateway_info -> {resp.status_code} {resp.text[:200]}"
        except httpx.HTTPError as error:
            last_error = repr(error)
        time.sleep(0.2)
    tail = stderr_path.read_text(errors="replace")[-2000:] if stderr_path.exists() else ""
    client.close()
    raise AssertionError(f"child gateway not ready: {last_error}\nstderr tail:\n{tail}")


@pytest.mark.slow
def test_kill_mid_run_child_process_recovers_interrupted(tmp_path: Path) -> None:
    """Real process death mid-body, real restart: honesty end to end.

    Child one runs the real app with the body parked mid-run (post-lease);
    the parent SIGKILLs it, boots child two over the same database, and the
    restarted gateway recovers the run ``interrupted``/``unknown`` through
    the HTTP surface with the gap visible and nothing invented.
    """
    db = tmp_path / "state.db"
    port_one = _free_port()
    child_one, stderr_one = _spawn_child(tmp_path, db, port_one, hold=True)
    client_one: httpx.Client | None = None
    try:
        client_one = _wait_child_ready(f"http://127.0.0.1:{port_one}", stderr_one)
        resp = client_one.post(
            f"/v1/benches/{BENCH}/runs",
            headers=_bearer(),
            json={
                "request_id": "req-voltage-check-1",  # §5: the binding doc's own id
                "binding_ref": BINDING_REF,
                "expected_generation": 1,
                "lease_id": None,
            },
        )
        assert resp.status_code == 202, resp.text
        run_id = str(resp.json()["data"]["run_id"])

        deadline = time.monotonic() + 10.0
        data: dict[str, Any] = {}
        while True:
            data = client_one.get(f"/v1/runs/{run_id}", headers=_bearer()).json()["data"]
            if data["state"] == "running":
                break
            assert data["state"] == "accepted", data
            assert time.monotonic() < deadline, f"run never reached running: {data}"
            time.sleep(0.1)
        # The park is mid-body by construction; let the configure dispatch land.
        time.sleep(0.5)

        child_one.kill()  # real process death
        child_one.wait(timeout=10)
        assert child_one.returncode != 0, "the child must have died to a signal"
    finally:
        if client_one is not None:
            client_one.close()

    port_two = _free_port()
    child_two, stderr_two = _spawn_child(tmp_path, db, port_two, hold=False)
    client_two: httpx.Client | None = None
    try:
        client_two = _wait_child_ready(f"http://127.0.0.1:{port_two}", stderr_two)
        deadline = time.monotonic() + 15.0
        while True:
            data = client_two.get(f"/v1/runs/{run_id}", headers=_bearer()).json()["data"]
            if data["state"] == "terminal":
                break
            assert time.monotonic() < deadline, f"run never recovered: {data}"
            time.sleep(0.2)
        assert data["outcome"] == "interrupted", data
        assert data["safe_state"] == "unknown"
        assert data["terminal_record"] is not None

        resp = client_two.get(
            f"/v1/benches/{BENCH}/events",
            headers=_bearer(),
            params={"after": "", "limit": 1000},
        )
        assert resp.status_code == 200, resp.text
        events: list[dict[str, Any]] = resp.json()["data"]["events"]
        kinds = [e["kind"] for e in events]
        assert kinds and set(kinds) == {"run_changed"}, events
        assert all(e.get("run_id") == run_id for e in events), events
        reason = app_module.RECOVERY_RUN_CHANGED_REASON
        assert any(
            reason in str(e.get("evidence", {})) for e in events
        ), "the recovery must be visible on the bench stream"
        assert "trip" not in kinds and "evidence_gap" not in kinds
    finally:
        if client_two is not None:
            client_two.close()
        child_two.terminate()
        child_two.wait(timeout=10)


# --- retention overtake --------------------------------------------------------


def test_retention_overtake_yields_event_gap_over_http(tmp_path: Path) -> None:
    """A cursor the retention window passed is 410 event_gap, not silent.

    ``max_page_size=1`` ⇒ the seam's bench-event window keeps 10. Twelve
    lease emissions later, a cursor captured at sequence 1 is behind the
    window: the read must fail loudly with ``event_gap`` (§7 events
    paragraph — the final-fix-wave correction from the wrong
    ``cursor_expired`` pin).
    """
    gateway = _launch(tmp_path, limits=SMALL_LIMITS)
    try:
        # §6 (WP08 Task 5): one live manual lease per bench, so the twelve
        # emissions are one create plus eleven RENEWALS of the same lease —
        # one lease_changed per call, the same twelve-emission arithmetic
        # twelve fresh creates used to produce.
        created = gateway.client.post(
            f"/v1/benches/{BENCH}/leases",
            headers=_bearer(),
            json={
                "request_id": "req-lease-1",
                "expected_generation": 1,
                "duration_ms": 60000,
            },
        )
        assert created.status_code == 201, created.text
        lease_id = str(created.json()["data"]["lease_id"])
        sequence = int(created.json()["data"]["sequence"])

        first = gateway.client.get(
            f"/v1/benches/{BENCH}/events",
            headers=_bearer(),
            params={"after": "", "limit": 1},
        )
        assert first.status_code == 200, first.text
        page: list[dict[str, Any]] = first.json()["data"]["events"]
        assert len(page) == 1
        stale_cursor = str(first.json()["data"]["cursor"])

        for index in range(2, 13):  # eleven renewals: 12 emissions, window 10
            renewed = gateway.client.post(
                f"/v1/leases/{lease_id}/renewals",
                headers=_bearer(),
                json={
                    "request_id": f"req-lease-{index}",
                    "sequence": sequence,
                    "duration_ms": 60000,
                },
            )
            assert renewed.status_code == 200, renewed.text
            sequence = int(renewed.json()["data"]["sequence"])

        overtaken = gateway.client.get(
            f"/v1/benches/{BENCH}/events",
            headers=_bearer(),
            params={"after": stale_cursor, "limit": 1},
        )
        assert overtaken.status_code == 410, overtaken.text
        error: dict[str, Any] = overtaken.json()["error"]
        assert error["code"] == "event_gap"
    finally:
        _shutdown(gateway)


# --- §144 device disconnect ----------------------------------------------------


def test_device_disconnect_yields_uncertain_truth(tmp_path: Path) -> None:
    """A transport fault mid-run is never dressed up as a pass.

    The measure dispatch dies on the wire (TRANSPORT_ERROR, dispatch state
    unknown): the terminal outcome is execution_error or outcome_unknown —
    never passed. The run's durable events carry the disconnect as the
    failed step's ``error_code`` with status ``unknown``; the terminal
    record's reasons carry the full disconnect message.
    """
    with _wrapped_psu(lambda inner: _DisconnectPsu(inner)):
        gateway = _launch(tmp_path)
        try:
            run_id = _start_run(gateway, "req-voltage-check-1", BINDING_REF)
            final = _poll_run(gateway, run_id, want="terminal", timeout=30.0)
            assert final["outcome"] in ("execution_error", "outcome_unknown"), final
            assert final["outcome"] != "passed"
            assert final["terminal_record"] is not None

            run = gateway.store.get_run(run_id)
            assert run is not None and run["terminal"] is not None
            reasons = [str(reason) for reason in run["terminal"]["reasons"]]
            assert any(DISCONNECT_MESSAGE in reason for reason in reasons), reasons
            events = gateway.store.read_events(f"run:{run_id}")
            failed = [e for e in events if e.get("status") == "unknown"]
            assert len(failed) == 1, f"exactly the faulted step is unknown: {events}"
            assert failed[0].get("error_code") == "TRANSPORT_ERROR", failed[0]

            bench = _bench_events(gateway)
            assert any(e["kind"] == "run_changed" and e.get("run_id") == run_id for e in bench)
        finally:
            _shutdown(gateway)


# --- §144 evidence-storage failure ---------------------------------------------


def test_evidence_storage_failure_emits_evidence_gap(tmp_path: Path) -> None:
    """Retention quota exceeded mid-run: exactly one loud evidence_gap.

    ``max_page_size=1`` gives the app an evidence quota of 10 retentions
    for the run while the monitor ticks more often than that (every
    dispatch twice plus every wait slice). The bench stream must carry
    exactly one ``evidence_gap`` naming the failure count, the evidence
    store must hold exactly the quota-bound rows, and the terminal record
    survives with its evidence refs intact (§152: the gap is loud; the
    record's own refs — pinned documents plus the event-stream digest —
    are not the missing snapshots). The refs are pinned EXACTLY (review
    backfill): every pinned document ref plus the ``events:{run_id}``
    stream digest, recomputed over the surviving stream, so a dropped or
    corrupted ref goes red.
    """
    gateway = _launch(tmp_path, limits=SMALL_LIMITS)
    try:
        run_id = _start_run(gateway, "req-voltage-check-1", BINDING_REF)
        final = _poll_run(gateway, run_id, want="terminal", timeout=30.0)
        assert final["terminal_record"] is not None

        def _doc_ref(path: Path) -> dict[str, str]:
            raw = path.read_bytes()
            doc = json.loads(raw)
            return {
                "id": str(doc["id"]),
                "version": str(doc["version"]),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }

        run = gateway.store.get_run(run_id)
        assert run is not None and run["terminal"] is not None
        record: dict[str, Any] = dict(run["terminal"])
        binding_doc = json.loads((FIXTURES / "run-binding.json").read_bytes())
        expected_refs = [
            {
                "id": str(binding_doc["request_id"]),
                "version": str(binding_doc["contract_version"]),
                "sha256": BINDING_SHA,
            },
            _doc_ref(FIXTURES / "procedure-voltage-check.json"),
            _doc_ref(FIXTURES / "bench.json"),
            _doc_ref(FIXTURES / "safety-policy.json"),
            _doc_ref(FIXTURES / "commissioning.json"),
            {
                "id": f"events:{run_id}",
                "version": "1",
                "sha256": hashlib.sha256(
                    canonical_json(gateway.store.read_events(f"run:{run_id}")).encode()
                ).hexdigest(),
            },
        ]
        assert record["evidence_refs"] == expected_refs, record["evidence_refs"]

        events = _bench_events(gateway)
        gaps = [e for e in events if e["kind"] == "evidence_gap" and e.get("run_id") == run_id]
        assert len(gaps) == 1, f"exactly one evidence_gap, got {gaps}"
        evidence = dict(gaps[0].get("evidence") or {})
        assert int(evidence["retention_failures"]) >= 1, gaps[0]

        quota = SMALL_LIMITS["max_page_size"] * 10
        row = gateway.store.connection.execute(
            "SELECT COUNT(*) FROM evidence WHERE context_key = ?", (f"run:{run_id}",)
        ).fetchone()
        assert row is not None and int(row[0]) == quota, row
    finally:
        _shutdown(gateway)


# --- D12 commissioned takeover (WP08 Task 3) -------------------------------------

_TAKEOVER_EVENT_DEF = json.loads(
    (REPO_ROOT / "standards" / "interface-v1.1.1" / "interface.schema.json").read_bytes()
)["$defs"]["event"]
# The def, VERBATIM — its stream_id pattern admits the seam's
# "bench.{bench_id}" naming (the fix-wave rename). Never patched here.
_TAKEOVER_EVENT_VALIDATOR = Draft202012Validator(_TAKEOVER_EVENT_DEF)


def test_run_start_with_lease_takeover_over_http(tmp_path: Path) -> None:
    """D12 wire pin: ``lease_id`` is honored as a takeover assertion.

    Over the real composed app (real worker, real coordinator): a run
    started against the caller's active manual lease is accepted (202) and
    reaches ``passed`` — proving the manual lease was consumed at accept
    time, before the coordinator's ``reserve`` could see it as
    ``bench_busy`` — the bench stream carries exactly one
    ``authority_changed`` in the vendored event shape (closed
    ``{id, version, sha256}`` evidence ref pinning the binding document),
    a same-request replay returns the SAME run, and a NEW request
    re-presenting the consumed lease fails closed 404 ``not_found``.
    """
    seed = Store.open(tmp_path / "state.db", check_same_thread=False)
    seed_content = ContentStore(seed)
    seed_content.put_document(
        SECOND_BINDING_BYTES,
        SECOND_BINDING_SHA,
        _variant_binding,
        "urn:stg:binding",
        NOW_ISO,
    )
    seed.close()

    gateway = _launch(tmp_path)
    try:
        lease = gateway.client.post(
            f"/v1/benches/{BENCH}/leases",
            headers=_bearer(),
            json={
                "request_id": "req-takeover-lease",
                "expected_generation": 1,
                "duration_ms": 60000,
            },
        )
        assert lease.status_code == 201, lease.text
        lease_id = str(lease.json()["data"]["lease_id"])

        started = gateway.client.post(
            f"/v1/benches/{BENCH}/runs",
            headers=_bearer(),
            json={
                "request_id": "req-voltage-check-1",
                "binding_ref": BINDING_REF,
                "expected_generation": 1,
                "lease_id": lease_id,
            },
        )
        assert started.status_code == 202, started.text
        run_id = str(started.json()["data"]["run_id"])
        final = _poll_run(gateway, run_id, want="terminal", timeout=30.0)
        assert final["outcome"] == "passed", final  # reserve() survived

        events = _bench_events(gateway)
        matches = [e for e in events if e["kind"] == "authority_changed"]
        assert len(matches) == 1, events
        event = matches[0]
        assert event["run_id"] == run_id
        assert event["evidence"] == {
            "id": BINDING_REF["id"],
            "version": BINDING_REF["version"],
            "sha256": BINDING_REF["sha256"],
        }
        assert not list(_TAKEOVER_EVENT_VALIDATOR.iter_errors(event))

        # §9 replay of the same request: the SAME run, never a re-takeover.
        replay = gateway.client.post(
            f"/v1/benches/{BENCH}/runs",
            headers=_bearer(),
            json={
                "request_id": "req-voltage-check-1",
                "binding_ref": BINDING_REF,
                "expected_generation": 1,
                "lease_id": lease_id,
            },
        )
        assert replay.status_code == 202, replay.text
        assert replay.json()["data"]["run_id"] == run_id

        # A NEW request re-presenting the consumed lease fails closed.
        again = gateway.client.post(
            f"/v1/benches/{BENCH}/runs",
            headers=_bearer(),
            json={
                "request_id": "req-voltage-check-2",
                "binding_ref": SECOND_REF,
                "expected_generation": 1,
                "lease_id": lease_id,
            },
        )
        assert again.status_code == 404, again.text
        assert again.json()["error"]["code"] == "not_found"
    finally:
        _shutdown(gateway)


# --- queued-cancel semantics (Task 5 deferred decision, pinned) ----------------


def test_second_run_start_on_live_run_conflicts_and_frees_after_terminal(
    tmp_path: Path,
) -> None:
    """D9 §5 pin (replaces the queued-cancel pin, whose premise D9 voids).

    A bench with a live run refuses a second ``run_start`` synchronously —
    409 ``conflict``, no queue forms ("no queue waits indefinitely for
    control") — and the bench frees once the run closes terminal, where a
    fresh binding starts cleanly. The pre-D9 surface let a second run
    queue behind a held one and recorded a mid-queue cancel as a no-op;
    with accept-time contention that state is unreachable through
    ``run_start`` (the worker's FIFO drain remains an internal residual,
    observable only in a single run's accept→dispatch window).
    """
    seed = Store.open(tmp_path / "state.db", check_same_thread=False)
    seed_content = ContentStore(seed)
    seed_content.put_document(
        SECOND_BINDING_BYTES,
        SECOND_BINDING_SHA,
        _variant_binding,
        "urn:stg:binding",
        NOW_ISO,
    )
    seed.close()

    release = threading.Event()
    with _wrapped_psu(lambda inner: _HoldPsu(inner, release)):
        gateway = _launch(tmp_path)
        try:
            first = _start_run(gateway, "req-voltage-check-1", BINDING_REF)
            _poll_run(gateway, first, want="running", timeout=15.0)

            second = gateway.client.post(
                f"/v1/benches/{BENCH}/runs",
                headers=_bearer(),
                json={
                    "request_id": "req-voltage-check-2",
                    "binding_ref": SECOND_REF,
                    "expected_generation": 1,
                    "lease_id": None,
                },
            )
            assert second.status_code == 409, second.text
            assert second.json()["error"]["code"] == "conflict"

            release.set()  # the parked body proceeds
            first_final = _poll_run(gateway, first, want="terminal", timeout=30.0)
            assert first_final["outcome"] == "passed", first_final

            # The bench freed: the second binding now starts cleanly.
            after = _start_run(gateway, "req-voltage-check-2", SECOND_REF)
            after_final = _poll_run(gateway, after, want="terminal", timeout=30.0)
            assert after_final["outcome"] == "passed", after_final
        finally:
            release.set()  # never leave the body parked
            _shutdown(gateway)
