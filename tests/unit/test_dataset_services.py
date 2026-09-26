"""The dataset services payload lane (issue #146 slice 3, §2.2 S3a).

Unit controls over a real store + staged writer + controller + payload
bundle: the refuse-at-create ceiling (R12), the allowance formula's missing
capture-clamp term (R4's create arm), reservation enforcement, cancellation,
session isolation, the host-computed finalise record (R3), terminal appends,
idempotent abort, and the writer's lane-honest refusal prose (R17's payload
extension). The bridge-facing classification controls (R10 both directions)
live in ``test_otdp_bridge.py`` where the real dispatch path exists.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.dataset_services import (
    DatasetController,
    DatasetPayloadBundle,
    DatasetServiceRejected,
    build_dataset_controller,
)
from benchweave.content.store import ContentStore
from benchweave.host.types import CaptureFinaliseRejected, CaptureQuotaExceeded
from benchweave.registry.otdp_contracts import CompiledAction, ResolvedOtdpContracts
from benchweave.state.store import Store


def _contracts() -> ResolvedOtdpContracts:
    """A directly-constructed contracts value (the resolution machinery has
    its own loader-test battery; the bundle only needs the value)."""
    from jsonschema import Draft202012Validator

    return ResolvedOtdpContracts(
        actions={
            "demo.act/1.0.0": CompiledAction(
                input_validator=Draft202012Validator({"type": "object"}),
                output_validator=Draft202012Validator({"type": "object"}),
                side_effect="none",
                lifecycle="direct",
            )
        },
        dataset_required_keys=frozenset(
            {
                "dataset_id",
                "kind",
                "configuration_id",
                "acquisition_id",
                "started_at",
                "clock",
                "axes",
                "variables",
                "trigger",
                "status",
                "context",
            }
        ),
        dataset_validator=Draft202012Validator({"type": "object"}),
    )


class DatasetHarness:
    """A real store + staged writer + controller + payload bundle.

    ``max_capture_bytes`` is deliberately TINY (64) and the dataset budget
    roomy: the payload allowance formula's missing capture-clamp term is
    only observable when the two ceilings disagree by an order of
    magnitude."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        max_capture_bytes: int = 64,
        max_dataset_bytes: int = 8192,
        evidence_quota: int = 50,
    ) -> None:
        self.store = Store.open(tmp_path / "dataset-services.db")
        self.content = ContentStore(self.store)
        self.writer = CaptureStagingStore(
            self.store,
            max_capture_bytes=max_capture_bytes,
            max_dataset_bytes=max_dataset_bytes,
        )
        self.controller = build_dataset_controller(
            _contracts(),
            writer=self.writer,
            content=self.content,
            context_key="dataset-harness-session",
            wall=lambda: "2026-09-26T00:00:00Z",
        )
        self.bundle = DatasetPayloadBundle(
            controller=self.controller,
            writer=self.writer,
            content=self.content,
            clock=lambda: 0.0,
            wall=lambda: "2026-09-26T00:00:00Z",
            quota_evidence=evidence_quota,
            context_key="dataset-harness-session",
        )
        self.controller.mint_dataset_id(
            "op-a", action_id="demo.act/1.0.0", input={}
        )

    def context(self, operation_id: str = "op-a") -> Any:
        return SimpleNamespace(
            operation_id=operation_id,
            dataset_id=f"ds:{operation_id}",
            cancelled=False,
            is_cancelled=lambda: False,
        )

    def staged_count(self) -> int:
        return int(
            self.store.connection.execute(
                "SELECT COUNT(*) FROM capture_staging WHERE state = 'staged'"
            ).fetchone()[0]
        )

    def close(self) -> None:
        self.store.close()


def run(coro: Any) -> Any:
    """Drive one bundle coroutine (the in-tree synchronous convention — no
    async test plugin exists in this suite)."""
    return asyncio.run(coro)


def test_r12_refuse_at_create_names_the_allowance_and_writes_no_row(tmp_path: Path) -> None:
    """R12: payload_create with byte_limit above the remaining dataset
    allowance refuses AT CREATE (the owner ruling, capture-G3 parity —
    never silently reduce), the refusal names the actual allowance, and no
    staging row is written."""
    harness = DatasetHarness(tmp_path, max_dataset_bytes=100)
    try:
        # Consume 40 bytes of the 100-byte dataset budget first.
        first = run(harness.bundle.payload_create("u8", 40, harness.context()))
        run(harness.bundle.payload_append(first, b"x" * 40, harness.context()))
        remaining = 100 - 40
        with pytest.raises(CaptureQuotaExceeded, match=f"payload allowance {remaining} "):
            run(harness.bundle.payload_create("u8", remaining + 1, harness.context()))
        assert harness.staged_count() == 1  # only the first payload's row
    finally:
        harness.close()


