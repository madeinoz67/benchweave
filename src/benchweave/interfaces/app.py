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
import logging
import sys
import tempfile
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import FastAPI

from benchweave.content.capture_services import build_capture_services
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.store import ContentStore, RetainingServices
from benchweave.content.stream_services import build_stream_services
from benchweave.control.clocking import MonotonicClock, SystemClock, WallClock
from benchweave.control.coordinator import RunCoordinator, _PreparedRun, _RunMonitor
from benchweave.control.documents import (
    _CONTRACTS,
    AdmittedDocuments,
    admit_documents,
)
from benchweave.control.provider_settings import TRANSPORT_SETTINGS_FILENAME
from benchweave.control.stream_host import RunStreamHost
from benchweave.host.plugin import DevicePlugin, SimulationInfo
from benchweave.host.services import QuotaLimits, ReadingSinks
from benchweave.interfaces.bootstrap import (
    RegistrySession,
    admit_fixture_lattice,
    admit_startup_bench,
)
from benchweave.interfaces.device_closures import (
    DeviceClosure,
    commissioned_device_closure,
)
from benchweave.interfaces.mcp import build_mcp
from benchweave.interfaces.operations import Operations, append_bench_event
from benchweave.interfaces.rest import build_router
from benchweave.interfaces.validation import VENDORED_CORPUS_ROOT, SeamValidator
from benchweave.interfaces.worker import RunWorker
from benchweave.registry.otdp_loading import load_otdp_plugin
from benchweave.state.hold import StoreHold
from benchweave.state.store import Store
from benchweave.vendoring import (
    CorpusResolution,
    declared_dev_family,
    sim_plugins_root,
)

# Sim plugins are repo fixtures loaded exactly as tests/integration/
# test_procedures.py loads them (they are not package code) — packaged
# inside the wheel so a fresh install can run the simulator demo
# (benchweave/vendoring.py resolves packaged-first, repo fallback).
_SIM_PLUGINS: tuple[tuple[str, str], ...] = (
    ("psu", "sim_psu"),
    ("controller", "sim_controller"),
)

#: Bench-stream evidence reason on the recovery ``run_changed`` (Task 11
#: wiring). D4 (interface-errata slice): the reason rides the gateway log;
#: the event pins the run's binding document.
RECOVERY_RUN_CHANGED_REASON = "gateway restart recovery: run finalised as interrupted"

#: The recovery ``run_changed`` for a run whose durable terminal record
#: already existed and whose live projection the sweep reconciled (issue
#: #156 fix wave): the record is the truth; only the stale queue-state row
#: was wrong.
RECOVERY_PROJECTION_REASON = (
    "gateway restart recovery: stale projection reconciled to the durable terminal record"
)

