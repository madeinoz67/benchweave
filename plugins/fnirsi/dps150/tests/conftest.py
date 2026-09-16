"""Pinned local test inputs and the shared synthetic device mock; tests never
download contracts."""

import asyncio
import hashlib
import json
import struct
from collections import deque
from pathlib import Path

import pytest

from benchweave_fnirsi_dps150.codec import GET
from benchweave_fnirsi_dps150.session import BAUD_NEGOTIATE, SESSION_OPEN


def pytest_sessionstart() -> None:
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "contracts/lock.json").read_text())
    for name, expected in lock["sha256"].items():
        path = root / "contracts/otdp-0.1.0" / name
        if not path.is_file():
            raise RuntimeError("Run python scripts/fetch_contracts.py before the offline tests")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Pinned contract hash mismatch: {name}")


# The connect sequence the live device demanded (connect-v2.jsonl), exactly.
_HANDSHAKE = SESSION_OPEN + BAUD_NEGOTIATE

# connect-v2.jsonl, "baud-negotiate" reply window: the five-frame telemetry
# cycle a woken device streams (~2 Hz), byte-verbatim — 195 output V/A/W,
# 192 input voltage, 226/227 reported limits, 196 temperature.
_TELEMETRY_CYCLE: tuple[bytes, ...] = (
    bytes.fromhex("f0 a1 c3 0c 00 00 00 00 00 00 00 00 00 00 00 00 cf"),
    bytes.fromhex("f0 a1 c0 04 35 89 a0 41 63"),
    bytes.fromhex("f0 a1 e2 04 9b ef 9e 41 4f"),
    bytes.fromhex("f0 a1 e3 04 33 33 a3 40 30"),
    bytes.fromhex("f0 a1 c4 04 93 a2 ab 41 e9"),
)


def _snapshot_payload() -> bytes:
    """Minimal codec-valid 139-byte ALL payload; never captured live."""
    buf = bytearray(139)  # zeroed: output off, protection normal, mode CC
    buf[0:28] = struct.pack("<7f", 20.1, 0.0, 0.0, 0.0, 0.0, 0.0, 21.3)
    buf[76:96] = struct.pack("<5f", 30.0, 5.0, 30.0, 5.0, 30.0)
    return bytes(buf)


# GET reply payloads by field. Captured values are byte-verbatim from
# connect-v2.jsonl (identity answers and the first telemetry cycle); the
# rest are minimal codec-valid stand-ins for fields the live session never
# asked about.
_GET_PAYLOADS: dict[int, bytes] = {
    192: bytes.fromhex("35 89 a0 41"),  # input ~20.1 V (captured)
    195: bytes(12),  # 0 V / 0 A / 0 W, output off (captured)
    196: bytes.fromhex("93 a2 ab 41"),  # ~21.3 degC (captured)
    217: struct.pack("<f", 0.0),
    218: struct.pack("<f", 0.0),
    219: b"\x00",  # output off
    220: b"\x00",  # normal
    221: b"\x00",  # CC
    222: b"DPS-150",  # captured identity answer
    223: b"V1.0",  # captured
    224: b"V1.2",  # captured
    226: bytes.fromhex("9b ef 9e 41"),  # ~19.74 V reported limit (captured)
    227: bytes.fromhex("33 33 a3 40"),  # 5.1 A reported limit (captured)
    255: _snapshot_payload(),
}


