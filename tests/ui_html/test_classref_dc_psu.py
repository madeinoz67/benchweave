"""The dc_psu class reference (L11 of the class sweep; design record
``.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md``): the
mockup-consistency arm (A3) and the pattern-library output-page
composition with its drift guard.

A3 — the L11 namesake. The mockup
(``docs/internal/ui-styleguide-mockups/class-dc_psu.html``) is the
spec; the reference is the data. This test is the bridge: it counts the
§E.1 contract hooks per theme section (RC-L11-3's hook pass put them on
the contract surfaces) and asserts the per-channel structure EQUALS the
reference's resolved expectation over F-psu-2 — the mockup-shaped
single-channel fixture derived from the committed OTDP class example.
The kill is two-directional by construction: a mockup edit that changes
a hook count reds against the resolved expectation, and a reference edit
that changes the derivation (a count expression, the plot binding, the
channels slot) reds against the mockup's counts. A mockup edit that does
NOT redden the test is the instrument failing — report, never a quiet
pass (the record's §6 A3 wording).

The expansion side (derive-ui/verify-ui censuses) is the SDK widening's
work and rides that train; what this file pins is the corpus pair's
structure — the reference document and the composition the host renders
from it.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
from benchweave_ui_html import classref, patterns

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = REPO_ROOT / "standards/plugin-ui-class-reference/0.3.0"
REFERENCE = FAMILY_DIR / "class-dc_psu.json"
DESCRIPTOR = REPO_ROOT / "standards/otdp/0.2.3/examples/class-dc_psu.json"
MOCKUP = REPO_ROOT / "docs/internal/ui-styleguide-mockups/class-dc_psu.html"

#: The §E.1 contract hooks the mockup carries (RC-L11-3): the component
#: roots the census keys on — never bespoke selectors.
HOOKS = ("bw-reading", "bw-alert-bubble", "bw-plot", "bw-data-table")


def _load(path: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


class _HookCensus(HTMLParser):
    """The §E.1 hook count per ``data-theme`` section of the mockup."""

    def __init__(self) -> None:
        super().__init__()
        self.counts: dict[str, dict[str, int]] = {}
        self._theme: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = {key: value for key, value in attrs}
        classes = set((fields.get("class") or "").split())
        theme = fields.get("data-theme")
        if "mock-theme" in classes and theme is not None:
            self._theme = theme
            self.counts[theme] = {hook: 0 for hook in HOOKS}
            return
        if self._theme is not None:
            for hook in HOOKS:
                if hook in classes:
                    self.counts[self._theme][hook] += 1


def _hook_census() -> dict[str, dict[str, int]]:
    parser = _HookCensus()
    parser.feed(MOCKUP.read_text(encoding="utf-8"))
    return parser.counts


def _source_channels(reference: dict[str, Any], descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    """The channels the reference's channels slot resolves — the role the
    SLOT names (never a literal role string here), declaration order."""
    where_role = str(reference["slots"]["outputs"]["where_role"])
    return [c for c in descriptor["channels"] if str(c["role"]) == where_role]


def _structural_counters(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The closed counter set over (reference × fixture): every counter is
    an expression over the fixture's declared channels and their declared
    quantities — never a count imported from the mockup."""
    source = _source_channels(reference, descriptor)
    n_source_channels = len(source)
    n_scalar_variables = sum(len(c["quantities"]) for c in source)
    return {
        "n_source_channels": n_source_channels,
        "n_scalar_variables": n_scalar_variables,
        "n_reading_tiles": n_scalar_variables,  # one tile per scalar variable
        "n_pages": len(reference["pages"]),
    }


def _resolve_count(expression: str, counters: dict[str, int]) -> int:
    """The closed count grammar the expect block authors: a pure-numeric
    literal or a ``{name}`` expression over the structural counters. An
    expression outside the closure refuses — an unknown name cannot
    launder a divergence."""
    if re.fullmatch(r"[0-9]+", expression):
        return int(expression)
    match = re.fullmatch(r"\{([a-z_]+)\}", expression)
    if match is not None and match.group(1) in counters:
        return counters[match.group(1)]
    raise AssertionError(f"unknown count expression: {expression!r}")


