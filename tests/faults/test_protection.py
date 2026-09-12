"""WP05 Task 8 fault tests: protection, coordination, truthful terminals.

Proves the trust surface of the run lifecycle: the protective response fires
on condition violations from acceptance onward, the protection deadline is
fixed at first entry and never extended, uncertainty is never dressed up as a
pass, cancellation still completes the safe transition, and a crashed
coordinator's run is recovered as interrupted with replay-suppressing
occurrence identities. Every terminal record is validated against the
vendored run-record schema, not hand-rolled shape checks.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from benchweave.control.binding import resolve_binding
from benchweave.control.clocking import TestClock
from benchweave.control.coordinator import RunCoordinator
from benchweave.control.documents import AdmittedDocuments, admit_documents
from benchweave.control.executor import Executor
from benchweave.control.protection import ProtectionEngine, read_signal_values
from benchweave.host.plugin import DevicePlugin
from benchweave.host.services import HostServices
from benchweave.host.types import (
    DispatchState,
    ErrorCode,
    OperationRequest,
    OperationResult,
    OperationStatus,
    OperationVerb,
    Quality,
    Reading,
    ReadingSource,
)
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
PLUGINS_ROOT = ROOT / "plugins"
RUN_RECORD_SCHEMA = ROOT / "contracts" / "execution-v1.0.0" / "run-record.schema.json"
DESCRIPTORS = {
    "psu": FIXTURES / "descriptor-sim-psu.json",
    "controller": FIXTURES / "descriptor-sim-controller.json",
}
PSU_OUTPUT = "otdp.dc_psu.output/1.0.0"
PSU_MEASURE = "otdp.dc_psu.measure/1.0.0"
BENCH_ID = "sim-bench"

_RECORD_VALIDATOR = Draft202012Validator(json.loads(RUN_RECORD_SCHEMA.read_text(encoding="utf-8")))


def _validate_record(record: dict[str, Any]) -> None:
    errors = sorted(_RECORD_VALIDATOR.iter_errors(record), key=lambda e: e.json_path)
    assert not errors, f"run record failed schema: {[e.message for e in errors]}"


def _admit() -> AdmittedDocuments:
    return admit_documents(
        procedure_path=FIXTURES / "procedure-voltage-check.json",
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=FIXTURES / "run-binding.json",
        commissioning_path=FIXTURES / "commissioning.json",
        descriptor_paths=DESCRIPTORS,
    )


def _load_plugin(name: str) -> ModuleType:
    path = PLUGINS_ROOT / name / "plugin.py"
    assert path.is_file(), f"plugin file missing: {path}"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _NullServices:
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


def _iso_minus_ms(stamp: str, milliseconds: int) -> str:
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (moment - timedelta(milliseconds=milliseconds)).isoformat().replace("+00:00", "Z")


def _iso_plus_ms(stamp: str, milliseconds: int) -> str:
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (moment + timedelta(milliseconds=milliseconds)).isoformat().replace("+00:00", "Z")


class _FaultPsu:
    """PSU wrapper for fault injection.

    ``force_voltage_v`` overrides reads of ``output_voltage_v`` (the value
    the monitor sees), ``stale_ms`` backdates those readings' observed_at so
    freshness fails, ``enable_sets_force`` arms a fault the moment the body
    enables output, and ``clear_force_on_disable`` makes the wrapper reflect
    the protection disable (or refuse to, for persistent faults).
    """

    def __init__(self, inner: DevicePlugin, now_fn: Callable[[], str]) -> None:
        self._inner = inner
        self._now = now_fn
        self.force_voltage_v: float | None = None
        self.stale_ms: int = 0
        self.future_ms: int = 0
        self.buffer_age_ms: int = 0
        self.enable_sets_force: float | None = None
        self.clear_force_on_disable: bool = True
        self.force_measure_voltage_v: float | None = None
        self.fail_configure_not_dispatched = False
        #: Reads of output_voltage_v serving a forced 5.9 V at exactly these
        #: zero-based read indices (one-poll transients for verify testing).
        self.bad_read_indices: set[int] = set()
        self.read_index = 0
        #: Measure returns an UNKNOWN dispatch AND arms the voltage fault
        #: (uncertain body + post-body condition violation).
        self.unknown_measure_and_trip = False
        #: A successful measure both tampers the voltage dataset (assertion
        #: failure) and arms the voltage fault (post-body violation).
        self.trip_after_measure = False
        self.on_invoke: Callable[[OperationRequest], None] | None = None
        self.dispatches: list[OperationRequest] = []

    @property
    def simulation(self) -> Any:
        return self._inner.simulation

    def plugin_open(self, services: HostServices) -> None:
        self._inner.plugin_open(services)

    def plugin_close(self) -> None:
        self._inner.plugin_close()

    def body_dispatches(self) -> list[OperationRequest]:
        return [r for r in self.dispatches if str(r.operation_id).startswith("op:")]

    def disable_dispatches(self) -> list[OperationRequest]:
        return [
            r
            for r in self.dispatches
            if r.verb is OperationVerb.INVOKE
            and r.arguments.get("action_id") == PSU_OUTPUT
            and r.arguments.get("input", {}).get("enabled") is False
        ]

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        if (
            request.verb is OperationVerb.READ
            and request.arguments.get("parameter") == "output_voltage_v"
        ):
            index = self.read_index
            self.read_index += 1
            forced = self.force_voltage_v
            if index in self.bad_read_indices:
                forced = 5.9  # exactly one dirty poll
            self.dispatches.append(request)
            if forced is not None:
                observed = self._now()
                if self.stale_ms:
                    observed = _iso_minus_ms(observed, self.stale_ms)
                if self.future_ms:
                    observed = _iso_plus_ms(observed, self.future_ms)
                return OperationResult.ok(
                    request.operation_id,
                    request.verb,
                    Reading(
                        parameter="output_voltage_v",
                        value=forced,
                        unit="V",
                        observed_at=observed,
                        age_ms=self.buffer_age_ms,
                        quality=Quality.VALID,
                        source=ReadingSource.DEVICE,
                    ),
                )
        self.dispatches.append(request)
        if (
            self.fail_configure_not_dispatched
            and request.verb is OperationVerb.INVOKE
            and str(request.arguments.get("action_id")).startswith("otdp.dc_psu.configure")
        ):
            return OperationResult.failure(
                request.operation_id,
                request.verb,
                code=ErrorCode.DEVICE_REJECTED,
                message="fault injected: configure rejected before dispatch",
                dispatch_state=DispatchState.NOT_DISPATCHED,
            )
        if (
            self.unknown_measure_and_trip
            and request.verb is OperationVerb.INVOKE
            and str(request.arguments.get("action_id")) == PSU_MEASURE
        ):
            self.force_voltage_v = 5.9  # the condition violates right after
            return OperationResult.indeterminate(
                request.operation_id,
                request.verb,
                code=ErrorCode.TIMEOUT,
                message="fault injected: dispatch state unknown",
            )
        result = self._inner.dispatch(request, deadline_ns=deadline_ns)
        if request.verb is OperationVerb.INVOKE and self.on_invoke is not None:
            self.on_invoke(request)
        self._manage_force(request, result)
        return result

    def _manage_force(self, request: OperationRequest, result: OperationResult) -> None:
        if request.verb is not OperationVerb.INVOKE or result.status is not OperationStatus.OK:
            return
        action_id = str(request.arguments.get("action_id"))
        if action_id == PSU_OUTPUT:
            enabled = request.arguments.get("input", {}).get("enabled")
            if enabled is False and self.clear_force_on_disable:
                self.force_voltage_v = None
            elif enabled is True and self.enable_sets_force is not None:
                self.force_voltage_v = self.enable_sets_force
        elif action_id == PSU_MEASURE:
            if self.trip_after_measure:
                self.force_voltage_v = 5.9  # violates the condition post-body
            if self.force_measure_voltage_v is not None and isinstance(result.data, dict):
                dataset = result.data.get("result")
                if isinstance(dataset, dict):
                    for variable in dataset.get("variables", []):
                        if variable.get("id") == "voltage":
                            variable["values"] = [self.force_measure_voltage_v]


def _plugins(clock: TestClock) -> dict[str, DevicePlugin]:
    plugins: dict[str, DevicePlugin] = {}
    for device_id, name in (("psu", "sim_psu"), ("controller", "sim_controller")):
        plugin = _load_plugin(name).create_plugin(
            now_fn=clock.now_iso, monotonic_ns_fn=clock.now_ns
        )
        plugin.plugin_open(_NullServices())
        plugins[device_id] = plugin
    return plugins


def _harness(
    tmp_path: Path,
) -> tuple[TestClock, _FaultPsu, RunCoordinator, Store, AdmittedDocuments]:
    clock = TestClock()
    plugins = _plugins(clock)
    fault = _FaultPsu(plugins["psu"], clock.now_iso)
    plugins["psu"] = fault
    store = Store.open(tmp_path / "state.db")
    docs = _admit()
    coordinator = RunCoordinator(store, plugins, clock, clock, docs)
    return clock, fault, coordinator, store, docs


def _assert_monotonic_events(store: Store, run_id: str) -> list[dict[str, Any]]:
    events = store.read_events(f"run:{run_id}")
    assert events, "event stream must be non-empty"
    sequences = [int(event["sequence"]) for event in events]
    assert sequences == sorted(sequences) and len(set(sequences)) == len(sequences)
    return events


# --- trip ---------------------------------------------------------------------


def test_condition_violation_trips_and_safe_transition_verifies(tmp_path: Path) -> None:
    """Voltage escaping the continuous condition trips the run; protection lands."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.enable_sets_force = 5.9  # bench reads 5.9 V once the body enables output

    record = coordinator.start_run("run-trip", "principal-a")

    assert record["body_outcome"] == "tripped"
    assert record["safe_state"] == "verified"
    assert record["outcome"] == "tripped"
    assert any("dut-voltage-bounds" in reason for reason in record["reasons"])
    assert fault.disable_dispatches(), "the safe action must have been dispatched"
    _validate_record(record)
    run = store.get_run("run-trip")
    assert run is not None
    assert run["terminal"] == record
    _assert_monotonic_events(store, "run-trip")


