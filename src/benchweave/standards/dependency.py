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
the package's ``contracts/{constraints,lock}.json``. Never the network, never
a clock (A04). The lock WRITER additionally reads the resolved OTDP version's
committed directory bytes for the legacy otdp projection — the descriptor
schema's ``api_version`` const (the ``validate_identity`` derivation
relocated to the pinned version, digest-verified against its corpus row) and
the top-level file map (the fetch-verify set, deliberately not the
corpus-row set) — disclosed as the design's §1.1 four-kinds sentence
resolved in favour of §1.3's explicit derivation. Slice 4 (#218) adds ONE
further input kind, disclosed the same way: a DEV-PINNED standard's bytes
materialize from the git OBJECT STORE at the opt-in's recorded sha
(``git show <sha>:<path>`` — the ``check.py::_pinned_sdk_package_version``
precedent), which is committed bytes by construction (a commit's tree), never
working-tree state and never a wheel's packaged tree. Repo checkout only: a
context without an object store refuses ``dev_head_unresolvable:`` and never
substitutes the active family.

Prefix vocabulary (deliberate drift from the SDK, design risk 3): the SDK's
``version_not_served:`` folds "never carried" into "not served"; this
resolver splits ``version_unknown:`` out per acceptance rule B4 — distinct
remediations (publish-or-widen vs re-pin). Slice 3's gateway admission
adopts the same three-way split so the vocabularies converge deliberately.

Refusal prefixes, each machine-matchable: ``constraint_syntax_unexpanded:``,
``constraint_document_invalid:``, ``lock_document_invalid:``,
``constraint_standard_unknown:``, ``constraint_unresolvable:``,
``version_shape_invalid:``, ``dev_pin_unsupported:`` (the INTERVAL block
never carries a dev pin — the opt-in does),
``dev_head_unresolvable:`` (the wheel/no-store posture and every
unaddressable head, by name — never a fallback to the active family),
``dev_target_retired:``, ``dev_pin_drift:`` (the head moved under a locked
dev pin — VR-29's revalidation refusal), ``retired_identifier:``,
``version_unknown:``, ``version_not_served:``,
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

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .export import canonical_json
from .manifest import (
    DESCRIPTOR_SCHEMA_NAME,
    RANGE_PATTERN,
    VERSION_PATTERN,
    StandardPolicy,
    StandardsError,
    carried_versions,
    declared_dev_head,
    load_dependency_policy,
    load_dependency_policy_from_corpus,
    load_manifest,
    retained_versions,
    retained_versions_from_corpus,
    served_versions,
    validate_dependency_policy,
    version_tuple,
)

#: The content-addressed dev pin's grammar: a canonical-numeral semver target
#: (the R5 leading-zero refusal), the ``-dev`` suffix, a literal ``@``, and a
#: full 40-hex git sha — the label is the human-readable half, the sha is
#: the address (VR-29: the pin records content identity, not only a label).
OPT_IN_PATTERN = (
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)-dev@[0-9a-f]{40}$"
)
_OPT_IN_SHAPE = re.compile(OPT_IN_PATTERN)

#: The constraints document's validating schema — gateway machinery, inline
#: in gateway source exactly like ``TRANSPORT_SETTINGS_SCHEMA``
#: (``control/provider_settings.py``): ``contracts/`` is plugin-authored
#: DATA; the schema that validates it is not. Stored form is explicit
#: intervals only (a stored caret refuses before the schema ever sees it).
#: ``opt_in`` carries slice 4's content-addressed dev pins (design §3.6):
#: one per standard, ``<target>-dev@<40-hex-git-sha>`` — explicit,
#: per-plugin, never ambient (VR-28).
CONSTRAINTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "constraint_version": {"const": 1},
        "standards": {
            "type": "object",
            "propertyNames": {"pattern": "^[a-z][a-z0-9-]*$"},
            "additionalProperties": {"type": "string", "minLength": 1},
        },
        "opt_in": {
            "type": "object",
            "propertyNames": {"pattern": "^[a-z][a-z0-9-]*$"},
            "additionalProperties": {"type": "string", "pattern": OPT_IN_PATTERN},
        },
    },
    "required": ["constraint_version", "standards", "opt_in"],
    "additionalProperties": False,
}

