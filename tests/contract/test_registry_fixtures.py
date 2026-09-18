# tests/contract/test_registry_fixtures.py
"""Fixture catalogue: committed artifacts are schema-valid and reproducible."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from benchweave.registry.schemas import load_manifest_document, load_status_document

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures" / "registry"

# The private signing keys are not committed (only their .pub.pem halves are);
# CI materialises them from repository secrets, and fork PRs receive none.
# The builder tests must SIGN, so they skip without the keys — never fail —
# while the catalogue tests keep validating the committed, already-signed
# artifacts on every clone.
requires_signing_keys = pytest.mark.skipif(
    not all(
        (REG / "keys" / name).is_file() and (REG / "keys" / name).stat().st_size > 0
        for name in ("main.pem", "originb.pem")
    ),
    reason="requires the private fixture signing keys under fixtures/registry/keys/",
)

CATALOGUE = [
    ("benchweave/dc-psu-profile", "1.0.0"),
    ("benchweave/sim-psu-descriptor", "1.0.0"),
    ("benchweave/sim-controller-descriptor", "1.0.0"),
    ("benchweave/sim-psu", "1.0.0"),
    ("benchweave/sim-controller", "1.0.0"),
]

#: Fault drop-in names the builder emits, each targeting the descriptor.
FAULTS = ("revoked", "expired", "rollback-seq1", "rollback-seq2")


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


def _build(out: Path) -> None:
    # Stays a subprocess: build_fixtures.py imports its sibling registry_common
    # via the script directory on sys.path (scripts/registry is not a package)
    # and main() parses --out from sys.argv, so an in-process call would need
    # sys.path/argv surgery that couples the test to the script's layout.
    subprocess.run(
        ["uv", "run", "python", "scripts/registry/build_fixtures.py", "--out", str(out)],
        check=True,
        cwd=REPO,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": "venv"},
    )


@requires_signing_keys
def test_builder_is_deterministic(tmp_path: Path) -> None:
    out = tmp_path / "registry"
    _build(out)
    # Full breadth, not one release of six: every release in the lattice
    # (origin-main AND origin-b) — manifest, payload and both signatures —
    # plus every fault status pair and the catalogue, byte-for-byte.
    lattice = json.loads((REG / "catalogue.json").read_bytes())
    for entry in lattice["releases"]:
        committed = _release_dir(entry["origin"], entry["package_id"], entry["version"])
        rebuilt = out / entry["origin"] / entry["package_id"] / entry["version"]
        for name in ("manifest.json", "manifest.sig", "status.json", "status.sig", "payload.zip"):
            assert (rebuilt / name).read_bytes() == (committed / name).read_bytes(), (
                f"{entry['origin']}/{entry['package_id']}/{name}"
            )
    for fault in FAULTS:
        committed = REG / "faults" / fault / "benchweave/sim-psu-descriptor" / "1.0.0"
        rebuilt = out / "faults" / fault / "benchweave/sim-psu-descriptor" / "1.0.0"
        for name in ("status.json", "status.sig"):
            assert (rebuilt / name).read_bytes() == (committed / name).read_bytes(), (
                f"faults/{fault}/{name}"
            )
    assert (out / "catalogue.json").read_bytes() == (REG / "catalogue.json").read_bytes()


@requires_signing_keys
def test_builder_prunes_stale_release_dirs(tmp_path: Path) -> None:
    """Renames/deletions upstream can't leave validly-signed ghosts under --out."""
    out = tmp_path / "registry"
    _build(out)

    # A stale release dir (a package renamed or deleted upstream) and a
    # stale fault dir — both carrying genuinely signed fixture bytes.
    ghost_release = out / "origin-main" / "benchweave/renamed-away" / "1.0.0"
    ghost_release.mkdir(parents=True)
    shutil.copy2(
        REG / "origin-main/benchweave/sim-psu/1.0.0/manifest.json",
        ghost_release / "manifest.json",
    )
    ghost_fault = out / "faults" / "retired-fault" / "benchweave/sim-psu-descriptor" / "1.0.0"
    ghost_fault.mkdir(parents=True)
    shutil.copy2(
        REG / "faults/revoked/benchweave/sim-psu-descriptor/1.0.0/status.json",
        ghost_fault / "status.json",
    )
    # A stale extra file inside a KEPT release dir must not survive either.
    kept = out / "origin-main" / "benchweave/sim-psu" / "1.0.0"
    (kept / "leftover.json").write_bytes(b"{}")

    _build(out)
    assert not ghost_release.exists()
    assert not ghost_fault.exists()
    assert not (kept / "leftover.json").exists()
    assert sorted(p.name for p in kept.iterdir()) == [
        "manifest.json",
        "manifest.sig",
        "payload.zip",
        "status.json",
        "status.sig",
    ]


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
