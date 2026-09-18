"""Synthetic class fixtures exercise presets and waveform presentation together."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.presentation.contracts import ValidationReport, validate_presentation

type JsonObject = dict[str, Any]
type Specimen = tuple[JsonObject, dict[str, JsonObject], JsonObject, JsonObject, dict[str, bytes]]

ROOT = Path(__file__).resolve().parents[2]


def encode(value: object) -> bytes:
    return json.dumps(value).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load(name: str) -> JsonObject:
    document: JsonObject = json.loads((ROOT / "standards/otdp/0.1.1" / name).read_bytes())
    return document


@pytest.fixture
def specimen() -> Specimen:
    documents: dict[str, JsonObject] = {}
    for directory in ("otdp/0.1.1", "plugin-ui/0.1.0"):
        for path in (ROOT / "standards" / directory).glob("*.schema.json"):
            document = json.loads(path.read_bytes())
            documents[document["$id"]] = document
    catalog = load("device-profile-catalog.json")
    documents["catalog"] = catalog
    descriptor = load("examples/class-dc_psu.json")
    action = "otdp.dc_psu.configure/1.0.0"
    schema = catalog["actions"][action]["input_schema"]
    schema_raw = encode(schema)
    preset = {
        "contract_version": "0.1.0",
        "id": "synthetic-3v3",
        "title": "Synthetic 3.3 V configuration",
        "revision": "1.0.0",
        "plugin_id": descriptor["id"],
        "profile_ids": descriptor["profiles"],
        "supported_firmware": ["1.0"],
        "settings_schema": {"id": schema["$id"], "sha256": digest(schema_raw)},
        "settings": {
            "configuration_id": "cfg-1",
            "channel": "ch1",
            "voltage_v": 3.3,
            "current_limit_a": 0.5,
            "ovp_v": 3.6,
            "ocp_a": 0.6,
        },
        "provenance": {"author": "BenchWeave", "revision": "1", "evidence": "synthetic"},
    }
    target = {
        "id": "configure",
        "kind": "configuration",
        "action_id": action,
        "profile_ids": descriptor["profiles"],
        "input_schema_id": schema["$id"],
        "schema_asset_id": "settings",
        "preset_asset_ids": ["preset"],
    }
    manifest = {
        "contract_version": "0.1.0",
        "plugin_id": descriptor["id"],
        "descriptor_sha256": digest(encode(descriptor)),
        "bindings": [
            {
                "id": "configuration",
                "kind": "configuration",
                "target_id": "configure",
                "preset_ids": ["preset"],
            }
        ],
        "pages": [
            {
                "id": "settings",
                "kind": "configuration",
                "title": "Settings",
                "bindings": ["configuration"],
                "required": True,
            }
        ],
    }
    return (
        descriptor,
        documents,
        target,
        manifest,
        {"settings": schema_raw, "preset": encode(preset)},
    )


def validate(specimen: Specimen) -> ValidationReport:
    descriptor, documents, target, manifest, assets = specimen
    descriptor_raw = encode(descriptor)
    manifest["descriptor_sha256"] = digest(descriptor_raw)
    manifest["plugin_id"] = descriptor["id"]
    manifest["assets"] = [
        {"id": name, "path": name + ".json", "sha256": digest(raw)} for name, raw in assets.items()
    ]
    manifest_raw = encode(manifest)
    catalogue = {
        "contract_version": "0.1.0",
        "descriptor_sha256": digest(descriptor_raw),
        "targets": [target],
    }
    envelope = {
        "contract_version": "0.1.0",
        "descriptor_sha256": digest(descriptor_raw),
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": digest(manifest_raw)},
    }
    resources = {name + ".json": raw for name, raw in assets.items()}
    resources["manifest.json"] = manifest_raw
    return validate_presentation(
        encode(envelope),
        descriptor_raw=descriptor_raw,
        resources=resources,
        binding_catalogue=catalogue,
        schema_documents=documents,
        supported_features=frozenset(),
        supported_panels=frozenset(),
        firmware="1.0",
    )


def test_configuration_preset_specimen(specimen: Specimen) -> None:
    report = validate(specimen)
    assert report.valid, report.findings


def test_profile_must_supply_the_bound_action(specimen: Specimen) -> None:
    specimen[0]["profiles"] = [*specimen[0]["profiles"], "otdp.other/1.0.0"]
    specimen[2]["profile_ids"] = ["otdp.other/1.0.0"]
    assert not validate(specimen).valid


def test_preset_cannot_bypass_canonical_action_schema(specimen: Specimen) -> None:
    permissive = json.loads(specimen[4]["settings"])
    permissive.pop("required", None)
    permissive["additionalProperties"] = True
    preset = json.loads(specimen[4]["preset"])
    preset["settings"] = {}
    specimen[4]["settings"] = encode(permissive)
    preset["settings_schema"]["sha256"] = digest(specimen[4]["settings"])
    specimen[4]["preset"] = encode(preset)
    assert not validate(specimen).valid


def scope_specimen(specimen: Specimen) -> Specimen:
    descriptor = load("examples/class-oscilloscope.json")
    action = "otdp.oscilloscope.fetch/1.0.0"
    target = {
        "id": "waveform",
        "kind": "dataset",
        "action_id": action,
        "profile_ids": descriptor["profiles"],
        "measurement_schema_id": "urn:otdp:measurement:0.1.1",
        "variables": [
            {"id": "time", "type": "number", "shape": "vector", "unit": "s", "axis_role": "x"},
            {"id": "signal", "type": "number", "shape": "vector", "unit": "V", "axis_role": "y"},
        ],
    }
    manifest = {
        "contract_version": "0.1.0",
        "bindings": [{"id": "capture", "kind": "dataset", "target_id": "waveform"}],
        "pages": [
            {
                "id": "waveform",
                "kind": "dataset",
                "title": "Waveform",
                "bindings": ["capture"],
                "required": True,
                "plots": [
                    {"kind": "waveform", "binding_id": "capture", "x": "time", "y": ["signal"]}
                ],
            }
        ],
    }
    return descriptor, specimen[1], target, manifest, {}


def test_waveform_specimen(specimen: Specimen) -> None:
    report = validate(scope_specimen(specimen))
    assert report.valid, report.findings


def test_dataset_requires_descriptor_measurement_contract(specimen: Specimen) -> None:
    scope = scope_specimen(specimen)
    scope[0]["contracts"] = []
    assert not validate(scope).valid
