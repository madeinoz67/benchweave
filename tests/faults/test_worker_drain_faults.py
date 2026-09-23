"""Fault injection for the run worker's drain path (issue #156).

Arm 1 pins the success-path containment contract: a completion emit that
raises — ``ValueError("no document anchor …")``, the real
``_resolve_event_evidence`` refusal's class and text, a known reachable
worker-side outcome — must not kill the drain. Before the fix the emit
escaped the ``else`` arm, the thread died with jobs 4-6 never ``get()``,
and ``queue.join()`` (hence gateway shutdown) hung forever.

Arm 2 pins the bounded join: a dead worker (never started) and a
live-but-stuck worker (a coordinator blocked past every bound) both
surface ``False`` inside the caller's timeout instead of hanging — the
watchdog shapes keep a RED run (an unbounded ``queue.join()``) from
hanging the suite.

Harness shape: the direct-worker arm of
``tests/integration/test_capture_sequential_model.py`` — real ``Store``,
no-op fake coordinators (no terminal record, no monitor: exactly one
``append_bench_event`` per job), a store-seeded bench configuration row
(the emit anchors its event on it), multiple ``submit``s, bounded join.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.interfaces import operations as operations_module
from benchweave.interfaces.worker import RunWorker
from benchweave.state.store import Store

BENCH_ID = "bench.worker-faults"
NOW = "2026-09-23T00:00:00Z"
# Pre-committed observation bounds (design record §7): no-op fake
# coordinators drain in milliseconds — 30 s is three orders of magnitude
# of slack. These bound the TEST's observation, never the production join.
T_OBS = 30.0
WATCHDOG_S = 5.0
POLL_S = 0.05


class _NoopRun:
    """RunCoordinator stand-in: ``start_run`` writes no terminal record
    and carries no monitor, so a successful job emits exactly one bench
    event (the ``run_changed`` completion emit)."""

    def __init__(self) -> None:
        self.entered = threading.Event()

    def start_run(self, run_id: str, principal_id: str) -> dict[str, Any]:
        del principal_id
        self.entered.set()
        return {}

    def cancel(self, run_id: str, principal_id: str) -> None:
        del run_id, principal_id


class _BlockingRun:
    """``start_run`` blocks on an unreleased event — the live-but-stuck
    worker (no fault in the gateway: a run whose coordinator outlives
    every bound)."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def start_run(self, run_id: str, principal_id: str) -> dict[str, Any]:
        del run_id, principal_id
        self.entered.set()
        self.release.wait(timeout=60)
        return {}

    def cancel(self, run_id: str, principal_id: str) -> None:
        del run_id, principal_id


def _join_bounded(
    worker: RunWorker, timeout: float, watchdog: float = WATCHDOG_S
) -> tuple[bool, bool | None]:
    """Call ``worker.join`` from a daemon watchdog thread and wait for it
    bounded: returns ``(returned, value)`` where ``returned`` is False
    when the call outlived the watchdog — the join-hang shape, reported
    as a failure instead of hanging the suite."""
    outcome: dict[str, bool | None] = {}
    done = threading.Event()

    def call() -> None:
        outcome["value"] = worker.join(timeout=timeout)
        done.set()

    thread = threading.Thread(target=call, daemon=True)
    thread.start()
    returned = done.wait(timeout=watchdog)
    return returned, outcome.get("value")


def _terminal_states(store: Store) -> dict[str, str]:
    return {row["run_id"]: row["state"] for row in store.list_run_states(BENCH_ID)}


def _poll_until(
    deadline_s: float, probe: Callable[[], bool]
) -> None:
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if probe():
            return
        time.sleep(POLL_S)


# --- Arm 1: emit fault containment ----------------------------------------------


