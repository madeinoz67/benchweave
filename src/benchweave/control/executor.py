"""The eight-kind procedure body interpreter (execution contract §3–§5).

Executes an admitted procedure body against bound device plugins under a
fixed monotonic body deadline, appending one step event per occurrence and
answering every re-entry from the occurrence ledger without re-dispatching.

Task 7 seam — ``resolve_value``: every invoke input and every write value
flows through the module-level :func:`resolve_value` hook before the policy
check and before dispatch. This task the hook is the identity for literal
JSON and raises ``NotImplementedError`` for the reserved ``$stg_ref`` /
``$stg_channel`` / ``$stg_issue`` reference objects, so a reference-bearing
procedure fails loudly instead of dispatching unresolved directives. The
integration tests therefore drive a reduced literal-input variant of the
fixture procedure (``configuration_id`` literal ``cfg-test-1``, channel
literal ``ch1``) built through ``readmit_mutated``. Sample freshness,
uncertainty and three-valued predicates land in Task 7 on the same seam.

Deadline discipline: the body deadline is fixed by the caller (it is
acceptance-time state); each dispatched ``deadline_ns`` is
``min(now + timeout_ms, body_deadline)`` — shortened only, never extended —
and a delay never waits past the body deadline. Body expiry is checked
before every step.

Error honesty: an operation whose result is not OK terminates the body —
``error.dispatch_state`` NOT_DISPATCHED maps to ``execution_error``;
DISPATCHED or UNKNOWN maps to ``outcome_unknown`` (uncertain, never
retried, never dressed up). A step event's ``status`` mirrors the operation
status (``ok`` / ``error`` / ``unknown``); the §5 uncertainty mapping lives
in ``body_outcome``. There is no automatic retry of any state-changing
operation: one dispatch per occurrence, ever. A policy denial happens
strictly before dispatch and surfaces as ``execution_error``.

Occurrence ledger replay: a ledger hit re-appends the recorded event and
returns the recorded result without any new dispatch, wait or policy check
— physical work is never repeated. Control-flow steps (``if`` / ``repeat``)
re-walk their recorded branch decision / iteration count so nested
occurrences replay too, and a step whose first execution terminated the
body terminates the replayed body the same way. Replay promises no
exactly-once physical execution; recovery semantics belong to the Task 8
coordinator.

``cancelled`` and ``tripped`` body outcomes belong to the coordinator and
the monitoring loop (Task 8); this module never produces them. No store, no
monitoring, no terminal records, and no imported time source — everything
flows through the injected clock ports. The ``wall`` port is retained for
the Task 7/8 freshness and audit work that builds on this executor.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import ChainMap
from dataclasses import dataclass
from typing import Any

from benchweave.control.binding import ResolvedBinding
from benchweave.control.clocking import MonotonicClock, WallClock
from benchweave.control.policy import PolicyDenied, check_allowed
from benchweave.host.plugin import DevicePlugin
from benchweave.host.types import (
    DispatchState,
    OperationRequest,
    OperationResult,
    OperationStatus,
    OperationVerb,
)

#: One step occurrence: (run_id, step_id, loop index path). The loop index
#: path carries one entry per enclosing ``repeat`` iteration; ``if`` branches
#: add nothing because step IDs are globally unique.
Occurrence = tuple[str, str, tuple[int, ...]]

BODY_COMPLETED = "completed"
BODY_ASSERTION_FAILED = "assertion_failed"
BODY_CANCELLED = "cancelled"
BODY_TIMED_OUT = "timed_out"
BODY_TRIPPED = "tripped"
BODY_EXECUTION_ERROR = "execution_error"
BODY_OUTCOME_UNKNOWN = "outcome_unknown"

_CONTAINER_KINDS = ("if", "repeat")


@dataclass(frozen=True)
class BodyResult:
    """Terminal view of one body execution (full outcome set per §5).

    ``body_outcome`` is one of ``completed``, ``assertion_failed``,
    ``cancelled``, ``timed_out``, ``tripped``, ``execution_error``,
    ``outcome_unknown``. ``step_events`` carries one event per executed
    occurrence (replayed occurrences included); full payloads stay with the
    coordinator, not the executor.
    """

    body_outcome: str
    reasons: list[str]
    step_events: list[dict[str, Any]]


def canonical_json(value: Any) -> str:
    """Canonical JSON for resolved-input hashes: sorted keys, compact."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def resolve_value(value: Any, scope: ChainMap[str, Any], role: str) -> Any:
    """Resolve one input position; identity for literals (Task 7 seam).

    Reserved ``$stg_*`` reference objects are recognised but not implemented
    this task — they raise ``NotImplementedError`` rather than dispatching an
    unresolved directive. Objects and lists are resolved recursively so the
    resolved input is a fresh literal tree with no shared mutable aliases.
    """
    if isinstance(value, dict):
        if any(str(key).startswith("$stg_") for key in value):
            raise NotImplementedError(
                f"$stg_* reference resolution arrives in Task 7: {value!r}"
            )
        return {key: resolve_value(item, scope, role) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, scope, role) for item in value]
    return value


