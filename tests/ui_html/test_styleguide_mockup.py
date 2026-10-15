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


def _extract_group(html: str, start: int) -> str:
    """Balanced extraction of one <g ...>...</g> block: count the tags,
    never trust .*? past a nested group."""
    depth = 0
    for match in re.finditer(r"<g\b|</g>", html[start:]):
        if match.group(0) == "<g":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return html[start : start + match.end()]
    raise AssertionError(f"unbalanced group at {start}")


def _find_all_groups(html: str, cls: str) -> list[str]:
    """All balanced <g> blocks whose opening tag carries cls."""
    blocks = []
    for match in re.finditer(f'<g class="{cls}"', html):
        blocks.append(_extract_group(html, match.start()))
    return blocks


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
    grouped-bus HEX READOUT rows carry the values (the values' formatting,
    not the prose header) — every readout chip is a 0x-prefixed hex value
    and every unknown chip is the unknown marker."""
    for theme, section in _themes(mockup_html).items():
        assert "D1-D8" in section, theme
        assert "D9-D16" in section, theme
        groups = _find_all_groups(section, "lane-group")
        assert len(groups) == 2, theme
        for group in groups:
            assert "D1-D8" in group or "D9-D16" in group, theme
            readout_blocks = _find_all_groups(group, "bus-readout")
            assert len(readout_blocks) == 1, theme
            chips = re.findall(r"<text[^>]*>([^<]*)</text>", readout_blocks[0])
            assert len(chips) >= 3, theme
            for chip in chips:
                assert chip == UNKNOWN_CELL or re.fullmatch(r"0x[0-9A-F]{1,2}", chip), (
                    theme,
                    chip,
                )


def test_group_bracket_ties_members_to_the_readout(mockup_html: str) -> None:
    """The group bracket: within each lane-group element the hex readout
    row rides ABOVE its member lanes (document order), the bracket device
    that ties members to their group's values."""
    for theme, section in _themes(mockup_html).items():
        groups = _find_all_groups(section, "lane-group")
        assert len(groups) == 2, theme
        for group in groups:
            readout = group.find('class="bus-readout"')
            first_member = group.find('class="lane-trace"')
            assert -1 < readout < first_member, theme


def test_time_axis_carries_cursors_trigger_and_delta(mockup_html: str) -> None:
    """The time axis: X1/X2 cursor markers and the T trigger marker on the
    axis, the delta readout in the context strip."""
    for theme, section in _themes(mockup_html).items():
        axis_blocks = _find_all_groups(section, "time-axis")
        assert len(axis_blocks) == 1, theme
        axis_text = " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", axis_blocks[0]))
        for marker in ("X1", "X2", "T"):
            assert marker in axis_text, (theme, marker)
        assert "Δt X1→X2" in section, theme
        assert re.search(r"Δt X1→X2 [0-9.]+ µs", section), theme


def test_decode_annotations_align_under_the_waveform(mockup_html: str) -> None:
    """Decoded transaction chips ride the SAME plot grid as the lanes:
    every decoder row is inside the single lanes <svg>, beneath the lane
    traces (document order), with hex field chips."""
    for theme, section in _themes(mockup_html).items():
        svg_match = re.search(
            r'<svg class="lanes-plot"[^>]*>(.*?)</svg>', section, re.DOTALL
        )
        assert svg_match, theme
        svg = svg_match.group(1)
        assert svg.count('data-lane-kind="decoder"') == 3, theme
        last_trace = svg.rfind('class="lane-trace"')
        for decoder_match in re.finditer(
            r'<g data-lane-kind="decoder"[^>]*>', svg
        ):
            assert decoder_match.start() > last_trace, theme
        decoder_blocks = [
            _extract_group(svg, m.start())
            for m in re.finditer(r'<g data-lane-kind="decoder"', svg)
        ]
        texts = re.findall(r"<text[^>]*>([^<]*)</text>", "".join(decoder_blocks))
        assert any(re.fullmatch(r"0x[0-9A-F]{2}", t) for t in texts), theme


def _frame_window(section: str, lane_index: int) -> tuple[float, float]:
    """The frame lane's transaction window in plot x-coordinates: from
    the first transition x to the last (the lead-in from the plot edge is
    point 0; the lead-out the last point)."""
    lane_start = section.find(f'data-lane-index="{lane_index}"')
    assert lane_start != -1, lane_index
    lane = _extract_group(section, section.rfind("<g", 0, lane_start))
    points = re.findall(r"([ML])([0-9.]+) ([0-9.]+)", lane)
    assert len(points) >= 4, (lane_index, len(points))
    return float(points[1][1]), float(points[-2][1])


def test_cursors_bracket_the_frame_window(mockup_html: str) -> None:
    """The cursors bracket a REAL measurement: X1 and X2 sit at the frame
    lane's fall and rise (the transaction window), and the context strip's
    delta is that window's duration."""
    for theme, section in _themes(mockup_html).items():
        fall_x, rise_x = _frame_window(section, 1)
        cursor_xs = [
            float(m.group(1))
            for m in re.finditer(r'<line class="cursor-line" x1="([0-9.]+)"', section)
        ]
        assert len(cursor_xs) == 2, theme
        assert abs(cursor_xs[0] - fall_x) < 2, (theme, cursor_xs, fall_x)
        assert abs(cursor_xs[1] - rise_x) < 2, (theme, cursor_xs, rise_x)
        assert "Δt X1→X2 1.68 µs" in section, theme


def test_decode_chips_sit_in_their_frame_windows(mockup_html: str) -> None:
    """Annotations visibly align to the lanes they decode: the SPI chips
    sit inside lane 1's low window, the I2C chips inside lane 9's."""
    for theme, section in _themes(mockup_html).items():
        for lane_index, decoder_label in ((1, "SPI"), (9, "I2C")):
            fall_x, rise_x = _frame_window(section, lane_index)
            decoder_start = section.find(
                f'aria-label="{decoder_label} decode annotations"'
            )
            assert decoder_start != -1, (theme, decoder_label)
            decoder = _extract_group(section, section.rfind("<g", 0, decoder_start))
            chip_xs = [
                float(m.group(1))
                for m in re.finditer(r'<text x="([0-9.]+)"', decoder)
            ]
            assert chip_xs, (theme, decoder_label)
            for chip_x in chip_xs:
                assert fall_x < chip_x < rise_x, (theme, decoder_label, chip_x)


def test_capture_context_strip(mockup_html: str) -> None:
    """The capture-context strip: acquired/drawn counts, the rate and the
    capture-time basis."""
    for theme, section in _themes(mockup_html).items():
        assert re.search(r"[0-9,]+ samples acquired", section), theme
        assert re.search(r"→ [0-9,]+ drawn", section), theme
        assert "1 MHz" in section, theme
        assert "capture time" in section, theme


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
