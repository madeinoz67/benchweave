"""The template-packaging guard (G1b design record §1.1 / risk 4 / O4):
the templates ship under ``src/benchweave_ui_html/templates`` so the
existing ``[tool.hatch.build.targets.wheel] packages`` config carries them;
this guard pins the directory's CONTENTS through ``importlib.resources``
(the same resolution a wheel install uses) and loads every template through
the real environment — a template that parses from source but is missing
from the package reds here, not at a host's first render. The wheel-build
half of O4 is the acceptance-run build check (record §6); this file is the
CI-verifiable guard.
"""

from __future__ import annotations

from importlib.resources import files

COMPONENT_TEMPLATES = frozenset(
    {
        "alert-bubble.j2",
        "button.j2",
        "confirm-action.j2",
        "data-table.j2",
        "digital-lanes.j2",
        "disabled-label.j2",
        "engineering-plot.j2",
        "mode-banner.j2",
        "numeric-input.j2",
        "panel.j2",
        "reading-tile.j2",
        "refusal.j2",
        "rotary-control.j2",
    }
)
ICON_TEMPLATES = frozenset(
    f"{key}.j2"
    for key in (
        "neutral", "success", "advisory", "warning", "critical", "trip",
        "busy", "hidden", "staged", "limiting",
    )
)
SEQUENCE_TEMPLATES = frozenset(
    f"{key}.j2"
    for key in ("dash-1", "dash-2") + tuple(f"symbol-{n}" for n in range(1, 9))
)


def _template_names() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    root = files("benchweave_ui_html").joinpath("templates")
    components = frozenset(
        resource.name for resource in root.iterdir() if resource.name.endswith(".j2")
    )
    icons = frozenset(
        resource.name
        for resource in root.joinpath("icon").iterdir()
        if resource.name.endswith(".j2")
    )
    sequences = frozenset(
        resource.name
        for resource in root.joinpath("sequence").iterdir()
        if resource.name.endswith(".j2")
    )
    return components, icons, sequences


def test_template_directory_contents_are_pinned() -> None:
    components, icons, sequences = _template_names()
    assert components == COMPONENT_TEMPLATES, sorted(components ^ COMPONENT_TEMPLATES)
    assert icons == ICON_TEMPLATES, sorted(icons ^ ICON_TEMPLATES)
    assert sequences == SEQUENCE_TEMPLATES, sorted(sequences ^ SEQUENCE_TEMPLATES)


def test_every_template_loads_through_the_real_environment() -> None:
    from benchweave_ui_html.env import ENV

    components, icons, sequences = _template_names()
    for name in sorted(components):
        ENV.get_template(name)
    for name in sorted(icons):
        ENV.get_template(f"icon/{name}")
    for name in sorted(sequences):
        ENV.get_template(f"sequence/{name}")


def test_strict_undefined_reds_a_partial_called_with_missing_data() -> None:
    """UR-01's loud-red property: a partial rendered with missing data
    raises at render time — never a silent hole in the output."""
    import pytest
    from benchweave_ui_html.env import ENV
    from jinja2 import UndefinedError

    template = ENV.get_template("button.j2")
    with pytest.raises(UndefinedError):
        template.render()  # no `data` at all
