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
import logging
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchweave.content.capture_services import CaptureServicesBundle
from benchweave.content.store import ContentStore
from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.types import OperationRequest, OperationStatus, OperationVerb
from benchweave.interfaces.app import _build_run_factory
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.device_closures import commissioned_device_closure
from benchweave.interfaces.worker import RunWorker
from benchweave.registry.activation import activate
from benchweave.registry.admission import AdmissionLimits, Approval, admit
from benchweave.registry.authenticity import TrustRoot, load_trust_root
from benchweave.registry.resolver import (
    LocalDirectorySource,
    OriginConfig,
    PackageSource,
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


def _public_pem(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _sign_release_tree(
    registry_root: Path, registry_id: str, key: Ed25519PrivateKey
) -> TrustRoot:
    """Runtime-key the served tree (issue #226 slice 4): sign every
    release's manifest and status bytes, return the matching trust root.

    The committed fixture statuses are signed by CI-materialised keys
    the tests cannot reuse, and the response-reach arms must rewrite and
    re-sign served statuses the way the SDK lifecycle ops do — so the
    harness keys its own origin (the replay_admission --fixture
    precedent) and signs everything the publisher left unsigned.
    """
    for status_path in sorted((registry_root / registry_id).rglob("status.json")):
        release_dir = status_path.parent
        for name in ("manifest", "status"):
            raw = (release_dir / f"{name}.json").read_bytes()
            (release_dir / f"{name}.sig").write_bytes(key.sign(raw))
    return TrustRoot(origin_id=registry_id, verify_key_pem=_public_pem(key))


def _keyed_dev_origin(registry_root: Path, registry_id: str = DEV_ID) -> TrustRoot:
    """Generate a runtime keypair, sign the served tree, return the root."""
    return _sign_release_tree(registry_root, registry_id, Ed25519PrivateKey.generate())


def _write_status(
    release_dir: Path, status: dict[str, Any], key: Ed25519PrivateKey | None
) -> None:
    """Canonical-encode a status document, write it, and sign it in place.

    The registry discipline every status writer follows: canonical JSON
    (sorted keys, compact separators, trailing newline — the fixture
    builder's form) and a detached signature over the exact served bytes.
    """
    raw = json.dumps(status, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    (release_dir / "status.json").write_bytes(raw)
    if key is not None:
        (release_dir / "status.sig").write_bytes(key.sign(raw))


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
        # Issue #316: the harness's gateway-owned runs carry the
        # commissioned unattended grant (a passing unattended-category row
        # beside the envelope row) — without it the run gate refuses.
        "modes": ["supervised", "unattended"],
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
            },
            {
                "category": "unattended",
                "report": {
                    "id": "activation-unattended-report",
                    "version": "0.1.0",
                    "sha256": "0" * 64,
                },
                "tested_at": "2026-09-11T00:00:00Z",
                "scope": "Simulator unattended endurance over the activation supply.",
                "result": "passed",
                # The simulation mark stays carried by the envelope row only
                # — this row inherits the harness's simulated flag so a
                # non-simulated bench keeps refusing sim substitution (F3).
                "limitations": ["simulator-only"] if simulated else [],
            },
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
        signed_dev_origin: bool = True,
        source_decorator: Callable[[PackageSource], PackageSource] | None = None,
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
        self.registry_root = registry_root
        # The signed posture (issue #226 slice 4): the harness keys its
        # own origin so arms can publish lifecycle changes the way the
        # SDK ops do — rewrite the served status, re-sign, let the
        # consult verify. The implementation release commissions at
        # sequence 2 (the floor the rollback arm needs: the status
        # schema's minimum sequence is 1, so a floor of 1 can never see a
        # served sequence below it).
        self.signing_key: Ed25519PrivateKey | None = None
        dev_root: TrustRoot | None = None
        if signed_dev_origin:
            self.signing_key = Ed25519PrivateKey.generate()
            impl_dir = registry_root / DEV_ID / IMPL_PACKAGE / PACKAGE_VERSION
            impl_status = json.loads((impl_dir / "status.json").read_bytes())
            impl_status["sequence"] = 2
            impl_status["reason"] = "harness commissioning revision"
            _write_status(impl_dir, impl_status, None)
            dev_root = _sign_release_tree(registry_root, DEV_ID, self.signing_key)

        def wrap(source: PackageSource) -> PackageSource:
            return source_decorator(source) if source_decorator is not None else source

        origins: dict[str, OriginConfig] = {
            DEV_ID: OriginConfig(
                registry_id=DEV_ID,
                root=dev_root,
                source=wrap(LocalDirectorySource(registry_root / DEV_ID)),
                namespaces=("dev",),
                signature_policy="dev-unsigned" if dev_root is None else "required",
            ),
            ORIGIN_MAIN: OriginConfig(
                registry_id=ORIGIN_MAIN,
                root=_main_root(),
                source=wrap(LocalDirectorySource(REGISTRY_FIXTURES / ORIGIN_MAIN)),
                namespaces=("benchweave",),
            ),
        }
        self._origins = origins
        self.work = tmp_path / "registry-work"
        from benchweave.interfaces.bootstrap import RegistrySession

        self.session = RegistrySession(
            resolver=Resolver(origins),
            roots={ORIGIN_MAIN: _main_root()},
            high_water={},
            cache_root=self.work / "cache",
            lock_path=self.work / "packages.lock.json",
            records_dir=self.work / "activations",
            advisories_dir=self.work / "advisories",
            status_cache={},
            consult_water={},
            limits=AdmissionLimits(
                max_archive_bytes=1_000_000, max_files=100, max_unpacked_bytes=1_000_000
            ),
            now_ns=lambda: NOW_NS,
            registry_id=DEV_ID,
        )
        if dev_root is not None:
            self.session.roots[DEV_ID] = dev_root
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
            # dev origin included (None root = dev-unsigned; the runtime
            # trust root under the signed posture); the session's own
            # roots field stays typed to real trust roots.
            roots={DEV_ID: dev_root, ORIGIN_MAIN: _main_root()},
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

    def release_dir(self, package_id: str) -> Path:
        """The served release directory for one dev package."""
        return self.registry_root / DEV_ID / package_id / PACKAGE_VERSION

    def rewrite_release_status(
        self,
        package_id: str,
        *,
        lifecycle: str | None = None,
        advisories: list[dict[str, Any]] | None = None,
        sequence: int | None = None,
        reason: str | None = None,
        updated_at: str = NOW_ISO,
        expires_at: str = "2027-09-11T00:00:00Z",
        manifest_sha256: str | None = None,
    ) -> None:
        """Publish a lifecycle change the way the SDK lifecycle ops do.

        Issue #226 slice 4, design §5 D1: lifecycle flip, ``sequence + 1``
        (or an explicit value), ``updated_at`` bumped, ``expires_at``
        renewed, canonical bytes, re-signed by the origin key.
        """
        assert self.signing_key is not None, "status rewriting needs the signed origin"
        release = self.release_dir(package_id)
        status = json.loads((release / "status.json").read_bytes())
        if lifecycle is not None:
            status["lifecycle"] = lifecycle
        if advisories is not None:
            status["advisories"] = advisories
        if reason is not None:
            status["reason"] = reason
        if sequence is not None:
            status["sequence"] = sequence
        else:
            status["sequence"] = int(status["sequence"]) + 1
        status["updated_at"] = updated_at
        status["expires_at"] = expires_at
        if manifest_sha256 is not None:
            status["release"]["manifest_sha256"] = manifest_sha256
        _write_status(release, status, self.signing_key)

    def fresh_session(self) -> None:
        """Replace the session with a process-fresh one over the same work
        root (issue #226 D1's cold-cache control): same resolver routing,
        same trust roots, cold status cache — the honest restart-freshness
        floor, where a process restart forces re-reads."""
        from benchweave.interfaces.bootstrap import RegistrySession

        self.session = RegistrySession(
            resolver=Resolver(self._origins),
            roots=dict(self.session.roots),
            high_water={},
            cache_root=self.work / "cache",
            lock_path=self.work / "packages.lock.json",
            records_dir=self.work / "activations",
            advisories_dir=self.work / "advisories",
            status_cache={},
            consult_water={},
            limits=self.session.limits,
            now_ns=lambda: NOW_NS,
            registry_id=DEV_ID,
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


# --- issue #226 slice 4: response reach — the cached status consult ------------------


def test_m6_baseline_published_revocation_does_not_reach_run_build(
    tmp_path: Path,
) -> None:
    """The M6 baseline, flipped at the mechanism commit (issue #226 slice 4,
    design §5 D1).

    The reproduced defect: the commissioned implementation release's
    served status was rewritten to ``revoked`` AFTER commissioning
    (lifecycle flip, sequence+1, updated_at bumped, re-signed by the
    origin key — the SDK lifecycle-op discipline), and the next run-build
    SUCCEEDED anyway, through the commissioned bridge (M6, PRD
    §5(l).1) — pinned green in the baseline commit (cc92037). The status
    consult closes M6: the same arm now refuses
    ``closure_status_revoked`` at run-build.
    """
    harness = _CommissionedHarness(tmp_path, "req-m6-baseline", signed_dev_origin=True)
    harness.rewrite_release_status(
        IMPL_PACKAGE, lifecycle="revoked", reason="published recall"
    )
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ValueError, match="closure_status_revoked"):
            factory(
                "run-m6", "principal-activation", harness.binding_ref(), store
            )
        assert store.get_run("run-m6") is None
    finally:
        store.close()


# The descriptor-override package publish_dev ships beside the
# implementation (the publisher's dashed-name rule: sim_psu -> sim-psu).
_DESCRIPTOR_PACKAGE = f"dev/{PLUGIN_DIRNAME.replace('_', '-')}-descriptor"

#: One served advisory (invented fixture content; the schema's closed shape).
_ADVISORY: dict[str, Any] = {
    "id": "adv-heat-derate",
    "severity": "medium",
    "summary": "Output derates above 40 degrees; requalify before extended runs.",
    "url": "https://example.invalid/advisories/adv-heat-derate",
}


class _CountingSource:
    """PackageSource wrapper counting status reads — D2's honest
    socket-equivalent: there is no socket to patch on a local-dir origin,
    so the arm counts the reads themselves."""

    def __init__(self, inner: PackageSource, reads: Counter[tuple[str, str]]) -> None:
        self._inner = inner
        self._reads = reads

    def manifest_bytes(self, package_id: str, version: str) -> tuple[bytes, str]:
        return self._inner.manifest_bytes(package_id, version)

    def status_bytes(self, package_id: str, version: str) -> tuple[bytes, str]:
        self._reads[(package_id, version)] += 1
        return self._inner.status_bytes(package_id, version)

    def payload_bytes(
        self, package_id: str, version: str, *, max_archive_bytes: int | None = None
    ) -> bytes:
        return self._inner.payload_bytes(
            package_id, version, max_archive_bytes=max_archive_bytes
        )

    def manifest_signature(self, package_id: str, version: str) -> bytes:
        return self._inner.manifest_signature(package_id, version)

    def status_signature(self, package_id: str, version: str) -> bytes:
        return self._inner.status_signature(package_id, version)


def _review_block(outcome: str) -> dict[str, Any]:
    """A schema-valid registry 0.1.2 review block (synthetic reviewer)."""
    return {
        "checklist_id": "review-checklist",
        "checklist_version": "1",
        "reviewer_id": "registry-reviewer-fixture",
        "outcome": outcome,
        "record_sha256": "b" * 64,
    }


def _upgrade_manifest_with_review(registry_root: Path, outcome: str) -> None:
    """Mutator: upgrade the implementation manifest to registry 0.1.2 with
    a review block (CR-13: admission stays review-indifferent — the
    release still resolves, admits and commissions; the drift it
    contradicts is surfaced only at the run-build consult, D4)."""
    release = registry_root / DEV_ID / IMPL_PACKAGE / PACKAGE_VERSION
    manifest = json.loads((release / "manifest.json").read_bytes())
    manifest["manifest_version"] = "0.1.2"
    manifest["review"] = _review_block(outcome)
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    (release / "manifest.json").write_bytes(raw)
    status = json.loads((release / "status.json").read_bytes())
    status["release"]["manifest_sha256"] = _sha(raw)
    _write_status(release, status, None)  # the harness signs afterwards


def _commissioning_inputs(harness: _CommissionedHarness) -> tuple[dict[str, Any], dict[str, Any]]:
    """The bench's commissioned device and its descriptor document."""
    bench = json.loads((harness.lattice_dir / "bench.json").read_bytes())
    descriptor = json.loads(
        (harness.lattice_dir / "descriptor-demo-supply.json").read_bytes()
    )
    return bench["devices"][0], descriptor


def _advisory_records(harness: _CommissionedHarness) -> list[dict[str, Any]]:
    """Every delivered operator record under the session's advisory dir."""
    return [
        json.loads(path.read_bytes())
        for path in sorted(harness.session.advisories_dir.glob("advisory-*.json"))
    ]


# --- D1: reach (CR-53; closes M6) ---------------------------------------------------


def test_d1_revoked_status_refuses_next_run_build(tmp_path: Path) -> None:
    """D1 SHIP arm — the flipped M6 baseline: a revocation published after
    commissioning refuses the NEXT run-build of the commissioned closure
    (the mechanism-composed refusal name; design record section 2.1
    step 6)."""
    harness = _CommissionedHarness(tmp_path, "req-d1-revoked", signed_dev_origin=True)
    harness.rewrite_release_status(
        IMPL_PACKAGE, lifecycle="revoked", reason="published recall"
    )
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ValueError, match="closure_status_revoked"):
            factory("run-d1-revoked", "principal-activation", harness.binding_ref(), store)
        assert store.get_run("run-d1-revoked") is None
    finally:
        store.close()


def test_d1_yanked_status_refuses_next_run_build(tmp_path: Path) -> None:
    """D1 SHIP arm: a published yank refuses the next run-build (the same
    class admission refuses at admit time, now enforced at the third
    moment)."""
    harness = _CommissionedHarness(tmp_path, "req-d1-yanked", signed_dev_origin=True)
    harness.rewrite_release_status(
        IMPL_PACKAGE, lifecycle="yanked", reason="author yank"
    )
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ValueError, match="closure_status_yanked"):
            factory("run-d1-yanked", "principal-activation", harness.binding_ref(), store)
    finally:
        store.close()


