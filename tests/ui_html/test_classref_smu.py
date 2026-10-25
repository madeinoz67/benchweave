"""The smu class reference (L16 of the class sweep; design record
``.claude/deep-review/2026-10-19-classref-l16-smu-design.md``): the
mockup-consistency arm (A3), the pattern-library output-page
composition with its drift guard — and the class's own arm, the
SWEEP-ABSENCE arm (the deferral made machine-checkable, the design's
load-bearing call put where a test can kill it).

A3, seventh class of the sweep — the PSU's shape worn over a THIRD
channel role. The mockup
(``docs/internal/ui-styleguide-mockups/class-smu.html``) is authored
WITH the reference (the dmm convention's fifth instance, with the §E.1
hooks and the placement contract from birth); the reference is the
data; this test is the bridge, keyed on the shared census instrument
(``tests/ui_html/classref_census.py``). Like dmm/eload there is NO
derived fixture: the mockup is authored to the committed OTDP class
example's own shape (2 source_measure channels x 3 declared quantities
= 6 tiles), so the census resolves over the committed example directly.
The kill is two-directional by construction: a mockup edit that changes
a hook count reds against the resolved expectation, and a reference
edit that changes the derivation (a count expression, the plot binding,
the channels slot's role) reds against the mockup's counts. A mockup
edit that does NOT redden the test is the instrument failing — report,
never a quiet pass (the record's A3 wording).

The sweep-absence arm (RC-L16-1, the design's §6 arm 7 and A1's sweep
half — this class's addition to the instrument): the committed example
declares ALL EIGHT profile actions, but the birth reference slots only
the required three, deferring the five-action sweep block by name. The
deferral must be a LIVE ASSERTION, not prose: the gateway-side
expansion of the example over the birth reference succeeds (no
``ClassRefusal`` — the derivation does not refuse declared-but-unslotted
optional actions; that refusal would falsify the deferral at the
coverage layer and fire the design's named fallback), carries no
sweep-derived component anywhere in the derived triple (no catalogue
target, no page binding, no layout control outside the Device features
page), and resolves the five sweep URNs' controls on the Device
features page — the vendor_actions coverage home, D14's unclaimed-URN
hook. The RED half demonstrates the arm has teeth: a mutated reference
that slots one sweep action produces exactly the violations the green
half refuses.

The identity half (§1's machine-checkable distinctness): a dc_psu
reference refuses the smu example — the smu's channels are
``source_measure``, and the PSU's slot names ``source``, so the
expansion refuses at the lanes arm. A third channel role is not a
profile-level detail; it is the difference between a page that renders
and a typed refusal.

The expansion side beyond the census (derive-ui/verify-ui gates) is the
batched SDK leg's work and rides that train; what this file pins is
the corpus pair's structure and the gateway-side expansion's honest
shape — the reference document, its schema admission, the composition
the host renders from it, and the deferral's live assertion.
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

from benchweave.presentation.classref import (
    LAYOUT_EXTENSION_KEY,
    ClassRefusal,
    derive_attachment,
    validate_reference_document,
)
from benchweave.vendoring import corpus_root

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = REPO_ROOT / "standards/plugin-ui-class-reference/0.5.0"
REFERENCE = FAMILY_DIR / "class-smu.json"
DESCRIPTOR = REPO_ROOT / "standards/otdp/0.2.4/examples/class-smu.json"
MOCKUP = REPO_ROOT / "docs/internal/ui-styleguide-mockups/class-smu.html"
CATALOG = REPO_ROOT / "standards/otdp/0.2.4/device-profile-catalog.json"
OUTPUT_ACTION = "otdp.smu.output/1.0.0"
CONFIGURE_ACTION = "otdp.smu.configure/1.0.0"
MEASURE_ACTION = "otdp.smu.measure/1.0.0"

#: The deferred sweep block (RC-L16-1): the profile-standard optional
#: actions the example declares and the birth reference does NOT slot —
#: configure_sweep/arm/trigger/fetch/abort, deferring as a unit (the
#: design's §3.1: the fetch dataset's table-kind derivation arm exists
#: nowhere, the I-V presentation needs a plot kind plugin-ui 0.4.0 does
#: not carry, and the block's composition is procedure-owned by §10's
#: own sentence).
SWEEP_URNS = (
    "otdp.smu.abort/1.0.0",
    "otdp.smu.arm/1.0.0",
    "otdp.smu.configure_sweep/1.0.0",
    "otdp.smu.fetch/1.0.0",
    "otdp.smu.trigger/1.0.0",
)
SWEEP_SLUGS = frozenset(urn.split("/")[0].rsplit(".", 1)[-1] for urn in SWEEP_URNS)


def _smu_census() -> dict[str, dict[str, int]]:
    return hook_census(MOCKUP)


def _source_measure_channels(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> list[dict[str, Any]]:
    """The channels the reference's channels slot resolves — the role the
    SLOT names (never a literal role string here), declaration order."""
    where_role = str(reference["slots"]["channels"]["where_role"])
    return [c for c in descriptor["channels"] if str(c["role"]) == where_role]


def _structural_counters(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The closed counter set over (reference x fixture): every counter is
    an expression over the fixture's declared channels and their declared
    quantities — never a count imported from the mockup."""
    smu = _source_measure_channels(reference, descriptor)
    n_source_measure_channels = len(smu)
    n_scalar_variables = sum(len(c["quantities"]) for c in smu)
    return {
        "n_source_measure_channels": n_source_measure_channels,
        "n_scalar_variables": n_scalar_variables,
        "n_reading_tiles": n_scalar_variables,  # one tile per scalar variable
        "n_pages": len(reference["pages"]),
    }


