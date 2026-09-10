"""WP02 baseline: local identity issuer + live MCP 2026-07-28 loopback exchange.

Proves the two risk-gate properties before any adapter freeze: (1) a local
test issuer rejects wrong-audience, expired, under-scoped and malformed
credentials with machine-matchable reasons, and (2) an exact initialize ->
tools/list -> tools/call exchange works over real HTTP against the vendored
contract corpus, gated by those credentials.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from benchweave.interfaces.identity import IdentityRejected, issue, validate

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_TOOLS = ROOT / "contracts" / "interface-v1.1.0" / "mcp-tools.json"
SECRET = b"wp02-test-secret-not-a-credential"
AUDIENCE = "benchweave-gateway"
INVOKE_SCOPE = "tools:invoke"
NOW = 2_000_000_000


def _token(**overrides: Any) -> str:
    params: dict[str, Any] = {
        "principal": "engineer-a",
        "audience": AUDIENCE,
        "scopes": [INVOKE_SCOPE],
        "expires_at": NOW + 600,
    }
    params.update(overrides)
    return issue(SECRET, **params)


# --- Identity issuer --------------------------------------------------------


def test_issue_and_validate_roundtrip() -> None:
    identity = validate(
        SECRET, _token(), audience=AUDIENCE, required_scopes=[INVOKE_SCOPE], now=NOW
    )
    assert identity.principal == "engineer-a"
    assert identity.audience == AUDIENCE
    assert identity.scopes == frozenset({INVOKE_SCOPE})
    assert identity.expires_at == NOW + 600


def test_wrong_audience_rejected() -> None:
    with pytest.raises(IdentityRejected, match="wrong_audience"):
        validate(SECRET, _token(audience="other-gateway"), audience=AUDIENCE, now=NOW)


def test_expired_rejected() -> None:
    with pytest.raises(IdentityRejected, match="expired"):
        validate(SECRET, _token(expires_at=NOW - 1), audience=AUDIENCE, now=NOW)


def test_insufficient_scope_rejected() -> None:
    with pytest.raises(IdentityRejected, match="insufficient_scope"):
        validate(
            SECRET, _token(scopes=[]), audience=AUDIENCE, required_scopes=[INVOKE_SCOPE], now=NOW
        )


def test_malformed_token_rejected() -> None:
    with pytest.raises(IdentityRejected, match="malformed_token"):
        validate(SECRET, "not-a-token", audience=AUDIENCE, now=NOW)


def test_bad_signature_rejected() -> None:
    genuine = _token()
    payload, signature = genuine.split(".", 1)
    forged = payload + "." + ("A" * len(signature))
    with pytest.raises(IdentityRejected, match="bad_signature"):
        validate(SECRET, forged, audience=AUDIENCE, now=NOW)


def test_secrets_are_keyed() -> None:
    with pytest.raises(IdentityRejected, match="bad_signature"):
        validate(b"different-secret", _token(), audience=AUDIENCE, now=NOW)


# --- Live MCP 2026-07-28 loopback exchange ----------------------------------


class _GatewayHandler(BaseHTTPRequestHandler):
    server_version = "BenchWeaveWP02Spike/0.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self._respond(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        message = json.loads(self.rfile.read(length).decode("utf-8"))
        method = message.get("method", "")

        if method != "initialize" and not self._authorise():
            return

        if method == "initialize":
            self._respond(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {
                        "protocolVersion": "2026-07-28",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "benchweave-spike", "version": "0.1.0"},
                    },
                },
                extra_headers={"Mcp-Session-Id": self.server.session_id},  # type: ignore[attr-defined]
            )
        elif method == "notifications/initialized":
            self._respond(202, None)
        elif method == "tools/list":
            tools = json.loads(CONTRACT_TOOLS.read_text(encoding="utf-8"))["tools"]
            self._respond(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {"tools": [{"name": t["name"]} for t in tools]},
                },
            )
        elif method == "tools/call":
            self._respond(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {"content": [{"type": "text", "text": "gateway:ok"}]},
                },
            )
        else:
            self._respond(404, {"error": "unknown_method"})

    def _authorise(self) -> bool:
        header = self.headers.get("Authorization", "")
        match = re.fullmatch(r"Bearer (\S+)", header)
        if match is None:
            self._respond(401, {"error": "malformed_token"})
            return False
        try:
            validate(
                SECRET,
                match.group(1),
                audience=AUDIENCE,
                required_scopes=[INVOKE_SCOPE],
                now=NOW,
            )
        except IdentityRejected as rejection:
            status = 403 if str(rejection) in ("wrong_audience", "insufficient_scope") else 401
            self._respond(status, {"error": str(rejection)})
            return False
        return True

    def _respond(self, status: int, body: Any, extra_headers: dict[str, str] | None = None) -> None:
        payload = b"" if body is None else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if payload:
            self.wfile.write(payload)


class _LoopbackServer:
    def __init__(self) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _GatewayHandler)
        self.httpd.session_id = "wp02-session-1"  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}/mcp"

    def post(
        self,
        body: dict[str, Any],
        token: str | None = None,
        session: str | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        if token is not None:
            request.add_header("Authorization", f"Bearer {token}")
        if session is not None:
            request.add_header("Mcp-Session-Id", session)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                raw = response.read().decode("utf-8")
                headers = {k.lower(): v for k, v in response.headers.items()}
                return response.status, headers, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8")
            return error.code, {}, json.loads(raw) if raw else None

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


@pytest.fixture(scope="module")
def server() -> Any:
    loopback = _LoopbackServer()
    yield loopback
    loopback.close()


def _initialize(server: _LoopbackServer) -> tuple[int, dict[str, str], Any]:
    return server.post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2026-07-28",
                "capabilities": {},
                "clientInfo": {"name": "wp02-spike-client", "version": "0.1.0"},
            },
        }
    )


def test_initialize_negotiates_protocol_and_session(server: _LoopbackServer) -> None:
    status, headers, body = _initialize(server)
    assert status == 200
    assert body["result"]["protocolVersion"] == "2026-07-28"
    assert headers["mcp-session-id"] == "wp02-session-1"


def test_tools_list_returns_all_seventeen_contract_tools(server: _LoopbackServer) -> None:
    status, _, body = server.post(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        token=_token(),
        session="wp02-session-1",
    )
    assert status == 200
    names = [tool["name"] for tool in body["result"]["tools"]]
    assert len(names) == 17
    assert names[0] == "stg_v1_gateway_info"


def test_tools_call_succeeds_with_valid_scoped_token(server: _LoopbackServer) -> None:
    status, _, body = server.post(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "stg_v1_gateway_info", "arguments": {}},
        },
        token=_token(),
        session="wp02-session-1",
    )
    assert status == 200
    assert body["result"]["content"][0]["text"] == "gateway:ok"


def test_wrong_audience_gets_403(server: _LoopbackServer) -> None:
    status, _, body = server.post(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        token=_token(audience="other-gateway"),
    )
    assert status == 403
    assert body["error"] == "wrong_audience"


def test_expired_gets_401(server: _LoopbackServer) -> None:
    status, _, body = server.post(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/list"},
        token=_token(expires_at=NOW - 1),
    )
    assert status == 401
    assert body["error"] == "expired"


def test_missing_scope_gets_403(server: _LoopbackServer) -> None:
    status, _, body = server.post(
        {"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
        token=_token(scopes=[]),
    )
    assert status == 403
    assert body["error"] == "insufficient_scope"


def test_malformed_gets_401(server: _LoopbackServer) -> None:
    status, _, body = server.post(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
        token="not-a-token",
    )
    assert status == 401
    assert body["error"] == "malformed_token"
