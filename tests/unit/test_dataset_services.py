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
import json
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

_REPO = Path(__file__).resolve().parents[2]


def _measurement() -> dict[str, Any]:
    """The REAL corpus measurement schema (the publish surface validates
    against the pinned bytes, not a stub)."""
    import importlib

    manifest = importlib.import_module("benchweave.standards.manifest")
    active = next(
        entry.version for entry in manifest.load_manifest(_REPO).standards
        if entry.id == "otdp"
    )
    measurement: dict[str, Any] = json.loads(
        (_REPO / "standards" / "otdp" / active / "otdp-measurement.schema.json").read_bytes()
    )
    return measurement


def _contracts() -> ResolvedOtdpContracts:
    """A directly-constructed contracts value (the resolution machinery has
    its own loader-test battery; the bundle only needs the value) — with
    the REAL corpus dataset validator and required keys."""
    from jsonschema import Draft202012Validator

    measurement = _measurement()
    dataset_def = measurement["$defs"]["dataset"]
    return ResolvedOtdpContracts(
        actions={
            "demo.act/1.0.0": CompiledAction(
                input_validator=Draft202012Validator(
                    {
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"},
                            "configuration_id": {"type": "string"},
                        },
                    }
                ),
                output_validator=Draft202012Validator({"type": "object"}),
                side_effect="none",
                lifecycle="direct",
            )
        },
        dataset_required_keys=frozenset(dataset_def.get("required", [])),
        dataset_validator=Draft202012Validator(
            {"$ref": "#/$defs/dataset", "$defs": measurement["$defs"]}
        ),
    )


def a_valid_manifest(dataset_id: str = "ds:op-a") -> dict[str, Any]:
    """A schema-valid scalar_set manifest (the empirically-validated
    fixture shape; invented names throughout)."""
    return {
        "dataset_id": dataset_id,
        "kind": "scalar_set",
        "configuration_id": "conf-1",
        "acquisition_id": None,
        "started_at": "2026-09-26T00:00:00Z",
        "clock": {
            "domain_id": "demo-clock",
            "timestamp_source": "device",
            "synchronisation": "unknown",
            "uncertainty_s": None,
        },
        "axes": [],
        "variables": [
            {
                "id": "voltage_v",
                "quantity": "voltage",
                "unit": "V",
                "channel_ids": ["ch1"],
                "dtype": "float64",
                "dimensions": [],
                "values": [5.0],  # the corpus's scalar: exactly one element
                "uncertainty": {"status": "unknown"},
                "calibration": {"status": "unknown"},
                "status": "valid",
            }
        ],
        "trigger": {"source": "software", "time_relative_s": None},
        "status": "complete",
        "context": {},
    }


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
            channels=("ch1",),
            content=self.content,
            clock=lambda: 0.0,
            wall=lambda: "2026-09-26T00:00:00Z",
            quota_evidence=evidence_quota,
            context_key="dataset-harness-session",
        )
        self.controller.mint_dataset_id(
            "op-a",
            action_id="demo.act/1.0.0",
            input={"x": 1, "configuration_id": "conf-1"},
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


# --- issue #146 slice 3 S3b: dataset_publish + dataset_lookup ----------------------


def evidence_rows(harness: DatasetHarness, kind: str = "dataset") -> int:
    return int(
        harness.store.connection.execute(
            "SELECT COUNT(*) FROM evidence WHERE kind = ?", (kind,)
        ).fetchone()[0]
    )


def test_publish_admits_validates_and_records(tmp_path: Path) -> None:
    """The happy path: a valid manifest publishes (identity, schema, the
    M-subset), its bytes route through the staged writer (a finalised
    staging row whose charged bytes carry the manifest size), one
    kind-dataset evidence row lands, and dataset_lookup returns it."""
    harness = DatasetHarness(tmp_path)
    try:
        admitted = run(harness.bundle.dataset_publish(a_valid_manifest(), harness.context()))
        assert admitted["dataset_id"] == "ds:op-a"
        charged = harness.store.connection.execute(
            "SELECT COALESCE(SUM(charged_bytes), 0) FROM capture_staging"
            " WHERE state = 'finalised'"
        ).fetchone()[0]
        manifest_bytes = len(json.dumps(a_valid_manifest(), sort_keys=True, separators=(",", ":")))
        assert charged == manifest_bytes, "the manifest bytes entered the used ledger"
        assert evidence_rows(harness) == 1
        looked_up = run(harness.bundle.dataset_lookup("ds:op-a", harness.context()))
        assert looked_up == a_valid_manifest()
    finally:
        harness.close()


def test_r2_identity_refusals(tmp_path: Path) -> None:
    """R2's publish identity arms: a manifest whose dataset_id is not the
    host-minted context id refuses; a null context.dataset_id forbids
    publishing."""
    harness = DatasetHarness(tmp_path)
    try:
        with pytest.raises(DatasetServiceRejected, match="does not carry the host-minted"):
            run(
                harness.bundle.dataset_publish(
                    a_valid_manifest("ds:somewhere-else"), harness.context()
                )
            )
        null_context = harness.context()
        null_context.dataset_id = None
        with pytest.raises(DatasetServiceRejected, match="null value forbids publishing"):
            run(harness.bundle.dataset_publish(a_valid_manifest(), null_context))
        assert evidence_rows(harness) == 0
    finally:
        harness.close()


def test_publish_schema_refusal_carries_the_validator_message(tmp_path: Path) -> None:
    harness = DatasetHarness(tmp_path)
    try:
        bad = a_valid_manifest()
        bad["kind"] = "not-a-kind"
        with pytest.raises(DatasetServiceRejected, match="pinned measurement schema"):
            run(harness.bundle.dataset_publish(bad, harness.context()))
        assert evidence_rows(harness) == 0
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        # M01 duplicate variable ids
        (
            lambda m: m["variables"].append(dict(m["variables"][0])),
            "M01: duplicate variable ids",
        ),
        # M01 unknown channel
        (
            lambda m: m["variables"][0].__setitem__("channel_ids", ["nope"]),
            "M01: variable 'voltage_v' references channel 'nope'",
        ),
        # M02 inline count disagreement: a scalar with two elements
        # refuses (scalar product one — the wave-2 narrowing).
        (
            lambda m: m["variables"][0].__setitem__("values", [1.0, 2.0]),
            "M02: variable 'voltage_v' carries 2 inline values",
        ),
        # M04 non-finite inline value (a single element — M02 binds first
        # otherwise)
        (
            lambda m: m["variables"][0].__setitem__("values", [float("nan")]),
            "M04",
        ),
    ],
)
def test_m_structural_refusals(
    tmp_path: Path, mutate: Any, fragment: str
) -> None:
    harness = DatasetHarness(tmp_path)
    try:
        manifest = a_valid_manifest()
        mutate(manifest)
        with pytest.raises(DatasetServiceRejected, match=fragment):
            run(harness.bundle.dataset_publish(manifest, harness.context()))
        assert evidence_rows(harness) == 0
    finally:
        harness.close()


