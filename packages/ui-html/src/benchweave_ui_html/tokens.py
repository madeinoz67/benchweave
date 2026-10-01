"""CSS custom-property parsing and both-directions token equality (UR-04).

``css_block`` is the verbatim port of ``cssBlock`` from
``ui/src/contract-coverage.test.ts``: regex over ``selector { … }`` blocks
whose selector contains the given fragment, extracting ``--name: value;``
declarations. Both directions × both themes (design record §6):

- contract → CSS: every §A.1 row's Light/Dark values equal the custom
  property's value in the matching theme block; §A.2-§A.4 values equal the
  ``:root`` block's;
- CSS → contract: every ``--bw-*`` custom property declared in the pinned
  blocks has a contract row with the same value — an extra CSS property with
  no row FAILS (the "extra unpinned token" class, enforced mechanically).

G1a reads the two CSS files by path and asserts values only; the inventory
hashing and serve-time verification over the same asset directory are the
named deferral D3 (UR-10).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from benchweave_ui_html.grammar import Row, literal

_BLOCK = re.compile(r"([^{}]*)\{([^{}]*)\}")
_PROPERTY = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")
_ROOT_FAMILIES = re.compile(r"^--bw-(space|radius|font)-")


def css_block(source: str, selector_fragment: str) -> dict[str, str]:
    """Extract ``--name: value`` custom properties from every rule block whose
    selector contains ``selector_fragment`` (the ``cssBlock`` shape)."""
    properties: dict[str, str] = {}
    for match in _BLOCK.finditer(source):
        if selector_fragment not in match.group(1):
            continue
        for declaration in _PROPERTY.finditer(match.group(2)):
            properties[f"--{declaration.group(1)}"] = declaration.group(2).strip()
    return properties


def theme_colour_mismatches(
    rows: Sequence[Row], light: dict[str, str], dark: dict[str, str]
) -> list[str]:
    """§A.1 both directions: each row's Light and Dark cells vs the theme
    blocks, and every theme-varying colour pinned by a row."""
    messages: list[str] = []
    pinned: set[str] = set()
    for row in rows:
        token = literal(row.cells[0])
        contract_light = literal(row.cells[1])
        contract_dark = literal(row.cells[2])
        pinned.add(token)
        if light.get(token) != contract_light:
            got = light.get(token)
            messages.append(f"{token} light: contract {contract_light!r} vs CSS {got!r}")
        if dark.get(token) != contract_dark:
            got = dark.get(token)
            messages.append(f"{token} dark: contract {contract_dark!r} vs CSS {got!r}")
    for token in light:
        if token not in pinned:
            messages.append(f"themes.css light token {token} is not contract-pinned")
    for token in dark:
        if token not in pinned:
            messages.append(f"themes.css dark token {token} is not contract-pinned")
    return messages


def token_value_mismatches(rows: Sequence[Row], root: dict[str, str]) -> list[str]:
    """§A.2-§A.4 both directions against the tokens.css ``:root`` block."""
    messages: list[str] = []
    pinned: set[str] = set()
    for row in rows:
        token = literal(row.cells[0])
        value = literal(row.cells[1])
        pinned.add(token)
        if root.get(token) != value:
            messages.append(f"{token}: contract {value!r} vs tokens.css {root.get(token)!r}")
    for token in root:
        in_pinned_family = _ROOT_FAMILIES.match(token) or token in (
            "--bw-font-ui",
            "--bw-font-data",
        )
        if in_pinned_family and token not in pinned:
            messages.append(f"tokens.css token {token} is not contract-pinned")
    return messages
