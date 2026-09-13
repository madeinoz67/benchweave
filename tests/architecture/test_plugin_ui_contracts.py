"""Canonical plugin presentation schemas are closed, local and versioned."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "docs/plugin-ui-v0.1.0"
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
        expected = f"https://benchweave.dev/contracts/plugin-ui/0.1.0/{name}.schema.json"
        assert schema["$id"] == expected


@pytest.mark.parametrize("extra", [False, True])
def test_minimal_manifest_needs_no_graph_and_rejects_unknown_fields(extra: bool) -> None:
    documents = schemas()
    registry = Registry().with_resources(
        (value["$id"], Resource.from_contents(value)) for value in documents.values()
    )
    document = {
        "contract_version": "0.1.0",
        "plugin_id": "test.plugin",
        "descriptor_sha256": "0" * 64,
        "pages": [],
        "bindings": [],
    }
    if extra:
        document["execute"] = "arbitrary code"
    validator = Draft202012Validator(documents["ui-manifest"], registry=registry)
    assert validator.is_valid(document) != extra
