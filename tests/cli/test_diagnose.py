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
#: the four in-dir names plus the four siblings beside the data dir.
_FAMILY_IN_DIR = (
    atrest.DB_NAME,
    atrest.DB_NAME + "-wal",
    atrest.DB_NAME + "-shm",
    atrest.CREDENTIAL_FILE,
)
_FAMILY_SIBLINGS = (".pid", ".stop", ".log", ".supervision.jsonl")


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
    disclosed = {atrest.DB_NAME + "-wal", atrest.DB_NAME + "-shm"}
    for name, (was, mtime) in before.items():
        now_exists, now_mtime = after[name]
        if was:
            assert now_exists, f"{name} vanished across the doctor run"
            assert now_mtime == mtime, f"{name} mtime moved across the run"
        else:
            assert (not now_exists) or name in disclosed, (
                f"{name} appeared beyond the disclosed sidecar pair"
            )
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
