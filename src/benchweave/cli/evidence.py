"""Seeded journey volume evidence — the PRD §3 path as a generator (Task 7).

``benchweave.cli.demo`` proves the §3 demonstration journey live, one drive
at a time; this module makes the same path a VOLUME generator: ONE ephemeral
gateway (the demo fresh-install idiom — scratch directory, anti-coordinate
gate, loopback uvicorn, every surface labelled ``SIMULATION``) drives
``count`` CONSECUTIVE seeded journey runs, and every run's evidence is
checked INLINE before the next run starts. Any inconsistency — an outcome
that is not ``passed``, a durable record missing or disagreeing with the
wire, an evidence digest that does not resolve, a dispatch occurrence that
appears twice — aborts generation LOUDLY (:class:`EvidenceError`); the
per-run records written so far stay on disk as truthful partial evidence,
but ``summary.json`` is never written for an incomplete generation.

Per-run derivation: run N (1-based) drives under seed ``seed + N``, and the
seed names the run's §9 identity — the fixture lattice's binding document
stored as a variant whose document-level ``request_id`` is
``req-volume-{seed}`` (the journey fault legs' second-binding idiom; the
pinned procedure/bench/policy/commissioning digests are untouched). The
drive itself is ``benchweave.cli.demo``'s one-REST-path discipline:
advisory ``run-checks`` preflight (validity + the CANONICAL generation the
fence reads — never a literal), ``run_start`` with 202 semantics, the §9
``run_find`` cross-check, a bounded poll to terminal.

Drive-parity note (disclosed, deliberate): the test-suite ``journey_run``
additionally retrieves the SAME run over MCP while it is in flight
(``stg_v1_run_find``/``stg_v1_run_get``) and checks the terminal projection
equal over both transports. This CLI drive is REST-only — the demo pattern
it re-implements — because the volume leg's question is per-run evidence
consistency at scale, not cross-transport parity (the parity suite owns
that). The 202-state check (``accepted``) and the §9 cross-check ARE
carried over from the journey drive.

The consistency gate (per run, inline, aborting):
1. wire truth — ``terminal`` / ``passed`` / ``verified`` and a closed
   terminal-record ref carrying a sha256;
2. durable truth — ``Store.get_run`` has a terminal record whose verdicts
   match the wire (the record document is deliberately not REST-servable);
3. digest identity — the wire ref's sha256 recomputed over the durable
   record matches (the digest names THIS record);
4. evidence resolution — every document evidence ref in the record's
   ``evidence_refs`` resolves in the ContentStore, and the ``events:{run}``
   digest is RECOMPUTED over the durable ``run:{id}`` stream and compared;
5. the dispatch oracle — exactly one durable event per dispatched device
   operation (``invoke``/``read``/``write``), and exactly
   :data:`EXPECTED_DISPATCHES` of them (the healthy-body pin the journey
   suite cites from ``test_procedures.test_worst_case_bound_exact``).
Because the gate aborts on any duplicate, a WRITTEN summary always carries
``duplicate_dispatch_total == 0`` — the field is kept so the retained
evidence states the number the PRD's no-duplicate-dispatch claim needs,
rather than leaving it to be inferred.

Host disclosure: the summary records the generating platform (system,
release, machine, python) — deliberately NOT the hostname; committed
evidence needs reproduction context, not a machine name.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import click

from benchweave.cli.atrest import DB_NAME
from benchweave.cli.client import GatewayClient, GatewayError
from benchweave.cli.demo import (
    BINDING_FILE,
    DEFAULT_LIMITS,
    DEFAULT_TIMEOUT_S,
    SIMULATION_LABEL,
    DemoError,
    _boot,
    held_stores,
    poll_to_terminal,
    resolve_fixtures,
)
from benchweave.cli.output import emit
from benchweave.performance import (
    ACCEPTANCE_TARGET_P95_MS,
    LABEL_ACCEPTANCE,
    LABEL_READS,
    LABEL_STRESS,
    READS_TARGET_P95_MS,
    PerformanceError,
    TimingResult,
    measure_acceptance,
    measure_reads,
    measure_stress,
)

if TYPE_CHECKING:
    import uvicorn

    from benchweave.content.store import ContentStore
    from benchweave.state.store import Store

#: The ephemeral gateway identity (visible in status/refusals).
EVIDENCE_GATEWAY_ID = "gw-cli-evidence"
#: The principal the generator's own ephemeral token is issued to.
EVIDENCE_PRINCIPAL = "benchweave-evidence"
#: Base seed the plan's Step-4 invocation pins into the retained evidence.
DEFAULT_SEED = 20260914
#: Default run count (the PRD volume leg).
DEFAULT_COUNT = 100
#: Step kinds that dispatch to a device — the executor's operation kinds
#: (``delay``/``sample``/``assert``/``if``/``repeat`` never reach a plugin;
#: executor.py's "one dispatch per occurrence, ever"). Re-declared here
#: because the journey suite's table is a test file, not a library.
DISPATCH_KINDS = frozenset({"invoke", "read", "write"})
#: A healthy fixture body dispatches configure, enable, note, model,
#: measure and remeasure x3 — eight device operations (the occurrence pin
#: ``test_procedures.test_worst_case_bound_exact`` enumerates, the journey
#: suite's ``LEG_OCCURRENCES`` cites).
EXPECTED_DISPATCHES = 8


class EvidenceError(RuntimeError):
    """A truthful generation failure (the CLI shows it and exits non-zero)."""


@dataclass(frozen=True)
class AppHandles:
    """One ephemeral gateway's drive handles.

    The drive itself is wire-only (``client`` — the demo rule); ``store``
    and ``content`` exist for the per-run consistency gate, which reads the
    DURABLE record and event stream the wire only references. ``timeout_s``
    bounds each run's poll to terminal. ``token`` is the ephemeral
    principal's bearer token (Task 9: the timing measurements build their
    own per-observer clients from base_url + token, not this one client).
    """

    client: GatewayClient
    store: Store
    content: ContentStore
    fixtures: Path
    base_url: str
    token: str
    timeout_s: float


@dataclass(frozen=True)
class RunRecord:
    """What one seeded journey run leaves behind — lean by contract.

    ids, digests, outcome and timings only (the brief's rule); the full
    terminal record and event stream stay in the (torn-down) store — their
    digests are what the retained evidence carries.
    """

    seed: int
    request_id: str
    run_id: str
    bench_id: str
    state: str
    outcome: str | None
    safe_state: str | None
    terminal_sha256: str
    binding_sha256: str
    events_digest: str
    dispatch_occurrences: int
    duplicate_dispatches: int
    started_at: str
    duration_s: float

    def to_dict(self) -> dict[str, Any]:
        """The persisted per-run record (round-trips through JSON)."""
        return {
            "seed": self.seed,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "bench_id": self.bench_id,
            "state": self.state,
            "outcome": self.outcome,
            "safe_state": self.safe_state,
            "terminal_sha256": self.terminal_sha256,
            "binding_sha256": self.binding_sha256,
            "events_digest": self.events_digest,
            "dispatch_occurrences": self.dispatch_occurrences,
            "started_at": self.started_at,
            "duration_s": self.duration_s,
        }


@dataclass(frozen=True)
class _Gate:
    """What the consistency gate verified for one run."""

    terminal_sha256: str
    events_digest: str
    dispatch_occurrences: int
    duplicate_dispatches: int


# --- clocks and host disclosure ---------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _now_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


def _host_disclosure() -> dict[str, str]:
    """The generating platform (no hostname — see the module docstring)."""
    info = platform.uname()
    return {
        "system": info.system,
        "release": info.release,
        "machine": info.machine,
        "python": platform.python_version(),
    }


# --- the drive ---------------------------------------------------------------------


def _binding_variant(
    content: ContentStore, fixtures: Path, request_id: str
) -> tuple[dict[str, str], dict[str, Any]]:
    """Store one binding variant under a fresh document-level request id.

    The journey fault legs' second-binding idiom: the fixture binding
    document with ONLY its ``request_id`` rewritten (the §9 acceptance key
    — the coordinator dedups on the binding document's own request id), so
    consecutive runs are distinct journeys over the same pinned lattice.
    """
    document: dict[str, Any] = json.loads((fixtures / BINDING_FILE).read_bytes())
    document["request_id"] = request_id
    raw = json.dumps(document, indent=2).encode()
    sha = hashlib.sha256(raw).hexdigest()
    content.put_document(raw, sha, document, "urn:stg:binding", _now_iso())
    version = str(document.get("version") or document.get("contract_version", "1"))
    return {"id": request_id, "version": version, "sha256": sha}, document


def drive_journey(handles: AppHandles, *, seed: int) -> RunRecord:
    """One seeded journey run over the ephemeral gateway, gate-checked.

    The demo drive path tightened to the volume leg's needs: preflight
    validity + the canonical generation (never a literal — no ``Admitted``
    exists to go stale here, but the discipline is the same), ``run_start``
    with 202 semantics, the §9 cross-check, bounded poll to terminal, then
    the full inline consistency gate (:func:`_consistency`).
    """
    started_wall = _now_iso()
    started = time.monotonic()
    request_id = f"req-volume-{seed}"
    ref, document = _binding_variant(handles.content, handles.fixtures, request_id)
    bench_id = str(document["bench"]["id"])
    client = handles.client

    preflight = client.run_check(bench_id, binding_ref=ref)
    if preflight.get("valid") is not True:
        raise EvidenceError(
            f"seed {seed} ({request_id}): run_check preflight rejected the binding — "
            f"{preflight.get('findings')!r}"
        )
    generation = preflight.get("generation")
    if not isinstance(generation, int):
        raise EvidenceError(
            f"seed {seed} ({request_id}): preflight carried no canonical generation"
        )
    started_run = client.run_start(
        bench_id,
        request_id=request_id,
        binding_ref=ref,
        expected_generation=generation,
    )
    run_id = str(started_run["run_id"])
    if started_run.get("state") != "accepted":
        raise EvidenceError(
            f"seed {seed} ({request_id}): run_start returned state "
            f"{started_run.get('state')!r}, not 'accepted'"
        )
    found = client.run_find(request_id)
    if str(found.get("run_id")) != run_id:
        raise EvidenceError(
            f"seed {seed} ({request_id}): run_find resolved "
            f"{found.get('run_id')!r}, not the started run {run_id!r}"
        )
    try:
        final = poll_to_terminal(client, run_id, timeout_s=handles.timeout_s)
    except DemoError as error:
        raise EvidenceError(f"seed {seed} ({request_id}): {error}") from error

    gate = _consistency(handles, seed=seed, run_id=run_id, final=final)
    return RunRecord(
        seed=seed,
        request_id=request_id,
        run_id=run_id,
        bench_id=bench_id,
        state=str(final["state"]),
        outcome=final.get("outcome"),
        safe_state=final.get("safe_state"),
        terminal_sha256=gate.terminal_sha256,
        binding_sha256=str(ref["sha256"]),
        events_digest=gate.events_digest,
        dispatch_occurrences=gate.dispatch_occurrences,
        duplicate_dispatches=gate.duplicate_dispatches,
        started_at=started_wall,
        duration_s=round(time.monotonic() - started, 3),
    )


# --- the per-run consistency gate ---------------------------------------------------


def _abort(seed: int, run_id: str, detail: str) -> NoReturn:
    """Raise the loud generation abort (one message shape for the whole gate)."""
    raise EvidenceError(f"seed {seed} run {run_id}: {detail}")


def _consistency(
    handles: AppHandles,
    *,
    seed: int,
    run_id: str,
    final: dict[str, Any],
) -> _Gate:
    """The volume leg's own assertions — EVERY run, inline, aborting loudly.

    See the module docstring for the five checks. ``final`` is the terminal
    wire projection; everything else reads the durable store the wire only
    references.
    """
    from benchweave.control.executor import canonical_json

    # 1. Wire truth.
    if final.get("state") != "terminal":
        _abort(seed, run_id, f"final state is {final.get('state')!r}, not 'terminal'")
    if final.get("outcome") != "passed":
        _abort(seed, run_id, f"outcome is {final.get('outcome')!r}, not 'passed'")
    if final.get("safe_state") != "verified":
        _abort(seed, run_id, f"safe_state is {final.get('safe_state')!r}, not 'verified'")
    wire_ref = final.get("terminal_record")
    if not (isinstance(wire_ref, dict) and wire_ref.get("sha256")):
        _abort(seed, run_id, "the wire carried no closed terminal-record ref")
    terminal_sha = str(wire_ref["sha256"])

    # 2. Durable truth: the record exists and agrees with the wire.
    run = handles.store.get_run(run_id)
    if run is None:
        _abort(seed, run_id, "no durable run row — the wire served a run the store lacks")
    terminal = run["terminal"]
    if not isinstance(terminal, dict):
        _abort(seed, run_id, "no durable terminal record behind a passed wire outcome")
    if str(terminal.get("run_id")) != run_id:
        _abort(seed, run_id, f"durable record names run {terminal.get('run_id')!r}")
    if str(terminal.get("outcome")) != "passed" or str(terminal.get("safe_state")) != "verified":
        _abort(
            seed,
            run_id,
            f"durable verdicts {terminal.get('outcome')!r}/{terminal.get('safe_state')!r} "
            "disagree with the wire",
        )

    # 3. Digest identity: the wire digest names THIS durable record (the
    # operations seam's own serialization, recomputed store-side).
    expected_sha = hashlib.sha256(
        json.dumps(terminal, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if terminal_sha != expected_sha:
        _abort(
            seed,
            run_id,
            f"terminal-record digest mismatch: wire {terminal_sha[:16]}… vs durable "
            f"{expected_sha[:16]}…",
        )

    # 4. Evidence resolution: every document ref resolves in the content
    # store; the events digest is recomputed over the durable stream.
    events = handles.store.read_events(f"run:{run_id}")
    events_digest = ""
    evidence_refs = terminal.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        _abort(seed, run_id, "the durable record carries no evidence refs")
    for evidence_ref in evidence_refs:
        if not isinstance(evidence_ref, dict):
            _abort(seed, run_id, f"malformed evidence ref {evidence_ref!r}")
        ref_id = str(evidence_ref.get("id", ""))
        ref_sha = str(evidence_ref.get("sha256", ""))
        if ref_id.startswith("events:"):
            actual = hashlib.sha256(canonical_json(events).encode("utf-8")).hexdigest()
            if actual != ref_sha:
                _abort(
                    seed,
                    run_id,
                    f"events digest mismatch for {ref_id}: recorded {ref_sha[:16]}… vs "
                    f"recomputed {actual[:16]}…",
                )
            events_digest = ref_sha
        elif handles.content.get_document(ref_sha) is None:
            _abort(
                seed,
                run_id,
                f"evidence ref {ref_id!r} digest {ref_sha} does not resolve "
                "in the content store",
            )
    if not events_digest:
        _abort(seed, run_id, "the record's evidence refs carry no events:{run} digest")

    # 5. The dispatch oracle: one durable event per dispatched device
    #    operation, and exactly the healthy-body count.
    dispatches = [event for event in events if str(event.get("kind")) in DISPATCH_KINDS]
    seen: dict[str, int] = {}
    for event in dispatches:
        key = json.dumps(event.get("occurrence"), sort_keys=True, separators=(",", ":"))
        seen[key] = seen.get(key, 0) + 1
    duplicates = sum(count - 1 for count in seen.values() if count > 1)
    if duplicates:
        _abort(
            seed,
            run_id,
            f"{duplicates} duplicated dispatch occurrence(s) in the durable stream — "
            "a second execution of one occurrence happened",
        )
    if len(dispatches) != EXPECTED_DISPATCHES:
        _abort(
            seed,
            run_id,
            f"{len(dispatches)} dispatched device operations, expected "
            f"{EXPECTED_DISPATCHES} (the healthy-body pin)",
        )
    return _Gate(
        terminal_sha256=terminal_sha,
        events_digest=events_digest,
        dispatch_occurrences=len(dispatches),
        duplicate_dispatches=0,
    )


# --- the generator -------------------------------------------------------------------


def _clear_prior(runs_dir: Path) -> None:
    """Remove this generator's own prior artifacts (a fresh, truthful tree)."""
    for pattern in ("run-*.json", "summary.json"):
        for path in runs_dir.glob(pattern):
            path.unlink()


@contextmanager
def _ephemeral_gateway(fixtures_dir: Path, *, timeout_s: float) -> Iterator[AppHandles]:
    """Boot ONE ephemeral SIMULATION gateway; yield its handles; tear down.

    The generate_runs boot, factored once (the timing leg reuses it):
    scratch mkdtemp root, the anti-coordinate gate BEFORE any composition,
    loopback uvicorn, the ephemeral principal's token, and a teardown that
    always stops the server, joins it, closes the store, and removes the
    scratch tree this context created.
    """
    # Lazy heavy imports: only generation pays for the app stack (the demo rule).
    from benchweave.content.store import ContentStore
    from benchweave.interfaces.app import create_app
    from benchweave.interfaces.identity import issue
    from benchweave.state.store import Store

    root = Path(tempfile.mkdtemp(prefix="benchweave-evidence-"))
    # Anti-coordinate gate (ISC-12): refuse BEFORE composing anything.
    held = held_stores(root)
    if held:
        raise EvidenceError(
            "refusing: a live gateway holds "
            + ", ".join(str(path) for path in held)
            + f" under {root} — the generator never composes a second coordinator "
            "over a held store"
        )
    try:
        store = Store.open(root / DB_NAME, check_same_thread=False)
    except sqlite3.OperationalError as error:
        raise EvidenceError(f"cannot open a scratch store under {root}: {error}") from error

    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    try:
        content = ContentStore(store)
        secret = secrets.token_bytes(32)
        app = create_app(
            store=store,
            content=content,
            secret=secret,
            limits=DEFAULT_LIMITS,
            gateway_id=EVIDENCE_GATEWAY_ID,
            fixtures_dir=fixtures_dir,
            now_iso=_now_iso,
            now_epoch=_now_epoch,
        )
        # demo's loopback boot, imported deliberately: ONE boot idiom, not a fork.
        server, thread, port = _boot(app)
        token = issue(
            secret,
            principal=EVIDENCE_PRINCIPAL,
            audience="stg",
            scopes={"stg:control"},
            expires_at=_now_epoch() + 3600,
        )
        client = GatewayClient(f"http://127.0.0.1:{port}", token=token)
        yield AppHandles(
            client=client,
            store=store,
            content=content,
            fixtures=fixtures_dir,
            base_url=f"http://127.0.0.1:{port}",
            token=token,
            timeout_s=timeout_s,
        )
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5.0)
        store.close()
        # The scratch tree is always this context's own mkdtemp creation.
        shutil.rmtree(root, ignore_errors=True)


def generate_runs(
    dest: Path,
    *,
    count: int = DEFAULT_COUNT,
    seed: int = DEFAULT_SEED,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    fixtures: Path | None = None,
    progress: Callable[[int, int, RunRecord], None] | None = None,
) -> dict[str, Any]:
    """Drive ``count`` consecutive seeded runs; write records + the summary.

    Boots ONE ephemeral simulation gateway (the demo fresh-install idiom:
    scratch store, anti-coordinate gate, loopback uvicorn, SIMULATION
    labels) and drives runs 1..``count`` under seeds ``seed + 1 ..``seed +
    count``, each gate-checked inline. Per-run records are written as they
    complete; ``summary.json`` lands only after EVERY run passed the gate —
    an abort leaves the partial records on disk (truthful) and no summary
    (nothing claims completeness). Returns the summary.
    """
    if count < 1:
        raise EvidenceError(f"count must be >= 1, got {count}")
    if timeout_s <= 0:
        raise EvidenceError(f"timeout_s must be positive, got {timeout_s}")
    fixtures_dir = resolve_fixtures(fixtures)
    with _ephemeral_gateway(fixtures_dir, timeout_s=timeout_s) as handles:
        runs_dir = Path(dest) / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        _clear_prior(runs_dir)

        outcomes: list[str] = []
        occurrence_total = 0
        duplicate_total = 0
        first: RunRecord | None = None
        wall = time.monotonic()
        for index in range(1, count + 1):
            record = drive_journey(handles, seed=seed + index)
            if first is None:
                first = record
            payload: dict[str, Any] = {"index": index, **record.to_dict()}
            (runs_dir / f"run-{index:03d}.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            outcomes.append(record.outcome or "unknown")
            occurrence_total += record.dispatch_occurrences
            duplicate_total += record.duplicate_dispatches
            if progress is not None:
                progress(index, count, record)
        duration_s = round(time.monotonic() - wall, 3)

        # The summary of a COMPLETE generation only — every run passed the gate.
        summary: dict[str, Any] = {
            "count": count,
            "outcomes": outcomes,
            "duplicate_dispatch_total": duplicate_total,
            "dispatch_occurrences_total": occurrence_total,
            "seed": seed,
            "host": _host_disclosure(),
            "simulation": True,
            "label": SIMULATION_LABEL,
            "gateway_id": EVIDENCE_GATEWAY_ID,
            "bench_id": first.bench_id if first is not None else "",
            "generated_at": _now_iso(),
            "duration_s": duration_s,
        }
        (runs_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return summary


# --- the timing leg (Task 9) --------------------------------------------------------

#: Default read requests per PRD-load window (PRD §6: 100 requests).
DEFAULT_TIMING_REQUESTS = 100
#: Default observers for the reads window (PRD §6: two observers).
DEFAULT_TIMING_OBSERVERS = 2
#: The stress tier's shape: 16 observers x 100 reads each, non-gating.
STRESS_OBSERVERS = 16
STRESS_REQUESTS_PER_OBSERVER = 100
#: Offset keeping the driver's §9 key family disjoint from the acceptance
#: family under any operator-passed seed.
_DRIVER_SEED_OFFSET = 900_000


class _ActiveRunDriver:
    """Keeps one run live on the bench, restarting as each reaches terminal.

    A fixture run reaches terminal in well under a second — far shorter
    than a measurement window — so the driver loops the seeded-journey
    start (fresh binding variant, preflight, ``run_start``, publish the
    run id, poll to terminal, next seed). ``coverage(window)`` is the live
    fraction the driver ACHIEVED over a measurement window: each live
    interval spans accept-response to terminal observation (0.2 s poll
    granularity), and the retained evidence reports this measured number,
    never a claim.
    """

    def __init__(self, handles: AppHandles, *, seed: int) -> None:
        self._handles = handles
        self._seed = seed
        self._stop = threading.Event()
        self._first = threading.Event()
        self._lock = threading.Lock()
        self._intervals: list[tuple[float, float]] = []
        self._open_since: float | None = None
        self._run_id = ""
        self._error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._loop, name="benchweave-timing-driver", daemon=True
        )

    @property
    def current_run_id(self) -> str:
        with self._lock:
            return self._run_id

    @property
    def error(self) -> BaseException | None:
        return self._error

    def start(self) -> None:
        self._thread.start()

    def wait_first_run(self, timeout_s: float) -> None:
        """Block until the first run is live (or fail truthfully)."""
        if not self._first.wait(timeout_s):
            self._stop.set()
            detail = f"the active-run driver produced no live run within {timeout_s:g}s"
            if self._error is not None:
                detail += f" (driver error: {self._error})"
            raise EvidenceError(detail)
        if self._error is not None:
            raise EvidenceError(f"the active-run driver failed: {self._error}") from self._error

    def stop(self) -> None:
        """Graceful stop: the in-flight run finishes to terminal, then the loop ends."""
        self._stop.set()
        self._thread.join(timeout=15.0)

    def coverage(self, window_start: float, window_end: float) -> float:
        """The live fraction achieved over [window_start, window_end].

        A run still live when this is called counts through ``window_end``
        — it was continuously live from its accept past the closed window
        (exact, not an estimate); a run that already reached terminal
        observation contributes its finalized interval.
        """
        window = window_end - window_start
        if window <= 0:
            return 0.0
        live = 0.0
        with self._lock:
            for start, end in self._intervals:
                live += max(0.0, min(end, window_end) - max(start, window_start))
            if self._open_since is not None:
                live += max(0.0, window_end - max(self._open_since, window_start))
        return min(1.0, live / window)

    def _loop(self) -> None:
        index = 0
        while not self._stop.is_set():
            index += 1
            try:
                self._drive(seed=self._seed + index)
            except BaseException as error:  # surfaced by the caller, never swallowed
                self._error = error
                self._first.set()
                return

    def _drive(self, *, seed: int) -> None:
        handles = self._handles
        request_id = f"req-timing-drive-{seed}"
        ref, document = _binding_variant(handles.content, handles.fixtures, request_id)
        bench_id = str(document["bench"]["id"])
        client = handles.client
        preflight = client.run_check(bench_id, binding_ref=ref)
        if preflight.get("valid") is not True:
            raise EvidenceError(
                f"driver seed {seed} ({request_id}): run_check preflight rejected "
                f"the binding — {preflight.get('findings')!r}"
            )
        generation = preflight.get("generation")
        if not isinstance(generation, int):
            raise EvidenceError(
                f"driver seed {seed} ({request_id}): preflight carried no canonical generation"
            )
        accepted = client.run_start(
            bench_id,
            request_id=request_id,
            binding_ref=ref,
            expected_generation=generation,
        )
        if accepted.get("state") != "accepted":
            raise EvidenceError(
                f"driver seed {seed} ({request_id}): run_start returned state "
                f"{accepted.get('state')!r}, not 'accepted'"
            )
        run_id = str(accepted["run_id"])
        accepted_at = time.monotonic()
        with self._lock:
            self._run_id = run_id
            self._open_since = accepted_at
        self._first.set()
        try:
            final = poll_to_terminal(client, run_id, timeout_s=handles.timeout_s)
        finally:
            with self._lock:
                self._intervals.append((accepted_at, time.monotonic()))
                self._open_since = None
        if final.get("outcome") != "passed":
            # A driver run failing under load is an anomaly the measurement
            # must not paper over — the load leg assumes a healthy body.
            raise EvidenceError(
                f"driver seed {seed} ({request_id}): outcome "
                f"{final.get('outcome')!r}, not 'passed' — the bench is unhealthy "
                "under this load"
            )


def _lattice_bench_id(handles: AppHandles) -> str:
    """The one bench the lattice admitted (in-process discovery, once)."""
    payload = handles.client.bench_list()
    items = payload.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        bench_id = str(items[0].get("bench_id", ""))
        if bench_id:
            return bench_id
    raise EvidenceError("the ephemeral gateway served no bench to measure against")


def _timing_entry(
    result: TimingResult,
    **extra: Any,
) -> dict[str, Any]:
    """One measurement's retained record: the TimingResult fields + extras."""
    entry: dict[str, Any] = {
        "label": result.label,
        "p50_ms": result.p50_ms,
        "p95_ms": result.p95_ms,
        "max_ms": result.max_ms,
        "count": result.count,
        "observers": result.observers,
        "active_run": result.active_run,
        "seed": result.seed,
    }
    entry.update(extra)
    return entry


def generate_timing(
    dest: Path,
    *,
    seed: int = DEFAULT_SEED,
    requests: int = DEFAULT_TIMING_REQUESTS,
    observers: int = DEFAULT_TIMING_OBSERVERS,
    acceptance_requests: int = DEFAULT_TIMING_REQUESTS,
    stress_observers: int = STRESS_OBSERVERS,
    stress_requests: int = STRESS_REQUESTS_PER_OBSERVER,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    fixtures: Path | None = None,
) -> dict[str, Any]:
    """Measure the PRD §6 targets + the stress tier; write both artifacts.

    One ephemeral SIMULATION gateway (the generate_runs idiom). Order
    matters and is disclosed in the artifacts: acceptance FIRST — it needs
    the bench's one live-run slot exclusively, every sample on a fresh §9
    key with the previous run driven to terminal — then the active-run
    driver keeps a run live across the reads and stress windows. The
    reads artifact records the ACHIEVED live fraction as
    ``active_run_coverage`` and this function REFUSES to write it with
    none: an active-run reads measurement that never observed a live run
    would be a fabricated condition, not a measurement.
    """
    if min(requests, acceptance_requests, stress_requests, observers, stress_observers) < 1:
        raise EvidenceError("every request/observer count must be >= 1")
    if timeout_s <= 0:
        raise EvidenceError(f"timeout_s must be positive, got {timeout_s}")
    fixtures_dir = resolve_fixtures(fixtures)
    with _ephemeral_gateway(fixtures_dir, timeout_s=timeout_s) as handles:
        bench_id = _lattice_bench_id(handles)

        def prepare(index: int) -> tuple[str, str, dict[str, Any]]:
            request_id = f"req-timing-accept-{seed + index}"
            ref, document = _binding_variant(handles.content, handles.fixtures, request_id)
            return str(document["bench"]["id"]), request_id, ref

        def await_terminal(run_id: str) -> None:
            final = poll_to_terminal(handles.client, run_id, timeout_s=handles.timeout_s)
            if final.get("outcome") != "passed":
                raise EvidenceError(
                    f"acceptance sample run {run_id}: outcome "
                    f"{final.get('outcome')!r}, not 'passed'"
                )

        acceptance = measure_acceptance(
            handles.base_url,
            handles.token,
            requests=acceptance_requests,
            observers=observers,
            timeout=timeout_s,
            prepare=prepare,
            await_terminal=await_terminal,
            seed=seed,
        )

        driver = _ActiveRunDriver(handles, seed=seed + _DRIVER_SEED_OFFSET)
        driver.start()
        try:
            driver.wait_first_run(timeout_s=timeout_s)
            reads_start = time.monotonic()
            reads = measure_reads(
                handles.base_url,
                handles.token,
                requests=requests,
                observers=observers,
                active_run=True,
                timeout=timeout_s,
                bench_id=bench_id,
                run_id_of=lambda: driver.current_run_id,
                seed=seed,
            )
            reads_end = time.monotonic()
            if driver.error is not None:
                raise EvidenceError(
                    f"the active-run driver failed during the reads window: {driver.error}"
                ) from driver.error
            reads_coverage = driver.coverage(reads_start, reads_end)
            if reads_coverage <= 0.0:
                raise EvidenceError(
                    "the reads window observed NO live run — refusing to write "
                    "active-run reads evidence with no active run"
                )

            stress_start = time.monotonic()
            stress = measure_stress(
                handles.base_url,
                handles.token,
                observers=stress_observers,
                requests_per_observer=stress_requests,
                timeout=timeout_s,
                bench_id=bench_id,
                run_id_of=lambda: driver.current_run_id,
                seed=seed,
            )
            stress_end = time.monotonic()
            if driver.error is not None:
                raise EvidenceError(
                    f"the active-run driver failed during the stress window: {driver.error}"
                ) from driver.error
            stress_coverage = driver.coverage(stress_start, stress_end)
        finally:
            driver.stop()

        method = {
            "reads": (
                f"{requests} metadata reads (GET /v1/benches, GET /v1/runs/{{id}}, "
                f"GET /v1/benches/{{id}}/events, rotating) by {observers} concurrent "
                "observer threads while one run is live; a background driver "
                "restarts seeded runs as each reaches terminal and the achieved "
                "live fraction is reported as active_run_coverage (accept-response "
                "to terminal observation, 0.2 s poll granularity)"
            ),
            "acceptance": (
                "each sample times ONE run_start call to its 202 accept response on "
                "a fresh §9 request key; the advisory run-check preflight and the "
                "poll to terminal (which frees the bench's one live-run slot) sit "
                "OUTSIDE every timed window — PRD §6 excludes device execution. "
                "Sequential on the single admitted bench: the committed fixture "
                "lattice admits exactly one bench per gateway and §5 holds one live "
                "run per bench, so a second concurrent run_start CONFLICTS at "
                "accept rather than measuring — the declared two-observer posture "
                "is recorded as observers_declared, the achieved shape as observers"
            ),
            "stress": (
                f"{stress_observers} observers x {stress_requests} metadata reads each "
                "(the same rotating read set), barrier-started so the whole burst "
                "is simultaneous, while the active-run driver keeps a run live; "
                "NON-REFERENCE and NON-GATING — it exists to make the D13 "
                "async-single-loop (blocking SQLite on one event loop) disclosure "
                "honest, not to gate anything"
            ),
            "percentile": "linear interpolation, rank = q * (n - 1), over the sorted sample",
            "timer": "time.perf_counter around each GatewayClient call (stdlib only)",
        }
        reads_entry = _timing_entry(
            reads,
            active_run=True,
            active_run_coverage=round(reads_coverage, 4),
            target_p95_ms=READS_TARGET_P95_MS,
            verdict="pass" if reads.p95_ms <= READS_TARGET_P95_MS else "fail",
        )
        acceptance_entry = _timing_entry(
            acceptance,
            observers_declared=observers,
            target_p95_ms=ACCEPTANCE_TARGET_P95_MS,
            verdict="pass" if acceptance.p95_ms <= ACCEPTANCE_TARGET_P95_MS else "fail",
        )
        stress_entry = _timing_entry(
            stress,
            active_run=stress_coverage > 0.0,
            active_run_coverage=round(stress_coverage, 4),
            verdict="recorded",
        )
        prd_payload: dict[str, Any] = {
            "generated_at": _now_iso(),
            "host": _host_disclosure(),
            "simulation": True,
            "label": SIMULATION_LABEL,
            "gateway_id": EVIDENCE_GATEWAY_ID,
            "seed": seed,
            "reference": True,
            "gating": True,
            "measurements": {LABEL_READS: reads_entry, LABEL_ACCEPTANCE: acceptance_entry},
            "method": method,
        }
        stress_payload: dict[str, Any] = {
            "generated_at": _now_iso(),
            "host": _host_disclosure(),
            "simulation": True,
            "label": SIMULATION_LABEL,
            "gateway_id": EVIDENCE_GATEWAY_ID,
            "seed": seed,
            "reference": False,
            "gating": False,
            "measurements": {LABEL_STRESS: stress_entry},
            "method": {key: method[key] for key in ("stress", "percentile", "timer")},
        }
        timing_dir = Path(dest) / "timing"
        timing_dir.mkdir(parents=True, exist_ok=True)
        (timing_dir / "prd-load.json").write_text(
            json.dumps(prd_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (timing_dir / "stress-16.json").write_text(
            json.dumps(stress_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return prd_payload


# --- the fault-matrix harvest (Task 11) ---------------------------------------------

#: The harvest target: exactly the four journey fault legs (Task 6), so the
#: junit report the transform reads carries only fault-leg cases.
DEFAULT_FAULT_TESTS = "tests/integration/test_poc_acceptance.py::test_journey_fault_legs"
#: Generous bound for the harvest pytest run (the legs share one booted
#: application via the suite's fixtures, but the suite is not fast).
FAULT_HARVEST_TIMEOUT_S = 600.0
#: The junit testcase name prefix every parameterized leg carries.
_LEG_TEST_PREFIX = "test_journey_fault_legs["
#: The measured values each leg records (pytest ``record_property``) — the
#: transform refuses a report lacking any of them rather than restate the
#: expectation tables from the test module.
_LEG_PROPERTIES = (
    "actual_outcome",
    "expected_outcomes",
    "occurrences_expected",
    "occurrences_actual",
)

#: The deterministic replacement for every ``hostname`` attribute value the
#: retained junit report carries (xunit1 writes one per ``<testsuite>``):
#: committed evidence records reproduction context, never a machine name —
#: the same doctrine the summaries' host disclosure already follows.
REFERENCE_HOST = "reference-host"


def scrub_junit_hostname(xml_bytes: bytes) -> bytes:
    """Replace every junit ``hostname="..."`` value with :data:`REFERENCE_HOST`.

    Retention-time scrub for the fault harvest's kept ``junit.xml``: the
    report pytest writes names the generating machine on every
    ``<testsuite>``, and retained evidence must not. A bytewise
    substitution — every other byte of the report passes through
    untouched, so the retained file stays byte-faithful to the scratch
    report apart from the hostname values.
    """
    return re.sub(
        rb'hostname="[^"]*"',
        f'hostname="{REFERENCE_HOST}"'.encode(),
        xml_bytes,
    )


def fault_legs_from_junit(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Project a junit report's fault-leg cases to lean per-leg rows.

    A pure transform — no test code imported, no values restated: every
    row field comes from the XML itself (the leg id from the parameterized
    name, the verdict from the testcase child element, the measured
    outcome and occurrence counts from the properties the leg test
    records). Non-leg cases are ignored; a report with no leg cases, or a
    leg case missing its recorded properties, refuses loudly — a wiring
    break, not a leg to guess about.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as error:
        # A truncated/invalid scratch report is a harvest failure with a
        # named message, never an xml.etree traceback through the CLI.
        raise EvidenceError(
            f"the junit report is not well-formed XML ({error}) — a truncated "
            "report is a wiring failure, not a leg to guess about"
        ) from error
    legs: list[dict[str, Any]] = []
    for case in root.iter("testcase"):
        name = str(case.get("name", ""))
        if not (name.startswith(_LEG_TEST_PREFIX) and name.endswith("]")):
            continue
        leg = name[len(_LEG_TEST_PREFIX) : -1]
        verdict = "passed"
        for tag in ("failure", "error", "skipped"):
            if case.find(tag) is not None:
                verdict = "failed" if tag == "failure" else tag
                break
        properties = {
            str(prop.get("name")): str(prop.get("value"))
            for prop in case.iter("property")
        }
        missing = [key for key in _LEG_PROPERTIES if key not in properties]
        if missing:
            raise EvidenceError(
                f"fault leg {leg!r}: the junit report records no "
                f"{', '.join(missing)} — the leg test must record them "
                "(pytest record_property)"
            )
        legs.append(
            {
                "name": leg,
                "verdict": verdict,
                "outcome": properties["actual_outcome"],
                "expected_outcomes": properties["expected_outcomes"].split(","),
                "occurrences": {
                    "expected": int(properties["occurrences_expected"]),
                    "actual": int(properties["occurrences_actual"]),
                },
                "duration_s": round(float(str(case.get("time", "0"))), 3),
            }
        )
    if not legs:
        raise EvidenceError(
            "the junit report carries no test_journey_fault_legs[...] cases — "
            "the harvest target must select the fault legs"
        )
    return sorted(legs, key=lambda leg: str(leg["name"]))


def generate_faults(
    dest: Path,
    *,
    tests: str = DEFAULT_FAULT_TESTS,
    timeout_s: float = FAULT_HARVEST_TIMEOUT_S,
) -> dict[str, Any]:
    """Harvest the fault-matrix leg results into ``<dest>/fault-matrix/``.

    Runs the journey fault legs under pytest with ``--junitxml`` into a
    scratch file, projects the report to a lean per-leg JSON, and retains
    BOTH: ``legs.json`` (the lean matrix) and ``junit.xml`` (the report
    itself — retained evidence, not tool state; the hostname attributes
    pytest writes are scrubbed to :data:`REFERENCE_HOST` at retention).
    The complete-matrix discipline of the other generators applies: artifacts land only when
    every leg passed — a failing or missing leg aborts loudly (naming the
    legs) and nothing is written.
    """
    if timeout_s <= 0:
        raise EvidenceError(f"timeout_s must be positive, got {timeout_s}")
    with tempfile.TemporaryDirectory(prefix="benchweave-faults-") as scratch:
        junit_path = Path(scratch) / "fault-legs.xml"
        # junit_family=xunit1: the default (xunit2) schema rejects
        # <properties> inside <testcase> — the recorded measurements the
        # transform reads — warning on every leg. xunit1 carries them
        # schema-valid; the retained junit.xml is self-describing either way.
        command = [
            sys.executable,
            "-m",
            "pytest",
            tests,
            "-o",
            "junit_family=xunit1",
            f"--junitxml={junit_path}",
        ]
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired as error:
            raise EvidenceError(
                f"the fault-leg pytest run exceeded {timeout_s:g}s — harvest refused"
            ) from error
        if not junit_path.is_file():
            tail = (completed.stdout + completed.stderr).strip()[-400:]
            raise EvidenceError(f"pytest produced no junit report: {tail!r}")
        legs = fault_legs_from_junit(junit_path.read_bytes())
        failed = [leg for leg in legs if str(leg["verdict"]) != "passed"]
        if failed or completed.returncode != 0:
            detail = ", ".join(
                f"{leg['name']} ({leg['verdict']})" for leg in failed
            )
            detail = detail or f"pytest exit {completed.returncode}"
            raise EvidenceError(
                f"the fault matrix is not green — refusing to harvest: {detail}"
            )
        payload: dict[str, Any] = {
            "generated_at": _now_iso(),
            "host": _host_disclosure(),
            "simulation": True,
            "label": SIMULATION_LABEL,
            "tests": tests,
            "legs": legs,
            "totals": {
                "legs": len(legs),
                "failed": 0,
                "duration_s": round(
                    sum(float(str(leg["duration_s"])) for leg in legs), 3
                ),
            },
        }
        fault_dir = Path(dest) / "fault-matrix"
        fault_dir.mkdir(parents=True, exist_ok=True)
        (fault_dir / "legs.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # Retention scrubs the machine name pytest writes per <testsuite>:
        # the retained junit.xml is byte-faithful to the scratch report
        # apart from the hostname values (committed evidence never names
        # the generating host).
        (fault_dir / "junit.xml").write_bytes(
            scrub_junit_hostname(junit_path.read_bytes())
        )
        return payload


# --- the digest index (Task 11) ------------------------------------------------------

#: Top-level dirs whose artifacts are REGENERABLE — the index names each
#: one's generator command; regenerating rewrites the artifact and this
#: index's digest row for it.
_GENERATED_DIRS = frozenset({"runs", "timing", "fault-matrix"})
#: Top-level dirs whose artifacts are RECORDS — digest-bound; regenerating
#: the index refreshes digests but never rewrites a record.
_RECORD_DIRS = frozenset({"timed-demos", "decisions"})
#: The index file this generator writes (and therefore never indexes — a
#: file cannot digest itself).
_INDEX_NAME = "index.md"
#: The regeneration cell a record-class row carries (records have no
#: regenerating command by definition).
_RECORD_CELL = "record — digest-bound, never regenerated"
#: The regenerating command named in each generated row (the dest exactly
#: as the operator passed it, so the row is reproducible).
_GENERATOR_COMMANDS = {
    "runs": "benchweave evidence runs --dest {dest}",
    "timing": "benchweave evidence timing --dest {dest}",
    "fault-matrix": "benchweave evidence faults --dest {dest}",
}
#: Regeneration preconditions a generated row discloses after its command
#: (the index tells the operator how to reproduce the artifact, including
#: where from: the faults default ``--tests`` node id is repo-relative).
_GENERATOR_NOTES = {
    "fault-matrix": "from the repository root — the default --tests node id is relative",
}


def _artifact_rows(dest: Path) -> list[tuple[str, str, str]]:
    """(relative path, class, sha256) for every classified artifact, sorted.

    Refuses anything the class rules do not cover: an unknown top-level
    directory or a stray file at the tree root would otherwise index under
    a silently wrong class — the loud refusal forces a conscious rule.
    """
    rows: list[tuple[str, str, str]] = []
    for path in sorted(dest.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(dest)
        if relative.parts == (_INDEX_NAME,):
            continue
        if any(part.startswith(".") for part in relative.parts):
            # Operator-local dotfiles (macOS .DS_Store, editor droppings)
            # are noise, not evidence: skipped wherever they sit — never
            # indexed, and never an unclassified-artifact refusal.
            continue
        if len(relative.parts) == 1:
            raise EvidenceError(
                f"unclassified artifact at the tree root: {relative} — the index "
                "classifies by top-level directory (runs/timing/fault-matrix are "
                "generated; timed-demos/decisions are records)"
            )
        top = relative.parts[0]
        if top in _GENERATED_DIRS:
            evidence_class = "generated"
        elif top in _RECORD_DIRS:
            evidence_class = "record"
        else:
            raise EvidenceError(
                f"unclassified evidence directory: {top}/ (from {relative}) — "
                "register the class before indexing it"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append((relative.as_posix(), evidence_class, digest))
    return rows


def generate_index(dest: Path) -> dict[str, Any]:
    """Write ``<dest>/index.md``: one row per artifact — digest + class.

    Deterministic by construction: rows are sorted by path, digests come
    from the bytes, and NO generation timestamp rides the index (times
    belong to the artifacts — the runs/timing/fault-matrix artifacts carry
    their own ``generated_at``). An unchanged tree regenerates a
    byte-identical index. Returns the lean emit payload.
    """
    dest = Path(dest)
    if not dest.is_dir():
        raise EvidenceError(f"evidence tree not found at {dest}")
    rows = _artifact_rows(dest)
    dest_arg = dest.as_posix()
    lines = [
        "# PoC evidence index",
        "",
        "Every retained artifact under this tree, one row per file, each row",
        "carrying the sha256 over the file's bytes. Classes:",
        "",
        "- `generated` — regenerable by the named command; regenerating rewrites",
        "  the artifact and this index's digest row for it.",
        "- `record` — digest-bound records (timed demos, decision registrations);",
        "  regenerating the index refreshes digests but NEVER rewrites a record.",
        "",
        "The index excludes itself (a file cannot digest itself) and is",
        "deterministic — an unchanged tree regenerates byte-identically — so it",
        "carries no timestamp of its own.",
        "",
        "| Artifact | Class | SHA-256 | Regeneration |",
        "|---|---|---|---|",
    ]
    for relative, evidence_class, digest in rows:
        top = relative.split("/")[0]
        if evidence_class == "generated":
            cell = f"`{_GENERATOR_COMMANDS[top].format(dest=dest_arg)}`"
            note = _GENERATOR_NOTES.get(top)
            if note:
                cell = f"{cell} ({note})"
        else:
            cell = _RECORD_CELL
        lines.append(f"| `{relative}` | {evidence_class} | `{digest}` | {cell} |")
    (dest / _INDEX_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
    generated = sum(1 for _, evidence_class, _ in rows if evidence_class == "generated")
    return {
        "dest": dest_arg,
        "index": (dest / _INDEX_NAME).as_posix(),
        "artifacts": len(rows),
        "generated": generated,
        "record": len(rows) - generated,
    }


# --- the Click surface ----------------------------------------------------------------


@click.group()
def evidence() -> None:
    """Generate and index the retained evidence tree.

    Four generators: ``runs`` (the seeded volume leg), ``timing`` (the PRD
    §6 targets + the stress tier), ``faults`` (the fault-matrix leg
    harvest), and ``index`` (the digest index binding the whole tree).
    """


def _set_json(json_output: bool) -> None:
    """Carry the ``--json`` flag to :func:`benchweave.cli.output.emit`."""
    ctx = click.get_current_context()
    obj = ctx.ensure_object(dict)
    obj["json"] = json_output


def _stderr_progress(index: int, count: int, record: RunRecord) -> None:
    """One line per completed run (stderr: stdout stays the machine surface)."""
    click.echo(
        f"[{index}/{count}] {record.run_id} {record.outcome} "
        f"({record.duration_s:.2f}s, {record.dispatch_occurrences} dispatches)",
        err=True,
    )


@evidence.command()
@click.option(
    "--dest",
    "dest",
    type=click.Path(path_type=Path),
    required=True,
    help="Output root; per-run records + summary.json land under <dest>/runs/.",
)
@click.option(
    "--count",
    "count",
    type=int,
    default=DEFAULT_COUNT,
    show_default=True,
    help="Number of consecutive seeded runs.",
)
@click.option(
    "--seed",
    "seed",
    type=int,
    default=DEFAULT_SEED,
    show_default=True,
    help="Base seed; run N derives seed + N and its own request id.",
)
@click.option(
    "--timeout",
    "timeout_s",
    type=float,
    default=DEFAULT_TIMEOUT_S,
    show_default=True,
    help="Seconds to wait for each run to reach a terminal state.",
)
@click.option(
    "--fixtures",
    "fixtures",
    type=click.Path(path_type=Path),
    default=None,
    envvar="BENCHWEAVE_FIXTURES",
    help="Fixture lattice directory (default: the repository execution lattice).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def runs(
    dest: Path,
    count: int,
    seed: int,
    timeout_s: float,
    fixtures: Path | None,
    json_output: bool,
) -> None:
    """Generate consecutive seeded journey runs (ephemeral SIMULATION)."""
    _set_json(json_output)
    try:
        summary = generate_runs(
            dest,
            count=count,
            seed=seed,
            timeout_s=timeout_s,
            fixtures=fixtures,
            progress=_stderr_progress,
        )
    except (EvidenceError, DemoError, GatewayError) as error:
        raise click.ClickException(str(error)) from error
    emit(summary)


@evidence.command()
@click.option(
    "--dest",
    "dest",
    type=click.Path(path_type=Path),
    required=True,
    help=(
        "Output root; the timing artifacts land under <dest>/timing/ "
        "(prd-load.json + stress-16.json)."
    ),
)
@click.option(
    "--seed",
    "seed",
    type=int,
    default=DEFAULT_SEED,
    show_default=True,
    help="Base seed; names the measurement and derives every §9 request key.",
)
@click.option(
    "--requests",
    "requests",
    type=int,
    default=DEFAULT_TIMING_REQUESTS,
    show_default=True,
    help="Metadata read requests in the PRD-load reads window.",
)
@click.option(
    "--observers",
    "observers",
    type=int,
    default=DEFAULT_TIMING_OBSERVERS,
    show_default=True,
    help="Concurrent observer threads for the reads window (PRD §6: two).",
)
@click.option(
    "--acceptance-requests",
    "acceptance_requests",
    type=int,
    default=DEFAULT_TIMING_REQUESTS,
    show_default=True,
    help="run_start accept-decision samples (fresh §9 keys, sequential).",
)
@click.option(
    "--stress-observers",
    "stress_observers",
    type=int,
    default=STRESS_OBSERVERS,
    show_default=True,
    help="Observers in the non-gating stress tier.",
)
@click.option(
    "--stress-requests",
    "stress_requests",
    type=int,
    default=STRESS_REQUESTS_PER_OBSERVER,
    show_default=True,
    help="Reads per observer in the stress tier.",
)
@click.option(
    "--timeout",
    "timeout_s",
    type=float,
    default=DEFAULT_TIMEOUT_S,
    show_default=True,
    help="Seconds to wait for any driven run to reach a terminal state.",
)
@click.option(
    "--fixtures",
    "fixtures",
    type=click.Path(path_type=Path),
    default=None,
    envvar="BENCHWEAVE_FIXTURES",
    help="Fixture lattice directory (default: the repository execution lattice).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def timing(
    dest: Path,
    seed: int,
    requests: int,
    observers: int,
    acceptance_requests: int,
    stress_observers: int,
    stress_requests: int,
    timeout_s: float,
    fixtures: Path | None,
    json_output: bool,
) -> None:
    """Measure PRD §6 targets + the 16-observer stress tier (SIMULATION)."""
    _set_json(json_output)
    try:
        payload = generate_timing(
            dest,
            seed=seed,
            requests=requests,
            observers=observers,
            acceptance_requests=acceptance_requests,
            stress_observers=stress_observers,
            stress_requests=stress_requests,
            timeout_s=timeout_s,
            fixtures=fixtures,
        )
    except (EvidenceError, DemoError, GatewayError, PerformanceError) as error:
        raise click.ClickException(str(error)) from error
    emit(payload)


@evidence.command()
@click.option(
    "--dest",
    "dest",
    type=click.Path(path_type=Path),
    required=True,
    help="Output root; legs.json + junit.xml land under <dest>/fault-matrix/.",
)
@click.option(
    "--tests",
    "tests",
    default=DEFAULT_FAULT_TESTS,
    show_default=True,
    help="pytest node id selecting the journey fault legs to harvest.",
)
@click.option(
    "--timeout",
    "timeout_s",
    type=float,
    default=FAULT_HARVEST_TIMEOUT_S,
    show_default=True,
    help="Seconds to bound the harvest pytest run.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def faults(dest: Path, tests: str, timeout_s: float, json_output: bool) -> None:
    """Harvest the fault-matrix leg results (lean JSON + retained junit)."""
    _set_json(json_output)
    try:
        payload = generate_faults(dest, tests=tests, timeout_s=timeout_s)
    except (EvidenceError, OSError) as error:
        raise click.ClickException(str(error)) from error
    emit(payload)


@evidence.command()
@click.option(
    "--dest",
    "dest",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    required=True,
    help="Evidence tree root; the digest index lands at <dest>/index.md.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Emit the stable machine JSON contract instead of text.",
)
def index(dest: Path, json_output: bool) -> None:
    """Index every artifact: sha256 + class + regenerating command."""
    _set_json(json_output)
    try:
        payload = generate_index(dest)
    except (EvidenceError, OSError) as error:
        raise click.ClickException(str(error)) from error
    emit(payload)
