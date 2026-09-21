"""Non-mutating check that the pinned SDK mirrors the canonical standards.

The bundle re-exported to a throwaway directory is the authority: the lock and
the vendored tree are compared against it, never rewritten. An empty failure
list is the only clean state; every failure is one ``prefix: detail`` line.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from .export import export_bundle
from .manifest import load_identity, load_manifest

LOCK_NAME = "standards-lock.json"
VENDORED = "src/benchweave_sdk/standards"
STAMP_NAME = "_GENERATED.txt"
# Mirrors standards_sync.STAMP_LINE in the SDK; a format change there must be
# mirrored here or every stamp reads as stale.
STAMP_LINE = "{path} — Generated from {identifier}@{version} — do not edit"


def run_check(root: Path, sdk_root: Path | None = None) -> list[str]:
    """Verify the pinned SDK against a fresh export; ``[]`` means clean.

    Re-exports the bundle into a temporary directory (never the working tree),
    then compares versions, digests, the vendored file set and the
    compatibility block.
    """
    sdk = sdk_root if sdk_root is not None else root / "packages" / "sdk"
    workspace = Path(tempfile.mkdtemp(prefix="benchweave-standards-check-"))
    try:
        bundle_root = workspace / "bundle"
        export_bundle(root, bundle_root)
        document: dict[str, Any] = json.loads(
            (bundle_root / "bundle-manifest.json").read_bytes()
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    lock = _read_lock(sdk)
    failures: list[str] = []
    failures.extend(_compare_lock(document, lock))
    failures.extend(_compare_tree(document, sdk))
    failures.extend(_compare_compatibility(document, lock))
    return failures


def version_lines(root: Path, sdk_root: Path | None = None) -> list[str]:
    """Version table: main project, per standard, adapter api, SDK lock, submodule SHA."""
    sdk = sdk_root if sdk_root is not None else root / "packages" / "sdk"
    lines = [f"benchweave {main_version(root)}"]
    for entry in load_manifest(root).standards:
        lines.append(f"standard {entry.id}@{entry.version} ({entry.status})")
    # Reported, not trusted: the declared value is derive-checked at every
    # export/check (manifest.validate_identity); undeclared says so.
    lines.append(f"adapter api {load_identity(root).get('adapter_api', 'undeclared')}")
    for row in sorted(_read_lock(sdk).get("standards", []), key=lambda item: str(item["id"])):
        lines.append(f"sdk lock {row['id']}@{row['version']}")
    lines.append(f"submodule packages/sdk {submodule_sha(sdk)}")
    return lines


def main_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def submodule_sha(sdk: Path) -> str:
    result = subprocess.run(  # noqa: S603 — fixed argv
        ["git", "-C", str(sdk), "rev-parse", "--short", "HEAD"],  # noqa: S607 — PATH git is the supported invocation
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _read_lock(sdk: Path) -> dict[str, Any]:
    """An absent lock reads as empty: every standard then reports as unpinned."""
    path = sdk / LOCK_NAME
    if not path.is_file():
        return {"standards": []}
    lock: dict[str, Any] = json.loads(path.read_bytes())
    return lock


def _digests(row: dict[str, Any]) -> dict[str, str]:
    return {str(file["path"]): str(file["sha256"]) for file in row["files"]}


def _compare_lock(document: dict[str, Any], lock: dict[str, Any]) -> list[str]:
    """Main manifest vs SDK lock: pinning, versions and same-version drift."""
    failures: list[str] = []
    lock_rows = {str(row["id"]): row for row in lock.get("standards", [])}
    bundle_rows = {str(row["id"]): row for row in document["standards"]}
    for row in document["standards"]:
        identifier = str(row["id"])
        prior = lock_rows.get(identifier)
        if prior is None:
            failures.append(f"pinned_sdk_incompatible: {identifier} absent from the SDK lock")
            continue
        if prior["version"] != row["version"]:
            failures.append(
                f"sdk_version_mismatch: {identifier} manifest {row['version']} "
                f"vs SDK lock {prior['version']}"
            )
            continue
        exported = _digests(row)
        recorded = _digests(prior)
        for path in sorted(set(exported) | set(recorded)):
            if exported.get(path) != recorded.get(path):
                failures.append(
                    f"content_drift_without_version: {path} differs between manifest "
                    f"and SDK lock at {row['version']}"
                )
    for identifier in sorted(set(lock_rows) - set(bundle_rows)):
        failures.append(
            f"stale_generated: {identifier}/ vendored for a standard the manifest "
            "no longer lists"
        )
    return failures


def _compare_tree(document: dict[str, Any], sdk: Path) -> list[str]:
    """Vendored bytes and file set vs what sync-standards would write."""
    failures: list[str] = []
    tree = sdk / VENDORED
    if not tree.is_dir():
        failures.append(f"missing_asset: {VENDORED}/ absent; run sync-standards first")
        return failures
    exported: dict[str, str] = {}
    stamps: dict[str, set[str]] = {}
    for row in document["standards"]:
        identifier = str(row["id"])
        for path, digest in _digests(row).items():
            exported[path] = digest
        stamps[identifier] = {
            STAMP_LINE.format(path=path, identifier=identifier, version=str(row["version"]))
            for path in _digests(row)
        }
    present = {
        path.relative_to(tree).as_posix()  # lock rows are '/'-separated (#138)
        for path in tree.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    stamp_paths = {f"{identifier}/{STAMP_NAME}" for identifier in stamps}
    for path in sorted(present - set(exported) - stamp_paths):
        failures.append(f"stale_generated: {VENDORED}/{path} is not written by sync-standards")
    for path in sorted(set(exported) - present):
        failures.append(f"missing_asset: {VENDORED}/{path} absent from the vendored tree")
    for path in sorted(exported):
        target = tree / path
        if not target.is_file():
            continue  # already reported as missing_asset
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != exported[path]:
            failures.append(
                f"hash_mismatch: {VENDORED}/{path} bytes differ from the exported digest"
            )
            failures.append(
                f"stale_generated: {VENDORED}/{path} differs from what sync would write"
            )
    for identifier, expected_lines in sorted(stamps.items()):
        stamp = tree / identifier / STAMP_NAME
        if not stamp.is_file():
            failures.append(f"stale_generated: {VENDORED}/{identifier}/{STAMP_NAME} missing")
            continue
        if set(stamp.read_text(encoding="utf-8").splitlines()) != expected_lines:
            failures.append(
                f"stale_generated: {VENDORED}/{identifier}/{STAMP_NAME} does not "
                "match the exported standard"
            )
    return failures


def _compare_compatibility(document: dict[str, Any], lock: dict[str, Any]) -> list[str]:
    """Changed or deprecated standards require a complete compatibility block."""
    triggers: list[str] = []
    lock_rows = {str(row["id"]): row for row in lock.get("standards", [])}
    for row in document["standards"]:
        identifier = str(row["id"])
        prior = lock_rows.get(identifier)
        if row["status"] == "deprecated" or (
            prior is not None and prior["version"] != row["version"]
        ):
            triggers.append(identifier)
    if not triggers:
        return []
    compatibility = lock.get("compatibility")
    compatibility = compatibility if isinstance(compatibility, dict) else {}
    missing = [
        field for field in ("main_project", "sdk", "notes") if not compatibility.get(field)
    ]
    if missing:
        return [
            "compatibility_incomplete: "
            f"{', '.join(sorted(triggers))} changed or deprecated but the SDK lock "
            f"compatibility block lacks {', '.join(missing)}"
        ]
    return []
