"""The class-reference family schemas are closed, local and versioned.

Landing 1 of the class-reference program (design record
``.claude/deep-review/2026-10-14-classref-logic-analyser-design.md``); the
L5 widening rides design record
``.claude/deep-review/2026-10-16-classref-l5-plugin-ui-0-4-0-design.md``.
The family's ACTIVE version ``plugin-ui-class-reference/0.4.0`` ships two
machine schemas and THREE class references — the founding
``class-logic_analyser.json`` (re-stamped, zero content change), the L11
``class-dc_psu.json`` (the first scalar/readings-shaped class; design record
``.claude/deep-review/2026-10-18-classref-l11-dc-psu-design.md``) and the
L12 ``class-dmm.json`` (the observation-pure class; design record
``.claude/deep-review/2026-10-19-classref-l12-dmm-design.md`` — the F4
settlement rides the same record: ``series`` is REQUIRED on ``time_series``
plots). The 0.1.0
and 0.2.0 predecessors stay digest-frozen — the retained-freeze arms below
assert them. Every schema rule carries a
valid and an invalid case; the reference-content tests pin the D2
structure-not-data discipline and the D12a extension-seam namespace at the
corpus level (the expansion-side A-rules are Landing 2).
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "standards/plugin-ui-class-reference/0.4.0"
REFERENCE = DIRECTORY / "class-logic_analyser.json"
REFERENCE_PSU = DIRECTORY / "class-dc_psu.json"
REFERENCE_DMM = DIRECTORY / "class-dmm.json"
CLASS_REF_ID = (
    "https://benchweave.dev/contracts/plugin-ui-class-reference"
    "/0.4.0/class-reference.schema.json"
)
LAYOUT_ID = (
    "https://benchweave.dev/contracts/plugin-ui-class-reference"
    "/0.4.0/layout.schema.json"
)
LAYOUT_REF = f"{LAYOUT_ID}#/$defs/layout_page"
# The plugin-ui manifest schema whose extensions seam carries the layout
# block (D12a): the namespace key must match its patternProperties grammar.
UI_MANIFEST = ROOT / "standards/plugin-ui/0.4.0/ui-manifest.schema.json"

# The class's actions per the OTDP 0.2.3 catalogue (the profile row the
# reference binds); the reference's action URNs must all exist there.
OTDP_CATALOG = ROOT / "standards/otdp/0.2.4/device-profile-catalog.json"


def schemas() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in ("class-reference", "layout"):
        path = DIRECTORY / f"{name}.schema.json"
        assert path.is_file(), f"Missing {name} schema"
        schema = json.loads(path.read_bytes())
        Draft202012Validator.check_schema(schema)
        result[name] = schema
    return result


def reference_validator() -> Draft202012Validator:
    documents = schemas()
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema))
        for schema in documents.values()
    )
    return Draft202012Validator(documents["class-reference"], registry=registry)


def layout_validator() -> Draft202012Validator:
    return Draft202012Validator(schemas()["layout"])


def minimal_layout_page() -> dict[str, Any]:
    return {
        "page_id": "capture",
        "sections": [
            {
                "id": "run",
                "surface": "raised",
                "children": [{"binding_id": "arm", "kind": "button"}],
            }
        ],
    }


def minimal_reference(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "contract_version": "0.4.0",
        "profile_id": "otdp.logic_analyser/1.0.0",
        "title": "Class reference",
        "targets": {"plugin_ui": ">=0.3.1"},
        "slots": {
            "lanes": {"kind": "channels", "where_role": "digital_input"},
            "arm": {
                "kind": "procedure",
                "action": "otdp.logic_analyser.arm/1.0.0",
            },
        },
        "pages": [
            {
                "id": "capture",
                "title": "Capture",
                "kind": "dataset",
                "binding_slots": ["lanes"],
            }
        ],
        "layouts": [minimal_layout_page()],
        "expect": {"components": {}, "controls": {}, "forbid": []},
        "cannot_derive": [],
    }
    document.update(overrides)
    return document


# --- the schemas themselves -----------------------------------------------------


def test_all_family_schemas_are_valid_and_versioned() -> None:
    for name, schema in schemas().items():
        expected = (
            "https://benchweave.dev/contracts/plugin-ui-class-reference"
            f"/0.4.0/{name}.schema.json"
        )
        assert schema["$id"] == expected


def test_minimal_reference_validates() -> None:
    assert reference_validator().is_valid(minimal_reference())


# --- class-reference.schema.json rules ------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "contract_version",
        "profile_id",
        "title",
        "targets",
        "slots",
        "pages",
        "expect",
        "cannot_derive",
    ],
)
def test_reference_rejects_missing_required_field(field: str) -> None:

    document = minimal_reference()
    del document[field]
    assert not reference_validator().is_valid(document)


def test_contract_version_is_pinned() -> None:
    assert not reference_validator().is_valid(
        minimal_reference(contract_version="0.1.0")
    )


@pytest.mark.parametrize(
    ("profile_id", "valid"),
    [
        ("otdp.logic_analyser/1.0.0", True),
        ("otdp.dc_psu/1.0.0", True),
        ("logic_analyser/1.0.0", False),
        ("otdp.logic-analyser/1.0.0", False),
        ("otdp.logic_analyser/1.0", False),
    ],
    ids=["class", "other-class", "no-prefix", "hyphen", "two-part-version"],
)
def test_profile_id_pattern(profile_id: str, valid: bool) -> None:
    assert (
        reference_validator().is_valid(minimal_reference(profile_id=profile_id))
        == valid
    )


@pytest.mark.parametrize(
    ("target", "valid"),
    [(">=0.3.1", True), (">0.3.1", True), ("0.3.1", False), ("latest", False), (">=zero", False)],
    ids=["range", "gt", "bare-invalid", "word", "non-numeric"],
)
def test_plugin_ui_target_pattern(target: str, valid: bool) -> None:
    document = minimal_reference(targets={"plugin_ui": target})
    assert reference_validator().is_valid(document) == valid


def test_slot_kinds_are_closed() -> None:
    document = minimal_reference(
        slots={
            "lanes": {"kind": "channels", "where_role": "digital_input"},
            "capture": {
                "kind": "dataset",
                "action": "otdp.logic_analyser.fetch/1.0.0",
                "schema_source": "output_measurement",
            },
            "configure": {
                "kind": "configuration",
                "action": "otdp.logic_analyser.configure/1.0.0",
                "schema_source": "input_schema",
            },
            "arm": {
                "kind": "procedure",
                "action": "otdp.logic_analyser.arm/1.0.0",
            },
            "vendor_actions": {"kind": "vendor_actions"},
        }
    )
    assert reference_validator().is_valid(document)
    document["slots"]["arm"]["kind"] = "envelope"
    assert not reference_validator().is_valid(document)


@pytest.mark.parametrize(
    "action",
    [
        "otdp.logic_analyser.arm/1.0.0",
        "otdp.logic_analyser.decode_annotated/1.0.0",
    ],
)
def test_action_urn_pattern_accepts_class_actions(action: str) -> None:
    document = minimal_reference(
        slots={"arm": {"kind": "procedure", "action": action}}
    )
    assert reference_validator().is_valid(document)


@pytest.mark.parametrize(
    "action",
    [
        "com.veridian-labs.auto-threshold/1.0.0",
        "otdp.logic_analyser.arm/1.0",
        "urn:otdp:action:logic_analyser.arm:1.0.0:input",
    ],
    ids=["vendor-urn", "short-version", "measurement-id"],
)
def test_action_urn_pattern_refuses_non_class_urns(action: str) -> None:
    document = minimal_reference(
        slots={"arm": {"kind": "procedure", "action": action}}
    )
    assert not reference_validator().is_valid(document)


def test_action_slot_requires_its_action() -> None:
    document = minimal_reference(
        slots={"arm": {"kind": "procedure"}}
    )
    assert not reference_validator().is_valid(document)


@pytest.mark.parametrize(
    ("overrides", "label"),
    [
        ({"kind": "dashboard"}, "page-kind"),
        ({"binding_slots": 42}, "binding-slots-type"),
        (
            {
                "binding_slots": ["lanes"],
                "plot": {"kind": "waveform", "over_slot": "lanes"},
            },
            "plot-kind",
        ),
        (
            {
                "binding_slots": ["lanes"],
                "plot": {
                    "kind": "digital_lanes",
                    "over_slot": "lanes",
                    "group_size": 16,
                },
            },
            "group-size",
        ),
        (
            {
                "binding_slots": ["lanes"],
                "plot": {
                    "kind": "digital_lanes",
                    "over_slot": "lanes",
                    "group_label_pattern": "Lane{first}-{last}",
                },
            },
            "group-label-pattern",
        ),
        (
            {
                "binding_slots": ["lanes"],
                "plot": {
                    "kind": "digital_lanes",
                    "over_slot": "lanes",
                    "group_radix": "octal",
                },
            },
            "group-radix",
        ),
    ],
    ids=[
        "page-kind",
        "binding-slots-type",
        "plot-kind",
        "group-size",
        "group-label-pattern",
        "group-radix",
    ],
)
def test_page_rules_refuse_malformed_pages(
    overrides: dict[str, Any], label: str
) -> None:
    document = minimal_reference()
    page: dict[str, Any] = {
        "id": "capture",
        "title": "Capture",
        "kind": "dataset",
        "binding_slots": ["lanes"],
    }
    page.update(overrides)
    document["pages"] = [page]
    assert not reference_validator().is_valid(document)


def test_vendor_features_is_boolean() -> None:
    document = minimal_reference()
    document["pages"].append(
        {
            "id": "device-features",
            "title": "Device features",
            "kind": "configuration",
            "binding_slots": ["vendor_actions"],
            "vendor_features": "yes",
        }
    )
    assert not reference_validator().is_valid(document)


def test_expect_controls_are_a_closed_enum() -> None:
    document = minimal_reference(
        expect={
            "components": {},
            "controls": {"otdp.logic_analyser.arm/1.0.0": "toggle"},
            "forbid": [],
        }
    )
    assert not reference_validator().is_valid(document)


@pytest.mark.parametrize(
    "components",
    [
        {"digital-lanes": {"count": True}},
        {"digital-lanes": {"count": "1", "attribute": "data-bw-lane-kind"}},
    ],
    ids=["count-boolean", "attribute-scalar"],
)
def test_component_expect_rules(components: dict[str, Any]) -> None:
    document = minimal_reference(expect={"components": components})
    assert not reference_validator().is_valid(document)


def test_forbid_items_are_strings() -> None:
    document = minimal_reference(
        expect={"components": {}, "controls": {}, "forbid": [{"wrap": True}]}
    )
    assert not reference_validator().is_valid(document)


def test_cannot_derive_rows_are_closed_world() -> None:
    row: dict[str, Any] = {
        "id": "thresholds",
        "aspect": "safe threshold_v range",
        "reason": "qualification is per bench",
        "author_action": "constrain the settings schema on the descriptor",
    }
    assert reference_validator().is_valid(
        minimal_reference(cannot_derive=[row])
    )
    missing = {key: value for key, value in row.items() if key != "author_action"}
    assert not reference_validator().is_valid(minimal_reference(cannot_derive=[missing]))
    extra = dict(row)
    extra["default"] = "[0, 5]"
    assert not reference_validator().is_valid(minimal_reference(cannot_derive=[extra]))


def test_reference_is_closed_world_against_authored_data() -> None:
    """The D2 trap: an author reaching for a data field must fail at the
    schema, not silently carry a value the expander cannot derive."""
    document = minimal_reference()
    document["threshold_v_range"] = [0, 5]
    assert not reference_validator().is_valid(document)


def test_the_vocabulary_has_no_data_bearing_fields() -> None:
    """D2 structural: no property anywhere in the reference vocabulary may
    carry a default, value, unit or numeric bound (JSON-Schema keywords that
    are part of the machinery itself are not property names here)."""
    forbidden = {
        "default",
        "value",
        "unit",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "step",
        "threshold",
    }
    schema = schemas()["class-reference"]

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for name in properties:
                    assert name not in forbidden, f"data-bearing field: {name}"
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)


# --- layouts (the cross-schema ref into the layout vocabulary) ------------------


def test_reference_layouts_ride_the_layout_vocabulary() -> None:
    assert reference_validator().is_valid(minimal_reference())


def test_reference_layouts_refuse_a_deep_block() -> None:
    layout_page = minimal_layout_page()
    layout_page["sections"][0]["children"] = [
        {
            "id": "outer",
            "surface": "raised",
            "children": [
                {
                    "id": "middle",
                    "surface": "raised",
                    "children": [
                        {
                            "id": "inner",
                            "surface": "raised",
                            "children": [
                                {
                                    "id": "beyond",
                                    "surface": "raised",
                                    "children": [
                                        {"binding_id": "arm", "kind": "button"}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    document = minimal_reference(layouts=[layout_page])
    assert not reference_validator().is_valid(document)


# --- the committed reference ----------------------------------------------------


def test_the_committed_reference_validates() -> None:
    assert REFERENCE.is_file(), f"Missing {REFERENCE.name}"
    document = json.loads(REFERENCE.read_bytes())
    assert document["profile_id"] == "otdp.logic_analyser/1.0.0"
    assert reference_validator().is_valid(document)


def test_the_reference_binds_the_catalogued_class_actions() -> None:
    """Every action the reference names must exist in the OTDP catalogue's
    logic_analyser row, and every required action must be bound."""
    document = json.loads(REFERENCE.read_bytes())
    catalog = json.loads(OTDP_CATALOG.read_bytes())
    profile = next(
        p
        for p in catalog["profiles"]
        if p["id"] == document["profile_id"]
    )
    bound = {
        slot["action"]
        for slot in document["slots"].values()
        if "action" in slot
    }
    assert bound <= set(catalog["actions"])
    assert set(profile["required_actions"]) <= bound


def test_reference_numbers_are_structural_only() -> None:
    """D2: the only numeric literals in the reference are the structural
    instantiations - group_size 8, the capture-page plot_index 0, and the
    layout grid spans (12, the vocabulary's own structural bound). The
    census covers string-encoded numerics too (lane 1 F4): pure-numeric
    strings carry only the count-arity literal "1" from the closed
    expression vocabulary; version strings like 0.3.1 and the URNs are not
    pure numerics and never were."""
    document = json.loads(REFERENCE.read_bytes())
    numbers: list[int | float] = []
    numeric_strings: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            numbers.append(node)
        elif isinstance(node, str):
            try:
                float(node)
            except ValueError:
                return
            numeric_strings.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    assert set(numbers) == {0, 8, 12}
    assert set(numeric_strings) == {"1"}


def test_reference_layouts_carry_no_text_nodes() -> None:
    """D2: text nodes are author capability; the reference authors none."""
    document = json.loads(REFERENCE.read_bytes())

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "body" in node:
                pytest.fail("reference layout carries a text node")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for layout_page in document.get("layouts", []):
        walk(layout_page)


def test_layout_extension_namespace_matches_the_plugin_ui_seam() -> None:
    """D12a: the layout block rides the plugin-ui 0.4.0 extensions seam; the
    namespace key must match the manifest schema's patternProperties."""
    schema = json.loads(UI_MANIFEST.read_bytes())
    patterns = [
        pattern.replace("\\", "")
        for pattern in schema["properties"]["extensions"]["patternProperties"]
    ]
    namespace = "plugin-ui-class-reference:layout"
    assert any(re.fullmatch(pattern, namespace) for pattern in patterns)


def test_controls_levels_match_the_class_ladder() -> None:
    """D14 class slice: configure is preset-mediated, arm is the staging
    pair, abort and trigger are bare buttons, decode's invocation carries a
    declared deviation; fetch has no control (the L4 dataset binding)."""
    document = json.loads(REFERENCE.read_bytes())
    controls = document["expect"]["controls"]
    assert controls == {
        "otdp.logic_analyser.configure/1.0.0": "preset",
        "otdp.logic_analyser.arm/1.0.0": "staging",
        "otdp.logic_analyser.abort/1.0.0": "button",
        "otdp.logic_analyser.trigger/1.0.0": "button",
        "otdp.logic_analyser.decode/1.0.0": "deviation",
    }


# --- layout.schema.json rules ---------------------------------------------------


def test_minimal_layout_document_validates() -> None:
    layout = {
        "contract_version": "0.4.0",
        "pages": [minimal_layout_page()],
    }
    assert layout_validator().is_valid(layout)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc.update(contract_version="0.2.0"),
        lambda doc: doc.update(pages=[]),
        lambda doc: doc["pages"][0].pop("page_id"),
        lambda doc: doc["pages"][0].update(sections=[]),
    ],
    ids=["version", "empty-pages", "missing-page-id", "empty-sections"],
)
def test_layout_document_rules_refuse(mutate: Any) -> None:
    layout: dict[str, Any] = {
        "contract_version": "0.4.0",
        "pages": [minimal_layout_page()],
    }
    mutate(layout)
    assert not layout_validator().is_valid(layout)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda section: section.update(surface="floating"),
        lambda section: section.update(span=13),
        lambda section: section.update(span=0),
    ],
    ids=["surface", "span-over", "span-under"],
)
def test_section_rules_refuse(mutate: Any) -> None:
    layout: dict[str, Any] = {
        "contract_version": "0.4.0",
        "pages": [minimal_layout_page()],
    }
    mutate(layout["pages"][0]["sections"][0])
    assert not layout_validator().is_valid(layout)