#: The v2 plugin lock's validating schema. The legacy top-level keys are the
#: OTDP PROJECTION (they were otdp-only): ``directory``, ``otdp_version`` and
#: ``adapter_api_version`` are re-derived from the resolved otdp row and move
#: iff it moves, while ``repository``/``revision`` are immutable fetch
#: provenance carried verbatim. TWO DIGEST SCOPES (fold wave 2 R12): the
#: top-level ``sha256`` is the version directory's top-level file map — the
#: fetch-verify set, prose companions (.md) included, examples/ excluded;
#: each ``standards[].digest`` is the digest-of-digests over the CORPUS ROWS
#: under the version — machine files and examples/ included, .md excluded —
#: EXCEPT a dev row, whose digest is the digest-of-digests over the head's
#: per-file digests AT THE RECORDED SHA (there are no frozen corpus rows for
#: a mutable head; the sha is the address). A dev row additionally carries
#: ``git_sha`` (the content address) and ``files`` (the per-file digests,
#: head-relative names) — VR-29's content identity, re-derivable by every
#: consumer from the object store.
LOCK_V2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lock_version": {"const": 2},
        "repository": {"type": "string", "minLength": 1},
        "revision": {"type": "string", "minLength": 1},
        "directory": {
            "type": "string",
            "pattern": r"^standards/otdp/(?:\d+\.)+\d+(?:-dev)?$",
        },
        "otdp_version": {
            "type": "string",
            "pattern": r"^(?:\d+\.)+\d+(?:-dev)?$",
        },
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
                    "version": {
                        "type": "string",
                        "pattern": r"^(?:\d+\.)+\d+(?:-dev)?$",
                    },
                    "stage": {"enum": ["released", "dev"]},
                    "digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "git_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                    "files": {
                        "type": "object",
                        "propertyNames": {"pattern": "^[A-Za-z0-9._/-]+$"},
                        "additionalProperties": {
                            "type": "string",
                            "pattern": "^[a-f0-9]{64}$",
                        },
                    },
                },
                "required": ["id", "version", "stage", "digest"],
                "allOf": [
                    {
                        "if": {"properties": {"stage": {"const": "dev"}}},
                        "then": {"required": ["git_sha", "files"]},
                    },
                    {
                        "if": {"properties": {"stage": {"const": "released"}}},
                        "then": {
                            "properties": {
                                "version": {"pattern": r"^(?:\d+\.)+\d+$"}
                            },
                            "not": {
                                "anyOf": [
                                    {"required": ["git_sha"]},
                                    {"required": ["files"]},
                                ]
                            },
                        },
                    },
                ],
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
        "note": {"type": "string", "maxLength": 2000},
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
    # version-ordered, never string-ordered: 0.2.10 > 0.2.2 by tuple, below by
    # string (fold F1 — both reproducers picked the string max)
    return max(served, key=version_tuple) if served else row.lower


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
    shape first (``-dev`` refuses naming the OPT-IN as the carrier — the
    interval block never carries a dev pin, #218 landed the mechanism; any
    other suffix refuses the pin-shape extension of
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
            f"dev_pin_unsupported: {standard_id} {version} names a dev head — the "
            "interval block never carries one; author a content-addressed opt-in "
            "(opt_in entry \"<target>-dev@<git-sha>\" in contracts/constraints.json, "
            "or pin --opt-in) instead; "
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


def parse_opt_in(value: object, where: str = "opt_in") -> tuple[str, str]:
    """Split a content-addressed dev pin into ``(label, sha)``.

    The grammar is exact (``OPT_IN_PATTERN``): canonical-numeral target,
    ``-dev``, ``@``, full 40-hex sha. A malformed value refuses
    ``constraint_document_invalid:``; authoring sugar (a caret) refuses
    ``constraint_syntax_unexpanded:`` — sugar is never silently interpreted
    in any stored document.
    """
    if not isinstance(value, str):
        raise StandardsError(
            f"constraint_document_invalid: {where}: {value!r} is not a string"
        )
    if "^" in value or "~" in value:
        raise StandardsError(
            f"constraint_syntax_unexpanded: {where}: {value!r} — caret sugar is "
            "authoring input; a stored document never carries it"
        )
    if _OPT_IN_SHAPE.fullmatch(value) is None:
        raise StandardsError(
            f"constraint_document_invalid: {where}: {value!r} is not a "
            "content-addressed dev pin (<target>-dev@<40-hex git sha>)"
        )
    label, _, sha = value.partition("@")
    return label, sha


@dataclass(frozen=True)
class Constraints:
    """One package's authored constraints, parsed into intervals.

    ``opt_in`` maps a standard id to its content-addressed dev pin
    (``<target>-dev@<sha>``) — explicit, per-plugin, never ambient; an
    opt-in standard must also carry its released interval in ``standards``
    (the opt-in documents an OVERRIDE, and the released interval is what a
    de-opted package falls back to).
    """

    standards: dict[str, Interval]
    opt_in: dict[str, str]
    path: Path


def load_constraints(package: Path) -> Constraints:
    """Load and validate ``contracts/constraints.json``; fail closed.

    Stored sugar refuses ``constraint_syntax_unexpanded:`` BEFORE the schema
    runs (the exact ``_parse_range`` ordering); a dev-shaped value in the
    INTERVAL block refuses ``dev_pin_unsupported:`` naming the opt-in as the
    carrier; a malformed opt-in value refuses with its own grammar; every
    other shape error refuses ``constraint_document_invalid:`` with the JSON
    path.
    """
    path = package / "contracts" / "constraints.json"
    if not path.is_file():
        raise StandardsError(f"plugin_constraints_absent: {path}")
    try:
        document = json.loads(path.read_bytes())
    except json.JSONDecodeError as exc:
        # Fold wave 2 R1: a file that does not decode refuses with the typed
        # prefix, never a bare decoder message.
        raise StandardsError(
            f"constraint_document_invalid: {path} does not decode as JSON ({exc})"
        ) from exc
    if not isinstance(document, dict):
        raise StandardsError(f"constraint_document_invalid: {path} is not an object")
    raw_standards = document.get("standards")
    if not isinstance(raw_standards, dict):
        # The schema below refuses the shape with its JSON path; there is
        # nothing for the sugar pre-check to walk.
        raw_standards = {}
    raw_opt_in = document.get("opt_in")
    if not isinstance(raw_opt_in, dict):
        raw_opt_in = {}
    for identifier, value in sorted(raw_standards.items()):
        if isinstance(value, str) and "-dev" in value:
            raise StandardsError(
                f"dev_pin_unsupported: {identifier}: {value!r} — the interval "
                "block never carries a dev pin; author a content-addressed "
                "opt-in (opt_in entry \"<target>-dev@<git-sha>\") instead"
            )
        parse_interval(value)  # sugar + grammar refusals, before the schema
    for identifier, value in sorted(raw_opt_in.items()):
        parse_opt_in(value, where=f"opt_in.{identifier}")
    errors = _validator("constraints", CONSTRAINTS_SCHEMA).iter_errors(document)
    error = next(iter(errors), None)
    if error is not None:
        raise StandardsError(
            f"constraint_document_invalid: {path.name} {error.json_path}: {error.message}"
        )
    stray = sorted(set(raw_opt_in) - set(raw_standards))
    if stray:
        # The opt-in documents a per-standard override: its standard must
        # carry the released interval in the same document, or the de-opted
        # fallback has nothing to fall back to.
        raise StandardsError(
            f"constraint_document_invalid: opt_in names {str(stray[0])!r}, which "
            "carries no interval in standards — an opt-in standard also "
            "declares its released interval"
        )
    intervals = {
        str(identifier): parse_interval(value)
        for identifier, value in sorted(raw_standards.items())
    }
    return Constraints(
        standards=intervals,
        opt_in={str(key): str(value) for key, value in sorted(raw_opt_in.items())},
        path=path,
    )


def apply_set(root: Path, package: Path, pairs: list[tuple[str, str]]) -> None:
    """Author constraints through the CLI boundary: expand sugar, never store it.

    ``--set <id>=<interval-or-caret>`` accepts ``^0.2`` at AUTHORING time and
    writes the expanded interval into the committed file — the only path from
    authoring to storage, so a caret never persists. An unknown standard
    refuses before any byte is written.
    """
    if not (package / "contracts").is_dir():
        # Fold wave 2 R1: refuse before any staged write is attempted — a
        # missing package directory is an authoring fact, not a crash.
        raise StandardsError(
            f"package_absent: {package / 'contracts'} — create the package "
            "before authoring its constraints"
        )
    policy = load_dependency_policy(root)
    path = package / "contracts" / "constraints.json"
    if path.is_file():
        # Fold wave 2 R1: the existing file routes through the loader's
        # validation first — a wrong-shape document refuses with its own
        # prefix instead of KeyError-ing under the authoring mutation.
        load_constraints(package)
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


def apply_opt_in(root: Path, package: Path, pairs: list[tuple[str, str]]) -> None:
    """Author a content-addressed dev opt-in through the CLI boundary.

    ``--opt-in <id>=<label>@<sha>`` validates BEFORE any byte is written:
    the standard is carried by the policy block AND by this document's
    interval block, the label names the manifest-DECLARED head exactly
    (accept-exactly-the-declared-head — one head per standard), and the
    target is not a retired identifier. Resolution re-verifies every one of
    these against the object store; authoring refuses early so the operator
    hears the typo at the authoring step, not at the pin.
    """
    if not (package / "contracts").is_dir():
        raise StandardsError(
            f"package_absent: {package / 'contracts'} — create the package "
            "before authoring its constraints"
        )
    policy = load_dependency_policy(root)
    path = package / "contracts" / "constraints.json"
    if path.is_file():
        load_constraints(package)
        document = json.loads(path.read_bytes())
    else:
        raise StandardsError(
            f"plugin_constraints_absent: {path} — author the released intervals "
            "first (pin --set), then the opt-in"
        )
    for identifier, value in pairs:
        if identifier not in policy.standards:
            raise StandardsError(
                f"constraint_standard_unknown: {identifier!r} names a standard the "
                f"dependency-policy block does not carry; supported: "
                f"{', '.join(sorted(policy.standards))}"
            )
        if identifier not in document["standards"]:
            raise StandardsError(
                f"constraint_document_invalid: opt_in names {identifier!r}, which "
                "carries no interval in standards — an opt-in standard also "
                "declares its released interval"
            )
        label, _sha = parse_opt_in(value, where=f"opt-in {identifier}")
        head = declared_dev_head(root / "standards", identifier)
        if head is None:
            raise StandardsError(
                f"dev_head_unresolvable: {identifier} opt-in {value!r} — the "
                "manifest declares no dev head for this standard (promoted or "
                "abandoned); nothing to opt into"
            )
        if head.version != label:
            raise StandardsError(
                f"dev_head_unresolvable: {identifier} opt-in {value!r} — the "
                f"manifest declares {head.version} (one head per standard; the "
                "opt-in names no declared head)"
            )
        target = label.removesuffix("-dev")
        row = policy.standards[identifier]
        if target in row.retired:
            major, minor, _patch = version_tuple(target)
            raise StandardsError(
                f"dev_target_retired: {identifier} {label} targets retired "
                f"identifier {target} (used and dead, never reissued — the head "
                f"could never promote); the next minor is {major}.{minor + 1}.0"
            )
        document["opt_in"][identifier] = value
    _atomic_write(path, canonical_json(document))


# --- the prior-lock carrier --------------------------------------------------------


@dataclass(frozen=True)
class PriorLock:
    """The prior lock's projection: provenance plus one version per standard.

    ``version`` is 1 (the DPS-150 shape — the legacy keys parse into their
    otdp projection) or 2 (rows). ``rows`` maps standard id to its locked
    version (a dev row's ``<target>-dev`` label included — stage awareness
    lives in ``stages``); ``file_map`` carries the prior sha256 map's names
    and digests (the allowlist's prior arm and the revision-scissors
    comparison); every other projection value is re-derived, never carried.
    """

    version: int
    repository: str
    revision: str
    rows: dict[str, str]
    file_map: dict[str, str]
    stages: dict[str, str]


#: A dev row's version label: ``<target>-dev`` with a canonical-numeral
#: target (the manifest's own ``DEV_VERSION_PATTERN`` grammar, kept in one
#: place there).
_DEV_LABEL = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)-dev$")


