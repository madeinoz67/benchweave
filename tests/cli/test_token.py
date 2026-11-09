"""Issue #625 — the operator token command.

The arms here are the ones the design record pre-committed (§6.1 A1–A10) before any
code existed. Each outcome is binary, so N = 1 per arm; the only way an arm could be
underpowered is if it cannot fail, which is why the load-bearing ones ship a RED twin
or a positive control alongside.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from click.testing import CliRunner, Result
from fastapi import FastAPI

from benchweave.cli import atrest
from benchweave.cli.commands import _TOKEN_DEFAULT_TTL_S, cli
from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.app_entry import _LIMITS
from benchweave.interfaces.errors import OperationFailure
from benchweave.interfaces.identity import IdentityRejected, issue, validate
from benchweave.interfaces.operations import require_permission
from benchweave.state.store import Store

AUDIENCE = "stg"


@pytest.fixture(autouse=True)
def _no_process_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each arm starts with no secret in the process environment.

    The bridge is set-if-not-set, so the FIRST arm that mints leaves
    BENCHWEAVE_SECRET in os.environ and every later arm then signs with that
    earlier value while the gateway it talks to uses its own file — the exact
    bad_signature trap the command discloses on stderr when the secret came from
    the environment rather than the file (§3.3). Clearing it per arm keeps each
    arm measuring what it claims to measure.
    """
    monkeypatch.delenv("BENCHWEAVE_SECRET", raising=False)
    monkeypatch.delenv("BENCHWEAVE_ENV", raising=False)
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"


def _combined(result: Result) -> str:
    stderr = result.stderr if hasattr(result, "stderr") else ""
    return str(result.output) + str(stderr)


def _data_dir(tmp_path: Path) -> Path:
    """A real data directory, created by the shipped command."""
    data = tmp_path / "data"
    result = CliRunner().invoke(cli, ["setup", "--data-dir", str(data)])
    assert result.exit_code == 0, _combined(result)
    return data


def _token(data: Path, *args: str) -> str:
    result = CliRunner().invoke(cli, ["token", "--data-dir", str(data), *args])
    assert result.exit_code == 0, _combined(result)
    # Plain mode prints exactly the credential on stdout (the ui-login shape).
    return str(result.stdout).strip()


def _app(data: Path, secret: bytes) -> FastAPI:
    """A composed gateway on its own store, signing with THIS data dir's secret."""
    store = Store.open(str(data / "state-app.sqlite"), check_same_thread=False)
    return create_app(
        store=store,
        content=ContentStore(store),
        secret=secret,
        limits=dict(_LIMITS),
        gateway_id="token-test",
        fixtures_dir=FIXTURES,
        now_iso=lambda: "2026-11-10T00:00:00Z",
        now_epoch=lambda: int(time.time()),
        ui_enabled=True,
    )


