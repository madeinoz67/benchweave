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
    carried_versions,
    load_dependency_policy,
    load_manifest,
    validate_dependency_policy,
    validate_identity,
    validate_manifest,
)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def export_bundle(root: Path, out: Path) -> Path:
    """Validate the canonical corpus, then write the bundle; fail before any write.

    Since issue #203 slice 1 the bundle carries one entry per CARRIED
    (id, version) — retained ∧ in-range, derived from the dependency-policy
    block, never hand-listed; yanked-in-interval versions ride with a
    ``"yanked": true`` marker because an explicit pin to them stays
    conforming with a deprecation warning (the Q10 ruling) and needs their
    bytes offline — the served set (¬yanked) is re-derived by every consumer
    from the mirrored policy block. The block itself travels verbatim
    (PKG-1: the range reaches the SDK via committed artifacts, never by
    reading the gateway checkout). The ACTIVE entry keeps its
    ``"active": true`` marker so consumers that want one version (matrix
    stamps, identity derivation) still get it structurally.
    """
    manifest = load_manifest(root)
    validate_manifest(manifest, root)
    validate_identity(manifest, root)
    policy = load_dependency_policy(root)
    validate_dependency_policy(policy, manifest, root)
    sources: dict[str, str] = {}  # bundle path -> repo-relative source path
    rows: list[dict[str, Any]] = []
    for entry in manifest.standards:
        carried = carried_versions(policy, root, entry.id)
        yanked = {record.version for record in policy.standards[entry.id].yanked}
        for version in carried:
            rows.append(_entry(root, entry, version, sources, yanked=version in yanked))
    document = {
        "bundle_version": 1,
        "exported_from": "benchweave",
        "dependency_policy": _policy_document(root),
        "standards": rows,
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


def _policy_document(root: Path) -> dict[str, Any]:
    """The dependency-policy block, carried verbatim from the manifest."""
    document = json.loads((root / "standards/standards-manifest.json").read_bytes())
    block = document.get("dependency_policy")
    if not isinstance(block, dict):
        raise StandardsError("dependency_policy_invalid: block absent at export time")
    return block


def _entry(
    root: Path,
    entry: StandardEntry,
    version: str,
    sources: dict[str, str],
    *,
    yanked: bool = False,
) -> dict[str, Any]:
    """One bundle row: the CARRIED version's corpus files.

    The ACTIVE version's row keeps the manifest's full metadata (status,
    released, supersedes) plus the marker; a non-active carried version has
    no manifest entry of its own, so its row carries ``status: "retained"``
    — the true statement about it — and its file set is enumerated from the
    corpus-manifest rows under ``<id>/<version>/`` (the byte authority),
    which is exactly the active row's set when the two coincide. A carried
    version always has corpus rows — retention is enumerated FROM those
    rows (``retained_versions``), so an empty enumeration here is
    unconstructible from loader-reachable state; the
    ``served_version_unresolved:`` guard this branch once carried was
    deleted on that proof (#215 fold row 14; the proof is recorded in the
    slice fix-wave record).
    """
    active = version == entry.version
    if active:
        relatives = list(entry.normative)
    else:
        corpus = json.loads((root / "standards/corpus-manifest.json").read_bytes())
        prefix = f"{entry.id}/{version}/"
        relatives = sorted(
            f"standards/{row['path']}"
            for row in corpus.get("files", [])
            if str(row["path"]).startswith(prefix)
        )
        # The entry's live-source rows (paths outside standards/, the
        # plugin-ui parity code row) list in EVERY carried row of the
        # standard: the bytes are one object and cannot multi-serve (F1/D2),
        # but each row's file set stays complete across active transitions.
        relatives += [
            path for path in entry.normative if not path.startswith("standards/")
        ]
    files = []
    for relative in relatives:
        raw = (root / relative).read_bytes()
        bundle_path = (
            relative.removeprefix("standards/")
            if relative.startswith("standards/")
            else f"{entry.id}/{Path(relative).name}"
        )
        if bundle_path in sources and sources[bundle_path] != relative:
            # Fail closed: a collision of DIFFERENT sources would ship one
            # file while files[] lists both. The same source listed by two
            # carried rows of one standard is a dedupe, not a collision —
            # the parity code row (plugin-ui's corpus-owned live source,
            # listed by the active row) rides every carried row so an
            # active transition never orphans the predecessor row's file
            # set (issue #203 slice 1; the code row's own multi-serving
            # question is deferral D2).
            raise StandardsError(
                f"normative_bundle_path_collision: {entry.id}: {bundle_path}"
            )
        sources[bundle_path] = relative
        files.append(
            {"path": bundle_path, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
        )
    row: dict[str, Any] = {
        "id": entry.id,
        "version": version,
        "status": entry.status if active else "retained",
        "active": active,
        "yanked": yanked,
        "files": sorted(files, key=lambda item: item["path"]),
    }
    if active:
        row["released"] = entry.released
        row["supersedes"] = entry.supersedes
    return row