def test_r4_payload_allowance_carries_no_capture_clamp_term(tmp_path: Path) -> None:
    """R4's create arm, pinned: the payload allowance is
    min(byte_limit, max_dataset_bytes − used) — asserted WITHOUT the
    max_capture_bytes clamp term. The harness's capture ceiling is 64
    bytes; a 500-byte payload create must ADMIT (a capture of 500 would
    refuse), pinning the formula difference."""
    harness = DatasetHarness(tmp_path, max_capture_bytes=64)
    try:
        payload_id = run(harness.bundle.payload_create("u8", 500, harness.context()))
        assert payload_id == "pay:op-a:1"
        run(harness.bundle.payload_append(payload_id, b"y" * 500, harness.context()))
        record = run(harness.bundle.payload_finalise(payload_id, harness.context()))
        assert record["byte_length"] == 500
    finally:
        harness.close()


def test_payload_create_validates_encoding_and_limit_shape(tmp_path: Path) -> None:
    harness = DatasetHarness(tmp_path)
    try:
        with pytest.raises(DatasetServiceRejected, match="encodings"):
            run(harness.bundle.payload_create("not-an-encoding", 10, harness.context()))
        with pytest.raises(DatasetServiceRejected, match=r"\[1, 2\^53-1\]"):
            run(harness.bundle.payload_create("u8", 0, harness.context()))
        with pytest.raises(DatasetServiceRejected, match=r"\[1, 2\^53-1\]"):
            run(harness.bundle.payload_create("u8", True, harness.context()))
        assert harness.staged_count() == 0
    finally:
        harness.close()


def test_reservation_enforced_and_terminal_appends_refused(tmp_path: Path) -> None:
    """R3's append arms: the reservation bounds appends (mid-payload quota
    refusal is the writer's stamped class), and appends after finalise are
    refused — a published payload stands."""
    harness = DatasetHarness(tmp_path)
    try:
        payload_id = run(harness.bundle.payload_create("u8", 16, harness.context()))
        run(harness.bundle.payload_append(payload_id, b"a" * 10, harness.context()))
        with pytest.raises(CaptureQuotaExceeded, match="payload reservation"):
            run(harness.bundle.payload_append(payload_id, b"b" * 10, harness.context()))
        record = run(harness.bundle.payload_finalise(payload_id, harness.context()))
        with pytest.raises(CaptureFinaliseRejected, match="terminal"):
            run(harness.bundle.payload_append(payload_id, b"c", harness.context()))
        with pytest.raises(CaptureFinaliseRejected, match="finalise is refused"):
            run(harness.bundle.payload_finalise(payload_id, harness.context()))
        assert record["encoding"] == "u8"
    finally:
        harness.close()


def test_r3_finalise_record_is_host_computed(tmp_path: Path) -> None:
    """R3: payload_finalise returns {artifact_id, encoding, byte_length,
    sha256} — every field host-computed over the real bytes (the artifact
    id IS art-<sha256>; adapter-supplied digests are not inputs at all)."""
    import hashlib as _hashlib

    harness = DatasetHarness(tmp_path)
    try:
        payload_id = run(harness.bundle.payload_create("f64le", 64, harness.context()))
        blob = b"\x01" * 64
        run(harness.bundle.payload_append(payload_id, blob, harness.context()))
        record = run(harness.bundle.payload_finalise(payload_id, harness.context()))
        digest = _hashlib.sha256(blob).hexdigest()
        assert record == {
            "artifact_id": f"art-{digest}",
            "encoding": "f64le",
            "byte_length": 64,
            "sha256": digest,
        }
        # The finalise record is registered for THIS operation (M11's
        # source) and the id left the live registry.
        assert harness.controller.finalise_records("op-a")[f"art-{digest}"] == record
        assert payload_id not in harness.controller.live_payload_ids("op-a")
    finally:
        harness.close()


def test_payload_append_honors_cancellation_per_append(tmp_path: Path) -> None:
    harness = DatasetHarness(tmp_path)
    try:
        payload_id = run(harness.bundle.payload_create("u8", 16, harness.context()))
        cancelled = harness.context()
        cancelled.is_cancelled = lambda: True
        with pytest.raises(TimeoutError, match="cancelled"):
            run(harness.bundle.payload_append(payload_id, b"a", cancelled))
        assert harness.staged_count() == 1  # nothing appended
    finally:
        harness.close()


