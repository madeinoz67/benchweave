"""The class-reference coverage gate (design record
``.claude/deep-review/2026-11-24-classref-coverage-gate-design.md``).

One no-regression arm over the real tracked tree, then one arm per refusal shape
on synthetic trees: missing reference with no plan row, stale reference, unknown
plan row, absent sweep plan. The gate's value is that it goes RED at the commit
that adds a declared-but-unreferenced class, so every refusal shape carries its
own arm rather than riding one happy path.

The CLI composition is asserted directly: ``check`` must report coverage failures
alongside the SDK-mirror lines, from tracked code, or the rule is a library nobody
runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchweave.standards.coverage import check_class_coverage

ROOT = Path(__file__).resolve().parents[2]

OTDP_VERSION = "0.1.0"
REFERENCE_VERSION = "0.1.0"
PROFILES = ["otdp.alpha/1.0.0", "otdp.beta/1.0.0"]


def _write(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def _tree(tmp_path: Path) -> Path:
    """A minimal corpus: two declared profiles, one reference, one planned row."""
    root = tmp_path
    _write(
        root / "standards" / "standards-manifest.json",
        {
            "manifest_version": 1,
            "standards": [
                {"id": "otdp", "version": OTDP_VERSION},
                {"id": "plugin-ui-class-reference", "version": REFERENCE_VERSION},
            ],
        },
    )
    _write(
        root / "standards" / "otdp" / OTDP_VERSION / "device-profile-catalog.json",
        {"profiles": [{"id": profile} for profile in PROFILES]},
    )
    _write(
        root
        / "standards"
        / "plugin-ui-class-reference"
        / REFERENCE_VERSION
        / "class-alpha.json",
        {"profile_id": "otdp.alpha/1.0.0"},
    )
    _write(
        root / "docs" / "internal" / "classref-sweep-plan.json",
        {"planned": [{"slug": "beta", "slot": "L9"}]},
    )
    return root


def _messages(root: Path) -> str:
    return "\n".join(check_class_coverage(root))


def test_the_tracked_tree_is_fully_accounted_for() -> None:
    """No regression: every class otdp/0.2.4 declares is referenced or planned."""
    assert check_class_coverage(ROOT) == []


def test_a_declared_class_with_nothing_accounting_for_it_reds(tmp_path: Path) -> None:
    """The gap the gate exists for: a NEW class, no reference, no plan row."""
    root = _tree(tmp_path)
    _write(
        root / "standards" / "otdp" / OTDP_VERSION / "device-profile-catalog.json",
        {"profiles": [{"id": profile} for profile in PROFILES + ["otdp.gamma/1.0.0"]]},
    )
    messages = _messages(root)
    assert "classref_coverage_missing: otdp.gamma/1.0.0" in messages


def test_a_reference_naming_an_undeclared_profile_reds(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    _write(
        root
        / "standards"
        / "plugin-ui-class-reference"
        / REFERENCE_VERSION
        / "class-delta.json",
        {"profile_id": "otdp.delta/1.0.0"},
    )
    messages = _messages(root)
    assert "classref_coverage_stale: a reference binds otdp.delta/1.0.0" in messages


def test_a_plan_row_for_a_class_otdp_has_not_declared_yet_is_accepted(
    tmp_path: Path,
) -> None:
    """The plan is a roadmap as well as an exception register: a slot may be
    named before otdp declares the class, and the docs site renders such a row
    as "planned". Refusing it would make the gate an obstacle to the sweep
    program it protects — and it opens no silencing channel, because a row only
    covers a gap whose slug already matches a declared profile."""
    root = _tree(tmp_path)
    _write(
        root / "docs" / "internal" / "classref-sweep-plan.json",
        {"planned": [{"slug": "beta", "slot": "L9"}, {"slug": "zhou", "slot": "L10"}]},
    )
    assert check_class_coverage(root) == []


def test_a_landed_class_keeping_its_row_is_accepted(tmp_path: Path) -> None:
    """The plan is APPEND-ONLY by design: the corpus wins for a slug both carry,
    so a class landing needs no edit to the shared file and parallel sweep lanes
    never conflict on one (`scripts/assemble_docs_site.py:755-758`,
    `docs/adding-a-device-class.md`, `docs/internal/drift-and-obligations.md`).

    An arm refusing this pair was written, executed and REMOVED — it contradicted
    all three surfaces and would have made every sweep increment edit one shared
    file. This arm pins the append-only state so the removal cannot creep back."""
    root = _tree(tmp_path)
    _write(
        root / "docs" / "internal" / "classref-sweep-plan.json",
        {"planned": [{"slug": "beta", "slot": "L9"}, {"slug": "alpha", "slot": "L8"}]},
    )
    assert check_class_coverage(root) == []


def test_an_absent_sweep_plan_reds_rather_than_passing_empty(tmp_path: Path) -> None:
    """Absence must not read as "no exceptions owed" — that would silently turn
    every future gap into a pass."""
    root = _tree(tmp_path)
    (root / "docs" / "internal" / "classref-sweep-plan.json").unlink()
    messages = _messages(root)
    assert "classref_coverage_plan_absent" in messages


def test_the_schema_file_in_the_family_is_not_read_as_a_reference() -> None:
    """``class-reference.schema.json`` globs as ``class-*.json``; reading it as a
    reference would red the real tree with a stale-binding failure."""
    assert "classref_coverage_stale" not in _messages(ROOT)
