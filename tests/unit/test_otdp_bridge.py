"""The explicit async-to-sync seam preserves host safety semantics."""

from types import SimpleNamespace
from typing import Any

import pytest

from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.plugin import SimulationInfo
from benchweave.host.types import (
    DispatchState,
    ErrorCode,
    Identity,
    OperationRequest,
    OperationStatus,
    OperationVerb,
    Reading,
    WriteReceipt,
)


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
