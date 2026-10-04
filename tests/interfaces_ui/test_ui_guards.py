"""The UI guard set (G2a, design §2.3 — NFR-S4–S7): the I1 ``security.py``
precedent adapted, each guard individually omittable so the acceptance
arms can prove which mechanism stops which attack.

The truth table for the trusted-host check runs against the pure
function; the end-to-end arms run against the composed sub-app with
exactly one guard disarmed (``build_ui_app(guards=...)``) — the
minus-one shape the design's §2.3 names.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from fastapi import FastAPI
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from benchweave.interfaces.operations import Operations
from benchweave.interfaces.sessions import SessionStore
from benchweave.interfaces.ui import (
    DEFAULT_GUARDS,
    BodyCapGuard,
    TrustedHostGuard,
    build_ui_app,
)

# --- the trusted-host truth table (the ported I1 logic) -------------------------


@pytest.mark.parametrize(
    ("header", "bound_host", "bound_port", "expected"),
    [
        ("127.0.0.1:8125", "127.0.0.1", 8125, True),  # exact match
        ("127.0.0.1:9999", "127.0.0.1", 8125, False),  # wrong port
        ("127.0.0.1", "127.0.0.1", 8125, False),  # no port at all
        ("localhost:8125", "127.0.0.1", 8125, True),  # localhost implies loopback bind
        ("localhost:8125", "0.0.0.0", 8125, False),  # 0.0.0.0 is not a loopback literal
        ("localhost:8125", "192.168.1.5", 8125, False),  # localhost on a non-loopback bind
        ("192.168.1.5:8125", "192.168.1.5", 8125, True),  # exact non-loopback name
        ("evil.example:8125", "127.0.0.1", 8125, False),  # a name that is not the bind
        ("[::1]:8125", "::1", 8125, True),  # bracketed IPv6 exact
        ("[::1]:8125", "127.0.0.1", 8125, False),  # IPv6 literal vs IPv4 bind
        ("[:garbage", "127.0.0.1", 8125, False),  # malformed bracket form
        ("[::1]:abc", "::1", 8125, False),  # non-numeric port
        ("10.0.0.1:8125", "127.0.0.1", 8125, False),  # another IP, not the bind
        ("127.0.0.2:8125", "127.0.0.1", 8125, False),  # loopback family but not the bind
    ],
)
def test_trusted_host_truth_table(
    header: str, bound_host: str, bound_port: int, expected: bool
) -> None:
    guard = TrustedHostGuard(
        app=_passthrough_app(), bound_host=bound_host, bound_port=bound_port
    )
    assert guard.trusted(header) is expected, header


# --- the guard behaviours end to end, each minus exactly one guard --------------


class _NullOperations:
    def __getattr__(self, name: str) -> object:
        def _unreachable(*args: object, **kwargs: object) -> object:
            raise AssertionError(f"the guard arm must not reach operations.{name}")

        return _unreachable


def _sub_app(guards: frozenset[str]) -> FastAPI:
    return build_ui_app(
        cast(Operations, _NullOperations()),
        SessionStore(now_epoch=lambda: 1_800_000_000),
        secret=b"guard-suite",
        limits={"max_json_bytes": 64},
        guards=guards,
    )


#: The trusted-host posture (I1's, kept): the Host header must carry
#: its port. A non-default TestClient base URL makes httpx keep the port
#: in the header, so the armed guard's happy path is exercisable in-process.
_CLIENT_BASE = "http://testserver:8125"


def _get(app: FastAPI, path: str, headers: dict[str, str] | None = None) -> Any:
    # The sub-app has no lifespan; a bare TestClient drives it synchronously.
    return TestClient(app, base_url=_CLIENT_BASE).get(
        path, headers=headers, follow_redirects=True
    )


def test_wrong_host_is_refused_with_the_full_guard_set() -> None:
    response = _get(_sub_app(DEFAULT_GUARDS), "/", headers={"Host": "evil.example"})
    assert response.status_code == 403
    assert "text/html" not in response.headers.get("content-type", "")


def test_minus_trusted_host_lets_the_wrong_host_through() -> None:
    """The minus-one RED control for the rebinding guard: with exactly
    ``trusted_host`` disarmed, the same wrong-Host request is answered by
    the UI itself (401 refusal page), not by the guard — proving the
    guard, not an incidental shape, is the mechanism."""
    guards = DEFAULT_GUARDS - {"trusted_host"}
    response = _get(_sub_app(guards), "/", headers={"Host": "evil.example"})
    assert response.status_code == 401
    assert "data-bw-refusal-code" in response.text


def test_oversized_body_is_preread_refused_with_the_full_guard_set() -> None:
    response = TestClient(_sub_app(DEFAULT_GUARDS), base_url=_CLIENT_BASE).post(
        "/login-codes",
        headers={"Authorization": "Bearer x", "Content-Length": "4096"},
        content=b"x" * 4096,
    )
    assert response.status_code == 413


def test_minus_body_cap_lets_the_oversized_header_through() -> None:
    guards = DEFAULT_GUARDS - {"body_cap"}
    response = TestClient(_sub_app(guards), base_url=_CLIENT_BASE).post(
        "/login-codes",
        headers={"Authorization": "Bearer x", "Content-Length": "4096"},
        content=b"x" * 4096,
    )
    # No guard refusal: the request reached the app's own handling (the
    # bearer is garbage, so the answer is the adapter's own envelope).
    assert response.status_code != 413


def test_html_carries_csp_with_the_full_guard_set() -> None:
    response = _get(_sub_app(DEFAULT_GUARDS), "/ui")
    assert "frame-ancestors 'none'" in response.headers.get(
        "content-security-policy", ""
    )


def test_minus_csp_drops_the_header() -> None:
    guards = DEFAULT_GUARDS - {"csp"}
    response = _get(_sub_app(guards), "/")
    assert "content-security-policy" not in response.headers


# --- the CSRF delivery surface (G3a, FOLD-1) ------------------------------------


def _seeded_ui_app(
    guards: frozenset[str],
) -> tuple[FastAPI, SessionStore]:
    """The sub-app over a store the arm seeds itself (the _sub_app shape,
    with the store surfaced for a mint+exchange)."""
    store = SessionStore(now_epoch=lambda: 1_800_000_000)
    app = build_ui_app(
        cast(Operations, _NullOperations()),
        store,
        secret=b"guard-suite",
        limits={"max_json_bytes": 64},
        guards=guards,
    )
    return app, store


def test_csrf_guard_refuses_a_session_post_without_the_header() -> None:
    """The guard-side truth the FOLD-1 defect hid: a session-bearing POST
    with NO x-csrf-token header is refused 403 — so a real browser
    (pre-FOLD-1) could never satisfy the guard, because nothing put the
    token on the wire. This arm pins the refusal; the served-bytes pin
    (test_ui_control_leases) pins the delivery."""
    from benchweave.interfaces.identity import Identity

    app, store = _seeded_ui_app(DEFAULT_GUARDS)
    code = store.mint_login_code(
        Identity(
            principal="ui-guard",
            audience="stg",
            scopes=frozenset({"stg:observe", "stg:control"}),
            expires_at=1_800_000_000 + 12 * 3600,
        )
    )
    record = store.exchange(code)
    response = TestClient(app, base_url=_CLIENT_BASE).post(
        "/logout",
        cookies={"bw_session": record.session_id},
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_minus_csrf_lets_the_headerless_post_through() -> None:
    """The minus-one control: with exactly the csrf guard disarmed, the
    same headerless POST reaches the app (the 303 logout) — proving the
    guard, not an incidental shape, is the mechanism."""
    from benchweave.interfaces.identity import Identity

    app, store = _seeded_ui_app(DEFAULT_GUARDS - {"csrf"})
    code = store.mint_login_code(
        Identity(
            principal="ui-guard",
            audience="stg",
            scopes=frozenset({"stg:observe", "stg:control"}),
            expires_at=1_800_000_000 + 12 * 3600,
        )
    )
    record = store.exchange(code)
    response = TestClient(app, base_url=_CLIENT_BASE).post(
        "/logout",
        cookies={"bw_session": record.session_id},
        follow_redirects=False,
    )
    assert response.status_code == 303


# --- the body-cap unit (pre-read refusal, the I1 shape) -------------------------


def _passthrough_app() -> object:
    from starlette.types import Receive, Scope, Send

    async def _app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await PlainTextResponse("ok")(scope, receive, send)

    return _app


async def _run_middleware(
    guard: BodyCapGuard, method: str, headers: dict[str, str]
) -> tuple[int, str]:
    """Drive one guard's ``dispatch`` with a synthetic request; the inner
    app answers ``inner``, the guard its own refusal."""
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse

    async def call_next(request: Request) -> PlainTextResponse:
        return PlainTextResponse("inner")

    request = Request(
        {
            "type": "http",
            "method": method,
            "path": "/x",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "http_version": "1.1",
            "root_path": "",
        }
    )
    response = await guard.dispatch(request, call_next)
    return response.status_code, bytes(response.body).decode()


def test_body_cap_unit_preread_refuses_oversized_state_changing() -> None:
    guard = BodyCapGuard(app=_passthrough_app(), limit=100)
    status, body = asyncio.run(_run_middleware(guard, "POST", {"content-length": "4096"}))
    assert status == 413
    assert body != "inner"  # the inner app never ran


def test_body_cap_unit_passes_reads_and_small_bodies() -> None:
    guard = BodyCapGuard(app=_passthrough_app(), limit=100)
    for method, headers in (("GET", {}), ("POST", {"content-length": "10"})):
        status, body = asyncio.run(_run_middleware(guard, method, headers))
        assert (status, body) == (200, "inner"), method


def test_body_cap_unit_passes_chunked_bodies_without_content_length() -> None:
    """The disclosed residual (the I1 posture): a chunked body sent
    without Content-Length is not pre-refused HERE — the routes' own
    ceiling check reads it. The guard states what it does not catch."""
    guard = BodyCapGuard(app=_passthrough_app(), limit=100)
    status, body = asyncio.run(_run_middleware(guard, "POST", {}))
    assert (status, body) == (200, "inner")
