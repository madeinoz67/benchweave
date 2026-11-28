# author: Stephen Eaton
"""Rigol DHO-924S integration: identify over SCPI, with an injectable transport.

DOCUMENTARY, NOT HARDWARE-QUALIFIED. This package was built from the
manufacturer's programming guide and tested against synthetic exchanges
only. No instrument was connected. It makes no claim about what any unit
does; docs/device-evidence.md lists each unknown fact and the evidence that
would settle it.

The package imports no BenchWeave core implementation module and has no
runtime dependencies. It provides no hardware backend: the transport is
injected by the host.
"""

from .adapter import (
    ACTION_ABORT,
    ACTION_ARM,
    ACTION_CONFIGURE,
    ACTION_FETCH,
    ACTION_TRIGGER,
    OSCILLOSCOPE_ACTIONS,
    AcquisitionBackend,
    AcquisitionMachine,
    AcquisitionState,
    create_plugin,
)
from .client import (
    COMMANDS,
    IEEE488_2_NL,
    Framing,
    OperationBusy,
    OperationTimeout,
    ScpiClient,
    SessionUnusable,
    Transport,
    UnsupportedCommand,
)
from .codec import (
    AsciiWaveformError,
    BlockHeaderError,
    BlockOversizedError,
    BlockTrailingError,
    BlockTruncatedError,
    CodecError,
    FormatUnsupportedError,
    FrameError,
    Idn,
    NonFiniteSampleError,
    PointsMismatchError,
    Preamble,
    PreambleError,
    TextFormatError,
    decode_ascii,
    decode_byte_waveform,
    parse_ascii_waveform,
    parse_block,
    parse_idn,
    parse_preamble,
)
from .descriptor import build_descriptor
from .session import Identity, IdentityMismatch, identify

__all__ = [
    "ACTION_ABORT",
    "ACTION_ARM",
    "ACTION_CONFIGURE",
    "ACTION_FETCH",
    "ACTION_TRIGGER",
    "AsciiWaveformError",
    "AcquisitionBackend",
    "AcquisitionMachine",
    "AcquisitionState",
    "BlockHeaderError",
    "BlockOversizedError",
    "BlockTrailingError",
    "BlockTruncatedError",
    "COMMANDS",
    "CodecError",
    "FormatUnsupportedError",
    "FrameError",
    "Framing",
    "Idn",
    "Identity",
    "IdentityMismatch",
    "IEEE488_2_NL",
    "NonFiniteSampleError",
    "OperationBusy",
    "OperationTimeout",
    "OSCILLOSCOPE_ACTIONS",
    "Preamble",
    "PreambleError",
    "PointsMismatchError",
    "ScpiClient",
    "SessionUnusable",
    "TextFormatError",
    "Transport",
    "UnsupportedCommand",
    "build_descriptor",
    "create_plugin",
    "decode_ascii",
    "decode_byte_waveform",
    "identify",
    "parse_ascii_waveform",
    "parse_block",
    "parse_idn",
    "parse_preamble",
]
