"""The attachment admission seam refuses without activating anything.

``validate_attachment`` is the explicit post-admission boundary: the caller
hands it exact bytes and verified resources, and gets back the compatibility
report — never execution authority. These tests drive the happy path and each
refusal family through the seam's own signature.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.presentation import contracts
from benchweave.presentation.admission import validate_attachment

type JsonObject = dict[str, Any]

ROOT = Path(__file__).resolve().parents[2]
#: The ACTIVE plugin-ui version, derived from the manifest — the module
#: tests the vendoring seam against the corpus the gateway actually pins,
#: and a literal here would go stale at the next bump (#102 D2's lesson).
_PLUGIN_UI = next(
    entry["version"]
    for entry in json.loads(
        (ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
    )["standards"]
    if entry["id"] == "plugin-ui"
)


def encode(value: object) -> bytes:
    return json.dumps(value).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def codes(report: contracts.ValidationReport) -> set[str]:
    return {finding.code for finding in report.findings}


@pytest.fixture
def descriptor_raw() -> bytes:
    # A superseded-version descriptor: admission parses it and does not pin its version.
    return (ROOT / "standards/otdp/0.1.0/examples/reference-psu.json").read_bytes()


@pytest.fixture
def schema_documents() -> dict[str, JsonObject]:
    documents: dict[str, JsonObject] = {}
    for path in (ROOT / "standards" / "plugin-ui" / _PLUGIN_UI).glob("*.schema.json"):
        schema = json.loads(path.read_bytes())
        documents[schema["$id"]] = schema
    return documents


def build_manifest(descriptor_raw: bytes) -> JsonObject:
    return {
        "contract_version": _PLUGIN_UI,
        "plugin_id": json.loads(descriptor_raw)["id"],
        "descriptor_sha256": digest(descriptor_raw),
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


def build_catalogue(descriptor_raw: bytes) -> JsonObject:
    return {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": digest(descriptor_raw),
        "targets": [
            {
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
                    {
                        "id": "value",
                        "type": "number",
                        "unit": "V",
                        "shape": "scalar",
                        "axis_role": "value",
                    },
                ],
            }
        ],
    }


def admit(
    descriptor_raw: bytes,
    schema_documents: dict[str, JsonObject],
    *,
    manifest: JsonObject | None = None,
    envelope_raw: bytes | None = None,
    envelope_updates: JsonObject | None = None,
    resources: dict[str, bytes] | None = None,
    panels: frozenset[str] = frozenset(),
    features: frozenset[str] = frozenset(),
) -> contracts.ValidationReport:
    manifest_raw = encode(manifest if manifest is not None else build_manifest(descriptor_raw))
    if envelope_raw is None:
        envelope: JsonObject = {
            "contract_version": _PLUGIN_UI,
            "descriptor_sha256": digest(descriptor_raw),
            "resource_root": "ui",
            "manifest": {"path": "manifest.json", "sha256": digest(manifest_raw)},
        }
        envelope.update(envelope_updates or {})
        envelope_raw = encode(envelope)
    return validate_attachment(
        envelope_raw,
        descriptor_raw=descriptor_raw,
        verified_resources=(
            resources if resources is not None else {"manifest.json": manifest_raw}
        ),
        binding_catalogue=build_catalogue(descriptor_raw),
        schema_documents=schema_documents,
        supported_features=features,
        supported_panels=panels,
        firmware="1.0",
    )


def test_compatible_attachment_is_admitted(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject]
) -> None:
    report = admit(descriptor_raw, schema_documents)
    assert report.valid
    assert report.findings == ()
    assert report.unavailable_pages == ()


def test_unsupported_envelope_version_is_refused(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject]
) -> None:
    report = admit(
        descriptor_raw, schema_documents, envelope_updates={"contract_version": "9.9.9"}
    )
    assert not report.valid
    assert "unsupported_version" in codes(report)


def test_descriptor_digest_mismatch_is_refused(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject]
) -> None:
    report = admit(
        descriptor_raw, schema_documents, envelope_updates={"descriptor_sha256": "0" * 64}
    )
    assert not report.valid
    assert "digest_mismatch" in codes(report)


def test_plugin_identity_mismatch_is_refused(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject]
) -> None:
    manifest = build_manifest(descriptor_raw)
    manifest["plugin_id"] = "someone:else:1.0.0"
    report = admit(descriptor_raw, schema_documents, manifest=manifest)
    assert not report.valid
    assert "identity_mismatch" in codes(report)


def test_unsafe_resource_key_is_refused(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject]
) -> None:
    report = admit(descriptor_raw, schema_documents, resources={"../manifest.json": b"{}"})
    assert not report.valid
    assert "unsafe_path" in codes(report)


def test_missing_manifest_resource_is_refused(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject]
) -> None:
    report = admit(descriptor_raw, schema_documents, resources={})
    assert not report.valid
    assert "unresolved_reference" in codes(report)


def test_malformed_envelope_bytes_are_refused(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject]
) -> None:
    report = admit(descriptor_raw, schema_documents, envelope_raw=b"\xff not json")
    assert not report.valid
    assert "invalid_document" in codes(report)


def test_oversized_envelope_is_refused(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject]
) -> None:
    padding = b" " * (contracts.MAX_DOCUMENT_BYTES + 1)
    report = admit(descriptor_raw, schema_documents, envelope_raw=b"{}" + padding)
    assert not report.valid
    assert "limit_exceeded" in codes(report)


def test_required_ui_feature_gap_is_refused(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject]
) -> None:
    manifest = build_manifest(descriptor_raw)
    manifest["required_ui_features"] = ["holograms/1.0.0"]
    report = admit(descriptor_raw, schema_documents, manifest=manifest)
    assert not report.valid
    assert "unsupported_feature" in codes(report)


@pytest.mark.parametrize("required", [False, True])
def test_unavailable_panel_refuses_only_required_pages(
    descriptor_raw: bytes, schema_documents: dict[str, JsonObject], required: bool
) -> None:
    manifest = build_manifest(descriptor_raw)
    manifest["pages"] = [
        {
            "id": "custom",
            "title": "Custom",
            "kind": "custom_panel",
            "panel_id": "custom/1.0.0",
            "bindings": [],
            "required": required,
        }
    ]
    report = admit(descriptor_raw, schema_documents, manifest=manifest)
    assert report.valid is not required
    assert report.unavailable_pages == ("custom",)
    supported = admit(
        descriptor_raw, schema_documents, manifest=manifest, panels=frozenset({"custom/1.0.0"})
    )
    assert supported.valid
