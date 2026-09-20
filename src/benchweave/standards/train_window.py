"""Bump-window enforcement for the prescriptive release train (#97).

GOVERNANCE.md's bump-window paragraph is enforced here, not remembered: a
standard may not bump more than once per floor (48h starting figure) measured
between the committer timestamps of the commits that added each new version
directory. Exempt from the pair sequence: a standard's first version
(admission) and a reset-class commit (one commit adding version directories
for three or more standards — the 2026-09-16 signature).

The clock self-anchors: only version-directory additions whose committer
timestamp is at or after the commit that added this module are checked, so
the rule's clock starts at the rule's arrival and prior history is
grandfathered by mechanism rather than a hand-maintained date.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

RESET_CLASS_STANDARD_COUNT = 3
"""Version directories for this many standards in one commit read as a reset."""

_MODULE_RELATIVE = Path("src/benchweave/standards/train_window.py")
_VERSION_DIR = re.compile(r"^standards/([a-z0-9-]+)/(\d+\.\d+\.\d+)/$")


class TrainWindowError(ValueError):
    """A bump landed inside its standard's window (prefixed, machine-matchable)."""


@dataclass(frozen=True)
class BumpEntry:
    """One version-directory addition: standard, version, landing time."""

    standard: str
    version: str
    timestamp: int


def window_violations(
    entries: tuple[BumpEntry, ...], floor_seconds: int
) -> tuple[str, ...]:
    """Return one prefixed message per same-standard pair inside the floor.

    Entries are inspected in timestamp order; admission exemption (a
    standard's first entry) and reset-class exemption (applied upstream by
    the collector) are both outside this function — it only judges gaps.
    The boundary case (gap exactly equal to the floor) passes: the window
    is a strict less-than refusal.
    """

    messages: list[str] = []
    by_standard: dict[str, list[BumpEntry]] = {}
    for entry in sorted(entries, key=lambda item: item.timestamp):
        by_standard.setdefault(entry.standard, []).append(entry)
    for standard, bumps in sorted(by_standard.items()):
        for previous, following in zip(bumps, bumps[1:], strict=False):
            gap = following.timestamp - previous.timestamp
            if gap < floor_seconds:
                messages.append(
                    f"train_window_violation: {standard} "
                    f"{previous.version} -> {following.version} "
                    f"({gap / 3600:.2f}h < {floor_seconds / 3600:.0f}h floor); "
                    "the queued change must wait for the next train "
                    "(GOVERNANCE.md bump window)"
                )
    return tuple(messages)


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def collect_bump_entries(root: Path) -> tuple[BumpEntry, ...]:
    """Read version-directory additions from git history, post-anchor only.

    The anchor is the committer timestamp of the commit that added this
    module; additions before it are the grandfathered history the rule was
    written against. Fails loud (never silent) when the history read is
    empty but the module is tracked — a shallow clone masquerading as a
    clean window is worse than a crash.
    """

    raw = _git(
        root,
        "log",
        "--diff-filter=A",
        "--format=%ct%x00%H",
        "--name-only",
        "--",
        "standards",
    )
    anchor_raw = _git(
        root,
        "log",
        "--diff-filter=A",
        "--format=%ct",
        "-1",
        "--",
        str(_MODULE_RELATIVE),
    ).strip()
    module_tracked = bool(anchor_raw)
    if module_tracked and not raw.strip():
        raise TrainWindowError(
            "train_window_history_unreadable: git log returned no standards "
            "history while this module is tracked — fetch full history "
            "(fetch-depth: 0) before trusting a clean window"
        )
    anchor = int(anchor_raw) if module_tracked else 0

    added: list[BumpEntry] = []
    seen_standards: set[str] = set()
    for block in _split_log(raw):
        timestamp = block.timestamp
        standards_in_commit: dict[str, tuple[str, str]] = {}
        for path in block.paths:
            match = _VERSION_DIR.match(f"{path}/")
            if match:
                standards_in_commit[match.group(1)] = match.group(2)
        if not standards_in_commit:
            continue
        is_reset_class = len(standards_in_commit) >= RESET_CLASS_STANDARD_COUNT
        for standard, version in standards_in_commit.items():
            first = standard not in seen_standards
            seen_standards.add(standard)
            if timestamp < anchor or first or is_reset_class:
                continue
            added.append(BumpEntry(standard, version, timestamp))
    return tuple(sorted(added, key=lambda item: item.timestamp))


def check_train_windows(root: Path, floor_seconds: int) -> tuple[str, ...]:
    """Full enforcement entry: collect, then judge. Raises on violation."""

    violations = window_violations(collect_bump_entries(root), floor_seconds)
    if violations:
        raise TrainWindowError("; ".join(violations))
    return violations


@dataclass(frozen=True)
class _LogBlock:
    timestamp: int
    paths: tuple[str, ...]


def _split_log(raw: str) -> list[_LogBlock]:
    """Split `--format=%ct%x00%H --name-only` output into per-commit blocks."""

    blocks: list[_LogBlock] = []
    current_timestamp: int | None = None
    current_paths: list[str] = []
    for line in raw.splitlines():
        if not line:
            continue
        header = line.split("\x00", 1)
        if len(header) == 2 and header[0].isdigit() and len(header[1]) == 40:
            if current_timestamp is not None:
                blocks.append(_LogBlock(current_timestamp, tuple(current_paths)))
            current_timestamp = int(header[0])
            current_paths = []
        elif current_timestamp is not None:
            current_paths.append(line)
    if current_timestamp is not None:
        blocks.append(_LogBlock(current_timestamp, tuple(current_paths)))
    return blocks
