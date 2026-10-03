"""The unattended-grant gate (issue #316): the two-layer refusal matrix.

Design record ``.claude/deep-review/2026-10-03-issue316-endurance-authz-design.md``
§5, pre-committed before any result was read: a closed mutation product over
the demo lattice — 8 illegal cells (each refuses at the SEAM, typed
``policy_denied``, message carrying its named prefix), 4 legal cells (admit
at the seam and reach a terminal record through the real factory), 5 parity
arms (the worker layer's refusal string is BYTE-IDENTICAL to the seam's for
the same lattice), and the two control arms (the gate neutralized: 0/8
refuse — the matrix measures THIS gate; and the pre-change counterexample —
the origin/main grant facts, supervised-only commissioning under a
``gateway_owned`` procedure — admits without the gate).

The corpus already specifies the rule (commissioning ``modes`` + the
``unattended`` evidence category + ``expires_at``; procedure ``mode``; the
execution contract's run-time clauses); this module pins the GATEWAY
enforcement of it, mirroring the offline census's vocabulary ("missing
unattended grant"; a passing ``unattended``-category evidence row). One
helper, one vocabulary, two enforcement points — the issue #260 shape.

Replay precedence is structural, as it is for the floor: the §9 peek
precedes every §5 pre-check in ``run_start``'s order, so the replay arm
here pins the live-replay shape only.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.control.documents import AdmissionRejected
from benchweave.interfaces import errors
from benchweave.interfaces.app import _build_run_factory
from benchweave.interfaces.bootstrap import admit_startup_bench, content_sha
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations, scoped_request_key
from benchweave.interfaces.validation import SeamValidator
from benchweave.interfaces.worker import RunWorker
from benchweave.state.store import Store
from benchweave.vendoring import active_contract_family

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
BENCH_ID = "sim-bench"  # the bootstrap bench (fixtures/execution/bench.json)
#: Fixed seam/worker clock for every arm: the gate is arithmetic on declared
#: values against the CALLER-SUPPLIED now_wall, so one fixed stamp makes
#: both layers' messages byte-comparable.
NOW = "2027-06-01T00:00:00Z"
FAR_EXPIRY = "2030-01-01T00:00:00Z"
#: The run-activation harness's own limits shape (test_execution_pin's
#: QUOTA_LIMITS): every key the retaining quota and the worker seam read.
QUOTA_LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
    "max_dataset_bytes": 8 * 1024 * 1024,
    "max_event_batch": 64,
}


def _ident(principal: str = "p1") -> Identity:
    return Identity(principal, "stg", frozenset({"stg:control"}), 2**31)


def _envelope_evidence() -> dict[str, Any]:
    """The demo lattice's own envelope row, byte-carried from the fixture."""
    commissioning = json.loads((FIXTURES / "commissioning.json").read_bytes())
    row: dict[str, Any]
    for row in commissioning["evidence"]:
        if row["category"] == "envelope":
            return row
    raise AssertionError("the demo commissioning carries no envelope evidence row")


def _passing_unattended_evidence() -> dict[str, Any]:
    """A PASSING ``unattended``-category evidence row — synthetic ids only
    (invented report identity, zero digest), the envelope row's own shape."""
    return {
        "category": "unattended",
        "report": {
            "id": "sim-unattended-report",
            "version": "0.1.0",
            "sha256": "0" * 64,
        },
        "tested_at": "2026-09-11T00:00:00Z",
        "scope": "Simulator unattended-mode endurance: gateway-owned body over the sim lattice.",
        "result": "passed",
        "limitations": [
            "simulator-only"
        ],
    }


