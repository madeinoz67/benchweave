"""The browser-session store (G2a, design §2.2; invariant CON-15).

Server-side only: a gateway restart empties the store and invalidates every
session (GW-94). The cookie carries an opaque session id; scopes and expiry
live in the record, never on the wire. Narrowing is permitted and widening
is structurally refused at the mint (NFR-S2).

Clock: every arm runs on an injected clock (the ``identity.py`` discipline)
— no wall-clock waits anywhere in this file.
"""

from __future__ import annotations

import re

import pytest

from benchweave.interfaces.identity import Identity
from benchweave.interfaces.sessions import (
    LoginCodeRejected,
    MintRejected,
    SessionStore,
)

NOW = 1_800_000_000
_CODE_TTL_S = 60
_SESSION_TTL_S = 8 * 3600

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class _Clock:
    """A mutable epoch clock — tests advance it explicitly."""

    def __init__(self, now: int = NOW) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


def _identity(
    *,
    principal: str = "ui-operator",
    scopes: frozenset[str] = frozenset({"stg:observe", "stg:control"}),
    # Long enough that the 8h session ceiling is the binding constraint
    # only where an arm means it to be (the narrowing arms shorten it).
    expires_at: int = NOW + 12 * 3600,
) -> Identity:
    return Identity(
        principal=principal, audience="stg", scopes=scopes, expires_at=expires_at
    )


def _store(clock: _Clock) -> SessionStore:
    return SessionStore(
        now_epoch=clock,
        code_ttl_s=_CODE_TTL_S,
        session_ttl_s=_SESSION_TTL_S,
    )


# --- mint -> exchange: the happy path -----------------------------------------


def test_exchange_returns_the_callers_projection() -> None:
    clock = _Clock()
    store = _store(clock)
    code = store.mint_login_code(
        _identity(), scopes=frozenset({"stg:observe"}), ttl_seconds=600
    )
    record = store.exchange(code)
    assert record.principal == "ui-operator"
    assert record.audience == "stg"
    assert record.scopes == frozenset({"stg:observe"})
    # Narrowing preserves expiry: the session can never outlive the caller
    # token that minted it (NFR-S2).
    assert record.expires_at == NOW + 600
    # Both opaque values are URL-safe tokens, never derived identity data.
    assert re.fullmatch(r"[A-Za-z0-9_-]{40,}", record.session_id)
    assert re.fullmatch(r"[A-Za-z0-9_-]{40,}", record.csrf_token)
    assert record.session_id != record.csrf_token


def test_default_mint_is_the_full_scope_set_at_the_session_ceiling() -> None:
    clock = _Clock()
    store = _store(clock)
    code = store.mint_login_code(_identity())
    record = store.exchange(code)
    assert record.scopes == frozenset({"stg:observe", "stg:control"})
    # The configured ceiling applies, still clamped by the caller token.
    assert record.expires_at == NOW + _SESSION_TTL_S


# --- the refusal matrix: each arm REDs alone -----------------------------------


def test_replay_of_a_used_code_is_refused() -> None:
    store = _store(_Clock())
    code = store.mint_login_code(_identity())
    store.exchange(code)
    with pytest.raises(LoginCodeRejected) as rejected:
        store.exchange(code)
    assert rejected.value.reason == "used"


def test_expired_code_is_refused_on_the_injected_clock() -> None:
    clock = _Clock()
    store = _store(clock)
    code = store.mint_login_code(_identity())
    clock.now = NOW + _CODE_TTL_S  # exactly at the TTL boundary: dead
    with pytest.raises(LoginCodeRejected) as rejected:
        store.exchange(code)
    assert rejected.value.reason == "expired"


def test_unknown_code_is_refused() -> None:
    store = _store(_Clock())
    with pytest.raises(LoginCodeRejected) as rejected:
        store.exchange("not-a-code")
    assert rejected.value.reason == "unknown"


def test_code_authority_dies_with_the_caller_token() -> None:
    """A code legally minted (session expiry == the caller token's own)
    refuses at exchange once that token has since expired — the
    projection cannot outlive its source identity, not even for one
    session."""
    clock = _Clock()
    store = _store(clock)
    code = store.mint_login_code(
        _identity(expires_at=NOW + 30), ttl_seconds=30  # exactly the caller's life
    )
    clock.now = NOW + 31
    with pytest.raises(LoginCodeRejected) as rejected:
        store.exchange(code)
    assert rejected.value.reason == "expired"


# --- narrowing-only: widening is structurally refused (NFR-S2) -----------------


def test_scope_widening_is_refused_at_the_mint() -> None:
    store = _store(_Clock())
    with pytest.raises(MintRejected) as rejected:
        store.mint_login_code(
            _identity(scopes=frozenset({"stg:observe"})),
            scopes=frozenset({"stg:observe", "stg:admin"}),
        )
    assert rejected.value.reason == "forbidden"


def test_expiry_widening_past_the_caller_token_is_refused() -> None:
    store = _store(_Clock())
    with pytest.raises(MintRejected) as rejected:
        store.mint_login_code(_identity(expires_at=NOW + 600), ttl_seconds=3600)
    assert rejected.value.reason == "forbidden"


def test_ttl_over_the_configured_ceiling_is_refused() -> None:
    store = _store(_Clock())
    with pytest.raises(MintRejected) as rejected:
        store.mint_login_code(_identity(), ttl_seconds=_SESSION_TTL_S + 1)
    assert rejected.value.reason == "invalid_request"


@pytest.mark.parametrize("bad_ttl", [0, -1])
def test_non_positive_ttl_is_refused(bad_ttl: int) -> None:
    store = _store(_Clock())
    with pytest.raises(MintRejected) as rejected:
        store.mint_login_code(_identity(), ttl_seconds=bad_ttl)
    assert rejected.value.reason == "invalid_request"


# --- sessions: resolve, expiry, logout, restart --------------------------------


def test_resolve_returns_the_record_until_logout() -> None:
    clock = _Clock()
    store = _store(clock)
    code = store.mint_login_code(_identity())
    record = store.exchange(code)
    assert store.resolve(record.session_id) == record
    store.logout(record.session_id)
    assert store.resolve(record.session_id) is None


def test_logout_is_idempotent() -> None:
    store = _store(_Clock())
    store.logout("never-existed")  # must not raise


def test_expired_session_resolves_to_none_and_is_swept() -> None:
    clock = _Clock()
    store = _store(clock)
    code = store.mint_login_code(_identity())
    record = store.exchange(code)
    clock.now = record.expires_at  # at the boundary: dead
    assert store.resolve(record.session_id) is None
    # The lazy sweep deleted the record (bounded memory, no janitor thread).
    assert record.session_id not in store._sessions


def test_a_new_store_invalidates_every_prior_session() -> None:
    """GW-94: sessions are server-side state — a restart (a new store) has
    no knowledge of the old ids, so every prior cookie is dead."""
    clock = _Clock()
    first = _store(clock)
    code = first.mint_login_code(_identity())
    record = first.exchange(code)
    second = _store(clock)
    assert second.resolve(record.session_id) is None


def test_codes_are_stored_hashed_never_raw() -> None:
    """CON-15's sibling hygiene: the login code exists raw exactly once —
    in the mint response. The store keys by sha256, so no in-memory
    structure (and no dump of one) carries the secret."""
    store = _store(_Clock())
    code = store.mint_login_code(_identity())
    assert all(_SHA256_HEX.match(key) for key in store._codes)
    assert code not in store._codes
