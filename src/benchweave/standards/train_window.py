"""Sync-completion pacing for the prescriptive release train (#451, G-5).

GOVERNANCE.md's G-5 amendment is enforced here, not remembered: a standard
may not bump while the same standard's previous released version's SDK leg
is outstanding — the commit adding a new pure-semver version directory of
standard S must arrive on a tree whose SDK lock already carries S's previous
released version. The lock is read at the bump commit's recorded ``packages/
sdk`` gitlink, from the submodule's object store: ``standards-lock.json``'s
rows are the carried set (retained ∧ in-range, yanked riding marked), and a
predecessor carried as yanked still counts — a yank is post-sync state, and
the release-ledger cost the rule prices was already paid.

What the rework keeps from #97: the collector skeleton (file paths derived
into version directories, a straddled directory counting once at its
earliest commit, the reset-class shape heuristic of three-or-more standards
in one commit, the chronological first version as the admission exemption,
``-dev`` directories invisible to the pure-semver regex), the fail-loud
postures (shallow repository, unreachable anchor), and self-anchoring. What
it drops: the wall clock — ``floor_seconds`` is gone, and two compliant
bumps an hour apart are now clean.

The clock self-anchors at the amendment's own arrival: the anchor is the
committer timestamp of the FIRST commit (oldest ``--reverse`` match) whose
``train_window.py`` content introduced ``ANCHOR_MARKER`` — found by pickaxe,
not a hand-maintained date — so history before the amendment is grandfathered
by mechanism. Delete-and-re-add cannot re-anchor (a move or delete matches
pickaxe, but the oldest match stays the amendment's arrival). Residual:
bumps are compared to the anchor by committer timestamp, so a post-amendment
commit carrying a skewed pre-amendment clock would be grandfathered — the
same residual the #97 mechanism carried. The lock read needs the submodule's
object store and runs lazily: only when a judged bump exists, so a tree with
no post-amendment bumps never needs the submodule. Uninitialized submodule,
an orphaned gitlink (the clone lacks the pinned object), or a malformed lock
is a typed ``train_window_history_unreadable`` refusal — fail-closed, never
a laundered pass.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

RESET_CLASS_STANDARD_COUNT = 3
"""Version directories for this many standards in one commit read as a reset."""

# The anchor query keys this exact path, so the needle is pinned beside it:
# the anchor is the first commit whose MODULE PATH introduced ANCHOR_MARKER.
# A later move of the module changes the occurrence count and matches
# pickaxe, but the oldest match stays the amendment's arrival — the same
# oldest-first discipline that made the #97 anchor delete-and-re-add safe.
_MODULE_RELATIVE = Path("src/benchweave/standards/train_window.py")
_SDK_RELATIVE = Path("packages/sdk")
_SDK_LOCK = "standards-lock.json"
_VERSION_PATH = re.compile(r"^standards/([a-z0-9-]+)/(\d+\.\d+\.\d+)/")

ANCHOR_MARKER = "train_window:g5-sync-completion-anchor"
"""The pickaxe needle: the amendment's arrival is the first commit whose
module path contains this literal. The test file pins the same literal; a
needle move without the test's copy strands every scratch anchor loudly."""

class TrainWindowError(ValueError):
    """A bump outran its predecessor's SDK leg (prefixed, machine-matchable)."""

@dataclass(frozen=True)
class BumpEntry:
    """One judged bump: the version landed, its commit, the version before it."""

    standard: str
    version: str
    commit: str
    predecessor: str


CarriedReader = Callable[[str], frozenset[tuple[str, str]]]
"""Commit -> the carried (id, version) pairs of the SDK lock pinned there."""


def sync_completion_violations(
    entries: tuple[BumpEntry, ...], carried_at: CarriedReader
) -> tuple[str, ...]:
    """Return one prefixed message per bump the pinned lock cannot justify.

    Exemptions (admission, reset-class, pre-anchor) are applied upstream by
    the collector; this function only judges carriage. A yanked predecessor
    row counts as carried — the reader includes yanked rows in the set.
    """

    messages: list[str] = []
    for entry in sorted(
        entries, key=lambda item: (item.standard, item.version, item.commit)
    ):
        if (entry.standard, entry.predecessor) not in carried_at(entry.commit):
            messages.append(
                f"train_window_violation: {entry.standard} "
                f"{entry.predecessor} -> {entry.version} "
                f"arrived at {entry.commit[:12]} before its predecessor "
                f"{entry.predecessor} completed its SDK leg (the SDK lock "
                "pinned at that commit carries no such row); the bump must "
                "wait for the predecessor's SDK sync to land "
                "(GOVERNANCE.md G-5)"
            )
    return tuple(messages)


