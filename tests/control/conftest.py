"""Shared harness for derivation admission/executor control tests.

Re-admits the execution fixture set with the psu descriptor (and optionally
the procedure) mutated, rebuilding the digest pin lattice in dependency
order so structural admission succeeds and only the stage under test can
reject — the ``readmit_mutated`` pattern from
``tests/integration/test_procedures.py``, kept local because the tests
directories are not an importable package.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from benchweave.control.documents import AdmittedDocuments, admit_documents

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
DESCRIPTORS = {
    "psu": FIXTURES / "descriptor-sim-psu.json",
    "controller": FIXTURES / "descriptor-sim-controller.json",
}

Graph = dict[str, Any]


def readmit_mutated(
    tmp_path: Path, mutate: Callable[[Graph], None]
) -> AdmittedDocuments:
    """Admit the fixture set with one mutation, every pin repointed."""

    filenames = {
        "procedure": "procedure-voltage-check.json",
        "policy": "safety-policy.json",
        "bench": "bench.json",
        "binding": "run-binding.json",
        "commissioning": "commissioning.json",
    }
    graph: Graph = {
        name: json.loads((FIXTURES / filename).read_text())
        for name, filename in filenames.items()
    }
    graph["descriptors"] = {
        device_id: json.loads(path.read_text()) for device_id, path in DESCRIPTORS.items()
    }
    mutate(graph)

    descriptor_paths: dict[str, Path] = {}
    for device_id, descriptor in graph["descriptors"].items():
        path = tmp_path / f"descriptor-{device_id}.json"
        path.write_text(json.dumps(descriptor, indent=2))
        descriptor_paths[device_id] = path
    policy_path = tmp_path / "safety-policy.json"
    policy_path.write_text(json.dumps(graph["policy"], indent=2))
    lock_path = tmp_path / "package-lock.json"
    lock_path.write_bytes((FIXTURES / "package-lock.json").read_bytes())

    bench = graph["bench"]
    for device in bench["devices"]:
        device["descriptor"]["sha256"] = hashlib.sha256(
            descriptor_paths[str(device["id"])].read_bytes()
        ).hexdigest()
    bench["policy"]["sha256"] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    bench["package_lock"]["sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    bench_path = tmp_path / "bench.json"
    bench_path.write_text(json.dumps(bench, indent=2))

    procedure_path = tmp_path / "procedure.json"
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
    commissioning_path = tmp_path / "commissioning.json"
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
    binding_path = tmp_path / "run-binding.json"
    binding_path.write_text(json.dumps(binding, indent=2))

    return admit_documents(
        procedure_path=procedure_path,
        policy_path=policy_path,
        bench_path=bench_path,
        binding_path=binding_path,
        commissioning_path=commissioning_path,
        descriptor_paths=descriptor_paths,
    )
