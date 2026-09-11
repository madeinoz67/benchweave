"""Time ports for execution: monotonic deadlines and wall-clock audit stamps.

The execution engine measures elapsed time only through ``MonotonicClock``
and takes audit stamps only through ``WallClock``; both are injected, so no
engine module imports a time source. This keeps the body deadline honest
(execution contract §5: the body budget is monotonic elapsed time from
acceptance; wall time is for audit and external freshness mapping, never for
elapsed-time enforcement) and keeps tests deterministic.

``TestClock`` implements both protocols as a fully virtual clock:
``wait_ns`` advances the monotonic reading instantly — it never sleeps — and
records every wait, and the wall reading derives from the same elapsed
nanoseconds so audit stamps track monotonic progress. ``SystemClock`` is the
production implementation over ``time.monotonic_ns`` and ``time.time``.
Plugins constructed from the same clock object share the executor's time
base; there is no hidden second clock.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

_NANOSECONDS_PER_MICROSECOND = 1_000


class MonotonicClock(Protocol):
    """Elapsed-time port: deadlines, delays and expiry checks."""

    def now_ns(self) -> int: ...

    def wait_ns(self, duration_ns: int) -> None: ...


class WallClock(Protocol):
    """Audit-time port; never used to enforce elapsed deadlines."""

    def now_iso(self) -> str: ...


def _zero_cell() -> list[int]:
    return [0]


@dataclass(frozen=True)
class TestClock:
    """Virtual clock implementing both ports; waits are instant and recorded.

    ``advance`` moves the monotonic reading directly (time passing outside a
    wait); ``wait_ns`` advances by the waited duration and records it in
    ``waits``. ``now_iso`` derives the wall stamp from ``wall_start`` plus the
    same elapsed nanoseconds, so audit stamps stay consistent with monotonic
    progress.
    """

    start_ns: int = 1_000_000_000
    wall_start: str = "2026-09-11T00:00:00Z"
    _elapsed_ns: list[int] = field(default_factory=_zero_cell)
    waits: list[int] = field(default_factory=list)

    # Not a pytest test class, despite the name the brief mandates.
    __test__ = False

    def now_ns(self) -> int:
        return self.start_ns + self._elapsed_ns[0]

    def advance(self, duration_ns: int) -> None:
        """Pass virtual time without recording a wait."""
        self._elapsed_ns[0] += duration_ns

    def wait_ns(self, duration_ns: int) -> None:
        """Wait by advancing virtual time instantly; records the duration."""
        self.advance(duration_ns)
        self.waits.append(duration_ns)

    def now_iso(self) -> str:
        base = datetime.fromisoformat(self.wall_start.replace("Z", "+00:00"))
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        stamp = base + timedelta(
            microseconds=self._elapsed_ns[0] // _NANOSECONDS_PER_MICROSECOND
        )
        return stamp.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SystemClock:
    """Production clock over ``time.monotonic_ns`` and ``time.time``."""

    def now_ns(self) -> int:
        return time.monotonic_ns()

    def wait_ns(self, duration_ns: int) -> None:
        time.sleep(duration_ns / 1_000_000_000)

    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
