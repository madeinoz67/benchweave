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
import re
import sqlite3
import threading
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import uuid4

from benchweave.content.store import EvidenceQuotaExceeded
from benchweave.host.plugin import SimulationInfo
from benchweave.host.types import (
    Assurance,
    CaptureFinaliseRejected,
    CaptureQuotaExceeded,
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
        capture: Any = None,
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
        # §0.3: capture control flows ONLY through this controller object,
        # never through self._services (the pinned exercised services
        # subset stays {monotonic} until the streaming slice). None = the
        # session was constructed without the artifact_writer permission.
        self._capture = capture
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

        if self._runner is None:
            # Survives python -O: the bridge must never run an operation
            # without its owning runner.
            raise RuntimeError("bridge invariant violated: no runner bound")
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
                # The adapter's own cooperative cleanup ran first (above);
                # this is the host-side guarantee for anything still open —
                # abort's no-op-retract makes the double call safe.
                if self._capture is not None:
                    with suppress(Exception):
                        self._capture.sweep_open(reason="plugin_close")
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
            supported = {
                "identify": set(),
                "read": {"parameter"},
                "write": {"parameter", "value"},
                "capture": {"capture_id", "format", "sample_count", "max_bytes"},
            }
            expected = supported.get(request.verb.value)
            if expected is None:
                return reject(
                    ErrorCode.UNSUPPORTED,
                    "Bridge supports identify, read, write and capture",
                )
            if set(request.arguments) != expected:
                return reject(ErrorCode.UNSUPPORTED, "Unsupported arguments for bridge operation")
            deadline = deadline_ns / 1_000_000_000
            if not math.isfinite(deadline) or self._services.monotonic() >= deadline:
                return reject(ErrorCode.TIMEOUT, "Operation deadline expired")
            capture_id: str | None = None
            if request.verb.value == "capture":
                gate = self._capture_gate(request)
                if isinstance(gate, OperationResult):
                    return gate
                capture_id = gate
            context = _Context(request.operation_id, deadline, self._services)
            envelope = {
                "operation_id": request.operation_id,
                "verb": request.verb.value,
                "arguments": copy.deepcopy(request.arguments),
            }

            def poison(exc: BaseException) -> OperationResult:
                self._failed = True
                return OperationResult.indeterminate(
                    request.operation_id,
                    request.verb,
                    code=ErrorCode.TIMEOUT
                    if isinstance(exc, TimeoutError)
                    else ErrorCode.PROTOCOL_ERROR,
                    message="Invalid, failed or late adapter result; no replay",
                )

            try:
                result = self._run(self._adapter.execute(envelope, context), context)
                converted = self._convert(request, result, context)
                if capture_id is not None and self._capture is not None:
                    # Success: retire the capture — no epilogue, no forensic
                    # record; a published, acknowledged capture stands.
                    self._capture.retire(capture_id)
                return converted
            except (
                CaptureQuotaExceeded,
                EvidenceQuotaExceeded,
                sqlite3.OperationalError,
            ) as exc:
                # Writer/bundle-originated resource conditions only: the
                # stamp is the discriminator (a bare raise of any of these
                # classes from adapter code keeps the poison posture).
                if getattr(exc, "writer_stamp", None) is None:
                    if capture_id is not None:
                        self._abort_contained(capture_id, request.operation_id)
                    return poison(exc)
                self._abort_contained(capture_id, request.operation_id)
                return OperationResult.failure(
                    request.operation_id,
                    request.verb,
                    code=ErrorCode.RESOURCE_LIMIT,
                    message=f"Capture resource condition: {exc}",
                    # A7: every refusal raised after execute entry is
                    # dispatched — never not_dispatched, and the session
                    # survives (no poison).
                    dispatch_state=DispatchState.DISPATCHED,
                )
            except (Exception, asyncio.CancelledError) as exc:
                if capture_id is not None:
                    self._abort_contained(capture_id, request.operation_id)
                return poison(exc)

    # The interoperable integer range (spec §4): values outside −(2^53−1)
    # through 2^53−1 are unsupported by the numeric interface — also the
    # structural sqlite-bind safety bound.
    _INT_MAX = 2**53 - 1
    _CAPTURE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*")
    _CAPTURE_FORMATS = ("waveform_f64le", "raw_binary")

    def _capture_gate(self, request: OperationRequest) -> str | OperationResult:
        """The pre-dispatch capture gates (R1: bounds before the device).

        Every refusal is a clean typed rejection with zero adapter calls;
        the gate region has no exception frame, so descriptor limits are
        type-validated here rather than trusted — a malformed descriptor
        yields INVALID_ARGUMENT, never an escaping exception.
        """
        arguments = request.arguments
        if self._capture is None:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.UNSUPPORTED,
                message="capture requires artifact_writer permission",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        capture_id = arguments.get("capture_id")
        if not isinstance(capture_id, str) or not self._CAPTURE_ID_PATTERN.fullmatch(
            capture_id
        ):
            return self._invalid(request, "capture_id must match the contract id shape")
        # A5: exact-type ints (bool rejected — the _reading precedent) and
        # the spec §4 interoperable bound, which keeps the sqlite bind
        # structurally safe.
        count = self._exact_int(arguments.get("sample_count"))
        byte_cap = self._exact_int(arguments.get("max_bytes"))
        if count is None or byte_cap is None:
            return self._invalid(
                request, "sample_count and max_bytes must be integers in [1, 2^53-1]"
            )
        if not (1 <= count <= self._INT_MAX) or not (1 <= byte_cap <= self._INT_MAX):
            return self._invalid(
                request, "sample_count and max_bytes must be integers in [1, 2^53-1]"
            )
        fmt = arguments.get("format")
        if fmt not in self._CAPTURE_FORMATS:
            return self._invalid(request, "format must be waveform_f64le or raw_binary")
        # G1 arithmetic: the request's own numbers must agree (spec §7:
        # byte length equals sample_count×8).
        if fmt == "waveform_f64le" and count * 8 > byte_cap:
            return self._invalid(
                request,
                f"waveform_f64le sample_count {count} needs "
                f"{count * 8} bytes, above the declared max_bytes {byte_cap}",
            )
        # G2 descriptor: limits read with type validation — malformed
        # limits are a clean refusal, never an exception.
        limits = self._descriptor.get("capture_limits")
        if not isinstance(limits, dict):
            return self._invalid(request, "descriptor capture_limits must be an object")
        limit_samples = self._exact_int(limits.get("max_samples"))
        limit_bytes = self._exact_int(limits.get("max_bytes"))
        if limit_samples is None or limit_samples < 1:
            return self._invalid(
                request, "descriptor capture_limits.max_samples must be an integer >= 1"
            )
        if limit_bytes is None or limit_bytes < 1:
            return self._invalid(
                request, "descriptor capture_limits.max_bytes must be an integer >= 1"
            )
        if count > limit_samples:
            return self._invalid(
                request,
                f"sample_count {count} exceeds descriptor max_samples {limit_samples}",
            )
        if byte_cap > limit_bytes:
            return self._invalid(
                request,
                f"max_bytes {byte_cap} exceeds descriptor max_bytes {limit_bytes}",
            )
        formats = self._descriptor.get("capture_formats")
        if not isinstance(formats, list) or fmt not in formats:
            return self._invalid(
                request, f"format {fmt!r} is not among the descriptor capture_formats"
            )
        # G3 quota: check-and-reserve in its own local frame (A6) — a quota
        # refusal is RESOURCE_LIMIT not_dispatched; any other store failure
        # is INTERNAL_ERROR not_dispatched. Nothing was opened in either
        # case, so no epilogue runs (zero forensic rows on gate refusals).
        try:
            self._capture.open_capture(
                capture_id=capture_id,
                fmt=fmt,
                sample_count=count,
                max_bytes=byte_cap,
            )
        except CaptureQuotaExceeded as exc:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.RESOURCE_LIMIT,
                message=f"capture allowance exceeded: {exc}",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        except CaptureFinaliseRejected as exc:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.INVALID_ARGUMENT,
                message=f"capture id refused: {exc}",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        except Exception as exc:
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.INTERNAL_ERROR,
                message=f"capture open failed: {exc}",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        return capture_id

    @staticmethod
    def _exact_int(value: Any) -> int | None:
        """The value iff it is exactly an int (bool is a subclass — rejected),
        else None; the gate's typing discipline."""
        return value if type(value) is int else None

    def _invalid(self, request: OperationRequest, message: str) -> OperationResult:
        return OperationResult.failure(
            request.operation_id,
            request.verb,
            code=ErrorCode.INVALID_ARGUMENT,
            message=message,
            dispatch_state=DispatchState.NOT_DISPATCHED,
        )

    def _abort_contained(self, capture_id: str | None, operation_id: str) -> None:
        """The bounded abort epilogue (A8): host-side synchronous reclaim
        plus the forensic record, without depending on adapter cooperation.
        Fully contained — every failure is suppressed and logged, never
        replacing the OperationResult being returned. Runs ONLY for a
        capture that was actually opened."""
        if capture_id is None or self._capture is None:
            return
        with suppress(Exception):
            self._capture.abort(capture_id, reason="dispatch failed", operation_id=operation_id)

    def _capture_manifest(
        self, request: OperationRequest, data: dict[str, Any]
    ) -> dict[str, Any]:
        """The two-sided manifest contract (G4): per-key echo checks against
        the dispatch request, host-computed fields from the writer's
        published record — adapter-supplied digest/length/artifact id are
        ignored, never trusted, and the bridge returns the HOST-constructed
        manifest. Per-key checks on purpose (A12): a raise-gated set
        literal would wrongly close the manifest (``x-`` extension keys are
        schema-legal) and trip the envelope pin.
        """
        arguments = request.arguments
        capture_id = str(arguments["capture_id"])
        record = self._capture.finalise_record(capture_id)
        if record is None:
            raise ValueError("capture result without a published capture")
        if data.get("capture_id") != capture_id:
            raise ValueError("uncorrelated capture manifest")
        if data.get("format") != arguments["format"]:
            raise ValueError("capture manifest format does not echo the request")
        if "sample_count" in data and data["sample_count"] != arguments["sample_count"]:
            raise ValueError("capture manifest sample_count does not echo the request")
        started_at = data.get("started_at")
        if not isinstance(started_at, str) or not started_at:
            raise ValueError("capture manifest requires a started_at string")
        manifest: dict[str, Any] = {
            "capture_id": capture_id,
            "format": record["format"],
            "artifact_id": record["artifact_id"],
            "byte_length": record["byte_length"],
            "sha256": record["sha256"],
            "started_at": started_at,
        }
        if arguments["format"] == "waveform_f64le":
            count = arguments["sample_count"]
            if record["byte_length"] != count * 8:
                raise ValueError("published byte_length disagrees with sample_count×8")
            interval = data.get("sample_interval_s")
            if (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not math.isfinite(interval)
                or not interval > 0
            ):
                raise ValueError("capture manifest requires a positive finite sample_interval_s")
            unit = data.get("unit")
            if not isinstance(unit, str) or not unit:
                raise ValueError("capture manifest requires a non-empty unit")
            manifest["sample_count"] = count
            manifest["sample_interval_s"] = interval
            manifest["unit"] = unit
        return manifest

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
        elif request.verb.value == "capture":
            value = self._capture_manifest(request, data)
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
