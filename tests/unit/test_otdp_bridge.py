"""The explicit async-to-sync seam preserves host safety semantics."""

import asyncio
import contextlib
import hashlib
import json as _json
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from benchweave.content.capture_services import build_capture_services
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.store import ContentStore, EvidenceQuotaExceeded
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
    """A real store + writer + bundle + controller + bridge over tmp_path.

    ``busy_timeout_ms`` commissions the store's busy timeout at OPEN (the
    row-B commissioning knob): a capture dispatch brackets itself in a
    clamp window derived from the open default, so a runtime
    ``PRAGMA busy_timeout`` override is no longer the lever it was — the
    contention tests commission here instead. ``clock`` is the capture
    services' injected monotonic (seconds); the default frozen ``0.0``
    keeps the pre-row-B tests' absolute ``deadline_ns`` values valid."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        evidence_quota: int = 50,
        busy_timeout_ms: int | None = None,
        clock: Any = None,
        check_same_thread: bool = False,
    ) -> None:
        import pathlib

        # ``check_same_thread=False`` (the harness default): the bridge
        # legitimately dispatches from a non-opening thread (the
        # ASGI-app posture — usage stays serialised by the bridge lock).
        open_kwargs: dict[str, Any] = {"check_same_thread": check_same_thread}
        if busy_timeout_ms is not None:
            open_kwargs["busy_timeout_ms"] = busy_timeout_ms
        self.store = Store.open(pathlib.Path(tmp_path) / "bridge-capture.db", **open_kwargs)
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
            clock=clock if clock is not None else (lambda: 0.0),
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


def test_capture_g1_gate_names_the_shortfall_and_never_opens_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L2-F2's test-half (fold wave): the G1 request self-consistency gate
    (waveform ``sample_count×8 ≤ max_bytes``, spec §7) refuses with the
    exact shortfall in the message, calls ``open_capture`` ZERO times (the
    arithmetic gate runs before the G3 check-and-reserve), and never
    reaches the adapter. The refusal path itself predates this pin — the
    message string and the zero-open contract were asserted by no test."""
    harness = CaptureHarness(tmp_path)
    controller = harness.controller
    assert controller is not None  # the harness asserts it at construction
    open_calls: list[dict[str, Any]] = []
    original_open = controller.open_capture

    def _spy_open(**kwargs: Any) -> Any:
        open_calls.append(kwargs)
        return original_open(**kwargs)

    monkeypatch.setattr(controller, "open_capture", _spy_open)
    try:
        plugin, result = a_capture_dispatch(
            harness, Adapter(), a_capture_request(sample_count=256, max_bytes=1024)
        )
        assert result.error is not None
        assert result.error.code is ErrorCode.INVALID_ARGUMENT
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert (
            "waveform_f64le sample_count 256 needs 2048 bytes, above the declared "
            "max_bytes 1024"
        ) in result.error.message
        assert open_calls == [], "the G1 arithmetic refusal precedes open_capture"
        assert harness.staged_count() == 0  # no reservation row was ever written
        assert harness.adapter.calls == 0
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


# --- F7: the deadline conversion at the bridge -------------------------------------


def test_capture_huge_deadline_converts_to_a_typed_reject(tmp_path: Path) -> None:
    """F7 (bridge half): a ``deadline_ns`` no float can represent converts
    to a typed INTERNAL_ERROR reject — a raw OverflowError can never
    escape ``dispatch()``. (The contract ceiling keeps schema-valid
    ``timeout_ms`` far from this; the bridge's own guard is the belt.)"""
    harness = CaptureHarness(tmp_path)
    try:
        plugin = harness.bridge(Adapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_capture_request(), deadline_ns=10**400)
        assert result.error is not None
        assert result.error.code is ErrorCode.INTERNAL_ERROR
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert "deadline" in result.error.message
        assert harness.adapter.calls == 0
        plugin.plugin_close()
    finally:
        harness.close()


