"""The canonical artifacts: one registered instance per contract row (G1b).

G1a landed the fail-closed gate — ``registry.evaluate_row`` refuses an
unregistered row with ``no canonical artifact for <row-id>``. This module is
the positive half: each artifact owns one row-id (``<table-slug>::<key>``)
and its ``satisfies(row)`` returns the unsatisfied item descriptions drawn
from THE ROW'S OWN CELLS — the row is the data, so fixture-text drift from
the contract is structurally impossible wherever the row cells carry the
pinned values (§C.2 labels, §C.3 refusals, §B.1 severities, §D.1 modes).

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
slice; they stay red with the honest ``no canonical artifact`` message
(satisfying them here with single-fixture structure checks would be
prose-laundering, which the acceptance rule kills).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

from benchweave_ui_html import fixtures, partials, registry
from benchweave_ui_html.assertions import RenderedComponent
from benchweave_ui_html.data import (
    AlertBubbleData,
    DisabledLabelData,
    LiveRegion,
    RefusalData,
    Severity,
)
from benchweave_ui_html.grammar import Row, literal
from benchweave_ui_html.items import (
    parse_attribute_cell,
    parse_attribute_item,
    split_items,
)
from benchweave_ui_html.manifest import MANIFEST
from benchweave_ui_html.tokens import css_block, theme_colour_mismatches, token_value_mismatches

#: The idempotence sentinel: the first row the §E.1 family registers.
SENTINEL_ROW_ID = "e-1-components::button"

#: The three behaviour-rule tables whose rows are G1d deferrals (record §1.2).
DEFERRED_SLUGS = frozenset({"b-2-state-rules", "b-4-staleness", "c-1-safety-rules"})

#: §E.1 components whose renderers land with the plot (slice 3) and lanes
#: (slice 4) commits. Unknown beyond these: a §E.1 row with no renderer
#: raises at collection — a new component row can never silently skip.
_PENDING_COMPONENTS = frozenset({"engineering-plot", "digital-lanes"})

#: The contract's executable token mirror (G1a deferral D3 keeps the path on
#: ``ui/src/styles/`` until G1e's re-point). The token rows are live where
#: the gate runs from the repository root; a missing asset reds loudly.
_STYLES_DIR = Path("ui") / "src" / "styles"
THEMES_CSS = _STYLES_DIR / "themes.css"
TOKENS_CSS = _STYLES_DIR / "tokens.css"

#: Geometry element names for icon/sequence structure assertions.
_GEOMETRY_TAGS = frozenset(
    {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect"}
)

_KEYS_BY_SLUG: dict[str, tuple[str, ...]] = {table.slug: table.keys for table in MANIFEST}

#: The §E.1 column indexes (Component | Root | attrs | roles | hooks | text | Notes).
_E1_ROOT, _E1_ATTRS, _E1_ROLES, _E1_HOOKS, _E1_TEXT = 1, 2, 3, 4, 5


def _cell(row: Row, index: int) -> str:
    return row.cells[index] if index < len(row.cells) else "—"


def _render_or_fail(render: Callable[[], str], owner: str) -> tuple[str | None, str | None]:
    try:
        return render(), None
    except Exception as exc:  # fail closed; the message carries the cause
        return None, f"{owner}: render failed: {exc}"


# ---------------------------------------------------------------------------
# §E.1 component_render


class ComponentRenderArtifact:
    """§E.1 ``component_render``: render the canonical fixture, assert the
    row's own attribute/role/class-hook/required-text items over it."""

    kind = "component_render"

    def __init__(self, component_key: str, render: Callable[[], str]) -> None:
        self.component_key = component_key
        self._render = render

    def satisfies(self, row: Row) -> list[str]:
        html, failure = _render_or_fail(self._render, self.component_key)
        if failure is not None or html is None:
            return [failure] if failure else ["render produced nothing"]
        return RenderedComponent(html).unsatisfied(
            root=literal(_cell(row, _E1_ROOT)),
            attributes=parse_attribute_cell(_cell(row, _E1_ATTRS)),
            roles=split_items(_cell(row, _E1_ROLES)),
            class_hooks=split_items(_cell(row, _E1_HOOKS)),
            required_texts=split_items(_cell(row, _E1_TEXT)),
        )


