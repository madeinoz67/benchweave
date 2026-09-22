"""The streaming services: subscription registry, event landing, teardown
markers, gap honesty (issue #43 slice 2, Decision 4).

Derivations (from primary sources, not the plan's restatement): the landing
shape is Decision 4's one-way door — event rows land as ``event_log``-kind
evidence with a content_ref carrying at minimum ``{subscription_id,
sequence, event kind, host_received_at, payload digest, capture/dataset
linkage}``; the teardown/quota refusal taxonomy (``RESOURCE_LIMIT`` refusal
plus host-cause ``ended`` marker, never session poison) is Decision 4; the
kind-scoped accounting dimension is the quota stack (``max_evidence_entries``
keeps meaning only what ``retain_evidence`` consumed); ``event_sink``
permission gating mirrors slice 1's ``artifact_writer`` treatment (spec
§8/S15: "Event production uses next_event and requires ``event_sink``
permission for streaming adapters").
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore, EvidenceQuotaExceeded, RetainingServices
from benchweave.content.stream_services import (
    StreamController,
    StreamLimitExceeded,
    build_stream_services,
    mint_subscription_id,
)
from benchweave.host.services import QuotaLimits, ReadingSinks
from benchweave.state.store import Store

_WALL = "2026-09-22T00:00:00Z"


def a_quota(**overrides: Any) -> QuotaLimits:
    values: dict[str, int] = {
        "max_dataset_bytes": 8192,
        "max_evidence_entries": 50,
        "max_event_batch": 4,
        "max_subscriptions": 2,
    }
    values.update(overrides)
    return QuotaLimits(**values)


def a_controller(store: Store, **overrides: Any) -> StreamController:
    controller = build_stream_services(
        descriptor_digest=a_raw_descriptor(store),
        store=store,
        wall=lambda: _WALL,
        quota=a_quota(**overrides),
        context_key="stream-session",
    )
    assert controller is not None
    return controller


def a_raw_descriptor(store: Store, *, permissions: list[str] | None = None) -> str:
    """Cache a RAW full-form descriptor at its pinned digest; return the digest."""
    content = ContentStore(store)
    raw = {
        "id": "dev.local.stream-harness",
        "descriptor_version": "1.0.0",
        "integration": {
            "mode": "adapter",
            "adapter": {
                "entry_point": "harness:create_plugin",
                "api_version": "1.1",
                "version": "1.0.0",
                "dependencies": [],
                "permissions": permissions
                or ["scoped_transport", "artifact_writer", "event_sink"],
            },
        },
    }
    blob = json.dumps(raw, sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    content.put_document(blob, digest, raw, "otdp-descriptor", _WALL)
    return digest


def a_telemetry(subscription_id: str, sequence: int) -> dict[str, Any]:
    return {
        "subscription_id": subscription_id,
        "sequence": sequence,
        "kind": "telemetry",
        "reading": {
            "parameter": "temperature",
            "value": 21.5,
            "unit": "Cel",
            "observed_at": _WALL,
            "age_ms": 0,
            "quality": "valid",
            "source": "device",
        },
    }


def event_rows(store: Store, reference: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    sql = "SELECT evidence_id, kind, content_ref_json, artifact_id, context_key FROM evidence"
    rows = store.connection.execute(sql).fetchall()
    parsed = [
        {
            "evidence_id": row[0],
            "kind": row[1],
            "content_ref": json.loads(row[2]),
            "artifact_id": row[2 - 2] and row[3],
            "context_key": row[4],
        }
        for row in rows
    ]
    if reference is None:
        return parsed
    return [
        row
        for row in parsed
        if all(row["content_ref"].get(key) == value for key, value in reference.items())
    ]


# --- the subscription id and the registry ----------------------------------------


def test_minted_subscription_ids_are_unique_contract_shaped_opaques() -> None:
    """Decision 4: host-minted globally-unique uuid4 opaques; the registry
    keys on the full id only, so the format stays reversible."""
    ids = {mint_subscription_id() for _ in range(64)}
    assert len(ids) == 64
    for value in ids:
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", value), value


def test_reserve_enforces_the_host_ceiling_and_dedupes_ids(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store)  # max_subscriptions=2
        controller.reserve(
            subscription_id="sub-one", parameters=("temperature",), min_interval_ms=100
        )
        controller.reserve(
            subscription_id="sub-two", parameters=("voltage",), min_interval_ms=100
        )
        with pytest.raises(StreamLimitExceeded):
            controller.reserve(
                subscription_id="sub-three", parameters=("current",), min_interval_ms=100
            )
        assert controller.live_subscription_ids() == ["sub-one", "sub-two"]
        with pytest.raises(ValueError):
            controller.reserve(
                subscription_id="sub-one", parameters=("temperature",), min_interval_ms=100
            )
    finally:
        store.close()


def test_release_drops_a_reservation_that_never_went_live(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store)
        controller.reserve(
            subscription_id="sub-one", parameters=("temperature",), min_interval_ms=100
        )
        assert controller.release("sub-one") is True
        assert controller.live_subscription_ids() == []
        assert controller.release("sub-one") is False  # already gone
        # The freed slot is reusable: the ceiling is live-count, not a census.
        controller.reserve(
            subscription_id="sub-next", parameters=("temperature",), min_interval_ms=100
        )
        assert controller.live_subscription_ids() == ["sub-next"]
    finally:
        store.close()


def test_record_event_advances_sequence_state_and_ended_is_terminal(
    tmp_path: Path,
) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store)
        controller.reserve(
            subscription_id="sub-one", parameters=("temperature",), min_interval_ms=100
        )
        controller.record_event("sub-one", sequence=0, kind="telemetry")
        state = controller.subscription("sub-one")
        assert state is not None and state.last_sequence == 0
        controller.record_event("sub-one", sequence=1, kind="ended")
        state = controller.subscription("sub-one")
        assert state is not None and state.last_kind == "ended"
        assert controller.live_subscription_ids() == []  # ended is terminal
    finally:
        store.close()


# --- the event_sink permission gate -----------------------------------------------


def test_admission_without_event_sink_builds_no_stream_services(tmp_path: Path) -> None:
    """The A11 mirror: without the permission there are no event services at
    all — None, and the composing object never sees a registry."""
    store = Store.open(tmp_path / "stream.db")
    try:
        digest = a_raw_descriptor(store, permissions=["scoped_transport", "artifact_writer"])
        controller = build_stream_services(
            descriptor_digest=digest,
            store=store,
            wall=lambda: _WALL,
            quota=a_quota(),
            context_key="stream-session",
        )
        assert controller is None
    finally:
        store.close()


def test_admission_with_event_sink_builds_the_controller(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store)
        assert isinstance(controller, StreamController)
    finally:
        store.close()


def test_admission_rejects_an_absent_descriptor_loudly(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        with pytest.raises(ValueError, match="raw descriptor not cached"):
            build_stream_services(
                descriptor_digest="0" * 64,
                store=store,
                wall=lambda: _WALL,
                quota=a_quota(),
                context_key="stream-session",
            )
    finally:
        store.close()


# --- the landing (the one-way door) -------------------------------------------------


def test_landed_rows_carry_the_decision_4_content_ref(tmp_path: Path) -> None:
    """R4's row-shape arm: subscription_id, sequence, kind,
    host_received_at, payload digest (recomputed over the stored artifact
    bytes), and the capture/dataset linkage fields present from event one —
    retrofitting them after accumulation would be a data migration."""
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store)
        event = a_telemetry("sub-one", 0)
        from benchweave.content.stream_services import LandedEvent

        evidence_ids = controller.land_events([LandedEvent(event, "2026-09-22T00:00:01Z")])
        assert len(evidence_ids) == 1
        rows = event_rows(store)
        assert len(rows) == 1
        row = rows[0]
        assert row["kind"] == "event_log"
        assert row["context_key"] == "stream-session"
        reference = row["content_ref"]
        assert reference["subscription_id"] == "sub-one"
        assert reference["sequence"] == 0
        assert reference["kind"] == "telemetry"
        assert reference["host_received_at"] == "2026-09-22T00:00:01Z"
        # The linkage fields land as explicit nulls on the core lane (the
        # projection's group-by exists from event one).
        assert reference["capture_id"] is None
        assert reference["dataset_id"] is None
        # The payload digest is over the real stored bytes, not a column.
        payload = json.dumps(event, sort_keys=True).encode()
        assert reference["sha256"] == hashlib.sha256(payload).hexdigest()
        stored = store.connection.execute(
            "SELECT data FROM artifacts WHERE artifact_id = ?", (row["artifact_id"],)
        ).fetchone()[0]
        assert bytes(stored) == payload
    finally:
        store.close()


def test_landing_is_transactional_per_batch(tmp_path: Path) -> None:
    """A batch whose last row crosses the kind-scoped ceiling leaves ZERO
    rows — the partial-batch posture is refused, not half-landed."""
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store, max_evidence_entries=2, max_event_batch=4)
        from benchweave.content.stream_services import LandedEvent

        batch = [
            LandedEvent(a_telemetry("sub-one", 0), _WALL),
            LandedEvent(a_telemetry("sub-one", 1), _WALL),
            LandedEvent(a_telemetry("sub-one", 2), _WALL),  # exceeds the ceiling of 2
        ]
        with pytest.raises(EvidenceQuotaExceeded):
            controller.land_events(batch)
        assert event_rows(store) == []
    finally:
        store.close()


def test_max_event_batch_bounds_each_landing_batch(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store, max_event_batch=2)
        from benchweave.content.stream_services import LandedEvent

        oversized = [LandedEvent(a_telemetry("sub-one", i), _WALL) for i in range(3)]
        with pytest.raises(ValueError, match="max_event_batch"):
            controller.land_events(oversized)
        assert event_rows(store) == []
        # At the bound itself: allowed.
        two = [LandedEvent(a_telemetry("sub-one", i), _WALL) for i in range(2)]
        assert len(controller.land_events(two)) == 2
    finally:
        store.close()


def test_telemetry_landings_deliver_readings_to_registered_sinks(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        sinks = ReadingSinks()
        seen: list[Any] = []
        sinks.register(seen.append)
        controller = build_stream_services(
            descriptor_digest=a_raw_descriptor(store),
            store=store,
            wall=lambda: _WALL,
            quota=a_quota(),
            context_key="stream-session",
            reading_sinks=sinks,
        )
        assert controller is not None
        from benchweave.content.stream_services import LandedEvent

        controller.land_events([LandedEvent(a_telemetry("sub-one", 0), _WALL)])
        assert seen == [a_telemetry("sub-one", 0)["reading"]]
    finally:
        store.close()


# --- teardown markers and gap honesty ------------------------------------------------


def test_mark_ended_writes_the_host_cause_marker_and_remembers_it(
    tmp_path: Path,
) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store)
        controller.reserve(
            subscription_id="sub-one", parameters=("temperature",), min_interval_ms=100
        )
        assert controller.mark_ended("sub-one", cause="event quota exhausted") is True
        assert controller.live_subscription_ids() == []
        markers = event_rows(store, {"marker": "host_ended"})
        assert len(markers) == 1
        assert markers[0]["content_ref"]["id"] == "sub-one"
        assert markers[0]["content_ref"]["cause"] == "event quota exhausted"
        # Idempotent: a second teardown of the same subscription writes nothing.
        assert controller.mark_ended("sub-one", cause="again") is False
        assert len(event_rows(store, {"marker": "host_ended"})) == 1
    finally:
        store.close()


def test_sweep_tears_down_every_live_subscription_with_markers(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store)
        controller.reserve(
            subscription_id="sub-a", parameters=("temperature",), min_interval_ms=100
        )
        controller.reserve(
            subscription_id="sub-b", parameters=("voltage",), min_interval_ms=100
        )
        torn = controller.sweep(reason="plugin_close")
        assert torn == ["sub-a", "sub-b"]
        assert controller.live_subscription_ids() == []
        markers = event_rows(store, {"marker": "host_ended"})
        assert {m["content_ref"]["id"] for m in markers} == {"sub-a", "sub-b"}
        assert all(m["content_ref"]["cause"] == "plugin_close" for m in markers)
    finally:
        store.close()


def test_the_jump_without_gap_annotation_is_a_host_evidence_row(tmp_path: Path) -> None:
    """R4's pinned HOST mechanism: after a simulated drop (a forward jump
    with no preceding ``gap`` event), the host records the annotation — not
    the fixture's emission duty."""
    store = Store.open(tmp_path / "stream.db")
    try:
        controller = a_controller(store)
        controller.reserve(
            subscription_id="sub-one", parameters=("temperature",), min_interval_ms=100
        )
        controller.note_sequence_jump("sub-one", from_sequence=2, to_sequence=7)
        annotations = event_rows(store, {"marker": "sequence_jump_without_gap"})
        assert len(annotations) == 1
        reference = annotations[0]["content_ref"]
        assert reference["id"] == "sub-one"
        assert reference["from_sequence"] == 2
        assert reference["to_sequence"] == 7
    finally:
        store.close()


