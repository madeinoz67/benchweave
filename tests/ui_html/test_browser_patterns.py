"""The browser lane (G1d design record §1.4; UR-09/Q6 — G1a deferral D2
landing): one Playwright run over the file:// pattern library — axe at
WCAG 2.2 AA on every page × both themes, one screenshot per PATTERNS entry
per theme, the export census, and the RoleResolver DISAGREEMENT CHECK (G1a
risk 4: the roles the §E.1 Required-roles cells name, queried through the
browser's real accessibility tree and compared against
``roles.ImplicitRoleResolver``'s verdicts — any disagreement reds).

The PLANTED-VIOLATION control runs in the same lane: a button stripped of
its accessible name MUST produce an axe violation — proving the axe
configuration actually detects in this file:// setup (a clean run against
the planted page means the measurement is broken, not the library).

Serialized lane (``browser`` marker): CI runs it on its own job with
chromium installed; the gates/timing lanes exclude the marker.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from pathlib import Path

import pytest
from benchweave_ui_html import patterns
from benchweave_ui_html.grammar import parse_contract
from benchweave_ui_html.items import split_items
from benchweave_ui_html.manifest import MANIFEST
from benchweave_ui_html.roles import ImplicitRoleResolver
from playwright.sync_api import Browser, Page, sync_playwright

pytestmark = pytest.mark.browser

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "internal" / "ui-contract.md"

#: axe's WCAG 2.2 AA rule set: levels A + AA of 2.0 and 2.2 (2.1's A/AA are
#: a subset of 2.2's at the tag level axe exposes; the tags name the
#: standard explicitly).
WCAG_22_AA_TAGS = ["wcag2a", "wcag2aa", "wcag22a", "wcag22aa"]


@pytest.fixture(scope="module")
def export_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The lane's output root: the export written once, screenshots added by
    the screenshot arm into the same tree."""
    root = tmp_path_factory.mktemp("pattern-browser")
    patterns.export(root)
    return root


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser: Browser) -> Generator[Page]:
    context = browser.new_context(viewport=patterns.VIEWPORT)
    yield context.new_page()
    context.close()


# --- the export census (the run's output root) --------------------------------


def test_export_census_in_the_runs_output_root(export_root: Path) -> None:
    """24 pages (12 × 2 themes) + the index; every page root carries
    data-bw-pattern-library; the manifest-derived minimum coverage holds as
    fixture ids on the pages."""
    for theme in ("light", "dark"):
        for page_slug in patterns.pages():
            path = export_root / "patterns" / theme / f"{page_slug}.html"
            assert path.is_file(), path
            html = path.read_text(encoding="utf-8")
            assert "data-bw-pattern-library" in html
    assert (export_root / "patterns" / "index.html").is_file()
    # The manifest-derived minimum coverage: every §C.3 code, §C.2 reason,
    # §B.1 severity, §D.1 mode and §B.3 state present as a fixture id.
    rendered_ids: set[str] = set()
    for theme in ("light", "dark"):
        for page_slug in patterns.pages():
            html = (export_root / "patterns" / theme / f"{page_slug}.html").read_text(
                encoding="utf-8"
            )
            rendered_ids.update(
                line.split('"')[0]
                for line in html.split('data-bw-pattern-row="')[1:]
            )
    for slug in (
        "c-3-refusal-mapping",
        "c-2-disabled-reason-enum",
        "b-1-severities",
        "d-1-modes",
        "b-3-reading-states",
    ):
        keys = next(table.keys for table in MANIFEST if table.slug == slug)
        for key in keys:
            assert f"{slug}::{key}" in rendered_ids, (slug, key)


# --- axe at WCAG 2.2 AA, every page, both themes -------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("page_slug", list(patterns.pages()))
def test_axe_wcag22aa_zero_violations(
    page: Page, export_root: Path, page_slug: str, theme: str
) -> None:
    target = export_root / "patterns" / theme / f"{page_slug}.html"
    page.goto(target.as_uri())
    from axe_playwright_python.sync_playwright import Axe  # type: ignore[import-untyped]

    results = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": WCAG_22_AA_TAGS},
            "resultTypes": ["violations"],
        },
    )
    assert results.violations_count == 0, results.generate_snapshot()


