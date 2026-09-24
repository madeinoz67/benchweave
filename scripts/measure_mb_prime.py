"""M-B' (issue #176 row B): mid-capture contention through a REAL capture
step on the DEV_HEAD-composed activated composition.

The design of record (.claude/deep-review/2026-09-24-issue176-execution-
train-design.md, Decision 2 + the acceptance section) pre-commits the
reading: at least 5 trials; the second writer acquires BEGIN IMMEDIATE
AFTER the G3 gate passes (mid-capture), so the contended writes are the
append and the abort epilogue. Report median and spread of the dispatch
wall-stretch vs the commissioned step deadline, WITH the clamp present;
the held-from-start shape (#167 M-B, median 5.199 s) is the matched
control. Ships if the clamped median is at most 1x busy_timeout plus the
measured epilogue class, with spread <= 25%; underpowered if spread
> 25% (record it, decide nothing); fires arm 3 (Option-B evaluation,
posted to issue #159) only if the clamped stretch exceeds the recorded
2x-busy anchor bound with no clamp-side remediation. M-B' reports the
class split per trial (the F3 table). M-C' rider: queued-run delay
behind the clamped contended capture.

Run lane (not CI gates). From the repo/worktree root:
UV_PROJECT_ENVIRONMENT=venv uv run python scripts/measure_mb_prime.py

The harness is the seam's accepted run-level harness
(tests/integration/test_capture_run.py) driven through
_build_run_factory(contracts=declared_dev_family("execution")) - the
same construction the A-R3/A-R4 controls exercise. The adapter module
is the harness's capture-lane adapter with a measurement-only,
env-gated signal arm (stamps the gate passage, waits for the measurer's
"held" marker, stamps the contended append's outcome). No production
code reads these environment variables; the arm is inert without them.
"""

from __future__ import annotations

import os
import sqlite3
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests" / "integration"))

import test_capture_run as tcr  # noqa: E402  (path set above)

from benchweave.content.store import ContentStore  # noqa: E402
from benchweave.control.clocking import SystemClock  # noqa: E402
from benchweave.interfaces.bootstrap import admit_startup_bench  # noqa: E402
from benchweave.interfaces.worker import RunWorker  # noqa: E402
from benchweave.state.store import Store  # noqa: E402

TRIALS = 5
STEP_TIMEOUT_MS = 2000
BUSY_TIMEOUT_MS = 5000
HOLD_S = 3.5
POLL_S = 0.002
RUN_ID = "run-mb"
STEP_ID = "grab"
CAPTURE_ID = "cap:" + RUN_ID + ":" + STEP_ID


def _require(condition: object, message: str) -> None:
    """A measurement precondition: a script-local loud refusal (ruff
    bans bare assert outside tests)."""
    if not condition:
        raise RuntimeError("M-B' precondition failed: " + str(message))



