"""A-R3/A-R4: the capture run through DEV_HEAD-composed ``build_run``.

Issue #176 increment 2's run-level controls over the seam's real
composition path: the run factory composed with the manifest-declared
execution head's contracts admits a capture step, the executor's capture
branch mints ``cap:{run_id}:{step_id}`` ids, policy is consulted BEFORE
any dispatch (deny-by-default, zero device calls), the landed manifest
reaches a later step through the ``_resolve_ref`` capture arm, failed
captures invalidate their minted id, and re-entry answers from the
occurrence ledger without re-dispatching.

The harness composes only through proven in-tree machinery: the unsigned
dev publisher, the resolver/admission stack, ``registry.activation``,
and ``_build_run_factory`` — the same construction the run-activation
controls exercise, threaded with ``contracts=declared_dev_family(...)``.
Every name in the lattice and the plugin is synthetic.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import test_run_activation as activation
import uvicorn

from benchweave.content.store import ContentStore
from benchweave.control.binding import resolve_binding
from benchweave.control.clocking import SystemClock
from benchweave.control.executor import Executor
from benchweave.interfaces.app import _build_run_factory, create_app
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.registry.activation import activate
from benchweave.registry.admission import AdmissionLimits, Approval, admit
from benchweave.registry.resolver import LocalDirectorySource, OriginConfig, Resolver
from benchweave.state.store import Store
from benchweave.vendoring import CorpusResolution, declared_dev_family

REPO = Path(__file__).resolve().parents[2]
EXECUTION_FIXTURES = REPO / "fixtures" / "execution"
REGISTRY_FIXTURES = REPO / "fixtures" / "registry"

HEAD = declared_dev_family("execution")
NOW_NS = activation.NOW_NS
NOW_ISO = activation.NOW_ISO
DEVICE_ID = activation.DEVICE_ID
BENCH_ID = "capture-bench"
IMPL_PACKAGE = activation.IMPL_PACKAGE
PACKAGE_VERSION = activation.PACKAGE_VERSION
DEV_ID = activation.DEV_ID
ORIGIN_MAIN = activation.ORIGIN_MAIN
QUOTA_LIMITS = dict(activation.QUOTA_LIMITS)
ACTIVATED_GENERATION = activation.ACTIVATED_GENERATION

_CAPTURE_ARM = '''\
        if verb == "capture":
            if CAPTURE_FAIL:
                return {
                    "operation_id": operation_id,
                    "verb": verb,
                    "status": "error",
                    "error": {
                        "code": "DEVICE_REJECTED",
                        "message": "synthetic capture failure",
                        "dispatch_state": "dispatched",
                    },
                }
            # The capture lane over the composed bundle: staged appends and
            # a finalise whose manifest metadata the writer (not the
            # adapter) computes the digest and length over.
            capture_id = arguments["capture_id"]
            waveform = arguments["format"] == "waveform_f64le"
            data = bytes(arguments["sample_count"] * 8 if waveform else 8)
            await context.services.artifact_append(capture_id, data, context)
            manifest = await context.services.artifact_finalise(
                capture_id,
                {
                    "format": arguments["format"],
                    "started_at": self.services.utc_now(),
                    **(
                        {"sample_interval_s": 0.001, "unit": "V"}
                        if waveform
                        else {}
                    ),
                },
                context,
            )
            self.last_manifest = manifest
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": manifest,
            }
'''

_CAPTURE_ARM_ORIGINAL = '''\
        if verb == "capture":
            # The capture lane over the composed bundle: staged appends and
            # a finalise whose manifest metadata the writer (not the
            # adapter) computes the digest and length over.
            capture_id = arguments["capture_id"]
            waveform = arguments["format"] == "waveform_f64le"
            data = bytes(arguments["sample_count"] * 8 if waveform else 8)
            await context.services.artifact_append(capture_id, data, context)
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": await context.services.artifact_finalise(
                    capture_id,
                    {
                        "format": arguments["format"],
                        "started_at": self.services.utc_now(),
                        **(
                            {"sample_interval_s": 0.001, "unit": "V"}
                            if waveform
                            else {}
                        ),
                    },
                    context,
                ),
            }
'''

# The capture harness adapter: the activation harness's recording supply
# with the invoke arm added (the $stg_ref consumer of a landed manifest),
# a fail flag for the dispatch-failure invalidation leg, and the landed
# manifest recorded for correlation. The capture lane runs over the
# composed artifact_writer services exactly as the activation arm does.
ADAPTER_SOURCE = activation.ADAPTER_SOURCE.replace(
    _CAPTURE_ARM_ORIGINAL,
    '''        if verb == "invoke":
            self.invokes.append(
                {"action_id": arguments["action_id"], "input": arguments["input"]}
            )
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {"result": {"annotated": True}},
            }
''' + _CAPTURE_ARM,
    1,
).replace(
    """class DemoSupplyAdapter:
    CLOSE_CALLS: int = 0

    def __init__(self) -> None:
        self.services = None""",
    """CAPTURE_FAIL = False


