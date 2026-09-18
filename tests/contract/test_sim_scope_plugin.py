"""sim_scope — host-ABI dispatch suite for the settings-presets proof vehicle.

Issue #6 row A: sim_scope is the first in-tree plugin whose named setups ship
as ui/presets documents. This file pins the plugin side of that claim — the
five otdp.oscilloscope profile actions over INVOKE, per-channel settings
applied through the parameter write path, and the configuration token
discipline a future apply path must not replay past (design §2.4).

Modeled on tests/contract/test_sim_plugins.py: explicit module load by path,
injected Clock, NullServices. Not in the shared CONFORMING_PLUGINS suite (the
scope plugin has no operator_note-style write target the shared suite asserts).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

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
NOW = "2026-09-19T00:00:00Z"
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


def make_sim_scope(clock: Clock) -> Any:
    module = load_plugin_module("sim_scope")
    return module.create_plugin(now_fn=clock.iso, monotonic_ns_fn=clock.monotonic_ns)


@pytest.fixture()
def scope() -> Iterator[Any]:
    clock = Clock()
    plugin = make_sim_scope(clock)
    plugin.plugin_open(NullServices())
    yield plugin
    plugin.plugin_close()


def _invoke(action_id: str, input_: dict[str, Any]) -> OperationRequest:
    return OperationRequest(
        operation_id="op-1",
        verb=OperationVerb.INVOKE,
        arguments={"action_id": action_id, "input": input_},
    )


def _configure(channels: list[dict[str, Any]], configuration_id: str = "cfg-1") -> OperationRequest:
    return _invoke(
        "otdp.oscilloscope.configure/1.0.0",
        {
            "configuration_id": configuration_id,
            "channels": channels,
            "sample_rate_hz": 1000.0,
            "sample_count": 1024,
            "pretrigger_fraction": 0.0,
            "trigger": {"kind": "immediate"},
        },
    )


CHANNEL_ITEM = {
    "channel": "ch1",
    "coupling": "dc",
    "range_v": 5.0,
    "offset_v": 0.0,
    "probe_ratio": 10.0,
}

LOW_NOISE_PAIR = [
    {
        "channel": "ch1",
        "coupling": "dc",
        "range_v": 1.0,
        "offset_v": 0.05,
        "probe_ratio": 10.0,
    },
    {
        "channel": "ch3",
        "coupling": "ac",
        "range_v": 1.0,
        "offset_v": -0.05,
        "probe_ratio": 10.0,
    },
]


def _arm(scope: Any, configuration_id: str = "cfg-1", acquisition_id: str = "acq-1") -> Any:
    return scope.dispatch(
        _invoke(
            "otdp.oscilloscope.arm/1.0.0",
            {
                "configuration_id": configuration_id,
                "acquisition_id": acquisition_id,
                "max_duration_ms": 1000,
            },
        ),
        deadline_ns=10**12,
    )


# --- ABI conformance -----------------------------------------------------------


def test_identify_returns_device_identity(scope: Any) -> None:
    result = scope.dispatch(OperationRequest.identify("op-1"), deadline_ns=TICK)
    assert result.status is OperationStatus.OK
    identity = result.data
    assert identity.manufacturer == "benchweave-sim"
    assert identity.source.value == "device"


def test_simulation_is_visibly_identified(scope: Any) -> None:
    info = scope.simulation
    assert isinstance(info, SimulationInfo)
    assert info.simulated is True
    assert info.label


def test_read_returns_valid_reading(scope: Any) -> None:
    result = scope.dispatch(
        OperationRequest.read("op-1", parameter="identity_model"), deadline_ns=TICK
    )
    assert result.status is OperationStatus.OK
    assert result.data.quality is Quality.VALID


def test_write_unknown_parameter_is_invalid_argument(scope: Any) -> None:
    result = scope.dispatch(
        OperationRequest.write("op-1", parameter="no_such_parameter", value=1),
        deadline_ns=TICK,
    )
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ARGUMENT
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_unsupported_verb_is_rejected_not_dispatched(scope: Any) -> None:
    request = OperationRequest(
        operation_id="op-1",
        verb=OperationVerb.CAPTURE,
        arguments={"capture_id": "c", "format": "raw_binary", "sample_count": 1, "max_bytes": 8},
    )
    result = scope.dispatch(request, deadline_ns=TICK)
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.UNSUPPORTED
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_dispatch_before_open_is_internal_error() -> None:
    clock = Clock()
    plugin = make_sim_scope(clock)
    result = plugin.dispatch(OperationRequest.identify("op-1"), deadline_ns=TICK)
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.INTERNAL_ERROR


def test_expired_deadline_times_out_not_dispatched() -> None:
    clock = Clock()
    plugin = make_sim_scope(clock)
    plugin.plugin_open(NullServices())
    clock.advance(10_000_000)
    result = plugin.dispatch(OperationRequest.identify("op-1"), deadline_ns=TICK)
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.TIMEOUT
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
    plugin.plugin_close()


# --- settings writes (the descriptor's declared envelope is the contract) ------


def test_write_setting_in_envelope_applies_and_verifies_by_readback(scope: Any) -> None:
    result = scope.dispatch(
        OperationRequest.write("op-1", parameter="averaging_count", value=8),
        deadline_ns=TICK,
    )
    assert result.status is OperationStatus.OK
    read = scope.dispatch(
        OperationRequest.read("op-2", parameter="averaging_count"), deadline_ns=TICK
    )
    assert read.data.value == 8


def test_write_averaging_out_of_envelope_is_invalid_argument(scope: Any) -> None:
    result = scope.dispatch(
        OperationRequest.write("op-1", parameter="averaging_count", value=0),
        deadline_ns=TICK,
    )
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ARGUMENT
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_write_probe_ratio_out_of_envelope_is_invalid_argument(scope: Any) -> None:
    result = scope.dispatch(
        OperationRequest.write("op-1", parameter="ch1_probe_ratio", value=3),
        deadline_ns=TICK,
    )
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ARGUMENT
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_write_unknown_channel_parameter_is_invalid_argument(scope: Any) -> None:
    result = scope.dispatch(
        OperationRequest.write("op-1", parameter="ch9_probe_ratio", value=1),
        deadline_ns=TICK,
    )
    assert result.status is OperationStatus.ERROR
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ARGUMENT


# --- configure: membership is enablement ---------------------------------------


def test_configure_applies_per_channel_state_observable_by_read(scope: Any) -> None:
    result = scope.dispatch(_configure([CHANNEL_ITEM]), deadline_ns=10**12)
    assert result.status.value == "ok"
    assert result.data["result"]["configuration_id"] == "cfg-1"
    for parameter, expected in (
        ("ch1_probe_ratio", 10.0),
        ("ch1_offset_v", 0.0),
        ("ch1_range_v", 5.0),
    ):
        reading = scope.dispatch(
            OperationRequest.read("op-2", parameter=parameter), deadline_ns=10**12
        )
        assert reading.data.value == expected


def test_configure_requires_configuration_id(scope: Any) -> None:
    request = _invoke(
        "otdp.oscilloscope.configure/1.0.0",
        {
            "configuration_id": "",
            "channels": [CHANNEL_ITEM],
            "sample_rate_hz": 1000.0,
            "sample_count": 1024,
            "pretrigger_fraction": 0.0,
            "trigger": {"kind": "immediate"},
        },
    )
    result = scope.dispatch(request, deadline_ns=10**12)
    assert result.status.value == "error"
    assert result.error.code.value == "INVALID_ARGUMENT"
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_configure_rejects_unknown_channel(scope: Any) -> None:
    item = dict(CHANNEL_ITEM)
    item["channel"] = "ch9"
    result = scope.dispatch(_configure([item]), deadline_ns=10**12)
    assert result.status.value == "error"
    assert result.error.code.value == "INVALID_ARGUMENT"


def test_configure_rejects_non_numeric_field(scope: Any) -> None:
    item = dict(CHANNEL_ITEM)
    item["range_v"] = "five"
    result = scope.dispatch(_configure([item]), deadline_ns=10**12)
    assert result.status.value == "error"
    assert result.error.code.value == "INVALID_ARGUMENT"


def test_configure_rejects_out_of_envelope_probe_ratio(scope: Any) -> None:
    item = dict(CHANNEL_ITEM)
    item["probe_ratio"] = 3
    result = scope.dispatch(_configure([item]), deadline_ns=10**12)
    assert result.status.value == "error"
    assert result.error.code.value == "INVALID_ARGUMENT"


# --- lifecycle: arm / trigger / fetch / abort ----------------------------------


def test_fetch_covers_configured_channels_only(scope: Any) -> None:
    """A preset that configures two channels yields two-channel fetches.

    The pair is deliberately non-contiguous (ch1+ch3): enablement by
    membership must not be confusable with an index slice.
    """
    scope.dispatch(_configure(LOW_NOISE_PAIR), deadline_ns=10**12)
    assert _arm(scope).status.value == "ok"
    result = scope.dispatch(
        _invoke(
            "otdp.oscilloscope.fetch/1.0.0",
            {"acquisition_id": "acq-1", "max_bytes": 1_048_576, "allow_partial": False},
        ),
        deadline_ns=10**12,
    )
    assert result.status.value == "ok"
    dataset = result.data["result"]
    channel_ids = [variable["channel_ids"] for variable in dataset["variables"]]
    assert channel_ids == [["ch1"], ["ch3"]]
    for variable in dataset["variables"]:
        assert len(variable["values"]) == 1024


def test_fetch_replaces_previous_configuration(scope: Any) -> None:
    """Reconfiguring re-scopes fetch: the enabled set is the last configure's."""
    scope.dispatch(_configure(LOW_NOISE_PAIR), deadline_ns=10**12)
    scope.dispatch(
        _configure(
            [
                {
                    "channel": "ch2",
                    "coupling": "dc",
                    "range_v": 5.0,
                    "offset_v": 0.0,
                    "probe_ratio": 1.0,
                }
            ],
            configuration_id="cfg-2",
        ),
        deadline_ns=10**12,
    )
    assert _arm(scope, configuration_id="cfg-2").status.value == "ok"
    result = scope.dispatch(
        _invoke(
            "otdp.oscilloscope.fetch/1.0.0",
            {"acquisition_id": "acq-1", "max_bytes": 1_048_576, "allow_partial": False},
        ),
        deadline_ns=10**12,
    )
    assert [variable["channel_ids"] for variable in result.data["result"]["variables"]] == [
        ["ch2"]
    ]