def _resolved_output_expectation(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The expect.components rows scoped to the output page, resolved over
    the committed example (no derived fixture — the mockup is authored to
    the example's own shape)."""
    counters = _structural_counters(reference, descriptor)
    resolved: dict[str, int] = {}
    for name, row in reference["expect"]["components"].items():
        if row.get("per_page") == "output":
            resolved[name] = resolve_count(str(row["count"]), counters)
    return resolved


# --- A3: the mockup-consistency arm ---------------------------------------------


def test_the_mockup_carries_the_contract_hooks_in_both_themes() -> None:
    """The hook pass (RC-L11-3), from birth (the dmm convention, fifth
    authored-from-birth instance): both theme sections carry every hook
    family the census keys on — a hook absent from one theme is a
    composition break, not a style choice."""
    census = _smu_census()
    assert set(census) == {"light", "dark"}
    for theme, hooks in census.items():
        for hook in HOOKS:
            assert hooks[hook] >= 1, (theme, hook)


def test_mockup_hook_counts_equal_the_resolved_expectation() -> None:
    """A3, the load-bearing arm: per theme section, the mockup's hook
    counts EQUAL the reference's resolved expectation over the committed
    OTDP example (2 source_measure channels x 3 declared quantities =
    6 tiles, 1 plot, 1 table) — the counts derived on BOTH sides, never
    literals on either.

    Kill direction 1: edit the mockup's card count — the reading hook
    count diverges from the resolved expectation and this reds.
    Kill direction 2: edit the reference's derivation — a count
    expression, the plot binding, the channels slot's role — and the
    RESOLVED side diverges from the mockup and this reds."""
    reference = load_document(REFERENCE)
    fixture = load_document(DESCRIPTOR)
    resolved = _resolved_output_expectation(reference, fixture)
    assert set(resolved) == {"reading-tile", "engineering-plot", "data-table"}, resolved
    census = _smu_census()
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
    the staged-source control card (a cannot_derive surface) carries NO
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
    # the staged-source control card: one per theme, tag section, no hook carried
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
    a ``bw-reading`` moved from a readings card onto the staged-source
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
    resolved = _resolved_output_expectation(reference, fixture)
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
    census = _smu_census()
    assert census["light"] == census["dark"]


def test_the_alert_surface_is_one_per_theme_and_a_named_cannot_derive() -> None:
    """The mockup's alert aside is structure the composition renders and
    data the reference cannot derive: exactly one ``bw-alert-bubble`` per
    theme, and ``compliance-alert`` names it in the deviation ledger
    (the condition is the device-reported compliance state — runtime
    observation data, device-classes §10 — not reference structure)."""
    reference = load_document(REFERENCE)
    ids = {str(row["id"]) for row in reference["cannot_derive"]}
    assert "compliance-alert" in ids
    census = _smu_census()
    for theme, hooks in census.items():
        assert hooks["bw-alert-bubble"] == 1, theme


def test_the_reference_selects_for_the_class_descriptor() -> None:
    """A4's green half, gateway-side: the smu class example's profile now
    selects a corpus reference (``select_references`` returned None
    before the class existed — the pair banked RED at design time on the
    L11 branch head c64f3d05 and carried through this slice's base
    9d06602b by the L15 rotation, design record §6 arm 6)."""
    from benchweave.presentation.classref import select_references

    selected = select_references(corpus_root(), load_document(DESCRIPTOR))
    assert selected is not None and len(selected) == 1
    assert selected[0]["profile_id"] == "otdp.smu/1.0.0"


def test_a_dc_psu_reference_refuses_the_smu_descriptor() -> None:
    """The class-identity falsifier, machine-checked (the design §1's
    second ground): the roles do not interoperate. Expanding the smu
    example over the dc_psu reference refuses at the lanes arm — the
    PSU's channels slot names the ``source`` role and the example's
    channels are ``source_measure`` — so the dc_psu reference is
    structurally unusable for smu descriptors and the classes are not
    presentation-interchangeable. The refusal is the membership
    evidence: a third channel role is its own class, not a profile.

    The descriptor carries the PSU profile's required actions (merged
    from the committed dc_psu example) so the walk passes the earlier
    fail-closed arms — the profile-claim check and the required-action
    check — and refuses at the CHANNELS arm, the role mismatch itself:
    every other refusal would be a descriptor-authoring artefact, not
    the structural claim under test."""
    reference = json.loads(
        (FAMILY_DIR / "class-dc_psu.json").read_text(encoding="utf-8")
    )
    descriptor = json.loads(DESCRIPTOR.read_text(encoding="utf-8"))
    dc_psu_example = json.loads(
        (REPO_ROOT / "standards/otdp/0.2.4/examples/class-dc_psu.json")
        .read_text(encoding="utf-8")
    )
    descriptor["profiles"] = ["otdp.dc_psu/1.0.0"]
    descriptor["actions"] = {
        **dc_psu_example["actions"],
        **descriptor["actions"],
    }
    with pytest.raises(ClassRefusal, match="classref_no_lanes:"):
        derive_attachment(
            json.dumps(descriptor).encode(),
            corpus=corpus_root(),
            references_override=[reference],
        )


# --- the reference's own shape ---------------------------------------------------


def test_the_reference_owns_the_source_measure_slots_and_pages() -> None:
    """The slot-and-page shape, machine-checked: the channels slot is
    ``channels`` keyed on the role the SLOT names (``source_measure`` —
    the third role, a free string, zero widening; the scope's generic
    key convention, neither the PSU's ``outputs`` nor the dmm's
    ``inputs`` — a role that both sources and measures); the readings
    page is ``output`` (the readings ARE the output's live state — the
    class's source-and-measure-at-the-same-terminals nature is the
    page's whole point); the layout is dc_psu's ratio — readings 12
    raised, trend 7 recessed, table 5 raised — the class's difference
    from dc_psu is content, not geometry."""
    reference = load_document(REFERENCE)
    channels = reference["slots"]["channels"]
    assert channels["kind"] == "channels"
    assert channels["where_role"] == "source_measure"
    assert channels["key"] == "id"
    assert channels["label"] == "label"
    assert [page["id"] for page in reference["pages"]] == [
        "output",
        "configuration",
        "device-features",
    ]
    assert reference["pages"][0]["plot"] == {
        "kind": "time_series",
        "over_slot": "measure",
        "series": "numeric_variables",
    }
    layout = next(lp for lp in reference["layouts"] if lp["page_id"] == "output")
    assert [(s["id"], s["surface"], s["span"]) for s in layout["sections"]] == [
        ("readings", "raised", 12),
        ("trend", "recessed", 7),
        ("table", "raised", 5),
    ]


def test_the_output_slot_is_the_psu_shape_with_no_host_supplied() -> None:
    """§1's structural marker, machine-checked: the smu output action
    carries the OTDP conditional (``configuration_id`` required iff
    ``enabled: true`` — the corpus's own encoding of the directional
    asymmetry, the same schema the PSU's output carries) but the
    reference keeps the PSU's slot shape — a bare procedure slot, every
    field a real caller input, no ``host_supplied`` on any slot (the
    L15 eload made the conditional structural via ``host_supplied``;
    the smu inherits the dc_psu posture verbatim, per the design §4.1 —
    the inheritance L11 recorded with this class named in it)."""
    reference = load_document(REFERENCE)
    output = reference["slots"]["output"]
    assert output["kind"] == "procedure"
    assert output["action"] == OUTPUT_ACTION
    assert "host_supplied" not in output
    assert "host_supplied" not in reference["slots"]["measure"]
    assert "host_supplied" not in reference["slots"]["configure"]
    assert "host_supplied" not in reference["slots"]["channels"]


def test_the_catalog_conditional_keys_the_engage_direction() -> None:
    """The directional inheritance's corpus corroboration, machine-checked
    (L11 §2.2's verdict, inherited verbatim): the catalog's output
    input_schema carries an ``allOf/if/then`` making ``configuration_id``
    required exactly when ``enabled`` is true — the energise direction
    must name the commissioned configuration it will source at (the
    values clause of the section C.1 confirm), while the de-energise
    direction is bare ``channel`` + ``enabled``. A catalog edit that
    drops or inverts the conditional reddens this arm."""
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


def test_the_energise_confirm_values_pair_by_the_sourced_function() -> None:
    """The smu's own directional wrinkle (the design §4.2, recorded as
    the safety-behaviours slice's input), pinned from BOTH sides so the
    pairing cannot be flattened later: the catalog's configure schema
    declares the function-selected source — a ``source_function`` enum
    of exactly the two sourcing modes, with the level and the
    opposite-quantity compliance as numbers beside it — and the
    reference's ``output-control`` deviation names the function-dependent
    pairing in its reason (the transpose rule: volts against amperes
    when sourcing one, the transpose when sourcing the other). A confirm
    that flattened the values to a single pair would name the wrong
    quantity for one of the two functions; this arm keeps the pairing
    visible as data."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    schema = catalog["actions"][CONFIGURE_ACTION]["input_schema"]
    properties = schema.get("properties", {})
    assert properties["source_function"]["enum"] == ["voltage", "current"]
    assert properties["level"]["type"] == "number"
    assert properties["compliance_abs"]["type"] == "number"
    for field in ("source_function", "level", "compliance_abs"):
        assert field in schema.get("required", []), field
    reference = load_document(REFERENCE)
    row = next(
        r for r in reference["cannot_derive"] if str(r["id"]) == "output-control"
    )
    reason = str(row["reason"])
    assert "opposite-quantity" in reason, reason
    assert "transpose" in reason, reason


def test_the_reference_authors_structure_not_data() -> None:
    """A6/D2, machine-checked: no numeric literals outside the structural
    set (layout spans and plot indices), and no authored data strings —
    no values, no units, no channel names, no quantity names, none of
    the configure schema's field names, and none of the smu's own enum
    members (the two sourcing modes, the two sense wirings — they appear
    nowhere: the function-selected source is descriptor-side
    configuration data, §3.2's expressed-with-zero-motion difference
    precisely because the reference never names it). Data arrives via
    the descriptor and catalog at expansion."""
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
    # fixture data string, a configure field name or a mode enum member;
    # the STRUCTURAL surface (where a data binding would launder —
    # slots, pages, layouts, expect, targets) carries none of them even
    # as a substring. Prose reasons are authored explanation, not data.
    fixture = load_document(DESCRIPTOR)
    banned: set[str] = {"voltage", "current", "two_wire", "four_wire"}
    for field_name in (
        "source_function",
        "level",
        "compliance_abs",
        "sense",
        "range",
    ):
        banned.add(field_name)
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
    """The family schema admits the source-measure-shaped reference: five
    slots (channels with the third-role free string / dataset /
    configuration / procedure / vendor_actions), three pages with a
    time_series plot over the measure slot, one layout block, the closed
    count grammar."""
    validate_reference_document(load_document(REFERENCE), corpus=corpus_root())


# --- the sweep-absence arm (RC-L16-1, this class's addition) ----------------------


def _derive_over_committed_pair() -> Any:
    """The gateway-side expansion of the committed example over the
    committed birth reference — the derivation the sweep-absence arm
    reads. Raises ``ClassRefusal`` (failing the arm) if the derivation
    refuses the unslotted optional five."""
    return derive_attachment(DESCRIPTOR.read_bytes(), corpus=corpus_root())


def _sweep_absence_violations(derived: Any) -> list[str]:
    """The deferral's live assertion, as a violation list: empty means
    the sweep block is absent-but-covered; any entry is a sweep-derived
    component the birth surface refuses (or a coverage failure)."""
    violations: list[str] = []
    for target in derived.catalogue["targets"]:
        # Post-#525 the catalogue also carries the example's OBSERVATION
        # targets (kind: observation, keyed by parameter_id) — an
        # observation names no action, so only action-carrying targets
        # can name a sweep URN.
        if str(target.get("action_id", "")) in SWEEP_URNS:
            violations.append(f"catalogue-target:{target['action_id']}")
    for page in derived.manifest["pages"]:
        for binding in page["bindings"]:
            if str(binding) in SWEEP_SLUGS:
                violations.append(f"page-binding:{page['id']}:{binding}")
    block = derived.manifest["extensions"][LAYOUT_EXTENSION_KEY]
    for layout_page in block["pages"]:
        for section in layout_page.get("sections", []):
            for child in section.get("children", []):
                binding_id = str(child.get("binding_id", ""))
                if binding_id in SWEEP_SLUGS and layout_page["page_id"] != (
                    "device-features"
                ):
                    violations.append(
                        f"layout-control:{layout_page['page_id']}:{binding_id}"
                    )
    return violations


def _device_features_binding_ids(derived: Any) -> set[str]:
    """The binding ids whose controls render on the Device features page
    (the vendor_actions coverage home)."""
    block = derived.manifest["extensions"][LAYOUT_EXTENSION_KEY]
    page = next(
        p for p in block["pages"] if p["page_id"] == "device-features"
    )
    ids: set[str] = set()
    for section in page.get("sections", []):
        for child in section.get("children", []):
            binding_id = str(child.get("binding_id", ""))
            if binding_id:
                ids.add(binding_id)
    return ids


def test_the_sweep_absence_holds_over_the_committed_pair() -> None:
    """RC-L16-1's green half — the deferral as a live assertion over the
    real expansion, not prose. Four claims, each machine-checked:

    1. NO REFUSAL: the derivation over the committed pair succeeds — the
       committed example declares all eight profile actions and the
       birth reference slots three; if the derivation refused
       declared-but-unslotted optional actions despite the
       vendor_actions slot, THIS line would raise and the design's
       named fallback (§3.1) would activate. The falsifier is armed.
    2. NO SWEEP COMPONENT: no catalogue target, no page binding and no
       layout control names a sweep slug outside the coverage home —
       the five deferred actions derive nothing on the signature page.
    3. COVERED, NOT SILENT: the sweep URNs' controls resolve on the
       Device features page (D14's unclaimed-URN hook) — the four
       expressible actions render there; the fifth (configure_sweep)
       derives NO control because its pattern-narrowed channel field
       pins it at L0 — the closed vocabulary's honest answer, asserted
       by name so its later landing is a visible change.
    4. THE SIGNATURE PAGE IS UNTOUCHED BY THE SWEEP: post-#525 the
       output page row binds its OBSERVATION bindings (the example
       declares its readable parameters — the zero-parameter shape that
       bound nothing is the state this arm asserted before the corpus
       fix); the sweep-absence claim is that NOTHING ELSE joins them,
       asserted as the exact expected observation set derived from the
       descriptor's own channels x quantities under the plot's over
       slot. The layout's authored children bind the measure slot only,
       and the layout block carries exactly one plot (the time_series
       over the measure slot) — no run panel, no second plot."""
    derived = _derive_over_committed_pair()
    assert _sweep_absence_violations(derived) == []
    feature_ids = _device_features_binding_ids(derived)
    assert {"arm", "trigger", "abort", "fetch"} <= feature_ids, feature_ids
    assert "configure_sweep" not in feature_ids, feature_ids
    output_page = next(
        p for p in derived.manifest["pages"] if p["id"] == "output"
    )
    reference = load_document(REFERENCE)
    over = str(reference["pages"][0]["plot"]["over_slot"])
    fixture = load_document(DESCRIPTOR)
    expected_observations = {
        f"{over}-{channel['id']}-{quantity}"
        for channel in _source_measure_channels(reference, fixture)
        for quantity in channel["quantities"]
    }
    assert set(output_page["bindings"]) == expected_observations, output_page
    output_layout = next(
        p
        for p in derived.manifest["extensions"][LAYOUT_EXTENSION_KEY]["pages"]
        if p["page_id"] == "output"
    )
    binding_ids = {
        str(child["binding_id"])
        for section in output_layout["sections"]
        for child in section.get("children", [])
        if "binding_id" in child
    }
    assert binding_ids == {"measure"}, binding_ids
    plots = [
        child
        for layout_page in derived.manifest["extensions"][LAYOUT_EXTENSION_KEY][
            "pages"
        ]
        for section in layout_page.get("sections", [])
        for child in section.get("children", [])
        if "plot_index" in child
    ]
    assert len(plots) == 1, plots


def test_a_slotted_sweep_action_reds_the_absence_arm() -> None:
    """RC-L16-1's RED half — the arm has teeth, demonstrated on a mutated
    reference (never the committed bytes): slotting ONE sweep action
    (``arm`` as a procedure slot bound beside the observation on the
    output page — the shape the sweep landing slice would author)
    produces exactly the violations the green half refuses: the
    catalogue gains the arm target and the output page's authored
    sections gain the arm's control (an L2 action derives its button on
    its plan page). The deferral's absence is load-bearing — a later
    sweep slot that does not re-run this design REDS here."""
    reference = load_document(REFERENCE)
    reference["slots"]["arm"] = {
        "kind": "procedure",
        "action": "otdp.smu.arm/1.0.0",
    }
    reference["pages"][0]["binding_slots"].append("arm")
    derived = derive_attachment(
        DESCRIPTOR.read_bytes(),
        corpus=corpus_root(),
        references_override=[reference],
    )
    violations = _sweep_absence_violations(derived)
    assert any(v.startswith("catalogue-target:otdp.smu.arm") for v in violations), (
        violations
    )
    assert "layout-control:output:arm" in violations, violations


# --- the directional deviation (inherited from L11, verbatim) ---------------------


def _direction_pin_violations(reference: dict[str, Any]) -> list[str]:
    """The pin's assertions over one reference document: the output
    control value, the cannot_derive id, and the forbid id — each named
    on failure so the RED demonstrations can assert WHICH pin fired."""
    violations: list[str] = []
    controls = reference["expect"]["controls"]
    if controls.get(OUTPUT_ACTION) != "deviation":
        violations.append(f"control:{controls.get(OUTPUT_ACTION)!r}")
    ids = {str(row["id"]) for row in reference["cannot_derive"]}
    if "output-control" not in ids:
        violations.append("cannot_derive:output-control")
    if "intermediated-energy-removing-action" not in reference["expect"]["forbid"]:
        violations.append("forbid:intermediated-energy-removing-action")
    return violations


def test_the_direction_pin_holds_over_the_committed_reference() -> None:
    """L11 §2.2's verdict, inherited verbatim (the record's deferral row
    names this class): ``output`` is a declared deviation (the per-action
    control vocabulary cannot split energise from de-energise),
    ``output-control`` names the directional deviation in the ledger
    with the ruling's own words, and
    ``intermediated-energy-removing-action`` is carried with its ground
    — the smu owns an energy-removing direction on ``output`` AND the
    deferred sweep's abort is the source-safe-transition action §10
    itself names, so the forbid's reason is stronger here than on the
    PSU (RC-L16-4; the refute lane is invited to kill it). The
    configure row's preset-mediation is the birth controls plan's other
    half."""
    reference = load_document(REFERENCE)
    assert _direction_pin_violations(reference) == []
    assert reference["expect"]["controls"][CONFIGURE_ACTION] == "preset"
    row = next(
        r for r in reference["cannot_derive"] if str(r["id"]) == "output-control"
    )
    assert "energise" in str(row["reason"])
    assert "R-DEENERGISE-1" in str(row["reason"])


def test_the_ungated_energise_misread_reds_the_pin() -> None:
    """The first RED demonstration (L11's own, inherited): mutating the
    output control to ``button`` — the ungated-energise misread — fires
    the pin's control assertion while the other two pins stay quiet."""
    reference = load_document(REFERENCE)
    reference["expect"]["controls"][OUTPUT_ACTION] = "button"
    violations = _direction_pin_violations(reference)
    assert violations == ["control:'button'"], violations


def test_the_gated_deenergise_misread_reds_the_pin() -> None:
    """The second RED demonstration: mutating the output control to
    ``staging`` — the gated-disengage misread, burying the one ungated
    action behind a staged control — fires the same control assertion.
    The pin discriminates in BOTH directions."""
    reference = load_document(REFERENCE)
    reference["expect"]["controls"][OUTPUT_ACTION] = "staging"
    violations = _direction_pin_violations(reference)
    assert violations == ["control:'staging'"], violations


def test_dropping_the_forbid_id_reds_the_pin() -> None:
    """The third RED demonstration: dropping
    ``intermediated-energy-removing-action`` from the forbid set fires
    the pin's forbid assertion while the control value stays honest."""
    reference = load_document(REFERENCE)
    reference["expect"]["forbid"] = [
        fid
        for fid in reference["expect"]["forbid"]
        if fid != "intermediated-energy-removing-action"
    ]
    violations = _direction_pin_violations(reference)
    assert violations == ["forbid:intermediated-energy-removing-action"], violations


# --- the pattern-library output page ----------------------------------------------


def test_tile_count_and_labels_derive_from_the_otdp_example() -> None:
    """D2 at the composition: the page's reading tiles are one per
    (channel, quantity) pair of the OTDP class example's declared
    source_measure channels — 2 x 3 computed from the descriptor, never
    a literal; every tile label names its channel label and quantity,
    both corpus strings."""
    page = classref.render_smu_output_page()
    descriptor = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
    smu = _source_measure_channels(reference, descriptor)
    expected_tiles = sum(len(c["quantities"]) for c in smu)
    assert expected_tiles >= 1
    tiles = re.findall(r'class="bw-reading[ \"]', page)
    assert len(tiles) == expected_tiles
    for channel in smu:
        for quantity in channel["quantities"]:
            assert f"{channel['label']} · {quantity}" in page, (
                channel["id"],
                quantity,
            )


def test_the_trend_is_one_plot_with_the_disclosed_two_traces() -> None:
    """One engineering plot (the layout block's trend section); the trace
    set is the disclosed author choice (the record's channel_hints
    matter, dc_psu's own posture): voltage and current of the first
    declared source_measure channel, matching the mockup's two traces."""
    page = classref.render_smu_output_page()
    figures = re.findall(r'class="bw-plot[ \"]', page)
    assert len(figures) == 1
    descriptor = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
    first = _source_measure_channels(reference, descriptor)[0]
    assert f"{first['label']} · voltage" in page
    assert f"{first['label']} · current" in page


def test_the_table_covers_every_channel_quantity_pair() -> None:
    """The data table's body is one row per (channel, quantity) pair —
    the same derivation as the tiles; the quality column carries the
    mockup's own wording (Verified / At compliance)."""
    page = classref.render_smu_output_page()
    descriptor = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
    smu = _source_measure_channels(reference, descriptor)
    body_rows = re.findall(r"<tr[^>]*>", page)[1:]  # the header row excluded
    assert len(body_rows) == sum(len(c["quantities"]) for c in smu)
    assert "Verified" in page
    assert "At compliance" in page


def test_the_page_sections_mirror_the_reference_layout_block() -> None:
    """The composition's sections carry the layout block's own surfaces
    and spans (data-bw-span): readings 12 raised, trend 7 recessed, table
    5 raised — the dc_psu ratio, the sourcing class's own geometry. An
    edit to the reference's layout block reddens the composition."""
    page = classref.render_smu_output_page()
    reference = load_document(REFERENCE)
    layout = next(lp for lp in reference["layouts"] if lp["page_id"] == "output")
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
    presentation is a named deviation; the staged-source idiom is
    cannot_derive; and the sweep block is DEFERRED — no run panel, no
    second plot, the honest birth surface the design's §2 paints) — the
    page fabricates none of them."""
    page = classref.render_smu_output_page()
    assert "bw-mode-banner" in page
    banner = page.find("bw-mode-banner")
    tile = page.find('class="bw-reading')
    assert -1 < banner < tile
    for surface in ("bw-alert-bubble", "bw-plot", "bw-data-table"):
        assert surface in page, surface
    assert "bw-rotary" not in page  # source-staging is cannot_derive
    assert "bw-confirm" not in page  # the directional control is a deviation
    assert "<button" not in page  # nothing on this page is runnable


def test_the_compliance_alert_renders_the_mockup_wording() -> None:
    """The alert's title and condition wording trace to the mockup (the
    spec) — the class's own condition (compliance active, the current
    held at the configured compliance); the device-specific suffix
    stays mockup-side."""
    page = classref.render_smu_output_page()
    assert "Compliance active" in page
    assert "held at configured compliance" in page


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_class_page_exports_in_both_themes(tmp_path: Path, theme: str) -> None:
    patterns.export(tmp_path)
    path = tmp_path / "patterns" / theme / "class-smu.html"
    assert path.is_file(), path
    html = path.read_text(encoding="utf-8")
    assert "data-bw-pattern-library" in html
    assert 'data-bw-pattern-page="class-smu"' in html
    assert "Reference channel 1 · voltage" in html


def test_the_class_page_census_entry_is_registered() -> None:
    """The page rides the PATTERNS census: kind class-page on the
    class-smu page (the smu's own page slug — dc_psu owns class-output,
    the scope precedent's rename-on-collision), row-keyed to the
    family's smu reference, fixture the readings-kind output page (the
    design §6 arm 8's naming)."""
    entry = next(e for e in patterns.PATTERNS if e.page == "class-smu")
    assert entry.kind == "class-page"
    assert entry.row_id == "plugin-ui-class-reference::class-smu"
    assert entry.fixture_id == "readings"
