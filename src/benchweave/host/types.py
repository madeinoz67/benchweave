"""OTDP runtime 0.2.0 envelopes as typed Python.

Every dataclass here mirrors a ``$defs`` entry in
standards/otdp/0.2.0/otdp-runtime.schema.json, and every ``__post_init__``
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
    """How far a reading can be trusted: ``valid`` is a fresh, in-spec
    observation; ``stale`` one that has aged past its freshness bound;
    ``invalid`` one the device or bridge knows to be wrong."""

    VALID = "valid"
    STALE = "stale"
    INVALID = "invalid"


class ReadingSource(StrEnum):
    """Where a reading's value came from: ``device`` is a live
    observation, ``cache`` an earlier observation replayed by the host,
    and ``commissioned`` a value asserted by commissioning records rather
    than measured."""

    DEVICE = "device"
    CACHE = "cache"
    COMMISSIONED = "commissioned"


class Assurance(StrEnum):
    """The write-verification ladder, weakest to strongest: ``dispatched``
    (the command left the host), ``acknowledged`` (the device accepted
    it), ``readback`` (the setting read back and matched), ``physical``
    (an independent measurement confirmed the effect). Plugins report only
    the level actually achieved, never an aspiration."""

    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    READBACK = "readback"
    PHYSICAL = "physical"


class ErrorCode(StrEnum):
    """The closed OTDP failure vocabulary. Caller faults:
    ``INVALID_ARGUMENT``, ``UNSUPPORTED``. Wrong instrument:
    ``IDENTITY_MISMATCH``. The device said no: ``DEVICE_REJECTED``. The
    wire failed: ``TRANSPORT_ERROR``, ``TIMEOUT``, ``PROTOCOL_ERROR``. Out
    of capacity: ``RESOURCE_LIMIT``. Stopped on request: ``CANCELLED``.
    Everything the plugin cannot classify: ``INTERNAL_ERROR``."""

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
    """What the device may have seen of a failed operation:
    ``not_dispatched`` — the command never left the host, retrying is
    safe; ``dispatched`` — it left, the device may have acted; ``unknown``
    — honesty after a mid-flight timeout, no claim either way. An
    ``unknown``-status result may never claim ``not_dispatched`` (enforced
    by :class:`OperationResult`)."""

    NOT_DISPATCHED = "not_dispatched"
    DISPATCHED = "dispatched"
    UNKNOWN = "unknown"


class OperationVerb(StrEnum):
    """The closed dispatch surface — every plugin operation is one of
    these ten, so hosts can reason about the whole ABI: ``identify``,
    ``read``, ``write``, ``self_test``, ``get_errors``, ``capture``,
    ``stream_subscribe``/``stream_unsubscribe``, ``reset``, and the
    profile-action escape hatch ``invoke``."""

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
    """The verdict of one dispatch: ``ok`` (data present), ``error`` (a
    definite failure with its error envelope), ``unknown`` (post-dispatch
    honesty — the outcome cannot be known), ``cancelled`` (stopped on
    request before completion)."""

    OK = "ok"
    ERROR = "error"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"


class IdentitySource(StrEnum):
    """Who asserted the identity: ``device`` — self-reported by the
    instrument; ``commissioned`` — asserted by the bench's commissioning
    record for devices that cannot report their own."""

    DEVICE = "device"
    COMMISSIONED = "commissioned"


@dataclass(frozen=True)
class Identity:
    """Who the instrument claims — or is commissioned — to be.
    Manufacturer and model are mandatory; serial and firmware are
    honest-when-known (None, never a placeholder)."""

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
    """One observed parameter value with its trust metadata: when it was
    observed, how old it was at reply time (``age_ms``), its ``Quality``
    and where it came from (``ReadingSource``)."""

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
    """The reply to a write: what was requested, what the device reports
    as in effect (None when unknowable), the ``Assurance`` level actually
    achieved, and the verifying ``Reading`` where readback happened."""

    parameter: str
    requested_value: Value
    effective_value: Value | None
    assurance: Assurance
    verification: Reading | None


@dataclass(frozen=True)
class DiagnosticDetail:
    """One self-test check line: what was checked, expected vs actual."""

    check: str
    expected: str
    actual: str


@dataclass(frozen=True)
class Diagnostic:
    """A self-test verdict (``pass`` | ``fail`` | ``unknown``) with its
    human summary and optional per-check details."""

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
    """One entry drained from the device's own error queue: the vendor's
    code and message, passed through untranslated."""

    code: str
    message: str


@dataclass(frozen=True)
class DeviceErrors:
    """A ``get_errors`` drain of the device error queue; ``more`` is True
    when entries remain undrained on the device."""

    entries: tuple[ErrorEntry, ...]
    more: bool


@dataclass(frozen=True)
class OperationError:
    """The failure half of a result: the closed ``ErrorCode``, a human
    message, and the ``DispatchState`` recording what the device may have
    seen of the attempt."""

    code: ErrorCode
    message: str
    dispatch_state: DispatchState

    def __post_init__(self) -> None:
        if not self.message:
            raise ValueError("error requires a message")


@dataclass(frozen=True)
class OperationRequest:
    """One typed dispatch request: a caller-minted ``operation_id`` (the
    correlation handle a result must echo), the verb, and its argument
    object. The classmethods build the common shapes."""

    operation_id: str
    verb: OperationVerb
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.operation_id:
            raise ValueError("request requires an operation_id")

    @classmethod
    def identify(cls, operation_id: str) -> OperationRequest:
        """An ``identify`` request (no arguments)."""
        return cls(operation_id=operation_id, verb=OperationVerb.IDENTIFY)

    @classmethod
    def read(cls, operation_id: str, *, parameter: str) -> OperationRequest:
        """A ``read`` of one named parameter."""
        return cls(
            operation_id=operation_id,
            verb=OperationVerb.READ,
            arguments={"parameter": parameter},
        )

    @classmethod
    def write(cls, operation_id: str, *, parameter: str, value: Value) -> OperationRequest:
        """A ``write`` of one named parameter to ``value``."""
        return cls(
            operation_id=operation_id,
            verb=OperationVerb.WRITE,
            arguments={"parameter": parameter, "value": value},
        )


@dataclass(frozen=True)
class OperationResult:
    """The reply envelope for one dispatch. ``__post_init__`` enforces the
    schema's conditionals: ``ok`` carries data and no error, every other
    status carries an error and no data, and ``unknown`` may never claim
    ``not_dispatched`` — indeterminacy about work that provably never left
    the host is a contradiction."""

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
        """A successful result carrying ``data``."""
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
        """A definite failure: status ``error`` with the given code,
        message and dispatch state."""
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
        """Post-dispatch honesty: status ``unknown`` with dispatch state
        ``unknown`` — the outcome cannot be known (a timeout mid-flight is
        the canonical case)."""
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
