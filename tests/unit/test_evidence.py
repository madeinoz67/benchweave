"""The seeded volume generator's accounting (WP09 Task 7, Step 1).

A 3-run smoke over the REAL generator — one ephemeral simulation gateway
(the ``benchweave.cli.demo`` fresh-install idiom, booted in-process) driving
three consecutive seeded journey runs — pinning the summary accounting, the
per-run record shape, and the seed derivation. The per-run consistency gate
(outcome, durable record, digest resolution, dispatch oracle) lives in the
generator and aborts loudly; if it ever fires here the test fails with its
truthful message, never a fabricated summary.
"""

from __future__ import annotations

import json
from pathlib import Path

from benchweave.cli.evidence import generate_runs

#: The per-run record's complete key set (lean by contract: ids, digests,
#: outcome, timings — full logs never ride a record).
_RECORD_KEYS = frozenset(
    {
        "index",
        "seed",
        "request_id",
        "run_id",
        "bench_id",
        "state",
        "outcome",
        "safe_state",
        "terminal_sha256",
        "binding_sha256",
        "events_digest",
        "dispatch_occurrences",
        "started_at",
        "duration_s",
    }
)


def test_generate_runs_three_run_smoke(tmp_path: Path) -> None:
    summary = generate_runs(tmp_path, count=3, seed=20260914)

    # Summary accounting (the Step-1 contract).
    assert summary["count"] == 3
    assert summary["outcomes"] == ["passed", "passed", "passed"]
    assert summary["duplicate_dispatch_total"] == 0
    assert summary["seed"] == 20260914
    assert summary["host"], "the host disclosure is non-empty"
    assert summary["simulation"] is True

    # A healthy body dispatches eight device operations (the journey
    # suite's occurrence oracle: configure, enable, note, model, measure,
    # remeasure x3) — three runs, none duplicated.
    assert summary["dispatch_occurrences_total"] == 24

    # The retained evidence tree: one lean record per run + the summary.
    runs_dir = tmp_path / "runs"
    assert sorted(path.name for path in runs_dir.glob("run-*.json")) == [
        "run-001.json",
        "run-002.json",
        "run-003.json",
    ]
    summary_file = runs_dir / "summary.json"
    persisted = json.loads(summary_file.read_text(encoding="utf-8"))
    assert persisted["count"] == 3
    assert persisted["outcomes"] == ["passed", "passed", "passed"]
    assert persisted["duplicate_dispatch_total"] == 0

    first = json.loads((runs_dir / "run-001.json").read_text(encoding="utf-8"))
    assert set(first) == set(_RECORD_KEYS)
    assert first["index"] == 1
    assert first["seed"] == 20260915  # seed + N, per-run derivation
    assert first["request_id"] == "req-volume-20260915"
    assert first["state"] == "terminal"
    assert first["outcome"] == "passed"
    assert first["safe_state"] == "verified"
    assert len(first["terminal_sha256"]) == 64
    assert len(first["binding_sha256"]) == 64
    assert len(first["events_digest"]) == 64
    assert first["dispatch_occurrences"] == 8
    assert first["duration_s"] >= 0.0
    assert first["started_at"].endswith("Z")

    # Consecutive runs are distinct journeys: distinct seeds, requests, runs.
    third = json.loads((runs_dir / "run-003.json").read_text(encoding="utf-8"))
    assert third["seed"] == 20260917
    assert third["request_id"] == "req-volume-20260917"
    assert third["run_id"] != first["run_id"]
