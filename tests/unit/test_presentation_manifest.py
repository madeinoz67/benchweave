"""Presentation manifests cannot invent capabilities or executable authority."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.presentation import contracts

type JsonObject = dict[str, Any]
type Bundle = tuple[bytes, dict[str, JsonObject], JsonObject, JsonObject]

ROOT = Path(__file__).resolve().parents[2]


def encode(value: object) -> bytes:
    return json.dumps(value).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def bundle() -> Bundle:
    descriptor = (ROOT / "standards/otdp/0.1.1/examples/reference-psu.json").read_bytes()
    documents: dict[str, JsonObject] = {}
    for path in (ROOT / "standards/plugin-ui/0.1.1").glob("*.schema.json"):
        schema = json.loads(path.read_bytes())
        documents[schema["$id"]] = schema
    target = {
        "id": "voltage",
        "kind": "observation",
        "parameter_id": "voltage_measured",
        "variables": [
            {
                "id": "time",
                "type": "number",
                "unit": "s",
                "shape": "scalar",
                "axis_role": "receipt_time",
            },
            {"id": "value", "type": "number", "unit": "V", "shape": "scalar", "axis_role": "value"},
        ],
    }
    catalogue = {
        "contract_version": "0.1.1",
        "descriptor_sha256": digest(descriptor),
        "targets": [target],
    }
    manifest = {
        "contract_version": "0.1.1",
        "plugin_id": json.loads(descriptor)["id"],
        "descriptor_sha256": digest(descriptor),
        "bindings": [{"id": "reading", "kind": "observation", "target_id": "voltage"}],
        "pages": [
            {
                "id": "readings",
                "title": "Readings",
                "kind": "readings",
                "bindings": ["reading"],
                "required": True,
                "plots": [
                    {"kind": "time_series", "binding_id": "reading", "x": "time", "y": ["value"]}
                ],
            }
        ],
    }
    return descriptor, documents, catalogue, manifest


def validate(
    bundle: Bundle,
    *,
    resources: dict[str, bytes] | None = None,
    envelope_updates: JsonObject | None = None,
    panels: frozenset[str] = frozenset(),
    features: frozenset[str] = frozenset(),
) -> contracts.ValidationReport:
    descriptor, documents, catalogue, manifest = bundle
    manifest_raw = encode(manifest)
    envelope = {
        "contract_version": "0.1.1",
        "descriptor_sha256": digest(descriptor),
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": digest(manifest_raw)},
    }
    envelope.update(envelope_updates or {})
    assert hasattr(contracts, "validate_presentation"), "Presentation validator is missing"
    return contracts.validate_presentation(
        encode(envelope),
        descriptor_raw=descriptor,
        resources=resources if resources is not None else {"manifest.json": manifest_raw},
        binding_catalogue=catalogue,
        schema_documents=documents,
        supported_features=features,
        supported_panels=panels,
        firmware="1.0",
    )


def codes(report: contracts.ValidationReport) -> set[str]:
    return {finding.code for finding in report.findings}


def test_valid_reading_plot(bundle: Bundle) -> None:
    assert validate(bundle).valid


@pytest.mark.parametrize("path", ["../manifest.json", "/tmp/manifest.json", "a\\b", "x\n"])
def test_rejects_unsafe_resource_keys(bundle: Bundle, path: str) -> None:
    assert "unsafe_path" in codes(validate(bundle, resources={path: b"{}"}))


def test_descriptor_hash_binds_attachment(bundle: Bundle) -> None:
    report = validate(bundle, envelope_updates={"descriptor_sha256": "0" * 64})
    assert "digest_mismatch" in codes(report)


def test_manifest_hash_uses_exact_bytes(bundle: Bundle) -> None:
    report = validate(bundle, resources={"manifest.json": encode(bundle[3]) + b"\n"})
    assert "digest_mismatch" in codes(report)


def test_missing_resource_is_rejected(bundle: Bundle) -> None:
    assert "unresolved_reference" in codes(validate(bundle, resources={}))


def test_duplicate_binding_is_rejected(bundle: Bundle) -> None:
    bundle[3]["bindings"] *= 2
    assert not validate(bundle).valid


def test_cannot_invent_parameter(bundle: Bundle) -> None:
    bundle[2]["targets"][0]["parameter_id"] = "invented"
    assert "capability_mismatch" in codes(validate(bundle))


def test_cannot_change_parameter_unit(bundle: Bundle) -> None:
    bundle[2]["targets"][0]["variables"][1]["unit"] = "A"
    assert "capability_mismatch" in codes(validate(bundle))


def test_unknown_page_binding_is_rejected(bundle: Bundle) -> None:
    bundle[3]["pages"][0]["bindings"] = ["missing"]
    assert "unresolved_reference" in codes(validate(bundle))


def test_non_numeric_plot_is_rejected(bundle: Bundle) -> None:
    bundle[2]["targets"][0]["variables"][1]["type"] = "string"
    assert "invalid_plot" in codes(validate(bundle))


def test_waveform_requires_vectors(bundle: Bundle) -> None:
    bundle[3]["pages"][0]["plots"][0]["kind"] = "waveform"
    assert "invalid_plot" in codes(validate(bundle))


def test_missing_required_feature_is_rejected(bundle: Bundle) -> None:
    bundle[3]["required_ui_features"] = ["unknown/1.0.0"]
    assert "unsupported_feature" in codes(validate(bundle))


@pytest.mark.parametrize("required", [False, True])
def test_unavailable_panel_is_explicit(bundle: Bundle, required: bool) -> None:
    bundle[3]["pages"] = [
        {
            "id": "custom",
            "title": "Custom",
            "kind": "custom_panel",
            "panel_id": "custom/1.0.0",
            "bindings": [],
            "required": required,
        }
    ]
    report = validate(bundle)
    assert report.valid is not required
    assert report.unavailable_pages == ("custom",)
    assert validate(bundle, panels=frozenset({"custom/1.0.0"})).valid


def test_asset_digest_is_checked(bundle: Bundle) -> None:
    bundle[3]["assets"] = [{"id": "help", "path": "help.txt", "sha256": "0" * 64}]
    resources = {"manifest.json": encode(bundle[3]), "help.txt": b"help"}
    assert "digest_mismatch" in codes(validate(bundle, resources=resources))


def test_unknown_executable_field_is_rejected(bundle: Bundle) -> None:
    bundle[3]["execute"] = "shell command"
    assert not validate(bundle).valid


# --- channel_hints (plugin-ui 0.1.1): P1/P2 equivalence and P3 catches ---


def test_hinted_and_unhinted_manifests_validate_identically(bundle: Bundle) -> None:
    """P1/P2: well-formed hints change no validation result, on any feature set.

    A host with no hint-consuming renderer feature (empty feature set) and a
    host with features declared both validate the hint-bearing document
    identically to the hint-free one: hints are inert data, never a
    ``required_ui_features`` entry.
    """
    baseline = {
        features: validate(bundle, features=features)
        for features in (frozenset(), frozenset({"legend/1.0.0"}))
    }
    assert all(report.valid for report in baseline.values())
    bundle[3]["pages"][0]["plots"][0]["channel_hints"] = [
        {"variable_id": "value", "color_role": "muted"}
    ]
    for features, unhinted in baseline.items():
        report = validate(bundle, features=features)
        assert report.valid, report.findings
        assert report.findings == unhinted.findings
        assert report.unavailable_pages == unhinted.unavailable_pages


def test_hint_for_unknown_variable_is_rejected(bundle: Bundle) -> None:
    bundle[3]["pages"][0]["plots"][0]["channel_hints"] = [
        {"variable_id": "unknown", "color_role": "accent"}
    ]
    report = validate(bundle)
    assert [finding.code for finding in report.findings] == ["unresolved_reference"]
    assert report.findings[0].path == "pages.readings.plots.channel_hints"


def test_hint_for_target_variable_outside_plot_y_is_rejected(bundle: Bundle) -> None:
    """``time`` is a variable of the bound target but the plot's x axis, not a y channel."""
    bundle[3]["pages"][0]["plots"][0]["channel_hints"] = [
        {"variable_id": "time", "visible": False}
    ]
    report = validate(bundle)
    assert [finding.code for finding in report.findings] == ["unresolved_reference"]


def test_duplicate_hint_variable_is_rejected(bundle: Bundle) -> None:
    bundle[3]["pages"][0]["plots"][0]["channel_hints"] = [
        {"variable_id": "value", "color_role": "accent"},
        {"variable_id": "value", "visible": False},
    ]
    report = validate(bundle)
    assert [finding.code for finding in report.findings] == ["invalid_document"]
    assert "Duplicate identifiers" in report.findings[0].message


def test_unknown_color_role_is_rejected(bundle: Bundle) -> None:
    """Severity roles are deliberately outside the hint vocabulary (schema job)."""
    bundle[3]["pages"][0]["plots"][0]["channel_hints"] = [
        {"variable_id": "value", "color_role": "critical"}
    ]
    report = validate(bundle)
    assert [finding.code for finding in report.findings] == ["invalid_document"]


def test_vacuous_hint_object_is_rejected(bundle: Bundle) -> None:
    bundle[3]["pages"][0]["plots"][0]["channel_hints"] = [{"variable_id": "value"}]
    report = validate(bundle)
    assert [finding.code for finding in report.findings] == ["invalid_document"]
