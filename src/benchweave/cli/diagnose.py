"""The doctor + logs verbs (issue #422 increment 4).

``doctor`` is the read-only triage probe (the design record §1): seven
typed check rows over the store-at-rest and the supervision family,
composed from mechanisms increment 3 already landed — the identity lattice
and hold verdict arrive EMBEDDED from ``lifecycle.status_lifecycle`` (one
spelling, so ``status`` and ``doctor`` can never disagree), the store read
is the ``verify``-precedent ``mode=ro`` SQLite probe, and the env-file
check is the SAME validation call serve makes.

The boundary (STO-3's rider): doctor takes no hold, opens no ``Store``,
runs no migrations, and writes no supervision or benchweave-owned file —
the ``mode=ro`` probe may materialize the empty SQLite sidecar pair
(``-shm``/``-wal``), ``verify``'s own at-rest behavior, already tolerated
by atrest ``_UNLISTED_OK``. Triage therefore works WHILE a live
coordinator holds the store, which is the whole point.

``logs`` (§2) tails the named destination through the resolution ladder
(pidfile field → journal/stderr/path, the post-mortem sibling rung, the
credential guard refusing the env file as a tail source). Both verbs emit
key NAMES and paths only — never env-file values or token material.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from benchweave import supervision
from benchweave.cli.atrest import CREDENTIAL_FILE, DB_NAME
from benchweave.cli.env_file import (
    ENV_FILE_EXCLUDED_KEYS,
    EnvFileError,
    parse_env_file,
    serve_env_file_keys,
)

#: The journald unit the gateway's systemd deploy serves under (the
#: journalctl leg's ``-u`` argument and D6's carried unit name).
JOURNAL_UNIT = "benchweave"

#: The tail's first read window (service parameter, A02: ``--lines`` and
#: the window bound the tail's own IO, never a bench envelope).
TAIL_WINDOW_BYTES = 64 * 1024

#: The doubling window's cap (service parameter, A02 — same class as
#: ``TAIL_WINDOW_BYTES``). The window never grows past this, so a blob
#: that defeats line-splitting is refused, never read whole (W1).
TAIL_WINDOW_CAP_BYTES = 8 * 1024 * 1024

#: The journalctl consult's bound (the atrest whoami/icacls precedent:
#: fixed argv, bounded timeout).
JOURNALCTL_TIMEOUT_S = 10.0

#: Typed refusal prefixes (the greppable discipline every refusal family
#: carries).
LOGS_LINES_DOMAIN = "logs_lines_domain:"
LOGS_DESTINATION_CREDENTIAL = "logs_destination_credential:"
LOGS_UNREADABLE = "logs_unreadable:"
LOGS_WINDOW_CAP = "logs_window_cap:"
LOGS_JOURNAL_UNAVAILABLE = "logs_journal_unavailable:"
LOGS_DESTINATION_STDERR = "logs_destination_stderr:"
LOGS_NO_DESTINATION = "logs_no_destination:"


class DiagnoseError(RuntimeError):
    """A typed logs refusal (the message carries the prefix)."""


def _db(data_dir: Path) -> Path:
    return Path(data_dir) / DB_NAME


def _row(check: str, verdict: str, detail: str, **fields: Any) -> dict[str, Any]:
    return {"check": check, "verdict": verdict, "detail": detail, **fields}


# --- D1: the store ----------------------------------------------------------------


def _store_integrity_problems(db: Path) -> list[str]:
    """The ``verify``-precedent read-only integrity probe — the same
    ``as_uri()?mode=ro`` idiom ``atrest._integrity_problems`` uses, cited
    rather than imported: doctor keeps its own small function so the probe
    stays a read-only triage fact, never entangled with the manifest
    digest gate ``verify`` layers on top of it."""
    uri = f"{db.resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except (sqlite3.Error, ValueError) as error:
        return [f"{DB_NAME}: cannot open read-only: {error}"]
    try:
        found = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as error:
        return [f"{DB_NAME}: integrity_check failed: {error}"]
    finally:
        conn.close()
    results = [str(row[0]) for row in found]
    if results != ["ok"]:
        return [f"{DB_NAME}: integrity_check failed: {'; '.join(results)}"]
    return []


def _check_store(db: Path) -> dict[str, Any]:
    if not db.is_file():
        return _row(
            "store",
            "fail",
            f"no {DB_NAME} — run `benchweave setup --data-dir "
            f"{db.parent}` first (doctor never creates one)",
        )
    problems = _store_integrity_problems(db)
    if problems:
        return _row("store", "fail", "; ".join(problems))
    return _row("store", "pass", "integrity_check ok (read-only probe)")


# --- D2/D3/D6: the status_lifecycle mappings --------------------------------------


def _check_hold(snapshot: dict[str, Any]) -> dict[str, Any]:
    hold = snapshot.get("hold") or {}
    holder = hold.get("holder") or {}
    if not hold.get("held"):
        return _row("hold", "pass", "free — no coordinator owns the store", held=False)
    label = str(holder.get("label") or "")
    if holder:
        detail = (
            f"held by {label or 'an unidentified live holder'} "
            f"(pid {holder.get('pid', '?')}) — informational; triage proceeds"
        )
    else:
        detail = (
            "held; the holder body is unreadable (advisory only — the flock "
            "is the truth)"
        )
    return _row("hold", "pass", detail, held=True, holder_label=label or None)


_PID_ROW_NOTES = {
    "ours": None,
    "absent": (
        "no pidfile — never served or cleanly stopped (foreground serve "
        "writes a PRESENT stderr pidfile; a fresh `start` inside its ≤30 s "
        "readiness window can transiently read absent)"
    ),
    "dead": "the pidfile names a dead pid — stale sidecars present; `stop` clears them",
}


def _check_pid(snapshot: dict[str, Any]) -> dict[str, Any]:
    pid = snapshot.get("pid") or {}
    verdict = str(pid.get("verdict", "absent"))
    detail = str(pid.get("detail") or "")
    if verdict in ("not-ours", "desync"):
        return _row("pid", "fail", detail, pid=pid.get("pid"))
    if verdict == "unknown":
        return _row("pid", "unknown", detail, pid=pid.get("pid"))
    note = _PID_ROW_NOTES.get(verdict)
    if note is not None:
        if verdict == "absent" and detail != "no pidfile":
            # W8: the lattice's absent detail names the real shape (a
            # fieldless/legacy pidfile IS present) — the notice says so,
            # never "no pidfile" while one exists.
            return _row("pid", "pass", detail, pid=pid.get("pid"))
        return _row("pid", "pass", note, pid=pid.get("pid"))
    return _row("pid", "pass", detail or verdict, pid=pid.get("pid"))


def _check_log_destination(data_dir: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    pid_verdict = str((snapshot.get("pid") or {}).get("verdict", "absent"))
    raw = snapshot.get("log_destination")
    if pid_verdict != "absent":
        # The pidfile-present branch: the field is what the writer recorded.
        if raw == "journal":
            return _row(
                "log_destination",
                "pass",
                f"the journal (unit {JOURNAL_UNIT}) — read via `logs`",
                destination="journal",
                unit=JOURNAL_UNIT,
            )
        if raw == "stderr":
            return _row(
                "log_destination",
                "pass",
                "stderr (foreground serve) — `logs` will refuse",
                destination="stderr",
            )
        if isinstance(raw, str) and raw:
            path = Path(raw)
            if path.is_file():
                return _row(
                    "log_destination",
                    "pass",
                    f"the file {path}",
                    destination=str(path),
                )
            return _row(
                "log_destination",
                "pass",
                f"no file at {path} yet — created at the next `start`",
                destination=str(path),
            )
        return _row(
            "log_destination",
            "unknown",
            "the pidfile's log_destination is out-of-vocab "
            f"({raw!r}) — hand-written or tampered; verify before acting",
            destination=raw if isinstance(raw, str) else None,
        )
    # The absent branch derives beyond the payload (R8 fold): the sibling
    # log file is the honest post-mortem source when it exists.
    log = supervision.log_path(_db(data_dir))
    if log.is_file():
        return _row(
            "log_destination",
            "pass",
            f"no pidfile — the sibling {log} is the post-mortem source",
            destination=str(log),
            post_mortem=True,
        )
    return _row(
        "log_destination",
        "pass",
        "no destination yet — <dir>.log is created at the next `start`",
    )


# --- D4: the env file --------------------------------------------------------------


def _check_env_file(data_dir: Path) -> dict[str, Any]:
    path = Path(data_dir) / CREDENTIAL_FILE
    if not path.is_file():
        return _row(
            "env_file",
            "pass",
            "no env file — autoload is optional (process env / a unit "
            "EnvironmentFile is the deploy path)",
            present=False,
        )
    # The SAME validation call serve makes (parse_env_file, NOT
    # load_env_file — the apply variant would put the secret into this
    # process's own env). Doctor previews the next boot's own refusal.
    try:
        parse_env_file(path, serve_env_file_keys(), excluded=ENV_FILE_EXCLUDED_KEYS)
    except EnvFileError as error:
        return _row("env_file", "fail", str(error), present=True)
    except OSError as error:
        # W2: the delete-in-window race — the file can vanish between the
        # is_file() above and the path.stat() inside _check_owner_only.
        # That OSError is not an EnvFileError; it becomes a FAIL row and
        # triage CONTINUES (never a mid-run crash with zero rows).
        return _row(
            "env_file",
            "fail",
            f"env_file: {path} disappeared or became unreadable during "
            f"the check: {error}",
            present=True,
        )
    note = (
        "valid against serve's own allowlist and perms discipline "
        "(key names only — values never reach output"
    )
    if sys.platform == "win32":
        note += (
            "; Windows: mode bits do not reach the ACL — setup enforced "
            "owner-only at write time"
        )
    note += ")"
    return _row("env_file", "pass", note, present=True)


# --- D5: the service-manager unit ---------------------------------------------------


def _check_unit(snapshot: dict[str, Any]) -> dict[str, Any]:
    from benchweave.cli.lifecycle import PLIST_DEFAULT, UNIT_DEFAULT

    if sys.platform == "darwin":
        path = Path.home() / "Library" / "LaunchDaemons" / PLIST_DEFAULT
        present = path.is_file()
        if present:
            detail = (
                "a plist is statable at the default path — statability is "
                "all it means: load state is launchctl's, and "
                "~/Library/LaunchDaemons is outside launchd's scan paths "
                "(/Library/LaunchDaemons, /Library/LaunchAgents, "
                "~/Library/LaunchAgents), so `launchctl load` may be the "
                "missing step"
            )
            if snapshot.get("log_destination") == "stderr":
                detail += (
                    "; the rendered plist sets no StandardErrorPath, so a "
                    "launchd-run daemon's log is lost by construction — "
                    "run under `start` (the <dir>.log + pidfile mode) until "
                    "the deferred launchd issue lands"
                )
        else:
            detail = "no plist at the default path — `start`/pidfile mode"
        return _row("unit", "pass", detail, path=str(path), present=present)
    path = UNIT_DEFAULT
    present = path.is_file()
    detail = (
        "a systemd unit is installed — restart-on-crash belongs to the "
        "service manager"
        if present
        else "no systemd unit at the conventional path — `start`/pidfile mode"
    )
    return _row("unit", "pass", detail, path=str(path), present=present)


# --- D7: the supervision sidecars ----------------------------------------------------


def _journal_problems(path: Path) -> tuple[list[str], list[str]]:
    """The journal parseability rule: ``(problems, notes)``.

    A torn FINAL line is the known crash-tear shape (appends are
    single-write+fsync, so a crash can tear exactly the last line) — a
    NOTE, not a problem. An unparseable non-final line is only reachable
    by tampering — a problem, and the row says so. An unreadable journal
    (OSError on open/read) is the ``supervision_journal_unreadable:``
    problem the caller maps to the row's ``unknown`` verdict.

    The classifier (W3, l2 F1): torn ONLY when the raw tail does not end
    ``"\\n"``. A single-write+fsync append cannot end with its own
    newline, so a NEWLINE-TERMINATED unparseable line — final or not — is
    TAMPERING, never the crash-tear pass."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return ([f"supervision_journal_unreadable: cannot read it: {error}"], [])
    torn_final_possible = not raw.endswith("\n")
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    problems: list[str] = []
    notes: list[str] = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1 and torn_final_possible:
                notes.append(
                    "the journal's final line is torn — the known crash-tear "
                    "shape (appends are single-write+fsync)"
                )
            else:
                problems.append(
                    f"the journal's line {index + 1} is unparseable — "
                    "every line here is newline-terminated (a completed "
                    "single-write+fsync append), so this is tampering, not "
                    "a crash tear (only an unterminated final line can tear)"
                )
    return (problems, notes)


