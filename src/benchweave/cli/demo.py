"""The built-in simulator demonstration (Task 11): one drive path, two modes.

Gateway mode (``--gateway URL``) drives the operator's LIVE gateway over the
same REST surface every other client uses — ``run_start`` with the fixture
lattice's valid binding (exactly how the parity/integration suites build
binding refs: the sha256 of ``run-binding.json``, and the binding document's
own ``request_id``, which the coordinator's acceptance key requires), a §9
``run_find`` cross-check, ``run_get`` polling bounded by a configurable
timeout, then the outcome plus the terminal record's evidence digests.

Fresh-install mode (no ``--gateway``) boots an EPHEMERAL gateway in-process
on a SCRATCH directory — never the daemon's data dir — drives the identical
path over loopback REST, labels every rendered surface ``SIMULATION`` (the
bench is the executable simulator fixture, not hardware), and tears down:
app shutdown, then the scratch tree is removed unless ``--keep`` (a scratch
directory that pre-existed is itself never deleted — only the demo's own
store files are).

Anti-coordinate rule (ISC-12): fresh-install mode REFUSES to compose if
:func:`benchweave.cli.atrest.daemon_holds` reports any live coordinator on
any store under the scratch dir — checked BEFORE the app (a second
coordinator over one store) is ever constructed. The ephemeral app is then
the single coordinator of its own scratch store, exactly like a serving
gateway.

The heavy app stack (uvicorn/fastapi/create_app) imports lazily inside the
fresh-install path so ``benchweave --help`` never pays for the demo.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from benchweave.cli.atrest import DB_NAME, daemon_holds
from benchweave.cli.client import GatewayClient

if TYPE_CHECKING:
    import uvicorn
    from fastapi import FastAPI

#: The binding document inside the fixture lattice (the suites' name).
BINDING_FILE = "run-binding.json"
#: The repository execution lattice, resolved like ``app_entry`` does.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURES = _REPO_ROOT / "fixtures" / "execution"
#: The demo's ephemeral gateway identity (visible in status/refusals).
GATEWAY_ID = "gw-cli-demo"
#: The principal the demo's own ephemeral token is issued to.
PRINCIPAL = "benchweave-demo"
#: The same limits block every composed test gateway uses.
DEFAULT_LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}
#: Default seconds to wait for the demonstration run to reach terminal.
DEFAULT_TIMEOUT_S = 120.0
POLL_INTERVAL_S = 0.2
#: The label every fresh-install surface carries (ruling: no exceptions).
SIMULATION_LABEL = "SIMULATION"


class DemoError(RuntimeError):
    """A truthful demo failure (the CLI shows it and exits non-zero)."""


class RunReader(Protocol):
    """The one operation the terminal poll needs (unit-testable without a
    gateway: a stub implementing ``run_get`` satisfies it structurally)."""

    def run_get(self, run_id: str) -> dict[str, Any]: ...


# --- fixture binding ------------------------------------------------------------


def resolve_fixtures(explicit: Path | None) -> Path:
    """The fixture lattice to drive: ``explicit``, ``BENCHWEAVE_FIXTURES``,
    or the repository execution lattice."""
    fixtures = explicit or Path(os.environ.get("BENCHWEAVE_FIXTURES", str(DEFAULT_FIXTURES)))
    if not (fixtures / BINDING_FILE).is_file():
        raise DemoError(
            f"fixture lattice not found at {fixtures} — pass --fixtures pointing at a "
            f"directory carrying {BINDING_FILE}"
        )
    return fixtures


def fixture_binding(fixtures: Path) -> dict[str, Any]:
    """The valid binding pin + ids from the lattice (the suites' recipe).

    ``request_id`` is the binding document's OWN request id — the
    coordinator's acceptance key is the binding's request id, so any other
    choice is the repeated-binding trap (accepted by the seam, rejected by
    the worker). ``ref.id`` mirrors the parity/rest-route suites' literal
    construction.
    """
    raw = (fixtures / BINDING_FILE).read_bytes()
    document: dict[str, Any] = json.loads(raw)
    version = str(document.get("version") or document.get("contract_version", "1"))
    return {
        "request_id": str(document["request_id"]),
        "bench_id": str(document["bench"]["id"]),
        "procedure_id": str(document["procedure"]["id"]),
        "ref": {
            "id": str(document["request_id"]),
            "version": version,
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
    }


# --- the drive path (identical for both modes) ------------------------------------


def poll_to_terminal(
    reader: RunReader, run_id: str, *, timeout_s: float, poll_s: float = POLL_INTERVAL_S
) -> dict[str, Any]:
    """Poll ``run_get`` until ``state == terminal``; a timeout fails
    truthfully, naming the run and its last observed state."""
    deadline = time.monotonic() + timeout_s
    while True:
        run = reader.run_get(run_id)
        if run.get("state") == "terminal":
            return run
        if time.monotonic() >= deadline:
            raise DemoError(
                f"run {run_id} did not reach a terminal state within "
                f"{timeout_s:g}s (last state: {run.get('state')!r})"
            )
        time.sleep(poll_s)


def _terminal_evidence(run: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """The terminal-record ref and the evidence digests it carries.

    The REST surface serves the run record as a closed ``{id, version,
    sha256}`` ref — the sha256 IS the digest of the evidence-bearing run
    record (outcome, reasons, and the full ``evidence_refs`` lattice live
    inside that document). An uncertain terminal (``outcome_unknown`` /
    ``interrupted``) legitimately carries no record and no digest.
    """
    terminal_ref = run.get("terminal_record")
    if not isinstance(terminal_ref, dict) or not terminal_ref.get("sha256"):
        return None, []
    return dict(terminal_ref), [str(terminal_ref["sha256"])]


def drive_gateway(
    client: GatewayClient, fixtures: Path, *, timeout_s: float
) -> dict[str, Any]:
    """Start the fixture run on the gateway's bench and drive it to terminal."""
    binding = fixture_binding(fixtures)
    bench_id = binding["bench_id"]
    bench = client.bench_get(bench_id)
    # Advisory preflight: the gateway must hold the binding and its pinned
    # documents, and it reports the same canonical generation the fence
    # reads — both computed where the truth lives, not on the client.
    preflight = client.run_check(bench_id, binding_ref=binding["ref"])
    if preflight.get("valid") is not True:
        raise DemoError(
            f"run_check preflight failed for bench {bench_id}: "
            f"{preflight.get('findings')!r} — is the gateway bootstrapped "
            "with the fixture lattice?"
        )
    generation = int(preflight.get("generation") or bench["generation"])
    started = client.run_start(
        bench_id,
        request_id=binding["request_id"],
        binding_ref=binding["ref"],
        expected_generation=generation,
    )
    run_id = str(started["run_id"])
    # §9 cross-check: the request must resolve, for this principal, to the
    # run that was just accepted.
    found = client.run_find(binding["request_id"])
    if str(found.get("run_id")) != run_id:
        raise DemoError(
            f"run_find({binding['request_id']!r}) resolved {found.get('run_id')!r}, "
            f"not the started run {run_id!r}"
        )
    run = poll_to_terminal(client, run_id, timeout_s=timeout_s)
    terminal_ref, digests = _terminal_evidence(run)
    events = client.events_get(bench_id)
    event_items = events.get("events")
    return {
        "bench_id": bench_id,
        "procedure_id": binding["procedure_id"],
        "request_id": binding["request_id"],
        "run_id": run_id,
        "state": str(run["state"]),
        "outcome": run.get("outcome"),
        "safe_state": run.get("safe_state"),
        "terminal_record": terminal_ref,
        "evidence_digests": digests,
        "events_observed": len(event_items) if isinstance(event_items, list) else 0,
    }


# --- mode payloads ----------------------------------------------------------------


def drive_live_gateway(
    base_url: str, token: str, *, fixtures: Path | None, timeout_s: float
) -> dict[str, Any]:
    """Gateway mode: drive the operator's live gateway; the report is NEVER
    labelled a simulation (the bench may be real hardware)."""
    fixtures_dir = resolve_fixtures(fixtures)
    client = GatewayClient(base_url, token=token)
    payload = drive_gateway(client, fixtures_dir, timeout_s=timeout_s)
    payload.update(
        {
            "mode": "gateway",
            "simulation": False,
            "label": None,
            "gateway": base_url.rstrip("/"),
        }
    )
    return payload


# --- fresh-install mode -------------------------------------------------------------


def held_stores(root: Path) -> list[Path]:
    """Every store under ``root`` a live coordinator holds (ISC-12).

    Candidates: the at-rest canonical ``state.sqlite`` plus every sqlite/db
    file discovered in the directory — so pointing the scratch at a live
    gateway's data directory refuses however that gateway's store is named.
    """
    root = Path(root)
    candidates: list[Path] = [root / DB_NAME]
    try:
        discovered = sorted({*root.glob("*.sqlite"), *root.glob("*.sqlite3"), *root.glob("*.db")})
    except OSError:
        # An unreadable/non-directory root simply has no discoverable
        # stores; the canonical probe below still runs.
        discovered = []
    for path in discovered:
        if path not in candidates:
            candidates.append(path)
    return [path for path in candidates if daemon_holds(path)]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _now_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


def _boot(app: FastAPI) -> tuple[uvicorn.Server, threading.Thread, int]:
    """The loopback boot the CLI test suites use: real port, lifespan-run."""
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="benchweave-demo")
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    servers = server.servers if getattr(server, "started", False) else None
    if servers is None:
        # The app's lifespan StoreHold is the loudest reason this happens:
        # a store grabbed between the anti-coordinate gate and composition
        # fails loudly here instead of silently double-coordinating.
        server.should_exit = True
        thread.join(timeout=5.0)
        raise DemoError("the ephemeral gateway did not start within 10s")
    port = int(servers[0].sockets[0].getsockname()[1])
    return server, thread, port


