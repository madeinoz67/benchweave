"""WP07 Task 8: the 17 tools exist with vendored-exact schemas; auth gates tools/call.

Fidelity mechanism (Task 1 spike, amended): signature-derived schemas are
unreachable in fastmcp 4.0.3, so every tool's ``parameters``/``output_schema``
is pinned to the vendored corpus verbatim at registration. The served WIRE
``tools/list`` then carries vendored-minus-``$defs`` (serve-time dereference
middleware prunes the corpus's unreferenced ``$defs`` — the accepted
deviation, pinned here as the wire expectation; everything else, including
``required: []``, survives byte-exact). Live-mount trio over real loopback:
a valid token calls ``stg_v1_gateway_info``; a missing token is rejected
401-class at the transport; an observe-only token on a control tool
surfaces the contract ``forbidden`` envelope.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
from fastmcp import FastMCP

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import issue
from benchweave.interfaces.mcp import build_mcp
from benchweave.interfaces.operations import Operations, append_bench_event
from benchweave.state.store import Store

VENDORED = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "contracts" / "interface-v1.1.0" / "mcp-tools.json"
    ).read_text(encoding="utf-8")
)
VENDORED_TOOLS = {
    t["name"]: t
    for t in (VENDORED["tools"] if isinstance(VENDORED, dict) and "tools" in VENDORED else VENDORED)
}
EXPECTED_17 = sorted(VENDORED_TOOLS)
assert len(EXPECTED_17) == 17

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
SECRET = b"wp07-task-eight-secret"
NOW_ISO = "2026-09-12T00:00:00Z"
NOW_EPOCH = 1_800_000_000
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}


def _token(scopes: set[str]) -> str:
    return issue(
        SECRET,
        principal="tester",
        audience="stg",
        scopes=scopes,
        expires_at=NOW_EPOCH + 3600,
    )


@pytest.fixture()
def seam_app(tmp_path: Path) -> Iterator[FastMCP]:
    """build_mcp over a real Operations on the admitted fixture bench."""
    store = Store.open(tmp_path / "state.db")
    content = ContentStore(store)
    operations = Operations(
        store,
        content,
        gateway_id="gw-task8",
        limits=LIMITS,
        now_iso=lambda: NOW_ISO,
        issuer_secret=SECRET,
        now_epoch=lambda: NOW_EPOCH,
    )
    yield build_mcp(
        operations, secret=SECRET, now_epoch=lambda: NOW_EPOCH, limits=LIMITS
    )
    store.close()


def test_served_tool_set_and_schemas_equal_vendored_corpus(seam_app: FastMCP) -> None:
    """All 17 tools registered, each pinned to the vendored corpus verbatim.

    Amended introspection (Task 1 spike): ``_tool_manager`` is gone in
    fastmcp 4.0.3 — the public route is the async ``get_tool(name)``.
    """

    async def collect() -> dict[str, Any]:
        return {name: await seam_app.get_tool(name) for name in EXPECTED_17}

    served = asyncio.run(collect())
    assert sorted(served) == EXPECTED_17
    for name, tool in served.items():
        assert tool is not None, f"{name} not registered"
        assert tool.parameters == VENDORED_TOOLS[name]["inputSchema"], (
            f"{name} input schema drifted from the vendored corpus"
        )
        # MCP-wire requirement (mcp_types' Tool model): outputSchema carries
        # a top-level ``type``; the vendored outputSchema is a bare oneOf
        # whose branches are all objects, so the pin adds the one required
        # key — semantically a no-op, everything else verbatim.
        assert tool.output_schema == {
            **VENDORED_TOOLS[name]["outputSchema"], "type": "object"
        }, f"{name} output schema drifted from the vendored corpus"
        annotations = tool.annotations
        assert annotations is not None, f"{name} annotations not pinned"
        assert (
            annotations.model_dump(exclude_none=True, by_alias=True)
            == VENDORED_TOOLS[name]["annotations"]
        ), f"{name} annotations drifted from the vendored corpus"


def test_tool_names_match_catalog_mcp_fields() -> None:
    catalog = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts" / "interface-v1.1.0" / "operation-catalog.json"
        ).read_text(encoding="utf-8")
    )
    with_mcp = {op["mcp_tool"] for op in catalog["operations"] if op["mcp_tool"]}
    assert with_mcp == set(EXPECTED_17)  # admin ops deliberately absent


# --- live-mount trio (Task 1 spike's loopback pattern) ------------------------


def _boot(app: FastAPI) -> tuple[str, uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # bind-wait: `servers` only exists once startup() assigns it, so poll the
    # `started` flag first (getattr: the attribute is absent before startup).
    for _ in range(100):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn did not start (lifespan startup failed)"
    servers = server.servers
    assert servers is not None, "uvicorn did not bind within 5s"
    port = servers[0].sockets[0].getsockname()[1]
    return f"http://127.0.0.1:{port}/mcp", server, thread


def _post(
    url: str,
    payload: dict[str, Any],
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any] | None, dict[str, str]]:
    """POST one JSON-RPC frame; parse JSON or SSE framing; 4xx/5xx as status."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    headers.update(extra_headers or {})
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as error:
        return error.code, None, {k.lower(): v for k, v in error.headers.items()}
    if not raw.strip():
        return status, None, response_headers
    if content_type.startswith("text/event-stream"):
        data_line = next(line for line in raw.splitlines() if line.startswith("data:"))
        raw = data_line[5:]
    parsed: dict[str, Any] = json.loads(raw)
    return status, parsed, response_headers


