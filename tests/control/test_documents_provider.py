"""Provider-declaring descriptor admission: the pin-mirror arm set.

The census (``tests/sdk/test_descriptor_equivalence.py``) pins gateway/SDK
AGREEMENT over the provider lattice and the gateway-only admission axes;
this module pins the gateway's own beyond-schema mirror rows the SDK lane
shares — ``_verify_provider_pin`` (path posture, hash, exact-byte decode,
schema, grammar meta-validation, kind uniqueness, reserved-seven
disjointness, identity equalities, declaration agreement) — plus the
hand-carried constants' self-arms (the reserved-seven spelling test and
the corpus-known derivation count), each through the REAL
``admit_documents`` with a settings document admitting the package's
triple, never the mirror functions directly.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest
from _harness import FIXTURES, ROOT

from benchweave.control import documents as documents_module
from benchweave.control.documents import AdmissionRejected

EXAMPLES = ROOT / "standards" / "otdp" / "0.2.2" / "examples"
NOW_WALL = "2026-09-23T00:00:00Z"


def _package_pair(tmp_path: Path, name: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """``tmp_path/name/`` holding the corpus reference pair; writable copies."""
    package = tmp_path / name
    package.mkdir(parents=True)
    descriptor = json.loads((EXAMPLES / "reference-hid-meter.json").read_text())
    contract = json.loads((EXAMPLES / "reference-provider.json").read_text())
    return package, descriptor, contract


def _write_package(
    package: Path,
    descriptor: dict[str, Any],
    contract: dict[str, Any] | None,
    *,
    recompute_digest: bool = True,
) -> Path:
    """Write the pair; return the descriptor path. Mirrors the census builder."""
    if contract is not None:
        raw = (json.dumps(contract, indent=2) + "\n").encode()
        (package / descriptor["transport"]["provider"]["path"]).write_bytes(raw)
        if recompute_digest:
            descriptor["transport"]["provider"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (package / "descriptor.json").write_text(json.dumps(descriptor, indent=2) + "\n")
    return package / "descriptor.json"


def _settings_for(package: Path) -> Path:
    raw = (package / "reference-provider.json").read_bytes()
    contract = json.loads(raw)
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


def _admit_package(
    tmp_path: Path,
    descriptor_path: Path,
    settings: Path | None,
    *,
    now_wall: str | None = NOW_WALL,
) -> None:
    """Admit the fixture lattice with the psu slot at ``descriptor_path``."""
    filenames = {
        "procedure": "procedure-voltage-check.json",
        "policy": "safety-policy.json",
        "bench": "bench.json",
        "binding": "run-binding.json",
        "commissioning": "commissioning.json",
    }
    graph = {
        name: json.loads((FIXTURES / filename).read_text())
        for name, filename in filenames.items()
    }
    descriptor_paths = {
        "psu": descriptor_path,
        "controller": FIXTURES / "descriptor-sim-controller.json",
    }
    spool = tmp_path / "spool"
    spool.mkdir(exist_ok=True)
    policy_path = spool / "safety-policy.json"
    policy_path.write_text(json.dumps(graph["policy"], indent=2))
    lock_path = spool / "package-lock.json"
    lock_path.write_bytes((FIXTURES / "package-lock.json").read_bytes())
    bench = graph["bench"]
    for device in bench["devices"]:
        raw = descriptor_paths[str(device["id"])].read_bytes()
        doc = json.loads(raw)
        device["descriptor"]["id"] = doc["id"]
        device["descriptor"]["version"] = doc.get(
            "descriptor_version", doc.get("version")
        )
        device["descriptor"]["sha256"] = hashlib.sha256(raw).hexdigest()
    bench["policy"]["sha256"] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    bench["package_lock"]["sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    bench_path = spool / "bench.json"
    bench_path.write_text(json.dumps(bench, indent=2))
    procedure_path = spool / "procedure.json"
    procedure_path.write_text(json.dumps(graph["procedure"], indent=2))
    commissioning = graph["commissioning"]
    for name, path in (
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lock_path),
    ):
        commissioning[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for reference in commissioning["procedure_refs"]:
        reference["sha256"] = hashlib.sha256(procedure_path.read_bytes()).hexdigest()
    commissioning_path = spool / "commissioning.json"
    commissioning_path.write_text(json.dumps(commissioning, indent=2))
    binding = graph["binding"]
    for name, path in (
        ("procedure", procedure_path),
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lock_path),
        ("commissioning", commissioning_path),
    ):
        binding[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    binding_path = spool / "run-binding.json"
    binding_path.write_text(json.dumps(binding, indent=2))
    documents_module.admit_documents(
        procedure_path=procedure_path,
        policy_path=policy_path,
        bench_path=bench_path,
        binding_path=binding_path,
        commissioning_path=commissioning_path,
        descriptor_paths=descriptor_paths,
        provider_settings=settings,
        now_wall=now_wall,
    )


def _admit_refusal(
    tmp_path: Path, descriptor_path: Path, settings: Path | None
) -> str:
    with pytest.raises(AdmissionRejected) as excinfo:
        _admit_package(tmp_path, descriptor_path, settings)
    return str(excinfo.value)


# --- the pin mirror: posture, hash, decode, schema, beyond-schema --------


def test_a_clean_pair_with_settings_admits(tmp_path: Path) -> None:
    package, descriptor, contract = _package_pair(tmp_path, "clean")
    slot = _write_package(package, descriptor, contract)
    _admit_package(tmp_path, slot, _settings_for(package))


def test_pin_digest_mismatch_refuses(tmp_path: Path) -> None:
    package, descriptor, contract = _package_pair(tmp_path, "badhash")
    descriptor["transport"]["provider"]["sha256"] = "b" * 64
    slot = _write_package(package, descriptor, contract, recompute_digest=False)
    message = _admit_refusal(tmp_path, slot, _settings_for(package))
    assert "provider_contract_hash_mismatch:" in message, message


def test_escaping_pin_path_refuses(tmp_path: Path) -> None:
    package, descriptor, contract = _package_pair(tmp_path, "escape")
    descriptor["transport"]["provider"]["path"] = "../outside.json"
    slot = _write_package(package, descriptor, contract)
    # No settings: the pin refuses before the admission row reads settings
    # (the arm is the pin's, not admission's).
    message = _admit_refusal(tmp_path, slot, None)
    assert "provider_contract_missing:" in message, message


def test_symlinked_pin_refuses_no_follow(tmp_path: Path) -> None:
    """The SDK's stricter posture, held on BOTH sides knowingly (the record's
    disclosed divergence): any symlink on the pin path refuses, even one
    that never leaves the descriptor's own package."""
    package, descriptor, contract = _package_pair(tmp_path, "symlinked")
    real = package / "real-provider.json"
    real.write_text(json.dumps(contract, indent=2) + "\n")
    link = package / "linked-provider.json"
    os.symlink("real-provider.json", link)
    descriptor["transport"]["provider"]["path"] = "linked-provider.json"
    descriptor["transport"]["provider"]["sha256"] = hashlib.sha256(
        link.read_bytes()
    ).hexdigest()
    (package / "descriptor.json").write_text(json.dumps(descriptor, indent=2) + "\n")
    # No settings: the no-follow refusal is the pin's own (admission reads
    # nothing when the pin already refused).
    message = _admit_refusal(tmp_path, package / "descriptor.json", None)
    assert "provider_contract_missing:" in message and "symlink" in message, message


