"""SM-5: a MINOR bump carries a from-predecessor migration note (#219).

VR-36/SM-5 — each release carries a migration note from its predecessor,
MUST for MINOR, SHOULD for PATCH — and a gate refuses a MINOR bump without
one (design §3.5, acceptance rule E2). The carrier is the policy block's
per-version row (``versions.<v>.migration_note``, a repo-relative pointer);
the walk is the compatibility matrix's per-version Migration note column
(``matrix.render_matrix``), which release review reads.

Judgement, all from committed history plus the committed policy block:

- a **bump** is a version-directory addition whose (major, minor) line
  moved from the standard's previous landed version (PATCH-only motion is
  exempt — SHOULD, not MUST; the first version of a standard is its
  admission and is exempt);
- the clock **self-anchors** at this module's own first arrival, exactly
  like ``train_window``: every release the tree carried before SM-5's
  adoption is grandfathered by mechanism, never by a hand-maintained date
  (design record D6 — SM-5 is from adoption), so a root that has not
  landed this module judges nothing;
- a judged bump must find its per-version note row AND the pointer must
  resolve to an existing file under the root — an absolute or
  root-escaping pointer is not a resolvable pointer;
- a shallow repository refuses to judge (``migration_note_history_
  unreadable:``): a grafted boundary lists every standards file as Added
  at one timestamp and launders the verdict out of nothing.

The git-log grammar (``_split_log``, ``_VERSION_PATH``) is
``train_window``'s — one parser for one ``--format=%ct%x00%H --name-only``
shape in one package; two parsers for that format would be drift bait, the
lesson ``version_tuple``'s single-comparator comment records.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .manifest import load_dependency_policy, version_tuple
from .train_window import _VERSION_PATH, _split_log

# The anchor: this module's own arrival, in-history for the repo. DO NOT
# repoint (train_window's rule): the arrival commit of the ORIGINAL path is
# SM-5's ratification moment; repointing would re-anchor to a move commit
# and grandfather the interim history.
_MODULE_RELATIVE = "src/benchweave/standards/migration_notes.py"


class MigrationNoteError(ValueError):
    """A bump carries no resolvable from-predecessor note, or cannot be judged."""


@dataclass(frozen=True)
class NoteBump:
    """One judged bump: the release, and the version it bumped from."""

    standard: str
    version: str
    predecessor: str


def _git(root: Path, *arguments: str) -> str:
    # Argument-array form, no shell — trusted callers, fixed argv (the
    # S603 audit); PATH git is intended (S607), matching the package's CLI
    # posture. A git failure (no repository, unreadable history) refuses
    # by name — never a raw CalledProcessError.
    try:
        completed = subprocess.run(  # noqa: S603 — audited argument array
            ["git", "-C", str(root), *arguments],  # noqa: S607 — PATH lookup intended
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or f"git {' '.join(arguments)} failed"
        raise MigrationNoteError(
            f"migration_note_history_unreadable: git history unreadable ({detail}); "
            "fetch full history before judging any migration note"
        ) from exc
    return completed.stdout


def _anchor(root: Path) -> int | None:
    """The committer timestamp of this module's first arrival; None pre-landing.

    None means the gate's clock has not started (the module is not in this
    root's history yet): there is no post-adoption bump to judge, so the
    caller judges nothing. The shallow refusal runs before this ever
    matters — a grafted boundary is the state where an empty read would
    launder a verdict.
    """
    raw = _git(
        root,
        "log",
        "--diff-filter=A",
        "--format=%ct",
        "--reverse",
        "--",
        _MODULE_RELATIVE,
    )
    anchor_raw = next((line.strip() for line in raw.splitlines() if line.strip()), "")
    return int(anchor_raw) if anchor_raw else None


def _refuse_shallow(root: Path) -> None:
    shallow = _git(root, "rev-parse", "--is-shallow-repository").strip()
    if shallow == "true":
        raise MigrationNoteError(
            "migration_note_history_unreadable: shallow repository — a grafted "
            "boundary lists every standards file as Added at one timestamp and "
            "launders verdicts (clean or violated) out of nothing; fetch full "
            "history (fetch-depth: 0) before judging any migration note"
        )


def _landed_sequences(root: Path) -> dict[str, list[tuple[int, str]]]:
    """Every landed (standard, version) from git Adds, earliest add first.

    The census runs with ``--no-renames``: under default rename detection
    git reclassifies a copy-never-move bump's Adds as renames of the
    predecessor's files and DROPS them from ``--diff-filter=A`` — measured
    on this tree, all six 0.1.0 directories (the reset batch) were
    invisible to the default query while ``--no-renames`` sees every
    version directory the tree carries. One parser for both gates
    (train_window shares the fix).
    """
    raw = _git(
        root,
        "log",
        "--no-renames",
        "--diff-filter=A",
        "--format=%ct%x00%H",
        "--name-only",
        "--",
        "standards",
    )
    # Earliest add wins: iterate oldest-first, first sighting records the
    # timestamp (a straddled version dir counts once, at its first commit).
    landed: dict[tuple[str, str], int] = {}
    for block in sorted(_split_log(raw), key=lambda item: item.timestamp):
        for path in block.paths:
            match = _VERSION_PATH.match(path)
            if match:
                landed.setdefault((match.group(1), match.group(2)), block.timestamp)

    sequences: dict[str, list[tuple[int, str]]] = {}
    for (standard, version), timestamp in landed.items():
        sequences.setdefault(standard, []).append((timestamp, version))
    return sequences


def collect_note_bumps(root: Path) -> tuple[NoteBump, ...]:
    """Every post-adoption MINOR-or-greater bump, with its predecessor.

    Version-directory additions are read from git history (file paths git
    emits, derived to version directories — train_window's grammar,
    ``--no-renames`` so copy-shaped Adds stay Adds), one bump per
    (standard, version) at its earliest commit, ordered chronologically per
    standard. The predecessor is the version that came before it in that
    landed sequence — the version the bump copied from (copy-never-move
    keeps it in history either way). PATCH-only motion and everything
    landed before the anchor are exempt; the shallow history refuses to
    judge.
    """
    _refuse_shallow(root)
    anchor = _anchor(root)
    sequences = _landed_sequences(root)

    bumps: list[NoteBump] = []
    for standard, entries in sorted(sequences.items()):
        entries.sort(key=lambda item: (item[0], version_tuple(item[1])))
        # Each pair (previous, following): FOLLOWING is the bump, PREVIOUS
        # is what it bumped from — the standard's first entry is its
        # admission and pairs with nothing (never judged).
        for (_, previous), (timestamp, version) in zip(entries, entries[1:], strict=False):
            if version_tuple(version)[:2] == version_tuple(previous)[:2]:
                continue  # PATCH-only motion — SM-5 is SHOULD here
            if anchor is None or timestamp < anchor:
                continue  # pre-adoption: grandfathered by mechanism (D6)
            bumps.append(NoteBump(standard=standard, version=version, predecessor=previous))
    return tuple(bumps)


def check_migration_notes(root: Path) -> tuple[str, ...]:
    """Refuse (``MigrationNoteError``) when any judged bump lacks a note.

    Clean is ``()``. The refusal joins every violation the history carries
    (train_window's ``; `` join), each line one machine-matchable prefix:
    ``migration_note_missing:`` (no per-version row) or
    ``migration_note_unresolved:`` (a row whose pointer does not resolve
    to a file under the root).
    """
    bumps = collect_note_bumps(root)
    if not bumps:
        return ()
    policy = load_dependency_policy(root)
    violations: list[str] = []
    for bump in bumps:
        row = policy.standards.get(bump.standard)
        pointer = row.versions.get(bump.version) if row is not None else None
        if not pointer:
            violations.append(
                f"migration_note_missing: {bump.standard} {bump.version} bumps from "
                f"{bump.predecessor} with no from-predecessor migration note "
                "(VR-36/SM-5); add dependency_policy.standards."
                f"{bump.standard}.versions.{bump.version}.migration_note"
            )
            continue
        # resolve() before the containment check: is_relative_to is
        # lexical, so a ``..`` segment would otherwise stay "inside" the
        # root while naming a file outside it (an absolute pointer replaces
        # the root outright, the same refusal).
        resolved = root.joinpath(pointer).resolve()
        if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
            violations.append(
                f"migration_note_unresolved: {bump.standard} {bump.version} migration "
                f"note pointer {pointer!r} does not resolve to a file under the root"
            )
    if violations:
        raise MigrationNoteError("; ".join(violations))
    return ()
