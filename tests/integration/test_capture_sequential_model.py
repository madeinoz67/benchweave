"""The slice-1 sequential-model quantities (Decision 1's measurement).

Disclosure, not a decision input (C10): these numbers CHARACTERISE the
globally serialized model slices 1–2 ship — they are not evidence that the
serial model is acceptable. Row 1's live reopen arm is the slice-2 poll
engine; no green number here may be cited as evidence the serial model is
acceptable.

Quantities (record item 10, amended by B2/C4/C5/C14):

1. Monitor gap during a deadline-max capture — ticks freeze while the
   blocking capture dispatch is in flight (the wrapper has no tick inside
   a dispatch). Fixture per C4: the adapter's natural duration (~800 ms of
   paced chunks) exceeds the declared budget (50 ms) + tolerance, so the
   bound arm is discriminable — the revert-map row is G5's ``bounded()``
   timeout arm (disable it and the gap tracks the adapter's natural
   duration, failing the bound).
2. Queued-run delay — driven through the REAL ``RunWorker`` (B2): a fake
   ``build_run`` whose ``start_run`` performs the capture dispatch, two
   submits, the second's start delay ≈ the remaining capture duration.
3. Second-dispatch lock-block — a helper-thread ``write`` dispatch during
   the capture blocks on the bridge ``RLock`` (reentrant per thread; the
   helper cannot deadlock); measured wait ≈ remaining capture duration.
4. Store contention (C5): the holder acquires the write lock MID-capture
   (between appends — hold-from-start only stresses the gate region); the
   asserted signal is the classification outcome (writer-originated
   ``OperationalError`` → RESOURCE_LIMIT, session NOT poisoned, staging
   reclaimed). The stretch magnitude under a release-before-timeout hold
   is reported as row-9 input (the busy-timeout clamp itself is row-9
   scope).

Assertions are orderings with generous tolerances (100–150 ms bands on
~50–300 ms fixtures) — CI-stable on the lanes that exist (no Windows
lane). Monitor prerequisites per C14: active lease, phase=body, bench
signals, a non-tripping policy — the fixture fails loudly if the wrapper
is dropped to "simplify" (the priming dispatch asserts ticks and reads
actually flow).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from benchweave.content.capture_services import build_capture_services
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.content.store import ContentStore
from benchweave.control.clocking import SystemClock
from benchweave.control.coordinator import _MonitoringPlugin, _RunMonitor
from benchweave.control.protection import bench_poll_ns
from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.plugin import SimulationInfo
from benchweave.host.services import QuotaLimits
from benchweave.host.types import (
    DispatchState,
    ErrorCode,
    OperationRequest,
    OperationResult,
    OperationStatus,
    OperationVerb,
)
from benchweave.interfaces.worker import RunWorker
from benchweave.state.store import Store

BUDGET_MS = 50
TOLERANCE_MS = 150

BENCH_ID = "bench.seq-model"
BENCH_SIGNALS = [
    {
        "id": "sig-temp",
        "source": {"device_id": "dev-1", "kind": "parameter", "parameter": "temp"},
        "max_age_ms": 600_000,
    }
]


def _now_iso() -> str:
    return SystemClock().now_iso()


class CapturingAdapter:
    """Serves bench-signal reads (and a scalar write receipt) plus a
    chunk-paced capture whose natural duration (~2 ms per chunk) exceeds
    the declared budget."""

    def __init__(self, *, chunks: int = 100, chunk_bytes: int = 8) -> None:
        self.chunks = chunks
        self.chunk_bytes = chunk_bytes
        self.calls = 0
        self.services: Any = None

    async def open(self, descriptor: dict[str, Any], services: Any, context: Any) -> None:
        self.services = services

    async def close(self, context: Any) -> None:
        pass

    async def execute(self, request: dict[str, Any], context: Any) -> dict[str, Any]:
        self.calls += 1
        verb = request["verb"]
        if verb == "read":
            return {
                "operation_id": request["operation_id"],
                "verb": "read",
                "status": "ok",
                "data": {
                    "parameter": request["arguments"]["parameter"],
                    "value": 23.5,
                    "unit": "Cel",
                    "observed_at": _now_iso(),
                    "age_ms": 0,
                    "quality": "valid",
                    "source": "device",
                },
            }
        if verb == "write":
            return {
                "operation_id": request["operation_id"],
                "verb": "write",
                "status": "ok",
                "data": {
                    "parameter": request["arguments"]["parameter"],
                    "requested_value": request["arguments"]["value"],
                    "effective_value": request["arguments"]["value"],
                    "assurance": "dispatched",
                },
            }
        if verb != "capture":
            raise ValueError(f"unsupported verb {verb!r}")
        capture_id = request["arguments"]["capture_id"]
        for _ in range(self.chunks):
            if context.is_cancelled():
                break
            await self.services.artifact_append(
                capture_id, b"\x01" * self.chunk_bytes, context
            )
            await asyncio.sleep(0.002)  # honest paced traffic, ~2 ms/chunk
        manifest = await self.services.artifact_finalise(
            capture_id,
            {
                "format": "waveform_f64le",
                "started_at": _now_iso(),
                "sample_interval_s": 0.001,
                "unit": "V",
            },
            context,
        )
        return {
            "operation_id": request["operation_id"],
            "verb": "capture",
            "status": "ok",
            "data": manifest,
        }


class MonitoredHarness:
    """A bridge + controller + monitor (real _RunMonitor, phase=body, an
    active lease, one bench signal, a non-tripping policy), with every
    tick's start time recorded on the real monotonic clock."""

    def __init__(self, db_path: Path, *, chunks: int = 400) -> None:
        self.clock = SystemClock()
        self.wall = SystemClock()
        self.store = Store.open(db_path, check_same_thread=False)
        content = ContentStore(self.store)
        raw = {
            "id": "dev.local.seq-model",
            "descriptor_version": "1.0.0",
            "integration": {"adapter": {"permissions": ["artifact_writer"]}},
        }
        blob = json.dumps(raw, sort_keys=True).encode()
        digest = hashlib.sha256(blob).hexdigest()
        content.put_document(blob, digest, raw, "otdp-descriptor", _now_iso())
        self.writer = CaptureStagingStore(
            self.store, max_capture_bytes=8192, max_dataset_bytes=8192
        )
        bundle, controller = build_capture_services(
            descriptor_digest=digest,
            content=content,
            writer=self.writer,
            clock=time.monotonic,
            wall=self.wall.now_iso,
            quota=QuotaLimits(
                max_dataset_bytes=8192, max_evidence_entries=50, max_event_batch=10
            ),
            context_key="seq-model-session",
        )
        assert controller is not None
        self.controller = controller
        self.adapter = CapturingAdapter(chunks=chunks)
        self.bridge = OTDPBridge(
            self.adapter,
            descriptor={
                "capture_formats": ["waveform_f64le", "raw_binary"],
                "capture_limits": {"max_samples": 1024, "max_bytes": 8192},
            },
            services=bundle,
            simulation=SimulationInfo(True, "Synthetic"),
            capture=self.controller,
        )
        self.bridge.plugin_open(object())
        self.lease = self.store.next_lease(
            BENCH_ID, "lease-seq", holder="run-seq", expires_at="2030-01-01T00:00:00Z"
        )
        self.monitor = _RunMonitor(
            self.store,
            BENCH_ID,
            {"continuous_conditions": []},  # non-tripping policy (C14)
            {"signals": BENCH_SIGNALS},
            {},
            self.clock,
            self.wall,
            run_id="run-seq",
            lease_sequence=self.lease.sequence,
        )
        self.monitor.phase = "body"
        self.plugin = _MonitoringPlugin(self.bridge, self.monitor)
        self.tick_times: list[int] = []
        self._original_tick = self.monitor.tick
        self.monitor.tick = self._recording_tick  # type: ignore[method-assign]
        # C14: the fixture fails loudly if the wrapper is dropped — the
        # priming dispatch proves ticks flow and signal reads serve.
        primed = self.plugin.dispatch(
            OperationRequest.read("prime", parameter="temp"),
            deadline_ns=self.deadline_ns(2000),
        )
        assert primed.status is OperationStatus.OK, "monitoring fixture degenerate"
        assert len(self.tick_times) >= 2, "the wrapper never ticked"

    def _recording_tick(self) -> None:
        self.tick_times.append(self.clock.now_ns())
        self._original_tick()

    def deadline_ns(self, milliseconds: float) -> int:
        """A deadline on the SAME timebase as the bundle clock (the bridge
        compares services.monotonic() seconds against deadline_ns/1e9)."""
        return int((time.monotonic() + milliseconds / 1000) * 1_000_000_000)

    def capture_request(self, capture_id: str = "cap-seq") -> OperationRequest:
        # chunks == sample_count: the adapter appends exactly count×8 bytes
        # (the finalise byte check), paced at ~2 ms per chunk — a natural
        # duration (~200 ms) far above the measurement budget (50 ms).
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

    def max_tick_gap_ms(self) -> float:
        times = self.tick_times
        assert len(times) >= 3, "not enough ticks to measure a gap"
        gap_ns = max(b - a for a, b in zip(times, times[1:], strict=False))
        return gap_ns / 1_000_000

    def close(self) -> None:
        self.store.close()


