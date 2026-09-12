"""Synthetic vectors only: no serial backend or hardware access."""

import asyncio
import importlib
from collections import deque
from typing import Any

import pytest


def api() -> Any:
    return importlib.import_module("benchweave.devices.fnirsi.dps150")


class MockTransport:
    def __init__(self, chunks: list[bytes] | None = None) -> None:
        self.chunks = deque(chunks or [])
        self.sent: list[bytes] = []
        self.reads = 0
        self.block_send = False
        self.send_error: Exception | None = None

    async def send(self, data: bytes) -> None:
        self.sent.append(data)
        if self.send_error:
            raise self.send_error
        if self.block_send:
            await asyncio.Future[None]()

    async def receive(self, max_bytes: int) -> bytes:
        self.reads += 1
        if not self.chunks:
            await asyncio.Future[None]()
        return self.chunks.popleft()


def test_combined_snapshot_preserves_unknown_bytes() -> None:
    async def scenario() -> None:
        p = api()
        # Synthetic 139-byte layout. Unknown tail is preserved, never interpreted.
        payload = (
            bytes.fromhex("0000a041 00004041 0000803f 00004041 0000803f 00004041 0000c841")
            + bytes(48)
            + bytes.fromhex("00007041 00000040 0000c841 0000a042 0000a040")
            + bytes(11)
            + bytes([1, 2, 1])
            + bytes.fromhex("ab")
            + bytes(28)
        )
        transport = MockTransport([response(255, payload)])
        snapshot = await p.Client(transport, get_payload=p.GetPayload.EMPTY).read(255, timeout=1)
        assert transport.sent == [bytes.fromhex("f1 a1 ff 00 ff")]
        assert (snapshot.voltage, snapshot.current, snapshot.power) == (12, 1, 12)
        assert (snapshot.ovp, snapshot.ocp, snapshot.opp) == (15, 2, 25)
        assert snapshot.enabled and snapshot.protection == "OCP" and snapshot.mode == "CV"
        assert snapshot.raw_payload == payload

    asyncio.run(scenario())


def test_fragmented_client_reply() -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport(
            [bytes([byte]) for byte in bytes.fromhex("f0 a1 c0 04 00 00 a0 41 a5")]
        )
        assert await p.Client(transport, get_payload=p.GetPayload.EMPTY).read(192, timeout=1) == 20
        assert len(transport.sent) == 1

    asyncio.run(scenario())


def test_overall_deadline_does_not_restart_per_fragment() -> None:
    class SlowTransport(MockTransport):
        async def receive(self, max_bytes: int) -> bytes:
            await asyncio.sleep(0.008)
            return await super().receive(max_bytes)

    async def scenario() -> None:
        p = api()
        transport = SlowTransport(
            [bytes([byte]) for byte in bytes.fromhex("f0 a1 c0 04 00 00 a0 41 a5")]
        )
        client = p.Client(transport, get_payload=p.GetPayload.EMPTY)
        with pytest.raises(p.OperationTimeout):
            await client.read(192, timeout=0.02)
        assert transport.chunks
        assert client.unusable and len(transport.sent) == 1

    asyncio.run(scenario())


def test_unsupported_read_is_rejected_before_io() -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport()
        client = p.Client(transport, get_payload=p.GetPayload.EMPTY)
        with pytest.raises(p.UnsupportedCommand):
            await client.read(225, timeout=1)
        assert not client.unusable and not transport.sent

    asyncio.run(scenario())


def test_explicit_dialect_required() -> None:
    with pytest.raises(ValueError):
        api().Client(MockTransport(), get_payload="auto")


def test_decoder_cannot_grow_after_error() -> None:
    p = api()
    decoder = p.FrameDecoder()
    with pytest.raises(p.ProtocolError):
        decoder.feed(b"x")
    with pytest.raises(p.ProtocolError):
        decoder.feed(b"x")
    assert not decoder.pending


def test_library_exists() -> None:
    assert importlib.util.find_spec("benchweave.devices.fnirsi.dps150") is not None


def test_literal_frames_and_minimum_frame() -> None:
    p = api()
    assert p.encode_packet(0xA1, 0xDE) == bytes.fromhex("f1 a1 de 00 de")
    assert p.encode_packet(0xB1, 0xC1, bytes.fromhex("00004041")) == bytes.fromhex(
        "f1 b1 c1 04 00 00 40 41 46"
    )
    packet = p.decode_packet(bytes.fromhex("f0 a1 de 00 de"))
    assert (packet.command, packet.field, packet.payload) == (0xA1, 0xDE, b"")


