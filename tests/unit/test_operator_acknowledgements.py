"""Operator acknowledgement persistence (issue #219, design deferral D11).

The production surface slice 3 left open: ``admit_documents`` carries the
``operator_acknowledgements`` seam, but nothing in ``bootstrap``/``app``
threaded it — a non-conforming pin in the STARTUP lattice was a hard
``startup_admission_rejected:`` refusal with no acknowledgement path at
all. This slice lands:

- the authored carrier — an optional ``operator-acknowledgements.json``
  beside the lattice (the transport-settings precedent: operator-owned,
  validated fail-closed, exact-byte decoded, no wire surface);
- threading through ``admit_fixture_lattice`` — the ONE resolution+admission
  body both startup (``admit_startup_bench``) and recovery
  (``app._recovery_documents``) call, so one seam wires both;
- persistence admission-record-owned: ``admit_startup_bench`` stamps each
  loaded acknowledgement onto the device's store row (STO column, additive
  migration), which is what later read surfaces — the API-view projection
  included — derive from.

The narrowed fixture policy (>=0.2.2) is the design's actual scenario: a
range narrowed past a committed pin makes that retained pin
non-conforming, and the cross-constraint row (execution 0.2.0 requires
otdp >=0.2.0) still admits it — an acknowledgement authorises the
odtp-window load, never the execution runtime interface.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from test_bootstrap_admission import BENCH_ID, FIXTURES, NOW, _mutate_pinned_descriptor

import benchweave.control.documents as documents_module
from benchweave.content.store import ContentStore
from benchweave.control.documents import AdmissionRejected
from benchweave.interfaces.app import _recovery_documents
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
ACK_FILENAME = "operator-acknowledgements.json"


def _narrowed_corpus(tmp_path: Path) -> Path:
    """A corpus whose policy range sits above the lattice's 0.2.0 pin."""
    corpus = tmp_path / "ack-corpus"
    shutil.copytree(ROOT / "standards", corpus)
    manifest = json.loads((corpus / "standards-manifest.json").read_text())
    manifest["dependency_policy"]["standards"]["otdp"]["range"] = ">=0.2.2,<0.3.0"
    (corpus / "standards-manifest.json").write_text(json.dumps(manifest))
    return corpus


def _acked_lattice(tmp_path: Path, name: str) -> Path:
    """The fixture lattice with its psu re-pinned to 0.2.0 (in-range for
    the seed policy, out-of-range for the narrowed one).

    ``_mutate_pinned_descriptor``'s re-pin only needs to carry refusal
    arms to the intended gate; a SUCCESS path additionally needs the
    binding's commissioning pin refreshed — ``_re_pin_bench`` rewrites
    commissioning.json (the bench sha), which drifts the commissioning
    digest the binding pins.
    """
    import hashlib

    from test_bootstrap_admission import _lattice_copy

    lattice = _lattice_copy(tmp_path, name)
    _mutate_pinned_descriptor(
        lattice, "descriptor-sim-psu.json", lambda d: d.update(otdp_version="0.2.0")
    )
    commissioning_sha = hashlib.sha256(
        (lattice / "commissioning.json").read_bytes()
    ).hexdigest()
    binding = json.loads((lattice / "run-binding.json").read_bytes())
    binding["commissioning"]["sha256"] = commissioning_sha
    (lattice / "run-binding.json").write_text(json.dumps(binding, indent=2) + "\n")
    return lattice


def _write_ack(lattice: Path, payload: dict[str, Any]) -> None:
    (lattice / ACK_FILENAME).write_text(json.dumps(payload, indent=1))


def _ack_payload(pin: str, device: str = "psu") -> dict[str, Any]:
    return {"acknowledgements": {device: pin}}


# --- the authored carrier ------------------------------------------------------