def _check_supervision_sidecars(db: Path) -> dict[str, Any]:
    details: list[str] = []
    stop_file = supervision.stop_path(db)
    if stop_file.is_file():
        record = supervision.read_stop_file(db)
        if record is None:
            details.append(
                "the .stop file is unreadable or unparseable — inert "
                "daemon-side (the daemon's stop-check treats an unreadable "
                "request as no request)"
            )
        elif "status" in record:
            details.append("the .stop file is a consumed verdict — inert")
        else:
            target = record.get("target_pid")
            if not isinstance(target, int):
                details.append(
                    "an unbound (legacy) stop request — `start` clears "
                    "unconsumed requests"
                )
            elif supervision.probe_process(target) == "dead":
                details.append(
                    f"a stale stop request targeting dead pid {target} — "
                    "`start` clears unconsumed requests (era-bound, inert)"
                )
            else:
                details.append(
                    f"a stop request targeting live pid {target} — in "
                    "flight or left over; inert unless its target consumes it"
                )
    else:
        details.append("no stop request present")
    journal = supervision.journal_path(db)
    if journal.is_file():
        problems, notes = _journal_problems(journal)
        details.extend(notes)
        details.extend(problems)
        if not problems:
            details.append("the journal's lines all parse")
        hard = [
            problem
            for problem in problems
            if not problem.startswith("supervision_journal_unreadable:")
        ]
        if hard:
            return _row("supervision_sidecars", "fail", "; ".join(details))
        if len(hard) != len(problems):
            # The unreadable journal is genuinely three-valued: the row goes
            # unknown and TRIAGE CONTINUES — never a mid-run crash.
            return _row("supervision_sidecars", "unknown", "; ".join(details))
    else:
        details.append("no journal yet")
    return _row("supervision_sidecars", "pass", "; ".join(details))


