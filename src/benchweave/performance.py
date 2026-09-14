"""PRD §6 performance measurement: metadata reads, acceptance, stress.

Three measured surfaces, stdlib-only timing (``time.perf_counter`` around
:class:`benchweave.cli.client.GatewayClient` calls — no new dependencies):

- ``prd-load-reads`` — the PRD "metadata reads" set (``GET /v1/benches``,
  ``GET /v1/runs/{id}``, ``GET /v1/benches/{id}/events``), issued by
  ``observers`` concurrent reader threads rotating through the three kinds,
  measured while a run is live on the bench (the caller arranges and
  truthfully reports the active-run coverage — this module measures, it
  does not drive).
- ``prd-load-acceptance`` — the request→accepted decision ONLY (PRD §6
  excludes device execution): each sample times ONE ``run_start`` call to
  its 202 accept response on a FRESH §9 key. The advisory ``run_check``
  preflight and the poll to terminal (which frees the bench's one live-run
  slot for the next sample) sit OUTSIDE every timed window.
- ``stress-16`` — the non-reference, non-gating stress tier: 16 observers
  × ``requests_per_observer`` reads, barrier-started so the burst is
  genuinely simultaneous. It exists to make the D13 async single-loop
  disclosure honest, never to gate anything.

Percentile method (pinned, disclosed in the retained evidence): linear
interpolation — ``rank = q * (n - 1)`` over the ascending sample (the
numpy default / ``statistics`` "inclusive" method).

Acceptance shape disclosure (measured, not assumed): the committed fixture
lattice admits exactly ONE bench per gateway (``admit_startup_bench`` reads
one ``bench.json``), and §5 holds one live run per bench — a second
concurrent ``run_start`` on the same bench CONFLICTS at accept rather than
measuring. The acceptance measurement is therefore SEQUENTIAL: distinct
§9 keys, previous run driven to terminal before the next request, one
calling thread. ``measure_acceptance`` accepts the declared ``observers``
posture for the record and the result carries the achieved observer count
(1); concurrent acceptance needs a multi-bench lattice this gateway cannot
admit. ``prepare``/``await_terminal`` are the orchestration seams: a fresh
binding per sample must be stored in the gateway's content store (no wire
document-upload exists), which only the in-process caller can do.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # TYPE_CHECKING-only: a module-level import would pull
    # ``benchweave.cli``'s package __init__ (commands → evidence → this
    # module) and make ``import benchweave.performance`` standalone fail
    # on a partially initialized cycle. The functions that construct a
    # client import it lazily; annotations stay strings under the future
    # import.
    from benchweave.cli.client import GatewayClient

#: The three evidence labels (the retained JSON keys).
LABEL_READS = "prd-load-reads"
LABEL_ACCEPTANCE = "prd-load-acceptance"
LABEL_STRESS = "stress-16"
#: Base seed for the timing families (matches ``evidence.DEFAULT_SEED`` —
#: the WP09 Step-4 invocation pins one seed across the retained evidence).
DEFAULT_SEED = 20260914
#: The PRD §6 targets on the recorded reference host (ms, p95).
READS_TARGET_P95_MS = 500
ACCEPTANCE_TARGET_P95_MS = 2000
#: Read-set rotation: bench list, run projection, bench event page.
_READ_KINDS = 3


class PerformanceError(RuntimeError):
    """A truthful measurement failure (bad arguments, dead gateway)."""


@dataclass(frozen=True)
class TimingResult:
    """One measured surface's latency summary.

    ``active_run`` records the measurement's declared live-run condition —
    the CALLER's retained evidence must carry the achieved coverage (the
    driver-side live fraction over the measurement window) alongside it.
    """

    label: str
    p50_ms: float
    p95_ms: float
    max_ms: float
    count: int
    observers: int
    active_run: bool
    seed: int


# --- the math ------------------------------------------------------------------------


def _percentile(ascending: list[float], q: float) -> float:
    """Linear interpolation: ``rank = q * (n - 1)`` over the sorted sample."""
    if not ascending:
        raise PerformanceError("a percentile needs at least one sample")
    if len(ascending) == 1:
        return ascending[0]
    rank = q * (len(ascending) - 1)
    low = int(rank)
    high = min(low + 1, len(ascending) - 1)
    weight = rank - low
    return ascending[low] + weight * (ascending[high] - ascending[low])


def _summarize(
    label: str,
    samples_ms: list[float],
    *,
    observers: int,
    active_run: bool,
    seed: int,
) -> TimingResult:
    """Fold collected samples into the retained summary (order-independent)."""
    if not samples_ms:
        raise PerformanceError(f"{label}: no samples were collected")
    ordered = sorted(samples_ms)
    return TimingResult(
        label=label,
        p50_ms=round(_percentile(ordered, 0.50), 3),
        p95_ms=round(_percentile(ordered, 0.95), 3),
        max_ms=round(ordered[-1], 3),
        count=len(ordered),
        observers=observers,
        active_run=active_run,
        seed=seed,
    )


# --- the concurrent collection core ----------------------------------------------------


def _measure_concurrent(
    label: str,
    *,
    operation: Callable[[int], float],
    observers: int,
    requests: int,
    active_run: bool,
    seed: int,
) -> TimingResult:
    """Run ``operation`` over ``requests`` calls across ``observers`` threads.

    Every observer passes one start barrier before its first call, so a
    burst (the stress tier) is genuinely simultaneous; the fair-share split
    guarantees exactly ``requests`` timed calls in total regardless of
    thread interleaving. The first observer failure is re-raised after the
    join, wrapped with the label — never swallowed, never half-reported.
    """
    if observers < 1:
        raise PerformanceError(f"{label}: observers must be >= 1, got {observers}")
    if requests < 1:
        raise PerformanceError(f"{label}: requests must be >= 1, got {requests}")
    base, extra = divmod(requests, observers)
    shares = [base + (1 if index < extra else 0) for index in range(observers)]

    samples: list[float] = []
    lock = threading.Lock()
    errors: list[BaseException] = []
    start = threading.Barrier(observers)

    def observer(share: int) -> None:
        try:
            start.wait(timeout=30.0)
            for local_index in range(share):
                elapsed_ms = operation(local_index)
                with lock:
                    samples.append(elapsed_ms)
        except BaseException as error:  # reported after the join, never swallowed
            with lock:
                errors.append(error)

    threads = [
        threading.Thread(target=observer, args=(share,), name=f"perf-{label}-{i}", daemon=True)
        for i, share in enumerate(shares)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise PerformanceError(f"{label}: an observer failed: {errors[0]}") from errors[0]
    return _summarize(
        label, samples, observers=observers, active_run=active_run, seed=seed
    )


# --- the read set ------------------------------------------------------------------------


def _thread_clients(
    base_url: str, token: str, timeout: float
) -> Callable[[], GatewayClient]:
    """One ``GatewayClient`` per observer thread (created lazily where used)."""
    from benchweave.cli.client import GatewayClient

    local = threading.local()

    def client() -> GatewayClient:
        client_ = getattr(local, "client", None)
        if client_ is None:
            client_ = GatewayClient(base_url, token=token, timeout=timeout)
            local.client = client_
        return client_

    return client


def _read_operation(
    client_of: Callable[[], GatewayClient],
    bench_id: str,
    run_id_of: Callable[[], str],
) -> Callable[[int], float]:
    """One timed metadata read per call, rotating the three read kinds."""

    def operation(local_index: int) -> float:
        client = client_of()
        started = time.perf_counter()
        kind = local_index % _READ_KINDS
        if kind == 0:
            client.bench_list()
        elif kind == 1:
            client.run_get(run_id_of())
        else:
            client.events_get(bench_id, after="", limit=100)
        return (time.perf_counter() - started) * 1000.0

    return operation


def _discover_bench(client: GatewayClient) -> str:
    payload = client.bench_list()
    items = payload.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        bench_id = str(items[0].get("bench_id", ""))
        if bench_id:
            return bench_id
    raise PerformanceError("GET /v1/benches carried no bench to read")


def _resolve_run_id(
    label: str, run_id: str | None, run_id_of: Callable[[], str] | None
) -> Callable[[], str]:
    """The per-read run resolver: the caller's live-run getter, or a fixed id."""
    if run_id_of is not None:
        return run_id_of
    if run_id is not None:

        def fixed() -> str:
            return run_id

        return fixed
    raise PerformanceError(
        f"{label} needs run_id (or run_id_of): the read set includes "
        "GET /v1/runs/{{id}} and the gateway has no runs-list surface"
    )


