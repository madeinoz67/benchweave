"""UR-07 — the server-side plot computation, emitted as data attributes.

Pure functions in, an emit-model out (G1b design record §1.3): slot
assignment (§E.2.1), pass-2 hint resolution (§E.2.0), y-axis assignment
(§E.2.3), reference-line binding (§E.2.4), the acquisition disclosure
(§E.2.5) and provenance markers (§E.2.6). Every name in the emitted
vocabulary is asserted by at least one contract row, so a rename reds the
harness — ``plot.py``'s emit model is the single source of truth a future
host script hydrates from.

The module makes NO draw-visibility claim (rubric G-render: payload and
attribute pins cannot falsify draw claims, so none are made — geometric
realization is G1d's axe/screenshot lane). The canvas element carries no
fake pixels: it is the empty hydrate target.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

#: §E.2.1: the dash names → the §E.1 ``data-line`` resolved forms
#: ("solid"/"dashed — the resolved dash, not a display position").
DASH_TO_DATA_LINE: dict[str, str] = {"dash-1": "solid", "dash-2": "dashed"}

#: §A.1: the plot's emphasis role is series slot 1.
EMPHASIS_SERIES = "--bw-series-1"

#: §E.2.0: the muted repaint target.
MUTED_SERIES = "--bw-text-muted"

ProvenanceKind = Literal["measured", "derived", "device-averaged", "display-processed"]


# --- §E.2.1 slot assignment ----------------------------------------------------


@dataclass(frozen=True)
class SlotAssignment:
    """One declared channel's pass-1 slot facts (pure function of the
    declared id set: bytewise sort, ``slot = ((i mod 8) + 1)`` with the
    dash wrap at 8)."""

    channel_id: str
    index: int
    slot: int
    series_token: str
    dash: str
    symbol: str


def assign_slots(declared_ids: Sequence[str]) -> list[SlotAssignment]:
    """§E.2: sort the declared ids bytewise (UTF-8 byte order) and assign
    slot ``i`` (0-based) its colour/dash/symbol. Display order never enters
    the assignment; the 16-id ceiling is the wire schema's (``maxItems``),
    not ours — a 17th id would collide with slot 8's pair and is refused by
    the wire first."""
    if len(set(declared_ids)) != len(declared_ids):
        raise ValueError("duplicate declared channel id (the wire schema refuses it)")
    ordered = sorted(declared_ids, key=lambda channel_id: channel_id.encode("utf-8"))
    assignments: list[SlotAssignment] = []
    for index, channel_id in enumerate(ordered):
        slot = (index % 8) + 1
        assignments.append(
            SlotAssignment(
                channel_id=channel_id,
                index=index,
                slot=slot,
                series_token=f"--bw-series-{slot}",
                dash="dash-1" if index < 8 else "dash-2",
                symbol=f"symbol-{slot}",
            )
        )
    return assignments


# --- §E.2.0 pass-2 composition --------------------------------------------------


@dataclass(frozen=True)
class ChannelHint:
    """The composition-layer hint (the same host-knowledge seam as trace
    provenance — the preview wire carries no hint field)."""

    color_role: Literal["accent", "muted"] | None = None
    visible: bool = True


@dataclass(frozen=True)
class ResolvedTrace:
    """Pass-2 result per trace: the resolved colour (post-hint), the dash,
    the symbol, and the visibility filter — styles resolved over the full
    declared set BEFORE visibility filters (hiding never restyles)."""

    assignment: SlotAssignment
    resolved_series: str
    data_line: str
    hidden: bool


def resolve_hints(
    assignments: Sequence[SlotAssignment],
    hints: Mapping[str, ChannelHint],
    declaration_order: Sequence[str],
    *,
    theme_resolves_muted: bool = True,
) -> list[ResolvedTrace]:
    """§E.2.0 pass 2 over the pass-1 assignments.

    - The emphasis colour (``--bw-series-1``) renders exactly once per plot:
      the first bytewise slot among VISIBLE traces claims it by default, so
      an accent hint on any other trace loses silently — no cascade.
    - A hidden trace releases its claim and neither claims nor starves.
    - A muted hint repaints ``--bw-text-muted`` and releases its claim; the
      token-less fallback (``theme_resolves_muted=False``) keeps the slot
      colour (which still claims if it is slot 1).
    - With the default claimant released, the earliest visible trace hinting
      accent (in declaration order) wins the emphasis; the others revert to
      their slot colours.
    """
    hint_of = {
        assignment.channel_id: hints.get(assignment.channel_id, ChannelHint())
        for assignment in assignments
    }
    # The emphasis claim is tied to pass-1 SLOT 1 (the trace at bytewise
    # index 0), not to "the first visible trace": a hidden slot 1 releases
    # its claim, and no other trace is restyled into it ("hiding a channel
    # never restyles its siblings").
    slot_one = assignments[0] if assignments else None
    slot_one_hint = hint_of.get(slot_one.channel_id) if slot_one else None
    slot_one_claims = bool(
        slot_one_hint
        and slot_one_hint.visible
        and not (
            slot_one_hint.color_role == "muted" and theme_resolves_muted
        )  # a resolved muted repaint releases the claim
    )
    accent_winner: SlotAssignment | None = None
    if not slot_one_claims:
        candidates = [
            assignment
            for assignment in assignments
            if hint_of[assignment.channel_id].visible
            and hint_of[assignment.channel_id].color_role == "accent"
        ]
        if candidates:
            accent_winner = min(
                candidates, key=lambda a: declaration_order.index(a.channel_id)
            )
    resolved: list[ResolvedTrace] = []
    for assignment in assignments:
        hint = hint_of[assignment.channel_id]
        if assignment is slot_one and slot_one_claims:
            series = EMPHASIS_SERIES  # slot 1's default is the emphasis colour
        elif not hint.visible:
            series = assignment.series_token  # hidden: styles already resolved
        elif hint.color_role == "muted" and theme_resolves_muted:
            series = MUTED_SERIES
        elif hint.color_role == "accent" and assignment is accent_winner:
            series = EMPHASIS_SERIES
        else:
            series = assignment.series_token
        resolved.append(
            ResolvedTrace(
                assignment=assignment,
                resolved_series=series,
                data_line=DASH_TO_DATA_LINE[assignment.dash],
                hidden=not hint.visible,
            )
        )
    return resolved


# --- §E.2.3 y-axis assignment ----------------------------------------------------


@dataclass(frozen=True)
class TraceSpec:
    """One declared trace: channel id, unit (trimmed before grouping),
    the samples the renderer DREW (``values.length`` semantics), the
    trace's OWN acquired count (§E.2.5's ``{n}`` is per-trace — the M1
    fold: one acquisition row per visible decimated trace, never a summed
    scalar), and the host-supplied provenance classification (§E.2.6)."""

    channel_id: str
    unit: str
    samples: tuple[float, ...] = ()
    acquired: int | None = None
    provenance: ProvenanceKind = "measured"
    derivation: str | None = None
    averaging_depth: int | None = None
    processing_name: str | None = None
    processing_window: str | None = None


@dataclass(frozen=True)
class AxesModel:
    """The §E.2.3 outcome: the rendering axes (first-declaration order over
    the FULL declared set, then the visibility filter — assignment never
    reshuffles), the per-channel axis numbers (renumbered onto survivors),
    and the >2-unit refusal flag."""

    refusal: bool
    units: tuple[str | None, ...]
    trace_axis: dict[str, str]


def assign_axes(traces: Sequence[TraceSpec]) -> AxesModel:
    """§E.2.3 over the FULL declared set: trimmed-unit EXACT string grouping
    (case-sensitive; a whitespace variant never spawns a second axis), unit
    order by first declaration, and the >2-unit refusal (no axes, no trace
    bindings — the renderer refuses to conflate incommensurable units)."""
    distinct: list[str | None] = []
    for trace in traces:
        trimmed = trace.unit.strip()
        unit: str | None = trimmed if trimmed else None  # the unitless group
        if unit not in distinct:
            distinct.append(unit)
    if len(distinct) > 2:
        return AxesModel(refusal=True, units=(), trace_axis={})
    axis_of_unit = {unit: str(number + 1) for number, unit in enumerate(distinct)}
    trace_axis = {
        trace.channel_id: axis_of_unit[trace.unit.strip() or None] for trace in traces
    }
    return AxesModel(refusal=False, units=tuple(distinct), trace_axis=trace_axis)


def filter_axes(axes: AxesModel, traces: Sequence[TraceSpec], hidden: set[str]) -> AxesModel:
    """The §E.2.3 fourth condition: axes whose traces are ALL
    presentation-hidden do not render; surviving traces' bindings are
    remapped onto the surviving axes (renumbered 1..k, declaration order
    preserved). Called by ``compose_plot`` with the resolved visibility."""
    if axes.refusal:
        return axes
    surviving_units: list[str | None] = []
    for unit in axes.units:
        unit_traces = [t for t in traces if (t.unit.strip() or None) == unit]
        if any(t.channel_id not in hidden for t in unit_traces):
            surviving_units.append(unit)
    renumbered = {unit: str(i + 1) for i, unit in enumerate(surviving_units)}
    trace_axis = {
        trace.channel_id: renumbered[trace.unit.strip() or None]
        for trace in traces
        if trace.channel_id not in hidden and (trace.unit.strip() or None) in renumbered
    }
    return AxesModel(refusal=False, units=tuple(surviving_units), trace_axis=trace_axis)


# --- §E.2.4 reference lines -------------------------------------------------------


@dataclass(frozen=True)
class ReferenceLine:
    """An applied or configured limit: meaning, value, unit, and the target
    traces it constrains."""

    meaning: str
    value: str
    unit: str
    targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class ThresholdLine:
    """A SEVERITY threshold — a distinct kind from a reference line
    (§E.2.4 Distinctness): severity hue and dashed, never the border token,
    never dotted."""

    severity: str
    value: str
    unit: str


@dataclass(frozen=True)
class EmittedRefLine:
    label: str
    unit: str
    colour_token: str
    dash: str
    axis: str


@dataclass(frozen=True)
class EmittedThreshold:
    label: str
    severity: str
    colour_token: str
    dash: str
    axis: str


# --- §E.2.6 provenance -------------------------------------------------------------


def provenance_marker(trace: TraceSpec) -> tuple[str | None, str | None]:
    """(marker text, disclosure text) per §E.2.6 — ``measured`` carries
    NEITHER the attribute nor a marker (the default asserts nothing more)."""
    if trace.provenance == "measured":
        return None, None
    if trace.provenance == "derived":
        derivation = trace.derivation or ""
        return "derived", f"{derivation} · uncertainty unknown"
    if trace.provenance == "device-averaged":
        # The L5 fold: the depth is the applied configured value from the
        # observed echo — a trace classified device-averaged WITHOUT a depth
        # is unrepresentable, not zero (never a default).
        if trace.averaging_depth is None:
            raise ValueError(
                "device-averaged requires the applied averaging_depth from the "
                "observed echo — never a default (§E.2.6)"
            )
        return f"device averaging {trace.averaging_depth}", None
    name = trace.processing_name or ""
    window = trace.processing_window or ""
    return f"display processing: {name} {window}".rstrip(), None


# --- the composed emit model --------------------------------------------------------


@dataclass(frozen=True)
class LegendRow:
    channel_id: str
    slot: int
    resolved_series: str
    data_line: str
    symbol: str
    hidden: bool
    axis: str
    provenance_kind: str | None
    provenance_marker: str | None
    provenance_disclosure: str | None


@dataclass(frozen=True)
class ComposedPlot:
    title: str
    description: str
    axes_attr: str
    refusal: bool
    legend: tuple[LegendRow, ...]
    ref_lines: tuple[EmittedRefLine, ...]
    thresholds: tuple[EmittedThreshold, ...]
    acquisition: tuple[AcquisitionRow, ...]


@dataclass(frozen=True)
class AcquisitionRow:
    """§E.2.5, per trace (the M1 fold): one disclosure row per VISIBLE
    trace that drew fewer points than it acquired — ``m`` is that trace's
    own drawn count, never a summed scalar across traces."""

    channel_id: str
    acquired: int
    drawn: int
    text: str


def acquisition_rows(
    visible_traces: Sequence[TraceSpec], rate: str | None
) -> tuple[AcquisitionRow, ...]:
    """§E.2.5: the disclosure is required exactly when a VISIBLE trace
    draws fewer points than it acquired (hidden traces draw nothing, so
    they disclose nothing); each row's ``m`` is computed from that trace's
    drawn sample count, never caller-supplied; an acquisition rate may
    append when known."""
    rows: list[AcquisitionRow] = []
    for trace in visible_traces:
        if trace.acquired is None:
            continue
        drawn = len(trace.samples)
        if drawn >= trace.acquired:
            continue
        text = f"Acquired {trace.acquired} samples · plotted {drawn}"
        if rate is not None:
            text = f"{text} at {rate}"
        rows.append(
            AcquisitionRow(
                channel_id=trace.channel_id, acquired=trace.acquired, drawn=drawn, text=text
            )
        )
    return tuple(rows)


def compose_plot(
    title: str,
    description: str,
    traces: Sequence[TraceSpec],
    hints: Mapping[str, ChannelHint],
    ref_lines: Sequence[ReferenceLine] = (),
    thresholds: Sequence[ThresholdLine] = (),
    rate: str | None = None,
    *,
    theme_resolves_muted: bool = True,
) -> ComposedPlot:
    """Compose the full emit model: pass-1 slots, pass-2 hints, axis
    assignment with the visibility filter, reference-line binding, and the
    per-trace acquisition rows. The >2-unit refusal renders NO traces."""
    declaration_order = [trace.channel_id for trace in traces]
    assignments = assign_slots(declaration_order)
    axes = assign_axes(traces)
    hidden = {
        channel for channel, hint in hints.items() if not hint.visible
    }
    axes = filter_axes(axes, traces, hidden)
    resolved = resolve_hints(
        assignments, hints, declaration_order, theme_resolves_muted=theme_resolves_muted
    )
    unit_of = {trace.channel_id: (trace.unit.strip() or None) for trace in traces}
    axis_by_unit = {unit: str(i + 1) for i, unit in enumerate(axes.units)}
    legend: list[LegendRow] = []
    # The M4 owner ruling (2026-10-02, adopt-with-recs): the >2-unit
    # refusal draws NO traces — the axis/canvas surface stays empty — but
    # the LEGEND stays: §E.1's "Every trace is listed in a visible legend"
    # is unqualified, and the legend is listing, not drawing (the TS
    # behavior). Slot facts are unit-independent, so every declared trace
    # lists with its slot; no axis binding exists on refusal.
    for trace_row in resolved:
        trace = next(t for t in traces if t.channel_id == trace_row.assignment.channel_id)
        marker, disclosure = provenance_marker(trace)
        unit = unit_of[trace.channel_id]
        legend.append(
            LegendRow(
                channel_id=trace.channel_id,
                slot=trace_row.assignment.slot,
                resolved_series=trace_row.resolved_series,
                data_line=trace_row.data_line,
                symbol=trace_row.assignment.symbol,
                hidden=trace_row.hidden,
                axis=axis_by_unit.get(unit, "") if not trace_row.hidden else "",
                provenance_kind=(
                    trace.provenance if trace.provenance != "measured" else None
                ),
                provenance_marker=marker,
                provenance_disclosure=disclosure,
            )
        )
    visible_traces = [t for t in traces if t.channel_id not in hidden]
    acquisition = acquisition_rows(visible_traces, rate)
    emitted_refs = tuple(
        EmittedRefLine(
            label=f"{line.meaning} · {line.value} {line.unit}",
            unit=line.unit,
            colour_token="--bw-border",  # noqa: S106 - a CSS custom-property name
            dash="dotted",
            axis=axis_by_unit.get(line.unit.strip() or None, ""),
        )
        for line in ref_lines
    )
    emitted_thresholds = tuple(
        EmittedThreshold(
            label=f"{line.severity} threshold · {line.value} {line.unit}",
            severity=line.severity,
            colour_token=f"--bw-{line.severity}",
            dash="dashed",
            axis=axis_by_unit.get(line.unit.strip() or None, ""),
        )
        for line in thresholds
    )
    return ComposedPlot(
        title=title,
        description=description,
        axes_attr=";".join(unit or "" for unit in axes.units),
        refusal=axes.refusal,
        legend=tuple(legend),
        ref_lines=emitted_refs,
        thresholds=emitted_thresholds,
        acquisition=acquisition,
    )
