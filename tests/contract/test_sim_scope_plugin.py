"""sim_scope — host-ABI dispatch suite for the settings-presets proof vehicle.

Issue #6 row A: sim_scope is the first in-tree plugin whose named setups ship
as ui/presets documents. This file pins the plugin side of that claim — the
five otdp.oscilloscope profile actions over INVOKE, per-channel settings
applied through the parameter write path, and the arm configuration-token
MISMATCH check (consistent replay is out of the sim's reach — design §2.4 as
corrected in the fix wave).

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


# --- configure-carried averaging (OTDP 0.2.0, issue #64) ------------------------


def _configure_with_averaging(
    scope: Any, averaging_count: object, configuration_id: str = "cfg-1"
) -> Any:
    request = _invoke(
        "otdp.oscilloscope.configure/1.0.0",
        {
            "configuration_id": configuration_id,
            "channels": [CHANNEL_ITEM],
            "sample_rate_hz": 1000.0,
            "sample_count": 1024,
            "pretrigger_fraction": 0.0,
            "trigger": {"kind": "immediate"},
            "averaging_count": averaging_count,
        },
    )
    return scope.dispatch(request, deadline_ns=10**12)


def test_configure_applies_averaging_count_and_reads_back(scope: Any) -> None:
    """The anti-laundry control for the 0.2.0 admission: a configure-carried
    averaging_count must reach device state. READ — not the echo — is the
    proof; before the revision the plugin silently ignored the key while
    returning OK, which would have made corpus-admitted presets evidence
    laundering a no-op."""
    result = _configure_with_averaging(scope, 8)
    assert result.status.value == "ok"
    assert result.data["result"]["effective_configuration"]["averaging_count"] == 8
    read = scope.dispatch(
        OperationRequest.read("op-2", parameter="averaging_count"), deadline_ns=10**12
    )
    assert read.data.value == 8


def test_configure_refuses_averaging_out_of_envelope(scope: Any) -> None:
    """65 matches the descriptor's authored range [1, 64]: the refusal is the
    envelope's, not the corpus's (the corpus maximum is the same 64)."""
    result = _configure_with_averaging(scope, 65)
    assert result.status.value == "error"
    assert result.error.code.value == "INVALID_ARGUMENT"
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_configure_omitted_averaging_preserves_state_and_echoes_effective(scope: Any) -> None:
    """Omission is not a reset: the in-force depth survives a configure that
    does not carry the key, and the echo reports that effective depth —
    device-classes.md section 6 requires the effective configuration actually
    in force, so 16 (previously written) proves the echo reads state rather
    than parroting a constant default."""
    written = scope.dispatch(
        OperationRequest.write("op-1", parameter="averaging_count", value=16),
        deadline_ns=TICK,
    )
    assert written.status is OperationStatus.OK
    result = scope.dispatch(_configure([CHANNEL_ITEM]), deadline_ns=10**12)
    assert result.status.value == "ok"
    assert result.data["result"]["effective_configuration"]["averaging_count"] == 16
    read = scope.dispatch(
        OperationRequest.read("op-2", parameter="averaging_count"), deadline_ns=10**12
    )
    assert read.data.value == 16


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
    """Token MISMATCH is refused: arm requires the stored configuration_id.

    This is the half-substituted-apply shape — one token to configure, another
    to arm. It does not catch consistent replay (see
    test_arm_accepts_consistent_replay_documenting_the_trap); that defense is
    the apply path's job, which must substitute the gateway-issued token
    rather than replay the preset's literal one.
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
        (Path(__file__).resolve().parents[2] / "standards/otdp/0.1.2/otdp-measurement.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(result.data["result"])


def test_arm_accepts_consistent_replay_documenting_the_trap(scope: Any) -> None:
    """CONSISTENT replay passes — the trap a future apply path must not rely on.

    arm checks equality against the LAST configure's token only, so
    configure("X") then arm("X") succeeds even when X is a preset's literal
    placeholder rather than a gateway-issued token. The sim cannot defend
    against consistent replay: CTL-7's issued-key marking attaches to the
    runtime execution-contract descriptor dialect, not this full-form
    descriptor. The apply path must substitute its own issued token; if this
    test ever fails, arm grew a check that belongs upstream of the plugin.
    """
    configured = scope.dispatch(
        _configure(LOW_NOISE_PAIR, configuration_id="preset-low-noise-pair"),
        deadline_ns=10**12,
    )
    assert configured.status.value == "ok"
    replayed = scope.dispatch(
        _invoke(
            "otdp.oscilloscope.arm/1.0.0",
            {
                "configuration_id": "preset-low-noise-pair",
                "acquisition_id": "acq-replay",
                "max_duration_ms": 1000,
            },
        ),
        deadline_ns=10**12,
    )
    assert replayed.status.value == "ok"


# --- sample_count bound (fix wave R1) -------------------------------------------


def test_configure_refuses_sample_count_above_bound(scope: Any) -> None:
    """The count envelope is authored, not measured: 1e6 samples per
    acquisition (32 MB at 4 channels x float64) is the simulator's declared
    ceiling, matched by the descriptor's configure input_constraints."""
    request = _invoke(
        "otdp.oscilloscope.configure/1.0.0",
        {
            "configuration_id": "cfg-1",
            "channels": [CHANNEL_ITEM],
            "sample_rate_hz": 1000.0,
            "sample_count": 1_000_001,
            "pretrigger_fraction": 0.0,
            "trigger": {"kind": "immediate"},
        },
    )
    result = scope.dispatch(request, deadline_ns=10**12)
    assert result.status.value == "error"
    assert result.error.code.value == "INVALID_ARGUMENT"
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
    at_bound = scope.dispatch(
        _invoke(
            "otdp.oscilloscope.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channels": [CHANNEL_ITEM],
                "sample_rate_hz": 1000.0,
                "sample_count": 1_000_000,
                "pretrigger_fraction": 0.0,
                "trigger": {"kind": "immediate"},
            },
        ),
        deadline_ns=10**12,
    )
    assert at_bound.status.value == "ok"


