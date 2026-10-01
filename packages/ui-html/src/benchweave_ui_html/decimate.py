"""§E.4.4 — edge-preserving lane decimation, a normative pure function.

Reduction keeps EVERY transition: a drawn column always contains every state
change of the acquired states it covers, as an edge (a column boundary, or the
single interior pre/post pair) or a glitch mark (a column covering more than
one transition). Sample-dropping reduction (LTTB-style point selection) is
non-conforming for this kind — a dropped transition is detected by the
property tests in ``tests/ui_html/test_lane_reduction.py``, which recompute
survival independently of this implementation.

This module is the Python port of ``ui/src/components/plots/lane-reduction.ts``
(G1c design record §1.2): the uniform floor grid, the interior transition
count, glitch exactly on more than one interior transition, and single
interior transitions rendered as the pre/post edge all port verbatim. The
columns partition ``[0, len(states))``; a transition AT a column boundary is
interior to neither column and survives as the drawn step between them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

#: The four-state logic alphabet carried verbatim on the OTDP wire.
LaneState = Literal["0", "1", "x", "z"]


@dataclass(frozen=True)
class LaneEdge:
    """The pre/post pair a single-interior-transition column draws."""

    # TS ``from``; the trailing underscore because ``from`` is a Python keyword.
    from_: LaneState
    to: LaneState


@dataclass(frozen=True)
class LaneColumn:
    """One drawn column of a reduced lane (the TS ``LaneColumn`` shape)."""

    #: Inclusive first sample index the column covers.
    first: int
    #: Exclusive last sample index (the columns partition ``[0, len(states))``).
    last: int
    #: The state drawn across the column when it carries no interior transition.
    state: LaneState
    #: Transitions strictly inside the column (both endpoints covered).
    transitions: int
    #: §E.4.4: a column covering more than one interior transition renders a
    #: multi-edge/glitch mark.
    glitch: bool
    #: Exactly one interior transition: the column draws the pre/post edge.
    edge: LaneEdge | None = None


def reduce_lane(states: Sequence[LaneState], columns: int) -> list[LaneColumn]:
    """Reduce one lane's acquired states to ``columns`` drawn columns.

    Boundaries fall on the transition-faithful grid: a transition at index t
    is a column boundary whenever the bucket sizes allow, and any transition
    that lands strictly inside a column is carried by that column — as its
    ``edge`` pair when it is the only one, as the ``glitch`` mark otherwise.
    Raises ``ValueError`` for ``columns < 1`` (the TS ``lane_columns_invalid``
    refusal), ported verbatim.
    """
    if not states:
        return []
    if columns < 1:
        raise ValueError("lane_columns_invalid: at least one column required")
    # More columns than samples helps nothing: one column per sample is the
    # finest drawable grid.
    target = min(columns, len(states))
    out: list[LaneColumn] = []
    for b in range(target):
        first = (b * len(states)) // target  # the uniform floor grid
        last = ((b + 1) * len(states)) // target
        # The tail span covers the remainder so the columns stay a partition
        # of non-empty spans.
        if b == target - 1:
            last = len(states)
        # Empty span: unreachable when target <= len(states) (consecutive
        # floors differ by >= 1); ported verbatim as defensive dead code —
        # this guard catches nothing on the reachable input space.
        if last <= first:
            continue
        transitions = 0
        single = -1
        for t in range(first, last - 1):  # interior pairs only
            if states[t] != states[t + 1]:
                transitions += 1
                single = t
        column = LaneColumn(first, last, states[first], transitions, transitions > 1)
        if transitions == 1:
            column = replace(column, edge=LaneEdge(states[single], states[single + 1]))
        out.append(column)
    return out
