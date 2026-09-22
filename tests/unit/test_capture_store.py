"""The staged-append capture writer over the v5 staging tables.

Derivations (from primary sources, not the plan's restatement):

- The G3 allowance formula is the design record's Decision 3 verbatim:
  refuse iff ``max_bytes > min(max_capture_bytes, max_dataset_bytes − used)``
  — ``used`` (Σ reserved over staged + Σ charged over finalised for the
  context key) appears ONLY in the dataset term (Amendment A1: the
  alternative double-applies it to the capture term).
- The count-times-eight rule is spec §7 line 154 ("Byte length equals
  sample_count×8"), enforced at finalise against the row's declared
  sample_count; zero-byte publication is refused for BOTH formats (spec §7
  line 156: "Failed/incomplete captures are aborted, not published as
  complete").
- The state vocabulary is code-enforced (no CHECK constraint, Amendment
  B7): the lifecycle arms visit exactly staged/finalised/aborted, and a
  raw-SQL fixture can insert any state.
- The sweep is TWO transactions (Amendment A3/B15-iv): the mark alone
  refunds the ledger (``used`` excludes aborted rows) and the delete is
  idempotent.
- Every writer-raised exception is writer-stamped (Amendment C3): the
  bridge's non-poisoning classification catches require the stamp.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# Module-object access (the new-module RED convention): the test module
# must COLLECT against the parent commit's stub, so every new name is
# resolved at call time rather than import time.
from benchweave.content import capture_store as capture_module
from benchweave.host import types as gateway_types
from benchweave.state.store import Store

NOW = "2026-09-22T00:00:00Z"
LATER = "2026-09-22T00:01:00Z"


def a_writer(store: Store) -> capture_module.CaptureStagingStore:
    return capture_module.CaptureStagingStore(
        store, max_capture_bytes=100, max_dataset_bytes=200
    )


def open_capture(
    writer: capture_module.CaptureStagingStore,
    capture_id: str = "cap-1",
    *,
    context_key: str = "session-a",
    fmt: str = "waveform_f64le",
    sample_count: int | None = 2,
    max_bytes: int = 16,
    now: str = NOW,
) -> None:
    writer.open_capture(
        capture_id=capture_id,
        context_key=context_key,
        fmt=fmt,
        sample_count=sample_count,
        max_bytes=max_bytes,
        now=now,
    )


def row(store: Store, capture_id: str) -> dict[str, Any] | None:
    found = store.connection.execute(
        "SELECT capture_id, context_key, state, reserved_bytes, charged_bytes,"
        " format, sample_count, artifact_id, started_at FROM capture_staging"
        " WHERE capture_id = ?",
        (capture_id,),
    ).fetchone()
    if found is None:
        return None
    return {
        "capture_id": found[0],
        "context_key": found[1],
        "state": found[2],
        "reserved_bytes": found[3],
        "charged_bytes": found[4],
        "format": found[5],
        "sample_count": found[6],
        "artifact_id": found[7],
        "started_at": found[8],
    }


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = Store.open(tmp_path / "capture.db")
    yield opened
    opened.close()


# --- open: the G3 allowance formula (A1's boundary matrix) ----------------------


def test_open_admits_up_to_genuine_headroom_past_the_crossover(store: Store) -> None:
    """Two-ceiling crossover, DERIVED (derivation rule 1 — the plan's
    example numbers do not cross over): the dataset term binds only when
    ``used > Md − Mc``; with Mc=100 and Md=200 that is used>100. At
    used=150 (charged by a finalised capture, so it stays 150) the
    allowance is min(100, 200−150) = 50 — 51 refuses and 50 ADMITS (the
    rejected alternative min(Mc−u, Md−u) = min(−50, 50) refuses everything,
    including the genuine 50-byte headroom)."""
    writer = a_writer(store)
    open_capture(
        writer, "cap-held", fmt="raw_binary", sample_count=None, max_bytes=100
    )
    writer.append("cap-held", b"\x01" * 100, "session-a")
    writer.finalise("cap-held", LATER)  # charged 100
    open_capture(
        writer, "cap-held-2", fmt="raw_binary", sample_count=None, max_bytes=50
    )
    writer.append("cap-held-2", b"\x02" * 50, "session-a")
    writer.finalise("cap-held-2", LATER)  # charged 50: used = 150
    assert writer.used_bytes("session-a") == 150
    with pytest.raises(gateway_types.CaptureQuotaExceeded, match="allowance"):
        open_capture(writer, "cap-over-headroom", max_bytes=51)
    open_capture(
        writer, "cap-at-headroom", fmt="raw_binary", sample_count=None, max_bytes=50
    )


def test_open_is_capped_by_mc_never_by_mc_minus_used(store: Store) -> None:
    """The Mc-binding case, DERIVED: with Mc=50 and Md=500, used=30 leaves
    the dataset term at 470, so the allowance is min(50, 470) = 50 — 51
    refuses and 50 ADMITS. A single capture is capped by Mc, never by
    Mc − used (``used`` appears only in the dataset term; the rejected
    alternative min(Mc−u, Md−u) = min(20, 470) would wrongly refuse 50)."""
    writer = capture_module.CaptureStagingStore(store, max_capture_bytes=50, max_dataset_bytes=500)
    open_capture(writer, "cap-held", max_bytes=30)  # used = 30
    open_capture(writer, "cap-at-mc", max_bytes=50)  # Mc still admits 50
    with pytest.raises(gateway_types.CaptureQuotaExceeded, match="allowance"):
        open_capture(writer, "cap-over-mc", max_bytes=51)


def test_open_refuses_a_context_already_over_the_dataset_ceiling(
    store: Store,
) -> None:
    writer = a_writer(store)
    # Two captures at Mc=100 each: used=200 == Md (Mc admits no single 200).
    open_capture(
        writer, "cap-a", fmt="raw_binary", sample_count=None, max_bytes=100
    )
    open_capture(
        writer, "cap-b", fmt="raw_binary", sample_count=None, max_bytes=100
    )
    # used=200 == Md: the dataset term is 0, so any positive request refuses.
    with pytest.raises(gateway_types.CaptureQuotaExceeded, match="allowance"):
        open_capture(writer, "cap-next", max_bytes=1)


def test_open_without_a_configured_quota_envelope_refuses(store: Store) -> None:
    sweep_writer = capture_module.CaptureStagingStore(store)  # the sweep's construction shape
    with pytest.raises(RuntimeError, match="quota envelope"):
        open_capture(sweep_writer)


def test_open_stamps_the_row_and_starts_the_digest(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", fmt="raw_binary", sample_count=None, max_bytes=99)
    stored = row(store, "cap-1")
    assert stored is not None
    assert stored["state"] == "staged"
    assert stored["reserved_bytes"] == 99
    assert stored["charged_bytes"] == 0
    assert stored["format"] == "raw_binary"
    assert stored["sample_count"] is None
    assert stored["artifact_id"] is None  # set inside the finalise transaction
    assert stored["started_at"] == NOW  # stamped at open (B5)
    assert "cap-1" in writer._hashers


def test_open_refuses_a_duplicate_id_and_keeps_the_original(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=16)
    with pytest.raises(gateway_types.CaptureFinaliseRejected, match="already exists"):
        open_capture(writer, "cap-1", max_bytes=8)
    assert row(store, "cap-1")["reserved_bytes"] == 16  # type: ignore[index]


# --- append: reservation, session keying, hasher -------------------------------


def test_append_enforces_the_reservation_mid_flight(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=16)
    writer.append("cap-1", b"\x00" * 10, "session-a")
    with pytest.raises(gateway_types.CaptureQuotaExceeded, match="reservation"):
        writer.append("cap-1", b"\x00" * 7, "session-a")  # 10 + 7 > 16
    assert writer.staged_bytes("cap-1") == 10  # the refused append stored nothing


def test_append_refuses_empty_data(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=16)
    with pytest.raises(gateway_types.CaptureFinaliseRejected, match="empty append"):
        writer.append("cap-1", b"", "session-a")
    assert writer.staged_bytes("cap-1") == 0


@pytest.mark.parametrize(
    ("case", "capture_id", "context_key"),
    [
        ("unknown id", "cap-unknown", "session-a"),
        ("wrong session", "cap-1", "session-b"),
    ],
)
def test_append_refuses_foreign_keys(
    store: Store, case: str, capture_id: str, context_key: str
) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=16)
    writer.append("cap-1", b"\x00" * 8, "session-a")
    with pytest.raises(gateway_types.CaptureFinaliseRejected, match=case.split()[0]):
        writer.append(capture_id, b"\x00" * 8, context_key)


def test_append_assigns_ordered_seqs_under_begin_immediate(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=64)
    for index in range(3):
        writer.append("cap-1", bytes([index]) * 8, "session-a")
    seqs = store.connection.execute(
        "SELECT seq, byte_length FROM capture_chunks WHERE capture_id = ?"
        " ORDER BY seq",
        ("cap-1",),
    ).fetchall()
    assert [(s, length) for s, length in seqs] == [(0, 8), (1, 8), (2, 8)]


# --- finalise: one transaction, host-computed integrity, G4 byte validation ----


def test_finalise_publishes_and_flips_in_one_transaction(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=16)
    payload = b"\x01" * 8 + b"\x02" * 8
    writer.append("cap-1", payload[:8], "session-a")
    writer.append("cap-1", payload[8:], "session-a")
    record = writer.finalise("cap-1", LATER)
    digest = hashlib.sha256(payload).hexdigest()
    assert record == {
        "artifact_id": "art-" + digest,
        "sha256": digest,
        "byte_length": 16,
    }
    stored = row(store, "cap-1")
    assert stored is not None
    assert stored["state"] == "finalised"
    assert stored["charged_bytes"] == 16  # reservation released, actual charged
    assert stored["reserved_bytes"] == 16  # the reservation column is history
    assert stored["artifact_id"] == "art-" + digest  # B5 read-back
    chunks = store.connection.execute(
        "SELECT COUNT(*) FROM capture_chunks WHERE capture_id = ?", ("cap-1",)
    ).fetchone()[0]
    assert chunks == 0
    # The artifact row is content-addressed and readable through the store.
    served = store.connection.execute(
        "SELECT data FROM artifacts WHERE artifact_id = ?", ("art-" + digest,)
    ).fetchone()
    assert served is not None and bytes(served[0]) == payload
    assert writer.finalise_record("cap-1") == {
        "artifact_id": "art-" + digest,
        "sha256": digest,
        "byte_length": 16,
        "format": "waveform_f64le",
        "sample_count": 2,
    }


def test_finalise_cross_checks_the_running_digest_against_stored_bytes(
    store: Store,
) -> None:
    """Store corruption between append and finalise is refused: the running
    in-memory digest and a streaming recompute over the stored chunk rows
    must agree, or nothing is published."""
    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=16)
    writer.append("cap-1", b"\x01" * 16, "session-a")
    store.connection.execute(
        "UPDATE capture_chunks SET data = ? WHERE capture_id = ?",
        (b"\xff" * 16, "cap-1"),
    )
    with pytest.raises(gateway_types.CaptureFinaliseRejected, match="digest"):
        writer.finalise("cap-1", LATER)
    assert row(store, "cap-1")["state"] == "staged"  # type: ignore[index]
    published = store.connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    assert published == 0


@pytest.mark.parametrize("fmt", ["waveform_f64le", "raw_binary"])
def test_zero_byte_finalise_is_refused_for_both_formats(
    store: Store, fmt: str
) -> None:
    """Spec §7 line 156: failed/incomplete captures are aborted, not
    published as complete — an empty acquisition window routes through
    abort, never through publication."""
    writer = a_writer(store)
    open_capture(writer, "cap-empty", fmt=fmt, sample_count=None, max_bytes=16)
    with pytest.raises(gateway_types.CaptureFinaliseRejected, match="zero"):
        writer.finalise("cap-empty", LATER)
    assert row(store, "cap-empty") is not None  # still staged: abort owns it


def test_a_short_capture_is_refused_at_finalise(store: Store) -> None:
    """Spec §7 line 154 (byte length equals sample_count×8): a declared
    sample_count of 2 demands 16 bytes; 8 delivered is a short capture and
    is refused, never published."""
    writer = a_writer(store)
    open_capture(writer, "cap-short", max_bytes=32, sample_count=2)
    writer.append("cap-short", b"\x01" * 8, "session-a")
    with pytest.raises(gateway_types.CaptureFinaliseRejected, match="short capture"):
        writer.finalise("cap-short", LATER)
    published = store.connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    assert published == 0


def test_finalise_refuses_unknown_and_post_terminal_ids(store: Store) -> None:
    writer = a_writer(store)
    with pytest.raises(gateway_types.CaptureFinaliseRejected, match="unknown"):
        writer.finalise("cap-unknown", LATER)
    open_capture(writer, "cap-1", max_bytes=16)
    writer.append("cap-1", b"\x01" * 16, "session-a")
    writer.finalise("cap-1", LATER)
    with pytest.raises(gateway_types.CaptureFinaliseRejected, match="terminal"):
        writer.append("cap-1", b"\x00", "session-a")
    with pytest.raises(gateway_types.CaptureFinaliseRejected, match="terminal"):
        writer.finalise("cap-1", LATER)


# --- abort: the single-transaction delete (§0.4) -------------------------------


def test_abort_deletes_chunks_and_entry_in_one_transaction(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=16)
    writer.append("cap-1", b"\x01" * 8, "session-a")
    assert writer.abort("cap-1") is True
    assert row(store, "cap-1") is None
    chunks = store.connection.execute(
        "SELECT COUNT(*) FROM capture_chunks WHERE capture_id = ?", ("cap-1",)
    ).fetchone()[0]
    assert chunks == 0
    published = store.connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    assert published == 0


def test_abort_is_a_noop_retract_after_finalise_and_for_unknown_ids(
    store: Store,
) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=16)
    writer.append("cap-1", b"\x01" * 16, "session-a")
    writer.finalise("cap-1", LATER)
    assert writer.abort("cap-1") is False  # a published capture stands
    assert row(store, "cap-1") is not None
    assert writer.abort("cap-never") is False


# --- the hasher lifecycle (B3) ---------------------------------------------------


def test_reuse_after_abort_starts_a_fresh_digest(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-1", fmt="raw_binary", sample_count=None, max_bytes=32)
    writer.append("cap-1", b"first", "session-a")
    writer.abort("cap-1")
    open_capture(writer, "cap-1", fmt="raw_binary", sample_count=None, max_bytes=32)
    writer.append("cap-1", b"second", "session-a")
    record = writer.finalise("cap-1", LATER)
    assert record["sha256"] == hashlib.sha256(b"second").hexdigest()
    assert record["byte_length"] == 6


def test_hasher_entries_track_open_captures(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-a", fmt="raw_binary", sample_count=None, max_bytes=16)
    open_capture(writer, "cap-b", fmt="raw_binary", sample_count=None, max_bytes=16)
    assert len(writer._hashers) == 2
    writer.append("cap-a", b"a" * 4, "session-a")
    writer.finalise("cap-a", LATER)  # finalise removes its entry
    assert len(writer._hashers) == 1
    writer.abort("cap-b")  # abort removes its entry
    assert len(writer._hashers) == 0


# --- the ledger and the sweep (A3, B15-iv) ----------------------------------------


def test_used_bytes_counts_reserved_then_charged_and_refunds_on_abort(
    store: Store,
) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-staged", max_bytes=40)
    open_capture(writer, "cap-final", max_bytes=60, sample_count=None, fmt="raw_binary")
    writer.append("cap-final", b"\x01" * 10, "session-a")
    writer.finalise("cap-final", LATER)
    assert writer.used_bytes("session-a") == 40 + 10  # reserved + charged
    writer.abort("cap-staged")
    assert writer.used_bytes("session-a") == 10


def test_reclaim_orphans_marks_then_deletes_and_is_idempotent(store: Store) -> None:
    writer = a_writer(store)
    open_capture(writer, "cap-a", max_bytes=16, context_key="session-a")
    open_capture(writer, "cap-b", max_bytes=16, context_key="session-b")
    open_capture(writer, "cap-c", max_bytes=16, context_key="session-a")
    writer.append("cap-c", b"\x01" * 16, "session-a")
    writer.finalise("cap-c", LATER)
    reclaimed = writer.reclaim_orphans(LATER)
    assert sorted(reclaimed) == ["cap-a", "cap-b"]
    assert row(store, "cap-a") is None
    assert row(store, "cap-b") is None
    kept = row(store, "cap-c")
    assert kept is not None and kept["state"] == "finalised"  # the ledger row stands
    assert writer.used_bytes("session-a") == 16  # cap-c's charged bytes only
    assert writer.reclaim_orphans(LATER) == []  # idempotent


def test_the_mark_transaction_alone_refunds_the_quota(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B15-iv's never-collapse machine check: a crash between the sweep's
    two transactions leaves rows marked aborted (they persist) and the
    ledger already refunded — ``used`` excludes aborted rows — and a second
    sweep completes the delete."""
    writer = a_writer(store)
    open_capture(writer, "cap-a", max_bytes=40, context_key="session-a")

    def exploding_delete() -> None:
        raise RuntimeError("simulated crash between the sweep's transactions")

    monkeypatch.setattr(writer, "_delete_aborted_rows", exploding_delete)
    with pytest.raises(RuntimeError, match="simulated crash"):
        writer.reclaim_orphans(LATER)
    marked = row(store, "cap-a")
    assert marked is not None and marked["state"] == "aborted"  # rows persist
    assert writer.used_bytes("session-a") == 0  # refunded by the mark alone
    monkeypatch.undo()
    assert writer.reclaim_orphans(LATER) == []  # completes the delete
    assert row(store, "cap-a") is None