_LOG = logging.getLogger(__name__)


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
    path = sim_plugins_root() / name / "src" / f"benchweave_{name}" / "plugin.py"
    if not path.is_file():
        raise FileNotFoundError(f"sim plugin file missing: {path}")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sim plugin from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _spool_provider_document(
    content: ContentStore, fixtures_dir: Path, spool: Path, descriptor_sha: str
) -> None:
    """Spool a provider-declaring descriptor's pinned contract beside it.

    The pin is DESCRIPTOR-relative, and the spooled descriptor lives at a
    new filename in a fresh directory — so the pinned contract must be
    found at the ORIGINAL descriptor's side (resolved by digest over the
    fixtures' descriptor family, the bootstrap resolution pattern),
    verified against the pin, and written into the spool at the pinned
    relative path. Without this, run admission could never admit a
    provider descriptor and the refusal would misattribute the cause
    ("does not name a contained regular file" against a package that has
    the file — fold wave B). Resolution failures return silently:
    admission then refuses with its own honest prefix against the spool's
    true state.
    """
    document = content.get_document(descriptor_sha)
    if document is None:
        return
    descriptor = document["content"]
    transport = descriptor.get("transport") if isinstance(descriptor, dict) else None
    provider = transport.get("provider") if isinstance(transport, dict) else None
    if not isinstance(provider, dict):
        return
    relative = provider.get("path")
    original = next(
        (
            path
            for path in sorted(fixtures_dir.glob("descriptor-*.json"))
            if hashlib.sha256(path.read_bytes()).hexdigest() == descriptor_sha
        ),
        None,
    )
    if original is None or not isinstance(relative, str):
        return
    try:
        raw = (original.parent / relative).read_bytes()
    except OSError:
        return
    if hashlib.sha256(raw).hexdigest() != provider.get("sha256"):
        return
    target = spool / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def _spool_documents(
    content: ContentStore, binding_ref: dict[str, Any], fixtures_dir: Path, spool: Path
) -> dict[str, Any]:
    """Spool the binding-pinned document bytes into the run-scoped directory.

    Every document the admission lattice pins is resolved from the
    ContentStore by digest; the package lock is the one exception — the
    bootstrap contract deliberately never admits it, so it is resolved from
    the fixtures directory (admit_documents reads it from the bench
    document's parent directory). A provider-declaring descriptor's pinned
    contract is spooled beside it (descriptor-relative pin), and the
    fixtures' optional ``transport-settings.json`` threads through so the
    run path admits provider lattices exactly as bootstrap does (fold
    wave B); the caller supplies ``now_wall``.
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
        _spool_provider_document(
            content, fixtures_dir, spool, str(device["descriptor"]["sha256"])
        )
    (spool / "package-lock.json").write_bytes((fixtures_dir / "package-lock.json").read_bytes())
    settings_path = fixtures_dir / TRANSPORT_SETTINGS_FILENAME
    return {
        "procedure_path": spool_one(str(binding["procedure"]["sha256"]), "procedure.json"),
        "policy_path": spool_one(str(binding["policy"]["sha256"]), "policy.json"),
        "bench_path": spool_one(bench_sha, "bench.json"),
        "binding_path": spool_one(binding_sha, "binding.json"),
        "commissioning_path": spool_one(
            str(binding["commissioning"]["sha256"]), "commissioning.json"
        ),
        "descriptor_paths": descriptor_paths,
        "provider_settings": settings_path if settings_path.is_file() else None,
    }


def _recovery_documents(
    fixtures_dir: Path, *, now_wall: str | None = None, contracts: Path = _CONTRACTS
) -> AdmittedDocuments | None:
    """Admit the startup lattice for recovery (Task 11 wiring).

    ``RunCoordinator.recover_interrupted`` only reads the admitted bench's
    identity, but recovery holds itself to the same admission standard as
    execution: the fixture lattice is fully admitted and pin-verified. The
    procedure is the binding-pinned one (the lattice may carry a family).

    Delegates to ``bootstrap.admit_fixture_lattice`` — the one resolution
    and admission path startup has (issue #85: bootstrap is the strict
    caller that refuses gateway startup; recovery is the contained one).
    The ENTIRE lattice read — binding parse, digest lookup, file reads and
    admission — is contained: a lattice that fails returns ``None``
    instead of raising. Recovery runs at app construction, and one
    poisoned stored document (a derivation-unparseable descriptor, a
    drifted pin, truncated or structurally broken bytes) must never kill
    gateway startup. The failure is surfaced (logged, machine-prefixed,
    exception class named) and the caller skips run recovery for that
    lattice — finalising runs against a bench it could not admit would be
    the less safe direction.
    """
    try:
        return admit_fixture_lattice(fixtures_dir, now_wall=now_wall, contracts=contracts)
    except Exception as error:
        # Containment mirrors the executor seam's ruling: recovery runs at
        # app construction, so ANY failure here — a typed admission
        # rejection, truncated JSON, a missing pinned file, a structural
        # surprise — is logged with its class and skipped, never raised.
        _LOG.error("recovery_admission_rejected: %s: %s", type(error).__name__, error)
        return None


def _recover_interrupted_runs(
    store: Store,
    fixtures_dir: Path,
    *,
    emit_keep: int,
    now_iso: Callable[[], str],
    contracts: Path = _CONTRACTS,
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

    Issue #156 fix wave: ``recover_interrupted`` sweeps beyond lease
    holders — a queued ghost left by the bounded shutdown drain records
    ``interrupted``; a stale live projection over a durable terminal is
    reconciled (never re-finalised). Both dispositions close the queue
    projection below, so neither wedge can hold the §5 busy oracle past
    a restart.
    """
    docs = _recovery_documents(fixtures_dir, now_wall=now_iso(), contracts=contracts)
    if docs is None:
        # Startup survives a poisoned lattice; run recovery does not. The
        # dangling-request reconciliation below needs no admitted documents
        # and still runs — a wedged request id is repairable regardless.
        _LOG.error(
            "recovery_skipped: startup lattice failed admission; runs left for "
            "recovery after the lattice is repaired and the gateway restarts"
        )
        store.reconcile_dangling_requests()
        # Slice 1: capture staging orphaned by host death reclaims on the
        # same startup path, BOTH branches — a wedged capture quota is
        # repairable regardless of document admission (the sweep constructs
        # its own writer; no quota envelope is needed to only reclaim).
        CaptureStagingStore(store).reclaim_orphans(now_iso())
        return []
    coordinator = RunCoordinator(
        store, {}, SystemClock(), SystemClock(), docs, contracts=contracts
    )
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
    # Slice 1: the capture-staging sweep rides the same startup path (both
    # branches — see the lattice-failed early return above).
    CaptureStagingStore(store).reclaim_orphans(now_iso())
    bench_id = str(docs.bench["id"])
    for run_id in recovered:
        store.put_run_state(run_id, bench_id, "terminal", now_iso())
        # The disposition rides the durable record (the authority): a run
        # the sweep interrupted gets the interrupted reason; a run whose
        # record already existed is only being projection-reconciled.
        run = store.get_run(run_id)
        record = run["terminal"] if run is not None else None
        outcome = str(record.get("body_outcome")) if record is not None else ""
        reason = (
            RECOVERY_RUN_CHANGED_REASON
            if outcome == "interrupted"
            else RECOVERY_PROJECTION_REASON
        )
        _LOG.info(
            "run_changed (recovery) run_id=%s reason=%s",
            run_id, reason,
        )
        append_bench_event(
            store,
            "run_changed",
            bench_id,
            run_id,
            None,
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
        stream_host: RunStreamHost | None = None,
        services: RetainingServices | None = None,
        implementation_disclosures: list[str] | None = None,
        contracts: Path = _CONTRACTS,
    ) -> None:
        # The stream host rides BOTH layers: the base coordinator hands it
        # to the monitoring clock (the wait-slice driver), this subclass
        # arms and tears it down around the body.
        super().__init__(
            store, plugins, clock, wall, docs, stream_host=stream_host, contracts=contracts
        )
        self.implementation_disclosures = list(implementation_disclosures or [])
        self._retain = retain
        self._spool_dir = spool  # cleaned up when the coordinator is collected
        self._last_monitor: _RunMonitor | None = None
        # The activation wiring's composition surfaces (issue #167): the
        # run's stream host (bridges + controllers it constructed) and the
        # run services (the register_reading_sink surface R11 drives).
        self.stream_host = stream_host
        self.services = services

    def _prepare_run(self, run_id: str, principal_id: str) -> _PreparedRun:
        prepared = super()._prepare_run(run_id, principal_id)
        prepared.monitor.retain = self._retain
        self._last_monitor = prepared.monitor
        # Decision 3: arm AFTER monitor arming — the wrapped clock already
        # holds the stream host, and the subscribe dispatches run through
        # the wrapped plugins so monitor ticks wrap them like every
        # dispatch. A refusal degrades loudly inside ``arm``; it never
        # fails the run.
        if self.stream_host is not None and self.stream_host.devices:
            self.stream_host.arm(self._docs.bench, prepared.plugins, prepared.monitor)
        return prepared

    def _run_and_record(self, prepared: _PreparedRun) -> Any:
        body = super()._run_and_record(prepared)
        # Decision 5, clause 2: teardown at body end, BEFORE protection
        # (the protective transition dispatches through these bridges —
        # they stay open until the terminal record lands). The monitor
        # moves to the protecting phase so a terminal body cause cannot
        # block the ending's own dispatches; the phase is "protecting"
        # from here on either way.
        if self.stream_host is not None and self.stream_host.armed:
            prepared.monitor.phase = "protecting"
            # F2: a violation observed inside the teardown window still
            # escalates into the terminal record's reasons (via
            # cause_reasons, which _body_truth appends) — the body is
            # already over, so this NEVER re-arms cause-blocking; before
            # _finish_run arms engine.enter there is no other escalation
            # path, and the record would report a bare outcome over a
            # drifted bench.
            prepared.monitor.on_violation = lambda fresh, _now: (
                prepared.monitor.cause_reasons.extend(
                    reason
                    for reason in fresh
                    if reason not in prepared.monitor.cause_reasons
                )
            )
            try:
                self.stream_host.teardown(prepared.plugins)
            finally:
                prepared.monitor.on_violation = None
        return body

    def _body_truth(self, prepared: _PreparedRun, body: Any) -> tuple[str, list[str]]:
        """Append the run's implementation disclosures to the record's
        reasons (F3): which implementation produced the evidence — a
        commissioned closure (manifest digest) or the simulation-declared
        bench's declarative fallback — is part of the record, not just the
        gateway log."""
        outcome, reasons = super()._body_truth(prepared, body)
        for disclosure in self.implementation_disclosures:
            if disclosure not in reasons:
                reasons.append(disclosure)
        return outcome, reasons

    def start_run(self, run_id: str, principal_id: str) -> dict[str, Any]:
        # The last-resort sweep: after the terminal record and lease
        # release (protection needed the bridges open), close each
        # constructed bridge — its own final sweep of anything still live
        # plus the loader/runner release. Contained inside the host, and
        # the finally covers a raising lifecycle too (F1): bridges never
        # leak past the coordinator that owns them.
        try:
            record = super().start_run(run_id, principal_id)
        finally:
            if self.stream_host is not None:
                self.stream_host.close()
        return record

    @property
    def monitor(self) -> _RunMonitor | None:
        live = self._active_monitor
        if live is not None:
            self._last_monitor = live
        return self._last_monitor

    @property
    def plugins(self) -> dict[str, DevicePlugin]:
        """The run's constructed plugins keyed by bench device id.

        Read-only composition surface (the activation controls assert the
        bridge/sim split through it); the coordinator's own dispatch paths
        read the wrapped copies built per run, never this mapping.
        """
        return dict(self._plugins)


