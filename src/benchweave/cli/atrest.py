"""At-rest commands: setup/verify/backup/restore over the data directory.

The at-rest layer operates directly on the on-disk layout — never through a
serving gateway — under the one-coordinator rule: every mutating command
acquires the store's advisory hold (``state.hold``) for its execution
window and refuses, naming the holder, while a live gateway owns the store.

Data-directory layout::

    <data_dir>/
      state.sqlite        # the whole store (WP03 state + WP07 content tables)
      state.sqlite-wal    # WAL sidecars while any connection is open
      state.sqlite.hold   # advisory lock + holder metadata (never backed up)
      content/            # the on-disk content plane (empty while all
                          # content is DB-backed; the layout is the contract)
      benchweave.env      # 0600 credential file (NEVER backed up or restored)

Backup layout (``out/backup-<iso>/``)::

    state.sqlite   # sqlite3 Connection.backup snapshot — committed WAL
                   # frames are folded in, so the file is self-contained
    content/       # verbatim copy of the data dir's content plane
    manifest.json  # {"files": {path: sha256}, "wal_included": bool, ...}

Secret posture: ``setup`` generates the gateway secret and writes it ONLY
to ``benchweave.env`` (mode 0600). The library never returns or prints it;
the CLI's ``--show-secret`` flag is the single explicit opt-in that puts it
on stdout. Credentials are operator-held state, deliberately excluded from
backups (a restored deployment re-uses the operator's kept credential file).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchweave.state.hold import (
    StoreHold,
)
from benchweave.state.hold import (
    daemon_holds as daemon_holds,  # re-export (Task 11 demo anti-coordinate)
)
from benchweave.state.hold import (
    holder_info as holder_info,  # re-export
)
from benchweave.state.store import Store

__all__ = [
    "CONTENT_DIR",
    "CREDENTIAL_FILE",
    "DB_NAME",
    "MANIFEST_NAME",
    "SECRET_ENV_KEY",
    "backup",
    "daemon_holds",
    "holder_info",
    "read_secret",
    "restore",
    "setup",
    "verify",
    "verify_problems",
]

#: The store file name inside a data directory.
DB_NAME = "state.sqlite"
#: The on-disk content plane inside a data directory.
CONTENT_DIR = "content"
#: The 0600 credential file written by setup.
CREDENTIAL_FILE = "benchweave.env"
#: The env key carrying the gateway secret inside the credential file.
SECRET_ENV_KEY = "BENCHWEAVE_SECRET"  # noqa: S105 — an env var NAME, not a credential
#: The digest manifest name (in backups and in restored data dirs).
MANIFEST_NAME = "manifest.json"
#: Files a verified tree may carry beyond the manifest's ``files``: the
#: manifest itself (written after the digests are taken), the store's
#: runtime sidecars — ``-wal``/``-shm`` and the ``.hold`` marker — and the
#: deliberately-unbacked credential file (the operator re-places
#: ``benchweave.env`` in a restored data dir per the guide). All are
#: live-state, never backup content.
_UNLISTED_OK = frozenset(
    {MANIFEST_NAME, CREDENTIAL_FILE, DB_NAME + "-wal", DB_NAME + "-shm", DB_NAME + ".hold"}
)
#: The registry session's work tree root. ``app_entry`` places it under
#: ``<data_dir>/registry/`` (cache, ``packages.lock.json``, activations) —
#: live-state in a serving data dir, never backup content (restore never
#: stages one; see ``app_entry.registry_session_from_env``).
_REGISTRY_WORK_TREE = "registry"


class AtRestError(RuntimeError):
    """A truthful at-rest failure (the CLI shows it and exits non-zero)."""


def db_path(data_dir: Path) -> Path:
    """The store file inside ``data_dir``."""
    return Path(data_dir) / DB_NAME


def _now_tag() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest_tree(root: Path) -> dict[str, str]:
    """sha256 of every file under ``root``, keyed by POSIX-relative path."""
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = _sha256(path)
    return files


def _tree_files(root: Path) -> set[str]:
    """POSIX-relative paths of every file under ``root``."""
    return {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }


def _is_live_state(rel: str) -> bool:
    """May ``rel`` live in a verified tree beyond the manifest: one of the
    exact live-state names, or anywhere inside the registry work tree
    (``app_entry`` puts its cache/locks/activations under
    ``<data_dir>/registry/``). A files-only inventory makes the prefix
    rule sufficient — a stray root FILE named ``registry`` is not the
    work tree and stays an extra."""
    return rel in _UNLISTED_OK or rel.startswith(_REGISTRY_WORK_TREE + "/")


def _write_credential_file(path: Path, secret: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, f"{SECRET_ENV_KEY}={secret}\n".encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    # os.open's mode is umask-masked; pin the mode exactly.
    os.chmod(path, 0o600)


def _load_manifest(target: Path) -> dict[str, Any] | None:
    path = target / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AtRestError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise AtRestError(f"{path} must hold a JSON object")
    return parsed


# --- setup ---------------------------------------------------------------------


def setup(data_dir: Path) -> Path:
    """Initialize a fresh data directory; return the database path.

    Creates ``<data_dir>/{state.sqlite, content/, benchweave.env}``. The
    store is created via ``Store.open`` — migrations run exactly as at app
    boot, so ``serve`` can open the result directly. The generated secret
    is written only to the 0600 credential file; it is never returned
    (read it via :func:`read_secret`, or let the CLI's ``--show-secret``
    opt-in print it).
    """
    data_dir = Path(data_dir)
    db = db_path(data_dir)
    if db.exists():
        raise AtRestError(f"{db} already exists — setup only initializes a fresh data dir")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / CONTENT_DIR).mkdir(exist_ok=True)
    _write_credential_file(data_dir / CREDENTIAL_FILE, secrets.token_urlsafe(32))
    with StoreHold(db, label=f"setup pid {os.getpid()}"):
        store = Store.open(db)
        try:
            if store.schema_version() < 1:
                raise AtRestError("store migrations did not apply during setup")
        finally:
            store.close()
    return db


def read_secret(data_dir: Path) -> str:
    """The generated gateway secret from the credential file."""
    path = Path(data_dir) / CREDENTIAL_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise AtRestError(f"cannot read credential file {path}: {error}") from error
    for line in lines:
        if line.startswith(f"{SECRET_ENV_KEY}="):
            return line.removeprefix(f"{SECRET_ENV_KEY}=")
    raise AtRestError(f"no {SECRET_ENV_KEY} entry in {path}")


# --- backup ----------------------------------------------------------------------


def backup(data_dir: Path, out: Path) -> Path:
    """Snapshot the store + content into ``out/backup-<iso>/``; return it.

    Runs under the store's advisory hold: a live gateway (or any other
    coordinator) makes this raise :class:`StoreHeldError`. The snapshot is
    a ``sqlite3.Connection.backup`` image — committed WAL frames are folded
    into the file, making it self-contained regardless of checkpoint state.
    """
    data_dir = Path(data_dir)
    db = db_path(data_dir)
    if not db.is_file():
        raise AtRestError(f"no store at {db} — run setup first")
    stamp = _now_tag()
    target = Path(out) / f"backup-{stamp}"
    suffix = 1
    while target.exists():
        target = Path(out) / f"backup-{stamp}-{suffix}"
        suffix += 1
    wal = db.with_name(db.name + "-wal")
    wal_included = wal.is_file() and wal.stat().st_size > 0
    with StoreHold(db, label=f"backup pid {os.getpid()}"):
        # Only created under the hold: a refused backup must not leave a
        # half-created target directory behind.
        target.mkdir(parents=True)
        try:
            source = sqlite3.connect(str(db))
            snapshot = target / DB_NAME
            dest = sqlite3.connect(str(snapshot))
            try:
                source.backup(dest)
            except sqlite3.Error as error:
                raise AtRestError(f"cannot snapshot {db}: {error}") from error
            finally:
                dest.close()
                source.close()
            content_src = data_dir / CONTENT_DIR
            try:
                if content_src.is_dir():
                    shutil.copytree(content_src, target / CONTENT_DIR)
                else:
                    (target / CONTENT_DIR).mkdir()
            except OSError as error:
                raise AtRestError(f"cannot copy content from {content_src}: {error}") from error
        except BaseException:
            # A failed backup must not leave a partial backup-<iso>/ behind
            # (review M4) — same cleanliness as the refusal path.
            shutil.rmtree(target, ignore_errors=True)
            raise
    manifest = {
        "files": _digest_tree(target),
        "wal_included": wal_included,
        "created_at": stamp,
    }
    (target / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


# --- restore ----------------------------------------------------------------------


def _manifest_mismatches(staged: Path, manifest: dict[str, Any]) -> list[str]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        return [f"{MANIFEST_NAME}: 'files' must be an object"]
    problems: list[str] = []
    # The digest gate may never be vacuous (review I1): a damaged manifest —
    # an emptied ``files`` dict, or one that stops covering the store while
    # the archive still carries it — must fail verification, not disarm it.
    if not files:
        problems.append(f"{MANIFEST_NAME}: 'files' is empty — nothing to verify")
    elif DB_NAME not in files and (staged / DB_NAME).is_file():
        problems.append(f"{MANIFEST_NAME}: 'files' does not cover {DB_NAME}")
    for rel in sorted(files):
        expected = str(files[rel])
        path = staged / rel
        if not path.is_file():
            problems.append(f"{rel}: missing")
            continue
        actual = _sha256(path)
        if actual != expected:
            problems.append(f"{rel}: sha256 mismatch (expected {expected[:12]}, got {actual[:12]})")
    # The gate is total in BOTH directions (WP08 closing audit, Forge
    # minor 3): a backup tree is complete, so any staged file the manifest
    # does not list is smuggling, not provenance — refuse naming the
    # extras. Before this, ``content/`` extras rode into the data dir
    # unverified and ``verify`` blessed the result. The only unlisted
    # files allowed are live-state (the manifest itself, the credential
    # file, the store's runtime sidecars, and the registry work tree —
    # see ``_is_live_state``).
    extras = sorted(
        rel for rel in _tree_files(staged) if rel not in files and not _is_live_state(rel)
    )
    if extras:
        problems.append(f"{MANIFEST_NAME}: unlisted file(s) present: " + ", ".join(extras))
    return problems


def restore(archive: Path, data_dir: Path) -> None:
    """Verify ``archive`` against its manifest, then swap it in as ``data_dir``.

    The archive is staged into a sibling temp directory and every manifest
    digest is checked BEFORE anything in ``data_dir`` is touched — a failed
    verify never half-replaces. The manifest gate is total in BOTH
    directions (review I1 + the WP08 closing audit): a damaged manifest
    (emptied ``files``, one that stops covering the store) fails the
    restore instead of disarming the digest check, and any staged file the
    manifest does not list is refused as tampering (a backup tree is
    complete). The staged snapshot must also pass the same SQLite
    integrity check ``verify`` applies — the mutating command never runs
    a weaker gate than the advisory one.
    The previous data dir is renamed aside as
    ``<name>.pre-restore-<stamp>`` (kept for the operator), then the staged
    directory is moved into place with ``os.replace``; if that move fails
    the aside copy is put straight back. During the swap window the held
    lock stays anchored to the OLD database file's inode (now inside the
    aside dir) — the incoming directory is un-anchored until this call
    returns, so a gateway booting concurrently can take a fresh hold inode;
    the swap then fails loudly (``ENOTEMPTY``) with the aside copy
    preserved — confusing, never corrupting. Credentials
    (``benchweave.env``) are deliberately not part of backups and are not
    restored.
    """
    archive = Path(archive)
    data_dir = Path(data_dir)
    if not (archive / MANIFEST_NAME).is_file():
        raise AtRestError(f"archive {archive} has no {MANIFEST_NAME} — not a backup directory")
    manifest = _load_manifest(archive)
    assert manifest is not None  # noqa: S101 — narrowing only; is_file above makes this true
    for required in (DB_NAME,):
        if not (archive / required).is_file():
            raise AtRestError(f"archive {archive} is missing {required}")
    db = db_path(data_dir)
    hold = StoreHold(db, label=f"restore pid {os.getpid()}") if db.is_file() else None
    if hold is not None:
        hold.acquire()
    try:
        try:
            staging = Path(
                tempfile.mkdtemp(dir=data_dir.parent, prefix=f".{data_dir.name}.restore-")
            )
        except OSError as error:
            # Disaster-recovery-to-a-rebuilt-path is THE restore use case —
            # a missing parent must refuse truthfully, not traceback.
            raise AtRestError(
                f"cannot stage restore beside {data_dir.parent}: {error}"
            ) from error
        try:
            staged = staging / data_dir.name
            staged.mkdir()
            try:
                shutil.copy2(archive / DB_NAME, staged / DB_NAME)
                content_src = archive / CONTENT_DIR
                if content_src.is_dir():
                    shutil.copytree(content_src, staged / CONTENT_DIR)
                else:
                    (staged / CONTENT_DIR).mkdir()
                shutil.copy2(archive / MANIFEST_NAME, staged / MANIFEST_NAME)
            except OSError as error:
                raise AtRestError(f"cannot read archive {archive}: {error}") from error
            problems = _manifest_mismatches(staged, manifest)
            problems.extend(_integrity_problems(staged / DB_NAME))
            if problems:
                raise AtRestError(
                    "archive digest/integrity verification failed: " + "; ".join(problems)
                )
            aside: Path | None = None
            if data_dir.exists():
                aside = data_dir.with_name(f"{data_dir.name}.pre-restore-{_now_tag()}")
                os.replace(data_dir, aside)
            try:
                os.replace(staged, data_dir)
            except OSError:
                if aside is not None and not data_dir.exists():
                    os.replace(aside, data_dir)  # put the live store back
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    finally:
        if hold is not None:
            hold.release()


# --- verify ------------------------------------------------------------------------


def _integrity_problems(db: Path) -> list[str]:
    # resolve(): a relative --data-dir must not crash as_uri() (which only
    # accepts absolute paths) — the CLI works from any cwd.
    uri = f"{db.resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except (sqlite3.Error, ValueError) as error:
        return [f"{DB_NAME}: cannot open read-only: {error}"]
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as error:
        return [f"{DB_NAME}: integrity_check failed: {error}"]
    finally:
        conn.close()
    results = [str(row[0]) for row in rows]
    if results != ["ok"]:
        return [f"{DB_NAME}: integrity_check failed: {'; '.join(results)}"]
    return []


def verify_problems(target: Path) -> list[str]:
    """Every problem found verifying ``target`` (empty list == clean).

    ``target`` is a backup archive or a restored data dir — both carry
    ``manifest.json``. Exit-0 bar: every manifest digest matches, NO
    unlisted file is present (beyond live-state: the manifest itself, the
    store's runtime sidecars, the deliberately-unbacked credential file,
    and the registry session's work tree), AND the store file passes
    SQLite's integrity_check. Runtime sidecar files
    (``-wal``/``-shm``/the hold marker) are live-state, not manifest
    entries — their presence is expected and never a mismatch.
    """
    target = Path(target)
    problems: list[str] = []
    manifest = _load_manifest(target)
    if manifest is None:
        return [
            f"{MANIFEST_NAME}: not found — verify needs a backup archive"
            " or a restored data dir"
        ]
    problems.extend(_manifest_mismatches(target, manifest))
    db = target / DB_NAME
    if db.is_file():
        problems.extend(_integrity_problems(db))
    return problems


def verify(target: Path) -> int:
    """0 iff every manifest digest matches and the store opens clean."""
    return 0 if not verify_problems(target) else 1
