"""Issue #422 increment 4 — ``doctor`` and ``logs`` (the triage verbs).

The arms follow the pre-committed acceptance rule in
`.claude/deep-review/2026-10-09-issue422-inc4-doctor-logs-design.md` §5
(the gate authority): G1-G11 + X1-X6 plus the RED controls (a)-(g).
Every arm is a staged-sidecar ``CliRunner`` arm or an in-process
composition (the record §0.4 promise: zero new real-subprocess daemons —
the one live-daemon property that matters, doctor working while the store
is held, is proven by holding a REAL ``StoreHold`` in this test process).

The RED controls are the fluff-proof part: each neutralizes ONE mechanism
at one site and asserts the corresponding arm's typed expectation is then
VIOLATED — an arm that stays green while its mechanism is neutralized
tests nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from click.testing import CliRunner, Result

from benchweave.cli import atrest
from benchweave.cli.commands import cli

REPO = Path(__file__).resolve().parents[2]
POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX mode bits; W1 residual"
)


# --- harness (the test_lifecycle.py L6 patterns) ---------------------------------


def _db(data_dir: Path) -> Path:
    return data_dir / atrest.DB_NAME


def _write_pidfile(data_dir: Path, payload: dict[str, Any]) -> Path:
    """Hand-write a pidfile sidecar the way a stale/tampered one looks."""
    from benchweave.supervision import pid_path

    path = pid_path(_db(data_dir))
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _hold_with_body(data_dir: Path, body: dict[str, Any]) -> Any:
    """Acquire the real hold, then rewrite the advisory BODY the way a
    gateway-written sidecar reads (the lock is real; the body is staged)."""
    from benchweave.state.hold import StoreHold, hold_path

    hold = StoreHold(_db(data_dir), label=str(body.get("label", "gateway gw-x")))
    hold.acquire()
    hold_path(_db(data_dir)).write_text(json.dumps(body), encoding="utf-8")
    return hold


@contextmanager
def _dead_pid() -> Iterator[int]:
    """A REAL exited process's pid (waited, so it is not a zombie we own)."""
    dead = subprocess.Popen(
        [sys.executable, "-c", "pass"], stdout=subprocess.DEVNULL
    )
    dead.wait(timeout=10)
    try:
        yield dead.pid
    finally:
        pass  # nothing to clean: the process has exited and been reaped


@contextmanager
def _live_child() -> Iterator[int]:
    """A REAL unrelated live process (its pid resolves to probe + ticks)."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait(timeout=10)


def _combined(result: Result) -> str:
    """stdout + stderr, robust to click < 8.2's mixed-stream Result."""
    try:
        return result.output + result.stderr
    except ValueError:
        return result.output


def _doctor(data_dir: Path, *extra: str) -> Result:
    return CliRunner().invoke(cli, ["doctor", "--data-dir", str(data_dir), *extra])


def _payload(result: Result) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(result.output))


def _row(payload: dict[str, Any], check: str) -> dict[str, Any]:
    matches = cast(
        list[dict[str, Any]],
        [row for row in payload["checks"] if row["check"] == check],
    )
    assert len(matches) == 1, f"expected exactly one {check!r} row: {payload['checks']}"
    return matches[0]


