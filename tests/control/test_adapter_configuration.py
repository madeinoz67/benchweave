"""Adapter-configuration admission arms (issue #447).

The gateway admission mirror ``_verify_adapter_configuration`` — a
structural sibling of ``_verify_provider_pin`` minus the exact-byte
decode (a configuration file is opaque bytes, the inventory posture, not
a document posture; the CON-1 family seam named in the mirror's
docstring) — exercised through the REAL ``admit_documents`` with the
execution fixture lattice, the way ``test_documents_provider.py``
exercises the provider-pin family:

- **M-A**: a 0.2.3-pinned descriptor carrying
  ``configuration.files = [{id, path, sha256}]`` with the file present at
  the pinned digest in its package admits with zero refusals, and the
  CON-10 projection carries ``adapter_configuration.files`` equal to the
  declared triples;
- **M-B**: the same package with the referenced file's bytes altered
  refuses ``adapter_config_hash_mismatch:`` (the pin is load-bearing);
- **M-C posture negatives**: ``../escape.bin``, an absolute path, a
  colon-bearing path and a symlinked target each refuse; a duplicate id
  and a duplicate path refuse (S21); the ``adapter_config_invalid:`` /
  ``adapter_config_missing:`` prefixes split shape from resolution.

The RED side (disclosed in the RED commit): pre-change the descriptor
with the field present refused on ``additionalProperties`` at
``$.integration.adapter`` — the schema gate, the design's own named RED
— so every arm here failed on the schema refusal text before the
mechanism existed, and passes only when the schema admits the field AND
the mirror enforces the pin/posture.

What this does NOT catch: the loader's inventory resolution (the
double-pin drift and not-in-bundle refusals live in
``tests/integration/test_adapter_configuration_loading.py``) and the
schema shape (the vectors file).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from _harness import FIXTURES, ROOT

from benchweave.control.documents import AdmissionRejected, admit_documents

EXAMPLES = ROOT / "standards" / "otdp" / "0.2.3" / "examples"
NOW_WALL = "2026-10-13T00:00:00Z"

IMAGE_BYTES = b"BW-SYNTHETIC-IMAGE-v1" + bytes(range(64)) * 4


def _base_descriptor() -> dict[str, Any]:
    """The corpus's class-logic_analyser fixture, re-pinned to the active
    0.2.3 version and carrying one declared configuration triple."""
    manifest = json.loads(
        (ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
    )
    version = next(
        entry["version"] for entry in manifest["standards"] if entry["id"] == "otdp"
    )
    body: dict[str, Any] = json.loads(
        (EXAMPLES / "class-logic_analyser.json").read_text(encoding="utf-8")
    )
    body["otdp_version"] = version
    body["integration"]["adapter"]["configuration"] = {
        "files": [
            {
                "id": "bench_image",
                "path": "reference-analyzer-image.bin",
                "sha256": hashlib.sha256(IMAGE_BYTES).hexdigest(),
            }
        ]
    }
    return body


def _write_package(package: Path, descriptor: dict[str, Any]) -> Path:
    """Write the package: the descriptor plus any declared file at the
    pinned digest; return the descriptor path."""
    configuration = (
        descriptor.get("integration", {}).get("adapter", {}).get("configuration")
    )
    if configuration:
        triple = configuration["files"][0]
        target = package / triple["path"]
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(IMAGE_BYTES)
    (package / "descriptor.json").write_text(json.dumps(descriptor, indent=2) + "\n")
    return package / "descriptor.json"


def _admit_package(tmp_path: Path, descriptor_path: Path) -> dict[str, Any]:
    """Admit the fixture lattice with the psu slot at ``descriptor_path``;
    return the admitted projection for the psu device."""
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
    return admit_documents(
        procedure_path=procedure_path,
        policy_path=policy_path,
        bench_path=bench_path,
        binding_path=binding_path,
        commissioning_path=commissioning_path,
        descriptor_paths=descriptor_paths,
    ).descriptors["psu"]


def _admit_refusal(tmp_path: Path, descriptor_path: Path) -> str:
    try:
        _admit_package(tmp_path, descriptor_path)
    except AdmissionRejected as exc:
        return str(exc)
    raise AssertionError("admission should have refused")


# --- M-A: declarative validity and the projection -------------------------


def test_configured_package_admits_and_projects(tmp_path: Path) -> None:
    """M-A: the file present at the pinned digest admits; the CON-10 view
    carries the declared triples verbatim."""
    package = tmp_path / "clean"
    package.mkdir()
    descriptor = _base_descriptor()
    slot = _write_package(package, descriptor)
    view = _admit_package(tmp_path, slot)
    assert view["adapter_configuration"] == {
        "files": [
            {
                "id": "bench_image",
                "path": "reference-analyzer-image.bin",
                "sha256": hashlib.sha256(IMAGE_BYTES).hexdigest(),
            }
        ]
    }


def test_configuration_absent_omits_projection_key(tmp_path: Path) -> None:
    """No declaration projects nothing — present only when declared, the
    capture-keys posture."""
    package = tmp_path / "plain"
    package.mkdir()
    descriptor = _base_descriptor()
    del descriptor["integration"]["adapter"]["configuration"]
    slot = _write_package(package, descriptor)
    view = _admit_package(tmp_path, slot)
    assert "adapter_configuration" not in view


# --- M-B: the digest negative control -------------------------------------


def test_altered_file_refuses_hash_mismatch(tmp_path: Path) -> None:
    """M-B kill control: the pin is load-bearing — altered bytes refuse
    with the typed prefix at admission."""
    package = tmp_path / "tampered"
    package.mkdir()
    descriptor = _base_descriptor()
    slot = _write_package(package, descriptor)
    triple = descriptor["integration"]["adapter"]["configuration"]["files"][0]
    (package / triple["path"]).write_bytes(b"tampered bytes")
    message = _admit_refusal(tmp_path, slot)
    assert "adapter_config_hash_mismatch:" in message, message


# --- M-C: posture negatives ------------------------------------------------


def test_escaping_path_refuses(tmp_path: Path) -> None:
    package = tmp_path / "escape"
    package.mkdir()
    descriptor = _base_descriptor()
    descriptor["integration"]["adapter"]["configuration"]["files"][0]["path"] = (
        "../escape.bin"
    )
    slot = _write_package(package, descriptor)
    message = _admit_refusal(tmp_path, slot)
    assert "adapter_config_invalid:" in message, message


def test_absolute_path_refuses(tmp_path: Path) -> None:
    package = tmp_path / "absolute"
    package.mkdir()
    descriptor = _base_descriptor()
    descriptor["integration"]["adapter"]["configuration"]["files"][0]["path"] = (
        "/etc/image.bin"
    )
    slot = _write_package(package, descriptor)
    message = _admit_refusal(tmp_path, slot)
    assert "adapter_config_invalid:" in message, message


def test_colon_path_refuses(tmp_path: Path) -> None:
    package = tmp_path / "colon"
    package.mkdir()
    descriptor = _base_descriptor()
    descriptor["integration"]["adapter"]["configuration"]["files"][0]["path"] = (
        "C:device-image.bin"
    )
    slot = _write_package(package, descriptor)
    message = _admit_refusal(tmp_path, slot)
    assert "adapter_config_invalid:" in message, message


def test_symlinked_target_refuses_no_follow(tmp_path: Path) -> None:
    """Strict no-follow: any symlink on the path refuses, even one that
    never leaves the package (the provider-pin posture, held knowingly)."""
    package = tmp_path / "symlinked"
    package.mkdir()
    descriptor = _base_descriptor()
    triple = descriptor["integration"]["adapter"]["configuration"]["files"][0]
    real = package / "real-image.bin"
    real.write_bytes(IMAGE_BYTES)
    link = package / "linked-image.bin"
    os.symlink(real.name, link)
    triple["path"] = link.name
    triple["sha256"] = hashlib.sha256(IMAGE_BYTES).hexdigest()
    (package / "descriptor.json").write_text(json.dumps(descriptor, indent=2) + "\n")
    message = _admit_refusal(tmp_path, package / "descriptor.json")
    assert "adapter_config_missing:" in message and "symlink" in message, message


def test_absent_file_refuses_missing(tmp_path: Path) -> None:
    package = tmp_path / "absent"
    package.mkdir()
    descriptor = _base_descriptor()
    descriptor["integration"]["adapter"]["configuration"]["files"][0]["path"] = (
        "not-there.bin"
    )
    slot = _write_package(package, descriptor)
    message = _admit_refusal(tmp_path, slot)
    assert "adapter_config_missing:" in message, message


def test_duplicate_id_refuses(tmp_path: Path) -> None:
    """S21 uniqueness: two triples sharing an id refuse even when the
    paths differ (byte-distinct, so the schema's uniqueItems cannot see
    them — the mirror is the enforcement point)."""
    package = tmp_path / "dupid"
    package.mkdir()
    descriptor = _base_descriptor()
    files = descriptor["integration"]["adapter"]["configuration"]["files"]
    files.append(
        {
            "id": "bench_image",
            "path": "reference-analyzer-overlay.bin",
            "sha256": hashlib.sha256(b"other bytes").hexdigest(),
        }
    )
    (package / "reference-analyzer-overlay.bin").write_bytes(b"other bytes")
    slot = _write_package(package, descriptor)
    message = _admit_refusal(tmp_path, slot)
    assert "adapter_config_invalid:" in message and "unique" in message, message


def test_duplicate_path_refuses(tmp_path: Path) -> None:
    """S21 uniqueness: two triples sharing a path refuse even when the
    ids differ."""
    package = tmp_path / "duppath"
    package.mkdir()
    descriptor = _base_descriptor()
    files = descriptor["integration"]["adapter"]["configuration"]["files"]
    files.append(
        {
            "id": "bench_overlay",
            "path": "reference-analyzer-image.bin",
            "sha256": hashlib.sha256(IMAGE_BYTES).hexdigest(),
        }
    )
    slot = _write_package(package, descriptor)
    message = _admit_refusal(tmp_path, slot)
    assert "adapter_config_invalid:" in message and "unique" in message, message


def test_oversized_file_refuses(tmp_path: Path) -> None:
    """The bounded-read cap, mirrored from the provider lane (a shared
    resource bound, not a semantic disagreement)."""
    package = tmp_path / "oversized"
    package.mkdir()
    descriptor = _base_descriptor()
    triple = descriptor["integration"]["adapter"]["configuration"]["files"][0]
    big = package / "big-image.bin"
    big.write_bytes(b"x" * 5_000_000)
    triple["path"] = "big-image.bin"
    triple["sha256"] = hashlib.sha256(b"x" * 5_000_000).hexdigest()
    (package / "descriptor.json").write_text(json.dumps(descriptor, indent=2) + "\n")
    message = _admit_refusal(tmp_path, package / "descriptor.json")
    assert "adapter_config_missing:" in message and "cap" in message, message
