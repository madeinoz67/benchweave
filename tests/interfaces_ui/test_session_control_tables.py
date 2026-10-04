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

The route-level translation (GW-95 refusals, the fragment, the mode
banner) lives in ``test_ui_control_leases.py``.
"""

from __future__ import annotations

from typing import Any

from ui_gateway_support import NOW_EPOCH

from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import HeldLease, SessionStore


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