def test_m10_correlation_refusal_and_agreement(tmp_path: Path) -> None:
    """M10: the dispatched action's input declares configuration_id, the
    invoke input carries conf-1 — a manifest echoing a different id
    refuses; the echoing one admits."""
    harness = DatasetHarness(tmp_path)
    try:
        mismatch = a_valid_manifest()
        mismatch["configuration_id"] = "conf-other"
        with pytest.raises(DatasetServiceRejected, match="M10"):
            run(harness.bundle.dataset_publish(mismatch, harness.context()))
        agreeing = a_valid_manifest()
        agreeing["configuration_id"] = "conf-1"
        run(harness.bundle.dataset_publish(agreeing, harness.context()))
        assert evidence_rows(harness) == 1
    finally:
        harness.close()


def test_r11_inline_manifest_bytes_refused_by_dataset_budget(tmp_path: Path) -> None:
    """R11: an inline manifest of N bytes against max_dataset_bytes = N − 1
    REFUSES at publish — no artifact_writer permission involved (inline
    manifests need no payload writers); the refusal exists only because
    the manifest routes through the staged writer."""
    probe = a_valid_manifest()
    size = len(json.dumps(probe, sort_keys=True, separators=(",", ":")))
    harness = DatasetHarness(tmp_path, max_dataset_bytes=size - 1)
    try:
        with pytest.raises(CaptureQuotaExceeded, match="payload allowance"):
            run(harness.bundle.dataset_publish(probe, harness.context()))
        assert evidence_rows(harness) == 0
    finally:
        harness.close()


