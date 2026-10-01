"""Fail-closed parser for the renderer-neutral contract (docs/internal/ui-contract.md).

Ported from the two TS gates this harness replaces at the G1 cutover:

- ``ui/src/contract-enforcement.test.ts`` ``contractTable`` — pipe rows are
  collected until the next heading line (the design record's grammar rule 2);
- ``ui/src/contract-coverage.test.ts`` ``parseTable`` — ``body = rows[2:]`` and
  a body row whose cell count differs from the header's is a parse failure,
  never a silently mis-parsed row.

The parser never raises on contract drift: every defect is captured as a
``PinDefect`` naming the table and a defect class, so drift can only present
as a red pin item, never as a pass or a skip.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

# Defect classes. The four the design record names (missing heading, missing
# table, wrong header cells, wrong stated row count) plus the ported L1
# arity check and the separator/stated-schema checks of grammar rules 3 and 5.
DEFECT_MISSING_HEADING = "missing heading"
DEFECT_MISSING_TABLE = "missing table"
DEFECT_WRONG_HEADER_CELLS = "wrong header cells"
DEFECT_MALFORMED_SEPARATOR = "malformed separator"
DEFECT_MISSING_SCHEMA_LINE = "missing Schema line"
DEFECT_WRONG_STATED_SCHEMA = "wrong stated schema"
DEFECT_WRONG_STATED_ROW_COUNT = "wrong stated row count"
DEFECT_WRONG_ENUMERATION_COUNT = "wrong enumeration count"
DEFECT_WRONG_ROW_CELL_COUNT = "wrong row cell count"

_SEPARATOR_CELL = re.compile(r"^:?-{1,}:?$")
_STATED_COUNT = re.compile(r"—\s*(\d+)\s+rows?\b")
_STATED_CELLS = re.compile(r"^Schema:\s*`([^`]*)`")


def literal(cell: str) -> str:
    """Strip one pair of surrounding backticks (the TS ``literal`` helper)."""
    if len(cell) >= 2 and cell.startswith("`") and cell.endswith("`"):
        return cell[1:-1]
    return cell


def slug_for_heading(heading: str) -> str:
    """The stable table slug: heading lowercased, section mark dropped, runs
    of non-alphanumerics collapsed to one dash (design record §2 — item ids
    carry the row-id so ``-k`` and junitxml greps stay stable)."""
    text = heading.strip().lstrip("#").strip().lower().replace("§", "")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


class TableSpec(Protocol):
    """What the parser needs from a manifest entry (structural, read-only —
    the manifest is frozen, and a settable-variable protocol would not match
    a frozen dataclass)."""

    @property
    def heading(self) -> str: ...

    @property
    def slug(self) -> str: ...

    @property
    def header_cells(self) -> tuple[str, ...]: ...

    @property
    def row_count(self) -> int: ...


@dataclass(frozen=True)
class PinDefect:
    """One fail-closed parse finding against one pinned table."""

    table_slug: str
    heading: str
    defect_class: str
    detail: str

    def message(self) -> str:
        return f"{self.defect_class} [{self.table_slug} ({self.heading})]: {self.detail}"


@dataclass(frozen=True)
class Row:
    """One parsed body row. ``key`` is the literal (backtick-stripped) first
    cell; ``row_id`` is ``<table-slug>::<key>`` — the registry's key space."""

    row_id: str
    table_slug: str
    cells: tuple[str, ...]

    @property
    def key(self) -> str:
        return literal(self.cells[0]) if self.cells else ""


@dataclass(frozen=True)
class ParsedTable:
    slug: str
    heading: str
    header: tuple[str, ...]
    body: tuple[Row, ...]
    stated_count: int | None
    stated_cells: tuple[str, ...] | None
    defects: tuple[PinDefect, ...] = field(default=())


@dataclass(frozen=True)
class Contract:
    """Parse results for every manifest table, in manifest order.

    A table that fails to parse is still present (with its defects and an
    empty/partial body) — the pin layer reports the defects; row items are
    generated for whatever body parsed.
    """

    tables: tuple[ParsedTable, ...]

    def by_slug(self, slug: str) -> ParsedTable | None:
        return next((table for table in self.tables if table.slug == slug), None)

    @property
    def row_count(self) -> int:
        return sum(len(table.body) for table in self.tables)


