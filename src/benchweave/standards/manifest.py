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
    entries: list[StandardEntry] = []
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