def _setup_store(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    atrest.setup(data_dir)


# --- G1: empty data dir -----------------------------------------------------------


def test_g1_empty_data_dir_fails_the_store_row(tmp_path: Path) -> None:
    """G1: no store at all — D1 fails, ok=false, exit 1; every other row
    still reports (triage completes)."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    payload = _payload(result)
    assert payload["ok"] is False
    assert _row(payload, "store")["verdict"] == "fail"
    assert len(payload["checks"]) == 7, payload["checks"]


# --- G2: healthy at-rest + the structural read-only pin ---------------------------


#: The enumerated sidecar family the read-only pin walks (§5 G2, R1 fold):
#: the four in-dir names plus the five siblings beside the data dir —
#: ``.hold`` included (W6): doctor taking the store hold is the KILL
#: criterion's own example, and the pin must see that path appear.
_FAMILY_IN_DIR = (
    atrest.DB_NAME,
    atrest.DB_NAME + "-wal",
    atrest.DB_NAME + "-shm",
    atrest.CREDENTIAL_FILE,
)
_FAMILY_SIBLINGS = (".pid", ".stop", ".log", ".supervision.jsonl", ".hold")


def _family_snapshot(data_dir: Path) -> dict[str, tuple[bool, int]]:
    snapshot: dict[str, tuple[bool, int]] = {}
    for name in _FAMILY_IN_DIR:
        path = data_dir / name
        snapshot[name] = (path.exists(), path.stat().st_mtime_ns if path.exists() else 0)
    for suffix in _FAMILY_SIBLINGS:
        path = data_dir.parent / (data_dir.name + suffix)
        snapshot[suffix] = (
            path.exists(),
            path.stat().st_mtime_ns if path.exists() else 0,
        )
    return snapshot


def _read_only_pin_violations(
    before: dict[str, tuple[bool, int]], after: dict[str, tuple[bool, int]]
) -> list[str]:
    """The structural read-only pin over the ENUMERATED family (§5 G2,
    R1 fold): existing files' mtimes unchanged, and no path appears
    beyond the disclosed empty ``-shm``/``-wal`` pair."""
    violations: list[str] = []
    disclosed = {atrest.DB_NAME + "-wal", atrest.DB_NAME + "-shm"}
    for name, (was, mtime) in before.items():
        now_exists, now_mtime = after[name]
        if was:
            if not now_exists:
                violations.append(f"{name} vanished across the doctor run")
            elif now_mtime != mtime:
                violations.append(f"{name} mtime moved across the run")
        elif now_exists and name not in disclosed:
            violations.append(f"{name} appeared beyond the disclosed sidecar pair")
    return violations


def test_g2_healthy_at_rest_all_pass_and_writes_nothing(tmp_path: Path) -> None:
    """G2: a real at-rest store (env file 0600, no pidfile, hold free) —
    every row passes, exit 0, and across the run the enumerated family's
    existing mtimes are unchanged with no new file beyond the disclosed
    empty ``-shm``/``-wal`` pair (the structural read-only pin, R1 fold)."""
    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    before = _family_snapshot(data_dir)
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 0, _combined(result)
    payload = _payload(result)
    assert payload["ok"] is True
    for row in payload["checks"]:
        assert row["verdict"] == "pass", row
    after = _family_snapshot(data_dir)
    assert _read_only_pin_violations(before, after) == []
    # The setup-written secret never reaches doctor output (G0 discipline).
    secret = atrest.read_secret(data_dir)
    assert secret not in _combined(result)


# --- G3: coherent live, in-process (works while the store is held) ----------------


def test_g3_coherent_live_in_process_passes_under_the_hold(tmp_path: Path) -> None:
    """G3: a real pidfile naming THIS process + a real StoreHold with a
    ``gateway `` label whose pid matches — D3 ours, D2 held, D1 integrity
    UNDER the held flock (triage works while live), exit 0."""
    from benchweave import supervision
    from benchweave.state.hold import StoreHold

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    db = _db(data_dir)
    log = supervision.log_path(db)
    log.write_text("serve line\n", encoding="utf-8")
    supervision.write_pidfile(db, gateway_id="gw-x", log_destination=str(log))
    hold = StoreHold(db, label="gateway gw-x")
    hold.acquire()
    try:
        result = _doctor(data_dir, "--json")
    finally:
        hold.release()
        supervision.remove_pidfile(db)
    assert result.exit_code == 0, _combined(result)
    payload = _payload(result)
    assert payload["ok"] is True
    assert _row(payload, "pid")["verdict"] == "pass"
    assert _row(payload, "hold")["verdict"] == "pass"
    assert _row(payload, "store")["verdict"] == "pass"
    assert _row(payload, "log_destination")["verdict"] == "pass"


# --- G4/G5/G6: the identity lattice rows ------------------------------------------


def test_g4_desync_fails_naming_both_pids(tmp_path: Path) -> None:
    """G4: pidfile self + gateway-label hold naming a DIFFERENT pid — D3
    fails with ``supervision_hold_desync:`` naming both pids; exit 1."""
    from benchweave import supervision

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    db = _db(data_dir)
    supervision.write_pidfile(
        db, gateway_id="gw-x", log_destination="stderr"
    )
    other_pid = os.getpid() + 40000
    hold = _hold_with_body(
        data_dir,
        {"pid": other_pid, "label": "gateway gw-x",
         "acquired_at": "2026-10-09T00:00:00Z"},
    )
    try:
        result = _doctor(data_dir, "--json")
    finally:
        hold.release()
        supervision.remove_pidfile(db)
    assert result.exit_code == 1, _combined(result)
    payload = _payload(result)
    row = _row(payload, "pid")
    assert row["verdict"] == "fail"
    assert "supervision_hold_desync:" in row["detail"]
    assert str(os.getpid()) in row["detail"] and str(other_pid) in row["detail"]


def test_g5_not_ours_fails_stale_pid(tmp_path: Path, live_child: int) -> None:
    """G5: the pidfile names a live pid whose recorded start time DIFFERS
    (pid reuse) — D3 fails with ``supervision_stale_pid:``; exit 1."""
    from benchweave import supervision

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    _write_pidfile(
        data_dir,
        {
            "pid": live_child,
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": (supervision.process_start_ticks(live_child) or 0) + 1,
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    row = _row(_payload(result), "pid")
    assert row["verdict"] == "fail"
    assert "supervision_stale_pid:" in row["detail"]


def test_g6_unknown_exits_one(tmp_path: Path, live_child: int,
                              monkeypatch: pytest.MonkeyPatch) -> None:
    """G6: the pidfile names a live pid whose start time cannot be read
    (ticks unobtainable, hold free) — D3 reports ``unknown`` and doctor
    EXITS 1: the load-bearing unknown-exits-nonzero pin (fork F1)."""
    from benchweave import supervision

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    _write_pidfile(
        data_dir,
        {
            "pid": live_child,
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    monkeypatch.setattr(supervision, "process_start_ticks", lambda pid: None)
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    payload = _payload(result)
    row = _row(payload, "pid")
    assert row["verdict"] == "unknown"
    assert "supervision_pid_unknown:" in row["detail"]
    assert payload["ok"] is False


# --- G7/G8: the env-file rows ------------------------------------------------------


@POSIX_ONLY
def test_g7_group_readable_env_file_fails_and_never_prints_the_secret(
    tmp_path: Path,
) -> None:
    """G7: chmod 0644 on the credential file — D4 fails (the shared perms
    discipline serve itself applies) and the setup-written secret never
    reaches combined output. POSIX-only provocation (mode bits; on Windows
    the check is skip-with-disclosure, the atrest #137 posture)."""
    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    (data_dir / atrest.CREDENTIAL_FILE).chmod(0o644)
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    row = _row(_payload(result), "env_file")
    assert row["verdict"] == "fail"
    assert "env_file:" in row["detail"]
    secret = atrest.read_secret(data_dir)
    assert secret not in _combined(result)


def test_g8_non_allowlisted_key_fails_previewing_serve(tmp_path: Path) -> None:
    """G8: an env file carrying a non-allowlisted key — D4 fails with the
    ``env_file:`` prefix family (doctor previews the next boot's own
    refusal: the SAME validation call serve makes, one spelling)."""
    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    env = data_dir / atrest.CREDENTIAL_FILE
    env.write_text("BENCHWEAVE_NOT_AN_ALLOWLISTED_KEY=hello\n", encoding="utf-8")
    env.chmod(0o600)
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    row = _row(_payload(result), "env_file")
    assert row["verdict"] == "fail"
    assert "env_file:" in row["detail"]
    assert "BENCHWEAVE_NOT_AN_ALLOWLISTED_KEY" in row["detail"]
    assert "hello" not in _combined(result), "values never reach output"


# --- G9: the corrupt store ---------------------------------------------------------


def test_g9_garbage_store_fails_the_integrity_row(tmp_path: Path) -> None:
    """G9: garbage bytes as state.sqlite — D1 fails through the
    cannot-open/integrity path; exit 1; never a traceback."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    (data_dir / atrest.DB_NAME).write_bytes(b"this is not a sqlite database")
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    row = _row(_payload(result), "store")
    assert row["verdict"] == "fail"
    assert "Traceback" not in _combined(result)


# --- G10/G11: the supervision-sidecar rows -----------------------------------------


def _journal_row(event: str) -> str:
    return json.dumps({"wall": "2026-10-09T00:00:00Z", "event": event})


def test_g10_journal_torn_final_passes_torn_midfile_fails(tmp_path: Path) -> None:
    """G10: a torn FINAL journal line is the known crash-tear shape — pass
    with note, exit 0; a torn NON-final line is only reachable by tampering
    (appends are single-write+fsync, mid-file tears cannot occur by
    construction) — fail, exit 1."""
    from benchweave import supervision

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    journal = supervision.journal_path(_db(data_dir))
    # Cell 1: valid rows + a torn FINAL line.
    journal.write_text(
        _journal_row("start_requested") + "\n"
        + _journal_row("started") + "\n"
        + '{"wall": "2026-10-09T00:00:01Z", "even',
        encoding="utf-8",
    )
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 0, _combined(result)
    row = _row(_payload(result), "supervision_sidecars")
    assert row["verdict"] == "pass", row
    assert "torn" in row["detail"].lower(), "the crash-tear note is carried"
    # Cell 2: a torn NON-final line.
    journal.write_text(
        '{"wall": "2026-10-09T00:00:01Z", "even\n'
        + _journal_row("started") + "\n",
        encoding="utf-8",
    )
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    row = _row(_payload(result), "supervision_sidecars")
    assert row["verdict"] == "fail"
    assert "tamper" in row["detail"].lower(), row


def test_g11_stale_stop_request_passes_naming_start(tmp_path: Path) -> None:
    """G11: a stale stop request targeting a dead pid — D7 passes with the
    note naming ``start`` as the cleaner (start clears unconsumed
    requests); exit 0."""
    from benchweave import supervision

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    with _dead_pid() as dead:
        supervision.write_stop_request(
            _db(data_dir), mode="plain", actor_pid=4242, target_pid=dead
        )
        result = _doctor(data_dir, "--json")
    assert result.exit_code == 0, _combined(result)
    row = _row(_payload(result), "supervision_sidecars")
    assert row["verdict"] == "pass", row
    assert "start" in row["detail"], "the note names the cleaner verb"


# --- the doctor plain-output shape --------------------------------------------------


def test_doctor_plain_output_is_one_line_per_row_plus_summary(tmp_path: Path) -> None:
    """The plain contract (§1.2): one ``doctor: <check> <verdict> <detail>``
    line per row plus a summary; ``--json`` is the machine contract."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    result = _doctor(data_dir)
    assert result.exit_code == 1, _combined(result)
    lines = [line for line in result.output.splitlines() if line.startswith("doctor:")]
    assert len(lines) == 8, lines  # seven rows + the summary line
    assert any(line.startswith("doctor: store fail ") for line in lines), lines
    assert any(line.startswith("doctor: not ok") for line in lines), lines


# --- RED controls: each neutralizes ONE mechanism, one site ------------------------


@POSIX_ONLY
def test_control_a_neutralized_perms_check_breaks_g7(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control (a): with the 0600 perms discipline neutralized (the shared
    ``_check_owner_only`` site serve and doctor both ride), the G7 scenario
    no longer produces its D4-fail — G7 would be red. The arm therefore
    tests the mechanism, not the fixture."""
    from benchweave.cli import env_file

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    (data_dir / atrest.CREDENTIAL_FILE).chmod(0o644)
    monkeypatch.setattr(env_file, "_check_owner_only", lambda path: None)
    result = _doctor(data_dir, "--json")
    assert _row(_payload(result), "env_file")["verdict"] != "fail"


def test_control_b_neutralized_integrity_probe_breaks_g9(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control (b): with the integrity probe forced clean, the G9 scenario
    no longer produces its D1-fail — G9 would be red."""
    from benchweave.cli import diagnose

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    (data_dir / atrest.DB_NAME).write_bytes(b"this is not a sqlite database")
    monkeypatch.setattr(diagnose, "_store_integrity_problems", lambda db: [])
    result = _doctor(data_dir, "--json")
    assert _row(_payload(result), "store")["verdict"] != "fail"


def test_control_c_neutralized_identity_verdict_breaks_g4_g5_g6(
    tmp_path: Path, live_child: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control (c): with the identity lattice forced to ``ours`` (the one
    verdict site status_lifecycle resolves at call time), none of the
    G4/G5/G6 scenarios produce their fail/unknown rows — all three arms
    would be red."""
    from benchweave import supervision

    monkeypatch.setattr(
        supervision,
        "verify_gateway_identity",
        lambda db, **kwargs: supervision.IdentityVerdict(
            "ours", os.getpid(), None, None, "running (ours — neutralized)"
        ),
    )
    # G4's shape: self pidfile + gateway-label hold naming another pid.
    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    supervision.write_pidfile(
        _db(data_dir), gateway_id="gw-x", log_destination="stderr"
    )
    hold = _hold_with_body(
        data_dir,
        {"pid": os.getpid() + 40000, "label": "gateway gw-x",
         "acquired_at": "2026-10-09T00:00:00Z"},
    )
    try:
        result = _doctor(data_dir, "--json")
    finally:
        hold.release()
    row = _row(_payload(result), "pid")
    assert row["verdict"] not in ("fail", "unknown")
    # G5's shape: mismatched ticks against a live pid.
    _write_pidfile(
        data_dir,
        {
            "pid": live_child,
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    result = _doctor(data_dir, "--json")
    assert _row(_payload(result), "pid")["verdict"] not in ("fail", "unknown")
    # G6's exit-contract leg: unknown is unreachable under the neutralization.
    assert _doctor(data_dir).exit_code != 1 or _row(
        _payload(_doctor(data_dir, "--json")), "pid"
    )["verdict"] != "unknown"


def test_control_g_neutralized_journal_check_breaks_g10(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control (g): with the journal-parse check forced clean, the G10
    torn-midfile scenario no longer produces its D7-fail — G10 would be
    red."""
    from benchweave import supervision
    from benchweave.cli import diagnose

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    supervision.journal_path(_db(data_dir)).write_text(
        '{"wall": "2026-10-09T00:00:01Z", "even\n' + _journal_row("started") + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(diagnose, "_journal_problems", lambda path: ([], []))
    result = _doctor(data_dir, "--json")
    assert _row(_payload(result), "supervision_sidecars")["verdict"] != "fail"


# --- the live_child fixture (shared with the G5/G6/control-c arms) ------------------


@pytest.fixture()
def live_child() -> Iterator[int]:
    with _live_child() as pid:
        yield pid


# --- X1-X6: the logs verb ------------------------------------------------------------


def _logs(data_dir: Path, *extra: str) -> Result:
    return CliRunner().invoke(cli, ["logs", "--data-dir", str(data_dir), *extra])


def _stage_log(db: Path, count: int, width: int = 700) -> Path:
    """A staged <dir>.log whose last ``--lines`` tail spans MORE than the
    64 KiB first window (so the doubling rung is exercised, not skipped)."""
    log = supervision_log_path(db)
    lines = [f"line-{index:04d}-" + "x" * width for index in range(count)]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


def supervision_log_path(db: Path) -> Path:
    from benchweave import supervision

    return supervision.log_path(db)


def test_x1_windowed_tail_returns_exactly_the_last_n(tmp_path: Path) -> None:
    """X1: a staged <dir>.log larger than the tail window + a pidfile with
    a path destination, ``--lines 100`` — exactly the last 100 lines, and
    the ``--json`` shape is ``{destination, lines}``."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    db = _db(data_dir)
    log = _stage_log(db, count=400)
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": str(log),
            "schema": 1,
        },
    )
    result = _logs(data_dir, "--lines", "100", "--json")
    assert result.exit_code == 0, _combined(result)
    payload = _payload(result)
    assert payload["destination"] == str(log)
    assert len(payload["lines"]) == 100
    assert payload["lines"][0].startswith("line-0300-"), payload["lines"][0][:20]
    assert payload["lines"][-1].startswith("line-0399-"), payload["lines"][-1][:20]
    assert "post_mortem" not in payload
    # The plain surface prints the tail's lines themselves.
    plain = _logs(data_dir, "--lines", "100")
    assert plain.exit_code == 0, _combined(plain)
    printed = [line for line in plain.output.splitlines() if line]
    assert printed[-1].startswith("line-0399-")
    assert len(printed) == 100


def test_x1b_lines_domain_is_typed(tmp_path: Path) -> None:
    """The R8-fold ``--lines`` domain: zero and negative are typed
    ``logs_lines_domain:`` refusals — never a silent default, never a
    traceback."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    db = _db(data_dir)
    _stage_log(db, count=5)
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": str(supervision_log_path(db)),
            "schema": 1,
        },
    )
    for bad in ("0", "-3"):
        result = _logs(data_dir, "--lines", bad)
        assert result.exit_code == 1, _combined(result)
        assert "logs_lines_domain:" in _combined(result), _combined(result)
        assert "Traceback" not in _combined(result)


def test_x2_pidfile_absent_tails_post_mortem(tmp_path: Path) -> None:
    """X2: no pidfile + a present <dir>.log — the post-mortem tail, with
    the resolution REPORTED as post-mortem (the JSON flag and the plain
    note both carry it)."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    log = _stage_log(_db(data_dir), count=5)
    result = _logs(data_dir, "--json")
    assert result.exit_code == 0, _combined(result)
    payload = _payload(result)
    assert payload["destination"] == str(log)
    assert payload["post_mortem"] is True
    assert payload["lines"][-1].startswith("line-0004-")
    plain = _logs(data_dir)
    assert plain.exit_code == 0, _combined(plain)
    assert "post-mortem" in _combined(plain)
    assert any(line.startswith("line-0004-") for line in plain.output.splitlines())


def test_x3_stderr_destination_refuses_typed(tmp_path: Path) -> None:
    """X3: destination ``stderr`` — the typed refusal naming the journalctl
    alternative; exit 1."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    result = _logs(data_dir)
    assert result.exit_code == 1, _combined(result)
    assert "logs_destination_stderr:" in _combined(result)
    assert "journalctl -u benchweave" in _combined(result)


def test_x4_journal_destination_pins_the_fixed_argv_and_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """X4: destination ``journal`` — with the resolver stubbed present the
    EXACT fixed argv is asserted (the real journalctl read cannot run in
    CI: no systemd user session — the argv pin plus the typed refusal are
    the evidence); with the resolver stubbed absent the typed
    ``logs_journal_unavailable:`` refusal fires."""
    from benchweave.cli import diagnose

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": "journal",
            "schema": 1,
        },
    )
    captured: dict[str, list[str]] = {}

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = list(argv)
        return subprocess.CompletedProcess(list(argv), 0, stdout="j1\nj2\n", stderr="")

    monkeypatch.setattr(diagnose, "_resolve_journalctl", lambda: Path("/stub/journalctl"))
    # diagnose's own `import subprocess` is this same module object — the
    # patch reaches the journalctl leg without naming a non-exported attr.
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _logs(data_dir, "--lines", "7", "--json")
    assert result.exit_code == 0, _combined(result)
    assert captured["argv"] == [
        "/stub/journalctl", "--no-pager", "-n", "7", "-u", "benchweave",
    ], captured["argv"]
    payload = _payload(result)
    assert payload["destination"] == "journal"
    assert payload["unit"] == "benchweave"
    assert payload["lines"] == ["j1", "j2"]
    # The absent half: degrade loudly, typed.
    monkeypatch.setattr(diagnose, "_resolve_journalctl", lambda: None)
    result = _logs(data_dir)
    assert result.exit_code == 1, _combined(result)
    assert "logs_journal_unavailable:" in _combined(result)
    assert "benchweave" in _combined(result), "the refusal names the unit"


@POSIX_ONLY
def test_x5_unreadable_destination_refuses_typed(tmp_path: Path) -> None:
    """X5: a destination path with mode 000 — the typed
    ``logs_unreadable:`` refusal, never a traceback (POSIX-only
    provocation: mode bits; W1 residual)."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    locked = data_dir / "locked.log"
    locked.write_text("secret-ish bytes\n", encoding="utf-8")
    locked.chmod(0o000)
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": str(locked),
            "schema": 1,
        },
    )
    try:
        result = _logs(data_dir)
        assert result.exit_code == 1, _combined(result)
        assert "logs_unreadable:" in _combined(result)
        assert "Traceback" not in _combined(result)
    finally:
        locked.chmod(0o600)


def test_x6_credential_destination_refuses_typed(tmp_path: Path) -> None:
    """X6: a staged pidfile whose log_destination names the env file — the
    typed ``logs_destination_credential:`` refusal naming the env-file
    class (the R3 fold: the pidfile field is operator-steerable through
    BENCHWEAVE_LOG_DESTINATION and rung 1 must not tail the secret); the
    SECRET is absent from combined output; exit 1."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    env = data_dir / atrest.CREDENTIAL_FILE
    secret = "tok-do-not-print-5f3a"
    env.write_text(f"BENCHWEAVE_SECRET={secret}\n", encoding="utf-8")
    env.chmod(0o600)
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": str(env),
            "schema": 1,
        },
    )
    result = _logs(data_dir)
    assert result.exit_code == 1, _combined(result)
    assert "logs_destination_credential:" in _combined(result)
    assert secret not in _combined(result)
    # --json refuses identically (the machine contract refuses too).
    json_result = _logs(data_dir, "--json")
    assert json_result.exit_code == 1, _combined(json_result)
    assert secret not in _combined(json_result)


