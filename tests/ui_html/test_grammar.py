"""Grammar unit tests: the fail-closed port of the TS parsers.

RED-first: this module was written before the package existed and watched
fail with ModuleNotFoundError; the defect-class cases below are synthetic
mini-contracts so each fail-closed class is pinned in isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from benchweave_ui_html.grammar import (
    DEFECT_MALFORMED_SEPARATOR,
    DEFECT_MISSING_HEADING,
    DEFECT_MISSING_SCHEMA_LINE,
    DEFECT_MISSING_TABLE,
    DEFECT_TABLE_INTERRUPTED,
    DEFECT_WRONG_ENUMERATION_COUNT,
    DEFECT_WRONG_HEADER_CELLS,
    DEFECT_WRONG_ROW_CELL_COUNT,
    DEFECT_WRONG_ROW_KEYS,
    DEFECT_WRONG_STATED_ROW_COUNT,
    DEFECT_WRONG_STATED_SCHEMA,
    literal,
    parse_contract,
    slug_for_heading,
)
from benchweave_ui_html.manifest import MANIFEST, ManifestTable

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_TEXT = (REPO_ROOT / "docs" / "internal" / "ui-contract.md").read_text(encoding="utf-8")

MINI_HEADING = "### §X.1 Mini"
MINI_SPEC = ManifestTable(
    MINI_HEADING, ("Key", "Value"), 2, "rule_proof", ("a", "b")
)


def mini_contract(
    *,
    heading: str = MINI_HEADING,
    schema: str = "Schema: `Key | Value` — 2 rows. Note.",
    header: str = "| Key | Value |",
    separator: str = "| --- | --- |",
    body: tuple[str, ...] = ("| `a` | 1 |", "| `b` | 2 |"),
) -> str:
    lines = ["# Title", "", heading, "", schema, "", header, separator, *body, "", "## After", ""]
    return "\n".join(lines)


@pytest.mark.parametrize(
    ("heading", "slug"),
    [
        ("### §A.1 Colour palette", "a-1-colour-palette"),
        ("#### §E.2.1 Slot mapping", "e-2-1-slot-mapping"),
        (
            "#### §E.4.4 Edge-preserving decimation (NORMATIVE)",
            "e-4-4-edge-preserving-decimation-normative",
        ),
        ("### §F.1 Icons", "f-1-icons"),
        (
            "### §E.3 Setpoint presentation (reading-tile sub-rows)",
            "e-3-setpoint-presentation-reading-tile-sub-rows",
        ),
    ],
)
def test_slug_for_heading(heading: str, slug: str) -> None:
    assert slug_for_heading(heading) == slug


def test_literal_strips_one_backtick_pair() -> None:
    assert literal("`--bw-canvas`") == "--bw-canvas"
    assert literal("plain") == "plain"
    assert literal("`nested ` inner`") == "nested ` inner"


def test_pristine_real_contract_parses_with_zero_defects() -> None:
    contract = parse_contract(CONTRACT_TEXT, MANIFEST)
    assert len(contract.tables) == 28
    assert contract.row_count == 168
    for table in contract.tables:
        assert table.defects == (), (table.slug, table.defects)
        assert table.stated_count == len(table.body)
        assert table.header == next(m.header_cells for m in MANIFEST if m.slug == table.slug)
    button = contract.by_slug("e-1-components")
    assert button is not None
    assert "e-1-components::button" in {row.row_id for row in button.body}


def test_row_ids_are_unique_across_the_contract() -> None:
    contract = parse_contract(CONTRACT_TEXT, MANIFEST)
    ids = [row.row_id for table in contract.tables for row in table.body]
    assert len(ids) == 168
    assert len(set(ids)) == 168


def test_pristine_mini_contract_has_no_defects() -> None:
    contract = parse_contract(mini_contract(), (MINI_SPEC,))
    table = contract.tables[0]
    assert table.defects == ()
    assert [row.row_id for row in table.body] == ["x-1-mini::a", "x-1-mini::b"]


def test_missing_heading() -> None:
    text = mini_contract().replace(f"{MINI_HEADING}\n", "", 1)
    table = parse_contract(text, (MINI_SPEC,)).tables[0]
    assert [d.defect_class for d in table.defects] == [DEFECT_MISSING_HEADING]
    assert table.body == ()
    assert MINI_SPEC.slug in table.defects[0].message()
    assert MINI_HEADING in table.defects[0].message()


def test_missing_table() -> None:
    text = mini_contract(schema="", header="", separator="", body=())
    table = parse_contract(text, (MINI_SPEC,)).tables[0]
    classes = [d.defect_class for d in table.defects]
    assert DEFECT_MISSING_TABLE in classes
    assert table.body == ()


def test_wrong_header_cells_and_stated_schema() -> None:
    text = mini_contract(header="| Keys | Value |")
    table = parse_contract(text, (MINI_SPEC,)).tables[0]
    classes = [d.defect_class for d in table.defects]
    assert DEFECT_WRONG_HEADER_CELLS in classes
    assert DEFECT_WRONG_STATED_SCHEMA in classes
    # The header-cell defect names both sides (design record grammar rule 4).
    wrong = [d for d in table.defects if d.defect_class == DEFECT_WRONG_HEADER_CELLS][0]
    assert "Key | Value" in wrong.message() and "Keys | Value" in wrong.message()


def test_malformed_separator() -> None:
    text = mini_contract(separator="| --- | oops |")
    table = parse_contract(text, (MINI_SPEC,)).tables[0]
    assert DEFECT_MALFORMED_SEPARATOR in [d.defect_class for d in table.defects]


def test_missing_schema_line() -> None:
    text = mini_contract(schema="Just a note.")
    table = parse_contract(text, (MINI_SPEC,)).tables[0]
    assert DEFECT_MISSING_SCHEMA_LINE in [d.defect_class for d in table.defects]
    assert table.stated_count is None


def test_wrong_stated_row_count_isolated() -> None:
    text = mini_contract(schema="Schema: `Key | Value` — 3 rows.")
    table = parse_contract(text, (MINI_SPEC,)).tables[0]
    classes = [d.defect_class for d in table.defects]
    assert classes == [DEFECT_WRONG_STATED_ROW_COUNT]
    assert "stated 3" in table.defects[0].detail and "body has 2" in table.defects[0].detail


def test_wrong_enumeration_count_is_the_independent_second_count() -> None:
    spec = ManifestTable(MINI_HEADING, ("Key", "Value"), 3, "rule_proof", ("a", "b"))
    table = parse_contract(mini_contract(), (spec,)).tables[0]
    # Stated (2) == body (2); only the committed manifest disagrees.
    assert [d.defect_class for d in table.defects] == [DEFECT_WRONG_ENUMERATION_COUNT]


def test_wrong_row_cell_count() -> None:
    text = mini_contract(body=("| `a` | 1 | extra |", "| `b` | 2 |"))
    table = parse_contract(text, (MINI_SPEC,)).tables[0]
    classes = [d.defect_class for d in table.defects]
    assert DEFECT_WRONG_ROW_CELL_COUNT in classes
    assert DEFECT_WRONG_STATED_ROW_COUNT not in classes  # 2 rows either way
    detail = next(d.detail for d in table.defects if d.defect_class == DEFECT_WRONG_ROW_CELL_COUNT)
    assert "3 cells" in detail and "header has 2" in detail


def test_wrong_row_keys_is_the_identity_pin() -> None:
    """Same count, same header, different keys: only the identity defect fires
    (the F1 fold — delete-and-pad and cross-table swaps keep counts green)."""
    text = mini_contract(body=("| `a` | 1 |", "| `a` | 2 |"))
    table = parse_contract(text, (MINI_SPEC,)).tables[0]
    assert [d.defect_class for d in table.defects] == [DEFECT_WRONG_ROW_KEYS]
    detail = table.defects[0].detail
    assert "index 1" in detail and "'b'" in detail and "got 'a'" in detail


def test_table_interrupted_by_a_non_pipe_line() -> None:
    """TS parseTable stops at the first non-pipe line; a mid-table interleave
    truncates the body AND is its own defect class (F1(b) — the L2 semantics
    skipped non-pipe lines and passed the corruption green)."""
    lines = mini_contract().split("\n")
    lines.insert(lines.index("| `a` | 1 |") + 1, "interleaved prose")
    table = parse_contract("\n".join(lines), (MINI_SPEC,)).tables[0]
    classes = [d.defect_class for d in table.defects]
    assert DEFECT_TABLE_INTERRUPTED in classes
    assert [row.key for row in table.body] == ["a"]  # truncated at the gap
    # The truncation also reds the count and identity pins.
    assert DEFECT_WRONG_STATED_ROW_COUNT in classes
    assert DEFECT_WRONG_ROW_KEYS in classes
