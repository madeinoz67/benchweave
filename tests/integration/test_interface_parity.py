"""WP07 Task 10 parity suite: REST and MCP are the same instrument, per-op.

One live gateway (real store/content/bootstrap/app/worker via ``create_app``,
uvicorn on a real loopback port — Task 8's pattern; REST rides the same port's
``/v1`` routes) serves BOTH transports. Every shared operation is fired with
the same logical request on each transport and the FULL contract envelope is
compared: MCP ``structuredContent`` must equal the REST body field-for-field
(the adapters wrap the one seam in the one envelope), and each reachable
failure class must surface the same error code at REST's
``error_http_status`` and inside the MCP envelope.

Deviation register — what this suite PINS as documented deviations (each has
a test; none is silent) versus what it proves equal:

- D1 ``run_get`` tier (catalog is authority): the seam required ``control``
  while the catalog declares ``observe``. The seam was FIXED to observe; the
  suite pins both tiers (observe passes directly, control passes via the
  observe ⊆ control ⊆ admin hierarchy).
- D2 ``change_apply`` body: the catalog's REST input schema does not declare
  ``approver_token``, but the REST adapter forwards it as a seam kwarg
  (Task 9 disclosure). CATALOG-AMENDMENT note: the vendored catalog is frozen
  authority and is NOT edited here — the suite pins the behavior end-to-end
  (authenticated apply over REST succeeds; apply without the detached token
  fails closed ``forbidden``/``missing_token``) and records the amendment for
  WP08. The three admin ops are REST-only by catalog: no MCP twin exists.
- D3 required-vs-defaulted params — CLOSED (WP08 Task 1, as a side effect
  of D8 seam validation): catalog input schemas declare paging/chunk
  params REQUIRED; REST rejects an absent param as 400 ``invalid_request``.
  fastmcp 4.0.3 does not enforce the pinned schema's ``required`` at
  dispatch, so the MCP tool signatures' dummy defaults still fire — but the
  seam now validates the defaulted payload: every empty-string default
  (``run_id``/``bench_id``/``reason``/...) violates the corpus pattern or
  ``minLength`` and surfaces ``invalid_request`` on MCP too (parity with
  REST's 400). The one honest residual: the paging defaults (``limit=1``,
  ``cursor=None``/``after=None``) are schema-VALID well-formed requests, so
  an MCP ``bench_list`` omitting them still succeeds — pinned below; that
  is a transport-default difference, not a validation gap.
- D4 event evidence shape: the seam emits free-form evidence dicts
  (``{retention_failures}``, ``{reason, request_id}``, ``{request_id}``)
  while the contract's event ``evidence`` def is a closed document ref
  ``{id, version, sha256}``. The CURRENT wire shape is pinned (events_get
  carries the free-form dict on both transports); payloads are NOT reshaped
  here. WP08 reconciliation item.
- D5 wire ``tools/list`` schemas are vendored-minus-``$defs`` (Task 1's
  accepted serve-time dereference deviation) — pinned here at the wire
  level, alongside the exactly-17 tool set with no admin twin.
- D6 failure-class expressibility: token-shaped rejections collapse to a
  transport 401 on MCP (no envelope can exist pre-auth — the WP02 map's 403
  semantics surface only at REST), and ``payload_too_large`` is REST-only
  (no MCP transport body ceiling is wired).
- D7 token-shape probes (backfilled after review — the initial suite DROPPED
  the brief's one-expired + one-wrong-audience tokens; the omission is
  disclosed here and closed by tests): an expired token is 401
  ``unauthenticated`` with reason ``expired`` at REST and the D6
  transport-401 collapse on MCP; a wrong-audience token is 403 ``forbidden``
  at REST (the WP02 map carries audience rejections with the 403 semantics,
  not 401) and the same D6 collapse on MCP; and an stg-audience token used
  as ``approver_token`` fails closed 403 — approval authentication requires
  the detached ``gateway-admin`` audience (D2).
- Write-op equivalence: ``run_start`` is compared via its §9 idempotent
  replay (byte-identical envelope); the lease lifecycle's monotone fields
  are compared with exactly the mutating field masked (``sequence`` for
  create/renew — same lease identity via the §9 key; ``lease_id`` for
  release — two fixture-seeded leases, one released per transport).
- Unreachable failure classes, named and not faked: ``policy_denied``
  (``_bench_projection`` has no tripped source yet — the flag is hardcoded
  False until the WP08 hardware surface), ``gone``/``cursor_expired``/
  ``rate_limited``/``unavailable``/``internal_error`` (no emitting path is
  reachable through a healthy app: ``cursor_expired`` has no emitter —
  retention ``trim_stream`` deletes a contiguous prefix, so a hole can
  never arise by construction, and the contract's §7 events paragraph
  assigns the one stale-cursor path there is, retention overtake, to
  ``event_gap`` (the overtake branch is its raise site); ``unavailable``
  needs an undecided apply crash or a worker-less gateway;
  ``internal_error`` needs an unexpected exception). Monitor retention
  failures emit the ``evidence_gap`` EVENT KIND (Task 6), a different thing
  from the ``event_gap`` failure code.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import issue
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
CONTRACTS = Path(__file__).resolve().parents[2] / "contracts" / "interface-v1.1.0"
CATALOG = json.loads((CONTRACTS / "operation-catalog.json").read_text(encoding="utf-8"))
VENDORED_TOOLS = {
    t["name"]: t
    for t in json.loads((CONTRACTS / "mcp-tools.json").read_text(encoding="utf-8"))[
        "tools"
    ]
}
OPS = {op["name"]: op for op in CATALOG["operations"]}
SHARED_OPS = [op for op in CATALOG["operations"] if op["mcp_tool"]]
REST_ONLY_OPS = [op for op in CATALOG["operations"] if not op["mcp_tool"]]

SECRET = b"wp07-task-ten-secret"
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
BENCH = "sim-bench"
DEVICE = "descriptor-sim-controller"  # bootstrap keys rows by descriptor id
BINDING_SHA = hashlib.sha256((FIXTURES / "run-binding.json").read_bytes()).hexdigest()
BINDING_REF = {"id": "req-voltage-check-1", "version": "1.0.0", "sha256": BINDING_SHA}
ARTIFACT_BYTES = b"0123456789abcdefghij"  # 20 bytes — chunk reassembly target
TARGET_REF = {"id": "t10", "version": "1", "sha256": "0" * 64}
RUN_REQUEST = "req-voltage-check-1"  # §5 (D9): must equal the binding doc's own request_id


def _token(
    principal: str,
    scopes: set[str],
    *,
    audience: str = "stg",
    expires: int = NOW_EPOCH + 3600,
) -> str:
    return issue(
        SECRET,
        principal=principal,
        audience=audience,
        scopes=scopes,
        expires_at=expires,
    )


# One principal owns the seeded §9 keys; tiers differ only by scope.
OBSERVE = _token("parity", {"stg:observe"})
CONTROL = _token("parity", {"stg:control"})
ADMIN = _token("parity", {"stg:admin"})
# D7 probes (review backfill): the brief's expired + wrong-audience tokens.
EXPIRED = _token("parity-late", {"stg:admin"}, expires=NOW_EPOCH - 1)
FOREIGN_AUDIENCE = _token("parity-elsewhere", {"stg:admin"}, audience="gateway-admin")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- module gateway: one live app, both transports, seeded state -------------


def _boot(app: FastAPI) -> tuple[uvicorn.Server, threading.Thread, int]:
    """Task 8's loopback boot: real port, lifespan-run (worker + bootstrap)."""
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


