"""The ``benchweave ui-login`` command (G2a, design §2.2 step 4; GW-90).

The Q1 mint surface for operators: an authenticated CLI that prints the
login URL. Plus the env-surface knobs (``app_entry``): the three session
limits parse fail-loud, and ``BENCHWEAVE_UI`` (default ON, per the
maintainer's F2 call) disables the UI at composition.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from click.testing import CliRunner, Result

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interfaces_ui"))
from ui_gateway_support import SECRET, boot, module_gateway, stop, ui_token

from benchweave.cli.commands import cli


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    app = module_gateway("cli-ui-login", tmp_path_factory.mktemp("cli-ui"))
    server, thread, port = boot(app)
    yield SimpleNamespace(app=app, base=f"http://127.0.0.1:{port}", port=port)
    stop(server, thread)


def _run(args: list[str]) -> Result:
    return CliRunner().invoke(cli, args)


def test_ui_login_prints_a_working_login_url(gateway: SimpleNamespace) -> None:
    result = _run(
        [
            "ui-login",
            "--gateway-url",
            gateway.base,
            "--token",
            ui_token(principal="cli-operator"),
        ]
    )
    assert result.exit_code == 0, result.output
    url = result.output.strip().splitlines()[-1]
    assert "/ui/login?code=" in url
    # The printed URL is REAL: exchanging it mints the session.
    exchanged = httpx.get(url, follow_redirects=False)
    assert exchanged.status_code == 303
    assert "code=" not in exchanged.headers["location"]


def test_ui_login_scope_narrowing_and_ttl(gateway: SimpleNamespace) -> None:
    result = _run(
        [
            "ui-login",
            "--gateway-url",
            gateway.base,
            "--token",
            ui_token(principal="cli-narrow"),
            "--scope",
            "stg:observe",
            "--ttl-mins",
            "10",
        ]
    )
    assert result.exit_code == 0, result.output
    url = result.output.strip().splitlines()[-1]
    exchanged = httpx.get(url, follow_redirects=False)
    assert exchanged.status_code == 303
    cookie = exchanged.cookies["bw_session"]
    record = gateway.app.state.ui_sessions.resolve(cookie)
    assert record is not None
    assert record.scopes == frozenset({"stg:observe"})
    assert record.expires_at == 1_800_000_000 + 600  # the frozen clock + 10 min


def test_ui_login_refused_token_exits_nonzero(gateway: SimpleNamespace) -> None:
    result = _run(
        [
            "ui-login",
            "--gateway-url",
            gateway.base,
            "--token",
            "garbage-token",
        ]
    )
    assert result.exit_code != 0
    assert "unauthenticated" in result.output


def test_ui_login_widening_scope_is_refused(gateway: SimpleNamespace) -> None:
    result = _run(
        [
            "ui-login",
            "--gateway-url",
            gateway.base,
            "--token",
            ui_token(scopes={"stg:observe"}),
            "--scope",
            "stg:admin",
        ]
    )
    assert result.exit_code != 0
    assert "forbidden" in result.output


# --- the env surface (app_entry) ------------------------------------------------


def test_limits_table_carries_the_session_knobs() -> None:
    from benchweave.interfaces import app_entry

    for key in (
        "ui_login_code_ttl_ms",
        "ui_session_ttl_ms",
        "ui_max_bridges_per_session",
    ):
        assert key in app_entry._LIMITS, key
    assert app_entry._LIMITS["ui_login_code_ttl_ms"] == 60000
    assert app_entry._LIMITS["ui_session_ttl_ms"] == 28800000
    assert app_entry._LIMITS["ui_max_bridges_per_session"] == 4


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", 1),
        ("90000", 90000),
    ],
)
def test_session_knob_env_overrides_parse(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: int
) -> None:
    from benchweave.interfaces import app_entry

    monkeypatch.setenv("BENCHWEAVE_UI_LOGIN_CODE_TTL_MS", raw)
    limits = app_entry._limits_from_env()
    assert limits["ui_login_code_ttl_ms"] == expected


@pytest.mark.parametrize("raw", ["banana", "0", "-5"])
def test_a_bad_session_knob_refuses_boot(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """Non-integers and sub-1 values both refuse boot — the quota-keys'
    fail-loud rule, applied to the session knobs (a 0 ms TTL is a typo,
    not a configuration)."""
    from benchweave.interfaces import app_entry

    monkeypatch.setenv("BENCHWEAVE_UI_SESSION_TTL_MS", raw)
    with pytest.raises(RuntimeError, match="BENCHWEAVE_UI_SESSION_TTL_MS"):
        app_entry._limits_from_env()


@pytest.mark.parametrize(
    ("raw", "enabled"),
    [
        ("1", True),
        ("true", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("off", False),
    ],
)
def test_benchweave_ui_flag_parses(
    monkeypatch: pytest.MonkeyPatch, raw: str, enabled: bool
) -> None:
    """F2 (maintainer decision, design §12): the default is ON — the flag
    exists to disable."""
    from benchweave.interfaces import app_entry

    monkeypatch.setenv("BENCHWEAVE_UI", raw)
    assert app_entry._ui_enabled_from_env() is enabled


def test_benchweave_ui_flag_default_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from benchweave.interfaces import app_entry

    monkeypatch.delenv("BENCHWEAVE_UI", raising=False)
    assert app_entry._ui_enabled_from_env() is True


def test_a_garbage_ui_flag_refuses_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    from benchweave.interfaces import app_entry

    monkeypatch.setenv("BENCHWEAVE_UI", "maybe")
    with pytest.raises(RuntimeError, match="BENCHWEAVE_UI"):
        app_entry._ui_enabled_from_env()


def test_disabled_flag_composes_without_the_ui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag reaches composition: BENCHWEAVE_UI=0 boots an app with no
    /ui surface at all (absent, not stubbed)."""
    from benchweave.interfaces import app_entry

    monkeypatch.setenv("BENCHWEAVE_DB", str(tmp_path / "flag.sqlite"))
    monkeypatch.setenv("BENCHWEAVE_UI", "0")
    monkeypatch.setenv(
        "BENCHWEAVE_FIXTURES",
        str(Path(__file__).parents[2] / "fixtures" / "execution"),
    )
    monkeypatch.setattr(app_entry, "_DEFAULT_SECRET", SECRET)
    app = app_entry.build()
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any(path.startswith("/ui") for path in paths), sorted(paths)
    assert not hasattr(app.state, "ui_sessions")