def test_worker_contains_completion_emit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """6 jobs, the completion emit raises on job 3 (the real refusal's
    class and text). PASS iff all 6 reach terminal, exactly 5 of 6
    emits complete (job 3's ``run_changed`` is honestly missing, carried
    by a gateway-log ERROR keyed by run id), the worker still serves a
    post-drain 7th submit, and join reports a drained queue."""
    store = Store.open(tmp_path / "worker-emit-fault.db")
    content = ContentStore(store)
    # The completion emit anchors its bench event on the bench's
    # configuration row (operations._resolve_event_evidence refuses an
    # event with no document anchor) — seed one.
    store.put_bench(BENCH_ID, 1, "qualification", "{}", "licence", NOW)

    calls: dict[str, list[tuple[str, str | None]]] = {
        "attempts": [],
        "completed": [],
        "raised": [],
    }
    real_emit = operations_module.append_bench_event

    def faulting_emit(
        emit_store: Store,
        kind: str,
        bench_id: str,
        run_id: str | None,
        evidence: dict[str, Any] | None = None,
        *,
        keep: int | None,
        now_iso: Callable[[], str],
    ) -> None:
        calls["attempts"].append((kind, run_id))
        if len(calls["attempts"]) == 3:  # the fault lands on job 3 of 6
            calls["raised"].append((kind, run_id))
            raise ValueError(
                f"no document anchor for event on bench {bench_id!r}"
                f" (run {run_id!r} has no row and the bench has no configuration)"
            )
        real_emit(
            emit_store, kind, bench_id, run_id, evidence, keep=keep, now_iso=now_iso
        )
        calls["completed"].append((kind, run_id))

    # The worker's module-level import binding is the seam both worker emit
    # paths call through — patch it there (string target: the binding is not
    # an explicit export of the worker module).
    monkeypatch.setattr(
        "benchweave.interfaces.worker.append_bench_event", faulting_emit
    )

    built: list[_NoopRun] = []

    def build_run(
        run_id: str, principal_id: str, binding: dict[str, Any], run_store: Store
    ) -> _NoopRun:
        del run_id, principal_id, binding, run_store
        coordinator = _NoopRun()
        built.append(coordinator)
        return coordinator

    worker = RunWorker(store, content, build_run=build_run, now_iso=lambda: NOW)
    worker.start()
    run_ids = [f"run-emit-{i}" for i in range(1, 7)]
    try:
        with caplog.at_level(logging.ERROR, logger="benchweave.interfaces.worker"):
            for run_id in run_ids:
                worker.submit(run_id, "p1", {"id": "b1"}, BENCH_ID)

            # 1. All 6 submitted runs reach terminal within T_obs.

            def _all_six_terminal() -> bool:
                current = _terminal_states(store)
                return set(current) == set(run_ids) and set(current.values()) == {"terminal"}

            _poll_until(T_OBS, _all_six_terminal)
            states = _terminal_states(store)
            terminal_count = sum(1 for s in states.values() if s == "terminal")
            assert set(states) == set(run_ids) and set(states.values()) == {"terminal"}, (
                f"only {terminal_count}/{len(run_ids)} submitted runs reached"
                f" terminal within {T_OBS}s (worker died mid-drain);"
                f" states={states}"
            )

            # 2. Exactly 5 of 6 emits completed; job 3's is honestly missing.

            def _all_emits_resolved() -> bool:
                return len(calls["attempts"]) == len(run_ids) and len(
                    calls["attempts"]
                ) == len(calls["completed"]) + len(calls["raised"])

            _poll_until(10.0, _all_emits_resolved)
            completed_ids = sorted(str(run_id) for _kind, run_id in calls["completed"])
            raised_ids = [str(run_id) for _kind, run_id in calls["raised"]]
            expected_completed = [
                "run-emit-1", "run-emit-2", "run-emit-4", "run-emit-5", "run-emit-6",
            ]
            assert completed_ids == expected_completed, (
                f"completion emits completed for {completed_ids};"
                f" expected exactly jobs 1,2,4,5,6 (job 3's run_changed"
                f" honestly missing), raised={raised_ids}"
            )
            assert raised_ids == ["run-emit-3"], (
                f"the fault must land on job 3; raised={raised_ids}"
            )
            assert all(kind == "run_changed" for kind, _ in calls["completed"])
            # The failure is disclosed, not silent (D4 posture): one ERROR
            # line keyed by run id in the gateway log.
            assert "run_worker completion close failed run_id=run-emit-3" in caplog.text, (
                "the contained completion failure must be visible in the"
                f" gateway log; caplog={caplog.text!r}"
            )

            # 3. Liveness past the fault: a post-drain 7th submit lands
            #    terminal — the worker survived, not just the queue.
            worker.submit("run-emit-7", "p1", {"id": "b7"}, BENCH_ID)
            _poll_until(
                10.0,
                lambda: _terminal_states(store).get("run-emit-7") == "terminal",
            )
            seventh = _terminal_states(store).get("run-emit-7", "absent")
            assert seventh == "terminal", (
                f"worker did not survive the fault: 7th submit state={seventh!r}"
            )

            # 4. join reports the drained queue.
            returned, value = _join_bounded(worker, timeout=T_OBS)
            assert returned, "join did not return within its watchdog"
            assert value is True, f"join must report a drained queue; got {value!r}"
        assert len(built) == 7  # every submitted job built a coordinator
    finally:
        worker.stop()
        _join_bounded(worker, timeout=5.0)
        store.close()