def test_stale_signal_trips_protectively(tmp_path: Path) -> None:
    """A signal past its bench max_age is invalid evidence and trips the run."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.force_voltage_v = 0.0
    fault.stale_ms = 600  # max_age_ms is 500

    record = coordinator.start_run("run-stale", "principal-a")

    assert record["body_outcome"] == "tripped"
    assert any("signal_invalid" in reason for reason in record["reasons"])
    assert record["safe_state"] == "verified"
    _validate_record(record)


def test_future_stamped_signal_trips_protectively(tmp_path: Path) -> None:
    """A future-stamped observed_at is impossible timing, not freshness (F2).

    The host cannot compute a negative age and call the signal maximally
    fresh: unknown timing cannot satisfy a finite max_age_ms (§4), so the
    signal is INVALID and the protective response fires exactly as for a
    stale one.
    """
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.force_voltage_v = 0.0  # in bounds: only the impossible timing trips
    fault.future_ms = 600

    record = coordinator.start_run("run-future", "principal-a")

    assert record["body_outcome"] == "tripped"
    assert any("signal_invalid" in reason for reason in record["reasons"])
    assert record["safe_state"] == "verified"
    _validate_record(record)


def test_read_signal_values_future_stamp_is_invalid_not_fresh() -> None:
    """Unit pin: a future stamp invalidates; it never reads as age 0."""
    clock = TestClock()
    plugins = _plugins(clock)
    fault = _FaultPsu(plugins["psu"], clock.now_iso)
    fault.force_voltage_v = 0.0
    fault.future_ms = 600
    plugins["psu"] = fault
    docs = _admit()

    snapshot = read_signal_values(
        plugins,
        docs.bench,
        deadline_ns=clock.now_ns() + 1_000_000,
        wall_now=clock.now_iso(),
    )

    assert snapshot["dut-voltage"].valid is False
    assert snapshot["dut-current"].valid is True  # the unforced signal stays fresh


def test_read_signal_values_device_reported_age_governs() -> None:
    """Unit pin: effective age is the older of host-computed and device age.

    Host receive time alone cannot refresh an old device buffer: a Reading
    reporting 800 ms of buffer age against a host-computed 0 is stale at
    800 ms (max_age_ms is 500).
    """
    clock = TestClock()
    plugins = _plugins(clock)
    fault = _FaultPsu(plugins["psu"], clock.now_iso)
    fault.force_voltage_v = 0.0
    fault.buffer_age_ms = 800
    plugins["psu"] = fault
    docs = _admit()

    stale = read_signal_values(
        plugins,
        docs.bench,
        deadline_ns=clock.now_ns() + 1_000_000,
        wall_now=clock.now_iso(),
    )
    assert stale["dut-voltage"].age_ms == 800  # the device age governs
    assert stale["dut-voltage"].valid is False

    fault.buffer_age_ms = 0  # an honest device buffer keeps host-computed age
    fresh = read_signal_values(
        plugins,
        docs.bench,
        deadline_ns=clock.now_ns() + 1_000_000,
        wall_now=clock.now_iso(),
    )
    assert fresh["dut-voltage"].age_ms == 0
    assert fresh["dut-voltage"].valid is True


def test_monitor_from_acceptance_trips_before_any_body_dispatch(tmp_path: Path) -> None:
    """A pre-energised violated condition stops the body at its first dispatch."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.force_voltage_v = 5.9  # bad before the run even starts

    record = coordinator.start_run("run-early", "principal-a")

    assert fault.body_dispatches() == [], "no body dispatch may reach the device"
    assert record["body_outcome"] == "tripped"
    assert fault.disable_dispatches(), "protection still ran"
    _validate_record(record)