def test_d1_advisory_status_proceeds_and_delivers_operator_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """D1 SHIP arm (Q14's recorded operator half): an advisory-carrying
    published status does NOT refuse the run — the advisory is DELIVERED
    as one append-once operator record plus a warning line, and re-consults
    (within the bound and beyond it) write no duplicate."""
    harness = _CommissionedHarness(tmp_path, "req-d1-advisory", signed_dev_origin=True)
    harness.rewrite_release_status(
        IMPL_PACKAGE, advisories=[dict(_ADVISORY)], reason="heat advisory"
    )
    run_id = "run-d1-advisory"
    coordinator, store, content = _coordinator(harness, run_id, QUOTA_LIMITS)
    try:
        with caplog.at_level(
            logging.WARNING, logger="benchweave.interfaces.device_closures"
        ):
            record = coordinator.start_run(run_id, "principal-activation")
        assert record["outcome"] == "passed"
        assert any(
            "closure_status_advisory" in entry.message for entry in caplog.records
        )
        delivered = _advisory_records(harness)
        assert len(delivered) == 1
        assert delivered[0]["kind"] == "operator_advisory"
        assert delivered[0]["advisory"] == _ADVISORY
        assert delivered[0]["release"]["package_id"] == IMPL_PACKAGE
        assert delivered[0]["release"]["registry_id"] == DEV_ID
        assert len(delivered[0]["status_sha256"]) == 64
        assert delivered[0]["consulted_at"]
    finally:
        store.close()

    # Re-consult within the bound (the cached view serves; zero reads) ...
    coordinator2, store2, _content2 = _coordinator(
        harness, "run-d1-advisory-b", QUOTA_LIMITS, request_id="req-d1-advisory-b"
    )
    try:
        record2 = coordinator2.start_run("run-d1-advisory-b", "principal-activation")
        assert record2["outcome"] == "passed"
    finally:
        store2.close()
    assert len(_advisory_records(harness)) == 1

    # ... and beyond the bound (the origin is re-read; the SAME advisory
    # id is already recorded — still exactly one record).
    from benchweave.interfaces.device_closures import _STATUS_CONSULT_BOUND_NS

    harness.session.now_ns = lambda: NOW_NS + _STATUS_CONSULT_BOUND_NS + 1
    coordinator3, store3, _content3 = _coordinator(
        harness, "run-d1-advisory-c", QUOTA_LIMITS, request_id="req-d1-advisory-c"
    )
    try:
        record3 = coordinator3.start_run("run-d1-advisory-c", "principal-activation")
        assert record3["outcome"] == "passed"
    finally:
        store3.close()
    assert len(_advisory_records(harness)) == 1


