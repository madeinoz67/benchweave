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
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from benchweave.control.binding import BindingError, release, reserve, resolve_binding
from benchweave.control.clocking import SystemClock, TestClock
from benchweave.control.documents import AdmissionRejected, AdmittedDocuments, admit_documents
from benchweave.control.executor import Executor, canonical_json
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
    path = PLUGINS_ROOT / name / "plugin.py"
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
    return readmit_mutated(tmp_path, _literalize_inputs)


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
