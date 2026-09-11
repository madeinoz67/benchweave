"""sim_psu — the first simulator plugin (WP04 S2).

A stateful simulated DC supply implementing the published host ABI:
finite hard bounds, OVP/OCP trip latch cleared only by reset, typed
readings, dispatch-state-honest errors. Deterministic — time is injected.
Simulation is visibly identified (SimulationInfo + benchweave-sim identity).
"""

from __future__ import annotations

from collections.abc import Callable

from benchweave.host import (
    Assurance,
    DeviceErrors,
    DispatchState,
    ErrorCode,
    ErrorEntry,
    HostServices,
    Identity,
    IdentitySource,
    OperationRequest,
    OperationResult,
    OperationVerb,
    Quality,
    Reading,
    ReadingSource,
    SimulationInfo,
    Value,
    WriteReceipt,
)

MAX_VOLTAGE_V = 30.0
MAX_CURRENT_A = 5.0

WRITABLE_BOUNDS: dict[str, tuple[float, float]] = {
    "voltage_setpoint_v": (0.0, MAX_VOLTAGE_V),
    "current_limit_a": (0.0, MAX_CURRENT_A),
    "ovp_threshold_v": (0.0, MAX_VOLTAGE_V),
    "ocp_threshold_a": (0.0, MAX_CURRENT_A),
    "load_a": (0.0, MAX_CURRENT_A),
}


def create_plugin(now_fn: Callable[[], str], monotonic_ns_fn: Callable[[], int]) -> SimPsuPlugin:
    return SimPsuPlugin(now_fn=now_fn, monotonic_ns_fn=monotonic_ns_fn)