def test_monitor_gap_during_a_deadline_max_capture(tmp_path: Path) -> None:
    """Quantity 1. Bound: the gap stays within budget + epilogue bound —
    the bridge's ``bounded()`` deadline enforces it (the revert arm: with
    the timeout disabled the adapter runs to its natural ~800 ms and the
    bound fails). Blackout reality: the gap reaches the dispatch duration —
    ticks genuinely freeze (if this ever fails the serial model changed
    and the disclosure is stale). Poll-cadence ratio is REPORTED, never
    thresholded (row 1's input, decided by the owner)."""
    harness = MonitoredHarness(tmp_path / "gap.db")
    try:
        poll_ms = bench_poll_ns({"signals": BENCH_SIGNALS}) / 1_000_000
        result = harness.plugin.dispatch(
            harness.capture_request(), deadline_ns=harness.deadline_ns(BUDGET_MS)
        )
        gap_ms = harness.max_tick_gap_ms()
        print(
            f"\nmonitor gap: {gap_ms:.1f} ms over poll cadence {poll_ms:.1f} ms"
            f" (ratio {gap_ms / poll_ms:.1f}x), outcome {result.status.value}"
        )
        assert result.status is OperationStatus.UNKNOWN  # the budget cut it
        assert gap_ms <= BUDGET_MS + TOLERANCE_MS  # the bound (C4's honest form)
        assert gap_ms >= BUDGET_MS - 40  # the blackout: ticks froze ~the budget
    finally:
        harness.close()


