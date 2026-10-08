"""Issue #422 increment 3 — the lifecycle FAULT arms (L5/L7/L8) and the
worker pickup-gate pins.

The design authority is
`.claude/deep-review/2026-10-08-issue422-inc2-supervision-design.md` §7:
L5 (SIGKILL rung over fault-injected wedged terminalization — Store's
sanctioned ``begin_kill_window`` seam), L7 (the A06 reconciliation
ORDERING over the real composition — the in-process variant §7 sanctions),
L8 (boot recovery with no human: SIGKILL a serving gateway mid-run →
``start``; the F14 determinism rule: the arm observes LIVE state before
its SIGKILL, and a second consecutive flake on the same arm is a KILL).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "fixtures" / "execution"
BENCH_ID = "sim-bench"
POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="signal-path arm: POSIX signals only (record §2.2)"
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return cast(int, sock.getsockname()[1])


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _derived_slow_lattice(tmp_path: Path) -> Path:
    """The runtime-derived slow lattice (the cli suite's Daemon recipe:
    stretch the top-level delay to 4 s — worst-case body stays inside the
    8000 ms bound — and re-pin the binding/commissioning chain)."""
    import hashlib

    derived = tmp_path / "fixtures-slow"
    shutil.copytree(FIXTURES, derived)
    procedure = json.loads(
        (FIXTURES / "procedure-voltage-check.json").read_text()
    )
    procedure["id"] = "slow-voltage-check"

    def stretch(steps: list[dict[str, Any]]) -> None:
        for step in steps:
            if step.get("kind") == "delay" and step.get("duration_ms") == 100:
                step["duration_ms"] = 4000
            for key in ("body", "then", "else"):
                if isinstance(step.get(key), list):
                    stretch(step[key])

    stretch(procedure.get("steps", []))
    procedure_path = derived / "procedure-slow-voltage-check.json"
    procedure_path.write_text(json.dumps(procedure, indent=2) + "\n")
    digest = hashlib.sha256(procedure_path.read_bytes()).hexdigest()
    binding = json.loads((FIXTURES / "run-binding.json").read_text())
    binding["procedure"] = {
        "id": "slow-voltage-check",
        "version": "0.1.0",
        "sha256": digest,
    }
    commissioning = json.loads((FIXTURES / "commissioning.json").read_text())
    commissioning.setdefault("procedure_refs", []).append(
        {"id": "slow-voltage-check", "version": "0.1.0", "sha256": digest}
    )
    (derived / "commissioning.json").write_text(
        json.dumps(commissioning, indent=2) + "\n"
    )
    binding["commissioning"] = {
        "id": binding["commissioning"]["id"],
        "version": binding["commissioning"]["version"],
        "sha256": hashlib.sha256(
            (derived / "commissioning.json").read_bytes()
        ).hexdigest(),
    }
    (derived / "run-binding.json").write_text(json.dumps(binding, indent=2) + "\n")
    return derived


class FaultDaemon:
    """A real slow-lattice `benchweave serve` subprocess (the lean twin of
    the cli suite's Daemon)."""

    def __init__(self, tmp_path: Path, *, principal: str) -> None:

        from benchweave.cli import atrest
        from benchweave.interfaces.identity import issue

        self.data_dir = tmp_path / "gateway"
        atrest.setup(self.data_dir)
        self.secret = atrest.read_secret(self.data_dir)
        self.fixtures = _derived_slow_lattice(tmp_path)
        self.port = _free_port()
        self.token = issue(
            self.secret.encode(),
            principal=principal,
            audience="stg",
            scopes={"stg:control"},
            expires_at=int(time.time()) + 3600,
        )
        self.stderr_path = tmp_path / "daemon.stderr.log"
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("BENCHWEAVE_")
        }
        env.update(
            {
                "BENCHWEAVE_DATA_DIR": str(self.data_dir),
                "BENCHWEAVE_FIXTURES": str(self.fixtures),
            }
        )
        self._handle = self.stderr_path.open("wb")
        self.proc = subprocess.Popen(
            [
                sys.executable, "-m", "benchweave", "serve",
                "--host", "127.0.0.1", "--port", str(self.port),
            ],
            cwd=str(REPO), env=env, stdout=subprocess.DEVNULL, stderr=self._handle,
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{self.port}", timeout=5.0,
                headers={"Authorization": f"Bearer {self.token}"},
            ) as client:
                deadline = time.monotonic() + 30.0
                while True:
                    if self.proc.poll() is not None:
                        raise AssertionError(
                            f"daemon exited rc={self.proc.returncode}:"
                            f"\n{self.stderr_tail()}"
                        )
                    try:
                        if client.get("/v1").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    assert time.monotonic() < deadline, "daemon never became ready"
                    time.sleep(0.2)
        except BaseException:
            self.close()
            raise

    def start_run(self, client: httpx.Client) -> str:
        import hashlib

        bench = client.get(
            "/v1/benches", params={"limit": 100}
        ).json()["data"]["items"][0]
        raw = (self.fixtures / "run-binding.json").read_bytes()
        request_id = json.loads(raw)["request_id"]
        resp = client.post(
            f"/v1/benches/{bench['bench_id']}/runs",
            json={
                "request_id": request_id,
                "binding_ref": {
                    "id": request_id,
                    "version": "0.1.0",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                },
                "expected_generation": bench["generation"],
            },
        )
        assert resp.status_code == 202, resp.text
        return str(resp.json()["data"]["run_id"])

    def wait_state(
        self, client: httpx.Client, run_id: str, *states: str, timeout: float = 30.0
    ) -> str:
        deadline = time.monotonic() + timeout
        state = ""
        while time.monotonic() < deadline:
            state = str(
                client.get(f"/v1/runs/{run_id}").json()["data"]["state"]
            )
            if state in states:
                return state
            time.sleep(0.2)
        raise AssertionError(f"run never reached {states} (last {state})")

    def stderr_tail(self, size: int = 3000) -> str:
        return self.stderr_path.read_text(errors="replace")[-size:]

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self._handle.close()


