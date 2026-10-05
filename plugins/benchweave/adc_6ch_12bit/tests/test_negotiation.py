# author: Stephen Eaton
"""The six A2 negotiation cells over the emulator (issue #393, design §10 A2).

Each cell body is shared with the RED control: the control runs the SAME
body against a stub negotiator that skips negotiation entirely — if the
stub passes the slim-frame and fallback cells, the CELLS are falsified.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from adc_wire import codec
from adc_wire.negotiate import NegotiationResult, negotiate_stream
from emulator import AdcEmulator, EmulatorServices

BOOT_BAUD = codec.SUPPORTED_BAUDS[0]
TARGET_BAUD = codec.SUPPORTED_BAUDS[1]
Negotiator = Callable[..., Awaitable[NegotiationResult]]


class _Ctx:
    """The negotiation's minimal context (deadline, cancel, dispatch)."""

    def __init__(self, deadline_s: float = 5.0) -> None:
        self.deadline_monotonic = time.monotonic() + deadline_s
        self.dispatched = True

    def is_cancelled(self) -> bool:
        return False


async def _noop_reopen(baud: int) -> None:
    """The in-process transport carries its baud state internally."""


def _negotiate(
    emulator: AdcEmulator,
    *,
    negotiator: Negotiator | None = None,
    **kwargs: Any,
) -> NegotiationResult:
    services = EmulatorServices(emulator)
    context = _Ctx(5.0)
    call = negotiator or negotiate_stream
    return asyncio.run(call(services, context, reopen=_noop_reopen, **kwargs))


def _decode_one(emu: AdcEmulator, *, n_active: int) -> tuple[codec.Frame, int, tuple[int, ...]]:
    """Stream one frame off the emulator and decode it at the given width."""
    emu.streaming = True
    raw = emu.read(4096)
    emu.streaming = False
    frames = codec.FrameParser().feed(raw)
    assert frames, "the streaming emulator must emit a frame"
    frame = frames[0]
    counter, values = codec.parse_sample(frame.payload, n_active=n_active)
    return frame, counter, values


# ---------------------------------------------------------------------------
# cell bodies (shared with the RED control)


def _cell_v2_success(emulator: AdcEmulator, negotiator: Negotiator) -> None:
    result = _negotiate(emulator, negotiator=negotiator)
    assert result.baud == TARGET_BAUD and result.slim, result.events
    assert emulator.baud == TARGET_BAUD and emulator.slim
    emulator.channel_mask = 0b000001
    frame, counter, values = _decode_one(emulator, n_active=1)
    assert len(frame.payload) == 6, "the slim stream carries the mask-sized 13 B frame"
    assert counter >= 0 and len(values) == 1


def _cell_v1_fallback(emulator: AdcEmulator, negotiator: Negotiator) -> None:
    result = _negotiate(emulator, negotiator=negotiator)
    assert not result.negotiated and result.baud == BOOT_BAUD and not result.slim
    steps = {(e["step"], e["outcome"]) for e in result.events}
    assert ("v2_attempt", "skipped") in steps, result.events
    frame, _counter, values = _decode_one(emulator, n_active=6)
    assert len(frame.payload) == 16 and codec.frame_bytes(6, slim=False) == 23, (
        "the legacy stream carries the fixed 23 B frame"
    )


def _cell_v2_nak_baud(emulator: AdcEmulator, negotiator: Negotiator) -> None:
    result = _negotiate(emulator, negotiator=negotiator)
    assert not result.negotiated and result.baud == BOOT_BAUD
    steps = {(e["step"], e["outcome"]) for e in result.events}
    assert ("v2_attempt", "fallback") in steps, result.events
    set_bauds = [c for c in emulator.commands if c[0] == int(codec.FrameType.SET_BAUD)]
    assert len(set_bauds) == 1, "exactly one SET_BAUD reached the wire"
    assert emulator.baud == BOOT_BAUD, "the NAK must leave the device at boot state"


