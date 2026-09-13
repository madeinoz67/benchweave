"""FastAPI application factory: one ASGI app, the MCP mount, the run worker.

The app composes the whole gateway: the write gate (process-wide
single-writer discipline), the run worker (constructed with ``limits=`` —
Task 6 mandate: ``limits=None`` leaves worker emissions untrimmed), the
operations seam, and the FastMCP server mounted at ``/mcp`` under a
combined lifespan (FastMCP's ``http_app`` lifespan MUST run on the host or
``initialize`` 500s — Task 1 spike). REST (Task 9) is included before the
mount so its ``/v1`` routes win.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import FastAPI

from benchweave.content.store import ContentStore, RetainingServices
from benchweave.control.clocking import MonotonicClock, SystemClock, WallClock
from benchweave.control.coordinator import RunCoordinator, _PreparedRun, _RunMonitor
from benchweave.control.documents import AdmittedDocuments, admit_documents
from benchweave.host.plugin import DevicePlugin
from benchweave.interfaces.bootstrap import RegistrySession, admit_startup_bench
from benchweave.interfaces.mcp import build_mcp
from benchweave.interfaces.operations import Operations, append_bench_event
from benchweave.interfaces.rest import build_router
from benchweave.interfaces.validation import VENDORED_CORPUS_ROOT, SeamValidator
from benchweave.interfaces.worker import RunWorker
from benchweave.state.hold import StoreHold
from benchweave.state.store import Store

# Sim plugins are repo fixtures loaded exactly as tests/integration/
# test_procedures.py loads them (they are not package code).
_PLUGINS_ROOT = Path(__file__).resolve().parents[3] / "plugins"
_SIM_PLUGINS: tuple[tuple[str, str], ...] = (
    ("psu", "sim_psu"),
    ("controller", "sim_controller"),
)

#: Bench-stream evidence reason on the recovery ``run_changed`` (Task 11
#: wiring). Free-form evidence joins the Task 10 parity ledger's D4 family.
RECOVERY_RUN_CHANGED_REASON = "gateway restart recovery: run finalised as interrupted"


class WriteGate:
    """Process-wide single-writer discipline around the main-thread Store.

    Admin change applies MUST run under this gate: the seam's
    ``change_apply`` fence-then-bump is check-then-act, and serialising the
    admin surface closes that TOCTOU (Task 7 carry — the REST adapter holds
    the gate around each apply call; ``app.state.write_gate`` is the handle).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def __enter__(self) -> WriteGate:
        self._lock.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self._lock.release()


def _load_sim_plugin(name: str) -> ModuleType:
    """The sim plugin module, mirroring the integration tests' loader."""
    path = _PLUGINS_ROOT / "benchweave" / name / "src" / f"benchweave_{name}" / "plugin.py"
    if not path.is_file():
        raise FileNotFoundError(f"sim plugin file missing: {path}")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sim plugin from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _spool_documents(
    content: ContentStore, binding_ref: dict[str, Any], fixtures_dir: Path, spool: Path
) -> dict[str, Any]:
    """Spool the binding-pinned document bytes into the run-scoped directory.

    Every document the admission lattice pins is resolved from the
    ContentStore by digest; the package lock is the one exception — the
    bootstrap contract deliberately never admits it, so it is resolved from
    the fixtures directory (admit_documents reads it from the bench
    document's parent directory).
    """
    binding_sha = str(binding_ref.get("sha256", ""))
    binding_doc = content.get_document(binding_sha)
    if binding_doc is None:
        raise ValueError(f"binding document {binding_sha} is not stored")
    binding = binding_doc["content"]

    def spool_one(sha256: str, filename: str) -> Path:
        document = content.get_document(sha256)
        if document is None:
            raise ValueError(f"pinned document {sha256} is not stored")
        path = spool / filename
        path.write_bytes(document["raw_bytes"])
        return path

    bench_sha = str(binding["bench"]["sha256"])
    bench_doc = content.get_document(bench_sha)
    if bench_doc is None:
        raise ValueError(f"pinned document {bench_sha} is not stored")
    descriptor_paths: dict[str, Path] = {}
    for device in bench_doc["content"]["devices"]:
        device_id = str(device["id"])
        descriptor_paths[device_id] = spool_one(
            str(device["descriptor"]["sha256"]), f"descriptor-{device_id}.json"
        )
    (spool / "package-lock.json").write_bytes((fixtures_dir / "package-lock.json").read_bytes())
    return {
        "procedure_path": spool_one(str(binding["procedure"]["sha256"]), "procedure.json"),
        "policy_path": spool_one(str(binding["policy"]["sha256"]), "policy.json"),
        "bench_path": spool_one(bench_sha, "bench.json"),
        "binding_path": spool_one(binding_sha, "binding.json"),
        "commissioning_path": spool_one(
            str(binding["commissioning"]["sha256"]), "commissioning.json"
        ),
        "descriptor_paths": descriptor_paths,
    }


