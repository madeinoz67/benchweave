"""WP07 Task 6: bench streams, kinds, cursor paging, retention overtake."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from benchweave.content.store import ContentStore
from benchweave.interfaces import errors, operations
from benchweave.interfaces.bootstrap import admit_startup_bench
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import Operations
from benchweave.interfaces.validation import SeamValidator
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
CORPUS = Path(__file__).resolve().parents[2] / "standards" / "interface/0.1.0"
NOW = "2026-09-12T00:00:00Z"
Seam = tuple[Operations, Store]

IDENT = Identity("p1", "stg", frozenset({"stg:observe", "stg:control"}), 2**31)


@pytest.fixture()
def seam(tmp_path: Path) -> Iterator[Seam]:
    store = Store.open(tmp_path / "state.db")
    content = ContentStore(store)
    admit_startup_bench(store, content, FIXTURES, now=NOW)
    ops = operations.Operations(
        store, content, gateway_id="gw-test",
        validator=SeamValidator(CORPUS),
        limits={"max_json_bytes": 1048576, "max_page_size": 1000,
                "max_chunk_bytes": 65536, "max_lease_ms": 600000,
                "min_poll_ms": 100, "max_admission_ms": 5000},
        now_iso=lambda: NOW,
    )
    yield ops, store
    store.close()


def test_events_get_returns_kinds_and_watermarks(seam: Seam) -> None:
    ops, store = seam
    ops._emit("run_changed", "sim-bench", "run-1")
    ops._emit("lease_changed", "sim-bench", None)
    data = ops.events_get(IDENT, "sim-bench", after=None, limit=10)
    assert [e["kind"] for e in data["events"]] == ["run_changed", "lease_changed"]
    assert data["stream_id"] == "bench.sim-bench"
    assert data["oldest_sequence"] == "1" and data["current_sequence"] == "2"


def test_cursor_pages_and_is_principal_bound(seam: Seam) -> None:
    ops, _ = seam
    for _ in range(5):
        ops._emit("bench_changed", "sim-bench", None)
    page1 = ops.events_get(IDENT, "sim-bench", after=None, limit=2)
    assert len(page1["events"]) == 2
    page2 = ops.events_get(IDENT, "sim-bench", after=page1["cursor"], limit=2)
    assert page2["events"][0]["sequence"] == "3"
    stranger = Identity("p2", "stg", frozenset({"stg:observe"}), 2**31)
    with pytest.raises(errors.OperationFailure):
        ops.events_get(stranger, "sim-bench", after=page1["cursor"], limit=2)


def test_retention_overtake_yields_event_gap(seam: Seam) -> None:
    """§7 events paragraph: a cursor the retention window has overtaken is
    ``event_gap`` WITH the retained watermarks in ``details`` (§10: the
    raise preempts the response, so the watermarks the caller needs to
    rejoin the stream must ride the failure itself) — the final-fix-wave
    correction from the wrong ``cursor_expired`` pin."""
    ops, store = seam
    for _ in range(6):
        ops._emit("run_changed", "sim-bench", "run-1")
    keep = 3
    store.trim_stream("bench.sim-bench", keep)
    stale = operations.encode_cursor("bench.sim-bench", "1", "p1")
    with pytest.raises(errors.OperationFailure) as exc:
        ops.events_get(IDENT, "sim-bench", after=stale, limit=10)
    assert exc.value.failure.code == "event_gap"
    # 6 emissions, trim keeps 3: the retained window is sequences 4..6.
    # D14-details: the failure carries the CLOSED six-key object with the
    # §7 watermarks AND the stream they address.
    assert exc.value.failure.details == {
        "findings": [],
        "current_revision": None,
        "stream_id": "bench.sim-bench",
        "oldest_sequence": "4",
        "current_sequence": "6",
        "retry_after_ms": None,
    }


def test_evidence_gap_emitted_when_retention_fails(seam: Seam) -> None:
    ops, store = seam
    ops._emit_evidence_gap("sim-bench", "run-1", 2)
    data = ops.events_get(IDENT, "sim-bench", after=None, limit=10)
    assert data["events"][-1]["kind"] == "evidence_gap"
    # D4 (interface-errata slice): the event pins the run's binding
    # document (run-1 has no run row in this fixture, so resolution falls
    # to the stream's commissioned bench configuration — the honest
    # document anchor); the failure count itself left the wire for the
    # gateway log.
    evidence = data["events"][-1]["evidence"]
    assert set(evidence) == {"id", "version", "sha256"}
