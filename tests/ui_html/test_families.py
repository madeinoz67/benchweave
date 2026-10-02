"""Slice-2 structural-family unit tests (G1b design record §3 slice 2).

Each family's artifact over the REAL contract row (parsed in-process): the
row's own cells drive the fixture or the assertion, so these tests are the
fast lane for the row layer's structural families — panel, data-table,
alert-bubble (§E.1 + §B.1), mode-banner (§E.1 + §D.1), numeric-input,
rotary-control, reading-tile (§E.1 + §B.3 + §E.3), confirm-action, §C.2
labels, §C.3 refusals, §F.1 icons, §E.2.2 sequences, §A token rows.
"""

from __future__ import annotations

from pathlib import Path

from benchweave_ui_html import artifacts, fixtures, partials
from benchweave_ui_html.data import DisabledLabelData, RefusalData
from benchweave_ui_html.grammar import Row, parse_contract
from benchweave_ui_html.manifest import MANIFEST

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "internal" / "ui-contract.md"

ICON_KEYS = ("neutral", "success", "advisory", "warning", "critical", "trip",
             "busy", "hidden", "staged", "limiting")
SEQUENCE_KEYS = ("dash-1", "dash-2", "symbol-1", "symbol-2", "symbol-3", "symbol-4",
                 "symbol-5", "symbol-6", "symbol-7", "symbol-8")


def _row(slug: str, key: str) -> Row:
    contract = parse_contract(CONTRACT.read_text(encoding="utf-8"), MANIFEST)
    for table in contract.tables:
        for row in table.body:
            if row.row_id == f"{slug}::{key}":
                return row
    raise AssertionError(f"row not found: {slug}::{key}")


def _rows(slug: str) -> list[Row]:
    contract = parse_contract(CONTRACT.read_text(encoding="utf-8"), MANIFEST)
    table = contract.by_slug(slug)
    assert table is not None
    return list(table.body)


# --- §E.1 structural components over their own rows ---------------------------


def test_e1_structural_components_satisfy_their_rows() -> None:
    for key in (
        "button",
        "numeric-input",
        "rotary-control",
        "reading-tile",
        "alert-bubble",
        "data-table",
        "panel",
        "mode-banner",
        "confirm-action",
    ):
        artifact = artifacts._component_factory(key)
        assert artifact.satisfies(_row("e-1-components", key)) == [], key


def test_reading_tile_carries_the_state_and_set_evidence() -> None:
    """The canonical fixture renders WITH §B.3's state and §E.3's set line
    (the row's Notes: the all-modes precedent)."""
    html = partials.render_reading(fixtures.reading())
    assert 'data-bw-reading-state="limiting"' in html
    assert 'data-bw-reading-role="set"' in html
    assert "Set 12.0 V" in html
    assert "Limiting" in html
    assert "steady · 2 s" in html


def test_mode_banner_renders_entries_in_d1_order() -> None:
    html = partials.render_mode_banner(fixtures.mode_banner())
    order = [
        html.index(wording)
        for wording in (
            "SIMULATED PRESENTATION DATA",
            "NO GATEWAY · LOCAL PRESENTATION ONLY",
            "NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED",
            "NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE",
        )
    ]
    assert order == sorted(order)


# --- §B.1 severities: every row drives its own fixture ------------------------


def test_severity_rows_satisfy_with_correct_live_regions_and_dismissal() -> None:
    for row in _rows("b-1-severities"):
        key = row.key
        artifact = artifacts.SeverityRowArtifact(key)
        assert artifact.satisfies(row) == [], key


def test_dismiss_affordance_discriminates() -> None:
    """warning (persistent-until-acknowledged-or-resolved) must NOT render a
    dismiss affordance while advisory must — the dismissal-class arm has
    teeth on both sides."""
    advisory = artifacts.SeverityRowArtifact("advisory").satisfies(
        _row("b-1-severities", "advisory")
    )
    warning = artifacts.SeverityRowArtifact("warning").satisfies(
        _row("b-1-severities", "warning")
    )
    assert advisory == []
    assert warning == []


# --- §D.1 modes ---------------------------------------------------------------