# --- configuration snapshot at arm (fix wave R3) --------------------------------


def test_fetch_reports_the_armed_configuration_not_the_latest(scope: Any) -> None:
    """Evidence attribution: arm→reconfigure→fetch must carry the ARMED identity.

    Without a snapshot, a fetch after a reconfigure reports the new
    configuration_id and the new channel set for an acquisition that was
    armed under the old one — misattributed evidence.
    """
    scope.dispatch(_configure(LOW_NOISE_PAIR, configuration_id="cfg-1"), deadline_ns=10**12)
    assert _arm(scope, configuration_id="cfg-1", acquisition_id="acq-1").status.value == "ok"
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
    result = scope.dispatch(
        _invoke(
            "otdp.oscilloscope.fetch/1.0.0",
            {"acquisition_id": "acq-1", "max_bytes": 1_048_576, "allow_partial": False},
        ),
        deadline_ns=10**12,
    )
    assert result.status.value == "ok"
    dataset = result.data["result"]
    assert dataset["configuration_id"] == "cfg-1"
    assert [variable["channel_ids"] for variable in dataset["variables"]] == [["ch1"], ["ch3"]]


# --- trigger validation at dispatch (fix wave R5) -------------------------------


def _configure_trigger(scope: Any, trigger: dict[str, Any]) -> Any:
    return scope.dispatch(
        _invoke(
            "otdp.oscilloscope.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channels": [CHANNEL_ITEM],
                "sample_rate_hz": 1000.0,
                "sample_count": 1024,
                "pretrigger_fraction": 0.0,
                "trigger": trigger,
            },
        ),
        deadline_ns=10**12,
    )


def test_configure_refuses_edge_trigger_missing_required_subfields(scope: Any) -> None:
    result = _configure_trigger(scope, {"kind": "edge"})
    assert result.status.value == "error"
    assert result.error.code.value == "INVALID_ARGUMENT"
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED


def test_configure_refuses_unknown_trigger_kind(scope: Any) -> None:
    result = _configure_trigger(scope, {"kind": "bogus"})
    assert result.status.value == "error"
    assert result.error.code.value == "INVALID_ARGUMENT"


def test_configure_accepts_external_trigger_with_source(scope: Any) -> None:
    result = _configure_trigger(scope, {"kind": "external", "source_channel": "ch1"})
    assert result.status.value == "ok"


# --- empty pretrigger buffer refuses with the true cause (review wave 1) --------


