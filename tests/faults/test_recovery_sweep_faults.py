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


def _wire_projection(store: Store, run_id: str) -> dict[str, Any]:
    """The seam's own run projection over this store — the wire object a
    client reads (``Operations._run_projection`` needs only the store)."""
    from benchweave.interfaces.operations import Operations

    operations = Operations.__new__(Operations)
    operations._store = store
    return operations._run_projection(run_id)


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
    """G5a (the D4 upgrade), re-armed by fold row 3: a stored binding doc
    whose const says ``0.2.0`` (the composition) beside a lying ``0.1.0``
    carried echo — the DOC is the stronger evidence (digest-pinned bytes,
    never the caller's echo): the record stamps the DOCUMENT's binding
    block (contract_version AND binding.version name one artifact — the
    machine self-consistency check), the disagreeing carried echo rides as
    an ``implementation_disclosure:`` reason, never a silent
    contradiction. RED at the fold base: the base classified the ECHO and
    skipped; at the slice head the record persisted 0.2.0 beside the
    0.1.0 echo with zero disclosure (adv2's machine check)."""
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
        record = run["terminal"]
        assert record["contract_version"] == "0.2.0", (
            "the doc names THIS composition — the normal record, the lying "
            "echo ignored"
        )
        # Fold row 3 (case E): the record's binding block stamps FROM THE
        # DOCUMENT, and the disagreeing carried echo rides as a disclosure.
        assert record["binding"]["version"] == "0.2.0", record["binding"]
        assert any(
            reason.startswith("implementation_disclosure:")
            and "execution@0.1.0" in reason
            and "the digest-pinned document governs" in reason
            for reason in record["reasons"]
        ), record["reasons"]
        # adv2's machine check: record self-consistency — the record's
        # contract_version equals its binding.version (the echo IS
        # carried, so the first disjunct must hold).
        assert record["contract_version"] == record["binding"]["version"]
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
        assert _busy(store) is True, (
            "pre-condition: the contained run's live row owns the bench"
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
        # Fold row 8: the reason names the CONSTS, not a digest fragment —
        # an operator reads what disagreed, not where.
        assert any(
            UNSOLVED_LOG in record.message
            and "0.1.0" in record.message
            and "0.2.0" in record.message
            for record in caplog.records
        ), "the containment must name both consts (row 8)"
        assert not any(
            SKIP_LOG in record.message for record in caplog.records
        ), "the old prefix is retired — it names no run anymore"
        # Issue #507: containment keeps the bench bookable. The projection
        # closes terminal OVER THE MISSING RECORD — the wire reads the
        # contract's outcome_unknown shape, never a fabricated outcome.
        assert _busy(store) is False, (
            f"the contained run left the bench busy forever; run_states={_states(store)}"
        )
        row = store.get_run_state("run-era-4")
        assert row is not None and row["state"] == "terminal", (
            f"the contained run's projection must close; run_states={_states(store)}"
        )
        projection = _wire_projection(store, "run-era-4")
        assert projection["state"] == "terminal", projection
        assert projection["outcome"] == "outcome_unknown", projection
        assert projection["safe_state"] == "unknown", projection
        assert projection["terminal_record"] is None, projection
        assert _run_changed(store, "run-era-4"), (
            "the contained projection close is on the bench stream"
        )
        # Idempotent: a second sweep finds a terminal row and no work, and
        # the durable record is still absent (no laundering on re-boot).
        assert _era_sweep(store) == []
        assert _busy(store) is False
        run_after = store.get_run("run-era-4")
        assert run_after is not None
        assert run_after["terminal"] is None, "no sweep may invent a record"
    finally:
        store.close()


def test_caller_data_ref_version_terminalizes_as_before(tmp_path: Path) -> None:
    """The caller-data boundary (fold-corrected to the THREE-WAY echo
    disposition): the stored binding version is the §5 ref's caller-supplied
    echo (D4 — the frozen contract types it as any non-empty string), judged
    never trusted. An echo with NO retained bytes ("1.0.0" is a RETIRED
    identifier — its directory is gone from the corpus) is caller data: the
    sweep terminalizes exactly as before the fold (the honest-ref class;
    the integration harnesses post exactly these refs and must keep
    recovering — the supervised battery caught the over-broad containment
    wedging them). The three-way's other legs: a carried echo era-stamps;
    a retired-but-RETAINED echo era-stamps FROM THE RETAINED BYTES
    (the policy-relativity arm)."""
    store = Store.open(tmp_path / "caller-data.db")
    try:
        stored = dict(BINDING, version="1.0.0")
        store.create_run("run-cd-1", stored, "p1", NOW)
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
        assert run["terminal"]["binding"]["version"] == "1.0.0"
        assert run["terminal"]["contract_version"] == "0.2.0"
    finally:
        store.close()


def test_era_echo_retired_by_a_later_policy_era_stamps_from_retained_bytes(
    tmp_path: Path,
) -> None:
    """Fold row 4, corrected to the THREE-WAY disposition (policy
    relativity, the G4 kill shape): an echo that WAS carried when the run
    ran, later RETIRED in a copied policy block — retirement ≠ removal
    (copy-never-move keeps the directory) — era-STAMPS FROM THE RETAINED
    BYTES: the record carries 0.1.0, never a composition-flip stamp AND
    never a wedge. RED against the fold's first cut: the over-broad
    containment wedged this run (containment non-None)."""
    import shutil as _shutil

    from benchweave.control.coordinator import _recovery_record_version

    corpus = tmp_path / "standards"
    _shutil.copytree(ROOT / "standards", corpus)
    manifest_path = corpus / "standards-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    execution = manifest["dependency_policy"]["standards"]["execution"]
    retired = execution.setdefault("retired", [])
    if "0.1.0" not in retired:
        retired.append("0.1.0")
    manifest_path.write_text(json.dumps(manifest, indent=2))

    run = {"binding": dict(ERA_BINDING)}  # echo 0.1.0, digest 0*64 (no doc)

    class _NoContent:
        def get_document(self, sha256: str) -> None:
            return None

    contracts = corpus / "execution" / "0.2.0"
    decision = _recovery_record_version(run, contracts, _NoContent())
    assert decision.record_version == "0.1.0", decision
    assert decision.containment is None, (
        "a retired-but-retained echo era-stamps from the retained bytes — "
        "never a composition flip, never a wedge"
    )
    # The same echo against the REAL corpus (still carried) stays an era
    # thread — policy relativity is the point, era-stamp is the honest
    # outcome while carried AND after retirement.
    from benchweave.vendoring import active_contract_family

    real = _recovery_record_version(
        run, active_contract_family("execution"), _NoContent()
    )
    assert real.record_version == "0.1.0", real
    assert real.containment is None


def _unrowed_corpus(tmp_path: Path) -> Path:
    """A corpus copy whose ``execution/0.1.0`` run-record schema lost its
    manifest row (a partially-rowed version dir) — the unrowed-schema
    containment class."""
    import shutil as _shutil

    corpus = tmp_path / "standards"
    _shutil.copytree(ROOT / "standards", corpus)
    manifest_path = corpus / "corpus-manifest.json"
    manifest_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    before = len(manifest_doc.get("files", []))
    manifest_doc["files"] = [
        row
        for row in manifest_doc.get("files", [])
        if str(row.get("path")) != "execution/0.1.0/run-record.schema.json"
    ]
    assert len(manifest_doc["files"]) == before - 1, "the probe row must exist"
    manifest_path.write_text(json.dumps(manifest_doc, indent=2))
    return corpus


def test_unrowed_run_record_schema_is_contained_per_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Fold row 7 + issue #507: recovery has per-run containment — a
    judgeable run whose version's run-record schema lost its corpus row
    (a partially-rowed version dir) is contained under the narrowed
    prefix, the SWEEP SURVIVES (fold row 7: an AdmissionRejected once
    killed gateway startup), AND (issue #507) the contained run's
    projection closes terminal over the missing record so the §5 busy
    oracle releases — driven through the app-level sweep, the lifespan's
    ONE recovery entrypoint, over the broken corpus copy."""
    import logging

    corpus = _unrowed_corpus(tmp_path)

    def sweep(store: Store) -> list[str]:
        return _recover_interrupted_runs(
            store,
            LATTICE_010,
            emit_keep=100,
            now_iso=lambda: NOW,
            contracts=corpus / "execution" / "0.2.0",
        )

    store = Store.open(tmp_path / "unrowed.db")
    try:
        store.create_run("run-era-5", ERA_BINDING, "p1", NOW)
        store.put_run_state("run-era-5", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-era-5", holder="run:run-era-5", expires_at=NOW
        )
        assert _busy(store) is True, (
            "pre-condition: the contained run's live row owns the bench"
        )
        with caplog.at_level(logging.ERROR, logger="benchweave.control.coordinator"):
            recovered = sweep(store)
        assert recovered == [], f"a contained run is not reported; recovered={recovered}"
        run = store.get_run("run-era-5")
        assert run is not None
        assert run["terminal"] is None, "no record without its schema"
        assert any(
            UNSOLVED_LOG in record.message
            and "run-era-5" in record.message
            and "corpus" in record.message
            for record in caplog.records
        ), f"the containment names the unrowed schema: {[r.message for r in caplog.records]}"
        # Issue #507: containment keeps the bench bookable — the projection
        # closes terminal over the missing record (outcome_unknown on the
        # wire), never a fabricated terminal record.
        assert _busy(store) is False, (
            f"the contained run left the bench busy forever; run_states={_states(store)}"
        )
        row = store.get_run_state("run-era-5")
        assert row is not None and row["state"] == "terminal", (
            f"the contained run's projection must close; run_states={_states(store)}"
        )
        projection = _wire_projection(store, "run-era-5")
        assert projection["state"] == "terminal", projection
        assert projection["outcome"] == "outcome_unknown", projection
        assert projection["safe_state"] == "unknown", projection
        assert projection["terminal_record"] is None, projection
        assert _run_changed(store, "run-era-5"), (
            "the contained projection close is on the bench stream"
        )
        # Idempotent: a second sweep finds a terminal row and no work, and
        # the durable record is still absent (no laundering on re-boot).
        assert sweep(store) == []
        assert _busy(store) is False
        run_after = store.get_run("run-era-5")
        assert run_after is not None
        assert run_after["terminal"] is None, "no sweep may invent a record"
    finally:
        store.close()


# --- the corrupt retained-bytes cohort (issue #534): the retired-echo probe splits ---


def _retired_era_corpus(tmp_path: Path) -> Path:
    """The retired-echo staging: the repo standards copied into tmp with
    0.1.0 added to the dependency policy's retired list — the
    retired-but-RETAINED world where the retained-bytes branch of the
    three-way disposition is the live one (the staging
    ``test_era_echo_retired_by_a_later_policy…`` inlines, factored for
    the corruption cohort)."""
    import shutil as _shutil

    corpus = tmp_path / "standards"
    _shutil.copytree(ROOT / "standards", corpus)
    manifest_path = corpus / "standards-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    execution = manifest["dependency_policy"]["standards"]["execution"]
    retired = execution.setdefault("retired", [])
    if "0.1.0" not in retired:
        retired.append("0.1.0")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return corpus


class _NoContent:
    """A content store holding nothing (the era fixtures' zero digest —
    the doc-absent echo path)."""

    def get_document(self, sha256: str) -> None:
        return None


def _retained_echo_decision(corpus: Path) -> Any:
    """The retired-echo decision probe over one staged corpus: echo 0.1.0,
    no stored binding document — whatever the retained-bytes branch
    decides is the decision the sweep would terminalize on."""
    from benchweave.control.coordinator import _recovery_record_version

    run = {"binding": dict(ERA_BINDING)}
    return _recovery_record_version(run, corpus / "execution" / "0.2.0", _NoContent())


def test_retained_bytes_tampered_with_row_intact_is_contained(tmp_path: Path) -> None:
    """D1 (issue #534): the retired echo's retained schema bytes TAMPERED
    with the corpus row intact — a digest refusal
    (``corpus_pin_mismatch:``). Pre-fix shape (the laundering hole): the
    blanket ``except Exception`` over the retained-bytes probe collapsed
    the refusal into the composition decision — corrupt retained bytes
    silently absent. Post-fix: decision-level CONTAINMENT quoting the
    refusal verbatim; no era stamp, no composition stamp."""
    corpus = _retired_era_corpus(tmp_path)
    schema = corpus / "execution" / "0.1.0" / "run-record.schema.json"
    schema.write_text(schema.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    decision = _retained_echo_decision(corpus)

    assert decision.containment is not None, (
        f"tampered retained bytes must contain, not compose: {decision}"
    )
    assert "corpus_pin_mismatch" in decision.containment, decision.containment
    assert (
        "corpus_pin_mismatch: standards/execution/0.1.0/run-record.schema.json"
        in decision.containment
    ), "the refusal is quoted verbatim, prefix and path intact"
    assert "does not match the on-disk bytes" in decision.containment
    assert decision.record_version is None, decision


def test_retained_bytes_without_corpus_row_is_contained(tmp_path: Path) -> None:
    """D2 (issue #534): the retired echo's schema file present but its
    corpus row REMOVED (the unrowed staging plus the retirement edit) —
    ``corpus_file_unpinned:``. The same laundering hole, the same split:
    containment quoting the refusal verbatim, never a composition
    record."""
    corpus = _retired_era_corpus(tmp_path)
    manifest_path = corpus / "corpus-manifest.json"
    manifest_doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    before = len(manifest_doc.get("files", []))
    manifest_doc["files"] = [
        row
        for row in manifest_doc.get("files", [])
        if str(row.get("path")) != "execution/0.1.0/run-record.schema.json"
    ]
    assert len(manifest_doc["files"]) == before - 1, "the probe row must exist"
    manifest_path.write_text(json.dumps(manifest_doc, indent=2))

    decision = _retained_echo_decision(corpus)

    assert decision.containment is not None, (
        f"unrowed retained bytes must contain, not compose: {decision}"
    )
    assert "corpus_file_unpinned" in decision.containment, decision.containment
    assert (
        "corpus_file_unpinned: execution/0.1.0/run-record.schema.json"
        in decision.containment
    ), "the refusal is quoted verbatim, prefix and path intact"
    assert decision.record_version is None, decision


def test_unparseable_corpus_manifest_is_an_access_failure_not_containment(
    tmp_path: Path,
) -> None:
    """D4 (#534 fold F1): the corpus manifest unparseable — classified
    ACCESS failure, not content corruption, on the evidence: a manifest
    that cannot parse is no evidence about the retained schema bytes (a
    digest mismatch is positive evidence the bytes are wrong; a broken
    manifest only proves the verification machinery could not run), and
    it is repaired by restoring the environment, not by re-judging
    bench fact. The disposition is the refuse-rather-than-lie skip: no
    record, no containment, no projection close — the run recovers on
    the next sweep after repair, and the reason names the file to
    repair. RED at the pre-fold tip, which CONTAINED this class (an
    irreversible no-record ending for a repairable condition)."""
    corpus = _retired_era_corpus(tmp_path)
    (corpus / "corpus-manifest.json").write_text("{ not json", encoding="utf-8")

    decision = _retained_echo_decision(corpus)

    assert decision.access_failure is not None, (
        f"an unparseable manifest is an access failure, not a bench fact: {decision}"
    )
    assert decision.containment is None, decision
    assert decision.record_version is None, decision
    assert "corpus-manifest.json" in decision.access_failure, decision.access_failure


def test_absent_retained_bytes_stays_the_composition_decision(tmp_path: Path) -> None:
    """D3 (issue #534), the ABSENT control: the retired echo's schema
    file DELETED — ``version_unknown:``, honest absence. The decision
    must stay the composition decision exactly as the caller-data class
    pins it, and it must NOT move: the #260 lesson is that over-broad
    containment wedges the honest-ref cohort the integration harnesses
    keep posting. RED only under the fluff control (a split that treats
    version_unknown as containment too)."""
    corpus = _retired_era_corpus(tmp_path)
    (corpus / "execution" / "0.1.0" / "run-record.schema.json").unlink()

    decision = _retained_echo_decision(corpus)

    assert decision.containment is None, (
        f"honest absence is caller data, never containment: {decision}"
    )
    assert decision.record_version is None, decision
    assert decision.binding_pin == ERA_BINDING, decision.binding_pin
    assert decision.reasons == ()


def test_sweep_over_tampered_retained_corpus_contains_and_releases(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """S1 (issue #534): D1's corpus through the app-level sweep — the
    laundering shape END TO END pre-fix (a durable composition terminal
    record stamped over corrupt retained 0.1.0 bytes, the run reported
    recovered). Post-fix: the run is NOT recovered, NO durable record,
    the unresolved log names the run and the mismatch, the projection
    closes terminal with outcome_unknown over the missing record (#507),
    the lease is released, the bench is bookable, and a second sweep is
    idempotent — repair does not retro-terminalize (that is #507's
    row-c door, disclosed, not widened here)."""
    import logging

    corpus = _retired_era_corpus(tmp_path)
    schema = corpus / "execution" / "0.1.0" / "run-record.schema.json"
    schema.write_text(schema.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    def sweep(store: Store) -> list[str]:
        return _recover_interrupted_runs(
            store,
            FIXTURES,
            emit_keep=100,
            now_iso=lambda: NOW,
            contracts=corpus / "execution" / "0.2.0",
        )

    store = Store.open(tmp_path / "tampered-retained.db")
    try:
        store.create_run("run-lau-1", dict(ERA_BINDING, id="req-lau-1"), "p1", NOW)
        store.put_run_state("run-lau-1", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-lau-1", holder="run:run-lau-1", expires_at=NOW
        )
        assert _busy(store) is True, "pre-condition: the live row owns the bench"
        with caplog.at_level(logging.ERROR, logger="benchweave.control.coordinator"):
            recovered = sweep(store)
        assert recovered == [], (
            f"a contained run is not reported recovered; recovered={recovered}"
        )
        run = store.get_run("run-lau-1")
        assert run is not None
        assert run["terminal"] is None, (
            "corrupt retained bytes must not become a composition record"
        )
        assert any(
            UNSOLVED_LOG in record.message
            and "run-lau-1" in record.message
            and "corpus_pin_mismatch" in record.message
            for record in caplog.records
        ), (
            "the unresolved log must name the run and the mismatch: "
            f"{[r.message for r in caplog.records]}"
        )
        assert store.get_active_lease(BENCH_ID) is None, "the lease is released"
        row = store.get_run_state("run-lau-1")
        assert row is not None and row["state"] == "terminal", (
            f"the #507 projection close; run_states={_states(store)}"
        )
        projection = _wire_projection(store, "run-lau-1")
        assert projection["state"] == "terminal", projection
        assert projection["outcome"] == "outcome_unknown", projection
        assert projection["safe_state"] == "unknown", projection
        assert projection["terminal_record"] is None, projection
        assert _busy(store) is False, "containment keeps the bench bookable"
        assert _run_changed(store, "run-lau-1"), (
            "the contained projection close is on the bench stream"
        )
        assert sweep(store) == [], "a second sweep finds nothing left to sweep"
        run_after = store.get_run("run-lau-1")
        assert run_after is not None
        assert run_after["terminal"] is None, "no sweep may invent a record"
    finally:
        store.close()


def test_unrecognised_refusal_prefix_fails_closed_to_containment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F5 (#534 fold): a refusal prefix the split does not name (wording
    drift a future documents.py may ship) fails CLOSED — containment,
    never a composition record, and never the access class (a typed
    refusal is a fact about the artifact; an untyped exception is the
    machinery failing). Today's raise site has no fourth prefix (it
    raises exactly version_unknown / corpus_file_unpinned /
    corpus_pin_mismatch), so the arm synthesizes the drifted refusal at
    the seam the split consumes — the module-bound resolution function —
    pinning the DEFAULT, not a raise site."""
    import benchweave.control.coordinator as coordinator_module
    from benchweave.control.documents import AdmissionRejected

    def _drifted(
        corpus: Path, standard: str, version: str, document_name: str
    ) -> Path:
        raise AdmissionRejected(
            f"future_refusal_class: {standard}/{version}/{document_name} "
            "refused for a reason this split has never seen"
        )

    monkeypatch.setattr(coordinator_module, "_versioned_schema_path", _drifted)
    corpus = _retired_era_corpus(tmp_path)

    decision = _retained_echo_decision(corpus)

    assert decision.containment is not None, (
        f"an unrecognised refusal prefix fails closed: {decision}"
    )
    assert "future_refusal_class" in decision.containment, decision.containment
    assert decision.access_failure is None, decision
    assert decision.record_version is None, decision


def test_sweep_over_unreadable_then_repaired_corpus_recovers_on_second_boot(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """F1 (#534 fold, the kill shape): an ACCESS failure at boot one is
    transient — the run is left untouched (no record, no containment, no
    projection close, the lease unreleased: the bench stays unavailable
    and that is deliberate), and once the operator repairs the access
    condition the NEXT sweep recovers the run with the honest durable
    era record. RED at the pre-fold tip: containment closed the
    projection terminal over the missing record, the second sweep found
    nothing left to sweep, and the transient had become an irreversible
    no-record ending."""
    import logging
    import os

    corpus = _retired_era_corpus(tmp_path)
    schema = corpus / "execution" / "0.1.0" / "run-record.schema.json"

    def sweep(store: Store) -> list[str]:
        return _recover_interrupted_runs(
            store,
            FIXTURES,
            emit_keep=100,
            now_iso=lambda: NOW,
            contracts=corpus / "execution" / "0.2.0",
        )

    store = Store.open(tmp_path / "unreadable-then-repaired.db")
    os.chmod(schema, 0o000)
    try:
        store.create_run("run-acc-1", dict(ERA_BINDING, id="req-acc-1"), "p1", NOW)
        store.put_run_state("run-acc-1", BENCH_ID, "running", NOW)
        store.next_lease(
            BENCH_ID, "lease-acc-1", holder="run:run-acc-1", expires_at=NOW
        )
        assert _busy(store) is True, "pre-condition: the live row owns the bench"
        # Boot one: the corpus is unreadable — the run is left as found.
        with caplog.at_level(logging.ERROR, logger="benchweave.control.coordinator"):
            recovered = sweep(store)
        assert recovered == [], (
            f"an access-failed run is deferred, not recovered: {recovered}"
        )
        run = store.get_run("run-acc-1")
        assert run is not None
        assert run["terminal"] is None, "no record while access fails"
        row = store.get_run_state("run-acc-1")
        assert row is not None and row["state"] == "running", (
            f"no projection close while access fails; run_states={_states(store)}"
        )
        assert _busy(store) is True, (
            "the bench stays unavailable while the corpus is unreadable — deliberate"
        )
        assert store.get_active_lease(BENCH_ID) is not None, (
            "the crashed run's lease is left as found"
        )
        assert any(
            "recovery_corpus_access_failed" in record.message
            and "run-acc-1" in record.message
            for record in caplog.records
        ), (
            "the access failure is logged loudly, naming the run: "
            f"{[r.message for r in caplog.records]}"
        )
        assert not any(
            UNSOLVED_LOG in record.message for record in caplog.records
        ), "an access failure is not containment"
        # Repair: the operator restores readability; nothing else changed.
        os.chmod(schema, 0o600)
        # Boot two: the same run recovers with the durable honest record.
        recovered = sweep(store)
        assert recovered == ["run-acc-1"], f"recovered={recovered}"
        run = store.get_run("run-acc-1")
        assert run is not None
        assert run["terminal"] is not None, (
            "the repaired boot writes the honest record"
        )
        assert run["terminal"]["outcome"] == "interrupted"
        assert run["terminal"]["safe_state"] == "unknown"
        assert run["terminal"]["contract_version"] == "0.1.0", (
            "the retained bytes era-stamp once they can be read again"
        )
        row = store.get_run_state("run-acc-1")
        assert row is not None and row["state"] == "terminal", (
            f"the repaired boot closes the projection; run_states={_states(store)}"
        )
        assert _busy(store) is False, "the repaired boot releases the bench"
        assert sweep(store) == [], "a third sweep finds nothing left"
    finally:
        os.chmod(schema, 0o600)  # never leak the 000 mode out of the arm
        store.close()
