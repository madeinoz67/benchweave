"""The store hold's contract holds on every development platform.

The fault suites prove cross-process release-on-death with real child
processes; this file pins the platform-portable surface (acquire, refuse,
release, probe) that Windows development checkouts rely on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from benchweave.state.hold import StoreHeldError, StoreHold, daemon_holds, holder_info


def test_second_holder_is_refused_and_named(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    with StoreHold(db, label="gateway serve"):
        assert daemon_holds(db)
        with pytest.raises(StoreHeldError, match="gateway serve"):
            StoreHold(db, label="backup").acquire()
    assert not daemon_holds(db)


def test_release_permits_reacquisition(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    first = StoreHold(db, label="one")
    first.acquire()
    first.release()
    second = StoreHold(db, label="two")
    second.acquire()
    info = holder_info(db)
    assert info is not None and info["label"] == "two"
    second.release()


def test_stale_marker_reads_free(tmp_path: Path) -> None:
    # A leftover body under a free lock is ignored by design: the lock state,
    # never the file content, decides held/free.
    db = tmp_path / "state.db"
    hold = StoreHold(db, label="crashed")
    hold.acquire()
    hold.release()
    assert holder_info(db) is not None  # stale metadata remains on disk
    assert not daemon_holds(db)  # but the store reads free
