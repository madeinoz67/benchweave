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

``logs`` (§2) tails the named destination; it lands in this module with
its own slice. Both verbs emit key NAMES and paths only — never env-file
values or token material.
"""

from __future__ import annotations

import json
import sqlite3
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
    problem the caller maps to the row's ``unknown`` verdict."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return ([f"supervision_journal_unreadable: cannot read it: {error}"], [])
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
            if index == len(lines) - 1:
                notes.append(
                    "the journal's final line is torn — the known crash-tear "
                    "shape (appends are single-write+fsync)"
                )
            else:
                problems.append(
                    f"the journal's line {index + 1} is unparseable — "
                    "mid-file tears cannot occur by construction (appends "
                    "are single-write+fsync), so this is tampering"
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
