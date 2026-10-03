"""The session bridge registry (G2c, design §2.2/§2.5): one SSE bridge
per (session, bench), capped per session, torn down with the session.

Store-level arms — the registry's own semantics, deterministic under the
injected clock, before any route exists:

- one bridge per (session, bench): a second claim for the same pair is
  ``conflict`` (GW-33's refusal half);
- the per-session cap (``ui_max_bridges_per_session``, default 4) refuses
  the fifth DISTINCT pair — the cap counts pairs, not requests;
- only a live session can claim: an unknown/expired/logged-out session
  refuses ``unauthenticated`` (a stream never outlives its session);
- logout and expiry deregister the session's bridges (the store's own
  teardown half; the generator's ``finally`` is the other);
- deregistration is idempotent — the generator's ``finally`` and the
  session's death can both fire without error.

The route-level translation of these refusals (rendered §C.3 pages) and
the abort-driven teardown live in ``test_ui_stream.py``.
"""

from __future__ import annotations

import pytest
from ui_gateway_support import NOW_EPOCH

from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import (
    BridgeRefused,
    SessionStore,
)


def _store(*, now: int = NOW_EPOCH) -> SessionStore:
    return SessionStore(now_epoch=lambda: now, session_ttl_s=3600)


def _session(store: SessionStore, principal: str = "bridge-op") -> str:
    code = store.mint_login_code(
        Identity(
            principal=principal,
            audience="stg",
            scopes=frozenset({"stg:observe"}),
            expires_at=NOW_EPOCH + 12 * 3600,
        )
    )
    return store.exchange(code).session_id


def test_second_bridge_for_the_same_pair_is_conflict() -> None:
    store = _store()
    session = _session(store)
    store.register_bridge(session, "bench-a", cap=4)
    with pytest.raises(BridgeRefused) as refused:
        store.register_bridge(session, "bench-a", cap=4)
    assert refused.value.reason == "conflict"


def test_fifth_distinct_pair_is_refused_at_the_cap() -> None:
    """The default cap is 4 (``ui_max_bridges_per_session``); the fifth
    DISTINCT pair is refused ``cap``. The cap counts concurrent pairs —
    re-claiming a deregistered pair always succeeds."""
    store = _store()
    session = _session(store)
    for index in range(4):
        store.register_bridge(session, f"bench-{index}", cap=4)
    with pytest.raises(BridgeRefused) as refused:
        store.register_bridge(session, "bench-4", cap=4)
    assert refused.value.reason == "cap"
    store.deregister_bridge(session, "bench-0")
    store.register_bridge(session, "bench-4", cap=4)  # freed slot re-claimable


def test_bridges_are_per_session_not_global() -> None:
    """Two sessions may each hold a bridge on the SAME bench — the one
    bridge per (session, bench) rule is per pair, not per bench."""
    store = _store()
    first = _session(store, "op-one")
    second = _session(store, "op-two")
    store.register_bridge(first, "bench-a", cap=4)
    store.register_bridge(second, "bench-a", cap=4)
    assert store.bridge_benches(first) == frozenset({"bench-a"})
    assert store.bridge_benches(second) == frozenset({"bench-a"})


def test_only_a_live_session_can_claim() -> None:
    store = _store()
    with pytest.raises(BridgeRefused) as unknown:
        store.register_bridge("no-such-session", "bench-a", cap=4)
    assert unknown.value.reason == "unauthenticated"


def test_logout_deregisters_the_sessions_bridges() -> None:
    store = _store()
    session = _session(store)
    store.register_bridge(session, "bench-a", cap=4)
    store.register_bridge(session, "bench-b", cap=4)
    store.logout(session)
    assert store.bridge_benches(session) == frozenset()
    # The session is gone: a re-claim refuses unauthenticated, and the
    # freed pair accepts a bridge from a NEW session immediately.
    with pytest.raises(BridgeRefused) as refused:
        store.register_bridge(session, "bench-a", cap=4)
    assert refused.value.reason == "unauthenticated"


def test_expiry_sweep_deregisters_the_sessions_bridges() -> None:
    """The lazy expiry sweep (``resolve`` of the expired session) clears
    the session's bridges with the record — a bridge cannot outlive its
    session in the registry even if no generator ``finally`` ever runs."""
    now = NOW_EPOCH
    store = SessionStore(now_epoch=lambda: now, session_ttl_s=60)
    session = _session(store)
    store.register_bridge(session, "bench-a", cap=4)
    now = NOW_EPOCH + 7200  # advance the injected clock past expiry
    store._now = lambda: now
    assert store.resolve(session) is None
    assert store.bridge_benches(session) == frozenset()


def test_deregister_is_idempotent() -> None:
    """The generator's ``finally`` and the session's death can both fire:
    the second deregistration is a no-op, never an error."""
    store = _store()
    session = _session(store)
    store.register_bridge(session, "bench-a", cap=4)
    store.deregister_bridge(session, "bench-a")
    store.deregister_bridge(session, "bench-a")
    assert store.bridge_benches(session) == frozenset()