def test_control_kinds_are_closed() -> None:
    layout: dict[str, Any] = {
        "contract_version": "0.4.0",
        "pages": [
            {
                "page_id": "capture",
                "sections": [
                    {
                        "id": "run",
                        "surface": "raised",
                        "children": [
                            {"binding_id": "arm", "kind": "slider"},
                        ],
                    }
                ],
            }
        ],
    }
    assert not layout_validator().is_valid(layout)


def test_text_body_is_bounded() -> None:
    body = "x" * 512
    layout: dict[str, Any] = {
        "contract_version": "0.4.0",
        "pages": [
            {
                "page_id": "capture",
                "sections": [
                    {"id": "note", "surface": "raised", "children": [{"body": body}]}
                ],
            }
        ],
    }
    assert layout_validator().is_valid(layout)
    layout["pages"][0]["sections"][0]["children"][0]["body"] = "x" * 513
    assert not layout_validator().is_valid(layout)


@pytest.mark.parametrize(
    "node",
    [
        {"binding_id": "capture", "kind": "gauge"},
        {"plot_index": "0"},
        {"binding_id": "!bad", "kind": "button"},
        {"binding_id": "arm", "kind": "button", "style": "color:red"},
    ],
    ids=["unknown-kind", "plot-index-string", "binding-id-grammar", "closed-world"],
)
def test_layout_nodes_are_closed_world(node: dict[str, Any]) -> None:
    layout: dict[str, Any] = {
        "contract_version": "0.4.0",
        "pages": [
            {
                "page_id": "capture",
                "sections": [
                    {"id": "s", "surface": "raised", "children": [node]}
                ],
            }
        ],
    }
    assert not layout_validator().is_valid(layout)


