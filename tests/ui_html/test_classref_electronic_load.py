"""The electronic_load class reference (L15 of the class sweep; design
record
``.claude/deep-review/2026-10-19-classref-l15-electronic-load-design.md``):
the mockup-consistency arm (A3) and the pattern-library input-page
composition with its drift guard — plus the class's own arm, the
direction pin (A8).

A3, sixth class of the sweep — the sweep's first energy-ADMITTING
class, the PSU's mirror. The mockup
(``docs/internal/ui-styleguide-mockups/class-electronic_load.html``) is
authored WITH the reference (the dmm convention's fourth instance, with
the §E.1 hooks and the placement contract from birth); the reference is
the data; this test is the bridge, keyed on the shared census instrument
(``tests/ui_html/classref_census.py``). Like dmm there is NO derived
fixture: the mockup is authored to the committed OTDP class example's
own shape (2 sink channels x 3 declared quantities = 6 tiles), so the
census resolves over the committed example directly. The kill is
two-directional by construction: a mockup edit that changes a hook
count reds against the resolved expectation, and a reference edit that
changes the derivation (a count expression, the plot binding, the
channels slot's role) reds against the mockup's counts. A mockup edit
that does NOT redden the test is the instrument failing — report,
never a quiet pass (the record's A3 wording).

A8 — the direction pin, this record's own arm (RC-L15-3). The class's
one hard question is which side of section C.1 the input-enable sits
on, and the record ruled it on substance: input-ENGAGE is the
flow-starting, hazard-creating action (R-ENERGISE-1's form — stage,
then a second explicit confirm naming effect, values and target);
input-DISENGAGE is the one ungated action (R-DEENERGISE-1, literally).
The dangerous misread — "a load removes energy from the DUT, so its
engage is the energy-removing action, so engage is ungated" — inverts
the rule's safety direction. The pin does not ENFORCE section C.1
(nothing this side of the safety-behaviours slice can); it makes the
two dangerous simplifications of the ruling visible as test failures
instead of silent authoring choices: mapping the output control to
``button`` (the ungated-engage misread) or to ``staging`` (the
gated-disengage misread), or dropping the forbid id, each red.

The expansion side (derive-ui/verify-ui censuses) is the batched SDK
leg's work and rides that train; what this file pins is the corpus
pair's structure — the reference document, its schema admission, and
the composition the host renders from it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from benchweave_ui_html import classref, patterns
from classref_census import (
    HOOKS,
    PLACEMENT_CONTAINER,
    PLACEMENT_TAG,
    HookCensus,
    hook_census,
    load_document,
    resolve_count,
)

from benchweave.presentation.classref import validate_reference_document
from benchweave.vendoring import corpus_root

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = REPO_ROOT / "standards/plugin-ui-class-reference/0.6.0"
REFERENCE = FAMILY_DIR / "class-electronic_load.json"
DESCRIPTOR = REPO_ROOT / "standards/otdp/0.2.4/examples/class-electronic_load.json"
MOCKUP = REPO_ROOT / "docs/internal/ui-styleguide-mockups/class-electronic_load.html"
CATALOG = REPO_ROOT / "standards/otdp/0.2.4/device-profile-catalog.json"
OUTPUT_ACTION = "otdp.electronic_load.output/1.0.0"
CONFIGURE_ACTION = "otdp.electronic_load.configure/1.0.0"


def _eload_census() -> dict[str, dict[str, int]]:
    return hook_census(MOCKUP)


def _sink_channels(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> list[dict[str, Any]]:
    """The channels the reference's channels slot resolves — the role the
    SLOT names (never a literal role string here), declaration order."""
    where_role = str(reference["slots"]["inputs"]["where_role"])
    return [c for c in descriptor["channels"] if str(c["role"]) == where_role]


def _structural_counters(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The closed counter set over (reference x fixture): every counter is
    an expression over the fixture's declared channels and their declared
    quantities — never a count imported from the mockup."""
    sink = _sink_channels(reference, descriptor)
    n_sink_channels = len(sink)
    n_scalar_variables = sum(len(c["quantities"]) for c in sink)
    return {
        "n_sink_channels": n_sink_channels,
        "n_scalar_variables": n_scalar_variables,
        "n_reading_tiles": n_scalar_variables,  # one tile per scalar variable
        "n_pages": len(reference["pages"]),
    }