def _stored_version(value: object, where: str) -> str:
    """A version stored in a committed document: pure semver or a dev label.

    Pure semver for every released surface (the v1 projection and released
    rows); the ``-dev`` label form is legal ONLY in a v2 row whose stage is
    ``dev`` — the stage↔shape pairing is enforced by the caller that knows
    the row's stage, this helper only refuses sugar and malformed shapes.
    """
    if not isinstance(value, str):
        raise StandardsError(f"lock_document_invalid: {where} must be a version string")
    if "^" in value or "~" in value:
        raise StandardsError(
            f"constraint_syntax_unexpanded: {where}: {value!r} — caret sugar is "
            "authoring input; a stored document never carries it"
        )
    if VERSION_PATTERN.fullmatch(value) is None and _DEV_LABEL.fullmatch(value) is None:
        raise StandardsError(
            f"lock_document_invalid: {where}: {value!r} is not pure semver or a "
            "<target>-dev label"
        )
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
        stages: dict[str, str] = {}
        raw_rows = document.get("standards")
        if not isinstance(raw_rows, list):
            raise StandardsError("lock_document_invalid: standards must be a list")
        for row in raw_rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise StandardsError("lock_document_invalid: a standards row is malformed")
            stage = row.get("stage", "released")
            if stage not in ("released", "dev"):
                raise StandardsError(
                    f"lock_document_invalid: standards[{row['id']}] stage "
                    f"{stage!r} is neither released nor dev"
                )
            version = _stored_version(row.get("version"), f"standards[{row['id']}]")
            # The stage↔shape pairing: a released row's version is pure
            # semver, a dev row's carries the -dev label — a swapped pair is
            # refused here, never carried into the ladder where the dev
            # label would order against released versions.
            if version.endswith("-dev") != (stage == "dev"):
                raise StandardsError(
                    f"lock_document_invalid: standards[{row['id']}] carries "
                    f"version {version!r} at stage {stage!r} — a dev stage pairs "
                    "with a <target>-dev label and a released stage with pure semver"
                )
            rows[row["id"]] = version
            stages[row["id"]] = str(stage)
        file_map = document.get("sha256")
        if not isinstance(file_map, dict) or not all(
            isinstance(value, str) for value in file_map.values()
        ):
            raise StandardsError("lock_document_invalid: sha256 must be a digest map")
        return PriorLock(
            version=2,
            repository=repository,
            revision=revision,
            rows=rows,
            file_map={str(key): str(value) for key, value in file_map.items()},
            stages=stages,
        )
    otdp_version = _stored_version(document.get("otdp_version"), "otdp_version")
    if otdp_version.endswith("-dev"):
        raise StandardsError(
            "lock_document_invalid: the v1 otdp projection never carries a dev "
            f"label ({otdp_version!r}) — dev pins are v2 rows"
        )
    file_map = document.get("sha256")
    if not isinstance(file_map, dict) or not all(
        isinstance(value, str) for value in file_map.values()
    ):
        raise StandardsError("lock_document_invalid: sha256 must be a digest map")
    return PriorLock(
        version=1,
        repository=repository,
        revision=revision,
        rows={"otdp": otdp_version},
        file_map={str(key): str(value) for key, value in file_map.items()},
        stages={"otdp": "released"},
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
    return _load_cross(root / "standards", "standards/cross-constraints.json")


def load_cross_constraints_from_corpus(corpus: Path) -> tuple[CrossConstraintRow, ...]:
    """``load_cross_constraints`` over a CORPUS directory (issue #217).

    The pairwise admission check (design §3.3) resolves the corpus
    packaged-first like every other admission read; same loader, same
    validation, same refusal prefixes — one implementation, two entry shapes.
    """
    return _load_cross(corpus, "cross-constraints.json")


def _load_cross(corpus: Path, named: str) -> tuple[CrossConstraintRow, ...]:
    path = corpus / Path(named).name
    if not path.is_file():
        raise StandardsError(
            f"cross_constraint_invalid: {named} absent — "
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
    policy = load_dependency_policy_from_corpus(corpus)
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
        if version not in retained_versions_from_corpus(corpus, standard):
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
            elif RANGE_PATTERN.fullmatch(str(value)) is None:
                # Fold wave 2 R3: requirement intervals validate AT LOAD with
                # this file's own prefix (stored sugar already refused above).
                raise StandardsError(
                    f"cross_constraint_invalid: {standard}@{version} requires "
                    f"{key} {value!r} — not an explicit half-open interval "
                    "(>=X.Y.Z,<X.Y.Z)"
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


def _corpus_rows(root: Path) -> list[tuple[str, str]]:
    """The corpus manifest's (path, sha256) rows, in file order.

    Fold wave 2 R6: a malformed row refuses with its own prefix here, at
    the one consumption point the resolver's helpers share — never a bare
    KeyError at whatever downstream site first indexes the missing field.
    """
    document = json.loads((root / "standards/corpus-manifest.json").read_bytes())
    rows: list[tuple[str, str]] = []
    for index, row in enumerate(document.get("files", [])):
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("path"), str)
            or not isinstance(row.get("sha256"), str)
        ):
            where = row.get("path") if isinstance(row, dict) else index
            raise StandardsError(
                f"corpus_manifest_row_invalid: row {where!r} needs string "
                "'path' and 'sha256' fields"
            )
        rows.append((row["path"], row["sha256"]))
    return rows


def row_digest(
    root: Path, standard_id: str, version: str, rows: list[tuple[str, str]] | None = None
) -> str:
    """The digest-of-digests over the corpus-manifest rows of one version.

    The lock's per-standard row digest is derived from the byte authority's
    own rows — sha256 over the canonical JSON of the sorted
    ``[[path, sha256], ...]`` list under ``<id>/<version>/`` — so the lock
    stays a CLAIM every consumer re-derives (the anti-forgery posture,
    design §7 risk 1); the per-file truth already lives in the corpus
    manifest.
    """
    prefix = f"{standard_id}/{version}/"
    pairs = sorted(
        pair for pair in (rows if rows is not None else _corpus_rows(root))
        if pair[0].startswith(prefix)
    )
    if not pairs:
        raise StandardsError(
            f"version_unknown: {standard_id} {version} has no corpus-manifest rows"
        )
    return hashlib.sha256(canonical_json([list(pair) for pair in pairs])).hexdigest()


# --- dev heads: content-addressed resolution (issue #218, design §3.6) ------------


def _git_show(root: Path, ref: str) -> bytes | None:
    """One object-store read (the ``check.py::_pinned_sdk_package_version``
    git-show precedent); ``None`` on any git failure — the caller refuses by
    name, never guesses which of not-a-repo / bad-sha / bad-path it was."""
    result = subprocess.run(  # noqa: S603 — fixed argv
        ["git", "-C", str(root), "show", ref],  # noqa: S607 — PATH git is the supported invocation
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def _git_ls_tree(root: Path, sha: str, prefix: str) -> list[str] | None:
    """The file names under ``prefix`` in ``sha``'s tree; ``None`` on git
    failure (not a repository, absent sha — the wheel posture and the dead
    address, one refusal channel)."""
    result = subprocess.run(  # noqa: S603 — fixed argv
        [  # noqa: S607 — PATH git is the supported invocation
            "git",
            "-C",
            str(root),
            "ls-tree",
            "-r",
            "--name-only",
            sha,
            "--",
            prefix,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


@dataclass(frozen=True)
class DevResolution:
    """One dev head's bytes at the recorded sha — the lock row's content."""

    version: str
    git_sha: str
    files: dict[str, str]
    digest: str


def _resolve_dev_pin(
    root: Path, policy: Any, standard_id: str, label: str, sha: str
) -> DevResolution:
    """Resolve a content-addressed dev pin from the object store; fail loud.

    The ladder (every refusal names the standard and the pin): the manifest
    declares a head and the label names it exactly (accept-exactly-the-
    declared-head — one head per standard); the target is not a retired
    identifier (a head that could never promote is a dead end); then the
    bytes — ``git ls-tree``/``git show`` at the recorded sha, which is
    committed bytes by construction. A context with no object store (a
    packaged/wheel install) and an unaddressable sha both refuse
    ``dev_head_unresolvable:`` — the head's bytes ON DISK are never
    substituted for the object-store read, and the active family is never
    substituted for the head.
    """
    head = declared_dev_head(root / "standards", standard_id)
    if head is None:
        raise StandardsError(
            f"dev_head_unresolvable: {standard_id} opt-in {label}@{sha} — the "
            "manifest declares no dev head for this standard (promoted or "
            "abandoned); nothing to resolve"
        )
    if head.version != label:
        raise StandardsError(
            f"dev_head_unresolvable: {standard_id} opt-in {label}@{sha} — the "
            f"manifest declares {head.version} (one head per standard; the "
            "opt-in names no declared head)"
        )
    target = label.removesuffix("-dev")
    row = policy.standards.get(standard_id)
    if row is not None and target in row.retired:
        major, minor, _patch = version_tuple(target)
        raise StandardsError(
            f"dev_target_retired: {standard_id} {label} targets retired "
            f"identifier {target} (used and dead, never reissued — the head "
            f"could never promote); the next minor is {major}.{minor + 1}.0"
        )
    prefix = f"standards/{standard_id}/{label}"
    names = _git_ls_tree(root, sha, prefix)
    if names is None:
        raise StandardsError(
            f"dev_head_unresolvable: {standard_id} opt-in {label}@{sha} — no git "
            f"object store resolves at {root} (a packaged/wheel install "
            "physically cannot resolve a dev head; the head's working-tree "
            "bytes are never substituted and the active family is never "
            "substituted)"
        )
    if not names:
        raise StandardsError(
            f"dev_head_unresolvable: {standard_id} opt-in {label}@{sha} — the "
            f"commit's tree carries no {prefix}/ (wrong sha or a pre-head "
            "commit)"
        )
    files: dict[str, str] = {}
    for relative in names:
        raw = _git_show(root, f"{sha}:{relative}")
        if raw is None:
            raise StandardsError(
                f"dev_head_unresolvable: {standard_id} opt-in {label}@{sha} — "
                f"{relative} does not resolve in the object store"
            )
        files[relative.removeprefix(prefix + "/")] = hashlib.sha256(raw).hexdigest()
    missing = [
        relative
        for relative in head.normative
        if relative.removeprefix(prefix + "/") not in files
    ]
    if missing:
        raise StandardsError(
            f"dev_head_unresolvable: {standard_id} opt-in {label}@{sha} — the "
            f"declared head's normative files are absent at the sha "
            f"({', '.join(missing)})"
        )
    digest = hashlib.sha256(
        canonical_json([[name, files[name]] for name in sorted(files)])
    ).hexdigest()
    return DevResolution(version=label, git_sha=sha, files=files, digest=digest)


def _dev_adapter_api(root: Path, dev: DevResolution) -> str:
    """``adapter_api`` for a DEV-pinned otdp row, from the head's descriptor
    schema AT THE SHA (G-2's authority under the pin; the working tree's head
    copy is never consulted — it may have moved since the pin)."""
    raw = _git_show(
        root,
        f"{dev.git_sha}:standards/otdp/{dev.version}/{DESCRIPTOR_SCHEMA_NAME}",
    )
    if raw is None:
        raise StandardsError(
            f"adapter_api_unresolved: otdp@{dev.version} has no descriptor "
            f"schema at {dev.git_sha}"
        )
    schema = json.loads(raw)
    try:
        const = schema["$defs"]["adapter"]["properties"]["api_version"]["const"]
    except (KeyError, TypeError):
        raise StandardsError(
            f"adapter_api_unresolved: api_version const absent from the dev "
            f"head's descriptor schema at {dev.git_sha}"
        ) from None
    if not isinstance(const, str):
        raise StandardsError(
            f"adapter_api_unresolved: api_version const is not a string in the "
            f"dev head's descriptor schema at {dev.git_sha}"
        )
    return const


def adapter_api_for(
    root: Path, otdp_version: str, rows: list[tuple[str, str]] | None = None
) -> str:
    """``adapter_api`` for the PINNED version, from its descriptor schema.

    The ``validate_identity`` derivation (manifest.py) relocated to the
    pinned version (G-2's amendment): the descriptor schema named by the
    corpus row at ``otdp/<version>/`` is read, digest-verified against that
    row, and its ``$defs.adapter.properties.api_version`` const returned —
    no independent range axis this arc.
    """
    relative = f"otdp/{otdp_version}/{DESCRIPTOR_SCHEMA_NAME}"
    pins = dict(rows if rows is not None else _corpus_rows(root))
    pinned = pins.get(relative)
    path = root / "standards" / relative
    if pinned is None or not path.is_file():
        raise StandardsError(
            f"adapter_api_unresolved: otdp@{otdp_version} has no corpus-pinned "
            f"{DESCRIPTOR_SCHEMA_NAME}"
        )
    raw = path.read_bytes()  # read once: the digest and the parse share bytes
    digest = hashlib.sha256(raw).hexdigest()
    if digest != pinned:
        raise StandardsError(
            f"corpus_pin_mismatch: standards/{relative}: corpus pin {pinned} does "
            f"not match the on-disk bytes ({digest})"
        )
    schema = json.loads(raw)
    try:
        const = schema["$defs"]["adapter"]["properties"]["api_version"]["const"]
    except (KeyError, TypeError):
        raise StandardsError(
            f"adapter_api_unresolved: api_version const absent from standards/{relative}"
        ) from None
    if not isinstance(const, str):
        raise StandardsError(
            f"adapter_api_unresolved: api_version const is not a string in "
            f"standards/{relative}"
        )
    return const


def otdp_file_map(
    root: Path,
    version: str,
    prior_map: dict[str, str],
    rows: list[tuple[str, str]] | None = None,
) -> dict[str, str]:
    """The top-level file map of ``standards/otdp/<version>/`` — an ALLOWLIST.

    Fold F3: the derived map admits exactly corpus-rowed top-level files
    (matched case-insensitively — on a case-insensitive filesystem
    ``STRAY.JSON`` and a ``stray.json`` row are the same file) plus files
    named in the prior lock's map. ANY other file present in the version
    directory refuses ``corpus_file_stray:`` naming its disposition — a
    ``.DS_Store`` or stray upload never enters a committed lock, and a
    legitimately NEW prose companion (no row, absent from the prior map)
    refuses until the prior map is extended deliberately, instead of being
    silently adopted (A02: qualified, not assumed — deliberately stricter
    than bare directory coverage). Machine files (``.json`` in any letter
    case) must carry a corpus row and verify against it; prose companions
    hash as-is.
    """
    directory = root / "standards" / "otdp" / version
    if not directory.is_dir():
        raise StandardsError(f"version_directory_absent: standards/otdp/{version}")
    # Fold wave 2 R15c: the rows load once per resolution and thread through
    # every consumer (map, adapter derivation, row digests).
    pins = dict(rows if rows is not None else _corpus_rows(root))
    prefix = f"otdp/{version}/"
    pins_lowered = {key.lower(): value for key, value in pins.items()}
    rowed_top_lower = {
        key.removeprefix(prefix).lower()
        for key in pins
        if key.startswith(prefix) and "/" not in key.removeprefix(prefix)
    }
    mapping: dict[str, str] = {}
    strays: list[str] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        relative = f"otdp/{version}/{path.name}"
        rowed = path.name.lower() in rowed_top_lower
        if not rowed and path.name not in prior_map:
            strays.append(relative)
            continue
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if path.name.lower().endswith(".json"):
            pinned = pins_lowered.get(relative.lower())
            if pinned is None:
                raise StandardsError(
                    f"corpus_file_unpinned: {relative} (a machine file inside a "
                    "version directory must carry a corpus row)"
                )
            if digest != pinned:
                raise StandardsError(
                    f"corpus_pin_mismatch: standards/{relative}: corpus pin "
                    f"{pinned} does not match the on-disk bytes ({digest})"
                )
        mapping[path.name] = digest
    if strays:
        # Named together, sorted: the operator sees the whole deliberate act
        # the fold demands, not one file per run.
        raise StandardsError(
            "corpus_file_stray: "
            + ", ".join(f"standards/{relative}" for relative in sorted(strays))
            + " — neither corpus-rowed nor in the prior lock's map; remove them, "
            "corpus-pin them, or extend the prior map deliberately"
        )
    if not mapping:
        raise StandardsError(
            f"version_directory_absent: standards/otdp/{version} carries no files"
        )
    return mapping


def _cross_violations(
    root: Path,
    resolved: dict[str, str],
    adapter_api: str,
    dev_ids: frozenset[str] = frozenset(),
) -> list[str]:
    """Pairwise cross-constraint violations over the resolved set, evidenced.

    Cross-constraint rows are RELEASED-interface facts (their evidence cites
    a released version's runtime-interface claims), so a DEV-staged entry is
    not judged by them — the dev pin's own gates (the opt-in, the content
    identity, the head-state check) govern it. Skipping is closed against
    laundering: a dev label must name the manifest-declared head (one per
    standard), so no released pin can dodge a row by suffixing ``-dev``.
    """
    violations: list[str] = []
    for row in load_cross_constraints(root):
        if resolved.get(row.standard) != row.version:
            continue  # the row constrains that exact version of its own standard
        for key, value in sorted(row.requires.items()):
            if key == "adapter_api":
                if "otdp" in dev_ids:
                    continue  # the lock's adapter const is a dev head's, not a released pin's
                if adapter_api != value:
                    violations.append(
                        f"{row.standard}@{row.version} requires adapter_api "
                        f"{value}, the lock carries {adapter_api} ({row.evidence})"
                    )
            else:
                if key in dev_ids:
                    continue
                got = resolved.get(key)
                if got is None or not parse_interval(value).contains(got):
                    violations.append(
                        f"{row.standard}@{row.version} requires {key} {value}; the "
                        f"lock carries {key}@{got or 'nothing'} ({row.evidence})"
                    )
    return violations


def resolve_package(
    root: Path,
    package: Path,
    *,
    precise: dict[str, str] | None = None,
    revision: str | None = None,
) -> Resolution:
    """Resolve constraints to a lock document (minimal motion; deterministic).

    Per constrained standard the candidate is the prior locked version when
    it still satisfies the authored interval and classifies served-or-yanked
    (a prior pin that no longer classifies falls through to auto-selection,
    never refuses); else the highest SERVED version inside the interval —
    auto-selection never picks yanked (the 0.2.1 rule) or a pre-release
    (VR-28). ``precise`` overrides exactly one standard with an explicit
    classification of its target. The resolved set then clears the
    cross-constraint rows pairwise, and the document is emitted with its
    legacy otdp projection re-derived and canonical bytes validated through
    LOCK_V2_SCHEMA before anything is written or returned.
    """
    # Fold wave 2 R6 + R15c: the corpus rows load and validate ONCE, up
    # front, through the shared helper — a malformed row refuses typed
    # before any consumer indexes into it, and the per-helper re-reads are
    # gone (the rows thread through map/adapter/digest derivations).
    rows = _corpus_rows(root)
    policy = load_dependency_policy(root)
    constraints = load_constraints(package)
    prior = load_prior_lock(package)
    if prior is None:
        raise StandardsError(
            f"plugin_lock_absent: {package / 'contracts' / 'lock.json'} — hand-author "
            "the v1 provenance keys (repository, revision, the otdp projection), "
            "then pin; fresh-lock creation is deferral D9"
        )
    overrides = precise or {}
    unknown = sorted(set(overrides) - set(constraints.standards))
    if unknown:
        raise StandardsError(
            f"constraint_standard_unknown: {unknown[0]!r} is not in this package's "
            f"constraints ({', '.join(sorted(constraints.standards)) or 'none'})"
        )
    resolved: dict[str, str] = {}
    stages: dict[str, str] = {}
    dev_resolutions: dict[str, DevResolution] = {}
    warnings: list[str] = []
    for standard_id in sorted(constraints.standards):
        interval = constraints.standards[standard_id]
        if standard_id not in policy.standards:
            raise StandardsError(
                f"constraint_standard_unknown: {standard_id!r} names a standard the "
                f"dependency-policy block does not carry; supported: "
                f"{', '.join(sorted(policy.standards))}"
            )
        if standard_id in constraints.opt_in:
            if overrides.get(standard_id) is not None:
                raise StandardsError(
                    f"constraint_unresolvable: {standard_id} is dev-opted at "
                    f"{constraints.opt_in[standard_id]}; remove the opt-in before "
                    "precise-targeting a released version"
                )
            label, sha = parse_opt_in(
                constraints.opt_in[standard_id], where=f"opt_in.{standard_id}"
            )
            dev_resolutions[standard_id] = _resolve_dev_pin(
                root, policy, standard_id, label, sha
            )
            resolved[standard_id] = label
            stages[standard_id] = "dev"
            continue
        classification: PinClassification | None = None
        target = overrides.get(standard_id)
        if target is not None:
            classification = classify_pin(policy, root, standard_id, target)
            if not interval.contains(target):
                raise StandardsError(
                    f"constraint_unresolvable: {standard_id}: the precise target "
                    f"{target} is outside the authored interval {interval.text()}; "
                    "widen the constraint (pin --set) or choose a version inside it"
                )
            if classification.warning is not None:
                warnings.append(classification.warning)
            resolved[standard_id] = target
            stages[standard_id] = "released"
            continue
        candidate: str | None = None
        prior_version = prior.rows.get(standard_id)
        # A prior DEV row never feeds the released ladder: its label does not
        # order against released versions, and its pin's authority (the sha)
        # died with the opt-in that recorded it — fall through to auto-select.
        if (
            prior_version is not None
            and not prior_version.endswith("-dev")
            and interval.contains(prior_version)
        ):
            try:
                classification = classify_pin(policy, root, standard_id, prior_version)
            except StandardsError:
                # the prior pin no longer classifies; fall through to auto-select
                classification = None
            if classification is not None:
                candidate = prior_version
                if classification.warning is not None:
                    warnings.append(classification.warning)
        if candidate is None:
            served = [
                version
                for version in served_versions(policy, root, standard_id)
                if interval.contains(version)
            ]
            if not served:
                every = ", ".join(served_versions(policy, root, standard_id)) or "nothing"
                raise StandardsError(
                    f"constraint_unresolvable: {standard_id}: no served version "
                    f"inside {interval.text()} (served: {every}); publish a version "
                    "into the interval or widen the constraint"
                )
            candidate = max(served, key=version_tuple)
        resolved[standard_id] = candidate
        stages[standard_id] = "released"
    otdp_version = resolved.get("otdp")
    if otdp_version is None:
        raise StandardsError(
            "lock_otdp_absent: the legacy otdp projection requires an otdp "
            "constraint; add one (pin --set otdp=...)"
        )
    # Coarse-to-fine refusal ladder (fold wave 2 R8): the version
    # directory's existence is the coarsest fact, then the pinned
    # descriptor's derivation (its own named refusals for a missing row or
    # const), then the file map and the pairwise cross rows — each refusal
    # names its own layer, never a downstream symptom of an earlier gap.
    # The DEV arm replaces the first two rungs with the object-store
    # resolution above (the sha IS the address) and its own map.
    if stages["otdp"] == "dev":
        dev = dev_resolutions["otdp"]
        adapter_api = _dev_adapter_api(root, dev)
        # The top-level projection map keeps the released scope (top-level
        # files only, examples/ excluded); the dev ROW's ``files`` carries
        # the whole head at the sha — the row is the content identity, the
        # projection is the fetch-verify set.
        file_map = {name: digest for name, digest in dev.files.items() if "/" not in name}
    else:
        if not (root / "standards" / "otdp" / otdp_version).is_dir():
            raise StandardsError(
                f"version_directory_absent: standards/otdp/{otdp_version}"
            )
        adapter_api = adapter_api_for(root, otdp_version, rows)
        file_map = otdp_file_map(root, otdp_version, prior.file_map, rows)
    dev_ids = frozenset(dev_resolutions)
    violations = _cross_violations(root, resolved, adapter_api, dev_ids)
    if violations:
        raise StandardsError(
            "cross_constraint_violation: " + "; ".join(violations)
        )
    lock_rows: list[dict[str, Any]] = []
    for standard_id in sorted(resolved):
        if stages[standard_id] == "dev":
            dev = dev_resolutions[standard_id]
            lock_rows.append(
                {
                    "id": standard_id,
                    "version": dev.version,
                    "stage": "dev",
                    "digest": dev.digest,
                    "git_sha": dev.git_sha,
                    "files": dict(dev.files),
                }
            )
        else:
            lock_rows.append(
                {
                    "id": standard_id,
                    "version": resolved[standard_id],
                    "stage": "released",
                    "digest": row_digest(root, standard_id, resolved[standard_id], rows),
                }
            )
    document = {
        "lock_version": 2,
        "repository": prior.repository,
        # Fold F4: --revision records a motion's revision alongside it; the
        # value is caller-provided provenance. (The resolver reads the git
        # object store for DEV pins — the recorded sha is a superior anchor
        # to a branch tip, which is why the dev arm of _scissors skips.)
        "revision": revision if revision is not None else prior.revision,
        "directory": f"standards/otdp/{otdp_version}",
        "otdp_version": otdp_version,
        "adapter_api_version": adapter_api,
        "sha256": file_map,
        "standards": lock_rows,
    }
    error = next(iter(_validator("lock-v2", LOCK_V2_SCHEMA).iter_errors(document)), None)
    if error is not None:
        raise StandardsError(
            f"lock_document_invalid: {error.json_path}: {error.message}"
        )
    return Resolution(document=document, raw=canonical_json(document), warnings=tuple(warnings))


def write_lock(package: Path, raw: bytes) -> bool:
    """Staged atomic write; ``False`` when the bytes already match.

    The repin "writes only when a digest changed" idiom: an unchanged
    resolution never rewrites the committed file.
    """
    path = package / "contracts" / "lock.json"
    if path.is_file() and path.read_bytes() == raw:
        return False
    _atomic_write(path, raw)
    return True


def normalized_equal(path_a: Path, path_b: Path, version_a: str, version_b: str) -> bool:
    """Version-normalized subtree comparison (the B6 raw-digest control).

    Each subtree is canonical-JSON'd, its OWN version string replaced with
    a fixed placeholder, and the two compared — so a pair whose only
    difference is version strings (const, ``$id``, title, description — the
    0.2.1/0.2.2 descriptor pair) compares equal while a structural
    difference (the 0.2.0 pair's missing ``provider`` element) still
    refuses. The comparator answers "equal apart from their own version
    strings", never "equal": a raw-digest comparison on the same
    version-strings-only pair fails (pinned by the B6 battery, the Q6 RED).

    Signature deviation from the design record's
    ``normalized_equal(path_a, path_b, own_version)`` sketch, disclosed:
    the design's own B6 arms compare two DISTINCT versions (0.2.1 vs
    0.2.2), and a single ``own_version`` parameter cannot name both
    subtrees' version strings.

    KNOWN FALSE-ACCEPT CLASS (fold wave 2 R4): substring replacement
    masks a real difference in any non-version field that happens to BEAR
    a document's own version string ("tested-with": "0.2.1 itself") —
    both sides collapse to the placeholder and the pair admits. The R4
    XOR arms pin both directions; field-scoped replacement is the fix
    shape, deliberately not taken this slice.
    """
    placeholder = b"<OWN-VERSION>"
    return _normalize_subtree(path_a, version_a, placeholder) == _normalize_subtree(
        path_b, version_b, placeholder
    )


def _normalize_subtree(path: Path, version: str, placeholder: bytes) -> bytes:
    document = json.loads(path.read_bytes())
    return canonical_json(document).replace(version.encode(), placeholder)


# --- CLI command drivers -----------------------------------------------------------


def list_lines(root: Path) -> list[str]:
    """The ``standards list`` render: policy block + corpus rows, deterministic.

    One block per manifest standard: the active version and declared range,
    then the derived retained / carried / served sets, then every recorded
    yank (reason and since) and the retired identifiers.
    """
    manifest = load_manifest(root)
    policy = load_dependency_policy(root)
    # Fold wave 2 R2: the render trusts the cross-check, not the join — a
    # manifest/policy desync refuses here instead of KeyError-ing per entry.
    validate_dependency_policy(policy, manifest, root)
    lines: list[str] = []
    for entry in manifest.standards:
        row = policy.standards[entry.id]
        lines.append(
            f"standard {entry.id}@{entry.version} ({entry.status}) — "
            f"range >={row.lower},<{row.upper}"
        )
        if entry.dev is not None:
            # VR-9's stage distinction on the dependency lane's surface: the
            # open head is stage-tagged dev (release candidate when the
            # coordinator declared one) and names its pinning channel — the
            # ``versions`` glance carries the same fact (check.py
            # ``version_lines``).
            marker = ", release candidate" if entry.dev.candidate else ""
            lines.append(
                f"  dev head {entry.dev.version} (opened {entry.dev.opened}{marker}; "
                "pins are content-addressed opt-in, never auto-selected)"
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


def _dev_head_state(root: Path, resolution: Resolution) -> None:
    """The locked-check half of VR-29: a dev row's per-file digests must
    match the head's CURRENT working-tree bytes.

    Resolution is content-addressed (the object store at the recorded sha
    reproduces the lock forever); this check is the one that sees the head
    MOVE — the label is mutable, the pin is not. A moved or deleted head
    file refuses ``dev_pin_drift:`` naming the file, the lock's recorded
    digest and the head's current digest; the remediation is to move the
    opt-in to the head's current sha and re-pin. A file absent from the head
    directory entirely (the promotion teardown shape) refuses with the same
    prefix naming the orphaned file.
    """
    for row in resolution.document["standards"]:
        if row.get("stage") != "dev":
            continue
        head_dir = root / "standards" / str(row["id"]) / str(row["version"])
        for name, digest in sorted(row["files"].items()):
            path = head_dir / str(name)
            if not path.is_file():
                raise StandardsError(
                    f"dev_pin_drift: {row['id']} {row['version']}@{row['git_sha']} — "
                    f"standards/{row['id']}/{row['version']}/{name} is absent from "
                    "the head (moved on, or the promotion teardown deleted it); "
                    "the label is mutable, the pin is not — move the opt-in to a "
                    "live head state and re-pin"
                )
            current = hashlib.sha256(path.read_bytes()).hexdigest()
            if current != digest:
                raise StandardsError(
                    f"dev_pin_drift: {row['id']} {row['version']}@{row['git_sha']} — "
                    f"standards/{row['id']}/{row['version']}/{name} changed under "
                    f"the pin: the lock records {digest}, the head's bytes hash "
                    f"to {current}; the label is mutable, the pin is not — "
                    "commit the head's state, move the opt-in to its sha and "
                    "re-pin"
                )
        if head_dir.is_dir():
            # Refute fold, lane A (#218): a file ADDED to the head after the
            # pin is drift the lock cannot name — the loop above only sees
            # the lock's own files. Enumerate the head and refuse names
            # absent from the per-file map.
            for path in sorted(head_dir.rglob("*")):
                if not path.is_file():
                    continue
                name = path.relative_to(head_dir).as_posix()
                if name not in row["files"]:
                    raise StandardsError(
                        f"dev_pin_drift: {row['id']} {row['version']}@"
                        f"{row['git_sha']} — standards/{row['id']}/"
                        f"{row['version']}/{name} appeared in the head after "
                        "the pin and the lock names no such file; the label "
                        "is mutable, the pin is not — move the opt-in to the "
                        "head's current sha and re-pin"
                    )


def _scissors(
    prior: PriorLock, resolution: Resolution, revision: str | None
) -> list[str]:
    """Fold F4 (revision scissors), WRITE PATH ONLY: same-version digest
    motion against the prior map refuses unless ``--revision`` records the
    motion's revision; additions are not motion and carry the
    fetch-existence warning. Under a VERSION MOVE the map's shared names
    differ because they are different versions' corpus-frozen files, not
    because bytes moved at the recorded revision — refusing there would
    break every legitimate upgrade, so the gate applies only when the
    resolved otdp version is unchanged. A DEV-resolved otdp row skips the
    motion gate: its map's motion is anchored by the row's own git sha (a
    content address, stricter than a branch tip), so demanding ``--revision``
    beside it would be ceremony, not evidence.
    """
    lines: list[str] = []
    derived = {
        str(name): str(digest) for name, digest in resolution.document["sha256"].items()
    }
    additions = sorted(name for name in derived if name not in prior.file_map)
    if additions:
        lines.append(
            f"map addition: {', '.join(additions)} (no digest motion; each file "
            "must exist at the recorded revision — fetch verifies fail closed)"
        )
    otdp_dev = any(
        row.get("id") == "otdp" and row.get("stage") == "dev"
        for row in resolution.document["standards"]
    )
    if not otdp_dev and prior.rows.get("otdp") == str(resolution.document["otdp_version"]):
        motion = sorted(
            name
            for name, digest in derived.items()
            if name in prior.file_map and prior.file_map[name] != digest
        )
        if motion and revision is None:
            raise StandardsError(
                f"revision_scissors: the derived map's digest moved for "
                f"{', '.join(motion)} while the recorded revision stays "
                f"{prior.revision!r} — the map must digest the bytes AT the "
                "recorded revision; restore the bytes or pass "
                "pin --revision <sha> to record the motion's revision alongside it"
            )
    return lines


def pin_lock(
    root: Path,
    package: Path,
    sets: list[tuple[str, str]] | None = None,
    opt_ins: list[tuple[str, str]] | None = None,
    *,
    locked: bool = False,
    revision: str | None = None,
) -> list[str]:
    """The ``pin`` command: author through ``--set``/``--opt-in``, resolve,
    write the lock.

    ``--locked`` (VR-30) is verify-only: resolve in memory, byte-compare the
    on-disk lock, refuse ``plugin_lock_drift:`` on disagreement — zero
    network by construction, and never a write. ``--revision`` (fold F4)
    records a new revision alongside same-version digest motion. Every mode
    runs the dev head-state check (VR-29): a dev row whose head moved under
    the pin refuses ``dev_pin_drift:`` — a stale dev pin never re-verifies
    green anywhere.
    """
    if locked and sets:
        raise StandardsError(
            "constraint_set_invalid: --set authors the constraints file; --locked "
            "is verify-only and never writes"
        )
    if locked and opt_ins:
        raise StandardsError(
            "constraint_set_invalid: --opt-in authors the constraints file; "
            "--locked is verify-only and never writes"
        )
    if locked and revision is not None:
        raise StandardsError(
            "constraint_set_invalid: --revision records a new revision; --locked "
            "is verify-only and never writes"
        )
    if sets:
        apply_set(root, package, sets)
    if opt_ins:
        apply_opt_in(root, package, opt_ins)
    # The prior is loaded BEFORE any write: post-write, the just-written lock
    # would be its own prior and the scissors could never see motion.
    prior = load_prior_lock(package)
    resolution = resolve_package(root, package, revision=revision)
    _dev_head_state(root, resolution)
    if prior is None:  # unreachable: resolve_package refused on the absent lock
        raise StandardsError("plugin_lock_absent: the prior lock vanished mid-pin")
    path = package / "contracts" / "lock.json"
    if locked:
        if path.read_bytes() != resolution.raw:
            raise StandardsError(
                f"plugin_lock_drift: {path} — re-resolving the authored "
                "constraints does not reproduce the committed lock (hand-edited "
                "constraint, forged digest, stale lock, or a non-canonical "
                "serialization of identical values); run "
                f"python -m benchweave.standards pin --package {package}"
            )
        return list(resolution.warnings) + [f"lock agrees with the authored constraints: {path}"]
    lines = [*resolution.warnings, *_scissors(prior, resolution, revision)]
    written = write_lock(package, resolution.raw)
    lines.append(f"{'relocked' if written else 'lock already current'}: {path}")
    for row in resolution.document["standards"]:
        marker = " (dev)" if row.get("stage") == "dev" else ""
        lines.append(f"  {row['id']}@{row['version']}{marker}")
    return lines


def upgrade_lock(root: Path, package: Path, standard_id: str, precise: str) -> list[str]:
    """The ``upgrade`` command: one standard, one explicit target, minimal motion.

    Classification refusals (retired / unknown / not-served / dev / shape)
    fire inside the resolution before anything is written; a legal target —
    served, or yanked with the deprecation warning — re-locks the package
    with exactly this standard's row moved. The move line carries the
    migration-note pointer ("migration guidance pending" until slice 5).
    """
    policy = load_dependency_policy(root)
    constraints = load_constraints(package)
    if standard_id not in policy.standards:
        raise StandardsError(
            f"constraint_standard_unknown: {standard_id!r} names a standard the "
            f"dependency-policy block does not carry; supported: "
            f"{', '.join(sorted(policy.standards))}"
        )
    if standard_id not in constraints.standards:
        raise StandardsError(
            f"constraint_standard_unknown: {standard_id!r} is not in this package's "
            f"constraints ({', '.join(sorted(constraints.standards)) or 'none'})"
        )
    prior = load_prior_lock(package)
    if prior is None:
        raise StandardsError(
            f"plugin_lock_absent: {package / 'contracts' / 'lock.json'} — hand-author "
            "the v1 provenance keys (repository, revision, the otdp projection), "
            "then pin; fresh-lock creation is deferral D9"
        )
    resolution = resolve_package(root, package, precise={standard_id: precise})
    write_lock(package, resolution.raw)
    before = prior.rows.get(standard_id)
    lines = [*resolution.warnings, *_scissors(prior, resolution, None)]
    lines.append(
        f"{standard_id}: {before or 'unpinned'} -> {precise}; "
        "migration guidance pending"
    )
    return lines
