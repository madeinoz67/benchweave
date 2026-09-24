"""Check command: non-mutating verification of the pinned SDK standards state."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _sdk_copy(tmp_path: Path) -> Path:
    """Minimal faithful copy of what run_check inspects: lock + vendored tree +
    pyproject (the anchor input, issue #187)."""
    source = ROOT / "packages/sdk"
    sdk = tmp_path / "sdk"
    (sdk / "src/benchweave_sdk").mkdir(parents=True)
    shutil.copy2(source / "standards-lock.json", sdk / "standards-lock.json")
    shutil.copytree(
        source / "src/benchweave_sdk/standards", sdk / "src/benchweave_sdk/standards"
    )
    shutil.copy2(source / "pyproject.toml", sdk / "pyproject.toml")
    return sdk


def _lock(sdk: Path) -> dict[str, Any]:
    lock: dict[str, Any] = json.loads((sdk / "standards-lock.json").read_bytes())
    return lock


def _write_lock(sdk: Path, lock: dict[str, Any]) -> None:
    (sdk / "standards-lock.json").write_text(json.dumps(lock))


def _prefixes(failures: list[str]) -> set[str]:
    return {line.split(":", 1)[0] for line in failures}


def _standards_root(tmp_path: Path) -> Path:
    """A non-git root carrying the real standards tree and parity validator.

    No gitlink and no submodule repository: both submodule-state SHAs read
    None, so run_check's mirror lane runs the lock-content comparison — the
    harness shape for feeding synthetic locks. (A detached sdk copy against
    ROOT itself is now refused as a submodule-state mismatch, correctly.)
    """
    root = tmp_path / "root"
    root.mkdir()
    shutil.copytree(ROOT / "standards", root / "standards")
    parity = root / "src/benchweave/presentation/contracts.py"
    parity.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "src/benchweave/presentation/contracts.py", parity)
    return root


def test_real_tree_is_clean() -> None:
    from benchweave.standards.check import run_check

    assert run_check(ROOT) == []


def test_cli_versions_fails_styled_on_an_invalid_identity_block(tmp_path: Path) -> None:
    """versions fails like check and repin do: styled error, exit 1, no traceback."""
    broken = tmp_path / "root"
    (broken / "standards").mkdir(parents=True)
    (broken / "standards/standards-manifest.json").write_bytes(
        (ROOT / "standards/standards-manifest.json").read_bytes()
    )
    (broken / "standards/corpus-manifest.json").write_text(json.dumps({"files": []}))
    (broken / "pyproject.toml").write_text('[project]\nname = "broken"\nversion = "0.0.0"\n')
    result = subprocess.run(
        [sys.executable, "-m", "benchweave.standards", "versions"],
        cwd=broken,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "standards versions error: identity_block_invalid" in combined
    assert "Traceback" not in combined, "the versions path must fail styled, not raw"


def test_version_mismatch_between_manifest_and_lock(tmp_path: Path) -> None:
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    lock["standards"][0]["version"] = "9.9.9"
    _write_lock(sdk, lock)
    failures = run_check(ROOT, sdk)
    assert "sdk_version_mismatch" in _prefixes(failures)


def test_tampered_vendored_file_is_hash_and_stale(tmp_path: Path) -> None:
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    victim = sdk / "src/benchweave_sdk/standards" / _lock(sdk)["standards"][0]["files"][0]["path"]
    victim.write_bytes(victim.read_bytes() + b" tampered\n")
    failures = run_check(ROOT, sdk)
    assert "hash_mismatch" in _prefixes(failures)
    assert "stale_generated" in _prefixes(failures)


def test_deleted_vendored_asset_is_missing(tmp_path: Path) -> None:
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    victim = sdk / "src/benchweave_sdk/standards" / _lock(sdk)["standards"][0]["files"][0]["path"]
    victim.unlink()
    failures = run_check(ROOT, sdk)
    assert "missing_asset" in _prefixes(failures)


def test_incomplete_compatibility_block_for_changed_standard(tmp_path: Path) -> None:
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    lock["standards"][0]["version"] = "9.9.9"  # changed vs manifest triggers the block
    del lock["compatibility"]
    _write_lock(sdk, lock)
    failures = run_check(ROOT, sdk)
    assert "compatibility_incomplete" in _prefixes(failures)


def test_lock_omitting_standard_is_pin_incompatible(tmp_path: Path) -> None:
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    lock["standards"] = lock["standards"][1:]
    _write_lock(sdk, lock)
    failures = run_check(ROOT, sdk)
    assert "pinned_sdk_incompatible" in _prefixes(failures)


def test_lock_digest_drift_at_same_version_is_content_drift(tmp_path: Path) -> None:
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    lock["standards"][1]["files"][0]["sha256"] = "0" * 64
    _write_lock(sdk, lock)
    failures = run_check(ROOT, sdk)
    assert "content_drift_without_version" in _prefixes(failures)


def test_unexpected_vendored_file_is_stale(tmp_path: Path) -> None:
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    stray = sdk / "src/benchweave_sdk/standards/otdp/leftover.json"
    stray.write_text("{}\n")
    failures = run_check(ROOT, sdk)
    assert "stale_generated" in _prefixes(failures)


def test_run_check_refuses_mirror_lock_drift(tmp_path: Path) -> None:
    """CON-12: the manifest sdk_compatibility mirror must track the SDK lock."""
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    lock["compatibility"]["sdk"] = "9.9.9"
    _write_lock(sdk, lock)
    failures = run_check(_standards_root(tmp_path), sdk)
    assert "sdk_compatibility_drift" in _prefixes(failures)


def test_mirror_drift_names_each_field(tmp_path: Path) -> None:
    """Each drifted key is its own named failure — one per field, not one blob."""
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    lock["compatibility"] = {
        "main_project": ">=9.0.0",
        "sdk": "9.9.9",
        "notes": "regenerated",
    }
    _write_lock(sdk, lock)
    failures = run_check(_standards_root(tmp_path), sdk)
    drift = sorted(line for line in failures if line.startswith("sdk_compatibility_drift:"))
    assert len(drift) == 3
    assert any(" manifest main_project=" in line for line in drift)
    assert any(" manifest sdk=" in line for line in drift)
    assert any(" manifest notes=" in line for line in drift)


def test_mirror_null_and_empty_notes_normalise_equal(tmp_path: Path) -> None:
    """The lock's nullable notes semantics: null and "" are the same value."""
    import json

    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    lock["compatibility"]["notes"] = ""
    _write_lock(sdk, lock)
    root = _standards_root(tmp_path)
    # Control the manifest side too: the live notes are whatever the current
    # landing carries, and this test owns the null-vs-empty pairing it pins.
    manifest = root / "standards" / "standards-manifest.json"
    m = json.loads(manifest.read_bytes())
    m["sdk_compatibility"]["notes"] = None
    manifest.write_text(json.dumps(m, indent=2))
    failures = run_check(root, sdk)
    assert "sdk_compatibility_drift" not in _prefixes(failures)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=BenchWeave Tests",
            "-c",
            "user.email=tests@example.invalid",
            # Local-path submodule clones need the file transport (refused by
            # default since git 2.38.1); this fixture only ever clones from
            # this repository's own pinned checkout into a temp dir.
            "-c",
            "protocol.file.allow=always",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        check=True,
    )