def test_capture_ceiling_scale_deadline_never_overflows(tmp_path: Path) -> None:
    """F7 (bridge half): the largest schema-valid ``timeout_ms`` builds a
    deadline the bridge converts without OverflowError — the dispatch
    proceeds against the far-future deadline and returns a result,
    whatever its verdict."""
    ceiling = 86_400_000  # the contract ceiling (one day, in ms)
    harness = CaptureHarness(tmp_path)
    try:
        plugin = harness.bridge(Adapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(
            a_capture_request(), deadline_ns=1_000_000_000 + ceiling * 1_000_000
        )
        assert result is not None  # no OverflowError escaped the conversion
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize("bad_id", ["Bad-ID", "1abc", "../escape", "cap/1", ""])
def test_capture_id_shape_is_validated(tmp_path: Path, bad_id: Any) -> None:
    """The capture id shape is the bridge's ``_CAPTURE_ID_PATTERN``:
    ``[a-z][a-z0-9_.:-]*`` — interface.schema.json's ``^[a-z][a-z0-9_.-]*$``
    widened with ``:`` so the host-minted ``cap:{run_id}:{step_id}`` ids
    pass (the issue #176 increment-2 minting precedent; the colon is the
    only separator that mint uses). Every refusal case below — uppercase,
    digit-start, traversal, slash, empty — still refuses under the widened
    pattern. The writer's PRIMARY KEY enforces session-uniqueness."""
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
    the epilogue reclaims once the holder releases. (Row B: the busy
    timeout is commissioned at open — the dispatch clamp derives from
    the open default, so the old runtime-pragma override moved here.)"""
    harness = CaptureHarness(tmp_path, busy_timeout_ms=80)
    try:

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

    harness = CaptureHarness(tmp_path, busy_timeout_ms=80)
    try:
        db_path = str(
            harness.store.connection.execute("PRAGMA database_list").fetchone()[2]
        )
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


def test_a_bare_unstamped_evidence_quota_raise_from_a_poll_keeps_poison(
    tmp_path: Path,
) -> None:
    """F2 (review wave): the C3 mirror on the poll path — the landing's
    quota refusal must prove LANDING origin (token identity + subscription
    binding), never class identity alone. A bare EvidenceQuotaExceeded
    raised by adapter code from next_event keeps the poison posture: no
    clean RESOURCE_LIMIT, no false 'event quota exhausted' marker (the
    poison sweep's markers are correct and stay)."""
    harness = StreamHarness(tmp_path)
    try:
        class Bare(StreamingAdapter):
            async def next_event(self, subscription_id: str, context: Any) -> Any:
                self.polls += 1
                raise EvidenceQuotaExceeded("adapter code can raise the class too")

        plugin = harness.bridge(Bare())
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        outcome = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert outcome.session_failed
        assert outcome.refusal is not None
        assert outcome.refusal.code is ErrorCode.PROTOCOL_ERROR
        # No false quota marker — the only teardown markers are the poison
        # sweep's, with the poison cause.
        assert harness.stream_rows({"cause": "event quota exhausted"}) == []
        markers = harness.stream_rows({"marker": "host_ended"})
        assert all(marker["cause"] == "session poisoned" for marker in markers)
        follow = plugin.dispatch(
            OperationRequest.identify("op-next"), deadline_ns=10_000_000_000
        )
        assert follow.error is not None  # poisoned
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("kind", "field", "value", "label"),
    [
        ("gap", "reading", "garbage", "garbage reading on a gap event"),
        ("ended", "reading", 7, "non-object reading on an ended event"),
        ("telemetry", "code", 5, "non-string code on a telemetry event"),
        ("telemetry", "message", "", "empty message on a telemetry event"),
    ],
)
def test_conditional_key_values_are_validated_regardless_of_kind(
    tmp_path: Path, kind: str, field: str, value: Any, label: str
) -> None:
    """G1 (Forge wave): $defs/event declares ``reading`` ($defs/reading)
    and ``code``/``message`` (minLength 1) UNCONDITIONALLY — the if/then
    blocks govern PRESENCE only — so any present conditional key with an
    invalid value is corpus-illegal whatever the kind, and must poison."""
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(script=[an_event("placeholder", 0, kind=kind)])
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id)
        event = adapter.script[0]
        assert event is not None
        event[field] = value
        outcome = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert outcome.session_failed, label
        assert outcome.refusal is not None
        assert outcome.refusal.code is ErrorCode.PROTOCOL_ERROR, label
        # No event row landed (the poison sweep's teardown markers may
        # exist; the illegal event never became evidence).
        landed = [row for row in harness.stream_rows() if "marker" not in row]
        assert landed == []
        plugin.plugin_close()
    finally:
        harness.close()


def test_a_valid_reading_on_a_gap_event_is_corpus_legal_and_lands(
    tmp_path: Path,
) -> None:
    """G1's positive arm: a schema-VALID reading carried on a non-telemetry
    event is corpus-legal (presence is what the if/then blocks govern) —
    the unconditional value check must not over-tighten into a refusal."""
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(script=[an_event("placeholder", 0, kind="gap")])
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id)
        gap_event = adapter.script[0]
        assert gap_event is not None
        gap_event["reading"] = a_reading()
        outcome = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert outcome.event is not None
        rows = [row for row in harness.stream_rows() if "marker" not in row]
        assert len(rows) == 1 and rows[0]["kind"] == "gap"
        plugin.plugin_close()
    finally:
        harness.close()


def test_an_unserializable_x_extension_value_refuses_as_an_invalid_event(
    tmp_path: Path,
) -> None:
    """G3 (Forge wave): the corpus admits any x-extension VALUE
    (patternProperties {}), so a circular one is legal content the host
    cannot STORE — the refusal must name that (the honest invalid-event
    class), not the generic 'Invalid, failed or late adapter event'
    protocol-lie wording; nothing lands and the posture stays poison."""
    harness = StreamHarness(tmp_path)
    try:
        adapter = StreamingAdapter(script=[an_event("placeholder", 0)])
        plugin = harness.bridge(adapter)
        plugin.plugin_open(object())
        subscription_id = a_live_subscription(harness, plugin)
        correlate(adapter.script, subscription_id)
        loop: dict[str, Any] = {}
        loop["self"] = loop
        loop_event = adapter.script[0]
        assert loop_event is not None
        loop_event["x-vendor-loop"] = loop
        outcome = plugin.poll_event(subscription_id, deadline_ns=10_000_000_000)
        assert outcome.session_failed
        assert outcome.refusal is not None
        assert outcome.refusal.code is ErrorCode.PROTOCOL_ERROR
        assert "serializ" in outcome.refusal.message
        assert "Invalid, failed or late" not in outcome.refusal.message
        landed = [row for row in harness.stream_rows() if "marker" not in row]
        assert landed == []
        plugin.plugin_close()
    finally:
        harness.close()



# --- issue #176 row B: the busy-timeout clamp, the epilogue floor ---------------------


class _MidCaptureHolder:
    """A separate-connection write-lock holder: acquires BEGIN IMMEDIATE
    once armed, holds a fixed wall duration, then rolls back — independent
    of the dispatch thread, so the lock is still held ACROSS the bridge's
    abort epilogue (the discrimination the in-adapter holder shape cannot
    make)."""

    def __init__(self, db_path: str, hold_s: float) -> None:
        import time as _time

        self._time = _time
        self._db_path = db_path
        self._hold_s = hold_s
        self._acquired: Any = None
        self._release: Any = None
        self.acquired_at: float = 0.0
        self.released_at: float = 0.0
        self._thread: Any = None

    def arm(self) -> float:
        import threading

        self._acquired = threading.Event()
        self._release = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._acquired.wait(10), "holder never took the write lock"
        return self.acquired_at

    def _run(self) -> None:
        contender = sqlite3.connect(self._db_path, timeout=5.0)
        try:
            contender.execute("BEGIN IMMEDIATE")
            self.acquired_at = self._time.monotonic()
            self._acquired.set()
            self._release.wait(self._hold_s)
            contender.rollback()
        finally:
            self.released_at = self._time.monotonic()
            contender.close()

    def release(self) -> float:
        self._release.set()
        self._thread.join(10)
        return self.released_at