# --- the doctor payload ---------------------------------------------------------------


def doctor(data_dir: Path) -> dict[str, Any]:
    """The seven-check triage payload: ``{"data_dir", "ok", "checks"}``.

    ``ok`` is no-fail AND no-unknown — the exit contract (0 iff ok) makes
    ``unknown`` a non-zero exit too (fork F1: scripts gating actions on
    doctor must not read an unverifiable pidfile as healthy, the same
    refusal ``start`` itself makes)."""
    data_dir = Path(data_dir)
    db = _db(data_dir)
    from benchweave.cli import lifecycle

    # One spelling (§0.3): status_lifecycle already derives the identity
    # verdict, hold + holder, and log destination; doctor MAPS that payload
    # onto rows so `status` and `doctor` can never disagree.
    snapshot = lifecycle.status_lifecycle(data_dir)
    rows = [
        _check_store(db),
        _check_hold(snapshot),
        _check_pid(snapshot),
        _check_env_file(data_dir),
        _check_unit(snapshot),
        _check_log_destination(data_dir, snapshot),
        _check_supervision_sidecars(db),
    ]
    ok = all(row["verdict"] == "pass" for row in rows)
    return {"data_dir": str(data_dir), "ok": ok, "checks": rows}


# --- logs (§2) ----------------------------------------------------------------------


