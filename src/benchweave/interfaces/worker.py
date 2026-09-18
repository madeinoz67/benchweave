"""Single run worker: drains accepted runs one at a time (one active
controlling procedure), owns coordinator execution and state projection.

The worker is the queue half of the run seam: ``Operations.run_start``
accepts and enqueues; this thread executes. Per run it projects the queue
state (``accepted`` → ``running`` → ``terminal``) into ``run_states`` and
delegates execution to a coordinator built by ``build_run`` — Task 8 wires
the real ``RunCoordinator`` (spooling the binding-ref documents into a
run-scoped tmp dir, admitting them, constructing the sim plugins, hooking
retention); Task 5 tests inject a fake with the same public API.
``build_run`` receives the worker thread's OWN re-opened ``Store`` as its
fourth argument — sqlite3 connections are thread-affine, so the whole
coordinator stack (including any ``ContentStore`` built over it) must be
constructed and used on this thread.

sqlite3 connections are thread-affine, so the worker re-opens the store's
database on its own connection (WAL plus the store's busy timeout keep the
two writers serialised safely).
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

from benchweave.content.store import ContentStore
from benchweave.control.clocking import SystemClock
from benchweave.interfaces.operations import append_bench_event
from benchweave.state.store import Store

# D4 (interface-errata slice): worker-side operational context (the poison
# error class/text, retention-failure counts) rides the gateway log keyed
# by run id — the closed event def has no free-form channel, and §10
# excludes crash detail from the wire.
_LOG = logging.getLogger(__name__)


class RunWorker:
    """Drains the accepted-run queue FIFO; exactly one run is ever active.

    A job whose construction or execution raises is contained per job
    (Task 11 poison guard): the queue state closes terminal without a
    terminal record — honest ``outcome_unknown`` through the projection —
    a ``run_changed`` event and a gateway-log ERROR line carry the
    failure (D4: the event pins the binding document; the error text
    rides the log), and the drain continues with the next queued run.
    """

    def __init__(
        self,
        store: Store,
        content: ContentStore,
        *,
        build_run: Callable[[str, str, dict[str, Any], Store], Any],
        now_iso: Callable[[], str] | None = None,
        limits: dict[str, int] | None = None,
    ) -> None:
        self._store = store
        # ``content`` stays on the landed constructor surface; build_run
        # derives its ContentStore from the worker-thread Store it receives.
        del content
        self._build_run = build_run
        self._now_iso = now_iso if now_iso is not None else SystemClock().now_iso
        # Task 6: retention window for drain-side bench events. None = the
        # worker appends untrimmed; the seam's next emit re-trims the stream
        # (worker slack is bounded at three events per completed run).
        self._emit_keep = limits["max_page_size"] * 10 if limits is not None else None
        self._queue: queue.Queue[tuple[str, str, dict[str, Any], str]] = queue.Queue()
        self._thread = threading.Thread(target=self._drain, name="stg-run-worker", daemon=True)
        self._stopping = threading.Event()
        self._done = 0
        self._submitted_count = 0
        self._active_lock = threading.Lock()
        self._active: tuple[str, Any] | None = None
        row = store.connection.execute("PRAGMA database_list").fetchone()
        if row is None or not row[2]:
            raise RuntimeError("run worker requires a file-backed store")
        self._db_path = str(row[2])

    def submit(
        self, run_id: str, principal_id: str, binding_ref: dict[str, Any], bench_id: str
    ) -> None:
        self._queue.put((run_id, principal_id, binding_ref, bench_id))
        self._submitted_count += 1

    @property
    def submitted(self) -> int:
        """Total :meth:`submit` calls — a deduped replay must never move it."""
        return self._submitted_count

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()

    def join(self, timeout: float | None = None) -> None:
        """Wait for the queue to drain.

        Fast path: without :meth:`stop`, once every submitted run is done
        the worker is parked on its next poll — return immediately instead
        of burning the full thread-join timeout. After :meth:`stop`, wait
        for the thread to actually exit.
        """
        self._queue.join()
        if not self._stopping.is_set() and self._done == self._submitted_count:
            return
        self._thread.join(timeout=timeout)

    def cancel(self, run_id: str, principal_id: str) -> None:
        """Forward a cancellation to the active coordinator when it owns the
        run (the coordinator API takes run and principal only — wrap, never
        fork its semantics). A queued-but-unstarted or finished run has no
        coordinator; the request is dropped and the run's own lifecycle
        decides the outcome (§5)."""
        with self._active_lock:
            active = self._active
        if active is not None and active[0] == run_id:
            active[1].cancel(run_id, principal_id)

    def _drain(self) -> None:
        store = Store.open(self._db_path)  # thread-affine connection
        try:
            self._drain_with(store)
        finally:
            # An explicit close, not GC-lifetime: a lingering connection keeps
            # the database files locked on Windows (scratch teardown, and the
            # at-rest commands' directory renames) until the cycle collector
            # happens to run.
            store.close()

    def _drain_with(self, store: Store) -> None:
        while True:
            try:
                run_id, principal_id, binding_ref, bench_id = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._stopping.is_set():
                    return  # queue drained; stop cleanly
                continue
            try:
                store.put_run_state(run_id, bench_id, "running", self._now_iso())
                coordinator = self._build_run(run_id, principal_id, binding_ref, store)
                with self._active_lock:
                    self._active = (run_id, coordinator)
                try:
                    coordinator.start_run(run_id, principal_id)
                finally:
                    with self._active_lock:
                        self._active = None
            except BaseException as error:
                # Task 11 poison guard: one poisoned job must never kill the
                # worker (a dead thread hangs every later run). Truth stays
                # with the run's own lifecycle: the queue state closes
                # terminal WITHOUT a terminal record, so the projection
                # reports outcome_unknown — honest uncertainty, never a
                # fabricated outcome. The bench stream carries the state
                # change (D4: the event pins the run's binding document;
                # the worker error itself rides the gateway log), and the
                # drain continues. The emit is itself guarded: a raising
                # call inside the poison handler would defeat the guard.
                store.put_run_state(run_id, bench_id, "terminal", self._now_iso())
                _LOG.error(
                    "run_worker poison run_id=%s error=%s: %s",
                    run_id, type(error).__name__, error,
                )
                try:
                    append_bench_event(
                        store, "run_changed", bench_id, run_id, None,
                        keep=self._emit_keep, now_iso=self._now_iso,
                    )
                except Exception:
                    _LOG.exception(
                        "run_worker poison emit failed run_id=%s", run_id
                    )
            else:
                store.put_run_state(run_id, bench_id, "terminal", self._now_iso())
                self._emit_completion(store, coordinator, run_id, bench_id)
            finally:
                self._done += 1
                self._queue.task_done()

    def _emit_completion(
        self, store: Store, coordinator: Any, run_id: str, bench_id: str
    ) -> None:
        """Task 6: honest drain-side bench events, appended on the worker's
        own (thread-affine) store. The durable terminal record decides the
        ``trip`` emission; the coordinator's monitor retention counter
        decides the single ``evidence_gap`` — neither is inferred from the
        in-memory return value."""
        run = store.get_run(run_id)
        terminal = run["terminal"] if run is not None else None
        append_bench_event(store, "run_changed", bench_id, run_id, None,
                           keep=self._emit_keep, now_iso=self._now_iso)
        if terminal is not None and str(terminal.get("outcome")) == "tripped":
            append_bench_event(store, "trip", bench_id, run_id, None,
                               keep=self._emit_keep, now_iso=self._now_iso)
        monitor = getattr(coordinator, "monitor", None)
        failures = int(getattr(monitor, "retention_failures", 0)) if monitor else 0
        if failures > 0:
            _LOG.warning(
                "evidence_gap run_id=%s retention_failures=%d", run_id, failures
            )
            append_bench_event(store, "evidence_gap", bench_id, run_id, None,
                               keep=self._emit_keep, now_iso=self._now_iso)