def _recovery_documents(fixtures_dir: Path) -> AdmittedDocuments:
    """Admit the startup lattice for recovery (Task 11 wiring).

    ``RunCoordinator.recover_interrupted`` only reads the admitted bench's
    identity, but recovery holds itself to the same admission standard as
    execution: the fixture lattice is fully admitted and pin-verified. The
    procedure is the binding-pinned one (the lattice may carry a family).
    """
    binding = json.loads((fixtures_dir / "run-binding.json").read_bytes())
    procedure_sha = str(binding["procedure"]["sha256"])
    procedure_path = next(
        (
            path
            for path in sorted(fixtures_dir.glob("procedure-*.json"))
            if hashlib.sha256(path.read_bytes()).hexdigest() == procedure_sha
        ),
        None,
    )
    if procedure_path is None:
        raise FileNotFoundError("binding-pinned procedure not found under fixtures")
    bench = json.loads((fixtures_dir / "bench.json").read_bytes())
    by_sha = {
        hashlib.sha256(path.read_bytes()).hexdigest(): path
        for path in sorted(fixtures_dir.glob("descriptor-*.json"))
    }
    descriptor_paths = {
        str(device["id"]): by_sha[str(device["descriptor"]["sha256"])]
        for device in bench["devices"]
    }
    return admit_documents(
        procedure_path=procedure_path,
        policy_path=fixtures_dir / "safety-policy.json",
        bench_path=fixtures_dir / "bench.json",
        binding_path=fixtures_dir / "run-binding.json",
        commissioning_path=fixtures_dir / "commissioning.json",
        descriptor_paths=descriptor_paths,
    )


def _recover_interrupted_runs(
    store: Store,
    fixtures_dir: Path,
    *,
    emit_keep: int,
    now_iso: Callable[[], str],
) -> list[str]:
    """Startup recovery (Task 11 wiring): close what a dead process left open.

    ``RunCoordinator.recover_interrupted`` finalises durable runs left
    without a terminal record as ``interrupted``/``unknown`` (rebuilding
    their occurrence identities from the durable event stream so nothing
    re-dispatches) and releases their leases. The interface owns the queue
    projection, so each recovered run's state closes ``terminal`` and one
    ``run_changed`` makes the gap visible on the bench stream — nothing
    else is invented. No plugins are constructed: recovery never touches a
    device.

    D13 batch A adds the crash-window leg on the same startup path:
    ``Store.reconcile_dangling_requests`` purges §9 keys whose run never
    materialized (a process death between ``accept_request`` and
    ``create_run``), unwedging the request id for a fresh attempt.
    """
    docs = _recovery_documents(fixtures_dir)
    coordinator = RunCoordinator(store, {}, SystemClock(), SystemClock(), docs)
    recovered = coordinator.recover_interrupted()
    # D13 crash-window reconciliation rides the same startup path: a §9
    # RUN-request key filed by a process that died between
    # accept_request and create_run points at a run that never
    # materialized (a permanent replay wedge). The sweep is scoped to run
    # keys — its anti-join must resolve in neither runs nor changes, so
    # change_submit keys (whose run_id column holds a change id) and keys
    # with a runs row, live or tombstoned, keep their replay protection —
    # and the same request id can proceed. No event is emitted: nothing
    # observable happened (no run, no dispatch) and the seven-kind fence
    # has no vocabulary for it; the purged keys are the caller's evidence.
    store.reconcile_dangling_requests()
    bench_id = str(docs.bench["id"])
    for run_id in recovered:
        store.put_run_state(run_id, bench_id, "terminal", now_iso())
        append_bench_event(
            store,
            "run_changed",
            bench_id,
            run_id,
            {"reason": RECOVERY_RUN_CHANGED_REASON},
            keep=emit_keep,
            now_iso=now_iso,
        )
    return recovered


