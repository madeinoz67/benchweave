"""The PRD §6 performance measurement core (WP09 Task 9, Step 1).

Three seams, three proofs, plus an end-to-end smoke:

1. the percentile math — a known sample through the REAL concurrent
   collection path (an injected sampler hands out exactly the multiset
   1..100 ms regardless of thread interleaving; percentile math is
   order-independent, so the pinned p50/p95/max values are deterministic);
2. ``TimingResult`` carries the contract field set verbatim;
3. ``measure_stress`` genuinely runs its observers concurrently — a
   ``threading.Barrier(observers)`` inside an injected operation only
   releases if N DISTINCT threads are inside the operation at the same
   instant (a serialised loop would time out and break the barrier);
4. the smoke drives the REAL timing generator end-to-end against a
   throwaway in-process gateway (the ``generate_runs`` fresh-install
   idiom): acceptance samples, active-run-driven reads, the stress tier,
   and both retained JSON artifacts with their reference/gating labels.

The reference numbers themselves are NOT asserted here — they are host
measurements, recorded by ``benchweave evidence timing`` and retained under
``docs/evidence/poc/timing/`` (asserting them in unit tests would be target
massaging by another name).
"""

from __future__ import annotations

import dataclasses
import json
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from benchweave.cli.evidence import generate_timing
from benchweave.performance import (
    LABEL_ACCEPTANCE,
    LABEL_READS,
    LABEL_STRESS,
    TimingResult,
    measure_stress,
)


def _sampler(values: list[float]) -> tuple[Callable[[int], float], list[float]]:
    """An injected operation handing out exactly ``values`` once each.

    The lock serialises the handout, so the collected multiset is exactly
    the input multiset no matter how the observer threads interleave —
    which is what makes the pinned percentiles deterministic.
    """
    iterator: Iterator[float] = iter(values)
    handed: list[float] = []
    lock = threading.Lock()

    def operation(_index: int) -> float:
        with lock:
            value = next(iterator)
            handed.append(value)
        return value

    return operation, handed


def test_percentile_math_over_known_sample_through_the_concurrent_path() -> None:
    from benchweave.performance import _measure_concurrent

    operation, _ = _sampler([float(value) for value in range(1, 101)])
    result = _measure_concurrent(
        LABEL_READS,
        operation=operation,
        observers=4,
        requests=100,
        active_run=True,
        seed=20260914,
    )
    # Linear interpolation (the numpy default): rank = q * (n - 1) over the
    # sorted sample 1..100 ms → p50 = 50.5, p95 = 95.05.
    assert result.count == 100
    assert result.p50_ms == pytest.approx(50.5)
    assert result.p95_ms == pytest.approx(95.05)
    assert result.max_ms == pytest.approx(100.0)
    assert result.observers == 4
    assert result.active_run is True
    assert result.seed == 20260914
    assert result.label == "prd-load-reads"


def test_percentile_math_edge_shapes() -> None:
    from benchweave.performance import _summarize

    # Odd count: p50 is a real sample; p95 interpolates (rank 3.8 of 0..4).
    odd = _summarize(
        LABEL_ACCEPTANCE,
        [10.0, 20.0, 30.0, 40.0, 100.0],
        observers=1,
        active_run=False,
        seed=1,
    )
    assert odd.p50_ms == pytest.approx(30.0)
    assert odd.p95_ms == pytest.approx(88.0)
    assert odd.max_ms == pytest.approx(100.0)
    # A single sample is its own every-percentile.
    one = _summarize(LABEL_STRESS, [7.5], observers=1, active_run=False, seed=1)
    assert (one.p50_ms, one.p95_ms, one.max_ms) == (7.5, 7.5, 7.5)
    assert one.count == 1


