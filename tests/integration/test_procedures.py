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
binding completeness belong to later stages and are not exercised here. The
policy evaluator is exercised against the admitted fixture policy:
deny-by-default allow rules with conjunctive constraint checking, and
conservative continuous-condition evaluation over hand-built signal snapshots.
Task 6 adds the execution engine core: the eight-kind interpreter over both
sim plugins on an injected ``TestClock`` — happy path over a literal-input
variant of the fixture procedure, per-step deadline clamping against the
fixed body deadline, no-retry uncertainty after a dispatched failure,
post-dispatch timeout honesty, body expiry, policy-gated dispatch and the
shared occurrence ledger across ``run_body`` calls.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import warnings
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from benchweave.control.binding import BindingError, release, reserve, resolve_binding
from benchweave.control.clocking import SystemClock, TestClock
from benchweave.control.coordinator import RunCoordinator
from benchweave.control.documents import AdmissionRejected, AdmittedDocuments, admit_documents
from benchweave.control.executor import Executor, SampleOutcome, canonical_json, evaluate_predicate
from benchweave.control.policy import (
    PolicyDenied,
    SignalValue,
    check_allowed,
    evaluate_conditions,
)
from benchweave.control.semantics import check_semantics, worst_case_body_ms
from benchweave.host.plugin import DevicePlugin
from benchweave.host.services import HostServices
from benchweave.host.types import (
    DispatchState,
    ErrorCode,
    OperationRequest,
    OperationResult,
    OperationVerb,
)
from benchweave.state.store import Store

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


def test_extra_descriptor_pin_rejected() -> None:
    # The pin_absent rule is two-directional: a descriptor no bench device
    # names is as fatal as a missing one.
    with pytest.raises(AdmissionRejected, match=r"^pin_absent: bench pins no descriptor"):
        admit_documents(
            procedure_path=FIXTURES / "procedure-voltage-check.json",
            policy_path=FIXTURES / "safety-policy.json",
            bench_path=FIXTURES / "bench.json",
            binding_path=FIXTURES / "run-binding.json",
            commissioning_path=FIXTURES / "commissioning.json",
            descriptor_paths={**DESCRIPTORS, "ghost": DESCRIPTORS["psu"]},
        )


def _descriptor_id_empty(graph: dict[str, Any]) -> None:
    graph["descriptors"]["psu"]["id"] = ""


def _descriptor_profiles_scalar(graph: dict[str, Any]) -> None:
    graph["descriptors"]["psu"]["profiles"] = "otdp:dc_psu/1.0.0"


def _descriptor_actions_scalar(graph: dict[str, Any]) -> None:
    graph["descriptors"]["psu"]["actions"] = "configure"


def _descriptor_action_not_object(graph: dict[str, Any]) -> None:
    graph["descriptors"]["psu"]["actions"] = ["configure"]


def _descriptor_action_missing_id(graph: dict[str, Any]) -> None:
    graph["descriptors"]["psu"]["actions"] = [{"issued": ["configuration_id"]}]


def _descriptor_action_issued_scalar(graph: dict[str, Any]) -> None:
    graph["descriptors"]["psu"]["actions"] = [
        {"action_id": "otdp.dc_psu.configure/1.0.0", "issued": "configuration_id"}
    ]


DESCRIPTOR_FAULTS: list[tuple[Callable[[dict[str, Any]], None], str]] = [
    (_descriptor_id_empty, r"schema: descriptor\[psu\] requires non-empty string id"),
    (_descriptor_profiles_scalar, r"requires profiles to be a list of strings"),
    (_descriptor_actions_scalar, r"requires actions to be a list"),
    (_descriptor_action_not_object, r"requires each action to be an object"),
    (_descriptor_action_missing_id, r"action requires non-empty string action_id"),
    (_descriptor_action_issued_scalar, r"requires issued to be a list of strings"),
]


@pytest.mark.parametrize(("mutate", "message"), DESCRIPTOR_FAULTS)
def test_descriptor_structural_rejection(
    tmp_path: Path, mutate: Callable[[dict[str, Any]], None], message: str
) -> None:
    """Descriptors have no vendored schema: every _check_descriptor branch
    is the only structural fence, and each rejects at admission."""
    with pytest.raises(AdmissionRejected, match=message):
        readmit_mutated(tmp_path, mutate)


def test_package_lock_structural_rejection(tmp_path: Path) -> None:
    # The lock's id must be a non-empty string; the bench sits beside the
    # tampered lock so the lock decode is the one under test (its structural
    # check runs before any pin in the lattice is verified).
    lock = json.loads((FIXTURES / "package-lock.json").read_text())
    lock["id"] = 5
    (tmp_path / "package-lock.json").write_text(json.dumps(lock, indent=2))
    (tmp_path / "bench.json").write_bytes((FIXTURES / "bench.json").read_bytes())
    with pytest.raises(
        AdmissionRejected, match=r"^schema: package_lock requires non-empty string id"
    ):
        admit_documents(
            procedure_path=FIXTURES / "procedure-voltage-check.json",
            policy_path=FIXTURES / "safety-policy.json",
            bench_path=tmp_path / "bench.json",
            binding_path=FIXTURES / "run-binding.json",
            commissioning_path=FIXTURES / "commissioning.json",
            descriptor_paths=DESCRIPTORS,
        )


def test_pin_names_wrong_document_identity_rejected(tmp_path: Path) -> None:
    # A pin may carry the right digest yet name the wrong id: identity and
    # bytes must agree, not just bytes.
    def mutate(graph: dict[str, Any]) -> None:
        graph["binding"]["procedure"]["id"] = "not-voltage-check"

    with pytest.raises(
        AdmissionRejected,
        match=r"digest_mismatch: binding pins procedure as not-voltage-check@",
    ):
        readmit_mutated(tmp_path, mutate)


def test_bench_commissioning_name_mismatch_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        graph["bench"]["commissioning_id"] = "wrong-commissioning"

    with pytest.raises(AdmissionRejected, match=r"digest_mismatch: bench.commissioning_id"):
        readmit_mutated(tmp_path, mutate)


def test_procedure_policy_name_mismatch_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        graph["procedure"]["safety_policy"]["version"] = "9.9.9"

    with pytest.raises(
        AdmissionRejected, match=r"digest_mismatch: procedure.safety_policy names"
    ):
        readmit_mutated(tmp_path, mutate)


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