def test_d1_rolled_back_status_refuses_sequence_rollback(tmp_path: Path) -> None:
    """D1 SHIP arm: a served sequence BELOW the persisted floor refuses
    (consult semantics — the reason name is deliberately distinct from
    the resolver's ``stale_sequence``; same-sequence replay is the healthy
    case and stays green in the controls below)."""
    harness = _CommissionedHarness(tmp_path, "req-d1-rollback", signed_dev_origin=True)
    harness.rewrite_release_status(
        IMPL_PACKAGE, sequence=1, reason="rolled back to the initial revision"
    )
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ValueError, match="closure_status_sequence_rollback"):
            factory("run-d1-rollback", "principal-activation", harness.binding_ref(), store)
    finally:
        store.close()


def test_d1_resurrection_via_origin_rollback_refused(tmp_path: Path) -> None:
    """adv1-F1 fold (issue #226): an origin rollback cannot resurrect a run
    past an AUTHENTICATED revocation within one session.

    The executed defect: a revocation at sequence 3 refuses the run-build;
    restoring the previously-signed sequence-2 bytes (an attacker needs no
    key — the old bytes were always validly signed) made the next consult
    pass the same-sequence replay, and a full run executed. The consult
    keeps a SESSION consult-water per release — every authenticated
    consult raises it, lifecycle refusals included (a revoked view counts)
    — and a consult below the water refuses
    ``closure_status_sequence_rollback``. Cross-restart exposure (a
    restart resets the water to the persisted admission floor) is the
    named residual for the PR body, tied to the Q19 re-issue."""
    harness = _CommissionedHarness(tmp_path, "req-d1-resurrect", signed_dev_origin=True)
    release = harness.release_dir(IMPL_PACKAGE)
    restored_status = (release / "status.json").read_bytes()
    restored_sig = (release / "status.sig").read_bytes()
    harness.rewrite_release_status(
        IMPL_PACKAGE, lifecycle="revoked", reason="published recall"
    )
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ValueError, match="closure_status_revoked"):
            factory("run-res-a", "principal-activation", harness.binding_ref(), store)
        # The origin rolls back to the previously-signed sequence-2 bytes.
        (release / "status.json").write_bytes(restored_status)
        (release / "status.sig").write_bytes(restored_sig)
        with pytest.raises(ValueError, match="closure_status_sequence_rollback"):
            factory("run-res-b", "principal-activation", harness.binding_ref(), store)
        assert store.get_run("run-res-b") is None
    finally:
        store.close()


