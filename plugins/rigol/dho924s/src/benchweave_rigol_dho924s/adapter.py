# author: Stephen Eaton
"""OTDP adapter API 1.1 boundary for the Rigol DHO-924S.

DOCUMENTARY, NOT HARDWARE-QUALIFIED. No instrument was connected while this
adapter was built, and every exchange it was tested against is synthetic.
See docs/device-evidence.md.

What the plugin puts on a wire: the identity query, once per ``identify``. It
is sent with the framing IEEE 488.2 defines, because the manufacturer's guide
names that standard as the basis of its command language. The framing of the
actual unit is not evidenced. With the wrong framing the query does not
complete and the operation is refused; an identity is never reported that was
not read in full.

What the plugin refuses before any I/O: every other verb. No profile is
claimed, so no class action reaches the wire.

The acquisition state machine is hardware-independent machinery. It enforces
the order of the oscilloscope class actions over an injected backend. No
backend is shipped: the SCPI for configure, arm, fetch and abort is not
evidenced for this unit. The plugin owns a machine without a backend, and it
does not route class actions to it.
"""

import asyncio
import json
import math
from collections.abc import Awaitable, Mapping
from enum import StrEnum
from typing import Any, Final, Protocol

from .client import IEEE488_2_NL, ScpiClient
from .codec import CodecError
from .descriptor import MANUFACTURER, MODEL, build_descriptor
from .session import IdentityMismatch, identify

#: The operation budget, in seconds. It is the identify policy of the
#: descriptor, a number this adapter chose. It is not a device measurement.
OPERATION_BUDGET_S: Final = 1.0
#: The largest identity reply this adapter accepts, in bytes. A protective
#: software bound this adapter chose, not a measurement of the unit.
IDN_MAX_BYTES: Final = 256

ACTION_CONFIGURE: Final = "otdp.oscilloscope.configure/1.0.0"
ACTION_ARM: Final = "otdp.oscilloscope.arm/1.0.0"
ACTION_TRIGGER: Final = "otdp.oscilloscope.trigger/1.0.0"
ACTION_FETCH: Final = "otdp.oscilloscope.fetch/1.0.0"
ACTION_ABORT: Final = "otdp.oscilloscope.abort/1.0.0"
#: Every action of the oscilloscope class: four base actions and the optional trigger.
OSCILLOSCOPE_ACTIONS: Final[tuple[str, ...]] = (
    ACTION_CONFIGURE,
    ACTION_ARM,
    ACTION_TRIGGER,
    ACTION_FETCH,
    ACTION_ABORT,
)

_VERBS: Final[frozenset[str]] = frozenset(
    {
        "identify",
        "read",
        "write",
        "self_test",
        "get_errors",
        "capture",
        "stream_subscribe",
        "stream_unsubscribe",
        "reset",
        "invoke",
    }
)
#: The error codes whose outcome after dispatch is indeterminate.
_INDETERMINATE: Final[frozenset[str]] = frozenset({"TIMEOUT", "CANCELLED", "TRANSPORT_ERROR"})


class OperationContext(Protocol):
    operation_id: str
    dataset_id: str | None
    deadline_monotonic: float

    def is_cancelled(self) -> bool: ...

    async def mark_dispatch_started(self) -> None: ...


class HostServices(Protocol):
    """The subset of specification section 8 services this adapter uses."""

    def monotonic(self) -> float: ...

    async def transfer(
        self, transaction: dict[str, Any], context: OperationContext
    ) -> dict[str, Any]: ...

    async def close_transport(self, context: OperationContext) -> None: ...


class _HostContractError(RuntimeError):
    """The host answered a scoped transfer with a result the grammar does not allow."""


def _remaining(services: HostServices, context: OperationContext, deadline: float) -> float:
    """Seconds left before the deadline; cancellation and a passed deadline raise."""
    if context.is_cancelled():
        raise asyncio.CancelledError
    now = services.monotonic()
    if not math.isfinite(now) or not math.isfinite(deadline):
        raise ValueError("Invalid host clock or deadline")
    remaining = deadline - now
    if remaining <= 0:
        raise TimeoutError
    return remaining