def _store_approval(
    content: ContentStore, change_id: str, expected_generation: int
) -> dict[str, str]:
    """One approval document binding ``change_id`` at one generation (Task 7)."""
    body = {
        "change_id": change_id,
        "expected_generation": expected_generation,
        "approver_principal": "approver-10",
        "policy_version": "1",
    }
    raw = json.dumps(body, sort_keys=True).encode()
    sha = hashlib.sha256(raw).hexdigest()
    content.put_document(raw, sha, body, "urn:stg:approval", NOW_ISO)
    return {"id": f"approval-{change_id}", "version": "1", "sha256": sha}


APPROVER_TOKEN = _token("approver-10", {"stg:admin"}, audience="gateway-admin")


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """Seed the whole inventory the matrix reads, in generation-fence order.

    Pre-boot (content store): one artifact + one evidence row. Post-boot via
    REST (admin principal ``parity``): one run driven to a truthful terminal
    by the app's real worker (the run_start replay case and run_get/run_find/
    run_cancel all compare its STABLE terminal projection), plus three leases
    at generation 1 — one for the renew case, two to be released one per
    transport. Generation stays 1 until the admin pins late in the module.
    """
    tmp_path = tmp_path_factory.mktemp("task10-parity")
    store = Store.open(tmp_path / "state.db", check_same_thread=False)
    content = ContentStore(store)
    artifact_id = content.put_artifact(ARTIFACT_BYTES, NOW_ISO)
    evidence_id = content.put_evidence(
        "document",
        {"id": "ev-doc", "version": "1", "sha256": "0" * 64},
        artifact_id,
        None,
        NOW_ISO,
    )
    app = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=LIMITS,
        gateway_id="gw-task10",
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )
    server, thread, port = _boot(app)
    base = f"http://127.0.0.1:{port}"
    with httpx.Client(base_url=base, timeout=10.0) as client:
        started = client.post(
            f"/v1/benches/{BENCH}/runs",
            headers=_bearer(ADMIN),
            json={
                "request_id": RUN_REQUEST,
                "binding_ref": BINDING_REF,
                "expected_generation": 1,
                "lease_id": None,
            },
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["data"]["run_id"]
        final = _poll_terminal(client, run_id)
        assert final["outcome"] == "passed", final

        leases: dict[str, str] = {}
        for name, request in (
            ("renew", "req-parity-lease-renew"),
            ("rel_a", "req-parity-lease-rel-a"),
            ("rel_b", "req-parity-lease-rel-b"),
        ):
            created = client.post(
                f"/v1/benches/{BENCH}/leases",
                headers=_bearer(CONTROL),
                json={
                    "request_id": request,
                    "expected_generation": 1,
                    "duration_ms": 60000,
                },
            )
            assert created.status_code == 201, created.text
            leases[name] = created.json()["data"]["lease_id"]

        yield SimpleNamespace(
            client=client,
            base=base,
            port=port,
            store=store,
            content=content,
            run_id=run_id,
            leases=leases,
            artifact_id=artifact_id,
            evidence_id=evidence_id,
        )
    server.should_exit = True
    thread.join(timeout=5)
    store.close()


def _poll_terminal(client: httpx.Client, run_id: str) -> dict[str, Any]:
    """Poll run_get to a terminal projection (the stable read parity needs)."""
    deadline = time.monotonic() + 60.0
    while True:
        resp = client.get(f"/v1/runs/{run_id}", headers=_bearer(ADMIN))
        assert resp.status_code == 200, resp.text
        data: dict[str, Any] = resp.json()["data"]
        if data["state"] == "terminal":
            return data
        assert time.monotonic() < deadline, f"run never reached terminal: {data}"
        time.sleep(0.2)


# --- MCP client (Task 8's frame pattern: session + SSE-aware post) ----------


def _post(
    port: int, payload: dict[str, Any], headers: dict[str, str] | None = None
) -> tuple[int, dict[str, Any] | None]:
    """POST one JSON-RPC frame; parse JSON or SSE framing; status always kept."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:  # transport-level rejections (401)
        return error.code, None
    if not raw.strip():
        return status, None
    if content_type.startswith("text/event-stream"):
        data_line = next(line for line in raw.splitlines() if line.startswith("data:"))
        raw = data_line[5:]
    return status, json.loads(raw)


def _initialize(
    port: int, headers: dict[str, str]
) -> tuple[int, str | None]:
    """One MCP initialize frame -> (status, session id); a rejected token
    surfaces as HTTP 401 with no session (the transport's only expression)."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "task10", "version": "0"},
                },
            }
        ).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **headers,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers.get("mcp-session-id")
    except urllib.error.HTTPError as error:
        return error.code, None


def _call(
    port: int, tool: str, arguments: dict[str, Any], token: str
) -> dict[str, Any]:
    """One tools/call on a fresh session -> the contract envelope."""
    headers = _bearer(token)
    status, session = _initialize(port, headers)
    assert status == 200 and session is not None, (status, session)
    ack = _post(
        port,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"Mcp-Session-Id": session, **headers},
    )
    assert ack[0] in (200, 202), ack
    status, body = _post(
        port,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
        {"Mcp-Session-Id": session, **headers},
    )
    assert status == 200, (status, body)
    assert body is not None and "result" in body, body
    result = body["result"]
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        found: dict[str, Any] = structured
        return found
    envelope: dict[str, Any] = json.loads(result["content"][0]["text"])
    return envelope


def _call_result(
    port: int, tool: str, arguments: dict[str, Any], token: str
) -> dict[str, Any]:
    """One tools/call on a fresh session -> the RAW JSON-RPC result object
    (``isError`` flag included, not just the contract envelope)."""
    headers = _bearer(token)
    status, session = _initialize(port, headers)
    assert status == 200 and session is not None, (status, session)
    ack = _post(
        port,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"Mcp-Session-Id": session, **headers},
    )
    assert ack[0] in (200, 202), ack
    status, body = _post(
        port,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
        {"Mcp-Session-Id": session, **headers},
    )
    assert status == 200, (status, body)
    assert body is not None and "result" in body, body
    result: dict[str, Any] = body["result"]
    return result


def _rest(
    gw: SimpleNamespace,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    token: str,
) -> tuple[int, dict[str, Any]]:
    resp = gw.client.request(method, path, json=body, headers=_bearer(token))
    return resp.status_code, resp.json()


def _fill(value: Any, ids: dict[str, Any]) -> Any:
    """Resolve ``"{name}"`` sentinels from ``ids`` (Task 9's matrix pattern)."""
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        return ids[value[1:-1]]
    if isinstance(value, dict):
        return {key: _fill(item, ids) for key, item in value.items()}
    return value


# --- wire tools/list: exactly 17, no admin twin, vendored-minus-$defs (D5) ---