def test_fetch_empty_pretrigger_buffer_names_the_trigger_cause(scope: Any) -> None:
    """pretrigger_fraction 0 + unfired trigger: nothing is acquired yet, and
    the refusal must name that cause — not max_bytes, which is ample."""
    result = scope.dispatch(
        _invoke(
            "otdp.oscilloscope.configure/1.0.0",
            {
                "configuration_id": "cfg-1",
                "channels": LOW_NOISE_PAIR,
                "sample_rate_hz": 1000.0,
                "sample_count": 1024,
                "pretrigger_fraction": 0.0,
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
    assert _arm(scope).status.value == "ok"
    refused = _fetch(scope, 1_048_576, True)
    assert refused.status.value == "error"
    assert refused.error.code.value == "DEVICE_REJECTED"
    assert "pretrigger" in refused.error.message
    assert "max_bytes" not in refused.error.message


# --- post-dispatch state refusals report DISPATCHED (forge wave FR1) ------------


def test_fetch_incomplete_refusal_reports_dispatched(scope: Any) -> None:
    """An invoke already dispatched into the handler that refuses on device
    state reports DISPATCHED, mirroring _write_parameter's mid-invoke
    posture — claiming not_dispatched would deny work the plugin did."""
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    refused = _fetch(scope, 1_048_576, False)
    assert refused.status.value == "error"
    assert refused.error.code.value == "DEVICE_REJECTED"
    assert refused.error.dispatch_state is DispatchState.DISPATCHED


def test_trigger_on_aborted_refusal_reports_dispatched(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    scope.dispatch(
        _invoke("otdp.oscilloscope.abort/1.0.0", {"acquisition_id": "acq-1"}),
        deadline_ns=10**12,
    )
    refused = scope.dispatch(
        _invoke("otdp.oscilloscope.trigger/1.0.0", {"acquisition_id": "acq-1"}),
        deadline_ns=10**12,
    )
    assert refused.status.value == "error"
    assert refused.error.code.value == "DEVICE_REJECTED"
    assert refused.error.dispatch_state is DispatchState.DISPATCHED


def test_fetch_on_aborted_refusal_reports_dispatched(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope).status.value == "ok"
    scope.dispatch(
        _invoke("otdp.oscilloscope.abort/1.0.0", {"acquisition_id": "acq-1"}),
        deadline_ns=10**12,
    )
    refused = _fetch(scope, 1_048_576, True)
    assert refused.status.value == "error"
    assert refused.error.code.value == "DEVICE_REJECTED"
    assert refused.error.dispatch_state is DispatchState.DISPATCHED


# --- acquisition ids are single-use (forge wave FR2) -----------------------------


def test_rearm_of_aborted_acquisition_is_refused(scope: Any) -> None:
    """arm -> abort -> arm under the same id must not resurrect the aborted
    record (its started_at, configuration snapshot and fetch count) —
    acquisition ids are single-use."""
    _configure_edge(scope)
    assert _arm(scope, acquisition_id="acq-2").status.value == "ok"
    aborted = scope.dispatch(
        _invoke("otdp.oscilloscope.abort/1.0.0", {"acquisition_id": "acq-2"}),
        deadline_ns=10**12,
    )
    assert aborted.status.value == "ok"
    resurrected = _arm(scope, acquisition_id="acq-2")
    assert resurrected.status.value == "error"
    assert resurrected.error.code.value == "DEVICE_REJECTED"
    assert "single-use" in resurrected.error.message


def test_rearm_of_live_acquisition_is_refused(scope: Any) -> None:
    _configure_edge(scope)
    assert _arm(scope, acquisition_id="acq-3").status.value == "ok"
    again = _arm(scope, acquisition_id="acq-3")
    assert again.status.value == "error"
    assert again.error.code.value == "DEVICE_REJECTED"


def test_descriptor_contract_pins_match_the_active_corpus() -> None:
    """F9 lane: the descriptor's contracts[] pins must hash the ACTIVE corpus.

    No other lane verifies a plugin descriptor's contract pins — a stale
    digest from a superseded corpus version is otherwise silent (the URN
    moves with a re-version while the digest forgets to). The pins must
    match the active-version bytes exactly.
    """

    import hashlib
    import json as _json

    descriptor_path = (
        Path(__file__).resolve().parents[2]
        / "plugins/benchweave/sim_scope/src/benchweave_sim_scope/descriptor.json"
    )
    descriptor = _json.loads(descriptor_path.read_bytes())
    active = descriptor["otdp_version"]
    for contract in descriptor["contracts"]:
        corpus = (
            Path(__file__).resolve().parents[2]
            / "standards/otdp"
            / active
            / contract["path"]
        )
        assert corpus.is_file(), f"active corpus file absent: {corpus}"
        digest = hashlib.sha256(corpus.read_bytes()).hexdigest()
        assert contract["sha256"] == digest, (
            f"{contract['id']} pins a stale digest (expected the active "
            f"{active} bytes)"
        )
