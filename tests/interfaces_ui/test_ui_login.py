"""The login-link flow over HTTP (G2a, design §2.2 / §7-B, GW-90–94).

Mint (Bearer-authenticated) → exchange (single-use code → 303 + cookie)
→ logout (CSRF-checked). The refusal matrix's HTTP arms: replay, expiry
(injected clock), unknown, narrowing refusals, logout death, restart
death. The log-exposure arm boots a real uvicorn with the serving log
config and asserts the code string appears in NO captured log line —
access log included (R2's kill condition).

I02's G2a half: identity comes from the Authorization header and the
server-side session ONLY — posted principal/identity data is ignored at
every /ui route (the cross-bench half joins with G2b's read routes).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from ui_gateway_support import (
    FIXTURES,
    LIMITS,
    NOW_EPOCH,
    SECRET,
    boot,
    mint_and_exchange,
    module_gateway,
    stop,
    ui_token,
)

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.ui import SESSION_COOKIE
from benchweave.state.store import Store


@pytest.fixture(scope="module")
def login_gateway(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    app = module_gateway("ui-login", tmp_path_factory.mktemp("ui-login"))
    server, thread, port = boot(app)
    yield SimpleNamespace(app=app, base=f"http://127.0.0.1:{port}", port=port)
    stop(server, thread)


class _Clock:
    """A mutable epoch clock for the expiry arms."""

    def __init__(self) -> None:
        self.now = NOW_EPOCH

    def __call__(self) -> int:
        return self.now


@pytest.fixture()
def clocked_app(tmp_path: Path) -> tuple[FastAPI, _Clock]:
    """A composed app on a mutable clock (its own store, the hold rule)."""
    clock = _Clock()
    store = Store.open(str(tmp_path / "clocked.sqlite"), check_same_thread=False)
    app = create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id="ui-clocked",
        fixtures_dir=FIXTURES,
        now_iso=lambda: "2026-10-03T00:00:00Z",
        now_epoch=clock,
    )
    return app, clock


# --- the mint --------------------------------------------------------------------


def test_mint_returns_a_login_url_and_nothing_else(login_gateway: SimpleNamespace) -> None:
    response = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {ui_token()}"},
        json={},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    login_url = body["data"]["login_url"]
    assert re.search(r"/ui/login\?code=[A-Za-z0-9_-]{20,}$", login_url), login_url
    # The mint hands the OPERATOR a URL; no session material, no token,
    # no scope rides the response.
    assert set(body["data"]) == {"login_url"}


@pytest.mark.parametrize(
    ("header", "status"),
    [
        ({}, 401),  # no Authorization at all
        ({"Authorization": "Basic zzz"}, 401),  # wrong scheme
        ({"Authorization": "Bearer not-a-token"}, 401),  # malformed
        ({"Authorization": "Bearer " + ui_token(expires_at=NOW_EPOCH - 1)}, 401),  # expired
        (
            {"Authorization": "Bearer " + ui_token(audience="gateway-admin")},
            403,
        ),  # wrong audience -> forbidden (the rest.py map)
    ],
)
def test_mint_authentication_failures(
    login_gateway: SimpleNamespace, header: dict[str, str], status: int
) -> None:
    response = httpx.post(
        f"{login_gateway.base}/ui/login-codes", headers=header, json={}
    )
    assert response.status_code == status
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == (
        "unauthenticated" if status == 401 else "forbidden"
    )


def test_mint_narrowing_refusals(login_gateway: SimpleNamespace) -> None:
    """NFR-S2's HTTP shape: widening is REFUSED, never clamped."""
    # A scope the caller does not hold.
    response = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {ui_token(scopes={'stg:observe'})}"},
        json={"scopes": ["stg:admin"]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    # An expiry past the caller token's own.
    response = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {ui_token(expires_at=NOW_EPOCH + 600)}"},
        json={"ttl_seconds": 3600},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    # A service-limit violation (over the configured session ceiling).
    response = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {ui_token()}"},
        json={"ttl_seconds": LIMITS["ui_session_ttl_ms"] // 1000 + 1},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_mint_ignores_posted_identity_data(login_gateway: SimpleNamespace) -> None:
    """I02's mint arm: the body cannot inject identity — principal,
    audience and expiry come from the validated token only."""
    response = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {ui_token(principal='real-principal')}"},
        json={
            "principal": "attacker",
            "audience": "gateway-admin",
            "scopes": ["stg:observe"],
            "expires_at": NOW_EPOCH + 999999,
        },
    )
    assert response.status_code == 201
    exchanged = httpx.get(
        response.json()["data"]["login_url"], follow_redirects=False
    )
    assert exchanged.status_code == 303
    with httpx.Client(base_url=login_gateway.base) as client:
        page = client.get(
            "/ui/", cookies={SESSION_COOKIE: exchanged.cookies[SESSION_COOKIE]}
        )
    assert 'data-bw-principal="real-principal"' in page.text
    assert "attacker" not in page.text


# --- the exchange ------------------------------------------------------------------


def test_exchange_redirects_to_a_clean_url_with_the_cookie(
    login_gateway: SimpleNamespace,
) -> None:
    minted = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {ui_token(principal='exchanger')}"},
        json={},
    )
    code = minted.json()["data"]["login_url"].split("code=")[-1]
    response = httpx.get(f"{login_gateway.base}/ui/login?code={code}")
    # GW-92: 303 to a clean URL — no code, no session material on the path.
    assert response.status_code == 303
    assert "code=" not in response.headers["location"]
    assert response.headers["location"].startswith("/ui")
    # The cookie: all four posture attributes; opaque value.
    raw = response.headers["set-cookie"]
    assert "HttpOnly" in raw
    assert "SameSite=strict" in raw or "SameStrict" in raw
    assert "Path=/ui" in raw
    assert "Secure" not in raw  # plain http serving (loopback posture)
    cookie = response.cookies[SESSION_COOKIE]
    assert re.fullmatch(r"[A-Za-z0-9_-]{40,}", cookie)
    # And the cookie works: the shell renders the session.
    page = httpx.get(
        f"{login_gateway.base}/ui/", cookies={SESSION_COOKIE: cookie},
        follow_redirects=True,
    )
    assert page.status_code == 200
    assert 'data-bw-principal="exchanger"' in page.text


