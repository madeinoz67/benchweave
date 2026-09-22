"""The explicit async-to-sync seam preserves host safety semantics."""

import asyncio
import hashlib
import json as _json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from benchweave.content.capture_services import build_capture_services
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.store import ContentStore
from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.plugin import SimulationInfo
from benchweave.host.services import QuotaLimits
from benchweave.host.types import (
    CaptureQuotaExceeded,
    DispatchState,
    ErrorCode,
    Identity,
    OperationRequest,
    OperationStatus,
    OperationVerb,
    Reading,
    WriteReceipt,
)
from benchweave.state.store import Store


class Adapter:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    async def open(self, descriptor: dict[str, Any], services: Any, context: Any) -> None:
        self.services = services
        self.context = context

    async def close(self, context: Any) -> None:
        self.closed = True

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        self.calls += 1
        self.context = context
        return {
            "operation_id": request["operation_id"],
            "verb": request["verb"],
            "status": "ok",
            "data": {
                "manufacturer": "Example",
                "model": "Thermometer",
                "serial": None,
                "firmware": None,
                "source": "device",
            },
        }


def bridge(adapter: Adapter) -> OTDPBridge:
    return OTDPBridge(
        adapter,
        descriptor={},
        services=SimpleNamespace(monotonic=lambda: 10.0),
        simulation=SimulationInfo(True, "Synthetic"),
    )


def test_identify_uses_scoped_services_and_same_clock() -> None:
    adapter = Adapter()
    plugin = bridge(adapter)
    plugin.plugin_open(object())
    result = plugin.dispatch(OperationRequest.identify("op"), deadline_ns=11_000_000_000)
    assert result.status is OperationStatus.OK
    assert isinstance(result.data, Identity)
    assert adapter.context.deadline_monotonic == 11.0
    assert adapter.context.operation_id == "op"
    assert plugin.simulation.label == "Synthetic"
    plugin.plugin_close()
    assert adapter.closed


def test_expired_deadline_does_not_execute() -> None:
    adapter = Adapter()
    plugin = bridge(adapter)
    plugin.plugin_open(object())
    result = plugin.dispatch(OperationRequest.identify("op"), deadline_ns=9_000_000_000)
    assert result.error is not None
    assert result.error.code is ErrorCode.TIMEOUT
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
    assert adapter.calls == 0
    plugin.plugin_close()


@pytest.mark.parametrize("mode", ["raise", "late", "wrong_identity"])
def test_uncertain_results_never_claim_not_dispatched(mode: str) -> None:
    class Bad(Adapter):
        async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
            if mode == "raise":
                self.calls += 1
                raise ConnectionError("after possible transfer")
            result = await super().execute(request, context)
            if mode == "late":
                self.services.monotonic = lambda: 12.0
            else:
                result["operation_id"] = "other"
            return result

    adapter = Bad()
    plugin = bridge(adapter)
    plugin.plugin_open(object())
    result = plugin.dispatch(OperationRequest.identify("op"), deadline_ns=11_000_000_000)
    assert result.status is OperationStatus.UNKNOWN
    assert result.error is not None
    assert result.error.dispatch_state is DispatchState.UNKNOWN
    assert adapter.calls == 1
    second = plugin.dispatch(OperationRequest.identify("next"), deadline_ns=20_000_000_000)
    assert second.status is OperationStatus.ERROR
    assert adapter.calls == 1
    plugin.plugin_close()


def test_failed_open_closes_adapter() -> None:
    class Bad(Adapter):
        async def open(self, descriptor: dict[str, Any], services: Any, context: Any) -> None:
            raise RuntimeError("partial open")

    adapter = Bad()
    plugin = bridge(adapter)
    with pytest.raises(RuntimeError, match="partial open"):
        plugin.plugin_open(object())
    assert adapter.closed


def test_unsupported_profile_never_reaches_adapter() -> None:
    adapter = Adapter()
    plugin = bridge(adapter)
    plugin.plugin_open(object())
    result = plugin.dispatch(
        OperationRequest("op", OperationVerb.INVOKE, {"profile": "x"}),
        deadline_ns=11_000_000_000,
    )
    assert result.error is not None
    assert result.error.code is ErrorCode.UNSUPPORTED
    assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
    assert adapter.calls == 0
    plugin.plugin_close()