class _GateWaitAdapter(Adapter):
    """Append #1 lands; the adapter then waits for the armed holder before
    append #2 contends — deterministic mid-capture ordering. ``idle_s``
    is pre-BEGIN work inside the bracket (the entry-time clamp never sees
    it) — the lane-1 F1 repro lever."""

    def __init__(self, first_landed: Any, proceed: Any, idle_s: float = 0.0) -> None:
        super().__init__()
        self.first_landed = first_landed
        self.proceed = proceed
        self.idle_s = idle_s
        self.append_started_at: float | None = None
        self.append_failed_at: float | None = None

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        self.calls += 1
        if request["verb"] != "capture":
            return await Adapter.execute(self, request, context)
        capture_id = request["arguments"]["capture_id"]
        await self.services.artifact_append(capture_id, b"\x01" * 8, context)
        self.first_landed.set()
        assert self.proceed.wait(10), "holder never armed"
        import time

        if self.idle_s:
            await asyncio.sleep(self.idle_s)
        self.append_started_at = time.monotonic()
        try:
            await self.services.artifact_append(capture_id, b"\x01" * 8, context)
        except sqlite3.OperationalError:
            self.append_failed_at = time.monotonic()
            raise
        raise AssertionError("append #2 should have contended and failed")


def _row_b_dispatch(
    harness: CaptureHarness,
    adapter: _GateWaitAdapter,
    *,
    deadline_ms: int,
) -> tuple[Any, Any, dict[str, Any]]:
    """Dispatch one capture on a worker thread: append #1 lands, the test
    arms the holder, the adapter proceeds into the contended append #2."""
    import threading
    import time

    plugin = harness.bridge(adapter)
    plugin.plugin_open(object())
    outcome: dict[str, Any] = {}

    def run() -> None:
        outcome["start"] = time.monotonic()
        outcome["result"] = plugin.dispatch(
            a_capture_request(),
            deadline_ns=time.monotonic_ns() + deadline_ms * 1_000_000,
        )
        outcome["end"] = time.monotonic()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    assert adapter.first_landed.wait(10), "append #1 never landed"
    return plugin, worker, outcome


def test_row_b_clamp_bounds_the_mid_capture_wait_by_the_step_deadline(
    tmp_path: Path,
) -> None:
    """B-R1 (ordering 1, remaining < default): the contended append's
    busy-wait is bounded by the step deadline (the clamp), not the store
    default — reverting the clamp, the same dispatch waits the whole hold
    out under the open default and SUCCEEDS past its deadline. The abort
    epilogue runs under its own floor and reclaims the staging row once
    the holder releases; reverting the floor, the epilogue inherits the
    clamp window, fails inside it, and the row leaks past the return."""
    harness = CaptureHarness(tmp_path, clock=time.monotonic)
    try:
        # The hold (1.0 s) must outlast the clamp (200 ms) PLUS the clamp
        # window the epilogue would inherit WITHOUT its own floor (another
        # 200 ms), with margin — that is the shape whose reclamation the
        # floor owns; a shorter hold leaves the no-floor epilogue's fate
        # to scheduler luck.
        holder = _MidCaptureHolder(harness.db_path, hold_s=1.0)
        first_landed = threading.Event()
        proceed = threading.Event()
        adapter = _GateWaitAdapter(first_landed, proceed)
        plugin, worker, outcome = _row_b_dispatch(
            harness, adapter, deadline_ms=200
        )
        holder.arm()
        proceed.set()
        worker.join(30)
        assert not worker.is_alive(), "dispatch never returned"
        result = outcome["result"]

        # Classification unchanged: the clamped-out BEGIN is the same
        # writer-originated resource condition (RESOURCE_LIMIT, and the
        # dispatch state stays DISPATCHED — the session survives).
        assert result.error is not None
        assert result.error.code is ErrorCode.RESOURCE_LIMIT
        assert result.error.dispatch_state is DispatchState.DISPATCHED

        # The clamp bounded the contended wait by the deadline: the busy-wait
        # (measured from the append's own entry, excluding the adapter's
        # event-wait wake-up) lasted ~the 200 ms clamp, well inside the 1 s
        # hold. Under the unclamped open default (5000 ms) the append waits
        # the hold out and the capture SUCCEEDS past its deadline.
        assert adapter.append_failed_at is not None
        assert adapter.append_started_at is not None
        append_wait_ms = (adapter.append_failed_at - adapter.append_started_at) * 1000
        assert 120 <= append_wait_ms <= 450, append_wait_ms

        # The epilogue floor let the reclaim wait out the remaining hold:
        # the row is gone and the forensic marker is durable at return.
        assert harness.staged_count() == 0
        assert harness.forensic_count("cap-1") == 1

        # The wall-stretch class: clamp + floor + jitter, not the 2x anchor.
        total_ms = (outcome["end"] - outcome["start"]) * 1000
        assert total_ms <= 200 + 5000 + 300, total_ms

        # B-R2: the pragma reads the open default again after the clamped,
        # failed dispatch.
        live = int(
            harness.store.connection.execute("PRAGMA busy_timeout").fetchone()[0]
        )
        assert live == harness.store.open_busy_timeout_ms == 5000

        follow = plugin.dispatch(
            OperationRequest.identify("op-follow"),
            deadline_ns=time.monotonic_ns() + 2_000_000_000,
        )
        assert follow.status is OperationStatus.OK  # session survives
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("default_ms", "deadline_ms", "hold_s", "clamp_wins"),
    [
        pytest.param(5000, 200, 0.45, True, id="deadline-bound-clamp-wins"),
        pytest.param(300, 3000, 0.9, False, id="default-bound-clamp-capped"),
    ],
)
def test_row_b_both_clamp_orderings_classify_one_pair(
    tmp_path: Path, default_ms: int, deadline_ms: int, hold_s: float, clamp_wins: bool
) -> None:
    """F3's pre-committed two-clamp table: when the dispatch-deadline
    clamp and the asyncio timeout are both live, the dispatch deadline is
    authoritative for ``remaining_deadline_ms`` (it already carries
    ``min(now + timeout_ms, body_deadline)``), and the failure class does
    not depend on WHICH bound capped the busy-wait: ONE
    (error_code, dispatch_state) pair under both orderings. The
    ``default-bound`` arm additionally proves the cap: the append fails at
    the commissioned default (~300 ms), far inside the 3 s deadline."""
    harness = CaptureHarness(tmp_path, busy_timeout_ms=default_ms, clock=time.monotonic)
    try:
        holder = _MidCaptureHolder(harness.db_path, hold_s=hold_s)
        first_landed = threading.Event()
        proceed = threading.Event()
        adapter = _GateWaitAdapter(first_landed, proceed)
        plugin, worker, outcome = _row_b_dispatch(
            harness, adapter, deadline_ms=deadline_ms
        )
        holder.arm()
        proceed.set()
        worker.join(30)
        result = outcome["result"]

        assert result.error is not None
        assert result.error.code is ErrorCode.RESOURCE_LIMIT
        assert result.error.dispatch_state is DispatchState.DISPATCHED

        assert adapter.append_failed_at is not None
        assert adapter.append_started_at is not None
        append_wait_ms = (adapter.append_failed_at - adapter.append_started_at) * 1000
        if clamp_wins:
            # The deadline bound: the append failed ~at the deadline.
            assert 120 <= append_wait_ms <= 450, append_wait_ms
        else:
            # The default bound: the append failed ~at the default, far
            # inside the 3000 ms deadline — the cap that made it win.
            assert 200 <= append_wait_ms <= 500, append_wait_ms
            assert append_wait_ms < deadline_ms
        plugin.plugin_close()
    finally:
        harness.close()