# --- the measured surfaces --------------------------------------------------------------


def measure_reads(
    base_url: str,
    token: str,
    *,
    requests: int = 100,
    observers: int = 2,
    active_run: bool = True,
    timeout: float = 10.0,
    bench_id: str | None = None,
    run_id: str | None = None,
    run_id_of: Callable[[], str] | None = None,
    seed: int = DEFAULT_SEED,
) -> TimingResult:
    """Time the metadata read set under ``observers`` concurrent readers.

    ``run_id_of`` (preferred) resolves the run to project per read — the
    caller driving a restarting run resolves its CURRENT run, so reads
    track the live run rather than a frozen terminal projection. The read
    set has no runs-list surface to discover one from, so either ``run_id``
    or ``run_id_of`` must be given.
    """
    from benchweave.cli.client import GatewayClient

    probe = GatewayClient(base_url, token=token, timeout=timeout)
    resolved_bench = bench_id if bench_id is not None else _discover_bench(probe)
    resolver = _resolve_run_id(LABEL_READS, run_id, run_id_of)
    operation = _read_operation(
        _thread_clients(base_url, token, timeout), resolved_bench, resolver
    )
    return _measure_concurrent(
        LABEL_READS,
        operation=operation,
        observers=observers,
        requests=requests,
        active_run=active_run,
        seed=seed,
    )


