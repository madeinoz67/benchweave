"""Unit tests for the §E item micro-syntax parser (G1b design record §1.1).

The parser is new load-bearing surface (grammar.py owns cells, not items):
the Authoring rule's separator, the three attribute-item forms, the
backtick-wrapping the §E.1 cells carry, the em-dash empty marker, and the
loud refusal for ``name=value`` values containing a quote or a backslash.
"""

from __future__ import annotations

import pytest
from benchweave_ui_html.items import (
    ItemSyntaxError,
    parse_attribute_cell,
    parse_attribute_item,
    split_items,
)


def test_split_items_strips_wrapping_backticks_and_splits() -> None:
    assert split_items("`data-variant ~ aria-busy`") == ["data-variant", "aria-busy"]


def test_split_items_em_dash_and_empty_yield_nothing() -> None:
    assert split_items("—") == []
    assert split_items("") == []
    assert split_items("`—`") == []


def test_split_items_keeps_unspaced_operators_inside_one_item() -> None:
    # The separator is space-bounded, so ~= survives inside a single item.
    items = split_items("`aria-valuetext~=staged ~ aria-label`")
    assert items == ["aria-valuetext~=staged", "aria-label"]


def test_split_items_over_plain_unwrapped_cells() -> None:
    # §C.3/§D.1-style cells that never carry backticks.
    assert split_items("SIMULATED PRESENTATION DATA") == ["SIMULATED PRESENTATION DATA"]


@pytest.mark.parametrize(
    ("item", "name", "match", "value"),
    [
        ("data-variant", "data-variant", "present", None),
        ("type=number", "type", "equals", "number"),
        ("aria-label=Traces", "aria-label", "equals", "Traces"),
        ("aria-label~=(hidden by presentation preference)", "aria-label", "contains",
         "(hidden by presentation preference)"),
        ("aria-valuetext~=staged", "aria-valuetext", "contains", "staged"),
    ],
)
def test_parse_attribute_item_forms(
    item: str, name: str, match: str, value: str | None
) -> None:
    parsed = parse_attribute_item(item)
    assert parsed.name == name
    assert parsed.match == match
    assert parsed.value == value


@pytest.mark.parametrize("value", ['name="x"', "name='x'", "name=a\\b"])
def test_equals_value_with_quote_or_backslash_fails_loud(value: str) -> None:
    """The Authoring rule excludes quotes and backslashes from ``name=value``
    values — accepting one would silently mis-issue the selector upstream."""
    with pytest.raises(ItemSyntaxError, match="must not contain"):
        parse_attribute_item(value)


def test_malformed_items_fail_loud() -> None:
    with pytest.raises(ItemSyntaxError):
        parse_attribute_item("~=value")
    with pytest.raises(ItemSyntaxError):
        parse_attribute_item("")


def test_parse_attribute_cell_round_trips_the_e1_button_cell() -> None:
    items = parse_attribute_cell("`data-variant ~ aria-busy`")
    assert [item.describe() for item in items] == ["data-variant", "aria-busy"]


def test_describe_round_trips_each_form() -> None:
    assert parse_attribute_item("a=b").describe() == "a=b"
    assert parse_attribute_item("a~=b").describe() == "a~=b"
    assert parse_attribute_item("a").describe() == "a"
