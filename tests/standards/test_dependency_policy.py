"""The dependency-policy block: one committed authority for ranges and statuses.

Issue #203 slice 1 (design §3.1–3.2): ``standards/standards-manifest.json``
gains a top-level ``dependency_policy`` block beside ``sdk_compatibility``,
read by its own fail-closed loader, cross-checked against the retained tree,
and the SERVED SET is derived from it (retained ∧ in-range ∧ ¬yanked) — never
hand-listed. Every refusal here carries a machine-matchable prefix.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from benchweave.standards.manifest import (
    StandardsError,
    load_dependency_policy,
    load_manifest,
    served_versions,
    validate_dependency_policy,
)

ROOT = Path(__file__).resolve().parents[2]


def _copy_standards(tmp_path: Path) -> Path:
    """A non-git root carrying the real standards tree, mutable per test."""
    root = tmp_path / "root"
    root.mkdir()
    shutil.copytree(ROOT / "standards", root / "standards")
    return root


def _edit_policy(root: Path, mutate: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """Rewrite the dependency_policy block through ``mutate``."""
    path = root / "standards/standards-manifest.json"
    document = json.loads(path.read_bytes())
    document["dependency_policy"] = mutate(document["dependency_policy"])
    path.write_text(json.dumps(document, indent=2))


def test_policy_block_loads_and_derives_the_served_set() -> None:
    """Design §3.2's seed served set, per-id: otdp {0.2.0, 0.2.2} (0.2.1
    yanked-in-interval), registry {0.1.0, 0.1.1}, execution {0.1.0, 0.2.0},
    interface {0.1.0}, plugin-ui {0.2.0} (F1 narrow range),
    plugin-ui-preview {0.1.0, 0.1.1}. The design record says "9 served
    versions" but its own enumeration sums to 10 — the per-id sets are the
    load-bearing rules (each traced to retained directories and declared
    ranges); the total is their consequence. Recorded as a design arithmetic
    slip in the slice measurement record."""
    policy = load_dependency_policy(ROOT)
    manifest = load_manifest(ROOT)
    validate_dependency_policy(policy, manifest, ROOT)
    served = {
        entry.id: served_versions(policy, ROOT, entry.id) for entry in manifest.standards
    }
    assert served == {
        "otdp": ("0.2.0", "0.2.2"),
        "registry": ("0.1.0", "0.1.1"),
        "execution": ("0.1.0", "0.2.0"),
        "interface": ("0.1.0",),
        "plugin-ui": ("0.2.0",),
        "plugin-ui-preview": ("0.1.0", "0.1.1"),
    }
    assert sum(len(versions) for versions in served.values()) == 10


def test_missing_policy_block_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)
    path = root / "standards/standards-manifest.json"
    document = json.loads(path.read_bytes())
    del document["dependency_policy"]
    path.write_text(json.dumps(document))
    with pytest.raises(StandardsError, match="dependency_policy_invalid"):
        load_dependency_policy(root)


def test_caret_syntax_in_a_stored_range_refuses(tmp_path: Path) -> None:
    """Caret sugar is AUTHORING input; a caret stored in a committed file
    refuses (design §3.1, prefix ``constraint_syntax_unexpanded:``)."""
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["otdp"]["range"] = "^0.2"
        return block

    _edit_policy(root, mutate)
    with pytest.raises(StandardsError, match="constraint_syntax_unexpanded"):
        load_dependency_policy(root)


def test_malformed_range_shape_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["otdp"]["range"] = ">=0.2.0"  # missing exclusive upper
        return block

    _edit_policy(root, mutate)
    with pytest.raises(StandardsError, match="dependency_policy_invalid"):
        load_dependency_policy(root)


def test_yanked_entry_naming_an_unretained_version_refuses(tmp_path: Path) -> None:
    """A yanked version must be retained: bytes have to exist for a
    yanked-but-conforming pin to validate against (design §3.1)."""
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["otdp"]["yanked"]["9.9.9"] = {
            "reason": "synthetic",
            "since": "2026-09-26",
        }
        return block

    _edit_policy(root, mutate)
    policy = load_dependency_policy(root)  # shape-valid; the cross-check refuses
    with pytest.raises(StandardsError, match="policy_entry_unresolved"):
        validate_dependency_policy(policy, load_manifest(root), root)


# --- #215 fold row 4: the yank record's since is machine-readable history. ---


@pytest.mark.parametrize("since", ["not-a-date", "26-09-2026", ""])
def test_yanked_entry_with_a_non_iso_since_refuses(tmp_path: Path, since: str) -> None:
    """Fold row 4 (#215): ``since`` was gated only as "a string", unlike the
    dev-head ``opened`` field's shape gate. A yank date that is not an ISO
    YYYY-MM-DD string refuses at load — the record is machine-readable
    history, not free prose."""
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["otdp"]["yanked"]["0.2.1"]["since"] = since
        return block

    _edit_policy(root, mutate)
    with pytest.raises(StandardsError, match="not an ISO YYYY-MM-DD date"):
        load_dependency_policy(root)


@pytest.mark.parametrize("since", ["2026-13-45", "9999-99-99", "2026-02-30"])
def test_yanked_entry_with_an_impossible_calendar_date_refuses(
    tmp_path: Path, since: str
) -> None:
    """The shape gate admits impossible calendars; only a real parse refuses
    them — the same two-step gate the dev-head ``opened`` field runs
    (manifest.py review row 4)."""
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["otdp"]["yanked"]["0.2.1"]["since"] = since
        return block

    _edit_policy(root, mutate)
    with pytest.raises(StandardsError, match="not a real calendar date"):
        load_dependency_policy(root)


def test_retired_entry_naming_the_active_version_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["otdp"]["retired"] = ["0.2.2"]
        return block

    _edit_policy(root, mutate)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="policy_retired_active"):
        validate_dependency_policy(policy, load_manifest(root), root)


def test_retired_entry_naming_a_retained_version_refuses(tmp_path: Path) -> None:
    """Retired means "used and dead": the number shipped once and the tree no
    longer carries it. A retired entry naming any retained version is a status
    conflict — the live directory contradicts "dead" (design §3.1: retired
    identifiers are the pre-reset enumeration; this test pins the resolution
    of the design's ``policy_entry_unresolved`` wording, which as literally
    written would refuse the seed block itself — see the design deviation note
    in the slice record)."""
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["otdp"]["retired"] = ["0.2.0"]
        return block

    _edit_policy(root, mutate)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="policy_status_conflict"):
        validate_dependency_policy(policy, load_manifest(root), root)


def test_yanked_and_retired_must_be_disjoint(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["otdp"]["retired"] = ["0.2.1"]
        return block

    _edit_policy(root, mutate)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="policy_status_conflict"):
        validate_dependency_policy(policy, load_manifest(root), root)


def test_policy_row_for_an_unknown_standard_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["nonexistent"] = {"range": ">=0.1.0,<0.2.0", "yanked": {}, "retired": []}
        return block

    _edit_policy(root, mutate)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="dependency_policy_invalid"):
        validate_dependency_policy(policy, load_manifest(root), root)


def test_manifest_standard_missing_from_the_policy_refuses(tmp_path: Path) -> None:
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        del block["standards"]["registry"]
        return block

    _edit_policy(root, mutate)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="dependency_policy_invalid"):
        validate_dependency_policy(policy, load_manifest(root), root)


def test_active_version_outside_the_served_set_refuses(tmp_path: Path) -> None:
    """The manifest's active version is retained by construction; a range that
    excludes it (or a yank on it) is incoherent with the manifest and refuses."""
    root = _copy_standards(tmp_path)

    def mutate(block: dict[str, Any]) -> dict[str, Any]:
        block["standards"]["otdp"]["range"] = ">=0.2.0,<0.2.2"  # excludes active 0.2.2
        return block

    _edit_policy(root, mutate)
    policy = load_dependency_policy(root)
    with pytest.raises(StandardsError, match="dependency_policy_invalid"):
        validate_dependency_policy(policy, load_manifest(root), root)


def test_served_set_excludes_yanked_in_interval_versions() -> None:
    """0.2.1 is retained and in-interval but yanked — excluded from serving."""
    policy = load_dependency_policy(ROOT)
    assert "0.2.1" not in served_versions(policy, ROOT, "otdp")


def test_version_literal_ratchet_holds_at_the_baseline() -> None:
    """A4: the committed counter runs clean on the real tree and is
    reproducible (two runs, byte-identical output). The planted-literal
    refusal is pinned beside this test (fold row 13) — the teeth are
    committed, not cited."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/standards/count_version_literals.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    first = result.stdout
    second = subprocess.run(
        [sys.executable, str(ROOT / "scripts/standards/count_version_literals.py")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert first == second


def test_a_planted_literal_fails_the_ratchet_in_a_scratch_copy(tmp_path: Path) -> None:
    """Fold row 13 (#215): the A4 ratchet's refusal is demonstrated by the
    committed test the slice record cites. A scratch copy of the repo's
    source tree plus ONE planted version literal makes the committed counter
    report the risen count and exit 1 — ratchet mode refuses, never warns."""
    import subprocess

    scratch = tmp_path / "scratch-repo"
    (scratch / "scripts/standards").mkdir(parents=True)
    shutil.copy(
        ROOT / "scripts/standards/count_version_literals.py",
        scratch / "scripts/standards/count_version_literals.py",
    )
    shutil.copytree(ROOT / "src/benchweave", scratch / "src/benchweave")
    (scratch / "src/benchweave" / "planted_literal.py").write_text(
        'OTDP_PIN = "0.2.2"\n', encoding="utf-8"
    )
    script = scratch / "scripts/standards/count_version_literals.py"
    risen = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )
    assert risen.returncode == 1, risen.stdout + risen.stderr
    assert "(baseline 12, EXCEEDED)" in risen.stdout
    detail = subprocess.run(
        [sys.executable, str(script), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert detail.returncode == 1
    payload = json.loads(detail.stdout)
    assert payload["count"] == payload["baseline"] + 1
    assert any(
        row["file"] == "src/benchweave/planted_literal.py" for row in payload["sites"]
    )