def _resolve_logs_destination(db: Path) -> tuple[str, Any]:
    """The resolution ladder as one seam, from inputs only: the pidfile's
    ``log_destination`` field when a pidfile is present, else the
    ``<dir>.log`` sibling when it exists (the post-mortem rung — absent
    means never-served or cleanly-stopped; foreground serve writes a
    PRESENT stderr pidfile, and a crash LEAVES one for `stop` to clear),
    else nothing. A present pidfile whose field is missing falls through
    to the sibling: the family is the only remaining input."""
    record = supervision.read_pidfile(db)
    if record is not None:
        raw = record.get("log_destination")
        if isinstance(raw, str) and raw:
            return ("pidfile", raw)
    log = supervision.log_path(db)
    if log.is_file():
        return ("post_mortem", str(log))
    return ("none", None)


def _is_credential_destination(resolved: Path, credential: Path) -> bool:
    """The credential guard (the R3 fold, widened by W4): the pidfile
    field is operator-steerable through ``BENCHWEAVE_LOG_DESTINATION``
    and pointed at ``benchweave.env`` the tail would otherwise read the
    secret. The compare is ``(st_dev, st_ino)`` AFTER resolve — identity,
    not path equality — so it covers the symlink alias AND the hardlink
    and case-variant aliases (same inode, different spelling). What it
    covers: both rungs of the resolution ladder — the pidfile-named
    destination and the post-mortem ``<dir>.log`` sibling (a symlink or
    hardlink of the env file is refused wherever the tail would open
    it). What it does NOT catch: a copied (distinct-inode) credential
    file named like a log — only identity is refused, and a copy is a
    different file the tail may legitimately read."""
    try:
        destination = resolved.resolve().stat()
        secret = credential.resolve().stat()
    except OSError:
        # A path that cannot be stat'ed is not the credential (the tail
        # path reports its own typed unreadable/no-destination outcome).
        return False
    return (destination.st_dev, destination.st_ino) == (secret.st_dev, secret.st_ino)