def test_fetch_requires_armed_acquisition(scope: Any) -> None:
    scope.dispatch(_configure(LOW_NOISE_PAIR), deadline_ns=10**12)
    result = scope.dispatch(
        _invoke(
            "otdp.oscilloscope.fetch/1.0.0",
            {"acquisition_id": "acq-none", "max_bytes": 1_048_576, "allow_partial": False},
        ),
        deadline_ns=10**12,
    )
    assert result.status.value == "error"
    assert result.error.code.value == "INVALID_ARGUMENT"


def test_arm_requires_current_configuration_token(scope: Any) -> None:
    """Token discipline (design §2.4): a replayed stale configuration_id is refused.

    sim_psu's measure/output enforce the stored token; sim_scope's arm does the
    same, so a future apply path that replays a preset's literal
    configuration_id fails visibly here instead of silently reconfiguring.
    """
    scope.dispatch(_configure(LOW_NOISE_PAIR, configuration_id="cfg-1"), deadline_ns=10**12)
    stale = _arm(scope, configuration_id="preset-low-noise-pair")
    assert stale.status.value == "error"
    assert stale.error.code.value == "DEVICE_REJECTED"
    assert "configuration" in stale.error.message


def test_trigger_and_abort_transition_the_acquisition(scope: Any) -> None:
    scope.dispatch(_configure(LOW_NOISE_PAIR), deadline_ns=10**12)
    assert _arm(scope).status.value == "ok"
    triggered = scope.dispatch(
        _invoke("otdp.oscilloscope.trigger/1.0.0", {"acquisition_id": "acq-1"}),
        deadline_ns=10**12,
    )
    assert triggered.status.value == "ok"
    assert triggered.data["result"]["state"] in ("running", "complete")
    aborted = scope.dispatch(
        _invoke("otdp.oscilloscope.abort/1.0.0", {"acquisition_id": "acq-1"}),
        deadline_ns=10**12,
    )
    assert aborted.status.value == "ok"
    assert aborted.data["result"]["state"] == "aborted"
    refused = scope.dispatch(
        _invoke(
            "otdp.oscilloscope.fetch/1.0.0",
            {"acquisition_id": "acq-1", "max_bytes": 1_048_576, "allow_partial": False},
        ),
        deadline_ns=10**12,
    )
    assert refused.status.value == "error"


