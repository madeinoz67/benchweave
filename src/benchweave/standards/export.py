"""Deterministic, validated export of the SDK-facing standards bundle."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .manifest import (
    StandardEntry,
    StandardsError,
    load_manifest,
    validate_identity,
    validate_manifest,
)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def export_bundle(root: Path, out: Path) -> Path:
    """Validate the canonical corpus, then write the bundle; fail before any write."""
    manifest = load_manifest(root)
    validate_manifest(manifest, root)
    validate_identity(manifest, root)
    sources: dict[str, str] = {}  # bundle path -> repo-relative source path
    document = {
        "bundle_version": 1,
        "exported_from": "benchweave",
        "standards": [_entry(root, entry, sources) for entry in manifest.standards],
    }
    staged = out.parent / (out.name + ".staging")
    if staged.exists():
        shutil.rmtree(staged)
    (staged / "files").mkdir(parents=True)
    for bundle_path, relative in sorted(sources.items()):
        target = staged / "files" / bundle_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / relative).read_bytes())
    (staged / "bundle-manifest.json").write_bytes(canonical_json(document))
    if out.exists():
        shutil.rmtree(out)
    staged.replace(out)
    return out / "bundle-manifest.json"


def _entry(root: Path, entry: StandardEntry, sources: dict[str, str]) -> dict[str, Any]:
    files = []
    for relative in entry.normative:
        raw = (root / relative).read_bytes()
        bundle_path = (
            relative.removeprefix("standards/")
            if relative.startswith("standards/")
            else f"{entry.id}/{Path(relative).name}"
        )
        if bundle_path in sources:
            # Fail closed: a collision would ship one file while files[] lists both.
            raise StandardsError(
                f"normative_bundle_path_collision: {entry.id}: {bundle_path}"
            )
        sources[bundle_path] = relative
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
