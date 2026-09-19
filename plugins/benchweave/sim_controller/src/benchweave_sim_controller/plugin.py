"""sim_controller — the simulated DUT plugin (WP04 S3).

Numeric telemetry per the PRD: uptime in seconds plus explicit identity,
supplied as typed readings over the published host ABI. Deterministic —
time is injected; uptime advances only when the clock advances.
"""

from __future__ import annotations

from collections.abc import Callable

from benchweave.host import (
    Assurance,
    DispatchState,
    ErrorCode,
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

MAX_NOTE_LENGTH = 200


def create_plugin(
    now_fn: Callable[[], str], monotonic_ns_fn: Callable[[], int]
) -> SimControllerPlugin:
    return SimControllerPlugin(now_fn=now_fn, monotonic_ns_fn=monotonic_ns_fn)


class SimControllerPlugin:
    def __init__(self, now_fn: Callable[[], str], monotonic_ns_fn: Callable[[], int]) -> None:
        self._now = now_fn
        self._monotonic_ns = monotonic_ns_fn
        self._boot_ns = monotonic_ns_fn()
        self._services: HostServices | None = None
        self._operator_note = ""

    @property
    def simulation(self) -> SimulationInfo:
        return SimulationInfo(simulated=True, label="sim-controller")

    def plugin_open(self, services: HostServices) -> None:
        self._services = services

    def plugin_close(self) -> None:
        self._services = None

    def _reject(self, request: OperationRequest, code: ErrorCode, message: str) -> OperationResult:
        return OperationResult.failure(
            request.operation_id,
            request.verb,
            code=code,
            message=message,
            dispatch_state=DispatchState.NOT_DISPATCHED,
        )

    def _state_reject(self, request: OperationRequest, message: str) -> OperationResult:
        """Refuse on device state after dispatch, reporting DISPATCHED.

        The write reached the device and its storage limit refused it —
        claiming not_dispatched would deny work the device did. Input
        validation failures keep the NOT_DISPATCHED form via _reject.
        """
        return OperationResult.failure(
            request.operation_id,
            request.verb,
            code=ErrorCode.DEVICE_REJECTED,
            message=message,
            dispatch_state=DispatchState.DISPATCHED,
        )

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        if self._monotonic_ns() >= deadline_ns:
            return self._reject(request, ErrorCode.TIMEOUT, "deadline already passed")
        if self._services is None:
            return self._reject(request, ErrorCode.INTERNAL_ERROR, "plugin not opened")
        if request.verb is OperationVerb.IDENTIFY:
            identity = Identity(
                manufacturer="benchweave-sim",
                model="sim-controller-1",
                serial="SIM-CTL-0001",
                firmware="sim-0.1.0",
                source=IdentitySource.DEVICE,
            )
            return OperationResult.ok(request.operation_id, request.verb, identity)
        if request.verb is OperationVerb.READ:
            return self._read(request)
        if request.verb is OperationVerb.WRITE:
            return self._write(request)
        return self._reject(request, ErrorCode.UNSUPPORTED, f"verb {request.verb} unsupported")

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
        uptime_s = (self._monotonic_ns() - self._boot_ns) // 1_000_000_000
        derived: dict[str, tuple[Value | None, str | None]] = {
            "uptime_s": (int(uptime_s), "s"),
            "identity_model": ("sim-controller-1", None),
            "operator_note": (self._operator_note, None),
        }
        if parameter not in derived:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, f"unknown parameter {parameter}"
            )
        value, unit = derived[parameter]
        return OperationResult.ok(
            request.operation_id, request.verb, self._reading(parameter, value, unit)
        )

    def _write(self, request: OperationRequest) -> OperationResult:
        parameter = request.arguments.get("parameter")
        value = request.arguments.get("value")
        if not isinstance(parameter, str) or "value" not in request.arguments:
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "write requires parameter and value"
            )
        if parameter != "operator_note" or not isinstance(value, str):
            return self._reject(
                request, ErrorCode.INVALID_ARGUMENT, "only operator_note (string) is writable"
            )
        if len(value) > MAX_NOTE_LENGTH:
            return self._state_reject(
                request, f"operator_note longer than {MAX_NOTE_LENGTH}"
            )
        self._operator_note = value
        receipt = WriteReceipt(
            parameter=parameter,
            requested_value=value,
            effective_value=self._operator_note,
            assurance=Assurance.DISPATCHED,
            verification=None,
        )
        return OperationResult.ok(request.operation_id, request.verb, receipt)