def _instrumented_source() -> str:
    """The harness adapter with the measurement-only signal arm spliced
    into the capture lane. String-exact against the harness source; the
    asserts make a drifted source fail loudly instead of measuring a
    silently mis-instrumented shape."""
    marker = '        if verb == "capture":\n'
    arm = marker + (
        "            # M-B' instrumentation (env-gated, inert off the measurer):\n"
        "            import os as _os, time as _t\n"
        '            _sig = _os.environ.get("MB_SIGNAL_DIR")\n'
        "            if _sig:\n"
        '                with open(_os.path.join(_sig, "ready"), "w") as f:\n'
        "                    f.write(repr(_t.monotonic()))\n"
        "                _deadline = _t.monotonic() + 30\n"
        '                while not _os.path.exists(_os.path.join(_sig, "held")):\n'
        "                    if _t.monotonic() > _deadline:\n"
        '                        raise AssertionError("measurer never armed the holder")\n'
        "                    await asyncio.sleep(0.002)\n"
        "            capture_id = arguments[\"capture_id\"]\n"
        "            waveform = arguments[\"format\"] == \"waveform_f64le\"\n"
        "            data = bytes(arguments[\"sample_count\"] * 8 if waveform else 8)\n"
        "            try:\n"
        "                await context.services.artifact_append(capture_id, data, context)\n"
        "            except Exception:\n"
        "                if _sig:\n"
        '                    with open(_os.path.join(_sig, "append_raise"), "w") as f:\n'
        "                        f.write(repr(_t.monotonic()))\n"
        "                raise\n"
        '            if _sig:\n'
        '                with open(_os.path.join(_sig, "append_ok"), "w") as f:\n'
        "                    f.write(repr(_t.monotonic()))\n"
        "            manifest = await context.services.artifact_finalise(\n"
        "                capture_id,\n"
        "                {\n"
        '                    "format": arguments["format"],\n'
        '                    "started_at": self.services.utc_now(),\n'
        "                    **(\n"
        '                        {"sample_interval_s": 0.001, "unit": "V"}\n'
        "                        if waveform\n"
        "                        else {}\n"
        "                    ),\n"
        "                },\n"
        "                context,\n"
        "            )\n"
        "            self.last_manifest = manifest\n"
        "            return {\n"
        '                "operation_id": operation_id,\n'
        '                "verb": verb,\n'
        '                "status": "ok",\n'
        '                "data": manifest,\n'
        "            }\n"
    )
    source = tcr.ADAPTER_SOURCE.replace(marker, arm, 1)
    for token in ("MB_SIGNAL_DIR", "append_raise", "held"):
        _require(token in source, "instrumentation surgery missed " + repr(token))
    _require(source.count('if verb == "capture":') == 1, "capture arm duplicated")
    return source


def _harness(root: Path, request_id: str) -> Any:
    """One capture harness in its own directory (fresh store per trial)."""
    tcr.ADAPTER_SOURCE = _instrumented_source()
    return tcr._CaptureHarness(root, request_id, capture_rule="conform")


class _Holder:
    """The second writer: BEGIN IMMEDIATE on its OWN connection, held a
    fixed wall duration, then rolled back - independent of the run
    thread, still holding ACROSS the bridge's abort epilogue."""

    def __init__(self, db_path: str, hold_s: float) -> None:
        self._db_path = db_path
        self._hold_s = hold_s
        self._acquired = threading.Event()
        self._release = threading.Event()
        self.acquired_at: float = 0.0
        self.released_at: float = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        contender = sqlite3.connect(self._db_path, timeout=5.0)
        try:
            contender.execute("BEGIN IMMEDIATE")
            self.acquired_at = time.monotonic()
            self._acquired.set()
            self._release.wait(self._hold_s)
            contender.rollback()
        finally:
            self.released_at = time.monotonic()
            contender.close()

    def arm(self) -> float:
        self._thread.start()
        _require(self._acquired.wait(15), "holder never took the write lock")
        return self.acquired_at

    def release(self) -> float:
        self._release.set()
        self._thread.join(10)
        return self.released_at


def _reader_count(db_path: str, sql: str, params: tuple[str, ...]) -> int:
    """A count on a dedicated read-only connection (WAL readers do not
    block the run thread's writer connection, and never touch it)."""
    conn = sqlite3.connect("file:" + db_path + "?mode=ro", uri=True)
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()


_FORENSIC_SQL = (
    "SELECT COUNT(*) FROM evidence WHERE kind = 'event_log'"
    " AND content_ref_json LIKE ?"
)


def _read_capture_event(db_path: str, run_id: str) -> dict[str, Any]:
    """The capture step's event envelope, read from the durable stream."""
    conn = sqlite3.connect("file:" + db_path + "?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT event_json FROM events WHERE stream_id = ? ORDER BY sequence",
            ("run:" + run_id,),
        ).fetchall()
    finally:
        conn.close()
    import json

    for row in rows:
        event = json.loads(row[0])
        if event.get("kind") == "capture":
            return event
    raise AssertionError("no capture step event found for " + run_id)


