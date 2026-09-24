"""Issue #194 fault arm: kill a process mid-disposition-transaction.

A1's fault control from the design record's pre-committed acceptance rule:
process death inside the one ``BEGIN IMMEDIATE`` invocation window leaves
NEITHER audit rows NOR deletions after reopen — the all-or-nothing crash
story that makes "auditable before executable" structural. The committed
twin (kill after COMMIT) is the survivor the recovery assertions compare
against, mirroring ``test_state_recovery.py``'s kill-window pair. Fixture
vocabulary is invented.
"""

from __future__ import annotations

import concurrent.futures
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from benchweave.cli.atrest import db_path, setup
from benchweave.content.capture_store import CaptureStagingStore
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
CHILD = ROOT / "tests" / "faults" / "_dispose_child.py"

T0 = "2026-09-20T00:00:00Z"
NOW = "2026-09-27T00:00:00Z"  # seven days later: every rule below is overdue

#: Generous bound for the child's next stdout marker (the healthy child
#: prints within milliseconds; the kill cleanup waits 10s).
MARKER_TIMEOUT = 30.0


def _read_marker_line(process: subprocess.Popen[bytes]) -> str:
    assert process.stdout is not None
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future: concurrent.futures.Future[bytes] = pool.submit(process.stdout.readline)
    try:
        raw = future.result(timeout=MARKER_TIMEOUT)
    except TimeoutError:
        pytest.fail(f"child emitted no marker within {MARKER_TIMEOUT}s")
    finally:
        # wait=False: a reader still stuck on the pipe is unblocked by the
        # caller's kill() (EOF), never joined here.
        pool.shutdown(wait=False)
    return raw.decode().strip()


def _await_marker(process: subprocess.Popen[bytes], marker: str) -> None:
    line = _read_marker_line(process)
    assert line == marker, f"waiting for {marker}, got: {line}"


def _seed(tmp_path: Path, captures: int = 4) -> Path:
    """A data dir with N finalised overdue delete-tier captures under one
    context key and the matching policy — the smallest store whose
    disposition transaction has a mid-transaction kill window."""
    import shutil

    data_dir = tmp_path / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    setup(data_dir)
    data_dir.joinpath("retention-policy.json").write_text(
        json.dumps({
            "config_version": "1",
            "default": {"duration_s": 3600, "retain_after": "landing",
                        "on_disposition": "review"},
            "classes": [
                {"selector": "capture:waveform_f64le", "duration_s": 3600,
                 "retain_after": "landing", "on_disposition": "delete"},
            ],
            "benches": {},
        }),
        encoding="utf-8",
    )
    store = Store.open(db_path(data_dir))
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=10_000_000)
        for i in range(captures):
            cid = f"fault-cap-{i}"
            writer.open_capture(capture_id=cid, context_key="run:fault-run",
                                fmt="waveform_f64le", sample_count=None,
                                max_bytes=1000, now=T0)
            writer.append(cid, bytes([i + 1]) * 32, "run:fault-run")
            writer.finalise(cid, T0, "run:fault-run")
    finally:
        store.close()
    return data_dir


def _counts(data_dir: Path) -> tuple[int, int, int]:
    uri = f"{db_path(data_dir).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        audit = int(conn.execute("SELECT COUNT(*) FROM dispositions").fetchone()[0])
        invocations = int(
            conn.execute("SELECT COUNT(*) FROM disposition_invocations").fetchone()[0]
        )
        remaining = int(
            conn.execute(
                "SELECT COUNT(*) FROM capture_staging"
                " WHERE capture_id LIKE 'fault-cap-%'").fetchone()[0]
        )
        return audit, invocations, remaining
    finally:
        conn.close()


def _spawn(data_dir: Path, mode: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, str(CHILD), mode, str(data_dir)],
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
    )


def test_kill_mid_disposition_leaves_neither_audit_nor_deletion(
    tmp_path: Path,
) -> None:
    """The A1 fault arm: SIGKILL with the invocation transaction open (one
    row fully processed, uncommitted) leaves ZERO audit rows, ZERO
    invocation rows and every governed row in place — the crash disposed
    nothing, and a re-run re-plans cleanly over the unchanged store."""
    data_dir = _seed(tmp_path)
    child = _spawn(data_dir, "hold")
    try:
        _await_marker(child, "READY")
    finally:
        child.kill()
        child.wait(timeout=10)

    audit, invocations, remaining = _counts(data_dir)
    assert audit == 0, "an uncommitted audit row survived the kill"
    assert invocations == 0, "an uncommitted invocation row survived the kill"
    assert remaining == 4, "an uncommitted deletion leaked through the kill"
    store = Store.open(db_path(data_dir))  # the db is still usable after the kill
    try:
        writer = CaptureStagingStore(store, max_capture_bytes=10_000_000,
                                     max_dataset_bytes=10_000_000)
        assert writer.used_bytes("run:fault-run") == 4 * 32, (
            "the ledger must be untouched by the killed invocation"
        )
    finally:
        store.close()

    # The re-run re-plans cleanly and disposes everything in one commit.
    from benchweave.cli.dispose import dispose_from_data_dir

    model = dispose_from_data_dir(data_dir, now=NOW, execute=True)
    assert model["counts"]["deleted"] == 4
    audit, invocations, remaining = _counts(data_dir)
    assert (audit, invocations, remaining) == (4, 1, 0)


def test_kill_after_disposition_commit_survives(tmp_path: Path) -> None:
    """The committed twin: after COMMIT, a SIGKILL loses nothing — the
    audit trail and the deletions are both durable."""
    data_dir = _seed(tmp_path)
    child = _spawn(data_dir, "commit")
    try:
        _await_marker(child, "COMMITTED")
    finally:
        child.kill()
        child.wait(timeout=10)
    audit, invocations, remaining = _counts(data_dir)
    assert (audit, invocations, remaining) == (4, 1, 0), (
        "committed dispositions must survive SIGKILL"
    )