def test_mode_rows_satisfy_their_fixed_wording() -> None:
    for row in _rows("d-1-modes"):
        assert artifacts.ModeRowArtifact(row.key).satisfies(row) == [], row.key


# --- §C.2 labels --------------------------------------------------------------


def test_label_rows_satisfy_with_the_device_state_parameter() -> None:
    for row in _rows("c-2-disabled-reason-enum"):
        assert artifacts.LabelRenderArtifact(row.key).satisfies(row) == [], row.key


def test_device_state_label_substitutes_the_canonical_parameter() -> None:
    html = partials.render_disabled_label(
        DisabledLabelData(reason="device-state", label="Device must be idle")
    )
    assert "Device must be idle" in html
    assert 'data-bw-disabled-reason="device-state"' in html


# --- §C.3 refusals ------------------------------------------------------------


def test_refusal_rows_satisfy_with_their_own_cells() -> None:
    for row in _rows("c-3-refusal-mapping"):
        assert artifacts.RefusalRenderArtifact(row.key).satisfies(row) == [], row.key


def test_no_response_renders_unknown_sent_status() -> None:
    html = partials.render_refusal(
        RefusalData(
            code="no-response",
            severity="critical",
            what_happened="No interface answer arrived (transport failure or timeout).",
            sent_status="UNKNOWN",
            operator_action="Reconcile before acting.",
        )
    )
    assert 'data-bw-sent-status="UNKNOWN"' in html


# --- §B.3 state + §E.3 triad ---------------------------------------------------


def test_state_row_satisfies_with_negative_arms() -> None:
    row = _row("b-3-reading-states", "limiting")
    assert artifacts.StateRowArtifact("limiting").satisfies(row) == []


def test_triad_rows_satisfy() -> None:
    for key in ("measured", "set", "staged"):
        row = _row(
            "e-3-setpoint-presentation-reading-tile-sub-rows", key
        )
        assert artifacts.TriadRowArtifact(key).satisfies(row) == [], key


# --- §F.1 icons / §E.2.2 sequences ---------------------------------------------


def test_icon_rows_satisfy_and_are_injective() -> None:
    for row in _rows("f-1-icons"):
        assert artifacts.IconPartialArtifact(row.key).satisfies(row) == [], row.key


def test_sequence_rows_satisfy_and_are_injective() -> None:
    for row in _rows("e-2-2-sequences"):
        assert artifacts.SequencePartialArtifact(row.key).satisfies(row) == [], row.key


def test_icon_set_is_ten_way_injective() -> None:
    renders = [partials.render_icon(key) for key in ICON_KEYS]
    assert len(set(renders)) == 10


def test_sequence_set_is_ten_way_injective() -> None:
    renders = [partials.render_sequence(key) for key in SEQUENCE_KEYS]
    assert len(set(renders)) == 10


# --- §A token rows over the real CSS mirror ------------------------------------


def test_token_pair_rows_satisfy_over_themes_css() -> None:
    for row in _rows("a-1-colour-palette"):
        assert artifacts.TokenPairArtifact().satisfies(row) == [], row.key


def test_token_value_rows_satisfy_over_tokens_css() -> None:
    for slug in ("a-2-spacing-and-layout", "a-3-radius", "a-4-typography-fonts"):
        for row in _rows(slug):
            assert artifacts.TokenValueArtifact().satisfies(row) == [], (slug, row.key)


def test_token_pair_detects_a_drifted_value() -> None:
    """A doctored themes.css (one value changed) reds that token's row — the
    row-direction discrimination proof, via the injectable CSS source (the
    asset itself is never written)."""
    row = _row("a-1-colour-palette", "--bw-canvas")
    doctored = artifacts.THEMES_CSS.read_text(encoding="utf-8").replace(
        "--bw-canvas: #e4ebef;", "--bw-canvas: #000000;"
    )
    assert "--bw-canvas: #000000;" in doctored, "the doctoring must bite"
    messages = artifacts.TokenPairArtifact(themes_text=doctored).satisfies(row)
    assert any("--bw-canvas light" in message for message in messages), messages
    assert artifacts.TokenPairArtifact().satisfies(row) == []