_COMPONENT_RENDERERS: dict[str, Callable[[], str]] = {
    "button": lambda: partials.render_button(fixtures.button()),
    "numeric-input": lambda: partials.render_numeric_input(fixtures.numeric_input()),
    "rotary-control": lambda: partials.render_rotary_control(fixtures.rotary_control()),
    "reading-tile": lambda: partials.render_reading(fixtures.reading()),
    "alert-bubble": lambda: partials.render_alert_bubble(fixtures.alert_bubble()),
    "data-table": lambda: partials.render_data_table(fixtures.data_table()),
    "panel": lambda: partials.render_panel(fixtures.panel()),
    "mode-banner": lambda: partials.render_mode_banner(fixtures.mode_banner()),
    "confirm-action": lambda: partials.render_confirm_action(fixtures.confirm_action()),
}


def _component_factory(key: str) -> ComponentRenderArtifact:
    renderer = _COMPONENT_RENDERERS.get(key)
    if renderer is None:
        if key in _PENDING_COMPONENTS:
            raise NotImplementedError(
                f"§E.1 component {key!r} renders with a later G1b slice"
            )
        raise KeyError(f"§E.1 component {key!r} has no canonical renderer")
    return ComponentRenderArtifact(key, renderer)


def button_artifact() -> ComponentRenderArtifact:
    """The §E.1 button artifact over the canonical fixture (the one-artifact
    control's registrable unit)."""
    return ComponentRenderArtifact("button", _COMPONENT_RENDERERS["button"])


# ---------------------------------------------------------------------------
# §C.3 refusal_render — the row's own cells are the fixture


class RefusalRenderArtifact:
    """§C.3: the refusal partial rendered from the row's own cells; the
    structure (severity attribute, sent-status attribute, what-happened and
    operator-action elements) is asserted, so a renderer that drops or
    swaps a field reds its row. ``no-response`` renders ``UNKNOWN`` (A06)."""

    kind = "refusal_render"

    def __init__(self, code: str) -> None:
        self.code = code

    def satisfies(self, row: Row) -> list[str]:
        data = RefusalData(
            code=literal(row.cells[0]),
            severity=cast(Severity, literal(row.cells[1])),
            what_happened=literal(row.cells[2]),
            sent_status=literal(row.cells[3]),
            operator_action=literal(row.cells[4]),
        )
        html, failure = _render_or_fail(
            lambda: partials.render_refusal(data), f"refusal:{self.code}"
        )
        if failure is not None or html is None:
            return [failure] if failure else ["render produced nothing"]
        rendered = RenderedComponent(html)
        messages: list[str] = []
        if rendered.root_tag != "aside":
            messages.append(f"root element: expected <aside>, got <{rendered.root_tag}>")
        if not any(
            element.attrs.get("data-bw-refusal-code") == data.code
            for element in rendered.elements
        ):
            messages.append(f"data-bw-refusal-code={data.code} not rendered")
        if not any(
            element.attrs.get("data-severity") == data.severity
            for element in rendered.elements
        ):
            messages.append(f"severity {data.severity} not rendered on data-severity")
        if data.what_happened not in rendered.texts_of_elements(
            class_hook="bw-refusal__what"
        ):
            messages.append("what-happened text not rendered in its element")
        if not any(
            element.attrs.get("data-bw-sent-status") == data.sent_status
            for element in rendered.elements
        ):
            messages.append(f"sent status {data.sent_status} not rendered")
        if data.operator_action not in rendered.texts_of_elements(
            class_hook="bw-refusal__action"
        ):
            messages.append("operator-action text not rendered in its element")
        return messages