@pytest.fixture()
def slow_daemon(tmp_path: Path) -> Iterator[FaultDaemon]:
    gate = FaultDaemon(tmp_path, principal=f"fault-{os.getpid()}")
    try:
        yield gate
    finally:
        gate.close()


def _stop_cli(data_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "benchweave", "stop", "--data-dir", str(data_dir), *args],
        cwd=str(REPO), capture_output=True, text=True, timeout=180,
    )


def _journal(data_dir: Path) -> list[dict[str, Any]]:
    from benchweave.supervision import journal_path

    path = journal_path(data_dir / "state.sqlite")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


# --- L5: the SIGKILL rung over wedged terminalization ------------------------------


@POSIX_ONLY
def test_l5_wedged_terminalization_escalates_to_one_sigkill(
    slow_daemon: FaultDaemon,
) -> None:
    """L5: fault-injected wedged terminalization (the test holds the
    store's sanctioned kill-window write lock, so the coordinator's
    ``finalize_run`` cannot land) → after the verdict-stated deadline: ONE
    SIGKILL; the supervision row `sigkill_sent` with reason
    `protective_deadline_exceeded`; the run left NON-terminal in the
    store; `stop` exits non-zero disclosing the kill."""
    from benchweave.state.store import Store

    daemon = slow_daemon
    with httpx.Client(
        base_url=f"http://127.0.0.1:{daemon.port}", timeout=10.0,
        headers={"Authorization": f"Bearer {daemon.token}"},
    ) as client:
        run_id = daemon.start_run(client)
        daemon.wait_state(client, run_id, "running")
    # The wedge: BEGIN IMMEDIATE + writes, uncommitted — every other
    # writer on the store blocks (the kill-child pattern, in-process).
    wedge = Store.open(daemon.data_dir / "state.sqlite")
    wedge.begin_kill_window()
    try:
        result = _stop_cli(daemon.data_dir, "--protective")
        assert result.returncode != 0, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "supervision_sigkill" in combined
        assert "protective_deadline_exceeded" in combined
        assert "STILL ALIVE" not in combined, (
            "one SIGKILL must land within the bounded exit-wait"
        )
    finally:
        wedge.close()  # rolls the window back; the junk rows vanish
    daemon.proc.wait(timeout=15)
    rows = [row for row in _journal(daemon.data_dir) if row["event"] == "sigkill_sent"]
    assert len(rows) == 1, _journal(daemon.data_dir)
    assert rows[0]["reason"] == "protective_deadline_exceeded"
    assert run_id in rows[0]["run_ids"]
    assert rows[0]["run_ids_source"] == "last_verdict"
    # The run stays NON-terminal in the store — the next boot's sweep
    # records it interrupted (the honest outcome; no rung manufactures one).
    store = Store.open(daemon.data_dir / "state.sqlite")
    try:
        run = store.get_run(run_id)
        assert run is not None
        assert run["terminal"] is None, (
            "a wedged-then-SIGKILLed run must stay non-terminal (CTL-9/CTL-11)"
        )
    finally:
        store.close()


