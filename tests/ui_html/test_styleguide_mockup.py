"""The styleguide mock-ups (#462 row 1, Landing 3 — spec drop + split
2026-10-15): one self-contained mock per device class under
docs/internal/ui-styleguide-mockups/, each carrying both themes. The
logic-analyser mock is the OWNER-AUTHORED SPEC composition
(/tmp/classref-mockup-spec.html) adapted three ways: invented naming only
(Veridian LA-32 / veridian.la32 / la32-fpga.bin — the real product's
name appears nowhere in committed bytes), the shipped token set embedded
byte-for-byte from packages/ui-html assets (drift-guarded), and the
shipped component class vocabulary (bw-reading / bw-panel / bw-button).
The index (ui-styleguide-mockup.html) links every device mock; the
tag-balance, drift-guard and naming arms run against EVERY file in the
directory so each L11-L21 sweep file inherits the gate automatically.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MOCKS_DIR = REPO_ROOT / "docs/internal/ui-styleguide-mockups"
INDEX = REPO_ROOT / "docs/internal/ui-styleguide-mockup.html"
ASSETS = REPO_ROOT / "packages/ui-html/src/benchweave_ui_html/assets"

MOCK_FILES = sorted(MOCKS_DIR.glob("class-*.html"))


class _Balance(HTMLParser):
    """The tag-balance checker (the standing arm)."""

    VOID = {"meta", "br", "img", "input", "hr", "link", "line", "rect", "path",
            "pattern", "polyline"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pass

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"mismatch at {tag}")
        else:
            self.stack.pop()


def _shipped(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def _embedded(html: str, asset: str) -> str:
    marker = asset.removesuffix(".css")
    after_open = html.split(f"/* bw-shipped:{marker} ", 1)[1].split("*/", 1)[1]
    block = after_open.split(f"/* /bw-shipped:{marker} */", 1)[0]
    return block.strip("\n")


@pytest.mark.parametrize("path", MOCK_FILES, ids=lambda p: p.stem)
def test_every_mock_is_tag_balanced(path: Path) -> None:
    parser = _Balance()
    parser.feed(path.read_text(encoding="utf-8"))
    assert not parser.errors, parser.errors[:5]
    assert not parser.stack, parser.stack[:5]


@pytest.mark.parametrize("path", MOCK_FILES, ids=lambda p: p.stem)
def test_every_mock_embeds_the_shipped_tokens_byte_for_byte(path: Path) -> None:
    """The single-source-of-truth arm: the embedded blocks equal the
    package's shipped bytes — any token/class drift in the package reds
    this row."""
    html = path.read_text(encoding="utf-8")
    for asset in ("tokens.css", "themes.css", "globals.css"):
        assert _embedded(html, asset) == _shipped(asset).rstrip("\n"), (path.stem, asset)


@pytest.mark.parametrize("path", MOCK_FILES, ids=lambda p: p.stem)
def test_every_mock_naming_is_invented_only(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    assert (
        "Veridian" in html
        or "PSU-01" in html
        or "DMM-01" in html
        or "OSC-01" in html
    ), path.stem
    for real in ("Intronix", "intronix", "LogicPort"):
        assert real not in html, (path.stem, real)


def test_the_directory_has_every_device_mock() -> None:
    assert {p.name for p in MOCK_FILES} == {
        "class-dc_psu.html",
        "class-dmm.html",
        "class-logic_analyser.html",
        "class-oscilloscope.html",
    }


def test_the_index_links_every_device_mock() -> None:
    html = INDEX.read_text(encoding="utf-8")
    for path in MOCK_FILES:
        assert f"ui-styleguide-mockups/{path.name}" in html, path.name


# --- the logic-analyser mock (the owner spec composition) ----------------------


def _body(html: str) -> str:
    return html.split("</style>", 1)[1]


@pytest.fixture
def analyser_html() -> str:
    return (MOCKS_DIR / "class-logic_analyser.html").read_text(encoding="utf-8")


def test_analyser_carries_the_spec_composition(analyser_html: str) -> None:
    """The spec's head, lease strip, tile set and capture canvas in both
    themes."""
    assert "Veridian LA-32" in analyser_html
    assert "veridian.la32" in analyser_html
    assert "la32-fpga.bin" in analyser_html
    body = _body(analyser_html)
    assert body.count('data-theme="light"') == 1
    assert body.count('data-theme="dark"') == 1
    assert body.count('class="bw-reading"') == 10  # 5 tiles x 2 themes
    assert body.count('aria-label="Logic capture mock"') == 2
    for head in (
        "Device overview", "Controller lease",
        "Staged configuration", "Gateway observations",
    ):
        assert body.count(head) == 2, head


def test_analyser_lane_labels_chips_and_furniture(analyser_html: str) -> None:
    """The canvas's lane label set, bus chips (hex), cursors, trigger
    chip, hatch rects per theme id, and the hidden-lanes note."""
    for label in ("CS#", "SCK", "MOSI", "MISO", "CLK1", "SPI"):
        assert f'class="ln">{label}</text>' in analyser_html, label
    for badge in ("D0", "D1", "D2", "D3", "ch32", "mode 0"):
        assert f">{badge}</text>" in analyser_html, badge
    chips = re.findall(r'class="pl"[^>]*>([^<]*)</text>', analyser_html)
    assert len(chips) == 8, len(chips)  # 4 per theme
    for chip in chips:
        assert re.fullmatch(r"0x[0-9A-F]{2}( / 0x[0-9A-F]{2})*", chip), chip
    assert analyser_html.count('stroke-dasharray="5 4"') == 4  # 2 cursors x 2 themes
    assert analyser_html.count("class=\"cu\">A</text>") == 2
    assert analyser_html.count("class=\"cu\">B</text>") == 2
    assert analyser_html.count('class="tg" text-anchor="middle">trigger</text>') == 2
    assert len(re.findall(r'<rect[^>]*fill="url\(#hatch-l\)"', analyser_html)) >= 2
    assert len(re.findall(r'<rect[^>]*fill="url\(#hatch-d\)"', analyser_html)) >= 2
    assert analyser_html.count("29 lanes hidden") == 2


def test_analyser_side_rail_and_context(analyser_html: str) -> None:
    """The sequencer table, the three buttons (Apply disabled), the
    reason, the message, and the axis readout in both themes."""
    assert analyser_html.count("D0 ↓ (CS#)") == 2
    assert analyser_html.count("Arm capture") == 2
    assert analyser_html.count("sequencer register packing not yet recovered") == 2
    assert analyser_html.count("pre-trigger buffer filling") == 2
    assert analyser_html.count("2048") == 2 and analyser_html.count("2.52 µs") == 2
    body = _body(analyser_html)
    assert body.count('data-variant="primary"') == 2
    assert body.count("disabled") >= 2
    severities = re.findall(r'data-severity="([a-z]+)"', _body(analyser_html))
    assert severities == ["advisory", "neutral", "neutral", "neutral", "success"] * 2


# --- the DC PSU mock ------------------------------------------------------------


@pytest.fixture
def psu_html() -> str:
    return (MOCKS_DIR / "class-dc_psu.html").read_text(encoding="utf-8")


def test_psu_carries_the_operator_surface(psu_html: str) -> None:
    """The Layered Precision surface in both themes: readings, the staged
    control, the plot, the channel table, the severity states."""
    body = _body(psu_html)
    assert body.count('data-theme="light"') == 1
    assert body.count('data-theme="dark"') == 1
    assert psu_html.count("DC supply · PSU-01") == 2
    assert psu_html.count("Operating margin") == 2
    assert psu_html.count("STAGED") == 2
    assert psu_html.count("WARNING") == 2
    assert psu_html.count("Near limit") == 2
    assert psu_html.count("Controls") == 2


def test_psu_consumes_the_shipped_tokens(psu_html: str) -> None:
    """The remap arm: the PSU composition carries no bespoke token
    names — every colour/stroke reference rides the shipped --bw-* set."""
    for bespoke in ("var(--canvas)", "var(--cyan)", "var(--amber)", "var(--green)", "var(--edge)"):
        assert bespoke not in psu_html, bespoke
    assert "--bw-accent" in psu_html and "--bw-warning" in psu_html


# --- the DMM mock (L12 — authored with the reference, not inherited) ------------


@pytest.fixture
def dmm_html() -> str:
    return (MOCKS_DIR / "class-dmm.html").read_text(encoding="utf-8")


def test_dmm_carries_the_operator_surface(dmm_html: str) -> None:
    """The observation-pure surface in both themes: the two reading
    tiles, the range-margin alert, the preset-preview control card, the
    trend, the channel table, the severity states."""
    body = _body(dmm_html)
    assert body.count('data-theme="light"') == 1
    assert body.count('data-theme="dark"') == 1
    assert dmm_html.count("Multimeter · DMM-01") == 2
    assert dmm_html.count("Range margin") == 2
    assert dmm_html.count("PRESET") == 2
    assert dmm_html.count("WARNING") == 2
    assert dmm_html.count("Near limit") == 2
    assert dmm_html.count("Controls") == 2


def test_dmm_consumes_the_shipped_tokens(dmm_html: str) -> None:
    """The remap arm, third instance: the DMM composition carries no
    bespoke token names — every colour/stroke reference rides the
    shipped --bw-* set."""
    for bespoke in ("var(--canvas)", "var(--cyan)", "var(--amber)", "var(--green)", "var(--edge)"):
        assert bespoke not in dmm_html, bespoke
    assert "--bw-accent" in dmm_html and "--bw-warning" in dmm_html


# --- the oscilloscope mock (L13 — authored with the reference, hooks from birth) ---


@pytest.fixture
def oscilloscope_html() -> str:
    return (MOCKS_DIR / "class-oscilloscope.html").read_text(encoding="utf-8")


def test_oscilloscope_carries_the_capture_surface(oscilloscope_html: str) -> None:
    """The acquisition surface in both themes: the waveform canvas with
    both channel traces, the trigger marker and cursor pair idioms, the
    acquisition line, the run panel's three buttons, the partial-capture
    alert."""
    body = _body(oscilloscope_html)
    assert body.count('data-theme="light"') == 1
    assert body.count('data-theme="dark"') == 1
    assert oscilloscope_html.count("Oscilloscope · OSC-01") == 2
    assert oscilloscope_html.count("Partial capture") == 2
    assert oscilloscope_html.count("Acquisition truncated") == 2
    assert oscilloscope_html.count("Acquired") == 2
    assert oscilloscope_html.count("TRIG") == 2
    assert oscilloscope_html.count("Controls") == 2
    for label in ("Arm acquisition", "Abort acquisition", "Force trigger"):
        assert oscilloscope_html.count(label) == 2, label


def test_oscilloscope_consumes_the_shipped_tokens(oscilloscope_html: str) -> None:
    """The remap arm, fourth instance: the oscilloscope composition
    carries no bespoke token names — every colour/stroke reference rides
    the shipped --bw-* set."""
    for bespoke in ("var(--canvas)", "var(--cyan)", "var(--amber)", "var(--green)", "var(--edge)"):
        assert bespoke not in oscilloscope_html, bespoke
    assert "--bw-accent" in oscilloscope_html and "--bw-warning" in oscilloscope_html
