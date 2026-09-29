"""Fault arms for the startup sweep's run-state-aware leg (issue #156 fix wave).

The refute pass executed two wedges the lease-held sweep cannot see:

- F1 — a queued ghost (an ``accepted`` projection over a durable run row,
  never started, no lease) survives every restart in LIVE_RUN_STATES, so
  the §5 busy oracle (any live row owns the bench,
  ``Operations._assert_bench_acceptable``) refuses every future run_start
  on that bench, forever. Reachable since the shutdown drain bound became
  real: a queued-not-started run is abandoned at the bound and the worker
  never opens it.
- F2 — a stale ``running`` projection over a DURABLE terminal record (the
  worker's contained close failed at ``put_run_state`` after the
  coordinator's ``finalize_run``) wedges the same way: no lease, so the
  lease scan is blind to it.

Both arms seed the split state directly over a real Store and drive the
app-level sweep (``_recover_interrupted_runs``, the lifespan's ONE
recovery entrypoint), mirroring ``tests/faults/test_capture_recovery.py``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.content.store import ContentStore
from benchweave.control.coordinator import build_terminal_record
from benchweave.interfaces.app import _recover_interrupted_runs
from benchweave.interfaces.operations import LIVE_RUN_STATES
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
BENCH_ID = "sim-bench"  # the bootstrap bench (fixtures/execution/bench.json)
NOW = "2026-09-23T00:00:00Z"
#: Synthetic closed binding ref — invented names, never a real corpus. The
#: version agrees with the composition the sweep admits through (the sweep
#: mechanics arms below pin discovery/terminalisation/projection-close, not
#: version agreement; DISAGREEMENT is its own pinned behavior — the era
#: cohort arms at the bottom, issue #220 fold).
BINDING: dict[str, Any] = {"id": "req-sweep-ghost", "version": "0.2.0", "sha256": "0" * 64}


def _busy(store: Store) -> bool:
    """The busy oracle's own predicate: any live row owns the bench."""
    return any(row["state"] in LIVE_RUN_STATES for row in store.list_run_states(BENCH_ID))


def _states(store: Store) -> list[tuple[str, str]]:
    return [(str(row["run_id"]), str(row["state"])) for row in store.list_run_states(BENCH_ID)]


def _sweep(store: Store) -> list[str]:
    return _recover_interrupted_runs(store, FIXTURES, emit_keep=100, now_iso=lambda: NOW)


def _run_changed(store: Store, run_id: str) -> bool:
    return any(
        event.get("kind") == "run_changed" and event.get("run_id") == run_id
        for event in store.read_events(f"bench.{BENCH_ID}")
    )


# --- F1: the queued ghost --------------------------------------------------------


def test_sweep_records_queued_ghost_interrupted_and_unwedges_bench(
    tmp_path: Path,
) -> None:
    """Accepted projection + durable run row + never started + no lease:
    the sweep must record it ``interrupted`` (the CTL-9 honest record,
    never a fabricated outcome) and clear the busy oracle — the refute
    pass left this row wedged in LIVE_RUN_STATES forever."""
    store = Store.open(tmp_path / "queued-ghost.db")
    try:
        store.create_run("run-q1", BINDING, "p1", NOW)
        store.put_run_state("run-q1", BENCH_ID, "accepted", NOW)
        assert _busy(store) is True  # pre-condition: the wedge is real

        recovered = _sweep(store)

        assert recovered == ["run-q1"], (
            f"sweep missed the queued ghost; recovered={recovered},"
            f" run_states={_states(store)}"
        )
        run = store.get_run("run-q1")
        assert run is not None
        terminal = run["terminal"]
        assert terminal is not None, "the ghost must gain a durable terminal record"
        assert terminal["body_outcome"] == "interrupted"
        assert terminal["safe_state"] == "unknown"
        assert terminal["outcome"] == "interrupted"
        assert _busy(store) is False, (
            f"queued ghost left the bench busy forever; run_states={_states(store)}"
        )
        assert _run_changed(store, "run-q1"), "the recovery state change is on the stream"
        assert _sweep(store) == [], "a second restart must find nothing left to sweep"
    finally:
        store.close()


# --- F2: the stale projection over a durable terminal ----------------------------


