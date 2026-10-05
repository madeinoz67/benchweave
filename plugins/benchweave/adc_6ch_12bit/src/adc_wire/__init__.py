# author: Stephen Eaton
"""The ADC wire-family v2 reference host-side package.

``codec`` is the dual-format frame codec, ``negotiate`` the host-side
baud/frame-format negotiation state machine, ``gaps`` the counter-gap
detector. Everything here is pure Python over the OTDP section 8.1
transaction surface (:class:`negotiate.TransportServices`) — no port, no
SDK import, no device dependency — so the contributor's adapter can adopt
the modules verbatim over any conformant host services, and the emulator
tests drive the same code with no hardware at all.
"""

from adc_wire.codec import (
    CHANNEL_MASK_ALL,
    N_CHANNELS,
    Frame,
    FrameParser,
    FrameType,
    IdentifyInfo,
    encode_frame,
    parse_identify,
)
from adc_wire.gaps import GapDetector, counter_delta, gaps_in_stream

__all__ = [
    "CHANNEL_MASK_ALL",
    "Frame",
    "FrameParser",
    "FrameType",
    "GapDetector",
    "IdentifyInfo",
    "N_CHANNELS",
    "counter_delta",
    "encode_frame",
    "gaps_in_stream",
    "parse_identify",
]