def measure_acceptance(
    base_url: str,
    token: str,
    *,
    requests: int = 100,
    observers: int = 2,
    timeout: float = 10.0,
    prepare: Callable[[int], tuple[str, str, dict[str, Any]]] | None = None,
    await_terminal: Callable[[str], None] | None = None,
    seed: int = DEFAULT_SEED,
) -> TimingResult:
    """Time ``run_start`` request→accepted decisions on fresh §9 keys.

    Per sample (see the module docstring for the shape and its disclosure):
    ``prepare(index)`` stores the fresh binding variant UNTIMED and returns
    ``(bench_id, request_id, binding_ref)``; the advisory ``run_check``
    preflight (which also reports the canonical generation the fence
    reads) is UNTIMED; the ONE timed call is ``run_start`` → its 202
    accept response; ``await_terminal(run_id)`` then frees the bench's
    live-run slot for the next sample, UNTIMED. The result records the
    achieved observer count (1 — sequential; §5 forbids a second
    concurrent run on the one admitted bench).
    """
    if prepare is None or await_terminal is None:
        raise PerformanceError(
            "measure_acceptance needs prepare/await_terminal seams: a fresh §9 "
            "binding per sample must be stored in the gateway's content store "
            "(no wire document-upload surface exists) and the previous run must "
            "reach terminal before the bench accepts the next"
        )
    if requests < 1:
        raise PerformanceError(f"requests must be >= 1, got {requests}")
    from benchweave.cli.client import GatewayClient

    client = GatewayClient(base_url, token=token, timeout=timeout)
    samples: list[float] = []
    for index in range(requests):
        bench_id, request_id, binding_ref = prepare(index)
        preflight = client.run_check(bench_id, binding_ref=binding_ref)
        if preflight.get("valid") is not True:
            raise PerformanceError(
                f"sample {index} ({request_id}): run_check preflight rejected the "
                f"binding — {preflight.get('findings')!r}"
            )
        generation = preflight.get("generation")
        if not isinstance(generation, int):
            raise PerformanceError(
                f"sample {index} ({request_id}): preflight carried no canonical generation"
            )
        started = time.perf_counter()
        accepted = client.run_start(
            bench_id,
            request_id=request_id,
            binding_ref=binding_ref,
            expected_generation=generation,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if accepted.get("state") != "accepted":
            raise PerformanceError(
                f"sample {index} ({request_id}): run_start returned state "
                f"{accepted.get('state')!r}, not 'accepted' — a conflicted bench "
                "must never be recorded as an acceptance sample"
            )
        samples.append(elapsed_ms)
        await_terminal(str(accepted["run_id"]))
    return _summarize(
        LABEL_ACCEPTANCE,
        samples,
        observers=1,
        active_run=False,
        seed=seed,
    )


def measure_stress(
    base_url: str,
    token: str,
    *,
    observers: int = 16,
    requests_per_observer: int = 100,
    timeout: float = 10.0,
    bench_id: str | None = None,
    run_id: str | None = None,
    run_id_of: Callable[[], str] | None = None,
    seed: int = DEFAULT_SEED,
    active_run: bool = False,
    _operation: Callable[[int], float] | None = None,
) -> TimingResult:
    """The non-gating stress tier: ``observers`` × ``requests_per_observer``
    reads, barrier-started so the whole burst is simultaneous.

    ``_operation`` is the unit-test seam (the concurrency proof runs a
    barrier inside it); production calls rotate the same metadata read set
    as ``measure_reads``.
    """
    if _operation is not None:
        return _measure_concurrent(
            LABEL_STRESS,
            operation=_operation,
            observers=observers,
            requests=observers * requests_per_observer,
            active_run=active_run,
            seed=seed,
        )
    from benchweave.cli.client import GatewayClient

    probe = GatewayClient(base_url, token=token, timeout=timeout)
    resolved_bench = bench_id if bench_id is not None else _discover_bench(probe)
    resolver = _resolve_run_id(LABEL_STRESS, run_id, run_id_of)
    operation = _read_operation(
        _thread_clients(base_url, token, timeout), resolved_bench, resolver
    )
    return _measure_concurrent(
        LABEL_STRESS,
        operation=operation,
        observers=observers,
        requests=observers * requests_per_observer,
        active_run=active_run,
        seed=seed,
    )


__all__ = [
    "ACCEPTANCE_TARGET_P95_MS",
    "DEFAULT_SEED",
    "LABEL_ACCEPTANCE",
    "LABEL_READS",
    "LABEL_STRESS",
    "READS_TARGET_P95_MS",
    "PerformanceError",
    "TimingResult",
    "measure_acceptance",
    "measure_reads",
    "measure_stress",
]