def _session(url: str, token: str) -> str:
    status, body, headers = _post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "task8", "version": "0"},
            },
        },
        {"Authorization": f"Bearer {token}"},
    )
    assert status == 200, f"initialize rejected: {status}"
    assert body is not None and "result" in body, f"initialize failed: {body}"
    session = headers.get("mcp-session-id")
    assert session is not None, "no session id on initialize"
    _post(
        url,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"Mcp-Session-Id": session, "Authorization": f"Bearer {token}"},
    )
    return session


def _call_envelope(body: dict[str, Any]) -> dict[str, Any]:
    """The tools/call result envelope: structuredContent, else content text."""
    result = body.get("result")
    assert isinstance(result, dict), f"no result in {body}"
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    text = result["content"][0]["text"]
    envelope: dict[str, Any] = json.loads(text)
    return envelope


@contextmanager
def _live_app(
    tmp_path: Path,
    *,
    limits: dict[str, int] | None = None,
    prep: Callable[[Store, ContentStore], None] | None = None,
) -> Iterator[str]:
    """create_app on a fresh file-backed store; boot over real loopback.

    The store is opened ``check_same_thread=False``: the ASGI app serves
    from the event-loop thread while the store was opened on the test
    thread (usage stays serialised — single serving loop, no REST yet).
    ``prep`` runs on the store before the app boots (second bench, events,
    artifacts for the clamp fixtures).
    """
    store = Store.open(tmp_path / "state.db", check_same_thread=False)
    content = ContentStore(store)
    if prep is not None:
        prep(store, content)
    app = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=limits or LIMITS,
        gateway_id="gw-task8",
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )
    url, server, thread = _boot(app)
    try:
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        store.close()


def test_live_mount_valid_token_calls_gateway_info_and_serves_wire_schemas(
    tmp_path: Path,
) -> None:
    with _live_app(tmp_path) as url:
        session = _session(url, _token({"stg:observe"}))

        status, body, _ = _post(
            url,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "stg_v1_gateway_info", "arguments": {}},
            },
            {"Mcp-Session-Id": session, "Authorization": f"Bearer {_token({'stg:observe'})}"},
        )
        assert status == 200
        assert body is not None
        envelope = _call_envelope(body)
        assert envelope["ok"] is True
        assert envelope["data"]["mcp_version"] == "2026-07-28"
        assert envelope["data"]["gateway_id"] == "gw-task8"

        status, body, _ = _post(
            url,
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
            {"Mcp-Session-Id": session, "Authorization": f"Bearer {_token({'stg:observe'})}"},
        )
        assert status == 200
        assert body is not None
        wire_tools = body["result"]["tools"]
        assert sorted(tool["name"] for tool in wire_tools) == EXPECTED_17
        for wire_tool in wire_tools:
            vendored_schema = VENDORED_TOOLS[wire_tool["name"]]["inputSchema"]
            # Accepted deviation (Task 1 spike): the wire schema is the
            # vendored corpus minus `$defs` (serve-time dereference
            # middleware); everything else survives byte-exact.
            assert wire_tool["inputSchema"] == {
                key: value
                for key, value in vendored_schema.items()
                if key != "$defs"
            }, f"{wire_tool['name']} wire schema drifted"


def test_live_mount_auth_rejections(tmp_path: Path) -> None:
    with _live_app(tmp_path) as url:
        # Missing token: 401-class rejection at the transport (no session).
        status, body, _ = _post(
            url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "task8", "version": "0"},
                },
            },
        )
        assert status == 401, f"missing token not rejected 401-class: {status} {body}"

        # Valid observe-only token: transport passes, the control-tier seam
        # refuses — the contract `forbidden` envelope over tools/call.
        observe = _token({"stg:observe"})
        session = _session(url, observe)
        status, body, _ = _post(
            url,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "stg_v1_run_check",
                    "arguments": {"bench_id": "sim-bench", "binding_ref": {}},
                },
            },
            {"Mcp-Session-Id": session, "Authorization": f"Bearer {observe}"},
        )
        assert status == 200
        assert body is not None
        envelope = _call_envelope(body)
        assert envelope["ok"] is False
        assert envelope["error"]["code"] == "forbidden"


# --- fix wave: adapter limit/length clamping + first run-through-app test ----


