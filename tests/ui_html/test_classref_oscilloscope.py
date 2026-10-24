"""The oscilloscope class reference (L13 of the class sweep; design
record ``.claude/deep-review/2026-10-19-classref-l13-oscilloscope-design.md``):
the mockup-consistency arm (A3) and the pattern-library capture-page
composition with its drift guard.

A3, fourth class of the sweep — the first waveform-shaped one. The
mockup (``docs/internal/ui-styleguide-mockups/class-oscilloscope.html``)
is authored WITH the reference (the dmm convention's second instance,
with the §E.1 hooks and the placement contract from birth); the
reference is the data; this test is the bridge, keyed on the shared
census instrument (``tests/ui_html/classref_census.py``) under the L13
extension: the capture classes' hook family set (``bw-plot``,
``bw-button``, ``bw-alert-bubble``), their container map (the capture
region, the run panel) and the idiom-surface classes (the trigger marker
and cursor pair — non-contract idioms that must carry NO ``bw-`` hook).

Like dmm there is NO derived fixture: the mockup is authored to the
committed OTDP class example's own shape (2 analogue channels x 1
declared quantity = 2 traces; the example declares all five actions =
3 run buttons), so the census resolves over the committed example
directly. The kill is two-directional by construction: a mockup edit
that changes a hook count reds against the resolved expectation, and a
reference edit that changes the derivation (a count expression, the plot
binding, the channels slot) reds against the mockup's counts. A mockup
edit that does NOT redden the test is the instrument failing — report,
never a quiet pass (the record's A3 wording).

The placement contract rides the shared census from birth: every hook on
its §E.1 root, container-scoped hooks inside their containers, the
count-conserving move reds while counts conserve, and the idiom surfaces
carry no hook at all (a non-contract idiom must never present as a
contract component).

The expansion side (derive-ui/verify-ui censuses) is the batched SDK
widening's work and rides that train; what this file pins is the corpus
pair's structure — the reference document, its schema admission, and the
composition the host renders from it.
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
    validate_reference_document,
)
from benchweave.vendoring import corpus_root

REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY_DIR = REPO_ROOT / "standards/plugin-ui-class-reference/0.4.0"
REFERENCE = FAMILY_DIR / "class-oscilloscope.json"
DESCRIPTOR = REPO_ROOT / "standards/otdp/0.2.4/examples/class-oscilloscope.json"
MOCKUP = REPO_ROOT / "docs/internal/ui-styleguide-mockups/class-oscilloscope.html"

#: The capture classes' hook families (the L13 census extension): the
#: run panel's ``bw-button`` joins the plot and alert hooks the readings
#: classes already carry. The ``bw-reading``/``bw-data-table`` families
#: are the readings classes' own — the scope page presents neither a
#: reading tile nor a table.
OSCILLOSCOPE_HOOKS: tuple[str, ...] = ("bw-plot", "bw-button", "bw-alert-bubble")

#: The placement contract for this mockup: each container-scoped hook
#: sits in its mockup container (the capture region, the run panel).
OSCILLOSCOPE_CONTAINERS: dict[str, str] = {
    "bw-plot": "traces",
    "bw-button": "run",
}

#: The idiom surfaces (the design's §2 extension): non-contract markers
#: painted over host-knowledge — the trigger marker (line + readout chip)
#: and the cursor pair with its Δ readout. They carry NO ``bw-`` hook.
OSCILLOSCOPE_IDIOMS: frozenset[str] = frozenset({"trigger-marker", "cursor-pair"})

#: component name -> the §E.1 hook root the mockup carries for it.
COMPONENT_HOOKS: dict[str, str] = {
    "engineering-plot": "bw-plot",
    "button": "bw-button",
}


def _oscilloscope_census() -> dict[str, dict[str, int]]:
    return hook_census(MOCKUP, hooks=OSCILLOSCOPE_HOOKS)


def _analogue_channels(
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
    over the committed example (no derived fixture — the mockup is
    authored to the example's own shape)."""
    counters = _structural_counters(reference, descriptor)
    resolved: dict[str, int] = {}
    for name, row in reference["expect"]["components"].items():
        if row.get("per_page") == "capture":
            resolved[name] = resolve_count(str(row["count"]), counters)
    return resolved


def _scratch_with_plot(plot: dict[str, Any]) -> dict[str, Any]:
    """A scratch reference document carrying the given plot block: the
    committed dmm document with its (first) plot swapped — the A8 arm
    vehicle, scratch-only (never committed)."""
    document: dict[str, Any] = json.loads(
        (FAMILY_DIR / "class-dmm.json").read_text(encoding="utf-8")
    )
    for page in document["pages"]:
        if "plot" in page:
            page["plot"] = plot
    return document


# --- A3: the mockup-consistency arm ---------------------------------------------


def test_the_mockup_carries_the_contract_hooks_in_both_themes() -> None:
    """The hook pass (RC-L11-3), from birth (RC-L12-1, second
    authored-from-birth instance): both theme sections carry every hook
    family the census keys on — a hook absent from one theme is a
    composition break, not a style choice."""
    census = _oscilloscope_census()
    assert set(census) == {"light", "dark"}
    for theme, hooks in census.items():
        for hook in OSCILLOSCOPE_HOOKS:
            assert hooks[hook] >= 1, (theme, hook)


