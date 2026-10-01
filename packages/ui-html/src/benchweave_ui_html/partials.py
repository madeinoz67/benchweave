"""Typed partial renderers: dataclass in, HTML string out (UR-01).

Each ``render_*`` function takes one frozen dataclass (``data.py``) and
returns the rendered component. Rendering goes through ``env.ENV`` —
strict-undefined, autoescaped, package-loaded — so a partial called with
missing data raises at render time (a loud red, never a rendered hole).
"""

from __future__ import annotations

from benchweave_ui_html.data import (
    AlertBubbleData,
    ButtonData,
    ConfirmActionData,
    DisabledLabelData,
    ModeBannerData,
    NumericInputData,
    PanelData,
    ReadingData,
    RefusalData,
    RotaryControlData,
    TableData,
)
from benchweave_ui_html.env import ENV


def _render(template: str, data: object) -> str:
    return ENV.get_template(template).render(data=data)


def render_button(data: ButtonData) -> str:
    """§E.1 ``button``: a native ``<button>`` with variant and busy state."""
    return _render("button.j2", data)


def render_numeric_input(data: NumericInputData) -> str:
    """§E.1 ``numeric-input``: labelled number field, bounds, staged help."""
    return _render("numeric-input.j2", data)


def render_rotary_control(data: RotaryControlData) -> str:
    """§E.1 ``rotary-control``: a dial that stages intent (never commands)."""
    return _render("rotary-control.j2", data)


def render_reading(data: ReadingData) -> str:
    """§E.1 ``reading-tile``: value/unit/quality with optional §B.3 state and
    §E.3 set evidence."""
    return _render("reading-tile.j2", data)


def render_alert_bubble(data: AlertBubbleData) -> str:
    """§E.1 ``alert-bubble`` + §B.1 rows: title/message/source, live region,
    dismissal for dismissible severities only."""
    return _render("alert-bubble.j2", data)


def render_panel(data: PanelData) -> str:
    """§E.1 ``panel``: raised/recessed surface with header and body."""
    return _render("panel.j2", data)


def render_data_table(data: TableData) -> str:
    """§E.1 ``data-table``: caption, ``th[scope=col]``, stable row keys."""
    return _render("data-table.j2", data)


def render_mode_banner(data: ModeBannerData) -> str:
    """§E.1 ``mode-banner`` / §D.1: one labelled entry per active mode."""
    return _render("mode-banner.j2", data)


def render_confirm_action(data: ConfirmActionData) -> str:
    """§E.1 ``confirm-action``: the armed confirm-step pattern."""
    return _render("confirm-action.j2", data)


def render_refusal(data: RefusalData) -> str:
    """§C.3: per-code refusal with severity, what-happened, sent status and
    operator action (``UNKNOWN`` for ``no-response`` — decision A06)."""
    return _render("refusal.j2", data)


def render_disabled_label(data: DisabledLabelData) -> str:
    """§C.2: the disabled-reason key and its visible required label text."""
    return _render("disabled-label.j2", data)


def render_icon(key: str) -> str:
    """§F.1: the icon partial for ``key`` (hand-authored geometry from the
    shape descriptions — the lucide names are the reference binding only)."""
    return ENV.get_template(f"icon/{key}.j2").render()


def render_sequence(key: str) -> str:
    """§E.2.2: the dash/symbol SVG fragment for ``key``."""
    return ENV.get_template(f"sequence/{key}.j2").render()