def test_sweep_reconciles_stale_running_projection_over_durable_terminal(
    tmp_path: Path,
) -> None:
    """Durable terminal record + stale ``running`` projection + no lease
    (the contained worker close failed at ``put_run_state``): the sweep
    must reconcile the projection to terminal and NEVER interrupt a run
    whose durable record says it completed."""
    record = build_terminal_record(
        run_id="run-q3",
        binding_pin=BINDING,
        principal_id="p1",
        started_at=NOW,
        ended_at=NOW,
        body_outcome="completed",
        safe_state="verified",
        reasons=["synthetic completed run"],
        evidence_refs=[BINDING],
    )
    store = Store.open(tmp_path / "stale-projection.db")
    try:
        store.create_run("run-q3", BINDING, "p1", NOW)
        store.finalize_run("run-q3", record)
        store.put_run_state("run-q3", BENCH_ID, "running", NOW)
        assert _busy(store) is True

        recovered = _sweep(store)

        assert recovered == ["run-q3"], (
            f"sweep left the stale projection untouched; recovered={recovered},"
            f" run_states={_states(store)}"
        )
        run = store.get_run("run-q3")
        assert run is not None
        assert run["terminal"] == record, "the durable record is the truth — untouched"
        row = store.get_run_state("run-q3")
        assert row is not None and row["state"] == "terminal"
        assert _busy(store) is False, (
            f"stale projection left the bench busy forever; run_states={_states(store)}"
        )
        assert _run_changed(store, "run-q3"), "the reconciled state change is on the stream"
        assert _sweep(store) == [], "a second restart must find nothing left to sweep"
    finally:
        store.close()


# --- order/edge probe: durable terminal + active lease + live projection ---------


def test_sweep_probe_terminal_with_stale_lease_and_live_projection(
    tmp_path: Path,
) -> None:
    """Order/edge probe (fix-wave instruction): a durable terminal record
    with an ACTIVE ``run:`` lease and a live projection. CTL-9's ordering
    (finalize_run → lease release → projection close) makes the window
    narrow, not impossible — a crash between ``finalize_run`` and the
    coordinator's lease release lands exactly here. Documented behavior of
    the composed sweep: the lease leg releases the stale lease without
    interrupting (the durable record already ends the run), then the
    run-state leg reconciles the projection — the bench un-wedges either
    way, and the completed record is never rewritten."""
    record = build_terminal_record(
        run_id="run-q4",
        binding_pin=BINDING,
        principal_id="p1",
        started_at=NOW,
        ended_at=NOW,
        body_outcome="completed",
        safe_state="verified",
        reasons=["synthetic completed run"],
        evidence_refs=[BINDING],
    )
    store = Store.open(tmp_path / "terminal-stale-lease.db")
    try:
        store.create_run("run-q4", BINDING, "p1", NOW)
        store.finalize_run("run-q4", record)
        store.put_run_state("run-q4", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-stale", holder="run:run-q4", expires_at="2030-01-01T00:00:00Z"
        )
        assert _busy(store) is True

        recovered = _sweep(store)

        assert recovered == ["run-q4"], (
            f"composed sweep left the wedge; recovered={recovered},"
            f" run_states={_states(store)}"
        )
        run = store.get_run("run-q4")
        assert run is not None
        assert run["terminal"] == record, "a terminal run is never re-finalised"
        assert store.get_active_lease(BENCH_ID) is None, "the stale lease is released"
        row = store.get_run_state("run-q4")
        assert row is not None and row["state"] == "terminal"
        assert _busy(store) is False
        assert _sweep(store) == []
    finally:
        store.close()


# --- the era cohort: a stored run older than the composition (issue #220 fold) ---

#: The pre-promotion cohort (execution 0.1.0 ran on this store before 54a59fa
#: promoted 0.2.0): an upgrade brings the OLD lattice in fixtures and the NEW
#: gateway. The stored binding's version is the era's fact — recovery must
#: neither rewrite it into the active record dialect (laundering) nor crash.
ERA_BINDING: dict[str, Any] = {"id": "req-era-1", "version": "0.1.0", "sha256": "0" * 64}
LATTICE_010 = ROOT / "tests" / "fixtures" / "lattice-execution-0.1.0"

#: The #220 fold's typed containment reason — RETIRED by issue #260 (the
#: runs it named are terminalized now). The constant stays only for the
#: retirement assertion (the new prefix must fully replace it in the log).
SKIP_LOG = "recovery_execution_version_not_runnable"
#: The narrowed containment prefix (issue #260): the class is
#: "unresolvable", not "not runnable".
UNSOLVED_LOG = "recovery_execution_version_unresolved"