def test_control_d_neutralized_resolution_breaks_x3_x4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control (d): with the destination resolution forced to the .log
    path, neither X3's stderr refusal nor X4's journalctl leg fires — both
    arms would be red (the typed refusals depend on the resolution
    ladder)."""
    from benchweave.cli import diagnose

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    _stage_log(_db(data_dir), count=5)
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": "stderr",
            "schema": 1,
        },
    )
    monkeypatch.setattr(
        diagnose,
        "_resolve_logs_destination",
        lambda db: ("pidfile", str(supervision_log_path(db))),
    )
    result = _logs(data_dir)
    assert "logs_destination_stderr:" not in _combined(result)
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": "journal",
            "schema": 1,
        },
    )
    result = _logs(data_dir)
    assert "logs_journal_unavailable:" not in _combined(result)
    assert result.exit_code == 0, _combined(result)  # it tailed instead


def test_control_f_neutralized_credential_guard_breaks_x6(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control (f): with the credential guard neutralized (the path is
    forced open), X6's scenario produces NO refusal and would tail the
    credential file — X6 would be red, and the guard is what stands
    between the operator and the secret."""
    from benchweave.cli import diagnose

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    env = data_dir / atrest.CREDENTIAL_FILE
    secret = "tok-do-not-print-5f3a"
    env.write_text(f"BENCHWEAVE_SECRET={secret}\n", encoding="utf-8")
    env.chmod(0o600)
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": str(env),
            "schema": 1,
        },
    )
    monkeypatch.setattr(diagnose, "_is_credential_destination", lambda resolved, credential: False)
    result = _logs(data_dir)
    assert "logs_destination_credential:" not in _combined(result)
    assert result.exit_code == 0, _combined(result)  # the tail proceeded


