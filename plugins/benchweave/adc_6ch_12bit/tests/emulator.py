# author: Stephen Eaton
"""The scripted ADC device emulator (issue #393, design §4.4).

Generalises the contributor fork's proven ``FakeBoardTransport`` shape:
a device-side state machine that parses real frames and answers like the
v2 firmware. Scriptable variants::

    v2             — full v2 device (IDENTIFY v2 7 B, SET_BAUD /
                     SET_FRAME_FORMAT with the T_revert revert guard,
                     mask-sized frames)
    v1             — a v1 device: 5 B IDENTIFY_RSP, NAK (bad command) on
                     0x0A/0x0B, fixed 16 B SAMPLE payloads
    v2_nak_baud    — identifies v2 with caps set but NAKs SET_BAUD
    silent_revert  — applies the baud switch then answers nothing; its
                     own T_revert later reverts it to boot state
    v2 + drop_list — a streaming source that skips the planted counters
    v2 + legacy_override — streams legacy frames after a slim negotiation
                     (the LEN/mask mismatch source)

Two surfaces, one state machine:

- the low byte surface (``read``/``write``) — what a serial link or the
  A3 pty pump drives (the device side of a real port);
- the transaction surface (:class:`EmulatorServices`) — an in-process
  host-side OTDP section 8.1 shim over the same emulator, so the
  negotiation cells run with no port and no SDK import.

The CRC is the table-driven one (``codec.crc16_table``) for fidelity to
the firmware plan and emulator speed; the codec tests pin table ==
bitwise.
"""

from __future__ import annotations

import time
from typing import Any

from adc_wire import codec

#: capability bits this emulator advertises as a v2 device
EMU_CAPS = codec.CAP_SET_BAUD | codec.CAP_SLIM_FRAME
#: emulator firmware version (the v2 firmware line)
FW_MAJOR, FW_MINOR = 0, 3

VARIANTS = ("v2", "v1", "v2_nak_baud", "silent_revert")


