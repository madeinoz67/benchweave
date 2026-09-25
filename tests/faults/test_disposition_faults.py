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
import hashlib
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


def _spawn(
    data_dir: Path, mode: str, target: Path | None = None
) -> subprocess.Popen[bytes]:
    argv = [sys.executable, str(CHILD), mode, str(data_dir)]
    if target is not None:
        argv.append(str(target))
    return subprocess.Popen(
        argv,
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


# --- issue #199: the archive tier's three crash windows (AR5) ------------------------


def _seed_archive(tmp_path: Path, rows: int = 3) -> Path:
    """A data dir with N overdue ARCHIVE-tier evidence rows under one
    context key and the matching policy — the smallest store whose
    archival invocation has a Phase-A staging window and a Phase-B
    transaction window."""
    import shutil

    from benchweave.content.store import ContentStore

    data_dir = tmp_path / "data-arch"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    setup(data_dir)
    data_dir.joinpath("retention-policy.json").write_text(
        json.dumps({
            "config_version": "1",
            "default": {"duration_s": 3600, "retain_after": "landing",
                        "on_disposition": "review"},
            "classes": [
                {"selector": "evidence:event_log", "duration_s": 3600,
                 "retain_after": "landing", "on_disposition": "archive"},
            ],
            "benches": {},
        }),
        encoding="utf-8",
    )
    store = Store.open(db_path(data_dir))
    try:
        content = ContentStore(store)
        for i in range(rows):
            payload = json.dumps({"fault-arch": i}).encode()
            content.put_evidence(
                "event_log",
                {"id": f"ref-fault-arch-{i}", "version": "1",
                 "sha256": hashlib.sha256(payload).hexdigest()},
                content.put_artifact(payload, T0),
                "run:fault-arch-run", T0,
            )
    finally:
        store.close()
    return data_dir


def _archive_counts(data_dir: Path) -> tuple[int, int, int]:
    uri = f"{db_path(data_dir).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        audit = int(
            conn.execute("SELECT COUNT(*) FROM dispositions").fetchone()[0]
        )
        invocations = int(
            conn.execute(
                "SELECT COUNT(*) FROM disposition_invocations"
            ).fetchone()[0]
        )
        remaining = int(
            conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE kind = 'event_log'"
            ).fetchone()[0]
        )
        return audit, invocations, remaining
    finally:
        conn.close()


def _whole_objects(target: Path) -> list[Path]:
    """Every regular object file under ``target/objects`` — each one must
    re-hash to its content-addressed name (temp-orphan leftovers, if any,
    are skipped as non-objects; a killed pre-replace temp file is
    tolerated and disclosed by the design)."""
    objects_dir = target / "objects"
    if not objects_dir.is_dir():
        return []
    return [p for p in sorted(objects_dir.iterdir())
            if p.is_file() and not p.name.startswith(".")]


def test_ar5a_kill_mid_phase_a_leaves_store_untouched_whole_objects_only(
    tmp_path: Path,
) -> None:
    """AR5 (a): SIGKILL after the FIRST staged object's bytes verify
    (Phase A, no store transaction open) leaves the store byte-untouched
    — zero audit rows, zero invocations, every governed row present —
    and the destination carrying WHOLE objects only (every present
    object re-hashes to its content address). The re-run completes with
    final state == one clean run, the kill's objects verify-and-skip
    (dedup counted)."""
    data_dir = _seed_archive(tmp_path)
    target = tmp_path / "offline-fault"
    child = _spawn(data_dir, "stage-hold", target)
    try:
        _await_marker(child, "READY")
    finally:
        child.kill()
        child.wait(timeout=10)

    assert _archive_counts(data_dir) == (0, 0, 3), (
        "a kill in Phase A must leave the store untouched — no audit "
        "rows, no invocation rows, no deletions"
    )
    objects = _whole_objects(target)
    assert objects, "the first staged object landed before the kill"
    for obj in objects:
        assert hashlib.sha256(obj.read_bytes()).hexdigest() == (
            obj.name.removeprefix("art-")
        ), f"{obj.name}: only whole, verified objects may be present"

    from benchweave.cli.dispose import dispose_from_data_dir

    model = dispose_from_data_dir(
        data_dir, now=NOW, execute=True, archive_target=target
    )
    assert model["counts"]["archived"] == 3
    assert model["archive_objects_deduped"] >= 1, (
        "the kill's whole objects verify-and-skip on the re-run"
    )
    assert _archive_counts(data_dir) == (3, 1, 0), (
        "the re-run completes to the same final state as one clean run"
    )


def test_ar5b_kill_inside_phase_b_rolls_back_store_keeps_destination(
    tmp_path: Path,
) -> None:
    """AR5 (b): SIGKILL inside the ONE transaction (Phase B, one archive
    row fully processed, uncommitted) rolls the store back completely —
    zero audit rows, zero invocations, every governed row present —
    while the destination RETAINS its verified objects (staged
    pre-transaction; over-preservation, disclosed). The re-run completes
    with every object deduped."""
    data_dir = _seed_archive(tmp_path)
    target = tmp_path / "offline-fault"
    child = _spawn(data_dir, "hold", target)
    try:
        _await_marker(child, "READY")
    finally:
        child.kill()
        child.wait(timeout=10)

    assert _archive_counts(data_dir) == (0, 0, 3), (
        "the kill must roll the whole invocation back"
    )
    objects = _whole_objects(target)
    assert len(objects) == 3, (
        "the destination retains every object Phase A verified"
    )
    for obj in objects:
        assert hashlib.sha256(obj.read_bytes()).hexdigest() == (
            obj.name.removeprefix("art-")
        )

    from benchweave.cli.dispose import dispose_from_data_dir

    model = dispose_from_data_dir(
        data_dir, now=NOW, execute=True, archive_target=target
    )
    assert model["counts"]["archived"] == 3
    assert model["archive_objects_placed"] == 0, "nothing left to place"
    assert model["archive_objects_deduped"] == 3
    assert _archive_counts(data_dir) == (3, 1, 0)


def test_ar5c_kill_after_commit_verifies_clean(tmp_path: Path) -> None:
    """AR5 (c): SIGKILL after COMMIT loses nothing — the audit trail and
    deletions are durable, and the verify arm over the same destination
    is clean (every archived row's object re-proves)."""
    data_dir = _seed_archive(tmp_path)
    target = tmp_path / "offline-fault"
    child = _spawn(data_dir, "commit", target)
    try:
        _await_marker(child, "COMMITTED")
    finally:
        child.kill()
        child.wait(timeout=10)
    assert _archive_counts(data_dir) == (3, 1, 0), (
        "committed archival must survive SIGKILL"
    )

    from benchweave.cli.dispose import dispose_from_data_dir

    model = dispose_from_data_dir(
        data_dir, now=NOW, archive_target=target, verify_archive=True
    )
    assert model["clean"] is True
    assert model["verified"] == 3
    assert model["orphans"] == []