def test_mockup_hook_counts_equal_the_resolved_expectation() -> None:
    """A3, the load-bearing arm: per theme section, the mockup's hook
    counts EQUAL the reference's resolved expectation over the committed
    OTDP example (2 analogue channels x 1 declared quantity = 2 traces;
    the example declares all five actions = 3 run buttons) — the counts
    derived on BOTH sides, never literals on either.

    Kill direction 1: edit the mockup's count — the hook count diverges
    from the resolved expectation and this reds.
    Kill direction 2: edit the reference's derivation — a count
    expression, the plot binding, the channels slot's role — and the
    RESOLVED side diverges from the mockup and this reds."""
    reference = load_document(REFERENCE)
    fixture = load_document(DESCRIPTOR)
    resolved = _resolved_capture_expectation(reference, fixture)
    assert set(resolved) == {"engineering-plot", "button"}, resolved
    counters = _structural_counters(reference, fixture)
    # the example's own shape: 2 channels x 1 quantity, 3 declared run
    # actions — the numbers the mockup is authored to (the census keys
    # on them; a fixture change reds the composition, never this arm)
    assert counters["n_trace_variables"] == counters["n_analogue_channels"] * 1
    assert counters["n_run_actions"] >= 1
    census = _oscilloscope_census()
    for theme, hooks in census.items():
        for name, hook in COMPONENT_HOOKS.items():
            assert hooks[hook] == resolved[name], (theme, hook, resolved[name])


