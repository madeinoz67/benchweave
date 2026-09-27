"""The plugin dependency resolver: intervals, classification, carriers (issue #216).

#203 slice 2 (design record §3.4, `.claude/deep-review/
2026-09-27-issue216-slice2-resolver-design.md`): a package's requirement is
authored data (``contracts/constraints.json``), its resolved pin is generated
(``contracts/lock.json``, the DPS-150 shape extended to v2), and the decision
between them is a deterministic, offline, pure function of committed bytes
plus the authored constraints (CON-14's resolution clauses — this slice makes
them true). Caret sugar is AUTHORING input, expanded at the CLI boundary and
refused wherever it is found stored; the dev clauses of CON-14 (content-
addressed dev pins, wheel refusal) ride slice 4.

Input kinds. The RESOLUTION — which version each standard resolves to — reads
committed data of exactly four kinds: the dependency-policy block in
``standards/standards-manifest.json``, the rows of
``standards/corpus-manifest.json``, ``standards/cross-constraints.json``, and
the package's ``contracts/{constraints,lock}.json``. Never git, never the
network, never a clock (A04). The lock WRITER additionally reads the resolved
OTDP version's committed directory bytes for the legacy otdp projection —
the descriptor schema's ``api_version`` const (the ``validate_identity``
derivation relocated to the pinned version, digest-verified against its
corpus row) and the top-level file map (the fetch-verify set, deliberately
not the corpus-row set) — disclosed as the design's §1.1 four-kinds sentence
resolved in favour of §1.3's explicit derivation; still committed bytes
only, so CON-14's purity clause holds.

Prefix vocabulary (deliberate drift from the SDK, design risk 3): the SDK's
``version_not_served:`` folds "never carried" into "not served"; this
resolver splits ``version_unknown:`` out per acceptance rule B4 — distinct
remediations (publish-or-widen vs re-pin). Slice 3's gateway admission
adopts the same three-way split so the vocabularies converge deliberately.

Refusal prefixes, each machine-matchable: ``constraint_syntax_unexpanded:``,
``constraint_document_invalid:``, ``lock_document_invalid:``,
``constraint_standard_unknown:``, ``constraint_unresolvable:``,
``version_shape_invalid:``, ``dev_pin_unsupported:``,
``retired_identifier:``, ``version_unknown:``, ``version_not_served:``,
``plugin_constraints_absent:``, ``plugin_lock_absent:``,
``plugin_lock_drift:``, ``cross_constraint_invalid:``,
``cross_constraint_unresolved:``, ``cross_constraint_violation:``,
``adapter_api_unresolved:``, ``lock_otdp_absent:``,
``version_directory_absent:``, ``corpus_file_unpinned:``,
``corpus_pin_mismatch:``, ``constraint_set_invalid:``,
``plugin_ambiguous:``. Every classification refusal carries the five VR-37
fields inline: standard, pinned version, supported range, move-to,
migration-note pointer ("migration guidance pending" until slice 5).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .export import canonical_json
from .manifest import (
    RANGE_PATTERN,
    VERSION_PATTERN,
    StandardPolicy,
    StandardsError,
    carried_versions,
    load_dependency_policy,
    load_manifest,
    retained_versions,
    served_versions,
    version_tuple,
)

#: The constraints document's validating schema — gateway machinery, inline
#: in gateway source exactly like ``TRANSPORT_SETTINGS_SCHEMA``
#: (``control/provider_settings.py``): ``contracts/`` is plugin-authored
#: DATA; the schema that validates it is not. Stored form is explicit
#: intervals only (a stored caret refuses before the schema ever sees it);
#: ``opt_in`` stays empty until slice 4's dev pins.
CONSTRAINTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "constraint_version": {"const": 1},
        "standards": {
            "type": "object",
            "propertyNames": {"pattern": "^[a-z][a-z0-9-]*$"},
            "additionalProperties": {"type": "string", "minLength": 1},
        },
        "opt_in": {"type": "object", "maxProperties": 0},
    },
    "required": ["constraint_version", "standards", "opt_in"],
    "additionalProperties": False,
}

#: The v2 plugin lock's validating schema. The legacy top-level keys are the
#: OTDP PROJECTION (they were otdp-only): ``directory``, ``otdp_version`` and
#: ``adapter_api_version`` are re-derived from the resolved otdp row and move
#: iff it moves, while ``repository``/``revision`` are immutable fetch
#: provenance carried verbatim; ``sha256`` is the version directory's
#: top-level file map (the fetch-verify set — prose companions included,
#: deliberately not the corpus-row set).
LOCK_V2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lock_version": {"const": 2},
        "repository": {"type": "string", "minLength": 1},
        "revision": {"type": "string", "minLength": 1},
        "directory": {
            "type": "string",
            "pattern": r"^standards/otdp/\d+\.\d+\.\d+$",
        },
        "otdp_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "adapter_api_version": {"type": "string", "pattern": r"^\d+\.\d+$"},
        "sha256": {
            "type": "object",
            "propertyNames": {"pattern": "^[A-Za-z0-9._-]+$"},
            "additionalProperties": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        },
        "standards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
                    "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
                    "stage": {"const": "released"},
                    "digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                },
                "required": ["id", "version", "stage", "digest"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "lock_version",
        "repository",
        "revision",
        "directory",
        "otdp_version",
        "adapter_api_version",
        "sha256",
        "standards",
    ],
    "additionalProperties": False,
}

#: The cross-constraints side table's validating schema
#: (``standards/cross-constraints.json``, governance data beside the two
#: manifests — no corpus rows, no repin). ``requires`` values are explicit
#: intervals, except the ``adapter_api`` key which names an exact
#: two-component adapter API version.
CROSS_CONSTRAINTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cross_constraint_version": {"const": 1},
        "note": {"type": "string"},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "standard": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
                    "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
                    "requires": {
                        "type": "object",
                        "propertyNames": {"pattern": "^[a-z][a-z0-9_-]*$"},
                        "additionalProperties": {"type": "string", "minLength": 1},
                    },
                    "evidence": {"type": "string", "minLength": 1},
                },
                "required": ["standard", "version", "requires", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cross_constraint_version", "rows"],
    "additionalProperties": False,
}

ADAPTER_API_PATTERN = re.compile(r"^\d+\.\d+$")
_VALIDATORS: dict[str, Any] = {}


def _validator(name: str, schema: dict[str, Any]) -> Any:
    """A cached schema-checked validator (the ``registry/schemas`` idiom)."""
    validator = _VALIDATORS.get(name)
    if validator is None:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        _VALIDATORS[name] = validator
    return validator


def _atomic_write(path: Path, raw: bytes) -> None:
    """Staged write then ``os.replace`` (the repin/admission staging idiom)."""
    staged = path.parent / f"{path.name}.{os.getpid()}.tmp"
    try:
        staged.write_bytes(raw)
        os.chmod(staged, path.stat().st_mode if path.exists() else 0o644)
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


# --- intervals --------------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    """An explicit half-open ``>=lower,<upper`` constraint interval."""

    lower: str
    upper: str

    def contains(self, version: str) -> bool:
        return version_tuple(self.lower) <= version_tuple(version) < version_tuple(self.upper)

    def text(self) -> str:
        return f">={self.lower},<{self.upper}"


def _components(value: str) -> list[int] | None:
    """Numeric components with no leading zeros (``01`` refuses, ``0`` is fine)."""
    parts = value.split(".")
    numbers: list[int] = []
    for part in parts:
        if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
            return None
        numbers.append(int(part))
    return numbers


def expand_caret(value: str) -> Interval:
    """Expand caret authoring sugar per the 0.x table; refuse everything else.

    ``^0.2`` and ``^0.2.5`` bump the MINOR position (0.x is a compatibility
    range on the minor — ``^0.2`` is NOT ``>=0.2.0,<1.0.0``); ``^0.0.3`` bumps
    the PATCH position (0.0.x is compatible only on patch); ``^1.2.3`` bumps
    the MAJOR position. One- and two-component carets beyond ``^M.m``, tilde
    sugar and every other shape refuse ``constraint_syntax_unexpanded:`` —
    sugar is authoring input only, never silently interpreted.
    """
    if not value.startswith("^"):
        raise StandardsError(
            f"constraint_syntax_unexpanded: {value!r} is not caret authoring sugar "
            "(expected ^X.Y or ^X.Y.Z)"
        )
    numbers = _components(value.removeprefix("^"))
    if numbers is None or len(numbers) not in (2, 3):
        raise StandardsError(
            f"constraint_syntax_unexpanded: {value!r} — accepted sugar is ^X.Y or "
            "^X.Y.Z only; tilde and single-component carets are not expanded"
        )
    if len(numbers) == 2:
        major, minor = numbers
        lower = f"{major}.{minor}.0"
        upper = f"0.{minor + 1}.0" if major == 0 else f"{major + 1}.0.0"
    else:
        major, minor, patch = numbers
        lower = f"{major}.{minor}.{patch}"
        if major == 0 and minor == 0:
            upper = f"0.0.{patch + 1}"
        elif major == 0:
            upper = f"0.{minor + 1}.0"
        else:
            upper = f"{major + 1}.0.0"
    return Interval(lower=lower, upper=upper)


def parse_interval(value: object) -> Interval:
    """Parse an explicit half-open interval; sugar and bad shapes refuse.

    The ``manifest.py::_parse_range`` posture reused verbatim in meaning: a
    caret or tilde refuses ``constraint_syntax_unexpanded:`` (stored sugar is
    never silently expanded); anything else that is not the exact
    ``>=X.Y.Z,<X.Y.Z`` grammar refuses ``constraint_document_invalid:``.
    """
    if not isinstance(value, str):
        raise StandardsError(f"constraint_document_invalid: interval {value!r} must be a string")
    if "^" in value or "~" in value:
        raise StandardsError(
            f"constraint_syntax_unexpanded: {value!r} — caret sugar is authoring "
            "input; expand it to an explicit half-open interval before storing it"
        )
    match = RANGE_PATTERN.fullmatch(value)
    if match is None:
        raise StandardsError(
            f"constraint_document_invalid: {value!r} is not an explicit half-open "
            "interval (>=X.Y.Z,<X.Y.Z — inclusive lower, exclusive upper)"
        )
    return Interval(lower=match.group(1), upper=match.group(2))


# --- classification ---------------------------------------------------------------


@dataclass(frozen=True)
class PinClassification:
    """The outcome of classifying one pin against the policy block.

    ``state`` is ``"served"`` or ``"yanked"`` — both resolve; a yanked pin
    stays conforming with ``warning`` naming the derived move-to (the Q10
    ruling). Every other state refuses at classification time.
    """

    state: str
    warning: str | None


def _move_to(policy: Any, row: StandardPolicy, root: Path, standard_id: str) -> str:
    """The derived move-to: highest served version, else the range's lower bound.

    The fold-F-E-10 fallback (nothing served) applies — the message always
    names a concrete next step.
    """
    served = served_versions(policy, root, standard_id)
    return max(served) if served else row.lower


def _vr37(
    policy: Any, standard_id: str, version: str, row: StandardPolicy, root: Path
) -> str:
    """The five VR-37 fields inline: standard, pinned, supported, move-to, note."""
    return (
        f"standard: {standard_id}; pinned: {version}; "
        f"supported: >={row.lower},<{row.upper}; "
        f"move-to: {_move_to(policy, row, root, standard_id)}; "
        "migration: migration guidance pending"
    )


def classify_pin(
    policy: Any, root: Path, standard_id: str, version: str
) -> PinClassification:
    """Classify one pin against the policy block and the retained tree.

    Yanked/retired/unknown are three answers, one comparator (design §1.1):
    shape first (``-dev`` refuses naming slice 4 as the carrier; any other
    suffix refuses the pin-shape extension of
    ``standards_entry_version_invalid``), then retired (used-and-dead, never
    reissued — the refusal carries the next-minor re-target hint), then
    retained (never carried = ``version_unknown:`` with the publish-or-widen
    remediation), then in-range (out-of-range = ``version_not_served:``,
    the SDK's prefix), then the yank warning for a conforming pin.
    """
    row = policy.standards.get(standard_id)
    if row is None:
        raise StandardsError(
            f"constraint_standard_unknown: {standard_id!r} names a standard the "
            f"dependency-policy block does not carry; supported: "
            f"{', '.join(sorted(policy.standards))}"
        )
    if "-dev" in version:
        raise StandardsError(
            f"dev_pin_unsupported: {standard_id} {version} pins a dev head — dev "
            "resolution lands with slice 4 (#203); "
            f"{_vr37(policy, standard_id, version, row, root)}"
        )
    if VERSION_PATTERN.fullmatch(version) is None:
        raise StandardsError(
            f"version_shape_invalid: {standard_id} {version} is not a pure "
            "three-component version (pins never carry pre-release suffixes); "
            f"{_vr37(policy, standard_id, version, row, root)}"
        )
    if version in row.retired:
        major, minor, _patch = version_tuple(version)
        raise StandardsError(
            f"retired_identifier: {standard_id} {version} is a retired identifier "
            f"(used and dead, never reissued); the next minor is "
            f"{major}.{minor + 1}.0; "
            f"{_vr37(policy, standard_id, version, row, root)}"
        )
    retained = retained_versions(root, standard_id)
    if version not in retained:
        raise StandardsError(
            f"version_unknown: {standard_id} {version} was never carried by this "
            f"corpus — publish it or widen the constraint; "
            f"{_vr37(policy, standard_id, version, row, root)}"
        )
    if not row.in_range(version):
        served = ", ".join(served_versions(policy, root, standard_id)) or "nothing"
        raise StandardsError(
            f"version_not_served: {standard_id} {version} is retained but outside "
            f"the served set (served: {served}); "
            f"{_vr37(policy, standard_id, version, row, root)}"
        )
    for record in row.yanked:
        if record.version == version:
            return PinClassification(
                state="yanked",
                warning=(
                    f"deprecation warning: {standard_id} {version} is yanked "
                    f"({record.reason}; since {record.since}); "
                    f"move-to: {_move_to(policy, row, root, standard_id)}"
                ),
            )
    return PinClassification(state="served", warning=None)


# --- the constraints carrier ------------------------------------------------------


@dataclass(frozen=True)
class Constraints:
    """One package's authored constraints, parsed into intervals."""

    standards: dict[str, Interval]
    path: Path


def load_constraints(package: Path) -> Constraints:
    """Load and validate ``contracts/constraints.json``; fail closed.

    Stored sugar refuses ``constraint_syntax_unexpanded:`` BEFORE the schema
    runs (the exact ``_parse_range`` ordering); a dev-shaped value refuses
    ``dev_pin_unsupported:`` naming slice 4; every other shape error refuses
    ``constraint_document_invalid:`` with the JSON path.
    """
    path = package / "contracts" / "constraints.json"
    if not path.is_file():
        raise StandardsError(f"plugin_constraints_absent: {path}")
    document = json.loads(path.read_bytes())
    if not isinstance(document, dict):
        raise StandardsError(f"constraint_document_invalid: {path} is not an object")
    raw_standards = document.get("standards")
    if not isinstance(raw_standards, dict):
        # The schema below refuses the shape with its JSON path; there is
        # nothing for the sugar pre-check to walk.
        raw_standards = {}
    for identifier, value in sorted(raw_standards.items()):
        if isinstance(value, str) and "-dev" in value:
            raise StandardsError(
                f"dev_pin_unsupported: {identifier}: {value!r} — dev pins are "
                "content-addressed opt-in and land with slice 4 (#203)"
            )
        parse_interval(value)  # sugar + grammar refusals, before the schema
    errors = _validator("constraints", CONSTRAINTS_SCHEMA).iter_errors(document)
    error = next(iter(errors), None)
    if error is not None:
        raise StandardsError(
            f"constraint_document_invalid: {path.name} {error.json_path}: {error.message}"
        )
    intervals = {
        str(identifier): parse_interval(value)
        for identifier, value in sorted(raw_standards.items())
    }
    return Constraints(standards=intervals, path=path)


def apply_set(root: Path, package: Path, pairs: list[tuple[str, str]]) -> None:
    """Author constraints through the CLI boundary: expand sugar, never store it.

    ``--set <id>=<interval-or-caret>`` accepts ``^0.2`` at AUTHORING time and
    writes the expanded interval into the committed file — the only path from
    authoring to storage, so a caret never persists. An unknown standard
    refuses before any byte is written.
    """
    policy = load_dependency_policy(root)
    path = package / "contracts" / "constraints.json"
    if path.is_file():
        document = json.loads(path.read_bytes())
    else:
        document = {"constraint_version": 1, "standards": {}, "opt_in": {}}
    for identifier, text in pairs:
        if identifier not in policy.standards:
            raise StandardsError(
                f"constraint_standard_unknown: {identifier!r} names a standard the "
                f"dependency-policy block does not carry; supported: "
                f"{', '.join(sorted(policy.standards))}"
            )
        interval = expand_caret(text) if text.startswith("^") else parse_interval(text)
        document["standards"][identifier] = interval.text()
    _atomic_write(path, canonical_json(document))


# --- the prior-lock carrier --------------------------------------------------------


@dataclass(frozen=True)
class PriorLock:
    """The prior lock's projection: provenance plus one version per standard.

    ``version`` is 1 (the DPS-150 shape — the legacy keys parse into their
    otdp projection) or 2 (rows). ``rows`` maps standard id to its locked
    version; everything else the writer needs is re-derived, never carried.
    """

    version: int
    repository: str
    revision: str
    rows: dict[str, str]


def _stored_version(value: object, where: str) -> str:
    """A version stored in a committed document: pure semver, never sugar."""
    if not isinstance(value, str):
        raise StandardsError(f"lock_document_invalid: {where} must be a version string")
    if "^" in value or "~" in value:
        raise StandardsError(
            f"constraint_syntax_unexpanded: {where}: {value!r} — caret sugar is "
            "authoring input; a stored document never carries it"
        )
    if VERSION_PATTERN.fullmatch(value) is None:
        raise StandardsError(f"lock_document_invalid: {where}: {value!r} is not pure semver")
    return value


def load_prior_lock(package: Path) -> PriorLock | None:
    """Parse ``contracts/lock.json`` into the projection; None when absent."""
    path = package / "contracts" / "lock.json"
    if not path.is_file():
        return None
    document = json.loads(path.read_bytes())
    if not isinstance(document, dict):
        raise StandardsError(f"lock_document_invalid: {path} is not an object")
    repository = document.get("repository")
    revision = document.get("revision")
    if not isinstance(repository, str) or not repository:
        raise StandardsError("lock_document_invalid: repository must be a non-empty string")
    if not isinstance(revision, str) or not revision:
        raise StandardsError("lock_document_invalid: revision must be a non-empty string")
    if "lock_version" in document:
        if document["lock_version"] != 2:
            raise StandardsError(
                f"lock_document_invalid: lock_version {document['lock_version']!r} is "
                "not 2 (a v1 lock carries no lock_version key)"
            )
        rows: dict[str, str] = {}
        raw_rows = document.get("standards")
        if not isinstance(raw_rows, list):
            raise StandardsError("lock_document_invalid: standards must be a list")
        for row in raw_rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise StandardsError("lock_document_invalid: a standards row is malformed")
            rows[row["id"]] = _stored_version(
                row.get("version"), f"standards[{row['id']}]"
            )
        return PriorLock(version=2, repository=repository, revision=revision, rows=rows)
    otdp_version = _stored_version(document.get("otdp_version"), "otdp_version")
    return PriorLock(
        version=1,
        repository=repository,
        revision=revision,
        rows={"otdp": otdp_version},
    )


# --- the cross-constraints side table --------------------------------------------


@dataclass(frozen=True)
class CrossConstraintRow:
    """One cross-standard constraint row (``standards/cross-constraints.json``)."""

    standard: str
    version: str
    requires: dict[str, str]
    evidence: str


def load_cross_constraints(root: Path) -> tuple[CrossConstraintRow, ...]:
    """Load the cross-constraints side table; fail closed on shape and retention.

    The file is governance data beside the two manifests (no corpus rows);
    its ABSENCE refuses too — a tree that lost its cross-standard governance
    data does not silently degrade to "no constraints". Stored sugar in a
    requirement refuses ``constraint_syntax_unexpanded:`` before the schema
    runs; a row naming a version with no retained directory refuses
    ``cross_constraint_unresolved:`` (rows name released versions of their
    own standard); unknown standards on either side of a row refuse
    ``constraint_standard_unknown:``; ``adapter_api`` requirements name an
    exact two-component version, everything else an explicit interval.
    """
    path = root / "standards/cross-constraints.json"
    if not path.is_file():
        raise StandardsError(
            "cross_constraint_invalid: standards/cross-constraints.json absent — "
            "the tree's cross-standard governance data is missing, not empty"
        )
    document = json.loads(path.read_bytes())
    if isinstance(document, dict) and isinstance(document.get("rows"), list):
        for row in document["rows"]:
            if isinstance(row, dict) and isinstance(row.get("requires"), dict):
                for key, value in sorted(row["requires"].items()):
                    if isinstance(value, str) and ("^" in value or "~" in value):
                        raise StandardsError(
                            f"constraint_syntax_unexpanded: {row.get('standard')!r} "
                            f"requires {key}: {value!r} — caret sugar is authoring "
                            "input; a stored document never carries it"
                        )
    error = next(
        iter(_validator("cross-constraints", CROSS_CONSTRAINTS_SCHEMA).iter_errors(document)),
        None,
    )
    if error is not None:
        raise StandardsError(
            f"cross_constraint_invalid: {path.name} {error.json_path}: {error.message}"
        )
    policy = load_dependency_policy(root)
    rows: list[CrossConstraintRow] = []
    seen: set[tuple[str, str]] = set()
    for raw in document["rows"]:
        standard = str(raw["standard"])
        version = str(raw["version"])
        if standard not in policy.standards:
            raise StandardsError(
                f"constraint_standard_unknown: {standard!r} names a standard the "
                f"dependency-policy block does not carry; supported: "
                f"{', '.join(sorted(policy.standards))}"
            )
        if version not in retained_versions(root, standard):
            raise StandardsError(
                f"cross_constraint_unresolved: {standard}@{version} names a version "
                "with no retained directory; rows name released versions of their "
                "own standard"
            )
        if (standard, version) in seen:
            raise StandardsError(
                f"cross_constraint_invalid: duplicate row for {standard}@{version}"
            )
        seen.add((standard, version))
        requires: dict[str, str] = {}
        for key, value in sorted(raw["requires"].items()):
            if key == "adapter_api":
                if not isinstance(value, str) or ADAPTER_API_PATTERN.fullmatch(value) is None:
                    raise StandardsError(
                        f"cross_constraint_invalid: {standard}@{version} requires "
                        f"adapter_api {value!r} — an exact two-component version"
                    )
            elif key not in policy.standards:
                raise StandardsError(
                    f"constraint_standard_unknown: {standard}@{version} requires "
                    f"{key!r}, a standard the dependency-policy block does not carry"
                )
            requires[key] = str(value)
        rows.append(
            CrossConstraintRow(
                standard=standard, version=version, requires=requires, evidence=str(raw["evidence"])
            )
        )
    return tuple(rows)


# --- resolution and the lock writer -----------------------------------------------


@dataclass(frozen=True)
class Resolution:
    """A resolved lock document with its canonical bytes and warnings."""

    document: dict[str, Any]
    raw: bytes
    warnings: tuple[str, ...]


def resolve_package(
    root: Path, package: Path, *, precise: dict[str, str] | None = None
) -> Resolution:
    """Resolve constraints to a lock document (minimal motion; deterministic)."""
    raise NotImplementedError(resolve_package.__name__)


def row_digest(root: Path, standard_id: str, version: str) -> str:
    """The digest-of-digests over the corpus-manifest rows of one version."""
    raise NotImplementedError(row_digest.__name__)


def normalized_equal(path_a: Path, path_b: Path, version_a: str, version_b: str) -> bool:
    """Version-normalized subtree comparison (the B6 raw-digest control)."""
    raise NotImplementedError(normalized_equal.__name__)


# --- CLI command drivers -----------------------------------------------------------


def list_lines(root: Path) -> list[str]:
    """The ``standards list`` render: policy block + corpus rows, deterministic.

    One block per manifest standard: the active version and declared range,
    then the derived retained / carried / served sets, then every recorded
    yank (reason and since) and the retired identifiers.
    """
    manifest = load_manifest(root)
    policy = load_dependency_policy(root)
    lines: list[str] = []
    for entry in manifest.standards:
        row = policy.standards[entry.id]
        lines.append(
            f"standard {entry.id}@{entry.version} ({entry.status}) — "
            f"range >={row.lower},<{row.upper}"
        )
        lines.append(f"  retained {', '.join(retained_versions(root, entry.id)) or '—'}")
        lines.append(
            f"  carried {', '.join(carried_versions(policy, root, entry.id)) or '—'}"
        )
        lines.append(f"  served {', '.join(served_versions(policy, root, entry.id)) or '—'}")
        for record in row.yanked:
            lines.append(
                f"  yanked {record.version} ({record.reason}; since {record.since})"
            )
        if row.retired:
            lines.append(f"  retired {', '.join(row.retired)}")
    return lines


def default_package(root: Path) -> Path:
    """The single in-tree package when exactly one exists; refuse ambiguity."""
    packages = sorted({path.parent for path in (root / "plugins").rglob("contracts")})
    if len(packages) == 1:
        return packages[0]
    if not packages:
        raise StandardsError(
            "plugin_constraints_absent: no in-tree package carries contracts/ "
            "under plugins/; pass --package"
        )
    raise StandardsError(
        "plugin_ambiguous: multiple in-tree packages carry contracts/ "
        f"({', '.join(path.name for path in packages)}); pass --package"
    )


def parse_set_argument(value: str) -> tuple[str, str]:
    """``<id>=<interval-or-caret>`` — the CLI authoring entry point."""
    identifier, separator, text = value.partition("=")
    if not separator or not identifier or not text:
        raise StandardsError(
            f"constraint_set_invalid: {value!r} (expected <id>=<interval-or-caret>)"
        )
    return identifier, text


def pin_lock(root: Path, package: Path, sets: list[tuple[str, str]] | None = None) -> list[str]:
    """The ``pin`` command: author through ``--set``, resolve, write the lock."""
    if sets:
        apply_set(root, package, sets)
    load_constraints(package)
    raise StandardsError(
        "lock_writer_pending: the lock v2 writer lands with this slice's "
        "B1/B2 implementation commit (design §5 ordering)"
    )


def upgrade_lock(root: Path, package: Path, standard_id: str, precise: str) -> list[str]:
    """The ``upgrade`` command: one standard, one explicit target, minimal motion.

    Classification refusals (retired / unknown / not-served / dev / shape)
    fire before anything is written; a legal target proceeds to the writer.
    """
    policy = load_dependency_policy(root)
    constraints = load_constraints(package)
    if standard_id not in policy.standards:
        raise StandardsError(
            f"constraint_standard_unknown: {standard_id!r} names a standard the "
            f"dependency-policy block does not carry; supported: "
            f"{', '.join(sorted(policy.standards))}"
        )
    classify_pin(policy, root, standard_id, precise)  # refusals fire before any write
    interval = constraints.standards.get(standard_id)
    if interval is None:
        raise StandardsError(
            f"constraint_standard_unknown: {standard_id!r} is not in this package's "
            f"constraints ({', '.join(sorted(constraints.standards)) or 'none'})"
        )
    if not interval.contains(precise):
        raise StandardsError(
            f"constraint_unresolvable: {standard_id}: the precise target {precise} "
            f"is outside the authored interval {interval.text()}; widen the "
            "constraint (pin --set) or choose a version inside it"
        )
    raise StandardsError(
        "lock_writer_pending: the lock v2 writer lands with this slice's "
        "B1/B2 implementation commit (design §5 ordering)"
    )