class SimPsuPlugin:
    def __init__(self, now_fn: Callable[[], str], monotonic_ns_fn: Callable[[], int]) -> None:
        self._now = now_fn
        self._monotonic_ns = monotonic_ns_fn
        self._services: HostServices | None = None
        self._tripped: str | None = None
        self._error_entries: list[ErrorEntry] = []
        self._state: dict[str, Value] = {
            "output_enabled": False,
            "voltage_setpoint_v": 0.0,
            "current_limit_a": MAX_CURRENT_A,
            "ovp_threshold_v": MAX_VOLTAGE_V,
            "ocp_threshold_a": MAX_CURRENT_A,
            "load_a": 0.0,
            "operator_note": "",
        }

    @property
    def simulation(self) -> SimulationInfo:
        return SimulationInfo(simulated=True, label="sim-psu")

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
            OperationVerb.GET_ERRORS: self._get_errors,
            OperationVerb.RESET: self._reset,
        }.get(request.verb)
        if handler is None:
            return self._reject(request, ErrorCode.UNSUPPORTED, f"verb {request.verb} unsupported")
        return handler(request)

    def _identify(self, request: OperationRequest) -> OperationResult:
        identity = Identity(
            manufacturer="benchweave-sim",
            model="sim-psu-1",
            serial="SIM-PSU-0001",
            firmware="sim-0.1.0",
            source=IdentitySource.DEVICE,
        )
        return OperationResult.ok(request.operation_id, request.verb, identity)

    def _reading(self, parameter: str, value: Value | None, unit: str | None) -> Reading:
        return Reading(
            parameter=parameter,
            value=value,
            unit=unit,
            observed_at=self._now(),
            age_ms=0,
            quality=Quality.VALID,
            source=ReadingSource.DEVICE,
        )

    def _read(self, request: OperationRequest) -> OperationResult:
        parameter = request.arguments.get("parameter")
        if not isinstance(parameter, str):
            return self._reject(request, ErrorCode.INVALID_ARGUMENT, "read requires parameter")
        derived: dict[str, tuple[Value | None, str | None]] = {
            "output_voltage_v": (self._output_voltage(), "V"),
            "output_current_a": (self._output_current(), "A"),
            "output_power_w": (
                round(self._output_voltage() * self._output_current(), 6),
                "W",
            ),
            "identity_model": ("sim-psu-1", None),
        }
        if parameter in derived:
            value, unit = derived[parameter]
            reading = self._reading(parameter, value, unit)
            return OperationResult.ok(request.operation_id, request.verb, reading)
        if parameter in self._state:
            reading = self._reading(parameter, self._state[parameter], None)
            return OperationResult.ok(request.operation_id, request.verb, reading)
        return self._reject(request, ErrorCode.INVALID_ARGUMENT, f"unknown parameter {parameter}")

    def _output_voltage(self) -> float:
        if self._tripped or not self._state["output_enabled"]:
            return 0.0
        return float(self._state["voltage_setpoint_v"])

    def _output_current(self) -> float:
        if self._tripped or not self._state["output_enabled"]:
            return 0.0
        return min(float(self._state["load_a"]), float(self._state["current_limit_a"]))

    def _write(self, request: OperationRequest) -> OperationResult:
        parameter = request.arguments.get("parameter")
        value = request.arguments.get("value")
        if not isinstance(parameter, str) or "value" not in request.arguments:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "write requires parameter and value"
            )
        if parameter not in self._state:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, f"unknown parameter {parameter}"
            )
        if self._tripped:
            return self._reject(
                request, ErrorCode.DEVICE_REJECTED, f"tripped ({self._tripped}); reset required"
            )
        if parameter in WRITABLE_BOUNDS:
            low, high = WRITABLE_BOUNDS[parameter]
            in_bounds = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and low <= value <= high
            )
            if not in_bounds:
                return self._reject(
                    request,
                    ErrorCode.DEVICE_REJECTED,
                    f"{parameter} out of bounds [{low}, {high}]",
                )
        if parameter == "output_enabled" and not isinstance(value, bool):
            return self._reject(request, ErrorCode.INVALID_ARGUMENT, "output_enabled is boolean")
        if parameter == "operator_note" and not isinstance(value, str):
            return self._reject(request, ErrorCode.INVALID_ARGUMENT, "operator_note is a string")
        typed_value = self._coerce(parameter, value)
        if typed_value is None:
            return self._reject(request, ErrorCode.INVALID_ARGUMENT, f"bad type for {parameter}")
        self._state[parameter] = typed_value
        trip = self._check_trips(parameter)
        if trip is not None:
            return self._reject(
                request, ErrorCode.DEVICE_REJECTED, f"protective trip: {trip}"
            )
        receipt = WriteReceipt(
            parameter=parameter,
            requested_value=typed_value,
            effective_value=self._state[parameter],
            assurance=Assurance.DISPATCHED,
            verification=self._reading(parameter, self._state[parameter], None)
            if parameter in WRITABLE_BOUNDS
            else None,
        )
        return OperationResult.ok(request.operation_id, request.verb, receipt)

    def _coerce(self, parameter: str, value: object) -> Value | None:
        if parameter == "output_enabled":
            return value if isinstance(value, bool) else None
        if parameter == "operator_note":
            return value if isinstance(value, str) else None
        if parameter in WRITABLE_BOUNDS:
            if isinstance(value, bool):
                return None
            if isinstance(value, (int, float)):
                return value
            return None
        return None

    def _check_trips(self, changed: str) -> str | None:
        enabled = self._state["output_enabled"]
        if (
            enabled
            and changed in ("voltage_setpoint_v", "ovp_threshold_v", "output_enabled")
            and float(self._state["voltage_setpoint_v"]) > float(self._state["ovp_threshold_v"])
        ):
            self._trip("OVP_TRIP", "voltage setpoint above OVP threshold")
            return "OVP_TRIP"
        if (
            enabled
            and changed in ("load_a", "ocp_threshold_a", "output_enabled", "current_limit_a")
            and float(self._state["load_a"]) > float(self._state["ocp_threshold_a"])
        ):
            self._trip("OCP_TRIP", "load above OCP threshold")
            return "OCP_TRIP"
        return None

    def _trip(self, code: str, message: str) -> None:
        self._tripped = code
        self._error_entries.append(ErrorEntry(code=code, message=message))
        self._state["output_enabled"] = False

    def _get_errors(self, request: OperationRequest) -> OperationResult:
        errors = DeviceErrors(entries=tuple(self._error_entries), more=False)
        return OperationResult.ok(request.operation_id, request.verb, errors)

    def _reset(self, request: OperationRequest) -> OperationResult:
        self._tripped = None
        self._error_entries.clear()
        self._state["output_enabled"] = False
        self._state["voltage_setpoint_v"] = 0.0
        return OperationResult.ok(
            request.operation_id, request.verb, {"acknowledged": True}
        )
