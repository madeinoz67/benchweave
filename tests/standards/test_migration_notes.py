"""SM-5: a MINOR bump carries a from-predecessor migration note (#219, E2).

VR-36/SM-5, acceptance rule E2 of design §4: a MINOR bump fixture without a
from-predecessor note refuses; with one, it passes, and the release-review
walk (the compatibility matrix's per-version Migration note column) lists
it.

Arms: the real tree carries no un-noted post-adoption bump (the
deployment-state row); a scratch-repository family drives the gate
end-to-end with controlled dates — admission exempt, PATCH exempt, the
MINOR refusal, the noted-pass plus the walk, an unresolvable pointer (both
the missing file and the root-escape shapes), and the shallow-history
refusal. The scratch family is what makes the real-tree row non-vacuous.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
T0 = "2026-09-20T12:00:00+08:00"


def _commit(repo: Path, date: str, *paths_contents: tuple[str, str]) -> None:
    for relative, content in paths_contents:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "-m", "w"],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date,
        },
    )


def _manifest(
    version: str,
    *,
    note: str | None = None,
    versions: dict[str, dict[str, str]] | None = None,
) -> str:
    """A minimal-but-complete standards manifest (the render's inputs).

    ``note`` is the 0.2.0 shorthand the original arms use; ``versions``
    overrides the per-version rows outright (the fold arms need notes on
    other versions).
    """
    otdp_row: dict[str, object] = {
        "range": ">=0.1.0,<0.3.0",
        "yanked": {},
        "retired": [],
    }
    if versions is not None:
        otdp_row["versions"] = versions
    elif note is not None:
        otdp_row["versions"] = {"0.2.0": {"migration_note": note}}
    document = {
        "manifest_version": 1,
        "sdk_compatibility": {"sdk": "0.3.1", "main_project": ">=0.1.0", "notes": None},
        "dependency_policy": {
            "policy_version": 1,
            "standards": {"otdp": otdp_row},
        },
        "standards": [
            {
                "id": "otdp",
                "version": version,
                "status": "stable",
                "released": "2026-09-01",
                "normative": [f"standards/otdp/{version}/x.schema.json"],
            }
        ],
    }
    return json.dumps(document, indent=1)


def _corpus_manifest(*versions: str) -> str:
    return json.dumps(
        {
            "files": [
                {
                    "path": f"otdp/{version}/x.schema.json",
                    "sha256": "0" * 64,
                }
                for version in versions
            ]
        },
        indent=1,
    )


def _scratch_repo(tmp_path: Path) -> Path:
    """git init + this module's anchor stand-in (train_window's pattern:
    the gate's clock starts at ITS OWN first arrival, so every release the
    tree already carries is grandfathered by mechanism)."""
    repo = tmp_path / "scratch"
    repo.mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    _commit(
        repo,
        T0,
        ("src/benchweave/standards/migration_notes.py", "# anchor stand-in\n"),
    )
    return repo


def _seed_first_release(repo: Path) -> None:
    """otdp 0.1.0 — the standard's first version (admission, exempt)."""
    _commit(
        repo,
        "2026-09-20T13:00:00+08:00",
        ("standards/otdp/0.1.0/x.schema.json", "{}\n"),
        ("standards/standards-manifest.json", _manifest("0.1.0")),
        ("standards/corpus-manifest.json", _corpus_manifest("0.1.0")),
        ("pyproject.toml", (ROOT / "pyproject.toml").read_text()),
        (".gitmodules", (ROOT / ".gitmodules").read_text()),
    )


def _bump_minor(repo: Path) -> None:
    """otdp 0.1.0 -> 0.2.0 (the MINOR bump under test)."""
    _commit(
        repo,
        "2026-09-20T14:00:00+08:00",
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
        ("standards/standards-manifest.json", _manifest("0.2.0")),
        ("standards/corpus-manifest.json", _corpus_manifest("0.1.0", "0.2.0")),
    )