def _repo_with_submodule(tmp_path: Path) -> Path:
    """A real parent repo whose gitlink pins the real submodule checkout.

    The submodule is cloned from the local ``packages/sdk`` (HEAD at the
    gitlink the parent records), so moving it is one commit inside it — the
    maintainer's measured issue-#158 shape.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(ROOT / "standards", repo / "standards")
    parity = repo / "src/benchweave/presentation/contracts.py"
    parity.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "src/benchweave/presentation/contracts.py", parity)
    _git("init", cwd=repo)
    _git(
        "submodule",
        "add",
        "--name",
        "packages/sdk",
        str(ROOT / "packages/sdk"),
        "packages/sdk",
        cwd=repo,
    )
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "scratch: standards tree with the pinned submodule", cwd=repo)
    return repo


def _repo_with_uninitialized_submodule(tmp_path: Path) -> Path:
    """A real git root whose gitlink pins packages/sdk, never initialized.

    The directory exists with no ``.git`` inside — the plain-clone-before-init
    shape. git run inside it discovers the superproject, which is exactly the
    misattribution the refusal must not make.
    """
    from benchweave.standards.check import _pinned_sdk_sha

    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(ROOT / "standards", repo / "standards")
    parity = repo / "src/benchweave/presentation/contracts.py"
    parity.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "src/benchweave/presentation/contracts.py", parity)
    _git("init", cwd=repo)
    (repo / "packages/sdk").mkdir(parents=True)
    _git("add", "-A", cwd=repo)
    pinned = _pinned_sdk_sha(ROOT)
    assert pinned is not None
    _git("update-index", "--add", "--cacheinfo", f"160000,{pinned},packages/sdk", cwd=repo)
    _git("commit", "-m", "scratch: gitlink pinned, submodule never initialized", cwd=repo)
    return repo


def test_mirror_refusal_names_uninitialized_submodule(tmp_path: Path) -> None:
    """An uninitialized submodule is refused by name — never the
    superproject's HEAD misattributed as submodule state."""
    import re

    from benchweave.standards.check import run_check

    repo = _repo_with_uninitialized_submodule(tmp_path)
    failures = run_check(repo)
    state = [f for f in failures if f.startswith("sdk_compatibility_drift:")]
    assert len(state) == 1
    assert state[0].startswith(
        "sdk_compatibility_drift: submodule packages/sdk is not initialized"
    )
    assert "run git submodule update --init packages/sdk" in state[0]
    assert not re.search(r"[0-9a-f]{40}", state[0]), (
        "the uninitialized refusal carries no SHAs — a superproject HEAD must "
        "never be misattributed as submodule state"
    )
    # The anchor inherits the state gate: one refusal, no second family line.
    assert "sdk_version_unanchored" not in _prefixes(failures)