def _era_schema_path() -> Path:
    """The digest-verified 0.1.0 run-record schema (the era arms' KILL
    arm: the record validates at ITS version's schema)."""
    from benchweave.control.documents import _corpus_root_of, _versioned_schema_path
    from benchweave.vendoring import active_contract_family

    return _versioned_schema_path(
        _corpus_root_of(active_contract_family("execution")),
        "execution",
        "0.1.0",
        "run-record.schema.json",
    )


def _era_sweep(store: Store) -> list[str]:
    """The sweep over the 0.1.0 lattice — the upgrade path's own posture
    (post-slice the lattice ADMITS at startup; recovery is the remaining
    record-writer)."""
    return _recover_interrupted_runs(store, LATTICE_010, emit_keep=100, now_iso=lambda: NOW)


def test_era_lease_held_run_terminalizes_against_its_own_version(
    tmp_path: Path,
) -> None:
    """The record lane (issue #260), flipping the #220 fold's skip: a store
    holding a non-terminal 0.1.0-era run (binding version 0.1.0, an active
    run: lease, no stored binding doc — the era fixture's zero digest)
    terminalizes against its OWN version: contract_version 0.1.0, validated
    against the digest-verified 0.1.0 schema, the implementation
    disclosure riding the reasons, the lease released, and the run REPORTED
    for projection close (the bench-busy wedge clears — the upgrade-path
    win). RED at the fold base: the skip left terminal None."""
    import jsonschema

    store = Store.open(tmp_path / "era-lease.db")
    try:
        store.create_run("run-era-1", ERA_BINDING, "p1", NOW)
        store.put_run_state("run-era-1", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-era-1", holder="run:run-era-1", expires_at=NOW
        )
        recovered = _era_sweep(store)
        assert recovered == ["run-era-1"], (
            f"an era run is now terminalized and reported for projection "
            f"close; recovered={recovered}"
        )
        run = store.get_run("run-era-1")
        assert run is not None
        record = run["terminal"]
        assert record is not None, "the era record now lands"
        assert record["contract_version"] == "0.1.0", record
        assert record["binding"]["version"] == "0.1.0"
        assert record["outcome"] == "interrupted"
        assert record["safe_state"] == "unknown"
        assert any(
            reason.startswith("implementation_disclosure:")
            and "execution@0.2.0" in reason
            and "execution@0.1.0" in reason
            for reason in record["reasons"]
        ), record["reasons"]
        # The era record validates at ITS schema (digest-verified bytes).
        schema_path = _era_schema_path()
        jsonschema.Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8"))
        ).validate(record)
        assert _busy(store) is False, "the wedge clears"
    finally:
        store.close()


def test_era_ghost_run_terminalizes_against_its_own_version(
    tmp_path: Path,
) -> None:
    """The record lane, second leg: the same era cohort through the
    run-state leg (no lease — the queued-ghost shape). Same
    terminalization: contract_version 0.1.0, reported for projection close
    (the caller marks reported ids terminal — no laundering, the record IS
    the run's own dialect now). Idempotent: a second sweep finds the
    durable terminal and only reconciles."""
    store = Store.open(tmp_path / "era-ghost.db")
    try:
        store.create_run("run-era-2", ERA_BINDING, "p1", NOW)
        store.put_run_state("run-era-2", BENCH_ID, "accepted", NOW)
        recovered = _era_sweep(store)
        assert recovered == ["run-era-2"], f"recovered={recovered}"
        run = store.get_run("run-era-2")
        assert run is not None
        assert run["terminal"] is not None
        assert run["terminal"]["contract_version"] == "0.1.0"
        assert _busy(store) is False, "the wedge clears"
        # Idempotent: the second sweep reconciles nothing (the durable
        # terminal is the truth).
        assert _era_sweep(store) == []
    finally:
        store.close()


