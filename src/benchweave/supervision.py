"""Process-level supervision protocol: pidfile identity, the stop
doorbell, the supervision journal (issue #422 increment 3).

The design authority is
``.claude/deep-review/2026-10-08-issue422-inc2-supervision-design.md``;
this module is its §2.3 file family and §2.4 identity protocol, shared by
the serving daemon (``interfaces/supervision.py`` mounts it) and the CLI
verbs (``cli/lifecycle.py`` drives it). It deliberately imports neither
FastAPI nor uvicorn: the protocol is files and signals, so both sides —
and the tests — see one implementation.

The division of truth (STO-3's rider): the store hold is the truth about
whether a gateway owns a store; the pidfile is only the SIGNALING HANDLE.
Every verdict here yields to the hold and never overrides it — a
pid/hold disagreement is a typed desync, not a tiebreak.

None of these files ever carries a secret, a token, or credential
material: pids, run ids, paths, timestamps and outcome words only.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchweave.state.hold import daemon_holds, holder_info, sibling_path

#: The supervision file family's suffixes (§2.3) — siblings of the RESOLVED
#: data directory, derived exactly like ``<dir>.hold`` so ``restore``'s
#: ``os.replace`` swap can never strand a live reference.
PID_SUFFIX = ".pid"
STOP_SUFFIX = ".stop"
LOG_SUFFIX = ".log"
JOURNAL_SUFFIX = ".supervision.jsonl"

#: The pidfile's shape version.
PIDFILE_SCHEMA = 1
#: The stop request/verdict file's shape version.
STOP_SCHEMA = 1

#: Labels a GATEWAY (a serving daemon) writes into the hold body. The
#: label-first cross-check (lane-1 F6 fold) reads this: a non-gateway
#: label means an at-rest command holds a store no daemon owns, so the
#: pidfile stands on probe alone and no desync fires.
GATEWAY_HOLD_LABEL_PREFIX = "gateway "

# Typed refusal prefixes — greppable in CLI output, daemon logs, and the
# journal (the machine-matchable discipline every other refusal family
# carries).
ALREADY_RUNNING = "supervision_already_running:"
STALE_PID = "supervision_stale_pid:"
PID_UNKNOWN = "supervision_pid_unknown:"
HOLD_DESYNC = "supervision_hold_desync:"
STOP_REFUSED_RUN_ACTIVE = "stop_refused_run_active:"
STOP_FOREIGN_OWNER = "supervision_stop_foreign_owner:"
STOP_MODE_SUPERSEDED = "stop_mode_superseded:"
STOP_TIMEOUT = "stop_timeout:"


class SupervisionError(RuntimeError):
    """A typed supervision refusal (the message carries the prefix)."""


def pid_path(db_path: Path) -> Path:
    """``<dir>.pid`` — the signaling handle (never the truth)."""
    return sibling_path(db_path, PID_SUFFIX)


def stop_path(db_path: Path) -> Path:
    """``<dir>.stop`` — the doorbell request/verdict file."""
    return sibling_path(db_path, STOP_SUFFIX)


def log_path(db_path: Path) -> Path:
    """``<dir>.log`` — THE named daemon log destination under ``start``."""
    return sibling_path(db_path, LOG_SUFFIX)


def journal_path(db_path: Path) -> Path:
    """``<dir>.supervision.jsonl`` — the lifecycle verbs' audit journal."""
    return sibling_path(db_path, JOURNAL_SUFFIX)


def _now_wall() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# --- atomic file writes (the atrest/restore precedent, with the F6-fold
# --- bounded replace-retry for Windows share modes) -------------------------------


def atomic_write_json(
    path: Path, payload: dict[str, Any], *, retry_deadline_s: float = 0.0
) -> None:
    """Write ``payload`` as JSON atomically (temp + ``os.replace``).

    ``retry_deadline_s`` bounds a retry loop around the replace: a Windows
    handle opened without ``FILE_SHARE_DELETE`` (a CLI's open read, an
    indexer) makes a replace onto it fail transiently — the writer retries
    at a short cadence until the deadline, then raises. The temp file is
    mode 0600 and the replace keeps it ( POSIX; on Windows the mode bits
    do not reach the access list — the family carries no secrets, so the
    inherited list stands, disclosed).
    """
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    deadline = time.monotonic() + retry_deadline_s if retry_deadline_s else None
    while True:
        tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, raw)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.chmod(tmp, 0o600)  # os.open's mode is umask-masked; pin it
            os.replace(tmp, path)
            return
        except OSError:
            with contextlib.suppress(OSError):
                tmp.unlink()
            if deadline is not None and time.monotonic() < deadline:
                time.sleep(0.1)
                continue
            raise


