"""The record lane (issue #260): runs are an implemented-dialect fact.

G1-G3 and G7 of the design's pre-committed acceptance, over the recovered
``tests/fixtures/lattice-execution-0.1.0/`` (unchanged) and the F1b
below-floor shape. RED proofs neutralized ONE mechanism at a time; counts
and exit codes from junitxml/true exits.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.control.clocking import SystemClock
from benchweave.control.documents import AdmissionRejected, _versioned_schema_path
from benchweave.interfaces.app import _build_run_factory
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
LATTICE_010 = ROOT / "tests" / "fixtures" / "lattice-execution-0.1.0"
NOW_WALL = "2026-09-23T00:00:00Z"
#: The seam's limit shape (test_seam_control's LIMITS): every key the
#: retention arithmetic and the worker read.
QUOTA_LIMITS = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
    "max_runs_retained": 8,
}


def _binding_ref(lattice: Path) -> tuple[dict[str, Any], bytes]:
    raw = (lattice / "run-binding.json").read_bytes()
    binding = json.loads(raw)
    ref = {
        "id": str(binding["request_id"]),
        "version": str(binding["contract_version"]),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return ref, raw


def _below_floor_lattice(tmp_path: Path) -> Path:
    """F1b's file shape: the 0.1.0 lattice with the psu pin dropped to
    otdp 0.1.2 (retained, out-of-range) behind the recorded operator
    acknowledgement — admits at startup on the rowless 0.1.0 bench, below
    the COMPOSITION's (0.2.0) implemented-dialect row. The digest web
    re-pins in dependency order (psu → bench → commissioning → binding),
    the per-pin suite's ``_spool_and_repin`` pattern."""
    lattice = tmp_path / "below-floor"
    shutil.copytree(LATTICE_010, lattice)

    def rewrite(name: str, document: dict[str, Any]) -> str:
        (lattice / name).write_text(json.dumps(document, indent=2))
        return hashlib.sha256((lattice / name).read_bytes()).hexdigest()

    psu = json.loads((lattice / "descriptor-sim-psu.json").read_bytes())
    psu["otdp_version"] = "0.1.2"
    psu_digest = rewrite("descriptor-sim-psu.json", psu)

    bench = json.loads((lattice / "bench.json").read_bytes())
    for device in bench["devices"]:
        if device["id"] == "psu":
            device["descriptor"]["sha256"] = psu_digest
    bench_digest = rewrite("bench.json", bench)

    commissioning = json.loads((lattice / "commissioning.json").read_bytes())
    commissioning["bench"]["sha256"] = bench_digest
    rewrite("commissioning.json", commissioning)
    commissioning_digest = hashlib.sha256(
        (lattice / "commissioning.json").read_bytes()
    ).hexdigest()

    binding = json.loads((lattice / "run-binding.json").read_bytes())
    binding["bench"]["sha256"] = bench_digest
    binding["commissioning"]["sha256"] = commissioning_digest
    rewrite("run-binding.json", binding)

    (lattice / "operator-acknowledgements.json").write_text(
        json.dumps({"acknowledgements": {"psu": "0.1.2"}})
    )
    return lattice


class TestG1RunOnPinnedOldLattice:
    """G1: a run over the recovered 0.1.0 lattice completes; the record
    carries the LATTICE's version and validates at it. RED at base: the
    #220 guard refused (test_f3's then-expectation)."""

    def test_run_completes_and_record_carries_the_lattice_version(
        self, tmp_path: Path
    ) -> None:
        lattice = tmp_path / "lattice"
        shutil.copytree(LATTICE_010, lattice)
        store = Store.open(tmp_path / "state.db")
        try:
            content = ContentStore(store)
            admit_startup_bench(store, content, lattice, now=NOW_WALL)
            ref, _raw = _binding_ref(lattice)
            factory = _build_run_factory(
                lattice, SystemClock().now_iso, limits=QUOTA_LIMITS
            )
            coordinator = factory("run-g1-1", "principal-g1", ref, store)
            record = coordinator.start_run("run-g1-1", "principal-g1")
            assert record["contract_version"] == "0.1.0", record
            assert record["binding"]["version"] == "0.1.0"
            assert any(
                reason.startswith("implementation_disclosure:")
                and "execution@0.2.0" in reason
                and "execution@0.1.0" in reason
                for reason in record["reasons"]
            ), record["reasons"]
            # Re-validate the persisted record bytes against the
            # digest-verified 0.1.0 schema (G1's own KILL arm).
            persisted = store.get_run("run-g1-1")
            assert persisted is not None and persisted["terminal"] is not None
            from jsonschema import Draft202012Validator

            Draft202012Validator(
                json.loads(_g1_schema_path().read_text(encoding="utf-8"))
            ).validate(persisted["terminal"])
        finally:
            store.close()


def _g1_schema_path() -> Path:
    """The digest-verified 0.1.0 run-record schema from the REAL corpus."""
    from benchweave.control.documents import _corpus_root_of
    from benchweave.vendoring import active_contract_family

    return _versioned_schema_path(
        _corpus_root_of(active_contract_family("execution")),
        "execution",
        "0.1.0",
        "run-record.schema.json",
    )


