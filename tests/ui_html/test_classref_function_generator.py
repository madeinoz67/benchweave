"""The function_generator class reference (L14 of the class sweep;
design record
``.claude/deep-review/2026-10-19-classref-l14-function-generator-design.md``):
the mockup-consistency arm (A3) and the pattern-library configuration-page
composition with its drift guard.

A3, fifth class of the sweep — the first PURE SOURCE. The mockup
(``docs/internal/ui-styleguide-mockups/class-function_generator.html``)
is authored WITH the reference (the dmm convention's third instance,
with the §E.1 hooks and the placement contract from birth); the
reference is the data; this test is the bridge, keyed on the shared
census instrument (``tests/ui_html/classref_census.py``). This class
carries the sweep's THINNEST hook census — two families
(``bw-data-table``, ``bw-alert-bubble``) on one derivable page — which
is itself the assertion: the profile has no measurement action, so no
observation binds and no plot template names an over-slot; the class's
operator surfaces (function cards, waveform preview, preset card,
output-control card) are hook-less idioms, and the census plants prove
a reverse-planted ``bw-`` class on any of the four reds.

Like dmm and the scope there is NO derived fixture: the mockup is
authored to the committed OTDP class example's own shape (2 source
channels x 1 declared quantity = 2 function cards), so the census
resolves over the committed example directly. One derived-in-test
fixture exists for the when_declared arm (A8): the example minus its
``upload`` action — the descriptor shape a generator without
arbitrary-waveform support presents. The kill is two-directional by
construction: a mockup edit that changes a hook count reds against the
resolved expectation, and a reference edit that changes the derivation
(a count expression, the slots, the page set) reds against the
mockup's counts. A mockup edit that does NOT redden the test is the
instrument failing — report, never a quiet pass (the record's A3
wording).

The expansion side (derive-ui/verify-ui censuses) is the batched SDK
leg's work and rides that train; what this file pins is the corpus
pair's structure — the reference document, its schema admission, and
the composition the host renders from it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from benchweave_ui_html import classref, patterns
from classref_census import (
    PLACEMENT_TAG,
    HookCensus,
    hook_census,
    load_document,
    resolve_count,
)

from benchweave.presentation.classref import (
    ClassRefusal,
    validate_reference_document,
)
from benchweave.vendoring import corpus_root

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = REPO_ROOT / "standards/plugin-ui-class-reference/0.3.0"
REFERENCE = FAMILY_DIR / "class-function_generator.json"
DESCRIPTOR = REPO_ROOT / "standards/otdp/0.2.3/examples/class-function_generator.json"
MOCKUP = REPO_ROOT / "docs/internal/ui-styleguide-mockups/class-function_generator.html"
CATALOG = REPO_ROOT / "standards/otdp/0.2.3/device-profile-catalog.json"
CONFIGURE_ACTION = "otdp.function_generator.configure/1.0.0"

#: The pure-source class's hook families — the sweep's thinnest census:
#: the settings table and the alert are the only contract surfaces the
#: class's one derivable page composes. No ``bw-reading`` (no
#: measurement action binds an observation), no ``bw-plot`` (no dataset
#: action exists for a plot template to name an over-slot), no
#: ``bw-button`` (both procedure controls are L0 deviations at birth).
FUNCTION_GENERATOR_HOOKS: tuple[str, ...] = ("bw-data-table", "bw-alert-bubble")

#: The placement contract for this mockup: the settings table sits in
#: the settings region (its container); the alert aside is pinned by its
#: §E.1 root alone, the readings classes' own convention.
FUNCTION_GENERATOR_CONTAINERS: dict[str, str] = {
    "bw-data-table": "settings",
}

#: The idiom surfaces (the design's §2 table): non-contract surfaces
#: painted over host composition — the per-channel function cards, the
#: waveform preview panel, the preset-preview card and the staged
#: output-control card. They carry NO ``bw-`` hook (L13's rule, this
#: class's largest idiom surface: four where dc_psu had one).
FUNCTION_GENERATOR_IDIOMS: frozenset[str] = frozenset(
    {"fncard", "waveform-preview", "preset-card", "output-control"}
)

#: component name -> the §E.1 hook root the mockup carries for it.
COMPONENT_HOOKS: dict[str, str] = {
    "data-table": "bw-data-table",
}


def _function_generator_census() -> dict[str, dict[str, int]]:
    return hook_census(MOCKUP, hooks=FUNCTION_GENERATOR_HOOKS)


def _source_channels(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> list[dict[str, Any]]:
    """The channels the reference's outputs slot resolves — the role the
    SLOT names (never a literal role string here), declaration order."""
    where_role = str(reference["slots"]["outputs"]["where_role"])
    return [c for c in descriptor["channels"] if str(c["role"]) == where_role]


def _structural_counters(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The closed counter set over (reference x fixture): every counter is
    an expression over the fixture's declared channels and their declared
    quantities — never a count imported from the mockup."""
    channels = _source_channels(reference, descriptor)
    return {
        "n_source_channels": len(channels),
        "n_source_quantities": sum(len(c["quantities"]) for c in channels),
        "n_pages": len(reference["pages"]),
    }