# --- Arm 2: bounded join ---------------------------------------------------------


def test_join_surfaces_dead_worker_within_bound(tmp_path: Path) -> None:
    """(i) Dead worker: constructed, never started, 2 queued jobs —
    ``join(timeout=0.5)`` returns within the 5 s watchdog AND reports
    ``False`` (a dead thread with outstanding work surfaces; hanging
    would be a lie)."""
    store = Store.open(tmp_path / "worker-dead.db")
    content = ContentStore(store)

    def build_run(
        run_id: str, principal_id: str, binding: dict[str, Any], run_store: Store
    ) -> _NoopRun:
        del run_id, principal_id, binding, run_store
        return _NoopRun()

    worker = RunWorker(store, content, build_run=build_run, now_iso=lambda: NOW)
    worker.submit("run-dead-1", "p1", {"id": "b1"}, BENCH_ID)
    worker.submit("run-dead-2", "p1", {"id": "b2"}, BENCH_ID)
    try:
        returned, value = _join_bounded(worker, timeout=0.5)
        assert returned, (
            f"join did not return within the {WATCHDOG_S}s watchdog — it hangs"
        )
        assert value is False, (
            f"a dead worker with outstanding work must surface False; got {value!r}"
        )
    finally:
        store.close()


def test_join_bounded_while_worker_live_but_stuck(tmp_path: Path) -> None:
    """(ii) Live-but-stuck: the coordinator blocks on an unreleased
    event; ``join(timeout=0.5)`` returns ``False`` within bounds from the
    deadline branch. Liveness at the False return is proved behaviorally:
    releasing the block lets the run finish — a dead thread could not."""
    store = Store.open(tmp_path / "worker-stuck.db")
    content = ContentStore(store)
    stuck = _BlockingRun()

    def build_run(
        run_id: str, principal_id: str, binding: dict[str, Any], run_store: Store
    ) -> _BlockingRun:
        del run_id, principal_id, binding, run_store
        return stuck

    worker = RunWorker(store, content, build_run=build_run, now_iso=lambda: NOW)
    worker.start()
    worker.submit("run-stuck", "p1", {"id": "b1"}, BENCH_ID)
    try:
        assert stuck.entered.wait(timeout=10), "run never entered start_run"
        returned, value = _join_bounded(worker, timeout=0.5)
        assert returned, (
            f"join did not return within the {WATCHDOG_S}s watchdog — it hangs"
        )
        assert value is False, (
            f"a live-but-stuck worker must surface False at the bound; got {value!r}"
        )
        # The deadline branch, not the death branch: release and watch the
        # run finish — the thread was alive the whole time.
        stuck.release.set()
        _poll_until(
            10.0, lambda: _terminal_states(store).get("run-stuck") == "terminal"
        )
        state = _terminal_states(store).get("run-stuck", "absent")
        assert state == "terminal", (
            f"thread was not alive at the False return (state={state!r})"
        )
    finally:
        stuck.release.set()
        worker.stop()
        _join_bounded(worker, timeout=5.0)
        store.close()
