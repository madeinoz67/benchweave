"""The dmm class reference (L12 of the class sweep; design record
``.claude/deep-review/2026-10-19-classref-l12-dmm-design.md``): the
mockup-consistency arm (A3) and the pattern-library readings-page
composition with its drift guard.

A3, third class of the sweep — first one where the mockup is AUTHORED
with the reference, not inherited. The mockup
(``docs/internal/ui-styleguide-mockups/class-dmm.html``) is the spec;
the reference is the data; this test is the bridge, keyed on the shared
census instrument (``tests/ui_html/classref_census.py`` — the L12 lift,
RC-L12-3). Unlike dc_psu there is NO derived fixture: the mockup is
authored to the committed OTDP class example's own shape (2 measure
channels x 1 declared quantity = 2 tiles), so the census resolves over
the committed example directly (F-dmm-1 IS the example; F-dmm-2 does
not exist). The kill is two-directional by construction: a mockup edit
that changes a hook count reds against the resolved expectation, and a
reference edit that changes the derivation (a count expression, the
plot binding, the channels slot) reds against the mockup's counts. A
mockup edit that does NOT redden the test is the instrument failing —
report, never a quiet pass (the record's §6 A3 wording).

The placement contract rides the shared census from birth (the F1
lesson, RC-L12-1): every hook on its §E.1 root, container-scoped hooks
inside their containers, and the preset-preview control card carrying
NO ``bw-`` hook — a cannot-derive surface must never present as a
reading.

The expansion side (derive-ui/verify-ui censuses) is the SDK widening's
work and rides that train; what this file pins is the corpus pair's
structure — the reference document and the composition the host renders
from it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from benchweave_ui_html import classref, patterns

from classref_census import (
    HOOKS,
    PLACEMENT_CONTAINER,
    PLACEMENT_TAG,
    HookCensus,
    hook_census,
    load_document,
    resolve_count,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = REPO_ROOT / "standards/plugin-ui-class-reference/0.3.0"
REFERENCE = FAMILY_DIR / "class-dmm.json"
DESCRIPTOR = REPO_ROOT / "standards/otdp/0.2.3/examples/class-dmm.json"
MOCKUP = REPO_ROOT / "docs/internal/ui-styleguide-mockups/class-dmm.html"


def _dmm_census() -> dict[str, dict[str, int]]:
    return hook_census(MOCKUP)


def _measure_channels(reference: dict[str, Any], descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    """The channels the reference's channels slot resolves — the role the
    SLOT names (never a literal role string here), declaration order."""
    where_role = str(reference["slots"]["inputs"]["where_role"])
    return [c for c in descriptor["channels"] if str(c["role"]) == where_role]


def _structural_counters(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The closed counter set over (reference x fixture): every counter is
    an expression over the fixture's declared channels and their declared
    quantities — never a count imported from the mockup."""
    measure = _measure_channels(reference, descriptor)
    n_measure_channels = len(measure)
    n_scalar_variables = sum(len(c["quantities"]) for c in measure)
    return {
        "n_measure_channels": n_measure_channels,
        "n_scalar_variables": n_scalar_variables,
        "n_reading_tiles": n_scalar_variables,  # one tile per scalar variable
        "n_pages": len(reference["pages"]),
    }