def test_declaration_agreement_is_enforced(tmp_path: Path) -> None:
    """The AR-6 SDK-added fourth equality, kept gateway-side knowingly: the
    pinned contract must declare the descriptor's provider identity."""
    package, descriptor, contract = _package_pair(tmp_path, "disagree")
    contract["id"] = "urn:otdp:transport-provider:other-lane:1.0.0"
    contract["feature_id"] = "otdp.transport.other-lane/1.0.0"
    slot = _write_package(package, descriptor, contract)
    settings = _settings_for(package)  # admits the WRITTEN bytes' triple
    message = _admit_refusal(tmp_path, slot, settings)
    assert "provider_contract_invalid:" in message, message


@pytest.mark.parametrize(
    ("mutate", "label"),
    [
        # a reserved generic kind reused: extends the table, never shadows it
        (
            lambda c: c["transaction_grammar"][0].update({"kind": "i2c_transfer"}),
            "reserved kind shadow",
        ),
        # two entries, same kind string, different limits: a duplicate, not
        # two kinds (uniqueItems refuses byte-identical entries only)
        (
            lambda c: c["transaction_grammar"].append(
                dict(c["transaction_grammar"][0], limits={"other": 1})
            ),
            "duplicate kind string",
        ),
        # grammar subschema that is not a valid Draft 2020-12 schema
        (
            lambda c: c["transaction_grammar"][0]["request_schema"].update(
                {"type": "nonsense"}
            ),
            "invalid subschema",
        ),
        # the three identity equalities: urn-embedded version disagreement
        (
            lambda c: c.update({"id": "urn:otdp:transport-provider:reference-hid:2.0.0"}),
            "urn version disagreement",
        ),
        # feature_id name segment != urn name segment
        (
            lambda c: c.update(
                {"feature_id": "otdp.transport.other-name/1.0.0"}
            ),
            "name segment disagreement",
        ),
    ],
)
def test_beyond_schema_contract_rows_refuse(
    tmp_path: Path, mutate: Any, label: str
) -> None:
    package, descriptor, contract = _package_pair(tmp_path, label.replace(" ", "-"))
    mutate(contract)
    slot = _write_package(package, descriptor, contract)
    message = _admit_refusal(tmp_path, slot, _settings_for(package))
    assert "provider_contract_invalid:" in message, f"{label}: {message}"


# --- the hand-carried constants' self-arms -------------------------------

#: The generic §8.1 transfer kinds, spelled from the corpus text
#: (transport-providers §3 names the seven verbatim) — the gateway mirror's
#: frozenset is prose-carried, so this pin makes a silent shrink fail here.
#: Extends the record's deferral-8 posture to both sides (the SDK carries
#: the same spelling test).
_RESERVED_KINDS = frozenset(
    {
        "stream_send",
        "stream_receive",
        "stream_exchange",
        "can_receive",
        "can_send",
        "i2c_transfer",
        "spi_transfer",
    }
)


def test_reserved_transfer_kinds_are_pinned_from_the_corpus_text() -> None:
    assert documents_module._RESERVED_TRANSFER_KINDS == _RESERVED_KINDS


def test_corpus_known_features_derive_from_the_vendored_tree() -> None:
    """The gateway derivation, not the SDK's: five lane consts + the twelve
    catalog profile ids at 0.2.2 — never hand-listed (the census pins the
    two derivations equal across lanes)."""
    known = documents_module._corpus_known_otdp_features()
    catalog = json.loads(
        (ROOT / "standards" / "otdp" / "0.2.2" / "device-profile-catalog.json").read_text()
    )
    lanes = {
        "otdp.core/0.1.0",
        "otdp.adapter/0.1.0",
        "otdp.measurement/0.1.0",
        "otdp.passive_can/0.1.0",
        "otdp.profile_actions/0.1.0",
    }
    assert known == frozenset(lanes | {p["id"] for p in catalog["profiles"]})
    assert len(known) == 17
