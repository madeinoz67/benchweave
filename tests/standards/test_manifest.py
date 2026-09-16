"""The standards manifest is complete, consistent and hash-verified."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from benchweave.standards.manifest import (
    StandardsError,
    load_manifest,
    validate_manifest,
)

ROOT = Path(__file__).resolve().parents[2]


def test_manifest_loads_all_six_standards() -> None:
    manifest = load_manifest(ROOT)
    assert {entry.id for entry in manifest.standards} == {
        "otdp",
        "registry",
        "execution",
        "interface",
        "plugin-ui",
        "plugin-ui-preview",
    }


def test_interface_reset_has_no_supersession() -> None:
    entry = next(e for e in load_manifest(ROOT).standards if e.id == "interface")
    assert entry.version == "0.1.0" and entry.supersedes is None


def test_validation_passes_on_the_canonical_corpus() -> None:
    validate_manifest(load_manifest(ROOT), ROOT)


def test_missing_normative_file_fails(tmp_path: Path) -> None:
    manifest = load_manifest(ROOT)
    (tmp_path / "standards").mkdir()
    with pytest.raises(StandardsError, match="missing_normative_file"):
        validate_manifest(manifest, tmp_path)


def test_hash_drift_against_corpus_manifest_fails(tmp_path: Path) -> None:
    # A standards/ normative file whose bytes disagree with standards/corpus-manifest.json.
    # Copy the real file in and corrupt only its pin, so the failure is the
    # disagreement — absence is the previous test's job.
    documents = json.loads((ROOT / "standards/corpus-manifest.json").read_bytes())
    first = load_manifest(ROOT).standards[0].normative[0]
    row = next(r for r in documents["files"] if r["path"] == first.removeprefix("standards/"))
    row["sha256"] = "0" * 64
    (tmp_path / first).parent.mkdir(parents=True)
    shutil.copyfile(ROOT / first, tmp_path / first)
    (tmp_path / "standards/corpus-manifest.json").write_text(json.dumps(documents))
    with pytest.raises(StandardsError, match="normative_hash_mismatch"):
        validate_manifest(load_manifest(ROOT), tmp_path)