def _resolved_readings_expectation(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The expect.components rows scoped to the readings page, resolved over
    the committed example (no derived fixture — the mockup is authored to
    the example's own shape)."""
    counters = _structural_counters(reference, descriptor)
    resolved: dict[str, int] = {}
    for name, row in reference["expect"]["components"].items():
        if row.get("per_page") == "readings":
            resolved[name] = resolve_count(str(row["count"]), counters)
    return resolved


# --- A3: the mockup-consistency arm ---------------------------------------------


def test_the_mockup_carries_the_contract_hooks_in_both_themes() -> None:
    """The hook pass (RC-L11-3), from birth this time (RC-L12-1): both
    theme sections carry every hook family the census keys on — a hook
    absent from one theme is a composition break, not a style choice."""
    census = _dmm_census()
    assert set(census) == {"light", "dark"}
    for theme, hooks in census.items():
        for hook in HOOKS:
            assert hooks[hook] >= 1, (theme, hook)


def test_mockup_hook_counts_equal_the_resolved_expectation() -> None:
    """A3, the load-bearing arm: per theme section, the mockup's hook
    counts EQUAL the reference's resolved expectation over the committed
    OTDP example (2 measure channels x 1 declared quantity = 2 tiles,
    1 plot, 1 table) — the counts derived on BOTH sides, never literals
    on either.

    Kill direction 1: edit the mockup's card count — the reading hook
    count diverges from the resolved expectation and this reds.
    Kill direction 2: edit the reference's derivation — a count
    expression, the plot binding, the channels slot's role — and the
    RESOLVED side diverges from the mockup and this reds."""
    reference = load_document(REFERENCE)
    fixture = load_document(DESCRIPTOR)
    resolved = _resolved_readings_expectation(reference, fixture)
    assert set(resolved) == {"reading-tile", "engineering-plot", "data-table"}, resolved
    census = _dmm_census()
    for theme, hooks in census.items():
        assert hooks["bw-reading"] == resolved["reading-tile"], theme
        assert hooks["bw-plot"] == resolved["engineering-plot"], theme
        assert hooks["bw-data-table"] == resolved["data-table"], theme


def test_every_hook_sits_on_its_contract_root_and_container() -> None:
    """The count-conserving-move kill (L11's refute proved it necessary;
    this class carries it from birth): every hook is on its §E.1 root
    element, the container-scoped hooks sit in their containers, and the
    preset-preview control card (a cannot_derive surface) carries NO
    ``bw-`` hook — a cannot-derive surface must never present as a
    reading. The count census alone is placement-blind: a hook moved
    count-conservingly onto the control card or out of its container
    reds HERE while the count arm stays green."""
    parser = HookCensus()
    parser.feed(MOCKUP.read_text(encoding="utf-8"))
    assert parser.placements, "the census recorded no hook placements"
    for theme, hook, tag, ancestors in parser.placements:
        assert tag == PLACEMENT_TAG[hook], (theme, hook, tag)
        container = PLACEMENT_CONTAINER.get(hook)
        if container is not None:
            # the stack at recording time holds ANCESTORS only (the
            # current element is appended after the hook check)
            assert any(
                container in ancestor_classes
                for _ancestor_tag, ancestor_classes in ancestors
            ), (theme, hook, container)
    # the preset-preview control card: one per theme, tag section, no hook carried
    assert len(parser.control_hooks) == 2, parser.control_hooks
    for theme, tag, carried in parser.control_hooks:
        assert tag == "section", (theme, tag)
        assert carried == (), (theme, carried)


def test_both_themes_carry_the_identical_hook_census() -> None:
    """One composition, two themes: the hook census is theme-invariant."""
    census = _dmm_census()
    assert census["light"] == census["dark"]


def test_the_alert_surface_is_one_per_theme_and_a_named_cannot_derive() -> None:
    """The mockup's alert aside is structure the composition renders and
    data the reference cannot derive: exactly one ``bw-alert-bubble`` per
    theme, and ``range-margin-alert`` names it in the deviation ledger
    (the condition is commissioned policy, A02)."""
    reference = load_document(REFERENCE)
    ids = {str(row["id"]) for row in reference["cannot_derive"]}
    assert "range-margin-alert" in ids
    census = _dmm_census()
    for theme, hooks in census.items():
        assert hooks["bw-alert-bubble"] == 1, theme


def test_the_reference_selects_for_the_class_descriptor() -> None:
    """A4's green half, gateway-side: the dmm class example's profile
    now selects a corpus reference (``select_references`` returned None
    before the class existed — the pair banked RED at design time on the
    L11 branch head, this record §15)."""
    from benchweave.presentation.classref import select_references
    from benchweave.vendoring import corpus_root

    selected = select_references(corpus_root(), load_document(DESCRIPTOR))
    assert selected is not None and len(selected) == 1
    assert selected[0]["profile_id"] == "otdp.dmm/1.0.0"


# --- the pattern-library readings page --------------------------------------------


def test_tile_count_and_labels_derive_from_the_otdp_example() -> None:
    """D2 at the composition: the page's reading tiles are one per
    (channel, quantity) pair of the OTDP class example's declared
    measure channels — 2 x 1 computed from the descriptor, never a
    literal; every tile label names its channel label and quantity,
    both corpus strings."""
    page = classref.render_dmm_readings_page()
    descriptor = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
    measure = _measure_channels(reference, descriptor)
    expected_tiles = sum(len(c["quantities"]) for c in measure)
    assert expected_tiles >= 1
    tiles = re.findall(r'class="bw-reading[ "]', page)
    assert len(tiles) == expected_tiles
    for channel in measure:
        for quantity in channel["quantities"]:
            assert f"{channel['label']} · {quantity}" in page, (channel["id"], quantity)


def test_the_trend_is_one_plot_with_both_channel_traces() -> None:
    """One engineering plot (the layout block's trend section); the
    trace set is one per declared measure channel — both channel traces
    of the example, matching the mockup's two."""
    page = classref.render_dmm_readings_page()
    figures = re.findall(r'class="bw-plot[ "]', page)
    assert len(figures) == 1
    descriptor = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
    for channel in _measure_channels(reference, descriptor):
        for quantity in channel["quantities"]:
            assert f"{channel['label']} · {quantity}" in page, (channel["id"], quantity)


def test_the_table_covers_every_channel_quantity_pair() -> None:
    """The data table's body is one row per (channel, quantity) pair —
    the same derivation as the tiles; the quality column carries the
    mockup's own wording (Verified / Near limit)."""
    page = classref.render_dmm_readings_page()
    descriptor = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
    measure = _measure_channels(reference, descriptor)
    body_rows = re.findall(r"<tr[^>]*>", page)[1:]  # the header row excluded
    assert len(body_rows) == sum(len(c["quantities"]) for c in measure)
    assert "Verified" in page
    assert "Near limit" in page


def test_the_page_sections_mirror_the_reference_layout_block() -> None:
    """The composition's sections carry the layout block's own surfaces
    and spans (data-bw-span): readings 12 raised, trend 7 recessed, table
    5 raised — the dc_psu ratio, the class's difference is content not
    geometry. An edit to the reference's layout block reddens the
    composition."""
    page = classref.render_dmm_readings_page()
    reference = load_document(REFERENCE)
    layout = next(
        lp for lp in reference["layouts"] if lp["page_id"] == "readings"
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
    surface derives at birth (configure is preset-mediated, a named
    deviation; no staged control is fabricated)."""
    page = classref.render_dmm_readings_page()
    assert "bw-mode-banner" in page
    banner = page.find("bw-mode-banner")
    tile = page.find('class="bw-reading')
    assert -1 < banner < tile
    for surface in ("bw-alert-bubble", "bw-plot", "bw-data-table"):
        assert surface in page, surface
    assert "bw-rotary" not in page  # function-selection is cannot_derive
    assert "bw-confirm" not in page
    assert "<button" not in page


def test_the_range_margin_alert_renders_the_mockup_wording() -> None:
    """The alert's title and condition wording trace to the mockup (the
    spec); the device-specific suffix stays mockup-side."""
    page = classref.render_dmm_readings_page()
    assert "Range margin" in page
    assert "approaching configured range limit" in page


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_class_page_exports_in_both_themes(tmp_path: Path, theme: str) -> None:
    patterns.export(tmp_path)
    path = tmp_path / "patterns" / theme / "class-readings.html"
    assert path.is_file(), path
    html = path.read_text(encoding="utf-8")
    assert "data-bw-pattern-library" in html
    assert 'data-bw-pattern-page="class-readings"' in html
    assert "Reference channel 1 · voltage" in html


def test_the_class_page_census_entry_is_registered() -> None:
    """The page rides the PATTERNS census: kind class-page on the
    class-readings page, row-keyed to the family's dmm reference."""
    entry = next(e for e in patterns.PATTERNS if e.page == "class-readings")
    assert entry.kind == "class-page"
    assert entry.row_id == "plugin-ui-class-reference::class-dmm"
    assert entry.fixture_id == "readings"