def _resolved_configuration_expectation(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The expect.components rows scoped to the configuration page,
    resolved over the committed example (no derived fixture — the mockup
    is authored to the example's own shape)."""
    counters = _structural_counters(reference, descriptor)
    resolved: dict[str, int] = {}
    for name, row in reference["expect"]["components"].items():
        if row.get("per_page") == "configuration":
            resolved[name] = resolve_count(str(row["count"]), counters)
    return resolved


def _configure_schema(descriptor: dict[str, Any]) -> dict[str, Any]:
    """The configure action's EFFECTIVE input schema: the catalog's own
    schema, refined by the example's declared input_constraints (the
    D13 intersection — an empty constraint set leaves the catalog schema
    unchanged, which is this example's shape)."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    schema = cast(
        "dict[str, Any]",
        catalog["actions"][CONFIGURE_ACTION]["input_schema"],
    )
    constraints = descriptor["actions"][CONFIGURE_ACTION].get(
        "input_constraints", {}
    )
    constraint_fields = constraints.get("properties", {})
    if not constraint_fields:
        return schema
    effective = cast(
        "dict[str, Any]", json.loads(json.dumps(schema))
    )
    effective.setdefault("properties", {}).update(constraint_fields)
    return effective


#: The identity fields the composition carries OUTSIDE the settings
#: table: the staged-configuration evidence line (``configuration_id``)
#: and the per-channel function cards (``channel``). The table's row set
#: is every OTHER field of the effective schema.
_TABLE_EXCLUDED_FIELDS = frozenset({"configuration_id", "channel"})


def _expected_conditional_notes(descriptor: dict[str, Any]) -> dict[str, str]:
    """The conditional rows' Notes wording, derived from the schema's
    ``allOf`` conditions (the design's §5 arm 7): the duty-cycle row
    names the square-or-pulse enum, the waveform-id row names the
    arbitrary const."""
    schema = _configure_schema(descriptor)
    notes: dict[str, str] = {}
    for condition in schema.get("allOf", []):
        required = condition.get("then", {}).get("required", [])
        function_clause = condition.get("if", {}).get("properties", {}).get(
            "function", {}
        )
        if "enum" in function_clause:
            wording = " or ".join(str(v) for v in function_clause["enum"])
        elif "const" in function_clause:
            wording = str(function_clause["const"])
        else:
            continue
        for field in required:
            notes[str(field)] = f"required when function is {wording}"
    return notes


def _upload_less_fixture() -> dict[str, Any]:
    """A8's derived-in-test fixture: the committed example minus its
    ``upload`` action — the descriptor shape a generator without
    arbitrary-waveform support presents (the optional action simply is
    not declared; the ``when_declared`` slot skips it)."""
    descriptor = load_document(DESCRIPTOR)
    descriptor["actions"] = {
        urn: action
        for urn, action in descriptor["actions"].items()
        if urn != "otdp.function_generator.upload/1.0.0"
    }
    return descriptor


# --- A3: the mockup-consistency arm ---------------------------------------------


def test_the_mockup_carries_the_contract_hooks_in_both_themes() -> None:
    """The hook pass (RC-L11-3), from birth (the dmm convention, third
    authored-from-birth instance): both theme sections carry every hook
    family the census keys on — a hook absent from one theme is a
    composition break, not a style choice. Two families is the sweep's
    thinnest census, and that is the assertion (the pure-source class
    derives exactly two contract surfaces on its one derivable page)."""
    census = _function_generator_census()
    assert set(census) == {"light", "dark"}
    for theme, hooks in census.items():
        for hook in FUNCTION_GENERATOR_HOOKS:
            assert hooks[hook] >= 1, (theme, hook)


def test_mockup_hook_counts_equal_the_resolved_expectation() -> None:
    """A3, the load-bearing arm: per theme section, the mockup's hook
    counts EQUAL the reference's resolved expectation over the committed
    OTDP example (2 source channels x 1 declared quantity = 2 function
    cards; the settings table is one) — the counts derived on BOTH
    sides, never literals on either.

    Kill direction 1: edit the mockup's count — the hook count diverges
    from the resolved expectation and this reds.
    Kill direction 2: edit the reference's derivation — a count
    expression, the slots, the page set — and the RESOLVED side diverges
    from the mockup and this reds."""
    reference = load_document(REFERENCE)
    fixture = load_document(DESCRIPTOR)
    resolved = _resolved_configuration_expectation(reference, fixture)
    assert set(resolved) == {"data-table"}, resolved
    counters = _structural_counters(reference, fixture)
    # the example's own shape: 2 channels x 1 quantity — the numbers the
    # mockup is authored to (the census keys on them; a fixture change
    # reds the composition, never this arm)
    assert counters["n_source_quantities"] == counters["n_source_channels"] * 1
    assert counters["n_source_channels"] >= 1
    census = _function_generator_census()
    for theme, hooks in census.items():
        for name, hook in COMPONENT_HOOKS.items():
            assert hooks[hook] == resolved[name], (theme, hook, resolved[name])


def test_every_hook_sits_on_its_contract_root_and_container() -> None:
    """The count-conserving-move kill and the idiom-surface kill (the
    design's §5 arm 3): every hook is on its §E.1 root element, the
    container-scoped hooks sit in their containers, and the idiom
    surfaces (function cards, waveform preview, preset card,
    output-control card) carry NO ``bw-`` hook — a non-contract idiom
    must never present as a contract component. The count census alone
    is placement-blind: a hook moved count-conservingly into the wrong
    container reds HERE while the count arm stays green."""
    parser = HookCensus(
        hooks=FUNCTION_GENERATOR_HOOKS,
        containers=FUNCTION_GENERATOR_CONTAINERS,
        idiom_classes=FUNCTION_GENERATOR_IDIOMS,
    )
    parser.feed(MOCKUP.read_text(encoding="utf-8"))
    assert parser.placements, "the census recorded no hook placements"
    for theme, hook, tag, ancestors in parser.placements:
        assert tag == PLACEMENT_TAG[hook], (theme, hook, tag)
        container = parser.containers.get(hook)
        if container is not None:
            # the stack at recording time holds ANCESTORS only (the
            # current element is appended after the hook check)
            assert any(
                container in ancestor_classes
                for _ancestor_tag, ancestor_classes in ancestors
            ), (theme, hook, container)
    # the idiom surfaces: present (the mockup paints them) and hook-free
    assert parser.idiom_surfaces, "the census recorded no idiom surfaces"
    for theme, tag, classes, carried in parser.idiom_surfaces:
        assert carried == (), (theme, tag, classes, carried)


def _census_of(html: str) -> HookCensus:
    """The census over a MUTATED copy of the mockup (the kill arms'
    vehicle — never the committed bytes)."""
    parser = HookCensus(
        hooks=FUNCTION_GENERATOR_HOOKS,
        containers=FUNCTION_GENERATOR_CONTAINERS,
        idiom_classes=FUNCTION_GENERATOR_IDIOMS,
    )
    parser.feed(html)
    return parser


def test_the_count_conserving_move_of_the_table_hook_reds_placement() -> None:
    """The count-conserving-move kill, demonstrated RED (the design's A3:
    a ``bw-data-table`` moved to the preview panel reds while counts
    conserve). The mutation strips the hook from the settings table and
    plants it on the waveform-preview panel in BOTH themes: the count
    census stays green under the move (one ``bw-data-table`` per theme
    either way) and the PLACEMENT arm is what reds — the tag is a
    section, not the §E.1 table root, and the settings container is no
    longer an ancestor."""
    html = MOCKUP.read_text(encoding="utf-8")
    moved = html.replace('class="settings-table bw-data-table"', 'class="settings-table"')
    moved = moved.replace(
        'class="plot waveform-preview"', 'class="plot waveform-preview bw-data-table"'
    )
    assert moved != html, "the mutation must change the mockup bytes"
    parser = _census_of(moved)
    # the count arm stays green under the move: still one per theme
    for theme, hooks in parser.counts.items():
        assert hooks["bw-data-table"] == 1, (theme, hooks)
    # the placement arm reds: every occurrence is checked, and each
    # moved occurrence now fails the root (or container) assertion
    reds = 0
    for _theme, hook, tag, ancestors in parser.placements:
        root_ok = tag == PLACEMENT_TAG[hook]
        container = parser.containers.get(hook)
        container_ok = container is None or any(
            container in ancestor_classes
            for _ancestor_tag, ancestor_classes in ancestors
        )
        if not (root_ok and container_ok):
            reds += 1
    assert reds >= 2, f"the move must red placement in both themes ({reds})"


@pytest.mark.parametrize(
    "idiom_class",
    sorted(FUNCTION_GENERATOR_IDIOMS),
)
def test_a_reverse_planted_hook_on_each_idiom_surface_reds(
    idiom_class: str,
) -> None:
    """The no-hook-on-idiom kill, demonstrated RED on each of the four
    idiom surfaces (L13's rule, multiplied across this class's larger
    idiom surface): planting a ``bw-`` class on a function card, the
    preview panel, the preset card or the output-control card makes the
    census record a carried hook — the idiom assertion (carried == ())
    reds while the count census stays green (the planted class adds no
    countable hook occurrence beyond the families the census counts, or
    conserves them exactly)."""
    html = MOCKUP.read_text(encoding="utf-8")
    planted = html.replace(
        f'class="{idiom_class}', f'class="{idiom_class} bw-data-table', 1
    )
    if planted == html:
        planted = html.replace(
            f' {idiom_class}"', f' {idiom_class} bw-data-table"', 1
        )
    assert planted != html, f"the plant must change the mockup bytes ({idiom_class})"
    parser = _census_of(planted)
    assert parser.idiom_surfaces, "the census recorded no idiom surfaces"
    carried = [
        bw
        for _theme, _tag, _classes, hooks in parser.idiom_surfaces
        for bw in hooks
    ]
    assert carried, "the planted idiom surface must carry the reverse-planted hook"


def test_both_themes_carry_the_identical_hook_census() -> None:
    """One composition, two themes: the hook census is theme-invariant."""
    census = _function_generator_census()
    assert census["light"] == census["dark"]


def test_the_alert_surface_is_one_per_theme_and_a_named_cannot_derive() -> None:
    """The mockup's alert aside is structure the composition renders and
    data the reference cannot derive: exactly one ``bw-alert-bubble``
    per theme, and ``load-convention-alert`` names it in the deviation
    ledger (the condition — delivered amplitude at the declared load vs
    the display convention — is commissioned policy, A02)."""
    reference = load_document(REFERENCE)
    ids = {str(row["id"]) for row in reference["cannot_derive"]}
    assert "load-convention-alert" in ids
    census = _function_generator_census()
    for theme, hooks in census.items():
        assert hooks["bw-alert-bubble"] == 1, theme


def test_the_reference_selects_for_the_class_descriptor() -> None:
    """A4's green half, gateway-side: the function_generator class
    example's profile now selects a corpus reference
    (``select_references`` returned None before the class existed — the
    pair banked RED at design time and re-banked on this slice's base
    ``dee6de896``, design record §6 arm 6)."""
    from benchweave.presentation.classref import select_references

    selected = select_references(corpus_root(), load_document(DESCRIPTOR))
    assert selected is not None and len(selected) == 1
    assert selected[0]["profile_id"] == "otdp.function_generator/1.0.0"


# --- the reference's own shape: two pages, no layout, no numerals -----------------


def test_the_reference_owns_exactly_two_pages_and_no_plot_or_layout() -> None:
    """RC-L14-2, machine-checked: the page set is Configuration and
    Device features — no output-shaped third page. A pure source has no
    measurement action, so no observation binds and no plot template
    names an over-slot; an output-shaped page would render panels and a
    mode-banner around two REPORTED deviations — placement-by-
    anticipation, refused by the design (§3). Zero layouts follows: the
    derivable page composes no reading nodes, no control nodes and no
    plot refs (an empty shell would be the same fabrication)."""
    reference = load_document(REFERENCE)
    pages = reference["pages"]
    assert [page["id"] for page in pages] == ["configuration", "device-features"]
    assert all("plot" not in page for page in pages)
    assert reference.get("layouts", []) == []


def test_the_optional_upload_slot_is_when_declared() -> None:
    """§3.2, machine-checked: ``upload`` is the ``when_declared`` seam's
    second use and its first NON-lifecycle optional action — a
    descriptor without arbitrary-waveform support simply does not
    declare it and the slot skips; both L0 procedure actions carry
    declared deviations (the ledger REPORTS them, never silent)."""
    reference = load_document(REFERENCE)
    upload = reference["slots"]["upload"]
    assert upload["kind"] == "procedure"
    assert upload["when_declared"] is True
    controls = reference["expect"]["controls"]
    assert controls == {
        "otdp.function_generator.configure/1.0.0": "preset",
        "otdp.function_generator.output/1.0.0": "deviation",
        "otdp.function_generator.upload/1.0.0": "deviation",
    }


def test_the_reference_authors_structure_not_data() -> None:
    """A6/D2, machine-checked and STRONGER than the readings classes'
    arm: the pure-source reference authors ZERO numeric literals — no
    layout block, no plot, no spans, so the allowed-numbers set is
    EMPTY (the census asserts the absence, not just the legality) — and
    none of the fixture's own data strings (channel ids, channel
    labels, quantity names) appears: data arrives via the descriptor
    and catalog at expansion."""
    reference = load_document(REFERENCE)

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
        # bools are schema flags (when_declared, vendor_features), not
        # numeric literals — bool subclasses int, excluded explicitly
        assert isinstance(value, bool) or not isinstance(value, int), value
        assert not isinstance(value, float), value
    raw = json.dumps(reference)
    fixture = load_document(DESCRIPTOR)
    banned: set[str] = set()
    for channel in fixture["channels"]:
        banned.add(str(channel["id"]))
        banned.add(str(channel["label"]))
        banned.update(str(q) for q in channel["quantities"])
    for data_string in banned:
        assert data_string not in raw, data_string


def test_the_reference_validates_against_the_family_schema() -> None:
    """The family schema admits the pure-source shape: five slots
    (channels/configuration/procedure x2 with the when_declared seam/
    vendor_actions), two configuration-kind pages, zero layouts, the
    closed count grammar over ``{n_pages}``."""
    validate_reference_document(load_document(REFERENCE), corpus=corpus_root())


def test_a_page_binding_an_unknown_slot_refuses() -> None:
    """The family's cross-object admission refusal, pinned for this
    class's page set: a scratch reference binding a slot key it does not
    own refuses at derivation (``classref_unknown_slot``) — an unknown
    key cannot launder a page. The schema alone is structural; the
    cross-object check is the derivation's (the README's own split)."""
    from benchweave.presentation.classref import derive_attachment

    document = load_document(REFERENCE)
    document["pages"][0]["binding_slots"] = ["configure", "measure"]
    descriptor_raw = DESCRIPTOR.read_bytes()
    with pytest.raises(ClassRefusal, match="classref_unknown_slot"):
        derive_attachment(
            descriptor_raw,
            corpus=corpus_root(),
            references_override=[document],
        )


# --- A8: the when_declared arm (this class's own) --------------------------------


def test_the_upload_less_descriptor_still_selects_the_reference() -> None:
    """A8, executed gateway-side: on the upload-less derived fixture
    (the example minus its ``upload`` action, derived in-test — the
    descriptor shape a generator without arbitrary-waveform support
    presents), ``select_references`` still resolves the reference and
    the derivation still produces the SAME two-page set — the
    ``when_declared`` slot skips the undeclared action, leaving no
    upload-shaped residue (no ghost page, no stray binding). The
    upload binding exists ONLY on the fixture that declares the action.
    The SDK-side census (the controls plan's deviation ledger rows) is
    the batched SDK leg's work and rides that train."""
    from benchweave.presentation.classref import derive_attachment, select_references

    fixture = _upload_less_fixture()
    assert "otdp.function_generator.upload/1.0.0" not in fixture["actions"]
    selected = select_references(corpus_root(), fixture)
    assert selected is not None and len(selected) == 1
    assert selected[0]["profile_id"] == "otdp.function_generator/1.0.0"

    full = json.loads(
        derive_attachment(
            DESCRIPTOR.read_bytes(), corpus=corpus_root()
        ).manifest_raw
    )
    reduced = json.loads(
        derive_attachment(
            json.dumps(fixture).encode(), corpus=corpus_root()
        ).manifest_raw
    )
    for manifest, label in ((full, "declared"), (reduced, "upload-less")):
        assert [page["id"] for page in manifest["pages"]] == [
            "configuration",
            "device-features",
        ], (label, manifest["pages"])
    binding_ids = {b["id"] for b in full["bindings"]}
    reduced_binding_ids = {b["id"] for b in reduced["bindings"]}
    assert "upload" in binding_ids
    assert "upload" not in reduced_binding_ids


# --- the pattern-library configuration page --------------------------------------


def test_the_settings_field_rows_derive_from_the_catalog_schema() -> None:
    """§5 arm 7's drift guard: the settings table's field-row set is one
    row per configure input-schema property minus the identity fields
    the composition carries elsewhere (``configuration_id`` on the
    staged-configuration evidence, ``channel`` on the function cards),
    each row's Kind derived from the property's own shape — corpus
    strings, never literals. A catalog edit (a field added, a type
    changed) reddens this arm until the page data is regenerated."""
    page = classref.render_function_generator_configuration_page()
    fixture = load_document(DESCRIPTOR)
    schema = _configure_schema(fixture)
    expected_rows = {
        name: (
            "selection"
            if "enum" in prop
            else "text"
            if prop.get("type") == "string"
            else "numeric"
        )
        for name, prop in schema["properties"].items()
        if name not in _TABLE_EXCLUDED_FIELDS
    }
    assert expected_rows, "the derivation found no fields"
    for field, kind in expected_rows.items():
        assert field in page, field
        assert kind in page, (field, kind)
    # the identity fields stay off the table (carried by the cards and
    # the evidence line, not duplicated as rows)
    table_start = page.find('class="bw-data-table')
    table_html = page[table_start:]
    assert "configuration_id" not in table_html


def test_the_conditional_notes_derive_from_the_allof_conditions() -> None:
    """§5 arm 7's second half: the conditional rows' Notes wording
    derives from the schema's ``allOf`` conditions — the duty-cycle row
    names the square-or-pulse enum, the waveform-id row names the
    arbitrary const. The wording is re-derived here from the catalog's
    own bytes; a catalog edit to the conditions reddens this arm."""
    page = classref.render_function_generator_configuration_page()
    for field, note in _expected_conditional_notes(load_document(DESCRIPTOR)).items():
        assert field in page, field
        assert note in page, (field, note)


def test_the_load_convention_alert_renders_the_mockup_wording() -> None:
    """The alert's title and condition wording trace to the mockup (the
    spec) — this class's §8-required case: the output-load convention
    ambiguity the normative prose names."""
    page = classref.render_function_generator_configuration_page()
    assert "Load convention" in page
    assert "declared 50 Ω load" in page
    assert "high-impedance" in page


def test_the_function_cards_derive_from_the_declared_channels() -> None:
    """Two function cards — one per (channel, declared quantity) of the
    OTDP example's declared source channels, resolved through the
    reference's own outputs slot: labels are corpus strings (the
    channel labels), counts derive. The cards carry NO ``bw-`` hook:
    they are REQUESTED values, and the contract's own reading-tile row
    bars presenting a requested value as a reading."""
    page = classref.render_function_generator_configuration_page()
    reference = load_document(REFERENCE)
    fixture = load_document(DESCRIPTOR)
    cards = page.count('class="fncard card')
    channels = _source_channels(reference, fixture)
    assert cards == len(channels), (cards, len(channels))
    for channel in channels:
        assert str(channel["label"]) in page, channel["id"]
    # the sweep's first class whose summary cards cannot be readings
    assert "bw-reading" not in page


def test_the_idiom_surfaces_compose_hookless() -> None:
    """§5 arm 7's composition guard: the preview, function cards,
    preset card and output-control card render with NO ``bw-`` hook and
    no fabricated control — no ``bw-rotary``, no ``bw-confirm``, no
    ``<button>``, no ``bw-plot`` (the F1-generalized lie: fabricating a
    contract component on a cannot-derive surface). The preview is the
    waveform-canvas idiom's landing (L13's ruling, idiom-level only —
    no dataset action exists for the plot arm to bind)."""
    page = classref.render_function_generator_configuration_page()
    assert "bw-mode-banner" in page  # §E.1 placement: the banner leads
    banner = page.find("bw-mode-banner")
    table = page.find('class="bw-data-table')
    assert -1 < banner < table
    assert 'class="plot waveform-preview"' in page
    assert "bw-plot" not in page
    assert "bw-rotary" not in page
    assert "bw-confirm" not in page
    assert "bw-button" not in page
    assert "<button" not in page
    assert "PRESET · APPLY REQUIRED" in page
    # the §C.1 directional idiom, painted: the enable arm stages then
    # confirms naming effect and target; the disable arm is one ungated
    # action — an armed line, never a confirm subtree
    assert "STAGED · CONFIRM REQUIRED" in page
    assert "ONE ACTION · NO CONFIRMATION" in page


def test_the_class_page_census_entry_is_registered() -> None:
    """The page rides the PATTERNS census: kind class-page on the
    class-configuration page, row-keyed to the family's
    function_generator reference, fixture the configuration page."""
    entry = next(
        e for e in patterns.PATTERNS if e.page == "class-configuration"
    )
    assert entry.kind == "class-page"
    assert entry.row_id == "plugin-ui-class-reference::class-function_generator"
    assert entry.fixture_id == "configuration"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_class_page_exports_in_both_themes(tmp_path: Path, theme: str) -> None:
    patterns.export(tmp_path)
    path = tmp_path / "patterns" / theme / "class-configuration.html"
    assert path.is_file(), path
    html = path.read_text(encoding="utf-8")
    assert "data-bw-pattern-library" in html
    assert 'data-bw-pattern-page="class-configuration"' in html
    assert "Reference channel 1" in html