# ---------------------------------------------------------------------------
# §C.2 label_render — the row's own cells are the fixture


class LabelRenderArtifact:
    """§C.2: ``data-bw-disabled-reason="<key>"`` plus the required label text
    visible (element text, never aria-only). The ``device-state`` row's
    template parameter ``{state}`` is substituted with the canonical example
    parameter from the row's own Parameter cell (``idle``)."""

    kind = "label_render"

    def __init__(self, reason_key: str) -> None:
        self.reason_key = reason_key

    def _expected_label(self, row: Row) -> str:
        label = literal(row.cells[1])
        parameter = re.search(r"`([^`]+)`", row.cells[2])
        if parameter and "{state}" in label:
            return label.replace("{state}", parameter.group(1))
        return label

    def satisfies(self, row: Row) -> list[str]:
        data = DisabledLabelData(reason=literal(row.cells[0]), label=self._expected_label(row))
        html, failure = _render_or_fail(
            lambda: partials.render_disabled_label(data), f"label:{self.reason_key}"
        )
        if failure is not None or html is None:
            return [failure] if failure else ["render produced nothing"]
        rendered = RenderedComponent(html)
        messages: list[str] = []
        if not any(
            element.attrs.get("data-bw-disabled-reason") == data.reason
            for element in rendered.elements
        ):
            messages.append(f"data-bw-disabled-reason={data.reason} not rendered")
        visible = rendered.texts_of_elements_with_attribute("data-bw-disabled-label")
        if data.label not in visible:
            messages.append(
                f"required label text {data.label!r} not visible beside the control "
                "(data-bw-disabled-label element text)"
            )
        return messages


# ---------------------------------------------------------------------------
# §B.1 severity_row — the row's own cells drive the fixture


class SeverityRowArtifact:
    """§B.1: the alert-bubble canonical fixture per severity —
    ``data-severity``, the live region per the row's Live-region cell
    (``alert`` for critical/trip, else ``status``), and the dismiss
    affordance present iff the Dismissal class is ``dismissible``. The
    live region is an explicit ``role`` attribute (``alert`` is outside the
    G1a resolver's pinned role set by design — see assertions.py)."""

    kind = "severity_row"

    def __init__(self, severity_key: str) -> None:
        self.severity_key = severity_key

    def satisfies(self, row: Row) -> list[str]:
        severity = literal(row.cells[0])
        meaning = literal(row.cells[1])
        dismissal = literal(row.cells[2])
        live_region = literal(row.cells[3])
        data = AlertBubbleData(
            severity=cast(Severity, severity),
            title=severity,
            message=meaning,
            live_region=cast(LiveRegion, live_region),
            dismissible=dismissal == "dismissible",
        )
        html, failure = _render_or_fail(
            lambda: partials.render_alert_bubble(data), f"severity:{self.severity_key}"
        )
        if failure is not None or html is None:
            return [failure] if failure else ["render produced nothing"]
        rendered = RenderedComponent(html)
        messages: list[str] = []
        if rendered.root_tag != "aside":
            messages.append(f"root element: expected <aside>, got <{rendered.root_tag}>")
        if not any(
            element.attrs.get("data-severity") == severity for element in rendered.elements
        ):
            messages.append(f"data-severity={severity} not rendered")
        if not rendered.explicit_role(live_region):
            messages.append(f"live region role={live_region} not rendered")
        has_dismiss = any(
            element.attrs.get("aria-label") == "Dismiss" for element in rendered.elements
        )
        if dismissal == "dismissible" and not has_dismiss:
            messages.append("dismiss affordance missing for a dismissible severity")
        if dismissal != "dismissible" and has_dismiss:
            messages.append(
                f"dismiss affordance rendered for dismissal class {dismissal!r}"
            )
        if meaning not in rendered.text_content:
            messages.append("the severity's Meaning cell text is not rendered")
        return messages


# ---------------------------------------------------------------------------
# §D.1 mode_row


