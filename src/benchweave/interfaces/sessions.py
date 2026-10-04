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
from typing import Any

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


class BridgeRefused(ValueError):
    """An SSE bridge claim was refused; ``reason`` names the class.

    ``conflict`` — the (session, bench) pair already holds a bridge
    (GW-33: one bridge per pair). ``cap`` — the session already holds
    ``ui_max_bridges_per_session`` bridges. ``unauthenticated`` — the
    session is not live; a stream never outlives its session. The UI
    adapter renders ``unauthenticated`` through the 401 row and the
    ownership refusals through the ``conflict`` row, the message naming
    the reason (FOLD-4: the refusal class, not the call site, picks the
    row).
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
    #: The GRANTED duration in seconds, recorded at exchange (G3a, design
    #: §2.1): the ttl from the exchange instant to ``expires_at`` — GW-44
    #: D1's percentage base for the session-expiry warning. ``0`` means
    #: "not recorded" (records constructed outside ``exchange``) and
    #: composes no warning verdict.
    duration_s: int = 0


@dataclass(frozen=True)
class HeldLease:
    """The session's held-lease view (G3a, design §2.1): the lease
    projection THIS session's ``lease_create``/``lease_renew`` response
    carried, plus the ``duration_ms`` the session requested (GW-44's
    percentage base). Presentation state of the session's own seam
    answers — never an authority source: every mutating POST re-validates
    at the seam, and a stale view fails there exactly as for any client.

    The wire deliberately omits the holder (the lease def's closed five
    fields); the view needs none — holder display renders the session's
    own principal, correct by construction because the seam mints
    ``holder = identity.principal`` and renews holder-only."""

    lease_id: str
    bench_id: str
    sequence: int
    expires_at: str
    state: str
    requested_duration_ms: int


@dataclass(frozen=True)
class StagedStart:
    """The session's staged-start record (G3b, design §2.1's second side
    table): one staging cycle per (session, bench) — the staged binding
    ref, the recorded ``run_check`` answer (``None`` until one has
    returned for the CURRENT staged set, GW-51), the armed flag, and the
    staging cycle's request id.

    The request id is the STAGED BINDING document's own ``request_id``,
    not a session-minted one: the seam's binding-match pre-check requires
    ``run_start``'s §9 request id to equal the binding document's own
    top-level ``request_id``, so the id the UI replays is the binding's —
    fixed across check/arm/confirm and post-refusal retries by
    construction (the same staged binding always carries the same id).
    A different binding is a new cycle with a new id. Presentation state
    of the session's own seam answers — never authority."""

    request_id: str | None
    binding_ref: dict[str, Any]
    check: dict[str, Any] | None
    armed: bool


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
        # The bridge registry (G2c, design §2.5): session_id -> the set of
        # benches that session holds an SSE bridge on. The bridge's live
        # state is its generator; this registry is the OWNERSHIP record the
        # pair rule and the per-session cap decide against — under the same
        # lock as the records, so a logout or expiry sweep and a concurrent
        # bridge claim can never interleave.
        self._bridges: dict[str, set[str]] = {}
        # The held-lease views (G3a, design §2.1): session_id -> the
        # benches that session holds a lease VIEW on, same death
        # semantics as the records themselves (logout, the lazy expiry
        # sweep, gateway restart).
        self._leases: dict[str, dict[str, HeldLease]] = {}
        # The staged-start records (G3b, design §2.1's second side
        # table): session_id -> {bench_id -> StagedStart}, same lock,
        # same death semantics. Presentation of the session's own
        # staged binding/check/arm cycle — never authority.
        self._staged: dict[str, dict[str, StagedStart]] = {}
        # Pending-cancel markers (G3b GW-55): session_id -> run ids the
        # session has POSTed a cancellation for. The marker presents the
        # OPERATOR'S OWN action until the seam reports the run terminal;
        # the state itself is always run_get's.
        self._cancels: dict[str, set[str]] = {}

    # --- held leases (G3a: response-sourced views, never authority) --------

    def record_held_lease(self, session_id: str, view: HeldLease) -> None:
        """Store the view this session's own lease response carried.
        Keyed (session, bench); a re-record (a renew's successor
        projection) replaces the view."""
        with self._lock:
            self._leases.setdefault(session_id, {})[view.bench_id] = view

    def clear_held_lease(self, session_id: str, bench_id: str) -> None:
        """Drop the view (release cleared it; a seam refusal on the
        renew/release path clears the stale view — R2's mitigation).
        Idempotent: a second clear is a no-op."""
        with self._lock:
            held = self._leases.get(session_id)
            if held is not None:
                held.pop(bench_id, None)
                if not held:
                    del self._leases[session_id]

    def held_lease(self, session_id: str, bench_id: str) -> HeldLease | None:
        """The session's view for ``bench_id``, or ``None`` — a snapshot
        under the lock (the caller renders from it; the seam re-validates
        every mutation)."""
        with self._lock:
            return self._leases.get(session_id, {}).get(bench_id)

    def held_lease_for_lease(self, session_id: str, lease_id: str) -> HeldLease | None:
        """The session's view whose lease id matches, or ``None`` — the
        server-truth lookup the mutating routes resolve their bench key
        from (FOLD-4: a client-supplied bench field never keys a view;
        the store keys views by bench and each value carries its own
        ``bench_id``)."""
        with self._lock:
            for view in self._leases.get(session_id, {}).values():
                if view.lease_id == lease_id:
                    return view
            return None

    # --- staged starts and pending-cancel markers (G3b) -----------------------

    def record_staged_start(
        self, session_id: str, bench_id: str, staged: StagedStart
    ) -> None:
        """Store the staging cycle's record, keyed (session, bench); a
        re-record REPLACES it (a different binding is the new cycle;
        the caller keeps a same-binding re-stage's id stable by passing
        the same request id)."""
        with self._lock:
            self._staged.setdefault(session_id, {})[bench_id] = staged

    def staged_start(self, session_id: str, bench_id: str) -> StagedStart | None:
        """The session's staging record for ``bench_id``, or ``None`` —
        a snapshot under the lock (the caller renders from it; the seam
        re-validates every start)."""
        with self._lock:
            return self._staged.get(session_id, {}).get(bench_id)

    def clear_staged_start(self, session_id: str, bench_id: str) -> None:
        """Drop the record (a start committed). Idempotent."""
        with self._lock:
            staged = self._staged.get(session_id)
            if staged is not None:
                staged.pop(bench_id, None)
                if not staged:
                    del self._staged[session_id]

    def record_cancel_request(self, session_id: str, run_id: str) -> None:
        """Mark that this session POSTed a cancellation for ``run_id``
        (GW-55's marker is presentation of the operator's own action)."""
        with self._lock:
            self._cancels.setdefault(session_id, set()).add(run_id)

    def cancel_requested(self, session_id: str, run_id: str) -> bool:
        """Whether this session's marker for ``run_id`` is set."""
        with self._lock:
            return run_id in self._cancels.get(session_id, set())

    def clear_cancel_request(self, session_id: str, run_id: str) -> None:
        """Drop the marker (the run reported terminal; the presentation
        gives way to the state itself). Idempotent."""
        with self._lock:
            markers = self._cancels.get(session_id)
            if markers is not None:
                markers.discard(run_id)
                if not markers:
                    del self._cancels[session_id]

    # --- bridges (G2c: one SSE bridge per session-and-bench, GW-33) --------

    def register_bridge(self, session_id: str, bench_id: str, *, cap: int) -> None:
        """Claim the (session, bench) bridge slot, or refuse by class.

        ``conflict`` — the pair is held; ``cap`` — the session holds
        ``cap`` bridges already; ``unauthenticated`` — the session is not
        live (only a live session can open a stream, and a stream never
        outlives its session). Atomic with every other session decision:
        the check and the claim happen under the one lock.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or self._now() >= session.expires_at:
                raise BridgeRefused("unauthenticated")
            held = self._bridges.setdefault(session_id, set())
            if bench_id in held:
                raise BridgeRefused("conflict")
            if len(held) >= cap:
                raise BridgeRefused("cap")
            held.add(bench_id)

    def deregister_bridge(self, session_id: str, bench_id: str) -> None:
        """Release the (session, bench) slot. Idempotent by design: the
        generator's ``finally`` and the session's own death can both fire
        — the second release is a no-op, never an error."""
        with self._lock:
            held = self._bridges.get(session_id)
            if held is not None:
                held.discard(bench_id)
                if not held:
                    del self._bridges[session_id]

    def bridge_benches(self, session_id: str) -> frozenset[str]:
        """The benches this session holds bridges on (the suite's
        observable; a snapshot under the lock)."""
        with self._lock:
            return frozenset(self._bridges.get(session_id, ()))

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
            granted_expiry = min(now + entry.session_ttl_s, entry.caller_expires_at)
            session = SessionRecord(
                session_id=secrets.token_urlsafe(32),
                principal=entry.principal,
                audience=entry.audience,
                scopes=entry.scopes,
                # The session runs for the GRANTED ttl from the moment
                # of exchange, still ending no later than the caller
                # token ever allowed (NFR-S2's second bound).
                expires_at=granted_expiry,
                csrf_token=secrets.token_urlsafe(32),
                # GW-44 D1's percentage base: the granted ttl itself,
                # recorded once at exchange.
                duration_s=granted_expiry - now,
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
                # The session's bridges die with the record: a bridge can
                # never outlive its session in the registry, even if no
                # generator ``finally`` ever runs (G2c teardown belt).
                self._bridges.pop(session_id, None)
                # The held-lease views die with it too (G3a): a view is
                # presentation of one session's own answers, never a
                # fact another record may keep.
                self._leases.pop(session_id, None)
                # The staging records and pending-cancel markers die with
                # it as well (G3b): presentation of one session's own
                # answers, never facts another record may keep.
                self._staged.pop(session_id, None)
                self._cancels.pop(session_id, None)
                return None
            return session

    def logout(self, session_id: str) -> None:
        """Delete the session record; the cookie alone is dead from here
        (GW-94). The session's bridges are dropped with it — logout ends
        every read the session's tabs were making. Idempotent — logging
        out an unknown id is a no-op, never an error a browser could
        learn from."""
        with self._lock:
            self._sessions.pop(session_id, None)
            self._bridges.pop(session_id, None)
            self._leases.pop(session_id, None)
            self._staged.pop(session_id, None)
            self._cancels.pop(session_id, None)

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