def _note_the_bump(repo: Path, pointer: str = "docs/migration/otdp-0.2.0.md") -> None:
    _commit(
        repo,
        "2026-09-20T15:00:00+08:00",
        ("standards/standards-manifest.json", _manifest("0.2.0", note=pointer)),
        (pointer, "# Migrating to otdp 0.2.0\n\nFixture note.\n"),
    )


def test_e2_a_minor_bump_without_a_note_refuses_and_with_one_the_walk_lists_it(
    tmp_path: Path,
) -> None:
    """E2, the whole sentence: refuse -> note -> pass -> the walk lists it."""
    from benchweave.standards.matrix import render_matrix
    from benchweave.standards.migration_notes import (
        MigrationNoteError,
        check_migration_notes,
    )

    repo = _scratch_repo(tmp_path)
    _seed_first_release(repo)
    assert check_migration_notes(repo) == (), "admission is exempt (first version)"

    _bump_minor(repo)
    with pytest.raises(MigrationNoteError, match=r"migration_note_missing: otdp 0.2.0"):
        check_migration_notes(repo)

    _note_the_bump(repo)
    assert check_migration_notes(repo) == (), "a noted MINOR bump passes (E2 arm 2)"

    # The release-review walk lists the note: the per-version matrix ROW
    # for the bumped version carries its from-predecessor pointer (the
    # summary table has a row with the same prefix — slice after the
    # per-version header so the assertion cannot land on it).
    from benchweave.standards.matrix import VERSION_HEADER

    rendered = render_matrix(repo)
    lines = rendered.splitlines()
    start = lines.index(VERSION_HEADER)
    row = next(
        line
        for line in lines[start + 2 :]
        if line.startswith("|") and line.startswith("| otdp | 0.2.0 |")
    )
    assert "docs/migration/otdp-0.2.0.md" in row, row


def test_a_post_anchor_patch_bump_needs_no_note(tmp_path: Path) -> None:
    """SM-5 is MUST for MINOR, SHOULD for PATCH: a patch bump (0.2.0 ->
    0.2.1) after an already-noted minor needs no note of its own."""
    from benchweave.standards.migration_notes import check_migration_notes

    repo = _scratch_repo(tmp_path)
    _seed_first_release(repo)
    _bump_minor(repo)
    _note_the_bump(repo)
    _commit(
        repo,
        "2026-09-20T16:00:00+08:00",
        ("standards/otdp/0.2.1/x.schema.json", "{}\n"),
        ("standards/corpus-manifest.json", _corpus_manifest("0.1.0", "0.2.0", "0.2.1")),
    )
    assert check_migration_notes(repo) == ()


def test_an_unresolvable_note_pointer_refuses(tmp_path: Path) -> None:
    """A note row whose pointer does not resolve to a file under the root
    refuses — both the missing-file shape and the root-escape shape (a
    pointer naming a file OUTSIDE the root is not a resolvable pointer)."""
    from benchweave.standards.migration_notes import (
        MigrationNoteError,
        check_migration_notes,
    )

    missing = _scratch_repo(tmp_path / "missing-parent")
    _seed_first_release(missing)
    _bump_minor(missing)
    _commit(
        missing,
        "2026-09-20T15:00:00+08:00",
        (
            "standards/standards-manifest.json",
            _manifest("0.2.0", note="docs/migration/absent.md"),
        ),
    )
    with pytest.raises(MigrationNoteError, match=r"migration_note_unresolved: otdp 0.2.0"):
        check_migration_notes(missing)

    escaping_parent = tmp_path / "escaping-parent"
    escaping_parent.mkdir()
    escaping = _scratch_repo(escaping_parent)
    _seed_first_release(escaping)
    _bump_minor(escaping)
    (escaping_parent / "outside.md").write_text("outside the root\n")
    _commit(
        escaping,
        "2026-09-20T15:00:00+08:00",
        (
            "standards/standards-manifest.json",
            _manifest("0.2.0", note="../outside.md"),
        ),
    )
    with pytest.raises(MigrationNoteError, match=r"migration_note_unresolved: otdp 0.2.0"):
        check_migration_notes(escaping)


