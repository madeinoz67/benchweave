"""The consolidated Tier-3 fold's tests (issue #298, both refute lanes):
M1 the per-trace acquisition model and the computed lanes plotted count,
M2 the accent-before-slot-1 corner, M3 the enum-membership arms, and the
lane-B LOWs L1/L2/L3/L5/L6 — each with its discriminating arm.
"""

from __future__ import annotations

from typing import cast

import pytest
from benchweave_ui_html import artifacts, fixtures, partials
from benchweave_ui_html.assertions import RenderedComponent
from benchweave_ui_html.decimate import LaneState
from benchweave_ui_html.grammar import Row
from benchweave_ui_html.lanes import (
    Cursor,
    DecoderEvent,
    LanesDeclaration,
    LaneSpec,
    compose_lanes,
)


def _row(slug: str, key: str, cells: tuple[str, ...]) -> Row:
    return Row(row_id=f"{slug}::{key}", table_slug=slug, cells=cells)


# --- M1: the acquisition model -------------------------------------------------


def test_acquisition_rows_are_per_trace_never_a_summed_scalar() -> None:
    rendered = RenderedComponent(partials.render_plot(fixtures.acquisition_multi_trace_plot()))
    texts = sorted(rendered.texts_of_elements(class_hook="bw-plot__acquisition"))
    assert texts == ["Acquired 100 samples · plotted 2", "Acquired 200 samples · plotted 4"]
    rows = [
        e for e in rendered.elements if "bw-plot__acquisition" in e.class_tokens
    ]
    by_channel = {e.attrs.get("data-bw-channel-id"): e for e in rows}
    assert by_channel["voltage"].attrs.get("data-bw-plotted") == "2"
    assert by_channel["current"].attrs.get("data-bw-plotted") == "4"


def test_lanes_plotted_is_computed_not_the_requested_columns() -> None:
    """The M1 lanes arm: a 24-sample capture asked to draw 100 columns drew
    24 — the acquisition line reports the COMPUTED count."""
    stable = cast(tuple[LaneState, ...], ("1",) * 24)
    composed = compose_lanes(
        LanesDeclaration(
            title="Tiny capture",
            description="24 samples, 100 requested columns.",
            lanes=(LaneSpec(0, "channel", "clk", states=stable),),
            acquired=24,
            columns=100,
            axis_label="Samples",
            axis_unit="samples",
        )
    )
    assert composed.acquisition_text == "Acquired 24 samples · plotted 24"


# --- M2: the accent-before-slot-1 corner ----------------------------------------


def test_accent_declared_before_slot1_still_loses() -> None:
    rendered = RenderedComponent(
        partials.render_plot(fixtures.hint_accent_before_slot1_plot())
    )
    rows = {
        e.attrs.get("data-bw-channel-id"): e
        for e in rendered.elements
        if "data-bw-series-slot" in e.attrs
    }
    assert rows["alpha"].attrs.get("data-bw-resolved-series") == "--bw-series-1"
    assert rows["beta"].attrs.get("data-bw-resolved-series") == "--bw-series-2"


# --- M3: enum memberships (row-as-data cannot detect enum drift) ------------------


def test_refusal_severity_outside_b1_reds() -> None:
    scratch = _row(
        "c-3-refusal-mapping",
        "bogus",
        ("`bogus`", "`catastrophic`", "`what`", "`NO`", "`do`"),
    )
    messages = artifacts.RefusalRenderArtifact("bogus").satisfies(scratch)
    assert any("not a §B.1 severity key" in m for m in messages), messages


def test_disabled_reason_outside_c2_reds() -> None:
    scratch = _row(
        "c-2-disabled-reason-enum",
        "bogus-reason",
        ("`bogus-reason`", "`Nope`", "—"),
    )
    messages = artifacts.LabelRenderArtifact("bogus-reason").satisfies(scratch)
    assert any("not a §C.2 enum key" in m for m in messages), messages


def test_mode_outside_d1_reds() -> None:
    scratch = _row(
        "d-1-modes",
        "phantom-mode",
        ("`phantom-mode`", "`PHANTOM`", "never"),
    )
    messages = artifacts.ModeRowArtifact("phantom-mode").satisfies(scratch)
    assert any("not a §D.1 mode key" in m for m in messages), messages


# --- L1/L2: span gating and float extents -------------------------------------------