# --- W1: the tail cap (critic + gw1 F3) -------------------------------------------


def _stage_giant_line(db: Path, size: int) -> Path:
    """A staged ``<dir>.log`` whose ONLY line is ``size`` bytes and carries
    no newline — the blob shape the windowed tail must refuse, not dump."""
    log = supervision_log_path(db)
    log.write_bytes(b"x" * size)
    return log


def _destination_pidfile(data_dir: Path, destination: str) -> None:
    _write_pidfile(
        data_dir,
        {
            "pid": os.getpid(),
            "gateway_id": "gw-x",
            "data_dir": str(data_dir),
            "started_wall": "2026-10-09T00:00:00Z",
            "started_ticks": 1,
            "log_destination": destination,
            "schema": 1,
        },
    )


def test_w1a_giant_single_line_refuses_the_fifty_line_request(tmp_path: Path) -> None:
    """W1 RED arm 1: a no-newline giant file (300 KiB single-line) +
    ``--lines 50`` — the requested lines cannot be served within the
    windowed tail, so a typed ``logs_window_cap:`` refusal, exit 1, and
    the blob's bytes never reach output (today the whole file lands in
    memory and is returned as the tail)."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    db = _db(data_dir)
    log = _stage_giant_line(db, 300 * 1024)
    _destination_pidfile(data_dir, str(log))
    result = _logs(data_dir, "--lines", "50")
    assert result.exit_code == 1, _combined(result)
    assert "logs_window_cap:" in _combined(result), _combined(result)
    assert "Traceback" not in _combined(result)
    assert "x" * 100 not in _combined(result), "the blob never reaches output"


def test_w1b_dense_blob_refuses_within_one_doubling_cycle_of_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W1 RED arm 2: a dense 5 MiB no-newline file + ``--lines 50`` — the
    typed refusal fires within one doubling cycle of the window cap: the
    tail never reads past ``TAIL_WINDOW_CAP_BYTES`` in one read, and the
    cumulative windowed reads stay under ``2 x`` the cap (the geometric
    series up to the cap)."""
    from benchweave.cli import diagnose

    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    db = _db(data_dir)
    log = _stage_giant_line(db, 5 * 1024 * 1024)
    _destination_pidfile(data_dir, str(log))
    reads: list[int] = []
    real_open = Path.open

    def counting_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        handle = real_open(self, *args, **kwargs)
        real_read = handle.read

        def counting_read(size: int = -1) -> bytes:
            data = real_read(size)
            reads.append(len(data))
            return cast(bytes, data)

        handle.read = counting_read
        return handle

    monkeypatch.setattr(Path, "open", counting_open)
    result = _logs(data_dir, "--lines", "50")
    assert result.exit_code == 1, _combined(result)
    assert "logs_window_cap:" in _combined(result), _combined(result)
    assert reads, "the windowed tail read something"
    assert max(reads) <= diagnose.TAIL_WINDOW_CAP_BYTES, max(reads)
    assert sum(reads) <= 2 * diagnose.TAIL_WINDOW_CAP_BYTES, sum(reads)


