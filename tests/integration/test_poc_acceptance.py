"""WP09 Task 4: PoC acceptance — the PRD §3 demonstration journey, live.

One suite drives the journey a PRD reader would recognise over the one
composed application (``create_app``: bootstrap admission, REST ``/v1``,
MCP ``/mcp``, run worker, sim plugins, wired registry session) on a
loopback uvicorn port — no TestClient, no seam doubles. This task lands
the scaffold (fixtures) and steps 1–3 (discover → admit → select); the
run/fault/reuse legs (§3 steps 4–7) land in Tasks 5–6 of this suite.

Sketch-risk deviations from the task brief (real surface wins):
- There is no ``GET /v1/registry`` — interface 1.1.1 has no
  registry-discovery operation. Discovery is the resolver surface the app
  itself routes (``build_registry_session`` over ``fixtures/registry``)
  plus the wire's admitted inventory: ``GET /v1/benches/{bench}/devices``
  carrying the ``otdp.dc_psu/1.0.0`` profile (the sketch's
  ``p["profile"] == "dc_psu"``).
- "Admit exact releases" is the two-phase admin change surface
  (``POST /v1/admin/changes`` + ``.../apply``), REST-only per the catalog;
  the approval document is stored through the ContentStore (operator-side
  artifact — there is no wire document-upload operation; the pattern suite
  ``test_registry_changes.py`` stages it the same way).
- "SIMULATION visibly identified" has no boolean on the wire: the visible
  markers are the commissioning document's ``simulator-only`` evidence
  limitation and its "Not hardware-qualified." description, read back
  byte-pinned through ``GET /v1/documents/{sha256}``.
- ``journey_discover_admit_select(app)`` gains a ``tokens`` argument
  (the principals live in the ``poc_tokens`` fixture; re-issuing inside
  the helper would fork the issuer state).
- Only ONE root goes through the live admission: the resolver's
  strictly-advancing high-water fence (rollback protection) refuses a
  second resolve of the shared profile package at the same status
  sequence, so one session admits one dependency-overlapping family —
  the psu closure, which already carries the profile package plus both
  descriptor and implementation releases (three exact releases).
  Discovery covers both implementations over fresh per-read views.

PRD row → evidence map (the coverage contract for the whole suite; the
journey assertion lands here, the named suite carries the deep behaviour —
rows naming Task 5/6 legs state where that evidence lands, by design):
  PRD-01 reproducible setup ..... journey boots from the fixture lattice
      over ``create_app``; clean-install legs = tests/integration/
      test_clean_install.py (wheel-proven); Linux build legs = CI
  PRD-02 package reuse .......... journey reuse leg (Task 6); deep =
      tests/integration/test_registry_reuse.py (second-install digest
      identity)
  PRD-03 authenticated admission .. journey: the live admit path itself
      (resolver closure → change_submit/change_apply below); fault
      vectors deep = test_registry_reuse.py + test_registry_changes.py
  PRD-04 real plugin ABI ........ journey: both sim plugins execute via
      the app's published factory/host services (run legs, Tasks 5–6);
      deep = tests/contract/test_sim_plugins.py + test_host_abi.py
  PRD-05 ownership/admission .... journey run starts on the admitted
      bench; stale generation start rejected (run legs, Tasks 5–6);
      deep = tests/integration/test_takeover.py + test_event_recovery.py
  PRD-06 bounded procedures ..... the fixture procedure executes all its
      step kinds (run legs, Tasks 5–6); deep = tests/integration/
      test_procedures.py
  PRD-07 run/request identity ... REST start + MCP retrieve = one run
      (Task 5); retry legs (Task 6); deep = test_event_recovery.py +
      tests/unit/test_seam_control.py
  PRD-08 protection/recovery .... trip + restart legs (Task 6); deep =
      test_event_recovery.py + tests/contract/test_fault_matrix.py
  PRD-09 measurement honesty .... assertions + final safe condition
      verified (Task 5); stale/wrong-unit deep = test_procedures.py
  PRD-10 parity/access .......... the same admitted inventory reads
      identically over both transports (discovery leg, here); the same
      run over both (Task 5); full parity =
      tests/integration/test_interface_parity.py
  PRD-11 network independence .. registry-loss leg (Task 6) if
      uncovered; deep = test_event_recovery.py
  PRD-12 controlled admin ....... one staged admission at a safe idle
      boundary in-journey (HERE); deep = tests/unit/test_seam_admin.py
      + tests/integration/test_registry_changes.py
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.bootstrap import RegistrySession, build_registry_session
from benchweave.interfaces.identity import issue
from benchweave.registry.resolver import ResolvedClosure
from benchweave.state.store import Store

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "fixtures" / "registry"
FIXTURES = REPO_ROOT / "fixtures" / "execution"

SECRET = b"wp09-task-four-secret"
NOW_ISO = "2026-09-14T00:00:00Z"
NOW_EPOCH = 1_800_000_000
# The registry clock, same posture as test_registry_changes: inside every
# fixture status's validity window (expires 2027-09-11, not future-dated).
NOW_NS = int(datetime(2026, 9, 14, tzinfo=UTC).timestamp() * 1_000_000_000)

LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}

BENCH = "sim-bench"
DC_PSU_PROFILE = "otdp.dc_psu/1.0.0"
SIM_PSU = "benchweave/sim-psu"
SIM_CONTROLLER = "benchweave/sim-controller"
PROFILE_PACKAGE = "benchweave/dc-psu-profile"
PACKAGE_VERSION = "1.0.0"
ORIGIN = "origin-main"

BINDING_SHA = hashlib.sha256((FIXTURES / "run-binding.json").read_bytes()).hexdigest()
#: The binding document's own request id (§5) — the run legs' dedup key.
BINDING_REF: dict[str, str] = {
    "id": "req-voltage-check-1",
    "version": "1.0.0",
    "sha256": BINDING_SHA,
}


# --- fixtures' shared types ----------------------------------------------------


@dataclass(frozen=True)
class Tokens:
    """One bearer per journey principal, all from the local test issuer."""

    #: observe-tier engineer (wire reads on both transports).
    observer: str
    #: control-tier operator (the run legs' principal).
    operator: str
    #: admin-tier applier (the change surface's submitting principal).
    admin: str
    #: The bench owner's DETACHED approval token (audience ``gateway-admin``)
    #: — the independent authentication change_apply demands; never rides
    #: the Authorization header.
    approver: str
    #: The approval documents' ``approver_principal`` (matches the token).
    approver_principal: str


@dataclass
class Gateway:
    """The live composed app: loopback base URL, handles, shutdown parts."""

    client: httpx.Client
    base: str
    port: int
    store: Store
    content: ContentStore
    session: RegistrySession
    server: uvicorn.Server
    thread: threading.Thread


@dataclass(frozen=True)
class Admitted:
    """What the journey's first three steps leave behind for Tasks 5–6."""

    bench_id: str
    #: The bench generation AFTER the admissions — run legs must present
    #: this as ``expected_generation`` (each apply advances it).
    generation: int
    #: The wire's device ids (the admitted descriptor ids, wire order).
    device_ids: tuple[str, ...]
    #: The §5 binding ref the run legs start runs with.
    binding_ref: dict[str, str]
    procedure_ref: dict[str, str]
    policy_ref: dict[str, str]
    commissioning_ref: dict[str, str]
    #: package_id -> manifest sha256 for the admitted root release.
    package_pins: dict[str, str]
    #: Every manifest digest the admission cached (the psu closure).
    manifest_sha256s: tuple[str, ...]
    change_ids: tuple[str, ...]
    lock_sha256: str
    #: The wire-visible simulation markers (``simulator-only``).
    simulated_limitations: tuple[str, ...]


