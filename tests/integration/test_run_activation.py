"""Run-engine activation controls (issue #167, design row 9 of the #43 record).

The controls R10/R11/R16 of the pre-committed acceptance rule
(`.claude/deep-review/2026-09-23-issue167-run-engine-activation-design.md`),
over the real ``build_run`` composition: adapter-mode bench devices whose
declared generation carries an activation record construct real
``OTDPBridge`` instances over the worker-thread store (R10), the run's
``ReadingSinks`` is ONE instance shared by the run services and every
stream controller (R11), and the quota seam refuses loudly before any
``plugin_open`` when the required operator ceilings are absent (R16).

The harness composes only through proven in-tree machinery: the unsigned
dev publisher (``scripts/registry/publish_dev.py``), the resolver/admission
stack over a dev origin plus the signed origin-main profile dependency,
``registry.activation.activate`` (the idle-boundary commissioning act), and
the ``readmit_mutated`` lattice-authoring idiom. Every name in the lattice
and the plugin is synthetic (harness-owned, not a real bench).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.capture_services import CaptureServicesBundle
from benchweave.content.store import ContentStore
from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.types import OperationRequest, OperationStatus, OperationVerb
from benchweave.interfaces.app import _build_run_factory
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.worker import RunWorker
from benchweave.registry.activation import activate
from benchweave.registry.admission import AdmissionLimits, Approval, admit
from benchweave.registry.authenticity import load_trust_root
from benchweave.registry.resolver import (
    LocalDirectorySource,
    OriginConfig,
    Resolver,
)
from benchweave.standards.manifest import load_manifest
from benchweave.state.store import Store

REPO = Path(__file__).resolve().parents[2]
REGISTRY_FIXTURES = REPO / "fixtures" / "registry"
EXECUTION_FIXTURES = REPO / "fixtures" / "execution"
PUBLISH_DEV = REPO / "scripts" / "registry" / "publish_dev.py"

# The registry clock, frozen inside every fixture status's validity window
# (the test_registry_reuse posture — never a hand-typed nanosecond literal).
NOW_NS = int(datetime(2026, 9, 14, tzinfo=UTC).timestamp() * 1_000_000_000)
NOW_ISO = "2026-09-14T00:00:00Z"

DEV_ID = "dev-local"
ORIGIN_MAIN = "origin-main"
BENCH_ID = "activation-bench"
DEVICE_ID = "psu"
# The dev publisher's role table keys descriptor members on the plugin
# dirname (scripts/registry/registry_common.py ROLE_BY_SUFFIX); the harness
# plugin therefore publishes under the fixture-family name "sim_psu" — a
# dev-namespace package, not the signed benchweave/sim-psu fixture.
PLUGIN_DIRNAME = "sim_psu"
IMPL_PACKAGE = f"dev/{PLUGIN_DIRNAME}"
PACKAGE_VERSION = "1.0.0"

#: The quota seam's required operator ceilings (design Decision 1).
QUOTA_LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
    "max_dataset_bytes": 8 * 1024 * 1024,
    "max_event_batch": 64,
}

#: The activated generation the bench's device declares (the linkage the
#: design names: ``bench.devices[].generation`` ↔ the activation record).
ACTIVATED_GENERATION = 2

# The synthetic OTDP adapter the harness publishes: a recording supply that
# answers scalar reads, applies writes with readback receipts, and serves
# ``next_event`` telemetry off its own state. Zero-argument factory (the
# OTDP ABI); construction and open stay free of device I/O.
ADAPTER_SOURCE = '''\
"""Synthetic recording supply adapter (activation harness)."""
from __future__ import annotations

import asyncio
import time


class DemoSupplyAdapter:
    CLOSE_CALLS: int = 0

    def __init__(self) -> None:
        self.services = None
        self.descriptor = None
        self.state = {
            "voltage_setpoint_v": 0.0,
            "output_enabled": False,
        }
        self.sequences: dict[str, int] = {}
        self.dispatches: list[str] = []
        # Measurement seams (the bench-measurer lane's machinery): every
        # execute/next_event call records its verb and wall span, so M-A's
        # per-poll latencies and M-B's dispatch wall-stretch read off the
        # composed adapter without touching production code.
        self.dispatch_spans: list[tuple[str, float, float]] = []

    async def open(self, descriptor, services, context) -> None:
        self.descriptor = descriptor
        self.services = services

    async def close(self, context) -> None:
        DemoSupplyAdapter.CLOSE_CALLS += 1

    def _reading(self, parameter, value, unit):
        return {
            "parameter": parameter,
            "value": value,
            "unit": unit,
            "observed_at": self.services.utc_now(),
            "age_ms": 0,
            "quality": "valid",
            "source": "device",
        }

    def _output_voltage(self):
        if self.state.get("drifted"):
            return 99.0
        if not self.state["output_enabled"]:
            return 0.0
        return float(self.state["voltage_setpoint_v"])

    async def execute(self, envelope, context):
        started = time.monotonic()
        try:
            return await self._execute(envelope, context)
        finally:
            self.dispatch_spans.append((envelope["verb"], started, time.monotonic()))

    async def _execute(self, envelope, context):
        global TRIP_AFTER_UNSUBSCRIBE
        if envelope["verb"] == "stream_unsubscribe" and TRIP_AFTER_UNSUBSCRIBE:
            self.state["drifted"] = True
        await context.mark_dispatch_started()
        verb = envelope["verb"]
        arguments = envelope["arguments"]
        self.dispatches.append(verb)
        operation_id = envelope["operation_id"]
        if verb == "read":
            parameter = arguments["parameter"]
            if parameter == "output_voltage_v":
                data = self._reading(parameter, self._output_voltage(), "V")
            elif parameter == "output_current_a":
                current = 0.1 if self.state["output_enabled"] else 0.0
                data = self._reading(parameter, current, "A")
            else:
                data = self._reading(parameter, 0.0, None)
            return {"operation_id": operation_id, "verb": verb, "status": "ok", "data": data}
        if verb == "write":
            parameter = arguments["parameter"]
            value = arguments["value"]
            self.state[parameter] = value
            unit = "V" if parameter == "voltage_setpoint_v" else None
            verification = self._reading(parameter, value, unit)
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {
                    "parameter": parameter,
                    "requested_value": value,
                    "effective_value": value,
                    "assurance": "readback",
                    "verification": verification,
                },
            }
        if verb in ("stream_subscribe", "stream_unsubscribe"):
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {"subscription_id": arguments["subscription_id"]},
            }
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
        return {
            "operation_id": operation_id,
            "verb": verb,
            "status": "error",
            "error": {
                "code": "UNSUPPORTED",
                "message": f"demo adapter does not implement {verb}",
                "dispatch_state": "not_dispatched",
            },
        }

    async def next_event(self, subscription_id, context):
        started = time.monotonic()
        try:
            return await self._next_event(subscription_id, context)
        finally:
            self.dispatch_spans.append(("next_event", started, time.monotonic()))

    async def _next_event(self, subscription_id, context):
        global SLOW_NEXT_EVENT_MS
        if SLOW_NEXT_EVENT_MS:
            # The saturated-but-legal regime: consume nearly the whole poll
            # deadline, then RETURN an event — unlike HANG (which poisons),
            # this survives, so M-A's saturated windows can exist.
            remaining = context.deadline_monotonic - context.services.monotonic()
            await asyncio.sleep(
                max(0.0, min(SLOW_NEXT_EVENT_MS / 1000.0, remaining - 0.005))
            )
        if HANG_NEXT_EVENT:
            await asyncio.sleep(10.0)
        sequence = self.sequences.get(subscription_id, -1) + 1
        self.sequences[subscription_id] = sequence
        parameter = "output_voltage_v"
        return {
            "subscription_id": subscription_id,
            "sequence": sequence,
            "kind": "telemetry",
            "reading": self._reading(parameter, self._output_voltage(), "V"),
        }


DEMO_ADAPTER = True
HANG_NEXT_EVENT = False
TRIP_AFTER_UNSUBSCRIBE = False
SLOW_NEXT_EVENT_MS = 0


def create_plugin():
    return DemoSupplyAdapter()
'''


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _main_root() -> Any:
    return load_trust_root(ORIGIN_MAIN, REGISTRY_FIXTURES / "keys" / "main.pub.pem")


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2))
    return path


def _pin(document: dict[str, Any], path: Path) -> dict[str, str]:
    return {
        "id": str(document["id"]),
        "version": str(document["version"]),
        "sha256": _sha(path.read_bytes()),
    }


def _mutated_descriptor(
    tmp_path: Path,
    *,
    stream_floor_ms: int = 10,
    streaming: bool = True,
    extra_permissions: tuple[str, ...] = (),
) -> Path:
    """The committed sim-psu descriptor with the capture/stream permissions.

    Additive-only mutations (the fixture byte-mover is deferred as row D):
    the adapter permissions gain ``artifact_writer`` + ``event_sink``, the
    root gains the schema-legal ``stream_limits``, and the entry point names
    the harness plugin. Everything else — parameters, actions, profiles —
    stays the committed, schema-valid content.
    """
    descriptor = json.loads((EXECUTION_FIXTURES / "descriptor-sim-psu.json").read_text())
    adapter = descriptor["integration"]["adapter"]
    adapter["entry_point"] = "benchweave_sim_psu.plugin:create_plugin"
    if streaming:
        adapter["permissions"] = [
            "scoped_transport",
            "artifact_writer",
            "event_sink",
            *extra_permissions,
        ]
        descriptor["stream_limits"] = {
            "min_interval_ms": stream_floor_ms,
            "max_subscriptions": 4,
        }
    else:
        # The committed fixture shape: transport-only permissions, no event
        # services, no capture writer (the F1 leak case — a commissioned
        # bridge the streaming registry never sees).
        adapter["permissions"] = ["scoped_transport", *extra_permissions]
    # The capture lane's descriptor bounds (the gate's G2 read): sized for
    # the measurement harness's smoke-scale captures.
    descriptor["capture_limits"] = {"max_samples": 1024, "max_bytes": 65536}
    descriptor["capture_formats"] = ["waveform_f64le", "raw_binary"]
    return _write(tmp_path / "descriptor-demo-supply.json", descriptor)


def _write_plugin_source(tmp_path: Path, source: str | None = None) -> Path:
    root = tmp_path / "plugin" / PLUGIN_DIRNAME / "src" / f"benchweave_{PLUGIN_DIRNAME}"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "plugin.py").write_text(ADAPTER_SOURCE if source is None else source)
    # The descriptor the harness publishes pins the OTDP class contracts
    # (catalog + measurement schema) at bundle-root paths, and #146 slice 2
    # resolves those pins against the verified inventory at load — so the
    # plugin source carries the corpus bytes and publish_dev ships them at
    # exactly the pinned root paths.
    active = next(
        entry.version
        for entry in load_manifest(REPO).standards
        if entry.id == "otdp"
    )
    for name in ("device-profile-catalog.json", "otdp-measurement.schema.json"):
        (root / name).write_bytes(
            (REPO / "standards" / "otdp" / active / name).read_bytes()
        )
    return tmp_path / "plugin" / PLUGIN_DIRNAME


def _publish(plugin_dir: Path, descriptor: Path, out: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(PUBLISH_DEV),
            str(plugin_dir),
            "--descriptor",
            str(descriptor),
            "--out",
            str(out),
            "--version",
            PACKAGE_VERSION,
        ],
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr.decode()


def _lattice(
    tmp_path: Path,
    request_id: str,
    *,
    signal_poll_ms: int = 50,
    continuous_max: float = 5.5,
    write_value: float = 5.0,
    enable_output: bool = False,
    stream_floor_ms: int = 10,
    streaming: bool = True,
    two_devices: bool = False,
    simulated: bool = True,
    steps: list[dict[str, Any]] | None = None,
    allow_rules: list[dict[str, Any]] | None = None,
    extra_permissions: tuple[str, ...] = (),
) -> Path:
    """Author the activation lattice: one commissioned supply device.

    Mirrors the ``readmit_mutated`` pin discipline (tests/control/_harness.py)
    over a synthetic single-device bench whose device declares the ACTIVATED
    generation — the design's linkage from a bench device to the admin act
    that commissioned its closure.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    descriptor_path = _mutated_descriptor(
        tmp_path,
        stream_floor_ms=stream_floor_ms,
        streaming=streaming,
        extra_permissions=extra_permissions,
    )
    descriptor = json.loads(descriptor_path.read_text())
    controller_descriptor_path = tmp_path / "descriptor-controller.json"
    if two_devices:
        controller_descriptor_path.write_bytes(
            (EXECUTION_FIXTURES / "descriptor-sim-controller.json").read_bytes()
        )

    procedure: dict[str, Any] = {
        "contract_version": "0.2.0",
        "id": "activation-procedure",
        "version": "0.1.0",
        "description": "Synthetic activation harness procedure.",
        "mode": "gateway_owned",
        "safety_policy": {"id": "activation-policy", "version": "0.1.0"},
        "roles": [
            {"id": "supply", "required_profiles": ["otdp.dc_psu/1.0.0"], "channels": ["output"]}
        ],
        "max_body_ms": 8000,
        "max_protection_ms": 2000,
        "steps": steps if steps is not None else [
            {
                "id": "set-voltage",
                "kind": "write",
                "role": "supply",
                "parameter": "voltage_setpoint_v",
                "value": write_value,
                "timeout_ms": 500,
            },
            *(
                [
                    {
                        "id": "enable",
                        "kind": "write",
                        "role": "supply",
                        "parameter": "output_enabled",
                        "value": True,
                        "timeout_ms": 500,
                    }
                ]
                if enable_output
                else []
            ),
            {"id": "settle", "kind": "delay", "duration_ms": 200},
            {
                "id": "observe",
                "kind": "read",
                "role": "supply",
                "parameter": "output_voltage_v",
                "timeout_ms": 500,
            },
        ],
    }
    procedure_path = _write(tmp_path / "procedure-activation.json", procedure)

    policy: dict[str, Any] = {
        "contract_version": "0.2.0",
        "id": "activation-policy",
        "version": "0.1.0",
        "description": "Synthetic activation harness policy.",
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
        "allow_rules": allow_rules if allow_rules is not None else [
            {
                "device_id": DEVICE_ID,
                "kind": "write",
                "parameter": "voltage_setpoint_v",
                "value_constraints": {"type": "number", "minimum": 0, "maximum": 5.5},
            },
            {
                "device_id": DEVICE_ID,
                "kind": "write",
                "parameter": "output_enabled",
                "value_constraints": {"type": "boolean"},
            },
        ],
        "continuous_conditions": [
            {
                "id": "dut-voltage-bounds",
                "kind": "numeric",
                "signal": "dut-voltage",
                "unit": "V",
                "minimum": -0.1,
                "maximum": continuous_max,
            }
        ],
        "independent_protection": {
            "required": False,
            "assessment": {
                "id": "activation-protection-assessment",
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
    policy_path = _write(tmp_path / "safety-policy.json", policy)

    lock_path = tmp_path / "package-lock.json"
    lock_path.write_bytes((EXECUTION_FIXTURES / "package-lock.json").read_bytes())

    bench: dict[str, Any] = {
        "contract_version": "0.2.0",
        "id": BENCH_ID,
        "version": "0.1.0",
        "description": "Synthetic activation harness bench. Not hardware-qualified.",
        "gateway_id": "activation-gateway",
        "fixture": {
            "id": "activation-fixture",
            "revision": "1",
            "identity_record_id": "ident-activation",
        },
        "dut_class": "low_voltage_embedded",
        "policy": {"id": "activation-policy", "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "commissioning_id": "activation-commissioning",
        "dut_ids": [DEVICE_ID],
        "protection_mechanisms": [],
        "devices": [
            {
                "id": DEVICE_ID,
                "generation": ACTIVATED_GENERATION,
                "descriptor": {
                    "id": descriptor["id"],
                    "version": descriptor["descriptor_version"],
                },
                "identity_record_id": "ident-psu",
                "connection_key": "sim_psu_local",
                "channels": ["ch1"],
            },
            *(
                [
                    {
                        "id": "controller",
                        "generation": 1,
                        "descriptor": {
                            "id": "dev.benchweave.sim-controller",
                            "version": "1.0.0",
                            "sha256": _sha(controller_descriptor_path.read_bytes()),
                        },
                        "identity_record_id": "ident-controller",
                        "connection_key": "sim_controller_local",
                        "channels": ["ch1"],
                    }
                ]
                if two_devices
                else []
            ),
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
                "poll_ms": signal_poll_ms,
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
    bench["policy"]["sha256"] = _sha(policy_path.read_bytes())
    bench["package_lock"]["sha256"] = _sha(lock_path.read_bytes())
    bench["devices"][0]["descriptor"]["sha256"] = _sha(descriptor_path.read_bytes())
    _write(bench_path, bench)

    commissioning: dict[str, Any] = {
        "contract_version": "0.2.0",
        "id": "activation-commissioning",
        "version": "0.1.0",
        "description": "Synthetic activation harness commissioning. Not hardware-qualified.",
        "bench": {"id": BENCH_ID, "version": "0.1.0"},
        "policy": {"id": "activation-policy", "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "procedure_refs": [{"id": "activation-procedure", "version": "0.1.0"}],
        "dut_class": "low_voltage_embedded",
        "modes": ["supervised"],
        "owners": {
            "bench": "activation-harness-owner",
            "test_safety": "activation-harness-owner",
            "system": "activation-harness-owner",
        },
        "approved_by": "activation-harness-owner",
        "approved_at": "2026-09-11T00:00:00Z",
        "expires_at": "2030-01-01T00:00:00Z",
        "offline_status_max_age_ms": 86400000,
        "scheduling_overhead_ms": 100,
        "evidence": [
            {
                "category": "envelope",
                "report": {
                    "id": "activation-envelope-report",
                    "version": "0.1.0",
                    "sha256": "0" * 64,
                },
                "tested_at": "2026-09-11T00:00:00Z",
                "scope": "Simulator envelope over the synthetic activation supply.",
                "result": "passed",
                "limitations": ["simulator-only"] if simulated else [],
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
    commissioning_path = _write(tmp_path / "commissioning.json", commissioning)

    binding: dict[str, Any] = {
        "contract_version": "0.2.0",
        "request_id": request_id,
        "procedure": {"id": "activation-procedure", "version": "0.1.0"},
        "bench": {"id": BENCH_ID, "version": "0.1.0"},
        "policy": {"id": "activation-policy", "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "commissioning": {"id": "activation-commissioning", "version": "0.1.0"},
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
    _write(tmp_path / "run-binding.json", binding)
    return tmp_path


class _CommissionedHarness:
    """One admitted-and-activated dev closure plus its execution lattice."""

    def __init__(
        self,
        tmp_path: Path,
        request_id: str,
        *,
        signal_poll_ms: int = 50,
        continuous_max: float = 5.5,
        write_value: float = 5.0,
        enable_output: bool = False,
        stream_floor_ms: int = 10,
        streaming: bool = True,
        two_devices: bool = False,
        simulated: bool = True,
        commissioned: bool = True,
        release_mutator: Callable[[Path], None] | None = None,
        adapter_source: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        allow_rules: list[dict[str, Any]] | None = None,
        extra_permissions: tuple[str, ...] = (),
    ) -> None:
        self.root = tmp_path
        self._release_mutator = release_mutator
        self.lattice_dir = _lattice(
            tmp_path / "lattice",
            request_id,
            signal_poll_ms=signal_poll_ms,
            continuous_max=continuous_max,
            write_value=write_value,
            enable_output=enable_output,
            stream_floor_ms=stream_floor_ms,
            streaming=streaming,
            two_devices=two_devices,
            simulated=simulated,
            steps=steps,
            allow_rules=allow_rules,
            extra_permissions=extra_permissions,
        )
        descriptor_path = self.lattice_dir / "descriptor-demo-supply.json"
        plugin_dir = _write_plugin_source(tmp_path / "pluginroot", adapter_source)
        registry_root = tmp_path / "dev-registry"
        _publish(plugin_dir, descriptor_path, registry_root)
        if release_mutator is not None:
            release_mutator(registry_root)

        origins: dict[str, OriginConfig] = {
            DEV_ID: OriginConfig(
                registry_id=DEV_ID,
                root=None,
                source=LocalDirectorySource(registry_root / DEV_ID),
                namespaces=("dev",),
                signature_policy="dev-unsigned",
            ),
            ORIGIN_MAIN: OriginConfig(
                registry_id=ORIGIN_MAIN,
                root=_main_root(),
                source=LocalDirectorySource(REGISTRY_FIXTURES / ORIGIN_MAIN),
                namespaces=("benchweave",),
            ),
        }
        self.work = tmp_path / "registry-work"
        from benchweave.interfaces.bootstrap import RegistrySession

        self.session = RegistrySession(
            resolver=Resolver(origins),
            roots={ORIGIN_MAIN: _main_root()},
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
                principal_id="activation-harness",
                approved_at=NOW_ISO,
                policy_id="local-policy",
                policy_version="1.0.0",
            ),
            now_ns=NOW_NS,
            # Admission's roots cover EVERY origin in the closure, the
            # dev origin included (None root = dev-unsigned); the session's
            # own roots field stays typed to real trust roots.
            roots={DEV_ID: None, ORIGIN_MAIN: _main_root()},
            high_water=self.session.high_water,
        )
        # The commissioning admin act: the activation record for generation
        # 2 is what the bench device's declared generation links to. A
        # non-commissioned harness (the F3 refusal and disclosure legs)
        # skips it — the device then has no commissioned closure.
        if commissioned:
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
        admit_startup_bench(store, content, self.lattice_dir, now=NOW_ISO)
        return store, content

    def build_run(self, limits: dict[str, int]) -> Callable[[str, str, dict[str, Any], Store], Any]:
        from benchweave.control.clocking import SystemClock

        factory = _build_run_factory(
            self.lattice_dir, SystemClock().now_iso, limits=limits, registry_session=self.session
        )
        return factory

    def binding_ref(self, request_id: str | None = None) -> dict[str, str]:
        """The §5 binding ref, optionally under a FRESH request id.

        Rewriting the request id (the only unpinned field — nothing pins
        the binding) lets one lattice serve several runs: the measurer's
        queued-run leg (M-C) submits a second run behind a live one
        without re-authoring the lattice.
        """
        path = self.lattice_dir / "run-binding.json"
        if request_id is not None:
            binding = json.loads(path.read_bytes())
            binding["request_id"] = request_id
            path.write_text(json.dumps(binding, indent=2))
        raw = path.read_bytes()
        return {
            "id": json.loads(raw)["request_id"],
            "version": "0.1.0",
            "sha256": _sha(raw),
        }


@pytest.fixture()
def commissioned(tmp_path: Path) -> _CommissionedHarness:
    return _CommissionedHarness(tmp_path, "req-activation-1")


def _coordinator(
    harness: _CommissionedHarness,
    run_id: str,
    limits: dict[str, int],
    *,
    request_id: str | None = None,
) -> tuple[Any, Store, ContentStore]:
    # A fresh request id REWRITES the binding file BEFORE open_store:
    # startup admission stores the lattice documents it finds, so the
    # rewritten binding must be on disk first.
    binding = harness.binding_ref(request_id)
    store, content = harness.open_store()
    try:
        factory = harness.build_run(limits)
        return factory(run_id, "principal-activation", binding, store), store, content
    except BaseException:
        store.close()
        raise


def test_r10_real_bridges_over_the_worker_store(commissioned: _CommissionedHarness) -> None:
    """R10: adapter-mode devices with a commissioned closure construct real
    bridges — the adapter's received services object is the eight-member
    capture bundle, and the run's terminal record is produced through the
    bridge (the sim path is NOT taken for the device)."""
    run_id = "run-r10"
    coordinator, store, content = _coordinator(commissioned, run_id, QUOTA_LIMITS)
    from benchweave.interfaces.app import _RetainingCoordinator

    assert isinstance(coordinator, _RetainingCoordinator)
    try:
        bridge = coordinator.plugins[DEVICE_ID]
        assert isinstance(bridge, OTDPBridge)
        received = bridge._adapter.services
        assert isinstance(received, CaptureServicesBundle)
        for member in (
            "monotonic",
            "utc_now",
            "transfer",
            "close_transport",
            "record_evidence",
            "artifact_append",
            "artifact_finalise",
            "artifact_abort",
        ):
            assert hasattr(received, member), member

        record = coordinator.start_run(run_id, "principal-activation")
        assert record["outcome"] == "passed"
        assert record["body_outcome"] == "completed"
        assert record["safe_state"] == "verified"
        kinds = [event["kind"] for event in store.read_events(f"run:{run_id}")]
        assert "write" in kinds and "read" in kinds
        # The bridge's adapter saw the procedure's write and the monitor's
        # read traffic — the run executed through the bridge, not a sim.
        assert "write" in bridge._adapter.dispatches
        assert "read" in bridge._adapter.dispatches
    finally:
        store.close()


def test_r16_quota_seam_refuses_before_plugin_open(
    commissioned: _CommissionedHarness,
) -> None:
    """R16: a commissioned adapter device + missing required quota keys →
    ``build_run`` refuses loudly before any device opens, and the worker
    contains the job (terminal projection, no fabricated outcome)."""
    limits = {key: value for key, value in QUOTA_LIMITS.items()
              if key not in ("max_dataset_bytes", "max_event_batch")}
    store, content = commissioned.open_store()
    try:
        factory = commissioned.build_run(limits)
        with pytest.raises(ValueError) as refused:
            factory("run-r16", "principal-activation", commissioned.binding_ref(), store)
        message = str(refused.value)
        assert "max_dataset_bytes" in message
        assert "max_event_batch" in message
        # Nothing opened: no bridge exists, and no run row was created.
        assert store.get_run("run-r16") is None
    finally:
        store.close()

    # The worker's poison guard contains the same refusal honestly: the
    # queue state closes terminal WITHOUT a terminal record (no fabricated
    # outcome), and the drain continues.
    store2, content2 = commissioned.open_store()
    try:
        worker = RunWorker(
            store2,
            content2,
            build_run=commissioned.build_run(limits),
            now_iso=lambda: NOW_ISO,
            limits=limits,
        )
        worker.start()
        try:
            worker.submit("run-r16b", "principal-activation", commissioned.binding_ref(), BENCH_ID)
            assert worker.join(timeout=10.0)
        finally:
            worker.stop()
            assert worker.join(timeout=5.0)
        states = {
            str(row["run_id"]): str(row["state"])
            for row in store2.list_run_states(BENCH_ID)
        }
        assert states.get("run-r16b") == "terminal"
        run = store2.get_run("run-r16b")
        assert run is None or run["terminal"] is None
    finally:
        store2.close()


def _loaded_adapter_module() -> Any:
    """The harness adapter's loaded module (found by its marker constant —
    the bundle loader mints a unique module prefix per construction)."""
    import sys as _sys

    for _name, module in list(_sys.modules.items()):
        if getattr(module, "DEMO_ADAPTER", False):
            return module
    raise AssertionError("harness adapter module not loaded")


def _event_log_refs(store: Store, run_id: str) -> list[dict[str, Any]]:
    """The run's landed ``event_log`` evidence rows (the report model's
    store-connection enumeration idiom — the content tables have no list
    API)."""
    rows = store.connection.execute(
        "SELECT content_ref_json FROM evidence WHERE context_key = ? AND kind = ?",
        (f"run:{run_id}", "event_log"),
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _assert_subscriptions_terminal(coordinator: Any) -> None:
    """Every subscription the run issued reached a terminal registry state."""
    host = coordinator.stream_host
    assert host is not None
    for device_id, subscription_ids in host.subscriptions.items():
        entry = host.devices[device_id]
        for subscription_id in subscription_ids:
            assert entry.controller.is_known(subscription_id), subscription_id
            assert not entry.controller.is_live(subscription_id), subscription_id
        assert entry.controller.live_subscription_ids() == []


def test_r11_one_shared_reading_sinks_across_run_services_and_controllers(
    commissioned: _CommissionedHarness,
) -> None:
    """R11: a sink registered through the run services
    (``register_reading_sink``) receives a reading delivered by a stream
    landing on a ``StreamController`` constructed in the same
    ``build_run`` — the two-default-instances shape is unrepresentable."""
    run_id = "run-r11"
    coordinator, store, content = _coordinator(commissioned, run_id, QUOTA_LIMITS)
    try:
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        assert coordinator.services is not None
        readings: list[Any] = []
        coordinator.services.register_reading_sink(readings.append)
        record = coordinator.start_run(run_id, "principal-activation")
        assert record["outcome"] == "passed"
        assert readings, "the shared sink observed no landed telemetry reading"
        voltages = [r["value"] for r in readings if r.get("parameter") == "output_voltage_v"]
        assert voltages and all(isinstance(v, (int, float)) for v in voltages)
        _assert_subscriptions_terminal(coordinator)
    finally:
        store.close()


def test_r12_slice_binding_and_hang_cut_lands_at_the_slice(
    commissioned: _CommissionedHarness,
) -> None:
    """R12: the composed engine's poll slice equals ``bench_poll_ns(bench)``
    (asserted on the composed run), and a hang-past-slice adapter's asyncio
    cut lands at the slice under the shared timebase — the production
    instance of the M2 pin (seconds = nanoseconds/1e9 of the one clock)."""
    import time as _time

    from benchweave.control.protection import bench_poll_ns

    run_id = "run-r12"
    coordinator, store, content = _coordinator(commissioned, run_id, QUOTA_LIMITS)
    try:
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        bench = json.loads((commissioned.lattice_dir / "bench.json").read_bytes())
        assert coordinator.stream_host is not None
        host = coordinator.stream_host
        module = _loaded_adapter_module()
        module.HANG_NEXT_EVENT = True
        started = _time.monotonic()
        record = coordinator.start_run(run_id, "principal-activation")
        elapsed = _time.monotonic() - started
        module.HANG_NEXT_EVENT = False
        # The slice binding: equality with the one derivation.
        assert host.poll_slice_ns == bench_poll_ns(bench)
        # The cut: a 10 s hang sliced at 50 ms — the run cannot have waited
        # the hang out (the asyncio timeout cut it at the slice deadline
        # computed on the SAME clock the engine slices on).
        assert elapsed < 5.0, f"run wall {elapsed:.2f}s — the hang was not cut"
        entry = host.devices[DEVICE_ID]
        assert entry.engine is not None and entry.engine.session_failed
        # The ending is the honest one: a cut poll cannot prove the adapter
        # did not hang (Decision 8) — session poison, uncertainty kept.
        assert record["safe_state"] in {"unknown", "verified"}
        assert record["outcome"] in {"outcome_unknown", "tripped", "execution_error"}
        _assert_subscriptions_terminal(coordinator)
    finally:
        store.close()


def test_r13_raising_on_event_consumer_is_contained(
    commissioned: _CommissionedHarness,
) -> None:
    """R13: an ``on_event`` consumer that raises on every event — the body
    completes its steps, the protective transition runs, the terminal
    record is normal, every subscription reaches a terminal state, and the
    failure counter is > 0."""

    def raising_consumer(subscription_id: str, event: Any, receipt: str) -> None:
        raise RuntimeError("harness on_event consumer raises on every event")

    run_id = "run-r13"
    coordinator, store, content = _coordinator(commissioned, run_id, QUOTA_LIMITS)
    try:
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        assert coordinator.stream_host is not None
        coordinator.stream_host.on_event = raising_consumer
        record = coordinator.start_run(run_id, "principal-activation")
        assert record["body_outcome"] == "completed"
        assert record["outcome"] == "passed"
        assert record["safe_state"] == "verified"
        assert coordinator.stream_host.event_callback_failures > 0
        _assert_subscriptions_terminal(coordinator)
    finally:
        store.close()


def test_r14_streams_are_additive_to_protection(
    tmp_path: Path,
) -> None:
    """R14, telemetry half: during a delay step, telemetry lands as
    ``event_log`` evidence under ``run:{run_id}`` carrying the Decision-4
    landing fields."""
    harness = _CommissionedHarness(tmp_path, "req-activation-r14a")
    run_id = "run-r14a"
    coordinator, store, content = _coordinator(harness, run_id, QUOTA_LIMITS)
    try:
        coordinator.start_run(run_id, "principal-activation")
        refs = _event_log_refs(store, run_id)
        assert refs, "no event_log evidence landed under the run context"
        telemetry = [ref for ref in refs if ref.get("kind") == "telemetry"]
        assert telemetry
        for ref in telemetry:
            assert ref.get("subscription_id")
            assert isinstance(ref.get("sequence"), int)
            assert ref.get("host_received_at")
        _assert_subscriptions_terminal(coordinator)
    finally:
        store.close()


def test_r14_condition_trip_mid_delay_ends_body_tripped(
    tmp_path: Path,
) -> None:
    """R14, protection half: a condition that trips mid-delay still ends
    the body ``tripped`` — the read-based monitor gates; streams neither
    replace nor mask it."""
    harness = _CommissionedHarness(
        tmp_path,
        "req-activation-r14b",
        continuous_max=4.5,
        write_value=5.0,
        enable_output=True,
    )
    run_id = "run-r14b"
    coordinator, store, content = _coordinator(harness, run_id, QUOTA_LIMITS)
    try:
        record = coordinator.start_run(run_id, "principal-activation")
        assert record["body_outcome"] == "tripped"
        assert any("dut-voltage-bounds" in reason for reason in record["reasons"])
        _assert_subscriptions_terminal(coordinator)
    finally:
        store.close()


def test_r15_fast_bench_signal_degrades_loudly(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """R15: a bench signal commissioned faster than the descriptor's
    declared floor — the subscription is refused cleanly, a
    machine-prefixed log line names it, the run proceeds, no session
    poison. The variant raises the descriptor's floor above the bench's
    50 ms cadence (the same G2 refusal as a sub-floor signal, without a
    bench-wide cadence so tight the monitor's own read budget flakes)."""
    harness = _CommissionedHarness(tmp_path, "req-activation-r15", stream_floor_ms=100)
    run_id = "run-r15"
    coordinator, store, content = _coordinator(harness, run_id, QUOTA_LIMITS)
    try:
        import logging as _logging

        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        with caplog.at_level(_logging.WARNING, logger="benchweave.control.stream_host"):
            record = coordinator.start_run(run_id, "principal-activation")
        assert record["outcome"] == "passed"
        assert any(
            "stream_subscribe_refused" in record_.message
            for record_ in caplog.records
        ), "the loud-degradation marker is absent from the log"
        assert coordinator.stream_host is not None
        entry = coordinator.stream_host.devices[DEVICE_ID]
        assert entry.engine is None, "a sub-floor subscription must not go live"
        assert entry.controller.live_subscription_ids() == []
    finally:
        store.close()


# --- fix wave F5: the M-A measurement seams (tick times, saturated polls) -------------


def _worst_tick_gap(times: list[float]) -> float:
    """The worst monitor-tick gap over one window (M-A's tick axis)."""
    return max((b - a for a, b in zip(times, times[1:], strict=False)), default=0.0)


def test_f5_measurement_seams_tick_times_and_saturated_polls(
    commissioned: _CommissionedHarness,
) -> None:
    """F5 smoke (machinery, not an acceptance control): the tick recorder
    times EVERY monitor tick (dispatch-driven and engine-driven), and the
    saturated slow-poll mode overruns most of each slice while SURVIVING —
    the regime M-A's worst-gap-over-windows rule measures. Without these
    seams the pre-committed M-A rule is unmeasurable."""
    run_id = "run-f5"
    coordinator, store, content = _coordinator(commissioned, run_id, QUOTA_LIMITS)
    try:
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        host = coordinator.stream_host
        assert host is not None
        tick_times: list[float] = []
        host.tick_recorder = tick_times.append
        landing_times: list[float] = []
        host.on_event = lambda subscription_id, event, receipt: landing_times.append(
            time.monotonic()
        )
        module = _loaded_adapter_module()
        module.SLOW_NEXT_EVENT_MS = 100  # slice is 50 ms -> ~45 ms per poll
        coordinator.start_run(run_id, "principal-activation")
        module.SLOW_NEXT_EVENT_MS = 0
        assert len(tick_times) >= 5, "the tick recorder observed no rhythm"
        worst = _worst_tick_gap(tick_times)
        assert worst >= 0.040, (
            f"worst tick gap {worst * 1000:.1f} ms — saturated rounds absent"
        )
        assert landing_times, "no events landed in the saturated window"
        entry = host.devices[DEVICE_ID]
        assert entry.engine is not None
        slow_polls = [
            span for verb, started, ended in entry.bridge._adapter.dispatch_spans
            if verb == "next_event" and (ended - started) >= 0.040
            for span in [ended - started]
        ]
        assert slow_polls, "no overrun poll spans recorded"
    finally:
        store.close()


# --- fix wave F4: closure resolution pins the served raw digest ----------------------


def _prettify_impl_manifest(registry_root: Path) -> None:
    """Rewrite the implementation release's manifest with indent=2 bytes
    and repin the (unsigned dev) status's manifest digest to the new raw
    bytes — a content-identical, non-canonically-formatted release that
    resolves and admits cleanly."""
    release = registry_root / DEV_ID / IMPL_PACKAGE / PACKAGE_VERSION
    manifest = json.loads((release / "manifest.json").read_bytes())
    pretty = json.dumps(manifest, indent=2)
    (release / "manifest.json").write_text(pretty)
    status = json.loads((release / "status.json").read_bytes())
    status["release"]["manifest_sha256"] = _sha(pretty.encode())
    canonical_status = (
        json.dumps(status, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    (release / "status.json").write_bytes(canonical_status)


def test_f4_pretty_printed_manifest_refused_at_resolution(tmp_path: Path) -> None:
    """F4 GREEN (issue #176 row G): the pre-composed residual — a
    content-identical pretty-printed manifest resolves, admits and pins
    cleanly, then dies at ``load_otdp_plugin`` as a misleading
    ``manifest_hash_mismatch`` — is now unrepresentable: the resolver
    refuses the non-canonical serialization AT RESOLUTION, so commissioning
    never sees it. Reverting the resolver's canonicality check re-opens the
    residual and this control fails (the closure resolves again)."""
    from benchweave.registry.schemas import RegistryRejected

    with pytest.raises(RegistryRejected) as refused:
        _CommissionedHarness(
            tmp_path, "req-f4a", release_mutator=_prettify_impl_manifest
        )
    assert refused.value.reason == "manifest_not_canonical"


# --- fix wave F3: the sim fallback is gated on the simulation mark --------------------


def test_f3_unmarked_bench_refuses_sim_substitution(tmp_path: Path) -> None:
    """F3 RED control: an adapter-mode device with no commissioned closure
    on a bench whose commissioning does NOT declare simulation must refuse
    — never silently substitute the simulator plugin on a device-id
    collision ({psu, controller}) and pass the run."""
    harness = _CommissionedHarness(
        tmp_path, "req-f3a", simulated=False, commissioned=False
    )
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ValueError, match="run_device_implementation_absent"):
            factory("run-f3a", "principal-activation", harness.binding_ref(), store)
    finally:
        store.close()


def test_f3_marked_fallback_discloses_in_record(tmp_path: Path) -> None:
    """F3 RED control: on a simulation-declared bench the declarative
    fallback runs AND the discriminator is record-visible — the terminal
    record's reasons disclose which implementation produced the
    evidence."""
    harness = _CommissionedHarness(
        tmp_path, "req-f3b", simulated=True, commissioned=False
    )
    run_id = "run-f3b"
    coordinator, store, content = _coordinator(harness, run_id, QUOTA_LIMITS)
    try:
        record = coordinator.start_run(run_id, "principal-activation")
        assert record["outcome"] == "passed"
        assert any(
            "implementation_disclosure" in reason
            and DEVICE_ID in reason
            and "declarative-sim-fallback" in reason
            for reason in record["reasons"]
        ), f"no implementation disclosure in reasons={record['reasons']}"
    finally:
        store.close()


# --- fix wave F2: teardown-window violations reach the record ----------------------


def test_f2_violation_during_teardown_window_reaches_the_record(
    commissioned: _CommissionedHarness,
) -> None:
    """F2 RED control: a monitored-signal drift that begins exactly on the
    ending stream_unsubscribe (inside the teardown window, after the body)
    must appear in the terminal record's reasons — today the phase flip
    disarms cause-blocking AND on_violation is not yet armed, so the
    violation vanishes and the record reports a bare outcome with no
    reason naming it."""
    run_id = "run-f2"
    coordinator, store, content = _coordinator(commissioned, run_id, QUOTA_LIMITS)
    try:
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        module = _loaded_adapter_module()
        module.TRIP_AFTER_UNSUBSCRIBE = True
        record = coordinator.start_run(run_id, "principal-activation")
        module.TRIP_AFTER_UNSUBSCRIBE = False
        assert any(
            "dut-voltage-bounds" in reason for reason in record["reasons"]
        ), (
            "the teardown-window violation vanished from the record "
            f"(reasons={record['reasons']})"
        )
    finally:
        store.close()


# --- fix wave F1: every commissioned bridge closes exactly once --------------------


def test_f1_event_sink_less_bridge_closes_at_run_end(tmp_path: Path) -> None:
    """F1 RED control: a commissioned bridge with NO event services (the
    committed fixture shape — transport-only permissions) is outside the
    streaming registry, so the run's only close path never saw it. It must
    close exactly once at run end regardless of registration."""
    harness = _CommissionedHarness(tmp_path, "req-f1a", streaming=False)
    run_id = "run-f1a"
    coordinator, store, content = _coordinator(harness, run_id, QUOTA_LIMITS)
    try:
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        bridge = coordinator.plugins[DEVICE_ID]
        assert isinstance(bridge, OTDPBridge)
        before = type(bridge._adapter).CLOSE_CALLS
        coordinator.start_run(run_id, "principal-activation")
        assert bridge._closed, "event_sink-less bridge was never closed at run end"
        assert before + 1 == type(bridge._adapter).CLOSE_CALLS
    finally:
        store.close()


def test_f1_bridges_close_when_start_run_raises(tmp_path: Path) -> None:
    """F1 RED control: a start_run that raises after construction (the §9
    replay refusal is the natural arm) must still close the bridges it
    opened — the Runner and adapter session do not leak past the raise."""
    harness = _CommissionedHarness(tmp_path, "req-f1b", streaming=False)
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        first = factory("run-f1b1", "principal-activation", harness.binding_ref(), store)
        first.start_run("run-f1b1", "principal-activation")
        second = factory("run-f1b2", "principal-activation", harness.binding_ref(), store)
        bridge = second.plugins[DEVICE_ID]
        with pytest.raises(ValueError, match="never reusable"):
            second.start_run("run-f1b2", "principal-activation")
        assert bridge._closed, "bridges leaked past a raising start_run"
    finally:
        store.close()


def test_f1_bridges_close_when_construction_raises_mid_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1 RED control: a construction failure AFTER one bridge opened (the
    second device's sim plugin fails to load) must close the opened bridge
    before the refusal propagates."""
    from benchweave.registry.otdp_loading import load_otdp_plugin as real_load_bridge

    harness = _CommissionedHarness(
        tmp_path, "req-f1c", streaming=False, two_devices=True
    )
    store, content = harness.open_store()
    opened: list[OTDPBridge] = []

    def capturing_load(*args: Any, **kwargs: Any) -> OTDPBridge:
        bridge = real_load_bridge(*args, **kwargs)
        opened.append(bridge)
        return bridge

    def broken_sim_load(name: str) -> Any:
        raise ImportError(f"harness refuses to load sim plugin {name!r}")

    import benchweave.interfaces.app as app_module

    monkeypatch.setattr(app_module, "load_otdp_plugin", capturing_load)
    monkeypatch.setattr(app_module, "_load_sim_plugin", broken_sim_load)
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ImportError):
            factory("run-f1c", "principal-activation", harness.binding_ref(), store)
        assert opened, "the psu bridge never constructed before the refusal"
        assert opened[0]._closed, "the opened bridge leaked past the raise"
    finally:
        store.close()


# --- the measurement harness machinery (M-A/M-B/M-C support) -----------------------
#
# The bench-measurer lane's formal evidence is produced AFTER refute; what
# lands here is the machinery it composes on: the adapter records a
# (verb, started, ended) monotonic span per dispatch and per next_event
# poll (M-A's per-poll latencies; M-B's dispatch wall-stretch), the stream
# host's replaceable on_event consumer is the landing-time channel (M-A's
# events/s windows), the composed bridge answers capture dispatches over
# the real staged writer (M-B's contention shape), and binding_ref(mints
# fresh request ids so a second run can queue behind a live one (M-C).


def test_measurement_harness_capture_dispatch_over_the_composed_bridge(
    commissioned: _CommissionedHarness,
) -> None:
    """Harness smoke: a capture dispatch through the composed bridge
    (build_run-constructed, eight-member bundle, staged writer over the
    worker store) publishes a manifest with host-computed digest and
    length — the machinery M-B's contention measurement drives."""
    run_id = "run-capture-smoke"
    coordinator, store, content = _coordinator(commissioned, run_id, QUOTA_LIMITS)
    try:
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        bridge = coordinator.plugins[DEVICE_ID]
        assert isinstance(bridge, OTDPBridge)
        request = OperationRequest(
            operation_id="capture-smoke-1",
            verb=OperationVerb.CAPTURE,
            arguments={
                "capture_id": "cap.smoke-1",
                "format": "waveform_f64le",
                "sample_count": 4,
                "max_bytes": 64,
            },
        )
        result = bridge.dispatch(request, deadline_ns=time.monotonic_ns() + 5_000_000_000)
        assert result.status is OperationStatus.OK, result.error
        manifest = result.data
        assert manifest["capture_id"] == "cap.smoke-1"
        assert manifest["byte_length"] == 32
        assert manifest["sample_count"] == 4
        assert len(manifest["sha256"]) == 64
        spans = [span for span in bridge._adapter.dispatch_spans if span[0] == "capture"]
        assert spans and spans[0][2] > spans[0][1]
    finally:
        store.close()


def test_issue146_invoke_lane_composes_over_the_real_activation_path(
    commissioned: _CommissionedHarness,
) -> None:
    """Issue #146 slice 2 wiring + slice 3's composed bundle: the
    demo-supply descriptor is invoke-capable, pins the corpus contract
    pair and holds artifact_writer — build_run's real activation loop
    constructs the dataset controller, hands it the session's shared
    staged writer (the invoke clamp is live), and the ADAPTER's services
    bundle carries the composed dataset lane (publish/lookup + the
    payload members) beside the capture members."""
    run_id = "run-invoke-wiring"
    coordinator, store, content = _coordinator(commissioned, run_id, QUOTA_LIMITS)
    try:
        from contextlib import nullcontext

        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        bridge = coordinator.plugins[DEVICE_ID]
        assert isinstance(bridge, OTDPBridge)
        assert bridge._dataset is not None, "no dataset controller on the real path"
        clamp = bridge._dataset.dispatch_clamp(
            time.monotonic_ns() + 5_000_000_000, now_ns=time.monotonic_ns()
        )
        clamp.__enter__()
        clamp.__exit__(None, None, None)
        assert not isinstance(clamp, nullcontext), (
            "the controller clamps nothing — the session writer never reached it"
        )
        # Slice 3: the adapter's services compose the dataset lane over the
        # capture bundle (the harness's Recording adapter captured them at
        # open — the only mechanism that reaches the adapter).
        adapter_services = bridge._adapter.services
        for member in (
            "dataset_publish",
            "dataset_lookup",
            "payload_create",
            "payload_append",
            "payload_finalise",
            "payload_abort",
            "artifact_append",
            "artifact_finalise",
            "artifact_abort",
        ):
            assert hasattr(adapter_services, member), member
    finally:
        store.close()


def test_demo_lattice_without_commissioned_closure_keeps_declarative_fallback(
    tmp_path: Path,
) -> None:
    """The demo lattice's adapter-mode devices declare generation 1 — the
    startup-admitted generation with NO activation record — so the run
    keeps the declarative sim fallback (loudly disclosed) instead of
    constructing a bridge it cannot commission. The committed demo flow is
    unaffected by the activation wiring."""
    from benchweave.interfaces.app import _SIM_PLUGINS

    factory = _build_run_factory(
        EXECUTION_FIXTURES,
        lambda: NOW_ISO,
        limits=QUOTA_LIMITS,
        registry_session=None,
    )
    store = Store.open(tmp_path / "demo-state.db")
    try:
        content = ContentStore(store)
        admit_startup_bench(store, content, EXECUTION_FIXTURES, now=NOW_ISO)
        binding_raw = (EXECUTION_FIXTURES / "run-binding.json").read_bytes()
        binding_ref = {
            "id": json.loads(binding_raw)["request_id"],
            "version": "0.1.0",
            "sha256": _sha(binding_raw),
        }
        coordinator = factory(
            "run-demo-fallback", "principal-demo", binding_ref, store
        )
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        for device_id, _sim_name in _SIM_PLUGINS:
            plugin = coordinator.plugins[device_id]
            assert not isinstance(plugin, OTDPBridge), (
                f"demo device {device_id} constructed a bridge without a "
                "commissioned closure"
            )
    finally:
        store.close()