def test_w1c_short_log_still_returns_what_it_has(tmp_path: Path) -> None:
    """The short-file undercount stays the standard tail (the X2/S8-2
    pin): a file inside the first read window with fewer lines than
    requested returns its lines — the window cap refuses only where the
    windowed read cannot serve the request (a grown window)."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    log = _stage_log(_db(data_dir), count=5)
    _destination_pidfile(data_dir, str(log))
    result = _logs(data_dir, "--lines", "50", "--json")
    assert result.exit_code == 0, _combined(result)
    assert len(_payload(result)["lines"]) == 5


# --- W2: the env-file stat race (critic) ------------------------------------------


def test_w2_env_file_stat_race_fails_the_row_and_triage_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W2 (critic): the delete-in-window race — the env file disappears
    between ``is_file()`` and the ``path.stat()`` inside
    ``_check_owner_only``. Today that OSError escapes the EnvFileError
    catch and crashes doctor with zero rows; the fix turns it into a FAIL
    row and triage continues (all seven rows emitted)."""
    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    env = data_dir / atrest.CREDENTIAL_FILE
    real_stat = Path.stat
    seen: list[str] = []

    def racing_stat(self: Path, *args: object, **kwargs: object) -> Any:
        if self == env:
            seen.append("stat")
            if len(seen) >= 2:
                # The file vanished in the is_file -> stat window.
                raise FileNotFoundError(str(self))
        return real_stat(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "stat", racing_stat)
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    payload = _payload(result)
    assert len(payload["checks"]) == 7, payload["checks"]
    row = _row(payload, "env_file")
    assert row["verdict"] == "fail"
    assert "Traceback" not in _combined(result)