# --- fixed protection deadline -------------------------------------------------


def test_second_fault_escalates_reasons_and_never_extends_deadline(tmp_path: Path) -> None:
    """The protection deadline is captured once; later faults only append."""
    clock = TestClock()
    plugins = _plugins(clock)
    fault = _FaultPsu(plugins["psu"], clock.now_iso)
    plugins["psu"] = fault
    docs = _admit()
    fault.force_voltage_v = 5.9
    fault.clear_force_on_disable = False  # verification can never converge
    engine = ProtectionEngine(plugins, docs.policy, docs.bench, clock, clock)

    entered_ns = clock.now_ns()
    first = engine.enter(["fault-1"], entered_ns)

    max_protection_ns = int(docs.policy["safe_transition"]["max_duration_ms"]) * 1_000_000
    assert engine.protection_deadline_ns == entered_ns + max_protection_ns  # captured once
    assert first.safe_state == "unknown"
    assert clock.now_ns() == entered_ns + max_protection_ns  # the budget fully lapsed

    second = engine.enter(["fault-2"], clock.now_ns())
    assert engine.protection_deadline_ns == entered_ns + max_protection_ns  # never extended
    assert "fault-1" in second.reasons and "fault-2" in second.reasons
    assert second.safe_state == "unknown"


def test_failed_safe_action_does_not_suppress_remaining_actions(tmp_path: Path) -> None:
    """Forge F3: one failing safe action never suppresses the rest.

    The mutated policy carries two safe actions whose FIRST targets an
    unreachable device: the failure is recorded as a reason, the second
    action still dispatches IN ORDER, and safe_state reflects only the
    verify conjunction outcome — never the action failure.
    """
    clock = TestClock()
    plugins = _plugins(clock)
    fault = _FaultPsu(plugins["psu"], clock.now_iso)
    plugins["psu"] = fault
    docs = _admit()
    policy = copy.deepcopy(docs.policy)
    disable = dict(policy["safe_transition"]["actions"][0])
    policy["safe_transition"]["actions"] = [
        {  # first in order, and it cannot reach any device
            "id": "dead-relay",
            "device_id": "ghost-relay",
            "kind": "invoke",
            "action_id": PSU_OUTPUT,
            "input": {"channel": "ch1", "enabled": False},
            "timeout_ms": 500,
        },
        disable,
    ]
    engine = ProtectionEngine(plugins, policy, docs.bench, clock, clock)

    result = engine.enter(["fault-1"], clock.now_ns())

    assert [action["id"] for action in result.actions] == ["dead-relay", "disable"]
    assert result.actions[0]["status"] == "error"
    assert result.actions[0]["error"] == "unknown_device"
    assert result.actions[1]["status"] == "ok"
    assert "safe_action dead-relay: error" in result.reasons
    assert "fault-1" in result.reasons
    # The verify conjunction — not the action failure — decides safety.
    assert result.safe_state == "verified"
    assert fault.disable_dispatches(), "the second action physically dispatched"