# --- L7: the A06 reconciliation ordering over the real composition ------------------


def test_l7_recovery_precedes_serving_and_the_seam_sees_it(tmp_path: Path) -> None:
    """L7 (the in-process variant §7 sanctions): a store carrying a
    non-terminal run boots the REAL composition — the sweep's `interrupted`
    records exist BEFORE the seam accepts any run. Pinned twice: the
    composition's own ordering (recovery completes before the worker
    starts), and the seam-level view (a run_start arriving at readiness
    sees the recovered terminal state)."""
    import hashlib

    import benchweave.interfaces.app as app_module
    from benchweave.content.store import ContentStore
    from benchweave.interfaces.app import create_app
    from benchweave.interfaces.errors import OperationFailure
    from benchweave.interfaces.identity import Identity
    from benchweave.state.store import Store

    store = Store.open(tmp_path / "state.sqlite", check_same_thread=False)
    content = ContentStore(store)
    # Seed the interrupted-run shape: a durable run row, a live
    # projection, and the run lease a crashed coordinator leaves behind.
    # The binding pin is the lattice's REAL binding digest — by recovery
    # time admission has stored it, so the version resolution judges the
    # record (an empty pin is issue #260's containment class: honestly no
    # record, which would defeat the arm).
    binding_raw = (FIXTURES / "run-binding.json").read_bytes()
    store.create_run(
        "run-l7-seeded",
        binding={
            "id": "req-voltage-check-1",
            "version": "0.1.0",
            "sha256": hashlib.sha256(binding_raw).hexdigest(),
        },
        principal_id="l7-seeder",
        now=_now_iso(),
    )
    store.put_run_state("run-l7-seeded", BENCH_ID, "running", _now_iso())
    store.next_lease(
        BENCH_ID, "lease-l7", "run:run-l7-seeded", "2099-01-01T00:00:00Z"
    )

    order: list[str] = []
    original_recover = app_module._recover_interrupted_runs

    def recording_recover(*args: Any, **kwargs: Any) -> list[str]:
        recovered = original_recover(*args, **kwargs)
        order.append("recovery-done")
        return recovered

    app_module._recover_interrupted_runs = recording_recover
    app: Any = None
    try:
        app = create_app(
            store=store,
            content=content,
            secret=b"wp08-task-ten-secret",
            limits={"max_json_bytes": 1048576, "max_page_size": 100,
                    "max_chunk_bytes": 65536, "max_lease_ms": 21600000,
                    "min_poll_ms": 100, "max_admission_ms": 5000},
            gateway_id="gw-l7",
            fixtures_dir=FIXTURES,
            now_iso=_now_iso,
            now_epoch=lambda: 0,
        )
        worker = app.state.operations._worker
        original_start = worker.start

        def recording_start() -> None:
            order.append("worker-start")
            original_start()

        worker.start = recording_start
        server, thread = _boot(app)
        try:
            assert order == ["recovery-done", "worker-start"], order
            # The seam-level half: a run_start arriving AT READINESS sees
            # the recovered terminal state (the wrapper asserts it at the
            # call, before any seam logic runs).
            operations = app.state.operations
            gate = app.state.write_gate
            seen_terminal: list[bool] = []
            original_run_start = operations.run_start

            def checking_run_start(*args: Any, **kwargs: Any) -> Any:
                run = store.get_run("run-l7-seeded")
                seen_terminal.append(
                    run is not None and run["terminal"] is not None
                )
                return original_run_start(*args, **kwargs)

            operations.run_start = checking_run_start
            identity = Identity(
                "l7-principal", "stg", frozenset({"stg:control"}), 2**31
            )
            raw = (FIXTURES / "run-binding.json").read_bytes()
            try:
                with gate:
                    operations.run_start(
                        identity, BENCH_ID, "req-voltage-check-1",
                        {
                            "id": "req-voltage-check-1",
                            "version": "0.1.0",
                            "sha256": hashlib.sha256(raw).hexdigest(),
                        },
                        store.current_generation(BENCH_ID), None,
                    )
            except OperationFailure:
                pass  # any seam refusal is fine — the ordering was observed
            assert seen_terminal == [True], (
                "run_start at readiness must see the recovered terminal record"
            )
        finally:
            server.should_exit = True
            thread.join(timeout=5)
    finally:
        app_module._recover_interrupted_runs = original_recover
        store.close()


def _boot(app: Any) -> tuple[Any, threading.Thread]:
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn did not start"
    return server, thread


