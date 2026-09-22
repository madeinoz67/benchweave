"""The stream poll engine: poll-slice multiplexing with monitor ticks
between polls (issue #43 slice 2, Decision 4 — the named mini-Option-B
machinery).

Derivations: each next_event is bounded to one poll slice mirroring the
_MonitoringClock.wait_ns contract (deadline-sliced, a tick at each slice
boundary); monitor ticks run between polls; a long poll is never a
monitoring blackout because no single next_event can outrun the slice the
engine handed it (Decision 4's poll-engine paragraph). The bounded polling
budget is spec §8 ("Calls to next_event have a bounded polling budget so
control is not blocked indefinitely").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from benchweave.control.clocking import TestClock
from benchweave.control.stream_polling import StreamPollEngine
from benchweave.host.otdp_bridge import PollOutcome
from benchweave.host.types import DispatchState, ErrorCode, OperationError

SLICE_NS = 10_000_000  # one poll slice: 10 ms


@dataclass
class Harness:
    """A recording fake poller + tick + live registry over a TestClock."""

    clock: TestClock = field(default_factory=TestClock)
    ticks: int = 0
    # (subscription_id, called_at_ns, deadline_ns) per poll
    polls: list[tuple[str, int, int]] = field(default_factory=list)
    # subscription_id -> scripted outcomes popped per poll; None (absent)
    # means quiet
    script: dict[str, list[PollOutcome]] = field(default_factory=dict)
    live: list[str] = field(default_factory=lambda: ["sub-a", "sub-b"])
    stop_after_ticks: int | None = None

    def tick(self) -> None:
        self.ticks += 1

    def stopped(self) -> bool:
        return self.stop_after_ticks is not None and self.ticks >= self.stop_after_ticks

    def poll(self, subscription_id: str, *, deadline_ns: int) -> PollOutcome:
        self.polls.append((subscription_id, self.clock.now_ns(), deadline_ns))
        queue = self.script.get(subscription_id)
        if queue:
            outcome = queue.pop(0)
            if outcome.refusal is not None:
                # The fake mirrors the real registry contract: a refusal has
                # always ended the subscription by the time it is reported.
                self.live = [sid for sid in self.live if sid != subscription_id]
            return outcome
        return PollOutcome()

    def engine(self) -> StreamPollEngine:
        return StreamPollEngine(
            poll=self.poll,
            live=lambda: list(self.live),
            clock=self.clock,
            tick=self.tick,
            poll_slice_ns=SLICE_NS,
            stop=self.stopped,
        )


def an_event_outcome(sequence: int = 0) -> PollOutcome:
    return PollOutcome(
        event={"subscription_id": "sub-a", "sequence": sequence, "kind": "telemetry"},
        host_received_at="2026-09-22T00:00:00Z",
    )


def a_refusal(code: ErrorCode = ErrorCode.INVALID_ARGUMENT) -> PollOutcome:
    return PollOutcome(
        refusal=OperationError(code, "refused", DispatchState.NOT_DISPATCHED)
    )


def test_each_poll_is_bounded_to_one_poll_slice() -> None:
    """The wait-slice contract: no single next_event deadline exceeds one
    poll slice from the moment the engine handed it over."""
    harness = Harness()
    engine = harness.engine()
    deadline = harness.clock.now_ns() + 5 * SLICE_NS
    engine.poll_until(deadline_ns=deadline, on_event=lambda *args: None)
    assert harness.polls, "the engine must poll"
    for subscription_id, called_at, poll_deadline in harness.polls:
        assert poll_deadline - called_at <= SLICE_NS, (
            f"poll of {subscription_id} was handed {poll_deadline - called_at} ns, "
            f"above the {SLICE_NS} ns slice"
        )


def test_monitor_ticks_run_between_polls() -> None:
    """A long poll is never a monitoring blackout: at least one tick per
    poll, plus the round boundaries."""
    harness = Harness()
    engine = harness.engine()
    deadline = harness.clock.now_ns() + 3 * SLICE_NS
    engine.poll_until(deadline_ns=deadline, on_event=lambda *args: None)
    assert harness.ticks >= len(harness.polls)


def test_the_poll_deadline_is_never_extended_past_the_engine_deadline() -> None:
    harness = Harness()
    engine = harness.engine()
    deadline = harness.clock.now_ns() + SLICE_NS // 2  # tighter than a slice
    engine.poll_until(deadline_ns=deadline, on_event=lambda *args: None)
    for _subscription_id, _called_at, poll_deadline in harness.polls:
        assert poll_deadline <= deadline


def test_a_refusal_drops_the_subscription_from_rotation() -> None:
    harness = Harness()
    harness.script["sub-b"] = [a_refusal()]
    engine = harness.engine()
    deadline = harness.clock.now_ns() + 4 * SLICE_NS
    refused = engine.poll_until(deadline_ns=deadline, on_event=lambda *args: None)
    assert refused == ["sub-b"]
    b_polls = [poll for poll in harness.polls if poll[0] == "sub-b"]
    assert len(b_polls) == 1  # refused once, never again
    a_polls = [poll for poll in harness.polls if poll[0] == "sub-a"]
    assert len(a_polls) >= 2  # the live stream keeps being polled


def test_a_failed_bridge_session_stops_the_engine() -> None:
    harness = Harness()
    harness.script["sub-a"] = [
        PollOutcome(
            refusal=OperationError(
                ErrorCode.PROTOCOL_ERROR, "protocol lie", DispatchState.UNKNOWN
            ),
            session_failed=True,
        )
    ]
    engine = harness.engine()
    deadline = harness.clock.now_ns() + 5 * SLICE_NS
    refused = engine.poll_until(deadline_ns=deadline, on_event=lambda *args: None)
    assert refused == []  # a session failure is not a per-subscription refusal
    polled = [poll[0] for poll in harness.polls]
    assert polled == ["sub-a"]  # the engine stopped at the first failure
    assert engine.session_failed  # latched: later rounds never re-poll a dead session


def test_a_terminal_monitor_cause_stops_the_engine() -> None:
    harness = Harness()
    harness.stop_after_ticks = 2  # the cause arrives after two ticks
    engine = harness.engine()
    deadline = harness.clock.now_ns() + 5 * SLICE_NS
    engine.poll_until(deadline_ns=deadline, on_event=lambda *args: None)
    assert len(harness.polls) <= 2  # the stop was honored mid-round


def test_events_flow_to_the_callback_with_their_receipts() -> None:
    harness = Harness()
    harness.script["sub-a"] = [an_event_outcome(0), an_event_outcome(1)]
    harness.script["sub-b"] = [an_event_outcome(0)]
    engine = harness.engine()
    seen: list[tuple[str, object, str]] = []
    deadline = harness.clock.now_ns() + 3 * SLICE_NS
    engine.poll_until(
        deadline_ns=deadline,
        on_event=lambda subscription_id, event, receipt: seen.append(
            (subscription_id, event["sequence"], receipt)
        ),
    )
    assert ("sub-a", 0, "2026-09-22T00:00:00Z") in seen
    assert ("sub-b", 0, "2026-09-22T00:00:00Z") in seen
    assert ("sub-a", 1, "2026-09-22T00:00:00Z") in seen


def test_an_empty_rotation_ends_the_round_early() -> None:
    harness = Harness()
    harness.live = []
    engine = harness.engine()
    deadline = harness.clock.now_ns() + 5 * SLICE_NS
    refused = engine.poll_until(deadline_ns=deadline, on_event=lambda *args: None)
    assert refused == []
    assert harness.polls == []


def test_one_round_drives_polls_outside_delay_steps() -> None:
    """The named scope: driving polls does not require a delay step — one
    poll_round call polls every live subscription exactly once and returns
    (the executor's delay rhythm is one caller of this, not the only one)."""
    harness = Harness()
    engine = harness.engine()
    refused = engine.poll_round(
        deadline_ns=harness.clock.now_ns() + 5 * SLICE_NS,
        on_event=lambda *args: None,
    )
    assert refused == []
    assert [poll[0] for poll in harness.polls] == ["sub-a", "sub-b"]
    assert len(harness.polls) == 2  # exactly once each, no pacing wait


def a_quiet_pace(outcomes: dict[str, list[PollOutcome]]) -> Any:
    return outcomes
