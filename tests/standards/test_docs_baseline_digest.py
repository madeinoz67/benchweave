# author: Stephen Eaton
"""The docs snapshot's file-set digest: the one line git refuses to merge
silently (issue #670).

Two branches that each add a different scanned document used to merge with
NO conflict. Each wrote the SAME ``file_count`` (git takes an identical
change once), and the ``files`` map did not help: a document with no version
literal gets no key there, and two different keys merge as two additions on
different lines. The merged tree then failed the counter
(``docs census changed: snapshot records N scanned files, found N+1``).

The snapshot now carries ``file_set_sha256``: a sha256 over the SORTED names
of every file the counter counts. Names only, never contents — a content
digest would conflict every document edit with every other. Two branches that
change the file set differently write two values to that one line, and git
stops. The counter recomputes the digest from its own scan on every run and
refuses a mismatch or an absent field.

The three arms are the mechanism as a real git conflict, the rule the
generator emits, and the counter's refusal of a hand-edited digest. Every
arm runs the REAL counter: the script is copied into a throwaway tree (it
anchors its roots on ``__file__``, never on the cwd) and invoked there, so a
digest in evidence is the code's own output and never the test's — the one
value the test writes is the forged digest of the tamper arms, which is the
point of them. The test recomputes each expected digest with its own
one-line rule.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
COUNTER = "scripts/standards/count_version_literals.py"
BASELINE = "scripts/standards/docs-literal-baseline.json"
DIGEST_FIELD = "file_set_sha256"

# A document with no version literal is the common case (16 of the 40 scanned
# on main at 7e94fe70). Five of the six merges that moved the census on
# 2026-11-28 added one: the baseline changed by its file_count line and by
# nothing in the files map.
PLAIN = "Plain prose, no version literal.\n"
CLAIMING = "Pins 0.17.4 here.\n"
# The base carries one document of each kind. The literal-carrying one gives
# the base a non-empty files map. With the single line ``"files": {}`` next
# to file_count, a branch that adds a literal-carrying document rewrites a
# line ADJACENT to the number both branches write, and git then conflicts
# for a reason that is not the digest: that arm would pass with no digest.
BASE_DOCS = {"docs/b.md": CLAIMING, "docs/c.md": PLAIN}
LEFT_NAMES = [*BASE_DOCS, "docs/a.md"]
RIGHT_NAMES = [*BASE_DOCS, "docs/e.md"]
ALL_NAMES = [*BASE_DOCS, "docs/a.md", "docs/e.md"]


def _expected_digest(names: list[str]) -> str:
    """The digest rule, written independently of the counter: sha256 over the
    sorted names, NUL-separated. No path can carry a NUL, so two different
    sets never share a preimage."""
    return hashlib.sha256("\0".join(sorted(names)).encode("utf-8")).hexdigest()


def _write(tree: Path, relative: str, body: str) -> None:
    target = tree / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")


def _scratch(tmp_path: Path, docs: dict[str, str]) -> Path:
    """A throwaway tree carrying the REAL counter and the manifest it pins its
    standard ids against. Nothing here is the real checkout."""
    tree = tmp_path / "tree"
    (tree / "scripts/standards").mkdir(parents=True)
    (tree / "standards").mkdir()
    shutil.copy(ROOT / COUNTER, tree / COUNTER)
    shutil.copy(
        ROOT / "standards/standards-manifest.json",
        tree / "standards/standards-manifest.json",
    )
    for relative, body in docs.items():
        _write(tree, relative, body)
    return tree


def _counter(tree: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run the tree's copy of the real counter."""
    return subprocess.run(
        [sys.executable, str(tree / COUNTER), *argv],
        capture_output=True,
        text=True,
        check=False,
    )


