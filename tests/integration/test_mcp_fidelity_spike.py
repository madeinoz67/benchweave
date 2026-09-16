"""FastMCP schema-fidelity spike (WP07 Task 1, amended 2026-09-12).

Original spike verdict: signature-derived deep-equality with the vendored
corpus is UNREACHABLE in fastmcp 4.0.3 — pydantic never emits an empty
``required``, ``compress_schema`` unconditionally prunes the corpus's
unreferenced ``$defs``, and ``@mcp.tool`` has no input-schema parameter.

AMENDED mechanism (proven here): ``Tool.to_mcp_tool`` serves
``overrides.get("inputSchema", self.parameters)`` — the ``parameters`` field
IS the SDK's explicit-schema route — so each tool is pinned to the VENDORED
inputSchema verbatim; the signature remains only the callable. The spike
pins gateway_info exactly (including ``required: []`` and the 10-entry
``$defs``) and proves the live loopback path.

Handshake (SDK-honest, per mcp_types.version): ``initialize`` counter-offers
at most LATEST_HANDSHAKE_VERSION (2025-11-25) in this SDK generation; the
interface/0.1.0 contract's 2026-07-28 pin is spoken via the modern
``server/discover`` path (``supportedVersions`` offers 2026-07-28). On the
wire, serve-time dereference middleware prunes the corpus's unreferenced
``$defs`` from tools/list (pinned below: wire schema == vendored minus
``$defs``, everything else identical) — the fact Task 8's parity pin must
account for.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from mcp_types.version import LATEST_HANDSHAKE_VERSION

vendored: dict[str, Any] = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "standards"
        / "interface/0.1.0"
        / "mcp-tools.json"
    ).read_text(encoding="utf-8")
)


def _vendored_tool(name: str) -> dict[str, Any]:
    raw: Any = (
        vendored["tools"] if isinstance(vendored, dict) and "tools" in vendored else vendored
    )
    tools: list[dict[str, Any]] = raw
    for tool in tools:
        if tool["name"] == name:
            return tool
    raise KeyError(name)


def test_vendored_gateway_info_schema_is_available() -> None:
    tool = _vendored_tool("stg_v1_gateway_info")
    assert tool["inputSchema"]["properties"] == {}
    assert tool["inputSchema"]["required"] == []


def test_override_pinned_schema_deep_equals_vendored() -> None:
    import asyncio

    from fastmcp import FastMCP

    mcp = FastMCP(name="fidelity-spike")

    @mcp.tool(name="stg_v1_gateway_info", description="Gateway information.")
    def gateway_info() -> dict[str, object]:
        """Spike tool: empty-input gateway info."""
        return {"ok": True, "data": {}}

    vend = _vendored_tool("stg_v1_gateway_info")
    # Override wiring (fastmcp 4.0.3): `_tool_manager` is gone; the public
    # introspection is the async `get_tool(name)`. `Tool.to_mcp_tool` serves
    # `overrides.get("inputSchema", self.parameters)` — the `parameters`
    # field IS the SDK's explicit-schema route, so pin the vendored schema
    # onto it verbatim (the signature remains only the callable).
    spike = asyncio.run(mcp.get_tool("stg_v1_gateway_info"))
    assert spike is not None, "spike tool not registered"
    spike.parameters = vend["inputSchema"]
    assert spike.parameters == vend["inputSchema"]
    assert spike.parameters["required"] == []
    assert "$defs" in spike.parameters
    # The serve conversion falls back to the pinned field — no call-time
    # inputSchema override kwarg is needed:
    assert spike.to_mcp_tool().input_schema == vend["inputSchema"]


def test_fastmcp_mount_serves_initialize_over_loopback() -> None:
    import asyncio

    import uvicorn
    from fastapi import FastAPI
    from fastmcp import FastMCP

    vend = _vendored_tool("stg_v1_gateway_info")

    mcp = FastMCP(name="spike")

    @mcp.tool(name="stg_v1_gateway_info", description="Gateway information.")
    def gateway_info() -> dict[str, object]:
        return {"ok": True, "data": {}}

    async def _pin() -> None:
        tool = await mcp.get_tool("stg_v1_gateway_info")
        assert tool is not None
        tool.parameters = vend["inputSchema"]

    asyncio.run(_pin())

    # FastMCP mounting contract: the mounted app's lifespan must run on the
    # host app or the streamable session manager's task group never starts
    # (initialize returns 500 "Task group is not initialized").
    mcp_app = mcp.http_app(path="/mcp")
    app = FastAPI(lifespan=mcp_app.lifespan)
    app.mount("/", mcp_app)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # bind-wait loop: `servers` only exists once startup() assigns it, so poll
    # the `started` flag first (getattr: attribute is absent before startup).
    for _ in range(100):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    servers = server.servers
    assert servers is not None, "uvicorn did not bind within 5s"
    port = servers[0].sockets[0].getsockname()[1]

    def post(
        payload: dict[str, object], extra_headers: dict[str, str] | None = None
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        # MCP streamable-HTTP requires both Accept types (406 otherwise); the
        # response may be SSE-framed, so parse either shape.
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        headers.update(extra_headers or {})
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/mcp",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
            response_headers = {k.lower(): v for k, v in response.headers.items()}
        if not raw.strip():
            return None, response_headers
        if content_type.startswith("text/event-stream"):
            data_line = next(line for line in raw.splitlines() if line.startswith("data:"))
            raw = data_line[5:]
        parsed: dict[str, Any] | None = json.loads(raw)
        return parsed, response_headers

    try:
        body, headers = post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {},
                    "clientInfo": {"name": "spike", "version": "0"},
                },
            }
        )
        assert body is not None and "result" in body
        # SDK-honest handshake: initialize can never echo 2026-07-28 in this
        # SDK generation — that revision is MODERN_PROTOCOL_VERSIONS, served
        # via `server/discover` below. The counter-offer caps at
        # LATEST_HANDSHAKE_VERSION (2025-11-25) per mcp_types.version.
        assert body["result"]["protocolVersion"] == LATEST_HANDSHAKE_VERSION
        session = headers.get("mcp-session-id")
        assert session is not None

        post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"Mcp-Session-Id": session},
        )

        body, _ = post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"Mcp-Session-Id": session},
        )
        assert body is not None
        wire_tool = body["result"]["tools"][0]
        assert wire_tool["name"] == "stg_v1_gateway_info"
        # Wire fact (Task 8's parity pin must account for it): serve-time
        # dereference middleware prunes the corpus's unreferenced `$defs`;
        # everything else — including `required: []` — survives verbatim.
        assert wire_tool["inputSchema"] == {
            k: v for k, v in vend["inputSchema"].items() if k != "$defs"
        }

        # Modern-era discovery: the interface/0.1.0 contract's 2026-07-28
        # pin is spoken here (envelope _meta keys + protocol/method headers).
        body, _ = post(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "server/discover",
                "params": {
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        "io.modelcontextprotocol/clientInfo": {
                            "name": "spike",
                            "version": "0",
                        },
                        "io.modelcontextprotocol/clientCapabilities": {},
                    }
                },
            },
            {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "server/discover"},
        )
        assert body is not None
        offered = body["result"]["supportedVersions"]
        assert "2026-07-28" in offered
    finally:
        server.should_exit = True
        thread.join(timeout=5)
