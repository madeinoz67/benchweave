"""Class-reference coverage: every declared OTDP device class is accounted for.

The defect this gate closes: ``otdp`` may declare a device class that
``plugin-ui-class-reference`` carries no reference for, and nothing structural
says so. ``select_references`` is fail-open by design — an unreferenced profile
is skipped and the plugin renders the no-attachment absence — so the gap surfaces
at a plugin author's keyboard instead of at a gate.

The rule is total and two-directional:

1. every profile in the ACTIVE otdp catalogue has a reference in the ACTIVE
   class-reference family, or a row in the tracked sweep plan naming the slot
   that will deliver it;
2. every reference names a profile that catalogue declares (a stale reference
   would render for a class that does not exist);
The plan is APPEND-ONLY, and that is deliberate, not an oversight: the corpus
wins for a slug the plan and the family both carry, so a class landing needs no
edit to the shared file and parallel sweep lanes never conflict on it. Four
surfaces teach the rule: ``scripts/assemble_docs_site.py:756-758`` (loader note),
``scripts/assemble_docs_site.py:854-855`` (the plan validator's own docstring),
``docs/adding-a-device-class.md:37`` and
``docs/internal/drift-and-obligations.md:710-711``. A slug that is both
referenced and planned is therefore a VALID state — the row is a historical plan
entry, not a live delivery claim; the corpus decides delivery. An arm refusing
that pair was written, executed and then removed: it contradicted all four
surfaces and would have made every sweep increment edit one shared file.

The arm did buy one thing, and losing it reopens that case, so it is stated
rather than inferred: if a reference is deleted while its plan row stands, this
gate is GREEN. The row covers the gap and the loss is visible only at that
deletion's own review (a review-gated breaking corpus change). A green run must
never be read as "a class cannot lose its reference without a red".

Deliberately NOT checked: that every sweep-plan row names a declared profile. A
plan is a roadmap — the docs site renders an
unlanded row as "planned", and a slot may legitimately be named before otdp
declares the class. Refusing that shape would make this gate an obstacle to the
sweep program it protects, and it opens no silencing channel: a row only covers a
gap whose slug already matches a declared profile.

The register is ``docs/internal/classref-sweep-plan.json`` — tracked,
machine-readable, already validated by ``scripts/assemble_docs_site.py``. Why the
four current gaps are unbuilt is recorded in
``.claude/deep-review/2026-11-24-classref-coverage-gate-design.md`` (the sweep
order L18-L21, one class per increment).

This does NOT ride ``run_check``: that function's contract is the SDK mirror, and
its test fixtures are synthetic roots carrying no otdp corpus. The CLI composes
the two, so ``make check-sdk-standards`` — and therefore CI's ``gates`` job —
enforces this rule from tracked code alone.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .manifest import StandardsError, active_version_from_corpus

OTDP = "otdp"
CLASS_REFERENCE = "plugin-ui-class-reference"
# otdp.<class>/<major>.<minor>.<patch> — the class name is the middle segment.
# Deliberately the corpus's own grammar, not a looser one: it mirrors
# class-reference.schema.json `$defs.profile_id`, so this gate cannot admit a
# profile id the family schema would refuse.
PROFILE_PATTERN = re.compile(r"^otdp\.([a-z_]+)/\d+\.\d+\.\d+$")
SWEEP_PLAN = Path("docs") / "internal" / "classref-sweep-plan.json"


def _read_json(path: Path, prefix: str) -> tuple[dict[str, Any] | None, str | None]:
    """The parsed document, or ``(None, failure line)`` — never a traceback."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"{prefix}: cannot read {path.as_posix()} ({exc.strerror})"
    except ValueError as exc:
        return None, f"{prefix}: {path.as_posix()} is not valid JSON ({exc})"
    if not isinstance(document, dict):
        return None, f"{prefix}: {path.as_posix()} is not a JSON object"
    return document, None


