"""Compatibility matrix: deterministic render, staleness gate, guidance."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

HEADER = (
    "| Standard | Schema/protocol version | Status | SDK version "
    "| Main-project range | Migration guidance | Sources |"
)


def _repo_copy(tmp_path: Path) -> Path:
    """Minimal root render_matrix reads: manifest tree, pyproject, .gitmodules."""
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "standards", repo / "standards")
    shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
    shutil.copy2(ROOT / ".gitmodules", repo / ".gitmodules")
    return repo


def _deprecated_repo(tmp_path: Path, notes: str | None) -> Path:
    """A one-standard (deprecated) manifest whose mirror carries `notes`.

    The corpus manifest rides along: the per-version table enumerates
    retained versions from it (a committed input whose absence refuses,
    CON-12), while the manifest's trimmed entry set still drives the
    summary table and the rows the per-version table renders.
    """
    repo = tmp_path / "repo"
    (repo / "standards").mkdir(parents=True)
    shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
    shutil.copy2(ROOT / ".gitmodules", repo / ".gitmodules")
    shutil.copy2(
        ROOT / "standards/corpus-manifest.json", repo / "standards/corpus-manifest.json"
    )
    document = json.loads((ROOT / "standards/standards-manifest.json").read_bytes())
    document["standards"] = [document["standards"][0]]
    document["standards"][0]["status"] = "deprecated"
    document["sdk_compatibility"]["notes"] = notes
    (repo / "standards/standards-manifest.json").write_text(json.dumps(document))
    return repo


def test_render_carries_header_rows_sdk_and_main_floor() -> None:
    from benchweave.standards.manifest import load_manifest, load_sdk_compatibility
    from benchweave.standards.matrix import render_matrix

    rendered = render_matrix(ROOT)
    assert HEADER in rendered
    for entry in load_manifest(ROOT).standards:
        assert f"| {entry.id} | {entry.version} | {entry.status} |" in rendered
    compatibility = load_sdk_compatibility(ROOT)
    assert compatibility.sdk in rendered
    assert compatibility.main_project in rendered


def test_render_excludes_the_submodule_sha() -> None:
    from benchweave.standards.check import submodule_sha
    from benchweave.standards.matrix import render_matrix

    rendered = render_matrix(ROOT)
    assert submodule_sha(ROOT / "packages/sdk") not in rendered


def test_render_is_byte_identical_across_calls() -> None:
    from benchweave.standards.matrix import render_matrix

    assert render_matrix(ROOT) == render_matrix(ROOT)


def test_render_neutralises_newlines_in_operator_notes() -> None:
    """Operator-authored cells must never break the markdown table."""
    from benchweave.standards.matrix import _cell

    assert _cell("line one\nline two") == "line one line two"
    assert _cell("a|b") == "a\\|b"
    assert "\n" not in _cell("x\n\ny")


def test_committed_matrix_is_not_stale() -> None:
    from benchweave.standards.matrix import check_matrix

    assert check_matrix(ROOT) == []


def test_check_matrix_clean_when_committed_file_matches_render(tmp_path: Path) -> None:
    from benchweave.standards.matrix import check_matrix, render_matrix

    repo = _repo_copy(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs/compatibility-matrix.md").write_text(render_matrix(repo), encoding="utf-8")
    assert check_matrix(repo) == []


def test_check_matrix_reports_stale_committed_file(tmp_path: Path) -> None:
    from benchweave.standards.matrix import check_matrix

    repo = _repo_copy(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs/compatibility-matrix.md").write_text("# hand edited\n", encoding="utf-8")
    failures = check_matrix(repo)
    assert failures
    assert failures[0].startswith("stale_matrix:")


def test_check_matrix_reports_missing_committed_file(tmp_path: Path) -> None:
    from benchweave.standards.matrix import check_matrix

    repo = _repo_copy(tmp_path)
    failures = check_matrix(repo)
    assert failures
    assert failures[0].startswith("stale_matrix:")


def test_deprecated_standard_renders_migration_guidance(tmp_path: Path) -> None:
    from benchweave.standards.matrix import render_matrix

    repo = _deprecated_repo(
        tmp_path, "Migrate device profiles to the 0.4 catalog before upgrading."
    )
    rendered = render_matrix(repo)
    # The synthetic manifest mirrors the real entry, so the row names whatever
    # version the corpus currently carries — not a hardcoded one.
    entry = json.loads((repo / "standards/standards-manifest.json").read_bytes())["standards"][0]
    assert f"| {entry['id']} | {entry['version']} | deprecated |" in rendered
    assert "Migrate device profiles to the 0.4 catalog before upgrading." in rendered


def test_deprecated_without_notes_marks_guidance_pending(tmp_path: Path) -> None:
    from benchweave.standards.matrix import render_matrix

    repo = _deprecated_repo(tmp_path, None)
    rendered = render_matrix(repo)
    assert "migration guidance pending" in rendered


def test_cli_matrix_check_clean_on_real_repo() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "benchweave.standards", "matrix", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cli_matrix_check_exits_nonzero_when_stale(tmp_path: Path) -> None:
    repo = _repo_copy(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "benchweave.standards", "matrix", "--check"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "stale_matrix:" in result.stdout


def _checkout_copy(tmp_path: Path, name: str, *, fork_origin: bool) -> Path:
    """A plain-checkout copy: committed tree, no submodule contents, no remotes.

    The issue-#158 shape — correct committed bytes read from a hostile checkout.
    ``fork_origin`` additionally git-inits the copy and points ``origin`` at a
    fork, the remote whose URL the render used to bake into the Sources cell.
    """
    repo = tmp_path / name
    repo.mkdir()
    shutil.copytree(ROOT / "standards", repo / "standards")
    shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
    shutil.copy2(ROOT / ".gitmodules", repo / ".gitmodules")
    (repo / "docs").mkdir()
    shutil.copy2(ROOT / "docs/compatibility-matrix.md", repo / "docs/compatibility-matrix.md")
    if fork_origin:
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "git@github.com:example/benchweave.git",
            ],
            cwd=repo,
            capture_output=True,
            check=True,
        )
    return repo


def test_render_is_pure_of_checkout_state(tmp_path: Path) -> None:
    """CON-12: the render is a function of committed files, not checkout state."""
    from benchweave.standards.matrix import DOCS_PATH, render_matrix

    plain = _checkout_copy(tmp_path, "plain", fork_origin=False)
    fork = _checkout_copy(tmp_path, "fork", fork_origin=True)
    committed = (ROOT / DOCS_PATH).read_text(encoding="utf-8")
    assert render_matrix(plain) == committed, "a no-git plain checkout must render committed bytes"
    assert render_matrix(fork) == committed, "a fork remote must not move the render"


def test_check_matrix_green_without_submodule_and_with_fork_origin(tmp_path: Path) -> None:
    """Issue #158: matrix --check exits 0 on a fork-remote plain checkout."""
    fork = _checkout_copy(tmp_path, "fork", fork_origin=True)
    result = subprocess.run(
        [sys.executable, "-m", "benchweave.standards", "matrix", "--check"],
        cwd=fork,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_still_bites_on_manifest_change_without_submodule(tmp_path: Path) -> None:
    """Anti-softening control: no submodule, fork remote — a committed-input
    change still reds the gate."""
    from benchweave.standards.matrix import check_matrix

    repo = _checkout_copy(tmp_path, "fork", fork_origin=True)
    document = json.loads((repo / "standards/standards-manifest.json").read_bytes())
    # Bumping the active version past a live head's target would refuse at
    # load (dev_head_stale) before the stale-matrix bite could fire — the
    # synthetic bump drops any head the live manifest carried.
    document["standards"][0].pop("dev", None)
    document["standards"][0]["version"] = "9.9.9"
    (repo / "standards/standards-manifest.json").write_text(json.dumps(document))
    failures = check_matrix(repo)
    assert failures
    assert failures[0].startswith("stale_matrix:")


def test_gate_still_bites_on_matrix_hand_edit_without_submodule(tmp_path: Path) -> None:
    """Anti-softening control: a hand-edited committed row still reds the gate."""
    from benchweave.standards.matrix import check_matrix

    repo = _checkout_copy(tmp_path, "fork", fork_origin=True)
    committed = repo / "docs/compatibility-matrix.md"
    text = committed.read_text(encoding="utf-8")
    committed.write_text(text.replace("| stable |", "| draft |", 1), encoding="utf-8")
    failures = check_matrix(repo)
    assert failures
    assert failures[0].startswith("stale_matrix:")


def test_cli_matrix_check_fails_styled_without_pyproject(tmp_path: Path) -> None:
    """A missing committed source is a styled refusal, never a raw traceback
    (absent pyproject.toml raises OSError inside the render)."""
    repo = _checkout_copy(tmp_path, "nopyproject", fork_origin=False)
    (repo / "pyproject.toml").unlink()
    result = subprocess.run(
        [sys.executable, "-m", "benchweave.standards", "matrix", "--check"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "standards matrix error:" in combined
    assert "Traceback" not in combined, "the matrix lane must fail styled, not raw"


# --- E3: one row per retained version, from committed state (#219 slice 5) ---


def _version_table_rows(rendered: str, header: str) -> list[str]:
    """The per-version table's data rows: everything after the header's
    rule until the table ends."""
    lines = rendered.splitlines()
    start = lines.index(header)
    rows: list[str] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(line)
    return rows


def test_e3_one_row_per_retained_version_at_the_seed() -> None:
    """E3 half 1: one row per retained version — 16 rows at the seed.

    16 = the retained version directories enumerated from the corpus
    manifest across the six manifest standards at this commit (otdp 6,
    registry 2, execution 2, interface 1, plugin-ui 3, plugin-ui-preview
    2). The expected count is re-derived from the same mechanism the
    render uses, and the literal 16 pins the seed denominator: if either
    moves, the test names which.
    """
    from benchweave.standards.manifest import load_manifest, retained_versions
    from benchweave.standards.matrix import VERSION_HEADER, render_matrix

    rendered = render_matrix(ROOT)
    rows = _version_table_rows(rendered, VERSION_HEADER)
    expected = sum(
        len(retained_versions(ROOT, entry.id)) for entry in load_manifest(ROOT).standards
    )
    assert expected == 18, f"the seed retained-set denominator moved: {expected}"
    assert len(rows) == expected, (
        f"the matrix rendered {len(rows)} per-version rows, expected {expected} "
        "(one row per retained version)"
    )


def _committed_repo(tmp_path: Path) -> Path:
    """A git root whose inputs are COMMITTED (the CON-12 purity fixture)."""
    repo = _repo_copy(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "-m",
            "seed",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_DATE": "2026-09-27T12:00:00+08:00",
            "GIT_COMMITTER_DATE": "2026-09-27T12:00:00+08:00",
        },
    )
    return repo


def test_e3_a_working_tree_only_policy_edit_does_not_change_the_render(
    tmp_path: Path,
) -> None:
    """E3 half 2 (the CON-12 fork-injection control): the render reads
    committed state only.

    The named control edits the POLICY BLOCK (the new per-version inputs'
    home) with the edit left uncommitted; the render must not move a byte.
    The same working-tree write also bumps the manifest's active version —
    the input the pre-slice render DID read from the working tree — so the
    control cannot pass vacuously before the committed-state read lands
    (the RED arm). A dirty working tree is asserted before the second
    render, so the control can never pass because the edit failed to
    apply.
    """
    from benchweave.standards.matrix import render_matrix

    repo = _committed_repo(tmp_path)
    before = render_matrix(repo)

    manifest_path = repo / "standards/standards-manifest.json"
    document = json.loads(manifest_path.read_bytes())
    document["dependency_policy"]["standards"]["otdp"]["range"] = ">=0.2.2,<0.3.0"
    # Drop any live dev head first: bumping the active past a head's
    # target would refuse at load (dev_head_stale) — the pure render
    # input is the point of this arm.
    document["standards"][0].pop("dev", None)
    document["standards"][0]["version"] = "9.9.9"
    manifest_path.write_text(json.dumps(document))
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert dirty.stdout.strip(), "the working-tree edit must actually apply"
    committed = subprocess.run(
        ["git", "show", "HEAD:standards/standards-manifest.json"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    assert committed.stdout != manifest_path.read_bytes(), (
        "the edit must be working-tree-only (HEAD still carries the seed bytes)"
    )

    after = render_matrix(repo)
    assert after == before, (
        "a working-tree-only edit changed the render — the matrix reads "
        "committed state only (CON-12)"
    )


# --- fold FIX B: the committed-read fallback's breadth (#219 refute wave) ----------


def test_an_untracked_promotion_record_in_a_committed_tree_renders_nothing(
    tmp_path: Path,
) -> None:
    """Lane B's repro: a repo committed WITHOUT promotion-records.json,
    with an untracked copy dropped in carrying a promotion. The old
    fallback read the untracked bytes and rendered a 'promoted' stage cell
    that exists in NO commit — E3's KILL clause (the render reading
    non-committed state). Path-absent-at-HEAD is committed-absent: the
    optional input skips staging, the render never moves.
    """
    from benchweave.standards.matrix import render_matrix

    repo = _repo_copy(tmp_path)
    (repo / "standards/promotion-records.json").unlink()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    before = render_matrix(repo)
    assert "promoted" not in before, "precondition: the seed render carries no stage cell"

    record = {
        "promotion_record_version": 1,
        "records": [
            {
                "standard": "otdp",
                "target": "0.2.2",
                "dev_head": "0.2.2-dev",
                "dev_edit_sha": "0" * 40,
                "dev_tree_digest": "0" * 64,
                "landing_sha": "1" * 40,
            }
        ],
    }
    (repo / "standards/promotion-records.json").write_text(json.dumps(record))
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert dirty.stdout.strip(), "the untracked copy must actually be present"

    after = render_matrix(repo)
    assert after == before, (
        "an untracked file moved the render — bytes in no commit produced a "
        "rendered stage cell (CON-12: committed state only)"
    )
    assert "promoted" not in after


def test_a_poisoned_git_dir_cannot_flip_the_render_to_working_tree_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lane A's repro: a healthy repo with every input committed, a
    working-tree edit to the manifest, and GIT_DIR pointed at a broken
    directory. The old fallback treated the poisoned git failure as
    'no committed copy' and rendered the WORKING-TREE edit silently. The
    render must never emit bytes that exist in no commit: the environment
    cannot redirect the committed read, and a repo that exists but cannot
    be read refuses loudly rather than degrading.
    """
    from benchweave.standards.matrix import render_matrix

    repo = _committed_repo(tmp_path)
    before = render_matrix(repo)

    manifest_path = repo / "standards/standards-manifest.json"
    document = json.loads(manifest_path.read_bytes())
    document["standards"][0].pop("dev", None)
    document["standards"][0]["version"] = "9.9.9"
    manifest_path.write_text(json.dumps(document))

    broken = tmp_path / "broken-git-dir"
    broken.mkdir()
    (broken / "HEAD").write_text("garbage\n")
    monkeypatch.setenv("GIT_DIR", str(broken))

    after = render_matrix(repo)
    assert "9.9.9" not in after, (
        "a poisoned GIT_DIR flipped the render to working-tree bytes — the "
        "committed read must not silently degrade"
    )
    assert after == before
