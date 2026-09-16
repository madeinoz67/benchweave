"""The run lifecycle coordinator: admission to truthful terminal record.

One coordinator owns one run's lifecycle end to end: idempotent request
acceptance, semantic admission, the run's own bench lease (holder
``run:{run_id}``, expiry = acceptance + max_body + max_protection), run
creation, a monitored body execution, the protective transition on ANY body
end, the terminal record, durable events, and lease release.

Monitoring runs from acceptance until the final safe condition is verified
(§7): every plugin dispatch is wrapped with a monitor tick before and after
it, and every monotonic wait is sliced at the bench poll cadence with a tick
per slice — single-threaded and deterministic on the injected clocks. A
condition violation detected during the body blocks the next dispatch with a
protective failure (the body ends ``tripped``); a requested cancellation in
the accepted-but-dispatchable window blocks it the same way (``cancelled``);
both still run the safe transition, because neither cancellation nor any
body deadline can suppress it (§5). During protection the monitor keeps
ticking and escalates new faults into the engine as additional reasons.

Terminal truth (§5, one function): the body outcome plus the verified safe
state decide the terminal outcome; an uncertain body or an unverifiable safe
state forces ``outcome_unknown`` — uncertainty is never erased by later
safety, and no report may say ``passed`` while final safety is unknown. The
body outcome is recorded independently alongside it. A monitor cause
(trip/cancel) replaces the body outcome only when its block terminated the
body; a cause observed alongside a body that ended on its own outcome is
appended to the reasons and never downgrades an uncertain or failed body.

Event aliasing: the executor returns step events whose dicts it also retains
inside the shared occurrence ledger. This coordinator treats retained
events as immutable and copies each one (``dict(event)``) when appending to
the durable stream, so the stored evidence can never be mutated through the
live ledger alias.

Restart recovery: durable runs left without a terminal record are finalised
with terminal outcome ``interrupted`` and ``unknown`` physical assurance,
and their leases released; body execution never resumes. Occurrence
identities are rebuilt from the crashed run's durable events into the
coordinator's ledger so the recorded occurrences can never dispatch again —
suppression of replay, not a promise of exactly-once physical execution.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from jsonschema import Draft202012Validator

from benchweave.control.binding import Reservation, release, reserve, resolve_binding
from benchweave.control.clocking import MonotonicClock, WallClock
from benchweave.control.documents import AdmittedDocuments
from benchweave.control.executor import Executor, Occurrence, canonical_json
from benchweave.control.policy import evaluate_conditions
from benchweave.control.protection import (
    ProtectionEngine,
    bench_poll_ns,
    read_signal_values,
)
from benchweave.control.semantics import check_semantics
from benchweave.host.plugin import DevicePlugin
from benchweave.host.services import HostServices
from benchweave.host.types import (
    DispatchState,
    ErrorCode,
    OperationError,
    OperationRequest,
    OperationResult,
    OperationStatus,
)
from benchweave.state.store import Store
from benchweave.vendoring import contract_family

#: The vendored execution contracts (packaged in the wheel, repo-relative
#: in a dev checkout — :mod:`benchweave.vendoring`).
_CONTRACTS = contract_family("execution/0.1.0")
_RUN_RECORD_VALIDATOR: Any = None

#: Body outcomes that pass through unchanged when the safe state is verified.
_OUTCOME_BY_BODY = {
    "completed": "passed",
    "assertion_failed": "assertion_failed",
    "cancelled": "cancelled",
    "timed_out": "timed_out",
    "tripped": "tripped",
    "execution_error": "execution_error",
}


def terminal_outcome(body_outcome: str, safe_state: str) -> str:
    """The §5 terminal mapping as one function.

    An uncertain body stays ``outcome_unknown`` and an unverified safe state
    forces ``outcome_unknown`` regardless of the body — uncertainty is never
    erased by later safety. One exception: restart recovery records
    ``interrupted`` with ``unknown`` physical assurance, which the run-record
    schema's allOf sanctions exactly (restart → interrupted). Everything
    else maps from the body outcome once the safe condition is verified.
    """
    if body_outcome == "interrupted":
        return "interrupted"
    if body_outcome == "outcome_unknown" or safe_state != "verified":
        return "outcome_unknown"
    return _OUTCOME_BY_BODY.get(body_outcome, body_outcome)


def _record_validator() -> Any:
    global _RUN_RECORD_VALIDATOR
    if _RUN_RECORD_VALIDATOR is None:
        schema = json.loads(
            (_CONTRACTS / "run-record.schema.json").read_text(encoding="utf-8")
        )
        _RUN_RECORD_VALIDATOR = Draft202012Validator(schema)
    return _RUN_RECORD_VALIDATOR


def build_terminal_record(
    *,
    run_id: str,
    binding_pin: dict[str, Any],
    principal_id: str,
    started_at: str,
    ended_at: str,
    body_outcome: str,
    safe_state: str,
    reasons: list[str],
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build one terminal run record and validate it against the schema.

    A record claimed to exist must validate: the vendored execution/0.1.0
    run-record schema is checked here, on every record, before it is
    returned or persisted. The ``outcome`` field is NOT an input — it is
    derived by :func:`terminal_outcome` so the §5 truth table lives in
    exactly one place.
    """
    record = {
        "contract_version": "0.1.0",
        "run_id": run_id,
        "binding": {
            "id": str(binding_pin["id"]),
            "version": str(binding_pin["version"]),
            "sha256": str(binding_pin["sha256"]),
        },
        "principal_id": principal_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "body_outcome": body_outcome,
        "outcome": terminal_outcome(body_outcome, safe_state),
        "safe_state": safe_state,
        "reasons": [str(reason) for reason in reasons],
        "evidence_refs": [
            {
                "id": str(ref["id"]),
                "version": str(ref["version"]),
                "sha256": str(ref["sha256"]),
            }
            for ref in evidence_refs
        ],
    }
    errors = sorted(_record_validator().iter_errors(record), key=lambda error: error.json_path)
    if errors:
        raise ValueError(
            f"terminal record failed run-record schema: {[e.message for e in errors]}"
        )
    return record