def _declared_profiles(corpus: Path, version: str) -> tuple[dict[str, str], list[str]]:
    """The profile id -> class slug map the active catalogue declares."""
    path = corpus / OTDP / version / "device-profile-catalog.json"
    document, failure = _read_json(path, "classref_coverage_catalog_unreadable")
    if document is None:
        return {}, [failure or "classref_coverage_catalog_unreadable"]
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        return {}, [
            f"classref_coverage_catalog_unreadable: {path.as_posix()} carries no"
            " profiles array"
        ]
    declared: dict[str, str] = {}
    for row in profiles:
        profile_id = row.get("id") if isinstance(row, dict) else None
        match = PROFILE_PATTERN.match(profile_id) if isinstance(profile_id, str) else None
        if match is None:
            return {}, [
                "classref_coverage_catalog_unreadable: "
                f"{path.as_posix()} carries an unparsable profile id {profile_id!r}"
            ]
        declared[str(profile_id)] = match.group(1)
    return declared, []


def _reference_profiles(corpus: Path, version: str) -> tuple[set[str], list[str]]:
    """The profile ids the active family's class references bind."""
    family = corpus / CLASS_REFERENCE / version
    if not family.is_dir():
        return set(), [
            f"classref_coverage_references_absent: {family.as_posix()} does not exist"
        ]
    bound: set[str] = set()
    failures: list[str] = []
    for path in sorted(family.glob("class-*.json")):
        if path.name.endswith(".schema.json"):
            continue
        document, failure = _read_json(
            path, "classref_coverage_reference_unreadable"
        )
        if document is None:
            failures.append(failure or "classref_coverage_reference_unreadable")
            continue
        # The family walk's own discriminator (presentation.classref
        # ._find_reference): a class document is the schema's ``profile_id``.
        profile_id = document.get("profile_id")
        if isinstance(profile_id, str):
            bound.add(profile_id)
    return bound, failures


def _planned_slugs(root: Path) -> tuple[set[str], list[str]]:
    """The sweep plan's slugs, or a fail-closed refusal.

    Absence is a failure, not an empty plan: an empty plan would silently convert
    every future gap into a pass.
    """
    path = root / SWEEP_PLAN
    document, failure = _read_json(path, "classref_coverage_plan_unreadable")
    if document is None:
        return set(), [
            f"classref_coverage_plan_absent: {SWEEP_PLAN.as_posix()} is missing or"
            " unreadable; the sweep plan is the recorded roadmap register"
        ]
    rows = document.get("planned")
    if not isinstance(rows, list):
        return set(), [
            "classref_coverage_plan_unreadable: "
            f"{SWEEP_PLAN.as_posix()} carries no planned array"
        ]
    planned: set[str] = set()
    for row in rows:
        slug = row.get("slug") if isinstance(row, dict) else None
        slot = row.get("slot") if isinstance(row, dict) else None
        if not isinstance(slug, str) or not isinstance(slot, str):
            return set(), [
                "classref_coverage_plan_unreadable: "
                f"{SWEEP_PLAN.as_posix()} carries a row without a string slug and slot"
            ]
        planned.add(slug)
    return planned, []


def check_class_coverage(root: Path) -> list[str]:
    """``[]`` means every declared device class is accounted for."""
    corpus = root / "standards"
    try:
        otdp_version = active_version_from_corpus(corpus, OTDP)
        reference_version = active_version_from_corpus(corpus, CLASS_REFERENCE)
    except StandardsError as exc:
        return [f"classref_coverage_manifest_unreadable: {exc}"]

    declared, failures = _declared_profiles(corpus, otdp_version)
    if failures:
        return failures
    bound, failures = _reference_profiles(corpus, reference_version)
    if failures:
        return failures
    planned, failures = _planned_slugs(root)
    if failures:
        return failures

    failures = []
    for profile_id, slug in sorted(declared.items()):
        if profile_id in bound or slug in planned:
            continue
        failures.append(
            f"classref_coverage_missing: {profile_id} has no class reference in"
            f" {CLASS_REFERENCE}/{reference_version} and no sweep-plan row; add the"
            " reference or record the slot in "
            f"{SWEEP_PLAN.as_posix()}"
        )
    for profile_id in sorted(bound - set(declared)):
        failures.append(
            f"classref_coverage_stale: a reference binds {profile_id}, which"
            f" {OTDP}/{otdp_version} does not declare"
        )
    return failures