def test_exchange_renders_unauthenticated_on_unknown_code(
    login_gateway: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="benchweave.interfaces.ui"):
        response = httpx.get(f"{login_gateway.base}/ui/login?code=not-a-code")
    assert response.status_code == 401
    assert 'data-bw-refusal-code="unauthenticated"' in response.text
    # The log line names the refusal class, never the code itself.
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert "unknown" in joined
    assert "not-a-code" not in joined


def test_exchange_replay_is_refused_and_logged(
    login_gateway: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    minted = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {ui_token()}"},
        json={},
    )
    code = minted.json()["data"]["login_url"].split("code=")[-1]
    first = httpx.get(f"{login_gateway.base}/ui/login?code={code}")
    assert first.status_code == 303
    with caplog.at_level(logging.INFO, logger="benchweave.interfaces.ui"):
        replay = httpx.get(f"{login_gateway.base}/ui/login?code={code}")
    assert replay.status_code == 401
    assert 'data-bw-refusal-code="unauthenticated"' in replay.text
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert "used" in joined
    assert code not in joined


def test_exchange_expiry_on_the_injected_clock(
    clocked_app: tuple[FastAPI, _Clock],
) -> None:
    app, clock = clocked_app
    from starlette.testclient import TestClient

    with TestClient(app, base_url="http://testserver:8125") as client:
        minted = client.post(
            "/ui/login-codes",
            headers={"Authorization": f"Bearer {ui_token()}"},
            json={},
        )
        code = minted.json()["data"]["login_url"].split("code=")[-1]
        clock.now = NOW_EPOCH + LIMITS["ui_login_code_ttl_ms"] // 1000
        expired = client.get(f"/ui/login?code={code}")
    assert expired.status_code == 401
    assert 'data-bw-refusal-code="unauthenticated"' in expired.text


# --- logout and restart --------------------------------------------------------------


