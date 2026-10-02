"""The cross-instance continuity instrument (issue #172 — row 1's rig).

The measurement rig for the #159 record's row 1: a two-instance harness
(dev-rig-a dispatches, dev-rig-b streams + carries a bench signal + the
protective write path) measuring the four frozen axes on both dispatch
arms, the consistency controls around ``T_acq_min``, and the classifier
that turns trial ledgers into arm verdicts. Every seam the axes read is a
production object (``_RunMonitor``/``retain``, ``_MonitoringPlugin``,
``_MonitoringClock``/``RunStreamHost``, ``read_signal_values``,
``ProtectionEngine``, ``OTDPBridge``'s per-instance lock); what is built
here is fixtures and bookkeeping, never a second mechanism.

Two rules live in this file's ancestry and they are NOT the same rule
(design §0):

* the FROZEN decision rule (#159 §6) — evaluated against COMMISSIONED
  bounds ``G1/G2/P/TB`` that do not exist (A02). The classifier in
  ``_continuity_rule`` implements it verbatim; every bound the table
  tests feed it is synthetic table data, and a missing bound reads
  UNDERPOWERED, never a default;
* the INSTRUMENT's own acceptance rule (design §5) — whose denominator
  is the rig's own dispatch duration and the matched control, explicitly
  NOT ``G1/G2/P/TB`` and never citable as a commissioning.

Check-6 honesty (design §3 row 6): the bit-identical ``TestClock``
fault-suite gate is defined only "under the host's wait primitive",
which does not exist on this tree — NOTHING lands for check 6 here, and
no baseline is faked against today's synchronous ``wait_ns``.

Design record:
``.claude/deep-review/2026-09-26-issue172-continuity-instrument-design.md``
(verdict BUILD; frozen parent: #159 §6).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import statistics
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from _continuity_rule import Arm, TrialRecord, classify, emit_trial_log, write_trial_log

from benchweave.content.capture_services import build_capture_services
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.store import ContentStore
from benchweave.content.stream_services import build_stream_services
from benchweave.control.clocking import SystemClock
from benchweave.control.coordinator import (
    _MonitoringClock,
    _MonitoringPlugin,
    _RunMonitor,
)
from benchweave.control.policy import SignalValue, evaluate_conditions
from benchweave.control.protection import ProtectionEngine, bench_poll_ns, read_signal_values
from benchweave.control.stream_host import RunStreamHost
from benchweave.host.otdp_bridge import OTDPBridge, PollOutcome
from benchweave.host.plugin import DevicePlugin, SimulationInfo
from benchweave.host.services import QuotaLimits
from benchweave.host.types import (
    DispatchState,
    ErrorCode,
    OperationError,
    OperationRequest,
    OperationResult,
    OperationStatus,
    OperationVerb,
)
from benchweave.state.store import Store

# The file IS one of the two real-paced rigs (issue #241 slice 1): every
# trial here measures wall-clock quantities against pacing bands, so the
# whole module runs serialized in the dedicated timing lane. The static
# classifier-table and retry-pin tests ride along — they still run in CI,
# just in the lane (sub-second cost, disclosed).
pytestmark = [pytest.mark.timing]

# --- the rig's fixture constants ----------------------------------------------------
#
# Every number here is a FIXTURE parameter for measurement discriminability
# only — never a commissioned bound (A02: numeric envelopes are commissioned
# per bench from qualification evidence) and never a T_acq_min authority
# (A09: the acquisition minimum is a device/qualification fact; the 200 ms
# pacing below is what the consistency controls assert AGAINST, §2.5).

BENCH_ID = "bench.continuity-rig"
DEVICE_A = "dev-rig-a"
DEVICE_B = "dev-rig-b"
SIG_A = "sig-rig-a-temp"
SIG_B = "sig-rig-b-level"

#: The paced acquisition duration (fixture): the non-capture arm's natural
#: dispatch duration and the capture arm's natural capture duration.
T_ACQ_MIN_MS = 200.0
#: The capture arm's declared budget — the deadline-max cut (§8(d): the
#: capture arm CUTS at the budget; the non-capture arm's deadline
#: ACCOMMODATES T_acq_min). The two arms intentionally differ in
#: completion posture; both black out ticks for their in-flight duration.
CAPTURE_BUDGET_MS = 50.0
#: The matched short-T control's budget (§2.5 control i): the acquisition
#: must FAIL (TIMEOUT/UNKNOWN, never OK).
SHORT_T_MS = 20.0
#: sig-rig-b's declared poll cadence — drives ``bench_poll_ns`` explicitly
#: (never the silent 10 ms default).
POLL_MS = 50
#: B's frame emission schedule period (the time-derived device model, §2.3).
FRAME_PERIOD_MS = 20.0
#: Dispatch-scale freshness bound — the #159 §2 pin the old fixture's
#: 600 000 ms made vacuous. A rig constant, never a commissioned G2.
#: 300 ms (1.5x the 200 ms arm) rather than the design sketch's 250: the
#: read leg's deadline-driven pacing overshoots T_acq_min by up to +24 ms
#: and one frame period (20 ms) of pre-dispatch receive lag rides on top,
#: landing the first post-tick age at ~219-250 ms — a 27-31 ms margin
#: under a 250 bound that one overshoot can eat, tripping the fail-safe
#: (signal_invalid) on pacing jitter and blocking the measured read for a
#: reason that is not the hazard. (The write leg is NOT a jitter source:
#: it runs idle-phase after the protective transition and idle-phase ticks
#: perform no signal reads.) X2 records the age whatever the validity;
#: only the condition's fail-safe reads the bound.
MAX_AGE_MS = 300

_SAFE_LEVEL = 1.0
_TRIP_LEVEL = 5.0

BENCH: dict[str, Any] = {
    "id": BENCH_ID,
    "signals": [
        {
            "id": SIG_A,
            "source": {"device_id": DEVICE_A, "kind": "parameter", "parameter": "temp"},
            "max_age_ms": MAX_AGE_MS,
            "poll_ms": 200,
            "absolute_error": 0.05,
        },
        {
            "id": SIG_B,
            "source": {"device_id": DEVICE_B, "kind": "parameter", "parameter": "level"},
            "max_age_ms": MAX_AGE_MS,
            "poll_ms": POLL_MS,
            "absolute_error": 0.05,
        },
    ],
}

POLICY: dict[str, Any] = {
    # The single continuous condition on B's signal: clean at _SAFE_LEVEL,
    # escaped at _TRIP_LEVEL (X4's hazard), clean again after the safe
    # action's write lands 0.0.
    "continuous_conditions": [
        {
            "id": "rig-b-level-bounds",
            "kind": "numeric",
            "signal": SIG_B,
            "unit": "V",
            "minimum": -0.1,
            "maximum": 4.5,
        }
    ],
    "safe_transition": {
        "max_duration_ms": 2000,
        "actions": [
            {
                "id": "b-level-zero",
                "device_id": DEVICE_B,
                "kind": "write",
                "parameter": "level",
                "value": 0.0,
                "timeout_ms": 500,
            }
        ],
        "verify": [
            {
                "id": "rig-b-level-safe",
                "kind": "numeric",
                "signal": SIG_B,
                "unit": "V",
                "minimum": -0.1,
                "maximum": 4.5,
            }
        ],
        "stable_for_ms": 100,
    },
}


#: The divergent-wall probe's variant (check 5): a 10x monitor wall
#: inflates every host-computed age past any dispatch-scale bound, so the
#: freshness condition is dropped for the probe only — it measures X1/X2,
#: not the hazard.
NO_TRIP_POLICY: dict[str, Any] = {
    "continuous_conditions": [],
    "safe_transition": POLICY["safe_transition"],
}


def _now_iso() -> str:
    return SystemClock().now_iso()


class StretchedWall:
    """A wall clock advancing ``rate`` x real time from a base epoch.

    The divergent-wall control's injection (#159 §6 machine check 5): X2's
    host-age domain is WALL (``wall_now() - observed_at`` in
    ``read_signal_values``) while X1/X3/X4 are monotonic — so stretching
    ONLY the monitor's wall must move only X2. The device/bundle wall stays
    on the real clock (the bundle stamps ``observed_at``; the monitor's
    ``wall_now`` measures it).
    """

    def __init__(self, rate: float) -> None:
        self._rate = rate
        self._t0 = time.time()
        self._base_epoch = self._t0

    def now_iso(self) -> str:
        epoch = self._base_epoch + (time.time() - self._t0) * self._rate
        return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z")


class ARigAdapter:
    """Device A (dev-rig-a): the dispatching instance.

    Serves the bench-signal read ``temp`` fast (the monitor's ticks must
    not be paced by A's own signal), the acquisition parameter
    ``acq_scalar`` paced at ``T_ACQ_MIN_MS`` in adapter-internal slices
    with NO artifact traffic (the mandatory non-capture arm, read and
    write legs), and the chunk-paced capture whose natural duration
    exceeds the declared budget (the capture arm's deadline-max shape).
    The split-refusal model (§2.5 control ii): the capture acquisition is
    one-shot per window — the window id is the capture id with its
    ``.hN`` half-suffix stripped, and a second half against a consumed
    window is device-rejected (two half-manifests cannot cover it).
    """

    def __init__(
        self, *, chunks: int = 100, chunk_ms: float = 2.0, acq_ms: float = T_ACQ_MIN_MS
    ) -> None:
        self.chunks = chunks
        self.chunk_ms = chunk_ms
        self.acq_ms = acq_ms
        self.services: Any = None
        self.consumed_windows: set[str] = set()
        self.acq_entered = threading.Event()
        self.captures: list[str] = []

    async def open(self, descriptor: dict[str, Any], services: Any, context: Any) -> None:
        self.services = services

    async def close(self, context: Any) -> None:
        pass

    async def _pace(self, total_ms: float) -> None:
        """Pace ``total_ms`` in adapter-internal slices, no artifact traffic.

        Deadline-driven (sleep-at-most-10ms increments against the target
        instant) rather than a fixed slice count: ``asyncio.sleep`` only
        ever OVERSHOOTS, so fixed slices accumulate overshoot under host
        load — a deadline-driven pacer converges to the target within one
        sleep granularity and the natural duration stays ~T_acq_min."""
        deadline = self.services.monotonic() + total_ms / 1000.0
        while True:
            remaining = deadline - self.services.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 0.01))

    def _temp_reading(self) -> dict[str, Any]:
        return {
            "parameter": "temp",
            "value": 23.5,
            "unit": "Cel",
            "observed_at": self.services.utc_now(),
            "age_ms": 0,
            "quality": "valid",
            "source": "device",
        }

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        verb = request["verb"]
        arguments = request["arguments"]
        operation_id = request["operation_id"]
        if verb == "read":
            parameter = arguments["parameter"]
            if parameter == "temp":
                return {
                    "operation_id": operation_id,
                    "verb": verb,
                    "status": "ok",
                    "data": self._temp_reading(),
                }
            if parameter == "acq_scalar":
                self.acq_entered.set()
                await self._pace(self.acq_ms)
                return {
                    "operation_id": operation_id,
                    "verb": verb,
                    "status": "ok",
                    "data": {
                        "parameter": parameter,
                        "value": 4.0,
                        "unit": "V",
                        "observed_at": self.services.utc_now(),
                        "age_ms": 0,
                        "quality": "valid",
                        "source": "device",
                    },
                }
            raise ValueError(f"unknown parameter {parameter!r}")
        if verb == "write":
            # The write leg: the same paced acquisition class (§2.2).
            self.acq_entered.set()
            await self._pace(self.acq_ms)
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {
                    "parameter": arguments["parameter"],
                    "requested_value": arguments["value"],
                    "effective_value": arguments["value"],
                    "assurance": "dispatched",
                },
            }
        if verb != "capture":
            raise ValueError(f"unsupported verb {verb!r}")
        capture_id = arguments["capture_id"]
        window = capture_id.rsplit(".h", 1)[0] if ".h" in capture_id else capture_id
        if window in self.consumed_windows:
            # §2.5 control (ii): one acquisition per window; a second half
            # cannot cover it. A clean typed device rejection — NOT a
            # session poison (dispatch_state not_dispatched, nothing sent).
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "error",
                "error": {
                    "code": "UNSUPPORTED",
                    "message": (
                        f"acquisition window {window!r} already consumed: one "
                        "acquisition per window, two half-manifests cannot cover it"
                    ),
                    "dispatch_state": "not_dispatched",
                },
            }
        self.consumed_windows.add(window)
        self.captures.append(capture_id)
        for _ in range(self.chunks):
            if context.is_cancelled():
                break
            await self.services.artifact_append(
                capture_id, b"\x01" * 8, context
            )
            await asyncio.sleep(self.chunk_ms / 1000.0)
        manifest = await self.services.artifact_finalise(
            capture_id,
            {
                "format": "waveform_f64le",
                "started_at": self.services.utc_now(),
                "sample_interval_s": 0.001,
                "unit": "V",
            },
            context,
        )
        return {
            "operation_id": operation_id,
            "verb": verb,
            "status": "ok",
            "data": manifest,
        }


class BRigAdapter:
    """Device B (dev-rig-b): the non-capturing instance.

    The §2.3 device classes, differing in BEHAVIOUR, never in the axis
    quantity (both report the ``read_signal_values`` envelope):

    * **buffered** (§8-conformant host-driven feed): telemetry frames
      exist only when polled — the device-side emission SCHEDULE is a pure
      function of the harness monotonic clock (one frame per
      ``FRAME_PERIOD_MS`` since subscribe; no threads, no background
      sampler — §8's own rule). Each event carries its device emission
      stamp in the schema-legal ``x-rig-emit-ns`` extension key. The
      parameter read serves the newest RECEIVED frame with its true device
      stamp (``observed_at`` = the frame's wall stamp, ``age_ms`` =
      elapsed since it). During A's dispatch the polls stop, so the newest
      received frame ages by the blackout — X2 is dispatch-scale on this
      class. A write to ``level`` updates the newest data point (a
      commanded value is the latest known value — the verify loop reads
      the parameter, and frames only arrive when polled).
    * **unbuffered**: ``read`` performs an immediate conversion
      (``observed_at = now``, ``age_ms = 0``) — X2 collapses to host-side
      skew (~0).

    The X4 hazard model: the level crosses the numeric condition bound at
    a scripted monotonic instant ``trip_cross_ns`` (time-derived onset —
    the harness knows it exactly) and stays crossed until the protective
    write lands (``write_landed_ns``), which resets the parameter to the
    commanded value.
    """

    def __init__(self, *, buffered: bool) -> None:
        self.buffered = buffered
        self.services: Any = None
        self.subscribe_mono_ns: int | None = None
        self.delivered = 0
        self.trip_cross_ns: int | None = None
        self.write_landed_ns: int | None = None
        self._override_ns: int | None = None
        self._override_value: float | None = None
        self._ref_mono_ns = 0
        self._ref_epoch = 0.0

    async def open(self, descriptor: dict[str, Any], services: Any, context: Any) -> None:
        self.services = services
        # The wall<->monotonic pair the frame stamps derive from (one clock
        # family: the bundle's injected clock and wall). Captured WALL
        # FIRST and biased 1 ms into the past: a derived stamp that lands
        # even microseconds in the FUTURE reads as impossible timing
        # (``read_signal_values`` marks the signal invalid), and the
        # unbuffered class stamps "now" — the capture gap between the two
        # reference reads must never outweigh the read path's conversion
        # overhead. Wall-first plus the bias makes every derived stamp
        # strictly in the past, so ages are non-negative by construction.
        stamp = datetime.fromisoformat(services.utc_now().replace("Z", "+00:00"))
        self._ref_epoch = stamp.timestamp() - 0.001
        self._ref_mono_ns = self._mono_ns()

    async def close(self, context: Any) -> None:
        pass

    def _mono_ns(self) -> int:
        return int(self.services.monotonic() * 1_000_000_000)

    def _wall_at(self, mono_ns: int) -> str:
        epoch = self._ref_epoch + (mono_ns - self._ref_mono_ns) / 1e9
        return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z")

    def _value_at(self, mono_ns: int) -> float:
        if self._override_ns is not None and mono_ns >= self._override_ns:
            assert self._override_value is not None
            return self._override_value
        if self.trip_cross_ns is not None and mono_ns >= self.trip_cross_ns:
            return _TRIP_LEVEL
        return _SAFE_LEVEL

    def due_count(self) -> int:
        """Frames whose schedule time has passed but are undelivered."""
        if self.subscribe_mono_ns is None:
            return 0
        now = self._mono_ns()
        due = int((now - self.subscribe_mono_ns) / (FRAME_PERIOD_MS * 1_000_000))
        return max(0, due - self.delivered)

    def _reading(self, value: float, mono_ns: int, age_ms: int) -> dict[str, Any]:
        return {
            "parameter": "level",
            "value": value,
            "unit": "V",
            "observed_at": self._wall_at(mono_ns),
            "age_ms": age_ms,
            "quality": "valid",
            "source": "device",
        }

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        verb = request["verb"]
        arguments = request["arguments"]
        operation_id = request["operation_id"]
        if verb == "read":
            now = self._mono_ns()
            if self.buffered:
                # Newest RECEIVED frame (the subscribe point before the
                # first poll, the open reference before any subscription):
                # the frame's own stamps, never the read's.
                if self.delivered == 0:
                    point = (
                        self.subscribe_mono_ns
                        if self.subscribe_mono_ns is not None
                        else self._ref_mono_ns
                    )
                else:
                    assert self.subscribe_mono_ns is not None
                    point = self.subscribe_mono_ns + self.delivered * int(
                        FRAME_PERIOD_MS * 1e6
                    )
                if self._override_ns is not None and self._override_ns > point:
                    point = self._override_ns
                age_ms = int((now - point) / 1_000_000)
                return {
                    "operation_id": operation_id,
                    "verb": verb,
                    "status": "ok",
                    "data": self._reading(self._value_at(point), point, age_ms),
                }
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": self._reading(self._value_at(now), now, 0),
            }
        if verb == "write":
            self._override_ns = self._mono_ns()
            self._override_value = float(arguments["value"])
            self.write_landed_ns = self._mono_ns()
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {
                    "parameter": arguments["parameter"],
                    "requested_value": arguments["value"],
                    "effective_value": arguments["value"],
                    "assurance": "dispatched",
                },
            }
        if verb == "stream_subscribe":
            self.subscribe_mono_ns = self._mono_ns()
            self.delivered = 0
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {"subscription_id": arguments["subscription_id"]},
            }
        if verb == "stream_unsubscribe":
            return {
                "operation_id": operation_id,
                "verb": verb,
                "status": "ok",
                "data": {"subscription_id": arguments["subscription_id"]},
            }
        raise ValueError(f"unsupported verb {verb!r}")

    async def next_event(self, subscription_id: str, context: Any) -> dict[str, Any] | None:
        if self.subscribe_mono_ns is None or self.due_count() <= 0:
            return None  # a healthy quiet stream (spec §8)
        self.delivered += 1
        emit_ns = self.subscribe_mono_ns + self.delivered * int(FRAME_PERIOD_MS * 1e6)
        event = {
            "subscription_id": subscription_id,
            "sequence": self.delivered - 1,
            "kind": "telemetry",
            "reading": self._reading(self._value_at(emit_ns), emit_ns, 0),
        }
        # The X3 seam: the device emission stamp, carried in-event on the
        # harness monotonic clock (schema-legal x-extension; the bridge's
        # own ``x-[a-z0-9]+-[a-z0-9_-]+`` pattern).
        event["x-rig-emit-ns"] = emit_ns
        return event


def _probe_wall_injection(monitor_wall_rate: float, no_trip: bool) -> bool:
    """One predicate for the probe-wall exemption (review fold, reviewer
    finding 4): host-computed ages carry no starvation signal whenever the
    fixture itself injects the wall — a stretched monitor wall (rate != 1.0
    inflates every age by its own factor) OR the probe's no-condition policy
    variant. The priming classification arms and the pre-flight staleness
    check share it; the only classify state is a real wall at a live policy
    (1.0, False), which today's probes never mix — the shared predicate
    exists so a future partial probe cannot fall between the two signals."""
    return monitor_wall_rate != 1.0 or no_trip


class ContinuityRig:
    """The two-instance harness (design §2.1): direct construction of the
    production objects — ONE store, A capturing (adopted, no stream), B
    streaming (registered, serves the bench signal, safe-action target),
    the monitor over the WRAPPED plugin dict (the load-bearing difference
    from the old single-instance harness), and a ``RunStreamHost`` armed
    exactly as production (subscriptions derived from the bench signals
    with declared ``poll_ms``)."""

    def __init__(
        self,
        db_path: Path,
        *,
        device_class: str = "buffered",
        monitor_wall_rate: float = 1.0,
        no_trip: bool = False,
        policy: dict[str, Any] | None = None,
    ) -> None:
        self.clock = SystemClock()
        self.wall = SystemClock()  # the device/bundle wall (always 1x)
        self.monitor_wall = StretchedWall(monitor_wall_rate)
        self.policy = policy if policy is not None else POLICY
        self.store = Store.open(db_path, check_same_thread=False)
        content = ContentStore(self.store)
        quota = QuotaLimits(
            max_dataset_bytes=8192, max_evidence_entries=1000, max_event_batch=10
        )
        self.writer = CaptureStagingStore(
            self.store, max_capture_bytes=8192, max_dataset_bytes=8192
        )

        def publish(raw: dict[str, Any]) -> str:
            blob = json.dumps(raw, sort_keys=True).encode()
            digest = hashlib.sha256(blob).hexdigest()
            content.put_document(blob, digest, raw, "otdp-descriptor", _now_iso())
            return digest

        digest_a = publish(
            {
                "id": "dev.local.rig-a",
                "descriptor_version": "1.0.0",
                "integration": {"adapter": {"permissions": ["artifact_writer"]}},
            }
        )
        digest_b = publish(
            {
                "id": "dev.local.rig-b",
                "descriptor_version": "1.0.0",
                "integration": {"adapter": {"permissions": ["event_sink"]}},
            }
        )

        bundle_a, controller_a = build_capture_services(
            descriptor_digest=digest_a,
            content=content,
            writer=self.writer,
            clock=time.monotonic,
            wall=self.wall.now_iso,
            quota=quota,
            context_key="rig-a-session",
        )
        assert controller_a is not None
        self.adapter_a = ARigAdapter()
        self.bridge_a = OTDPBridge(
            self.adapter_a,
            descriptor={
                "capture_formats": ["waveform_f64le", "raw_binary"],
                "capture_limits": {"max_samples": 1024, "max_bytes": 8192},
            },
            services=bundle_a,
            simulation=SimulationInfo(True, "Synthetic"),
            capture=controller_a,
        )
        self.bridge_a.plugin_open(object())

        bundle_b, _none = build_capture_services(
            descriptor_digest=digest_b,
            content=content,
            writer=self.writer,
            clock=time.monotonic,
            wall=self.wall.now_iso,
            quota=quota,
            context_key="rig-b-session",
        )
        controller_b = build_stream_services(
            descriptor_digest=digest_b,
            store=self.store,
            wall=self.wall.now_iso,
            quota=quota,
            context_key="rig-b-session",
        )
        assert controller_b is not None
        self.adapter_b = BRigAdapter(buffered=device_class == "buffered")
        self.bridge_b = OTDPBridge(
            self.adapter_b,
            descriptor={"stream_limits": {"min_interval_ms": 10, "max_subscriptions": 4}},
            services=bundle_b,
            simulation=SimulationInfo(True, "Synthetic"),
            stream=controller_b,
        )
        self.bridge_b.plugin_open(object())

        self.lease = self.store.next_lease(
            BENCH_ID, "lease-rig", holder="run-rig", expires_at="2030-01-01T00:00:00Z"
        )
        wrapped: dict[str, DevicePlugin] = {}
        self.monitor = _RunMonitor(
            self.store,
            BENCH_ID,
            self.policy,
            BENCH,
            wrapped,  # filled below: the monitor reads through the wrapper
            self.clock,
            self.monitor_wall,
            run_id="run-rig",
            lease_sequence=self.lease.sequence,
        )
        wrapped[DEVICE_A] = _MonitoringPlugin(self.bridge_a, self.monitor)
        wrapped[DEVICE_B] = _MonitoringPlugin(self.bridge_b, self.monitor)
        self.wrapped = wrapped

        self.stream_host = RunStreamHost(run_id="run-rig", clock=self.clock)
        self.stream_host.register(DEVICE_B, self.bridge_b, controller_b)
        self.stream_host.adopt(DEVICE_A, self.bridge_a)  # close authority, no stream
        self.monitor_clock = _MonitoringClock(
            self.clock, self.monitor, bench_poll_ns(BENCH), streams=self.stream_host
        )

        # The measurement seams.
        self.tick_times: list[int] = []
        self.tick_tripped: list[bool] = []
        self._original_tick = self.monitor.tick
        self.monitor.tick = self._recording_tick  # type: ignore[method-assign]
        self.snapshots: list[tuple[int, dict[str, SignalValue]]] = []
        self.monitor.retain = self._retain
        self.events: list[tuple[int, dict[str, Any], str]] = []
        self.stream_host.on_event = self._on_event

        self.monitor.phase = "body"
        # C14 priming, extended: a read through A proves ticks flow and BOTH
        # signals serve — the fixture fails loudly if the wrapper is dropped
        # to "simplify".
        primed = self.wrapped[DEVICE_A].dispatch(
            OperationRequest.read("prime-a", parameter="temp"),
            deadline_ns=self.deadline_ns(2000),
        )
        # Construction-time starvation, read-#1 presentation (review fold,
        # HIGH+MEDIUM converged): when the stall predates the wrapper's
        # pre-dispatch tick, that tick itself reads the aged signal, the
        # fail-safe latches signal_invalid, and the monitor REFUSES the
        # priming dispatch at the door — primed.status lands ERROR with a
        # NOT_DISPATCHED freshness-block envelope. The discriminant is the
        # same one the measured dispatch uses (_freshness_trip_block: the
        # monitor's own blocked latch plus the freshness kind), and the
        # class is the same host starvation, so it retries rather than
        # dying on the degenerate-wiring assert below.
        #
        # Both priming classification arms guard on the SHARED probe-wall
        # predicate (review folds, critic F2 + reviewer finding 4): a
        # stretched monitor wall inflates every host-computed age by its
        # own factor, and the no-condition probe variant ages by policy —
        # either way an over-aged priming read is the probe's OWN
        # injection. Classifying it would both retry structurally uselessly
        # (every construction re-injects the wall) and attribute a probe
        # artifact to host starvation, misdirecting slice 2.
        if (
            primed.status is not OperationStatus.OK
            and not _probe_wall_injection(monitor_wall_rate, no_trip)
            and _freshness_trip_block(self, primed)
        ):
            raise TrialInfrastructureError(
                "a bench signal failed to serve at priming (read-#1 "
                "starvation: the pre-dispatch tick read an aged signal "
                "and the fail-safe refused the priming read)",
                site="priming-block-refusal",
            )
        assert primed.status is OperationStatus.OK, "monitoring fixture degenerate"
        assert len(self.tick_times) >= 2, "the wrapper never ticked"
        assert self.snapshots, "the retain seam never fired"
        # Construction-time starvation (issue #241 slice 1, the observed CI
        # failure): construction itself is an un-polled window (drain_until_
        # quiet's docstring names it), so sig-rig-b's first read can arrive
        # aged past max_age_ms on a loaded host — an infrastructure fact,
        # never a property of the measured system, so the marker says retry
        # on a fresh rig. The sibling wiring asserts above stay plain:
        # degenerate wiring has no CI evidence of load-triggering, and
        # retrying it would mask a dropped wrapper behind two wasted rigs.
        # The shared probe-wall predicate guards here too, same as the
        # block-refusal arm above.
        if not _probe_wall_injection(monitor_wall_rate, no_trip) and not all(
            value.valid for value in self.snapshots[-1][1].values()
        ):
            raise TrialInfrastructureError(
                "a bench signal failed to serve at priming "
                "(construction-time starvation; run 36309281160)",
                site="priming-validity",
            )
        # Armed exactly as production: B's subscription derives from the
        # bench signal's declared poll_ms (sig-rig-b -> min_interval_ms 50).
        self.stream_host.arm(BENCH, self.wrapped, self.monitor)
        assert self.stream_host.subscriptions.get(DEVICE_B), "B never subscribed"

    # -- seams ---------------------------------------------------------------------

    def _recording_tick(self) -> None:
        self.tick_times.append(self.clock.now_ns())
        self._original_tick()
        self.tick_tripped.append(bool(self.monitor.violations))

    def _retain(self, snapshot: dict[str, SignalValue]) -> str:
        self.snapshots.append((self.clock.now_ns(), dict(snapshot)))
        return "rig-snapshot"

    def _on_event(self, subscription_id: str, event: dict[str, Any], receipt: str) -> None:
        self.events.append((self.clock.now_ns(), dict(event), receipt))

    def deadline_ns(self, milliseconds: float) -> int:
        """A deadline on the SAME timebase as the bundle clock (the bridge
        compares services.monotonic() seconds against deadline_ns/1e9)."""
        return int((time.monotonic() + milliseconds / 1000.0) * 1_000_000_000)

    def capture_request(self, capture_id: str = "cap.rig") -> OperationRequest:
        return OperationRequest(
            "op-capture",
            OperationVerb.CAPTURE,
            {
                "capture_id": capture_id,
                "format": "waveform_f64le",
                "sample_count": 100,
                "max_bytes": 1024,
            },
        )

    # -- the trial rhythm -------------------------------------------------------------

    def settle(self, milliseconds: float) -> None:
        """An idle window through the REAL monitoring clock (the delay-step
        rhythm: poll rounds and ticks run inside the slices)."""
        self.monitor_clock.wait_ns(int(milliseconds * 1_000_000))

    def drain_until_quiet(self, *, cap_ms: float = 2000.0) -> None:
        """Deliver every due frame so the newest-received point sits within
        one frame period of now (the X2-control precondition: the receive
        lag must be fixture-bounded, never backlog-shaped — with a 20 ms
        period against 50 ms slice polls the backlog would otherwise grow
        without bound), and keep draining for two frame periods past the
        last delivery — a frame about to fire must not be missed by an
        instantaneous due==0 reading (the control's 20 ms window can hold
        exactly one straddling frame). Pre-trip this drives the ENGINE's
        poll rounds (the production path, monitor ticks between polls);
        post-trip the engine is stopped by design (``stop =
        monitor.cause is not None``; "Stops early on a terminal monitor
        cause"), so the drain polls the bridge directly and hands each
        validated event to the host's contained ``on_event`` dispatcher —
        the identical landing call the engine makes.

        The pre-trip ``poll_slice`` deadline is ONE POLL CADENCE (50 ms),
        never a few ms: the engines open each round with a monitor tick
        BEFORE the deadline check, and a tick reads both signals through
        their bridges (several ms; more under load) — a 5 ms deadline is
        already expired by the time the poll is about to run, the round
        returns without polling, no frame is ever delivered, the buffered
        read never crosses the hazard and the monitor never trips while
        the loop spins hot to the cap (the observed CI failure: "the
        condition never tripped post-dispatch" / "no in-window frames for
        X3"). The 1 ms yield in the spinning branch keeps the loop off the
        CPU between rounds. A cap-exit is LOUD: truncating the latency set
        or the receive point would silently bias X2/X3, so a cap-exit
        raises the ``drain-cap`` infrastructure site (issue #241 slice 2;
        an ``AssertionError`` subclass — an exhausted retry still fails
        the trial as an assertion), never a silent return."""
        end = time.monotonic() + cap_ms / 1000.0
        quiet_floor = time.monotonic() + 2 * FRAME_PERIOD_MS / 1000.0 + 0.005
        subscriptions = self.stream_host.subscriptions.get(DEVICE_B, [])
        quiet = False
        while time.monotonic() < end:
            if self.adapter_b.due_count() <= 0:
                if time.monotonic() >= quiet_floor:
                    quiet = True
                    break
                time.sleep(0.001)
                continue
            if self.monitor.cause is None:
                self.stream_host.poll_slice(deadline_ns=self.deadline_ns(POLL_MS))
                time.sleep(0.001)
                continue
            for subscription_id in subscriptions:
                outcome = self.bridge_b.poll_event(
                    subscription_id, deadline_ns=self.deadline_ns(50)
                )
                if _poll_found_dead_session(outcome):
                    raise TrialInfrastructureError(
                        f"rig-b session already dead at the poll door: {outcome.refusal}",
                        site="drain-poll-door",
                    )
                if (
                    outcome.session_failed
                    and outcome.refusal is not None
                    and outcome.refusal.code is ErrorCode.TIMEOUT
                    and outcome.refusal.dispatch_state is DispatchState.UNKNOWN
                ):
                    # Slice 4 (design §1.3): the TIMEOUT-flavor poison — a
                    # poll whose event delivery outran the poll's own 50 ms
                    # deadline under host stall — is starvation-shaped, so
                    # the F4 charter retries it on a fresh rig. Every
                    # deterministic (protocol-lie) flavor stays
                    # non-retryable exactly as now: the door reject above
                    # keeps its site, and any other session-failed refusal
                    # still reds on the plain assert below. The UNKNOWN
                    # dispatch_state is required so a CLEAN poll-deadline
                    # TIMEOUT refusal (session alive, the bridge's own
                    # early return) can never misclassify as poison.
                    raise TrialInfrastructureError(
                        f"rig-b drain poll poisoned its session (TIMEOUT "
                        f"flavor: delivery outran the poll's 50 ms "
                        f"deadline): {outcome.refusal}",
                        site="drain-poll-timeout",
                    )
                assert not outcome.session_failed, outcome.refusal
                if outcome.event is not None:
                    self.stream_host._contained_on_event(
                        subscription_id,
                        outcome.event,
                        outcome.host_received_at or "",
                    )
        if not quiet:
            # The delivery-drain cap (issue #241 slice 2): frames still due
            # at the cap is the delivery path starved by the HOST — the F4
            # class, the sweep's 39-frames-due gates failure — not a
            # property of the measured system, so the marker says retry on
            # a fresh rig. An ``AssertionError`` subclass: an exhausted
            # retry still fails the trial as an assertion.
            raise TrialInfrastructureError(
                f"drain_until_quiet hit its {cap_ms:.0f} ms cap with "
                f"{self.adapter_b.due_count()} frame(s) still due — the delivery "
                "path starved; a truncated latency set or receive point would "
                "silently bias X2/X3",
                site="drain-cap",
            )

    def align_to_frame(self, *, lead_ms: float = 4.0) -> None:
        """Busy-align the next dispatch start to just before a frame
        boundary — the schedule is a pure function of the harness clock
        (pure derivation, no threads), so the control's 20 ms window is
        guaranteed at least one in-window frame for X3."""
        period_ns = int(FRAME_PERIOD_MS * 1_000_000)
        assert self.adapter_b.subscribe_mono_ns is not None
        while True:
            now = int(time.monotonic() * 1_000_000_000)
            phase = (now - self.adapter_b.subscribe_mono_ns) % period_ns
            remaining = period_ns - phase
            if remaining <= lead_ms * 1_000_000:
                return
            time.sleep(min(remaining - lead_ms * 1_000_000, 500_000) / 1e9)

    def teardown_and_close(self) -> None:
        self.stream_host.teardown(self.wrapped)
        self.stream_host.close()
        self.store.close()


def _max_tick_gap_ms(tick_times: list[int]) -> float:
    assert len(tick_times) >= 2, "not enough ticks to measure a gap"
    return max(b - a for a, b in zip(tick_times, tick_times[1:], strict=False)) / 1_000_000


class TrialInfrastructureError(AssertionError):
    """The retryable failure class (review finding F4 on PR #236): host
    starvation of the fixture, never a property of the measured system.

    A site that has classified its own failure as infrastructure raises
    this marker; ``run_trial``'s matcher inspects the TYPE and never
    message text, so a plain ``AssertionError`` quoting a historical
    retryable wording raises straight through (pinned by test).
    Subclassing ``AssertionError`` keeps an exhausted retry a normal
    assertion failure for pytest.

    Every raise carries a ``site`` label (review fold, critic F3): the
    retry budget's evidence base. A bare retry count discards the
    intermediate sites — exhaustion would report only the last attempt's
    site — so ``run_trial`` records each failed attempt's label in
    ``outcome["retry_sites"]`` and the exhausted exception carries its own
    (the last) site — and, since the wave-1 fold (critic F1), renders the
    full recorded sequence into the re-raised message at exhaustion. The
    keyword is REQUIRED: a defaulted label would let
    a future site raise unlabelled and silently re-open the hole.
    """

    def __init__(self, message: str, *, site: str) -> None:
        super().__init__(message)
        self.site = site


def _dead_session_reject(bridge: OTDPBridge, result: OperationResult) -> bool:
    """The structural signal behind a dispatch's ``INTERNAL_ERROR`` "A
    fresh opened bridge is required" door reject: the bridge's own failure
    latch plus NOT_DISPATCHED — retryable infrastructure means the dispatch
    NEVER ran, so an error envelope claiming the work was dispatched stays
    plain whatever its code (an adapter envelope can claim dispatch; the
    door reject never does). The door itself is the three-disjunct
    ``not _opened or _closed or _failed`` (otdp_bridge.py); checking only
    ``_failed`` is a mid-trial narrowing, sound because a rig bridge is
    open from ``plugin_open`` and closes only at teardown/finally — after
    every site that classifies. The capture gate's own ``INTERNAL_ERROR``
    store refusals fire with the latch down and stay non-retryable."""
    error = result.error
    return (
        error is not None
        and error.code is ErrorCode.INTERNAL_ERROR
        and error.dispatch_state is DispatchState.NOT_DISPATCHED
        and bridge._failed
    )


def _freshness_trip_block(rig: ContinuityRig, result: OperationResult) -> bool:
    """A dispatch the protective fail-safe refused at the door — the
    settle/pre-tick starvation class. Block-ness is read from the
    monitor's OWN §5 latch (``blocked``, set by ``block_result`` when it
    actually refused a dispatch) plus the block result's NOT_DISPATCHED
    state, NEVER inferred from a latched cause: after the post-dispatch
    tick — or past the protective transition, where phase idle makes a
    block impossible — a freshness cause can be latched while the failing
    dispatch was device-side (F1's two lanes), and a device-side
    ``DEVICE_REJECTED`` must never retry whatever cause is latched. The
    freshness KIND still gates: only ``signal_invalid`` (staleness) is the
    starvation class; a real (non-freshness) trip's block keeps the plain
    assert."""
    error = result.error
    if error is None or error.code is not ErrorCode.DEVICE_REJECTED:
        return False
    if error.dispatch_state is not DispatchState.NOT_DISPATCHED:
        return False
    if not rig.monitor.blocked:
        return False
    kinds = {
        reason.split(":", 2)[1].strip()
        for reason in rig.monitor.cause_reasons
        if reason.count(":") >= 1
    }
    return "signal_invalid" in kinds


def _dispatch_failure_is_infrastructure(
    rig: ContinuityRig, result: OperationResult
) -> bool:
    """Classify an unexpected dispatch status by structure (F4): the
    dead-session door reject and the freshness-trip block are host
    starvation; every other landing — a wrong status for its own sake, a
    real trip, a store refusal at the capture gate, a late-result poison —
    is a measurement failure and must fail the trial, not retry it."""
    return _dead_session_reject(rig.bridge_a, result) or _freshness_trip_block(
        rig, result
    )


def _poll_found_dead_session(outcome: PollOutcome) -> bool:
    """A drain poll that found the session already dead (the door reject —
    ``INTERNAL_ERROR`` with ``session_failed``). NOT classified: a session
    the poll itself poisoned via a protocol-lie refusal (a deterministic
    rig defect). The TIMEOUT flavor (a poll whose event delivery outran
    the poll's own 50 ms deadline under host stall) is classified beside
    this check (issue #241 slice 4, design §1.3): the F4 charter's own
    rule applied to a site its disclosure already admitted was
    starvation-shaped — it is the retryable ``drain-poll-timeout`` site
    in ``run_trial``'s carrying list. The remaining known non-retryable
    starvation residual, disclosed as an owner row: entry-timeout at the
    dispatch door. (Wave-1 fold, adversary F1: drain-cap starvation was
    listed here before #241 slice 2 classified it — it is now the
    retryable ``drain-cap`` site in ``run_trial``'s carrying list, not a
    residual.)"""
    refusal = outcome.refusal
    return (
        outcome.session_failed
        and refusal is not None
        and refusal.code is ErrorCode.INTERNAL_ERROR
    )


#: Per-arm dispatch references. The X1 band reference is the arm's own
#: in-flight duration (design §5.3 with §2.2/§8(d)): the capture arm CUTS
#: at its budget (in-flight ~50 ms), the non-capture arm COMPLETES at
#: T_acq_min (in-flight ~200 ms). Both black out ticks for that duration —
#: the exposure class being measured.
_ARM_DISPATCH_MS = {"capture": CAPTURE_BUDGET_MS, "non_capture": T_ACQ_MIN_MS}


def _construct_rig(db_path: Path, **kwargs: Any) -> ContinuityRig:
    """Construct a ``ContinuityRig`` whose FAILED construction still closes
    what it built (review fold, critic F4 + adversary F3):
    ``_run_trial_once`` builds the rig before its own try, so a raise
    inside ``__init__`` never reaches that try's finally belt — and the
    instance handle is lost mid-construction, where no except clause can
    see it. Allocating the instance first and calling ``__init__``
    explicitly keeps the handle, so the module's belt shape
    (``_close_partially_constructed``) can close the partial rig's stream
    host and store — the only OS-bearing objects; the adapters spawn no
    threads, adversary-verified on this fold. Best-effort and idempotent
    (sqlite closes are idempotent; the stream host's close sweeps every
    constructed bridge)."""
    rig = ContinuityRig.__new__(ContinuityRig)
    try:
        ContinuityRig.__init__(rig, db_path, **kwargs)
    except BaseException:
        _close_partially_constructed([rig])
        raise
    return rig


def run_trial(
    tmp_path: Path,
    *,
    arm: str,
    device_class: str,
    trial_index: int,
    monitor_wall_rate: float = 1.0,
    no_trip: bool = False,
) -> dict[str, Any]:
    """One fresh-rig trial on a fresh store (design §2.4): the measured
    dispatch, all four axes with their seams, the protective transition,
    and the wall-domain fields recorded alongside X3 (check 5's object).

    ``no_trip`` is the divergent-wall probe's variant (check 5): a 10x
    monitor wall inflates every host-computed age, so the freshness
    condition would trip at the first settle tick for reasons that have
    nothing to do with the hazard — the probe runs the same dispatch
    rhythm under a no-condition policy and measures X1/X2 only.

    Retry disclosure: a trial whose measured dispatch never ran because
    the host starved the fixture BEFORE it (a settle stretched past the
    dispatch-scale bound, or a >50 ms read path tripping the bridge's
    late-result poison on a fast read) is an infrastructure failure, not a
    measurement — ``run_trial`` retries it on a FRESH rig under a fixed
    three-attempt budget (the initial attempt plus two retries, so an
    exhausted trial has built exactly three rigs, pinned ``len(rigs) == 3``),
    and records the retry count in the outcome, alongside the ordered
    ``retry_sites`` label of every failed attempt (review fold, critic F3:
    a bare count discards the composition — a priming-then-pre-flight
    retry is not the same lane health signal as a single-site retry; and
    wave-1 fold, critic F1: at exhaustion the re-raised error RENDERS the
    full site sequence into its message, so a lane log shows every failed
    site — the last attempt's site still travels as the error's own
    ``site``). The
    retryable class is
    carried STRUCTURALLY (review finding F4): every site that has
    classified its own failure as host starvation raises
    ``TrialInfrastructureError`` — an ``AssertionError`` subclass, so an
    exhausted retry still fails the trial as an assertion — and the
    matcher below inspects that TYPE, never message text. The carrying
    sites: the construction-time priming block-refusal — read-#1
    starvation, where the wrapper's pre-dispatch tick reads the aged
    signal and the fail-safe refuses the priming dispatch at the door
    (review fold: the heaviest presentation of the exact slice-1
    condition) — the construction-time priming signal-validity check
    (issue #241 slice 1, the observed CI failure), the pre-flight
    staleness check (pre-dispatch by intent), a
    dispatch whose refusal is the dead-session door reject (the bridge's
    failure latch plus NOT_DISPATCHED, not its wording) or the monitor's
    own ``blocked``-latched freshness (``signal_invalid``) door-refusal —
    block-ness read from the monitor's latch, never inferred from a
    latched cause — a post-trip drain poll that found the session
    already dead at the door, a drain poll that poisoned its session
    with the TIMEOUT-flavor refusal (delivery outran the poll's own
    50 ms deadline under host stall; issue #241 slice 4), and the
    delivery-drain cap — frames still due at the 2000 ms cap, the
    sweep's 39-frames-due gates failure (issue #241 slice 2).
    Everything else — a wrong status for any
    other reason, a real (non-freshness) trip, a device-side rejection
    whatever cause is latched (F1's two lanes), an error envelope claiming
    the work was dispatched, a session the poll itself poisoned — keeps
    its plain ``AssertionError`` and raises straight through, as does any
    ``AssertionError`` that merely quotes the historical retryable wording
    (pinned by test). Starvation-shaped NON-retryables that remain — the
    drain-cap starvation this row once pointed at is now the classified
    ``drain-cap`` carrying site above (wave-1 fold, adversary F1), and
    the poll's TIMEOUT-flavor poison is now the classified
    ``drain-poll-timeout`` site (slice 4) — reduce to entry-timeout at
    the dispatch door, disclosed as an owner row."""
    retry_sites: list[str] = []
    for attempt in range(3):
        try:
            outcome = _run_trial_once(
                tmp_path,
                arm=arm,
                device_class=device_class,
                trial_index=trial_index * 10 + attempt,
                monitor_wall_rate=monitor_wall_rate,
                no_trip=no_trip,
            )
            outcome["retries"] = attempt
            outcome["retry_sites"] = retry_sites
            return outcome
        except TrialInfrastructureError as error:
            retry_sites.append(error.site)
            if attempt == 2:
                # Wave-1 fold, critic F1: exhaustion must not drop the
                # composition — the re-raise renders every failed site
                # into the message (pytest shows str(error)), so a lane
                # log at exhaustion carries the full sequence, not only
                # the last attempt's site. Type, traceback, and the
                # error's own (last) site are untouched.
                error.args = (
                    f"{error.args[0]} [retry composition exhausted after "
                    f"{len(retry_sites)} attempts: "
                    f"{' -> '.join(retry_sites)}]",
                )
                raise
    raise AssertionError("unreachable retry exhaustion")



def _run_trial_once(
    tmp_path: Path,
    *,
    arm: str,
    device_class: str,
    trial_index: int,
    monitor_wall_rate: float,
    no_trip: bool,
) -> dict[str, Any]:
    rig = _construct_rig(
        tmp_path / f"rig-{arm}-{device_class}-{trial_index}.db",
        device_class=device_class,
        monitor_wall_rate=monitor_wall_rate,
        no_trip=no_trip,
        policy=NO_TRIP_POLICY if no_trip else POLICY,
    )
    try:
        # The trial rhythm: no long un-drained idle window is allowed — the
        # buffered receive point ages by (window - delivered frames), and a
        # dispatch-scale max_age bound must see the DISPATCH's blackout,
        # never a backlog artifact. So: a quiet-drain FIRST (construction
        # time — imports, the store migration, the priming dispatch — is
        # itself an un-polled window whose backlog would otherwise age the
        # first settle tick past the bound on a loaded host), then settle
        # (polls + ticks), quiet-drain again, align, and only then the
        # measured dispatch.
        rig.drain_until_quiet()
        rig.settle(100)
        rig.drain_until_quiet()
        rig.align_to_frame()
        # Loud pre-flight (skipped whenever the fixture itself injects the
        # wall — the shared probe-wall predicate, reviewer finding 4): if
        # the fixture ever enters the measured dispatch with the monitored
        # signal already stale, the block that follows would misreport the
        # cause — fail HERE with the actual age.
        if not _probe_wall_injection(monitor_wall_rate, no_trip):
            last_sig_b = rig.snapshots[-1][1][SIG_B]
            if not last_sig_b.valid:
                # Pre-dispatch by intent (F4): entering the measured window
                # with an already-stale signal is fixture starvation, never
                # a property of the measurement — the marker says retry.
                raise TrialInfrastructureError(
                    f"pre-dispatch staleness: {SIG_B} age {last_sig_b.age_ms} ms",
                    site="pre-flight-staleness",
                )
        write_gap: float | None = None

        tick_mark = len(rig.tick_times)
        snap_mark = len(rig.snapshots)
        event_mark = len(rig.events)
        # X4's hazard onset: scripted INSIDE the dispatch window (the
        # harness knows T_cross exactly). The wrapper's structure is
        # tick -> dispatch -> tick, so exactly one tick (and one retained
        # snapshot) lands between the dispatch call and its return: the
        # FIRST post-dispatch snapshot is rig.snapshots[snap_mark + 1].
        dispatch_start_ns = rig.clock.now_ns()
        if no_trip:
            t_cross_ns = None
        else:
            t_cross_offset_ms = {"capture": 20.0, "non_capture": 40.0, "control": 10.0}[
                "control" if arm == "control" else arm
            ]
            rig.adapter_b.trip_cross_ns = dispatch_start_ns + int(t_cross_offset_ms * 1e6)
            t_cross_ns = rig.adapter_b.trip_cross_ns

        budget = SHORT_T_MS if arm == "control" else (
            CAPTURE_BUDGET_MS if arm == "capture" else T_ACQ_MIN_MS + 500
        )
        if arm == "capture":
            result = rig.wrapped[DEVICE_A].dispatch(
                rig.capture_request(), deadline_ns=rig.deadline_ns(budget)
            )
            expected = OperationStatus.UNKNOWN  # the deadline-max cut
        elif arm == "control":
            result = rig.wrapped[DEVICE_A].dispatch(
                OperationRequest.read("op-acq-short", parameter="acq_scalar"),
                deadline_ns=rig.deadline_ns(budget),
            )
            expected = OperationStatus.UNKNOWN  # §2.5 control (i): fails
        else:
            result = rig.wrapped[DEVICE_A].dispatch(
                OperationRequest.read("op-acq", parameter="acq_scalar"),
                deadline_ns=rig.deadline_ns(budget),
            )
            expected = OperationStatus.OK  # the deadline ACCOMMODATES T_acq
        dispatch_end_ns = rig.clock.now_ns()
        if result.status is not expected:
            # F4/F1: classify by structure before failing — see
            # _dispatch_failure_is_infrastructure (block-ness is the
            # monitor's latch, never a latched cause).
            detail = (
                f"{arm} dispatch landed {result.status.value}, expected {expected.value}: "
                f"{result.error.message if result.error else ''}"
            )
            if _dispatch_failure_is_infrastructure(rig, result):
                raise TrialInfrastructureError(detail, site="dispatch-door")
            raise AssertionError(detail)
        duration_ms = (dispatch_end_ns - dispatch_start_ns) / 1e6

        # X1 — the tick-gap class (monotonic, the _recording_tick seam).
        x1 = _max_tick_gap_ms(rig.tick_times[tick_mark:])

        # X2 — sig-rig-b-level's envelope in the FIRST post-dispatch
        # retained snapshot (the retain seam; wall-derived age domain).
        # snapshots[snap_mark] is the wrapper's pre-tick, [snap_mark + 1]
        # its after-tick — the first one that spans the dispatch. The
        # bracket is STRUCTURAL (single-threaded: the wrapper runs tick ->
        # block -> inner dispatch -> tick, and nothing else can tick in
        # between), so the wiring check is that [snap_mark] was retained
        # INSIDE the wrapper — after the measured dispatch began — and
        # [snap_mark + 1] after it. The original 0.5x-duration span
        # arithmetic on the RETAIN stamps was retired: retain stamps land
        # after the tick's signal reads, and under host load a pre-tick's
        # reads can exceed half of the short control's 20 ms budget
        # (observed: an 18 ms pre-tick against a 20.9 ms control window
        # — the wrapper's bracket held, the arithmetic did not).
        assert len(rig.snapshots) > snap_mark + 1, "no post-dispatch snapshot retained"
        pre_snap_ts, _ = rig.snapshots[snap_mark]
        post_snap_ts, post_snapshot = rig.snapshots[snap_mark + 1]
        assert pre_snap_ts > dispatch_start_ns, (
            "the pre-dispatch snapshot was retained before the measured "
            "dispatch began — the wrapper's pre-tick did not retain"
        )
        assert post_snap_ts > pre_snap_ts, "snapshot ordering inverted"
        x2 = float(post_snapshot[SIG_B].age_ms)

        # Drain until quiet so every emitted frame eventually lands (X3's
        # latency set is complete). DEVIATION from the design's letter
        # ("drains via _MonitoringClock.wait_ns slices"): a tripped monitor
        # ENDS wait_ns slices immediately by design ("protective
        # intervention ends the wait") AND the engine's own stop latch
        # (``stop = monitor.cause is not None``) halts poll rounds — and
        # the unbuffered class trips at the first post-dispatch tick, so
        # wait_ns/engine polling can deliver nothing post-trip. The drain
        # helper therefore polls the bridge directly through the host's
        # contained on_event dispatcher once tripped (the identical landing
        # call the engine makes), with the cause already latched.
        rig.drain_until_quiet()

        # X3 — events emitted vs landed for in-window frames (the on_event
        # seam + the in-event x-rig-emit-ns stamp; one monotonic clock
        # domain by construction). The wall-domain observed_at /
        # host_received_at pair is recorded alongside (check 5's object).
        in_window: list[dict[str, Any]] = []
        for landing_ns, event, receipt in rig.events[event_mark:]:
            emit_ns = event.get("x-rig-emit-ns")
            if isinstance(emit_ns, int) and dispatch_start_ns < emit_ns < dispatch_end_ns:
                reading = event.get("reading") or {}
                in_window.append(
                    {
                        "emit_ns": emit_ns,
                        "landing_ns": landing_ns,
                        "latency_ms": (landing_ns - emit_ns) / 1e6,
                        "landed_during_window": landing_ns < dispatch_end_ns,
                        "observed_at": reading.get("observed_at"),
                        "host_received_at": receipt,
                    }
                )
        assert in_window, "no in-window frames for X3 (alignment failed)"
        assert all(not frame["landed_during_window"] for frame in in_window), (
            "a frame landed DURING the dispatch — the blackout did not hold"
        )
        x3 = max(frame["latency_ms"] for frame in in_window)

        # X4 — hazard onset -> action landed (the safety-honest zero point,
        # design §2.4's disclosed pin), with the 3-way decomposition recorded
        # so the reopen can re-cut without re-measuring: onset ->
        # observation (the first tick that read the crossed level),
        # observation -> enter-call, and enter-call -> action-landed (the
        # protective write's landing on B). The middle leg is the RIG's OWN
        # bookkeeping — the X3 drain's quiet floor plus X3's computation
        # sit between the observing tick and the engine call — so a future
        # re-cut that wants the engine's response alone sums
        # onset->observation with enter_call->action and EXCLUDES
        # observation->enter_call rather than subtracting a guessed floor
        # out of observation->action.
        if no_trip:
            x4 = None
            onset_to_observation_ms = None
            observation_to_action_ms = None
            observation_to_enter_call_ms = None
            enter_call_to_action_ms = None
            safe_state = None
        else:
            tripped_at = next(
                (
                    rig.tick_times[i]
                    for i in range(tick_mark, len(rig.tick_times))
                    if rig.tick_tripped[i]
                ),
                None,
            )
            assert tripped_at is not None, "the condition never tripped post-dispatch"
            assert t_cross_ns is not None
            rig.monitor.phase = "protecting"
            engine = ProtectionEngine(rig.wrapped, rig.policy, BENCH, rig.clock, rig.wall)
            enter_reasons = (
                list(rig.monitor.violations) if rig.monitor.cause is not None else []
            )
            enter_call_ns = rig.clock.now_ns()
            protection = engine.enter(enter_reasons, rig.clock.now_ns())
            rig.monitor.phase = "idle"
            assert rig.adapter_b.write_landed_ns is not None, "the safe action never landed"
            action_ns = rig.adapter_b.write_landed_ns
            x4 = (action_ns - t_cross_ns) / 1e6
            onset_to_observation_ms = (tripped_at - t_cross_ns) / 1e6
            observation_to_action_ms = (action_ns - tripped_at) / 1e6
            observation_to_enter_call_ms = (enter_call_ns - tripped_at) / 1e6
            enter_call_to_action_ms = (action_ns - enter_call_ns) / 1e6
            safe_state = protection.safe_state

        # The write leg (§2.2's "and a write leg") runs AFTER the protective
        # transition, in the idle phase: the same paced acquisition class
        # through the write verb, completing OK. Its figure is the tick-gap
        # blackout — the wrapper still times every tick, and the thread is
        # still the single engine thread — but idle-phase ticks perform no
        # signal reads, so the write leg cannot trip the fail-safe on its
        # OWN staleness (an in-body write leg would: its 200 ms blackout
        # ages the buffered signal past the dispatch-scale bound before the
        # measured read ever runs, and the trip that blocks is an artifact
        # of pacing jitter, not the hazard). The read leg carries the
        # fully-monitored measurement; the write leg pins the same
        # blackout class from the write verb.
        if arm == "non_capture":
            write_mark = len(rig.tick_times)
            write_result = rig.wrapped[DEVICE_A].dispatch(
                OperationRequest.write("op-acq-w", parameter="acq_scalar", value=1),
                deadline_ns=rig.deadline_ns(T_ACQ_MIN_MS + 500),
            )
            if write_result.status is not OperationStatus.OK:
                # F4/F1: the dead bridge session's door reject is the
                # mid-trial host-pathology class; a device-side write
                # refusal — whatever cause the monitor still holds; the
                # post-trip latch makes it cause-adjacent, not a block
                # (phase is idle here) — and any real write failure stay
                # plain, non-retryable assertions.
                detail = (
                    f"write leg landed {write_result.status.value}: {write_result.error}"
                )
                if _dispatch_failure_is_infrastructure(rig, write_result):
                    raise TrialInfrastructureError(detail, site="write-leg-door")
                raise AssertionError(detail)
            write_gap = _max_tick_gap_ms(rig.tick_times[write_mark:])

        outcome = {
            "arm": arm,
            "device_class": device_class,
            "trial": trial_index,
            "x1_ms": x1,
            "x2_ms": x2,
            "x3_ms": x3,
            "x4_ms": x4,
            "onset_to_observation_ms": onset_to_observation_ms,
            "observation_to_action_ms": observation_to_action_ms,
            "observation_to_enter_call_ms": observation_to_enter_call_ms,
            "enter_call_to_action_ms": enter_call_to_action_ms,
            "dispatch_duration_ms": duration_ms,
            "write_leg_gap_ms": write_gap,
            "in_window_frames": len(in_window),
            "safe_state": safe_state,
            "status": result.status.value,
        }
        rig.teardown_and_close()
        return outcome
    finally:
        # The failure belt: a raised assertion must not leak the store's
        # connection or the bridges' runners (sqlite connections close
        # idempotently; plugin_close is the bridge's own final sweep).
        rig.stream_host.close()
        with suppress(Exception):
            rig.store.close()


# --- check 1: the classifier table (frozen #159 §6, verbatim) -----------------------
#
# The grid enumerates (breach count 0-5 x splittable x spread x bounds
# present x controls asserted) over SYNTHETIC table data — every bound is
# table data, labelled as such, never a commissioned G1/G2/P/TB. Each cell
# must yield exactly one arm (the single-enum return is the totality
# mechanism; the test asserts it across the grid); the 2-of-5/tight/
# bounds/controls cell must read INCONCLUSIVE; a None bound reads
# UNDERPOWERED; equality-at-bound is not a breach.

_BOUNDS = {"X1": 100.0, "X2": 100.0, "X3": 100.0, "X4": 100.0}


def _table_trial(
    *,
    value_ms: float,
    t_acq_controls: bool = True,
    device_class: str = "buffered",
    tightening_admitted: bool = False,
    splitting_admitted: bool = False,
    unsplittable_class: bool = True,
) -> TrialRecord:
    """One synthetic table trial: all four axes at one value (the grid
    varies the breach count by how many trials sit above the bound, not by
    per-axis structure — per-axis structure is covered by the dedicated
    cells below)."""
    return TrialRecord(
        trial=0,
        arm="non_capture",
        device_class=device_class,
        axes_ms={"X1": value_ms, "X2": value_ms, "X3": value_ms, "X4": value_ms},
        t_acq_controls=t_acq_controls,
        tightening_admitted=tightening_admitted,
        splitting_admitted=splitting_admitted,
        unsplittable_class=unsplittable_class,
        parameterization={"fixture": "classifier-table", "value_ms": value_ms},
        command="pytest tests/integration/test_cross_instance_continuity.py"
        " -k classifier (synthetic table data — no rig dispatch)",
    )


def _t_acq_series(breach_values: list[float], *, clean: float = 90.0) -> list[TrialRecord]:
    """Five T_acq_min trials (both controls asserted) whose breach count is
    len([v for v in breach_values]) — the values above the bound of 100.

    Breach values must stay within 25% of the bound of the clean value or
    the series is loose by the rule's own trial-quality gate (the grid's
    tight arm uses 105 against 90: range 15, tight for bound 100)."""
    return [
        _table_trial(value_ms=value, t_acq_controls=True)
        for value in [*breach_values, *[clean] * (5 - len(breach_values))]
    ]


def test_classifier_grid_total_and_single_valued() -> None:
    """Every grid cell yields exactly one arm: the return IS a single enum
    member (totality by construction), asserted cell by cell so a clause
    edit that empties a cell's mapping is visible here. The modal cell —
    2-of-5 breaches, tight spread, bounds present, controls asserted — is
    INCONCLUSIVE, never FIRE or KILL (#159 §6 arm 4 names it)."""
    for breach_count in range(6):
        values = [105.0] * breach_count
        for spread in ("tight", "loose"):
            # tight: every trial at the same value (range 0); loose: the
            # range exceeds 25% of the axis's own bound (140-90=50 > 25).
            trials = _t_acq_series(values)
            if spread == "loose":
                wide = list(trials)
                wide[0] = _table_trial(value_ms=140.0)
                wide[4] = _table_trial(value_ms=90.0)  # range 50 > 25% of 100
                trials = wide
            for bounds in (_BOUNDS, {**_BOUNDS, "X2": None}):
                arm = classify(trials, bounds)
                assert isinstance(arm, Arm), f"non-arm return {arm!r}"
                assert arm in (
                    Arm.UNDERPOWERED,
                    Arm.FIRE,
                    Arm.KILL,
                    Arm.INCONCLUSIVE,
                )
                # The pinned cells:
                if spread == "tight" and bounds is _BOUNDS:
                    if breach_count >= 3:
                        # §6 arm 2: at T_acq_min (both controls asserted),
                        # any axis breaching in >=3 of 5 trials fires.
                        assert arm is Arm.FIRE, f"{breach_count}-of-5: {arm}"
                    else:
                        # 0/1/2-of-5 with tight spread and commissioned
                        # bounds: INCONCLUSIVE (arm 4 names 2-of-5 and
                        # 1-of-5 explicitly).
                        assert arm is Arm.INCONCLUSIVE, f"{breach_count}-of-5: {arm}"
                if spread == "loose":
                    # §6 arm 1: trial range > 25% of the axis's own bound
                    # reads UNDERPOWERED — decide nothing.
                    assert arm is Arm.UNDERPOWERED, f"loose spread: {arm}"
                if bounds["X2"] is None:
                    # §6 denominator clause: a missing bound for ANY axis
                    # blocks that axis's decision; it never defaults.
                    assert arm is Arm.UNDERPOWERED, f"missing X2 bound: {arm}"


def test_classifier_two_of_five_is_inconclusive() -> None:
    """The RED-pinned modal cell on its own (§6 arm 4: "everything else,
    including 2-of-5 and 1-of-5 breach series with tight spread and
    commissioned bounds")."""
    trials = _t_acq_series([105.0, 105.0])
    assert classify(trials, _BOUNDS) is Arm.INCONCLUSIVE


def test_classifier_equality_at_bound_is_not_a_breach() -> None:
    """§6 breach comparator: strictly greater than; equality passes. Five
    trials exactly AT the bound breach nothing — INCONCLUSIVE, not FIRE."""
    at_bound = [_table_trial(value_ms=100.0) for _ in range(5)]
    assert classify(at_bound, _BOUNDS) is Arm.INCONCLUSIVE


def test_classifier_kill_needs_two_classes_five_dispatches_unsplittable() -> None:
    """§6 arm 3: KILL requires >=2 device classes x >=5 dispatches each,
    including >=1 non-compositional un-splittable class, where every
    counted dispatch admits T-tightening or splitting."""
    compliant = dict(t_acq_controls=False, tightening_admitted=True)

    def killable(cls: str, *, unsplittable: bool) -> list[TrialRecord]:
        return [
            _table_trial(
                value_ms=10.0,
                device_class=cls,
                unsplittable_class=unsplittable,
                **compliant,
            )
            for _ in range(5)
        ]

    both = [*killable("buffered", unsplittable=True), *killable("unbuffered", unsplittable=False)]
    assert classify(both, _BOUNDS) is Arm.KILL
    # Without the un-splittable class (critique C4/F3's guard): not KILL.
    all_splittable = [
        *killable("buffered", unsplittable=False),
        *killable("unbuffered", unsplittable=False),
    ]
    assert classify(all_splittable, _BOUNDS) is Arm.INCONCLUSIVE
    # One class only: not KILL.
    assert classify(killable("buffered", unsplittable=True), _BOUNDS) is Arm.INCONCLUSIVE
    # A counted dispatch that admits neither tightening nor splitting
    # blocks the KILL (the exposure survives somewhere).
    blocked = killable("buffered", unsplittable=True)
    blocked[2] = _table_trial(value_ms=10.0, device_class="buffered", t_acq_controls=False)
    with_unblocked = [*blocked, *killable("unbuffered", unsplittable=False)]
    assert classify(with_unblocked, _BOUNDS) is Arm.INCONCLUSIVE


def test_classifier_refuses_to_arm_fire_and_kill_on_the_same_set() -> None:
    """§6 arm 3's construction clause: "T_acq_min dispatches are KILL-exempt
    by construction (their controls assert neither tightening nor splitting
    is available), so FIRE and KILL cannot arm on the same set." Two
    discriminating forms, both over tight data (a loose series reads
    UNDERPOWERED by the rule's own trial-quality gate):

    1. PRECEDENCE: a set whose FIRE predicate (3-of-5 T_acq breaches) AND
       KILL predicate (>=2 classes x >=5 admitting dispatches, one
       un-splittable) are both satisfiable resolves to exactly ONE arm —
       FIRE, the higher-precedence one.
    2. EXEMPTION: T_acq trials marked splitting-admitted (the adversarial
       double marking) NEVER count toward KILL's per-class dispatch
       minimums — with only one genuine non-T_acq class the set reads
       INCONCLUSIVE, not KILL."""
    fire_side = _t_acq_series([105.0, 105.0, 105.0])  # 3-of-5 breaches
    kill_side = [
        *[
            _table_trial(
                value_ms=90.0,
                device_class="unbuffered",
                t_acq_controls=False,
                splitting_admitted=True,
                unsplittable_class=True,
            )
            for _ in range(5)
        ],
        *[
            _table_trial(
                value_ms=90.0,
                device_class="third",
                t_acq_controls=False,
                tightening_admitted=True,
                unsplittable_class=False,
            )
            for _ in range(5)
        ],
    ]
    arm = classify([*fire_side, *kill_side], _BOUNDS)
    assert arm is Arm.FIRE, f"both-predicate input must resolve to exactly FIRE, got {arm}"

    double_marked = [
        _table_trial(
            value_ms=90.0,
            t_acq_controls=True,
            splitting_admitted=True,
            device_class="buffered",
            unsplittable_class=True,
        )
        for _ in range(5)
    ]
    one_real_class = [
        _table_trial(
            value_ms=90.0,
            device_class="unbuffered",
            t_acq_controls=False,
            splitting_admitted=True,
            unsplittable_class=True,
        )
        for _ in range(5)
    ]
    arm = classify([*double_marked, *one_real_class], _BOUNDS)
    assert arm is Arm.INCONCLUSIVE, (
        f"T_acq dispatches must never count toward KILL's class minimums: {arm}"
    )


def test_classifier_fire_requires_exactly_five_t_acq_trials() -> None:
    """§6 arm 2's denominator is its own letter: ">=3 of 5 trials" — the
    FIRE series is EXACTLY five T_acq trials. A longer series with the same
    breach count (3-of-8) or the same breach rate (3-of-10, rate 0.3) is
    not the clause's input shape: it falls through to arm 4 ("everything
    else ... raise n and re-run") and reads INCONCLUSIVE, never FIRE."""
    def series(values: list[float]) -> list[TrialRecord]:
        return [_table_trial(value_ms=value, t_acq_controls=True) for value in values]

    # The exactly-5 comparator: 3 breaches in a 5-series fires.
    assert classify(series([105.0] * 3 + [90.0] * 2), _BOUNDS) is Arm.FIRE
    # 3-of-8 (breach count held, n grown): INCONCLUSIVE, not FIRE.
    assert classify(series([105.0] * 3 + [90.0] * 5), _BOUNDS) is Arm.INCONCLUSIVE
    # 3-of-10 (the rate-0.3 class input): INCONCLUSIVE, not FIRE.
    assert classify(series([105.0] * 3 + [90.0] * 7), _BOUNDS) is Arm.INCONCLUSIVE


def test_classifier_never_pools_across_device_classes() -> None:
    """Device classes never pool (design §2.8): X2 is class-dependent BY
    DESIGN — buffered reads dispatch-scale ages (~220 ms on this rig),
    unbuffered collapses to host skew (~1 ms) — so a pooled breach count
    mixes populations and can manufacture FIRE from two underpowered
    halves. Arms 1/2/4 evaluate per class; KILL alone aggregates across
    classes (its own §6 letter). The aggregation keeps §6's precedence: an
    underpowered class blocks (arm 1) before a firing class fires (arm 2)."""
    pooled_fire_shaped = [
        *[
            _table_trial(value_ms=105.0, t_acq_controls=True, device_class="buffered")
            for _ in range(3)
        ],
        *[
            _table_trial(value_ms=90.0, t_acq_controls=True, device_class="unbuffered")
            for _ in range(2)
        ],
    ]
    # Pooled, this ledger is a 5-series with 3 breaches (FIRE-shaped); per
    # class it is a 3-series and a 2-series — neither is the 5-trial FIRE
    # input, so the ledger reads INCONCLUSIVE.
    assert classify(pooled_fire_shaped, _BOUNDS) is Arm.INCONCLUSIVE

    separated_fire = [
        *[
            _table_trial(value_ms=105.0, t_acq_controls=True, device_class="buffered")
            for _ in range(5)
        ],
        *[
            _table_trial(value_ms=90.0, t_acq_controls=True, device_class="unbuffered")
            for _ in range(5)
        ],
    ]
    # The same measurements, per class complete: the buffered class's own
    # 5-series fires (5-of-5 breaches); the unbuffered class's clean series
    # does not veto it (no class reads UNDERPOWERED) — the ledger reads FIRE.
    assert classify(separated_fire, _BOUNDS) is Arm.FIRE

    one_class_loose = [
        *[
            _table_trial(value_ms=value, t_acq_controls=True, device_class="buffered")
            for value in [105.0, 105.0, 105.0, 90.0, 90.0]
        ],
        *[
            _table_trial(value_ms=value, t_acq_controls=True, device_class="unbuffered")
            for value in [140.0, 90.0]
        ],
    ]
    # §6 precedence across classes: the unbuffered class's loose range
    # (140-90 = 50 > 25% of the 100 bound) blocks the buffered class's
    # FIRE-shaped series — the ledger reads UNDERPOWERED, decide nothing.
    assert classify(one_class_loose, _BOUNDS) is Arm.UNDERPOWERED


def test_classifier_refuses_inconsistent_unsplittable_labels() -> None:
    """The un-splittable label is a per-class qualification fact (design
    §2.8, finding F-C): one declaration per class. A ledger whose class
    carries both labels is malformed input — the classifier refuses it
    loudly instead of silently reading one trial's label for the group."""
    inconsistent = [
        _table_trial(
            value_ms=10.0,
            device_class="buffered",
            t_acq_controls=False,
            tightening_admitted=True,
            unsplittable_class=True,
        ),
        _table_trial(
            value_ms=10.0,
            device_class="buffered",
            t_acq_controls=False,
            tightening_admitted=True,
            unsplittable_class=False,
        ),
    ]
    with pytest.raises(ValueError, match="unsplittable_class"):
        classify(inconsistent, _BOUNDS)


def test_classifier_absent_axis_reads_underpowered() -> None:
    """§6 arm 1's single-instance clause: an axis NO trial measured (the
    single-instance rig cannot measure X2-X4) reads UNDERPOWERED even with
    every bound present."""
    partial = [
        TrialRecord(
            trial=1,
            arm="non_capture",
            device_class="buffered",
            axes_ms={"X1": 50.0},
            t_acq_controls=True,
            tightening_admitted=False,
            splitting_admitted=False,
            unsplittable_class=True,
            parameterization={"fixture": "classifier-table"},
            command="pytest -k classifier (synthetic table data)",
        )
    ]
    assert classify(partial, _BOUNDS) is Arm.UNDERPOWERED


# --- check 3: the provenance emitter's shape ---------------------------------------


def test_emit_trial_log_every_numeric_row_carries_command_and_parameterization() -> None:
    """The machine-enforceable half of "every record-quoted figure cites a
    reproducing command": each numeric row in the emitted log carries both
    ``command`` and ``parameterization`` (quoting-into-prose discipline
    stays review-rubric territory — the design's check-3 deferral)."""
    records = _t_acq_series([140.0, 140.0])
    log = emit_trial_log(records)
    rows = log["rows"]
    assert rows, "the emitted log carries no rows"
    numeric_rows = [row for row in rows if isinstance(row.get("value_ms"), (int, float))]
    assert numeric_rows, "no numeric rows to shape-check"
    for row in numeric_rows:
        assert isinstance(row.get("command"), str) and row["command"], row
        assert isinstance(row.get("parameterization"), dict), row
        assert row["parameterization"], row
    # Axis identity and clock domain ride every figure row (the domain pin
    # is #159 §6's critique-C5 clause).
    for row in numeric_rows:
        assert row["axis"] in ("X1", "X2", "X3", "X4"), row
        assert row["clock_domain"] in ("monotonic", "wall"), row


# --- the measured trials (§5.1/§5.3: 5/5 per arm x class, all four axes) ------------
#
# One module-level cell cache: the cells are expensive (a fresh rig per
# trial on a fresh store — the trial IS the unit), and the acceptance
# assertions in the tests below read the SAME trials rather than
# re-measuring. A structurally failed cell fails every test that reads
# it, loudly; a BAND breach no longer does — it is the one-shot cell
# belt's to absorb (one re-measure) — and this raw cache is never
# rewritten by the belt (refute fold C5: the pre-belt claim "a failed
# cell fails every test that reads it" held before the belt existed).

_TRIAL_CELLS: dict[tuple[str, str], list[dict[str, Any]]] = {}


def _cell(tmp_path: Path, arm: str, device_class: str, *, count: int = 5) -> list[dict[str, Any]]:
    key = (arm, device_class)
    if key not in _TRIAL_CELLS:
        _TRIAL_CELLS[key] = [
            run_trial(
                tmp_path, arm=arm, device_class=device_class, trial_index=index
            )
            for index in range(1, count + 1)
        ]
    return _TRIAL_CELLS[key]


def _median(values: list[float]) -> float:
    return statistics.median(values)


def _axis_upper_band_breaches(trials: list[dict[str, Any]], arm: str) -> list[str]:
    """The two observed-red per-trial UPPER bands of the axis-trials test,
    re-homed behind the one-shot cell belt (issue #241 slice 3, design
    §1.2): the dispatch duration and X1 both sit in ``[0, dispatch + 150]``
    — the breach values are byte-identical to the inline asserts they
    replace (breach iff NOT ``value <= bound``). Every FLOOR stays inline
    in the test: host load inflates, it does not deflate, so lower bounds
    are not the flake class and never gain a re-roll."""
    dispatch_ms = _ARM_DISPATCH_MS[arm]
    breaches: list[str] = []
    for trial in trials:
        if trial["dispatch_duration_ms"] > dispatch_ms + 150:
            breaches.append(
                f"dispatch_duration_ms {trial['dispatch_duration_ms']:.1f} exceeds "
                f"the {dispatch_ms:.0f} + 150 ms band: {trial}"
            )
        if trial["x1_ms"] > dispatch_ms + 150:
            breaches.append(
                f"x1_ms {trial['x1_ms']:.1f} exceeds the "
                f"{dispatch_ms:.0f} + 150 ms band: {trial}"
            )
    return breaches


def _assert_x1_floor(trials: list[dict[str, Any]], arm: str) -> None:
    """The X1 FLOOR — the serial-model disclosure pin — asserted on BOTH
    generations (refute fold A, issue #241 slice 3: adv-F1/mech-F3): host
    load inflates X1, so a lower bound on a load-inflated quantity cannot
    false-red, and gen-1's violation must red even when the belt absorbed
    a gen-1 band breach with a clean fresh draw. The floor never triggers
    a re-roll — it is asserted, never belt-evaluated."""
    dispatch_ms = _ARM_DISPATCH_MS[arm]
    for trial in trials:
        assert dispatch_ms - 50 <= trial["x1_ms"], (
            f"X1 floor (the serial-model disclosure pin) breached on trial "
            f"{trial['trial']}: {trial}"
        )


#: The one-shot cell belt's fresh generations (issue #241 slice 3, design
#: §1.2): ONE re-run per (arm, device_class) key, shared by every belt
#: reader — whichever reader breaches first certifies the generation, and
#: later readers evaluate the certified cell, so reader verdicts are
#: order-independent (each reader evaluates gen-1, then the certified
#: generation, in that order whatever the test order). The raw gen-1 cache
#: (``_TRIAL_CELLS``) is never rewritten: what was measured stays what the
#: trial log records; the belt's generations are printed, never
#: substituted into the log's gen-1.
_BELT_FRESH_GENERATIONS: dict[tuple[str, str], list[dict[str, Any]]] = {}
#: Generation count per key, asserted ``<= 1`` at every certification: the
#: bound is structural (the memo guard admits one generation per key) and
#: the assert pins it in code, so a future widening of the guard trips the
#: assert instead of silently re-rolling.
_BELT_GENERATION_RUNS: dict[tuple[str, str], int] = {}


def _belt_fresh_generation(
    tmp_path: Path, arm: str, device_class: str
) -> list[dict[str, Any]]:
    """The belt's re-measure: five fresh ``run_trial`` invocations,
    ``trial_index`` 51–55 — a range no other caller uses: the module's
    direct ``trial_index=`` callers, grep-verified at build (refute fold
    C1) and re-verified at the slice-4 refute fold (pins 9 and 10 added),
    are 1, 3, 6, 7, 8, 9, 10, 11, 44, 45, 46, 99 — so the fresh stores
    never collide with a cached cell's or another test's."""
    return [
        run_trial(tmp_path, arm=arm, device_class=device_class, trial_index=index)
        for index in range(51, 56)
    ]


def _render_belt_trial(trial: dict[str, Any]) -> str:
    """One trial line for the belt's both-generations failure render."""
    return (
        f"trial {trial['trial']}: X1={trial['x1_ms']:.1f} X2={trial['x2_ms']:.1f} "
        f"X3={trial['x3_ms']:.1f} X4={trial['x4_ms']:.1f} "
        f"(dur {trial['dispatch_duration_ms']:.1f}, retries {trial['retries']})"
    )


def _certified_cell(
    tmp_path: Path,
    arm: str,
    device_class: str,
    evaluate: Callable[[list[dict[str, Any]]], list[str]],
) -> list[dict[str, Any]]:
    """The frozen #159 §6 arm 4 mechanized, bounded at ONE re-run (issue
    #241 slice 3, design §1.2): evaluate the shared cached cell; a
    non-empty breach list certifies ONE fresh generation for the key; a
    fresh breach FAILS rendering BOTH generations' breaches and values —
    the kill direction: a systematically-loose fixture is caught twice and
    the red is §5's honest "underpowered, decide nothing". Only band
    breaches re-measure: ``evaluate`` returns a breach list and the belt
    never inspects exception types, so a structural failure raised inside
    an evaluator propagates immediately with zero fresh generations
    (pinned below). The disclosed price (design §1.2): for a fixture loose
    enough to pass any single 5-trial draw with per-generation probability
    p, the belt raises the per-execution pass probability to 1-(1-p)^2 —
    immaterial for looseness that matters against an 8.3x quiet margin
    (trimmed spread 6.0 ms vs the 50 ms bound, 384 readings, slice-2
    Evidence C.4) and proven toothy by the forced-loose pin."""
    key = (arm, device_class)
    trials = _cell(tmp_path, arm, device_class)
    breaches = evaluate(trials)
    if not breaches:
        return trials
    if key not in _BELT_FRESH_GENERATIONS:
        _BELT_FRESH_GENERATIONS[key] = _belt_fresh_generation(
            tmp_path, arm, device_class
        )
        _BELT_GENERATION_RUNS[key] = _BELT_GENERATION_RUNS.get(key, 0) + 1
        assert _BELT_GENERATION_RUNS[key] <= 1, (
            f"the belt re-ran more than one fresh generation for "
            f"{arm}/{device_class} — the bound is one re-run per cell"
        )
        print(
            f"\n{arm}/{device_class} belt: gen-1 breached a re-measurable "
            "band — certifying the one fresh generation (trials 51-55)"
        )
    fresh = _BELT_FRESH_GENERATIONS[key]
    fresh_breaches = evaluate(fresh)
    if fresh_breaches:
        raise AssertionError(
            f"{arm}/{device_class}: the one-shot cell belt re-measured "
            "(trials 51-55) and the breach held on BOTH generations — a "
            "systematically-loose fixture, not a transient host stall; "
            "§5's honest verdict is this red (underpowered, decide "
            "nothing).\n"
            "gen-1 breaches:\n  " + "\n  ".join(breaches) + "\n"
            "fresh-generation breaches:\n  " + "\n  ".join(fresh_breaches) + "\n"
            "gen-1 trials:\n  "
            + "\n  ".join(_render_belt_trial(trial) for trial in trials)
            + "\n"
            "fresh-generation trials:\n  "
            + "\n  ".join(_render_belt_trial(trial) for trial in fresh)
        )
    print(
        f"\n{arm}/{device_class} belt: the fresh generation cleared the "
        f"breach (generations re-run for this key: "
        f"{_BELT_GENERATION_RUNS[key]})"
    )
    return fresh


@pytest.mark.parametrize(
    ("arm", "device_class"),
    [("capture", "buffered"), ("capture", "unbuffered"),
     ("non_capture", "buffered"), ("non_capture", "unbuffered")],
)
def test_axis_trials_complete_all_four_axes(
    tmp_path: Path, arm: str, device_class: str
) -> None:
    """§5.1: every (arm, class) produces 5/5 completed trials with all four
    axes recorded; §5.3: X1's max tick gap sits in the per-arm blackout
    band [dispatch - 50, dispatch + 150] (the reference is the arm's own
    in-flight duration — the capture arm CUTS at its budget, the
    non-capture arm COMPLETES at T_acq_min; if this ever fails the serial
    model changed and the disclosure is stale). The write leg's gap is
    recorded on the non-capture arm (§2.2's second leg). The retry cap is
    part of the acceptance: a trial runs a fixed three-attempt budget (the
    initial attempt plus two retries — exhaustion builds exactly three
    rigs, pinned ``len(rigs) == 3``), and a chronically starved host must
    not ship all-green on the retry crutch —
    the assert trips if the retry loop is ever widened without amending
    the acceptance rule.

    The two per-trial UPPER bands — the dispatch duration and X1 against
    ``dispatch + 150`` — read through the one-shot cell belt (issue #241
    slice 3, design §1.2): a gen-1 breach re-measures the cell once, so
    the multi-stall host shape among tight trials is absorbed without
    touching the reading, and a fresh breach reds with both generations
    rendered. The floors and every structural assert stay inline and hard
    and never trigger a re-roll themselves — but they evaluate whichever
    generation the belt returns: an absorbed gen-1 band breach skips
    gen-1's floor/structural verdicts, EXCEPT the load-safe X1 floor,
    which asserts on BOTH generations (refute fold A; load inflates X1,
    so its lower bound cannot false-red). The retry cap, in_window_frames,
    and the write-leg gap band stay return-generation-only — re-asserting
    gen-1's load-inflated upper quantities would reintroduce the flake
    class this slice retires.

    The named residual families (issue #241 slice 4's register — the
    §5.2 accounting tolerates these BY NAME, and a red without the
    family's signature is NOT in one): chronic-starvation exhaustion —
    a trial's fixed three-attempt budget exhausts on infrastructure
    sites, the composition rendered in the red; sustained-stretch —
    three distinct band families breaching in one execution, the belt
    reding on both generations by design (underpowered, decide
    nothing)."""
    trials = _certified_cell(
        tmp_path, arm, device_class, lambda cell: _axis_upper_band_breaches(cell, arm)
    )
    assert len(trials) == 5
    # gen-1's X1 floor is always audited — a cached read, never a
    # re-measure — then the certified generation's (identical when the
    # belt returned gen-1).
    _assert_x1_floor(_cell(tmp_path, arm, device_class), arm)
    _assert_x1_floor(trials, arm)
    for trial in trials:
        for axis in ("x1_ms", "x2_ms", "x3_ms", "x4_ms"):
            assert trial[axis] is not None, (arm, device_class, trial["trial"], axis)
        assert trial["in_window_frames"] >= 1, trial
        assert trial["retries"] <= 2, (
            f"trial retried {trial['retries']} times (max 2): {trial}"
        )
        sites_note = (
            f", sites {','.join(trial['retry_sites'])}"
            if trial["retry_sites"]
            else ""
        )
        print(
            f"\n{arm}/{device_class} trial {trial['trial']}: "
            f"X1={trial['x1_ms']:.1f} X2={trial['x2_ms']:.1f} "
            f"X3={trial['x3_ms']:.1f} X4={trial['x4_ms']:.1f} "
            f"(dur {trial['dispatch_duration_ms']:.1f}, "
            f"onset->obs {trial['onset_to_observation_ms']:.1f}, "
            f"obs->enter {trial['observation_to_enter_call_ms']:.1f}, "
            f"enter->action {trial['enter_call_to_action_ms']:.1f}, "
            f"safe {trial['safe_state']}, "
            f"retries {trial['retries']}{sites_note})"
        )
    if arm == "non_capture":
        # The write leg blacked out ticks too (the exposure class runs
        # through writes as well as reads).
        for trial in trials:
            gap = trial["write_leg_gap_ms"]
            assert gap is not None
            assert T_ACQ_MIN_MS - 50 <= gap <= T_ACQ_MIN_MS + 150, trial


def test_control_arm_and_separation(tmp_path: Path) -> None:
    """§5.2 — the instrument's floor semantics (a control that passes both
    ways proves nothing) plus §2.5 control (i): the matched short-T
    control FAILS the acquisition (TIMEOUT/UNKNOWN, never OK — the pacing
    is a real floor for this fixture, not a label)."""
    control = _cell(tmp_path, "control", "buffered")
    long_arm = _cell(tmp_path, "non_capture", "buffered")
    for trial in control:
        assert trial["status"] == "unknown", trial
        assert trial["retries"] <= 2, trial
    control_x2 = _median([t["x2_ms"] for t in control])
    control_x3 = max(t["x3_ms"] for t in control)
    control_x4 = max(t["x4_ms"] for t in control)
    long_x2 = _median([t["x2_ms"] for t in long_arm])
    long_x3 = max(t["x3_ms"] for t in long_arm)
    long_x4 = _median([t["x4_ms"] for t in long_arm])
    print(
        f"\nseparation: long X2 median {long_x2:.1f} vs control {control_x2:.1f}; "
        f"X3 worst {long_x3:.1f} vs {control_x3:.1f}; "
        f"X4 {long_x4:.1f} vs {control_x4:.1f}"
    )
    assert long_x2 >= T_ACQ_MIN_MS - 50, "long-arm X2 did not reach dispatch scale"
    assert control_x2 <= 50, "control X2 exceeded the 50 ms floor bound"
    assert long_x3 >= T_ACQ_MIN_MS - 50, "long-arm X3 did not reach dispatch scale"
    assert control_x3 <= 3 * POLL_MS, "control X3 exceeded 3x poll_ms"
    assert long_x4 >= T_ACQ_MIN_MS - 50, "long-arm X4 did not reach dispatch scale"
    assert control_x4 <= 1000, "control X4 exceeded the 1 s protection-shaped bound"
    # The honest unbuffered comparator (§2.3): X2 collapses to host-side
    # skew on the fresh-conversion class — the axis quantity is
    # device-class-dependent and a bench must declare its class.
    unbuffered = _cell(tmp_path, "non_capture", "unbuffered")
    unbuffered_x2 = _median([t["x2_ms"] for t in unbuffered])
    assert unbuffered_x2 < 50, (
        f"unbuffered X2 {unbuffered_x2:.1f} did not collapse to host-side skew"
    )


#: §5's instrument-level range-gate denominator: the rig's DISPATCH
#: DURATION — the 200 ms acquisition class BOTH arms instantiate (§5's
#: fixture scale names one dispatch arm, 200 ms; the capture arm CUTS the
#: same acquisition at its 50 ms budget, §8(d)). A per-arm reading (50 ms
#: for the capture cells) was measured and rejected: its 12.5 ms gate sits
#: INSIDE the host's own cut-overshoot distribution — single-trial
#: deadline-max overshoots of 12.3 ms and 16.2 ms on the 50 ms cut in
#: consecutive local runs, on different trials (stochastic scheduler
#: stalls, not fixture scatter) — so a per-arm gate would flake on host
#: load the fixture cannot pace, violating the clause's own intent (the
#: range measures INSTRUMENT precision). Explicitly never a commissioned
#: bound (§0's first rule).
_RANGE_GATE_DENOMINATOR_MS = T_ACQ_MIN_MS


def _underpowered_range_ms(values: list[float]) -> float:
    """§5's per-axis range reading over one cell's trials, TRIMMED of the
    single most extreme trial (the one furthest from the median).

    [#217 unblock, licensed by item 7's own rationale:] the record REJECTED
    the per-arm denominator because 'single-trial deadline-max overshoots
    ... would flake on scheduler stalls rather than catch loose pacing' —
    the clause measures INSTRUMENT precision ('fix fixture pacing, decide
    nothing'), and one host-stalled trial among tight trials is exactly
    that stall class, not loose pacing. The trim is bounded to ONE trial
    per axis: a systematically-spread fixture (every trial scattered) and
    a double-spiked shape still exceed the bound — pinned in
    test_range_gate_tolerance_both_directions, the still-catches
    direction. The frozen §6 classifier's own range arm (check 1,
    _continuity_rule.py, commissioned bounds) is untouched."""
    if len(values) <= 2:
        return max(values) - min(values)
    centre = statistics.median(values)
    trimmed = list(values)
    trimmed.remove(max(values, key=lambda v: abs(v - centre)))
    return max(trimmed) - min(trimmed)


def _range_gate_evaluation(
    arm: str, device_class: str
) -> Callable[[list[dict[str, Any]]], list[str]]:
    """The belt's evaluate closure for the spread loop, built by factory so
    the loop's variables bind at construction (a loop-body lambda with
    parameter defaults late-binds through mypy's inference floor)."""
    return lambda cell: _range_gate_breaches(cell, arm, device_class)


def _range_gate_breaches(
    trials: list[dict[str, Any]], arm: str, device_class: str
) -> list[str]:
    """The §5 spread loop of the range-gate test, re-homed behind the
    one-shot cell belt (issue #241 slice 3, design §1.2): the READING is
    untouched — ``_underpowered_range_ms`` over each axis's five values
    against 25% of the dispatch duration — and a breach carries the exact
    message the inline assert carried (trimmed and raw range, values)."""
    breaches: list[str] = []
    for axis_key in ("x1_ms", "x2_ms", "x3_ms", "x4_ms"):
        values = [trial[axis_key] for trial in trials]
        spread = _underpowered_range_ms(values)
        if spread > 0.25 * _RANGE_GATE_DENOMINATOR_MS:
            breaches.append(
                f"{arm}/{device_class} {axis_key.upper()}: trial range "
                f"{spread:.1f} ms (raw {max(values) - min(values):.1f}) "
                f"over {len(values)} trials exceeds 25% of "
                f"the {_RANGE_GATE_DENOMINATOR_MS:.0f} ms dispatch "
                "duration — §5's UNDERPOWERED reading (fix fixture "
                "pacing, decide nothing; the reading is trimmed of the "
                "single most extreme trial, one host stall tolerated); "
                f"values: {[round(v, 1) for v in values]}"
            )
    return breaches


def test_instrument_range_gate_per_axis_per_cell(tmp_path: Path) -> None:
    """§5's instrument-level UNDERPOWERED clause, machine-checked: any
    axis's trial range > 25% of the DISPATCH DURATION reads UNDERPOWERED —
    fix fixture pacing, decide nothing (the denominator and the rejected
    per-arm reading are documented at ``_RANGE_GATE_DENOMINATOR_MS``).
    The gate covers the four measurement cells; the short-dispatch CONTROL
    is deliberately excluded — its X2/X3/X4 are cadence/response-scale
    quantities bounded by §5.2 through medians and maxima (poll_ms
    multiples, the protection shape), and a 25%-of-20-ms range gate on
    them would demand 5 ms stability of latencies §5.2 itself allows to
    reach 150 ms — a scale mismatch the clause never committed to, and a
    flake generator rather than a quality gate.

    The spread loop reads through the one-shot cell belt (issue #241
    slice 3, design §1.2): the READING is untouched — 25% of the dispatch
    duration, trimmed of one trial — a gen-1 breach re-measures the cell
    ONCE (a 2–3-stall host shape among tight trials is the runner, not
    the fixture; every in-lane range-gate red since slice 2 was that
    shape), and a fresh breach reds with both generations rendered — a
    systematically-loose fixture is still caught, twice."""
    for arm in ("capture", "non_capture"):
        for device_class in ("buffered", "unbuffered"):
            trials = _certified_cell(
                tmp_path,
                arm,
                device_class,
                _range_gate_evaluation(arm, device_class),
            )
            assert len(trials) == 5, (
                "the certified cell carries five trials — an empty cell "
                "would evaluate clean without measuring anything"
            )


# --- the one-shot cell belt's own pins (#241 slice 3, design §5.1 AR-1) --------------


def test_belt_forced_loose_fixture_reds_on_both_generations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AR-1.1, the kill direction for "re-roll until green": a
    systematically-loose fixture — ``_pace`` re-scaled per rig by a
    deterministic factor ladder, so every trial scatters — breaches gen-1
    AND the belt's one fresh generation, and the belt FAILS rendering
    BOTH generations. RED on the pre-belt line is the standing behavior
    (the same scattered fixture reds today's gate on gen-1 alone; shown
    at build with the belt neutralized to the pre-belt shape — fail on
    first breach, no re-run). The ladder keeps every trial INSIDE the
    inline floors (X1 in [160, 280] ms against the 150 ms floor on the
    200 ms class), so the red is the range gate's spread reading, on both
    generations of it. The module caches are snapshotted and restored
    around the arm: the scattered cell must never leak into the
    measurement tests' gen-1 cache."""
    ladder = (0.8, 1.0, 1.2, 0.9, 1.4)
    adapters: list[ARigAdapter] = []
    original_init = ARigAdapter.__init__

    def counting_init(self: ARigAdapter) -> None:
        original_init(self)
        adapters.append(self)

    monkeypatch.setattr(ARigAdapter, "__init__", counting_init)
    original_pace = ARigAdapter._pace

    async def scattered_pace(self: ARigAdapter, total_ms: float) -> None:
        # Systematic looseness: each rig's acquisition paces to a
        # different duration (±40%), so every trial in the cell scatters —
        # no single outlier for the one-trial trim to absorb.
        await original_pace(
            self, total_ms * ladder[adapters.index(self) % len(ladder)]
        )

    monkeypatch.setattr(ARigAdapter, "_pace", scattered_pace)
    saved_cells = dict(_TRIAL_CELLS)
    saved_fresh = dict(_BELT_FRESH_GENERATIONS)
    saved_runs = dict(_BELT_GENERATION_RUNS)
    _TRIAL_CELLS.clear()
    _BELT_FRESH_GENERATIONS.clear()
    _BELT_GENERATION_RUNS.clear()
    try:
        with pytest.raises(AssertionError, match="BOTH generations") as raised:
            _certified_cell(
                tmp_path,
                "non_capture",
                "buffered",
                lambda cell: _range_gate_breaches(cell, "non_capture", "buffered"),
            )
        assert _BELT_GENERATION_RUNS[("non_capture", "buffered")] == 1, (
            "the belt must have re-measured exactly once before redding"
        )
        assert "fresh-generation breaches" in str(raised.value), str(raised.value)
    finally:
        _TRIAL_CELLS.clear()
        _TRIAL_CELLS.update(saved_cells)
        _BELT_FRESH_GENERATIONS.clear()
        _BELT_FRESH_GENERATIONS.update(saved_fresh)
        _BELT_GENERATION_RUNS.clear()
        _BELT_GENERATION_RUNS.update(saved_runs)


def test_belt_absorbs_a_single_stall_with_one_fresh_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AR-1.2, the absorption direction: gen-1's evaluation returns one
    breach (the transient single-stall shape among tight trials), the
    belt's ONE fresh generation evaluates clean, and the helper hands
    back the certified cell with generation-re-runs 1 recorded. Synthetic
    evaluators and a monkeypatched fresh-generation seam: this pin
    exercises the BELT's decision logic only — the real fixture paths are
    AR-1.1's (both generations, real trials, real breach) and the
    axis/range-gate tests' own reads. The module memos are snapshotted
    and restored (refute fold C4): the synthetic key must not linger in
    them after the pin."""
    key = ("capture", "belt-pin-single-stall")
    gen1 = [{"trial": index} for index in range(1, 6)]
    gen2 = [{"trial": index} for index in range(51, 56)]
    evaluations: list[int] = []

    def single_stall_then_clean(cell: list[dict[str, Any]]) -> list[str]:
        evaluations.append(len(cell))
        if len(evaluations) == 1:
            return ["synthetic single-stall breach (one trial stretched)"]
        return []

    monkeypatch.setitem(globals(), "_cell", lambda *args: gen1)
    monkeypatch.setitem(globals(), "_belt_fresh_generation", lambda *args: gen2)
    saved_cells = dict(_TRIAL_CELLS)
    saved_fresh = dict(_BELT_FRESH_GENERATIONS)
    saved_runs = dict(_BELT_GENERATION_RUNS)
    _TRIAL_CELLS.clear()
    _BELT_FRESH_GENERATIONS.clear()
    _BELT_GENERATION_RUNS.clear()
    try:
        certified = _certified_cell(tmp_path, key[0], key[1], single_stall_then_clean)
        assert certified is gen2, "the belt must hand back the certified generation"
        assert _BELT_FRESH_GENERATIONS[key] is gen2, "the memo holds the certification"
        assert _BELT_GENERATION_RUNS[key] == 1, _BELT_GENERATION_RUNS[key]
        assert len(evaluations) == 2, evaluations
    finally:
        _TRIAL_CELLS.clear()
        _TRIAL_CELLS.update(saved_cells)
        _BELT_FRESH_GENERATIONS.clear()
        _BELT_FRESH_GENERATIONS.update(saved_fresh)
        _BELT_GENERATION_RUNS.clear()
        _BELT_GENERATION_RUNS.update(saved_runs)


def test_belt_never_re_runs_a_structural_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AR-1.3, the scope pin: the belt re-rolls the two band families
    ONLY. A structural failure — a plain ``AssertionError`` raised by the
    evaluator itself, not a band breach — propagates immediately, with
    ZERO fresh generations run (pinned via the memo: no certified cell,
    no recorded run). The non-interception is structural, not
    policy-checked: the belt never inspects exception types, and an
    exception from ``evaluate`` never reaches the generation branch."""
    key = ("capture", "belt-pin-structural")
    monkeypatch.setitem(
        globals(), "_cell", lambda *args: [{"trial": index} for index in range(1, 6)]
    )

    def structural(cell: list[dict[str, Any]]) -> list[str]:
        raise AssertionError("structural: an axis failed to record")

    with pytest.raises(AssertionError, match="structural") as raised:
        _certified_cell(tmp_path, key[0], key[1], structural)
    assert type(raised.value) is AssertionError
    assert key not in _BELT_FRESH_GENERATIONS, (
        "a structural failure must not certify a fresh generation"
    )
    assert _BELT_GENERATION_RUNS.get(key, 0) == 0, _BELT_GENERATION_RUNS


def test_belt_swap_still_audits_gen1_x1_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refute fold A (adv-F1 / mech-F3, MEDIUM): when gen-1 breaches a
    belt band and the fresh draw is clean, the belt hands back the FRESH
    cell — and the axis test's inline asserts then evaluated the fresh
    cell only, so a gen-1 X1-floor violation (the serial-model disclosure
    pin) shipped green (the adversary's A/B: the poisoned shape passed at
    the pre-fold tip where origin/main reds). The fix asserts the
    load-safe X1 floor on BOTH generations; this pin drives the REAL
    axis test — first five adapters scattered by a factor ladder (one
    trial below the 150 ms floor, one past the 350 ms upper band), every
    later adapter healthy, so gen-1 breaches a band AND violates the
    floor while the belt's fresh generation is clean — and the floor must
    RED on gen-1 through the swapped verdict. RED-shown at build against
    the pre-fix shape (the gen-1 floor call neutralized out of the axis
    test): the poisoned cell then passes — the exact defect.

    Slice 4 (run 36867869659): the ladder indexes by PACED order — an
    infrastructure retry's rig is discarded before its acquisition (never
    paces), so construction-order indexing shifted the ladder under load:
    the discarded rig consumed a poisoning slot, gen-1 drew floor-only,
    the belt correctly certified nothing (the observed empty map), and
    the floor audit reded through the pin's own swap post-condition — or
    the mirrored shift silently vacated the pin. The pace hook appends an
    adapter on its first pace call; the counting __init__ stays as the
    construction registry."""
    ladder = (0.55, 1.0, 1.9, 0.75, 1.45)
    adapters: list[ARigAdapter] = []
    original_init = ARigAdapter.__init__

    def counting_init(self: ARigAdapter) -> None:
        original_init(self)
        adapters.append(self)

    monkeypatch.setattr(ARigAdapter, "__init__", counting_init)
    original_pace = ARigAdapter._pace

    paced: list[ARigAdapter] = []

    async def first_five_scattered_pace(self: ARigAdapter, total_ms: float) -> None:
        # Slice 4: indexed by PACED order — append on FIRST pace; a rig
        # discarded before its acquisition never paces and consumes no
        # ladder slot (an infrastructure retry under load shifted a
        # construction-indexed ladder: run 36867869659 reded the pin's own
        # swap post-condition on an empty belt map; the mirrored shift
        # silently vacates the pin). The counting __init__ stays as the
        # construction registry.
        if self not in paced:
            paced.append(self)
        index = paced.index(self)
        if index < len(ladder):
            await original_pace(self, total_ms * ladder[index])
        else:
            await original_pace(self, total_ms)

    monkeypatch.setattr(ARigAdapter, "_pace", first_five_scattered_pace)
    saved_cells = dict(_TRIAL_CELLS)
    saved_fresh = dict(_BELT_FRESH_GENERATIONS)
    saved_runs = dict(_BELT_GENERATION_RUNS)
    _TRIAL_CELLS.clear()
    _BELT_FRESH_GENERATIONS.clear()
    _BELT_GENERATION_RUNS.clear()
    try:
        with pytest.raises(AssertionError, match="X1 floor") as raised:
            # The REAL axis test, not a reimplementation: its belt read,
            # its swap, and its both-generations floor are what is under
            # test. Parametrize args are plain function arguments here.
            test_axis_trials_complete_all_four_axes(
                tmp_path, "non_capture", "buffered"
            )
        assert "x1_ms" in str(raised.value), str(raised.value)
        # The belt really swapped: the fresh generation was certified for
        # the key (a band breach was absorbed), so the red came through
        # the swapped verdict, not from a gen-1-only read.
        assert _BELT_GENERATION_RUNS.get(("non_capture", "buffered"), 0) == 1, (
            _BELT_GENERATION_RUNS
        )
    finally:
        _TRIAL_CELLS.clear()
        _TRIAL_CELLS.update(saved_cells)
        _BELT_FRESH_GENERATIONS.clear()
        _BELT_FRESH_GENERATIONS.update(saved_fresh)
        _BELT_GENERATION_RUNS.clear()
        _BELT_GENERATION_RUNS.update(saved_runs)


def test_belt_swap_pace_allocation_survives_a_pre_acquisition_discard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #241 slice 4, AR-1's green arm: the belt-swap pin's designed
    ladder allocation must survive one infrastructure retry that discards
    its rig BEFORE the acquisition — the merge-run red (run 36867869659)
    was this shape: the discarded rig consumed a poisoning slot, gen-1
    drew floor-only, the belt correctly certified nothing, and the floor
    audit reded through the pin's own swap post-condition on an empty
    map. With the pace hook indexing by PACED order, the same injected
    discard changes nothing: a pre-acquisition discard never paces, so
    gen-1's measured five draw the designed ladder, the 1.9-paced trial
    breaches the upper band, the belt certifies exactly one fresh
    generation, and gen-1's floor red lands through the swapped verdict.

    Mutation-RED at build (AR-1): with the hook reverted to
    construction-order indexing under the same injected discard, the 0.55
    slot burns on the discarded rig, gen-1 draws floor-only, no designed
    floor red lands, and this arm reds (DID NOT RAISE) — the pin
    silently exercising nothing, the vacuous twin of the observed red.
    The injection is a first-call drain_until_quiet refusal — the trial
    rhythm's first post-construction step, before any pacing."""
    ladder = (0.55, 1.0, 1.9, 0.75, 1.45)
    constructions: list[ARigAdapter] = []
    paced: list[ARigAdapter] = []
    discarded: list[ARigAdapter] = []
    original_init = ARigAdapter.__init__

    def counting_init(self: ARigAdapter) -> None:
        original_init(self)
        constructions.append(self)

    monkeypatch.setattr(ARigAdapter, "__init__", counting_init)
    original_pace = ARigAdapter._pace

    async def pace_ordered_scatter(self: ARigAdapter, total_ms: float) -> None:
        if self not in paced:
            paced.append(self)
        index = paced.index(self)
        if index < len(ladder):
            await original_pace(self, total_ms * ladder[index])
        else:
            await original_pace(self, total_ms)

    monkeypatch.setattr(ARigAdapter, "_pace", pace_ordered_scatter)
    original_drain = ContinuityRig.drain_until_quiet

    def discard_first_drain(self: ContinuityRig, **kwargs: Any) -> None:
        if not discarded:
            discarded.append(self.adapter_a)
            raise TrialInfrastructureError(
                "injected pre-acquisition discard (AR-1 arm)",
                site="pre-flight-staleness",
            )
        return original_drain(self, **kwargs)

    monkeypatch.setattr(ContinuityRig, "drain_until_quiet", discard_first_drain)
    saved_cells = dict(_TRIAL_CELLS)
    saved_fresh = dict(_BELT_FRESH_GENERATIONS)
    saved_runs = dict(_BELT_GENERATION_RUNS)
    _TRIAL_CELLS.clear()
    _BELT_FRESH_GENERATIONS.clear()
    _BELT_GENERATION_RUNS.clear()
    try:
        with pytest.raises(AssertionError, match="X1 floor") as raises:
            test_axis_trials_complete_all_four_axes(
                tmp_path, "non_capture", "buffered"
            )
        assert "x1_ms" in str(raises.value), str(raises.value)
        # The discard fired exactly once and consumed a construction...
        assert len(discarded) == 1, (len(discarded), len(constructions), len(paced))
        # ...PRE-acquisition: it never paced, so it consumed no ladder slot.
        assert all(a not in paced for a in discarded), (
            len(paced),
            len(constructions),
        )
        # (A count guard here false-reds on a NATURAL pre-acquisition
        # discard: constructions=12, paced=10, recorded=1 reds 10==11
        # with the mechanism all-green — refute A-F1/C-F1 dropped the
        # bare-arithmetic form; a derived never-paced count is a
        # tautology, so the kept guards are the membership, the
        # recorded-discard count, and the belt-map post-condition.)
        # The belt really swapped: a band breach was absorbed for the key,
        # so the floor red came through the swapped verdict.
        assert _BELT_GENERATION_RUNS.get(("non_capture", "buffered"), 0) == 1, (
            _BELT_GENERATION_RUNS
        )
    finally:
        _TRIAL_CELLS.clear()
        _TRIAL_CELLS.update(saved_cells)
        _BELT_FRESH_GENERATIONS.clear()
        _BELT_FRESH_GENERATIONS.update(saved_fresh)
        _BELT_GENERATION_RUNS.clear()
        _BELT_GENERATION_RUNS.update(saved_runs)


def test_trial_log_written_with_provenance(tmp_path: Path) -> None:
    """Check 3's artifact half: the measured cells emit the consolidated
    trial log under the trial dir — the future measurement record quotes
    from this file, never from hand transcription.

    The vacuity guard: this test enumerates the five cells ITSELF (the
    module-level cache makes that a no-op after the measurement tests) and
    asserts the record set is non-empty — the old shape, which read only
    the cache, passed with zero rows under ``-k trial_log``, proving
    nothing. Trial-log honesty: a short-T CONTROL trial never carries
    ``t_acq_controls=True`` — it IS control (i)'s evidence (its acquisition
    fails by construction at ``SHORT_T_MS``), not a T_acq_min dispatch
    whose controls were asserted; stamping it True would let the
    classifier's FIRE series count failed acquisitions as
    controls-asserted trials."""
    cells = [
        (arm, device_class)
        for arm in ("capture", "non_capture", "control")
        for device_class in ("buffered", "unbuffered")
        if not (arm == "control" and device_class == "unbuffered")
    ]
    records: list[TrialRecord] = []
    for arm, device_class in cells:
        for trial in _cell(tmp_path, arm, device_class):
            parameterization: dict[str, Any] = {
                "fixture": "continuity-rig",
                "arm": arm,
                "device_class": device_class,
                "t_acq_min_ms": T_ACQ_MIN_MS,
                "poll_ms": POLL_MS,
                "frame_period_ms": FRAME_PERIOD_MS,
                "max_age_ms": MAX_AGE_MS,
                "dispatch_duration_ms": trial["dispatch_duration_ms"],
                "onset_to_observation_ms": trial["onset_to_observation_ms"],
                "observation_to_action_ms": trial["observation_to_action_ms"],
                "observation_to_enter_call_ms": trial["observation_to_enter_call_ms"],
                "enter_call_to_action_ms": trial["enter_call_to_action_ms"],
            }
            if arm == "control":
                parameterization["t_acq_note"] = (
                    "short-T control trial: acquisition fails by construction "
                    "at SHORT_T_MS — control (i)'s evidence, not a T_acq_min "
                    "dispatch; dispatched via the READ verb (the capture "
                    "arm's own short-T variant is not run separately — the "
                    "read-verb control pins the pacing floor for both arms' "
                    "T_acq_min class)"
                )
            records.append(
                TrialRecord(
                    trial=trial["trial"],
                    arm=arm,
                    device_class=device_class,
                    axes_ms={
                        "X1": trial["x1_ms"],
                        "X2": trial["x2_ms"],
                        "X3": trial["x3_ms"],
                        "X4": trial["x4_ms"],
                    },
                    # The T_acq consistency controls are asserted for the
                    # MEASURED arms only: short-T failure (the control cell)
                    # AND split refusal (the capture-window test below; the
                    # scalar arm's split refusal is definitional).
                    t_acq_controls=arm != "control",
                    tightening_admitted=False,
                    splitting_admitted=False,
                    unsplittable_class=True,
                    parameterization=parameterization,
                    command=(
                        "pytest tests/integration/test_cross_instance_continuity.py"
                        f" -k {arm} and {device_class}"
                    ),
                )
            )
    assert records, "the trial log emitted zero rows — the cells never ran"
    path = tmp_path / "continuity-trial-log.json"
    log = write_trial_log(path, records)
    assert path.is_file()
    written = json.loads(path.read_text())
    assert written == log
    assert len(log["rows"]) >= len(records) * 4
    # The control rows carry the honest stamp and its provenance note.
    control_rows = [row for row in log["rows"] if row["arm"] == "control"]
    assert control_rows, "no control rows in the emitted log"
    assert all(row["value"] is False for row in control_rows if row.get("figure")), (
        "a short-T control trial claimed t_acq_controls=True"
    )
    assert all(
        "t_acq_note" in row["parameterization"] for row in control_rows
    ), "the control provenance nuance is missing from the log"
    print(f"\ntrial log: {path}")


def test_split_refusal_capture_window_one_shot(tmp_path: Path) -> None:
    """§2.5 control (ii), capture arm: the fixture's device model makes the
    acquisition one-shot per window — the second half-dispatch is
    device-rejected (the manifests cannot cover the window). The scalar
    arm's split refusal is definitional (a single conversion is not
    splittable) and rides the trial log as a definition row, not a fake
    assertion."""
    rig = ContinuityRig(tmp_path / "split.db")
    try:
        first = rig.bridge_a.dispatch(
            rig.capture_request("cap.split-a.h1"), deadline_ns=rig.deadline_ns(2000)
        )
        assert first.status is OperationStatus.OK, first.error
        second = rig.bridge_a.dispatch(
            rig.capture_request("cap.split-a.h2"), deadline_ns=rig.deadline_ns(2000)
        )
        assert second.status is OperationStatus.ERROR, second
        assert second.error is not None and "already consumed" in second.error.message
        # The session survived the clean rejection.
        follow = rig.bridge_a.dispatch(
            OperationRequest.read("op-follow", parameter="temp"),
            deadline_ns=rig.deadline_ns(2000),
        )
        assert follow.status is OperationStatus.OK, follow.error
    finally:
        rig.teardown_and_close()


def test_eight_separation_bound_share_vs_movable_share(tmp_path: Path) -> None:
    """§2.6 — the structural pair, run DURING A's dispatch from helper
    threads (the quantity-3 thread shape; helper threads appear ONLY in
    these controls — the axis trials are single-threaded like the run
    path): a bridge-level read on B's bridge succeeds promptly (B's
    per-instance lock is free — the movable share's existence proof),
    while a read on A's bridge blocks until the dispatch ends (§8
    per-instance serialization — the bound share's proof). Together they
    pin the #159 §5 claim the single-source fixture could not separate:
    the blackout is the single engine thread, not the device topology."""
    rig = ContinuityRig(tmp_path / "separation.db")
    try:
        rig.settle(100)
        outcomes: dict[str, Any] = {}

        def dispatch_a() -> None:
            outcomes["a"] = rig.bridge_a.dispatch(
                OperationRequest.read("op-a-slow", parameter="acq_scalar"),
                deadline_ns=rig.deadline_ns(2000),
            )

        def read_bridge(bridge: OTDPBridge, key: str, parameter: str) -> None:
            start = time.monotonic()
            result = bridge.dispatch(
                OperationRequest.read(f"op-helper-{key}", parameter=parameter),
                deadline_ns=rig.deadline_ns(2000),
            )
            outcomes[key] = {"elapsed_ms": (time.monotonic() - start) * 1000, "result": result}

        rig.adapter_a.acq_entered.clear()
        main = threading.Thread(target=dispatch_a)
        main.start()
        assert rig.adapter_a.acq_entered.wait(timeout=5), "A's dispatch never entered"
        on_b = threading.Thread(target=read_bridge, args=(rig.bridge_b, "b", "level"))
        on_a = threading.Thread(target=read_bridge, args=(rig.bridge_a, "a_block", "temp"))
        on_b.start()
        on_a.start()
        main.join(timeout=10)
        on_b.join(timeout=10)
        on_a.join(timeout=10)
        assert outcomes["a"].status is OperationStatus.OK, outcomes["a"].error
        b_out = outcomes["b"]
        a_out = outcomes["a_block"]
        print(
            f"\n§8 pair: B-lock-free read {b_out['elapsed_ms']:.1f} ms; "
            f"A-locked read {a_out['elapsed_ms']:.1f} ms"
        )
        # The movable share: B's read lands while A's dispatch is in flight.
        assert b_out["result"].status is OperationStatus.OK, b_out["result"].error
        assert b_out["elapsed_ms"] <= 100, b_out
        # The bound share: A's read waited out (most of) the dispatch.
        assert a_out["result"].status is OperationStatus.OK, a_out["result"].error
        assert a_out["elapsed_ms"] >= 100, a_out
    finally:
        rig.teardown_and_close()


def test_store_connection_census_two_instances_one_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check 4: monkeypatch-counted ``Store.open`` across a full
    two-instance trial — zero additional opens beyond the rig's own one,
    and one opening thread (the two-instance baseline the reopen must
    hold; the census AS a host build gate rides the reopen)."""
    opened: list[int] = []
    original_open = Store.open

    def counting_open(path: Any, **kwargs: Any) -> Store:
        opened.append(threading.get_ident())
        return original_open(path, **kwargs)

    monkeypatch.setattr(Store, "open", staticmethod(counting_open))
    trial = run_trial(tmp_path, arm="non_capture", device_class="buffered", trial_index=99)
    assert trial["x1_ms"] > 0
    # One open per rig construction (a retried trial constructs a fresh
    # rig — the retry count is in the outcome), and ONE opening thread:
    # two instances, one store, no worker-thread re-open.
    assert opened and set(opened) == {threading.get_ident()}, (
        f"census: {len(opened)} Store.open calls on threads {opened}"
    )
    assert len(opened) == 1 + trial["retries"], (len(opened), trial["retries"])


def test_divergent_wall_moves_x2_not_x1(tmp_path: Path) -> None:
    """Check 5: the monitor wall stretched 10x moves X2's host-age >= 5x
    the baseline while X1's monotonic gap stays within +-50 ms (clock-domain
    contamination would show as X1 stretching too). The probe runs the
    same buffered non-capture dispatch rhythm under a no-condition policy
    (the stretched wall inflates every host age past any dispatch-scale
    bound — tripping on THAT would be a fixture artifact, not the hazard)."""
    baseline = _cell(tmp_path, "non_capture", "buffered")
    probe = run_trial(
        tmp_path,
        arm="non_capture",
        device_class="buffered",
        trial_index=1,
        monitor_wall_rate=10.0,
        no_trip=True,
    )
    baseline_x2 = _median([t["x2_ms"] for t in baseline])
    baseline_x1 = _median([t["x1_ms"] for t in baseline])
    print(
        f"\nwall divergence: X2 {probe['x2_ms']:.1f} vs baseline {baseline_x2:.1f} "
        f"({probe['x2_ms'] / baseline_x2:.1f}x); X1 {probe['x1_ms']:.1f} vs "
        f"{baseline_x1:.1f}"
    )
    assert probe["x2_ms"] >= 5 * baseline_x2, probe
    assert abs(probe["x1_ms"] - baseline_x1) <= 50, probe


# --- check 2 (boundary half): the max_age_ms inclusive pin + the aged-reading deficiency


class _FixedAgePlugin:
    """A minimal DevicePlugin serving one Reading whose observed_at is a
    fixed wall instant minus a scripted age — the direct
    ``read_signal_values`` table's input."""

    def __init__(self, *, age_ms: int, wall_epoch: datetime) -> None:
        self._age_ms = age_ms
        self._wall_epoch = wall_epoch

    @property
    def simulation(self) -> Any:
        return SimulationInfo(True, "Synthetic")

    def plugin_open(self, services: Any) -> None:
        return None

    def plugin_close(self) -> None:
        return None

    def dispatch(self, request: OperationRequest, *, deadline_ns: int) -> OperationResult:
        from datetime import timedelta

        from benchweave.host.types import Quality, Reading, ReadingSource

        observed = (
            self._wall_epoch - timedelta(milliseconds=self._age_ms)
        ).isoformat()
        return OperationResult.ok(
            request.operation_id,
            request.verb,
            Reading(
                parameter=str(request.arguments["parameter"]),
                value=1.0,
                unit="V",
                observed_at=observed,
                age_ms=0,
                quality=Quality.VALID,
                source=ReadingSource.DEVICE,
            ),
        )


def test_check2_boundary_ages_inclusive_and_aged_reading_deficiency() -> None:
    """Check 2's boundary half. (1) The ``max_age_ms`` boundary is
    INCLUSIVE-valid today: ages M-1 / M / M+1 read valid / valid / invalid
    — the -1/0/+1 pin #159 §2 wrote for the reopen. (2) The
    documented-deficiency pin (A06's hazard, pinned not fixed — D1 owns
    the src/ change): an aged-in-bound ``SignalValue`` yields ZERO
    violations from a numeric condition, because ``evaluate_conditions``
    reads ``age_ms`` only in the product-skew path. THE REOPEN FLIP: when
    D1's aged-reading representation lands (no reading evaluates as clean
    without its age), the second assertion below FAILS by design — that is
    the watched flip, not a regression. No ``src/`` byte moves here."""
    wall_epoch = datetime(2026, 9, 26, tzinfo=UTC)
    wall_iso = wall_epoch.isoformat().replace("+00:00", "Z")
    bench = {
        "signals": [
            {
                "id": SIG_B,
                "source": {"device_id": DEVICE_B, "kind": "parameter", "parameter": "level"},
                "max_age_ms": MAX_AGE_MS,
                "absolute_error": 0.05,
            }
        ]
    }
    boundary_ages = (
        (MAX_AGE_MS - 1, True),
        (MAX_AGE_MS, True),
        (MAX_AGE_MS + 1, False),
    )
    for age_ms, expected_valid in boundary_ages:
        snapshot = read_signal_values(
            {DEVICE_B: _FixedAgePlugin(age_ms=age_ms, wall_epoch=wall_epoch)},
            bench,
            deadline_ns=time.monotonic_ns() + 1_000_000_000,
            wall_now=wall_iso,
        )
        assert snapshot[SIG_B].valid is expected_valid, (age_ms, snapshot[SIG_B])

    aged_in_bound = SignalValue(
        signal_id=SIG_B, value=1.0, unit="V", age_ms=MAX_AGE_MS - 1,
        valid=True, absolute_error=0.05,
    )
    # Today's truth, pinned: an aged-in-bound reading evaluates CLEAN
    # against a numeric condition (the evaluator consults `valid` alone).
    assert evaluate_conditions(POLICY, {SIG_B: aged_in_bound}) == []
    # The invalid path does report today (the fail-safe direction works):
    stale = SignalValue(
        signal_id=SIG_B, value=1.0, unit="V", age_ms=MAX_AGE_MS + 1,
        valid=False, absolute_error=0.05,
    )
    violations = evaluate_conditions(POLICY, {SIG_B: stale})
    assert violations and violations[0].startswith("rig-b-level-bounds: signal_invalid")


# --- #217 unblock: the range gate's outlier tolerance + the priming marker ----------


def test_priming_serve_failure_retries_as_the_infrastructure_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#217 unblock, ADAPTED to #159's F4 doctrine: the priming serve
    failure ('a bench signal failed to serve at priming', the second of
    PR #245's two CI reds) is construction-time host starvation — the site
    raises TrialInfrastructureError (the pre-flight staleness class:
    pre-dispatch by intent) and the type-keyed matcher retries it on a
    fresh trial; the wording classifies nothing (the message matcher this
    replaced is deleted — a plain AssertionError carrying the same wording
    raises straight through, pinned by #159's legacy-wording test)."""
    calls: list[int] = []

    def flaky_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["trial_index"])
        if len(calls) == 1:
            raise TrialInfrastructureError(
                "a bench signal failed to serve at priming",
                site="priming-validity",
            )
        return {"arm": kwargs["arm"], "trial": kwargs["trial_index"]}

    monkeypatch.setitem(globals(), "_run_trial_once", flaky_once)
    outcome = run_trial(
        tmp_path, arm="non_capture", device_class="buffered", trial_index=7
    )
    assert outcome["retries"] == 1
    assert calls == [70, 71]


def test_range_gate_tolerance_both_directions() -> None:
    """The gate's outlier tolerance, pinned from the CI evidence (PR #245,
    two red lanes): a replayed CONTENDED shape — one trial spiked ~2x among
    tight trials ([78.0, 78.1, 77.9, 150.9, 77.6], raw range 73.3 ms) — is
    a scheduler stall, not loose pacing, and must NOT read UNDERPOWERED;
    a SYSTEMATICALLY-SPREAD fixture (every trial scattered, no single
    outlier) and a double-spiked shape must STILL read UNDERPOWERED —
    §5's clause keeps its teeth (the still-catches direction)."""
    bound = 0.25 * _RANGE_GATE_DENOMINATOR_MS

    contended = [78.0, 78.1, 77.9, 150.9, 77.6]
    assert _underpowered_range_ms(contended) <= bound, (
        "the contended replay must not read UNDERPOWERED"
    )

    for spread in (
        [70.0, 95.5, 121.0, 146.5, 172.0],  # systematic: every trial scattered
        [78.0, 78.1, 150.9, 151.0, 77.6],  # two spikes: one trim is not enough
    ):
        assert _underpowered_range_ms(spread) > bound, (
            f"a systematically-spread fixture must still fire: {spread}"
        )


# --- the retry matcher's discrimination (#159 owner call 1, review finding F4) ------


@pytest.mark.parametrize(
    "wording",
    [
        "A fresh opened bridge is required",
        "pre-dispatch staleness: sig-rig-b age 999 ms",
        "protection trip: rig-b-level-bounds: signal_invalid: sig-rig-b",
    ],
)
def test_plain_assertion_with_legacy_wording_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wording: str
) -> None:
    """The retry matcher must key on an explicit structural marker, never
    on message text (review finding F4 on PR #236): a PLAIN
    ``AssertionError`` whose message merely quotes one of the historical
    retryable wordings raises straight through on the first attempt — one
    ``_run_trial_once`` call, no retry."""
    calls: list[int] = []

    def failing_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["trial_index"])
        raise AssertionError(wording)

    monkeypatch.setitem(globals(), "_run_trial_once", failing_once)
    with pytest.raises(AssertionError) as raised:
        run_trial(tmp_path, arm="non_capture", device_class="buffered", trial_index=3)
    assert len(calls) == 1, (
        f"a plain AssertionError was retried {len(calls)} time(s) — the "
        "matcher keyed on message text, not the structural marker"
    )
    assert type(raised.value) is AssertionError


def test_infrastructure_marker_retries_on_a_fresh_trial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F4, direction (a): a marker-carrying failure is retried on a fresh
    trial index and the outcome records the retry count."""
    calls: list[int] = []

    def flaky_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["trial_index"])
        if len(calls) == 1:
            raise TrialInfrastructureError(
                "pre-dispatch staleness: synthetic", site="pre-flight-staleness"
            )
        return {"arm": kwargs["arm"], "trial": kwargs["trial_index"]}

    monkeypatch.setitem(globals(), "_run_trial_once", flaky_once)
    outcome = run_trial(
        tmp_path, arm="non_capture", device_class="buffered", trial_index=7
    )
    assert outcome["retries"] == 1
    # trial_index * 10 + attempt: the retry re-ran as a FRESH trial index.
    assert calls == [70, 71]


def test_infrastructure_marker_exhausts_at_two_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cap: a chronically starved host fails after exactly three
    attempts, and the marker stays an ``AssertionError`` subclass so the
    exhausted trial still fails as an assertion (the axis trials'
    starved-host guard keeps its meaning). The exhausted exception carries
    its own site label — the LAST attempt's site travels with the raise,
    not only with a successful outcome."""
    calls: list[int] = []

    def always_failing_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["trial_index"])
        raise TrialInfrastructureError("starved", site="synthetic")

    monkeypatch.setitem(globals(), "_run_trial_once", always_failing_once)
    with pytest.raises(TrialInfrastructureError) as raised:
        run_trial(tmp_path, arm="control", device_class="unbuffered", trial_index=1)
    assert len(calls) == 3  # the attempt plus at most two retries
    assert isinstance(raised.value, AssertionError)
    assert raised.value.site == "synthetic"


def test_exhaustion_renders_the_full_retry_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wave-1 fold, critic F1: at exhaustion the re-raise carries the
    WHOLE site sequence rendered into the message — the record's risk-1
    falsifier (a lane log showing drain-cap repeated to exhaustion)
    requires the composition where pytest shows it, and pre-fold the
    re-raise dropped it (only the LAST attempt's site travelled). The
    sequence is deliberately MIXED (drain-cap, priming-validity,
    drain-cap): a homogeneous sequence cannot distinguish the rendered
    composition from the last site's own label."""
    calls: list[int] = []
    sequence = ["drain-cap", "priming-validity", "drain-cap"]

    def failing_mixed_sites(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["trial_index"])
        raise TrialInfrastructureError("starved", site=sequence[len(calls) - 1])

    monkeypatch.setitem(globals(), "_run_trial_once", failing_mixed_sites)
    with pytest.raises(TrialInfrastructureError) as raised:
        run_trial(tmp_path, arm="control", device_class="unbuffered", trial_index=1)
    assert len(calls) == 3
    assert raised.value.site == "drain-cap"  # the LAST attempt's own site
    assert "drain-cap -> priming-validity -> drain-cap" in str(raised.value), (
        str(raised.value)
    )


def test_retry_composition_records_each_failed_attempts_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fold (MEDIUM, critic F3): the retry budget's evidence base.
    A bare ``retries`` int discards the intermediate sites — exhaustion
    reports only the LAST attempt's site, so a mixed-sequence trial (priming
    starvation, then pre-flight staleness, then success) was indistinguishable
    from a single-site retry, and the design's lane-sits-at-2 signal was
    unobservable. Pin: ``outcome["retry_sites"]`` carries each failed
    attempt's site IN ORDER across a forced mixed-site sequence."""
    calls: list[int] = []

    def mixed_sites_once(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["trial_index"])
        if len(calls) == 1:
            raise TrialInfrastructureError(
                "priming starvation: synthetic", site="priming-validity"
            )
        if len(calls) == 2:
            raise TrialInfrastructureError(
                "pre-dispatch staleness: synthetic", site="pre-flight-staleness"
            )
        return {"arm": kwargs["arm"], "trial": kwargs["trial_index"]}

    monkeypatch.setitem(globals(), "_run_trial_once", mixed_sites_once)
    outcome = run_trial(
        tmp_path, arm="non_capture", device_class="buffered", trial_index=9
    )
    assert outcome["retries"] == 2, outcome["retries"]
    assert outcome["retry_sites"] == ["priming-validity", "pre-flight-staleness"]
    assert calls == [90, 91, 92]


# --- the priming-starvation classification (#241 slice 1) ---------------------------


def _install_priming_starvation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    every_construction: bool,
    starve_from_read: int = 2,
) -> list[ContinuityRig]:
    """Force the over-aged priming B-read (#241 slice 1, design §2.1): B's
    FIRST tick read serves fresh (the healthy fixture — a stale first read
    trips the block at the pre-tick, the read-#1 presentation the review
    fold classifies as retryable infrastructure), and every read AFTER it
    lands ten seconds before the open reference — far past the 300 ms
    ``max_age_ms`` — so the post-dispatch tick's retained snapshot is the
    one that goes invalid. (The observed CI failure reached the same
    assert by another driver — the divergent-wall probe's rate-10
    injection inflating every host age on a condition-free config, which
    the wall-rate guard excludes from the classification; this helper
    forces the aged-read presentations the classification itself routes
    to retry.) ``starve_from_read`` moves the threshold: 2 (the
    default) starves reads two onward — the post-tick presentation; 1
    starves every read including the first — the pre-tick block-refusal
    presentation. The first construction's adapter only, or every
    construction's in the exhaustion shape. Returns the rigs (including
    any that raised partway through construction) for the caller's
    failure belt."""
    rigs: list[ContinuityRig] = []
    adapters: list[BRigAdapter] = []
    reads: dict[int, int] = {}
    original_init = ContinuityRig.__init__

    def counting_init(self: ContinuityRig, db_path: Path, **kwargs: Any) -> None:
        rigs.append(self)
        original_init(self, db_path, **kwargs)

    monkeypatch.setattr(ContinuityRig, "__init__", counting_init)
    original_b_init = BRigAdapter.__init__

    def counting_b_init(self: BRigAdapter, *, buffered: bool) -> None:
        original_b_init(self, buffered=buffered)
        adapters.append(self)

    monkeypatch.setattr(BRigAdapter, "__init__", counting_b_init)
    original_wall_at = BRigAdapter._wall_at

    def starved_wall_at(self: BRigAdapter, mono_ns: int) -> str:
        starved = adapters if every_construction else adapters[:1]
        if any(self is adapter for adapter in starved):
            seen = reads.get(id(self), 0) + 1
            reads[id(self)] = seen
            if seen >= starve_from_read:
                stamp = datetime.fromtimestamp(self._ref_epoch - 10.0, tz=UTC)
                return stamp.isoformat().replace("+00:00", "Z")
        return original_wall_at(self, mono_ns)

    monkeypatch.setattr(BRigAdapter, "_wall_at", starved_wall_at)
    return rigs


def _close_partially_constructed(rigs: list[ContinuityRig]) -> None:
    """The failure belt for rigs whose construction raised before
    ``_run_trial_once``'s own belt could see them — the module's belt shape
    (the stream host's close sweeps every constructed bridge; sqlite closes
    are idempotent), best-effort over whatever the failed construction
    managed to build."""
    for rig in rigs:
        stream_host = getattr(rig, "stream_host", None)
        if stream_host is not None:
            with suppress(Exception):
                stream_host.close()
        store = getattr(rig, "store", None)
        if store is not None:
            with suppress(Exception):
                store.close()


def test_failed_construction_leaves_no_unclosed_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fold (LOW, critic F4 + NIT, adversary F3): a construction-time
    raise escapes ``_run_trial_once``'s failure belt — the rig is built
    BEFORE the try whose finally closes the stream host and store, so a
    starved construction leaked its sqlite handle and bridge objects into
    the next attempt's timing envelope (the pins carried their own belt;
    the module machinery had none). Machine check, census style: across an
    exhausted construction-starved trial, every ``Store.open`` is matched
    by a ``Store.close`` — zero unclosed stores."""
    opened: list[Store] = []
    closed: list[Store] = []
    original_open = Store.open
    original_close = Store.close

    def counting_open(path: Any, **kwargs: Any) -> Store:
        store = original_open(path, **kwargs)
        opened.append(store)
        return store

    def counting_close(self: Store) -> None:
        closed.append(self)
        original_close(self)

    monkeypatch.setattr(Store, "open", staticmethod(counting_open))
    monkeypatch.setattr(Store, "close", counting_close)
    rigs = _install_priming_starvation(monkeypatch, every_construction=True)
    try:
        with pytest.raises(TrialInfrastructureError):
            run_trial(
                tmp_path, arm="non_capture", device_class="buffered", trial_index=6
            )
        assert len(rigs) == 3
        assert opened, "the census saw no Store.open"
        unclosed = [store for store in opened if store not in closed]
        assert not unclosed, (
            f"{len(unclosed)} of {len(opened)} opened store(s) left unclosed "
            "by failed constructions"
        )
    finally:
        # Session hygiene for the RED shape: pre-fix the module leaks them,
        # and this test must not leak them into the session too.
        _close_partially_constructed(rigs)


def test_priming_signal_starvation_is_infrastructure_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #241 slice 1, direction (a): construction-time priming
    starvation is infrastructure, so it retries on a fresh rig. The C14
    priming block's signal-validity check is a ``TrialInfrastructureError``
    site (construction itself is an un-polled window — ``drain_until_quiet``'s
    own docstring names it — so sig-rig-b's first read can arrive aged past
    ``max_age_ms`` on a loaded host, the observed CI failure): the first
    construction's starved priming read must retry, not fail the trial, and
    the second, unpatched construction must complete it. De-clocked by
    slice 3 (design §1.1): the pin asserts the classification fact —
    ``retries >= 1`` and ``"priming-validity" in retry_sites`` — not the
    exact attempt count, which host load legitimately moves (an unpatched
    attempt can hit its own real starvation site and the budget absorbs
    it; the drain-cap pin's three CI reds were this exact shape)."""
    rigs = _install_priming_starvation(monkeypatch, every_construction=False)
    try:
        outcome = run_trial(
            tmp_path, arm="non_capture", device_class="buffered", trial_index=7
        )
        assert outcome["retries"] >= 1, outcome["retries"]
        assert "priming-validity" in outcome["retry_sites"], outcome["retry_sites"]
    finally:
        _close_partially_constructed(rigs)


def test_priming_signal_starvation_exhausts_at_two_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cap at the new site: a host so starved that EVERY construction's
    priming read is over-aged exhausts the budget — three attempts — and the
    exhausted failure is still an ``AssertionError`` (the existing
    exhaustion-pin shape, carried by the real construction path rather than
    a patched ``_run_trial_once``)."""
    rigs = _install_priming_starvation(monkeypatch, every_construction=True)
    try:
        with pytest.raises(TrialInfrastructureError) as raised:
            run_trial(
                tmp_path, arm="non_capture", device_class="buffered", trial_index=1
            )
        assert len(rigs) == 3  # the attempt plus at most two retries
        assert isinstance(raised.value, AssertionError)
    finally:
        _close_partially_constructed(rigs)


def test_priming_read1_starvation_routes_the_block_refusal_to_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fold (HIGH+MEDIUM converged): read-#1 starvation — the
    heaviest presentation, the exact slice-1 condition — never reaches the
    validity assert. The wrapper's pre-dispatch tick reads the already-aged
    signal, the fail-safe latches ``signal_invalid``, and the monitor
    REFUSES the priming dispatch at the door (``primed.status`` not OK).
    That block-refusal is the same starvation class as the validity
    presentation — the discriminant is the monitor's own ``blocked`` latch
    plus the freshness kind (``_freshness_trip_block``) — so it must retry
    on a fresh rig, not die on the degenerate-wiring assert: the first
    construction's starved reads retry, the second, unpatched construction
    completes. De-clocked by slice 3 (design §1.1): the pin asserts
    ``retries >= 1`` plus the SITE membership —
    ``"priming-block-refusal" in retry_sites`` — the classification fact,
    not the attempt bookkeeping host load moves."""
    rigs = _install_priming_starvation(
        monkeypatch, every_construction=False, starve_from_read=1
    )
    try:
        outcome = run_trial(
            tmp_path, arm="non_capture", device_class="buffered", trial_index=8
        )
        assert outcome["retries"] >= 1, outcome["retries"]
        assert "priming-block-refusal" in outcome["retry_sites"], (
            outcome["retry_sites"]
        )
    finally:
        _close_partially_constructed(rigs)


def test_priming_read1_starvation_exhaustion_is_the_starvation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read-#1 exhaustion arm: EVERY construction's every read aged
    fails every priming dispatch at the door, and the exhausted failure is
    the starvation marker itself — never the degenerate-wiring assert
    (which would misattribute a starved host to broken wiring)."""
    rigs = _install_priming_starvation(
        monkeypatch, every_construction=True, starve_from_read=1
    )
    try:
        with pytest.raises(TrialInfrastructureError) as raised:
            run_trial(
                tmp_path, arm="non_capture", device_class="buffered", trial_index=9
            )
        assert len(rigs) == 3
        assert "monitoring fixture degenerate" not in str(raised.value)
    finally:
        _close_partially_constructed(rigs)


def test_divergent_wall_priming_age_never_reads_as_starvation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fold (MEDIUM, critic F2): under the divergent-wall probe's
    own injection the priming classification is meaningless and its retry
    structurally useless — every construction re-injects the stretched
    wall, and the inflated age (measured ~9x construction elapsed at
    rate 10; the critic's crossing estimate sits inside the lane's target
    regime) would red with a FALSE construction-time starvation
    attribution, misdirecting slice 2. Pin: the probe variant (10x wall,
    no-condition policy) with every construction's post-tick priming read
    forced over-aged COMPLETES on the first construction — no
    TrialInfrastructureError, retries == 0 — the same guard the pre-flight
    staleness check gives itself under no_trip."""
    rigs = _install_priming_starvation(monkeypatch, every_construction=True)
    try:
        outcome = run_trial(
            tmp_path,
            arm="non_capture",
            device_class="buffered",
            trial_index=3,
            monitor_wall_rate=10.0,
            no_trip=True,
        )
        assert outcome["retries"] == 0, outcome["retries"]
    finally:
        _close_partially_constructed(rigs)


def test_partial_probe_pre_flight_starvation_classification_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fold (LOW, reviewer finding 4): the probe-wall exemption had
    two predicates — the priming arms keyed on ``monitor_wall_rate == 1.0``,
    the pre-flight staleness check on ``no_trip`` — and a partial probe
    (stretched wall, live policy) fell in the gap: the pre-flight check
    could classify its own wall-inflated age as host starvation and burn
    the whole retry budget on rigs that re-inject the same wall. One
    shared predicate (``_probe_wall_injection``: rate != 1.0 OR no_trip)
    covers both probe signals at all three classification sites. Pin: the
    partial probe's terminal failure never carries the pre-flight
    staleness attribution, and the truth table pins the one classify
    state (a real wall at a live policy). The threshold is calibrated:
    construction's own reads (initial, pre-tick, subscribe) stay fresh so
    construction completes, and the injected age lands exactly at the
    pre-flight read — pre-fix it reads as starvation (age ~10.5 s against
    the 300 ms bound) and exhausts the budget."""
    rigs = _install_priming_starvation(
        monkeypatch, every_construction=True, starve_from_read=4
    )
    try:
        with pytest.raises(AssertionError) as raised:
            run_trial(
                tmp_path,
                arm="non_capture",
                device_class="buffered",
                trial_index=11,
                monitor_wall_rate=10.0,
                no_trip=False,
            )
        assert "pre-dispatch staleness" not in str(raised.value), raised.value
        if isinstance(raised.value, TrialInfrastructureError):
            assert raised.value.site != "pre-flight-staleness", raised.value.site
    finally:
        _close_partially_constructed(rigs)
    assert not _probe_wall_injection(1.0, False)
    assert _probe_wall_injection(10.0, False)
    assert _probe_wall_injection(10.0, True)
    assert _probe_wall_injection(1.0, True)


# --- the drain-cap classification (#241 slice 2) -----------------------------------


def _install_drain_cap_starvation(
    monkeypatch: pytest.MonkeyPatch,
    *,
    every_construction: bool = False,
) -> list[ContinuityRig]:
    """Force the drain-cap presentation (issue #241 slice 2, design §1.1
    — patch shape reworked on mechanism evidence, disclosed in the commit
    message): the FIRST construction's adapter never delivers a frame, so
    the adapter's REAL ``due_count`` grows without bound and
    ``drain_until_quiet``'s quiet guard never sees zero — delivery
    starvation, the sweep's total-starvation subclass ("the backlog GROWS
    through the cap; delivery ~0", frame-due 20–103 at the observed hits,
    ~100 frames at a full 2000 ms spin). The design's letter patched
    ``due_count`` positive instead, but ``next_event`` shares that method
    as its delivery-liveness check, so an always-positive reading makes
    delivery OUTPACE the 20 ms schedule — the receive point races into
    the future and the fixture degrades into a ``drain-poll-door`` death
    inside the spin (measured: both arms failed with site
    ``drain-poll-door`` pre-fix), never reaching the cap. Starving
    delivery instead reproduces the real mechanism with real quantities.
    Construction itself never polls events, so the patched construction
    completes healthy and the rig dies at the trial path's FIRST drain
    call site — nothing downstream (settle, the measured dispatch) runs.
    ``every_construction=True`` starves EVERY construction's adapter
    (wave-1 fold, adversary F2): all three attempts die at their first
    drain, so the trial exhausts its budget entirely at the drain-cap
    site. Returns the rigs (the slice-1 counter shape) for the caller's
    failure belt."""
    rigs: list[ContinuityRig] = []
    adapters: list[BRigAdapter] = []
    original_init = ContinuityRig.__init__

    def counting_init(self: ContinuityRig, db_path: Path, **kwargs: Any) -> None:
        rigs.append(self)
        original_init(self, db_path, **kwargs)

    monkeypatch.setattr(ContinuityRig, "__init__", counting_init)
    original_b_init = BRigAdapter.__init__

    def counting_b_init(self: BRigAdapter, *, buffered: bool) -> None:
        original_b_init(self, buffered=buffered)
        adapters.append(self)

    monkeypatch.setattr(BRigAdapter, "__init__", counting_b_init)
    original_next_event = BRigAdapter.next_event

    async def starved_next_event(
        self: BRigAdapter, subscription_id: str, context: Any
    ) -> dict[str, Any] | None:
        starved = adapters if every_construction else adapters[:1]
        if any(self is adapter for adapter in starved):
            return None  # delivery ~0: the starved-delivery presentation
        return await original_next_event(self, subscription_id, context)

    monkeypatch.setattr(BRigAdapter, "next_event", starved_next_event)
    return rigs


def test_drain_cap_hit_is_infrastructure_at_the_drain_cap_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #241 slice 2, the TYPE arm: the drain cap's raise is a
    ``TrialInfrastructureError`` carrying ``site="drain-cap"`` — matched
    on TYPE and site label, never message text. A short explicit
    ``cap_ms`` spins the REAL loop to its REAL cap (cheap — no full-cap
    burn) with delivery starved on the instance's adapter, so the real
    backlog grows past the quiet floor. Constructed under the no-trip
    probe policy (``_run_trial_once``'s own wiring for ``no_trip``): a
    condition-free monitor cannot latch mid-spin, so the spin stays on
    the pre-trip polling branch regardless of host load. The
    ``isinstance`` pin is the exhaustion-still-reds property at the type
    level: an exhausted drain-cap retry fails the trial as an
    assertion."""
    rig = _construct_rig(
        tmp_path / "drain-cap-type.db",
        device_class="buffered",
        no_trip=True,
        policy=NO_TRIP_POLICY,
    )
    try:

        async def never_delivers(subscription_id: str, context: Any) -> dict[str, Any] | None:
            return None

        monkeypatch.setattr(rig.adapter_b, "next_event", never_delivers)
        with pytest.raises(TrialInfrastructureError) as raised:
            rig.drain_until_quiet(cap_ms=250.0)
        assert type(raised.value) is TrialInfrastructureError
        assert raised.value.site == "drain-cap", raised.value.site
        assert isinstance(raised.value, AssertionError)
    finally:
        _close_partially_constructed([rig])


def test_drain_cap_starvation_retries_on_a_fresh_rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #241 slice 2, the INTEGRATION arm (AR-1), de-clocked by slice
    3 (design §1.1): the trial path's first drain hits the default
    2000 ms cap on the patched construction, the raise rides
    ``run_trial``'s fresh-rig retry, and the unpatched second construction
    completes the trial. The pin asserts the PROPERTY, not the attempt
    bookkeeping — ``retries >= 1`` and ``"drain-cap" in retry_sites`` —
    because under load the UNPATCHED attempt can itself hit a real
    starvation site (pre-flight staleness, a real drain-cap, priming) that
    the retry budget legitimately absorbs (three CI reds, runs
    36452983841/36817483120/36852240046, all ``retries`` 2≠1 with the
    property holding); the machinery's ``retries <= 2`` cap stays pinned
    where it always was, on the axis trials. The membership form is
    airtight unless attempt 0's own construction starves at priming first
    — the residual §7 risk 2 names. Runs the production policy; burns one
    real cap spin (~2 s, disclosed). Site-level exhaustion is pinned next
    door; the site-agnostic machinery at
    ``test_infrastructure_marker_exhausts_at_two_retries``. RED direction
    (AR-2b, shown at build): with the drain-cap raise reverted to a plain
    ``assert`` in place, the refusal propagates out of ``run_trial`` and
    THIS pin reds — the classification is what the membership rides on."""
    rigs = _install_drain_cap_starvation(monkeypatch)
    try:
        outcome = run_trial(
            tmp_path, arm="non_capture", device_class="buffered", trial_index=7
        )
        assert outcome["retries"] >= 1, outcome["retries"]
        assert "drain-cap" in outcome["retry_sites"], outcome["retry_sites"]
    finally:
        _close_partially_constructed(rigs)


def test_drain_cap_starvation_exhausts_at_the_drain_cap_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wave-1 fold, adversary F2: the drain-cap-specific exhaustion arm —
    EVERY construction starved, so all three rigs die at their first
    drain and the trial exhausts its budget entirely at the drain-cap
    site (the site-agnostic budget is pinned at ``synthetic``; this pins
    the real site end-to-end, and its site/count/type asserts are
    regression pins over the committed D1 mechanism — they pass on the
    pre-fold tip). The exhaustion raise renders the homogeneous
    composition (critic F1's mechanism): ``drain-cap`` repeated to
    exhaustion is the record's risk-1 lane log, now real. Burns three
    real cap spins (~7 s; design §7 risk 6's per-attempt arithmetic,
    ×3)."""
    rigs = _install_drain_cap_starvation(monkeypatch, every_construction=True)
    try:
        with pytest.raises(TrialInfrastructureError) as raised:
            run_trial(
                tmp_path, arm="non_capture", device_class="buffered", trial_index=8
            )
        assert len(rigs) == 3, len(rigs)
        assert type(raised.value) is TrialInfrastructureError
        assert raised.value.site == "drain-cap", raised.value.site
        assert isinstance(raised.value, AssertionError)
        assert "drain-cap -> drain-cap -> drain-cap" in str(raised.value), (
            str(raised.value)
        )
    finally:
        _close_partially_constructed(rigs)


# --- the drain-poll TIMEOUT-flavor poison (issue #241 slice 4) ---------------------

#: The trial machinery's known infrastructure site labels — the membership
#: set the refute folds (A-F2/A-F3) pin compositions against. Grep-verified
#: against ``site="`` in this module; 'synthetic' is excluded — the
#: synthetic-marker machinery pin's own label, never a real trial's site.
_INFRASTRUCTURE_SITES = frozenset(
    {
        "dispatch-door",
        "drain-cap",
        "drain-poll-door",
        "drain-poll-timeout",
        "pre-flight-staleness",
        "priming-block-refusal",
        "priming-validity",
        "write-leg-door",
    }
)

def _install_drain_poll_timeout_poison(
    monkeypatch: pytest.MonkeyPatch,
    *,
    every_construction: bool = False,
) -> tuple[list[ContinuityRig], list[OTDPBridge]]:
    """Force the TIMEOUT-flavor poison presentation (issue #241 slice 4,
    design §1.3): the poisoned rig's bridge returns the TIMEOUT-flavor
    session poison on its first poll — a poll whose event delivery
    outran the poll's own 50 ms deadline under host stall, the exact
    presentation ``_poll_found_dead_session``'s own disclosure named
    (one live observation logged at the slice-3 outcome comment). The
    poison fires at the rig's first post-trip drain poll — gated on the
    owning rig's monitor having latched its cause, the same post-trip
    for-branch context the sibling ``drain-poll-door`` site raises in —
    so the trial still reaches its measured dispatch and each attempt
    burns the real trial rhythm (~2-3 s, disclosed).
    ``every_construction=True`` poisons every rig (the exhaustion arm):
    all three attempts die at their first post-trip drain poll. Returns
    (rigs, poison_served) — the rigs (the slice-1 counter shape) for the
    caller's failure belt, and the bridges the poison actually SERVED at
    their post-trip poll (A-F2: empty means the poisoned rig's attempt
    never reached post-trip — a natural infrastructure site preempted it —
    and the membership pin tolerates the substitution).
    The poison mirrors the bridge's real adapter-TimeoutError
    presentation: TIMEOUT + UNKNOWN, not the clean poll-deadline
    refusal's NOT_DISPATCHED. (Why the post-trip gate: a pre-trip poison
    rides ``poll_slice`` — the engine's ``poll_round`` latches
    ``session_failed`` and STOPS silently, delivery stalls, and the
    trial dies at the ``drain-cap`` site without ever reaching this
    classification — measured in this session's build.)"""
    rigs: list[ContinuityRig] = []
    bridges: list[OTDPBridge] = []
    original_init = ContinuityRig.__init__

    def counting_init(self: ContinuityRig, db_path: Path, **kwargs: Any) -> None:
        rigs.append(self)
        original_init(self, db_path, **kwargs)
        bridges.append(self.bridge_b)

    monkeypatch.setattr(ContinuityRig, "__init__", counting_init)
    original_poll_event = OTDPBridge.poll_event

    poison_served: list[OTDPBridge] = []

    def poisoned_poll_event(
        self: OTDPBridge, subscription_id: str, *, deadline_ns: int
    ) -> PollOutcome:
        poisoned = bridges if every_construction else bridges[:1]
        if any(self is bridge for bridge in poisoned):
            rig = next(rig for rig in rigs if rig.bridge_b is self)
            if rig.monitor.cause is not None:
                poison_served.append(self)
                return PollOutcome(
                    refusal=OperationError(
                        ErrorCode.TIMEOUT,
                        "poisoned poll: delivery outran the poll's own 50 ms deadline",
                        DispatchState.UNKNOWN,
                    ),
                    session_failed=True,
                )
        return original_poll_event(self, subscription_id, deadline_ns=deadline_ns)

    monkeypatch.setattr(OTDPBridge, "poll_event", poisoned_poll_event)
    return rigs, poison_served


def test_drain_poll_timeout_poison_retries_on_a_fresh_rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #241 slice 4 (design §1.3), the membership pin (the
    de-clock doctrine's form, the drain-cap pin precedent): the poisoned
    rig's first post-trip drain poll raises at the ``drain-poll-timeout``
    site, the raise rides ``run_trial``'s fresh-rig retry, and the
    unpoisoned second construction completes the trial. Asserts the
    PROPERTY, not the attempt bookkeeping — ``retries >= 1`` and
    ``"drain-poll-timeout" in retry_sites`` — because under load the
    UNPOISONED attempt can itself hit a real starvation site the retry
    budget legitimately absorbs. Runs the production policy; burns the
    real trial rhythm per attempt (~2-3 s, disclosed)."""
    rigs, poison_served = _install_drain_poll_timeout_poison(monkeypatch)
    try:
        outcome = run_trial(
            tmp_path, arm="non_capture", device_class="buffered", trial_index=9
        )
        assert outcome["retries"] >= 1, outcome["retries"]
        sites = outcome["retry_sites"]
        assert sites, sites
        # A-F2 (refute fold): every rendered site is a known infrastructure
        # site, and the poison's own site is present whenever the poison
        # actually SERVED — a natural pre-trip site on the poisoned rig's
        # attempt preempts the post-trip poll entirely, so the composition
        # may legitimately substitute (this pin's property is the retry
        # machinery itself; the classification is pinned next door at
        # exhaustion, where every rig is poisoned).
        assert all(site in _INFRASTRUCTURE_SITES for site in sites), sites
        assert "drain-poll-timeout" in sites or not poison_served, (
            sites,
            len(poison_served),
        )
    finally:
        _close_partially_constructed(rigs)


def test_drain_poll_timeout_poison_exhausts_at_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AR-2b, the kill direction: a DETERMINISTIC TIMEOUT poison on
    every construction must still red — through exhaustion, with the
    composition rendered. The widening cannot launder a rig defect: a
    poisoned poll on every rig burns exactly three attempts and fails as
    a normal assertion (TrialInfrastructureError is an AssertionError
    subclass). A-F3 (refute fold): the rendered composition's sites are
    asserted by MEMBERSHIP in the infrastructure-site set, not as an
    exact homogeneous triple — a natural infrastructure site may
    substitute on any attempt; the render itself is still required.
    Three real trial rhythms (~7-9 s, disclosed; no cap spins — the
    poison fires at the first post-trip poll)."""
    rigs, poison_served = _install_drain_poll_timeout_poison(
        monkeypatch, every_construction=True
    )
    try:
        with pytest.raises(TrialInfrastructureError) as raised:
            run_trial(
                tmp_path, arm="non_capture", device_class="buffered", trial_index=10
            )
        assert len(rigs) == 3, len(rigs)
        assert type(raised.value) is TrialInfrastructureError
        assert isinstance(raised.value, AssertionError)
        rendered = str(raised.value)
        # A-F3 (refute fold): the composition must still RENDER — the §5.2
        # family requires it — but the exact homogeneous triple is not
        # asserted: a natural infrastructure site may substitute on any
        # attempt, so every rendered site must be a known infrastructure
        # site. The error's own site is the composition's LAST element
        # (run_trial appends it before re-raising) — consistency, not a
        # fixed label.
        marker = "[retry composition exhausted after 3 attempts: "
        assert marker in rendered, rendered
        composition = rendered.rsplit(marker, 1)[1].rstrip("]")
        sites = composition.split(" -> ")
        assert sites and all(s in _INFRASTRUCTURE_SITES for s in sites), composition
        assert raised.value.site == sites[-1], (raised.value.site, composition)
    finally:
        _close_partially_constructed(rigs)


# --- F1 fold: block-ness is the monitor's latch, never cause-adjacency (#159) ------


_FRESHNESS_REASON = "rig-b-level-bounds: signal_invalid: sig-rig-b-level"
_ESCAPE_REASON = (
    "rig-b-level-bounds: interval_escape: [4.95, 5.05] escapes [-0.1, 4.5]"
)


class _ClassifierMonitor:
    """The monitor state ``_dispatch_failure_is_infrastructure`` reads — the
    direct-classifier table's stand-in (the F1 refute lanes' coverage
    finding: the classifier family had zero direct tests, which is how the
    cause-adjacency hole landed unwitnessed)."""

    def __init__(
        self, *, cause: str | None, cause_reasons: list[str], blocked: bool
    ) -> None:
        self.cause = cause
        self.cause_reasons = cause_reasons
        self.blocked = blocked


class _ClassifierBridge:
    def __init__(self, *, failed: bool) -> None:
        self._failed = failed


class _ClassifierRig:
    def __init__(
        self, *, monitor: _ClassifierMonitor, bridge: _ClassifierBridge
    ) -> None:
        self.monitor = monitor
        self.bridge_a = bridge


def _classifier_result(
    code: ErrorCode, state: DispatchState, message: str
) -> OperationResult:
    return OperationResult.failure(
        "op-classifier",
        OperationVerb.WRITE,
        code=code,
        message=message,
        dispatch_state=state,
    )


def _device_rejection_envelope(request: dict[str, Any]) -> dict[str, Any]:
    """A plain device-side OTDP refusal — the standard "device said no"
    posture (``DEVICE_REJECTED``, nothing sent)."""
    return {
        "operation_id": request["operation_id"],
        "verb": request["verb"],
        "status": "error",
        "error": {
            "code": "DEVICE_REJECTED",
            "message": "device refused: parameter outside permitted range",
            "dispatch_state": "not_dispatched",
        },
    }


@pytest.mark.parametrize(
    ("result", "monitor", "bridge", "expected"),
    [
        pytest.param(
            _classifier_result(
                ErrorCode.DEVICE_REJECTED,
                DispatchState.NOT_DISPATCHED,
                f"protection trip: {_FRESHNESS_REASON}",
            ),
            _ClassifierMonitor(
                cause="tripped", cause_reasons=[_FRESHNESS_REASON], blocked=True
            ),
            _ClassifierBridge(failed=False),
            True,
            id="genuine-monitor-freshness-block-retries",
        ),
        pytest.param(
            _classifier_result(
                ErrorCode.INTERNAL_ERROR,
                DispatchState.NOT_DISPATCHED,
                "A fresh opened bridge is required",
            ),
            _ClassifierMonitor(cause=None, cause_reasons=[], blocked=False),
            _ClassifierBridge(failed=True),
            True,
            id="dead-session-door-retries",
        ),
        pytest.param(
            _classifier_result(
                ErrorCode.DEVICE_REJECTED,
                DispatchState.NOT_DISPATCHED,
                "parameter outside permitted range",
            ),
            _ClassifierMonitor(
                cause="tripped", cause_reasons=[_FRESHNESS_REASON], blocked=False
            ),
            _ClassifierBridge(failed=False),
            False,
            id="f1-write-leg-device-rejection-with-latched-cause-never-retries",
        ),
        pytest.param(
            _classifier_result(
                ErrorCode.DEVICE_REJECTED,
                DispatchState.NOT_DISPATCHED,
                "device refused: parameter not readable in current state",
            ),
            _ClassifierMonitor(
                cause="tripped", cause_reasons=[_FRESHNESS_REASON], blocked=False
            ),
            _ClassifierBridge(failed=False),
            False,
            id="f1-measured-dispatch-device-rejection-post-tick-cause-never-retries",
        ),
        pytest.param(
            _classifier_result(
                ErrorCode.INTERNAL_ERROR,
                DispatchState.DISPATCHED,
                "adapter-reported internal failure after execution",
            ),
            _ClassifierMonitor(cause=None, cause_reasons=[], blocked=False),
            _ClassifierBridge(failed=True),
            False,
            id="dispatched-internal-error-envelope-never-retries",
        ),
        pytest.param(
            _classifier_result(
                ErrorCode.DEVICE_REJECTED,
                DispatchState.DISPATCHED,
                f"protection trip: {_FRESHNESS_REASON}",
            ),
            _ClassifierMonitor(
                cause="tripped", cause_reasons=[_FRESHNESS_REASON], blocked=True
            ),
            _ClassifierBridge(failed=False),
            False,
            id="dispatched-block-shaped-envelope-never-retries",
        ),
        pytest.param(
            _classifier_result(
                ErrorCode.DEVICE_REJECTED,
                DispatchState.NOT_DISPATCHED,
                f"protection trip: {_ESCAPE_REASON}",
            ),
            _ClassifierMonitor(cause="tripped", cause_reasons=[_ESCAPE_REASON], blocked=True),
            _ClassifierBridge(failed=False),
            False,
            id="real-trip-block-stays-plain",
        ),
        pytest.param(
            _classifier_result(
                ErrorCode.INTERNAL_ERROR,
                DispatchState.NOT_DISPATCHED,
                "capture open failed: store busy",
            ),
            _ClassifierMonitor(cause=None, cause_reasons=[], blocked=False),
            _ClassifierBridge(failed=False),
            False,
            id="capture-gate-store-refusal-stays-plain",
        ),
        pytest.param(
            _classifier_result(
                ErrorCode.PROTOCOL_ERROR,
                DispatchState.UNKNOWN,
                "Invalid, failed or late adapter result; no replay",
            ),
            _ClassifierMonitor(cause=None, cause_reasons=[], blocked=False),
            _ClassifierBridge(failed=True),
            False,
            id="late-result-poison-stays-plain",
        ),
    ],
)
def test_dispatch_failure_classifier_table(
    result: OperationResult,
    monitor: _ClassifierMonitor,
    bridge: _ClassifierBridge,
    expected: bool,
) -> None:
    """Direct classifier pins (F1's coverage remedy): a genuine monitor
    block — read from the monitor's OWN blocked latch — and the
    dead-session door stay retryable; a device-side rejection never
    retries, whatever cause is latched (F1's two lanes present the SAME
    classifier state: cause latched, no block — block-ness is what
    differs); and no envelope claiming the work was dispatched retries
    (retryable infrastructure means the dispatch NEVER ran)."""
    rig = cast(ContinuityRig, _ClassifierRig(monitor=monitor, bridge=bridge))
    assert _dispatch_failure_is_infrastructure(rig, result) is expected


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        pytest.param(
            PollOutcome(
                refusal=OperationError(
                    ErrorCode.INTERNAL_ERROR,
                    "A fresh opened bridge is required",
                    DispatchState.NOT_DISPATCHED,
                ),
                session_failed=True,
            ),
            True,
            id="dead-at-the-door-retries",
        ),
        pytest.param(
            PollOutcome(
                refusal=OperationError(
                    ErrorCode.PROTOCOL_ERROR,
                    "Invalid, failed or late adapter event; no replay",
                    DispatchState.UNKNOWN,
                ),
                session_failed=True,
            ),
            False,
            id="self-poisoned-protocol-lie-stays-plain",
        ),
        pytest.param(
            PollOutcome(
                refusal=OperationError(
                    ErrorCode.TIMEOUT,
                    "Invalid, failed or late adapter event; no replay",
                    DispatchState.UNKNOWN,
                ),
                session_failed=True,
            ),
            False,
            id="timeout-flavor-starvation-is-a-disclosed-residual-not-retryable",
        ),
        pytest.param(
            PollOutcome(
                refusal=OperationError(
                    ErrorCode.INTERNAL_ERROR,
                    "registry invariant violated",
                    DispatchState.NOT_DISPATCHED,
                ),
            ),
            False,
            id="internal-error-without-session-failure-stays-plain",
        ),
        pytest.param(PollOutcome(), False, id="quiet-poll-stays-plain"),
    ],
)
def test_poll_dead_session_classifier_table(
    outcome: PollOutcome, expected: bool
) -> None:
    """Direct pins for the drain-side classifier: only a session already
    dead at the poll door retries. The TIMEOUT-flavor poison is
    starvation-shaped yet stays non-retryable — the disclosed owner-row
    residual, deliberately not a classifier input here."""
    assert _poll_found_dead_session(outcome) is expected


def _starved_trip_rig_counter(monkeypatch: pytest.MonkeyPatch) -> list[ContinuityRig]:
    """The F1 repro precondition: count every rig constructed, and tighten
    SIG_B's commissioned freshness bound so the measured dispatch's own
    blackout latches ``signal_invalid`` at the wrapper's post-dispatch tick
    (the starved-host trip class) — a latched cause WITHOUT any block."""
    rigs: list[ContinuityRig] = []
    original_init = ContinuityRig.__init__

    def counting_init(self: ContinuityRig, *args: Any, **kwargs: Any) -> None:
        rigs.append(self)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(ContinuityRig, "__init__", counting_init)
    tightened = copy.deepcopy(BENCH)
    for signal in tightened["signals"]:
        if signal["id"] == SIG_B:
            signal["max_age_ms"] = 150
    monkeypatch.setitem(globals(), "BENCH", tightened)
    return rigs


def test_transient_device_write_refusal_cannot_launder_into_clean_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1 lane 1, end to end: with the freshness cause latched (the
    protective transition is done — phase idle, so no block is possible),
    device A refuses the write leg with a plain device-side
    ``DEVICE_REJECTED`` envelope. The cause-adjacency classifier retried
    it and the fresh rig measured clean, returning a CLEAN verdict with
    the device's refusal swallowed (adversarial probe: 2 rigs, no raise).
    De-clocked by slice 3 (design §1.1): the injection refuses the write
    leg on EVERY rig — an infrastructure retry can no longer dodge it by
    landing on a later construction (the load shape that produced the
    ``DID NOT RAISE`` red, run 36817483120, where an infra retry moved
    the write leg to an unpatched rig and the refusal never fired —
    indistinguishable in the old shape from real laundering). The pin is
    the TYPE: ``type(raised.value) is AssertionError`` — the device
    refusal itself was never classified. ``TrialInfrastructureError``
    SUBCLASSES ``AssertionError``, so the type pin discriminates the
    laundering regression (a classified refusal retries, exhausts, and
    re-raises as ``TrialInfrastructureError`` — this pin reds, pinned by
    the AR-2a planted-bug arm next door) while remaining indifferent to
    however many infrastructure retries preceded the refusal. The
    ``len(rigs)`` count assert is deleted, not re-banded: which rig the
    refusal fired on is exactly what load moves."""
    _starved_trip_rig_counter(monkeypatch)
    original_execute = ARigAdapter.execute

    async def rejecting_every_write(
        self: ARigAdapter, request: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        if request["verb"] == "write":
            return _device_rejection_envelope(request)
        return await original_execute(self, request, context)

    monkeypatch.setattr(ARigAdapter, "execute", rejecting_every_write)
    with pytest.raises(AssertionError) as raised:
        run_trial(tmp_path, arm="non_capture", device_class="buffered", trial_index=44)
    assert type(raised.value) is AssertionError


def test_measured_dispatch_device_refusal_with_latched_staleness_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1 lane 2, end to end: the device consumes the acquisition window
    (a 220 ms paced read against the tightened 150 ms freshness bound) and
    then refuses the MEASURED dispatch device-side; the wrapper's
    post-dispatch tick latches ``signal_invalid`` BEFORE the site
    classifies — cause-adjacent, never a block. De-clocked by slice 3
    (design §1.1): the pin is the TYPE — ``type(raised.value) is
    AssertionError``, the refusal itself was never classified —
    indifferent to how many infrastructure retries preceded it (the two
    ``len(rigs) != 1`` reds, runs 36395616332/36818395071, were an
    earlier site legitimately consuming attempt 0; the no-retry property
    held in both). The count assert is deleted, not re-banded; the
    injection already refuses on every rig."""
    _starved_trip_rig_counter(monkeypatch)
    original_execute = ARigAdapter.execute

    async def window_consuming_refusal(
        self: ARigAdapter, request: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        if request["verb"] == "read" and request["operation_id"] == "op-acq":
            await asyncio.sleep(0.22)
            return _device_rejection_envelope(request)
        return await original_execute(self, request, context)

    monkeypatch.setattr(ARigAdapter, "execute", window_consuming_refusal)
    with pytest.raises(AssertionError) as raised:
        run_trial(tmp_path, arm="non_capture", device_class="buffered", trial_index=45)
    assert type(raised.value) is AssertionError


@pytest.mark.parametrize(
    "displaced_final_site",
    [
        pytest.param(False, id="refusal-exhausts-at-dispatch-door"),
        pytest.param(
            True, id="real-starvation-displaces-the-final-attempts-site"
        ),
    ],
)
def test_ar2_classifier_regression_refusal_exhausts_as_infrastructure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, displaced_final_site: bool
) -> None:
    """AR-2(a) (issue #241 slice 3, design §5.1), the planted-regression
    direction that keeps the de-clocked F1 pins' RED: if the dispatch
    classifier ever again classifies a device-side
    ``DEVICE_REJECTED``+``NOT_DISPATCHED`` refusal as infrastructure (the
    cause-adjacency bug F1 fixed), the refusal no longer raises plain —
    it retries on fresh rigs, exhausts the budget, and re-raises as
    ``TrialInfrastructureError``. This arm plants exactly that bug and
    pins the exhausted TYPE: ``type(raised.value) is
    TrialInfrastructureError`` is the precise negation of the F1 lanes'
    ``type(raised.value) is AssertionError`` pin — under this bug both
    lanes red (shown RED-first at build: the de-clocked lanes were run
    with the classifier sabotaged in place and both type pins failed).
    The bug's presence is pinned by MEMBERSHIP — ``"dispatch-door" in
    str(raised.value)`` — never by the exhausted error's own site
    (refute fold B, mech-F1): at exhaustion ``run_trial`` bare-raises the
    LAST attempt's error, so a REAL starvation site on the final attempt
    displaces the site while the planted bug is present — the exact
    false-red class this slice retires (the displaced table row builds
    that shape; the site equality form was shown RED against it at
    build). On healthy machinery the same refusal stays a plain,
    unretried ``AssertionError`` — the F1 lanes themselves."""
    original_classifier = _dispatch_failure_is_infrastructure

    def cause_adjacency_regression(rig: ContinuityRig, result: OperationResult) -> bool:
        error = result.error
        if (
            error is not None
            and error.code is ErrorCode.DEVICE_REJECTED
            and error.dispatch_state is DispatchState.NOT_DISPATCHED
        ):
            return True
        return original_classifier(rig, result)

    monkeypatch.setitem(
        globals(), "_dispatch_failure_is_infrastructure", cause_adjacency_regression
    )
    original_execute = ARigAdapter.execute

    async def refusing_measured_dispatch(
        self: ARigAdapter, request: dict[str, Any], context: Any
    ) -> dict[str, Any]:
        if request["verb"] == "read" and request["operation_id"] == "op-acq":
            return _device_rejection_envelope(request)
        return await original_execute(self, request, context)

    monkeypatch.setattr(ARigAdapter, "execute", refusing_measured_dispatch)
    if displaced_final_site:
        # The critic's probe shape, on the real path: the planted bug
        # classifies attempts 0-1's refusals (dispatch-door, through the
        # real classifier sabotage), then a REAL pre-flight-staleness
        # site consumes the final attempt — the same mixed-site seam the
        # retry-composition pins use.
        original_once = _run_trial_once
        once_calls: list[int] = []

        def displacing_final_site(*args: Any, **kwargs: Any) -> dict[str, Any]:
            once_calls.append(kwargs["trial_index"])
            if len(once_calls) == 3:
                raise TrialInfrastructureError(
                    "pre-dispatch staleness: synthetic (a real load site "
                    "consuming the final attempt)",
                    site="pre-flight-staleness",
                )
            return original_once(*args, **kwargs)

        monkeypatch.setitem(globals(), "_run_trial_once", displacing_final_site)
    with pytest.raises(TrialInfrastructureError) as raised:
        run_trial(tmp_path, arm="non_capture", device_class="buffered", trial_index=46)
    assert type(raised.value) is TrialInfrastructureError
    assert isinstance(raised.value, AssertionError)  # still an assertion for pytest
    assert "dispatch-door" in str(raised.value), str(raised.value)
    if displaced_final_site:
        # The displacement itself is pinned (deterministic by
        # construction — the synthetic wrapper sets it): the membership
        # above holds WHILE the site is not the planted bug's.
        assert raised.value.site == "pre-flight-staleness", raised.value.site