def test_safe_action_beyond_device_bound_is_rejected_not_clamped() -> None:
    """A safe action whose value exceeds a device bound is rejected, never clamped.

    Safe actions carry literal commissioned arguments and dispatch without
    allow-rule re-evaluation — but the device's own hard bounds still apply.
    The engine records the rejection as a reason, the value reaches the
    device UNCHANGED (no silent clamping to the bound), and verification
    still decides the safe state on its own. This also pins the write-kind
    safe action request path, which only invoke-kind actions had covered.
    """
    clock = TestClock()
    plugins = _plugins(clock)
    fault = _FaultPsu(plugins["psu"], clock.now_iso)
    plugins["psu"] = fault
    docs = _admit()
    policy = copy.deepcopy(docs.policy)
    policy["safe_transition"]["actions"] = [
        {
            "id": "over-voltage-write",
            "device_id": "psu",
            "kind": "write",
            "parameter": "voltage_setpoint_v",
            "value": 999.0,  # beyond the simulated PSU's 30 V hard bound
            "timeout_ms": 500,
        }
    ]
    engine = ProtectionEngine(plugins, policy, docs.bench, clock, clock)

    result = engine.enter(["fault-1"], clock.now_ns())

    assert [action["id"] for action in result.actions] == ["over-voltage-write"]
    assert result.actions[0]["status"] == "error"
    error = result.actions[0]["error"]
    assert error is not None and "DEVICE_REJECTED" in error
    assert "safe_action over-voltage-write: error" in result.reasons
    # No clamping: the device saw the commissioned literal, out of bounds.
    writes = [
        request
        for request in fault.dispatches
        if request.verb is OperationVerb.WRITE
        and request.arguments.get("parameter") == "voltage_setpoint_v"
    ]
    assert len(writes) == 1
    assert writes[0].arguments["value"] == 999.0
    # The verify conjunction — not the action failure — decides safety:
    # output was never enabled, so voltage reads 0 V and verifies.
    assert result.safe_state == "verified"