def test_the_ack_file_loads_the_admission_param_shape() -> None:
    """The file IS the ``operator_acknowledgements`` argument: device ->
    exact OTDP pin, nothing else (one ack cannot blanket other devices)."""
    import tempfile

    from benchweave.control.operator_acknowledgements import (
        load_operator_acknowledgements,
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ACK_FILENAME
        path.write_text(json.dumps(_ack_payload("0.1.2")))
        assert load_operator_acknowledgements(path) == {"psu": "0.1.2"}


@pytest.mark.parametrize(
    "payload",
    [
        {"acknowledgements": {"psu": "latest"}},
        {"acknowledgements": {"PSU bad id": "0.1.2"}},
        {"acknowledgements": {"psu": "0.1.2"}, "extra": {}},
    ],
    ids=["non-semver pin", "malformed device id", "unknown top-level key"],
)
def test_a_malformed_ack_file_refuses_with_a_typed_prefix(payload: dict[str, Any]) -> None:
    """Fail-closed at load, the transport-settings posture: every payload
    shape the admission seam cannot honour refuses by name (an
    acknowledgement naming a non-version could never equal a pin)."""
    import tempfile

    from benchweave.control.operator_acknowledgements import (
        AcknowledgementsRejected,
        load_operator_acknowledgements,
    )

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ACK_FILENAME
        path.write_text(json.dumps(payload))
        with pytest.raises(AcknowledgementsRejected, match=r"acknowledgements_schema:"):
            load_operator_acknowledgements(path)


# --- threading through bootstrap and recovery ---------------------------------


def test_startup_threads_the_ack_and_persists_it_on_the_admission_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D11's landing: a narrowed-range lattice whose retained pin is
    non-conforming loads behind the file, and the acknowledgement — with
    the admission's ``now`` stamped as its recorded_at — lands on the
    device's store row (persistence + stamping, the slice-3 seam's
    deferred half)."""
    corpus = _narrowed_corpus(tmp_path)  # built once: _otdp_corpus() is called per pin
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)
    lattice = _acked_lattice(tmp_path, "startup-acked")
    _write_ack(lattice, _ack_payload("0.2.0"))
    store = Store.open(tmp_path / "ack.db")
    content = ContentStore(store)
    try:
        admit_startup_bench(store, content, lattice, now=NOW)
        devices, _more = store.list_devices(BENCH_ID, limit=10, offset=0)
        psu_rows = [
            row
            for row in devices
            if json.loads(row["descriptor_json"]).get("otdp_version") == "0.2.0"
        ]
        assert len(psu_rows) == 1, devices
        record = json.loads(psu_rows[0]["acknowledgement_json"])
        assert record == {"otdp_version": "0.2.0", "recorded_at": NOW}, record
    finally:
        store.close()


def test_startup_without_the_ack_file_still_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the file is the ONLY authorisation — no file, no load
    (the posture the operator guide documented before the file existed)."""
    corpus = _narrowed_corpus(tmp_path)  # built once: _otdp_corpus() is called per pin
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)
    lattice = _acked_lattice(tmp_path, "startup-unacked")
    store = Store.open(tmp_path / "ack.db")
    content = ContentStore(store)
    try:
        with pytest.raises(AdmissionRejected, match=r"^operator_ack_required:"):
            admit_startup_bench(store, content, lattice, now=NOW)
        devices, _more = store.list_devices(BENCH_ID, limit=10, offset=0)
        assert devices == [], "a refused startup must not write device rows"
    finally:
        store.close()


def test_a_malformed_ack_file_refuses_startup_leaving_the_store_untouched(
    tmp_path: Path,
) -> None:
    """Fail-closed where it belongs: a file the loader cannot honour is a
    startup refusal (never silently ignored — an ignored file would
    pretend the operator acknowledged nothing while the file claims they
    did)."""
    from benchweave.control.operator_acknowledgements import AcknowledgementsRejected

    lattice = _lattice_copy_untouched(tmp_path, "startup-bad-ack")
    _write_ack(lattice, {"acknowledgements": {"psu": "not-a-version"}})
    store = Store.open(tmp_path / "ack.db")
    content = ContentStore(store)
    try:
        with pytest.raises(AcknowledgementsRejected, match=r"acknowledgements_schema:"):
            admit_startup_bench(store, content, lattice, now=NOW)
        devices, _more = store.list_devices(BENCH_ID, limit=10, offset=0)
        assert devices == [], "a refused startup must not write device rows"
    finally:
        store.close()


def _lattice_copy_untouched(tmp_path: Path, name: str) -> Path:
    from test_bootstrap_admission import _lattice_copy

    return _lattice_copy(tmp_path, name)


def test_recovery_threads_the_ack_and_returns_admitted_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The app-side wire: recovery runs the same admission body, so the
    same file admits it — a contained path returning real admitted
    documents (with the acknowledgement on the pin record), not ``None``
    from a swallowed refusal."""
    corpus = _narrowed_corpus(tmp_path)  # built once: _otdp_corpus() is called per pin
    monkeypatch.setattr(documents_module, "_otdp_corpus", lambda: corpus)
    lattice = _acked_lattice(tmp_path, "recovery-acked")
    _write_ack(lattice, _ack_payload("0.2.0"))
    docs = _recovery_documents(lattice, now_wall=NOW)
    assert docs is not None, "recovery admission was contained (refused) despite the ack"
    assert docs.pins["psu"].conformance == "non-conforming"
    assert docs.pins["psu"].acknowledgement == {
        "otdp_version": "0.2.0",
        "recorded_at": NOW,
    }
    assert docs.pins["controller"].conformance == "conforming"


# --- the persisted record's read surface ---------------------------------------


def test_the_projection_stays_silent_for_an_acked_stored_pin(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VR-16's R4 arm closes its own deferral: the projection threads the
    STORED acknowledgement, so an acknowledged non-conforming device
    does not warn on every read — and the unacked twin still does (the
    warning is for the unacknowledged state)."""
    import logging

    from benchweave.interfaces.operations import Operations

    raw = json.loads((FIXTURES / "descriptor-sim-psu.json").read_text())
    raw["otdp_version"] = "0.1.2"

    def projection(ack: str | None) -> Any:
        row = {
            "device_id": "psu",
            "generation": 1,
            "profiles_json": "[]",
            "descriptor_json": json.dumps(raw),
            "identity_state": "matched",
            "licence": "proprietary",
            "updated_at": NOW,
            "acknowledgement_json": ack,
        }
        seam = object.__new__(Operations)
        with caplog.at_level(logging.WARNING, logger="benchweave.interfaces.operations"):
            view = seam._device_projection(row)
        assert set(view) == {
            "device_id",
            "generation",
            "profiles",
            "descriptor",
            "identity_state",
        }
        return [
            record.message
            for record in caplog.records
            if "device_conformance_mismatch" in record.message
        ]

    caplog.clear()
    warnings = projection(json.dumps({"otdp_version": "0.1.2", "recorded_at": NOW}))
    assert warnings == [], warnings

    caplog.clear()
    warnings = projection(None)
    assert warnings, "an unacked non-conforming pin must still warn"
    assert "0.1.2" in warnings[0]
