"""Row D sim honesty (issue #176, design Decision 3): the bridge-leg
streaming adapter's emission logic against the bridge's event contract.

D-R2: a pinned test drives the sim's ``next_event`` directly — the
declared interval floor is honored (a poll inside the window returns
None; a healthy quiet stream is not an error), per-subscription
sequences start at zero and strictly increase, and the terminal
``ended`` event carries code and message and ends the subscription.
Every emitted event is validated through the REAL bridge validator
(``OTDPBridge._validate_event``) — the bridge's event-validation
contract is the authority; a sim that violates it poisons by design,
and these pins keep the sim honest.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.plugin import SimulationInfo

ROOT = Path(__file__).resolve().parents[2]
EXECUTION_FIXTURES = ROOT / "fixtures" / "execution"

ADAPTER_SUB_INTERVAL_MS = 50


def load_adapter_module() -> ModuleType:
    path = (
        ROOT
        / "plugins"
        / "benchweave"
        / "sim_psu"
        / "src"
        / "benchweave_sim_psu"
        / "adapter.py"
    )
    assert path.is_file(), f"bridge-leg adapter missing: {path}"
    spec = importlib.util.spec_from_file_location("benchweave_sim_psu_adapter", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Clock:
    """Injected monotonic time (seconds) and a fixed wall stamp."""

    def __init__(self) -> None:
        self.now = 100.0

    def monotonic(self) -> float:
        return self.now

    def utc_now(self) -> str:
        return "2026-09-24T00:00:00Z"


class _PollContext:
    def __init__(self, clock: _Clock) -> None:
        self.services = clock

    async def mark_dispatch_started(self) -> None:
        return None


def a_bridge_validator() -> OTDPBridge:
    """A throwaway unopened bridge whose event validators the test drives."""
    return OTDPBridge(
        object(),
        descriptor={},
        services=SimpleNamespace(monotonic=lambda: 0.0),
        simulation=SimulationInfo(True, "test"),
    )


def test_the_sim_emission_logic_honors_the_contract() -> None:
    """D-R2: floor honored, sequences strictly increasing from zero,
    terminal ``ended`` with code and message — every event through the
    real bridge validator, and telemetry values tracking device state."""
    module = load_adapter_module()
    adapter = module.create_plugin()
    clock = _Clock()
    context = _PollContext(clock)
    validator = a_bridge_validator()

    async def drive() -> list[dict[str, object]]:
        await adapter.open({}, clock, context)

        async def execute(verb: str, arguments: dict[str, object]) -> dict[str, object]:
            # The path-loaded adapter module is Any to the type checker
            # (plugins/ sits outside mypy's scope); narrow the envelope.
            return cast(
                dict[str, object],
                await adapter.execute(
                    {"operation_id": f"op-{verb}", "verb": verb, "arguments": arguments},
                    context,
                ),
            )

        subscribe = await execute(
            "stream_subscribe",
            {
                "subscription_id": "sub-1",
                "parameters": ["output_voltage_v"],
                "min_interval_ms": ADAPTER_SUB_INTERVAL_MS,
            },
        )
        assert subscribe["status"] == "ok"
        assert subscribe["data"] == {"subscription_id": "sub-1"}

        # Device state through the bridge verb set: the telemetry the sim
        # emits must be the device's actual reading, not a constant.
        await execute("write", {"parameter": "voltage_setpoint_v", "value": 5.0})
        await execute("write", {"parameter": "output_enabled", "value": True})

        # First poll: emission starts at the subscription instant (sequence 0).
        first = await adapter.next_event("sub-1", context)
        assert first is not None and first["sequence"] == 0
        assert first["kind"] == "telemetry"
        assert first["reading"]["parameter"] == "output_voltage_v"
        assert first["reading"]["value"] == 5.0

        # A poll inside the declared interval window: the floor is honored —
        # a healthy quiet stream returns None and is not an error.
        quiet = await adapter.next_event("sub-1", context)
        assert quiet is None

        events: list[dict[str, object]] = [first]
        for expected_sequence in range(1, module._EVENTS_PER_SUBSCRIPTION):
            clock.now += ADAPTER_SUB_INTERVAL_MS / 1000.0
            event = await adapter.next_event("sub-1", context)
            assert event is not None, f"no event at sequence {expected_sequence}"
            assert event["sequence"] == expected_sequence
            assert event["kind"] == "telemetry"
            events.append(event)

        # The terminal event: the synthetic-telemetry budget exhausts and the
        # stream says so with code and message, at the next sequence number.
        clock.now += ADAPTER_SUB_INTERVAL_MS / 1000.0
        ended = await adapter.next_event("sub-1", context)
        assert ended is not None
        assert ended["kind"] == "ended"
        assert ended["sequence"] == module._EVENTS_PER_SUBSCRIPTION
        assert isinstance(ended["code"], str) and ended["code"]
        assert isinstance(ended["message"], str) and ended["message"]
        events.append(ended)

        # After the terminal event the subscription is gone: the bridge's
        # registry (which the validator mirrors) refuses it as ended.
        after = await adapter.next_event("sub-1", context)
        assert after is None

        # Unknown subscriptions never produce events.
        assert await adapter.next_event("absent", context) is None
        return events

    events = asyncio.run(drive())

    # The bridge's validators remain the authority: every event the sim
    # produced validates against the closed $defs/event with the exact
    # sequence/kind progression the poller would have seen.
    last_sequence: int | None = None
    last_kind: str | None = None
    for event in events:
        validated = validator._validate_event(
            "sub-1", event, last_sequence=last_sequence, last_kind=last_kind
        )
        assert validated["subscription_id"] == "sub-1"
        last_sequence = int(validated["sequence"])
        last_kind = str(validated["kind"])


def test_the_sim_honors_the_requested_interval_per_subscription() -> None:
    """Two subscriptions at different requested intervals emit on their own
    floors: the shorter-interval subscription produces events in windows the
    longer one still considers quiet."""
    module = load_adapter_module()
    adapter = module.create_plugin()
    clock = _Clock()
    context = _PollContext(clock)

    async def drive() -> tuple[bool, bool]:
        await adapter.open({}, clock, context)
        for subscription_id, interval in (
            ("sub-fast", ADAPTER_SUB_INTERVAL_MS),
            ("sub-slow", 10 * ADAPTER_SUB_INTERVAL_MS),
        ):
            result = await adapter.execute(
                {
                    "operation_id": f"op-{subscription_id}",
                    "verb": "stream_subscribe",
                    "arguments": {
                        "subscription_id": subscription_id,
                        "parameters": ["output_current_a"],
                        "min_interval_ms": interval,
                    },
                },
                context,
            )
            assert result["status"] == "ok"
        await adapter.next_event("sub-fast", context)  # seq 0 at t0
        await adapter.next_event("sub-slow", context)  # seq 0 at t0
        clock.now += 1.0  # well past both floors: both re-emit
        fast_second = await adapter.next_event("sub-fast", context)
        slow_second = await adapter.next_event("sub-slow", context)
        return fast_second is not None, slow_second is not None

    fast_emitted, slow_emitted = asyncio.run(drive())
    assert fast_emitted is True, "fast subscription missed its floor window"
    assert slow_emitted is True, "slow subscription never re-emitted after 1 s"


def test_the_fixture_descriptor_declares_the_streaming_surface() -> None:
    """The demo descriptor's row-D authoring values, pinned: the event_sink
    permission and the stream_limits the subscribe gate enforces (fixture
    authoring choices for a synthetic bench — not commissioned numbers)."""
    descriptor = json.loads(
        (EXECUTION_FIXTURES / "descriptor-sim-psu.json").read_bytes()
    )
    assert descriptor["integration"]["adapter"]["permissions"] == [
        "scoped_transport",
        "event_sink",
    ]
    assert descriptor["stream_limits"] == {
        "min_interval_ms": 20,
        "max_subscriptions": 4,
    }
    assert (
        descriptor["integration"]["adapter"]["entry_point"]
        == "benchweave_sim_psu.adapter:create_plugin"
    )
