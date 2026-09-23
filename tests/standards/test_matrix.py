"""Compatibility matrix: deterministic render, staleness gate, guidance."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

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
    """A one-standard (deprecated) manifest whose mirror carries `notes`."""
    repo = tmp_path / "repo"
    (repo / "standards").mkdir(parents=True)
    shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
    shutil.copy2(ROOT / ".gitmodules", repo / ".gitmodules")
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
