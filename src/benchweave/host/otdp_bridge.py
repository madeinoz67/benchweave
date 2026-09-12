"""Explicit OTDP 0.3/API 1.1 compatibility for the synchronous host.

Identify, scalar read and scalar write are supported. Dataset, profile and stream
semantics need a native async host. Services are caller-supplied, including the
SAME monotonic timebase used for host deadlines (seconds versus nanoseconds).
No transport provider is created. Adapters are trusted Python, not sandboxed;
deadlines require cooperative async code. Each bridge owns one event loop and
serialises its lifecycle and dispatch. An uncertain failure poisons the session.
"""

from __future__ import annotations

import asyncio
import copy
import math
import threading
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import uuid4

from benchweave.host.plugin import SimulationInfo
from benchweave.host.types import (
    Assurance,
    DispatchState,
    ErrorCode,
    Identity,
    IdentitySource,
    OperationError,
    OperationRequest,
    OperationResult,
    OperationStatus,
    Quality,
    Reading,
    ReadingSource,
    WriteReceipt,
)


class _Context:
    def __init__(self, operation_id: str, deadline: float, services: Any) -> None:
        self.operation_id = operation_id
        self.dataset_id = None
        self.deadline_monotonic = deadline
        self.services = services
        self.dispatched = False
        self.cancelled = False

    def is_cancelled(self) -> bool:
        return self.cancelled

    async def mark_dispatch_started(self) -> None:
        if self.cancelled or self.services.monotonic() >= self.deadline_monotonic:
            raise TimeoutError("dispatch deadline expired")
        self.dispatched = True