def _csrf_for(app: FastAPI, cookie: str) -> str:
    from benchweave.interfaces.sessions import SessionRecord

    record: SessionRecord | None = app.state.ui_sessions.resolve(cookie)
    assert record is not None
    return record.csrf_token


def test_logout_kills_the_cookie_and_requires_csrf(
    login_gateway: SimpleNamespace,
) -> None:
    token = ui_token(principal="logout-probe")
    minted = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    code = minted.json()["data"]["login_url"].split("code=")[-1]
    exchanged = httpx.get(f"{login_gateway.base}/ui/login?code={code}")
    cookie = exchanged.cookies[SESSION_COOKIE]

    # Without the CSRF token: the guard refuses (NFR-S4).
    refused = httpx.post(
        f"{login_gateway.base}/ui/logout", cookies={SESSION_COOKIE: cookie}
    )
    assert refused.status_code == 403
    # With the wrong token: refused too.
    wrong = httpx.post(
        f"{login_gateway.base}/ui/logout",
        cookies={SESSION_COOKIE: cookie},
        headers={"x-csrf-token": "guessed"},
    )
    assert wrong.status_code == 403
    # Cross-origin Origin with a valid token: refused.
    leaked = httpx.post(
        f"{login_gateway.base}/ui/logout",
        cookies={SESSION_COOKIE: cookie},
        headers={
            "x-csrf-token": _csrf_for(login_gateway.app, cookie),
            "Origin": "https://elsewhere.example",
        },
    )
    assert leaked.status_code == 403

    # The session is still alive after those refusals.
    alive = httpx.get(
        f"{login_gateway.base}/ui/", cookies={SESSION_COOKIE: cookie}
    )
    assert 'data-bw-principal="logout-probe"' in alive.text

    # The real logout: server-side deletion, cookie dead from this moment.
    gone = httpx.post(
        f"{login_gateway.base}/ui/logout",
        cookies={SESSION_COOKIE: cookie},
        headers={"x-csrf-token": _csrf_for(login_gateway.app, cookie)},
    )
    assert gone.status_code == 303
    replay = httpx.get(
        f"{login_gateway.base}/ui/", cookies={SESSION_COOKIE: cookie}
    )
    assert replay.status_code == 401


def test_a_rebuilt_gateway_invalidates_every_cookie(tmp_path: Path) -> None:
    """GW-94: a restart (new store) has no knowledge of prior sessions."""
    from starlette.testclient import TestClient

    app = module_gateway("ui-restart-first", tmp_path)
    result = mint_and_exchange(app, ui_token(principal="restart-probe"))
    cookie = result.cookie
    assert cookie, "the exchange set no cookie"
    rebuilt = module_gateway("ui-restart-second", tmp_path)
    response = TestClient(rebuilt, base_url="http://testserver:8125").get(
        "/ui/", headers={"Cookie": f"{SESSION_COOKIE}={cookie}"}
    )
    assert response.status_code == 401


# --- the log-exposure arm (§7-B / R2): the code never reaches a log line -------------


