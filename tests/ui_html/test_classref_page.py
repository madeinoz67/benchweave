"""The class-reference capture page (Landing 3, gateway issues #462 rows
1-2): the pattern-library page composes the reference-derived capture
composition from the E.1 partials — no renderer change — and its
structure is re-derived from the committed corpus files so the page
cannot drift from the reference/descriptor pair without redding.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from benchweave_ui_html import classref, patterns

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "standards/plugin-ui-class-reference/0.1.0/class-logic_analyser.json"
DESCRIPTOR = REPO_ROOT / "standards/otdp/0.2.3/examples/class-logic_analyser.json"
VECTORS = REPO_ROOT / "standards/otdp/0.2.3/examples/class-action-vectors.json"
CATALOG = REPO_ROOT / "standards/otdp/0.2.3/device-profile-catalog.json"


def _load(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _declared_lanes() -> list[dict[str, Any]]:
    """The descriptor's digital_input channels, declaration order."""
    return [
        channel
        for channel in _load(DESCRIPTOR)["channels"]
        if channel["role"] == "digital_input"
    ]


def _vector_maps() -> dict[str, dict[str, str]]:
    """The decode_annotated channel maps in the descriptor's vectors — the
    resolution evidence for decoder lanes."""
    maps: dict[str, dict[str, str]] = {}
    for vector in _load(VECTORS)["vectors"]:
        block = vector["request"]["arguments"]["input"]
        decoder_id = block.get("decoder")
        channel_map = block.get("channel_map")
        if decoder_id and channel_map:
            maps[decoder_id] = channel_map
    return maps


def test_lane_structure_is_derived_from_the_descriptor() -> None:
    """Lane identity is declared position: the descriptor's digital_input
    channels in declaration order are the channel lanes, at the indices
    their declaration order assigns."""
    composed = classref.capture_lanes()
    declared = _declared_lanes()
    channel_lanes = [lane for lane in composed.lanes if lane.spec.kind == "channel"]
    assert [lane.spec.index for lane in channel_lanes] == list(range(len(declared)))
    assert [lane.spec.label for lane in channel_lanes] == [c["label"] for c in declared]


def test_group_label_and_radix_instantiate_the_reference_pattern() -> None:
    """The group label instantiates the reference's D{first}-D{last}
    pattern over 1-based positional numbers (DECIMAL labels always; the
    radix governs the rendered values, never the label); members are the
    declared channel ids, first declared member the LSB."""
    composed = classref.capture_lanes()
    plot = next(p["plot"] for p in _load(REFERENCE)["pages"] if p["id"] == "capture")
    assert plot["group_label_pattern"] == "D{first}-D{last}"
    declared = _declared_lanes()
    size = plot["group_size"]
    n_lanes = len(declared)
    n_groups = n_lanes // size + (1 if n_lanes % size >= 2 else 0)
    groups = [lane for lane in composed.lanes if lane.spec.kind == "group"]
    assert len(groups) == n_groups == 1
    group = groups[0]
    assert group.spec.label == "D1-D2"
    assert group.spec.radix == plot["group_radix"] == "hex"
    assert group.spec.members == tuple(c["id"] for c in declared)


def test_decoder_lanes_resolve_through_the_descriptor_vectors() -> None:
    """One decoder lane per descriptor-pinned decoder whose line roles
    resolve onto declared channels; the resolution evidence is the
    descriptor's own pinned vectors. onewire_link pins no resolving
    vector, so it renders no lane."""
    composed = classref.capture_lanes()
    maps = _vector_maps()
    assert maps == {
        "i2c": {"scl": "ch1", "sda": "ch2"},
        "spi": {"clk": "ch1", "cs": "ch2"},
        "uart": {"rx": "ch1"},
    }
    decoders = [lane for lane in composed.lanes if lane.spec.kind == "decoder"]
    assert len(decoders) == len(maps) == 3
    assert [lane.spec.label for lane in decoders] == [
        "i2c · scl=ch1 sda=ch2",
        "spi · clk=ch1 cs=ch2",
        "uart · rx=ch1",
    ]
    declared_ids = {c["id"] for c in _declared_lanes()}
    for lane in decoders:
        decoder_id, mapping = lane.spec.label.split(" · ")
        assert decoder_id in {d["id"] for d in _load(DESCRIPTOR)["decoders"]}
        for token in mapping.replace("=", " ").split():
            assert token in declared_ids or token in {"scl", "sda", "clk", "cs", "rx"}


# --- the page composition -------------------------------------------------------


