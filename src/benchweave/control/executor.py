"""The eight-kind procedure body interpreter (execution contract §3–§5).

Executes an admitted procedure body against bound device plugins under a
fixed monotonic body deadline, appending one step event per occurrence and
answering every re-entry from the occurrence ledger without re-dispatching.

Task 7 seam — ``resolve_value``: every invoke input, every write value and
every read parameter flows through the module-level :func:`resolve_value`
before the policy check and before dispatch. Literals pass through as a
fresh tree; the three reserved ``$stg_`` forms resolve against earlier
successful results (``$stg_ref``, RFC 6901 pointer with exact types), the
role's channel binding (``$stg_channel``) and the occurrence-scoped
issued-id registry (``$stg_issue``). Any unresolvable directive raises
:class:`ScopeError`, which the executor maps to ``execution_error`` with an
``unresolved_reference:`` reason — the body ends before dispatch. Read
parameters are literals by schema (a plain string); the runtime rejects
``$stg_`` directives in that position through the same seam rather than
trusting admission alone.

Issued ids: ``$stg_issue`` mints
``f"{field}-{run_id}-{step_id}{occurrence_suffix}"`` once per occurrence
and retains it in the occurrence-ledger entry under ``issued_ids``; a step
whose operation does not succeed invalidates every id it issued, and a
replayed occurrence reuses the recorded result without minting again.

Trustworthy samples and three-valued predicates (§4): a ``sample`` step
selects one scalar from an earlier invoke's dataset through
:func:`select_sample` — exact unit equality, exactly one finite value,
empty dimensions, valid status, freshness measured from acquisition
(``started_at``) at selection time, and known uncertainty when required —
and ``assert`` / ``if`` predicates evaluate through
:func:`evaluate_predicate`. Freshness is rechecked at predicate evaluation
against a fresh wall read: a sample fresh at selection but older than its
``max_age_ms`` by predicate time is INVALID. INVALID evidence is
``execution_error``, never
the false branch and never a passing assertion; a false assert is
``assertion_failed``; a false if takes the else branch; and a known
uncertainty decides by the conservative interval ``[v-|u|, v+|u|]`` inside
the inclusive bounds rather than by the nominal value.

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
from datetime import UTC, datetime
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


class ScopeError(Exception):
    """A reserved ``$stg_`` directive could not be resolved (§3).

    Raised before policy and before dispatch; the executor maps it to
    ``execution_error`` with the ``unresolved_reference:`` reason prefix, so
    a body never dispatches a directive it could not fully resolve.
    """


#: Invalid-sample reason codes (§4): evidence that is not a trustworthy
#: scalar can never satisfy a predicate — it terminates the body instead.
SAMPLE_MISSING = "missing"
SAMPLE_WRONG_UNIT = "wrong_unit"
SAMPLE_NOT_SCALAR = "not_scalar"
SAMPLE_STALE = "stale"
SAMPLE_UNKNOWN_UNCERTAINTY = "unknown_uncertainty"

_RESERVED_KEYS = ("$stg_ref", "$stg_channel", "$stg_issue")


@dataclass(frozen=True)
class SampleOutcome:
    """One sampled scalar: a TRUE_VALUE payload or an INVALID reason.

    ``invalid_reason`` is ``None`` exactly when the sample is trustworthy;
    otherwise it is one of the ``SAMPLE_*`` codes and ``value`` is ``None``.
    ``uncertainty`` carries the known absolute uncertainty (``None`` when
    unknown but permitted) and ``configuration_id`` retains the dataset's
    provenance. ``acquired_at`` / ``max_age_ms`` retain the freshness
    contract so predicate evaluation can recheck it against a fresh wall
    read (§4: freshness is rechecked at predicate evaluation).
    """

    value: float | None
    uncertainty: float | None
    configuration_id: str | None
    invalid_reason: str | None
    acquired_at: str | None = None
    max_age_ms: int | None = None


@dataclass(frozen=True)
class ResolveContext:
    """Per-occurrence resolution inputs: bound channels and issued ids.

    ``channels`` is the role's alias-to-actual channel map from the resolved
    binding; ``issued_ids`` is the executor's occurrence-keyed registry the
    ``$stg_issue`` resolver mints into and invalidation writes back to.
    """

    run_id: str
    step_id: str
    index_path: tuple[int, ...]
    channels: dict[str, str]
    issued_ids: dict[Occurrence, dict[str, dict[str, str]]]


def _recheck_stale(outcome: SampleOutcome, evaluated_at_wall: str) -> bool:
    """True when a finite freshness contract is violated at evaluation time.

    §4: freshness is rechecked at predicate evaluation. A sample that was
    fresh at selection but has aged past ``max_age_ms`` by the time its
    predicate runs is INVALID evidence. Unknown timing cannot satisfy a
    finite bound, so an unparseable timestamp also reads as stale.
    """
    if outcome.max_age_ms is None:
        return False
    acquired = _parse_wall(outcome.acquired_at)
    evaluated = _parse_wall(evaluated_at_wall)
    if acquired is None or evaluated is None:
        return True
    return (evaluated - acquired).total_seconds() * 1000.0 > float(outcome.max_age_ms)


def _invalid_sample(reason: str) -> SampleOutcome:
    return SampleOutcome(
        value=None, uncertainty=None, configuration_id=None, invalid_reason=reason
    )


def _parse_wall(text: Any) -> datetime | None:
    """Parse an ISO-8601 wall timestamp, treating a naive value as UTC."""
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


def _reserved_key(value: dict[Any, Any]) -> str | None:
    """Return the first ``$stg_``-prefixed key in ``value``, if any."""
    for key in value:
        if str(key).startswith("$stg_"):
            return str(key)
    return None


def _contains_stg_directive(value: Any) -> bool:
    """True when any dict under ``value`` carries a ``$stg_``-prefixed key."""
    if isinstance(value, dict):
        return _reserved_key(value) is not None or any(
            _contains_stg_directive(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_stg_directive(item) for item in value)
    return False


def resolve_value(
    value: Any,
    scope: ChainMap[str, Any],
    role: str,
    *,
    context: ResolveContext | None = None,
) -> Any:
    """Resolve one input position against the visible scope (§3).

    Literals pass through unchanged (recursively, as fresh containers); a
    dict whose single key is a reserved ``$stg_`` form resolves that
    reference: ``$stg_ref`` walks the earlier step's recorded result by
    RFC 6901 pointer with exact types (invoke results start at
    ``data["result"]``, scalar core operation results at ``data``),
    ``$stg_channel`` maps the role's alias through the binding, and
    ``$stg_issue`` mints or reuses the occurrence's issued id. Any other
    ``$stg_`` shape, a missing or wrongly typed target, or a reference to a
    step that is not visible raises :class:`ScopeError` — there are no
    defaults, coercions, interpolation or arithmetic.
    """
    if isinstance(value, dict):
        reserved = _reserved_key(value)
        if reserved is not None:
            if len(value) != 1 or reserved not in _RESERVED_KEYS:
                raise ScopeError(
                    f"malformed_reference: {value!r} is not a single reserved form"
                )
            if reserved == "$stg_ref":
                return _resolve_ref(value["$stg_ref"], scope)
            if reserved == "$stg_channel":
                return _resolve_channel(value["$stg_channel"], role, context)
            return _resolve_issue(value["$stg_issue"], role, context)
        return {
            key: resolve_value(item, scope, role, context=context)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [resolve_value(item, scope, role, context=context) for item in value]
    return value


def _resolve_ref(directive: Any, scope: ChainMap[str, Any]) -> Any:
    if (
        not isinstance(directive, dict)
        or set(directive) != {"step", "pointer"}
        or not isinstance(directive["step"], str)
        or not isinstance(directive["pointer"], str)
    ):
        raise ScopeError(f"malformed_reference: $stg_ref directive {directive!r}")
    step_id = directive["step"]
    if step_id not in scope:
        raise ScopeError(f"scope: step {step_id!r} is not visible at this point")
    source = scope[step_id]
    if not isinstance(source, OperationResult) or source.status is not OperationStatus.OK:
        raise ScopeError(f"scope: step {step_id!r} has no successful operation result")
    data = source.data
    if isinstance(data, dict) and "result" in data:
        data = data["result"]  # invoke envelope; scalar core ops walk data itself
    return _walk_pointer(data, directive["pointer"], step_id)


def _walk_pointer(base: Any, pointer: str, step_id: str) -> Any:
    """RFC 6901 walk with exact types; every miss raises :class:`ScopeError`."""
    current = base
    if pointer != "":
        for raw_token in pointer.split("/")[1:]:
            token = raw_token.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict):
                if token not in current:
                    raise ScopeError(
                        f"pointer: {pointer!r} key {token!r} missing in "
                        f"result of {step_id!r}"
                    )
                current = current[token]
            elif isinstance(current, list):
                if (
                    not (token.isascii() and token.isdigit())
                    or (len(token) > 1 and token.startswith("0"))
                ):
                    raise ScopeError(
                        f"pointer: {pointer!r} token {token!r} is not an array index"
                    )
                index = int(token)
                if index >= len(current):
                    raise ScopeError(
                        f"pointer: {pointer!r} index {index} out of range in "
                        f"{step_id!r}"
                    )
                current = current[index]
            else:
                raise ScopeError(
                    f"pointer: {pointer!r} cannot descend through "
                    f"{type(current).__name__} in result of {step_id!r}"
                )
    if isinstance(current, (dict, list, bool, int, float, str)) or current is None:
        return current
    raise ScopeError(
        f"pointer: {pointer!r} selects a non-JSON {type(current).__name__} "
        f"in result of {step_id!r}"
    )


def _resolve_channel(
    alias: Any, role: str, context: ResolveContext | None
) -> str:
    if not isinstance(alias, str):
        raise ScopeError(f"malformed_reference: $stg_channel alias {alias!r}")
    if context is None:
        raise ScopeError(f"channel: no binding context for role {role!r}")
    if alias not in context.channels:
        raise ScopeError(f"channel: alias {alias!r} is not bound for role {role!r}")
    return context.channels[alias]


def _resolve_issue(field: Any, role: str, context: ResolveContext | None) -> str:
    if not isinstance(field, str):
        raise ScopeError(f"malformed_reference: $stg_issue field {field!r}")
    if context is None:
        raise ScopeError(f"issue: no resolution context for role {role!r}")
    occurrence: Occurrence = (context.run_id, context.step_id, context.index_path)
    bucket = context.issued_ids.setdefault(occurrence, {})
    record = bucket.get(field)
    if record is None:
        suffix = "".join(f".{index}" for index in context.index_path)
        record = {
            "id": f"{field}-{context.run_id}-{context.step_id}{suffix}",
            "status": "issued",
        }
        bucket[field] = record
    return record["id"]


def select_sample(
    step: dict[str, Any], invoke_result: object, *, evaluated_at_wall: str
) -> SampleOutcome:
    """Select one trustworthy scalar from an earlier invoke's dataset (§4).

    The source must be a successful invoke result holding a ``scalar_set``
    dataset whose named variable carries the exact unit, exactly one finite
    numeric inline value, empty dimensions and valid status. Freshness is
    measured from acquisition (``started_at``) to ``evaluated_at_wall`` —
    never from fetch time — and unknown timing cannot satisfy a finite
    ``max_age_ms``. A known uncertainty is retained for the conservative
    interval; ``require_known_uncertainty`` rejects an unknown one. Dataset
    ``configuration_id`` provenance is retained in the outcome.
    """
    variable_id = str(step["variable_id"])
    unit = str(step["unit"])
    result = invoke_result
    if not isinstance(result, OperationResult) or result.status is not OperationStatus.OK:
        return _invalid_sample(SAMPLE_MISSING)
    data = result.data
    if not isinstance(data, dict) or not isinstance(data.get("result"), dict):
        return _invalid_sample(SAMPLE_MISSING)
    dataset: dict[str, Any] = data["result"]
    if dataset.get("kind") != "scalar_set":
        return _invalid_sample(SAMPLE_NOT_SCALAR)
    variables = dataset.get("variables")
    if not isinstance(variables, list):
        return _invalid_sample(SAMPLE_MISSING)
    variable = next(
        (
            candidate
            for candidate in variables
            if isinstance(candidate, dict) and candidate.get("id") == variable_id
        ),
        None,
    )
    if variable is None:
        return _invalid_sample(SAMPLE_MISSING)
    if variable.get("unit") != unit:  # exact equality: no conversion
        return _invalid_sample(SAMPLE_WRONG_UNIT)
    values = variable.get("values")
    raw = values[0] if isinstance(values, list) and len(values) == 1 else None
    if (
        raw is None
        or isinstance(raw, bool)
        or not isinstance(raw, (int, float))
        or not math.isfinite(raw)
        or variable.get("dimensions") != []
        or variable.get("status") != "valid"
    ):
        return _invalid_sample(SAMPLE_NOT_SCALAR)
    max_age_ms = step.get("max_age_ms")
    freshness_bound = (
        max_age_ms
        if isinstance(max_age_ms, int) and not isinstance(max_age_ms, bool)
        else None
    )
    started_at = dataset.get("started_at")
    if freshness_bound is not None:
        started = _parse_wall(started_at)
        evaluated = _parse_wall(evaluated_at_wall)
        if started is None or evaluated is None:
            return _invalid_sample(SAMPLE_STALE)
        age_ms = (evaluated - started).total_seconds() * 1000.0
        if age_ms > float(freshness_bound):
            return _invalid_sample(SAMPLE_STALE)
    uncertainty: float | None = None
    declared = variable.get("uncertainty")
    if isinstance(declared, dict) and declared.get("status") == "known":
        absolute = declared.get("absolute")
        if (
            isinstance(absolute, (int, float))
            and not isinstance(absolute, bool)
            and math.isfinite(absolute)
        ):
            uncertainty = abs(float(absolute))
    if step.get("require_known_uncertainty", False) and uncertainty is None:
        return _invalid_sample(SAMPLE_UNKNOWN_UNCERTAINTY)
    configuration_id = dataset.get("configuration_id")
    return SampleOutcome(
        value=float(raw),
        uncertainty=uncertainty,
        configuration_id=(
            configuration_id if isinstance(configuration_id, str) else None
        ),
        invalid_reason=None,
        acquired_at=started_at if isinstance(started_at, str) else None,
        max_age_ms=freshness_bound,
    )


def evaluate_predicate(
    predicate: dict[str, Any],
    samples: dict[str, SampleOutcome],
    *,
    evaluated_at_wall: str | None = None,
) -> bool | None:
    """Three-valued predicate over sampled evidence (§4).

    Returns ``None`` (INVALID) when the named sample is absent or carries an
    INVALID reason — INVALID evidence is never a false branch or a passing
    assertion. Freshness is rechecked at predicate evaluation: when
    ``evaluated_at_wall`` is supplied and the outcome carries a finite
    ``max_age_ms``, a sample fresh at selection but stale at evaluation is
    INVALID. With a known uncertainty the conservative interval
    ``[value - |u|, value + |u|]`` must fit inside the inclusive bounds for
    BOTH ``assert`` and ``if``; when uncertainty is unknown and explicitly
    permitted, the nominal value is compared alone.
    """
    outcome = samples.get(str(predicate["sample"]))
    if not isinstance(outcome, SampleOutcome):
        return None
    if outcome.invalid_reason is not None or outcome.value is None:
        return None
    if evaluated_at_wall is not None and _recheck_stale(outcome, evaluated_at_wall):
        return None
    minimum = predicate["minimum"]
    maximum = predicate["maximum"]
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, (int, float))
        or isinstance(maximum, bool)
        or not isinstance(maximum, (int, float))
    ):
        return None
    if outcome.uncertainty is not None:
        low = outcome.value - outcome.uncertainty
        high = outcome.value + outcome.uncertainty
        return bool(low >= minimum and high <= maximum)
    return bool(minimum <= outcome.value <= maximum)


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
        # Occurrence-keyed issued-id registry: minted by $stg_issue during
        # resolution, invalidated when the issuing step's operation fails,
        # and copied into the occurrence-ledger entry for observability.
        self._issued: dict[Occurrence, dict[str, dict[str, str]]] = {}

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
            result = self._step_read(step, scope, index_path, body, event)
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
            body.terminate(
                BODY_EXECUTION_ERROR, f"unknown step kind {kind!r} at {step_id}"
            )
            return None
        issued_here = self._issued.get(occurrence)
        entry: dict[str, Any] = {"event": event, "result": result}
        if issued_here:
            if kind in ("invoke", "read", "write") and not (
                isinstance(result, OperationResult)
                and result.status is OperationStatus.OK
            ):
                for record in issued_here.values():
                    record["status"] = "invalidated"
            entry["issued_ids"] = {
                field: dict(record) for field, record in issued_here.items()
            }
        if body.outcome is not None:
            # This step ended the body (outcome was clear when it started);
            # replay must terminate the same way.
            entry["outcome"] = body.outcome
            entry["reason"] = body.reasons[-1]
        self._ledger[occurrence] = entry
        return result

    # -- operation kinds --------------------------------------------------------

    def _resolve_context(
        self, role: str, step_id: str, index_path: tuple[int, ...], body: _Body
    ) -> ResolveContext:
        """Everything reference resolution needs for one occurrence."""
        return ResolveContext(
            run_id=body.run_id,
            step_id=step_id,
            index_path=index_path,
            channels=self._binding.channels_by_role.get(role, {}),
            issued_ids=self._issued,
        )

    def _resolve_input(
        self,
        value: Any,
        scope: ChainMap[str, Any],
        role: str,
        step_id: str,
        index_path: tuple[int, ...],
        body: _Body,
        event: dict[str, Any],
    ) -> tuple[bool, Any]:
        """Resolve one dispatch input; an unresolvable one ends the body."""
        try:
            resolved = resolve_value(
                value,
                scope,
                role,
                context=self._resolve_context(role, step_id, index_path, body),
            )
            return True, resolved
        except ScopeError as error:
            event["status"] = "error"
            event["error_code"] = "UNRESOLVED_REFERENCE"
            body.terminate(
                BODY_EXECUTION_ERROR, f"unresolved_reference: {step_id}: {error}"
            )
            return False, None

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
        resolved, resolved_input = self._resolve_input(
            step["input"], scope, role, step_id, index_path, body, event
        )
        if not resolved:
            return None
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
        scope: ChainMap[str, Any],
        index_path: tuple[int, ...],
        body: _Body,
        event: dict[str, Any],
    ) -> OperationResult | None:
        step_id = str(step["id"])
        role = str(step["role"])
        try:
            # Read parameters are literals by schema (a declared parameter
            # name); the runtime rejects references in that position through
            # the same seam instead of trusting admission alone.
            if _contains_stg_directive(step["parameter"]):
                raise ScopeError("read parameter must be a literal parameter name")
            parameter = resolve_value(
                step["parameter"],
                scope,
                role,
                context=self._resolve_context(role, step_id, index_path, body),
            )
            if not isinstance(parameter, str):
                raise ScopeError(
                    f"read parameter must resolve to a string, got "
                    f"{type(parameter).__name__}"
                )
        except ScopeError as error:
            event["status"] = "error"
            event["error_code"] = "UNRESOLVED_REFERENCE"
            body.terminate(
                BODY_EXECUTION_ERROR, f"unresolved_reference: {step_id}: {error}"
            )
            return None
        device_id = self._binding.device_by_role[role]
        event["resolved_input_sha256"] = _sha256_hex({"parameter": parameter})
        operation_id = _operation_id(body.run_id, step_id, index_path)
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
        resolved, resolved_value = self._resolve_input(
            step["value"], scope, role, step_id, index_path, body, event
        )
        if not resolved:
            return None
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
    ) -> SampleOutcome:
        step_id = str(step["id"])
        source_id = str(step["source_step"])
        event["resolved_input_sha256"] = _sha256_hex(
            {
                "source_step": source_id,
                "variable_id": step["variable_id"],
                "unit": step["unit"],
                "max_age_ms": step.get("max_age_ms"),
                "require_known_uncertainty": step.get("require_known_uncertainty", False),
            }
        )
        outcome = select_sample(
            step, scope.get(source_id), evaluated_at_wall=self._wall.now_iso()
        )
        if outcome.invalid_reason is not None:
            event["status"] = "error"
            event["error_code"] = "INVALID_SAMPLE"
            body.terminate(
                BODY_EXECUTION_ERROR,
                f"sample {step_id}: INVALID ({outcome.invalid_reason})",
            )
        return outcome

    def _predicate_samples(
        self, predicate: dict[str, Any], scope: ChainMap[str, Any]
    ) -> dict[str, SampleOutcome]:
        sample_id = str(predicate["sample"])
        sample = scope.get(sample_id)
        if isinstance(sample, SampleOutcome):
            return {sample_id: sample}
        return {}

    def _evaluate_predicate(
        self, predicate: dict[str, Any], scope: ChainMap[str, Any]
    ) -> tuple[bool | None, str]:
        """Evaluate one predicate with a fresh wall read (§4 recheck).

        Returns ``(verdict, invalid_detail)``: the detail is non-empty when
        the verdict is INVALID because the evidence went stale between
        selection and evaluation.
        """
        sample = scope.get(str(predicate["sample"]))
        wall_now = self._wall.now_iso()
        held = evaluate_predicate(
            predicate,
            self._predicate_samples(predicate, scope),
            evaluated_at_wall=wall_now,
        )
        if held is not None:
            return held, ""
        stale_now = isinstance(sample, SampleOutcome) and _recheck_stale(sample, wall_now)
        return None, " (stale at evaluation)" if stale_now else ""

    def _assertion_failure_reason(
        self, predicate: dict[str, Any], scope: ChainMap[str, Any], step_id: str
    ) -> str:
        minimum = predicate["minimum"]
        maximum = predicate["maximum"]
        outcome = scope.get(str(predicate["sample"]))
        value = outcome.value if isinstance(outcome, SampleOutcome) else None
        if (
            value is not None
            and isinstance(outcome, SampleOutcome)
            and outcome.uncertainty is not None
        ):
            low = value - outcome.uncertainty
            high = value + outcome.uncertainty
            return (
                f"assert {step_id}: conservative interval [{low}, {high}] escapes "
                f"[{minimum}, {maximum}]"
            )
        return f"assert {step_id}: {value} outside [{minimum}, {maximum}]"

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
        held, invalid_detail = self._evaluate_predicate(predicate, scope)
        if held is None:
            event["status"] = "error"
            event["error_code"] = "INVALID_SAMPLE"
            body.terminate(
                BODY_EXECUTION_ERROR,
                f"assert {step_id}: sample {str(predicate['sample'])!r} is "
                f"INVALID{invalid_detail}",
            )
            return None
        if not held:
            event["status"] = "failed"
            body.terminate(
                BODY_ASSERTION_FAILED,
                self._assertion_failure_reason(predicate, scope, step_id),
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
            predicate = step["predicate"]
            held, invalid_detail = self._evaluate_predicate(predicate, scope)
            if held is None:
                event["status"] = "error"
                event["error_code"] = "INVALID_SAMPLE"
                body.terminate(
                    BODY_EXECUTION_ERROR,
                    f"if {step_id}: sample {str(predicate['sample'])!r} is "
                    f"INVALID{invalid_detail}",
                )
                self._ledger[occurrence] = {
                    "event": event,
                    "result": None,
                    "outcome": body.outcome,
                    "reason": body.reasons[-1],
                }
                return None
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