def test_timing_result_carries_the_contract_fields() -> None:
    names = [field.name for field in dataclasses.fields(TimingResult)]
    assert names == [
        "label",
        "p50_ms",
        "p95_ms",
        "max_ms",
        "count",
        "observers",
        "active_run",
        "seed",
    ]
    result = TimingResult(
        label=LABEL_STRESS,
        p50_ms=1.0,
        p95_ms=2.0,
        max_ms=3.0,
        count=1600,
        observers=16,
        active_run=False,
        seed=20260914,
    )
    assert result.label == "stress-16"
    assert result.count == 1600
    assert result.observers == 16
    assert result.active_run is False


def test_measure_stress_runs_observers_concurrently() -> None:
    """The barrier proves N DISTINCT threads sampled together.

    ``measure_stress`` hands each observer thread its own calls; the
    injected operation waits on a ``Barrier(observers)`` — it only releases
    when all observers are inside the operation at the same instant. A
    serialised implementation (one thread looping) breaks the barrier and
    fails this test.
    """
    observers = 4
    barrier = threading.Barrier(observers)
    idents: set[int] = set()
    ident_lock = threading.Lock()

    def operation(_index: int) -> float:
        with ident_lock:
            idents.add(threading.get_ident())
        barrier.wait(timeout=10.0)
        return 1.0

    result = measure_stress(
        "http://127.0.0.1:1",
        "token",
        observers=observers,
        requests_per_observer=1,
        timeout=10.0,
        _operation=operation,
    )
    assert result.observers == observers
    assert result.count == observers
    assert len(idents) == observers
    assert result.p50_ms == pytest.approx(1.0)
    assert result.label == "stress-16"


def test_timing_generator_smoke_against_in_process_gateway(tmp_path: Path) -> None:
    """The real flow, small counts: acceptance, active-run reads, stress.

    Boots the throwaway in-process gateway (the ``generate_runs`` idiom),
    times 3 acceptance decisions, reads under a live restarting run with 2
    observers, fires a 16-observer stress tier, and writes both retained
    JSON artifacts — labels, reference/gating flags, verdicts, and the
    active-run coverage disclosure included.
    """
    payload = generate_timing(
        tmp_path,
        seed=20260914,
        requests=6,
        observers=2,
        acceptance_requests=3,
        stress_observers=16,
        stress_requests=2,
    )

    prd_path = tmp_path / "timing" / "prd-load.json"
    stress_path = tmp_path / "timing" / "stress-16.json"
    assert prd_path.is_file() and stress_path.is_file()
    prd = json.loads(prd_path.read_text(encoding="utf-8"))
    stress = json.loads(stress_path.read_text(encoding="utf-8"))

    # The two PRD-load artifacts are the reference, gated pair.
    assert prd["reference"] is True
    assert prd["gating"] is True
    assert prd["seed"] == 20260914
    assert prd["host"], "the host disclosure is non-empty"
    assert prd["simulation"] is True
    reads = prd["measurements"]["prd-load-reads"]
    acceptance = prd["measurements"]["prd-load-acceptance"]
    assert reads["count"] == 6
    assert reads["observers"] == 2
    assert reads["active_run"] is True
    assert 0.0 < reads["active_run_coverage"] <= 1.0
    assert reads["target_p95_ms"] == 500
    assert reads["verdict"] in {"pass", "fail"}
    assert reads["verdict"] == ("pass" if reads["p95_ms"] <= 500 else "fail")
    assert acceptance["count"] == 3
    assert acceptance["observers"] == 1  # sequential on the one lattice bench
    assert acceptance["target_p95_ms"] == 2000
    assert acceptance["verdict"] == ("pass" if acceptance["p95_ms"] <= 2000 else "fail")

    # The stress tier is labelled non-reference and non-gating.
    assert stress["reference"] is False
    assert stress["gating"] is False
    assert stress["seed"] == 20260914
    measurement = stress["measurements"]["stress-16"]
    assert measurement["count"] == 16 * 2
    assert measurement["observers"] == 16
    assert "verdict" not in measurement or measurement.get("verdict") == "recorded"

    # The emitted payload and the retained files agree on the numbers.
    assert payload["measurements"]["prd-load-reads"]["p95_ms"] == reads["p95_ms"]
