"""The safe-transition engine and final-condition verification (§5, §7).

On the first entry to protecting, the engine fixes its deadline —
``entered_at_ns + safe_transition.max_duration_ms`` of monotonic time — and
runs the commissioned transition: the ordered safe actions, each dispatched
under ``min(action timeout, remaining protection)`` so nothing outruns the
protective budget, then verification, which polls the bench signals named by
the ``verify`` conditions until the whole conjunction holds CONTINUOUSLY for
``stable_for_ms`` within the budget. Later entries append reasons only: the
deadline is never extended and the transition is never restarted, exactly as
the execution contract demands.

Safe actions are the policy's own protective authority, admitted with the
policy at commissioning time and carrying literal arguments; they are
dispatched without a re-evaluation against the body's allow rules, because a
rule mismatch must not be able to suppress the commissioned protective
response. A failed or unknown safe action is recorded, and the remaining
non-conflicting actions are still attempted within the remaining budget.

Verification truth: a conjunction that cannot be observed stable within the
budget yields ``unknown``, never ``verified`` — a missing, stale, wrong-unit
or error-unknown signal invalidates its condition and resets the stability
window. This module never decides the terminal outcome; mapping body outcome
plus safe state onto the terminal truth table is the coordinator's single
§5 function.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from benchweave.control.clocking import MonotonicClock, WallClock
from benchweave.control.policy import SignalValue, evaluate_conditions
from benchweave.host.plugin import DevicePlugin
from benchweave.host.types import (
    OperationRequest,
    OperationStatus,
    OperationVerb,
    Quality,
    Reading,
)

SAFE_VERIFIED = "verified"
SAFE_UNKNOWN = "unknown"

_DEFAULT_POLL_MS = 10


@dataclass(frozen=True)
class ProtectionResult:
    """One protective transition's truth: safe state, reasons, actions.

    ``safe_state`` is ``verified`` only when the verify conjunction was
    observed continuously stable inside the fixed budget; ``reasons``
    accumulates every entry reason (faults escalate, never reset) plus safe
    -action failure notes; ``actions`` records each attempted safe action
    with its outcome. ``entered_at_ns`` / ``deadline_ns`` carry the captured
    first-entry timing so callers can value-assert that the deadline was
    fixed once.
    """

    safe_state: str
    reasons: list[str]
    actions: list[dict[str, Any]]
    entered_at_ns: int
    deadline_ns: int


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


def _nonnegative_float(value: Any) -> float | None:
    """A finite nonnegative number, or None when absent/unknown."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def read_signal_values(
    plugins: dict[str, DevicePlugin],
    bench: dict[str, Any],
    *,
    deadline_ns: int,
    wall_now: str,
) -> dict[str, SignalValue]:
    """Build one bench-signal snapshot from fresh plugin parameter reads.

    Each bench signal's ``parameter`` source is read through the bound
    plugin (a non-state-changing observation, so no allow rule applies).
    Freshness is decided HERE, where the snapshot is built: the reading's
    age is measured from its own ``observed_at`` stamp against the bench
    signal's ``max_age_ms`` — host receive time alone cannot refresh an old
    device buffer. A missing device, failed read, non-numeric value, bad
    quality or lapsed freshness marks the signal invalid, which makes its
    conditions INVALID downstream.
    """
    snapshot: dict[str, SignalValue] = {}
    now = _parse_wall(wall_now)
    for signal in bench["signals"]:
        signal_id = str(signal["id"])
        source = signal.get("source", {})
        plugin = plugins.get(str(source.get("device_id")))
        reading: Reading | None = None
        if plugin is not None and source.get("kind") == "parameter":
            request = OperationRequest.read(
                f"signal:{signal_id}", parameter=str(source.get("parameter"))
            )
            result = plugin.dispatch(request, deadline_ns=deadline_ns)
            if result.status is OperationStatus.OK and isinstance(result.data, Reading):
                reading = result.data
        value: float | None = None
        unit: str | None = None
        age_ms = 0
        valid = False
        if reading is not None and now is not None:
            unit = reading.unit if isinstance(reading.unit, str) else None
            observed = _parse_wall(reading.observed_at)
            if observed is not None:
                age_ms = max(0, int((now - observed).total_seconds() * 1000.0))
            raw = reading.value
            if (
                isinstance(raw, (int, float))
                and not isinstance(raw, bool)
                and reading.quality is Quality.VALID
                and observed is not None
                and age_ms <= int(signal["max_age_ms"])
            ):
                valid = True
                value = float(raw)
        error = signal.get("absolute_error")
        snapshot[signal_id] = SignalValue(
            signal_id=signal_id,
            value=value if value is not None else 0.0,
            unit=unit if unit is not None else "",
            age_ms=age_ms,
            valid=valid,
            absolute_error=_nonnegative_float(error),
        )
    return snapshot


