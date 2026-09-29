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
            # D9 discipline: nothing persisted for the refused start — the
            # SCOPED key the requests table actually keys on (fold row 6:
            # the pre-fold arm queried the raw request id against
            # sha256-keyed storage — always None, vacuous).
            from benchweave.interfaces.operations import scoped_request_key

            scoped = scoped_request_key("p1", "run_start", str(ref["id"]))
            assert store.find_request(scoped) is None
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


class TestFoldRow1SeamClassificationRefuses:
    """Fold row 1 (the triplicated HIGH): the seam's classification step
    DECIDES — a stored bench whose contract_version is a refused class
    refuses typed at the POST with the VR-37 fields, instead of the
    pre-fold 202-then-outcome_unknown. RED at the fold base: every cell
    below 202-accepted (the record was computed and discarded)."""

    def _start_with_stored_bench(
        self,
        tmp_path: Path,
        contract_version: str,
        *,
        contracts_override: Path | None = None,
    ) -> tuple[str, str]:
        """Admit the 0.1.0 lattice, store a bench document whose
        contract_version is ``contract_version`` under a fresh digest, and
        run_start against it. Returns (code, message)."""
        import json as _json

        from benchweave.interfaces import errors
        from benchweave.interfaces.bootstrap import content_sha
        from benchweave.interfaces.identity import Identity
        from benchweave.interfaces.operations import Operations
        from benchweave.interfaces.validation import SeamValidator
        from benchweave.interfaces.worker import RunWorker
        from benchweave.vendoring import active_contract_family

        lattice = tmp_path / "lattice"
        shutil.copytree(LATTICE_010, lattice)
        store = Store.open(tmp_path / "state.db")
        try:
            content = ContentStore(store)
            admit_startup_bench(store, content, lattice, now=NOW_WALL)
            bench = _json.loads((lattice / "bench.json").read_bytes())
            bench["contract_version"] = contract_version
            bench_bytes = _json.dumps(bench).encode()
            bench_sha = content_sha(content, bench_bytes, bench, NOW_WALL)
            binding = _json.loads((lattice / "run-binding.json").read_bytes())
            binding["bench"] = {"sha256": bench_sha}
            binding_bytes = _json.dumps(binding).encode()
            binding_sha = content_sha(content, binding_bytes, binding, NOW_WALL)
            ref = {
                "id": str(binding["request_id"]),
                "version": str(binding["contract_version"]),
                "sha256": binding_sha,
            }
            worker = RunWorker(
                store, content, build_run=lambda *a: None, now_iso=lambda: NOW_WALL
            )
            ops = Operations(
                store,
                content,
                validator=SeamValidator(active_contract_family("interface")),
                gateway_id="gw-row1",
                limits=QUOTA_LIMITS,
                worker=worker,
                now_iso=lambda: NOW_WALL,
                contracts=contracts_override
                if contracts_override is not None
                else active_contract_family("execution"),
            )
            ident = Identity("p1", "stg", frozenset({"stg:control"}), 2**31)
            try:
                ops.run_start(ident, "sim-bench", str(ref["id"]), ref, 1, None)
            except errors.OperationFailure as failure:
                return failure.failure.code, failure.failure.message
            return "accepted", ""
        finally:
            store.close()

    def test_never_carried_bench_refuses_at_the_post(self, tmp_path: Path) -> None:
        """9.9.9 (never carried) — version_unknown with the five VR-37
        fields inline; typed, not 202."""
        code, message = self._start_with_stored_bench(tmp_path, "9.9.9")
        assert code == "policy_denied", (code, message)
        assert message.startswith("version_unknown:"), message
        for field in ("standard: execution", "supported:", "move-to:"):
            assert field in message, message

    def test_retired_bench_refuses_at_the_post(self, tmp_path: Path) -> None:
        """execution 1.0.0 is RETIRED (the R4 classifier's own fixture) —
        retired_identifier: at the POST."""
        code, message = self._start_with_stored_bench(tmp_path, "1.0.0")
        assert code == "policy_denied", (code, message)
        assert message.startswith("retired_identifier:"), message

    def test_nonconforming_bench_refuses_at_the_post(self, tmp_path: Path) -> None:
        """A retained out-of-range execution pin — standard_nonconforming:
        with the VR-37 fields (no ack path for the execution family). The
        REAL corpus carries no nonconforming execution version (0.1.0 and
        0.2.0 are both served in-range), so the probe narrows a COPIED
        corpus's policy range — the honest way to make the cell reachable —
        and points the seam's contracts at the copy."""
        import json as _json

        corpus = tmp_path / "narrowed-standards"
        shutil.copytree(ROOT / "standards", corpus)
        manifest_path = corpus / "standards-manifest.json"
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["dependency_policy"]["standards"]["execution"]["range"] = (
            ">=0.2.0,<0.3.0"
        )
        manifest_path.write_text(_json.dumps(manifest, indent=2))
        narrowed = corpus / "execution" / "0.2.0"
        code, message = self._start_with_stored_bench(
            tmp_path, "0.1.0", contracts_override=narrowed
        )
        assert code == "policy_denied", (code, message)
        assert message.startswith("standard_nonconforming:"), message
        assert "move-to:" in message, message


