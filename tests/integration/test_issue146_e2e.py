"""Issue #146 slice 3 E2E: the dataset lane through the REAL activation path.

N = 30 procedure runs (§7's E2E measurement), each
``configure(invoke) → fetch(invoke, payload-backed dataset) → sample →
assert`` through app.py bridge construction — never a hand-built bridge —
plus the mutation battery (§7: 0 unrefused protocol lies) and the
disclosure measurements (publish+validate p50/p95; I5 first-use vs
steady-state, reported separately). Invented fixture names throughout.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path
from typing import Any

import pytest
from test_run_activation import (
    DEVICE_ID,
    QUOTA_LIMITS,
    _CommissionedHarness,
    _coordinator,
)

RUNS = 30

DATASET_ADAPTER_SOURCE = '''\
import struct


class DatasetSupplyAdapter:
    """An invoke-only supply adapter: configure echoes an effective
    configuration; measure stages a payload artifact, publishes the
    manifest through the dataset services, and returns the admitted
    dataset (invented fixture names throughout)."""

    def __init__(self):
        self.services = None
        self.published = []
        self.publish_timings_ms = []
        self.state = {"output_enabled": False, "voltage_setpoint_v": 0.0}

    async def open(self, descriptor, services, context):
        self.services = services

    async def close(self, context):
        return None

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
        if not self.state["output_enabled"]:
            return 0.0
        return float(self.state["voltage_setpoint_v"])

    async def execute(self, request, context):
        verb = request["verb"]
        if verb == "read":
            parameter = request["arguments"]["parameter"]
            if parameter == "output_voltage_v":
                value, unit = self._output_voltage(), "V"
            elif parameter == "output_current_a":
                value, unit = (0.1 if self.state["output_enabled"] else 0.0), "A"
            else:
                value, unit = 0.0, None
            return {
                "operation_id": request["operation_id"],
                "verb": verb,
                "status": "ok",
                "data": self._reading(parameter, value, unit),
            }
        if verb == "write":
            parameter = request["arguments"]["parameter"]
            value = request["arguments"]["value"]
            self.state[parameter] = value
            return {
                "operation_id": request["operation_id"],
                "verb": verb,
                "status": "ok",
                "data": {
                    "parameter": parameter,
                    "requested_value": value,
                    "effective_value": value,
                    "assurance": "readback",
                    "verification": self._reading(
                        parameter, value, "V" if parameter == "voltage_setpoint_v" else None
                    ),
                },
            }
        if verb != "invoke":
            return {
                "operation_id": request["operation_id"],
                "verb": verb,
                "status": "ok",
                "data": {
                    "manufacturer": "Example",
                    "model": "Supply",
                    "serial": None,
                    "firmware": None,
                    "source": "device",
                },
            }
        arguments = request["arguments"]
        action_id = arguments["action_id"]
        if action_id == "otdp.dc_psu.configure/1.0.0":
            configuration_id = arguments["input"]["configuration_id"]
            result = {
                "configuration_id": configuration_id,
                "effective_configuration": {
                    "configuration_id": configuration_id,
                    "channel": "ch1",
                    "voltage_v": arguments["input"].get("voltage_v", 5.0),
                    "current_limit_a": arguments["input"].get("current_limit_a", 1.0),
                    "ovp_v": arguments["input"].get("ovp_v", 6.0),
                    "ocp_a": arguments["input"].get("ocp_a", 1.0),
                },
            }
        elif action_id == "otdp.dc_psu.measure/1.0.0":
            result = await self._measure(arguments["input"], context)
        else:
            raise ValueError("unknown action " + action_id)
        return {
            "operation_id": request["operation_id"],
            "verb": "invoke",
            "status": "ok",
            "data": {"action_id": action_id, "result": result},
        }

    async def _measure(self, invoke_input, context):
        payload_id = await self.services.payload_create("f64le", 8, context)
        await self.services.payload_append(payload_id, struct.pack("<d", 5.0), context)
        record = await self.services.payload_finalise(payload_id, context)
        manifest = {
            "dataset_id": context.dataset_id,
            "kind": "scalar_set",
            "configuration_id": invoke_input["configuration_id"],
            "acquisition_id": None,
            "started_at": "2026-09-26T00:00:00Z",
            "clock": {
                "domain_id": "demo-clock",
                "timestamp_source": "device",
                "synchronisation": "unknown",
                "uncertainty_s": None,
            },
            "axes": [],
            "variables": [
                {
                    "id": "raw_samples",
                    "quantity": "voltage",
                    "unit": "V",
                    "channel_ids": ["ch1"],
                    "dtype": "float64",
                    "dimensions": [],
                    "artifact": dict(record),
                    "uncertainty": {"status": "unknown"},
                    "calibration": {"status": "unknown"},
                    "status": "valid",
                },
                {
                    "id": "voltage_v",
                    "quantity": "voltage",
                    "unit": "V",
                    "channel_ids": ["ch1"],
                    "dtype": "float64",
                    "dimensions": [],
                    "values": [5.0],
                    "uncertainty": {"status": "unknown"},
                    "calibration": {"status": "unknown"},
                    "status": "valid",
                },
            ],
            "trigger": {"source": "software", "time_relative_s": None},
            "status": "complete",
            "context": {},
        }
        import time as _time
        started = _time.perf_counter()
        admitted = await self.services.dataset_publish(manifest, context)
        self.publish_timings_ms.append((_time.perf_counter() - started) * 1000)
        self.published.append(admitted["dataset_id"])
        return admitted


def create_plugin():
    return DatasetSupplyAdapter()
'''

INVOKE_STEPS: list[dict[str, Any]] = [
    {
        "id": "configure",
        "kind": "invoke",
        "role": "supply",
        "action_id": "otdp.dc_psu.configure/1.0.0",
        "input": {
            "configuration_id": "conf-e2e",
            "channel": "ch1",
            "voltage_v": 5.0,
            "current_limit_a": 1.0,
            "ovp_v": 6.0,
            "ocp_a": 1.0,
        },
        "timeout_ms": 500,
    },
    {
        "id": "fetch",
        "kind": "invoke",
        "role": "supply",
        "action_id": "otdp.dc_psu.measure/1.0.0",
        "input": {"configuration_id": "conf-e2e", "channels": ["ch1"]},
        "timeout_ms": 500,
    },
    {
        "id": "assert-voltage",
        "kind": "sample",
        "source_step": "fetch",
        "variable_id": "voltage_v",
        "unit": "V",
        "max_age_ms": 86400000,  # the fixture started_at is fixed; a day of slack
        "require_known_uncertainty": False,  # the fixture declares unknown honestly
    },
    # The monitor-feeding tail LAST: terminal safety verifies on a fresh
    # reading (the invoke lane ahead of it would age the signal otherwise).
    {
        "id": "set-voltage",
        "kind": "write",
        "role": "supply",
        "parameter": "voltage_setpoint_v",
        "value": 5.0,
        "timeout_ms": 500,
    },
    {"id": "settle", "kind": "delay", "duration_ms": 200},
    {
        "id": "observe",
        "kind": "read",
        "role": "supply",
        "parameter": "output_voltage_v",
        "timeout_ms": 500,
    },
]

INVOKE_ALLOW_RULES: list[dict[str, Any]] = [
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
    {
        "device_id": DEVICE_ID,
        "kind": "invoke",
        "action_id": "otdp.dc_psu.configure/1.0.0",
        "input_constraints": {"type": "object"},
    },
    {
        "device_id": DEVICE_ID,
        "kind": "invoke",
        "action_id": "otdp.dc_psu.measure/1.0.0",
        "input_constraints": {"type": "object"},
    },
]


def _e2e_coordinator(
    harness: _CommissionedHarness, run_id: str, request_id: str
) -> tuple[Any, Any, Any]:
    """_coordinator's fresh-request shape: one lattice, many runs (the
    harness's binding_ref mints a fresh request id per run — duplicate
    suppression keys on it)."""
    from test_run_activation import QUOTA_LIMITS, _coordinator

    return _coordinator(harness, run_id, QUOTA_LIMITS, request_id=request_id)


def _e2e_harness(tmp_path: Path, source: str = DATASET_ADAPTER_SOURCE) -> _CommissionedHarness:
    return _CommissionedHarness(
        tmp_path,
        "req-146-e2e",
        streaming=False,
        adapter_source=source,
        steps=INVOKE_STEPS,
        allow_rules=INVOKE_ALLOW_RULES,
        extra_permissions=("artifact_writer",),  # the payload-backed fetch
    )


def _publish_evidence_rows(store: Any, run_id: str) -> int:
    """THIS run's publish evidence row — scoped by the run's ds: reference
    id, not kind: the kind-`dataset` dimension is shared with the monitor's
    per-tick retention (Amendment 1 LOW-3's disclosed competitor, live in
    this very harness — the run: rows), and the harness's store carries
    every run's rows (one state.db per harness)."""
    return int(
        store.connection.execute(
            "SELECT COUNT(*) FROM evidence WHERE kind = 'dataset'"
            " AND content_ref_json LIKE ?",
            (f'%ds:op:{run_id}:%',),
        ).fetchone()[0]
    )


