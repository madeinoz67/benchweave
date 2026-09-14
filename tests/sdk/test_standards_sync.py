"""SDK standards import verifies hashes, classifies changes and refuses drift."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

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
    first_line = stamp.read_text().splitlines()[0]
    assert first_line.startswith("otdp/")
    assert first_line.endswith("Generated from otdp@0.3.0 — do not edit")
    # Stamps live beside files that stay byte-identical to the bundle.
    document = json.loads((bundle / "bundle-manifest.json").read_bytes())
    entry = next(s["files"][0] for s in document["standards"] if s["id"] == "otdp")
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
    target = next(s for s in document["standards"] if s["id"] == "otdp")
    asset = bundle / "files" / target["files"][0]["path"]
    asset.write_bytes(asset.read_bytes() + b"\n")
    target["files"][0]["sha256"] = hashlib.sha256(asset.read_bytes()).hexdigest()
    target["version"] = "0.3.1"
    (bundle / "bundle-manifest.json").write_bytes(
        (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    report = sync(bundle, sdk)
    assert report.changed == ("otdp",)