def test_row_b_clamp_is_entry_time_remaining_disclosed_overshoot(
    tmp_path: Path,
) -> None:
    """Lane-1 F1's disclosed bound, pinned (final fold): the clamp is
    computed at bracket ENTRY, so pre-BEGIN time inside the bracket —
    here the adapter's 1 s idle before the contended append — consumes
    budget the clamp never sees, and the contended busy-wait can END
    past the step budget by that consumed amount. The busy-wait ITSELF
    stays at the entry-time remaining (shortened only relative to the
    open default); the overshoot is the disclosed residual, per-BEGIN
    re-derivation deferred (the record's row 26). The old
    'a busy-wait can never run past the step budget' claim is dead."""
    harness = CaptureHarness(tmp_path, clock=time.monotonic)
    try:
        holder = _MidCaptureHolder(harness.db_path, hold_s=4.0)
        first_landed = threading.Event()
        proceed = threading.Event()
        adapter = _GateWaitAdapter(first_landed, proceed, idle_s=1.0)
        plugin, worker, outcome = _row_b_dispatch(
            harness, adapter, deadline_ms=1500
        )
        holder.arm()
        proceed.set()
        worker.join(30)
        assert not worker.is_alive(), "dispatch never returned"
        result = outcome["result"]
        assert result.error is not None
        assert result.error.code is ErrorCode.RESOURCE_LIMIT
        assert result.error.dispatch_state is DispatchState.DISPATCHED

        dispatch_start = outcome["start"]
        assert adapter.append_started_at is not None
        assert adapter.append_failed_at is not None
        pre_begin_ms = (adapter.append_started_at - dispatch_start) * 1000
        fail_delta_ms = (adapter.append_failed_at - dispatch_start) * 1000
        busy_wait_ms = (
            adapter.append_failed_at - adapter.append_started_at
        ) * 1000
        # The pre-BEGIN idle really consumed bracket budget.
        assert 900 <= pre_begin_ms <= 1400, pre_begin_ms
        # The disclosed overshoot EXISTS: the busy-wait ends past the
        # step budget — the corrected claim, not the dead one.
        assert fail_delta_ms > 1500, fail_delta_ms
        # ... by (approximately) the consumed amount, not unboundedly.
        assert fail_delta_ms <= 1500 + pre_begin_ms + 300, fail_delta_ms
        # The busy-wait itself stayed at the entry-time remaining.
        assert 1300 <= busy_wait_ms <= 1700, busy_wait_ms
        plugin.plugin_close()
    finally:
        harness.close()


def test_row_b_sweep_and_startup_reclaim_never_enter_a_window(tmp_path: Path) -> None:
    """B-R3: only the capture DISPATCH brackets a busy-timeout window.
    plugin_close's sweep_open and the startup reclaim_orphans run at the
    open default, unclamped — the recording store sees exactly the
    dispatch windows and nothing from the sweep/reclaim paths."""
    harness = CaptureHarness(tmp_path)
    assert harness.controller is not None
    windows: list[int] = []
    original_window = harness.store.busy_timeout_window

    @contextlib.contextmanager
    def recording_window(ms: int) -> Any:
        windows.append(ms)
        with original_window(ms):
            yield

    harness.store.busy_timeout_window = recording_window  # type: ignore[method-assign]
    try:
        # A successful clamped capture: exactly ONE window (the clamp).
        plugin, result = a_capture_dispatch(
            harness, CaptureAdapter(), a_capture_request()
        )
        assert result.status is OperationStatus.OK
        assert windows == [5000]  # the frozen harness clock -> remaining huge -> the default cap
        assert (
            int(harness.store.connection.execute("PRAGMA busy_timeout").fetchone()[0])
            == 5000
        )
        plugin.plugin_close()
        assert windows == [5000]  # the close sweep added nothing
        # The startup reclaim path is equally window-free.
        harness.controller.open_capture(
            capture_id="cap-orphan",
            fmt="raw_binary",
            sample_count=None,
            max_bytes=16,
        )
        harness.writer.reclaim_orphans("2026-09-22T00:00:00Z")
        assert windows == [5000]  # still — reclaim_orphans is unclamped
        assert harness.staged_count() == 0
    finally:
        harness.close()


