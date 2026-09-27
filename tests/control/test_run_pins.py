"""The run-evidence surface of the per-device pins (issue #217, VR-46).

Run evidence records each device's validated versions and conformance
class. The execution run-record document itself is schema-frozen
(``additionalProperties: false``, closed ``{id, version, sha256}``
evidence refs — an interface/corpus motion this slice does not make), so
the per-device pins land in the RUN-SCOPOPED EVENT STREAM — the durable
``run:{run_id}`` stream whose digest already rides the terminal record as
the ``events:{run_id}`` evidence ref. A ``devices_pinned`` event is the
stream's FIRST record, appended at run preparation: durable before the
body executes, so a crash mid-body still leaves the pins on the record.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from test_documents_perpin import _admit, _controller_document, _psu_document

from benchweave.control.clocking import TestClock
from benchweave.control.coordinator import RunCoordinator
from benchweave.host.plugin import DevicePlugin
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
PLUGINS_ROOT = ROOT / "plugins" / "benchweave"


class _NullServices:
    """The faults harness's null host surface (test_protection's shape)."""

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

    def issue_token(self, action_id: str, fields: list[str]) -> dict[str, Any]:
        return {field: "issued" for field in fields}

    def now_iso(self) -> str:
        return "2026-09-27T00:00:00Z"


def _load_plugin(name: str) -> ModuleType:
    path = PLUGINS_ROOT / name / "src" / f"benchweave_{name}" / "plugin.py"
    spec = importlib.util.spec_from_file_location(f"benchweave_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _plugins(clock: TestClock) -> dict[str, DevicePlugin]:
    plugins: dict[str, DevicePlugin] = {}
    for device_id, name in (("psu", "sim_psu"), ("controller", "sim_controller")):
        plugin = _load_plugin(name).create_plugin(
            now_fn=clock.now_iso, monotonic_ns_fn=clock.now_ns
        )
        plugin.plugin_open(_NullServices())
        plugins[device_id] = plugin
    return plugins


def test_c1_the_run_record_carries_both_pins_and_classes(tmp_path: Path) -> None:
    """VR-46's mixed-version arm: a bench whose psu pins 0.2.0 and whose
    controller pins 0.2.2 runs, and the run's evidence stream records BOTH
    validated versions with their conformance classes — the first event on
    the stream, durable before the body's step events."""
    psu = _psu_document()
    psu["otdp_version"] = "0.2.0"
    controller = _controller_document()
    assert controller["otdp_version"] == "0.2.2"
    docs = _admit(tmp_path, {"psu": psu, "controller": controller})

    clock = TestClock()
    store = Store.open(tmp_path / "state.db")
    coordinator = RunCoordinator(store, _plugins(clock), clock, clock, docs)
    record = coordinator.start_run("run-mixed-pins", "principal-a")

    assert record["outcome"] == "passed", record
    events = store.read_events("run:run-mixed-pins")
    assert events, "run stream must be non-empty"
    first = events[0]
    assert first.get("kind") == "devices_pinned", first
    devices = first["devices"]
    assert devices["psu"] == {
        "otdp_version": "0.2.0",
        "conformance": "conforming",
    }
    assert devices["controller"] == {
        "otdp_version": "0.2.2",
        "conformance": "conforming",
    }


def test_the_nonconforming_class_and_ack_ride_the_run_record(tmp_path: Path) -> None:
    """C4's KILL arm on the run surface: an acknowledged non-conforming
    device's run records the class AND the recorded acknowledgement — never
    silently conforming. Runs on the execution/0.1.0 composition (the only
    rowless bench in the seed corpus; see test_documents_cross_constraint)."""
    psu = _psu_document()
    psu["otdp_version"] = "0.1.2"
    docs = _admit(
        tmp_path,
        {"psu": psu},
        execution="0.1.0",
        operator_acknowledgements={"psu": "0.1.2"},
    )

    clock = TestClock()
    store = Store.open(tmp_path / "state.db")
    coordinator = RunCoordinator(store, _plugins(clock), clock, clock, docs)
    record = coordinator.start_run("run-nonconforming", "principal-a")

    assert record["outcome"] == "passed", record
    first = store.read_events("run:run-nonconforming")[0]
    psu_view = first["devices"]["psu"]
    assert psu_view["otdp_version"] == "0.1.2"
    assert psu_view["conformance"] == "non-conforming"
    assert psu_view["acknowledgement"] == {
        "otdp_version": "0.1.2",
        "recorded_at": None,
    }
    # The other device stays conforming with no acknowledgement record.
    assert first["devices"]["controller"]["conformance"] == "conforming"
    assert "acknowledgement" not in first["devices"]["controller"]