def test_budget_lapse_is_outcome_unknown_despite_terminal_body(tmp_path: Path) -> None:
    """An unverifiable safe condition forces outcome_unknown even on a clean body."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.enable_sets_force = 5.9
    fault.clear_force_on_disable = False  # disable lands, the fault persists

    record = coordinator.start_run("run-lapse", "principal-a")

    # The body itself trips (the fault is live from enable), protection's
    # disable cannot clear it, verification lapses: uncertainty wins.
    assert record["safe_state"] == "unknown"
    assert record["outcome"] == "outcome_unknown"
    assert fault.disable_dispatches(), "the transition was still attempted"
    _validate_record(record)


def test_mid_window_transient_resets_the_stability_window(tmp_path: Path) -> None:
    """One dirty poll inside the window resets stability; two endpoints lie.

    Poll cadence 50 ms, stable_for 100 ms. The conjunction is dirty at
    exactly read #2 (t+100 ms, inside the first window): a continuously
    sampled window must reset and verify only at t+250 ms — never at the
    two-endpoint t+100 ms a blind wait would report.
    """
    clock = TestClock()
    plugins = _plugins(clock)
    fault = _FaultPsu(plugins["psu"], clock.now_iso)
    plugins["psu"] = fault
    docs = _admit()
    fault.bad_read_indices = {2}
    engine = ProtectionEngine(plugins, docs.policy, docs.bench, clock, clock)

    entered_ns = clock.now_ns()
    result = engine.enter(["fault-1"], entered_ns)

    assert result.safe_state == "verified"
    assert clock.now_ns() == entered_ns + 250_000_000  # reset cost a full window


def test_mid_window_transient_then_budget_lapse_is_unknown(tmp_path: Path) -> None:
    """A transient whose reset outruns the budget ends unknown, not verified.

    A tighter commissioned budget (150 ms) admits the first stability window
    (clean polls at t+0/t+50) but not a second one: the dirty poll at t+100
    resets the window, the budget lapses at t+150 mid-restart, and the
    honest answer is ``unknown``.
    """
    clock = TestClock()
    plugins = _plugins(clock)
    fault = _FaultPsu(plugins["psu"], clock.now_iso)
    plugins["psu"] = fault
    docs = _admit()
    policy = copy.deepcopy(docs.policy)
    policy["safe_transition"]["max_duration_ms"] = 150
    fault.bad_read_indices = {2}  # dirty at t+100 ms, inside the first window
    engine = ProtectionEngine(plugins, policy, docs.bench, clock, clock)

    entered_ns = clock.now_ns()
    result = engine.enter(["fault-1"], entered_ns)

    assert result.safe_state == "unknown"
    assert clock.now_ns() == entered_ns + 150_000_000  # lapsed mid-restart, exactly


# --- cancel ---------------------------------------------------------------------


def test_cancel_still_completes_the_safe_transition(tmp_path: Path) -> None:
    """Cancellation ends the body but never suppresses protection."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)

    def inject_cancel(request: OperationRequest) -> None:
        coordinator.cancel("run-cancel", "principal-a")

    fault.on_invoke = inject_cancel

    record = coordinator.start_run("run-cancel", "principal-a")

    assert record["body_outcome"] == "cancelled"
    assert record["outcome"] == "cancelled"
    assert record["safe_state"] == "verified"  # the transition still ran
    assert fault.disable_dispatches()
    _validate_record(record)
    events = _assert_monotonic_events(store, "run-cancel")
    blocked = [e for e in events if e.get("status") == "cancelled"]
    assert blocked, "the blocked step event carries the honest cancelled bucket"