def test_wire_tools_list_exact_set_and_schemas(gateway: SimpleNamespace) -> None:
    headers = _bearer(OBSERVE)
    status, session = _initialize(gateway.port, headers)
    assert status == 200 and session is not None
    status, body = _post(
        gateway.port,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"Mcp-Session-Id": session, **headers},
    )
    assert status == 200 and body is not None, body
    wire_tools = body["result"]["tools"]
    names = {tool["name"] for tool in wire_tools}
    assert names == {op["mcp_tool"] for op in SHARED_OPS}
    assert len(names) == 17
    for op in REST_ONLY_OPS:
        assert f"stg_v1_{op['name']}" not in names  # admin ops have no MCP twin
    for tool in wire_tools:
        vendored = VENDORED_TOOLS[tool["name"]]["inputSchema"]
        assert tool["inputSchema"] == {
            key: value for key, value in vendored.items() if key != "$defs"
        }, f"{tool['name']} wire schema drifted (D5 pin: vendored minus $defs)"


# --- per-operation success parity: FULL envelope equality --------------------


EXACT_CASES: dict[str, dict[str, Any]] = {
    # op -> rest (method, path, body), mcp tool arguments, token tier.
    # Every read compares a stable projection; run_cancel's response is the
    # terminal projection (worker cancel on a finished run is a documented
    # no-op), so firing it on both transports is byte-comparable.
    "gateway_info": {
        "rest": ("get", "/v1", None),
        "mcp": {},
        "token": OBSERVE,
    },
    "bench_list": {
        "rest": ("get", "/v1/benches?limit=10&cursor=", None),
        "mcp": {"limit": 10, "cursor": None},
        "token": OBSERVE,
    },
    "bench_get": {
        "rest": ("get", f"/v1/benches/{BENCH}", None),
        "mcp": {"bench_id": BENCH},
        "token": OBSERVE,
    },
    "device_list": {
        "rest": ("get", f"/v1/benches/{BENCH}/devices?limit=10&cursor=", None),
        "mcp": {"bench_id": BENCH, "limit": 10, "cursor": None},
        "token": OBSERVE,
    },
    "device_get": {
        "rest": ("get", f"/v1/benches/{BENCH}/devices/{DEVICE}", None),
        "mcp": {"bench_id": BENCH, "device_id": DEVICE},
        "token": OBSERVE,
    },
    "document_get": {
        "rest": ("get", "/v1/documents/{sha}", None),
        "mcp": {"sha256": "{sha}"},
        "token": OBSERVE,
    },
    "run_check": {
        "rest": ("post", f"/v1/benches/{BENCH}/run-checks", {"binding_ref": BINDING_REF}),
        "mcp": {"bench_id": BENCH, "binding_ref": BINDING_REF},
        "token": CONTROL,
    },
    # OBSERVE is the tier pin (D1): the catalog declares run_get observe.
    "run_get": {
        "rest": ("get", "/v1/runs/{run_id}", None),
        "mcp": {"run_id": "{run_id}"},
        "token": OBSERVE,
    },
    "run_find": {
        "rest": ("get", f"/v1/requests/{RUN_REQUEST}", None),
        "mcp": {"request_id": RUN_REQUEST},
        "token": CONTROL,
    },
    "run_cancel": {
        "rest": (
            "post",
            "/v1/runs/{run_id}/cancellations",
            {"request_id": "req-parity-cancel", "reason": "parity"},
        ),
        "mcp": {
            "run_id": "{run_id}",
            "request_id": "req-parity-cancel",
            "reason": "parity",
        },
        "token": CONTROL,
    },
    "events_get": {
        "rest": ("get", f"/v1/benches/{BENCH}/events?after=&limit=10", None),
        "mcp": {"bench_id": BENCH, "after": None, "limit": 10},
        "token": OBSERVE,
    },
    "evidence_get": {
        "rest": ("get", "/v1/evidence/{evidence_id}", None),
        "mcp": {"evidence_id": "{evidence_id}"},
        "token": OBSERVE,
    },
    "artifact_read": {
        "rest": ("get", "/v1/artifacts/{artifact_id}/chunks?offset=0&length=64", None),
        "mcp": {"artifact_id": "{artifact_id}", "offset": 0, "length": 64},
        "token": OBSERVE,
    },
}
WRITE_LIFECYCLE_OPS = {"lease_create", "lease_release", "lease_renew", "run_start"}
assert set(EXACT_CASES) == {op["name"] for op in SHARED_OPS} - WRITE_LIFECYCLE_OPS, (
    "matrix must cover every shared op except the four write-lifecycle ops"
)


@pytest.mark.parametrize("op_name", sorted(EXACT_CASES))
def test_rest_and_mcp_agree_per_operation(
    gateway: SimpleNamespace, op_name: str
) -> None:
    case = EXACT_CASES[op_name]
    seed = {
        "sha": BINDING_SHA,
        "run_id": gateway.run_id,
        "evidence_id": gateway.evidence_id,
        "artifact_id": gateway.artifact_id,
    }
    method, path, body = case["rest"]
    status, rest_json = _rest(
        gateway, method, path.format(**seed), _fill(body, seed), case["token"]
    )
    assert status == OPS[op_name]["success_status"], (op_name, rest_json)
    assert rest_json["ok"] is True, op_name
    mcp_json = _call(
        gateway.port,
        OPS[op_name]["mcp_tool"],
        _fill(case["mcp"], seed),
        case["token"],
    )
    # Contract §2: MCP structuredContent carries the same STG result — the
    # FULL data envelope, field for field, not a shape sample.
    assert mcp_json == rest_json, op_name


# --- D1: run_get tier pinned at observe (catalog authority) ------------------


def test_run_get_catalog_tier_observe_control_hierarchy(
    gateway: SimpleNamespace,
) -> None:
    """Catalog declares observe; the hierarchy still admits control/admin."""
    for token in (OBSERVE, CONTROL, ADMIN):
        status, rest_json = _rest(gateway, "get", f"/v1/runs/{gateway.run_id}", None, token)
        assert status == 200 and rest_json["ok"] is True, (token, rest_json)
        assert _call(gateway.port, "stg_v1_run_get", {"run_id": gateway.run_id}, token) == (
            rest_json
        )


# --- write-lifecycle parity ---------------------------------------------------


def test_run_start_replay_parity(gateway: SimpleNamespace) -> None:
    """§9 replay: the same request id + binding pin returns the ORIGINAL run
    (no second enqueue), so both transports answer byte-identically."""
    status, rest_json = _rest(
        gateway,
        "post",
        f"/v1/benches/{BENCH}/runs",
        {
            "request_id": RUN_REQUEST,
            "binding_ref": BINDING_REF,
            "expected_generation": 1,
            "lease_id": None,
        },
        CONTROL,
    )
    assert status == 202, rest_json
    assert rest_json["data"]["run_id"] == gateway.run_id
    assert rest_json["data"]["state"] == "terminal"
    mcp_json = _call(
        gateway.port,
        "stg_v1_run_start",
        {
            "bench_id": BENCH,
            "request_id": RUN_REQUEST,
            "binding_ref": BINDING_REF,
            "expected_generation": 1,
            "lease_id": None,
        },
        CONTROL,
    )
    assert mcp_json == rest_json