def _boot(app: FastAPI) -> tuple[uvicorn.Server, threading.Thread, int]:
    """A real loopback server, because ui-login speaks HTTP and cannot be faked."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn did not start"
    servers = server.servers
    assert servers is not None, "uvicorn did not bind"
    return server, thread, servers[0].sockets[0].getsockname()[1]


def _stop(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=5.0)


# --- A1: the token is real (REST round trip) -----------------------------------


def test_a1_the_minted_token_authenticates_against_its_own_gateway(tmp_path: Path) -> None:
    from starlette.testclient import TestClient

    data = _data_dir(tmp_path)
    secret = atrest.read_secret(data).encode()
    token = _token(data)
    with TestClient(_app(data, secret)) as client:
        ok = client.get("/v1", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200, ok.text


def test_a1_twin_a_foreign_secret_token_is_rejected(tmp_path: Path) -> None:
    """The twin: the arm depends on the secret bridge, not on any well-formed token."""
    from starlette.testclient import TestClient

    data = _data_dir(tmp_path)
    secret = atrest.read_secret(data).encode()
    foreign = issue(
        b"a-different-secret",
        principal="operator",
        audience=AUDIENCE,
        scopes={"stg:observe"},
        expires_at=int(time.time()) + 3600,
    )
    with TestClient(_app(data, secret)) as client:
        refused = client.get("/v1", headers={"Authorization": f"Bearer {foreign}"})
    assert refused.status_code == 401, refused.text


# --- A2: the issue's operator path, end to end (UI) ---------------------------


def test_a2_token_then_ui_login_reaches_a_session(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    secret = atrest.read_secret(data).encode()
    token = _token(data)
    server, thread, port = _boot(_app(data, secret))
    try:
        result = CliRunner().invoke(
            cli,
            [
                "ui-login",
                "--gateway-url",
                f"http://127.0.0.1:{port}",
                "--token",
                token,
            ],
        )
        assert result.exit_code == 0, _combined(result)
        url = result.stdout.strip().splitlines()[-1]
        exchange = httpx.get(url, follow_redirects=False)
        assert exchange.status_code == 303, exchange.text
        assert exchange.cookies, "the exchange must set a session cookie"
    finally:
        _stop(server, thread)


# --- A3: the signing secret never printed, with a positive control ------------


def test_a3_the_secret_never_appears_in_either_output_mode(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    secret = atrest.read_secret(data)
    runner = CliRunner()
    plain = runner.invoke(cli, ["token", "--data-dir", str(data)])
    machine = runner.invoke(cli, ["token", "--data-dir", str(data), "--json"])
    assert plain.exit_code == 0 and machine.exit_code == 0
    assert secret not in _combined(plain)
    assert secret not in _combined(machine)
    payload = json.loads(machine.stdout)
    assert "secret" not in payload
    assert payload["token"]


def test_a3_control_the_detector_can_see_a_printed_secret(tmp_path: Path) -> None:
    """The positive control: the same assertion applied to setup --show-secret RAISES."""
    data = tmp_path / "control-data"
    result = CliRunner().invoke(
        cli, ["setup", "--data-dir", str(data), "--show-secret"]
    )
    assert result.exit_code == 0, _combined(result)
    secret = atrest.read_secret(data)
    assert secret in result.output, "the detector must be able to see a printed secret"


# --- A4: least privilege by default, and the widening flag is not inert -------


def test_a4_default_token_is_observe_only_and_scope_widens(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    secret = atrest.read_secret(data).encode()

    narrow = validate(secret, _token(data), audience=AUDIENCE, now=int(time.time()))
    require_permission(narrow, "observe")
    for tier in ("control", "admin"):
        with pytest.raises(OperationFailure):
            require_permission(narrow, tier)

    wider = validate(
        secret, _token(data, "--scope", "stg:control"), audience=AUDIENCE, now=int(time.time())
    )
    require_permission(wider, "control")


# --- A5: the default lifetime makes the documented path work ------------------


def test_a5_a_short_token_cannot_mint_the_default_session(tmp_path: Path) -> None:
    """The RED twin of A2: the failure is the expiry bound, so the default matters."""
    data = _data_dir(tmp_path)
    secret = atrest.read_secret(data).encode()
    short = _token(data, "--ttl-mins", "5")
    server, thread, port = _boot(_app(data, secret))
    try:
        result = CliRunner().invoke(
            cli,
            ["ui-login", "--gateway-url", f"http://127.0.0.1:{port}", "--token", short],
        )
        combined = _combined(result)
        assert result.exit_code != 0, combined
        assert "forbidden" in combined, combined
    finally:
        _stop(server, thread)


# --- A6: expiry is what the payload claims ------------------------------------


def test_a6_expiry_matches_the_payload_and_is_enforced(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    secret = atrest.read_secret(data).encode()
    before = int(time.time())
    result = CliRunner().invoke(
        cli, ["token", "--data-dir", str(data), "--ttl-mins", "1", "--json"]
    )
    assert result.exit_code == 0, _combined(result)
    payload = json.loads(result.stdout)
    assert abs(payload["expires_at"] - (before + 60)) <= 2

    token = payload["token"]
    validate(secret, token, audience=AUDIENCE, now=payload["expires_at"] - 1)
    with pytest.raises(IdentityRejected) as expired:
        validate(secret, token, audience=AUDIENCE, now=payload["expires_at"])
    assert expired.value.reason == "expired"


# --- A7: the default is pinned above the session ceiling ----------------------


def test_a7_the_default_lifetime_exceeds_the_session_ceiling() -> None:
    """A drift guard: raising the gateway ceiling without raising the default reds
    here, instead of at an operator's terminal as a 403."""
    ceiling_s = _LIMITS["ui_session_ttl_ms"] // 1000
    assert ceiling_s < _TOKEN_DEFAULT_TTL_S, (
        f"the default token lifetime ({_TOKEN_DEFAULT_TTL_S}s) must exceed the session"
        f" ceiling ({ceiling_s}s) or ui-login with no --ttl-mins refuses"
    )


