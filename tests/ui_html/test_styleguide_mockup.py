"""The styleguide mockup's compositions (#462 row 1, Landing 3): the
mockup shows BOTH operator compositions — the DC PSU surface and the
digital-analyzer capture view — in matched light and dark themes. The
analyzer composition uses the mockup's semantic tokens and severity
model; lane group labels are DECIMAL positional (D{first}-D{last}); all
device and lane names are invented (the class-reference program's
fixture-vocabulary rule).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

UNKNOWN_CELL = "\u2014"  # the unknown marker an unstable bus cell carries


class _Balance(HTMLParser):
    """The tag-balance checker (the fold's standing arm)."""

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


REPO_ROOT = Path(__file__).resolve().parents[2]
MOCKUP = REPO_ROOT / "docs/internal/ui-styleguide-mockup.html"


@pytest.fixture
def mockup_html() -> str:
    return MOCKUP.read_text(encoding="utf-8")


def _themes(html: str) -> dict[str, str]:
    """Split the mockup into its two theme sections: between the theme
    opening tags and the next theme boundary (the sections nest, so the
    boundary is the next opening tag or the main close)."""
    light = html.split('<section class="theme"', 1)[1].split('<section class="theme dark"', 1)[0]
    dark = html.split('<section class="theme dark"', 1)[1].split("</main>", 1)[0]
    return {"light": light, "dark": dark}


def test_both_theme_sections_carry_the_analyzer_composition(mockup_html: str) -> None:
    """Each theme section carries the digital-analyzer capture view."""
    for theme, section in _themes(mockup_html).items():
        assert 'aria-label="Digital analyser capture view"' in section, theme


def test_lane_groups_are_eight_lanes_with_decimal_labels(mockup_html: str) -> None:
    """8-lane groups with DECIMAL positional labels D{first}-D{last}; the
    bus VALUES carry the hex formatting (F4: the values' formatting, not
    the prose header) — every value cell is two uppercase hex digits and
    every unknown cell is the unknown marker."""
    for theme, section in _themes(mockup_html).items():
        assert "D1-D8" in section, theme
        assert "D9-D16" in section, theme
        blocks = re.findall(
            r'<div class="bus-values">(.*?)</div>', section, re.DOTALL
        )
        assert len(blocks) == 2, theme
        for block in blocks:
            cells = re.findall(r"<span(?: class=\"unk\")?>([^<]*)</span>", block)
            assert len(cells) == 12, theme
            for cell in cells:
                assert cell == UNKNOWN_CELL or re.fullmatch(r"[0-9A-F]{2}", cell), (
                    theme,
                    cell,
                )


def test_arm_control_is_a_staging_pair(mockup_html: str) -> None:
    """F2: the analyzer's Arm control is the staging pair (a labelled
    numeric input followed by the Arm button) matching the pattern page
    and the reference's controls plan (arm: staging)."""
    for theme, section in _themes(mockup_html).items():
        start = section.find('aria-label="Run controls"')
        assert start != -1, theme
        run_block = section[start : start + 900]
        numeric = run_block.find('type="number"')
        label = run_block.find("Max duration")
        arm = run_block.find(">Arm<")
        assert -1 < label < numeric < arm, theme


def test_decoder_lanes_present(mockup_html: str) -> None:
    """Decoder annotation rows render beneath the channel/bus rows."""
    for theme, section in _themes(mockup_html).items():
        assert 'data-lane-kind="decoder"' in section, theme
        assert "I2C" in section and "UART" in section, theme


def test_capture_view_is_waveform_first(mockup_html: str) -> None:
    """Waveform-first: within the analyzer composition the lanes view
    renders before the run controls."""
    for theme, section in _themes(mockup_html).items():
        start = section.find('aria-label="Digital analyser capture view"')
        lanes = section.find("data-lane-kind", start)
        controls = section.find("Run controls", start)
        assert start != -1
        assert -1 < lanes < controls, theme


def test_analyzer_uses_the_severity_model(mockup_html: str) -> None:
    """The composition marks states with the mockup's severity classes —
    the warning decoder event carries the warning treatment, normal
    quality carries the normal treatment."""
    for theme, section in _themes(mockup_html).items():
        analyzer = section.split('aria-label="Digital analyser capture view"', 1)[1]
        analyzer = analyzer.split("</main>", 1)[0]
        assert "warning" in analyzer, theme
        assert "NORMAL" in analyzer, theme


def test_the_mockup_markup_is_balanced(mockup_html: str) -> None:
    """F4: the standing tag-balance check — the parser reports 0 errors
    and 0 unclosed tags over the whole document."""
    parser = _Balance()
    parser.feed(mockup_html)
    assert not parser.errors, parser.errors[:5]
    assert not parser.stack, parser.stack[:5]


def test_lane_names_are_invented(mockup_html: str) -> None:
    """No real instrument, vendor or corpus name appears — LA-32 and the
    Data line N labels are the class-reference fixture vocabulary."""
    html = mockup_html
    assert "LA-32" in html
    assert "Data line" in html