def _tools_call(
    url: str, session: str, token: str, request_id: int, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    status, body, _ = _post(
        url,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        {"Mcp-Session-Id": session, "Authorization": f"Bearer {token}"},
    )
    assert status == 200
    assert body is not None
    return _call_envelope(body)


SMALL_LIMITS: dict[str, int] = {**LIMITS, "max_page_size": 1, "max_chunk_bytes": 8}


def _prep_two_benches_two_devices_two_events(store: Store, content: ContentStore) -> None:
    """Clamp-fixture inventory: 2 benches, 2 devices on sim-bench, 2 events."""
    del content  # pages need no content-store rows
    generation = store.bump_generation("bench-two", NOW_ISO)
    store.put_bench("bench-two", generation, "observation", "{}", "proprietary", NOW_ISO)
    for _ in range(2):
        append_bench_event(
            store, "bench_changed", "sim-bench", None, keep=None, now_iso=lambda: NOW_ISO
        )


def test_adapter_limit_clamped_to_max_page_size(tmp_path: Path) -> None:
    """limit=10**9 arrives as one page: the tool layer clamps to
    max_page_size before the seam's unbounded SQL LIMIT sees it."""
    with _live_app(
        tmp_path, limits=SMALL_LIMITS, prep=_prep_two_benches_two_devices_two_events
    ) as url:
        token = _token({"stg:observe"})
        session = _session(url, token)

        benches = _tools_call(
            url, session, token, 2, "stg_v1_bench_list", {"limit": 10**9, "cursor": None}
        )
        assert benches["ok"] is True, benches
        assert len(benches["data"]["items"]) == 1  # 2 benches exist
        assert benches["data"]["next_cursor"] is not None

        devices = _tools_call(
            url,
            session,
            token,
            3,
            "stg_v1_device_list",
            {"bench_id": "sim-bench", "limit": 10**9, "cursor": None},
        )
        assert devices["ok"] is True, devices
        assert len(devices["data"]["items"]) == 1  # 2 devices exist on sim-bench
        assert devices["data"]["next_cursor"] is not None

        events = _tools_call(
            url,
            session,
            token,
            4,
            "stg_v1_events_get",
            {"bench_id": "sim-bench", "after": None, "limit": 10**9},
        )
        assert events["ok"] is True, events
        assert len(events["data"]["events"]) == 1  # 2 events exist on the stream


def test_adapter_length_clamped_to_max_chunk_bytes(tmp_path: Path) -> None:
    """length=10**9 reads exactly one chunk: the tool layer clamps to
    max_chunk_bytes (the store would otherwise serve up to its own hard
    ceiling of 65536 in one response)."""
    artifact_id = ""

    def prep(store: Store, content: ContentStore) -> None:
        nonlocal artifact_id
        del store
        artifact_id = content.put_artifact(b"0123456789abcdefghij", NOW_ISO)  # 20 bytes

    with _live_app(tmp_path, limits=SMALL_LIMITS, prep=prep) as url:
        token = _token({"stg:observe"})
        session = _session(url, token)

        chunk = _tools_call(
            url,
            session,
            token,
            2,
            "stg_v1_artifact_read",
            {"artifact_id": artifact_id, "offset": 0, "length": 10**9},
        )
        assert chunk["ok"] is True, chunk
        assert chunk["data"]["bytes"] == 8  # clamped to max_chunk_bytes, not 20
        assert chunk["data"]["total_bytes"] == 20
        assert chunk["data"]["eof"] is False


def test_live_run_through_app_reaches_truthful_terminal(tmp_path: Path) -> None:
    """The whole run path over the app: run_start enqueues, the worker's
    build_run spools+admits+executes on its own thread, and run_get polls
    to a terminal state whose outcome comes from the durable record (the
    disclosed worker-death mode would land here as outcome_unknown)."""
    binding_sha = hashlib.sha256(
        (FIXTURES / "run-binding.json").read_bytes()
    ).hexdigest()
    with _live_app(tmp_path) as url:
        token = _token({"stg:control"})
        session = _session(url, token)

        started = _tools_call(
            url,
            session,
            token,
            2,
            "stg_v1_run_start",
            {
                "bench_id": "sim-bench",
                "request_id": "req-task8-live-1",
                "binding_ref": {
                    "id": "req-voltage-check-1",
                    "version": "1.0.0",
                    "sha256": binding_sha,
                },
                "expected_generation": 1,
                "lease_id": None,
            },
        )
        assert started["ok"] is True, started
        run = started["data"]
        assert run["state"] == "accepted"  # 202 semantics: read before submit

        final: dict[str, Any] = {}
        deadline = time.monotonic() + 60.0
        while True:
            current = _tools_call(
                url, session, token, 3, "stg_v1_run_get", {"run_id": run["run_id"]}
            )
            assert current["ok"] is True, current
            final = current["data"]
            if final["state"] == "terminal":
                break
            assert time.monotonic() < deadline, f"run never reached terminal: {final}"
            time.sleep(0.2)

        assert final["outcome"] == "passed"
        assert final["safe_state"] == "verified"
        assert final["terminal_record"] is not None
