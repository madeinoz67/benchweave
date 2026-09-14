# Standards Synchronisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the SDK to its own repository as a submodule and build a manifest-verified, hash-enforced standards synchronisation mechanism between benchweave (canonical) and benchweave-sdk.

**Architecture:** One standards manifest in the main repo; a deterministic exporter producing a verifiable bundle; an SDK-side importer writing a stamped vendored tree plus a lock file; orchestration and non-mutating check targets; CI enforcement at five pipelines; generated compatibility matrix. Spec: `docs/superpowers/specs/2026-09-14-standards-sync-design.md`.

**Tech Stack:** Python 3.13, uv workspace, stdlib `hashlib`/`json`/`argparse`, pytest, GitHub Actions. SDK remote `https://github.com/madeinoz67/benchweave-sdk.git`.

## Global Constraints

- `uv` only; never pip/npm directly. Python 3.13. TypeScript N/A.
- mypy strict covers `src`, `tests`, `scripts/registry`, `packages/sdk/src`, `scripts/sdk_smoke.py`; ruff select `E,F,I,UP,B,SIM`; run gates before every commit: `uv run ruff check .`, `uv run mypy`, `uv run pytest -q` (minus the three key-dependent files locally: `tests/contract/test_registry_admission.py`, `test_registry_resolver.py`, `test_registry_fixtures.py` — CI runs them with secret keys).
- Signing keys are absent locally; those three files failing locally is environmental, not a finding.
- Submodule mounts at `packages/sdk`; uv workspace member path is unchanged.
- Standards ids (fixed six): `otdp`, `registry`, `execution`, `interface`, `plugin-ui`, `plugin-ui-preview`. `interface` version `1.1.1`, supersedes `1.1.0`.
- Normative-list consistency rule: a normative path under `contracts/` must appear in `contracts/manifest.json` with a matching sha256; a path outside `contracts/` (the parity validator `src/benchweave/presentation/contracts.py`) is hashed directly.
- Every generated SDK file starts with a stamp line: `Generated from <standard-id>@<version> — do not edit.`
- Commit hooks run `gortex enrich churn` (minutes per commit) — chain commits in one background command, verify with `git log` after.
- Two-repo discipline: SDK-side edits are committed INSIDE `packages/sdk` (submodule repo, branch `main`), then the main repo commits the pointer bump as its own commit.

---

### Task 1: Split the SDK into benchweave-sdk and mount the submodule

**Files:**
- Create: `.gitmodules` (via `git submodule add`)
- Modify: `.github/workflows/ci.yml`, `device-plugins.yml`, `package.yml` (add `submodules: recursive` to every `actions/checkout@v4`)
- Delete: in-tree `packages/sdk` (replaced by submodule)

**Interfaces:**
- Produces: submodule `packages/sdk` on branch `main` of `benchweave-sdk`, full history; all workflows check out submodules. Later tasks edit files inside `packages/sdk/` and commit them in the submodule.

- [ ] **Step 1: Subtree-split and push**

```bash
git subtree split -P packages/sdk -b sdk-split-origin
git push https://github.com/madeinoz67/benchweave-sdk.git sdk-split-origin:main
```

Expected: push succeeds; `git -C ~/Documents/src/benchweave-sdk fetch origin && git -C ~/Documents/src/benchweave-sdk log --oneline -3` shows SDK history.

- [ ] **Step 2: Replace in-tree dir with submodule**

```bash
git rm -r -q packages/sdk
git submodule add https://github.com/madeinoz67/benchweave-sdk.git packages/sdk
```

Expected: `.gitmodules` created; `packages/sdk` populated at the pushed tip.

- [ ] **Step 3: Wire submodules into CI checkouts**

In all three workflow files, every `- uses: actions/checkout@v4` gains:

```yaml
        with:
          submodules: recursive
```

- [ ] **Step 4: Verify workspace + gates**

```bash
UV_PROJECT_ENVIRONMENT=venv uv sync
uv run ruff check . && uv run mypy
rtk proxy uv run pytest -q --ignore=tests/contract/test_registry_admission.py --ignore=tests/contract/test_registry_resolver.py --ignore=tests/contract/test_registry_fixtures.py
UV_PROJECT_ENVIRONMENT=venv uv run scripts/sdk_smoke.py --out-dir /tmp/bw-smoke-split
```