def test_queued_run_delay_behind_a_capture(tmp_path: Path) -> None:
    """Quantity 2 through the REAL RunWorker (B2): run 1's start_run
    performs the deadline-max capture; run 2 (submitted immediately
    after) starts only once run 1 drains — the one-worker FIFO shape."""
    events: dict[str, float] = {}

    class FakeRun:
        def __init__(self, capture: bool) -> None:
            self._capture = capture

        def start_run(self, run_id: str, principal_id: str) -> None:
            events[f"{run_id}:start"] = time.monotonic()
            if not self._capture:
                return
            harness = MonitoredHarness(tmp_path / "worker-run.db")
            try:
                result = harness.plugin.dispatch(
                    harness.capture_request(), deadline_ns=harness.deadline_ns(BUDGET_MS)
                )
                assert result.status is OperationStatus.UNKNOWN
            finally:
                harness.close()

        def cancel(self, run_id: str, principal_id: str) -> None:
            return None

    def build_run(run_id: str, principal_id: str, binding: Any, store: Any) -> Any:
        return FakeRun(capture=run_id == "run-capture")

    store = Store.open(tmp_path / "worker-queue.db")
    content = ContentStore(store)
    # The completion emit anchors its bench event on the bench's
    # configuration row (operations._resolve_event_evidence refuses an
    # event with no document anchor) — seed one.
    store.put_bench(
        BENCH_ID, 1, "qualification", "{}", "licence", _now_iso()
    )
    try:
        worker = RunWorker(store, content, build_run=build_run, now_iso=_now_iso)
        worker.start()
        worker.submit("run-capture", "p1", {"id": "b1"}, BENCH_ID)
        events["run-queued:submit"] = time.monotonic()
        worker.submit("run-queued", "p2", {"id": "b2"}, BENCH_ID)
        worker.join(timeout=30)
        delay_ms = (events["run-queued:start"] - events["run-queued:submit"]) * 1000
        print(f"\nqueued-run delay: {delay_ms:.1f} ms behind a {BUDGET_MS} ms capture")
        assert delay_ms >= BUDGET_MS - 40  # the second run waited out the capture
        assert delay_ms <= BUDGET_MS + 300  # init inside run-1 adds startup
    finally:
        store.close()


