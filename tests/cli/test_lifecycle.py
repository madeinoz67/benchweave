"""Issue #422 increment 3 — the lifecycle verbs (stop/start/restart/status,
service install) and the supervision protocol core.

The arms follow the pre-committed acceptance rule in
`.claude/deep-review/2026-10-08-issue422-inc2-supervision-design.md` §7
(the stop-gate authority): L1-L13 + L3b, plus the protocol-core unit arms
that pin the pidfile identity lattice (§2.4) and the doorbell file shapes
(§3.2/§3.3). The real-subprocess arms use the live-serve pattern from
``tests/cli/test_serve.py``; the fault arms (L5/L7/L8) live in
``tests/faults/test_lifecycle_faults.py``.

Signal-path arms are POSIX-scoped by design (record §2.2: POSIX signals
are a latency optimization over the file doorbell; the Windows CI leg
corroborates the file path — W1).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from click.testing import CliRunner, Result

from benchweave.cli.commands import cli

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "fixtures" / "execution"
TEMPLATE = REPO / "deploy" / "systemd" / "benchweave.service.template"
BINDING_REQUEST_ID = "req-voltage-check-1"
BENCH_ID = "sim-bench"
# R9's wall-time bound for the idle plain stop: the join window (5 s) plus
# the connection-close bound (the daemon's own graceful timeout) plus
# schedule slack. A regression to an UNBOUNDED drain (an open SSE stream
# hanging shutdown, an unbounded join) blows through this, not a healthy
# run under CI load.
L1_WALL_BOUND_S = 25.0
POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="signal-path arm: POSIX signals only (record §2.2)"
)


# --- protocol core: the identity lattice (record §2.4) --------------------------


def _write_pidfile(data_dir: Path, payload: dict[str, Any]) -> Path:
    """Hand-write a pidfile sidecar the way a stale/corrupt one looks."""
    from benchweave.supervision import pid_path

    path = pid_path(data_dir / "state.sqlite")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _hold_with_body(db: Path, body: dict[str, Any]) -> Any:
    """Acquire the real hold, then rewrite the advisory BODY the way a
    hand-written sidecar reads (the lock is real; the body is ours to
    stage — the L9 fixture shape)."""
    from benchweave.state.hold import StoreHold, hold_path

    hold = StoreHold(db, label=str(body.get("label", "gateway gw-x")))
    hold.acquire()
    hold_path(db).write_text(json.dumps(body), encoding="utf-8")
    return hold


@contextmanager
def _live_child() -> Iterator[int]:
    """A REAL unrelated live process (its pid + our own ticks read of it)."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait(timeout=10)


@pytest.fixture()
def live_child() -> Iterator[int]:
    with _live_child() as pid:
        yield pid