def atomic_append_line(path: Path, line: str) -> None:
    """Append one line to the journal (open-append + write + fsync)."""
    payload = (line + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


# --- the pidfile (§2.4) ------------------------------------------------------------


def write_pidfile(
    db_path: Path, *, gateway_id: str, log_destination: str
) -> dict[str, Any]:
    """Write the pidfile ONCE at lifespan startup (after hold acquire).

    ``started_ticks`` is the OS process start time — the identity that
    makes pid reuse detectable (a recycled pid reads NOT-OURS, never a
    false OURS). Platform sources: Linux ``/proc/<pid>/stat`` field 22;
    macOS ``proc_pidinfo(PROC_PIDTBSDINFO)``; Windows ``GetProcessTimes``
    creation time; elsewhere absent and the verdict lattice defers to the
    hold.
    """
    payload: dict[str, Any] = {
        "pid": os.getpid(),
        "gateway_id": gateway_id,
        "data_dir": str(Path(db_path).parent),
        "started_wall": _now_wall(),
        "started_ticks": process_start_ticks(os.getpid()),
        "log_destination": log_destination,
        "schema": PIDFILE_SCHEMA,
    }
    atomic_write_json(pid_path(db_path), payload)
    return payload


def read_pidfile(db_path: Path) -> dict[str, Any] | None:
    """The parsed pidfile, or None when absent/unparseable."""
    try:
        raw = pid_path(db_path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("pid"), int):
        return parsed
    return None


def remove_pidfile(db_path: Path) -> None:
    """Remove the pidfile at clean shutdown (a no-op when absent)."""
    try:
        pid_path(db_path).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass  # a stale handle never blocks the shutdown path


# --- process identity (probe + start-time) ----------------------------------------


def probe_process(pid: int) -> str:
    """Signal-0-equivalent liveness: ``running`` / ``dead`` / ``unknown``.

    EPERM reads RUNNING (the process exists but is not ours to signal);
    an unresolvable failure reads UNKNOWN — anything else is
    indeterminate and must not be read as absence (the muninndb
    ``probeProcessNative`` discipline, adopted).
    """
    if sys.platform == "win32":
        return _probe_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "running"
    except OSError:
        return "unknown"
    return "running"


def _probe_windows(pid: int) -> str:
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
    if not handle:
        error = int(ctypes.get_last_error())  # type: ignore[attr-defined]
        if error == 5:  # ERROR_ACCESS_DENIED — exists, not ours
            return "running"
        if error == 87:  # ERROR_INVALID_PARAMETER — no such pid
            return "dead"
        return "unknown"
    try:
        code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return "running" if code.value == STILL_ACTIVE else "dead"
        return "unknown"
    finally:
        kernel32.CloseHandle(handle)


def process_start_ticks(pid: int) -> int | None:
    """The OS process start time as an opaque comparable integer.

    The value is only ever COMPARED against another read for the same
    platform (the pidfile records whatever this returns); its unit is
    platform-defined. ``None`` means unobtainable — the verdict lattice
    then defers to the hold (§2.4).
    """
    if sys.platform == "linux":
        return _ticks_linux(pid)
    if sys.platform == "darwin":
        return _ticks_darwin(pid)
    if sys.platform == "win32":
        return _ticks_windows(pid)
    return None


def _ticks_linux(pid: int) -> int | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    # The comm field (2) can contain spaces and parens — everything after
    # the LAST ')' is field 3 onward; starttime is field 22, index 19 here.
    tail = raw.rsplit(")", 1)
    if len(tail) != 2:
        return None
    fields = tail[1].split()
    if len(fields) < 20:
        return None
    try:
        return int(fields[19])
    except ValueError:
        return None


def _ticks_darwin(pid: int) -> int | None:
    """``sysctl(KERN_PROC_PID)`` → ``kp_proc.p_starttime`` (§2.4).

    The record names the sysctl discipline; the STRUCT layout is Apple's
    to change between SDKs (``proc_pidinfo``'s BSD-info flavor already
    slimmed on current macOS), so the reader asks for ``kinfo_proc`` and
    locates the start timeval as the first plausible ``(tv_sec, tv_usec)``
    pair — a seconds value within the last 30 days and a well-formed
    microsecond. The value only needs to be STABLE and COMPARABLE per
    platform, never interpreted absolutely."""
    import ctypes
    import struct as _struct
    import time as _time

    libc = ctypes.CDLL(None, use_errno=True)
    sysctl = libc.sysctl
    sysctl.restype = ctypes.c_int
    # CTL_KERN=1, KERN_PROC=14, KERN_PROC_PID=1.
    mib = (ctypes.c_int * 4)(1, 14, 1, pid)
    buf = ctypes.create_string_buffer(1024)
    length = ctypes.c_size_t(len(buf))
    if sysctl(mib, 4, buf, ctypes.byref(length), None, 0) != 0:
        return None
    raw = buf.raw[: length.value]
    horizon = _time.time() - 30 * 86400
    for offset in range(0, max(0, len(raw) - 16), 8):
        sec, usec = _struct.unpack_from("<qI", raw, offset)
        if horizon <= sec <= _time.time() and 0 <= usec < 1_000_000:
            return int(sec) * 1_000_000 + int(usec)
    return None


def _ticks_windows(pid: int) -> int | None:
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
    if not handle:
        return None
    try:
        class _Filetime(ctypes.Structure):
            _fields_ = [
                ("low", ctypes.c_ulong),
                ("high", ctypes.c_ulong),
            ]

        creation = _Filetime()
        exit_ = _Filetime()
        kernel = _Filetime()
        user = _Filetime()
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        return (int(creation.high) << 32) | int(creation.low)
    finally:
        kernel32.CloseHandle(handle)


def _signal_pid(pid: int, sig: int) -> None:
    """The single signal site (POSIX; a test spy seam — never called on
    Windows, where the poll is the doorbell of record)."""
    os.kill(pid, sig)


def _path_owner_uid(path: Path) -> int:
    """The file's owning uid (POSIX) / a Windows stand-in comparison value.

    On Windows the owner SID comparison degrades to equality with the
    process's own token: ``st_uid`` there is derived from the security
    descriptor in a way that matches for self-created files, so the
    foreign-owner hole the check closes is the POSIX one; disclosed.
    """
    return os.stat(path).st_uid


def _is_gateway_label(label: object) -> bool:
    return isinstance(label, str) and label.startswith(GATEWAY_HOLD_LABEL_PREFIX)


@dataclass(frozen=True)
class IdentityVerdict:
    """The three-valued identity plus the hold cross-check, every cell of
    the lattice (§2.4, lane-1 F7 fold) expressed as one of:

    ``absent``   — no pidfile: nothing to signal, nothing stale.
    ``dead``     — the named pid is gone: sidecars may be cleared.
    ``not-ours`` — a live pid that is NOT this gateway (pid reuse):
                   nothing is signaled; typed ``supervision_stale_pid:``.
    ``unknown``  — indeterminate (probe unresolved, or ticks unobtainable
                   with the hold not vouching): refuse, name the file.
    ``desync``   — identity says ours but the hold names a different
                   gateway pid: typed ``supervision_hold_desync:`` naming
                   BOTH numbers; nothing is signaled.
    ``ours``     — signal (with the hold's agreement wherever it is held
                   by a gateway label).
    """

    verdict: str
    pid: int | None
    pidfile: dict[str, Any] | None
    holder: dict[str, Any] | None
    detail: str


def verify_gateway_identity(
    db_path: Path,
    *,
    probe: Any = probe_process,
    ticks: Any = process_start_ticks,
) -> IdentityVerdict:
    """The full §2.4 lattice over one store's pidfile + hold."""
    db_path = Path(db_path)
    record = read_pidfile(db_path)
    if record is None:
        return IdentityVerdict("absent", None, None, None, "no pidfile")
    pid = int(record["pid"])
    file_ref = str(pid_path(db_path))
    holder = holder_info(db_path)
    held = daemon_holds(db_path)

    liveness = probe_process(pid)
    if liveness == "dead":
        return IdentityVerdict("dead", pid, record, holder, "not running")
    if liveness == "unknown":
        return IdentityVerdict(
            "unknown", pid, record, holder,
            f"{PID_UNKNOWN} the liveness probe could not resolve pid {pid} "
            f"({file_ref}) — verify the process manually before acting",
        )

    live_ticks = process_start_ticks(pid)
    if live_ticks is not None:
        recorded = record.get("started_ticks")
        if not isinstance(recorded, int) or recorded != live_ticks:
            return IdentityVerdict(
                "not-ours", pid, record, holder,
                f"{STALE_PID} pid {pid} is alive but is not this gateway "
                f"(start time differs; {file_ref} is a stale handle from a "
                "recycled pid) — nothing was signaled",
            )
        # Identity matches: the label-first hold cross-check (F6 fold).
        if held and _is_gateway_label((holder or {}).get("label")):
            holder_pid = (holder or {}).get("pid")
            if isinstance(holder_pid, int) and holder_pid != pid:
                return IdentityVerdict(
                    "desync", pid, record, holder,
                    f"{HOLD_DESYNC} the pidfile names pid {pid} but the "
                    f"store hold names gateway pid {holder_pid} — the hold "
                    "is the truth; nothing was signaled; verify which "
                    "process owns the bench",
                )
        return IdentityVerdict("ours", pid, record, holder, "running (ours)")

    # Ticks unobtainable: the hold decides (F7 fold).
    if held and _is_gateway_label((holder or {}).get("label")):
        holder_pid = (holder or {}).get("pid")
        if isinstance(holder_pid, int) and holder_pid == pid:
            return IdentityVerdict(
                "ours", pid, record, holder,
                "running (ours — the hold vouches; start time unobtainable "
                "on this platform)",
            )
        return IdentityVerdict(
            "unknown", pid, record, holder,
            f"{PID_UNKNOWN} pid {pid} is alive, its start time is "
            f"unobtainable, and the hold names gateway pid {holder_pid} "
            f"({file_ref}) — refuse rather than guess",
        )
    if held:
        # A non-gateway holder: the pidfile stands on probe alone, but
        # ticks are unobtainable — the conservative direction is refuse.
        return IdentityVerdict(
            "unknown", pid, record, holder,
            f"{PID_UNKNOWN} pid {pid} is alive, its start time is "
            f"unobtainable and the hold is held by "
            f"{(holder or {}).get('label')!r} "
            f"({file_ref}) — refuse rather than guess",
        )
    return IdentityVerdict(
        "unknown", pid, record, holder,
        f"{PID_UNKNOWN} pid {pid} is alive but its start time is "
        f"unobtainable on this platform and the hold is free ({file_ref}) "
        "— refuse rather than guess",
    )


# --- the stop doorbell (§3.2) ------------------------------------------------------


def write_stop_request(
    db_path: Path, *, mode: str, actor_pid: int, retry_deadline_s: float = 10.0
) -> dict[str, Any]:
    """Write the stop REQUEST atomically (step 1 of the doorbell)."""
    payload: dict[str, Any] = {
        "schema": STOP_SCHEMA,
        "mode": mode,
        "requested_wall": _now_wall(),
        "actor_pid": actor_pid,
    }
    atomic_write_json(stop_path(db_path), payload, retry_deadline_s=retry_deadline_s)
    return payload


def read_stop_file(db_path: Path) -> dict[str, Any] | None:
    """The parsed stop file (request OR verdict), None when absent or
    unparseable — a torn read is inert, never a crash."""
    try:
        raw = stop_path(db_path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def request_owner_ok(path: Path, *, daemon_uid: int | None = None) -> bool:
    """§3.2 step 4: the request file's OWNER must be the daemon's own
    effective identity — a foreign-owned request is never consumed."""
    expected = os.geteuid() if daemon_uid is None else daemon_uid
    return _path_owner_uid(path) == expected


# --- the supervision journal (§3.5 — the CLI is the SOLE writer) -------------------


def journal_append(db_path: Path, event: str, **fields: Any) -> None:
    """Append one typed row to ``<dir>.supervision.jsonl``.

    The journal is written ONLY by the lifecycle verbs (F2 fold: one
    writer per file — the daemon's verdict-file fields are copied here on
    observation, never appended cross-process). Durability split (F9):
    these rows are the DURABLE class — written before the CLI's own exit;
    rung 3's intent row is written BEFORE the kill, proceed-on-failure.
    """
    row: dict[str, Any] = {"wall": _now_wall(), "event": event, **fields}
    atomic_append_line(journal_path(db_path), json.dumps(row, sort_keys=True))
