"""The class-reference family schemas are closed, local and versioned.

Landing 1 of the class-reference program (design record
``.claude/deep-review/2026-10-14-classref-logic-analyser-design.md``): the
family ``plugin-ui-class-reference/0.1.0`` ships two machine schemas and the
founding ``class-logic_analyser.json`` reference. Every schema rule carries a
valid and an invalid case; the reference-content tests pin the D2
structure-not-data discipline and the D12a extension-seam namespace at the
corpus level (the expansion-side A-rules are Landing 2).
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "standards/plugin-ui-class-reference/0.1.0"
REFERENCE = DIRECTORY / "class-logic_analyser.json"
CLASS_REF_ID = (
    "https://benchweave.dev/contracts/plugin-ui-class-reference"
    "/0.1.0/class-reference.schema.json"
)
LAYOUT_ID = (
    "https://benchweave.dev/contracts/plugin-ui-class-reference"
    "/0.1.0/layout.schema.json"
)
LAYOUT_REF = f"{LAYOUT_ID}#/$defs/layout_page"
# The plugin-ui manifest schema whose extensions seam carries the layout
# block (D12a): the namespace key must match its patternProperties grammar.
UI_MANIFEST = ROOT / "standards/plugin-ui/0.3.1/ui-manifest.schema.json"

# The class's actions per the OTDP 0.2.3 catalogue (the profile row the
# reference binds); the reference's action URNs must all exist there.
OTDP_CATALOG = ROOT / "standards/otdp/0.2.3/device-profile-catalog.json"


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
        "contract_version": "0.1.0",
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
            f"/0.1.0/{name}.schema.json"
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
        minimal_reference(contract_version="0.2.0")
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
    [(">=0.3.1", True), ("0.3.1", True), ("latest", False), (">=zero", False)],
    ids=["range", "bare", "word", "non-numeric"],
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
        ({"binding_slots": ["lanes"], "plot": {"kind": "time_series"}}, "plot-kind"),
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
    instantiations - group_size 8 and the capture-page plot_index 0."""
    document = json.loads(REFERENCE.read_bytes())
    numbers: list[int | float] = []

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            numbers.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    assert sorted(numbers) == [0, 8]


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
    """D12a: the layout block rides the plugin-ui 0.3.1 extensions seam; the
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
        "contract_version": "0.1.0",
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
        "contract_version": "0.1.0",
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
        "contract_version": "0.1.0",
        "pages": [minimal_layout_page()],
    }
    mutate(layout["pages"][0]["sections"][0])
    assert not layout_validator().is_valid(layout)


def test_control_kinds_are_closed() -> None:
    layout: dict[str, Any] = {
        "contract_version": "0.1.0",
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
        "contract_version": "0.1.0",
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
        {"binding_id": "capture", "kind": "select"},
        {"plot_index": "0"},
        {"binding_id": "!bad", "kind": "button"},
        {"binding_id": "arm", "kind": "button", "style": "color:red"},
    ],
    ids=["reading-kind", "plot-index-string", "binding-id-grammar", "closed-world"],
)
def test_layout_nodes_are_closed_world(node: dict[str, Any]) -> None:
    layout: dict[str, Any] = {
        "contract_version": "0.1.0",
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
        "contract_version": "0.1.0",
        "pages": [
            {"page_id": "capture", "sections": [node("outer", [node("middle", [leaf])])]}
        ],
    }
    assert layout_validator().is_valid(three_deep)
    beyond = node("inner", [node("beyond", [{"body": "x"}])])
    four_deep: dict[str, Any] = {
        "contract_version": "0.1.0",
        "pages": [
            {"page_id": "capture", "sections": [node("outer", [node("middle", [beyond])])]}
        ],
    }
    assert not layout_validator().is_valid(four_deep)