def test_a_shallow_history_refuses_to_judge(tmp_path: Path) -> None:
    """A depth-1 clone grafts every standards file onto HEAD; the verdict
    would be laundered out of nothing. Refuse rather than judge (the
    train_window posture, mirrored)."""
    from benchweave.standards.migration_notes import (
        MigrationNoteError,
        check_migration_notes,
    )

    repo = _scratch_repo(tmp_path)
    _seed_first_release(repo)
    _bump_minor(repo)
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--no-local", str(repo), str(shallow)],
        check=True,
        capture_output=True,
    )
    with pytest.raises(MigrationNoteError, match="migration_note_history_unreadable"):
        check_migration_notes(shallow)


def test_real_tree_carries_no_unnoted_post_adoption_bump() -> None:
    """The deployment state: every MINOR bump the tree has landed since
    this gate's own arrival carries a note. Non-vacuity is the scratch
    family above — this row pins the real tree."""
    from benchweave.standards.migration_notes import check_migration_notes

    assert check_migration_notes(ROOT) == ()


# --- fold FIX A: the Add census must see copy-shaped Adds (#219 refute wave) ----


def test_the_add_census_covers_every_version_dir_in_the_tree() -> None:
    """Rename detection must not hide Adds from the shared census.

    Under default rename detection, git reclassifies a copy-never-move
    bump's file Adds as RENAMES of the predecessor's files and drops them
    from ``--diff-filter=A`` — measured on this tree, all six 0.1.0
    directories (the 2026-09-16 reset batch, each a copy of a pre-reset
    tree) were invisible to the default query. A census the gate cannot
    see is a bump the gate cannot judge (and, under lattice pairing, a
    missing lowest version mis-places the admission exemption). The
    property: every pure-semver version directory the TREE carries appears
    as a landed key — intersected with tree membership, so deleted-dir
    ghosts (the pre-reset numbers git still lists as Adds) do not count.
    """
    from benchweave.standards.manifest import VERSION_PATTERN
    from benchweave.standards.migration_notes import _landed_sequences

    landed = {
        (standard, version)
        for standard, entries in _landed_sequences(ROOT).items()
        for _timestamp, version in entries
    }
    tree = {
        (directory.parent.name, directory.name)
        for directory in (ROOT / "standards").glob("*/*")
        if directory.is_dir() and VERSION_PATTERN.fullmatch(directory.name)
    }
    assert tree, "the enumeration itself found nothing — the fixture broke"
    missing = sorted(tree - landed)
    assert not missing, (
        f"the Add census is blind to {missing} — rename detection "
        "reclassified their Adds; run the shared log with --no-renames"
    )


# --- fold FIX C: lattice pairing, not committer-timestamp pairing (#219 refute) ---


def _skewed_minor_bump(repo: Path, *, note_for_010: str | None = None) -> None:
    """0.1.0 landed at 13:00; the un-noted MINOR 0.2.0 committed with a
    committer date of 12:30 — ordinary clock skew, no forgery. Under
    timestamp pairing the sequence reads [0.2.0@12:30, 0.1.0@13:00]: the
    innocent 0.1.0 is judged as 'bumping from 0.2.0' and the real un-noted
    MINOR rides free behind the first-entry exemption."""
    versions = {"0.1.0", "0.2.0"}
    _commit(
        repo,
        "2026-09-20T13:00:00+08:00",
        ("standards/otdp/0.1.0/x.schema.json", "{}\n"),
        ("standards/standards-manifest.json", _manifest("0.1.0")),
        ("standards/corpus-manifest.json", _corpus_manifest(*sorted(versions))),
        ("pyproject.toml", (ROOT / "pyproject.toml").read_text()),
        (".gitmodules", (ROOT / ".gitmodules").read_text()),
    )
    note_rows = (
        {"0.1.0": {"migration_note": note_for_010}}
        if note_for_010 is not None
        else None
    )
    _commit(
        repo,
        "2026-09-20T12:30:00+08:00",  # skewed BEFORE the admission
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
        (
            "standards/standards-manifest.json",
            _manifest("0.2.0", versions=note_rows),
        ),
        ("standards/corpus-manifest.json", _corpus_manifest("0.1.0", "0.2.0")),
    )


