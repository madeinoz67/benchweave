"""Fault arms for the worker poison guard's terminal record (issue #513).

The poison arm (``RunWorker._drain_with``'s ``except BaseException``)
closed the queue projection terminal WITHOUT a durable terminal record,
and the next-boot sweep skips rows whose projection already reads
terminal — the gap was unhealable. These arms pin the #513 fix:
``finalize_poisoned_run`` attempts a recovery-shaped record on the
poison path, judgeable cohort only, NEVER over an existing record, and
a record-write failure changes nothing about the outcome or the drain.

- F1 — the judgeable poison gains a record (RED at base: the mechanism
  does not exist).
- F2 — the overwrite guard: a record landed by the run's own machinery
  (the ``_finish_run`` non-Exception pending re-raise shape) survives
  the poison branch byte-for-byte.
- F3 — the #507 containment boundary: a doc/echo-disagreement poison
  (the ``test_recovery_sweep_faults.py`` era-disagreement shape) writes
  NO record; the projection still closes terminal with the frozen
  contract's ``outcome_unknown`` wire shape, and the containment log
  line is the operator's evidence.
- F4 — A07 liveness: a failing ``finalize_run`` is contained — the
  projection closes, the drain continues, the failure is disclosed in
  the gateway log.

Harness shape: ``tests/faults/test_worker_drain_faults.py`` — real
``Store``, seeded bench row, bounded join, the poison injected at the
fake ``build_run``/``start_run`` seam (no timing, no load). Run rows are
created exactly as ``Operations.run_start`` creates them (``create_run``
with the caller-echo binding, ``put_run_state`` accepted) — acceptance
precedes submit, so the judge sees the production shape.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.control.coordinator import _CONTRACTS, build_terminal_record
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.worker import RunWorker
from benchweave.state.store import Store

BENCH_ID = "bench.poison-record"
NOW = "2026-11-08T00:00:00Z"
# Pre-committed observation bound (design record §9): the fake-seam
# poisons drain in milliseconds — 30 s is three orders of magnitude of
# slack. This bounds the TEST's observation, never the production join.
T_OBS = 30.0

#: The caller-echo binding of a JUDGEABLE run: the echo names the
#: composition (carried by definition, ``_recovery_record_version``
#: composition arm) and the digest names no stored document, so the
#: decision is the composition record — synthetic names, never a real
#: corpus.
BINDING: dict[str, Any] = {
    "id": "req-poison-1",
    "version": _CONTRACTS.name,
    "sha256": "0" * 64,
}


class _NoopRun:
    """RunCoordinator stand-in: ``start_run`` writes no terminal record
    (the healthy job — its completion close is projection-only)."""

    def start_run(self, run_id: str, principal_id: str) -> dict[str, Any]:
        del run_id, principal_id
        return {}

    def cancel(self, run_id: str, principal_id: str) -> None:
        del run_id, principal_id


class _FinalizingThenRaisingRun:
    """The ``_finish_run`` pending re-raise shape: ``start_run`` lands a
    REAL record (``build_terminal_record`` + ``finalize_run``) and THEN
    raises ``KeyboardInterrupt`` — the belt re-raises the non-Exception
    pending AFTER the record, so the poison branch fires with the
    record already on the row."""

    def __init__(self, run_id: str, store: Store) -> None:
        self._run_id = run_id
        self._store = store
        self.written: dict[str, Any] | None = None

    def start_run(self, run_id: str, principal_id: str) -> dict[str, Any]:
        del principal_id
        record = build_terminal_record(
            run_id=run_id,
            binding_pin=BINDING,
            principal_id="p1",
            started_at=NOW,
            ended_at=NOW,
            body_outcome="completed",
            safe_state="verified",
            reasons=["synthetic healthy completion"],
            evidence_refs=[
                BINDING,
                {
                    "id": f"events:{run_id}",
                    "version": "1",
                    "sha256": hashlib.sha256(b"poison-fixture-events").hexdigest(),
                },
            ],
            contracts=_CONTRACTS,
        )
        self._store.finalize_run(run_id, record)
        self.written = record
        raise KeyboardInterrupt()

    def cancel(self, run_id: str, principal_id: str) -> None:
        del run_id, principal_id


def _seed_run(store: Store, run_id: str, binding: dict[str, Any]) -> None:
    """The run row exactly as ``Operations.run_start`` leaves it after
    acceptance: ``create_run`` with the caller-echo binding, then the
    ``accepted`` queue projection."""
    store.create_run(run_id, binding=binding, principal_id="p1", now=NOW)
    store.put_run_state(run_id, BENCH_ID, "accepted", NOW)


def _open_store(tmp_path: Path, name: str) -> tuple[Store, ContentStore]:
    store = Store.open(tmp_path / name)
    content = ContentStore(store)
    # The drain-side emits anchor their bench events on the bench's
    # configuration row (the test_worker_drain_faults.py harness shape).
    store.put_bench(BENCH_ID, 1, "qualification", "{}", "licence", NOW)
    return store, content


def _wire_projection(store: Store, run_id: str) -> dict[str, Any]:
    """The seam's own run projection over this store — the wire object a
    client reads (``Operations._run_projection`` needs only the store)."""
    operations = Operations.__new__(Operations)
    operations._store = store
    return operations._run_projection(run_id)


def _state(store: Store, run_id: str) -> str | None:
    row = store.get_run_state(run_id)
    return None if row is None else str(row["state"])


# --- F1: the judgeable poison gains a record --------------------------------------


def test_poison_writes_judgeable_terminal_record(
    tmp_path: Path,
) -> None:
    """F1: a construction-arm poison (``build_run`` raises) over a
    judgeable run leaves a durable terminal record — outcome_unknown /
    unknown, the poison line as ``reasons[0]``, the recovery evidence
    refs — and the drain continues with the next queued run."""
    store, content = _open_store(tmp_path, "poison-f1.db")
    poisoned = "run-poison-f1"
    healthy = "run-poison-f1b"
    _seed_run(store, poisoned, dict(BINDING, id="req-poison-1"))
    _seed_run(store, healthy, dict(BINDING, id="req-poison-1b"))

    def build_run(
        run_id: str,
        principal_id: str,
        binding: dict[str, Any],
        run_store: Store,
    ) -> Any:
        del principal_id, binding, run_store
        if run_id == poisoned:
            raise RuntimeError("boom")
        return _NoopRun()

    worker = RunWorker(store, content, build_run=build_run, now_iso=lambda: NOW)
    worker.start()
    try:
        worker.submit(poisoned, "p1", dict(BINDING, id="req-poison-1"), BENCH_ID)
        worker.submit(healthy, "p1", dict(BINDING, id="req-poison-1b"), BENCH_ID)
        assert worker.join(timeout=T_OBS), "the worker did not drain both jobs"

        row = store.get_run(poisoned)
        assert row is not None and row["terminal"] is not None, (
            f"the judgeable poison must gain a terminal record; row={row}"
        )
        record = row["terminal"]
        assert record["outcome"] == "outcome_unknown", record
        assert record["safe_state"] == "unknown", record
        assert record["body_outcome"] == "outcome_unknown", record
        assert record["reasons"][0] == "run_worker poison: RuntimeError: boom", record
        assert len(record["evidence_refs"]) >= 2, record
        assert _state(store, poisoned) == "terminal", "projection must close terminal"
        # The drain continued: the healthy job completed after the poison.
        assert _state(store, healthy) == "terminal", (
            f"the drain must continue past the poison; states="
            f"{_state(store, poisoned)!r}/{_state(store, healthy)!r}"
        )
    finally:
        worker.stop()
        worker.join(timeout=5.0)
        store.close()


# --- F2: the overwrite guard -------------------------------------------------------


def test_poison_never_overwrites_a_landed_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """F2: the poison branch fires over a run whose own machinery already
    landed a record (the ``_finish_run`` non-Exception pending re-raise
    shape) — the ORIGINAL record survives byte-for-byte; no
    ``run_worker poison`` reason is written over it."""
    store, content = _open_store(tmp_path, "poison-f2.db")
    run_id = "run-poison-f2"
    _seed_run(store, run_id, BINDING)
    fake: _FinalizingThenRaisingRun | None = None

    def build_run(
        run_id_arg: str,
        principal_id: str,
        binding: dict[str, Any],
        run_store: Store,
    ) -> Any:
        del principal_id, binding
        nonlocal fake
        fake = _FinalizingThenRaisingRun(run_id_arg, run_store)
        return fake

    worker = RunWorker(store, content, build_run=build_run, now_iso=lambda: NOW)
    worker.start()
    try:
        with caplog.at_level(logging.ERROR, logger="benchweave.interfaces.worker"):
            worker.submit(run_id, "p1", BINDING, BENCH_ID)
            assert worker.join(timeout=T_OBS), "the worker did not drain"
        assert fake is not None and fake.written is not None, (
            "the fake never landed its record — the fixture is broken"
        )
        # The poison branch really fired (the log line, not silence).
        assert "run_worker poison" in caplog.text, caplog.text
        row = store.get_run(run_id)
        assert row is not None, "the run row must survive"
        assert row["terminal"] == fake.written, (
            "the landed record must survive the poison branch byte-for-byte;"
            f" landed={fake.written!r}; after={row['terminal']!r}"
        )
        assert not any(
            "run_worker poison" in reason for reason in row["terminal"]["reasons"]
        ), row["terminal"]
        assert _state(store, run_id) == "terminal"
    finally:
        worker.stop()
        worker.join(timeout=5.0)
        store.close()


# --- F3: the containment boundary --------------------------------------------------


def test_contained_poison_writes_no_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """F3 (the #507 boundary): a doc/echo-disagreement poison (the era
    containment shape) writes NO record — no record is safe — while the
    projection still closes terminal and the wire reads the frozen
    contract's outcome_unknown shape. The unresolved log line is the
    operator's evidence."""
    store, content = _open_store(tmp_path, "poison-f3.db")
    run_id = "run-poison-f3"
    # The era-disagreement shape (test_recovery_sweep_faults.py): a
    # stored document whose const classifies as a CARRIED dialect
    # (0.1.0) beside a disagreeing carried echo (the composition).
    document = {
        "request_id": "req-poison-contained",
        "contract_version": "0.1.0",
        "bench": {"sha256": "0" * 64},
    }
    raw = json.dumps(document).encode()
    digest = hashlib.sha256(raw).hexdigest()
    content.put_document(raw, digest, document, "urn:stg:test", NOW)
    binding = {
        "id": "req-poison-contained",
        "version": _CONTRACTS.name,
        "sha256": digest,
    }
    _seed_run(store, run_id, binding)

    def build_run(
        run_id_arg: str,
        principal_id: str,
        binding_arg: dict[str, Any],
        run_store: Store,
    ) -> Any:
        del run_id_arg, principal_id, binding_arg, run_store
        raise RuntimeError("boom")

    worker = RunWorker(store, content, build_run=build_run, now_iso=lambda: NOW)
    worker.start()
    try:
        with caplog.at_level(logging.ERROR):
            worker.submit(run_id, "p1", binding, BENCH_ID)
            assert worker.join(timeout=T_OBS), "the worker did not drain"
        row = store.get_run(run_id)
        assert row is not None, "the run row must survive"
        assert row["terminal"] is None, (
            f"no record is safe under doc/echo disagreement; got {row['terminal']!r}"
        )
        assert _state(store, run_id) == "terminal", "the projection must close"
        projection = _wire_projection(store, run_id)
        assert projection["state"] == "terminal", projection
        assert projection["outcome"] == "outcome_unknown", projection
        assert projection["safe_state"] == "unknown", projection
        assert projection["terminal_record"] is None, projection
        assert any(
            "recovery_execution_version_unresolved" in record.getMessage()
            and run_id in record.getMessage()
            for record in caplog.records
        ), f"the containment must be logged: {[r.getMessage() for r in caplog.records]}"
    finally:
        worker.stop()
        worker.join(timeout=5.0)
        store.close()