def test_row_b_gate_refusal_clamps_once_and_restores(tmp_path: Path) -> None:
    """B-R2's gate arm: the G3 open_capture BEGIN runs INSIDE the clamp
    window (bracketed with everything else), and a writer-originated
    refusal there still restores the open default — one window entered,
    none leaked."""
    import threading

    harness = CaptureHarness(tmp_path, busy_timeout_ms=80)
    try:
        db_path = str(
            harness.store.connection.execute("PRAGMA database_list").fetchone()[2]
        )
        windows: list[int] = []
        original_window = harness.store.busy_timeout_window

        @contextlib.contextmanager
        def recording_window(ms: int) -> Any:
            windows.append(ms)
            with original_window(ms):
                yield

        harness.store.busy_timeout_window = recording_window  # type: ignore[method-assign]
        holder_lock = threading.Event()
        release = threading.Event()

        def holder() -> None:
            contender = sqlite3.connect(db_path, timeout=5.0)
            contender.execute("BEGIN IMMEDIATE")
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
            # The gate ran inside the clamp window (once), and the
            # pragma is back at the commissioned default: no leak.
            assert windows == [80]
            assert (
                int(
                    harness.store.connection.execute(
                        "PRAGMA busy_timeout"
                    ).fetchone()[0]
                )
                == 80
            )
        finally:
            release.set()
            holder_thread.join(10)
        plugin.plugin_close()
    finally:
        harness.close()


def test_row_b_clamp_reads_the_injected_clock_no_hidden_second_clock(
    tmp_path: Path,
) -> None:
    """F6's clock-domain pin: the clamp's remaining-deadline arithmetic
    reads the capture services' INJECTED monotonic — there is no hidden
    second clock. With the services clock diverging −60 s from the
    deadline's timebase, the injected-clock remaining is huge and the
    open default caps the clamp; a hidden real clock would compute
    remaining ≈ 150 ms and clamp to that. The +60 s arm mirrors it: the
    injected clock leaves 150 ms, and a hidden real clock would have
    capped at the default instead."""
    harness = CaptureHarness(
        tmp_path, clock=lambda: time.monotonic() - 60.0
    )
    try:
        windows: list[int] = []
        original_window = harness.store.busy_timeout_window

        @contextlib.contextmanager
        def recording_window(ms: int) -> Any:
            windows.append(ms)
            with original_window(ms):
                yield

        harness.store.busy_timeout_window = recording_window  # type: ignore[method-assign]
        plugin = harness.bridge(CaptureAdapter())
        plugin.plugin_open(object())
        plugin.dispatch(
            a_capture_request(),
            deadline_ns=time.monotonic_ns() + 150_000_000,
        )
        # injected remaining = 60.15 s -> the default cap, not 150 ms.
        assert windows == [5000]
        plugin.plugin_close()
    finally:
        harness.close()


def test_row_b_clamp_negative_injected_remaining_clamps_to_zero(
    tmp_path: Path,
) -> None:
    """F6's second arm: a services clock +60 s ahead leaves only 150 ms
    of injected-clock remaining for a deadline 60.15 s out — the clamp is
    150 ms, not the default cap a hidden real clock would produce."""
    harness = CaptureHarness(
        tmp_path, clock=lambda: time.monotonic() + 60.0
    )
    try:
        windows: list[int] = []
        original_window = harness.store.busy_timeout_window

        @contextlib.contextmanager
        def recording_window(ms: int) -> Any:
            windows.append(ms)
            with original_window(ms):
                yield

        harness.store.busy_timeout_window = recording_window  # type: ignore[method-assign]
        plugin = harness.bridge(CaptureAdapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(
            a_capture_request(),
            deadline_ns=int((time.monotonic() + 60.15) * 1_000_000_000),
        )
        assert result.status is OperationStatus.OK
        # ~150 ms of injected-clock remaining (± scheduler jitter between
        # the deadline stamp and the clamp entry) — decisively not the
        # default cap a hidden real clock would produce.
        assert len(windows) == 1 and 100 <= windows[0] <= 150, windows
        plugin.plugin_close()
    finally:
        harness.close()


# --- issue #146 slice 2: invoke dispatch (§2.3) ---------------------------------
#
# Derivations (from the corpus, not the plan's restatement): the invoke
# request arguments are the runtime schema's closed branch {action_id,
# input}; the success data is the closed {action_id, result}; the dataset
# cross-check is design §2.3 (the strict posture — §3 slice 2: a
# dataset-shaped result that was never published through dataset_publish
# refuses from day one); the gates' bounds-before-device posture and the
# A7 dispatch-state table are the capture gates' own discipline.

_INVOKE_REPO = Path(__file__).resolve().parents[2]


def _active_otdp_bytes(name: str) -> bytes:
    from benchweave.standards.manifest import load_manifest

    active = next(
        entry.version for entry in load_manifest(_INVOKE_REPO).standards if entry.id == "otdp"
    )
    document = _INVOKE_REPO / "standards" / "otdp" / active / name
    return document.read_bytes()


def _active_measurement_bytes() -> bytes:
    return _active_otdp_bytes("otdp-measurement.schema.json")


def _invoke_synthetic_contracts() -> Any:
    """A synthetic pinned pair: a catalog-schema-valid catalog with three
    actions (invented fixture names — the corpus-faithful dataset-ref
    fetch, a plain configure action, and a permissive-output action for
    isolating the publication cross-check channel) plus the REAL corpus
    measurement schema (the dataset required keys are its own)."""
    import hashlib as _hashlib

    from benchweave.registry.otdp_contracts import resolve_otdp_contracts

    measurement = _json.loads(_active_measurement_bytes())
    # The version consts derive from the corpus catalog bytes (the
    # loader-test precedent) — the schema pins both to the active corpus
    # version, so a hardcoded literal would be a version-bearing surface.
    corpus_catalog = _json.loads(_active_otdp_bytes("device-profile-catalog.json"))
    catalog = {
        "catalog_version": corpus_catalog["catalog_version"],
        "otdp_version": corpus_catalog["otdp_version"],
        "profiles": [
            {
                "id": "demo.profile/1.0.0",
                "title": "Demo profile",
                "channel_roles": ["source"],
                "required_actions": [
                    "demo.act/1.0.0",
                    "demo.fetch/1.0.0",
                    "demo.raw/1.0.0",
                ],
                "optional_actions": [],
            }
        ],
        "actions": {
            "demo.act/1.0.0": {
                "description": "Configure the demo output.",
                "input_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "required": ["x"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
                "side_effect": "state_change",
                "lifecycle": "direct",
            },
            "demo.fetch/1.0.0": {
                "description": "Fetch a dataset (corpus-faithful shape).",
                "input_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "integer", "minimum": 1}},
                    "required": ["count"],
                },
                "output_schema": {"$ref": measurement["$id"] + "#/$defs/dataset"},
                "side_effect": "none",
                "lifecycle": "acquisition",
            },
            "demo.raw/1.0.0": {
                "description": "Permissive output (the isolation arm).",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "side_effect": "none",
                "lifecycle": "direct",
            },
        },
    }
    inventory = {
        "contracts/catalog.json": _json.dumps(catalog).encode(),
        "contracts/measurement.json": _active_measurement_bytes(),
    }
    entries = [
        {
            "id": "urn:demo:catalog",
            "path": path,
            "sha256": _hashlib.sha256(data).hexdigest(),
        }
        for path, data in sorted(inventory.items())
    ]
    resolved = resolve_otdp_contracts(entries, inventory=inventory)
    assert resolved is not None
    return resolved


