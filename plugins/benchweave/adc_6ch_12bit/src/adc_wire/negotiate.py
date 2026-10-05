# author: Stephen Eaton
"""Host-side protocol-v2 negotiation for the ADC board (issue #393).

The design (§4.1) sequence, ONE attempt, never a silent retry loop
(A06): connect at 2 Mbps -> IDENTIFY (the only frame permitted before
its response; non-mutating) -> if the device identifies proto >= 2 with
the SET_BAUD and slim-frame capability bits set: ACKed SET_BAUD ->
the host reopens the port at the new baud -> ACKed SET_FRAME_FORMAT
-> stream. Failure at any step after IDENTIFY falls back to the legacy
path (2 Mbps, fixed 23 B frame), surfaces the fallback as an event and
never retries the switch. A v1 device answers SET_BAUD with NAK
(bad command) — the fallback path is identical.

Timing (wire-protocol.md §timing; commissioned per bench per A02 — the
defaults are hints, not constants tuned on one bench):
- ``T_switch`` (host): if SET_FRAME_FORMAT is not ACKed within it after
  the host reopened at the new baud, the host reopens at 2 Mbps,
  re-IDENTIFYs to confirm the legacy path, and reports.
- ``T_revert`` (device): after applying a switch, if no CRC-valid frame
  arrives within it, the device reverts to 2 Mbps + legacy on its own.
  The HOST does not implement the device side; the emulator does.

The module speaks ONLY the OTDP section 8.1 transaction surface
(:class:`TransportServices`) — the SDK serial backend conforms
structurally, the emulator implements it in-process, and no port exists
in this module. Transmits need the host's dispatch marker on the context
(the backend's transmit discipline); the caller marks the dispatch
before calling :func:`negotiate_stream`.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from adc_wire import codec

#: Default host switch timeout T_switch (wire-protocol.md §timing).
T_SWITCH_DEFAULT_S = 0.5
#: Default device revert window T_revert — documented for symmetry; the
#: HOST never enforces it (the device reverts on its own).
T_REVERT_DEFAULT_S = 0.25


class TransportServices(Protocol):
    """The OTDP §8.1 transaction surface the negotiation drives.

    Structurally the SDK ``HostServices`` transfer member: one
    ``transfer(transaction, context)`` coroutine over the closed
    stream_send / stream_receive / stream_exchange field sets. The
    emulator implements it in-process; the SDK backend conforms.
    """

    def transfer(self, transaction: dict[str, Any], context: Any) -> Any: ...


#: The host's port-reopen move: ``reopen(baud)`` reopens the port at the
#: given baud (the host owns the transport; this module never does).
Reopen = Callable[[int], Awaitable[None]]


@dataclass
class NegotiationResult:
    """The negotiated stream state plus the surfaced events."""

    baud: int
    slim: bool
    identify: codec.IdentifyInfo
    events: list[dict[str, str]] = field(default_factory=list)

    @property
    def negotiated(self) -> bool:
        return self.baud != codec.SUPPORTED_BAUDS[0] or self.slim


def _event(step: str, outcome: str, detail: str) -> dict[str, str]:
    return {"step": step, "outcome": outcome, "detail": detail}


class NegotiationFailed(RuntimeError):
    """IDENTIFY itself failed (no frame, transport error, bad CRC repeatedly).

    The negotiation cannot even establish the device's identity — no
    fallback state is known, the caller owns the reconnect.
    """


async def _read_frame(
    services: TransportServices, parser: codec.FrameParser, context: Any
) -> codec.Frame:
    """One complete frame off the transaction surface (exact-byte reads
    sized by the parser's ``bytes_wanted``; quiet-line ``b""`` re-raises
    as the timeout it is)."""
    while True:
        want = parser.bytes_wanted()
        transaction = {
            "kind": "stream_receive",
            "max_bytes": want,
            "termination": "lf",
            "exact_bytes": want,
        }
        data = (await services.transfer(transaction, context))["data"]
        if data:
            frames = parser.feed(data)
            if frames:
                return frames[0]
            continue
        raise TimeoutError("no reply by the deadline (quiet line)")


async def _exchange(
    services: TransportServices,
    parser: codec.FrameParser,
    context: Any,
    frame: codec.Frame,
) -> codec.Frame:
    """Send one request frame, then read the one reply frame."""
    request = codec.encode_frame(frame)
    await services.transfer({"kind": "stream_send", "data": request}, context)
    return await _read_frame(services, parser, context)


def _ack_matches(reply: codec.Frame, command: codec.FrameType, value: int) -> bool:
    """ACK correlation: echoed command + the expected value (SET_BAUD
    correlates on the LOW 16 bits — the ACK's u16 carries baud & 0xFFFF)."""
    if reply.type != int(codec.FrameType.ACK):
        return False
    echo, acked = codec.parse_ack(reply.payload)
    return echo == int(command) and acked == (value & 0xFFFF)


class _StepContext:
    """A per-step view of the host context with an earlier deadline.

    Exposes the inner context's dispatch marker (the operation was
    dispatched before negotiation started; the steps inherit it).
    """

    def __init__(self, inner: Any, deadline_monotonic: float) -> None:
        self._inner = inner
        self.deadline_monotonic = deadline_monotonic
        self.dispatched = getattr(inner, "dispatched", False)

    def is_cancelled(self) -> bool:
        return self._inner.is_cancelled()


async def _identify(
    services: TransportServices, parser: codec.FrameParser, context: Any
) -> codec.IdentifyInfo:
    """One IDENTIFY round trip; any deviation from IDENTIFY_RSP refuses
    (NegotiationFailed — the caller owns the reconnect)."""
    reply = await _exchange(
        services,
        parser,
        context,
        codec.Frame(type=int(codec.FrameType.IDENTIFY), seq=0, payload=b""),
    )
    if reply.type != int(codec.FrameType.IDENTIFY_RSP):
        raise NegotiationFailed(
            f"identify answered {codec.FrameType(reply.type).name}, not IDENTIFY_RSP"
        )
    return codec.parse_identify(reply.payload)


async def negotiate_stream(
    services: TransportServices,
    context: Any,
    *,
    reopen: Reopen,
    target_baud: int = codec.SUPPORTED_BAUDS[-1],
    switch_timeout_s: float = T_SWITCH_DEFAULT_S,
) -> NegotiationResult:
    """The §4.1 negotiation; see the module docstring for the sequence.

    ``context`` is the host's operation context (deadline +
    cancellation); every step runs under it. ``reopen(baud)`` is the
    host's port-reopen move (no-op for in-process transports that carry
    their baud state internally).
    """
    parser = codec.FrameParser()
    events: list[dict[str, str]] = []
    identify = await _identify(services, parser, context)
    events.append(
        _event(
            "identify",
            "ok",
            f"proto {identify.proto_version} fw {identify.fw_major}."
            f"{identify.fw_minor} caps {identify.caps}",
        )
    )
    if not identify.is_v2 or not (
        identify.caps & codec.CAP_SET_BAUD and identify.caps & codec.CAP_SLIM_FRAME
    ):
        events.append(_event("v2_attempt", "skipped", "device lacks v2 caps"))
        return NegotiationResult(
            baud=codec.SUPPORTED_BAUDS[0], slim=False, identify=identify, events=events
        )
    return await _attempt_v2(
        services,
        parser,
        context,
        identify,
        events,
        reopen=reopen,
        target_baud=target_baud,
        switch_timeout_s=switch_timeout_s,
    )


async def _attempt_v2(
    services: TransportServices,
    parser: codec.FrameParser,
    context: Any,
    identify: codec.IdentifyInfo,
    events: list[dict[str, str]],
    *,
    reopen: Reopen,
    target_baud: int,
    switch_timeout_s: float,
) -> NegotiationResult:
    """The one v2 attempt plus the fallback on any failure after IDENTIFY."""
    try:
        reply = await _exchange(
            services,
            parser,
            context,
            codec.Frame(
                type=int(codec.FrameType.SET_BAUD),
                seq=1,
                payload=codec.build_set_baud(target_baud),
            ),
        )
        if not _ack_matches(reply, codec.FrameType.SET_BAUD, target_baud):
            raise ValueError(f"SET_BAUD not ACKed as requested: {reply.type:#x}")
        await reopen(target_baud)
        events.append(_event("baud_switch", "applied", f"{target_baud} baud"))
    except Exception as exc:
        return await _fallback(
            services, parser, context, identify, events, reopen=reopen, switched=False, reason=exc
        )
    try:
        step = _StepContext(context, time.monotonic() + switch_timeout_s)
        reply = await _exchange(
            services,
            parser,
            step,
            codec.Frame(
                type=int(codec.FrameType.SET_FRAME_FORMAT),
                seq=2,
                payload=codec.build_set_frame_format(True),
            ),
        )
        if not _ack_matches(reply, codec.FrameType.SET_FRAME_FORMAT, 1):
            raise ValueError(f"SET_FRAME_FORMAT not ACKed as requested: {reply.type:#x}")
        events.append(_event("frame_format", "applied", "mask-sized (slim) frames"))
    except Exception as exc:
        return await _fallback(
            services, parser, context, identify, events, reopen=reopen, switched=True, reason=exc
        )
    return NegotiationResult(
        baud=target_baud, slim=True, identify=identify, events=events
    )


async def _fallback(
    services: TransportServices,
    parser: codec.FrameParser,
    context: Any,
    identify: codec.IdentifyInfo,
    events: list[dict[str, str]],
    *,
    reopen: Reopen,
    switched: bool,
    reason: Exception,
) -> NegotiationResult:
    """The legacy path: reopen at boot baud if the switch was applied,
    surface the fallback, then one confirm IDENTIFY (its failure is
    recorded as ``legacy_confirm: unresolved`` — the fallback still
    reports)."""
    if switched:
        await reopen(codec.SUPPORTED_BAUDS[0])
        events.append(_event("baud_switch", "reverted", "host reopened at 2 Mbps"))
    events.append(
        _event("v2_attempt", "fallback", f"{type(reason).__name__}: {reason}")
    )
    try:
        confirm = await _identify(services, parser, context)
        events.append(
            _event("legacy_confirm", "ok", f"proto {confirm.proto_version}")
        )
    except Exception as exc:
        events.append(
            _event("legacy_confirm", "unresolved", f"{type(exc).__name__}: {exc}")
        )
    return NegotiationResult(
        baud=codec.SUPPORTED_BAUDS[0], slim=False, identify=identify, events=events
    )