class ModeRowArtifact:
    """§D.1: the all-modes banner carries an entry with
    ``data-bw-mode="<mode>"`` whose own element text is the row's fixed
    wording, verbatim."""

    kind = "mode_row"

    def __init__(self, mode_key: str) -> None:
        self.mode_key = mode_key

    def satisfies(self, row: Row) -> list[str]:
        mode = literal(row.cells[0])
        wording = literal(row.cells[1])
        html, failure = _render_or_fail(
            lambda: partials.render_mode_banner(fixtures.mode_banner()), f"mode:{self.mode_key}"
        )
        if failure is not None or html is None:
            return [failure] if failure else ["render produced nothing"]
        rendered = RenderedComponent(html)
        messages: list[str] = []
        if rendered.root_tag != "section":
            messages.append(f"root element: expected <section>, got <{rendered.root_tag}>")
        entries = rendered.texts_of_elements(attribute=("data-bw-mode", mode))
        if not entries:
            messages.append(f"no banner entry carries data-bw-mode={mode}")
        elif wording not in entries:
            messages.append(
                f"entry data-bw-mode={mode} does not carry the fixed wording {wording!r}"
            )
        return messages


# ---------------------------------------------------------------------------
# §B.3 state_row


class StateRowArtifact:
    """§B.3 ``limiting``: the canonical reading tile carries
    ``data-bw-reading-state="limiting"``, the visible ``Limiting`` label in
    ``bw-reading__state`` with the state icon, and the negative arms — no
    ``alert`` role, no dismiss affordance (never an alert-bubble pattern)."""

    kind = "state_row"

    def __init__(self, state_key: str) -> None:
        self.state_key = state_key

    def satisfies(self, row: Row) -> list[str]:
        state = literal(row.cells[0])
        html, failure = _render_or_fail(
            lambda: partials.render_reading(fixtures.reading()), f"state:{state}"
        )
        if failure is not None or html is None:
            return [failure] if failure else ["render produced nothing"]
        rendered = RenderedComponent(html)
        messages: list[str] = []
        if not any(
            element.attrs.get("data-bw-reading-state") == state
            for element in rendered.elements
        ):
            messages.append(f"data-bw-reading-state={state} not rendered on the tile")
        state_texts = rendered.texts_of_elements(class_hook="bw-reading__state")
        if state.capitalize() not in state_texts:
            messages.append(
                f"visible label {state.capitalize()!r} not rendered in bw-reading__state"
            )
        if not any(element.tag == "svg" for element in rendered.elements):
            messages.append("the state icon (§F.1 svg) does not render with the label")
        if rendered.explicit_role("alert"):
            messages.append("a limiting reading must never enter a live region alert")
        if any(element.attrs.get("aria-label") == "Dismiss" for element in rendered.elements):
            messages.append("a limiting reading never renders a dismiss affordance")
        return messages


# ---------------------------------------------------------------------------
# §E.3 triad_row


