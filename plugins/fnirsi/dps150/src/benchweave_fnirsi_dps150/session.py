"""Evidence-backed session handshake and telemetry drain for the DPS-150.

Real-hardware capture, first contact 2026-09-15, committed at
``fixtures/protocols/dps150/``: the device is silent until a two-frame
session handshake is sent (twelve bare field queries across six bauds drew
zero bytes — ``first-contact-negative.jsonl``), after which it answers and
streams unsolicited telemetry (``connect-v2.jsonl``). The handshake frames
below are hand-derived constants, deliberately NOT routed through
``codec.encode_packet``: the codec's supported-subset guard excludes the
C1/B0 commands by design, and that guard stays intact.

Preconditions proven by the same capture: an exclusively owned,
already-established transport with RTS/CTS hardware flow control enabled
(the negative capture ran without it and got silence), and fire-and-forget
frames paced ~50 ms apart — neither frame draws a reply of its own; the
device's wake is proven only by the traffic that follows.
"""

import asyncio
import contextlib
import math
from collections.abc import Awaitable, Callable

from .client import Transport
from .codec import FrameDecoder, Packet

# connect-v2.jsonl step "session-open", sent byte-verbatim:
# "f1 c1 00 01 01 02". Header 0xF1, command 0xC1, then the codec's framing
# law — body (field 0x00, length 0x01, payload 0x01), checksum
# sum(body) % 256 = (0x00 + 0x01 + 0x01) = 0x02. Drew no reply of its own.
SESSION_OPEN: bytes = bytes.fromhex("f1 c1 00 01 01 02")

# connect-v2.jsonl step "baud-negotiate", sent byte-verbatim:
# "f1 b0 00 01 05 06". Header 0xF1, command 0xB0, body (field 0x00,
# length 0x01, payload 0x05), checksum (0x00 + 0x01 + 0x05) = 0x06. The
# device's unsolicited telemetry stream begins in this step's reply window.
BAUD_NEGOTIATE: bytes = bytes.fromhex("f1 b0 00 01 05 06")


async def open_session(
    transport: Transport,
    *,
    delay_s: float = 0.05,
    _sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Send the two-frame session handshake with pacing; fire-and-forget.

    Neither frame is acknowledged and no session state is established here
    — the device's wake is proven only by subsequent traffic, so nothing
    is received and errors surface only from the transport or the sleeper.
    ``delay_s`` (default ~50 ms, as paced in the capture) separates the
    frames; ``_sleep`` exists so tests can pin the pacing without
    wall-clock waits.
    """
    await transport.send(SESSION_OPEN)
    await _sleep(delay_s)
    await transport.send(BAUD_NEGOTIATE)
    await _sleep(delay_s)


async def drain_telemetry(transport: Transport, *, window_s: float) -> list[Packet]:
    """Collect complete packets for one wall-clock-bounded receive window.

    The drain-before-commanded-call primitive for the adapter: the live
    device streams unsolicited telemetry around its command replies, so a
    caller drains whatever complete frames arrive inside ``window_s`` and
    discards the trailing partial frame. EOF (b"") ends the drain early; a
    receive still pending at the deadline is cancelled. Malformed input is
    not discarded — the strict decoder's ProtocolError propagates, because
    the drain's job is to empty a healthy stream, not to hide corruption.
    """
    if (
        type(window_s) not in (float, int)
        or not 0 < window_s <= 3600
        or not math.isfinite(window_s)
    ):
        raise ValueError("Window must be a finite positive number <=3600 seconds")
    deadline = asyncio.get_running_loop().time() + window_s
    decoder = FrameDecoder()
    packets: list[Packet] = []
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout_at(deadline):
            while True:
                # A yield enforces the deadline even if a mock/provider
                # returns fragments synchronously without yielding to the
                # event loop.
                await asyncio.sleep(0)
                chunk = await transport.receive(260)
                if chunk == b"":
                    break
                packets.extend(decoder.feed(chunk))
    return packets