class AdcEmulator:
    """The v2/v1 device behavior behind either surface.

    ``t_revert_s`` scales the device revert guard (default the spec's
    250 ms hint; the silent-revert cells shrink it).
    """

    def __init__(
        self,
        io: Any = None,
        *,
        variant: str = "v2",
        t_revert_s: float = 0.25,
        drop_list: tuple[int, ...] = (),
        legacy_override: bool = False,
    ) -> None:
        if variant not in VARIANTS:
            raise ValueError(f"unknown variant: {variant}")
        self._io = io
        self.variant = variant
        self.t_revert_s = t_revert_s
        self.drop_list = tuple(sorted(drop_list))
        self.legacy_override = legacy_override
        self.baud = codec.SUPPORTED_BAUDS[0]
        self.host_baud = codec.SUPPORTED_BAUDS[0]  # M7 (fold): the host side
        self.garbled_bytes = 0
        self.slim = False
        self.streaming = False
        self.channel_mask = codec.CHANNEL_MASK_ALL
        self.averaging = 0
        self.counter = 0
        self.commands: list[tuple[int, bytes]] = []
        self.reverts: list[float] = []
        self._out = bytearray()
        self._parser = codec.FrameParser()
        self._revert_deadline: float | None = None
        self._silent = False
        self.drop_ack_once: int | None = None  # M8 (fold): frame type whose next ACK is lost
        self._drop_armed = False

    # -- low byte surface (the device side of a port) ----------------------

    def write(self, data: bytes) -> None:
        """Host -> device bytes: parse frames, answer like firmware. A
        write from a host whose baud disagrees with the device's is
        line garbage (M7, fold): dropped and counted, never parsed."""
        now = time.monotonic()
        if self._revert_deadline is not None and now >= self._revert_deadline:
            self._revert()
        if self.host_baud != self.baud:
            self.garbled_bytes += len(data)
            return
        for frame in self._parser.feed(bytes(data)):
            self._handle(frame)

    def read(self, size: int = 4096) -> bytes:
        """Device -> host bytes: serve queued replies; while streaming,
        generate one sample frame per call (the sustained source). A due
        revert guard fires here too (the deadline is time-driven, not
        byte-driven)."""
        now = time.monotonic()
        if self._revert_deadline is not None and now >= self._revert_deadline:
            self._revert()
        if self.streaming:
            self._out += self._stream_frame()
        out = bytes(self._out[:size])
        del self._out[:size]
        return out

    # -- device behaviors ----------------------------------------------------

    def _handle(self, frame: codec.Frame) -> None:
        now = time.monotonic()
        self.commands.append((frame.type, frame.payload))
        if self._revert_deadline is not None and now >= self._revert_deadline:
            self._revert()
        if self.variant == "silent_revert" and self._silent:
            return  # the dead-air window: answers nothing, disarms nothing
        if self._revert_deadline is not None:
            self._revert_deadline = None  # any valid frame disarms the guard
        if self.variant == "silent_revert" and self._silent:
            return  # the dead-air window: answers nothing until the revert fires
        if frame.type == int(codec.FrameType.IDENTIFY):
            self._queue_identify(frame.seq)
        elif frame.type == int(codec.FrameType.SET_BAUD):
            self._set_baud(frame)
        elif frame.type == int(codec.FrameType.SET_FRAME_FORMAT):
            self._set_frame_format(frame)
        elif frame.type == int(codec.FrameType.SET_AVERAGING):
            self.averaging = (
                int.from_bytes(frame.payload[:2], "little")
                if len(frame.payload) >= 2
                else 0
            )
            self._out += self._encode(codec.Frame(
                type=int(codec.FrameType.ACK), seq=0,
                payload=bytes((int(codec.FrameType.SET_AVERAGING),))
                + self.averaging.to_bytes(2, "little"),
            ))
        elif frame.type == int(codec.FrameType.SET_CHANNELS):
            if len(frame.payload) < 1 or frame.payload[0] == 0 or frame.payload[0] > 0x3F:
                self._out += self._nak(codec.FrameType.SET_CHANNELS, codec.ErrorCode.BAD_PARAMETER)
            else:
                self.channel_mask = frame.payload[0]
                self._out += self._ack(codec.FrameType.SET_CHANNELS, self.channel_mask)
        elif frame.type == int(codec.FrameType.START_STREAM):
            self.streaming = True
            self._out += self._ack(codec.FrameType.START_STREAM, 0)
        elif frame.type == int(codec.FrameType.STOP_STREAM):
            self.streaming = False
            self._out += self._ack(codec.FrameType.STOP_STREAM, 0)
        elif frame.type == int(codec.FrameType.SAMPLE_ONCE):
            self.streaming = False
            self._out += self._ack(codec.FrameType.SAMPLE_ONCE, 0)
            self._out += self._stream_frame()
        elif frame.type == int(codec.FrameType.RESET):
            self.streaming = False
            self.counter = 0  # M9 (fold): the firmware reboots its counter
            self._out += self._ack(codec.FrameType.RESET, 0)
        else:
            self._out += self._nak(codec.FrameType(frame.type), codec.ErrorCode.BAD_COMMAND)

    def _stream_frame(self) -> bytes:
        """One SAMPLE frame for the stream (mask-sized when slim)."""
        while self.counter in self.drop_list:
            self.counter += 1  # planted gaps: those counters never hit the wire
        if not self.slim or self.legacy_override:
            values = tuple(
                (self.counter * 7 + 100 * c) & 0x0FFF if self.channel_mask & (1 << c) else 0
                for c in range(codec.N_CHANNELS)
            )
            payload = self.counter.to_bytes(4, "little") + b"".join(
                v.to_bytes(2, "little") for v in values
            )
        else:
            active = [c for c in range(codec.N_CHANNELS) if self.channel_mask & (1 << c)]
            values = tuple(
                (self.counter * 7 + 100 * c) & 0x0FFF for c in active
            )
            payload = codec.build_sample_payload(self.counter, values)
        self.counter += 1
        return self._encode(codec.Frame(
            type=int(codec.FrameType.SAMPLE), seq=0, payload=payload
        ))

    def _encode(self, frame: codec.Frame) -> bytes:
        return codec.encode_frame(frame)

    def _ack(self, command: codec.FrameType, value: int) -> bytes:
        frame = codec.Frame(
            type=int(codec.FrameType.ACK), seq=0,
            payload=bytes((int(command),)) + value.to_bytes(2, "little"),
        )
        if self.drop_ack_once is not None and int(command) == int(self.drop_ack_once):
            self.drop_ack_once = None  # one shot: the NEXT matching ACK is lost
            return b""
        return self._encode(frame)

    def _nak(self, command: codec.FrameType, error: int) -> bytes:
        return self._encode(codec.Frame(
            type=int(codec.FrameType.NAK), seq=0,
            payload=bytes((int(command), error)),
        ))

    def _queue_identify(self, seq: int) -> None:
        if self.variant == "v1":
            payload = bytes((1, 0, 2, codec.N_CHANNELS, 12))
        else:
            payload = bytes(
                (2, FW_MAJOR, FW_MINOR, codec.N_CHANNELS, 12)
            ) + EMU_CAPS.to_bytes(2, "little")
        self._out += self._encode(codec.Frame(
            type=int(codec.FrameType.IDENTIFY_RSP), seq=seq, payload=payload
        ))

    def _set_baud(self, frame: codec.Frame) -> None:
        if self.variant in ("v1", "v2_nak_baud"):
            self._out += self._nak(frame.type, codec.ErrorCode.BAD_COMMAND)
            return
        if len(frame.payload) < 4:
            self._out += self._nak(frame.type, codec.ErrorCode.BAD_PARAMETER)
            return
        baud = int.from_bytes(frame.payload[:4], "little")
        if baud not in codec.SUPPORTED_BAUDS:
            self._out += self._nak(frame.type, codec.ErrorCode.BAD_PARAMETER)
            return
        # ACK at the CURRENT baud first; the switch applies after the ACK
        # is queued (the firmware's apply-after-TC, in-memory). The revert
        # guard arms with the switch and disarms on SET_FRAME_FORMAT's ACK.
        self._out += self._ack(codec.FrameType.SET_BAUD, baud & 0xFFFF)
        self.baud = baud
        self._silent = self.variant == "silent_revert"
        self._revert_deadline = (
            None if baud == codec.SUPPORTED_BAUDS[0]
            else time.monotonic() + self.t_revert_s
        )

    def _set_frame_format(self, frame: codec.Frame) -> None:
        if self.variant == "v1":
            self._out += self._nak(frame.type, codec.ErrorCode.BAD_COMMAND)
            return
        if len(frame.payload) < 1 or frame.payload[0] not in (0, 1):
            self._out += self._nak(frame.type, codec.ErrorCode.BAD_PARAMETER)
            return
        slim = frame.payload[0] == 1
        self._out += self._ack(codec.FrameType.SET_FRAME_FORMAT, 1 if slim else 0)
        self.slim = slim
        self._revert_deadline = None  # negotiation completed: guard disarmed
        self._silent = False

    def _revert(self) -> None:
        """T_revert expired with no valid frame: back to boot state."""
        self.baud = codec.SUPPORTED_BAUDS[0]
        self.slim = False
        self._silent = False
        self._revert_deadline = None
        self.reverts.append(time.monotonic())