Expected: all green (editable install resolves through the submodule path unchanged).

- [ ] **Step 5: Commit (main repo)**

```bash
git add .gitmodules packages/sdk .github/workflows/
git commit -m "build(sdk): mount benchweave-sdk as a submodule at packages/sdk"
```

---

### Task 2: Standards manifest and loader (main repo)

**Files:**
- Create: `standards/standards-manifest.json`
- Create: `src/benchweave/standards/__init__.py` (empty), `src/benchweave/standards/manifest.py`
- Test: `tests/standards/test_manifest.py`

**Interfaces:**
- Produces: `StandardsError` (subclass of `ValueError`); `@dataclass(frozen=True) class StandardEntry` with fields `id: str, version: str, status: str, released: str, supersedes: str | None, normative: tuple[str, ...]`; `@dataclass(frozen=True) class StandardsManifest` with `standards: tuple[StandardEntry, ...]`; `load_manifest(root: Path) -> StandardsManifest`; `validate_manifest(manifest: StandardsManifest, root: Path) -> None` (raises `StandardsError`).
- Consumes: `contracts/manifest.json` (existing file/sha256 authority).

- [ ] **Step 1: Write the failing tests**

```python
"""The standards manifest is complete, consistent and hash-verified."""
import json
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


def test_interface_supersedes_1_1_0() -> None:
    entry = next(e for e in load_manifest(ROOT).standards if e.id == "interface")
    assert entry.version == "1.1.1" and entry.supersedes == "1.1.0"


def test_validation_passes_on_the_canonical_corpus() -> None:
    validate_manifest(load_manifest(ROOT), ROOT)


def test_missing_normative_file_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = load_manifest(ROOT)
    (tmp_path / "contracts").mkdir()
    with pytest.raises(StandardsError, match="missing_normative_file"):
        validate_manifest(manifest, tmp_path)


def test_hash_drift_against_contracts_manifest_fails(tmp_path: Path) -> None:
    # A contracts/ normative file whose bytes disagree with contracts/manifest.json
    documents = json.loads((ROOT / "contracts/manifest.json").read_bytes())
    documents["files"][0]["sha256"] = "0" * 64
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts/manifest.json").write_text(json.dumps(documents))
    with pytest.raises(StandardsError, match="normative_hash_mismatch"):
        validate_manifest(load_manifest(ROOT), tmp_path)
```