# --- W3: the torn-final classifier (l2 F1) ----------------------------------------


def test_w3_newline_terminated_unparseable_final_line_is_tampering(
    tmp_path: Path,
) -> None:
    """W3 (l2 F1): a newline-terminated unparseable FINAL line is
    TAMPERING — a single-write+fsync append cannot end with its own
    newline — not the crash-tear pass. Today the classifier calls any
    unparseable final line a crash tear and passes with a false note."""
    from benchweave import supervision

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    journal = supervision.journal_path(_db(data_dir))
    journal.write_text(
        '{"wall": "2026-10-09T00:00:00Z", "event": "started"}\n'
        "GARBAGE-COMPLETE-LINE\n",
        encoding="utf-8",
    )
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    row = _row(_payload(result), "supervision_sidecars")
    assert row["verdict"] == "fail", row
    assert "tamper" in row["detail"].lower(), row


def test_w3_unterminated_unparseable_final_line_stays_the_crash_tear(
    tmp_path: Path,
) -> None:
    """The crash-tear half (unchanged): an UNTERMINATED unparseable final
    line is still the known tear shape — pass with the note."""
    from benchweave import supervision

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    journal = supervision.journal_path(_db(data_dir))
    journal.write_text(
        '{"wall": "2026-10-09T00:00:00Z", "event": "started"}\n'
        '{"wall": "2026-10-09T00:00:01Z", "even',
        encoding="utf-8",
    )
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 0, _combined(result)
    row = _row(_payload(result), "supervision_sidecars")
    assert row["verdict"] == "pass", row
    assert "torn" in row["detail"].lower(), row


