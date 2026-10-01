"""Typed partial renderers: dataclass in, HTML string out (UR-01).

Each ``render_*`` function takes one frozen dataclass (``data.py``) and
returns the rendered component. Rendering goes through ``env.ENV`` —
strict-undefined, autoescaped, package-loaded — so a partial called with
missing data raises at render time (a loud red, never a rendered hole).
"""

from __future__ import annotations

from benchweave_ui_html.data import ButtonData
from benchweave_ui_html.env import ENV


def render_button(data: ButtonData) -> str:
    """§E.1 ``button``: a native ``<button>`` with variant and busy state."""
    return ENV.get_template("button.j2").render(data=data)
