"""PoC acceptance — the PRD §3 demonstration journey, live.

One suite drives the journey a PRD reader would recognise over the one
composed application (``create_app``: bootstrap admission, REST ``/v1``,
MCP ``/mcp``, run worker, sim plugins, wired registry session) on a
loopback uvicorn port — no TestClient, no seam doubles. Tasks 4–5 landed
the scaffold (fixtures), steps 1–3 (discover → admit → select) and steps
4–5 (the run journey: start via REST, retrieve via MCP, the report); the
fault legs and the second-install reuse leg (§3 steps 6–7) complete the
suite.

Sketch-risk deviations from the task brief (real surface wins):
- There is no ``GET /v1/registry`` — interface 0.1.0 has no
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
- The sketch's "supply disabled" final-state element has no separate
  wire moment to assert: a passed run's safe transition disables the
  supply and the verified final safe condition
  (``safe_state == "verified"``) subsumes it.
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
      bench; stale generation start rejected after the in-journey admin
      change (run legs, HERE); deep = tests/integration/test_takeover.py
      + test_event_recovery.py
  PRD-06 bounded procedures ..... the fixture procedure executes all its
      step kinds (run legs, Tasks 5–6); deep = tests/integration/
      test_procedures.py
  PRD-07 run/request identity ... REST start + MCP retrieve = one run
      (run leg, HERE); retry legs (Task 6); deep = test_event_recovery.py
      + tests/unit/test_seam_control.py
  PRD-08 protection/recovery .... trip + restart legs (Task 6); deep =
      test_event_recovery.py + tests/contract/test_fault_matrix.py
  PRD-09 measurement honesty .... assertions + final safe condition
      verified (run leg, HERE); stale/wrong-unit deep = test_procedures.py
  PRD-10 parity/access .......... the same admitted inventory reads
      identically over both transports (discovery leg, here); the same
      run over both (run leg, HERE); full parity =
      tests/integration/test_interface_parity.py
  PRD-11 network independence .. registry-loss leg (Task 6) if
      uncovered; deep = test_event_recovery.py
  PRD-12 controlled admin ....... one staged admission at a safe idle
      boundary in-journey (HERE), then one staged ``trip_reset`` at the
      safe idle boundary after the run lands terminal (run leg, HERE —
      the registry kinds cannot re-apply in this session: Task 4's
      admission spent the resolver's high-water map); deep =
      tests/unit/test_seam_admin.py + tests/integration/test_registry_changes.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from benchweave.cli.report import build_report, render_markdown
from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.bootstrap import (
    RegistrySession,
    admit_startup_bench,
    build_registry_session,
)
from benchweave.interfaces.identity import issue
from benchweave.interfaces.operations import scoped_request_key
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

#: The restart leg's crash state (§3 step 6d): a PREVIOUS process's
#: mid-body kill under the journey operator's principal, staged through
#: the real Store APIs before the gateway boots (the ``poc_app`` fixture),
#: so the journey gateway's own lifespan is the recovery boot. A second
#: boot over a live gateway's database is impossible by design — the
#: flock daemon-hold refuses it (state/hold.py) — which is exactly why
#: the staged idiom lives in the stand-up rather than a second app.
RESTART_RUN_ID = "run-poc-fault-restart"
RESTART_REQUEST_ID = "req-poc-fault-restart"
RESTART_REF: dict[str, str] = {
    "id": RESTART_REQUEST_ID,
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


@dataclass(frozen=True)
class TerminalRecord:
    """What one driven run leaves behind (§3 steps 4–5; Tasks 6–9 consume).

    Wire-shaped by design: every field is what the transports serve, so
    fault/volume/timing legs can assert on it without store access (the
    durable record document itself is store-side only — see
    :func:`journey_run`).
    """

    run_id: str
    bench_id: str
    #: The §9 request id the run was filed under (the binding's own id).
    request_id: str
    state: str
    outcome: str | None
    #: PRD-09's final safe condition, wire-named (``verified``/``unknown``).
    safe_state: str | None
    #: The closed ``{id, version, sha256}`` terminal-record ref; ``None``
    #: on an uncertain terminal (``outcome_unknown``/``interrupted``),
    #: which truthfully carries no record.
    terminal_record: dict[str, str] | None
    #: The evidence-bearing run record's digest(s) — the ref's sha256.
    evidence_digests: tuple[str, ...]
    #: The run id as MCP read it in flight — identity across transports.
    mcp_run_id: str
    #: Bench events on the stream when the drive finished (paged whole).
    events_observed: int


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

    One initialized session PER PRINCIPAL, created lazily on first use:
    fastmcp binds a session to the credential that created it, so the
    tier a call runs under is chosen by which session it enters through
    (per-call bearer switching on one session is impossible on this
    transport — see the ``__init__`` note for the live proof).
    """

    def __init__(self, url: str, tokens: Tokens) -> None:
        self._url = url
        self._tokens = tokens
        # One session PER PRINCIPAL, lazily initialized: fastmcp binds a
        # session to the credential that created it and answers a call
        # riding a different bearer with a transport-level 404 ("credential
        # does not match"), so per-call principal switching on one session
        # is impossible — the tier is chosen by which session the call
        # enters through (proven live in Task 5's run_find leg).
        self._sessions: dict[str, str] = {"observer": _mcp_initialize(url, tokens.observer)}

    def _session_for(self, principal: str) -> tuple[str, str]:
        """The principal's (session id, bearer), initializing on first use."""
        token = {
            "observer": self._tokens.observer,
            "operator": self._tokens.operator,
            "admin": self._tokens.admin,
        }.get(principal)
        assert token is not None, f"unknown journey principal {principal!r}"
        if principal not in self._sessions:
            self._sessions[principal] = _mcp_initialize(self._url, token)
        return self._sessions[principal], token

    def call(
        self, name: str, arguments: dict[str, Any], *, principal: str = "observer"
    ) -> dict[str, Any]:
        session, token = self._session_for(principal)
        status, body, _ = _mcp_post(
            self._url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            {"Mcp-Session-Id": session, "Authorization": f"Bearer {token}"},
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
    real packages live. And one pre-boot block the restart leg needs: a
    previous process's crashed run is staged through the real Store APIs
    BEFORE the boot (the staged-crash idiom), so this gateway's lifespan
    runs its startup recovery over it — the journey gateway is itself a
    recovery boot (§3 step 6d asserts the honesty of that recovery).
    """
    work = tmp_path_factory.mktemp("poc-acceptance")
    db_path = work / "state.db"
    seed = Store.open(db_path, check_same_thread=False)
    seed_content = ContentStore(seed)
    admit_startup_bench(seed, seed_content, FIXTURES, now=NOW_ISO)
    _stage_crashed_run(seed, RESTART_RUN_ID, RESTART_REF, principal="poc-operator")
    seed.close()
    store = Store.open(db_path, check_same_thread=False)
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
    # Anti-fabrication pin: the inventory reports the descriptor's own
    # version (full-form descriptor_version), never a defaulted "1".
    assert psu_devices[0]["descriptor"]["version"] == "1.0.0", psu_devices[0]
    assert psu_devices[0]["descriptor"]["id"] == "dev.benchweave.sim-psu"

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


# --- the run drive (Task 5 produces; Tasks 6–9 consume) --------------------------


def _bench_events(rest: _Rest, bench_id: str) -> list[dict[str, Any]]:
    """The bench stream whole, cursor-paged, with an exhaustion guard.
    The exhaustion signal is an EMPTY PAGE, never an empty cursor — the
    events endpoint always returns a cursor (``after`` or the zero mark
    when there is nothing new), so a cursor-based termination would page
    forever (the Task-5 review minor: exit on exhaustion, and fail loudly
    if the 50-page cap is reached with events still coming instead of
    silently undercounting — the test_event_recovery paging idiom).
    """
    events: list[dict[str, Any]] = []
    after = ""
    for _ in range(50):
        page = rest.get(
            f"/v1/benches/{bench_id}/events", params={"after": after, "limit": 1000}
        ).json()["data"]
        page_events = list(page["events"])
        if not page_events:
            return events  # exhausted: the server has no more rows
        events.extend(page_events)
        after = str(page.get("cursor") or "")
    raise AssertionError(f"bench event stream for {bench_id} exceeded 50 pages")


def journey_run(
    app: Gateway,
    rest: _Rest,
    mcp: _Mcp,
    admitted: Admitted,
    *,
    request_id: str | None = None,
    binding_ref: dict[str, str] | None = None,
    expected_generation: int | None = None,
    timeout_s: float = 60.0,
    poll_s: float = 0.2,
) -> TerminalRecord:
    """PRD §3 step 4 over the live gateway — the full drive Tasks 6–9 reuse.

    ``benchweave.cli.demo``'s discipline, both transports: advisory
    ``run-checks`` preflight (the binding and its pinned documents are
    held; the reported generation is the canonical authority the fence
    reads), ``run_start`` via REST (the fixture lattice's valid binding —
    the binding document's own ``request_id`` is the §9 key), a §9
    ``run_find`` cross-check on BOTH transports plus ``run_get`` via MCP
    while the run is in flight (one run over both transports, PRD-07/10),
    then a bounded REST poll to terminal (the ``test_event_recovery``
    idiom) ending at the terminal record's wire ref and digest.

    Defaults come from ``admitted`` — ``Admitted.generation`` is the
    ``expected_generation`` (never a literal: each applied change advances
    it). Fault/volume/timing legs override ``request_id``/``binding_ref``/
    ``expected_generation`` for their own bindings; the drive asserts
    only transport invariants (202/200, §9 identity), never an outcome —
    the caller asserts what the outcome should be.

    ``app`` is the drive's gateway handle, kept for the fault legs that
    need store access; the drive itself is wire-only.
    """
    del app  # wire-only drive: the handle stays in the signature for Tasks 6–9
    ref = dict(binding_ref or admitted.binding_ref)
    rid = request_id if request_id is not None else str(ref["id"])
    generation = (
        expected_generation if expected_generation is not None else admitted.generation
    )

    # Advisory preflight: valid binding + the canonical generation the
    # fence reads. An Admitted carrying a stale generation fails HERE,
    # truthfully, instead of at the 409 below.
    preflight = rest.post(
        f"/v1/benches/{admitted.bench_id}/run-checks",
        principal="operator",
        json={"binding_ref": ref},
    ).json()["data"]
    assert preflight["valid"] is True, preflight
    assert preflight["generation"] == generation, (
        f"admitted generation {generation} is stale; the bench is at "
        f"{preflight['generation']} — re-run the admission journey"
    )

    started = rest.post(
        f"/v1/benches/{admitted.bench_id}/runs",
        principal="operator",
        json={
            "request_id": rid,
            "binding_ref": ref,
            "expected_generation": generation,
            "lease_id": None,
        },
    )
    assert started.status_code == 202, started.text
    run = started.json()["data"]
    assert run["state"] == "accepted"  # 202 semantics: read before submit
    run_id = str(run["run_id"])

    # §9 cross-check on both transports: the request resolves, for this
    # principal, to the run that was just accepted.
    found_rest = rest.get(f"/v1/requests/{rid}", principal="operator").json()["data"]
    assert str(found_rest["run_id"]) == run_id
    found_mcp = mcp.call(
        "stg_v1_run_find", {"request_id": rid}, principal="operator"
    )["data"]
    assert str(found_mcp["run_id"]) == run_id
    via_mcp = mcp.call("stg_v1_run_get", {"run_id": run_id})["data"]
    mcp_run_id = str(via_mcp["run_id"])
    assert mcp_run_id == run_id

    # Bounded poll to terminal.
    deadline = time.monotonic() + timeout_s
    while True:
        current = rest.get(f"/v1/runs/{run_id}").json()["data"]
        if current["state"] == "terminal":
            break
        assert time.monotonic() < deadline, (
            f"run {run_id} never reached terminal within {timeout_s:g}s "
            f"(last state: {current['state']!r})"
        )
        time.sleep(poll_s)

    # The terminal record ref + its digest (the demo's rule: an uncertain
    # terminal carries no record and no digest — never fabricated).
    terminal_ref = current.get("terminal_record")
    ref_dict = dict(terminal_ref) if isinstance(terminal_ref, dict) else None
    digests: tuple[str, ...] = (
        (str(ref_dict["sha256"]),) if ref_dict and ref_dict.get("sha256") else ()
    )

    # The bench stream, paged whole (cursor-bounded; one page holds it).
    events = len(_bench_events(rest, admitted.bench_id))

    return TerminalRecord(
        run_id=run_id,
        bench_id=admitted.bench_id,
        request_id=rid,
        state=str(current["state"]),
        outcome=current.get("outcome"),
        safe_state=current.get("safe_state"),
        terminal_record=ref_dict,
        evidence_digests=digests,
        mcp_run_id=mcp_run_id,
        events_observed=events,
    )


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
    assert journey_admitted.procedure_ref["version"] == "0.1.0"
    assert journey_admitted.policy_ref["id"] == "sim-policy"
    assert journey_admitted.policy_ref["version"] == "0.1.0"
    assert journey_admitted.simulated_limitations == ("simulator-only",)


# --- steps 4–5 (Task 5's run journey) -------------------------------------------


@pytest.fixture(scope="module")
def journey_terminal(
    poc_app: Gateway, poc_rest: _Rest, poc_mcp: _Mcp, journey_admitted: Admitted
) -> TerminalRecord:
    """§3 step 4, driven once: the terminal run both journey tests assert on."""
    return journey_run(poc_app, poc_rest, poc_mcp, journey_admitted)


def test_journey_run_rest_retrieve_mcp_report(
    poc_app: Gateway, poc_rest: _Rest, poc_mcp: _Mcp, journey_terminal: TerminalRecord
) -> None:
    """PRD §3 steps 4–5, live: one run over both transports, then the report.

    Step 4 — the run starts via REST (``POST /v1/benches/{bench}/runs``;
    the sketch's ``/v1/runs/start`` does not exist), the SAME run is
    retrieved via MCP (``stg_v1_run_find`` + ``stg_v1_run_get``) while
    in flight, and the terminal projection reads identically over both
    transports (PRD-07/10). The terminal outcome is ``passed`` and the
    final safe condition is verified — on the wire that is
    ``safe_state == "verified"`` (the sketch's
    ``final_safety.verified`` field does not exist; the interface
    schema's conditional pins ``passed ⇒ safe_state verified +
    terminal_record present``), and in the durable terminal record the
    same verdict with its evidence lattice (store-side read: the record
    document is deliberately not REST-servable). Step 5 — the report
    renders with visible SIMULATION identification. Report rendering is
    CLI-side (``benchweave report`` reads the store at rest and refuses
    while this gateway holds it), so the journey exercises the same pure
    model that command renders — ``build_report`` + ``render_markdown``
    over the app's own store/content handles — and asserts its
    wire-adjacent equivalents (SIMULATION labels, the run's row, every
    evidence digest present).
    """
    record = journey_terminal

    # One run over both transports (PRD-07/10): identity in flight (the
    # MCP retrieve inside the drive), and the terminal projection equal.
    assert record.mcp_run_id == record.run_id
    rest_final = poc_rest.get(f"/v1/runs/{record.run_id}").json()["data"]
    mcp_final = poc_mcp.call("stg_v1_run_get", {"run_id": record.run_id})["data"]
    assert mcp_final == rest_final

    # Terminal outcome + final safe condition (PRD-09), wire side.
    assert record.state == "terminal"
    assert record.outcome == "passed"
    assert record.safe_state == "verified"
    assert record.terminal_record is not None
    assert len(record.evidence_digests) == 1  # the record ref's digest
    for digest in record.evidence_digests:
        assert len(digest) == 64 and int(digest, 16) >= 0

    # The durable terminal record itself (store-side; never REST-served):
    # the same verdicts plus the evidence lattice the wire ref points at.
    durable = poc_app.store.get_run(record.run_id)
    assert durable is not None
    terminal = dict(durable["terminal"])
    assert terminal["run_id"] == record.run_id
    assert terminal["outcome"] == "passed"
    assert terminal["safe_state"] == "verified"  # PRD-09: the record's verdict
    assert terminal["principal_id"] == "poc-operator"
    assert terminal["evidence_refs"]  # assertions evaluated along the way
    for ref in terminal["evidence_refs"]:
        assert len(str(ref["sha256"])) == 64

    # The bench stream recorded the run's lifecycle (event evidence).
    assert record.events_observed > 0
    page = poc_rest.get(
        f"/v1/benches/{record.bench_id}/events", params={"after": "", "limit": 1000}
    ).json()["data"]
    kinds = [str(event["kind"]) for event in page["events"]]
    assert "run_changed" in kinds

    # Step 5: the report — SIMULATION visibly identified (the pure model
    # the at-rest ``benchweave report`` command renders; see docstring).
    report = build_report(
        poc_app.store, poc_app.content, bench_id=record.bench_id, now=NOW_ISO
    )
    assert report["simulation"] is True
    markdown = render_markdown(report)
    assert "SIMULATION" in markdown
    (run_row,) = [row for row in report["runs"] if row["id"] == record.run_id]
    assert run_row["state"] == "terminal"
    assert run_row["outcome"] == "passed"
    assert run_row["simulation"] is True
    assert report["missing_evidence"] == []  # every evidence digest present


def test_journey_admin_change_and_stale_generation_rejected(
    poc_app: Gateway,
    poc_rest: _Rest,
    poc_tokens: Tokens,
    journey_admitted: Admitted,
    journey_terminal: TerminalRecord,
) -> None:
    """PRD-12 then PRD-05, in-journey: controlled admin at the safe idle
    boundary, then the stale-generation fence.

    The staged admin change is a ``trip_reset`` pinning the bench's
    commissioning document — the one kind that can apply in this session:
    both registry kinds re-resolve their target closure through the
    resolver session's shared high-water map, which Task 4's admission
    already spent (the strictly-advancing rollback fence refuses the
    revisit), while ``trip_reset`` needs only a non-tripped bench. It is
    submitted under the admin principal, applied at the wire-visible safe
    idle boundary (the journey's run is terminal; the bench holds no live
    lease and no trip) with the bench owner's detached approval — Task
    4's two-phase idiom — and the bench generation advances with the
    change. PRD-05: a run start presenting the PRE-change generation is
    fenced (409 ``conflict``, nothing filed), and the corrected retry
    under the new generation is the §9 replay — the same request resolves
    to the SAME run, never a second execution.
    """
    bench_id = journey_admitted.bench_id

    # The safe idle boundary, wire-visible: no live lease, no trip, and
    # the journey's run has closed terminal (the §5 run-side busy oracle).
    bench = poc_rest.get(f"/v1/benches/{bench_id}").json()["data"]
    assert bench["busy"] is False
    assert bench["tripped"] is False
    assert journey_terminal.state == "terminal"

    # Stage + apply the controlled admin change (two-phase, distinct
    # approver — the applier's admin identity authorizes nothing).
    generation = journey_admitted.generation
    submitted = poc_rest.post(
        "/v1/admin/changes",
        principal="admin",
        json={
            "request_id": "req-poc-trip-reset",
            "bench_id": bench_id,
            "kind": "trip_reset",
            "target_ref": journey_admitted.commissioning_ref,
            "expected_generation": generation,
            "reason": "poc journey: controlled admin change at the safe idle boundary",
        },
    )
    assert submitted.status_code == 201, submitted.text
    change_id = str(submitted.json()["data"]["change_id"])
    approval_ref = _store_approval(poc_app.content, change_id, generation, poc_tokens)
    applied = poc_rest.post(
        f"/v1/admin/changes/{change_id}/apply",
        principal="admin",
        json={
            "request_id": "req-poc-apply-trip-reset",
            "expected_generation": generation,
            "approval_ref": approval_ref,
            "approver_token": poc_tokens.approver,
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["state"] == "applied"

    # The change really happened: generation advanced, the record stands
    # applied, and the bench stream carries the admin event for THIS change.
    bench = poc_rest.get(f"/v1/benches/{bench_id}").json()["data"]
    assert bench["generation"] == generation + 1
    change = poc_rest.get(
        f"/v1/admin/changes/{change_id}", principal="admin"
    ).json()["data"]
    assert change["state"] == "applied"
    page = poc_rest.get(
        f"/v1/benches/{bench_id}/events", params={"after": "", "limit": 1000}
    ).json()["data"]
    admin_events = [
        event for event in page["events"] if str(event["kind"]) == "bench_changed"
    ]
    assert any(
        event["evidence"] == journey_admitted.commissioning_ref
        for event in admin_events
    )

    # PRD-05: the same start presenting the pre-change generation is fenced.
    stale = poc_rest.post(
        f"/v1/benches/{bench_id}/runs",
        principal="operator",
        json={
            "request_id": journey_admitted.binding_ref["id"],
            "binding_ref": journey_admitted.binding_ref,
            "expected_generation": generation,  # stale: the change advanced it
            "lease_id": None,
        },
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "conflict"

    # The corrected retry under the new generation is the §9 REPLAY: the
    # same request resolves to the SAME terminal run — never re-executed.
    replay = poc_rest.post(
        f"/v1/benches/{bench_id}/runs",
        principal="operator",
        json={
            "request_id": journey_admitted.binding_ref["id"],
            "binding_ref": journey_admitted.binding_ref,
            "expected_generation": generation + 1,
            "lease_id": None,
        },
    )
    assert replay.status_code == 202, replay.text
    assert str(replay.json()["data"]["run_id"]) == journey_terminal.run_id


# --- §3 step 6: the fault legs (Task 6) ------------------------------------------

#: Step kinds that dispatch to a device — the executor's operation kinds
#: (``delay``/``sample``/``assert``/``if``/``repeat`` never reach a plugin).
#: The durable ``run:{id}`` stream carries one event per executed
#: occurrence, so counting these events IS the dispatch count: an
#: unintended second execution would mint events above the leg's pin
#: (executor.py's "one dispatch per occurrence, ever"; the occurrence
#: pins in test_procedures.py).
DISPATCH_KINDS = frozenset({"invoke", "read", "write"})

#: Per-leg terminal outcome. Every value is pinned by the deep suite that
#: owns the behaviour — never derived here by intuition:
LEG_EXPECTATION: dict[str, tuple[str, ...]] = {
    # The dropped 202 is transport-side: the run itself is healthy, and the
    # identical retry must resolve to THAT run — operations.py's "§9 replay
    # beats §5 contention" pin; the replay idiom is
    # test_event_recovery.test_same_request_retry_after_recovery_returns_existing_run.
    "lost_response": ("passed",),
    # test_procedures.test_stale_sample_is_execution_error: the stale sample
    # is INVALID evidence — body ``execution_error`` ("stale" reason), which
    # the verified final safe condition passes through (terminal_outcome).
    "stale_sample": ("execution_error",),
    # The dispatched OVP rejection is uncertain truth: executor.py's
    # "DISPATCHED or UNKNOWN maps to outcome_unknown" over the sim plugin's
    # trip contract (test_sim_plugins' OVP pins), and coordinator.py's
    # "uncertainty is never erased by later safety" keeps it there.
    "trip": ("outcome_unknown",),
    # test_event_recovery.test_kill_mid_run_staged_crash_recovers_interrupted
    # (in-process variant): a fresh boot's recovery records ``interrupted``.
    "restart": ("interrupted",),
}

#: Per-leg dispatched-device-operation count, from the same derivation the
#: deep suites walk (test_procedures.test_worst_case_bound_exact enumerates
#: the fixture procedure's step list; each pin below names where its fault
#: terminates the body):
LEG_OCCURRENCES: dict[str, int] = {
    # A healthy body dispatches configure, enable, note, model, measure and
    # remeasure x3 — eight device operations, and the §9 retry adds none.
    "lost_response": 8,
    # The stale leg dies at the ``voltage`` sample (never dispatched):
    # configure, enable, note, model, measure — five dispatches, the last
    # measure's result ageing past max_age before selection.
    "stale_sample": 5,
    # The trip leg dies on the tripping ``enable`` dispatch: configure then
    # enable — two dispatches, the second applied-then-tripped.
    "trip": 2,
    # The staged crash dispatched nothing (no step events in the durable
    # stream), and recovery only rebuilds the occurrence ledger to suppress
    # replay — zero dispatches, ever.
    "restart": 0,
}


def dispatch_occurrences(app: Gateway, record: TerminalRecord) -> int:
    """Dispatched device operations in the run's durable event stream."""
    events = app.store.read_events(f"run:{record.run_id}")
    return sum(1 for event in events if str(event.get("kind")) in DISPATCH_KINDS)


def _wire_generation(rest: _Rest, bench_id: str) -> int:
    """The bench's CURRENT generation over the wire — legs never assume a
    literal (the admission and the in-journey trip_reset both advanced it
    before the legs run; any future admin change must keep working here)."""
    return int(rest.get(f"/v1/benches/{bench_id}").json()["data"]["generation"])


def _poll_terminal(
    rest: _Rest, run_id: str, *, timeout_s: float = 60.0, poll_s: float = 0.2
) -> dict[str, Any]:
    """Bounded REST poll to terminal (the journey_run idiom, leg-local)."""
    deadline = time.monotonic() + timeout_s
    current: dict[str, Any] = {}
    while True:
        current = rest.get(f"/v1/runs/{run_id}").json()["data"]
        if current["state"] == "terminal":
            return current
        assert time.monotonic() < deadline, (
            f"run {run_id} never reached terminal within {timeout_s:g}s "
            f"(last state: {current['state']!r})"
        )
        time.sleep(poll_s)


def _record_from_final(
    bench_id: str,
    run_id: str,
    request_id: str,
    final: dict[str, Any],
    *,
    mcp_run_id: str,
    events: int,
) -> TerminalRecord:
    """Assemble the wire-shaped TerminalRecord from a terminal projection
    (journey_run's tail discipline: an uncertain terminal carries no record
    and no digest — never fabricated)."""
    terminal_ref = final.get("terminal_record")
    ref_dict = dict(terminal_ref) if isinstance(terminal_ref, dict) else None
    digests: tuple[str, ...] = (
        (str(ref_dict["sha256"]),) if ref_dict and ref_dict.get("sha256") else ()
    )
    return TerminalRecord(
        run_id=run_id,
        bench_id=bench_id,
        request_id=request_id,
        state=str(final["state"]),
        outcome=final.get("outcome"),
        safe_state=final.get("safe_state"),
        terminal_record=ref_dict,
        evidence_digests=digests,
        mcp_run_id=mcp_run_id,
        events_observed=events,
    )


def _fault_binding(
    app: Gateway, request_id: str, *, procedure: dict[str, Any] | None = None
) -> dict[str, str]:
    """Store one §5 binding variant for a fault leg; returns its wire ref.

    The fixture binding under a fresh document-level ``request_id`` (the
    second-binding idiom from test_event_recovery — the coordinator's
    per-binding acceptance dedups on it), optionally pinning a MUTATED
    procedure. A mutated procedure needs a commissioning variant too: the
    admission lattice pins the procedure digest from BOTH sides
    (documents.py: binding → procedure and commissioning.procedure_refs →
    procedure), so the mutation is re-pinned through the chain exactly as
    test_procedures' ``readmit_mutated`` rebuilds it, and the run path
    loads every document from the ContentStore by digest
    (app._spool_documents).
    """
    binding = json.loads((FIXTURES / "run-binding.json").read_bytes())
    binding["request_id"] = request_id
    if procedure is not None:
        procedure_bytes = json.dumps(procedure, indent=2).encode()
        procedure_sha = hashlib.sha256(procedure_bytes).hexdigest()
        app.content.put_document(
            procedure_bytes, procedure_sha, procedure, "urn:stg:procedure", NOW_ISO
        )
        binding["procedure"]["sha256"] = procedure_sha
        commissioning = json.loads((FIXTURES / "commissioning.json").read_bytes())
        for ref in commissioning["procedure_refs"]:
            if ref["id"] == procedure["id"] and ref["version"] == procedure["version"]:
                ref["sha256"] = procedure_sha
        commissioning_bytes = json.dumps(commissioning, indent=2).encode()
        commissioning_sha = hashlib.sha256(commissioning_bytes).hexdigest()
        app.content.put_document(
            commissioning_bytes,
            commissioning_sha,
            commissioning,
            "urn:stg:commissioning",
            NOW_ISO,
        )
        binding["commissioning"]["sha256"] = commissioning_sha
    binding_bytes = json.dumps(binding, indent=2).encode()
    binding_sha = hashlib.sha256(binding_bytes).hexdigest()
    app.content.put_document(binding_bytes, binding_sha, binding, "urn:stg:binding", NOW_ISO)
    return {"id": request_id, "version": "1.0.0", "sha256": binding_sha}


def _stale_procedure() -> dict[str, Any]:
    """The stale-evidence vector, verbatim from the deep suite.

    test_procedures.test_stale_sample_is_execution_error inserts a 600 ms
    delay between the ``measure`` invoke and the ``voltage`` sample
    (``max_age_ms`` 500): the sample is INVALID at selection —
    ``execution_error``, never a passing assertion.
    """
    procedure: dict[str, Any] = json.loads(
        (FIXTURES / "procedure-voltage-check.json").read_bytes()
    )
    steps = procedure["steps"]
    index = next(i for i, step in enumerate(steps) if step["id"] == "measure")
    steps.insert(index + 1, {"id": "age", "kind": "delay", "duration_ms": 600})
    return procedure


def _trip_procedure() -> dict[str, Any]:
    """The OVP-trip vector: policy-clean inputs that trip the real device.

    5.4 V under a 5.3 V OVP threshold — both inside the policy's configure
    constraints (voltage_v <= 5.5, ovp_v <= 6), so the dispatch is admitted
    and the DEVICE trips when the enable write turns the output on with
    the setpoint above threshold (sim_psu._check_trips) — the plugin
    contract's OVP pins (test_sim_plugins: latch until reset, dispatched).
    """
    procedure: dict[str, Any] = json.loads(
        (FIXTURES / "procedure-voltage-check.json").read_bytes()
    )
    configure = next(step for step in procedure["steps"] if step["id"] == "configure")
    configure["input"]["voltage_v"] = 5.4
    configure["input"]["ovp_v"] = 5.3
    return procedure


def _stage_crashed_run(
    store: Store, run_id: str, binding_ref: dict[str, str], *, principal: str
) -> None:
    """Stage exactly the durable state a mid-body kill leaves behind.

    The real Store APIs write what a crashed process had committed (the
    test_event_recovery idiom, principal parametrised for the journey's
    operator): an accepted (principal, ``run_start``, request_id) dedup
    row, a run row without a terminal record, queue state ``running``, and
    an active bench lease held by ``run:{run_id}`` — reserved before the
    body's first dispatch.
    """
    key = scoped_request_key(principal, "run_start", str(binding_ref["id"]))
    body_sha = hashlib.sha256(
        json.dumps(binding_ref, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    store.accept_request(key, body_sha, run_id, NOW_ISO)
    store.create_run(
        run_id,
        binding={
            "id": str(binding_ref["id"]),
            "version": str(binding_ref["version"]),
            "sha256": body_sha,
        },
        principal_id=principal,
        now=NOW_ISO,
    )
    store.next_lease(BENCH, f"lease-{run_id}", f"run:{run_id}", f"{NOW_ISO}T+10s")
    store.put_run_state(run_id, BENCH, "running", NOW_ISO)


def _leg_lost_response(
    app: Gateway, rest: _Rest, mcp: _Mcp, admitted: Admitted, tokens: Tokens
) -> TerminalRecord:
    """§3 step 6a — the operator's start response is lost; the identical
    retry returns the SAME run, never a second dispatch.

    The "dropped" 202 is driven in its hardest window: the retry fires
    while the run is still live and the bench busy, where §5 contention
    would refuse a DIFFERENT request — operations.py pins that the §9
    replay resolves first and returns the original run. The run itself is
    healthy by design (the fault is transport-side); LEG_OCCURRENCES
    carries the no-second-dispatch proof.
    """
    del tokens
    generation = _wire_generation(rest, admitted.bench_id)
    ref = _fault_binding(app, "req-poc-fault-lost-response")
    body = {
        "request_id": ref["id"],
        "binding_ref": ref,
        "expected_generation": generation,
        "lease_id": None,
    }
    started = rest.post(
        f"/v1/benches/{admitted.bench_id}/runs", principal="operator", json=body
    )
    assert started.status_code == 202, started.text
    run_id = str(started.json()["data"]["run_id"])

    # The response is "lost" — the client holds only the request it filed;
    # the byte-identical retry must resolve to the SAME live run.
    retry = rest.post(
        f"/v1/benches/{admitted.bench_id}/runs", principal="operator", json=body
    )
    assert retry.status_code == 202, retry.text
    replayed = retry.json()["data"]
    assert str(replayed["run_id"]) == run_id
    assert replayed["state"] in ("accepted", "running"), replayed

    final = _poll_terminal(rest, run_id)
    found = mcp.call(
        "stg_v1_run_find", {"request_id": ref["id"]}, principal="operator"
    )["data"]
    assert str(found["run_id"]) == run_id  # one run under the request, both transports
    via_mcp = mcp.call("stg_v1_run_get", {"run_id": run_id})["data"]
    assert str(via_mcp["run_id"]) == run_id
    return _record_from_final(
        admitted.bench_id,
        run_id,
        ref["id"],
        final,
        mcp_run_id=str(via_mcp["run_id"]),
        events=len(_bench_events(rest, admitted.bench_id)),
    )


def _leg_stale_sample(
    app: Gateway, rest: _Rest, mcp: _Mcp, admitted: Admitted, tokens: Tokens
) -> TerminalRecord:
    """§3 step 6b — a stale sample is INVALID evidence, never a pass.

    The deep-suite vector exactly: a 600 ms delay ages the measure result
    past ``max_age_ms`` 500 before the ``voltage`` sample selects it. The
    wire outcome is ``execution_error`` with the INVALID_SAMPLE signature
    on the durable stream, and the body died at the sample — ``recheck``
    never runs (test_procedures pins all three).
    """
    del tokens
    generation = _wire_generation(rest, admitted.bench_id)
    ref = _fault_binding(app, "req-poc-fault-stale-sample", procedure=_stale_procedure())
    record = journey_run(
        app,
        rest,
        mcp,
        admitted,
        request_id=ref["id"],
        binding_ref=ref,
        expected_generation=generation,
    )
    by_step = {
        str(event["occurrence"][1]): event
        for event in app.store.read_events(f"run:{record.run_id}")
    }
    assert by_step["voltage"]["status"] == "error"
    assert by_step["voltage"]["error_code"] == "INVALID_SAMPLE"
    assert "recheck" not in by_step  # the body ended at the stale sample
    assert record.outcome != "passed"
    return record


def _leg_trip(
    app: Gateway, rest: _Rest, mcp: _Mcp, admitted: Admitted, tokens: Tokens
) -> TerminalRecord:
    """§3 step 6c — the simulator's OVP trip, live through the real plugin.

    Policy-clean configure inputs (5.4 V under a 5.3 V OVP threshold) are
    admitted, and the device trips on the enable write — applied then
    latched (sim_psu: "write applied; protective trip: OVP_TRIP"). A
    DISPATCHED rejection is uncertain truth: the terminal outcome is
    ``outcome_unknown`` with a real record, the durable stream carries the
    enable step's DEVICE_REJECTED, and the record's reasons name the trip.
    """
    del tokens
    generation = _wire_generation(rest, admitted.bench_id)
    ref = _fault_binding(app, "req-poc-fault-trip", procedure=_trip_procedure())
    record = journey_run(
        app,
        rest,
        mcp,
        admitted,
        request_id=ref["id"],
        binding_ref=ref,
        expected_generation=generation,
    )
    by_step = {
        str(event["occurrence"][1]): event
        for event in app.store.read_events(f"run:{record.run_id}")
    }
    assert by_step["enable"]["status"] == "error"
    assert by_step["enable"]["error_code"] == "DEVICE_REJECTED"
    assert "measure" not in by_step  # the body ended at the tripping enable
    assert record.terminal_record is not None  # uncertain, but recorded
    durable = app.store.get_run(record.run_id)
    assert durable is not None and durable["terminal"] is not None
    reasons = [str(reason) for reason in durable["terminal"]["reasons"]]
    assert any("OVP_TRIP" in reason for reason in reasons), reasons
    assert record.outcome != "passed"
    return record


def _leg_restart(
    app: Gateway, rest: _Rest, mcp: _Mcp, admitted: Admitted, tokens: Tokens
) -> TerminalRecord:
    """§3 step 6d — the journey gateway IS a recovery boot, honestly.

    A previous process's mid-body kill (the staged crash the ``poc_app``
    fixture wrote before boot: accepted §9 row, run row without a
    terminal record, running queue state, lease held by ``run:{id}``)
    under the journey operator's principal. The boot's lifespan recovery
    finalised it ``interrupted``/``unknown`` with a real record, one
    visible recovery ``run_changed``, nothing invented — and zero
    dispatches, ever (recovery rebuilds the occurrence ledger to suppress
    replay; it never dispatches). Everything is asserted over the
    journey's own transports.
    """
    del app, tokens  # read-only over the journey's transports
    final = _poll_terminal(rest, RESTART_RUN_ID, timeout_s=10.0)
    assert final["outcome"] == "interrupted"
    assert final["safe_state"] == "unknown"
    assert isinstance(final["terminal_record"], dict)  # recovery writes a real record

    # The recovery is visible on the bench stream exactly once, nothing
    # invented (the staged-crash pin: no trip, no fabricated event).
    bench_events = _bench_events(rest, admitted.bench_id)
    recovery_events = [
        event
        for event in bench_events
        if event.get("run_id") == RESTART_RUN_ID and str(event["kind"]) == "run_changed"
    ]
    assert len(recovery_events) == 1, (
        [e["kind"] for e in bench_events if e.get("run_id") == RESTART_RUN_ID]
    )
    # D4 (interface-errata slice): the recovery event pins the run's
    # binding document; the reason rides the gateway log.
    assert set(recovery_events[0].get("evidence", {})) == {"id", "version", "sha256"}
    run_kinds = [
        str(event["kind"])
        for event in bench_events
        if event.get("run_id") == RESTART_RUN_ID
    ]
    assert run_kinds == ["run_changed"]  # no invented protective event

    # §9 under the journey's principal, both transports: the staged request
    # resolves to the recovered run — one run, recovered not re-executed.
    found = mcp.call(
        "stg_v1_run_find", {"request_id": RESTART_REQUEST_ID}, principal="operator"
    )["data"]
    assert str(found["run_id"]) == RESTART_RUN_ID
    via_mcp = mcp.call("stg_v1_run_get", {"run_id": RESTART_RUN_ID})["data"]
    assert str(via_mcp["run_id"]) == RESTART_RUN_ID
    return _record_from_final(
        admitted.bench_id,
        RESTART_RUN_ID,
        RESTART_REQUEST_ID,
        final,
        mcp_run_id=str(via_mcp["run_id"]),
        events=len(bench_events),
    )


journey_fault_legs: dict[str, Callable[..., TerminalRecord]] = {
    "lost_response": _leg_lost_response,
    "stale_sample": _leg_stale_sample,
    "trip": _leg_trip,
    "restart": _leg_restart,
}


@pytest.mark.parametrize("leg", ["lost_response", "stale_sample", "trip", "restart"])
def test_journey_fault_legs(
    leg: str,
    poc_app: Gateway,
    poc_rest: _Rest,
    poc_mcp: _Mcp,
    poc_tokens: Tokens,
    journey_admitted: Admitted,
    record_property: Callable[[str, object], None],
) -> None:
    """PRD §3 step 6, live: four fault legs, each honest, each executed
    exactly once.

    Three legs are fault-OUTCOME legs (stale sample, OVP trip, restart):
    their terminal outcome is never ``passed`` — asserted inside each
    driver together with the fault's deep-suite signature. The fourth is
    transport-side: the lost-response leg's RUN is healthy by design, and
    its fault proof is the §9 replay plus LEG_OCCURRENCES. Every
    expectation and occurrence count cites its deep-suite pin in the
    LEG_EXPECTATION / LEG_OCCURRENCES tables; the durable event stream is
    the occurrence oracle (one dispatch per occurrence, ever).

    The measured per-leg values (outcome, expected outcomes, occurrence
    counts) are recorded via ``record_property`` so the WP09 Task-11
    fault-matrix harvest can project them out of the ``--junitxml``
    report into the retained evidence — the committed matrix carries
    MEASURED values, never these tables restated.
    """
    record = journey_fault_legs[leg](poc_app, poc_rest, poc_mcp, journey_admitted, poc_tokens)
    occurrences = dispatch_occurrences(poc_app, record)
    record_property("actual_outcome", record.outcome)
    record_property("expected_outcomes", ",".join(LEG_EXPECTATION[leg]))
    record_property("occurrences_expected", LEG_OCCURRENCES[leg])
    record_property("occurrences_actual", occurrences)
    assert record.outcome in LEG_EXPECTATION[leg]
    assert occurrences == LEG_OCCURRENCES[leg]


# --- §3 step 7: second-install reuse from the built wheel (Task 6) ----------------


@dataclass(frozen=True)
class WheelTree:
    """One fresh install of the built wheel: the console binary plus the
    installed package's vendored plugin tree (site-packages root)."""

    binary: Path
    site_packages: Path

    def plugin_digests(self) -> dict[str, str]:
        """sha256 of every source file under the vendored plugin tree,
        keyed relative to ``plugins/benchweave``.

        Byte identity is the reuse contract: pyproject's force-include
        ships the tree verbatim ("the same trees ship verbatim inside the
        package"), so digest equality against the repo sources IS the
        zero-plugin-source-changes proof, and equality between installs
        is deterministic package reuse.
        """
        root = self.site_packages / "benchweave" / "_vendored" / "plugins" / "benchweave"
        digests = {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        }
        assert digests, f"no vendored plugin files under {root}"
        assert "sim_psu/src/benchweave_sim_psu/plugin.py" in digests
        return digests


@pytest.fixture(scope="module")
def journey_wheel(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Build the wheel once for this module (the test_clean_install
    idiom, kept local: hoisting the session fixture into conftest would
    touch that suite's file for a per-session duplicate-build saving —
    disclosed in the Task-6 report)."""
    root = tmp_path_factory.mktemp("poc-reuse")
    dist = root / "dist"
    build = subprocess.run(  # noqa: S603, S607 - fixed argv; uv is the toolchain
        ["uv", "build", "--out-dir", str(dist)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert build.returncode == 0, f"uv build failed:\n{build.stderr}"
    wheels = sorted(dist.glob("benchweave-*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, found: {wheels}"
    yield wheels[0]


def _install_wheel(wheel: Path, root: Path) -> WheelTree:
    """Install the built wheel into a throwaway venv (never the dev venv)
    — the clean-install idiom."""
    created = subprocess.run(  # noqa: S603, S607 - fixed argv; uv is the toolchain
        ["uv", "venv", str(root / "venv")],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert created.returncode == 0, f"uv venv failed:\n{created.stderr}"
    installed = subprocess.run(  # noqa: S603, S607
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(root / "venv" / "bin" / "python"),
            str(wheel),
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert installed.returncode == 0, f"wheel install failed:\n{installed.stderr}"
    binary = root / "venv" / "bin" / "benchweave"
    assert binary.is_file(), "the wheel must install the benchweave console script"
    sites = sorted((root / "venv" / "lib").glob("python*/site-packages"))
    assert len(sites) == 1, f"expected one site-packages, found: {sites}"
    return WheelTree(binary=binary, site_packages=sites[0])


def _demo_end_to_end(install: WheelTree, scratch: Path) -> dict[str, Any]:
    """The §3 journey's outcome set at CLI level on a fresh install (the
    test_clean_install demo step, tightened to the Task-4/5 assertions):
    SIMULATION-identified, terminal ``passed``, verified safe condition, a
    real terminal-record digest and real evidence digests."""
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("BENCHWEAVE_")
    }
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            str(install.binary),
            "demo",
            "--scratch",
            str(scratch),
            "--keep",
            "--fixtures",
            str(FIXTURES),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=360,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    demo: dict[str, Any] = json.loads(result.stdout)
    assert demo["mode"] == "simulation"
    assert demo["simulation"] is True
    assert demo["label"] == "SIMULATION"
    assert demo["bench_id"] == BENCH
    assert demo["state"] == "terminal"
    assert demo["outcome"] == "passed"
    assert demo["safe_state"] == "verified"
    terminal_sha = str(demo["terminal_record"]["sha256"])
    assert len(terminal_sha) == 64 and int(terminal_sha, 16) >= 0
    assert demo["evidence_digests"], "the simulator run retains evidence digests"
    assert all(len(str(d)) == 64 for d in demo["evidence_digests"])
    return demo


@pytest.mark.slow
def test_journey_second_install_reuse(journey_wheel: Path, tmp_path: Path) -> None:
    """PRD §3 step 7 / PRD-01+02: a SECOND fresh install of the same built
    wheel reuses the exact plugin packages and repeats the demo
    end-to-end.

    Two independent trees install the one built wheel; both carry
    byte-identical vendored plugin packages (deterministic packaging
    reuse), and those bytes are the repo's plugin sources verbatim —
    zero plugin-source changes between install one and the reused install
    two. The second install then runs the demonstration journey
    end-to-end (the Task-4/5 outcome set at CLI level), proving the reused
    packages execute, not just sit in the tree.
    """
    primary = _install_wheel(journey_wheel, tmp_path / "install-one")
    secondary = _install_wheel(journey_wheel, tmp_path / "install-two")

    # Package reuse: both installs carry byte-identical plugin packages.
    assert primary.plugin_digests() == secondary.plugin_digests()

    # Zero plugin-source changes: the vendored trees are the repo's plugin
    # sources verbatim (the pyproject force-include contract).
    repo_root = REPO_ROOT / "plugins" / "benchweave"
    repo_digests = {
        str(path.relative_to(repo_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(repo_root.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        # Transient virtualenvs a concurrent uv run may leave under a
        # plugin project are not plugin source (refute hit this live).
        and not {"venv", ".venv"}.intersection(path.parts)
    }
    assert primary.plugin_digests() == repo_digests

    # The reused install repeats the demonstration journey end-to-end.
    demo = _demo_end_to_end(secondary, tmp_path / "demo-two")
    assert demo["outcome"] == "passed"

