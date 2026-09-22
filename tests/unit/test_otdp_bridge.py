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
from benchweave.content.stream_services import (
    StreamController,
    build_stream_services,
    mint_subscription_id,
)
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
    """B8: the bundle's record_evidence counts on its own kind-scoped
    dimension and stamps its refusals — quota is a resource condition, not
    a protocol lie, so the session survives."""
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


@pytest.mark.parametrize("verb", [OperationVerb.INVOKE])
def test_non_expansion_verbs_remain_unsupported(tmp_path: Path, verb: Any) -> None:
    """The slice-2 pin movement (consciously narrowed): the stream verbs
    left this list when the bridge grew their dispatch (issue #43 slice 2);
    their own arms live in the stream section below. ``invoke`` (and the
    never-supported self_test/get_errors/reset) stay refused."""
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


def test_a_forged_stamp_attribute_keeps_the_poison_posture(tmp_path: Path) -> None:
    """C3 as amended by the refutation (F4): the discriminator requires
    module-token IDENTITY, not attribute presence — an adapter assigning
    its own stamp attribute (the refuter's probe_forge3 shape: a hostile
    or confused adapter is one attribute assignment away from a non-poison
    failure) must keep the poison posture."""
    harness = CaptureHarness(tmp_path)
    try:
        import sqlite3

        class ForgedStamp(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                if request["verb"] != "capture":
                    return await Adapter.execute(self, request, context)
                self.calls += 1
                error = sqlite3.OperationalError("adapter-forged condition")
                error.writer_stamp = object()  # type: ignore[attr-defined]  # a plausible-looking stamp
                raise error

        plugin, result = a_capture_dispatch(harness, ForgedStamp(), a_capture_request())
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


def test_a_saved_stamped_exception_replayed_on_a_write_dispatch_keeps_poison(
    tmp_path: Path,
) -> None:
    """F4's second shape (probe_stamp2): the adapter SAVES a genuine
    writer-stamped exception from a real capture failure, then raises it
    during an unrelated WRITE dispatch to buy a clean non-poison failure.
    The stamp must bind to the capture (and the bundle's to the operation):
    a replay on another dispatch keeps the poison posture."""
    harness = CaptureHarness(tmp_path)
    try:
        saved: dict[str, BaseException] = {}

        class Replay(CaptureAdapter):
            async def execute(self, request: Any, context: Any) -> dict[str, Any]:
                self.calls += 1
                if request["verb"] == "write":
                    raise saved["exc"]  # the genuine saved stamp, replayed
                if request["verb"] == "capture":
                    await self.services.artifact_append("cap-1", b"\x01" * 40, context)
                    try:
                        await self.services.artifact_append(
                            "cap-1", b"\x01" * 40, context
                        )
                    except CaptureQuotaExceeded as exc:
                        saved["exc"] = exc  # keep the REAL stamped instance
                        raise
                    raise AssertionError("unreachable")  # pragma: no cover
                return await Adapter.execute(self, request, context)

        plugin = harness.bridge(Replay())
        plugin.plugin_open(object())
        first = plugin.dispatch(a_capture_request(max_bytes=64), deadline_ns=10_000_000_000)
        assert first.error is not None
        assert first.error.code is ErrorCode.RESOURCE_LIMIT  # genuine stamp, real capture
        follow = plugin.dispatch(
            OperationRequest.write("op-w", parameter="temp", value=1),
            deadline_ns=10_000_000_000,
        )
        assert follow.status is OperationStatus.UNKNOWN  # replay -> poison
        assert follow.error is not None
        assert follow.error.code is ErrorCode.PROTOCOL_ERROR
        after = plugin.dispatch(
            OperationRequest.identify("op-after"), deadline_ns=10_000_000_000
        )
        assert after.error is not None  # the session did not survive
        plugin.plugin_close()
    finally:
        harness.close()


def test_gate_region_lock_contention_is_resource_limit_not_dispatched(tmp_path: Path) -> None:
    """F6: the same writer-originated condition (a stamped OperationalError
    from the writer's BEGIN) classifies RESOURCE_LIMIT at the gate too —
    C2's resource-condition claim is unqualified by site, and C5 named the
    gate and append sites as one family. Nothing was opened (A6's
    no-epilogue rule holds: zero forensic rows, zero staging rows) and the
    adapter is never called."""
    import threading

    harness = CaptureHarness(tmp_path)
    try:
        db_path = str(
            harness.store.connection.execute("PRAGMA database_list").fetchone()[2]
        )
        harness.store.connection.execute("PRAGMA busy_timeout=80")
        holder_lock = threading.Event()
        release = threading.Event()

        def holder() -> None:
            contender = sqlite3.connect(db_path, timeout=5.0)
            contender.execute("BEGIN IMMEDIATE")
            contender.execute(
                "INSERT INTO benches (bench_id, generation, qualification,"
                " configuration_json, licence, updated_at)"
                " VALUES ('gate-held', 1, 'q', '{}', 'l', 't')"
            )
            holder_lock.set()
            release.wait(10)
            contender.rollback()
            contender.close()

        holder_thread = threading.Thread(target=holder)
        holder_thread.start()
        assert holder_lock.wait(10), "holder never took the write lock"
        try:
            plugin, result = a_capture_dispatch(harness, Adapter(), a_capture_request())
            assert result.error is not None
            assert result.error.code is ErrorCode.RESOURCE_LIMIT
            assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
            assert harness.adapter.calls == 0
            assert harness.staged_count() == 0  # nothing was opened
            assert harness.forensic_count() == 0  # A6's no-epilogue rule
        finally:
            release.set()
            holder_thread.join(10)
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_non_quota_open_failure_is_internal_error_not_dispatched(tmp_path: Path) -> None:
    """R1 (review wave 3): A6's INTERNAL_ERROR gate arm — any non-quota,
    non-duplicate-id exception from open_capture returns
    INTERNAL_ERROR not_dispatched with the adapter never called and zero
    forensic rows. Derivation: the post-F6 gate classification table has
    exactly two store-failure classes — a WRITER-ORIGINATED stamped
    OperationalError -> RESOURCE_LIMIT not_dispatched (pinned by
    test_gate_region_lock_contention_is_resource_limit_not_dispatched)
    and every OTHER failure -> INTERNAL_ERROR not_dispatched (this arm).
    The cheapest honest trigger is the envelope-less writer: its
    open_capture raises RuntimeError('capture quota envelope not
    configured'). The refusal CODE is asserted, not the message (the
    message carries the exception)."""
    import pathlib

    from benchweave.content.capture_store import CaptureStagingStore
    from benchweave.state.store import Store

    db_root = pathlib.Path(tmp_path)
    store = Store.open(db_root / "envelope-less.db", check_same_thread=False)
    try:
        harness = CaptureHarness(tmp_path)
        content = ContentStore(store)
        import hashlib as _hashlib

        raw = {
            "id": "dev.local.capture-harness",
            "descriptor_version": "1.0.0",
            "integration": {
                "adapter": {"permissions": ["scoped_transport", "artifact_writer"]}
            },
        }
        blob = _json.dumps(raw, sort_keys=True).encode()
        digest = _hashlib.sha256(blob).hexdigest()
        content.put_document(blob, digest, raw, "otdp-descriptor", "t")
        bundle, controller = build_capture_services(
            descriptor_digest=digest,
            content=content,
            writer=CaptureStagingStore(store),  # NO quota envelope
            clock=lambda: 0.0,
            wall=lambda: "t",
            quota=QuotaLimits(
                max_dataset_bytes=8192, max_evidence_entries=50, max_event_batch=10
            ),
            context_key="envelope-less-session",
        )
        assert controller is not None
        adapter = CaptureAdapter()
        plugin = OTDPBridge(
            adapter,
            descriptor=dict(CAPTURE_DESCRIPTOR),
            services=bundle,
            simulation=SimulationInfo(True, "Synthetic"),
            capture=controller,
        )
        plugin.plugin_open(object())
        result = plugin.dispatch(a_capture_request(), deadline_ns=10_000_000_000)
        assert result.error is not None
        assert result.error.code is ErrorCode.INTERNAL_ERROR
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert adapter.calls == 0
        assert harness.forensic_count() == 0
        plugin.plugin_close()
        harness.close()
    finally:
        store.close()


def test_develop_your_device_compatibility_sentence_covers_capture_and_streaming() -> None:
    """R2 (review wave 3) + the slice-2 flip: docs/develop-your-device.md's
    loader paragraph must not claim capture or streaming need further
    integration now that both lanes are mediated — only profile actions and
    third-party dependencies genuinely remain pending."""
    doc = (
        Path(__file__).resolve().parents[2] / "docs" / "develop-your-device.md"
    ).read_text(encoding="utf-8")
    assert "capture/streaming" not in doc
    assert "single-channel capture" in doc
    assert "streaming subscriptions" in doc
    assert "Profile actions" in doc
    # The stale pending claim (slice 1's wording) must be gone.
    assert "Profile actions, streaming and arbitrary" not in doc


# --- issue #43 slice 2: stream dispatch ------------------------------------------
#
# Derivations (from primary sources): the three-argument subscribe request
# and one-argument unsubscribe are the corpus $defs/operationRequest stream
# branches (required {subscription_id, parameters, min_interval_ms} /
# {subscription_id}; parameters minItems 1 uniqueItems pattern
# ^[a-z][a-z0-9_]*$; min_interval_ms integer minimum 1) and spec §5 lines
# 88-89; the normative floor ("requested intervals cannot be shorter") and
# the max_subscriptions limit are §7 line 152; "Unknown subscriptions ...
# are rejected by the host" and unsubscribe idempotence are §7 line 160;
# event_sink gating is §8 line 216/S15; the echo-correlation refusal is the
# _convert operation-id precedent extended to subscription ids (Decision 4).

STREAM_DESCRIPTOR = {
    "stream_limits": {"min_interval_ms": 100, "max_subscriptions": 2},
    "capture_formats": ["waveform_f64le", "raw_binary"],
    "capture_limits": {"max_samples": 1024, "max_bytes": 8192},
}


class StreamAdapter(Adapter):
    """Echoes the request's subscription id (the correlated success shape)."""

    def __init__(self) -> None:
        super().__init__()
        self.seen_verbs: list[str] = []

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        self.calls += 1
        self.seen_verbs.append(request["verb"])
        if request["verb"] in ("stream_subscribe", "stream_unsubscribe"):
            return {
                "operation_id": request["operation_id"],
                "verb": request["verb"],
                "status": "ok",
                "data": {"subscription_id": request["arguments"]["subscription_id"]},
            }
        return await Adapter.execute(self, request, context)


class StreamHarness:
    """A real store + stream controller + bridge over tmp_path (the
    CaptureHarness sibling; the descriptor admits BOTH lanes so the gates'
    refusal codes are attributable to the stream gates alone)."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        max_subscriptions: int = 2,
        evidence_quota: int = 50,
    ) -> None:
        import pathlib

        self.store = Store.open(pathlib.Path(tmp_path) / "bridge-stream.db")
        self.content = ContentStore(self.store)
        raw_descriptor = {
            "id": "dev.local.stream-harness",
            "descriptor_version": "1.0.0",
            "integration": {
                "mode": "adapter",
                "adapter": {
                    "entry_point": "harness:create_plugin",
                    "api_version": "1.1",
                    "version": "1.0.0",
                    "dependencies": [],
                    "permissions": ["scoped_transport", "artifact_writer", "event_sink"],
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
        controller = build_stream_services(
            descriptor_digest=self.descriptor_digest,
            store=self.store,
            wall=lambda: "2026-09-22T00:00:00Z",
            quota=QuotaLimits(
                max_dataset_bytes=8192,
                max_evidence_entries=evidence_quota,
                max_event_batch=10,
                max_subscriptions=max_subscriptions,
            ),
            context_key="stream-harness-session",
        )
        if controller is None:
            raise AssertionError("stream harness descriptor must admit event_sink")
        self.controller: StreamController = controller
        self.adapter: Any = None

    def bridge(self, adapter: Any, *, descriptor: dict[str, Any] | None = None) -> OTDPBridge:
        self.adapter = adapter
        return OTDPBridge(
            adapter,
            descriptor=dict(descriptor if descriptor is not None else STREAM_DESCRIPTOR),
            services=SimpleNamespace(monotonic=lambda: 0.0),
            simulation=SimulationInfo(True, "Synthetic"),
            stream=self.controller,
        )

    def close(self) -> None:
        self.store.close()

    def stream_rows(self, reference: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = self.store.connection.execute(
            "SELECT content_ref_json FROM evidence WHERE kind = 'event_log'"
        ).fetchall()
        parsed = [_json.loads(row[0]) for row in rows]
        if reference is None:
            return parsed
        return [
            row
            for row in parsed
            if all(row.get(key) == value for key, value in reference.items())
        ]


def a_subscribe_request(**overrides: Any) -> OperationRequest:
    arguments: dict[str, Any] = {
        "subscription_id": mint_subscription_id(),
        "parameters": ["temperature"],
        "min_interval_ms": 100,
    }
    arguments.update(overrides)
    return OperationRequest("op-s", OperationVerb.STREAM_SUBSCRIBE, arguments)


def an_unsubscribe_request(subscription_id: str) -> OperationRequest:
    return OperationRequest(
        "op-u",
        OperationVerb.STREAM_UNSUBSCRIBE,
        {"subscription_id": subscription_id},
    )


def test_stream_subscribe_round_trip_registers_the_subscription(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        plugin = harness.bridge(StreamAdapter())
        plugin.plugin_open(object())
        request = a_subscribe_request()
        result = plugin.dispatch(request, deadline_ns=10_000_000_000)
        assert result.status is OperationStatus.OK
        assert result.data == {"subscription_id": request.arguments["subscription_id"]}
        assert harness.controller.is_live(str(request.arguments["subscription_id"]))
        assert harness.adapter.seen_verbs == ["stream_subscribe"]
        plugin.plugin_close()
    finally:
        harness.close()


def test_stream_subscribe_without_event_sink_is_unsupported_not_dispatched(
    tmp_path: Path,
) -> None:
    """The R8 mirror: no event_sink -> no event services at all, and the
    dispatch is refused at the gate before any adapter call."""
    harness = StreamHarness(tmp_path)
    try:
        plugin = OTDPBridge(
            StreamAdapter(),
            descriptor=dict(STREAM_DESCRIPTOR),
            services=SimpleNamespace(monotonic=lambda: 0.0),
            simulation=SimulationInfo(True, "Synthetic"),
        )
        plugin.plugin_open(object())
        result = plugin.dispatch(a_subscribe_request(), deadline_ns=10_000_000_000)
        assert result.error is not None
        assert result.error.code is ErrorCode.UNSUPPORTED
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert "event_sink" in result.error.message
        assert plugin.dispatch(
            an_unsubscribe_request(mint_subscription_id()), deadline_ns=10_000_000_000
        ).error is not None
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("overrides", "label"),
    [
        ({"subscription_id": ""}, "empty subscription_id"),
        ({"subscription_id": 42}, "non-string subscription_id"),
        ({"parameters": []}, "empty parameters"),
        ({"parameters": ["temperature", "temperature"]}, "duplicate parameters"),
        ({"parameters": ["Bad-Name"]}, "non-pattern parameter"),
        ({"parameters": "temperature"}, "non-list parameters"),
        ({"min_interval_ms": True}, "bool min_interval_ms"),
        ({"min_interval_ms": 2.5}, "float min_interval_ms"),
        ({"min_interval_ms": 0}, "zero min_interval_ms"),
    ],
)
def test_stream_subscribe_typing_is_exact(
    tmp_path: Path, overrides: dict[str, Any], label: str
) -> None:
    harness = StreamHarness(tmp_path)
    try:
        plugin = harness.bridge(StreamAdapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_subscribe_request(**overrides), deadline_ns=10_000_000_000)
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_ARGUMENT, label
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert harness.adapter.calls == 0, label
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("limits", "label"),
    [
        ("not-an-object", "non-dict stream_limits"),
        ({"min_interval_ms": "100", "max_subscriptions": 2}, "string min_interval_ms"),
        ({"min_interval_ms": 100}, "absent max_subscriptions"),
        ({"min_interval_ms": 100, "max_subscriptions": 0}, "zero max_subscriptions"),
        ({"min_interval_ms": -5, "max_subscriptions": 2}, "negative min_interval_ms"),
    ],
)
def test_stream_malformed_descriptor_limits_refuse_cleanly(
    tmp_path: Path, limits: Any, label: str
) -> None:
    """The gate region has no exception frame: a malformed descriptor's
    stream_limits yield a clean INVALID_ARGUMENT, never an escaping
    exception (the capture gate's malformed-descriptor discipline)."""
    harness = StreamHarness(tmp_path)
    adapter = StreamAdapter()
    harness.adapter = adapter
    try:
        plugin = harness.bridge(
            adapter, descriptor=dict(STREAM_DESCRIPTOR, stream_limits=limits)
        )
        plugin.plugin_open(object())
        result = plugin.dispatch(a_subscribe_request(), deadline_ns=10_000_000_000)
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_ARGUMENT, label
        assert adapter.calls == 0, label
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_requested_interval_below_the_descriptor_floor_is_refused(
    tmp_path: Path,
) -> None:
    """Spec §7's normative floor: 'requested intervals cannot be shorter' —
    refusal, never clamping."""
    harness = StreamHarness(tmp_path)
    try:
        plugin = harness.bridge(StreamAdapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(
            a_subscribe_request(min_interval_ms=5), deadline_ns=10_000_000_000
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_ARGUMENT
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert "100" in result.error.message  # the declared floor is named
        assert harness.adapter.calls == 0
        plugin.plugin_close()
    finally:
        harness.close()


def test_the_descriptor_subscription_limit_is_refused(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        plugin = harness.bridge(StreamAdapter())
        plugin.plugin_open(object())
        first = plugin.dispatch(a_subscribe_request(), deadline_ns=10_000_000_000)
        second = plugin.dispatch(a_subscribe_request(), deadline_ns=10_000_000_000)
        third = plugin.dispatch(a_subscribe_request(), deadline_ns=10_000_000_000)
        assert first.status is OperationStatus.OK
        assert second.status is OperationStatus.OK
        assert third.error is not None
        assert third.error.code is ErrorCode.INVALID_ARGUMENT
        assert third.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert harness.adapter.calls == 2
        plugin.plugin_close()
    finally:
        harness.close()


def test_the_host_subscription_ceiling_is_a_resource_limit(tmp_path: Path) -> None:
    """The host QuotaLimits.max_subscriptions ceiling (an author-claimed
    value alone would allow unbounded bridge state growth): RESOURCE_LIMIT,
    not_dispatched, zero adapter calls."""
    harness = StreamHarness(tmp_path, max_subscriptions=1)
    try:
        generous_descriptor = dict(
            STREAM_DESCRIPTOR,
            stream_limits={"min_interval_ms": 100, "max_subscriptions": 99},
        )
        plugin = harness.bridge(StreamAdapter(), descriptor=generous_descriptor)
        plugin.plugin_open(object())
        first = plugin.dispatch(a_subscribe_request(), deadline_ns=10_000_000_000)
        second = plugin.dispatch(a_subscribe_request(), deadline_ns=10_000_000_000)
        assert first.status is OperationStatus.OK
        assert second.error is not None
        assert second.error.code is ErrorCode.RESOURCE_LIMIT
        assert second.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert harness.adapter.calls == 1
        plugin.plugin_close()
    finally:
        harness.close()


def test_an_uncorrelated_subscription_echo_poisons(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        class Lying(StreamAdapter):
            async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
                result = await super().execute(request, context)
                if request["verb"] == "stream_subscribe":
                    result["data"] = {"subscription_id": mint_subscription_id()}
                return result

        plugin = harness.bridge(Lying())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_subscribe_request(), deadline_ns=10_000_000_000)
        assert result.status is OperationStatus.UNKNOWN
        follow = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert follow.error is not None  # poisoned
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_failed_subscribe_releases_the_reservation(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        class Refused(StreamAdapter):
            async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
                self.calls += 1
                if request["verb"] == "stream_subscribe":
                    return {
                        "operation_id": request["operation_id"],
                        "verb": request["verb"],
                        "status": "error",
                        "error": {
                            "code": "DEVICE_REJECTED",
                            "message": "device refused",
                            "dispatch_state": "not_dispatched",
                        },
                    }
                return await Adapter.execute(self, request, context)

        plugin = harness.bridge(Refused())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_subscribe_request(), deadline_ns=10_000_000_000)
        assert result.error is not None
        assert result.error.code is ErrorCode.DEVICE_REJECTED
        assert harness.controller.live_subscription_ids() == []  # released
        follow = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert follow.status is OperationStatus.OK  # session survived
        plugin.plugin_close()
    finally:
        harness.close()


def test_unsubscribe_unknown_is_rejected_by_the_host_before_the_adapter(
    tmp_path: Path,
) -> None:
    """Spec §7: 'Unknown subscriptions owned by another connection/principal
    are rejected by the host' — an id this session never registered never
    reaches the adapter."""
    harness = StreamHarness(tmp_path)
    try:
        plugin = harness.bridge(StreamAdapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(
            an_unsubscribe_request(mint_subscription_id()), deadline_ns=10_000_000_000
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_ARGUMENT
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert harness.adapter.calls == 0
        plugin.plugin_close()
    finally:
        harness.close()


def test_unsubscribe_closes_and_is_idempotent_for_known_terminal_subscriptions(
    tmp_path: Path,
) -> None:
    harness = StreamHarness(tmp_path)
    try:
        plugin = harness.bridge(StreamAdapter())
        plugin.plugin_open(object())
        request = a_subscribe_request()
        subscription_id = str(request.arguments["subscription_id"])
        assert plugin.dispatch(request, deadline_ns=10_000_000_000).status is (
            OperationStatus.OK
        )
        first = plugin.dispatch(
            an_unsubscribe_request(subscription_id), deadline_ns=10_000_000_000
        )
        assert first.status is OperationStatus.OK
        assert first.data == {"subscription_id": subscription_id}
        assert not harness.controller.is_live(subscription_id)
        calls_before = harness.adapter.calls
        second = plugin.dispatch(
            an_unsubscribe_request(subscription_id), deadline_ns=10_000_000_000
        )
        assert second.status is OperationStatus.OK  # idempotent (spec §7)
        assert second.data == {"subscription_id": subscription_id}
        assert harness.adapter.calls == calls_before  # no re-dispatch
        plugin.plugin_close()
    finally:
        harness.close()


def test_plugin_close_sweeps_live_subscriptions_with_ended_markers(
    tmp_path: Path,
) -> None:
    harness = StreamHarness(tmp_path)
    try:
        plugin = harness.bridge(StreamAdapter())
        plugin.plugin_open(object())
        request = a_subscribe_request()
        assert plugin.dispatch(request, deadline_ns=10_000_000_000).status is (
            OperationStatus.OK
        )
        plugin.plugin_close()
        assert harness.controller.live_subscription_ids() == []
        markers = harness.stream_rows({"marker": "host_ended"})
        assert len(markers) == 1
        assert markers[0]["id"] == request.arguments["subscription_id"]
        assert markers[0]["cause"] == "plugin_close"
    finally:
        harness.close()


def test_poison_on_an_unrelated_dispatch_clears_live_subscriptions(
    tmp_path: Path,
) -> None:
    """Decision 4: poison clears the bridge's subscription registry (with
    host-cause ended markers), so a poisoned session cannot leak live
    subscriptions until close."""
    harness = StreamHarness(tmp_path)
    try:
        class Poisonous(StreamAdapter):
            async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
                if request["verb"] == "identify":
                    self.calls += 1
                    raise RuntimeError("adapter exploded")
                return await super().execute(request, context)

        plugin = harness.bridge(Poisonous())
        plugin.plugin_open(object())
        request = a_subscribe_request()
        assert plugin.dispatch(request, deadline_ns=10_000_000_000).status is (
            OperationStatus.OK
        )
        poisoned = plugin.dispatch(
            OperationRequest.identify("op-x"), deadline_ns=10_000_000_000
        )
        assert poisoned.status is OperationStatus.UNKNOWN
        assert harness.controller.live_subscription_ids() == []
        markers = harness.stream_rows({"marker": "host_ended"})
        assert len(markers) == 1
        assert markers[0]["id"] == request.arguments["subscription_id"]
        plugin.plugin_close()
    finally:
        harness.close()


# --- issue #43 slice 2: next_event mediation (R4 + the refusal taxonomy) -----------


def a_reading() -> dict[str, Any]:
    return {
        "parameter": "temperature",
        "value": 21.5,
        "unit": "Cel",
        "observed_at": "2026-09-22T00:00:00Z",
        "age_ms": 0,
        "quality": "valid",
        "source": "device",
    }


def an_event(subscription_id: str, sequence: int, kind: str = "telemetry") -> dict[str, Any]:
    event: dict[str, Any] = {
        "subscription_id": subscription_id,
        "sequence": sequence,
        "kind": kind,
    }
    if kind == "telemetry":
        event["reading"] = a_reading()
    else:
        event["code"] = "DROP"
        event["message"] = "discarded telemetry"
    return event


class StreamingAdapter(StreamAdapter):
    """Answers next_event from a script (one event or None per call)."""

    def __init__(self, script: list[dict[str, Any] | None] | None = None) -> None:
        super().__init__()
        self.script: list[dict[str, Any] | None] = list(script or [])
        self.polls = 0

    async def next_event(self, subscription_id: str, context: Any) -> dict[str, Any] | None:
        self.polls += 1
        if not self.script:
            return None
        return self.script.pop(0)


def a_live_subscription(harness: StreamHarness, plugin: OTDPBridge) -> str:
    request = a_subscribe_request()
    assert plugin.dispatch(request, deadline_ns=10_000_000_000).status is OperationStatus.OK
    return str(request.arguments["subscription_id"])


def correlate(
    script: list[dict[str, Any] | None], subscription_id: str, *indices: int
) -> None:
    """Point the scripted events at the real subscription id (mypy-narrowed)."""
    for index in indices or range(len(script)):
        event = script[index]
        assert event is not None
        event["subscription_id"] = subscription_id


def test_a_quiet_stream_polls_none_without_landing(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(script=[None, None])
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        first = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert first.event is None and first.refusal is None and not first.session_failed
        assert harness.stream_rows() == []  # nothing landed for a quiet poll
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_validated_telemetry_event_lands_with_the_decision_4_row(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(script=[an_event("placeholder", 0)])
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id, 0)
        outcome = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert outcome.event is not None
        assert outcome.event["sequence"] == 0
        assert outcome.host_received_at == "2026-09-22T00:00:00Z"
        rows = harness.stream_rows()
        assert len(rows) == 1
        reference = rows[0]
        # R4's row-shape arm: every landing-contract field present.
        assert reference["subscription_id"] == subscription_id
        assert reference["sequence"] == 0
        assert reference["kind"] == "telemetry"
        assert reference["host_received_at"] == "2026-09-22T00:00:00Z"
        assert reference["sha256"] == hashlib.sha256(
            _json.dumps(outcome.event, sort_keys=True).encode()
        ).hexdigest()
        assert reference["capture_id"] is None
        assert reference["dataset_id"] is None
        plugin.plugin_close()
    finally:
        harness.close()


def test_the_ended_event_is_terminal_for_polling(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(script=[an_event("placeholder", 0, kind="ended")])
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id, 0)
        ended = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert ended.event is not None and ended.event["kind"] == "ended"
        assert not harness.controller.is_live(subscription_id)
        # The refusal taxonomy: known-but-already-ended is a CLEAN refusal
        # (INVALID_ARGUMENT not_dispatched), zero adapter calls.
        polls_before = adapter.polls
        refused = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert refused.event is None
        assert refused.refusal is not None
        assert refused.refusal.code is ErrorCode.INVALID_ARGUMENT
        assert refused.refusal.dispatch_state is DispatchState.NOT_DISPATCHED
        assert adapter.polls == polls_before
        plugin.plugin_close()
    finally:
        harness.close()


def test_an_unknown_subscription_poll_is_refused_before_the_adapter(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter()
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        outcome = plugin.poll_event(mint_subscription_id(), deadline_ns=10_000_000_000)
        assert outcome.refusal is not None
        assert outcome.refusal.code is ErrorCode.INVALID_ARGUMENT
        assert outcome.refusal.dispatch_state is DispatchState.NOT_DISPATCHED
        assert adapter.polls == 0
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("mutation", "label"),
    [
        ({"sequence": 0}, "duplicate sequence"),
        ({"sequence": 0, "kind": "alarm", "code": "X", "message": "m"}, "regression"),
        ({"subscription_id": "other"}, "wrong subscription id"),
        ({"kind": "status"}, "unknown kind"),
        ({"kind": "alarm"}, "telemetry without reading"),
    ],
)
def test_protocol_lies_poison_the_session(
    tmp_path: Path, mutation: dict[str, Any], label: str
) -> None:
    """R4's poison arms: a duplicate or regressing sequence, a
    cross-subscription event, a non-schema kind, a telemetry event without
    a reading — all protocol lies, all poison."""
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(
            script=[an_event("placeholder", 0), an_event("placeholder", 1)]
        )
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id, 0)
        correlate(adapter.script, subscription_id, 1)
        mutated_event = adapter.script[1]
        assert mutated_event is not None
        mutated_event.update(mutation)
        first = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert first.event is not None
        second = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert second.session_failed, label
        assert second.refusal is not None
        assert second.refusal.code is ErrorCode.PROTOCOL_ERROR, label
        follow = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert follow.error is not None  # poisoned
        plugin.plugin_close()
    finally:
        harness.close()


def test_an_event_after_ended_is_refused_by_the_validator(tmp_path: Path) -> None:
    """R4's after-ended arm, enforced at the validator (structural): the
    registry gate above already refuses polling a dead subscription
    cleanly, so the sequential path cannot reach the adapter — this pin
    holds the PROTOCOL_ERROR rule itself for any path that presents one."""
    harness = StreamHarness(tmp_path)
    try:
        plugin = harness.bridge(StreamingAdapter())
        plugin.plugin_open(object())
        with pytest.raises(ValueError, match="ended"):
            plugin._validate_event(
                "sub-x",
                an_event("sub-x", 5),
                last_sequence=1,
                last_kind="ended",
            )
        plugin.plugin_close()
    finally:
        harness.close()


def test_an_alarm_without_code_and_message_poisons(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(script=[an_event("placeholder", 0, kind="gap")])
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id, 0)
        gap_event = adapter.script[0]
        assert gap_event is not None
        del gap_event["code"]
        outcome = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert outcome.session_failed
        plugin.plugin_close()
    finally:
        harness.close()


def test_poison_from_a_poll_clears_live_subscriptions(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(
            script=[an_event("placeholder", 5)]  # first event jumps — lands with annotation
        )
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id, 0)
        assert plugin.poll_event(subscription_id, deadline_ns=10_000_000_000).event is not None
        second_request = a_subscribe_request()
        assert plugin.dispatch(second_request, deadline_ns=10_000_000_000).status is (
            OperationStatus.OK
        )
        other_id = str(second_request.arguments["subscription_id"])
        adapter.script.append(an_event(other_id, 0))  # fine for the other stream
        adapter.script.append(an_event(other_id, 0))  # duplicate -> poison
        assert plugin.poll_event(other_id, deadline_ns=10_000_000_000).event is not None
        poisoned = plugin.poll_event(other_id, deadline_ns=10_000_000_000)
        assert poisoned.session_failed
        # The registry is cleared: no live subscriptions remain.
        assert harness.controller.live_subscription_ids() == []
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_forward_jump_without_gap_is_recorded_by_the_host(tmp_path: Path) -> None:
    """R4's gap-honesty arm, pinned on the HOST mechanism: after a
    simulated drop (0 -> 7, no gap event), the host's annotation row is
    present and the events themselves still land."""
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(
            script=[
                an_event("placeholder", 0),
                an_event("placeholder", 7),
            ]
        )
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id)
        assert plugin.poll_event(subscription_id, deadline_ns=10_000_000_000).event
        assert plugin.poll_event(subscription_id, deadline_ns=10_000_000_000).event
        annotations = harness.stream_rows({"marker": "sequence_jump_without_gap"})
        assert len(annotations) == 1
        assert annotations[0]["id"] == subscription_id
        assert annotations[0]["from_sequence"] == 0
        assert annotations[0]["to_sequence"] == 7
        # Both events landed (the jump is recorded, not refused).
        landed = [row for row in harness.stream_rows() if "marker" not in row]
        assert [row["sequence"] for row in landed] == [0, 7]
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_preceding_gap_event_covers_the_jump_without_annotation(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(
            script=[
                an_event("placeholder", 0),
                an_event("placeholder", 1, kind="gap"),
                an_event("placeholder", 7),
            ]
        )
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id)
        for _ in adapter.script:
            assert plugin.poll_event(subscription_id, deadline_ns=10_000_000_000).event
        assert harness.stream_rows({"marker": "sequence_jump_without_gap"}) == []
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_first_event_past_zero_is_annotated(tmp_path: Path) -> None:
    """Spec §7: sequence starts at zero per subscription — a first event
    already past zero is a delivery gap the host records."""
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(script=[an_event("placeholder", 4)])
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id, 0)
        assert plugin.poll_event(subscription_id, deadline_ns=10_000_000_000).event
        annotations = harness.stream_rows({"marker": "sequence_jump_without_gap"})
        assert len(annotations) == 1
        assert annotations[0]["from_sequence"] is None
        assert annotations[0]["to_sequence"] == 4
        plugin.plugin_close()
    finally:
        harness.close()


def test_quota_exhaustion_at_landing_is_a_clean_refusal_with_teardown(
    tmp_path: Path,
) -> None:
    """Decision 4's refusal taxonomy: quota exhaustion at a landing
    boundary is a clean RESOURCE_LIMIT refusal plus teardown with a
    host-cause ended marker — never session poison."""
    harness = StreamHarness(tmp_path, evidence_quota=1)
    try:
        # The event dimension holds one row: the first event lands, the
        # second refuses at the landing boundary.
        adapter = StreamingAdapter(
            script=[an_event("placeholder", 0), an_event("placeholder", 1)]
        )
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id)
        first = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert first.event is not None
        second = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert second.event is None
        assert second.refusal is not None
        assert second.refusal.code is ErrorCode.RESOURCE_LIMIT
        assert second.refusal.dispatch_state is DispatchState.DISPATCHED
        assert not second.session_failed
        assert not harness.controller.is_live(subscription_id)
        markers = harness.stream_rows({"marker": "host_ended"})
        assert len(markers) == 1
        assert markers[0]["cause"] == "event quota exhausted"
        # Never poison: the session survives.
        follow = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert follow.status is OperationStatus.OK
        plugin.plugin_close()
    finally:
        harness.close()


def test_an_ended_event_refused_at_the_quota_boundary_still_marks_teardown(
    tmp_path: Path,
) -> None:
    """F1 (review wave): the terminal ``ended`` event discarded at the
    event-quota boundary must still leave exactly one durable host_ended
    marker — carrying the discarded event's sequence — after close.
    Decision 4's contract is teardown WITH a host-cause ended marker; a
    registry flip without a durable record is a silent ending."""
    harness = StreamHarness(tmp_path, evidence_quota=1)
    try:
        adapter = StreamingAdapter(
            script=[
                an_event("placeholder", 0),
                an_event("placeholder", 1, kind="ended"),
            ]
        )
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id)
        first = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert first.event is not None
        second = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert second.refusal is not None
        assert second.refusal.code is ErrorCode.RESOURCE_LIMIT
        assert not second.session_failed
        assert not harness.controller.is_live(subscription_id)
        plugin.plugin_close()
        markers = harness.stream_rows({"marker": "host_ended"})
        assert len(markers) == 1
        assert markers[0]["id"] == subscription_id
        assert markers[0]["cause"] == "event quota exhausted"
        assert markers[0]["discarded_sequence"] == 1
    finally:
        harness.close()


def test_a_hanging_poll_poisons_as_a_timeout(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        class Hanging(StreamingAdapter):
            async def next_event(self, subscription_id: str, context: Any) -> Any:
                self.polls += 1
                await asyncio.sleep(1.0)  # blows the 0.3s poll budget
                return an_event(subscription_id, 0)

        plugin = harness.bridge(Hanging())
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        outcome = plugin.poll_event(subscription_id, deadline_ns=300_000_000)
        assert outcome.session_failed
        assert outcome.refusal is not None
        assert outcome.refusal.code is ErrorCode.TIMEOUT
        assert harness.controller.live_subscription_ids() == []
        plugin.plugin_close()
    finally:
        harness.close()


def test_polling_without_a_stream_controller_refuses_unsupported(tmp_path: Path) -> None:
    harness = StreamHarness(tmp_path)
    try:
        plugin = OTDPBridge(
            StreamingAdapter(),
            descriptor=dict(STREAM_DESCRIPTOR),
            services=SimpleNamespace(monotonic=lambda: 0.0),
            simulation=SimulationInfo(True, "Synthetic"),
        )
        plugin.plugin_open(object())
        outcome = plugin.poll_event(mint_subscription_id(), deadline_ns=10_000_000_000)
        assert outcome.refusal is not None
        assert outcome.refusal.code is ErrorCode.UNSUPPORTED
        plugin.plugin_close()
    finally:
        harness.close()

