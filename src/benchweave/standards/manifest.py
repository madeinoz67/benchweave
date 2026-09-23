"""Load and validate the canonical standards manifest."""

from __future__ import annotations

import hashlib
import json
import re
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
# The active entry's version is pure semver: a "-dev" suffix there would add
# a release directory the train-window collector's pure-semver regex cannot
# count — the one evasion the dev stage opens (devstage record §4.1).
ACTIVE_VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
# A dev head's version names its promotion target plus the suffix; the target
# must be strictly greater than the active version or the head is a leftover.
DEV_VERSION_PATTERN = re.compile(r"(\d+\.\d+\.\d+)-dev")
# F4 (ratified): stale-head age is machine-readable in the manifest block —
# the open date is required whenever a head exists.
DEV_OPENED_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class StandardsError(ValueError):
    """A standards-manifest inconsistency; always names the offending entry."""


@dataclass(frozen=True)
class DevHead:
    """One open dev head on a standard's entry (devstage record §4.1).

    ``version`` is ``<target>-dev`` with the target strictly greater than the
    entry's active version; ``opened`` carries the machine-readable open date
    (F4) so a stale head is visible without git archaeology; every
    ``normative`` path lives under ``standards/<id>/<version>/``. At most one
    head per standard is structural — one optional field, not a list.
    """

    version: str
    opened: str
    normative: tuple[str, ...]


@dataclass(frozen=True)
class StandardEntry:
    id: str
    version: str
    status: str
    released: str
    supersedes: str | None
    normative: tuple[str, ...]
    dev: DevHead | None = None


@dataclass(frozen=True)
class StandardsManifest:
    standards: tuple[StandardEntry, ...]


@dataclass(frozen=True)
class SdkCompatibility:
    sdk: str
    main_project: str
    notes: str | None


def load_manifest(root: Path) -> StandardsManifest:
    path = root / "standards/standards-manifest.json"
    document = json.loads(path.read_bytes())
    if document.get("manifest_version") != 1:
        raise StandardsError("standards_manifest_version_unsupported")
    entries: list[StandardEntry] = []
    seen: set[str] = set()
    for raw in document["standards"]:
        entry_id = str(raw["id"])
        version = str(raw["version"])
        status = str(raw["status"])
        normative = tuple(str(item) for item in raw["normative"])
        if status not in VALID_STATUS or not normative:
            raise StandardsError(f"standards_entry_invalid: {entry_id}")
        if ACTIVE_VERSION_PATTERN.fullmatch(version) is None:
            # Pure semver on the active entry is what keeps the window
            # undodgeable: the collector counts exactly these directories.
            # This guard precedes dev parsing on purpose: the target
            # comparison int-parses the active version.
            raise StandardsError(
                f"standards_entry_version_invalid: {entry_id}: {version} "
                "(the active version must be pure semver; a -dev suffix is "
                "legal only in a dev head)"
            )
        entry = StandardEntry(
            id=entry_id,
            version=version,
            status=status,
            released=str(raw["released"]),
            supersedes=raw.get("supersedes"),
            normative=normative,
            dev=_load_dev_head(raw.get("dev"), entry_id, version),
        )
        if entry.id in seen:
            # Two entries for one id make every id-keyed derivation (identity,
            # descriptor location) a list-order first-match — refuse at load.
            raise StandardsError(f"standards_entry_duplicate: {entry.id}")
        seen.add(entry.id)
        entries.append(entry)
    return StandardsManifest(tuple(entries))