class DemoSupplyAdapter:
    CLOSE_CALLS: int = 0

    def __init__(self) -> None:
        self.invokes: list[dict] = []
        self.last_manifest: dict | None = None
        self.services = None""",
    1,
)

# The surgery above is string-exact against the activation source; if a
# future edit changes the original capture arm, fail loudly here rather
# than run a harness with silently missing arms.
assert "invokes.append" in ADAPTER_SOURCE, "invoke arm surgery missed"
assert "CAPTURE_FAIL" in ADAPTER_SOURCE, "fail flag surgery missed"
assert ADAPTER_SOURCE.count('if verb == "capture":') == 1, "capture arm duplicated"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _descriptor(path: Path) -> dict[str, Any]:
    descriptor: dict[str, Any] = json.loads(
        (EXECUTION_FIXTURES / "descriptor-sim-psu.json").read_text()
    )
    adapter = descriptor["integration"]["adapter"]
    adapter["entry_point"] = "benchweave_sim_psu.plugin:create_plugin"
    adapter["permissions"] = ["scoped_transport", "artifact_writer"]
    descriptor["capture_formats"] = ["waveform_f64le", "raw_binary"]
    descriptor["capture_limits"] = {"max_samples": 1024, "max_bytes": 65536}
    # Two more string rw parameters beside the committed operator_note:
    # the three $stg_ref note-writes land the manifest's three §3 members
    # as declared device parameters (string rw is a schema-admitted shape —
    # operator_note's own form, cloned).
    note = next(p for p in descriptor["parameters"] if p["name"] == "operator_note")
    for name in ("capture_artifact_note", "capture_digest_note"):
        clone = json.loads(json.dumps(note))
        clone["name"] = name
        clone["description"] = f"synthetic {name}"
        descriptor["parameters"].append(clone)
    path.write_text(json.dumps(descriptor, indent=2) + "\n")
    return descriptor


def _capture_step(
    *,
    step_id: str = "grab",
    sample_count: int = 64,
    timeout_ms: int = 2000,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "kind": "capture",
        "role": "supply",
        "format": "waveform_f64le",
        "sample_count": sample_count,
        "max_bytes": 1024,
        "timeout_ms": timeout_ms,
    }


def _note_writes() -> list[dict[str, Any]]:
    """Three later writes whose values are the manifest's three §3 members
    through ``$stg_ref`` — the capture arm's live consumers. (An invoke
    cannot carry them: the bridge's closed supported map deliberately
    excludes invoke until the native-async dataset host.)"""

    def note(step_id: str, parameter: str, pointer: str) -> dict[str, Any]:
        return {
            "id": step_id,
            "kind": "write",
            "role": "supply",
            "parameter": parameter,
            "value": {"$stg_ref": {"step": "grab", "pointer": pointer}},
            "timeout_ms": 500,
        }

    return [
        note("note-capture", "operator_note", "/capture_id"),
        note("note-artifact", "capture_artifact_note", "/artifact_id"),
        note("note-digest", "capture_digest_note", "/sha256"),
    ]


def _policy_rules(*, capture: str = "conform") -> list[dict[str, Any]]:
    """Allow rules: the three note-writes always; the capture leg varies —
    ``conform`` allows a conforming request, ``none`` adds no capture rule
    (deny-by-default), ``violating`` allows a rule whose capture_constraints
    the step's request exceeds."""
    rules: list[dict[str, Any]] = [
        {
            "device_id": DEVICE_ID,
            "kind": "write",
            "parameter": parameter,
            "value_constraints": {"type": "string"},
        }
        for parameter in (
            "operator_note",
            "capture_artifact_note",
            "capture_digest_note",
        )
    ]
    if capture == "conform":
        rules.append(
            {
                "device_id": DEVICE_ID,
                "kind": "capture",
                "format": "waveform_f64le",
                "capture_constraints": {
                    "type": "object",
                    "properties": {
                        "sample_count": {"maximum": 1024},
                        "max_bytes": {"maximum": 65536},
                    },
                },
            }
        )
    elif capture == "violating":
        rules.append(
            {
                "device_id": DEVICE_ID,
                "kind": "capture",
                "format": "waveform_f64le",
                "capture_constraints": {
                    "type": "object",
                    "properties": {"sample_count": {"maximum": 32}},
                },
            }
        )
    return rules


