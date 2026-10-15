"""The §E.1 input trio (L5, PR-1 — gateway issue #463): the renderer half.

Three partials — ``text-input``, ``select``, ``boolean-input`` — with the
design record's exact hooks (``bw-text``/``bw-select``/``bw-boolean``) and the
trio's one staging sentence as required text. Two honesty arms ride the
renderer itself: the text-input's bounds render ONLY when the caller supplies
them (A02 bound honesty — an absent bound renders the absent attribute, never
an invented limit; the ABSENCE literal is asserted, design record R6's
renderer-level falsifier) and the select's const / single-option shape
renders the read-only fixed display, never an editable offer.
"""

from __future__ import annotations

from benchweave_ui_html import fixtures, partials
from benchweave_ui_html.data import BooleanInputData, SelectData, TextInputData


def test_text_input_canonical_renders_the_row_shape() -> None:
    """The canonical text-input: div-rooted, labelled via for, type=text
    field, the staged sentence, the bw-text hook family — and NO bounds
    (the canonical fixture declares none; the ABSENCE literal is the A02
    arm)."""
    html = partials.render_text_input(fixtures.text_input())
    assert '<div class="bw-text">' in html
    assert 'class="bw-text__label"' in html
    assert 'class="bw-text__field"' in html
    assert 'class="bw-text__help"' in html
    assert 'type="text"' in html
    assert "for=" in html
    assert "aria-describedby=" in html
    assert "Staged value; use Apply to request the change" in html
    # A02 bound honesty: the canonical fixture declares no bounds, so the
    # bound ATTRIBUTES are absent — never an invented limit.
    assert "minlength" not in html
    assert "maxlength" not in html
    assert "min=" not in html
    assert "max=" not in html


def test_text_input_declared_bounds_render_the_declared_attributes() -> None:
    """Bounds render only when the effective schema declares them — a
    declared bound renders its own attribute with its own value."""
    data = TextInputData(
        label="Site label",
        value="Bench 1",
        minlength="1",
        maxlength="64",
    )
    html = partials.render_text_input(data)
    assert 'minlength="1"' in html
    assert 'maxlength="64"' in html
    # Still no numeric-control bounds: the field stays a text control.
    assert "min=" not in html
    assert "max=" not in html


def test_select_canonical_renders_the_enum_field() -> None:
    """The canonical select: div-rooted, labelled via for, one option per
    enum value with the declared value selected, the staged sentence, the
    bw-select hook family."""
    html = partials.render_select(fixtures.select())
    assert '<div class="bw-select">' in html
    assert 'class="bw-select__label"' in html
    assert 'class="bw-select__field"' in html
    assert "for=" in html
    assert "aria-describedby=" in html
    assert "Staged value; use Apply to request the change" in html
    assert '<option value="auto"' in html
    assert '<option value="normal"' in html
    assert '<option value="single"' in html
    # The declared value is the selected offer.
    assert '<option value="auto" selected' in html


def test_select_const_shape_renders_the_read_only_fixed_display() -> None:
    """A const (or single-option enum) renders the read-only fixed display,
    never an editable offer: no <select> element, no staged sentence (a
    fixed value is not staged), the value visible in the field hook."""
    data = SelectData(label="Fixed mode", options=("single",), value="single")
    html = partials.render_select(data)
    assert '<div class="bw-select">' in html
    assert "bw-select__label" in html
    assert "bw-select__field" in html
    assert "<select" not in html
    assert "<option" not in html
    assert "single" in html
    assert "Staged value; use Apply to request the change" not in html


def test_boolean_input_renders_the_switch_shape() -> None:
    """The boolean-input: div-rooted, the control element carries
    role=switch + aria-checked, labelled via for, the staged sentence, the
    bw-boolean hook family; the aria-checked value follows the data in both
    arms."""
    html = partials.render_boolean(fixtures.boolean_input())
    assert '<div class="bw-boolean">' in html
    assert 'class="bw-boolean__label"' in html
    assert 'class="bw-boolean__control"' in html
    assert 'role="switch"' in html
    assert 'aria-checked="true"' in html
    assert "for=" in html
    assert "Staged value; use Apply to request the change" in html

    off = partials.render_boolean(
        BooleanInputData(label="Holdoff enabled", checked=False)
    )
    assert 'aria-checked="false"' in off
    assert 'aria-checked="true"' not in off
