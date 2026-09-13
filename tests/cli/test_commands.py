"""Task 9: CLI foundation — Click tree, machine output, import confinement.

Covers the brief's three RED tests plus the controller-ruling pins:

- ``--help`` lists all eight commands (CliRunner).
- ``status --json`` against a LIVE composed gateway (uvicorn on an ephemeral
  port — the parity-suite boot pattern, no mocks) parses and carries
  ``gateway_id`` + benches. The exact top-level shape is pinned here because
  it is the machine contract Tasks 10-15 build on (see ``output.py``).
- click/textual import sites exist ONLY under ``src/benchweave/cli/``
  (AST walk over every module — function-level imports included).
- Exit codes: connection refusal and token rejection both exit non-zero with
  a truthful message naming the failure.
- The seven stub commands raise the exact brief message so ``--help`` is
  already the full operator surface today.
- ``main()`` returns int exit codes directly (the console-script contract).
"""

import ast
import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import uvicorn
from click.testing import CliRunner, Result
from fastapi import FastAPI

from benchweave import __version__
from benchweave.cli.client import GatewayClient, GatewayError
from benchweave.cli.commands import cli, main
from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import issue
from benchweave.state.store import Store

COMMANDS = ["setup", "status", "demo", "report", "backup", "restore", "verify", "serve"]
# Tasks 10-13 made the at-rest commands, demo and report live; only serve
# remains a stub until Task 14 lands it.
STUB_COMMANDS = ["serve"]

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
SECRET = b"wp08-task-nine-secret"
NOW_ISO = "2026-09-13T00:00:00Z"
NOW_EPOCH = 1_800_000_000
GATEWAY_ID = "gw-cli-status"
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}
OBSERVE = issue(
    SECRET,
    principal="cli-status",
    audience="stg",
    scopes={"stg:observe"},
    expires_at=NOW_EPOCH + 3600,
)

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "benchweave"
FORBIDDEN_ROOTS = {"click", "textual"}


def _combined(result: Result) -> str:
    """stdout + stderr, robust to click < 8.2's mixed-stream Result."""
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


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
    """One live composed gateway (bootstrap admits the sim-bench)."""
    tmp_path = tmp_path_factory.mktemp("task9-cli")
    store = Store.open(tmp_path / "state.db", check_same_thread=False)
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
    yield SimpleNamespace(base=f"http://127.0.0.1:{port}")
    server.should_exit = True
    thread.join(timeout=5)
    store.close()


# --- surface -----------------------------------------------------------------


def test_help_lists_all_eight_commands() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for name in COMMANDS:
        assert name in result.output, f"--help must list {name}"


@pytest.mark.parametrize("name", STUB_COMMANDS)
def test_stub_commands_fail_with_the_exact_brief_message(name: str) -> None:
    result = CliRunner().invoke(cli, [name])
    assert result.exit_code != 0
    assert "not implemented in this task" in _combined(result)


def test_version_flag_prints_package_version() -> None:
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "benchweave" in result.output
    assert __version__ in result.output


# --- status against a live gateway --------------------------------------------


def test_status_json_shape_is_pinned(gateway: SimpleNamespace) -> None:
    result = CliRunner().invoke(
        cli, ["status", "--gateway", gateway.base, "--token", OBSERVE, "--json"]
    )
    assert result.exit_code == 0, _combined(result)
    payload = json.loads(result.output)
    # The machine contract: exactly two top-level sections (see output.py).
    assert set(payload) == {"gateway", "benches"}
    assert payload["gateway"]["gateway_id"] == GATEWAY_ID
    for key in ("interface_version", "mcp_version", "limits"):
        assert key in payload["gateway"], f"gateway.{key} is contract"
    items = payload["benches"]["items"]
    assert isinstance(items, list)
    assert items, "bootstrap must have admitted at least one bench"
    assert any(item["bench_id"] == "sim-bench" for item in items)
    assert "next_cursor" in payload["benches"]


def test_status_plain_text_when_not_a_tty(gateway: SimpleNamespace) -> None:
    result = CliRunner().invoke(cli, ["status", "--gateway", gateway.base, "--token", OBSERVE])
    assert result.exit_code == 0, _combined(result)
    assert "gateway_id" in result.output
    assert GATEWAY_ID in result.output
    assert "sim-bench" in result.output


