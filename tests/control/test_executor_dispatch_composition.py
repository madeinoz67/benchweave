"""Issue #73: the permanent dispatch-state composition pin.

The #66 increment (PR #72) taught sim_psu/sim_controller to report
``dispatch_state: DISPATCHED`` on post-dispatch device-state refusals, and
its refute lane proved end-to-end — there only — that ``Executor._dispatch``
composes with that posture: a NOT_DISPATCHED failure ends the body
``execution_error`` and any dispatched failure ends it ``outcome_unknown``,
so a post-dispatch refusal can never launder an outcome-uncertain step into
a clean pre-dispatch error (A06). The probe died with the branch; the
doctrine was left unpinned. This module is the pin, and it exercises the
composition through the real machinery — ``RunCoordinator`` over the
admitted fixture graph, the real ``Executor``, the real sim_psu plugin and
a real ``Store`` — never the mapping function in isolation.

Legs (one admitted procedure each; the body ends at the first failure):

- pre-dispatch: a malformed invoke input refused by input validation
  (INVALID_ARGUMENT, NOT_DISPATCHED) — terminal ``execution_error``.
- post-dispatch: a well-typed input the device itself refuses after
  dispatch (DEVICE_REJECTED, DISPATCHED) — terminal ``outcome_unknown``
  with the dispatch state recorded in the reasons, even though the safe
  transition verifies (uncertainty is never erased by later safety).

Discrimination provenance (RED, run before the pin was trusted): reverting
the plugin's #66 classification port to the fused NOT_DISPATCHED form
fails only the post-dispatch leg; swapping the executor mapping's two
outcomes fails both legs. Test-only increment — no plugin or fixture bytes
move on this branch.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from _harness import ROOT, readmit_mutated

from benchweave.control.clocking import TestClock
from benchweave.control.coordinator import RunCoordinator
from benchweave.host.plugin import DevicePlugin
from benchweave.state.store import Store

PLUGINS_ROOT = ROOT / "plugins"
PRINCIPAL = "principal-a"

#: A literal configure token: both legs need a token whose stored value is
#: fully controlled by the procedure text (no ``$stg_issue`` indirection —
#: the pin is about dispatch posture, not id minting).
TOKEN = "cfg-composition-pin"

_CONFIGURE = {
    "id": "configure",
    "kind": "invoke",
    "role": "supply",
    "action_id": "otdp.dc_psu.configure/1.0.0",
    "input": {
        "configuration_id": TOKEN,
        "channel": "ch1",
        "voltage_v": 5.0,
        "current_limit_a": 0.5,
        "ovp_v": 5.5,
        "ocp_a": 0.5,
    },
    "timeout_ms": 500,
}


class _NullServices:
    """Scoped-services stand-in; the sim plugins only store the reference."""

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


def _load_plugin(name: str) -> ModuleType:
    path = PLUGINS_ROOT / "benchweave" / name / "src" / f"benchweave_{name}" / "plugin.py"
    assert path.is_file(), f"plugin file missing: {path}"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
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


def _coordinated_run(
    tmp_path: Path, run_id: str, steps: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Admit the fixture graph with ``steps`` as the body, run it to a
    terminal record through the real coordinator/executor/store, and return
    the terminal record plus the durable event stream."""

    def mutate(graph: dict[str, Any]) -> None:
        graph["procedure"]["steps"] = steps

    clock = TestClock()
    plugins = _plugins(clock)
    docs = readmit_mutated(tmp_path, mutate)
    store = Store.open(tmp_path / f"state-{run_id}.db")
    try:
        coordinator = RunCoordinator(store, plugins, clock, clock, docs)
        record = coordinator.start_run(run_id, PRINCIPAL)
        events = store.read_events(f"run:{run_id}")
    finally:
        store.close()
    return record, events


def _event_for(events: list[dict[str, Any]], step_id: str) -> dict[str, Any]:
    matches = [
        event
        for event in events
        if event["kind"] == "invoke" and event["occurrence"][1] == step_id
    ]
    assert len(matches) == 1, [event["occurrence"] for event in events]
    return matches[0]


def test_pre_dispatch_input_refusal_is_execution_error(tmp_path: Path) -> None:
    """Leg (a): input validation refused before any device state was
    touched — the honest clean error, ``execution_error``, never the
    uncertain bucket."""

    steps = [
        dict(_CONFIGURE),
        {
            # A bare string where the plugin's input validation demands a
            # list: a framing failure classified by KIND (input shape, not
            # device state) as INVALID_ARGUMENT / not_dispatched — the token
            # check may run first, but a shape failure never reports as a
            # device evaluation. The descriptor's channel item patterns do
            # not type the array itself, so an admitted procedure can
            # legitimately carry it to dispatch.
            "id": "probe-framing",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.measure/1.0.0",
            "input": {"configuration_id": TOKEN, "channels": "ch1"},
            "timeout_ms": 500,
        },
    ]
    record, events = _coordinated_run(tmp_path, "run-composition-predispatch", steps)

    assert record["outcome"] == "execution_error", record["reasons"]
    assert record["body_outcome"] == "execution_error", record["reasons"]
    assert record["safe_state"] == "verified", record["reasons"]
    assert any(
        reason.startswith("step probe-framing: INVALID_ARGUMENT:")
        for reason in record["reasons"]
    ), record["reasons"]
    # The pre-dispatch reason carries no dispatch phrase: nothing was sent.
    assert not any("dispatch dispatched" in reason for reason in record["reasons"])

    event = _event_for(events, "probe-framing")
    assert event["status"] == "error"
    assert event["error_code"] == "INVALID_ARGUMENT"


def test_post_dispatch_device_refusal_is_outcome_unknown(tmp_path: Path) -> None:
    """Leg (b): a well-typed input the device evaluated and refused after
    dispatch — ``outcome_unknown`` with the dispatch state in the reasons,
    even though the safe transition then verifies."""

    steps = [
        {
            # A well-typed token that matches no stored configuration: the
            # framing is sound, so the refusal is the device's own
            # (DEVICE_REJECTED / dispatched after #66).
            "id": "probe-refused",
            "kind": "invoke",
            "role": "supply",
            "action_id": "otdp.dc_psu.measure/1.0.0",
            "input": {
                "configuration_id": "cfg-never-configured",
                "channels": ["ch1"],
            },
            "timeout_ms": 500,
        },
    ]
    record, events = _coordinated_run(tmp_path, "run-composition-postdispatch", steps)

    assert record["outcome"] == "outcome_unknown", record["reasons"]
    assert record["body_outcome"] == "outcome_unknown", record["reasons"]
    # Uncertainty is never erased by later safety: the safe state verified,
    # and the outcome stays unknown because the dispatch was uncertain.
    assert record["safe_state"] == "verified", record["reasons"]
    assert any(
        reason.startswith("step probe-refused: dispatch dispatched, outcome uncertain:")
        for reason in record["reasons"]
    ), record["reasons"]

    event = _event_for(events, "probe-refused")
    assert event["status"] == "error"
    assert event["error_code"] == "DEVICE_REJECTED"