INVOKE_DESCRIPTOR = {
    "capabilities": ["identify", "invoke"],
    "actions": {
        "demo.act/1.0.0": {
            "binding": {"kind": "adapter", "key": "act"},
            "input_constraints": {
                "type": "object",
                "properties": {"x": {"minimum": 10}},
            },
            "timeout_ms": 500,
            "side_effect": "state_change",
            "cancellable": True,
            "retry": "never",
        },
        "demo.fetch/1.0.0": {
            "binding": {"kind": "adapter", "key": "fetch"},
            "input_constraints": {"type": "object"},
            "timeout_ms": 500,
            "side_effect": "none",
            "cancellable": True,
            "retry": "never",
        },
        "demo.raw/1.0.0": {
            "binding": {"kind": "adapter", "key": "raw"},
            "input_constraints": {"type": "object"},
            "timeout_ms": 500,
            "side_effect": "none",
            "cancellable": True,
            "retry": "never",
        },
        "demo.local-only/1.0.0": {
            "binding": {"kind": "adapter", "key": "local"},
            "input_constraints": {"type": "object"},
            "timeout_ms": 500,
            "side_effect": "none",
            "cancellable": True,
            "retry": "never",
        },
    },
}

_DATASET_SHAPED_RESULT: dict[str, Any] = {
    "dataset_id": "ds:op-i",
    "kind": "scalar_set",
    "configuration_id": None,
    "acquisition_id": None,
    "started_at": "2026-09-25T00:00:00Z",
    "clock": {"kind": "host_monotonic"},
    "axes": [],
    "variables": [],
    "trigger": "manual",
    "status": "valid",
    "context": {},
}


class InvokeHarness:
    """A real store + writer + scoped bundle + resolved dataset controller
    over tmp_path — the §2.3 substrate. The descriptor declares the invoke
    capability WITHOUT artifact_writer, so the composing bundle is the
    five-member scoped shape and no capture controller exists (invoke is
    not capture's lane)."""

    def __init__(self, tmp_path: Path, *, evidence_quota: int = 50) -> None:
        self.store = Store.open(tmp_path / "bridge-invoke.db")
        self.content = ContentStore(self.store)
        raw = {
            "id": "dev.local.invoke-harness",
            "descriptor_version": "1.0.0",
            "integration": {
                "mode": "adapter",
                "adapter": {
                    "entry_point": "harness:create_plugin",
                    "api_version": "1.1",
                    "version": "1.0.0",
                    "dependencies": [],
                    "permissions": ["scoped_transport"],
                },
            },
        }
        blob = _json.dumps(raw, sort_keys=True).encode()
        digest = hashlib.sha256(blob).hexdigest()
        self.content.put_document(blob, digest, raw, "otdp-descriptor", "2026-09-25T00:00:00Z")
        self.writer = CaptureStagingStore(
            self.store, max_capture_bytes=8192, max_dataset_bytes=8192
        )
        self.bundle, no_capture = build_capture_services(
            descriptor_digest=digest,
            content=self.content,
            writer=self.writer,
            clock=lambda: 0.0,
            wall=lambda: "2026-09-25T00:00:00Z",
            quota=QuotaLimits(
                max_dataset_bytes=8192,
                max_evidence_entries=evidence_quota,
                max_event_batch=10,
            ),
            context_key="invoke-harness-session",
        )
        assert no_capture is None
        from benchweave.content.dataset_services import build_dataset_controller

        self.controller = build_dataset_controller(
            _invoke_synthetic_contracts(), writer=self.writer
        )
        self.adapter: Any = None

    def bridge(self, adapter: Any, *, dataset: Any = "default") -> OTDPBridge:
        self.adapter = adapter
        return OTDPBridge(
            adapter,
            descriptor=dict(INVOKE_DESCRIPTOR),
            services=self.bundle,
            simulation=SimulationInfo(True, "Synthetic"),
            dataset=self.controller if dataset == "default" else dataset,
        )

    def close(self) -> None:
        self.store.close()


class InvokeAdapter(Adapter):
    """Returns a fixed invoke result, optionally recording evidence first
    (the R17 evidence-quota lane)."""

    def __init__(
        self, result: Any = None, *, evidence_calls: int = 0, action_echo: str | None = None
    ) -> None:
        super().__init__()
        self.result = result if result is not None else {"ok": True}
        self.evidence_calls = evidence_calls
        self.action_echo = action_echo
        self.services: Any = None

    async def open(self, descriptor: dict[str, Any], services: Any, context: Any) -> None:
        self.services = services
        await super().open(descriptor, services, context)

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        self.calls += 1
        self.context = context
        if request["verb"] != "invoke":
            return await Adapter.execute(self, request, context)
        for _ in range(self.evidence_calls):
            await self.services.record_evidence({"lane": "invoke"}, context)
        return {
            "operation_id": request["operation_id"],
            "verb": "invoke",
            "status": "ok",
            "data": {
                "action_id": self.action_echo or request["arguments"]["action_id"],
                "result": self.result,
            },
        }