# --- timeout ----------------------------------------------------------------------


def test_body_deadline_expiry_times_out_but_protection_verifies(tmp_path: Path) -> None:
    """A lapsed body budget ends the body timed_out; the safe state still verifies."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)

    def advance_past_body_deadline(request: OperationRequest) -> None:
        if str(request.operation_id).startswith("op:"):  # body dispatches only
            clock.advance(9_000_000_000)  # max_body_ms is 8000

    fault.on_invoke = advance_past_body_deadline

    record = coordinator.start_run("run-timeout", "principal-a")

    assert record["body_outcome"] == "timed_out"
    assert record["safe_state"] == "verified"
    assert record["outcome"] == "timed_out"
    assert fault.disable_dispatches()
    _validate_record(record)


# --- truthful terminals ------------------------------------------------------------


def test_false_assertion_is_assertion_failed_with_verified_safety(tmp_path: Path) -> None:
    """§5 row: a false assert ends the body assertion_failed; safety verifies."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.force_measure_voltage_v = 4.0  # the measured evidence escapes [4.9, 5.1]

    record = coordinator.start_run("run-assert", "principal-a")

    assert record["body_outcome"] == "assertion_failed"
    assert record["safe_state"] == "verified"
    assert record["outcome"] == "assertion_failed"
    assert any("escapes" in reason for reason in record["reasons"])
    assert fault.disable_dispatches()
    _validate_record(record)


