"""The styleguide mockup's compositions (#462 row 1, Landing 3, spec-drop
2026-10-15): the mockup shows BOTH operator compositions in matched light
and dark themes — the DC PSU surface and the logic-analyser capture view.
The analyser composition is the OWNER-AUTHORED SPEC
(/tmp/classref-mockup-spec.html, the authoritative layout), adopted
verbatim in layout, spacing, tokens and composition, with three
adaptations: invented naming only (Veridian LA-32 / veridian.la32 /
la32-fpga.bin — the real product's name appears nowhere in committed
bytes), theme integration (selectors scoped to the section, a unique
hatch-pattern id per theme), and these test arms. The pattern-library
class page is untouched — the mock leads the renderer.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MOCKUP = REPO_ROOT / "docs/internal/ui-styleguide-mockup.html"


class _Balance(HTMLParser):
    """The tag-balance checker (the standing arm)."""

    VOID = {"meta", "br", "img", "input", "hr", "link"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"mismatch at {tag}")
        else:
            self.stack.pop()


@pytest.fixture
def mockup_html() -> str:
    return MOCKUP.read_text(encoding="utf-8")


def _themes(html: str) -> dict[str, str]:
    """Split the mockup into its two theme sections (the sections nest)."""
    light = html.split('<section class="theme"', 1)[1].split('<section class="theme dark"', 1)[0]
    dark = html.split('<section class="theme dark"', 1)[1].split("</main>", 1)[0]
    return {"light": light, "dark": dark}


def test_bus_chips_carry_hex_values(mockup_html: str) -> None:
    """The annotation-chip row: every bus chip text is 0x-prefixed hex,
    singly or in the paired / form (the spec's chip vocabulary)."""
    for theme, section in _themes(mockup_html).items():
        chips = re.findall(r'class="pl"[^>]*>([^<]*)</text>', section)
        assert len(chips) == 4, (theme, chips)
        for chip in chips:
            assert re.fullmatch(r"0x[0-9A-F]{2}( / 0x[0-9A-F]{2})*", chip), (theme, chip)
        assert "0x9F" in chips, theme


def test_cursors_trigger_and_axis_readout(mockup_html: str) -> None:
    """The canvas's measurement furniture: two dashed cursor lines with
    their A/B labels, the trigger line and chip, the axis readout."""
    for theme, section in _themes(mockup_html).items():
        dashes = re.findall(r'<line[^>]*stroke-dasharray', section)
        assert len(dashes) == 2, (theme, len(dashes))
        labels = re.findall(r'class="cu">([^<]*)</text>', section)
        assert sorted(labels) == ["A", "B"], (theme, labels)
        assert re.search(r'class="tg"[^>]*>trigger</text>', section), theme
        assert re.search(r'x1="250.0"[^>]*stroke="var\(--bw-warning\)"', section), theme
        axis = section.split("</svg>", 1)[1]
        assert "2048" in axis and "400" in axis, theme
        assert "Δt A→B" in axis and "2.52 µs" in axis, theme


def test_hatch_x_state_rects(mockup_html: str) -> None:
    """The x-state hatch rects on the MISO lane — at least two per theme,
    each filling that theme's unique hatch pattern."""
    for theme, section in _themes(mockup_html).items():
        hatch_id = f"hatch-{theme[0]}"
        rects = re.findall(f'<rect[^>]*fill="url\\(#{hatch_id}\\)"', section)
        assert len(rects) >= 2, (theme, rects)


def test_hidden_lanes_note(mockup_html: str) -> None:
    """The disclosure note: the un-drawn lanes are named and counted."""
    for theme, section in _themes(mockup_html).items():
        assert re.search(r"D4–D31, CLK2 · 29 lanes hidden", section), theme


def test_the_mockup_markup_is_balanced(mockup_html: str) -> None:
    """The standing tag-balance check — 0 errors and 0 unclosed tags."""
    parser = _Balance()
    parser.feed(mockup_html)
    assert not parser.errors, parser.errors[:5]
    assert not parser.stack, parser.stack[:5]


# --- the adopted composition structure ----------------------------------------


def test_both_theme_sections_carry_the_spec_composition(mockup_html: str) -> None:
    """Each theme section carries the spec's head, lease strip, tile set
    and the single-SVG lane canvas (the owner-authored composition)."""
    for theme, section in _themes(mockup_html).items():
        assert "Device overview" in section, theme
        assert "Veridian LA-32" in section, theme
        assert "Controller lease" in section, theme
        assert "la32-fpga.bin" in section, theme
        assert section.count('class="bw-reading"') == 5, theme
        assert 'aria-label="Logic capture mock"' in section, theme


def test_the_lane_label_set_and_position_badges(mockup_html: str) -> None:
    """The canvas's lane label set with its position badges: CS#/SCK/
    MOSI/MISO/CLK1/SPI and the D0-D3 / ch32 / mode 0 marks."""
    for theme, section in _themes(mockup_html).items():
        for label in ("CS#", "SCK", "MOSI", "MISO", "CLK1", "SPI"):
            assert f'class="ln">{label}</text>' in section, (theme, label)
        for badge in ("D0", "D1", "D2", "D3", "ch32", "mode 0"):
            assert f'>{badge}</text>' in section, (theme, badge)


def test_side_rail_sequencer_and_messages(mockup_html: str) -> None:
    """The raised side rail: the staged trigger-sequencer table (its
    condition row on the frame lane), the three buttons (Apply disabled),
    the disabled reason, and the gateway-observations message."""
    for theme, section in _themes(mockup_html).items():
        rail = section.split('class="panel raised"', 1)[1]
        assert "Staged configuration" in rail and "Trigger sequencer" in rail, theme
        for head in ("<th>Level</th>", "<th>Condition</th>", "<th>Then</th>"):
            assert head in rail, (theme, head)
        assert "D0 ↓ (CS#)" in rail, theme
        assert "Arm capture" in rail and "Stop" in rail, theme
        assert "Apply" in rail and "disabled" in rail, theme
        assert "sequencer register packing not yet recovered" in rail, theme
        assert "Gateway observations" in rail and "Messages" in rail, theme
        assert "pre-trigger buffer filling" in rail, theme


def test_context_strip_and_severity(mockup_html: str) -> None:
    """The axis status line (acquisition disclosure) and the tile severity
    model (the data-severity keys the spec's tiles carry)."""
    for theme, section in _themes(mockup_html).items():
        assert re.search(r"2048</b> samples acquired → <b>400</b> drawn · 100 MHz", section), theme
        assert "capture time" in section, theme
        severities = re.findall(r'data-severity="([a-z]+)"', section)
        assert severities == ["advisory", "neutral", "neutral", "neutral", "success"], (
            theme,
            severities,
        )


def test_naming_is_invented_only(mockup_html: str) -> None:
    """The public-repo rule: the invented vocabulary rides, the real
    product's name appears nowhere in the document."""
    assert "Veridian LA-32" in mockup_html
    assert "veridian.la32" in mockup_html
    assert "la32-fpga.bin" in mockup_html
    for real in ("Intronix", "intronix", "LogicPort"):
        assert real not in mockup_html, real
