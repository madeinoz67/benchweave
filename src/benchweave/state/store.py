"""Durable run/lease/request/event state over SQLite (WP03).

Single-writer store: WAL journal, synchronous=FULL, explicit transactions.
Timestamps are caller-supplied (no clock reads); no device, network or
plugin I/O lives here. Sequence authorities (per-bench lease sequence,
per-stream event sequence) are assigned under BEGIN IMMEDIATE, which makes
them monotonic and gap-free by construction.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchweave.state.migrations import MIGRATIONS


class Duplicate(Exception):
    """Idempotent replay: same key, same body, already accepted."""


class Conflict(Exception):
    """Same key, different body: not a replay, a client bug or a race."""


class LeaseNotActive(ValueError):
    """A lease operation targeted a sequence that is not active."""


@dataclass(frozen=True)
class AcceptResult:
    """The §9 idempotency verdict: ``outcome`` is ``"accepted"`` on first
    sight or ``"duplicate"`` on a byte-identical replay; ``run_id`` is the
    id the key resolves to either way."""

    outcome: str  # "accepted" | "duplicate"
    run_id: str


@dataclass(frozen=True)
class Lease:
    """One immutable row of a bench's lease ledger, at its store-assigned
    gap-free ``sequence``; ``state`` is ``"active"`` or ``"released"`` as
    stored (a consumed lease records ``released`` too — see
    ``Store.consume_lease``)."""

    lease_id: str
    bench_id: str
    sequence: int
    holder: str
    expires_at: str
    state: str


def accept_result(result: AcceptResult) -> str:
    """The outcome string alone, for callers that branch on nothing else."""
    return result.outcome


class Store:
    """Single-writer: SQLite permits one writer; every write serialises through
    this store's connection. Callers must never open a second write path."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    @property
    def connection(self) -> sqlite3.Connection:
        """The single writer connection (shared with ContentStore, WP07)."""
        return self._conn

    # --- lifecycle ---------------------------------------------------------

    @classmethod
    def open(cls, path: str | Path, *, check_same_thread: bool = True) -> Store:
        """Open (or create) the database at ``path`` and bring it to the
        current schema: WAL, synchronous=FULL and a 5s busy timeout are set
        first, then every pending migration is applied, each under its own
        BEGIN IMMEDIATE (a failed migration rolls back whole)."""
        # ``check_same_thread=False`` is the ASGI-app posture (WP07 Task 8):
        # the gateway serves from the event-loop thread while the store was
        # opened on the caller's thread; usage stays serialised by design
        # (single serving loop + the app write gate + WAL busy timeout), and
        # the run worker keeps its own thread-affine connection.
        connection = sqlite3.connect(
            str(path), isolation_level=None, check_same_thread=check_same_thread
        )
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=5000")
        store = cls(connection)
        store._apply_migrations()
        return store

    def close(self) -> None:
        """Close the underlying connection; the store is unusable after."""
        self._conn.close()

    def _apply_migrations(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        # B6: refuse-newer guard. A database written by a newer gateway
        # (on-disk MAX(version) above the newest known migration) would
        # otherwise open as silently "migrated", lying about its schema;
        # v5 makes downgrade reachable for the first time and the family
        # has paid for silent downgrade twice.
        on_disk = int(
            self._conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            or 0
        )
        if on_disk > MIGRATIONS[-1].version:
            raise RuntimeError(
                f"refuse_newer_schema: on-disk schema version {on_disk} is newer "
                f"than the newest known migration ({MIGRATIONS[-1].version}); "
                "downgrade is refused — run a gateway version that knows this "
                "schema before opening this database"
            )
        for migration in MIGRATIONS:
            applied = self._conn.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?", (migration.version,)
            ).fetchone()[0]
            if applied:
                continue
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in migration.statements:
                    self._conn.execute(statement)
                self._conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (migration.version, "applied-by-migration"),
                )
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def schema_version(self) -> int:
        """The highest applied migration version (0 on a virgin database)."""
        row = self._conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0)

    # --- request idempotency -------------------------------------------------

    def accept_request(self, key: str, body_sha256: str, run_id: str, now: str) -> AcceptResult:
        """File an idempotency key under BEGIN IMMEDIATE (§9): first sight
        inserts the row and returns ``accepted`` with the caller's
        ``run_id``; a byte-identical replay (same ``body_sha256``) returns
        ``duplicate`` carrying the ORIGINALLY filed run id; the same key
        with a different body raises ``Conflict`` and files nothing."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT body_sha256, run_id FROM requests WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if row is not None:
                self._conn.execute("ROLLBACK")
                if row[0] == body_sha256:
                    return AcceptResult(outcome="duplicate", run_id=row[1])
                raise Conflict(f"idempotency key {key!r} reused with a different body")
            self._conn.execute(
                "INSERT INTO requests (idempotency_key, body_sha256, run_id, accepted_at)"
                " VALUES (?, ?, ?, ?)",
                (key, body_sha256, run_id, now),
            )
        except BaseException:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return AcceptResult(outcome="accepted", run_id=run_id)

    def find_request(self, key: str) -> dict[str, Any] | None:
        """The filed request row for ``key``, or None when never accepted."""
        row = self._conn.execute(
            "SELECT idempotency_key, body_sha256, run_id, accepted_at"
            " FROM requests WHERE idempotency_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "idempotency_key": row[0],
            "body_sha256": row[1],
            "run_id": row[2],
            "accepted_at": row[3],
        }

    def reconcile_dangling_requests(self) -> list[str]:
        """Purge §9 RUN-request keys whose run never materialized (D13).

        ``accept_request`` and ``create_run`` are two transactions: a
        process death between them files a key that points at no run, and
        every same-body replay then resolves the key and fails on the
        ghost — a permanent wedge. This sweep (the store leg of the app
        lifespan's recovery entrypoint, alongside
        ``RunCoordinator.recover_interrupted``) deletes exactly those RUN
        keys: the anti-join must resolve in EVERY durable table the one
        ``requests`` store serves — a ``change_submit`` key's ``run_id``
        column holds a CHANGE id (change ids are not run ids and never
        become them), and a ``lease_renew`` key's holds the LEASE id
        (renewal re-issues the same identity at a new sequence, so a
        lease row has existed since creation — a renewal key is never
        dangling), so keys that resolve in ``changes`` or ``leases`` are
        healthy and keep their replay protection, as do run keys whose
        run row exists, live or tombstoned. Idempotent by construction;
        returns the purged keys.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            rows = self._conn.execute(
                "SELECT requests.idempotency_key FROM requests"
                " LEFT JOIN runs ON runs.run_id = requests.run_id"
                " LEFT JOIN changes ON changes.change_id = requests.run_id"
                " LEFT JOIN leases ON leases.lease_id = requests.run_id"
                " WHERE runs.run_id IS NULL AND changes.change_id IS NULL"
                " AND leases.lease_id IS NULL"
            ).fetchall()
            keys = [str(row[0]) for row in rows]
            for key in keys:
                self._conn.execute(
                    "DELETE FROM requests WHERE idempotency_key = ?", (key,)
                )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return keys

    # --- runs -----------------------------------------------------------------

    def create_run(self, run_id: str, binding: dict[str, Any], principal_id: str, now: str) -> None:
        """Insert the run row (binding stored as canonical sorted-key JSON).

        ``ValueError`` when the id already exists — live or tombstoned:
        run ids are never reusable, so a tombstone burns the id forever.
        """
        existing = self._conn.execute(
            "SELECT tombstoned FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if existing is not None:
            if existing[0]:
                raise ValueError(f"run {run_id!r} is tombstoned; ids are never reusable")
            raise ValueError(f"run {run_id!r} already exists")
        self._conn.execute("BEGIN IMMEDIATE")
        self._conn.execute(
            "INSERT INTO runs (run_id, binding_json, principal_id, started_at)"
            " VALUES (?, ?, ?, ?)",
            (run_id, json.dumps(binding, sort_keys=True), principal_id, now),
        )
        self._conn.execute("COMMIT")

    def set_run_authority(self, run_id: str, authority: str) -> None:
        """Record whether the run's authority came from a lease ("lease") or
        the gateway ("gateway") — D9 lease-authority modeling; WP08 Task 3
        consumes the field for commissioned takeover."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = self._conn.execute(
                "UPDATE runs SET authority = ? WHERE run_id = ?", (authority, run_id)
            )
        except BaseException:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        if cursor.rowcount != 1:
            self._conn.execute("ROLLBACK")
            raise ValueError(f"run {run_id!r} not found")
        self._conn.execute("COMMIT")

    def finalize_run(self, run_id: str, terminal: dict[str, Any]) -> None:
        """Stamp the terminal envelope onto a live run; ``ValueError`` when
        the run is unknown or tombstoned."""
        cursor = self._conn.execute(
            "UPDATE runs SET terminal_json = ? WHERE run_id = ? AND tombstoned = 0",
            (json.dumps(terminal, sort_keys=True), run_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"run {run_id!r} not found or tombstoned")

    def delete_run(self, run_id: str, now: str) -> None:
        """Tombstone a run — soft delete: the row stays, the id stays
        burned (``create_run`` refuses it forever). ``ValueError`` when the
        run is unknown or already tombstoned."""
        cursor = self._conn.execute(
            "UPDATE runs SET tombstoned = 1, tombstoned_at = ? WHERE run_id = ? AND tombstoned = 0",
            (now, run_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"run {run_id!r} not found or already tombstoned")

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """The full run row (binding/terminal JSON decoded, tombstones
        included), or None when the id was never created."""
        row = self._conn.execute(
            "SELECT binding_json, principal_id, started_at, terminal_json, tombstoned,"
            " tombstoned_at, authority FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "run_id": run_id,
            "binding": json.loads(row[0]),
            "principal_id": row[1],
            "started_at": row[2],
            "terminal": json.loads(row[3]) if row[3] is not None else None,
            "tombstoned": bool(row[4]),
            "tombstoned_at": row[5],
            # D9 lease-authority modeling (WP08 Task 2): "lease" | "gateway".
            "authority": str(row[6]),
        }

    # --- leases -----------------------------------------------------------------

    def next_lease(self, bench_id: str, lease_id: str, holder: str, expires_at: str) -> Lease:
        """Issue the bench's next lease at MAX(sequence)+1 under BEGIN
        IMMEDIATE — the per-bench sequence authority: assignment inside the
        write transaction is what makes lease sequences monotonic and
        gap-free. Returns the row just written, state ``active``."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT MAX(sequence) FROM leases WHERE bench_id = ?", (bench_id,)
            ).fetchone()
            sequence = int(row[0] or 0) + 1
            self._conn.execute(
                "INSERT INTO leases (bench_id, sequence, lease_id, holder, expires_at, state)"
                " VALUES (?, ?, ?, ?, ?, 'active')",
                (bench_id, sequence, lease_id, holder, expires_at),
            )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return Lease(
            lease_id=lease_id,
            bench_id=bench_id,
            sequence=sequence,
            holder=holder,
            expires_at=expires_at,
            state="active",
        )

    def release_lease(self, bench_id: str, sequence: int, now: str) -> None:
        """Release an active lease (the holder returns the bench)."""
        self._close_lease(bench_id, sequence, now)

    def consume_lease(self, bench_id: str, sequence: int, now: str) -> None:
        """Consume an active lease for a commissioned takeover (D12).

        The interface lease-state enum is closed (active | released |
        expired), so consumption records ``released`` like a holder
        release; what distinguishes it is the audit trail — the
        ``authority_changed`` bench event and the commissioned run's
        ``authority='lease'`` row. A consumed lease can never authorize a
        second takeover: the seam's takeover validation accepts only an
        ACTIVE row, and this guarded transition (exact bench + sequence,
        active-only, under the store's one-writer discipline) is the
        single write that closes one.
        """
        self._close_lease(bench_id, sequence, now)

    def _close_lease(self, bench_id: str, sequence: int, now: str) -> None:
        """The ONE guarded active→released transition (D13 hygiene fold):
        both a holder release and a commissioned consumption close the
        lease the same way — exact bench + sequence, active-only, the
        close time stamped into ``expires_at`` — so the two public
        methods can never drift apart."""
        cursor = self._conn.execute(
            "UPDATE leases SET state = 'released', expires_at = ? "
            "WHERE bench_id = ? AND sequence = ? AND state = 'active'",
            (now, bench_id, sequence),
        )
        if cursor.rowcount != 1:
            raise LeaseNotActive(f"no active lease {sequence} on bench {bench_id!r}")

    def get_active_lease(self, bench_id: str) -> Lease | None:
        """The bench's active lease at the highest sequence, or None when
        the bench is unheld."""
        row = self._conn.execute(
            "SELECT lease_id, bench_id, sequence, holder, expires_at, state"
            " FROM leases WHERE bench_id = ? AND state = 'active'"
            " ORDER BY sequence DESC LIMIT 1",
            (bench_id,),
        ).fetchone()
        if row is None:
            return None
        return Lease(
            lease_id=row[0], bench_id=row[1], sequence=row[2], holder=row[3],
            expires_at=row[4], state=row[5],
        )

    def list_leases(self, bench_id: str) -> list[Lease]:
        """The bench's whole lease ledger in sequence order, closed rows
        included — leases are history, never deleted."""
        rows = self._conn.execute(
            "SELECT lease_id, bench_id, sequence, holder, expires_at, state"
            " FROM leases WHERE bench_id = ? ORDER BY sequence",
            (bench_id,),
        ).fetchall()
        return [
            Lease(
                lease_id=row[0], bench_id=row[1], sequence=row[2], holder=row[3],
                expires_at=row[4], state=row[5],
            )
            for row in rows
        ]

    # --- events -------------------------------------------------------------------

    def append_event(self, stream_id: str, event: dict[str, Any]) -> int:
        """Append to a stream at MAX(sequence)+1 under BEGIN IMMEDIATE (the
        per-stream sequence authority). The assigned sequence is stamped
        into the stored envelope as a decimal string and returned."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT MAX(sequence) FROM events WHERE stream_id = ?", (stream_id,)
            ).fetchone()
            sequence = int(row[0] or 0) + 1
            envelope = dict(event)
            envelope["sequence"] = str(sequence)
            self._conn.execute(
                "INSERT INTO events (stream_id, sequence, event_json) VALUES (?, ?, ?)",
                (stream_id, sequence, json.dumps(envelope, sort_keys=True)),
            )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return sequence

    def read_events(self, stream_id: str) -> list[dict[str, Any]]:
        """The whole stream in sequence order, envelopes decoded."""
        rows = self._conn.execute(
            "SELECT event_json FROM events WHERE stream_id = ? ORDER BY sequence",
            (stream_id,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def read_events_after(
        self, stream_id: str, after: str | None, limit: int
    ) -> list[dict[str, Any]]:
        """Windowed read for cursor paging: the ``limit`` events after
        sequence ``after`` (whole-stream head when ``after`` is None),
        ordered — no silent reordering, no silent truncation beyond limit."""
        if after is None:
            rows = self._conn.execute(
                "SELECT event_json FROM events WHERE stream_id = ? ORDER BY sequence LIMIT ?",
                (stream_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT event_json FROM events WHERE stream_id = ? AND sequence > ?"
                " ORDER BY sequence LIMIT ?",
                (stream_id, int(after), limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def stream_watermarks(self, stream_id: str) -> tuple[str | None, str | None]:
        """(oldest, current) sequence as decimal strings; (None, None) when
        the stream is empty — retention arithmetic needs both bounds."""
        row = self._conn.execute(
            "SELECT MIN(sequence), MAX(sequence) FROM events WHERE stream_id = ?",
            (stream_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None, None
        return str(row[0]), str(row[1])

    def trim_stream(self, stream_id: str, keep: int) -> int:
        """Delete the oldest events beyond ``keep``; return the deleted
        count. Trimming is the only event deletion, and callers surface it
        as ``cursor_expired`` — never silent truncation."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cursor = self._conn.execute(
                "SELECT sequence FROM events WHERE stream_id = ? ORDER BY sequence DESC"
                " LIMIT 1 OFFSET ?",
                (stream_id, keep - 1),
            ).fetchone()
            if cursor is None:
                self._conn.execute("ROLLBACK")
                return 0
            deleted = self._conn.execute(
                "DELETE FROM events WHERE stream_id = ? AND sequence < ?",
                (stream_id, cursor[0]),
            ).rowcount
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return int(deleted)

    # --- generation authority (WP07) -----------------------------------------

    def current_generation(self, bench_id: str) -> int:
        """The bench's generation (0 before the first bump) — the fence
        value admin changes and run starts compare against."""
        row = self._conn.execute(
            "SELECT generation FROM generations WHERE bench_id = ?", (bench_id,)
        ).fetchone()
        return int(row[0]) if row else 0

    def bump_generation(self, bench_id: str, now: str) -> int:
        """Advance the bench's generation by one under BEGIN IMMEDIATE and
        return the new value (1 on the first bump). Read-then-write inside
        the transaction — the check-then-act callers must still serialise
        through the app's write gate."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT generation FROM generations WHERE bench_id = ?", (bench_id,)
            ).fetchone()
            generation = int(row[0]) + 1 if row else 1
            self._conn.execute(
                "INSERT INTO generations (bench_id, generation, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(bench_id) DO UPDATE SET generation = excluded.generation, "
                "updated_at = excluded.updated_at",
                (bench_id, generation, now),
            )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return generation

    # --- bench inventory (WP07) --------------------------------------------------

    def put_bench(
        self,
        bench_id: str,
        generation: int,
        qualification: str,
        configuration_json: str,
        licence: str,
        now: str,
    ) -> None:
        """Upsert the bench inventory row — whole-row replace keyed on
        ``bench_id``; the caller supplies the generation (the authority is
        ``bump_generation``, not this table)."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO benches (bench_id, generation, qualification, configuration_json,"
                " licence, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(bench_id) DO UPDATE SET generation = excluded.generation,"
                " qualification = excluded.qualification,"
                " configuration_json = excluded.configuration_json,"
                " licence = excluded.licence, updated_at = excluded.updated_at",
                (bench_id, generation, qualification, configuration_json, licence, now),
            )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def get_bench(self, bench_id: str) -> dict[str, Any] | None:
        """The bench inventory row, or None when unknown. JSON columns come
        back raw — the projection layer owns decoding."""
        row = self._conn.execute(
            "SELECT bench_id, generation, qualification, configuration_json, licence, updated_at"
            " FROM benches WHERE bench_id = ?",
            (bench_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "bench_id": row[0],
            "generation": int(row[1]),
            "qualification": row[2],
            "configuration_json": row[3],
            "licence": row[4],
            "updated_at": row[5],
        }

    def list_benches(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], bool]:
        """One page of benches ordered by id: ``(items, has_more)``. The
        ``limit + 1`` overfetch makes ``has_more`` exact without a COUNT;
        callers clamp ``limit`` — SQLite reads a negative LIMIT as
        unlimited."""
        rows = self._conn.execute(
            "SELECT bench_id, generation, qualification, configuration_json, licence, updated_at"
            " FROM benches ORDER BY bench_id LIMIT ? OFFSET ?",
            (limit + 1, offset),
        ).fetchall()
        has_more = len(rows) > limit
        items = [
            {
                "bench_id": row[0],
                "generation": int(row[1]),
                "qualification": row[2],
                "configuration_json": row[3],
                "licence": row[4],
                "updated_at": row[5],
            }
            for row in rows[:limit]
        ]
        return items, has_more

    # --- device inventory (WP07) -----------------------------------------------------

    def put_device(
        self,
        device_id: str,
        bench_id: str,
        generation: int,
        profiles_json: str,
        descriptor_json: str,
        identity_state: str,
        licence: str,
        now: str,
    ) -> None:
        """Upsert the device inventory row — whole-row replace keyed on
        ``device_id`` (a re-put may re-home the device to another bench)."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO devices (device_id, bench_id, generation, profiles_json,"
                " descriptor_json, identity_state, licence, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(device_id) DO UPDATE SET bench_id = excluded.bench_id,"
                " generation = excluded.generation, profiles_json = excluded.profiles_json,"
                " descriptor_json = excluded.descriptor_json,"
                " identity_state = excluded.identity_state, licence = excluded.licence,"
                " updated_at = excluded.updated_at",
                (
                    device_id,
                    bench_id,
                    generation,
                    profiles_json,
                    descriptor_json,
                    identity_state,
                    licence,
                    now,
                ),
            )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """The device inventory row, or None when unknown. JSON columns
        come back raw — the projection layer owns decoding."""
        row = self._conn.execute(
            "SELECT device_id, bench_id, generation, profiles_json, descriptor_json,"
            " identity_state, licence, updated_at FROM devices WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "device_id": row[0],
            "bench_id": row[1],
            "generation": int(row[2]),
            "profiles_json": row[3],
            "descriptor_json": row[4],
            "identity_state": row[5],
            "licence": row[6],
            "updated_at": row[7],
        }

    def list_devices(
        self, bench_id: str, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], bool]:
        """One page of a bench's devices ordered by id: ``(items,
        has_more)`` via the same ``limit + 1`` overfetch as
        ``list_benches``."""
        rows = self._conn.execute(
            "SELECT device_id, bench_id, generation, profiles_json, descriptor_json,"
            " identity_state, licence, updated_at FROM devices WHERE bench_id = ?"
            " ORDER BY device_id LIMIT ? OFFSET ?",
            (bench_id, limit + 1, offset),
        ).fetchall()
        has_more = len(rows) > limit
        items = [
            {
                "device_id": row[0],
                "bench_id": row[1],
                "generation": int(row[2]),
                "profiles_json": row[3],
                "descriptor_json": row[4],
                "identity_state": row[5],
                "licence": row[6],
                "updated_at": row[7],
            }
            for row in rows[:limit]
        ]
        return items, has_more

    # --- run-state projection (WP07) ---------------------------------------------

    def put_run_state(self, run_id: str, bench_id: str, state: str, now: str) -> None:
        """Upsert the run's queue-state projection; every overwrite
        advances ``revision`` by one (first put is revision 1), so readers
        can order updates without timestamps."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO run_states (run_id, bench_id, state, revision, updated_at)"
                " VALUES (?, ?, ?, 1, ?)"
                " ON CONFLICT(run_id) DO UPDATE SET bench_id = excluded.bench_id,"
                " state = excluded.state, revision = revision + 1,"
                " updated_at = excluded.updated_at",
                (run_id, bench_id, state, now),
            )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def get_run_state(self, run_id: str) -> dict[str, Any] | None:
        """The run's queue-state row, or None when never projected."""
        row = self._conn.execute(
            "SELECT run_id, bench_id, state, revision, updated_at FROM run_states"
            " WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row[0],
            "bench_id": row[1],
            "state": row[2],
            "revision": int(row[3]),
            "updated_at": row[4],
        }

    def list_run_states(self, bench_id: str) -> list[dict[str, Any]]:
        """Every queue-state row for one bench, ordered by run id.

        The store has no other per-bench run view, so the seam's §5 busy
        oracle derives bench activity from these rows (D9): a run owns its
        bench from acceptance until its state closes terminal. Read-only.
        """
        rows = self._conn.execute(
            "SELECT run_id, bench_id, state, revision, updated_at FROM run_states"
            " WHERE bench_id = ? ORDER BY run_id",
            (bench_id,),
        ).fetchall()
        return [
            {
                "run_id": row[0],
                "bench_id": row[1],
                "state": row[2],
                "revision": int(row[3]),
                "updated_at": row[4],
            }
            for row in rows
        ]

    # --- admin change records (WP07) ------------------------------------------------

    def put_change(
        self,
        change_id: str,
        bench_id: str,
        kind: str,
        target_ref_json: str,
        expected_generation: int,
        reason: str,
        now: str,
    ) -> None:
        """File a new admin change record in state ``proposed`` with an
        empty reasons list; ``expected_generation`` is the fence the later
        apply compares against."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO changes (change_id, bench_id, kind, target_ref_json,"
                " expected_generation, reason, state, reasons_json, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 'proposed', '[]', ?, ?)",
                (change_id, bench_id, kind, target_ref_json, expected_generation, reason,
                 now, now),
            )
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")

    def get_change(self, change_id: str) -> dict[str, Any] | None:
        """The change record (reasons decoded), or None when unknown."""
        row = self._conn.execute(
            "SELECT change_id, bench_id, kind, target_ref_json, expected_generation, reason,"
            " state, reasons_json, created_at, updated_at FROM changes WHERE change_id = ?",
            (change_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "change_id": row[0],
            "bench_id": row[1],
            "kind": row[2],
            "target_ref_json": row[3],
            "expected_generation": int(row[4]),
            "reason": row[5],
            "state": row[6],
            "reasons": json.loads(row[7]),
            "created_at": row[8],
            "updated_at": row[9],
        }

    def set_change_state(
        self, change_id: str, state: str, reasons: list[str], now: str
    ) -> None:
        """Move a change record to ``state`` and replace its audit
        ``reasons``; ``ValueError`` when the change id is unknown."""
        cursor = self._conn.execute(
            "UPDATE changes SET state = ?, reasons_json = ?, updated_at = ?"
            " WHERE change_id = ?",
            (state, json.dumps(reasons), now, change_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"change {change_id!r} not found")

    # --- fault-injection window (test support) --------------------------------------

    def begin_kill_window(self) -> None:
        """Open BEGIN IMMEDIATE, write a marker run and lease, and return
        with the transaction still OPEN — the sanctioned
        kill-a-process-mid-write window the fault suite aims at: a process
        killed here must leave no trace after recovery. Test support only."""
        self._conn.execute("BEGIN IMMEDIATE")
        self._conn.execute(
            "INSERT INTO runs (run_id, binding_json, principal_id, started_at)"
            " VALUES ('kill-window-run', '{}', 'fault-injector', '1970-01-01T00:00:00Z')"
        )
        self._conn.execute(
            "INSERT INTO leases (bench_id, sequence, lease_id, holder, expires_at, state)"
            " VALUES ('kill-bench', 1, 'kill-lease', 'fault-injector',"
            " '1970-01-01T00:00:00Z', 'active')"
        )

    def commit_kill_window(self) -> None:
        """The committed twin of ``begin_kill_window``: same writes, COMMIT
        issued — the survivor the fault suite's recovery assertions compare
        against."""
        self.begin_kill_window()
        self._conn.execute("COMMIT")