# --- F4: A07 liveness under a record-write failure ----------------------------------


def test_record_write_failure_never_blocks_the_drain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """F4 (A07): a failing ``finalize_run`` is contained — the projection
    still closes terminal, the drain continues with the next queued run,
    the failure is disclosed in the gateway log, and nothing raises out
    of the poison handler. Evidence storage is a dependency of neither
    the containment nor the worker's liveness."""

    def failing_finalize(self: Store, run_id: str, terminal: dict[str, Any]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Store, "finalize_run", failing_finalize)
    store, content = _open_store(tmp_path, "poison-f4.db")
    poisoned = "run-poison-f4"
    healthy = "run-poison-f4b"
    _seed_run(store, poisoned, dict(BINDING, id="req-poison-4"))
    _seed_run(store, healthy, dict(BINDING, id="req-poison-4b"))

    def build_run(
        run_id: str,
        principal_id: str,
        binding: dict[str, Any],
        run_store: Store,
    ) -> Any:
        del principal_id, binding, run_store
        if run_id == poisoned:
            raise RuntimeError("boom")
        return _NoopRun()

    worker = RunWorker(store, content, build_run=build_run, now_iso=lambda: NOW)
    worker.start()
    try:
        with caplog.at_level(logging.ERROR, logger="benchweave.interfaces.worker"):
            worker.submit(poisoned, "p1", dict(BINDING, id="req-poison-4"), BENCH_ID)
            worker.submit(healthy, "p1", dict(BINDING, id="req-poison-4b"), BENCH_ID)
            assert worker.join(timeout=T_OBS), (
                "the worker did not drain both jobs — the write failure killed"
                " the drain"
            )
        assert _state(store, poisoned) == "terminal", (
            "the projection must close even when the record write fails"
        )
        assert _state(store, healthy) == "terminal", "the drain must continue"
        row = store.get_run(poisoned)
        assert row is not None and row["terminal"] is None, row
        assert "run_worker poison record failed" in caplog.text, caplog.text
        assert "run_worker poison run_id=" in caplog.text, caplog.text
    finally:
        worker.stop()
        worker.join(timeout=5.0)
        store.close()
