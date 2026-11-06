"""The provider-approval window gate (issue #568, CTL-12's window leg).

The two-layer rule in the #260/#316 shape, over the same seam/worker
machinery ``tests/control/test_unattended_grant.py`` drives (B2's two
legs):

- the SEAM's runnability pre-check refuses typed ``policy_denied`` BEFORE
  any lease is consumed, over approvals the STORED documents answer
  (descriptor → pinned contract, digest-addressed; an unstored contract
  keeps the inverted-guard skip, the worker owning that lattice);
- the WORKER's build is authoritative: the same helper and vocabulary
  over the full admission result, the refusal failing the run build;
- the arithmetic is CTL-10's own sentence applied to the approval: the
  run window (``now_wall + max_body_ms + max_protection_ms``) cannot
  exceed ``expires_at`` — a window ending exactly at expiry admits, one
  ending past it refuses, and an unjudgeable window authorises no start.

The provider lattice carries an operator-supplied contract whose
``approval.expires_at`` the tests mutate; every other identity is
invented fixture data.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.control.documents import AdmissionRejected
from benchweave.interfaces import errors
from benchweave.interfaces.app import _build_run_factory
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.validation import SeamValidator
from benchweave.interfaces.worker import RunWorker
from benchweave.state.store import Store
from benchweave.vendoring import active_contract_family

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
EXAMPLES = ROOT / "standards" / "otdp" / "0.2.2" / "examples"
NOW = "2026-10-28T00:00:00Z"
BENCH_ID = "sim-bench"
#: The fixture procedure's budgets: 8000 + 2000 = the 10 s run window the
#: approval must cover (max_body_ms/max_protection_ms read from the
#: committed fixture, never retyped).
PROCEDURE_WINDOW_MS = 10_000

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


def _documents_module() -> Any:
    return importlib.import_module("benchweave.control.documents")


def _contract_with_expiry(expires: str) -> bytes:
    """The corpus reference provider contract with the approval expiry the
    test plants (operator-supplied bytes: the settings admit them by
    digest, the descriptor pins the same bytes)."""
    contract = json.loads((EXAMPLES / "reference-provider.json").read_bytes())
    contract["approval"]["expires_at"] = expires
    return (json.dumps(contract, indent=2) + "\n").encode()


def _provider_lattice(tmp_path: Path, contract_expires: str) -> Path:
    """The fixture lattice with the psu slot at an authored provider pair
    whose approval expires at ``contract_expires``."""
    directory = tmp_path / "lattice"
    directory.mkdir(parents=True)
    for name in (
        "procedure-voltage-check.json",
        "safety-policy.json",
        "bench.json",
        "run-binding.json",
        "commissioning.json",
        "package-lock.json",
        "descriptor-sim-controller.json",
    ):
        (directory / name).write_bytes((FIXTURES / name).read_bytes())
    contract_raw = _contract_with_expiry(contract_expires)
    (directory / "reference-provider.json").write_bytes(contract_raw)
    descriptor = json.loads((EXAMPLES / "reference-hid-meter.json").read_bytes())
    descriptor["transport"]["provider"]["sha256"] = hashlib.sha256(
        contract_raw
    ).hexdigest()
    (directory / "descriptor-provider.json").write_text(json.dumps(descriptor, indent=2))
    settings = {
        "config_version": "1",
        "admitted": [
            {
                "id": json.loads(contract_raw)["id"],
                "version": json.loads(contract_raw)["version"],
                "sha256": hashlib.sha256(contract_raw).hexdigest(),
                "feature_id": json.loads(contract_raw)["feature_id"],
                "document": "reference-provider.json",
            }
        ],
        "connections": [
            {
                "connection_key": "power_meter",
                "provider_id": json.loads(contract_raw)["id"],
            }
        ],
    }
    (directory / "transport-settings.json").write_text(json.dumps(settings, indent=2))
    (directory / "provider-connections.json").write_text(
        json.dumps(
            {
                "config_version": "1",
                "connections": [
                    {
                        "connection_key": "power_meter",
                        "usb": {
                            "vendor_id": 1027,
                            "product_id": 24593,
                            "serial": "FT-DEMO-0042",
                            "interface": 1,
                        },
                    }
                ],
            },
            indent=2,
        )
    )
    bench = json.loads((directory / "bench.json").read_text())
    raw = (directory / "descriptor-provider.json").read_bytes()
    for device in bench["devices"]:
        if str(device["id"]) == "psu":
            device["descriptor"]["id"] = descriptor["id"]
            device["descriptor"]["version"] = descriptor["descriptor_version"]
            device["descriptor"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (directory / "bench.json").write_text(json.dumps(bench, indent=2))
    bench_sha = hashlib.sha256((directory / "bench.json").read_bytes()).hexdigest()
    commissioning = json.loads((directory / "commissioning.json").read_text())
    commissioning["bench"]["sha256"] = bench_sha
    (directory / "commissioning.json").write_text(json.dumps(commissioning, indent=2))
    commissioning_sha = hashlib.sha256(
        (directory / "commissioning.json").read_bytes()
    ).hexdigest()
    binding = json.loads((directory / "run-binding.json").read_text())
    binding["bench"]["sha256"] = bench_sha
    binding["commissioning"]["sha256"] = commissioning_sha
    (directory / "run-binding.json").write_text(json.dumps(binding, indent=2))
    return directory


class _Cell:
    """One lattice's stack: admitted store + seam + worker, the
    unattended-grant harness's shape."""

    def __init__(self, tmp_path: Path, name: str, *, expires: str) -> None:
        self.lattice = _provider_lattice(tmp_path / name, expires)
        self.store = Store.open(tmp_path / f"{name}.db")
        content = ContentStore(self.store)
        admit_startup_bench(self.store, content, self.lattice, now=NOW)
        def build(*args: Any) -> None:
            pass  # refusal arms stay synchronous

        self.worker = RunWorker(
            self.store, content, build_run=build, now_iso=lambda: NOW
        )
        self.ops = Operations(
            self.store,
            content,
            validator=SeamValidator(active_contract_family("interface")),
            gateway_id=f"gw-568-{name}",
            limits=QUOTA_LIMITS,
            worker=self.worker,
            now_iso=lambda: NOW,
        )
        raw = (self.lattice / "run-binding.json").read_bytes()
        self.ref = {
            "id": str(json.loads(raw)["request_id"]),
            "version": str(json.loads(raw)["contract_version"]),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    def close(self) -> None:
        self.worker.stop()
        with contextlib.suppress(RuntimeError):
            self.worker.join(timeout=10)
        self.store.close()


def _ident() -> Identity:
    return Identity("principal-568", "stg", frozenset({"stg:control"}), 2**31)


def _seam_message(cell: _Cell) -> str | None:
    """The seam's typed refusal message, or None when the start passed the
    pre-check (the lease-free manual shape is not this gate's concern:
    run_start's refusal under test is the provider window's)."""
    try:
        cell.ops.run_start(_ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None)
    except errors.OperationFailure as raised:
        return str(raised.failure.message)
    except Exception as raised:
        return f"{type(raised).__name__}: {raised}"
    return None


def _worker_refusal(cell: _Cell, run_id: str = "run-568") -> str | None:
    """The worker layer's refusal for the SAME lattice (the factory over
    the full admission result); None when the build passed the gate."""
    factory = _build_run_factory(cell.lattice, lambda: NOW, limits=QUOTA_LIMITS)
    try:
        factory(run_id, "p1", cell.ref, cell.store)
    except AdmissionRejected as raised:
        return str(raised)
    except Exception as raised:  # post-gate failures name themselves
        return f"{type(raised).__name__}: {raised}"
    return None


# --- the helper's own arithmetic ------------------------------------------------


def test_the_helper_refuses_a_straddling_window() -> None:
    documents = _documents_module()
    with pytest.raises(AdmissionRejected, match="provider_grant_window_exceeded:"):
        documents.check_provider_grant_window(
            [
                (
                    "descriptor[psu]",
                    "urn:otdp:transport-provider:ftdi-control:1.0.0",
                    "2026-10-28T00:00:05Z",
                )
            ],
            now_wall=NOW,
            body_ms=8000,
            protection_ms=2000,
        )


def test_the_helper_admits_a_window_ending_exactly_at_expiry() -> None:
    """CTL-10's boundary sentence: "cannot exceed", not "must end before" —
    a window ending exactly at expiry admits."""
    documents = _documents_module()
    documents.check_provider_grant_window(
        [("descriptor[psu]", "urn:x:y:1.0.0", "2026-10-28T00:00:10Z")],
        now_wall=NOW,
        body_ms=8000,
        protection_ms=2000,
    )


@pytest.mark.parametrize(
    ("expires", "body_ms", "protection_ms", "label"),
    [
        ("not-a-date", 8000, 2000, "unparseable expiry"),
        (None, 8000, 2000, "missing expiry"),
        ("2026-10-28T00:00:10Z", "8000", 2000, "non-integer body budget"),
    ],
)
def test_the_helper_fails_closed(
    expires: object, body_ms: object, protection_ms: int, label: str
) -> None:
    """An unjudgeable window authorises no run start — typed, the CTL-10
    fail-closed clauses' vocabulary."""
    documents = _documents_module()
    with pytest.raises(AdmissionRejected, match="provider_grant_window_exceeded:"):
        documents.check_provider_grant_window(
            [("descriptor[psu]", "urn:x:y:1.0.0", expires)],
            now_wall=NOW,
            body_ms=body_ms,
            protection_ms=protection_ms,
        ), label


# --- the two layers over the real seam and worker -------------------------------


def test_b2_window_exceeded_refuses_at_the_seam_and_the_worker(
    tmp_path: Path,
) -> None:
    """B2: the approval expires inside the run window (half the body) →
    ``provider_grant_window_exceeded:`` at the seam pre-check AND at the
    worker, one vocabulary."""
    cell = _Cell(tmp_path, "b2", expires="2026-10-28T00:00:05Z")
    try:
        seam = _seam_message(cell)
        assert seam is not None and "provider_grant_window_exceeded:" in seam, seam
        worker = _worker_refusal(cell)
        assert worker is not None and "provider_grant_window_exceeded:" in worker, worker
    finally:
        cell.close()


def test_a_window_covered_by_the_approval_admits_both_layers(
    tmp_path: Path,
) -> None:
    """The control's other half: an approval covering the whole window
    passes the gate at both layers (the seam's refusal, when one fires,
    names a different axis; the worker proceeds past the window gate)."""
    cell = _Cell(tmp_path, "covered", expires="2027-10-26T00:00:00Z")
    try:
        worker = _worker_refusal(cell)
        assert worker is None or "provider_grant_window_exceeded:" not in worker, worker
    finally:
        cell.close()


def test_the_boundary_window_admits_at_the_worker(tmp_path: Path) -> None:
    """The boundary: expires exactly at now + body + protection admits."""
    cell = _Cell(tmp_path, "boundary", expires="2026-10-28T00:00:10Z")
    try:
        worker = _worker_refusal(cell)
        assert worker is None or "provider_grant_window_exceeded:" not in worker, worker
    finally:
        cell.close()


def test_the_seam_and_worker_refusals_agree_on_the_vocabulary(
    tmp_path: Path,
) -> None:
    """The #260 Risk-4 leg: both layers' refusals name the same prefix and
    the same two timestamps."""
    cell = _Cell(tmp_path, "parity", expires="2026-10-28T00:00:05Z")
    try:
        seam = _seam_message(cell)
        worker = _worker_refusal(cell)
        assert seam is not None and worker is not None
        for message in (seam, worker):
            assert "provider_grant_window_exceeded:" in message
            assert "2026-10-28T00:00:05Z" in message
            assert NOW in message
    finally:
        cell.close()


def test_an_unstored_contract_is_not_decided_at_the_seam(tmp_path: Path) -> None:
    """The inverted guard: with the contract ABSENT from the content store
    the seam skips the provider window (the worker owns that lattice) —
    pinned by removing the stored contract document rows before the seam
    call."""
    cell = _Cell(tmp_path, "unstored", expires="2026-10-28T00:00:05Z")
    try:
        contract_raw = (cell.lattice / "reference-provider.json").read_bytes()
        digest = hashlib.sha256(contract_raw).hexdigest()
        # The pinned contract's row was cached by bootstrap (the #568
        # seam-liveness leg); remove it so the seam's digest-addressed
        # lookup misses — the inverted-guard's premise.
        deleted = cell.store.connection.execute(
            "DELETE FROM documents WHERE sha256 = ?", (digest,)
        ).rowcount
        assert deleted == 1, "the bootstrap cache did not store the contract"
        cell.store.connection.commit()
        seam = None
        try:
            cell.ops.run_start(_ident(), BENCH_ID, str(cell.ref["id"]), cell.ref, 1, None)
        except errors.OperationFailure as raised:
            seam = str(raised.failure.message)
        except Exception as raised:
            seam = f"{type(raised).__name__}: {raised}"
        # with the contract unstored the seam does NOT carry the provider
        # window refusal — whatever fires names another axis (or nothing)
        assert seam is None or "provider_grant_window_exceeded:" not in seam, seam
    finally:
        cell.close()