def test_axe_covers_the_index_too(page: Page, export_root: Path) -> None:
    """Fold F6: the library index joins the axe pass (it was the one
    unchecked page in the original 24-render claim)."""
    target = export_root / "patterns" / "index.html"
    page.goto(target.as_uri())
    from axe_playwright_python.sync_playwright import Axe

    results = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": WCAG_22_AA_TAGS},
            "resultTypes": ["violations"],
        },
    )
    assert results.violations_count == 0, results.generate_snapshot()


def test_planted_violation_must_red(page: Page) -> None:
    """The axe RED control: a button stripped of its accessible name on a
    scratch page MUST produce a violation — proving the measurement detects
    in this file:// setup (a clean run here means axe measured nothing)."""
    page.set_content(
        '<!doctype html><html><head><meta charset="utf-8"></head>'
        "<body><button></button><a href=\"#target\"></a></body></html>"
    )
    from axe_playwright_python.sync_playwright import Axe

    results = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": WCAG_22_AA_TAGS},
            "resultTypes": ["violations"],
        },
    )
    violation_ids = {violation["id"] for violation in results.response["violations"]}
    # Fold F6: two detector classes pinned — button-name AND link-name (the
    # empty anchor) — so the multi-detector claim is not one rule's word.
    assert "button-name" in violation_ids, violation_ids
    assert "link-name" in violation_ids, violation_ids
    assert results.violations_count > 0


# --- screenshots (UR-13): one per PATTERNS entry per theme ---------------------


def test_screenshot_count_is_patterns_times_themes(
    browser: Browser, tmp_path: Path
) -> None:
    """One screenshot per PATTERNS entry per theme, keyed by contract row +
    fixture (guide links survive re-export); each entry on its own fresh
    settled page (fold F1's determinism — the armed scene flapped 1px under
    page reuse)."""
    written = patterns.capture_screenshots(tmp_path, browser=browser)
    assert written == len(patterns.PATTERNS) * len(patterns.THEMES)
    for theme in patterns.THEMES:
        shots = sorted(
            path.name
            for path in (tmp_path / "patterns" / "screenshots" / theme).glob("*.png")
        )
        assert len(shots) == len(patterns.PATTERNS)
        expected = {
            f"{entry.row_id.replace('::', '__')}__{entry.fixture_id}.png"
            for entry in patterns.PATTERNS
        }
        assert set(shots) == expected, sorted(set(shots) ^ expected)[:5]


def test_the_two_themes_pixel_differ_in_every_screenshot(
    browser: Browser, tmp_path: Path
) -> None:
    """Fold F1's control: every entry's light and dark PNGs must differ in
    bytes — a themed render that renders identically in both themes means
    the theme tokens are not APPLIED (lane B's refuter proved the
    token-CSS-only pages did not differ until globals.css was inlined)."""
    patterns.capture_screenshots(tmp_path, browser=browser)
    same = []
    for entry in patterns.PATTERNS:
        name = f"{entry.row_id.replace('::', '__')}__{entry.fixture_id}.png"
        light = (tmp_path / "patterns" / "screenshots" / "light" / name).read_bytes()
        dark = (tmp_path / "patterns" / "screenshots" / "dark" / name).read_bytes()
        if light == dark:
            same.append(name)
    assert not same, f"{len(same)} entries render identically in both themes: {same[:3]}"


# --- the RoleResolver disagreement check (G1a risk 4) --------------------------


