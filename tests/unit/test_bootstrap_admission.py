"""Issue #85: bootstrap routes descriptors through the admission gate.

The five poisoned-lattice variants from the design record's pre-committed
acceptance rule (§10), each a tempdir copy of ``fixtures/execution/``
carrying exactly one defect (schema defects ride a re-pinned lattice so
they reach the gate's descriptor validation rather than the resolution
step): startup admission must refuse before any store write
(all-or-nothing — no bench row, no device row, no generation bump, no
content row), with the typed prefixes riding the refusal. The happy-path
control pins that the committed lattice admits byte-identically with the
same inventory bootstrap has always written (no fixture edits), and the
unpinned-extra control pins that device rows follow the bench's pins, not
the descriptor glob.

Never the repository's own fixtures or database: every variant copies the
lattice into the test's tmp_path first (design §11 risk 5).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.control.documents import AdmissionRejected
from benchweave.interfaces.app import _recovery_documents
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
NOW = "2026-09-20T00:00:00Z"
BENCH_ID = "sim-bench"


def _lattice_copy(tmp_path: Path, name: str) -> Path:
    dest = tmp_path / name
    shutil.copytree(FIXTURES, dest)
    return dest


def _mutate_json(path: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    document = json.loads(path.read_bytes())
    mutate(document)
    path.write_text(json.dumps(document, indent=2) + "\n")


def _re_pin_bench(lattice: Path) -> None:
    """Refresh the bench-level digest pins after a bench.json edit.

    The commissioning and the binding both pin the bench by digest, so a
    bench.json mutation drifts those pins collaterally; re-pinning keeps
    the variant's refusal about the intended defect (the WP05
    ``readmit_with_procedure`` idiom, applied to the bench).
    """
    bench_sha = hashlib.sha256((lattice / "bench.json").read_bytes()).hexdigest()
    for name in ("commissioning.json", "run-binding.json"):
        document = json.loads((lattice / name).read_bytes())
        document["bench"]["sha256"] = bench_sha
        (lattice / name).write_text(json.dumps(document, indent=2) + "\n")


def _mutate_pinned_descriptor(
    lattice: Path, filename: str, mutate: Callable[[dict[str, Any]], None]
) -> None:
    """Mutate one descriptor and re-pin the lattice to the mutated bytes.

    A schema defect must ride a consistent pin lattice to reach the gate's
    descriptor validation: with a stale pin the resolution step refuses
    first (the pin names bytes that no longer exist on disk) — the V3/V4
    drift shape, not the S01/S02 shape. The bench device pin and the
    bench-level digest pins are refreshed so the refusal names the defect.
    """
    path = lattice / filename
    _mutate_json(path, mutate)
    descriptor_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    descriptor_id = str(json.loads(path.read_bytes())["id"])
    bench = json.loads((lattice / "bench.json").read_bytes())
    for device in bench["devices"]:
        if str(device["descriptor"]["id"]) == descriptor_id:
            device["descriptor"]["sha256"] = descriptor_sha
    (lattice / "bench.json").write_text(json.dumps(bench, indent=2) + "\n")
    _re_pin_bench(lattice)


def _assert_store_untouched(store: Store, content: ContentStore, lattice: Path) -> None:
    """§10.2 all-or-nothing: refusal leaves zero rows and no generation bump."""
    benches, more_benches = store.list_benches(limit=10, offset=0)
    assert benches == [], f"refused startup wrote bench rows: {benches}"
    assert not more_benches
    devices, more_devices = store.list_devices(BENCH_ID, limit=10, offset=0)
    assert devices == [], f"refused startup wrote device rows: {devices}"
    assert not more_devices
    assert store.current_generation(BENCH_ID) == 0, "refused startup bumped the generation"
    bench_sha = hashlib.sha256((lattice / "bench.json").read_bytes()).hexdigest()
    assert content.get_document(bench_sha) is None, (
        "refused startup stored the bench document in the content store"
    )


def test_v1_s01_capabilities_mismatch_refuses_startup(tmp_path: Path) -> None:
    lattice = _lattice_copy(tmp_path, "v1-s01")

    def duplicate_parameter_name(document: dict[str, Any]) -> None:
        # The caps/ops-set half of S01 is schema-enforced on 0.2.0 (a `not`
        # clause at $.operations fires first); duplicate parameter names
        # pass the schema and reach the mirror — its live branch.
        document["parameters"].append(dict(document["parameters"][0]))

    _mutate_pinned_descriptor(lattice, "descriptor-sim-psu.json", duplicate_parameter_name)
    store = Store.open(tmp_path / "v1.db")
    content = ContentStore(store)
    try:
        with pytest.raises(AdmissionRejected, match=r"^schema: descriptor\[psu\] S01"):
            admit_startup_bench(store, content, lattice, now=NOW)
        _assert_store_untouched(store, content, lattice)
    finally:
        store.close()


def test_v2_s02_reversed_parameter_bounds_refuse_startup(tmp_path: Path) -> None:
    lattice = _lattice_copy(tmp_path, "v2-s02")

    def reverse_voltage_range(document: dict[str, Any]) -> None:
        for parameter in document["parameters"]:
            if parameter["name"] == "voltage_setpoint_v":
                parameter["range"] = [30.0, 0.0]

    _mutate_pinned_descriptor(lattice, "descriptor-sim-psu.json", reverse_voltage_range)
    store = Store.open(tmp_path / "v2.db")
    content = ContentStore(store)
    try:
        with pytest.raises(AdmissionRejected, match=r"^schema: descriptor\[psu\] S02"):
            admit_startup_bench(store, content, lattice, now=NOW)
        _assert_store_untouched(store, content, lattice)
    finally:
        store.close()


def test_v3_bench_pin_digest_drift_refuses_startup(tmp_path: Path) -> None:
    lattice = _lattice_copy(tmp_path, "v3-drift")
    # Cross-point the psu device pin at the controller descriptor's
    # digest: the pin still resolves to a real lattice file (so the
    # resolution step passes) but names the wrong document — the
    # id-vs-bytes disagreement is what digest_mismatch pins.
    controller_sha = hashlib.sha256(
        (lattice / "descriptor-sim-controller.json").read_bytes()
    ).hexdigest()

    def point_psu_at_controller(document: dict[str, Any]) -> None:
        for device in document["devices"]:
            if device["id"] == "psu":
                device["descriptor"]["sha256"] = controller_sha

    _mutate_json(lattice / "bench.json", point_psu_at_controller)
    _re_pin_bench(lattice)
    store = Store.open(tmp_path / "v3.db")
    content = ContentStore(store)
    try:
        with pytest.raises(AdmissionRejected, match=r"^digest_mismatch:"):
            admit_startup_bench(store, content, lattice, now=NOW)
        _assert_store_untouched(store, content, lattice)
    finally:
        store.close()


def test_v4_pinned_descriptor_absent_refuses_startup(tmp_path: Path) -> None:
    lattice = _lattice_copy(tmp_path, "v4-no-descriptor")
    (lattice / "descriptor-sim-controller.json").unlink()
    store = Store.open(tmp_path / "v4.db")
    content = ContentStore(store)
    try:
        with pytest.raises(
            FileNotFoundError, match=r"bench device controller pins descriptor sha256 c0e503bd"
        ):
            admit_startup_bench(store, content, lattice, now=NOW)
        _assert_store_untouched(store, content, lattice)
    finally:
        store.close()


def test_v5_binding_pinned_procedure_absent_refuses_startup(tmp_path: Path) -> None:
    lattice = _lattice_copy(tmp_path, "v5-no-procedure")
    (lattice / "procedure-voltage-check.json").unlink()
    store = Store.open(tmp_path / "v5.db")
    content = ContentStore(store)
    try:
        with pytest.raises(FileNotFoundError, match=r"binding-pinned procedure not found"):
            admit_startup_bench(store, content, lattice, now=NOW)
        _assert_store_untouched(store, content, lattice)
    finally:
        store.close()


def test_malformed_bench_document_refuses_startup_typed(tmp_path: Path) -> None:
    """Design §2 row 2, closed: a malformed bench arrives as ``schema:``.

    The resolution step parses bench.json before ``admit_documents`` sees
    it; that parse runs through the exact-byte decoder so the truncated /
    duplicate-key / non-finite shapes refuse with the typed prefix
    instead of a raw JSONDecodeError traceback.
    """
    lattice = _lattice_copy(tmp_path, "malformed-bench")
    (lattice / "bench.json").write_text('{"id": "sim-bench", "devices": [')
    store = Store.open(tmp_path / "malformed-bench.db")
    content = ContentStore(store)
    try:
        with pytest.raises(AdmissionRejected, match=r"^schema: bench"):
            admit_startup_bench(store, content, lattice, now=NOW)
        _assert_store_untouched(store, content, lattice)
    finally:
        store.close()


def test_malformed_binding_document_refuses_startup_typed(tmp_path: Path) -> None:
    """Same channel for run-binding.json, the other resolution parse."""
    lattice = _lattice_copy(tmp_path, "malformed-binding")
    (lattice / "run-binding.json").write_text("not json at all")
    store = Store.open(tmp_path / "malformed-binding.db")
    content = ContentStore(store)
    try:
        with pytest.raises(AdmissionRejected, match=r"^schema: binding"):
            admit_startup_bench(store, content, lattice, now=NOW)
        _assert_store_untouched(store, content, lattice)
    finally:
        store.close()


def test_recovery_contains_a_malformed_bench_lattice_unchanged(tmp_path: Path) -> None:
    """The typed wrap changes the recovery caller's exception class only.

    Before the exact-byte decode, the resolution parse raised raw
    JSONDecodeError; after it, AdmissionRejected — the containment
    outcome is identical either way (logged ``recovery_admission_rejected``,
    ``None``, run recovery skipped), which is the "semantics identical"
    claim pinned as a test line.
    """
    lattice = _lattice_copy(tmp_path, "recovery-malformed")
    (lattice / "bench.json").write_text('{"id": "sim-bench", ')
    assert _recovery_documents(lattice) is None


def test_unpinned_extra_descriptor_gains_no_device_row(tmp_path: Path) -> None:
    """Surface 3 of the design's laundering list: rows follow the pins.

    An extra descriptor file the bench does not pin is cached in the
    content store (D5: family members meet the gate when a binding pins
    them) but must not gain a device row — pre-fix, the glob drove the rows
    and any descriptor-shaped file was inventoried as a matched device.
    """
    lattice = _lattice_copy(tmp_path, "extra-descriptor")
    extra = json.loads((lattice / "descriptor-sim-controller.json").read_bytes())
    extra["id"] = "dev.benchweave.ghost-extra"
    (lattice / "descriptor-ghost-extra.json").write_text(json.dumps(extra, indent=2) + "\n")
    store = Store.open(tmp_path / "extra.db")
    content = ContentStore(store)
    try:
        result = admit_startup_bench(store, content, lattice, now=NOW)
        devices, _ = store.list_devices(BENCH_ID, limit=10, offset=0)
        assert sorted(row["device_id"] for row in devices) == [
            "dev.benchweave.sim-controller",
            "dev.benchweave.sim-psu",
        ], "device rows must follow the bench's pins, not the descriptor glob"
        extra_sha = hashlib.sha256(
            (lattice / "descriptor-ghost-extra.json").read_bytes()
        ).hexdigest()
        assert extra_sha in result["documents"], (
            "the unpinned family member stays cached in the content store"
        )
    finally:
        store.close()


def test_committed_lattice_admits_with_unchanged_inventory(tmp_path: Path) -> None:
    """§10.2 happy path: the committed fixtures admit byte-identically.

    Pins the exact inventory bootstrap has always written — same bench row,
    same device rows (descriptor-id keying, D1), identity_state 'matched'
    now an evidenced claim, profiles and descriptor bytes identical.
    """
    store = Store.open(tmp_path / "happy.db")
    content = ContentStore(store)
    try:
        result = admit_startup_bench(store, content, FIXTURES, now=NOW)
        assert result["bench_id"] == BENCH_ID
        bench, _ = store.list_benches(limit=10, offset=0)
        assert [row["bench_id"] for row in bench] == [BENCH_ID]
        devices, _ = store.list_devices(BENCH_ID, limit=10, offset=0)
        assert sorted(row["device_id"] for row in devices) == [
            "dev.benchweave.sim-controller",
            "dev.benchweave.sim-psu",
        ]
        assert all(row["identity_state"] == "matched" for row in devices)
        for row in devices:
            descriptor_id = row["device_id"]
            source = next(
                path
                for path in sorted(FIXTURES.glob("descriptor-*.json"))
                if str(json.loads(path.read_bytes())["id"]) == descriptor_id
            )
            raw = source.read_bytes()
            descriptor = json.loads(raw)
            assert row["descriptor_json"] == raw.decode()
            assert row["profiles_json"] == json.dumps(descriptor.get("profiles", []))
            assert row["licence"] == str(descriptor.get("licence", "proprietary"))
        assert store.current_generation(BENCH_ID) == 1
    finally:
        store.close()