def test_depth_is_bounded_at_three() -> None:
    def node(section_id: str, children: list[dict[str, Any]]) -> dict[str, Any]:
        return {"id": section_id, "surface": "raised", "children": children}

    leaf = node("inner", [{"binding_id": "arm", "kind": "button"}])
    three_deep: dict[str, Any] = {
        "contract_version": "0.4.0",
        "pages": [
            {"page_id": "capture", "sections": [node("outer", [node("middle", [leaf])])]}
        ],
    }
    assert layout_validator().is_valid(three_deep)
    beyond = node("inner", [node("beyond", [{"body": "x"}])])
    four_deep: dict[str, Any] = {
        "contract_version": "0.4.0",
        "pages": [
            {"page_id": "capture", "sections": [node("outer", [node("middle", [beyond])])]}
        ],
    }
    assert not layout_validator().is_valid(four_deep)


# --- the admission fold: adversary lanes 1 and 2 (RED-first batch) ---------------


def test_slot_variables_key_is_removed() -> None:
    """Lane 1 F1 probe 1 (D2 smuggling): the per-slot variable template was
    dropped at admission - nothing authored it and lane variables derive
    from the descriptor. A slot carrying a free-form variables object (the
    adversary's {default, unit, maximum} probe) must refuse."""
    document = minimal_reference(
        slots={
            "arm": {
                "kind": "procedure",
                "action": "otdp.logic_analyser.arm/1.0.0",
                "variables": {"default": 1.8, "unit": "V", "maximum": 5.0},
            }
        }
    )
    assert not reference_validator().is_valid(document)


