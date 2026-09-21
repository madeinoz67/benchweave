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
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from benchweave.cli import atrest
from benchweave.cli.atrest import (
    AtRestError,
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


def _windows_access_entries(path: Path) -> list[str]:
    """``icacls`` output for ``path``, one string per access entry."""
    system32 = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
    listing = subprocess.run(
        [str(system32 / "icacls.exe"), str(path)], capture_output=True, text=True, check=True
    ).stdout
    entries = []
    for line in listing.replace(str(path), "", 1).splitlines():
        entry = line.strip()
        if entry and "(" in entry:  # the trailing "Successfully processed" line has no rights
            entries.append(entry)
    return entries


def _assert_owner_only(credential: Path) -> None:
    """Mode 0600 where mode bits mean something; one explicit entry for this user where not."""
    if sys.platform != "win32":
        assert stat.S_IMODE(credential.stat().st_mode) == 0o600, "credential file must be 0600"
        return
    system32 = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
    me = subprocess.run(
        [str(system32 / "whoami.exe")], capture_output=True, text=True, check=True
    ).stdout.strip()
    entries = _windows_access_entries(credential)
    assert len(entries) == 1, f"credential file must carry exactly one access entry: {entries}"
    assert entries[0].casefold().startswith(me.casefold() + ":"), entries
    assert "(F)" in entries[0], entries
    assert "(I)" not in entries[0], f"the entry must be explicit, not inherited: {entries}"


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
    _assert_owner_only(credential)
    secret = _read_secret(data)
    assert len(secret) >= 32, "generated secret must have real entropy"
    # Migrations ran exactly as at app boot: same Store.open path, same version.
    store = Store.open(db)
    try:
        assert store.schema_version() > 0
    finally:
        store.close()


def test_credential_is_restricted_before_the_secret_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#137: on Windows the secret must never sit behind an inherited access list.

    The writer is plain file I/O around one restriction call, so with that call
    replaced the ordering is provable on any platform: at the moment of
    restriction the (staged) file exists and is empty.
    """
    seen: list[bytes] = []
    monkeypatch.setattr(atrest, "_restrict_to_current_user", lambda p: seen.append(p.read_bytes()))
    credential = tmp_path / "benchweave.env"
    atrest._write_owner_only_windows(credential, b"BENCHWEAVE_SECRET=s3cret\n")
    assert seen == [b""], "the file must exist, empty, when the access list is restricted"
    assert credential.read_bytes() == b"BENCHWEAVE_SECRET=s3cret\n"


def test_credential_is_not_written_when_it_cannot_be_restricted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#137: a volume with no access lists gets a refusal, not an unprotected secret."""

    def refuse(path: Path) -> None:
        raise AtRestError(f"cannot restrict {path} to the current user")

    monkeypatch.setattr(atrest, "_restrict_to_current_user", refuse)
    credential = tmp_path / "benchweave.env"
    with pytest.raises(AtRestError, match="cannot restrict"):
        atrest._write_owner_only_windows(credential, b"BENCHWEAVE_SECRET=s3cret\n")
    assert list(tmp_path.iterdir()) == [], "no credential file and no staging directory may remain"


@pytest.mark.skipif(sys.platform != "win32", reason="access lists are the Windows half of 0600")
def test_credential_is_born_private_under_a_permissive_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#137: a handle opened before the restriction would still read the secret afterwards.

    Windows checks access when a handle is opened, so restricting a file that
    was created permissive leaves a window. The data directory here grants
    every authenticated account Modify, inheritably (the posture of a
    directory on a data drive). At the moment of restriction, which is before
    any secret exists, the file must already carry nothing from that grant.
    """
    data = tmp_path / "data"
    data.mkdir()
    system32 = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
    subprocess.run(
        [str(system32 / "icacls.exe"), str(data), "/grant", "*S-1-5-11:(OI)(CI)M"],
        capture_output=True,
        check=True,
    )
    granted = [entry for entry in _windows_access_entries(data) if "(I)" not in entry]
    assert len(granted) == 1, granted  # the grant above, under its localised name
    everyone_signed_in = granted[0].split(":", 1)[0]

    at_restriction: list[list[str]] = []
    restrict = atrest._restrict_to_current_user

    def spy(path: Path) -> None:
        at_restriction.append(_windows_access_entries(path))
        restrict(path)

    monkeypatch.setattr(atrest, "_restrict_to_current_user", spy)
    credential = data / "benchweave.env"
    atrest._write_owner_only_windows(credential, b"BENCHWEAVE_SECRET=s3cret\n")

    assert len(at_restriction) == 1 and at_restriction[0], at_restriction
    assert not any(entry.startswith(everyone_signed_in + ":") for entry in at_restriction[0]), (
        f"the file was reachable through the directory's grant before it was restricted: "
        f"{at_restriction[0]}"
    )
    _assert_owner_only(credential)
    assert sorted(p.name for p in data.iterdir()) == ["benchweave.env"], "staging must be removed"


@pytest.mark.skipif(sys.platform != "win32", reason="icacls and whoami are Windows tools")
def test_restriction_failure_is_a_named_refusal(tmp_path: Path) -> None:
    """#137: icacls failing (here: the file is absent) surfaces as AtRestError, never silence."""
    with pytest.raises(AtRestError, match="no secret was written"):
        atrest._restrict_to_current_user(tmp_path / "absent.env")


def test_setup_secret_never_reaches_stdout_without_show_secret(tmp_path: Path) -> None:
    data = tmp_path / "data"
    result = CliRunner().invoke(cli, ["setup", "--data-dir", str(data)])
    assert result.exit_code == 0, _combined(result)
    assert _read_secret(data) not in result.output
    # Guidance on stderr names the credential file and its permission mode.
    combined = _combined(result)
    assert "benchweave.env" in combined
    assert "0600" in combined
    # ... and says what that means where mode bits mean nothing (#137).
    assert ("restricted to your account" in combined) is (sys.platform == "win32")


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
    # The marker is a sibling of the data dir (see state/hold.hold_path).
    (tmp_path / "data.hold").write_text(
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


# --- review fix wave: I1 — the digest gate may never be vacuous ------------------


def _rewrite_manifest_files(archive: Path, files: dict[str, str]) -> None:
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = files
    (archive / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def test_restore_rejects_an_emptied_manifest_despite_a_valid_db(tmp_path: Path) -> None:
    """A damaged manifest must fail the restore, not disarm it: an empty
    ``files`` dict would verify clean with ZERO digests checked."""
    data = tmp_path / "data"
    _initialized(data)
    archive = backup(data, tmp_path / "out")
    _rewrite_manifest_files(archive, {})
    fresh = tmp_path / "fresh"
    result = CliRunner().invoke(
        cli, ["restore", "--archive", str(archive), "--data-dir", str(fresh)]
    )
    assert result.exit_code != 0
    combined = _combined(result)
    assert "files" in combined and "empty" in combined
    assert not (fresh / "state.sqlite").exists(), "a disarmed manifest must not restore"


def test_restore_rejects_a_manifest_that_stops_covering_the_store(tmp_path: Path) -> None:
    """Dropping the ``state.sqlite`` entry while other digests still pass
    must not let the store swap in unverified."""
    data = tmp_path / "data"
    _initialized(data)
    (data / "content" / "blob.bin").write_bytes(b"content-bytes")
    archive = backup(data, tmp_path / "out")
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    files = {k: v for k, v in manifest["files"].items() if k != "state.sqlite"}
    assert files, "test needs at least one non-store entry to pass its digest"
    _rewrite_manifest_files(archive, files)
    fresh = tmp_path / "fresh"
    result = CliRunner().invoke(
        cli, ["restore", "--archive", str(archive), "--data-dir", str(fresh)]
    )
    assert result.exit_code != 0
    assert "state.sqlite" in _combined(result)
    assert not (fresh / "state.sqlite").exists()


def test_restore_runs_integrity_check_beyond_digests(tmp_path: Path) -> None:
    """The mutating command applies at least the advisory gate: a corrupt
    store whose manifest digest was fixed up to match still refuses."""
    data = tmp_path / "data"
    _initialized(data)
    archive = backup(data, tmp_path / "out")
    corrupt = b"definitely not a sqlite database"
    (archive / "state.sqlite").write_bytes(corrupt)
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    files = dict(manifest["files"])
    files["state.sqlite"] = _sha256_bytes(corrupt)
    _rewrite_manifest_files(archive, files)
    fresh = tmp_path / "fresh"
    result = CliRunner().invoke(
        cli, ["restore", "--archive", str(archive), "--data-dir", str(fresh)]
    )
    assert result.exit_code != 0
    assert "integrity" in _combined(result)
    assert not (fresh / "state.sqlite").exists()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# --- review fix wave: I2 — traceback-free at-rest boundaries ----------------------


def _handled(result: Result) -> None:
    assert result.exception is None or isinstance(
        result.exception, SystemExit
    ), f"must be a handled error, not a traceback: {result.exception!r}"


def test_restore_to_a_missing_parent_dir_is_handled_not_a_traceback(tmp_path: Path) -> None:
    """Disaster-recovery-to-a-rebuilt-path is THE restore use case — a
    nonexistent parent must refuse truthfully, not FileNotFoundError."""
    data = tmp_path / "data"
    _initialized(data)
    archive = backup(data, tmp_path / "out")
    target = tmp_path / "nonexistent" / "parent" / "data"
    result = CliRunner().invoke(
        cli, ["restore", "--archive", str(archive), "--data-dir", str(target)]
    )
    _handled(result)
    assert result.exit_code != 0
    assert "stage" in _combined(result)
    assert not (tmp_path / "nonexistent").exists(), "nothing created on refusal"


def test_backup_over_a_corrupted_store_is_handled_and_leaves_no_partial(
    tmp_path: Path,
) -> None:
    """A non-SQLite state.sqlite must exit non-zero with a truthful message
    (not sqlite3.DatabaseError), and a failed backup must not leave a
    partial backup-<iso>/ behind."""
    data = tmp_path / "data"
    _initialized(data)
    (data / "state.sqlite").write_bytes(b"junk-bytes-not-a-database")
    out = tmp_path / "out"
    result = CliRunner().invoke(cli, ["backup", "--data-dir", str(data), "--out", str(out)])
    _handled(result)
    assert result.exit_code != 0
    assert "snapshot" in _combined(result)
    assert not list(out.glob("backup-*")), "a failed backup must not leave a partial dir"


# --- WP08 closing audit: restore extras gate + the setup hold boundary ------------


def test_restore_refuses_unlisted_extra_files_in_the_archive(tmp_path: Path) -> None:
    """Forge minor 3: the digest gate was one-directional — an unlisted
    extra file in the archive's content/ rode into the data dir
    unverified and ``verify`` blessed the result. A backup tree is
    complete: ANY unlisted staged file is tampering."""
    data = tmp_path / "data"
    _initialized(data)
    (data / "content" / "blob.bin").write_bytes(b"content-bytes")
    archive = backup(data, tmp_path / "out")
    (archive / "content" / "smuggled.bin").write_bytes(b"evil-bytes")
    problems = verify_problems(archive)
    assert any("smuggled.bin" in line for line in problems), (
        "verify must not bless an archive carrying unlisted extras"
    )
    fresh = tmp_path / "fresh"
    result = CliRunner().invoke(
        cli, ["restore", "--archive", str(archive), "--data-dir", str(fresh)]
    )
    assert result.exit_code != 0
    combined = _combined(result)
    assert "smuggled.bin" in combined, "the refusal must name the extras"
    assert "unlisted" in combined
    assert not (fresh / "state.sqlite").exists(), "a smuggled extra must not restore"


def test_verify_still_accepts_live_sidecars_beside_the_manifest(tmp_path: Path) -> None:
    """The extras gate carves out the store's runtime sidecars and the
    deliberately-unbacked credential file: a restored data dir that has
    since served traffic (``-wal``/``-shm``) and carries the operator's
    re-placed ``benchweave.env`` still verifies clean — live-state, not
    tampering. The advisory hold marker lives BESIDE the data dir and so
    never enters the verified tree at all."""
    data = tmp_path / "data"
    _initialized(data)
    archive = backup(data, tmp_path / "out")
    fresh = tmp_path / "fresh"
    restore(archive, fresh)
    for sidecar in ("state.sqlite-wal", "state.sqlite-shm"):
        (fresh / sidecar).write_bytes(b"live-state")
    (fresh / "benchweave.env").write_text("BENCHWEAVE_SECRET=replaced\n")
    (tmp_path / "fresh.hold").write_bytes(b"live-state")  # sibling marker: outside the tree
    assert verify(fresh) == 0


def test_verify_still_accepts_the_registry_work_tree(tmp_path: Path) -> None:
    """``app_entry`` places the registry session's work tree (cache,
    ``packages.lock.json``, activations) under ``<data_dir>/registry/`` —
    live-state in a serving data dir, never backup content (restore never
    stages one). A restored data dir with registry activity must still
    verify clean, while a non-registry extra still refuses."""
    data = tmp_path / "data"
    _initialized(data)
    archive = backup(data, tmp_path / "out")
    fresh = tmp_path / "fresh"
    restore(archive, fresh)
    (fresh / "registry" / "cache").mkdir(parents=True)
    (fresh / "registry" / "cache" / "pkg.tgz").write_bytes(b"package")
    (fresh / "registry" / "packages.lock.json").write_text("{}\n")
    assert verify(fresh) == 0
    # The carve-out is narrow: a non-registry extra still refuses.
    (fresh / "content" / "smuggled.bin").write_bytes(b"evil")
    assert verify(fresh) != 0


def test_setup_refusal_while_the_store_is_held_is_handled_not_a_traceback(
    tmp_path: Path,
) -> None:
    """Forge minor 4: a racing setup (another coordinator holds the lock
    between the exists-check and the hold acquisition) must surface as a
    handled refusal naming the holder, never a StoreHeldError traceback."""
    data = tmp_path / "data"
    data.mkdir()
    with StoreHold(data / "state.sqlite", label="gateway gw-unit pid 424242"):
        result = CliRunner().invoke(cli, ["setup", "--data-dir", str(data)])
    _handled(result)
    assert result.exit_code != 0
    combined = _combined(result)
    assert "held" in combined
    assert "gw-unit" in combined and "424242" in combined, "must name the holder"


def test_verify_tolerates_the_legacy_in_dir_hold_marker(tmp_path: Path) -> None:
    """Pre-relocation releases left ``<data_dir>/state.sqlite.hold`` behind
    on release (unlock-without-unlink); every dir ever served or backed up
    before the marker moved beside the tree carries it. The fixed, known
    name is tolerated as live-state — the SIBLING marker stays outside the
    tree (the relocation's whole point), pinned by the sidecar test above
    (PR #35 MEDIUM).
    """

    data = tmp_path / "data"
    _initialized(data)
    archive = backup(data, tmp_path / "out")
    fresh = tmp_path / "fresh"
    restore(archive, fresh)
    (fresh / "state.sqlite.hold").write_bytes(b"legacy in-dir marker")
    assert verify(fresh) == 0
