"""D2 — the composed-path re-measurement rig (issue #159, option A).

The D2 slice's rig (record:
``.claude/deep-review/2026-10-08-issue159-d2-composed-remeasure-design.md``,
commit 1 on this branch): both continuity arms through the REAL composed run
path — a run admitted by ``admit_documents``, executed by the executor, on a
bench whose two devices are both real ``OTDPBridge`` instances built by
``_build_run_factory`` — re-measuring the four frozen axes and emitting
``_continuity_rule.TrialRecord`` ledgers with provenance (§2.8).

The instrument-level bands asserted here are the design's §4 clause 2 (the
#172 §5 bands at the rig's fixture scale: dispatch arm 200 ms, capture cut
at 50 ms budget, ``poll_ms`` 50, B frame period 50 ms (the poll cadence,
deviation 5), ``max_age_ms`` 500 (deviation 4)). They are the rig's own
discrimination proof, explicitly NOT ``G1/G2/P/TB`` and never citable as a
commissioning (A02). Every figure
this module prints carries its denominator (the rig's dispatch/poll/frame
scale), its cell (arm x class), and its sample size; the trial log is the
provenance record.

Deviations from the design's harness letter, all found on contact with the
code and none silent (the record's §6 risk 7 guard):

1. One merged registry lock, one activation record: ``admit`` clobbers the
   session lock with ITS closure's rows (admission.py:451) and ``activate``
   is generation-keyed, so the design's "two activate calls at
   bench_generation=1" is unconstructible (generation_conflict / lock
   drift). The harness runs the design's two publishes, two resolves and
   two admits, merges the two admitted lock documents (union of
   packages/roots, validated through ``load_lock_document``), and calls the
   REAL ``activate`` once over a constructed ``Admitted`` binding the
   merged digest. Both devices declare the resulting generation 2. No
   ``src/`` byte moved; the §4 KILL-the-design arm does NOT fire.
2. X3 and X4 ride separate trial variants of the read arm: production's
   post-trip stop-latch (``stop = monitor.cause is not None``) means a
   tripping trial lands nothing after the trip (D2-e declined measuring
   through it), so one trial cannot carry both X3 (needs the trailing
   settle's drain) and X4 (needs the trip). Cells: completing read cells
   (X1/X2/X3), armed read cells (X1/X2/X4 + the counted-unlanded X3
   disclosure), capture cells (X1/X2 + counted-unlanded X3; X4 structurally
   absent — the cut ends the body outcome_unknown before any crossing can
   trip), the completing control (X1/X2/X3), two worker-leg trials — the
   ~30-composed-run scale §8's own budget names. X4's clause-2 control band
   ("<= 1 s control") is NOT RELIABLY MEASURABLE at n=5 here (the fold's
   MEDIUM-1 correction of this docstring's earlier "structurally
   unmeasurable"): the self-anchored crossing needs a blackout longer than
   DELTA, and DELTA must exceed the ~50 ms tick rhythm, so the 20 ms
   control dispatch can only contain an anchor on tick-phase alignment —
   observed possible but rare (~8% of trials, phase luck); five trials do
   not reliably produce one. Disclosed, not worked around (scripting the
   onset would be the harness omniscience §2.2 rejects).
3. DELTA_MS stays 100 as designed on the 200 ms arms; the anchor-in-window
   property (§6 risk 5) is asserted only where the arm's arithmetic makes
   it hold (the armed read arm). No armed control cell exists (deviation 2).

Disclosed band notes: the capture cells' X2 floor is asserted only as
``>= 0.0`` — vacuous by design pending an owner floor (the capture arm's
cut makes the same dispatch-scale arithmetic that drives the read bands
inapplicable at a 50 ms budget); flagged for the owner row table.

Import discipline: ``test_run_activation as activation`` (the
``test_capture_run``/``test_issue146_e2e`` precedent) and the light rig's
rule module ``_continuity_rule`` (the #172 sibling shape). The light rig
module itself is imported only for the check-3 shape test's verbatim reuse.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from statistics import median
from typing import Any

import pytest
import test_cross_instance_continuity as continuity
import test_run_activation as activation
from _continuity_rule import Arm, TrialRecord, classify, write_trial_log

from benchweave.content.capture_services import CaptureServicesBundle
from benchweave.content.store import ContentStore
from benchweave.control.binding import resolve_binding
from benchweave.control.clocking import SystemClock
from benchweave.control.executor import Executor
from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.types import OperationRequest, OperationStatus, OperationVerb
from benchweave.interfaces.app import _build_run_factory
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.worker import RunWorker
from benchweave.registry.activation import activate
from benchweave.registry.admission import (
    AdmissionLimits,
    Admitted,
    Approval,
    admit,
)
from benchweave.registry.resolver import LocalDirectorySource, OriginConfig, Resolver
from benchweave.registry.schemas import load_lock_document
from benchweave.standards.manifest import load_manifest
from benchweave.state.store import Store
from benchweave.vendoring import contract_family

REPO = Path(__file__).resolve().parents[2]
EXECUTION_FIXTURES = REPO / "fixtures" / "execution"
REGISTRY_FIXTURES = REPO / "fixtures" / "registry"

#: The active execution corpus (the capture-step-admitting 0.2.0 head).
ACTIVE_CORPUS = contract_family("execution/0.2.0")

BENCH_ID = "composed-rig"
DEVICE_A = "supply-a"
DEVICE_B = "meter-b"
SIG_A = "sig-comp-a-temp"
SIG_B = "sig-comp-b-level"
CONDITION_ID = "comp-b-level-bounds"

DEV_ID = activation.DEV_ID
ORIGIN_MAIN = activation.ORIGIN_MAIN
NOW_NS = activation.NOW_NS
NOW_ISO = activation.NOW_ISO
QUOTA_LIMITS = dict(activation.QUOTA_LIMITS)
POLICY_ID = "composed-policy"
PROCEDURE_ID = "composed-procedure"

T_ACQ_MIN_MS = 200.0
CAPTURE_BUDGET_MS = 50.0
CONTROL_MS = 20.0
POLL_MS = 50
FRAME_PERIOD_MS = 50.0
MAX_AGE_MS = 500
#: (Deviation 4) The design's fixture scale said 300 (1.5x the light rig's
#: ALIGNED dispatch). The composed path cannot pre-align — the executor
#: owns timing — so the post-dispatch age runs dispatch + last-poll
#: residue = 200 + (slice + frame) ~ 270-380 ms and a 300 bound trips
#: signal_invalid on jitter, the exact failure #172's margin analysis
#: exists to prevent (its own 250 was raised to 300 for the same reason).
#: 500 keeps signal_invalid out of the measured arms for reasons that are
#: not the hazard. A rig parameter, never a commissioned G2 (A02).
DELTA_MS = 100.0

SAFE_LEVEL = 1.0
CROSS_LEVEL = 5.0

_LEDGER: list[TrialRecord] = []

_COMMAND_TEMPLATE = (
    "uv run pytest tests/integration/test_d2_composed_continuity.py -k {node}"
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

# --- the two adapter plugin sources (loaded through the real bundle loader) -------
#
# Each source is a module string the publisher ships; the bundle loader
# re-executes it per bridge construction per harness; module knobs are set
# by the trial AFTER construction (the _loaded_module idiom, F5).

ADAPTER_A_SOURCE = '''\
"""Synthetic paced supply adapter (D2 composed rig, device A)."""
from __future__ import annotations

import asyncio
import time

RIG_SUPPLY_ADAPTER = True

NATURAL_MS = 200.0
CHUNKS = 100
CHUNK_MS = 2.0


class RigSupplyAdapter:
    """The dispatching instance: fast signal reads, a paced acquisition
    parameter, and the chunk-paced capture with artifact traffic (natural
    ~200 ms against the arm's 50 ms budget). Every dispatch records a
    (verb, started, ended) monotonic span plus a verb count."""

    def __init__(self) -> None:
        self.services = None
        self.descriptor = None
        self.dispatches = []
        self.dispatch_spans = []
        self.captures = []

    async def open(self, descriptor, services, context) -> None:
        self.descriptor = descriptor
        self.services = services

    async def close(self, context) -> None:
        pass
    async def _pace(self, total_ms):
        deadline = self.services.monotonic() + total_ms / 1000.0
        while True:
            remaining = deadline - self.services.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 0.01))

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

    async def execute(self, request, context):
        started = time.monotonic()
        try:
            return await self._execute(request, context)
        finally:
            self.dispatch_spans.append(
                (
                    request["verb"],
                    started,
                    time.monotonic(),
                    request.get("arguments", {}).get("parameter"),
                )
            )
    async def _execute(self, request, context):
        verb = request["verb"]
        arguments = request["arguments"]
        operation_id = request["operation_id"]
        self.dispatches.append(verb)
        if verb == "read":
            parameter = arguments["parameter"]
            if parameter == "acq_scalar":
                await self._pace(NATURAL_MS)
                value = 4.0
            elif parameter == "temp":
                value = 23.5
            else:
                value = 0.0
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": self._reading(
                    parameter, value, "Cel" if parameter == "temp" else "V"
                ),
            }
        if verb == "capture":
            capture_id = arguments["capture_id"]
            self.captures.append(capture_id)
            for _ in range(CHUNKS):
                if context.is_cancelled():
                    break
                await self.services.artifact_append(capture_id, b"\\x01" * 8, context)
                await asyncio.sleep(CHUNK_MS / 1000.0)
            manifest = await self.services.artifact_finalise(
                capture_id,
                {
                    "format": arguments["format"],
                    "started_at": self.services.utc_now(),
                    "sample_interval_s": 0.001,
                    "unit": "V",
                },
                context,
            )
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": manifest,
            }
        return {
            "operation_id": operation_id,
            "verb": verb,
            "status": "error",
            "error": {
                "code": "UNSUPPORTED",
                "message": f"rig supply adapter does not implement {verb}",
                "dispatch_state": "not_dispatched",
            },
        }


def create_plugin():
    return RigSupplyAdapter()
'''


ADAPTER_B_SOURCE = '''\
"""Synthetic meter adapter (B) — D2 composed rig, device B."""
from __future__ import annotations

import time
from datetime import UTC, datetime

RIG_METER_ADAPTER = True

BUFFERED = True
ARM_CROSSING = False
DELTA_MS = 100.0
SAFE_LEVEL = 1.0
CROSS_LEVEL = 5.0
# Frame period = the poll cadence (50 ms): the poll engine delivers at
# most ONE frame per 50 ms slice (poll_round polls each live subscription
# exactly once), so any period below the cadence accumulates an unbounded
# backlog (the light rig drained it with bypass machinery; the composed
# path cannot) and the newest-point age climbs without bound. At period
# = cadence there is no backlog; peak ages stay ~dispatch + residue.
FRAME_PERIOD_MS = 50.0
OVERRIDE_VALUE = 0.0
class RigMeterAdapter:
    """The non-dispatching instance: the buffered/unbuffered classes (the
    live BUFFERED knob), the frame schedule with the in-event emission
    stamp, the self-anchored crossing model, and the safe-action write that
    zeroes the served model. The crossing instant is recorded at the first
    crossed serve as the previous read plus DELTA (§2.4's onset), exposed
    for post-run read-back."""

    def __init__(self) -> None:
        self.services = None
        self.dispatches = []
        self.dispatch_spans = []
        self.subscribe_mono_ns = None
        self.delivered = 0
        self.last_read_ns = None
        self.onset_ns = None
        self.onset_prev_read_ns = None
        self.write_landed_ns = None
        self._override_ns = None
        self._ref_mono_ns = 0
        self._ref_epoch = 0.0

    async def open(self, descriptor, services, context) -> None:
        self.services = services
        stamp = datetime.fromisoformat(services.utc_now().replace("Z", "+00:00"))
        self._ref_epoch = stamp.timestamp() - 0.001
        self._ref_mono_ns = int(self.services.monotonic() * 1e9)

    async def close(self, context) -> None:
        pass
    def _mono_ns(self):
        return int(self.services.monotonic() * 1e9)

    def _wall_at(self, mono_ns):
        epoch = self._ref_epoch + (mono_ns - self._ref_mono_ns) / 1e9
        return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z")

    def _value_at(self, mono_ns):
        if self._override_ns is not None and mono_ns >= self._override_ns:
            return OVERRIDE_VALUE
        if ARM_CROSSING and self.onset_ns is not None and mono_ns >= self.onset_ns:
            return CROSS_LEVEL
        return SAFE_LEVEL

    def _reading(self, value, mono_ns, age_ms):
        return {
            "parameter": "level",
            "value": value,
            "unit": "V",
            "observed_at": self._wall_at(mono_ns),
            "age_ms": age_ms,
            "quality": "valid",
            "source": "device",
        }
    async def execute(self, request, context):
        started = time.monotonic()
        try:
            return await self._execute_inner(request, context)
        finally:
            self.dispatch_spans.append((request["verb"], started, time.monotonic()))

    async def _execute_inner(self, request, context):
        verb = request["verb"]
        arguments = request["arguments"]
        operation_id = request["operation_id"]
        self.dispatches.append(verb)
        if verb == "read":
            now = self._mono_ns()
            prev = self.last_read_ns
            if prev is None:
                prev = now
            onset_pending = (
                ARM_CROSSING
                and self.onset_ns is None
                and now - prev >= int(DELTA_MS * 1e6)
            )
            if BUFFERED:
                if self.delivered == 0:
                    if self.subscribe_mono_ns is None:
                        # No frames can exist before the first poll: the
                        # device serves a fresh conversion until polling
                        # begins (the open-stamp fallback would age past
                        # the dispatch-scale bound across the composed
                        # path's factory-to-run gap and trip the fail-safe
                        # on fixture arithmetic, not the hazard).
                        point = now
                    else:
                        point = self.subscribe_mono_ns
                else:
                    point = self.subscribe_mono_ns + self.delivered * int(
                        FRAME_PERIOD_MS * 1e6
                    )
                age = int((now - point) / 1_000_000)
                if self._override_ns is not None and self._override_ns > point:
                    point = self._override_ns
                stamps = point
            else:
                point = now
                age = 0
                stamps = now
            if onset_pending:
                self.onset_ns = prev + int(DELTA_MS * 1e6)
                self.onset_prev_read_ns = prev
                value = CROSS_LEVEL
            else:
                value = self._value_at(point)
            self.last_read_ns = now
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": self._reading(value, stamps, age),
            }
        if verb == "write":
            now = self._mono_ns()
            self._override_ns = now
            self.write_landed_ns = now
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {
                    "parameter": arguments["parameter"],
                    "requested_value": arguments["value"],
                    "effective_value": arguments["value"],
                    "assurance": "dispatched",
                },
            }
        if verb == "stream_subscribe":
            self.subscribe_mono_ns = self._mono_ns()
            self.delivered = 0
            self._override_ns = None
            self.onset_ns = None
            self.onset_prev_read_ns = None
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {"subscription_id": arguments["subscription_id"]},
            }
        if verb == "stream_unsubscribe":
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {"subscription_id": arguments["subscription_id"]},
            }
        raise ValueError(f"unsupported verb {verb!r}")
    async def next_event(self, subscription_id, context):
        if self.subscribe_mono_ns is None:
            return None
        due = (
            int(
                (self._mono_ns() - self.subscribe_mono_ns)
                / (FRAME_PERIOD_MS * 1e6)
            )
            - self.delivered
        )
        if due <= 0:
            return None
        self.delivered += 1
        emit_ns = self.subscribe_mono_ns + self.delivered * int(FRAME_PERIOD_MS * 1e6)
        event = {
            "subscription_id": subscription_id,
            "sequence": self.delivered - 1,
            "kind": "telemetry",
            "reading": self._reading(self._value_at(emit_ns), emit_ns, 0),
        }
        event["x-rig-emit-ns"] = emit_ns
        return event


def create_plugin():
    return RigMeterAdapter()
'''

def _load_fixture_descriptor() -> dict[str, Any]:
    """The committed sim-psu descriptor, cloned to both rig shapes."""
    descriptor: dict[str, Any] = json.loads(
        (EXECUTION_FIXTURES / "descriptor-sim-psu.json").read_text()
    )
    return descriptor


def _write_descriptor(tmp_path: Path, name: str, descriptor: dict[str, Any]) -> Path:
    path = tmp_path / f"descriptor-{name}.json"
    path.write_text(json.dumps(descriptor, indent=2) + "\n")
    return path

def _descriptor_a() -> dict[str, Any]:
    """Device A: staged capture writer + the temp parameter."""
    descriptor = _load_fixture_descriptor()
    descriptor["id"] = "dev.benchweave.sim-supply-a"
    adapter = descriptor["integration"]["adapter"]
    adapter["entry_point"] = "benchweave_sim_psu.plugin:create_plugin"
    adapter["permissions"] = ["scoped_transport", "artifact_writer"]
    descriptor["capture_formats"] = ["waveform_f64le", "raw_binary"]
    descriptor["capture_limits"] = {"max_samples": 1024, "max_bytes": 65536}
    voltage = next(
        p for p in descriptor["parameters"] if p["name"] == "output_voltage_v"
    )
    for name in ("temp", "acq_scalar"):
        clone = json.loads(json.dumps(voltage))
        clone["name"] = name
        clone["description"] = f"synthetic {name}"
        descriptor["parameters"].append(clone)
    return descriptor

def _descriptor_b() -> dict[str, Any]:
    """Device B: event sink, stream floor 10 ms, the level parameter."""
    descriptor = _load_fixture_descriptor()
    descriptor["id"] = "dev.benchweave.sim-meter-b"
    adapter = descriptor["integration"]["adapter"]
    adapter["entry_point"] = "benchweave_sim_controller.plugin:create_plugin"
    # artifact_writer rides along so the adapter receives the eight-member
    # capture bundle (the light rig's B carried a capture bundle it never
    # used) — the dataset wrap slices the bundle by these permissions.
    adapter["permissions"] = ["scoped_transport", "event_sink", "artifact_writer"]
    descriptor["stream_limits"] = {"min_interval_ms": 10, "max_subscriptions": 4}
    setpoint = next(
        p for p in descriptor["parameters"] if p["name"] == "voltage_setpoint_v"
    )
    clone = json.loads(json.dumps(setpoint))
    clone["name"] = "level"
    clone["description"] = "synthetic level"
    descriptor["parameters"].append(clone)
    return descriptor

def _steps_for(arm: str) -> list[dict[str, Any]]:
    """The arms' step lists (§2.3)."""
    if arm == "capture":
        return [
            {"id": "settle-a", "kind": "delay", "duration_ms": 200},
            {
                "id": "grab",
                "kind": "capture",
                "role": "supply",
                "format": "waveform_f64le",
                "sample_count": 100,
                "max_bytes": 1024,
                "timeout_ms": 50,
            },
            {"id": "settle-b", "kind": "delay", "duration_ms": 300},
            {
                "id": "observe",
                "kind": "read",
                "role": "meter",
                "parameter": "level",
                "timeout_ms": 500,
            },
        ]

    if arm in ("read", "control", "short_t", "armed"):
        timeout_ms = 20 if arm == "short_t" else 250
        return [
            {"id": "settle-a", "kind": "delay", "duration_ms": 200},
            {
                "id": "acq",
                "kind": "read",
                "role": "supply",
                "parameter": "acq_scalar",
                "timeout_ms": timeout_ms,
            },
            {"id": "settle-b", "kind": "delay", "duration_ms": 200},
            {
                "id": "observe",
                "kind": "read",
                "role": "meter",
                "parameter": "level",
                "timeout_ms": 500,
            },
        ]
    raise ValueError(f"unknown arm {arm!r}")


def _procedure_doc(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "contract_version": "0.2.0",
        "id": PROCEDURE_ID,
        "version": "0.1.0",
        "description": "Synthetic composed-rig procedure. Not hardware-qualified.",
        "mode": "gateway_owned",
        "safety_policy": {"id": POLICY_ID, "version": "0.1.0"},
        "roles": [
            {"id": "supply", "required_profiles": ["otdp.dc_psu/1.0.0"], "channels": ["output"]},
            {"id": "meter", "required_profiles": ["otdp.dc_psu/1.0.0"], "channels": ["output"]},
        ],
        "max_body_ms": 12000,
        "max_protection_ms": 2000,
        "steps": steps,
    }

def _policy_doc() -> dict[str, Any]:
    """The rig's policy: the capture allow rule (format-keyed), B's
    safe-action write rule, the one continuous condition on sig-comp-b-level,
    and the approved safe transition."""
    return {
        "contract_version": "0.2.0",
        "id": POLICY_ID,
        "version": "0.1.0",
        "description": "Synthetic composed-rig policy. Not hardware-qualified.",
        "domains": [
            {
                "id": "dut",
                "max_abs_voltage_v": 6,
                "max_abs_current_a": 1,
                "max_power_w": 3,
                "max_stored_energy_j": 0.01,
                "max_energised_ms": 20000,
            }
        ],
        "allow_rules": [
            {
                "device_id": DEVICE_A,
                "kind": "capture",
                "format": "waveform_f64le",
                "capture_constraints": {
                    "type": "object",
                    "properties": {
                        "sample_count": {"maximum": 1024},
                        "max_bytes": {"maximum": 65536},
                    },
                },
            },

            {
                "device_id": DEVICE_B,
                "kind": "write",
                "parameter": "level",
                "value_constraints": {"type": "number", "minimum": 0, "maximum": 5.5},
            },
        ],
        "continuous_conditions": [
            {
                "id": CONDITION_ID,
                "kind": "numeric",
                "signal": SIG_B,
                "unit": "V",
                "minimum": -0.1,
                "maximum": 4.5,
            }
        ],
        "independent_protection": {
            "required": False,
            "assessment": {
                "id": "composed-protection-assessment",
                "version": "0.1.0",
                "sha256": "0" * 64,
            },
            "mechanism_ids": [],
        },
        "safe_transition": {
            "max_duration_ms": 2000,
            "actions": [
                {
                    "id": "level-zero",
                    "device_id": DEVICE_B,
                    "kind": "write",
                    "parameter": "level",
                    "value": 0.0,
                    "timeout_ms": 500,
                }
            ],

            "verify": [
                {
                    "id": "level-safe",
                    "kind": "numeric",
                    "signal": SIG_B,
                    "unit": "V",
                    "minimum": -0.1,
                    "maximum": 4.5,
                }
            ],
            "stable_for_ms": 100,
        },
    }

def _bench_doc(
    descriptor_paths: tuple[Path, Path], lattice_dir: Path, *, poll_ms: int
) -> dict[str, Any]:
    """The two-device bench: both devices pin their descriptor by digest and
    declare the activated generation; the two signals source A's temp and
    B's level; one resource joins both devices (one controlling procedure,
    A03)."""
    descriptor_a = json.loads(descriptor_paths[0].read_text())
    descriptor_b = json.loads(descriptor_paths[1].read_text())
    bench: dict[str, Any] = {
        "contract_version": "0.2.0",
        "id": BENCH_ID,
        "version": "0.1.0",
        "description": "Synthetic composed-rig bench. Not hardware-qualified.",
        "gateway_id": "composed-gateway",
        "fixture": {
            "id": "composed-fixture",
            "revision": "1",
            "identity_record_id": "ident-composed",
        },
        "dut_class": "low_voltage_embedded",
        "policy": {"id": POLICY_ID, "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "commissioning_id": "composed-commissioning",
        "dut_ids": [DEVICE_A, DEVICE_B],
        "protection_mechanisms": [],
        "devices": [
            {
                "id": DEVICE_A,
                "generation": 2,
                "descriptor": {
                    "id": descriptor_a["id"],
                    "version": descriptor_a["descriptor_version"],
                },
                "identity_record_id": "ident-psu",
                "connection_key": "sim_psu_local",
                "channels": ["ch1"],
            },

            {
                "id": DEVICE_B,
                "generation": 2,
                "descriptor": {
                    "id": descriptor_b["id"],
                    "version": descriptor_b["descriptor_version"],
                },
                "identity_record_id": "ident-meter",
                "connection_key": "sim_meter_local",
                "channels": ["ch1"],
            },
        ],
        "resources": [
            {"id": "dut-net", "device_ids": [DEVICE_A, DEVICE_B], "depends_on": []}
        ],

        "terminals": [
            {
                "id": "psu-out",
                "owner_kind": "device",
                "owner_id": DEVICE_A,
                "channel_id": "ch1",
                "name": "out",
                "domain_id": "dut",
            },
            {
                "id": "psu-in",
                "owner_kind": "device",
                "owner_id": DEVICE_A,
                "channel_id": "ch1",
                "name": "in",
                "domain_id": "dut",
            },
            {
                "id": "meter-out",
                "owner_kind": "device",
                "owner_id": DEVICE_B,
                "channel_id": "ch1",
                "name": "out",
                "domain_id": "dut",
            },

            {
                "id": "meter-in",
                "owner_kind": "device",
                "owner_id": DEVICE_B,
                "channel_id": "ch1",
                "name": "in",
                "domain_id": "dut",
            },
        ],
        "nets": [{"id": "n1", "terminal_ids": ["psu-out", "psu-in", "meter-out", "meter-in"]}],
        "signals": [
            {
                "id": SIG_A,
                "quantity": "temperature",
                "unit": "Cel",
                "poll_ms": poll_ms,
                "max_age_ms": MAX_AGE_MS,
                "absolute_error": 0.05,
                "resource_id": "dut-net",
                "source": {
                    "kind": "parameter",
                    "device_id": DEVICE_A,
                    "parameter": "temp",
                },
            },

            {
                "id": SIG_B,
                "quantity": "voltage",
                "unit": "V",
                "poll_ms": poll_ms,
                "max_age_ms": MAX_AGE_MS,
                "absolute_error": 0.05,
                "resource_id": "dut-net",
                "source": {
                    "kind": "parameter",
                    "device_id": DEVICE_B,
                    "parameter": "level",
                },
            },
        ],
    }
    bench["policy"]["sha256"] = _sha((lattice_dir / "safety-policy.json").read_bytes())
    bench["package_lock"]["sha256"] = _sha(
        (EXECUTION_FIXTURES / "package-lock.json").read_bytes()
    )
    for device, path in zip(bench["devices"], descriptor_paths, strict=True):
        device["descriptor"]["sha256"] = _sha(path.read_bytes())
    return bench

def _commissioning_doc(lattice_dir: Path) -> dict[str, Any]:
    """The commissioning: unattended grant (both evidence rows) + pins."""
    return {
        "contract_version": "0.2.0",
        "id": "composed-commissioning",
        "version": "0.1.0",
        "description": "Synthetic composed-rig commissioning. Not hardware-qualified.",
        "bench": {"id": BENCH_ID, "version": "0.1.0"},
        "policy": {"id": POLICY_ID, "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "procedure_refs": [{"id": PROCEDURE_ID, "version": "0.1.0"}],
        "dut_class": "low_voltage_embedded",
        "modes": ["supervised", "unattended"],

        "owners": {
            "bench": "composed-harness-owner",
            "test_safety": "composed-harness-owner",
            "system": "composed-harness-owner",
        },
        "approved_by": "composed-harness-owner",
        "approved_at": "2026-09-11T00:00:00Z",
        "expires_at": "2030-01-01T00:00:00Z",
        "offline_status_max_age_ms": 86400000,
        "scheduling_overhead_ms": 100,
        "evidence": [
            {
                "category": "envelope",
                "report": {
                    "id": "composed-envelope-report",
                    "version": "0.1.0",
                    "sha256": "0" * 64,
                },
                "tested_at": "2026-09-11T00:00:00Z",
                "scope": "Simulator envelope over the synthetic composed rig.",
                "result": "passed",
                "limitations": ["simulator-only"],
            },

            {
                "category": "unattended",
                "report": {
                    "id": "composed-unattended-report",
                    "version": "0.1.0",
                    "sha256": "0" * 64,
                },
                "tested_at": "2026-09-11T00:00:00Z",
                "scope": "Simulator unattended endurance over the composed rig.",
                "result": "passed",
                "limitations": ["simulator-only"],
            },
        ],
    }

def _binding_doc(request_id: str) -> dict[str, Any]:
    return {
        "contract_version": "0.2.0",
        "request_id": request_id,
        "procedure": {"id": PROCEDURE_ID, "version": "0.1.0"},
        "bench": {"id": BENCH_ID, "version": "0.1.0"},
        "policy": {"id": POLICY_ID, "version": "0.1.0"},
        "package_lock": {"id": "sim-lock", "version": "0.1.0"},
        "commissioning": {"id": "composed-commissioning", "version": "0.1.0"},
        "bindings": [
            {
                "role": "supply",
                "device_id": DEVICE_A,
                "channels": {"output": "ch1"},
            },
            {
                "role": "meter",
                "device_id": DEVICE_B,
                "channels": {"output": "ch1"},
            },
        ],
    }

def _lattice(
    tmp_path: Path, request_id: str, *, arm: str, poll_ms: int = POLL_MS
) -> Path:
    """Author the composed-rig lattice (docs in tmp_path, the harness
    pattern — no fixture-lattice change)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    descriptor_paths = (
        _write_descriptor(tmp_path, "sim-supply-a", _descriptor_a()),
        _write_descriptor(tmp_path, "sim-meter-b", _descriptor_b()),
    )
    procedure_path = tmp_path / "procedure-composed.json"
    procedure_path.write_text(
        json.dumps(_procedure_doc(_steps_for(arm)), indent=2) + "\n"
    )
    policy_path = tmp_path / "safety-policy.json"
    policy_path.write_text(json.dumps(_policy_doc(), indent=2) + "\n")
    lock_path = tmp_path / "package-lock.json"
    lock_path.write_bytes((EXECUTION_FIXTURES / "package-lock.json").read_bytes())
    bench = _bench_doc(descriptor_paths, tmp_path, poll_ms=poll_ms)
    bench_path = tmp_path / "bench.json"
    bench_path.write_text(json.dumps(bench, indent=2) + "\n")

    commissioning = _commissioning_doc(tmp_path)
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
    binding = _binding_doc(request_id)
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

def _write_rig_plugin_source(tmp_path: Path, dirname: str, source: str) -> Path:
    """One rig plugin dir in the publisher's expected layout (the
    ``_write_plugin_source`` precedent): the adapter source at
    ``<dirname>/src/benchweave_<dirname>/plugin.py`` plus the two OTDP
    class-contract files the descriptor's ``contracts`` pins resolve
    against the verified inventory at load (#146)."""
    root = tmp_path / "plugins" / dirname / "src" / f"benchweave_{dirname}"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "plugin.py").write_text(source)
    active = next(
        entry.version
        for entry in load_manifest(REPO).standards
        if entry.id == "otdp"
    )
    for name in ("device-profile-catalog.json", "otdp-measurement.schema.json"):
        (root / name).write_bytes(
            (REPO / "standards" / "otdp" / active / name).read_bytes()
        )
    return tmp_path / "plugins" / dirname


def _loaded_module(adapter: Any, marker: str) -> Any:
    """The loaded rig adapter module THAT ADAPTER INSTANCE runs under.

    The bundle loader re-executes the module string per bridge construction
    under a unique name, so sys.modules accumulates stale instances across
    trials — a marker scan returns the WRONG (stale) module and the trial's
    knob settings land on a module no live adapter reads (observed: the
    control's 20 ms knob dispatching a 200 ms read). The authoritative
    resolution is the adapter's own class module."""
    import sys

    module = sys.modules.get(type(adapter).__module__)
    assert module is not None, "the adapter's module is not importable"
    assert getattr(module, marker, False), (
        f"adapter module does not carry the {marker!r} marker"
    )
    return module

def _merge_locks(lock_a: bytes, lock_b: bytes) -> bytes:
    """The merged session lock (deviation 1): union of packages and roots.

    The lock document's schema is validated through the registry's own
    ``load_lock_document`` — hand-merged bytes that the schema refuses die
    here, loudly, at harness construction.
    """
    a = json.loads(lock_a)
    b = json.loads(lock_b)
    b_keys = {
        (str(r["registry_id"]), str(r["package_id"])) for r in b["packages"]
    }
    merged = dict(b)
    merged["packages"] = list(b["packages"]) + [
        r for r in a["packages"] if (str(r["registry_id"]), str(r["package_id"])) not in b_keys
    ]

    merged["roots"] = list(b["roots"]) + [
        r
        for r in a["roots"]
        if (str(r["registry_id"]), str(r["package_id"])) not in b_keys
    ]
    raw = json.dumps(merged, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    load_lock_document(raw, _sha(raw), max_bytes=1_000_000)
    return raw

class _ComposedRigHarness:
    """The two-package lattice through the real registry stack (deviation 1
    in the module docstring: merged lock + one activate)."""

    def __init__(
        self,
        tmp_path: Path,
        request_id: str,
        *,
        arm: str = "read",
        poll_ms: int = POLL_MS,
    ) -> None:
        self.root = tmp_path
        self.arm = arm
        self.lattice_dir = _lattice(
            tmp_path / "lattice", request_id, arm=arm, poll_ms=poll_ms
        )
        plugin_a = _write_rig_plugin_source(
            tmp_path / "pluginroot", "sim_psu", ADAPTER_A_SOURCE
        )
        plugin_b = _write_rig_plugin_source(
            tmp_path / "pluginroot", "sim_controller", ADAPTER_B_SOURCE
        )
        descriptor_a_path = self.lattice_dir / "descriptor-sim-supply-a.json"
        descriptor_b_path = self.lattice_dir / "descriptor-sim-meter-b.json"
        registry_root = tmp_path / "dev-registry"
        activation._publish(plugin_a, descriptor_a_path, registry_root)
        activation._publish(plugin_b, descriptor_b_path, registry_root)
        dev_root = activation._keyed_dev_origin(registry_root)

        origins = {
            DEV_ID: OriginConfig(
                registry_id=DEV_ID,
                root=dev_root,
                source=LocalDirectorySource(registry_root / DEV_ID),
                namespaces=("dev",),
            ),
            ORIGIN_MAIN: OriginConfig(
                registry_id=ORIGIN_MAIN,
                root=activation._main_root(),
                source=LocalDirectorySource(REGISTRY_FIXTURES / ORIGIN_MAIN),
                namespaces=("benchweave",),
            ),
        }
        self.work = tmp_path / "registry-work"
        from benchweave.interfaces.bootstrap import RegistrySession

        self.session = RegistrySession(
            resolver=Resolver(origins),
            roots={DEV_ID: dev_root, ORIGIN_MAIN: activation._main_root()},
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

        lock_path = self.session.lock_path
        closure_a = self.session.resolver.resolve(
            DEV_ID,
            "dev/sim_psu",
            "1.0.0",
            now_ns=NOW_NS,
            high_water=self.session.high_water,
        )
        admitted_a = admit(
            closure_a,
            cache_root=self.session.cache_root,
            lock_path=lock_path,
            limits=self.session.limits,
            approval=Approval(
                principal_id="composed-harness",
                approved_at=NOW_ISO,
                policy_id="local-policy",
                policy_version="1.0.0",
            ),
            now_ns=NOW_NS,
            roots={DEV_ID: dev_root, ORIGIN_MAIN: activation._main_root()},
            high_water=self.session.high_water,
        )
        lock_a = lock_path.read_bytes()

        closure_b = self.session.resolver.resolve(
            DEV_ID,
            "dev/sim_controller",
            "1.0.0",
            now_ns=NOW_NS,
            # A fresh high-water view: the resolver's fence is strictly
            # increasing within ONE map, so the shared origin-main profile
            # dependency's second consult at the same sequence would refuse
            # stale_sequence — the persisted water (merged at admission)
            # carries the idempotent-replay semantics that actually govern
            # the second closure (admission.py's _gate_lifecycle allows
            # replaying the same sequence).
            high_water={},
        )
        admitted_b = admit(
            closure_b,
            cache_root=self.session.cache_root,
            lock_path=lock_path,
            limits=self.session.limits,
            approval=Approval(
                principal_id="composed-harness",
                approved_at=NOW_ISO,
                policy_id="local-policy",
                policy_version="1.0.0",
            ),
            now_ns=NOW_NS,
            roots={DEV_ID: dev_root, ORIGIN_MAIN: activation._main_root()},
            high_water=self.session.high_water,
        )
        lock_b = lock_path.read_bytes()
        merged = _merge_locks(lock_a, lock_b)
        lock_path.write_bytes(merged)
        admitted = Admitted(
            lock_path=lock_path,
            lock_sha256=_sha(merged),
            manifest_sha256s=(
                admitted_a.manifest_sha256s + admitted_b.manifest_sha256s
            ),
        )

        activate(
            admitted,
            bench_generation=1,
            bench_has_live_lease=False,
            records_dir=self.session.records_dir / BENCH_ID,
            activated_at=NOW_ISO,
        )
        # The merged-lock record now exists at activation-2.json; both
        # devices declare generation 2 and resolve their own closures.

    def open_store(self) -> tuple[Store, ContentStore]:
        store = Store.open(self.root / "state.db")
        content = ContentStore(store)
        admit_startup_bench(
            store, content, self.lattice_dir, now=NOW_ISO, contracts=ACTIVE_CORPUS
        )
        return store, content

    def build_run(self) -> Callable[..., Any]:
        return _build_run_factory(
            self.lattice_dir,
            SystemClock().now_iso,
            limits=QUOTA_LIMITS,
            registry_session=self.session,
            contracts=ACTIVE_CORPUS,
        )

    def _coordinator(self, run_id: str) -> tuple[Any, Store]:
        store, _content = self.open_store()
        try:
            factory = self.build_run()
            coordinator = factory(run_id, "principal-composed", self.binding_ref(), store)
            return coordinator, store
        except BaseException:
            store.close()
            raise

    def binding_ref(self) -> dict[str, str]:
        raw = (self.lattice_dir / "run-binding.json").read_bytes()
        return {
            "id": json.loads(raw)["request_id"],
            "version": "0.1.0",
            "sha256": _sha(raw),
        }

class _RigRecorder:
    """The axis seams attached to a factory-built coordinator pre-start."""

    def __init__(self) -> None:
        self.tick_times: list[float] = []
        self.snapshots: list[tuple[int, dict[str, Any]]] = []
        self.events: list[tuple[float, dict[str, Any]]] = []
        self.retention_rows: int = 0

    def on_tick(self, stamp: float) -> None:
        self.tick_times.append(stamp)

    def on_retain(self, snapshot: dict[str, Any]) -> None:
        self.snapshots.append((time.monotonic_ns(), dict(snapshot)))

    def on_event(self, subscription_id: str, event: dict[str, Any], receipt: str) -> None:
        del subscription_id
        del receipt
        self.events.append((time.monotonic(), dict(event)))

def _attach_axes(seam_host: Any, recorder: _RigRecorder) -> None:
    """Attach the three measurement seams pre-start (the F5 idiom). The
    design's §1 cited the monitor's ``retain``; the monitor materializes
    only inside start_run, so the pre-start attach point is the
    coordinator's CONSTRUCTOR-supplied retain hook
    (``_RetainingCoordinator._retain``) — the same callable, intercepted
    one frame earlier; production retention continues through the wrapper,
    so the store-row cross-check can prove it ran."""
    seam_host.stream_host.tick_recorder = recorder.on_tick
    seam_host.stream_host.on_event = recorder.on_event
    original_retain = seam_host._retain

    def retaining_wrapper(snapshot: dict[str, Any]) -> str:
        recorder.on_retain(snapshot)
        retained: str = original_retain(snapshot)
        return retained

    seam_host._retain = retaining_wrapper

def _run_axis_trial(
    tmp_path: Path,
    *,
    node: str,
    arm: str,
    device_class: str,
    trial_index: int,
    worker: bool = False,
) -> dict[str, Any]:
    """One fresh-harness trial: the measured dispatch through the composed
    path, the four axes with their seams, and the §2.7 discriminators."""
    arm_variant = "armed" if arm == "armed_read" else arm
    harness = _ComposedRigHarness(
        tmp_path / f"trial-{node}-{trial_index}",
        f"req-{node}-{trial_index}",
        arm=arm_variant,
    )
    module_a = None
    module_b = None
    store, _content = harness.open_store()
    try:
        factory = harness.build_run()
        run_id = f"run-{node}-{trial_index}"
        recorder = _RigRecorder()
        coordinator = factory(run_id, "principal-composed", harness.binding_ref(), store)
        module_a = _loaded_module(
            coordinator.plugins[DEVICE_A]._adapter, "RIG_SUPPLY_ADAPTER"
        )
        module_b = _loaded_module(
            coordinator.plugins[DEVICE_B]._adapter, "RIG_METER_ADAPTER"
        )
        module_a.NATURAL_MS = CONTROL_MS if arm == "control" else T_ACQ_MIN_MS
        module_b.BUFFERED = device_class == "buffered"
        module_b.ARM_CROSSING = arm in ("armed_read",)
        _attach_axes(coordinator, recorder)

        record = coordinator.start_run(run_id, "principal-composed")
        axis_outcome = _compute_axes(
            recorder, coordinator, store, run_id, harness, arm
        )
        axis_outcome["record"] = record
        axis_outcome["coordinator"] = coordinator
        axis_outcome["run_id"] = run_id
        axis_outcome["recorder"] = recorder
        axis_outcome["harness"] = harness
        axis_outcome["module_b"] = module_b
        axis_outcome["store"] = store
        return axis_outcome
    except BaseException:
        store.close()
        raise

def _compute_axes(
    recorder: _RigRecorder,
    coordinator: Any,
    store: Store,
    run_id: str,
    harness: _ComposedRigHarness,
    arm: str,
) -> dict[str, Any]:
    """The four axes from the seams, plus the §2.7 discriminator facts."""
    adapter_a = coordinator.plugins[DEVICE_A]._adapter
    adapter_b = coordinator.plugins[DEVICE_B]._adapter
    dispatch_span = _measured_dispatch_span(adapter_a, arm)
    dispatch_start_s, dispatch_end_s = dispatch_span
    x1 = _worst_tick_gap(recorder.tick_times)
    x2 = _post_dispatch_snapshot_age(recorder.snapshots, dispatch_end_s)
    in_window, landed, unlanded = _x3_frames(
        recorder.events, adapter_b, dispatch_start_s, dispatch_end_s
    )
    x3 = max(landed) if landed else None
    onset = adapter_b.onset_ns
    write_landed = adapter_b.write_landed_ns
    x4 = None
    if onset is not None and write_landed is not None:
        x4 = (write_landed - onset) / 1e6

    events = store.read_events(f"run:{run_id}")
    kinds = [event["kind"] for event in events]
    terminal = store.get_run(run_id)
    terminal_record = terminal["terminal"] if terminal is not None else None
    observation_ns = None
    observation_ms = None
    if x4 is not None:
        window_end_s = dispatch_end_s
        after = [t for t in recorder.tick_times if t > window_end_s]
        observation_ns = int(after[0] * 1e9) if after else None
        observation_ms = (
            (observation_ns - onset) / 1e6 if observation_ns is not None else None
        )
    return {
        "arm": arm,
        "x1_ms": x1,
        "x2_ms": x2,
        "x3_ms": x3,
        "x3_unlanded_count": unlanded,
        "x3_in_window": in_window,
        "x4_ms": x4,
        "onset_ns": onset,
        "write_landed_ns": write_landed,
        "observation_ns": observation_ns,
        "observation_ms": observation_ms,
        "dispatch_span_s": dispatch_span,
        "events": events,
        "kinds": kinds,
        "terminal_record": terminal_record,
        "adapter_a": adapter_a,
        "adapter_b": adapter_b,
    }

def _measured_dispatch_span(adapter_a: Any, arm: str) -> tuple[float, float]:
    """A's measured dispatch span for the trial's arm, from its recorded
    spans: the body's acquisition is the ``acq_scalar`` read span (the
    monitor's temp reads carry their own parameter); the capture arm's is
    the capture span."""
    if arm == "capture":
        spans = [s for s in adapter_a.dispatch_spans if s[0] == "capture"]
        assert spans, "no capture span recorded"
        span = spans[0]
        return (span[1], span[2])
    read_spans = [
        s
        for s in adapter_a.dispatch_spans
        if s[0] == "read" and s[3] == "acq_scalar"
    ]
    assert read_spans, f"no paced read span recorded: {adapter_a.dispatch_spans}"
    span = read_spans[0]
    return (span[1], span[2])

def _worst_tick_gap(tick_times: list[float]) -> float:
    assert len(tick_times) >= 2, "not enough ticks to measure a gap"
    return max(
        (b - a for a, b in zip(tick_times, tick_times[1:], strict=False)),
        default=0.0,
    ) * 1000.0


def _post_dispatch_snapshot_age(
    snapshots: list[tuple[int, dict[str, Any]]], dispatch_end_s: float
) -> float:
    """X2: sig-comp-b-level's envelope in the FIRST post-dispatch retained
    snapshot (the wall-domain age the monitor computed)."""
    window_ns = dispatch_end_s * 1e9
    for ts, snapshot in snapshots:
        if ts > window_ns:
            envelope = snapshot[SIG_B]
            return float(envelope.age_ms)
    raise AssertionError(
        f"no post-dispatch snapshot retained ({len(snapshots)} snapshots)"
    )

def _x3_frames(
    recorder_events: list[tuple[float, dict[str, Any]]],
    adapter_b: Any,
    dispatch_start_s: float,
    dispatch_end_s: float,
) -> tuple[int, list[float], int]:
    """X3's in-window frames: frames whose schedule emission fell inside
    the dispatch window, from B's own frame schedule. A frame landing
    DURING the window is a blackout violation (asserted); the latency set
    is the frames that landed after the window (the trailing drain);
    frames with no landing at all are the counted-and-disclosed unlanded
    set (A06: never laundered into the landed set)."""
    if adapter_b.subscribe_mono_ns is None:
        return (0, [], 0)
    landed_by_emit: dict[int, float] = {}
    for landing_s, event in recorder_events:
        emit_ns = event.get("x-rig-emit-ns")
        if isinstance(emit_ns, int):
            landed_by_emit.setdefault(emit_ns, landing_s)
    period_ns = int(FRAME_PERIOD_MS * 1e6)
    subscribe_ns = adapter_b.subscribe_mono_ns
    in_window = 0
    landed: list[float] = []
    unlanded = 0

    # Frames EXIST by the emission schedule whether or not a poll ever
    # delivered them — the capture arm's in-window frames are exactly the
    # never-delivered ones the disclosure exists to count (A06). The
    # schedule is the adapter's own grid, so the bound is the window's
    # end, not the delivered count.
    scheduled = int((dispatch_end_s * 1e9 - subscribe_ns) // period_ns) + 1
    for k in range(1, max(scheduled, adapter_b.delivered) + 1):
        emit_ns = subscribe_ns + k * period_ns
        emit_s = emit_ns / 1e9
        if not (dispatch_start_s < emit_s < dispatch_end_s):
            continue
        in_window += 1
        if emit_ns in landed_by_emit:
            landing_s = landed_by_emit[emit_ns]
            if landing_s < dispatch_end_s:
                raise AssertionError(
                    "a frame landed DURING the dispatch — the blackout did not hold"
                )
            landed.append((landing_s - emit_s) * 1000.0)
        else:
            unlanded += 1
    return (in_window, landed, unlanded)

def _assert_discriminators(outcome: dict[str, Any], *, arm: str, run_id: str) -> None:
    """The §2.7 anti-shortcut battery, every axis trial:
    1. factory-built _RetainingCoordinator, both devices real OTDPBridges
       over the eight-member bundle (asserted at trial setup);
    2. the executor-minted id in the run's event log;
    3. the terminal record with the arm's honest outcome;
    4. production retention rows exist (the X2 cross-check's store half)."""
    record = outcome["record"]
    store: Store = outcome["store"]
    coordinator: Any = outcome["coordinator"]
    events = outcome["events"]
    if arm == "capture":
        minted = f"cap:{run_id}:grab"
        body = record["body_outcome"]
        assert record["outcome"] == "outcome_unknown"

    body = record["body_outcome"]
    if arm == "capture":
        assert body != "completed"
        capture_event = next(
            (e for e in events if e["kind"] == "capture"), None
        )
        assert capture_event is not None, "no capture step event landed"
        assert capture_event["operation_id"] == minted, (
            "the capture event must carry the executor-minted id"
        )
        assert capture_event["dispatch_state"] == "unknown"
        entry = coordinator.occurrence_ledger[(run_id, "grab", ())]
        issued = entry["issued_ids"]["capture_id"]
        assert issued["id"] == minted
    elif arm in ("read", "armed_read", "control"):
        assert record["outcome"] in ("passed", "tripped")

        read_events = [
            e
            for e in events
            if e["kind"] == "read"
            and e.get("operation_id") == f"op:{run_id}:acq"
        ]
        assert read_events, "the body's read step event carries no minted id"
        if arm == "armed_read":
            assert body == "tripped"
            assert any(CONDITION_ID in r for r in record["reasons"])
            assert not any("signal_invalid" in r for r in record["reasons"])
        elif arm == "control":
            assert record["outcome"] == "passed"
        else:
            assert record["outcome"] == "passed"
    else:
        assert record["outcome"] == "outcome_unknown"
        assert body != "completed"
    terminal_record = outcome["terminal_record"]
    assert terminal_record is not None, "no terminal record"
    assert terminal_record["outcome"] == record["outcome"]

    evidence_rows = store.connection.execute(
        "SELECT COUNT(*) FROM evidence WHERE context_key = ? AND kind = ?",
        (f"run:{run_id}", "dataset"),
    ).fetchone()[0]
    monitor = getattr(coordinator, "monitor", None)
    retained = len(monitor.snapshot_evidence) if monitor is not None else 0
    assert evidence_rows > 0, "production retention rows absent"
    assert retained == evidence_rows, (
        f"retention cross-check: {retained} snapshots vs {evidence_rows} rows"
    )
    # §6 risk 3's kill arm, per trial: a quota collision lands in
    # retention_failures (the A07 shape) - it must never be silent.
    assert monitor is None or monitor.retention_failures == 0, (
        f"retention_failures {monitor.retention_failures} on {run_id}"
    )

def _ledger_record(
    outcome: dict[str, Any], *, node: str, device_class: str, trial_index: int
) -> TrialRecord:
    """The trial's ``TrialRecord`` (§2.8) with full parameterization."""
    arm = outcome["arm"]
    axes: dict[str, float] = {"X1": outcome["x1_ms"], "X2": outcome["x2_ms"]}
    if outcome["x3_ms"] is not None:
        axes["X3"] = outcome["x3_ms"]
    if outcome["x4_ms"] is not None:
        axes["X4"] = outcome["x4_ms"]
    # The light convention: the T_acq arms' rows carry the CONJUNCTIVE
    # consistency-control fact (both §2.5 controls asserted by the
    # dedicated short-T and replay tests), so D5's FIRE arm stays
    # reachable; the control arm is exempt by construction. Fold B-F4:
    # the hardcoded False left every ledger with zero t_acq rows.
    t_acq = arm in ("read", "armed_read")
    return TrialRecord(
        trial=trial_index,
        arm=f"composed-{arm}",
        device_class=device_class,
        axes_ms=axes,
        t_acq_controls=t_acq,
        tightening_admitted=False,
        splitting_admitted=False,
        unsplittable_class=True,
        parameterization={
            "dispatch_ms": T_ACQ_MIN_MS if arm in ("read", "armed_read") else (
                CAPTURE_BUDGET_MS if arm == "capture" else CONTROL_MS
            ),
            "poll_ms": POLL_MS,
            "frame_ms": FRAME_PERIOD_MS,
            "max_age_ms": MAX_AGE_MS,
            "arm_shape": arm,
            "worker_leg": False,
            "x3_in_window": outcome["x3_in_window"],
            "x3_unlanded": outcome["x3_unlanded_count"],
            # The 3-way X4 decomposition (fold MEDIUM-3): a future re-cut
            # re-derives the legs without re-measuring.
            **(
                {
                    "x4_onset_obs_ms": outcome["observation_ms"],
                    "x4_obs_action_ms": outcome["x4_ms"] - outcome["observation_ms"],
                }
                if outcome["x4_ms"] is not None
                and outcome["observation_ms"] is not None
                else {}
            ),
        },
        command=_COMMAND_TEMPLATE.format(node=node),
    )

def _run_worker_trial(
    tmp_path: Path, *, node: str, arm: str, device_class: str
) -> dict[str, Any]:
    """One worker-leg trial (§2.6): the run through RunWorker.submit → the
    worker thread's thread-affine re-open → start_run, seams attached to
    the coordinator the factory returns inside the worker's drain (the rig
    wraps ONLY the callable the worker already receives)."""
    harness = _ComposedRigHarness(
        tmp_path / f"trial-{node}", f"req-{node}", arm=arm
    )
    store, content = harness.open_store()
    try:
        factory = harness.build_run()
        run_id = f"run-{node}"
        recorder = _RigRecorder()
        captured: dict[str, Any] = {}

        def wrapped_build_run(
            rid: str, principal: str, binding: dict[str, Any], wstore: Store
        ) -> Any:
            coordinator = factory(rid, principal, binding, wstore)
            captured["coordinator"] = coordinator
            supply = _loaded_module(
                coordinator.plugins[DEVICE_A]._adapter, "RIG_SUPPLY_ADAPTER"
            )
            meter = _loaded_module(
                coordinator.plugins[DEVICE_B]._adapter, "RIG_METER_ADAPTER"
            )
            supply.NATURAL_MS = CONTROL_MS if arm == "control" else T_ACQ_MIN_MS

            meter.BUFFERED = device_class == "buffered"
            meter.ARM_CROSSING = arm == "armed_read"
            _attach_axes(coordinator, recorder)
            return coordinator

        worker = RunWorker(store, content, build_run=wrapped_build_run, limits=QUOTA_LIMITS)
        worker.start()
        try:
            worker.submit(run_id, "principal-composed", harness.binding_ref(), BENCH_ID)
            drained = worker.join(timeout=120.0)
            assert drained, "the worker leg never drained in bounds"
        finally:
            worker.stop()
            stopped = worker.join(timeout=10.0)
            assert stopped, "the worker never stopped in bounds"
        axis_outcome = _compute_axes(
            recorder, captured["coordinator"], store, run_id, harness, arm
        )
        record = axis_outcome["terminal_record"]
        axis_outcome["record"] = {
            "outcome": record["outcome"],
            "body_outcome": record.get("body_outcome"),
            "reasons": record.get("reasons"),
        }

        axis_outcome["run_id"] = run_id
        axis_outcome["recorder"] = recorder
        axis_outcome["coordinator"] = captured["coordinator"]
        axis_outcome["worker"] = True
        axis_outcome["store"] = store
        return axis_outcome
    except BaseException:
        store.close()
        raise

def _measure_cell(
    tmp_path: Path,
    *,
    node: str,
    arm: str,
    device_class: str,
    count: int = 5,
) -> list[TrialRecord]:
    """One (arm x class) cell: `count` fresh-harness trials, per-trial §2.7
    discriminators, per-cell trimmed range gates (the #172 §5 item-7
    machinery: trimmed of the single most extreme trial, range <= 25% of
    the 200 ms dispatch), trial log written."""
    records: list[TrialRecord] = []
    for index in range(count):
        outcome = _run_axis_trial(
            tmp_path,
            node=node,
            arm=arm,
            device_class=device_class,
            trial_index=index,
        )
        _assert_discriminators(outcome, arm=arm, run_id=outcome["run_id"])
        store: Store = outcome["store"]
        store.close()
        records.append(
            _ledger_record(outcome, node=node, device_class=device_class, trial_index=index)
        )
        _LEDGER.append(records[-1])
    write_trial_log(tmp_path / f"trial-log-{node}.json", records)
    for axis in ("X1", "X2", "X3", "X4"):
        subset = [r for r in records if axis in r.axes_ms]
        if subset:
            # Gate every axis that recorded, subsets included - an axis
            # missing from some trials (X3's window-hit subset) is gated on
            # its subset, never skipped.
            gate = _trimmed_range_gate(subset, axis)
            assert gate <= 0.25, (
                f"{node} {axis} trimmed range {gate * 200.0:.1f} ms past the "
                "25%-of-dispatch gate"
            )
    print(
        f"[{node}] "
        + " ".join(
            f"X{axis}={median([r.axes_ms[axis] for r in records if axis in r.axes_ms]):.1f}ms"
            for axis in ("X1", "X2", "X3", "X4")
            if any(axis in r.axes_ms for r in records)
        )
    )
    return records

def _trimmed_range_gate(records: list[TrialRecord], axis: str) -> float:
    """The range-gate statistic (#172 §5 item 7), on the LIGHT RIG'S OWN
    machinery (imported, not copied — the design's "imported machinery"):
    the axis's trial range trimmed of the single most extreme trial (the
    one furthest from the median), as a fraction of the 200 ms dispatch
    scale (<= 0.25 passes). Fewer than three values is a LOUD refusal, not
    a vacuous pass — a gate that cannot measure must not wave the cell
    through."""
    values = [r.axes_ms[axis] for r in records if axis in r.axes_ms]
    if len(values) < 3:
        raise AssertionError(
            f"range gate on {axis}: {len(values)} value(s) — too few to gate"
        )
    return continuity._underpowered_range_ms(values) / 200.0

pytestmark = [pytest.mark.timing]


def test_composed_two_device_lattice_commissions_both_real_bridges(
    tmp_path: Path,
) -> None:
    """§2.2's smoke — the KILL-arm check: the two-package lattice
    commissions BOTH devices as real bridges through the harness sequence
    (two publishes, two resolves, two admits, the merged lock, one
    activate), and the factory-built coordinator's plugins are real
    OTDPBridge instances over the eight-member CaptureServicesBundle with
    both registrations on the stream host."""
    harness = _ComposedRigHarness(tmp_path, "req-smoke", arm="read")
    coordinator, store = harness._coordinator("run-smoke")
    try:
        from benchweave.interfaces.app import _RetainingCoordinator

        assert isinstance(coordinator, _RetainingCoordinator)
        bridge_a = coordinator.plugins[DEVICE_A]
        bridge_b = coordinator.plugins[DEVICE_B]
        assert isinstance(bridge_a, OTDPBridge)
        assert isinstance(bridge_b, OTDPBridge)

        for bridge in (bridge_a, bridge_b):
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
        stream_host = coordinator.stream_host
        assert stream_host is not None
        assert DEVICE_B in stream_host.devices
        assert DEVICE_A in stream_host.bridges
        assert DEVICE_B in stream_host.bridges
    finally:
        store.close()

def test_capture_cells_measure_with_discriminators(tmp_path: Path) -> None:
    """The capture-arm cells (the cut shape): five buffered + five
    unbuffered trials, all four §2.7 discriminators per trial, X1 <= 350 ms
    (the lower bound vacuous by arithmetic — disclosed), X2 recorded, and
    X3 riding as the counted-unlanded disclosure (A06, no laundering)."""
    for device_class in ("buffered", "unbuffered"):
        records = _measure_cell(
            tmp_path,
            node=f"capture-{device_class}",
            arm="capture",
            device_class=device_class,
        )
        for record in records:
            assert record.axes_ms["X1"] <= 350.0
            assert record.axes_ms["X2"] >= 0.0
            assert record.parameterization["x3_in_window"] >= 1, (
                "no in-window frames for the X3 disclosure"
            )

def test_read_cells_measure_all_drain_axes(tmp_path: Path) -> None:
    """The completing read-arm cells: five buffered + five unbuffered
    trials — X1 in the dispatch blackout band [150, 350] ms, X3's latency
    set complete (the trailing settle drains through the engine's own
    slices), and the class agreement input: buffered X2 (dispatch-scale
    ages) vs unbuffered X2 (host skew, < 50 ms)."""
    long_records: list[TrialRecord] = []
    for device_class in ("buffered", "unbuffered"):
        records = _measure_cell(
            tmp_path,
            node=f"read-{device_class}",
            arm="read",
            device_class=device_class,
        )
        for record in records:
            assert 150.0 <= record.axes_ms["X1"] <= 350.0
            # The completing arm drains at most ~4 deliveries per settle
            # (each poll_round's tick reads cost a slice's budget, capping
            # effective deliveries), so the LAST one or two in-window
            # emissions can ride past teardown when the queue depth
            # exceeds the drain - delivery ends at unsubscribe, no bypass
            # (D2-e). Counted and disclosed (A06), never laundered into
            # the landed set; the latency set is over landed frames only.
            assert record.parameterization["x3_unlanded"] <= 2, (
                f"x3 unlanded {record.parameterization['x3_unlanded']}"
            )
            assert record.parameterization["x3_in_window"] >= 1
        long_records.extend(records)
    buffered_x2 = median(
        [r.axes_ms["X2"] for r in long_records if r.device_class == "buffered"]
    )
    unbuffered_x2 = median(
        [r.axes_ms["X2"] for r in long_records if r.device_class == "unbuffered"]
    )
    assert buffered_x2 >= 150.0, f"buffered X2 median {buffered_x2:.1f} ms"
    assert unbuffered_x2 < 50.0, f"unbuffered X2 median {unbuffered_x2:.1f} ms"

def test_armed_cells_measure_protective_latency(tmp_path: Path) -> None:
    """The crossing-armed read cells: five buffered + five unbuffered
    trials — the body trips with the CONDITION's reason (never
    signal_invalid, the R14 + freshness discipline), the self-anchored
    onset lands inside A's recorded dispatch span (§6 risk 5), and X4's
    decomposition (onset -> observation -> write-start -> write-end) is
    recorded in every trial-log row (fold B-F3/MEDIUM-3).

    The acceptance band binds the CELL MEDIAN over ALL TEN trials, never a
    single trial (fold HIGH-1): one X4 reading is not the cell's — the
    pre-committed rule consumes medians, and a band checked on the last
    loop variable accepts on one trial of ten. The trial log is written
    inside the loop so a mid-run failure still leaves the measured rows.
    """
    records: list[TrialRecord] = []
    for device_class in ("buffered", "unbuffered"):
        class_records: list[TrialRecord] = []
        for index in range(5):
            outcome = _run_axis_trial(
                tmp_path,
                node=f"armed-{device_class}-{index}",
                arm="armed_read",
                device_class=device_class,
                trial_index=index,
            )
            _assert_discriminators(
                outcome, arm="armed_read", run_id=outcome["run_id"]
            )
            outcome["store"].close()
            onset_ns = outcome["onset_ns"]
            assert onset_ns is not None, "the crossing never fired"
            dispatch_start_ns = int(outcome["dispatch_span_s"][0] * 1e9)
            dispatch_end_ns = int(outcome["dispatch_span_s"][1] * 1e9)
            assert dispatch_start_ns <= onset_ns <= dispatch_end_ns, (
                "the anchor fell outside A's recorded dispatch span"
            )
            assert outcome["x4_ms"] is not None
            observation = outcome["observation_ns"]
            write_landed = outcome["write_landed_ns"]
            assert observation is not None and write_landed is not None
            record = _ledger_record(
                outcome,
                node=f"armed-{device_class}-{index}",
                device_class=device_class,
                trial_index=index,
            )
            _LEDGER.append(record)
            class_records.append(record)
            records.append(record)
        write_trial_log(
            tmp_path / f"trial-log-armed-{device_class}.json", class_records
        )
        gate = _trimmed_range_gate(class_records, "X4")
        assert gate <= 0.25, (
            f"armed {device_class} X4 trimmed range {gate * 200.0:.1f} ms "
            "past the 25%-of-dispatch gate"
        )
        print(
            f"[armed-{device_class}] X4="
            f"{median([r.axes_ms['X4'] for r in class_records]):.1f}ms (n=5)"
        )
    assert len(records) == 10, f"the armed ledger holds {len(records)} of 10"
    # The clause-2 floor (150) encoded the LIGHT rig's scripted-early
    # onset (20-40 ms into the dispatch); the self-anchored onset sits at
    # prev-read + DELTA = ~100 ms into the 200 ms dispatch, so X4 =
    # (dispatch - DELTA) + observation-to-action by arithmetic. The floor
    # moves to that anchor arithmetic; the decomposition is the headline.
    x4_values = [r.axes_ms["X4"] for r in records]
    x4_median = median(x4_values)
    assert x4_median >= 90.0, (
        f"armed-cell X4 median {x4_median:.1f} ms below the band "
        f"({len(x4_values)} trials)"
    )
    print(f"[armed-all] X4 median {x4_median:.1f} ms over {len(records)} trials")

def test_control_cell_separates_from_the_long_arm(tmp_path: Path) -> None:
    """The matched short-dispatch control (5 trials) against the long arm:
    control X2 <= 150 ms (anchor arithmetic, deviation 6), X1 <= 350 ms,
    and the long-vs-control separation DIRECTION holds (the clause-2
    KILL-defect detector: long ~ control is a wiring defect to fix,
    explicitly not row-1 evidence)."""
    control_records = _measure_cell(
        tmp_path, node="control", arm="control", device_class="buffered"
    )
    for record in control_records:
        assert record.axes_ms["X1"] <= 350.0
    # The clause-2 control bands encoded the LIGHT rig's ALIGNED control
    # (a fresh frame at dispatch start). The composed control cannot
    # pre-align — the executor owns timing — so its X2 floor by arithmetic
    # is dispatch + last-poll residue (20 + up to a slice + a frame period
    # ~ 70-120 ms). X3 records only when the 20 ms window catches a 50 ms
    # emission-grid point (~40% of trials): the completeness shortfall is
    # disclosed, the band asserted on the recorded subset.
    control_x2 = median([r.axes_ms["X2"] for r in control_records])
    assert control_x2 <= 150.0, f"control X2 median {control_x2:.1f} ms"
    x3_records = [r.axes_ms["X3"] for r in control_records if "X3" in r.axes_ms]
    if x3_records:
        control_x3 = median(x3_records)
        assert control_x3 <= 150.0, f"control X3 median {control_x3:.1f} ms"
        print(
            f"[control] X3 recorded on {len(x3_records)}/{len(control_records)} "
            f"trials (20 ms window vs 50 ms emission grid), median {control_x3:.1f} ms"
        )

def test_worker_legs_reach_the_same_discriminators(tmp_path: Path) -> None:
    """§2.6: at least one trial per arm through RunWorker.submit → the
    thread-affine re-open → start_run, the same §2.7 discriminators read
    from the store (the seams attach to the coordinator the wrapped
    build_run returns inside the drain)."""
    for arm in ("read", "capture"):
        outcome = _run_worker_trial(
            tmp_path,
            node=f"worker-{arm}",
            arm=arm,
            device_class="buffered",
        )
        _assert_discriminators(outcome, arm=arm, run_id=outcome["run_id"])
        outcome["store"].close()
        assert outcome["worker"] is True
        print(
            f"[worker-{arm}] outcome={outcome['record']['outcome']} "
            f"X1={outcome['x1_ms']:.1f}ms X2={outcome['x2_ms']:.1f}ms"
        )

def test_t_acq_short_budget_fails_the_acquisition(tmp_path: Path) -> None:
    """§2.5 control (i): the short-T read at a 20 ms budget against the
    natural 200 ms acquisition — the run records the honest UNKNOWN shape
    (body outcome_unknown, the step event's dispatch_state unknown,
    TIMEOUT-class), never a fabricated OK."""
    outcome = _run_axis_trial(
        tmp_path,
        node="short-t",
        arm="short_t",
        device_class="buffered",
        trial_index=0,
    )
    _assert_discriminators(
        outcome, arm="short_t", run_id=outcome["run_id"]
    )
    outcome["store"].close()
    acq_events = [
        e
        for e in outcome["events"]
        if e["kind"] == "read" and e.get("operation_id") == f"op:{outcome['run_id']}:acq"
    ]
    assert acq_events
    assert acq_events[0]["dispatch_state"] == "unknown"
    assert acq_events[0]["error_code"] == "TIMEOUT"

def test_capture_window_one_shot_through_the_replay_leg(tmp_path: Path) -> None:
    """§2.5 control (ii), the composed one-shot shape: after a composed
    capture run recorded the minted window, a replay body over the SAME
    occurrence ledger answers from the recorded results — zero new
    dispatches (the A-R4 replay idiom: the composed path's one-shot-ness
    is the replay suppression, the scalar/capture window unsplittable per
    the fixture)."""
    outcome = _run_axis_trial(
        tmp_path, node="replay", arm="capture", device_class="buffered", trial_index=0
    )
    coordinator: Any = outcome["coordinator"]
    store: Store = outcome["store"]
    adapter_a = outcome["adapter_a"]
    before = adapter_a.captures
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
        outcome["run_id"],
        SystemClock().now_ns() + 10_000_000_000,
    )
    # The replay reproduces the RECORDED results — the composed capture was
    # cut at its 50 ms budget, so the honest recorded shape is the
    # outcome_unknown the first dispatch left (A06: the replay never
    # upgrades uncertainty). The one-shot claim is the ZERO new dispatches.
    assert body.body_outcome == "outcome_unknown"
    assert adapter_a.captures == before, "the replay re-dispatched the window"
    store.close()

def test_red_arm_discriminator_refuses_bypassed_dispatch(tmp_path: Path) -> None:
    """The RED arm (§2.7): the same capture request driven DIRECTLY on the
    bridge (the light-rig shape — no run, no executor) must be REFUSED by
    every composed discriminator: no run event, no executor-minted id, no
    occurrence-ledger entry, no terminal record. A discriminator that
    passes both ways proves nothing — this arm pins that it discriminates."""
    harness = _ComposedRigHarness(tmp_path, "req-red", arm="capture")
    run_id = "run-red-direct"
    coordinator, store = harness._coordinator(run_id)
    try:
        request = OperationRequest(
            operation_id="op-red-direct",
            verb=OperationVerb.CAPTURE,
            arguments={
                "capture_id": "cap.rig-direct",
                "format": "waveform_f64le",
                "sample_count": 100,
                "max_bytes": 1024,
            },
        )

        deadline_ns = time.monotonic_ns() + 5_000_000_000
        result = coordinator.plugins[DEVICE_A].dispatch(request, deadline_ns=deadline_ns)
        assert result.status is OperationStatus.OK
        assert result.data["capture_id"] == "cap.rig-direct"
        # The key the coordinator actually namespaces: f"run:{run_id}"
        # Two key conventions, both load-bearing (fold HIGH-3 + row 8):
        # the EVENT STREAM is namespaced run:{run_id}, while the RUNS
        # TABLE keys on the BARE run id (store.get_run's WHERE run_id = ?)
        # - the f-string form reads an events context here, and the bare
        # form reads the runs table. Mixing them makes the no-events or
        # no-row half vacuous.
        events = store.read_events(f"run:{run_id}")
        assert not events, "a bypassed dispatch produced run events"
        assert coordinator.occurrence_ledger == {}, (
            "a bypassed dispatch reached the occurrence ledger"
        )
        run = store.get_run(run_id)
        assert run is None, "a bypassed dispatch created a run row"
    finally:
        store.close()

def test_structural_pair_during_a_composed_run(tmp_path: Path) -> None:
    """§2.5's structural pair on a DEDICATED trial (helper threads appear
    only here and in the worker leg — CTL-8): a helper thread dispatches
    reads to BOTH bridges for the run's duration; post-hoc selection
    against A's recorded dispatch span: reads on B's bridge land promptly
    throughout (the movable share), reads on A's bridge block for the
    remaining dispatch (§8 per-instance serialization — the bound
    share)."""
    harness = _ComposedRigHarness(tmp_path, "req-s8", arm="read")
    store, _content = harness.open_store()
    try:
        factory = harness.build_run()
        run_id = "run-s8"
        coordinator = factory(run_id, "principal-composed", harness.binding_ref(), store)
        supply = _loaded_module(
            coordinator.plugins[DEVICE_A]._adapter, "RIG_SUPPLY_ADAPTER"
        )
        meter = _loaded_module(
            coordinator.plugins[DEVICE_B]._adapter, "RIG_METER_ADAPTER"
        )
        supply.NATURAL_MS = T_ACQ_MIN_MS
        meter.BUFFERED = True
        meter.ARM_CROSSING = False
        _attach_axes(coordinator, _RigRecorder())

        spans: list[tuple[str, float, float, Any]] = []
        stop = threading.Event()
        # TWO independent helper threads (the light rig's §8 pair shape): a
        # single alternating loop would block ITSELF on A and starve the
        # movable share's evidence.
        spans_lock = threading.Lock()

        def helper_loop(device_id: str, parameter: str) -> None:
            bridge = coordinator.plugins[device_id]
            while not stop.is_set():
                # Paced: a tight helper loop starves the body's own slices
                # (the monitor's reads queue behind helper dispatches) and
                # the run trips the fail-safe on fixture contention - an
                # artifact, not the measured serialization.
                time.sleep(0.01)
                started = time.monotonic()
                result = bridge.dispatch(
                    OperationRequest.read("op-helper", parameter=parameter),
                    deadline_ns=time.monotonic_ns() + 2_000_000_000,
                )
                with spans_lock:
                    spans.append(
                        (device_id, started, time.monotonic(), result.status)
                    )

        helper_a = threading.Thread(target=helper_loop, args=(DEVICE_A, "temp"), daemon=True)
        helper_b = threading.Thread(target=helper_loop, args=(DEVICE_B, "level"), daemon=True)
        helper_a.start()
        helper_b.start()
        record = coordinator.start_run(run_id, "principal-composed")
        stop.set()
        helper_a.join(timeout=10.0)
        helper_b.join(timeout=10.0)
        assert record["outcome"] == "passed"
        adapter_a = coordinator.plugins[DEVICE_A]._adapter
        body_span = [
            s
            for s in adapter_a.dispatch_spans
            if s[0] == "read" and s[3] == "acq_scalar"
        ]
        assert body_span, "the body's paced read span never recorded"
        span_start, span_end = body_span[0][1], body_span[0][2]

        overlapping = [
            s
            for s in spans
            if s[1] < span_end and s[2] > span_start
        ]
        on_b = [s for s in overlapping if s[0] == DEVICE_B]
        # The bound share: ANY helper A-read overlapping the dispatch
        # window cannot complete inside it (the per-instance lock is held)
        # - whether it started just before or during the window. That
        # includes the read IN FLIGHT at window entry: blocked to the end.
        on_a_overlapping = [s for s in overlapping if s[0] == DEVICE_A]
        # The movable share: at least one B read FULLY INSIDE the dispatch
        # window (started and ended within it) - the B helper runs freely
        # during A's blackout.
        b_inside = [
            s for s in on_b if s[1] >= span_start and s[2] <= span_end
        ]
        assert b_inside and on_a_overlapping, (
            f"no in-window helper spans: {len(overlapping)} of {len(spans)}"
        )
        b_elapsed = [s[2] - s[1] for s in b_inside]
        assert max(b_elapsed) <= 0.1, f"B's reads blocked: {max(b_elapsed):.3f}s"
        for s in on_a_overlapping:
            # §8 per-instance serialization: an A-dispatch overlapping the
            # body's read cannot complete before the read ends.
            assert s[2] >= span_end - 0.005, (
                f"A's read completed mid-dispatch: elapsed {s[2] - s[1]:.3f}s"
            )
        print(
            f"[s8-pair] movable-share worst {max(b_elapsed)*1000:.0f} ms; "
            f"{len(on_a_overlapping)} bound-share read(s) all held to the dispatch end"
        )
    finally:
        store.close()

def test_store_connection_census_start_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """§4 clause 6 / §2.6: monkeypatch-counted Store.open across a full
    start_run trial — exactly one open, on the main thread (the two-instance
    composed baseline; no worker re-open)."""
    opened: list[int] = []
    original_open = Store.open

    def counting_open(path: Any, **kwargs: Any) -> Store:
        opened.append(threading.get_ident())
        return original_open(path, **kwargs)

    monkeypatch.setattr(Store, "open", staticmethod(counting_open))
    outcome = _run_axis_trial(
        tmp_path,
        node="census-run",
        arm="read",
        device_class="buffered",
        trial_index=0,
    )
    outcome["store"].close()
    # The census claims the Store.open facts (§2.6), not the run's
    # outcome - a load-sensitive staleness trip changes the outcome, not
    # the store topology. The trial must complete its lifecycle.
    assert outcome["terminal_record"] is not None
    assert opened, "no Store.open was counted"
    assert set(opened) == {threading.get_ident()}, (
        f"census: {len(opened)} opens on threads {opened}"
    )
    assert len(opened) == 1, f"census: {len(opened)} opens"

def test_store_connection_census_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """§4 clause 6 on the worker shape: exactly the two expected connections
    (main + the worker's thread-affine re-open), on two distinct threads."""
    opened: list[int] = []
    original_open = Store.open

    def counting_open(path: Any, **kwargs: Any) -> Store:
        opened.append(threading.get_ident())
        return original_open(path, **kwargs)

    monkeypatch.setattr(Store, "open", staticmethod(counting_open))
    outcome = _run_worker_trial(
        tmp_path,
        node="census-worker",
        arm="read",
        device_class="buffered",
    )
    outcome["store"].close()
    assert outcome["terminal_record"] is not None
    assert len(opened) == 2, f"census: {len(opened)} opens ({opened})"
    assert len(set(opened)) == 2, f"census: threads {opened}"

#: The light rig's re-measured cells ([R5]: PR #236 body, re-measured
#: post-fix) - the clause-3 class-agreement reference.
_LIGHT_CELLS_R5: dict[str, float] = {
    "X2-long-buffered": 219.0,
    "X2-control": 42.0,
    "X2-unbuffered": 1.0,
    "X3-long": 202.0,
    "X3-control": 32.0,
}


def _composed_cell_median(
    arm: str, device_class: str, axis: str, *, minimum: int = 3
) -> float | None:
    """The clause-3 consumer's cell median: the RECORD-count floor guards
    the producer having run; the AXIS subset is a different matter - X3
    records only when the dispatch window catches the emission grid, and
    the grid phase LOCKS per process (a session can measure 0/5 on the
    control where another measures 4/5). An empty axis subset is
    therefore session luck, not a missing producer: the caller gets None
    and skips with a disclosure - the fold's letter ("the MEASURED
    cells") is exactly this."""
    records = [
        r
        for r in _LEDGER
        if r.arm == arm and r.device_class == device_class
    ]
    assert len(records) >= minimum, (
        f"clause-3 cell {arm} x {device_class}: {len(records)} record(s) "
        f"- the producing cell test did not run"
    )
    values = [r.axes_ms[axis] for r in records if axis in r.axes_ms]
    if not values:
        return None
    return median(values)


def test_clause3_class_agreement_against_the_light_cells() -> None:
    """§4 clause 3 as an executable arm (fold HIGH-2/B-F1): every compared
    composed cell lies within the pre-committed ±100 ms class tolerance of
    the light rig's same-cell median [R5], and the long-vs-control
    separation direction matches. X4 is EXCLUDED from the cross-rig
    comparison with a disclosed rationale: the light rig's hazard onset
    was SCRIPTED at 10-40 ms into the dispatch (harness omniscience),
    while the composed onset is SELF-ANCHORED at prev-read + DELTA
    (~105-115 ms into the 200 ms window) - a mechanism change, not a
    scale change, so same-cell X4 numbers are not comparable; the
    composed X4 band (>= 90, anchor arithmetic) and its recorded
    decomposition are the X4 evidence instead."""
    assert _LEDGER, "no composed trials ran"
    x2_long = _composed_cell_median("composed-read", "buffered", "X2")
    x2_control = _composed_cell_median("composed-control", "buffered", "X2")
    x2_unbuffered = _composed_cell_median("composed-read", "unbuffered", "X2")
    # X2 always records (the envelope is the after-tick snapshot); only
    # X3's subset is phase-lucky. Narrow the structural cells.
    assert x2_long is not None and x2_control is not None
    assert x2_unbuffered is not None
    x3_long = _composed_cell_median("composed-read", "buffered", "X3")
    assert x3_long is not None, (
        "the long cell's X3 subset is empty - the 200 ms window at the "
        "50 ms grid always catches points; this session is degenerate"
    )
    # The control's X3 subset is session luck (the grid-phase lock, see
    # the helper): an empty subset skips the comparison with a disclosure
    # rather than red the battery on a phase coin.
    x3_control = _composed_cell_median("composed-control", "buffered", "X3", minimum=1)
    # Direction first (a wiring defect reads long ~ control). The X3
    # direction is asserted only when the control subset produced a
    # median this session.
    assert x2_long > x2_control, (
        f"X2 separation direction lost: long {x2_long:.1f} vs control "
        f"{x2_control:.1f}"
    )
    if x3_control is not None:
        assert x3_long > x3_control, (
            f"X3 separation direction lost: long {x3_long:.1f} vs control "
            f"{x3_control:.1f}"
        )
    comparisons = {
        "X2-long-buffered": (x2_long, _LIGHT_CELLS_R5["X2-long-buffered"]),
        "X2-control": (x2_control, _LIGHT_CELLS_R5["X2-control"]),
        "X2-unbuffered": (x2_unbuffered, _LIGHT_CELLS_R5["X2-unbuffered"]),
        "X3-long": (x3_long, _LIGHT_CELLS_R5["X3-long"]),
    }
    if x3_control is None:
        print(
            "[clause-3] X3-control: the control cell's X3 subset is empty "
            "this session (grid-phase lock, 0/5 window hits) - no median "
            "exists to compare; skipped with this disclosure"
        )
    else:
        comparisons["X3-control"] = (
            x3_control,
            _LIGHT_CELLS_R5["X3-control"],
        )
    for cell, (composed, light) in comparisons.items():
        delta = abs(composed - light)
        assert delta <= 100.0, (
            f"clause-3 tolerance exceeded on {cell}: composed "
            f"{composed:.1f} vs light {light:.1f} (delta {delta:.1f} ms) - "
            "the #172 record re-opens per its own risk table"
        )
        print(f"[clause-3] {cell}: composed {composed:.1f} vs light {light:.1f} ms")


def test_range_gate_double_spike_fails() -> None:
    """Fold B-F2, the table test: the gate trims ONE trial (the one
    furthest from the median - the light rig's exact machinery), never
    both ends, so a double-spiked cell [100, 210, 220, 230, 400] FAILS
    (both-ends trimming passes it at 20 ms; single-trim reads 130/200 =
    0.65)."""
    records = [
        TrialRecord(
            trial=i,
            arm="composed-read",
            device_class="buffered",
            axes_ms={"X1": value},
            t_acq_controls=False,
            tightening_admitted=False,
            splitting_admitted=False,
            unsplittable_class=True,
        )
        for i, value in enumerate([100.0, 210.0, 220.0, 230.0, 400.0])
    ]
    gate = _trimmed_range_gate(records, "X1")
    assert gate > 0.25, f"the double-spiked cell passed the gate at {gate:.3f}"


def test_get_run_reads_the_bare_run_id(tmp_path: Path) -> None:
    """Fold row 8, the permanent pin: the runs table keys on the BARE run
    id (store.get_run's WHERE run_id = ?) while the event stream is
    namespaced run:{run_id} - a real start_run-minted run is readable at
    the bare id, and the "run:"-prefixed form is structurally blind to it
    (the vacuous shape the RED arm briefly carried)."""
    outcome = _run_axis_trial(
        tmp_path,
        node="get-run-probe",
        arm="capture",
        device_class="buffered",
        trial_index=0,
    )
    store: Store = outcome["store"]
    run_id = outcome["run_id"]
    try:
        assert store.get_run(run_id) is not None, (
            "the runs table is not readable at the BARE run id - the "
            "real path writes run_id, not run:{run_id}"
        )
        assert store.get_run(f"run:{run_id}") is None, (
            "the run:-prefixed form FOUND a runs-table row - that form "
            "belongs to the event stream namespace only"
        )
    finally:
        store.close()


def test_ledger_classifier_consumption_underpowered(tmp_path: Path) -> None:
    """§4 clause 4: classify over the rig's real ledger with the §6
    all-None bounds returns UNDERPOWERED — the no-commissioning reading
    applies verbatim, no denominator invented (A02); and the check-3
    shape test is reused verbatim from the light rig (imported, not
    copied)."""
    assert _LEDGER, (
        "the composed ledger is empty - the classifier consumption would "
        "pass vacuously (fold B-F5/LOW-3)"
    )
    long_arm_rows = [
        r
        for r in _LEDGER
        if r.arm in ("composed-read", "composed-armed_read")
    ]
    assert any(r.t_acq_controls for r in long_arm_rows), (
        "the long arm carries zero t_acq=True rows - D5's FIRE arm is "
        "unreachable from this ledger (fold B-F4)"
    )
    verdict = classify(_LEDGER, {"X1": None, "X2": None, "X3": None, "X4": None})
    assert verdict is Arm.UNDERPOWERED
    by_cell: dict[tuple[str, str], list[TrialRecord]] = {}
    for record in _LEDGER:
        by_cell.setdefault((record.arm, record.device_class), []).append(record)
    for (arm, device_class), records in sorted(by_cell.items()):
        figures = ", ".join(
            f"{axis}={median([r.axes_ms[axis] for r in records if axis in r.axes_ms]):.1f}ms"
            for axis in ("X1", "X2", "X3", "X4")
            if any(axis in r.axes_ms for r in records)
        )
        print(f"[ledger] {arm} x {device_class} (n={len(records)}): {figures}")
    continuity.test_emit_trial_log_every_numeric_row_carries_command_and_parameterization()