@pytest.mark.parametrize("cut", range(10))
def test_every_fragment_boundary(cut: int) -> None:
    p = api()
    frame = bytes.fromhex("f0 a1 c0 04 00 00 a0 41 a5")
    decoder = p.FrameDecoder()
    packets = decoder.feed(frame[:cut]) + decoder.feed(frame[cut:])
    assert len(packets) == 1
    assert p.decode_value(packets[0]) == 20.0
    assert not decoder.pending


def test_multiple_frames() -> None:
    p = api()
    packets = p.FrameDecoder().feed(bytes.fromhex("f0 a1 db 01 00 dc f0 a1 db 01 01 dd"))
    assert [p.decode_value(packet) for packet in packets] == [False, True]


@pytest.mark.parametrize(
    "wire",
    [
        "",
        "f0 a1",
        "f1 a1 de 00 de",
        "f0 a1 de 02 00",
        "f0 a1 de 00 df",
        "f0 a1 de 00 de 00",
        "f0 b1 de 00 de",
    ],
)
def test_malformed_packets(wire: str) -> None:
    with pytest.raises(api().ProtocolError):
        api().decode_packet(bytes.fromhex(wire))


def test_buffer_limits_and_noise() -> None:
    p = api()
    with pytest.raises(p.ProtocolError):
        p.FrameDecoder().feed(b"x")
    with pytest.raises(p.ProtocolError):
        p.FrameDecoder().feed(b"\xf0" * 261)
    with pytest.raises(p.ProtocolError):
        p.FrameDecoder(max_payload=12).feed(bytes.fromhex("f0 a1 ff 8b"))


@pytest.mark.parametrize(
    "command,field,payload",
    [
        (0xC1, 0, b"\x01"),
        (0xB0, 0, b"\x05"),
        (0xA1, 225, b""),
        (0xA1, 193, b""),
        (0xB1, 222, b""),
        (True, 222, b""),
    ],
)
def test_unsupported_packets(command: object, field: object, payload: bytes) -> None:
    with pytest.raises((ValueError, api().UnsupportedCommand)):
        api().encode_packet(command, field, payload)


def response(field: int, payload: bytes) -> bytes:
    # Malformation fixtures use an independent envelope builder; valid golden
    # exchanges below are literal bytes, not encoder round trips.
    return (
        bytes([0xF0, 0xA1, field, len(payload)])
        + payload
        + bytes([(field + len(payload) + sum(payload)) % 256])
    )


@pytest.mark.parametrize(
    "field,payload",
    [
        (192, bytes.fromhex("0000c07f")),
        (192, b"\0" * 3),
        (192, b"\0" * 5),
        (195, b"\0" * 8),
        (219, b"\x02"),
        (221, b"\x02"),
        (220, b"\x07"),
        (222, b"\xff"),
        (222, b""),
        (222, b"a\0b"),
        (255, b"\0" * 138),
    ],
)
def test_malformed_values(field: int, payload: bytes) -> None:
    p = api()
    with pytest.raises(p.ProtocolError):
        p.decode_value(p.decode_packet(response(field, payload)))


@pytest.mark.parametrize(
    "field,wire,expected",
    [
        (192, "f0 a1 c0 04 00 00 a0 41 a5", 20.0),
        (195, "f0 a1 c3 0c 00 00 40 41 00 00 80 3f 00 00 40 41 90", (12.0, 1.0, 12.0)),
        (219, "f0 a1 db 01 01 dd", True),
        (220, "f0 a1 dc 01 02 df", "OCP"),
        (221, "f0 a1 dd 01 01 df", "CV"),
        (222, "f0 a1 de 08 44 50 53 2d 31 35 30 00 90", "DPS-150"),
    ],
)
def test_exact_queries(field: int, wire: str, expected: object) -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport([bytes.fromhex(wire)])
        client = p.Client(transport, get_payload=p.GetPayload.EMPTY)
        assert transport.sent == []
        assert await client.read(field, timeout=1) == expected
        assert transport.sent == [bytes([0xF1, 0xA1, field, 0, field])]

    asyncio.run(scenario())