def test_mirror_refuses_moved_submodule_with_honest_message(tmp_path: Path) -> None:
    """CON-12: a working tree away from the gitlink is refused by name.

    Following a manifest edit there would mirror a version the gitlink does
    not pin — the message must point at the submodule state, never at
    standards-manifest.json.
    """
    from benchweave.standards.check import run_check

    repo = _repo_with_submodule(tmp_path)
    sdk = repo / "packages/sdk"
    lock = _lock(sdk)
    lock["compatibility"]["sdk"] = "0.0.5"
    _write_lock(sdk, lock)
    _git("add", "-A", cwd=sdk)
    _git("commit", "-m", "scratch: bump compatibility.sdk", cwd=sdk)
    failures = run_check(repo)
    assert len(failures) == 1
    assert failures[0].startswith(
        "sdk_compatibility_drift: submodule working tree is not at the pinned commit"
    )
    assert "run git submodule update --init packages/sdk" in failures[0]
    assert "update standards-manifest.json" not in failures[0]
    # The anchor inherits the same gate: the moved posture adds no second line.
    assert "sdk_version_unanchored" not in _prefixes(failures)
    # Restoring the pin greens the check: the pinned lock matches the mirror.
    _git("submodule", "update", "--init", "packages/sdk", cwd=repo)
    assert run_check(repo) == []


def test_mirror_refuses_non_string_lock_values_without_laundering(tmp_path: Path) -> None:
    """A non-string lock value is malformed and named as such — never
    str()-laundered into a comparison or a quoted '0' that reads as a string."""
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    lock["compatibility"]["sdk"] = 0
    lock["compatibility"]["notes"] = 0
    _write_lock(sdk, lock)
    failures = run_check(_standards_root(tmp_path), sdk)
    drift = [line for line in failures if line.startswith("sdk_compatibility_drift:")]
    assert len(drift) == 2
    assert any("SDK lock sdk is not a string or null (int)" in line for line in drift)
    assert any("SDK lock notes is not a string or null (int)" in line for line in drift)
    assert "'0'" not in "\n".join(drift)


# --- the compatibility.sdk anchor (issue #187 class closure) ------------------------


def test_sdk_version_anchor_catches_the_issue_187_replay(tmp_path: Path) -> None:
    """The #187 replay: lock and mirror staled TOGETHER — every existing lane green.

    Both committed sides carry the same stale version (the historical state that
    shipped broken in #187): ``sdk_compatibility_drift`` compares mirror to lock
    and both moved, so nothing reds. The anchor reads the pinned SDK's own
    pyproject and refuses by name — and only by name: no
    ``sdk_compatibility_drift`` line may appear (the two failures have different
    meanings and different fixes).
    """
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    pinned_version = lock["compatibility"]["sdk"]  # the true-pairing value
    lock["compatibility"]["sdk"] = "0.1.1"
    _write_lock(sdk, lock)
    root = _standards_root(tmp_path)
    manifest = root / "standards" / "standards-manifest.json"
    mirror = json.loads(manifest.read_bytes())
    mirror["sdk_compatibility"]["sdk"] = "0.1.1"
    manifest.write_text(json.dumps(mirror, indent=2))
    failures = run_check(root, sdk)
    unanchored = [f for f in failures if f.startswith("sdk_version_unanchored:")]
    assert len(unanchored) == 1, failures
    assert pinned_version in unanchored[0] and "0.1.1" in unanchored[0], failures


def test_sdk_version_anchor_refuses_unreadable_pinned_pyproject(tmp_path: Path) -> None:
    """A pinned pyproject that cannot be read is refused by name — never a pass,
    and never a degraded ``"unknown"`` comparison laundering the refusal."""
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    (sdk / "pyproject.toml").unlink()
    failures = run_check(_standards_root(tmp_path), sdk)
    unanchored = [f for f in failures if f.startswith("sdk_version_unanchored:")]
    assert len(unanchored) == 1, failures
    assert "cannot read" in unanchored[0] and "pyproject.toml" in unanchored[0], failures