class _Scope:
    """Per-execute transport bridge; never retained on the plugin instance.

    It satisfies the client's ``Transport`` contract: one send is one complete
    command, and one receive is one complete reply as the host framed it.
    """

    def __init__(
        self,
        services: HostServices,
        context: OperationContext,
        deadline: float,
        termination: str,
    ) -> None:
        self.services = services
        self.context = context
        self.deadline = deadline
        self.termination = termination
        self.marked = False
        self.dispatch_state = "not_dispatched"

    def remaining(self) -> float:
        return _remaining(self.services, self.context, self.deadline)

    async def send(self, data: bytes) -> None:
        self.remaining()
        if not self.marked:
            # Dispatch intent is recorded once, before the first transmission.
            await self.context.mark_dispatch_started()
            self.marked = True
        self.remaining()
        self.dispatch_state = "unknown"
        result = await self.services.transfer({"kind": "stream_send", "data": data}, self.context)
        self.dispatch_state = "dispatched"
        self.remaining()
        if result != {}:
            raise _HostContractError("Invalid host send response")

    async def receive(self, max_bytes: int) -> bytes:
        self.remaining()
        result = await self.services.transfer(
            {
                "kind": "stream_receive",
                "max_bytes": max_bytes,
                "termination": self.termination,
                "exact_bytes": None,
            },
            self.context,
        )
        self.remaining()
        if not isinstance(result, dict) or set(result) != {"data"}:
            raise _HostContractError("Invalid host receive response")
        data = result["data"]
        if type(data) is not bytes or len(data) > max_bytes:
            raise _HostContractError("Host receive did not return bounded bytes")
        return data


class AcquisitionState(StrEnum):
    IDLE = "idle"
    CONFIGURED = "configured"
    ARMED = "armed"
    FETCHED = "fetched"
    FAULTED = "faulted"


class AcquisitionBackend(Protocol):
    """The device operations an acquisition needs. No implementation is shipped.

    Each method is one device exchange. ``apply`` returns the effective
    configuration as the device read it back. ``stop`` returns only once the
    acquisition is confirmed stopped.
    """

    async def apply(self, configuration: Mapping[str, object]) -> Mapping[str, object]: ...

    async def start(self, acquisition_id: str, max_duration_ms: int) -> None: ...

    async def read(self, acquisition_id: str) -> object: ...

    async def stop(self, acquisition_id: str) -> None: ...


def _result(operation_id: str, action_id: str, result: object) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "verb": "invoke",
        "status": "ok",
        "data": {"action_id": action_id, "result": result},
    }


def _refusal(operation_id: str, code: str, message: str) -> dict[str, Any]:
    """The class refusal shape: a typed error, and nothing was dispatched.

    A request outside what the device supports, or outside the order of the
    class actions, is refused before any device contact.
    """
    return {
        "operation_id": operation_id,
        "verb": "invoke",
        "status": "error",
        "error": {"code": code, "message": message, "dispatch_state": "not_dispatched"},
    }