def test_second_dispatch_lock_block(tmp_path: Path) -> None:
    """Quantity 3 (B2's relabel: bridge-level second-dispatch lock-block).
    A helper-thread write dispatch issued mid-capture blocks on the bridge
    RLock — the RLock is reentrant per thread, so the helper cannot
    deadlock; its measured wait ≈ the remaining capture duration."""
    harness = MonitoredHarness(tmp_path / "lock-block.db")
    try:
        first_append = threading.Event()
        original_append = harness.writer.append

        def observed_append(capture_id: str, data: bytes, context_key: str) -> None:
            original_append(capture_id, data, context_key)
            first_append.set()

        harness.writer.append = observed_append  # type: ignore[method-assign]
        outcome: dict[str, Any] = {}

        def blocked_write() -> None:
            outcome["start"] = time.monotonic()
            outcome["result"] = harness.bridge.dispatch(
                OperationRequest.write("op-w", parameter="temp", value=1),
                deadline_ns=harness.deadline_ns(BUDGET_MS + TOLERANCE_MS),
            )
            outcome["end"] = time.monotonic()

        helper = threading.Thread(target=blocked_write)
        request = harness.capture_request()
        capture_result: dict[str, OperationResult] = {}

        def run_capture() -> None:
            capture_result["result"] = harness.plugin.dispatch(
                request, deadline_ns=harness.deadline_ns(BUDGET_MS)
            )

        capture_thread = threading.Thread(target=run_capture)
        capture_thread.start()
        assert first_append.wait(timeout=10), "capture never appended"
        helper.start()
        capture_thread.join(timeout=30)
        helper.join(timeout=30)
        wait_ms = (outcome["end"] - outcome["start"]) * 1000
        print(f"\nsecond-dispatch lock-block: helper waited {wait_ms:.1f} ms")
        # The capture's budget expiry poisons the session, so the helper's
        # dispatch REFUSES once the lock releases ("A fresh opened bridge is
        # required") — the measured quantity is the WAIT, and that a result
        # came back at all proves the block released.
        assert outcome["result"].status is OperationStatus.ERROR
        helper_error = outcome["result"].error
        assert helper_error is not None and "fresh opened bridge" in helper_error.message
        assert wait_ms >= 20  # it waited out a real slice of the capture
        assert wait_ms <= BUDGET_MS + TOLERANCE_MS
    finally:
        harness.close()


