"""Slice-3 plot-lane tests (G1b design record §3 slice 3): plot.py's pure
functions, the composed emit vocabulary, the §E.1 engineering-plot row, the
§E.2.1 slot rows, the §E.2.0 hint rows, the §E.2.3–§E.2.6 rule rows over the
real contract, and mutation control (b) — the dash wrap.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from benchweave_ui_html import artifacts, fixtures, partials, plot
from benchweave_ui_html.grammar import Row, parse_contract
from benchweave_ui_html.manifest import MANIFEST

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "internal" / "ui-contract.md"


def _rows(slug: str) -> list[Row]:
    table = parse_contract(CONTRACT.read_text(encoding="utf-8"), MANIFEST).by_slug(slug)
    assert table is not None
    return list(table.body)


# --- §E.2.1 slot assignment ------------------------------------------------------


def test_assign_slots_is_bytewise_with_the_wrap_at_eight() -> None:
    ids = [f"ch-{index:02d}" for index in range(16)]
    assignments = plot.assign_slots(ids)
    assert [a.slot for a in assignments] == [1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 5, 6, 7, 8]
    assert [a.dash for a in assignments] == ["dash-1"] * 8 + ["dash-2"] * 8
    assert [a.symbol for a in assignments] == [f"symbol-{(i % 8) + 1}" for i in range(16)]
    assert assignments[0].series_token == "--bw-series-1"


def test_assign_slots_sorts_bytewise_not_lexicographically_by_codepoint() -> None:
    # UTF-8 byte order is the contract's stated order; the distinction is
    # invisible for ASCII ids but the key function must be the bytes.
    assignments = plot.assign_slots(["b", "a", "c"])
    assert [a.channel_id for a in assignments] == ["a", "b", "c"]
    assert plot.assign_slots(["b", "a"])[0].channel_id == "a"


def test_assign_slots_refuses_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        plot.assign_slots(["a", "a"])


# --- §E.2.0 pass 2 ---------------------------------------------------------------


def test_slot_one_visible_beats_an_accent_hint_elsewhere() -> None:
    assignments = plot.assign_slots(["alpha", "beta"])
    resolved = plot.resolve_hints(
        assignments, {"beta": plot.ChannelHint("accent")}, ["alpha", "beta"]
    )
    by_channel = {r.assignment.channel_id: r for r in resolved}
    assert by_channel["beta"].resolved_series == "--bw-series-2"


def test_released_claim_goes_to_the_earliest_visible_accent_hint() -> None:
    assignments = plot.assign_slots(["alpha", "beta", "gamma"])
    resolved = plot.resolve_hints(
        assignments,
        {
            "alpha": plot.ChannelHint(visible=False),
            "beta": plot.ChannelHint("accent"),
            "gamma": plot.ChannelHint("accent"),
        },
        ["alpha", "beta", "gamma"],
    )
    by_channel = {r.assignment.channel_id: r for r in resolved}
    assert by_channel["beta"].resolved_series == "--bw-series-1"
    assert by_channel["gamma"].resolved_series == "--bw-series-3"


def test_muted_repaints_and_releases_without_cascade() -> None:
    assignments = plot.assign_slots(["alpha", "beta"])
    resolved = plot.resolve_hints(
        assignments, {"alpha": plot.ChannelHint("muted")}, ["alpha", "beta"]
    )
    by_channel = {r.assignment.channel_id: r for r in resolved}
    assert by_channel["alpha"].resolved_series == "--bw-text-muted"
    assert by_channel["beta"].resolved_series == "--bw-series-2"


# --- §E.2.3 axes ------------------------------------------------------------------


def test_axes_trim_grouping_case_and_refusal() -> None:
    axes = plot.assign_axes([plot.TraceSpec("v", "V"), plot.TraceSpec("w", " V")])
    assert axes.units == ("V",)
    assert plot.assign_axes([plot.TraceSpec("v", "V"), plot.TraceSpec("w", "v")]).refusal is False
    two = plot.assign_axes([plot.TraceSpec("v", "V"), plot.TraceSpec("i", "A")])
    assert two.units == ("V", "A")
    assert plot.assign_axes(
        [plot.TraceSpec("v", "V"), plot.TraceSpec("i", "A"), plot.TraceSpec("p", "W")]
    ).refusal is True
    assert plot.assign_axes([plot.TraceSpec("n", "")]).units == (None,)


def test_hidden_axes_drop_and_survivors_renumber() -> None:
    traces = (plot.TraceSpec("voltage", "V"), plot.TraceSpec("current", "A"))
    axes = plot.assign_axes(traces)
    filtered = plot.filter_axes(axes, traces, {"voltage"})
    assert filtered.units == ("A",)
    assert filtered.trace_axis == {"current": "1"}


# --- §E.2.5 acquisition -------------------------------------------------------------


def test_acquisition_m_is_computed_never_supplied() -> None:
    """The M1 fold: per-trace acquisition rows — ``m`` is each trace's own
    drawn count, never a caller-supplied scalar or a cross-trace sum."""
    rows = plot.acquisition_rows(
        [plot.TraceSpec("v", "V", samples=(0.0, 1.0), acquired=100)], None
    )
    assert [row.text for row in rows] == ["Acquired 100 samples · plotted 2"]
    rows = plot.acquisition_rows(
        [plot.TraceSpec("v", "V", samples=(0.0, 1.0), acquired=100)], "1 kHz"
    )
    assert rows[0].text == "Acquired 100 samples · plotted 2 at 1 kHz"


def test_no_visible_decimation_no_disclosure() -> None:
    rows = plot.acquisition_rows(
        [plot.TraceSpec("v", "V", samples=(1.0, 2.0, 3.0), acquired=3)], None
    )
    assert rows == ()


# --- the contract rows --------------------------------------------------------------


def test_e1_engineering_plot_row_satisfies() -> None:
    artifact = artifacts._component_factory("engineering-plot")
    row = _rows("e-1-components")[5]  # engineering-plot
    assert row.key == "engineering-plot"
    assert artifact.satisfies(row) == []


@pytest.mark.parametrize("index", range(16), ids=str)
def test_slot_rows_satisfy(index: int) -> None:
    rows = {row.key: row for row in _rows("e-2-1-slot-mapping")}
    assert artifacts.SlotValueArtifact(str(index)).satisfies(rows[str(index)]) == []


def test_hint_rows_satisfy() -> None:
    for row in _rows("e-2-0-pass-2-composition-channel-hints"):
        assert artifacts.HintRowArtifact(row.key).satisfies(row) == [], row.key


@pytest.mark.parametrize(
    "slug",
    [
        "e-2-3-y-axis-assignment",
        "e-2-4-reference-lines",
        "e-2-5-acquisition-disclosure",
        "e-2-6-trace-provenance",
    ],
)
def test_plot_rule_rows_satisfy(slug: str) -> None:
    for row in _rows(slug):
        assert artifacts._plot_rule_factory(row.key).satisfies(row) == [], (slug, row.key)


# --- mutation control (b): the dash wrap ---------------------------------------------


def test_mutation_control_b_broken_dash_wrap_reds_exactly_slots_8_to_15(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Design record §6 control (b): with the wrap broken (i ≥ 8 keeps
    dash-1), exactly the i=8..15 slot rows red — the assertions
    discriminate the wrap, and nothing else moves."""

    def broken_assign_slots(declared_ids: list[str]) -> list[plot.SlotAssignment]:
        ordered = sorted(declared_ids, key=lambda channel: channel.encode("utf-8"))
        return [
            plot.SlotAssignment(
                channel_id=channel,
                index=index,
                slot=(index % 8) + 1,
                series_token=f"--bw-series-{(index % 8) + 1}",
                dash="dash-1",  # THE BREAK: the wrap at 8 never happens
                symbol=f"symbol-{(index % 8) + 1}",
            )
            for index, channel in enumerate(ordered)
        ]

    monkeypatch.setattr(plot, "assign_slots", broken_assign_slots)
    rows = {row.key: row for row in _rows("e-2-1-slot-mapping")}
    red = [
        index
        for index in range(16)
        if artifacts.SlotValueArtifact(str(index)).satisfies(rows[str(index)])
    ]
    assert red == list(range(8, 16)), red


# --- no draw claims (UR-07 posture) ----------------------------------------------------


def test_the_canvas_is_an_empty_hydrate_target() -> None:
    html = partials.render_plot(fixtures.engineering_plot())
    assert 'class="bw-plot__canvas"' in html
    assert "svg" not in html.split("bw-plot__legend")[0]  # no fake pixels before the legend