def test_lease_create_parity(gateway: SimpleNamespace) -> None:
    """Same §9 key on both transports names the SAME lease identity; only the
    monotone fencing ``sequence`` differs (masked — the one mutating field)."""
    body = {
        "request_id": "req-parity-lease-create",
        "expected_generation": 1,
        "duration_ms": 60000,
    }
    rest_status, rest_json = _rest(
        gateway, "post", f"/v1/benches/{BENCH}/leases", body, CONTROL
    )
    mcp_json = _call(
        gateway.port,
        "stg_v1_lease_create",
        {"bench_id": BENCH, **body},
        CONTROL,
    )
    assert rest_status == 201 and rest_json["ok"] and mcp_json["ok"]
    assert rest_json["data"]["lease_id"] == mcp_json["data"]["lease_id"]
    masked = [{**env["data"], "sequence": None} for env in (rest_json, mcp_json)]
    assert masked[0] == masked[1]
    assert rest_json["data"]["sequence"] != mcp_json["data"]["sequence"]


def test_lease_release_parity(gateway: SimpleNamespace) -> None:
    """Two fixture-seeded leases, one released per transport: identical
    released-envelope shape; only the §9-derived ``lease_id`` differs."""
    rest_status, rest_json = _rest(
        gateway,
        "post",
        f"/v1/leases/{gateway.leases['rel_a']}/releases",
        {"request_id": "req-parity-release-rest", "reason": "done"},
        CONTROL,
    )
    mcp_json = _call(
        gateway.port,
        "stg_v1_lease_release",
        {
            "lease_id": gateway.leases["rel_b"],
            "request_id": "req-parity-release-mcp",
            "reason": "done",
        },
        CONTROL,
    )
    assert rest_status == 200 and rest_json["ok"] and mcp_json["ok"]
    assert rest_json["data"]["state"] == mcp_json["data"]["state"] == "released"
    # Both fields differ by construction: §9-derived lease ids name different
    # leases, and bench-wide fencing sequences are monotone per issue.
    masked = [
        {**env["data"], "lease_id": None, "sequence": None}
        for env in (rest_json, mcp_json)
    ]
    assert masked[0] == masked[1]


def test_lease_renew_parity(gateway: SimpleNamespace) -> None:
    """Renew twice (REST at sequence S, MCP at S+1): same lease identity and
    frozen-clock expiry; only the fencing ``sequence`` advances (masked).
    The live sequence is read from the store — the fixture run's coordinator
    reservation consumed sequence 1, so no sequence is positionally knowable."""
    current = next(
        lease.sequence
        for lease in gateway.store.list_leases(BENCH)
        if lease.lease_id == gateway.leases["renew"] and lease.state == "active"
    )
    rest_status, rest_json = _rest(
        gateway,
        "post",
        f"/v1/leases/{gateway.leases['renew']}/renewals",
        {
            "request_id": "req-parity-renew-rest",
            "sequence": current,
            "duration_ms": 60000,
        },
        CONTROL,
    )
    assert rest_status == 200, rest_json
    next_sequence = rest_json["data"]["sequence"]
    mcp_json = _call(
        gateway.port,
        "stg_v1_lease_renew",
        {
            "lease_id": gateway.leases["renew"],
            "request_id": "req-parity-renew-mcp",
            "sequence": next_sequence,
            "duration_ms": 60000,
        },
        CONTROL,
    )
    assert mcp_json["ok"], mcp_json
    assert mcp_json["data"]["lease_id"] == rest_json["data"]["lease_id"]
    masked = [{**env["data"], "sequence": None} for env in (rest_json, mcp_json)]
    assert masked[0] == masked[1]
    assert mcp_json["data"]["sequence"] == next_sequence + 1


# --- failure-class parity ------------------------------------------------------

FAILURE_CASES: list[tuple[str, str]] = [
    # code, how the two sides compare (see the assertion block for levels):
    # "full" = the seam produced the identical failure on both transports.
    ("unauthenticated", "transport"),
    ("forbidden", "code"),
    ("not_found", "full"),
    ("conflict", "full"),
]


@pytest.mark.parametrize("code,level", FAILURE_CASES)
def test_failure_classes_match_on_both_transports(
    gateway: SimpleNamespace, code: str, level: str
) -> None:
    if code == "unauthenticated":
        # REST: 401 + contract envelope for a MISSING token; MCP: the
        # transport can only reject 401 pre-auth (D6, pinned honestly).
        resp = gateway.client.get("/v1")  # no Authorization header at all
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthenticated"
        status, session = _initialize(gateway.port, {})
        assert status == 401 and session is None  # transport-level reject
        return

    if code == "forbidden":
        # Insufficient tier on each transport's own surface: observe token on
        # the admin REST route / on the control-tier MCP tool.
        status, rest_json = _rest(
            gateway, "get", "/v1/admin/changes/none", None, OBSERVE
        )
        mcp_json = _call(
            gateway.port,
            "stg_v1_run_check",
            {"bench_id": BENCH, "binding_ref": BINDING_REF},
            OBSERVE,
        )
    elif code == "not_found":
        status, rest_json = _rest(gateway, "get", "/v1/benches/nope-bench", None, OBSERVE)
        mcp_json = _call(
            gateway.port, "stg_v1_bench_get", {"bench_id": "nope-bench"}, OBSERVE
        )
    else:  # conflict: stale expected_generation, never enqueued
        body = {
            "request_id": "req-parity-conflict",
            "binding_ref": BINDING_REF,
            "expected_generation": 999,
            "lease_id": None,
        }
        status, rest_json = _rest(
            gateway, "post", f"/v1/benches/{BENCH}/runs", body, CONTROL
        )
        mcp_json = _call(
            gateway.port,
            "stg_v1_run_start",
            {"bench_id": BENCH, **body},
            CONTROL,
        )

    assert status == CATALOG["error_http_status"][code], (code, rest_json)
    assert rest_json["ok"] is False and mcp_json["ok"] is False
    assert rest_json["error"]["code"] == mcp_json["error"]["code"] == code
    assert rest_json["error"]["retry"] == mcp_json["error"]["retry"]
    if level == "full":
        assert rest_json["error"] == mcp_json["error"], code


