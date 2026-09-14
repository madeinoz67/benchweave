"""Compatibility matrix: deterministic render, staleness gate, guidance."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

HEADER = (
    "| Standard | Schema/protocol version | Status | SDK version "
    "| Main-project range | Migration guidance | Sources |"
)


def _lock() -> dict[str, Any]:
    lock: dict[str, Any] = json.loads((ROOT / "packages/sdk/standards-lock.json").read_bytes())
    return lock


def _repo_copy(tmp_path: Path) -> Path:
    """Minimal root render_matrix reads: the canonical manifest tree."""
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "standards", repo / "standards")
    return repo


def _deprecated_repo(tmp_path: Path, notes: str | None) -> tuple[Path, Path]:
    """A one-standard (deprecated) manifest plus a lock carrying `notes`."""
    repo = tmp_path / "repo"
    (repo / "standards").mkdir(parents=True)
    document = json.loads((ROOT / "standards/standards-manifest.json").read_bytes())
    document["standards"] = [document["standards"][0]]
    document["standards"][0]["status"] = "deprecated"
    (repo / "standards/standards-manifest.json").write_text(json.dumps(document))
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    (sdk / "standards-lock.json").write_text(
        json.dumps(
            {
                "lock_version": 1,
                "standards": [
                    {"id": "otdp", "version": "0.3.0", "status": "deprecated", "files": []}
                ],
                "compatibility": {
                    "main_project": ">=0.1.0",
                    "sdk": "0.1.0",
                    "notes": notes,
                },
            }
        )
    )
    return repo, sdk


def test_render_carries_header_rows_sdk_and_main_floor() -> None:
    from benchweave.standards.manifest import load_manifest
    from benchweave.standards.matrix import render_matrix

    rendered = render_matrix(ROOT)
    assert HEADER in rendered
    for entry in load_manifest(ROOT).standards:
        assert f"| {entry.id} | {entry.version} | {entry.status} |" in rendered
    lock = _lock()
    assert str(lock["compatibility"]["sdk"]) in rendered
    assert str(lock["compatibility"]["main_project"]) in rendered


def test_render_excludes_the_submodule_sha() -> None:
    from benchweave.standards.check import submodule_sha
    from benchweave.standards.matrix import render_matrix

    rendered = render_matrix(ROOT)
    assert submodule_sha(ROOT / "packages/sdk") not in rendered


def test_render_is_byte_identical_across_calls() -> None:
    from benchweave.standards.matrix import render_matrix

    assert render_matrix(ROOT) == render_matrix(ROOT)


def test_committed_matrix_is_not_stale() -> None:
    from benchweave.standards.matrix import check_matrix

    assert check_matrix(ROOT) == []


def test_check_matrix_clean_when_committed_file_matches_render(tmp_path: Path) -> None:
    from benchweave.standards.matrix import check_matrix, render_matrix

    repo = _repo_copy(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs/compatibility-matrix.md").write_text(
        render_matrix(repo, ROOT / "packages/sdk"), encoding="utf-8"
    )
    assert check_matrix(repo, ROOT / "packages/sdk") == []


def test_check_matrix_reports_stale_committed_file(tmp_path: Path) -> None:
    from benchweave.standards.matrix import check_matrix

    repo = _repo_copy(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs/compatibility-matrix.md").write_text("# hand edited\n", encoding="utf-8")
    failures = check_matrix(repo, ROOT / "packages/sdk")
    assert failures
    assert failures[0].startswith("stale_matrix:")


def test_check_matrix_reports_missing_committed_file(tmp_path: Path) -> None:
    from benchweave.standards.matrix import check_matrix

    repo = _repo_copy(tmp_path)
    failures = check_matrix(repo, ROOT / "packages/sdk")
    assert failures
    assert failures[0].startswith("stale_matrix:")


def test_deprecated_standard_renders_migration_guidance(tmp_path: Path) -> None:
    from benchweave.standards.matrix import render_matrix

    repo, sdk = _deprecated_repo(
        tmp_path, "Migrate device profiles to the 0.4 catalog before upgrading."
    )
    rendered = render_matrix(repo, sdk)
    assert "| otdp | 0.3.0 | deprecated |" in rendered
    assert "Migrate device profiles to the 0.4 catalog before upgrading." in rendered


def test_deprecated_without_notes_marks_guidance_pending(tmp_path: Path) -> None:
    from benchweave.standards.matrix import render_matrix

    repo, sdk = _deprecated_repo(tmp_path, None)
    rendered = render_matrix(repo, sdk)
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