def test_the_login_code_never_reaches_a_log_line(
    tmp_path: Path,
) -> None:
    """Boot the REAL serving posture (uvicorn with the access-log config
    the ``serve`` command installs), drive a full mint + exchange, and
    assert the code string appears in NO captured log line — access log
    included. Any hit is the design's kill condition."""
    from benchweave.interfaces.ui import build_serving_log_config

    app = module_gateway("ui-logs", tmp_path)
    log_config = build_serving_log_config()
    import threading
    import time

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_config=log_config)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    from benchweave.interfaces.ui import _redacting_access_formatter

    try:
        # Prove the serving config INSTALLED the redacting formatter: the
        # access logger's own handler formats a synthetic /ui/login record
        # to the redacted line (a default AccessFormatter keeps the code).
        access_logger = logging.getLogger("uvicorn.access")
        installed = [h for h in access_logger.handlers if h.formatter is not None]
        assert installed, "the serving config installed no access handler"
        probe = logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            1,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:0", "GET", "/ui/login?code=PROBE", "1.1", 303),
            None,
        )
        formatter_probe = installed[0].formatter
        assert formatter_probe is not None
        rendered = formatter_probe.format(probe)
        assert "PROBE" not in rendered and "code=[redacted]" in rendered, rendered

        # End to end: FORMATTED lines (what any log sink reads), asserted
        # free of the code.
        formatter = _redacting_access_formatter(
            fmt='%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            use_colors=False,
        )
        lines: list[str] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    lines.append(self.format(record))
                except Exception:  # pragma: no cover - formatting failure
                    lines.append(record.getMessage())

        handler = _Capture()
        handler.setFormatter(formatter)
        access_logger.addHandler(handler)
        minted = httpx.post(
            f"http://127.0.0.1:{port}/ui/login-codes",
            headers={"Authorization": f"Bearer {ui_token()}"},
            json={},
        )
        assert minted.status_code == 201
        code = minted.json()["data"]["login_url"].split("code=")[-1]
        exchanged = httpx.get(f"http://127.0.0.1:{port}/ui/login?code={code}")
        assert exchanged.status_code == 303
        assert lines, "no log lines captured — the arm proves nothing"
        for line in lines:
            assert code not in line, f"the login code leaked into a log line: {line}"
        # The access log DID record the exchange request — redacted.
        access = [line for line in lines if "/ui/login" in line]
        assert access, "the access log never recorded the exchange request"
        assert all("code=[redacted]" in line for line in access), access
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


def test_the_code_is_redacted_at_the_record_level(tmp_path: Path) -> None:
    """FOLD-2 (refute lane-1 F2): redaction is RECORD-scoped, not
    formatter-scoped — a PLAIN handler with no formatter, attached to
    uvicorn.access under the serving config, must never render the code
    (the lane's exact repro: a non-default sink re-leaks otherwise)."""
    import threading
    import time

    import uvicorn
    from ui_gateway_support import module_gateway

    from benchweave.interfaces.ui import build_serving_log_config

    app = module_gateway("ui-logs-record", tmp_path)
    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_config=build_serving_log_config()
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    captured: list[logging.LogRecord] = []

    class _Plain(logging.Handler):
        """No formatter, no redaction of its own: exactly the shape of an
        arbitrary third-party sink."""

        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _Plain()
    logging.getLogger("uvicorn.access").addHandler(handler)
    try:
        minted = httpx.post(
            f"http://127.0.0.1:{port}/ui/login-codes",
            headers={"Authorization": f"Bearer {ui_token()}"},
            json={},
        )
        assert minted.status_code == 201
        code = minted.json()["data"]["login_url"].split("code=")[-1]
        exchanged = httpx.get(f"http://127.0.0.1:{port}/ui/login?code={code}")
        assert exchanged.status_code == 303
        assert captured, "no access records captured — the arm proves nothing"
        for record in captured:
            rendered = record.getMessage()
            assert code not in rendered, (
                f"a plain sink rendered the login code: {rendered}"
            )
        access = [r.getMessage() for r in captured if "/ui/login" in r.getMessage()]
        assert access, "the exchange request never reached the access logger"
        assert all("code=[redacted]" in line for line in access), access
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


def test_a_session_bearing_mint_post_is_csrf_refused(
    login_gateway: SimpleNamespace,
) -> None:
    """Fold G4: the mint is Bearer-only BY DESIGN, so it holds no
    browser-rideable credential — and the CSRF guard no longer exempts
    it. A request carrying a SESSION cookie is treated like any other
    state-changing /ui request: the per-session CSRF token is required,
    fail-closed, even alongside a valid Bearer token."""
    token = ui_token(principal="mint-csrf-probe")
    minted = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    code = minted.json()["data"]["login_url"].split("code=")[-1]
    exchanged = httpx.get(f"{login_gateway.base}/ui/login?code={code}")
    cookie = exchanged.cookies[SESSION_COOKIE]

    refused = httpx.post(
        f"{login_gateway.base}/ui/login-codes",
        headers={"Authorization": f"Bearer {token}"},
        cookies={SESSION_COOKIE: cookie},
        json={},
    )
    assert refused.status_code == 403
    assert "csrf" in refused.text