# --- ReadingSinks and the live gateway members ---------------------------------------


def test_reading_sinks_register_deliver_and_contain_failures() -> None:
    sinks = ReadingSinks()
    seen: list[Any] = []
    sinks.register(seen.append)

    def broken(reading: Any) -> None:
        raise RuntimeError("sink failed")

    sinks.register(broken)
    sinks.deliver({"parameter": "temperature"})
    assert seen == [{"parameter": "temperature"}]
    assert sinks.failures == 1
    with pytest.raises(TypeError):
        sinks.register(object())


def test_retaining_services_emit_event_lands_within_the_event_quota(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        content = ContentStore(store)
        services = RetainingServices(
            content,
            quota=1,
            now=_WALL,
            wall=lambda: "2026-09-22T00:00:02Z",
            context_key="run:stream-1",
        )
        services.emit_event("stream_started", {"subscription_id": "sub-one"})
        rows = event_rows(store, {"kind": "stream_started"})
        assert len(rows) == 1
        assert rows[0]["context_key"] == "run:stream-1"
        assert rows[0]["content_ref"]["host_received_at"] == "2026-09-22T00:00:02Z"
        with pytest.raises(EvidenceQuotaExceeded):
            services.emit_event("stream_stopped", {"subscription_id": "sub-one"})
    finally:
        store.close()


def test_retaining_services_emit_event_requires_a_context_key(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        services = RetainingServices(ContentStore(store), quota=10, now=_WALL)
        with pytest.raises(ValueError, match="context key"):
            services.emit_event("x", {})
    finally:
        store.close()


def test_retaining_services_registers_reading_sinks(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "stream.db")
    try:
        services = RetainingServices(ContentStore(store), quota=10, now=_WALL)
        seen: list[Any] = []
        services.register_reading_sink(seen.append)
        services.reading_sinks.deliver({"parameter": "voltage"})
        assert seen == [{"parameter": "voltage"}]
    finally:
        store.close()