def test_invoke_unknown_action_rejected_not_dispatched(scope: Any) -> None:
    result = scope.dispatch(_invoke("otdp.oscilloscope.nope/1.0.0", {}), deadline_ns=10**12)
    assert result.status.value == "error"
    assert result.error.code.value == "UNSUPPORTED"
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


# --- fetch honesty (fix wave F3): boundary table + lifecycle pins ---------------


def _configure_edge(scope: Any) -> None:
    """Configure an edge-triggered two-channel acquisition that stays armed."""
    result = scope.dispatch(
        _invoke(
            "otdp.oscilloscope.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channels": LOW_NOISE_PAIR,
                "sample_rate_hz": 1000.0,
                "sample_count": 1024,
                "pretrigger_fraction": 0.25,
                "trigger": {
                    "kind": "edge",
                    "source_channel": "ch1",
                    "slope": "rising",
                    "level_v": 0.5,
                },
            },
        ),
        deadline_ns=10**12,
    )
    assert result.status.value == "ok"


def _fetch(scope: Any, max_bytes: int, allow_partial: bool, acq: str = "acq-1") -> Any:
    return scope.dispatch(
        _invoke(
            "otdp.oscilloscope.fetch/1.0.0",
            {"acquisition_id": acq, "max_bytes": max_bytes, "allow_partial": allow_partial},
        ),
        deadline_ns=10**12,
    )