class TestFoldUnstoredDescriptorSkip:
    """Fold addendum (adv260b part 2, Risk 2's other half): the pre-check's
    UNSTORED-DESCRIPTOR skip is pinned as the disclosed residual — a stored
    bench whose descriptor digest does not resolve skips the pre-check
    silently and the start 202-accepts (the worker's poison guard owns it:
    the run dies at admission as ``outcome_unknown``). The skip is a
    pass-through, never an admission."""

    def test_unstored_descriptor_skips_the_pre_check_and_202s(
        self, tmp_path: Path
    ) -> None:
        import json as _json

        from benchweave.interfaces.bootstrap import content_sha
        from benchweave.interfaces.identity import Identity
        from benchweave.interfaces.operations import Operations
        from benchweave.interfaces.validation import SeamValidator
        from benchweave.interfaces.worker import RunWorker
        from benchweave.vendoring import active_contract_family

        lattice = tmp_path / "lattice"
        shutil.copytree(LATTICE_010, lattice)
        store = Store.open(tmp_path / "state.db")
        try:
            content = ContentStore(store)
            admit_startup_bench(store, content, lattice, now=NOW_WALL)
            bench = _json.loads((lattice / "bench.json").read_bytes())
            # The descriptor digest names NOTHING in the content store:
            bench["devices"][0]["descriptor"]["sha256"] = "f" * 64
            bench_bytes = _json.dumps(bench).encode()
            bench_sha = content_sha(content, bench_bytes, bench, NOW_WALL)
            binding = _json.loads((lattice / "run-binding.json").read_bytes())
            binding["bench"] = {"sha256": bench_sha}
            binding_bytes = _json.dumps(binding).encode()
            binding_sha = content_sha(content, binding_bytes, binding, NOW_WALL)
            ref = {
                "id": str(binding["request_id"]),
                "version": str(binding["contract_version"]),
                "sha256": binding_sha,
            }
            worker = RunWorker(
                store, content, build_run=lambda *a: None, now_iso=lambda: NOW_WALL
            )
            ops = Operations(
                store,
                content,
                validator=SeamValidator(active_contract_family("interface")),
                gateway_id="gw-skip",
                limits=QUOTA_LIMITS,
                worker=worker,
                now_iso=lambda: NOW_WALL,
            )
            ident = Identity("p1", "stg", frozenset({"stg:control"}), 2**31)
            result = ops.run_start(ident, "sim-bench", str(ref["id"]), ref, 1, None)
            # The 202 posture: accepted at the seam (the pre-check skipped),
            # the refusal class deferred to the worker.
            assert result.get("run_id"), result
            assert result.get("state") == "accepted", result
        finally:
            store.close()


class TestFoldRow2FloorBoundaryTable:
    """Fold row 2: the floor's comparator is total — every raw pin value
    yields a TYPED refusal or a pass across both row shapes, never an
    untyped ValueError at the wire. RED at the fold base: the malformed
    cells raised ValueError out of Interval.contains."""

    VALUES = ("", "garbage", "0.2.0-dev", "1.2.3", "0.2.2", "0.1.2", "9.9.9")

    def _corpus_copy(self, tmp_path: Path, *, drop_otdp_leg: bool) -> Path:
        corpus = tmp_path / ("adapter-only" if drop_otdp_leg else "otdp-leg")
        shutil.copytree(ROOT / "standards", corpus)
        if drop_otdp_leg:
            import json as _json

            row_path = corpus / "cross-constraints.json"
            document = _json.loads(row_path.read_text(encoding="utf-8"))
            for row in document.get("rows", []):
                if row.get("standard") == "execution" and row.get("version") == "0.2.0":
                    row.get("requires", {}).pop("otdp", None)
            row_path.write_text(_json.dumps(document, indent=2))
        return corpus / "execution" / "0.2.0"

    def _pins(self, version: str) -> dict[str, Any]:
        from benchweave.control.documents import DescriptorPin

        return {
            "psu": DescriptorPin(
                otdp_version=version, status="served", conformance="conforming"
            )
        }

    def _assert_typed_or_pass(
        self,
        tmp_path: Path,
        *,
        drop_otdp_leg: bool,
    ) -> None:
        """The row-2 table body: every value × every row shape × both
        helpers yields TYPED (AdmissionRejected) or a pass — never an
        untyped ValueError out of the interval comparator."""
        from functools import partial

        from benchweave.control.documents import _check_cross_constraints, _check_run_floor

        contracts = self._corpus_copy(tmp_path, drop_otdp_leg=drop_otdp_leg)
        for value in self.VALUES:
            pins = self._pins(value)
            for name, call in (
                (
                    "admission rows",
                    partial(_check_cross_constraints, "0.2.0", pins),
                ),
                ("run floor", partial(_check_run_floor, pins, contracts)),
            ):
                try:
                    call()
                except AdmissionRejected:
                    pass  # typed
                except ValueError as exc:
                    raise AssertionError(
                        f"{name} raised UNTYPED ValueError for {value!r}: {exc}"
                    ) from exc

    def test_otdp_leg_row_is_typed_or_pass(self, tmp_path: Path) -> None:
        self._assert_typed_or_pass(tmp_path, drop_otdp_leg=False)

    def test_adapter_only_row_is_typed_or_pass(self, tmp_path: Path) -> None:
        self._assert_typed_or_pass(tmp_path, drop_otdp_leg=True)