def a_invoke_request(**overrides: Any) -> OperationRequest:
    arguments: dict[str, Any] = {"action_id": "demo.act/1.0.0", "input": {"x": 10}}
    arguments.update(overrides)
    return OperationRequest("op-i", OperationVerb.INVOKE, arguments)


def test_i1_invoke_without_a_controller_refuses_unsupported(tmp_path: Path) -> None:
    """R1/I1: no resolved contract surface, no invoke — a typed UNSUPPORTED
    not_dispatched with zero adapter calls."""
    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(InvokeAdapter(), dataset=None)
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert result.error is not None
        assert result.error.code is ErrorCode.UNSUPPORTED
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED
        assert "invoke requires" in result.error.message
        assert harness.adapter.calls == 0
        plugin.plugin_close()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("overrides", "code", "fragment", "label"),
    [
        (
            {"action_id": "demo.nowhere/1.0.0"},
            ErrorCode.INVALID_ARGUMENT,
            "not declared by the descriptor",
            "I2 undeclared action",
        ),
        (
            {"action_id": "demo.local-only/1.0.0"},
            ErrorCode.INVALID_ARGUMENT,
            "does not resolve in the pinned profile catalog",
            "I3 catalog-unknown action (M14)",
        ),
        (
            {"action_id": 123},
            ErrorCode.INVALID_ARGUMENT,
            "action_id must be a non-empty string",
            "I2 non-string action_id",
        ),
        (
            {"input": ["not", "an", "object"]},
            ErrorCode.INVALID_ARGUMENT,
            "input must be an object",
            "I4 non-object input",
        ),
        (
            {"input": {"x": "not-an-integer"}},
            ErrorCode.INVALID_ARGUMENT,
            "input violates the action's catalog input schema",
            "I4 schema-invalid input",
        ),
        (
            {"input": {"x": 1}},
            ErrorCode.INVALID_ARGUMENT,
            "input violates the descriptor action's input_constraints",
            "I5 descriptor narrowing",
        ),
    ],
)
def test_r1_invoke_bounds_before_the_device(
    tmp_path: Path, overrides: dict[str, Any], code: ErrorCode, fragment: str, label: str
) -> None:
    """R1: every gate refusal is typed, not_dispatched, names its gate, and
    the spy adapter records ZERO execute calls."""
    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(InvokeAdapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(**overrides), deadline_ns=11_000_000_000)
        assert result.error is not None, label
        assert result.error.code is code, label
        assert result.error.dispatch_state is DispatchState.NOT_DISPATCHED, label
        assert fragment in result.error.message, (label, result.error.message)
        assert harness.adapter.calls == 0, label
        plugin.plugin_close()
    finally:
        harness.close()