def test_fetch_armed_without_partial_is_refused(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    refused = _fetch(scope, 1_048_576, False)
    assert refused.status.value == "error"
    assert refused.error.code.value == "DEVICE_REJECTED"


def test_fetch_armed_with_partial_returns_partial_dataset(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    result = _fetch(scope, 1_048_576, True)
    assert result.status.value == "ok"
    dataset = result.data["result"]
    assert dataset["status"] == "partial"
    assert "trigger" in dataset["status_reason"]
    for variable in dataset["variables"]:
        assert len(variable["values"]) == 256  # the pretrigger buffer: 0.25 x 1024
    assert dataset["axes"][0]["length"] == 256


def test_fetch_complete_at_exact_budget_is_complete(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    triggered = scope.dispatch(
        _invoke("otdp.oscilloscope.trigger/1.0.0", {"acquisition_id": "acq-1"}),
        deadline_ns=10**12,
    )
    assert triggered.status.value == "ok"
    exact = _fetch(scope, 2 * 1024 * 8, False)  # 2 channels x 1024 float64
    assert exact.status.value == "ok"
    dataset = exact.data["result"]
    assert dataset["status"] == "complete"
    for variable in dataset["variables"]:
        assert len(variable["values"]) == 1024


def test_fetch_complete_below_budget_refuses_without_partial(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    scope.dispatch(
        _invoke("otdp.oscilloscope.trigger/1.0.0", {"acquisition_id": "acq-1"}),
        deadline_ns=10**12,
    )
    refused = _fetch(scope, 2 * 1024 * 8 - 1, False)
    assert refused.status.value == "error"
    assert refused.error.code.value == "DEVICE_REJECTED"


def test_fetch_complete_below_budget_truncates_with_partial(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    scope.dispatch(
        _invoke("otdp.oscilloscope.trigger/1.0.0", {"acquisition_id": "acq-1"}),
        deadline_ns=10**12,
    )
    result = _fetch(scope, 2 * 1024 * 8 - 1, True)
    assert result.status.value == "ok"
    dataset = result.data["result"]
    assert dataset["status"] == "partial"
    assert "max_bytes" in dataset["status_reason"]
    for variable in dataset["variables"]:
        assert len(variable["values"]) == 1023  # (16384 - 1) // (8 * 2)
    assert dataset["axes"][0]["length"] == 1023


def test_fetch_budget_below_one_sample_per_channel_refused(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    scope.dispatch(
        _invoke("otdp.oscilloscope.trigger/1.0.0", {"acquisition_id": "acq-1"}),
        deadline_ns=10**12,
    )
    refused = _fetch(scope, 8, True)
    assert refused.status.value == "error"
    assert refused.error.code.value == "DEVICE_REJECTED"


def test_fetch_started_at_is_the_arm_time() -> None:
    class AdvancingClock(Clock):
        """iso() moves with advance() so arm-time and fetch-time differ."""

        def __init__(self) -> None:
            super().__init__()
            self.stamp = NOW

        def advance(self, ns: int) -> None:
            super().advance(ns)
            self.stamp = "2026-09-19T00:00:05Z"

        def iso(self) -> str:
            return self.stamp

    clock = AdvancingClock()
    plugin = make_sim_scope(clock)
    plugin.plugin_open(NullServices())
    _configure_edge(plugin)
    _arm(plugin)
    clock.advance(5_000_000_000)
    result = _fetch(plugin, 1_048_576, True)
    assert result.status.value == "ok"
    assert result.data["result"]["started_at"] == NOW
    plugin.plugin_close()


def test_fetch_dataset_ids_are_unique_per_fetch(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    first = _fetch(scope, 1_048_576, True)
    second = _fetch(scope, 1_048_576, True)
    assert first.data["result"]["dataset_id"] != second.data["result"]["dataset_id"]


def test_fetch_dataset_matches_otdp_schema(scope: Any) -> None:
    import json as _json

    from jsonschema import Draft202012Validator

    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    result = _fetch(scope, 1_048_576, True)
    schema = _json.loads(
        (Path(__file__).resolve().parents[2] / "standards/otdp/0.1.1/otdp-measurement.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(result.data["result"])