def test_every_hook_sits_on_its_contract_root_and_container() -> None:
    """The count-conserving-move kill and the idiom-surface kill (the
    design's §6 arm 3): every hook is on its §E.1 root element, the
    container-scoped hooks sit in their containers, and the idiom
    surfaces (trigger marker, cursor pair) carry NO ``bw-`` hook — a
    non-contract idiom must never present as a contract component. The
    count census alone is placement-blind: a hook moved
    count-conservingly into the wrong container reds HERE while the count
    arm stays green, and a ``bw-`` class reverse-planted on a marker chip
    reds here."""
    parser = HookCensus(
        hooks=OSCILLOSCOPE_HOOKS,
        containers=OSCILLOSCOPE_CONTAINERS,
        idiom_classes=OSCILLOSCOPE_IDIOMS,
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


def test_both_themes_carry_the_identical_hook_census() -> None:
    """One composition, two themes: the hook census is theme-invariant."""
    census = _oscilloscope_census()
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
    census = _oscilloscope_census()
    for theme, hooks in census.items():
        assert hooks["bw-alert-bubble"] == 1, theme


def test_the_reference_selects_for_the_class_descriptor() -> None:
    """A4's green half, gateway-side: the oscilloscope class example's
    profile now selects a corpus reference (``select_references``
    returned None before the class existed — the pair banked RED at
    design time, design record §6 arm 6)."""
    from benchweave.presentation.classref import select_references

    selected = select_references(corpus_root(), load_document(DESCRIPTOR))
    assert selected is not None and len(selected) == 1
    assert selected[0]["profile_id"] == "otdp.oscilloscope/1.0.0"


# --- A6: the D2 census on the scope reference ------------------------------------


def test_the_reference_authors_structure_not_data() -> None:
    """D2, machine-checked: no numeric literal outside the structural set
    (plot indices, layout spans), and none of the fixture's own data
    strings (channel ids, channel labels, quantity names) appears in the
    reference — data arrives via the descriptor at expansion. What this
    guard does NOT catch: an invented qualitative string that is not one
    of the fixture's data strings cannot be machine-told from a
    structural title (that class of authoring error is review discipline,
    per the L11 record's A6 wording)."""
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

    allowed_numbers = {0, 12}  # plot_index 0; the grid span 12
    for value in walk(reference):
        # bools are schema flags (when_declared), not numeric literals —
        # bool subclasses int, so it is excluded explicitly
        assert (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value in allowed_numbers
        ), value
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


# --- A8: the waveform widening's own arms ---------------------------------------


def test_a_waveform_plot_template_validates() -> None:
    """The widening's positive arm (RED before the enum edit: the 0.3.0
    plot-kind enum admits only `digital_lanes` and `time_series`): a
    `waveform` plot carrying the mirrored conditional — `series`
    required, no group machinery — validates against the family
    schema."""
    document = _scratch_with_plot(
        {
            "kind": "waveform",
            "over_slot": "measure",
            "series": "numeric_variables",
        }
    )
    validate_reference_document(document, corpus=corpus_root())


def test_a_waveform_template_without_series_refuses() -> None:
    """The mirrored conditional's first half: `waveform` requires
    `series` (post-L12-settlement semantics). Pre-widening this arm is
    enum-covered (the kind itself refuses); post-widening the conditional
    is the refusing authority — the arm pins both."""
    document = _scratch_with_plot(
        {"kind": "waveform", "over_slot": "measure"}
    )
    with pytest.raises(ClassRefusal, match="classref_invalid_reference"):
        validate_reference_document(document, corpus=corpus_root())


def test_a_waveform_template_with_group_machinery_refuses() -> None:
    """The mirrored conditional's second half: `waveform` bans the lanes
    group machinery (`group_size`, `group_label_pattern`, `group_radix`),
    exactly as `time_series` does. Same dual-coverage note as above."""
    document = _scratch_with_plot(
        {
            "kind": "waveform",
            "over_slot": "measure",
            "series": "numeric_variables",
            "group_size": 8,
        }
    )
    with pytest.raises(ClassRefusal, match="classref_invalid_reference"):
        validate_reference_document(document, corpus=corpus_root())


def test_a_scratch_time_series_template_still_requires_series() -> None:
    """No-regression on the L12 settlement: a `time_series` template
    without `series` still refuses (the widened enum must not loosen the
    existing conditional)."""
    document = _scratch_with_plot({"kind": "time_series", "over_slot": "measure"})
    with pytest.raises(ClassRefusal, match="classref_invalid_reference"):
        validate_reference_document(document, corpus=corpus_root())


def test_every_committed_class_document_validates() -> None:
    """Every class reference in the 0.4.0 family passes the family
    schema — the oscilloscope document's own `waveform` plot included
    (a committed document failing is a kill; the mockup's A3 arms keep
    the document and mockup in step)."""
    documents = []
    for path in sorted(FAMILY_DIR.glob("class-*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        # a class document is the schema's own discriminator: a bound
        # profile_id (the same gate `_find_reference` walks — the glob
        # also matches class-reference.schema.json itself)
        if isinstance(document, dict) and "profile_id" in document:
            documents.append((path, document))
    names = {path.name for path, _ in documents}
    assert "class-oscilloscope.json" in names, names
    for _path, document in documents:
        validate_reference_document(document, corpus=corpus_root())


# --- the pattern-library capture page --------------------------------------------


def test_one_waveform_plot_with_both_channel_traces() -> None:
    """One engineering plot (the layout block's capture section); the
    trace set is one per (channel, declared quantity) of the OTDP
    example's analogue channels — 2 x 1 computed from the corpus pair,
    never literals; every trace label names its channel label and
    quantity, both corpus strings."""
    page = classref.render_oscilloscope_capture_page()
    figures = re.findall(r'class="bw-plot[ "]', page)
    assert len(figures) == 1
    fixture = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
    expected_traces = 0
    for channel in _analogue_channels(reference, fixture):
        for quantity in channel["quantities"]:
            expected_traces += 1
            assert f"{channel['label']} · {quantity}" in page, (
                channel["id"],
                quantity,
            )
    assert expected_traces >= 1


def test_the_run_buttons_resolve_over_declared_actions() -> None:
    """The run panel's buttons are one per DECLARED run action of the
    example (the capture layout's run children resolved against the
    descriptor's action set — 3 on this example, fewer on a trigger-less
    descriptor): the L2 arm staging control plus the L1 abort and
    trigger buttons. Labels are fixture choices (D2); counts derive."""
    page = classref.render_oscilloscope_capture_page()
    fixture = load_document(DESCRIPTOR)
    reference = load_document(REFERENCE)
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
    and spans (data-bw-span): the capture page is the analyser's capture
    geometry — plot recessed and dominant (span 12), the run panel raised
    below (span 12). An edit to the reference's layout block reddens the
    composition."""
    page = classref.render_oscilloscope_capture_page()
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
    new contract rows; the banner leads (§E.1 placement), and no control
    surface derives beyond the ladder's: acquisition settings are
    cannot_derive (the settings surface is preset-mediated at birth) so
    no rotary/composed settings face is fabricated, and the capture page
    carries NO data table — a table of waveform samples is not a surface
    this class presents (the reference's expect block declares none)."""
    page = classref.render_oscilloscope_capture_page()
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
    spec); the device-specific suffix stays mockup-side."""
    page = classref.render_oscilloscope_capture_page()
    assert "Partial capture" in page
    assert "Acquisition truncated" in page


def test_the_class_page_census_entry_is_registered() -> None:
    """The page rides the PATTERNS census: kind class-page on the
    class-waveform page, row-keyed to the family's oscilloscope
    reference, fixture the capture page."""
    entry = next(e for e in patterns.PATTERNS if e.page == "class-waveform")
    assert entry.kind == "class-page"
    assert entry.row_id == "plugin-ui-class-reference::class-oscilloscope"
    assert entry.fixture_id == "capture"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_class_page_exports_in_both_themes(tmp_path: Path, theme: str) -> None:
    patterns.export(tmp_path)
    path = tmp_path / "patterns" / theme / "class-waveform.html"
    assert path.is_file(), path
    html = path.read_text(encoding="utf-8")
    assert "data-bw-pattern-library" in html
    assert 'data-bw-pattern-page="class-waveform"' in html
    assert "Reference channel 1 · voltage" in html