def test_l6a_dead_pidfile_clears_sidecars(tmp_path: Path) -> None:
    """L6(a): the pidfile names a pid that is DEAD (an exited child) —
    stop reports `not running`, clears the stale sidecars, journals."""
    from benchweave.supervision import journal_path, pid_path, stop_path

    dead = subprocess.Popen(
        [sys.executable, "-c", "pass"], stdout=subprocess.DEVNULL
    )
    dead.wait(timeout=10)
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    _write_pidfile(
        data_dir,
        {
            "pid": dead.pid,
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-08T00:00:00Z",
            "started_ticks": 1,
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    stop_path(data_dir / "state.sqlite").write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(cli, ["stop", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, _combined(result)
    assert "not running" in _combined(result)
    assert not pid_path(data_dir / "state.sqlite").exists(), "stale pidfile cleared"
    assert not stop_path(data_dir / "state.sqlite").exists(), "stale stop file cleared"
    rows = [
        json.loads(line)
        for line in journal_path(data_dir / "state.sqlite").read_text().splitlines()
    ]
    assert "stale_sidecars_cleared" in {row["event"] for row in rows}


def test_l6b_identity_mismatch_is_not_ours_nothing_signaled(
    tmp_path: Path, live_child: int
) -> None:
    """L6(b): a LIVE pid whose recorded start time DIFFERS (a mismatched
    ticks value — writing the child's own start time would match and signal;
    lane-1 F9 fold) reads NOT-OURS, nothing is signaled, typed refusal."""
    from benchweave.supervision import process_start_ticks

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    real_ticks = process_start_ticks(live_child)
    assert real_ticks is not None, "the test platform must read start ticks"
    _write_pidfile(
        data_dir,
        {
            "pid": live_child,
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-08T00:00:00Z",
            "started_ticks": int(real_ticks) - 12345,  # MISMATCHED, F9 fold
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    import benchweave.supervision as supervision

    signaled: list[tuple[int, int]] = []
    original = supervision._signal_pid

    def spy_kill(pid: int, sig: int) -> None:
        signaled.append((pid, sig))

    supervision._signal_pid = spy_kill
    try:
        result = CliRunner().invoke(cli, ["stop", "--data-dir", str(data_dir)])
    finally:
        supervision._signal_pid = original
    assert result.exit_code != 0
    assert "supervision_stale_pid:" in _combined(result)
    assert not signaled, "a NOT-OURS pidfile must never be signaled"


def test_l6c_ticks_unobtainable_and_hold_free_is_unknown_refusal(
    tmp_path: Path, live_child: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L6(c): pid alive, started_ticks unobtainable on the platform, hold
    free → UNKNOWN verdict, nothing signaled, typed `supervision_pid_unknown:`."""
    import benchweave.supervision as supervision

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    _write_pidfile(
        data_dir,
        {
            "pid": live_child,
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-08T00:00:00Z",
            "started_ticks": 1,
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    monkeypatch.setattr(supervision, "process_start_ticks", lambda pid: None)
    signaled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        supervision, "_signal_pid", lambda pid, sig: signaled.append((pid, sig))
    )
    result = CliRunner().invoke(cli, ["stop", "--data-dir", str(data_dir)])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "supervision_pid_unknown:" in combined
    assert str(supervision.pid_path(data_dir / "state.sqlite")) in combined, (
        "the refusal names the file to verify"
    )
    assert not signaled


def test_l6c_ticks_unobtainable_hold_vouches_signals(
    tmp_path: Path, live_child: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lattice's vouching cell: ticks unobtainable, but the store hold
    is HELD by a gateway label whose pid EQUALS the pidfile pid — the hold
    is the truth, the verdict is OURS and the signal proceeds."""
    import benchweave.supervision as supervision

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    db = data_dir / "state.sqlite"
    _write_pidfile(
        data_dir,
        {
            "pid": live_child,
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-08T00:00:00Z",
            "started_ticks": 1,
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    monkeypatch.setattr(supervision, "process_start_ticks", lambda pid: None)
    hold = _hold_with_body(
        db,
        {"pid": live_child, "label": "gateway gw-x",
         "acquired_at": "2026-10-08T00:00:00Z"},
    )
    try:
        verdict = supervision.verify_gateway_identity(db)
    finally:
        hold.release()
    assert verdict.verdict == "ours", verdict.detail
    assert "vouches" in verdict.detail, (
        "the vouching cell is the one that permits signaling"
    )


def test_l9_hold_desync_names_both_pids_nothing_signaled(
    tmp_path: Path, live_child: int
) -> None:
    """L9: the hold is held by a gateway label whose pid DISAGREES with the
    pidfile (a hand-written sidecar) — typed `supervision_hold_desync:`
    naming BOTH numbers; nothing is signaled."""
    import benchweave.supervision as supervision

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    db = data_dir / "state.sqlite"
    _write_pidfile(
        data_dir,
        {
            "pid": live_child,
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-08T00:00:00Z",
            "started_ticks": supervision.process_start_ticks(live_child),
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    other_pid = live_child + 40000
    hold = _hold_with_body(
        db,
        {"pid": other_pid, "label": "gateway gw-x",
         "acquired_at": "2026-10-08T00:00:00Z"},
    )
    try:
        verdict = supervision.verify_gateway_identity(db)
    finally:
        hold.release()
    assert verdict.verdict == "desync"
    assert str(live_child) in verdict.detail and str(other_pid) in verdict.detail
    assert "supervision_hold_desync:" in verdict.detail


def test_hold_label_cross_check_no_desync_on_atrest_holders(
    tmp_path: Path, live_child: int
) -> None:
    """F6 fold: a NON-gateway holder label (`service-install`, `backup pid
    …`) holds a store no daemon owns — the pidfile stands on probe+identity
    alone and NO desync fires even though the pids differ."""
    import benchweave.supervision as supervision

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    db = data_dir / "state.sqlite"
    _write_pidfile(
        data_dir,
        {
            "pid": live_child,
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-08T00:00:00Z",
            "started_ticks": supervision.process_start_ticks(live_child),
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    hold = _hold_with_body(
        db,
        {"pid": 1, "label": "backup pid 1",
         "acquired_at": "2026-10-08T00:00:00Z"},
    )
    try:
        verdict = supervision.verify_gateway_identity(db)
    finally:
        hold.release()
    assert verdict.verdict == "ours", verdict.detail


# --- protocol core: the doorbell file shapes (record §3.2/§3.3) ------------------


def test_stop_request_shape_and_verdict_parse(tmp_path: Path) -> None:
    from benchweave.supervision import (
        read_stop_file,
        stop_path,
        write_stop_request,
    )

    db = tmp_path / "state.sqlite"
    request = write_stop_request(db, mode="protective", actor_pid=4242)
    assert request["schema"] == 1
    assert request["mode"] == "protective"
    assert request["actor_pid"] == 4242
    assert "requested_wall" in request
    assert "status" not in request, "a request carries no verdict status"
    assert read_stop_file(db) == request
    # A foreign shape (unparseable) reads as None — never a crash.
    stop_path(db).write_text("{not json", encoding="utf-8")
    assert read_stop_file(db) is None


def test_journal_rows_are_typed_and_append_only(tmp_path: Path) -> None:
    from benchweave.supervision import journal_append, journal_path

    db = tmp_path / "state.sqlite"
    journal_append(
        db, "stop_requested", mode="plain", target_pid=99, signal_name="SIGTERM"
    )
    journal_append(db, "stopped")
    rows = [
        json.loads(line)
        for line in journal_path(db).read_text().splitlines()
    ]
    assert [row["event"] for row in rows] == ["stop_requested", "stopped"]
    assert all("wall" in row for row in rows)
    assert rows[0]["target_pid"] == 99
    assert rows[0]["signal_name"] == "SIGTERM"


def test_pidfile_roundtrip_and_removal(tmp_path: Path) -> None:
    from benchweave.supervision import (
        pid_path,
        process_start_ticks,
        read_pidfile,
        remove_pidfile,
        write_pidfile,
    )

    db = tmp_path / "state.sqlite"
    written = write_pidfile(db, gateway_id="gw-test", log_destination="stderr")
    assert written["pid"] == os.getpid()
    assert written["schema"] == 1
    assert written["started_ticks"] == process_start_ticks(os.getpid())
    assert read_pidfile(db) == written
    assert pid_path(db).stat().st_mode & 0o777 == 0o600
    remove_pidfile(db)
    assert read_pidfile(db) is None


def test_sibling_family_derives_from_the_resolved_data_dir(tmp_path: Path) -> None:
    """§2.3: one derivation, four siblings — every supervision file derives
    exactly the way `hold_path` derives `<dir>.hold` (STO-3's rider)."""
    from benchweave.state.hold import hold_path, sibling_path

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    db = data_dir / "state.sqlite"
    assert sibling_path(db, ".hold") == hold_path(db)
    assert sibling_path(db, ".pid").name == "gateway.pid"
    assert sibling_path(db, ".stop").parent == hold_path(db).parent
    # The resolved-spelling rule: an alias derives the same sibling.
    alias = tmp_path / "alias"
    alias.symlink_to(data_dir, target_is_directory=True)
    assert sibling_path(alias / "state.sqlite", ".pid") == sibling_path(db, ".pid")


# --- the live daemon scaffold (test_serve.py's live-leg pattern) -----------------


class Daemon:
    """A real `benchweave serve` subprocess over a setup-created data dir.

    ``slow`` builds a derived lattice whose top-level procedure delay is
    stretched to 4 s (the F14 determinism rule: a stop decision landing
    seconds after acceptance observes the run IN-BODY, not a run that
    already finished — the stock sim body completes in well under a
    second; the stretch keeps the worst-case body inside the procedure's
    8000 ms bound). The derived lattice is generated at runtime from the
    stock files, so the committed execution lattice carries zero test-only
    bytes."""

    def __init__(self, tmp_path: Path, *, principal: str, slow: bool = False) -> None:
        import hashlib
        import shutil

        from benchweave.cli import atrest
        from benchweave.interfaces.identity import issue

        self.data_dir = tmp_path / "gateway"
        atrest.setup(self.data_dir)
        self.secret = atrest.read_secret(self.data_dir)
        self.port = _free_port()
        self.principal = principal
        self.token = issue(
            self.secret.encode(),
            principal=principal,
            audience="stg",
            scopes={"stg:control"},
            expires_at=int(time.time()) + 3600,
        )
        self.fixtures = FIXTURES
        if slow:
            derived = tmp_path / "fixtures-slow"
            shutil.copytree(FIXTURES, derived)
            procedure = json.loads(
                (FIXTURES / "procedure-voltage-check.json").read_text()
            )
            procedure["id"] = "slow-voltage-check"
            procedure["description"] = (
                "Runtime-derived slow twin of the voltage check (the "
                "supervision arms' in-body window); never a committed file."
            )

            def stretch(steps: list[dict[str, Any]]) -> None:
                for step in steps:
                    if (
                        step.get("kind") == "delay"
                        and step.get("duration_ms") == 100
                    ):
                        # 4000 ms: the worst-case body (this delay + the
                        # nested repeat's own delays, 3400 ms) stays under
                        # the procedure's 8000 ms bound with the 100 ms
                        # scheduling overhead — a ~4 s in-body window.
                        step["duration_ms"] = 4000
                    for key in ("body", "then", "else"):
                        if isinstance(step.get(key), list):
                            stretch(step[key])

            stretch(procedure.get("steps", []))
            procedure_path = derived / "procedure-slow-voltage-check.json"
            procedure_path.write_text(json.dumps(procedure, indent=2) + "\n")
            procedure_digest = hashlib.sha256(
                procedure_path.read_bytes()
            ).hexdigest()
            binding = json.loads((FIXTURES / "run-binding.json").read_text())
            binding["procedure"] = {
                "id": "slow-voltage-check",
                "version": "0.1.0",
                "sha256": procedure_digest,
            }
            (derived / "run-binding.json").write_text(
                json.dumps(binding, indent=2) + "\n"
            )
            # The commissioning document enumerates the commissioned
            # procedures (admission's procedure_refs pin): the slow twin
            # joins the set — an ADDITIVE row, the original untouched.
            commissioning = json.loads(
                (FIXTURES / "commissioning.json").read_text()
            )
            commissioning.setdefault("procedure_refs", []).append(
                {
                    "id": "slow-voltage-check",
                    "version": "0.1.0",
                    "sha256": procedure_digest,
                }
            )
            (derived / "commissioning.json").write_text(
                json.dumps(commissioning, indent=2) + "\n"
            )
            # The binding pins the commissioning digest; the patched
            # commissioning gets its new pin in the derived binding.
            binding["commissioning"] = {
                "id": binding["commissioning"]["id"],
                "version": binding["commissioning"]["version"],
                "sha256": hashlib.sha256(
                    (derived / "commissioning.json").read_bytes()
                ).hexdigest(),
            }
            (derived / "run-binding.json").write_text(
                json.dumps(binding, indent=2) + "\n"
            )
            self.fixtures = derived
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
                sys.executable,
                "-m",
                "benchweave",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=str(REPO),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=self._handle,
        )
        self._wait_ready()

    def _wait_ready(self) -> None:
        last_error = "daemon never became ready"
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{self.port}", timeout=5.0
            ) as client:
                deadline = time.monotonic() + 30.0
                while time.monotonic() < deadline:
                    if self.proc.poll() is not None:
                        raise AssertionError(
                            f"daemon exited early (rc={self.proc.returncode})"
                            f"\nstderr tail:\n{self.stderr_tail()}"
                        )
                    try:
                        resp = client.get(
                            "/v1", headers={"Authorization": f"Bearer {self.token}"}
                        )
                        if resp.status_code == 200:
                            return
                        last_error = f"/v1 -> {resp.status_code} {resp.text[:200]}"
                    except httpx.HTTPError as error:
                        last_error = repr(error)
                    time.sleep(0.2)
            raise AssertionError(
                f"daemon not ready: {last_error}\nstderr tail:\n{self.stderr_tail()}"
            )
        except BaseException:
            self.close()
            raise

    def stderr_tail(self, size: int = 3000) -> str:
        return self.stderr_path.read_text(errors="replace")[-size:]

    def client(self) -> httpx.Client:
        return httpx.Client(
            base_url=f"http://127.0.0.1:{self.port}",
            timeout=10.0,
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def start_run(self, client: httpx.Client) -> str:
        """Drive a real sim run over REST; returns the run id. On a
        ``slow`` daemon the ACTIVE binding is the derived slow one (the
        ~6 s in-body window that makes a stop decision landing seconds
        after acceptance observe the run in-body — record §7, F14)."""
        import hashlib

        bench = client.get(
            "/v1/benches", params={"limit": 100}
        ).json()["data"]["items"][0]
        raw = (self.fixtures / "run-binding.json").read_bytes()
        request_id = json.loads(raw)["request_id"]
        binding = {
            "id": request_id,
            "version": "0.1.0",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        resp = client.post(
            f"/v1/benches/{bench['bench_id']}/runs",
            json={
                "request_id": request_id,
                "binding_ref": binding,
                "expected_generation": bench["generation"],
            },
        )
        assert resp.status_code == 202, resp.text
        return str(resp.json()["data"]["run_id"])

    def wait_run_state(
        self, client: httpx.Client, run_id: str, *states: str, timeout: float = 30.0
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            resp = client.get(f"/v1/runs/{run_id}")
            assert resp.status_code == 200, resp.text
            last = resp.json()["data"]
            if last.get("state") in states:
                return last
            time.sleep(0.2)
        raise AssertionError(f"run never reached {states}: {last}")

    def pid(self) -> int:
        from benchweave.supervision import read_pidfile

        record = read_pidfile(self.data_dir / "state.sqlite")
        assert record is not None, "the daemon must write its pidfile"
        return int(record["pid"])

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
def daemon(tmp_path: Path) -> Iterator[Daemon]:
    gate = Daemon(tmp_path, principal=f"lifecycle-{secrets.token_hex(4)}")
    try:
        yield gate
    finally:
        gate.close()


@pytest.fixture()
def slow_daemon(tmp_path: Path) -> Iterator[Daemon]:
    gate = Daemon(tmp_path, principal=f"lifecycle-{secrets.token_hex(4)}", slow=True)
    try:
        yield gate
    finally:
        gate.close()


def _stop_cli(
    data_dir: Path, *args: str
) -> tuple[int, str]:
    """Run the REAL stop CLI as a subprocess (thread-safe, isolated)."""
    proc = subprocess.run(
        [sys.executable, "-m", "benchweave", "stop", "--data-dir", str(data_dir), *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _journal_events(data_dir: Path) -> list[dict[str, Any]]:
    from benchweave.supervision import journal_path

    path = journal_path(data_dir / "state.sqlite")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _run_at_rest(data_dir: Path, run_id: str) -> dict[str, Any] | None:
    from benchweave.state.store import Store

    store = Store.open(data_dir / "state.sqlite", check_same_thread=False)
    try:
        return store.get_run(run_id)
    finally:
        store.close()


# --- the arms (record §7) ---------------------------------------------------------


@POSIX_ONLY
def test_l1_idle_stop_drains_releases_and_journals(daemon: Daemon) -> None:
    """L1: idle stop — verdict accepted, process exited, hold released,
    pidfile gone, supervision rows `stop_requested`(SIGTERM)+`stopped`,
    and the R9 wall-time bound holds."""
    from benchweave.state.hold import daemon_holds

    pid = daemon.pid()
    started = time.monotonic()
    code, output = _stop_cli(daemon.data_dir)
    elapsed = time.monotonic() - started
    assert code == 0, output
    assert elapsed < L1_WALL_BOUND_S, (
        f"the idle plain stop must be bounded: took {elapsed:.1f}s"
    )
    assert "accepted" in output
    daemon.proc.wait(timeout=10)
    assert daemon.proc.returncode == 0, daemon.stderr_tail()
    assert not daemon_holds(daemon.data_dir / "state.sqlite")
    from benchweave.supervision import pid_path

    assert not pid_path(daemon.data_dir / "state.sqlite").exists()
    events = [row["event"] for row in _journal_events(daemon.data_dir)]
    assert "stop_requested" in events
    requested = _journal_events(daemon.data_dir)[events.index("stop_requested")]
    assert requested["signal_name"] == "SIGTERM"
    assert requested["target_pid"] == pid
    assert "stopped" in events
    assert "did not drain" not in daemon.stderr_tail()


@POSIX_ONLY
def test_l2_active_plain_stop_refuses_run_active(slow_daemon: Daemon) -> None:
    """L2: a live run + plain stop → typed `stop_refused_run_active:` naming
    the run; the daemon KEEPS serving (a follow-up read succeeds); the run
    continues to its own terminal; no terminal record was written by the
    stop (the KILL-on-sight condition)."""
    daemon = slow_daemon
    with daemon.client() as client:
        run_id = daemon.start_run(client)
        daemon.wait_run_state(client, run_id, "running")
        code, output = _stop_cli(daemon.data_dir)
        assert code != 0, output
        assert "stop_refused_run_active:" in output
        assert run_id in output
        # Still serving: the follow-up read succeeds.
        alive = client.get(f"/v1/runs/{run_id}")
        assert alive.status_code == 200, alive.text
        # The run continues to its own terminal state.
        final = daemon.wait_run_state(client, run_id, "terminal", timeout=60.0)
        assert final["state"] == "terminal"
    run = _run_at_rest(daemon.data_dir, run_id)
    assert run is not None
    terminal = run["terminal"]
    assert terminal is not None, "the run's OWN lifecycle terminalized it"
    assert str(terminal["body_outcome"]) != "interrupted", (
        "a plain-stop refusal must never manufacture an outcome"
    )


@POSIX_ONLY
def test_l3_protective_stop_cancels_with_transition_truth(slow_daemon: Daemon) -> None:
    """L3: protective — run terminal `cancelled` with the transition's
    safe_state; verdict accepted + deadline; exit 0; hold released; rows
    `protective_cancel` + `terminal_observed`."""
    daemon = slow_daemon
    from benchweave.supervision import read_stop_file

    with daemon.client() as client:
        run_id = daemon.start_run(client)
        daemon.wait_run_state(client, run_id, "running")
    code, output = _stop_cli(daemon.data_dir, "--protective")
    assert code == 0, output
    assert "accepted" in output
    daemon.proc.wait(timeout=30)
    run = _run_at_rest(daemon.data_dir, run_id)
    assert run is not None and run["terminal"] is not None
    assert run["terminal"]["body_outcome"] == "cancelled"
    verdict = read_stop_file(daemon.data_dir / "state.sqlite")
    assert verdict is not None and verdict.get("status") == "accepted"
    assert verdict.get("mode") == "protective"
    assert verdict.get("protective_deadline_wall")
    assert run_id in verdict.get("run_ids", [])
    quoted = verdict.get("terminal_observed", [])
    assert any(
        row.get("run_id") == run_id
        and row.get("outcome") == "cancelled"
        and row.get("source") == "coordinator_terminal_record"
        for row in quoted
    ), verdict
    events = {row["event"]: row for row in _journal_events(daemon.data_dir)}
    assert "protective_cancel" in events
    assert run_id in events["protective_cancel"]["run_ids"]
    observed = [r for r in _journal_events(daemon.data_dir)
                if r["event"] == "terminal_observed"]
    assert any(r["run_id"] == run_id and r["outcome"] == "cancelled" for r in observed)
    # The quoted safe_state is the coordinator's own record, verbatim.
    assert all(
        r.get("safe_state") == run["terminal"]["safe_state"] for r in observed
    )


@POSIX_ONLY
def test_l3b_active_and_queued_one_writer_per_run(slow_daemon: Daemon) -> None:
    """L3b (lane-1 F1's arm): run A live, run B accepted (a seeded queued
    ghost — the #156 shape) → protective stop: B NEVER dispatches, B
    finalizes `interrupted` via the scoped sweep, A ends `cancelled` with
    its transition truth, exactly ONE writer terminalizes each run."""
    daemon = slow_daemon
    from benchweave.state.store import Store

    with daemon.client() as client:
        run_a = daemon.start_run(client)
        daemon.wait_run_state(client, run_a, "running")
        # Seed B as the queued ghost: a durable run row + accepted
        # projection, never enqueued (the shutdown-drain shape). The
        # binding pin is REAL (the slow lattice's own binding) so the
        # stop sweep's version resolution judges it like any stored run —
        # an empty pin is the containment class, not a sweepable ghost.
        import hashlib as _hashlib

        binding_raw = (daemon.fixtures / "run-binding.json").read_bytes()
        binding_pin = {
            "id": json.loads(binding_raw)["request_id"],
            "version": "0.1.0",
            "sha256": _hashlib.sha256(binding_raw).hexdigest(),
        }
        store = Store.open(daemon.data_dir / "state.sqlite")
        try:
            store.create_run(
                "run-queuedghost0001",
                binding=binding_pin,
                principal_id="lifecycle-seeder",
                now=_now_iso(),
            )
            store.put_run_state(
                "run-queuedghost0001", BENCH_ID, "accepted", "2026-10-08T00:00:01Z"
            )
        finally:
            store.close()
    code, output = _stop_cli(daemon.data_dir, "--protective")
    assert code == 0, output
    daemon.proc.wait(timeout=30)
    run_a_row = _run_at_rest(daemon.data_dir, run_a)
    run_b_row = _run_at_rest(daemon.data_dir, "run-queuedghost0001")
    assert run_a_row is not None and run_a_row["terminal"] is not None
    assert run_a_row["terminal"]["body_outcome"] == "cancelled"
    assert run_b_row is not None and run_b_row["terminal"] is not None
    assert run_b_row["terminal"]["body_outcome"] == "interrupted"
    reasons = run_b_row["terminal"]["reasons"]
    assert any("gateway stop: run was never started" in str(r) for r in reasons), (
        f"the stop-sweep era reason must ride the record: {reasons}"
    )


@POSIX_ONLY
def test_l4_bare_sigterm_idle_is_the_execstop_contract(daemon: Daemon) -> None:
    """L4: bare SIGTERM on an idle serve (no request file) — graceful
    lifespan drain, exit 0, hold released, NO 'did not drain' log line
    (the F3 fold: `should_exit` directly, never the captured-signal replay)."""
    from benchweave.state.hold import daemon_holds

    os.kill(daemon.pid(), signal.SIGTERM)
    daemon.proc.wait(timeout=15)
    assert daemon.proc.returncode == 0, (
        f"exit {daemon.proc.returncode} — the captured-signal replay would "
        f"end the process by signal 15\nstderr tail:\n{daemon.stderr_tail()}"
    )
    assert not daemon_holds(daemon.data_dir / "state.sqlite")
    tail = daemon.stderr_tail()
    assert "did not drain" not in tail, tail


@POSIX_ONLY
def test_l11_two_concurrent_stops_one_action_truthful_reports(
    slow_daemon: Daemon, tmp_path: Path
) -> None:
    daemon = slow_daemon
    """L11 (R7/F7): two concurrent stops — one plain, one protective —
    against one busy gateway: exactly ONE action occurs (the consumed
    mode); both CLIs exit with truthful reports (the loser observes the
    mode mismatch as a typed note)."""
    with daemon.client() as client:
        run_id = daemon.start_run(client)
        daemon.wait_run_state(client, run_id, "running")
    plain = subprocess.Popen(
        [sys.executable, "-m", "benchweave", "stop", "--data-dir",
         str(daemon.data_dir)],
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    protective = subprocess.Popen(
        [sys.executable, "-m", "benchweave", "stop", "--data-dir",
         str(daemon.data_dir), "--protective"],
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    plain_out = plain.communicate(timeout=120)[0]
    protective_out = protective.communicate(timeout=120)[0]
    from benchweave.supervision import read_stop_file

    verdict = read_stop_file(daemon.data_dir / "state.sqlite")
    assert verdict is not None, "one request must have been consumed"
    consumed = verdict.get("mode")
    assert consumed in ("plain", "protective")
    if consumed == "protective":
        daemon.proc.wait(timeout=30)
        run = _run_at_rest(daemon.data_dir, run_id)
        assert run is not None and run["terminal"] is not None
        assert run["terminal"]["body_outcome"] == "cancelled", (
            "exactly one action: the protective consumption cancelled the run"
        )
        # The loser's report is TRUTHFUL: the gateway DID stop (exit 0
        # mirrors the observed outcome) and the typed note names whose
        # mode acted — the record's "both CLIs exit with truthful
        # reports", not a failure that never happened.
        assert plain.returncode == 0, (
            f"the plain loser's report:\n{plain_out}"
        )
        assert "stopped: True" in plain_out or '"stopped": true' in plain_out
        assert "stop_mode_superseded:" in plain_out, plain_out
    else:
        # The plain request was consumed against a BUSY gateway: it gets
        # the truthful run_active refusal (non-zero), the daemon keeps
        # serving, and the run reaches its OWN terminal untouched.
        assert plain.returncode != 0, plain_out
        assert "stop_refused_run_active:" in plain_out, plain_out
        with daemon.client() as client:
            alive = client.get(f"/v1/runs/{run_id}")
            assert alive.status_code == 200, "the daemon is still serving"
            final = daemon.wait_run_state(client, run_id, "terminal", timeout=60.0)
        assert final["state"] == "terminal"
        assert "stop_mode_superseded:" in protective_out, protective_out


@POSIX_ONLY
def test_l12_foreign_owner_request_not_consumed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """L12 (F3 fold): a foreign-owned request file is NOT consumed — the
    daemon answers with the typed `supervision_stop_foreign_owner:` line,
    the request file stays a request, nothing acts.

    Deviation from the record's tabled mechanics, DISCLOSED: `os.chown` to
    a foreign uid needs privilege neither macOS dev nor the CI runners
    have, so the arm stages foreign ownership by stubbing the stat the
    daemon-side check reads — in-process (the poll decision is the real
    production code), not cross-process."""
    import logging

    from benchweave import supervision
    from benchweave.supervision import read_stop_file

    app, server, thread, store = _compose_armed(tmp_path)
    try:
        surface = app.state.supervision
        db = surface.db_path
        supervision.write_stop_request(db, mode="protective", actor_pid=999999)
        # Stage foreign ownership without privilege: the daemon-side owner
        # check reads through supervision._path_owner_uid — the arm pins
        # the real decision over a foreign uid (the chown the record's
        # table presumes needs root neither macOS nor CI runners have).
        monkeypatch.setattr(
            supervision, "_path_owner_uid", lambda path: os.getuid() + 4242
        )
        with caplog.at_level(logging.WARNING, logger="benchweave.interfaces"):
            surface.poll_once()
        assert "supervision_stop_foreign_owner:" in caplog.text, caplog.text
        after = read_stop_file(db)
        assert after is not None and "status" not in after, (
            "the foreign request must NOT be consumed"
        )
        assert server.should_exit is False, "nothing acts on a foreign request"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        store.close()


def _compose_armed(
    tmp_path: Path,
) -> tuple[Any, Any, threading.Thread, Any]:
    """The in-process armed composition (the parity-suite `_boot` pattern):
    real uvicorn thread, real lifespan (hold + pidfile + doorbell poll)."""
    from fastapi import FastAPI

    from benchweave.content.store import ContentStore
    from benchweave.interfaces.app import create_app
    from benchweave.state.store import Store

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    store = Store.open(data_dir / "state.sqlite", check_same_thread=False)
    content = ContentStore(store)
    app: FastAPI = create_app(
        store=store,
        content=content,
        secret=b"wp08-task-nine-secret",
        limits={"max_json_bytes": 1048576, "max_page_size": 100,
                "max_chunk_bytes": 65536, "max_lease_ms": 21600000,
                "min_poll_ms": 100, "max_admission_ms": 5000},
        gateway_id="gw-lifecycle-arm",
        fixtures_dir=FIXTURES,
        now_iso=_now_iso,
        now_epoch=lambda: 0,
        supervision_armed=True,
    )
    app.state.harness_store = store
    server, thread = _boot(app)
    return app, server, thread, store


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


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def test_l13_run_start_concurrent_with_idle_plain_stop(tmp_path: Path) -> None:
    """L13 (F4's arm, composition-level): the run_start body in flight as
    the stop decision reads live states — set-then-check under the write
    gate closes the TOCTOU. The forced interleave pins the mechanism;
    the racing loop pins the invariant: NEVER a stop window that read
    idle (accepted) while a run it could not see went on to be created."""
    from benchweave.interfaces.errors import OperationFailure
    from benchweave.interfaces.identity import Identity

    app, server, thread, store = _compose_armed(tmp_path)
    try:
        surface = app.state.supervision
        operations = app.state.operations
        gate = app.state.write_gate
        identity = Identity(
            "l13-principal", "stg", frozenset({"stg:control"}), 2**31
        )
        binding = _binding_ref()

        # The forced interleave: the stop window OPENS (flag set + states
        # read, under the write gate) and only then does the start run.
        window = surface.open_stop_window()
        refused: list[str] = []
        with gate:
            generation = store.current_generation(BENCH_ID)
            try:
                operations.run_start(
                    identity, BENCH_ID, BINDING_REQUEST_ID, binding, generation, None
                )
            except OperationFailure as failure:
                refused.append(str(failure.failure.body()))
        assert any("stop_in_progress:" in text for text in refused), refused
        assert window.live_runs == [], "the window read idle (accepted-shape)"
        # No run row exists: the refused start created nothing.
        assert store.list_run_states(BENCH_ID) == [] or all(
            row["state"] == "terminal"
            for row in store.list_run_states(BENCH_ID)
        ), "a refused start must leave no live run behind"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        store.close()


def test_l13_racing_loop_never_abandons_a_run_under_an_idle_window(
    tmp_path: Path,
) -> None:
    """L13's closed invariant under real scheduling: rounds of a run_start
    racing the stop window — in NO round do both (the window read idle)
    and (a run was created) hold. A created round drains before the next
    (the bench is busy until its run terminalizes)."""
    from benchweave.interfaces.errors import OperationFailure
    from benchweave.interfaces.identity import Identity

    app, server, thread, store = _compose_armed(tmp_path)
    try:
        surface = app.state.supervision
        operations = app.state.operations
        gate = app.state.write_gate
        binding = _binding_ref()
        for round_no in range(6):
            # A distinct principal per round: the §9 key is principal+op+
            # request_id, and the binding document's own request_id must
            # equal the wire request id — so the round's freshness rides
            # the principal, never the request id.
            identity = Identity(
                f"l13-race-{round_no}", "stg", frozenset({"stg:control"}), 2**31
            )
            created: list[bool] = []
            errors: list[OperationFailure] = []

            def starter(
                identity: Any = identity,
                created: list[bool] = created,
                errors: list[OperationFailure] = errors,
            ) -> None:
                # B023: the loop variables bind as defaults, not closures.
                with gate:
                    try:
                        operations.run_start(
                            identity,
                            BENCH_ID,
                            BINDING_REQUEST_ID,
                            binding,
                            store.current_generation(BENCH_ID),
                            None,
                        )
                        created.append(True)
                    except OperationFailure as failure:
                        errors.append(failure)

            racer = threading.Thread(target=starter)
            racer.start()
            window = surface.open_stop_window()
            racer.join()
            if window.live_runs == []:
                assert not created or errors, (
                    "an idle window with a created run is the abandoned-run "
                    "shape F4 closes"
                )
            surface.reset_stop_window()
            if created:
                _drain_live_runs(store)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        store.close()


def _drain_live_runs(store: Any, timeout: float = 40.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        states = store.list_run_states(BENCH_ID)
        if all(row["state"] == "terminal" for row in states):
            return
        time.sleep(0.2)
    raise AssertionError("a created racing run never terminalized")


def _binding_ref() -> dict[str, str]:
    import hashlib

    raw = (FIXTURES / "run-binding.json").read_bytes()
    return {
        "id": json.loads(raw)["request_id"],
        "version": "0.1.0",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


# --- start / restart (record §4.1) ------------------------------------------------


def test_start_refuses_when_pidfile_verifies_ours(tmp_path: Path) -> None:
    from benchweave.supervision import write_pidfile

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    (data_dir / "state.sqlite").write_bytes(b"")
    write_pidfile(data_dir / "state.sqlite", gateway_id="gw-x",
                  log_destination="stderr")
    result = CliRunner().invoke(cli, ["start", "--data-dir", str(data_dir)])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "supervision_already_running:" in combined
    assert str(os.getpid()) in combined, "the refusal names the pid"


def test_start_refuses_when_hold_held_without_pidfile(tmp_path: Path) -> None:
    """The dual-ownership guard: a held store with no pidfile (the
    'systemd owns it' shape) refuses naming the holder — start never
    spawns a second contender (muninndb's restart-race lesson)."""
    from benchweave.state.hold import StoreHold

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    db = data_dir / "state.sqlite"
    db.write_bytes(b"")
    with StoreHold(db, label="gateway gw-systemd"):
        result = CliRunner().invoke(cli, ["start", "--data-dir", str(data_dir)])
    assert result.exit_code != 0
    combined = _combined(result)
    assert "gateway gw-systemd" in combined, "the holder is named"


def test_start_refuses_when_no_store(tmp_path: Path) -> None:
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    result = CliRunner().invoke(cli, ["start", "--data-dir", str(data_dir)])
    assert result.exit_code != 0
    assert "no store at" in _combined(result)


def test_start_spawns_detached_and_reports_readiness(tmp_path: Path) -> None:
    """The §4.1 happy path: detached spawn, stderr to <dir>.log, readiness
    = the pidfile appears and names the child (hold-acquired readiness),
    the end-of-wait liveness re-check passes, and the daemon serves."""
    from benchweave.cli import atrest
    from benchweave.supervision import log_path, read_pidfile

    data_dir = tmp_path / "gateway"
    atrest.setup(data_dir)
    port = _free_port()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("BENCHWEAVE_")
    }
    env.update({"BENCHWEAVE_FIXTURES": str(FIXTURES)})
    proc = subprocess.run(
        [sys.executable, "-m", "benchweave", "start", "--data-dir", str(data_dir),
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO), capture_output=True, text=True, timeout=60, env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    record = read_pidfile(data_dir / "state.sqlite")
    assert record is not None
    child_pid = int(record["pid"])
    assert record["log_destination"] == str(log_path(data_dir / "state.sqlite"))
    assert log_path(data_dir / "state.sqlite").exists(), "stderr went to <dir>.log"
    try:
        from benchweave.interfaces.identity import issue

        token = issue(
            atrest.read_secret(data_dir).encode(),
            principal="start-arm", audience="stg", scopes={"stg:observe"},
            expires_at=int(time.time()) + 3600,
        )
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5.0) as client:
            deadline = time.monotonic() + 30.0
            while True:
                try:
                    resp = client.get("/v1", headers={
                        "Authorization": f"Bearer {token}"})
                    if resp.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "started daemon never served"
                time.sleep(0.2)
    finally:
        stopped = subprocess.run(
            [sys.executable, "-m", "benchweave", "stop", "--data-dir",
             str(data_dir)],
            cwd=str(REPO), capture_output=True, text=True, timeout=60,
        )
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    # The child is gone and the sidecar cleaned.
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except OSError:
            break
        time.sleep(0.2)
    else:
        raise AssertionError("the stopped child is still alive")
    assert read_pidfile(data_dir / "state.sqlite") is None


def test_start_child_dying_in_the_window_is_nonzero_with_log_hint(
    tmp_path: Path,
) -> None:
    """F8 fold: a child dying before readiness → non-zero with the log-tail
    hint, never a hung window, never exit-0-over-a-dead-daemon. The boot is
    made to refuse via the production secret posture (a public secret)."""
    from benchweave.cli import atrest

    data_dir = tmp_path / "gateway"
    atrest.setup(data_dir)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("BENCHWEAVE_")
    }
    env.update(
        {
            "BENCHWEAVE_ENV": "production",
            "BENCHWEAVE_SECRET": "wp07-task-eleven-secret",
            "BENCHWEAVE_FIXTURES": str(FIXTURES),
        }
    )
    proc = subprocess.run(
        [sys.executable, "-m", "benchweave", "start", "--data-dir", str(data_dir),
         "--host", "127.0.0.1", "--port", str(_free_port())],
        cwd=str(REPO), capture_output=True, text=True, timeout=60, env=env,
    )
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "refusing" in combined or "log" in combined.lower(), (
        "the failure names the boot refusal and points at the log"
    )


@POSIX_ONLY
def test_restart_stops_then_starts_with_a_new_pid(tmp_path: Path) -> None:
    from benchweave.cli import atrest
    from benchweave.supervision import read_pidfile

    data_dir = tmp_path / "gateway"
    atrest.setup(data_dir)
    port = _free_port()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("BENCHWEAVE_")
    }
    env.update({"BENCHWEAVE_FIXTURES": str(FIXTURES)})
    first = subprocess.run(
        [sys.executable, "-m", "benchweave", "start", "--data-dir", str(data_dir),
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO), capture_output=True, text=True, timeout=60, env=env,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    old_record = read_pidfile(data_dir / "state.sqlite")
    assert old_record is not None
    old_pid = int(old_record["pid"])
    second = subprocess.run(
        [sys.executable, "-m", "benchweave", "restart", "--data-dir", str(data_dir),
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO), capture_output=True, text=True, timeout=90, env=env,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    new_record = read_pidfile(data_dir / "state.sqlite")
    assert new_record is not None
    new_pid = int(new_record["pid"])
    assert new_pid != old_pid, "restart must produce a NEW process"
    try:
        from benchweave.interfaces.identity import issue

        token = issue(
            atrest.read_secret(data_dir).encode(),
            principal="restart-arm", audience="stg", scopes={"stg:observe"},
            expires_at=int(time.time()) + 3600,
        )
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5.0) as client:
            deadline = time.monotonic() + 30.0
            while True:
                try:
                    resp = client.get("/v1", headers={
                        "Authorization": f"Bearer {token}"})
                    if resp.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "restarted daemon never served"
                time.sleep(0.2)
    finally:
        subprocess.run(
            [sys.executable, "-m", "benchweave", "stop", "--data-dir",
             str(data_dir)],
            cwd=str(REPO), capture_output=True, text=True, timeout=60,
        )


# --- service install (record §4.3, L10) --------------------------------------------


def _commissioned_store(data_dir: Path) -> None:
    """A setup'd store whose lattice is admitted (the app-boot admission
    path, run at rest): the bench row + its pinned policy land in the
    store — `service install`'s commissioned ceiling source."""
    from benchweave.content.store import ContentStore
    from benchweave.interfaces.bootstrap import admit_startup_bench
    from benchweave.state.store import Store

    store = Store.open(data_dir / "state.sqlite", check_same_thread=False)
    try:
        admit_startup_bench(
            store, ContentStore(store), FIXTURES, now=_now_iso()
        )
    finally:
        store.close()


def test_l10_service_install_derives_timeout_from_commissioned_ceilings(
    tmp_path: Path,
) -> None:
    """L10: a commissioned store renders ExecStop + TimeoutStopSec =
    commissioned max + 30 s (the fixtures' 2000 ms policy → 32 s)."""
    from benchweave.cli import atrest

    data_dir = tmp_path / "gateway"
    atrest.setup(data_dir)
    _commissioned_store(data_dir)
    unit_out = tmp_path / "benchweave.service"
    result = CliRunner().invoke(
        cli,
        ["service", "install", "--data-dir", str(data_dir),
         "--unit-output", str(unit_out)],
    )
    assert result.exit_code == 0, _combined(result)
    text = unit_out.read_text()
    assert re.search(r"^ExecStop=.+benchweave stop", text, re.MULTILINE)
    assert re.search(r"^TimeoutStopSec=32s$", text, re.MULTILINE)
    assert "{{" not in text


def test_l10_service_install_uncommissioned_renders_default_with_comment(
    tmp_path: Path,
) -> None:
    from benchweave.cli import atrest

    data_dir = tmp_path / "gateway"
    atrest.setup(data_dir)
    unit_out = tmp_path / "benchweave.service"
    result = CliRunner().invoke(
        cli,
        ["service", "install", "--data-dir", str(data_dir),
         "--unit-output", str(unit_out)],
    )
    assert result.exit_code == 0, _combined(result)
    text = unit_out.read_text()
    assert re.search(r"^ExecStop=.+benchweave stop", text, re.MULTILINE)
    assert "TimeoutStopSec=" not in text.replace(
        "# TimeoutStopSec=", ""
    ), "uncommissioned renders the manager default, not a fabricated ceiling"
    assert "no commissioned" in text, "the fallback carries the disclosed comment"


def test_service_install_refuses_while_a_live_gateway_holds_the_store(
    tmp_path: Path,
) -> None:
    from benchweave.cli import atrest
    from benchweave.state.hold import StoreHold

    data_dir = tmp_path / "gateway"
    atrest.setup(data_dir)
    with StoreHold(data_dir / "state.sqlite", label="gateway gw-live"):
        result = CliRunner().invoke(
            cli,
            ["service", "install", "--data-dir", str(data_dir),
             "--unit-output", str(tmp_path / "u.service")],
        )
    assert result.exit_code != 0
    assert "gateway gw-live" in _combined(result)


def test_service_install_renders_launchd_plist_on_macos(tmp_path: Path) -> None:
    from benchweave.cli import atrest

    data_dir = tmp_path / "gateway"
    atrest.setup(data_dir)
    _commissioned_store(data_dir)
    plist_out = tmp_path / "com.benchweave.gateway.plist"
    result = CliRunner().invoke(
        cli,
        ["service", "install", "--data-dir", str(data_dir),
         "--plist-output", str(plist_out)],
    )
    if sys.platform != "darwin":
        # The plist analogue renders on macOS only; the arm degrades to a
        # typed note on the other platforms (the unit is the deploy target).
        assert result.exit_code != 0
        return
    assert result.exit_code == 0, _combined(result)
    text = plist_out.read_text()
    assert "launchd" in text
    assert "benchweave stop" in text, "the ExecStop mapping is named in comments"
    assert "TimeoutStopSec" in text, "the divergence is tabled in comments"


# --- helpers ----------------------------------------------------------------------


def _combined(result: Result) -> str:
    """stdout + stderr, robust to click < 8.2's mixed-stream Result."""
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return cast(int, sock.getsockname()[1])