def _lattice(
    tmp_path: Path,
    request_id: str,
    *,
    capture_rule: str = "conform",
    steps: list[dict[str, Any]] | None = None,
) -> Path:
    """The capture harness lattice: one commissioned capture supply."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    descriptor_path = tmp_path / "descriptor-demo-supply.json"
    descriptor = _descriptor(descriptor_path)
    if steps is None:
        steps = [_capture_step(), *_note_writes()]

    procedure: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "capture-procedure",
        "version": "0.1.0",
        "description": "Synthetic capture harness procedure.",
        "mode": "gateway_owned",
        "safety_policy": {"id": "capture-policy", "version": "0.1.0"},
        "roles": [
            {
                "id": "supply",
                "required_profiles": ["otdp.dc_psu/1.0.0"],
                "channels": ["output"],
            }
        ],
        "max_body_ms": 8000,
        "max_protection_ms": 2000,
        "steps": steps,
    }
    procedure_path = tmp_path / "procedure-capture.json"
    procedure_path.write_text(json.dumps(procedure, indent=2) + "\n")

    policy: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "capture-policy",
        "version": "0.1.0",
        "description": "Synthetic capture harness policy.",
        "domains": [
            {
                "id": "dut",
                "max_abs_voltage_v": 6,
                "max_abs_current_a": 1,
                "max_power_w": 3,
                "max_stored_energy_j": 0.01,
                "max_energised_ms": 10000,
            }
        ],
        "allow_rules": _policy_rules(capture=capture_rule),
        "continuous_conditions": [
            {
                "id": "dut-voltage-bounds",
                "kind": "numeric",
                "signal": "dut-voltage",
                "unit": "V",
                "minimum": -0.1,
                "maximum": 5.5,
            }
        ],
        "independent_protection": {
            "required": False,
            "assessment": {
                "id": "capture-protection-assessment",
                "version": "0.1.0",
                "sha256": "0" * 64,
            },
            "mechanism_ids": [],
        },
        "safe_transition": {
            "max_duration_ms": 2000,
            "actions": [
                {
                    "id": "disable",
                    "device_id": DEVICE_ID,
                    "kind": "write",
                    "parameter": "output_enabled",
                    "value": False,
                    "timeout_ms": 500,
                }
            ],
            "verify": [
                {
                    "id": "voltage-safe",
                    "kind": "numeric",
                    "signal": "dut-voltage",
                    "unit": "V",
                    "minimum": -0.1,
                    "maximum": 0.1,
                }
            ],
            "stable_for_ms": 100,
        },
    }
    policy_path = tmp_path / "safety-policy.json"
    policy_path.write_text(json.dumps(policy, indent=2) + "\n")

    lock_path = tmp_path / "package-lock.json"
    lock_path.write_bytes((EXECUTION_FIXTURES / "package-lock.json").read_bytes())

    bench: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": BENCH_ID,
        "version": "0.1.0",
        "description": "Synthetic capture harness bench. Not hardware-qualified.",
        "gateway_id": "capture-gateway",
        "fixture": {
            "id": "capture-fixture",
            "revision": "1",
            "identity_record_id": "ident-capture",
        },
        "dut_class": "low_voltage_embedded",
        "policy": {
            "id": "capture-policy",
            "version": "0.1.0",
            "sha256": _sha(policy_path.read_bytes()),
        },
        "package_lock": {
            "id": "sim-lock",
            "version": "0.1.0",
            "sha256": _sha(lock_path.read_bytes()),
        },
        "commissioning_id": "capture-commissioning",
        "dut_ids": [DEVICE_ID],
        "protection_mechanisms": [],
        "devices": [
            {
                "id": DEVICE_ID,
                "generation": ACTIVATED_GENERATION,
                "descriptor": {
                    "id": descriptor["id"],
                    "version": descriptor["descriptor_version"],
                    "sha256": _sha(descriptor_path.read_bytes()),
                },
                "identity_record_id": "ident-psu",
                "connection_key": "sim_psu_local",
                "channels": ["ch1"],
            }
        ],
        "resources": [{"id": "dut-net", "device_ids": [DEVICE_ID], "depends_on": []}],
        "terminals": [
            {
                "id": "psu-out",
                "owner_kind": "device",
                "owner_id": DEVICE_ID,
                "channel_id": "ch1",
                "name": "out",
                "domain_id": "dut",
            },
            {
                "id": "psu-in",
                "owner_kind": "device",
                "owner_id": DEVICE_ID,
                "channel_id": "ch1",
                "name": "in",
                "domain_id": "dut",
            },
        ],
        "nets": [{"id": "n1", "terminal_ids": ["psu-out", "psu-in"]}],
        "signals": [
            {
                "id": "dut-voltage",
                "quantity": "voltage",
                "unit": "V",
                "poll_ms": 50,
                "max_age_ms": 500,
                "absolute_error": 0.05,
                "resource_id": "dut-net",
                "source": {
                    "kind": "parameter",
                    "device_id": DEVICE_ID,
                    "parameter": "output_voltage_v",
                },
            }
        ],
    }
    bench_path = tmp_path / "bench.json"
    bench_path.write_text(json.dumps(bench, indent=2) + "\n")

    commissioning: dict[str, Any] = {
        "contract_version": "0.1.0",
        "id": "capture-commissioning",
        "version": "0.1.0",
        "description": "Synthetic capture harness commissioning. Not hardware-qualified.",
        "bench": {"id": BENCH_ID, "version": "0.1.0"},
        "policy": {"id": "capture-policy", "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "procedure_refs": [{"id": "capture-procedure", "version": "0.1.0"}],
        "dut_class": "low_voltage_embedded",
        "modes": ["supervised"],
        "owners": {
            "bench": "capture-harness-owner",
            "test_safety": "capture-harness-owner",
            "system": "capture-harness-owner",
        },
        "approved_by": "capture-harness-owner",
        "approved_at": "2026-09-11T00:00:00Z",
        "expires_at": "2030-01-01T00:00:00Z",
        "offline_status_max_age_ms": 86400000,
        "scheduling_overhead_ms": 100,
        "evidence": [
            {
                "category": "envelope",
                "report": {
                    "id": "capture-envelope-report",
                    "version": "0.1.0",
                    "sha256": "0" * 64,
                },
                "tested_at": "2026-09-11T00:00:00Z",
                "scope": "Simulator envelope over the synthetic capture supply.",
                "result": "passed",
                "limitations": ["simulator-only"],
            }
        ],
    }
    for name, path in (
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lock_path),
    ):
        commissioning[name]["sha256"] = _sha(path.read_bytes())
    for reference in commissioning["procedure_refs"]:
        reference["sha256"] = _sha(procedure_path.read_bytes())
    commissioning_path = tmp_path / "commissioning.json"
    commissioning_path.write_text(json.dumps(commissioning, indent=2) + "\n")

    binding: dict[str, Any] = {
        "contract_version": "0.1.0",
        "request_id": request_id,
        "procedure": {"id": "capture-procedure", "version": "0.1.0"},
        "bench": {"id": BENCH_ID, "version": "0.1.0"},
        "policy": {"id": "capture-policy", "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "commissioning": {"id": "capture-commissioning", "version": "0.1.0"},
        "bindings": [
            {"role": "supply", "device_id": DEVICE_ID, "channels": {"output": "ch1"}}
        ],
    }
    for name, path in (
        ("procedure", procedure_path),
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lock_path),
        ("commissioning", commissioning_path),
    ):
        binding[name]["sha256"] = _sha(path.read_bytes())
    (tmp_path / "run-binding.json").write_text(json.dumps(binding, indent=2) + "\n")
    return tmp_path


class _CaptureHarness:
    """One commissioned capture device plus the DEV_HEAD-composed factory."""

    def __init__(
        self,
        tmp_path: Path,
        request_id: str,
        *,
        capture_rule: str = "conform",
    ) -> None:
        self.root = tmp_path
        self.lattice_dir = _lattice(
            tmp_path / "lattice", request_id, capture_rule=capture_rule
        )
        descriptor_path = self.lattice_dir / "descriptor-demo-supply.json"
        # The plugin source: activation's writer with the capture harness's
        # adapter (invoke arm + fail flag) swapped in through its module
        # global — the publisher reads the source string at publish time.
        previous_source = activation.ADAPTER_SOURCE
        activation.ADAPTER_SOURCE = ADAPTER_SOURCE
        try:
            plugin_dir = activation._write_plugin_source(tmp_path / "pluginroot")
        finally:
            activation.ADAPTER_SOURCE = previous_source
        registry_root = tmp_path / "dev-registry"
        activation._publish(plugin_dir, descriptor_path, registry_root)

        origins = {
            DEV_ID: OriginConfig(
                registry_id=DEV_ID,
                root=None,
                source=LocalDirectorySource(registry_root / DEV_ID),
                namespaces=("dev",),
                signature_policy="dev-unsigned",
            ),
            ORIGIN_MAIN: OriginConfig(
                registry_id=ORIGIN_MAIN,
                root=activation._main_root(),
                source=LocalDirectorySource(REGISTRY_FIXTURES / ORIGIN_MAIN),
                namespaces=("benchweave",),
            ),
        }
        from benchweave.interfaces.bootstrap import RegistrySession

        self.work = tmp_path / "registry-work"
        self.session = RegistrySession(
            resolver=Resolver(origins),
            roots={ORIGIN_MAIN: activation._main_root()},
            high_water={},
            cache_root=self.work / "cache",
            lock_path=self.work / "packages.lock.json",
            records_dir=self.work / "activations",
            limits=AdmissionLimits(
                max_archive_bytes=1_000_000, max_files=100, max_unpacked_bytes=1_000_000
            ),
            now_ns=lambda: NOW_NS,
            registry_id=DEV_ID,
        )
        closure = self.session.resolver.resolve(
            DEV_ID,
            IMPL_PACKAGE,
            PACKAGE_VERSION,
            now_ns=NOW_NS,
            high_water=self.session.high_water,
        )
        self.admitted = admit(
            closure,
            cache_root=self.session.cache_root,
            lock_path=self.session.lock_path,
            limits=self.session.limits,
            approval=Approval(
                principal_id="capture-harness",
                approved_at=NOW_ISO,
                policy_id="local-policy",
                policy_version="1.0.0",
            ),
            now_ns=NOW_NS,
            roots={DEV_ID: None, ORIGIN_MAIN: activation._main_root()},
            high_water=self.session.high_water,
        )
        activate(
            self.admitted,
            bench_generation=1,
            bench_has_live_lease=False,
            records_dir=self.session.records_dir / BENCH_ID,
            activated_at=NOW_ISO,
        )

    def open_store(self) -> tuple[Store, ContentStore]:
        store = Store.open(self.root / "state.db")
        content = ContentStore(store)
        # Startup admission through the seam's bootstrap threading: the
        # dev-resolved contracts admit the capture lattice at boot.
        admit_startup_bench(store, content, self.lattice_dir, now=NOW_ISO, contracts=HEAD)
        return store, content

    def build_run(self) -> Callable[..., Any]:
        from benchweave.control.clocking import SystemClock

        return _build_run_factory(
            self.lattice_dir,
            SystemClock().now_iso,
            limits=QUOTA_LIMITS,
            registry_session=self.session,
            contracts=HEAD,
        )

    def binding_ref(self) -> dict[str, str]:
        """The §5 binding ref as the startup path stored it (no rewrite —
        a rewritten request id changes the digest the ContentStore pins)."""
        raw = (self.lattice_dir / "run-binding.json").read_bytes()
        return {
            "id": json.loads(raw)["request_id"],
            "version": "0.1.0",
            "sha256": _sha(raw),
        }

    def _coordinator(self, run_id: str) -> tuple[Any, Store]:
        store, _content = self.open_store()
        try:
            factory = self.build_run()
            coordinator = factory(run_id, "principal-capture", self.binding_ref(), store)
            return coordinator, store
        except BaseException:
            store.close()
            raise


def _loaded_adapter() -> Any:
    """The capture harness adapter's loaded module (the CAPTURE_FAIL marker)."""
    for _name, module in list(sys.modules.items()):
        if getattr(module, "DEMO_ADAPTER", False) and hasattr(module, "CAPTURE_FAIL"):
            return module
    raise AssertionError("capture harness adapter module not loaded")