def _split_cells(line: str) -> list[str]:
    """Trim, strip one leading and one trailing pipe, split on pipes, trim
    cells — exactly the TS row-push shape."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _parse_schema_line(region: Sequence[str]) -> tuple[int | None, tuple[str, ...] | None]:
    """Extract (stated count, stated header cells) from the region's first
    ``Schema:`` line. Returns (None, None) when the region has none."""
    for line in region:
        stripped = line.strip()
        if not stripped.startswith("Schema:"):
            continue
        count_match = _STATED_COUNT.search(stripped)
        cells_match = _STATED_CELLS.match(stripped)
        stated_count = int(count_match.group(1)) if count_match else None
        stated_cells: tuple[str, ...] | None = None
        if cells_match:
            stated_cells = tuple(cell.strip() for cell in cells_match.group(1).split("|"))
        return stated_count, stated_cells
    return None, None


def _parse_table(lines: Sequence[str], spec: TableSpec) -> ParsedTable:
    heading_index = next(
        (i for i, line in enumerate(lines) if line.strip() == spec.heading), None
    )
    defects: list[PinDefect] = []

    def defect(defect_class: str, detail: str) -> PinDefect:
        return PinDefect(spec.slug, spec.heading, defect_class, detail)

    if heading_index is None:
        return ParsedTable(
            slug=spec.slug,
            heading=spec.heading,
            header=(),
            body=(),
            stated_count=None,
            stated_cells=None,
            defects=(defect(DEFECT_MISSING_HEADING, "the exact heading line is absent"),),
        )

    region: list[str] = []
    for line in lines[heading_index + 1 :]:
        if line.strip().startswith("#"):
            break
        region.append(line)

    stated_count, stated_cells = _parse_schema_line(region)
    if stated_count is None and stated_cells is None:
        defects.append(
            defect(DEFECT_MISSING_SCHEMA_LINE, "no `Schema: … — N rows` line under the heading")
        )

    rows = [_split_cells(line) for line in region if line.strip().startswith("|")]
    if len(rows) < 3:
        defects.append(
            defect(
                DEFECT_MISSING_TABLE,
                f"no parsable table under the heading (pipe rows={len(rows)}; "
                "a table needs header, separator and at least one body row)",
            )
        )
        return ParsedTable(
            slug=spec.slug,
            heading=spec.heading,
            header=tuple(rows[0]) if rows else (),
            body=(),
            stated_count=stated_count,
            stated_cells=stated_cells,
            defects=tuple(defects),
        )

    header = tuple(rows[0])
    body_rows = rows[2:]

    separator = rows[1]
    if not all(_SEPARATOR_CELL.match(cell or "") for cell in separator):
        defects.append(
            defect(
                DEFECT_MALFORMED_SEPARATOR,
                f"second pipe row is not a separator: {'|'.join(separator)!r}",
            )
        )

    if header != tuple(spec.header_cells):
        defects.append(
            defect(
                DEFECT_WRONG_HEADER_CELLS,
                f"expected {' | '.join(spec.header_cells)!r}, got {' | '.join(header)!r}",
            )
        )
    if stated_cells is not None and stated_cells != header:
        stated = " | ".join(stated_cells)
        actual = " | ".join(header)
        detail = f"Schema line states {stated!r}, header is {actual!r}"
        defects.append(defect(DEFECT_WRONG_STATED_SCHEMA, detail))

    for row in body_rows:
        if len(row) != len(header):
            key = literal(row[0]) if row else ""
            defects.append(
                defect(
                    DEFECT_WRONG_ROW_CELL_COUNT,
                    f"row {key!r} has {len(row)} cells, header has {len(header)}",
                )
            )

    if stated_count is not None and stated_count != len(body_rows):
        defects.append(
            defect(
                DEFECT_WRONG_STATED_ROW_COUNT,
                f"stated {stated_count} rows, body has {len(body_rows)}",
            )
        )
    if len(body_rows) != spec.row_count:
        defects.append(
            defect(
                DEFECT_WRONG_ENUMERATION_COUNT,
                f"manifest pins {spec.row_count} rows, body has {len(body_rows)}",
            )
        )

    body = tuple(
        Row(row_id=f"{spec.slug}::{literal(row[0])}", table_slug=spec.slug, cells=tuple(row))
        for row in body_rows
    )
    return ParsedTable(
        slug=spec.slug,
        heading=spec.heading,
        header=header,
        body=body,
        stated_count=stated_count,
        stated_cells=stated_cells,
        defects=tuple(defects),
    )


def parse_contract(text: str, specs: Sequence[TableSpec]) -> Contract:
    """Parse every manifest table's region of ``text``. Never raises on drift."""
    return Contract(tuple(_parse_table(text.split("\n"), spec) for spec in specs))