def _resolved_input_expectation(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The expect.components rows scoped to the input page, resolved over
    the committed example (no derived fixture — the mockup is authored to
    the example's own shape)."""
    counters = _structural_counters(reference, descriptor)
    resolved: dict[str, int] = {}
    for name, row in reference["expect"]["components"].items():
        if row.get("per_page") == "input":
            resolved[name] = resolve_count(str(row["count"]), counters)
    return resolved


# --- A3: the mockup-consistency arm ---------------------------------------------


def test_the_mockup_carries_the_contract_hooks_in_both_themes() -> None:
    """The hook pass (RC-L11-3), from birth (the dmm convention, fourth
    authored-from-birth instance): both theme sections carry every hook
    family the census keys on — a hook absent from one theme is a
    composition break, not a style choice."""
    census = _eload_census()
    assert set(census) == {"light", "dark"}
    for theme, hooks in census.items():
        for hook in HOOKS:
            assert hooks[hook] >= 1, (theme, hook)


def test_mockup_hook_counts_equal_the_resolved_expectation() -> None:
    """A3, the load-bearing arm: per theme section, the mockup's hook
    counts EQUAL the reference's resolved expectation over the committed
    OTDP example (2 sink channels x 3 declared quantities = 6 tiles,
    1 plot, 1 table) — the counts derived on BOTH sides, never literals
    on either.

    Kill direction 1: edit the mockup's card count — the reading hook
    count diverges from the resolved expectation and this reds.
    Kill direction 2: edit the reference's derivation — a count
    expression, the plot binding, the channels slot's role — and the
    RESOLVED side diverges from the mockup and this reds."""
    reference = load_document(REFERENCE)
    fixture = load_document(DESCRIPTOR)
    resolved = _resolved_input_expectation(reference, fixture)
    assert set(resolved) == {"reading-tile", "engineering-plot", "data-table"}, resolved
    census = _eload_census()
    for theme, hooks in census.items():
        assert hooks["bw-reading"] == resolved["reading-tile"], theme
        assert hooks["bw-plot"] == resolved["engineering-plot"], theme
        assert hooks["bw-data-table"] == resolved["data-table"], theme


def test_every_hook_sits_on_its_contract_root_and_container() -> None:
    """The count-conserving-move kill (L11's refute proved it necessary;
    this class carries it from birth, both mutations named in the design
    §6 arm 3): every hook is on its §E.1 root element, the
    container-scoped hooks sit in their containers (``bw-reading`` only
    inside the readings row, ``bw-plot`` only inside the lower grid), and
    the staged-draw control card (a cannot_derive surface) carries NO
    ``bw-`` hook — a cannot-derive surface must never present as a
    reading. The count census alone is placement-blind: a hook moved
    count-conservingly onto the control card or out of its container
    reds HERE while the count arm stays green."""
    parser = HookCensus()
    parser.feed(MOCKUP.read_text(encoding="utf-8"))
    assert parser.placements, "the census recorded no hook placements"
    for theme, hook, tag, ancestors in parser.placements:
        assert tag == PLACEMENT_TAG[hook], (theme, hook, tag)
        container = PLACEMENT_CONTAINER.get(hook)
        if container is not None:
            # the stack at recording time holds ANCESTORS only (the
            # current element is appended after the hook check)
            assert any(
                container in ancestor_classes
                for _ancestor_tag, ancestor_classes in ancestors
            ), (theme, hook, container)
    # the staged-draw control card: one per theme, tag section, no hook carried
    assert len(parser.control_hooks) == 2, parser.control_hooks
    for theme, tag, carried in parser.control_hooks:
        assert tag == "section", (theme, tag)
        assert carried == (), (theme, carried)


def _census_of(html: str) -> HookCensus:
    """The census over a MUTATED copy of the mockup (the kill arms'
    vehicle — never the committed bytes)."""
    parser = HookCensus()
    parser.feed(html)
    return parser


def test_the_count_conserving_move_of_a_reading_onto_the_control_card_reds() -> None:
    """The count-conserving-move kill, demonstrated RED (the design's A3):
    a ``bw-reading`` moved from a readings card onto the staged-draw
    control card in BOTH themes — the count census stays green under the
    move (six per theme either way) and the PLACEMENT arm is what reds:
    the moved occurrence's tag is a section, not the §E.1 article root,
    and the readings container is no longer an ancestor."""
    html = MOCKUP.read_text(encoding="utf-8")
    moved = html.replace(
        'class="card warning bw-reading"', 'class="card warning"', 1
    ).replace('class="card warning bw-reading"', 'class="card warning"', 1)
    moved = moved.replace('class="card control"', 'class="card control bw-reading"')
    assert moved != html, "the mutation must change the mockup bytes"
    parser = _census_of(moved)
    # the count arm stays green under the move: still the resolved count
    reference = load_document(REFERENCE)
    fixture = load_document(DESCRIPTOR)
    resolved = _resolved_input_expectation(reference, fixture)
    for theme, hooks in parser.counts.items():
        assert hooks["bw-reading"] == resolved["reading-tile"], (theme, hooks)
    # the placement arm reds: the moved occurrence fails root AND container
    reds = 0
    for _theme, hook, tag, ancestors in parser.placements:
        root_ok = tag == PLACEMENT_TAG[hook]
        container = PLACEMENT_CONTAINER.get(hook)
        container_ok = container is None or any(
            container in ancestor_classes
            for _ancestor_tag, ancestor_classes in ancestors
        )
        if not (root_ok and container_ok):
            reds += 1
    assert reds >= 2, f"the move must red placement in both themes ({reds})"


def test_the_count_conserving_move_of_the_plot_out_of_the_lower_grid_reds() -> None:
    """The second named mutation, demonstrated RED: the ``bw-plot`` hook
    moved from the trend section onto the alert aside (outside the lower
    grid) in BOTH themes — counts conserve (one per theme) and the
    placement arm reds on both the root (aside, not section) and the
    container (the alert is not inside the lower grid)."""
    html = MOCKUP.read_text(encoding="utf-8")
    moved = html.replace(
        'class="plot bw-plot"', 'class="plot"'
    ).replace(
        'class="alert bw-alert-bubble"', 'class="alert bw-alert-bubble bw-plot"'
    )
    assert moved != html, "the mutation must change the mockup bytes"
    parser = _census_of(moved)
    for theme, hooks in parser.counts.items():
        assert hooks["bw-plot"] == 1, (theme, hooks)
    reds = 0
    for _theme, hook, tag, ancestors in parser.placements:
        if hook != "bw-plot":
            continue
        root_ok = tag == PLACEMENT_TAG[hook]
        container = PLACEMENT_CONTAINER.get(hook)
        container_ok = container is None or any(
            container in ancestor_classes
            for _ancestor_tag, ancestor_classes in ancestors
        )
        if not (root_ok and container_ok):
            reds += 1
    assert reds >= 2, f"the move must red placement in both themes ({reds})"


def test_both_themes_carry_the_identical_hook_census() -> None:
    """One composition, two themes: the hook census is theme-invariant."""
    census = _eload_census()
    assert census["light"] == census["dark"]


def test_the_alert_surface_is_one_per_theme_and_a_named_cannot_derive() -> None:
    """The mockup's alert aside is structure the composition renders and
    data the reference cannot derive: exactly one ``bw-alert-bubble`` per
    theme, and ``sink-margin-alert`` names it in the deviation ledger
    (the condition — draw vs configured current or power maximum — is
    commissioned policy, A02)."""
    reference = load_document(REFERENCE)
    ids = {str(row["id"]) for row in reference["cannot_derive"]}
    assert "sink-margin-alert" in ids
    census = _eload_census()
    for theme, hooks in census.items():
        assert hooks["bw-alert-bubble"] == 1, theme


def test_the_reference_selects_for_the_class_descriptor() -> None:
    """A4's green half, gateway-side: the electronic_load class example's
    profile now selects a corpus reference (``select_references``
    returned None before the class existed — the pair banked RED at
    design time on the L11 branch head c64f3d05 and again on this
    slice's base 11805ef9 by the L14 rotation, design record §6 arm 6)."""
    from benchweave.presentation.classref import select_references

    selected = select_references(corpus_root(), load_document(DESCRIPTOR))
    assert selected is not None and len(selected) == 1
    assert selected[0]["profile_id"] == "otdp.electronic_load/1.0.0"


# --- the reference's own shape ---------------------------------------------------


def test_the_reference_owns_the_sink_shaped_slots_and_pages() -> None:
    """RC-L15-2, machine-checked: the channels slot is ``inputs`` keyed
    on the role the SLOT names (``sink`` — a free string, zero widening);
    the readings page is ``input`` (the terminal name, while every action
    URN keeps the corpus's own action name ``output``); the layout is
    dc_psu's ratio — readings 12 raised, trend 7 recessed, table 5
    raised — the class's difference from dc_psu is content and
    direction, not geometry."""
    reference = load_document(REFERENCE)
    inputs = reference["slots"]["inputs"]
    assert inputs["kind"] == "channels"
    assert inputs["where_role"] == "sink"
    assert inputs["key"] == "id"
    assert inputs["label"] == "label"
    assert [page["id"] for page in reference["pages"]] == [
        "input",
        "configuration",
        "device-features",
    ]
    assert reference["pages"][0]["plot"] == {
        "kind": "time_series",
        "over_slot": "measure",
        "series": "numeric_variables",
    }
    layout = next(lp for lp in reference["layouts"] if lp["page_id"] == "input")
    assert [(s["id"], s["surface"], s["span"]) for s in layout["sections"]] == [
        ("readings", "raised", 12),
        ("trend", "recessed", 7),
        ("table", "raised", 5),
    ]


def test_the_output_slot_names_the_conditional_field_host_supplied() -> None:
    """§1.3's structural marker, machine-checked: the OTDP output schema
    requires ``configuration_id`` iff ``enabled: true`` — the corpus's own
    encoding of the directional asymmetry — and the reference makes it
    structural: ``output`` is a procedure slot carrying exactly
    ``host_supplied: ["configuration_id"]`` (the analyser's ``arm``
    convention, applied to the field the engage direction alone
    requires). The measure and configure slots carry none."""
    reference = load_document(REFERENCE)
    output = reference["slots"]["output"]
    assert output["kind"] == "procedure"
    assert output["action"] == OUTPUT_ACTION
    assert output["host_supplied"] == ["configuration_id"]
    assert "host_supplied" not in reference["slots"]["measure"]
    assert "host_supplied" not in reference["slots"]["configure"]


def test_the_catalog_conditional_keys_the_engage_direction() -> None:
    """The ruling's corpus corroboration, machine-checked: the catalog's
    output input_schema carries an ``allOf/if/then`` making
    ``configuration_id`` required exactly when ``enabled`` is true — the
    engage direction must name the commissioned configuration it will
    sink at (the values clause of the section C.1 confirm), while the
    disengage direction is bare ``channel`` + ``enabled``. A catalog edit
    that drops or inverts the conditional reddens this arm — the
    direction pin's evidence base, re-derived from the catalog's own
    bytes."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    schema = catalog["actions"][OUTPUT_ACTION]["input_schema"]
    conditions = [
        condition
        for condition in schema.get("allOf", [])
        if condition.get("if", {}).get("properties", {}).get("enabled", {}).get(
            "const"
        )
        is True
    ]
    assert conditions, "the enabled-true conditional is absent from the catalog"
    for condition in conditions:
        required = condition.get("then", {}).get("required", [])
        assert "configuration_id" in required, required


def test_the_reference_authors_structure_not_data() -> None:
    """A6/D2, machine-checked: no numeric literals outside the structural
    set (layout spans and plot indices), and no authored data strings —
    no values, no units, no channel names, no quantity names, and none
    of the load's mode enum members (``cc``/``cv``/``cr``/``cp`` appear
    nowhere: the mode is descriptor-side configuration data). Data
    arrives via the descriptor and catalog at expansion."""
    reference = load_document(REFERENCE)
    allowed_numbers = {12, 7, 5, 0}  # spans + plot index, the structural set

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)
        else:
            yield node

    for value in walk(reference):
        # bools are schema flags (vendor_features), not numeric literals
        # — bool subclasses int, excluded explicitly; every genuine int
        # must be a structural one (a span or a plot index)
        if isinstance(value, bool):
            continue
        assert not isinstance(value, float), value
        if isinstance(value, int):
            assert value in allowed_numbers, value
    # the authored-string census: no value anywhere in the document is a
    # fixture data string or a mode enum member, and the STRUCTURAL
    # surface (where a data binding would launder — slots, pages,
    # layouts, expect) carries none of them even as a substring. Prose
    # reasons are authored explanation, not data: an English word that
    # happens to be a quantity name ("the configured current maximum")
    # is not a binding, so the substring rule scopes to structure only.
    fixture = load_document(DESCRIPTOR)
    banned: set[str] = {"cc", "cv", "cr", "cp"}
    for channel in fixture["channels"]:
        banned.add(str(channel["id"]))
        banned.add(str(channel["label"]))
        banned.update(str(q) for q in channel["quantities"])
    for value in walk(reference):
        if isinstance(value, str):
            assert value not in banned, value
    structural = {
        key: reference[key]
        for key in ("slots", "pages", "layouts", "expect", "targets")
    }
    raw_structural = json.dumps(structural)
    for data_string in banned:
        assert data_string not in raw_structural, data_string


def test_the_reference_validates_against_the_family_schema() -> None:
    """The family schema admits the sink-shaped reference: five slots
    (channels with a free-string role / dataset / configuration /
    procedure with the host_supplied field names / vendor_actions),
    three pages with a time_series plot over the measure slot, one
    layout block, the closed count grammar."""
    validate_reference_document(load_document(REFERENCE), corpus=corpus_root())


# --- A8: the direction pin (this class's own arm) --------------------------------


def _direction_pin_violations(reference: dict[str, Any]) -> list[str]:
    """The pin's three assertions over one reference document: the output
    control value, the cannot_derive id, and the forbid id — each named
    on failure so the RED demonstrations can assert WHICH pin fired."""
    violations: list[str] = []
    controls = reference["expect"]["controls"]
    if controls.get(OUTPUT_ACTION) != "deviation":
        violations.append(f"control:{controls.get(OUTPUT_ACTION)!r}")
    ids = {str(row["id"]) for row in reference["cannot_derive"]}
    if "input-control" not in ids:
        violations.append("cannot_derive:input-control")
    if "intermediated-energy-removing-action" not in reference["expect"]["forbid"]:
        violations.append("forbid:intermediated-energy-removing-action")
    return violations


def test_the_direction_pin_holds_over_the_committed_reference() -> None:
    """A8's green half: the ruling in vocabulary form — ``output`` is a
    declared deviation (the per-action control vocabulary cannot split
    engage from disengage), ``input-control`` names the directional
    deviation in the ledger, and ``intermediated-energy-removing-action``
    is carried with its second true home (the never-intermediated action
    is the DISENGAGE — a bulk-energy flow-stop). The input-control reason
    carries the ruling's own words, so an editor reading the ledger
    cannot read the direction the wrong way round."""
    reference = load_document(REFERENCE)
    assert _direction_pin_violations(reference) == []
    # the controls plan's other row: configure is preset-mediated at birth
    assert reference["expect"]["controls"][CONFIGURE_ACTION] == "preset"
    row = next(
        r for r in reference["cannot_derive"] if str(r["id"]) == "input-control"
    )
    assert "flow-starting" in str(row["reason"])
    assert "R-DEENERGISE-1" in str(row["reason"])


def test_the_ungated_engage_misread_reds_the_pin() -> None:
    """A8's first RED demonstration: mutating the output control to
    ``button`` — the ungated-engage misread, the drain-from-DUT reading
    the design §1 exists to kill — fires the pin's control assertion
    while the other two pins stay quiet (the mutation is one
    dangerous choice, not three)."""
    reference = load_document(REFERENCE)
    reference["expect"]["controls"][OUTPUT_ACTION] = "button"
    violations = _direction_pin_violations(reference)
    assert violations == ["control:'button'"], violations


def test_the_gated_disengage_misread_reds_the_pin() -> None:
    """A8's second RED demonstration: mutating the output control to
    ``staging`` — the gated-disengage misread, burying the one ungated
    action behind a staged control — fires the same control assertion.
    The pin discriminates in BOTH directions: ``button`` and ``staging``
    are the two dangerous simplifications, and neither passes as
    ``deviation``'s honest name."""
    reference = load_document(REFERENCE)
    reference["expect"]["controls"][OUTPUT_ACTION] = "staging"
    violations = _direction_pin_violations(reference)
    assert violations == ["control:'staging'"], violations


def test_dropping_the_forbid_id_reds_the_pin() -> None:
    """A8's third RED demonstration: dropping
    ``intermediated-energy-removing-action`` from the forbid set — the
    never-intermediated DISENGAGE losing its guard — fires the pin's
    forbid assertion while the control value stays honest."""
    reference = load_document(REFERENCE)
    reference["expect"]["forbid"] = [
        fid
        for fid in reference["expect"]["forbid"]
        if fid != "intermediated-energy-removing-action"
    ]
    violations = _direction_pin_violations(reference)
    assert violations == ["forbid:intermediated-energy-removing-action"], violations


# --- the pattern-library input page ----------------------------------------------


def test_tile_count_and_labels_derive_from_the_otdp_example() -> None:
    """D2 at the composition: the page's reading tiles are one per
    (channel, quantity) pair of the OTDP class example's declared sink
    channels — 2 x 3 computed from the descriptor, never a literal;
    every tile label names its channel label and quantity, both corpus
    strings."""
    page = classref.render_electronic_load_input_page()
    descriptor = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
    sink = _sink_channels(reference, descriptor)
    expected_tiles = sum(len(c["quantities"]) for c in sink)
    assert expected_tiles >= 1
    tiles = re.findall(r'class="bw-reading[ "]', page)
    assert len(tiles) == expected_tiles
    for channel in sink:
        for quantity in channel["quantities"]:
            assert f"{channel['label']} · {quantity}" in page, (
                channel["id"],
                quantity,
            )


def test_the_trend_is_one_plot_with_the_disclosed_two_traces() -> None:
    """One engineering plot (the layout block's trend section); the trace
    set is the disclosed author choice (the record's channel_hints
    matter): voltage and current of the first declared sink channel,
    matching the mockup's two traces."""
    page = classref.render_electronic_load_input_page()
    figures = re.findall(r'class="bw-plot[ "]', page)
    assert len(figures) == 1
    descriptor = load_document(DESCRIPTOR)
    first = next(c for c in descriptor["channels"] if str(c["role"]) == "sink")
    assert f"{first['label']} · voltage" in page
    assert f"{first['label']} · current" in page


def test_the_table_covers_every_channel_quantity_pair() -> None:
    """The data table's body is one row per (channel, quantity) pair —
    the same derivation as the tiles; the quality column carries the
    mockup's own wording (Verified / Near limit)."""
    page = classref.render_electronic_load_input_page()
    descriptor = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
    sink = _sink_channels(reference, descriptor)
    body_rows = re.findall(r"<tr[^>]*>", page)[1:]  # the header row excluded
    assert len(body_rows) == sum(len(c["quantities"]) for c in sink)
    assert "Verified" in page
    assert "Near limit" in page


def test_the_page_sections_mirror_the_reference_layout_block() -> None:
    """The composition's sections carry the layout block's own surfaces
    and spans (data-bw-span): readings 12 raised, trend 7 recessed, table
    5 raised — the dc_psu ratio, the mirror class's own geometry. An
    edit to the reference's layout block reddens the composition."""
    page = classref.render_electronic_load_input_page()
    reference = load_document(REFERENCE)
    layout = next(lp for lp in reference["layouts"] if lp["page_id"] == "input")
    for section in layout["sections"]:
        pattern = re.compile(
            rf'data-bw-section-id="{section["id"]}"[^>]*'
            rf'data-surface="{section["surface"]}"[^>]*'
            rf'data-bw-span="{section["span"]}"'
        )
        assert pattern.search(page), section["id"]


def test_the_page_composes_only_e1_partials() -> None:
    """Host composition of §E.1 partials only — no renderer change, no
    new contract rows; the banner leads (§E.1 placement), and no control
    surface derives at birth (the output action's directional section C.1
    presentation is a named deviation; the staged-draw idiom is
    cannot_derive) — the page fabricates neither, and the dashed
    configured-maximum line is cannot_derive (limit-overlay) and composes
    nothing here."""
    page = classref.render_electronic_load_input_page()
    assert "bw-mode-banner" in page
    banner = page.find("bw-mode-banner")
    tile = page.find('class="bw-reading')
    assert -1 < banner < tile
    for surface in ("bw-alert-bubble", "bw-plot", "bw-data-table"):
        assert surface in page, surface
    assert "bw-rotary" not in page  # draw-staging is cannot_derive
    assert "bw-confirm" not in page  # the directional control is a deviation
    assert "<button" not in page


def test_the_sink_margin_alert_renders_the_mockup_wording() -> None:
    """The alert's title and condition wording trace to the mockup (the
    spec) — the load's own quantity and sense (absorbed, not delivered);
    the device-specific suffix stays mockup-side."""
    page = classref.render_electronic_load_input_page()
    assert "Sinking margin" in page
    assert "approaching configured current maximum" in page


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_class_page_exports_in_both_themes(tmp_path: Path, theme: str) -> None:
    patterns.export(tmp_path)
    path = tmp_path / "patterns" / theme / "class-input.html"
    assert path.is_file(), path
    html = path.read_text(encoding="utf-8")
    assert "data-bw-pattern-library" in html
    assert 'data-bw-pattern-page="class-input"' in html
    assert "Reference channel 1 · voltage" in html


def test_the_class_page_census_entry_is_registered() -> None:
    """The page rides the PATTERNS census: kind class-page on the
    class-input page, row-keyed to the family's electronic_load
    reference, fixture the input page."""
    entry = next(e for e in patterns.PATTERNS if e.page == "class-input")
    assert entry.kind == "class-page"
    assert entry.row_id == "plugin-ui-class-reference::class-electronic_load"
    assert entry.fixture_id == "input"
