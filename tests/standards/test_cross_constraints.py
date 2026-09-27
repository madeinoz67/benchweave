"""The cross-constraints side table: loader, retrofit row, exemption mechanics.

Issue #216 (#203 slice 2, design §1.4): ``standards/cross-constraints.json``
is governance data beside the two manifests — no corpus rows, no repin —
which is only mechanically true because the exemption lists in ``repin.py``
and ``tests/contract/test_baseline.py`` extend once, root-scoped. The loader
is fail-closed; the retrofit row set is exactly what the tree's recorded
evidence supports (one row today — the honest negatives are data, not gaps).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from benchweave.standards.dependency import load_cross_constraints
from benchweave.standards.export import canonical_json
from benchweave.standards.manifest import StandardsError

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "standards"
CROSS = CONTRACTS / "cross-constraints.json"


def _copy_standards(tmp_path: Path) -> Path:
    """A non-git root carrying the real standards tree, mutable per test."""
    root = tmp_path / "root"
    root.mkdir()
    shutil.copytree(ROOT / "standards", root / "standards")
    return root


def _rewrite(root: Path, mutate: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    document = json.loads((root / "standards/cross-constraints.json").read_bytes())
    document = mutate(document)
    (root / "standards/cross-constraints.json").write_bytes(canonical_json(document))


def test_the_retrofit_row_is_exactly_the_evidenced_set() -> None:
    """One row today: execution 0.2.0 requiring OTDP 0.2.x and adapter API
    1.1, citing PR #201's prose. Every other standard's absence is the
    recorded honest negative carried in the file's note."""
    rows = load_cross_constraints(ROOT)
    assert [(row.standard, row.version) for row in rows] == [("execution", "0.2.0")]
    row = rows[0]
    assert row.requires == {"otdp": ">=0.2.0,<0.3.0", "adapter_api": "1.1"}
    assert "PR #201" in row.evidence
    note = json.loads(CROSS.read_bytes())["note"]
    assert "plugin-ui" in note and "deliberate" in note


def test_absent_file_refuses_fail_closed(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    (root / "standards/cross-constraints.json").unlink()
    with pytest.raises(StandardsError, match="cross_constraint_invalid"):
        load_cross_constraints(root)


def test_shape_error_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    (root / "standards/cross-constraints.json").write_text("{}")
    with pytest.raises(StandardsError, match="cross_constraint_invalid"):
        load_cross_constraints(root)


def test_stored_sugar_in_a_requirement_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(document: dict[str, Any]) -> dict[str, Any]:
        document["rows"][0]["requires"]["otdp"] = "^0.2"
        return document

    _rewrite(root, mutate)
    with pytest.raises(StandardsError, match="constraint_syntax_unexpanded"):
        load_cross_constraints(root)


def test_a_row_naming_an_unretained_version_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(document: dict[str, Any]) -> dict[str, Any]:
        document["rows"][0]["version"] = "9.9.9"
        return document

    _rewrite(root, mutate)
    with pytest.raises(StandardsError, match="cross_constraint_unresolved"):
        load_cross_constraints(root)


def test_a_row_naming_an_unknown_standard_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(document: dict[str, Any]) -> dict[str, Any]:
        document["rows"][0]["standard"] = "nonexistent"
        return document

    _rewrite(root, mutate)
    with pytest.raises(StandardsError, match="constraint_standard_unknown"):
        load_cross_constraints(root)


def test_a_requirement_naming_an_unknown_standard_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(document: dict[str, Any]) -> dict[str, Any]:
        document["rows"][0]["requires"]["nonexistent"] = ">=0.1.0,<2.0.0"
        return document

    _rewrite(root, mutate)
    with pytest.raises(StandardsError, match="constraint_standard_unknown"):
        load_cross_constraints(root)


def test_a_malformed_adapter_api_requirement_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(document: dict[str, Any]) -> dict[str, Any]:
        document["rows"][0]["requires"]["adapter_api"] = "1"
        return document

    _rewrite(root, mutate)
    with pytest.raises(StandardsError, match="cross_constraint_invalid"):
        load_cross_constraints(root)


def test_a_duplicate_row_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(document: dict[str, Any]) -> dict[str, Any]:
        rows: list[Any] = document["rows"]
        rows.append(dict(rows[0]))
        return document

    _rewrite(root, mutate)
    with pytest.raises(StandardsError, match="cross_constraint_invalid"):
        load_cross_constraints(root)


# --- the exemption mechanics (design §1.4, risk 1) --------------------------------


def test_repin_returns_clean_with_the_file_present(tmp_path: Path) -> None:
    """The integration proof: on a tree carrying cross-constraints.json,
    ``repin_manifest`` finds nothing to do and does not refuse it as an
    unpinned corpus file (the root-scoped exemption at work)."""
    from benchweave.standards.repin import repin_manifest

    root = _copy_standards(tmp_path)
    assert repin_manifest(root) == []


def test_the_exemption_is_root_scoped_not_basename_scoped(tmp_path: Path) -> None:
    """The tightening proof: a NESTED file named corpus-manifest.json is NOT
    exempt — the old basename check would have excused it, the root-relative
    membership refuses it as corpus content (``corpus_file_unpinned:``)."""
    from benchweave.standards.repin import _check_coverage

    root = _copy_standards(tmp_path)
    nested = root / "standards" / "alpha" / "0.1.0"
    nested.mkdir(parents=True)
    (nested / "corpus-manifest.json").write_text("{}")
    with pytest.raises(StandardsError, match=r"corpus_file_unpinned: alpha/0.1.0"):
        _check_coverage(root, set())


def test_the_baseline_listing_admits_the_governance_file() -> None:
    """``_all_corpus_json_files`` and ``_contract_files`` both exclude the
    governance files by ROOT-RELATIVE path: cross-constraints.json is not a
    contract file (no $id walk), and the manifest-listing test compares only
    corpus content against corpus rows."""
    import importlib.util

    baseline_path = ROOT / "tests/contract/test_baseline.py"
    spec = importlib.util.spec_from_file_location("test_baseline_probe", baseline_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for helper in (module._all_corpus_json_files, module._contract_files):
        listed = {path.relative_to(CONTRACTS).as_posix() for path in helper()}
        for governance in (
            "corpus-manifest.json",
            "standards-manifest.json",
            "cross-constraints.json",
        ):
            assert governance not in listed