def _teardown_scratch(root: Path, *, remove_root: bool, keep: bool) -> None:
    """Remove the demo's footprint: the tree it created, or in a pre-existing
    directory exactly its own store files (never the operator's directory)."""
    if keep:
        return
    if remove_root:
        shutil.rmtree(root, ignore_errors=True)
        return
    for suffix in ("", "-wal", "-shm", ".hold"):
        with contextlib.suppress(OSError):
            (root / (DB_NAME + suffix)).unlink()


def run_simulation(
    scratch: Path | None,
    *,
    keep: bool,
    fixtures: Path | None,
    timeout_s: float,
) -> dict[str, Any]:
    """Fresh-install mode: an ephemeral labelled simulation on a scratch dir."""
    # Lazy heavy imports: only the demo pays for the app stack.
    from benchweave.content.store import ContentStore
    from benchweave.interfaces.app import create_app
    from benchweave.interfaces.identity import issue
    from benchweave.state.store import Store

    fixtures_dir = resolve_fixtures(fixtures)
    # The demo owns (and on teardown removes) exactly the tree IT creates:
    # the mkdtemp default, or a --scratch path that did not exist yet. A
    # pre-existing --scratch directory is never deleted itself — only the
    # demo's own store files inside it are.
    if scratch is not None:
        root = Path(scratch)
        created_root = not root.exists()
    else:
        root = Path(tempfile.mkdtemp(prefix="benchweave-demo-"))
        created_root = True
    # Anti-coordinate gate (ISC-12): refuse BEFORE composing anything —
    # there is no in-process-composition-against-a-held-store path.
    held = held_stores(root)
    if held:
        raise DemoError(
            "refusing: a live gateway holds "
            + ", ".join(str(path) for path in held)
            + f" under {root} — the demo never composes a second coordinator "
            "over a held store; stop that gateway first"
        )
    if created_root:
        root.mkdir(parents=True, exist_ok=True)  # mkdtemp already made it

    store = Store.open(root / DB_NAME, check_same_thread=False)
    content = ContentStore(store)
    secret = secrets.token_bytes(32)
    app = create_app(
        store=store,
        content=content,
        secret=secret,
        limits=DEFAULT_LIMITS,
        gateway_id=GATEWAY_ID,
        fixtures_dir=fixtures_dir,
        now_iso=_now_iso,
        now_epoch=_now_epoch,
    )
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    port = 0
    try:
        server, thread, port = _boot(app)
        token = issue(
            secret,
            principal=PRINCIPAL,
            audience="stg",
            scopes={"stg:control"},
            expires_at=_now_epoch() + 3600,
        )
        client = GatewayClient(f"http://127.0.0.1:{port}", token=token)
        payload = drive_gateway(client, fixtures_dir, timeout_s=timeout_s)
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5.0)
        store.close()
        _teardown_scratch(root, remove_root=created_root, keep=keep)
    payload.update(
        {
            "mode": "simulation",
            "simulation": True,
            "label": SIMULATION_LABEL,
            "gateway": f"http://127.0.0.1:{port}",
            "scratch_dir": str(root),
        }
    )
    if keep:
        payload["kept"] = True
    return payload


