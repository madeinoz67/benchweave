"""The commissioned transport-settings surface (issue #147 increment 3).

Derivations (from the increment-3 design record §1.2, not restatements):

- the document is gateway-schema-validated (a schema in gateway source, NOT
  corpus — provider instances are deliberately versioned elsewhere) and
  ``additionalProperties: false`` throughout: no field can express an
  endpoint, path target, process, credential or secret — the surface
  carries identity only (contract triple + connection_key binding), and
  that is a schema property, not a policy;
- every admitted ``document`` decodes through the exact-byte decoder, its
  bytes must hash to the triple's ``sha256`` (``settings_digest_mismatch:``),
  and the instance must validate against the vendored provider schema;
- refusals carry the typed ``settings_schema:`` / ``settings_digest_mismatch:``
  prefixes, machine-matchable like every other admission refusal;
- the settings document itself decodes through the exact-byte decoder
  (duplicate keys, non-finite numbers, size, strict UTF-8).

The module under test is new: every name resolves at call time so the test
module COLLECTS against the parent commit (the new-module RED convention).
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "standards" / "otdp" / "0.2.2" / "examples"


def _module() -> Any:
    return importlib.import_module("benchweave.control.provider_settings")


def _write_pair(package: Path) -> tuple[dict[str, Any], bytes]:
    """The corpus reference provider pair, written verbatim into ``package``."""
    contract_raw = (EXAMPLES / "reference-provider.json").read_bytes()
    (package / "reference-provider.json").write_bytes(contract_raw)
    contract = json.loads(contract_raw)
    return contract, contract_raw


def _valid_settings(package: Path) -> Path:
    """Write ``package/transport-settings.json`` admitting the corpus pair."""
    contract, raw = _write_pair(package)
    settings = {
        "config_version": "1",
        "admitted": [
            {
                "id": contract["id"],
                "version": contract["version"],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "feature_id": contract["feature_id"],
                "document": "reference-provider.json",
            }
        ],
        "connections": [
            {"connection_key": "power_meter", "provider_id": contract["id"]}
        ],
    }
    path = package / "transport-settings.json"
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path


def test_loads_the_identity_axis_and_builds_the_registry(tmp_path: Path) -> None:
    mod = _module()
    registry = mod.load_transport_settings(_valid_settings(tmp_path))
    contract, _raw = _write_pair(tmp_path)
    digest = hashlib.sha256(
        (tmp_path / "reference-provider.json").read_bytes()
    ).hexdigest()
    entry = registry.find(contract["id"], contract["version"], digest)
    assert entry is not None
    assert entry.feature_id == "otdp.transport.reference-hid/1.0.0"
    assert entry.document["transaction_grammar"][0]["kind"] == "hid_output_report"
    assert registry.feature_ids() == frozenset({"otdp.transport.reference-hid/1.0.0"})
    bound = registry.resolve_connection("power_meter")
    assert bound is not None and bound.id == contract["id"]
    assert registry.resolve_connection("no_such_key") is None
    assert registry.find(contract["id"], contract["version"], "0" * 64) is None


def test_the_schema_is_closed_at_every_object_level(tmp_path: Path) -> None:
    """§1.2/§6 made structural: additionalProperties:false throughout, so no
    field — added at any nesting the schema admits — can carry an endpoint,
    path target, credential or secret. A schema walk asserts the close, not
    a policy statement."""
    mod = _module()
    schema = mod.TRANSPORT_SETTINGS_SCHEMA

    def walk(node: dict[str, Any]) -> None:
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, node
        for child in node.values():
            if isinstance(child, dict):
                walk(child)
            elif isinstance(child, list):
                for item in child:
                    if isinstance(item, dict):
                        walk(item)

    walk(schema)
    # Identity-only, positively: every string property is pattern-constrained
    # except the settings-relative document name, which carries the
    # package-relative path rules instead (its own arm below).
    unconstrained = {
        name
        for name, spec in schema["properties"]["admitted"]["items"]["properties"].items()
        if spec.get("type") == "string" and "pattern" not in spec
    }
    assert unconstrained == {"document"}


@pytest.mark.parametrize(
    ("mutation", "label"),
    [
        (lambda s: s.update({"endpoint": "tcp://bench.local:5025"}), "endpoint key"),
        (lambda s: s.update({"config_version": "2"}), "wrong config version"),
        (lambda s: s.pop("connections"), "missing connections"),
        (
            lambda s: s["admitted"][0].update({"secret": "hunter2"}),
            "secret on an admission",
        ),
        (
            lambda s: s["admitted"][0].update({"path": "/dev/ttyUSB0"}),
            "device path on an admission",
        ),
        (
            lambda s: s["admitted"][0].update({"sha256": "not-hex"}),
            "malformed digest",
        ),
        (
            lambda s: s["admitted"][0].update({"feature_id": "otdp.core/9.9.9"}),
            "feature outside the sanctioned sub-namespace",
        ),
        (
            lambda s: s["admitted"][0].update({"id": "not-a-urn"}),
            "malformed provider urn",
        ),
        (
            lambda s: s["connections"][0].update({"provider_id": "tcp://x"}),
            "endpoint as provider id",
        ),
        (
            lambda s: s["connections"][0].update({"connection_key": "PowerMeter"}),
            "malformed connection key",
        ),
    ],
)
def test_schema_refusals_are_typed(
    tmp_path: Path, mutation: Any, label: str
) -> None:
    mod = _module()
    path = _valid_settings(tmp_path)
    settings = json.loads(path.read_text())
    mutation(settings)
    path.write_text(json.dumps(settings, indent=2))
    with pytest.raises(ValueError, match="settings_schema:"):
        mod.load_transport_settings(path)


@pytest.mark.parametrize(
    "document",
    [
        "../outside.json",
        "/absolute/provider.json",
        "a\\b.json",
        "C:provider.json",
        "./here.json",
        "a//b.json",
    ],
)
def test_document_paths_are_settings_relative_and_contained(
    tmp_path: Path, document: str
) -> None:
    mod = _module()
    path = _valid_settings(tmp_path)
    settings = json.loads(path.read_text())
    settings["admitted"][0]["document"] = document
    path.write_text(json.dumps(settings, indent=2))
    with pytest.raises(ValueError, match="settings_schema:"):
        mod.load_transport_settings(path)


def test_document_digest_mismatch_refuses(tmp_path: Path) -> None:
    mod = _module()
    _write_pair(tmp_path)
    contract, raw = _write_pair(tmp_path)
    settings = {
        "config_version": "1",
        "admitted": [
            {
                "id": contract["id"],
                "version": contract["version"],
                "sha256": "a" * 64,  # the bytes hash elsewhere
                "feature_id": contract["feature_id"],
                "document": "reference-provider.json",
            }
        ],
        "connections": [],
    }
    path = tmp_path / "transport-settings.json"
    path.write_text(json.dumps(settings))
    with pytest.raises(ValueError, match="settings_digest_mismatch:"):
        mod.load_transport_settings(path)
    assert hashlib.sha256(raw).hexdigest() != "a" * 64  # the arm's premise


def test_admitted_document_validates_against_the_vendored_provider_schema(
    tmp_path: Path,
) -> None:
    mod = _module()
    not_a_contract = {"id": "urn:otdp:transport-provider:reference-hid:1.0.0"}
    raw = json.dumps(not_a_contract).encode()
    (tmp_path / "reference-provider.json").write_bytes(raw)
    contract = json.loads((EXAMPLES / "reference-provider.json").read_text())
    settings = {
        "config_version": "1",
        "admitted": [
            {
                "id": contract["id"],
                "version": contract["version"],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "feature_id": contract["feature_id"],
                "document": "reference-provider.json",
            }
        ],
        "connections": [],
    }
    path = tmp_path / "transport-settings.json"
    path.write_text(json.dumps(settings))
    with pytest.raises(ValueError, match="settings_schema:"):
        mod.load_transport_settings(path)


def test_internal_consistency_refusals(tmp_path: Path) -> None:
    mod = _module()
    contract, raw = _write_pair(tmp_path)
    digest = hashlib.sha256(raw).hexdigest()
    admission = {
        "id": contract["id"],
        "version": contract["version"],
        "sha256": digest,
        "feature_id": contract["feature_id"],
        "document": "reference-provider.json",
    }
    for admitted, connections, label in (
        # the same triple twice: an ambiguous admission record
        ([admission, dict(admission)], [], "duplicate triple"),
        # a connection naming a provider the document never admitted
        ([admission], [{"connection_key": "k", "provider_id": "urn:x"}], "unknown provider"),
        # one key bound twice
        (
            [admission],
            [
                {"connection_key": "k", "provider_id": contract["id"]},
                {"connection_key": "k", "provider_id": contract["id"]},
            ],
            "duplicate connection key",
        ),
    ):
        path = tmp_path / f"transport-settings-{label.replace(' ', '-')}.json"
        path.write_text(
            json.dumps(
                {
                    "config_version": "1",
                    "admitted": admitted,
                    "connections": connections,
                }
            )
        )
        with pytest.raises(ValueError, match="settings_schema:"):
            mod.load_transport_settings(path), label


def test_the_exact_byte_decoder_governs_the_settings_document(
    tmp_path: Path,
) -> None:
    mod = _module()
    good = _valid_settings(tmp_path)
    plain = good.read_bytes()
    variants = {
        "utf8-bom": b"\xef\xbb\xbf" + plain,
        "utf16": plain.decode().encode("utf-16"),
        "duplicate-keys": plain.replace(b"{", b'{"config_version": "9",', 1),
    }
    for label, raw in variants.items():
        path = tmp_path / f"settings-{label}.json"
        path.write_bytes(raw)
        with pytest.raises(ValueError, match="settings_schema:"):
            mod.load_transport_settings(path), label


def test_a_missing_document_file_refuses(tmp_path: Path) -> None:
    mod = _module()
    path = _valid_settings(tmp_path)
    (tmp_path / "reference-provider.json").unlink()
    with pytest.raises(ValueError, match="settings_schema:"):
        mod.load_transport_settings(path)
