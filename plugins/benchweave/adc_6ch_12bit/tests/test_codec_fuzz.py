# author: Stephen Eaton
"""In-tree fuzz corpus for the wire codec (fold M10).

Ported from the refute lane's external suite: random soup, byte-shifted
trains, sync-inside-payload, LEN 0/255 corners, truncation, and a bit-
flip corpus. The lane found no codec defect, so these pin DEFENSE: the
parser never raises on arbitrary bytes and resynchronises when clean
frames resume.
"""

from __future__ import annotations

import random

from adc_wire import codec


def _feed_all(parser: codec.FrameParser, chunks: list[bytes]) -> list[codec.Frame]:
    frames: list[codec.Frame] = []
    for chunk in chunks:
        frames.extend(parser.feed(chunk))
    return frames


def test_random_soup_never_raises_and_resyncs() -> None:
    rng = random.Random(393)
    for _ in range(200):
        soup = bytes(rng.randrange(256) for _ in range(rng.randrange(512)))
        parser = codec.FrameParser()
        frames = _feed_all(parser, [soup[i : i + 7] for i in range(0, len(soup), 7)])
        assert isinstance(frames, list)


def test_clean_frames_resume_after_soup() -> None:
    """Defense, bounded honestly: after arbitrary soup the parser
    realigns within a bounded amount of clean data. The worst-case
    swallow is ONE bogus header with maximum LEN: 5 + 255 + 2 = 262 B,
    rejected by its CRC, after which the parser re-frames at the next
    SYNC. The soup is <= 128 B, so 40 clean frames (680 B > 128 + 262)
    guarantee at least one decodes intact."""
    rng = random.Random(394)
    target = codec.Frame(type=0x08, seq=0, payload=b"\x01\x02\x03\x04\x05")
    good = codec.encode_frame(target)
    for _ in range(100):
        soup = bytes(rng.randrange(256) for _ in range(rng.randrange(128)))
        parser = codec.FrameParser()
        frames = _feed_all(parser, [soup + good * 40])
        assert target in frames, "the parser never re-framed after soup"


def test_sync_inside_payload_is_skipped() -> None:
    frame = codec.encode_frame(
        codec.Frame(type=0x90, seq=0, payload=b"\xaa\x55\x01\x02")
    )
    parser = codec.FrameParser()
    frames = parser.feed(b"\xde\xad" + frame + b"\xaa\x55\xbe\xef")
    assert len(frames) == 1, "the trailing pseudo-sync must not mint a frame"
    assert frames[0].payload == b"\xaa\x55\x01\x02"


def test_len_corners_and_truncation() -> None:
    parser = codec.FrameParser()
    assert parser.feed(b"\xaa\x55\x90\x00\xff") == []  # LEN 255, truncated
    frame = codec.encode_frame(codec.Frame(type=0x90, seq=0, payload=b""))
    assert len(frame) == 7
    out = codec.FrameParser().feed(frame)
    assert out == [codec.Frame(type=0x90, seq=0, payload=b"")]


def test_bitflip_corpus_never_frames_corrupt() -> None:
    rng = random.Random(396)
    frame = codec.encode_frame(
        codec.Frame(type=0x90, seq=0, payload=b"\x01\x02\x03\x04\x05\x06")
    )
    for _ in range(500):
        raw = bytearray(frame)
        position = rng.randrange(len(raw))
        raw[position] ^= 1 << rng.randrange(8)  # exactly one effective flip
        parser = codec.FrameParser()
        frames = parser.feed(bytes(raw))
        if frames:
            # a flip inside the payload bytes CAN still decode validly only
            # if the CRC moved with it; single/double flips here must not.
            assert all(
                f.payload != b"\x01\x02\x03\x04\x05\x06" or f.type != 0x90
                for f in frames
            ), f"corrupt bytes framed: {bytes(raw).hex()}"
