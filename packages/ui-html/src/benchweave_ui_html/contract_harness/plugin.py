"""The pytest contract harness (pytest11 entry point, design record §2).

Collection is the parse: this collector claims files named ``ui-contract.md``
and emits two item families and no test file — a pin item per manifest table
(parse integrity) and a row item per parsed body row (implementation). Since
the G1e cutover the gate is LIVE in this repository's default pytest run
(``testpaths`` carries the contract beside ``tests/``, fail-closed by the
default-run pin in ``tests/ui_html/test_harness.py``); any file not named
``ui-contract.md`` is still ignored — in OTHER pytest environments sharing a
venv with this wheel the plugin claims nothing, so foreign suites are never
hijacked (UR-11's published-wheel posture).

The pytest11 entry point is inert unless pytest is the running process, so a
host that installs the wheel for rendering never pulls pytest (UR-11).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchweave_ui_html import artifacts, registry
from benchweave_ui_html.grammar import ParsedTable, Row, parse_contract
from benchweave_ui_html.manifest import KIND_BY_SLUG, MANIFEST

CONTRACT_FILENAME = "ui-contract.md"
CONTRACT_MARKER = "contract"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{CONTRACT_MARKER}: generated contract-gate item (pin or row layer)",
    )


def pytest_collect_file(file_path: Path, parent: pytest.Collector) -> pytest.File | None:
    if file_path.name == CONTRACT_FILENAME:
        return ContractFile.from_parent(parent, path=file_path)
    return None


class ContractFile(pytest.File):
    def collect(self) -> Iterator[pytest.Item]:
        text = Path(self.path).read_text(encoding="utf-8")
        contract = parse_contract(text, MANIFEST)
        # G1b — the canonical artifacts register AFTER the parse and BEFORE
        # the orphan check, so the check polices the registrations it is
        # about to consume (design record §1.1). Idempotent by sentinel: a
        # process that registered artifacts beforehand suppresses the
        # auto-registration instead of colliding with it.
        artifacts.ensure_registered()
        # F1 fold — orphan check: every registered key must be a row the
        # contract actually parses. Without this, delete-and-pad with a fully
        # populated registry runs green while the deleted row's artifact sits
        # orphaned; with it, the disagreement fails collection loudly.
        row_ids = {row.row_id for table in contract.tables for row in table.body}
        orphans = registry.REGISTRY.orphaned_artifacts(row_ids)
        if orphans:
            raise pytest.Collector.CollectError(
                f"orphaned artifact: {', '.join(orphans)} "
                "(registered for rows this contract does not parse)"
            )
        for table in contract.tables:
            # The pin layer: one item per pinned table, red on any defect.
            yield PinItem.from_parent(self, name=f"pin::{table.slug}", table=table)
            # The row layer: one item per parsed body row — the artifact
            # requirement, fail-closed on the empty registry.
            for row in table.body:
                yield RowItem.from_parent(self, name=f"row::{row.row_id}", row=row)


class PinItem(pytest.Item):
    def __init__(self, *, table: ParsedTable, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._table = table
        self.add_marker(CONTRACT_MARKER)

    def runtest(self) -> None:
        if self._table.defects:
            joined = "; ".join(defect.message() for defect in self._table.defects)
            pytest.fail(joined, pytrace=False)

    def reportinfo(self) -> tuple[str | Path, int, str]:
        return self.path, 0, self.name


class RowItem(pytest.Item):
    def __init__(self, *, row: Row, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._row = row
        self.add_marker(CONTRACT_MARKER)

    def runtest(self) -> None:
        # REQUIRE_ARTIFACT is read from the module at call time — the module
        # constant is the only switch, and an in-process flip (the
        # mechanism-toggle control) must take effect.
        failure = registry.evaluate_row(
            self._row,
            registry.REGISTRY.get(self._row.row_id),
            require_artifact=registry.REQUIRE_ARTIFACT,
            expected_kind=KIND_BY_SLUG[self._row.table_slug],
        )
        if failure is not None:
            pytest.fail(failure, pytrace=False)

    def reportinfo(self) -> tuple[str | Path, int, str]:
        return self.path, 0, self.name
