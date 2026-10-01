"""§E.4 — the digital-lanes composition over G1c's ``decimate.reduce_lane``.

Identity is lane POSITION; colour carries nothing. The composed model emits
the §E.4 vocabulary as data attributes: lane rows (``data-bw-lane``,
``data-bw-lane-kind``), state segments (``data-bw-state`` plus
``data-bw-state-kind`` — high/low/hatch/midline, the monochrome-
discriminable geometries; the pixel realization is G1d's lane), glitch
marks, the bus value model, decoder spans and the time-axis furniture.
Sample-dropping reduction is non-conforming for this kind by construction:
the composition is column-wise over ``reduce_lane``'s partition, never
point selection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from benchweave_ui_html.decimate import LaneState, reduce_lane

LaneKind = Literal["channel", "group", "decoder"]
StateKind = Literal["high", "low", "hatch", "midline"]
Radix = Literal["hex", "decimal"]

_STATE_KIND: dict[str, StateKind] = {
    "1": "high",
    "0": "low",
    "x": "hatch",
    "z": "midline",
}


@dataclass(frozen=True)
class DecoderEvent:
    """One decoded event on its ``[start_s, end_s)`` extent; the payload is
    the wire's hex encoding, rendered verbatim (never re-encoded)."""

    start_s: float
    end_s: float
    payload: str


@dataclass(frozen=True)
class LaneSpec:
    """One declared lane. ``index`` is the declared lane identity
    (``data-bw-lane``); ``members`` is declaration order with the FIRST
    declared member the LSB (bus values are a pure function of member
    states and member order)."""

    index: int
    kind: LaneKind
    label: str
    states: tuple[LaneState, ...] = ()
    members: tuple[str, ...] = ()
    bit_width: int = 0
    radix: Radix = "hex"
    events: tuple[DecoderEvent, ...] = ()
    hidden: bool = False
    source_channel: str | None = None  # decoder lanes: whose decode this is


@dataclass(frozen=True)
class Cursor:
    position_s: float
    label: str = ""


@dataclass(frozen=True)
class LanesDeclaration:
    """The capture: lanes in declaration order, the acquisition counts
    (acquired → drawn columns), the axis (host-supplied label + unit —
    sample-index or seconds mode is the host's choice, disclosed BY the
    label), the rate (1/axis step), and the cursor/trigger model
    (presentation-only: positions are host-supplied)."""

    title: str
    description: str
    lanes: tuple[LaneSpec, ...]
    acquired: int
    columns: int
    axis_label: str
    axis_unit: Literal["samples", "s"]
    sample_rate_hz: float | None = None
    trigger_s: float | None = None
    cursors: tuple[Cursor, ...] = ()


@dataclass(frozen=True)
class LaneSegment:
    """One drawn column of a channel lane — the ``reduce_lane`` column with
    its §E.4.2 state kind attached. A single-interior-transition column
    carries the pre/post edge; more than one carries the glitch mark."""

    first: int
    last: int
    state: LaneState | None
    state_kind: StateKind
    glitch: bool
    edge_from: LaneState | None = None
    edge_to: LaneState | None = None


@dataclass(frozen=True)
class BusCell:
    """One drawn column of a bus lane: the formatted value, or ``unknown``
    when any member column fails to resolve stably (x/z, or an interior
    edge/glitch — a column where a member changed is as unstable as an
    unknown; never a fabricated number over a transition)."""

    first: int
    last: int
    value: str | None
    unknown: bool


@dataclass(frozen=True)
class ComposedSpan:
    """One rendered decoder span: the event's extent mapped through the
    capture axis to sample positions, clipped to the window, the width
    clamped at the one-column minimum (a zero-width event renders that
    minimum mark, never invisible)."""

    start_sample: int
    end_sample: int
    payload: str


@dataclass(frozen=True)
class ComposedLane:
    spec: LaneSpec
    segments: tuple[LaneSegment, ...] = ()
    bus_cells: tuple[BusCell, ...] = ()
    spans: tuple[ComposedSpan, ...] = ()
    waiting: bool = False


@dataclass(frozen=True)
class ComposedLanes:
    title: str
    description: str
    lanes: tuple[ComposedLane, ...]
    acquired: int
    plotted: int
    acquisition_text: str
    axis_label: str
    axis_unit: str
    rate_suffix: str
    trigger_sample: int | None
    cursor_positions_samples: tuple[int, ...]
    delta_t_text: str


def _state_segments(
    states: Sequence[LaneState], columns: int
) -> list[LaneSegment]:
    segments: list[LaneSegment] = []
    for column in reduce_lane(states, columns):
        edge_from, edge_to = (column.edge.from_, column.edge.to) if column.edge else (None, None)
        segments.append(
            LaneSegment(
                first=column.first,
                last=column.last,
                state=column.state,
                state_kind=_STATE_KIND[column.state],
                glitch=column.glitch,
                edge_from=edge_from,
                edge_to=edge_to,
            )
        )
    return segments


def _member_column_state(
    states: Sequence[LaneState], first: int, last: int
) -> str | None:
    """The member's stable state over the column, or None when the column
    does not resolve stably (x/z anywhere, or an interior change)."""
    covered = states[first:last]
    distinct = set(covered)
    if len(distinct) != 1:
        return None
    state = covered[0]
    return state if state in ("0", "1") else None