def _operation_id(run_id: str, step_id: str, index_path: tuple[int, ...]) -> str:
    """Stable operation id for one occurrence, e.g. ``op:run-1:remeasure.2``."""
    suffix = "".join(f".{index}" for index in index_path)
    return f"op:{run_id}:{step_id}{suffix}"


@dataclass
class _Body:
    """Mutable state of one ``run_body`` call."""

    run_id: str
    deadline_ns: int
    events: list[dict[str, Any]]
    reasons: list[str]
    outcome: str | None = None

    def terminate(self, outcome: str, reason: str) -> None:
        if self.outcome is None:
            self.outcome = outcome
        self.reasons.append(reason)


class Executor:
    """Interpreter for the eight step kinds over bound device plugins."""

    def __init__(
        self,
        plugins: dict[str, DevicePlugin],
        binding: ResolvedBinding,
        policy: dict[str, Any],
        clock: MonotonicClock,
        wall: WallClock,
        occurrence_ledger: dict[Occurrence, dict[str, Any]] | None = None,
    ) -> None:
        self._plugins = plugins
        self._binding = binding
        self._policy = policy
        self._clock = clock
        self._wall = wall
        self._ledger: dict[Occurrence, dict[str, Any]] = (
            {} if occurrence_ledger is None else occurrence_ledger
        )

    def run_body(
        self, procedure: dict[str, Any], run_id: str, body_deadline_ns: int
    ) -> BodyResult:
        """Execute the procedure body once under the fixed body deadline.

        The deadline is acceptance-time state supplied by the caller; it is
        never derived or extended here. Occurrences already recorded in the
        (possibly shared) ledger replay their recorded results without any
        new dispatch, wait or policy check.
        """
        body = _Body(run_id=run_id, deadline_ns=body_deadline_ns, events=[], reasons=[])
        scope: ChainMap[str, Any] = ChainMap()
        self._execute_block(procedure["steps"], scope, (), body)
        outcome = body.outcome if body.outcome is not None else BODY_COMPLETED
        return BodyResult(body_outcome=outcome, reasons=body.reasons, step_events=body.events)

    # -- block and step dispatch ------------------------------------------------

    def _execute_block(
        self,
        steps: list[dict[str, Any]],
        scope: ChainMap[str, Any],
        index_path: tuple[int, ...],
        body: _Body,
    ) -> None:
        for step in steps:
            if body.outcome is not None:
                return
            if self._clock.now_ns() >= body.deadline_ns:
                body.terminate(
                    BODY_TIMED_OUT,
                    f"body_deadline_exceeded: {body.deadline_ns} ns reached before "
                    f"step {step['id']}",
                )
                return
            scope[str(step["id"])] = self._execute_step(step, scope, index_path, body)

    def _new_event(
        self, body: _Body, step_id: str, kind: str, index_path: tuple[int, ...]
    ) -> dict[str, Any]:
        return {
            "occurrence": [body.run_id, step_id, list(index_path)],
            "kind": kind,
            "resolved_input_sha256": "",
            "operation_id": None,
            "status": "ok",
        }

    @staticmethod
    def _replay_termination(recorded: dict[str, Any], body: _Body) -> bool:
        """Re-terminate a replayed body when the recorded step ended it."""
        outcome = recorded.get("outcome")
        if isinstance(outcome, str) and body.outcome is None:
            body.terminate(outcome, str(recorded["reason"]))
            return True
        return False

    def _execute_step(
        self,
        step: dict[str, Any],
        scope: ChainMap[str, Any],
        index_path: tuple[int, ...],
        body: _Body,
    ) -> Any:
        step_id = str(step["id"])
        kind = str(step["kind"])
        occurrence: Occurrence = (body.run_id, step_id, index_path)
        # Control-flow steps re-walk their recorded decisions so nested
        # occurrences replay; every other kind is a leaf that replays whole.
        if kind in _CONTAINER_KINDS:
            if kind == "if":
                return self._run_if(step, scope, index_path, body, occurrence)
            return self._run_repeat(step, scope, index_path, body, occurrence)

        recorded = self._ledger.get(occurrence)
        if recorded is not None:
            body.events.append(recorded["event"])
            self._replay_termination(recorded, body)
            return recorded["result"]

        event = self._new_event(body, step_id, kind, index_path)
        body.events.append(event)
        result: Any
        if kind == "invoke":
            result = self._step_invoke(step, scope, index_path, body, event)
        elif kind == "read":
            result = self._step_read(step, index_path, body, event)
        elif kind == "write":
            result = self._step_write(step, scope, index_path, body, event)
        elif kind == "delay":
            self._step_delay(step, body, event)
            result = None
        elif kind == "sample":
            result = self._step_sample(step, scope, body, event)
        elif kind == "assert":
            result = self._step_assert(step, scope, body, event)
        else:
            body.terminate(BODY_EXECUTION_ERROR, f"unknown step kind {kind!r} at {step_id}")
            return None
        entry: dict[str, Any] = {"event": event, "result": result}
        if body.outcome is not None:
            # This step ended the body (outcome was clear when it started);
            # replay must terminate the same way.
            entry["outcome"] = body.outcome
            entry["reason"] = body.reasons[-1]
        self._ledger[occurrence] = entry
        return result

    # -- operation kinds --------------------------------------------------------

    def _step_invoke(
        self,
        step: dict[str, Any],
        scope: ChainMap[str, Any],
        index_path: tuple[int, ...],
        body: _Body,
        event: dict[str, Any],
    ) -> OperationResult | None:
        step_id = str(step["id"])
        role = str(step["role"])
        action_id = str(step["action_id"])
        device_id = self._binding.device_by_role[role]
        resolved_input = resolve_value(step["input"], scope, role)
        event["resolved_input_sha256"] = _sha256_hex(resolved_input)
        operation_id = _operation_id(body.run_id, step_id, index_path)
        event["operation_id"] = operation_id
        try:
            check_allowed(self._policy, device_id, "invoke", action_id, resolved_input)
        except PolicyDenied as denied:
            event["status"] = "error"
            event["error_code"] = "POLICY_DENIED"
            body.terminate(BODY_EXECUTION_ERROR, f"policy_denied: {step_id}: {denied.reason}")
            return None
        request = OperationRequest(
            operation_id=operation_id,
            verb=OperationVerb.INVOKE,
            arguments={"action_id": action_id, "input": resolved_input},
        )
        return self._dispatch(self._plugins[device_id], request, step, body, event)

    def _step_read(
        self,
        step: dict[str, Any],
        index_path: tuple[int, ...],
        body: _Body,
        event: dict[str, Any],
    ) -> OperationResult:
        parameter = str(step["parameter"])
        device_id = self._binding.device_by_role[str(step["role"])]
        event["resolved_input_sha256"] = _sha256_hex({"parameter": parameter})
        operation_id = _operation_id(body.run_id, str(step["id"]), index_path)
        event["operation_id"] = operation_id
        # Core reads are non-state-changing observation: no allow rule applies.
        request = OperationRequest.read(operation_id, parameter=parameter)
        return self._dispatch(self._plugins[device_id], request, step, body, event)

    def _step_write(
        self,
        step: dict[str, Any],
        scope: ChainMap[str, Any],
        index_path: tuple[int, ...],
        body: _Body,
        event: dict[str, Any],
    ) -> OperationResult | None:
        step_id = str(step["id"])
        role = str(step["role"])
        parameter = str(step["parameter"])
        device_id = self._binding.device_by_role[role]
        resolved_value = resolve_value(step["value"], scope, role)
        event["resolved_input_sha256"] = _sha256_hex(resolved_value)
        operation_id = _operation_id(body.run_id, step_id, index_path)
        event["operation_id"] = operation_id
        try:
            check_allowed(self._policy, device_id, "write", parameter, resolved_value)
        except PolicyDenied as denied:
            event["status"] = "error"
            event["error_code"] = "POLICY_DENIED"
            body.terminate(BODY_EXECUTION_ERROR, f"policy_denied: {step_id}: {denied.reason}")
            return None
        request = OperationRequest.write(operation_id, parameter=parameter, value=resolved_value)
        return self._dispatch(self._plugins[device_id], request, step, body, event)

    def _dispatch(
        self,
        plugin: DevicePlugin,
        request: OperationRequest,
        step: dict[str, Any],
        body: _Body,
        event: dict[str, Any],
    ) -> OperationResult:
        step_id = str(step["id"])
        timeout_ns = int(step["timeout_ms"]) * 1_000_000
        # Shorten a step timeout to the remaining body budget; never extend it.
        deadline_ns = min(self._clock.now_ns() + timeout_ns, body.deadline_ns)
        result = plugin.dispatch(request, deadline_ns=deadline_ns)
        error = result.error
        if result.status is OperationStatus.OK:
            event["status"] = "ok"
            return result
        if error is None:  # defensive: the result type guarantees an error
            body.terminate(BODY_EXECUTION_ERROR, f"step {step_id}: result carries no error")
            return result
        event["status"] = "error" if result.status is OperationStatus.ERROR else "unknown"
        event["error_code"] = error.code.value
        if error.dispatch_state is DispatchState.NOT_DISPATCHED:
            body.terminate(
                BODY_EXECUTION_ERROR,
                f"step {step_id}: {error.code.value}: {error.message}",
            )
        else:
            body.terminate(
                BODY_OUTCOME_UNKNOWN,
                f"step {step_id}: dispatch {error.dispatch_state.value}, outcome "
                f"uncertain: {error.code.value}: {error.message}",
            )
        return result

    # -- non-operation kinds ----------------------------------------------------

    def _step_delay(self, step: dict[str, Any], body: _Body, event: dict[str, Any]) -> None:
        duration_ns = int(step["duration_ms"]) * 1_000_000
        event["resolved_input_sha256"] = _sha256_hex({"duration_ms": step["duration_ms"]})
        # A delay never waits past the body deadline: clamp to what remains.
        remaining_ns = body.deadline_ns - self._clock.now_ns()
        wait_ns = min(duration_ns, remaining_ns)
        if wait_ns > 0:
            self._clock.wait_ns(wait_ns)

    def _step_sample(
        self,
        step: dict[str, Any],
        scope: ChainMap[str, Any],
        body: _Body,
        event: dict[str, Any],
    ) -> float | None:
        step_id = str(step["id"])
        source_id = str(step["source_step"])
        variable_id = str(step["variable_id"])
        unit = str(step["unit"])
        event["resolved_input_sha256"] = _sha256_hex(
            {"source_step": source_id, "variable_id": variable_id, "unit": unit}
        )
        value, failure = self._extract_sample(step, scope)
        if failure is not None:
            event["status"] = "error"
            event["error_code"] = "INVALID_SAMPLE"
            body.terminate(BODY_EXECUTION_ERROR, f"sample {step_id}: {failure}")
            return None
        return value

    def _extract_sample(
        self, step: dict[str, Any], scope: ChainMap[str, Any]
    ) -> tuple[float | None, str | None]:
        """Extract one scalar from an earlier invoke's dataset; no new I/O.

        Task 6 performs the structural part of the scalar selection contract
        (§4): a successful invoke result holding a ``scalar_set`` dataset,
        exactly one finite numeric inline value, exact unit equality.
        Freshness-from-acquisition, known-uncertainty and provenance checks
        arrive with Task 7's trustworthy samples on this same seam.
        """
        source_id = str(step["source_step"])
        variable_id = str(step["variable_id"])
        unit = str(step["unit"])
        source = scope.get(source_id)
        if not isinstance(source, OperationResult) or source.status is not OperationStatus.OK:
            return None, f"source step {source_id!r} has no successful operation result"
        data = source.data
        if not isinstance(data, dict) or not isinstance(data.get("result"), dict):
            return None, f"source step {source_id!r} produced no class dataset"
        dataset: dict[str, Any] = data["result"]
        if dataset.get("kind") != "scalar_set":
            return None, f"dataset of {source_id!r} is {dataset.get('kind')!r}, not scalar_set"
        variables = dataset.get("variables")
        if not isinstance(variables, list):
            return None, f"dataset of {source_id!r} has no variables list"
        variable = next(
            (
                candidate
                for candidate in variables
                if isinstance(candidate, dict) and candidate.get("id") == variable_id
            ),
            None,
        )
        if variable is None:
            return None, f"variable {variable_id!r} missing from dataset of {source_id!r}"
        if variable.get("unit") != unit:
            return None, (
                f"variable {variable_id!r} unit {variable.get('unit')!r} does not "
                f"equal {unit!r}"
            )
        values = variable.get("values")
        if not isinstance(values, list) or len(values) != 1:
            return None, f"variable {variable_id!r} must hold exactly one inline value"
        raw = values[0]
        if (
            isinstance(raw, bool)
            or not isinstance(raw, (int, float))
            or not math.isfinite(raw)
        ):
            return None, f"variable {variable_id!r} value is not one finite number"
        return float(raw), None

    def _predicate_value(
        self, predicate: dict[str, Any], scope: ChainMap[str, Any]
    ) -> tuple[float | None, str | None]:
        sample_id = str(predicate["sample"])
        value = scope.get(sample_id)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"sample {sample_id!r} is not a numeric sample"
        if not math.isfinite(value):
            return None, f"sample {sample_id!r} is not finite"
        return float(value), None

    def _step_assert(
        self,
        step: dict[str, Any],
        scope: ChainMap[str, Any],
        body: _Body,
        event: dict[str, Any],
    ) -> bool | None:
        step_id = str(step["id"])
        predicate = step["predicate"]
        event["resolved_input_sha256"] = _sha256_hex(predicate)
        value, failure = self._predicate_value(predicate, scope)
        if failure is not None:
            event["status"] = "error"
            event["error_code"] = "INVALID_SAMPLE"
            body.terminate(BODY_EXECUTION_ERROR, f"assert {step_id}: {failure}")
            return None
        minimum, maximum = predicate["minimum"], predicate["maximum"]
        held: bool = bool(minimum <= value <= maximum)
        if not held:
            event["status"] = "failed"
            body.terminate(
                BODY_ASSERTION_FAILED,
                f"assert {step_id}: {value} outside [{minimum}, {maximum}]",
            )
        return held

    # -- control-flow kinds (ledger-aware re-walk) -------------------------------

    def _run_if(
        self,
        step: dict[str, Any],
        scope: ChainMap[str, Any],
        index_path: tuple[int, ...],
        body: _Body,
        occurrence: Occurrence,
    ) -> bool | None:
        step_id = str(step["id"])
        recorded = self._ledger.get(occurrence)
        if recorded is not None:
            body.events.append(recorded["event"])
            if self._replay_termination(recorded, body):
                return None
            held = recorded["result"]
        else:
            event = self._new_event(body, step_id, "if", index_path)
            event["resolved_input_sha256"] = _sha256_hex(step["predicate"])
            body.events.append(event)
            value, failure = self._predicate_value(step["predicate"], scope)
            if failure is not None:
                event["status"] = "error"
                event["error_code"] = "INVALID_SAMPLE"
                body.terminate(BODY_EXECUTION_ERROR, f"if {step_id}: {failure}")
                self._ledger[occurrence] = {
                    "event": event,
                    "result": None,
                    "outcome": body.outcome,
                    "reason": body.reasons[-1],
                }
                return None
            predicate = step["predicate"]
            held = bool(predicate["minimum"] <= value <= predicate["maximum"])
            self._ledger[occurrence] = {"event": event, "result": held}
        # Exactly one statically declared branch, scoped to this block; the
        # replay re-walks the recorded decision so nested occurrences replay.
        if isinstance(held, bool):
            branch_steps = step["then"] if held else step.get("else", [])
            self._execute_block(branch_steps, scope.new_child(), index_path, body)
        return held if isinstance(held, bool) else None

    def _run_repeat(
        self,
        step: dict[str, Any],
        scope: ChainMap[str, Any],
        index_path: tuple[int, ...],
        body: _Body,
        occurrence: Occurrence,
    ) -> None:
        step_id = str(step["id"])
        recorded = self._ledger.get(occurrence)
        if recorded is not None:
            body.events.append(recorded["event"])
            if self._replay_termination(recorded, body):
                return
        else:
            event = self._new_event(body, step_id, "repeat", index_path)
            event["resolved_input_sha256"] = _sha256_hex({"count": step["count"]})
            body.events.append(event)
            self._ledger[occurrence] = {"event": event, "result": None}
        for iteration in range(int(step["count"])):
            if body.outcome is not None:
                return
            # Each iteration sees enclosing results plus its own, never the
            # previous iteration's, and never leaks outward.
            self._execute_block(
                step["steps"], scope.new_child(), index_path + (iteration,), body
            )
