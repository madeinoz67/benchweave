"""Preset checks are offline and preserve complete, explicit settings."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.presentation import contracts

type JsonObject = dict[str, Any]
type Bundle = tuple[JsonObject, JsonObject, bytes, dict[str, JsonObject]]

ROOT = Path(__file__).resolve().parents[2]


def encode(value: object) -> bytes:
    return json.dumps(value).encode()


@pytest.fixture
def bundle() -> Bundle:
    documents: dict[str, JsonObject] = {}
    for path in (ROOT / "standards/plugin-ui/0.1.1").glob("*.schema.json"):
        schema = json.loads(path.read_bytes())
        documents[schema["$id"]] = schema
    descriptor = json.loads(
        (ROOT / "standards/otdp/0.1.2/examples/class-dc_psu.json").read_bytes()
    )
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:test:complete-settings",
        "type": "object",
        "required": ["voltage"],
        "additionalProperties": False,
        "properties": {"voltage": {"type": "number", "minimum": 0, "maximum": 5, "default": 3.3}},
    }
    schema_raw = encode(schema)
    preset = {
        "contract_version": "0.1.1",
        "id": "synthetic-3v3",
        "title": "Synthetic 3.3 V settings",
        "revision": "1.0.0",
        "plugin_id": descriptor["id"],
        "profile_ids": descriptor["profiles"],
        "supported_firmware": ["1.0"],
        "settings_schema": {
            "id": schema["$id"],
            "sha256": hashlib.sha256(schema_raw).hexdigest(),
        },
        "settings": {"voltage": 3.3},
        "provenance": {"author": "BenchWeave tests", "revision": "1", "evidence": "synthetic"},
    }
    return preset, descriptor, schema_raw, documents


def validate(bundle: Bundle, *, firmware: str | None = "1.0") -> contracts.ValidationReport:
    preset, descriptor, schema_raw, documents = bundle
    assert hasattr(contracts, "validate_preset"), "Preset validator is missing"
    return contracts.validate_preset(
        encode(preset),
        descriptor_raw=encode(descriptor),
        settings_schema_raw=schema_raw,
        schema_documents=documents,
        firmware=firmware,
    )


def test_valid_complete_preset(bundle: Bundle) -> None:
    assert validate(bundle).valid


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("plugin_id", "wrong.plugin", "identity_mismatch"),
        ("profile_ids", ["unknown/1.0"], "capability_mismatch"),
        ("settings", {}, "invalid_settings"),
        ("settings", {"voltage": 6}, "invalid_settings"),
        ("settings", {"voltage": 3.3, "execute": True}, "invalid_settings"),
        ("contract_version", "2.0.0", "unsupported_version"),
    ],
)
def test_rejects_incompatible_preset(bundle: Bundle, field: str, value: object, code: str) -> None:
    bundle[0][field] = value
    report = validate(bundle)
    assert not report.valid
    assert code in {finding.code for finding in report.findings}


@pytest.mark.parametrize("firmware", [None, "2.0"])
def test_requires_known_compatible_firmware(bundle: Bundle, firmware: str | None) -> None:
    assert "incompatible_firmware" in {
        finding.code for finding in validate(bundle, firmware=firmware).findings
    }


def test_hashes_exact_settings_schema_bytes(bundle: Bundle) -> None:
    preset, descriptor, schema_raw, documents = bundle
    report = validate((preset, descriptor, schema_raw + b"\n", documents))
    assert "digest_mismatch" in {finding.code for finding in report.findings}


def test_schema_identity_is_checked(bundle: Bundle) -> None:
    bundle[0]["settings_schema"]["id"] = "urn:test:other"
    assert "identity_mismatch" in {f.code for f in validate(bundle).findings}


def test_unknown_schema_reference_is_offline_failure(bundle: Bundle) -> None:
    preset, descriptor, schema_raw, documents = bundle
    schema = json.loads(schema_raw)
    schema["$ref"] = "https://unreachable.invalid/missing.schema.json"
    schema_raw = encode(schema)
    preset["settings_schema"]["sha256"] = hashlib.sha256(schema_raw).hexdigest()
    report = validate((preset, descriptor, schema_raw, documents))
    assert "unresolved_reference" in {f.code for f in report.findings}


def test_invalid_descriptor_returns_finding(bundle: Bundle) -> None:
    preset, _, schema_raw, documents = bundle
    assert not validate((preset, {}, schema_raw, documents)).valid
