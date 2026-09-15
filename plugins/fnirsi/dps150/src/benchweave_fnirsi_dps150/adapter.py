"""Read-only OTDP 0.3.0 adapter, structurally implementing the documented 1.1 ABI.

Only scoped host services perform I/O. No SDK, serial driver, background reader,
retry, reconnection, or profile assurance is implied by this adapter. Session
truth lives here per the WP10 architecture: the device is silent until the
evidence-backed two-frame handshake (fixtures/protocols/dps150/), its wake is
power-cycle-bound and survives reconnection, and unsolicited ~2 Hz telemetry
interleaves with request/response — so the adapter establishes the session at
first commanded use, drains a bounded telemetry window before each commanded
call, and consumes each commanded reply window by correlation: the first
frame matching the requested field is the reply, and every other frame in
the window is telemetry, buffered into its measurement surface.
"""

import asyncio
import json
import math
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

from .client import Client, GetPayload
from .codec import Packet, ProtocolError, Value, decode_packet, decode_value
from .descriptor import PARAMETERS, build_descriptor
from .session import drain_telemetry, open_session

# Evidence-backed session constants (WP10; fixtures/protocols/dps150/): the
# ~50 ms fire-and-forget pacing captured in connect-v2.jsonl...
_SESSION_DELAY_S: float = 0.05
# ...and one bounded telemetry drain before each commanded call. The captured
# cycle is five fields at ~2 Hz (a frame per ~100 ms), so a window above the
# inter-frame gap both empties the reply path and captures at least one frame
# while staying well inside the adapter's 1 s soft operation deadline. The
# window is frame-atomic (WP11 W1): it bounds when the drain stops STARTING
# receives — a frame in flight at the edge completes, so the boundary can
# never desync the stream and poison the session.
_DRAIN_WINDOW_S: float = 0.15


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

    async def _receive_exact(self, size: int) -> bytes | None:
        """One exact host receive; None when the transport offers no bytes."""
        self.remaining()
        result = await self.services.transfer(
            {"kind": "stream_receive", "max_bytes": size, "termination": "lf", "exact_bytes": size},
            self.context,
        )
        self.remaining()
        if not isinstance(result, dict) or set(result) != {"data"}:
            raise ProtocolError("Invalid host receive response")
        data = result["data"]
        if data == b"":
            return None
        if type(data) is not bytes or len(data) != size:
            raise ProtocolError("Incomplete or oversized exact receive")
        return data

    async def _exact(self, size: int) -> bytes:
        data = await self._receive_exact(size)
        if data is None:
            raise ProtocolError("Incomplete or oversized exact receive")
        return data

    async def _frame(self, max_bytes: int) -> bytes | None:
        """One header-validated complete frame; None if no bytes are offered."""
        header = await self._receive_exact(4)
        if header is None:
            return None
        if header[:2] != b"\xf0\xa1" or header[3] + 5 > max_bytes:
            raise ProtocolError("Invalid frame header or length")
        body = await self._receive_exact(header[3] + 1)
        if body is None:
            raise ProtocolError("Incomplete or oversized exact receive")
        self.received_monotonic = self.services.monotonic()
        self.received_at = self.services.utc_now()
        self.remaining()
        return header + body

    async def receive(self, max_bytes: int) -> bytes:
        """One strictly framed complete frame; no offered bytes are an error.

        Satisfies the library Transport contract the session opener types
        against (_Scope is what open_session receives). The commanded
        Client path no longer uses this strict view — on a live streaming
        device a commanded window legitimately holds interleaved telemetry,
        which is _CorrelatedWire's job — so exhaustion here is a failed
        exchange, exactly as it was when the Client consumed _Scope raw.
        """
        frame = await self._frame(max_bytes)
        if frame is None:
            raise ProtocolError("Incomplete or oversized exact receive")
        return frame

    async def receive_stream(self, max_bytes: int) -> bytes:
        """A complete frame, or b"" when no bytes are offered.

        Framing matches receive(); an exhausted transport ends a telemetry
        drain or a correlated receive window quietly (the session library
        reads b"" as end-of-stream) while corrupt frames still raise
        ProtocolError: a receive window empties a healthy stream, it must
        not hide corruption.
        """
        frame = await self._frame(max_bytes)
        return b"" if frame is None else frame


class _TelemetryDrain:
    """_Scope as the session library's Transport for bounded telemetry drains.

    The drain never sends; receive yields exactly one complete frame per
    call, so the library's decoder sees whole frames and an exhausted
    transport (b"") ends the window early as it would on the raw Transport.
    """

    def __init__(self, scope: _Scope) -> None:
        self._scope = scope

    async def send(self, data: bytes) -> None:
        raise AssertionError("the telemetry drain never sends")

    async def receive(self, max_bytes: int) -> bytes:
        return await self._scope.receive_stream(max_bytes)