def test_the_yank_warning_rides_the_run_record(tmp_path: Path) -> None:
    """A yanked pin's run records the deprecation note naming the move-to
    (the Q10 ruling's warning channel — recorded evidence, not a lost
    warnings.warn)."""
    psu = _psu_document()
    psu["otdp_version"] = "0.2.1"
    docs = _admit(tmp_path, {"psu": psu})

    clock = TestClock()
    store = Store.open(tmp_path / "state.db")
    coordinator = RunCoordinator(store, _plugins(clock), clock, clock, docs)
    coordinator.start_run("run-yanked", "principal-a")

    first = store.read_events("run:run-yanked")[0]
    psu_view = first["devices"]["psu"]
    assert psu_view["otdp_version"] == "0.2.1"
    assert psu_view["conformance"] == "conforming"
    assert "yanked" in psu_view["deprecation"]
    assert "0.2.2" in psu_view["deprecation"]


def test_the_pins_event_is_digest_covered_run_evidence(tmp_path: Path) -> None:
    """The event is not a side channel: it sits on the stream the terminal
    record pins by digest (``events:{run_id}``), so the pins are part of
    the run's evidence identity."""
    import hashlib

    from benchweave.control.executor import canonical_json

    psu = _psu_document()
    psu["otdp_version"] = "0.2.0"
    docs = _admit(tmp_path, {"psu": psu})

    clock = TestClock()
    store = Store.open(tmp_path / "state.db")
    coordinator = RunCoordinator(store, _plugins(clock), clock, clock, docs)
    record = coordinator.start_run("run-digest", "principal-a")

    events_ref = next(
        ref for ref in record["evidence_refs"] if ref["id"] == "events:run-digest"
    )
    digest = hashlib.sha256(
        canonical_json(store.read_events("run:run-digest")).encode("utf-8")
    ).hexdigest()
    assert events_ref["sha256"] == digest
    assert store.read_events("run:run-digest")[0]["kind"] == "devices_pinned"


# --- the API-view surface (VR-16, the D4-sanctioned channel) ----------------------


def test_the_api_view_logs_a_nonconforming_stored_device(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VR-16's API-view arm: a STORED device whose raw descriptor pins a
    non-conforming version surfaces through the projection's server-side
    log (the wire's device object is contract-frozen — interface 0.1.0's
    closed def; the wire field lands with the interface lane, disclosed).
    The wire object itself stays exactly the contract shape."""
    import logging

    from benchweave.interfaces.operations import Operations

    raw = _psu_document()
    raw["otdp_version"] = "0.1.2"
    row = {
        "device_id": "psu",
        "generation": 1,
        "profiles_json": "[]",
        "descriptor_json": json.dumps(raw),
        "identity_state": "matched",
        "licence": "proprietary",
        "updated_at": "2026-09-27T00:00:00Z",
    }
    seam = object.__new__(Operations)  # the projection is pure over ``row``
    with caplog.at_level(logging.WARNING, logger="benchweave.interfaces.operations"):
        view = seam._device_projection(row)
    assert any(
        "device_conformance_mismatch" in record.message and "0.1.2" in record.message
        for record in caplog.records
    ), [record.message for record in caplog.records]
    # The wire object stays exactly the contract's closed device shape.
    assert set(view) == {
        "device_id",
        "generation",
        "profiles",
        "descriptor",
        "identity_state",
    }
    assert set(view["descriptor"]) == {"id", "version", "sha256"}


def test_a_conforming_stored_device_logs_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from benchweave.interfaces.operations import Operations

    row = {
        "device_id": "psu",
        "generation": 1,
        "profiles_json": "[]",
        "descriptor_json": json.dumps(_psu_document()),
        "identity_state": "matched",
        "licence": "proprietary",
        "updated_at": "2026-09-27T00:00:00Z",
    }
    seam = object.__new__(Operations)  # the projection is pure over ``row``
    with caplog.at_level(logging.WARNING, logger="benchweave.interfaces.operations"):
        seam._device_projection(row)
    assert not [
        record
        for record in caplog.records
        if "device_conformance_mismatch" in record.message
    ]
