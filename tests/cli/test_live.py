"""Task 11: live demo — gateway mode, fresh-install mode, anti-coordinate.

The brief's three RED tests plus the controller-ruling pins:

- Gateway mode against a LIVE composed gateway (uvicorn on an ephemeral
  port, the T9 boot pattern — no mocks): a run reaches a terminal state,
  the outcome and the terminal record's evidence digests are printed.
- Fresh-install mode (no ``--gateway``): the demo boots its own ephemeral
  app on a SCRATCH temp dir, drives the fixture simulator procedure to
  terminal, labels every rendered surface ``SIMULATION``, and tears down
  (scratch removed unless ``--keep``).
- Anti-coordinate (ISC-12): fresh-install mode refuses when a live gateway
  holds any store under the scratch dir — proven against a REAL gateway
  booted by this module's fixture, with demo's scratch pointed at its
  store directory.
- Timeout truthfulness (unit level — the poll loop, not a fake gateway):
  a run that never terminates produces a truthful failure naming the run
  and its last observed state.
- The three T10 review carries: ``verify`` on an invalid manifest.json and
  ``setup`` under an unwritable parent exit truthfully instead of
  tracebacking, and ``daemon_holds`` reads a PermissionError probe as HELD
  (the pinned safe direction).
"""

from __future__ import annotations

import errno
import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import uvicorn
from click.testing import CliRunner, Result
from fastapi import FastAPI

from benchweave.cli.commands import cli
from benchweave.cli.demo import DemoError, poll_to_terminal
from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import issue
from benchweave.state.hold import daemon_holds
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
SECRET = b"wp08-task-eleven-secret"
NOW_ISO = "2026-09-13T00:00:00Z"
NOW_EPOCH = 1_800_000_000
GATEWAY_ID = "gw-task11-live"
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}


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


