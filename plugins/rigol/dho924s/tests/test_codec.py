# author: Stephen Eaton
"""A2: the codec decodes the DOCUMENTED waveform shapes and refuses the rest.

Every block, preamble and reply in this module is SYNTHETIC: it was authored
from the shapes the manufacturer's programming guide documents, with invented
values. None was recorded on an instrument and none is hardware-qualified.
The guide documents no float waveform format for this series, so no float
decoder exists here to test.
"""

import pytest
from support import vectors

from benchweave_rigol_dho924s.codec import (
    AsciiWaveformError,
    BlockHeaderError,
    BlockOversizedError,
    BlockTrailingError,
    BlockTruncatedError,
    CodecError,
    FormatUnsupportedError,
    NonFiniteSampleError,
    PointsMismatchError,
    PreambleError,
    TextFormatError,
    decode_ascii,
    decode_byte_waveform,
    parse_ascii_waveform,
    parse_block,
    parse_idn,
    parse_preamble,
)

# A four-point BYTE block: the header #9 with a nine-digit length, then the points.
BLOCK = bytes.fromhex("233930303030303030303400808EFF")
PREAMBLE = "0,0,4,1,1.000000E-8,0.000000E+0,0.000000E+0,5.000000E-1,0,128"
POINTS = b"\x00\x80\x8e\xff"
REASONS = {
    "WAV_HEADER": BlockHeaderError,
    "WAV_TRUNCATED": BlockTruncatedError,
    "WAV_TRAILING": BlockTrailingError,
    "WAV_OVERSIZED": BlockOversizedError,
    "WAV_PREAMBLE": PreambleError,
    "WAV_FORMAT_UNSUPPORTED": FormatUnsupportedError,
    "WAV_POINTS": PointsMismatchError,
    "WAV_NONFINITE": NonFiniteSampleError,
    "WAV_ASCII": AsciiWaveformError,
    "SCPI_TEXT": TextFormatError,
}


def decode_block(block_hex: str, preamble_text: str) -> tuple[float, ...]:
    preamble = parse_preamble(preamble_text)
    return decode_byte_waveform(parse_block(bytes.fromhex(block_hex), max_bytes=4096), preamble)


def test_synthetic_byte_block_decodes_to_the_expected_volts() -> None:
    for vector in vectors("adapter-vectors.json")["waveform"]["byte"]:
        preamble = parse_preamble(vector["preamble"])
        points = parse_block(bytes.fromhex(vector["block_hex"]), max_bytes=4096)
        assert points == POINTS
        assert decode_byte_waveform(points, preamble) == tuple(vector["volts"])
        # The arithmetic the guide documents, done again here by hand:
        # volts = (point - yorigin - yreference) * yincrement.
        manual = tuple(
            (point - preamble.yorigin - preamble.yreference) * preamble.yincrement
            for point in points
        )
        assert manual == (-64.0, 0.0, 7.0, 63.5) == tuple(vector["volts"])


def test_preamble_fields_keep_their_documented_positions() -> None:
    preamble = parse_preamble(PREAMBLE)
    assert (preamble.format, preamble.type, preamble.points, preamble.count) == (0, 0, 4, 1)
    assert (preamble.xincrement, preamble.xorigin, preamble.xreference) == (1e-8, 0.0, 0.0)
    assert (preamble.yincrement, preamble.yorigin, preamble.yreference) == (0.5, 0.0, 128.0)


def test_synthetic_ascii_waveform_decodes_to_the_expected_volts() -> None:
    for vector in vectors("adapter-vectors.json")["waveform"]["ascii"]:
        assert parse_ascii_waveform(vector["text"]) == tuple(vector["volts"])
    assert parse_ascii_waveform(" 1.5 , -2.25\n,3E+0 ") == (1.5, -2.25, 3.0)


def test_synthetic_waveform_failures_refuse_with_a_stable_reason_prefix() -> None:
    for vector in vectors("adapter-failure-vectors.json")["waveform"]:
        expected = REASONS[vector["reason"]]
        with pytest.raises(CodecError) as info:
            if "text" in vector:
                parse_ascii_waveform(vector["text"])
            else:
                decode_block(vector["block_hex"], vector["preamble"])
        assert type(info.value) is expected, vector["id"]
        assert type(info.value).reason == vector["reason"]
        assert str(info.value).startswith(vector["reason"] + ": ")