def _adapter_instance(coordinator: Any) -> Any:
    return coordinator.plugins[DEVICE_ID]._adapter


def test_a_r3_no_capture_rule_denies_dispatch_with_zero_device_calls(
    tmp_path: Path,
) -> None:
    """A-R3 (deny-by-default leg): through DEV_HEAD-composed admission a
    capture step on a capture-declaring device ADMITS, but with no capture
    allow rule the dispatch is denied ``no_matching_rule:`` with ZERO
    adapter capture calls — and the minted id records as invalidated."""
    harness = _CaptureHarness(tmp_path, "req-capture-norule", capture_rule="none")
    run_id = "run-norule"
    coordinator, store = harness._coordinator(run_id)
    try:
        record = coordinator.start_run(run_id, "principal-capture")
        assert record["outcome"] == "execution_error"
        assert any("no_matching_rule:" in reason for reason in record["reasons"])
        entry = coordinator.occurrence_ledger[(run_id, "grab", ())]
        issued = entry["issued_ids"]["capture_id"]
        assert issued["status"] == "invalidated"
        assert issued["id"] == f"cap:{run_id}:grab"
        adapter = _adapter_instance(coordinator)
        # Zero capture executes and no procedure note-write landed (the
        # flat verb list also carries the monitor's signal reads and the
        # protective transition's own write — by-design traffic after the
        # denial, not procedure dispatches).
        assert "capture" not in adapter.dispatches
        assert "operator_note" not in adapter.state
    finally:
        store.close()


