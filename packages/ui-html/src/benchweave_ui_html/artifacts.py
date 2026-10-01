"""The canonical artifacts: one registered instance per contract row (G1b).

G1a landed the fail-closed gate — ``registry.evaluate_row`` refuses an
unregistered row with ``no canonical artifact for <row-id>``. This module is
the positive half: each artifact owns one row-id (``<table-slug>::<key>``)
and its ``satisfies(row)`` returns the unsatisfied item descriptions drawn
from THE ROW'S OWN CELLS (the row is the data — fixture-text drift from the
contract is structurally impossible for every family whose row cells carry
the pinned values).

``ensure_registered()`` is called by the harness plugin after the parse and
before the orphan check, so the orphan check polices the registrations it is
about to consume. It is idempotent by sentinel: once the sentinel row-id
``e-1-components::button`` is present the function no-ops (duplicate
registration is refused by ``ArtifactRegistry.register``), which also keeps
G1a's prelude-based meta-acceptance controls working — a prelude that
registered artifacts before collection suppresses auto-registration rather
than colliding with it.

Import direction keeps UR-11: this module imports ``fixtures`` →
``partials`` → ``env`` → jinja2 (declared runtime deps) and NEVER pytest —
only the pytest11 plugin imports this module.

Scope (G1b design record §1.2): 158 of the 168 rows. The ten ``rule_proof``
behaviour rows — §B.2 SR-B1/B2/B3, §B.4 ST-1..ST-4, §C.1 R-ENERGISE-1/
R-DEENERGISE-1/R-PROTECT-1 — are named deferrals to the G1d compositions
slice; they stay red with the honest ``no canonical artifact`` message.
"""

from __future__ import annotations

from collections.abc import Callable

from benchweave_ui_html import fixtures, registry
from benchweave_ui_html.assertions import RenderedComponent
from benchweave_ui_html.grammar import Row, literal
from benchweave_ui_html.items import parse_attribute_cell, split_items
from benchweave_ui_html.partials import render_button

#: The idempotence sentinel: the first row the §E.1 family registers.
SENTINEL_ROW_ID = "e-1-components::button"

#: The §E.1 column indexes (Component | Root | attrs | roles | hooks | text | Notes).
_E1_ROOT, _E1_ATTRS, _E1_ROLES, _E1_HOOKS, _E1_TEXT = 1, 2, 3, 4, 5


class ComponentRenderArtifact:
    """§E.1 ``component_render``: render the canonical fixture, assert the
    row's own attribute/role/class-hook/required-text items over it."""

    kind = "component_render"

    def __init__(self, component_key: str, render: Callable[[], str]) -> None:
        self.component_key = component_key
        self._render = render

    def satisfies(self, row: Row) -> list[str]:
        try:
            html = self._render()
        except Exception as exc:  # fail closed; the message carries the cause
            return [f"{self.component_key}: render failed: {exc}"]
        rendered = RenderedComponent(html)
        return rendered.unsatisfied(
            root=literal(_cell(row, _E1_ROOT)),
            attributes=parse_attribute_cell(_cell(row, _E1_ATTRS)),
            roles=split_items(_cell(row, _E1_ROLES)),
            class_hooks=split_items(_cell(row, _E1_HOOKS)),
            required_texts=split_items(_cell(row, _E1_TEXT)),
        )


def _cell(row: Row, index: int) -> str:
    return row.cells[index] if index < len(row.cells) else "—"


def button_artifact() -> ComponentRenderArtifact:
    """The §E.1 button artifact over the canonical fixture."""
    return ComponentRenderArtifact("button", lambda: render_button(fixtures.button()))


#: Every row-id G1b registers, by table (the explicit scope split; the meta
#: acceptance pins set-equality against the manifest-derived expectation).
G1B_ROW_IDS: frozenset[str] = frozenset({SENTINEL_ROW_ID})


def ensure_registered() -> None:
    """Register every G1b artifact exactly once (sentinel-idempotent)."""
    if SENTINEL_ROW_ID in registry.REGISTRY:
        return
    registry.REGISTRY.register(SENTINEL_ROW_ID, button_artifact())


__all__ = [
    "ComponentRenderArtifact",
    "G1B_ROW_IDS",
    "SENTINEL_ROW_ID",
    "button_artifact",
    "ensure_registered",
]
