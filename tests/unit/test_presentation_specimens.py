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
    document: JsonObject = json.loads((ROOT / "standards/otdp/0.1.2" / name).read_bytes())
    return document


@pytest.fixture
def specimen() -> Specimen:
    documents: dict[str, JsonObject] = {}
    for directory in ("otdp/0.1.2", "plugin-ui/0.1.1"):
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
        "contract_version": "0.1.1",
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
        "contract_version": "0.1.1",
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


def validate(specimen: Specimen, *, features: frozenset[str] = frozenset()) -> ValidationReport:
    descriptor, documents, target, manifest, assets = specimen
    descriptor_raw = encode(descriptor)
    manifest["descriptor_sha256"] = digest(descriptor_raw)
    manifest["plugin_id"] = descriptor["id"]
    manifest["assets"] = [
        {"id": name, "path": name + ".json", "sha256": digest(raw)} for name, raw in assets.items()
    ]
    manifest_raw = encode(manifest)
    catalogue = {
        "contract_version": "0.1.1",
        "descriptor_sha256": digest(descriptor_raw),
        "targets": [target],
    }
    envelope = {
        "contract_version": "0.1.1",
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
        supported_features=features,
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
        "measurement_schema_id": "urn:otdp:measurement:0.1.2",
        "variables": [
            {"id": "time", "type": "number", "shape": "vector", "unit": "s", "axis_role": "x"},
            {"id": "signal", "type": "number", "shape": "vector", "unit": "V", "axis_role": "y"},
        ],
    }
    manifest = {
        "contract_version": "0.1.1",
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


# --- channel_hints (plugin-ui 0.1.1) on a multi-y dataset specimen ---

FEATURE_CONDITIONS: tuple[frozenset[str], ...] = (
    frozenset(),
    frozenset({"legend/1.0.0"}),
)


def multi_channel_specimen(specimen: Specimen, y_count: int) -> Specimen:
    """Dual-and-more-channel waveform: the only target kind that can plot several
    y variables at once (observation targets carry exactly one value variable)."""
    descriptor = load("examples/class-oscilloscope.json")
    y_variables = [
        {
            "id": f"trace{index:02d}",
            "type": "number",
            "shape": "vector",
            "unit": "V",
            "axis_role": "y",
        }
        for index in range(1, y_count + 1)
    ]
    variables = [
        {"id": "time", "type": "number", "shape": "vector", "unit": "s", "axis_role": "x"}
    ] + y_variables
    target = {
        "id": "waveform",
        "kind": "dataset",
        "action_id": "otdp.oscilloscope.fetch/1.0.0",
        "profile_ids": descriptor["profiles"],
        "measurement_schema_id": "urn:otdp:measurement:0.1.2",
        "variables": variables,
    }
    manifest = {
        "contract_version": "0.1.1",
        "plugin_id": descriptor["id"],
        "bindings": [{"id": "capture", "kind": "dataset", "target_id": "waveform"}],
        "pages": [
            {
                "id": "waveform",
                "kind": "dataset",
                "title": "Waveform",
                "bindings": ["capture"],
                "required": True,
                "plots": [
                    {
                        "kind": "waveform",
                        "binding_id": "capture",
                        "x": "time",
                        "y": [f"trace{index:02d}" for index in range(1, y_count + 1)],
                    }
                ],
            }
        ],
    }
    return descriptor, specimen[1], target, manifest, {}


def test_multi_channel_hinted_specimen_pair_is_equivalent(specimen: Specimen) -> None:
    """Metric 1 on the multi-y case hints exist for: hinted vs unhinted twin,
    both feature conditions, identical finding-free reports."""
    scope = multi_channel_specimen(specimen, y_count=2)
    baseline = {features: validate(scope, features=features) for features in FEATURE_CONDITIONS}
    assert all(report.valid for report in baseline.values()), baseline
    scope[3]["pages"][0]["plots"][0]["channel_hints"] = [
        {"variable_id": "trace02", "color_role": "accent"},
        {"variable_id": "trace01", "visible": False},
    ]
    for features, unhinted in baseline.items():
        report = validate(scope, features=features)
        assert report.valid, report.findings
        assert report.findings == unhinted.findings


@pytest.mark.parametrize("with_plots", [False, True], ids=["configuration", "waveform"])
def test_specimen_hint_pairs_are_equivalent(specimen: Specimen, with_plots: bool) -> None:
    """Metric 1 on the remaining corpus: the configuration specimen (no plots,
    so the pair is byte-identical — hints have nowhere to attach) and the
    waveform specimen (single-y hint), each at both feature conditions."""
    scope = scope_specimen(specimen) if with_plots else specimen
    baseline = {features: validate(scope, features=features) for features in FEATURE_CONDITIONS}
    assert all(report.valid for report in baseline.values()), baseline
    if with_plots:
        scope[3]["pages"][0]["plots"][0]["channel_hints"] = [
            {"variable_id": "signal", "color_role": "muted"}
        ]
    for features, unhinted in baseline.items():
        report = validate(scope, features=features)
        assert report.valid, report.findings
        assert report.findings == unhinted.findings


def test_seventeenth_hint_on_sixteen_channel_plot_is_rejected(specimen: Specimen) -> None:
    """Metric 2 variant 6: schema maxItems mirrors y's own 16-channel ceiling.

    Lives here (not with the other five variants) because a 16-y plot needs a
    dataset target: observation targets with more than one value variable fail
    ``capability_mismatch`` independently of any hint.
    """
    scope = multi_channel_specimen(specimen, y_count=16)
    hints: list[dict[str, str | bool]] = [
        {"variable_id": f"trace{index:02d}", "color_role": "muted"} for index in range(1, 17)
    ]
    hints.append({"variable_id": "time", "visible": False})
    scope[3]["pages"][0]["plots"][0]["channel_hints"] = hints
    report = validate(scope)
    assert [finding.code for finding in report.findings] == ["invalid_document"]