def test_write_receipt_conversion() -> None:
    class Writer(Adapter):
        async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
            await context.mark_dispatch_started()
            return {
                "operation_id": request["operation_id"],
                "verb": "write",
                "status": "ok",
                "data": {
                    "parameter": "setpoint",
                    "requested_value": 4,
                    "effective_value": 4,
                    "assurance": "acknowledged",
                },
            }

    plugin = bridge(Writer())
    plugin.plugin_open(object())
    result = plugin.dispatch(
        OperationRequest.write("op", parameter="setpoint", value=4),
        deadline_ns=11_000_000_000,
    )
    assert result.status is OperationStatus.OK
    assert isinstance(result.data, WriteReceipt)
    assert result.data.effective_value == 4
    plugin.plugin_close()


@pytest.mark.parametrize("field,value", [("model", ["bad"]), ("serial", 3)])
def test_malformed_identity_is_unknown(field: str, value: Any) -> None:
    class Malformed(Adapter):
        async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
            result = await super().execute(request, context)
            result["data"][field] = value
            return result

    plugin = bridge(Malformed())
    plugin.plugin_open(object())
    result = plugin.dispatch(OperationRequest.identify("op"), deadline_ns=11_000_000_000)
    assert result.status is OperationStatus.UNKNOWN
    plugin.plugin_close()


@pytest.mark.parametrize("bad_value", [[23.5], float("nan"), {"value": 23.5}])
def test_malformed_scalar_read_is_unknown(bad_value: Any) -> None:
    class Reader(Adapter):
        async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
            return {
                "operation_id": request["operation_id"],
                "verb": "read",
                "status": "ok",
                "data": {
                    "parameter": "temperature",
                    "value": bad_value,
                    "unit": "Cel",
                    "observed_at": "2026-09-12T00:00:00Z",
                    "age_ms": 0,
                    "quality": "valid",
                    "source": "device",
                },
            }

    plugin = bridge(Reader())
    plugin.plugin_open(object())
    result = plugin.dispatch(
        OperationRequest.read("op", parameter="temperature"), deadline_ns=11_000_000_000
    )
    assert result.status is OperationStatus.UNKNOWN
    plugin.plugin_close()


def test_scalar_read_conversion() -> None:
    class Reader(Adapter):
        async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
            return {
                "operation_id": request["operation_id"],
                "verb": "read",
                "status": "ok",
                "data": {
                    "parameter": "temperature",
                    "value": 23.5,
                    "unit": "Cel",
                    "observed_at": "2026-09-12T00:00:00Z",
                    "age_ms": 0,
                    "quality": "valid",
                    "source": "device",
                },
            }

    plugin = bridge(Reader())
    plugin.plugin_open(object())
    result = plugin.dispatch(
        OperationRequest.read("op", parameter="temperature"), deadline_ns=11_000_000_000
    )
    assert isinstance(result.data, Reading)
    assert result.data.value == 23.5
    plugin.plugin_close()


@pytest.mark.parametrize("marked", [False, True])
def test_cancelled_dispatch_state_is_preserved_or_rejected(marked: bool) -> None:
    class Cancelled(Adapter):
        async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
            if marked:
                await context.mark_dispatch_started()
            return {
                "operation_id": request["operation_id"],
                "verb": "identify",
                "status": "cancelled",
                "error": {
                    "code": "CANCELLED",
                    "message": "Cancelled",
                    "dispatch_state": "not_dispatched",
                },
            }

    plugin = bridge(Cancelled())
    plugin.plugin_open(object())
    result = plugin.dispatch(OperationRequest.identify("op"), deadline_ns=11_000_000_000)
    assert result.status is (OperationStatus.UNKNOWN if marked else OperationStatus.CANCELLED)
    plugin.plugin_close()


