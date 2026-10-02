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

Scope (G1b design record §1.2 + G1d record §1.2): the full 168 rows. The
ten ``rule_proof`` behaviour rows — §B.2 SR-B1/B2/B3, §B.4 ST-1..ST-4,
§C.1 R-ENERGISE-1/R-DEENERGISE-1/R-PROTECT-1 — were G1b's named deferrals
and are discharged by G1d's composition checkers: state-machine drivers
(transitions, fire attempts, refusals), never single-fixture structure
checks (the G1b kill rule — prose-laundering).
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast, get_args, get_type_hints

from benchweave_ui_html import assets, compositions, fixtures, partials, registry, staleness
from benchweave_ui_html.assertions import Element, RenderedComponent
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
from benchweave_ui_html.plot import DASH_TO_DATA_LINE, EMPHASIS_SERIES, MUTED_SERIES
from benchweave_ui_html.tokens import css_block, theme_colour_mismatches, token_value_mismatches

#: The idempotence sentinel: the first row the §E.1 family registers.
SENTINEL_ROW_ID = "e-1-components::button"

#: The behaviour-rule tables G1b deferred to G1d (record §1.2). EMPTY since
#: G1d slice 2: the ten rows register through the composition checkers, and
#: the constant stays as the declaration that no table is deferred — a
#: future deferral names its slugs here or the completeness arm reds.
DEFERRED_SLUGS: frozenset[str] = frozenset()

#: §E.1 components whose renderers land with the plot (slice 3) and lanes
#: (slice 4) commits. Unknown beyond these: a §E.1 row with no renderer
#: raises at collection — a new component row can never silently skip.
_PENDING_COMPONENTS: frozenset[str] = frozenset()

#: The contract's executable token mirror — the package's vendored assets
#: (G1e, UR-10): the last React build's bytes, moved verbatim and pinned by
#: ``assets/inventory.json`` (verified by ``assets.verify_vendored_assets``).
#: Anchored to the package, so the paths are CWD-independent; a missing
#: asset reds loudly.
_STYLES_DIR = assets.ASSETS_DIR
THEMES_CSS = _STYLES_DIR / "themes.css"
TOKENS_CSS = _STYLES_DIR / "tokens.css"
#: Fold F1 (issue #300 two-lane refute): globals.css APPLIES the theme
#: tokens (html background/colour) — without it the two themes render
#: pixel-identical. Inlined last, after the token definitions it reads.
GLOBALS_CSS = _STYLES_DIR / "globals.css"

