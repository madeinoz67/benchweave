"""Bump-window enforcement for the prescriptive release train (#97).

GOVERNANCE.md's bump-window paragraph is enforced here, not remembered: a
standard may not bump more than once per floor (48h starting figure) measured
between the committer timestamps of the commits that added each version
directory. A version directory whose files land across several commits
counts once, at the earliest commit (the real corpus straddles otdp 0.1.2
by 26 seconds). Reset-class commits (one commit adding version directories
for three or more standards — a heuristic matching the 2026-09-16
signature, not the Resets section's full definition) contribute no entries:
each standard's next non-exempt bump opens a fresh window. The chronological
first non-exempt version of a standard is its admission and likewise opens
the window rather than being judged.

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

# The anchor query keys this exact path. DO NOT repoint it if this module is
# moved: the arrival commit of the ORIGINAL path is the rule's ratification
# moment, and repointing would re-anchor to the move commit and grandfather
# the interim history (git records moves as fresh adds without rename
# detection).
_MODULE_RELATIVE = Path("src/benchweave/standards/train_window.py")
_VERSION_PATH = re.compile(r"^standards/([a-z0-9-]+)/(\d+\.\d+\.\d+)/")


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

    Exemptions (admission, reset-class, pre-anchor) are applied upstream by
    the collector — this function only judges gaps. The boundary case (gap
    exactly equal to the floor) passes: the window is a strict less-than
    refusal.
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

    git log emits FILE paths (never bare directories), so version
    directories are derived from the files inside them.

    The anchor is the committer timestamp of the commit that added this
    module; additions before it are the grandfathered history the rule was
    written against. Fails loud when that anchor is unreadable while the
    module exists on disk — under a shallow boundary git lists every
    standards file as Added at one timestamp, which without this guard
    would fabricate gap-0 verdicts instead of refusing to judge.
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
    if not anchor_raw and (root / _MODULE_RELATIVE).exists():
        raise TrainWindowError(
            "train_window_history_unreadable: the anchor commit (this "
            "module's own arrival) is unreachable but the module exists on "
            "disk — the history read is incomplete; fetch full history "
            "(fetch-depth: 0) before trusting any window verdict"
        )
    anchor = int(anchor_raw) if anchor_raw else 0

    # Chronological, oldest-first: git log walks newest first, and the
    # admission and dedup passes both need landing order.
    landed: dict[tuple[str, str], tuple[int, bool]] = {}
    for block in sorted(_split_log(raw), key=lambda item: item.timestamp):
        standards_in_commit: dict[str, str] = {}
        for path in block.paths:
            match = _VERSION_PATH.match(path)
            if match:
                standards_in_commit[match.group(1)] = match.group(2)
        is_reset_class = len(standards_in_commit) >= RESET_CLASS_STANDARD_COUNT
        for standard, version in standards_in_commit.items():
            key = (standard, version)
            if key not in landed or block.timestamp < landed[key][0]:
                landed[key] = (block.timestamp, is_reset_class)

    by_standard: dict[str, list[tuple[int, str, bool]]] = {}
    for (standard, version), (timestamp, exempt) in sorted(landed.items()):
        by_standard.setdefault(standard, []).append((timestamp, version, exempt))
    entries: list[BumpEntry] = []
    for standard, versions in by_standard.items():
        versions.sort()
        # Admission is the standard's chronological FIRST version over all
        # history, exempt-flag included — a version that arrived in a
        # reset-class commit is still that standard's first, so the next
        # bump after a reset is judged, not silently admitted.
        first_version = versions[0][1]
        for timestamp, version, exempt in versions:
            if timestamp < anchor or exempt or version == first_version:
                continue
            entries.append(BumpEntry(standard, version, timestamp))
    return tuple(sorted(entries, key=lambda item: item.timestamp))


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
    """Split `--format=%ct%x00%H --name-only` output into per-commit blocks.

    A header line carries an all-digit timestamp before the NUL; accepting
    any digit run (not a fixed hash length) keeps parsing correct under
    SHA-256 object format.
    """

    blocks: list[_LogBlock] = []
    current_timestamp: int | None = None
    current_paths: list[str] = []
    for line in raw.splitlines():
        if not line:
            continue
        header = line.split("\x00", 1)
        if len(header) == 2 and header[0].isdigit():
            if current_timestamp is not None:
                blocks.append(_LogBlock(current_timestamp, tuple(current_paths)))
            current_timestamp = int(header[0])
            current_paths = []
        elif current_timestamp is not None:
            current_paths.append(line)
    if current_timestamp is not None:
        blocks.append(_LogBlock(current_timestamp, tuple(current_paths)))
    return blocks