def test_d1_expired_status_refuses_expired_status(tmp_path: Path) -> None:
    """D1 SHIP arm: a status whose ``expires_at`` is past refuses — an
    unattested lifecycle is UNKNOWN, not published (A06; the same clock
    admission already enforces at admit time)."""
    harness = _CommissionedHarness(tmp_path, "req-d1-expired", signed_dev_origin=True)
    harness.rewrite_release_status(
        IMPL_PACKAGE, expires_at="2026-09-13T00:00:00Z", reason="status lapsed"
    )
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ValueError, match="closure_status_expired_status"):
            factory("run-d1-expired", "principal-activation", harness.binding_ref(), store)
    finally:
        store.close()


def test_d1_swapped_status_refuses_release_mismatch(tmp_path: Path) -> None:
    """D1 SHIP arm: a validly-signed status naming ANOTHER release's key
    and manifest digest cannot mask this release's lifecycle — the
    binding check fires before the gates (design section 2.1 step 4)."""
    harness = _CommissionedHarness(tmp_path, "req-d1-swap", signed_dev_origin=True)
    donor = harness.release_dir(_DESCRIPTOR_PACKAGE)
    target = harness.release_dir(IMPL_PACKAGE)
    (target / "status.json").write_bytes((donor / "status.json").read_bytes())
    (target / "status.sig").write_bytes((donor / "status.sig").read_bytes())
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ValueError, match="closure_status_release_mismatch"):
            factory("run-d1-swap", "principal-activation", harness.binding_ref(), store)
    finally:
        store.close()


