"""G1b's in-process meta arms (design record §1.5), reconciled with G1a's
subprocess controls (O1): the auto-registration completeness set-equality,
the idempotence no-op, the fail-closed pure-function control (the empty-
registry control moved here from collection level once the plugin started
auto-registering), the ship-shape green/red split over the real contract,
and the one-artifact control (registering exactly one artifact greens
exactly its own row — ±0 others; a leak is a harness leak).

Every arm sets its own registry state first: they are order-independent and
safe to run in one process (the default suite never collects the contract,
so in-process registration reaches no other test).
"""

from __future__ import annotations

from pathlib import Path

from benchweave_ui_html import artifacts, registry
from benchweave_ui_html.grammar import Row, parse_contract
from benchweave_ui_html.manifest import KIND_BY_SLUG, MANIFEST

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "internal" / "ui-contract.md"


def _contract_rows() -> list[Row]:
    contract = parse_contract(CONTRACT.read_text(encoding="utf-8"), MANIFEST)
    return [row for table in contract.tables for row in table.body]


def _evaluate(row: Row, artifact: registry.Artifact | None) -> str | None:
    return registry.evaluate_row(
        row,
        artifact,
        require_artifact=registry.REQUIRE_ARTIFACT,
        expected_kind=KIND_BY_SLUG[row.table_slug],
    )


def test_registration_completeness_is_set_equality() -> None:
    """After ``ensure_registered()`` the registry holds exactly G1b's declared
    row-ids — no orphan, no gap (the expectation is the artifacts module's
    own declared scope; the manifest-derivation equality lands with the
    full 158)."""
    registry.REGISTRY.clear()
    artifacts.ensure_registered()
    assert set(registry.REGISTRY) == set(artifacts.G1B_ROW_IDS)


def test_ensure_registered_is_idempotent() -> None:
    """A second call is a no-op (duplicate registration would raise)."""
    registry.REGISTRY.clear()
    artifacts.ensure_registered()
    before = len(registry.REGISTRY)
    artifacts.ensure_registered()
    assert len(registry.REGISTRY) == before


def test_empty_registry_fail_closed_pure_function() -> None:
    """The empty-registry control, at the pure function G1a isolated for
    exactly this: with ``REGISTRY.clear()`` every row returns the canonical
    missing-artifact message."""
    registry.REGISTRY.clear()
    for row in _contract_rows():
        assert _evaluate(row, registry.REGISTRY.get(row.row_id)) == (
            f"no canonical artifact for {row.row_id}"
        )


def test_ship_state_green_red_split_over_the_real_contract() -> None:
    """Every G1b-registered row is green against the real contract; every
    other row reds with exactly the no-canonical-artifact message class (a
    red from ``unsatisfied contract items`` there would mean something
    registered-and-failed — a different defect)."""
    registry.REGISTRY.clear()
    artifacts.ensure_registered()
    rows = {row.row_id: row for row in _contract_rows()}
    assert set(rows)  # the contract parsed
    for row_id in artifacts.G1B_ROW_IDS:
        assert row_id in rows, f"registered row-id absent from the contract: {row_id}"
        assert _evaluate(rows[row_id], registry.REGISTRY.get(row_id)) is None, row_id
    for row_id, row in rows.items():
        if row_id in artifacts.G1B_ROW_IDS:
            continue
        message = _evaluate(row, registry.REGISTRY.get(row_id))
        assert message == f"no canonical artifact for {row_id}", (row_id, message)


def test_one_artifact_control_greens_exactly_its_own_row() -> None:
    """The fluff-killer: registering exactly the button artifact greens
    exactly ``e-1-components::button`` and no other row."""
    registry.REGISTRY.clear()
    registry.REGISTRY.register(artifacts.SENTINEL_ROW_ID, artifacts.button_artifact())
    green = [
        row.row_id
        for row in _contract_rows()
        if _evaluate(row, registry.REGISTRY.get(row.row_id)) is None
    ]
    assert green == [artifacts.SENTINEL_ROW_ID]


def test_mutation_control_a_reading_state_drop_reds_naming_the_item() -> None:
    """Mutation control (a), design record §6: drop ``data-bw-reading-state``
    from the fixture → the reading-tile rows red NAMING that item (an
    assertion that cannot name its item cannot discriminate)."""
    from benchweave_ui_html import fixtures, partials
    from benchweave_ui_html.data import ReadingData

    row_e1 = next(r for r in _contract_rows() if r.row_id == "e-1-components::reading-tile")
    row_b3 = next(r for r in _contract_rows() if r.row_id == "b-3-reading-states::limiting")

    dropped = ReadingData(
        label="Supply voltage",
        severity="neutral",
        value="12.5",
        unit="V",
        state=None,
        state_label=None,
        set_value="12.0",
        set_unit="V",
    )
    assert dropped != fixtures.reading()  # the mutation must bite
    rendered_without_state = partials.render_reading(dropped)

    from benchweave_ui_html.artifacts import ComponentRenderArtifact, StateRowArtifact

    e1_messages = ComponentRenderArtifact(
        "reading-tile", lambda: rendered_without_state
    ).satisfies(row_e1)
    assert any("data-bw-reading-state" in message for message in e1_messages), e1_messages

    # The B.3 artifact renders the canonical fixture internally; sabotage it
    # through the fixture itself (same mechanism the record names).
    original = fixtures.reading
    try:
        fixtures.reading = lambda: dropped
        b3_messages = StateRowArtifact("limiting").satisfies(row_b3)
    finally:
        fixtures.reading = original
    assert any("data-bw-reading-state" in message for message in b3_messages), b3_messages
