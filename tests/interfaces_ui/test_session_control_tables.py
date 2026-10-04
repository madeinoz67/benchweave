"""The G3a session-side control state (design record §2.1): the held-lease
view table and the session's recorded granted duration.

Store-level arms first — the tables' own semantics, deterministic under
the injected clock, before any route exists:

- ``exchange`` records the session's GRANTED duration in seconds
  (GW-44 D1's percentage base: ``min(session ttl, caller token)`` from
  the exchange instant — the same arithmetic the session's
  ``expires_at`` uses, recorded once);
- the held-lease table mirrors the bridge registry's shape:
  ``session_id -> {bench_id -> HeldLease}``, one view per (session,
  bench), a re-record REPLACES the view (renew), clear removes it, and
  the read is a snapshot under the lock;
- the views die with the session exactly as the records do: logout and
  the lazy expiry sweep both drop them, and a gateway restart empties
  the whole store (CON-15's death semantics by construction).

G3b (issue #304, design record §2.1's second side table) adds the
staging record — ``session_id -> {bench_id -> StagedStart}`` — and the
pending-cancel markers, under the same lock and the same death
semantics. The staging cycle's request id is the STAGED BINDING
document's own ``request_id`` (the seam's binding-match pre-check
requires exactly that id on ``run_start``), so the record carries the
binding's id, never a session-minted one; a re-stage of the same
binding keeps the record (and its id — fixed across check/arm/confirm
and post-refusal retries), a different binding replaces it.

The route-level translation (GW-95 refusals, the fragment, the mode
banner) lives in ``test_ui_control_leases.py``; the G3b route arms in
``test_ui_control_runs.py``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ui_gateway_support import NOW_EPOCH

from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import HeldLease, SessionStore, StagedStart


def _store(*, now: int = NOW_EPOCH, session_ttl_s: int = 3600) -> SessionStore:
    return SessionStore(now_epoch=lambda: now, session_ttl_s=session_ttl_s)


def _identity(
    scopes: frozenset[str] | None = None,
    ttl: int = 12 * 3600,
    principal: str = "lease-op",
) -> Identity:
    return Identity(
        principal=principal,
        audience="stg",
        scopes=scopes or frozenset({"stg:observe", "stg:control"}),
        expires_at=NOW_EPOCH + ttl,
    )


def _live_session(store: SessionStore, **kwargs: Any) -> str:
    code = store.mint_login_code(_identity(**kwargs))
    record = store.exchange(code)
    assert record.duration_s > 0
    return record.session_id


# --- SessionRecord.duration_s (GW-44 D1's percentage base) -----------------------


def test_exchange_records_the_granted_session_duration() -> None:
    """The granted duration is the ttl from the exchange instant to the
    record's own ``expires_at`` — the exact number the D1 warning
    predicate divides by."""
    store = _store(session_ttl_s=3600)
    code = store.mint_login_code(_identity(ttl=12 * 3600))
    record = store.exchange(code)
    assert record.expires_at == NOW_EPOCH + 3600
    assert record.duration_s == 3600


def test_exchange_duration_is_clamped_by_the_caller_token() -> None:
    """A short caller token shortens the session; the recorded duration
    follows the SAME clamp (never wider than the record's expiry)."""
    store = _store(session_ttl_s=8 * 3600)
    code = store.mint_login_code(_identity(ttl=1800), ttl_seconds=1800)
    record = store.exchange(code)
    assert record.expires_at == NOW_EPOCH + 1800
    assert record.duration_s == 1800


def test_session_record_duration_defaults_to_unrecorded() -> None:
    """A record constructed outside exchange (G2 suites' shapes) carries
    ``duration_s == 0`` — "not recorded" — and the D1 warning composes
    no verdict from an unrecorded duration."""
    from benchweave.interfaces.sessions import SessionRecord

    record = SessionRecord(
        session_id="s",
        principal="p",
        audience="stg",
        scopes=frozenset({"stg:observe"}),
        expires_at=NOW_EPOCH + 60,
        csrf_token="t",
    )
    assert record.duration_s == 0


# --- the held-lease view table ----------------------------------------------------


def test_record_and_read_a_held_lease_view() -> None:
    store = _store()
    session_id = _live_session(store)
    view = HeldLease(
        lease_id="lease-a",
        bench_id="bench-one",
        sequence=1,
        expires_at="2026-10-03T01:00:00Z",
        state="active",
        requested_duration_ms=3_600_000,
    )
    store.record_held_lease(session_id, view)
    held = store.held_lease(session_id, "bench-one")
    assert held == view


def test_re_record_replaces_the_view_and_clear_removes_it() -> None:
    """A renew's successor projection replaces the view; release clears
    it; a cleared view reads ``None``."""
    store = _store()
    session_id = _live_session(store)
    store.record_held_lease(
        session_id,
        HeldLease(
            lease_id="lease-a",
            bench_id="bench-one",
            sequence=1,
            expires_at="2026-10-03T01:00:00Z",
            state="active",
            requested_duration_ms=3_600_000,
        ),
    )
    store.record_held_lease(
        session_id,
        HeldLease(
            lease_id="lease-a",
            bench_id="bench-one",
            sequence=2,
            expires_at="2026-10-03T02:00:00Z",
            state="active",
            requested_duration_ms=1_800_000,
        ),
    )
    held = store.held_lease(session_id, "bench-one")
    assert held is not None and held.sequence == 2
    assert held.requested_duration_ms == 1_800_000
    store.clear_held_lease(session_id, "bench-one")
    assert store.held_lease(session_id, "bench-one") is None
    # Idempotent: a second clear is a no-op, never an error.
    store.clear_held_lease(session_id, "bench-one")


def test_views_are_session_scoped() -> None:
    """One session's view never answers another session's read."""
    store = _store()
    first = _live_session(store, principal="op-one")
    second = _live_session(store, principal="op-two")
    store.record_held_lease(
        first,
        HeldLease(
            lease_id="lease-a",
            bench_id="bench-one",
            sequence=1,
            expires_at="2026-10-03T01:00:00Z",
            state="active",
            requested_duration_ms=60_000,
        ),
    )
    assert store.held_lease(second, "bench-one") is None


def test_logout_drops_the_held_lease_views() -> None:
    """CON-15's death semantics: the side table is not identity state and
    dies with the record at logout."""
    store = _store()
    session_id = _live_session(store)
    store.record_held_lease(
        session_id,
        HeldLease(
            lease_id="lease-a",
            bench_id="bench-one",
            sequence=1,
            expires_at="2026-10-03T01:00:00Z",
            state="active",
            requested_duration_ms=60_000,
        ),
    )
    store.logout(session_id)
    assert store.held_lease(session_id, "bench-one") is None


def test_expiry_sweep_drops_the_held_lease_views() -> None:
    """The lazy sweep at resolution drops expired sessions' views (a view
    can never outlive its session)."""
    clock = [NOW_EPOCH]
    store = SessionStore(now_epoch=lambda: clock[0], session_ttl_s=100)
    session_id = _live_session(store)
    store.record_held_lease(
        session_id,
        HeldLease(
            lease_id="lease-a",
            bench_id="bench-one",
            sequence=1,
            expires_at="2026-10-03T01:00:00Z",
            state="active",
            requested_duration_ms=60_000,
        ),
    )
    clock[0] = NOW_EPOCH + 101  # past the session's expiry: the next
    # resolution sweeps the record and its views.
    assert store.resolve(session_id) is None
    assert store.held_lease(session_id, "bench-one") is None


# --- the frozen dataclass's shape (projection + requested duration) ----------------


def test_held_lease_is_the_projection_plus_the_requested_duration() -> None:
    fields = HeldLease.__dataclass_fields__
    assert set(fields) == {
        "lease_id",
        "bench_id",
        "sequence",
        "expires_at",
        "state",
        "requested_duration_ms",
    }


# --- the staging record (G3b, design record §2.1's second side table) --------------


def _binding_ref(sha: str) -> dict[str, Any]:
    return {"id": "voltage-check", "version": "0.1.0", "sha256": sha}


def _staged(
    request_id: str = "req-voltage-check-1", sha: str = "a" * 64, *, armed: bool = False
) -> StagedStart:
    return StagedStart(
        request_id=request_id,
        binding_ref=_binding_ref(sha),
        check=None,
        armed=armed,
    )


def test_staging_record_round_trips_and_is_session_and_bench_scoped() -> None:
    store = _store()
    first = _live_session(store, principal="op-one")
    second = _live_session(store, principal="op-two")
    staged = _staged(sha="a" * 64)
    store.record_staged_start(first, "bench-one", staged)
    assert store.staged_start(first, "bench-one") == staged
    # One session's staging never answers another session's read.
    assert store.staged_start(second, "bench-one") is None
    # One bench's staging never answers another bench's read.
    assert store.staged_start(first, "bench-two") is None


def test_re_stage_the_same_binding_keeps_the_cycle_request_id() -> None:
    """A same-binding re-stage REPLACES the record's mutable halves (the
    check clears — GW-51) while the binding's own request id — the
    staging cycle's id — stays fixed; a DIFFERENT binding replaces the
    record wholesale (the new cycle's new id)."""
    store = _store()
    session_id = _live_session(store)
    store.record_staged_start(session_id, "bench-one", _staged(sha="a" * 64))
    store.record_staged_start(
        session_id,
        "bench-one",
        replace(_staged(sha="a" * 64), check={"valid": True, "generation": 3, "findings": []}),
    )
    held = store.staged_start(session_id, "bench-one")
    assert held is not None
    assert held.request_id == "req-voltage-check-1"  # the cycle id, unchanged
    assert held.check is not None  # the caller's re-record is what reads back
    # A different binding (a different cycle): the record replaces wholesale.
    store.record_staged_start(
        session_id, "bench-one", _staged(request_id="req-other-2", sha="b" * 64)
    )
    staged = store.staged_start(session_id, "bench-one")
    assert staged is not None
    assert staged.request_id == "req-other-2"
    assert staged.binding_ref["sha256"] == "b" * 64
    assert staged.check is None


def test_clear_staged_start_is_idempotent() -> None:
    store = _store()
    session_id = _live_session(store)
    store.record_staged_start(session_id, "bench-one", _staged())
    store.clear_staged_start(session_id, "bench-one")
    assert store.staged_start(session_id, "bench-one") is None
    store.clear_staged_start(session_id, "bench-one")  # no-op, never an error


def test_staging_and_markers_die_with_logout_and_expiry_sweep() -> None:
    """CON-15's death semantics: the staging records and the pending-cancel
    markers are presentation of one session's own answers, not identity
    facts — both drop at logout and at the lazy expiry sweep."""
    clock = [NOW_EPOCH]
    store = SessionStore(now_epoch=lambda: clock[0], session_ttl_s=100)
    session_id = _live_session(store)
    store.record_staged_start(session_id, "bench-one", _staged())
    store.record_cancel_request(session_id, "run-1")
    store.logout(session_id)
    assert store.staged_start(session_id, "bench-one") is None
    assert not store.cancel_requested(session_id, "run-1")

    session_id = _live_session(store)
    store.record_staged_start(session_id, "bench-one", _staged())
    store.record_cancel_request(session_id, "run-2")
    clock[0] = NOW_EPOCH + 101  # the next resolution sweeps the record...
    assert store.resolve(session_id) is None
    assert store.staged_start(session_id, "bench-one") is None
    assert not store.cancel_requested(session_id, "run-2")


# --- pending-cancel markers (G3b GW-55: the operator's own action,
# --- presented until the seam reports the run terminal) -----------------------------


def test_cancel_marker_round_trip() -> None:
    store = _store()
    session_id = _live_session(store)
    assert not store.cancel_requested(session_id, "run-1")
    store.record_cancel_request(session_id, "run-1")
    assert store.cancel_requested(session_id, "run-1")
    # Session-scoped: another session's read stays clear.
    other = _live_session(store, principal="op-two")
    assert not store.cancel_requested(other, "run-1")
    store.clear_cancel_request(session_id, "run-1")
    assert not store.cancel_requested(session_id, "run-1")
    store.clear_cancel_request(session_id, "run-1")  # idempotent


def test_staged_start_is_the_recorded_four_fields() -> None:
    """The record's closed shape: request id (the binding's own), the
    binding ref, the recorded check, the armed flag."""
    fields = StagedStart.__dataclass_fields__
    assert set(fields) == {"request_id", "binding_ref", "check", "armed"}
