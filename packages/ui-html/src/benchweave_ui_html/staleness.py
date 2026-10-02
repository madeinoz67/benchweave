"""Contract §B.4 staleness — the ST-2 predicate as a pure function. Ported
verbatim from the React reference renderer's ``staleness.ts`` (deleted at
the G1e cutover); since the cutover THIS module is the semantic reference
(the §B.4 rows are normative either way).

ST-1 (folded semantics, per the corpus): the cadence is the POLLED
parameter's ``max_age_ms`` — the descriptor's own read-acceptance window
(its disavowal boundary). For streaming observations
``stream_limits.min_interval_ms`` is a rate CAP (OTDP spec §158): silence is
healthy, so a stream-cadence source supplies NO cadence here and renders no
staleness verdict — the missed-data signal is the gap event, never
silence-inference. ST-3: no cadence ⇒ NO verdict (asserts freshness
nowhere); ``freshness_ms: None`` likewise. Garbage inputs (non-finite or
negative age, non-finite or negative cadence) also render no verdict — a
fabricated ``fresh`` is the lie class. ``max_age_ms: 0`` is VALID semantics
(fresh-acquisition-only): everything ≥ 1 ms is stale.
"""

from __future__ import annotations

import math
from typing import Literal

StalenessVerdict = Literal["stale", "fresh", "no-verdict"]


def staleness(freshness_ms: float | None, max_age_ms: float | None) -> StalenessVerdict:
    """The §B.4 ST-2 boundary predicate: stale iff ``freshness_ms > max_age_ms``
    (strictly greater; equality is not stale — the boundary IS the
    descriptor's own disavowal line)."""
    if max_age_ms is None:
        return "no-verdict"
    if not _is_finite(max_age_ms) or max_age_ms < 0:
        return "no-verdict"
    if freshness_ms is None:
        return "no-verdict"
    if not _is_finite(freshness_ms) or freshness_ms < 0:
        return "no-verdict"
    return "stale" if freshness_ms > max_age_ms else "fresh"


def _is_finite(value: float) -> bool:
    """``Number.isFinite``'s twin; nan and inf are both non-finite."""
    return math.isfinite(value)