def test_r8_idempotent_republish_and_divergent_refusal(tmp_path: Path) -> None:
    """R8: a byte-identical manifest under the same dataset id returns the
    admitted manifest with no new rows (staging unchanged, evidence
    unchanged); a divergent manifest under the used id refuses."""
    harness = DatasetHarness(tmp_path)
    try:
        manifest = a_valid_manifest()
        first = run(harness.bundle.dataset_publish(manifest, harness.context()))
        staging_after_first = harness.store.connection.execute(
            "SELECT COUNT(*) FROM capture_staging"
        ).fetchone()[0]
        second = run(harness.bundle.dataset_publish(manifest, harness.context()))
        assert second == first
        assert (
            harness.store.connection.execute(
                "SELECT COUNT(*) FROM capture_staging"
            ).fetchone()[0]
            == staging_after_first
        )
        assert evidence_rows(harness) == 1  # one row, not two
        divergent = a_valid_manifest()
        divergent["variables"][0]["values"] = [9.0]
        with pytest.raises(DatasetServiceRejected, match="immutable"):
            run(harness.bundle.dataset_publish(divergent, harness.context()))
    finally:
        harness.close()


def test_r15_prior_operation_artifact_refuses(tmp_path: Path) -> None:
    """R15 (M11 operation-scoped): a manifest referencing an artifact
    finalised during a PRIOR operation of the same session refuses at
    publish — session-scoped existence would pass every other check."""
    harness = DatasetHarness(tmp_path)
    try:
        # Operation op-prior finalises a payload artifact.
        harness.controller.mint_dataset_id("op-prior")
        prior_id = run(harness.bundle.payload_create("f64le", 8, harness.context("op-prior")))
        run(harness.bundle.payload_append(prior_id, b"\x02" * 8, harness.context("op-prior")))
        prior_record = run(harness.bundle.payload_finalise(prior_id, harness.context("op-prior")))
        # Operation op-a's manifest references it.
        manifest = a_valid_manifest()
        manifest["variables"][0]["values"] = None
        del manifest["variables"][0]["values"]
        manifest["variables"][0]["artifact"] = {
            "artifact_id": prior_record["artifact_id"],
            "encoding": "f64le",
            "byte_length": prior_record["byte_length"],
            "sha256": prior_record["sha256"],
        }
        with pytest.raises(DatasetServiceRejected, match="M11"):
            run(harness.bundle.dataset_publish(manifest, harness.context()))
        assert evidence_rows(harness) == 0
    finally:
        harness.close()


def test_r3_manifest_artifact_fields_cross_checked(tmp_path: Path) -> None:
    """R3's publish arm: a variable whose artifact fields disagree with the
    writer's published record is refused — adapter-supplied digests are
    cross-checked, never trusted."""
    harness = DatasetHarness(tmp_path)
    try:
        payload_id = run(harness.bundle.payload_create("f64le", 8, harness.context()))
        run(harness.bundle.payload_append(payload_id, b"\x03" * 8, harness.context()))
        record = run(harness.bundle.payload_finalise(payload_id, harness.context()))
        manifest = a_valid_manifest()
        manifest["configuration_id"] = "conf-1"
        del manifest["variables"][0]["values"]
        manifest["variables"][0]["artifact"] = {
            "artifact_id": record["artifact_id"],
            "encoding": record["encoding"],
            "byte_length": record["byte_length"],
            "sha256": "f" * 64,  # forged digest
        }
        with pytest.raises(DatasetServiceRejected, match="M11: .* sha256 .* disagrees"):
            run(harness.bundle.dataset_publish(manifest, harness.context()))
        assert evidence_rows(harness) == 0
    finally:
        harness.close()


def test_dataset_payload_publish_full_round_trip(tmp_path: Path) -> None:
    """The fetch shape end to end at the service level: a payload-backed
    variable THIS operation finalised publishes cleanly (M11 agrees, M03
    dtype/encoding pairs, M02 byte length matches the product)."""
    harness = DatasetHarness(tmp_path)
    try:
        payload_id = run(harness.bundle.payload_create("f64le", 8, harness.context()))
        run(harness.bundle.payload_append(payload_id, b"\x04" * 8, harness.context()))
        record = run(harness.bundle.payload_finalise(payload_id, harness.context()))
        manifest = a_valid_manifest()
        manifest["configuration_id"] = "conf-1"
        del manifest["variables"][0]["values"]
        manifest["variables"][0]["artifact"] = dict(record)
        admitted = run(harness.bundle.dataset_publish(manifest, harness.context()))
        assert admitted["dataset_id"] == "ds:op-a"
        assert evidence_rows(harness) == 1
    finally:
        harness.close()