def test_d1_absent_status_refuses_closure_status_absent(tmp_path: Path) -> None:
    """D1 SHIP arm and D3's offline half: with a cold cache and the status
    channel absent from the origin, the consult refuses loudly — never
    asserts published (F1, fail-closed)."""
    harness = _CommissionedHarness(tmp_path, "req-d1-absent", signed_dev_origin=True)
    release = harness.release_dir(IMPL_PACKAGE)
    (release / "status.json").unlink()
    (release / "status.sig").unlink()
    store, content = harness.open_store()
    try:
        factory = harness.build_run(QUOTA_LIMITS)
        with pytest.raises(ValueError, match="closure_status_absent"):
            factory("run-d1-absent", "principal-activation", harness.binding_ref(), store)
    finally:
        store.close()


def test_d1_control_untouched_closure_same_sequence_replay_stays_green(
    tmp_path: Path,
) -> None:
    """D1 control: the untouched closure — every release served at exactly
    the sequence it was admitted at (impl 2, descriptor 1, profile 1) —
    run-builds green: consult semantics replay the same authenticated
    sequence; only a lower one refuses."""
    harness = _CommissionedHarness(tmp_path, "req-d1-ctl", signed_dev_origin=True)
    coordinator, store, content = _coordinator(harness, "run-d1-ctl", QUOTA_LIMITS)
    try:
        record = coordinator.start_run("run-d1-ctl", "principal-activation")
        assert record["outcome"] == "passed"
        assert isinstance(coordinator.plugins[DEVICE_ID], OTDPBridge)
    finally:
        store.close()