def _grant_lattice(
    directory: Path,
    *,
    modes: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    expires_at: str = FAR_EXPIRY,
    procedure_mode: str = "gateway_owned",
    procedure: dict[str, Any] | None = None,
) -> Path:
    """A repinned copy of the demo lattice with the grant fields controlled.

    Defaults to the LEGAL grant shape (supervised + unattended modes, a
    passing ``unattended`` evidence row beside the envelope row, a far
    future expiry); every mutation is expressed against that default. The
    digest web re-pins in dependency order (procedure → commissioning's
    procedure_refs → binding), the per-pin suite's ``_spool_and_repin``
    pattern — the committed tree is never touched.
    """
    shutil.copytree(FIXTURES, directory)
    proc = (
        procedure
        if procedure is not None
        else json.loads((directory / "procedure-voltage-check.json").read_bytes())
    )
    proc["mode"] = procedure_mode
    (directory / "procedure-voltage-check.json").write_text(json.dumps(proc, indent=2))
    proc_digest = hashlib.sha256(
        (directory / "procedure-voltage-check.json").read_bytes()
    ).hexdigest()

    commissioning = json.loads((directory / "commissioning.json").read_bytes())
    commissioning["modes"] = (
        modes if modes is not None else ["supervised", "unattended"]
    )
    commissioning["evidence"] = (
        evidence
        if evidence is not None
        else [_envelope_evidence(), _passing_unattended_evidence()]
    )
    commissioning["expires_at"] = expires_at
    for reference in commissioning["procedure_refs"]:
        if (
            reference["id"] == proc["id"]
            and reference["version"] == proc["version"]
        ):
            reference["sha256"] = proc_digest
    (directory / "commissioning.json").write_text(
        json.dumps(commissioning, indent=2)
    )
    commissioning_digest = hashlib.sha256(
        (directory / "commissioning.json").read_bytes()
    ).hexdigest()

    binding = json.loads((directory / "run-binding.json").read_bytes())
    binding["procedure"]["sha256"] = proc_digest
    binding["commissioning"]["sha256"] = commissioning_digest
    (directory / "run-binding.json").write_text(json.dumps(binding, indent=2))
    return directory