def _spans_of(events: tuple[DecoderEvent, ...]) -> list[tuple[float, float]]:
    composed = compose_lanes(
        LanesDeclaration(
            title="Gating",
            description="Span gating probes.",
            lanes=(
                LaneSpec(0, "channel", "data", states=cast(tuple[LaneState, ...], ("1",) * 100)),
                LaneSpec(1, "decoder", "DEC", events=events, source_channel="data"),
            ),
            acquired=200,
            columns=4,
            axis_label="Samples",
            axis_unit="samples",
            sample_rate_hz=1_000_000.0,
        )
    )
    return [(span.start_s, span.end_s) for span in composed.lanes[1].spans]


def test_zero_width_event_at_t_zero_renders() -> None:
    """The L1 fold: the old ``end <= 0`` gate dropped the [0, 0) event; a
    zero-width point IN the window renders its minimum mark."""
    spans = _spans_of((DecoderEvent(0.0, 0.0, "0x77"),))
    assert spans == [(0.0, 1e-06)]


def test_events_fully_outside_the_window_do_not_render() -> None:
    """Negative-side extents — zero-width or interval — render nothing."""
    assert _spans_of((DecoderEvent(-0.001, -0.001, "0x01"),)) == []
    assert _spans_of((DecoderEvent(-0.002, -0.001, "0x02"),)) == []
    assert _spans_of((DecoderEvent(0.0030, 0.0031, "0x03"),)) == []  # past the end


def test_span_extents_are_float_seconds_not_sample_ints() -> None:
    """The L2 fold: exact extents — 0.0001 s stays 0.0001, never rounded to
    a sample integer."""
    spans = _spans_of((DecoderEvent(0.0001, 0.0002, "0x55"),))
    assert spans == [(0.0001, 0.0002)]


# --- L3: edge columns render two single-value halves ---------------------------------


def test_edge_column_renders_two_single_value_halves() -> None:
    rendered = RenderedComponent(partials.render_lanes(fixtures.digital_lanes()))
    segments = artifacts._channel_segments(rendered)
    halves = [e for e in segments if e.attrs.get("data-bw-half")]
    assert halves, "the canonical fixture must exercise an edge column"
    for element in halves:
        state = str(element.attrs.get("data-bw-state") or "")
        assert "→" not in state, "an edge half carries a single value"
        assert element.attrs.get("data-bw-state-kind") in ("high", "low", "hatch", "midline")
    kinds = {(e.attrs.get("data-bw-state"), e.attrs.get("data-bw-half")) for e in halves}
    assert any(s == "1" and h == "first" for s, h in kinds)
    assert any(s == "x" and h == "second" for s, h in kinds)


# --- L5: device-averaged without a depth is unrepresentable ---------------------------


def test_device_averaged_without_depth_reds() -> None:
    from benchweave_ui_html.plot import TraceSpec as Spec
    from benchweave_ui_html.plot import provenance_marker

    with pytest.raises(ValueError, match="averaging_depth"):
        provenance_marker(Spec("rail", "V", provenance="device-averaged"))


def test_canonical_provenance_plot_still_greens() -> None:
    for row_key in ("measured", "derived", "device-averaged", "display-processed"):
        checker = artifacts._plot_rule_factory(row_key)
        assert checker.satisfies(Row(
            row_id=f"e-2-6-trace-provenance::{row_key}",
            table_slug="e-2-6-trace-provenance",
            cells=(f"`{row_key}`", "marker", "disclosure", "constraint"),
        )) == [], row_key


# --- L6: checker evidence is scoped to its own element source --------------------------


