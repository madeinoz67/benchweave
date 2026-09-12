# tests/integration/test_registry_reuse.py
"""WP06 acceptance: clean-install reuse and the pre-activation fault vectors.

PRD-02: a second clean installation — fresh trust roots, fresh high-water
map, fresh cache and lock, same origin — pins byte-identical manifest
digests, and the plugin it activates from its own content-addressed cache
executes the published configure → output → measure contract vector. The
WP05 control stack then runs the fixture procedure end-to-end on that
cache-loaded plugin (``passed`` terminal record); the cache plugin is carried
onto the coordinator's clock through a test-local seam because ``load_plugin``
anchors its default monotonic at load while the executor computes deadlines
on its own injected clock.

PRD-03: every fault vector — wrong trust root, tampered manifest, revocation,
status rollback, origin collision — is rejected before anything is activated:
no cache directory, no lock file.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from benchweave.control.clocking import TestClock
from benchweave.control.coordinator import RunCoordinator
from benchweave.control.documents import AdmittedDocuments, admit_documents
from benchweave.host import QuotaState
from benchweave.host.plugin import DevicePlugin
from benchweave.host.services import HostServices
from benchweave.host.types import (
    ErrorCode,
    OperationRequest,
    OperationResult,
    OperationVerb,
)
from benchweave.registry.activation import load_plugin
from benchweave.registry.admission import (
    AdmissionLimits,
    AdmissionRejected,
    Admitted,
    Approval,
    admit,
)
from benchweave.registry.authenticity import (
    AuthenticityRejected,
    TrustRoot,
    load_trust_root,
)
from benchweave.registry.manifests import Key
from benchweave.registry.resolver import (
    LocalDirectorySource,
    OriginConfig,
    PackageSource,
    ResolvedClosure,
    Resolver,
)
from benchweave.state.store import Store

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures" / "registry"
EXECUTION_FIXTURES = REPO / "fixtures" / "execution"
PLUGINS_ROOT = REPO / "plugins"
NOW_NS = int(datetime(2026, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)
RUN_ID = "run-1"
SIM_PSU = "benchweave/sim-psu"
DESC_PACKAGE = "benchweave/sim-psu-descriptor"
DESC_KEY: Key = ("origin-main", DESC_PACKAGE, "1.0.0")

# The configure/output/measure vectors, verbatim from
# tests/contract/test_sim_plugins.py (the construction authority).
ACTION_CONFIGURE = "otdp.dc_psu.configure/1.0.0"
ACTION_OUTPUT = "otdp.dc_psu.output/1.0.0"
ACTION_MEASURE = "otdp.dc_psu.measure/1.0.0"
CONFIGURE_INPUT: dict[str, Any] = {
    "configuration_id": "cfg-1",
    "channel": "ch1",
    "voltage_v": 5.0,
    "current_limit_a": 0.5,
    "ovp_v": 5.5,
    "ocp_a": 0.5,
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _main_root() -> TrustRoot:
    return load_trust_root("origin-main", REG / "keys" / "main.pub.pem")


def _origins(
    *,
    main_root: TrustRoot | None = None,
    main_source: PackageSource | None = None,
    include_origin_b: bool = False,
) -> dict[str, OriginConfig]:
    origins: dict[str, OriginConfig] = {
        "origin-main": OriginConfig(
            registry_id="origin-main",
            root=main_root if main_root is not None else _main_root(),
            source=main_source if main_source is not None else LocalDirectorySource(
                REG / "origin-main"
            ),
            namespaces=("benchweave",),
        )
    }
    if include_origin_b:
        # Carries benchweave/sim-psu under a different trust root; present,
        # never routed — the collision this file pins must never redirect.
        origins["origin-b"] = OriginConfig(
            registry_id="origin-b",
            root=load_trust_root("origin-b", REG / "keys" / "originb.pub.pem"),
            source=LocalDirectorySource(REG / "origin-b"),
            namespaces=(),
        )
    return origins


def _resolve(
    source: PackageSource | None = None,
    *,
    high_water: dict[Key, int] | None = None,
    include_origin_b: bool = False,
) -> ResolvedClosure:
    return Resolver(
        _origins(main_source=source, include_origin_b=include_origin_b)
    ).resolve(
        "origin-main",
        SIM_PSU,
        "1.0.0",
        now_ns=NOW_NS,
        high_water=high_water if high_water is not None else {},
    )


def _admit(closure: ResolvedClosure, work: Path) -> Admitted:
    return admit(
        closure,
        cache_root=work / "cache",
        lock_path=work / "packages.lock.json",
        limits=AdmissionLimits(
            max_archive_bytes=1_000_000, max_files=100, max_unpacked_bytes=1_000_000
        ),
        approval=Approval(
            principal_id="benchweave-test",
            approved_at="2026-09-12T00:00:00Z",
            policy_id="local-policy",
            policy_version="1.0.0",
        ),
        now_ns=NOW_NS,
        roots={"origin-main": _main_root()},
    )


def _install(work: Path, *, include_origin_b: bool = False) -> tuple[ResolvedClosure, Admitted]:
    """One clean installation: fresh roots, fresh high-water, fresh cache and lock."""
    closure = _resolve(include_origin_b=include_origin_b)
    return closure, _admit(closure, work)


def _sim_psu_release(closure: ResolvedClosure) -> Any:
    return next(r for r in closure.releases if r.package_id == SIM_PSU)


def _drop_in_fault(origin: Path, fault: str) -> None:
    """Copy the committed origin tree, then overlay a fault status drop-in."""
    shutil.copytree(REG / "origin-main", origin, dirs_exist_ok=True)
    fault_dir = REG / "faults" / fault / DESC_PACKAGE / "1.0.0"
    target = origin / DESC_PACKAGE / "1.0.0"
    shutil.copy2(fault_dir / "status.json", target / "status.json")
    shutil.copy2(fault_dir / "status.sig", target / "status.sig")


class _NullServices:
    """Scoped-services stand-in; the sim plugins only store the reference.

    One typing repair over the test_procedures double, mirroring the
    activation test: ``quota_state`` returns the typed ``QuotaState`` the
    ``HostServices`` protocol requires.
    """

    def resolve_content(self, content_id: str) -> bytes:
        return b"{}"

    def retain_evidence(self, key: str, payload: bytes) -> str:
        return f"evidence-{key}"

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        pass

    def quota_state(self) -> QuotaState:
        return QuotaState(dataset_bytes_used=0, evidence_entries_used=0, events_emitted=0)

    def register_reading_sink(self, sink: Any) -> None:
        pass


class _RecordingPlugin:
    """DevicePlugin wrapper capturing every dispatched request and deadline."""

    def __init__(self, inner: DevicePlugin) -> None:
        self._inner = inner
        self.calls: list[tuple[OperationRequest, int]] = []

    @property
    def simulation(self) -> Any:
        return self._inner.simulation

    def plugin_open(self, services: HostServices) -> None:
        self._inner.plugin_open(services)

    def plugin_close(self) -> None:
        self._inner.plugin_close()

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        self.calls.append((request, deadline_ns))
        return self._inner.dispatch(request, deadline_ns=deadline_ns)


def _load_plugin_module(name: str) -> ModuleType:
    """Explicit-path module loader, mirrored from test_procedures/_sim_plugins."""
    path = PLUGINS_ROOT / "benchweave" / name / "src" / f"benchweave_{name}" / "plugin.py"
    assert path.is_file(), f"plugin file missing: {path}"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _invoke(action_id: str, input_: dict[str, Any]) -> OperationRequest:
    """Verbatim construction from test_sim_plugins._invoke."""
    return OperationRequest(
        operation_id="op-1",
        verb=OperationVerb.INVOKE,
        arguments={"action_id": action_id, "input": input_},
    )


def _execution_docs() -> AdmittedDocuments:
    """The WP05 executable fixture set, mirrored from test_procedures.admit."""
    return admit_documents(
        procedure_path=EXECUTION_FIXTURES / "procedure-voltage-check.json",
        policy_path=EXECUTION_FIXTURES / "safety-policy.json",
        bench_path=EXECUTION_FIXTURES / "bench.json",
        binding_path=EXECUTION_FIXTURES / "run-binding.json",
        commissioning_path=EXECUTION_FIXTURES / "commissioning.json",
        descriptor_paths={
            "psu": EXECUTION_FIXTURES / "descriptor-sim-psu.json",
            "controller": EXECUTION_FIXTURES / "descriptor-sim-controller.json",
        },
    )


# --- PRD-02: second clean install reuses the same digests, and runs ----------


def test_second_clean_install_reuses_same_digests_and_runs(tmp_path: Path) -> None:
    _closure_a, install_a = _install(tmp_path / "install-a")
    closure_b, install_b = _install(tmp_path / "install-b")

    # Two independent installations of the same origin pin the exact same
    # manifest digest set (sorted, stable tuple) and the same lock bytes.
    assert install_a.manifest_sha256s == install_b.manifest_sha256s
    assert len(install_b.manifest_sha256s) == 3  # sim-psu + descriptor + profile
    assert install_a.lock_sha256 == install_b.lock_sha256
    for work, admitted in (
        (tmp_path / "install-a", install_a),
        (tmp_path / "install-b", install_b),
    ):
        assert (work / "packages.lock.json").is_file()
        assert sorted(p.name for p in (work / "cache").iterdir()) == sorted(
            [*admitted.manifest_sha256s, "high-water.json"]
        )

    # ...and runs: the second installation's plugin loads from ITS cache and
    # executes the contract configure → output → measure vector.
    release = _sim_psu_release(closure_b)
    plugin = load_plugin(
        tmp_path / "install-b" / "cache",
        release.manifest,
        release.manifest_sha256,
        entry_relpath="plugin/plugin.py",
    )
    # Regression pin: the loader imports the entry under a module name
    # suffixed with the manifest sha (registry.activation.load_plugin), so
    # this instance is provably the cache-loaded module, not a same-bytes
    # in-repo import that would pass every behavioral assertion below.
    assert type(plugin).__module__.endswith(release.manifest_sha256)
    assert plugin.simulation.simulated is True
    plugin.plugin_open(_NullServices())
    try:
        configured = plugin.dispatch(
            _invoke(ACTION_CONFIGURE, CONFIGURE_INPUT), deadline_ns=10**12
        )
        assert configured.status.value == "ok"
        assert configured.data["result"]["configuration_id"] == "cfg-1"
        output = plugin.dispatch(
            _invoke(
                ACTION_OUTPUT,
                {"channel": "ch1", "enabled": True, "configuration_id": "cfg-1"},
            ),
            deadline_ns=10**12,
        )
        assert output.status.value == "ok"
        assert output.data["result"]["enabled"] is True
        measured = plugin.dispatch(
            _invoke(ACTION_MEASURE, {"configuration_id": "cfg-1", "channels": ["ch1"]}),
            deadline_ns=10**12,
        )
        assert measured.status.value == "ok"
        dataset = measured.data["result"]
        assert dataset["kind"] == "scalar_set"
        assert [v["id"] for v in dataset["variables"]] == ["voltage", "current", "power"]
        scalars = {v["id"]: v["values"][0] for v in dataset["variables"]}
        assert all(
            isinstance(value, float) and math.isfinite(value) for value in scalars.values()
        )
        assert scalars["voltage"] == 5.0
    finally:
        plugin.plugin_close()


def test_control_stack_run_on_cached_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The WP05 coordinated run over a registry-admitted cache plugin.

    Harness mirrored from test_procedures.test_start_run_full_pass_over_
    pristine_fixture with ONE substitution: the sim_psu instance comes from
    ``load_plugin`` over the admitted cache instead of the plugins tree.
    """
    closure, _admitted = _install(tmp_path / "registry")
    release = _sim_psu_release(closure)

    clock = TestClock()
    # CLOCK CARRY (test-local seam): load_plugin's default clock is a
    # zero-based monotonic anchored at load, while the coordinator computes
    # every deadline on its own injected clock. Swap the loader's clock
    # source for the run's TestClock so the cache-loaded plugin shares the
    # executor's timebase. The plugin is still imported and constructed by
    # load_plugin from the content-addressed cache; only its clock differs.
    monkeypatch.setattr(
        "benchweave.registry.activation._default_clock",
        lambda: (clock.now_iso, clock.now_ns),
    )
    cached_psu = load_plugin(
        tmp_path / "registry" / "cache",
        release.manifest,
        release.manifest_sha256,
        entry_relpath="plugin/plugin.py",
    )
    # Regression pin, same as the PRD-02 run leg: the module name carries
    # the manifest sha, proving the coordinator runs the cache-loaded
    # plugin rather than a same-bytes import from the plugins tree.
    assert type(cached_psu).__module__.endswith(release.manifest_sha256)
    # The seam is load-bearing: a deadline one tick below the TestClock
    # reading is already expired for this plugin. On the loader's default
    # zero-based clock the same deadline would sit far in the future.
    probe = cached_psu.dispatch(
        OperationRequest.identify("probe-1"), deadline_ns=clock.now_ns() - 1
    )
    assert probe.error is not None and probe.error.code is ErrorCode.TIMEOUT

    psu_calls = _RecordingPlugin(cached_psu)
    controller = _load_plugin_module("sim_controller").create_plugin(
        now_fn=clock.now_iso, monotonic_ns_fn=clock.now_ns
    )
    psu_calls.plugin_open(_NullServices())
    controller.plugin_open(_NullServices())
    run_start_ns = clock.now_ns()

    store = Store.open(tmp_path / "state.db")
    try:
        coordinator = RunCoordinator(
            store,
            {"psu": psu_calls, "controller": controller},
            clock,
            clock,
            _execution_docs(),
        )
        record = coordinator.start_run(RUN_ID, "principal-a")

        assert record["outcome"] == "passed"
        assert record["body_outcome"] == "completed"
        assert record["safe_state"] == "verified"
        assert record["reasons"] == []
        assert store.get_active_lease("sim-bench") is None  # the lease was released
        assert {event["kind"] for event in store.read_events(f"run:{RUN_ID}")} == {
            "invoke", "read", "write", "delay", "sample", "assert", "if", "repeat"
        }
    finally:
        store.close()

    # The procedure's psu workload executed on the cache-loaded plugin —
    # configure, enable, measure and the three loop remeasures — with every
    # dispatched deadline inside the TestClock window the executor computed.
    psu_invokes = [
        request.arguments["action_id"]
        for request, _deadline_ns in psu_calls.calls
        if request.verb is OperationVerb.INVOKE
    ]
    assert psu_invokes[:6] == [
        ACTION_CONFIGURE,
        ACTION_OUTPUT,
        ACTION_MEASURE,
        ACTION_MEASURE,
        ACTION_MEASURE,
        ACTION_MEASURE,
    ]
    assert all(
        run_start_ns <= deadline_ns <= run_start_ns + 10_000_000_000
        for _request, deadline_ns in psu_calls.calls
    )