def test_era_lying_echo_doc_first_composition_terminalization(
    tmp_path: Path,
) -> None:
    """G5a (the D4 upgrade): a stored binding doc whose const says
    ``0.2.0`` (the composition) beside a lying ``0.1.0`` echo — the DOC is
    the stronger evidence (digest-pinned bytes, never the caller's echo):
    the NORMAL composition terminalization fires. RED at the fold base:
    the base classified the ECHO and skipped."""
    store = Store.open(tmp_path / "era-lying.db")
    try:
        content = ContentStore(store)
        binding = dict(ERA_BINDING, version="0.1.0")
        document = {
            "request_id": str(binding["id"]),
            "contract_version": "0.2.0",
            "bench": {"sha256": "0" * 64},
        }
        raw = json.dumps(document).encode()
        content.put_document(
            raw, hashlib.sha256(raw).hexdigest(), document, "urn:stg:test", NOW
        )
        stored = dict(binding, sha256=hashlib.sha256(raw).hexdigest())
        store.create_run("run-era-3", stored, "p1", NOW)
        store.put_run_state("run-era-3", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-era-3", holder="run:run-era-3", expires_at=NOW
        )
        recovered = _era_sweep(store)
        run = store.get_run("run-era-3")
        assert run is not None
        assert run["terminal"] is not None, "the doc-first record lands"
        assert run["terminal"]["contract_version"] == "0.2.0", (
            "the doc names THIS composition — the normal record, the lying "
            "echo ignored"
        )
        assert recovered == ["run-era-3"]
    finally:
        store.close()


def test_era_doc_echo_disagreement_is_contained(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """G5b (containment): a doc const that classifies as a CARRIED dialect
    (``0.1.0``) beside a disagreeing carried echo (``0.2.0``) — no record
    is safe (the two surviving artifacts contradict each other about what
    ran). No record, the run stays non-terminal, logged under the NEW
    narrowed prefix ``recovery_execution_version_unresolved:`` (the old
    ``recovery_execution_version_not_runnable:`` RETIRED). RED at base:
    without the containment check the record would carry the doc's
    version beside a contradicting echo."""
    import logging

    store = Store.open(tmp_path / "era-disagree.db")
    try:
        content = ContentStore(store)
        document = {
            "request_id": "req-era-4",
            "contract_version": "0.1.0",
            "bench": {"sha256": "0" * 64},
        }
        raw = json.dumps(document).encode()
        content.put_document(
            raw, hashlib.sha256(raw).hexdigest(), document, "urn:stg:test", NOW
        )
        stored = dict(
            ERA_BINDING,
            id="req-era-4",
            version="0.2.0",
            sha256=hashlib.sha256(raw).hexdigest(),
        )
        store.create_run("run-era-4", stored, "p1", NOW)
        store.put_run_state("run-era-4", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-era-4", holder="run:run-era-4", expires_at=NOW
        )
        with caplog.at_level(logging.ERROR, logger="benchweave.control.coordinator"):
            recovered = _era_sweep(store)
        assert recovered == [], f"a contained run is not reported; recovered={recovered}"
        run = store.get_run("run-era-4")
        assert run is not None
        assert run["terminal"] is None, "no record is safe under disagreement"
        assert any(
            UNSOLVED_LOG in record.message and "run-era-4" in record.message
            for record in caplog.records
        ), f"the narrowed containment prefix must be logged: {[r.message for r in caplog.records]}"
        assert not any(
            SKIP_LOG in record.message for record in caplog.records
        ), "the old prefix is retired — it names no run anymore"
    finally:
        store.close()


def test_caller_data_ref_version_terminalizes_as_before(tmp_path: Path) -> None:
    """Fold row 1's boundary, the other side: the stored binding version is
    the §5 ref's caller-supplied echo (D4 — the frozen contract types it as
    any non-empty string), so it is JUDGED, never trusted. A version the
    corpus never carried as a served dialect ("1.0.0" is RETIRED — no
    gateway ever ran it) is caller data, not an era fact: the sweep
    terminalises exactly as before the fold, and the record's
    contract_version literal beside it faithfully records the ref. (The
    real-path twin: the child-process kill-mid-run suite posts exactly such
    a ref and must keep recovering.)"""
    store = Store.open(tmp_path / "caller-data.db")
    try:
        store.create_run("run-cd-1", BINDING, "p1", NOW)
        store.put_run_state("run-cd-1", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-cd-1", holder="run:run-cd-1", expires_at=NOW
        )
        recovered = _sweep(store)
        assert recovered == ["run-cd-1"], f"recovered={recovered}"
        run = store.get_run("run-cd-1")
        assert run is not None
        assert run["terminal"] is not None, (
            "a caller-data version is not an era fact — the honest "
            "interrupted record still lands"
        )
        assert run["terminal"]["binding"]["version"] == BINDING["version"]
        assert run["terminal"]["contract_version"] == "0.2.0"
    finally:
        store.close()