def test_state_rendering_ignores_bus_hatch_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    """§E.4.2's arm must take its evidence from CHANNEL lanes: a capture
    with NO x-state channel segments (but z-state channels, so the z arm is
    satisfied) and hatched BUS cells still reds the x arm — the pre-fold
    checker read the bus cells' hatch attribute and passed."""
    stable = cast(tuple[LaneState, ...], ("1",) * 50 + ("z",) * 50)
    toggling = cast(
        tuple[LaneState, ...], tuple("10"[(i // 5) % 2] for i in range(100))
    )
    unstable_bus = compose_lanes(
        LanesDeclaration(
            title="Unscoped probe",
            description="A bus whose members never resolve stably.",
            lanes=(
                LaneSpec(0, "channel", "steady", states=stable),
                LaneSpec(1, "channel", "wild", states=toggling),
                LaneSpec(2, "group", "bus", members=("wild", "steady"), bit_width=2),
            ),
            acquired=100,
            columns=4,
            axis_label="Samples",
            axis_unit="samples",
        ),
        member_states={"steady": stable, "wild": toggling},
    )
    monkeypatch.setattr(
        fixtures, "digital_lanes", lambda: unstable_bus, raising=True
    )
    messages = artifacts._check_state_rendering("x` and `z")(
        Row(row_id="probe", table_slug="e-4-2-state-rendering", cells=("`x` and `z`", "r"))
    )
    assert any("plain 'x' segment must render" in m for m in messages), messages
    assert not any("'z' segment" in m for m in messages), messages


def test_unknown_bus_ignores_channel_hatch_segments(monkeypatch: pytest.MonkeyPatch) -> None:
    """§E.4.3's arm must take its evidence from BUS cells: a capture whose
    bus resolves stably but whose channel lanes carry x segments still reds
    the unknown-bus arm (the pre-fold checker read the channel hatch)."""
    states = cast(
        tuple[LaneState, ...], (("1",) * 300) + (("x",) * 200) + (("0",) * 300)
    )
    stable_bus = compose_lanes(
        LanesDeclaration(
            title="Stable bus probe",
            description="A stable bus beside an x-state channel.",
            lanes=(
                LaneSpec(0, "channel", "data", states=states),
                LaneSpec(1, "channel", "clk", states=cast(tuple[LaneState, ...], ("1",) * 800)),
                LaneSpec(2, "group", "bus", members=("clk", "clk"), bit_width=2),
            ),
            acquired=800,
            columns=4,
            axis_label="Samples",
            axis_unit="samples",
        ),
        member_states={"clk": cast(tuple[LaneState, ...], ("1",) * 800), "data": states},
    )
    monkeypatch.setattr(fixtures, "digital_lanes", lambda: stable_bus, raising=True)
    messages = artifacts._check_groups_buses("Unknown bus")(
        Row(row_id="probe", table_slug="e-4-3-groups-and-buses", cells=("`Unknown bus`", "r"))
    )
    assert any("hatched" in m for m in messages), messages


# --- the canonical lanes row after the fold ---------------------------------------------


def test_canonical_capture_literals_hold_after_the_fold() -> None:
    composed = fixtures.digital_lanes()
    assert composed.acquisition_text == "Acquired 1000 samples · plotted 12 at 1 MHz"
    assert composed.delta_t_text == "Δt = 7 µs"


def test_reversed_cursors_read_the_magnitude() -> None:
    stable = cast(tuple[LaneState, ...], ("1",) * 100)
    composed = compose_lanes(
        LanesDeclaration(
            title="Reversed cursors",
            description="Cursors supplied in reverse order.",
            lanes=(LaneSpec(0, "channel", "clk", states=stable),),
            acquired=100,
            columns=4,
            axis_label="Samples",
            axis_unit="samples",
            sample_rate_hz=1_000_000.0,
            cursors=(Cursor(0.000017), Cursor(0.000010)),
        )
    )
    assert composed.delta_t_text == "Δt = 7 samples"


# --- M4 (owner-ruled 2026-10-02): the legend stays on the >2-unit refusal ------


def test_refusal_keeps_the_legend_and_empties_the_drawing_surface() -> None:
    """The M4 ruling (adopt-with-recs): §E.1's "Every trace is listed in a
    visible legend" is unqualified — the legend is listing, not drawing.
    Every declared trace stays listed with its slot; the drawing surface
    (axis bindings, the canvas payload) stays empty."""
    rendered = RenderedComponent(partials.render_plot(fixtures.three_unit_refusal_plot()))
    rows = [e for e in rendered.elements if "data-bw-series-slot" in e.attrs]
    assert len(rows) == 3, "every declared trace stays listed"
    assert {e.attrs.get("data-bw-channel-id") for e in rows} == {
        "voltage",
        "current",
        "power",
    }
    assert not any("data-bw-axis" in e.attrs for e in rendered.elements)
    canvas = next(e for e in rendered.elements if "bw-plot__canvas" in e.class_tokens)
    assert not rendered._element_texts[rendered.elements.index(canvas)].strip()
    assert any("bw-plot__refusal" in e.class_tokens for e in rendered.elements)
