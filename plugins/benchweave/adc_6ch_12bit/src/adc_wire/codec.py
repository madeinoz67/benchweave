# author: Stephen Eaton
"""The ADC board wire codec, dual-format (protocol v2).

Reference host-side implementation of the wire family described in
``plugins/benchweave/adc_6ch_12bit/docs/wire-protocol.md``. v1 frames
remain valid on the wire; the negotiated frame format selects which
SAMPLE encoding a stream carries. Pure codec: no I/O, no device.

Frame shape (v1 and v2 share it)::

    [0xAA 0x55][type][seq][len][payload(0..len)][crc16 LE]

- CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflect, no xorout),
  over type..payload, little-endian on the wire.
- v1 SAMPLE payload: fixed 16 B (u32 counter + 6 x u16).
- v2 SAMPLE payload: 4 + 2 x n_active B (mask-sized); the LEN byte already
  encodes the width, so a decoder cross-checks LEN against the negotiated
  mask popcount — mismatch means the stream and the negotiation disagree
  (resync + protocol error).
- v2 adds SET_BAUD (0x0A, u32 LE) and SET_FRAME_FORMAT (0x0B, u8:
  0 = legacy fixed, 1 = mask-sized).
- IDENTIFY_RSP: 5 B (proto 1) or 7 B (proto 2: + caps u16 LE, bit0
  SET_BAUD, bit1 slim frame; the rest reserved zero).

The parser is the proven incremental resync discipline: on a corrupt byte
or bad CRC it drops forward to the next SYNC and keeps going, counting
errors. Gaps in the SAMPLE counter stream are detected by
:mod:`adc_wire.gaps`, never here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

SYNC = b"\xaa\x55"
HEADER_LEN = 5  # sync(2) + type(1) + seq(1) + len(1)
CRC_LEN = 2
MAX_PAYLOAD = 255
MAX_FRAME = HEADER_LEN + MAX_PAYLOAD + CRC_LEN

N_CHANNELS = 6
CHANNEL_MASK_ALL = 0b0011_1111
#: The fixed v1 SAMPLE payload size (u32 counter + 6 x u16).
LEGACY_SAMPLE_PAYLOAD = 16
#: The fixed v1 frame size on the wire (5 header + 16 + 2 CRC).
LEGACY_FRAME_BYTES = 23

PROTOCOL_VERSION = 2
#: capability bits in the v2 IDENTIFY_RSP ``caps`` field
CAP_SET_BAUD = 1 << 0
CAP_SLIM_FRAME = 1 << 1
#: The device-supported baud set (CH32V006 USART ceiling is 3 Mbps,
#: USARTDIV = 1.0 exact at 48 MHz PCLK2 — wire-protocol.md §baud).
SUPPORTED_BAUDS = (2_000_000, 3_000_000)

AVERAGING_CHOICES = (0, 4, 8, 16, 32, 64, 128, 256)
SAMPLE_MODE_FREE_RUN = 0


class FrameType(IntEnum):
    SET_AVERAGING = 0x01
    SET_CHANNELS = 0x02
    SET_SAMPLE_MODE = 0x03
    START_STREAM = 0x04
    STOP_STREAM = 0x05
    SAMPLE_ONCE = 0x06
    RESET = 0x07
    IDENTIFY = 0x08
    ARM_TRIGGER = 0x09  # reserved: external trigger not implemented
    SET_BAUD = 0x0A  # v2: u32 LE baud
    SET_FRAME_FORMAT = 0x0B  # v2: u8 0 = legacy fixed, 1 = mask-sized
    ACK = 0x81
    NAK = 0x82
    IDENTIFY_RSP = 0x83
    SAMPLE = 0x90


class ErrorCode(IntEnum):
    BAD_COMMAND = 0x01
    BAD_PARAMETER = 0x02
    BUSY = 0x03
    UNSUPPORTED = 0x04


@dataclass(frozen=True)
class Frame:
    type: int
    seq: int
    payload: bytes


@dataclass(frozen=True)
class IdentifyInfo:
    proto_version: int
    fw_major: int
    fw_minor: int
    n_channels: int
    resolution: int
    caps: int | None = None

    @property
    def is_v2(self) -> bool:
        return self.proto_version >= 2 and self.caps is not None


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflect, no xorout.

    The bitwise reference; the nibble table below computes the same value
    (the codec tests pin the two together over random vectors, and the
    firmware's table is the same one).
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


#: The nibble table for CRC-16/CCITT-FALSE: ``table[n]`` is the poly
#: applied four shifting rounds to ``n << 12``. 16 x u16 = 32 B — the
#: firmware embeds the same constants (firmware main.c CRC_NIBBLE), and
#: the codec test derives the table from the bitwise reference and pins
#: every entry (regenerate-or-fail, the A4 honesty shape).
CRC_NIBBLE: tuple[int, ...] = (
    0x0000, 0x1021, 0x2042, 0x3063,
    0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B,
    0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
)


def crc16_table(data: bytes) -> int:
    """CRC-16/CCITT-FALSE through the nibble table (4 rounds per byte)."""
    crc = 0xFFFF
    for byte in data:
        crc = (crc << 4) & 0xFFFF ^ CRC_NIBBLE[((crc >> 12) ^ (byte >> 4)) & 0xF]
        crc = (crc << 4) & 0xFFFF ^ CRC_NIBBLE[((crc >> 12) ^ (byte & 0xF)) & 0xF]
    return crc


def encode_frame(frame: Frame) -> bytes:
    """Encode one frame: sync + header + payload + CRC (LE), CRC over
    type..payload."""
    if not 0 <= frame.type <= 0xFF:
        raise ValueError(f"type out of range: {frame.type}")
    if not 0 <= frame.seq <= 0xFF:
        raise ValueError(f"seq out of range: {frame.seq}")
    if len(frame.payload) > MAX_PAYLOAD:
        raise ValueError(f"payload too long: {len(frame.payload)}")
    body = bytes((SYNC[0], SYNC[1], frame.type, frame.seq, len(frame.payload))) + frame.payload
    return body + crc16_table(body[2:]).to_bytes(CRC_LEN, "little")


class FrameParser:
    """Incremental decoder that resynchronises on corrupt bytes or a bad CRC.

    A bad-CRC frame drops one byte forward; garbage before a SYNC is
    dropped wholesale; error_count tracks every forward move. Gaps in the
    SAMPLE counter stream are :mod:`adc_wire.gaps`' business, not the
    parser's.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.error_count = 0

    def feed(self, data: bytes) -> list[Frame]:
        self._buffer += data
        frames: list[Frame] = []
        while True:
            frame = self._extract()
            if frame is None:
                break
            frames.append(frame)
        return frames

    def bytes_wanted(self) -> int:
        """Bytes that complete the buffered header, or else the buffered frame."""
        buf = self._buffer
        if len(buf) < HEADER_LEN:
            return HEADER_LEN - len(buf)
        return HEADER_LEN + buf[4] + CRC_LEN - len(buf)

    def _extract(self) -> Frame | None:
        while True:
            buf = self._buffer
            start = buf.find(SYNC)
            if start < 0:
                keep = 1 if len(buf) > 1 else len(buf)
                self._buffer = buf[-keep:]
                return None
            if start > 0:
                self.error_count += 1
                del buf[:start]
                continue
            if len(buf) < HEADER_LEN:
                return None
            length = buf[4]
            total = HEADER_LEN + length + CRC_LEN
            if len(buf) < total:
                return None
            frame_bytes = bytes(buf[:total])
            got_crc = int.from_bytes(frame_bytes[-CRC_LEN:], "little")
            if crc16_table(frame_bytes[2 : HEADER_LEN + length]) != got_crc:
                self.error_count += 1
                del buf[0]
                continue
            del buf[:total]
            return Frame(
                type=frame_bytes[2],
                seq=frame_bytes[3],
                payload=frame_bytes[5 : HEADER_LEN + length],
            )