def _tail_lines(path: Path, lines: int) -> list[str]:
    """The seek-bounded windowed tail: read from ``max(0, size - window)``,
    doubling on undercount up to ``TAIL_WINDOW_CAP_BYTES`` — windowed
    WITH a cap (a whole-file read happens only for a file inside the
    first window; the doubling never grows past the cap, so a blob that
    defeats line-splitting is refused, never read whole). Decode with
    ``errors="replace"`` (the ``_log_tail`` DECODE policy only — this
    helper improves on that one's whole-file read).

    The refusal rule (W1): when the windowed ladder cannot produce
    ``lines`` complete rows and the window had to grow past its first
    read window to get there — the ladder ended at the file start or at
    the cap — the requested lines cannot be served within the windowed
    tail: typed :data:`LOGS_WINDOW_CAP`. A file that fits the first
    window and simply has fewer lines than requested returns what it has
    (the standard short-file tail)."""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        window = TAIL_WINDOW_BYTES
        while True:
            offset = max(0, size - window)
            handle.seek(offset)
            text = handle.read().decode("utf-8", errors="replace")
            # CRLF-honest: a Windows-written log carries \r\n; strip the
            # one trailing \r per row so callers compare content, not
            # line endings.
            rows = [row.removesuffix("\r") for row in text.split("\n")]
            if offset > 0 and rows:
                rows = rows[1:]  # the leading partial line at a mid-file seek
            if rows and rows[-1] == "":
                rows.pop()  # the final newline's empty remainder
            if len(rows) >= lines:
                return rows[-lines:]
            if offset == 0 or window >= TAIL_WINDOW_CAP_BYTES:
                if window > TAIL_WINDOW_BYTES:
                    raise DiagnoseError(
                        f"{LOGS_WINDOW_CAP} the requested {lines} line(s) "
                        "cannot be served within the windowed read "
                        f"(window cap {TAIL_WINDOW_CAP_BYTES // (1024 * 1024)} "
                        f"MiB; {path}) — the file has fewer complete lines "
                        "than requested beyond the first read window; try a "
                        "smaller --lines"
                    )
                return rows[-lines:]
            window = min(window * 2, TAIL_WINDOW_CAP_BYTES)


def _file_tail(path: Path, lines: int, *, post_mortem: bool) -> dict[str, Any]:
    try:
        tailed = _tail_lines(path, lines)
    except OSError as error:
        raise DiagnoseError(
            f"{LOGS_UNREADABLE} cannot tail {path}: {error}"
        ) from error
    payload: dict[str, Any] = {"destination": str(path), "lines": tailed}
    if post_mortem:
        payload["post_mortem"] = True
    return payload


def _resolve_journalctl() -> Path | None:
    """PATH-resolve journalctl (None where the host has none — the typed
    degrade's trigger)."""
    found = shutil.which("journalctl")
    return Path(found) if found else None


