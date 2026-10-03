"""Browser sessions: server-side, cookie-mapped, at-most-as-wide
projections of a validated Identity (CON-15, G2a design §2.2).

The store is the whole session layer. A browser never holds a bearer
token (NFR-S1): the cookie carries an opaque session id only, and every
authority-bearing fact — principal, scopes, expiry, the CSRF token —
lives in the server-side record this module owns. Three consequences are
structural, not policy:

- **Narrowing only.** A login code may project a SUBSET of the caller's
  scopes and a session that ends no later than the caller token's own
  expiry; anything wider is refused at the mint (``MintRejected``), never
  silently clamped (NFR-S2).
- **Single-use codes.** The mint hands out one random, opaque
  ``secrets.token_urlsafe`` value; the store keys its record by
  ``sha256(code)``, so the raw secret exists exactly once — in the mint
  response — and no in-memory structure carries it. The lookup is a dict
  key computed from the presented bytes (no string comparison on the
  secret at all).
- **Server-side invalidation.** Logout deletes the record; expiry is
  enforced at resolution (lazily swept, no janitor thread); and a gateway
  restart empties the store, killing every session (GW-94) — the cookie
  alone is worthless the moment the record is gone.

Clock discipline mirrors ``identity.py``: ``now_epoch`` is injected, so
issue, exchange, expiry and sweep behaviour are deterministic under test.
The login-code record is marked used under the same lock that resolves
the exchange, which is what makes single-use atomic rather than advisory.

The bridge registry (one SSE bridge per session-and-bench, capped per
session) joins this record with the G2c event-bridge slice; G2a ships the
store without it.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace

from benchweave.interfaces.identity import Identity


class LoginCodeRejected(ValueError):
    """A login code was not exchanged; ``reason`` names the class.

    ``unknown`` | ``expired`` | ``used`` — the rendered refusal is the
    same for all three (the caller learns nothing about which codes
    exist); the reason distinguishes the log line.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MintRejected(ValueError):
    """A login-code mint was refused; ``reason`` names the class.

    ``invalid_request`` — the requested shape violates a service limit
    (non-positive or over-ceiling session TTL). ``forbidden`` — the
    request would widen the projection beyond the caller token (a scope
    the caller lacks, or an expiry past the token's own).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SessionRecord:
    """One live browser session — everything the cookie stands for.

    ``session_id`` and ``csrf_token`` are independent opaque tokens;
    neither encodes or derives any identity fact.
    """

    session_id: str
    principal: str
    audience: str
    scopes: frozenset[str]
    expires_at: int
    csrf_token: str


@dataclass(frozen=True)
class _LoginCode:
    """The server side of one minted login code (keyed by sha256)."""

    principal: str
    audience: str
    scopes: frozenset[str]
    caller_expires_at: int
    code_expires_at: int
    session_ttl_s: int
    used: bool = False


def _keyed(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class SessionStore:
    """``session_id -> SessionRecord`` plus the login-code side table.

    Both tables live under one lock; every method that decides
    single-use, expiry or deletion does so inside it, so no interleaving
    of requests can double-spend a code or resurrect a session.
    """

    def __init__(
        self,
        *,
        now_epoch: Callable[[], int],
        code_ttl_s: int = 60,
        session_ttl_s: int = 8 * 3600,
    ) -> None:
        self._now = now_epoch
        self._code_ttl_s = code_ttl_s
        self._session_ttl_s = session_ttl_s
        self._lock = threading.Lock()
        self._codes: dict[str, _LoginCode] = {}
        self._sessions: dict[str, SessionRecord] = {}

    # --- mint ----------------------------------------------------------------

    def mint_login_code(
        self,
        caller: Identity,
        *,
        scopes: frozenset[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> str:
        """Mint a single-use login code projecting (a subset of) ``caller``.

        Validation order is service shape first, identity second: a
        non-positive or over-ceiling ``ttl_seconds`` is
        ``invalid_request``; a scope outside the caller's set or an
        expiry past the caller token's own is ``forbidden`` (NFR-S2 —
        widening is refused, never clamped). Returns the raw code; the
        store keeps only its hash.
        """
        granted = frozenset(caller.scopes if scopes is None else scopes)
        now = self._now()
        if ttl_seconds is None:
            ttl_seconds = self._session_ttl_s
        if ttl_seconds <= 0 or ttl_seconds > self._session_ttl_s:
            raise MintRejected("invalid_request")
        if not granted <= caller.scopes:
            raise MintRejected("forbidden")
        if now + ttl_seconds > caller.expires_at:
            raise MintRejected("forbidden")
        code = secrets.token_urlsafe(32)
        with self._lock:
            self._sweep_codes_locked(now)
            self._codes[_keyed(code)] = _LoginCode(
                principal=caller.principal,
                audience=caller.audience,
                scopes=granted,
                caller_expires_at=caller.expires_at,
                code_expires_at=now + self._code_ttl_s,
                session_ttl_s=ttl_seconds,
            )
        return code

    # --- exchange ------------------------------------------------------------

    def exchange(self, code: str) -> SessionRecord:
        """Exchange a login code for a session, exactly once.

        Unknown, expired and used codes are refused by class; a code
        whose caller token has since expired refuses as ``expired`` too —
        the projection cannot outlive its source identity, not even for
        one session. The used-marking, the code's retirement from
        re-exchange, and the session's creation all happen under the one
        lock, which is the single-use guarantee.
        """
        key = _keyed(code)
        with self._lock:
            now = self._now()
            entry = self._codes.get(key)
            if entry is None:
                raise LoginCodeRejected("unknown")
            if entry.used:
                raise LoginCodeRejected("used")
            if now >= entry.code_expires_at:
                del self._codes[key]
                raise LoginCodeRejected("expired")
            if entry.caller_expires_at <= now:
                del self._codes[key]
                raise LoginCodeRejected("expired")
            # Retire the code by marking it used (a replay then reads
            # ``used``, distinguishing an attack from a stale link) and
            # create the session in the same critical section.
            self._codes[key] = replace(entry, used=True)
            session = SessionRecord(
                session_id=secrets.token_urlsafe(32),
                principal=entry.principal,
                audience=entry.audience,
                scopes=entry.scopes,
                # The session runs for the GRANTED ttl from the moment
                # of exchange, still ending no later than the caller
                # token ever allowed (NFR-S2's second bound).
                expires_at=min(now + entry.session_ttl_s, entry.caller_expires_at),
                csrf_token=secrets.token_urlsafe(32),
            )
            self._sessions[session.session_id] = session
            return session

    # --- sessions ------------------------------------------------------------

    def resolve(self, session_id: str) -> SessionRecord | None:
        """The live record for ``session_id``, or ``None``.

        ``None`` covers unknown, logged-out and expired alike — the
        caller cannot distinguish them, and does not need to. An expired
        record is deleted on first resolution (the lazy sweep).
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if self._now() >= session.expires_at:
                del self._sessions[session_id]
                return None
            return session

    def logout(self, session_id: str) -> None:
        """Delete the session record; the cookie alone is dead from here
        (GW-94). Idempotent — logging out an unknown id is a no-op, never
        an error a browser could learn from."""
        with self._lock:
            self._sessions.pop(session_id, None)

    # --- internals -----------------------------------------------------------

    def _sweep_codes_locked(self, now: int) -> None:
        """Drop fully-expired code records (used markers included).

        Runs inside the lock at mint time — outstanding codes number at
        most the mints of the last TTL window, so the sweep is bounded by
        construction. A used marker within its TTL is deliberately kept:
        its replay still reads ``used``.
        """
        for key in [
            key for key, entry in self._codes.items() if now >= entry.code_expires_at
        ]:
            del self._codes[key]
