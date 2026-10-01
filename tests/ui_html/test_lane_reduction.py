"""The §E.4.4 lane-reduction property proofs — the port of
``ui/src/components/plots/lane-reduction.test.ts`` and
``lane-reduction.lttb.control.test.ts`` (G1c design record §1.2/§1.4, §2
group iv).

Fixtures and thresholds unchanged: the PRNG streams (seeds 0x2445220/0x2445221/
0x2445222), the run counts (240/60/1/50), the adversarial 257-sample fixture,
the permutation null and the LTTB RED control all port verbatim, pinned by the
24 mulberry32 golden vectors (design-time node-vs-Python capture, record §1.4).
The property checker recomputes survival independently of ``reduce_lane`` —
it is the conformance oracle, not the implementation's echo.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from benchweave_ui_html.decimate import LaneColumn, LaneState, reduce_lane

STATES: Final[tuple[LaneState, ...]] = ("0", "1", "x", "z")

# The 24 golden vectors: the first 8 outputs of each of the three fixture
# seeds, captured 2026-10-01 by running the TS body under node against this
# port (bit-identical, G1c design record §1.4 / §2 L6). Digit-exact equality —
# a one-bit masking slip in the port reds these.
GOLDEN: Final[dict[int, tuple[float, ...]]] = {
    0x2445220: (
        0.9652225237805396,
        0.4304069571662694,
        0.725462764268741,
        0.36950787785463035,
        0.15731652243994176,
        0.9143903909716755,
        0.0463623246178031,
        0.9720222509931773,
    ),
    0x2445221: (
        0.4868193008005619,
        0.4788632411509752,
        0.7096924297511578,
        0.15034811082296073,
        0.36186491628177464,
        0.04382433579303324,
        0.6783437498379499,
        0.6790179717354476,
    ),
    0x2445222: (
        0.7662574690766633,
        0.8407656361814588,
        0.7420316401403397,
        0.012470268877223134,
        0.559661966515705,
        0.7370667946524918,
        0.6548893116414547,
        0.491069600218907,
    ),
}


def _imul(a: int, b: int) -> int:
    """JS ``Math.imul``: the low 32 bits of the product (bit-identical to the
    signed-int32 result under every later bitwise use in the stream)."""
    return (a * b) & 0xFFFFFFFF


def mulberry32(seed: int) -> Callable[[], float]:
    """The deterministic PRNG, ported bit-exactly so the fixture streams are
    the TS suite's streams (record §1.4).

    Every intermediate is masked to uint32; the one subtle step — JS
    ``t = (t + Math.imul(...)) ^ t`` adds in float64 and truncates only at
    the XOR — becomes ``(t + imul(...)) & 0xFFFFFFFF`` BEFORE the XOR.
    """
    a = seed & 0xFFFFFFFF

    def rand() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rand


def random_states(rand: Callable[[], float], length: int) -> list[LaneState]:
    """``STATES[Math.floor(random() * 4)]`` per sample, ported verbatim."""
    return [STATES[int(rand() * 4)] for _ in range(length)]


@dataclass
class Survival:
    """The §E.4.4 property verdict, recomputed independently of the reducer."""

    survived: int
    total: int
    missing: list[int]
    unmarked_multi_edge: list[int]
    # Fold F3a: glitch is EXACTLY (interior transitions > 1) — a marked
    # single-edge column destroys the edge information the mark replaces.
    overmarked_single_edge: list[int]
    # Fold F3b: a single-edge column's from/to are the ACTUAL neighbouring
    # states — a swap time-reverses the drawn edge.
    reversed_edges: list[int]


def _interior_transitions(states: Sequence[LaneState], column: LaneColumn) -> int:
    count = 0
    for t in range(column.first, column.last - 1):
        if states[t] != states[t + 1]:
            count += 1
    return count


def _transitions(states: Sequence[LaneState]) -> int:
    count = 0
    for t in range(len(states) - 1):
        if states[t] != states[t + 1]:
            count += 1
    return count


def check_survival(states: Sequence[LaneState], out: Sequence[LaneColumn]) -> Survival:
    """Every transition must survive to the drawn output — as a column-boundary
    edge, a column's single-interior edge, or a glitch mark — and every column
    covering more than one transition carries the glitch mark."""
    missing: list[int] = []
    survived = 0
    # Column lookup by covered sample index.
    column_at: dict[int, int] = {}
    for index, column in enumerate(out):
        for sample in range(column.first, column.last):
            column_at[sample] = index
    for t in range(len(states) - 1):
        if states[t] == states[t + 1]:
            continue  # not a transition
        owner = column_at.get(t)
        if owner is None:
            missing.append(t)
            continue
        column = out[owner]
        if t + 1 == column.last:
            survived += 1  # boundary edge between columns
        elif column.glitch or column.edge is not None:
            survived += 1
        else:
            missing.append(t)
    unmarked_multi_edge = [
        index
        for index, column in enumerate(out)
        if _interior_transitions(states, column) > 1 and not column.glitch
    ]
    overmarked_single_edge = [
        index
        for index, column in enumerate(out)
        if column.glitch and _interior_transitions(states, column) <= 1
    ]
    reversed_edges: list[int] = []
    for index, column in enumerate(out):
        if _interior_transitions(states, column) == 1 and column.edge is not None:
            for sample in range(column.first, column.last - 1):
                if states[sample] != states[sample + 1]:
                    if (
                        column.edge.from_ != states[sample]
                        or column.edge.to != states[sample + 1]
                    ):
                        reversed_edges.append(index)
                    break
    return Survival(
        survived=survived,
        total=_transitions(states),
        missing=missing,
        unmarked_multi_edge=unmarked_multi_edge,
        overmarked_single_edge=overmarked_single_edge,
        reversed_edges=reversed_edges,
    )


def lttb_shaped_reduce(states: Sequence[LaneState], columns: int) -> list[LaneColumn]:
    """The RED control's LTTB-shaped sample-dropping reducer (ported from
    ``lane-reduction.lttb.control.test.ts``): keep the first and last samples
    and select interior samples at a fixed stride — returned as one-sample
    columns, exactly what a drawn LTTB output covers."""
    picked = [0]
    step = max(1, len(states) // columns)
    sample = step
    while sample < len(states) - 1 and len(picked) < columns - 1:
        picked.append(sample)
        sample += step
    picked.append(len(states) - 1)
    ordered = sorted(picked)
    kept = [s for index, s in enumerate(ordered) if index == 0 or s != ordered[index - 1]]
    return [LaneColumn(s, s + 1, states[s], 0, False) for s in kept]


def missing_transitions(states: Sequence[LaneState], out: Sequence[LaneColumn]) -> list[int]:
    """The control's own survival checker: a transition survives only if both
    endpoints are covered AND carried (a boundary, an edge, or a glitch)."""
    covered: set[int] = set()
    for column in out:
        covered.update(range(column.first, column.last))
    missing: list[int] = []
    for t in range(len(states) - 1):
        if states[t] == states[t + 1]:
            continue
        if t not in covered or t + 1 not in covered:
            missing.append(t)  # at least one endpoint was dropped entirely
            continue
        owner = next((c for c in out if c.first <= t and t + 1 <= c.last), None)
        if owner is None or (
            t + 1 != owner.last and not owner.glitch and owner.edge is None
        ):
            missing.append(t)
    return missing


def test_mulberry32_golden_vectors() -> None:
    """L6: the three fixture seeds' first 8 outputs, digit-exact (24 values)."""
    for seed, expected in GOLDEN.items():
        rand = mulberry32(seed)
        for index, value in enumerate(expected):
            assert rand() == value, f"seed {seed:#x} output {index}: {value!r}"


