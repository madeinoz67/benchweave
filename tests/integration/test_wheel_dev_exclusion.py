"""Wheels carry no dev-stage bytes (the devstage design record's F1 call)."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _build_surface(tmp_path: Path) -> Path:
    """A wheel-build copy of the repo with a dev directory planted.

    Copies only the surfaces a wheel build reads — pyproject, the readme it
    names, the packaged trees, the build hook — never the repo itself (a
    test must not mutate ROOT). The planted head is intentionally UNKNOWN to
    the manifests: the packaging-side exclusion is lexical and must hold
    even for a stray ``-dev`` directory governance has not admitted yet.
    """
    root = tmp_path / "surface"
    root.mkdir()
    for relative in ("pyproject.toml", "hatch_build.py", "LICENSE"):
        source = REPO / relative
        if source.is_file():
            shutil.copyfile(source, root / relative)
    (root / "docs").mkdir()
    shutil.copyfile(REPO / "docs/project-index.md", root / "docs/project-index.md")
    shutil.copytree(REPO / "src", root / "src")
    shutil.copytree(REPO / "standards", root / "standards")
    shutil.copytree(
        REPO / "plugins/benchweave",
        root / "plugins/benchweave",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "venv"),
    )
    dev = root / "standards/otdp/0.9.9-dev"
    dev.mkdir(parents=True)
    (dev / "staged.json").write_text('{"staged": true}\n', encoding="utf-8")
    return root


@pytest.mark.slow
def test_wheel_carries_no_dev_stage_bytes(tmp_path: Path) -> None:
    """F1 (ratified 2026-09-23): a wheel built while a head is open ships no
    ``-dev`` entries, and the exclusion narrows nothing else — the active
    contracts tree and the manifest files at its root ship exactly as the
    whole-tree force-include shipped them."""
    root = _build_surface(tmp_path)
    dist = tmp_path / "dist"
    built = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert built.returncode == 0, f"uv build failed:\n{built.stderr}"
    (wheel_path,) = dist.glob("benchweave-*.whl")
    with zipfile.ZipFile(wheel_path) as archive:
        names = archive.namelist()
    shipped = [name for name in names if "-dev/" in name]
    assert not shipped, f"dev-stage bytes shipped in the wheel: {shipped}"
    # Carriage preserved: an active version directory and the root manifests.
    assert any(
        name.startswith("benchweave/_vendored/contracts/otdp/0.2.0/") for name in names
    ), "the active contracts tree must keep shipping"
    for root_file in ("standards-manifest.json", "corpus-manifest.json"):
        assert f"benchweave/_vendored/contracts/{root_file}" in names


@pytest.mark.slow
def test_sdist_carriage_is_the_disclosed_posture(tmp_path: Path) -> None:
    """Row 7: the SDIST carries dev bytes BY CHOICE — the ratified F1 call
    names wheels, and the sdist is the repository's source tree. Pinned so
    the posture is a decision, not drift: an accidental exclusion (or a
    widening of the wheel rule) shows up here as a failing choice."""
    root = _build_surface(tmp_path)
    dist = tmp_path / "dist-sdist"
    built = subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(dist)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert built.returncode == 0, f"uv build failed:\n{built.stderr}"
    (archive,) = dist.glob("benchweave-*.tar.gz")
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    # Segment-suffix form (the wheel arm's convention): "-dev/" matches the
    # staged directory but never "otdp-device-descriptor" ("-devi", not "-dev/").
    dev_entries = [name for name in names if "-dev/" in name]
    assert dev_entries, (
        "the sdist lost its disclosed dev-byte carriage — posture drift, "
        "not a ruled change"
    )
