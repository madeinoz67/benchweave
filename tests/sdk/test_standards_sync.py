"""SDK standards import verifies hashes, classifies changes and refuses drift."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# The SDK lives in the submodule; expose it to this workspace test module
# (same bootstrap as tests/sdk/test_sdk.py) before importing from it.
SDK_SRC = Path(__file__).resolve().parents[2] / "packages/sdk/src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from benchweave_sdk.standards_sync import SyncReport, sync  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _export(tmp_path: Path) -> Path:
    from benchweave.standards.export import export_bundle

    bundle = tmp_path / "bundle"
    export_bundle(ROOT, bundle)
    return bundle


def _synced_sdk(tmp_path: Path, bundle: Path) -> Path:
    sdk = tmp_path / "sdk"
    (sdk / "src/benchweave_sdk").mkdir(parents=True)
    (sdk / "src/benchweave_sdk/__init__.py").write_text("")
    sync(bundle, sdk)
    return sdk


def test_first_sync_writes_lock_and_vendored_tree(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    lock = json.loads((sdk / "standards-lock.json").read_bytes())
    assert {s["id"] for s in lock["standards"]} == {
        "otdp", "registry", "execution", "interface", "plugin-ui", "plugin-ui-preview"
    }
    stamp = sdk / "src/benchweave_sdk/standards/otdp/_GENERATED.txt"
    first_line = stamp.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("otdp/")
    # Stamps live beside files that stay byte-identical to the bundle; the
    # version in the stamp line is the bundle's, derived — never a literal
    # that goes stale at the next corpus bump.
    document = json.loads((bundle / "bundle-manifest.json").read_bytes())
    otdp_row = next(s for s in document["standards"] if s["id"] == "otdp")
    assert first_line.endswith(f"Generated from otdp@{otdp_row['version']} — do not edit")
    entry = otdp_row["files"][0]
    vendored = sdk / "src/benchweave_sdk/standards" / entry["path"]
    assert vendored.read_bytes() == (bundle / "files" / entry["path"]).read_bytes()


def test_check_mode_detects_tampered_file(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    victim = next((sdk / "src/benchweave_sdk/standards").rglob("*.json"))
    victim.write_text(victim.read_text() + " tampered")
    with pytest.raises(ValueError, match="hash_mismatch"):
        sync(bundle, sdk, check_only=True)


def test_unchanged_resync_is_noop_report(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    report = sync(bundle, sdk)
    assert report == SyncReport((), (), (), ())


def test_normative_change_without_version_bump_is_refused(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    document = json.loads((bundle / "bundle-manifest.json").read_bytes())
    target = next(s for s in document["standards"] if s["id"] == "otdp")
    asset = bundle / "files" / target["files"][0]["path"]
    asset.write_bytes(asset.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="standards_version_required"):
        sync(bundle, sdk)


def test_versioned_change_reports_changed(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    document = json.loads((bundle / "bundle-manifest.json").read_bytes())
    # Multi-version serving: the version-increment arm is the ACTIVE row's
    # succession; mutating a non-active carried row is add-plus-remove.
    from benchweave_sdk.served import active_version

    active = active_version("otdp")
    target = next(
        s for s in document["standards"] if s["id"] == "otdp" and s["version"] == active
    )
    asset = bundle / "files" / target["files"][0]["path"]
    asset.write_bytes(asset.read_bytes() + b"\n")
    target["files"][0]["sha256"] = hashlib.sha256(asset.read_bytes()).hexdigest()
    target["version"] = "0.3.1"
    (bundle / "bundle-manifest.json").write_bytes(
        (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    report = sync(bundle, sdk)
    assert report.changed == ("otdp@0.3.1",)


def test_status_only_deprecation_is_reported(tmp_path: Path) -> None:
    """stable -> deprecated at the same version and hashes is reportable, not silent."""
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    document = json.loads((bundle / "bundle-manifest.json").read_bytes())
    target = next(s for s in document["standards"] if s["id"] == "otdp")
    target["status"] = "deprecated"
    (bundle / "bundle-manifest.json").write_bytes(
        (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    report = sync(bundle, sdk)
    # The label names the row the status moved on (multi-version labels).
    assert report.deprecated == ("otdp@0.2.0",)
    assert report.changed == ()


def test_missing_bundle_file_is_vocabulary_prefixed(tmp_path: Path) -> None:
    """A manifest-listed file absent from files/ is a ValueError, not a bare OSError."""
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    victim = bundle / "files" / "registry/0.1.1/package-lock.schema.json"
    victim.unlink()
    with pytest.raises(ValueError, match="bundle_file_missing"):
        sync(bundle, sdk)


def test_corrupt_lock_is_vocabulary_prefixed(tmp_path: Path) -> None:
    """An unparsable lock is reported as lock_invalid, not a bare JSONDecodeError."""
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    (sdk / "standards-lock.json").write_text("{not json")
    with pytest.raises(ValueError, match="lock_invalid"):
        sync(bundle, sdk)


def test_check_command_exits_zero_on_clean_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import benchweave_sdk.standards_sync as standards_sync
    from benchweave_sdk import cli as sdk_cli

    monkeypatch.setattr(
        standards_sync, "sync", lambda *args, **kwargs: SyncReport((), (), (), ())
    )
    assert sdk_cli.main(["sync-standards", str(tmp_path), "--check"]) == 0


def test_check_command_exits_nonzero_on_nonempty_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import benchweave_sdk.standards_sync as standards_sync
    from benchweave_sdk import cli as sdk_cli

    monkeypatch.setattr(
        standards_sync,
        "sync",
        lambda *args, **kwargs: SyncReport(("otdp",), (), (), ()),
    )
    assert sdk_cli.main(["sync-standards", str(tmp_path), "--check"]) == 1


def test_check_command_exits_nonzero_on_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import benchweave_sdk.standards_sync as standards_sync
    from benchweave_sdk import cli as sdk_cli

    def _tampered(*args: object, **kwargs: object) -> SyncReport:
        raise ValueError("hash_mismatch: tampered")

    monkeypatch.setattr(standards_sync, "sync", _tampered)
    assert sdk_cli.main(["sync-standards", str(tmp_path), "--check"]) == 1


# --- --check with no bundle: the self-contained lane, no main-project export. ---


def test_self_check_clean_tree_verifies_without_bundle(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    assert sync(None, sdk, check_only=True) == SyncReport((), (), (), ())


def test_self_check_detects_tampered_file_without_bundle(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    victim = next((sdk / "src/benchweave_sdk/standards").rglob("*.json"))
    victim.write_text(victim.read_text() + " tampered")
    with pytest.raises(ValueError, match="hash_mismatch"):
        sync(None, sdk, check_only=True)


def test_self_check_detects_deleted_file_without_bundle(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    victim = next((sdk / "src/benchweave_sdk/standards").rglob("*.json"))
    victim.unlink()
    with pytest.raises(ValueError, match="hash_mismatch.*missing"):
        sync(None, sdk, check_only=True)


def test_self_check_detects_extra_file_without_bundle(tmp_path: Path) -> None:
    """A file in the tree the lock does not record would ride into wheels."""
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    stray = sdk / "src/benchweave_sdk/standards/otdp/EXTRA.txt"
    stray.write_text("not in the lock")
    with pytest.raises(ValueError, match="unexpected_vendored_file"):
        sync(None, sdk, check_only=True)


def test_self_check_detects_missing_stamp_without_bundle(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    (sdk / "src/benchweave_sdk/standards/otdp/_GENERATED.txt").unlink()
    with pytest.raises(ValueError, match="stamp_missing"):
        sync(None, sdk, check_only=True)


def test_no_bundle_without_check_flag_is_refused(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)
    with pytest.raises(ValueError, match="bundle_required"):
        sync(None, sdk)


def test_check_command_without_bundle_passes_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import benchweave_sdk.standards_sync as standards_sync
    from benchweave_sdk import cli as sdk_cli

    seen: dict[str, object] = {}

    def _capture(bundle: object, *, sdk_root: object, check_only: object) -> SyncReport:
        seen["bundle"] = bundle
        return SyncReport((), (), (), ())

    monkeypatch.setattr(standards_sync, "sync", _capture)
    assert sdk_cli.main(["sync-standards", "--check"]) == 0
    assert seen["bundle"] is None


def test_check_command_without_bundle_verifies_real_committed_tree() -> None:
    """End to end on the submodule itself: the CLI's no-bundle lane is clean."""
    from benchweave_sdk import cli as sdk_cli

    assert sdk_cli.main(["sync-standards", "--check"]) == 0


