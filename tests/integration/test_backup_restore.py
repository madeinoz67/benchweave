"""Task 10 integration: daemon-hold refusal + backup/restore restore parity.

The three brief pins, at the composed-gateway level:

1. **Daemon-hold both directions** — ``backup``/``restore`` refuse
   (exit != 0, truthful message naming the holder) while a LIVE composed
   gateway (real uvicorn boot, lifespan-run) holds the store, and succeed
   after shutdown.
2. **Restore parity (Verification rule 6)** — the test captures a BASELINE
   first (bench rows, run rows, a multi-event stream across two streams,
   evidence rows, artifact digests — read via the store), then
   backup -> destroy the data dir -> restore -> verify green, and proves
   the restored store serves the SAME rows/digests/events as baseline.
   A single synthetic event never closes this.
3. **WAL state** — the seeding connection stays OPEN before backup so the
   store carries un-checkpointed WAL activity (asserted non-empty); the
   SQLite backup-API snapshot must still contain the last committed rows
   (``wal_included: true`` in the manifest, event parity on restore).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from click.testing import CliRunner, Result
from fastapi import FastAPI

from benchweave.cli import atrest
from benchweave.cli.atrest import daemon_holds
from benchweave.cli.commands import cli
from benchweave.content.store import ContentStore
from benchweave.interfaces.app import create_app
from benchweave.interfaces.identity import issue
from benchweave.state.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
SECRET = b"wp08-task-ten-secret"
NOW_ISO = "2026-09-14T00:00:00Z"
NOW_EPOCH = 1_800_000_000
GATEWAY_ID = "gw-atrest"
LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
}


def _combined(result: Result) -> str:
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compose(db_path: Path) -> FastAPI:
    """The T9 boot composition over a chosen database file.

    The app does not own the store it is handed (its lifespan only takes
    and drops the hold), so the harness keeps it on ``app.state`` for
    ``_close_store`` to close.
    """
    store = Store.open(db_path, check_same_thread=False)
    content = ContentStore(store)
    app = create_app(
        store=store,
        content=content,
        secret=SECRET,
        limits=LIMITS,
        gateway_id=GATEWAY_ID,
        fixtures_dir=FIXTURES,
        now_iso=lambda: NOW_ISO,
        now_epoch=lambda: NOW_EPOCH,
    )
    app.state.harness_store = store
    return app


def _close_store(app: Any) -> None:
    """Close the connection ``_compose`` opened.

    In production the process exits and the OS closes it. In-process it
    stays open, which POSIX forgives and Windows does not: a directory
    holding an open file cannot be renamed there, so a restore after
    shutdown failed with WinError 5 (#136).
    """
    app.state.harness_store.close()


def _boot(app: FastAPI) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    assert getattr(server, "started", False), "uvicorn did not start"
    return server, thread


def _shutdown(
    server: uvicorn.Server, thread: threading.Thread, *, close_store: bool = True
) -> None:
    server.should_exit = True
    thread.join(timeout=5)
    if close_store:
        _close_store(server.config.app)


def _wait_held(db: Path, *, expected: bool, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while daemon_holds(db) is not expected:
        if time.monotonic() > deadline:
            pytest.fail(f"daemon_holds({db}) did not settle to {expected}")
        time.sleep(0.05)


# --- pin 1: daemon-hold, both directions ---------------------------------------


def test_backup_refuses_under_live_gateway_and_succeeds_after_shutdown(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    db = data / "state.sqlite"
    app = _compose(db)
    server, thread = _boot(app)
    try:
        _wait_held(db, expected=True)
        result = CliRunner().invoke(
            cli, ["backup", "--data-dir", str(data), "--out", str(tmp_path / "out")]
        )
        assert result.exit_code != 0
        combined = _combined(result)
        assert "held" in combined
        assert GATEWAY_ID in combined, "the refusal must name the holder"
        assert not list((tmp_path / "out").glob("backup-*"))
    finally:
        _shutdown(server, thread)

    _wait_held(db, expected=False)
    result = CliRunner().invoke(
        cli, ["backup", "--data-dir", str(data), "--out", str(tmp_path / "out")]
    )
    assert result.exit_code == 0, _combined(result)
    backups = list((tmp_path / "out").glob("backup-*"))
    assert len(backups) == 1
    assert atrest.verify(backups[0]) == 0, "the post-shutdown snapshot must verify clean"


def test_restore_refuses_under_live_gateway_and_leaves_target_untouched(
    tmp_path: Path,
) -> None:
    sacrificial = tmp_path / "seed"
    atrest.setup(sacrificial)
    archive = atrest.backup(sacrificial, tmp_path / "out")

    target = tmp_path / "live"
    target.mkdir()
    db = target / "state.sqlite"
    app = _compose(db)
    server, thread = _boot(app)
    before = _sha256(db)
    try:
        _wait_held(db, expected=True)
        result = CliRunner().invoke(
            cli, ["restore", "--archive", str(archive), "--data-dir", str(target)]
        )
        assert result.exit_code != 0
        combined = _combined(result)
        assert "held" in combined
        assert GATEWAY_ID in combined
    finally:
        # The store stays open across the byte comparison: closing the last
        # connection checkpoints the WAL into state.sqlite, which would change
        # the very bytes the comparison is about.
        _shutdown(server, thread, close_store=False)

    try:
        assert _sha256(db) == before, "a refused restore must not touch the live store"
        assert not list(tmp_path.glob("live.pre-restore-*"))
    finally:
        _close_store(app)

    # After shutdown the same restore completes and verifies green.
    result = CliRunner().invoke(
        cli, ["restore", "--archive", str(archive), "--data-dir", str(target)]
    )
    assert result.exit_code == 0, _combined(result)
    assert atrest.verify(target) == 0


# --- pins 2+3: restore parity over a WAL-active store ---------------------------


def test_roundtrip_restore_parity_with_uncheckpointed_wal(tmp_path: Path) -> None:
    data = tmp_path / "data"
    db = atrest.setup(data)
    store = Store.open(db)
    content = ContentStore(store)
    # M8 strictness: autocheckpoint OFF on the seeding connection, so the
    # un-checkpointed-WAL precondition is deterministic (not emergent from
    # merely holding the connection open).
    store.connection.execute("PRAGMA wal_autocheckpoint=0")

    # Seed a real multi-row, multi-stream corpus directly through the store.
    store.put_bench("bench-a", 1, "qualified", "{}", "licence-a", NOW_ISO)
    store.put_bench("bench-b", 2, "experimental", "{}", "licence-b", NOW_ISO)
    store.create_run("run-1", {"binding": "one"}, "principal-1", NOW_ISO)
    store.create_run("run-2", {"binding": "two", "nested": [1, 2]}, "principal-2", NOW_ISO)
    store.put_run_state("run-1", "bench-a", "terminal", NOW_ISO)
    store.put_run_state("run-2", "bench-b", "queued", NOW_ISO)
    # Streams use the seam's own naming ("bench.{bench_id}") so the
    # post-restore SERVED letter (M5 below) reads the same streams.
    for index in range(5):
        store.append_event("bench.bench-a", {"type": "run_changed", "index": str(index)})
    for index in range(3):
        store.append_event(
            "bench.bench-b", {"type": "lease_state_changed", "index": str(index)}
        )
    artifact_ids = [
        content.put_artifact(b"artifact-one", NOW_ISO),
        content.put_artifact(b"artifact-two-" * 64, NOW_ISO),
        content.put_artifact(b"artifact-three", NOW_ISO),
    ]
    evidence_id = content.put_evidence(
        "dataset",
        {"id": "run:run-1", "version": "1", "sha256": hashlib.sha256(b"artifact-one").hexdigest()},
        artifact_ids[0],
        "run:run-1",
        NOW_ISO,
    )

    # Pin 3 precondition: the seeding connection stays OPEN, so the store's
    # latest commits live in un-checkpointed WAL frames at backup time.
    wal = db.with_name(db.name + "-wal")
    assert wal.is_file() and wal.stat().st_size > 0, "WAL must hold un-checkpointed activity"

    # BASELINE FIRST (Verification rule 6) — everything via the store.
    baseline: dict[str, Any] = {
        "benches": {bid: store.get_bench(bid) for bid in ("bench-a", "bench-b")},
        "runs": {rid: store.get_run(rid) for rid in ("run-1", "run-2")},
        "run_states": {rid: store.get_run_state(rid) for rid in ("run-1", "run-2")},
        "events": {
            sid: store.read_events(sid) for sid in ("bench.bench-a", "bench.bench-b")
        },
        "artifact_digests": {
            aid: content.artifact_chunk(aid, 0, 64)["sha256"] for aid in artifact_ids
        },
        "evidence": content.get_evidence(evidence_id),
    }
    assert len(baseline["events"]["bench.bench-a"]) == 5, "multi-event stream, not a single event"

    archive = atrest.backup(data, tmp_path / "out")
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["wal_included"] is True, "the un-checkpointed WAL path was exercised"

    store.close()
    shutil.rmtree(data)
    assert not db.exists(), "data dir destroyed before restore"

    atrest.restore(archive, data)
    assert atrest.verify(data) == 0

    reopened = Store.open(db)
    try:
        recontent = ContentStore(reopened)
        benches = {bid: reopened.get_bench(bid) for bid in ("bench-a", "bench-b")}
        assert benches == baseline["benches"]
        assert {rid: reopened.get_run(rid) for rid in ("run-1", "run-2")} == baseline["runs"]
        assert {
            rid: reopened.get_run_state(rid) for rid in ("run-1", "run-2")
        } == baseline["run_states"]
        assert {
            sid: reopened.read_events(sid) for sid in ("bench.bench-a", "bench.bench-b")
        } == baseline["events"], "restored stream must match the baseline event-for-event"
        assert {
            aid: recontent.artifact_chunk(aid, 0, 64)["sha256"] for aid in artifact_ids
        } == baseline["artifact_digests"]
        assert recontent.get_evidence(evidence_id) == baseline["evidence"]
    finally:
        reopened.close()

    # M5 (serving letter): the restored store serves the SAME event letter
    # over REST — the full events_get envelope, not just store-level parity.
    app = _compose(db)
    server, thread = _boot(app)
    try:
        port = server.servers[0].sockets[0].getsockname()[1]
        observe = issue(
            SECRET,
            principal="atrest-observe",
            audience="stg",
            scopes={"stg:observe"},
            expires_at=NOW_EPOCH + 3600,
        )
        resp = httpx.get(
            f"http://127.0.0.1:{port}/v1/benches/bench-a/events",
            params={"limit": 10},
            headers={"Authorization": f"Bearer {observe}"},
            timeout=5.0,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert set(data) == {
            "events",
            "cursor",
            "stream_id",
            "oldest_sequence",
            "current_sequence",
        }
        assert data["events"] == baseline["events"]["bench.bench-a"]
        assert data["stream_id"] == "bench.bench-a"
        assert data["oldest_sequence"] == "1"
        assert data["current_sequence"] == "5"
    finally:
        _shutdown(server, thread)


# --- parity helper reuse guard ---------------------------------------------------


def test_restored_store_serves_through_a_composed_gateway(tmp_path: Path) -> None:
    """The restored store is not just readable — it serves a live gateway."""
    data = tmp_path / "data"
    db = atrest.setup(data)
    store = Store.open(db)
    store.put_bench("bench-z", 7, "qualified", "{}", "licence-z", NOW_ISO)
    store.close()
    archive = atrest.backup(data, tmp_path / "out")
    shutil.rmtree(data)
    atrest.restore(archive, data)

    db = data / "state.sqlite"
    app = _compose(db)
    server, thread = _boot(app)
    try:
        _wait_held(db, expected=True)
        store = Store.open(db, check_same_thread=False)
        try:
            row = store.get_bench("bench-z")
            assert row is not None and row["generation"] == 7
        finally:
            store.close()
    finally:
        _shutdown(server, thread)


def test_second_gateway_boot_is_refused_while_the_first_holds_the_store(
    tmp_path: Path,
) -> None:
    """M6: the one-coordinator rule at BOOT — while a live gateway holds the
    store, a second gateway composed over the same database must fail its
    lifespan (the StoreHold refusal), never silently co-coordinate."""
    data = tmp_path / "data"
    db = atrest.setup(data)
    first = _compose(db)
    server, thread = _boot(first)
    try:
        _wait_held(db, expected=True)
        second = _compose(db)
        config = uvicorn.Config(second, host="127.0.0.1", port=0, log_level="error")
        second_server = uvicorn.Server(config)
        second_thread = threading.Thread(target=second_server.run, daemon=True)
        second_thread.start()
        deadline = time.monotonic() + 5.0
        while not second_server.started and second_thread.is_alive():
            if time.monotonic() > deadline:
                break
            time.sleep(0.05)
        assert not second_server.started, (
            "a second gateway must not boot on a store the first one holds"
        )
        second_thread.join(timeout=5)
        _close_store(second)
        _wait_held(db, expected=True)  # the FIRST holder is unchanged
    finally:
        _shutdown(server, thread)