def test_a_r3_capture_constraint_violation_denies_before_dispatch(
    tmp_path: Path,
) -> None:
    """A-R3 (constraint leg): a request exceeding the matching rule's
    capture_constraints refuses ``capture_constraint:`` before any device
    call (zero capture executes)."""
    harness = _CaptureHarness(tmp_path, "req-capture-constraint", capture_rule="violating")
    run_id = "run-constraint"
    coordinator, store = harness._coordinator(run_id)
    try:
        record = coordinator.start_run(run_id, "principal-capture")
        assert record["outcome"] == "execution_error"
        assert any("capture_constraint:" in reason for reason in record["reasons"])
        adapter = _adapter_instance(coordinator)
        assert "capture" not in adapter.dispatches
        assert "operator_note" not in adapter.state
        entry = coordinator.occurrence_ledger[(run_id, "grab", ())]
        assert entry["issued_ids"]["capture_id"]["status"] == "invalidated"
    finally:
        store.close()


def test_a_r4_capture_executes_and_the_manifest_reaches_a_later_step(
    tmp_path: Path,
) -> None:
    """A-R4: a conforming run executes the capture (one step event, the
    manifest is the step's result), the three later writes' $stg_ref
    pointers resolve through the capture arm into the device parameters,
    the minted id matches the pattern, sits in issued_ids as live, and is
    the id the device saw."""
    harness = _CaptureHarness(tmp_path, "req-capture-pass")
    run_id = "run-capture-pass"
    coordinator, store = harness._coordinator(run_id)
    try:
        record = coordinator.start_run(run_id, "principal-capture")
        assert record["outcome"] == "passed", record["reasons"]
        events = store.read_events(f"run:{run_id}")
        kinds = [event["kind"] for event in events]
        assert kinds.count("capture") == 1
        assert kinds.count("write") == 3

        adapter = _adapter_instance(coordinator)
        # One capture dispatched (the three procedure writes and the
        # monitor/protective traffic are counted on the step-event surface,
        # which carries procedure occurrences only).
        assert adapter.dispatches.count("capture") == 1
        minted = f"cap:{run_id}:grab"
        entry = coordinator.occurrence_ledger[(run_id, "grab", ())]
        issued = entry["issued_ids"]["capture_id"]
        assert issued["id"] == minted
        assert issued["status"] == "issued"

        # The manifest landed as the step's result: its capture_id IS the
        # minted id, and each later note-write received its member through
        # $stg_ref (the resolver arm) — the values the adapter stored.
        result = entry["result"]
        assert result.status.value == "ok"
        assert result.verb.value == "capture"
        manifest = result.data
        assert manifest["capture_id"] == minted
        assert manifest["artifact_id"] == adapter.last_manifest["artifact_id"]
        assert isinstance(manifest["sha256"], str) and len(manifest["sha256"]) == 64

        assert adapter.state["operator_note"] == minted
        assert adapter.state["capture_artifact_note"] == manifest["artifact_id"]
        assert adapter.state["capture_digest_note"] == manifest["sha256"]
    finally:
        store.close()