# --- rendering -----------------------------------------------------------------------


def render_demo(data: Mapping[str, object]) -> str:
    """Plain-text TTY rendering (the Textual renderer lands in Task 12)."""
    lines: list[str] = []
    simulation = bool(data.get("simulation"))
    if simulation:
        lines.append(
            f"=== {SIMULATION_LABEL} — ephemeral scratch bench, no hardware was driven ==="
        )
    lines.append(f"mode:            {data.get('mode')}")
    lines.append(f"gateway:         {data.get('gateway')}")
    if simulation:
        lines.append(f"scratch:         {data.get('scratch_dir')}")
    lines.append(f"bench:           {data.get('bench_id')}")
    lines.append(f"procedure:       {data.get('procedure_id')}")
    lines.append(f"request:         {data.get('request_id')}")
    lines.append(f"run:             {data.get('run_id')}")
    lines.append(f"state:           {data.get('state')}")
    lines.append(f"outcome:         {data.get('outcome')}")
    lines.append(f"safe_state:      {data.get('safe_state')}")
    terminal = data.get("terminal_record")
    if isinstance(terminal, Mapping):
        lines.append(f"terminal_record: {terminal.get('sha256')}")
    digests = data.get("evidence_digests")
    printed = 0
    if isinstance(digests, list):
        for digest in digests:
            if isinstance(digest, str):
                printed += 1
                lines.append(f"evidence digest: {digest}  (the run record document)")
    if printed == 0:
        lines.append("evidence digest: (none — uncertain terminal carries no record)")
    lines.append(f"events_observed: {data.get('events_observed')}")
    if data.get("kept"):
        lines.append(f"scratch kept at: {data.get('scratch_dir')}")
    return "\n".join(lines)