class TriadRowArtifact:
    """§E.3: measured/set/staged placements over the canonical fixtures —
    ``Set {value} {unit}`` in ``bw-reading__set`` with
    ``data-bw-reading-role="set"``; ``Staged`` only in the staging inputs
    and never inside a reading tile."""

    kind = "triad_row"

    def __init__(self, role_key: str) -> None:
        self.role_key = role_key

    def satisfies(self, row: Row) -> list[str]:
        role = literal(row.cells[0])
        messages: list[str] = []
        if role == "measured":
            html = partials.render_reading(fixtures.reading_without_state())
            rendered = RenderedComponent(html)
            value_texts = rendered.texts_of_elements(class_hook="bw-reading__value")
            if not any("12.5" in text for text in value_texts):
                messages.append(
                    "the measured value does not render in the tile's bw-reading__value"
                )
            if "12.5 V" not in rendered.text_content:
                messages.append("the value does not render with its adjacent unit")
            if "Staged" in rendered.text_content:
                messages.append("'Staged' must never render inside a reading tile")
        elif role == "set":
            html = partials.render_reading(fixtures.reading())
            rendered = RenderedComponent(html)
            set_texts = [
                text
                for text in rendered.texts_of_elements(class_hook="bw-reading__set")
            ]
            if not set_texts:
                messages.append("the canonical set line does not render (bw-reading__set)")
            for text in set_texts:
                element_ok = text.startswith("Set ") and text.endswith(" V")
                if not element_ok:
                    messages.append(
                        f"set labelling must be 'Set {{value}} {{unit}}', got {text!r}"
                    )
            if not any(
                element.attrs.get("data-bw-reading-role") == "set"
                for element in rendered.elements
            ):
                messages.append("the set line does not carry data-bw-reading-role=set")
            if "Staged" in rendered.text_content:
                messages.append("'Staged' must never render inside a reading tile")
        elif role == "staged":
            tile = RenderedComponent(partials.render_reading(fixtures.reading()))
            if "Staged" in tile.text_content:
                messages.append("'Staged' must never render inside a reading tile")
            numeric = partials.render_numeric_input(fixtures.numeric_input())
            rotary = partials.render_rotary_control(fixtures.rotary_control())
            if "Staged" not in numeric:
                messages.append("the numeric-input staging field lost its 'Staged' pin")
            if "Staged" not in rotary:
                messages.append("the rotary-control staging field lost its 'Staged' pin")
        else:
            messages.append(f"unknown §E.3 role {role!r}")
        return messages


# ---------------------------------------------------------------------------
# §F.1 icon_partial / §E.2.2 sequence_partial


def _pairwise_distinct_renders(render: Callable[[str], str], keys: tuple[str, ...]) -> bool:
    renders = [render(key) for key in keys]
    return len(set(renders)) == len(renders)


class IconPartialArtifact:
    """§F.1: hand-authored minimal geometric SVG from the row's shape
    description (no lucide path data — the reference binding names the
    reference renderer's icons only). Asserts the class hook from the row's
    Class cell, ``aria-hidden="true"``, a non-empty viewBox with real
    geometry, and the 10-way injectivity (the copy-paste-icon failure class
    dies here)."""

    kind = "icon_partial"

    def __init__(self, icon_key: str) -> None:
        self.icon_key = icon_key

    def satisfies(self, row: Row) -> list[str]:
        icon = literal(row.cells[0])
        icon_class = literal(row.cells[1])
        html, failure = _render_or_fail(lambda: partials.render_icon(icon), f"icon:{icon}")
        if failure is not None or html is None:
            return [failure] if failure else ["render produced nothing"]
        rendered = RenderedComponent(html)
        messages: list[str] = []
        if rendered.root_tag != "svg":
            messages.append(f"root element: expected <svg>, got <{rendered.root_tag}>")
        if not rendered.has_class_hook(f"bw-icon--{icon_class}"):
            messages.append(f"class hook bw-icon--{icon_class} not carried")
        if not rendered.satisfies_attribute_item(parse_attribute_item("aria-hidden=true")):
            messages.append('aria-hidden="true" not carried')
        # html.parser lowercases attribute names: viewBox parses as viewbox.
        viewbox = next(
            (
                element.attrs.get("viewbox")
                for element in rendered.elements
                if "viewbox" in element.attrs
            ),
            None,
        )
        if not viewbox:
            messages.append("the icon carries no non-empty viewBox")
        if not any(element.tag in _GEOMETRY_TAGS for element in rendered.elements):
            messages.append("the icon carries no geometry element")
        icon_keys = _KEYS_BY_SLUG["f-1-icons"]
        if not _pairwise_distinct_renders(partials.render_icon, icon_keys):
            messages.append("the ten icon renders are not pairwise distinct (injectivity)")
        return messages