def test_component_attribute_is_a_closed_selector_map() -> None:
    """Lane 1 F1 probe 2 (D2 smuggling): attribute maps count expressions
    onto the closed lane-kind selectors only - a data-bearing key such as
    the adversary's voltage_limit:{maximum:3.3} must refuse."""
    document = minimal_reference(
        expect={
            "components": {
                "digital-lanes": {
                    "count": "1",
                    "attribute": {"voltage_limit": {"maximum": 3.3}},
                }
            }
        }
    )
    assert not reference_validator().is_valid(document)


def test_attribute_selectors_are_the_lane_kinds() -> None:
    """The F1 closure keeps the designed vocabulary: the three lane-kind
    selectors with count-expression values still admit."""
    document = minimal_reference(
        expect={
            "components": {
                "digital-lanes": {
                    "count": "1",
                    "attribute": {"data-bw-lane-kind=channel": "{n_lanes}"},
                }
            }
        }
    )
    assert reference_validator().is_valid(document)


@pytest.mark.parametrize(
    "target",
    [">=0.3.1,garbage!!", ">=0.3.1 ", "=0.3.1"],
    ids=["trailing-garbage", "trailing-space", "bare-equals"],
)
def test_target_grammar_is_exact(target: str) -> None:
    """Lane 1 F8: the target grammar is anchored - the prefix-only pattern
    admitted arbitrary trailing bytes."""
    document = minimal_reference(targets={"plugin_ui": target})
    assert not reference_validator().is_valid(document), target