# --- W4: the credential guard's remaining holes (gw1 F4) --------------------------


@POSIX_ONLY
def test_w4a_post_mortem_symlink_to_the_env_file_refuses(tmp_path: Path) -> None:
    """W4 (a): the post-mortem rung had NO credential guard — a
    ``<dir>.log`` SYMLINK to ``benchweave.env`` tailed the secret. The
    guard now covers both rungs (stat identity after resolve)."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    env = data_dir / atrest.CREDENTIAL_FILE
    secret = "tok-do-not-print-5f3a"
    env.write_text(f"BENCHWEAVE_SECRET={secret}\n", encoding="utf-8")
    env.chmod(0o600)
    log = supervision_log_path(_db(data_dir))
    log.symlink_to(env)
    result = _logs(data_dir)
    assert result.exit_code == 1, _combined(result)
    assert "logs_destination_credential:" in _combined(result)
    assert secret not in _combined(result)


@POSIX_ONLY
def test_w4b_post_mortem_hardlink_to_the_env_file_refuses(tmp_path: Path) -> None:
    """W4 (b): the compare is ``(st_dev, st_ino)`` after resolve — a
    HARDLINK of ``benchweave.env`` (a different path, the same inode) is
    the same credential and is refused (today's path-equality compare
    misses it and the tail leaks the secret)."""
    data_dir = tmp_path / "gateway"
    data_dir.mkdir()
    env = data_dir / atrest.CREDENTIAL_FILE
    secret = "tok-do-not-print-5f3a"
    env.write_text(f"BENCHWEAVE_SECRET={secret}\n", encoding="utf-8")
    env.chmod(0o600)
    log = supervision_log_path(_db(data_dir))
    os.link(env, log)
    result = _logs(data_dir)
    assert result.exit_code == 1, _combined(result)
    assert "logs_destination_credential:" in _combined(result)
    assert secret not in _combined(result)


# --- W5: log_destination's rungs were unguarded (gw1 F1) --------------------------


def _surface_log_destination(
    monkeypatch: pytest.MonkeyPatch, env: str | None, journal: bool
) -> str:
    from benchweave.interfaces.supervision import SupervisionSurface

    if env is None:
        monkeypatch.delenv("BENCHWEAVE_LOG_DESTINATION", raising=False)
    else:
        monkeypatch.setenv("BENCHWEAVE_LOG_DESTINATION", env)
    if journal:
        monkeypatch.setenv("JOURNAL_STREAM", "8:12345")
    else:
        monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    surface = object.__new__(SupervisionSurface)
    return surface.log_destination()


def test_w5a_env_destination_beats_the_journal_indicator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W5 leg 1 (gw1 F1): the R2-folded order — the env path (the
    ``start``-written value) WINS over ``JOURNAL_STREAM``. Swapping the
    rungs back to journal-first makes exactly this leg fail: the
    mechanism shipped unguarded (no leg pinned the order)."""
    assert (
        _surface_log_destination(monkeypatch, "/abs/data.log", journal=True)
        == "/abs/data.log"
    )


