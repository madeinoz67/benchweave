"""WP07 Task 2: v2 migration, generation authority, projections, request lookup."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from benchweave.state.store import LeaseNotActive, Store


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    s = Store.open(tmp_path / "state.db")
    yield s
    s.close()


def test_migration_applies_and_reports_version_2(store: Store) -> None:
    assert store.schema_version() >= 2


def test_generation_starts_at_zero_and_bumps_monotonically(store: Store) -> None:
    assert store.current_generation("bench-1") == 0
    first = store.bump_generation("bench-1", "2026-09-12T00:00:00Z")
    second = store.bump_generation("bench-1", "2026-09-12T00:01:00Z")
    assert (first, second) == (1, 2)
    assert store.current_generation("bench-1") == 2


def test_bench_roundtrip_and_listing(store: Store) -> None:
    store.put_bench("bench-1", 1, "observation", "{}", "Apache-2.0", "2026-09-12T00:00:00Z")
    bench = store.get_bench("bench-1")
    assert bench is not None and bench["qualification"] == "observation"
    items, has_more = store.list_benches(limit=10, offset=0)
    assert [b["bench_id"] for b in items] == ["bench-1"] and not has_more


def test_run_state_upsert_increments_revision(store: Store) -> None:
    store.put_run_state("run-1", "bench-1", "accepted", "2026-09-12T00:00:00Z")
    store.put_run_state("run-1", "bench-1", "running", "2026-09-12T00:00:01Z")
    state = store.get_run_state("run-1")
    assert state is not None
    assert state["state"] == "running" and state["revision"] == 2


def test_change_records_and_state_machine(store: Store) -> None:
    store.put_change(
        "chg-1", "bench-1", "trip_reset", "{}", 3, "operator reset", "2026-09-12T00:00:00Z"
    )
    store.set_change_state("chg-1", "applied", [], "2026-09-12T00:00:05Z")
    change = store.get_change("chg-1")
    assert change is not None and change["state"] == "applied"


def test_find_request_returns_accepted_row(store: Store) -> None:
    store.accept_request("key-1", "aa" * 32, "run-9", "2026-09-12T00:00:00Z")
    row = store.find_request("key-1")
    assert row is not None and row["run_id"] == "run-9"
    assert store.find_request("missing") is None


def test_lease_not_active_is_typed(store: Store) -> None:
    store.next_lease("bench-x", "lease-1", "run:r1", "2026-09-12T00:01:00Z")
    with pytest.raises(LeaseNotActive):
        store.release_lease("bench-x", 99, "2026-09-12T00:02:00Z")
