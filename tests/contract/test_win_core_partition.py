"""Partition proof, W1 probe pin, and detection teeth for the Windows core
subset (issue #471; design of record
``.claude/deep-review/2026-10-15-windows-core-subset-design.md``).

The proof is mechanical and count-level, run in the default gates selection:

- **Subset + disjointness** — per-file counts under
  ``-m "wincore and not timing and not browser"`` equal the plain
  ``-m wincore`` counts, so every wincore id is inside the gates selection
  (a wincore+timing double-mark would under-count the subset combo), and
  wincore ∩ timing = ∅ and wincore ∩ browser = ∅ (both combos collect zero).
- **Manifest** — the manifest script's ``--check`` exits 0 on the committed
  manifest: recollected per-file ``(total, core)`` rows match exactly, the
  ``w1_map`` keys equal the live win32/msvcrt text scan of
  ``src/benchweave``, and every mapped test file is whole-module marked
  (``core == total``).
- **Teeth** — ``--check`` refuses a doctored manifest: a dropped file row, a
  bumped core count, a dropped ``w1_map`` row. Each tooth asserts a NONZERO
  exit, so the ratchet's detection is proven inside the suite, not in a
  PR-body claim.
- **Workflow** — the ci.yml windows job runs ``-m wincore`` with a 20-minute
  timeout and the evidence posture intact: continue-on-error on the test
  step, the junitxml artifact, the evidence summary.

What these arms do NOT catch: a test-side platform construct (e.g. a
tzset-guarded test) in a file with no src win32 branch — the probe covers
src-side branching only; the classes and the owner-reviewed manifest diff
are the boundary (design §9 under-selection residual; AR-5 is the outcome
check on the first Windows run).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

try:  # POSIX: serialize the subprocess work under xdist. On Windows the
    # gates suite does not run (the windows lane runs -m wincore instead),
    # so the no-op fallback there costs nothing the lane needs.
    import fcntl
except ImportError:  # pragma: no cover - platform-dependent import
    fcntl = None  # type: ignore[assignment]

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci" / "win_core_manifest.py"
MANIFEST = REPO / "tests" / "win_core_manifest.json"
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

_COLLECT_RE = re.compile(r"^([^ :]+): (\d+)$")


def _path_env() -> str:
    """PATH pass-through so subprocesses resolve the same tooling."""
    return os.environ.get("PATH", "/usr/bin:/bin")


@contextmanager
def _serial() -> Iterator[None]:
    """Serialize the subprocess work across xdist workers.

    The partition arms spawn real pytest collections; left unserialized under
    ``-n auto`` they run concurrently with the battery's pacing-sensitive
    integration tier and redden flake-prone arms there (observed twice on
    this branch: test_issue146_e2e twice, run_activation's r11/d1/f5 once
    each — all green in isolation and on the pre-change tree's full
    battery). One at a time keeps the added parallel load near zero.
    """
    # The lock lives in the temp dir, not the repo: a repo-root lock file
    # would need unlink-on-release, and unlinking a lock another worker may
    # still hold lets a third worker lock a fresh inode (two inside at once).
    lock_path = Path(tempfile.gettempdir()) / "benchweave-win-core-partition.lock"
    with open(lock_path, "w") as handle:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _collect(marker: str) -> dict[str, int]:
    """Per-file collected counts for one marker expression."""
    with _serial():
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", marker],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=300,
            env={
                "PYTEST_ADDOPTS": "",
                "PATH": _path_env(),
                "UV_PROJECT_ENVIRONMENT": "venv",
            },
            check=False,
        )
    if proc.returncode not in (0, 5):
        raise AssertionError(
            f"collection failed for -m {marker!r} (exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    # Exit 5 is pytest's empty-selection code and is DATA here, not failure:
    # the disjointness combos (wincore ∩ timing, wincore ∩ browser) collect
    # zero by design. A collection ERROR exits nonzero-but-not-5 and still
    # raises, so a broken tree cannot masquerade as an empty intersection.
    counts: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        match = _COLLECT_RE.match(line.strip())
        if match is None:
            continue
        path = match.group(1).replace("\\", "/")
        if (path.startswith("tests/") or path.startswith("docs/")) and (
            path.endswith(".py") or path.endswith(".md")
        ):
            counts[path] = int(match.group(2))
    return counts


def _run_script(manifest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the manifest script against an explicit manifest path."""
    with _serial():
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--manifest", str(manifest), *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )


def _windows_job_text(workflow_text: str) -> str:
    """The windows job's YAML block (from its key to the next job key)."""
    match = re.search(
        r"^  windows:\n(.*?)(?=^  \w+:|\Z)", workflow_text, re.S | re.M
    )
    assert match is not None, "windows job block not found in ci.yml"
    return match.group(1)


def _windows_job_text_full(workflow_text: str) -> str:
    """The windows-full job's YAML block."""
    match = re.search(
        r"^  windows-full:\n(.*?)(?=^  [\w-]+:|\Z)", workflow_text, re.S | re.M
    )
    assert match is not None, "windows-full job block not found in ci.yml"
    return match.group(1)


@pytest.fixture(scope="module")
def selections() -> dict[str, dict[str, int]]:
    """All four marker selections in one cached pass (one worker's worth)."""
    return {
        "wincore": _collect("wincore"),
        "subset": _collect("wincore and not timing and not browser"),
        "timing": _collect("wincore and timing"),
        "browser": _collect("wincore and browser"),
    }


def test_wincore_subset_of_gates_selection_and_disjoint_from_lanes(
    selections: dict[str, dict[str, int]],
) -> None:
    """wincore ⊆ gates selection, wincore ∩ timing = ∅, wincore ∩ browser = ∅.

    Count-level shape of design §5.2's id-level claim: the gates-combo counts
    equal the plain wincore counts per file (subset), and both lane-intersection
    combos collect zero (disjointness). The core must also be nonempty — an
    empty core would make every other arm vacuous.
    """
    wincore = selections["wincore"]
    assert sum(wincore.values()) > 0, "the founding core is empty"
    assert selections["subset"] == wincore, (
        "wincore is not a subset of the gates selection: per-file counts of "
        "-m 'wincore and not timing and not browser' differ from -m wincore — "
        "a wincore test carries a timing/browser mark"
    )
    assert sum(selections["timing"].values()) == 0, (
        "wincore ∩ timing is not empty: a wincore test carries the timing mark"
    )
    assert sum(selections["browser"].values()) == 0, (
        "wincore ∩ browser is not empty: a wincore test carries the browser mark"
    )


def test_committed_manifest_is_check_green() -> None:
    """The committed manifest matches the live tree (AR-1's green side)."""
    proc = _run_script(MANIFEST, "--check")
    assert proc.returncode == 0, (
        f"--check red on the committed manifest (exit {proc.returncode}):\n"
        f"{proc.stdout}\n{proc.stderr}"
    )


def _doctored_manifest(tmp_path: Path, mutate: Any) -> Path:
    """A tmp_path copy of the committed manifest with one mutation applied."""
    document = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mutate(document)
    doctored = tmp_path / "win_core_manifest.doctored.json"
    doctored.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return doctored


def test_teeth_dropped_file_row_refuses(tmp_path: Path) -> None:
    """Dropping one file row reds --check (growth/shrinkage both refuse)."""
    def mutate(document: Any) -> None:
        files = document["files"]
        victim = next(
            key
            for key, row in files.items()
            if row["total"] > 0 and row["core"] == 0
        )
        del files[victim]

    proc = _run_script(_doctored_manifest(tmp_path, mutate), "--check")
    assert proc.returncode != 0, (
        "--check exited 0 on a manifest missing a file row — the ratchet "
        f"does not detect dropped files:\n{proc.stdout}\n{proc.stderr}"
    )


def test_teeth_bumped_core_count_refuses(tmp_path: Path) -> None:
    """A core-count row that disagrees with the live collection reds --check."""
    def mutate(document: Any) -> None:
        files = document["files"]
        victim = next(
            key for key, row in files.items() if row["core"] > 0
        )
        files[victim]["core"] += 1

    proc = _run_script(_doctored_manifest(tmp_path, mutate), "--check")
    assert proc.returncode != 0, (
        "--check exited 0 on a manifest with a wrong core count — the "
        f"ratchet does not detect count drift:\n{proc.stdout}\n{proc.stderr}"
    )