def _cell_silent_revert(emulator: AdcEmulator) -> None:
    result = _negotiate(emulator, switch_timeout_s=0.08)
    assert not result.negotiated
    steps = {(e["step"], e["outcome"]) for e in result.events}
    assert ("v2_attempt", "fallback") in steps, result.events
    assert emulator.baud == TARGET_BAUD, "the device applied the switch"
    time.sleep(0.4)  # > the emulator's T_revert (0.25 s)
    emulator.read(1)  # tick the emulator's time-driven revert
    assert emulator.reverts, "the device must revert on its own T_revert"
    assert emulator.baud == BOOT_BAUD and not emulator.slim
    frame, _counter, _values = _decode_one(emulator, n_active=6)
    assert len(frame.payload) == 16, "the link still streams at boot state"


def _cell_host_timeout_no_retry(emulator: AdcEmulator) -> None:
    result = _negotiate(emulator, switch_timeout_s=0.08)
    assert not result.negotiated
    steps = {(e["step"], e["outcome"]) for e in result.events}
    assert ("v2_attempt", "fallback") in steps, result.events
    set_bauds = [c for c in emulator.commands if c[0] == int(codec.FrameType.SET_BAUD)]
    format_cmds = [c for c in emulator.commands if c[0] == int(codec.FrameType.SET_FRAME_FORMAT)]
    assert len(set_bauds) == 1 and len(format_cmds) == 1, "one attempt, no retry loop"


def _cell_len_mask_mismatch(emulator: AdcEmulator) -> None:
    result = _negotiate(emulator)
    assert result.slim, result.events
    emulator.channel_mask = 0b000001
    emulator.legacy_override = True  # the buggy stream: legacy frames after slim
    emulator.streaming = True
    raw = emulator.read(4096)
    emulator.streaming = False
    frames = codec.FrameParser().feed(raw)
    assert frames
    with pytest.raises(ValueError, match="sample_len_mismatch"):
        codec.parse_sample(frames[0].payload, n_active=1)
    emulator.legacy_override = False
    frame, counter, values = _decode_one(emulator, n_active=1)
    assert counter >= 0 and len(values) == 1, "a conforming frame still decodes"


# ---------------------------------------------------------------------------
# the six cells, green


def test_a2_1_v2_success_streams_slim() -> None:
    _cell_v2_success(AdcEmulator(variant="v2"), negotiate_stream)


def test_a2_2_v1_device_falls_back_to_the_legacy_stream() -> None:
    _cell_v1_fallback(AdcEmulator(variant="v1"), negotiate_stream)


def test_a2_3_v2_device_that_naks_set_baud_falls_back() -> None:
    _cell_v2_nak_baud(AdcEmulator(variant="v2_nak_baud"), negotiate_stream)


def test_a2_4_silent_device_reverts_and_the_link_still_streams() -> None:
    _cell_silent_revert(AdcEmulator(variant="silent_revert", t_revert_s=0.25))


def test_a2_5_host_switch_timeout_one_fallback_no_retry() -> None:
    _cell_host_timeout_no_retry(AdcEmulator(variant="silent_revert", t_revert_s=60))


def test_a2_6_len_mask_mismatch_is_a_protocol_error_with_resync() -> None:
    _cell_len_mask_mismatch(AdcEmulator(variant="v2"))


# ---------------------------------------------------------------------------
# the RED control: a stub that skips negotiation must fail the cells


async def _stub_negotiate(
    services: Any, context: Any, *, reopen: Any, **kwargs: Any
) -> NegotiationResult:
    """The anti-gaming stub: a legacy result with zero wire commands."""
    return NegotiationResult(
        baud=BOOT_BAUD,
        slim=False,
        identify=codec.IdentifyInfo(1, 0, 2, codec.N_CHANNELS, 12),
        events=[{"step": "v2_attempt", "outcome": "skipped", "detail": "stub"}],
    )


def test_a2_red_control_stub_fails_the_cells() -> None:
    with pytest.raises(AssertionError):
        _cell_v2_success(AdcEmulator(variant="v2"), _stub_negotiate)
    with pytest.raises(AssertionError):
        _cell_v2_nak_baud(AdcEmulator(variant="v2_nak_baud"), _stub_negotiate)