# --- B7's vocabulary pin and C3's stamp -------------------------------------------


def test_the_state_vocabulary_is_code_enforced_and_raw_sql_is_unconstrained(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No CHECK constraint exists (B7): the lifecycle arms visit exactly
    staged/finalised/aborted (a normal abort DELETES its row — 'aborted'
    persists only in the sweep's crash window) and a raw-SQL fixture can
    insert any state (the sweep's WHERE clauses are state-equality filters,
    so an exotic row is invisible to them)."""
    writer = a_writer(store)
    open_capture(writer, "cap-final", fmt="raw_binary", sample_count=None, max_bytes=16)
    writer.append("cap-final", b"\x00" * 16, "session-a")
    writer.finalise("cap-final", LATER)
    open_capture(writer, "cap-crash", fmt="raw_binary", sample_count=None, max_bytes=16)
    # A normal abort DELETES its row, so 'aborted' is observable only in the
    # sweep's crash window: mark-only (delete patched out) — which also
    # sweeps cap-crash, so the 'staged' witness must be opened AFTER.
    monkeypatch.setattr(writer, "_delete_aborted_rows", lambda: None)
    writer.reclaim_orphans(LATER)  # mark-only: the crash window persists 'aborted'
    monkeypatch.undo()
    # NOT completing the reclamation here: 'aborted' must be observable.
    open_capture(writer, "cap-staged", fmt="raw_binary", sample_count=None, max_bytes=16)
    states = {
        str(found[0])
        for found in store.connection.execute(
            "SELECT state FROM capture_staging"
        ).fetchall()
    }
    assert states == {"staged", "finalised", "aborted"}
    store.connection.execute(
        "INSERT INTO capture_staging (capture_id, context_key, state,"
        " reserved_bytes, charged_bytes, created_at, updated_at)"
        " VALUES ('cap-weird', 'session-a', 'weird', 0, 0, ?, ?)",
        (NOW, NOW),
    )  # no CHECK refuses this — the B7 trade, pinned


def test_writer_exceptions_are_stamped_and_a_bare_raise_is_not(store: Store) -> None:
    """C3 as amended (F4): the stamp carries the writer module's token
    bound to the capture; writer_originated is the discriminator (identity
    + binding), and a bare raise — or the same exception bound to ANOTHER
    capture — does not classify."""
    from benchweave.content.capture_store import writer_originated

    writer = a_writer(store)
    open_capture(writer, "cap-1", max_bytes=16)
    with pytest.raises(gateway_types.CaptureQuotaExceeded) as quota:
        writer.append("cap-1", b"\x00" * 17, "session-a")
    assert writer_originated(quota.value, "cap-1")
    assert not writer_originated(quota.value, "cap-other")  # binding, not just presence
    with pytest.raises(gateway_types.CaptureFinaliseRejected) as rejected:
        writer.finalise("cap-unknown", LATER)
    assert rejected.value.capture_stamp is not None
    bare = gateway_types.CaptureQuotaExceeded("adapter code can raise the class too")
    assert bare.capture_stamp is None
    assert not writer_originated(bare, "cap-1")  # the discriminator refuses it


# --- F7: the stamp frame covers the COMMIT sites -------------------------------


class _CommitFailingConn:
    """A delegating connection proxy whose Nth COMMIT fails with the real
    condition class (the refuter could not reach COMMIT-busy on WAL —
    the reachable shapes are SQLITE_FULL/IO at exactly the COMMIT of a
    mid-capture write — so the arm injects at the real call site)."""

    def __init__(self, inner: Any, fail_on: int) -> None:
        self._inner = inner
        self._commits = 0
        self._fail_on = fail_on

    def execute(self, sql: str, *args: Any) -> Any:
        if sql.strip().upper().startswith("COMMIT"):
            self._commits += 1
            if self._commits == self._fail_on:
                raise sqlite3.OperationalError("disk I/O error (injected)")
        return self._inner.execute(sql, *args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def test_commit_site_failures_are_stamped(store: Store) -> None:
    """F7: 'every exception this writer raises is writer-stamped' must
    include the COMMIT sites — an OperationalError from COMMIT itself is a
    store-resource condition the bridge classifies non-poison, not a
    protocol lie."""
    from benchweave.content.capture_store import writer_originated

    writer = a_writer(store)
    original = writer._conn
    writer._conn = _CommitFailingConn(original, fail_on=1)  # type: ignore[assignment]
    try:
        with pytest.raises(sqlite3.OperationalError, match="injected"):
            open_capture(writer, "cap-1", fmt="raw_binary", sample_count=None, max_bytes=16)
    finally:
        writer._conn = original
    # The staged row the failed COMMIT left behind is rolled back.
    assert row(store, "cap-1") is None
    # RED on the unfixed tree: the COMMIT failure escapes unstamped.
    # Re-raise through the proxy once more to inspect the stamp directly.
    writer._conn = _CommitFailingConn(original, fail_on=2)  # type: ignore[assignment]
    try:
        open_capture(  # commit 1 succeeds under the proxy
            writer, "cap-2", fmt="raw_binary", sample_count=None, max_bytes=16
        )
        with pytest.raises(sqlite3.OperationalError, match="injected") as caught:
            writer.append("cap-2", b"\x01" * 8, "session-a")  # commit 2 fails
    finally:
        writer._conn = original
    assert writer_originated(caught.value, "cap-2")