# --- A8: issuance writes nothing ---------------------------------------------


def test_a8_minting_touches_no_file(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    before = sorted(p.name for p in data.iterdir())
    _token(data)
    after = sorted(p.name for p in data.iterdir())
    assert after == before, f"token wrote {set(after) - set(before)}"
    assert not [n for n in after if n.endswith(("-wal", "-shm", ".hold"))]


# --- A9: failure envelopes ----------------------------------------------------


def test_a9a_a_directory_that_is_not_a_data_dir_is_named(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = CliRunner().invoke(cli, ["token", "--data-dir", str(empty)])
    assert result.exit_code != 0
    assert "token:" in _combined(result)
    assert "not a BenchWeave data directory" in _combined(result)


@pytest.mark.skipif(
    __import__("sys").platform == "win32", reason="mode bits mean nothing on Windows"
)
def test_a9b_a_group_readable_file_is_refused(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    env = data / atrest.CREDENTIAL_FILE
    env.chmod(0o644)
    result = CliRunner().invoke(cli, ["token", "--data-dir", str(data)])
    combined = _combined(result)
    assert result.exit_code != 0
    assert "env_file:" in combined and "chmod 0600" in combined, combined


def test_a9c_an_excluded_key_is_refused(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    env = data / atrest.CREDENTIAL_FILE
    env.write_text(env.read_text() + "BENCHWEAVE_DB=x\n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["token", "--data-dir", str(data)])
    combined = _combined(result)
    assert result.exit_code != 0
    assert "env_file:" in combined and "BENCHWEAVE_DB" in combined, combined


def test_a9d_an_unknown_scope_is_refused(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    result = CliRunner().invoke(cli, ["token", "--data-dir", str(data), "--scope", "stg:root"])
    combined = _combined(result)
    assert result.exit_code != 0
    assert "unknown scope" in combined, combined


def test_a9e_a_zero_ttl_is_a_usage_error(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    result = CliRunner().invoke(cli, ["token", "--data-dir", str(data), "--ttl-mins", "0"])
    assert result.exit_code == 2, _combined(result)


def test_a9f_a_blank_process_secret_is_refused_and_unsetting_it_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The RED twin proves the refusal is about the blank value, not the fixture."""
    data = _data_dir(tmp_path)
    monkeypatch.setenv("BENCHWEAVE_SECRET", "")
    refused = CliRunner().invoke(cli, ["token", "--data-dir", str(data)])
    assert refused.exit_code != 0
    assert "env_file:" in _combined(refused)

    monkeypatch.delenv("BENCHWEAVE_SECRET", raising=False)
    allowed = CliRunner().invoke(cli, ["token", "--data-dir", str(data)])
    assert allowed.exit_code == 0, _combined(allowed)


# --- A10: no value echoed on a malformed file --------------------------------


def test_a10_a_malformed_line_never_echoes_the_secret(tmp_path: Path) -> None:
    data = _data_dir(tmp_path)
    env = data / atrest.CREDENTIAL_FILE
    secret = atrest.read_secret(data)
    # A line with no '=' — unparseable, and it carries the real secret text.
    env.write_text(env.read_text() + f"BENCHWEAVE_SECRET {secret}\n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["token", "--data-dir", str(data)])
    combined = _combined(result)
    assert result.exit_code != 0, combined
    assert "env_file:" in combined, combined
    assert secret not in combined, "a refusal must never echo the line it refuses"
