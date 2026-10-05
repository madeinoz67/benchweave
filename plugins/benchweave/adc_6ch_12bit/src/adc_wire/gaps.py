# author: Stephen Eaton
"""Counter-gap detection for the ADC SAMPLE stream (protocol v2).

The u32 SAMPLE counter is the drop-detection basis (design §4.1): on
decode, ``counter != prev + 1`` (mod 2**32) means the wire dropped frames
(ring overflow, emulator drop-list, device fault) — gaps are never
silently skipped. Every gap emits one record: the gap's start (the last
seen counter), the first counter seen after the hole, and the missed
count (delta - 1).
"""

from __future__ import annotations

_COUNTER_MOD = 1 << 32


def counter_delta(prev: int, cur: int) -> int:
    """Signed distance forward from ``prev`` to ``cur`` (mod 2**32)."""
    return (cur - prev) % _COUNTER_MOD


class GapDetector:
    """Fold a counter stream into gap records.

    The detector never fabricates: the FIRST counter seen starts the
    baseline (no gap for the baseline itself); a counter that does not
    continue it by exactly one emits one gap record and re-baselines.
    """

    def __init__(self) -> None:
        self._prev: int | None = None
        self.gaps: list[tuple[int, int, int]] = []

    def feed(self, counter: int) -> tuple[int, int, int] | None:
        """Feed one counter; return its gap record, or None.

        The record is ``(last_seen, first_after, missed)`` where ``missed
        = delta - 1``; wrapping at 2**32 is normal continuation.
        """
        if self._prev is None:
            self._prev = counter
            return None
        delta = counter_delta(self._prev, counter)
        missed = delta - 1
        last_seen = self._prev
        self._prev = counter
        if delta == 1:
            return None
        record = (last_seen, counter, missed)
        self.gaps.append(record)
        return record


def gaps_in_stream(counters: list[int]) -> list[tuple[int, int, int]]:
    """Convenience: every gap in an entire counter list."""
    detector = GapDetector()
    return [g for c in counters if (g := detector.feed(c)) is not None]
