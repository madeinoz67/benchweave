"""D13 batch A: the store-side hygiene register, pinned per named item.

``docs/compatibility.md`` row D13 groups the known seam/transport
residuals. Its STORE-side named items are enumerated here, each pinned by
its own assert (this file is the register of record for the batch):

1. lease expiry — "an expired-unreleased lease keeps its bench ``busy``":
   the seam's active-lease reads (the bench projection's ``busy`` flag)
   must treat an ACTIVE row whose stored ``expires_at`` has passed as no
   lease. The stored stamp is the oracle (``limits.max_lease_ms`` is the
   mint-time ceiling, not the read-time authority) and the seam's injected
   clock decides "now", exactly the Task-3 takeover idiom.
2. events cursor-read index — the ``events`` table's cursor-read path is
   served by a named, migration-tracked index, proven by EXPLAIN QUERY
   PLAN (an index that exists but is not used fails this pin).
3. crash-window — ``accept_request``→``create_run`` is two transactions;
   a process death between them wedges the §9 request key. The startup
   recovery path (the app lifespan's ONE recovery entrypoint) reconciles
   the dangling key so the same ``request_id`` proceeds.
4. lease-close hygiene — ``release_lease`` and ``consume_lease`` are one
   guarded active→released transition (shared private helper), pinned as
   behaviorally identical.

Transport-side D13 items (MCP body ceiling, ``internal_error`` text /
``correlation_id``, ``change_apply`` retry semantics, the async
single-loop posture) are NOT store hygiene and stay in their WP08 batch.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import test_seam_control as control_module
from test_seam_control import (  # noqa: E402  (sibling, pytest path insertion)
    BENCH_ID,
    LIMITS,
    NOW,
    SeamControl,
    _control,
)
from test_seam_control import (
    seam_control as _seam_control_fixture,
)

from benchweave.control.coordinator import _iso_plus_ms
from benchweave.interfaces import errors
from benchweave.interfaces.app import _recover_interrupted_runs
from benchweave.interfaces.identity import Identity
from benchweave.interfaces.operations import scoped_request_key
from benchweave.state.migrations import MIGRATIONS
from benchweave.state.store import LeaseNotActive, Store

# pytest registers module-level fixture objects by attribute name, so the
# alias assignment is what makes the sibling module's full seam bootstrap
# resolvable for this suite's ``seam_control`` parameters (the tests/unit
# answer to tests/integration/conftest.py's re-export — a second conftest
# would collide with it as a duplicate module under mypy).
seam_control = _seam_control_fixture

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"

# The windowed cursor read, verbatim from Store.read_events_after's paging
# branch — the query the events index must serve.
_CURSOR_READ_SQL = (
    "SELECT event_json FROM events WHERE stream_id = ? AND sequence > ?"
    " ORDER BY sequence LIMIT ?"
)


# --- D13 item 1: lease expiry un-pins the bench ----------------------------------


def test_d13_expired_unreleased_lease_stops_pinning_bench_busy(
    seam_control: SeamControl, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stored ``expires_at`` (minted under the ``max_lease_ms``
    ceiling) is the read-time oracle: before it the bench reads busy, at
    and after it the lease pins nothing — and the bench admits a fresh run
    and a fresh lease. The clock is the seam's injected one, advanced by
    rebinding the fixture module's frozen NOW (the same injection point
    Task 3's expiry tests used)."""
    ops = seam_control.ops
    ceiling = int(LIMITS["max_lease_ms"])
    frozen = control_module.NOW
    lease = ops.lease_create(_control("p1"), BENCH_ID, "lease-exp-busy-1", 1, ceiling)
    assert str(lease["expires_at"]) == _iso_plus_ms(NOW, ceiling)

    # Mirror: before the stored expiry the bench is busy.
    assert ops.bench_get(_control("p1"), BENCH_ID)["busy"] is True
    monkeypatch.setattr(control_module, "NOW", _iso_plus_ms(frozen, ceiling - 1000))
    assert ops.bench_get(_control("p1"), BENCH_ID)["busy"] is True

    # At the expiry instant the lease is gone (now >= expires_at)…
    monkeypatch.setattr(control_module, "NOW", _iso_plus_ms(frozen, ceiling))
    assert ops.bench_get(_control("p1"), BENCH_ID)["busy"] is False
    # …and every instant after.
    monkeypatch.setattr(control_module, "NOW", _iso_plus_ms(frozen, ceiling + 1000))
    assert ops.bench_get(_control("p1"), BENCH_ID)["busy"] is False

    # Admissibility: a fresh run and a fresh lease are both accepted on a
    # bench whose only lease expired unreleased.
    run = ops.run_start(
        _control("p1"),
        BENCH_ID,
        str(seam_control.binding_ref["id"]),
        seam_control.binding_ref,
        1,
        None,
    )
    assert run["state"] in ("accepted", "running")
    seam_control.release.set()
    seam_control.worker.join(timeout=10)
    fresh = ops.lease_create(_control("p2"), BENCH_ID, "lease-after-expiry", 1, 1000)
    assert fresh["state"] == "active"


