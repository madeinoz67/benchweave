# author: Stephen Eaton
"""SCPI query over an injected transport, through a closed command grammar.

DOCUMENTARY, NOT HARDWARE-QUALIFIED. The one command this client can send is
the identity query, in the form the manufacturer's programming guide gives.
No other command is evidenced for this unit, so no other command can be sent:
a name outside the grammar raises ``UnsupportedCommand`` before any write.
There is no arbitrary-command method.

The transport is injected and the package provides no hardware backend. The
transport is message framed: one ``send`` is one complete command, and one
``receive`` returns exactly one complete reply as the host framed it, with its
terminator. Framing (which terminator ends a command and a reply) is not
documented for this unit. It is therefore an explicit choice at every
construction, never a default, and never detected.

This client never connects, never retries a whole operation and never
reconnects. A failure after I/O starts marks the client unusable; recovery
belongs to the caller.
"""

import asyncio
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Protocol

from .codec import FrameError, check_bound

#: The longest operation this client accepts, in seconds.
MAX_TIMEOUT_S: Final = 3600.0


class Transport(Protocol):
    """A message-framed, exclusively owned session supplied by the caller.

    ``send`` accepts exactly one complete command, or raises, possibly after
    a partial dispatch. ``receive`` returns exactly one complete reply of at
    most ``max_bytes`` bytes, terminator included, or ``b""`` on EOF. An
    implementation must cooperate with asyncio cancellation, must never block
    the event loop, and must hide no retry or reconnection.
    """

    async def send(self, data: bytes) -> None: ...

    async def receive(self, max_bytes: int) -> bytes: ...


_READ_TERMINATORS: Final[Mapping[str, bytes]] = MappingProxyType(
    {"lf": b"\n", "crlf": b"\r\n", "eom": b""}
)
_WRITE_TERMINATORS: Final[frozenset[bytes]] = frozenset({b"", b"\n", b"\r\n"})


@dataclass(frozen=True)
class Framing:
    """The terminator that ends each command sent and each reply received.

    ``read_termination`` is the OTDP scoped-transfer termination name:
    ``lf``, ``crlf``, or ``eom`` for a message boundary the transport signals.
    """

    write_termination: bytes
    read_termination: str

    def __post_init__(self) -> None:
        if (
            type(self.write_termination) is not bytes
            or self.write_termination not in _WRITE_TERMINATORS
        ):
            raise ValueError("write_termination must be a line ending: LF, CRLF or none")
        if type(self.read_termination) is not str or self.read_termination not in (
            _READ_TERMINATORS
        ):
            raise ValueError("read_termination must be one of: lf, crlf, eom")

    def strip(self, reply: bytes) -> bytes:
        """Remove the read terminator from one reply, or refuse the reply."""
        marker = _READ_TERMINATORS[self.read_termination]
        if marker and not reply.endswith(marker):
            raise FrameError(f"the reply does not end with the {self.read_termination} terminator")
        return reply[: len(reply) - len(marker)] if marker else reply


#: The framing IEEE 488.2 defines, which the guide names as the basis of its
#: command language: a line feed ends each command and each reply. This is
#: documentary by reference. The framing of the actual unit is not evidenced.
IEEE488_2_NL: Final = Framing(write_termination=b"\n", read_termination="lf")


#: Every query this client may send, by name.
QUERIES: Final[Mapping[str, bytes]] = MappingProxyType({"idn": b"*IDN?"})
#: Every non-query command this client may send. None is evidenced.
WRITES: Final[Mapping[str, bytes]] = MappingProxyType({})
#: The declared grammar: the commands this client can put on a wire.
COMMANDS: Final[Mapping[str, bytes]] = QUERIES


class UnsupportedCommand(ValueError):
    """The command is outside the declared grammar; nothing was sent."""


class SessionUnusable(RuntimeError):
    """A failed exchange requires external session recovery."""


class OperationBusy(RuntimeError):
    """Concurrent calls are rejected, never implicitly queued."""


class OperationTimeout(TimeoutError):
    """No completion was established; dispatch intent does not prove receipt."""

    def __init__(self, *, dispatch_started: bool) -> None:
        super().__init__("SCPI operation deadline expired; the outcome may be unknown")
        self.dispatch_started = dispatch_started


@dataclass(frozen=True)
class DispatchReceipt:
    """Transport acceptance only, never an acknowledgement or a readback."""

    request: bytes
    assurance: Literal["dispatched"] = "dispatched"


def check_timeout(timeout: object) -> float:
    """A timeout is a finite positive number of seconds, at most one hour."""
    if isinstance(timeout, bool) or not isinstance(timeout, int | float):
        raise ValueError("Timeout must be a finite positive number <=3600 seconds")
    seconds = float(timeout)
    if not 0 < seconds <= MAX_TIMEOUT_S or not math.isfinite(seconds):
        raise ValueError("Timeout must be a finite positive number <=3600 seconds")
    return seconds


class ScpiClient:
    """Single-flight queries with one overall deadline and no cached replies.

    A failed call marks this client unusable. Constructing another client over
    the same transport is not a recovery: late bytes may still arrive.
    """

    def __init__(self, transport: Transport, *, framing: Framing) -> None:
        if not isinstance(framing, Framing):
            raise ValueError("Select an explicit framing")
        self._transport = transport
        self._framing = framing
        self._busy = False
        self._unusable = False

    @property
    def unusable(self) -> bool:
        return self._unusable

    async def query(self, name: str, *, timeout: float, max_bytes: int) -> bytes:
        """Send one query and return its reply without the read terminator."""
        if type(name) is not str or name not in QUERIES:
            raise UnsupportedCommand(f"Unsupported command: {name!r}")
        seconds = check_timeout(timeout)
        bound = check_bound(max_bytes)
        request = QUERIES[name] + self._framing.write_termination
        try:
            reply = await self._exchange(request, seconds, bound)
            return self._framing.strip(reply)
        except FrameError:
            self._unusable = True
            raise

    async def write(self, name: str, *, timeout: float) -> DispatchReceipt:
        """Send one non-query command and read nothing.

        No non-query command is evidenced for this unit, so every name is
        refused here, including a query's name.
        """
        if type(name) is not str or name in QUERIES or name not in WRITES:
            raise UnsupportedCommand(f"Unsupported command: {name!r}")
        seconds = check_timeout(timeout)
        request = WRITES[name] + self._framing.write_termination
        await self._exchange(request, seconds, None)
        return DispatchReceipt(request)

    async def _exchange(self, request: bytes, timeout: float, max_bytes: int | None) -> bytes:
        if self._unusable:
            raise SessionUnusable("Session recovery is the caller's responsibility")
        if self._busy:
            raise OperationBusy("Only one operation may be in flight")
        self._busy = True
        try:
            async with asyncio.timeout(timeout):
                await self._transport.send(request)
                # A yield enforces the deadline even when a mock or a provider
                # returns fragments synchronously without yielding.
                await asyncio.sleep(0)
                if max_bytes is None:
                    return b""
                reply = await self._transport.receive(max_bytes)
                if reply == b"":
                    raise ConnectionError("EOF during response")
                return reply
        except TimeoutError as exc:
            self._unusable = True
            raise OperationTimeout(dispatch_started=True) from exc
        except BaseException:
            # Includes external cancellation: a late reply may still arrive.
            self._unusable = True
            raise
        finally:
            self._busy = False
