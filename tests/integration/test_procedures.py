"""WP05 admission of the executable fixture document set.

Proves the admission properties this work package owns: the fixture corpus
admits through schema validation plus the full digest pin lattice, any byte
tamper surfaces as a machine-matchable ``digest_mismatch``, and any structural
drift (unknown fields, duplicate keys, nonfinite numbers) surfaces as
``schema`` — inherited from the exact-byte decoder and the vendored
execution-v1.0.0 schemas. On top of structure, the semantic stage enforces
step-ID uniqueness, lexical scoping of result references, ``$stg_issue``
placement at descriptor-marked issued fields, and the budget bounds (worst-case
body, energised time, commissioning deadline). Profile satisfaction and
binding completeness belong to later stages and are not exercised here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from benchweave.control.documents import AdmissionRejected, AdmittedDocuments, admit_documents
from benchweave.control.semantics import check_semantics, worst_case_body_ms

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
DESCRIPTORS = {
    "psu": FIXTURES / "descriptor-sim-psu.json",
    "controller": FIXTURES / "descriptor-sim-controller.json",
}
NOW_WALL = "2026-09-11T00:00:00Z"


def admit() -> AdmittedDocuments:
    return admit_documents(
        procedure_path=FIXTURES / "procedure-voltage-check.json",
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=FIXTURES / "run-binding.json",
        commissioning_path=FIXTURES / "commissioning.json",
        descriptor_paths=DESCRIPTORS,
    )


def readmit_with_procedure(
    tmp_path: Path, mutate_fn: Callable[[dict[str, Any]], None]
) -> AdmittedDocuments:
    """Admit the fixture set with a mutated procedure, pins repointed.

    Mutating the procedure bytes invalidates the two procedure pins (the
    binding's ``procedure.sha256`` and the commissioning's
    ``procedure_refs`` entry); rewriting the commissioning then invalidates the
    binding's ``commissioning`` pin. All three are repointed at the rewritten
    documents so structural admission succeeds and only the semantic stage can
    reject. Bench, policy, descriptors and package lock stay original.
    """
    procedure = json.loads((FIXTURES / "procedure-voltage-check.json").read_text())
    mutate_fn(procedure)
    procedure_path = tmp_path / "procedure.json"
    procedure_path.write_text(json.dumps(procedure, indent=2))
    procedure_digest = hashlib.sha256(procedure_path.read_bytes()).hexdigest()

    commissioning = json.loads((FIXTURES / "commissioning.json").read_text())
    for ref in commissioning["procedure_refs"]:
        if ref["id"] == procedure["id"] and ref["version"] == procedure["version"]:
            ref["sha256"] = procedure_digest
    commissioning_path = tmp_path / "commissioning.json"
    commissioning_path.write_text(json.dumps(commissioning, indent=2))

    binding = json.loads((FIXTURES / "run-binding.json").read_text())
    binding["procedure"]["sha256"] = procedure_digest
    binding["commissioning"]["sha256"] = hashlib.sha256(
        commissioning_path.read_bytes()
    ).hexdigest()
    binding_path = tmp_path / "run-binding.json"
    binding_path.write_text(json.dumps(binding, indent=2))

    return admit_documents(
        procedure_path=procedure_path,
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=binding_path,
        commissioning_path=commissioning_path,
        descriptor_paths=DESCRIPTORS,
    )


def _root_step(procedure: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(step for step in procedure["steps"] if step["id"] == step_id)


def _loop_step(procedure: dict[str, Any], step_id: str) -> dict[str, Any]:
    loop = _root_step(procedure, "loop")
    return next(step for step in loop["steps"] if step["id"] == step_id)


def _admit_tampered_procedure(text: str, tmp_path: Path) -> None:
    tampered = tmp_path / "procedure.json"
    tampered.write_text(text)
    admit_documents(
        procedure_path=tampered,
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=FIXTURES / "run-binding.json",
        commissioning_path=FIXTURES / "commissioning.json",
        descriptor_paths=DESCRIPTORS,
    )


def test_fixtures_admit() -> None:
    docs = admit()
    assert docs.procedure["id"] == "voltage-check"
    assert docs.binding["request_id"] == "req-voltage-check-1"


def test_digest_mismatch_rejected(tmp_path: Path) -> None:
    tampered = tmp_path / "procedure.json"
    tampered.write_text((FIXTURES / "procedure-voltage-check.json").read_text()
                        .replace('"voltage_v": 5.0', '"voltage_v": 5.1'))
    with pytest.raises(AdmissionRejected, match="digest_mismatch"):
        admit_documents(
            procedure_path=tampered,
            policy_path=FIXTURES / "safety-policy.json",
            bench_path=FIXTURES / "bench.json",
            binding_path=FIXTURES / "run-binding.json",
            commissioning_path=FIXTURES / "commissioning.json",
            descriptor_paths=DESCRIPTORS,
        )


def test_unknown_field_rejected_as_schema_error(tmp_path: Path) -> None:
    original = (FIXTURES / "procedure-voltage-check.json").read_text()
    with pytest.raises(AdmissionRejected, match=r"^schema:"):
        _admit_tampered_procedure(original[:-1] + ',"unexpected": 1}', tmp_path)


def test_duplicate_key_rejected_by_decoder(tmp_path: Path) -> None:
    original = (FIXTURES / "procedure-voltage-check.json").read_text()
    with pytest.raises(AdmissionRejected, match="schema: .*duplicate_key"):
        _admit_tampered_procedure(
            original.replace('"id": "voltage-check",', '"id": "voltage-check", "id": "clone",'),
            tmp_path,
        )


def test_nonfinite_number_rejected_by_decoder(tmp_path: Path) -> None:
    original = (FIXTURES / "procedure-voltage-check.json").read_text()
    with pytest.raises(AdmissionRejected, match="schema: .*nonfinite_number"):
        _admit_tampered_procedure(
            original.replace('"voltage_v": 5.0', '"voltage_v": 1e999'), tmp_path
        )


def test_missing_descriptor_pin_rejected() -> None:
    with pytest.raises(AdmissionRejected, match="pin_absent"):
        admit_documents(
            procedure_path=FIXTURES / "procedure-voltage-check.json",
            policy_path=FIXTURES / "safety-policy.json",
            bench_path=FIXTURES / "bench.json",
            binding_path=FIXTURES / "run-binding.json",
            commissioning_path=FIXTURES / "commissioning.json",
            descriptor_paths={"psu": DESCRIPTORS["psu"]},
        )


def test_semantics_admit() -> None:
    check_semantics(admit(), now_wall=NOW_WALL)


def test_duplicate_step_id_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        loop = _root_step(procedure, "loop")
        loop["steps"].append({"id": "settle", "kind": "delay", "duration_ms": 50})

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^duplicate_step_id:"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_future_reference_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        configure = _root_step(procedure, "configure")
        configure["input"]["enabled"] = {
            "$stg_ref": {"step": "enable", "pointer": "/enabled"}
        }

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^scope: .*enable"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_branch_scope_leak_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        check = _root_step(procedure, "check")
        check["predicate"]["sample"] = "recheck"

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^scope: .*recheck"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_loop_scope_leak_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        check = _root_step(procedure, "check")
        check["predicate"]["sample"] = "remeasure"

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^scope: .*remeasure"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_previous_iteration_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        remeasure = _loop_step(procedure, "remeasure")
        remeasure["input"]["self"] = {
            "$stg_ref": {"step": "remeasure", "pointer": "/configuration_id"}
        }

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^scope: .*remeasure"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_issue_misplacement_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        configure = _root_step(procedure, "configure")
        configure["input"]["voltage_v"] = {"$stg_issue": "configuration_id"}

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^issue_placement:"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_issue_nested_below_top_level_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        configure = _root_step(procedure, "configure")
        configure["input"]["configuration_id"] = [{"$stg_issue": "configuration_id"}]

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^issue_placement:"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_body_budget_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        loop = _root_step(procedure, "loop")
        loop["count"] = 12

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^body_budget:"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_energised_budget_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        procedure["max_body_ms"] = 15000

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^energised_budget:"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_expired_commissioning_rejected() -> None:
    with pytest.raises(AdmissionRejected, match=r"^expired:"):
        check_semantics(admit(), now_wall="2031-01-01T00:00:00Z")


def test_worst_case_bound_exact() -> None:
    steps = json.loads((FIXTURES / "procedure-voltage-check.json").read_text())["steps"]
    # Hand computation from the fixture step list:
    #   configure invoke 500 + enable invoke 500 + settle delay 100
    #   + note write 200 + model read 200 + measure invoke 500 = 2000
    #   voltage sample 0 + check assert 0 = 0
    #   branch if: max(then, else) = max(recheck sample 0 + check-current
    #   assert 0, 0) = 0
    #   loop repeat: 3 x (remeasure invoke 500 + voltage-again sample 0
    #   + check-again assert 0) = 1500
    #   total = 2000 + 0 + 0 + 1500 = 3500
    assert worst_case_body_ms(steps) == 3500