def frame_bytes(n_active: int, slim: bool) -> int:
    """The on-wire frame size for a stream of ``n_active`` channels.

    Legacy format: the fixed 23 B whatever the mask. Slim (v2 mask-sized):
    11 + 2 x n (header 5 + counter 4 + n x u16 + CRC 2); the all-six mask
    gives 11 + 12 = 23 B — byte-identical to legacy.
    """
    if slim:
        return 11 + 2 * n_active
    return LEGACY_FRAME_BYTES


def build_sample_payload(counter: int, values: tuple[int, ...] | list[int]) -> bytes:
    """One v2 mask-sized SAMPLE payload: u32 LE counter + n x u16 LE."""
    payload = counter.to_bytes(4, "little")
    for value in values:
        payload += value.to_bytes(2, "little")
    return payload


def parse_sample(payload: bytes, *, n_active: int) -> tuple[int, tuple[int, ...]]:
    """Decode one SAMPLE payload; the LEN cross-check is the caller's
    negotiated-mask popcount (a mismatch is a protocol error, resync
    downstream)."""
    if len(payload) != 4 + 2 * n_active:
        raise ValueError(
            f"sample_len_mismatch: payload {len(payload)} B, expected "
            f"{4 + 2 * n_active} B for {n_active} active channel(s)"
        )
    counter = int.from_bytes(payload[0:4], "little")
    values = tuple(
        int.from_bytes(payload[4 + 2 * i : 6 + 2 * i], "little") for i in range(n_active)
    )
    return counter, values


def build_set_baud(baud: int) -> bytes:
    """The SET_BAUD payload: u32 LE."""
    return baud.to_bytes(4, "little")


def build_set_frame_format(slim: bool) -> bytes:
    """The SET_FRAME_FORMAT payload: u8, 0 = legacy fixed, 1 = mask-sized."""
    return bytes((1 if slim else 0,))


def parse_ack(payload: bytes) -> tuple[int, int]:
    if len(payload) < 3:
        raise ValueError("short ACK payload")
    return payload[0], int.from_bytes(payload[1:3], "little")


def parse_nak(payload: bytes) -> tuple[int, int]:
    if len(payload) < 2:
        raise ValueError("short NAK payload")
    return payload[0], payload[1]


def parse_identify(payload: bytes) -> IdentifyInfo:
    """IDENTIFY_RSP by declared length: 5 B reads as proto 1 (caps None);
    7 B is proto 2 with the caps field."""
    if len(payload) < 5:
        raise ValueError("short IDENTIFY payload")
    if len(payload) >= 7:
        caps = int.from_bytes(payload[5:7], "little")
        proto = payload[0]
        if proto < 2 or caps == 0:
            # A proto-1 device never sends 7 B; a v2 device with zero
            # capability bits has nothing this module negotiates. Keep the
            # recorded value either way — the caller decides.
            pass
        return IdentifyInfo(
            proto_version=proto,
            fw_major=payload[1],
            fw_minor=payload[2],
            n_channels=payload[3],
            resolution=payload[4],
            caps=caps,
        )
    return IdentifyInfo(
        proto_version=payload[0],
        fw_major=payload[1],
        fw_minor=payload[2],
        n_channels=payload[3],
        resolution=payload[4],
    )