class ProtectionEngine:
    """Runs the commissioned safe transition under a fixed budget."""

    def __init__(
        self,
        plugins: dict[str, DevicePlugin],
        policy: dict[str, Any],
        bench: dict[str, Any],
        clock: MonotonicClock,
        wall: WallClock,
    ) -> None:
        self._plugins = plugins
        self._policy = policy
        self._bench = bench
        self._clock = clock
        self._wall = wall
        self._reasons: list[str] = []
        self._actions: list[dict[str, Any]] = []
        self._entered_at_ns: int | None = None
        self._deadline_ns: int | None = None
        self._standing: str | None = None
        self._in_transition = False

    @property
    def entered(self) -> bool:
        """True once the first entry fixed the protection deadline."""
        return self._entered_at_ns is not None

    @property
    def protection_deadline_ns(self) -> int | None:
        """The first-entry deadline; ``None`` before the first entry."""
        return self._deadline_ns

    def _fixed_deadline(self) -> int:
        """The captured deadline, narrowed (only called after the first entry)."""
        assert self._deadline_ns is not None
        return self._deadline_ns

    def enter(self, reasons: list[str], entered_at_ns: int) -> ProtectionResult:
        """Enter protecting; run the transition on the first entry only.

        The first call fixes ``deadline_ns = entered_at_ns +
        safe_transition.max_duration_ms`` and executes the ordered safe
        actions followed by verification. Any later call — whether the
        transition is still running (a fault observed mid-verify) or already
        complete — only appends its reasons and returns the standing state;
        the deadline is never extended and the transition never restarts.
        """
        for reason in reasons:
            if reason not in self._reasons:
                self._reasons.append(reason)
        if self.entered:
            return self._snapshot_result()
        self._entered_at_ns = entered_at_ns
        transition = self._policy["safe_transition"]
        self._deadline_ns = entered_at_ns + int(transition["max_duration_ms"]) * 1_000_000
        self._in_transition = True
        try:
            self._dispatch_actions(transition)
            safe_state = self._verify(transition)
        finally:
            self._in_transition = False
        self._standing = safe_state
        return self._snapshot_result()

    def _snapshot_result(self) -> ProtectionResult:
        assert self._entered_at_ns is not None and self._deadline_ns is not None
        return ProtectionResult(
            safe_state=self._standing if self._standing is not None else SAFE_UNKNOWN,
            reasons=list(self._reasons),
            actions=[dict(action) for action in self._actions],
            entered_at_ns=self._entered_at_ns,
            deadline_ns=self._deadline_ns,
        )

    def _dispatch_actions(self, transition: dict[str, Any]) -> None:
        """Attempt the ordered safe actions within the remaining budget."""
        protection_deadline = self._fixed_deadline()
        for action in transition.get("actions", []):
            action_id = str(action["id"])
            now = self._clock.now_ns()
            timeout_ns = int(action["timeout_ms"]) * 1_000_000
            deadline_ns = min(now + timeout_ns, protection_deadline)
            record: dict[str, Any] = {
                "id": action_id,
                "device_id": str(action["device_id"]),
                "deadline_ns": deadline_ns,
                "status": "error",
                "error": None,
            }
            plugin = self._plugins.get(str(action["device_id"]))
            request = self._safe_action_request(action)
            if plugin is None or request is None:
                record["error"] = "unknown_device" if plugin is None else "unsupported_kind"
            else:
                result = plugin.dispatch(request, deadline_ns=deadline_ns)
                record["status"] = result.status.value
                if result.status is not OperationStatus.OK and result.error is not None:
                    record["error"] = (
                        f"{result.error.code.value}: {result.error.message}"
                    )
            self._actions.append(record)
            if record["status"] != "ok":
                self._append_reason(f"safe_action {action_id}: {record['status']}")

    def _safe_action_request(self, action: dict[str, Any]) -> OperationRequest | None:
        """Build the typed request for one declared safe action."""
        operation_id = f"protect:{action['id']}"
        kind = action.get("kind")
        if kind == "invoke":
            return OperationRequest(
                operation_id=operation_id,
                verb=OperationVerb.INVOKE,
                arguments={
                    "action_id": str(action["action_id"]),
                    "input": dict(action["input"]),
                },
            )
        if kind == "write":
            return OperationRequest.write(
                operation_id,
                parameter=str(action["parameter"]),
                value=action["value"],
            )
        return None

    def _append_reason(self, reason: str) -> None:
        if reason not in self._reasons:
            self._reasons.append(reason)

    def _poll_ns(self) -> int:
        """The fastest declared signal poll period, as nanoseconds."""
        polls = [
            int(signal["poll_ms"])
            for signal in self._bench["signals"]
            if isinstance(signal.get("poll_ms"), int)
        ]
        return max(1, min(polls, default=_DEFAULT_POLL_MS)) * 1_000_000

    def _verify(self, transition: dict[str, Any]) -> str:
        """Poll the verify conjunction until continuously stable or budget end.

        Continuity is observed at the bench's declared poll cadence: while
        the conjunction holds, only the stability remainder is waited; any
        violated or INVALID condition resets the window. The loop ends with
        ``verified`` only inside the fixed budget, else ``unknown``.
        """
        verify = list(transition.get("verify", []))
        stable_ns = int(transition.get("stable_for_ms", 0)) * 1_000_000
        poll_ns = self._poll_ns()
        protection_deadline = self._fixed_deadline()
        stable_since: int | None = None
        while True:
            now = self._clock.now_ns()
            remaining = protection_deadline - now
            if remaining <= 0:
                return SAFE_UNKNOWN
            snapshot = read_signal_values(
                self._plugins,
                self._bench,
                deadline_ns=protection_deadline,
                wall_now=self._wall.now_iso(),
            )
            violations = evaluate_conditions({"continuous_conditions": verify}, snapshot)
            if not violations:
                if stable_since is None:
                    stable_since = now
                held_ns = now - stable_since
                if held_ns >= stable_ns:
                    return SAFE_VERIFIED
                self._clock.wait_ns(min(stable_ns - held_ns, remaining))
            else:
                stable_since = None
                self._clock.wait_ns(min(poll_ns, remaining))