class _Rest:
    """httpx client with the journey principal's bearer injected."""

    _TOKENS = {
        "observer": 0,
        "operator": 1,
        "admin": 2,
    }

    def __init__(self, client: httpx.Client, tokens: Tokens) -> None:
        self._client = client
        self._bearers = [tokens.observer, tokens.operator, tokens.admin]

    def _headers(self, principal: str) -> dict[str, str]:
        index = self._TOKENS.get(principal)
        assert index is not None, f"unknown journey principal {principal!r}"
        return {"Authorization": f"Bearer {self._bearers[index]}"}

    def get(
        self,
        path: str,
        *,
        principal: str = "observer",
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return self._client.get(path, headers=self._headers(principal), params=params)

    def post(
        self, path: str, *, json: dict[str, Any], principal: str = "operator"
    ) -> httpx.Response:
        return self._client.post(path, headers=self._headers(principal), json=json)


class _Mcp:
    """MCP 2026-07-28 loopback client over the live app (task-8 idiom).

    One initialized session (observer token at the transport); each
    ``call`` carries the named principal's bearer — the seam enforces the
    tier per tool.
    """

    def __init__(self, url: str, tokens: Tokens) -> None:
        self._url = url
        self._tokens = tokens
        self._session = _mcp_initialize(url, tokens.observer)

    def call(
        self, name: str, arguments: dict[str, Any], *, principal: str = "observer"
    ) -> dict[str, Any]:
        token = {
            "observer": self._tokens.observer,
            "operator": self._tokens.operator,
            "admin": self._tokens.admin,
        }.get(principal)
        assert token is not None, f"unknown journey principal {principal!r}"
        status, body, _ = _mcp_post(
            self._url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            {"Mcp-Session-Id": self._session, "Authorization": f"Bearer {token}"},
        )
        assert status == 200, f"{name} rejected: {status} {body}"
        assert body is not None, f"{name} returned no body"
        return _call_envelope(body)


def _mcp_post(
    url: str, payload: dict[str, Any], extra_headers: dict[str, str]
) -> tuple[int, dict[str, Any] | None, dict[str, str]]:
    """POST one JSON-RPC frame; parse JSON or SSE framing (task-8 idiom)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        **extra_headers,
    }
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


def _mcp_initialize(url: str, token: str) -> str:
    status, body, headers = _mcp_post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "poc-acceptance", "version": "0"},
            },
        },
        {"Authorization": f"Bearer {token}"},
    )
    assert status == 200, f"initialize rejected: {status} {body}"
    assert body is not None and "result" in body, f"initialize failed: {body}"
    session = headers.get("mcp-session-id")
    assert session is not None, "no session id on initialize"
    _mcp_post(
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


# --- fixtures ------------------------------------------------------------------


@pytest.fixture(scope="module")
def poc_tokens() -> Tokens:
    """Local-issuer bearers for the journey's three principals plus the
    bench owner's detached gateway-admin approval token."""
    return Tokens(
        observer=issue(
            SECRET,
            principal="poc-observer",
            audience="stg",
            scopes=["stg:observe"],
            expires_at=NOW_EPOCH + 3600,
        ),
        operator=issue(
            SECRET,
            principal="poc-operator",
            audience="stg",
            scopes=["stg:control"],
            expires_at=NOW_EPOCH + 3600,
        ),
        admin=issue(
            SECRET,
            principal="poc-admin",
            audience="stg",
            scopes=["stg:admin"],
            expires_at=NOW_EPOCH + 3600,
        ),
        approver=issue(
            SECRET,
            principal="poc-bench-owner",
            audience="gateway-admin",
            scopes=["stg:admin"],
            expires_at=NOW_EPOCH + 3600,
        ),
        approver_principal="poc-bench-owner",
    )


@pytest.fixture(scope="module")
def poc_app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Gateway]:
    """The composed gateway, live: registry session wired, loopback port.

    The stand-up is the ``test_event_recovery`` in-process variant
    (``create_app`` on a file-backed store, uvicorn on an ephemeral port)
    with one addition the journey needs: ``build_registry_session`` over
    the committed fixture registry, so the admin change surface can admit
    real packages live.
    """
    work = tmp_path_factory.mktemp("poc-acceptance")
    store = Store.open(work / "state.db", check_same_thread=False)
    content = ContentStore(store)
    session = build_registry_session(REGISTRY, work / "registry", now_ns=lambda: NOW_NS)
    app = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=LIMITS,
        gateway_id="gw-poc-acceptance",
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
        registry_session=session,
    )
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
    port = int(servers[0].sockets[0].getsockname()[1])
    base = f"http://127.0.0.1:{port}"
    yield Gateway(
        client=httpx.Client(base_url=base, timeout=30.0),
        base=base,
        port=port,
        store=store,
        content=content,
        session=session,
        server=server,
        thread=thread,
    )
    server.should_exit = True
    thread.join(timeout=10.0)
    store.close()


