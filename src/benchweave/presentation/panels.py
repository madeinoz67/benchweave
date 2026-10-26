"""The gateway-owned panel registry (L4 capability c; design record
2026-10-15 §3).

``PANELS`` maps panel ids to GATEWAY functions — registration is a code
act, deliberately (the A05 trusted-extension posture): panels are
executable host surface and their admission is a gateway release, not a
registry-record act. ``SUPPORTED_PANELS`` derives from the registry
(``frozenset(PANELS)``) and the validator consumes the derived value, so
registry/declaration drift is unrepresentable — a panel is servable the
moment it exists, and a manifest page can never validate against a panel
the registry lacks (B7's mechanical arm).

No plugin code ever executes (A05/NFR-S9 unchanged; the validator's
"never imports or executes that panel" rule stays true: the registry maps
ids to gateway functions over composed page DATA).

The registry cites each panel's corpus pin (the family reference version
it renders) so the panel and the corpus bytes it interprets move in one
reviewable unit (R4): a pin mismatch renders the honest version note,
never the composition.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from markupsafe import Markup, escape

from benchweave.presentation.classref import family_version
from benchweave.vendoring import corpus_root

_NO_AUTHORITY = "no-authority"
_NO_AUTHORITY_LABEL = "No lease or policy authority"


@dataclass(frozen=True)
class PanelContext:
    """The composed page data a panel renderer receives (never plugin
    code): the page's bindings and the catalogue targets they resolve."""

    panel_id: str
    page_id: str
    title: str
    bindings: tuple[str, ...]
    bindings_index: Mapping[str, Mapping[str, Any]]
    targets: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class Panel:
    """One registered panel: the id the manifest's ``panel_id`` names, the
    title, the corpus version pin, and the gateway function that renders
    the composition from composed page data."""

    panel_id: str
    title: str
    corpus_pin: str
    render: Callable[[PanelContext], Markup]


def _render_classref_logic_analyser(context: PanelContext) -> Markup:
    """The host-owned rendering of the class reference's capture page —
    lane rails from the bound dataset's variables, the run group's
    disabled §E.1 buttons (the G2 read-only scope line: no authority on
    the device page), grouped §E.1 panels per binding kind."""
    lane_rows: list[str] = []
    run_buttons: list[str] = []
    for binding_id in context.bindings:
        binding = context.bindings_index.get(binding_id, {})
        target = context.targets.get(str(binding.get("target_id", "")), {})
        kind = str(binding.get("kind", ""))
        if kind == "dataset":
            for variable in target.get("variables", []):
                if str(variable.get("axis_role", "")) == "x":
                    continue
                lane_rows.append(
                    f'<li data-bw-lane-kind="channel">{escape(str(variable.get("id", "")))}</li>'
                )
        elif kind == "procedure":
            from benchweave_ui_html.data import ButtonData
            from benchweave_ui_html.partials import render_button

            run_buttons.append(
                render_button(
                    ButtonData(
                        label=str(binding_id),
                        variant="primary",
                        disabled_reason=_NO_AUTHORITY,
                        disabled_label=_NO_AUTHORITY_LABEL,
                    )
                )
            )
    sections: list[str] = []
    if lane_rows:
        sections.append(
            f'<section class="bw-panel bw-presentation__section" '
            f'data-bw-section-id="{context.page_id}-lanes" '
            f'data-surface="raised" style="grid-column: span 12">'
            f"<h4>Lanes</h4>"
            f'<ul class="bw-lane-skeleton" data-bw-lane-skeleton>'
            f'{"".join(lane_rows)}</ul>'
            f'<p class="bw-plot-note">no plotted data</p></section>'
        )
    if run_buttons:
        sections.append(
            f'<section class="bw-panel bw-presentation__section" '
            f'data-bw-section-id="{context.page_id}-run" '
            f'data-surface="raised" style="grid-column: span 12">'
            f"<h4>Run</h4>{''.join(run_buttons)}</section>"
        )
    body = "".join(sections) or (
        '<p class="bw-panel-note">No bound targets to compose.</p>'
    )
    return Markup(  # noqa: S704 - escape()d rows and fixed literals only
        f'<div class="bw-panel-host" data-bw-panel="{escape(context.panel_id)}">'
        f"{body}</div>"
    )


# Registration id note (design deviation, disclosed): the design's §3
# example id "benchweave/classref-logic-analyser/0.1.0" carries TWO
# slashes, but the ui-manifest schema's own panel_id pattern (the shape
# the design itself names as binding) admits exactly one — the two-slash
# string is schema-refused on any class_panel page
# (test_panel_id_pattern_conflict documents it). The registry uses the
# pattern-conforming form with the same gateway-owned namespace prefix.
PANELS: Mapping[str, Panel] = {
    "benchweave.classref-logic-analyser/0.1.0": Panel(
        panel_id="benchweave.classref-logic-analyser/0.1.0",
        title="Logic analyser class panel",
        corpus_pin="0.5.0",
        render=_render_classref_logic_analyser,
    ),
}

#: The validator consumes the DERIVED set (frozenset(PANELS)); the drift
#: shape between registry and declaration is unrepresentable by
#: construction (B7's mechanical arm).
SUPPORTED_PANELS: frozenset[str] = frozenset(PANELS)


def served_family_version(corpus: Path) -> str:
    """The served family version (the registry's pin guard reads it)."""
    return family_version(corpus)


def panel_markup(
    panel_id: str,
    context: PanelContext,
    *,
    corpus_path: Path | None,
) -> Markup | None:
    """One registered panel's composition, or ``None`` for an
    unregistered id (the validator's own finding renders instead).

    The corpus-pin guard (R4): the panel's pin must name the family
    version the gateway actually serves — a mismatch renders the honest
    version note, never the composition, because a panel rendering
    against reference bytes it was not built for is the skew the pin
    exists to prevent."""
    panel = PANELS.get(panel_id)
    if panel is None:
        return None
    # The pin guard has no exemption arm: a None corpus_path reads the
    # SERVED corpus (corpus_root()) — a call that skipped the check would
    # render the composition against reference bytes whose version it
    # never verified (R4's skew, via the None arm).
    served = served_family_version(
        corpus_path if corpus_path is not None else corpus_root()
    )
    if served != panel.corpus_pin:
        return Markup(  # noqa: S704 - fixed literals + derived strings
            f'<div class="bw-panel-host" data-bw-panel-version-skew>'
            f"<p>Panel {escape(panel.panel_id)} renders class-reference "
            f"{escape(panel.corpus_pin)}; this gateway serves {escape(served)}. "
            f"Unavailable until the panel and the corpus move together.</p></div>"
        )
    return panel.render(context)