#: The quota keys an adapter-constructing run REQUIRES from gateway-local
#: operator configuration (design Decision 1: no silent defaults for
#: required ceilings — a missing key refuses the run before any device is
#: opened; the worker's poison guard contains the refusal honestly).
_QUOTA_REQUIRED_KEYS = ("max_dataset_bytes", "max_event_batch")


def _run_quota_limits(limits: dict[str, int]) -> QuotaLimits:
    """The run's ``QuotaLimits`` — the first production construction site.

    ``max_evidence_entries`` keeps its in-tree derivation (page size × 10,
    the same integer ``create_app`` derives for bench-event windows).
    ``max_capture_bytes``/``max_subscriptions`` take the fork-3 HINT
    defaults unless configured (the ``QuotaLimits`` docstring's posture:
    commissioned values come from bench qualification, A02).
    """
    missing = [key for key in _QUOTA_REQUIRED_KEYS if key not in limits]
    if missing:
        raise ValueError(
            "run_quota_config_absent: the run constructs adapter bridges, "
            "which require the gateway-local quota ceilings "
            + ", ".join(sorted(missing))
            + " in the app's limits mapping (env: BENCHWEAVE_MAX_DATASET_BYTES"
            " / BENCHWEAVE_MAX_EVENT_BATCH) — refusing before any device is opened"
        )
    return QuotaLimits(
        max_dataset_bytes=int(limits["max_dataset_bytes"]),
        max_evidence_entries=int(limits["max_page_size"]) * 10,
        max_event_batch=int(limits["max_event_batch"]),
        max_capture_bytes=int(limits.get("max_capture_bytes", 16 * 1024 * 1024)),
        max_subscriptions=int(limits.get("max_subscriptions", 16)),
    )