def _trial(root: Path, index: int) -> dict[str, Any]:
    """One M-B' trial: contended mid-capture, clamped, through the real
    composition. Returns the per-trial record (the F3 class split)."""
    harness = _harness(root, "req-mb-" + str(index))
    db_path = str(root / "state.db")
    signal_dir = root / "signals"
    signal_dir.mkdir()
    os.environ["MB_SIGNAL_DIR"] = str(signal_dir)
    run_result: dict[str, Any] = {}

    def run() -> None:
        coordinator, store = harness._coordinator(RUN_ID)
        try:
            run_result["record"] = coordinator.start_run(RUN_ID, "principal-mb")
        finally:
            store.close()

    thread = threading.Thread(target=run, daemon=True)
    run_start = time.monotonic()
    thread.start()
    ready_path = signal_dir / "ready"
    gate_deadline = time.monotonic() + 60
    while not ready_path.exists():
        _require(time.monotonic() < gate_deadline, "adapter never signalled the gate")
        time.sleep(POLL_S)
    holder = _Holder(db_path, HOLD_S)
    acquired_at = holder.arm()
    (signal_dir / "held").write_text(repr(time.monotonic()))

    # Poll for the epilogue's forensic row (the reclaim + record landing).
    t_epilogue: float | None = None
    poll_deadline = time.monotonic() + 60
    while t_epilogue is None and time.monotonic() < poll_deadline:
        if _reader_count(db_path, _FORENSIC_SQL, ('%"' + CAPTURE_ID + '"%',)) >= 1:
            t_epilogue = time.monotonic()
            break
        time.sleep(POLL_S)
    thread.join(60)
    _require(not thread.is_alive(), "run never completed")
    os.environ.pop("MB_SIGNAL_DIR", None)
    holder.release()

    record = run_result["record"]
    _require(record["outcome"] == "outcome_unknown", record)
    event = _read_capture_event(db_path, RUN_ID)
    # F3's pair, through the real composition.
    _require(event["error_code"] == "RESOURCE_LIMIT", event)
    _require(event["dispatch_state"] == "dispatched", event)
    # Staging reclaimed in the epilogue; the forensic marker durable.
    staged = _reader_count(
        db_path,
        "SELECT COUNT(*) FROM capture_staging WHERE state = 'staged'",
        (),
    )
    _require(staged == 0, staged)
    forensic = _reader_count(db_path, _FORENSIC_SQL, ('%"' + CAPTURE_ID + '"%',))
    _require(forensic == 1, forensic)

    t_raise = float((signal_dir / "append_raise").read_text())
    append_wait_ms = (t_raise - acquired_at) * 1000
    epilogue_wait_ms = (t_epilogue - t_raise) * 1000
    stretch_ms = (t_epilogue - acquired_at) * 1000
    return {
        "trial": index,
        "outcome": record["outcome"],
        "error_code": event["error_code"],
        "dispatch_state": event["dispatch_state"],
        "append_wait_ms": append_wait_ms,
        "epilogue_wait_ms": epilogue_wait_ms,
        "stretch_ms": stretch_ms,
        "run_ms": (time.monotonic() - run_start) * 1000,
        # The F3 class split: which bound each segment answered to.
        "append_bound": (
            "deadline-clamp" if append_wait_ms < BUSY_TIMEOUT_MS else "default-cap"
        ),
        "epilogue_bound": "holder-release-inside-floor",
    }