#: Geometry element names for icon/sequence structure assertions.
_GEOMETRY_TAGS = frozenset(
    {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect"}
)

_KEYS_BY_SLUG: dict[str, tuple[str, ...]] = {table.slug: table.keys for table in MANIFEST}

#: The M3 fold: closed-enum memberships the row-as-data echo cannot detect
#: on its own (a drifted scratch row would render-and-pass); each artifact
#: reds a key outside its enum.
_SEVERITY_KEYS = frozenset(_KEYS_BY_SLUG["b-1-severities"])
_DISABLED_REASON_KEYS = frozenset(_KEYS_BY_SLUG["c-2-disabled-reason-enum"])
_MODE_KEYS = frozenset(_KEYS_BY_SLUG["d-1-modes"])

#: The §E.1 column indexes (Component | Root | attrs | roles | hooks | text | Notes).
_E1_ROOT, _E1_ATTRS, _E1_ROLES, _E1_HOOKS, _E1_TEXT = 1, 2, 3, 4, 5

#: A-F3 fold: inline styles that hide an element — the statically
#: parseable half of the deleted TS gates' ``toBeVisible`` assertion. A
#: required-visible element carrying one of these in its ``style``
#: attribute is a renderer defect, named per element.
_HIDING_INLINE_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden")


def _inline_hiding_violations(rendered: RenderedComponent) -> list[str]:
    """Elements hidden by inline style (``display:none`` /
    ``visibility:hidden`` in the ``style`` attribute). Does NOT catch
    CSS-class hiding — statics compute no stylesheets; that residual stays
    the browser lane's, the same disclosed class the TS gates carried
    (jsdom applied no stylesheets either)."""
    return [
        f"element <{element.tag}> is hidden by inline style "
        f"(style={element.attrs.get('style')!r}) — required-visible output "
        "must not be inline-hidden"
        for element in rendered.elements
        if _HIDING_INLINE_STYLE.search(element.attrs.get("style") or "")
    ]


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
    "engineering-plot": lambda: partials.render_plot(fixtures.engineering_plot()),
    "digital-lanes": lambda: partials.render_lanes(fixtures.digital_lanes()),
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
        # The M3 fold: the severity cell must be a §B.1 key — the row-as-data
        # echo alone cannot detect enum drift (a scratch row would
        # render-and-pass).
        if data.severity not in _SEVERITY_KEYS:
            messages.append(
                f"severity {data.severity!r} is not a §B.1 severity key"
            )
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
        # A-F3 fold: the same inline-style visibility guard over the
        # refusal bubble — a hidden bubble with all fields present is
        # still hidden.
        messages.extend(_inline_hiding_violations(rendered))
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
        # The M3 fold: the reason key must be a §C.2 enum key.
        if data.reason not in _DISABLED_REASON_KEYS:
            messages.append(f"disabled reason {data.reason!r} is not a §C.2 enum key")
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
        # A-F3 fold: the inline-style half of visibility — a hidden label
        # with matching text is still hidden.
        messages.extend(_inline_hiding_violations(rendered))
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
        # The M3 fold: the mode key must be a §D.1 key.
        if mode not in _MODE_KEYS:
            messages.append(f"mode {mode!r} is not a §D.1 mode key")
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
# §E.2.1 slot_value / §E.2.0 hint_row — over plot.py's emit model


def _legend_rows(rendered: RenderedComponent) -> list[Element]:
    """The legend rows: elements carrying ``data-bw-series-slot``."""
    return [
        element for element in rendered.elements if "data-bw-series-slot" in element.attrs
    ]


def _legend_row_for(rendered: RenderedComponent, channel: str) -> Element | None:
    return next(
        (
            element
            for element in _legend_rows(rendered)
            if element.attrs.get("data-bw-channel-id") == channel
        ),
        None,
    )


class SlotValueArtifact:
    """§E.2.1: the slot-i row's Colour/Dash/Symbol cells against the 16-id
    canonical fixture's emitted legend triple — ``data-bw-series-slot`` =
    ``((i mod 8)+1)``, ``data-bw-resolved-series`` = the colour cell,
    ``data-line`` = the RESOLVED dash form (solid/dashed, per §E.1 — the
    cell names the §E.2.2 key), ``data-bw-symbol`` = the symbol cell. Two
    legend rows share a slot number; the dash disambiguates (the wrap at
    8 is what the mutation control breaks)."""

    kind = "slot_value"

    def __init__(self, key: str) -> None:
        self.key = key

    def satisfies(self, row: Row) -> list[str]:
        index = int(literal(row.cells[0]))
        colour = literal(row.cells[1])
        dash = literal(row.cells[2])
        symbol = literal(row.cells[3])
        expected_line = DASH_TO_DATA_LINE[dash]
        rendered = RenderedComponent(partials.render_plot(fixtures.slots16_plot()))
        matching = [
            element
            for element in _legend_rows(rendered)
            if element.attrs.get("data-bw-series-slot") == str((index % 8) + 1)
            and element.attrs.get("data-bw-resolved-series") == colour
            and element.attrs.get("data-line") == expected_line
            and element.attrs.get("data-bw-symbol") == symbol
        ]
        if not matching:
            return [
                f"no legend row carries the slot-{(index % 8) + 1} triple "
                f"({colour} / {dash} → {expected_line} / {symbol})"
            ]
        return []


class HintRowArtifact:
    """§E.2.0: each hint row's Effect, asserted on the canonical hinted sets
    — accent loses to a visible slot-1 claim / wins by trace order when the
    claim is released, muted repaints and releases (with the token-less
    fallback keeping the slot colour), ``visible: false`` never moves a
    slot or restyles siblings, no hint keeps every §E.2.1 slot fact."""

    kind = "hint_row"

    def __init__(self, key: str) -> None:
        self.key = key

    def satisfies(self, row: Row) -> list[str]:
        hint = literal(row.cells[0])
        messages: list[str] = []
        if hint == 'color_role: "accent"':
            loses = RenderedComponent(
                partials.render_plot(fixtures.hint_accent_loses_plot())
            )
            alpha, beta = (_legend_row_for(loses, c) for c in ("alpha", "beta"))
            if alpha is None or beta is None:
                return ["the accent fixture did not render its legend rows"]
            if alpha.attrs.get("data-bw-resolved-series") != EMPHASIS_SERIES:
                messages.append(
                    f"pass-1 slot 1 must keep the emphasis default {EMPHASIS_SERIES}"
                )
            if beta.attrs.get("data-bw-resolved-series") != "--bw-series-2":
                messages.append(
                    "an accent hint on a non-slot-1 trace must lose silently to "
                    "the visible slot-1 claim (revert to its slot colour)"
                )
            wins = RenderedComponent(partials.render_plot(fixtures.hint_accent_wins_plot()))
            beta_w, gamma_w = (_legend_row_for(wins, c) for c in ("beta", "gamma"))
            if beta_w is None or gamma_w is None:
                return ["the accent-winner fixture did not render its legend rows"]
            if beta_w.attrs.get("data-bw-resolved-series") != EMPHASIS_SERIES:
                messages.append(
                    "with the slot-1 claim released, the earliest visible accent "
                    "hint in trace order must win the emphasis colour"
                )
            if gamma_w.attrs.get("data-bw-resolved-series") != "--bw-series-3":
                messages.append(
                    "a later accent hint must revert to its slot colour"
                )
            # The M2 corner: the accent-hinted channel DECLARED BEFORE the
            # slot-1 channel — slots come from the bytewise sort, so slot 1
            # still claims and the accent reverts (declaration order cannot
            # mint a second emphasis; the TS's order-dependent double-emphasis
            # bug is the reference's, dying at G1e — fold note).
            corner = RenderedComponent(
                partials.render_plot(fixtures.hint_accent_before_slot1_plot())
            )
            alpha_c, beta_c = (_legend_row_for(corner, c) for c in ("alpha", "beta"))
            if alpha_c is None or beta_c is None:
                messages.append("the M2 corner fixture did not render its legend rows")
            else:
                if alpha_c.attrs.get("data-bw-resolved-series") != EMPHASIS_SERIES:
                    messages.append(
                        "the bytewise slot-1 trace keeps series-1 regardless of "
                        "declaration order"
                    )
                if beta_c.attrs.get("data-bw-resolved-series") != "--bw-series-2":
                    messages.append(
                        "an accent hint on a later slot declared FIRST still loses "
                        "to the slot-1 claim (no double emphasis)"
                    )
        elif hint == 'color_role: "muted"':
            muted = RenderedComponent(partials.render_plot(fixtures.hint_muted_plot()))
            alpha, beta = (_legend_row_for(muted, c) for c in ("alpha", "beta"))
            if alpha is None or beta is None:
                return ["the muted fixture did not render its legend rows"]
            if alpha.attrs.get("data-bw-resolved-series") != MUTED_SERIES:
                messages.append(f"a muted hint must repaint {MUTED_SERIES}")
            if beta.attrs.get("data-bw-resolved-series") != "--bw-series-2":
                messages.append(
                    "releasing the muted trace's claim must not cascade (the "
                    "sibling keeps its slot colour, never promoted)"
                )
            fallback = RenderedComponent(
                partials.render_plot(fixtures.hint_muted_plot(theme_resolves_muted=False))
            )
            alpha_f = _legend_row_for(fallback, "alpha")
            if alpha_f is None:
                return ["the token-less muted fixture did not render its legend rows"]
            if alpha_f.attrs.get("data-bw-resolved-series") != "--bw-series-1":
                messages.append(
                    "a token-less muted hint falls back to its slot colour "
                    "(which still claims if it is slot 1)"
                )
        elif hint == "visible: false":
            hidden_plot = RenderedComponent(partials.render_plot(fixtures.hint_hidden_plot()))
            alpha, beta, gamma = (
                _legend_row_for(hidden_plot, c) for c in ("alpha", "beta", "gamma")
            )
            if alpha is None or beta is None or gamma is None:
                return ["the hidden fixture did not render its legend rows"]
            if "data-hidden" not in beta.attrs:
                messages.append("the hidden channel's legend row must carry data-hidden")
            if beta.attrs.get("data-bw-series-slot") != "2":
                messages.append("a hidden channel's SLOT never moves")
            if alpha.attrs.get("data-bw-series-slot") != "1" or gamma.attrs.get(
                "data-bw-series-slot"
            ) != "3":
                messages.append("hiding a channel must not restyle its siblings")
            if gamma.attrs.get("data-bw-resolved-series") != "--bw-series-3":
                messages.append("sibling colours resolve over the full declared set")
        elif hint == "(no hint)":
            plain = RenderedComponent(partials.render_plot(fixtures.no_hint_plot()))
            alpha, beta = (_legend_row_for(plain, c) for c in ("alpha", "beta"))
            if alpha is None or beta is None:
                return ["the no-hint fixture did not render its legend rows"]
            expected = {
                "alpha": ("1", "--bw-series-1", "solid", "symbol-1"),
                "beta": ("2", "--bw-series-2", "solid", "symbol-2"),
            }
            for channel, (slot, series, line, symbol) in expected.items():
                element = alpha if channel == "alpha" else beta
                got = (
                    element.attrs.get("data-bw-series-slot"),
                    element.attrs.get("data-bw-resolved-series"),
                    element.attrs.get("data-line"),
                    element.attrs.get("data-bw-symbol"),
                )
                if got != (slot, series, line, symbol):
                    messages.append(
                        f"{channel} must keep its §E.2.1 slot facts "
                        f"{(slot, series, line, symbol)}, got {got}"
                    )
        else:
            messages.append(f"unknown §E.2.0 hint row {hint!r}")
        return messages


# ---------------------------------------------------------------------------
# §E.2.3–§E.2.6 rule_proof rows — pure plot.py functions asserted through
# the emitted vocabulary (the record's §1.2 in-scope rule rows)


class RuleProofArtifact:
    """A ``rule_proof`` row proven on a canonical fixture — the checker
    receives the row and returns the unsatisfied item messages. Behaviour
    rules across components and time stay G1d's (the named deferral)."""

    kind = "rule_proof"

    def __init__(self, key: str, checker: Callable[[Row], list[str]]) -> None:
        self.key = key
        self._checker = checker

    def satisfies(self, row: Row) -> list[str]:
        return self._checker(row)


def _axes_attr(rendered: RenderedComponent) -> str:
    return next(
        (
            element.attrs.get("data-bw-axes") or ""
            for element in rendered.elements
            if "data-bw-axes" in element.attrs
        ),
        "",
    )


def _check_one_unit(row: Row) -> list[str]:
    messages: list[str] = []
    one = RenderedComponent(partials.render_plot(fixtures.one_unit_plot()))
    if _axes_attr(one) != "V":
        messages.append(f"one distinct unit must yield one y-axis named V; got {_axes_attr(one)!r}")
    for channel in ("v1", "v2", "v3"):
        element = _legend_row_for(one, channel)
        if element is None or element.attrs.get("data-bw-axis") != "1":
            messages.append(f"every trace binds to its own unit's axis (1): {channel}")
    unitless = RenderedComponent(partials.render_plot(fixtures.unitless_plot()))
    if _axes_attr(unitless) != "":
        messages.append(
            "a unit empty after trimming is the unitless group — a legal single "
            "group whose axis renders unnamed"
        )
    return messages


def _check_two_units(row: Row) -> list[str]:
    messages: list[str] = []
    two = RenderedComponent(partials.render_plot(fixtures.two_unit_plot()))
    if _axes_attr(two) != "V;A":
        messages.append(
            f"two units must yield axes V;A in first-declaration order; got {_axes_attr(two)!r}"
        )
    voltage, current = (_legend_row_for(two, c) for c in ("voltage", "current"))
    if voltage is None or voltage.attrs.get("data-bw-axis") != "1":
        messages.append("axis 1 = the earliest declared trace's unit (V)")
    if current is None or current.attrs.get("data-bw-axis") != "2":
        messages.append("axis 2 = the other unit (A)")
    return messages


def _check_refusal(row: Row) -> list[str]:
    """§E.2.3 row 3 — the M4 owner ruling (2026-10-02, adopt-with-recs):
    the >2-unit refusal draws NO traces (the axis/canvas drawing surface
    stays empty; no axis bindings exist), but the LEGEND stays — §E.1's
    "Every trace is listed in a visible legend" is unqualified, and the
    legend is listing, not drawing (matching the TS behavior)."""
    messages: list[str] = []
    refusal = RenderedComponent(partials.render_plot(fixtures.three_unit_refusal_plot()))
    if not any(
        "bw-plot__refusal" in element.class_tokens for element in refusal.elements
    ):
        messages.append("the >2-unit refusal must render its refusal note")
    if not refusal.explicit_role("status"):
        messages.append("the refusal note is a role=status live region")
    rows = _legend_rows(refusal)
    if len(rows) != 3:
        messages.append(
            "every declared trace stays listed in the legend on refusal "
            "(the legend is listing, not drawing)"
        )
    if not all("data-bw-series-slot" in element.attrs for element in rows):
        messages.append("the listed rows carry their series slot")
    if any("data-bw-axis" in element.attrs for element in refusal.elements):
        messages.append("no trace binds to an axis on refusal (nothing is drawn)")
    canvas = next(
        (e for e in refusal.elements if "bw-plot__canvas" in e.class_tokens), None
    )
    if canvas is None:
        messages.append("the canvas element must render")
    elif refusal._element_texts[refusal.elements.index(canvas)].strip():
        messages.append("the drawing surface stays empty on refusal")
    return messages


def _check_hidden_axis(row: Row) -> list[str]:
    messages: list[str] = []
    hidden = RenderedComponent(partials.render_plot(fixtures.hidden_axis_plot()))
    if _axes_attr(hidden) != "A":
        messages.append(
            "an axis whose traces are all hidden must not render; the survivor "
            f"list is just A — got {_axes_attr(hidden)!r}"
        )
    current = _legend_row_for(hidden, "current")
    if current is None or current.attrs.get("data-bw-axis") != "1":
        messages.append("surviving traces' bindings remap onto the surviving axis (renumbered 1)")
    return messages


def _check_ref_labelling(row: Row) -> list[str]:
    rendered = RenderedComponent(partials.render_plot(fixtures.reference_line_plot()))
    labels = rendered.texts_of_elements(class_hook="bw-plot__ref-label")
    if "Current limit · 2 A" not in labels:
        return ["every reference line is labelled with its meaning and value in the plot"]
    return []


def _check_ref_neutrality(row: Row) -> list[str]:
    rendered = RenderedComponent(partials.render_plot(fixtures.reference_line_plot()))
    for element in rendered.elements:
        if "data-bw-ref-line" in element.attrs:
            if element.attrs.get("data-bw-ref-colour") != "--bw-border":
                return ["reference lines render in the border token, never a severity hue"]
            if element.attrs.get("data-line") != "dotted":
                return ["reference lines render dotted, never a series dash"]
            return []
    return ["the fixture renders no reference line"]


def _check_ref_distinctness(row: Row) -> list[str]:
    rendered = RenderedComponent(partials.render_plot(fixtures.reference_line_plot()))
    ref = next(
        (e for e in rendered.elements if "data-bw-ref-line" in e.attrs), None
    )
    threshold = next(
        (e for e in rendered.elements if "data-bw-threshold" in e.attrs), None
    )
    if ref is None or threshold is None:
        return ["the distinctness fixture needs both a reference line and a threshold"]
    if ref.attrs.get("data-bw-ref-colour") == threshold.attrs.get("data-bw-ref-colour"):
        return ["a reference line and a severity threshold never share colour"]
    if ref.attrs.get("data-line") == threshold.attrs.get("data-line"):
        return ["a reference line and a severity threshold never share dash"]
    return []


def _check_ref_carrier(row: Row) -> list[str]:
    messages: list[str] = []
    rendered = RenderedComponent(
        partials.render_plot(fixtures.reference_line_hidden_target_plot())
    )
    ref = next((e for e in rendered.elements if "data-bw-ref-line" in e.attrs), None)
    if ref is None:
        return ["a reference line whose targets are all hidden must still render"]
    if "data-hidden" in ref.attrs:
        messages.append("the carrier itself is never hidden by its targets' visibility")
    if ref.attrs.get("data-bw-ref-unit") != "A":
        messages.append("each line names the unit it constrains (data-bw-ref-unit)")
    if ref.attrs.get("data-bw-carrier") != "extent":
        messages.append("one extent-spanning carrier per target axis")
    return messages


def _check_acquisition_when(row: Row) -> list[str]:
    messages: list[str] = []
    required = RenderedComponent(
        partials.render_plot(fixtures.acquisition_decimated_plot())
    )
    if not any(
        "bw-plot__acquisition" in element.class_tokens for element in required.elements
    ):
        messages.append("a visible decimated trace MUST disclose")
    not_required = RenderedComponent(
        partials.render_plot(fixtures.acquisition_not_required_plot())
    )
    if any(
        "bw-plot__acquisition" in element.class_tokens
        for element in not_required.elements
    ):
        messages.append(
            "presentation-hidden traces draw nothing, so they disclose nothing"
        )
    return messages


def _check_acquisition_placement(row: Row) -> list[str]:
    rendered = RenderedComponent(partials.render_plot(fixtures.acquisition_decimated_plot()))
    lines = [e for e in rendered.elements if "bw-plot__acquisition" in e.class_tokens]
    if not lines:
        return ["the disclosure renders as visible text"]
    if not all("data-bw-acquisition" in e.attrs for e in lines):
        return ["the disclosure carries the data-bw-acquisition attribute"]
    canvas = next(
        (e for e in rendered.elements if "bw-plot__canvas" in e.class_tokens), None
    )
    if canvas is None:
        return ["the canvas element must render"]
    # The canvas is the EMPTY hydrate target — nothing renders inside it, so
    # the disclosure is necessarily outside the chart image (never
    # tooltip-only). Assert the emptiness that makes "outside" structural.
    canvas_index = rendered.elements.index(canvas)
    canvas_text = rendered._element_texts[canvas_index]
    if canvas_text.strip():
        return ["the hydrate-target canvas carries no payload text"]
    return []


def _check_acquisition_wording(row: Row) -> list[str]:
    messages: list[str] = []
    rendered = RenderedComponent(partials.render_plot(fixtures.acquisition_decimated_plot()))
    texts = rendered.texts_of_elements(class_hook="bw-plot__acquisition")
    if texts != ["Acquired 100 samples · plotted 2"]:
        messages.append(f"wording must be 'Acquired 100 samples · plotted 2'; got {texts!r}")
    line = next(e for e in rendered.elements if "bw-plot__acquisition" in e.class_tokens)
    if line.attrs.get("data-bw-plotted") != "2":
        messages.append("m is the drawn count (values.length), never caller-supplied")
    # The M1 fold's multi-trace arm: one row PER TRACE with that trace's own
    # drawn count — a summed scalar across traces reds here.
    multi = RenderedComponent(partials.render_plot(fixtures.acquisition_multi_trace_plot()))
    multi_texts = sorted(multi.texts_of_elements(class_hook="bw-plot__acquisition"))
    if multi_texts != [
        "Acquired 100 samples · plotted 2",
        "Acquired 200 samples · plotted 4",
    ]:
        messages.append(
            "the acquisition rows are PER TRACE (each trace's own acquired and "
            f"drawn counts, never a summed scalar); got {multi_texts!r}"
        )
    return messages


_PROVENANCE_CHANNEL = {
    "measured": "measured-rail",
    "derived": "derived-rail",
    "device-averaged": "averaged-rail",
    "display-processed": "smoothed-rail",
}


def _check_provenance(row: Row) -> list[str]:
    provenance = literal(row.cells[0])
    channel = _PROVENANCE_CHANNEL[provenance]
    rendered = RenderedComponent(partials.render_plot(fixtures.provenance_plot()))
    element = _legend_row_for(rendered, channel)
    if element is None:
        return [f"the {provenance} fixture row did not render"]
    if provenance == "measured":
        if "data-bw-trace-provenance" in element.attrs:
            return ["a measured trace carries NEITHER the attribute"]
        if "device averaging" in rendered._element_texts[rendered.elements.index(element)]:
            return ["a measured trace carries no marker text"]
        return []
    if element.attrs.get("data-bw-trace-provenance") != provenance:
        return [f"a marked trace carries data-bw-trace-provenance={provenance}"]
    text = rendered._element_texts[rendered.elements.index(element)]
    if provenance == "derived":
        if "derived" not in text:
            return ["the derived marker text must render"]
        if "rail ÷ divider ratio" not in text or "uncertainty unknown" not in text:
            return ["the derivation expression and 'uncertainty unknown' must render"]
    elif provenance == "device-averaged":
        if "device averaging 8" not in text:
            return ["the applied device averaging depth must render in the marker"]
        if "display processing" in text:
            return ["marker text never uses the display-processing vocabulary"]
    elif provenance == "display-processed":
        if "display processing: moving-average 100 ms" not in text:
            return ["the processing name and window must render in the marker"]
        if "device averaging" in text:
            return ["marker text never uses the device-averaging vocabulary"]
        if _legend_row_for(rendered, "smoothed-rail-source") is None:
            return ["the source trace remains rendered in the same plot"]
    return []


_PLOT_RULE_CHECKERS: dict[str, Callable[[Row], list[str]]] = {
    "One distinct unit among the declared traces": _check_one_unit,
    "Two distinct units among the declared traces": _check_two_units,
    "More than two distinct units among the declared traces": _check_refusal,
    "Every trace bound to an axis is presentation-hidden": _check_hidden_axis,
    "Labelling": _check_ref_labelling,
    "Neutrality": _check_ref_neutrality,
    "Distinctness": _check_ref_distinctness,
    "Carrier": _check_ref_carrier,
    "When required": _check_acquisition_when,
    "Placement": _check_acquisition_placement,
    "Wording": _check_acquisition_wording,
    "measured": _check_provenance,
    "derived": _check_provenance,
    "device-averaged": _check_provenance,
    "display-processed": _check_provenance,
}


def _plot_rule_factory(key: str) -> RuleProofArtifact:
    checker = _PLOT_RULE_CHECKERS.get(key)
    if checker is None:
        raise KeyError(f"no plot rule checker for {key!r}")
    return RuleProofArtifact(key, checker)


# ---------------------------------------------------------------------------
# §E.4.1–§E.4.6 rule_proof rows — lanes.py structure over the canonical capture


def _lane_rows(rendered: RenderedComponent) -> list[Element]:
    """The LANE ROW elements — those carrying both ``data-bw-lane`` and
    ``data-bw-lane-kind``. Segments and bus cells also carry ``data-bw-lane``
    (the L6 scoping attribute) but must never read as lane rows."""
    return [
        element
        for element in rendered.elements
        if "data-bw-lane" in element.attrs and "data-bw-lane-kind" in element.attrs
    ]


def _segments(rendered: RenderedComponent) -> list[Element]:
    return [
        element for element in rendered.elements if "data-bw-state-kind" in element.attrs
    ]


def _check_lane_layout(key: str) -> Callable[[Row], list[str]]:
    def check(row: Row) -> list[str]:
        rendered = RenderedComponent(partials.render_lanes(fixtures.digital_lanes()))
        messages: list[str] = []
        if key == "Uniform bands":
            heights = {
                element.attrs.get("data-bw-band-height")
                for element in _lane_rows(rendered)
            }
            if heights != {"1"}:
                messages.append(
                    f"every drawn channel band carries the same height (identity is "
                    f"position, never size); got {sorted(str(h) for h in heights)}"
                )
        elif key == "Pinned labels":
            for _lane in _lane_rows(rendered):
                label = next(
                    (
                        element
                        for element in rendered.elements
                        if "bw-lanes__label" in element.class_tokens
                    ),
                    None,
                )
                if label is None or "data-hidden" in label.attrs:
                    messages.append(
                        "the label column is pinned left and always visible — labels "
                        "never scroll or clip out of view"
                    )
                    break
        elif key == "Hidden lanes":
            hidden_rows = [e for e in _lane_rows(rendered) if "data-hidden" in e.attrs]
            if not hidden_rows:
                return ["the canonical capture declares a hidden lane"]
            hidden_row = hidden_rows[0]
            if not (hidden_row.attrs.get("aria-label") or "").endswith(
                "(hidden by presentation preference)"
            ):
                messages.append("the hidden lane's aria-label must end with the wording")
            label_text = rendered.texts_of_elements(class_hook="bw-lanes__label")
            if not any("hidden" in text and "aux" in text for text in label_text):
                messages.append(
                    "a hidden lane keeps its label plus the hidden marker text"
                )
        elif key == "Hiding is disclosure":
            rows_in_order = _lane_rows(rendered)
            order = [str(e.attrs.get("data-bw-lane") or "") for e in rows_in_order]
            kinds = [str(e.attrs.get("data-bw-lane-kind") or "") for e in rows_in_order]
            if sorted(order, key=int) != [str(i) for i in range(6)]:
                messages.append(
                    "hiding is never a removal — every declared lane index stays"
                )
            channel_group = [
                int(n)
                for n, k in zip(order, kinds, strict=True)
                if k in ("channel", "group")
            ]
            decoder = [
                int(n) for n, k in zip(order, kinds, strict=True) if k == "decoder"
            ]
            if channel_group != sorted(channel_group) or decoder != sorted(decoder):
                messages.append(
                    f"lane rows keep declaration order within their band; got {order}"
                )
            if any(k == "decoder" for k in kinds[: len(channel_group)]):
                messages.append("decoder rows render beneath the channel and bus rows")
            if not any(
                (e.attrs.get("aria-label") or "").startswith("aux ")
                for e in _lane_rows(rendered)
            ):
                messages.append("the hidden marker names the lane")
        return messages

    return check


def _lane_kind_by_index(rendered: RenderedComponent) -> dict[str, str]:
    return {
        str(lane.attrs.get("data-bw-lane") or ""): str(lane.attrs.get("data-bw-lane-kind") or "")
        for lane in _lane_rows(rendered)
    }


def _channel_segments(rendered: RenderedComponent) -> list[Element]:
    """The L6 fold: §E.4.2's evidence set is the CHANNEL lanes' segments —
    a bus cell's hatch attribute can never satisfy a state-rendering arm."""
    kinds = _lane_kind_by_index(rendered)
    return [
        element
        for element in _segments(rendered)
        if kinds.get(str(element.attrs.get("data-bw-lane") or "")) == "channel"
    ]


def _bus_cells_of(rendered: RenderedComponent) -> list[Element]:
    """The L6 fold: §E.4.3's evidence set is the bus lanes' cells (both the
    valued form and the hatched unknown form) — a channel lane's x-hatch
    segment can never satisfy an unknown-bus arm."""
    kinds = _lane_kind_by_index(rendered)
    return [
        element
        for element in rendered.elements
        if "data-bw-first" in element.attrs
        and kinds.get(str(element.attrs.get("data-bw-lane") or "")) == "group"
    ]


def _check_state_rendering(key: str) -> Callable[[Row], list[str]]:
    def check(row: Row) -> list[str]:
        rendered = RenderedComponent(partials.render_lanes(fixtures.digital_lanes()))
        segments = _channel_segments(rendered)
        messages: list[str] = []
        state_kind = {
            "1": "high",
            "0": "low",
            "x": "hatch",
            "z": "midline",
        }
        if key in ("1", "0", "x` and `z"):
            wanted = ["1"] if key == "1" else ["0"] if key == "0" else ["x", "z"]
            for state in wanted:
                plain = [
                    e for e in segments if e.attrs.get("data-bw-state") == state
                ]
                if not plain:
                    messages.append(f"a plain {state!r} segment must render")
                    continue
                kinds = {e.attrs.get("data-bw-state-kind") for e in plain}
                if kinds != {state_kind[state]}:
                    messages.append(
                        f"state {state!r} must render as {state_kind[state]!r}; got {kinds}"
                    )
            # The L3 fold: every emitted data-bw-state is a single value — the
            # old "pre→post" composite is gone, and each edge half carries its
            # own resolved kind.
            composite = [
                e
                for e in segments
                if "→" in str(e.attrs.get("data-bw-state") or "")
            ]
            if composite:
                messages.append(
                    "an edge column renders two half-width single-value segments, "
                    "never a composite data-bw-state"
                )
            halves = [
                e for e in segments if e.attrs.get("data-bw-half") in ("first", "second")
            ]
            if not halves:
                messages.append("the four-state fixture must exercise an edge column")
        elif key == "Monochrome discriminability":
            mapping: dict[str, str] = {}
            for element in segments:
                seg_state = element.attrs.get("data-bw-state") or ""
                kind = element.attrs.get("data-bw-state-kind") or ""
                if seg_state in state_kind:
                    mapping.setdefault(seg_state, kind)
            if len(set(mapping.values())) != len(mapping):
                messages.append(
                    "the four states must be mutually discriminable WITHOUT colour — "
                    f"distinct geometries; got {mapping}"
                )
        return messages

    return check


def _check_groups_buses(key: str) -> Callable[[Row], list[str]]:
    def check(row: Row) -> list[str]:
        rendered = RenderedComponent(partials.render_lanes(fixtures.digital_lanes()))
        messages: list[str] = []
        if key == "Bus lane":
            groups = [
                e for e in _lane_rows(rendered) if e.attrs.get("data-bw-lane-kind") == "group"
            ]
            if len(groups) != 1:
                messages.append(
                    "a declared group renders collapsed as ONE bus lane — identity is "
                    "its label and position"
                )
        elif key == "Radix":
            cells = [
                e for e in rendered.elements if "data-bw-bus-value" in e.attrs
            ]
            if not cells:
                return ["the canonical bus renders no valued cells"]
            values = [e.attrs.get("data-bw-bus-value") for e in cells]
            if not all(
                v is not None and len(v) == 1 and v[0] in "0123456789ABCDEF"
                for v in values
            ):
                messages.append(
                    f"hex default zero-pads to the group's bit width in nibbles; got {values}"
                )
            decimal = RenderedComponent(
                partials.render_lanes(fixtures.bus_decimal_lanes())
            )
            decimal_values = [
                e.attrs.get("data-bw-bus-value")
                for e in decimal.elements
                if "data-bw-bus-value" in e.attrs
            ]
            if decimal_values and decimal_values[0] == "3":
                pass  # decimal per-group opt-in renders the decimal form
            else:
                messages.append("the decimal opt-in renders the decimal form")
        elif key == "Member order":
            forward = RenderedComponent(
                partials.render_lanes(fixtures.bus_member_order_lanes())
            )
            swapped = RenderedComponent(
                partials.render_lanes(fixtures.bus_member_order_lanes(swapped=True))
            )
            forward_value = next(
                (
                    e.attrs.get("data-bw-bus-value")
                    for e in forward.elements
                    if "data-bw-bus-value" in e.attrs
                ),
                None,
            )
            swapped_value = next(
                (
                    e.attrs.get("data-bw-bus-value")
                    for e in swapped.elements
                    if "data-bw-bus-value" in e.attrs
                ),
                None,
            )
            # lo=1, hi=0: (lo, hi) = 0b01 = 1; (hi, lo) = 0b10 = 2 — the
            # FIRST declared member is the LSB.
            if forward_value != "1" or swapped_value != "2":
                messages.append(
                    "the first declared member is the LSB — bus values are a pure "
                    f"function of (member states, member order); "
                    f"got {forward_value}/{swapped_value}"
                )
        elif key == "Unknown bus":
            # The L6 fold: the evidence set is the BUS lanes' cells — a
            # channel lane's x-hatch segment can never satisfy this arm.
            bus_cells = _bus_cells_of(rendered)
            unknown = [
                e
                for e in bus_cells
                if e.attrs.get("data-bw-state-kind") == "hatch"
                and "data-bw-bus-value" not in e.attrs
            ]
            if not unknown:
                messages.append(
                    "a member column not resolving stably renders the bus cell hatched"
                )
            if any(
                e.attrs.get("data-bw-state-kind") == "hatch"
                and "data-bw-bus-value" in e.attrs
                for e in bus_cells
            ):
                messages.append("never a fabricated number over a transition")
        return messages

    return check


def _check_decimation(key: str) -> Callable[[Row], list[str]]:
    def check(row: Row) -> list[str]:
        composed = fixtures.digital_lanes()
        rendered = RenderedComponent(partials.render_lanes(composed))
        messages: list[str] = []
        states = fixtures._clk_states()
        lane = composed.lanes[0]
        if key == "Every transition survives":
            total = sum(1 for i in range(len(states) - 1) if states[i] != states[i + 1])
            interior = 0
            for segment in lane.segments:
                for i in range(segment.first, segment.last - 1):
                    if states[i] != states[i + 1]:
                        interior += 1
            boundary = 0
            for a, b in zip(lane.segments, lane.segments[1:], strict=False):
                if states[a.last - 1] != states[b.first]:
                    boundary += 1
            if interior + boundary != total:
                messages.append(
                    f"a drawn column must contain every state change (as an edge or "
                    f"a glitch mark): {interior} interior + {boundary} boundary != "
                    f"{total} acquired transitions"
                )
        elif key == "Glitch mark":
            glitches = [
                e for e in rendered.elements if "data-bw-glitch" in e.attrs
            ]
            if not glitches:
                messages.append(
                    "any column covering more than one transition renders the glitch mark"
                )
        elif key == "No sample dropping":
            segments = lane.segments
            if not (segments[0].first == 0 and segments[-1].last == len(states)):
                messages.append("the drawn columns partition the acquired window")
            elif any(
                b.first != a.last
                for a, b in zip(segments, segments[1:], strict=False)
            ):
                messages.append("the drawn columns are contiguous (a partition)")
            elif len(segments) != 12:
                messages.append(
                    "the reduction is column-wise over the partition, never "
                    f"point selection; got {len(segments)} columns"
                )
        return messages

    return check


def _check_time_axis(key: str) -> Callable[[Row], list[str]]:
    def check(row: Row) -> list[str]:
        composed = fixtures.digital_lanes()
        rendered = RenderedComponent(partials.render_lanes(composed))
        messages: list[str] = []
        if key == "Axis label":
            axis = next(
                (e for e in rendered.elements if "data-bw-axis-label" in e.attrs), None
            )
            if axis is None or axis.attrs.get("data-bw-axis-label") != "Capture time":
                messages.append("the axis renders the host-supplied label")
            if axis is not None and axis.attrs.get("data-bw-axis-unit") != "s":
                messages.append("the mode is disclosed BY the label (unit attribute)")
        elif key == "Sample rate":
            if "at 1 MHz" not in composed.acquisition_text:
                messages.append(
                    "the rate discloses via the acquisition suffix (rate = 1/axis step)"
                )
        elif key == "Trigger":
            triggers = [e for e in rendered.elements if "data-bw-trigger" in e.attrs]
            if not triggers:
                messages.append("the trigger marker renders from a non-null trigger time")
            elif (triggers[0].attrs.get("data-bw-trigger-sample")) != "500":
                messages.append("the trigger renders at its time")
            elif "trigger" not in (rendered._element_texts[rendered.elements.index(triggers[0])]):
                messages.append("the trigger marker is labelled 'trigger'")
            null_render = RenderedComponent(
                partials.render_lanes(fixtures.null_trigger_lanes())
            )
            if any("data-bw-trigger" in e.attrs for e in null_render.elements):
                messages.append("a null trigger renders no marker and fabricates no position")
        elif key == "Cursors":
            cursors = [e for e in rendered.elements if "data-bw-cursor" in e.attrs]
            if len(cursors) < 2:
                messages.append("at least two cursors are supported")
            if "Δt = 7 µs" not in rendered.text_content:
                messages.append("the seconds-mode Δt readout scales the unit (Δt = 7 µs)")
            sample_render = RenderedComponent(
                partials.render_lanes(fixtures.sample_mode_cursor_lanes())
            )
            if "Δt = 7 samples" not in sample_render.text_content:
                messages.append("sample-index mode reads the raw difference (Δt = 7 samples)")
            if (
                "Δt = 7 µs" in sample_render.text_content
                and "Δt = 7 samples" in sample_render.text_content
            ):
                messages.append("never both readouts at once")
        return messages

    return check


def _check_decoder(key: str) -> Callable[[Row], list[str]]:
    def check(row: Row) -> list[str]:
        composed = fixtures.digital_lanes()
        rendered = RenderedComponent(partials.render_lanes(composed))
        messages: list[str] = []
        lane_positions = [
            rendered.elements.index(e) for e in _lane_rows(rendered)
        ]
        if key == "Span rendering":
            spans = [e for e in rendered.elements if "data-bw-span" in e.attrs]
            if len(spans) != 4:
                messages.append(
                    "extents clip to the capture window (the fully-outside event "
                    f"does not render); got {len(spans)} spans"
                )
            for span in spans:
                # The L2 fold: float second-extents, never sample ints.
                start = float(span.attrs.get("data-bw-span-start") or "0")
                end = float(span.attrs.get("data-bw-span-end") or "0")
                if end <= start:
                    messages.append("the drawn width clamps at the minimum mark")
            zero_width_starts = {"0.0", "0.0006"}
            rendered_starts = {
                str(span.attrs.get("data-bw-span-start")) for span in spans
            }
            if not zero_width_starts <= rendered_starts:
                messages.append(
                    "a zero-width [t, t) event renders the minimum mark — including "
                    "the t=0 event (the L1 fold)"
                )
            decoder_rows = [
                e for e in _lane_rows(rendered) if e.attrs.get("data-bw-lane-kind") == "decoder"
            ]
            if decoder_rows and lane_positions:
                last_channelish = max(
                    rendered.elements.index(e)
                    for e in _lane_rows(rendered)
                    if e.attrs.get("data-bw-lane-kind") in ("channel", "group")
                )
                if rendered.elements.index(decoder_rows[0]) < last_channelish:
                    messages.append(
                        "decoder lanes render BENEATH the channel and bus rows"
                    )
        elif key == "Payload":
            payloads = rendered.texts_of_elements(class_hook="bw-lanes__payload")
            for expected in ("0x55", "0xAA", "0x00"):
                if expected not in payloads:
                    messages.append(f"the span carries the event's payload verbatim ({expected})")
        elif key == "Disclosure":
            labels = rendered.texts_of_elements(class_hook="bw-lanes__label")
            if not any("UART-REF · 115200 8N1" in text for text in labels):
                messages.append(
                    "the row's label names the decoder and its settings verbatim"
                )
        elif key == "Never orphan":
            hidden_source = RenderedComponent(
                partials.render_lanes(fixtures.hidden_source_decoder_lanes())
            )
            if any("data-bw-span" in e.attrs for e in hidden_source.elements):
                messages.append(
                    "an event whose source channel is hidden does NOT render"
                )
            waiting = [
                e for e in hidden_source.elements if "data-bw-waiting" in e.attrs
            ]
            if not waiting:
                messages.append("the row discloses the wait visibly")
            canonical_waiting = [
                e for e in rendered.elements if "data-bw-waiting" in e.attrs
            ]
            if not canonical_waiting:
                messages.append(
                    "a declared lane with NO events keeps the awaiting-render note"
                )
        return messages

    return check


_LANES_RULE_CHECKERS: dict[str, Callable[[Row], list[str]]] = {}
for _key in ("Uniform bands", "Pinned labels", "Hidden lanes", "Hiding is disclosure"):
    _LANES_RULE_CHECKERS[_key] = _check_lane_layout(_key)
for _key in ("1", "0", "x` and `z", "Monochrome discriminability"):
    _LANES_RULE_CHECKERS[_key] = _check_state_rendering(_key)
for _key in ("Bus lane", "Radix", "Member order", "Unknown bus"):
    _LANES_RULE_CHECKERS[_key] = _check_groups_buses(_key)
for _key in ("Every transition survives", "Glitch mark", "No sample dropping"):
    _LANES_RULE_CHECKERS[_key] = _check_decimation(_key)
for _key in ("Axis label", "Sample rate", "Trigger", "Cursors"):
    _LANES_RULE_CHECKERS[_key] = _check_time_axis(_key)
for _key in ("Span rendering", "Payload", "Disclosure", "Never orphan"):
    _LANES_RULE_CHECKERS[_key] = _check_decoder(_key)


def _lanes_rule_factory(key: str) -> RuleProofArtifact:
    checker = _LANES_RULE_CHECKERS.get(key)
    if checker is None:
        raise KeyError(f"no lanes rule checker for {key!r}")
    return RuleProofArtifact(key, checker)


# ---------------------------------------------------------------------------
# §B.2 / §B.4 / §C.1 — the ten behaviour rows (G1d design record §1.2),
# proven by DRIVING the composition state machine: transitions, fire
# attempts, refusals — never render-only structure checks (the G1b kill
# rule). Each checker ports its TS assertion body (safety-proof.test.tsx,
# reading-states-proof.test.tsx, DeviceWorkbench.test.tsx); the machinery
# itself is pinned by tests/ui_html/test_compositions.py.


def _button_texts(rendered: RenderedComponent) -> list[str]:
    """The button elements' subtree texts — paired by position (identity),
    never ``index()``: twin controls share tag+attrs, so dataclass equality
    would resolve to the wrong sibling's text."""
    return [
        text
        for element, text in zip(rendered.elements, rendered._element_texts, strict=True)
        if element.tag == "button"
    ]


def _own_text_of(rendered: RenderedComponent, element: Element) -> str:
    for candidate, text in zip(rendered.elements, rendered._element_texts, strict=True):
        if candidate is element:
            return text
    raise AssertionError("element not in render")


def _de_energised(scene: compositions.WorkbenchState) -> compositions.WorkbenchState:
    return dataclasses.replace(
        scene,
        output=compositions.OutputState(energised=False, trip=scene.output.trip),
    )


_SCENES: tuple[tuple[str, Callable[[], compositions.WorkbenchState]], ...] = (
    ("psu-07", compositions.psu_scene),
    ("daq-47", compositions.daq_scene),
)


def _check_r_energise(row: Row) -> list[str]:
    messages: list[str] = []
    for name, scene_factory in _SCENES:
        scene = scene_factory()
        # The vacuous-pass control: both scenes must contain an
        # energy-sourcing and an energy-removing action.
        rendered = RenderedComponent(compositions.render_workbench(scene))
        texts = _button_texts(rendered)
        if not any("Energise output" in text for text in texts):
            messages.append(f"{name}: no energy-sourcing action renders (the vacuous-pass control)")
        if not any("De-energise output" in text for text in texts):
            messages.append(f"{name}: no energy-removing action renders (the vacuous-pass control)")
        # Arm the energise control ⇒ no dispatch; the confirm text carries
        # the effect, the exact value+unit, and the target; the second
        # explicit action dispatches with the staged value.
        unarmed = _de_energised(scene)
        if not isinstance(compositions.attempt_fire(unarmed, "energise"), compositions.Refused):
            messages.append(f"{name}: firing an un-armed energise must never dispatch")
        armed = compositions.reduce(unarmed, compositions.Arm("energise"))
        armed_render = RenderedComponent(compositions.render_workbench(armed))
        confirm_text = armed_render.texts_of_elements(class_hook="bw-confirm__text")
        if not any(
            "the output will be energised" in text
            and f"{scene.staged_value:g} V" in text
            and f"{scene.device_id.upper()} output" in text
            for text in confirm_text
        ):
            messages.append(
                f"{name}: the confirm text must state the effect, the exact "
                f"value with unit ({scene.staged_value:g} V) and the target"
            )
        fired = compositions.attempt_fire(armed, "energise")
        if fired != compositions.Dispatched("energise", scene.staged_value):
            messages.append(f"{name}: the second explicit action must dispatch the staged value")
        # A set-point change on an ENERGISED output is energy-sourcing.
        if not isinstance(compositions.attempt_fire(scene, "set-point"), compositions.Refused):
            messages.append(
                f"{name}: applying a set-point on an energised output must stage, not dispatch"
            )
        armed_set = compositions.reduce(scene, compositions.Arm("set-point"))
        set_render = RenderedComponent(compositions.render_workbench(armed_set))
        if not any(
            "the set-point of the energised output will change" in text
            for text in set_render.texts_of_elements(class_hook="bw-confirm__text")
        ):
            messages.append(f"{name}: the set-point confirm must state the set-point effect")
        if compositions.attempt_fire(armed_set, "set-point") != compositions.Dispatched(
            "set-point", scene.staged_value
        ):
            messages.append(f"{name}: the set-point confirm must dispatch the staged value")
        # On a de-energised output the apply is one action with no confirm
        # subtree.
        if compositions.attempt_fire(unarmed, "set-point") != compositions.Dispatched(
            "set-point", scene.staged_value
        ):
            messages.append(
                f"{name}: a set-point on a de-energised output applies in one action"
            )
        if "Confirm: Apply staged set-point" in RenderedComponent(
            compositions.render_workbench(unarmed)
        ).text_content:
            messages.append(
                f"{name}: no confirm subtree renders for the de-energised set-point apply"
            )
    # The laundering witness (the m4 mutation's target): the staged value
    # 13.0 while the tile's set line still reads the gateway-observed 12.5 —
    # a renderer deriving the set line from the staged input reds here.
    scene = dataclasses.replace(compositions.psu_scene(), staged_value=13.0)
    set_lines = RenderedComponent(compositions.render_workbench(scene)).texts_of_elements(
        class_hook="bw-reading__set"
    )
    if "Set 12.5 V" not in set_lines or "Set 13.0 V" in set_lines:
        messages.append(
            "the tile's set line must read the gateway-observed set, never the staged input"
        )
    return messages


def _check_r_deenergise(row: Row) -> list[str]:
    messages: list[str] = []
    for name, scene_factory in _SCENES:
        for guard_state in ("healthy", "trip", "no-authority", "both"):
            scene = dataclasses.replace(
                scene_factory(),
                output=compositions.OutputState(
                    energised=False,
                    trip=guard_state in ("trip", "both"),
                ),
                authority=guard_state not in ("no-authority", "both"),
            )
            if compositions.attempt_fire(scene, "de-energise") != compositions.Dispatched(
                "de-energise", None
            ):
                messages.append(
                    f"{name}/{guard_state}: the off action must dispatch in one action"
                )
            rendered = RenderedComponent(compositions.render_workbench(scene))
            if "Confirm: De-energise" in rendered.text_content:
                messages.append(f"{name}/{guard_state}: the off action must never carry a confirm")
            if "will be de-energised" in rendered.text_content:
                messages.append(f"{name}/{guard_state}: no de-energise confirm text may render")
            # The control is never disabled by any guard reason.
            off_buttons = [
                element
                for element in rendered.elements
                if element.tag == "button"
                and "De-energise output" in _own_text_of(rendered, element)
            ]
            if not off_buttons:
                messages.append(f"{name}/{guard_state}: the off control does not render")
                continue
            off = off_buttons[0]
            if "disabled" in off.attrs or "data-bw-disabled-reason" in off.attrs:
                messages.append(
                    f"{name}/{guard_state}: nothing may stand between the operator "
                    "and de-energising"
                )
    return messages


def _check_r_protect(row: Row) -> list[str]:
    messages: list[str] = []
    scene = compositions.psu_scene()
    # Trip ⇒ the energise control renders disabled with protection-active
    # and its §C.2 visible label; de-energise stays enabled.
    tripped = compositions.reduce(scene, compositions.TripArrives())
    rendered = RenderedComponent(compositions.render_workbench(tripped))
    energise = next(
        (
            element
            for element in rendered.elements
            if element.tag == "button"
            and "Energise output" in _own_text_of(rendered, element)
        ),
        None,
    )
    if energise is None:
        return ["the trip render lost the energise control"]
    if "disabled" not in energise.attrs:
        messages.append("the energise control must render disabled while a trip is active")
    if energise.attrs.get("data-bw-disabled-reason") != "protection-active":
        messages.append("the energise control must carry data-bw-disabled-reason=protection-active")
    labels = rendered.texts_of_elements_with_attribute("data-bw-disabled-label")
    if "Protection trip active" not in labels:
        messages.append("the trip's §C.2 visible label must render beside the control")
    off = next(
        (
            element
            for element in rendered.elements
            if element.tag == "button"
            and "De-energise output" in _own_text_of(rendered, element)
        ),
        None,
    )
    if off is None or "disabled" in off.attrs:
        messages.append("the trip guard never reaches the energy-removing action")
    # Guard-while-armed (the fire-time rule): arm, the trip arrives ⇒ the
    # ARMED confirm button itself is disabled, the fire REFUSES without
    # dispatch; no auto-disarm, Cancel stays enabled, the departing guard
    # re-enables and the fire then dispatches.
    armed = compositions.reduce(_de_energised(scene), compositions.Arm("energise"))
    guarded = compositions.reduce(armed, compositions.TripArrives())
    if guarded.confirm != "armed":
        messages.append("no auto-disarm: the armed state must survive the guard")
    guarded_render = RenderedComponent(compositions.render_workbench(guarded))
    confirm = next(
        (
            element
            for element in guarded_render.elements
            if element.tag == "button"
            and "Confirm: Energise output" in _own_text_of(guarded_render, element)
        ),
        None,
    )
    if confirm is None:
        messages.append("the armed confirm button does not render under the guard")
    else:
        if "disabled" not in confirm.attrs:
            messages.append("the ARMED confirm button itself must render disabled under the guard")
        if confirm.attrs.get("data-bw-disabled-reason") != "protection-active":
            messages.append("the armed confirm must carry protection-active")
    if compositions.attempt_fire(guarded, "energise") != compositions.Refused(
        "protection-active"
    ):
        messages.append("the fire path must re-check the guard and refuse without dispatch")
    cancel = next(
        (
            element
            for element in guarded_render.elements
            if element.tag == "button"
            and "Cancel" in _own_text_of(guarded_render, element)
        ),
        None,
    )
    if cancel is None or "disabled" in cancel.attrs:
        messages.append("Cancel stays enabled while armed and guarded")
    cleared = compositions.reduce(guarded, compositions.TripClears())
    if compositions.attempt_fire(cleared, "energise") != compositions.Dispatched(
        "energise", scene.staged_value
    ):
        messages.append("the departing guard re-enables and the fire then dispatches")
    # Combined trip+authority-lost presents protection-active, NOT the
    # no-authority label (the trip is the present blocker).
    combined = compositions.reduce(
        compositions.reduce(armed, compositions.TripArrives()), compositions.AuthorityLost()
    )
    combined_render = RenderedComponent(compositions.render_workbench(combined))
    combined_confirm = next(
        (
            element
            for element in combined_render.elements
            if element.tag == "button"
            and "Confirm: Energise output" in _own_text_of(combined_render, element)
        ),
        None,
    )
    if combined_confirm is None or combined_confirm.attrs.get(
        "data-bw-disabled-reason"
    ) != "protection-active":
        messages.append("the combined state must present protection-active")
    if "No lease or policy authority" in combined_render.texts_of_elements_with_attribute(
        "data-bw-disabled-label"
    ):
        messages.append("the no-authority label must not present under an active trip")
    # Property (e): every [data-bw-disabled-reason] element in the trip
    # render and in the no-authority render carries its key's visible label.
    for guard_name, guard_state in (
        ("trip", compositions.reduce(scene, compositions.TripArrives())),
        ("no-authority", compositions.reduce(scene, compositions.AuthorityLost())),
    ):
        guard_render = RenderedComponent(compositions.render_workbench(guard_state))
        keys = {
            str(element.attrs["data-bw-disabled-reason"])
            for element in guard_render.elements
            if "data-bw-disabled-reason" in element.attrs
        }
        if not keys:
            messages.append(f"the {guard_name} render must carry disabled controls")
            continue
        guard_labels = guard_render.texts_of_elements_with_attribute("data-bw-disabled-label")
        for key in keys:
            if compositions.GUARD_LABELS.get(key) not in guard_labels:
                messages.append(
                    f"the {guard_name} render must carry the visible label for {key}"
                )
    return messages


def _check_sr_b1(row: Row) -> list[str]:
    messages: list[str] = []
    scene = compositions.psu_scene()
    # The warning message renders anchored in its affected context (panel)
    # across an unrelated re-render (persistence).
    warning = next(m for m in scene.messages if m.severity == "warning")
    for state_name, state in (
        ("initial", scene),
        ("after an unrelated re-render", compositions.reduce(scene, compositions.Unrelated())),
    ):
        rendered = RenderedComponent(compositions.render_workbench(state))
        panel_texts = rendered.texts_of_elements(class_hook="bw-panel__body")
        if not any(warning.text in text for text in panel_texts):
            messages.append(
                f"the warning message must stay anchored in its panel {state_name}"
            )
    # The toast channel accepts only neutral/success/advisory severities —
    # typed shut; the m7 mutation loosens the Literal and this reflection
    # reds (unrepresentable-bad-state, not policy-checked).
    hints = get_type_hints(compositions.ToastData)
    if set(get_args(hints["severity"])) != {"neutral", "success", "advisory"}:
        messages.append(
            "the transient toast channel's severity type must admit exactly "
            "neutral, success and advisory"
        )
    for severity in ("neutral", "success", "advisory"):
        html = compositions.render_toast(compositions.ToastData(severity=severity, text="ok"))
        if f'data-severity="{severity}"' not in html:
            messages.append(f"a {severity} toast must render through the transient channel")
    # warning/critical/trip never route to the transient channel: they
    # render anchored, and no toast element carries them.
    for severity in ("warning", "critical", "trip"):
        variant = dataclasses.replace(
            scene,
            messages=(dataclasses.replace(scene.messages[0], severity=severity),),  # type: ignore[arg-type]
        )
        rendered = RenderedComponent(compositions.render_workbench(variant))
        if any("data-bw-toast" in element.attrs for element in rendered.elements):
            messages.append(f"a {severity} message must never route to the transient channel")
        if not any(
            scene.messages[0].text in text
            for text in rendered.texts_of_elements(class_hook="bw-panel__body")
        ):
            messages.append(f"a {severity} message must remain present in the affected context")
    return messages


def _single_reading_scene(severity: str) -> compositions.WorkbenchState:
    scene = compositions.psu_scene()
    return dataclasses.replace(
        scene,
        readings=(
            compositions.ReadingSlot(
                id="voltage",
                label="Supply voltage",
                value="12.04",
                unit="V",
                severity=severity,  # type: ignore[arg-type]
                quality="Verified",
                freshness_ms=120.0,
                max_age_ms=150.0,
            ),
        ),
    )


def _check_sr_b2(row: Row) -> list[str]:
    messages: list[str] = []
    # The warning/critical/trip composition states each carry icon +
    # explicit label + border hook + text on the affected reading.
    for severity in ("warning", "critical", "trip"):
        rendered = RenderedComponent(
            compositions.render_workbench(_single_reading_scene(severity))
        )
        tile = next(
            (
                element
                for element in rendered.elements
                if "bw-reading" in element.class_tokens
                and element.attrs.get("data-severity") == severity
            ),
            None,
        )
        if tile is None:
            messages.append(f"a {severity} reading tile does not render")
            continue
        # border hook: data-severity on the tile (the CSS border/glow hook).
        severity_span = next(
            (
                element
                for element in rendered.elements
                if "bw-reading__severity" in element.class_tokens
            ),
            None,
        )
        if severity_span is None:
            messages.append(f"the {severity} reading must carry its severity span")
            continue
        if severity not in _own_text_of(rendered, severity_span):
            messages.append(f"the {severity} reading must carry its explicit label")
        span_index = next(
            index
            for index, element in enumerate(rendered.elements)
            if element is severity_span
        )
        if not any(
            element.tag == "svg"
            for element in rendered.elements[span_index : span_index + 3]
        ):
            messages.append(f"the {severity} reading must carry an icon")
        if "Supply voltage" not in _own_text_of(rendered, tile):
            messages.append(f"the {severity} reading must carry text on the affected reading")
    # normal/success render no glow-carrying vocabulary (the CSS-structure
    # half was test_reading_tile_css_pins.py fold-row 11, retired with ui/
    # at G1e — the no-glow property itself transfers to the G2/G3 host CSS,
    # drift-and-obligations row 26).
    for severity in ("neutral", "success"):
        rendered = RenderedComponent(
            compositions.render_workbench(_single_reading_scene(severity))
        )
        if any("data-bw-glow" in element.attrs for element in rendered.elements) or any(
            "glow" in token
            for element in rendered.elements
            for token in element.class_tokens
        ):
            messages.append(f"a {severity} reading must not render glow vocabulary")
    return messages


def _check_sr_b3(row: Row) -> list[str]:
    messages: list[str] = []
    scene = compositions.psu_scene()
    advisory = next(m for m in scene.messages if m.severity == "advisory")
    # dismiss-message removes the bubble while the condition bit stays set…
    fired = compositions.reduce(scene, compositions.AuthorityLost())
    dismissed = compositions.reduce(fired, compositions.DismissMessage(advisory.id))
    stored = next(m for m in dismissed.messages if m.id == advisory.id)
    if not stored.active:
        messages.append("dismissal must not clear the underlying condition bit")
    if stored.acknowledged:
        messages.append("dismissal must not acknowledge the condition (m5's mutant)")
    rendered = RenderedComponent(compositions.render_workbench(dismissed))
    bubbles = rendered.texts_of_elements(class_hook="bw-alert-bubble__content")
    if any(advisory.text in text for text in bubbles):
        messages.append("a dismissed message must not render its bubble")
    # …and re-renders on the next transition of its condition.
    refired = compositions.reduce(
        compositions.reduce(dismissed, compositions.AuthorityRegained()),
        compositions.AuthorityLost(),
    )
    refired_render = RenderedComponent(compositions.render_workbench(refired))
    if not any(
        advisory.text in text
        for text in refired_render.texts_of_elements(class_hook="bw-alert-bubble__content")
    ):
        messages.append("the dismissed message must re-render on the next transition")
    # acknowledge-attempt without authority refuses.
    no_auth = compositions.reduce(scene, compositions.AuthorityLost())
    attempted = compositions.reduce(no_auth, compositions.AcknowledgeAttempt(advisory.id))
    if next(m for m in attempted.messages if m.id == advisory.id).acknowledged:
        messages.append("acknowledgement without authority must be refused")
    # With authority the separately-labelled act succeeds.
    authorised = compositions.reduce(scene, compositions.AcknowledgeAttempt(advisory.id))
    if not next(m for m in authorised.messages if m.id == advisory.id).acknowledged:
        messages.append("an authorised acknowledgement must set the bit")
    # Acknowledgement is separately labelled from dismissal — never the same
    # control.
    base_render = RenderedComponent(compositions.render_workbench(scene))
    button_texts = _button_texts(base_render)
    if not any("Acknowledge" in text for text in button_texts):
        messages.append("the acknowledge control must render with its own label")
    for text in button_texts:
        if "Acknowledge" in text and "Dismiss" in text:
            messages.append("dismissal and acknowledgement must be separate controls")
    return messages


def _check_st_1(row: Row) -> list[str]:
    messages: list[str] = []
    scene = compositions.daq_scene()
    excitation = next(r for r in scene.readings if r.max_age_ms is None)
    # A stream-cadence source (no window supplied) renders NO staleness
    # verdict in any render — steady state or after transitions — and
    # asserts freshness nowhere (no silence-inference).
    for state_name, state in (
        ("steady state", scene),
        (
            "after the source goes quiet",
            compositions.reduce(scene, compositions.ReadingWentStale(excitation.id)),
        ),
    ):
        rendered = RenderedComponent(compositions.render_workbench(state))
        if any("data-bw-stale" in element.attrs for element in rendered.elements):
            messages.append(
                f"a stream-cadence source must render no staleness verdict ({state_name})"
            )
        if excitation.id in state.last_transition:
            messages.append(
                "a source with no commissioned window can never cross (no silence-inference)"
            )
    # The verdict's cadence input is the polled max_age_ms only: the psu
    # voltage well INSIDE the window renders fresh, and crossing past the
    # window (the transition) turns it stale — the verdict tracks the
    # window, never a renderer default. (The boundary value itself is ST-2's
    # own arm, so this checker keeps off the equality case.)
    psu = compositions.psu_scene()
    inside = dataclasses.replace(
        psu,
        readings=(
            dataclasses.replace(psu.readings[0], freshness_ms=100.0, max_age_ms=150.0),
            *psu.readings[1:],
        ),
    )
    inside_render = RenderedComponent(compositions.render_workbench(inside))
    if any(
        "data-bw-stale" in element.attrs
        for element in inside_render.elements
        if "bw-reading" in element.class_tokens
    ):
        messages.append("freshness inside the commissioned window is fresh, not stale")
    crossed = compositions.reduce(inside, compositions.ReadingWentStale("voltage"))
    crossed_render = RenderedComponent(compositions.render_workbench(crossed))
    if not any(
        element.attrs.get("data-bw-stale") == "true"
        for element in crossed_render.elements
        if "bw-reading" in element.class_tokens
    ):
        messages.append("crossing past the commissioned window must turn the verdict stale")
    return messages


def _check_st_2(row: Row) -> list[str]:
    messages: list[str] = []
    psu = compositions.psu_scene()

    def voltage(freshness: float | None, window: float | None) -> RenderedComponent:
        scene = dataclasses.replace(
            psu,
            readings=(
                dataclasses.replace(
                    psu.readings[0], freshness_ms=freshness, max_age_ms=window
                ),
                *psu.readings[1:],
            ),
        )
        return RenderedComponent(compositions.render_workbench(scene))

    def stale_marker_present(rendered: RenderedComponent) -> bool:
        return any(
            element.attrs.get("data-bw-stale") == "true"
            for element in rendered.elements
            if "bw-reading" in element.class_tokens
        )

    # The boundary arms, each asserted through the rendered tile (no marker
    # for fresh/no-verdict, marker for stale).
    if stale_marker_present(voltage(150, 150)):
        messages.append(
            "staleness(150,150) must be fresh (strictly greater; equality is not stale)"
        )
    if not stale_marker_present(voltage(151, 150)):
        messages.append("staleness(151,150) must be stale (the boundary is the disavowal line)")
    if not stale_marker_present(voltage(1, 0)):
        messages.append(
            "max_age_ms=0 is valid fresh-acquisition-only semantics: staleness(1,0) is stale"
        )
    for freshness, window in ((float("nan"), 150.0), (120.0, -5.0)):
        rendered = voltage(freshness, window)
        if stale_marker_present(rendered):
            messages.append(
                f"garbage inputs ({freshness!r},{window!r}) must render no verdict "
                "(a fabricated verdict is the lie class)"
            )
        quality_text = rendered.texts_of_elements(class_hook="bw-reading__quality")[0]
        if "fresh" in quality_text.lower():
            messages.append("no-verdict must assert freshness nowhere (case-insensitive)")
    # The predicate itself, once, at the exact arms.
    if staleness.staleness(150, 150) != "fresh" or staleness.staleness(151, 150) != "stale":
        messages.append("the predicate boundary must be strictly greater")
    return messages


def _check_st_3(row: Row) -> list[str]:
    messages: list[str] = []
    psu = compositions.psu_scene()

    def scene_with(
        freshness: float | None, window: float | None, quality: str = "Verified"
    ) -> RenderedComponent:
        scene = dataclasses.replace(
            psu,
            readings=(
                dataclasses.replace(
                    psu.readings[0],
                    freshness_ms=freshness,
                    max_age_ms=window,
                    quality=quality,
                ),
                *psu.readings[1:],
            ),
        )
        return RenderedComponent(compositions.render_workbench(scene))

    # No known cadence ⇒ no verdict and no freshness claim anywhere.
    no_cadence = scene_with(120.0, None)
    if any("data-bw-stale" in element.attrs for element in no_cadence.elements):
        messages.append("no known cadence must render no staleness verdict")
    if "stale" in no_cadence.text_content.lower().replace("staged", ""):
        messages.append("no known cadence must not claim staleness anywhere")
    # freshness_ms is None renders Unavailable and is not stale.
    null_freshness = scene_with(None, 150.0)
    if "Unavailable" not in null_freshness.text_content:
        messages.append("a null freshness must render Unavailable")
    if any("data-bw-stale" in element.attrs for element in null_freshness.elements):
        messages.append("a null freshness is not stale")
    # A device quality string renders verbatim in the quality slot and is
    # never overwritten or augmented by the computed verdict — two channels,
    # never laundered into one (fold A1's stronger form): the quality
    # element's own text MINUS the marker span equals exactly
    # "{quality} · {freshness}". A renderer appending the verdict's text
    # into the quality line (the s7 sabotage keeps the marker span AND
    # inlines the text) reds here and only here; the marker's
    # PRESENCE-while-stale stays ST-4's own claim (m6 drops the marker).
    narrow_state = dataclasses.replace(
        psu,
        readings=(
            dataclasses.replace(
                psu.readings[0], freshness_ms=301.0, max_age_ms=150.0, quality="device-good"
            ),
            *psu.readings[1:],
        ),
    )
    html = compositions.render_workbench(narrow_state)
    reading = narrow_state.readings[0]
    expected_line = f"{reading.quality} · {reading.freshness_text}"
    quality_blocks = re.findall(
        r'<p class="bw-reading__quality">(.*?)</p>', html, re.DOTALL
    )
    device_blocks = [block for block in quality_blocks if "device-good" in block]
    if not device_blocks:
        messages.append("the device quality string must render verbatim in the quality slot")
        return messages
    for block in device_blocks:
        without_marker_spans = re.sub(r"<span[^>]*>.*?</span>", "", block, flags=re.DOTALL)
        direct_text = re.sub(r"<[^>]+>", "", without_marker_spans)
        direct_text = re.sub(r"\s+", " ", direct_text).strip()
        if direct_text != expected_line:
            messages.append(
                "the quality element's text minus the marker span must equal "
                f"exactly {expected_line!r} — the computed verdict never "
                f"launders into the quality string; got {direct_text!r}"
            )
    return messages


def _check_st_4(row: Row) -> list[str]:
    messages: list[str] = []
    psu = compositions.psu_scene()
    stale_scene = dataclasses.replace(
        psu,
        readings=(
            dataclasses.replace(psu.readings[0], freshness_ms=301.0, max_age_ms=150.0),
            *psu.readings[1:],
        ),
    )
    rendered = RenderedComponent(compositions.render_workbench(stale_scene))
    # A stale tile carries the dimming class hook + data-bw-stale="true" +
    # the visible `stale` marker appended to the quality line; the marker is
    # never missing while the attribute renders (m6's mutant drops the
    # marker and keeps the attribute).
    tile = next(
        (
            element
            for element in rendered.elements
            if "bw-reading" in element.class_tokens
            and element.attrs.get("data-bw-stale") == "true"
        ),
        None,
    )
    if tile is None:
        return ["a stale reading must carry data-bw-stale=true"]
    if "bw-reading--stale" not in tile.class_tokens:
        messages.append("a stale tile must carry the dimming class hook")
    markers = rendered.texts_of_elements(class_hook="bw-reading__stale-marker")
    if not markers or not any("stale" in marker for marker in markers):
        messages.append(
            "a stale reading never renders without its marker (the OTDP §5 rule, "
            "at the presentation boundary)"
        )
    # The fresh→stale transition carries exactly ONE status live-region
    # announcement (the last_transition ledger): on the crossing render,
    # absent on the steady stale re-render and on a duplicate no-change
    # event — coalesced, once.
    fresh_scene = dataclasses.replace(
        psu,
        readings=(
            dataclasses.replace(psu.readings[0], freshness_ms=120.0, max_age_ms=150.0),
            *psu.readings[1:],
        ),
    )
    crossed = compositions.reduce(fresh_scene, compositions.ReadingWentStale("voltage"))
    crossing = RenderedComponent(compositions.render_workbench(crossed))
    announcements = crossing.texts_of_elements(class_hook="bw-workbench__announcements")
    if len(announcements) != 1 or "stale" not in announcements[0]:
        messages.append("the fresh→stale crossing render must carry exactly one announcement")
    for state_name, state in (
        ("the steady stale re-render", compositions.reduce(crossed, compositions.Unrelated())),
        (
            "a duplicate no-change event",
            compositions.reduce(crossed, compositions.ReadingWentStale("voltage")),
        ),
    ):
        steady = RenderedComponent(compositions.render_workbench(state))
        if steady.texts_of_elements(class_hook="bw-workbench__announcements"):
            messages.append(f"the announcement must be absent on {state_name} (coalesced, once)")
    # The data-table row arm: tr[data-bw-stale] + row dimming + marker;
    # fresh rows unmarked.
    stale_rows = [
        element
        for element in rendered.elements
        if element.tag == "tr" and element.attrs.get("data-bw-stale") == "true"
    ]
    if not stale_rows:
        messages.append("the stale reading's table row must carry data-bw-stale")
    for element in stale_rows:
        if "bw-table-row--stale" not in element.class_tokens:
            messages.append("the stale table row must carry the row dimming class")
        if "stale" not in _own_text_of(rendered, element):
            messages.append("the stale table row must carry the visible marker")
    for element in rendered.elements:
        if (
            element.tag == "tr"
            and "data-bw-stale" not in element.attrs
            and "stale" in _own_text_of(rendered, element)
        ):
            messages.append("a fresh table row must not carry the marker")
    return messages


_COMPOSITION_RULE_CHECKERS: dict[str, Callable[[Row], list[str]]] = {
    "R-ENERGISE-1": _check_r_energise,
    "R-DEENERGISE-1": _check_r_deenergise,
    "R-PROTECT-1": _check_r_protect,
    "SR-B1": _check_sr_b1,
    "SR-B2": _check_sr_b2,
    "SR-B3": _check_sr_b3,
    "ST-1": _check_st_1,
    "ST-2": _check_st_2,
    "ST-3": _check_st_3,
    "ST-4": _check_st_4,
}


def _composition_rule_factory(key: str) -> RuleProofArtifact:
    checker = _COMPOSITION_RULE_CHECKERS.get(key)
    if checker is None:
        raise KeyError(f"no composition rule checker for {key!r}")
    return RuleProofArtifact(key, checker)



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
    "e-2-0-pass-2-composition-channel-hints": HintRowArtifact,
    "e-2-1-slot-mapping": SlotValueArtifact,
    "e-2-3-y-axis-assignment": _plot_rule_factory,
    "e-2-4-reference-lines": _plot_rule_factory,
    "e-2-5-acquisition-disclosure": _plot_rule_factory,
    "e-2-6-trace-provenance": _plot_rule_factory,
    "e-4-1-lane-layout": _lanes_rule_factory,
    "e-4-2-state-rendering": _lanes_rule_factory,
    "e-4-3-groups-and-buses": _lanes_rule_factory,
    "e-4-4-edge-preserving-decimation-normative": _lanes_rule_factory,
    "e-4-5-time-axis": _lanes_rule_factory,
    "e-4-6-decoder-lanes": _lanes_rule_factory,
    "b-2-state-rules": _composition_rule_factory,
    "b-4-staleness": _composition_rule_factory,
    "c-1-safety-rules": _composition_rule_factory,
}

#: Every row-id the registrars register (158 of G1b + the ten G1d behaviour
#: rows = the full 168) — derived from the registrar coverage, so the
#: completeness meta arm (set equality against the registry) and the
#: registration share one mechanism.
def _registered_row_ids() -> frozenset[str]:
    ids: set[str] = set()
    for slug in _REGISTRARS:
        for key in _KEYS_BY_SLUG[slug]:
            if slug == "e-1-components" and key in _PENDING_COMPONENTS:
                continue
            ids.add(f"{slug}::{key}")
    return frozenset(ids)


REGISTERED_ROW_IDS: frozenset[str] = _registered_row_ids()

#: Historical alias for the G1b-era name; the derivation is the same
#: mechanism, now covering the full population.
G1B_ROW_IDS: frozenset[str] = REGISTERED_ROW_IDS


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
    "GLOBALS_CSS",
    "IconPartialArtifact",
    "LabelRenderArtifact",
    "ModeRowArtifact",
    "REGISTERED_ROW_IDS",
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


