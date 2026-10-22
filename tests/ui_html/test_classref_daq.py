"""The daq class reference (L17 of the class sweep; design record
``.claude/deep-review/2026-10-19-classref-l17-daq-design.md``): the
mockup-consistency arm (A3), the pattern-library capture-page
composition with its drift guard — and the sweep's first
real-consumer conformance arm (A10) over a vendored public descriptor.

A3, eighth class of the sweep — the second capture-shaped one, the
oscilloscope's action-identical sibling with a different substance
(engineering units per channel instead of probe-scaled display; the
boundary settled at the design's §3.1 — two classes stay, no forked
machinery). The mockup
(``docs/internal/ui-styleguide-mockups/class-daq.html``) is authored
WITH the reference (the §E.1 hooks and the placement contract from
birth); the reference is the data; this test is the bridge, keyed on
the shared census instrument (``tests/ui_html/classref_census.py``)
under the L13 extension: the capture classes' hook family set
(``bw-plot``, ``bw-button``, ``bw-alert-bubble``), their container map
(the traces region, the run panel) and the idiom-surface classes (the
trigger marker, the cursor pair, the unit/calibration context line —
non-contract idioms that must carry NO ``bw-`` hook).

Unlike the scope there IS a derived fixture: the mockup is authored to
the real consumer's six-channel shape while the committed OTDP example
declares two, so the census resolves over F-daq-2 — a six-channel
fixture DERIVED IN-TEST from the committed example (the channel list
widened to six invented ids, quantities unchanged — L11's
two-fixture pattern, second application). Six traces sit at slots 0-5
of the 16-id §E.2 assignment ceiling, all dash-1, six distinct
colours; one distinct unit renders one y-axis. The kill is
two-directional by construction: a mockup edit that changes a hook
count reds against the resolved expectation, and a reference edit that
changes the derivation (a count expression, the plot binding, the
channels slot's role) reds against the mockup's counts. A mockup edit
that does NOT redden the test is the instrument failing — report,
never a quiet pass (the record's A3 wording).

A10, this class's own arm — the sweep's first conformance claim
against a SHIPPED plugin's public bytes: a vendored byte-copy of the
``community.benchweave-adc.adc-6ch-12bit`` descriptor (public fork,
pull-only; source commit named at ``PARKVIEW_FIXTURE`` below; no
network in CI — RC-L17-4) runs through the design's structural
acceptance rule and ACCEPTS: 6 analogue channels, 6 traces within the
16-id ceiling, the optional trigger bound, one y-axis, the dataset's
own unit. The three kill arms fire: a profile flip selects nothing, a
trigger-less mutant still accepts (acceptance is
trigger-independent), and a three-distinct-unit mutant hits §E.2.3's
honest refusal — no silent conflation.

The expansion side beyond the census (derive-ui/verify-ui gates) is
the batched SDK leg's work and rides that train; what this file pins
is the corpus pair's structure and the gateway-side expansion's
honest shape — the reference document, its schema admission, the
composition the host renders from it, and the real consumer's
conformance answer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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
    derive_attachment,
    validate_reference_document,
)
from benchweave.vendoring import corpus_root

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = REPO_ROOT / "standards/plugin-ui-class-reference/0.3.0"
REFERENCE = FAMILY_DIR / "class-daq.json"
DESCRIPTOR = REPO_ROOT / "standards/otdp/0.2.4/examples/class-daq.json"
MOCKUP = REPO_ROOT / "docs/internal/ui-styleguide-mockups/class-daq.html"

#: The vendored real-consumer descriptor (A10; RC-L17-4): a byte-copy
#: of the public plugin's descriptor, read pull-only over ``gh api``
#: at design time and vendored at build time so CI never touches the
#: network. Source: the public fork's ``plugins/adc_6ch_12bit/
#: descriptor.json`` at commit d867f13eafe57666ad3b44fd9129ddc8827f3208
#: (the design record §4 walks its bytes); regenerating the fixture
#: from that commit must reproduce it byte-for-byte, and a drifted
#: upstream descriptor is a finding to surface, never a silent pass.
PARKVIEW_FIXTURE = (
    REPO_ROOT / "tests/ui_html/fixtures/parkview-adc-6ch-12bit-descriptor.json"
)

#: The capture classes' hook families (the L13 census extension,
#: second capture instance): the run panel's ``bw-button`` joins the
#: plot and alert hooks. The ``bw-reading``/``bw-data-table`` families
#: are the readings classes' own — the capture page carries neither a
#: reading tile nor a table (the scope ruling, carried).
DAQ_HOOKS: tuple[str, ...] = ("bw-plot", "bw-button", "bw-alert-bubble")

#: The placement contract for this mockup: each container-scoped hook
#: sits in its mockup container (the traces region, the run panel).
DAQ_CONTAINERS: dict[str, str] = {
    "bw-plot": "traces",
    "bw-button": "run",
}

#: The idiom surfaces (the design's §2): non-contract markers painted
#: over host knowledge — the trigger marker (line + readout chip), the
#: cursor pair with its Δ readout, and the unit/calibration context
#: line (the daq's own: a raw-counts digitiser's honest face). They
#: carry NO ``bw-`` hook.
DAQ_IDIOMS: frozenset[str] = frozenset(
    {"trigger-marker", "cursor-pair", "calibration-context"}
)

#: component name -> the §E.1 hook root the mockup carries for it.
COMPONENT_HOOKS: dict[str, str] = {
    "engineering-plot": "bw-plot",
    "button": "bw-button",
}

#: The §E.2.1 series-assignment ceiling (plugin-ui ``$defs.plot.y``
#: ``maxItems``): the declared trace id set an assignment carries.
TRACE_ID_CEILING = 16

#: The §E.2.3 y-axis rule: one distinct unit renders one y-axis, two
#: render two — three or more draw no traces and render a visible
#: refusal naming the condition. The heterogeneous daq's honest
#: boundary, already contracted.
MAX_Y_AXES = 2


def _daq_census() -> dict[str, dict[str, int]]:
    return hook_census(MOCKUP, hooks=DAQ_HOOKS)


def _analogue_channels(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> list[dict[str, Any]]:
    """The channels the reference's channels slot resolves — the role the
    SLOT names (never a literal role string here), declaration order."""
    where_role = str(reference["slots"]["channels"]["where_role"])
    return [c for c in descriptor["channels"] if str(c["role"]) == where_role]


def _derived_six_channel_fixture() -> dict[str, Any]:
    """F-daq-2, derived in-test from the committed example (the design
    §1's two-fixture pattern, second application): the channel list
    widened to six invented ids following the example's own id/label
    pattern, quantities unchanged, actions unchanged (the example
    declares all five). The mockup is authored to this shape — the
    real consumer's channel COUNT, its identity nowhere (public-repo
    discipline: ``ch1``..``ch6`` are the mockup's own invented ids)."""
    document = load_document(DESCRIPTOR)
    channels: list[dict[str, Any]] = []
    for index in range(len(document["channels"]), 6):
        channels.append(
            {
                "id": f"ch{index + 1}",
                "label": f"Reference channel {index + 1}",
                "role": document["channels"][0]["role"],
                "quantities": list(document["channels"][0]["quantities"]),
                "parameter_names": [],
            }
        )
    document["channels"] = list(document["channels"]) + channels
    return document


def _structural_counters(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The closed counter set over (reference x fixture): every counter is
    an expression over the fixture's declared channels, their declared
    quantities, and the capture layout's declared run children — never a
    count imported from the mockup."""
    channels = _analogue_channels(reference, descriptor)
    n_analogue_channels = len(channels)
    n_trace_variables = sum(len(c["quantities"]) for c in channels)
    capture = next(
        lp for lp in reference["layouts"] if lp["page_id"] == "capture"
    )
    run = next(s for s in capture["sections"] if s["id"] == "run")
    slots = reference["slots"]
    n_run_actions = 0
    for child in run["children"]:
        slot = slots[str(child["binding_id"])]
        if str(slot["action"]) in descriptor["actions"]:
            n_run_actions += 1
    return {
        "n_analogue_channels": n_analogue_channels,
        "n_trace_variables": n_trace_variables,
        "n_run_actions": n_run_actions,
        "n_pages": len(reference["pages"]),
    }


def _resolved_capture_expectation(
    reference: dict[str, Any], descriptor: dict[str, Any]
) -> dict[str, int]:
    """The expect.components rows scoped to the capture page, resolved
    over F-daq-2 (the six-channel derived fixture the mockup is
    authored to)."""
    counters = _structural_counters(reference, descriptor)
    resolved: dict[str, int] = {}
    for name, row in reference["expect"]["components"].items():
        if row.get("per_page") == "capture":
            resolved[name] = resolve_count(str(row["count"]), counters)
    return resolved


# --- A3: the mockup-consistency arm ---------------------------------------------


def test_the_mockup_carries_the_contract_hooks_in_both_themes() -> None:
    """The hook pass (RC-L11-3), from birth (the capture convention,
    third authored-from-birth instance): both theme sections carry
    every hook family the census keys on — a hook absent from one
    theme is a composition break, not a style choice."""
    census = _daq_census()
    assert set(census) == {"light", "dark"}
    for theme, hooks in census.items():
        for hook in DAQ_HOOKS:
            assert hooks[hook] >= 1, (theme, hook)


def test_mockup_hook_counts_equal_the_resolved_expectation() -> None:
    """A3, the load-bearing arm: per theme section, the mockup's hook
    counts EQUAL the reference's resolved expectation over F-daq-2 (6
    analogue channels x 1 declared quantity = 6 traces; the fixture
    declares all five actions = 3 run buttons) — the counts derived on
    BOTH sides, never literals on either.

    Kill direction 1: edit the mockup's count — a trace dropped from
    the legend changes nothing here, but a button dropped from the run
    panel reds against the resolved expectation.
    Kill direction 2: edit the reference's derivation — a count
    expression, the plot binding, the channels slot's role — and the
    RESOLVED side diverges from the mockup and this reds."""
    reference = load_document(REFERENCE)
    fixture = _derived_six_channel_fixture()
    resolved = _resolved_capture_expectation(reference, fixture)
    assert set(resolved) == {"engineering-plot", "button"}, resolved
    counters = _structural_counters(reference, fixture)
    # the derived fixture's own shape: 6 channels x 1 quantity within
    # the 16-id ceiling, 3 declared run actions — the numbers the
    # mockup is authored to (the census keys on them; a fixture change
    # reds the composition, never this arm)
    assert counters["n_trace_variables"] == 6
    assert counters["n_trace_variables"] <= TRACE_ID_CEILING
    assert counters["n_run_actions"] == 3
    census = _daq_census()
    for theme, hooks in census.items():
        for name, hook in COMPONENT_HOOKS.items():
            assert hooks[hook] == resolved[name], (theme, hook, resolved[name])


def test_every_hook_sits_on_its_contract_root_and_container() -> None:
    """The count-conserving-move kill and the idiom-surface kill (the
    design's §6 arm 3): every hook is on its §E.1 root element, the
    container-scoped hooks sit in their containers, and the idiom
    surfaces (trigger marker, cursor pair, calibration context line)
    carry NO ``bw-`` hook — a non-contract idiom must never present as
    a contract component. The count census alone is placement-blind: a
    hook moved count-conservingly into the wrong container reds HERE
    while the count arm stays green, and a ``bw-`` class
    reverse-planted on a marker chip or the context line reds here."""
    parser = HookCensus(
        hooks=DAQ_HOOKS,
        containers=DAQ_CONTAINERS,
        idiom_classes=DAQ_IDIOMS,
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


def _census_of(html: str, **kwargs: Any) -> HookCensus:
    """The census over a MUTATED copy of the mockup (the kill arms'
    vehicle — never the committed bytes)."""
    parser = HookCensus(
        hooks=kwargs.pop("hooks", DAQ_HOOKS),
        containers=kwargs.pop("containers", DAQ_CONTAINERS),
        idiom_classes=kwargs.pop("idiom_classes", DAQ_IDIOMS),
    )
    parser.feed(html)
    return parser


def _placement_reds(parser: HookCensus, hook: str) -> int:
    """The count of one hook family's occurrences that violate the
    placement contract (root tag or container) — the mutation arms
    assert this rises while the count census stays green."""
    reds = 0
    for _theme, family, tag, ancestors in parser.placements:
        if family != hook:
            continue
        root_ok = tag == PLACEMENT_TAG[family]
        container = parser.containers.get(family)
        container_ok = container is None or any(
            container in ancestor_classes
            for _ancestor_tag, ancestor_classes in ancestors
        )
        if not (root_ok and container_ok):
            reds += 1
    return reds


def test_the_count_conserving_move_of_a_button_onto_the_figure_reds() -> None:
    """The count-conserving-move kill, first named mutation,
    demonstrated RED (the design's A3): a ``bw-button`` moved from the
    run panel onto the capture figure in BOTH themes — the count
    census stays green under the move (three per theme either way) and
    the PLACEMENT arm is what reds: the moved occurrence's root is a
    section (the figure), not the §E.1 button root, and the run panel
    is no longer its container."""
    html = MOCKUP.read_text(encoding="utf-8")
    moved = html.replace(
        '<button class="bw-button">Abort</button>',
        '<button>Abort</button>',
    ).replace(
        '<div class="plot-head"><span>CAPTURE · SIX CHANNELS</span>',
        '<div class="plot-head"><button class="bw-button">Abort</button>'
        '<span>CAPTURE · SIX CHANNELS</span>',
    )
    assert moved != html, "the mutation must change the mockup bytes"
    parser = _census_of(moved)
    # the count arm stays green under the move: still the resolved count
    reference = load_document(REFERENCE)
    fixture = _derived_six_channel_fixture()
    resolved = _resolved_capture_expectation(reference, fixture)
    for theme, hooks in parser.counts.items():
        assert hooks["bw-button"] == resolved["button"], (theme, hooks)
    assert _placement_reds(parser, "bw-button") >= 2, (
        "the move must red placement in both themes"
    )


def test_the_count_conserving_move_of_the_plot_onto_the_run_panel_reds() -> None:
    """The second named mutation, demonstrated RED: the ``bw-plot`` hook
    moved from the capture section onto the run panel's card in BOTH
    themes — counts conserve (one per theme) and the placement arm reds
    on both the root (section still, but the run panel's card is not
    the traces container) and the container (the run panel is not the
    traces region)."""
    html = MOCKUP.read_text(encoding="utf-8")
    moved = html.replace(
        '<section class="capture bw-plot">', '<section class="capture">'
    ).replace(
        '<section class="card run-panel">',
        '<section class="card run-panel bw-plot">',
    )
    assert moved != html, "the mutation must change the mockup bytes"
    parser = _census_of(moved)
    for theme, hooks in parser.counts.items():
        assert hooks["bw-plot"] == 1, (theme, hooks)
    assert _placement_reds(parser, "bw-plot") >= 2, (
        "the move must red placement in both themes"
    )


def test_a_hook_planted_on_an_idiom_surface_reds() -> None:
    """The no-hook-on-idiom-surface kill, demonstrated RED (the L13
    arm, second capture application): a ``bw-`` class reverse-planted
    on the calibration context line in BOTH themes — the hook counts
    conserve (the plant adds no counted hook family member... the
    ``bw-plot`` plant DOES count, so the count arm reds too) and the
    idiom arm reds outright: the idiom surface now carries a contract
    hook, presenting a host-knowledge idiom as a contract component.
    The context line is the daq's own honesty surface — a ``bw-`` hook
    there would claim the renderer derives the dataset's unit, and it
    never does."""
    html = MOCKUP.read_text(encoding="utf-8")
    planted = html.replace(
        '<p class="context calibration-context">',
        '<p class="context calibration-context bw-plot">',
    )
    assert planted != html, "the mutation must change the mockup bytes"
    parser = _census_of(planted)
    # the idiom arm reds: the context line now carries a bw- hook
    carrying = [
        (theme, tag, carried)
        for theme, tag, _classes, carried in parser.idiom_surfaces
        if "calibration-context" in _classes
    ]
    assert carrying, "the census recorded no calibration-context surfaces"
    for theme, tag, carried in carrying:
        assert carried != (), (theme, tag, carried)
    # the count arm reds with it: the plant counted as a second plot
    for theme, hooks in parser.counts.items():
        assert hooks["bw-plot"] == 2, (theme, hooks)


def test_both_themes_carry_the_identical_hook_census() -> None:
    """One composition, two themes: the hook census is theme-invariant."""
    census = _daq_census()
    assert census["light"] == census["dark"]


def test_the_alert_surface_is_one_per_theme_and_a_named_cannot_derive() -> None:
    """The mockup's alert aside is structure the composition renders and
    data the reference cannot derive: exactly one ``bw-alert-bubble`` per
    theme, and ``partial-capture-alert`` names it in the deviation ledger
    (the condition is the dataset's runtime `status: partial` +
    `status_reason` — observation state, data not structure)."""
    reference = load_document(REFERENCE)
    ids = {str(row["id"]) for row in reference["cannot_derive"]}
    assert "partial-capture-alert" in ids
    census = _daq_census()
    for theme, hooks in census.items():
        assert hooks["bw-alert-bubble"] == 1, theme


# --- A4: the selection halves ----------------------------------------------------


def test_the_reference_selects_for_the_class_descriptor() -> None:
    """A4's green half, gateway-side: the daq class example's profile now
    selects a corpus reference (``select_references`` returned None
    before the class existed — the pair banked RED at design time on
    the L11 branch head c64f3d05 and carried through this slice's base
    b02fbd08 by the L16 rotation, design record §6 arm 4)."""
    from benchweave.presentation.classref import select_references

    selected = select_references(corpus_root(), load_document(DESCRIPTOR))
    assert selected is not None and len(selected) == 1
    assert selected[0]["profile_id"] == "otdp.daq/1.0.0"


def test_the_real_consumer_selects_the_class_reference() -> None:
    """A4's real-consumer half — the sweep's first shipped consumer
    (the design §4): the vendored descriptor's profile selects this
    reference, so the moment the batch lands the L4 no-manifest
    fallback makes THIS reference the plugin's served presentation
    (the plugin ships no ``ui/`` manifest). The plugin pins
    ``otdp_version`` 0.2.2; the reference binds the profile, not the
    catalog version."""
    from benchweave.presentation.classref import select_references

    selected = select_references(
        corpus_root(), load_document(PARKVIEW_FIXTURE)
    )
    assert selected is not None and len(selected) == 1
    assert selected[0]["profile_id"] == "otdp.daq/1.0.0"


def test_an_oscilloscope_reference_refuses_the_daq_descriptor() -> None:
    """The class-identity falsifier, machine-checked (the design §3.1's
    first layer): a merged scope+daq document is not an expressible
    object in this family — ``profile_id`` binds exactly one OTDP
    profile. Expanding the daq example over the scope reference
    refuses at the profile-claim arm (the descriptor claims
    ``otdp.daq``, the reference binds ``otdp.oscilloscope``); the
    refusal is the boundary itself, not a descriptor-authoring
    artefact — every earlier arm passes and this one fires."""
    reference = json.loads(
        (FAMILY_DIR / "class-oscilloscope.json").read_text(encoding="utf-8")
    )
    descriptor = load_document(DESCRIPTOR)
    with pytest.raises(
        ClassRefusal, match="classref_invalid_reference: profile"
    ):
        derive_attachment(
            json.dumps(descriptor).encode(),
            corpus=corpus_root(),
            references_override=[reference],
        )


# --- the reference's own shape ---------------------------------------------------


def test_the_reference_owns_the_daq_slots_and_pages() -> None:
    """The slot-and-page shape, machine-checked: the channels slot is
    ``channels`` keyed on the role the SLOT names
    (``analogue_input``); the capture page is the analyser/scope
    geometry — traces recessed and dominant (span 12), the run panel
    raised below (span 12) — with a ``waveform`` plot over the capture
    slot (L13's widening, load-bearing here: the reference is
    schema-invalid without it, the design's P1e); the second capture
    class re-proves the geometry, carrying the scope's shape with
    different URNs and one extra cannot_derive row."""
    reference = load_document(REFERENCE)
    channels = reference["slots"]["channels"]
    assert channels["kind"] == "channels"
    assert channels["where_role"] == "analogue_input"
    assert channels["key"] == "id"
    assert channels["label"] == "label"
    assert [page["id"] for page in reference["pages"]] == [
        "capture",
        "configuration",
        "device-features",
    ]
    assert reference["pages"][0]["plot"] == {
        "kind": "waveform",
        "over_slot": "capture",
        "series": "numeric_variables",
    }
    layout = next(lp for lp in reference["layouts"] if lp["page_id"] == "capture")
    assert [(s["id"], s["surface"], s["span"]) for s in layout["sections"]] == [
        ("traces", "recessed", 12),
        ("run", "raised", 12),
    ]
    assert [c["binding_id"] for c in layout["sections"][1]["children"]] == [
        "arm",
        "abort",
        "trigger",
    ]


def test_the_trigger_slot_is_when_declared_and_the_lifecycle_is_host_supplied() -> None:
    """The daq's own structural wrinkle, machine-checked: ``trigger``
    is the family's first ``when_declared`` slot on a capture class
    (binds only when the descriptor declares it — both fixtures and
    the real consumer do; a trigger-less descriptor renders its ghost,
    RC-L13-3's ruling), and the lifecycle slots carry exactly the
    acquisition-lifecycle ``host_supplied`` field names — structural
    field NAMES, D2-clean (the values are runtime binding data)."""
    reference = load_document(REFERENCE)
    slots = reference["slots"]
    assert slots["trigger"]["when_declared"] is True
    assert slots["arm"]["host_supplied"] == [
        "configuration_id",
        "acquisition_id",
    ]
    assert slots["abort"]["host_supplied"] == ["acquisition_id"]
    assert slots["trigger"]["host_supplied"] == ["acquisition_id"]
    assert slots["capture"]["host_supplied"] == ["acquisition_id"]
    assert "host_supplied" not in slots["configure"]
    assert "host_supplied" not in slots["channels"]


def test_the_reference_authors_structure_not_data() -> None:
    """A6/D2, machine-checked: no numeric literals outside the structural
    set (layout spans and plot indices), and no authored data strings —
    no values, no units, no channel names, no quantity names, none of
    the configure schema's field names, and none of the daq's own enum
    members (the two sampling modes — they appear nowhere: the
    sampling mode is descriptor-side configuration data, the
    per-channel quantity/unit/range difference expressed with zero
    motion precisely because the reference never names it). The
    dataset unit the real consumer streams (``count``) is runtime data
    named by the ``calibration-context`` deviation, never by the
    structure. Data arrives via the descriptor and the fetch dataset
    at expansion."""
    reference = load_document(REFERENCE)
    allowed_numbers = {12, 0}  # the grid span 12; plot_index 0

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
        if isinstance(value, bool):
            continue
        assert not isinstance(value, float), value
        if isinstance(value, int):
            assert value in allowed_numbers, value
    # the authored-string census: no value anywhere in the document is a
    # fixture data string, a configure field name, a mode enum member or
    # the dataset unit — exact-match over every string. The STRUCTURAL
    # surface (where a data binding would launder — slots, pages,
    # layouts, expect, targets) carries none of them even as a
    # substring, with ONE named exception: the closed count grammar's
    # own ``count`` KEY (``{"count": "1"}``) shares its spelling with
    # the raw-counts unit, so the unit's substring ban cannot key on
    # it — the unit-as-data would appear as a VALUE, and the
    # exact-match ban carries that half. Prose reasons are authored
    # explanation, not data.
    fixture = load_document(DESCRIPTOR)
    banned: set[str] = {
        "quantity",
        "unit",
        "range",
        "sample_rate_hz",
        "sample_count",
        "sampling",
        "simultaneous",
        "multiplexed",
        "count",
    }
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
    for data_string in banned - {"count"}:
        assert data_string not in raw_structural, data_string


def test_the_reference_validates_against_the_family_schema() -> None:
    """The family schema admits the capture-shaped reference: seven
    slots (channels / dataset / configuration / three procedures — the
    lifecycle quartet with ``fetch`` as the dataset action — /
    vendor_actions), three pages with a ``waveform`` plot over the
    capture slot, one layout block, the closed count grammar."""
    validate_reference_document(load_document(REFERENCE), corpus=corpus_root())


def test_the_calibration_context_is_the_classs_own_deviation() -> None:
    """The daq's one extra cannot_derive row over the scope (the design
    §3.1's third layer): ``calibration-context`` names the honesty —
    the dataset's unit and calibration state are runtime data, and the
    class presents the unit the dataset carries, never a nicer one.
    The real consumer streams raw counts with calibration
    ``not_applied``; the page this reference yields names ``count`` on
    its axis until an upstream measurement-profiles layer exists."""
    reference = load_document(REFERENCE)
    row = next(
        r for r in reference["cannot_derive"] if str(r["id"]) == "calibration-context"
    )
    reason = str(row["reason"])
    assert "runtime data" in reason, reason
    ids = {str(r["id"]) for r in reference["cannot_derive"]}
    assert ids == {
        "acquisition-settings",
        "trigger-marker",
        "cursor-readout",
        "partial-capture-alert",
        "calibration-context",
        "channel-names",
    }, ids


# --- A10: the real-consumer conformance arm (RC-L17-4) ----------------------------


def _acceptance(
    reference: dict[str, Any],
    descriptor: dict[str, Any],
    trace_units: dict[tuple[str, str], str],
) -> tuple[str, dict[str, Any]]:
    """The design's structural acceptance rule (§6 P2), encoded:
    profile match; required-slot actions present; ``when_declared``
    binding; channel role resolution; one trace per (channel, declared
    quantity) against the 16-id ceiling; the §E.2.3 unit rule over the
    derived trace set's units. Returns ``(verdict, findings)`` —
    ``("accepts", {...})`` or the refusal arm that fired. The trace
    units are the dataset's own (runtime data the adapter's fetch
    carries, keyed by (channel id, quantity) here — the vendored
    descriptor's adapter doc names the unit its dataset streams)."""
    findings: dict[str, Any] = {}
    if str(reference["profile_id"]) not in descriptor["profiles"]:
        return ("no reference selected", findings)
    slots = reference["slots"]
    for key, slot in slots.items():
        if slot.get("kind") not in {"dataset", "configuration", "procedure"}:
            continue
        declared = str(slot["action"]) in descriptor["actions"]
        if slot.get("when_declared"):
            findings[f"slot:{key}"] = "bound" if declared else "unbound"
        elif not declared:
            return (f"classref_required_action_absent: {slot['action']}", findings)
    channels = _analogue_channels(reference, descriptor)
    if not channels:
        return ("classref_no_lanes: no channels resolve", findings)
    traces = [
        (str(c["id"]), str(q)) for c in channels for q in c["quantities"]
    ]
    findings["n_channels"] = len(channels)
    findings["n_traces"] = len(traces)
    if len(traces) > TRACE_ID_CEILING:
        return (f"trace id ceiling exceeded: {len(traces)}", findings)
    units = {trace_units[trace] for trace in traces}
    findings["units"] = sorted(units)
    if len(units) > MAX_Y_AXES:
        return (
            "y-axis refusal: more than two distinct units — the plot draws "
            "no traces and renders a visible refusal naming the condition",
            findings,
        )
    return ("accepts", findings)


def _parkview_trace_units(descriptor: dict[str, Any]) -> dict[tuple[str, str], str]:
    """The trace-unit map for the vendored descriptor: the adapter's
    fetch drains buffered samples into an otdp-measurement waveform
    dataset in raw counts — every (channel, declared quantity) trace
    carries the dataset's one unit (the adapter's own doc; the design
    §4 walks it)."""
    units: dict[tuple[str, str], str] = {}
    for channel in descriptor["channels"]:
        for quantity in channel["quantities"]:
            units[(str(channel["id"]), str(quantity))] = "count"
    return units


def test_the_real_consumer_accepts_with_every_finding_surfaced() -> None:
    """A10's green half — the sweep's first conformance claim against a
    shipped plugin's public bytes, executable: the structural
    acceptance rule over the vendored descriptor ACCEPTS — 6 channels,
    6 traces within the 16-id ceiling, the optional trigger BOUND (the
    plugin declares all five actions, so every slot binds live), one
    y-axis, ``units == ["count"]`` — the honest raw-counts face, not
    smoothed to volts."""
    reference = load_document(REFERENCE)
    descriptor = load_document(PARKVIEW_FIXTURE)
    verdict, findings = _acceptance(
        reference, descriptor, _parkview_trace_units(descriptor)
    )
    assert verdict == "accepts", (verdict, findings)
    assert findings["n_channels"] == 6, findings
    assert findings["n_traces"] == 6, findings
    assert findings["slot:trigger"] == "bound", findings
    assert findings["units"] == ["count"], findings


def test_a_profile_flip_selects_nothing() -> None:
    """A10 kill arm 1: the descriptor's profile flipped to one the
    family holds no class reference for — no reference selects (the
    family's answer to an unheld profile is ``None``, the honest
    fail-open signal, not a nearest-neighbour match). The design's P2
    flipped to the oscilloscope on the L11 base where the scope was
    the unwritten slot; on this base the scope HAS its reference (and
    the scope-identity arm above pins the refusal that pairing
    derives), so the flip target rotates with the sweep to the
    unwritten slot — embedded_controller, the L18 exemplar."""
    from benchweave.presentation.classref import select_references

    descriptor = load_document(PARKVIEW_FIXTURE)
    descriptor["profiles"] = ["otdp.embedded_controller/1.0.0"]
    assert select_references(corpus_root(), descriptor) is None
    reference = load_document(REFERENCE)
    verdict, _findings = _acceptance(
        reference, descriptor, _parkview_trace_units(descriptor)
    )
    assert verdict == "no reference selected"


def test_a_triggerless_mutant_still_accepts() -> None:
    """A10 kill arm 2, the negative-direction proof: the optional
    ``trigger`` removed from the descriptor's actions — acceptance is
    trigger-independent (the ``when_declared`` slot reports UNBOUND,
    a ghost on the page, and every required slot still binds). A
    reference that refused a trigger-less daq would falsify the
    ``when_declared`` seam; this arm pins that it does not."""
    reference = load_document(REFERENCE)
    descriptor = load_document(PARKVIEW_FIXTURE)
    descriptor["actions"] = {
        key: value
        for key, value in descriptor["actions"].items()
        if key != "otdp.daq.trigger/1.0.0"
    }
    verdict, findings = _acceptance(
        reference, descriptor, _parkview_trace_units(descriptor)
    )
    assert verdict == "accepts", (verdict, findings)
    assert findings["slot:trigger"] == "unbound", findings
    assert findings["n_traces"] == 6, findings


def test_a_three_unit_mutant_hits_the_honest_refusal() -> None:
    """A10 kill arm 3: a mutant whose derived trace set carries three
    distinct units hits §E.2.3's honest refusal — the plot draws no
    traces and renders a visible refusal naming the condition; no
    silent conflation onto two axes. The heterogeneous daq's boundary
    is already contracted (the design §5's widening answer: nothing);
    the per-unit plot splitting a 3-unit daq would deserve is a named
    deferral with its reopen trigger, not this slice's motion."""
    reference = load_document(REFERENCE)
    descriptor = load_document(PARKVIEW_FIXTURE)
    units = _parkview_trace_units(descriptor)
    for index, key in enumerate(sorted(units)):
        units[key] = ("count", "volt", "ampere")[index % 3]
    verdict, findings = _acceptance(reference, descriptor, units)
    assert verdict.startswith("y-axis refusal"), verdict
    assert findings["units"] == ["ampere", "count", "volt"], findings


def test_the_vendored_fixture_names_its_source() -> None:
    """RC-L17-4's regenerable-check half: the fixture is a byte-copy of
    a public repository's public plugin descriptor at a pinned commit
    (named at ``PARKVIEW_FIXTURE`` above); the descriptor's own bytes
    carry the plugin id this file's docstring and the design record
    name — public provenance, cited as provenance, never claimed as
    evidence of anything but the plugin's own shape."""
    descriptor = load_document(PARKVIEW_FIXTURE)
    assert descriptor["id"] == "community.benchweave-adc.adc-6ch-12bit"
    assert descriptor["otdp_version"] == "0.2.2"
    assert sorted(descriptor["actions"]) == [
        "otdp.daq.abort/1.0.0",
        "otdp.daq.arm/1.0.0",
        "otdp.daq.configure/1.0.0",
        "otdp.daq.fetch/1.0.0",
        "otdp.daq.trigger/1.0.0",
    ]


# --- the pattern-library capture page --------------------------------------------


def test_one_waveform_plot_with_all_six_channel_traces() -> None:
    """One engineering plot (the layout block's traces section); the
    trace set is one per (channel, declared quantity) of the derived
    six-channel fixture — 6 x 1 computed from the corpus pair, never
    literals; every trace label names its channel label and quantity,
    both corpus strings. The composition is authored to the mockup's
    own shape (the real consumer's channel count; its identity
    nowhere)."""
    page = classref.render_daq_capture_page()
    figures = re.findall(r'class="bw-plot[ "]', page)
    assert len(figures) == 1
    reference = load_document(REFERENCE)
    fixture = _derived_six_channel_fixture()
    expected_traces = 0
    for channel in _analogue_channels(reference, fixture):
        for quantity in channel["quantities"]:
            expected_traces += 1
            assert f"{channel['label']} · {quantity}" in page, (
                channel["id"],
                quantity,
            )
    assert expected_traces == 6


def test_the_run_buttons_resolve_over_declared_actions() -> None:
    """The run panel's buttons are one per DECLARED run action of the
    derived fixture (the capture layout's run children resolved against
    the descriptor's action set — 3 on this fixture: the arm staging
    control plus the abort and trigger buttons): the L2 arm staging
    control plus the two L1 buttons. Labels are fixture choices (D2);
    counts derive."""
    page = classref.render_daq_capture_page()
    reference = load_document(REFERENCE)
    fixture = _derived_six_channel_fixture()
    counters = _structural_counters(reference, fixture)
    buttons = re.findall(r'<button[^>]*class="[^"]*bw-button', page)
    assert len(buttons) == counters["n_run_actions"], (
        len(buttons),
        counters["n_run_actions"],
    )
    # the staging control is the L2 arm face: a numeric input beside the
    # button, never a confirm subtree (the D7 forbid)
    assert "bw-numeric" in page
    assert "bw-confirm" not in page


def test_the_page_sections_mirror_the_reference_layout_block() -> None:
    """The composition's sections carry the layout block's own surfaces
    and spans (data-bw-span): the capture page is the analyser/scope
    capture geometry — plot recessed and dominant (span 12), the run
    panel raised below (span 12). An edit to the reference's layout
    block reddens the composition."""
    page = classref.render_daq_capture_page()
    reference = load_document(REFERENCE)
    layout = next(
        lp for lp in reference["layouts"] if lp["page_id"] == "capture"
    )
    for section in layout["sections"]:
        pattern = re.compile(
            rf'data-bw-section-id="{section["id"]}"[^>]*'
            rf'data-surface="{section["surface"]}"[^>]*'
            rf'data-bw-span="{section["span"]}"'
        )
        assert pattern.search(page), section["id"]


def test_the_page_composes_only_e1_partials() -> None:
    """Host composition of §E.1 partials only — no renderer change, no
    new contract rows; the banner leads (§E.1 placement), and no
    control surface derives beyond the ladder's: acquisition settings
    are cannot_derive (the settings surface is preset-mediated at
    birth) so no rotary/composed settings face is fabricated, and the
    capture page carries NO data table and NO reading tile — a table
    of streamed samples is not a surface this class presents, and
    waveform variables carry no scalar-extraction rule (the
    streaming-latest monitor strip is a named deferral)."""
    page = classref.render_daq_capture_page()
    assert "bw-mode-banner" in page
    banner = page.find("bw-mode-banner")
    plot = page.find('class="bw-plot')
    assert -1 < banner < plot
    assert "bw-plot" in page
    assert "bw-button" in page
    assert "bw-alert-bubble" in page
    assert "bw-rotary" not in page  # acquisition-settings is cannot_derive
    assert "bw-confirm" not in page  # D7: abort is one ungated action
    assert "bw-data-table" not in page
    assert "bw-reading" not in page


def test_the_partial_capture_alert_renders_the_mockup_wording() -> None:
    """The alert's title and condition wording trace to the mockup (the
    spec) — the class's own condition (buffer overflow, the partial
    dataset retained); the device-specific suffix stays mockup-side."""
    page = classref.render_daq_capture_page()
    assert "Buffer overflow" in page
    assert "Acquisition truncated — partial dataset retained" in page


def test_the_class_page_census_entry_is_registered() -> None:
    """The page rides the PATTERNS census: kind class-page on the
    class-daq page (the daq's own page slug — the generic capture name
    ``class-waveform`` is the scope's), row-keyed to the family's daq
    reference, fixture the capture page."""
    entry = next(e for e in patterns.PATTERNS if e.page == "class-daq")
    assert entry.kind == "class-page"
    assert entry.row_id == "plugin-ui-class-reference::class-daq"
    assert entry.fixture_id == "capture"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_class_page_exports_in_both_themes(tmp_path: Path, theme: str) -> None:
    patterns.export(tmp_path)
    path = tmp_path / "patterns" / theme / "class-daq.html"
    assert path.is_file(), path
    html = path.read_text(encoding="utf-8")
    assert "data-bw-pattern-library" in html
    assert 'data-bw-pattern-page="class-daq"' in html
    assert "Reference channel 1 · voltage" in html