def test_invalid_request_required_param_rest_vs_mcp_default(
    gateway: SimpleNamespace,
) -> None:
    """D3 post-D8 pin: REST rejects an absent required param (400
    invalid_request) and a non-integer one; on MCP the fastmcp defaults
    still fire (no dispatch-time ``required`` enforcement), but the seam now
    validates the defaulted payload — the empty-string defaults are
    schema-INVALID, so an omitted required string param surfaces
    ``invalid_request`` on MCP too (the D3 close). The paging defaults
    (``limit=1``, ``cursor=None``) are schema-valid well-formed requests
    and still succeed: the honest residual, pinned as such."""
    status, rest_json = _rest(gateway, "get", "/v1/benches", None, OBSERVE)
    assert status == 400
    assert rest_json["error"]["code"] == "invalid_request"

    status, rest_json = _rest(gateway, "get", "/v1/benches?limit=abc&cursor=", None, OBSERVE)
    assert status == 400
    assert rest_json["error"]["code"] == "invalid_request"

    # REST twin of the MCP defaulted call: omitting required BODY fields is
    # 400 there, so the class agrees across transports for string params.
    status, rest_json = _rest(
        gateway, "post", "/v1/runs/none/cancellations", {"request_id": "req-d3"}, CONTROL
    )
    assert status == 400
    assert rest_json["error"]["code"] == "invalid_request"

    # The close: omitted required string params over MCP now yield the
    # contract invalid_request envelope (empty-string defaults violate the
    # corpus pattern/minLength) — previously this call succeeded.
    mcp_json = _call(gateway.port, "stg_v1_run_cancel", {}, CONTROL)
    assert mcp_json["ok"] is False, mcp_json
    assert mcp_json["error"]["code"] == "invalid_request"

    # The residual: paging defaults are schema-valid, so the call succeeds.
    mcp_json = _call(gateway.port, "stg_v1_bench_list", {}, OBSERVE)
    assert mcp_json["ok"] is True, mcp_json  # limit/cursor defaulted, valid


# --- D8: seam validation parity (spec Decision 2) -----------------------------
#
# Empirical transport boundary (pinned by this suite's RED run, and the
# reason the matrix is split by what can reach the seam):
#
# - REST forwards raw body/path values, so EVERY schema violation reaches
#   the seam and is ``invalid_request`` 400 — pinned for all classes below.
# - MCP dispatch validates arguments against the tool SIGNATURE, not the
#   vendored schema (the D3 root): numeric strings COERCE to the annotated
#   int (``"1"`` -> 1) and string-where-object is rejected by fastmcp with
#   its own non-contract error — neither reaches the seam over MCP. The
#   seam itself rejects both classes (unit suite + REST prove it).
# - Schema violations on plain string params (pattern violations, empty
#   strings) pass signature coercion and DO reach the seam on both
#   transports — the both-transport envelope matrix below.

TYPE_CONFUSION_CASES: dict[str, dict[str, Any]] = {
    # op -> rest (method, path, body), token tier. Every case is
    # shape-invalid per the vendored corpus. Pre-D8 REST behavior (pinned
    # by the RED run): 500 internal_error (AttributeError on the confused
    # binding), 409 conflict (string expected_generation compared
    # unequal), or a 201 with garbage stored (change_submit target_ref).
    "run_start_binding": {
        "rest": ("post", f"/v1/benches/{BENCH}/runs", {
            "request_id": "req-tc-run-start",
            "binding_ref": "not-an-object",
            "expected_generation": 1,
            "lease_id": None,
        }),
        "token": CONTROL,
    },
    "run_check_binding": {
        "rest": ("post", f"/v1/benches/{BENCH}/run-checks", {
            "binding_ref": "not-an-object",
        }),
        "token": CONTROL,
    },
    "run_start_generation": {
        "rest": ("post", f"/v1/benches/{BENCH}/runs", {
            "request_id": "req-tc-generation",
            "binding_ref": BINDING_REF,
            "expected_generation": "1",  # string where the corpus declares integer
            "lease_id": None,
        }),
        "token": CONTROL,
    },
    "lease_create_duration": {
        "rest": ("post", f"/v1/benches/{BENCH}/leases", {
            "request_id": "req-tc-lease-create",
            "expected_generation": 1,
            "duration_ms": "60000",  # string where the corpus declares integer
        }),
        "token": CONTROL,
    },
    "lease_renew_sequence": {
        # "{renew}" resolves to the fixture's live renew lease in-test.
        "rest": ("post", "/v1/leases/{renew}/renewals", {
            "request_id": "req-tc-lease-renew",
            "sequence": "1",  # string where the corpus declares integer
            "duration_ms": 60000,
        }),
        "token": CONTROL,
    },
    "change_submit_target": {
        "rest": ("post", "/v1/admin/changes", {
            "request_id": "req-tc-change-submit",
            "bench_id": BENCH,
            "kind": "trip_reset",
            "target_ref": "not-an-object",
            "expected_generation": 1,
            "reason": "type-confusion pin",
        }),
        "token": ADMIN,  # admin ops are REST-only by catalog (no MCP twin)
    },
}


@pytest.mark.parametrize("op_name", sorted(TYPE_CONFUSION_CASES))
def test_type_confusion_is_invalid_request_at_rest(
    gateway: SimpleNamespace, op_name: str
) -> None:
    """D8 pin (REST carries every class): shape-invalid inputs are the
    contract ``invalid_request`` at the catalog's 400 — replacing the
    presence-only layer where they coerced (409), 500'd, or stored garbage
    (201). The MCP arms of two classes are transport-pre-empted (see
    ``test_mcp_signature_coercion_boundary``); the seam-level rejection is
    proven by the unit validation suite.
    """
    case = TYPE_CONFUSION_CASES[op_name]
    seed = {"renew": gateway.leases["renew"]}
    method, path, body = case["rest"]
    status, rest_json = _rest(
        gateway, method, path.format(**seed), _fill(body, seed), case["token"]
    )
    assert status == CATALOG["error_http_status"]["invalid_request"], (op_name, rest_json)
    assert rest_json["error"]["code"] == "invalid_request", op_name
    assert rest_json["error"]["retry"] == "never"


SCHEMA_VIOLATION_CASES: dict[str, dict[str, Any]] = {
    # Violations on plain string params pass fastmcp's signature coercion
    # and reach the seam on BOTH transports — full envelope parity here.
    # Pre-D8 behavior (RED run): not_found 404 on both.
    "bench_get": {
        "rest": ("get", "/v1/benches/BAD_ID", None),
        "mcp": {"bench_id": "BAD_ID"},  # violates ^[a-z][a-z0-9_.-]*$
        "token": OBSERVE,
    },
    "run_find": {
        "rest": ("get", "/v1/requests/REQ_BAD", None),
        "mcp": {"request_id": "REQ_BAD"},
        "token": CONTROL,
    },
    "lease_create": {
        "rest": ("post", "/v1/benches/BAD_BENCH/leases", {
            "request_id": "req-sv-lease-create",
            "expected_generation": 1,
            "duration_ms": 60000,
        }),
        "mcp": {
            "bench_id": "BAD_BENCH",
            "request_id": "req-sv-lease-create",
            "expected_generation": 1,
            "duration_ms": 60000,
        },
        "token": CONTROL,
    },
}


@pytest.mark.parametrize("op_name", sorted(SCHEMA_VIOLATION_CASES))
def test_schema_violation_is_invalid_request_on_both_transports(
    gateway: SimpleNamespace, op_name: str
) -> None:
    """D8 pin (both transports): a schema violation that reaches the seam
    yields the identical contract failure envelope — same code, same retry
    — with REST at the catalog's 400.
    """
    case = SCHEMA_VIOLATION_CASES[op_name]
    method, path, body = case["rest"]
    status, rest_json = _rest(gateway, method, path, body, case["token"])
    assert status == CATALOG["error_http_status"]["invalid_request"], (op_name, rest_json)
    assert rest_json["error"]["code"] == "invalid_request", op_name
    mcp_json = _call(
        gateway.port, f"stg_v1_{op_name}", case["mcp"], case["token"]
    )
    assert mcp_json["ok"] is False, (op_name, mcp_json)
    assert mcp_json["error"]["code"] == "invalid_request", op_name
    assert mcp_json["error"]["retry"] == rest_json["error"]["retry"]