class SequencePartialArtifact:
    """§E.2.2: the dash/symbol fragments. dash-1 is the no-dasharray default
    (solid); dash-2 carries an equal on/off dasharray; symbols are geometry,
    not lines; all ten renders pairwise distinct."""

    kind = "sequence_partial"

    def __init__(self, sequence_key: str) -> None:
        self.sequence_key = sequence_key

    def satisfies(self, row: Row) -> list[str]:
        key = literal(row.cells[0])
        html, failure = _render_or_fail(
            lambda: partials.render_sequence(key), f"sequence:{key}"
        )
        if failure is not None or html is None:
            return [failure] if failure else ["render produced nothing"]
        rendered = RenderedComponent(html)
        messages: list[str] = []
        if rendered.root_tag not in _GEOMETRY_TAGS:
            messages.append(
                f"a sequence fragment must be a geometry element, got <{rendered.root_tag}>"
            )
        if not rendered.has_class_hook("bw-seq"):
            messages.append("class hook bw-seq not carried")
        if key == "dash-1":
            if any("stroke-dasharray" in element.attrs for element in rendered.elements):
                messages.append("dash-1 (solid) must carry no stroke-dasharray")
        elif key == "dash-2":
            dasharray = next(
                (
                    element.attrs.get("stroke-dasharray")
                    for element in rendered.elements
                    if "stroke-dasharray" in element.attrs
                ),
                None,
            )
            if dasharray != "4 4":
                messages.append(
                    f"dash-2 must be equal on/off segments (4 4), got {dasharray!r}"
                )
        else:
            if rendered.root_tag == "line":
                messages.append("a symbol must be a filled geometry, not a line")
        sequence_keys = _KEYS_BY_SLUG["e-2-2-sequences"]
        if not _pairwise_distinct_renders(partials.render_sequence, sequence_keys):
            messages.append("the ten sequence renders are not pairwise distinct")
        return messages


# ---------------------------------------------------------------------------
# §A token rows — thin artifacts over G1a's tokens functions, CSS by path


