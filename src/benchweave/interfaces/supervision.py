"""The daemon-side supervision surface (issue #422 increment 3).

The design authority is
``.claude/deep-review/2026-10-08-issue422-inc2-supervision-design.md``
§3 (stop semantics) and §4 (arming). This module is mounted by
:func:`benchweave.interfaces.app.create_app` ONLY when the composition is
armed — the ``serve`` CLI sets the flag before ``uvicorn.run``; ``demo``
and ``evidence`` boot the real lifespan with the flag unset and inherit
NO supervision surface (record §3.2's F4 fold: no doorbell, no pidfile,
no signal handler on those compositions).

What runs where (the F12 fold, load-bearing): the doorbell poll and the
SIGTERM handler only ever SCHEDULE the decision — an asyncio task on the
serving loop. The decision and the protective wait run ON the loop,
never inside the handler, so serving, the doorbell poll and further
signals stay live for the whole commissioned window.

No rung of the stop ladder writes a terminal record and none is an
outcome authority (CTL-11): the coordinator's §5 ending and the scoped
stop-time sweep are the only writers, and rung 2 QUOTES the
coordinator's terminal record verbatim with its source named.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal as signal_module
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from benchweave import supervision
from benchweave.interfaces.operations import LIVE_RUN_STATES, append_bench_event
from benchweave.state.store import Store

if TYPE_CHECKING:
    from benchweave.content.store import ContentStore
    from benchweave.interfaces.operations import Operations
    from benchweave.interfaces.worker import RunWorker

_LOG = logging.getLogger(__name__)

#: The doorbell poll cadence bound (record §3.2 step 3: ≤ 1 s).
STOP_POLL_SECONDS = 1.0

#: The protective wait's own poll cadence (terminal-record observation).
TERMINAL_POLL_SECONDS = 0.2

#: The era reason the scoped stop sweep writes into interrupted records
#: (record §3.3 step 3).
STOP_ERA_REASON = "gateway stop: run was never started"

#: The run_changed log reason for a protective-stop cancel (F15 fold: the
#: store can distinguish an operator REST cancel from a protective-stop
#: cancel; the closed event def has no free-form channel — the reason
#: rides the gateway log, the recovery-emit precedent).
PROTECTIVE_CANCEL_REASON = "gateway_supervision_protective_stop"

#: The principal a protective stop cancels under (F15 fold).
SUPERVISION_PRINCIPAL = "gateway-supervision"


def _parse_wall(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class StopWindow:
    """The stop decision's view of live state, read under the write gate
    AFTER the stop flag is set (§3.1's set-then-check TOCTOU close)."""

    live_runs: list[dict[str, Any]] = field(default_factory=list)
    decided_wall: str = ""


class SupervisionSurface:
    """One armed gateway's supervision state machine (§3.3's three paths).

    Constructed by ``create_app`` when armed; the lifespan calls
    :meth:`startup` after the hold is acquired (the pidfile lands between
    hold-acquire and admission — §2.1's HOLD-ACQUIRED readiness), and
    :meth:`shutdown` before the worker drain.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        gateway_id: str,
        store: Store,
        content: ContentStore,
        worker: RunWorker,
        operations: Operations,
        gate: Any,
        fixtures_dir: Path,
        contracts: Path,
        now_iso: Any,
        emit_keep: int | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.gateway_id = gateway_id
        self._store = store
        self._content = content
        self._worker = worker
        self._operations = operations
        self._gate = gate
        self._fixtures_dir = fixtures_dir
        self._contracts = contracts
        self._now_iso = now_iso
        # The bench-event retention window (the worker's own discipline:
        # limits["max_page_size"] * 10) for the sweep's run_changed emits.
        self._emit_keep = emit_keep
        self._server: Any = None  # uvicorn.Server, bound by serve before run
        self._loop: asyncio.AbstractEventLoop | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._previous_handler: Any = None
        self._decision_task: asyncio.Task[None] | None = None
        self._decided = False
        self._foreign_seen: set[tuple[int, int]] = set()
        # The SSE close event (F2 fold: the stop decision closes live
        # streams so the drain cannot hang on the Events view forever).
        self.streams_closing = asyncio.Event()

    # -- serve wiring ----------------------------------------------------------

    @property
    def store(self) -> Store:
        """The composition's store (serve derives its graceful timeout from
        the commissioned ceilings the same way `service install` does)."""
        return self._store

    @property
    def content(self) -> ContentStore:
        """The composition's content store (the ceilings' document source)."""
        return self._content

    def bind_server(self, server: Any) -> None:
        """serve binds the uvicorn Server before ``run`` so the decision
        can trigger the graceful shutdown DIRECTLY (``should_exit``) —
        never by re-raising into uvicorn's captured-signal replay (F3
        fold: the replay ends the process by signal 15 after a clean
        drain, failing the exit-0 contract)."""
        self._server = server

    def log_destination(self) -> str:
        """Where this daemon's stderr bytes land (§2.3): ``start`` sets
        ``BENCHWEAVE_LOG_DESTINATION`` to the ``<dir>.log`` path in the
        child env; under systemd the unit sets no StandardError so the
        journal collects them (``logs`` in increment 4 derives from this
        field); foreground serve keeps the terminal."""
        return os.environ.get("BENCHWEAVE_LOG_DESTINATION", "stderr")

    # -- lifecycle mounting ----------------------------------------------------

    def write_pidfile(self) -> None:
        supervision.write_pidfile(
            self.db_path,
            gateway_id=self.gateway_id,
            log_destination=self.log_destination(),
        )

    async def startup(self, app: Any) -> None:
        """Mount the doorbell: the ≤1 s poll task and (POSIX, main thread
        only — handlers cannot be installed from a serving thread; the
        file poll is the doorbell of record either way) the SIGTERM
        handler that captures uvicorn's for delegation context."""
        self._loop = asyncio.get_running_loop()
        self._poll_task = asyncio.get_running_loop().create_task(self._poll_loop())
        if (
            sys.platform != "win32"
            and threading.current_thread() is threading.main_thread()
        ):
            captured = signal_module.getsignal(signal_module.SIGTERM)
            self._previous_handler = captured

            def _handler(signum: int, frame: Any) -> None:
                # F12 fold: only SCHEDULE — never run the decision in the
                # handler (the protective wait would freeze the loop).
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(self._schedule_bare_decision)

            signal_module.signal(signal_module.SIGTERM, _handler)

    async def shutdown(self) -> None:
        """Unmount the doorbell (the lifespan's pre-drain step)."""
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            except Exception:
                _LOG.exception("supervision poll loop ended with an error")
            self._poll_task = None
        if self._previous_handler is not None:
            signal_module.signal(signal_module.SIGTERM, self._previous_handler)
            self._previous_handler = None

    def remove_pidfile(self) -> None:
        supervision.remove_pidfile(self.db_path)

    # -- the doorbell ----------------------------------------------------------

    def _schedule_bare_decision(self) -> None:
        if self._decided:
            return
        self._decision_task = asyncio.ensure_future(
            self._run_decision(None, trigger="signal")
        )

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(STOP_POLL_SECONDS)
            task = self.poll_once()
            if task is not None:
                await task

    def poll_once(self) -> asyncio.Task[None] | None:
        """ONE doorbell poll (the poll loop's body; the deterministic
        seam the foreign-owner arm drives). Returns the scheduled
        decision task, or None when there was nothing to consume.

        A verdict-shaped file (already consumed) is a no-op: the protocol
        is single-shot by construction. A foreign-owned request is NOT
        consumed (§3.2 step 4) — the typed line answers on the gateway
        log and the file is left exactly as it is."""
        record = supervision.read_stop_file(self.db_path)
        if record is None or "status" in record:
            return None
        path = supervision.stop_path(self.db_path)
        if not supervision.request_owner_ok(path):
            stat = os.stat(path)
            key = (stat.st_uid, stat.st_mtime_ns)
            if key not in self._foreign_seen:
                self._foreign_seen.add(key)
                _LOG.warning(
                    "%s request file %s is owned by uid %s, not this gateway "
                    "(uid %s); not consumed — nothing acts on it",
                    supervision.STOP_FOREIGN_OWNER,
                    path,
                    stat.st_uid,
                    os.geteuid(),
                )
            return None
        if self._decided:
            return None
        return asyncio.ensure_future(self._run_decision(record, trigger="file"))

    # -- the decision (§3.3) ---------------------------------------------------

    def open_stop_window(self) -> StopWindow:
        """§3.1's set-then-check fragment, under the write gate the
        transports already hold for mutating calls: FIRST the stop flag
        (a ``run_start`` arriving after it refuses typed
        ``stop_in_progress:``), THEN the live-state read — so a run
        accepted mid-decision can never be silently abandoned under an
        accepted verdict (F4 fold; arm L13)."""
        with self._gate:
            self._operations.begin_stop()
            live: list[dict[str, Any]] = []
            offset = 0
            while True:
                items, has_more = self._store.list_benches(limit=1000, offset=offset)
                for bench in items:
                    for row in self._store.list_run_states(str(bench["bench_id"])):
                        if row["state"] in LIVE_RUN_STATES:
                            live.append(
                                {
                                    "run_id": str(row["run_id"]),
                                    "bench_id": str(bench["bench_id"]),
                                    "state": str(row["state"]),
                                }
                            )
                if not has_more:
                    break
                offset += len(items)
        return StopWindow(live_runs=live, decided_wall=self._now_iso())

    def reset_stop_window(self) -> None:
        """Clear the stop flag WITHOUT acting (the L13 arm's round reset;
        production never resets — the flag's life is the stop's)."""
        self._operations.end_stop()

    async def _run_decision(self, request: dict[str, Any] | None, *, trigger: str
                            ) -> None:
        if self._decided:
            return
        self._decided = True
        # The FILE is the mode carrier whichever trigger won the race: a
        # signal landing before the poll still acts on an unconsumed
        # request's mode (and writes its verdict — the polling CLI learns
        # the outcome); a file already consumed (a verdict) or absent is a
        # BARE decision (§3.4's three-way on live state).
        file_record = supervision.read_stop_file(self.db_path)
        if file_record is not None and "status" not in file_record:
            request = file_record
        mode = "plain" if request is None else str(request.get("mode", "plain"))
        window = self.open_stop_window()
        _LOG.info(
            "supervision stop decision trigger=%s mode=%s live_runs=%d",
            trigger, mode, len(window.live_runs),
        )
        if mode != "protective":
            if window.live_runs:
                states = {row["run_id"]: row["state"] for row in window.live_runs}
                if request is not None:
                    supervision.atomic_write_json(
                        supervision.stop_path(self.db_path),
                        {
                            "schema": supervision.STOP_SCHEMA,
                            "status": "refused",
                            "reason": "run_active",
                            "mode": "plain",
                            "run_ids": sorted(states),
                            "states": states,
                            "decided_wall": self._now_iso(),
                            "gateway_pid": os.getpid(),
                        },
                    )
                _LOG.warning(
                    "%s runs %s are live (%s); serving continues — nothing "
                    "was stopped, nothing was recorded",
                    supervision.STOP_REFUSED_RUN_ACTIVE,
                    sorted(states), states,
                )
                self._decided = False  # a later stop may be protective
                return
            # Plain idle: accept and drain through the in-tree lifespan.
            if request is not None:
                supervision.atomic_write_json(
                    supervision.stop_path(self.db_path),
                    {
                        "schema": supervision.STOP_SCHEMA,
                        "status": "accepted",
                        "mode": "plain",
                        "run_ids": [],
                        "decided_wall": self._now_iso(),
                        "gateway_pid": os.getpid(),
                    },
                )
            await self._graceful_exit()
            return

        # Protective (§3.3): route the existing engine through its seams.
        run_ids = sorted(row["run_id"] for row in window.live_runs)
        deadline = self._protective_deadline(window.live_runs)
        verdict: dict[str, Any] = {
            "schema": supervision.STOP_SCHEMA,
            "status": "accepted",
            "mode": "protective",
            "run_ids": run_ids,
            "protective_deadline_wall": deadline,
            "decided_wall": self._now_iso(),
            "gateway_pid": os.getpid(),
        }
        supervision.atomic_write_json(supervision.stop_path(self.db_path), verdict)
        # Close live SSE streams FIRST (F2): the drain must not hang on
        # the Events view while the protective wait runs.
        self.streams_closing.set()
        # F1 ordering: pickup gate BEFORE cancel, sweep only after the
        # active run is terminal AND the worker thread has exited under
        # the gate.
        self._worker.gate_pickup()
        if run_ids:
            verdict["protective_cancel"] = {"run_ids": run_ids}
            supervision.atomic_write_json(supervision.stop_path(self.db_path), verdict)
        for row in window.live_runs:
            if row["state"] in ("running", "protecting"):
                self._worker.cancel(row["run_id"], SUPERVISION_PRINCIPAL)
                _LOG.info(
                    "run_cancel run_id=%s reason=%s principal=%s (protective stop)",
                    row["run_id"], PROTECTIVE_CANCEL_REASON, SUPERVISION_PRINCIPAL,
                )
                self._emit_run_changed(row["run_id"], row["bench_id"])
        # Wait terminal to the verdict-stated deadline (numeric authority
        # stays in the daemon — the commissioned window arithmetic).
        deadline_moment = _parse_wall(deadline)
        if deadline_moment is None:
            deadline_moment = datetime.now().astimezone()
        # ONLY the active runs are waited (F1's ordering): queued ghosts
        # are the sweep's, and the sweep runs after this wait — waiting a
        # ghost here would be a deadlock by construction.
        observed: list[dict[str, Any]] = []
        pending = [
            row for row in window.live_runs
            if row["state"] in ("running", "protecting")
        ]
        while pending:
            await asyncio.sleep(TERMINAL_POLL_SECONDS)
            with self._gate:
                still_pending = [
                    row for row in pending
                    if self._run_is_not_terminal(row["run_id"])
                ]
            for row in [r for r in pending if r not in still_pending]:
                quoted = self._quote_terminal(row["run_id"])
                if quoted is not None:
                    observed.append(quoted)
                    verdict["terminal_observed"] = observed
                    supervision.atomic_write_json(
                        supervision.stop_path(self.db_path), verdict
                    )
            pending = still_pending
            if not pending:
                break
            if datetime.now().astimezone() >= deadline_moment:
                # The commissioned window closed with a non-terminal run:
                # rung 3 belongs to the CLI (or systemd's TimeoutStopSec).
                # This process does NOT drain over a possibly-wedged
                # writer — it stays up for the external kill and says so.
                verdict["deadline_exceeded"] = True
                supervision.atomic_write_json(
                    supervision.stop_path(self.db_path), verdict
                )
                _LOG.error(
                    "supervision_protective_deadline_exceeded: %s did not "
                    "terminalize by %s; staying up for the external "
                    "escalation rung (CLI SIGKILL / TimeoutStopSec)",
                    sorted(row["run_id"] for row in pending), deadline,
                )
                return
        # The scoped sweep (F1/F13): queued ghosts only, after the
        # confirmed gate-held queue state.
        sweep_note: str | None = None
        if not self._worker.wait_gated_exit(timeout=15.0):
            _LOG.error(
                "supervision pickup gate: the run worker did not exit "
                "within bounds; queued runs are left for next-boot recovery"
            )
            sweep_note = "worker did not exit under the pickup gate"
        else:
            interrupted, skipped = self._stop_time_sweep()
            if skipped:
                sweep_note = (
                    f"{len(interrupted) and ''}recovery_skipped: lattice failed "
                    "admission; queued runs left for next-boot recovery"
                )
        if sweep_note is not None:
            verdict["sweep_disclosure"] = sweep_note
            supervision.atomic_write_json(
                supervision.stop_path(self.db_path), verdict
            )
        await self._graceful_exit()

    async def _graceful_exit(self) -> None:
        """Trigger the in-tree lifespan drain: close SSE, then set the
        bound server's ``should_exit`` DIRECTLY (never the captured-
        signal replay — F3)."""
        self.streams_closing.set()
        if self._server is not None:
            self._server.should_exit = True
        else:
            _LOG.error(
                "supervision: no uvicorn server was bound; cannot trigger "
                "the graceful shutdown from the decision path"
            )

    # -- protective helpers ------------------------------------------------------

    def _protective_deadline(self, live: list[dict[str, Any]]) -> str:
        """The commissioned window's end (CTL-10/STO-4 arithmetic: run
        lease expiry where a live lease exists, else acceptance +
        max_body_ms + max_protection_ms from the run's binding/procedure
        documents — never an ambient guess). Unresolvable runs contribute
        nothing; an empty result is the decided-now boundary (the wait
        loop then defers to the external rung immediately, disclosed)."""
        best: datetime | None = None
        for row in live:
            moment = self._run_window_end(row["run_id"])
            if moment is not None and (best is None or moment > best):
                best = moment
        if best is None:
            return str(self._now_iso())
        return str(best.isoformat().replace("+00:00", "Z"))

    def _run_window_end(self, run_id: str) -> datetime | None:
        # The materialized arithmetic first: the run lease's expiry IS
        # acceptance + body + protection (STO-4).
        for bench in self._store.list_benches(limit=1000, offset=0)[0]:
            for lease in self._store.list_leases(str(bench["bench_id"])):
                if (
                    lease.state == "active"
                    and lease.holder == f"run:{run_id}"
                ):
                    moment = _parse_wall(str(lease.expires_at))
                    if moment is not None:
                        return moment
        # Documents fallback (queued runs hold no lease yet). The content
        # store's envelope wraps the document under "content".
        run = self._store.get_run(run_id)
        if run is None:
            return None
        started = _parse_wall(str(run["started_at"]))
        binding_pin = run["binding"].get("sha256", "")
        envelope = self._content.get_document(str(binding_pin))
        document = envelope.get("content") if isinstance(envelope, dict) else None
        if started is None or not isinstance(document, dict):
            return None
        procedure_pin = document.get("procedure")
        if not isinstance(procedure_pin, dict):
            return None
        procedure_envelope = self._content.get_document(
            str(procedure_pin.get("sha256", ""))
        )
        procedure = (
            procedure_envelope.get("content")
            if isinstance(procedure_envelope, dict) else None
        )
        if not isinstance(procedure, dict):
            return None
        body = procedure.get("max_body_ms")
        protection = procedure.get("max_protection_ms")
        if (
            not isinstance(body, int) or isinstance(body, bool)
            or not isinstance(protection, int) or isinstance(protection, bool)
        ):
            return None
        from datetime import timedelta

        return started + timedelta(milliseconds=body + protection)

    def _run_is_not_terminal(self, run_id: str) -> bool:
        run = self._store.get_run(run_id)
        return run is not None and run["terminal"] is None

    def _quote_terminal(self, run_id: str) -> dict[str, Any] | None:
        """Rung 2's observation (F1 fold): QUOTE the coordinator's
        terminal record verbatim with its source named — an observation,
        never an outcome authority."""
        run = self._store.get_run(run_id)
        if run is None or run["terminal"] is None:
            return None
        record = run["terminal"]
        return {
            "run_id": run_id,
            "outcome": record.get("body_outcome"),
            "safe_state": record.get("safe_state"),
            "source": "coordinator_terminal_record",
        }

    def _emit_run_changed(self, run_id: str, bench_id: str) -> None:
        try:
            append_bench_event(
                self._store, "run_changed", bench_id, run_id, None,
                keep=self._emit_keep, now_iso=self._now_iso,
            )
        except Exception:
            _LOG.exception("supervision run_changed emit failed run_id=%s", run_id)

    def _stop_time_sweep(self) -> tuple[list[str], bool]:
        """The scoped sweep (§3.3 step 3): finalize queued ghosts
        (`accepted`, never-started) as `interrupted` with the stop era
        reason — the #156 queued-ghost leg ONLY (reclaim/reconcile legs
        skipped at stop time, F13). Returns (interrupted ids, skipped):
        skipped=True means the lattice failed admission and every queued
        run is left for next-boot recovery (F10's disclosure)."""
        from benchweave.control.clocking import SystemClock
        from benchweave.control.coordinator import RunCoordinator
        from benchweave.interfaces.app import _recovery_documents

        docs = _recovery_documents(
            self._fixtures_dir, now_wall=self._now_iso(), contracts=self._contracts
        )
        if docs is None:
            _LOG.error(
                "recovery_skipped: stop-time lattice failed admission; queued "
                "runs are left for next-boot recovery (disclosed)"
            )
            return [], True
        coordinator = RunCoordinator(
            self._store, {}, SystemClock(), SystemClock(), docs,
            contracts=self._contracts,
        )
        bench_id = str(docs.bench["id"])
        with self._gate:
            interrupted = coordinator.interrupt_queued_at_stop(self._now_iso())
            for run_id in interrupted:
                self._store.put_run_state(run_id, bench_id, "terminal", self._now_iso())
                _LOG.info(
                    "run_changed (stop sweep) run_id=%s reason=%s",
                    run_id, STOP_ERA_REASON,
                )
                append_bench_event(
                    self._store, "run_changed", bench_id, run_id, None,
                    keep=self._emit_keep, now_iso=self._now_iso,
                )
        if interrupted:
            _LOG.info(
                "supervision stop sweep interrupted %d queued run(s): %s",
                len(interrupted), interrupted,
            )
        return interrupted, False