@pytest.mark.parametrize(
    ("block", "reason"),
    [
        pytest.param(b"", "WAV_TRUNCATED", id="nothing-arrived"),
        pytest.param(b"#", "WAV_TRUNCATED", id="header-cut-short"),
        pytest.param(b"#9", "WAV_TRUNCATED", id="length-digits-missing"),
        pytest.param(b"#90000000", "WAV_TRUNCATED", id="length-digits-cut"),
        pytest.param(BLOCK[:-1], "WAV_TRUNCATED", id="one-point-missing"),
        pytest.param(b"X9000000004" + POINTS, "WAV_HEADER", id="no-identifier"),
        pytest.param(b" #9000000004" + POINTS, "WAV_HEADER", id="leading-space"),
        pytest.param(b"#0000000004" + POINTS, "WAV_HEADER", id="indefinite-length"),
        pytest.param(b"#A000000004" + POINTS, "WAV_HEADER", id="digit-count-not-a-digit"),
        pytest.param(b"#9x12345678" + POINTS, "WAV_HEADER", id="length-not-numeric"),
        pytest.param(b"#9+00000004" + POINTS, "WAV_HEADER", id="signed-length"),
        pytest.param(b"#9000000003" + POINTS, "WAV_TRAILING", id="one-point-too-many"),
        pytest.param(BLOCK + b"\n", "WAV_TRAILING", id="terminator-inside-the-block"),
    ],
)
def test_block_refusals_name_their_reason(block: bytes, reason: str) -> None:
    with pytest.raises(CodecError) as info:
        parse_block(block, max_bytes=4096)
    assert type(info.value) is REASONS[reason]
    assert str(info.value).startswith(reason + ": ")


def test_a_block_longer_than_the_bound_is_refused_before_it_is_parsed() -> None:
    with pytest.raises(BlockOversizedError) as info:
        parse_block(BLOCK, max_bytes=3)
    assert str(info.value).startswith("WAV_OVERSIZED: ")


def test_a_single_digit_length_count_is_accepted() -> None:
    # The documented header shape allows one to nine length digits.
    assert parse_block(b"#14" + POINTS, max_bytes=4096) == POINTS


def test_only_the_byte_format_is_decoded() -> None:
    with pytest.raises(FormatUnsupportedError) as info:
        decode_block(BLOCK.hex(), PREAMBLE.replace("0,0,4", "1,0,4", 1))
    assert str(info.value).startswith("WAV_FORMAT_UNSUPPORTED: ")
    assert "byte order" in str(info.value)
    with pytest.raises(FormatUnsupportedError) as info:
        decode_block(BLOCK.hex(), PREAMBLE.replace("0,0,4", "2,0,4", 1))
    assert "ASCII" in str(info.value)
    with pytest.raises(FormatUnsupportedError):
        parse_preamble(PREAMBLE.replace("0,0,4", "7,0,4", 1))


@pytest.mark.parametrize(
    ("preamble", "reason"),
    [
        pytest.param("", "WAV_PREAMBLE", id="empty"),
        pytest.param(",".join(PREAMBLE.split(",")[:-1]), "WAV_PREAMBLE", id="one-field-missing"),
        pytest.param(PREAMBLE.replace("0,0,4,1", "0,0,4,x", 1), "WAV_PREAMBLE", id="count-not-int"),
        pytest.param(PREAMBLE + ",0", "WAV_PREAMBLE", id="one-field-too-many"),
        pytest.param(PREAMBLE.replace("0,0,4", "0,0,x", 1), "WAV_PREAMBLE", id="count-not-int"),
        pytest.param(PREAMBLE.replace("0,0,4", "0,0,0", 1), "WAV_PREAMBLE", id="zero-points"),
        pytest.param(PREAMBLE.replace("0,0,4", "0,9,4", 1), "WAV_PREAMBLE", id="unknown-type"),
        pytest.param(PREAMBLE.replace("E-8", "E", 1), "WAV_PREAMBLE", id="malformed-number"),
    ],
)
def test_preamble_refusals_name_their_reason(preamble: str, reason: str) -> None:
    with pytest.raises(CodecError) as info:
        parse_preamble(preamble)
    assert type(info.value) is REASONS[reason]
    assert str(info.value).startswith(reason + ": ")