def test_payload_id_from_another_session_refused(tmp_path: Path) -> None:
    """R7's isolation arm through the payload lane: a payload id opened on
    one session key is refused to another (the writer keys the row)."""
    harness = DatasetHarness(tmp_path)
    try:
        payload_id = run(harness.bundle.payload_create("u8", 16, harness.context()))
        # A second bundle over the SAME store but a DIFFERENT context key.
        other = DatasetPayloadBundle(
            controller=DatasetController(contracts=_contracts()),
            writer=CaptureStagingStore(
                harness.store, max_capture_bytes=64, max_dataset_bytes=8192
            ),
            content=harness.content,
            clock=lambda: 0.0,
            wall=lambda: "2026-09-26T00:00:00Z",
            quota_evidence=50,
            context_key="another-session",
        )
        with pytest.raises(CaptureFinaliseRejected, match="wrong session"):
            run(other.payload_append(payload_id, b"a", harness.context()))
        with pytest.raises(CaptureFinaliseRejected, match="wrong session"):
            run(other.payload_finalise(payload_id, harness.context()))
    finally:
        harness.close()


def test_payload_abort_is_idempotent_and_local(tmp_path: Path) -> None:
    """R5's abort arm: abort deletes the staging row (no forensic
    evidence row — the corpus §3's local cleanup, unlike capture's
    marker), and aborts after finalise or of unknown ids are no-ops."""
    harness = DatasetHarness(tmp_path)
    try:
        payload_id = run(harness.bundle.payload_create("u8", 16, harness.context()))
        run(harness.bundle.payload_append(payload_id, b"a" * 8, harness.context()))
        run(harness.bundle.payload_abort(payload_id))
        run(harness.bundle.payload_abort(payload_id))  # idempotent
        assert harness.staged_count() == 0
        evidence_rows = harness.store.connection.execute(
            "SELECT COUNT(*) FROM evidence"
        ).fetchone()[0]
        assert evidence_rows == 0  # no forensic row on the payload lane
        published = run(harness.bundle.payload_create("u8", 8, harness.context()))
        run(harness.bundle.payload_append(published, b"z", harness.context()))
        run(harness.bundle.payload_finalise(published, harness.context()))
        run(harness.bundle.payload_abort(published))  # after finalise: no-op
        finalised = harness.store.connection.execute(
            "SELECT COUNT(*) FROM capture_staging WHERE state = 'finalised'"
        ).fetchone()[0]
        assert finalised == 1  # the published payload stands
    finally:
        harness.close()


def test_r17_payload_refusals_carry_no_capture_wording(tmp_path: Path) -> None:
    """R17's extension to the payload lane: the writer's refusal prose for
    a pay: id names the payload lane — asserted free of capture wording
    for both the create-ceiling and reservation refusals."""
    harness = DatasetHarness(tmp_path, max_dataset_bytes=32)
    try:
        with pytest.raises(CaptureQuotaExceeded) as create_refusal:
            run(harness.bundle.payload_create("u8", 33, harness.context()))
        assert "payload allowance" in str(create_refusal.value)
        assert "apture" not in str(create_refusal.value)
        payload_id = run(harness.bundle.payload_create("u8", 16, harness.context()))
        run(harness.bundle.payload_append(payload_id, b"a" * 8, harness.context()))
        with pytest.raises(CaptureQuotaExceeded) as append_refusal:
            run(harness.bundle.payload_append(payload_id, b"b" * 16, harness.context()))
        assert "payload reservation" in str(append_refusal.value)
        assert "apture" not in str(append_refusal.value)
    finally:
        harness.close()


def test_controller_abort_open_and_sweep_reclaim(tmp_path: Path) -> None:
    """R5: the controller's abort_open reclaims an operation's still-open
    payloads without adapter cooperation, and sweep_open clears every
    operation (plugin_close's sweep)."""
    harness = DatasetHarness(tmp_path)
    try:
        run(harness.bundle.payload_create("u8", 16, harness.context("op-x")))
        run(harness.bundle.payload_create("u8", 16, harness.context("op-y")))
        assert harness.staged_count() == 2
        reclaimed = harness.controller.abort_open("op-x")
        assert reclaimed == ["pay:op-x:1"]
        assert harness.staged_count() == 1
        swept = harness.controller.sweep_open(reason="plugin_close")
        assert swept == ["pay:op-y:2"]  # one per-session counter
        assert harness.staged_count() == 0
    finally:
        harness.close()