def _binding_ref(lattice: Path) -> dict[str, Any]:
    raw = (lattice / "run-binding.json").read_bytes()
    binding = json.loads(raw)
    return {
        "id": str(binding["request_id"]),
        "version": str(binding["contract_version"]),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


class _Cell:
    """One matrix cell's stack: mutated lattice + admitted store + seam.

    ``real_factory`` wires the worker to the REAL ``_build_run_factory``
    (at ``worker_clock``, which the LOW-2 pins skew against the seam's
    NOW); the default's no-op build keeps the refusal arms synchronous.
    """

    lattice: Path
    store: Store
    ops: Operations
    worker: RunWorker
    ref: dict[str, Any]

    def __init__(
        self,
        tmp_path: Path,
        name: str,
        *,
        real_factory: bool = False,
        worker_clock: str = NOW,
        **kwargs: Any,
    ) -> None:
        self.lattice = _grant_lattice(tmp_path / name, **kwargs)
        self.store = Store.open(tmp_path / f"{name}.db")
        content = ContentStore(self.store)
        admit_startup_bench(self.store, content, self.lattice, now=NOW)
        build: Any = (
            _build_run_factory(self.lattice, lambda: worker_clock, limits=QUOTA_LIMITS)
            if real_factory
            else (lambda *a: None)
        )
        self.worker = RunWorker(
            self.store, content, build_run=build, now_iso=lambda: worker_clock
        )
        self.ops = Operations(
            self.store,
            content,
            validator=SeamValidator(active_contract_family("interface")),
            gateway_id=f"gw-316-{name}",
            limits=QUOTA_LIMITS,
            worker=self.worker,
            now_iso=lambda: NOW,
        )
        self.ref = _binding_ref(self.lattice)

    def close(self) -> None:
        self.worker.stop()
        # The worker thread was never started in refusal arms — join would
        # raise on the unstarted thread; there is nothing to drain.
        with contextlib.suppress(RuntimeError):
            self.worker.join(timeout=10)
        self.store.close()


def _seam_refusal(cell: _Cell, *, lease_id: str | None = None) -> str:
    """Drive run_start to its typed refusal; returns the failure message."""
    with pytest.raises(errors.OperationFailure) as raised:
        cell.ops.run_start(_ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, lease_id)
    failure = raised.value.failure
    assert failure.code == "policy_denied", failure
    return failure.message


def _worker_refusal(cell: _Cell, run_id: str = "run-parity") -> str:
    """The worker layer's refusal for the SAME lattice: the factory over the
    full admission result (past any seam), the #260 Risk-4 leg."""
    factory = _build_run_factory(cell.lattice, lambda: NOW, limits=QUOTA_LIMITS)
    with pytest.raises(AdmissionRejected) as raised:
        factory(run_id, "p1", cell.ref, cell.store)
    return str(raised.value)


def _nothing_persisted(cell: _Cell) -> None:
    """D9 discipline for every refused start: no §9 request key, no run."""
    assert cell.worker.submitted == 0
    assert (
        cell.store.find_request(
            scoped_request_key("p1", "run_start", str(cell.ref["id"]))
        )
        is None
    )
    assert not [
        row for row in cell.store.list_run_states(BENCH_ID) if row["state"] != "terminal"
    ]


# --- illegal cells: the seam refuses, typed, with the named prefix -------------


def test_cell1a_grant_absent_lease_absent_refuses(tmp_path: Path) -> None:
    """Cell 1a: ``gateway_owned`` procedure, supervised-only commissioning,
    no lease presented — the origin/main grant facts. The gate refuses
    ``unattended_grant_absent:`` at the POST and nothing persists."""
    cell = _Cell(tmp_path, "c1a", modes=["supervised"])
    try:
        message = _seam_refusal(cell)
        assert message.startswith("unattended_grant_absent:"), message
        assert "missing unattended grant" in message, message
        _nothing_persisted(cell)
    finally:
        cell.close()


def test_cell1b_grant_absent_lease_present_refuses_leases_untouched(
    tmp_path: Path,
) -> None:
    """Cell 1b: the same lattice with a PRESENTED lease — the refusal fires
    BEFORE lease consumption (the §5 block's consume-last ordering), so the
    operator's lease survives unconsumed and unreleased."""
    cell = _Cell(tmp_path, "c1b", modes=["supervised"])
    try:
        lease = cell.ops.lease_create(_ident(), BENCH_ID, "lease-c1b", 1, 600_000)
        message = _seam_refusal(cell, lease_id=str(lease["lease_id"]))
        assert message.startswith("unattended_grant_absent:"), message
        rows = cell.store.list_leases(BENCH_ID)
        assert [row.state for row in rows] == ["active"], rows
        assert rows[0].sequence == lease["sequence"]
        _nothing_persisted(cell)
    finally:
        cell.close()


def test_cell2_unattended_evidence_row_absent_refuses(tmp_path: Path) -> None:
    """Cell 2: the commissioning CLAIMS the unattended mode but carries no
    ``unattended``-category evidence row at all — the claim grants nothing."""
    cell = _Cell(
        tmp_path,
        "c2",
        modes=["supervised", "unattended"],
        evidence=[_envelope_evidence()],
    )
    try:
        message = _seam_refusal(cell)
        assert message.startswith("unattended_evidence_failed:"), message
        _nothing_persisted(cell)
    finally:
        cell.close()


def test_cell3_unattended_evidence_not_passed_refuses(tmp_path: Path) -> None:
    """Cell 3: the evidence row exists but its result is not ``passed`` — a
    syntactically complete record with failed evidence grants nothing."""
    failed = _passing_unattended_evidence()
    failed["result"] = "failed"
    cell = _Cell(
        tmp_path,
        "c3",
        modes=["supervised", "unattended"],
        evidence=[_envelope_evidence(), failed],
    )
    try:
        message = _seam_refusal(cell)
        assert message.startswith("unattended_evidence_failed:"), message
        assert "failed" in message or "not passed" in message, message
        _nothing_persisted(cell)
    finally:
        cell.close()


def test_cell4a_window_exceeded_by_one_ms_refuses(tmp_path: Path) -> None:
    """Cell 4a: the grant is in order but ``expires_at`` lands ONE
    MILLISECOND inside the run window (8000 ms body + 2000 ms protection) —
    acceptance-time arithmetic refuses at the door, marginally."""
    cell = _Cell(tmp_path, "c4a", expires_at="2027-06-01T00:00:09.999000Z")
    try:
        message = _seam_refusal(cell)
        assert message.startswith("qualification_window_exceeded:"), message
        _nothing_persisted(cell)
    finally:
        cell.close()


def test_cell4b_window_exceeded_badly_refuses(tmp_path: Path) -> None:
    """Cell 4b: ``expires_at`` five seconds out — the same refusal, far from
    the boundary."""
    cell = _Cell(tmp_path, "c4b", expires_at="2027-06-01T00:00:05Z")
    try:
        message = _seam_refusal(cell)
        assert message.startswith("qualification_window_exceeded:"), message
        _nothing_persisted(cell)
    finally:
        cell.close()


def test_cell5_qualification_expired_refuses(tmp_path: Path) -> None:
    """Cell 5: ``expires_at`` in the past — an expired qualification
    authorises no run start (and expiry precedes the window check)."""
    cell = _Cell(tmp_path, "c5", expires_at="2027-05-31T00:00:00Z")
    try:
        message = _seam_refusal(cell)
        assert message.startswith("qualification_expired:"), message
        _nothing_persisted(cell)
    finally:
        cell.close()


def test_cell6_manual_without_lease_refuses(tmp_path: Path) -> None:
    """Cell 6: a ``manual`` procedure, grant in order, window covering — but
    no client lease presented. Manual mode requires an active client lease;
    without one the start is the same silent promotion this gate closes."""
    cell = _Cell(tmp_path, "c6", procedure_mode="manual")
    try:
        message = _seam_refusal(cell)
        assert message.startswith("manual_lease_required:"), message
        _nothing_persisted(cell)
    finally:
        cell.close()


# --- legal cells: admit at the seam, complete through the real factory ---------


def _complete_through_factory(
    cell: _Cell, run_id: str, *, lease_authority: bool = False
) -> dict[str, Any]:
    """The worker layer over the real factory: build the coordinator and
    drive it to its terminal record. ``lease_authority`` pre-creates the run
    row with authority ``lease`` — the shape the seam's consumed takeover
    leaves behind, which is where the worker's ``lease_present`` reads from."""
    if lease_authority:
        cell.store.create_run(
            run_id,
            binding={
                "id": str(cell.ref["id"]),
                "version": str(cell.ref["version"]),
                "sha256": str(cell.ref["sha256"]),
            },
            principal_id="p1",
            now=NOW,
        )
        cell.store.set_run_authority(run_id, "lease")
    factory = _build_run_factory(cell.lattice, lambda: NOW, limits=QUOTA_LIMITS)
    coordinator = factory(run_id, "p1", cell.ref, cell.store)
    record: dict[str, Any] = coordinator.start_run(run_id, "p1")
    return record


def test_legal_gateway_owned_grant_ok_lease_absent_admits_and_completes(
    tmp_path: Path,
) -> None:
    """Legal: the default grant shape, no lease — the seam accepts and the
    real factory reaches a terminal record."""
    cell = _Cell(tmp_path, "legal1")
    try:
        cell.worker.start()
        result = cell.ops.run_start(
            _ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None
        )
        assert result["state"] == "accepted", result
        cell.worker.join(timeout=10)
        record = _complete_through_factory(cell, "run-legal1")
        assert record["outcome"] == "passed", record
        persisted = cell.store.get_run("run-legal1")
        assert persisted is not None and persisted["terminal"] is not None
    finally:
        cell.close()


def test_legal_gateway_owned_grant_ok_lease_present_admits_and_completes(
    tmp_path: Path,
) -> None:
    """Legal: the commissioned takeover — a validated, consumed lease under
    a ``gateway_owned`` procedure whose grant is in order (the disclosed
    residual: the lease is consumed, authority passes to the run)."""
    cell = _Cell(tmp_path, "legal2")
    try:
        lease = cell.ops.lease_create(_ident(), BENCH_ID, "lease-legal2", 1, 600_000)
        cell.worker.start()
        result = cell.ops.run_start(
            _ident(),
            BENCH_ID,
            str(cell.ref["id"]),
            cell.ref,
            1,
            str(lease["lease_id"]),
        )
        assert result["state"] == "accepted", result
        cell.worker.join(timeout=10)
        # The takeover consumed the lease and recorded lease authority.
        rows = cell.store.list_leases(BENCH_ID)
        assert [row.state for row in rows] == ["released"], rows
        seam_run = cell.store.get_run(str(result["run_id"]))
        assert seam_run is not None and seam_run["authority"] == "lease"
        record = _complete_through_factory(cell, "run-legal2")
        assert record["outcome"] == "passed", record
    finally:
        cell.close()


def test_legal_manual_with_lease_admits_and_completes(tmp_path: Path) -> None:
    """Legal: a ``manual`` procedure behind a presented lease — the lease is
    validated, consumed, and the run proceeds at both layers."""
    cell = _Cell(tmp_path, "legal3", procedure_mode="manual")
    try:
        lease = cell.ops.lease_create(_ident(), BENCH_ID, "lease-legal3", 1, 600_000)
        cell.worker.start()
        result = cell.ops.run_start(
            _ident(),
            BENCH_ID,
            str(cell.ref["id"]),
            cell.ref,
            1,
            str(lease["lease_id"]),
        )
        assert result["state"] == "accepted", result
        cell.worker.join(timeout=10)
        record = _complete_through_factory(
            cell, "run-legal3", lease_authority=True
        )
        assert record["outcome"] == "passed", record
    finally:
        cell.close()


def test_legal_manual_without_unattended_grant_admits_and_completes(
    tmp_path: Path,
) -> None:
    """Legal: a ``manual`` run needs NO unattended grant — only the window.
    Supervised-only commissioning under a manual procedure with a lease
    admits (over-tightness would refuse this cell)."""
    cell = _Cell(
        tmp_path,
        "legal4",
        modes=["supervised"],
        evidence=[_envelope_evidence()],
        procedure_mode="manual",
    )
    try:
        lease = cell.ops.lease_create(_ident(), BENCH_ID, "lease-legal4", 1, 600_000)
        cell.worker.start()
        result = cell.ops.run_start(
            _ident(),
            BENCH_ID,
            str(cell.ref["id"]),
            cell.ref,
            1,
            str(lease["lease_id"]),
        )
        assert result["state"] == "accepted", result
        cell.worker.join(timeout=10)
        record = _complete_through_factory(
            cell, "run-legal4", lease_authority=True
        )
        assert record["outcome"] == "passed", record
    finally:
        cell.close()


# --- parity arms: one helper, one vocabulary, byte-identical at both layers ----


def test_parity_unattended_grant_absent(tmp_path: Path) -> None:
    cell = _Cell(tmp_path, "par1", modes=["supervised"])
    try:
        seam = _seam_refusal(cell)
        assert seam.startswith("unattended_grant_absent:"), seam
        assert _worker_refusal(cell) == seam
    finally:
        cell.close()


def test_parity_unattended_evidence_failed(tmp_path: Path) -> None:
    failed = _passing_unattended_evidence()
    failed["result"] = "failed"
    cell = _Cell(
        tmp_path,
        "par2",
        modes=["supervised", "unattended"],
        evidence=[_envelope_evidence(), failed],
    )
    try:
        seam = _seam_refusal(cell)
        assert seam.startswith("unattended_evidence_failed:"), seam
        assert _worker_refusal(cell) == seam
    finally:
        cell.close()


def test_parity_qualification_expired(tmp_path: Path) -> None:
    cell = _Cell(tmp_path, "par3", expires_at="2027-05-31T00:00:00Z")
    try:
        seam = _seam_refusal(cell)
        assert seam.startswith("qualification_expired:"), seam
        assert _worker_refusal(cell) == seam
    finally:
        cell.close()


def test_parity_qualification_window_exceeded(tmp_path: Path) -> None:
    cell = _Cell(tmp_path, "par4", expires_at="2027-06-01T00:00:05Z")
    try:
        seam = _seam_refusal(cell)
        assert seam.startswith("qualification_window_exceeded:"), seam
        assert _worker_refusal(cell) == seam
    finally:
        cell.close()


def test_parity_manual_lease_required(tmp_path: Path) -> None:
    cell = _Cell(tmp_path, "par5", procedure_mode="manual")
    try:
        seam = _seam_refusal(cell)
        assert seam.startswith("manual_lease_required:"), seam
        assert _worker_refusal(cell) == seam
    finally:
        cell.close()


# --- NIT-1 fold: the comparison itself rides the fail-closed clause --------------


def test_nit1_naive_expires_against_aware_now_refuses_typed() -> None:
    """NIT-1 (fold wave): a naive ``expires_at`` against an aware
    ``now_wall`` raises at the COMPARISON, not at construction — Python
    refuses to order offset-naive against offset-aware datetimes. RED at
    the fold base: that TypeError escaped the typed vocabulary raw.
    GREEN: the fail-closed clause owns it, mapped to
    ``qualification_expired:`` (the expiry comparison is the check that
    needed the value — the deviation-4 prefix mapping) with the
    cannot-be-compared wording. Unreachable in production (admission's
    FormatChecker enforces offset date-times in both dialects; every
    production now_wall is Z-stamped) — pinned at the unit seam the
    refute lanes probed."""
    from benchweave.control.documents import _check_unattended_grant

    procedure: dict[str, Any] = {
        "id": "nit1-procedure",
        "version": "0.1.0",
        "mode": "gateway_owned",
        "max_body_ms": 1000,
        "max_protection_ms": 1000,
    }
    commissioning: dict[str, Any] = {
        "id": "nit1-commissioning",
        "version": "0.1.0",
        "modes": ["unattended"],
        "evidence": [{"category": "unattended", "result": "passed"}],
        # Naive — no offset. Construction succeeds; the comparison cannot.
        "expires_at": "2030-01-01T00:00:00",
    }
    with pytest.raises(AdmissionRejected) as raised:
        _check_unattended_grant(
            procedure, commissioning, now_wall="2027-06-01T00:00:00Z", lease_present=False
        )
    message = str(raised.value)
    assert message.startswith("qualification_expired:"), message
    assert "cannot be compared" in message, message


def test_nit1_window_arithmetic_that_cannot_be_held_refuses_typed() -> None:
    """NIT-1's other leg (fold wave): execution 0.1.0 caps neither
    ``max_body_ms`` nor ``max_protection_ms`` (the 86 400 000 ms cap is
    0.2.0's), so a schema-valid 0.1.0 lattice can carry a budget whose
    timedelta construction itself overflows. RED at the fold base: the
    raw OverflowError escaped typed. GREEN: the window comparison rides
    its own fail-closed clause under ``qualification_window_exceeded:``
    with the cannot-be-judged wording."""
    from benchweave.control.documents import _check_unattended_grant

    procedure: dict[str, Any] = {
        "id": "nit1b-procedure",
        "version": "0.1.0",
        "mode": "gateway_owned",
        "max_body_ms": 10**30,
        "max_protection_ms": 1000,
    }
    commissioning: dict[str, Any] = {
        "id": "nit1b-commissioning",
        "version": "0.1.0",
        "modes": ["unattended"],
        "evidence": [{"category": "unattended", "result": "passed"}],
        "expires_at": "2030-01-01T00:00:00Z",
    }
    with pytest.raises(AdmissionRejected) as raised:
        _check_unattended_grant(
            procedure, commissioning, now_wall="2027-06-01T00:00:00Z", lease_present=False
        )
    message = str(raised.value)
    assert message.startswith("qualification_window_exceeded:"), message
    assert "cannot be" in message, message


# --- LOW-2 fold pins: the worker claims, driven through the real thread ----------


def test_low2_manual_lease_through_the_real_worker_thread_completes(
    tmp_path: Path,
) -> None:
    """LOW-2 pin (i): a manual+lease start through the REAL RunWorker
    thread wired to the REAL factory — the worker layer reads
    ``lease_present`` from the seam-created run row's authority ("lease"
    iff a validated lease was presented and consumed at accept time) and
    the run completes ``passed``. A pin of lane-probe-verified behavior:
    the shipped matrix drove the factory directly, never the thread."""
    cell = _Cell(tmp_path, "low2a", procedure_mode="manual", real_factory=True)
    try:
        cell.worker.start()
        lease = cell.ops.lease_create(
            _ident(), BENCH_ID, "lease-low2a", 1, 600_000
        )
        result = cell.ops.run_start(
            _ident(),
            BENCH_ID,
            str(cell.ref["id"]),
            cell.ref,
            1,
            str(lease["lease_id"]),
        )
        assert result["state"] == "accepted", result
        assert cell.worker.join(timeout=10), "the real worker did not drain"
        projection = cell.ops.run_get(_ident(), str(result["run_id"]))
        assert projection["state"] == "terminal", projection
        assert projection["outcome"] == "passed", projection
        row = cell.store.get_run(str(result["run_id"]))
        assert row is not None and row["terminal"] is not None
        assert row["authority"] == "lease"
    finally:
        cell.close()


def test_low2_marginal_window_refuses_at_the_worker_after_seam_accepts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """LOW-2 pin (ii): the marginal window across the two layers' clocks —
    the seam's now + body + protection lands EXACTLY on ``expires_at``
    (equality admits; DOC-1), so the seam 202-accepts, but the worker
    runs one second later and its window overshoots: the factory's
    admission-path call refuses ``qualification_window_exceeded:`` inside
    the real thread, the poison guard contains it (terminal projection,
    NO terminal record — honest ``outcome_unknown``), and the typed
    reason rides the gateway log. A pin of lane-probe-verified
    behavior."""
    import logging

    # expires = seam-now + 10 s exactly: seam equality admits (DOC-1),
    # worker-now (+1 s) + 10 s overshoots by exactly one second.
    cell = _Cell(
        tmp_path,
        "low2b",
        expires_at="2027-06-01T00:00:10Z",
        real_factory=True,
        worker_clock="2027-06-01T00:00:01Z",
    )
    try:
        cell.worker.start()
        with caplog.at_level(logging.ERROR, logger="benchweave.interfaces.worker"):
            result = cell.ops.run_start(
                _ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None
            )
            assert result["state"] == "accepted", result
            assert cell.worker.join(timeout=10), "the real worker did not drain"
        projection = cell.ops.run_get(_ident(), str(result["run_id"]))
        assert projection["state"] == "terminal", projection
        assert projection["outcome"] == "outcome_unknown", projection
        row = cell.store.get_run(str(result["run_id"]))
        assert row is not None and row["terminal"] is None  # no fabricated record
        assert "run_worker poison" in caplog.text, caplog.text
        assert "qualification_window_exceeded" in caplog.text, caplog.text
    finally:
        cell.close()


# --- control arms: the matrix measures THIS gate --------------------------------


#: The eight illegal cells' lattice shapes, in matrix order — the neutralized
#: control loops exactly these.
_ILLEGAL_CELLS: list[dict[str, Any]] = [
    {"name": "ctl-1a", "modes": ["supervised"]},
    {"name": "ctl-1b", "modes": ["supervised"]},
    {
        "name": "ctl-2",
        "modes": ["supervised", "unattended"],
        "evidence": [_envelope_evidence()],
    },
    {
        "name": "ctl-3",
        "modes": ["supervised", "unattended"],
        "evidence": [
            _envelope_evidence(),
            {**_passing_unattended_evidence(), "result": "failed"},
        ],
    },
    {"name": "ctl-4a", "expires_at": "2027-06-01T00:00:09.999000Z"},
    {"name": "ctl-4b", "expires_at": "2027-06-01T00:00:05Z"},
    {"name": "ctl-5", "expires_at": "2027-05-31T00:00:00Z"},
    {"name": "ctl-6", "procedure_mode": "manual"},
]


def test_control_neutralized_gate_no_illegal_cell_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED control (a): with the helper neutralized at BOTH enforcement
    points (the seam's and the worker's module binding), 0/8 illegal cells
    refuse at the seam — every lattice 202-accepts. The matrix measures this
    gate, not a pre-existing refusal."""
    import benchweave.interfaces.app as app_module
    import benchweave.interfaces.operations as operations_module

    def _no_gate(
        procedure: object,
        commissioning: object,
        *,
        now_wall: str,
        lease_present: bool,
    ) -> None:
        del procedure, commissioning, now_wall, lease_present
        return None

    monkeypatch.setattr(operations_module, "_check_unattended_grant", _no_gate)
    monkeypatch.setattr(app_module, "_check_unattended_grant", _no_gate)
    for spec in _ILLEGAL_CELLS:
        name = str(spec.pop("name"))
        cell = _Cell(tmp_path, name, **spec)
        try:
            lease_id: str | None = None
            if name == "ctl-1b":
                lease = cell.ops.lease_create(
                    _ident(), BENCH_ID, f"lease-{name}", 1, 600_000
                )
                lease_id = str(lease["lease_id"])
            result = cell.ops.run_start(
                _ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, lease_id
            )
            assert result["state"] == "accepted", (name, result)
        finally:
            cell.close()


def test_control_prechange_counterexample_admits_without_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED control (b): the pre-change counterexample — the demo lattice's
    grant facts exactly as they stand on origin/main (supervised-only
    commissioning, envelope-only evidence, ``gateway_owned`` procedure) —
    ADMITS a run start with the gate neutralized. That admission is the
    demonstrated defect: the attended path proved a validated lease while
    the autonomous path proved nothing."""
    import benchweave.interfaces.operations as operations_module

    def _no_gate(
        procedure: object,
        commissioning: object,
        *,
        now_wall: str,
        lease_present: bool,
    ) -> None:
        del procedure, commissioning, now_wall, lease_present
        return None

    monkeypatch.setattr(operations_module, "_check_unattended_grant", _no_gate)
    # The origin/main grant facts, pinned as literals (the committed fixture
    # now carries the grant — this slice's own item 4): supervised-only
    # modes, envelope-only evidence, gateway_owned procedure. `git show
    # c183db4:fixtures/execution/commissioning.json` is the authority these
    # reproduce.
    origin_main_modes = ["supervised"]
    procedure = json.loads(
        (FIXTURES / "procedure-voltage-check.json").read_bytes()
    )
    assert procedure["mode"] == "gateway_owned", procedure["mode"]

    cell = _Cell(
        tmp_path,
        "counterexample",
        modes=origin_main_modes,
        evidence=[_envelope_evidence()],
    )
    try:
        result = cell.ops.run_start(
            _ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None
        )
        assert result["state"] == "accepted", result
    finally:
        cell.close()


# --- the inverted guard and the ordering pins -----------------------------------


def _cell_with_unstored_pin(
    tmp_path: Path, name: str, *, pin: str
) -> tuple[_Cell, ContentStore]:
    """A grant-ABSENT lattice whose binding pins an UNSTORED digest for
    ``pin`` (procedure or commissioning) — if the gate ran it would refuse,
    so acceptance proves the skip."""
    cell = _Cell(tmp_path, name, modes=["supervised"])
    content = ContentStore(cell.store)
    binding = json.loads((cell.lattice / "run-binding.json").read_bytes())
    binding[pin]["sha256"] = "e" * 64 if pin == "procedure" else "d" * 64
    raw = json.dumps(binding).encode()
    digest = content_sha(content, raw, binding, NOW)
    cell.ref = {
        "id": str(binding["request_id"]),
        "version": str(binding["contract_version"]),
        "sha256": digest,
    }
    return cell, content


def test_unstored_procedure_skips_the_gate_and_202s(tmp_path: Path) -> None:
    """The inverted guard (procedure leg): a stored binding whose procedure
    digest names nothing in the content store is NOT decided at the seam —
    the start 202-accepts and the worker's authority owns it."""
    cell, _content = _cell_with_unstored_pin(tmp_path, "skip-proc", pin="procedure")
    try:
        result = cell.ops.run_start(
            _ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None
        )
        assert result["state"] == "accepted", result
    finally:
        cell.close()


def test_unstored_commissioning_skips_the_gate_and_202s(tmp_path: Path) -> None:
    """The inverted guard (commissioning leg): same skip for an unstored
    commissioning document."""
    cell, _content = _cell_with_unstored_pin(
        tmp_path, "skip-comm", pin="commissioning"
    )
    try:
        result = cell.ops.run_start(
            _ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None
        )
        assert result["state"] == "accepted", result
    finally:
        cell.close()


def test_unstored_at_seam_refuses_at_the_worker_once_stored(
    tmp_path: Path,
) -> None:
    """The worker layer's authority over the seam's skip: the same store
    after the commissioning document lands under its digest — the factory's
    admission-path call refuses typed. A start the seam skipped can never
    execute silently (the digest-addressed read is the same bytes both
    layers admit)."""
    cell, content = _cell_with_unstored_pin(tmp_path, "worker-owns", pin="commissioning")
    try:
        result = cell.ops.run_start(
            _ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None
        )
        assert result["state"] == "accepted", result
        # The commissioning document lands under the digest the ORIGINAL
        # lattice binding pins (bootstrap stored that binding too).
        commissioning_raw = (cell.lattice / "commissioning.json").read_bytes()
        content_sha(
            content, commissioning_raw, json.loads(commissioning_raw), NOW
        )
        original_ref = _binding_ref(cell.lattice)
        factory = _build_run_factory(
            cell.lattice, lambda: NOW, limits=QUOTA_LIMITS
        )
        with pytest.raises(AdmissionRejected) as raised:
            factory("run-worker-owns", "p1", original_ref, cell.store)
        assert str(raised.value).startswith("unattended_grant_absent:"), (
            str(raised.value)
        )
    finally:
        cell.close()


def test_replay_of_a_live_run_precedes_the_gate(tmp_path: Path) -> None:
    """Ordering pin: a §9 replay of a filed request returns the existing run
    and never reaches the §5 pre-checks — the peek precedes the gate exactly
    as it precedes contention (structural, the floor's own position)."""
    cell = _Cell(tmp_path, "replay")
    try:
        cell.worker.start()
        first = cell.ops.run_start(
            _ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None
        )
        replay = cell.ops.run_start(
            _ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None
        )
        assert replay["run_id"] == first["run_id"], (first, replay)
        assert cell.worker.submitted == 1
        cell.worker.join(timeout=10)
    finally:
        cell.close()