def _format_bus_value(value: int, bit_width: int, radix: Radix) -> str:
    if radix == "decimal":
        return str(value)
    nibbles = max(1, (bit_width + 3) // 4)
    return f"{value:0{nibbles}X}"


def _bus_cells(
    spec: LaneSpec,
    member_states: Mapping[str, Sequence[LaneState]],
    columns: int,
) -> list[BusCell]:
    cells: list[BusCell] = []
    for column in reduce_lane(member_states[spec.members[0]], columns):
        value = 0
        unknown = False
        for position, member in enumerate(spec.members):  # first declared = LSB
            states = member_states[member]
            stable = _member_column_state(states, column.first, column.last)
            if stable is None:
                unknown = True
                break
            value |= int(stable) << position
        cells.append(
            BusCell(
                first=column.first,
                last=column.last,
                value=None if unknown else _format_bus_value(value, spec.bit_width, spec.radix),
                unknown=unknown,
            )
        )
    return cells


def _spans(
    spec: LaneSpec,
    acquired: int,
    rate_hz: float | None,
    hidden_channels: set[str],
) -> tuple[list[ComposedSpan], bool]:
    """Map the decoder's events through the capture axis to sample
    positions; clip to the window; clamp the width at the one-column
    minimum. An event whose source channel is hidden renders NOTHING and
    orphans onto no neighbour (the lane keeps its awaiting-render note);
    a declared lane with no renderable events waits visibly."""
    if rate_hz is None or (
        spec.source_channel is not None and spec.source_channel in hidden_channels
    ):
        return [], True
    spans: list[ComposedSpan] = []
    for event in spec.events:
        start = round(event.start_s * rate_hz)
        end = round(event.end_s * rate_hz)
        if end <= 0 or start >= acquired:  # fully outside the window
            continue
        start = max(0, start)
        end = min(acquired, end)
        if end <= start:  # zero-width [t, t): the minimum mark, never invisible
            end = start + 1
        spans.append(ComposedSpan(start, end, event.payload))
    return spans, not spans


def compose_lanes(
    declaration: LanesDeclaration,
    member_states: Mapping[str, Sequence[LaneState]] | None = None,
) -> ComposedLanes:
    """Compose the capture view: channel segments over ``reduce_lane``, bus
    cells over the member states, decoder spans through the capture axis,
    and the time-axis furniture (rate suffix, trigger marker from a non-null
    trigger time, cursors with the Δt readout in the axis's mode — seconds
    mode scales the unit, sample-index mode reads the raw difference, never
    both)."""
    member_states = member_states or {}
    hidden_channels = {spec.label for spec in declaration.lanes if spec.hidden}
    composed: list[ComposedLane] = []
    for spec in declaration.lanes:
        if spec.kind == "channel":
            composed.append(
                ComposedLane(
                    spec=spec,
                    segments=tuple(
                        _state_segments(spec.states, declaration.columns)
                    ),
                )
            )
        elif spec.kind == "group":
            composed.append(
                ComposedLane(
                    spec=spec,
                    bus_cells=tuple(
                        _bus_cells(spec, member_states, declaration.columns)
                    ),
                )
            )
        else:
            spans, waiting = _spans(
                spec, declaration.acquired, declaration.sample_rate_hz, hidden_channels
            )
            composed.append(ComposedLane(spec=spec, spans=tuple(spans), waiting=waiting))
    rate_suffix = ""
    if declaration.sample_rate_hz is not None:
        if declaration.sample_rate_hz >= 1e6:
            rate_suffix = f"at {declaration.sample_rate_hz / 1e6:g} MHz"
        else:
            rate_suffix = f"at {declaration.sample_rate_hz / 1e3:g} kHz"
    acquisition = f"Acquired {declaration.acquired} samples · plotted {declaration.columns}"
    if rate_suffix:
        acquisition = f"{acquisition} {rate_suffix}"
    trigger_sample = (
        round(declaration.trigger_s * (declaration.sample_rate_hz or 0.0))
        if declaration.trigger_s is not None
        else None
    )
    cursor_samples = tuple(
        round(cursor.position_s * (declaration.sample_rate_hz or 0.0))
        for cursor in declaration.cursors
    )
    delta_text = ""
    if len(declaration.cursors) >= 2:
        if declaration.axis_unit == "samples":
            delta_text = f"Δt = {cursor_samples[1] - cursor_samples[0]} samples"
        else:
            delta_seconds = declaration.cursors[1].position_s - declaration.cursors[0].position_s
            micro = delta_seconds * 1e6
            delta_text = f"Δt = {micro:g} µs"
    # §E.4.6: decoder lanes are annotation rows BENEATH the channel and bus
    # rows — regrouped by kind, each group keeping its own declaration order
    # (lane indices never renumber: identity is position).
    beneath = [lane for lane in composed if lane.spec.kind != "decoder"]
    beneath += [lane for lane in composed if lane.spec.kind == "decoder"]
    return ComposedLanes(
        title=declaration.title,
        description=declaration.description,
        lanes=tuple(beneath),
        acquired=declaration.acquired,
        plotted=declaration.columns,
        acquisition_text=acquisition,
        axis_label=declaration.axis_label,
        axis_unit=declaration.axis_unit,
        rate_suffix=rate_suffix,
        trigger_sample=trigger_sample,
        cursor_positions_samples=cursor_samples,
        delta_t_text=delta_text,
    )
