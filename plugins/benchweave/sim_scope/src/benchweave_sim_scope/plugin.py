"""sim_scope — deterministic four-channel oscilloscope simulator (issue #6 row A).

The settings-presets proof vehicle: a plugin whose named measurement setups
ship as ui/presets documents. Implements all five otdp.oscilloscope/1.0.0
profile actions over INVOKE, applies per-channel coupling/range/offset/probe
through the parameter write path (the sim_psu `_write_parameter` re-homing
pattern), and keeps channel enablement behaviorally real — fetch covers the
channels the last configure named, nothing else.

The descriptor's declared parameter envelope is this plugin's validation
contract: a write outside it never reached a device, so it is refused
INVALID_ARGUMENT/NOT_DISPATCHED rather than DEVICE_REJECTED (sim_psu's
DEVICE_REJECTED is its physical-trip posture; this plugin has no trips).
Deterministic — time is injected. Simulation is visibly identified.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from benchweave.host import (
    Assurance,
    DispatchState,
    ErrorCode,
    HostServices,
    Identity,
    IdentitySource,
    OperationRequest,
    OperationResult,
    OperationStatus,
    OperationVerb,
    Quality,
    Reading,
    ReadingSource,
    SimulationInfo,
    Value,
    WriteReceipt,
)

CHANNELS = ("ch1", "ch2", "ch3", "ch4")
PROBE_RATIOS = (1.0, 10.0, 20.0, 50.0)
OFFSET_LIMIT_V = 10.0
RANGE_MIN_V = 0.001
RANGE_MAX_V = 10.0
AVERAGING_MIN = 1
AVERAGING_MAX = 64
SAMPLE_RATE_MAX_HZ = 1_000_000.0
SAMPLE_COUNT_MAX = 1_000_000
COUPLINGS = ("ac", "dc", "ground")
TRIGGER_KINDS = ("immediate", "software", "external", "edge")

ACTION_CONFIGURE = "otdp.oscilloscope.configure/1.0.0"
ACTION_ARM = "otdp.oscilloscope.arm/1.0.0"
ACTION_TRIGGER = "otdp.oscilloscope.trigger/1.0.0"
ACTION_FETCH = "otdp.oscilloscope.fetch/1.0.0"
ACTION_ABORT = "otdp.oscilloscope.abort/1.0.0"

# Channel action input field -> device parameter (applied through the write
# path so a configure refuses exactly where the equivalent raw write would).
CHANNEL_FIELDS: tuple[tuple[str, str], ...] = (
    ("probe_ratio", "{channel}_probe_ratio"),
    ("offset_v", "{channel}_offset_v"),
    ("range_v", "{channel}_range_v"),
    ("coupling", "{channel}_coupling"),
)


def _numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class SimScopePlugin:
    def __init__(self, now_fn: Callable[[], str], monotonic_ns_fn: Callable[[], int]) -> None:
        self._now = now_fn
        self._monotonic_ns = monotonic_ns_fn
        self._services: HostServices | None = None
        self._configuration_id: str | None = None
        self._acquisitions: dict[str, dict[str, Any]] = {}
        self._channels: dict[str, dict[str, Value]] = {
            channel: {
                "probe_ratio": 1.0,
                "offset_v": 0.0,
                "range_v": 10.0,
                "coupling": "dc",
            }
            for channel in CHANNELS
        }
        self._enabled: list[str] = []
        self._state: dict[str, Value] = {"averaging_count": 4, "identity_model": "sim-scope-1"}
        self._acquisition_shape: dict[str, Any] = {
            "sample_rate_hz": 1000.0,
            "sample_count": 1024,
            "pretrigger_fraction": 0.0,
            "trigger": {"kind": "immediate"},
        }

    @property
    def simulation(self) -> SimulationInfo:
        return SimulationInfo(simulated=True, label="sim-scope")

    def plugin_open(self, services: HostServices) -> None:
        self._services = services

    def plugin_close(self) -> None:
        self._services = None

    def _reject(
        self, request: OperationRequest, code: ErrorCode, message: str
    ) -> OperationResult:
        return OperationResult.failure(
            request.operation_id,
            request.verb,
            code=code,
            message=message,
            dispatch_state=DispatchState.NOT_DISPATCHED,
        )

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        if self._monotonic_ns() >= deadline_ns:
            return self._reject(request, ErrorCode.TIMEOUT, "deadline already passed")
        if self._services is None:
            return self._reject(request, ErrorCode.INTERNAL_ERROR, "plugin not opened")
        handler = {
            OperationVerb.IDENTIFY: self._identify,
            OperationVerb.READ: self._read,
            OperationVerb.WRITE: self._write,
            OperationVerb.INVOKE: self._invoke,
        }.get(request.verb)
        if handler is None:
            return self._reject(request, ErrorCode.UNSUPPORTED, f"verb {request.verb} unsupported")
        return handler(request)

    def _identify(self, request: OperationRequest) -> OperationResult:
        identity = Identity(
            manufacturer="benchweave-sim",
            model="sim-scope-1",
            serial="SIM-SCOPE-0001",
            firmware="sim-1.0.0",
            source=IdentitySource.DEVICE,
        )
        return OperationResult.ok(request.operation_id, request.verb, identity)

    def _reading(self, parameter: str, value: Value | None) -> Reading:
        return Reading(
            parameter=parameter,
            value=value,
            unit=None,
            observed_at=self._now(),
            age_ms=0,
            quality=Quality.VALID,
            source=ReadingSource.DEVICE,
        )

    def _read(self, request: OperationRequest) -> OperationResult:
        parameter = request.arguments.get("parameter")
        if not isinstance(parameter, str):
            return self._reject(request, ErrorCode.INVALID_ARGUMENT, "read requires parameter")
        if parameter in self._state:
            reading = self._reading(parameter, self._state[parameter])
            return OperationResult.ok(request.operation_id, request.verb, reading)
        channel, _, field = parameter.partition("_")
        if channel in self._channels and field in self._channels[channel]:
            reading = self._reading(parameter, self._channels[channel][field])
            return OperationResult.ok(request.operation_id, request.verb, reading)
        return self._reject(request, ErrorCode.INVALID_ARGUMENT, f"unknown parameter {parameter}")

    def _validate(self, parameter: str, value: object) -> str | None:
        """Return a refusal message when a value is outside the declared envelope."""
        if parameter == "averaging_count":
            if not _numeric(value) or not AVERAGING_MIN <= value <= AVERAGING_MAX:  # type: ignore[operator]
                return f"{parameter} must be an integer in [{AVERAGING_MIN}, {AVERAGING_MAX}]"
            if isinstance(value, float) and not value.is_integer():
                return f"{parameter} must be an integer in [{AVERAGING_MIN}, {AVERAGING_MAX}]"
            return None
        if parameter == "identity_model":
            return "identity_model is read-only"
        channel, _, field = parameter.partition("_")
        settings = self._channels.get(channel)
        if settings is None or field not in settings:
            return f"unknown parameter {parameter}"
        if field == "coupling":
            if value not in COUPLINGS:
                return f"{parameter} must be one of {COUPLINGS}"
            return None
        if field == "probe_ratio":
            if not _numeric(value) or value not in PROBE_RATIOS:  # type: ignore[operator]
                return f"{parameter} must be one of {PROBE_RATIOS}"
            return None
        low, high = (-OFFSET_LIMIT_V, OFFSET_LIMIT_V) if field == "offset_v" else (
            RANGE_MIN_V,
            RANGE_MAX_V,
        )
        if not _numeric(value) or not low <= value <= high:  # type: ignore[operator]
            return f"{parameter} out of bounds [{low}, {high}]"
        return None

    def _typed(self, parameter: str, value: object) -> Value:
        if parameter == "averaging_count":
            return int(value) if isinstance(value, float) else value  # type: ignore[return-value]
        if parameter.endswith("_coupling"):
            return value if isinstance(value, str) else ""
        return float(value) if isinstance(value, int) else value  # type: ignore[return-value]

    def _write(self, request: OperationRequest) -> OperationResult:
        parameter = request.arguments.get("parameter")
        value = request.arguments.get("value")
        if not isinstance(parameter, str) or "value" not in request.arguments:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "write requires parameter and value"
            )
        refusal = self._validate(parameter, value)
        if refusal is not None:
            return self._reject(request, ErrorCode.INVALID_ARGUMENT, refusal)
        typed_value = self._typed(parameter, value)
        channel, _, field = parameter.partition("_")
        if channel in self._channels and field in self._channels[channel]:
            self._channels[channel][field] = typed_value
        else:
            self._state[parameter] = typed_value
        receipt = WriteReceipt(
            parameter=parameter,
            requested_value=typed_value,
            effective_value=typed_value,
            assurance=Assurance.DISPATCHED,
            verification=self._reading(parameter, typed_value),
        )
        return OperationResult.ok(request.operation_id, request.verb, receipt)

    def _write_parameter(
        self, request: OperationRequest, parameter: str, value: object
    ) -> OperationResult:
        """Apply one write through the full write path, re-homed to the invoke.

        Failures are reported DISPATCHED: by the time an inner write fails, the
        invoke has been dispatched and earlier writes may already be applied.
        """
        write = self._write(
            OperationRequest(
                operation_id=request.operation_id,
                verb=OperationVerb.WRITE,
                arguments={"parameter": parameter, "value": value},
            )
        )
        if write.status is OperationStatus.OK:
            return write
        error = write.error
        code = error.code if error is not None else ErrorCode.INTERNAL_ERROR
        message = error.message if error is not None else "write failed without error"
        return OperationResult.failure(
            request.operation_id,
            request.verb,
            code=code,
            message=message,
            dispatch_state=DispatchState.DISPATCHED,
        )

    def _invoke(self, request: OperationRequest) -> OperationResult:
        action_id = request.arguments.get("action_id")
        action_input = request.arguments.get("input")
        if (
            not isinstance(action_id, str)
            or not action_id
            or not isinstance(action_input, dict)
        ):
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "invoke requires action_id and input"
            )
        typed_input: dict[str, Any] = action_input
        handler = {
            ACTION_CONFIGURE: self._action_configure,
            ACTION_ARM: self._action_arm,
            ACTION_TRIGGER: self._action_trigger,
            ACTION_FETCH: self._action_fetch,
            ACTION_ABORT: self._action_abort,
        }.get(action_id)
        if handler is None:
            return self._reject(request, ErrorCode.UNSUPPORTED, f"action {action_id} unsupported")
        return handler(request, typed_input)

    def _action_configure(
        self, request: OperationRequest, action_input: dict[str, Any]
    ) -> OperationResult:
        configuration_id = action_input.get("configuration_id")
        if not isinstance(configuration_id, str) or not configuration_id:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "configure requires configuration_id"
            )
        channels = action_input.get("channels")
        if not isinstance(channels, list) or not channels:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "configure requires a non-empty channels list"
            )
        seen: list[str] = []
        for item in channels:
            if not isinstance(item, dict):
                return self._reject(
                    request, ErrorCode.INVALID_ARGUMENT, "channels items must be objects"
                )
            channel = item.get("channel")
            if channel not in CHANNELS:
                return self._reject(
                    request,
                    ErrorCode.INVALID_ARGUMENT,
                    f"configure requires channels in {CHANNELS}",
                )
            if channel in seen:
                return self._reject(
                    request, ErrorCode.INVALID_ARGUMENT, f"duplicate channel {channel}"
                )
            seen.append(channel)
            for field in ("range_v", "offset_v", "probe_ratio"):
                if not _numeric(item.get(field)):
                    return self._reject(
                        request, ErrorCode.INVALID_ARGUMENT, f"configure requires numeric {field}"
                    )
            if item.get("coupling") not in COUPLINGS:
                return self._reject(
                    request, ErrorCode.INVALID_ARGUMENT, f"coupling must be one of {COUPLINGS}"
                )
            parameter = f"{channel}_probe_ratio"
            if item["probe_ratio"] not in PROBE_RATIOS:
                return self._reject(
                    request,
                    ErrorCode.INVALID_ARGUMENT,
                    f"{parameter} must be one of {PROBE_RATIOS}",
                )
            parameter = f"{channel}_range_v"
            if not RANGE_MIN_V <= item["range_v"] <= RANGE_MAX_V:
                return self._reject(
                    request,
                    ErrorCode.INVALID_ARGUMENT,
                    f"{parameter} out of bounds [{RANGE_MIN_V}, {RANGE_MAX_V}]",
                )
            parameter = f"{channel}_offset_v"
            if not -OFFSET_LIMIT_V <= item["offset_v"] <= OFFSET_LIMIT_V:
                return self._reject(
                    request,
                    ErrorCode.INVALID_ARGUMENT,
                    f"{parameter} out of bounds [{-OFFSET_LIMIT_V}, {OFFSET_LIMIT_V}]",
                )
        sample_rate_hz = action_input.get("sample_rate_hz")
        if (
            not _numeric(sample_rate_hz)
            or not 0 < sample_rate_hz <= SAMPLE_RATE_MAX_HZ  # type: ignore[operator]
        ):
            return self._reject(
                request,
                ErrorCode.INVALID_ARGUMENT,
                f"sample_rate_hz must be in (0, {SAMPLE_RATE_MAX_HZ}]",
            )
        sample_count = action_input.get("sample_count")
        if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 1:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "sample_count must be a positive integer"
            )
        if sample_count > SAMPLE_COUNT_MAX:
            return self._reject(
                request,
                ErrorCode.INVALID_ARGUMENT,
                f"sample_count exceeds the simulator ceiling of {SAMPLE_COUNT_MAX}",
            )
        pretrigger_fraction = action_input.get("pretrigger_fraction")
        if not _numeric(pretrigger_fraction) or not 0 <= pretrigger_fraction <= 1:  # type: ignore[operator]
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "pretrigger_fraction must be in [0, 1]"
            )
        # Trigger shape per the corpus action schema: dispatch is the last
        # line of validation under host-ABI use, so the closed trigger form
        # (kind set; edge requires source_channel/slope/level_v; external
        # requires source_channel) is enforced here, not only in the lanes.
        # Residual: the corpus keys beyond these (additionalProperties: false
        # on the trigger object, the source_channel naming pattern) are
        # lanes-only — dispatch does not reject unknown trigger keys or
        # oddly-named source channels.
        trigger = action_input.get("trigger")
        if not isinstance(trigger, dict) or trigger.get("kind") not in TRIGGER_KINDS:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, f"trigger kind must be one of {TRIGGER_KINDS}"
            )
        if trigger["kind"] in ("edge", "external"):
            source = trigger.get("source_channel")
            if not isinstance(source, str) or not source:
                return self._reject(
                    request,
                    ErrorCode.INVALID_ARGUMENT,
                    f"{trigger['kind']} trigger requires source_channel",
                )
        if trigger["kind"] == "edge":
            if trigger.get("slope") not in ("rising", "falling"):
                return self._reject(
                    request, ErrorCode.INVALID_ARGUMENT, "edge trigger requires a slope"
                )
            if not _numeric(trigger.get("level_v")):
                return self._reject(
                    request, ErrorCode.INVALID_ARGUMENT, "edge trigger requires numeric level_v"
                )
        for item in channels:
            for field, pattern in CHANNEL_FIELDS:
                parameter = pattern.format(channel=item["channel"])
                applied = self._write_parameter(request, parameter, item[field])
                if applied.status is not OperationStatus.OK:
                    return applied
        self._enabled = [item["channel"] for item in channels]
        self._acquisition_shape = {
            "sample_rate_hz": sample_rate_hz,
            "sample_count": sample_count,
            "pretrigger_fraction": pretrigger_fraction,
            "trigger": dict(trigger),
        }
        self._configuration_id = configuration_id
        return OperationResult.ok(
            request.operation_id,
            request.verb,
            {
                "result": {
                    "configuration_id": configuration_id,
                    "effective_configuration": {
                        "configuration_id": configuration_id,
                        "channels": channels,
                        "sample_rate_hz": sample_rate_hz,
                        "sample_count": sample_count,
                        "pretrigger_fraction": pretrigger_fraction,
                        "trigger": trigger,
                    },
                }
            },
        )

    def _action_arm(
        self, request: OperationRequest, action_input: dict[str, Any]
    ) -> OperationResult:
        configuration_id = action_input.get("configuration_id")
        if not isinstance(configuration_id, str) or configuration_id != self._configuration_id:
            return self._reject(
                request,
                ErrorCode.DEVICE_REJECTED,
                "configuration_id does not match the stored configuration",
            )
        acquisition_id = action_input.get("acquisition_id")
        if not isinstance(acquisition_id, str) or not acquisition_id:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "arm requires acquisition_id"
            )
        max_duration_ms = action_input.get("max_duration_ms")
        if (
            not isinstance(max_duration_ms, int)
            or isinstance(max_duration_ms, bool)
            or max_duration_ms < 1
        ):
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "arm requires a positive max_duration_ms"
            )
        # An immediate trigger condition is met at arm time; every other kind
        # waits for the trigger action. The acquisition start is the arm time.
        # The active configuration is snapshotted here: a later reconfigure
        # must not re-scope or re-attribute an acquisition already armed.
        shape = self._acquisition_shape
        kind = shape["trigger"].get("kind")
        state = "complete" if kind == "immediate" else "armed"
        self._acquisitions[acquisition_id] = {
            "state": state,
            "started_at": self._now(),
            "fetches": 0,
            "configuration": {
                "configuration_id": self._configuration_id,
                "enabled": list(self._enabled),
                "offsets": {
                    channel: self._channels[channel]["offset_v"] for channel in self._enabled
                },
                "shape": {
                    "sample_rate_hz": shape["sample_rate_hz"],
                    "sample_count": shape["sample_count"],
                    "pretrigger_fraction": shape["pretrigger_fraction"],
                    "trigger": dict(shape["trigger"]),
                },
            },
        }
        return OperationResult.ok(
            request.operation_id,
            request.verb,
            {"result": {"acquisition_id": acquisition_id, "state": state}},
        )

    def _action_trigger(
        self, request: OperationRequest, action_input: dict[str, Any]
    ) -> OperationResult:
        acquisition_id = action_input.get("acquisition_id")
        if not isinstance(acquisition_id, str) or acquisition_id not in self._acquisitions:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, f"unknown acquisition {acquisition_id}"
            )
        if self._acquisitions[acquisition_id]["state"] == "aborted":
            return self._reject(
                request, ErrorCode.DEVICE_REJECTED, f"acquisition {acquisition_id} was aborted"
            )
        # The operator fired the trigger; the deterministic acquisition fills
        # immediately, so the state transitions to complete.
        self._acquisitions[acquisition_id]["state"] = "complete"
        return OperationResult.ok(
            request.operation_id,
            request.verb,
            {"result": {"acquisition_id": acquisition_id, "state": "complete"}},
        )

    def _action_fetch(
        self, request: OperationRequest, action_input: dict[str, Any]
    ) -> OperationResult:
        acquisition_id = action_input.get("acquisition_id")
        if not isinstance(acquisition_id, str) or acquisition_id not in self._acquisitions:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, f"unknown acquisition {acquisition_id}"
            )
        max_bytes = action_input.get("max_bytes")
        allow_partial = action_input.get("allow_partial")
        if (
            not isinstance(max_bytes, int)
            or isinstance(max_bytes, bool)
            or max_bytes < 1
            or not isinstance(allow_partial, bool)
        ):
            return self._reject(
                request,
                ErrorCode.INVALID_ARGUMENT,
                "fetch requires a positive integer max_bytes and boolean allow_partial",
            )
        acquisition = self._acquisitions[acquisition_id]
        if acquisition["state"] == "aborted":
            return self._reject(
                request, ErrorCode.DEVICE_REJECTED, f"acquisition {acquisition_id} was aborted"
            )
        # Materialize from the snapshot taken at arm, not live state.
        snapshot = acquisition["configuration"]
        shape = snapshot["shape"]
        # Corpus dataset semantics: complete means the full requested
        # acquisition; anything missing samples is partial and records why,
        # reporting the actual axes/shapes (never padded to the request).
        samples = shape["sample_count"]
        status = "complete"
        reason: str | None = None
        if acquisition["state"] != "complete":
            if not allow_partial:
                return self._reject(
                    request,
                    ErrorCode.DEVICE_REJECTED,
                    f"acquisition {acquisition_id} is not complete and allow_partial is false",
                )
            samples = round(shape["pretrigger_fraction"] * shape["sample_count"])
            if samples < 1:
                # Zero-acquired samples is the trigger's cause, not a budget
                # cause: even an ample max_bytes cannot fetch what was never
                # acquired. Refuse naming the true reason.
                return self._reject(
                    request,
                    ErrorCode.DEVICE_REJECTED,
                    "trigger has not fired and the pretrigger buffer is empty; "
                    "no samples acquired yet",
                )
            status = "partial"
            reason = "trigger has not fired; pretrigger buffer only"
        width = 8  # float64 elements
        channels = snapshot["enabled"]
        needed = len(channels) * samples * width
        if needed > max_bytes:
            if not allow_partial:
                return self._reject(
                    request,
                    ErrorCode.DEVICE_REJECTED,
                    f"insufficient max_bytes: {needed} bytes needed, {max_bytes} given",
                )
            samples = max_bytes // (width * len(channels))
            status = "partial"
            reason = f"truncated to {samples} samples per channel by max_bytes"
        if samples < 1:
            return self._reject(
                request,
                ErrorCode.DEVICE_REJECTED,
                "max_bytes is below one sample per channel; no representable dataset",
            )
        acquisition["fetches"] += 1
        variables = [
            {
                "id": channel,
                "quantity": "voltage",
                "unit": "V",
                "channel_ids": [channel],
                "dtype": "float64",
                "dimensions": ["sample"],
                "values": [snapshot["offsets"][channel]] * samples,
                "uncertainty": {"status": "unknown"},
                "calibration": {"status": "unknown"},
                "status": "valid",
            }
            for channel in channels
        ]
        kind = shape["trigger"].get("kind", "unknown")
        dataset: dict[str, Any] = {
            "dataset_id": f"dataset-scope-{acquisition_id}-{acquisition['fetches']}",
            "kind": "waveform",
            "configuration_id": snapshot["configuration_id"],
            "acquisition_id": acquisition_id,
            "started_at": acquisition["started_at"],
            "clock": {
                "domain_id": "sim-scope",
                "timestamp_source": "device",
                "synchronisation": "unknown",
                "uncertainty_s": None,
            },
            "axes": [
                {
                    "id": "sample",
                    "quantity": "time",
                    "unit": "s",
                    "length": samples,
                    "coordinates": {
                        "kind": "regular",
                        "start": 0.0,
                        "step": 1.0 / shape["sample_rate_hz"],
                    },
                }
            ],
            "variables": variables,
            "trigger": {
                "source": kind,
                "time_relative_s": 0.0 if kind == "immediate" else None,
            },
            "status": status,
            "context": {"direction": "observed"},
        }
        if reason is not None:
            dataset["status_reason"] = reason
        return OperationResult.ok(request.operation_id, request.verb, {"result": dataset})

    def _action_abort(
        self, request: OperationRequest, action_input: dict[str, Any]
    ) -> OperationResult:
        acquisition_id = action_input.get("acquisition_id")
        if not isinstance(acquisition_id, str) or acquisition_id not in self._acquisitions:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, f"unknown acquisition {acquisition_id}"
            )
        self._acquisitions[acquisition_id]["state"] = "aborted"
        return OperationResult.ok(
            request.operation_id,
            request.verb,
            {"result": {"acquisition_id": acquisition_id, "state": "aborted"}},
        )


def create_plugin(
    now_fn: Callable[[], str], monotonic_ns_fn: Callable[[], int]
) -> SimScopePlugin:
    return SimScopePlugin(now_fn=now_fn, monotonic_ns_fn=monotonic_ns_fn)