def _journal_tail(lines: int) -> dict[str, Any]:
    """The journalctl rung (fixed argv, bounded timeout — the atrest
    whoami/icacls subprocess precedent). The real read cannot run in CI
    (no systemd user session): X4's argv pin plus this typed refusal are
    the evidence, and the first real systemd deployment corroborates."""
    binary = _resolve_journalctl()
    if binary is None:
        raise DiagnoseError(
            f"{LOGS_JOURNAL_UNAVAILABLE} journalctl is not resolvable on "
            f"this host — cannot read the {JOURNAL_UNIT} unit's journal "
            "(run `logs` on the systemd host, or `journalctl -u "
            f"{JOURNAL_UNIT}` there)"
        )
    argv = [str(binary), "--no-pager", "-n", str(lines), "-u", JOURNAL_UNIT]
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, resolved binary
            argv,
            capture_output=True,
            text=True,
            timeout=JOURNALCTL_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise DiagnoseError(
            f"{LOGS_JOURNAL_UNAVAILABLE} journalctl did not answer within "
            f"{JOURNALCTL_TIMEOUT_S:.0f}s for unit {JOURNAL_UNIT}"
        ) from error
    except OSError as error:
        raise DiagnoseError(
            f"{LOGS_JOURNAL_UNAVAILABLE} journalctl could not be executed "
            f"({error}) — unit {JOURNAL_UNIT}"
        ) from error
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        raise DiagnoseError(
            f"{LOGS_JOURNAL_UNAVAILABLE} journalctl exited "
            f"rc={completed.returncode} for unit {JOURNAL_UNIT}"
            + (f": {detail[0]}" if detail else "")
        )
    return {
        "destination": "journal",
        "unit": JOURNAL_UNIT,
        "lines": completed.stdout.splitlines(),
    }


def logs(data_dir: Path, lines: int) -> dict[str, Any]:
    """Tail the named destination for ``data_dir`` (§2's ladder).

    Raises :class:`DiagnoseError` on every typed refusal; returns the
    ``{destination, unit?, lines, post_mortem?}`` payload otherwise. No
    ``--follow`` (deferred: streaming needs subprocess lifecycle +
    interrupt semantics + a Windows story; ``tail -f`` / ``journalctl -f``
    exist and the operator has them)."""
    if not isinstance(lines, int) or isinstance(lines, bool) or lines <= 0:
        raise DiagnoseError(
            f"{LOGS_LINES_DOMAIN} --lines must be a positive integer "
            f"(got {lines!r})"
        )
    data_dir = Path(data_dir)
    db = _db(data_dir)
    kind, dest = _resolve_logs_destination(db)
    if kind == "none":
        raise DiagnoseError(
            f"{LOGS_NO_DESTINATION} no pidfile names a destination and no "
            f"sibling log exists for {data_dir} — never served, or served "
            "with no log file; nothing to tail"
        )
    if kind == "pidfile":
        raw = str(dest)
        if raw == "journal":
            return _journal_tail(lines)
        if raw == "stderr":
            raise DiagnoseError(
                f"{LOGS_DESTINATION_STDERR} the daemon was started "
                "foreground (its bytes went to a terminal this command "
                "cannot recover) or the pidfile predates journal detection "
                f"— under systemd try: journalctl -u {JOURNAL_UNIT}"
            )
        path = Path(raw)
        credential = data_dir / CREDENTIAL_FILE
        if _is_credential_destination(path, credential):
            raise DiagnoseError(
                f"{LOGS_DESTINATION_CREDENTIAL} the resolved destination "
                f"is the credential file ({credential}) — the pidfile's "
                "log_destination is steerable through "
                "BENCHWEAVE_LOG_DESTINATION and is refused as a tail "
                "source; point it back at the <dir>.log sibling"
            )
        return _file_tail(path, lines, post_mortem=False)
    # W4: the post-mortem rung rides the same guard — a <dir>.log symlink
    # or hardlink of the env file is the credential however it is named.
    sibling = Path(str(dest))
    credential = data_dir / CREDENTIAL_FILE
    if _is_credential_destination(sibling, credential):
        raise DiagnoseError(
            f"{LOGS_DESTINATION_CREDENTIAL} the resolved destination is "
            f"the credential file ({credential}) — a <dir>.log that is a "
            "symlink or hardlink of it is refused as a tail source; point "
            "the log at a real log file"
        )
    return _file_tail(sibling, lines, post_mortem=True)
