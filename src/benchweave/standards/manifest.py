"""Load and validate the canonical standards manifest."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from datetime import date
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


# The dependency-policy range grammar: explicit half-open intervals only
# (">=X.Y.Z,<X.Y.Z", inclusive lower, exclusive upper — design §3.1). Caret
# sugar is AUTHORING input expanded before anything is stored; a caret stored
# in a committed file refuses (constraint_syntax_unexpanded).
RANGE_PATTERN = re.compile(r">=(\d+\.\d+\.\d+),<(\d+\.\d+\.\d+)")
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")


@dataclass(frozen=True)
class YankRecord:
    """One yanked version: retained, digest-frozen, in-interval, unserved.

    ``reason`` and ``since`` are recorded governance data; explicit pins to a
    yanked version stay conforming with a deprecation warning naming the
    derived move-to (the 0.2.1 template, design Q10).
    """

    version: str
    reason: str
    since: str


@dataclass(frozen=True)
class StandardPolicy:
    """One standard's declared range and recorded statuses."""

    id: str
    lower: str
    upper: str
    yanked: tuple[YankRecord, ...]
    retired: tuple[str, ...]
    note: str | None

    def in_range(self, version: str) -> bool:
        return _version_tuple(self.lower) <= _version_tuple(version) < _version_tuple(self.upper)


@dataclass(frozen=True)
class DependencyPolicy:
    """The committed dependency-policy block (design §3.1), read whole."""

    standards: dict[str, StandardPolicy]


def _version_tuple(version: str) -> tuple[int, int, int]:
    # Manual 3-unpack: the generator expression types as tuple[int, ...] and
    # needed a return-value ignore (#215 fold-wave F-E 9); the fixed arity is
    # the function's own contract.
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


@dataclass(frozen=True)
class DevHead:
    """One open dev head on a standard's entry (devstage record §4.1).

    ``version`` is ``<target>-dev`` with the target strictly greater than the
    entry's active version; ``opened`` carries the machine-readable open date
    (F4) so a stale head is visible without git archaeology; every
    ``normative`` path lives under ``standards/<id>/<version>/``. At most one
    head per standard is structural — one optional field, not a list.
    ``candidate`` (owner ruling 2026-09-23, §13.9) is the coordinator's
    believed-ready declaration — advisory, machine-readable, changing no
    enforcement: absent/false is the authoring state.
    """

    version: str
    opened: str
    normative: tuple[str, ...]
    candidate: bool = False


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
    candidate = raw.get("candidate", False)
    if not isinstance(candidate, bool):
        # The RC marker is a boolean declaration, not a truthiness guess: a
        # string or a 1 is refused rather than coerced (owner ruling §13.9).
        raise StandardsError(
            f"dev_block_invalid: {entry_id}: candidate must be a boolean when present "
            f"(got {type(candidate).__name__})"
        )
    if DEV_OPENED_PATTERN.fullmatch(opened) is None:
        raise StandardsError(
            f"dev_block_invalid: {entry_id}: opened {opened} is not an ISO YYYY-MM-DD date"
        )
    try:
        # Review row 4: the shape regex admits 9999-99-99 and 2027-13-45 —
        # only a real parse refuses them. The machine-readable head age must
        # not be a fiction.
        date.fromisoformat(opened)
    except ValueError:
        raise StandardsError(
            f"dev_block_invalid: {entry_id}: opened {opened} is not a real calendar date"
        ) from None
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
        # Review row 5: containment is checked on the LEXICALLY NORMALIZED
        # path — the raw string's startswith admitted
        # standards/<id>/<v>-dev/../<v-active>/… escapes into the active
        # tree. Lexical, not filesystem resolution: the corpus's paths are
        # split, never opened (repin's traversal-check posture).
        if not posixpath.normpath(relative).startswith(head_prefix):
            # Dev bytes outside the head directory would make the head a
            # laundering surface for paths the active spine governs.
            raise StandardsError(
                f"dev_path_outside_head: {entry_id}: {relative} "
                f"(dev paths must live under {head_prefix})"
            )
    return DevHead(
        version=version, opened=opened, normative=tuple(normative), candidate=candidate
    )


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