def test_seventeen_layout_pages_refuse_both_ways() -> None:
    """Lane 1 F7: the seam block's page cap (16) is the binding one - the
    reference-side layouts bound must match it, so seventeen pages refuse
    as a standalone block AND as reference layouts."""
    pages = [minimal_layout_page() for _ in range(17)]
    assert not layout_validator().is_valid(
        {"contract_version": "0.4.0", "pages": pages}
    )
    assert not reference_validator().is_valid(minimal_reference(layouts=pages))


def test_sixteen_layout_pages_admit_both_ways() -> None:
    """The F7 alignment is a tightening to the seam cap, not a new ceiling:
    sixteen pages admit on both writers."""
    pages = [minimal_layout_page() for _ in range(16)]
    assert layout_validator().is_valid(
        {"contract_version": "0.4.0", "pages": pages}
    )
    assert reference_validator().is_valid(minimal_reference(layouts=pages))


def test_the_reference_declares_the_intermediation_forbid() -> None:
    """Lane 1 F2 (D7): the forbid arm extends past bw-confirm ancestors to
    any intermediating control on an energy-removing action; the class
    reference declares the check."""
    document = json.loads(REFERENCE.read_bytes())
    assert "intermediated-energy-removing-action" in document["expect"]["forbid"]


# --- the L5 widening and the retained-freeze arms (issue #463 L5) ---------------


@pytest.mark.parametrize(
    "kind",
    ["text", "select", "boolean"],
)
def test_control_kinds_widen_to_the_input_trio(kind: str) -> None:
    """L5: the layout vocabulary's control.kind enum widens to the six
    kinds; the trio admit as control nodes (RED against the 0.1.0 schema,
    which refuses them — the widening is what admits)."""
    layout: dict[str, Any] = {
        "contract_version": "0.4.0",
        "pages": [
            {
                "page_id": "capture",
                "sections": [
                    {
                        "id": "s",
                        "surface": "raised",
                        "children": [{"binding_id": "configure", "kind": kind}],
                    }
                ],
            }
        ],
    }
    assert layout_validator().is_valid(layout)