def test_explicit_zero_get_dialect() -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport([bytes.fromhex("f0 a1 db 01 00 dc")])
        client = p.Client(transport, get_payload=p.GetPayload.ZERO)
        assert await client.read(219, timeout=1) is False
        assert transport.sent == [bytes.fromhex("f1 a1 db 01 00 dc")]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field,value,wire",
    [
        (193, 12.0, "f1 b1 c1 04 00 00 40 41 46"),
        (194, 1.0, "f1 b1 c2 04 00 00 80 3f 85"),
        (209, 15.0, "f1 b1 d1 04 00 00 70 41 86"),
        (210, 2.0, "f1 b1 d2 04 00 00 00 40 16"),
        (219, False, "f1 b1 db 01 00 dc"),
        (219, True, "f1 b1 db 01 01 dd"),
    ],
)
def test_write_dispatch_only(field: int, value: object, wire: str) -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport()
        receipt = await p.Client(transport, get_payload=p.GetPayload.EMPTY).write(
            field, value, timeout=1
        )
        assert receipt.assurance == "dispatched"
        assert receipt.request == bytes.fromhex(wire)
        assert transport.sent == [bytes.fromhex(wire)]
        assert transport.reads == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "field,value",
    [
        (193, -1),
        (193, 31),
        (193, True),
        (193, "5"),
        (193, float("nan")),
        (193, float("inf")),
        (193, 0.001),
        (194, 5.1),
        (194, 0.0001),
        (219, 1),
        (219, "false"),
        (209, 31),
        (210, 5.2),
        (255, 0),
    ],
)
def test_invalid_write_has_no_io(field: int, value: object) -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport()
        with pytest.raises((ValueError, p.UnsupportedCommand)):
            await p.Client(transport, get_payload=p.GetPayload.EMPTY).write(field, value, timeout=1)
        assert transport.sent == []

    asyncio.run(scenario())


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf"), "1"])
def test_invalid_timeout_has_no_io(timeout: object) -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport()
        with pytest.raises(ValueError):
            await p.Client(transport, get_payload=p.GetPayload.EMPTY).read(192, timeout=timeout)
        assert transport.sent == []

    asyncio.run(scenario())


@pytest.mark.parametrize("chunks", [[], [b"\xf0\xa1"], [b"\xf0", b"\xa1", b"\xc0"]])
def test_receive_timeout_blocks_reuse(chunks: list[bytes]) -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport(chunks)
        client = p.Client(transport, get_payload=p.GetPayload.EMPTY)
        with pytest.raises(p.OperationTimeout) as exc:
            await client.read(192, timeout=0.01)
        assert exc.value.dispatch_started
        with pytest.raises(p.SessionUnusable):
            await client.read(192, timeout=1)
        assert len(transport.sent) == 1

    asyncio.run(scenario())


def test_send_timeout_and_no_replay() -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport()
        transport.block_send = True
        client = p.Client(transport, get_payload=p.GetPayload.EMPTY)
        with pytest.raises(p.OperationTimeout) as exc:
            await client.write(219, True, timeout=0.01)
        assert exc.value.dispatch_started
        assert client.unusable
        assert len(transport.sent) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "wire",
    [
        "f0 a1 db 01 00 dc",  # wrong field
        "f0 a1 c0 04 00 00 a0 41 a6",  # checksum
        "f0 a1 c0 04 00 00 a0 41 a5 f0",  # trailing partial frame
        "f0 a1 c0 04 00 00 a0 41 a5 f0 a1 c0 04 00 00 a0 41 a5",  # duplicate
        "",  # EOF
    ],
)
def test_bad_exchange_blocks_reuse(wire: str) -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport([bytes.fromhex(wire)])
        client = p.Client(transport, get_payload=p.GetPayload.EMPTY)
        with pytest.raises((p.ProtocolError, ConnectionError)):
            await client.read(192, timeout=1)
        with pytest.raises(p.SessionUnusable):
            await client.read(192, timeout=1)
        assert len(transport.sent) == 1

    asyncio.run(scenario())


def test_cancellation_and_concurrent_calls() -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport()
        client = p.Client(transport, get_payload=p.GetPayload.EMPTY)
        task = asyncio.create_task(client.read(192, timeout=1))
        await asyncio.sleep(0)
        with pytest.raises(p.OperationBusy):
            await client.read(192, timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert client.unusable
        assert len(transport.sent) == 1

    asyncio.run(scenario())


def test_transport_failure_blocks_reuse() -> None:
    async def scenario() -> None:
        p = api()
        transport = MockTransport()
        transport.send_error = ConnectionError("mock disconnect")
        client = p.Client(transport, get_payload=p.GetPayload.EMPTY)
        with pytest.raises(ConnectionError):
            await client.write(219, False, timeout=1)
        assert client.unusable
        assert len(transport.sent) == 1

    asyncio.run(scenario())
