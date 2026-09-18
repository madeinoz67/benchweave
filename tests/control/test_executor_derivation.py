"""RED control B: executor derivation wiring is load-bearing.

A procedure ``sample`` step selecting a derived variable from an invoke
dataset must return the computed value through ``select_sample`` with
``configuration_id`` provenance intact (design §4.5). With the derivation
application in ``_step_invoke`` disabled, the same run fails with
``SAMPLE_MISSING``. A structural refusal (unit mismatch on ``+``) ends the
body ``execution_error`` with step ``error_code: DERIVATION_INVALID`` while
the raw plugin dataset stays in scope as evidence.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from benchweave.control.binding import resolve_binding
from benchweave.control.clocking import TestClock
from benchweave.control.executor import Executor
from benchweave.host.plugin import DevicePlugin

from conftest import ROOT, readmit_mutated

PLUGINS_ROOT = ROOT / "plugins"
RUN_ID = "run-derivation"
FIXTURE_CONFIGURATION_ID = "cfg-derivation-probe"

RAIL_OFFSET = {
    "id": "rail_offset",
    "quantity": "voltage",
    "unit": "V",
    "expression": "voltage - 4.5",
}


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
    path = PLUGINS_ROOT / "benchweave" / name / "src" / f"benchweave_{name}" / "plugin.py"
    assert path.is_file(), f"plugin file missing: {path}"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _plugins(clock: TestClock) -> dict[str, DevicePlugin]:
    plugins: dict[str, DevicePlugin] = {}
    for device_id, name in (("psu", "sim_psu"), ("controller", "sim_controller")):
        plugin = _load_plugin(name).create_plugin(
            now_fn=clock.now_iso, monotonic_ns_fn=clock.now_ns
        )
        plugin.plugin_open(_NullServices())
        plugins[device_id] = plugin
    return plugins


def _derived_procedure(graph: dict[str, Any]) -> None:
    """Minimal literal-input procedure: configure → enable → measure → sample."""

    graph["descriptors"]["psu"]["derived_variables"] = [dict(RAIL_OFFSET)]
    graph["procedure"]["steps"] = [
        {
            "id": "configure",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.configure/1.0.0",
            "input": {
                "configuration_id": FIXTURE_CONFIGURATION_ID,
                "channel": "ch1",
                "voltage_v": 5.0,
                "current_limit_a": 0.5,
                "ovp_v": 5.5,
                "ocp_a": 0.5,
            },
            "timeout_ms": 500,
        },
        {
            "id": "enable",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.output/1.0.0",
            "input": {
                "channel": "ch1",
                "enabled": True,
                "configuration_id": FIXTURE_CONFIGURATION_ID,
            },
            "timeout_ms": 500,
        },
        {
            "id": "measure",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.measure/1.0.0",
            "input": {
                "configuration_id": FIXTURE_CONFIGURATION_ID,
                "channels": ["ch1"],
            },
            "timeout_ms": 500,
        },
        {
            "id": "rail",
            "kind": "sample",
            "source_step": "measure",
            "variable_id": "rail_offset",
            "unit": "V",
            "max_age_ms": 500,
            "require_known_uncertainty": False,
        },
        {
            "id": "check-rail",
            "kind": "assert",
            "predicate": {"sample": "rail", "minimum": 0.49, "maximum": 0.51},
        },
    ]


def _run(tmp_path: Path, mutate=_derived_procedure) -> tuple[Any, dict, dict[str, Any]]:
    clock = TestClock()
    plugins = _plugins(clock)
    ledger: dict[tuple[str, str, tuple[int, ...]], dict[str, Any]] = {}
    docs = readmit_mutated(tmp_path, mutate)
    executor = Executor(
        plugins=plugins,
        binding=resolve_binding(docs),
        policy=docs.policy,
        clock=clock,
        wall=clock,
        occurrence_ledger=ledger,
        derived_variables={
            device_id: descriptor.get("derived_variables", [])
            for device_id, descriptor in docs.descriptors.items()
        },
    )
    body = executor.run_body(
        docs.procedure,
        run_id=RUN_ID,
        body_deadline_ns=clock.now_ns() + int(docs.procedure["max_body_ms"]) * 1_000_000,
    )
    return body, docs, ledger


def test_derived_variable_flows_to_select_sample(tmp_path: Path) -> None:
    body, _docs, ledger = _run(tmp_path)
    assert body.body_outcome == "completed", body.reasons
    sample = ledger[(RUN_ID, "rail", ())]["result"]
    assert sample.value == 5.0 - 4.5  # both exactly representable: 0.5
    assert sample.invalid_reason is None
    assert sample.configuration_id == FIXTURE_CONFIGURATION_ID


def test_invoke_result_carries_the_derived_variable_with_marker(tmp_path: Path) -> None:
    body, _docs, ledger = _run(tmp_path)
    assert body.body_outcome == "completed", body.reasons
    measure = ledger[(RUN_ID, "measure", ())]["result"]
    dataset = measure.data["result"]
    variables = {variable["id"]: variable for variable in dataset["variables"]}
    rail = variables["rail_offset"]
    assert rail["values"] == [0.5]
    assert rail["uncertainty"] == {"status": "unknown"}
    assert rail["calibration"] == {"status": "unknown"}
    assert rail["derivation"] == {
        "kind": "expression",
        "expression": "voltage - 4.5",
        "operand_ids": ["voltage"],
    }
    # The plugin-emitted variables are untouched beside the appended one.
    assert variables["voltage"]["values"] == [5.0]
    assert variables["voltage"]["uncertainty"]["status"] == "known"


def test_structural_refusal_ends_the_body_execution_error(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _derived_procedure(graph)
        # voltage (V) - current (A) at a '+'/'-' node: refused loudly.
        graph["descriptors"]["psu"]["derived_variables"] = [
            {
                "id": "rail_offset",
                "quantity": "voltage",
                "unit": "V",
                "expression": "voltage - current",
            }
        ]

    body, _docs, ledger = _run(tmp_path, mutate)
    assert body.body_outcome == "execution_error", body.reasons
    measure_event = next(
        event for event in body.step_events if event["kind"] == "invoke"
    )
    assert measure_event["status"] == "error"
    assert measure_event["error_code"] == "DERIVATION_INVALID"
    assert "derivation_unit_mismatch:" in body.reasons[-1], body.reasons
    # The raw plugin dataset stays in scope as evidence (A06).
    measure = ledger[(RUN_ID, "measure", ())]["result"]
    ids = [variable["id"] for variable in measure.data["result"]["variables"]]
    assert ids == ["voltage", "current", "power"]


def test_known_uncertainty_requirement_refuses_derived_samples(tmp_path: Path) -> None:
    """A02 honesty: derived uncertainty is structurally unknown, so a sample
    step demanding a known one is refused — an honest refusal, not a defect
    (design §4.4 consequence)."""

    def mutate(graph: dict[str, Any]) -> None:
        _derived_procedure(graph)
        sample = next(
            step for step in graph["procedure"]["steps"] if step["id"] == "rail"
        )
        sample["require_known_uncertainty"] = True

    body, _docs, _ledger = _run(tmp_path, mutate)
    assert body.body_outcome == "execution_error", body.reasons
    rail_event = next(event for event in body.step_events if event["kind"] == "sample")
    assert rail_event["status"] == "error"
    assert rail_event["error_code"] == "INVALID_SAMPLE"
    assert "UNKNOWN_UNCERTAINTY" in body.reasons[-1], body.reasons