def test_d13_live_lease_helper_fails_open_on_unparseable_stamp(
    seam_control: SeamControl,
) -> None:
    """A corrupt ``expires_at`` cannot wedge the bench: the lease-state
    row is still ACTIVE, but no parseable deadline exists, so the busy
    read treats it as no lease (the takeover path already fails the same
    row closed ``not_found`` — Task 3's truthful branch)."""
    seam_control.store.next_lease(
        BENCH_ID, "lease-corrupt-1", holder="p1", expires_at="not-a-timestamp"
    )
    lease = seam_control.ops._live_lease(BENCH_ID)
    assert lease is None
    assert seam_control.ops.bench_get(_control("p1"), BENCH_ID)["busy"] is False


# --- D13 item 2: events cursor-read index -----------------------------------------


def test_d13_events_cursor_read_is_served_by_the_migration_index(
    tmp_path: Path,
) -> None:
    """The falsifier is the plan itself: the cursor-read query must SEARCH
    via the v4 index (``idx_events_stream_seq``), never SCAN the table —
    an index that exists but is not used fails this pin."""
    store = Store.open(tmp_path / "hygiene.db")
    try:
        assert store.schema_version() == MIGRATIONS[-1].version == 4
        plans = store.connection.execute(
            "EXPLAIN QUERY PLAN " + _CURSOR_READ_SQL, ("bench.sim-bench", 0, 100)
        ).fetchall()
        detail = " | ".join(str(row[3]) for row in plans)
        assert "USING INDEX idx_events_stream_seq" in detail, detail
        assert "SCAN events" not in detail, detail
    finally:
        store.close()


def test_d13_store_stays_clock_free_expiry_lives_at_the_seam() -> None:
    """The store's constitution is caller-supplied timestamps (no clock
    reads), so expiry enforcement lives in the seam's injected clock, not
    the store — structural pin mirroring the no-device-I/O test."""
    source = (ROOT / "src" / "benchweave" / "state" / "store.py").read_text(
        encoding="utf-8"
    )
    for banned in ("import time", "from datetime", "time.time", "datetime.now"):
        assert banned not in source, f"state code must stay clock-free: {banned}"


# --- D13 item 3: crash-window reconciliation --------------------------------------


