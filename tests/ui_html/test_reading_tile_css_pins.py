"""The reading-tile CSS pins (G1b design record §1.4; G1c deferral 1 ruled
to G1b): structural pins over ``ui/src/components/readings/reading-tile.css``
through a module-level path constant (the tokens.py pattern — fail loud if
absent). Three pins:

1. the ordered list of top-level selector blocks equals the pinned order
   (S1 fold-row 5 — same-shape corruption reds on order, not just counts);
2. no glow-carrying declaration in the normal blocks — the base
   ``.bw-reading`` block's box-shadow is exactly the elevation token (a
   glow is a second, ``color-mix``-composed term; SR-B2: normal and success
   readings do not glow) and the limiting block declares no box-shadow at
   all (§B.3: no glow);
3. the limiting block's border colour is exactly ``var(--bw-limiting)``
   (the §B.3 label token).

A mutation arm doctors a copy (reordered blocks + glow term + wrong token)
and reds all three. The pin DIES WITH ``ui/`` at G1e unless re-pointed at
the vendored asset — recorded as a named G1e checklist row in the design
record (§1.4), so the deletion cannot lose it silently.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
READING_TILE_CSS = REPO_ROOT / "ui" / "src" / "components" / "readings" / "reading-tile.css"

_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_BLOCK = re.compile(r"([^{}]*)\{([^{}]*)\}")

#: Pin 1 — the ordered top-level selector blocks (whitespace-normalized,
#: comments stripped). 14 blocks.
PINNED_BLOCK_ORDER: tuple[str, ...] = (
    ".bw-reading",
    '.bw-reading[data-severity="advisory"], .bw-reading[data-severity="warning"], '
    '.bw-reading[data-severity="critical"], .bw-reading[data-severity="trip"]',
    ".bw-reading__header, .bw-reading__severity",
    ".bw-reading__header",
    ".bw-reading__severity",
    ".bw-reading__value",
    ".bw-reading__value small, .bw-reading__quality",
    ".bw-reading__quality",
    ".bw-reading__set",
    '.bw-reading[data-bw-reading-state="limiting"]',
    ".bw-reading__state",
    '.bw-reading[data-bw-stale="true"] .bw-reading__value, '
    '.bw-reading[data-bw-stale="true"] .bw-reading__quality',
    ".bw-reading__stale-marker",
)


def _load() -> str:
    assert READING_TILE_CSS.is_file(), (
        f"reading-tile.css missing at {READING_TILE_CSS} — the CSS pins point at "
        "ui/src/ until G1e's re-point (design record §1.4)"
    )
    return READING_TILE_CSS.read_text(encoding="utf-8")


def _blocks(source: str) -> list[tuple[str, str]]:
    """Top-level (selector, body) pairs in document order, comments stripped,
    selectors whitespace-normalized."""
    cleaned = _COMMENT.sub(" ", source)
    return [
        (" ".join(match.group(1).split()), " ".join(match.group(2).split()))
        for match in _BLOCK.finditer(cleaned)
    ]


def _block(source: str, selector: str) -> tuple[str, str] | None:
    return next(((s, body) for s, body in _blocks(source) if s == selector), None)


def _declaration(body: str, property_name: str) -> str | None:
    match = re.search(rf"(?:^|;)\s*{re.escape(property_name)}\s*:\s*([^;]+)", body)
    return match.group(1).strip() if match else None


def _pin_block_order(source: str) -> list[str]:
    return [selector for selector, _body in _blocks(source)]


def _pin_no_glow_in_normal_blocks(source: str) -> list[str]:
    messages: list[str] = []
    base = _block(source, ".bw-reading")
    assert base is not None, "the base .bw-reading block must exist"
    shadow = _declaration(base[1], "box-shadow")
    if shadow != "var(--bw-shadow-raised)":
        messages.append(
            "the normal .bw-reading block must carry elevation only "
            f"(box-shadow: var(--bw-shadow-raised)); got {shadow!r}"
        )
    limiting = _block(source, '.bw-reading[data-bw-reading-state="limiting"]')
    assert limiting is not None, "the limiting block must exist"
    if _declaration(limiting[1], "box-shadow") is not None:
        messages.append("the limiting block must declare no box-shadow (§B.3: no glow)")
    return messages


def _pin_limiting_border_token(source: str) -> list[str]:
    limiting = _block(source, '.bw-reading[data-bw-reading-state="limiting"]')
    assert limiting is not None, "the limiting block must exist"
    border = _declaration(limiting[1], "border-color")
    if border != "var(--bw-limiting)":
        return [f"the limiting border must be var(--bw-limiting); got {border!r}"]
    return []


def test_pin_block_order() -> None:
    assert _pin_block_order(_load()) == list(PINNED_BLOCK_ORDER)


def test_pin_no_glow_in_normal_blocks() -> None:
    assert _pin_no_glow_in_normal_blocks(_load()) == []


def test_pin_limiting_border_token() -> None:
    assert _pin_limiting_border_token(_load()) == []


def test_doctored_css_reds_all_three_pins() -> None:
    """The mutation arm: a doctored copy (two blocks swapped, a glow term
    added to the base block, the limiting border re-pointed at a severity
    hue) reds every pin — assertions that stay green under their own
    mutation do not discriminate."""
    lines = _load().splitlines(keepends=True)
    # Swap the .bw-reading__set block with the limiting block (order pin).
    set_index = next(i for i, line in enumerate(lines) if line.startswith(".bw-reading__set"))
    limiting_index = next(
        i for i, line in enumerate(lines)
        if line.startswith('.bw-reading[data-bw-reading-state="limiting"]')
    )
    lines[set_index], lines[limiting_index] = lines[limiting_index], lines[set_index]
    doctored = "".join(lines)
    # Add the glow term to the base block and re-point the limiting border.
    doctored = doctored.replace(
        "box-shadow: var(--bw-shadow-raised);\n  color: var(--bw-text);",
        "box-shadow: var(--bw-shadow-raised), 0 0 1.5rem color-mix("
        "in srgb, var(--bw-trip), transparent 68%);\n  color: var(--bw-text);",
        1,
    )
    doctored = doctored.replace(
        "border-color: var(--bw-limiting);", "border-color: var(--bw-trip);", 1
    )
    assert _pin_block_order(doctored) != list(PINNED_BLOCK_ORDER)
    assert _pin_no_glow_in_normal_blocks(doctored) != []
    assert _pin_limiting_border_token(doctored) != []
