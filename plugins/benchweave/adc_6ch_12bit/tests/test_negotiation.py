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


def _emulator_reopen(emulator: AdcEmulator) -> Any:
    """The in-process reopen: the host side moves to the new baud (the
    emulator tracks both ends since fold M7)."""

    async def reopen(baud: int) -> None:
        emulator.host_baud = baud

    return reopen


def _negotiate(
    emulator: AdcEmulator,
    *,
    negotiator: Negotiator | None = None,
    **kwargs: Any,
) -> NegotiationResult:
    services = EmulatorServices(emulator)
    context = _Ctx(5.0)
    call = negotiator or negotiate_stream
    return asyncio.run(call(services, context, reopen=_emulator_reopen(emulator), **kwargs))


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
    # M5 (fold): wire-level reach — the negotiator must have ASKED the
    # device. A silent stub (zero transmissions) fails here.
    identifies = [c for c in emulator.commands if c[0] == int(codec.FrameType.IDENTIFY)]
    assert identifies, "the fallback cell requires the device to receive IDENTIFY"
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
# fold-wave cells (M6/M7/M8)


def test_m6_out_of_enum_reply_type_raises_negotiation_failed() -> None:
    """M6 (fold): an out-of-enum IDENTIFY answer (0x0C) must raise
    NegotiationFailed carrying the raw byte — never a ValueError from
    FrameType(x).name inside the raiser."""

    class _OddServices:
        """Answers every send with a hand-built 0x0C frame."""

        def __init__(self) -> None:
            self.sent: list[bytes] = []

        async def transfer(self, transaction: dict[str, Any], context: Any) -> dict[str, Any]:
            if transaction["kind"] == "stream_receive":
                frame = codec.Frame(type=0x0C, seq=0, payload=b"")
                return {"data": codec.encode_frame(frame)}
            self.sent.append(transaction["data"])
            return {}

    from adc_wire.negotiate import NegotiationFailed

    services = _OddServices()
    context = _Ctx(5.0)
    with pytest.raises(NegotiationFailed, match="0x0c"):
        asyncio.run(
            negotiate_stream(services, context, reopen=_noop_reopen)  # type: ignore[arg-type]
        )


def test_m7_revert_during_reopen_is_never_a_success() -> None:
    """M7 (fold): the emulator is baud-aware — if the host's reopen
    outlasts the device's T_revert, the device reverts and the late
    SET_FRAME_FORMAT arrives as wrong-baud garbage. The host must NOT
    report a negotiated 3 Mbps success; the result is a fallback (with
    an unresolved link, since the confirm then also fails)."""

    async def _slow_reopen(baud: int) -> None:
        await asyncio.sleep(0.4)  # > the emulator's T_revert (0.25 s)
        emu.host_baud = baud

    emu = AdcEmulator(variant="v2", t_revert_s=0.25)
    services = EmulatorServices(emu)
    context = _Ctx(5.0)
    result = asyncio.run(negotiate_stream(services, context, reopen=_slow_reopen))
    assert not result.negotiated, (
        f"a revert during the reopen must never read as success: {result.events}"
    )
    assert result.baud == BOOT_BAUD
    assert emu.garbled_bytes > 0, "the late frames must arrive as wrong-baud garble"
    # The device self-reverted, so the host's fallback re-joins it at the
    # boot baud: a CLEAN legacy fallback here is the honest outcome (the
    # defect the fold named was the old emulator reporting 3 Mbps
    # SUCCESS). Unresolved is the other acceptable terminal state.
    assert result.link_state in ("ok", "unresolved"), result.events
    assert ("v2_attempt", "fallback") in {(e["step"], e["outcome"]) for e in result.events}


def test_m8_lost_format_ack_leaves_the_link_unresolved() -> None:
    """M8 (fold): the SET_FRAME_FORMAT ACK is lost after the device
    applied slim — the host falls back, the confirm fails (wrong baud),
    and the result must carry link_state='unresolved': the device sits
    at the switched baud until RESET. A plain legacy fallback is a lie."""
    emu = AdcEmulator(variant="v2", t_revert_s=60)
    emu.drop_ack_once = int(codec.FrameType.SET_FRAME_FORMAT)
    services = EmulatorServices(emu)
    context = _Ctx(5.0)

    async def _noop_reopen(baud: int) -> None:
        emu.host_baud = baud

    result = asyncio.run(negotiate_stream(services, context, reopen=_noop_reopen))
    assert not result.negotiated, result.events
    assert result.link_state == "unresolved", result.events
    assert emu.slim, "the device applied the format before the ACK was lost"
    assert emu.baud == TARGET_BAUD, "the device is stranded at the switched baud"