def _parse_utc(text: Any) -> datetime | None:
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


def _iso_plus_ms(stamp: str, milliseconds: int) -> str:
    moment = _parse_utc(stamp)
    if moment is None:
        raise ValueError(f"invalid wall timestamp {stamp!r}")
    return (moment + timedelta(milliseconds=milliseconds)).isoformat().replace("+00:00", "Z")


def _cancel_result(request: OperationRequest, reason: str) -> OperationResult:
    """The CANCELLED-status block result (honest bucket, nothing dispatched)."""
    return OperationResult(
        operation_id=request.operation_id,
        verb=request.verb,
        status=OperationStatus.CANCELLED,
        error=OperationError(
            code=ErrorCode.CANCELLED,
            message=reason,
            dispatch_state=DispatchState.NOT_DISPATCHED,
        ),
    )


class _RunMonitor:
    """Continuous-condition monitoring for one run, from acceptance on.

    Ticks are driven by the wrapped plugins (before/after every dispatch)
    and the wrapped clock (one tick per poll-cadence slice of any wait).
    During the body a fresh violation, a requested cancellation or lease
    loss sets the terminal cause, which the wrapper then materialises by
    blocking the next dispatch; during protection the tick keeps reading
    and escalates new violations into the engine through ``on_violation``
    without blocking anything. Reads inside a tick are re-entrancy guarded
    so the monitor's own signal reads never recurse.
    """

    def __init__(
        self,
        store: Store,
        bench_id: str,
        policy: dict[str, Any],
        bench: dict[str, Any],
        plugins: dict[str, DevicePlugin],
        clock: MonotonicClock,
        wall: WallClock,
        *,
        run_id: str,
        lease_sequence: int,
    ) -> None:
        self._store = store
        self._bench_id = bench_id
        self._policy = policy
        self._bench = bench
        self._plugins = plugins
        self._clock = clock
        self._wall = wall
        self.run_id = run_id
        self._lease_sequence = lease_sequence
        self.phase = "idle"
        self._poll_ns = bench_poll_ns(bench)
        self.in_tick = False
        self.violations: list[str] = []
        self.cause: str | None = None
        self.cause_reasons: list[str] = []
        self.blocked = False
        self._cancelled = False
        self.on_violation: Callable[[list[str], int], Any] | None = None
        #: Optional per-tick snapshot retention (WP07 monitor evidence).
        self.retain: Callable[[dict[str, Any]], str] | None = None
        self.snapshot_evidence: list[str] = []
        self.retention_failures = 0

    def request_cancel(self) -> None:
        self._cancelled = True

    def _set_cause(self, cause: str, reasons: list[str]) -> None:
        if self.cause is None:
            self.cause = cause
            self.cause_reasons = list(reasons)

    def tick(self) -> None:
        if self.in_tick or self.phase == "idle":
            return
        self.in_tick = True
        try:
            if self.phase == "body":
                self._check_body_phase()
            snapshot = read_signal_values(
                self._plugins,
                self._bench,
                deadline_ns=self._clock.now_ns() + self._poll_ns,
                wall_now=self._wall.now_iso,
            )
            if self.retain is not None:
                try:
                    self.snapshot_evidence.append(self.retain(dict(snapshot)))
                except Exception:
                    self.retention_failures += 1  # caller emits evidence_gap (Task 6)
            fresh = [
                violation
                for violation in evaluate_conditions(self._policy, snapshot)
                if violation not in self.violations
            ]
            if fresh:
                self.violations.extend(fresh)
                if self.phase == "body":
                    self._set_cause("tripped", list(self.violations))
                if self.on_violation is not None:
                    self.on_violation(fresh, self._clock.now_ns())
        finally:
            self.in_tick = False

    def _check_body_phase(self) -> None:
        """Cancellation and lease loss end the body (§5); protection is untouched."""
        if self._cancelled:
            self._set_cause("cancelled", [f"cancelled by principal for run {self.run_id}"])
            return
        lease = self._store.get_active_lease(self._bench_id)
        if lease is None or lease.sequence != self._lease_sequence:
            self._set_cause(
                "cancelled",
                [f"lease_lost: bench lease {self._lease_sequence} is no longer active"],
            )
            return
        expiry = _parse_utc(lease.expires_at)
        now = _parse_utc(self._wall.now_iso())
        if expiry is not None and now is not None and now > expiry:
            self._set_cause("cancelled", [f"lease_expired: {lease.expires_at}"])

    def block_result(self, request: OperationRequest) -> OperationResult | None:
        """The protective failure that ends the body, or None to proceed.

        A trip blocks as a device rejection the executor records as an
        error; a cancellation blocks as a CANCELLED operation so the blocked
        step event carries the honest cancelled bucket. Both carry
        ``not_dispatched``: nothing was sent to the device.
        """
        if self.phase != "body" or self.cause is None:
            return None
        self.blocked = True  # this cause terminated the body (the §5 latch)
        if self.cause == "cancelled":
            return _cancel_result(
                request, f"run {self.run_id} cancelled before dispatch"
            )
        return OperationResult.failure(
            request.operation_id,
            request.verb,
            code=ErrorCode.DEVICE_REJECTED,
            message="protection trip: " + "; ".join(self.cause_reasons),
            dispatch_state=DispatchState.NOT_DISPATCHED,
        )


