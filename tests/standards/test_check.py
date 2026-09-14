"""Check command: non-mutating verification of the pinned SDK standards state."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _sdk_copy(tmp_path: Path) -> Path:
    """Minimal faithful copy of what run_check inspects: lock + vendored tree."""
    source = ROOT / "packages/sdk"
    sdk = tmp_path / "sdk"
    (sdk / "src/benchweave_sdk").mkdir(parents=True)
    shutil.copy2(source / "standards-lock.json", sdk / "standards-lock.json")
    shutil.copytree(
        source / "src/benchweave_sdk/standards", sdk / "src/benchweave_sdk/standards"
    )
    return sdk


def _lock(sdk: Path) -> dict[str, Any]:
    lock: dict[str, Any] = json.loads((sdk / "standards-lock.json").read_bytes())
    return lock


def _write_lock(sdk: Path, lock: dict[str, Any]) -> None:
    (sdk / "standards-lock.json").write_text(json.dumps(lock))


def _prefixes(failures: list[str]) -> set[str]:
    return {line.split(":", 1)[0] for line in failures}


def test_real_tree_is_clean() -> None:
    from benchweave.standards.check import run_check

    assert run_check(ROOT) == []


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
