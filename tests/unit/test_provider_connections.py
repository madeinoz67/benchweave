"""The commissioned provider-connections surface (issue #568, design §1.3b).

Derivations (from the design record §1.3b, not restatements):

- the commissioned endpoint lives in a second gateway-owned operator
  document — ``provider-connections.json`` — beside the settings file, and
  it binds ``connection_key`` → USB identity and expresses NOTHING else:
  ``additionalProperties: false`` throughout, no field of any other shape
  (URL, path, host, port, credential, process reference) is
  schema-representable — the identity-only discipline of the settings
  schema, restated in this document's own vocabulary;
- ``serial`` is REQUIRED (maintainer ruling 2): a commissioning identity
  without a serial is ambiguous the moment two same-model devices are
  attached, and wrong-device actuation is the hazard the binding exists to
  close — ambiguity is unrepresentable at the schema level;
- internal consistency refuses typed: a key the settings document does not
  bind is dead config; one key with two identities and two keys sharing one
  USB identity (a USB interface is single-client) both refuse
  ``connections_schema:`` at load;
- the presence rule: the document is REQUIRED iff the settings document
  binds any connection — a settings document with connections and no
  endpoints document refuses at load, and the operator learns it at
  startup, not at first run (the closed default, A02);
- the document decodes through the exact-byte decoder with the shared
  1 MiB admission cap, and loads beside the settings file at BOTH
  admission lanes (bootstrap and the run path's re-admission).

The loader and the wiring are new: every name resolves at call time so the
test module COLLECTS against the parent commit (the new-module RED
convention).
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


def _settings_module() -> Any:
    return importlib.import_module("benchweave.control.provider_settings")


def _documents_module() -> Any:
    return importlib.import_module("benchweave.control.documents")


def _write_contract(package: Path) -> dict[str, Any]:
    """The corpus reference provider contract, written into ``package``."""
    raw = (EXAMPLES / "reference-provider.json").read_bytes()
    (package / "reference-provider.json").write_bytes(raw)
    contract: dict[str, Any] = json.loads(raw)
    return contract


def _valid_settings(package: Path) -> Path:
    """Write settings admitting the corpus pair and binding one key."""
    contract = _write_contract(package)
    settings = {
        "config_version": "1",
        "admitted": [
            {
                "id": contract["id"],
                "version": contract["version"],
                "sha256": hashlib.sha256(
                    (package / "reference-provider.json").read_bytes()
                ).hexdigest(),
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


def _valid_connections(package: Path) -> Path:
    """Write ``package/provider-connections.json`` binding the settings' key
    to an invented USB identity (fixture discipline: invented serials, never
    a real device's)."""
    return _write_connections(
        package,
        [
            {
                "connection_key": "power_meter",
                "usb": {
                    "vendor_id": 1027,
                    "product_id": 24593,
                    "serial": "FT-DEMO-0042",
                    "interface": 1,
                },
            }
        ],
    )


def _write_connections(package: Path, connections: list[dict[str, Any]]) -> Path:
    path = package / "provider-connections.json"
    path.write_text(
        json.dumps({"config_version": "1", "connections": connections}, indent=2)
        + "\n"
    )
    return path


def _registry(package: Path) -> Any:
    return _settings_module().load_transport_settings(_valid_settings(package))


# --- the loader ---------------------------------------------------------------


def test_loads_the_identity_axis(tmp_path: Path) -> None:
    mod = _settings_module()
    _valid_connections(tmp_path)
    endpoints = mod.load_provider_connections(
        tmp_path / "provider-connections.json", _registry(tmp_path)
    )
    identity = endpoints.resolve("power_meter")
    assert identity is not None
    assert (identity.vendor_id, identity.product_id, identity.serial) == (
        1027,
        24593,
        "FT-DEMO-0042",
    )
    assert identity.interface == 1
    assert endpoints.resolve("no_such_key") is None
    assert endpoints.resolve(None) is None


def test_the_schema_is_closed_at_every_object_level(tmp_path: Path) -> None:
    """§1.3b made structural: ``additionalProperties: false`` throughout, so
    no field — added at any nesting the schema admits — can carry a URL, a
    path, a host, a port, a credential or a process reference. A schema walk
    asserts the close, not a policy statement."""
    mod = _settings_module()
    schema = mod.PROVIDER_CONNECTIONS_SCHEMA

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
    # (the serial carries its own class; the key mirrors the settings schema's).
    items = schema["properties"]["connections"]["items"]["properties"]
    for name, spec in items.items():
        if spec.get("type") == "string":
            assert "pattern" in spec, name
    usb = items["usb"]["properties"]
    for name, spec in usb.items():
        if spec.get("type") == "string":
            assert "pattern" in spec, name


@pytest.mark.parametrize(
    ("mutation", "label"),
    [
        (lambda c: c.update({"url": "tcp://bench.local:5025"}), "url key"),
        (lambda c: c.update({"config_version": "2"}), "wrong config version"),
        (lambda c: c.pop("usb"), "missing usb identity"),
        (
            lambda c: c["usb"].update({"path": "/dev/ttyUSB0"}),
            "device path on an identity",
        ),
        (
            lambda c: c["usb"].update({"host": "bench.local"}),
            "host on an identity",
        ),
        (
            lambda c: c["usb"].update({"port": 5025}),
            "port on an identity",
        ),
        (
            lambda c: c["usb"].update({"token": "hunter2"}),
            "credential on an identity",
        ),
        (
            lambda c: c["usb"].update({"command": "echo hi"}),
            "process reference on an identity",
        ),
        (lambda c: c["usb"].pop("serial"), "serial is required"),
        (
            lambda c: c["usb"].update({"vendor_id": 65536}),
            "vendor id above 16 bits",
        ),
        (
            lambda c: c["usb"].update({"product_id": -1}),
            "negative product id",
        ),
        (
            lambda c: c["usb"].update({"interface": 0}),
            "interface below 1",
        ),
        (
            lambda c: c["usb"].update({"interface": 9}),
            "interface above 8",
        ),
        (
            lambda c: c["usb"].update({"serial": "spaced serial!"}),
            "serial outside the pattern",
        ),
        (
            lambda c: c["usb"].update({"serial": ""}),
            "empty serial",
        ),
        (
            lambda c: c.update({"connection_key": "PowerMeter"}),
            "malformed connection key",
        ),
    ],
)
def test_schema_refusals_are_typed(
    tmp_path: Path, mutation: Any, label: str
) -> None:
    """C3's plantation arms plus the range closures: every non-identity shape
    a planted field could take refuses ``connections_schema:``."""
    mod = _settings_module()
    _valid_connections(tmp_path)
    document = json.loads((tmp_path / "provider-connections.json").read_text())
    mutation(document["connections"][0])
    (tmp_path / "provider-connections.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="connections_schema:"):
        mod.load_provider_connections(
            tmp_path / "provider-connections.json", _registry(tmp_path)
        ), label


def test_internal_consistency_refusals(tmp_path: Path) -> None:
    mod = _settings_module()
    identity = {
        "vendor_id": 1027,
        "product_id": 24593,
        "serial": "FT-DEMO-0042",
        "interface": 1,
    }
    other = {
        "vendor_id": 1027,
        "product_id": 24593,
        "serial": "FT-DEMO-0043",
        "interface": 1,
    }
    for connections, label in (
        # an endpoint for a key the settings document never bound: dead config
        (
            [
                {
                    "connection_key": "power_meter",
                    "usb": identity,
                },
                {"connection_key": "unbound_key", "usb": other},
            ],
            "key not bound by the settings document",
        ),
        # one key carrying two identities
        (
            [
                {"connection_key": "power_meter", "usb": identity},
                {"connection_key": "power_meter", "usb": other},
            ],
            "one key two identities",
        ),
        # two keys sharing one USB identity: a USB interface is single-client
        (
            [
                {"connection_key": "power_meter", "usb": identity},
                {"connection_key": "power_meter_b", "usb": dict(identity)},
            ],
            "two keys one identity",
        ),
    ):
        path = _write_connections(tmp_path, connections)
        with pytest.raises(ValueError, match="connections_schema:"):
            mod.load_provider_connections(path, _registry(tmp_path)), label


def test_the_exact_byte_decoder_governs_the_connections_document(
    tmp_path: Path,
) -> None:
    mod = _settings_module()
    good = _valid_connections(tmp_path)
    plain = good.read_bytes()
    variants = {
        "utf8-bom": b"\xef\xbb\xbf" + plain,
        "utf16": plain.decode().encode("utf-16"),
        "duplicate-keys": plain.replace(b"{", b'{"config_version": "9",', 1),
    }
    for label, raw in variants.items():
        path = tmp_path / f"connections-{label}.json"
        path.write_bytes(raw)
        with pytest.raises(ValueError, match="connections_schema:"):
            mod.load_provider_connections(path, _registry(tmp_path)), label


def test_a_missing_document_file_refuses(tmp_path: Path) -> None:
    mod = _settings_module()
    path = _valid_connections(tmp_path)
    path.unlink()
    with pytest.raises(ValueError, match="connections_schema:"):
        mod.load_provider_connections(path, _registry(tmp_path))


# --- the presence rule at admission -------------------------------------------

FIXTURES = ROOT / "fixtures" / "execution"
NOW = "2026-10-28T00:00:00Z"


def _provider_lattice(tmp_path: Path) -> Path:
    """A full admitting lattice whose psu device is the corpus provider pair
    (the ``test_run_path_provider`` construction: proven against the parent
    commit, so the presence-rule arms below change exactly one variable)."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for name in (
        "procedure-voltage-check.json",
        "safety-policy.json",
        "bench.json",
        "run-binding.json",
        "commissioning.json",
        "package-lock.json",
        "descriptor-sim-controller.json",
    ):
        (fixtures / name).write_bytes((FIXTURES / name).read_bytes())
    _valid_settings(fixtures)
    descriptor = json.loads((EXAMPLES / "reference-hid-meter.json").read_text())
    contract_raw = (fixtures / "reference-provider.json").read_bytes()
    descriptor["transport"]["provider"]["sha256"] = hashlib.sha256(
        contract_raw
    ).hexdigest()
    (fixtures / "descriptor-provider.json").write_text(json.dumps(descriptor, indent=2))
    bench = json.loads((fixtures / "bench.json").read_text())
    raw = (fixtures / "descriptor-provider.json").read_bytes()
    for device in bench["devices"]:
        if str(device["id"]) == "psu":
            device["descriptor"]["id"] = descriptor["id"]
            device["descriptor"]["version"] = descriptor["descriptor_version"]
            device["descriptor"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (fixtures / "bench.json").write_text(json.dumps(bench, indent=2))
    bench_sha = hashlib.sha256((fixtures / "bench.json").read_bytes()).hexdigest()
    commissioning = json.loads((fixtures / "commissioning.json").read_text())
    commissioning["bench"]["sha256"] = bench_sha
    (fixtures / "commissioning.json").write_text(json.dumps(commissioning, indent=2))
    commissioning_sha = hashlib.sha256(
        (fixtures / "commissioning.json").read_bytes()
    ).hexdigest()
    binding = json.loads((fixtures / "run-binding.json").read_text())
    binding["bench"]["sha256"] = bench_sha
    binding["commissioning"]["sha256"] = commissioning_sha
    (fixtures / "run-binding.json").write_text(json.dumps(binding, indent=2))
    return fixtures


def _admit(fixtures: Path) -> Any:
    documents = _documents_module()
    return documents.admit_documents(
        procedure_path=fixtures / "procedure-voltage-check.json",
        policy_path=fixtures / "safety-policy.json",
        bench_path=fixtures / "bench.json",
        binding_path=fixtures / "run-binding.json",
        commissioning_path=fixtures / "commissioning.json",
        descriptor_paths={
            "psu": fixtures / "descriptor-provider.json",
            "controller": fixtures / "descriptor-sim-controller.json",
        },
        provider_settings=fixtures / "transport-settings.json",
        provider_connections=(
            fixtures / "provider-connections.json"
            if (fixtures / "provider-connections.json").is_file()
            else None
        ),
        now_wall=NOW,
    )


def test_the_lattice_admits_with_the_endpoints_document(tmp_path: Path) -> None:
    """The healthy path: settings + endpoints + provider descriptor admit."""
    fixtures = _provider_lattice(tmp_path)
    _valid_connections(fixtures)
    docs = _admit(fixtures)
    assert docs.descriptors["psu"]["id"] == "dev.local.reference-hid-meter"


def test_settings_binding_connections_require_the_endpoints_document(
    tmp_path: Path,
) -> None:
    """THE presence rule (design §1.3b): a settings document with connections
    and no endpoints document refuses at admission — on the parent commit the
    same lattice admits silently, which is the RED this test pins."""
    fixtures = _provider_lattice(tmp_path)
    assert not (fixtures / "provider-connections.json").exists()
    with pytest.raises(ValueError, match="connections_schema:"):
        _admit(fixtures)


def test_connectionless_settings_do_not_require_the_document(
    tmp_path: Path,
) -> None:
    """The presence rule's other half: a settings document binding NO
    connection never requires the endpoints document (the document loads
    only beside a settings file that binds connections — maintainer ruling
    3). The refusal that fires names the connection axis, never the
    endpoints document."""
    fixtures = _provider_lattice(tmp_path)
    settings = json.loads((fixtures / "transport-settings.json").read_text())
    settings["connections"] = []
    (fixtures / "transport-settings.json").write_text(json.dumps(settings))
    with pytest.raises(ValueError) as refused:
        _admit(fixtures)
    assert "provider_not_admitted:" in str(refused.value)
    assert "provider-connections.json" not in str(refused.value)