# --- issue #146 slice 3 S3c: artifact_read + R13 ----------------------------------


def _published_artifact(harness: DatasetHarness) -> tuple[str, bytes]:
    """Publish a manifest and return (its routed artifact id, its bytes)."""
    manifest = a_valid_manifest()
    admitted = run(harness.bundle.dataset_publish(manifest, harness.context()))
    blob = json.dumps(admitted, sort_keys=True, separators=(",", ":")).encode()
    return "art-" + __import__("hashlib").sha256(blob).hexdigest(), blob


def test_r13_offset_floor_boundary_table(tmp_path: Path) -> None:
    """R13: negative offsets REFUSE (never clamp — the seam's clamp is the
    pinned MCP behavior, not this bundle's); EOF (offset == size) yields
    zero bytes; beyond size refuses; the middle window reads correctly."""
    from benchweave.content.dataset_services import DatasetFullBundle

    harness = DatasetHarness(tmp_path)
    try:
        # Build the full bundle (reader + writer members) over the harness.
        full = DatasetFullBundle(
            controller=harness.controller,
            writer=harness.writer,
            channels=("ch1",),
            content=harness.content,
            clock=lambda: 0.0,
            wall=lambda: "2026-09-26T00:00:00Z",
            quota_evidence=50,
            context_key="dataset-harness-session",
        )
        artifact_id, blob = _published_artifact(harness)
        size = len(blob)
        assert run(full.artifact_read(artifact_id, 0, 4, harness.context())) == blob[:4]
        # (-1, 1): refuse, never clamp to zero.
        with pytest.raises(DatasetServiceRejected, match="negative"):
            run(full.artifact_read(artifact_id, -1, 1, harness.context()))
        # (-1, MAX): refuse.
        with pytest.raises(DatasetServiceRejected, match="negative"):
            run(full.artifact_read(artifact_id, -1, 2**53 - 1, harness.context()))
        # (size, 1): EOF — zero bytes, per D11.
        assert run(full.artifact_read(artifact_id, size, 1, harness.context())) == b""
        # (size+1, 1): beyond size — refuse.
        with pytest.raises(DatasetServiceRejected, match="window refused"):
            run(full.artifact_read(artifact_id, size + 1, 1, harness.context()))
        # length floor.
        with pytest.raises(DatasetServiceRejected, match="integer >= 1"):
            run(full.artifact_read(artifact_id, 0, 0, harness.context()))
    finally:
        harness.close()


def test_r7_artifact_read_authorization_subset(tmp_path: Path) -> None:
    """R7's reader arm: an artifact this run did NOT publish refuses —
    even one that exists in the store (another session's manifest)."""
    from benchweave.content.dataset_services import DatasetReaderBundle

    harness = DatasetHarness(tmp_path)
    try:
        artifact_id, _blob = _published_artifact(harness)
        # A foreign artifact in the same store (another session's content).
        foreign = harness.content.put_artifact(b"foreign-bytes", "2026-09-26T00:00:00Z")
        reader = DatasetReaderBundle(
            controller=harness.controller,
            writer=harness.writer,
            channels=("ch1",),
            content=harness.content,
            clock=lambda: 0.0,
            wall=lambda: "2026-09-26T00:00:00Z",
            quota_evidence=50,
            context_key="dataset-harness-session",
        )
        assert (
            run(reader.artifact_read(artifact_id, 0, 8, harness.context()))
            == _published_bytes(harness, artifact_id)[:8]
        )
        with pytest.raises(DatasetServiceRejected, match="this run published"):
            run(reader.artifact_read(foreign, 0, 8, harness.context()))
    finally:
        harness.close()


def _published_bytes(harness: DatasetHarness, artifact_id: str) -> bytes:
    row = harness.store.connection.execute(
        "SELECT data FROM artifacts WHERE artifact_id = ?", (artifact_id,)
    ).fetchone()
    return bytes(row[0])


# --- issue #146 slice 3 S3d: the permission-gated builder (§2.2's table) ----------