class _MonitoringPlugin:
    """DevicePlugin wrapper placing a monitor tick around every dispatch."""

    def __init__(self, inner: DevicePlugin, monitor: _RunMonitor) -> None:
        self._inner = inner
        self._monitor = monitor

    @property
    def simulation(self) -> Any:
        return self._inner.simulation

    def plugin_open(self, services: HostServices) -> None:
        self._inner.plugin_open(services)

    def plugin_close(self) -> None:
        self._inner.plugin_close()

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        monitor = self._monitor
        if monitor.in_tick:  # the monitor's own signal reads never recurse
            return self._inner.dispatch(request, deadline_ns=deadline_ns)
        monitor.tick()
        blocked = monitor.block_result(request)
        if blocked is not None:
            return blocked
        result = self._inner.dispatch(request, deadline_ns=deadline_ns)
        monitor.tick()
        return result


class _MonitoringClock:
    """Monotonic clock wrapper slicing waits with monitor ticks (§3: delay
    keeps monitoring active); a terminal cause ends the wait early."""

    def __init__(self, inner: MonotonicClock, monitor: _RunMonitor, poll_ns: int) -> None:
        self._inner = inner
        self._monitor = monitor
        self._poll_ns = max(1, poll_ns)

    def now_ns(self) -> int:
        return self._inner.now_ns()

    def wait_ns(self, duration_ns: int) -> None:
        remaining = duration_ns
        while remaining > 0:
            self._monitor.tick()
            if self._monitor.cause is not None:
                return  # protective intervention ends the wait
            slice_ns = min(self._poll_ns, remaining)
            self._inner.wait_ns(slice_ns)
            remaining -= slice_ns
        self._monitor.tick()