def _read_css(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


class TokenPairArtifact:
    """§A.1: the row's Light/Dark cells vs ``themes.css`` (G1a's
    ``theme_colour_mismatches`` scoped to the single row), plus the
    table-level CSS→contract direction — a theme-varying colour with no
    §A.1 row reds every §A.1 row (fail-closed: an unpinned extra is a
    property of the table, not of one row). ``themes_text`` injects the CSS
    source for the drift-discrimination test (never writes the asset)."""

    kind = "token_pair"

    def __init__(self, key: str = "", *, themes_text: str | None = None) -> None:
        self.key = key
        self._themes_text = themes_text

    def satisfies(self, row: Row) -> list[str]:
        themes = self._themes_text if self._themes_text is not None else _read_css(THEMES_CSS)
        if themes is None:
            return [
                "themes.css unreadable at "
                f"{THEMES_CSS.resolve()} — the token rows are live where the gate "
                "runs from the repository root (G1a deferral D3 keeps the path)"
            ]
        light = css_block(themes, 'data-theme="light"')
        dark = css_block(themes, 'data-theme="dark"')
        scoped = [
            message
            for message in theme_colour_mismatches([row], light, dark)
            if not message.startswith("themes.css")
        ]
        pinned = set(_KEYS_BY_SLUG["a-1-colour-palette"])
        extras = [f"themes.css light token {t} is not contract-pinned"
                  for t in light if t not in pinned]
        extras += [f"themes.css dark token {t} is not contract-pinned"
                   for t in dark if t not in pinned]
        return scoped + extras


#: ``tokens.css`` ``:root`` families → the §A table that owns the family.
_TOKEN_FAMILY_SLUGS: dict[str, str] = {
    "--bw-space-": "a-2-spacing-and-layout",
    "--bw-radius-": "a-3-radius",
    "--bw-font-": "a-4-typography-fonts",
}


class TokenValueArtifact:
    """§A.2–§A.4: the row's Value cell vs ``tokens.css`` ``:root`` (G1a's
    ``token_value_mismatches`` scoped to the single row), plus the family's
    CSS→contract direction — an extra ``--bw-space-*``/``--bw-radius-*``/
    ``--bw-font-*`` token reds exactly its own family's rows.
    ``tokens_text`` injects the CSS source for tests (never writes assets)."""

    kind = "token_value"

    def __init__(self, key: str = "", *, tokens_text: str | None = None) -> None:
        self.key = key
        self._tokens_text = tokens_text

    def satisfies(self, row: Row) -> list[str]:
        tokens_css = (
            self._tokens_text if self._tokens_text is not None else _read_css(TOKENS_CSS)
        )
        if tokens_css is None:
            return [
                "tokens.css unreadable at "
                f"{TOKENS_CSS.resolve()} — the token rows are live where the gate "
                "runs from the repository root (G1a deferral D3 keeps the path)"
            ]
        root = css_block(tokens_css, ":root")
        scoped = [
            message
            for message in token_value_mismatches([row], root)
            if not message.startswith("tokens.css")
        ]
        pinned = set(_KEYS_BY_SLUG[row.table_slug])
        family_extras: list[str] = []
        for token in root:
            family = next(
                (slug for prefix, slug in _TOKEN_FAMILY_SLUGS.items()
                 if token.startswith(prefix)),
                None,
            )
            if family == row.table_slug and token not in pinned:
                family_extras.append(f"tokens.css token {token} is not contract-pinned")
        return scoped + family_extras


# ---------------------------------------------------------------------------
# Registration

_REGISTRARS: dict[str, Callable[[str], registry.Artifact]] = {
    "e-1-components": _component_factory,
    "c-3-refusal-mapping": RefusalRenderArtifact,
    "c-2-disabled-reason-enum": LabelRenderArtifact,
    "b-1-severities": SeverityRowArtifact,
    "d-1-modes": ModeRowArtifact,
    "b-3-reading-states": StateRowArtifact,
    "e-3-setpoint-presentation-reading-tile-sub-rows": TriadRowArtifact,
    "f-1-icons": IconPartialArtifact,
    "e-2-2-sequences": SequencePartialArtifact,
    "a-1-colour-palette": TokenPairArtifact,
    "a-2-spacing-and-layout": TokenValueArtifact,
    "a-3-radius": TokenValueArtifact,
    "a-4-typography-fonts": TokenValueArtifact,
}

#: Every row-id G1b registers — derived from the registrar coverage, so the
#: completeness meta arm (set equality against the registry) and the
#: registration share one mechanism; the independent manifest-derivation
#: equality lands with the final slice's coverage arm.
def _registered_row_ids() -> frozenset[str]:
    ids: set[str] = set()
    for slug in _REGISTRARS:
        for key in _KEYS_BY_SLUG[slug]:
            if slug == "e-1-components" and key in _PENDING_COMPONENTS:
                continue
            ids.add(f"{slug}::{key}")
    return frozenset(ids)


G1B_ROW_IDS: frozenset[str] = _registered_row_ids()


def ensure_registered() -> None:
    """Register every G1b artifact exactly once (sentinel-idempotent)."""
    if SENTINEL_ROW_ID in registry.REGISTRY:
        return
    for slug, factory in _REGISTRARS.items():
        for key in _KEYS_BY_SLUG[slug]:
            if slug == "e-1-components" and key in _PENDING_COMPONENTS:
                continue
            registry.REGISTRY.register(f"{slug}::{key}", factory(key))


__all__ = [
    "ComponentRenderArtifact",
    "DEFERRED_SLUGS",
    "G1B_ROW_IDS",
    "IconPartialArtifact",
    "LabelRenderArtifact",
    "ModeRowArtifact",
    "RefusalRenderArtifact",
    "SENTINEL_ROW_ID",
    "SequencePartialArtifact",
    "SeverityRowArtifact",
    "StateRowArtifact",
    "THEMES_CSS",
    "TOKENS_CSS",
    "TokenPairArtifact",
    "TokenValueArtifact",
    "TriadRowArtifact",
    "button_artifact",
    "ensure_registered",
]