# --- L8: boot recovery with no human (F14: observe LIVE before the SIGKILL) --------


@POSIX_ONLY
def test_l8_sigkill_mid_run_then_start_recovers_without_a_human(
    tmp_path: Path,
) -> None:
    """L8: SIGKILL a serving gateway MID-RUN (the arm first observes the
    run LIVE — the F14 determinism rule), then `start`: the new pidfile
    names the NEW pid, the run finalizes `interrupted`/`unknown` at the
    new boot's reconcile, the gateway serves, the old sidecars are
    replaced."""

    from benchweave.interfaces.identity import issue
    from benchweave.supervision import read_pidfile

    daemon = FaultDaemon(tmp_path, principal="l8-victim")
    with httpx.Client(
        base_url=f"http://127.0.0.1:{daemon.port}", timeout=10.0,
        headers={"Authorization": f"Bearer {daemon.token}"},
    ) as client:
        run_id = daemon.start_run(client)
        state = daemon.wait_state(client, run_id, "running")
        assert state == "running", "the arm kills the gateway IN-BODY (F14)"
    old_record = read_pidfile(daemon.data_dir / "state.sqlite")
    assert old_record is not None
    old_pid = int(old_record["pid"])
    daemon.proc.kill()  # no drain, no cleanup: the KILLED class
    daemon.proc.wait(timeout=10)
    daemon._handle.close()
    # The restart-on-crash path a service manager takes — here, a human
    # verb: `start` (§4.2: identical gate by construction).
    port = _free_port()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("BENCHWEAVE_")
    }
    env.update(
        {
            "BENCHWEAVE_DATA_DIR": str(daemon.data_dir),
            "BENCHWEAVE_FIXTURES": str(daemon.fixtures),
        }
    )
    started = subprocess.run(
        [sys.executable, "-m", "benchweave", "start", "--data-dir",
         str(daemon.data_dir), "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO), capture_output=True, text=True, timeout=60, env=env,
    )
    assert started.returncode == 0, started.stdout + started.stderr
    record = read_pidfile(daemon.data_dir / "state.sqlite")
    assert record is not None
    new_pid = int(record["pid"])
    assert new_pid != old_pid, "the new boot must be a NEW process"
    # The new gateway serves; the run finalizes interrupted/unknown at
    # its reconcile-before-serving.
    token = issue(
        daemon.secret.encode(),
        principal="l8-after", audience="stg", scopes={"stg:observe"},
        expires_at=int(time.time()) + 3600,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=10.0,
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            deadline = time.monotonic() + 30.0
            while True:
                try:
                    if client.get("/v1").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "restarted gateway never served"
                time.sleep(0.2)
            outcome = ""
            safe: object = None
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                data = client.get(f"/v1/runs/{run_id}").json()["data"]
                if data["state"] == "terminal":
                    outcome = str(data.get("outcome"))
                    record_json = data.get("terminal_record")
                    if isinstance(record_json, dict):
                        safe = record_json.get("safe_state")
                    break
                time.sleep(0.2)
            else:
                raise AssertionError("the interrupted run never terminalized at boot")
            assert outcome == "interrupted", outcome
            assert safe in ("unknown", None), safe
    finally:
        stopped = _stop_cli(daemon.data_dir)
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr


# --- the worker pickup gate (record §3.3 step 3's mechanism, unit-pinned) ----------


def test_pickup_gate_stops_dequeue_and_lets_the_active_job_finish() -> None:
    """The gate: once set, a QUEUED job is requeued untouched (never
    dispatched) and the thread exits; the active job finishes first; the
    requeue keeps ``unfinished_tasks`` truthful."""

    from benchweave.interfaces.worker import RunWorker

    ran: list[str] = []
    released = threading.Event()
    blocker_started = threading.Event()

    def build_run(run_id: str, principal: str, binding: dict[str, Any],
                  store: Any) -> Any:
        class FakeCoordinator:
            def start_run(self, rid: str, principal_id: str) -> dict[str, Any]:
                if rid == "run-blocker":
                    blocker_started.set()
                    released.wait(timeout=30)
                ran.append(rid)
                return {}

            def cancel(self, rid: str, principal_id: str) -> None:
                pass

        return FakeCoordinator()

    # RunWorker's constructor requires a file-backed store (its PRAGMA
    # probe): a real one on a temp file — the worker thread re-opens the
    # database itself.
    import tempfile

    from benchweave.state.store import Store

    with tempfile.TemporaryDirectory() as tmp:
        real = Store.open(Path(tmp) / "state.sqlite")
        worker = RunWorker(
            real,
            cast(Any, None),
            build_run=build_run,
            limits={"max_page_size": 100},
        )
        worker.submit("run-blocker", "p", {}, "bench")
        worker.submit("run-queued", "p", {}, "bench")
        worker.start()
        # The active job signals IN-BODY before blocking (a timeout-based
        # wait here raced the gate in the first draft: the worker moved on
        # the moment the timeout fired, before the gate landed).
        assert blocker_started.wait(timeout=10), "the active job never started"
        worker.gate_pickup()
        assert worker.pickup_gated is True
        released.set()
        assert worker.wait_gated_exit(timeout=10), "the gated worker must exit"
        assert ran == ["run-blocker"], ran
        # The queued job is still IN the queue (requeued, never taken).
        # G7 folded the arithmetic: the requeue's ``put`` re-increments
        # ``unfinished_tasks`` (the ``get`` that fetched it never
        # decremented it — only ``task_done`` does), so the ghost's count
        # is requeue-inflated until ``join`` settles it at thread exit
        # under the gate — the join-True arm directly below pins that.
        # The pin here is the QUEUE CONTENT.
        assert worker._queue.qsize() == 1
        job = worker._queue.get_nowait()
        assert job[0] == "run-queued"


def test_g7_join_settles_gated_ghost_bookkeeping_and_reports_drained() -> None:
    """G7: after a gated stop with a queued ghost, ``join`` reports the
    truth — no job mid-flight, the thread gone — instead of the false
    did-not-drain (whose CTL-9 shutdown line then cannot fire after a
    protective stop that already finalized its ghosts). The ghost stays
    IN the queue for the stop-time sweep; the queue's unfinished-count
    bookkeeping settles at thread exit under the gate."""

    from benchweave.interfaces.worker import RunWorker

    blocker_started = threading.Event()
    released = threading.Event()

    def build_run(run_id: str, principal: str, binding: dict[str, Any],
                  store: Any) -> Any:
        class FakeCoordinator:
            def start_run(self, rid: str, principal_id: str) -> dict[str, Any]:
                if rid == "run-active":
                    blocker_started.set()
                    released.wait(timeout=30)
                return {}

            def cancel(self, rid: str, principal_id: str) -> None:
                pass

        return FakeCoordinator()

    import tempfile

    from benchweave.state.store import Store

    with tempfile.TemporaryDirectory() as tmp:
        real = Store.open(Path(tmp) / "state.sqlite")
        worker = RunWorker(
            real,
            cast(Any, None),
            build_run=build_run,
            limits={"max_page_size": 100},
        )
        worker.submit("run-active", "p", {}, "bench")
        worker.submit("run-ghost", "p", {}, "bench")
        worker.start()
        assert blocker_started.wait(timeout=10), "the active job never started"
        worker.gate_pickup()
        released.set()
        assert worker.wait_gated_exit(timeout=10), "the gated worker must exit"
        # The RED shape: unfinished_tasks counts the ghost (and the
        # requeue's put double-counts the taken slot) — join reported
        # the false did-not-drain at stop time.
        assert worker.join(timeout=2.0) is True, (
            "join after a gated stop with a queued ghost must report the "
            "drained truth (G7) — the false CTL-9 shutdown line rides "
            "the False return"
        )
        assert worker._queue.qsize() == 1, "the ghost stays for the sweep"
        assert worker._queue.get_nowait()[0] == "run-ghost"
        real.close()


# --- G4: the dequeue-to-mark escape (2026-10-08 refute fold) -----------------------


def _compose_armed_stock(
    tmp_path: Path,
) -> tuple[Any, Any, threading.Thread, Any, Path]:
    """The in-process armed composition over the DERIVED SLOW lattice
    (the cli suite's ``_compose_armed`` shape): the G4 arm needs the
    escape's mark to land inside the shrunken gate wait AND the body to
    still be IN-FLIGHT when the fixpoint loop's cancel arrives — a fast
    body would complete before the cancel's monitor tick and the outcome
    assert would pin timing instead of the mechanism."""
    from fastapi import FastAPI

    from benchweave.content.store import ContentStore
    from benchweave.interfaces.app import create_app
    from benchweave.state.store import Store

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    fixtures = _derived_slow_lattice(tmp_path)
    store = Store.open(data_dir / "state.sqlite", check_same_thread=False)
    content = ContentStore(store)
    app: FastAPI = create_app(
        store=store,
        content=content,
        secret=b"wp08-task-nine-secret",
        limits={"max_json_bytes": 1048576, "max_page_size": 100,
                "max_chunk_bytes": 65536, "max_lease_ms": 21600000,
                "min_poll_ms": 100, "max_admission_ms": 5000},
        gateway_id="gw-g4-arm",
        fixtures_dir=fixtures,
        now_iso=_now_iso,
        now_epoch=lambda: 0,
        supervision_armed=True,
    )
    server, thread = _boot(app)
    return app, server, thread, store, fixtures


def test_g4_dequeue_to_mark_escape_cannot_abandon_a_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G4: a job taken between ``queue.get`` and the running mark escapes
    the stop window's state read — the protective decision currently
    ends mid-body-abandon (``wait_gated_exit`` False → the sweep-note →
    graceful exit over a run it never cancelled). The fold: after
    ``wait_gated_exit``, RE-READ live states, cancel+wait anything now
    running, loop to fixpoint BEFORE the sweep."""
    import asyncio
    import hashlib

    import benchweave.interfaces.supervision as supervision_surface_module
    from benchweave import supervision
    from benchweave.interfaces.errors import OperationFailure
    from benchweave.interfaces.identity import Identity
    from benchweave.state.store import Store

    park_seconds = 1.5
    monkeypatch.setattr(
        supervision_surface_module, "GATE_EXIT_WAIT_S", 0.5
    )
    real_put = Store.put_run_state
    parked = threading.Event()

    def parking_put(self: Any, *args: Any, **kwargs: Any) -> None:
        state = args[2] if len(args) > 2 else kwargs.get("state")
        if state == "running" and not parked.is_set():
            parked.set()
            time.sleep(park_seconds)  # the dequeue-to-mark window, held open
        return real_put(self, *args, **kwargs)

    monkeypatch.setattr(Store, "put_run_state", parking_put)
    app, server, thread, store, fixtures = _compose_armed_stock(tmp_path)
    try:
        surface = app.state.supervision
        operations = app.state.operations
        gate = app.state.write_gate
        identity = Identity(
            "g4-principal", "stg", frozenset({"stg:control"}), 2**31
        )
        raw = (fixtures / "run-binding.json").read_bytes()
        binding = {
            "id": json.loads(raw)["request_id"],
            "version": "0.1.0",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        with gate:
            try:
                operations.run_start(
                    identity, BENCH_ID, "req-voltage-check-1", binding,
                    store.current_generation(BENCH_ID), None,
                )
            except OperationFailure as failure:
                pytest.fail(f"the run_start refused pre-park: {failure}")
        assert parked.wait(timeout=10.0), (
            "the worker never took the job (the park never armed)"
        )
        # The protective stop lands INSIDE the parked window: the window
        # read sees the run as `accepted` (a ghost), the gate lands after
        # the dequeue.
        supervision.stop_path(surface.db_path).write_text(
            json.dumps(
                {
                    "schema": 1,
                    "mode": "protective",
                    "requested_wall": _now_iso(),
                    "actor_pid": os.getpid(),
                    "target_pid": os.getpid(),
                }
            ),
            encoding="utf-8",
        )
        future = asyncio.run_coroutine_threadsafe(
            surface._run_decision(
                supervision.read_stop_file(surface.db_path), trigger="file"
            ),
            surface._loop,
        )
        future.result(timeout=30.0)
        # THE ASSERT: the decision is over — the escaped run must already
        # be terminal, cancelled by the fixpoint loop (never abandoned
        # mid-body, never fabricated `interrupted` by the sweep).
        deadline = time.monotonic() + 10.0
        run = None
        while time.monotonic() < deadline:
            run = _only_run(store)
            if run is not None and run["terminal"] is not None:
                break
            time.sleep(0.2)
        assert run is not None, "the escaped run's row exists"
        assert run["terminal"] is not None, (
            "the decision completed over a NON-terminal run — the "
            "mid-body abandon (G4)"
        )
        assert run["terminal"]["body_outcome"] == "cancelled", run["terminal"]
        assert str(run["terminal"]["body_outcome"]) != "interrupted", (
            "a dispatched run is the coordinator's to terminalize — the "
            "sweep must never own it (CTL-9)"
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        store.close()


def _only_run(store: Any) -> Any:
    for bench in store.list_benches(limit=1000, offset=0)[0]:
        for row in store.list_run_states(str(bench["bench_id"])):
            run = store.get_run(str(row["run_id"]))
            if run is not None:
                return run
    return None