@pytest.fixture(scope="module")
def poc_rest(poc_app: Gateway, poc_tokens: Tokens) -> _Rest:
    """Bearer-injecting REST client over the live gateway."""
    return _Rest(poc_app.client, poc_tokens)


@pytest.fixture(scope="module")
def poc_mcp(poc_app: Gateway, poc_tokens: Tokens) -> _Mcp:
    """Initialized MCP client over the live gateway's ``/mcp`` mount."""
    return _Mcp(f"{poc_app.base}/mcp", poc_tokens)


@pytest.fixture(scope="module")
def journey_admitted(poc_app: Gateway, poc_tokens: Tokens) -> Admitted:
    """The journey's steps 1–3, run once: discovered, admitted, selected.

    Module-scoped on purpose — the admission advances the bench
    generation, and Tasks 5–6's run legs must read ``generation`` (never
    assume 1) from the returned :class:`Admitted`.
    """
    return journey_discover_admit_select(poc_app, poc_tokens)


# --- the journey helper (Tasks 5–6 consume its result) --------------------------


def journey_discover_admit_select(app: Gateway, tokens: Tokens) -> Admitted:
    """PRD §3 steps 1–3 over the live gateway; returns the admitted state.

    Step 1 — discovery: the resolver over the app's curated registry
    resolves both simulated roots (each read over a FRESH high-water view —
    discovery must not spend the session's rollback fence); each closure
    carries the shared profile package (the curated registry's shape: one
    profile, two implementations). Step 2 — admission: the psu closure —
    three exact releases, profile package included — goes in as one
    digest-pinned ``package_admission`` change through the wire's
    two-phase admin surface, applied at a safe idle boundary with the
    bench owner's detached approval. (The second root cannot ride the same
    session: both closures share the profile package and every fixture
    status sits at sequence 1, and the resolver's strictly-advancing
    high-water fence refuses the revisit — one admission per
    dependency-overlapping family per session, the rollback fence doing
    its job.) Step 3 — selection: the commissioning document pins the
    versioned procedure and policy, and simulation is visibly identified
    (``simulator-only``).
    """
    rest = _Rest(app.client, tokens)

    # Step 1: discover the curated registry — profile package + both sims.
    # Fresh high-water per read: resolve WRITES the map it is given, and the
    # session's shared map must stay unspent for the live admission below.
    closures: dict[str, ResolvedClosure] = {
        root: app.session.resolver.resolve(
            ORIGIN, root, PACKAGE_VERSION, now_ns=NOW_NS, high_water={}
        )
        for root in (SIM_PSU, SIM_CONTROLLER)
    }
    package_pins: dict[str, str] = {}
    for root, closure in closures.items():
        package_ids = {release.package_id for release in closure.releases}
        assert PROFILE_PACKAGE in package_ids, f"{root} closure lost the profile package"
        assert root in package_ids
        root_release = next(r for r in closure.releases if r.package_id == root)
        package_pins[root] = root_release.manifest_sha256
    # The psu closure is the three exact releases the admission pins below.
    admitted_closure = closures[SIM_PSU]
    manifest_sha256s = {
        release.manifest_sha256 for release in admitted_closure.releases
    }
    assert len(manifest_sha256s) == 3

    # Step 2: admit exact releases — two-phase, staged, independently
    # approved, at a safe idle boundary (the bench holds no lease).
    generation = 1
    submitted = rest.post(
        "/v1/admin/changes",
        principal="admin",
        json={
            "request_id": "req-poc-admit-sim-psu",
            "bench_id": BENCH,
            "kind": "package_admission",
            "target_ref": {
                "id": SIM_PSU,
                "version": PACKAGE_VERSION,
                "sha256": package_pins[SIM_PSU],
            },
            "expected_generation": generation,
            "reason": "poc journey admission of exact releases",
        },
    )
    assert submitted.status_code == 201, submitted.text
    assert submitted.json()["data"]["state"] == "proposed"
    change_id = str(submitted.json()["data"]["change_id"])

    approval_ref = _store_approval(app.content, change_id, generation, tokens)
    applied = rest.post(
        f"/v1/admin/changes/{change_id}/apply",
        principal="admin",
        json={
            "request_id": "req-poc-apply-sim-psu",
            "expected_generation": generation,
            "approval_ref": approval_ref,
            "approver_token": tokens.approver,
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["state"] == "applied"
    generation += 1

    # The admission really happened: the lock root is the exact pin and
    # every closure member sits in the content-addressed cache.
    lock_bytes = Path(app.session.lock_path).read_bytes()
    lock = json.loads(lock_bytes)
    assert {root["package_id"]: root["manifest_sha256"] for root in lock["roots"]} == {
        SIM_PSU: package_pins[SIM_PSU]
    }
    for sha in manifest_sha256s:
        assert (app.session.cache_root / sha).is_dir(), f"{sha} never cached"

    bench = rest.get(f"/v1/benches/{BENCH}").json()["data"]
    assert bench["generation"] == generation

    # The wire's admitted inventory (discovery, wire side): the devices the
    # startup lattice admitted, keyed by their DESCRIPTOR ids — the PSU
    # device is the one carrying the dc_psu profile.
    devices = rest.get(
        f"/v1/benches/{BENCH}/devices", params={"limit": 100}
    ).json()["data"]["items"]
    device_ids = tuple(str(device["device_id"]) for device in devices)
    psu_devices = [
        device for device in devices if device["profiles"] == [DC_PSU_PROFILE]
    ]
    assert len(psu_devices) == 1, devices

    # Step 3: select the versioned fixture/policy/procedure — the
    # commissioning document (the bench's stored configuration) pins all
    # three, and simulation is visible on its face.
    commissioning_ref = dict(bench["configuration"])
    document = rest.get(f"/v1/documents/{commissioning_ref['sha256']}").json()["data"]
    commissioning = dict(document["content"])
    procedure_ref = dict(commissioning["procedure_refs"][0])
    policy_ref = dict(commissioning["policy"])
    limitations = tuple(
        limitation
        for evidence in commissioning.get("evidence", [])
        for limitation in evidence.get("limitations", [])
    )
    assert "simulator-only" in limitations
    assert "simulator" in str(commissioning.get("description", "")).lower()

    return Admitted(
        bench_id=BENCH,
        generation=generation,
        device_ids=device_ids,
        binding_ref=dict(BINDING_REF),
        procedure_ref=procedure_ref,
        policy_ref=policy_ref,
        commissioning_ref=commissioning_ref,
        package_pins={SIM_PSU: package_pins[SIM_PSU]},
        manifest_sha256s=tuple(sorted(manifest_sha256s)),
        change_ids=(change_id,),
        lock_sha256=hashlib.sha256(lock_bytes).hexdigest(),
        simulated_limitations=limitations,
    )


def _store_approval(
    content: ContentStore, change_id: str, generation: int, tokens: Tokens
) -> dict[str, str]:
    """Store the approval document binding one change at one generation.

    The bench owner's side of the two-phase protocol: a sha-pinned
    document naming the exact change and generation. The matching detached
    token (``tokens.approver``) authenticates it at apply time — the
    applier's admin identity authorizes nothing (PRD-12).
    """
    body = {
        "change_id": change_id,
        "expected_generation": generation,
        "approver_principal": tokens.approver_principal,
        "policy_version": "1",
    }
    raw = json.dumps(body, sort_keys=True).encode()
    sha = hashlib.sha256(raw).hexdigest()
    content.put_document(raw, sha, body, "urn:stg:approval", NOW_ISO)
    return {"id": f"approval-{change_id}", "version": "1", "sha256": sha}


# --- steps 1–3 (this task's journey test) ---------------------------------------


def test_journey_discover_admit_select(
    poc_rest: _Rest, poc_mcp: _Mcp, journey_admitted: Admitted
) -> None:
    """PRD §3 steps 1–3, live: discover → admit exact releases → select.

    Step 1 — the curated registry carries the profile package and both
    simulated implementations; the wire shows the dc_psu profile on the
    PSU device over BOTH transports. Step 2 — the psu closure (three
    exact releases, profile package included) is admitted through the
    two-phase admin change surface (proposed → applied at a safe idle
    boundary, generation advancing with the change). Step 3 — the
    versioned procedure/policy pair is selected through the
    commissioning document, and simulation is visibly identified on the
    wire (the ``simulator-only`` limitation).
    """
    # Step 1 (wire parity leg, PRD-10 seed): same inventory both transports.
    rest_devices = poc_rest.get(
        f"/v1/benches/{journey_admitted.bench_id}/devices", params={"limit": 100}
    ).json()["data"]["items"]
    mcp_devices = poc_mcp.call(
        "stg_v1_device_list",
        {"bench_id": journey_admitted.bench_id, "limit": 100, "cursor": None},
    )["data"]["items"]
    assert [d["device_id"] for d in rest_devices] == list(journey_admitted.device_ids)
    assert rest_devices == mcp_devices
    psu = next(d for d in rest_devices if d["profiles"] == [DC_PSU_PROFILE])
    assert psu is not None

    # Step 2 (admit leg): the change stands applied; the bench advanced.
    bench = poc_rest.get(f"/v1/benches/{journey_admitted.bench_id}").json()["data"]
    assert bench["generation"] == journey_admitted.generation
    for change_id in journey_admitted.change_ids:
        change = poc_rest.get(f"/v1/admin/changes/{change_id}", principal="admin").json()[
            "data"
        ]
        assert change["state"] == "applied"

    # Step 3 (select leg): versioned procedure + policy; simulation visible.
    assert journey_admitted.procedure_ref["id"] == "voltage-check"
    assert journey_admitted.procedure_ref["version"] == "1.0.0"
    assert journey_admitted.policy_ref["id"] == "sim-policy"
    assert journey_admitted.policy_ref["version"] == "1.0.0"
    assert journey_admitted.simulated_limitations == ("simulator-only",)