def _pin_descriptor(harness: DatasetHarness, permissions: list[str]) -> str:
    raw = {
        "id": "dev.local.ds-builder",
        "descriptor_version": "1.0.0",
        "integration": {"adapter": {"permissions": permissions}},
        "channels": [{"id": "ch1"}],
    }
    blob = json.dumps(raw, sort_keys=True).encode()
    digest = __import__("hashlib").sha256(blob).hexdigest()
    harness.content.put_document(blob, digest, raw, "otdp-descriptor", "t")
    pinned: str = digest
    return pinned


def test_r7_builder_permission_table(tmp_path: Path) -> None:
    """R7's structure table: publish/lookup always (the invoke lane);
    payload members only with artifact_writer; artifact_read only with
    artifact_reader — structural absence, asserted by attribute; and the
    composed bundle KEEPS the base's capture members (a capturing class
    device keeps both lanes)."""
    from benchweave.content.capture_services import CaptureServicesBundle
    from benchweave.content.dataset_services import build_dataset_services

    harness = DatasetHarness(tmp_path)
    try:
        for permissions, payload, reader in (
            (["scoped_transport"], False, False),
            (["scoped_transport", "artifact_writer"], True, False),
            (["scoped_transport", "artifact_reader"], False, True),
            (["scoped_transport", "artifact_writer", "artifact_reader"], True, True),
        ):
            base = CaptureServicesBundle(
                content=harness.content,
                clock=lambda: 0.0,
                wall=lambda: "t",
                quota_evidence=10,
                context_key="builder-session",
                writer=harness.writer,
            )
            digest = _pin_descriptor(harness, permissions)
            composed = build_dataset_services(
                controller=harness.controller,
                services=base,
                descriptor_digest=digest,
                content=harness.content,
                writer=harness.writer,
            )
            assert hasattr(composed, "dataset_publish"), permissions
            assert hasattr(composed, "dataset_lookup"), permissions
            assert hasattr(composed, "payload_create") is payload, permissions
            assert hasattr(composed, "payload_append") is payload, permissions
            assert hasattr(composed, "payload_finalise") is payload, permissions
            assert hasattr(composed, "payload_abort") is payload, permissions
            assert hasattr(composed, "artifact_read") is reader, permissions
            # The base's capture members survive the composition.
            assert hasattr(composed, "artifact_append"), permissions
            assert hasattr(composed, "artifact_finalise"), permissions
            assert hasattr(composed, "artifact_abort"), permissions
            assert composed.monotonic() == 0.0  # the base's state carried
    finally:
        harness.close()


# --- issue #146 slice 3 S3e: the riders -------------------------------------------


