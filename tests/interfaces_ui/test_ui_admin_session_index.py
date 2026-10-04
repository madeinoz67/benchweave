"""The G4 session change index (issue #305, design record §2.1): the
one new state home — ``session_id -> {change_id -> ChangeView}`` under
the store's existing lock, mirroring the staged-start shape.

Store-level arms first — the table's own semantics, deterministic under
the injected clock, before any route exists:

- record + read: a change this session submitted or attempted to apply
  reads back; one session's index never answers another's read;
- a re-record REPLACES the view (the approval-load path rides it: the
  view's approval facts update, the acknowledged flag survives);
- the acknowledgement is the operator's per-session mark;
- CON-15's death semantics by construction: logout and the lazy expiry
  sweep both drop the table (a gateway restart empties the store
  whole — nothing to pin beyond construction).

An index, not a state cache: the view carries NO change state — every
rendered state comes from a fresh ``change_get`` at render time (the
C3 arm proves the render follows ``change_get``; the dataclass shape
pin below is the structural half of that rule).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ui_gateway_support import NOW_EPOCH

from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import (
    ApprovalView,
    ChangeView,
    SessionStore,
)


def _store(*, now: int = NOW_EPOCH, session_ttl_s: int = 3600) -> SessionStore:
    return SessionStore(now_epoch=lambda: now, session_ttl_s=session_ttl_s)


def _identity(
    scopes: frozenset[str] | None = None,
    ttl: int = 12 * 3600,
    principal: str = "admin-op",
) -> Identity:
    return Identity(
        principal=principal,
        audience="stg",
        scopes=scopes or frozenset({"stg:observe", "stg:control", "stg:admin"}),
        expires_at=NOW_EPOCH + ttl,
    )


def _live_session(store: SessionStore, **kwargs: Any) -> str:
    code = store.mint_login_code(_identity(**kwargs))
    record = store.exchange(code)
    return record.session_id


def _view(bench_id: str = "bench-one", *, acknowledged: bool = False) -> ChangeView:
    return ChangeView(bench_id=bench_id, acknowledged=acknowledged)


def test_change_index_round_trips_and_is_session_scoped() -> None:
    store = _store()
    first = _live_session(store, principal="op-one")
    second = _live_session(store, principal="op-two")
    view = _view("bench-one")
    store.record_change_view(first, "chg-1", view)
    assert store.change_view(first, "chg-1") == view
    # One session's index never answers another session's read.
    assert store.change_view(second, "chg-1") is None
    # One change never answers another change's read.
    assert store.change_view(first, "chg-2") is None


def test_change_index_is_bench_keyed_for_the_region_query() -> None:
    """The bench admin region renders THIS session's changes for one
    bench: the bench-keyed query returns exactly those."""
    store = _store()
    session_id = _live_session(store)
    store.record_change_view(session_id, "chg-1", _view("bench-one"))
    store.record_change_view(session_id, "chg-2", _view("bench-two"))
    rows = store.change_views_for_bench(session_id, "bench-one")
    assert set(rows) == {"chg-1"}
    assert rows["chg-1"].bench_id == "bench-one"


def test_re_record_replaces_and_acknowledgement_survives() -> None:
    """The approval-load path replaces the view's approval facts without
    disturbing the operator's acknowledgement."""
    store = _store()
    session_id = _live_session(store)
    store.record_change_view(session_id, "chg-1", _view("bench-one", acknowledged=True))
    approval = ApprovalView(
        sha256="a" * 64,
        ref_id="approval-1",
        ref_version="1",
        approver_principal="approver-x",
        policy_version="1",
        binds=True,
        bound_change_id="chg-1",
        bound_generation=1,
    )
    store.record_change_approval(session_id, "chg-1", approval)
    view = store.change_view(session_id, "chg-1")
    assert view is not None
    assert view.acknowledged is True
    assert view.approval == approval
    # A second load replaces the approval (the operator re-pasted).
    second = replace(approval, approver_principal="approver-y")
    store.record_change_approval(session_id, "chg-1", second)
    view = store.change_view(session_id, "chg-1")
    assert view is not None and view.approval == second


def test_approval_load_on_an_unindexed_change_records_it() -> None:
    """Loading an approval for a change this session did not submit (a
    manually-entered id — G4-D2's discovery posture) indexes it."""
    store = _store()
    session_id = _live_session(store)
    approval = ApprovalView(
        sha256="b" * 64,
        ref_id="approval-1",
        ref_version="1",
        approver_principal="approver-x",
        policy_version="1",
        binds=False,
        bound_change_id="chg-x",
        bound_generation=1,
    )
    store.record_change_approval(session_id, "chg-x", approval)
    view = store.change_view(session_id, "chg-x")
    assert view is not None
    assert view.approval is not None


def test_acknowledge_marks_the_operator_read_the_record() -> None:
    """The acknowledgement is the operator's per-session mark; a second
    is a no-op; acknowledging a change this session never indexed is a
    no-op too (nothing to clear)."""
    store = _store()
    session_id = _live_session(store)
    store.record_change_view(session_id, "chg-1", _view("bench-one"))
    store.acknowledge_change(session_id, "chg-1")
    view = store.change_view(session_id, "chg-1")
    assert view is not None and view.acknowledged is True
    store.acknowledge_change(session_id, "chg-1")  # idempotent
    store.acknowledge_change(session_id, "chg-absent")  # no-op, never an error


def test_change_index_dies_with_logout_and_expiry_sweep() -> None:
    """CON-15's death semantics: the index is presentation of one
    session's own answers, not identity facts — logout and the lazy
    expiry sweep both drop it."""
    clock = [NOW_EPOCH]
    store = SessionStore(now_epoch=lambda: clock[0], session_ttl_s=100)
    session_id = _live_session(store)
    store.record_change_view(session_id, "chg-1", _view("bench-one"))
    store.logout(session_id)
    assert store.change_view(session_id, "chg-1") is None

    session_id = _live_session(store)
    store.record_change_view(session_id, "chg-2", _view("bench-one"))
    clock[0] = NOW_EPOCH + 101  # the next resolution sweeps the record...
    assert store.resolve(session_id) is None
    assert store.change_view(session_id, "chg-2") is None


def test_change_view_carries_no_change_state() -> None:
    """The index-caches-nothing rule (design §2.1, C3's structural
    half): the view's fields are exactly {bench_id, acknowledged,
    approval} — a state field would make the render answer from
    yesterday's seam answer."""
    fields = set(ChangeView.__dataclass_fields__)
    assert fields == {"bench_id", "acknowledged", "approval"}
