"""B-R2's store leg (issue #176 row B): the guarded busy-timeout window.

``Store.busy_timeout_window`` is the pragma surface Decision 2 adds: set
on entry, restore on EVERY exit path (try/finally), so a capture dispatch
that raises between set and restore cannot leak the temporary value. The
commissioned default (``Store.open(busy_timeout_ms=...)``) is the value
the window restores to when no window is already open, and the value the
clamp and the epilogue floor read — one commissioning knob, one story
(F12/A02: a stock default named as such, commissionable per bench).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from benchweave.state.store import DEFAULT_BUSY_TIMEOUT_MS, Store


def test_store_open_commissions_the_stock_default_by_name(tmp_path: Path) -> None:
    """The open-time default is the stock sqlite3 default, named and
    commissionable; the pragma and the store's property agree."""
    store = Store.open(tmp_path / "default.db")
    try:
        assert DEFAULT_BUSY_TIMEOUT_MS == 5000  # the stock value, named
        assert store.open_busy_timeout_ms == DEFAULT_BUSY_TIMEOUT_MS
        live = int(
            store.connection.execute("PRAGMA busy_timeout").fetchone()[0]
        )
        assert live == DEFAULT_BUSY_TIMEOUT_MS
    finally:
        store.close()


def test_store_open_commissions_a_per_bench_value(tmp_path: Path) -> None:
    """A02's commissioning path: a different open-time value moves the
    pragma, the property, and therefore both row-B faces (the clamp's
    default cap and the epilogue floor's cap) with it."""
    store = Store.open(tmp_path / "commissioned.db", busy_timeout_ms=300)
    try:
        assert store.open_busy_timeout_ms == 300
        live = int(
            store.connection.execute("PRAGMA busy_timeout").fetchone()[0]
        )
        assert live == 300
    finally:
        store.close()


def test_store_open_refuses_a_negative_commissioning(tmp_path: Path) -> None:
    """A negative busy_timeout_ms is refused loudly at open, before any
    migration runs — a silent pragma no-op would misstate every row-B
    bound that reads the property."""
    with pytest.raises(ValueError, match="busy_timeout_ms"):
        Store.open(tmp_path / "negative.db", busy_timeout_ms=-1)


def test_store_open_refuses_above_the_sqlite_c_int_bound(tmp_path: Path) -> None:
    """Above 2^31−1 SQLite silently converts the pragma to 0 — the busy
    handler DISABLED while ``open_busy_timeout_ms`` would keep reporting
    the commissioned number. The open-time guard refuses that lie
    (lane-1 F2, final fold): the property and the pragma can never
    disagree at open."""
    with pytest.raises(ValueError, match="2 147 483 647|2147483647|C-int"):
        Store.open(tmp_path / "too-big.db", busy_timeout_ms=2**31)
    # The bound itself commissions cleanly, and the readback agrees.
    store = Store.open(tmp_path / "max.db", busy_timeout_ms=2**31 - 1)
    try:
        live = int(store.connection.execute("PRAGMA busy_timeout").fetchone()[0])
        assert live == store.open_busy_timeout_ms == 2**31 - 1
    finally:
        store.close()


def test_window_sets_and_restores_the_open_default(tmp_path: Path) -> None:
    """Entry sets the window value; exit restores the open default."""
    store = Store.open(tmp_path / "window.db", busy_timeout_ms=300)
    try:
        with store.busy_timeout_window(1500):
            live = int(
                store.connection.execute("PRAGMA busy_timeout").fetchone()[0]
            )
            assert live == 1500
        live = int(
            store.connection.execute("PRAGMA busy_timeout").fetchone()[0]
        )
        assert live == 300  # the commissioned default, restored
    finally:
        store.close()


def test_window_restore_survives_an_exception_between_set_and_restore(
    tmp_path: Path,
) -> None:
    """B-R2's leak discipline: a raise inside the window body still
    restores the value in force at entry — the temporary value cannot
    leak past the window."""
    store = Store.open(tmp_path / "raise.db", busy_timeout_ms=300)
    try:
        with (
            pytest.raises(RuntimeError, match="dispatch raised"),
            store.busy_timeout_window(1500),
        ):
            raise RuntimeError("dispatch raised")
        live = int(
            store.connection.execute("PRAGMA busy_timeout").fetchone()[0]
        )
        assert live == 300
    finally:
        store.close()


def test_window_nesting_restores_the_inner_previous_value(tmp_path: Path) -> None:
    """The clamp and the epilogue floor nest inside one dispatch: the
    inner window's exit restores the OUTER window's value (the value in
    force at inner entry), and the outer exit restores the default."""
    store = Store.open(tmp_path / "nested.db", busy_timeout_ms=300)
    try:
        with store.busy_timeout_window(200):
            with store.busy_timeout_window(150):
                live = int(
                    store.connection.execute("PRAGMA busy_timeout").fetchone()[0]
                )
                assert live == 150
            live = int(
                store.connection.execute("PRAGMA busy_timeout").fetchone()[0]
            )
            assert live == 200  # the outer window's value, not the default
        live = int(
            store.connection.execute("PRAGMA busy_timeout").fetchone()[0]
        )
        assert live == 300
    finally:
        store.close()


def test_window_set_matches_sqlite_observability(tmp_path: Path) -> None:
    """The window's value is the pragma SQLite itself enforces: a BEGIN
    against a held write lock fails after ~the window, not instantly —
    observed here as a failed BEGIN on a second connection while the
    window value is small and the lock stays held past it."""
    store = Store.open(tmp_path / "enforce.db", busy_timeout_ms=5000)
    contender: sqlite3.Connection | None = None
    try:
        contender = sqlite3.connect(str(tmp_path / "enforce.db"), timeout=5.0)
        contender.execute("BEGIN IMMEDIATE")
        with (
            store.busy_timeout_window(50),
            pytest.raises(sqlite3.OperationalError, match="locked"),
        ):
            store.connection.execute("BEGIN IMMEDIATE")
        # Outside the window the default is back: the same BEGIN now
        # waits the full 5 s — bounded by releasing here instead.
    finally:
        if contender is not None:
            contender.rollback()
            contender.close()
        store.close()