class _AckBaudSpy(AdcEmulator):
    """Records the device baud at the moment the SET_BAUD ACK is encoded —
    the in-process observable of 'the ACK leaves at the old rate'."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.baud_at_ack: int | None = None

    def _ack(self, command: codec.FrameType, value: int) -> bytes:
        if int(command) == int(codec.FrameType.SET_BAUD) and self.baud_at_ack is None:
            self.baud_at_ack = self.baud
        return super()._ack(command, value)


class _MutantEmulatorSwitchesFirst(_AckBaudSpy):
    """The fold-vet ordering mutant: the switch applies BEFORE the ACK is
    queued — on real hardware that is a baud change with the ACK still in
    the TX buffer, i.e. the ACK leaves at the WRONG rate exactly when the
    host must read it."""

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
        self.baud = baud  # THE MUTANT: switch first ...
        self._out += self._ack(codec.FrameType.SET_BAUD, baud & 0xFFFF)  # ... ACK after
        self._revert_deadline = (
            None if baud == codec.SUPPORTED_BAUDS[0] else time.monotonic() + self.t_revert_s
        )


def _cell_m15(emu: AdcEmulator) -> None:
    """The ordering body, shared by the green pin and the mutant control.
    ``emu`` must be an :class:`_AckBaudSpy` (the discrimination is the
    baud observed at ACK-encode time — the end state alone cannot
    distinguish the orders)."""
    request = codec.encode_frame(
        codec.Frame(
            type=int(codec.FrameType.SET_BAUD),
            seq=1,
            payload=codec.build_set_baud(TARGET_BAUD),
        )
    )
    emu.write(request)
    # the ACK is queued (it leaves at the old rate) ...
    queued = codec.FrameParser().feed(bytes(emu._out))
    assert queued and queued[0].type == int(codec.FrameType.ACK), emu.commands
    assert codec.parse_ack(queued[0].payload)[0] == int(codec.FrameType.SET_BAUD)
    # ... the switch applies after the queueing: the ACK was encoded at
    # the OLD rate (the end state alone cannot see the order).
    assert emu.baud == TARGET_BAUD, "the switch applies after the ACK is queued"
    assert emu.baud_at_ack == BOOT_BAUD, (
        "the ACK must be encoded at the old rate; the switch-first mutant "
        f"encodes it at {emu.baud_at_ack}"
    )
    # A host still at the boot baud sends the next command pre-reopen:
    # wrong-baud garble — dropped, never parsed, never answered.
    format_request = codec.encode_frame(
        codec.Frame(
            type=int(codec.FrameType.SET_FRAME_FORMAT), seq=2, payload=b"\x01"
        )
    )
    emu.write(format_request)
    assert emu.garbled_bytes == len(format_request), "pre-reopen writes are garble"
    replies_after_garble = codec.FrameParser().feed(bytes(emu._out))
    assert len(replies_after_garble) == 1, "no ACK may answer a garbled write"
    # The host reopens (host side moves), and the SAME command now lands.
    emu.host_baud = TARGET_BAUD
    emu.write(format_request)
    replies = codec.FrameParser().feed(bytes(emu._out))
    assert replies[-1].type == int(codec.FrameType.ACK)
    assert emu.slim, "the format command lands once the host has reopened"


def test_m15_ack_leaves_at_the_old_rate_before_the_switch_applies() -> None:
    """Fold-vet ordering pin: SET_BAUD queues its ACK (which leaves at
    the OLD rate) and only then applies the switch — and a host that has
    not yet reopened sends wrong-baud garble the device must drop. The
    A3 regression at the fold tip (a no-op reopen left host_baud stale
    and the post-reopen SET_FRAME_FORMAT garbled) is this cell's unit
    shape."""
    _cell_m15(_AckBaudSpy(variant="v2"))


def test_m15_control_switch_first_fails_the_ordering_pin() -> None:
    """The ordering mutant: switch BEFORE the ACK is queued — on real
    hardware a baud change with the ACK still in the TX buffer, i.e. the
    ACK leaves at the wrong rate exactly when the host must read it."""
    with pytest.raises(AssertionError, match="encoded at the old rate"):
        _cell_m15(_MutantEmulatorSwitchesFirst(variant="v2"))


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
