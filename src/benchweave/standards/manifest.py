"""Load and validate the canonical standards manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

VALID_STATUS = frozenset({"draft", "stable", "deprecated"})
DESCRIPTOR_SCHEMA_NAME = "otdp-device-descriptor.schema.json"
# Identity keys that name a standards-manifest id and therefore carry its version
IDENTITY_STANDARD_KEYS = ("otdp", "registry", "execution", "interface")
# Closed world: the identity block carries exactly these keys; a new key is a
# standards-governance event, so the validator refuses it until updated here.
IDENTITY_ALLOWED_KEYS = frozenset(IDENTITY_STANDARD_KEYS) | {
    "adapter_api",
    "architecture",
    "mcp",
    "note",
}


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
    seen: set[str] = set()
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
        if entry.id in seen:
            # Two entries for one id make every id-keyed derivation (identity,
            # descriptor location) a list-order first-match — refuse at load.
            raise StandardsError(f"standards_entry_duplicate: {entry.id}")
        seen.add(entry.id)
        entries.append(entry)
    return StandardsManifest(tuple(entries))


def validate_manifest(manifest: StandardsManifest, root: Path) -> None:
    """Every normative file exists; standards/ files match standards/corpus-manifest.json pins."""
    pins = _corpus_pins(root)
    for entry in manifest.standards:
        for relative in entry.normative:
            path = root / relative
            if not path.is_file():
                raise StandardsError(f"missing_normative_file: {entry.id}: {relative}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if relative.startswith("standards/"):
                pinned = pins.get(relative.removeprefix("standards/"))
                if pinned is None:
                    raise StandardsError(f"normative_not_in_corpus_manifest: {relative}")
                if pinned != digest:
                    raise StandardsError(f"normative_hash_mismatch: {relative}")
            # Non-standards paths (the parity validator) carry no second authority.


def _corpus_pins(root: Path) -> dict[str, str]:
    path = root / "standards/corpus-manifest.json"
    if not path.is_file():
        return {}
    document = json.loads(path.read_bytes())
    return {str(row["path"]): str(row["sha256"]) for row in document.get("files", [])}


def load_identity(root: Path) -> dict[str, str]:
    """Read the corpus identity block; fail closed when it is absent or malformed."""
    path = root / "standards/corpus-manifest.json"
    if not path.is_file():
        raise StandardsError("identity_block_invalid: standards/corpus-manifest.json absent")
    identity = json.loads(path.read_bytes()).get("identity")
    if not isinstance(identity, dict):
        raise StandardsError("identity_block_invalid: identity block absent or not an object")
    return {str(key): str(value) for key, value in identity.items()}


def validate_identity(manifest: StandardsManifest, root: Path) -> None:
    """The identity block is closed-world and derived-checked.

    The block carries exactly IDENTITY_ALLOWED_KEYS; an unknown key is refused
    (identity_key_unknown) because a new key is a standards-governance event,
    not an additive edit. adapter_api must equal the descriptor schema's
    api_version const, and the standards-manifest is the authority for the
    standard version keys: for each manifest id in IDENTITY_STANDARD_KEYS the
    block must declare exactly that version, and must not declare a standard
    the manifest does not carry. Declarations are verified, never trusted.
    """
    identity = load_identity(root)
    unknown = set(identity) - IDENTITY_ALLOWED_KEYS
    if unknown:
        raise StandardsError(f"identity_key_unknown: {', '.join(sorted(unknown))}")
    if "adapter_api" not in identity:
        raise StandardsError("identity_adapter_api_absent: adapter_api")
    relative = _descriptor_relative(manifest)
    path = root / relative
    if not path.is_file():
        raise StandardsError(f"missing_normative_file: otdp: {relative}")
    schema = json.loads(path.read_bytes())
    try:
        const = schema["$defs"]["adapter"]["properties"]["api_version"]["const"]
    except (KeyError, TypeError):
        raise StandardsError(
            f"identity_adapter_api_mismatch: api_version const absent from {relative}"
        ) from None
    if not isinstance(const, str):
        raise StandardsError(
            f"identity_adapter_api_mismatch: api_version const is not a string in {relative}"
        )
    if identity["adapter_api"] != const:
        raise StandardsError(
            f"identity_adapter_api_mismatch: identity {identity['adapter_api']} "
            f"vs schema const {const} in {relative}"
        )
    versions = {entry.id: entry.version for entry in manifest.standards}
    for key in IDENTITY_STANDARD_KEYS:
        if key in versions:
            if key not in identity:
                raise StandardsError(f"identity_standard_absent: {key}")
            if identity[key] != versions[key]:
                raise StandardsError(
                    f"identity_standard_mismatch: identity {key} {identity[key]} "
                    f"vs manifest {key}@{versions[key]}"
                )
        elif key in identity:
            raise StandardsError(
                f"identity_standard_mismatch: identity declares {key} "
                "but the manifest has no such standard"
            )


def _descriptor_relative(manifest: StandardsManifest) -> str:
    """Locate the active descriptor schema via the otdp entry's normative list."""
    for entry in manifest.standards:
        if entry.id != "otdp":
            continue
        matches = [p for p in entry.normative if Path(p).name == DESCRIPTOR_SCHEMA_NAME]
        if len(matches) == 1:
            return matches[0]
        raise StandardsError(
            f"identity_otdp_descriptor_missing: {DESCRIPTOR_SCHEMA_NAME} is not named "
            f"exactly once in the otdp@{entry.version} normative list"
        )
    raise StandardsError("identity_otdp_descriptor_missing: no otdp standard in the manifest")