class AcquisitionMachine:
    """The order of the oscilloscope class actions, over an injected backend.

    ``IDLE -> CONFIGURED -> ARMED -> FETCHED``. ``abort`` from ``ARMED``
    returns to ``IDLE``. The machine never substitutes one trigger kind for
    another: a kind outside ``supported_trigger_kinds`` is refused and the
    state does not change.

    A backend call that fails leaves the state unknown. The machine then
    refuses every action: the outcome on the device is not known, and a fresh
    instance is required. It never retries.
    """

    def __init__(
        self, *, backend: AcquisitionBackend | None, supported_trigger_kinds: frozenset[str]
    ) -> None:
        if type(supported_trigger_kinds) is not frozenset:
            raise ValueError("supported_trigger_kinds must be a frozenset")
        if "software" in supported_trigger_kinds:
            raise ValueError(
                "the software trigger kind needs the optional trigger action, "
                "which this adapter does not implement"
            )
        self._backend = backend
        self._supported_trigger_kinds = supported_trigger_kinds
        self._state = AcquisitionState.IDLE
        self._configuration_id: str | None = None
        self._acquisition_id: str | None = None

    @property
    def state(self) -> AcquisitionState:
        return self._state

    @property
    def backend(self) -> AcquisitionBackend | None:
        return self._backend

    @property
    def supported_trigger_kinds(self) -> frozenset[str]:
        return self._supported_trigger_kinds

    async def _run[T](self, operation: Awaitable[T]) -> T:
        """Await one backend call; any failure leaves the state unknown."""
        try:
            return await operation
        except BaseException:
            self._state = AcquisitionState.FAULTED
            raise

    def _blocked(self, operation_id: str) -> dict[str, Any] | None:
        if self._state is AcquisitionState.FAULTED:
            return _refusal(
                operation_id,
                "TRANSPORT_ERROR",
                "the acquisition state is unknown after a failed device exchange; "
                "a fresh instance is required",
            )
        return None

    def _no_backend(self, operation_id: str) -> dict[str, Any]:
        return _refusal(
            operation_id, "UNSUPPORTED", "no acquisition backend is evidenced for this unit"
        )

    def _unknown_acquisition(self, operation_id: str, acquisition_id: object) -> dict[str, Any]:
        return _refusal(operation_id, "INVALID_ARGUMENT", f"unknown acquisition {acquisition_id!r}")

    async def configure(
        self,
        operation_id: str,
        *,
        configuration_id: str,
        trigger_kind: str,
        settings: Mapping[str, object],
    ) -> dict[str, Any]:
        """Apply one configuration and return the configuration the device read back."""
        refusal = self._blocked(operation_id)
        if refusal is not None:
            return refusal
        backend = self._backend
        if backend is None:
            return self._no_backend(operation_id)
        if self._state is AcquisitionState.ARMED:
            return _refusal(
                operation_id,
                "DEVICE_REJECTED",
                "a live acquisition is armed; abort it before a new configuration",
            )
        if type(trigger_kind) is not str or trigger_kind not in self._supported_trigger_kinds:
            supported = sorted(self._supported_trigger_kinds)
            return _refusal(
                operation_id,
                "INVALID_ARGUMENT",
                f"trigger kind {trigger_kind!r} is not evidenced for this unit; "
                f"evidenced kinds: {supported}",
            )
        if type(configuration_id) is not str or not configuration_id:
            return _refusal(
                operation_id, "INVALID_ARGUMENT", "configure requires a configuration_id"
            )
        if not isinstance(settings, Mapping):
            return _refusal(
                operation_id, "INVALID_ARGUMENT", "configure requires a settings object"
            )
        configuration = {
            "configuration_id": configuration_id,
            "trigger_kind": trigger_kind,
            "settings": dict(settings),
        }
        effective = await self._run(backend.apply(configuration))
        self._configuration_id = configuration_id
        self._acquisition_id = None
        self._state = AcquisitionState.CONFIGURED
        return _result(
            operation_id,
            ACTION_CONFIGURE,
            {"configuration_id": configuration_id, "effective_configuration": dict(effective)},
        )

    async def arm(
        self,
        operation_id: str,
        *,
        configuration_id: str,
        acquisition_id: str,
        max_duration_ms: int,
    ) -> dict[str, Any]:
        """Arm one acquisition of the stored configuration."""
        refusal = self._blocked(operation_id)
        if refusal is not None:
            return refusal
        backend = self._backend
        if backend is None:
            return self._no_backend(operation_id)
        if self._configuration_id is None:
            return _refusal(
                operation_id, "DEVICE_REJECTED", "no configuration is stored; configure before arm"
            )
        if configuration_id != self._configuration_id:
            return _refusal(
                operation_id,
                "DEVICE_REJECTED",
                f"configuration_id {configuration_id!r} does not match the stored configuration",
            )
        if self._state is AcquisitionState.ARMED:
            return _refusal(
                operation_id,
                "DEVICE_REJECTED",
                f"an acquisition is already armed as {self._acquisition_id!r}; "
                "abort it before another arm",
            )
        if type(acquisition_id) is not str or not acquisition_id:
            return _refusal(operation_id, "INVALID_ARGUMENT", "arm requires an acquisition_id")
        if type(max_duration_ms) is not int or max_duration_ms < 1:
            return _refusal(
                operation_id, "INVALID_ARGUMENT", "arm requires a positive max_duration_ms"
            )
        await self._run(backend.start(acquisition_id, max_duration_ms))
        self._acquisition_id = acquisition_id
        self._state = AcquisitionState.ARMED
        return _result(
            operation_id, ACTION_ARM, {"acquisition_id": acquisition_id, "state": "armed"}
        )

    def _live(self, acquisition_id: object) -> bool:
        return self._state is AcquisitionState.ARMED and acquisition_id == self._acquisition_id

    async def fetch(self, operation_id: str, *, acquisition_id: str) -> dict[str, Any]:
        """Read the data of the armed acquisition. Fetching does not re-trigger."""
        refusal = self._blocked(operation_id)
        if refusal is not None:
            return refusal
        backend = self._backend
        if backend is None:
            return self._no_backend(operation_id)
        if not self._live(acquisition_id):
            return self._unknown_acquisition(operation_id, acquisition_id)
        dataset = await self._run(backend.read(acquisition_id))
        self._acquisition_id = None
        self._state = AcquisitionState.FETCHED
        return _result(operation_id, ACTION_FETCH, dataset)

    async def abort(self, operation_id: str, *, acquisition_id: str) -> dict[str, Any]:
        """Stop the armed acquisition and return to idle once the stop is confirmed."""
        refusal = self._blocked(operation_id)
        if refusal is not None:
            return refusal
        backend = self._backend
        if backend is None:
            return self._no_backend(operation_id)
        if not self._live(acquisition_id):
            return self._unknown_acquisition(operation_id, acquisition_id)
        await self._run(backend.stop(acquisition_id))
        self._acquisition_id = None
        self._configuration_id = None
        self._state = AcquisitionState.IDLE
        return _result(
            operation_id, ACTION_ABORT, {"acquisition_id": acquisition_id, "state": "aborted"}
        )