def test_d1_control_cold_cache_after_fresh_session_stays_green(
    tmp_path: Path,
) -> None:
    """D1 control: the healthy arm under a COLD cache after process-fresh
    session construction (the restart-freshness floor — a fresh session
    starts cold and re-reads everything)."""
    harness = _CommissionedHarness(tmp_path, "req-d1-cold", signed_dev_origin=True)
    harness.fresh_session()
    coordinator, store, content = _coordinator(harness, "run-d1-cold", QUOTA_LIMITS)
    try:
        record = coordinator.start_run("run-d1-cold", "principal-activation")
        assert record["outcome"] == "passed"
    finally:
        store.close()


# --- D2: staleness and cost (NFR-S3) -------------------------------------------------


def test_d2_staleness_bound_bounds_status_reads(tmp_path: Path) -> None:
    """D2 SHIP arms on the injected clock + the counting source: consult 1
    cold reads each release's status exactly once; a consult within the
    bound reads NOTHING (exact zero); a consult beyond the bound re-reads
    (each release again — the bound is the reach delay)."""
    reads: Counter[tuple[str, str]] = Counter()

    def wrap(source: PackageSource) -> PackageSource:
        return _CountingSource(source, reads)

    harness = _CommissionedHarness(
        tmp_path, "req-d2", signed_dev_origin=True, source_decorator=wrap
    )
    # The counter starts AFTER construction: the harness's own resolve
    # reads each release's status once while admitting (the resolver's
    # status_bytes — not the consult's), and the arm measures the consult
    # alone.
    reads.clear()
    clock = {"now": NOW_NS}
    harness.session.now_ns = lambda: clock["now"]
    device, descriptor = _commissioning_inputs(harness)

    # Consult 1, cold: exactly one status read per release (three
    # releases in the closure: implementation, descriptor, profile).
    assert (
        commissioned_device_closure(harness.session, BENCH_ID, device, descriptor)
        is not None
    )
    assert sum(reads.values()) == 3
    assert len(reads) == 3 and all(count == 1 for count in reads.values())

    # Consult 2, within the bound: the cached view serves — zero reads.
    assert (
        commissioned_device_closure(harness.session, BENCH_ID, device, descriptor)
        is not None
    )
    assert sum(reads.values()) == 3

    # Beyond the bound: the view is stale, every release re-reads.
    from benchweave.interfaces.device_closures import _STATUS_CONSULT_BOUND_NS

    clock["now"] = NOW_NS + _STATUS_CONSULT_BOUND_NS + 1
    assert (
        commissioned_device_closure(harness.session, BENCH_ID, device, descriptor)
        is not None
    )
    assert sum(reads.values()) == 6
    assert all(count == 2 for count in reads.values())