def load_dependency_policy(root: Path) -> DependencyPolicy:
    """Read the dependency-policy block; fail closed when malformed.

    The exact ``load_sdk_compatibility`` posture (governance data in the
    standards manifest, read by its own loader): the block must be an object
    with ``policy_version`` 1 and a ``standards`` map whose rows carry the
    explicit half-open ``range`` plus ``yanked`` and ``retired`` statuses.
    Shape errors refuse ``dependency_policy_invalid:``; a caret (or any other
    authoring sugar) stored in the committed file refuses
    ``constraint_syntax_unexpanded:`` — sugar is expanded before storage, never
    stored (design §3.1).
    """
    path = root / "standards/standards-manifest.json"
    document = json.loads(path.read_bytes())
    block = document.get("dependency_policy")
    if not isinstance(block, dict) or block.get("policy_version") != 1:
        raise StandardsError(
            "dependency_policy_invalid: dependency_policy block absent, not an "
            "object, or not policy_version 1"
        )
    rows = block.get("standards")
    if not isinstance(rows, dict) or not rows:
        raise StandardsError(
            "dependency_policy_invalid: the block's standards map is absent or empty"
        )
    policies: dict[str, StandardPolicy] = {}
    for identifier, raw in sorted(rows.items()):
        if not isinstance(identifier, str) or not isinstance(raw, dict):
            raise StandardsError("dependency_policy_invalid: a standards row is malformed")
        where = f"dependency_policy_invalid: {identifier}"
        lower, upper, problem = _parse_range(raw.get("range"))
        if problem == "unexpanded":
            raise StandardsError(
                f"constraint_syntax_unexpanded: {identifier}: {raw.get('range')!r} — "
                "caret sugar is authoring input; expand it to an explicit "
                "half-open interval before storing it"
            )
        if problem is not None:
            raise StandardsError(f"{where}: {problem}")
        yanked_raw = raw.get("yanked")
        if not isinstance(yanked_raw, dict):
            raise StandardsError(f"{where}: yanked must be an object")
        yanked: list[YankRecord] = []
        for version, record in sorted(yanked_raw.items()):
            if (
                VERSION_PATTERN.fullmatch(str(version)) is None
                or not isinstance(record, dict)
                or not isinstance(record.get("reason"), str)
                or not isinstance(record.get("since"), str)
            ):
                raise StandardsError(
                    f"{where}: yanked entry {version!r} needs a pure-semver key with "
                    "reason and since strings"
                )
            since = record["since"]
            if DEV_OPENED_PATTERN.fullmatch(since) is None:
                # Fold row 4 (#215): the yank record's since is machine-readable
                # history, gated exactly like the dev-head opened field — shape
                # first, then a real calendar parse.
                raise StandardsError(
                    f"{where}: yanked entry {version!r} since {since!r} is not an ISO "
                    "YYYY-MM-DD date"
                )
            try:
                date.fromisoformat(since)
            except ValueError:
                raise StandardsError(
                    f"{where}: yanked entry {version!r} since {since!r} is not a real "
                    "calendar date"
                ) from None
            yanked.append(
                YankRecord(version=str(version), reason=record["reason"], since=since)
            )
        retired_raw = raw.get("retired")
        if not isinstance(retired_raw, list) or not all(
            isinstance(item, str) for item in retired_raw
        ):
            raise StandardsError(f"{where}: retired must be a list of version strings")
        for version in retired_raw:
            if VERSION_PATTERN.fullmatch(version) is None:
                raise StandardsError(
                    f"{where}: retired entry {version!r} is not a pure semver version"
                )
        note = raw.get("note")
        if note is not None and not isinstance(note, str):
            raise StandardsError(f"{where}: note must be a string or absent")
        policies[identifier] = StandardPolicy(
            id=identifier,
            lower=lower or "",
            upper=upper or "",
            yanked=tuple(yanked),
            retired=tuple(retired_raw),
            note=note,
        )
    return DependencyPolicy(policies)