def _load_dev_head(raw: object, entry_id: str, active_version: str) -> DevHead | None:
    """Parse and structurally vet one optional dev block (devstage §4.1).

    Every bad state is unloadable, not warned about: a malformed block, a
    non-``<target>-dev`` version, a missing open date, a target that is not
    strictly greater than active (the leftover head a forgotten promotion
    teardown leaves — equal target — and its class-escalated form — target
    below active), and any path outside ``standards/<id>/<target>-dev/``
    each refuse with their own machine-matchable prefix.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise StandardsError(f"dev_block_invalid: {entry_id}: the dev block is not an object")
    version = raw.get("version")
    opened = raw.get("opened")
    normative = raw.get("normative")
    if (
        not isinstance(version, str)
        or not isinstance(opened, str)
        or not isinstance(normative, list)
        or not normative
        or not all(isinstance(item, str) for item in normative)
    ):
        raise StandardsError(
            f"dev_block_invalid: {entry_id}: version (a <target>-dev string), "
            "opened (an ISO YYYY-MM-DD date) and normative (a non-empty path "
            "list) are required"
        )
    if DEV_OPENED_PATTERN.fullmatch(opened) is None:
        raise StandardsError(
            f"dev_block_invalid: {entry_id}: opened {opened} is not an ISO YYYY-MM-DD date"
        )
    match = DEV_VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise StandardsError(
            f"dev_version_invalid: {entry_id}: {version} "
            "(expected <major>.<minor>.<patch>-dev)"
        )
    target = match.group(1)
    # Both guards below rely on the caller's pure-semver check having run on
    # active_version first; tuple comparison is exact on that shape.
    target_parts = tuple(int(part) for part in target.split("."))
    active_parts = tuple(int(part) for part in active_version.split("."))
    if target_parts == active_parts:
        # A promotion to the head's named target that forgets the teardown
        # leaves target == active; the block cannot ride along silently.
        raise StandardsError(
            f"dev_target_not_greater: {entry_id}: dev target {target} "
            f"equals active {active_version}"
        )
    if target_parts < active_parts:
        # The class-escalated form: active was promoted HIGHER than the head
        # named, so the head now targets a version below the release line.
        raise StandardsError(
            f"dev_head_stale: {entry_id}: dev target {target} is below "
            f"active {active_version}"
        )
    head_prefix = f"standards/{entry_id}/{version}/"
    for relative in normative:
        if not relative.startswith(head_prefix):
            # Dev bytes outside the head directory would make the head a
            # laundering surface for paths the active spine governs.
            raise StandardsError(
                f"dev_path_outside_head: {entry_id}: {relative} "
                f"(dev paths must live under {head_prefix})"
            )
    return DevHead(version=version, opened=opened, normative=tuple(normative))


def load_sdk_compatibility(root: Path) -> SdkCompatibility:
    """Read the mirrored SDK compatibility block; fail closed when malformed.

    The block mirrors the pinned SDK lock's ``compatibility`` — the lock stays
    the authority and ``check.run_check`` refuses drift between the two.
    ``sdk`` and ``main_project`` must be non-empty strings; ``notes`` mirrors
    the lock's nullable semantics (string or null).
    """
    path = root / "standards/standards-manifest.json"
    document = json.loads(path.read_bytes())
    block = document.get("sdk_compatibility")
    if not isinstance(block, dict):
        raise StandardsError(
            "sdk_compatibility_invalid: sdk_compatibility block absent or not an object"
        )
    for field in ("sdk", "main_project"):
        value = block.get(field)
        if not isinstance(value, str) or not value:
            raise StandardsError(f"sdk_compatibility_invalid: {field} missing or empty")
    notes = block.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise StandardsError("sdk_compatibility_invalid: notes must be a string or null")
    return SdkCompatibility(
        sdk=str(block["sdk"]),
        main_project=str(block["main_project"]),
        notes=notes,
    )


def validate_manifest(manifest: StandardsManifest, root: Path) -> None:
    """Every normative file exists; standards/ files match corpus-manifest pins.

    A dev head's paths are checked exactly like the active paths — a stale
    dev pin is the same defect class as a stale active pin, so the refusal
    prefixes are the existing ones, naming the dev path (devstage §4.1).
    """
    pins = _corpus_pins(root)
    for entry in manifest.standards:
        relatives = list(entry.normative)
        if entry.dev is not None:
            relatives.extend(entry.dev.normative)
        for relative in relatives:
            _check_normative_path(root, entry.id, relative, pins)


def _check_normative_path(
    root: Path, entry_id: str, relative: str, pins: dict[str, str]
) -> None:
    path = root / relative
    if not path.is_file():
        raise StandardsError(f"missing_normative_file: {entry_id}: {relative}")
    if not relative.startswith("standards/"):
        # Non-standards paths (the parity validator) carry no second authority.
        return
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    pinned = pins.get(relative.removeprefix("standards/"))
    if pinned is None:
        raise StandardsError(f"normative_not_in_corpus_manifest: {relative}")
    if pinned != digest:
        raise StandardsError(f"normative_hash_mismatch: {relative}")


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
