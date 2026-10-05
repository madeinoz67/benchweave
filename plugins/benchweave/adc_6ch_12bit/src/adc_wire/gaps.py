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


_RESTART_THRESHOLD = 1 << 31


class GapDetector:
    """Fold a counter stream into gap records (fold M9 semantics).

    The detector never fabricates: the FIRST counter seen starts the
    baseline; continuation is exactly +1 (mod 2**32). Three non-continuation
    shapes are distinguished instead of being folded into one gap number:

    - forward jump -> one gap record ``(last_seen, first_after, missed)``,
      ``missed = delta - 1`` (mod-2**32 distance), appended to ``gaps``;
    - duplicate (delta 0) -> recorded in ``duplicates``, never a negative
      ``missed``;
    - restart (the counter went BACKWARDS, e.g. a device RESET reboots it
      to 0) -> recorded in ``restarts`` as ``(last_seen, first_after)``,
      and the detector re-baselines -- never a ~2**32 fabricated gap.

    A seamless wrap near 2**32 remains continuation, not a restart.
    """

    def __init__(self) -> None:
        self._prev: int | None = None
        self.gaps: list[tuple[int, int, int]] = []
        self.duplicates: list[int] = []
        self.restarts: list[tuple[int, int]] = []

    def feed(self, counter: int) -> tuple[int, int, int] | None:
        """Feed one counter; return its gap record, or None."""
        if self._prev is None:
            self._prev = counter
            return None
        last_seen = self._prev
        delta = (counter - last_seen) % _COUNTER_MOD
        self._prev = counter
        if delta == 1:
            return None  # continuation (mod 2**32: the seamless wrap)
        if delta == 0:
            self.duplicates.append(counter)
            return None
        raw = counter - last_seen
        if raw < 0 and delta > _RESTART_THRESHOLD:
            self.restarts.append((last_seen, counter))
            return None  # rebaseline: the counter went backwards
        missed = delta - 1
        record = (last_seen, counter, missed)
        self.gaps.append(record)
        return record


def gaps_in_stream(counters: list[int]) -> list[tuple[int, int, int]]:
    """Convenience: every gap in an entire counter list."""
    detector = GapDetector()
    return [g for c in counters if (g := detector.feed(c)) is not None]