def test_pre_dispatch_error_is_execution_error_with_verified_safety(tmp_path: Path) -> None:
    """§5 row: a pre-dispatch device rejection is execution_error, not unknown."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.fail_configure_not_dispatched = True

    record = coordinator.start_run("run-execerr", "principal-a")

    assert record["body_outcome"] == "execution_error"
    assert record["safe_state"] == "verified"
    assert record["outcome"] == "execution_error"
    assert any("fault injected" in reason for reason in record["reasons"])
    assert fault.disable_dispatches()
    _validate_record(record)


def test_truthful_passed_run_record_validates(tmp_path: Path) -> None:
    """A normal full run reports passed only with a verified safe state."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)

    record = coordinator.start_run("run-pass", "principal-a")

    assert record["body_outcome"] == "completed"
    assert record["safe_state"] == "verified"
    assert record["outcome"] == "passed"
    assert record["reasons"] == []
    assert record["principal_id"] == "principal-a"
    started = datetime.fromisoformat(record["started_at"].replace("Z", "+00:00"))
    ended = datetime.fromisoformat(record["ended_at"].replace("Z", "+00:00"))
    assert started < ended
    _validate_record(record)
    run = store.get_run("run-pass")
    assert run is not None
    assert run["terminal"] == record
    events = _assert_monotonic_events(store, "run-pass")
    assert len(events) == 21  # the full eight-kind body
    assert store.get_active_lease(BENCH_ID) is None