def _git(root: Path, *arguments: str) -> str:
    # Argument-array form: no shell, no interpolation — the program is the
    # literal "git" and every argument is a repo path or a module constant
    # from trusted callers, never request data (the S603 audit); "git" from
    # PATH is the intent (S607), matching the daemon's own CLI posture.
    completed = subprocess.run(  # noqa: S603 — audited argument array
        ["git", "-C", str(root), *arguments],  # noqa: S607 — PATH lookup intended
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _version_key(version: str) -> tuple[int, int, int]:
    """Semver order for landing sequences; the version regex admits only
    three-component numeric versions, so the unpack is total."""

    major, minor, patch = version.split(".")
    return (int(major), int(minor), int(patch))


def collect_bump_entries(root: Path) -> tuple[BumpEntry, ...]:
    """Judged bumps: post-anchor, non-admission, non-reset-class, each
    carrying the previous released version its commit's lock must include."""

    landing, anchor = _landing(root)
    entries: list[BumpEntry] = []
    for standard, versions in landing.items():
        first_version = versions[0][2]
        previous: str | None = None
        for timestamp, commit, version, exempt in versions:
            predecessor = previous if previous is not None else ""
            previous = version
            if timestamp < anchor or exempt or version == first_version:
                continue
            entries.append(BumpEntry(standard, version, commit, predecessor))
    return tuple(entries)


def check_train_windows(root: Path) -> tuple[str, ...]:
    """Full enforcement entry: collect, then judge against the pinned locks.
    Raises on violation. The lock read is lazy: a tree with no judged bumps
    never touches the submodule."""

    violations = sync_completion_violations(
        collect_bump_entries(root), _carried_at(root)
    )
    if violations:
        raise TrainWindowError("; ".join(violations))
    return violations


def _landing(root: Path) -> tuple[dict[str, list[tuple[int, str, str, bool]]], int]:
    """Read the version-directory landing history into per-standard
    sequences, with the G-5 anchor timestamp alongside.

    Each (standard, version) lands once, at its earliest commit; ties on
    timestamp resolve to the non-exempt record so equal-dated commits are
    judged, not excused. The per-standard sequences are chronological by
    (timestamp, semver) — a same-commit double version keeps its two entries
    adjacent in semver order, which makes the higher version's predecessor
    the lower one (the stacking refusal).
    """

    raw = _git(
        root,
        "log",
        # --no-renames: default rename detection reclassifies a
        # copy-never-move bump's file Adds as renames of the predecessor's
        # files and DROPS them from --diff-filter=A (measured on this tree:
        # all six 0.1.0 reset-batch directories invisible to the default
        # query). A bump the census cannot see is a window the rule never
        # judges — the same fix migration_notes' census carries (#219
        # refute wave, FIX A).
        "--no-renames",
        "--diff-filter=A",
        "--format=%ct%x00%H",
        "--name-only",
        "--",
        "standards",
    )
    if (
        _git(root, "rev-parse", "--is-shallow-repository").strip() == "true"
        and (root / _MODULE_RELATIVE).exists()
    ):
        raise TrainWindowError(
            "train_window_history_unreadable: shallow repository — a grafted "
            "boundary lists every standards file as Added at one timestamp "
            "and launders verdicts (clean or violated) out of nothing; "
            "fetch full history (fetch-depth: 0) before judging any window"
        )
    # The anchor is the FIRST introduction of the marker in this module's
    # path (oldest --reverse match) — the G-5 amendment's own arrival. A
    # delete + re-add of the module matches pickaxe too, but the oldest
    # match stays the amendment: a revert and re-land cannot re-anchor the
    # clock and grandfather standing verdicts.
    anchor_lines = [
        line
        for line in _git(
            root,
            "log",
            "--reverse",
            f"-S{ANCHOR_MARKER}",
            "--format=%ct",
            "--",
            str(_MODULE_RELATIVE),
        ).splitlines()
        if line.strip()
    ]
    if not anchor_lines and (root / _MODULE_RELATIVE).exists():
        raise TrainWindowError(
            "train_window_history_unreadable: the anchor commit (the first "
            "arrival of this module's G-5 marker) is unreachable but the "
            "module exists on disk — the history read is incomplete; fetch "
            "full history (fetch-depth: 0) before trusting any window verdict"
        )
    anchor = int(anchor_lines[0]) if anchor_lines else 0

    landed: dict[tuple[str, str], tuple[int, str, bool]] = {}
    for block in reversed(_split_log(raw)):
        pairs: set[tuple[str, str]] = set()
        for path in block.paths:
            match = _VERSION_PATH.match(path)
            if match:
                pairs.add((match.group(1), match.group(2)))
        is_reset_class = len({standard for standard, _ in pairs}) >= (
            RESET_CLASS_STANDARD_COUNT
        )
        for key in sorted(pairs, key=lambda key_: (key_[0], _version_key(key_[1]))):
            if key not in landed or (block.timestamp, is_reset_class) < (
                landed[key][0],
                landed[key][2],
            ):
                landed[key] = (block.timestamp, block.commit, is_reset_class)

    landing: dict[str, list[tuple[int, str, str, bool]]] = {}
    for (standard, version), (timestamp, commit, exempt) in sorted(
        landed.items(),
        key=lambda item: (item[1][0], item[0][0], _version_key(item[0][1])),
    ):
        landing.setdefault(standard, []).append(
            (timestamp, commit, version, exempt)
        )
    return landing, anchor


def _carried_at(root: Path) -> CarriedReader:
    """A cached reader of the SDK lock's carried set at historical pins.
    Every unreadable posture is a typed refusal — the check never guesses."""

    cache: dict[str, frozenset[tuple[str, str]]] = {}

    def read(commit: str) -> frozenset[tuple[str, str]]:
        if commit not in cache:
            cache[commit] = _sdk_lock_carried(root, commit)
        return cache[commit]

    return read


def _sdk_lock_carried(root: Path, commit: str) -> frozenset[tuple[str, str]]:
    """The carried (id, version) pairs of the SDK lock at ``commit``'s pin.

    The gitlink ``git ls-tree`` reads is what the bump commit itself arrived
    on — the pairing state the #187 anchor established as the authority.
    Yanked rows are included: a yank is post-sync state, so the predecessor
    an SDK leg already carried still counts.
    """

    listing = _git(root, "ls-tree", commit, str(_SDK_RELATIVE))
    tokens = listing.split()
    if len(tokens) < 3 or tokens[1] != "commit":
        raise TrainWindowError(
            f"train_window_history_unreadable: commit {commit[:12]} records "
            f"no {_SDK_RELATIVE} gitlink — the SDK lock state the bump "
            "arrived on cannot be read; the sync-completion verdict is "
            "unknowable here"
        )
    link = tokens[2]
    sdk = root / _SDK_RELATIVE
    if not (sdk / ".git").exists():
        raise TrainWindowError(
            "train_window_history_unreadable: submodule packages/sdk is not "
            "initialized; run git submodule update --init packages/sdk "
            "before judging any sync-completion window"
        )
    # Argument-array form, unchecked return handled below: a missing object
    # (the orphaned-pin class) is a typed refusal, not a traceback.
    completed = subprocess.run(  # noqa: S603 — audited argument array
        ["git", "-C", str(sdk), "show", f"{link}:{_SDK_LOCK}"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise TrainWindowError(
            f"train_window_history_unreadable: the SDK lock at submodule "
            f"pin {link[:12]} (commit {commit[:12]}) is unreadable: the "
            "submodule clone lacks the pinned object — fetch full "
            "submodule history (fetch-depth: 0) before judging any "
            "sync-completion window"
        )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise TrainWindowError(
            f"train_window_history_unreadable: the SDK lock at submodule "
            f"pin {link[:12]} (commit {commit[:12]}) is not valid JSON: "
            f"{error}"
        ) from error
    rows = document.get("standards") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        raise TrainWindowError(
            f"train_window_history_unreadable: the SDK lock at submodule "
            f"pin {link[:12]} (commit {commit[:12]}) has malformed "
            "standards rows; the carried set cannot be read from it"
        )
    carried: set[tuple[str, str]] = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not isinstance(row.get("version"), str)
        ):
            raise TrainWindowError(
                f"train_window_history_unreadable: the SDK lock at submodule "
                f"pin {link[:12]} (commit {commit[:12]}) has a malformed "
                "row; the carried set cannot be read from it"
            )
        carried.add((row["id"], row["version"]))
    return frozenset(carried)


@dataclass(frozen=True)
class _LogBlock:
    timestamp: int
    commit: str
    paths: tuple[str, ...]


def _split_log(raw: str) -> list[_LogBlock]:
    """Split `--format=%ct%x00%H --name-only` output into per-commit blocks.

    A header line carries an all-digit timestamp before the NUL; accepting
    any digit run (not a fixed hash length) keeps parsing correct under
    SHA-256 object format.
    """

    blocks: list[_LogBlock] = []
    current: _LogBlock | None = None
    for line in raw.splitlines():
        if not line:
            continue
        header = line.split("\x00", 1)
        if len(header) == 2 and header[0].isdigit():
            if current is not None:
                blocks.append(current)
            current = _LogBlock(int(header[0]), header[1].strip(), ())
        elif current is not None:
            current = _LogBlock(
                current.timestamp, current.commit, (*current.paths, line)
            )
    if current is not None:
        blocks.append(current)
    return blocks
