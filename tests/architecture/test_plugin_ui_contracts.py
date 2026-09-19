"""Canonical plugin presentation schemas are closed, local and versioned."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "standards/plugin-ui/0.2.0"
NAMES = ("ui-manifest", "configuration-preset", "presentation-envelope", "binding-catalogue")


def schemas() -> dict[str, dict[str, Any]]:
    result = {}
    for name in NAMES:
        path = DIRECTORY / f"{name}.schema.json"
        assert path.is_file(), f"Missing {name} schema"
        schema = json.loads(path.read_bytes())
        Draft202012Validator.check_schema(schema)
        result[name] = schema
    return result


def test_all_contract_schemas_are_valid_and_versioned() -> None:
    for name, schema in schemas().items():
        expected = f"https://benchweave.dev/contracts/plugin-ui/0.2.0/{name}.schema.json"
        assert schema["$id"] == expected


@pytest.mark.parametrize("extra", [False, True])
def test_minimal_manifest_needs_no_graph_and_rejects_unknown_fields(extra: bool) -> None:
    documents = schemas()
    registry = Registry().with_resources(
        (value["$id"], Resource.from_contents(value)) for value in documents.values()
    )
    document = {
        "contract_version": "0.2.0",
        "plugin_id": "test.plugin",
        "descriptor_sha256": "0" * 64,
        "pages": [],
        "bindings": [],
    }
    if extra:
        document["execute"] = "arbitrary code"
    validator = Draft202012Validator(documents["ui-manifest"], registry=registry)
    assert validator.is_valid(document) != extra


def _plot_validator() -> Draft202012Validator:
    documents = schemas()
    registry = Registry().with_resources(
        (value["$id"], Resource.from_contents(value)) for value in documents.values()
    )
    return Draft202012Validator(documents["ui-manifest"], registry=registry)


def _plot_document(hints: Any) -> dict[str, Any]:
    return {
        "contract_version": "0.2.0",
        "plugin_id": "test.plugin",
        "descriptor_sha256": "0" * 64,
        "bindings": [{"id": "capture", "kind": "dataset", "target_id": "waveform"}],
        "pages": [
            {
                "id": "waveform",
                "title": "Waveform",
                "kind": "dataset",
                "bindings": ["capture"],
                "required": False,
                "plots": [
                    {
                        "kind": "waveform",
                        "binding_id": "capture",
                        "x": "time",
                        "y": ["trace01", "trace02"],
                        "channel_hints": hints,
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "hints",
    [
        [{"variable_id": "trace01", "color_role": "accent"}],
        [{"variable_id": "trace02", "visible": False}],
        [{"variable_id": "trace01", "color_role": "muted", "visible": True}],
    ],
    ids=["color-role", "visible", "both"],
)
def test_channel_hints_accept_well_formed_preferences(hints: list[dict[str, Any]]) -> None:
    assert _plot_validator().is_valid(_plot_document(hints))


@pytest.mark.parametrize(
    "hints",
    [
        [{"variable_id": "trace01", "color_role": "critical"}],
        [{"variable_id": "trace01", "colour": "#ff0000"}],
        [{"variable_id": "trace01"}],
        [{"variable_id": "trace01", "visible": "false"}],
        [{"variable_id": f"trace{index:02d}", "color_role": "muted"} for index in range(1, 18)],
    ],
    ids=[
        "severity-role",
        "literal-colour",
        "vacuous",
        "non-boolean-visible",
        "seventeen-on-two-channel-plot",
    ],
)
def test_channel_hints_are_closed_world(hints: list[dict[str, Any]]) -> None:
    """Severity roles, literal colours and vacuous objects are refused by shape;
    the ceiling matches ``y``'s own maxItems."""
    assert not _plot_validator().is_valid(_plot_document(hints))
