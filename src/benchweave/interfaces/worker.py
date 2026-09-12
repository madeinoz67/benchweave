"""Single run worker: drains accepted runs one at a time (one active
controlling procedure), owns coordinator execution and state projection.

The worker is the queue half of the run seam: ``Operations.run_start``
accepts and enqueues; this thread executes. Per run it projects the queue
state (``accepted`` → ``running`` → ``terminal``) into ``run_states`` and
delegates execution to a coordinator built by ``build_run`` — Task 8 wires
the real ``RunCoordinator`` (spooling the binding-ref documents into a
run-scoped tmp dir, admitting them, constructing the sim plugins, hooking
retention); Task 5 tests inject a fake with the same public API.

sqlite3 connections are thread-affine, so the worker re-opens the store's
database on its own connection (WAL plus the store's busy timeout keep the
two writers serialised safely).
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any

from benchweave.content.store import ContentStore
from benchweave.control.clocking import SystemClock
from benchweave.state.store import Store


class RunWorker:
    """Drains the accepted-run queue FIFO; exactly one run is ever active."""

    def __init__(
        self,
        store: Store,
        content: ContentStore,
        *,
        build_run: Callable[[str, str, dict[str, Any]], Any],
        now_iso: Callable[[], str] | None = None,
    ) -> None:
        self._store = store
        # Content is the landed constructor surface; Task 8's build_run
        # wiring closes over it (spooling reads documents from the store).
        self._content = content
        self._build_run = build_run
        self._now_iso = now_iso if now_iso is not None else SystemClock().now_iso
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
        """Wait for the queue to drain, then for the thread to exit."""
        self._queue.join()
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
        while True:
            try:
                run_id, principal_id, binding_ref, bench_id = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._stopping.is_set():
                    return  # queue drained; stop cleanly
                continue
            try:
                store.put_run_state(run_id, bench_id, "running", self._now_iso())
                coordinator = self._build_run(run_id, principal_id, binding_ref)
                with self._active_lock:
                    self._active = (run_id, coordinator)
                try:
                    coordinator.start_run(run_id, principal_id)
                finally:
                    with self._active_lock:
                        self._active = None
            except BaseException:
                store.put_run_state(run_id, bench_id, "terminal", self._now_iso())
                raise
            else:
                store.put_run_state(run_id, bench_id, "terminal", self._now_iso())
            finally:
                self._done += 1
                self._queue.task_done()
