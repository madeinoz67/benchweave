"""The run-owned streaming composition (issue #167, design Decisions 2–5).

One :class:`RunStreamHost` per run, minted in ``build_run`` beside the ONE
shared :class:`~benchweave.host.services.ReadingSinks`: it holds every
bridge/``StreamController`` pair the run constructed so the coordinator can
arm, drive and tear them down as ONE composition —

* **arm** — subscriptions derive solely from the admitted bench document's
  declared signals (Decision 3), issued as ``stream_subscribe`` dispatches
  through the wrapped plugin so monitor ticks wrap them like every
  dispatch;
* **drive** — poll rounds run only inside the monitoring clock's
  wait-slice rhythm, each poll bounded to one slice
  (``poll_slice_ns == bench_poll_ns(bench)``, Decision 4's one derivation);
* **teardown** — exit-path-owned (Decision 5): body-end unsubscribe
  dispatches, a controller sweep for anything still live, with
  ``plugin_close`` as the last-resort sweep — never the ``on_event``
  callback returning cleanly;
* **containment** — the ``on_event`` the run hands the poll engine is a
  contained dispatcher shaped on ``ReadingSinks.deliver``: a raising
  consumer increments :attr:`event_callback_failures` and logs
  (machine-prefixed); the raise never propagates into ``poll_round`` and
  cannot fail a landing (the event landed transactionally before the
  callback fired).

The candidate invariant CTL-13 anchors here. The construction slice lands
the holder (registration and shared state); arming, driving and teardown
land with the composition slice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Annotation-only: the host depends on the composed SHAPES, not their
    # modules at runtime.
    from benchweave.content.stream_services import StreamController
    from benchweave.control.clocking import MonotonicClock
    from benchweave.control.stream_polling import StreamPollEngine
    from benchweave.host.otdp_bridge import OTDPBridge


class _StreamDevice:
    """One constructed streaming bridge: the bridge and its controller."""

    def __init__(
        self, device_id: str, bridge: OTDPBridge, controller: StreamController
    ) -> None:
        self.device_id = device_id
        self.bridge = bridge
        self.controller = controller
        #: The device's poll engine — armed with the run monitor, one per
        #: streaming bridge (the engine multiplexes the bridge's
        #: subscriptions internally).
        self.engine: StreamPollEngine | None = None


class RunStreamHost:
    """Run-scoped holder for the streaming composition the run constructed."""

    def __init__(self, *, run_id: str, clock: MonotonicClock) -> None:
        self._run_id = run_id
        self._clock = clock
        self._devices: dict[str, _StreamDevice] = {}
        #: Run-visible failure counter for the contained ``on_event``
        #: dispatcher (Decision 5, clause 1).
        self.event_callback_failures = 0
        #: The derived poll slice — ``bench_poll_ns(bench)``, set at arming
        #: (Decision 4: one derivation, equality by construction, no knob).
        self.poll_slice_ns: int | None = None
        #: Subscription ids the run issued at arming (device_id -> ids).
        self.subscriptions: dict[str, list[str]] = {}

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def clock(self) -> MonotonicClock:
        return self._clock

    @property
    def devices(self) -> dict[str, _StreamDevice]:
        """The registered stream devices keyed by bench device id."""
        return dict(self._devices)

    @property
    def armed(self) -> bool:
        return self.poll_slice_ns is not None

    def register(self, device_id: str, bridge: OTDPBridge, controller: StreamController) -> None:
        """Hold one constructed bridge/controller pair for the run.

        Registration is construction-time (the run owns the controllers it
        constructed — teardown authority comes with ownership).
        """
        if device_id in self._devices:
            raise ValueError(f"stream device registered twice: {device_id!r}")
        self._devices[device_id] = _StreamDevice(device_id, bridge, controller)