def test_control_kinds_still_admit_the_founding_kinds() -> None:
    """The widening is additive: the founding kinds keep admitting."""
    layout: dict[str, Any] = {
        "contract_version": "0.4.0",
        "pages": [
            {
                "page_id": "capture",
                "sections": [
                    {
                        "id": "s",
                        "surface": "raised",
                        "children": [
                            {"binding_id": "a", "kind": "button"},
                            {"binding_id": "b", "kind": "numeric"},
                            {"binding_id": "c", "kind": "rotary"},
                        ],
                    }
                ],
            }
        ],
    }
    assert layout_validator().is_valid(layout)


def test_retained_freeze_predecessor_dirs_still_exist() -> None:
    """Copy-never-move: the 0.1.0 family dir and the 0.3.1 plugin-ui dir
    stay in the tree, digest-frozen by their corpus rows."""
    for relpath in (
        "standards/plugin-ui-class-reference/0.1.0",
        "standards/plugin-ui-class-reference/0.2.0",
        "standards/plugin-ui/0.3.1",
    ):
        assert (ROOT / relpath).is_dir(), f"predecessor dir removed: {relpath}"


def test_retained_freeze_predecessor_rows_verify_against_bytes() -> None:
    """The predecessor rows' digests still match the files' bytes — a
    retained version's rows are verified, never rewritten (CON-7)."""
    manifest = json.loads((ROOT / "standards/corpus-manifest.json").read_bytes())
    pins = {str(row["path"]): str(row["sha256"]) for row in manifest["files"]}
    checked = 0
    for directory, names in (
        ("plugin-ui-class-reference/0.1.0",
         ("class-reference.schema.json", "layout.schema.json",
          "class-logic_analyser.json")),
        ("plugin-ui-class-reference/0.2.0",
         ("class-reference.schema.json", "layout.schema.json",
          "class-logic_analyser.json")),
        ("plugin-ui/0.3.1",
         ("ui-manifest.schema.json", "binding-catalogue.schema.json",
          "configuration-preset.schema.json", "presentation-envelope.schema.json")),
    ):
        for name in names:
            relpath = f"{directory}/{name}"
            assert relpath in pins, f"predecessor row missing: {relpath}"
            raw = (ROOT / "standards" / relpath).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == pins[relpath], (
                f"retained row diverges from its frozen bytes: {relpath}"
            )
            checked += 1
    assert checked == 10, f"expected 10 predecessor rows, checked {checked}"


def test_retained_freeze_predecessor_schemas_keep_their_own_consts() -> None:
    """The frozen schemas still pin their own versions — a retained
    version's const is frozen history, never re-stamped."""
    family = json.loads(
        (ROOT / "standards/plugin-ui-class-reference/0.1.0/class-reference.schema.json")
        .read_bytes()
    )
    assert family["properties"]["contract_version"]["const"] == "0.1.0"
    layout = json.loads(
        (ROOT / "standards/plugin-ui-class-reference/0.1.0/layout.schema.json")
        .read_bytes()
    )
    assert layout["properties"]["contract_version"]["const"] == "0.1.0"
    assert layout["$defs"]["control"]["properties"]["kind"]["enum"] == [
        "button", "numeric", "rotary",
    ]
    manifest_schema = json.loads(
        (ROOT / "standards/plugin-ui/0.3.1/ui-manifest.schema.json").read_bytes()
    )
    assert manifest_schema["properties"]["contract_version"]["const"] == "0.3.1"


# --- the L11 widening and the dc_psu reference (issue #463 slot L11) ------------


