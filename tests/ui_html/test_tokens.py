"""Token-equality unit tests (UR-04): the cssBlock port, both directions."""

from __future__ import annotations

from benchweave_ui_html.grammar import Row
from benchweave_ui_html.tokens import css_block, theme_colour_mismatches, token_value_mismatches

THEMES = """
:root { --bw-font-ui: system-ui; }
[data-theme="light"] {
  --bw-canvas: #ffffff;
  --bw-text: #1a1a1a;
  --bw-orphan-light: #123456;
}
[data-theme="dark"] {
  --bw-canvas: #0b0e12;
  --bw-text: #e6e8ea;
}
"""

TOKENS = """
:root {
  --bw-space-1: 0.25rem;
  --bw-space-2: 0.5rem;
  --bw-radius-control: 0.25rem;
  --bw-font-ui: system-ui;
  --bw-unrelated: 1px;
}
"""


def colour_rows(*cells: tuple[str, ...]) -> list[Row]:
    rows = []
    for cell in cells:
        key = cell[0].strip("`")
        rows.append(Row(f"a-1-colour-palette::{key}", "a-1-colour-palette", cell))
    return rows


def themes_of(source: str) -> tuple[dict[str, str], dict[str, str]]:
    return css_block(source, 'data-theme="light"'), css_block(source, 'data-theme="dark"')


def test_css_block_extracts_only_selector_matched_declarations() -> None:
    light, dark = themes_of(THEMES)
    assert light == {
        "--bw-canvas": "#ffffff",
        "--bw-text": "#1a1a1a",
        "--bw-orphan-light": "#123456",
    }
    assert dark == {"--bw-canvas": "#0b0e12", "--bw-text": "#e6e8ea"}
    assert css_block(THEMES, ":root") == {"--bw-font-ui": "system-ui"}


def test_theme_colour_mismatches_report_both_directions() -> None:
    rows = colour_rows(
        ("`--bw-canvas`", "`#ffffff`", "`#0b0e12`", "Use"),
        ("`--bw-text`", "`#ffffff`", "`#e6e8ea`", "Use"),
    )
    messages = theme_colour_mismatches(rows, *themes_of(THEMES))
    assert "--bw-text light: contract '#ffffff' vs CSS '#1a1a1a'" in messages
    assert "themes.css light token --bw-orphan-light is not contract-pinned" in messages
    assert len(messages) == 2


def test_theme_colour_equal_values_are_clean() -> None:
    """A CSS pair with every theme-varying colour pinned and equal is clean."""
    themes = """
[data-theme="light"] { --bw-canvas: #ffffff; }
[data-theme="dark"] { --bw-canvas: #0b0e12; }
"""
    rows = colour_rows(("`--bw-canvas`", "`#ffffff`", "`#0b0e12`", "Use"))
    assert theme_colour_mismatches(rows, *themes_of(themes)) == []


def test_token_value_mismatches_report_both_directions() -> None:
    def value_row(token: str, value: str) -> Row:
        return Row(
            f"a-2-spacing-and-layout::{token.strip('`')}",
            "a-2-spacing-and-layout",
            (token, value, "use"),
        )

    rows = [value_row("`--bw-space-1`", "`0.5rem`"), value_row("`--bw-space-2`", "`0.5rem`")]
    messages = token_value_mismatches(rows, css_block(TOKENS, ":root"))
    assert "--bw-space-1: contract '0.5rem' vs tokens.css '0.25rem'" in messages
    assert "tokens.css token --bw-radius-control is not contract-pinned" in messages
    assert "tokens.css token --bw-font-ui is not contract-pinned" in messages
    # --bw-unrelated is outside the pinned families: not a pinning failure.
    assert not any("--bw-unrelated" in message for message in messages)