def _control(root: Path) -> dict[str, Any]:
    """The matched control: the held-from-start shape (#167 M-B, median
    5.199 s), measured at the BRIDGE level - the condition that number
    names is the gate's busy-wait, and a full-run harness would fail run
    ACCEPTANCE against a 5.5 s hold (the acceptance BEGIN waits the same
    5 s default and refuses first). The holder arms before the dispatch;
    the gate's check-and-reserve contends and waits the full open
    default (clamp = min(5000, 30000) = the default cap)."""
    unit_dir = str(REPO / "tests" / "unit")
    if unit_dir not in sys.path:
        sys.path.insert(0, unit_dir)
    import test_otdp_bridge as tob

    root.mkdir(parents=True, exist_ok=True)
    harness = tob.CaptureHarness(root, busy_timeout_ms=BUSY_TIMEOUT_MS, clock=time.monotonic)
    try:
        holder = _Holder(harness.db_path, HOLD_S + 2.0)
        acquired_at = holder.arm()
        plugin = harness.bridge(tob.CaptureAdapter(chunks=2))
        plugin.plugin_open(object())
        start = time.monotonic()
        result = plugin.dispatch(
            tob.a_capture_request(),
            deadline_ns=time.monotonic_ns() + 30_000_000_000,
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        _require(result.error is not None, "control dispatch unexpectedly ok")
        _require(
            result.error.code.value == "RESOURCE_LIMIT"
            and result.error.dispatch_state.value == "not_dispatched",
            "control classification drifted: " + repr(result.error),
        )
        _require(harness.staged_count() == 0, "control staged rows leaked")
        _require(harness.forensic_count() == 0, "control forensic rows leaked")
        plugin.plugin_close()
        holder.release()
        return {
            "gate_wait_ms": elapsed_ms,
            "hold_ms": (holder.released_at - acquired_at) * 1000,
        }
    finally:
        harness.close()


def _queued_run(root: Path) -> float:
    """M-C': queued-run delay behind the clamped contended capture,
    through the REAL RunWorker (the one-worker FIFO shape)."""
    harness = _harness(root, "req-mb-queued")
    db_path = str(root / "worker.db")
    store = Store.open(root / "worker.db")
    content = ContentStore(store)
    # Startup admission on the WORKER store (the trials get it via
    # _coordinator's open_store; the worker path must store the lattice
    # documents - including the pinned binding - itself).
    admit_startup_bench(
        store, content, harness.lattice_dir, now=tcr.NOW_ISO, contracts=tcr.HEAD
    )
    # The completion emit anchors its bench event on the bench's
    # configuration row - seed one (the seq-model harness precedent).
    store.put_bench(
        tcr.BENCH_ID, 1, "qualification", "{}", "licence", SystemClock().now_iso()
    )
    factory = harness.build_run()
    starts: dict[str, float] = {}
    submitted: dict[str, float] = {}

    def build_run(run_id: str, principal: str, binding: Any, worker_store: Any) -> Any:
        starts[run_id] = time.monotonic()
        return factory(run_id, principal, binding, worker_store)

    worker = RunWorker(store, content, build_run=build_run, now_iso=SystemClock().now_iso)
    worker.start()
    # run-queued is a genuinely NEW request: the §9 idempotency key is
    # the binding DOCUMENT's request id, so a second run needs a second
    # lattice (its own binding bytes) admitted into the same worker
    # store. The bench/policy/procedure bytes are identical across the
    # two lattices; only the binding's request id (and therefore the
    # binding digest) differs.
    queued_harness = _harness(root / "lattice-queued", "req-mb-queued-2")
    admit_startup_bench(
        store,
        ContentStore(store),
        queued_harness.lattice_dir,
        now=tcr.NOW_ISO,
        contracts=tcr.HEAD,
    )
    submitted["run-cap"] = time.monotonic()
    worker.submit("run-cap", "principal-mb", harness.binding_ref(), tcr.BENCH_ID)
    submitted["run-queued"] = time.monotonic()
    worker.submit(
        "run-queued", "principal-mb", queued_harness.binding_ref(), tcr.BENCH_ID
    )

    # Arm the holder when run-cap's adapter signals the gate; run-queued
    # sits in the queue behind the contended capture the whole time.
    signal_dir = root / "signals"
    signal_dir.mkdir()
    os.environ["MB_SIGNAL_DIR"] = str(signal_dir)
    ready = signal_dir / "ready"
    gate_deadline = time.monotonic() + 60
    while not ready.exists():
        _require(time.monotonic() < gate_deadline, "adapter never signalled")
        time.sleep(POLL_S)
    holder = _Holder(db_path, HOLD_S)
    holder.arm()
    (signal_dir / "held").write_text(repr(time.monotonic()))
    poll_deadline = time.monotonic() + 60
    while time.monotonic() < poll_deadline:
        if _reader_count(db_path, _FORENSIC_SQL, ('%"' + CAPTURE_ID + '"%',)) >= 1:
            break
        time.sleep(POLL_S)
    # Run-cap's capture is done (epilogue landed). Retire the signal arm
    # so run-queued's own capture runs uncontended.
    os.environ.pop("MB_SIGNAL_DIR", None)
    holder.release()
    _require(worker.join(60), "worker never drained")
    starts["run-queued"]  # exists
    delay_ms = (starts["run-queued"] - submitted["run-queued"]) * 1000
    store.close()
    return delay_ms


def main() -> None:
    import tempfile

    work = Path(tempfile.mkdtemp(prefix="mb-prime-"))
    print("work dir:", work)
    print(
        f"configuration: step deadline {STEP_TIMEOUT_MS} ms, "
        f"busy_timeout {BUSY_TIMEOUT_MS} ms (stock), hold {HOLD_S:.1f} s"
    )
    trials = [_trial(work / ("trial" + str(i)), i) for i in range(TRIALS)]
    print()
    print("M-B' trials (per-trial F3 class split):")
    print(
        f"{'trial':<6} {'error/state':<24} {'append_ms':>10} "
        f"{'append_bound':<14} {'epilogue_ms':>12} {'stretch_ms':>12}"
    )
    for trial in trials:
        pair = trial["error_code"] + "/" + trial["dispatch_state"]
        print(
            f"{trial['trial']:<6} {pair:<24} {trial['append_wait_ms']:>10.1f} "
            f"{trial['append_bound']:<14} {trial['epilogue_wait_ms']:>12.1f} "
            f"{trial['stretch_ms']:>12.1f}"
        )
    stretches = [t["stretch_ms"] for t in trials]
    epilogues = [t["epilogue_wait_ms"] for t in trials]
    median_stretch = statistics.median(stretches)
    median_epilogue = statistics.median(epilogues)
    spread_pct = (max(stretches) - min(stretches)) / median_stretch * 100
    bound = BUSY_TIMEOUT_MS + median_epilogue
    ships = median_stretch <= bound and spread_pct <= 25.0
    underpowered = spread_pct > 25.0
    anchor_bound = 2 * BUSY_TIMEOUT_MS + 730  # the slice-1 anchor: 10.73 s at 5 s
    print()
    print(f"median stretch: {median_stretch:.1f} ms")
    print(f"spread: {spread_pct:.1f}%")
    print(f"measured epilogue class (median): {median_epilogue:.1f} ms")
    print(f"ships-if bound (1x busy + measured epilogue): {bound:.1f} ms")
    print(f"2x-busy anchor bound: {anchor_bound:.1f} ms")
    if underpowered:
        verdict = "UNDERPOWERED (spread > 25%) - record, decide nothing"
    elif ships:
        verdict = "SHIPS"
    elif median_stretch > anchor_bound:
        verdict = "FIRES ARM 3 (Option-B evaluation)"
    else:
        verdict = "DOES NOT MEET THE SHIPS BOUND - review before deciding"
    print("verdict:", verdict)

    control = _control(work / "control")
    print()
    gate_ms = control["gate_wait_ms"]
    print(
        f"matched control (held-from-start, #167 M-B condition): gate wait "
        f"{gate_ms:.1f} ms (anchor median was 5199 ms)"
    )
    queued_delay_ms = _queued_run(work / "queued")
    print()
    print(
        f"M-C' queued-run delay behind the clamped contended capture: "
        f"{queued_delay_ms:.1f} ms (the contended capture window itself "
        f"was ~{HOLD_S * 1000:.0f} ms)"
    )


if __name__ == "__main__":
    main()