def test_d13_crash_window_request_key_reconciles_and_retry_proceeds(
    seam_control: SeamControl,
) -> None:
    """Split state written directly with sqlite3 (the store's own
    connection): the ``requests`` row a dead process committed between
    ``accept_request`` and ``create_run``, and the ``runs`` row it never
    wrote. Pre-recovery the same-body retry fails honestly (``not_found``
    on the run that never materialized); the lifespan's recovery
    entrypoint reconciles the key; the SAME request id then proceeds."""
    ops = seam_control.ops
    store = seam_control.store
    request_id = str(seam_control.binding_ref["id"])
    key = scoped_request_key("p1", "run_start", request_id)
    body_sha = hashlib.sha256(
        json.dumps(seam_control.binding_ref, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    store.connection.execute(
        "INSERT INTO requests (idempotency_key, body_sha256, run_id, accepted_at)"
        " VALUES (?, ?, ?, ?)",
        (key, body_sha, "run-ghost-1", NOW),
    )

    # The honest wedge: the replay peek resolves the key, the projection
    # cannot resolve the run.
    with pytest.raises(errors.OperationFailure) as exc:
        ops.run_start(
            _control("p1"), BENCH_ID, request_id, seam_control.binding_ref, 1, None
        )
    assert exc.value.failure.code == "not_found"

    # The recovery idiom WP03 already uses: the lifespan's one recovery
    # entrypoint (RunCoordinator.recover_interrupted + this task's
    # dangling-key sweep riding the same startup path).
    _recover_interrupted_runs(store, FIXTURES, emit_keep=100, now_iso=lambda: NOW)
    assert store.find_request(key) is None

    run = ops.run_start(
        _control("p1"), BENCH_ID, request_id, seam_control.binding_ref, 1, None
    )
    assert run["state"] in ("accepted", "running")


def test_d13_sweep_spares_change_submit_keys(
    seam_control: SeamControl,
) -> None:
    """``change_submit`` files §9 keys whose ``run_id`` column holds a
    change id (there is no run and never will be). The crash-window sweep
    must scope itself to RUN keys: a change key survives with its §9
    replay intact — the same request id replays to the EXISTING change,
    never a fresh filing — while a genuine dangling run key is still
    purged in the same sweep."""
    ops = seam_control.ops
    store = seam_control.store
    admin = Identity("admin-1", "stg", frozenset({"stg:admin"}), 2**31)
    target = {"id": "t", "version": "1", "sha256": "0" * 64}
    first = ops.change_submit(
        admin, "chg-d13", BENCH_ID, "trip_reset", target, 1, "d13 covering"
    )
    assert first["state"] == "proposed"

    store.reconcile_dangling_requests()  # the restart-class sweep
    key = scoped_request_key("admin-1", "change_submit", "chg-d13")
    assert store.find_request(key) is not None, "change keys are not dangling"
    assert store.get_change(str(first["change_id"])) is not None

    second = ops.change_submit(
        admin, "chg-d13", BENCH_ID, "trip_reset", target, 1, "d13 covering"
    )
    assert second["change_id"] == first["change_id"]  # replay, not a re-file

    # Mirror in the same sweep pass: a genuine dangling run key still goes.
    run_key = scoped_request_key("p1", "run_start", "req-mirror")
    store.connection.execute(
        "INSERT INTO requests (idempotency_key, body_sha256, run_id, accepted_at)"
        " VALUES (?, ?, ?, ?)",
        (run_key, "0" * 64, "run-ghost-2", NOW),
    )
    assert store.reconcile_dangling_requests() == [run_key]


# --- D13 item 4: the lease-close transition ----------------------------------------


def test_d13_release_and_consume_are_one_guarded_transition(
    tmp_path: Path,
) -> None:
    """``release_lease`` and ``consume_lease`` share one private guarded
    active→released transition (the Task-3 review fold): both stamp the
    close time into ``expires_at``, both refuse anything not active, and
    neither can close the other's row twice."""
    store = Store.open(tmp_path / "hygiene.db")
    try:
        first = store.next_lease("bench-h", "lease-h-1", "p1", "2030-01-01T00:00:00Z")
        store.release_lease("bench-h", first.sequence, "2026-09-12T00:00:09Z")
        rows = store.list_leases("bench-h")
        assert (rows[0].state, rows[0].expires_at) == (
            "released",
            "2026-09-12T00:00:09Z",
        )
        with pytest.raises(LeaseNotActive):
            store.consume_lease("bench-h", first.sequence, "2026-09-12T00:00:10Z")

        second = store.next_lease("bench-h", "lease-h-2", "p1", "2030-01-01T00:00:00Z")
        store.consume_lease("bench-h", second.sequence, "2026-09-12T00:00:11Z")
        rows = store.list_leases("bench-h")
        assert (rows[1].state, rows[1].expires_at) == (
            "released",
            "2026-09-12T00:00:11Z",
        )
        with pytest.raises(LeaseNotActive):
            store.release_lease("bench-h", second.sequence, "2026-09-12T00:00:12Z")

        assert store.get_active_lease("bench-h") is None
    finally:
        store.close()