class OTDPBridge:
    """An unopened DevicePlugin wrapping an async adapter with explicit authority."""

    def __init__(
        self,
        adapter: Any,
        *,
        descriptor: dict[str, Any],
        services: Any,
        simulation: SimulationInfo,
        lifecycle_timeout: float = 5.0,
    ) -> None:
        if not isinstance(simulation, SimulationInfo):
            raise TypeError("explicit SimulationInfo required")
        if not callable(getattr(services, "monotonic", None)):
            raise TypeError("scoped OTDP services with monotonic() required")
        if not math.isfinite(lifecycle_timeout) or lifecycle_timeout <= 0:
            raise ValueError("lifecycle_timeout must be finite and positive")
        self._adapter = adapter
        self._descriptor = copy.deepcopy(descriptor)
        self._services = services
        self._simulation = simulation
        self._lifecycle_timeout = lifecycle_timeout
        self._runner: asyncio.Runner | None = None
        self._lock = threading.RLock()
        self._opened = False
        self._closed = False
        self._failed = False
        self._release_loader: Callable[[], None] = lambda: None

    @property
    def simulation(self) -> SimulationInfo:
        return self._simulation

    def _context(self) -> _Context:
        return _Context(
            str(uuid4()),
            self._services.monotonic() + self._lifecycle_timeout,
            self._services,
        )

    def _run(self, awaitable: Awaitable[Any], context: _Context) -> Any:
        async def bounded() -> Any:
            try:
                remaining = context.deadline_monotonic - self._services.monotonic()
                async with asyncio.timeout(max(0, remaining)):
                    result = await awaitable
                if self._services.monotonic() >= context.deadline_monotonic:
                    raise TimeoutError("late adapter result")
                return result
            except BaseException:
                context.cancelled = True
                raise

        assert self._runner is not None
        return self._runner.run(bounded())

    @staticmethod
    def _require_sync() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError("OTDPBridge requires a synchronous calling thread")

    def plugin_open(self, services: Any) -> None:
        """Open using the scoped OTDP services supplied at construction."""
        self._require_sync()
        with self._lock:
            if self._opened or self._closed:
                raise RuntimeError("bridge cannot be reopened")
            self._runner = asyncio.Runner()
            try:
                context = self._context()
                self._run(
                    self._adapter.open(copy.deepcopy(self._descriptor), self._services, context),
                    context,
                )
                self._opened = True
            except BaseException:
                # Preserve the original failure, including after partial acquisition.
                with suppress(BaseException):
                    context = self._context()
                    self._run(self._adapter.close(context), context)
                self._runner.close()
                self._closed = True
                self._release_loader()
                raise

    def plugin_close(self) -> None:
        self._require_sync()
        with self._lock:
            if self._closed:
                return
            try:
                if self._runner is not None:
                    context = self._context()
                    self._run(self._adapter.close(context), context)
            finally:
                self._closed = True
                self._opened = False
                try:
                    if self._runner is not None:
                        self._runner.close()
                finally:
                    self._release_loader()

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        self._require_sync()
        with self._lock:

            def reject(code: ErrorCode, message: str) -> OperationResult:
                return OperationResult.failure(
                    request.operation_id,
                    request.verb,
                    code=code,
                    message=message,
                    dispatch_state=DispatchState.NOT_DISPATCHED,
                )

            if not self._opened or self._closed or self._failed:
                return reject(ErrorCode.INTERNAL_ERROR, "A fresh opened bridge is required")
            supported = {"identify": set(), "read": {"parameter"}, "write": {"parameter", "value"}}
            expected = supported.get(request.verb.value)
            if expected is None:
                return reject(ErrorCode.UNSUPPORTED, "Bridge supports identify, read and write")
            if set(request.arguments) != expected:
                return reject(ErrorCode.UNSUPPORTED, "Unsupported arguments for bridge operation")
            deadline = deadline_ns / 1_000_000_000
            if not math.isfinite(deadline) or self._services.monotonic() >= deadline:
                return reject(ErrorCode.TIMEOUT, "Operation deadline expired")
            context = _Context(request.operation_id, deadline, self._services)
            envelope = {
                "operation_id": request.operation_id,
                "verb": request.verb.value,
                "arguments": copy.deepcopy(request.arguments),
            }
            try:
                result = self._run(self._adapter.execute(envelope, context), context)
                return self._convert(request, result, context)
            except (Exception, asyncio.CancelledError) as exc:
                self._failed = True
                return OperationResult.indeterminate(
                    request.operation_id,
                    request.verb,
                    code=ErrorCode.TIMEOUT
                    if isinstance(exc, TimeoutError)
                    else ErrorCode.PROTOCOL_ERROR,
                    message="Invalid, failed or late adapter result; no replay",
                )

    @staticmethod
    def _scalar(value: Any) -> bool:
        return (
            value is None
            or type(value) in {str, bool, int}
            or (type(value) is float and math.isfinite(value))
        )

    @staticmethod
    def _reading(data: dict[str, Any], parameter: str) -> Reading:
        if not isinstance(data, dict) or not OTDPBridge._scalar(data.get("value")):
            raise ValueError("reading requires a finite scalar value")
        if type(data.get("age_ms")) is not int:
            raise ValueError("reading age must be an integer")
        if not isinstance(data.get("observed_at"), str):
            raise ValueError("reading timestamp must be a string")
        if data.get("unit") is not None and not isinstance(data["unit"], str):
            raise ValueError("reading unit must be a string or null")
        data = dict(data)
        if data.get("parameter") != parameter:
            raise ValueError("uncorrelated parameter")
        data["quality"] = Quality(data["quality"])
        data["source"] = ReadingSource(data["source"])
        return Reading(**data)

    def _convert(
        self, request: OperationRequest, result: Any, context: _Context
    ) -> OperationResult:
        if (
            not isinstance(result, dict)
            or result.get("operation_id") != request.operation_id
            or result.get("verb") != request.verb.value
        ):
            raise ValueError("uncorrelated result")
        status = OperationStatus(result["status"])
        if status is not OperationStatus.OK:
            if set(result) != {"operation_id", "verb", "status", "error"}:
                raise ValueError("invalid error envelope")
            error = result["error"]
            if set(error) != {"code", "message", "dispatch_state"}:
                raise ValueError("invalid error")
            state = DispatchState(error["dispatch_state"])
            if context.dispatched and state is DispatchState.NOT_DISPATCHED:
                raise ValueError("contradictory dispatch receipt")
            if state is not DispatchState.NOT_DISPATCHED:
                self._failed = True
            return OperationResult(
                request.operation_id,
                request.verb,
                status,
                error=OperationError(ErrorCode(error["code"]), error["message"], state),
            )
        if set(result) != {"operation_id", "verb", "status", "data"}:
            raise ValueError("invalid success envelope")
        if not isinstance(result["data"], dict):
            raise ValueError("success data must be an object")
        data = dict(result["data"])
        value: Any
        if request.verb.value == "identify":
            if any(
                not isinstance(data.get(key), str) or not data[key]
                for key in ("manufacturer", "model")
            ):
                raise ValueError("identity requires nonempty strings")
            if any(
                data.get(key) is not None and not isinstance(data[key], str)
                for key in ("serial", "firmware")
            ):
                raise ValueError("identity fields must be strings or null")
            data["source"] = IdentitySource(data["source"])
            value = Identity(**data)
        elif request.verb.value == "read":
            value = self._reading(data, request.arguments["parameter"])
        else:
            if (
                data.get("parameter") != request.arguments["parameter"]
                or data.get("requested_value") != request.arguments["value"]
            ):
                raise ValueError("uncorrelated write receipt")
            if not self._scalar(data.get("effective_value")):
                raise ValueError("write receipt requires a finite scalar")
            data["assurance"] = Assurance(data["assurance"])
            if data.get("verification") is not None:
                data["verification"] = self._reading(data["verification"], data["parameter"])
            data.setdefault("verification", None)
            value = WriteReceipt(**data)
        return OperationResult.ok(request.operation_id, request.verb, value)