class TestPlotKindWidening:
    """The 0.3.0 MINOR's substance: ``page_template.plot.kind`` widens
    const -> enum ``[digital_lanes, time_series]`` with per-kind
    conditionals — the lanes group machinery stays exactly as it was
    (digital_lanes), ``time_series`` carries the one structural field
    ``series: "numeric_variables"`` (the closed derivation rule), and
    ``waveform`` is deliberately NOT admitted (L13 widens again on its
    own evidence). RED against the 0.2.0 schema: time_series refuses,
    the widening is what admits. The L12 F4 settlement (2026-10-19
    record §5) makes ``series`` REQUIRED on ``time_series`` inside the
    same unreleased 0.3.0 window: a series-less time_series template is
    a document that does not exist in the corpus, and the tightening
    changes validity for exactly those."""

    def _page(self, plot: dict[str, Any]) -> dict[str, Any]:
        document = minimal_reference()
        document["pages"] = [
            {
                "id": "output",
                "title": "Output",
                "kind": "readings",
                "binding_slots": ["lanes"],
                "plot": plot,
            }
        ]
        return document

    def test_time_series_without_series_refuses(self) -> None:
        """The F4 settlement's RED arm (A9): a time_series plot template
        WITHOUT ``series`` fails schema validation after the tightening —
        absent-semantics would leave two spellings of one meaning and
        push a default into every consumer. The admit direction is
        ``test_time_series_with_the_series_rule_admits`` below (this arm
        replaces the pre-settlement ``test_time_series_plot_admits``,
        whose series-less admit assertion the settlement reverses)."""
        assert not reference_validator().is_valid(
            self._page({"kind": "time_series", "over_slot": "lanes"})
        )

    def test_time_series_with_the_series_rule_admits(self) -> None:
        assert reference_validator().is_valid(
            self._page(
                {
                    "kind": "time_series",
                    "over_slot": "lanes",
                    "series": "numeric_variables",
                }
            )
        )

    def test_time_series_with_group_machinery_refuses(self) -> None:
        assert not reference_validator().is_valid(
            self._page(
                {
                    "kind": "time_series",
                    "over_slot": "lanes",
                    "group_size": 8,
                }
            )
        )

    def test_digital_lanes_with_series_refuses(self) -> None:
        assert not reference_validator().is_valid(
            self._page(
                {
                    "kind": "digital_lanes",
                    "over_slot": "lanes",
                    "series": "numeric_variables",
                }
            )
        )

    def test_waveform_is_not_admitted(self) -> None:
        assert not reference_validator().is_valid(
            self._page({"kind": "waveform", "over_slot": "lanes"})
        )

    def test_series_value_is_closed(self) -> None:
        assert not reference_validator().is_valid(
            self._page(
                {
                    "kind": "time_series",
                    "over_slot": "lanes",
                    "series": "named_variables",
                }
            )
        )

    def test_both_committed_time_series_documents_carry_series(self) -> None:
        """A9's break-nothing half: the tightening changes validity for
        exactly the documents that do not exist — the only committed
        ``time_series`` documents (dc_psu L11, dmm L12) both carry
        ``series: "numeric_variables"`` and both still validate."""
        for path in (REFERENCE_PSU, REFERENCE_DMM):
            document = json.loads(path.read_bytes())
            plots = [
                page["plot"] for page in document["pages"] if "plot" in page
            ]
            time_series = [p for p in plots if p["kind"] == "time_series"]
            assert time_series, path.name
            assert all(
                p.get("series") == "numeric_variables" for p in time_series
            ), path.name
            assert reference_validator().is_valid(document), path.name


class TestDcPsuReference:
    """The committed ``class-dc_psu.json`` (L11): the first
    scalar/readings-shaped class — binding ``otdp.dc_psu/1.0.0``."""

    def test_the_committed_reference_validates(self) -> None:
        assert REFERENCE_PSU.is_file(), f"Missing {REFERENCE_PSU.name}"
        document = json.loads(REFERENCE_PSU.read_bytes())
        assert document["profile_id"] == "otdp.dc_psu/1.0.0"
        assert reference_validator().is_valid(document)

    def test_the_reference_binds_the_catalogued_class_actions(self) -> None:
        """Every action the reference names exists in the OTDP catalogue's
        dc_psu row, and every required action (configure, output, measure)
        is bound."""
        document = json.loads(REFERENCE_PSU.read_bytes())
        catalog = json.loads(OTDP_CATALOG.read_bytes())
        profile = next(
            p for p in catalog["profiles"] if p["id"] == document["profile_id"]
        )
        bound = {
            slot["action"]
            for slot in document["slots"].values()
            if "action" in slot
        }
        assert bound <= set(catalog["actions"])
        assert set(profile["required_actions"]) <= bound

    def test_dc_psu_numbers_are_structural_only(self) -> None:
        """D2: the PSU reference's only numbers are the layout spans
        (12, 7, 5) and the trend section's plot_index (0); its only
        pure-numeric string is the count-arity literal "1"."""
        document = json.loads(REFERENCE_PSU.read_bytes())
        numbers: list[int | float] = []
        numeric_strings: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, bool):
                return
            if isinstance(node, (int, float)):
                numbers.append(node)
            elif isinstance(node, str):
                try:
                    float(node)
                except ValueError:
                    return
                numeric_strings.append(node)
            elif isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(document)
        assert set(numbers) == {0, 12, 7, 5}
        assert set(numeric_strings) == {"1"}

    def test_dc_psu_layouts_carry_no_text_nodes(self) -> None:
        document = json.loads(REFERENCE_PSU.read_bytes())

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if "body" in node:
                    pytest.fail("reference layout carries a text node")
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for layout_page in document.get("layouts", []):
            walk(layout_page)

    def test_dc_psu_controls_match_the_class_ladder(self) -> None:
        """configure is preset-mediated at birth, the output toggle
        declares a deviation (the directional §C.1 presentation is beyond
        the per-action vocabulary — the record's §2.2); measure needs no
        control (the dataset slot is page-covered)."""
        document = json.loads(REFERENCE_PSU.read_bytes())
        controls = document["expect"]["controls"]
        assert controls == {
            "otdp.dc_psu.configure/1.0.0": "preset",
            "otdp.dc_psu.output/1.0.0": "deviation",
        }

    def test_dc_psu_declares_the_analyser_forbid_set(self) -> None:
        """The analyser's four forbid ids stand (the record's §2): the
        intermediated-energy-removing-action id declares the class's
        intent even though the gate's D7 slug set does not yet name
        output."""
        document = json.loads(REFERENCE_PSU.read_bytes())
        assert set(document["expect"]["forbid"]) == {
            "confirm-wrapped-run-action",
            "color-role-hint-on-lane",
            "untraceable-lane-label",
            "intermediated-energy-removing-action",
        }

    def test_dc_psu_cannot_derive_names_the_mockup_elements(self) -> None:
        """Every cannot_derive id traces to a mockup element (the record's
        §2.3 table): the six ids, verbatim."""
        document = json.loads(REFERENCE_PSU.read_bytes())
        ids = {str(row["id"]) for row in document["cannot_derive"]}
        assert ids == {
            "output-control",
            "setpoint-staging",
            "margin-alert",
            "limit-overlay",
            "presets",
            "channel-names",
        }