def test_mcp_signature_coercion_boundary(gateway: SimpleNamespace) -> None:
    """D8/D3 boundary disclosure (empirical, from this suite's RED run):
    fastmcp validates tool arguments against the SIGNATURE, not the
    vendored schema, so two type-confusion classes never reach the seam
    over MCP. (a) A string-where-object argument is rejected BY FASTMCP —
    an isError result carrying fastmcp's own text, not the contract
    envelope (the call fails; nothing is accepted). (b) A numeric-string
    argument is COERCED to the annotated int — a coerced renewal proceeds
    to its real semantic fence (here: the sequence conflict; on
    run_start/lease_create the RED run showed coerced accepts). The seam
    itself rejects both classes — proven by the unit validation suite and
    the REST arms above. No state is mutated by this probe.
    """
    rejected = _call_result(
        gateway.port,
        "stg_v1_run_check",
        {"bench_id": BENCH, "binding_ref": "not-an-object"},
        CONTROL,
    )
    assert rejected["isError"] is True, rejected
    assert "structuredContent" not in rejected  # not a contract envelope

    coerced = _call(
        gateway.port,
        "stg_v1_lease_renew",
        {
            "lease_id": gateway.leases["renew"],
            "request_id": "req-coerce-renew",
            "sequence": "1",  # coerced to int 1 -> real semantic fence
            "duration_ms": 60000,
        },
        CONTROL,
    )
    assert coerced["ok"] is False, coerced
    assert coerced["error"]["code"] == "conflict"  # sequence fence, no mutation


def test_extra_property_wire_truth_on_both_transports(
    gateway: SimpleNamespace,
) -> None:
    """D8 residual pin — extra-property enforcement is seam-only, and the
    two wires diverge (RED-sanity'd both ways before pinning):

    - REST drops the extra property at the adapter's named-field
      translation (``_field`` extraction), so the request SUCCEEDS with
      the property silently ignored — the normal success envelope at the
      catalog's success status, not ``invalid_request``.
    - MCP rejects an unknown tool argument at dispatch (fastmcp validates
      against the SIGNATURE, which has no ``junk`` param): an isError
      result carrying fastmcp's own text — not the contract envelope, and
      nothing is accepted.
    - The seam itself rejects extra properties (``additionalProperties:
      false``, unit suite); wire-level enforcement on either transport
      needs adapter changes (excluded here by the ruling-4 adapter
      freeze) — registered as the named D8 residual in
      docs/compatibility.md.
    """
    mcp_result = _call_result(
        gateway.port,
        "stg_v1_run_cancel",
        {
            "run_id": gateway.run_id,
            "request_id": "req-extra-mcp",
            "reason": "extra",
            "junk": 1,
        },
        CONTROL,
    )
    assert mcp_result["isError"] is True, mcp_result
    assert "structuredContent" not in mcp_result  # not a contract envelope

    status, rest_json = _rest(
        gateway,
        "post",
        f"/v1/runs/{gateway.run_id}/cancellations",
        {"request_id": "req-extra-rest", "reason": "extra", "junk": 1},
        CONTROL,
    )
    assert status == OPS["run_cancel"]["success_status"], rest_json
    assert rest_json["ok"] is True, rest_json  # extra property silently dropped