# --- D4: approval drift (CR-42) -------------------------------------------------------


def test_d4_review_changes_requested_surfaces_approval_drift(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """D4 SHIP arm: a commissioned release whose published review block
    records a non-acceptance (the local lock's approval block asserts an
    approval-for-commissioning) never rides silently — the consult
    surfaces one ``approval_drift`` operator record plus a warning line,
    and the run CONTINUES (surfaced, never enforced; REG-5's admission
    seam holds). Admission admitted the 0.1.2 changes-requested release
    unchanged — CR-13's review-indifference, proven by the fixture."""
    harness = _CommissionedHarness(
        tmp_path,
        "req-d4-drift",
        signed_dev_origin=True,
        release_mutator=lambda root: _upgrade_manifest_with_review(
            root, "changes-requested"
        ),
    )
    run_id = "run-d4-drift"
    coordinator, store, content = _coordinator(harness, run_id, QUOTA_LIMITS)
    try:
        with caplog.at_level(
            logging.WARNING, logger="benchweave.interfaces.device_closures"
        ):
            record = coordinator.start_run(run_id, "principal-activation")
        assert record["outcome"] == "passed"
        assert any(
            "closure_status_approval_drift" in entry.message
            for entry in caplog.records
        )
        surfaced = _advisory_records(harness)
        assert len(surfaced) == 1
        assert surfaced[0]["kind"] == "approval_drift"
        assert surfaced[0]["review"]["outcome"] == "changes-requested"
        assert surfaced[0]["review"]["reviewer_id"] == "registry-reviewer-fixture"
        assert surfaced[0]["release"]["package_id"] == IMPL_PACKAGE
    finally:
        store.close()


def test_d4_control_accepted_review_surfaces_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """D4 control: an accepted review block on the same 0.1.2 upgrade is
    agreement, not drift — no record, no warning."""
    harness = _CommissionedHarness(
        tmp_path,
        "req-d4-accepted",
        signed_dev_origin=True,
        release_mutator=lambda root: _upgrade_manifest_with_review(root, "accepted"),
    )
    run_id = "run-d4-accepted"
    coordinator, store, content = _coordinator(harness, run_id, QUOTA_LIMITS)
    try:
        with caplog.at_level(
            logging.WARNING, logger="benchweave.interfaces.device_closures"
        ):
            record = coordinator.start_run(run_id, "principal-activation")
        assert record["outcome"] == "passed"
        assert not any(
            "closure_status_approval_drift" in entry.message
            for entry in caplog.records
        )
        assert _advisory_records(harness) == []
    finally:
        store.close()