def test_a_r4_failed_capture_dispatch_invalidates_the_minted_id(
    tmp_path: Path,
) -> None:
    """A-R4 (failure leg): a capture whose operation does not succeed
    invalidates its minted id — a live id never survives a failed
    capture."""
    harness = _CaptureHarness(tmp_path, "req-capture-fail")
    run_id = "run-capture-fail"
    coordinator, store = harness._coordinator(run_id)
    try:
        module = _loaded_adapter()
        module.CAPTURE_FAIL = True
        try:
            record = coordinator.start_run(run_id, "principal-capture")
        finally:
            module.CAPTURE_FAIL = False
        assert record["outcome"] != "passed"
        entry = coordinator.occurrence_ledger[(run_id, "grab", ())]
        issued = entry["issued_ids"]["capture_id"]
        assert issued["status"] == "invalidated"
        assert issued["id"] == f"cap:{run_id}:grab"
    finally:
        store.close()


def test_a_r4_replay_answers_from_the_ledger_without_redispaching(
    tmp_path: Path,
) -> None:
    """A-R4 (replay leg): a second body over the same occurrence ledger
    answers from recorded results — zero new dispatches, the recorded
    step events replayed."""
    harness = _CaptureHarness(tmp_path, "req-capture-replay")
    run_id = "run-capture-replay"
    coordinator, store = harness._coordinator(run_id)
    try:
        record = coordinator.start_run(run_id, "principal-capture")
        assert record["outcome"] == "passed", record["reasons"]
        adapter = _adapter_instance(coordinator)
        before = list(adapter.dispatches)
        assert before.count("capture") == 1

        replay = Executor(
            plugins=coordinator.plugins,
            binding=resolve_binding(coordinator._docs),
            policy=coordinator._docs.policy,
            clock=SystemClock(),
            wall=SystemClock(),
            occurrence_ledger=coordinator.occurrence_ledger,
        )
        body = replay.run_body(
            coordinator._docs.procedure,
            run_id,
            SystemClock().now_ns() + 10_000_000_000,
        )
        assert body.body_outcome == "completed"
        after = list(adapter.dispatches)
        assert after == before, "replay must not re-dispatch"
        assert [event["kind"] for event in body.step_events] == [
            "capture",
            "write",
            "write",
            "write",
        ]
    finally:
        store.close()