def test_payload_too_large_rest_only(gateway: SimpleNamespace) -> None:
    """D6 pin: the REST adapter enforces ``max_json_bytes`` (413); no MCP
    transport body ceiling is wired, so the class is REST-reachable only."""
    padding = "x" * (LIMITS["max_json_bytes"] + 1)
    resp = gateway.client.post(
        f"/v1/benches/{BENCH}/run-checks",
        headers=_bearer(ADMIN),
        json={"binding_ref": {"id": padding, "version": "1", "sha256": BINDING_SHA}},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"


def test_expired_token_probe(gateway: SimpleNamespace) -> None:
    """D7 pin: an expired token is 401 ``unauthenticated`` carrying the
    reason string ``expired`` at REST, and the D6 transport-401 collapse
    (no envelope, no session) on MCP."""
    status, rest_json = _rest(gateway, "get", "/v1", None, EXPIRED)
    assert status == 401
    assert rest_json["error"]["code"] == "unauthenticated"
    assert "expired" in rest_json["error"]["message"]
    transport_status, session = _initialize(gateway.port, _bearer(EXPIRED))
    assert transport_status == 401 and session is None  # D6 collapse


def test_wrong_audience_token_probe(gateway: SimpleNamespace) -> None:
    """D7 pin: a token minted for another audience never reaches an stg
    surface — 403 ``forbidden`` at REST (the WP02 map carries audience
    rejections with the 403 semantics, not 401; pinned as the map yields),
    and the same D6 transport-401 collapse on MCP."""
    status, rest_json = _rest(gateway, "get", "/v1", None, FOREIGN_AUDIENCE)
    assert status == 403
    assert rest_json["error"]["code"] == "forbidden"
    assert "wrong_audience" in rest_json["error"]["message"]
    transport_status, session = _initialize(
        gateway.port, _bearer(FOREIGN_AUDIENCE)
    )
    assert transport_status == 401 and session is None  # D6 collapse


def test_mcp_is_error_flag_on_failure_and_success(gateway: SimpleNamespace) -> None:
    """Final-fix-wave pin (§2/§10): a failure envelope is not a normal tool
    result — the MCP result carries ``isError: true`` with the contract
    envelope as structured content, and a success carries ``isError``
    false. REST expresses the same truth via its HTTP status; the flag is
    the MCP transport's only expression of it."""
    failed = _call_result(
        gateway.port,
        "stg_v1_bench_get",
        {"bench_id": "nope-bench"},
        OBSERVE,
    )
    assert failed["isError"] is True, failed
    failure_envelope = failed["structuredContent"]
    assert failure_envelope["ok"] is False
    assert failure_envelope["error"]["code"] == "not_found"

    succeeded = _call_result(
        gateway.port, "stg_v1_bench_get", {"bench_id": BENCH}, OBSERVE
    )
    assert succeeded["isError"] is False, succeeded
    assert succeeded["structuredContent"]["ok"] is True


# --- D4: event evidence wire shape ---------------------------------------------


def test_event_evidence_shape_deviation(gateway: SimpleNamespace) -> None:
    """D4 pin, realigned by D12: the seam's free-form evidence dict still
    rides the wire on both transports for the legacy kinds (the contract's
    event def declares a closed doc-ref — that half of the divergence is
    pinned, not reshaped; the remaining free-form kinds stay a WP08
    reconciliation item), while ``authority_changed`` — D12's first
    emitters — conforms to the def's closed ref exactly.

    Runs BEFORE the retention-trim case: the run_cancel evidence rows this
    asserts over are exactly what the trim deletes.
    """
    _, rest_json = _rest(
        gateway, "get", f"/v1/benches/{BENCH}/events?after=&limit=100", None, OBSERVE
    )
    mcp_json = _call(
        gateway.port,
        "stg_v1_events_get",
        {"bench_id": BENCH, "after": None, "limit": 100},
        OBSERVE,
    )
    assert mcp_json == rest_json
    evidences = [event["evidence"] for event in rest_json["data"]["events"]]
    # The matrix's run_cancel emitted {reason, request_id} — free-form, and
    # demonstrably not the closed {id, version, sha256} doc-ref.
    assert {"reason": "parity", "request_id": "req-parity-cancel"} in evidences
    # D12: wherever the matrix emitted authority_changed, its evidence IS
    # the closed doc-ref (the def's shape) — the first kind reconciled.
    authority = [
        event["evidence"]
        for event in rest_json["data"]["events"]
        if event["kind"] == "authority_changed"
    ]
    assert all(set(ev) == {"id", "version", "sha256"} for ev in authority), authority


def test_event_gap_after_retention_trim(gateway: SimpleNamespace) -> None:
    """event_gap on both transports (§7 events paragraph, final-fix-wave
    correction): a valid held cursor the retention window has overtaken is
    refused, never silently truncated. The trim is seeded directly on the
    fixture's store; both adapters then read the same retained stream."""
    stream = f"bench.{BENCH}"
    page = _rest(
        gateway, "get", f"/v1/benches/{BENCH}/events?after=&limit=1", None, OBSERVE
    )
    assert page[1]["ok"] is True
    held = page[1]["data"]["cursor"]
    assert held is not None
    gateway.store.trim_stream(stream, 1)  # retention overtakes the held cursor
    status, rest_json = _rest(
        gateway, "get", f"/v1/benches/{BENCH}/events?after={held}&limit=10", None, OBSERVE
    )
    mcp_json = _call(
        gateway.port,
        "stg_v1_events_get",
        {"bench_id": BENCH, "after": held, "limit": 10},
        OBSERVE,
    )
    assert status == 410
    assert rest_json["error"]["code"] == "event_gap"
    assert mcp_json["error"] == rest_json["error"]


# --- §9 isolation (ledger item 7) ----------------------------------------------


def test_cross_principal_request_id_isolation(gateway: SimpleNamespace) -> None:
    """§9 (ledger item 7) over the SEEDED run: discovery is principal-scoped —
    a foreign principal replaying the request id finds nothing on either
    transport; the owning principal's retry returns the same run on both.

    No second run is started here by design: the coordinator's acceptance
    key is the BINDING document's own request id ("run ids are never
    reusable"), so a fresh run_start on the same binding would crash in the
    worker instead of proving anything about §9 — Task 9's matrix replays for
    the same reason. Principal scoping is exactly what run_find proves."""
    owner = _token("parity", {"stg:control"})  # the seeded run's principal
    foreign = _token("parity-b", {"stg:control"})

    status, rest_json = _rest(gateway, "get", f"/v1/requests/{RUN_REQUEST}", None, foreign)
    assert status == 404
    mcp_json = _call(
        gateway.port, "stg_v1_run_find", {"request_id": RUN_REQUEST}, foreign
    )
    assert mcp_json["ok"] is False
    assert mcp_json["error"] == rest_json["error"]

    status, rest_json = _rest(gateway, "get", f"/v1/requests/{RUN_REQUEST}", None, owner)
    assert status == 200 and rest_json["data"]["run_id"] == gateway.run_id
    assert _call(
        gateway.port, "stg_v1_run_find", {"request_id": RUN_REQUEST}, owner
    ) == rest_json


# --- document bytes + chunk digests through both transports --------------------


def test_document_bytes_and_chunk_digests(gateway: SimpleNamespace) -> None:
    raw = (FIXTURES / "run-binding.json").read_bytes()
    _, rest_json = _rest(
        gateway, "get", f"/v1/documents/{BINDING_SHA}", None, OBSERVE
    )
    assert base64.b64decode(rest_json["data"]["original_utf8_base64"]) == raw
    mcp_json = _call(
        gateway.port, "stg_v1_document_get", {"sha256": BINDING_SHA}, OBSERVE
    )
    assert mcp_json == rest_json
    assert base64.b64decode(mcp_json["data"]["original_utf8_base64"]) == raw

    # Interleaved chunk reads reassemble to the whole-artifact digest; every
    # response's sha256 is the WHOLE artifact's (Task 3 invariant).
    _, whole = _rest(
        gateway,
        "get",
        f"/v1/artifacts/{gateway.artifact_id}/chunks?offset=0&length=64",
        None,
        OBSERVE,
    )
    whole_sha = whole["data"]["sha256"]
    assert whole["data"]["total_bytes"] == len(ARTIFACT_BYTES)
    assert whole["data"]["eof"] is True
    reassembled = b""
    for offset, via_mcp in ((0, False), (7, True), (14, False)):
        if via_mcp:
            chunk = _call(
                gateway.port,
                "stg_v1_artifact_read",
                {"artifact_id": gateway.artifact_id, "offset": offset, "length": 7},
                OBSERVE,
            )["data"]
        else:
            chunk = _rest(
                gateway,
                "get",
                f"/v1/artifacts/{gateway.artifact_id}/chunks?offset={offset}&length=7",
                None,
                OBSERVE,
            )[1]["data"]
        assert chunk["sha256"] == whole_sha
        assert chunk["bytes"] == min(7, len(ARTIFACT_BYTES) - offset)
        reassembled += base64.b64decode(chunk["base64"])
    assert reassembled == ARTIFACT_BYTES
    assert hashlib.sha256(reassembled).hexdigest() == whole_sha


def test_negative_offset_serves_head_bytes_on_both_transports(
    gateway: SimpleNamespace,
) -> None:
    """Final-fix-wave parity edge: a negative artifact offset is floored at
    0 BY THE SEAM (operations.artifact_read), so both adapters serve the
    head bytes by construction — REST's own clamp is now redundant defense,
    and MCP (which passed negatives into Python slicing) no longer serves
    wrong-window bytes from the tail."""
    _, rest_json = _rest(
        gateway,
        "get",
        f"/v1/artifacts/{gateway.artifact_id}/chunks?offset=-5&length=64",
        None,
        OBSERVE,
    )
    mcp_json = _call(
        gateway.port,
        "stg_v1_artifact_read",
        {"artifact_id": gateway.artifact_id, "offset": -5, "length": 64},
        OBSERVE,
    )
    assert rest_json["ok"] is True and mcp_json["ok"] is True
    assert mcp_json["data"] == rest_json["data"]
    head = rest_json["data"]
    assert head["offset"] == 0  # floored, not sliced from the tail
    assert head["bytes"] == len(ARTIFACT_BYTES)
    assert head["eof"] is True
    assert base64.b64decode(head["base64"]) == ARTIFACT_BYTES  # the HEAD bytes


# --- admin pins (D2 + stored-generation fence + not_ready) ---------------------


def test_artifact_offset_letter_beyond_size_fails_at_size_serves_empty(
    gateway: SimpleNamespace,
) -> None:
    """D11 closed (WP08 Task 5, ALIGNED to the contract §8 letter): "At EOF
    an offset equal to size yields zero bytes; offsets beyond size fail."
    At-size is the pinned zero-byte eof chunk on both transports; beyond-size
    is ``invalid_request`` on both — the seam is the single construction
    site, so the failure envelopes are identical by construction and are
    compared end to end here."""
    size = len(ARTIFACT_BYTES)
    status, rest_json = _rest(
        gateway,
        "get",
        f"/v1/artifacts/{gateway.artifact_id}/chunks?offset={size}&length=64",
        None,
        OBSERVE,
    )
    assert status == 200, rest_json
    assert rest_json["data"]["bytes"] == 0
    assert rest_json["data"]["eof"] is True
    mcp_json = _call(
        gateway.port,
        "stg_v1_artifact_read",
        {"artifact_id": gateway.artifact_id, "offset": size, "length": 64},
        OBSERVE,
    )
    assert mcp_json["data"] == rest_json["data"]

    status, rest_json = _rest(
        gateway,
        "get",
        f"/v1/artifacts/{gateway.artifact_id}/chunks?offset={size + 1}&length=64",
        None,
        OBSERVE,
    )
    assert status == 400, rest_json
    assert rest_json["error"]["code"] == "invalid_request"
    mcp_json = _call(
        gateway.port,
        "stg_v1_artifact_read",
        {"artifact_id": gateway.artifact_id, "offset": size + 1, "length": 64},
        OBSERVE,
    )
    assert mcp_json["ok"] is False, mcp_json
    assert mcp_json["error"]["code"] == rest_json["error"]["code"]
    assert mcp_json["error"]["message"] == rest_json["error"]["message"]


def test_change_apply_approver_token_end_to_end(gateway: SimpleNamespace) -> None:
    """D2 CATALOG-AMENDMENT pin (REST-only surface): the catalog body omits
    ``approver_token`` yet REST forwards it as a seam kwarg — apply without
    the detached token fails closed; apply with it succeeds end-to-end."""
    submitted = gateway.client.post(
        "/v1/admin/changes",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-notoken",
            "bench_id": BENCH,
            "kind": "trip_reset",
            "target_ref": TARGET_REF,
            "expected_generation": 1,
            "reason": "pin: fail closed without approver token",
        },
    )
    assert submitted.status_code == 201, submitted.text
    change_id = submitted.json()["data"]["change_id"]

    denied = gateway.client.post(
        f"/v1/admin/changes/{change_id}/apply",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-notoken-apply",
            "expected_generation": 1,
            "approval_ref": _store_approval(gateway.content, change_id, 1),
        },
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "forbidden"
    assert "missing_token" in denied.json()["error"]["message"]
    _, failed = _rest(gateway, "get", f"/v1/admin/changes/{change_id}", None, ADMIN)
    assert failed["data"]["state"] == "failed"

    ok = gateway.client.post(
        "/v1/admin/changes",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-apply-ok",
            "bench_id": BENCH,
            "kind": "trip_reset",
            "target_ref": TARGET_REF,
            "expected_generation": 1,
            "reason": "pin: apply with detached approver token",
        },
    )
    assert ok.status_code == 201, ok.text
    applied_change = ok.json()["data"]["change_id"]
    applied = gateway.client.post(
        f"/v1/admin/changes/{applied_change}/apply",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-apply-ok-apply",
            "expected_generation": 1,
            "approval_ref": _store_approval(gateway.content, applied_change, 1),
            "approver_token": APPROVER_TOKEN,
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["state"] == "applied"


def test_change_apply_stored_generation_fence(gateway: SimpleNamespace) -> None:
    """Ledger item 5: right token, wrong stored generation — the change record
    was proposed at generation 2; apply presenting 3 (with a matching approval
    binding) is a conflict and records ``failed``, not a silent apply."""
    submitted = gateway.client.post(
        "/v1/admin/changes",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-stale",
            "bench_id": BENCH,
            "kind": "trip_reset",
            "target_ref": TARGET_REF,
            "expected_generation": 2,  # stored generation (post first apply)
            "reason": "pin: stored-generation fence",
        },
    )
    assert submitted.status_code == 201, submitted.text
    change_id = submitted.json()["data"]["change_id"]
    conflicted = gateway.client.post(
        f"/v1/admin/changes/{change_id}/apply",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-stale-apply",
            "expected_generation": 3,  # approval binds 3 so verification passes
            "approval_ref": _store_approval(gateway.content, change_id, 3),
            "approver_token": APPROVER_TOKEN,
        },
    )
    assert conflicted.status_code == 409, conflicted.text
    assert conflicted.json()["error"]["code"] == "conflict"
    assert "proposed at generation 2" in conflicted.json()["error"]["message"]
    _, record = _rest(gateway, "get", f"/v1/admin/changes/{change_id}", None, ADMIN)
    assert record["data"]["state"] == "failed"
    assert record["data"]["reasons"]


