"""Manifest-driven version discovery (#102 D2): the validator's corpus
directory, report title, and the pin's report path derive from
standards-manifest.json's active otdp entry — never a hardcoded literal.

RED at the pre-change tree: OUT and REPORT_TITLE are hardcoded "0.2.0", so
a tmp standards tree whose manifest declares a different active otdp
version (a real, superseded-but-present dir) leaves them unmoved.
"""

from __future__ import annotations

import json
import runpy
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "architecture" / "check_devices.py"


def _tree_with_active_version(tmp_path: Path, version: str) -> Path:
    standards = tmp_path / "standards"
    shutil.copytree(ROOT / "standards", standards)
    manifest_path = standards / "standards-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["standards"] if item["id"] == "otdp")
    entry["version"] = version
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return standards


def test_out_and_title_follow_the_manifest_active_version(tmp_path: Path) -> None:
    standards = _tree_with_active_version(tmp_path, "0.1.2")
    namespace = runpy.run_path(
        str(SCRIPT), init_globals={"STANDARDS": standards}
    )
    out: Path = namespace["OUT"]
    assert out == standards / "otdp" / "0.1.2", (
        "OUT must derive from the manifest's active otdp version, not a literal"
    )
    title: str = namespace["REPORT_TITLE"]
    assert title == "# OTDP 0.1.2 specification verification", (
        "REPORT_TITLE must carry the manifest's active otdp version"
    )


def test_manifest_absence_is_a_loud_refusal(tmp_path: Path) -> None:
    standards = tmp_path / "standards"
    shutil.copytree(ROOT / "standards", standards)
    (standards / "standards-manifest.json").unlink()
    with pytest.raises(SystemExit, match="otdp_manifest_absent"):
        runpy.run_path(str(SCRIPT), init_globals={"STANDARDS": standards})
