"""WP04 S2/S3 — simulator plugin conformance against the published ABI.

One shared conformance suite, parametrized over every simulator plugin: the
"published ABI" is one suite, not two opinions (ISA D3). Plugins are loaded
by explicit path — registry admission is WP06's job, and the loader itself
is part of what this proves. Deterministic: clocks are injected.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from benchweave.host import (
    DispatchState,
    ErrorCode,
    OperationRequest,
    OperationStatus,
    OperationVerb,
    Quality,
    SimulationInfo,
)

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
CONTRACTS = ROOT / "standards" / "otdp/0.2.0"
NOW = "2026-09-11T00:00:00Z"
TICK = 1_000_000


def load_plugin_module(name: str) -> ModuleType:
    path = PLUGINS / "benchweave" / name / "src" / f"benchweave_{name}" / "plugin.py"
    assert path.is_file(), f"plugin file missing: {path}"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class NullServices:
    """Scoped-services stand-in recording every touch."""

    def __init__(self) -> None:
        self.touches: list[str] = []

    def resolve_content(self, content_id: str) -> bytes:
        self.touches.append(f"resolve:{content_id}")
        return b"{}"

    def retain_evidence(self, key: str, payload: bytes) -> str:
        self.touches.append(f"retain:{key}")
        return f"evidence-{key}"

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        self.touches.append(f"event:{kind}")

    def quota_state(self) -> dict[str, int]:
        return {"dataset_bytes_used": 0, "evidence_entries_used": 0, "events_emitted": 0}

    def register_reading_sink(self, sink: Any) -> None:
        self.touches.append("reading-sink")


class Clock:
    def __init__(self) -> None:
        self.now_ns = 0

    def monotonic_ns(self) -> int:
        return self.now_ns

    def iso(self) -> str:
        return NOW

    def advance(self, ns: int) -> None:
        self.now_ns += ns


def make_sim_psu(clock: Clock) -> Any:
    module = load_plugin_module("sim_psu")
    return module.SimPsuPlugin(now_fn=clock.iso, monotonic_ns_fn=clock.monotonic_ns)


@pytest.fixture()
def psu() -> Iterator[Any]:
    clock = Clock()
    plugin = make_sim_psu(clock)
    plugin.plugin_open(NullServices())
    yield plugin
    plugin.plugin_close()


# --- sim_controller behaviour -------------------------------------------------


def make_sim_controller(clock: Clock) -> Any:
    module = load_plugin_module("sim_controller")
    return module.create_plugin(now_fn=clock.iso, monotonic_ns_fn=clock.monotonic_ns)


def test_controller_uptime_tracks_injected_clock() -> None:
    clock = Clock()
    plugin = make_sim_controller(clock)
    plugin.plugin_open(NullServices())
    first = plugin.dispatch(
        OperationRequest.read("op-1", parameter="uptime_s"), deadline_ns=10**12
    )
    assert first.data.value == 0
    clock.advance(5_000_000_000)
    second = plugin.dispatch(
        OperationRequest.read("op-2", parameter="uptime_s"), deadline_ns=10**15
    )
    assert second.data.value == 5
    plugin.plugin_close()


def test_controller_rejects_non_note_writes() -> None:
    clock = Clock()
    plugin = make_sim_controller(clock)
    plugin.plugin_open(NullServices())
    result = plugin.dispatch(
        OperationRequest.write("op-1", parameter="setpoint", value=1), deadline_ns=10**12
    )
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ARGUMENT
    plugin.plugin_close()


def test_controller_note_too_long_is_dispatched_device_rejection() -> None:
    """The note-length refusal is device state: the write reached the device."""
    clock = Clock()
    plugin = make_sim_controller(clock)
    plugin.plugin_open(NullServices())
    result = plugin.dispatch(
        OperationRequest.write("op-1", parameter="operator_note", value="x" * 201),
        deadline_ns=10**12,
    )
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.DEVICE_REJECTED
    assert result.error.dispatch_state is DispatchState.DISPATCHED
    plugin.plugin_close()


# --- shared ABI conformance (parametrized over plugins; S3 extends) ----------

CONFORMING_PLUGINS: list[str] = ["sim_psu", "sim_controller"]


@pytest.fixture(params=CONFORMING_PLUGINS)
def conforming(request: pytest.FixtureRequest) -> Any:
    clock = Clock()
    module = load_plugin_module(request.param)
    plugin = module.create_plugin(now_fn=clock.iso, monotonic_ns_fn=clock.monotonic_ns)
    plugin.plugin_open(NullServices())
    return plugin


def test_identify_returns_device_identity(conforming: Any) -> None:
    result = conforming.dispatch(OperationRequest.identify("op-1"), deadline_ns=TICK)
    assert result.status is OperationStatus.OK
    identity = result.data
    assert identity.manufacturer == "benchweave-sim"
    assert identity.source.value == "device"


def test_simulation_is_visibly_identified(conforming: Any) -> None:
    info = conforming.simulation
    assert isinstance(info, SimulationInfo)
    assert info.simulated is True
    assert info.label


def test_read_returns_valid_reading(conforming: Any) -> None:
    result = conforming.dispatch(
        OperationRequest.read("op-1", parameter="identity_model"), deadline_ns=TICK
    )
    assert result.status is OperationStatus.OK
    assert result.data.quality is Quality.VALID


def test_write_in_bounds_succeeds(conforming: Any) -> None:
    result = conforming.dispatch(
        OperationRequest.write("op-1", parameter="operator_note", value="checked"),
        deadline_ns=TICK,
    )
    assert result.status is OperationStatus.OK
    assert result.data.assurance.value == "dispatched"


def test_write_unknown_parameter_is_invalid_argument(conforming: Any) -> None:
    result = conforming.dispatch(
        OperationRequest.write("op-1", parameter="no_such_parameter", value=1),
        deadline_ns=TICK,
    )
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ARGUMENT
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_unsupported_verb_is_rejected_not_dispatched(conforming: Any) -> None:
    request = OperationRequest(
        operation_id="op-1",
        verb=OperationVerb.CAPTURE,
        arguments={"capture_id": "c", "format": "raw_binary", "sample_count": 1, "max_bytes": 8},
    )
    result = conforming.dispatch(request, deadline_ns=TICK)
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.UNSUPPORTED
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_dispatch_before_open_is_internal_error() -> None:
    clock = Clock()
    module = load_plugin_module("sim_psu")
    plugin = module.create_plugin(now_fn=clock.iso, monotonic_ns_fn=clock.monotonic_ns)
    result = plugin.dispatch(OperationRequest.identify("op-1"), deadline_ns=TICK)
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.INTERNAL_ERROR


def test_expired_deadline_times_out_not_dispatched() -> None:
    clock = Clock()
    module = load_plugin_module("sim_psu")
    plugin = module.create_plugin(now_fn=clock.iso, monotonic_ns_fn=clock.monotonic_ns)
    plugin.plugin_open(NullServices())
    clock.advance(10_000_000)
    result = plugin.dispatch(OperationRequest.identify("op-1"), deadline_ns=TICK)
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.TIMEOUT
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


# --- sim_psu behaviour --------------------------------------------------------


def test_psu_voltage_follows_output_state(psu: Any) -> None:
    plugin = psu
    off = plugin.dispatch(
        OperationRequest.read("op-1", parameter="output_voltage_v"), deadline_ns=TICK
    )
    assert off.data.value == 0.0
    plugin.dispatch(
        OperationRequest.write("op-2", parameter="voltage_setpoint_v", value=12.0),
        deadline_ns=TICK,
    )
    plugin.dispatch(
        OperationRequest.write("op-3", parameter="output_enabled", value=True),
        deadline_ns=TICK,
    )
    on = plugin.dispatch(
        OperationRequest.read("op-4", parameter="output_voltage_v"), deadline_ns=TICK
    )
    assert on.data.value == 12.0


def test_psu_write_out_of_bounds_is_device_rejected(psu: Any) -> None:
    plugin = psu
    result = plugin.dispatch(
        OperationRequest.write("op-1", parameter="voltage_setpoint_v", value=999.0),
        deadline_ns=TICK,
    )
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.DEVICE_REJECTED
    assert result.error.dispatch_state is DispatchState.DISPATCHED


def test_psu_write_wrong_type_on_bounded_parameter_is_invalid_argument(psu: Any) -> None:
    """Wrong type is a framing failure; the envelope sees only well-typed values.

    The bounds branch types the value before evaluating the envelope
    (REG-2 dispatch-state honesty), so a non-numeric value for a bounded
    parameter refuses INVALID_ARGUMENT / not_dispatched — the same taxonomy
    as _action_configure's numeric field checks and the profile catalog's
    string-typed configuration_id. A well-typed but out-of-range value
    stays DEVICE_REJECTED / dispatched (write_setpoint_out_of_bounds).
    """
    plugin = psu
    result = plugin.dispatch(
        OperationRequest.write("op-1", parameter="voltage_setpoint_v", value="twelve"),
        deadline_ns=TICK,
    )
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ARGUMENT
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_psu_ovp_trip_latches_until_reset(psu: Any) -> None:
    plugin = psu
    plugin.dispatch(
        OperationRequest.write("op-1", parameter="output_enabled", value=True),
        deadline_ns=TICK,
    )
    plugin.dispatch(
        OperationRequest.write("op-2", parameter="ovp_threshold_v", value=10.0),
        deadline_ns=TICK,
    )
    trip = plugin.dispatch(
        OperationRequest.write("op-3", parameter="voltage_setpoint_v", value=12.0),
        deadline_ns=TICK,
    )
    assert trip.status is OperationStatus.ERROR
    assert trip.error is not None and trip.error.code is ErrorCode.DEVICE_REJECTED
    errors = plugin.dispatch(OperationRequest("op-4", OperationVerb.GET_ERRORS), deadline_ns=TICK)
    assert errors.status is OperationStatus.OK
    assert any(entry.code == "OVP_TRIP" for entry in errors.data.entries)
    blocked = plugin.dispatch(
        OperationRequest.write("op-5", parameter="voltage_setpoint_v", value=5.0),
        deadline_ns=TICK,
    )
    assert blocked.status is OperationStatus.ERROR
    assert blocked.error is not None and blocked.error.code is ErrorCode.DEVICE_REJECTED
    assert blocked.error.dispatch_state is DispatchState.DISPATCHED
    reset = plugin.dispatch(OperationRequest("op-6", OperationVerb.RESET), deadline_ns=TICK)
    assert reset.status is OperationStatus.OK and reset.data["acknowledged"] is True
    recovered = plugin.dispatch(
        OperationRequest.write("op-7", parameter="voltage_setpoint_v", value=5.0),
        deadline_ns=TICK,
    )
    assert recovered.status is OperationStatus.OK


def test_psu_ovp_trip_raw_write_reports_dispatched(psu: Any) -> None:
    """A raw WRITE that trips reports DISPATCHED, like the invoke path.

    The write is applied to device state before the trip check runs (the
    trip is detected *from* the applied state and the latch persists until
    reset), so claiming not_dispatched would deny work the device did. This
    is the same compound-action honesty the invoke path pins for configure.
    """
    plugin = psu
    plugin.dispatch(
        OperationRequest.write("op-1", parameter="output_enabled", value=True),
        deadline_ns=TICK,
    )
    plugin.dispatch(
        OperationRequest.write("op-2", parameter="ovp_threshold_v", value=10.0),
        deadline_ns=TICK,
    )
    trip = plugin.dispatch(
        OperationRequest.write("op-3", parameter="voltage_setpoint_v", value=12.0),
        deadline_ns=TICK,
    )
    assert trip.status is OperationStatus.ERROR
    assert trip.error is not None and trip.error.code is ErrorCode.DEVICE_REJECTED
    assert trip.error.dispatch_state is DispatchState.DISPATCHED
    applied = plugin.dispatch(
        OperationRequest.read("op-4", parameter="voltage_setpoint_v"),
        deadline_ns=TICK,
    )
    assert applied.data.value == 12.0


def test_psu_reset_clears_configuration_token(psu: Any) -> None:
    """Reset clears the stored configuration_id: the old token is dead (M1).

    The trip latch already forces a reset boundary; the configuration token
    must not survive it — a post-reset measure under the pre-reset token is
    device-rejected, so stale configuration state can never leak into a new
    configuration's measurements.
    """
    configured = psu.dispatch(
        _invoke(
            "otdp.dc_psu.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channel": "ch1",
                "voltage_v": 5.0,
                "current_limit_a": 0.5,
                "ovp_v": 5.5,
                "ocp_a": 0.5,
            },
        ),
        deadline_ns=10**12,
    )
    assert configured.status.value == "ok"

    reset = psu.dispatch(OperationRequest("op-2", OperationVerb.RESET), deadline_ns=10**12)
    assert reset.status.value == "ok"

    stale = psu.dispatch(
        _invoke(
            "otdp.dc_psu.measure/1.0.0",
            {"configuration_id": "cfg-1", "channels": ["ch1"]},
        ),
        deadline_ns=10**12,
    )
    assert stale.status.value == "error"
    assert stale.error.code.value == "DEVICE_REJECTED"
    assert "configuration" in stale.error.message


# --- WP05 class actions (INVOKE: configure / output / measure) ----------------


def _invoke(action_id: str, input_: dict[str, Any]) -> OperationRequest:
    return OperationRequest(
        operation_id="op-1",
        verb=OperationVerb.INVOKE,
        arguments={"action_id": action_id, "input": input_},
    )


def test_invoke_configure_applies_and_echoes(psu: Any) -> None:
    result = psu.dispatch(
        _invoke(
            "otdp.dc_psu.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channel": "ch1",
                "voltage_v": 5.0,
                "current_limit_a": 0.5,
                "ovp_v": 5.5,
                "ocp_a": 0.5,
            },
        ),
        deadline_ns=10**12,
    )
    assert result.status.value == "ok"
    assert result.data["result"]["configuration_id"] == "cfg-1"
    reading = psu.dispatch(
        OperationRequest.read("op-2", parameter="voltage_setpoint_v"),
        deadline_ns=10**12,
    )
    assert reading.data.value == 5.0


def test_invoke_measure_returns_admitted_scalar_set(psu: Any) -> None:
    psu.dispatch(
        _invoke(
            "otdp.dc_psu.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channel": "ch1",
                "voltage_v": 5.0,
                "current_limit_a": 0.5,
                "ovp_v": 5.5,
                "ocp_a": 0.5,
            },
        ),
        deadline_ns=10**12,
    )
    psu.dispatch(
        _invoke(
            "otdp.dc_psu.output/1.0.0",
            {"channel": "ch1", "enabled": True, "configuration_id": "cfg-1"},
        ),
        deadline_ns=10**12,
    )
    result = psu.dispatch(
        _invoke(
            "otdp.dc_psu.measure/1.0.0",
            {"configuration_id": "cfg-1", "channels": ["ch1"]},
        ),
        deadline_ns=10**12,
    )
    dataset = result.data["result"]
    assert dataset["kind"] == "scalar_set"
    ids = [v["id"] for v in dataset["variables"]]
    assert ids == ["voltage", "current", "power"]
    voltage = dataset["variables"][0]
    assert voltage["unit"] == "V" and voltage["values"] == [5.0]
    assert voltage["dimensions"] == [] and voltage["status"] == "valid"
    assert voltage["uncertainty"] == {"status": "known", "absolute": 0.05}


def test_invoke_unknown_action_rejected_not_dispatched(psu: Any) -> None:
    result = psu.dispatch(_invoke("otdp.dc_psu.nope/1.0.0", {}), deadline_ns=10**12)
    assert result.status.value == "error"
    assert result.error.code.value == "UNSUPPORTED"
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_invoke_measure_requires_current_configuration(psu: Any) -> None:
    result = psu.dispatch(
        _invoke(
            "otdp.dc_psu.measure/1.0.0",
            {"configuration_id": "cfg-wrong", "channels": ["ch1"]},
        ),
        deadline_ns=10**12,
    )
    assert result.status.value == "error"
    assert result.error.code.value == "DEVICE_REJECTED"
    assert result.error.dispatch_state is DispatchState.DISPATCHED


def test_invoke_measure_dataset_matches_otdp_schema(psu: Any) -> None:
    psu.dispatch(
        _invoke(
            "otdp.dc_psu.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channel": "ch1",
                "voltage_v": 5.0,
                "current_limit_a": 0.5,
                "ovp_v": 5.5,
                "ocp_a": 0.5,
            },
        ),
        deadline_ns=10**12,
    )
    psu.dispatch(
        _invoke(
            "otdp.dc_psu.output/1.0.0",
            {"channel": "ch1", "enabled": True, "configuration_id": "cfg-1"},
        ),
        deadline_ns=10**12,
    )
    result = psu.dispatch(
        _invoke(
            "otdp.dc_psu.measure/1.0.0",
            {"configuration_id": "cfg-1", "channels": ["ch1"]},
        ),
        deadline_ns=10**12,
    )
    dataset = result.data["result"]
    schema = json.loads(
        (CONTRACTS / "otdp-measurement.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(dataset)


def test_invoke_output_without_configuration_id_is_allowed(psu: Any) -> None:
    """Safe transitions must not depend on a configuration token (exec contract §7)."""
    result = psu.dispatch(
        _invoke("otdp.dc_psu.output/1.0.0", {"channel": "ch1", "enabled": False}),
        deadline_ns=10**12,
    )
    assert result.status.value == "ok"
    assert result.data["result"]["enabled"] is False


def test_invoke_output_with_stale_configuration_id_is_device_rejected(psu: Any) -> None:
    result = psu.dispatch(
        _invoke(
            "otdp.dc_psu.output/1.0.0",
            {"channel": "ch1", "enabled": True, "configuration_id": "cfg-stale"},
        ),
        deadline_ns=10**12,
    )
    assert result.status.value == "error"
    assert result.error.code.value == "DEVICE_REJECTED"
    assert result.error.dispatch_state is DispatchState.DISPATCHED


def test_invoke_configure_rejects_bad_channel_and_non_numeric_fields(psu: Any) -> None:
    bad_channel = psu.dispatch(
        _invoke(
            "otdp.dc_psu.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channel": "ch9",
                "voltage_v": 5.0,
                "current_limit_a": 0.5,
                "ovp_v": 5.5,
                "ocp_a": 0.5,
            },
        ),
        deadline_ns=10**12,
    )
    assert bad_channel.status.value == "error"
    assert bad_channel.error.code.value == "INVALID_ARGUMENT"
    non_numeric = psu.dispatch(
        _invoke(
            "otdp.dc_psu.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channel": "ch1",
                "voltage_v": "five",
                "current_limit_a": 0.5,
                "ovp_v": 5.5,
                "ocp_a": 0.5,
            },
        ),
        deadline_ns=10**12,
    )
    assert non_numeric.status.value == "error"
    assert non_numeric.error.code.value == "INVALID_ARGUMENT"


def test_invoke_configure_trip_surfaces_as_device_rejected(psu: Any) -> None:
    psu.dispatch(
        _invoke(
            "otdp.dc_psu.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channel": "ch1",
                "voltage_v": 3.0,
                "current_limit_a": 0.5,
                "ovp_v": 10.0,
                "ocp_a": 0.5,
            },
        ),
        deadline_ns=10**12,
    )
    psu.dispatch(
        _invoke(
            "otdp.dc_psu.output/1.0.0",
            {"channel": "ch1", "enabled": True, "configuration_id": "cfg-1"},
        ),
        deadline_ns=10**12,
    )
    result = psu.dispatch(
        _invoke(
            "otdp.dc_psu.configure/1.0.0",
            {
                "configuration_id": "cfg-2",
                "channel": "ch1",
                "voltage_v": 12.0,
                "current_limit_a": 0.5,
                "ovp_v": 10.0,
                "ocp_a": 0.5,
            },
        ),
        deadline_ns=10**12,
    )
    assert result.status.value == "error"
    assert result.error.code.value == "DEVICE_REJECTED"
    assert result.error.dispatch_state is DispatchState.DISPATCHED
    errors = psu.dispatch(
        OperationRequest("op-9", OperationVerb.GET_ERRORS), deadline_ns=10**12
    )
    assert any(entry.code == "OVP_TRIP" for entry in errors.data.entries)


def test_invoke_configure_bounds_rejection_mid_apply_reports_dispatched(psu: Any) -> None:
    """A bounds rejection lands after thresholds applied — the invoke was sent."""
    result = psu.dispatch(
        _invoke(
            "otdp.dc_psu.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channel": "ch1",
                "voltage_v": 999.0,
                "current_limit_a": 0.5,
                "ovp_v": 5.5,
                "ocp_a": 0.5,
            },
        ),
        deadline_ns=10**12,
    )
    assert result.status.value == "error"
    assert result.error.code.value == "DEVICE_REJECTED"
    assert result.error.dispatch_state is DispatchState.DISPATCHED
    thresholds = psu.dispatch(
        OperationRequest.read("op-3", parameter="ovp_threshold_v"),
        deadline_ns=10**12,
    )
    assert thresholds.data.value == 5.5
