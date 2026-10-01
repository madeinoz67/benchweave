"""The §E cell micro-syntax parser (the contract's Authoring rule).

The Authoring rule (docs/internal/ui-contract.md:22-34) is normative on the
§E item cells: items within an attribute, role, class-hook or required-text
cell are separated by `` ~ ``; an attribute item is ``name`` (present),
``name=value`` (exact) or ``name~=substring`` (contains); a ``name=value``
value must not contain a quote or a backslash. G1a's ``grammar.py`` owns
cells, not items — this module is the new load-bearing item surface (G1b
design record §2): a parser that silently mis-issued such a selector would
be a silent pass upstream, so the excluded-value class fails loud here
instead.

Cells arrive as parsed (possibly backtick-wrapped); ``grammar.literal``
strips one leading and one trailing backtick independently, exactly as it
does for row keys, before the split.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from benchweave_ui_html.grammar import literal

#: The item separator (space-tilde-space), so ``~=`` inside one item survives.
ITEM_SEPARATOR = " ~ "

#: The empty-cell marker the §E.1 tables use for "no items".
EMPTY_CELL = "—"


class ItemSyntaxError(ValueError):
    """An item the Authoring rule excludes — never a silently-parsed item."""


@dataclass(frozen=True)
class AttributeItem:
    """One attribute item: presence, exact-value, or substring containment."""

    name: str
    match: Literal["present", "equals", "contains"]
    value: str | None = None

    def describe(self) -> str:
        """The item rendered back as its cell syntax (failure messages)."""
        if self.match == "equals":
            return f"{self.name}={self.value}"
        if self.match == "contains":
            return f"{self.name}~={self.value}"
        return self.name


def split_items(cell: str) -> list[str]:
    """Split an item cell (attribute/role/class-hook/required-text) on
    `` ~ ``. A ``—`` or empty cell yields no items; the cell's wrapping
    backticks are stripped first (one leading and one trailing, the
    ``grammar.literal`` semantics)."""
    text = literal(cell.strip())
    if not text or text == EMPTY_CELL:
        return []
    return [part.strip() for part in text.split(ITEM_SEPARATOR) if part.strip()]


def parse_attribute_item(item: str) -> AttributeItem:
    """Parse one attribute item per the Authoring rule.

    ``~=`` is tested before ``=`` (a contains-item also contains an ``=``).
    A ``name=value`` value carrying a quote or a backslash raises
    ``ItemSyntaxError`` — the Authoring rule excludes those characters, and a
    parser that accepted one would mis-issue the selector downstream.
    """
    if "~=" in item:
        name, value = item.split("~=", 1)
        name, value = name.strip(), value.strip()
        if not name or not value:
            raise ItemSyntaxError(f"malformed contains-item: {item!r}")
        return AttributeItem(name, "contains", value)
    if "=" in item:
        name, value = item.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name:
            raise ItemSyntaxError(f"malformed equals-item: {item!r}")
        if any(ch in value for ch in ("'", '"', "\\")):
            raise ItemSyntaxError(
                f"attribute item {item!r}: a name=value value must not contain "
                "a quote or a backslash (Authoring rule, ui-contract.md:29)"
            )
        return AttributeItem(name, "equals", value)
    if not item.strip():
        raise ItemSyntaxError("empty attribute item")
    return AttributeItem(item.strip(), "present")


def parse_attribute_cell(cell: str) -> list[AttributeItem]:
    """Parse a whole attribute cell into its items."""
    return [parse_attribute_item(item) for item in split_items(cell)]