def _published_artifacts(store: Any) -> int:
    return int(
        store.connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    )


def test_issue146_e2e_thirty_runs_through_the_real_activation_path(
    tmp_path: Path,
) -> None:
    """§7's E2E ship gate: N=30 runs terminal-complete, each with one
    admitted dataset (one evidence row, published artifacts) and a sample
    assertion resolving over the admitted scalar_set."""
    harness = _e2e_harness(tmp_path)
    publish_timings: list[float] = []
    first_use_ms: list[float] = []
    steady_ms: list[float] = []
    for index in range(RUNS):
        run_id = f"run-146-e2e-{index}"
        coordinator, store, content = _coordinator(
            harness, run_id, QUOTA_LIMITS, request_id=f"req-146-{run_id}"
        )
        try:
            bridge = coordinator.plugins[DEVICE_ID]
            adapter = bridge._adapter
            started = time.perf_counter()
            record = coordinator.start_run(run_id, "principal-activation")
            wall_ms = (time.perf_counter() - started) * 1000
            assert record["outcome"] == "passed", (index, record)
            assert record["body_outcome"] == "completed", (index, record)
            assert _publish_evidence_rows(store, run_id) == 1, index
            assert _published_artifacts(store) >= 2, index  # payload + manifest rows
            assert len(adapter.published) == 1 and adapter.published[0].startswith(
                "ds:op:"
            ), (index, adapter.published)
            # The sample assertion resolved: an invalid sample fails its
            # step (and the body), so outcome==passed already proves it —