def test_teeth_dropped_w1_map_row_refuses(tmp_path: Path) -> None:
    """Removing a w1_map row (probe hit intact) reds --check (AR-2 dead-row)."""
    def mutate(document: Any) -> None:
        w1_map = document["w1_map"]
        victim = sorted(w1_map)[0]
        del w1_map[victim]

    proc = _run_script(_doctored_manifest(tmp_path, mutate), "--check")
    assert proc.returncode != 0, (
        "--check exited 0 with a w1_map row removed while its probe hit "
        f"remains — the dead-row check has no teeth:\n{proc.stdout}\n{proc.stderr}"
    )


def test_probe_pins_the_win32_branching_source_set() -> None:
    """The live win32/msvcrt scan of src equals the manifest's w1_map keys.

    This is the pin the script's --check enforces through its own scan; the
    duplicate scan here keeps the assertion (and its failure message) inside
    the suite. Also pins the W1 shape: mapped test files exist and are
    whole-module marked.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    w1_map: dict[str, Any] = manifest["w1_map"]
    files: dict[str, Any] = manifest["files"]

    live: set[str] = set()
    src = REPO / "src" / "benchweave"
    for path in sorted(src.rglob("*.py")):
        if re.search(r"win32|msvcrt", path.read_text(encoding="utf-8")):
            live.add(path.relative_to(REPO).as_posix())

    assert live == set(w1_map), (
        "the win32-branching src set drifted from w1_map: "
        f"unmapped hits {sorted(live - set(w1_map))} / dead rows "
        f"{sorted(set(w1_map) - live)}"
    )
    for src_file, test_files in sorted(w1_map.items()):
        assert test_files, f"w1_map row {src_file} maps no test file"
        for test_file in test_files:
            assert (REPO / test_file).exists(), (
                f"w1_map row {src_file} names absent test file {test_file}"
            )
            row = files[test_file]
            assert row["core"] == row["total"], (
                f"W1 whole-module mark incomplete: {test_file} "
                f"(core {row['core']} != total {row['total']})"
            )


def test_workflow_windows_job_pins_the_core_selection() -> None:
    """The windows job runs the core selection with the posture intact.

    RED control for the workflow change: this arm reds against the pre-fix
    ci.yml (full selection, 45-minute timeout).
    """
    job = _windows_job_text(WORKFLOW.read_text(encoding="utf-8"))
    assert "-m wincore" in job, (
        "the windows job no longer runs the core selection (-m wincore)"
    )
    assert "timeout-minutes: 20" in job, (
        "the windows job timeout is not the R5 20-minute value"
    )
    assert "continue-on-error: true" in job, (
        "the windows job lost the evidence posture (continue-on-error on the "
        "test step)"
    )
    assert "--junitxml=windows-evidence.xml" in job, (
        "the windows job lost the junitxml evidence artifact"
    )
    assert "Evidence summary" in job, (
        "the windows job lost the evidence summary step"
    )
    assert "windows-evidence-junit" in job, (
        "the windows job lost the junitxml artifact upload"
    )


def test_workflow_weekly_full_lane_pins_the_complement_run() -> None:
    """R1 (owner ruling, 2026-10-15): the weekly full-selection lane is pinned.

    The windows-full job exists, runs ONLY on the schedule trigger, runs the
    gates selection (the complement's per-week reproduction surface), and
    carries the same evidence posture as the core lane.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    job = _windows_job_text_full(text)
    assert 'if: github.event_name == \'schedule\'' in job, (
        "windows-full is not schedule-gated — it would run on every PR"
    )
    assert '-m "not timing and not browser"' in job, (
        "windows-full no longer runs the full gates selection"
    )
    assert "continue-on-error: true" in job, (
        "windows-full lost the evidence posture (continue-on-error)"
    )
    assert "windows-evidence-full-junit" in job, (
        "windows-full lost its junitxml artifact upload"
    )
    # The schedule trigger exists and every OTHER job guards itself out of
    # the weekly run: schedule must execute exactly one job. The guard may
    # sit anywhere in the job's header block (the windows job's sits below
    # its comment block).
    assert re.search(r"^  schedule:\n    - cron: \"23 2 \* \* 1\"$", text, re.M), (
        "the weekly cron trigger is absent or changed"
    )
    for name in ("gates", "timing", "browser", "systemd", "windows", "sdk-drift"):
        match = re.search(
            rf"^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:|\Z)", text, re.S | re.M
        )
        assert match is not None, f"job {name} vanished from ci.yml"
        assert "if: github.event_name != 'schedule'" in match.group(1), (
            f"job {name} lost its schedule guard — the weekly cron would run it"
        )
