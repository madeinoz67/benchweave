"""Task 10: at-rest commands — setup/verify/backup/restore + daemon-hold.

Covers the brief's failing-test groups at the CLI/library layer:

- ``setup`` creates the data-dir layout (``state.sqlite`` + ``content/``),
  applies migrations exactly as at app boot, and writes the generated
  secret ONLY to a 0600 credential file — stdout stays secret-free unless
  ``--show-secret`` is passed explicitly.
- The daemon-hold gate: ``daemon_holds`` is true under a live holder,
  false for a free store, and — the property pid/boot-check designs chase
  — false for a stale marker left by a dead holder (the flock is the
  truth, the file body is only a name tag).
- ``backup`` refuses (exit != 0) while a live holder locks the store,
  naming the holder; produces the brief's backup layout with a sha256
  manifest; ``verify`` is 0 iff every digest matches and the store passes
  integrity_check, enumerating mismatches truthfully.
- ``restore`` verifies digests BEFORE touching the target — a failed
  verify never half-replaces — and swaps atomically via ``os.replace``.
"""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from benchweave.cli.atrest import (
    backup,
    daemon_holds,
    restore,
    verify,
    verify_problems,
)
from benchweave.cli.commands import cli
from benchweave.state.hold import StoreHold
from benchweave.state.store import Store


def _combined(result: Result) -> str:
    """stdout + stderr, robust to click < 8.2's mixed-stream Result."""
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_secret(data_dir: Path) -> str:
    for line in (data_dir / "benchweave.env").read_text(encoding="utf-8").splitlines():
        if line.startswith("BENCHWEAVE_SECRET="):
            return line.removeprefix("BENCHWEAVE_SECRET=")
    raise AssertionError("credential file carries no BENCHWEAVE_SECRET")


def _initialized(data_dir: Path) -> Path:
    result = CliRunner().invoke(cli, ["setup", "--data-dir", str(data_dir)])
    assert result.exit_code == 0, _combined(result)
    return data_dir / "state.sqlite"


# --- setup -------------------------------------------------------------------


def test_setup_creates_layout_migrations_and_0600_credential_file(tmp_path: Path) -> None:
    data = tmp_path / "data"
    db = _initialized(data)
    assert db.is_file()
    assert (data / "content").is_dir()
    credential = data / "benchweave.env"
    assert credential.is_file()
    assert stat.S_IMODE(credential.stat().st_mode) == 0o600, "credential file must be 0600"
    secret = _read_secret(data)
    assert len(secret) >= 32, "generated secret must have real entropy"
    # Migrations ran exactly as at app boot: same Store.open path, same version.
    store = Store.open(db)
    try:
        assert store.schema_version() > 0
    finally:
        store.close()


def test_setup_secret_never_reaches_stdout_without_show_secret(tmp_path: Path) -> None:
    data = tmp_path / "data"
    result = CliRunner().invoke(cli, ["setup", "--data-dir", str(data)])
    assert result.exit_code == 0, _combined(result)
    assert _read_secret(data) not in result.output
    # Guidance on stderr names the credential file and its permission mode.
    combined = _combined(result)
    assert "benchweave.env" in combined
    assert "0600" in combined


def test_setup_show_secret_is_the_explicit_stdout_opt_in(tmp_path: Path) -> None:
    data = tmp_path / "data"
    result = CliRunner().invoke(cli, ["setup", "--data-dir", str(data), "--show-secret"])
    assert result.exit_code == 0, _combined(result)
    assert _read_secret(data) in result.output


def test_setup_json_contract_carries_no_secret_by_default(tmp_path: Path) -> None:
    data = tmp_path / "data"
    result = CliRunner().invoke(cli, ["setup", "--data-dir", str(data), "--json"])
    assert result.exit_code == 0, _combined(result)
    # CliRunner's `output` mixes the stderr guidance into the stream (a real
    # shell keeps them separate); the machine contract starts at the first {.
    payload = json.loads(result.output[result.output.index("{") :])
    assert {"data_dir", "db_path", "secret_file"} <= set(payload)
    assert "secret" not in payload
    assert _read_secret(data) not in result.output