@dataclass
class _PreparedRun:
    """Acceptance-time state fixed before the body starts."""

    run_id: str
    principal_id: str
    acceptance_ns: int
    acceptance_iso: str
    reservation: Reservation
    monitor: _RunMonitor
    plugins: dict[str, DevicePlugin]
    clock: MonotonicClock


class RunCoordinator:
    """Drives one procedure run from admission to a truthful terminal record."""

    def __init__(
        self,
        store: Store,
        plugins: dict[str, DevicePlugin],
        clock: MonotonicClock,
        wall: WallClock,
        docs: AdmittedDocuments,
    ) -> None:
        self._store = store
        self._plugins = plugins
        self._clock = clock
        self._wall = wall
        self._docs = docs
        #: Occurrence identities this coordinator will never re-dispatch.
        self.occurrence_ledger: dict[Occurrence, dict[str, Any]] = {}
        self._active_monitor: _RunMonitor | None = None

    @property
    def monitor(self) -> _RunMonitor | None:
        """Read-only view of the armed monitor (WP07 Task 6: the run
        worker reads ``retention_failures`` off it for the drain-side
        ``evidence_gap`` emission)."""
        return self._active_monitor

    # -- public API -----------------------------------------------------------

    def start_run(self, run_id: str, principal_id: str) -> dict[str, Any]:
        """Run the whole lifecycle; return the validated terminal record."""
        prepared = self._prepare_run(run_id, principal_id)
        return self._finish_run(prepared)

    def cancel(self, run_id: str, principal_id: str) -> None:
        """Request cancellation in the accepted-but-dispatchable window.

        The intent is honoured at the next monitor tick while the body is
        still dispatchable. Once the body has ended, the safe transition is
        already running under its own protective authority and the terminal
        outcome stands (§5: cancellation cannot suppress the transition).
        """
        monitor = self._active_monitor
        if monitor is not None and monitor.phase == "body" and monitor.run_id == run_id:
            monitor.request_cancel()

    def recover_interrupted(self) -> list[str]:
        """Finalise un-terminalised runs as interrupted; release their leases.

        Discovery rides the bench leases this coordinator's bench declares:
        a run that crashed anywhere between ``create_run`` and
        ``finalize_run`` still holds (or left) an active lease whose holder
        is ``run:{run_id}``. Recovered runs are recorded ``interrupted``
        with ``unknown`` physical assurance and their occurrence identities
        rebuilt from the durable event stream so they can never re-dispatch.
        """
        bench_id = str(self._docs.bench["id"])
        recovered: list[str] = []
        for lease in self._store.list_leases(bench_id):
            if lease.state != "active" or not lease.holder.startswith("run:"):
                continue
            run_id = lease.holder[len("run:"):]
            run = self._store.get_run(run_id)
            now = self._wall.now_iso()
            if run is None:
                # Crashed between taking the lease and creating the run.
                self._store.release_lease(bench_id, lease.sequence, now)
                continue
            if run["terminal"] is None:
                record = build_terminal_record(
                    run_id=run_id,
                    binding_pin=run["binding"],
                    principal_id=run["principal_id"],
                    started_at=run["started_at"],
                    ended_at=now,
                    body_outcome="interrupted",
                    safe_state="unknown",
                    reasons=[
                        "gateway restart: run was not terminalised; body execution "
                        "never resumes automatically"
                    ],
                    evidence_refs=self._recovery_evidence_refs(run_id, run["binding"]),
                )
                self._store.finalize_run(run_id, record)
                self._rebuild_ledger_from_events(run_id)
                recovered.append(run_id)
            self._store.release_lease(bench_id, lease.sequence, now)
        return recovered

    # -- pipeline ---------------------------------------------------------------

    def _binding_pin(self) -> dict[str, str]:
        """The run's binding pin: request_id / contract version / digest."""
        binding = self._docs.binding
        return {
            "id": str(binding["request_id"]),
            "version": str(binding["contract_version"]),
            "sha256": self._docs.digests["binding"],
        }

    def _prepare_run(self, run_id: str, principal_id: str) -> _PreparedRun:
        """Accept, admit, reserve and create the run; arm the monitor.

        Acceptance is idempotent on the binding document's request id; a
        replayed request is refused (run ids are never reusable). Partial
        failure after the lease is taken releases the reservation, so a
        rejected admission leaves no partially-reserved state.
        """
        acceptance_iso = self._wall.now_iso()
        acceptance_ns = self._clock.now_ns()
        key = str(self._docs.binding["request_id"])
        accepted = self._store.accept_request(
            key, self._docs.digests["binding"], run_id, acceptance_iso
        )
        if accepted.outcome == "duplicate":
            raise ValueError(
                f"request {key!r} was already accepted as run {accepted.run_id!r}; "
                "run ids are never reusable"
            )
        check_semantics(self._docs, now_wall=acceptance_iso)

        bench_id = str(self._docs.bench["id"])
        horizon_ms = int(self._docs.procedure["max_body_ms"]) + int(
            self._docs.procedure["max_protection_ms"]
        )
        # D12 commissioned-takeover handoff: a run accepted against a named
        # manual lease arrives with that lease already consumed at the seam
        # (validated there: active, on this bench, unexpired, §6
        # owner-or-admin), so reserve's one-active check sees an idle bench
        # and the takeover run takes its OWN lease exactly as a
        # gateway-owned start does — one ownership path through the WP05
        # core, no takeover-specific coordinator state.
        reservation = reserve(
            self._store,
            self._docs,
            bench_id=bench_id,
            holder=f"run:{run_id}",
            expires_at=_iso_plus_ms(acceptance_iso, horizon_ms),
            now_wall=acceptance_iso,
        )
        try:
            # WP07 Task 8: the seam pre-creates the run row before enqueueing
            # (202 semantics — the run must read back before the worker
            # starts); adopt that row — only a fresh run id creates one.
            # The queue handoff orders the seam's write before this check.
            if self._store.get_run(run_id) is None:
                self._store.create_run(
                    run_id, binding=self._binding_pin(), principal_id=principal_id,
                    now=acceptance_iso,
                )
        except BaseException:
            release(self._store, reservation, self._wall.now_iso())
            raise

        monitor = _RunMonitor(
            self._store,
            bench_id,
            self._docs.policy,
            self._docs.bench,
            self._plugins,
            self._clock,
            self._wall,
            run_id=run_id,
            lease_sequence=reservation.lease.sequence,
        )
        wrapped_plugins: dict[str, DevicePlugin] = {
            device_id: _MonitoringPlugin(plugin, monitor)
            for device_id, plugin in self._plugins.items()
        }
        wrapped_clock = _MonitoringClock(self._clock, monitor, bench_poll_ns(self._docs.bench))
        monitor.phase = "body"
        self._active_monitor = monitor
        monitor.tick()  # monitoring applies from acceptance (§7)
        return _PreparedRun(
            run_id=run_id,
            principal_id=principal_id,
            acceptance_ns=acceptance_ns,
            acceptance_iso=acceptance_iso,
            reservation=reservation,
            monitor=monitor,
            plugins=wrapped_plugins,
            clock=wrapped_clock,
        )

    def _run_and_record(self, prepared: _PreparedRun) -> Any:
        """Execute the monitored body and make its events durable.

        Durable before protection: a crash during the transition still
        leaves the body's evidence stream intact for recovery.
        """
        executor = Executor(
            plugins=prepared.plugins,
            binding=resolve_binding(self._docs),
            policy=self._docs.policy,
            clock=prepared.clock,
            wall=self._wall,
            occurrence_ledger=self.occurrence_ledger,
        )
        body_deadline_ns = prepared.acceptance_ns + int(
            self._docs.procedure["max_body_ms"]
        ) * 1_000_000
        body = executor.run_body(self._docs.procedure, prepared.run_id, body_deadline_ns)
        prepared.monitor.tick()  # acceptance→end coverage, post-last-dispatch too
        stream_id = f"run:{prepared.run_id}"
        for event in body.step_events:
            # Copy: the executor aliases event dicts into the shared ledger;
            # stored evidence must never be mutable through that alias.
            self._store.append_event(stream_id, dict(event))
        return body

    def _finish_run(self, prepared: _PreparedRun) -> dict[str, Any]:
        """Protect, build the terminal record, finalise and release."""
        body = self._run_and_record(prepared)
        monitor = prepared.monitor
        body_outcome, body_reasons = self._body_truth(prepared, body)

        engine = ProtectionEngine(
            prepared.plugins, self._docs.policy, self._docs.bench, self._clock, self._wall
        )
        entered_at_ns = self._clock.now_ns()
        monitor.phase = "protecting"
        monitor.on_violation = engine.enter  # later faults escalation, never extension
        enter_reasons = body_reasons if monitor.cause is not None else []
        result = engine.enter(enter_reasons, entered_at_ns)
        monitor.phase = "idle"
        monitor.on_violation = None
        self._active_monitor = None

        reasons: list[str] = []
        for reason in [*body_reasons, *result.reasons]:
            if reason not in reasons:
                reasons.append(reason)
        record = build_terminal_record(
            run_id=prepared.run_id,
            binding_pin=self._binding_pin(),
            principal_id=prepared.principal_id,
            started_at=prepared.acceptance_iso,
            ended_at=self._wall.now_iso(),
            body_outcome=body_outcome,
            safe_state=result.safe_state,
            reasons=reasons,
            evidence_refs=self._evidence_refs(prepared.run_id),
        )
        self._store.finalize_run(prepared.run_id, record)
        release(self._store, prepared.reservation, self._wall.now_iso())
        return record

    def _body_truth(self, prepared: _PreparedRun, body: Any) -> tuple[str, list[str]]:
        """The body outcome this run will record, per the monitor's cause.

        Reclassification to ``tripped``/``cancelled`` exists for exactly one
        case: the monitor's block TERMINATED the body, so the executor's
        terminal ``execution_error`` is the blocking proxy and the
        coordinator replaces it with the real cause. When the body ended on
        its own outcome — uncertain dispatch, failed assertion, deadline,
        completion — a cause observed alongside or after it may never
        downgrade the body: the executor's reasons are preserved and the
        cause reasons are APPENDED (uncertainty is never erased by a trip).
        """
        monitor = prepared.monitor
        if monitor.blocked and monitor.cause == "tripped":
            return "tripped", list(monitor.cause_reasons)
        if monitor.blocked and monitor.cause == "cancelled":
            return "cancelled", list(monitor.cause_reasons)
        reasons = list(body.reasons)
        for reason in monitor.cause_reasons:
            if reason not in reasons:
                reasons.append(reason)
        return body.body_outcome, reasons

    def _evidence_refs(self, run_id: str) -> list[dict[str, str]]:
        """The pinned evidence set, including the event-stream digest."""
        docs = self._docs
        refs = [
            self._binding_pin(),
            {
                "id": str(docs.procedure["id"]),
                "version": str(docs.procedure["version"]),
                "sha256": docs.digests["procedure"],
            },
            {
                "id": str(docs.bench["id"]),
                "version": str(docs.bench["version"]),
                "sha256": docs.digests["bench"],
            },
            {
                "id": str(docs.policy["id"]),
                "version": str(docs.policy["version"]),
                "sha256": docs.digests["policy"],
            },
            {
                "id": str(docs.commissioning["id"]),
                "version": str(docs.commissioning["version"]),
                "sha256": docs.digests["commissioning"],
            },
            {
                "id": f"events:{run_id}",
                "version": "1",
                "sha256": self._event_stream_digest(run_id),
            },
        ]
        return refs

    def _event_stream_digest(self, run_id: str) -> str:
        events = self._store.read_events(f"run:{run_id}")
        return hashlib.sha256(canonical_json(events).encode("utf-8")).hexdigest()

    def _recovery_evidence_refs(
        self, run_id: str, binding_pin: dict[str, Any]
    ) -> list[dict[str, str]]:
        """Recovery evidence: what the store itself retains for the run."""
        return [
            {
                "id": str(binding_pin["id"]),
                "version": str(binding_pin["version"]),
                "sha256": str(binding_pin["sha256"]),
            },
            {
                "id": f"events:{run_id}",
                "version": "1",
                "sha256": self._event_stream_digest(run_id),
            },
        ]

    def _rebuild_ledger_from_events(self, run_id: str) -> None:
        """Suppress replay of every recorded occurrence of ``run_id``.

        The rebuilt entries keep the durable event (immutable evidence) and
        a ``None`` result placeholder: a re-walk answers from the ledger
        without dispatching, which is the honest suppression guarantee — no
        exactly-once physical-execution promise is made or possible.
        """
        for event in self._store.read_events(f"run:{run_id}"):
            occurrence = event.get("occurrence")
            if not isinstance(occurrence, list) or len(occurrence) != 3:
                continue
            run_part, step_id, index_path = occurrence
            if run_part != run_id or not isinstance(step_id, str):
                continue
            if not isinstance(index_path, list):
                continue
            key: Occurrence = (
                str(run_part),
                step_id,
                tuple(int(index) for index in index_path),
            )
            self.occurrence_ledger.setdefault(
                key, {"event": dict(event), "result": None, "interrupted": True}
            )