def _parse_range(value: object) -> tuple[str | None, str | None, str | None]:
    """Return (lower, upper, problem); the range grammar is exact."""
    if not isinstance(value, str):
        return None, None, "range must be a string"
    if "^" in value or "~" in value:
        return None, None, "unexpanded"
    match = RANGE_PATTERN.fullmatch(value)
    if match is None:
        return None, None, (
            f"range {value!r} is not an explicit half-open interval "
            "(>=X.Y.Z,<X.Y.Z — inclusive lower, exclusive upper)"
        )
    return match.group(1), match.group(2), None


def retained_versions(root: Path, standard_id: str) -> tuple[str, ...]:
    """The digest-pinned version set for one standard, from corpus rows.

    The corpus manifest is the byte authority, so retention is enumerated from
    its rows (never a directory listing): every ``<id>/<version>/`` prefix
    with at least one row is a retained version directory.
    """
    path = root / "standards/corpus-manifest.json"
    if not path.is_file():
        return ()
    document = json.loads(path.read_bytes())
    prefix = f"{standard_id}/"
    versions: set[str] = set()
    for row in document.get("files", []):
        relative = str(row["path"])
        if relative.startswith(prefix):
            remainder = relative.removeprefix(prefix).split("/", 1)
            if len(remainder) == 2 and VERSION_PATTERN.fullmatch(remainder[0]):
                versions.add(remainder[0])
    return tuple(sorted(versions))


def served_versions(policy: DependencyPolicy, root: Path, standard_id: str) -> tuple[str, ...]:
    """Served = retained ∧ in-range ∧ ¬yanked, derived, never hand-listed."""
    entry = policy.standards.get(standard_id)
    if entry is None:
        raise StandardsError(
            f"dependency_policy_invalid: no policy row for standard {standard_id!r}"
        )
    yanked = {record.version for record in entry.yanked}
    return tuple(
        version
        for version in retained_versions(root, standard_id)
        if entry.in_range(version) and version not in yanked
    )


def carried_versions(policy: DependencyPolicy, root: Path, standard_id: str) -> tuple[str, ...]:
    """Carried = retained ∧ in-range (yanked included): the byte-carrying set.

    The design's served-set rule governs classification and auto-selection
    (served = carried ∧ ¬yanked), but the export, the SDK lock and the wheel
    carry the CARRIED set — an explicit pin to a yanked-in-interval version
    stays conforming with a deprecation warning (the Q10 ruling), which needs
    the yanked version's bytes offline (PKG-1/VR-32). The design record's own
    wheel-payload enumeration (otdp/0.2.1 present, 688 KB du) and the A1
    anti-gaming arm (a 0.2.1-pinned suite, green with the warning) both
    require it; rows carry a ``yanked`` marker so every consumer re-derives
    the served set from the mirrored policy block. Recorded as a design
    contradiction resolution in the slice measurement record.
    """
    entry = policy.standards.get(standard_id)
    if entry is None:
        raise StandardsError(
            f"dependency_policy_invalid: no policy row for standard {standard_id!r}"
        )
    return tuple(
        version
        for version in retained_versions(root, standard_id)
        if entry.in_range(version)
    )


