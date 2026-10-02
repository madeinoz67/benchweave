"""The BenchWeave gate wrapper — honest, machine-readable gate evidence.

Issue #247 increment 3 (Leg D): evidence discipline is part of the gate
definition. rtk's filtered summaries lie in both directions (5+ documented
instances 2026-09-14 -> 2026-09-27), and `cmd | tail -1; echo $?` reports
tail's status, not the command's — so this wrapper runs each gate command
with its output redirected to a file (never through a pipe that would mask
the status it reports), parses the junitxml report attributes for the pytest
leg, and prints one machine-readable line per gate:

    GATE pytest 2413 0 0 11 PASS
    GATE ruff - - - - PASS
    GATE mypy - - - - PASS

Fields: `GATE <name> <tests> <failures> <errors> <skipped> <PASS|FAIL|SKIP>`;
`-` marks a field that gate does not produce. Exit codes: 0 all gates passed
(an explicit SKIP is not a failure), 1 any gate failed, 2 usage error. The
exit code is the verdict — no downstream `| tail` can change it.

Usage:
    uv run python scripts/gate.py --fast [pytest-paths...]
    uv run python scripts/gate.py --full
    uv run python scripts/gate.py --fast --only ruff,pytest [pytest-paths...]

--fast is the per-commit lane: ruff + fresh-cache mypy + focused pytest over
the paths given. --full is the per-push battery: ruff + mypy + the full
suite — when pytest-xdist is importable in the project environment the suite
runs `-n auto -m "not timing and not browser"` (the timing marker stays
serialized per #241/#246; the browser marker runs in its own lane with
chromium installed, per #300); until xdist lands on main this is the plain
serial suite.

The pytest leg of --fast with no paths prints an explicit SKIP rather than
silently running nothing — the fast lane has no exemptions, and a hidden
no-op is how a gate starts lying.

The mypy leg runs `--no-incremental` (fresh-cache evidence per the #247
doctrine) rather than deleting .mypy_cache (it avoids READING stale cache
entries — the honest-evidence point; it still WRITES shared cache shards,
an availability hazard for concurrent agents, never an honesty one, which
is why the wrapper does not delete the directory).

Gate output survives the run: each invocation writes to
.gate-logs/<run-id>/ (gitignored, pruned to the last 20 runs) and failing
gates print the retained path plus a 30-line excerpt — a "full log:"
pointer that vanishes at process exit is a dead reference, not evidence.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parent.parent
UV = "uv"
GATE_NAMES = ("ruff", "mypy", "pytest")
EXCERPT_LINES = 30
LOG_ROOT = REPO / ".gate-logs"
MAX_RETAINED_RUNS = 20

#: pytest flags whose run COLLECTS but never EXECUTES: whatever they print,
#: they are not gate evidence, and the pytest leg reads FAIL under them.
COLLECT_ONLY_FLAGS = ("--collect-only", "--co")

#: The pytest-xdist parallel flags (design §2): full suite, excluding the
#: `timing` marker (serialized in its own lane) and the `browser` marker
#: (issue #300 G1d: serialized in its own lane with chromium installed —
#: the batteries never assume the browsers are present).
XDIST_FLAGS = ["-n", "auto", "-m", "not timing and not browser"]


class GateCmd(NamedTuple):
    name: str
    args: list[str]
    junit: Path | None


@dataclass(frozen=True)
class GateResult:
    name: str
    returncode: int
    counts: tuple[int, int, int, int] | None
    log_path: Path
    collect_only: bool = False

    @property
    def status(self) -> str:
        if self.returncode != 0:
            return "FAIL"
        if self.collect_only:
            # Collection executes nothing; a green collect-only run is not
            # evidence of anything.
            return "FAIL"
        if self.counts is not None and self.counts[0] == 0:
            # Zero tests ran — a FAILED check per the #247 doctrine, not a
            # pass. Does not catch an all-skipped run: tests>0 still PASSes,
            # visibly, in the skipped cell.
            return "FAIL"
        return "PASS"


def parse_junit_counts(path: Path) -> tuple[int, int, int, int]:
    """Read (tests, failures, errors, skipped) from a junitxml report.

    Handles both shapes the repo's `junit_family = "xunit1"` default can
    produce: a bare `<testsuite>` root and a `<testsuites>` wrapper (which is
    what pytest itself writes for a filtered run). Attributes pytest omits
    for zero — `skipped` most commonly — read as 0; absence of a count is a
    zero, not an unparseable report. Multiple `<testsuite>` elements sum.
    """
    # The report is self-produced: this same run pointed pytest's
    # --junitxml here one command earlier. No untrusted-XML surface.
    root = ET.parse(path).getroot()  # noqa: S314 - self-produced report
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    tests = failures = errors = skipped = 0
    for suite in suites:
        tests += int(suite.get("tests", "0"))
        failures += int(suite.get("failures", "0"))
        errors += int(suite.get("errors", "0"))
        skipped += int(suite.get("skipped", "0"))
    return tests, failures, errors, skipped


def format_gate_line(
    name: str, counts: tuple[int, int, int, int] | None, status: str
) -> str:
    cells = [str(value) for value in counts] if counts else ["-", "-", "-", "-"]
    return " ".join(["GATE", name, *cells, status])


def build_commands(
    mode: str, pytest_args: list[str], xdist_available: bool, log_dir: Path
) -> list[GateCmd]:
    """The doctrine's commands, pinned exactly. mypy stays bare (no path
    arguments — those silently drop packages/sdk/src from the build)."""
    junit = log_dir / "pytest-junit.xml"
    pytest_cmd = [UV, "run", "pytest", f"--junitxml={junit}"]
    if mode == "fast":
        # The browser marker never runs in the fast lane: chromium is the
        # browser job's own install, and a chromium-less machine errored
        # the whole fast lane here (27 errors, issue #300 fold F3) — the
        # marker exclusion is part of the fast lane's definition now.
        pytest_cmd.extend([*pytest_args, "-m", "not browser"])
    elif xdist_available:
        pytest_cmd.extend(XDIST_FLAGS)
    return [
        GateCmd("ruff", [UV, "run", "ruff", "check", "."], None),
        GateCmd("mypy", [UV, "run", "mypy", "--no-incremental"], None),
        GateCmd("pytest", pytest_cmd, junit),
    ]


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    # Non-dot venv: without this, uv silently creates .venv/ (root-caused
    # dot-dir .pth skipping; machine-wide convention).
    env.setdefault("UV_PROJECT_ENVIRONMENT", "venv")
    env["NO_COLOR"] = "1"
    return env


def xdist_available(env: dict[str, str], cwd: Path) -> bool:
    """Probe the environment pytest will actually run in (the project env via
    uv), not this wrapper's interpreter."""
    probe = subprocess.run(
        [
            UV,
            "run",
            "python",
            "-c",
            "import importlib.util as i; raise SystemExit(0 if i.find_spec('xdist') else 1)",
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        timeout=120,
    )
    return probe.returncode == 0


def run_gate_cmd(
    cmd: GateCmd, env: dict[str, str], cwd: Path, log_dir: Path
) -> GateResult:
    """Run one gate with output to a FILE — the true exit code comes from
    subprocess, immune to any downstream pipe."""
    log_path = log_dir / f"{cmd.name}.log"
    with log_path.open("wb") as out:
        proc = subprocess.run(
            cmd.args, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT
        )
    counts = None
    if cmd.junit is not None and cmd.junit.exists():
        counts = parse_junit_counts(cmd.junit)
    collect_only = any(
        arg in COLLECT_ONLY_FLAGS or arg.startswith("--collect-only=")
        for arg in cmd.args
    )
    return GateResult(cmd.name, proc.returncode, counts, log_path, collect_only)


def print_excerpt(result: GateResult) -> None:
    """In-band tail of a failing gate's output, for the human reading the
    run; machine readers match ^GATE and the exit code."""
    try:
        lines = result.log_path.read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    excerpt = lines[-EXCERPT_LINES:]
    print(
        f"--- {result.name} output (last {len(excerpt)} of {len(lines)} lines; "
        f"full log: {result.log_path}) ---"
    )
    for line in excerpt:
        print(line)


def prune_old_runs(keep: int = MAX_RETAINED_RUNS) -> None:
    """Best-effort hygiene: keep the newest `keep` run dirs. Pruning must
    never become a gate verdict, so every error is ignored."""
    try:
        runs = sorted(path for path in LOG_ROOT.iterdir() if path.is_dir())
        for stale in runs[:-keep]:
            shutil.rmtree(stale, ignore_errors=True)
    except OSError:
        pass


def new_log_dir() -> Path:
    """A stable, collision-resistant per-run directory: run-id is
    timestamp + pid, so concurrent wrappers never share a log dir."""
    log_dir = LOG_ROOT / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the BenchWeave gates with honest, machine-readable evidence.",
        epilog=(
            "Wire format: GATE <name> <tests> <failures> <errors> <skipped> "
            "<PASS|FAIL|SKIP> ('-' = not produced). Exit: 0 pass, 1 any gate "
            "failed, 2 usage."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--fast",
        action="store_const",
        const="fast",
        dest="mode",
        help="per-commit lane: ruff + fresh-cache mypy + focused pytest (paths below)",
    )
    mode.add_argument(
        "--full",
        action="store_const",
        const="full",
        dest="mode",
        help=(
            "per-push battery: ruff + mypy + full suite "
            "(-n auto -m 'not timing and not browser' under xdist)"
        ),
    )
    parser.add_argument(
        "--only",
        default=",".join(GATE_NAMES),
        help="comma-separated subset of gates to run (default: all)",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="pytest paths/args (fast lane); with none, the pytest leg SKIPs visibly",
    )
    args = parser.parse_args(argv)

    selected = set(args.only.split(","))
    unknown = selected - set(GATE_NAMES)
    if unknown:
        parser.error(f"unknown gate(s) in --only: {sorted(unknown)}")

    cwd = REPO
    env = child_env()
    log_dir = new_log_dir()
    commands = [
        cmd
        for cmd in build_commands(
            args.mode,
            args.pytest_args,
            xdist_available(env, cwd) if args.mode == "full" else False,
            log_dir,
        )
        if cmd.name in selected
    ]
    failures: list[GateResult] = []
    for cmd in commands:
        if cmd.name == "pytest" and args.mode == "fast" and not args.pytest_args:
            print(format_gate_line("pytest", None, "SKIP"), flush=True)
            continue
        result = run_gate_cmd(cmd, env, cwd, log_dir)
        print(format_gate_line(result.name, result.counts, result.status), flush=True)
        if result.status == "FAIL":
            failures.append(result)
    for failure in failures:
        print_excerpt(failure)
    prune_old_runs()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