def test_the_target_size_minimum_is_carried_by_the_inlined_css(
    page: Page, export_root: Path
) -> None:
    """Fold F2's machine check, in the shape that survived contact with F1:
    the export's 24px target-size minimum is carried by a LAYERED pair of
    the page's own inlined CSS — globals.css's ``button { font: inherit }`
    at the 16px root (buttons land at 24px) and the page-chrome
    ``min-height`` rule as the second layer. Stripping ONE layer stays
    clean (the other carries it); stripping BOTH reds target-size — the
    minimum is a mechanism, not luck. (Pre-fold, with the token CSS alone
    and no globals.css, the chrome rule was the ONLY layer — lane B's
    original measurement.)"""
    from axe_playwright_python.sync_playwright import Axe

    def violations_of(path: Path) -> set[str]:
        page.goto(path.as_uri())
        results = Axe().run(
            page,
            options={
                "runOnly": {"type": "tag", "values": WCAG_22_AA_TAGS},
                "resultTypes": ["violations"],
            },
        )
        return {violation["id"] for violation in results.response["violations"]}

    source = export_root / "patterns" / "light" / "confirm-action.html"
    html = source.read_text(encoding="utf-8")
    chrome_rule = (
        ".bw-pattern button, .bw-pattern input, .bw-pattern [role=slider] { min-height: 24px; }"
    )
    font_inherit = "button,\ninput,\nselect,\ntextarea {\n  font: inherit;\n}"
    assert chrome_rule in html, "the chrome rule must be present to strip"
    assert font_inherit in html, "globals' font: inherit must be present to strip"

    chrome_stripped = export_root / "patterns" / "light" / "-f2-chrome.html"
    chrome_stripped.write_text(html.replace(chrome_rule, "", 1), encoding="utf-8")
    both_stripped = export_root / "patterns" / "light" / "-f2-both.html"
    both_stripped.write_text(
        html.replace(chrome_rule, "", 1).replace(font_inherit, "", 1), encoding="utf-8"
    )
    try:
        # Either layer alone stays clean.
        assert "target-size" not in violations_of(chrome_stripped)
        # Both stripped: the unstyled-default controls fall below 24px and
        # axe MUST report it.
        assert "target-size" in violations_of(both_stripped)
    finally:
        chrome_stripped.unlink()
        both_stripped.unlink()


def test_negative_disagreement_role_absent_in_both_lanes(
    page: Page, export_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fold F4: the disagreement check must be able to say NO — a role that
    must NOT be present (table on the button page) is absent in BOTH lanes,
    and a resolver stubbed to always-True REDS the comparison (a lying
    resolver cannot hide behind presence-only checks)."""
    path = export_root / "patterns" / "light" / "button.html"
    html = path.read_text(encoding="utf-8")
    page.goto(path.as_uri())
    snapshot = page.locator("body").aria_snapshot()
    import re

    tree_roles = {
        match.group(1)
        for match in re.finditer(r"^\s*-?\s*'?([a-z]+)", snapshot, re.MULTILINE)
    }
    resolver = ImplicitRoleResolver()
    absent_role = "table"  # in the resolver's pinned set; not on the button page
    assert resolver.has_role(html, absent_role) is False
    assert absent_role not in tree_roles
    # The lying-resolver control: always-True must disagree with the tree.
    class AlwaysTrue:
        def has_role(self, html: str, role: str) -> bool:
            return True

    stub = AlwaysTrue()
    assert stub.has_role(html, absent_role) != (absent_role in tree_roles)


def _e1_role_cells() -> list[tuple[str, list[str]]]:
    """(component key, required-roles items) from the parsed contract — the
    §E.1 Required-roles column is index 3."""
    contract = parse_contract(CONTRACT.read_text(encoding="utf-8"), MANIFEST)
    table = next(table for table in contract.tables if table.slug == "e-1-components")
    return [
        (row.key, split_items(row.cells[3]))
        for row in table.body
        if split_items(row.cells[3])
    ]


def test_browser_a11y_tree_agrees_with_the_implicit_role_resolver(
    page: Page, export_root: Path
) -> None:
    """The disagreement check: for every role an §E.1 Required-roles cell
    names, the browser's accessibility tree on that component's library
    page must agree with ``ImplicitRoleResolver``'s verdict over the same
    page's HTML — any disagreement reds (it retro-challenges G1a's
    resolver; the resolution is recorded, not silenced)."""
    resolver = ImplicitRoleResolver()
    import re

    role_line = re.compile(r"^\s*-?\s*'?([a-z]+)", re.MULTILINE)

    def browser_roles(snapshot: str) -> set[str]:
        """Playwright's ``aria_snapshot`` renders the a11y tree as role-first
        lines (``- button "Energise output"``); the role token of each line
        is the tree's role set."""
        return {match.group(1) for match in role_line.finditer(snapshot)}

    for component, roles in _e1_role_cells():
        path = export_root / "patterns" / "light" / f"{component}.html"
        html = path.read_text(encoding="utf-8")
        page.goto(path.as_uri())
        tree_roles = browser_roles(page.locator("body").aria_snapshot())
        for role in roles:
            resolver_says = resolver.has_role(html, role)
            browser_says = role in tree_roles
            assert resolver_says == browser_says, (
                f"{component}: role {role!r} — resolver says {resolver_says}, "
                f"the browser a11y tree says {browser_says} "
                f"(tree roles: {sorted(tree_roles)})"
            )