# and the step's durable event carries the sample verdict.
            sample_events = store.connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_json LIKE"
                " '%assert-voltage%' AND event_json LIKE '%sample%'"
            ).fetchone()[0]
            assert sample_events >= 1, index
            publish_timings.extend(adapter.publish_timings_ms)
            if index == 0:
                first_use_ms.append(wall_ms)
            else:
                steady_ms.append(wall_ms)
        finally:
            store.close()
    # Disclosure measurements (§7: reported, no gate): whole-run wall time
    # first-use vs steady-state (the I5 constraints-validator compile and
    # the first-bridge warm path live in the first-use number).
    def pct(values: list[float], q: float) -> float:
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, int(q * len(ordered)))]

    print(
        f"\nE2E disclosure ({RUNS} runs, real activation path): "
        f"publish+validate p50 {pct(publish_timings, 0.5):.2f} ms, "
        f"p95 {pct(publish_timings, 0.95):.2f} ms "
        f"(n={len(publish_timings)}); whole-run first-use "
        f"{first_use_ms[0]:.1f} ms vs steady p50 {pct(steady_ms, 0.5):.1f} ms "
        f"/ p95 {pct(steady_ms, 0.95):.1f} ms (the I5 constraints-validator "
        "compile and first-bridge warm path live in the first-use number)"
    )
    assert len(steady_ms) == RUNS - 1
    _ = statistics  # reported above; keep the import honest


@pytest.mark.parametrize(
    "mode",
    [
        "unpublished-dataset",
        "divergent-republish",
        "wrong-dataset-id",
        "malformed-envelope",
    ],
)
def test_issue146_e2e_mutation_battery(tmp_path: Path, mode: str) -> None:
    """§7's battery: protocol lies through the REAL path are refused —
    the run fails loudly, nothing is admitted, no evidence row lands."""
    anchor = (
        "        import time as _time\n"
        "        started = _time.perf_counter()\n"
        "        admitted = await self.services.dataset_publish(manifest, context)\n"
        "        self.publish_timings_ms.append((_time.perf_counter() - started) * 1000)\n"
        "        self.published.append(admitted[\"dataset_id\"])\n"
        "        return admitted"
    )
    source = DATASET_ADAPTER_SOURCE.replace(anchor, _MUTATIONS[mode])
    del anchor
    assert source != DATASET_ADAPTER_SOURCE, mode
    harness = _e2e_harness(tmp_path, source)
    coordinator, store, content = _coordinator(harness, "run-146-mut", QUOTA_LIMITS)
    try:
        record = coordinator.start_run("run-146-mut", "principal-activation")
        assert record["outcome"] != "passed", (mode, record)
        # The PRE-publish lies (unpublished dataset, wrong id) admit
        # nothing; the POST-publish lies (divergent return, malformed
        # envelope) admit once — the dataset stands, the lie is the
        # returned result, and the bridge refuses it.
        expected_rows = 0 if mode in ("unpublished-dataset", "wrong-dataset-id") else 1
        assert _publish_evidence_rows(store, "run-146-mut") == expected_rows, (
            mode,
            _publish_evidence_rows(store, "run-146-mut"),
        )
    finally:
        store.close()


_MUTATIONS: dict[str, str] = {
    # R2's unpublished arm: the adapter returns a dataset it never
    # published through dataset_publish.
    "unpublished-dataset": (
        "        self.published.append(manifest[\"dataset_id\"])\n"
        "        return manifest"
    ),
    # R8's divergent arm: publish once, then return a mutated manifest.
    "divergent-republish": (
        "        admitted = await self.services.dataset_publish(manifest, context)\n"
        "        self.published.append(admitted[\"dataset_id\"])\n"
        "        admitted[\"status\"] = \"partial\"\n"
        "        return admitted"
    ),
    # R2's identity arm: the manifest carries a foreign dataset id.
    "wrong-dataset-id": (
        "        manifest[\"dataset_id\"] = \"ds:somewhere-else\"\n"
        "        self.published.append(manifest[\"dataset_id\"])\n"
        "        return manifest"
    ),
    # R6's envelope arm: an extra key in the invoke data envelope.
    "malformed-envelope": (
        "        admitted = await self.services.dataset_publish(manifest, context)\n"
        "        self.published.append(admitted[\"dataset_id\"])\n"
        "        return {\"extra\": True, **admitted}"
    ),
}
