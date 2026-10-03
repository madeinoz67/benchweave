"""Shared helpers for the G2a UI suites (unique module name on purpose —
the integration conftest's sys.path-insertion precedent).

One real composed gateway per suite via ``boot`` (the parity suite's
pattern: a real uvicorn thread on an ephemeral loopback port,
lifespan-run, so startup admission and the trusted-host guard's socket
judgement are real). Clocks frozen: session expiry and code TTL behave
deterministically.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from fastapi import FastAPI

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import Identity, issue
from benchweave.interfaces.sessions import SessionRecord, SessionStore
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
SECRET = b"g2a-ui-suite-secret"
NOW_ISO = "2026-10-03T00:00:00Z"
NOW_EPOCH = 1_800_000_000
#: The parity suite's limits table plus the three UI session knobs.
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
    "ui_login_code_ttl_ms": 60000,
    "ui_session_ttl_ms": 28800000,
    "ui_max_bridges_per_session": 4,
}


def ui_token(
    principal: str = "ui-operator",
    scopes: set[str] | None = None,
    *,
    audience: str = "stg",
    expires_at: int = NOW_EPOCH + 12 * 3600,
) -> str:
    """A local-issuer bearer token for the mint path (identity.py shape)."""
    return issue(
        SECRET,
        principal=principal,
        audience=audience,
        scopes=scopes if scopes is not None else {"stg:observe", "stg:control"},
        expires_at=expires_at,
    )


def build_ui_gateway(
    data_dir: Path, *, ui_enabled: bool = True, name: str = "app"
) -> FastAPI:
    """A composed app on its OWN store (the hold rule: never share a DB
    between two composed apps — every call opens a fresh database file)."""
    store = Store.open(str(data_dir / f"state-{name}.sqlite"), check_same_thread=False)
    return create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id="ui-test",
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
        ui_enabled=ui_enabled,
    )


def boot(app: FastAPI) -> tuple[uvicorn.Server, threading.Thread, int]:
    """The parity suite's loopback boot: real port, lifespan-run."""
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


def stop(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=5.0)


def mint_and_exchange(app: FastAPI, token: str) -> SimpleNamespace:
    """Drive the HTTP mint + exchange once (G2a's login suite); returns
    the login URL, the extracted code, the exchange response and the
    session cookie value it set."""
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        minted = client.post(
            "/ui/login-codes", headers={"Authorization": f"Bearer {token}"}, json={}
        )
        assert minted.status_code == 201, minted.text
        login_url = minted.json()["data"]["login_url"]
        code = login_url.split("code=")[-1]
        exchanged = client.get(f"/ui/login?code={code}", follow_redirects=False)
    cookie = exchanged.cookies.get("bw_session")
    return SimpleNamespace(
        login_url=login_url, code=code, response=exchanged, cookie=cookie or ""
    )


def module_gateway(gateway_id: str, data_dir: Path) -> FastAPI:
    """The module-gateway app factory (the parity suite's shape: real
    store, bootstrap admission, frozen clocks)."""
    store = Store.open(
        str(data_dir / f"state-{gateway_id}.sqlite"), check_same_thread=False
    )
    return create_app(
        store=store,
        content=ContentStore(store),
        secret=SECRET,
        limits=dict(LIMITS),
        gateway_id=gateway_id,
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )


def live_session(app: FastAPI, *, principal: str = "ui-shell") -> SessionRecord:
    """A live browser session via the server-side store (store-level mint
    + exchange — the HTTP mint path carries its own suite)."""
    store: SessionStore = app.state.ui_sessions
    code = store.mint_login_code(
        Identity(
            principal=principal,
            audience="stg",
            scopes=frozenset({"stg:observe"}),
            expires_at=NOW_EPOCH + 12 * 3600,
        )
    )
    record = store.exchange(code)
    assert isinstance(record, SessionRecord)
    return record
