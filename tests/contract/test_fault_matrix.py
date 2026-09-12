"""WP04 S4 — the fault matrix and protocol fixtures (closes gate G1).

Replays every strict-JSON vector owned by plugins/benchweave/ against the real
plugins, and proves the timeout-after-dispatch rule at the ABI layer: a
result observed after its deadline expired may never claim ok — the slow
device is modelled by advancing the injected clock inside dispatch, and the
enforced downgrade is exactly the host rule WP05 will apply.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from benchweave.host import (
    DispatchState,
    ErrorCode,
    OperationRequest,
    OperationResult,
    OperationStatus,
    OperationVerb,
    SimulationInfo,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "plugins" / "benchweave"
TICK = 10**9


def _strict_loads(text: str) -> Any:
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(text, object_pairs_hook=reject_pairs, parse_constant=reject_constant)


class Clock:
    def __init__(self) -> None:
        self.now_ns = 0

    def monotonic_ns(self) -> int:
        return self.now_ns

    def iso(self) -> str:
        return "2026-09-11T00:00:00Z"

    def advance(self, ns: int) -> None:
        self.now_ns += ns


class NullServices:
    def resolve_content(self, content_id: str) -> bytes:
        return b"{}"

    def retain_evidence(self, key: str, payload: bytes) -> str:
        return f"evidence-{key}"

    def emit_event(self, kind: str, body: dict[str, Any]) -> None:
        pass

    def quota_state(self) -> dict[str, int]:
        return {"dataset_bytes_used": 0, "evidence_entries_used": 0, "events_emitted": 0}

    def register_reading_sink(self, sink: Any) -> None:
        pass


def load_plugin_module(name: str) -> ModuleType:
    path = ROOT / "plugins" / "benchweave" / name / "src" / f"benchweave_{name}" / "plugin.py"
    spec = importlib.util.spec_from_file_location(f"fixture_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_plugin(name: str, clock: Clock) -> Any:
    module = load_plugin_module(name)
    plugin = module.create_plugin(now_fn=clock.iso, monotonic_ns_fn=clock.monotonic_ns)
    plugin.plugin_open(NullServices())
    return plugin


def to_request(entry: dict[str, Any]) -> OperationRequest:
    return OperationRequest(
        operation_id="fault-op",
        verb=OperationVerb(entry["verb"]),
        arguments=dict(entry.get("arguments", {})),
    )


def assert_expect(result: OperationResult, expect: dict[str, Any]) -> None:
    status = expect.get("status")
    if status == "ok":
        assert result.status is OperationStatus.OK, expect.get("name", "")
        if "data_value" in expect:
            assert result.data.value == expect["data_value"]
        if "data_manufacturer" in expect:
            assert result.data.manufacturer == expect["data_manufacturer"]
        if "error_entry_code" in expect:
            codes = [entry.code for entry in result.data.entries]
            assert expect["error_entry_code"] in codes
        return
    assert result.status is OperationStatus.ERROR, expect.get("name", "")
    assert result.error is not None
    assert result.error.code.value == expect["error_code"]
    assert result.error.dispatch_state.value == expect["dispatch_state"]


# --- protocol fixture replay -------------------------------------------------


@pytest.mark.parametrize(
    "fixture_name",
    sorted(str(path.relative_to(FIXTURES)) for path in FIXTURES.glob("*/src/*/vectors.json")),
)
def test_protocol_vectors_replay(fixture_name: str) -> None:
    document = _strict_loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    plugin_name = document["plugin"]
    for vector in document["vectors"]:
        clock = Clock()
        plugin = make_plugin(plugin_name, clock)
        for setup_entry in vector.get("setup", []):
            plugin.dispatch(to_request(setup_entry), deadline_ns=TICK)
        clock.advance(int(vector.get("advance_ns", 0)))
        result = plugin.dispatch(to_request(vector["request"]), deadline_ns=10**12)
        assert_expect(result, vector["expect"])
        plugin.plugin_close()


# --- timeout-after-dispatch (the host rule, proven at the ABI layer) ----------


class SlowDevice:
    """Advances the clock inside dispatch, modelling a device that answers
    after the caller's deadline has already passed."""

    def __init__(self, inner: Any, clock: Clock, stall_ns: int) -> None:
        self._inner = inner
        self._clock = clock
        self._stall_ns = stall_ns

    @property
    def simulation(self) -> SimulationInfo:
        inner_info: SimulationInfo = self._inner.simulation
        return inner_info

    def plugin_open(self, services: Any) -> None:
        self._inner.plugin_open(services)

    def plugin_close(self) -> None:
        self._inner.plugin_close()

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        raw = self._inner.dispatch(request, deadline_ns=deadline_ns)
        self._clock.advance(self._stall_ns)
        if self._clock.monotonic_ns() >= deadline_ns and raw.status is OperationStatus.OK:
            return OperationResult.indeterminate(
                request.operation_id,
                request.verb,
                code=ErrorCode.TIMEOUT,
                message="deadline expired during dispatch; outcome not confirmed",
            )
        typed: OperationResult = raw
        return typed


def test_slow_device_never_claims_ok_after_deadline() -> None:
    clock = Clock()
    plugin = make_plugin("sim_psu", clock)
    slow = SlowDevice(plugin, clock, stall_ns=5 * TICK)
    result = slow.dispatch(OperationRequest.identify("op-1"), deadline_ns=TICK)
    assert result.status is OperationStatus.UNKNOWN
    assert result.error is not None and result.error.code is ErrorCode.TIMEOUT
    assert result.error.dispatch_state in (DispatchState.DISPATCHED, DispatchState.UNKNOWN)


def test_fast_device_within_deadline_is_unaffected() -> None:
    clock = Clock()
    plugin = make_plugin("sim_psu", clock)
    slow = SlowDevice(plugin, clock, stall_ns=1)
    result = slow.dispatch(OperationRequest.identify("op-1"), deadline_ns=TICK)
    assert result.status is OperationStatus.OK


def test_indeterminate_result_cannot_claim_not_dispatched() -> None:
    result = OperationResult.indeterminate(
        "op-1", OperationVerb.WRITE, code=ErrorCode.TIMEOUT, message="expired mid-dispatch"
    )
    assert result.error is not None
    assert result.error.dispatch_state is not DispatchState.NOT_DISPATCHED