def _snapshot_text(text: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(text)
    return document


def _snapshot(tree: Path) -> dict[str, Any]:
    """The tree's generated baseline, parsed."""
    return _snapshot_text((tree / BASELINE).read_text(encoding="utf-8"))


def _records(document: dict[str, Any], names: list[str]) -> str:
    """The failure text of a digest assertion: what the snapshot records
    against what the rule gives for the names the counter counted."""
    return (
        f"the snapshot records {document.get(DIGEST_FIELD)!r} for {DIGEST_FIELD}; "
        f"the {len(names)} names the counter counts hash to {_expected_digest(names)}"
    )


def _git_env() -> dict[str, str]:
    """git's environment for the throwaway repository. The git configuration
    and the git variables of the surrounding process are left out, so an arm
    does not depend on the machine that runs it: no hook path, no signing, no
    conflict style, no GIT_DIR inherited from a hook."""
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    return env


def _git(tree: Path, *argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(tree),
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "merge.conflictstyle=merge",
            *argv,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    if check:
        assert result.returncode == 0, f"git {' '.join(argv)} failed:\n{result.stderr}"
    return result


def _commit(tree: Path, message: str) -> None:
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", message)


def _silent_merge_evidence(tree: Path, mode: str) -> str:
    """The RED text: git met the two branches with no conflict, and the
    counter refuses the tree that resulted."""
    after = _counter(tree, "--scope", "docs")
    return (
        f"git {mode} exited 0 and the baseline merged with no conflict; the "
        f"counter on the resulting tree exits {after.returncode}:\n"
        f"{after.stdout}{after.stderr}"
    )


def _conflict_hunk(text: str) -> tuple[list[str], list[str]]:
    """The lines of each side inside the file's ONE conflict hunk, in the
    default merge style (``<<<<<<<``, ``=======``, ``>>>>>>>``)."""
    lines = text.splitlines()
    opens = [index for index, line in enumerate(lines) if line.startswith("<<<<<<< ")]
    mids = [index for index, line in enumerate(lines) if line == "======="]
    closes = [index for index, line in enumerate(lines) if line.startswith(">>>>>>> ")]
    assert len(opens) == len(mids) == len(closes) == 1, (
        f"expected one conflict hunk, found {len(opens)}:\n{text}"
    )
    assert opens[0] < mids[0] < closes[0], text
    return lines[opens[0] + 1 : mids[0]], lines[mids[0] + 1 : closes[0]]


@pytest.mark.parametrize(
    ("mode", "left_body"),
    [
        pytest.param("merge", PLAIN, id="merge-plain"),
        pytest.param("rebase", PLAIN, id="rebase-plain"),
        pytest.param("merge", CLAIMING, id="merge-left-claims"),
    ],
)
def test_two_branches_that_add_a_different_file_conflict_on_the_baseline(
    tmp_path: Path, mode: str, left_body: str
) -> None:
    """The mechanism, as a real git conflict. Two branches from one base each
    add a different document under docs/ and regenerate the baseline through
    the real script; meeting them must stop ON THE BASELINE, with the two
    digests on the two sides of one hunk. The two plain arms are the incident
    (issue #666: both added files carried no literal, so the files map did not
    move and only file_count was written). RED at 7e94fe70: git merge and git
    rebase both exited 0 with no conflicted file, and the counter refused the
    resulting tree."""
    tree = _scratch(tmp_path, BASE_DOCS)
    _git(tree, "init", "-q", "-b", "base")
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    _commit(tree, "base: one document of each kind")

    _git(tree, "checkout", "-q", "-b", "left", "base")
    _write(tree, "docs/a.md", left_body)
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    _commit(tree, "left adds docs/a.md")

    _git(tree, "checkout", "-q", "-b", "right", "base")
    _write(tree, "docs/e.md", PLAIN)
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    _commit(tree, "right adds docs/e.md")

    # Each branch is green on its own tree: what stops below is not a broken branch.
    for branch in ("left", "right"):
        _git(tree, "checkout", "-q", branch)
        own = _counter(tree, "--scope", "docs")
        assert own.returncode == 0, f"{branch}: {own.stdout}{own.stderr}"

    if mode == "merge":
        _git(tree, "checkout", "-q", "left")
        meeting = _git(tree, "merge", "right", check=False)
    else:
        meeting = _git(tree, "rebase", "left", check=False)
    assert meeting.returncode != 0, _silent_merge_evidence(tree, mode)

    conflicted = _git(tree, "diff", "--name-only", "--diff-filter=U").stdout.split()
    assert conflicted == [BASELINE], meeting.stdout + meeting.stderr

    # One line, two values: each tip's digest is its own file set's, and the
    # hunk holds that line and nothing else.
    left = _snapshot_text(_git(tree, "show", f"left:{BASELINE}").stdout)
    right = _snapshot_text(_git(tree, "show", f"right:{BASELINE}").stdout)
    assert left.get(DIGEST_FIELD) == _expected_digest(LEFT_NAMES), _records(left, LEFT_NAMES)
    assert right.get(DIGEST_FIELD) == _expected_digest(RIGHT_NAMES), _records(right, RIGHT_NAMES)
    assert left[DIGEST_FIELD] != right[DIGEST_FIELD]
    ours, theirs = _conflict_hunk((tree / BASELINE).read_text(encoding="utf-8"))
    assert ours == [f'  "{DIGEST_FIELD}": "{left[DIGEST_FIELD]}",']
    assert theirs == [f'  "{DIGEST_FIELD}": "{right[DIGEST_FIELD]}",']

    # The repository stays workable: the generator alone resolves the conflict.
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    _git(tree, "add", BASELINE)
    if mode == "merge":
        _git(tree, "commit", "-q", "-m", "merge right: the generator resolved the baseline")
    else:
        _git(tree, "-c", "core.editor=true", "rebase", "--continue")
    settled = _counter(tree, "--scope", "docs")
    assert settled.returncode == 0, settled.stdout + settled.stderr
    resolved = _snapshot(tree)
    assert resolved["file_count"] == len(ALL_NAMES)
    assert resolved.get(DIGEST_FIELD) == _expected_digest(ALL_NAMES), _records(resolved, ALL_NAMES)


def test_a_refresh_emits_the_digest_of_the_names_it_counted(tmp_path: Path) -> None:
    """The generator's rule: the digest is the sha256 of the sorted names of
    every file it counted. The counter counts a document that carries no
    literal, the files map does not list it, so the digest is NOT the digest
    of the files keys. RED at 7e94fe70: the snapshot had no digest field."""
    names = ["docs/b.md", "docs/c.md", "docs/d.md"]
    tree = _scratch(tmp_path, {"docs/b.md": PLAIN, "docs/c.md": PLAIN, "docs/d.md": CLAIMING})
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    document = _snapshot(tree)
    assert document["file_count"] == len(names)
    assert document.get(DIGEST_FIELD) == _expected_digest(names), _records(document, names)
    assert sorted(document["files"]) == ["docs/d.md"], (
        "the files map lists only the document that carries a literal"
    )
    assert document[DIGEST_FIELD] != _expected_digest(sorted(document["files"]))


@pytest.mark.parametrize(
    ("added_body", "listed_in_files"),
    [
        pytest.param(CLAIMING, True, id="claiming"),
        pytest.param(PLAIN, False, id="plain"),
    ],
)
def test_an_added_file_moves_the_digest(
    tmp_path: Path, added_body: str, listed_in_files: bool
) -> None:
    """A file that joins the counted set moves the digest, whatever it
    carries. The plain arm is the #658 case: the files map does not change, so
    the digest is the only line that can carry the change to git. RED at
    7e94fe70: no digest field was emitted."""
    before_names = ["docs/b.md", "docs/d.md"]
    after_names = ["docs/b.md", "docs/c.md", "docs/d.md"]
    tree = _scratch(tmp_path, {"docs/b.md": PLAIN, "docs/d.md": CLAIMING})
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    before = _snapshot(tree)
    assert before.get(DIGEST_FIELD) == _expected_digest(before_names), _records(
        before, before_names
    )

    _write(tree, "docs/c.md", added_body)
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    after = _snapshot(tree)

    assert after.get(DIGEST_FIELD) == _expected_digest(after_names), _records(after, after_names)
    assert after[DIGEST_FIELD] != before[DIGEST_FIELD]
    assert (before["file_count"], after["file_count"]) == (2, 3)
    assert ("docs/c.md" in after["files"]) is listed_in_files


def test_an_edited_file_leaves_the_digest_alone(tmp_path: Path) -> None:
    """A document's CONTENT changes and the counted set does not: the digest
    does not move. This is what keeps the repository workable — a digest over
    contents would conflict every document edit with every other. The guard
    on the first digest stops the arm from passing on two absent fields. RED
    at 7e94fe70: no digest field was emitted."""
    names = ["docs/b.md", "docs/d.md"]
    tree = _scratch(tmp_path, {"docs/b.md": PLAIN, "docs/d.md": CLAIMING})
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    before_bytes = (tree / BASELINE).read_bytes()
    before = _snapshot(tree)
    assert before.get(DIGEST_FIELD) == _expected_digest(names), _records(before, names)

    _write(tree, "docs/d.md", CLAIMING + "Another claim, 9.9.9, and new prose.\n")
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    after_bytes = (tree / BASELINE).read_bytes()
    after = _snapshot(tree)

    assert after_bytes != before_bytes, "the refresh must rewrite the snapshot for the edit"
    assert after["files"]["docs/d.md"] == {"0.17.4": 1, "9.9.9": 1}
    # The counted set is the same before and after: same count, same files keys.
    assert (before["file_count"], after["file_count"]) == (len(names), len(names))
    assert sorted(after["files"]) == sorted(before["files"])
    assert after.get(DIGEST_FIELD) == before[DIGEST_FIELD], (
        f"the digest moved although the counted set did not: "
        f"{before[DIGEST_FIELD]} became {after.get(DIGEST_FIELD)}"
    )


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param("wrong-value", id="wrong-value"),
        pytest.param("removed", id="removed"),
    ],
)
def test_a_hand_edited_digest_is_refused(tmp_path: Path, tamper: str) -> None:
    """The counter verifies the field: a digest that is not the counted set's
    is a finding and a non-zero exit, and so is an absent field — a snapshot
    without its digest is exactly an un-regenerated baseline. RED at 7e94fe70:
    there was no digest to verify, so the counter exited 0 on the tampered
    file."""
    names = ["docs/b.md", "docs/c.md"]
    tree = _scratch(tmp_path, {"docs/b.md": PLAIN, "docs/c.md": CLAIMING})
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    generated = (tree / BASELINE).read_bytes()
    valid = _counter(tree, "--scope", "docs")
    assert valid.returncode == 0, valid.stdout + valid.stderr

    forged = "0" * 64 if _expected_digest(names) != "0" * 64 else "1" * 64
    document = _snapshot(tree)
    if tamper == "wrong-value":
        document[DIGEST_FIELD] = forged
    else:
        document.pop(DIGEST_FIELD, None)
    (tree / BASELINE).write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    refused = _counter(tree, "--scope", "docs")
    assert refused.returncode == 1, (
        f"the counter exited {refused.returncode} on a snapshot whose "
        f"{DIGEST_FIELD} was {tamper}:\n{refused.stdout}{refused.stderr}"
    )
    assert (tree / BASELINE).read_bytes() != generated, "the tamper did not change the snapshot"
    assert DIGEST_FIELD in refused.stdout, refused.stdout
    if tamper == "wrong-value":
        # The finding names the digest recorded and the digest the file set gives.
        assert "docs census digest mismatch" in refused.stdout, refused.stdout
        assert forged in refused.stdout, refused.stdout
        assert _expected_digest(names) in refused.stdout, refused.stdout
    else:
        assert "docs census digest absent" in refused.stdout, refused.stdout
    findings = [line for line in refused.stdout.splitlines() if line.startswith("  ")]
    assert len(findings) == 1, refused.stdout

    # The remedy is the generator, never a hand edit.
    assert _counter(tree, "--refresh-docs-baseline").returncode == 0
    assert (tree / BASELINE).read_bytes() == generated
    restored = _counter(tree, "--scope", "docs")
    assert restored.returncode == 0, restored.stdout + restored.stderr
