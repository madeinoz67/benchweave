"""The run-owned streaming composition (issue #167, design Decisions 2–5).

One :class:`RunStreamHost` per run, minted in ``build_run`` beside the ONE
shared :class:`~benchweave.host.services.ReadingSinks`: it holds every
bridge/``StreamController`` pair the run constructed so the coordinator can
arm, drive and tear them down as ONE composition —

* **arm** — subscriptions derive solely from the admitted bench document's
  declared signals (Decision 3): for each signal whose source device is a
  registered streaming bridge, ``parameters=(signal.source.parameter,)``
  and ``min_interval_ms = signal.poll_ms``, subscription id host-minted,
  issued as a ``stream_subscribe`` dispatch THROUGH the wrapped plugin so
  monitor ticks wrap it like every dispatch. Refusals degrade loudly and
  never fail the run (R15): a bench commissioning faster than the
  descriptor's declared floor simply has no stream for that signal — the
  monitor's read-based snapshot is unaffected;
* **drive** — poll rounds run only inside the monitoring clock's
  wait-slice rhythm, each poll bounded to one slice
  (``poll_slice_ns == bench_poll_ns(bench)``, Decision 4's one derivation,
  equality by construction, no knob);
* **teardown** — exit-path-owned (Decision 5): body-end unsubscribe
  dispatches (ticked like any dispatch), a controller sweep for anything
  still live, with ``plugin_close`` as the last-resort sweep — never the
  ``on_event`` callback returning cleanly;
* **containment** — the ``on_event`` the run hands the poll engine is a
  contained dispatcher shaped on ``ReadingSinks.deliver``: a raising
  consumer increments :attr:`event_callback_failures` and logs
  (machine-prefixed); the raise never propagates into ``poll_round`` and
  cannot fail a landing (the event landed transactionally before the
  callback fired).

The candidate invariant CTL-13 anchors here: subscriptions derive solely
from admitted bench declarations; polls run only inside the wait-slice
rhythm; ``poll_slice_ns`` equals ``bench_poll_ns`` by the one derivation
and is never finer; teardown is exit-path-owned; ``on_event`` is contained
at the run boundary; one shared ``ReadingSinks`` and one run context key
per run.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from benchweave.control.stream_polling import StreamPollEngine
from benchweave.host.types import OperationRequest, OperationStatus, OperationVerb

if TYPE_CHECKING:
    from benchweave.content.stream_services import StreamController
    from benchweave.control.clocking import MonotonicClock
    from benchweave.control.coordinator import _RunMonitor
    from benchweave.host.otdp_bridge import OTDPBridge
    from benchweave.host.plugin import DevicePlugin

_LOG = logging.getLogger(__name__)

#: One stream-verb dispatch's operational deadline (seconds). A transport
#: bound, not a protective parameter (the bridge's own lifecycle-timeout
#: class): it bounds a subscribe/unsubscribe roundtrip so a hung adapter
#: cannot stall the ending — the refusal path degrades loudly either way.
_DISPATCH_BUDGET_S = 5.0


class _StreamDevice:
    """One constructed streaming bridge: the bridge and its controller."""

    def __init__(self, device_id: str, bridge: OTDPBridge, controller: StreamController) -> None:
        self.device_id = device_id
        self.bridge = bridge
        self.controller = controller
        #: The device's poll engine — one per streaming bridge (the engine
        #: multiplexes the bridge's subscriptions internally).
        self.engine: StreamPollEngine | None = None


class RunStreamHost:
    """Run-scoped holder and driver for the streaming composition."""

    def __init__(self, *, run_id: str, clock: MonotonicClock) -> None:
        self._run_id = run_id
        self._clock = clock
        self._devices: dict[str, _StreamDevice] = {}
        # EVERY bridge the run constructed (F1): end-of-run close authority
        # is ownership, not stream registration — an event_sink-less
        # commissioned bridge leaks its Runner and adapter session if only
        # the streaming registry is closed.
        self._bridges: dict[str, OTDPBridge] = {}
        #: Run-visible failure counter for the contained ``on_event``
        #: dispatcher (Decision 5, clause 1).
        self.event_callback_failures = 0
        #: The derived poll slice — ``bench_poll_ns(bench)``, set at arming
        #: (Decision 4: one derivation, equality by construction, no knob).
        self.poll_slice_ns: int | None = None
        #: The run's ``on_event`` consumer, invoked inside the contained
        #: dispatcher for every event a poll lands. Replaceable so a run's
        #: observers can hook telemetry; the default records nothing (the
        #: landed ``event_log`` evidence IS the record — the callback is an
        #: observation channel, not a persistence path).
        self.on_event: Any = lambda subscription_id, event, receipt: None
        #: Subscription ids the run issued at arming (device_id -> ids) —
        #: the composition's own bookkeeping for teardown accounting.
        self.subscriptions: dict[str, list[str]] = {}
        #: M-A measurement seam (F5): when set before the run starts, every
        #: monitor tick — dispatch-driven and engine-driven alike — is
        #: timestamped through it, so the worst-tick-gap-over-windows axis
        #: reads off the composed run without touching the monitor.
        self.tick_recorder: Any = None

    # -- construction-time surface --------------------------------------------------

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
    def bridges(self) -> dict[str, OTDPBridge]:
        """Every constructed bridge keyed by bench device id (the close set)."""
        return dict(self._bridges)

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
        self.adopt(device_id, bridge)
        self._devices[device_id] = _StreamDevice(device_id, bridge, controller)

    def adopt(self, device_id: str, bridge: OTDPBridge) -> None:
        """Hold one constructed bridge for end-of-run close.

        Every commissioned bridge is adopted — with or without event
        services (F1): ``close()`` is the run's single close authority.
        """
        self._bridges[device_id] = bridge

    # -- arming (Decision 3) ----------------------------------------------------------

    def arm(
        self,
        bench: dict[str, Any],
        wrapped_plugins: dict[str, DevicePlugin],
        monitor: _RunMonitor,
    ) -> None:
        """Derive the run's subscriptions from the bench's declared signals.

        Called after monitor arming in ``_prepare_run``'s composition. The
        slice is derived ONCE here (``bench_poll_ns`` — the same single
        derivation every other consumer uses) and never re-derived.
        """
        from benchweave.content.stream_services import mint_subscription_id
        from benchweave.control.protection import bench_poll_ns

        if self.armed:
            raise RuntimeError(f"stream host armed twice for run {self._run_id!r}")
        self.poll_slice_ns = bench_poll_ns(bench)
        recorder = self.tick_recorder
        if recorder is not None:
            # The seam wraps the monitor's tick at the INSTANCE level, so
            # every caller (dispatch wrappers, the engine's between-poll
            # ticks, the wait-slice boundaries) is observed — a harness
            # measurement hook, never a behavior change.
            original_tick = monitor.tick

            def observed_tick() -> None:
                recorder(time.monotonic())
                original_tick()

            monitor.tick = observed_tick  # type: ignore[method-assign]
        for signal in bench.get("signals", []):
            source = signal.get("source") or {}
            if source.get("kind") != "parameter":
                continue
            device_id = str(source.get("device_id"))
            entry = self._devices.get(device_id)
            plugin = wrapped_plugins.get(device_id)
            if entry is None or plugin is None:
                continue
            signal_id = str(signal.get("id"))
            poll_ms = signal.get("poll_ms")
            if not isinstance(poll_ms, int) or poll_ms < 1:
                _LOG.warning(
                    "stream_signal_skipped: signal=%s run=%s declares no usable poll_ms",
                    signal_id, self._run_id,
                )
                continue
            subscription_id = mint_subscription_id()
            request = OperationRequest(
                operation_id=f"stream:{self._run_id}:{signal_id}",
                verb=OperationVerb.STREAM_SUBSCRIBE,
                arguments={
                    "subscription_id": subscription_id,
                    # The closed §5 argument set demands a LIST of parameter
                    # names (the corpus pattern); the bench signal names one.
                    "parameters": [str(source.get("parameter"))],
                    "min_interval_ms": poll_ms,
                },
            )
            deadline_ns = self._clock.now_ns() + int(_DISPATCH_BUDGET_S * 1_000_000_000)
            result = plugin.dispatch(request, deadline_ns=deadline_ns)
            if result.status is not OperationStatus.OK:
                # Loud degradation, never a failed run (R15): the signal
                # has no stream; the monitor's read-based snapshot is
                # unaffected.
                code = result.error.code.value if result.error is not None else "unknown"
                _LOG.warning(
                    "stream_subscribe_refused: signal=%s device=%s run=%s code=%s %s",
                    signal_id, device_id, self._run_id, code,
                    result.error.message if result.error is not None else "",
                )
                continue
            self.subscriptions.setdefault(device_id, []).append(subscription_id)
            if entry.engine is None:
                entry.engine = StreamPollEngine(
                    poll=entry.bridge.poll_event,
                    live=entry.controller.live_subscription_ids,
                    clock=self._clock,
                    tick=monitor.tick,
                    poll_slice_ns=self.poll_slice_ns,
                    stop=lambda: monitor.cause is not None,
                )
            _LOG.info(
                "stream_subscribed: signal=%s device=%s run=%s subscription=%s",
                signal_id, device_id, self._run_id, subscription_id,
            )

    # -- driving (Decision 4: inside the wait-slice rhythm only) -----------------------

    def poll_slice(self, *, deadline_ns: int) -> None:
        """One wait slice's poll round across every armed engine.

        Each engine's ``poll_round`` bounds every poll to one slice and
        ticks the monitor between polls itself (the engine's constructor
        contract); the caller sleeps the slice's unspent remainder so the
        wait's total duration is preserved.
        """
        for entry in self._devices.values():
            if entry.engine is None:
                continue
            if entry.engine.session_failed or self._clock.now_ns() >= deadline_ns:
                continue
            entry.engine.poll_round(deadline_ns=deadline_ns, on_event=self._contained_on_event)

    def _contained_on_event(
        self, subscription_id: str, event: dict[str, Any], receipt: str
    ) -> None:
        """The contained dispatcher (Decision 5, clause 1).

        Shaped on ``ReadingSinks.deliver``: a raising consumer counts and
        logs; the raise never escapes into ``poll_round``, and it cannot
        fail a landing — the event was already landed transactionally
        inside ``poll_event`` before this callback fired.
        """
        try:
            self.on_event(subscription_id, event, receipt)
        except Exception:
            self.event_callback_failures += 1
            _LOG.exception(
                "stream_on_event_contained: subscription=%s run=%s",
                subscription_id, self._run_id,
            )

    # -- teardown (Decision 5, clauses 2–3: exit-path-owned) ----------------------------

    def teardown(self, wrapped_plugins: dict[str, DevicePlugin]) -> None:
        """Body-end teardown, before the protective transition.

        For each live subscription, a ``stream_unsubscribe`` dispatch
        (ticked like any dispatch — the caller moves the monitor out of the
        body phase first so a terminal cause cannot block the ending);
        anything still live afterwards (refused, poisoned) is swept
        directly through the controller with a ``run_body_end``
        host-cause ended marker. No drain-before-unsubscribe (A12): the
        teardown marker is the record.
        """
        for device_id, entry in sorted(self._devices.items()):
            plugin = wrapped_plugins.get(device_id)
            for subscription_id in entry.controller.live_subscription_ids():
                if plugin is None:
                    break
                request = OperationRequest(
                    operation_id=f"stream-end:{self._run_id}:{subscription_id}",
                    verb=OperationVerb.STREAM_UNSUBSCRIBE,
                    arguments={"subscription_id": subscription_id},
                )
                deadline_ns = self._clock.now_ns() + int(_DISPATCH_BUDGET_S * 1_000_000_000)
                result = plugin.dispatch(request, deadline_ns=deadline_ns)
                if result.status is not OperationStatus.OK:
                    code = result.error.code.value if result.error is not None else "unknown"
                    _LOG.warning(
                        "stream_unsubscribe_refused: subscription=%s device=%s run=%s "
                        "code=%s — the controller sweep below is the record",
                        subscription_id, device_id, self._run_id, code,
                    )
            torn = entry.controller.sweep(reason="run_body_end")
            for subscription_id in torn:
                _LOG.info(
                    "stream_swept: subscription=%s device=%s run=%s cause=run_body_end",
                    subscription_id, device_id, self._run_id,
                )

    def close(self) -> None:
        """The last-resort sweep: close every constructed bridge.

        Runs after the terminal record (protection needed the bridges
        open), and on every exit path that leaves bridges open — a raising
        ``build_run`` or a raising ``start_run`` closes through here too
        (F1). ``plugin_close`` is the bridge's own final sweep of anything
        still live plus the loader/runner release, and is idempotent.
        Contained — a close failure is logged, never raised into the
        caller's ending.
        """
        for device_id, bridge in sorted(self._bridges.items()):
            try:
                bridge.plugin_close()
            except Exception:
                _LOG.exception(
                    "stream_close_failed: device=%s run=%s", device_id, self._run_id
                )