Note for the implementer: the drift test must copy a real normative file into `tmp_path/contracts/` too — build the tmp tree by copying the two files the first normative entry names, then corrupt the pinned sha256. Keep the test honest: it must fail because the pin disagrees, not because the file is absent (that is the previous test's job).

- [ ] **Step 2: Run, expect import failure**

Run: `rtk proxy uv run pytest tests/standards -q --no-header`
Expected: FAIL — `ModuleNotFoundError: benchweave.standards`.

- [ ] **Step 3: Write `standards/standards-manifest.json`**

Author the manifest with exactly these normative lists (paths from repo root):

- `otdp` v0.3.0 stable — every `*.json` under `contracts/otdp-v0.3.0/` (schemas, device-profile-catalog, examples) — 24 files.
- `registry` v1.0.0 stable — every `*.json` under `contracts/registry-v1.0.0/` — 6 files.
- `execution` v1.0.0 stable — every `*.json` under `contracts/execution-v1.0.0/` — 12 files.
- `interface` v1.1.1 stable, supersedes 1.1.0 — every `*.json` under `contracts/interface-v1.1.1/` — 6 files.
- `plugin-ui` v0.1.0 stable — the four `*.schema.json` under `contracts/plugin-ui-v0.1.0/` plus `src/benchweave/presentation/contracts.py` (parity validator, direct-hash authority) — 5 files.
- `plugin-ui-preview` v1.0.0 stable — both schemas under `contracts/plugin-ui-preview-v1/` — 2 files.

Shape (one entry shown; write all six):

```json
{
  "manifest_version": 1,
  "standards": [
    {
      "id": "otdp",
      "version": "0.3.0",
      "status": "stable",
      "released": "2026-09-10",
      "supersedes": null,
      "normative": [
        "contracts/otdp-v0.3.0/device-profile-catalog.json",
        "contracts/otdp-v0.3.0/device-profile-catalog.schema.json"
      ]
    }
  ]
}
```

Use `released` dates from git history of each set (`git log --format=%as --diff-filter=A -- <dir> | tail -1`).

- [ ] **Step 4: Implement `manifest.py`**

```python
"""Load and validate the canonical standards manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

VALID_STATUS = frozenset({"draft", "stable", "deprecated"})


class StandardsError(ValueError):
    """A standards-manifest inconsistency; always names the offending entry."""


@dataclass(frozen=True)
class StandardEntry:
    id: str
    version: str
    status: str
    released: str
    supersedes: str | None
    normative: tuple[str, ...]


@dataclass(frozen=True)
class StandardsManifest:
    standards: tuple[StandardEntry, ...]


def load_manifest(root: Path) -> StandardsManifest:
    path = root / "standards/standards-manifest.json"
    document = json.loads(path.read_bytes())
    if document.get("manifest_version") != 1:
        raise StandardsError("standards_manifest_version_unsupported")
    entries = []
    for raw in document["standards"]:
        entry = StandardEntry(
            id=str(raw["id"]),
            version=str(raw["version"]),
            status=str(raw["status"]),
            released=str(raw["released"]),
            supersedes=raw.get("supersedes"),
            normative=tuple(str(item) for item in raw["normative"]),
        )
        if entry.status not in VALID_STATUS or not entry.normative:
            raise StandardsError(f"standards_entry_invalid: {entry.id}")
        entries.append(entry)
    return StandardsManifest(tuple(entries))


def validate_manifest(manifest: StandardsManifest, root: Path) -> None:
    """Every normative file exists; contracts/ files match contracts/manifest.json pins."""
    pins = _contracts_pins(root)
    for entry in manifest.standards:
        for relative in entry.normative:
            path = root / relative
            if not path.is_file():
                raise StandardsError(f"missing_normative_file: {entry.id}: {relative}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if relative.startswith("contracts/"):
                pinned = pins.get(relative.removeprefix("contracts/"))
                if pinned is None:
                    raise StandardsError(f"normative_not_in_contracts_manifest: {relative}")
                if pinned != digest:
                    raise StandardsError(f"normative_hash_mismatch: {relative}")
            # Non-contracts paths (the parity validator) carry no second authority.


def _contracts_pins(root: Path) -> dict[str, str]:
    path = root / "contracts/manifest.json"
    if not path.is_file():
        return {}
    document = json.loads(path.read_bytes())
    return {str(row["path"]): str(row["sha256"]) for row in document.get("files", [])}
```

- [ ] **Step 5: Green, gates, commit**

Run: `rtk proxy uv run pytest tests/standards -q --no-header` → PASS; run global gates; commit `feat(standards): canonical standards manifest with hash validation`.

---

### Task 3: Deterministic export (main repo)

**Files:**
- Create: `src/benchweave/standards/export.py`, `src/benchweave/standards/__main__.py`
- Modify: `.gitignore` (add `.standards-bundle/`)
- Test: `tests/standards/test_export.py`

**Interfaces:**
- Consumes: `load_manifest`, `validate_manifest` (Task 2).
- Produces: `canonical_json(value: object) -> bytes` (sorted keys, separators `(",", ":")`, LF-terminated); `export_bundle(root: Path, out: Path) -> Path` (validates first, writes `out/bundle-manifest.json` + `out/files/<id>/<contract-set-relative-path>`, returns manifest path). Bundle manifest entry shape: `{"id", "version", "status", "released", "supersedes", "files": [{"path": "<id>/<rel>", "sha256", "size"}]}`. CLI: `uv run python -m benchweave.standards export [--out .standards-bundle]`.

- [ ] **Step 1: Failing tests**

```python
"""Export is deterministic, validated and fails closed."""
import subprocess
import sys
from pathlib import Path

import pytest

from benchweave.standards.export import canonical_json, export_bundle
from benchweave.standards.manifest import load_manifest

ROOT = Path(__file__).resolve().parents[2]


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
    import json

    bundle = json.loads(manifest_path.read_bytes())
    listed = {f["path"] for s in bundle["standards"] for f in s["files"]}
    expected = {
        f"{e.id}/{n.removeprefix('contracts/')}"
        for e in load_manifest(ROOT).standards
        for n in e.normative
        if n.startswith("contracts/")
    }
    assert listed == expected


def test_export_refuses_a_missing_normative_file(tmp_path: Path) -> None:
    broken = tmp_path / "root"
    (broken / "standards").mkdir(parents=True)
    (broken / "standards/standards-manifest.json").write_bytes(
        (ROOT / "standards/standards-manifest.json").read_bytes()
    )
    with pytest.raises(Exception, match="missing_normative_file"):
        export_bundle(broken, tmp_path / "out")
    assert not (tmp_path / "out").exists(), "export must not leave partial output"
```

- [ ] **Step 2: Run → FAIL (module missing).**

- [ ] **Step 3: Implement `export.py`**

```python
"""Deterministic, validated export of the SDK-facing standards bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .manifest import StandardsManifest, load_manifest, validate_manifest


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def export_bundle(root: Path, out: Path) -> Path:
    """Validate the canonical corpus, then write the bundle; fail before any write."""
    manifest = load_manifest(root)
    validate_manifest(manifest, root)
    document = {
        "bundle_version": 1,
        "exported_from": "benchweave",
        "standards": [_entry(root, entry) for entry in manifest.standards],
    }
    staged = out.parent / (out.name + ".staging")
    if staged.exists():
        shutil.rmtree(staged)
    (staged / "files").mkdir(parents=True)
    for standard in document["standards"]:
        for file in standard["files"]:
            source = root / _source_path(manifest, standard["id"], file["path"])
            target = staged / "files" / file["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    (staged / "bundle-manifest.json").write_bytes(canonical_json(document))
    if out.exists():
        shutil.rmtree(out)
    staged.replace(out)
    return out / "bundle-manifest.json"


def _entry(root: Path, entry: Any) -> dict[str, Any]:
    files = []
    for relative in entry.normative:
        raw = (root / relative).read_bytes()
        bundle_path = (
            f"{entry.id}/{relative.removeprefix('contracts/')}"
            if relative.startswith("contracts/")
            else f"{entry.id}/{relative.name}"
        )
        files.append(
            {"path": bundle_path, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
        )
    return {
        "id": entry.id,
        "version": entry.version,
        "status": entry.status,
        "released": entry.released,
        "supersedes": entry.supersedes,
        "files": sorted(files, key=lambda row: row["path"]),
    }


def _source_path(manifest: StandardsManifest, standard_id: str, bundle_path: str) -> Path:
    relative = bundle_path.removeprefix(f"{standard_id}/")
    entry = next(e for e in manifest.standards if e.id == standard_id)
    for candidate in entry.normative:
        if candidate == relative or candidate.endswith(f"/{relative}") or candidate.endswith(relative):
            from pathlib import PurePosixPath

            if PurePosixPath(candidate).name == PurePosixPath(relative).name:
                return Path(candidate)
    raise KeyError(standard_id, bundle_path)
```

Note: `_source_path` resolves a bundle path back to its repo path — the validator (`contracts.py` parity asset) lands in the bundle under its bare filename; contract files under their set-relative path. If the `endswith` chain offends review, replace with an explicit reverse map built once in `_entry`; behaviour must stay identical.

`__main__.py`:

```python
"""Command line: python -m benchweave.standards export|check."""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--out", type=Path, default=Path(".standards-bundle"))
    arguments = parser.parse_args()
    if arguments.command == "export":
        from .export import export_bundle

        export_bundle(Path.cwd(), arguments.out)
        print(f"standards bundle exported to {arguments.out}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Green + `.gitignore` entry `.standards-bundle/`; gates; commit** `feat(standards): deterministic bundle export`.

---

### Task 4: SDK `sync-standards` import, lock and `--check` (submodule repo)

**Files (inside `packages/sdk/` — commit in the SUBMODULE):**
- Create: `packages/sdk/src/benchweave_sdk/standards_sync.py`
- Create (generated at sync time, committed): `packages/sdk/standards-lock.json`, `packages/sdk/src/benchweave_sdk/standards/` tree
- Modify: `packages/sdk/src/benchweave_sdk/cli.py` (add `sync-standards` command)
- Test: `tests/sdk/test_standards_sync.py` (MAIN repo — workspace imports the submodule)

**Interfaces:**
- Consumes: bundle layout from Task 3 (`bundle-manifest.json` + `files/`).
- Produces: `@dataclass(frozen=True) class SyncReport` with `added: tuple[str,...]`, `changed: tuple[str,...]`, `deprecated: tuple[str,...]`, `removed: tuple[str,...]`; `sync(bundle: Path, sdk_root: Path, *, check_only: bool = False) -> SyncReport` — raises `ValueError` with `standards_version_required:` prefix on unversioned normative change; CLI `benchweave-sdk sync-standards <bundle> [--check]`; lock shape at `packages/sdk/standards-lock.json`:

```json
{"lock_version": 1, "standards": [{"id": "otdp", "version": "0.3.0", "status": "stable",
  "files": [{"path": "otdp/otdp-device-descriptor.schema.json", "sha256": "…"}]}],
 "compatibility": {"main_project": ">=0.1.0", "sdk": "0.1.0", "notes": null}}
```

- [ ] **Step 1: Failing tests** (`tests/sdk/test_standards_sync.py` in MAIN repo; build bundles by exporting from the repo root, so tests exercise real artefacts)

```python
"""SDK standards import verifies hashes, classifies changes and refuses drift."""
import json
from pathlib import Path

import pytest

from benchweave_sdk.standards_sync import SyncReport, sync

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
    sdk = _synced_sdk(tmp_path, _export(tmp_path))
    lock = json.loads((sdk / "standards-lock.json").read_bytes())
    assert {s["id"] for s in lock["standards"]} == {
        "otdp", "registry", "execution", "interface", "plugin-ui", "plugin-ui-preview"
    }
    stamped = next((sdk / "src/benchweave_sdk/standards").rglob("*.json"))
    assert stamped.read_text().startswith("Generated from")


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
    import hashlib

    target["files"][0]["sha256"] = hashlib.sha256(asset.read_bytes()).hexdigest()
    target["version"] = "0.3.1"
    (bundle / "bundle-manifest.json").write_bytes(
        (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    report = sync(bundle, sdk)
    assert report.changed == ("otdp",)
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `standards_sync.py`**

```python
"""Import a benchweave standards bundle into the SDK's own vendored tree."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOCK_NAME = "standards-lock.json"
STAMP = "Generated from {identifier}@{version} — do not edit."


@dataclass(frozen=True)
class SyncReport:
    added: tuple[str, ...]
    changed: tuple[str, ...]
    deprecated: tuple[str, ...]
    removed: tuple[str, ...]


def sync(bundle: Path, sdk_root: Path, *, check_only: bool = False) -> SyncReport:
    document = _verify_bundle(bundle)
    lock = _read_lock(sdk_root)
    previous = {row["id"]: row for row in lock.get("standards", [])}
    added, changed, deprecated, removed = [], [], [], []
    for standard in document["standards"]:
        identifier, version = standard["id"], standard["version"]
        prior = previous.pop(identifier, None)
        if prior is None:
            added.append(identifier)
        elif prior["version"] != version:
            changed.append(identifier)
            if standard["status"] == "deprecated":
                deprecated.append(identifier)
        elif _file_hashes(standard) != {r["path"]: r["sha256"] for r in prior["files"]}:
            raise ValueError(
                f"standards_version_required: {identifier} content changed without a "
                "standards version increment"
            )
    removed.extend(sorted(previous))
    if check_only:
        _verify_vendored_tree(sdk_root, document)
        return SyncReport(tuple(sorted(added)), tuple(sorted(changed)),
                          tuple(sorted(deprecated)), tuple(sorted(removed)))
    _write_vendored(sdk_root, document)
    return SyncReport(tuple(sorted(added)), tuple(sorted(changed)),
                      tuple(sorted(deprecated)), tuple(sorted(removed)))


def _verify_bundle(bundle: Path) -> dict[str, Any]:
    manifest_path = bundle / "bundle-manifest.json"
    document = json.loads(manifest_path.read_bytes())
    if document.get("bundle_version") != 1:
        raise ValueError("bundle_version_unsupported")
    for standard in document["standards"]:
        for file in standard["files"]:
            raw = (bundle / "files" / file["path"]).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != file["sha256"] or len(raw) != file["size"]:
                raise ValueError(f"hash_mismatch: {file['path']}")
    return document


def _read_lock(sdk_root: Path) -> dict[str, Any]:
    path = sdk_root / LOCK_NAME
    if not path.is_file():
        return {}
    return json.loads(path.read_bytes())


def _file_hashes(standard: dict[str, Any]) -> dict[str, str]:
    return {row["path"]: row["sha256"] for row in standard["files"]}


def _write_vendored(sdk_root: Path, document: dict[str, Any]) -> None:
    tree = sdk_root / "src/benchweave_sdk/standards"
    if tree.exists():
        import shutil

        shutil.rmtree(tree)
    lock: dict[str, Any] = {"lock_version": 1, "standards": [], "compatibility": {
        "main_project": ">=0.1.0", "sdk": _sdk_version(sdk_root), "notes": None}}
    for standard in document["standards"]:
        for file in standard["files"]:
            target = tree / file["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            stamp = STAMP.format(identifier=standard["id"], version=standard["version"])
            raw = (Path(document["_bundle"]) / "files" / file["path"]).read_bytes() if False else None
            # bundle path is threaded via document below
            file["_raw"] = raw
        lock["standards"].append({
            "id": standard["id"], "version": standard["version"], "status": standard["status"],
            "files": [{"path": f["path"], "sha256": f["sha256"]} for f in standard["files"]],
        })
    # NOTE: implementation must carry `bundle` into _write_vendored — see step note.
    raise NotImplementedError("thread bundle root through _write_vendored")
```

**Implementer note (binding):** the sketch above intentionally leaves `_write_vendored` incomplete — complete it so that it takes `(bundle: Path, sdk_root: Path, document)` and writes each file's bytes prefixed by the stamp line as a JSON-with-header ONLY for `.json` files (prepend `# ` comment is invalid JSON — instead write the stamp into a sibling `<name>.stamp` file OR set the stamp as the first line of a `_GENERATED.md` per standard directory). **Decision locked by spec: stamp goes in `standards/<id>/_GENERATED.txt`** (one line per file: `<path> — Generated from <id>@<version> — do not edit`), keeping every vendored file byte-identical to the bundle (the lock hashes them). Update the Task-4 test `startswith("Generated from")` assertion to read `_GENERATED.txt` instead. `_verify_vendored_tree(sdk_root, document)` recomputes sha256 over `src/benchweave_sdk/standards/<path>` for every lock+bundle file and compares both. Wire the CLI into `cli.py` mirroring `check-preset`'s pattern (Click command `sync-standards`, argument `bundle`, flag `--check`, decorated `@_domain_errors`, calling `sync` with `sdk_root=Path(__file__).resolve().parents[2]`).

- [ ] **Step 4: Green; commit IN SUBMODULE** `feat(standards): sync-standards import with lock and check mode`; then MAIN repo: `git add packages/sdk && git commit -m "chore(sdk): advance submodule for standards sync"`.

---

### Task 5: hatch_build packages the vendored tree; smoke self-contained

**Files (submodule):** Modify `packages/sdk/hatch_build.py`, `packages/sdk/src/benchweave_sdk/fixtures.py`, `packages/sdk/src/benchweave_sdk/presentation.py` (schema/contract path resolution), `packages/sdk/pyproject.toml` (sdist include `standards-lock.json`).
**Files (main):** Modify `scripts/sdk_smoke.py` (drop `_contract_sets()` ast read; read the SDK lock instead), `tests/sdk/test_presentation_packaging.py` (wheel-content assertions → lock-driven).

**Interfaces:**
- Consumes: `standards-lock.json` (Task 4).
- Produces: SDK wheel whose `benchweave_sdk/standards/` tree is exactly the locked set; `hatch_build.CONTRACT_SETS` and the checkout reach are DELETED; `sdk_smoke` compares the wheel's standards tree against `packages/sdk/standards-lock.json`.

- [ ] **Step 1: RED — packaging test asserts lock↔wheel equality**

Modify `tests/sdk/test_presentation_packaging.py`: after building the wheel from sdist (existing helper), assert the set of `benchweave_sdk/standards/` names in the wheel equals the lock's file paths, each byte-identical. Run → FAIL (wheel still built from checkout reach; no standards tree yet).

- [ ] **Step 2: Run the smoke → observe it pass unchanged (control)**

Run: `UV_PROJECT_ENVIRONMENT=venv uv run scripts/sdk_smoke.py --out-dir /tmp/bw-smoke-pre5` → PASS (this is the pre-change control for the rewiring).

- [ ] **Step 3: Rewire hatch_build** — replace the checkout-reach branch with: require `src/benchweave_sdk/standards/` present, verify every file against `standards-lock.json` (reuse `_validate_preview_assets`'s shape: size + sha256 per entry), include the tree in wheel and sdist; sdist also includes `standards-lock.json` via pyproject `include`. Update `fixtures.py::_schema_path` and `presentation.py::_contract()` to resolve from `benchweave_sdk/standards/<id>/…` first (packaged path), keeping the editable-checkout fallback for pre-sync dev trees.

- [ ] **Step 4: Rewire sdk_smoke** — replace the ast-parsed `_contract_sets()` with reading `packages/sdk/standards-lock.json`; expected hashes = lock entries; the installed-check compares the wheel tree to the same lock. Delete the ast helper.

- [ ] **Step 5: Full gates + smoke** → green. Commit submodule `build(standards): package the vendored standards tree`; main: pointer commit + `test(sdk): packaging asserts lock↔wheel equality`.

---

### Task 6: Check command and Makefile targets (main repo)

**Files:**
- Create: `src/benchweave/standards/check.py`, `Makefile`
- Modify: `src/benchweave/standards/__main__.py` (add `check` subcommand)
- Test: `tests/standards/test_check.py`

**Interfaces:**
- Produces: `run_check(root: Path) -> list[str]` (empty = clean; each failure a one-line `field: detail`); `python -m benchweave.standards check` exits 0/1; `make sync-sdk-standards` (export → submodule import → manifests → targeted tests → version table; leaves changes uncommitted); `make check-sdk-standards` (temp re-export + `run_check`; no writes outside temp).

Failure classes `run_check` must produce (exact prefixes): `sdk_version_mismatch:`, `content_drift_without_version:`, `hash_mismatch:`, `stale_generated:`, `compatibility_incomplete:`, `missing_asset:`, `pinned_sdk_incompatible:`.

- [ ] **Step 1: Failing tests** — happy path clean (`run_check(ROOT) == []` with synced submodule); then four tamper cases using a tmp sdk root + monkeypatched submodule path resolution (version mismatch, tampered vendored file → `hash_mismatch` + `stale_generated`, missing asset → `missing_asset`, lock without compatibility block → `compatibility_incomplete`). Also `pinned_sdk_incompatible:` when the submodule lock omits a standard the main manifest lists. Use the same export-then-mutate harness as Task 4.

- [ ] **Step 2: Implement `check.py`** — re-export to `tempfile.mkdtemp`, compare: main manifest versions vs submodule lock versions; bundle hashes vs lock hashes vs vendored-tree bytes (`packages/sdk/src/benchweave_sdk/standards/`); regenerated import would be a no-op (`stale_generated`); every main-manifest standard present in the lock (`pinned_sdk_incompatible` when absent); compatibility block complete when any status is `deprecated` or any entry changed. Write `Makefile`:

```make
.PHONY: sync-sdk-standards check-sdk-standards

sync-sdk-standards:
	git submodule update --init --recursive
	@test -z "$$(git -C packages/sdk status --porcelain)" || (echo "submodule tree dirty; commit first" && exit 1)
	uv run python -m benchweave.standards export
	uv run --project packages/sdk benchweave-sdk sync-standards .standards-bundle
	uv run python -m benchweave.standards check
	uv run pytest -q tests/sdk tests/standards
	@uv run python -m benchweave.standards versions

check-sdk-standards:
	uv run python -m benchweave.standards check
```

Add a `versions` subcommand to `__main__.py` printing main version (pyproject), per-standard versions, SDK lock versions + submodule SHA.

- [ ] **Step 3: Green + gates; commit** `feat(standards): non-mutating sync check and make targets`.

---

### Task 7: CI wiring — five pipelines

**Files (main):** `.github/workflows/ci.yml` (add step `make check-sdk-standards` to `gates`), `.github/workflows/package.yml` (release job adds the same check).
**Files (submodule):** Create `.github/workflows/ci.yml` and `.github/workflows/publish.yml` in `packages/sdk/` — these belong to the SDK repo: checkout (no submodules), `uv sync --project .`, ruff+mypy over `src`, `benchweave-sdk sync-standards --check` (self-consistency against its own committed bundle copy: add `.standards-bundle/` — no: SDK self-check compares lock ↔ vendored tree ↔ wheel contents via `--check` with no bundle arg; extend the CLI so `--check` without a bundle verifies the committed tree against the lock), wheel build, `uv build` + install smoke (subset of sdk_smoke that needs no main repo: `benchweave-sdk --version`, `check` on a scaffolded descriptor).

- [ ] **Step 1: SDK `--check` no-bundle mode** — RED test: `sync` signature gains `bundle: Path | None`; `--check` with `None` verifies lock↔tree only. Implement, green, submodule commit.
- [ ] **Step 2: Write both SDK workflows** (mirror main's ci.yml discipline: pinned actions, read-only permissions, timeout).
- [ ] **Step 3: Main workflow steps** — add `make check-sdk-standards` after Test in `gates`, and to the release job in `package.yml`.
- [ ] **Step 4: Verify locally what CI will run** — `make check-sdk-standards` green; `git -C packages/sdk` workflows pass `actionlint` if available, else YAML-parse check.
- [ ] **Step 5: Commits** — submodule `ci(standards): SDK check pipeline`; main pointer commit + `ci(standards): gate PRs and releases on standards sync`.

---

### Task 8: Compatibility matrix generation

**Files:**
- Create: `src/benchweave/standards/matrix.py`, `docs/compatibility-matrix.md` (generated)
- Modify: `src/benchweave/standards/__main__.py` (`matrix` subcommand), `Makefile` (`check-sdk-standards` gains matrix staleness: `python -m benchweave.standards matrix --check`)
- Test: `tests/standards/test_matrix.py`

**Interfaces:** `render_matrix(root: Path) -> str` (markdown table); `--check` writes to temp and diffs against the committed file, exit 1 naming it stale. Table columns per spec §9. Commit `feat(standards): generated compatibility matrix`.

---

### Task 9: End-to-end scenario tests

**Files:** Test: `tests/standards/test_scenarios.py`

Scenarios (spec §10), each a full export→sync→check cycle on tmp copies:
1. **Unchanged** — sync no-op report, check clean.
2. **Compatible clarification** — edit a NON-normative doc file (`docs/plugin-ui-v0.1.0/README.md`), sync reports no delta, check clean (proves prose is outside the normative set).
3. **Breaking positive** — mutate a normative contract file + bump its standards version in the manifest (updating `contracts/manifest.json` pin + docs copy to match): sync reports `changed`, check clean.
4. **Breaking negative** — mutate the normative file WITHOUT the version bump: `validate_manifest` (hash pin), `sync`, and `run_check` each refuse with `standards_version_required` / `normative_hash_mismatch`.

RED-first per scenario where the assertion can fail against current code; commit `test(standards): unchanged, clarification and breaking scenarios`.

---

### Task 10: Close-out

- [ ] Force-add the spec and plan per repo convention: `git add -f docs/superpowers/specs/2026-09-14-standards-sync-design.md docs/superpowers/plans/2026-09-14-standards-sync.md`; commit `docs(spec): standards synchronisation design and plan` (they now document something that landed).
- [ ] Full gates + smoke + `make check-sdk-standards` + `make sync-sdk-standards` dry state clean.
- [ ] Update `docs/development.md` (sync workflow section) and `AGENTS.md` (two-repo discipline: submodule commits then pointer commits).
- [ ] Record final versions: main / standards-per-id / SDK / submodule SHA.
- [ ] Memory: propose the two-repo operating procedure to the ledger.
- [ ] Push branch; open PR with the version table and the acceptance-criteria checklist ticked from evidence.

---

## Self-Review (performed, fixes applied inline)

1. **Spec coverage:** manifest (T2), export (T3), import/lock/--check (T4), generated-tree marking (T4 stamp file), independent buildability (T5), orchestration (T6), non-mutating check incl. pinned-compat (T6), five CI pipelines (T7), classification/version-forcing (T2+T4+T9), matrix (T8), scenarios (T9), split (T1). Gap found and fixed: SDK CI self-check without main-repo access required a no-bundle `--check` mode — added as Task 7 Step 1.
2. **Placeholders:** Task 4's implementation sketch is deliberately partial with a binding implementer note and a locked decision (`_GENERATED.txt` stamps); no TBDs elsewhere.
3. **Type consistency:** `SyncReport(added, changed, deprecated, removed)` used in T4 tests and implementation; `run_check` failure prefixes enumerated in T6 and consumed by T9 assertions; lock/bundle path shapes identical across T3/T4/T5.
