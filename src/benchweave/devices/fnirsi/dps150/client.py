"""Injected-transport DPS-150 client, with no port ownership or reconnection."""

import asyncio
import math
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol

from .codec import (
    GET,
    SET,
    FrameDecoder,
    ProtocolError,
    Value,
    decode_value,
    encode_packet,
    write_payload,
)


class Transport(Protocol):
    """An exclusively owned, clean, already-established byte session.

    Methods must cooperate with asyncio cancellation and never block the loop.
    send completes only after accepting every byte, or raises (possibly after
    partial dispatch). receive returns 1..max_bytes bytes, or b'' on EOF.
    No retry/reconnect may be hidden by an implementation of this interface.
    """

    async def send(self, data: bytes) -> None: ...

    async def receive(self, max_bytes: int) -> bytes: ...


class GetPayload(Enum):
    EMPTY = b""  # KochC ae1df445
    ZERO = b"\0"  # cho45 6107bd34


class SessionUnusable(RuntimeError):
    """An ambiguous/failed exchange requires external session recovery."""


class OperationBusy(RuntimeError):
    """Concurrent calls are rejected, never implicitly queued."""


class OperationTimeout(TimeoutError):
    """No completion established; dispatch intent does not prove device receipt."""

    def __init__(self, *, dispatch_started: bool) -> None:
        super().__init__("DPS-150 operation deadline expired; outcome may be unknown")
        self.dispatch_started = dispatch_started


@dataclass(frozen=True)
class DispatchReceipt:
    """Transport acceptance only, never acknowledgement or setting readback."""

    request: bytes
    assurance: Literal["dispatched"] = "dispatched"


class Client:
    """Single-flight protocol calls with one overall deadline and no cached reads.

    A failed call poisons this instance. The caller must independently establish
    a clean session before constructing another instance; replacement alone does
    not flush late bytes. This class never connects, handshakes or closes a port.
    """

    def __init__(self, transport: Transport, *, get_payload: GetPayload) -> None:
        if not isinstance(get_payload, GetPayload):
            raise ValueError("Select an explicit GetPayload dialect")
        self._transport = transport
        self._get_payload = get_payload
        self._busy = False
        self._unusable = False

    @property
    def unusable(self) -> bool:
        return self._unusable

    async def read(self, field: int, *, timeout: float) -> Value:
        request = encode_packet(GET, field, self._get_payload.value)
        result = await self._execute(request, field, timeout)
        assert not isinstance(result, DispatchReceipt)
        return result

    async def write(self, field: int, value: object, *, timeout: float) -> DispatchReceipt:
        request = encode_packet(SET, field, write_payload(field, value))
        result = await self._execute(request, None, timeout)
        assert isinstance(result, DispatchReceipt)
        return result

    async def _execute(
        self, request: bytes, expected_field: int | None, timeout: float
    ) -> Value | DispatchReceipt:
        if (
            type(timeout) not in (float, int)
            or not 0 < timeout <= 3600
            or not math.isfinite(timeout)
        ):
            raise ValueError("Timeout must be a finite positive number <=3600 seconds")
        if self._unusable:
            raise SessionUnusable("Session recovery is the caller's responsibility")
        if self._busy:
            raise OperationBusy("Only one operation may be in flight")
        self._busy = True
        dispatch_started = False
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            async with asyncio.timeout_at(deadline):
                dispatch_started = True
                await self._transport.send(request)
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError
                if expected_field is None:
                    return DispatchReceipt(request)
                decoder = FrameDecoder()
                while True:
                    # A yield enforces the deadline even if a mock/provider returns
                    # fragments synchronously without yielding to the event loop.
                    await asyncio.sleep(0)
                    chunk = await self._transport.receive(260)
                    if asyncio.get_running_loop().time() >= deadline:
                        raise TimeoutError
                    if chunk == b"":
                        raise ConnectionError("EOF during response")
                    packets = decoder.feed(chunk)
                    if not packets:
                        continue
                    if len(packets) != 1 or decoder.pending:
                        raise ProtocolError("Extra response bytes cannot satisfy a later request")
                    packet = packets[0]
                    if packet.field != expected_field:
                        raise ProtocolError("Unexpected response field; no resynchronisation")
                    return decode_value(packet)
        except TimeoutError as exc:
            self._unusable = True
            raise OperationTimeout(dispatch_started=dispatch_started) from exc
        except BaseException:
            # Includes external cancellation: a late response may still arrive.
            self._unusable = True
            raise
        finally:
            self._busy = False
