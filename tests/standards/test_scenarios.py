"""Spec §10 scenarios: full export→sync→check cycles on throwaway corpus copies.

The real tree and the ``packages/sdk`` submodule are never mutated. Every
scenario builds a temporary "repo" from what the manifest names — ``standards/``,
``contracts/``, the parity validator, the plugin-ui docs tree — plus a temporary
SDK root populated by a first sync, then mutates the copy the way an operator
would and watches each gate's reaction.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

# The SDK lives in the submodule; expose it to this workspace test module
# (same bootstrap as tests/sdk/test_standards_sync.py) before importing it.
SDK_SRC = Path(__file__).resolve().parents[2] / "packages/sdk/src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from benchweave_sdk.standards_sync import SyncReport, sync  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

STANDARD = "plugin-ui"
OLD_VERSION = "0.1.0"
NEW_VERSION = "0.2.0"
# The scenario victim: normative, contracts-pinned, and mirrored under docs/.
NORMATIVE = "contracts/plugin-ui-v0.1.0/ui-manifest.schema.json"
PIN_KEY = "plugin-ui-v0.1.0/ui-manifest.schema.json"
DOC_README = "docs/plugin-ui-v0.1.0/README.md"
DOC_COPY = "docs/plugin-ui-v0.1.0/ui-manifest.schema.json"
PARITY = "src/benchweave/presentation/contracts.py"
ALL_IDS = {"otdp", "registry", "execution", "interface", "plugin-ui", "plugin-ui-preview"}


def _repo_copy(tmp_path: Path) -> Path:
    """Throwaway corpus: the trees the manifest names, nothing else."""
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(ROOT / "standards", repo / "standards")
    shutil.copytree(ROOT / "contracts", repo / "contracts")
    parity = repo / PARITY
    parity.parent.mkdir(parents=True)
    shutil.copy2(ROOT / PARITY, parity)
    shutil.copytree(ROOT / "docs/plugin-ui-v0.1.0", repo / "docs/plugin-ui-v0.1.0")
    return repo


def _synced_sdk(tmp_path: Path, bundle: Path) -> Path:
    """Import the bundle into a fresh throwaway SDK root; asserts the import ran."""
    sdk = tmp_path / "sdk"
    (sdk / "src/benchweave_sdk").mkdir(parents=True)
    (sdk / "src/benchweave_sdk/__init__.py").write_text("")
    first = sync(bundle, sdk)
    assert set(first.added) == ALL_IDS
    return sdk


def _first_cycle(tmp_path: Path, repo: Path) -> tuple[Path, Path]:
    """Baseline: one export→sync on the throwaway corpus, clean by construction."""
    from benchweave.standards.export import export_bundle

    bundle = tmp_path / "bundle"
    export_bundle(repo, bundle)
    return bundle, _synced_sdk(tmp_path, bundle)


def _break_normative(repo: Path) -> None:
    """A real content change: new bytes, still valid JSON, new digest."""
    document: dict[str, Any] = json.loads((repo / NORMATIVE).read_bytes())
    document["x_scenario_breaking_change"] = "renamed a required binding field"
    (repo / NORMATIVE).write_text(json.dumps(document, indent=2) + "\n")


def _bump_version(repo: Path) -> None:
    """The matching standards version increment in the canonical manifest."""
    document: dict[str, Any] = json.loads(
        (repo / "standards/standards-manifest.json").read_bytes()
    )
    entry = next(s for s in document["standards"] if s["id"] == STANDARD)
    assert entry["version"] == OLD_VERSION
    entry["version"] = NEW_VERSION
    (repo / "standards/standards-manifest.json").write_text(
        json.dumps(document, indent=2) + "\n"
    )


def _repin(repo: Path) -> None:
    """Point the contracts pin back at the (mutated) bytes on disk."""
    document: dict[str, Any] = json.loads((repo / "contracts/manifest.json").read_bytes())
    row = next(f for f in document["files"] if f["path"] == PIN_KEY)
    row["sha256"] = hashlib.sha256((repo / NORMATIVE).read_bytes()).hexdigest()
    (repo / "contracts/manifest.json").write_text(json.dumps(document, indent=2) + "\n")


def _stamp_line(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("STAMP_LINE = "):
            return line
    raise AssertionError(f"STAMP_LINE definition not found in {path}")


def test_spec10_unchanged_cycle_is_a_no_op(tmp_path: Path) -> None:
    """Spec §10 scenario 1 (unchanged): re-sync reports nothing, check is clean."""
    from benchweave.standards.check import run_check

    repo = _repo_copy(tmp_path)
    bundle, sdk = _first_cycle(tmp_path, repo)
    assert sync(bundle, sdk) == SyncReport((), (), (), ())
    assert run_check(repo, sdk) == []


def test_spec10_clarification_outside_normative_set_is_no_delta(tmp_path: Path) -> None:
    """Spec §10 scenario 2 (compatible clarification): prose is not normative."""
    from benchweave.standards.check import run_check
    from benchweave.standards.export import export_bundle

    repo = _repo_copy(tmp_path)
    bundle, sdk = _first_cycle(tmp_path, repo)
    before = (bundle / "bundle-manifest.json").read_bytes()
    readme = repo / DOC_README
    readme.write_text(readme.read_text() + "\nClarification: prose only, no contract change.\n")
    export_bundle(repo, bundle)
    # The bundle manifest is byte-identical: the docs edit moved nothing normative.
    assert (bundle / "bundle-manifest.json").read_bytes() == before
    assert sync(bundle, sdk) == SyncReport((), (), (), ())
    assert run_check(repo, sdk) == []


def test_spec10_versioned_breaking_change_updates_the_lock(tmp_path: Path) -> None:
    """Spec §10 scenario 3 (breaking positive): content + version + pin move together."""
    from benchweave.standards.check import run_check
    from benchweave.standards.export import export_bundle

    repo = _repo_copy(tmp_path)
    bundle, sdk = _first_cycle(tmp_path, repo)
    _break_normative(repo)
    _bump_version(repo)
    _repin(repo)
    shutil.copy2(repo / NORMATIVE, repo / DOC_COPY)  # keep the docs mirror honest
    export_bundle(repo, bundle)
    report = sync(bundle, sdk)
    assert report.changed == (STANDARD,)
    assert report.added == () and report.deprecated == () and report.removed == ()
    lock: dict[str, Any] = json.loads((sdk / "standards-lock.json").read_bytes())
    entry = next(s for s in lock["standards"] if s["id"] == STANDARD)
    assert entry["version"] == NEW_VERSION
    assert run_check(repo, sdk) == []


def test_spec10_unversioned_breaking_change_refused_at_every_gate(tmp_path: Path) -> None:
    """Spec §10 scenario 4 (breaking negative): mutation without the bump refuses."""
    from benchweave.standards.check import run_check
    from benchweave.standards.export import export_bundle
    from benchweave.standards.manifest import (
        StandardsError,
        load_manifest,
        validate_manifest,
    )

    repo = _repo_copy(tmp_path)
    bundle, sdk = _first_cycle(tmp_path, repo)
    _break_normative(repo)  # no version bump, no pin update

    # Gate 1: the contracts pin refuses first — stale pin vs mutated bytes.
    with pytest.raises(StandardsError, match="normative_hash_mismatch"):
        validate_manifest(load_manifest(repo), repo)
    # Gate 2: run_check refuses the same way — the export fails closed.
    with pytest.raises(StandardsError, match="normative_hash_mismatch"):
        run_check(repo, sdk)
    # Gate 3: even a repaired pin does not excuse the missing version bump.
    _repin(repo)
    export_bundle(repo, bundle)  # succeeds: the pin now matches the bytes
    with pytest.raises(ValueError, match="standards_version_required"):
        sync(bundle, sdk)
    # And the checker reports the same-version drift instead of passing.
    failures = run_check(repo, sdk)
    prefixes = {line.split(":", 1)[0] for line in failures}
    assert "content_drift_without_version" in prefixes


def test_stamp_line_is_identical_in_checker_and_sdk() -> None:
    """T6 concern: check.py's stamp mirror must byte-equal the SDK's stamp format."""
    checker = _stamp_line(ROOT / "src/benchweave/standards/check.py")
    sdk = _stamp_line(ROOT / "packages/sdk/src/benchweave_sdk/standards_sync.py")
    assert checker == sdk, (
        "STAMP_LINE drifted between src/benchweave/standards/check.py and "
        "packages/sdk/src/benchweave_sdk/standards_sync.py — every stamp would "
        "read as stale; update whichever file fell behind"
    )


def test_check_only_stray_file_gate_symmetry(tmp_path: Path) -> None:
    """T7 follow-up: how the two --check lanes treat a stray vendored file.

    Asymmetry pinned here deliberately, not fixed (a close-out decision):
    bundle-mode --check verifies only the lock-recorded paths and lets a stray
    extra file through, while the no-bundle lane recomputes the whole tree and
    refuses it.
    """
    from benchweave.standards.export import export_bundle

    bundle = tmp_path / "bundle"
    export_bundle(ROOT, bundle)
    sdk = _synced_sdk(tmp_path, bundle)
    stray = sdk / "src/benchweave_sdk/standards" / STANDARD / "EXTRA.txt"
    stray.write_text("not in the lock\n")
    assert sync(bundle, sdk, check_only=True) == SyncReport((), (), (), ())
    with pytest.raises(ValueError, match="unexpected_vendored_file"):
        sync(None, sdk, check_only=True)
