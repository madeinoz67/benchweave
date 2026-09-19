"""OTDP runtime 0.1.2 envelopes as typed Python.

Every dataclass here mirrors a ``$defs`` entry in
standards/otdp/0.1.2/otdp-runtime.schema.json, and every ``__post_init__``
invariant enforces one of that schema's conditionals in code. The contract
is the authority; this module is its Python projection. Pure: no I/O, no
clock — callers supply timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

Value = int | float | str | bool


class Quality(StrEnum):
    VALID = "valid"
    STALE = "stale"
    INVALID = "invalid"


class ReadingSource(StrEnum):
    DEVICE = "device"
    CACHE = "cache"
    COMMISSIONED = "commissioned"


class Assurance(StrEnum):
    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    READBACK = "readback"
    PHYSICAL = "physical"


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNSUPPORTED = "UNSUPPORTED"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    DEVICE_REJECTED = "DEVICE_REJECTED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    TIMEOUT = "TIMEOUT"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class DispatchState(StrEnum):
    NOT_DISPATCHED = "not_dispatched"
    DISPATCHED = "dispatched"
    UNKNOWN = "unknown"


class OperationVerb(StrEnum):
    IDENTIFY = "identify"
    READ = "read"
    WRITE = "write"
    SELF_TEST = "self_test"
    GET_ERRORS = "get_errors"
    CAPTURE = "capture"
    STREAM_SUBSCRIBE = "stream_subscribe"
    STREAM_UNSUBSCRIBE = "stream_unsubscribe"
    RESET = "reset"
    INVOKE = "invoke"


class OperationStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"


class IdentitySource(StrEnum):
    DEVICE = "device"
    COMMISSIONED = "commissioned"


@dataclass(frozen=True)
class Identity:
    manufacturer: str
    model: str
    serial: str | None
    firmware: str | None
    source: IdentitySource

    def __post_init__(self) -> None:
        if not self.manufacturer or not self.model:
            raise ValueError("identity requires manufacturer and model")


@dataclass(frozen=True)
class Reading:
    parameter: str
    value: Value | None
    unit: str | None
    observed_at: str
    age_ms: int
    quality: Quality
    source: ReadingSource

    def __post_init__(self) -> None:
        if not self.parameter:
            raise ValueError("reading requires a parameter")
        if self.age_ms < 0:
            raise ValueError("age_ms must be >= 0")


@dataclass(frozen=True)
class WriteReceipt:
    parameter: str
    requested_value: Value
    effective_value: Value | None
    assurance: Assurance
    verification: Reading | None


@dataclass(frozen=True)
class DiagnosticDetail:
    check: str
    expected: str
    actual: str


@dataclass(frozen=True)
class Diagnostic:
    verdict: str  # pass | fail | unknown
    summary: str
    details: tuple[DiagnosticDetail, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in ("pass", "fail", "unknown"):
            raise ValueError(f"unknown diagnostic verdict: {self.verdict}")
        if not self.summary:
            raise ValueError("diagnostic requires a summary")


@dataclass(frozen=True)
class ErrorEntry:
    code: str
    message: str


@dataclass(frozen=True)
class DeviceErrors:
    entries: tuple[ErrorEntry, ...]
    more: bool


@dataclass(frozen=True)
class OperationError:
    code: ErrorCode
    message: str
    dispatch_state: DispatchState

    def __post_init__(self) -> None:
        if not self.message:
            raise ValueError("error requires a message")


@dataclass(frozen=True)
class OperationRequest:
    operation_id: str
    verb: OperationVerb
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.operation_id:
            raise ValueError("request requires an operation_id")

    @classmethod
    def identify(cls, operation_id: str) -> OperationRequest:
        return cls(operation_id=operation_id, verb=OperationVerb.IDENTIFY)

    @classmethod
    def read(cls, operation_id: str, *, parameter: str) -> OperationRequest:
        return cls(
            operation_id=operation_id,
            verb=OperationVerb.READ,
            arguments={"parameter": parameter},
        )

    @classmethod
    def write(cls, operation_id: str, *, parameter: str, value: Value) -> OperationRequest:
        return cls(
            operation_id=operation_id,
            verb=OperationVerb.WRITE,
            arguments={"parameter": parameter, "value": value},
        )


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    verb: OperationVerb
    status: OperationStatus
    data: Any = None
    error: OperationError | None = None

    def __post_init__(self) -> None:
        error = self.error
        if self.status is OperationStatus.OK:
            if self.data is None:
                raise ValueError("ok result requires data")
            if error is not None:
                raise ValueError("ok result must not carry an error")
        else:
            if error is None:
                raise ValueError(f"{self.status} result requires an error")
            if self.data is not None:
                raise ValueError(f"{self.status} result must not carry data")
            if (
                self.status is OperationStatus.UNKNOWN
                and error.dispatch_state is DispatchState.NOT_DISPATCHED
            ):
                raise ValueError("unknown status cannot claim not_dispatched")

    @classmethod
    def ok(cls, operation_id: str, verb: OperationVerb, data: Any) -> OperationResult:
        return cls(operation_id=operation_id, verb=verb, status=OperationStatus.OK, data=data)

    @classmethod
    def failure(
        cls,
        operation_id: str,
        verb: OperationVerb,
        *,
        code: ErrorCode,
        message: str,
        dispatch_state: DispatchState,
    ) -> OperationResult:
        return cls(
            operation_id=operation_id,
            verb=verb,
            status=OperationStatus.ERROR,
            error=OperationError(code=code, message=message, dispatch_state=dispatch_state),
        )

    @classmethod
    def indeterminate(
        cls,
        operation_id: str,
        verb: OperationVerb,
        *,
        code: ErrorCode,
        message: str,
    ) -> OperationResult:
        return cls(
            operation_id=operation_id,
            verb=verb,
            status=OperationStatus.UNKNOWN,
            error=OperationError(
                code=code,
                message=message,
                dispatch_state=DispatchState.UNKNOWN,
            ),
        )
