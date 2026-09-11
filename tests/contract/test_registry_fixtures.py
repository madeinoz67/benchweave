# tests/contract/test_registry_fixtures.py
"""Fixture catalogue: committed artifacts are schema-valid and reproducible."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from benchweave.registry.schemas import load_manifest_document, load_status_document

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures" / "registry"

CATALOGUE = [
    ("benchweave/dc-psu-profile", "1.0.0"),
    ("benchweave/sim-psu-descriptor", "1.0.0"),
    ("benchweave/sim-controller-descriptor", "1.0.0"),
    ("benchweave/sim-psu", "1.0.0"),
    ("benchweave/sim-controller", "1.0.0"),
]


def _release_dir(origin: str, package_id: str, version: str) -> Path:
    return REG / origin / package_id / version


def test_every_release_loads_and_validates() -> None:
    for package_id, version in CATALOGUE:
        d = _release_dir("origin-main", package_id, version)
        raw = (d / "manifest.json").read_bytes()
        manifest = load_manifest_document(raw, hashlib.sha256(raw).hexdigest(), max_bytes=1_000_000)
        assert manifest.content["version"] == version
        sraw = (d / "status.json").read_bytes()
        status = load_status_document(sraw, hashlib.sha256(sraw).hexdigest(), max_bytes=100_000)
        assert status.content["lifecycle"] == "published"
        assert (d / "payload.zip").is_file()
        assert (d / "manifest.sig").is_file()
        assert (d / "status.sig").is_file()


def test_origin_b_collision_present() -> None:
    d = _release_dir("origin-b", "benchweave/sim-psu", "1.0.0")
    raw = (d / "manifest.json").read_bytes()
    load_manifest_document(raw, hashlib.sha256(raw).hexdigest(), max_bytes=1_000_000)
    main_dir = _release_dir("origin-main", "benchweave/sim-psu", "1.0.0")
    main_raw = (main_dir / "manifest.json").read_bytes()
    assert raw != main_raw  # same identity, distinct origin content


def test_builder_is_deterministic(tmp_path: Path) -> None:
    out = tmp_path / "registry"
    subprocess.run(
        ["uv", "run", "python", "scripts/registry/build_fixtures.py", "--out", str(out)],
        check=True,
        cwd=REPO,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": "venv"},
    )
    for rel in (
        "origin-main/benchweave/sim-psu/1.0.0/manifest.json",
        "origin-main/benchweave/sim-psu/1.0.0/payload.zip",
    ):
        assert (out / rel).read_bytes() == (REG / rel).read_bytes(), rel


def test_catalogue_json_matches_tree() -> None:
    lattice = json.loads((REG / "catalogue.json").read_text())
    listed = {
        (e["package_id"], e["version"]) for e in lattice["releases"] if e["origin"] == "origin-main"
    }
    assert listed == set(CATALOGUE)
    for entry in lattice["releases"]:
        d = _release_dir(entry["origin"], entry["package_id"], entry["version"])
        raw = (d / "manifest.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["manifest_sha256"]