def test_retention_quota_is_derived_from_one_source() -> None:
    """LOW-3's pin: the max_page_size x 10 retention quota appears as ONE
    textual derivation in app.py (the helper) — every consumer derives
    from it, so the three historical sites cannot drift apart."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src/benchweave/interfaces/app.py").read_text()
    assert source.count('max_page_size"]) * 10') == 1, (
        "the max_page_size x10 retention derivation must appear exactly "
        "once (the _retention_quota helper); consumers derive from it"
    )
    assert "def _retention_quota(" in source


def test_dataset_shape_note_names_the_schema_finding(tmp_path: Path) -> None:
    """Rider (c): a dataset-shaped result that also fails the pinned
    schema carries the validator's own finding in the refusal note (a
    `kind` outside the corpus's nine dataset kinds names the enum) — and
    a schema-clean unpublished dataset carries no note (the publication
    lie stands alone)."""
    harness = DatasetHarness(tmp_path)
    try:
        bogus = a_valid_manifest()
        bogus["kind"] = "not-a-kind"
        note = harness.controller.dataset_shape_note(bogus)
        assert note is not None and "not-a-kind" in note and "kind" in note
        assert harness.controller.dataset_shape_note(a_valid_manifest()) is None
        assert harness.controller.dataset_shape_note({"not": "shaped"}) is None
    finally:
        harness.close()


# --- wave 2: the publish leak, M02 narrowing, the epilogue floor -------------------


def test_w2_publish_evidence_quota_refusal_charges_nothing(tmp_path: Path) -> None:
    """Wave2 #1 (critic-HIGH + adversary-F1, both measured): a publish
    whose evidence row refuses on quota must leave the ledger EXACTLY as
    before — the old order finalised the routed manifest BEFORE the
    evidence write and the reclaim aborted a FINALISED row (a no-op), so
    the manifest bytes charged `used` permanently and retries ratcheted
    the dataset budget down. The honest boundary is ONE transaction:
    artifact, staging flip and evidence row commit together or not at
    all."""
    from benchweave.content.store import EvidenceQuotaExceeded

    harness = DatasetHarness(tmp_path, evidence_quota=1)
    try:
        manifest = a_valid_manifest()
        first = run(harness.bundle.dataset_publish(manifest, harness.context()))
        assert first["dataset_id"] == "ds:op-a"
        after_first = harness.writer.used_bytes("dataset-harness-session")
        # The second publish, under a fresh operation and dataset id, hits
        # the evidence quota (quota=1 is already consumed).
        second = a_valid_manifest()
        second["dataset_id"] = "ds:op-b"
        with pytest.raises(EvidenceQuotaExceeded):
            run(harness.bundle.dataset_publish(second, harness.context("op-b")))
        # Nothing charged: the ledger returns to the post-first state.
        assert harness.writer.used_bytes("dataset-harness-session") == after_first, (
            "the quota-refused publish leaked its routed manifest bytes "
            "into the used ledger"
        )
        # Zero orphan staging rows and exactly ONE finalised row (the
        # first publish's); no second artifact.
        staged = harness.store.connection.execute(
            "SELECT COUNT(*) FROM capture_staging WHERE state = 'staged'"
        ).fetchone()[0]
        finalised = harness.store.connection.execute(
            "SELECT COUNT(*) FROM capture_staging WHERE state = 'finalised'"
        ).fetchone()[0]
        assert staged == 0
        assert finalised == 1
        # No registry/store divergence: the refused operation's payload id
        # is terminal in the registry and ABSENT from the store.
        assert harness.controller.live_payload_ids("op-b") == ()
        refused_ids = harness.store.connection.execute(
            "SELECT capture_id FROM capture_staging"
        ).fetchall()
        assert all("op-b" not in str(row[0]) for row in refused_ids)
    finally:
        harness.close()


def test_w2_m02_scalar_product_one_boundary_table(tmp_path: Path) -> None:
    """Wave2 #2 (critic-M + adversary-F2): the flattened element count is
    the product of axis lengths WITH SCALAR PRODUCT ONE (mm.md §1/§2) — a
    dimensionless scalar carries exactly one element. The ONLY suspension
    is mm.md 188-191's derived-invalid record (empty values, empty
    dimensions, invalid status, the §8 derivation marker) — a shape never
    established asserts no element count."""
    harness = DatasetHarness(tmp_path)
    try:
        # Refused: scalar with 0, 2 and 3 elements.
        for _count, values in ((0, []), (2, [1.0, 2.0]), (3, [1.0, 2.0, 3.0])):
            manifest = a_valid_manifest()
            manifest["variables"][0]["values"] = values
            with pytest.raises(
                DatasetServiceRejected, match="M02: .*dimension product of 1"
            ):
                run(harness.bundle.dataset_publish(manifest, harness.context()))
        # Refused: a scalar artifact whose byte_length is not one element.
        payload_id = run(harness.bundle.payload_create("f64le", 8, harness.context()))
        run(harness.bundle.payload_append(payload_id, b"\x05" * 8, harness.context()))
        record = run(harness.bundle.payload_finalise(payload_id, harness.context()))
        manifest = a_valid_manifest()
        manifest["configuration_id"] = "conf-1"
        del manifest["variables"][0]["values"]
        forged = dict(record)
        forged["byte_length"] = 16  # two elements claimed as a scalar
        manifest["variables"][0]["artifact"] = forged
        with pytest.raises(DatasetServiceRejected, match="M02: .*byte_length"):
            run(harness.bundle.dataset_publish(manifest, harness.context()))
        # Admitted: the derived-invalid record suspends count agreement.
        derived_invalid = a_valid_manifest()
        derived_invalid["variables"][0].update(
            {
                "values": [],
                "status": "invalid",
                "status_reason": "operand_not_established",
                "derivation": {
                    "kind": "expression",
                    "expression": "a / b",
                    "operand_ids": ["a", "b"],
                },
            }
        )
        admitted = run(
            harness.bundle.dataset_publish(derived_invalid, harness.context())
        )
        assert admitted["variables"][0]["values"] == []
    finally:
        harness.close()
