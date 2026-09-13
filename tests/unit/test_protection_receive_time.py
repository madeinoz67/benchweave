"""Freshness uses host receipt time without trusting device timestamps."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from benchweave.control.coordinator import _RunMonitor
from benchweave.control.protection import read_signal_values
from benchweave.host.plugin import DevicePlugin
from benchweave.host.types import (
    OperationRequest,
    OperationResult,
    OperationStatus,
    Quality,
    Reading,
    ReadingSource,
)


@pytest.mark.parametrize("sampling_path", ["direct", "monitor"])
@pytest.mark.parametrize(
    ("offset_us", "buffer_age_ms", "expected_valid"),
    [(0, 0, True), (1, 0, False), (2000, 0, False), (-200000, 0, False), (0, 200, False)],
    ids=["fresh", "future-submillisecond", "future", "host-stale", "device-buffer-stale"],
)
def test_each_delayed_read_uses_its_receive_time(
    offset_us: int, buffer_age_ms: int, expected_valid: bool, sampling_path: str
) -> None:
    """Serial reads advance time; only genuinely future/stale readings fail."""
    moment = datetime(2026, 9, 13, tzinfo=UTC)

    class DelayedPlugin:
        def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
            nonlocal moment
            moment += timedelta(milliseconds=3)
            return OperationResult(
                operation_id=request.operation_id,
                verb=request.verb,
                status=OperationStatus.OK,
                data=Reading(
                    parameter=str(request.arguments["parameter"]),
                    value=0.0,
                    unit="A",
                    observed_at=(moment + timedelta(microseconds=offset_us)).isoformat(),
                    age_ms=buffer_age_ms,
                    quality=Quality.VALID,
                    source=ReadingSource.DEVICE,
                ),
            )

    bench = {
        "signals": [
            {
                "id": name,
                "source": {"kind": "parameter", "device_id": "psu", "parameter": name},
                "max_age_ms": 100,
                "absolute_error": 0.01,
            }
            for name in ("current", "second-current")
        ]
    }
    plugins = {"psu": cast(DevicePlugin, DelayedPlugin())}
    if sampling_path == "direct":
        snapshot = read_signal_values(
            plugins, bench, deadline_ns=1_000_000_000, wall_now=lambda: moment.isoformat()
        )
    else:
        # Exercise the real monitor's sampling call without leases or hardware.
        clock: Any = SimpleNamespace(now_ns=lambda: 0, now_iso=lambda: moment.isoformat())
        monitor = _RunMonitor(
            cast(Any, None),
            "bench",
            {"continuous_conditions": []},
            bench,
            plugins,
            clock,
            clock,
            run_id="run",
            lease_sequence=1,
        )
        monitor.phase = "protecting"
        retained: list[Any] = []
        monitor.retain = retained.append
        monitor.tick()
        assert len(retained) == 1
        snapshot = retained[0]
    assert [value.valid for value in snapshot.values()] == [expected_valid, expected_valid]
    if expected_valid:
        assert all(value.age_ms == 0 and value.unit == "A" for value in snapshot.values())