class EmulatorServices:
    """An in-process host-side OTDP section 8.1 shim over one emulator.

    Mirrors the SDK backend's receive discipline (the cells' semantics):
    exact_bytes precedence; a terminated frame within max_bytes; an
    unfinished receive stays buffered; a quiet line answers b""; a
    deadline with a partial buffered raises TimeoutError; the field sets
    are the closed section-8.1 sets. No dispatch marker requirement (the
    marker discipline is the SDK backend's conformance posture; this shim
    serves the DEVICE side of the conversation).
    """

    _FIELDS = {
        "stream_send": {"kind", "data"},
        "stream_receive": {"kind", "max_bytes", "termination", "exact_bytes"},
        "stream_exchange": {"kind", "data", "max_bytes", "termination", "exact_bytes"},
    }

    def __init__(self, emulator: AdcEmulator, *, quiet_s: float = 0.02) -> None:
        self.emulator = emulator
        self._ring = bytearray()
        self.quiet_s = quiet_s

    async def transfer(self, transaction: dict[str, Any], context: Any) -> dict[str, Any]:
        kind = transaction.get("kind")
        if kind not in self._FIELDS or set(transaction) != self._FIELDS[kind]:
            raise ValueError(f"not a section 8.1 stream transaction: {sorted(transaction)}")
        if kind != "stream_receive":
            self.emulator.write(transaction["data"])
        if kind == "stream_send":
            return {}
        max_bytes = transaction["max_bytes"]
        termination = transaction["termination"].encode()
        exact = transaction["exact_bytes"] or 0
        deadline = context.deadline_monotonic
        quiet_until = time.monotonic() + self.quiet_s
        while True:
            data = self.emulator.read(4096)
            self._ring += data
            if exact:
                if len(self._ring) >= exact:
                    out = bytes(self._ring[:exact])
                    del self._ring[:exact]
                    return {"data": out}
            else:
                end = self._ring[:max_bytes].find(termination)
                if end >= 0:
                    out = bytes(self._ring[: end + len(termination)])
                    del self._ring[: end + len(termination)]
                    return {"data": out}
                if len(self._ring) >= max_bytes:
                    del self._ring[:max_bytes]
                    raise ValueError(f"no terminator within {max_bytes} bytes")
            if not self._ring and time.monotonic() >= quiet_until:
                return {"data": b""}  # the quiet line, before the deadline
            if time.monotonic() >= deadline:
                raise TimeoutError("receive deadline expired")
            time.sleep(0.001)
