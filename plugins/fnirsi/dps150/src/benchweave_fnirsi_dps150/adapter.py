"""Read-only OTDP 0.3.0 adapter, structurally implementing the documented 1.1 ABI.

Only scoped host services perform I/O. No SDK, serial driver, background reader,
handshake, retry, reconnection, or profile assurance is implied by this adapter.
"""

import asyncio
import json
import math
import re
from datetime import datetime, timedelta
from typing import Any, Protocol

from .client import Client, GetPayload
from .codec import ProtocolError
from .descriptor import PARAMETERS, build_descriptor


class OperationContext(Protocol):
    operation_id: str
    dataset_id: str | None
    deadline_monotonic: float

    def is_cancelled(self) -> bool: ...
    async def mark_dispatch_started(self) -> None: ...


class HostServices(Protocol):
    """The subset of specification §8 services this adapter is permitted to use."""

    def monotonic(self) -> float: ...
    def utc_now(self) -> str: ...
    async def transfer(
        self, transaction: dict[str, Any], context: OperationContext
    ) -> dict[str, Any]: ...
    async def close_transport(self, context: OperationContext) -> None: ...


class _Failure(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _remaining(services: HostServices, context: OperationContext, deadline: float) -> float:
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
    """Per-execute transport bridge; never retained on the plugin instance."""

    def __init__(self, services: HostServices, context: OperationContext, deadline: float):
        self.services = services
        self.context = context
        self.deadline = deadline
        self.marked = False
        self.dispatch_state = "not_dispatched"
        self.received_monotonic = 0.0
        self.received_at = ""

    def remaining(self) -> float:
        return _remaining(self.services, self.context, self.deadline)

    async def send(self, data: bytes) -> None:
        self.remaining()
        if not self.marked:
            await self.context.mark_dispatch_started()
            self.marked = True
        self.remaining()
        self.dispatch_state = "unknown"
        result = await self.services.transfer({"kind": "stream_send", "data": data}, self.context)
        self.dispatch_state = "dispatched"
        self.remaining()
        if result != {}:
            raise ProtocolError("Invalid host send response")

    async def _exact(self, size: int) -> bytes:
        self.remaining()
        result = await self.services.transfer(
            {"kind": "stream_receive", "max_bytes": size, "termination": "lf", "exact_bytes": size},
            self.context,
        )
        self.remaining()
        if not isinstance(result, dict) or set(result) != {"data"}:
            raise ProtocolError("Invalid host receive response")
        data = result["data"]
        if type(data) is not bytes or len(data) != size:
            raise ProtocolError("Incomplete or oversized exact receive")
        return data

    async def receive(self, max_bytes: int) -> bytes:
        header = await self._exact(4)
        if header[:2] != b"\xf0\xa1" or header[3] + 5 > max_bytes:
            raise ProtocolError("Invalid frame header or length")
        body = await self._exact(header[3] + 1)
        self.received_monotonic = self.services.monotonic()
        self.received_at = self.services.utc_now()
        self.remaining()
        return header + body


class DevicePlugin:
    """One scoped connection, one active operation, permanently failed after ambiguity."""

    def __init__(self) -> None:
        self._services: HostServices | None = None
        self._opened = False
        self._closed = False
        self._failed = False
        self._busy = False
        self._identified = False

    async def open(
        self, descriptor: dict[str, Any], services: HostServices, context: OperationContext
    ) -> None:
        if self._services is not None or self._closed:
            raise RuntimeError("A fresh plugin instance is required")
        # Retain only services so even failed admission permits bounded close.
        self._services = services
        _remaining(services, context, context.deadline_monotonic)
        if json.dumps(descriptor, sort_keys=True, allow_nan=False) != json.dumps(
            build_descriptor(), sort_keys=True, allow_nan=False
        ):
            raise ValueError("Descriptor differs from the reviewed adapter contract")
        self._opened = True

    async def execute(self, request: dict[str, Any], context: OperationContext) -> dict[str, Any]:
        # Missing envelope identity cannot be turned into a valid correlated result.
        operation_id, verb = request.get("operation_id"), request.get("verb")
        verbs = {
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
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or not isinstance(verb, str)
            or verb not in verbs
        ):
            raise ValueError("Invalid runtime envelope identity")
        base: dict[str, Any] = {"operation_id": operation_id, "verb": verb}

        def failure(code: str, message: str, dispatch: str = "not_dispatched") -> dict[str, Any]:
            return {
                **base,
                "status": "unknown"
                if dispatch != "not_dispatched"
                else "cancelled"
                if code == "CANCELLED"
                else "error",
                "error": {"code": code, "message": message, "dispatch_state": dispatch},
            }

        if operation_id != context.operation_id or set(request) != {
            "operation_id",
            "verb",
            "arguments",
        }:
            return failure("INVALID_ARGUMENT", "Invalid request envelope or context identity")
        if verb not in {"identify", "read"}:
            return failure("UNSUPPORTED", "Operation is not advertised")
        arguments = request["arguments"]
        if not isinstance(arguments, dict):
            return failure("INVALID_ARGUMENT", "Arguments must be an object")
        parameter = arguments.get("parameter")
        if verb == "identify":
            valid = not arguments
        else:
            valid = (
                set(arguments) == {"parameter"}
                and isinstance(parameter, str)
                and parameter in {p[0] for p in PARAMETERS}
            )
        if not valid:
            return failure("INVALID_ARGUMENT", "Invalid arguments for advertised operation")
        if not self._opened or self._closed or self._failed or self._services is None:
            return failure("TRANSPORT_ERROR", "A fresh commissioned session is required")
        if self._busy:
            return failure("RESOURCE_LIMIT", "An operation is already active")
        if verb == "read" and not self._identified:
            return failure("IDENTITY_MISMATCH", "Identify this instance before reading")
        services = self._services
        scope = _Scope(
            services, context, min(context.deadline_monotonic, services.monotonic() + 1.0)
        )
        self._busy = True
        succeeded = False
        try:
            async with asyncio.timeout(scope.remaining()):
                client = Client(scope, get_payload=GetPayload.EMPTY)
                if verb == "identify":
                    self._identified = False
                    model = await client.read(222, timeout=scope.remaining())
                    if model != "DPS-150":
                        raise _Failure("IDENTITY_MISMATCH", "Device model does not match DPS-150")
                    firmware = await client.read(224, timeout=scope.remaining())
                    if not isinstance(firmware, str):
                        raise ProtocolError("Invalid firmware identity")
                    data: dict[str, Any] = {
                        "manufacturer": "FNIRSI",
                        "model": model,
                        "serial": None,
                        "firmware": firmware,
                        "source": "device",
                    }
                    scope.remaining()
                    self._identified = True
                else:
                    spec = next(p for p in PARAMETERS if p[0] == parameter)
                    _, field, component, kind, unit, _, choices = spec
                    value = await client.read(field, timeout=scope.remaining())
                    if component is not None:
                        if not isinstance(value, tuple):
                            raise ProtocolError("Expected voltage/current/power tuple")
                        value = value[component]
                    if kind == "float" and (type(value) is not float or not math.isfinite(value)):
                        raise ProtocolError("Invalid numeric reading")
                    if kind == "bool" and type(value) is not bool:
                        raise ProtocolError("Invalid boolean reading")
                    if kind == "enum" and value not in choices:
                        raise ProtocolError("Invalid enum reading")
                    if not re.fullmatch(
                        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)",
                        scope.received_at,
                    ):
                        raise ValueError("Host timestamp must be RFC3339 UTC")
                    timestamp = datetime.fromisoformat(scope.received_at)
                    if timestamp.utcoffset() != timedelta(0):
                        raise ValueError("Host timestamp must be RFC3339 UTC")
                    scope.remaining()
                    age = services.monotonic() - scope.received_monotonic
                    if not math.isfinite(age) or age < 0:
                        raise ValueError("Invalid host monotonic clock")
                    data = {
                        "parameter": parameter,
                        "value": value,
                        "unit": unit,
                        "observed_at": scope.received_at,
                        "age_ms": int(age * 1000),
                        "quality": "valid",
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
        except _Failure as exc:
            return failure(exc.code, str(exc), scope.dispatch_state)
        except ProtocolError:
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
        return None

    async def close(self, context: OperationContext) -> None:
        if self._closed:
            return
        if self._busy:
            raise RuntimeError("Cancel and await the active operation before close")
        self._failed = True
        self._identified = False
        if self._services is not None:
            remaining = _remaining(self._services, context, context.deadline_monotonic)
            async with asyncio.timeout(min(remaining, 1.0)):
                await self._services.close_transport(context)
                _remaining(self._services, context, context.deadline_monotonic)
        self._closed = True
        self._opened = False
        self._services = None


def create_plugin() -> DevicePlugin:
    """Construct a fresh instance without importing or opening a serial backend."""
    return DevicePlugin()