def test_i6_invoke_mints_the_host_dataset_id_on_the_context(tmp_path: Path) -> None:
    """I6: the host mints ds:{operation_id} on the context for invoke; a
    non-invoke dispatch on the same bridge keeps dataset_id None."""
    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(InvokeAdapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert result.status is OperationStatus.OK
        assert harness.adapter.context.dataset_id == "ds:op-i"
        identify = plugin.dispatch(
            OperationRequest.identify("op-id"), deadline_ns=11_000_000_000
        )
        assert identify.status is OperationStatus.OK
        assert harness.adapter.context.dataset_id is None
        # The strict cross-check did not fire for a plain configure result.
        assert result.data == {"action_id": "demo.act/1.0.0", "result": {"ok": True}}
        plugin.plugin_close()
    finally:
        harness.close()


def test_r6_schema_invalid_result_poisons_with_the_validator_message(
    tmp_path: Path,
) -> None:
    """R6: a schema-invalid result poisons PROTOCOL_ERROR carrying the
    validator's own message — never the generic failed-or-late wording."""
    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(InvokeAdapter(result={"ok": "not-a-boolean"}))
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.code is ErrorCode.PROTOCOL_ERROR
        assert "not of type 'boolean'" in result.error.message
        assert "Invalid, failed or late adapter result" not in result.error.message
        second = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert second.error is not None
        assert second.error.code is ErrorCode.INTERNAL_ERROR
        assert harness.adapter.calls == 1
        plugin.plugin_close()
    finally:
        harness.close()


def test_r6_action_id_echo_mismatch_poisons(tmp_path: Path) -> None:
    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(InvokeAdapter(action_echo="demo.other/1.0.0"))
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.code is ErrorCode.PROTOCOL_ERROR
        assert "action_id" in result.error.message
        plugin.plugin_close()
    finally:
        harness.close()


def test_r6_extra_data_key_poisons_the_closed_envelope(tmp_path: Path) -> None:
    class Extra(InvokeAdapter):
        async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
            self.calls += 1
            envelope = await super().execute(request, context)
            envelope["data"]["extra"] = True
            return envelope

    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(Extra())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.code is ErrorCode.PROTOCOL_ERROR
        plugin.plugin_close()
    finally:
        harness.close()


def test_r6_unknown_outcome_never_downgraded_through_invoke(tmp_path: Path) -> None:
    class Unknown(InvokeAdapter):
        async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
            self.calls += 1
            await context.mark_dispatch_started()
            return {
                "operation_id": request["operation_id"],
                "verb": "invoke",
                "status": "unknown",
                "error": {
                    "code": "DEVICE_REJECTED",
                    "message": "action refused by the device",
                    "dispatch_state": "dispatched",
                },
            }

    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(Unknown())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.dispatch_state is DispatchState.DISPATCHED
        plugin.plugin_close()
    finally:
        harness.close()


def test_r2_dataset_shaped_result_without_publication_poisons(
    tmp_path: Path,
) -> None:
    """R2 (strict posture, §3 slice 2): a dataset-shaped invoke result that
    was never admitted through dataset_publish poisons PROTOCOL_ERROR with
    the publication lie named — bridge-side state, not adapter
    cooperation."""
    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(InvokeAdapter(result=_DATASET_SHAPED_RESULT))
        plugin.plugin_open(object())
        result = plugin.dispatch(
            a_invoke_request(action_id="demo.raw/1.0.0", input={}),
            deadline_ns=11_000_000_000,
        )
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.code is ErrorCode.PROTOCOL_ERROR
        assert "dataset_publish" in result.error.message
        assert "Invalid, failed or late adapter result" not in result.error.message
        plugin.plugin_close()
    finally:
        harness.close()


def test_r2_corpus_fetched_dataset_refuses_at_the_schema_channel(
    tmp_path: Path,
) -> None:
    """The corpus-faithful arm: a fetch action whose output_schema refs the
    measurement dataset def refuses an ill-formed dataset through the
    schema channel (the validator's message), before the publication
    cross-check is reached."""
    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(InvokeAdapter(result=_DATASET_SHAPED_RESULT))
        plugin.plugin_open(object())
        result = plugin.dispatch(
            a_invoke_request(action_id="demo.fetch/1.0.0", input={"count": 1}),
            deadline_ns=11_000_000_000,
        )
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.code is ErrorCode.PROTOCOL_ERROR
        assert "required" in result.error.message
        plugin.plugin_close()
    finally:
        harness.close()


def test_invoke_dispatch_brackets_the_store_clamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row-B bracket extends to invoke when the controller exists
    (§2.3): the clamp forwards to the session's shared staged writer with
    the entry-time deadline."""
    harness = InvokeHarness(tmp_path)
    calls: list[dict[str, Any]] = []

    def _spy_clamp(deadline_ns: int, **kwargs: Any) -> Any:
        calls.append({"deadline_ns": deadline_ns, **kwargs})
        return contextlib.nullcontext()

    monkeypatch.setattr(harness.controller, "dispatch_clamp", _spy_clamp)
    try:
        plugin = harness.bridge(InvokeAdapter())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert result.status is OperationStatus.OK
        assert len(calls) == 1 and calls[0]["deadline_ns"] == 11_000_000_000
        identify = plugin.dispatch(
            OperationRequest.identify("op-id"), deadline_ns=11_000_000_000
        )
        assert identify.status is OperationStatus.OK
        assert len(calls) == 1  # a non-invoke dispatch does not clamp
        plugin.plugin_close()
    finally:
        harness.close()


def test_r17_invoke_classified_resource_refusal_names_no_capture_lane(
    tmp_path: Path,
) -> None:
    """R17: an invoke-classified RESOURCE_LIMIT refusal (the evidence lane —
    slice 2's only classifiable origin during invoke) names the invoke
    lane, never capture wording, and the session survives."""
    harness = InvokeHarness(tmp_path, evidence_quota=2)
    try:
        plugin = harness.bridge(InvokeAdapter(evidence_calls=5))
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert result.error is not None
        assert result.error.code is ErrorCode.RESOURCE_LIMIT
        assert result.error.dispatch_state is DispatchState.DISPATCHED
        assert "apture" not in result.error.message
        assert "invoke" in result.error.message
        # The session survives the classified refusal.
        again = plugin.dispatch(
            a_invoke_request(), deadline_ns=11_000_000_000
        )
        assert again.error is not None
        assert again.error.code is ErrorCode.RESOURCE_LIMIT
        plugin.plugin_close()
    finally:
        harness.close()


def test_bare_evidence_quota_raise_during_invoke_poisons(tmp_path: Path) -> None:
    """C3's discriminator through the invoke lane: a bare EvidenceQuotaExceeded
    the adapter raises itself (no bundle stamp) keeps the poison posture."""

    class Forged(InvokeAdapter):
        async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
            self.calls += 1
            raise EvidenceQuotaExceeded("forged")

    harness = InvokeHarness(tmp_path)
    try:
        plugin = harness.bridge(Forged())
        plugin.plugin_open(object())
        result = plugin.dispatch(a_invoke_request(), deadline_ns=11_000_000_000)
        assert result.status is OperationStatus.UNKNOWN
        assert result.error is not None
        assert result.error.code is ErrorCode.PROTOCOL_ERROR
        plugin.plugin_close()
    finally:
        harness.close()


def test_item8_self_contained_constraints_refs_resolve_at_dispatch(
    tmp_path: Path,
) -> None:
    """Item 8 (R22), the dispatch-level legitimate arm: a descriptor
    action whose input_constraints reference an internal ``#/$defs``
    pointer — the one ref shape I5's bare compile resolves — narrows at
    the gate with the validator's own message (both directions), with no
    exception escaping the gate region."""
    import copy

    harness = InvokeHarness(tmp_path)
    try:
        descriptor: dict[str, Any] = copy.deepcopy(INVOKE_DESCRIPTOR)
        descriptor["actions"]["demo.act/1.0.0"]["input_constraints"] = {
            "$defs": {"floor": {"minimum": 10}},
            "properties": {"x": {"$ref": "#/$defs/floor"}},
        }
        adapter = InvokeAdapter()
        harness.adapter = adapter
        plugin = OTDPBridge(
            adapter,
            descriptor=descriptor,
            services=harness.bundle,
            simulation=SimulationInfo(True, "Synthetic"),
            dataset=harness.controller,
        )
        plugin.plugin_open(object())
        ok = plugin.dispatch(a_invoke_request(input={"x": 20}), deadline_ns=11_000_000_000)
        assert ok.status is OperationStatus.OK
        refused = plugin.dispatch(a_invoke_request(input={"x": 1}), deadline_ns=11_000_000_000)
        assert refused.error is not None
        assert refused.error.code is ErrorCode.INVALID_ARGUMENT
        assert "input violates the descriptor action's input_constraints" in (
            refused.error.message
        )
        assert harness.adapter.calls == 1  # only the passing dispatch executed
        plugin.plugin_close()
    finally:
        harness.close()