def test_no_false_passed_when_verification_fails(tmp_path: Path) -> None:
    """A completed body can never report passed while safety is unverifiable."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)

    def arm_during_disable(request: OperationRequest) -> None:
        if (
            request.verb is OperationVerb.INVOKE
            and request.arguments.get("action_id") == PSU_OUTPUT
            and request.arguments.get("input", {}).get("enabled") is False
        ):
            fault.force_voltage_v = 5.9  # the bench goes bad exactly as we protect
            fault.clear_force_on_disable = False

    fault.on_invoke = arm_during_disable

    record = coordinator.start_run("run-nopass", "principal-a")

    assert record["body_outcome"] == "completed"
    assert record["safe_state"] == "unknown"
    assert record["outcome"] == "outcome_unknown"
    assert any("dut-voltage-bounds" in reason for reason in record["reasons"])
    _validate_record(record)


def test_uncertain_body_is_never_reclassified_to_tripped(tmp_path: Path) -> None:
    """An uncertain dispatch stays outcome_unknown even with a live violation.

    The measure dispatch returns UNKNOWN (uncertain, never retried) and the
    voltage condition violates right after it. The monitor's cause may not
    downgrade the body: the record keeps the executor's uncertainty reasons
    AND appends the violation, and the outcome stays ``outcome_unknown``.
    """
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.unknown_measure_and_trip = True

    record = coordinator.start_run("run-uncertain", "principal-a")

    assert record["body_outcome"] == "outcome_unknown"
    assert record["outcome"] == "outcome_unknown"
    assert any("outcome uncertain" in reason for reason in record["reasons"])
    assert any("dut-voltage-bounds" in reason for reason in record["reasons"])
    assert fault.disable_dispatches()
    _validate_record(record)


def test_assertion_failed_body_is_never_reclassified_to_tripped(tmp_path: Path) -> None:
    """A failed assertion keeps its §5 row; the violation rides as a reason.

    The measure dataset is tampered so ``check`` fails honestly while the
    voltage condition violates at the same moment. The body ended on its
    own assertion failure — no monitor block reclassifies it — so the
    terminal is ``assertion_failed`` with both reasons retained.
    """
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.force_measure_voltage_v = 4.0
    fault.trip_after_measure = True

    record = coordinator.start_run("run-assert-trip", "principal-a")

    assert record["body_outcome"] == "assertion_failed"
    assert record["outcome"] == "assertion_failed"
    assert any("escapes" in reason for reason in record["reasons"])
    assert any("dut-voltage-bounds" in reason for reason in record["reasons"])
    assert fault.disable_dispatches()
    _validate_record(record)


# --- lease lifecycle ----------------------------------------------------------------


def test_lease_released_after_terminal_and_bench_readmits(tmp_path: Path) -> None:
    """After a terminal record the bench lease is free; a new request admits."""
    clock, fault, coordinator, store, docs = _harness(tmp_path)
    first = coordinator.start_run("run-1", "principal-a")
    assert first["outcome"] == "passed"
    assert store.get_active_lease(BENCH_ID) is None

    # A second admission needs a fresh request id: copy the binding, re-pin nothing
    # (no document pins the binding itself), and admit the new set.
    binding = json.loads((FIXTURES / "run-binding.json").read_text())
    binding["request_id"] = "req-voltage-check-2"
    binding_path = tmp_path / "run-binding-2.json"
    binding_path.write_text(json.dumps(binding, indent=2))
    docs2 = admit_documents(
        procedure_path=FIXTURES / "procedure-voltage-check.json",
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=binding_path,
        commissioning_path=FIXTURES / "commissioning.json",
        descriptor_paths=DESCRIPTORS,
    )
    clock2 = TestClock()
    plugins2 = _plugins(clock2)
    coordinator2 = RunCoordinator(store, plugins2, clock2, clock2, docs2)

    second = coordinator2.start_run("run-2", "principal-b")

    assert second["outcome"] == "passed"
    assert store.get_active_lease(BENCH_ID) is None
    _validate_record(second)


# --- restart recovery ----------------------------------------------------------------


def test_crashed_run_recovers_interrupted_and_suppresses_replay(tmp_path: Path) -> None:
    """A run left un-terminalised recovers as interrupted; ids are never reused."""
    clock, fault, coordinator_a, store_a, docs = _harness(tmp_path)
    assert fault.force_voltage_v is None

    # Coordinator A crashes between create_run and finalize_run: drive the
    # internal pipeline through the body + durable events, then abandon it.
    prepared = coordinator_a._prepare_run("run-1", "principal-a")
    coordinator_a._run_and_record(prepared)
    # (no protection, no terminal record, no lease release — the process died)

    # Coordinator B opens the same store file and recovers.
    store_b = Store.open(tmp_path / "state.db")
    clock_b = TestClock()
    plugins_b = _plugins(clock_b)
    coordinator_b = RunCoordinator(store_b, plugins_b, clock_b, clock_b, docs)
    recovered = coordinator_b.recover_interrupted()

    assert recovered == ["run-1"]
    run = store_b.get_run("run-1")
    assert run is not None
    terminal = run["terminal"]
    assert terminal is not None
    assert terminal["body_outcome"] == "interrupted"
    assert terminal["safe_state"] == "unknown"
    assert terminal["outcome"] == "interrupted"
    _validate_record(terminal)
    assert store_b.get_active_lease(BENCH_ID) is None, "the dead lease is released"

    # The same run_id is refused — run ids are never reusable.
    with pytest.raises(ValueError):
        coordinator_b.start_run("run-1", "principal-a")
    # A repeated recovery sweep is idempotent.
    assert coordinator_b.recover_interrupted() == []

    # Occurrence identities from the crashed run suppress replay: re-running
    # the body through an executor over the rebuilt ledger dispatches nothing.
    assert ("run-1", "configure", ()) in coordinator_b.occurrence_ledger
    recorder = _FaultPsu(plugins_b["psu"], clock_b.now_iso)
    plugins_b["psu"] = recorder
    executor = Executor(
        plugins=plugins_b,
        binding=resolve_binding(docs),
        policy=docs.policy,
        clock=clock_b,
        wall=clock_b,
        occurrence_ledger=coordinator_b.occurrence_ledger,
    )
    replay = executor.run_body(docs.procedure, "run-1", clock_b.now_ns() + 10_000_000_000)
    assert recorder.dispatches == [], "suppressed occurrences must not re-dispatch"
    assert replay.step_events, "the replay re-walks the recorded occurrences"


def test_error_codes_surface_in_events_and_terminal(tmp_path: Path) -> None:
    """Smoke: the vendored schema accepts every record shape this suite makes."""
    clock, fault, coordinator, store, _ = _harness(tmp_path)
    fault.enable_sets_force = 5.9
    record = coordinator.start_run("run-smoke", "principal-a")
    _validate_record(record)
    run = store.get_run("run-smoke")
    assert run is not None
    assert run["terminal"] == record