def test_status_dead_port_exits_nonzero_with_truthful_message() -> None:
    port = _dead_port()
    result = CliRunner().invoke(
        cli, ["status", "--gateway", f"http://127.0.0.1:{port}", "--token", OBSERVE]
    )
    assert result.exit_code != 0
    combined = _combined(result)
    assert f"127.0.0.1:{port}" in combined
    assert "unreachable" in combined


def test_status_rejected_token_exits_nonzero(gateway: SimpleNamespace) -> None:
    result = CliRunner().invoke(
        cli, ["status", "--gateway", gateway.base, "--token", "forged.token"]
    )
    assert result.exit_code != 0
    combined = _combined(result)
    assert "401" in combined
    assert "token rejected" in combined


# --- wrong-shaped but alive servers (the common misconfiguration) -------------


@contextmanager
def _raw_server(body: bytes, content_type: str) -> Iterator[str]:
    """A real loopback listener serving one fixed 2xx body to any request."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _handled(result: Result) -> None:
    """The failure was handled (exit + message), not a traceback-class exception.

    Standalone Click turns ClickException into SystemExit(1); only genuine
    crashes surface here as Exception instances.
    """
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"must be a handled error, not a traceback: {result.exception!r}"


def test_status_html_2xx_body_exits_nonzero_with_truthful_message() -> None:
    with _raw_server(b"<html><body>gateway admin UI</body></html>", "text/html") as base:
        result = CliRunner().invoke(cli, ["status", "--gateway", base, "--token", OBSERVE])
    _handled(result)
    assert result.exit_code != 0
    combined = _combined(result)
    assert "non-JSON body" in combined
    assert "<html>" in combined  # the repr-escaped snippet names the culprit


def test_status_json_array_2xx_body_exits_nonzero_with_truthful_message() -> None:
    with _raw_server(b"[1, 2, 3]", "application/json") as base:
        result = CliRunner().invoke(cli, ["status", "--gateway", base, "--token", OBSERVE])
    _handled(result)
    assert result.exit_code != 0
    assert "non-JSON-object body" in _combined(result)


def test_client_read_phase_timeout_is_a_gateway_error() -> None:
    """A gateway that answers headers then hangs must not traceback."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "64")
            self.end_headers()
            time.sleep(2.0)

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = GatewayClient(
            f"http://127.0.0.1:{server.server_address[1]}", token="x", timeout=0.3
        )
        with pytest.raises(GatewayError, match="timed out"):
            client.get("/v1")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


# --- entrypoint contract ------------------------------------------------------


def test_main_returns_int_exit_codes() -> None:
    assert main(["--help"]) == 0
    assert main(["status", "--gateway", f"http://127.0.0.1:{_dead_port()}", "--token", "x"]) != 0


# --- T9 carry (Task 10): bare-word gateway URLs must not traceback ----------------


def test_status_schemeless_gateway_url_is_handled_not_a_traceback() -> None:
    """``--gateway banana`` used to escape ``ValueError: unknown url type``
    from deep inside urllib — the constructor now rejects it as GatewayError."""
    result = CliRunner().invoke(cli, ["status", "--gateway", "banana", "--token", OBSERVE])
    _handled(result)
    assert result.exit_code != 0
    combined = _combined(result)
    assert "banana" in combined
    assert "http://" in combined and "https://" in combined


# --- structure pin ------------------------------------------------------------


def test_click_and_textual_imports_confined_to_cli_package() -> None:
    offenders: list[str] = []
    walked = 0
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(SRC_ROOT)
        if rel.parts and rel.parts[0] == "cli":
            continue
        walked += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_ROOTS:
                        offenders.append(f"{rel}:{node.lineno}: import {alias.name}")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[0] in FORBIDDEN_ROOTS
            ):
                offenders.append(f"{rel}:{node.lineno}: from {node.module} import")
    # Self-verify: SRC_ROOT breakage (rglob finding nothing) must not pass vacuously.
    assert walked > 20, f"structure walk must cover the package; only {walked} files walked"
    assert not offenders, (
        "click/textual may only be imported under src/benchweave/cli/: "
        + ", ".join(offenders)
    )