def test_store_contention_mid_capture_stretches_then_classifies(tmp_path: Path) -> None:
    """C5: the holder acquires the write lock MID-capture (between
    appends). Release-before-timeout: the dispatch stretches by the hold
    and still succeeds (the stretch is REPORTED — row-9 input; the
    busy-timeout clamp itself is row-9 scope). Hold past the store's busy
    timeout: the writer-originated OperationalError classifies
    RESOURCE_LIMIT, the session survives and staging is reclaimed — the
    asserted signals, not the magnitudes."""
    harness = MonitoredHarness(tmp_path / "contention.db", chunks=100)
    try:
        db_path = str(
            harness.store.connection.execute("PRAGMA database_list").fetchone()[2]
        )
        harness.store.connection.execute("PRAGMA busy_timeout=300")

        def hold_lock(seconds: float) -> None:
            contender = sqlite3.connect(db_path, timeout=5.0)
            try:
                contender.execute("BEGIN IMMEDIATE")
                time.sleep(seconds)
                contender.rollback()
            finally:
                contender.close()

        # Arm 1 — release (150 ms) before the busy timeout (300 ms): the
        # mid-capture append waits the hold out; the capture completes.
        first_append = threading.Event()
        original_append = harness.writer.append

        def observed_append(capture_id: str, data: bytes, context_key: str) -> None:
            original_append(capture_id, data, context_key)
            first_append.set()

        harness.writer.append = observed_append  # type: ignore[method-assign]
        arm1_result: dict[str, OperationResult] = {}
        arm1_timing: dict[str, float] = {}

        def arm1_capture() -> None:
            arm1_timing["start"] = time.monotonic()
            arm1_result["result"] = harness.plugin.dispatch(
                harness.capture_request("cap-stretch"),
                deadline_ns=harness.deadline_ns(2000),
            )
            arm1_timing["end"] = time.monotonic()

        t1 = threading.Thread(target=arm1_capture)
        t1.start()
        assert first_append.wait(timeout=10), "arm 1 capture never appended"
        holder = threading.Thread(target=hold_lock, args=(0.15,))
        holder.start()
        holder.join(timeout=10)
        t1.join(timeout=30)
        assert arm1_result["result"].status is OperationStatus.OK
        stretch_ms = (arm1_timing["end"] - arm1_timing["start"]) * 1000
        print(f"\ncontention stretch (release-before-timeout): {stretch_ms:.1f} ms")
        assert stretch_ms >= 110  # the hold was waited out mid-capture

        # Arm 2 — hold (600 ms) past the busy timeout (300 ms): classified.
        # (No pre-open: the bridge's G3 gate opens the capture itself.)
        appended = threading.Event()

        def counted_append(capture_id: str, data: bytes, context_key: str) -> None:
            original_append(capture_id, data, context_key)
            appended.set()

        harness.writer.append = counted_append  # type: ignore[method-assign]
        arm2_result: dict[str, OperationResult] = {}

        def arm2_capture() -> None:
            arm2_result["result"] = harness.bridge.dispatch(
                harness.capture_request("cap-contention"),
                deadline_ns=harness.deadline_ns(2000),
            )

        t2 = threading.Thread(target=arm2_capture)
        t2.start()
        assert appended.wait(timeout=10), "arm 2 capture never appended"
        over_holder = threading.Thread(target=hold_lock, args=(0.6,))
        over_holder.start()
        t2.join(timeout=30)
        over_holder.join(timeout=10)
        result = arm2_result["result"]
        assert result.error is not None
        assert result.error.code is ErrorCode.RESOURCE_LIMIT
        assert result.error.dispatch_state is DispatchState.DISPATCHED
        staged = harness.store.connection.execute(
            "SELECT COUNT(*) FROM capture_staging WHERE state = 'staged'"
        ).fetchone()[0]
        assert staged == 0  # the epilogue reclaimed once the holder released
        follow = harness.bridge.dispatch(
            OperationRequest.read("op-after", parameter="temp"),
            deadline_ns=harness.deadline_ns(2000),
        )
        assert follow.status is OperationStatus.OK  # the session survives
    finally:
        harness.close()