def test_property_arm_keeps_every_transition() -> None:
    """L1: 240 seeded runs (>= 200 checked), lengths 2..5000, widths 1..64."""
    rand = mulberry32(0x2445220)
    checked = 0
    for run in range(240):
        length = 2 + int(rand() * 4999)
        columns = 1 + int(rand() * 64)
        states = random_states(rand, length)
        survival = check_survival(states, reduce_lane(states, columns))
        assert survival.missing == [], (
            f"run {run}: len {length} cols {columns} — "
            f"transitions {survival.missing} did not survive"
        )
        assert survival.unmarked_multi_edge == [], (
            f"run {run}: multi-transition columns without the glitch mark"
        )
        assert survival.overmarked_single_edge == [], (
            f"run {run}: single-edge columns carrying the glitch mark"
        )
        assert survival.reversed_edges == [], (
            f"run {run}: single-edge columns whose from/to are reversed"
        )
        assert survival.survived == survival.total
        checked += 1
    assert checked >= 200


def test_partition_covers_every_sample_exactly_once() -> None:
    """L2: 60 seeded runs — contiguous, non-empty, covering."""
    rand = mulberry32(0x2445221)
    for _ in range(60):
        length = 2 + int(rand() * 500)
        columns = 1 + int(rand() * 64)
        states = random_states(rand, length)
        out = reduce_lane(states, columns)
        assert out[0].first == 0
        assert out[-1].last == length
        for i in range(1, len(out)):
            assert out[i].first == out[i - 1].last, "columns are contiguous"
        for column in out:
            assert column.last > column.first, "no empty columns"