# --- PRD-03: fault vectors reject before activation ---------------------------


def test_unknown_trust_root_rejects_before_activation(tmp_path: Path) -> None:
    # The origin-main releases verified against origin-b's key: every honest
    # signature fails, exactly as a mis-trusted origin must.
    imposter_root = load_trust_root("origin-main", REG / "keys" / "originb.pub.pem")
    # Wave-1 item 9: mkdir the cache root so "untouched" is falsifiable —
    # the rejection must leave an EMPTY cache, not a never-created one.
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    with pytest.raises(AuthenticityRejected) as exc:
        Resolver(_origins(main_root=imposter_root)).resolve(
            "origin-main", SIM_PSU, "1.0.0", now_ns=NOW_NS, high_water={}
        )
    assert exc.value.reason == "bad_signature"
    # Rejected at resolve: nothing was ever cached or locked — the cache the
    # test created stays EMPTY (falsifiable, wave-1 item 9).
    assert list(cache_root.iterdir()) == []
    assert not (tmp_path / "packages.lock.json").exists()


def test_tampered_manifest_rejects(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    shutil.copytree(REG / "origin-main", origin)
    cache_root = tmp_path / "cache"
    cache_root.mkdir()  # wave-1 item 9: "untouched" must be falsifiable
    manifest_path = origin / SIM_PSU / "1.0.0" / "manifest.json"
    raw = manifest_path.read_bytes()
    assert b"origin-main" in raw
    # One byte flipped inside a JSON string: the document stays schema-valid
    # but the detached signature over the original bytes no longer verifies.
    manifest_path.write_bytes(raw.replace(b"origin-main", b"origin-maio", 1))
    with pytest.raises(AuthenticityRejected) as exc:
        _resolve(LocalDirectorySource(origin))
    assert exc.value.reason == "bad_signature"
    assert list(cache_root.iterdir()) == []  # empty, not never-created
    assert not (tmp_path / "packages.lock.json").exists()


def test_revocation_blocks_new_admission(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    _drop_in_fault(origin, "revoked")
    closure = _resolve(LocalDirectorySource(origin))
    with pytest.raises(AdmissionRejected) as exc:
        _admit(closure, tmp_path)
    assert exc.value.reason == "revoked"
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "packages.lock.json").exists()


def test_rollback_blocks_readmission(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    _drop_in_fault(origin, "rollback-seq2")
    persisted: dict[Key, int] = {}
    closure = _resolve(LocalDirectorySource(origin), high_water=persisted)
    _admit(closure, tmp_path)  # first install replays sequence 2 — admitted
    assert persisted[DESC_KEY] == 2

    # The registry later rolls back to sequence 1 (byte-identical to the
    # honest status); the persisted high-water map must refuse readmission.
    _drop_in_fault(origin, "rollback-seq1")
    with pytest.raises(AuthenticityRejected) as exc:
        _resolve(LocalDirectorySource(origin), high_water=persisted)
    assert exc.value.reason == "stale_sequence"


def test_origin_collision_resolution_strict(tmp_path: Path) -> None:
    _main_closure, main_only = _install(tmp_path / "main-only")
    both_closure, both = _install(tmp_path / "both", include_origin_b=True)

    assert {release.registry_id for release in both_closure.releases} == {"origin-main"}
    sim_psu = _sim_psu_release(both_closure)
    honest = _sha((REG / "origin-main" / SIM_PSU / "1.0.0" / "manifest.json").read_bytes())
    clone = _sha((REG / "origin-b" / SIM_PSU / "1.0.0" / "manifest.json").read_bytes())
    assert sim_psu.manifest_sha256 == honest
    assert honest != clone  # the colliding clone is a different release
    # Through admission too: the collision changes nothing about what a
    # strict-routing install pins.
    assert both.manifest_sha256s == main_only.manifest_sha256s
