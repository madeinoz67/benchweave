"""The stream poll engine: mini-Option-B machinery inside the executor's
wait-slice rhythm (issue #43 slice 2, Decision 4).

No round-robin engine existed in the tree — this module is the named
slice-2 construction. It multiplexes ``next_event`` across a bridge's live
subscriptions on the caller's thread:

* **Poll-slice bounding.** Each ``next_event`` poll is handed a deadline at
  most ONE poll slice away (``min(now + poll_slice_ns, engine_deadline)``),
  mirroring the ``_MonitoringClock.wait_ns`` contract — deadline-sliced, a
  tick at each slice boundary. A long poll is thereby never a monitoring
  blackout: no single ``next_event`` call can outrun the slice the engine
  handed it, because the bridge's asyncio timeout cuts it at that deadline
  — one residual, the R6 class: a ``next_event`` that never yields cannot
  be preempted by any asyncio timeout, and deadlines require cooperative
  adapters (the bridge docstring's boundary); the thread-level watchdog
  stays deferral row 11.
* **Monitor ticks between polls.** The injected ``tick`` (the run monitor's
  own) runs at every round boundary and between every pair of polls, so
  condition evaluation, cancel detection and lease-loss detection keep
  running while telemetry flows.
* **Driving polls outside delay steps.** ``poll_round`` polls every live
  subscription exactly once with no pacing wait — any host loop can drive
  it; ``poll_until`` paces rounds to the poll slice until the engine
  deadline. The pre-slice rhythm existed only inside ``delay`` steps; this
  engine is the mechanism the record names for polling independent of them.
* **Honest rotation.** A refusal that ended the subscription (unknown,
  ended, or torn down for quota) is reported and the live registry — the
  authority, re-read every round — stops listing it. A poll-deadline
  TIMEOUT refusal changes no registry state, so a still-live subscription
  is re-polled. A failed bridge session stops the whole engine: the
  session is dead, not one stream. One residual (the row-9 wiring's): a
  raising ``on_event`` callback escapes ``poll_round``/``poll_until``
  without the engine tearing down live subscriptions — "no stream
  outlives its host-owned subscription authority" then rests on the
  run-engine exit path that owns the callback, named here so the
  activation wiring carries it.

Delivery budget (the derivation the device guide carries, corrected by the
review wave): one event per ``next_event`` call; a round polls every live
subscription once and then waits one slice ``S``, so with per-poll
latencies ``L_i`` a round lasts ``S + ΣL_i``. The shared budget is
``N/(S + ΣL_i)`` events/s and each subscription sees at most
``1/(S + ΣL_i)``. Two asymptotes bound it: instant polls give ``N/S``
shared (two subscriptions at a 10 ms slice ≈ 200 events/s), and every poll
blocking for its full slice converges to ``1/S`` (≈100 events/s shared at
10 ms; sixteen blocking subscriptions ≈ 94 events/s). A device whose
N-variables × R-Hz product approaches the budget its poll behaviour
implies belongs on the capture or dataset lane, streaming a decimated
signal at most. The engine itself floors the slice at 1 ns
(``max(1, poll_slice_ns)``); the bench poll cadence — ``bench_poll_ns``:
the minimum declared signal ``poll_ms``, defaulting to 10 ms and floored
at 1 ms — binds ``poll_slice_ns`` at the run-engine wiring (deferral
row 9), not here.

Timebase identity (the M2 invariant): the engine slices deadlines on its
injected ``MonotonicClock`` (ns) while the bridge cuts on
``services.monotonic()`` (s) — the slice bound is only as real as those
being ONE timebase (seconds = nanoseconds/1e9 of the same clock). The
binding is the run-engine wiring's (row 9); the composition test pins it
with a shared clock and a hang-past-slice adapter whose asyncio cut
lands at the slice.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from benchweave.control.clocking import MonotonicClock

if TYPE_CHECKING:
    # Annotation-only: the engine depends on the poller's SHAPE, not the
    # bridge module at runtime.
    from benchweave.host.otdp_bridge import PollOutcome


class EventPoller(Protocol):
    """One subscription's mediated poll (the OTDPBridge.poll_event shape)."""

    def __call__(self, subscription_id: str, *, deadline_ns: int) -> PollOutcome: ...


class StreamPollEngine:
    """Round-robin ``next_event`` multiplexing under the wait-slice rhythm."""

    def __init__(
        self,
        *,
        poll: EventPoller,
        live: Callable[[], list[str]],
        clock: MonotonicClock,
        tick: Callable[[], None],
        poll_slice_ns: int,
        stop: Callable[[], bool] | None = None,
    ) -> None:
        self._poll = poll
        self._live = live
        self._clock = clock
        self._tick = tick
        # The floor mirrors _MonitoringClock's max(1, poll_ns): a slice
        # must be a positive duration even if a caller passes zero.
        self._poll_slice_ns = max(1, poll_slice_ns)
        self._stop = stop
        self.session_failed = False

    def poll_round(
        self,
        *,
        deadline_ns: int,
        on_event: Callable[[str, dict[str, object], str], None],
    ) -> list[str]:
        """Poll every live subscription exactly once, no pacing wait.

        Returns the subscriptions whose poll refused. Rotation is the live
        registry's call, re-read every round: the taxonomy's unknown,
        ended and quota refusals end the subscription before they are
        reported, but a poll-deadline TIMEOUT refusal changes no registry
        state — a still-live subscription is re-polled on the next round.
        Stops early on a terminal monitor cause, the engine deadline, or a
        failed bridge session (latched: ``session_failed`` stays set for
        later rounds too — a dead session must never be re-polled by this
        engine)."""
        refused: list[str] = []
        for subscription_id in self._live():
            self._tick()  # monitor ticks run between polls
            if self._stopped() or self.session_failed:
                return refused
            now = self._clock.now_ns()
            if now >= deadline_ns:
                return refused
            poll_deadline = min(now + self._poll_slice_ns, deadline_ns)
            outcome = self._poll(subscription_id, deadline_ns=poll_deadline)
            if outcome.session_failed:
                # The bridge session is dead — not one stream. Stop the
                # whole engine; the registry was cleared with markers.
                self.session_failed = True
                return refused
            if outcome.event is not None:
                receipt = outcome.host_received_at or ""
                on_event(subscription_id, outcome.event, receipt)
            if outcome.refusal is not None:
                refused.append(subscription_id)
        self._tick()  # the round's closing boundary tick
        return refused

    def poll_until(
        self,
        *,
        deadline_ns: int,
        on_event: Callable[[str, dict[str, object], str], None],
    ) -> list[str]:
        """Poll rounds paced to the poll slice until the engine deadline.

        Between rounds the engine waits exactly one slice (clamped to the
        remaining deadline) — never a blind wait: the round boundary ticked
        before it, and the next round ticks after it. A terminal monitor
        cause, a failed bridge session, or an empty rotation ends the
        polling early."""
        refused: list[str] = []
        while True:
            self._tick()  # the round's opening boundary tick
            if self._stopped() or self.session_failed:
                return refused
            now = self._clock.now_ns()
            if now >= deadline_ns:
                return refused
            if not self._live():
                return refused  # nothing pollable remains
            refused.extend(self.poll_round(deadline_ns=deadline_ns, on_event=on_event))
            if self._stopped():
                return refused
            now = self._clock.now_ns()
            remaining = deadline_ns - now
            if remaining <= 0:
                return refused
            # Pace to the next round: one poll slice, clamped to the
            # remaining deadline.
            self._clock.wait_ns(min(self._poll_slice_ns, remaining))

    def _stopped(self) -> bool:
        return self._stop is not None and self._stop()