class TestFoldRow9DisclosureRenderer:
    """Fold row 9: the ONE renderer's full text, pinned verbatim."""

    def test_full_text(self) -> None:
        from benchweave.control.coordinator import _implementation_disclosure

        assert (
            _implementation_disclosure("0.2.0", "0.1.0", "executed")
            == "implementation_disclosure: gateway composition execution@0.2.0 "
            "executed lattice execution@0.1.0"
        )
        assert (
            _implementation_disclosure("0.2.0", "0.1.0", "recovered")
            == "implementation_disclosure: gateway composition execution@0.2.0 "
            "recovered lattice execution@0.1.0"
        )


class TestFoldRow10SeamWorkerByteIdentity:
    """Fold row 10 / Risk 4's machine check: for ONE below-floor fixture the
    seam's refusal message and the worker's refusal message are
    BYTE-IDENTICAL (both key by the bench's device id, one helper, one
    vocabulary). RED at the fold base: the two strings differed (the seam
    keyed by descriptor id)."""

    def test_refusal_strings_match(self, tmp_path: Path) -> None:
        import json as _json

        from benchweave.interfaces import errors
        from benchweave.interfaces.bootstrap import content_sha
        from benchweave.interfaces.identity import Identity
        from benchweave.interfaces.operations import Operations
        from benchweave.interfaces.validation import SeamValidator
        from benchweave.interfaces.worker import RunWorker
        from benchweave.vendoring import active_contract_family

        lattice = _below_floor_lattice(tmp_path)
        store = Store.open(tmp_path / "state.db")
        try:
            content = ContentStore(store)
            admit_startup_bench(store, content, lattice, now=NOW_WALL)
            # Worker leg: the factory's floor refusal.
            ref, _raw = _binding_ref(lattice)
            factory = _build_run_factory(
                lattice, SystemClock().now_iso, limits=QUOTA_LIMITS
            )
            with pytest.raises(AdmissionRejected) as worker_raised:
                factory("run-identity-1", "p1", ref, store)
            worker_message = str(worker_raised.value)

            # Seam leg: the same fixture through run_start.
            content_sha(content, _raw, _json.loads(_raw), NOW_WALL)
            worker2 = RunWorker(
                store, content, build_run=lambda *a: None, now_iso=lambda: NOW_WALL
            )
            ops = Operations(
                store,
                content,
                validator=SeamValidator(active_contract_family("interface")),
                gateway_id="gw-identity",
                limits=QUOTA_LIMITS,
                worker=worker2,
                now_iso=lambda: NOW_WALL,
            )
            ident = Identity("p1", "stg", frozenset({"stg:control"}), 2**31)
            with pytest.raises(errors.OperationFailure) as seam_raised:
                ops.run_start(ident, "sim-bench", str(ref["id"]), ref, 1, None)
            assert seam_raised.value.failure.message == worker_message, (
                f"seam:   {seam_raised.value.failure.message!r}\n"
                f"worker: {worker_message!r}"
            )
        finally:
            store.close()


class TestFoldRow6D9SubArmIsReal:
    """Fold row 6: G2's D9 sub-arm queries the SCOPED key (the old arm
    queried the raw request id against sha256-keyed storage — always None,
    vacuous). The positive control proves the query CAN find a filed key."""

    def test_absent_key_is_a_real_query(self, tmp_path: Path) -> None:
        from benchweave.state.store import Store as _Store

        store = _Store.open(tmp_path / "d9.db")
        try:
            key = __import__(
                "benchweave.interfaces.operations", fromlist=["scoped_request_key"]
            ).scoped_request_key("p1", "run_start", "req-d9-1")
            # The honest absence for the refused start:
            assert store.find_request(key) is None
            # Positive control: the SAME query finds a filed key.
            accepted = store.accept_request(key, "a" * 64, "run-d9-control", NOW_WALL)
            assert accepted.outcome != "duplicate"
            filed = store.find_request(key)
            assert filed is not None and filed["run_id"] == "run-d9-control"
        finally:
            store.close()
