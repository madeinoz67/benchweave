"""WP07 Task 5: run_start 202-parity, §9 scoped dedup, leases, queue states.

Unit level: the worker executes a FakeCoordinator with RunCoordinator's
public API (the real coordinator is exercised end-to-end in Task 11), so
these tests pin the seam contract — §9 principal-scoped request keys, the
202-accept/dedup/conflict decision, queue-state transitions accepted →
running → terminal, the lease lifecycle, and the monitor's retention hook.
Projections are checked against the vendored interface-v1.1.0 ``run`` and
``lease`` defs (closed objects; the shapes must stay contract-legal).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.control.clocking import TestClock
from benchweave.control.coordinator import _RunMonitor
from benchweave.control.documents import admit_documents
from benchweave.host.plugin import DevicePlugin
from benchweave.interfaces import errors, operations
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.worker import RunWorker
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "plugins"
BENCH_ID = "sim-bench"  # the bootstrap bench (fixtures/execution/bench.json)
DESCRIPTORS = {
    "psu": FIXTURES / "descriptor-sim-psu.json",
    "controller": FIXTURES / "descriptor-sim-controller.json",
}
NOW = "2026-09-12T00:00:00Z"
LIMITS = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}


def _control(principal: str) -> Identity:
    return Identity(principal, "stg", frozenset({"stg:control"}), 2**31)


def _await_coordinator(
    coordinators: list[FakeCoordinator], timeout: float = 5.0
) -> FakeCoordinator:
    """Wait for the worker to build AND enter a coordinator (both are
    asynchronous relative to run_start's return)."""
    deadline = time.monotonic() + timeout
    while not coordinators and time.monotonic() < deadline:
        time.sleep(0.01)
    assert coordinators, "worker never built a coordinator"
    assert coordinators[0].entered.wait(timeout=timeout), "run never entered start_run"
    return coordinators[0]


class FakeCoordinator:
    """RunCoordinator stand-in: same constructor shape and public API.

    ``start_run`` is synchronous like the real one but blocks on a release
    event, so queue-state transitions are observable; ``entered`` fires once
    the run is actually in-flight (deterministic waiting for cancel tests).
    """

    def __init__(
        self,
        store: Store,
        plugins: dict[str, DevicePlugin],
        clock: object,
        wall: object,
        docs: object,
        *,
        release: threading.Event,
    ) -> None:
        self.store_arg = store  # the worker-thread Store build_run received
        del plugins, clock, wall, docs  # constructor-shape parity only
        self._release = release
        self.entered = threading.Event()
        self.started: list[tuple[str, str]] = []
        self.cancelled: list[tuple[str, str]] = []

    def start_run(self, run_id: str, principal_id: str) -> dict[str, Any]:
        self.started.append((run_id, principal_id))
        self.entered.set()
        self._release.wait(timeout=30)
        return {
            "run_id": run_id,
            "body_outcome": "completed",
            "outcome": "passed",
            "safe_state": "verified",
        }

    def cancel(self, run_id: str, principal_id: str) -> None:
        self.cancelled.append((run_id, principal_id))

    def recover_interrupted(self) -> list[str]:
        return []


@dataclass
class SeamControl:
    """The seam fixture: unpacks as (ops, worker, release) with named extras."""

    ops: Operations
    worker: RunWorker
    release: threading.Event
    store: Store
    binding_ref: dict[str, Any]
    coordinators: list[FakeCoordinator]

    def __iter__(self) -> Iterator[Any]:
        """Unpack as (ops, worker, release) — the brief's tests' shape."""
        yield self.ops
        yield self.worker
        yield self.release


@pytest.fixture()
def seam_control(tmp_path: Path) -> Iterator[SeamControl]:
    store = Store.open(tmp_path / "state.db")
    content = ContentStore(store)
    admit_startup_bench(store, content, FIXTURES, now=NOW)
    binding_raw = (FIXTURES / "run-binding.json").read_bytes()
    binding_doc = json.loads(binding_raw)
    binding_ref = {
        "id": str(binding_doc["request_id"]),
        "version": str(binding_doc["contract_version"]),
        "sha256": hashlib.sha256(binding_raw).hexdigest(),
    }
    release = threading.Event()
    coordinators: list[FakeCoordinator] = []

    def build_run(
        run_id: str, principal_id: str, binding: dict[str, Any], run_store: Store
    ) -> FakeCoordinator:
        del run_id, principal_id, binding
        coordinator = FakeCoordinator(run_store, {}, None, None, None, release=release)
        coordinators.append(coordinator)
        return coordinator

    worker = RunWorker(store, content, build_run=build_run, now_iso=lambda: NOW)
    worker.start()
    ops = operations.Operations(
        store,
        content,
        gateway_id="gw-test",
        limits=LIMITS,
        worker=worker,
        now_iso=lambda: NOW,
    )
    yield SeamControl(ops, worker, release, store, binding_ref, coordinators)
    release.set()  # unblock any in-flight fake before draining and joining
    worker.stop()
    worker.join(timeout=10)
    store.close()


# --- §9 scoped request keys -----------------------------------------------------


def test_scoped_request_key_is_sha256_of_scoped_triple() -> None:
    expected = hashlib.sha256(b"p1|run_start|req-1").hexdigest()
    assert operations.scoped_request_key("p1", "run_start", "req-1") == expected
    assert operations.scoped_request_key("p2", "run_start", "req-1") != expected


# --- run_start: acceptance, dedup, §9 scoping -----------------------------------


def test_run_start_is_idempotent_per_principal(seam_control: SeamControl) -> None:
    ops, worker, _ = seam_control
    ident = _control("p1")
    ref = seam_control.binding_ref
    first = ops.run_start(ident, BENCH_ID, "req-1", ref, 1, None)
    second = ops.run_start(ident, BENCH_ID, "req-1", ref, 1, None)
    assert first["run_id"] == second["run_id"]
    assert worker.submitted == 1  # dedup hit, no second submit


def test_request_id_is_principal_scoped(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    p1 = _control("p1")
    p2 = _control("p2")
    ref = seam_control.binding_ref
    one = ops.run_start(p1, BENCH_ID, "same-id", ref, 1, None)
    two = ops.run_start(p2, BENCH_ID, "same-id", ref, 1, None)
    assert one["run_id"] != two["run_id"]  # separate namespaces (§9)
    assert ops.run_find(p1, "same-id")["run_id"] == one["run_id"]
    assert ops.run_find(p2, "same-id")["run_id"] == two["run_id"]


def test_expected_generation_mismatch_conflicts(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    ident = _control("p1")
    with pytest.raises(errors.OperationFailure) as exc:
        ops.run_start(ident, BENCH_ID, "req-x", seam_control.binding_ref, 999, None)
    assert exc.value.failure.code == "conflict"


def test_generation_fence_reads_canonical_authority(seam_control: SeamControl) -> None:
    """Decision 4: the generations table is THE authority. A bare
    bump_generation (no bench-row refresh) must fence a stale client —
    run_start and lease_create both bite on expected_generation=1."""
    ops, _, _ = seam_control
    seam_control.store.bump_generation(BENCH_ID, NOW)  # authority now 2
    with pytest.raises(errors.OperationFailure) as exc:
        ops.run_start(
            _control("p1"), BENCH_ID, "req-g", seam_control.binding_ref, 1, None
        )
    assert exc.value.failure.code == "conflict"
    with pytest.raises(errors.OperationFailure) as exc:
        ops.lease_create(_control("p1"), BENCH_ID, "lease-req-g", 1, 1000)
    assert exc.value.failure.code == "conflict"


def test_run_start_reused_request_with_different_body_conflicts(
    seam_control: SeamControl,
) -> None:
    ops, _, _ = seam_control
    ident = _control("p1")
    other = dict(seam_control.binding_ref, version="9.9.9")
    ops.run_start(ident, BENCH_ID, "req-d", seam_control.binding_ref, 1, None)
    with pytest.raises(errors.OperationFailure) as exc:
        ops.run_start(ident, BENCH_ID, "req-d", other, 1, None)
    assert exc.value.failure.code == "conflict"


def test_run_start_requires_control_tier(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    observer = Identity("p1", "stg", frozenset({"stg:observe"}), 2**31)
    with pytest.raises(errors.OperationFailure) as exc:
        ops.run_start(observer, BENCH_ID, "req-o", seam_control.binding_ref, 1, None)
    assert exc.value.failure.code == "forbidden"


# --- run projection + queue states ------------------------------------------------


def test_run_state_reaches_terminal_after_worker_drains(seam_control: SeamControl) -> None:
    ops, worker, release = seam_control
    coordinators = seam_control.coordinators
    ident = _control("p1")
    run = ops.run_start(ident, BENCH_ID, "req-9", seam_control.binding_ref, 1, None)
    assert run["state"] == "accepted"
    assert run["revision"] == 1
    assert run["outcome"] is None and run["safe_state"] is None
    coordinator = _await_coordinator(coordinators)
    release.set()
    joined_at = time.monotonic()
    worker.join(timeout=10)  # no stop() yet: the fast path must return now
    assert time.monotonic() - joined_at < 5, "join burned the full thread timeout"
    assert coordinator.store_arg is not seam_control.store  # worker-thread Store
    final = ops.run_get(ident, run["run_id"])
    assert final["state"] == "terminal"
    assert final["revision"] == 3  # accepted → running → terminal
    assert final["outcome"] == "outcome_unknown"  # no durable terminal record yet
    assert coordinator.started == [(run["run_id"], "p1")]


def test_run_get_unknown_run_not_found(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    with pytest.raises(errors.OperationFailure) as exc:
        ops.run_get(_control("p1"), "run-nope")
    assert exc.value.failure.code == "not_found"


def test_run_find_unknown_request_not_found(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    with pytest.raises(errors.OperationFailure) as exc:
        ops.run_find(_control("p1"), "never-filed")
    assert exc.value.failure.code == "not_found"


def test_run_cancel_forwards_to_active_coordinator(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    coordinators = seam_control.coordinators
    ident = _control("p1")
    run = ops.run_start(ident, BENCH_ID, "req-c", seam_control.binding_ref, 1, None)
    coordinator = _await_coordinator(coordinators)
    ops.run_cancel(ident, run["run_id"], "req-c", "operator requested")
    assert coordinator.cancelled == [(run["run_id"], "p1")]


# --- run_check: advisory preflight -------------------------------------------------


def test_run_check_reports_valid_generation_and_findings(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    result = ops.run_check(_control("p1"), BENCH_ID, seam_control.binding_ref)
    assert result == {"valid": True, "generation": 1, "findings": []}


def test_run_check_flags_unknown_binding_document(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    ref = dict(seam_control.binding_ref, sha256="0" * 64)
    result = ops.run_check(_control("p1"), BENCH_ID, ref)
    assert result["valid"] is False
    assert result["generation"] == 1
    assert result["findings"] == [
        {
            "field": "binding_ref.sha256",
            "reason": f"binding document {'0' * 64} is not stored",
        }
    ]


# --- leases -------------------------------------------------------------------------


def test_lease_create_renew_release_lifecycle(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    ident = _control("p1")
    lease = ops.lease_create(ident, BENCH_ID, "lease-req-1", 1, 1000)
    assert lease == {
        "lease_id": lease["lease_id"],
        "bench_id": BENCH_ID,
        "sequence": 1,
        "expires_at": "2026-09-12T00:00:01Z",  # fixed clock + 1000 ms
        "state": "active",
    }
    renewed = ops.lease_renew(ident, lease["lease_id"], "lease-req-1", 1, 2000)
    assert renewed["lease_id"] == lease["lease_id"]
    assert renewed["sequence"] == 2
    assert renewed["state"] == "active"
    assert renewed["expires_at"] == "2026-09-12T00:00:02Z"
    released = ops.lease_release(ident, lease["lease_id"], "lease-req-1", "done testing")
    assert released["state"] == "released"
    with pytest.raises(errors.OperationFailure) as exc:
        ops.lease_release(ident, lease["lease_id"], "lease-req-1", "already gone")
    assert exc.value.failure.code == "not_found"


def test_lease_renew_by_non_holder_forbidden(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    lease = ops.lease_create(_control("p1"), BENCH_ID, "lease-req-2", 1, 1000)
    with pytest.raises(errors.OperationFailure) as exc:
        ops.lease_renew(
            _control("p2"), lease["lease_id"], "lease-req-2", lease["sequence"], 1000
        )
    assert exc.value.failure.code == "forbidden"


def test_lease_renew_stale_sequence_conflicts(seam_control: SeamControl) -> None:
    ops, _, _ = seam_control
    ident = _control("p1")
    lease = ops.lease_create(ident, BENCH_ID, "lease-req-3", 1, 1000)
    with pytest.raises(errors.OperationFailure) as exc:
        ops.lease_renew(ident, lease["lease_id"], "lease-req-3", 99, 1000)
    assert exc.value.failure.code == "conflict"


# --- monitor retention hook (WP05 inertness + evidence) ------------------------------


class _NullServices:
    """Scoped-services stand-in; the sim plugins only store the reference."""

    def resolve_content(self, content_id: str) -> bytes:
        return b"{}"

    def retain_evidence(self, key: str, payload: bytes) -> str:
        return f"evidence-{key}"

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        pass

    def quota_state(self) -> dict[str, int]:
        return {"dataset_bytes_used": 0, "evidence_entries_used": 0, "events_emitted": 0}

    def register_reading_sink(self, sink: Any) -> None:
        pass


def _load_plugin(name: str) -> ModuleType:
    path = PLUGINS_ROOT / name / "plugin.py"
    assert path.is_file(), f"plugin file missing: {path}"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sim_plugins(clock: TestClock) -> dict[str, DevicePlugin]:
    """Both sim plugins on the SAME clock the monitor will use (WP05 shape)."""
    plugins: dict[str, DevicePlugin] = {}
    for device_id, name in (("psu", "sim_psu"), ("controller", "sim_controller")):
        plugin = _load_plugin(name).create_plugin(
            now_fn=clock.now_iso, monotonic_ns_fn=clock.now_ns
        )
        plugin.plugin_open(_NullServices())
        plugins[device_id] = plugin
    return plugins


def _monitor_for(tmp_path: Path, clock: TestClock) -> tuple[_RunMonitor, Store]:
    docs = admit_documents(
        procedure_path=FIXTURES / "procedure-voltage-check.json",
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=FIXTURES / "run-binding.json",
        commissioning_path=FIXTURES / "commissioning.json",
        descriptor_paths=DESCRIPTORS,
    )
    store = Store.open(tmp_path / "monitor.db")
    monitor = _RunMonitor(
        store,
        BENCH_ID,
        docs.policy,
        docs.bench,
        _sim_plugins(clock),
        clock,
        clock,
        run_id="run-monitor",
        lease_sequence=1,
    )
    monitor.phase = "body"
    return monitor, store


def test_monitor_retention_hook_evidence_and_failure_counts(tmp_path: Path) -> None:
    clock = TestClock()
    monitor, store = _monitor_for(tmp_path, clock)
    try:
        monitor.tick()  # retain is None: the hook is inert on a clean run
        assert monitor.snapshot_evidence == []
        assert monitor.retention_failures == 0

        retained: list[dict[str, Any]] = []

        def retain_ok(snapshot: dict[str, Any]) -> str:
            retained.append(snapshot)
            return f"ev-{len(retained)}"

        monitor.retain = retain_ok
        monitor.tick()
        assert retained  # a real signal snapshot was retained
        assert "dut-voltage" in retained[0]
        assert monitor.snapshot_evidence == [f"ev-{i + 1}" for i in range(len(retained))]
        assert monitor.retention_failures == 0

        def retain_boom(snapshot: dict[str, Any]) -> str:
            raise RuntimeError("retention sink down")

        monitor.retain = retain_boom
        monitor.tick()
        assert monitor.retention_failures == 1
        assert len(monitor.snapshot_evidence) == len(retained)  # failures append nothing
    finally:
        store.close()
