"""Session handshake and telemetry drain; synthetic transports only."""

import asyncio
from collections import deque

import pytest

from benchweave_fnirsi_dps150.codec import FrameDecoder  # noqa: F401 (shape check)
from benchweave_fnirsi_dps150.session import (
    BAUD_NEGOTIATE,
    SESSION_OPEN,
    drain_telemetry,
    open_session,
)

# One real telemetry frame from the live capture (connect-v2.jsonl): field
# 195 (0xC3), 12 zero payload bytes, valid checksum — output off, unloaded.
TELEMETRY = bytes.fromhex("f0 a1 c3 0c 00 00 00 00 00 00 00 00 00 00 00 00 cf")


class HandshakeTransport:
    """Records sends; receive is never expected (handshake is fire-and-forget)."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def receive(self, max_bytes: int) -> bytes:
        return b""


class ScriptedTransport:
    """Yields scripted chunks, then blocks forever or reports EOF."""

    def __init__(self, chunks: list[bytes], *, eof: bool = False) -> None:
        self.chunks = deque(chunks)
        self.reads = 0
        self.eof = eof

    async def send(self, data: bytes) -> None:
        raise AssertionError("the session layer never sends while draining")

    async def receive(self, max_bytes: int) -> bytes:
        self.reads += 1
        if not self.chunks:
            if self.eof:
                return b""
            await asyncio.Future[None]()
        return self.chunks.popleft()


def test_open_session_sends_evidence_frames_in_order() -> None:
    async def scenario() -> None:
        transport = HandshakeTransport()
        delays: list[float] = []

        async def fake_sleep(s: float) -> None:
            delays.append(s)

        await open_session(transport, delay_s=0.05, _sleep=fake_sleep)
        assert transport.sent == [SESSION_OPEN, BAUD_NEGOTIATE]
        assert bytes.fromhex("f1 c1 00 01 01 02") == SESSION_OPEN
        assert bytes.fromhex("f1 b0 00 01 05 06") == BAUD_NEGOTIATE
        assert delays == [0.05, 0.05]

    asyncio.run(scenario())


def test_open_session_default_pacing_uses_real_sleep() -> None:
    async def scenario() -> None:
        transport = HandshakeTransport()
        await open_session(transport, delay_s=0)
        assert transport.sent == [SESSION_OPEN, BAUD_NEGOTIATE]

    asyncio.run(scenario())


def test_drain_collects_frames_until_window_ends() -> None:
    async def scenario() -> None:
        transport = ScriptedTransport([TELEMETRY] * 3)
        packets = await drain_telemetry(transport, window_s=0.02)
        assert [packet.field for packet in packets] == [195, 195, 195]
        assert not transport.chunks

    asyncio.run(scenario())


@pytest.mark.parametrize("cut", range(1, 2 * len(TELEMETRY)))
def test_drain_reassembles_fragmented_frames(cut: int) -> None:
    stream = TELEMETRY + TELEMETRY

    async def scenario() -> None:
        transport = ScriptedTransport([stream[:cut], stream[cut:]])
        packets = await drain_telemetry(transport, window_s=0.01)
        assert [packet.field for packet in packets] == [195, 195]

    asyncio.run(scenario())


def test_drain_discards_partial_tail() -> None:
    async def scenario() -> None:
        partial = bytes.fromhex("f0 a1 c3 0c")
        transport = ScriptedTransport([TELEMETRY, partial])
        packets = await drain_telemetry(transport, window_s=0.01)
        assert [packet.field for packet in packets] == [195]

    asyncio.run(scenario())


def test_drain_stops_at_eof_before_window_edge() -> None:
    async def scenario() -> None:
        transport = ScriptedTransport([TELEMETRY, TELEMETRY], eof=True)
        started = asyncio.get_running_loop().time()
        packets = await drain_telemetry(transport, window_s=2)
        assert [packet.field for packet in packets] == [195, 195]
        assert asyncio.get_running_loop().time() - started < 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "window_s", [0, -1, True, float("nan"), float("inf"), "1", 3601]
)
def test_invalid_window_has_no_io(window_s: object) -> None:
    async def scenario() -> None:
        transport = ScriptedTransport([])
        with pytest.raises(ValueError):
            await drain_telemetry(transport, window_s=window_s)  # type: ignore[arg-type]
        assert transport.reads == 0

    asyncio.run(scenario())