def _dead_port() -> int:
    """A loopback port that is (near-certainly) refusing connections."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return cast(int, sock.getsockname()[1])


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
    """One live composed gateway holding a NON-canonically-named store.

    The store file is ``state.db`` (not the at-rest ``state.sqlite``) so the
    anti-coordinate test proves the scan discovers ANY held store under the
    scratch dir, not just the canonical name.
    """
    store_dir = tmp_path_factory.mktemp("task11-live")
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
        principal="task11-control",
        audience="stg",
        scopes={"stg:control"},
        expires_at=NOW_EPOCH + 3600,
    )
    yield SimpleNamespace(
        base=f"http://127.0.0.1:{port}", token=token, store_dir=store_dir
    )
    server.should_exit = True
    thread.join(timeout=5)
    store.close()


# --- gateway mode: a live run to terminal with evidence -------------------------


def test_demo_gateway_mode_json_reaches_terminal_with_evidence(
    gateway: SimpleNamespace,
) -> None:
    result = CliRunner().invoke(
        cli,
        ["demo", "--gateway", gateway.base, "--token", gateway.token, "--json"],
    )
    assert result.exit_code == 0, _combined(result)
    payload = json.loads(result.output)
    assert payload["mode"] == "gateway"
    assert payload["simulation"] is False
    assert payload["label"] is None
    assert "scratch_dir" not in payload  # simulation-only key stays simulation-only
    assert payload["gateway"] == gateway.base
    assert payload["bench_id"] == "sim-bench"
    assert payload["procedure_id"] == "voltage-check"
    assert payload["request_id"] == "req-voltage-check-1"
    assert payload["run_id"].startswith("run-")
    assert payload["state"] == "terminal"
    assert payload["outcome"] == "passed"
    assert payload["safe_state"] == "verified"
    terminal = payload["terminal_record"]
    assert isinstance(terminal, dict)
    assert len(terminal["sha256"]) == 64
    # The REST surface serves the run record as a closed ref; its sha256 is
    # the digest of the evidence-bearing record — the demo's evidence digest.
    digests = payload["evidence_digests"]
    assert digests == [terminal["sha256"]]
    assert isinstance(payload["events_observed"], int)
    assert payload["events_observed"] >= 1


def test_demo_gateway_mode_text_names_outcome_and_is_not_a_simulation(
    gateway: SimpleNamespace,
) -> None:
    result = CliRunner().invoke(
        cli, ["demo", "--gateway", gateway.base, "--token", gateway.token]
    )
    assert result.exit_code == 0, _combined(result)
    assert "passed" in result.output
    assert "SIMULATION" not in result.output


def test_demo_gateway_mode_dead_port_refuses_truthfully() -> None:
    port = _dead_port()
    result = CliRunner().invoke(
        cli, ["demo", "--gateway", f"http://127.0.0.1:{port}", "--token", "t"]
    )
    _handled(result)
    assert result.exit_code != 0
    assert "unreachable" in _combined(result)


# --- fresh-install mode: ephemeral, labelled, torn down --------------------------


def test_demo_fresh_install_json_labelled_simulation_and_torn_down(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "fresh"  # absent: the demo creates — and removes — it
    result = CliRunner().invoke(cli, ["demo", "--scratch", str(scratch), "--json"])
    assert result.exit_code == 0, _combined(result)
    payload = json.loads(result.output)
    assert payload["mode"] == "simulation"
    assert payload["simulation"] is True
    assert payload["label"] == "SIMULATION"
    assert payload["scratch_dir"] == str(scratch)
    assert payload["bench_id"] == "sim-bench"
    assert payload["state"] == "terminal"
    assert payload["outcome"] == "passed"
    assert payload["safe_state"] == "verified"
    assert payload["evidence_digests"], "the simulator run retains its evidence digest"
    assert not scratch.exists(), "scratch dir must be removed unless --keep"


def test_demo_fresh_install_text_carries_simulation_label(tmp_path: Path) -> None:
    scratch = tmp_path / "fresh-text"
    result = CliRunner().invoke(cli, ["demo", "--scratch", str(scratch)])
    assert result.exit_code == 0, _combined(result)
    assert "SIMULATION" in result.output  # the non-TTY plain surface is labelled too
    assert "passed" in result.output
    assert not scratch.exists()


def test_demo_fresh_install_default_scratch_is_removed() -> None:
    """The default (mkdtemp) scratch path is a demo-created tree: the whole
    directory leaves with the demo — found by a real-binary smoke, pinned
    here because the --scratch variants cannot see the default path."""
    result = CliRunner().invoke(cli, ["demo", "--json"])
    assert result.exit_code == 0, _combined(result)
    payload = json.loads(result.output)
    scratch = Path(payload["scratch_dir"])
    assert "benchweave-demo-" in scratch.name
    assert not scratch.exists(), "the default mkdtemp scratch must be removed"


def test_demo_fresh_install_keep_retains_scratch(tmp_path: Path) -> None:
    scratch = tmp_path / "kept"
    result = CliRunner().invoke(
        cli, ["demo", "--scratch", str(scratch), "--keep", "--json"]
    )
    assert result.exit_code == 0, _combined(result)
    payload = json.loads(result.output)
    assert payload["kept"] is True
    assert scratch.is_dir()
    assert (scratch / "state.sqlite").is_file()


def test_demo_fresh_install_preexisting_scratch_survives_with_own_files_removed(
    tmp_path: Path,
) -> None:
    """T11 M3: a pre-existing --scratch directory is the OPERATOR's — the
    demo removes exactly its own store files, never the directory or its
    contents."""
    scratch = tmp_path / "operator-scratch"
    scratch.mkdir()
    operator_file = scratch / "operator-notes.txt"
    operator_file.write_text("operator data", encoding="utf-8")
    result = CliRunner().invoke(cli, ["demo", "--scratch", str(scratch), "--json"])
    assert result.exit_code == 0, _combined(result)
    assert scratch.is_dir(), "the operator's directory must survive"
    assert operator_file.read_text(encoding="utf-8") == "operator data"
    for suffix in ("", "-wal", "-shm", ".hold"):
        assert not (scratch / f"state.sqlite{suffix}").exists(), suffix


# --- anti-coordinate (ISC-12): never compose against a held store ----------------


def test_demo_fresh_install_refuses_a_held_store_under_scratch(
    gateway: SimpleNamespace,
) -> None:
    """The module gateway holds ``store_dir/state.db``; pointing the demo's
    scratch resolution at that directory must refuse BEFORE composing —
    and must not drop a new store file into the held directory."""
    result = CliRunner().invoke(cli, ["demo", "--scratch", str(gateway.store_dir)])
    _handled(result)
    assert result.exit_code != 0
    combined = _combined(result)
    assert "refusing" in combined
    assert "state.db" in combined  # the refusal names the held store it found
    assert not (gateway.store_dir / "state.sqlite").exists()


# --- timeout truthfulness (unit level) -------------------------------------------


class _StuckRun:
    """A run reader whose run never leaves ``running`` (no gateway faked)."""

    def __init__(self) -> None:
        self.calls = 0

    def run_get(self, run_id: str) -> dict[str, Any]:
        self.calls += 1
        return {
            "run_id": run_id,
            "state": "running",
            "outcome": None,
            "safe_state": None,
            "terminal_record": None,
        }


def test_poll_to_terminal_timeout_is_truthful() -> None:
    stuck = _StuckRun()
    with pytest.raises(DemoError) as raised:
        poll_to_terminal(stuck, "run-stuck", timeout_s=0.05, poll_s=0.01)
    message = str(raised.value)
    assert "run-stuck" in message
    assert "did not reach a terminal state" in message
    assert "running" in message  # the last observed state is named
    assert stuck.calls >= 1


def test_demo_rejects_nonpositive_timeout() -> None:
    result = CliRunner().invoke(cli, ["demo", "--timeout", "0"])
    assert result.exit_code != 0
    assert "positive" in _combined(result)


# --- T10 review carries (one-liners, ruled do-now) --------------------------------


def test_verify_invalid_manifest_json_exits_truthfully(tmp_path: Path) -> None:
    target = tmp_path / "archive"
    target.mkdir()
    (target / "manifest.json").write_text("{ truncated", encoding="utf-8")
    result = CliRunner().invoke(cli, ["verify", "--data-dir", str(target)])
    _handled(result)
    assert result.exit_code != 0
    combined = _combined(result)
    assert "not valid JSON" in combined
    assert "manifest.json" in combined


def test_setup_under_a_file_parent_exits_truthfully(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file", encoding="utf-8")
    result = CliRunner().invoke(cli, ["setup", "--data-dir", str(blocker / "x")])
    _handled(result)
    assert result.exit_code != 0
    combined = _combined(result)
    assert str(blocker) in combined  # the refusal names the unusable path


def test_daemon_holds_permissionerror_reads_as_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pinned direction (T10 review): an unreadable hold marker reads as
    HELD — for the anti-coordinate rule a false 'free' risks exactly the
    second coordinator the gate exists to prevent, while a false 'held'
    in the single-operator loopback context is a cheap, truthful retry."""
    db = tmp_path / "state.sqlite"
    hold_file = db.with_name(db.name + ".hold")
    hold_file.write_text("{}", encoding="utf-8")
    real_open = os.open

    def refusing_open(path: object, flags: int, *rest: int) -> int:
        if str(cast("str | os.PathLike[str]", path)) == str(hold_file):
            raise PermissionError(errno.EACCES, "permission denied", str(path))
        return real_open(cast("str | bytes | os.PathLike[str]", path), flags, *rest)

    monkeypatch.setattr("benchweave.state.hold.os.open", refusing_open)
    assert daemon_holds(db) is True
