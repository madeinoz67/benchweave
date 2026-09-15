"""Bounded DPS-150 codec; source-verified, not hardware-qualified.

Framing/checksum algorithms ported from cho45/fnirsi-dps-150 (MIT).
See LICENSE and docs/protocol-evidence.md for provenance and deliberate restrictions.
"""

import math
import struct
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final

GET = 0xA1
SET = 0xB1
# The length byte bounds payloads to 255, so the largest possible wire frame
# is 4 header bytes (F0 A1 field length) + 255 payload bytes + 1 checksum.
MAX_FRAME_BYTES: Final[int] = 260
READ_FIELDS = frozenset({192, 195, 196, 217, 218, 219, 220, 221, 222, 223, 224, 226, 227, 255})
# Conservative software envelope, not a commissioned DUT envelope. Protection
# thresholds have no verified resolution, so only their finite bounds are applied.
WRITE_LIMITS = MappingProxyType(
    {
        193: (30.0, "0.01"),
        194: (5.0, "0.001"),
        209: (30.0, None),
        210: (5.1, None),
    }
)
WRITE_FIELDS = frozenset({*WRITE_LIMITS, 219})


class ProtocolError(ValueError):
    """Malformed, unexpected or unrepresentable response; never a device verdict."""


class UnsupportedCommand(ValueError):
    """Operation is outside the explicitly implemented protocol subset."""


@dataclass(frozen=True)
class Packet:
    command: int
    field: int
    payload: bytes


@dataclass(frozen=True)
class Snapshot:
    """Known subset of the 139-byte ALL response, with opaque bytes preserved."""

    input_voltage: float
    set_voltage: float
    set_current: float
    voltage: float
    current: float
    power: float
    temperature_c: float
    ovp: float
    ocp: float
    opp: float
    otp_c: float
    lvp: float
    enabled: bool
    protection: str
    mode: str
    raw_payload: bytes


type Value = float | bool | str | tuple[float, float, float] | Snapshot