def test_w5b_journal_indicator_when_no_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W5 leg 2: no env value, systemd's ``JOURNAL_STREAM`` present →
    ``"journal"``."""
    assert (
        _surface_log_destination(monkeypatch, None, journal=True) == "journal"
    )


def test_w5c_stderr_when_neither(monkeypatch: pytest.MonkeyPatch) -> None:
    """W5 leg 3: neither the env value nor ``JOURNAL_STREAM`` →
    ``"stderr"`` (foreground serve keeps the terminal)."""
    assert _surface_log_destination(monkeypatch, None, journal=False) == "stderr"


# --- W6: the G2 pin-scope vs the KILL (gw1 F2) ------------------------------------


def test_w6_control_hold_take_breaks_the_read_only_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W6 RED: neutralize ``_check_store`` into a StoreHold acquire +
    release — doctor taking the hold is the KILL criterion's own example
    — and the G2 read-only pin must FAIL (the ``<dir>.hold`` family
    member appears). Today the pin is green on it: ``.hold`` was not in
    the enumerated family, so the new path was invisible."""
    from benchweave.cli import diagnose
    from benchweave.state.hold import StoreHold

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)

    def hold_taking_check(db: Path) -> dict[str, Any]:
        hold = StoreHold(db, label="doctor (neutralized)")
        hold.acquire()
        hold.release()
        return {"check": "store", "verdict": "pass", "detail": "neutralized"}

    monkeypatch.setattr(diagnose, "_check_store", hold_taking_check)
    before = _family_snapshot(data_dir)
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 0, _combined(result)
    after = _family_snapshot(data_dir)
    violations = _read_only_pin_violations(before, after)
    assert violations, (
        "the read-only pin must catch doctor taking the hold "
        f"(the KILL criterion's own example): {violations}"
    )


# --- W7: the recorded field is absolute by construction (gw1 F5) -------------------


def test_w7_relative_data_dir_records_an_absolute_log_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Structural pin (disclosed NON-RED): ``start`` resolves ``--data-dir``
    to absolute before recording ``log_destination``, so the recorded
    field is absolute for any spelling — a same-named file at a later
    ``logs``-invoker's cwd can never be silently tailed through it. (The
    property already held via ``state.hold.sibling_path``'s resolve; this
    pin makes it structural at ``start`` rather than incidental.)"""
    from benchweave.cli import lifecycle

    root = tmp_path / "invoker"
    (root / "gw-data").mkdir(parents=True)
    _setup_store(root / "gw-data")
    captured: dict[str, Any] = {}

    class _StubChild:
        pid = 42424242
        returncode = 1

        def poll(self) -> int:
            return 1

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> None:
            return None

        def kill(self) -> None:
            return None

    def stub_popen(argv: list[str], **kwargs: Any) -> Any:
        captured["argv"] = list(argv)
        captured["env"] = dict(kwargs.get("env") or {})
        return _StubChild()

    monkeypatch.setattr(subprocess, "Popen", stub_popen)
    monkeypatch.chdir(root)
    with pytest.raises(lifecycle.LifecycleError):
        # The stubbed child dies before readiness; the pin reads what
        # start recorded into the spawn env on its way there.
        lifecycle.start(Path("gw-data"), host="127.0.0.1", port=8125)
    value = str(captured["env"]["BENCHWEAVE_LOG_DESTINATION"])
    assert Path(value).is_absolute(), value


# --- W8: NITs + the two unarmed R7 cells ------------------------------------------


def test_w8a_fieldless_pidfile_notice_names_the_real_shape(tmp_path: Path) -> None:
    """W8 (NIT): a pidfile that exists but names no pid (a fieldless or
    legacy shape) reads as the lattice's ``absent`` cell — the notice
    must name that real shape, never claim ``no pidfile`` while one
    exists."""
    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    _write_pidfile(
        data_dir,
        {"gateway_id": "gw-x", "log_destination": "stderr", "schema": 1},
    )
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 0, _combined(result)
    row = _row(_payload(result), "pid")
    assert row["verdict"] == "pass", row
    detail = str(row["detail"]).lower()
    assert "fieldless" in detail or "legacy" in detail, row
    assert "no pidfile" not in detail, row


def test_w8b_out_of_vocabulary_destination_is_unknown_and_exits_one(
    tmp_path: Path,
) -> None:
    """W8: the R7-folded D6 cell (an out-of-vocab ``log_destination`` —
    a tampered or hand-written pidfile whose field is not the pinned
    ``journal``/``stderr``/non-empty string shape) reports ``unknown``
    naming the raw value and feeds the exit-1 contract; this arm pins the
    previously untested cell (both the non-string and the empty form)."""
    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    for raw in (42, ""):
        _write_pidfile(
            data_dir,
            {
                "pid": os.getpid(),
                "gateway_id": "gw-x",
                "data_dir": str(data_dir),
                "started_wall": "2026-10-09T00:00:00Z",
                "started_ticks": 1,
                "log_destination": raw,
                "schema": 1,
            },
        )
        result = _doctor(data_dir, "--json")
        assert result.exit_code == 1, _combined(result)
        row = _row(_payload(result), "log_destination")
        assert row["verdict"] == "unknown", row


def test_w8c_unreadable_journal_is_unknown_and_triage_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W8: the R7-folded D7 cell — an unreadable journal (OSError on
    open/read) reports ``unknown`` and triage CONTINUES (all seven rows
    emitted, never a mid-run crash); this arm pins the cell."""
    from benchweave import supervision

    data_dir = tmp_path / "gateway"
    _setup_store(data_dir)
    journal = supervision.journal_path(_db(data_dir))
    journal.write_text(_journal_row("started") + "\n", encoding="utf-8")
    real_read_text = Path.read_text

    def unreadable(self: Path, *args: object, **kwargs: object) -> str:
        if self == journal:
            raise OSError("permission denied (the unreadable-journal cell)")
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", unreadable)
    result = _doctor(data_dir, "--json")
    assert result.exit_code == 1, _combined(result)
    payload = _payload(result)
    assert len(payload["checks"]) == 7, payload["checks"]
    row = _row(payload, "supervision_sidecars")
    assert row["verdict"] == "unknown", row