def test_setup_refuses_to_touch_an_initialized_data_dir(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _initialized(data)
    result = CliRunner().invoke(cli, ["setup", "--data-dir", str(data)])
    assert result.exit_code != 0
    assert "already exists" in _combined(result)


# --- daemon-hold ----------------------------------------------------------------


def test_daemon_holds_is_false_for_a_free_store(tmp_path: Path) -> None:
    db = _initialized(tmp_path / "data")
    assert daemon_holds(db) is False


def test_daemon_holds_is_true_under_a_live_holder(tmp_path: Path) -> None:
    db = _initialized(tmp_path / "data")
    with StoreHold(db, label="gateway gw-unit pid 424242"):
        assert daemon_holds(db) is True
    assert daemon_holds(db) is False, "release must make the store free again"


def test_stale_marker_from_a_dead_holder_does_not_block(tmp_path: Path) -> None:
    """The no-false-positive-across-process-death pin: a crashed holder's
    leftover file body is ignored — the flock, not the content, is truth."""
    data = tmp_path / "data"
    db = _initialized(data)
    (data / "state.sqlite.hold").write_text(
        json.dumps({"pid": 999999, "label": "gateway gw-dead", "acquired_at": "2026-01-01"}),
        encoding="utf-8",
    )
    assert daemon_holds(db) is False
    result = CliRunner().invoke(
        cli, ["backup", "--data-dir", str(data), "--out", str(tmp_path / "o")]
    )
    assert result.exit_code == 0, _combined(result)


def test_backup_refuses_while_a_live_holder_locks_the_store(tmp_path: Path) -> None:
    data = tmp_path / "data"
    db = _initialized(data)
    with StoreHold(db, label="gateway gw-unit pid 424242"):
        result = CliRunner().invoke(
            cli, ["backup", "--data-dir", str(data), "--out", str(tmp_path / "out")]
        )
    assert result.exit_code != 0
    combined = _combined(result)
    assert "held" in combined
    assert "gw-unit" in combined and "424242" in combined, "must name the holder"
    assert not list((tmp_path / "out").glob("backup-*")), "refusal must not half-backup"


# --- backup + verify -------------------------------------------------------------


def test_backup_produces_the_brief_layout_with_sha256_manifest(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _initialized(data)
    # Content files (the on-disk content plane beside the DB-backed store).
    (data / "content" / "nested").mkdir(parents=True)
    (data / "content" / "nested" / "blob.bin").write_bytes(b"content-bytes")
    target = backup(data, tmp_path / "out")
    assert target.name.startswith("backup-")
    assert (target / "state.sqlite").is_file()
    assert (target / "content" / "nested" / "blob.bin").read_bytes() == b"content-bytes"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["wal_included"] in (True, False)
    files = manifest["files"]
    assert "state.sqlite" in files
    assert files["content/nested/blob.bin"] == _sha256(data / "content" / "nested" / "blob.bin")
    assert files["state.sqlite"] == _sha256(target / "state.sqlite")
    assert verify(target) == 0


def test_verify_enumerates_mismatches_truthfully(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _initialized(data)
    target = backup(data, tmp_path / "out")
    # Corrupt the store snapshot in the archive.
    (target / "state.sqlite").write_bytes(b"not-a-sqlite-file")
    problems = verify_problems(target)
    assert problems, "a corrupted archive must not verify clean"
    assert any("state.sqlite" in line for line in problems)
    assert verify(target) != 0


def test_verify_without_a_manifest_fails_with_guidance(tmp_path: Path) -> None:
    problems = verify_problems(tmp_path / "nowhere")
    assert problems and any("manifest" in line for line in problems)
    assert verify(tmp_path / "nowhere") != 0


def test_verify_accepts_relative_data_dir_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative ``--data-dir`` (found by the real-binary smoke): the
    read-only integrity probe must resolve, not crash on ``as_uri()``."""
    data = tmp_path / "data"
    _initialized(data)
    target = backup(data, tmp_path / "out")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli, ["verify", "--data-dir", target.relative_to(tmp_path).as_posix()]
    )
    assert result.exit_code == 0, _combined(result)


def test_backup_missing_store_fails_truthfully(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli, ["backup", "--data-dir", str(tmp_path / "empty"), "--out", str(tmp_path / "o")]
    )
    assert result.exit_code != 0
    assert "no store" in _combined(result)


# --- restore ------------------------------------------------------------------


def test_restore_into_a_fresh_dir_and_verify_green(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _initialized(data)
    target = backup(data, tmp_path / "out")
    fresh = tmp_path / "restored"
    restore(target, fresh)
    assert (fresh / "state.sqlite").is_file()
    assert (fresh / "content").is_dir()
    assert (fresh / "manifest.json").is_file(), "restore carries provenance for verify"
    assert verify(fresh) == 0
    store = Store.open(fresh / "state.sqlite")
    try:
        assert store.schema_version() > 0
    finally:
        store.close()


def test_failed_digest_verification_never_half_replaces(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _initialized(data)
    target = backup(data, tmp_path / "out")
    (target / "state.sqlite").write_bytes(b"corrupted-snapshot")
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "precious.txt").write_text("must survive a failed restore")
    result = CliRunner().invoke(
        cli, ["restore", "--archive", str(target), "--data-dir", str(victim)]
    )
    assert result.exit_code != 0
    assert "digest" in _combined(result)
    # Nothing was replaced: the original dir is intact, no aside copy exists.
    assert (victim / "precious.txt").read_text() == "must survive a failed restore"
    assert not (victim / "state.sqlite").exists()
    assert not list(tmp_path.glob("victim.pre-restore-*"))
    assert not list(tmp_path.glob(".victim.restore-*")), "staging dir must be cleaned"


def test_restore_replaces_a_live_data_dir_and_keeps_the_previous_copy(tmp_path: Path) -> None:
    old = tmp_path / "data"
    _initialized(old)
    (old / "content" / "old.txt").write_text("old")
    sacrificial = tmp_path / "seed2"
    _initialized(sacrificial)
    (sacrificial / "content" / "new.txt").write_text("new")
    archive = backup(sacrificial, tmp_path / "out")
    restore(archive, old)
    assert (old / "content" / "new.txt").read_text() == "new"
    asides = list(tmp_path.glob("data.pre-restore-*"))
    assert asides and (asides[0] / "content" / "old.txt").read_text() == "old"
    assert verify(old) == 0


def test_restore_missing_archive_fails_truthfully(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli, ["restore", "--archive", str(tmp_path / "nope"), "--data-dir", str(tmp_path / "d")]
    )
    assert result.exit_code != 0
