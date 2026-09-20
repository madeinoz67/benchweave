"""Wheels ship the lock-verified vendored standards tree, not checkout reach."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "packages" / "sdk" / "standards-lock.json"
STAMP_NAME = "_GENERATED.txt"


def _locked_files() -> dict[str, str]:
    assert LOCK_PATH.is_file(), (
        "packages/sdk/standards-lock.json missing; run benchweave-sdk sync-standards"
    )
    lock = json.loads(LOCK_PATH.read_bytes())
    files = {
        file["path"]: file["sha256"]
        for standard in lock["standards"]
        for file in standard["files"]
    }
    assert files, "standards-lock.json records no files"
    return files


def _assert_standards_tree(names: list[str], read: Callable[[str], bytes]) -> None:
    """The packaged standards tree is exactly the locked set plus its stamps."""
    expected = _locked_files()
    prefix = "benchweave_sdk/standards/"
    included = {name.removeprefix(prefix) for name in names if name.startswith(prefix)}
    stamps = {
        f"{identifier}/{STAMP_NAME}"
        for identifier in {path.partition("/")[0] for path in expected}
    }
    assert included == set(expected) | stamps
    for path, digest in sorted(expected.items()):
        assert hashlib.sha256(read(prefix + path)).hexdigest() == digest, path


def test_sdk_wheel_rebuilt_from_sdist_contains_locked_standards_tree(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", str(ROOT / "packages/sdk"), "--out-dir", str(dist)],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        _assert_standards_tree(names, archive.read)
        # The checkout reach is gone: no force-included contracts copy and no
        # synthesized top-level validator module may remain in the wheel.
        assert "benchweave_sdk/_presentation_contract.py" not in names
        assert not any(name.startswith("benchweave_sdk/contracts/") for name in names)
        inventory_path = "benchweave_sdk/preview_assets/inventory.json"
        inventory = json.loads(archive.read(inventory_path))
        assert inventory["api_version"] == 1
        assert inventory["assets"]
        for asset in inventory["assets"]:
            packaged = archive.read(f"benchweave_sdk/preview_assets/{asset['path']}")
            assert len(packaged) == asset["size"]
            assert hashlib.sha256(packaged).hexdigest() == asset["sha256"]
    # The vendored validator stays byte-identical to the gateway's canonical
    # source; the lock pins that exact digest.
    gateway_validator = ROOT / "src/benchweave/presentation/contracts.py"
    assert (
        hashlib.sha256(gateway_validator.read_bytes()).hexdigest()
        == _locked_files()["plugin-ui/contracts.py"]
    )
    unpacked = tmp_path / "source"
    unpacked.mkdir()
    with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
        sdist_names = archive.getnames()
        archive.extractall(unpacked, filter="data")
    source = next(unpacked.iterdir())
    assert (source / "standards-lock.json").is_file(), "sdist omits the standards lock"
    # PKG-2, pinned at the sdist too: no repo/VCS metadata or agent
    # configuration ships past the declared five-entry include list. Caught
    # live in the issue-#71 fold — an unanchored "README.md" include matched
    # .claude/deep-review/README.md at depth, and hatchling force-includes
    # .gitignore into every sdist past include/exclude entirely (stopped in
    # the SDK's build hook; this pin is the main-side detector).
    forbidden_files = {".gitignore", ".mcp.json", "AGENTS.md", "CLAUDE.md"}
    leaked = [
        name
        for name in sdist_names
        if Path(name).name in forbidden_files or "/.claude/" in f"/{name}"
    ]
    assert not leaked, f"sdist leaks repo files past the include list: {sorted(leaked)}"
    rebuilt = tmp_path / "rebuilt"
    subprocess.run(
        ["uv", "build", "--wheel", str(source), "--out-dir", str(rebuilt)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    with zipfile.ZipFile(next(rebuilt.glob("*.whl"))) as archive:
        _assert_standards_tree(archive.namelist(), archive.read)
        rebuilt_inventory = json.loads(
            archive.read("benchweave_sdk/preview_assets/inventory.json")
        )
        assert rebuilt_inventory == inventory