class TestG2SynchronousFloorRefusal:
    """G2: a below-floor run start refuses SYNCHRONOUSLY — typed
    policy_denied, cross_constraint_violation: prefix, no run row, no §9
    request key, no 202. RED at base: the call 202-accepted (the guard
    refused inside the worker instead)."""

    def test_below_floor_start_refuses_at_the_seam(self, tmp_path: Path) -> None:
        from benchweave.interfaces import errors
        from benchweave.interfaces.operations import Operations
        from benchweave.interfaces.validation import SeamValidator
        from benchweave.interfaces.worker import RunWorker
        from benchweave.vendoring import active_contract_family

        lattice = _below_floor_lattice(tmp_path)
        store = Store.open(tmp_path / "state.db")
        try:
            content = ContentStore(store)
            admit_startup_bench(store, content, lattice, now=NOW_WALL)
            ref, raw = _binding_ref(lattice)
            # The binding document rides the content store (D4's true-ref
            # discipline): the seam's request-id match and the runnability
            # pre-check both read it by digest.
            from benchweave.interfaces.bootstrap import content_sha

            content_sha(content, raw, json.loads(raw), NOW_WALL)
            worker = RunWorker(
                store, content, build_run=lambda *a: None, now_iso=lambda: NOW_WALL
            )
            ops = Operations(
                store,
                content,
                validator=SeamValidator(active_contract_family("interface")),
                gateway_id="gw-g2",
                limits=QUOTA_LIMITS,
                worker=worker,
                now_iso=lambda: NOW_WALL,
            )

            from benchweave.interfaces.identity import Identity

            ident = Identity("p1", "stg", frozenset({"stg:control"}), 2**31)
            with pytest.raises(errors.OperationFailure) as raised:
                ops.run_start(ident, "sim-bench", str(ref["id"]), ref, 1, None)
            failure = raised.value.failure
            assert failure.code == "policy_denied", failure
            assert failure.message.startswith("cross_constraint_violation:"), failure
            assert "otdp@0.1.2" in failure.message, failure
            assert "execution@0.2.0" in failure.message, failure
            assert "PR #201" in failure.message, failure
            # D9 discipline: nothing persisted for the refused start.
            assert store.find_request(f"p1|run_start|{ref['id']}") is None
            assert not [
                row for row in store.list_run_states("sim-bench")
                if row["state"] != "terminal"
            ]
            assert not worker.submitted
        finally:
            store.close()

    def test_worker_floor_is_authoritative_over_the_full_admission(
        self, tmp_path: Path
    ) -> None:
        """The worker layer of the two-layer rule: the below-floor lattice
        at the WORKER (past any seam) refuses AdmissionRejected with the
        same vocabulary, before any device plan or bridge exists. (G3's
        neutralization proves THIS check is the refusing mechanism at the
        worker; the seam test above proves its own.)"""
        lattice = _below_floor_lattice(tmp_path)
        store = Store.open(tmp_path / "state.db")
        try:
            content = ContentStore(store)
            admit_startup_bench(store, content, lattice, now=NOW_WALL)
            ref, _raw = _binding_ref(lattice)
            factory = _build_run_factory(
                lattice, SystemClock().now_iso, limits=QUOTA_LIMITS
            )
            with pytest.raises(AdmissionRejected) as raised:
                factory("run-g2b", "principal-g2", ref, store)
            assert str(raised.value).startswith("cross_constraint_violation:"), (
                str(raised.value)
            )
            assert "this gateway runs" in str(raised.value)
        finally:
            store.close()


class TestG3FloorIsTheMechanism:
    """G3 (the anti-vacuous arm): with ONLY the floor neutralized (worker +
    seam sites), the below-floor fixture STARTS — proving the floor is the
    refusing mechanism, not incidental plumbing."""

    def test_neutralized_floor_lets_the_below_floor_run_start(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import benchweave.interfaces.app as app_module
        import benchweave.interfaces.operations as operations_module

        def _no_floor(pins: object, contracts: object) -> None:
            return None

        monkeypatch.setattr(app_module, "_check_run_floor", _no_floor)
        monkeypatch.setattr(operations_module, "_check_run_floor", _no_floor)
        lattice = _below_floor_lattice(tmp_path)
        store = Store.open(tmp_path / "state.db")
        try:
            content = ContentStore(store)
            admit_startup_bench(store, content, lattice, now=NOW_WALL)
            ref, _raw = _binding_ref(lattice)
            factory = _build_run_factory(
                lattice, SystemClock().now_iso, limits=QUOTA_LIMITS
            )
            coordinator = factory("run-g3-1", "principal-g3", ref, store)
            record = coordinator.start_run("run-g3-1", "principal-g3")
            # The run STARTED (the guard is gone and the floor is out):
            # its record threads the lattice's own version.
            assert record["contract_version"] == "0.1.0", record
        finally:
            store.close()


class TestG7SpliceRider:
    """G7: no ``retired_identifier::`` double-colon rendering remains —
    single-colon pinned (the rider, §1.5)."""

    def test_retired_identifier_renders_single_colon(self, tmp_path: Path) -> None:
        from benchweave.control.documents import _authorise_pin, classify_descriptor_pin

        record = classify_descriptor_pin("0.3.0")
        assert record.status == "retired", record
        with pytest.raises(AdmissionRejected) as raised:
            _authorise_pin("dev.example", record, acknowledged_pin=None, now_wall=None)
        message = str(raised.value)
        assert message.startswith("retired_identifier: "), message
        assert "::" not in message, message
