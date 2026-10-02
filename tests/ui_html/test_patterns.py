"""The pattern library's census and export guards (G1d design record §1.3/
§3 slice 3): the census derives its expectation from the manifest keys,
never a hand count; the export reds loudly when the styles are absent; the
tree is 12 pages × 2 themes with every page root carrying
``data-bw-pattern-library``; and the generated tree is NEVER committed (the
repo-side guard refuses a ``patterns/`` dir at the tracked root).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from benchweave_ui_html import artifacts, patterns
from benchweave_ui_html.assertions import RenderedComponent
from benchweave_ui_html.grammar import literal, parse_contract
from benchweave_ui_html.manifest import MANIFEST

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "internal" / "ui-contract.md"


def _manifest_keys(slug: str) -> tuple[str, ...]:
    return next(table.keys for table in MANIFEST if table.slug == slug)


# --- the census: manifest-derived, never a hand count -------------------------


@pytest.mark.parametrize(
    "slug",
    [
        "c-3-refusal-mapping",
        "c-2-disabled-reason-enum",
        "b-1-severities",
        "d-1-modes",
        "b-3-reading-states",
    ],
)
def test_every_enumerated_key_is_a_fixture_row(slug: str) -> None:
    """The manifest-derived minimum coverage: every §C.3 code, §C.2 reason,
    §B.1 severity, §D.1 mode and §B.3 state is present as an entry's
    row_id."""
    row_ids = {entry.row_id for entry in patterns.PATTERNS}
    for key in _manifest_keys(slug):
        assert f"{slug}::{key}" in row_ids, (slug, key)


def test_one_page_per_component_plus_the_refusal_page() -> None:
    pages = patterns.pages()
    assert pages == _manifest_keys("e-1-components") + ("refusals",)
    assert len(pages) == 12


def test_every_page_has_entries_and_every_entry_names_a_page() -> None:
    for page in patterns.pages():
        assert patterns.entries_for_page(page), page
    valid = set(patterns.pages())
    for entry in patterns.PATTERNS:
        assert entry.page in valid, entry


def test_fixture_ids_are_unique_the_screenshot_keys() -> None:
    """Screenshots are keyed by contract row + fixture — the fixture id must
    be unique within its row (the pair is the filename)."""
    seen: set[tuple[str, str]] = set()
    for entry in patterns.PATTERNS:
        pair = (entry.row_id, entry.fixture_id)
        assert pair not in seen, pair
        seen.add(pair)


def test_the_row_checkers_fixture_population_is_the_librarys() -> None:
    """One registry: the §E.1 canonical entries' row_ids are exactly the
    §E.1 manifest keys, and the composition entries' row_ids name the §C.1
    behaviour rows the checkers drive (the same fixtures, no second
    mirror)."""
    component_rows = {
        entry.row_id for entry in patterns.PATTERNS if entry.kind == "component"
    }
    assert component_rows == {
        f"e-1-components::{key}" for key in _manifest_keys("e-1-components")
    }
    composition_rows = {
        entry.row_id for entry in patterns.PATTERNS if entry.kind == "composition"
    }
    assert composition_rows <= {
        "c-1-safety-rules::R-ENERGISE-1",
        "c-1-safety-rules::R-PROTECT-1",
    }


# --- the export ----------------------------------------------------------------


def test_export_writes_twelve_pages_both_themes_and_the_index(
    tmp_path: Path,
) -> None:
    result = patterns.export(tmp_path)
    assert len(result.pages) == 24, result.pages
    assert set(result.themes) == {"light", "dark"}
    assert result.index == "patterns/index.html"
    for theme in ("light", "dark"):
        for page in patterns.pages():
            path = tmp_path / "patterns" / theme / f"{page}.html"
            assert path.is_file(), path
            html = path.read_text(encoding="utf-8")
            # Every page root carries the library attribute, the theme root
            # attribute, and the REAL token CSS inlined (one mirror).
            assert "data-bw-pattern-library" in html
            assert f'data-theme="{theme}"' in html
            assert "--bw-canvas" in html, "the real tokens.css must be inlined"
            assert "--bw-series-1" in html, "the real themes.css must be inlined"


def test_exported_pages_carry_every_entry_of_their_page(tmp_path: Path) -> None:
    patterns.export(tmp_path)
    page = tmp_path / "patterns" / "light" / "refusals.html"
    html = page.read_text(encoding="utf-8")
    for entry in patterns.entries_for_page("refusals"):
        assert f'data-bw-pattern-fixture="{entry.fixture_id}"' in html, entry
        assert entry.render() in html, entry


def test_export_reds_loudly_when_the_styles_are_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The token rows' own fail-loud shape: a missing CSS asset refuses the
    export loudly (the G1e CSS re-point rides drift-and-obligations)."""
    monkeypatch.setattr(
        artifacts, "TOKENS_CSS", tmp_path / "nowhere" / "tokens.css"
    )
    with pytest.raises(patterns.PatternExportRefused, match="styles are absent"):
        patterns.export(tmp_path)


def test_the_library_pages_derive_from_the_contract_cells(tmp_path: Path) -> None:
    """Row-as-data: the refusal page carries the contract's own
    what-happened cells and the button page the §C.2 label cells — the
    library cannot drift from the contract without the gate's rows reding
    first."""
    contract = parse_contract(CONTRACT.read_text(encoding="utf-8"), MANIFEST)
    rows = {row.row_id: row for table in contract.tables for row in table.body}
    patterns.export(tmp_path)
    html = (tmp_path / "patterns" / "light" / "refusals.html").read_text(
        encoding="utf-8"
    )
    rendered = RenderedComponent(html)
    for row in (
        rows[f"c-3-refusal-mapping::{key}"]
        for key in _manifest_keys("c-3-refusal-mapping")
    ):
        assert literal(row.cells[2]) in rendered.text_content, row.row_id
    button_html = (tmp_path / "patterns" / "light" / "button.html").read_text(
        encoding="utf-8"
    )
    assert "No lease or policy authority" in button_html
    assert "Protection trip active" in button_html


def test_no_patterns_directory_is_committed_at_the_tracked_root() -> None:
    """UR-13's repo-side guard: the generated tree is never committed — a
    tracked ``patterns/`` dir at the repository root refuses (the Pages
    publish stages the export at build time, not from the tree)."""
    proc = subprocess.run(
        ["git", "ls-files", "--", "patterns"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert not proc.stdout.strip(), (
        "patterns/ must never be tracked at the repository root — the export "
        "stages into the docs site at build time (UR-13): " + proc.stdout
    )
    assert not (REPO_ROOT / "patterns").exists(), (
        "an untracked patterns/ root dir invites accidental commits; export "
        "into the site tree or a scratch dir instead"
    )
