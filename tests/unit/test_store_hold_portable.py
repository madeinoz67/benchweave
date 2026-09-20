"""The store hold's contract holds on every development platform.

The fault suites prove cross-process release-on-death with real child
processes; this file pins the platform-portable surface (acquire, refuse,
release, probe) that Windows development checkouts rely on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from benchweave.state.hold import (
    StoreHeldError,
    StoreHold,
    daemon_holds,
    hold_path,
    holder_info,
)


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


def test_symlink_spelling_shares_one_marker(tmp_path: Path) -> None:
    """Two spellings of one data dir (a symlink alias and its real path)
    derive the SAME marker — the split-brain review reproduced at the
    pre-fix head, where both spellings held simultaneously (PR #35 HIGH).
    """

    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    via_real = real / "state.sqlite"
    via_alias = alias / "state.sqlite"
    from benchweave.state.hold import hold_path

    assert hold_path(via_real) == hold_path(via_alias)
    with StoreHold(via_real, label="gateway serve"):
        with pytest.raises(StoreHeldError, match="gateway serve"):
            StoreHold(via_alias, label="backup").acquire()
        assert daemon_holds(via_alias)


def test_hold_marker_is_the_resolved_dirs_sibling(tmp_path: Path) -> None:
    """Shape pin: the marker is named ``<resolved-dir>.hold`` BESIDE the
    resolved data directory — never inside it (the Windows rename rule)."""

    db = tmp_path / "data" / "state.sqlite"
    marker = hold_path(db)
    data_dir = db.parent.resolve()
    assert marker == data_dir.parent / (data_dir.name + ".hold")
    assert marker.parent == data_dir.parent

