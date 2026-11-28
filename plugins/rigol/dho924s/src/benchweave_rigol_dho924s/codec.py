# author: Stephen Eaton
"""Waveform and text codec for the Rigol DHO800/900 command language.

DOCUMENTARY, NOT HARDWARE-QUALIFIED. Every shape decoded here is taken from
the manufacturer's programming guide, read as a description of command
shapes. No vector in this project was recorded on an instrument, and nothing
here says what any unit does. See docs/device-evidence.md.

What the guide documents, and what this module implements:

- the identity reply: four comma-separated fields
- a waveform block: ``#``, a digit count, that many length digits, the data
- a waveform preamble: ten comma-separated parameters
- the BYTE waveform format: one byte per point, converted to volts with the
  vertical increment, origin and reference

What the guide does not document, and what this module refuses:

- a float waveform format. The guide defines BYTE, WORD and ASCII only, so no
  float decoder exists here
- the byte order of the WORD format. WORD data is refused
- any message terminator. Framing belongs to the transport

Every refusal raises a ``CodecError`` whose message starts with the stable
reason of its class, for example ``WAV_TRUNCATED:``.
"""

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Final, NamedTuple

#: The documented waveform format codes of the preamble.
FORMAT_BYTE: Final = 0
FORMAT_WORD: Final = 1
FORMAT_ASCII: Final = 2
_FORMATS: Final = (FORMAT_BYTE, FORMAT_WORD, FORMAT_ASCII)
_TYPES: Final = (0, 1, 2)
#: The preamble carries this many comma-separated parameters.
PREAMBLE_FIELDS: Final = 10
#: A block header names its length with 1 to 9 digits.
MAX_LENGTH_DIGITS: Final = 9

_DIGIT: Final = re.compile(r"\d+")
_NUMBER: Final = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?")
_NONFINITE: Final = re.compile(r"[+-]?(?:NAN|INF|INFINITY)", re.IGNORECASE)
_HEADER_DIGITS: Final = frozenset(b"0123456789")
_IDENTIFIER: Final = 0x23  # '#'
_ASCII_ZERO: Final = 0x30


class CodecError(ValueError):
    """A refused waveform or text. Never a verdict about the device."""

    reason: ClassVar[str]

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.reason}: {detail}")


class BlockHeaderError(CodecError):
    reason = "WAV_HEADER"


class BlockTruncatedError(CodecError):
    reason = "WAV_TRUNCATED"


class BlockTrailingError(CodecError):
    reason = "WAV_TRAILING"


class BlockOversizedError(CodecError):
    reason = "WAV_OVERSIZED"


class PreambleError(CodecError):
    reason = "WAV_PREAMBLE"


class FormatUnsupportedError(CodecError):
    reason = "WAV_FORMAT_UNSUPPORTED"


class PointsMismatchError(CodecError):
    reason = "WAV_POINTS"


class NonFiniteSampleError(CodecError):
    reason = "WAV_NONFINITE"


class AsciiWaveformError(CodecError):
    reason = "WAV_ASCII"


class TextFormatError(CodecError):
    reason = "SCPI_TEXT"


class FrameError(CodecError):
    """A reply that the transport did not frame as the declared framing says."""

    reason = "SCPI_FRAME"


class Idn(NamedTuple):
    """The four fields of an identity reply: manufacturer, model, serial, firmware."""

    manufacturer: str
    model: str
    serial: str
    firmware: str


def check_bound(max_bytes: object) -> int:
    """A byte bound is a positive integer. Booleans are not integers here."""
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    return max_bytes


def parse_block(data: bytes, *, max_bytes: int) -> bytes:
    """Return the data of one waveform block, header excluded.

    The header is ``#``, one digit that counts the length digits, then that
    many decimal digits giving the data length in bytes. The data must be
    exactly that long: fewer bytes is a truncated block and more is trailing
    data. A block that declares more than ``max_bytes`` is refused before its
    data is looked at. The transport's own terminator is not part of the
    block; it was removed before this function is called.
    """
    bound = check_bound(max_bytes)
    if type(data) is not bytes:
        raise BlockHeaderError("waveform data must be bytes")
    if not data:
        raise BlockTruncatedError("no bytes arrived")
    if data[0] != _IDENTIFIER:
        raise BlockHeaderError("a waveform block starts with '#'")
    if len(data) < 2:
        raise BlockTruncatedError("the digit count after '#' did not arrive")
    digits = data[1] - _ASCII_ZERO
    if not 1 <= digits <= MAX_LENGTH_DIGITS:
        raise BlockHeaderError(f"the digit count after '#' must be 1 to 9, got {data[1]!r}")
    header_end = 2 + digits
    if len(data) < header_end:
        raise BlockTruncatedError("the length field did not arrive in full")
    length_field = data[2:header_end]
    if any(digit not in _HEADER_DIGITS for digit in length_field):
        raise BlockHeaderError(f"the length field {length_field!r} is not decimal digits")
    length = int(length_field)
    if length > bound:
        raise BlockOversizedError(f"the block declares {length} bytes; the bound is {bound}")
    payload = data[header_end:]
    if len(payload) < length:
        raise BlockTruncatedError(f"the header declares {length} bytes; {len(payload)} arrived")
    if len(payload) > length:
        extra = len(payload) - length
        raise BlockTrailingError(f"{extra} bytes follow the declared {length}")
    return payload


