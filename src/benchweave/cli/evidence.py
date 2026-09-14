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
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time
from collections.abc import Callable
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
    bounds each run's poll to terminal.
    """

    client: GatewayClient
    store: Store
    content: ContentStore
    fixtures: Path
    base_url: str
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
    port = 0
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
        handles = AppHandles(
            client=client,
            store=store,
            content=content,
            fixtures=fixtures_dir,
            base_url=f"http://127.0.0.1:{port}",
            timeout_s=timeout_s,
        )

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
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5.0)
        store.close()
        # The scratch tree is always this generator's own mkdtemp creation.
        shutil.rmtree(root, ignore_errors=True)


# --- the Click surface ----------------------------------------------------------------


@click.group()
def evidence() -> None:
    """Generate retained evidence artifacts (volume runs; timing/faults to come)."""


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
