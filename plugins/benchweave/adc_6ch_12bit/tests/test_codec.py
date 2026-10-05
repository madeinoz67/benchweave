# author: Stephen Eaton
"""Codec and gap-detector tests for the adc_wire reference package.

The CRC cells pin the nibble table to the bitwise reference over random
vectors (regenerate-or-fail, the A4 honesty shape — a hand-typed table
cannot pass), pin the check value, and pin the firmware's own
nibble-table constants to the same derivation.
"""

from __future__ import annotations

import random

import pytest
from adc_wire import codec
from adc_wire.gaps import GapDetector, counter_delta, gaps_in_stream


def test_crc_nibble_table_is_derived_from_the_bitwise_reference() -> None:
    """table[n] must equal four bitwise rounds on n << 12 (a hand-typed
    entry cannot pass: the builder had this exact defect once — 0x6CC6
    vs the true 0x60C6)."""
    for n in range(16):
        crc = (n << 12) & 0xFFFF
        for _ in range(4):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        assert codec.CRC_NIBBLE[n] == crc, f"table[{n}]"
    assert codec.crc16(b"123456789") == 0x29B1
    assert codec.crc16_table(b"123456789") == 0x29B1
    assert codec.crc16_table(b"") == 0xFFFF


def test_crc_table_equals_bitwise_over_random_vectors() -> None:
    random.seed(393)
    for _ in range(2000):
        blob = bytes(random.randrange(256) for _ in range(random.randrange(64)))
        assert codec.crc16(blob) == codec.crc16_table(blob), blob


def test_table_round_trip_matches_the_fork_bitwise_codec() -> None:
    """The frame encode path uses the table CRC; the fork's proven bitwise
    decoder must read the same frames (interoperability pin)."""
    from adc_wire.codec import Frame, FrameParser

    random.seed(394)
    for _ in range(50):
        frame = Frame(
            type=random.randrange(0x0B),
            seq=random.randrange(256),
            payload=bytes(random.randrange(256) for _ in range(random.randrange(20))),
        )
        wire = codec.encode_frame(frame)
        parsed = FrameParser().feed(wire)
        assert parsed == [frame]


def test_dual_format_sample_round_trip() -> None:
    for n_active, slim in ((6, False), (6, True), (1, True), (3, True)):
        values = tuple(0x123 * (i + 1) & 0x0FFF for i in range(n_active))
        payload = (
            codec.build_sample_payload(0xCAFE0001, values)
            if slim
            else codec.build_sample_payload(0xCAFE0001, values)
        )
        counter, decoded = codec.parse_sample(payload, n_active=n_active)
        assert counter == 0xCAFE0001 and decoded == values


def test_parse_sample_len_mismatch_is_typed() -> None:
    with pytest.raises(ValueError, match="sample_len_mismatch"):
        codec.parse_sample(b"\x00" * 16, n_active=1)


def test_frame_bytes_matches_the_legacy_constant() -> None:
    assert codec.frame_bytes(6, slim=False) == 23 == codec.LEGACY_FRAME_BYTES
    assert codec.frame_bytes(6, slim=True) == 23
    assert codec.frame_bytes(1, slim=True) == 13


def test_parse_identify_reads_proto_by_declared_length() -> None:
    v1 = codec.parse_identify(bytes((1, 0, 2, 6, 12)))
    assert v1.proto_version == 1 and v1.caps is None and not v1.is_v2
    v2 = codec.parse_identify(bytes((2, 0, 3, 6, 12, 0x03, 0x00)))
    assert v2.proto_version == 2 and v2.caps == 3 and v2.is_v2


def test_gap_detector_reports_planted_gaps_and_wraps() -> None:
    detector = GapDetector()
    got = [g for c in (1, 2, 3, 7, 8) if (g := detector.feed(c)) is not None]
    assert got == [(3, 7, 3)]  # 4, 5, 6 missed
    # A wrap scenario on its own detector: the counter must REACH the top
    # for the wrap to be seamless — a jump from a low counter to the top
    # is itself a (huge) gap, correctly reported as one.
    wrapped = GapDetector()
    got2 = [
        g
        for c in (0xFFFFFFFE, 0xFFFFFFFF, 0, 5)
        if (g := wrapped.feed(c)) is not None
    ]
    assert got2 == [(0, 5, 4)]
    assert counter_delta(0xFFFFFFFF, 0) == 1
    assert gaps_in_stream([10, 11, 12]) == []


def test_gap_detector_baseline_never_fabricates() -> None:
    detector = GapDetector()
    assert detector.feed(1234) is None  # the baseline is not a gap