def test_clock_skew_pairs_the_bump_with_its_lattice_predecessor(tmp_path: Path) -> None:
    """Lane B F2's repro, arm 1: the refusal must name the real un-noted
    MINOR (0.2.0, bumping FROM 0.1.0) — pairing and the admission exemption
    derive from the version lattice (semver, copy-never-move's own ground
    truth), with timestamps feeding ONLY the adoption cutoff."""
    from benchweave.standards.migration_notes import (
        MigrationNoteError,
        check_migration_notes,
    )

    repo = _scratch_repo(tmp_path)
    _skewed_minor_bump(repo)
    with pytest.raises(MigrationNoteError) as raised:
        check_migration_notes(repo)
    message = str(raised.value)
    assert "migration_note_missing: otdp 0.2.0 bumps from 0.1.0" in message, message
    assert "0.1.0 bumps from" not in message, message


def test_following_the_skewed_message_advice_does_not_go_clean(tmp_path: Path) -> None:
    """Lane B F2's repro, arm 2: the state today's skewed message tells you
    to author (a note on the INNOCENT 0.1.0) must not clean the gate — the
    real un-noted MINOR is still refusing. Remediation advice you can
    follow into a false clean is worse than no advice."""
    from benchweave.standards.migration_notes import (
        MigrationNoteError,
        check_migration_notes,
    )

    repo = _scratch_repo(tmp_path)
    _commit(repo, "2026-09-20T12:05:00+08:00", ("docs/migration/otdp-0.1.0.md", "n\n"))
    _skewed_minor_bump(repo, note_for_010="docs/migration/otdp-0.1.0.md")
    with pytest.raises(MigrationNoteError) as raised:
        check_migration_notes(repo)
    assert "migration_note_missing: otdp 0.2.0 bumps from 0.1.0" in str(raised.value)


def test_a_backport_patch_pairs_with_its_lattice_predecessor(tmp_path: Path) -> None:
    """The critic's mispair: landed [0.2.2, 0.3.0], then a 0.2.3 backport.
    Timestamp pairing reads 0.2.3 as bumping from 0.3.0 — MINOR-class,
    demanding a MUST note for a PATCH. Lattice order pairs 0.2.3 with 0.2.2
    (PATCH, SHOULD) and the gate goes clean."""
    from benchweave.standards.migration_notes import check_migration_notes

    repo = _scratch_repo(tmp_path)
    _commit(
        repo,
        "2026-09-20T13:00:00+08:00",
        ("standards/otdp/0.2.2/x.schema.json", "{}\n"),
        ("standards/standards-manifest.json", _manifest("0.2.2")),
        ("standards/corpus-manifest.json", _corpus_manifest("0.2.2")),
        ("pyproject.toml", (ROOT / "pyproject.toml").read_text()),
        (".gitmodules", (ROOT / ".gitmodules").read_text()),
    )
    _commit(
        repo,
        "2026-09-20T14:00:00+08:00",
        ("standards/otdp/0.3.0/x.schema.json", "{}\n"),
        (
            "standards/standards-manifest.json",
            _manifest(
                "0.3.0",
                versions={"0.3.0": {"migration_note": "docs/migration/otdp-0.3.0.md"}},
            ),
        ),
        ("docs/migration/otdp-0.3.0.md", "note\n"),
        ("standards/corpus-manifest.json", _corpus_manifest("0.2.2", "0.3.0")),
    )
    # The backport lands AFTER the minor it patches behind: 0.2.3 at 15:00,
    # un-noted, no corpus rows for it yet (a PATCH under lattice pairing).
    _commit(
        repo,
        "2026-09-20T15:00:00+08:00",
        ("standards/otdp/0.2.3/x.schema.json", "{}\n"),
        ("standards/corpus-manifest.json", _corpus_manifest("0.2.2", "0.2.3", "0.3.0")),
    )
    # 0.2.3 is un-noted: a PATCH under lattice pairing — clean is the call.
    assert check_migration_notes(repo) == ()
