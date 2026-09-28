"""The gate wrapper reads TRUE exit codes: a pipe, a tail, or a filtered
summary line cannot false-green a failing gate (issue #247 increment 3,
Leg D — evidence discipline is part of the gate definition)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "gate.py"


def _failure_log_path(proc_stdout: str) -> Path:
    match = re.search(r"full log: ([^)]+)", proc_stdout)
    assert match, proc_stdout
    return Path(match.group(1))


def _load_gate() -> Any:
    spec = importlib.util.spec_from_file_location("gate_wrapper_under_test", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so the dataclass machinery can resolve string
    # annotations through sys.modules (importlib documented requirement).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_gate(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    """Invoke the wrapper black-box, exactly as a build agent would. stdout
    always arrives through a pipe here — the same shape `| tail -1` produces."""
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _planted_failing_test(tmp_path: Path) -> Path:
    planted = tmp_path / "test_planted_failure.py"
    planted.write_text(
        "def test_planted_failure() -> None:\n    assert False\n", encoding="utf-8"
    )
    return planted


# --- (c) junit count parsing -------------------------------------------------


def test_junit_counts_parsed_from_known_xunit1_fixture(tmp_path: Path) -> None:
    gate = _load_gate()
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<testsuite errors="0" failures="1" name="pytest" skipped="1" tests="3" time="0.1">\n'
        '  <testcase classname="t" name="passes" time="0.01"/>\n'
        '  <testcase classname="t" name="fails" time="0.01"><failure message="f"/></testcase>\n'
        '  <testcase classname="t" name="skips" time="0.01"><skipped message="s"/></testcase>\n'
        "</testsuite>\n",
        encoding="utf-8",
    )
    assert gate.parse_junit_counts(junit) == (3, 1, 0, 1)


def test_junit_missing_skipped_attribute_reads_zero(tmp_path: Path) -> None:
    """pytest omits `skipped` when nothing skipped — absence means zero, not
    an unparseable report."""
    gate = _load_gate()
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<testsuite errors="0" failures="0" name="pytest" tests="2" time="0.1">\n'
        "</testsuite>\n",
        encoding="utf-8",
    )
    assert gate.parse_junit_counts(junit) == (2, 0, 0, 0)


def test_junit_testsuites_wrapper_aggregates_suites(tmp_path: Path) -> None:
    gate = _load_gate()
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<testsuites><testsuite errors="1" failures="0" tests="2" time="0.1"/>'
        '<testsuite errors="0" failures="2" tests="3" time="0.1"/></testsuites>\n',
        encoding="utf-8",
    )
    assert gate.parse_junit_counts(junit) == (5, 2, 1, 0)


# --- the pinned wire shape ----------------------------------------------------


def test_gate_line_matches_the_pinned_wire_shape() -> None:
    gate = _load_gate()
    assert gate.format_gate_line("pytest", (2413, 0, 0, 11), "PASS") == (
        "GATE pytest 2413 0 0 11 PASS"
    )
    assert gate.format_gate_line("ruff", None, "PASS") == "GATE ruff - - - - PASS"
    assert gate.format_gate_line("mypy", None, "FAIL") == "GATE mypy - - - - FAIL"
    assert gate.format_gate_line("pytest", None, "SKIP") == "GATE pytest - - - - SKIP"


# --- command construction -----------------------------------------------------


def test_full_mode_adds_parallel_flags_only_when_xdist_available(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    with_xdist = gate.build_commands("full", [], True, tmp_path)
    without_xdist = gate.build_commands("full", [], False, tmp_path)
    pytest_with = next(c for c in with_xdist if c.name == "pytest")
    pytest_without = next(c for c in without_xdist if c.name == "pytest")
    assert pytest_with.args[-4:] == ["-n", "auto", "-m", "not timing"]
    assert "-n" not in pytest_without.args
    assert "-m" not in pytest_without.args


def test_fast_mode_pins_the_three_doctrine_commands(tmp_path: Path) -> None:
    gate = _load_gate()
    commands = {c.name: c for c in gate.build_commands("fast", ["tests/unit"], False, tmp_path)}
    # ruff: exactly the bare tree check
    assert commands["ruff"].args == ["uv", "run", "ruff", "check", "."]
    # mypy: bare and config-driven (no path args — those drop packages/sdk/src),
    # fresh cache per the #247 evidence rule
    assert commands["mypy"].args == ["uv", "run", "mypy", "--no-incremental"]
    # pytest: junitxml always requested so counts come from the report, not a
    # summary line
    pytest_cmd = commands["pytest"]
    assert any(arg.startswith("--junitxml=") for arg in pytest_cmd.args)
    assert "tests/unit" in pytest_cmd.args
    assert pytest_cmd.junit is not None


# --- (a) a planted failing gate reads FAIL with the true counts ----------------


def test_planted_failing_gate_reads_fail_with_true_counts(tmp_path: Path) -> None:
    planted = _planted_failing_test(tmp_path)
    proc = _run_gate("--fast", "--only", "pytest", str(planted))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "GATE pytest 1 1 0 0 FAIL" in proc.stdout, proc.stdout


# --- (b) the piped lie cannot false-green the wrapper --------------------------


def test_piped_summary_cannot_false_green_a_failing_gate(tmp_path: Path) -> None:
    planted = _planted_failing_test(tmp_path)
    # stdout through a pipe (capture_output), status still true
    proc = _run_gate("--fast", "--only", "pytest", str(planted))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    # and the doctrine's exact failing shape — `wrapper | tail -1` reports
    # tail's exit status, so the consumer must read PIPESTATUS[0]; the
    # wrapper's true status must still be there to read.
    shell = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f'{sys.executable} "{GATE}" --fast --only pytest "{planted}" | tail -1 >/dev/null; '
            'exit "${PIPESTATUS[0]}"',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert shell.returncode == 1


# --- (d) pass paths -------------------------------------------------------------


def test_ruff_pass_path_reads_pass_through_a_pipe() -> None:
    proc = _run_gate("--fast", "--only", "ruff")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GATE ruff - - - - PASS" in proc.stdout, proc.stdout


def test_mypy_pass_path_reads_pass_on_a_clean_tree() -> None:
    proc = _run_gate("--fast", "--only", "mypy", timeout=900)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GATE mypy - - - - PASS" in proc.stdout, proc.stdout


def test_missing_mode_is_a_usage_error_not_a_silent_default() -> None:
    proc = _run_gate("--only", "ruff")
    assert proc.returncode == 2


# --- refute fold F1: the "full log:" pointer must survive the run --------------


def test_failure_log_path_exists_after_the_run_completes(tmp_path: Path) -> None:
    planted = _planted_failing_test(tmp_path)
    proc = _run_gate("--fast", "--only", "pytest", str(planted))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    log_path = _failure_log_path(proc.stdout)
    assert log_path.exists(), f"log pointer dead on arrival: {log_path}"


def test_every_planted_failure_reachable_in_stdout_or_retained_log(
    tmp_path: Path,
) -> None:
    """Eight planted failures overflow the 30-line excerpt; the tail carries
    only the last few, so the earlier messages must stay reachable through
    the retained log file."""
    planted = tmp_path / "test_planted_eight.py"
    planted.write_text(
        "\n".join(
            f'def test_planted_{i}() -> None:\n    assert False, "PLANTED-F1-{i}"\n'
            for i in range(8)
        ),
        encoding="utf-8",
    )
    proc = _run_gate("--fast", "--only", "pytest", str(planted))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    log_path = _failure_log_path(proc.stdout)
    reachable = proc.stdout + (
        log_path.read_text(errors="replace") if log_path.exists() else ""
    )
    for i in range(8):
        assert f"PLANTED-F1-{i}" in reachable, f"planted failure {i} unreachable"


def test_prune_keeps_only_the_newest_runs(tmp_path: Path, monkeypatch: object) -> None:
    gate = _load_gate()
    monkeypatch.setattr(gate, "LOG_ROOT", tmp_path)  # type: ignore[attr-defined]
    for i in range(25):
        (tmp_path / f"20260101-0000{i:02d}-1").mkdir()
    (tmp_path / "stray-file").write_text("x", encoding="utf-8")
    gate.prune_old_runs()
    remaining = sorted(path.name for path in tmp_path.iterdir())
    assert len(remaining) == 21, remaining  # 20 runs + the untouched stray file
    assert "20260101-000024-1" in remaining, remaining
    assert "20260101-000000-1" not in remaining, remaining


# --- refute fold F2: zero tests ran is a FAILED check, not a pass --------------


def test_collect_only_is_not_gate_evidence_reads_fail(tmp_path: Path) -> None:
    """A runnable test + `--collect-only` exits 0 with junit tests=0 — the
    gate read `GATE pytest 0 0 0 0 PASS` (verified against the unfixed
    wrapper). No tests ran; a pass verdict here is the exact green-shaped
    no-op the #247 doctrine calls a FAILED check."""
    planted = tmp_path / "test_probe_passing.py"
    planted.write_text(
        "def test_probe_passing() -> None:\n    assert True\n", encoding="utf-8"
    )
    proc = _run_gate(
        "--fast", "--only", "pytest", str(planted), "--", "--collect-only", "-q"
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "GATE pytest 0 0 0 0 FAIL" in proc.stdout, proc.stdout


def test_zero_tests_without_collect_only_also_reads_fail(tmp_path: Path) -> None:
    """Plain invocation over a dir with no tests: pytest exits 5, but the
    wrapper's zero-count guard must hold even if an exit code were ever 0."""
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = _run_gate("--fast", "--only", "pytest", str(empty))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "GATE pytest 0 0 0 0 FAIL" in proc.stdout, proc.stdout