@pytest.mark.parametrize("token", ["NAN", "INF", "+INF", "-INF", "INFINITY"])
def test_a_non_finite_scaling_term_is_refused(token: str) -> None:
    with pytest.raises(NonFiniteSampleError) as info:
        parse_preamble(PREAMBLE.replace("5.000000E-1", token))
    assert str(info.value).startswith("WAV_NONFINITE: ")


def test_a_non_finite_product_is_refused() -> None:
    preamble = parse_preamble(PREAMBLE.replace("5.000000E-1", "1.000000E+308"))
    with pytest.raises(NonFiniteSampleError) as info:
        decode_byte_waveform(POINTS, preamble)
    assert str(info.value).startswith("WAV_NONFINITE: ")


def test_a_block_whose_point_count_differs_from_the_preamble_is_refused() -> None:
    with pytest.raises(PointsMismatchError) as info:
        decode_byte_waveform(POINTS, parse_preamble(PREAMBLE.replace("0,0,4", "0,0,3", 1)))
    assert str(info.value).startswith("WAV_POINTS: ")


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        pytest.param("", "WAV_ASCII", id="empty"),
        pytest.param(",", "WAV_ASCII", id="empty-sample"),
        pytest.param("1,2,", "WAV_ASCII", id="trailing-comma"),
        pytest.param("1,,2", "WAV_ASCII", id="gap"),
        pytest.param("1;2", "WAV_ASCII", id="wrong-separator"),
        pytest.param("1 2", "WAV_ASCII", id="space-separated"),
        pytest.param("NaN", "WAV_NONFINITE", id="nan"),
        pytest.param("1,-INF", "WAV_NONFINITE", id="negative-infinity"),
        pytest.param("1.0e999", "WAV_NONFINITE", id="overflow"),
    ],
)
def test_ascii_waveform_refusals_name_their_reason(text: str, reason: str) -> None:
    with pytest.raises(CodecError) as info:
        parse_ascii_waveform(text)
    assert type(info.value) is REASONS[reason]
    assert str(info.value).startswith(reason + ": ")


def test_identity_reply_is_four_non_empty_fields_with_surrounding_spaces_stripped() -> None:
    reply = parse_idn("RIGOL TECHNOLOGIES , DHO924S , SYNTHETIC-SERIAL, SYNTHETIC-FIRMWARE ")
    assert tuple(reply) == (
        "RIGOL TECHNOLOGIES",
        "DHO924S",
        "SYNTHETIC-SERIAL",
        "SYNTHETIC-FIRMWARE",
    )
    assert (reply.manufacturer, reply.model, reply.serial, reply.firmware) == tuple(reply)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param("RIGOL TECHNOLOGIES,DHO924S,SYNTHETIC-FIRMWARE", id="three-fields"),
        pytest.param("RIGOL TECHNOLOGIES,DHO924S,S,F,extra", id="five-fields"),
        pytest.param("RIGOL TECHNOLOGIES,DHO924S,,F", id="empty-serial"),
        pytest.param("RIGOL TECHNOLOGIES,DHO924S,S,", id="empty-firmware"),
        pytest.param(",DHO924S,S,F", id="empty-manufacturer"),
        pytest.param("RIGOL TECHNOLOGIES,,S,F", id="empty-model"),
        pytest.param("RIGOL TECHNOLOGIES,DHO924S,S,F\n", id="terminator-inside"),
        pytest.param("RIGOL TECHNOLOGIES,DHO924S,S,F\x00", id="nul"),
        pytest.param("RIGOL TECHNOLOGIES,DHO924S,S,F\t", id="tab"),
    ],
)
def test_a_malformed_identity_reply_is_refused(text: str) -> None:
    with pytest.raises(TextFormatError) as info:
        parse_idn(text)
    assert str(info.value).startswith("SCPI_TEXT: ")


@pytest.mark.parametrize("data", [b"\xff", b"caf\xe9", b"a\x00b", b"a\nb"])
def test_reply_bytes_must_be_printable_ascii(data: bytes) -> None:
    with pytest.raises(TextFormatError) as info:
        decode_ascii(data)
    assert str(info.value).startswith("SCPI_TEXT: ")
    assert decode_ascii(b"RIGOL TECHNOLOGIES,DHO924S,S,F") == "RIGOL TECHNOLOGIES,DHO924S,S,F"