# --- #215 fix wave: the bump-class gate is pinned here too; narrowing reports. ---


def _manifest(bundle: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((bundle / "bundle-manifest.json").read_bytes())
    return document


def _rewrite_manifest(bundle: Path, document: dict[str, Any]) -> None:
    (bundle / "bundle-manifest.json").write_bytes(
        (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )


def _versioned_sdk(tmp_path: Path, version: str) -> Path:
    """A sync target whose pyproject names an SDK version (the gate's anchor)."""
    sdk = tmp_path / "sdk"
    (sdk / "src/benchweave_sdk").mkdir(parents=True)
    (sdk / "src/benchweave_sdk/__init__.py").write_text("")
    (sdk / "pyproject.toml").write_text(
        f'[project]\nname = "benchweave-sdk"\nversion = "{version}"\n', encoding="utf-8"
    )
    return sdk


def test_carried_set_change_without_an_sdk_bump_is_refused(tmp_path: Path) -> None:
    """F4 (#215), gateway twin: the two-sided gate's SDK leg is exercised
    through the submodule import — a carried-set change inside an unchanged
    declared range with an unmoved SDK version refuses ``sdk_bump_class_invalid:``.
    Neutralizing the gate in the SDK tree turns this test red (the mutation
    proof is recorded in the fix-wave record)."""
    import shutil

    bundle = _export(tmp_path)  # the real export carries dependency_policy + markers
    sdk = _versioned_sdk(tmp_path, "0.3.1")
    sync(bundle, sdk)  # anchors compatibility.sdk = 0.3.1 in the prior lock
    document = _manifest(bundle)
    template = next(
        s
        for s in document["standards"]
        if s["id"] == "otdp" and s["version"] == "0.2.2"
    )
    new_row = {**template, "version": "0.2.9", "active": False}
    new_row["files"] = [
        {
            "path": file["path"].replace("otdp/0.2.2/", "otdp/0.2.9/", 1),
            "sha256": file["sha256"],
        }
        for file in template["files"]
    ]
    for file in template["files"]:
        source = bundle / "files" / file["path"]
        target = bundle / "files" / file["path"].replace("otdp/0.2.2/", "otdp/0.2.9/", 1)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    document["standards"].append(new_row)
    _rewrite_manifest(bundle, document)
    with pytest.raises(ValueError, match="^sdk_bump_class_invalid: "):
        sync(bundle, sdk)


def test_range_change_with_a_patch_bump_is_refused(tmp_path: Path) -> None:
    """F4's second arm, gateway twin: a declared-range change is a MINOR-class
    SDK bump at least; a PATCH motion refuses."""
    bundle = _export(tmp_path)
    sdk = _versioned_sdk(tmp_path, "0.3.1")
    sync(bundle, sdk)
    document = _manifest(bundle)
    document["dependency_policy"]["standards"]["otdp"]["range"] = ">=0.2.1,<0.3.0"
    _rewrite_manifest(bundle, document)
    (sdk / "pyproject.toml").write_text(
        '[project]\nname = "benchweave-sdk"\nversion = "0.3.2"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="^sdk_bump_class_invalid: "):
        sync(bundle, sdk)


def test_range_narrowing_that_drops_a_carried_version_reports_it_removed(
    tmp_path: Path,
) -> None:
    """F5 (#215), gateway twin: a range-narrowing train must REPORT the
    dropped row under ``removed()`` — the active-succession branch used to
    consume the one remaining same-id row silently."""
    import shutil

    bundle = _export(tmp_path)
    sdk = _synced_sdk(tmp_path, bundle)  # the real export marks active/yanked + policy
    document = _manifest(bundle)
    document["dependency_policy"]["standards"]["otdp"]["range"] = ">=0.2.1,<0.3.0"
    rows = [r for r in document["standards"] if r["id"] != "otdp"]
    active_row = next(
        r
        for r in document["standards"]
        if r["id"] == "otdp" and r.get("active")
    )
    del active_row["active"]
    new_row = {**active_row, "version": "0.2.3", "active": True}
    new_row["files"] = [
        {
            "path": file["path"].replace("otdp/0.2.2/", "otdp/0.2.3/", 1),
            "sha256": file["sha256"],
        }
        for file in active_row["files"]
    ]
    for file in active_row["files"]:
        source = bundle / "files" / file["path"]
        target = bundle / "files" / file["path"].replace("otdp/0.2.2/", "otdp/0.2.3/", 1)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    otdp_rows = [
        r
        for r in document["standards"]
        if r["id"] == "otdp" and r["version"] != "0.2.0"
    ]
    document["standards"] = rows + otdp_rows + [new_row]
    _rewrite_manifest(bundle, document)
    report = sync(bundle, sdk)
    assert report.removed == ("otdp@0.2.0",)
    assert report.changed == ()
    assert report.added == ("otdp@0.2.3",)
    assert sync(None, sdk, check_only=True) == SyncReport((), (), (), ())