def test_sdk_version_anchor_refuses_permission_broken_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pyproject that raises on open (permission bits) refuses by name —
    never a raw traceback out of run_check (governor fold F4, #187).

    The posture is simulated at the exact failure point (Path.open raising
    PermissionError for the pyproject alone): deterministic on every lane,
    including root, where real permission bits are bypassed. run_check's
    other Path.open reads (export, lock) are delegated untouched.
    """
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    target = sdk / "pyproject.toml"
    real_open = Path.open

    def deny(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == target:
            raise PermissionError(13, "Permission denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)
    failures = run_check(_standards_root(tmp_path), sdk)
    unanchored = [f for f in failures if f.startswith("sdk_version_unanchored:")]
    assert len(unanchored) == 1, failures
    assert "cannot read" in unanchored[0] and "pyproject.toml" in unanchored[0], failures


def test_sdk_version_anchor_refuses_undeclared_lock_sdk(tmp_path: Path) -> None:
    """An undeclared lock field is the original defect shape.

    The mirror lane also reds on this mutation (mirror still declares a version
    the lock no longer carries) — both red is honest, each names its own fix.
    """
    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    lock = _lock(sdk)
    lock["compatibility"]["sdk"] = None
    _write_lock(sdk, lock)
    failures = run_check(_standards_root(tmp_path), sdk)
    assert "sdk_version_unanchored" in _prefixes(failures)
    assert "sdk_compatibility_drift" in _prefixes(failures)


def test_sdk_version_anchor_greens_a_regenerated_pairing(tmp_path: Path) -> None:
    """The green control: a correctly regenerated pairing (#189 shape) never refuses.

    lock ``sdk`` == mirror ``sdk`` == pinned pyproject — the anchor adds no
    line. ``test_real_tree_is_clean`` carries the same proof against the live
    tree in CI; this pins the synthetic-fixture shape.
    """
    import tomllib

    from benchweave.standards.check import run_check

    sdk = _sdk_copy(tmp_path)
    root = _standards_root(tmp_path)
    with (sdk / "pyproject.toml").open("rb") as handle:
        pinned = str(tomllib.load(handle)["project"]["version"])
    mirror = json.loads((root / "standards" / "standards-manifest.json").read_bytes())
    lock = _lock(sdk)
    # Precondition: the untouched fixture copy IS the three-way-equal pairing —
    # this test guards the anchor's false-positive edge, so pin it explicitly.
    assert lock["compatibility"]["sdk"] == mirror["sdk_compatibility"]["sdk"] == pinned
    assert run_check(root, sdk) == []


# --- the RC candidate marker in the versions glance (devstage record §13.9) --------


def _glance_root(tmp_path: Path, dev_block: dict[str, object] | None) -> Path:
    """Minimal root for version_lines: pyproject, headed manifest, identity."""
    root = tmp_path / "repo"
    (root / "standards").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    entry: dict[str, object] = {
        "id": "demo",
        "version": "0.1.0",
        "status": "stable",
        "released": "2026-09-20",
        "normative": ["standards/demo/0.1.0/demo.schema.json"],
    }
    if dev_block is not None:
        entry["dev"] = dev_block
    (root / "standards/standards-manifest.json").write_text(
        json.dumps({"manifest_version": 1, "standards": [entry]}), encoding="utf-8"
    )
    (root / "standards/corpus-manifest.json").write_text(
        json.dumps({"files": [], "identity": {}}), encoding="utf-8"
    )
    return root


def _glance_lines(root: Path) -> list[str]:
    from benchweave.standards.check import version_lines

    sdk = root / "sdk"
    sdk.mkdir(exist_ok=True)
    (sdk / "standards-lock.json").write_text('{"standards": []}', encoding="utf-8")
    return version_lines(root, sdk)


_HEAD_NO_CANDIDATE: dict[str, object] = {
    "version": "0.2.0-dev",
    "opened": "2026-09-23",
    "normative": ["standards/demo/0.2.0-dev/demo.schema.json"],
}


def test_versions_glance_marks_a_candidate_head(tmp_path: Path) -> None:
    root = _glance_root(
        tmp_path, {**_HEAD_NO_CANDIDATE, "candidate": True}
    )
    lines = _glance_lines(root)
    assert (
        "standard demo dev-head 0.2.0-dev (opened 2026-09-23, release candidate)"
        in lines
    ), lines


def test_versions_glance_head_line_is_unchanged_without_the_marker(tmp_path: Path) -> None:
    # Absent and explicit-false render the SAME head line as before the
    # marker existed — the authoring state is byte-identical.
    for name, block in (
        ("absent", _HEAD_NO_CANDIDATE),
        ("explicit-false", {**_HEAD_NO_CANDIDATE, "candidate": False}),
    ):
        lines = _glance_lines(_glance_root(tmp_path / name, block))
        assert "standard demo dev-head 0.2.0-dev (opened 2026-09-23)" in lines, lines
