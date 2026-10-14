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
    for path in (ROOT / "standards/plugin-ui/0.3.1").glob("*.schema.json"):
        schema = json.loads(path.read_bytes())
        documents[schema["$id"]] = schema
    descriptor = json.loads(
        (ROOT / "standards/otdp/0.2.0/examples/class-dc_psu.json").read_bytes()
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
        "contract_version": "0.3.1",
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


def _with_identity(
    bundle: Bundle, firmware_policy: str, supported_firmware: list[str] | None
) -> Bundle:
    """Rebind the bundle's descriptor identity: the corpus's commissioned
    pattern (reference-can) carries the policy and no descriptor-side
    firmware list; a declared list is the schema-permitted variant."""
    preset, descriptor, schema_raw, documents = bundle
    identity = dict(descriptor.get("identity", {}))
    identity["firmware_policy"] = firmware_policy
    if supported_firmware is None:
        identity.pop("supported_firmware", None)
    else:
        identity["supported_firmware"] = supported_firmware
    return preset, {**descriptor, "identity": identity}, schema_raw, documents


def commissioned(bundle: Bundle) -> Bundle:
    return _with_identity(bundle, "commissioned", None)


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


# --- issue #444: the commissioned policy's firmware authority -------------------


_INCOMPATIBLE = (
    "incompatible_firmware",
    "preset.supported_firmware",
    "A known firmware compatible with the descriptor and preset is required",
)


def test_commissioned_policy_admits_missing_firmware(bundle: Bundle) -> None:
    """Under ``firmware_policy: "commissioned"`` with no descriptor-side
    firmware list (the corpus's own commissioned pattern), a missing firmware
    value is the honest offline posture: the bench's commissioned record is
    the authority (OTDP 0.2.2 specification, identity/firmware policy), so
    the check defers to the apply-time established-firmware gate instead of
    asserting an incompatibility it cannot decide from the descriptor."""
    report = validate(commissioned(bundle), firmware=None)
    assert report.valid, report.findings


def test_commissioned_policy_admits_preset_listed_firmware(bundle: Bundle) -> None:
    """A supplied firmware the preset's own ``supported_firmware`` lists is
    admitted under commissioned policy: the plugin author's applicability
    claim keeps its full force, and the descriptor asserts nothing further."""
    report = validate(commissioned(bundle), firmware="1.0")
    assert report.valid, report.findings


def test_commissioned_preset_list_mismatch_refuses(bundle: Bundle) -> None:
    """Negative control C3: the preset's own declared applicability list is
    enforced regardless of policy — a firmware value outside it refuses with
    the exact unchanged finding (rule 1 of the #444 design's three-rule
    gate)."""
    report = validate(commissioned(bundle), firmware="2.0")
    assert [(f.code, f.path, f.message) for f in report.findings] == [_INCOMPATIBLE]


def test_listed_policy_missing_firmware_refuses(bundle: Bundle) -> None:
    """Negative control C4: ``firmware is None`` stays inadmissible under
    listed policy — unknown firmware fails exactly as before (rule 2)."""
    report = validate(_with_identity(bundle, "listed", ["1.0"]), firmware=None)
    assert [(f.code, f.path, f.message) for f in report.findings] == [_INCOMPATIBLE]


def test_commissioned_declared_list_still_enforced_for_missing(bundle: Bundle) -> None:
    """A commissioned descriptor that DECLARES a firmware list (the
    schema-permitted shape early adopters of the descriptor-side list rely
    on) is enforced regardless of policy: a declared list refuses a missing
    firmware value (rule 3 — None is not a member)."""
    report = validate(_with_identity(bundle, "commissioned", ["1.0"]), firmware=None)
    assert [(f.code, f.path, f.message) for f in report.findings] == [_INCOMPATIBLE]


def test_commissioned_declared_list_still_enforced_for_mismatch(bundle: Bundle) -> None:
    """Rule 3's value arm: a firmware the preset lists but the descriptor's
    declared list does not carry refuses under commissioned policy — the
    descriptor-side membership applies whenever the descriptor declares a
    list."""
    declared = _with_identity(bundle, "commissioned", ["1.0"])
    declared[0]["supported_firmware"] = ["1.0", "2.0"]
    report = validate(declared, firmware="2.0")
    assert [(f.code, f.path, f.message) for f in report.findings] == [_INCOMPATIBLE]


def test_commissioned_declared_list_admits_member(bundle: Bundle) -> None:
    """The declared-list keeper: a firmware inside both the preset's list and
    the descriptor's declared list admits under commissioned policy — the
    workaround shape keeps its check (nothing it relies on disappears)."""
    report = validate(_with_identity(bundle, "commissioned", ["1.0"]), firmware="1.0")
    assert report.valid, report.findings


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


@pytest.mark.parametrize("name", ["fast-survey", "low-noise-pair"])
def test_listed_policy_corpus_admits_with_no_findings(name: str) -> None:
    """Acceptance (iv) of the #444 design: the in-tree listed-policy corpus
    (the shipped sim_scope presets, N=2) admits through the live gate with
    an EMPTY findings tuple — the widening-only proof. The tuple was empty
    under the predecessor gate for exactly these documents and stays empty:
    any non-empty finding would mean a previously-valid listed-policy
    document became refused (the design's KILL condition)."""
    package = ROOT / "plugins/benchweave/sim_scope/src/benchweave_sim_scope"
    documents: dict[str, JsonObject] = {}
    for path in (ROOT / "standards/plugin-ui/0.3.1").glob("*.schema.json"):
        schema = json.loads(path.read_bytes())
        documents[schema["$id"]] = schema
    # The corpus action catalogue so the envelope resolves exactly as the
    # SDK lanes resolve it (the active OTDP version is derived from the
    # committed manifest, never a test-side literal).
    manifest = json.loads((ROOT / "standards/standards-manifest.json").read_bytes())
    otdp_version = next(
        entry["version"] for entry in manifest["standards"] if entry["id"] == "otdp"
    )
    catalog_path = ROOT / "standards" / "otdp" / otdp_version / "device-profile-catalog.json"
    catalog = json.loads(catalog_path.read_bytes())
    documents[catalog.get("$id", f"otdp/{otdp_version}/device-profile-catalog.json")] = catalog
    report = contracts.validate_preset(
        (package / "ui/presets" / f"{name}.json").read_bytes(),
        descriptor_raw=(package / "descriptor.json").read_bytes(),
        settings_schema_raw=(
            package / "ui/settings/oscilloscope-configure.schema.json"
        ).read_bytes(),
        schema_documents=documents,
        firmware="sim-1.0.0",
    )
    assert report.findings == (), name