class _RetainingCoordinator(RunCoordinator):
    """RunCoordinator with the monitor's evidence-retention hook armed.

    The monitor is constructed per run inside ``_prepare_run`` (whose
    acceptance tick fires before this override can arm ``retain``), so the
    hook arms the moment ``_prepare_run`` returns: every body tick retains
    its snapshot; the acceptance tick's snapshot is not retained (disclosed
    gap). The last monitor stays reachable after the run — the base class
    clears ``_active_monitor`` in ``_finish_run`` — so the run worker can
    still read ``retention_failures`` for its drain-side ``evidence_gap``
    emission (Task 6 wiring that the base class's None-ing would defeat).
    """

    def __init__(
        self,
        store: Store,
        plugins: dict[str, DevicePlugin],
        clock: MonotonicClock,
        wall: WallClock,
        docs: AdmittedDocuments,
        *,
        retain: Callable[[dict[str, Any]], str],
        spool: tempfile.TemporaryDirectory[str],
    ) -> None:
        super().__init__(store, plugins, clock, wall, docs)
        self._retain = retain
        self._spool_dir = spool  # cleaned up when the coordinator is collected
        self._last_monitor: _RunMonitor | None = None

    def _prepare_run(self, run_id: str, principal_id: str) -> _PreparedRun:
        prepared = super()._prepare_run(run_id, principal_id)
        prepared.monitor.retain = self._retain
        self._last_monitor = prepared.monitor
        return prepared

    @property
    def monitor(self) -> _RunMonitor | None:
        live = self._active_monitor
        if live is not None:
            self._last_monitor = live
        return self._last_monitor


def _build_run_factory(
    fixtures_dir: Path, now_iso: Callable[[], str], *, quota: int
) -> Callable[[str, str, dict[str, Any], Store], RunCoordinator]:
    def build_run(
        run_id: str, principal_id: str, binding_ref: dict[str, Any], worker_store: Store
    ) -> RunCoordinator:
        """The whole coordinator stack, built on the worker thread.

        Task 5/6 wiring: ``build_run`` receives the worker thread's own
        re-opened Store as its fourth argument — sqlite3 connections are
        thread-affine, so the ContentStore, the admission, the sim plugins
        and the coordinator are all constructed here, never handed over
        from the main thread.
        """
        content = ContentStore(worker_store)
        spool = tempfile.TemporaryDirectory(prefix=f"stg-run-{run_id}-")
        docs = admit_documents(
            **_spool_documents(content, binding_ref, fixtures_dir, Path(spool.name))
        )
        clock = SystemClock()
        services = RetainingServices(content, quota=quota, now=now_iso())
        plugins: dict[str, DevicePlugin] = {}
        for device_id, name in _SIM_PLUGINS:
            plugin = _load_sim_plugin(name).create_plugin(
                now_fn=clock.now_iso, monotonic_ns_fn=clock.now_ns
            )
            plugin.plugin_open(services)
            plugins[device_id] = plugin
        return _RetainingCoordinator(
            worker_store,
            plugins,
            clock,
            clock,
            docs,
            # The monitor's retain hook is one-argument (the snapshot dict);
            # RetainingServices keys evidence per context — one context per
            # run, so the run's quota bounds its snapshot retentions.
            retain=lambda snapshot: services.retain_evidence(f"run:{run_id}", snapshot),
            spool=spool,
        )

    return build_run


