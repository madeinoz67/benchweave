"""End to end: the poll engine driving a real bridge's next_event
mediation over a real store (issue #43 slice 2).

The bridge validates, stamps, records and lands; the engine slices, ticks
and rotates. This is the mini-Option-B leg proven on the real seam — the
activation wiring (row 9) will construct exactly these pieces inside a
run, so this test pins their composition works before that wiring exists.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from benchweave.content.stream_services import build_stream_services
from benchweave.control.clocking import TestClock
from benchweave.control.stream_polling import StreamPollEngine
from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.plugin import SimulationInfo
from benchweave.host.services import QuotaLimits
from benchweave.host.types import OperationRequest, OperationStatus, OperationVerb
from benchweave.state.store import Store

STREAM_DESCRIPTOR = {
    "stream_limits": {"min_interval_ms": 10, "max_subscriptions": 2},
}


class StreamingAdapter:
    """Answers next_event from a script; echoes subscription ids on
    dispatch."""

    def __init__(self, script: dict[str, list[dict[str, Any] | None]]) -> None:
        self.script = script
        self.calls = 0
        self.polls: list[tuple[str, int, int]] = []

    async def open(self, descriptor: dict[str, Any], services: Any, context: Any) -> None:
        return None

    async def close(self, context: Any) -> None:
        return None

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        self.calls += 1
        if request["verb"] in ("stream_subscribe", "stream_unsubscribe"):
            return {
                "operation_id": request["operation_id"],
                "verb": request["verb"],
                "status": "ok",
                "data": {"subscription_id": request["arguments"]["subscription_id"]},
            }
        return {
            "operation_id": request["operation_id"],
            "verb": request["verb"],
            "status": "ok",
            "data": {
                "manufacturer": "Example",
                "model": "Streambench",
                "serial": None,
                "firmware": None,
                "source": "device",
            },
        }

    async def next_event(self, subscription_id: str, context: Any) -> dict[str, Any] | None:
        self.polls.append((subscription_id, context.deadline_monotonic, 0))
        queue = self.script.get(subscription_id)
        if not queue:
            return None
        return queue.pop(0)


def a_reading() -> dict[str, Any]:
    return {
        "parameter": "temperature",
        "value": 20.0,
        "unit": "Cel",
        "observed_at": "2026-09-22T00:00:00Z",
        "age_ms": 0,
        "quality": "valid",
        "source": "device",
    }


def test_the_engine_drives_bridge_polls_that_land_as_evidence(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream-poll.db")
    try:
        content_digest = _admit_descriptor(store)
        controller = build_stream_services(
            descriptor_digest=content_digest,
            store=store,
            wall=lambda: "2026-09-22T00:00:00Z",
            quota=QuotaLimits(
                max_dataset_bytes=8192,
                max_evidence_entries=50,
                max_event_batch=10,
                max_subscriptions=2,
            ),
            context_key="poll-engine-session",
        )
        assert controller is not None
        adapter = StreamingAdapter(
            script={
                "sub-alpha": [
                    {"subscription_id": "sub-alpha", "sequence": 0, "kind": "telemetry",
                     "reading": a_reading()},
                    {"subscription_id": "sub-alpha", "sequence": 1, "kind": "telemetry",
                     "reading": a_reading()},
                ],
                "sub-beta": [
                    {"subscription_id": "sub-beta", "sequence": 0, "kind": "telemetry",
                     "reading": a_reading()},
                ],
            }
        )
        plugin = OTDPBridge(
            adapter,
            descriptor=dict(STREAM_DESCRIPTOR),
            services=_FrozenMonotonic(),
            simulation=SimulationInfo(True, "Synthetic"),
            stream=controller,
        )
        plugin.plugin_open(object())
        for subscription_id in ("sub-alpha", "sub-beta"):
            result = plugin.dispatch(
                OperationRequest(
                    "op-" + subscription_id,
                    OperationVerb.STREAM_SUBSCRIBE,
                    {
                        "subscription_id": subscription_id,
                        "parameters": ["temperature"],
                        "min_interval_ms": 10,
                    },
                ),
                deadline_ns=10_000_000_000,
            )
            assert result.status is OperationStatus.OK

        clock = TestClock()
        ticks: list[int] = []
        engine = StreamPollEngine(
            poll=plugin.poll_event,
            live=controller.live_subscription_ids,
            clock=clock,
            tick=lambda: ticks.append(clock.now_ns()),
            poll_slice_ns=10_000_000,
        )
        seen: list[tuple[str, object]] = []
        refused = engine.poll_until(
            deadline_ns=clock.now_ns() + 3 * 10_000_000,
            on_event=lambda subscription_id, event, receipt: seen.append(
                (subscription_id, event["sequence"])
            ),
        )
        assert refused == []
        # Every scripted event flowed and landed.
        assert sorted(seen) == [("sub-alpha", 0), ("sub-alpha", 1), ("sub-beta", 0)]
        rows = store.connection.execute(
            "SELECT content_ref_json FROM evidence WHERE kind = 'event_log'"
        ).fetchall()
        landed = [json.loads(row[0]) for row in rows]
        assert {row["subscription_id"] for row in landed} == {"sub-alpha", "sub-beta"}
        for row in landed:
            assert row["capture_id"] is None and row["dataset_id"] is None
        # Monitor ticks ran throughout (between polls and at boundaries).
        assert len(ticks) >= len(adapter.polls)
        plugin.plugin_close()
    finally:
        store.close()


def test_a_quota_teardown_mid_stream_drops_only_that_stream(tmp_path: Path) -> None:
    """The engine keeps polling the healthy stream after another stream's
    landing hit the event quota: the refusal drops the torn-down
    subscription from rotation, the session survives (Decision 4)."""
    store = Store.open(tmp_path / "stream-poll.db")
    try:
        content_digest = _admit_descriptor(store)
        controller = build_stream_services(
            descriptor_digest=content_digest,
            store=store,
            wall=lambda: "2026-09-22T00:00:00Z",
            quota=QuotaLimits(
                max_dataset_bytes=8192,
                max_evidence_entries=2,  # two event rows: both first events land
                max_event_batch=10,
                max_subscriptions=2,
            ),
            context_key="poll-engine-session",
        )
        assert controller is not None
        adapter = StreamingAdapter(
            script={
                "sub-alpha": [
                    {"subscription_id": "sub-alpha", "sequence": 0, "kind": "telemetry",
                     "reading": a_reading()},
                    {"subscription_id": "sub-alpha", "sequence": 1, "kind": "telemetry",
                     "reading": a_reading()},
                ],
                "sub-beta": [
                    {"subscription_id": "sub-beta", "sequence": 0, "kind": "telemetry",
                     "reading": a_reading()},
                ],
            }
        )
        plugin = OTDPBridge(
            adapter,
            descriptor=dict(STREAM_DESCRIPTOR),
            services=_FrozenMonotonic(),
            simulation=SimulationInfo(True, "Synthetic"),
            stream=controller,
        )
        plugin.plugin_open(object())
        for subscription_id in ("sub-alpha", "sub-beta"):
            assert plugin.dispatch(
                OperationRequest(
                    "op-" + subscription_id,
                    OperationVerb.STREAM_SUBSCRIBE,
                    {
                        "subscription_id": subscription_id,
                        "parameters": ["temperature"],
                        "min_interval_ms": 10,
                    },
                ),
                deadline_ns=10_000_000_000,
            ).status is OperationStatus.OK

        clock = TestClock()
        engine = StreamPollEngine(
            poll=plugin.poll_event,
            live=controller.live_subscription_ids,
            clock=clock,
            tick=lambda: None,
            poll_slice_ns=10_000_000,
        )
        seen: list[str] = []
        refused = engine.poll_until(
            deadline_ns=clock.now_ns() + 4 * 10_000_000,
            on_event=lambda subscription_id, event, receipt: seen.append(subscription_id),
        )
        # Rotation is sorted: both first events land (the two-row dimension
        # fills), then alpha's second event is the third landing and
        # refuses at the boundary — alpha tears down while the drained beta
        # stream stays live and quiet.
        assert refused == ["sub-alpha"]
        assert seen == ["sub-alpha", "sub-beta"]
        assert not controller.is_live("sub-alpha")
        assert controller.is_live("sub-beta")
        # The session survived: a dispatch still executes.
        follow = plugin.dispatch(
            OperationRequest.identify("op-after"), deadline_ns=10_000_000_000
        )
        assert follow.status is OperationStatus.OK
        plugin.plugin_close()
    finally:
        store.close()


def _admit_descriptor(store: Store) -> str:
    from benchweave.content.store import ContentStore

    content = ContentStore(store)
    raw = {
        "id": "dev.local.poll-engine",
        "descriptor_version": "1.0.0",
        "integration": {
            "mode": "adapter",
            "adapter": {
                "entry_point": "harness:create_plugin",
                "api_version": "1.1",
                "version": "1.0.0",
                "dependencies": [],
                "permissions": ["scoped_transport", "event_sink"],
            },
        },
    }
    blob = json.dumps(raw, sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    content.put_document(blob, digest, raw, "otdp-descriptor", "2026-09-22T00:00:00Z")
    return digest


class _FrozenMonotonic:
    """The bridge's services subset: a frozen monotonic reading (the
    adapter scripts return instantly, so the deadline math passes)."""

    def monotonic(self) -> float:
        return 0.0