def test_the_run_section_follows_the_controls_plan() -> None:
    """arm = staging (the action schema's remaining required numeric,
    max_duration_ms); abort and trigger are L1 buttons; abort renders as
    ONE action — never inside a confirm subtree (the D7 forbid
    confirm-wrapped-run-action).

    The bounds arm re-derives BOTH bound renderings from the catalog
    bytes: the rendered minimum string equals the schema minimum, and the
    rendered maximum equals the schema maximum — a declared schema bound
    renders its value, an absent one renders the empty attribute, never
    an invented bound (A02).

    What the guard does NOT catch (G4): drift in the disclosed fixture
    choices — the decoder event timings, cursor/trigger positions, state
    sequences, and the 24-sample/12-column fixture scale — none of which
    the corpus carries an authority for. The arm pins only the strings
    the corpus itself carries."""
    page = classref.render_capture_page()
    vectors = _load(VECTORS)["vectors"]
    schema = _load(CATALOG)["actions"]["otdp.logic_analyser.arm/1.0.0"]["input_schema"]
    remaining = [
        n for n in schema["required"]
        if n not in ("configuration_id", "acquisition_id")
    ]
    assert remaining == ["max_duration_ms"]
    field = schema["properties"]["max_duration_ms"]
    # The bounds arm: the page equals the catalog bytes, both directions.
    assert f'min="{field["minimum"]}"' in page
    if "maximum" in field:
        assert f'max="{field["maximum"]}"' in page
        assert 'max=""' not in page
    else:
        assert 'max=""' in page  # the absent bound, disclosed
    # The adversary's uncovered set, cheaply pinned: the arm example
    # value, the configure rate and the staged-config identity — each
    # re-derived from the corpus bytes.
    arm_vector = next(v for v in vectors if v["id"] == "logic_analyser-arm")
    arm_value = arm_vector["request"]["arguments"]["input"]["max_duration_ms"]
    assert f'value="{arm_value}"' in page
    configure_vector = next(v for v in vectors if v["id"] == "logic_analyser-configure")
    rate = configure_vector["request"]["arguments"]["input"]["sample_rate_hz"]
    assert classref.capture_lanes().rate_suffix == f"at {rate / 1e6:g} MHz"
    assert "cfg-1" in page  # the vectors' canonical configuration_id
    assert "Arm acquisition" in page
    assert "Abort acquisition" in page
    assert "Force trigger" in page
    assert "bw-confirm" not in page


def test_every_structural_string_traces_to_the_corpus() -> None:
    """D2 render discipline: the page's structural strings appear in the
    committed corpus files; the page authors no data the corpus does not
    carry (presentation timing and state sequences are disclosed fixture
    choices in the fixtures.py sense — corpus-shaped, fixture-documented)."""
    page = classref.render_capture_page()
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in (REFERENCE, DESCRIPTOR, VECTORS))
    for token in (
        "Reference channel 1",
        "Reference channel 2",
        "Address write: 50",
        "Data write: 12",
        "CS# was deasserted during this data word!",
        "55",
        "AA",
        "FF",
        "3A",
        "A8",
    ):
        assert token in corpus, token
        assert token in page, token
    # The group label is the DERIVED instantiation of the reference's
    # pattern (a structural string per design record §3.5): the corpus arm
    # asserts the pattern; the page arm the instantiation.
    assert "D{first}-D{last}" in corpus
    assert "D1-D2" in page
    # Decoder labels are composed: each part (decoder id, line, channel id)
    # traces to the corpus, the display form is a documented fixture choice.
    for label in ("i2c · scl=ch1 sda=ch2", "spi · clk=ch1 cs=ch2", "uart · rx=ch1"):
        assert label in page, label
        for part in label.replace(" · ", " ").replace("=", " ").split():
            assert part in corpus, part


def test_the_mode_banner_leads_the_page() -> None:
    """The placement rule: the mode banner is the page's first component
    (the workbench composition's own precedent)."""
    page = classref.render_capture_page()
    banner = page.find("bw-mode-banner")
    lanes = page.find("bw-lane")
    assert -1 < banner < lanes


def test_the_page_composes_only_e1_partials() -> None:
    """The composition rides the §E.1 partials (host composition — the
    record's §2.6 rule): banner, lanes capture, staged numeric, buttons."""
    page = classref.render_capture_page()
    assert "bw-mode-banner" in page
    assert "bw-lane" in page
    assert "bw-numeric" in page
    assert "<button" in page


# --- the export integration -----------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_class_page_exports_in_both_themes(tmp_path: Path, theme: str) -> None:
    patterns.export(tmp_path)
    path = tmp_path / "patterns" / theme / "class-capture.html"
    assert path.is_file(), path
    html = path.read_text(encoding="utf-8")
    assert "data-bw-pattern-library" in html
    assert 'data-bw-pattern-page="class-capture"' in html
    assert "Reference channel 1" in html
    assert "D1-D2" in html


def test_the_class_page_census_entry_is_registered() -> None:
    """The page rides the PATTERNS census: kind class-page on the
    class-capture page, row-keyed to the family."""
    entry = next(e for e in patterns.PATTERNS if e.page == "class-capture")
    assert entry.kind == "class-page"
    assert entry.row_id == "plugin-ui-class-reference::class-logic_analyser"
    assert entry.fixture_id == "capture"