def test_not_ready_configuration_activation_under_live_lease(
    gateway: SimpleNamespace,
) -> None:
    """not_ready pin (REST-only admin surface): the idle boundary refuses a
    configuration_activation while the renew-parity lease is still live."""
    submitted = gateway.client.post(
        "/v1/admin/changes",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-notready",
            "bench_id": BENCH,
            "kind": "configuration_activation",
            "target_ref": TARGET_REF,
            "expected_generation": 2,
            "reason": "pin: activation under live lease",
        },
    )
    assert submitted.status_code == 201, submitted.text
    change_id = submitted.json()["data"]["change_id"]
    refused = gateway.client.post(
        f"/v1/admin/changes/{change_id}/apply",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-notready-apply",
            "expected_generation": 2,
            "approval_ref": _store_approval(gateway.content, change_id, 2),
            "approver_token": APPROVER_TOKEN,
        },
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "not_ready"
    assert "live lease" in refused.json()["error"]["message"]
    _, record = _rest(gateway, "get", f"/v1/admin/changes/{change_id}", None, ADMIN)
    assert record["data"]["state"] == "failed"


def test_approver_token_requires_gateway_admin_audience(
    gateway: SimpleNamespace,
) -> None:
    """D7 twist on the D2 flow: an stg-audience admin token as
    ``approver_token`` fails closed 403 — approval authentication validates
    against the detached ``gateway-admin`` audience, so gateway scope alone
    authorizes nothing; the change records ``failed``."""
    submitted = gateway.client.post(
        "/v1/admin/changes",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-approver-audience",
            "bench_id": BENCH,
            "kind": "trip_reset",
            "target_ref": TARGET_REF,
            "expected_generation": 2,
            "reason": "pin: approver token must be gateway-admin audience",
        },
    )
    assert submitted.status_code == 201, submitted.text
    change_id = submitted.json()["data"]["change_id"]
    refused = gateway.client.post(
        f"/v1/admin/changes/{change_id}/apply",
        headers=_bearer(ADMIN),
        json={
            "request_id": "req-pin-approver-audience-apply",
            "expected_generation": 2,
            "approval_ref": _store_approval(gateway.content, change_id, 2),
            "approver_token": ADMIN,  # stg audience + admin scope: not an approver
        },
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "forbidden"
    assert "wrong_audience" in refused.json()["error"]["message"]
    _, record = _rest(gateway, "get", f"/v1/admin/changes/{change_id}", None, ADMIN)
    assert record["data"]["state"] == "failed"
