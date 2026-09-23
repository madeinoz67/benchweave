"""Export is deterministic, validated and fails closed."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

from benchweave.standards.export import canonical_json, export_bundle
from benchweave.standards.manifest import (
    StandardEntry,
    StandardsError,
    load_manifest,
)

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_json_is_sorted_compact_and_lf_terminated() -> None:
    assert canonical_json({"b": 1, "a": [2, 3]}) == b'{"a":[2,3],"b":1}\n'


def test_export_is_byte_identical_across_runs(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    export_bundle(ROOT, first)
    export_bundle(ROOT, second)
    assert _tree_digest(first) == _tree_digest(second)


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): p.read_bytes().hex()[:16]
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_bundle_covers_every_normative_file(tmp_path: Path) -> None:
    manifest_path = export_bundle(ROOT, tmp_path)
    bundle = json.loads(manifest_path.read_bytes())
    listed = {f["path"] for s in bundle["standards"] for f in s["files"]}
    expected: set[str] = set()
    for entry in load_manifest(ROOT).standards:
        expected |= _bundle_paths(entry)
    assert listed == expected


def _bundle_paths(entry: StandardEntry) -> set[str]:
    # standards/ assets land under their tree-relative path (<id>/<version>/…);
    # the parity validator (src/...) lands under its bare filename.
    return {
        n.removeprefix("standards/")
        if n.startswith("standards/")
        else f"{entry.id}/{PurePosixPath(n).name}"
        for n in entry.normative
    }


def test_export_carries_no_dev_head_bytes(tmp_path: Path) -> None:
    """Devstage record §4.2, first table row: export iterates the active
    spine — a properly-pinned dev head validates clean and never reaches the
    bundle. A pin, not a bug-fix arm: _entry ignored dev paths before this
    row existed; this holds the line against a future _entry change."""
    root = tmp_path / "repo"
    (root / "standards").mkdir(parents=True)
    document = json.loads((ROOT / "standards/standards-manifest.json").read_bytes())
    entry = next(e for e in document["standards"] if e["id"] == "otdp")
    descriptor = next(
        p for p in entry["normative"]
        if Path(p).name == "otdp-device-descriptor.schema.json"
    )
    # The head targets one patch above whatever the live tree carries, so
    # the pin holds on both headless and headed checkouts.
    major, minor, patch = (int(part) for part in entry["version"].split("."))
    dev_version = f"{major}.{minor}.{patch + 1}-dev"
    dev_descriptor = descriptor.replace(f"/{entry['version']}/", f"/{dev_version}/")
    entry.pop("dev", None)
    entry["normative"] = [descriptor]
    entry["dev"] = {
        "version": dev_version,
        "opened": "2026-09-23",
        "normative": [dev_descriptor],
    }
    document["standards"] = [entry]
    for relative in (descriptor, dev_descriptor):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / descriptor, target)
    corpus = json.loads((ROOT / "standards/corpus-manifest.json").read_bytes())
    active_row = next(
        row
        for row in corpus["files"]
        if row["path"] == descriptor.removeprefix("standards/")
    )
    dev_row = dict(active_row)
    dev_row["path"] = dev_descriptor.removeprefix("standards/")
    dev_row["source"] = active_row["path"]
    dev_row["sha256"] = hashlib.sha256((root / dev_descriptor).read_bytes()).hexdigest()
    corpus["files"] = [active_row, dev_row]
    for key in ("registry", "execution", "interface"):
        corpus["identity"].pop(key)
    (root / "standards/corpus-manifest.json").write_text(json.dumps(corpus))
    (root / "standards/standards-manifest.json").write_text(json.dumps(document))

    bundle_path = export_bundle(root, tmp_path / "out")
    bundle = json.loads(bundle_path.read_bytes())

    listed = {f["path"] for s in bundle["standards"] for f in s["files"]}
    assert listed == {descriptor.removeprefix("standards/")}, listed
    # Segment-level, not substring: "otdp-device-descriptor" contains "-dev".
    assert not any(
        part.endswith("-dev") for path in listed for part in path.split("/")
    )
    exported_files = {
        str(p.relative_to(tmp_path / "out" / "files"))
        for p in (tmp_path / "out" / "files").rglob("*")
        if p.is_file()
    }
    assert exported_files == listed, "the dev byte must not be written to the bundle"


def test_export_refuses_normative_paths_that_collide_in_the_bundle(tmp_path: Path) -> None:
    """Two normative paths mapping to one bundle path must fail closed."""
    broken = tmp_path / "repo"
    (broken / "standards").mkdir(parents=True)
    (broken / "src/benchweave/presentation/other").mkdir(parents=True)
    document = json.loads((ROOT / "standards/standards-manifest.json").read_bytes())
    entry = document["standards"][0]
    # The synthetic corpus below is REDUCED (one row); a live dev head's
    # paths have no rows there and validate would refuse them before the
    # collision under test could fire — the reduced entry is headless.
    entry.pop("dev", None)
    # Two non-contracts paths sharing a basename: both map to <id>/contracts.py
    # in the bundle - a silent file drop without the collision guard. The
    # descriptor stays named (and pinned) so identity validation passes and the
    # collision is the defect that fires.
    descriptor = next(
        p
        for p in entry["normative"]
        if Path(p).name == "otdp-device-descriptor.schema.json"
    )
    entry["normative"] = [
        descriptor,
        "src/benchweave/presentation/contracts.py",
        "src/benchweave/presentation/other/contracts.py",
    ]
    document["standards"] = [entry]
    shutil.copy(
        ROOT / "src/benchweave/presentation/contracts.py",
        broken / "src/benchweave/presentation/contracts.py",
    )
    shutil.copy(
        ROOT / "src/benchweave/presentation/contracts.py",
        broken / "src/benchweave/presentation/other/contracts.py",
    )
    (broken / descriptor).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / descriptor, broken / descriptor)
    corpus = json.loads((ROOT / "standards/corpus-manifest.json").read_bytes())
    corpus["files"] = [
        row for row in corpus["files"] if row["path"] == descriptor.removeprefix("standards/")
    ]
    # The tmp manifest carries only the otdp entry; the identity block derives
    # from it, so the standard keys it cannot account for are dropped too.
    for key in ("registry", "execution", "interface"):
        corpus["identity"].pop(key)
    (broken / "standards/corpus-manifest.json").write_text(json.dumps(corpus))
    (broken / "standards/standards-manifest.json").write_text(json.dumps(document))

    with pytest.raises(StandardsError, match="normative_bundle_path_collision"):
        export_bundle(broken, tmp_path / "out")


def test_export_refuses_a_missing_normative_file(tmp_path: Path) -> None:
    broken = tmp_path / "root"
    (broken / "standards").mkdir(parents=True)
    (broken / "standards/standards-manifest.json").write_bytes(
        (ROOT / "standards/standards-manifest.json").read_bytes()
    )
    with pytest.raises(Exception, match="missing_normative_file"):
        export_bundle(broken, tmp_path / "out")
    assert not (tmp_path / "out").exists(), "export must not leave partial output"
    assert not (tmp_path / "out.staging").exists(), "export must not leave staging behind"


def test_export_refuses_an_undeclared_adapter_api(tmp_path: Path) -> None:
    """The identity block is validated before any bundle write (validate-before-write)."""
    broken = tmp_path / "root"
    shutil.copytree(ROOT / "standards", broken / "standards")
    (broken / "src/benchweave/presentation").mkdir(parents=True)
    shutil.copy(
        ROOT / "src/benchweave/presentation/contracts.py",
        broken / "src/benchweave/presentation/contracts.py",
    )
    document = json.loads((broken / "standards/corpus-manifest.json").read_bytes())
    document["identity"].pop("adapter_api", None)
    (broken / "standards/corpus-manifest.json").write_text(json.dumps(document))
    with pytest.raises(StandardsError, match="identity_adapter_api_absent"):
        export_bundle(broken, tmp_path / "out")
    assert not (tmp_path / "out").exists(), "export must not leave partial output"
    assert not (tmp_path / "out.staging").exists(), "export must not leave staging behind"


def test_cli_export_writes_the_bundle(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchweave.standards",
            "export",
            "--out",
            str(tmp_path / "bundle"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "bundle" / "bundle-manifest.json").is_file()
