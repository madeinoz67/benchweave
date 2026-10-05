"""Wheels ship the lock-verified vendored standards tree, not checkout reach."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "packages" / "sdk" / "standards-lock.json"
STAMP_NAME = "_GENERATED.txt"

#: The leak detector's template exemption is a PATH PREFIX — the SDK
#: distribution's own `template/` root (`benchweave_sdk-<version>/template/`,
#: the force-included copier template the SDK's PKG-2 has carried since
#: #347 WS2/WS3) — never a bare "/template/" substring: a doctored member
#: outside that root must still RED (review fold F4 on PR #400).
_TEMPLATE_ROOT = re.compile(r"^benchweave_sdk-[^/]+/template/")
_FORBIDDEN_NAMES = {".gitignore", ".mcp.json", "AGENTS.md", "CLAUDE.md"}


def _sdk_leaks(sdist_names: list[str]) -> list[str]:
    """Repo-config members of an SDK sdist that must not ship: dotfiles,
    `.mcp.json`, `AGENTS.md`, `CLAUDE.md`, anything under `.claude/` — each
    a leak unless it sits under the distribution's own template root."""
    return [
        name
        for name in sdist_names
        if (
            Path(name).name in _FORBIDDEN_NAMES or "/.claude/" in f"/{name}"
        )
        and _TEMPLATE_ROOT.match(name) is None
    ]


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


def test_the_template_carve_out_is_prefix_bound() -> None:
    """The leak detector's template exemption is a path prefix, not a
    substring (review fold F4 on PR #400): the real template members stay
    green, a doctored member OUTSIDE the template root REDS, and the
    original catch (repo-root config) stays caught. RED at the substring
    form: `docs/template/.gitignore` passed untouched."""
    legit = [
        "benchweave_sdk-0.7.1/template/.claude/skills/benchweave-plugin-ui/SKILL.md.jinja",
        "benchweave_sdk-0.7.1/template/AGENTS.md.jinja",
        "benchweave_sdk-0.7.1/template/.copier-answers.yml.jinja",
    ]
    assert _sdk_leaks(legit) == []
    doctored = ["benchweave_sdk-0.7.1/docs/template/.gitignore"]
    assert _sdk_leaks(doctored) == doctored
    original_catch = ["benchweave_sdk-0.7.1/.claude/deep-review/README.md"]
    assert _sdk_leaks(original_catch) == original_catch


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
        # synthesized top-level validator module may remain in the wheel. The
        # frozen preview_assets bundle that was also asserted here died with
        # SDK 0.7.0 (the SA-PREVIEW exit, #309): deleted from the wheel
        # entirely — nothing preview-shaped may ship in it either.
        assert "benchweave_sdk/_presentation_contract.py" not in names
        assert not any(name.startswith("benchweave_sdk/contracts/") for name in names)
        assert not any(name.startswith("benchweave_sdk/preview_assets/") for name in names)
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
    # configuration ships past the declared include list. Caught
    # live in the issue-#71 fold — an unanchored "README.md" include matched
    # .claude/deep-review/README.md at depth, and hatchling force-includes
    # .gitignore into every sdist past include/exclude entirely (stopped in
    # the SDK's build hook; this pin is the main-side detector).
    # The SDK's PKG-2 carve-out (since #347 WS2/WS3, in the tree the 0.7.1
    # pointer advances to): the force-included copier template — copier.yml +
    # template/, including template/.claude/skills and the jinja agent
    # assets — is generated-PROJECT content that ships by design. The leak
    # detector catches repo config OUTSIDE that template root; the old pin
    # predated the template members entirely.
    leaked = _sdk_leaks(sdist_names)
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