class TestDmmReference:
    """The committed ``class-dmm.json`` (L12): the observation-pure class
    — binding ``otdp.dmm/1.0.0``, no sourcing action, no directional
    safety surface, no capture view."""

    def test_the_committed_reference_validates(self) -> None:
        assert REFERENCE_DMM.is_file(), f"Missing {REFERENCE_DMM.name}"
        document = json.loads(REFERENCE_DMM.read_bytes())
        assert document["profile_id"] == "otdp.dmm/1.0.0"
        assert reference_validator().is_valid(document)

    def test_the_reference_binds_the_catalogued_class_actions(self) -> None:
        """Every action the reference names exists in the OTDP catalogue's
        dmm row, and every required action (configure, measure) is
        bound."""
        document = json.loads(REFERENCE_DMM.read_bytes())
        catalog = json.loads(OTDP_CATALOG.read_bytes())
        profile = next(
            p for p in catalog["profiles"] if p["id"] == document["profile_id"]
        )
        bound = {
            slot["action"]
            for slot in document["slots"].values()
            if "action" in slot
        }
        assert bound <= set(catalog["actions"])
        assert set(profile["required_actions"]) <= bound

    def test_dmm_numbers_are_structural_only(self) -> None:
        """D2: the dmm reference's only numbers are the layout spans
        (12, 7, 5) and the trend section's plot_index (0); its only
        pure-numeric string is the count-arity literal "1"."""
        document = json.loads(REFERENCE_DMM.read_bytes())
        numbers: list[int | float] = []
        numeric_strings: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, bool):
                return
            if isinstance(node, (int, float)):
                numbers.append(node)
            elif isinstance(node, str):
                try:
                    float(node)
                except ValueError:
                    return
                numeric_strings.append(node)
            elif isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(document)
        assert set(numbers) == {0, 12, 7, 5}
        assert set(numeric_strings) == {"1"}

    def test_dmm_layouts_carry_no_text_nodes(self) -> None:
        document = json.loads(REFERENCE_DMM.read_bytes())

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if "body" in node:
                    pytest.fail("reference layout carries a text node")
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for layout_page in document.get("layouts", []):
            walk(layout_page)

    def test_dmm_controls_match_the_class_ladder(self) -> None:
        """configure is preset-mediated at birth (the function/range/
        aperture/autozero surface is inexpressible at L2 — the record's
        §3); measure needs no control (the dataset slot is page-covered
        via the plot figure)."""
        document = json.loads(REFERENCE_DMM.read_bytes())
        controls = document["expect"]["controls"]
        assert controls == {
            "otdp.dmm.configure/1.0.0": "preset",
        }

    def test_dmm_declares_the_observation_pure_forbid_set(self) -> None:
        """Three forbid ids: the family-generic carry WITHOUT the
        energy-removing id — dmm has no energy-removing action and cannot
        acquire one within its profile, so dc_psu's intent declaration
        would be vacuous about a surface that cannot exist (the record's
        §3, the drop with its reason recorded)."""
        document = json.loads(REFERENCE_DMM.read_bytes())
        assert set(document["expect"]["forbid"]) == {
            "confirm-wrapped-run-action",
            "color-role-hint-on-lane",
            "untraceable-lane-label",
        }

    def test_dmm_cannot_derive_names_the_mockup_elements(self) -> None:
        """Every cannot_derive id traces to a mockup element (the record's
        §3 table): the five ids, verbatim."""
        document = json.loads(REFERENCE_DMM.read_bytes())
        ids = {str(row["id"]) for row in document["cannot_derive"]}
        assert ids == {
            "function-selection",
            "range-margin-alert",
            "range-overlay",
            "presets",
            "channel-names",
        }