class _CorrelatedWire:
    """_Scope as the Client's Transport on a live streaming session.

    The live device interleaves ~2 Hz telemetry with command replies inside
    one commanded receive window (connect-v2.jsonl; live-stream.jsonl
    "diagnosis-final"): a frame in flight when the pre-call drain closes can
    land ahead of the reply, and the stream continues behind it. The
    Client's one-frame rule is correct for a quiescent session, so this
    wrapper keeps the library's contract honest by never showing it the
    streaming reality: receive() returns exactly the first frame whose field
    matches the field the adapter is about to request, and every other
    frame — telemetry by definition on this protocol — is absorbed through
    the same PARAMETERS mapping as the drain. When telemetry itself carries
    the requested field (the ~2 Hz cycle includes 195), that telemetry frame
    IS the reply: the protocol offers no reply marker, so first-field-match
    is the only rule available, and the superseded reply frame surfaces
    through the absorb path as telemetry (WP11 W2 pin). Malformed frames
    still raise ProtocolError (this wrapper empties a healthy stream, it
    must not hide corruption), and an exhausted transport inside a
    commanded window fails the exchange as the protocol failure the
    adapter already pins.
    """

    def __init__(self, scope: _Scope, absorb: Callable[[Packet, float, str], None]) -> None:
        self._scope = scope
        self._absorb = absorb
        self._expected: int | None = None

    def expect(self, field: int) -> None:
        """Name the field the next Client read will request."""
        self._expected = field

    async def send(self, data: bytes) -> None:
        await self._scope.send(data)

    async def receive(self, max_bytes: int) -> bytes:
        expected = self._expected
        if expected is None:
            raise AssertionError("expect() must precede each commanded read")
        while True:
            frame = await self._scope.receive_stream(max_bytes)
            if frame == b"":
                # A commanded window on this device is never legitimately
                # empty: the awake device always answers and always streams,
                # so exhaustion inside the window is a failed exchange —
                # surfaced as the protocol failure the adapter already pins,
                # not reclassified as transport loss (b"" EOF stays a
                # library-level truth for raw transports).
                raise ProtocolError("Commanded window offered no bytes")
            packet = decode_packet(frame)
            if packet.field == expected:
                return frame
            self._absorb(packet, self._scope.received_monotonic, self._scope.received_at)


class DevicePlugin:
    """One scoped connection, one active operation, permanently failed after ambiguity."""

    def __init__(self) -> None:
        self._services: HostServices | None = None
        self._opened = False
        self._closed = False
        self._failed = False
        self._busy = False
        self._identified = False
        self._established = False
        self._telemetry: dict[str, tuple[Value, float, str]] = {}

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

    def _absorb_stamped(self, packet: Packet, observed_monotonic: float, observed_at: str) -> None:
        """Buffer one telemetry packet into the measurement surface.

        The same PARAMETERS mapping as a commanded read: field 195 surfaces
        as voltage, current and power (V/A/W), 192 as input_voltage, 196 as
        temperature; one row per parameter, latest frame wins.
        """
        decoded: Value | None = None
        for name, field, component, _, _, _, _ in PARAMETERS:
            if field != packet.field:
                continue
            if decoded is None:
                decoded = decode_value(packet)
            value = decoded
            if component is not None:
                if not isinstance(decoded, tuple):
                    raise ProtocolError("Expected voltage/current/power tuple")
                value = decoded[component]
            self._telemetry[name] = (value, observed_monotonic, observed_at)

    async def _drain(self, scope: _Scope) -> None:
        """Buffer one bounded telemetry window before a commanded call.

        Front protection and telemetry freshness: the live device streams
        unsolicited telemetry around its replies, so the window empties the
        reply path ahead of the request and captures fresh frames; frames
        that still interleave with the reply itself are consumed by
        _CorrelatedWire inside the commanded window. Buffered frames are
        never discarded: fields carrying an adapter parameter surface
        through latest_telemetry() using the same PARAMETERS mapping as a
        commanded read; rows are stamped with the window's last frame
        receipt. Malformed frames propagate (ProtocolError), per the drain's
        contract of emptying only a healthy stream.
        """
        packets = await drain_telemetry(_TelemetryDrain(scope), window_s=_DRAIN_WINDOW_S)
        if not packets:
            return
        observed_monotonic = scope.received_monotonic
        observed_at = scope.received_at
        for packet in packets:
            self._absorb_stamped(packet, observed_monotonic, observed_at)

    def latest_telemetry(self) -> tuple[dict[str, Any], ...]:
        """Latest drained telemetry as rows in the adapter's reading shape.

        Rows follow the same measurement contract as a commanded read
        (parameter, value, unit, observed_at, age_ms, quality, source) and
        the same PARAMETERS mapping — field 195 surfaces as voltage,
        current and power (V/A/W), 192 as input_voltage, 196 as temperature.
        One row per parameter, latest frame wins, PARAMETERS order; age_ms
        grows from the drain-time stamp.
        """
        services = self._services
        if services is None:
            return ()
        rows: list[dict[str, Any]] = []
        for name, _, _, _, unit, _, _ in PARAMETERS:
            stamped = self._telemetry.get(name)
            if stamped is None:
                continue
            value, observed_monotonic, observed_at = stamped
            age = services.monotonic() - observed_monotonic
            rows.append(
                {
                    "parameter": name,
                    "value": value,
                    "unit": unit,
                    "observed_at": observed_at,
                    "age_ms": max(0, int(age * 1000)),
                    "quality": "valid",
                    "source": "device",
                }
            )
        return tuple(rows)

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
                if not self._established:
                    # The device's wake is power-cycle-bound and survives
                    # reconnection, so the handshake is sent unconditionally
                    # at first commanded use — harmless to an already-awake
                    # device — and never read as evidence that silence is
                    # an error.
                    await open_session(scope, delay_s=_SESSION_DELAY_S)
                    self._established = True
                wire = _CorrelatedWire(scope, self._absorb_stamped)
                client = Client(wire, get_payload=GetPayload.EMPTY)

                async def correlated_read(field: int) -> Value:
                    # One act: name the field on the wire, then ask the Client
                    # for it, so the correlation can never go stale.
                    wire.expect(field)
                    return await client.read(field, timeout=scope.remaining())

                if verb == "identify":
                    self._identified = False
                    await self._drain(scope)
                    model = await correlated_read(222)
                    if model != "DPS-150":
                        raise _Failure("IDENTITY_MISMATCH", "Device model does not match DPS-150")
                    await self._drain(scope)
                    firmware = await correlated_read(224)
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
                    await self._drain(scope)
                    value = await correlated_read(field)
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
        self._established = False
        self._telemetry.clear()
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