def test_write_value_reference_scope_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        note = _root_step(procedure, "note")
        note["value"] = {"$stg_ref": {"step": "model", "pointer": "/value"}}

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^scope: .*model"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_sample_source_scope_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        _root_step(procedure, "voltage")["source_step"] = "remeasure"

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(AdmissionRejected, match=r"^scope: .*remeasure"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_issue_in_write_value_rejected(tmp_path: Path) -> None:
    def mutate(procedure: dict[str, Any]) -> None:
        _root_step(procedure, "note")["value"] = {"$stg_issue": "configuration_id"}

    docs = readmit_with_procedure(tmp_path, mutate)
    with pytest.raises(
        AdmissionRejected, match=r"^issue_placement: .*outside an invoke input"
    ):
        check_semantics(docs, now_wall=NOW_WALL)


def test_semantics_invalid_now_wall_rejected() -> None:
    with pytest.raises(AdmissionRejected, match=r"^expired: now_wall"):
        check_semantics(admit(), now_wall="not-a-timestamp")


def test_semantics_invalid_expires_at_rejected() -> None:
    # In-memory mutation: the commissioning schema's date-time format fence
    # normally rejects this earlier, but that fence rides the optional
    # rfc3339-validator dependency — the semantics-stage parse is the
    # unconditional one under test here.
    docs = admit()
    docs.commissioning["expires_at"] = "not-a-timestamp"
    with pytest.raises(AdmissionRejected, match=r"^expired: commissioning.expires_at"):
        check_semantics(docs, now_wall=NOW_WALL)


def test_semantics_timestamp_parse_is_eager_before_other_checks() -> None:
    """An unparseable deadline input surfaces before any other semantic work.

    The document set carries BOTH a duplicate step id and a garbage
    expires_at: the eager parse must reject on the timestamp, not on the
    duplicate — the deadline is admission input, not a value to fail on at
    first use after everything else has run.
    """
    docs = admit()
    docs.procedure["steps"].append({"id": "settle", "kind": "delay", "duration_ms": 50})
    docs.commissioning["expires_at"] = "not-a-timestamp"
    with pytest.raises(AdmissionRejected, match=r"^expired: commissioning.expires_at"):
        check_semantics(docs, now_wall=NOW_WALL)


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


# --- Task 4: binding, resource closure, bench lease --------------------------

LEASE_EXPIRES = "2026-09-11T00:10:00Z"
LEASE_RELEASED_AT = "2026-09-11T00:01:00Z"


def _open_store(tmp_path: Path) -> Store:
    return Store.open(tmp_path / "state.db")


def readmit_mutated(
    tmp_path: Path, mutate: Callable[[dict[str, Any]], None]
) -> AdmittedDocuments:
    """Admit the fixture set with one document mutated, every pin repointed.

    ``mutate`` receives the whole in-memory document graph keyed by
    ``procedure``, ``policy``, ``bench``, ``binding``, ``commissioning`` and
    ``descriptors``. The full set is written out under ``tmp_path`` with the
    digest pin lattice rebuilt in dependency order (descriptor, policy and
    package-lock pins into the bench; bench, policy, package-lock and the
    procedure refs into the commissioning; all five pins into the binding),
    so structural admission succeeds and only the binding stage can reject.
    """
    filenames = {
        "procedure": "procedure-voltage-check.json",
        "policy": "safety-policy.json",
        "bench": "bench.json",
        "binding": "run-binding.json",
        "commissioning": "commissioning.json",
    }
    graph: dict[str, Any] = {
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
    procedure_digest = hashlib.sha256(procedure_path.read_bytes()).hexdigest()
    bench_digest = hashlib.sha256(bench_path.read_bytes()).hexdigest()
    policy_digest = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    lock_digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()

    commissioning = graph["commissioning"]
    commissioning["bench"]["sha256"] = bench_digest
    commissioning["policy"]["sha256"] = policy_digest
    commissioning["package_lock"]["sha256"] = lock_digest
    for ref in commissioning["procedure_refs"]:
        ref["sha256"] = procedure_digest
    commissioning_path = tmp_path / "commissioning.json"
    commissioning_path.write_text(json.dumps(commissioning, indent=2))

    binding = graph["binding"]
    binding["procedure"]["sha256"] = procedure_digest
    binding["bench"]["sha256"] = bench_digest
    binding["policy"]["sha256"] = policy_digest
    binding["package_lock"]["sha256"] = lock_digest
    binding["commissioning"]["sha256"] = hashlib.sha256(
        commissioning_path.read_bytes()
    ).hexdigest()
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


def _binding_entry(graph: dict[str, Any], role: str) -> dict[str, Any]:
    return next(entry for entry in graph["binding"]["bindings"] if entry["role"] == role)


def _procedure_step(graph: dict[str, Any], step_id: str) -> dict[str, Any]:
    return next(step for step in graph["procedure"]["steps"] if step["id"] == step_id)


def _resource(graph: dict[str, Any], resource_id: str) -> dict[str, Any]:
    return next(r for r in graph["bench"]["resources"] if r["id"] == resource_id)


def test_resolve_binding_maps_roles_and_channels() -> None:
    resolved = resolve_binding(admit())
    assert resolved.device_by_role == {"supply": "psu", "dut": "controller"}
    assert resolved.channels_by_role == {"supply": {"output": "ch1"}, "dut": {}}


def test_reserve_takes_lease_and_reserves_resources(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        reservation = reserve(
            store, admit(), bench_id="sim-bench", holder="run:run-1",
            expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
        )
        assert reservation.resources == frozenset({"dut-net"})
        assert reservation.lease.lease_id == "lease-req-voltage-check-1"
        assert reservation.lease.holder == "run:run-1"
        assert reservation.lease.state == "active"
        active = store.get_active_lease("sim-bench")
        assert active is not None and active.sequence == reservation.lease.sequence
    finally:
        store.close()


def test_unbound_role_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        graph["binding"]["bindings"] = [
            entry for entry in graph["binding"]["bindings"] if entry["role"] != "dut"
        ]

    with pytest.raises(BindingError, match=r"^unbound_role: dut$"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_duplicate_role_binding_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        graph["binding"]["bindings"].append(
            {"role": "supply", "device_id": "psu", "channels": {}}
        )

    with pytest.raises(BindingError, match=r"^duplicate_role:"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_unknown_role_binding_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        graph["binding"]["bindings"].append(
            {"role": "phantom", "device_id": "psu", "channels": {}}
        )

    with pytest.raises(BindingError, match=r"^unknown_role:"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_unknown_device_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _binding_entry(graph, "dut")["device_id"] = "ghost"

    with pytest.raises(BindingError, match=r"^unknown_device:"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_missing_profile_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        graph["descriptors"]["psu"]["profiles"] = []

    with pytest.raises(BindingError, match=r"^missing_profile:"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_undeclared_action_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _procedure_step(graph, "configure")["action_id"] = "otdp.dc_psu.configure/9.9.9"

    with pytest.raises(BindingError, match=r"^undeclared_action:"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_undeclared_parameter_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _procedure_step(graph, "model")["parameter"] = "nope"

    with pytest.raises(BindingError, match=r"^undeclared_parameter:"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_channel_alias_to_undeclared_channel_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _binding_entry(graph, "supply")["channels"] = {"output": "ch9"}

    with pytest.raises(BindingError, match=r"^undeclared_channel:"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_unbound_channel_alias_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _binding_entry(graph, "supply")["channels"] = {}

    with pytest.raises(BindingError, match=r"^unbound_channel:"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_extra_channel_alias_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _binding_entry(graph, "supply")["channels"] = {"output": "ch1", "spare": "ch1"}

    with pytest.raises(BindingError, match=r"^undeclared_channel:"):
        resolve_binding(readmit_mutated(tmp_path, mutate))


def test_bench_mismatch_rejected(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        with pytest.raises(BindingError, match=r"^bench_mismatch:"):
            reserve(
                store, admit(), bench_id="other-bench", holder="run:run-1",
                expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
            )
    finally:
        store.close()


def test_resource_cycle_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _resource(graph, "dut-net")["depends_on"] = ["aux"]
        graph["bench"]["resources"].append(
            {"id": "aux", "device_ids": [], "depends_on": ["dut-net"]}
        )

    store = _open_store(tmp_path)
    try:
        with pytest.raises(BindingError, match=r"^resource_cycle:"):
            reserve(
                store, readmit_mutated(tmp_path, mutate), bench_id="sim-bench",
                holder="run:run-1", expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
            )
        assert store.get_active_lease("sim-bench") is None
    finally:
        store.close()


def test_unknown_resource_dependency_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _resource(graph, "dut-net")["depends_on"] = ["ghost"]

    store = _open_store(tmp_path)
    try:
        with pytest.raises(BindingError, match=r"^unknown_resource:"):
            reserve(
                store, readmit_mutated(tmp_path, mutate), bench_id="sim-bench",
                holder="run:run-1", expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
            )
    finally:
        store.close()


def test_duplicate_resource_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        graph["bench"]["resources"].append(
            {"id": "dut-net", "device_ids": [], "depends_on": []}
        )

    store = _open_store(tmp_path)
    try:
        with pytest.raises(BindingError, match=r"^duplicate_resource:"):
            reserve(
                store, readmit_mutated(tmp_path, mutate), bench_id="sim-bench",
                holder="run:run-1", expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
            )
    finally:
        store.close()


def test_signal_naming_unknown_resource_rejected(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        graph["bench"]["signals"][0]["resource_id"] = "ghost-net"

    store = _open_store(tmp_path)
    try:
        with pytest.raises(BindingError, match=r"^unknown_resource:"):
            reserve(
                store, readmit_mutated(tmp_path, mutate), bench_id="sim-bench",
                holder="run:run-1", expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
            )
    finally:
        store.close()


def test_invalid_now_wall_rejected(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.next_lease(
            "sim-bench", lease_id="lease-held", holder="run:run-other",
            expires_at=LEASE_EXPIRES,
        )
        with pytest.raises(BindingError, match=r"^invalid_timestamp:"):
            reserve(
                store, admit(), bench_id="sim-bench", holder="run:run-1",
                expires_at=LEASE_EXPIRES, now_wall="not-a-timestamp",
            )
    finally:
        store.close()


def test_closure_expands_depends_on(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _resource(graph, "dut-net")["depends_on"] = ["aux"]
        graph["bench"]["resources"].append(
            {"id": "aux", "device_ids": [], "depends_on": []}
        )

    store = _open_store(tmp_path)
    try:
        reservation = reserve(
            store, readmit_mutated(tmp_path, mutate), bench_id="sim-bench",
            holder="run:run-1", expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
        )
        assert reservation.resources == frozenset({"dut-net", "aux"})
    finally:
        store.close()


def test_reserve_twice_bench_busy_until_released(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        docs = admit()
        first = reserve(
            store, docs, bench_id="sim-bench", holder="run:run-1",
            expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
        )
        with pytest.raises(BindingError, match=r"^bench_busy:"):
            reserve(
                store, docs, bench_id="sim-bench", holder="run:run-2",
                expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
            )
        release(store, first, now_wall=LEASE_RELEASED_AT)
        second = reserve(
            store, docs, bench_id="sim-bench", holder="run:run-2",
            expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
        )
        assert second.lease.sequence == first.lease.sequence + 1
    finally:
        store.close()


def test_expired_active_lease_does_not_block_reserve(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        # A dead run's lease: still marked active in the store, expired by the clock.
        store.next_lease(
            "sim-bench", lease_id="lease-stale", holder="run:run-dead",
            expires_at="2026-09-10T23:00:00Z",
        )
        assert store.get_active_lease("sim-bench") is not None
        reservation = reserve(
            store, admit(), bench_id="sim-bench", holder="run:run-1",
            expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
        )
        assert reservation.lease.sequence == 2
    finally:
        store.close()


def test_failed_reserve_leaves_no_active_lease(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        graph["binding"]["bindings"] = [
            entry for entry in graph["binding"]["bindings"] if entry["role"] != "dut"
        ]

    store = _open_store(tmp_path)
    try:
        with pytest.raises(BindingError, match=r"^unbound_role: dut$"):
            reserve(
                store, readmit_mutated(tmp_path, mutate), bench_id="sim-bench",
                holder="run:run-1", expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
            )
        assert store.get_active_lease("sim-bench") is None
    finally:
        store.close()


def test_release_is_idempotent(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        reservation = reserve(
            store, admit(), bench_id="sim-bench", holder="run:run-1",
            expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
        )
        release(store, reservation, now_wall=LEASE_RELEASED_AT)
        release(store, reservation, now_wall=LEASE_RELEASED_AT)
        assert store.get_active_lease("sim-bench") is None
    finally:
        store.close()


def test_release_reraises_undocumented_value_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the documented not-active outcome is idempotent success.

    A ValueError from the store that is NOT the no-active-lease condition is
    a defect and must surface, never be swallowed by the idempotence guard.
    """
    store = _open_store(tmp_path)
    try:
        reservation = reserve(
            store, admit(), bench_id="sim-bench", holder="run:run-1",
            expires_at=LEASE_EXPIRES, now_wall=NOW_WALL,
        )

        def boom(bench_id: str, sequence: int, now: str) -> None:
            raise ValueError("programming error: connection closed")

        monkeypatch.setattr(store, "release_lease", boom)
        with pytest.raises(ValueError, match="programming error"):
            release(store, reservation, now_wall=LEASE_RELEASED_AT)
    finally:
        store.close()


# --- Task 5: safety policy allow rules and continuous conditions ------------

PSU_CONFIGURE = "otdp.dc_psu.configure/1.0.0"
PSU_OUTPUT = "otdp.dc_psu.output/1.0.0"
CONFIGURE_INPUT = {
    "channel": "ch1",
    "voltage_v": 5.0,
    "current_limit_a": 0.4,
    "ovp_v": 5.8,
    "ocp_a": 0.45,
}


def _signal(
    signal_id: str,
    value: float,
    unit: str = "V",
    *,
    age_ms: int = 100,
    valid: bool = True,
    absolute_error: float | None = 0.05,
) -> SignalValue:
    return SignalValue(
        signal_id=signal_id,
        value=value,
        unit=unit,
        age_ms=age_ms,
        valid=valid,
        absolute_error=absolute_error,
    )


def _current(value: float, *, age_ms: int = 100) -> SignalValue:
    return _signal("dut-current", value, "A", age_ms=age_ms, absolute_error=0.01)


def _live_snapshot(
    voltage: SignalValue | None = None, current: SignalValue | None = None
) -> dict[str, SignalValue]:
    """Snapshot of the two fixture signals; ``None`` omits the key entirely."""
    snapshot: dict[str, SignalValue] = {}
    if voltage is not None:
        snapshot["dut-voltage"] = voltage
    if current is not None:
        snapshot["dut-current"] = current
    return snapshot


def test_policy_no_matching_rule_denied() -> None:
    # Rules exist for psu configure but none for the controller: deny by default.
    with pytest.raises(PolicyDenied, match=r"^no_matching_rule:") as raised:
        check_allowed(
            admit().policy,
            "controller",
            "invoke",
            PSU_CONFIGURE,
            {"channel": "ch1", "voltage_v": 5.0},
        )
    assert raised.value.rule_ids == ()


def test_policy_input_constraint_denied() -> None:
    with pytest.raises(PolicyDenied, match=r"^input_constraint:") as raised:
        check_allowed(
            admit().policy,
            "psu",
            "invoke",
            PSU_CONFIGURE,
            {**CONFIGURE_INPUT, "voltage_v": 5.6},
        )
    assert raised.value.rule_ids == ("allow_rules[0]",)
    assert "5.6 is greater than the maximum of 5.5" in raised.value.reason


def test_policy_matched_invoke_allowed() -> None:
    # Returning without raising is the allow verdict.
    check_allowed(admit().policy, "psu", "invoke", PSU_CONFIGURE, CONFIGURE_INPUT)


def test_policy_invoke_payload_must_be_object() -> None:
    # A bare scalar slips past "properties" (it only applies to objects), so
    # the payload being an object is itself a constraint.
    with pytest.raises(PolicyDenied, match=r"^input_constraint:.*not an object"):
        check_allowed(admit().policy, "psu", "invoke", PSU_OUTPUT, "ch1")


def test_policy_write_value_constraint_denied() -> None:
    with pytest.raises(PolicyDenied, match=r"^value_constraint:") as raised:
        check_allowed(admit().policy, "controller", "write", "operator_note", "x" * 201)
    assert raised.value.rule_ids == ("allow_rules[3]",)


def test_policy_write_within_constraint_allowed() -> None:
    check_allowed(admit().policy, "controller", "write", "operator_note", "x" * 200)


def test_policy_conjunctive_rules_all_must_pass() -> None:
    policy = copy.deepcopy(admit().policy)
    policy["allow_rules"].append(
        {
            "device_id": "psu",
            "kind": "invoke",
            "action_id": PSU_CONFIGURE,
            "input_constraints": {"properties": {"voltage_v": {"maximum": 4.5}}},
        }
    )
    # Rule 0 passes at 5.0 V but the stricter duplicate does not: matching
    # rules apply conjunctively, with no order-dependent overrides.
    with pytest.raises(PolicyDenied, match=r"^input_constraint:") as raised:
        check_allowed(policy, "psu", "invoke", PSU_CONFIGURE, CONFIGURE_INPUT)
    assert raised.value.rule_ids == ("allow_rules[4]",)
    check_allowed(
        policy, "psu", "invoke", PSU_CONFIGURE, {**CONFIGURE_INPUT, "voltage_v": 4.0}
    )


def test_policy_vacuous_constraint_rule_warns() -> None:
    policy = copy.deepcopy(admit().policy)
    policy["allow_rules"].append(
        {
            "device_id": "psu",
            "kind": "invoke",
            "action_id": PSU_CONFIGURE,
            "input_constraints": {},
        }
    )
    # An empty schema validates every payload: the appended rule matches yet
    # constrains nothing, which is almost certainly an admission mistake.
    with pytest.warns(UserWarning, match=r"vacuous_constraint: allow_rules\[4\]"):
        check_allowed(policy, "psu", "invoke", PSU_CONFIGURE, CONFIGURE_INPUT)


def test_policy_constrained_rule_stays_silent() -> None:
    with warnings.catch_warnings():
        # The fixture rule carries a real constraint schema; any warning
        # escaping it here would be noise, not signal.
        warnings.simplefilter("error")
        check_allowed(admit().policy, "psu", "invoke", PSU_CONFIGURE, CONFIGURE_INPUT)


def test_conditions_all_clear() -> None:
    # (5.0 + 0.05) x (0.5 + 0.01) = 2.5755 <= 3 W, equal ages, bounds hold.
    snapshot = _live_snapshot(_signal("dut-voltage", 5.0), _current(0.5))
    assert evaluate_conditions(admit().policy, snapshot) == []


def test_conditions_numeric_interval_escape() -> None:
    # 5.4 alone is inside [-0.1, 5.5]; the error interval [5.2, 5.6] is not.
    snapshot = _live_snapshot(
        _signal("dut-voltage", 5.4, absolute_error=0.2), _current(0.5)
    )
    assert evaluate_conditions(admit().policy, snapshot) == [
        "dut-voltage-bounds: interval_escape: [5.2, 5.6] escapes [-0.1, 5.5]"
    ]


def test_conditions_numeric_at_bound_passes() -> None:
    # [5.4, 5.5] touches both endpoints: containment is inclusive.
    snapshot = _live_snapshot(_signal("dut-voltage", 5.45), _current(0.5))
    assert evaluate_conditions(admit().policy, snapshot) == []


def test_conditions_stale_signal_violates() -> None:
    # The snapshot builder marks age 600 > bench max_age 500 as invalid.
    snapshot = _live_snapshot(
        _signal("dut-voltage", 5.0, age_ms=600, valid=False), _current(0.5)
    )
    violations = evaluate_conditions(admit().policy, snapshot)
    assert "dut-voltage-bounds: signal_invalid: dut-voltage" in violations
    assert "dut-power: signal_invalid: dut-voltage" in violations


def test_conditions_missing_signal_violates() -> None:
    snapshot = _live_snapshot(current=_current(0.5))
    violations = evaluate_conditions(admit().policy, snapshot)
    assert "dut-voltage-bounds: signal_missing: dut-voltage" in violations
    assert "dut-power: signal_missing: dut-voltage" in violations


def test_conditions_unit_mismatch_violates() -> None:
    snapshot = _live_snapshot(_signal("dut-voltage", 5.0, unit="A"), _current(0.5))
    # Both factors carry "A": the numeric condition unit-mismatches AND the
    # product condition is an INVALID V x A pairing (Forge F1 — the pairing
    # itself is a violation, not silent pass-through).
    assert evaluate_conditions(admit().policy, snapshot) == [
        "dut-voltage-bounds: unit_mismatch: expected V, have A",
        "dut-power: factor_unit_mismatch: expected V and A factors, have A and A",
    ]


def test_conditions_unknown_error_violates() -> None:
    snapshot = _live_snapshot(
        _signal("dut-voltage", 5.0, absolute_error=None), _current(0.5)
    )
    assert "dut-voltage-bounds: unknown_error" in evaluate_conditions(
        admit().policy, snapshot
    )


def test_conditions_nonfinite_value_violates() -> None:
    snapshot = _live_snapshot(_signal("dut-voltage", float("nan")), _current(0.5))
    assert "dut-voltage-bounds: nonfinite_value: dut-voltage" in evaluate_conditions(
        admit().policy, snapshot
    )


def test_conditions_boolean_match_passes() -> None:
    policy = copy.deepcopy(admit().policy)
    policy["continuous_conditions"].append(
        {"id": "psu-output-on", "kind": "boolean", "signal": "dut-voltage", "expected": True}
    )
    snapshot = _live_snapshot(_signal("dut-voltage", 5.0), _current(0.5))
    assert evaluate_conditions(policy, snapshot) == []


def test_conditions_boolean_mismatch_violates() -> None:
    policy = copy.deepcopy(admit().policy)
    policy["continuous_conditions"].append(
        {"id": "psu-output-on", "kind": "boolean", "signal": "dut-voltage", "expected": True}
    )
    # A zero reading is falsy, so expecting True on it mismatches.
    snapshot = _live_snapshot(_signal("dut-voltage", 0.0), _current(0.5))
    assert evaluate_conditions(policy, snapshot) == [
        "psu-output-on: boolean_mismatch: dut-voltage is 0, expected True"
    ]


def test_conditions_product_bound_exceeded() -> None:
    # (5.0 + 0.05) x (0.7 + 0.01) = 3.5855 > 3 W.
    snapshot = _live_snapshot(_signal("dut-voltage", 5.0), _current(0.7))
    assert evaluate_conditions(admit().policy, snapshot) == [
        "dut-power: bound_exceeded: 3.5855 > maximum 3"
    ]


def test_conditions_unknown_kind_raises_value_error() -> None:
    """An unknown condition kind is a typed fence, not a KeyError.

    The dict dispatch is the admission boundary for condition kinds: an
    unexpected kind raises ValueError naming the offender, mirroring the
    registry fence pattern.
    """
    policy = copy.deepcopy(admit().policy)
    policy["continuous_conditions"].append(
        {"id": "bad-condition", "kind": "quantum", "signal": "dut-voltage"}
    )
    with pytest.raises(ValueError, match="unknown condition kind"):
        evaluate_conditions(policy, _live_snapshot(_signal("dut-voltage", 5.0), _current(0.5)))


def test_conditions_product_at_exact_bound_passes() -> None:
    # (4.9 + 0.1) x (0.6 + 0) = 5.0 x 0.6 = 3.0 W exactly at the maximum:
    # the product bound is inclusive at the bound, like the numeric interval
    # and the skew bound. (4.9 ± 0.1 stays inside [-0.1, 5.5].)
    snapshot = _live_snapshot(
        _signal("dut-voltage", 4.9, absolute_error=0.1),
        _signal("dut-current", 0.6, "A", absolute_error=0.0),
    )
    assert evaluate_conditions(admit().policy, snapshot) == []


def test_conditions_product_skew_exceeded() -> None:
    snapshot = _live_snapshot(
        _signal("dut-voltage", 5.0, age_ms=100), _current(0.5, age_ms=250)
    )
    assert evaluate_conditions(admit().policy, snapshot) == [
        "dut-power: skew_exceeded: 150 > max_skew_ms 100"
    ]


def test_conditions_product_skew_at_bound_passes() -> None:
    snapshot = _live_snapshot(
        _signal("dut-voltage", 5.0, age_ms=100), _current(0.5, age_ms=200)
    )
    assert evaluate_conditions(admit().policy, snapshot) == []


def test_conditions_product_factor_units_must_be_v_and_a() -> None:
    """§7: the product condition is V x A -> W; mis-unitized factors are INVALID.

    A kV-scaled factor would slip through the numeric bound (0.005 reads as
    tiny) — the factor units themselves must make the condition a violation
    the caller acts on, in either signal order (Forge F1).
    """
    snapshot = _live_snapshot(_signal("dut-voltage", 0.005, unit="kV"), _current(0.5))
    assert evaluate_conditions(admit().policy, snapshot) == [
        "dut-voltage-bounds: unit_mismatch: expected V, have kV",
        "dut-power: factor_unit_mismatch: expected V and A factors, have kV and A",
    ]
    reversed_policy = copy.deepcopy(admit().policy)
    product = next(
        condition
        for condition in reversed_policy["continuous_conditions"]
        if condition["id"] == "dut-power"
    )
    product["signals"] = ["dut-current", "dut-voltage"]
    assert evaluate_conditions(
        reversed_policy, _live_snapshot(_signal("dut-voltage", 5.0), _current(0.5))
    ) == []


# --- Task 6: clocking + execution engine core ---------------------------------

PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "plugins"
RUN_ID = "run-1"
LITERAL_CONFIGURATION_ID = "cfg-test-1"
PSU_MEASURE = "otdp.dc_psu.measure/1.0.0"
CONFIGURE_LITERAL_INPUT = {
    "configuration_id": LITERAL_CONFIGURATION_ID,
    "channel": "ch1",
    "voltage_v": 5.0,
    "current_limit_a": 0.5,
    "ovp_v": 5.5,
    "ocp_a": 0.5,
}


def _load_plugin(name: str) -> ModuleType:
    path = PLUGINS_ROOT / "benchweave" / name / "src" / f"benchweave_{name}" / "plugin.py"
    assert path.is_file(), f"plugin file missing: {path}"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _NullServices:
    """Scoped-services stand-in; the sim plugins only store the reference."""

    def resolve_content(self, content_id: str) -> bytes:
        return b"{}"

    def retain_evidence(self, key: str, payload: bytes) -> str:
        return f"evidence-{key}"

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        pass

    def quota_state(self) -> dict[str, int]:
        return {"dataset_bytes_used": 0, "evidence_entries_used": 0, "events_emitted": 0}

    def register_reading_sink(self, sink: Any) -> None:
        pass


class _RecordingPlugin:
    """DevicePlugin wrapper capturing every dispatched request and deadline.

    The optional ``hook`` intercepts a dispatch and returns an override
    OperationResult (a fault injection), or None to delegate to the inner
    plugin.
    """

    def __init__(self, inner: DevicePlugin) -> None:
        self._inner = inner
        self.calls: list[tuple[OperationRequest, int]] = []
        self.hook: Callable[[OperationRequest], OperationResult | None] | None = None

    @property
    def simulation(self) -> Any:
        return self._inner.simulation

    def plugin_open(self, services: HostServices) -> None:
        self._inner.plugin_open(services)

    def plugin_close(self) -> None:
        self._inner.plugin_close()

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        self.calls.append((request, deadline_ns))
        override = None if self.hook is None else self.hook(request)
        if override is not None:
            return override
        return self._inner.dispatch(request, deadline_ns=deadline_ns)


def _walk_all_steps(steps: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for step in steps:
        yield step
        if step["kind"] == "if":
            yield from _walk_all_steps(step["then"])
            yield from _walk_all_steps(step.get("else", []))
        elif step["kind"] == "repeat":
            yield from _walk_all_steps(step["steps"])


def _literalize_inputs(graph: dict[str, Any]) -> None:
    """Replace the three $stg reference forms with literals (Task 6 seam).

    Reference resolution, issued IDs and trustworthy samples arrive in Task 7;
    until then the engine under test runs a reduced literal-input variant of
    the fixture procedure, admitted through the normal pin lattice.
    """
    for step in _walk_all_steps(graph["procedure"]["steps"]):
        if step["kind"] != "invoke":
            continue
        step_input = step["input"]
        if isinstance(step_input.get("configuration_id"), dict):
            step_input["configuration_id"] = LITERAL_CONFIGURATION_ID
        if isinstance(step_input.get("channel"), dict):
            step_input["channel"] = "ch1"
        if isinstance(step_input.get("channels"), list):
            step_input["channels"] = ["ch1" for _ in step_input["channels"]]


def _admit_literal(tmp_path: Path) -> AdmittedDocuments:
    """Literal-input variant of the fixture, admitted through the pins.

    Task 7's conservative-interval predicates made the fixture's own
    ``check-current`` bounds (``[0.0, 0.5]`` vs current ``0.0 ± 0.01``)
    honestly unsatisfiable, so the reduced variant also widens that one
    predicate (see ``_widen_check_current``) to keep the completing-body
    shape these tests assert.
    """

    def mutate(graph: dict[str, Any]) -> None:
        _literalize_inputs(graph)
        _widen_check_current(graph)

    return readmit_mutated(tmp_path, mutate)


def _plugins_for(clock: TestClock) -> dict[str, DevicePlugin]:
    """Both sim plugins on the SAME clock the executor will use."""
    plugins: dict[str, DevicePlugin] = {}
    for device_id, name in (("psu", "sim_psu"), ("controller", "sim_controller")):
        plugin = _load_plugin(name).create_plugin(
            now_fn=clock.now_iso, monotonic_ns_fn=clock.now_ns
        )
        plugin.plugin_open(_NullServices())
        plugins[device_id] = plugin
    return plugins


def _executor_for(
    docs: AdmittedDocuments,
    plugins: dict[str, DevicePlugin],
    clock: TestClock,
    ledger: dict[tuple[str, str, tuple[int, ...]], dict[str, Any]] | None = None,
) -> Executor:
    return Executor(
        plugins=plugins,
        binding=resolve_binding(docs),
        policy=docs.policy,
        clock=clock,
        wall=clock,
        occurrence_ledger=ledger,
    )


def _body_deadline(clock: TestClock, docs: AdmittedDocuments) -> int:
    return clock.now_ns() + int(docs.procedure["max_body_ms"]) * 1_000_000


def _wrapped_psu(plugins: dict[str, DevicePlugin]) -> _RecordingPlugin:
    recorder = _RecordingPlugin(plugins["psu"])
    plugins["psu"] = recorder
    return recorder


def test_test_clock_advances_waits_and_stamps_wall_time() -> None:
    clock = TestClock(start_ns=1_000)
    assert clock.now_ns() == 1_000
    assert clock.now_iso() == "2026-09-11T00:00:00Z"
    clock.advance(5)
    clock.wait_ns(100_000_000)
    assert clock.now_ns() == 100_001_005  # waits advance instantly, never sleep
    assert clock.waits == [100_000_000]
    assert clock.now_iso() == "2026-09-11T00:00:00.100000Z"


def test_system_clock_satisfies_both_ports() -> None:
    clock = SystemClock()
    before = clock.now_ns()
    clock.wait_ns(0)
    assert before > 0
    assert clock.now_ns() >= before
    stamp = datetime.fromisoformat(clock.now_iso().replace("Z", "+00:00"))
    assert stamp.tzinfo is not None


def test_run_body_happy_path_executes_all_eight_kinds(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    ledger: dict[tuple[str, str, tuple[int, ...]], dict[str, Any]] = {}
    docs = _admit_literal(tmp_path)
    executor = _executor_for(docs, plugins, clock, ledger)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "completed"
    assert result.reasons == []
    assert {event["kind"] for event in result.step_events} == {
        "invoke", "read", "write", "delay", "sample", "assert", "if", "repeat"
    }
    assert all(event["status"] == "ok" for event in result.step_events)
    # 10 root steps (the repeat parent included) + 2 then-branch steps
    # + 3 x 3 loop children.
    assert len(result.step_events) == 21
    by_step = {event["occurrence"][1]: event for event in result.step_events}
    assert by_step["configure"]["occurrence"] == [RUN_ID, "configure", []]
    assert by_step["loop"]["occurrence"] == [RUN_ID, "loop", []]
    assert by_step["recheck"]["occurrence"] == [RUN_ID, "recheck", []]
    assert [event["occurrence"] for event in result.step_events
            if event["occurrence"][1] == "remeasure"] == [
        [RUN_ID, "remeasure", [0]],
        [RUN_ID, "remeasure", [1]],
        [RUN_ID, "remeasure", [2]],
    ]
    assert by_step["configure"]["operation_id"] == f"op:{RUN_ID}:configure"
    assert {event["operation_id"] for event in result.step_events} >= {
        f"op:{RUN_ID}:remeasure.0",
        f"op:{RUN_ID}:remeasure.1",
        f"op:{RUN_ID}:remeasure.2",
    }
    assert by_step["configure"]["resolved_input_sha256"] == hashlib.sha256(
        canonical_json(CONFIGURE_LITERAL_INPUT).encode("utf-8")
    ).hexdigest()
    configure_result = ledger[(RUN_ID, "configure", ())]["result"]
    assert configure_result.data["result"]["configuration_id"] == LITERAL_CONFIGURATION_ID
    assert clock.waits == [100_000_000]  # the settle delay, through the injected clock
    assert len(psu_calls.calls) == 6  # configure + enable + measure + 3 remeasure


def test_step_deadline_clamped_to_remaining_body_budget(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _literalize_inputs(graph)
        graph["procedure"]["max_body_ms"] = 1

    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock)
    start_ns = clock.now_ns()
    body_deadline_ns = start_ns + 1_000_000

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=body_deadline_ns
    )

    # The 1 ms body budget is shorter than every step timeout: the body ends
    # at its deadline and every dispatched deadline is clamped to the budget.
    assert result.body_outcome == "timed_out"
    assert psu_calls.calls
    for _request, dispatched_deadline_ns in psu_calls.calls:
        assert start_ns <= dispatched_deadline_ns <= body_deadline_ns
        assert dispatched_deadline_ns < start_ns + 500_000_000
    assert psu_calls.calls[0][1] == body_deadline_ns


def test_uncertain_operation_is_never_retried(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    attempts = [0]

    def fail_measure_once(request: OperationRequest) -> OperationResult | None:
        if (
            request.verb is OperationVerb.INVOKE
            and request.arguments.get("action_id") == PSU_MEASURE
        ):
            attempts[0] += 1
            if attempts[0] == 1:
                return OperationResult.failure(
                    request.operation_id,
                    request.verb,
                    code=ErrorCode.TRANSPORT_ERROR,
                    message="transport dropped after dispatch",
                    dispatch_state=DispatchState.DISPATCHED,
                )
        return None

    psu_calls.hook = fail_measure_once
    docs = _admit_literal(tmp_path)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "outcome_unknown"
    assert any(
        "measure" in reason and "TRANSPORT_ERROR" in reason for reason in result.reasons
    )
    measure_events = [
        event for event in result.step_events if event["occurrence"][1] == "measure"
    ]
    assert len(measure_events) == 1
    # The event mirrors the operation status; the uncertainty lives in the
    # body outcome above.
    assert measure_events[0]["status"] == "error"
    assert measure_events[0]["error_code"] == "TRANSPORT_ERROR"
    assert attempts[0] == 1  # the failed occurrence was never re-dispatched
    assert all(
        event["occurrence"][1] not in ("voltage", "check", "branch", "loop")
        for event in result.step_events
    )


def test_post_dispatch_timeout_is_outcome_unknown(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)

    def timeout_measure(request: OperationRequest) -> OperationResult | None:
        if (
            request.verb is OperationVerb.INVOKE
            and request.arguments.get("action_id") == PSU_MEASURE
        ):
            return OperationResult.indeterminate(
                request.operation_id,
                request.verb,
                code=ErrorCode.TIMEOUT,
                message="no answer before the deadline",
            )
        return None

    psu_calls.hook = timeout_measure
    docs = _admit_literal(tmp_path)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "outcome_unknown"
    assert any("measure" in reason and "TIMEOUT" in reason for reason in result.reasons)


def test_body_deadline_already_expired_times_out(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    docs = _admit_literal(tmp_path)
    executor = _executor_for(docs, plugins, clock)
    clock.advance(10_000_000_000)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=clock.now_ns() - 1_000_000
    )

    assert result.body_outcome == "timed_out"
    assert result.step_events == []
    assert len(result.reasons) == 1
    assert result.reasons[0].startswith("body_deadline_exceeded:")


def test_policy_denial_is_execution_error_and_blocks_dispatch(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _literalize_inputs(graph)
        _procedure_step(graph, "configure")["input"]["voltage_v"] = 5.6  # > policy 5.5

    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert any("input_constraint" in reason for reason in result.reasons)
    assert psu_calls.calls == []  # denied before dispatch: zero plugin calls
    assert [event["occurrence"][1] for event in result.step_events] == ["configure"]
    configure_event = result.step_events[0]
    assert configure_event["status"] == "error"
    assert configure_event["error_code"] == "POLICY_DENIED"


def test_shared_occurrence_ledger_replays_without_redispatch(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    ledger: dict[tuple[str, str, tuple[int, ...]], dict[str, Any]] = {}
    docs = _admit_literal(tmp_path)
    executor = _executor_for(docs, plugins, clock, ledger)
    body_deadline_ns = _body_deadline(clock, docs)

    first = executor.run_body(docs.procedure, run_id=RUN_ID, body_deadline_ns=body_deadline_ns)
    assert first.body_outcome == "completed"
    dispatches_after_first = list(psu_calls.calls)
    waits_after_first = list(clock.waits)
    occurrences_after_first = set(ledger)

    second = executor.run_body(docs.procedure, run_id=RUN_ID, body_deadline_ns=body_deadline_ns)

    assert second.body_outcome == "completed"
    assert second.reasons == []
    assert psu_calls.calls == dispatches_after_first  # no physical work repeated
    assert clock.waits == waits_after_first  # the delay was not re-waited either
    assert set(ledger) == occurrences_after_first  # occurrence identity is stable
    assert second.step_events == first.step_events


# --- Task 7: references, issued ids, trustworthy samples ----------------------


def _stub_variable(
    variable_id: str,
    unit: str,
    value: float,
    *,
    uncertainty: dict[str, Any] | None = None,
    dimensions: list[str] | None = None,
    values: list[Any] | None = None,
    status: str = "valid",
) -> dict[str, Any]:
    """One scalar_set variable, shape-compatible with sim_psu's measure."""
    return {
        "id": variable_id,
        "quantity": variable_id,
        "unit": unit,
        "channel_ids": ["ch1"],
        "dtype": "float64",
        "dimensions": [] if dimensions is None else dimensions,
        "values": [value] if values is None else values,
        "uncertainty": (
            {"status": "known", "absolute": 0.05} if uncertainty is None else uncertainty
        ),
        "calibration": {"status": "unknown"},
        "status": status,
    }


def _stub_dataset(started_at: str, variables: list[dict[str, Any]]) -> dict[str, Any]:
    """A scalar_set dataset envelope, shape-compatible with sim_psu's measure."""
    return {
        "dataset_id": "dataset-stub-1",
        "kind": "scalar_set",
        "configuration_id": "cfg-stub-1",
        "acquisition_id": None,
        "started_at": started_at,
        "clock": {
            "domain_id": "stub",
            "timestamp_source": "device",
            "synchronisation": "unknown",
            "uncertainty_s": None,
        },
        "axes": [],
        "variables": variables,
        "trigger": {"source": "unknown", "time_relative_s": None},
        "status": "complete",
        "context": {"direction": "delivered_to_dut"},
    }


def _override_first_measure(
    clock: TestClock, variables: list[dict[str, Any]]
) -> Callable[[OperationRequest], OperationResult | None]:
    """Hook replacing the ROOT measure result with a crafted stub dataset.

    Loop ``remeasure`` occurrences still hit the real plugin, so stub-driven
    root samples and real loop samples coexist in one body.
    """
    fired = [False]

    def hook(request: OperationRequest) -> OperationResult | None:
        if (
            request.verb is OperationVerb.INVOKE
            and request.arguments.get("action_id") == PSU_MEASURE
            and not fired[0]
        ):
            fired[0] = True
            return OperationResult.ok(
                request.operation_id,
                request.verb,
                {"result": _stub_dataset(clock.now_iso(), variables)},
            )
        return None

    return hook


def _psu_inputs(psu_calls: _RecordingPlugin) -> list[dict[str, Any]]:
    return [request.arguments["input"] for request, _ in psu_calls.calls]


def _events_by_step(result: Any) -> dict[str, dict[str, Any]]:
    return {event["occurrence"][1]: event for event in result.step_events}


def _widen_check_current(graph: dict[str, Any]) -> None:
    """Make the fixture's then-branch assert satisfiable by honest evidence.

    The fixture bounds ``check-current`` at ``[0.0, 0.5]`` while current
    measures ``0.0 ± 0.01``: the conservative interval ``[-0.01, 0.01]``
    dips below the zero minimum, so the pristine fixture cannot complete
    under §4 semantics (pinned separately below). Tests that need a
    completing body widen this one predicate; everything else stays
    original.
    """
    then_branch = _root_step(graph["procedure"], "branch")["then"]
    check_current = next(s for s in then_branch if s["id"] == "check-current")
    check_current["predicate"] = {"sample": "recheck", "minimum": -0.1, "maximum": 0.5}


def test_reference_fixture_resolves_all_three_forms(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    ledger: dict[tuple[str, str, tuple[int, ...]], dict[str, Any]] = {}
    docs = readmit_mutated(tmp_path, _widen_check_current)
    executor = _executor_for(docs, plugins, clock, ledger)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "completed"
    assert result.reasons == []
    assert len(result.step_events) == 21  # same shape as the literal variant
    inputs = _psu_inputs(psu_calls)
    issued_id = inputs[0]["configuration_id"]
    assert issued_id == f"configuration_id-{RUN_ID}-configure"
    # $stg_ref fed every later consumer with configure's echoed configuration_id
    for later_input in inputs[1:]:
        assert later_input["configuration_id"] == issued_id
    configure_result = ledger[(RUN_ID, "configure", ())]["result"]
    assert configure_result.data["result"]["configuration_id"] == issued_id
    assert ledger[(RUN_ID, "configure", ())]["issued_ids"] == {
        "configuration_id": {"id": issued_id, "status": "issued"}
    }

    # Replay on the shared ledger: references resolve from the recorded
    # results on re-entry, with no new dispatch and no new issued id.
    dispatches_after_first = list(psu_calls.calls)
    second = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )
    assert second.body_outcome == "completed"
    assert psu_calls.calls == dispatches_after_first
    assert second.step_events == result.step_events
    assert ledger[(RUN_ID, "configure", ())]["issued_ids"] == {
        "configuration_id": {"id": issued_id, "status": "issued"}
    }


def test_pristine_fixture_completes_with_interval_honest_bounds(tmp_path: Path) -> None:
    """The fixture's check-current bounds now admit honest interval evidence.

    Original finding: current measures 0.0 ± 0.01 while ``check-current``
    demanded ``[0.0, 0.5]`` — the conservative interval ``[-0.01, 0.01]``
    dipped below the zero minimum, so under §4 semantics the pristine body
    ended ``assertion_failed`` there (pinned before the Task 8 fixture
    fix). The ratified fix widens the fixture minimum to ``-0.01`` so the
    whole interval fits inside the inclusive bounds; the pristine fixture
    now completes with every assertion passing on real interval evidence,
    not nominal comparison.
    """
    clock = TestClock()
    plugins = _plugins_for(clock)
    docs = admit()  # the untouched reference-bearing fixture, bounds fixed
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "completed"
    assert result.reasons == []
    by_step = _events_by_step(result)
    assert by_step["check-current"]["status"] == "ok"
    assert "recheck" in by_step  # the then branch ran on real interval evidence
    assert "loop" in by_step  # the body ran to completion


def test_stg_channel_resolves_output_alias_via_binding(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    docs = admit()
    executor = _executor_for(docs, plugins, clock)

    executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    inputs = _psu_inputs(psu_calls)
    assert inputs[0]["channel"] == "ch1"  # alias "output" never reaches the device
    assert inputs[2]["channels"] == ["ch1"]


def test_stg_ref_missing_key_fails_before_dispatch(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        enable = _root_step(graph["procedure"], "enable")
        enable["input"]["configuration_id"]["$stg_ref"]["pointer"] = "/nonexistent"

    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert result.reasons[0].startswith("unresolved_reference:")
    assert "nonexistent" in result.reasons[0]
    # configure dispatched; enable — the consuming step — never did
    assert [request.arguments["action_id"] for request, _ in psu_calls.calls] == [
        PSU_CONFIGURE
    ]
    by_step = _events_by_step(result)
    assert by_step["enable"]["status"] == "error"
    assert by_step["enable"]["error_code"] == "UNRESOLVED_REFERENCE"
    assert "settle" not in by_step  # the body ended at enable


def test_stg_issue_mints_fresh_id_per_run(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    docs = admit()
    executor = _executor_for(docs, plugins, clock)

    executor.run_body(
        docs.procedure, run_id="run-1", body_deadline_ns=_body_deadline(clock, docs)
    )
    executor.run_body(
        docs.procedure, run_id="run-2", body_deadline_ns=_body_deadline(clock, docs)
    )

    issued = [
        request.arguments["input"]["configuration_id"]
        for request, _ in psu_calls.calls
        if request.arguments["action_id"] == PSU_CONFIGURE
    ]
    assert issued == [
        "configuration_id-run-1-configure",
        "configuration_id-run-2-configure",
    ]


def test_failed_configure_invalidates_issued_id_without_remint(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    attempts = [0]

    def reject_configure_once(request: OperationRequest) -> OperationResult | None:
        if (
            request.verb is OperationVerb.INVOKE
            and request.arguments.get("action_id") == PSU_CONFIGURE
        ):
            attempts[0] += 1
            if attempts[0] == 1:
                return OperationResult.failure(
                    request.operation_id,
                    request.verb,
                    code=ErrorCode.DEVICE_REJECTED,
                    message="configuration rejected",
                    dispatch_state=DispatchState.NOT_DISPATCHED,
                )
        return None

    psu_calls.hook = reject_configure_once
    ledger: dict[tuple[str, str, tuple[int, ...]], dict[str, Any]] = {}
    docs = admit()
    executor = _executor_for(docs, plugins, clock, ledger)

    first = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert first.body_outcome == "execution_error"
    assert attempts[0] == 1
    issued_id = psu_calls.calls[0][0].arguments["input"]["configuration_id"]
    assert ledger[(RUN_ID, "configure", ())]["issued_ids"] == {
        "configuration_id": {"id": issued_id, "status": "invalidated"}
    }

    second = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert second.body_outcome == "execution_error"
    assert attempts[0] == 1  # replayed occurrence: no re-dispatch, no re-mint
    assert len(psu_calls.calls) == 1
    assert ledger[(RUN_ID, "configure", ())]["issued_ids"] == {
        "configuration_id": {"id": issued_id, "status": "invalidated"}
    }


def test_loop_results_do_not_leak_past_iteration_frames(tmp_path: Path) -> None:
    """Runtime counterpart of admission's loop-scope rejection.

    A result visible inside a repeat iteration must be unresolvable outside
    the loop: each iteration executes in a fresh scope frame and nothing is
    written back to the enclosing scope. Admission rejects this shape
    statically (Task 3); this proves the executor agrees when handed the
    procedure directly.
    """
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    docs = readmit_mutated(tmp_path, _widen_check_current)
    procedure = copy.deepcopy(docs.procedure)
    procedure["steps"].append(
        {
            "id": "after",
            "kind": "invoke",
            "role": "supply",
            "action_id": PSU_MEASURE,
            "input": {
                "configuration_id": {
                    "$stg_ref": {"step": "remeasure", "pointer": "/configuration_id"}
                },
                "channels": [{"$stg_channel": "output"}],
            },
            "timeout_ms": 500,
        }
    )
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert result.reasons[0].startswith("unresolved_reference:")
    assert "remeasure" in result.reasons[0]
    measure_dispatches = [
        request
        for request, _ in psu_calls.calls
        if request.arguments.get("action_id") == PSU_MEASURE
    ]
    # root measure + three loop remeasures; `after` never dispatched
    assert len(measure_dispatches) == 4


def test_wrong_unit_sample_is_execution_error(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _root_step(graph["procedure"], "voltage")["unit"] = "mV"

    clock = TestClock()
    plugins = _plugins_for(clock)
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert "wrong_unit" in result.reasons[0]
    by_step = _events_by_step(result)
    assert by_step["voltage"]["status"] == "error"
    assert by_step["voltage"]["error_code"] == "INVALID_SAMPLE"
    assert "check" not in by_step  # INVALID never reaches the predicate


def test_stale_at_predicate_time_is_execution_error(tmp_path: Path) -> None:
    """§4: freshness is rechecked at predicate evaluation, not just selection.

    A sample fresh when selected but older than ``max_age_ms`` by the time
    its assert runs is INVALID evidence — ``execution_error``, never a
    passing assertion and never the false branch.
    """
    def mutate(graph: dict[str, Any]) -> None:
        steps = graph["procedure"]["steps"]
        index = next(i for i, step in enumerate(steps) if step["id"] == "voltage")
        steps.insert(
            index + 1, {"id": "age-at-assert", "kind": "delay", "duration_ms": 600}
        )

    clock = TestClock()
    plugins = _plugins_for(clock)
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"  # not assertion_failed
    assert any("stale" in reason for reason in result.reasons)
    by_step = _events_by_step(result)
    assert by_step["voltage"]["status"] == "ok"  # fresh at selection time
    assert by_step["check"]["status"] == "error"  # stale at predicate time
    assert by_step["check"]["error_code"] == "INVALID_SAMPLE"
    assert "recheck" not in by_step  # the body ended at the assert, not later


def test_stale_sample_is_execution_error(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        steps = graph["procedure"]["steps"]
        index = next(i for i, step in enumerate(steps) if step["id"] == "measure")
        steps.insert(
            index + 1, {"id": "age", "kind": "delay", "duration_ms": 600}
        )

    clock = TestClock()
    plugins = _plugins_for(clock)
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert "stale" in result.reasons[0]
    by_step = _events_by_step(result)
    assert by_step["voltage"]["error_code"] == "INVALID_SAMPLE"
    # freshness is measured from acquisition: 600 ms elapsed vs max_age 500
    assert 600_000_000 in clock.waits


def test_multi_value_dataset_is_not_scalar(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    psu_calls.hook = _override_first_measure(
        clock,
        [_stub_variable("voltage", "V", 5.0, values=[5.0, 5.1])],
    )
    docs = admit()
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert "not_scalar" in result.reasons[0]
    assert _events_by_step(result)["voltage"]["error_code"] == "INVALID_SAMPLE"


def test_nonempty_dimensions_is_not_scalar(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    psu_calls.hook = _override_first_measure(
        clock,
        [_stub_variable("voltage", "V", 5.0, dimensions=["sweep"])],
    )
    docs = admit()
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert "not_scalar" in result.reasons[0]


def test_unknown_required_uncertainty_is_invalid(tmp_path: Path) -> None:
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    psu_calls.hook = _override_first_measure(
        clock,
        [_stub_variable("voltage", "V", 5.0, uncertainty={"status": "unknown"})],
    )
    docs = admit()
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert "unknown_uncertainty" in result.reasons[0]
    assert _events_by_step(result)["voltage"]["error_code"] == "INVALID_SAMPLE"


def test_conservative_interval_escape_is_assertion_failed(tmp_path: Path) -> None:
    """Headline truthfulness: the interval decides, not the nominal value."""
    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    # Nominal 5.08 is INSIDE [4.9, 5.1]; the interval [5.03, 5.13] escapes.
    psu_calls.hook = _override_first_measure(
        clock, [_stub_variable("voltage", "V", 5.08)]
    )
    docs = admit()
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "assertion_failed"  # not completed, not an error
    by_step = _events_by_step(result)
    assert by_step["check"]["status"] == "failed"
    assert any("escapes" in reason for reason in result.reasons)
    assert "branch" not in by_step  # the body ended at the assert

    # Unit-level pin of the three-valued comparison on the same numbers.
    predicate = {"sample": "v", "minimum": 4.9, "maximum": 5.1}
    conservative = SampleOutcome(5.08, 0.05, None, None)
    nominal_only = SampleOutcome(5.08, None, None, None)
    passing = SampleOutcome(5.0, 0.05, None, None)
    invalid = SampleOutcome(None, None, None, "stale")
    assert evaluate_predicate(predicate, {"v": conservative}) is False
    assert evaluate_predicate(predicate, {"v": nominal_only}) is True
    assert evaluate_predicate(predicate, {"v": passing}) is True
    assert evaluate_predicate(predicate, {"v": invalid}) is None
    assert evaluate_predicate(predicate, {}) is None


def test_if_false_runs_else_branch_only(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _root_step(graph["procedure"], "check")["predicate"] = {
            "sample": "voltage",
            "minimum": 0.0,
            "maximum": 10.0,
        }
        _root_step(graph["procedure"], "branch")["else"] = [
            {"id": "fallback", "kind": "delay", "duration_ms": 10}
        ]

    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    # 5.6 ± 0.05 → interval [5.55, 5.65] escapes the branch bounds [0.1, 5.5]
    psu_calls.hook = _override_first_measure(
        clock, [_stub_variable("voltage", "V", 5.6)]
    )
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "completed"
    step_ids = [event["occurrence"][1] for event in result.step_events]
    assert "fallback" in step_ids  # else branch executed
    assert "recheck" not in step_ids  # then branch did not
    assert "check-current" not in step_ids
    assert clock.waits.count(10_000_000) == 1  # the fallback delay ran once


def test_if_side_interval_escape_selects_else_end_to_end(tmp_path: Path) -> None:
    """The if predicate decides by the conservative interval, not the nominal.

    5.45 V is nominally INSIDE [0.1, 5.5], but 5.45 ± 0.1 gives [5.35, 5.55]
    whose top escapes the branch bound: a nominal-only comparison would run
    the then-branch; the honest conservative one runs else. This is the
    if-side end-to-end twin of the assert-side headline pin.
    """
    def mutate(graph: dict[str, Any]) -> None:
        _root_step(graph["procedure"], "check")["predicate"] = {
            "sample": "voltage",
            "minimum": 0.0,
            "maximum": 10.0,
        }
        _root_step(graph["procedure"], "branch")["else"] = [
            {"id": "fallback", "kind": "delay", "duration_ms": 10}
        ]

    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    interval_escape = _stub_variable(
        "voltage", "V", 5.45, uncertainty={"status": "known", "absolute": 0.1}
    )
    psu_calls.hook = _override_first_measure(clock, [interval_escape])
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "completed"
    step_ids = [event["occurrence"][1] for event in result.step_events]
    assert "fallback" in step_ids  # the interval escaped: else ran
    assert "recheck" not in step_ids  # a nominal-only predicate would have run then
    assert clock.waits.count(10_000_000) == 1  # the fallback delay ran once


def test_read_parameter_reference_rejected_before_dispatch(tmp_path: Path) -> None:
    """Read parameters are literals by schema; the runtime seam agrees."""
    clock = TestClock()
    plugins = _plugins_for(clock)
    controller_calls = _RecordingPlugin(plugins["controller"])
    plugins["controller"] = controller_calls
    docs = admit()
    procedure = copy.deepcopy(docs.procedure)
    model = next(step for step in procedure["steps"] if step["id"] == "model")
    model["parameter"] = {
        "$stg_ref": {"step": "configure", "pointer": "/configuration_id"}
    }
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert result.reasons[0].startswith("unresolved_reference:")
    # only the note write reached the controller; the model read never dispatched
    assert [request.verb for request, _ in controller_calls.calls] == [
        OperationVerb.WRITE
    ]
    by_step = _events_by_step(result)
    assert by_step["model"]["error_code"] == "UNRESOLVED_REFERENCE"


def _procedure_with_model_before_note(docs: AdmittedDocuments) -> dict[str, Any]:
    """Fixture copy with the model read reordered ahead of the note write.

    Admission's lexical scope rejects a note→model reference as a future
    reference (correctly), so the read/write ``$stg_ref`` tests reorder the
    two steps in an in-memory copy and hand it straight to the executor —
    the established executor-direct pattern; admission is not re-run.
    """
    procedure = copy.deepcopy(docs.procedure)
    steps = procedure["steps"]
    model = next(step for step in steps if step["id"] == "model")
    steps.remove(model)
    note_index = next(i for i, step in enumerate(steps) if step["id"] == "note")
    steps.insert(note_index, model)
    return procedure


def test_stg_ref_to_read_step_resolves_into_later_write(tmp_path: Path) -> None:
    """execution-contract §3: a read step's Reading is referable downstream.

    ``$stg_ref`` walks the projected Reading fields (``/value`` here) into a
    later write's value: the controller receives exactly the string it
    reported, and the body completes.
    """
    clock = TestClock()
    plugins = _plugins_for(clock)
    controller_calls = _RecordingPlugin(plugins["controller"])
    plugins["controller"] = controller_calls
    docs = admit()
    procedure = _procedure_with_model_before_note(docs)
    note = next(step for step in procedure["steps"] if step["id"] == "note")
    note["value"] = {"$stg_ref": {"step": "model", "pointer": "/value"}}
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "completed"
    assert result.reasons == []
    writes = [
        request.arguments["value"]
        for request, _ in controller_calls.calls
        if request.verb is OperationVerb.WRITE
    ]
    assert writes == ["sim-controller-1"]


def test_stg_ref_to_write_receipt_resolves(tmp_path: Path) -> None:
    """§3: a write step's WriteReceipt is referable by later action input."""
    clock = TestClock()
    plugins = _plugins_for(clock)
    controller_calls = _RecordingPlugin(plugins["controller"])
    plugins["controller"] = controller_calls
    docs = admit()
    procedure = copy.deepcopy(docs.procedure)
    steps = procedure["steps"]
    note_index = next(i for i, step in enumerate(steps) if step["id"] == "note")
    steps.insert(
        note_index + 1,
        {
            "id": "echo-note",
            "kind": "write",
            "role": "dut",
            "parameter": "operator_note",
            "value": {"$stg_ref": {"step": "note", "pointer": "/requested_value"}},
            "timeout_ms": 200,
        },
    )
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "completed"
    assert result.reasons == []
    writes = [
        request.arguments["value"]
        for request, _ in controller_calls.calls
        if request.verb is OperationVerb.WRITE
    ]
    assert writes == ["wp05 run", "wp05 run"]


def test_stg_ref_into_absent_reading_field_fails_honestly(tmp_path: Path) -> None:
    """A pointer to a field the Reading projection lacks is a ScopeError.

    The projection carries every Reading field, so ``/no_such_field`` is a
    genuine miss — the body ends ``execution_error`` before dispatch, never
    silently defaulting.
    """
    clock = TestClock()
    plugins = _plugins_for(clock)
    controller_calls = _RecordingPlugin(plugins["controller"])
    plugins["controller"] = controller_calls
    docs = admit()
    procedure = _procedure_with_model_before_note(docs)
    note = next(step for step in procedure["steps"] if step["id"] == "note")
    note["value"] = {"$stg_ref": {"step": "model", "pointer": "/no_such_field"}}
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "execution_error"
    assert result.reasons[0].startswith("unresolved_reference:")
    assert "no_such_field" in result.reasons[0]
    writes = [
        request.arguments["value"]
        for request, _ in controller_calls.calls
        if request.verb is OperationVerb.WRITE
    ]
    assert writes == []  # the consuming write never dispatched


def test_nested_if_inside_repeat_composes(tmp_path: Path) -> None:
    def mutate(graph: dict[str, Any]) -> None:
        _widen_check_current(graph)
        _root_step(graph["procedure"], "loop")["steps"].append(
            {
                "id": "loop-branch",
                "kind": "if",
                "predicate": {"sample": "voltage-again", "minimum": 0.1, "maximum": 5.5},
                "then": [{"id": "loop-note", "kind": "delay", "duration_ms": 5}],
                "else": [],
            }
        )

    clock = TestClock()
    plugins = _plugins_for(clock)
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock)

    result = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=_body_deadline(clock, docs)
    )

    assert result.body_outcome == "completed"
    assert result.reasons == []
    loop_notes = [
        event["occurrence"]
        for event in result.step_events
        if event["occurrence"][1] == "loop-note"
    ]
    assert loop_notes == [
        [RUN_ID, "loop-note", [0]],
        [RUN_ID, "loop-note", [1]],
        [RUN_ID, "loop-note", [2]],
    ]
    assert clock.waits.count(5_000_000) == 3  # nested then-branch ran per iteration


def test_nested_if_in_repeat_replays_from_shared_ledger(tmp_path: Path) -> None:
    """Occurrence identity survives re-entered nested control flow on replay.

    A second run_body over the shared ledger must answer the loop's nested
    if decisions and their then-branch occurrences from the ledger: no new
    dispatch, no new wait, and an identical event stream. (The single-run
    composition is pinned by the test above; the ledger-replay test near the
    top of this section covers root + repeat but no if nested in a repeat.)
    """
    def mutate(graph: dict[str, Any]) -> None:
        _widen_check_current(graph)
        _root_step(graph["procedure"], "loop")["steps"].append(
            {
                "id": "loop-branch",
                "kind": "if",
                "predicate": {"sample": "voltage-again", "minimum": 0.1, "maximum": 5.5},
                "then": [{"id": "loop-note", "kind": "delay", "duration_ms": 5}],
                "else": [],
            }
        )

    clock = TestClock()
    plugins = _plugins_for(clock)
    psu_calls = _wrapped_psu(plugins)
    ledger: dict[tuple[str, str, tuple[int, ...]], dict[str, Any]] = {}
    docs = readmit_mutated(tmp_path, mutate)
    executor = _executor_for(docs, plugins, clock, ledger)
    body_deadline_ns = _body_deadline(clock, docs)

    first = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=body_deadline_ns
    )
    assert first.body_outcome == "completed"
    dispatches_after_first = list(psu_calls.calls)
    waits_after_first = list(clock.waits)
    occurrences_after_first = set(ledger)

    second = executor.run_body(
        docs.procedure, run_id=RUN_ID, body_deadline_ns=body_deadline_ns
    )

    assert second.body_outcome == "completed"
    assert psu_calls.calls == dispatches_after_first  # no physical work repeated
    assert clock.waits == waits_after_first  # the nested delays were not re-waited
    assert set(ledger) == occurrences_after_first  # occurrence identity is stable
    assert second.step_events == first.step_events
    # The nested control-flow occurrences themselves are in the ledger: the
    # per-iteration if decisions and their then-branch steps.
    assert {key[1] for key in ledger} >= {"loop-branch", "loop-note"}


# --- Task 8: the full coordinated run ------------------------------------------


def test_start_run_full_pass_over_pristine_fixture(tmp_path: Path) -> None:
    """The final WP05 integration: admit, lease, monitor, execute, protect, record.

    The pristine fixture (bounds widened so honest intervals fit) runs to a
    ``passed`` terminal record with a verified safe state, a schema-valid
    run record, every one of the eight step kinds in the durable event
    stream, and a released bench lease.
    """
    clock = TestClock()
    plugins = _plugins_for(clock)
    store = Store.open(tmp_path / "state.db")
    docs = admit()
    coordinator = RunCoordinator(store, plugins, clock, clock, docs)

    record = coordinator.start_run(RUN_ID, "principal-a")

    assert record["outcome"] == "passed"
    assert record["body_outcome"] == "completed"
    assert record["safe_state"] == "verified"
    assert record["reasons"] == []
    assert record["binding"] == {
        "id": docs.binding["request_id"],
        "version": docs.binding["contract_version"],
        "sha256": docs.digests["binding"],
    }
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "standards" / "execution-v1.0.0"
         / "run-record.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(record)
    run = store.get_run(RUN_ID)
    assert run is not None
    assert run["terminal"] == record

    events = store.read_events(f"run:{RUN_ID}")
    assert events, "the durable event stream is non-empty"
    assert [int(event["sequence"]) for event in events] == list(
        range(1, len(events) + 1)
    )
    assert {event["kind"] for event in events} == {
        "invoke", "read", "write", "delay", "sample", "assert", "if", "repeat"
    }

    assert store.get_active_lease("sim-bench") is None  # the lease was released
    store.close()