def test_dev_head_composition_boots_and_admits_the_committed_lattice(
    tmp_path: Path,
) -> None:
    """The seam end to end: ``create_app(execution_corpus=DEV_HEAD)``
    resolves the declared head once at composition and the lifespan's
    startup admission runs against the same family — the committed
    lattice (no capture steps) admits under BOTH corpora, so the boot
    succeeds through the dev-resolved path."""
    import shutil

    import test_startup_admission_refusal as boot

    lattice = tmp_path / "lattice"
    shutil.copytree(boot.FIXTURES, lattice)
    store = Store.open(tmp_path / "state.sqlite", check_same_thread=False)
    content = ContentStore(store)
    app = create_app(
        store=store,
        content=content,
        secret=b"capture-boot-secret",
        limits={
            "max_json_bytes": 1048576,
            "max_page_size": 1000,
            "max_chunk_bytes": 65536,
            "max_lease_ms": 600000,
            "min_poll_ms": 100,
            "max_admission_ms": 5000,
        },
        gateway_id="gw-capture-boot",
        fixtures_dir=lattice,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: int(time.time()),
        execution_corpus=CorpusResolution.DEV_HEAD,
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5.0
    while not server.started and thread.is_alive():
        if time.monotonic() > deadline:
            break
        time.sleep(0.05)
    try:
        assert server.started, "a DEV_HEAD composition must boot the committed lattice"
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
        store.close()
