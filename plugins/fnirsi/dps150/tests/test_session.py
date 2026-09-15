"""Session handshake and telemetry drain; synthetic transports only."""

import asyncio
from collections import deque

import pytest

from benchweave_fnirsi_dps150.client import Client, GetPayload, OperationTimeout, Transport
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


def test_drain_consumes_all_offered_frames_until_eof() -> None:
    """Re-pinned for the frame-atomic window: with EOF available, the drain
    collects every offered frame and ends early on b"" — the window never
    interrupts a frame, so nothing offered is left behind."""

    async def scenario() -> None:
        transport = ScriptedTransport([TELEMETRY] * 3, eof=True)
        packets = await drain_telemetry(transport, window_s=0.02)
        assert [packet.field for packet in packets] == [195, 195, 195]
        assert not transport.chunks
        assert transport.reads == 4  # three frames, then the EOF that ends

    asyncio.run(scenario())


@pytest.mark.parametrize("cut", range(1, 2 * len(TELEMETRY)))
def test_drain_reassembles_fragmented_frames(cut: int) -> None:
    stream = TELEMETRY + TELEMETRY

    async def scenario() -> None:
        transport = ScriptedTransport([stream[:cut], stream[cut:]], eof=True)
        packets = await drain_telemetry(transport, window_s=0.01)
        assert [packet.field for packet in packets] == [195, 195]

    asyncio.run(scenario())


def test_drain_discards_partial_tail() -> None:
    async def scenario() -> None:
        partial = bytes.fromhex("f0 a1 c3 0c")
        transport = ScriptedTransport([TELEMETRY, partial], eof=True)
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


class DelayedTailTransport:
    """Replays the WP10 W1 window edge at the session layer: one complete
    frame inside the window, whose successor's bytes only land after the
    window has closed. Schedule offsets are relative to construction."""

    def __init__(self, chunks_at: list[tuple[float, bytes]]) -> None:
        self._schedule = list(chunks_at)
        self._started = asyncio.get_running_loop().time()

    async def send(self, data: bytes) -> None:
        raise AssertionError("the session layer never sends while draining")

    async def receive(self, max_bytes: int) -> bytes:
        if not self._schedule:
            return b""
        at, chunk = self._schedule.pop(0)
        target = self._started + at
        now = asyncio.get_running_loop().time()
        if target > now:
            await asyncio.sleep(target - now)
        return chunk


def test_drain_window_edge_is_frame_atomic() -> None:
    """W1: a frame whose bytes straddle the window edge completes — the
    window bounds frame starts, never a frame already in flight. Old
    cancel-at-deadline behaviour abandoned the pending receive mid-frame
    and left the stream misaligned for the next reader."""

    async def scenario() -> None:
        transport = DelayedTailTransport(
            [
                (0.0, TELEMETRY),
                (0.25, TELEMETRY),
            ]
        )
        packets = await drain_telemetry(transport, window_s=0.1)
        assert [packet.field for packet in packets] == [195, 195]
        # The stream stays aligned: the next reader sees a clean EOF, not a
        # fragment of the frame the window edge interrupted.
        assert await transport.receive(260) == b""

    asyncio.run(scenario())


@pytest.mark.parametrize("window_s", [0, -1, True, float("nan"), float("inf"), "1", 3601])
def test_invalid_window_has_no_io(window_s: object) -> None:
    async def scenario() -> None:
        transport = ScriptedTransport([])
        with pytest.raises(ValueError):
            await drain_telemetry(transport, window_s=window_s)  # type: ignore[arg-type]
        assert transport.reads == 0

    asyncio.run(scenario())


def test_client_read_times_out_without_handshake(
    handshaking_transport: Transport,
) -> None:
    """The captured negative, replayed: a bare GET is dispatched, the
    un-handshaked device offers zero bytes, and the deadline expires."""

    async def scenario() -> None:
        client = Client(handshaking_transport, get_payload=GetPayload.ZERO)
        with pytest.raises(OperationTimeout) as excinfo:
            await client.read(222, timeout=0.05)
        assert excinfo.value.dispatch_started is True
        assert client.unusable

    asyncio.run(scenario())


def test_client_read_answers_after_handshake(
    handshaking_transport: Transport,
) -> None:
    """open_session wakes the device: GETs draw their reply first, then the
    captured telemetry cycle keeps streaming around them."""

    async def scenario() -> None:
        await open_session(handshaking_transport, delay_s=0)
        client = Client(handshaking_transport, get_payload=GetPayload.ZERO)
        assert await client.read(222, timeout=1) == "DPS-150"
        assert await client.read(195, timeout=1) == (0.0, 0.0, 0.0)
        packets = await drain_telemetry(handshaking_transport, window_s=0.05)
        fields = [packet.field for packet in packets]
        assert fields[:5] == [195, 192, 226, 227, 196]
        assert set(fields) == {195, 192, 226, 227, 196}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "preamble",
    [
        BAUD_NEGOTIATE + SESSION_OPEN,  # right frames, wrong order
        SESSION_OPEN,  # second frame never sent
        SESSION_OPEN + bytes.fromhex("f1 b0 00 01 05 07"),  # corrupt checksum
        b"\x00" * 12,  # noise
    ],
    ids=["reversed", "incomplete", "corrupt", "noise"],
)
def test_wrong_preamble_keeps_the_device_silent(
    handshaking_transport: Transport, preamble: bytes
) -> None:
    """Only the exact captured sequence wakes the device; anything else
    leaves it as silent as the twelve bare queries were."""

    async def scenario() -> None:
        await handshaking_transport.send(preamble)
        client = Client(handshaking_transport, get_payload=GetPayload.ZERO)
        with pytest.raises(OperationTimeout):
            await client.read(222, timeout=0.03)

    asyncio.run(scenario())
