"""Slice-4 lanes-lane tests (G1b design record §3 slice 4): the §E.1
digital-lanes row, the §E.4.1–§E.4.6 rule rows over the real contract, and
the composition's own vocabulary (identity is lane POSITION; colour carries
nothing). The end state lands here: 158 of 168 rows green, the ten
behaviour rows red with the honest missing-artifact message.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from benchweave_ui_html import artifacts, fixtures, partials
from benchweave_ui_html.grammar import Row, parse_contract
from benchweave_ui_html.manifest import MANIFEST

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "internal" / "ui-contract.md"


def _rows(slug: str) -> list[Row]:
    table = parse_contract(CONTRACT.read_text(encoding="utf-8"), MANIFEST).by_slug(slug)
    assert table is not None
    return list(table.body)


def test_e1_digital_lanes_row_satisfies() -> None:
    artifact = artifacts._component_factory("digital-lanes")
    row = next(r for r in _rows("e-1-components") if r.key == "digital-lanes")
    assert artifact.satisfies(row) == []


@pytest.mark.parametrize(
    "slug",
    [
        "e-4-1-lane-layout",
        "e-4-2-state-rendering",
        "e-4-3-groups-and-buses",
        "e-4-4-edge-preserving-decimation-normative",
        "e-4-5-time-axis",
        "e-4-6-decoder-lanes",
    ],
)
def test_lanes_rule_rows_satisfy(slug: str) -> None:
    for row in _rows(slug):
        assert artifacts._lanes_rule_factory(row.key).satisfies(row) == [], (slug, row.key)


def test_canonical_capture_carries_the_contract_literals() -> None:
    composed = fixtures.digital_lanes()
    assert composed.acquisition_text == "Acquired 1000 samples · plotted 12 at 1 MHz"
    assert composed.delta_t_text == "Δt = 7 µs"
    assert composed.trigger_sample == 500
    html = partials.render_lanes(composed)
    assert 'data-bw-trigger-sample="500"' in html
    assert "hidden" in html


def test_the_ten_behaviour_rows_are_registered_and_green() -> None:
    """The G1d discharge, asserted at the ship state: the ten behaviour
    rule_proof rows (§B.2 SR-B1..B3, §B.4 ST-1..4, §C.1 R-ENERGISE-1/
    R-DEENERGISE-1/R-PROTECT-1) register through the composition checkers
    and evaluate green against the real contract — and no table stays
    deferred (a satisfied-but-failed message there would be a
    cheap-satisfaction attempt, which the mutation arms in
    test_compositions_mutations.py kill)."""
    from benchweave_ui_html import registry

    registry.REGISTRY.clear()
    artifacts.ensure_registered()
    rows = {row.row_id: row for table in
            parse_contract(CONTRACT.read_text(encoding="utf-8"), MANIFEST).tables
            for row in table.body}
    behaviour_slugs = {"b-2-state-rules", "b-4-staleness", "c-1-safety-rules"}
    behaviour = {row_id for row_id in rows if row_id.split("::")[0] in behaviour_slugs}
    assert len(behaviour) == 10, sorted(behaviour)
    assert not artifacts.DEFERRED_SLUGS
    assert set(registry.REGISTRY) == set(rows)
    for row_id in behaviour:
        message = registry.evaluate_row(
            rows[row_id],
            registry.REGISTRY.get(row_id),
            require_artifact=True,
            expected_kind="rule_proof",
        )
        assert message is None, (row_id, message)