# --- issue #43 slice 1: capture dispatch ---------------------------------------
#
# Derivations (from primary sources, not the plan's restatement): the
# four-argument capture request is the corpus $defs/operationRequest
# capture branch (required {capture_id, format, sample_count, max_bytes},
# additionalProperties false) and spec §5 line 87 ("Host capture ID,
# format, sample count, maximum bytes"); the capture_id shape is the
# contract id pattern ^[a-z][a-z0-9_.-]*$ (interface.schema.json); the
# integer bound is spec §4's interoperable range (2^53-1); count×8 is
# spec §7 line 154; "Requests must satisfy both descriptor and host
# limits" is §7 line 152; the classification arms' dispatch_state table is
# A7 (gate refusals not_dispatched; every post-execute refusal
# dispatched); the forensic mold is C1.

CAPTURE_DESCRIPTOR = {
    "capture_formats": ["waveform_f64le", "raw_binary"],
    "capture_limits": {"max_samples": 1024, "max_bytes": 8192},
}

_WAVEFORM_METADATA = {
    "format": "waveform_f64le",
    "started_at": "2026-09-22T00:00:00Z",
    "sample_interval_s": 0.001,
    "unit": "V",
}


class CaptureHarness:
    """A real store + writer + bundle + controller + bridge over tmp_path."""

    def __init__(self, tmp_path: Path, *, evidence_quota: int = 50) -> None:
        import pathlib

        self.store = Store.open(pathlib.Path(tmp_path) / "bridge-capture.db")
        self.db_path = str(
            self.store.connection.execute("PRAGMA database_list").fetchone()[2]
        )
        self.content = ContentStore(self.store)
        raw_descriptor = {
            "id": "dev.local.capture-harness",
            "descriptor_version": "1.0.0",
            "integration": {
                "mode": "adapter",
                "adapter": {
                    "entry_point": "harness:create_plugin",
                    "api_version": "1.1",
                    "version": "1.0.0",
                    "dependencies": [],
                    "permissions": ["scoped_transport", "artifact_writer"],
                },
            },
        }
        descriptor_bytes = _json.dumps(raw_descriptor, sort_keys=True).encode()
        self.descriptor_digest = hashlib.sha256(descriptor_bytes).hexdigest()
        self.content.put_document(
            descriptor_bytes,
            self.descriptor_digest,
            raw_descriptor,
            "otdp-descriptor",
            "2026-09-22T00:00:00Z",
        )
        self.writer = CaptureStagingStore(
            self.store, max_capture_bytes=8192, max_dataset_bytes=8192
        )
        self.bundle, self.controller = build_capture_services(
            descriptor_digest=self.descriptor_digest,
            content=self.content,
            writer=self.writer,
            clock=lambda: 0.0,
            wall=lambda: "2026-09-22T00:00:00Z",
            quota=QuotaLimits(
                max_dataset_bytes=8192,
                max_evidence_entries=evidence_quota,
                max_event_batch=10,
            ),
            context_key="capture-harness-session",
        )
        assert self.controller is not None
        self.adapter: Any = None

    def bridge(self, adapter: Any) -> OTDPBridge:
        self.adapter = adapter
        return OTDPBridge(
            adapter,
            descriptor=dict(CAPTURE_DESCRIPTOR),
            services=self.bundle,
            simulation=SimulationInfo(True, "Synthetic"),
            capture=self.controller,
        )

    def close(self) -> None:
        self.store.close()

    def forensic_count(self, capture_id: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM evidence WHERE kind = 'event_log'"
        if capture_id is None:
            return int(self.store.connection.execute(sql).fetchone()[0])
        return int(
            self.store.connection.execute(
                sql + " AND content_ref_json LIKE ?",
                (f'%"{capture_id}"%',),
            ).fetchone()[0]
        )

    def staged_count(self) -> int:
        return int(
            self.store.connection.execute(
                "SELECT COUNT(*) FROM capture_staging WHERE state = 'staged'"
            ).fetchone()[0]
        )

    def artifact_count(self) -> int:
        return int(
            self.store.connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        )


class CaptureAdapter(Adapter):
    """Appends chunks and finalises through the services the bridge hands
    over at open (the A11 shape), returning the finalise manifest."""

    def __init__(self, chunks: int = 2, chunk_bytes: int = 8) -> None:
        super().__init__()
        self.chunks = chunks
        self.chunk_bytes = chunk_bytes
        self.services: Any = None

    async def open(self, descriptor: dict[str, Any], services: Any, context: Any) -> None:
        self.services = services
        await super().open(descriptor, services, context)

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        self.calls += 1
        if request["verb"] != "capture":
            return await Adapter.execute(self, request, context)
        arguments = request["arguments"]
        capture_id = arguments["capture_id"]
        for _ in range(self.chunks):
            await self.services.artifact_append(
                capture_id, b"\x01" * self.chunk_bytes, context
            )
        manifest = await self.services.artifact_finalise(
            capture_id, dict(_WAVEFORM_METADATA), context
        )
        return {
            "operation_id": request["operation_id"],
            "verb": "capture",
            "status": "ok",
            "data": manifest,
        }


def a_capture_request(**overrides: Any) -> OperationRequest:
    arguments: dict[str, Any] = {
        "capture_id": "cap-1",
        "format": "waveform_f64le",
        "sample_count": 2,
        "max_bytes": 64,
    }
    arguments.update(overrides)
    return OperationRequest("op-c", OperationVerb.CAPTURE, arguments)


def a_capture_dispatch(
    harness: CaptureHarness, adapter: Any, request: OperationRequest
) -> tuple[OTDPBridge, Any]:
    plugin = harness.bridge(adapter)
    plugin.plugin_open(object())
    return plugin, plugin.dispatch(request, deadline_ns=10_000_000_000)


# --- R1: bounds before the device ------------------------------------------------


def test_capture_g1_arithmetic_refused_before_the_device(tmp_path: Path) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        plugin, result = a_capture_dispatch(
            harness, Adapter(), a_capture_request(sample_count=9, max_bytes=64)
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_ARGUMENT
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert harness.adapter.calls == 0
        assert harness.forensic_count() == 0  # R1's gate arm: zero markers
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("overrides", "label"),
    [
        ({"sample_count": 2048}, "over max_samples"),
        ({"max_bytes": 999999}, "over descriptor max_bytes"),
        ({"format": "csv"}, "format not in capture_formats"),
    ],
)
def test_capture_g2_descriptor_limit_refusals(
    tmp_path: Path, overrides: dict[str, Any], label: str
) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        plugin, result = a_capture_dispatch(
            harness, Adapter(), a_capture_request(**overrides)
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_ARGUMENT, label
        assert harness.adapter.calls == 0, label
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("limits", "label"),
    [
        ("not-an-object", "non-dict limits"),
        ({"max_samples": 1024, "max_bytes": 8192, "extra": 1}, "limits ok"),
        ({"max_samples": "1024", "max_bytes": 8192}, "string max_samples"),
        ({"max_samples": -1, "max_bytes": 8192}, "negative max_samples"),
        ({"max_samples": 1024}, "absent max_bytes"),
    ],
)
def test_capture_malformed_descriptor_limits_refuse_cleanly(
    tmp_path: Path, limits: Any, label: str
) -> None:
    """The gate region has no exception frame: a malformed descriptor's
    limits must yield a clean INVALID_ARGUMENT, never an escaping
    exception (the record's malformed-descriptor rule)."""
    harness = CaptureHarness(tmp_path)
    adapter = CaptureAdapter()
    harness.adapter = adapter
    try:
        descriptor = dict(CAPTURE_DESCRIPTOR, capture_limits=limits)
        plugin = OTDPBridge(
            adapter,
            descriptor=descriptor,
            services=harness.bundle,
            simulation=SimulationInfo(True, "Synthetic"),
            capture=harness.controller,  # real: the limits are the variable
        )
        plugin.plugin_open(object())
        result = plugin.dispatch(
            a_capture_request(), deadline_ns=10_000_000_000
        )
        if label == "limits ok":
            # The limits gate passed: the outcome is a capture outcome,
            # not a limits refusal.
            assert result.error is None or (
                result.error.code is not ErrorCode.INVALID_ARGUMENT
            )
        else:
            assert result.error is not None
            assert result.error.code is ErrorCode.INVALID_ARGUMENT, label
            assert harness.adapter.calls == 0
        plugin.plugin_close()
    finally:
        harness.close()


def test_capture_g3_quota_refusal_is_resource_limit_not_dispatched(tmp_path: Path) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        # Fill the context's ledger: reserved 8128 of Md=8192 leaves 64.
        assert harness.controller is not None
        harness.controller.open_capture(
            capture_id="cap-held",
            fmt="raw_binary",
            sample_count=None,
            max_bytes=8128,
        )
        plugin, result = a_capture_dispatch(
            harness, Adapter(), a_capture_request(max_bytes=65)
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.RESOURCE_LIMIT
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert harness.adapter.calls == 0
        assert harness.forensic_count() == 0  # nothing was opened
        assert harness.staged_count() == 1  # only the held capture
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("overrides", "label"),
    [
        ({"sample_count": True}, "bool sample_count"),
        ({"sample_count": 2.0}, "float sample_count"),
        ({"max_bytes": 0}, "zero max_bytes"),
        ({"max_bytes": -(2**53)}, "negative max_bytes"),
        ({"max_bytes": 2**53}, "above 2^53-1"),
        ({"sample_count": 2, "max_bytes": 2**53}, "max_bytes above 2^53-1"),
    ],
)
def test_capture_typing_is_exact_and_bounded(
    tmp_path: Path, overrides: dict[str, Any], label: str
) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        plugin, result = a_capture_dispatch(
            harness, Adapter(), a_capture_request(**overrides)
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_ARGUMENT, label
        assert harness.adapter.calls == 0, label
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize("bad_id", ["Bad-ID", "1abc", "../escape", "cap/1", ""])
def test_capture_id_shape_is_validated(tmp_path: Path, bad_id: Any) -> None:
    """The contract id pattern ^[a-z][a-z0-9_.-]*$ (interface.schema.json);
    the writer's PRIMARY KEY enforces session-uniqueness."""
    harness = CaptureHarness(tmp_path)
    try:
        plugin, result = a_capture_dispatch(
            harness, Adapter(), a_capture_request(capture_id=bad_id)
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_ARGUMENT
        assert harness.adapter.calls == 0
        plugin.plugin_close()
    finally:
        harness.close()


# --- R8: the permission gate -------------------------------------------------------


def test_capture_without_the_controller_is_unsupported_not_dispatched(tmp_path: Path) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        plugin = OTDPBridge(
            Adapter(),
            descriptor=dict(CAPTURE_DESCRIPTOR),
            services=SimpleNamespace(monotonic=lambda: 0.0),
            simulation=SimulationInfo(True, "Synthetic"),
        )
        plugin.plugin_open(object())
        result = plugin.dispatch(a_capture_request(), deadline_ns=10_000_000_000)
        assert result.error is not None
        assert result.error.code is ErrorCode.UNSUPPORTED
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert "artifact_writer" in result.error.message
        # Zero writer rows ever created.
        rows = harness.store.connection.execute(
            "SELECT COUNT(*) FROM capture_staging"
        ).fetchone()[0]
        assert rows == 0
        plugin.plugin_close()
    finally:
        harness.close()


# --- the happy path and R3 ---------------------------------------------------------


def test_capture_round_trip_returns_the_host_constructed_manifest(tmp_path: Path) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        adapter = CaptureAdapter(chunks=2, chunk_bytes=8)
        plugin, result = a_capture_dispatch(harness, adapter, a_capture_request())
        assert result.status is OperationStatus.OK
        manifest = result.data
        digest = hashlib.sha256(b"\x01" * 16).hexdigest()
        assert manifest["sha256"] == digest
        assert manifest["byte_length"] == 16
        assert manifest["artifact_id"] == "art-" + digest
        assert manifest["sample_count"] == 2
        assert manifest["sample_interval_s"] == 0.001
        assert manifest["unit"] == "V"
        assert manifest["capture_id"] == "cap-1"
        assert manifest["format"] == "waveform_f64le"
        # R3: the control recompute hashes the STORED bytes, not the column.
        stored = harness.store.connection.execute(
            "SELECT data FROM artifacts WHERE artifact_id = ?", ("art-" + digest,)
        ).fetchone()[0]
        assert hashlib.sha256(bytes(stored)).hexdigest() == digest
        # Success retires the capture: no forensic row, none at close.
        assert harness.forensic_count() == 0
        plugin.plugin_close()
        assert harness.forensic_count() == 0
    finally:
        harness.close()


def test_adapter_supplied_integrity_fields_are_ignored_not_trusted(tmp_path: Path) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        class Lying(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                result = await super().execute(request, context)
                result["data"] = dict(
                    result["data"],
                    sha256="0" * 64,
                    byte_length=999999,
                    artifact_id="art-forged",
                )
                return result

        plugin, result = a_capture_dispatch(harness, Lying(), a_capture_request())
        assert result.status is OperationStatus.OK
        digest = hashlib.sha256(b"\x01" * 16).hexdigest()
        assert result.data["sha256"] == digest  # host values, not the lie
        assert result.data["byte_length"] == 16
        assert result.data["artifact_id"] == "art-" + digest
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_short_capture_is_refused_at_finalise_and_poisons(tmp_path: Path) -> None:
    """R3: a short-writing adapter (declared sample_count exceeds delivered
    bytes) is refused by the writer's finalise — a shape refusal, so the
    poison posture holds and nothing publishes; the epilogue reclaims."""
    harness = CaptureHarness(tmp_path)
    try:
        adapter = CaptureAdapter(chunks=1, chunk_bytes=8)  # 8 of 16 declared
        plugin, result = a_capture_dispatch(harness, adapter, a_capture_request())
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.dispatch_state is DispatchState.UNKNOWN
        # Nothing published: the only artifact row is the forensic payload.
        assert harness.artifact_count() == harness.forensic_count("cap-1")
        assert harness.staged_count() == 0  # the epilogue reclaimed
        assert harness.forensic_count("cap-1") == 1
        second = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert second.error is not None  # poisoned: a fresh bridge is required
        plugin.plugin_close()
    finally:
        harness.close()


# --- R2: abort-not-published --------------------------------------------------------


def test_append_then_raise_publishes_nothing_with_one_forensic_row(tmp_path: Path) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        midflight: dict[str, int] = {}

        class AppendThenRaise(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                self.calls += 1
                await self.services.artifact_append("cap-1", b"\x01" * 8, context)
                midflight["chunks"] = harness.staged_count()
                raise RuntimeError("device failed mid-capture")

        plugin, result = a_capture_dispatch(
            harness, AppendThenRaise(), a_capture_request()
        )
        assert midflight["chunks"] == 1  # positive precondition (C6)
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.dispatch_state in (
            DispatchState.DISPATCHED,
            DispatchState.UNKNOWN,
        )
        # Zero published capture rows (the one artifact is the payload).
        assert harness.artifact_count() == harness.forensic_count("cap-1")
        assert harness.staged_count() == 0  # writer reclaim asserted directly
        assert harness.forensic_count("cap-1") == 1  # exactly one forensic row
        plugin.plugin_close()
    finally:
        harness.close()


# --- R5: cancellation mid-capture ----------------------------------------------------


def test_deadline_expiry_mid_capture_reclaims_without_adapter_cooperation(tmp_path: Path) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        class OverstayingAppend(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                self.calls += 1
                await self.services.artifact_append("cap-1", b"\x01" * 8, context)
                await asyncio.sleep(1.0)  # blows the 0.3s dispatch budget
                return await super().execute(request, context)

        plugin = harness.bridge(OverstayingAppend())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_capture_request(), deadline_ns=300_000_000)
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.code is ErrorCode.TIMEOUT
        assert harness.artifact_count() == harness.forensic_count("cap-1")
        assert harness.staged_count() == 0  # the epilogue ran (no cooperation)
        assert harness.forensic_count("cap-1") == 1
        plugin.plugin_close()
    finally:
        harness.close()


def test_cooperative_overstaying_cleanup_is_cut_and_close_completes(tmp_path: Path) -> None:
    """R6: a cleanup that yields but overstays is cut by the bridge's
    deadline and plugin_close still completes (wall-bounded). A cleanup
    that NEVER yields cannot be preempted by any asyncio timeout — that
    residual is disclosed (deferral row 11), NOT asserted here."""
    harness = CaptureHarness(tmp_path)
    try:
        class Cooperative(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                self.calls += 1
                try:
                    await self.services.artifact_append("cap-1", b"\x01" * 8, context)
                    await asyncio.sleep(1.0)  # overstay the budget
                finally:
                    await asyncio.sleep(0.05)  # yields, but overstays further
                    await self.services.artifact_abort("cap-1")
                raise AssertionError("unreachable")  # pragma: no cover

        plugin = harness.bridge(Cooperative())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_capture_request(), deadline_ns=300_000_000)
        assert result.status is OperationStatus.UNKNOWN
        plugin.plugin_close()  # completes (the wall-bounded claim)
        assert harness.forensic_count("cap-1") == 1  # epilogue or cooperative abort
        assert harness.staged_count() == 0
    finally:
        harness.close()


# --- the classification arms ---------------------------------------------------------


def test_mid_append_quota_is_resource_limit_and_the_session_survives(tmp_path: Path) -> None:
    """A7's append-time arm: RESOURCE_LIMIT, dispatched, session NOT
    poisoned, zero staging rows, exactly one forensic row."""
    harness = CaptureHarness(tmp_path)
    try:
        class OverAppend(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                self.calls += 1
                if request["verb"] != "capture":
                    return await Adapter.execute(self, request, context)
                await self.services.artifact_append("cap-1", b"\x01" * 40, context)
                await self.services.artifact_append("cap-1", b"\x01" * 40, context)
                raise AssertionError("unreachable")

        plugin, result = a_capture_dispatch(
            harness,
            OverAppend(),
            a_capture_request(max_bytes=64),
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.RESOURCE_LIMIT
        assert result.error.dispatch_state is DispatchState.DISPATCHED
        assert harness.staged_count() == 0
        assert harness.forensic_count("cap-1") == 1
        # The session survives: a fresh dispatch still executes.
        follow = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert follow.status is OperationStatus.OK
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_bare_unstamped_quota_raise_keeps_the_poison_posture(tmp_path: Path) -> None:
    """C3's negative arm: the class alone buys nothing — a bare
    CaptureQuotaExceeded from adapter code lacks the writer's stamp."""
    harness = CaptureHarness(tmp_path)
    try:
        class Bare(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                self.calls += 1
                if request["verb"] != "capture":
                    return await Adapter.execute(self, request, context)
                raise CaptureQuotaExceeded("adapter code can raise the class too")

        plugin, result = a_capture_dispatch(harness, Bare(), a_capture_request())
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.code is ErrorCode.PROTOCOL_ERROR
        follow = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert follow.error is not None  # poisoned
        plugin.plugin_close()
    finally:
        harness.close()


def test_evidence_quota_is_resource_limit_and_the_session_survives(tmp_path: Path) -> None:
    """B8: the bundle's record_evidence keeps all-kind COUNT semantics and
    stamps its refusals — quota is a resource condition, not a protocol
    lie, so the session survives."""
    harness = CaptureHarness(tmp_path, evidence_quota=1)
    try:
        class Evidence(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                self.calls += 1
                if request["verb"] != "capture":
                    return await Adapter.execute(self, request, context)
                await self.services.record_evidence(
                    {"kind": "device_error", "entry": {"code": "E1", "message": "x"}},
                    context,
                )
                await self.services.record_evidence(
                    {"kind": "device_error", "entry": {"code": "E2", "message": "y"}},
                    context,
                )
                return await super().execute(request, context)

        plugin, result = a_capture_dispatch(harness, Evidence(), a_capture_request())
        assert result.error is not None
        assert result.error.code is ErrorCode.RESOURCE_LIMIT
        assert result.error.dispatch_state is DispatchState.DISPATCHED
        follow = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert follow.status is OperationStatus.OK
        plugin.plugin_close()
    finally:
        harness.close()


def test_writer_originated_lock_contention_is_resource_limit(tmp_path: Path) -> None:
    """C5: the holder acquires the write lock MID-capture (between the
    bridge's open and the adapter's append); the writer-originated
    OperationalError classifies RESOURCE_LIMIT, the session survives and
    the epilogue reclaims once the holder releases."""
    harness = CaptureHarness(tmp_path)
    try:
        harness.store.connection.execute("PRAGMA busy_timeout=80")

        class Contended(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                self.calls += 1
                if request["verb"] != "capture":
                    return await Adapter.execute(self, request, context)
                contender = sqlite3.connect(harness.db_path, timeout=0.05)
                try:
                    contender.execute("BEGIN IMMEDIATE")
                    contender.execute(
                        "INSERT INTO benches (bench_id, generation, qualification,"
                        " configuration_json, licence, updated_at)"
                        " VALUES ('contended', 1, 'q', '{}', 'l', 't')"
                    )
                    await self.services.artifact_append("cap-1", b"\x01" * 8, context)
                    raise AssertionError("append should have failed on the lock")
                except sqlite3.OperationalError:
                    raise
                finally:
                    contender.rollback()
                    contender.close()
                raise AssertionError("unreachable")  # pragma: no cover

        plugin, result = a_capture_dispatch(harness, Contended(), a_capture_request())
        assert result.error is not None
        assert result.error.code is ErrorCode.RESOURCE_LIMIT
        assert result.error.dispatch_state is DispatchState.DISPATCHED
        assert harness.staged_count() == 0  # epilogue reclaimed post-release
        follow = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert follow.status is OperationStatus.OK  # session survives
        plugin.plugin_close()
    finally:
        harness.close()


# --- the UNSUPPORTED narrowing --------------------------------------------------------


@pytest.mark.parametrize(
    "verb", [OperationVerb.STREAM_SUBSCRIBE, OperationVerb.STREAM_UNSUBSCRIBE, OperationVerb.INVOKE]
)
def test_non_capture_expansion_verbs_remain_unsupported(tmp_path: Path, verb: Any) -> None:
    harness = CaptureHarness(tmp_path)
    try:
        plugin = harness.bridge(Adapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(
            OperationRequest("op-x", verb, {}), deadline_ns=10_000_000_000
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.UNSUPPORTED
        assert harness.adapter.calls == 0
        plugin.plugin_close()
    finally:
        harness.close()


# --- plugin_close's sweep ----------------------------------------------------------------


def test_plugin_close_sweeps_still_open_captures(tmp_path: Path) -> None:
    harness = CaptureHarness(tmp_path)
    assert harness.controller is not None
    try:
        harness.controller.open_capture(
            capture_id="cap-open",
            fmt="raw_binary",
            sample_count=None,
            max_bytes=16,
        )
        plugin = harness.bridge(Adapter())
        plugin.plugin_open(object())
        plugin.plugin_close()  # adapter close runs first, then the sweep
        assert harness.staged_count() == 0
        assert harness.forensic_count("cap-open") == 1
    finally:
        harness.close()


def test_bridge_docstring_names_the_version_boundary_and_budget() -> None:
    """Record item 7 (the docstring amendment): the version drift is fixed,
    the async-host sentence names the real boundary (poll multiplexing and
    invoke/dataset scheduling — explicitly NOT capture/stream correctness),
    and the capture-budget disclosure (the step's timeout_ms is the budget,
    clamped by min(now + timeout_ms, body_deadline); busy_timeout under
    contention) lands in the same docstring."""
    import benchweave.host.otdp_bridge as bridge_module

    doc = " ".join((bridge_module.__doc__ or "").split())  # wrap-normalised
    assert "OTDP 0.2.0" in doc and "0.3" not in doc
    assert "poll multiplexing" in doc
    assert "NOT for capture/stream" in doc
    assert "timeout_ms" in doc
    assert "busy_timeout" in doc
    assert "native async host" in doc