def validate_dependency_policy(
    policy: DependencyPolicy, manifest: StandardsManifest, root: Path
) -> None:
    """Cross-check the policy block against the manifest and the retained tree.

    Fail-closed (design §3.1): every manifest standard declares a policy row
    and vice versa; the active version sits inside the served set; a yanked
    entry names a retained in-range version (bytes must exist for a
    yanked-but-conforming pin to validate against — ``policy_entry_unresolved:``);
    a retired entry naming the ACTIVE version refuses ``policy_retired_active:``;
    retired and yanked stay disjoint and retired names no retained version
    (``policy_status_conflict:`` — retired means "used and dead": the number
    shipped once and the tree no longer carries it, so a live directory
    contradicts the status).
    """
    manifest_ids = {entry.id for entry in manifest.standards}
    unknown = sorted(set(policy.standards) - manifest_ids)
    if unknown:
        raise StandardsError(
            f"dependency_policy_invalid: policy rows for standards the manifest "
            f"does not carry: {', '.join(unknown)}"
        )
    missing = sorted(manifest_ids - set(policy.standards))
    if missing:
        raise StandardsError(
            f"dependency_policy_invalid: manifest standards with no policy row: "
            f"{', '.join(missing)}"
        )
    for entry in manifest.standards:
        row = policy.standards[entry.id]
        retained = retained_versions(root, entry.id)
        served = served_versions(policy, root, entry.id)
        if entry.version not in served:
            raise StandardsError(
                f"dependency_policy_invalid: {entry.id}: the manifest's active version "
                f"{entry.version} is not in the served set (range >={row.lower},<{row.upper}"
                f"{'; yanked: ' + ', '.join(r.version for r in row.yanked) if row.yanked else ''})"
            )
        for record in row.yanked:
            if record.version not in retained:
                raise StandardsError(
                    f"policy_entry_unresolved: {entry.id}: yanked {record.version} names a "
                    "version with no retained directory"
                )
            if not row.in_range(record.version):
                raise StandardsError(
                    f"policy_status_conflict: {entry.id}: yanked {record.version} is outside "
                    f"the declared range >={row.lower},<{row.upper}; the yank status could "
                    "never matter"
                )
        for version in row.retired:
            if version == entry.version:
                raise StandardsError(
                    f"policy_retired_active: {entry.id}: retired {version} IS the live "
                    "active version"
                )
            if version in retained:
                raise StandardsError(
                    f"policy_status_conflict: {entry.id}: retired {version} names a "
                    "retained directory; retired identifiers are used-and-dead and never "
                    "reissued"
                )
            # No "both yanked and retired" arm here — it was defensively
            # unreachable and is deleted with this proof (#215 fold-wave
            # F-E 12, the fold-row-14 pattern): the yanked loop above runs
            # first and requires every yanked version to be retained
            # (``policy_entry_unresolved:``), while this loop refuses any
            # retired version that IS retained — so a version in both sets
            # is always refused by one of those two conditions before a
            # dedicated overlap arm could fire. No enumeration ever listed
            # the deleted prefix.


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


def validate_carried_corpus_pins(
    manifest: StandardsManifest, policy: DependencyPolicy, root: Path
) -> None:
    """Every CARRIED version's corpus rows match their corpus-manifest pins.

    ``validate_manifest`` pins the ACTIVE and dev normative paths; before
    this check nothing consulted the corpus pins for superseded versions —
    a parse-valid tamper of a non-active carried version's bytes exported
    CLEAN, the bundle row carrying the tampered digest as its authority
    while ``corpus-manifest.json`` still pinned the original (#215
    fold-wave F-B; GOVERNANCE's frozen-superseded promise had no gate). The
    active version's rows are re-checked here too: ``export_bundle`` runs
    ``validate_manifest`` first, so an active-row tamper keeps its
    ``normative_hash_mismatch:`` refusal — order decides, both refuse.
    Rows under directories OUTSIDE the carried set ride neither the bundle
    nor this gate. Called from ``export_bundle`` (hence from
    ``benchweave.standards export``, ``check`` — which re-exports — and
    ``make check-sdk-standards``); NOT from ``validate_manifest``, whose
    repin caller must keep admitting a tree whose superseded rows repin is
    about to rewrite.
    """
    corpus = json.loads((root / "standards/corpus-manifest.json").read_bytes())
    rows = [str(row["path"]) for row in corpus.get("files", [])]
    pins = _corpus_pins(root)
    for entry in manifest.standards:
        for version in carried_versions(policy, root, entry.id):
            prefix = f"{entry.id}/{version}/"
            for relative in rows:
                if not relative.startswith(prefix):
                    continue
                path = root / "standards" / relative
                if not path.is_file():
                    raise StandardsError(
                        f"missing_normative_file: {entry.id}: standards/{relative}"
                    )
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                pinned = pins[relative]
                if pinned != digest:
                    raise StandardsError(
                        f"corpus_pin_mismatch: standards/{relative}: corpus pin "
                        f"{pinned} does not match the on-disk bytes ({digest}); "
                        "superseded versions are digest-frozen — restore the "
                        "pinned bytes or move the change through a new version, "
                        "never an in-place edit"
                    )


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