def _store_db_path(store: Store) -> Path | None:
    """The main database file backing ``store`` (None for in-memory stores)."""
    for row in store.connection.execute("PRAGMA database_list").fetchall():
        if row[1] == "main" and row[2]:
            return Path(str(row[2]))
    return None


def create_app(
    *,
    store: Store,
    content: ContentStore,
    secret: bytes,
    limits: dict[str, int],
    gateway_id: str,
    fixtures_dir: Path,
    now_iso: Callable[[], str],
    now_epoch: Callable[[], int],
    registry_session: RegistrySession | None = None,
) -> FastAPI:
    """Compose the gateway: gate, worker (limits mandated), seam, MCP mount."""
    gate = WriteGate()
    # Same retention arithmetic as the seam's bench-event windows.
    quota = int(limits["max_page_size"]) * 10
    worker = RunWorker(
        store,
        content,
        build_run=_build_run_factory(fixtures_dir, now_iso, quota=quota),
        now_iso=now_iso,
        limits=limits,
    )
    operations = Operations(
        store,
        content,
        # D8: the seam validates every payload against the vendored corpus;
        # the registry builds once per app (corpus disagreement is fatal).
        validator=SeamValidator(VENDORED_CORPUS_ROOT),
        gateway_id=gateway_id,
        limits=limits,
        worker=worker,
        now_iso=now_iso,
        issuer_secret=secret,
        now_epoch=now_epoch,
        # WP08 Task 7: the fixture resolver session (constructed once via
        # bootstrap.build_registry_session); ``None`` keeps the fail-closed
        # WP07 posture for the registry change kinds.
        registry_session=registry_session,
    )

    mcp_server = build_mcp(
        operations, secret=secret, now_epoch=now_epoch, limits=limits, gate=gate
    )
    mcp_app = mcp_server.http_app(path="/mcp")

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        # WP08 Task 10: mark store ownership for the whole serving lifetime.
        # At-rest commands (backup/restore) acquire the same advisory lock
        # and refuse — naming this gateway — while it is held, and a second
        # gateway on the same database fails loudly here instead of silently
        # corrupting it. The OS releases the flock on process death, so a
        # crash can never wedge the gate (see state/hold.py).
        db_file = _store_db_path(store)
        hold = StoreHold(db_file, label=f"gateway {gateway_id}") if db_file else None
        if hold is not None:
            hold.acquire()
        try:
            with gate:
                admit_startup_bench(store, content, fixtures_dir, now=now_iso())
                # Task 11 wiring: a restarted gateway closes what a dead process
                # left open before it serves or executes anything new.
                _recover_interrupted_runs(
                    store, fixtures_dir, emit_keep=quota, now_iso=now_iso
                )
            worker.start()
            try:
                async with mcp_app.lifespan(app):
                    yield
            finally:
                worker.stop()
                worker.join(timeout=5.0)
        finally:
            if hold is not None:
                hold.release()

    app = FastAPI(title="BenchWeave gateway", version="1.1.0", lifespan=_lifespan)
    # Task 9: the REST router is included BEFORE the "/" mount — a mount at
    # "/" swallows every route included after it, so /v1 must land first.
    app.include_router(
        build_router(operations, gate, secret=secret, limits=limits, now_epoch=now_epoch)
    )
    # Mounted at "/" so FastMCP's internal "/mcp" route lands at /mcp; the
    # REST router (Task 9) is included BEFORE this mount so /v1 wins.
    app.mount("/", mcp_app)
    # Task 9's REST adapter routes admin change applies through this gate
    # (Task 7 carry: change_apply's fence-then-bump is check-then-act).
    app.state.write_gate = gate
    return app
