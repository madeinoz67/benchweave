"""Advisory single-holder ownership for a store's database file (WP08 Task 10).

The one-coordinator rule's enforcement primitive: a live gateway holds an
exclusive ``flock`` on ``<db>.hold`` for exactly as long as its app lifespan
owns the store, and the at-rest commands (backup/restore) acquire the same
lock — refusing, with the holder named, while a live coordinator owns it.

Why ``flock`` and not a pid/boot-check marker: the operating system releases
an advisory ``flock`` when the holding PROCESS DIES, so a crashed gateway can
never leave a false "held" behind — the gate cannot false-positive across
process death (the exact failure mode pid+boot-check designs have to chase).
The lockfile BODY carries holder metadata (pid, label, acquired_at) purely
so a refused command can NAME the holder in its message; the lock itself,
never the file content, is the truth. Metadata is written only after the
lock is acquired, so the body always describes the current holder; stale
content under a free lock is ignored by design.

``fcntl.flock`` is POSIX (macOS/Linux) — the repo's supported platforms (CI
matrix is ubuntu/macos; the deploy target is systemd).
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class StoreHeldError(RuntimeError):
    """The store's database file is held by a live coordinator."""

    def __init__(self, holder: dict[str, Any] | None) -> None:
        self.holder = holder
        if holder:
            who = "{label} (pid {pid}, acquired {acquired_at})".format_map(
                {**{"label": "?", "pid": "?", "acquired_at": "?"}, **holder}
            )
        else:
            who = "an unidentified live holder"
        super().__init__(f"refusing: the store is held by {who}")


def hold_path(db_path: Path) -> Path:
    """The advisory lock file that marks ownership of ``db_path``."""
    db_path = Path(db_path)
    return db_path.with_name(db_path.name + ".hold")


def _read_holder(path: Path) -> dict[str, Any] | None:
    """Best-effort metadata read (never trusted for the held/free decision)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def holder_info(db_path: Path) -> dict[str, Any] | None:
    """Holder metadata for ``db_path``'s lock file, if any (advisory only)."""
    return _read_holder(hold_path(db_path))


class StoreHold:
    """An exclusive advisory hold over one store's database file.

    Context-manager or explicit ``acquire``/``release``; the hold lives
    exactly as long as the owning coordinator (a serving gateway's lifespan,
    or one at-rest command's execution window).
    """

    def __init__(self, db_path: Path, *, label: str) -> None:
        self._db_path = Path(db_path)
        self._label = label
        self._fd: int | None = None

    def acquire(self) -> None:
        """Take the exclusive hold; raise :class:`StoreHeldError` (naming the
        current holder) if a live coordinator already owns the store."""
        path = hold_path(self._db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Written only under the held lock: the body names the CURRENT
            # holder, never a refused contender.
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(
                fd,
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "label": self._label,
                        "acquired_at": datetime.now(UTC).isoformat(),
                    }
                ).encode("utf-8"),
            )
            os.fsync(fd)
        except BlockingIOError as error:
            os.close(fd)
            raise StoreHeldError(_read_holder(path)) from error
        except OSError:
            # Any other failure must not leak the descriptor (review M3).
            os.close(fd)
            raise
        self._fd = fd

    def release(self) -> None:
        """Drop the hold (a no-op when not held)."""
        if self._fd is None:
            return
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None

    def __enter__(self) -> StoreHold:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def daemon_holds(db_path: Path) -> bool:
    """True iff a live coordinator currently holds the store's advisory lock.

    The probe never writes and never trusts the file body — only the lock
    state decides, so a crashed holder's leftover marker cannot read as
    "held".
    """
    db_path = Path(db_path)
    path = hold_path(db_path)
    if not path.exists():
        return False
    try:
        # Read-only suffices for flock (review M3): the probe never writes,
        # and a read-only open works where a write open could not (e.g. a
        # 0600 marker owned by the gateway's user, probed by the operator).
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return False
    except PermissionError:
        # T10 review carry, direction PINNED (Task 11): an unreadable hold
        # marker reads as HELD. For the anti-coordinate rule (ISC-12) the
        # safe direction is held-true — a false "free" risks exactly the
        # second coordinator the gate exists to prevent, while a false
        # "held" in this single-operator loopback context is a cheap,
        # truthful retry once the operator fixes the permissions.
        return True
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return True
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
    return False