def _f_psu_2() -> dict[str, Any]:
    """F-psu-2, the mockup-shaped fixture: the committed OTDP class
    example with exactly ONE source channel kept — the mockup's own
    shape, derived from the corpus pair in-test (the record's §6 fixed
    fixture set)."""
    document = _load(DESCRIPTOR)
    source = [
        c
        for c in document["channels"]
        if str(c["role"]) == "source"
    ]
    assert source, "the OTDP class example declares no source channels"
    document["channels"] = source[:1]
    return document


def _resolved_output_expectation(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The expect.components rows scoped to the output page, resolved over
    the fixture."""
    counters = _structural_counters(reference, descriptor)
    resolved: dict[str, int] = {}
    for name, row in reference["expect"]["components"].items():
        if row.get("per_page") == "output":
            resolved[name] = _resolve_count(str(row["count"]), counters)
    return resolved


# --- A3: the mockup-consistency arm ---------------------------------------------


def test_the_mockup_carries_the_contract_hooks_in_both_themes() -> None:
    """The hook pass (RC-L11-3): both theme sections carry every hook
    family the census keys on — a hook absent from one theme is a
    composition break, not a style choice."""
    census = _hook_census()
    assert set(census) == {"light", "dark"}
    for theme, hooks in census.items():
        for hook in HOOKS:
            assert hooks[hook] >= 1, (theme, hook)


def test_mockup_hook_counts_equal_the_resolved_expectation() -> None:
    """A3, the load-bearing arm: per theme section, the mockup's hook
    counts EQUAL the reference's resolved expectation over F-psu-2 (one
    source channel × its three declared quantities = 3 tiles, 1 plot, 1
    table) — the counts derived on BOTH sides, never literals on either.

    Kill direction 1: edit the mockup's card count — the reading hook
    count diverges from the resolved expectation and this reds.
    Kill direction 2: edit the reference's derivation — a count
    expression, the plot binding, the channels slot's role — and the
    RESOLVED side diverges from the mockup and this reds."""
    reference = _load(REFERENCE)
    fixture = _f_psu_2()
    resolved = _resolved_output_expectation(reference, fixture)
    assert set(resolved) == {"reading-tile", "engineering-plot", "data-table"}, resolved
    census = _hook_census()
    for theme, hooks in census.items():
        assert hooks["bw-reading"] == resolved["reading-tile"], theme
        assert hooks["bw-plot"] == resolved["engineering-plot"], theme
        assert hooks["bw-data-table"] == resolved["data-table"], theme


def test_both_themes_carry_the_identical_hook_census() -> None:
    """One composition, two themes: the hook census is theme-invariant."""
    census = _hook_census()
    assert census["light"] == census["dark"]


def test_the_alert_surface_is_one_per_theme_and_a_named_cannot_derive() -> None:
    """The mockup's alert aside is structure the composition renders and
    data the reference cannot derive: exactly one ``bw-alert-bubble`` per
    theme, and ``margin-alert`` names it in the deviation ledger (the
    condition is commissioned policy, A02)."""
    reference = _load(REFERENCE)
    ids = {str(row["id"]) for row in reference["cannot_derive"]}
    assert "margin-alert" in ids
    census = _hook_census()
    for theme, hooks in census.items():
        assert hooks["bw-alert-bubble"] == 1, theme


def test_the_reference_selects_for_the_class_descriptor() -> None:
    """A4's green half, gateway-side: the dc_psu class example's profile
    now selects a corpus reference (``select_references`` returned None
    before the class existed — the recorded RED control)."""
    from benchweave.presentation.classref import select_references
    from benchweave.vendoring import corpus_root

    selected = select_references(corpus_root(), _load(DESCRIPTOR))
    assert selected is not None and len(selected) == 1
    assert selected[0]["profile_id"] == "otdp.dc_psu/1.0.0"


# --- the pattern-library output page --------------------------------------------


def test_tile_count_and_labels_derive_from_the_otdp_example() -> None:
    """D2 at the composition: the page's reading tiles are one per
    (channel, quantity) pair of the OTDP class example's declared source
    channels — 2 × 3 computed from the descriptor, never a literal; every
    tile label names its channel id and quantity, both corpus strings."""
    page = classref.render_output_page()
    descriptor = _load(DESCRIPTOR)
    reference = _load(REFERENCE)
    source = _source_channels(reference, descriptor)
    expected_tiles = sum(len(c["quantities"]) for c in source)
    assert expected_tiles >= 1
    tiles = re.findall(r'class="bw-reading[ "]', page)
    assert len(tiles) == expected_tiles
    for channel in source:
        for quantity in channel["quantities"]:
            assert f"{channel['label']} · {quantity}" in page, (channel["id"], quantity)


def test_the_trend_is_one_plot_with_the_disclosed_two_traces() -> None:
    """One engineering plot (the layout block's trend section); the trace
    set is the disclosed author choice (the record's channel_hints
    matter): voltage and current of the first declared channel, matching
    the mockup's two traces."""
    page = classref.render_output_page()
    figures = re.findall(r'class="bw-plot[ "]', page)
    assert len(figures) == 1
    descriptor = _load(DESCRIPTOR)
    first = next(c for c in descriptor["channels"] if str(c["role"]) == "source")
    assert f"{first['label']} · voltage" in page
    assert f"{first['label']} · current" in page


def test_the_table_covers_every_channel_quantity_pair() -> None:
    """The data table's body is one row per (channel, quantity) pair —
    the same derivation as the tiles; the quality column carries the
    mockup's own wording (Verified / Near limit)."""
    page = classref.render_output_page()
    descriptor = _load(DESCRIPTOR)
    reference = _load(REFERENCE)
    source = _source_channels(reference, descriptor)
    body_rows = re.findall(r"<tr[^>]*>", page)[1:]  # the header row excluded
    assert len(body_rows) == sum(len(c["quantities"]) for c in source)
    assert "Verified" in page
    assert "Near limit" in page


def test_the_page_sections_mirror_the_reference_layout_block() -> None:
    """The composition's sections carry the layout block's own surfaces
    and spans (data-bw-span): readings 12 raised, trend 7 recessed, table
    5 raised — the mockup's 5/7 ratio expressed in the vocabulary. An
    edit to the reference's layout block reddens the composition."""
    page = classref.render_output_page()
    reference = _load(REFERENCE)
    layout = next(
        lp for lp in reference["layouts"] if lp["page_id"] == "output"
    )
    for section in layout["sections"]:
        pattern = re.compile(
            rf'data-bw-section-id="{section["id"]}"[^>]*'
            rf'data-surface="{section["surface"]}"[^>]*'
            rf'data-bw-span="{section["span"]}"'
        )
        assert pattern.search(page), section["id"]


def test_the_page_composes_only_e1_partials() -> None:
    """Host composition of §E.1 partials only — no renderer change, no
    new contract rows; the banner leads (§E.1 placement), and no control
    surface derives at birth (the output action is a named deviation; no
    staged control is fabricated)."""
    page = classref.render_output_page()
    assert "bw-mode-banner" in page
    banner = page.find("bw-mode-banner")
    tile = page.find('class="bw-reading')
    assert -1 < banner < tile
    for surface in ("bw-alert-bubble", "bw-plot", "bw-data-table"):
        assert surface in page, surface
    assert "bw-rotary" not in page  # setpoint-staging is cannot_derive
    assert "bw-confirm" not in page
    assert "<button" not in page


def test_the_margin_alert_renders_the_mockup_wording() -> None:
    """The alert's title and condition wording trace to the mockup (the
    spec); the device-specific suffix stays mockup-side."""
    page = classref.render_output_page()
    assert "Operating margin" in page
    assert "approaching configured limit" in page


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_class_page_exports_in_both_themes(tmp_path: Path, theme: str) -> None:
    patterns.export(tmp_path)
    path = tmp_path / "patterns" / theme / "class-output.html"
    assert path.is_file(), path
    html = path.read_text(encoding="utf-8")
    assert "data-bw-pattern-library" in html
    assert 'data-bw-pattern-page="class-output"' in html
    assert "Reference channel 1 · voltage" in html


def test_the_class_page_census_entry_is_registered() -> None:
    """The page rides the PATTERNS census: kind class-page on the
    class-output page, row-keyed to the family's dc_psu reference."""
    entry = next(e for e in patterns.PATTERNS if e.page == "class-output")
    assert entry.kind == "class-page"
    assert entry.row_id == "plugin-ui-class-reference::class-dc_psu"
    assert entry.fixture_id == "output"
