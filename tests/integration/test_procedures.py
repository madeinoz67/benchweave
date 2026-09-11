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
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from benchweave.control.binding import BindingError, release, reserve, resolve_binding
from benchweave.control.documents import AdmissionRejected, AdmittedDocuments, admit_documents
from benchweave.control.policy import (
    PolicyDenied,
    SignalValue,
    check_allowed,
    evaluate_conditions,
)
from benchweave.control.semantics import check_semantics, worst_case_body_ms
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
    assert evaluate_conditions(admit().policy, snapshot) == [
        "dut-voltage-bounds: unit_mismatch: expected V, have A"
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