#: The commissioning evidence limitation that declares a simulated bench —
#: the same mark ``cli.report.SIMULATION_MARK`` derives the report's
#: simulation label from (the derivation lives here as a literal to keep
#: the interface layer off the CLI's import graph; report.py owns the
#: cross-surface pin).
_SIMULATION_MARK = "simulator-only"


def _bench_declares_simulation(commissioning: dict[str, Any]) -> bool:
    """True iff the commissioning evidence declares the bench simulated."""
    for entry in commissioning.get("evidence", []):
        if isinstance(entry, dict) and _SIMULATION_MARK in entry.get("limitations", []):
            return True
    return False


class _BridgePlan:
    """One adapter-mode device's commissioned construction plan."""

    def __init__(self, closure: DeviceClosure, descriptor: dict[str, Any], digest: str) -> None:
        self.closure = closure
        self.descriptor = descriptor
        self.digest = digest

    def disclosure(self, device_id: str) -> str:
        return (
            f"implementation_disclosure: device={device_id} "
            f"kind=commissioned-closure "
            f"manifest_sha256={self.closure.manifest_sha256[:12]}"
        )


class _SimPlan:
    """One device on the declarative fixture-sim leg.

    ``disclosure`` is set only when the plan is the simulation-declared
    bench's SUBSTITUTION for an uncommissioned adapter-mode device (the
    record-visible discriminator, F3); a non-adapter descriptor's own sim
    leg is the declared integration mode, not a substitution.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.disclosure: str | None = None


def _require_registry_session(session: RegistrySession | None) -> RegistrySession:
    """Narrow the optional session for the bridge-construction branch.

    A bridge plan only exists when the closure resolution had a session, so
    this never fires in practice — it keeps the narrowing explicit (and
    python -O honest) instead of an assert.
    """
    if session is None:
        raise RuntimeError(
            "run activation invariant violated: bridge plan without a "
            "registry session"
        )
    return session


def _device_plans(
    content: ContentStore,
    docs: AdmittedDocuments,
    bench_id: str,
    run_id: str,
    registry_session: RegistrySession | None,
) -> dict[str, _BridgePlan | _SimPlan]:
    """Survey the bench's devices WITHOUT running any plugin code.

    Per device (from the admitted bench document, each pinning a descriptor
    by digest): resolve the RAW descriptor from the content store; an
    ``integration.mode == "adapter"`` device whose declared generation
    carries an activation record plans a real bridge (Decision 1); anything
    else keeps the committed fixture-sim leg. The sim fallback for an
    adapter-mode device is the demo lattice's own posture — its devices
    declare the startup-admitted generation, which no admin act has
    commissioned — and is disclosed loudly, never silently taken.
    """
    plans: dict[str, _BridgePlan | _SimPlan] = {}
    sim_names = dict(_SIM_PLUGINS)
    simulated = _bench_declares_simulation(docs.commissioning)
    for device in docs.bench["devices"]:
        device_id = str(device["id"])
        digest = str(device["descriptor"]["sha256"])
        document = content.get_document(digest)
        if document is None:
            raise ValueError(
                f"run_device_descriptor_absent: pinned descriptor {digest[:12]}… "
                f"for device {device_id!r} is not stored"
            )
        descriptor = document["content"]
        integration = descriptor.get("integration") or {}
        if integration.get("mode") == "adapter":
            closure = commissioned_device_closure(
                registry_session, bench_id, device, descriptor
            )
            if closure is not None:
                plans[device_id] = _BridgePlan(closure, descriptor, digest)
                continue
            if device_id not in sim_names or not simulated:
                # F3: the fallback is a SIMULATION-declared bench's posture.
                # An unmarked bench (commissioning evidence without the
                # simulator-only limitation) never substitutes a simulator
                # for an uncommissioned adapter device — the device-id
                # collision with {psu, controller} is not authority.
                raise ValueError(
                    "run_device_implementation_absent: adapter-mode device "
                    f"{device_id!r} on bench {bench_id!r} declares generation "
                    f"{device.get('generation')!r} with no commissioned registry "
                    "closure, and the bench's commissioning does not declare "
                    "simulation — refusing to substitute a simulator "
                    "implementation for uncommissioned hardware"
                )
            _LOG.warning(
                "run_device_declarative_fallback: device=%s run=%s bench=%s "
                "adapter-mode descriptor has no commissioned closure for its "
                "declared generation; the simulation-declared bench runs the "
                "committed sim plugin",
                device_id, run_id, bench_id,
            )
            fallback = _SimPlan(sim_names[device_id])
            fallback.disclosure = (
                f"implementation_disclosure: device={device_id} "
                "kind=declarative-sim-fallback "
                f"reason=no-commissioned-closure-for-generation-{device.get('generation')}"
            )
            plans[device_id] = fallback
            continue
        if device_id in sim_names:
            plans[device_id] = _SimPlan(sim_names[device_id])
    return plans


def _build_run_factory(
    fixtures_dir: Path,
    now_iso: Callable[[], str],
    *,
    limits: dict[str, int],
    registry_session: RegistrySession | None = None,
    contracts: Path = _CONTRACTS,
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

        Issue #167 activation wiring (design Decision 1): adapter-mode
        bench devices with a commissioned registry closure construct real
        ``OTDPBridge`` instances here — capture/stream services over the
        worker-thread store, one shared ``ReadingSinks``, one run context
        key — and the committed fixture-sim tuple remains the declarative
        fallback leg. The quota seam refuses loudly BEFORE any device is
        opened when an adapter bridge would construct without the required
        operator ceilings. Every constructed bridge is adopted by the
        stream host, so every exit path that abandons the build closes
        them (F1) — the Runner and adapter session never leak.
        """
        content = ContentStore(worker_store)
        spool = tempfile.TemporaryDirectory(prefix=f"stg-run-{run_id}-")
        docs = admit_documents(
            **_spool_documents(content, binding_ref, fixtures_dir, Path(spool.name)),
            now_wall=now_iso(),
            contracts=contracts,
        )
        clock = SystemClock()
        bench_id = str(docs.bench["id"])
        plans = _device_plans(content, docs, bench_id, run_id, registry_session)
        bridges = [plan for plan in plans.values() if isinstance(plan, _BridgePlan)]
        quota_limits = _run_quota_limits(limits) if bridges else None
        # One shared ReadingSinks for the WHOLE run (Decision 2): the run
        # services and every stream controller constructed below see the
        # same instance, so a sink registered through
        # ``register_reading_sink`` receives readings any stream lands.
        sinks = ReadingSinks()
        # The streaming-slice members (emit_event, register_reading_sink)
        # get the run's context key and a fresh-stamp clock: an emitted host
        # event lands on the run's event dimension with a live timestamp.
        services = RetainingServices(
            content,
            quota=int(limits["max_page_size"]) * 10,
            now=now_iso(),
            wall=now_iso,
            context_key=f"run:{run_id}",
            reading_sinks=sinks,
        )
        simulated = _bench_declares_simulation(docs.commissioning)
        context_key = f"run:{run_id}"
        stream_host = RunStreamHost(run_id=run_id, clock=clock)
        plugins: dict[str, DevicePlugin] = {}
        # F1: every exit path that leaves opened bridges behind closes them
        # through the host before the refusal propagates — a construction
        # failure mid-loop (or a coordinator that never materialises) must
        # not leak the Runner and adapter session.
        try:
            for device_id, plan in plans.items():
                if isinstance(plan, _BridgePlan):
                    if quota_limits is None:
                        # Survives python -O: the survey above guarantees
                        # the seam refused already when the keys were
                        # missing.
                        raise RuntimeError(
                            "run activation invariant violated: bridge plan "
                            "without constructed quota limits"
                        )
                    writer = CaptureStagingStore(
                        worker_store,
                        max_capture_bytes=quota_limits.max_capture_bytes,
                        max_dataset_bytes=quota_limits.max_dataset_bytes,
                    )
                    bundle, capture_controller = build_capture_services(
                        descriptor_digest=plan.digest,
                        content=content,
                        writer=writer,
                        # M2 timebase identity: seconds = nanoseconds / 1e9
                        # of the SAME clock the coordinator and poll engine
                        # slice on (the design's Decision-3/5 pin).
                        clock=lambda: clock.now_ns() / 1e9,
                        wall=now_iso,
                        quota=quota_limits,
                        context_key=context_key,
                    )
                    stream_controller = build_stream_services(
                        descriptor_digest=plan.digest,
                        store=worker_store,
                        wall=now_iso,
                        quota=quota_limits,
                        context_key=context_key,
                        reading_sinks=sinks,
                    )
                    bridge = load_otdp_plugin(
                        _require_registry_session(registry_session).cache_root,
                        plan.closure.manifest,
                        plan.closure.manifest_sha256,
                        entry_relpath=plan.closure.entry_relpath,
                        descriptor=plan.descriptor,
                        services=bundle,
                        simulation=SimulationInfo(
                            simulated=simulated,
                            label=str(plan.descriptor.get("id") or device_id),
                        ),
                        capture=capture_controller,
                        stream=stream_controller,
                    )
                    bridge.plugin_open(bundle)
                    plugins[device_id] = bridge
                    if stream_controller is not None:
                        stream_host.register(device_id, bridge, stream_controller)
                    else:
                        # F1: end-of-run close authority is ownership — a
                        # commissioned bridge without event services is
                        # adopted for close all the same.
                        stream_host.adopt(device_id, bridge)
                    continue
                plugin = _load_sim_plugin(plan.name).create_plugin(
                    now_fn=clock.now_iso, monotonic_ns_fn=clock.now_ns
                )
                plugin.plugin_open(services)
                plugins[device_id] = plugin
            disclosures = [
                plan.disclosure(device_id)
                for device_id, plan in plans.items()
                if isinstance(plan, _BridgePlan)
            ] + [
                plan.disclosure
                for plan in plans.values()
                if isinstance(plan, _SimPlan) and plan.disclosure is not None
            ]
            return _RetainingCoordinator(
                worker_store,
                plugins,
                clock,
                clock,
                docs,
                # The monitor's retain hook is one-argument (the snapshot
                # dict); RetainingServices keys evidence per context — one
                # context per run, so the run's quota bounds its snapshot
                # retentions.
                retain=lambda snapshot: services.retain_evidence(f"run:{run_id}", snapshot),
                spool=spool,
                stream_host=stream_host,
                services=services,
                implementation_disclosures=disclosures,
                contracts=contracts,
            )
        except BaseException:
            stream_host.close()
            raise

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
    execution_corpus: CorpusResolution = CorpusResolution.ACTIVE,
) -> FastAPI:
    """Compose the gateway: gate, worker (limits mandated), seam, MCP mount.

    ``execution_corpus`` (issue #176 increment 2, design §1b) is the
    dev-corpus resolution seam: a keyword-only composition parameter with
    no env, config, or wire surface — the only code-level opt-in is the
    enum, and no production caller passes it. ``DEV_HEAD`` resolves the
    manifest-declared execution head ONCE, here at composition, and the
    resulting directory threads the existing injection path (worker build
    factory, startup admission, run recovery); ``ACTIVE`` — the default —
    resolves the frozen ``execution/0.1.0`` literal, byte-identical to
    today's posture. A wheel-installed gateway cannot resolve ``DEV_HEAD``
    (the head never exports) and refuses loudly rather than degrading; a
    stray ``DEV_HEAD`` after the promotion's teardown refuses
    ``execution_dev_head_absent:`` — the seam self-retires.
    """
    gate = WriteGate()
    # The seam resolves once, here: the directory threads the injection
    # path, nothing downstream re-resolves.
    if execution_corpus is CorpusResolution.DEV_HEAD:
        contracts = declared_dev_family("execution")
    else:
        contracts = _CONTRACTS
    # Same retention arithmetic as the seam's bench-event windows.
    quota = int(limits["max_page_size"]) * 10
    worker = RunWorker(
        store,
        content,
        build_run=_build_run_factory(
            fixtures_dir,
            now_iso,
            limits=limits,
            registry_session=registry_session,
            contracts=contracts,
        ),
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
                admit_startup_bench(
                    store, content, fixtures_dir, now=now_iso(), contracts=contracts
                )
                # Task 11 wiring: a restarted gateway closes what a dead process
                # left open before it serves or executes anything new.
                _recover_interrupted_runs(
                    store,
                    fixtures_dir,
                    emit_keep=quota,
                    now_iso=now_iso,
                    contracts=contracts,
                )
            worker.start()
            try:
                async with mcp_app.lifespan(app):
                    yield
            finally:
                worker.stop()
                if not worker.join(timeout=5.0):
                    # Issue #156: the join bound is now real — a wedged or
                    # dead worker no longer hangs shutdown forever. The
                    # unwind is the CTL-9 honest one: the startup recovery
                    # sweep records outstanding runs `interrupted` (a run
                    # whose durable record already completed only has its
                    # stale projection reconciled).
                    _LOG.error(
                        "run worker did not drain at shutdown"
                        " (submitted=%d done=%d); outstanding runs are"
                        " recorded interrupted at next startup",
                        worker.submitted,
                        worker.done,
                    )
        finally:
            if hold is not None:
                hold.release()

    app = FastAPI(title="BenchWeave gateway", version="0.1.0", lifespan=_lifespan)
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
