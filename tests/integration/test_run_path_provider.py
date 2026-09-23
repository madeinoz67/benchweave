"""The run path admits a provider-declaring lattice (fold wave B).

The run factory's spool (``app._spool_documents``) resolves every pinned
document from the ContentStore — but a provider descriptor's pin is
DESCRIPTOR-relative, and the spooled descriptor lives at a new filename in
a fresh directory, so the pinned contract must be spooled BESIDE it for
admission to resolve the pin at all; the fixtures' ``transport-settings.json``
and a wall stamp must thread through the same call. Before the fold, the
run path could never admit a provider descriptor and its refusals
misattributed the cause ("does not name a contained regular file" for a
package that has the file; "no transport settings document is configured"
with one configured).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from benchweave.content.store import ContentStore
from benchweave.control.documents import admit_documents
from benchweave.interfaces import app as app_module
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
EXAMPLES = ROOT / "standards" / "otdp" / "0.2.2" / "examples"
NOW = "2026-09-23T00:00:00Z"


def _provider_fixtures(tmp_path: Path) -> Path:
    """A fixtures lattice whose psu device is the corpus provider pair."""
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
    # The provider package: descriptor + pinned contract + settings, the
    # pin covering the contract bytes actually written.
    descriptor = json.loads((EXAMPLES / "reference-hid-meter.json").read_text())
    contract_raw = (EXAMPLES / "reference-provider.json").read_bytes()
    (fixtures / "reference-provider.json").write_bytes(contract_raw)
    descriptor["transport"]["provider"]["sha256"] = hashlib.sha256(
        contract_raw
    ).hexdigest()
    (fixtures / "descriptor-provider.json").write_text(json.dumps(descriptor, indent=2))
    contract = json.loads(contract_raw)
    settings = {
        "config_version": "1",
        "admitted": [
            {
                "id": contract["id"],
                "version": contract["version"],
                "sha256": hashlib.sha256(contract_raw).hexdigest(),
                "feature_id": contract["feature_id"],
                "document": "reference-provider.json",
            }
        ],
        "connections": [
            {"connection_key": "power_meter", "provider_id": contract["id"]}
        ],
    }
    (fixtures / "transport-settings.json").write_text(json.dumps(settings, indent=2))
    # Repoint the bench's psu pin at the provider descriptor, then cascade
    # the digest lattice (commissioning pins bench; binding pins both).
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


def _cached(fixtures: Path, tmp_path: Path) -> tuple[ContentStore, dict[str, Any]]:
    """Cache the binding-pinned lattice in a ContentStore; return the
    binding_ref the run factory would receive."""
    store = Store.open(tmp_path / "run.db")
    content = ContentStore(store)
    for name in (
        "procedure-voltage-check.json",
        "safety-policy.json",
        "bench.json",
        "run-binding.json",
        "commissioning.json",
        "descriptor-provider.json",
        "descriptor-sim-controller.json",
    ):
        raw = (fixtures / name).read_bytes()
        parsed = json.loads(raw)
        content.put_document(raw, hashlib.sha256(raw).hexdigest(), parsed, "urn:stg:admitted", NOW)
    binding_sha = hashlib.sha256((fixtures / "run-binding.json").read_bytes()).hexdigest()
    return content, {"sha256": binding_sha}


def test_the_run_path_admits_a_provider_descriptor(tmp_path: Path) -> None:
    """The spool resolves the pinned contract beside the spooled descriptor
    and threads the fixtures' settings, so run admission works as
    advertised (fold wave B's preference: make it work)."""
    fixtures = _provider_fixtures(tmp_path)
    content, binding_ref = _cached(fixtures, tmp_path)
    spool = tmp_path / "spool"
    spool.mkdir()
    kwargs = app_module._spool_documents(content, binding_ref, fixtures, spool)
    assert kwargs["provider_settings"] == fixtures / "transport-settings.json"
    docs = admit_documents(**kwargs, now_wall=NOW)
    view = docs.descriptors["psu"]
    assert view["id"] == "dev.local.reference-hid-meter"


def test_the_spooled_pin_resolves_inside_the_spool(tmp_path: Path) -> None:
    """The pinned contract lands at the PINNED relative path beside the
    spooled descriptor, its bytes the verified originals."""
    fixtures = _provider_fixtures(tmp_path)
    content, binding_ref = _cached(fixtures, tmp_path)
    spool = tmp_path / "spool"
    spool.mkdir()
    app_module._spool_documents(content, binding_ref, fixtures, spool)
    descriptor = json.loads(
        (fixtures / "descriptor-provider.json").read_text()
    )
    pinned = spool / descriptor["transport"]["provider"]["path"]
    assert pinned.is_file(), "the pinned contract was not spooled beside the descriptor"
    original = (fixtures / descriptor["transport"]["provider"]["path"]).read_bytes()
    assert pinned.read_bytes() == original
    assert (
        hashlib.sha256(original).hexdigest()
        == descriptor["transport"]["provider"]["sha256"]
    )