def test_adversarial_alternating_fixture_all_glitch() -> None:
    """L3: the 257-sample alternating 0101… fixture at 16 columns — sub-column
    spacing puts >1 transition in EVERY column."""
    states: list[LaneState] = ["0" if i % 2 == 0 else "1" for i in range(257)]
    out = reduce_lane(states, 16)
    assert len(out) == 16
    for column in out:
        assert column.glitch, f"column [{column.first},{column.last}) covers >1 transition"
    survival = check_survival(states, out)
    assert survival.missing == []
    assert survival.survived == survival.total


def test_permutation_null() -> None:
    """L4: 50 Fisher-Yates copies of the adversarial fixture — every
    transition of EACH ordering survives (the multiset, and with it the
    transition count, changes; the invariant is the survival rate)."""
    rand = mulberry32(0x2445222)
    base: list[LaneState] = ["0" if i % 2 == 0 else "1" for i in range(257)]
    base_survival = check_survival(base, reduce_lane(base, 16))
    assert base_survival.survived == base_survival.total
    assert base_survival.total == len(base) - 1
    for run in range(50):
        permuted = base[:]
        # Fisher-Yates with the seeded PRNG: ordering changes, multiset does not.
        for i in range(len(permuted) - 1, 0, -1):
            j = int(rand() * (i + 1))
            permuted[i], permuted[j] = permuted[j], permuted[i]
        survival = check_survival(permuted, reduce_lane(permuted, 16))
        assert survival.missing == [], f"permutation {run}"
        assert survival.unmarked_multi_edge == [], f"permutation {run}"
        assert (
            survival.survived == survival.total
        ), f"permutation {run}: every transition of this ordering survives"


def test_lttb_red_control() -> None:
    """L5: §E.4.4's committed RED control — an LTTB-shaped sample-dropping
    reducer run against the SAME survival property MUST violate it. This
    control is the proof the property has teeth: a checker that an LTTB
    reducer passes cannot be enforcing transition survival."""
    states: list[LaneState] = [
        ("0" if i % 2 == 0 else "1") if i % 40 < 20 else "0" for i in range(200)
    ]
    dropped = missing_transitions(states, lttb_shaped_reduce(states, 12))
    assert len(dropped) > 0, (
        "the LTTB control must lose transitions — "
        "a pass here means the property checker has no teeth"
    )
    # The conforming reducer loses none on the same fixture.
    assert missing_transitions(states, reduce_lane(states, 12)) == []