@dataclass(frozen=True)
class Preamble:
    """The ten parameters of a waveform preamble, in their documented order."""

    format: int
    type: int
    points: int
    count: int
    xincrement: float
    xorigin: float
    xreference: float
    yincrement: float
    yorigin: float
    yreference: float


def _number(token: str, refuse: Callable[[str], CodecError]) -> float:
    """One finite decimal or scientific number; anything else is refused."""
    text = token.strip()
    if not text:
        raise refuse("an empty parameter")
    if _NONFINITE.fullmatch(text):
        raise NonFiniteSampleError(f"parameter {text!r} is not a finite number")
    if _NUMBER.fullmatch(text) is None:
        raise refuse(f"parameter {text!r} is not a number")
    value = float(text)
    if not math.isfinite(value):
        raise NonFiniteSampleError(f"parameter {text!r} is not a finite number")
    return value


def _format_refusal(fmt: int) -> FormatUnsupportedError:
    if fmt == FORMAT_WORD:
        return FormatUnsupportedError(
            "WORD waveform data is documented without its byte order for this "
            "series; the byte order needs evidence from the unit"
        )
    if fmt == FORMAT_ASCII:
        return FormatUnsupportedError("ASCII waveform data carries no point block")
    return FormatUnsupportedError(f"waveform format code {fmt} is not documented")


def parse_preamble(text: str) -> Preamble:
    """Parse the ten comma-separated parameters of a waveform preamble."""
    if type(text) is not str:
        raise PreambleError("the preamble must be text")
    fields = text.split(",")
    if len(fields) != PREAMBLE_FIELDS:
        raise PreambleError(f"expected {PREAMBLE_FIELDS} parameters; received {len(fields)}")
    codes: list[int] = []
    for field in fields[:4]:
        if _DIGIT.fullmatch(field) is None:
            raise PreambleError(f"parameter {field!r} is not a non-negative integer")
        codes.append(int(field))
    fmt, kind, points, count = codes
    if fmt not in _FORMATS:
        raise _format_refusal(fmt)
    if kind not in _TYPES:
        raise PreambleError(f"acquisition type code {kind} is not documented")
    if points < 1:
        raise PreambleError(f"the preamble declares {points} points; at least one is needed")
    if count < 1:
        raise PreambleError(f"the preamble declares an average count of {count}")
    values = [_number(field, PreambleError) for field in fields[4:]]
    return Preamble(fmt, kind, points, count, *values)


def decode_byte_waveform(points: bytes, preamble: Preamble) -> tuple[float, ...]:
    """Convert the points of a BYTE waveform block to volts.

    The conversion the guide documents: the point minus the vertical origin
    and the vertical reference, times the vertical increment. The block must
    carry exactly the number of points the preamble declares.
    """
    if preamble.format != FORMAT_BYTE:
        raise _format_refusal(preamble.format)
    if type(points) is not bytes:
        raise PointsMismatchError("waveform points must be bytes")
    if len(points) != preamble.points:
        raise PointsMismatchError(
            f"the block carries {len(points)} points; the preamble declares {preamble.points}"
        )
    volts = tuple(
        (point - preamble.yorigin - preamble.yreference) * preamble.yincrement for point in points
    )
    if not all(math.isfinite(value) for value in volts):
        raise NonFiniteSampleError("a converted sample is not a finite number")
    return volts


def parse_ascii_waveform(text: str) -> tuple[float, ...]:
    """Parse an ASCII waveform: voltage values separated by commas."""
    if type(text) is not str:
        raise AsciiWaveformError("waveform text must be text")
    tokens = text.split(",")
    samples: list[float] = []
    for token in tokens:
        if not token.strip():
            raise AsciiWaveformError("every sample must be a number; an empty sample arrived")
        samples.append(_number(token, AsciiWaveformError))
    return tuple(samples)


def _check_text(text: str) -> None:
    if any(not 0x20 <= ord(character) <= 0x7E for character in text):
        raise TextFormatError("the reply contains a control or non-ASCII character")


def decode_ascii(data: bytes) -> str:
    """Decode a reply as printable ASCII. Any other byte is refused."""
    if type(data) is not bytes:
        raise TextFormatError("a reply must be bytes")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        raise TextFormatError("the reply is not ASCII") from None
    _check_text(text)
    return text


def parse_idn(text: str) -> Idn:
    """Parse an identity reply: four comma-separated fields, spaces stripped.

    Every field must be non-empty. Whether this unit can answer with an empty
    serial field is not evidenced, so an empty field is refused.
    """
    if type(text) is not str:
        raise TextFormatError("an identity reply must be text")
    _check_text(text)
    fields = tuple(field.strip(" ") for field in text.split(","))
    if len(fields) != 4:
        raise TextFormatError(f"expected 4 comma-separated fields; received {len(fields)}")
    if any(not field for field in fields):
        raise TextFormatError("every field of an identity reply must be non-empty")
    return Idn(*fields)