def _byte(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 255:
        raise ValueError("Expected an integer byte (booleans are not bytes)")
    return value


def _check_field(command: int, field: int) -> None:
    supported = READ_FIELDS if command == GET else WRITE_FIELDS if command == SET else frozenset()
    if field not in supported:
        raise UnsupportedCommand(f"Unsupported command/field: {command:#x}/{field:#x}")


def write_payload(field: int, value: object) -> bytes:
    """Validate before encoding; never clamp or silently quantise a setpoint."""
    _check_field(SET, _byte(field))
    if field == 219:
        if type(value) is not bool:
            raise ValueError("Output enable requires a bool")
        return bytes([int(value)])
    maximum, step = WRITE_LIMITS[field]
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        raise ValueError("Expected a finite number")
    if not 0 <= value <= maximum or not math.isfinite(value):
        raise ValueError(f"Value outside [0, {maximum}]")
    if step is not None and Decimal(str(value)) % Decimal(step):
        raise ValueError(f"Value must be a multiple of {step}")
    return struct.pack("<f", value)


def encode_packet(command: int, field: int, payload: bytes = b"") -> bytes:
    """Encode an allowed GET/SET only; checksum excludes header and command."""
    command, field = _byte(command), _byte(field)
    _check_field(command, field)
    if type(payload) is not bytes or len(payload) > 255:
        raise ValueError("Payload must be bytes of length <=255")
    if command == GET:
        if payload not in (b"", b"\0"):
            raise ValueError("GET payload must be empty or one zero byte")
    elif field == 219:
        if payload not in (b"\0", b"\1"):
            raise ValueError("Output payload must be one boolean byte")
    else:
        number = _floats(payload, 1)[0]
        if not 0 <= number <= WRITE_LIMITS[field][0] + 1e-6:
            raise ValueError("SET payload is outside supported limits")
    body = bytes([field, len(payload)]) + payload
    return bytes([0xF1, command]) + body + bytes([sum(body) % 256])


def decode_packet(wire: bytes) -> Packet:
    """Decode exactly one GET response, rejecting surplus bytes and bad checksums."""
    if type(wire) is not bytes or len(wire) < 5:
        raise ProtocolError("Packet too short or not bytes")
    if wire[0] != 0xF0 or wire[1] != GET:
        raise ProtocolError("Unexpected response header/command")
    if len(wire) != wire[3] + 5:
        raise ProtocolError("Packet length mismatch")
    if sum(wire[2:-1]) % 256 != wire[-1]:
        raise ProtocolError("Checksum mismatch")
    if wire[2] not in READ_FIELDS:
        raise ProtocolError("Unsupported response field")
    return Packet(wire[1], wire[2], wire[4:-1])


class FrameDecoder:
    """Strict incremental decoder; no noise skipping or unbounded accumulation.

    Each feed is <=260 bytes (largest possible wire frame). Complete frames
    are returned together; at most one incomplete frame remains buffered.
    """

    def __init__(self, *, max_payload: int = 255) -> None:
        self._max_payload = _byte(max_payload)
        self._buffer = bytearray()

    @property
    def pending(self) -> bool:
        return bool(self._buffer)

    def feed(self, chunk: bytes) -> list[Packet]:
        try:
            return self._feed(chunk)
        except ProtocolError:
            self._buffer.clear()
            raise

    def _feed(self, chunk: bytes) -> list[Packet]:
        if type(chunk) is not bytes or len(chunk) > MAX_FRAME_BYTES:
            raise ProtocolError("Chunk exceeds bounded receive size or is not bytes")
        self._buffer.extend(chunk)
        packets: list[Packet] = []
        while self._buffer:
            if self._buffer[0] != 0xF0:
                raise ProtocolError("Noise or unexpected header")
            if len(self._buffer) >= 2 and self._buffer[1] != GET:
                raise ProtocolError("Unexpected command")
            if len(self._buffer) < 4:
                break
            if self._buffer[3] > self._max_payload:
                raise ProtocolError("Payload exceeds configured limit")
            size = self._buffer[3] + 5
            if len(self._buffer) < size:
                break
            packets.append(decode_packet(bytes(self._buffer[:size])))
            del self._buffer[:size]
        return packets


def _floats(data: bytes, count: int) -> tuple[float, ...]:
    if len(data) != count * 4:
        raise ProtocolError("Float payload length mismatch")
    values: tuple[float, ...] = struct.unpack(f"<{count}f", data)
    if not all(math.isfinite(value) for value in values):
        raise ProtocolError("Non-finite float response")
    return values


def _choice(data: bytes, choices: tuple[str, ...]) -> str:
    if len(data) != 1 or data[0] >= len(choices):
        raise ProtocolError("Invalid enum response")
    return choices[data[0]]


def decode_value(packet: Packet) -> Value:
    """Interpret known fields; no defaults on missing/malformed data."""
    field, data = packet.field, packet.payload
    if packet.command != GET or field not in READ_FIELDS:
        raise ProtocolError("Unsupported response")
    if field in {192, 196, 217, 218, 226, 227}:
        return _floats(data, 1)[0]
    if field == 195:
        voltage, current, power = _floats(data, 3)
        return voltage, current, power
    if field == 219:
        return _choice(data, ("off", "on")) == "on"
    if field == 220:
        return _choice(data, ("normal", "OVP", "OCP", "OPP", "OTP", "LVP", "REP"))
    if field == 221:
        return _choice(data, ("CC", "CV"))
    if field in {222, 223, 224}:
        try:
            text = data.rstrip(b"\0").decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Invalid identity encoding") from exc
        if not text or any(ord(char) < 32 or ord(char) == 127 for char in text):
            raise ProtocolError("Empty identity or embedded control character")
        return text
    if len(data) != 139:
        raise ProtocolError("Only the source-documented 139-byte ALL layout is supported")
    head = _floats(data[:28], 7)
    protections = _floats(data[76:96], 5)
    enabled = _choice(data[107:108], ("off", "on")) == "on"
    protection = _choice(data[108:109], ("normal", "OVP", "OCP", "OPP", "OTP", "LVP", "REP"))
    mode = _choice(data[109:110], ("CC", "CV"))
    return Snapshot(
        head[0],
        head[1],
        head[2],
        head[3],
        head[4],
        head[5],
        head[6],
        protections[0],
        protections[1],
        protections[2],
        protections[3],
        protections[4],
        enabled,
        protection,
        mode,
        data,
    )