class DevicePlugin:
    """One scoped connection, one active operation, failed for good after ambiguity."""

    def __init__(self) -> None:
        self._services: HostServices | None = None
        self._opened = False
        self._closed = False
        self._failed = False
        self._busy = False
        self.acquisition = AcquisitionMachine(backend=None, supported_trigger_kinds=frozenset())

    async def open(
        self, descriptor: dict[str, Any], services: HostServices, context: OperationContext
    ) -> None:
        """Attach the scoped services. Sends nothing."""
        if self._services is not None or self._closed:
            raise RuntimeError("A fresh plugin instance is required")
        # Retain only services, so even a failed admission permits a bounded close.
        self._services = services
        _remaining(services, context, context.deadline_monotonic)
        if json.dumps(descriptor, sort_keys=True, allow_nan=False) != json.dumps(
            build_descriptor(), sort_keys=True, allow_nan=False
        ):
            raise ValueError("Descriptor differs from the reviewed adapter contract")
        self._opened = True

    async def execute(self, request: dict[str, Any], context: OperationContext) -> dict[str, Any]:
        # Missing envelope identity cannot be turned into a valid correlated result.
        if not isinstance(request, dict):
            raise ValueError("Invalid runtime envelope identity")
        operation_id, verb = request.get("operation_id"), request.get("verb")
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or not isinstance(verb, str)
            or verb not in _VERBS
        ):
            raise ValueError("Invalid runtime envelope identity")
        base: dict[str, Any] = {"operation_id": operation_id, "verb": verb}

        def failure(code: str, message: str, dispatch: str = "not_dispatched") -> dict[str, Any]:
            # Specification section 5. A failure after dispatch is `error` when
            # the reply was read and judged, and `unknown` only when the
            # outcome is indeterminate: a timeout, a cancellation or a lost link.
            if dispatch == "not_dispatched":
                status = "cancelled" if code == "CANCELLED" else "error"
            else:
                status = "unknown" if code in _INDETERMINATE else "error"
            return {
                **base,
                "status": status,
                "error": {"code": code, "message": message, "dispatch_state": dispatch},
            }

        if operation_id != context.operation_id or set(request) != {
            "operation_id",
            "verb",
            "arguments",
        }:
            return failure("INVALID_ARGUMENT", "Invalid request envelope or context identity")
        if verb != "identify":
            return failure("UNSUPPORTED", "Operation is not advertised")
        arguments = request["arguments"]
        if not isinstance(arguments, dict) or arguments:
            return failure("INVALID_ARGUMENT", "Invalid arguments for advertised operation")
        if not self._opened or self._closed or self._failed or self._services is None:
            return failure("TRANSPORT_ERROR", "A fresh commissioned session is required")
        if self._busy:
            return failure("RESOURCE_LIMIT", "An operation is already active")
        services = self._services
        scope = _Scope(
            services,
            context,
            min(context.deadline_monotonic, services.monotonic() + OPERATION_BUDGET_S),
            IEEE488_2_NL.read_termination,
        )
        self._busy = True
        succeeded = False
        try:
            async with asyncio.timeout(scope.remaining()):
                client = ScpiClient(scope, framing=IEEE488_2_NL)
                identity = await identify(
                    client,
                    manufacturer=MANUFACTURER,
                    model=MODEL,
                    timeout=scope.remaining(),
                    max_bytes=IDN_MAX_BYTES,
                )
                scope.remaining()
                data = {
                    "manufacturer": identity.manufacturer,
                    "model": identity.model,
                    "serial": identity.serial,
                    "firmware": identity.firmware,
                    "source": "device",
                }
            succeeded = True
            return {**base, "status": "ok", "data": data}
        except asyncio.CancelledError:
            return failure(
                "CANCELLED", "Operation cancelled; no rollback implied", scope.dispatch_state
            )
        except TimeoutError:
            return failure("TIMEOUT", "Operation deadline expired", scope.dispatch_state)
        except IdentityMismatch:
            return failure(
                "IDENTITY_MISMATCH",
                f"Device model does not match the committed model {MODEL!r}",
                scope.dispatch_state,
            )
        except CodecError:
            return failure(
                "PROTOCOL_ERROR", "Malformed or uncorrelated response", scope.dispatch_state
            )
        except ConnectionError:
            return failure("TRANSPORT_ERROR", "Scoped transport failed", scope.dispatch_state)
        except ValueError:
            return failure(
                "INVALID_ARGUMENT", "Host rejected transaction or metadata", scope.dispatch_state
            )
        except Exception:
            return failure("INTERNAL_ERROR", "Adapter or scoped host failure", scope.dispatch_state)
        finally:
            if not succeeded and scope.dispatch_state != "not_dispatched":
                self._failed = True
            self._busy = False

    async def next_event(
        self, subscription_id: str, context: OperationContext
    ) -> dict[str, Any] | None:
        """No streaming capability exists, so there is never an event and no I/O."""
        return None

    async def close(self, context: OperationContext) -> None:
        """Bounded and idempotent. Sends no device command."""
        if self._closed:
            return
        if self._busy:
            raise RuntimeError("Cancel and await the active operation before close")
        self._failed = True
        if self._services is not None:
            remaining = _remaining(self._services, context, context.deadline_monotonic)
            async with asyncio.timeout(min(remaining, OPERATION_BUDGET_S)):
                await self._services.close_transport(context)
                _remaining(self._services, context, context.deadline_monotonic)
        self._closed = True
        self._opened = False
        self._services = None


def create_plugin() -> DevicePlugin:
    """Construct a fresh instance without I/O and without a hardware backend."""
    return DevicePlugin()
