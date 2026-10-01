"""Manifest unit tests: the corrected 28-table / 168-row enumeration."""

from __future__ import annotations

from pathlib import Path

from benchweave_ui_html.grammar import parse_contract
from benchweave_ui_html.manifest import KIND_BY_SLUG, MANIFEST, TOTAL_ROWS, TOTAL_TABLES
from benchweave_ui_html.registry import KNOWN_KINDS

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_TEXT = (REPO_ROOT / "docs" / "internal" / "ui-contract.md").read_text(encoding="utf-8")

# The three build-time-corrected entries (design record §5, Build-time
# correction): §E.4.2 is the +1; §E.2.4/§E.2.5 were a net-zero swap.
CORRECTED_ENTRIES = {
    "e-4-2-state-rendering": 4,
    "e-2-4-reference-lines": 4,
    "e-2-5-acquisition-disclosure": 3,
}


def test_totals() -> None:
    assert TOTAL_TABLES == 28
    assert TOTAL_ROWS == 168


def test_slugs_and_headings_unique() -> None:
    slugs = [table.slug for table in MANIFEST]
    headings = [table.heading for table in MANIFEST]
    assert len(set(slugs)) == 28
    assert len(set(headings)) == 28


def test_every_kind_is_known_and_maps_round_trip() -> None:
    assert set(KIND_BY_SLUG) == {table.slug for table in MANIFEST}
    for table in MANIFEST:
        assert table.kind in KNOWN_KINDS, table.slug


def test_corrected_entries_carry_the_measured_counts() -> None:
    by_slug = {table.slug: table for table in MANIFEST}
    for slug, count in CORRECTED_ENTRIES.items():
        assert by_slug[slug].row_count == count, slug


def test_manifest_agrees_with_the_real_contract_parse() -> None:
    """The independent second count, checked against the contract itself."""
    contract = parse_contract(CONTRACT_TEXT, MANIFEST)
    for table, entry in zip(contract.tables, MANIFEST, strict=True):
        assert len(table.body) == entry.row_count, entry.slug
        assert table.header == entry.header_cells, entry.slug
        assert table.stated_count == entry.row_count, entry.slug


def test_manifest_carries_the_168_ordered_identity_keys() -> None:
    """F1 fold: every entry pins its exact ordered key list — the identity
    pin, same coupling as the TS fold-P5 key arrays."""
    total = sum(len(table.keys) for table in MANIFEST)
    assert total == 168
    for table in MANIFEST:
        assert len(table.keys) == table.row_count, table.slug
        assert len(set(table.keys)) == table.row_count, table.slug


def test_manifest_keys_equal_the_parsed_key_cells() -> None:
    contract = parse_contract(CONTRACT_TEXT, MANIFEST)
    for table, entry in zip(contract.tables, MANIFEST, strict=True):
        assert tuple(row.key for row in table.body) == entry.keys, entry.slug