class HandshakingTransport:
    """The live capture's session behaviour as a transport: silent until the
    exact connect sequence, then answering.

    first-contact-negative.jsonl pinned twelve bare GETs (six bauds, both
    dialects) that drew zero reply bytes; connect-v2.jsonl shows the device
    answering only after SESSION_OPEN then BAUD_NEGOTIATE. ``receive``
    therefore stays pending — zero bytes offered, like a serial read against
    a silent device — while the concatenated bytes sent so far form a prefix
    of exactly that handshake. A preamble that diverges from it (wrong
    order, missing or corrupt frame, noise) latches the transport silent
    forever; the device does not resynchronise.

    Once woken it answers each GET with a valid reply for the requested
    field first, then keeps offering the captured five-frame telemetry
    cycle, one whole frame per receive. SETs and session frames are recorded
    but draw no reply, matching the client's dispatch-only writes; a GET for
    a field with no configured payload is a mock-configuration error.

    ``trailing_telemetry`` mode models the steady-state streaming device from
    live-stream.jsonl "diagnosis-final": the ~2 Hz stream shares the
    commanded receive window with the reply, so each GET's answer window
    holds telemetry ahead of and behind the reply (connect-v2.jsonl
    identity-222 captured one 171-byte window with the reply plus fifteen
    telemetry frames). The frame in flight when the pre-call drain closes is
    pinned to the cycle's captured 195 V/A/W lead — its live position in the
    cycle is a timing race, but a regression test must present the window
    that poisons deterministically — and the trailing frame continues the
    cycle.
    """

    def __init__(
        self,
        *,
        trailing_telemetry: bool = False,
        trailing_tail: bool = True,
        get_overrides: dict[int, bytes] | None = None,
    ) -> None:
        self.sent: list[bytes] = []
        self.awake = False
        self.trailing_telemetry = trailing_telemetry
        self.trailing_tail = trailing_tail
        self._get_overrides = get_overrides or {}
        self._diverged = False
        self._preamble = bytearray()
        self._replies: deque[bytes] = deque()
        self._cycle = 0

    async def send(self, data: bytes) -> None:
        self.sent.append(data)
        if self.awake:
            self._answer(data)
            return
        if self._diverged:
            return
        self._preamble.extend(data)
        seen = bytes(self._preamble)
        limit = min(len(seen), len(_HANDSHAKE))
        if seen[:limit] != _HANDSHAKE[:limit]:
            self._diverged = True
        elif len(seen) >= len(_HANDSHAKE):
            if len(seen) > len(_HANDSHAKE):
                # Noise appended to the completing send — modeled
                # conservatively; the captures do not settle noise after the
                # handshake. The captured wake sequence is exactly two
                # frames, and surplus bytes diverge the preamble rather than
                # waking and silently dropping them.
                self._diverged = True
            else:
                self.awake = True

    async def receive(self, max_bytes: int) -> bytes:
        if not self.awake:
            await asyncio.Future[None]()
        if self._replies:
            reply = self._replies.popleft()
            assert len(reply) <= max_bytes  # Transport contract: bounded offers
            return reply
        frame = _TELEMETRY_CYCLE[self._cycle % len(_TELEMETRY_CYCLE)]
        self._cycle += 1
        assert len(frame) <= max_bytes  # Transport contract: bounded offers
        return frame

    def _answer(self, data: bytes) -> None:
        if data[:2] != bytes((0xF1, GET)):
            return
        payload = self._get_overrides.get(data[2])
        if payload is None:
            try:
                payload = _GET_PAYLOADS[data[2]]
            except KeyError:
                raise ValueError(f"no HandshakingTransport reply for field {data[2]}") from None
        body = bytes((data[2], len(payload))) + payload
        reply = bytes((0xF0, GET)) + body + bytes((sum(body) % 256,))
        if not self.trailing_telemetry:
            self._replies.append(reply)
            return
        front = _TELEMETRY_CYCLE[0]
        entry = front + reply
        if self.trailing_tail:
            entry += _TELEMETRY_CYCLE[self._cycle % len(_TELEMETRY_CYCLE)]
            self._cycle += 1
        self._replies.append(entry)


@pytest.fixture
def handshaking_transport() -> HandshakingTransport:
    """A device that stays silent until the exact captured handshake."""
    return HandshakingTransport()


@pytest.fixture
def trailing_transport() -> HandshakingTransport:
    """A woken device whose commanded windows interleave live telemetry.

    Trailing-telemetry mode: every GET reply shares its receive window with
    the ~2 Hz stream — one frame in flight ahead of the reply, the cycle
    continuing behind it — the shape that poisoned the live session in
    live-stream.jsonl "diagnosis-final".
    """
    return HandshakingTransport(trailing_telemetry=True)


@pytest.fixture
def same_field_transport() -> HandshakingTransport:
    """A woken device whose GET reply for a field differs from its telemetry
    for the same field — the W2 pin: with no reply marker in the protocol,
    the first same-field frame in the commanded window IS the reply, so the
    telemetry frame must win and the superseded reply must surface through
    the absorb path as telemetry."""
    overrides = {195: struct.pack("<3f", 2.5, 0.5, 1.25)}
    return HandshakingTransport(
        trailing_telemetry=True, trailing_tail=False, get_overrides=overrides
    )
