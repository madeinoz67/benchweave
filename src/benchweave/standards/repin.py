"""Recompute corpus-manifest sha256 rows from the on-disk corpus (repin).

The one mechanical writer of corpus-manifest pins: it rewrites existing rows'
digests and nothing else. Rows themselves — path, source, order, count — stay
hand-authored under governance review (``standards/GOVERNANCE.md``), because a
machine cannot know reset-import vs supersession-copy provenance.
Superseded-version rows are verified against their pinned digests and never
rewritten, so the command cannot launder an in-place edit of a retained
version into a clean manifest. Every structural refusal fires before any
byte is written; the one after-write exception is the validate_manifest
self-check, which can raise on a missing non-standards normative parity
path (unchecked pre-write) after the manifest is already correctly
written — the write is not lost, and the next run is a no-op.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .manifest import StandardsError, load_manifest, validate_manifest

_ROW_KEYS = frozenset({"path", "source", "sha256"})
_MANIFESTS = frozenset({"corpus-manifest.json", "standards-manifest.json"})


def repin_manifest(root: Path) -> list[str]:
    """Recompute corpus-manifest sha256 rows from the on-disk corpus.

    Existing rows only: row creation/deletion and ``source`` provenance stay
    hand-authored under governance review. Superseded-version rows are
    verified, never rewritten. Fails closed before any write; writes only when
    a digest actually changed. Returns the paths whose pins changed.
    """
    manifest_path = root / "standards/corpus-manifest.json"
    if not manifest_path.is_file():
        # Unlike _corpus_pins (which tolerates absence), a pin command with no
        # rows to pin is a hard error.
        raise StandardsError("corpus_manifest_absent: standards/corpus-manifest.json")
    try:
        document = _strict_loads(manifest_path.read_bytes())
    except ValueError as exc:
        raise StandardsError(f"corpus_manifest_invalid: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("files"), list):
        raise StandardsError("corpus_manifest_invalid: files must be a list")
    rows: list[Any] = document["files"]

    _validate_rows(rows)
    pinned = {str(row["path"]) for row in rows}
    # Classification precedes the disk-coverage scan so a normative path with
    # no row is named as the manifest-authoring gap it is (the bump flow
    # authors rows before repin runs), not as a stray disk file.
    regenerable = _regenerable_paths(root, pinned)
    _check_coverage(root, pinned)

    changed: list[str] = []
    for row in rows:
        path = str(row["path"])
        digest = hashlib.sha256((root / "standards" / path).read_bytes()).hexdigest()
        if path in regenerable:
            if row["sha256"] != digest:
                row["sha256"] = digest
                changed.append(path)
        elif row["sha256"] != digest:
            # GOVERNANCE "copy, never move": retained-version bytes are frozen.
            # Repinning them would paper over an in-place edit of a retained
            # version — restore the bytes or do a proper bump instead.
            raise StandardsError(f"frozen_row_changed: {path}")
    if not changed:
        return []

    staged = manifest_path.parent / (manifest_path.name + ".tmp")
    staged.write_bytes((json.dumps(document, indent=2) + "\n").encode())
    os.chmod(staged, manifest_path.stat().st_mode)
    os.replace(staged, manifest_path)
    # A raise here is a repin bug failing loudly, not a repaired state.
    validate_manifest(load_manifest(root), root)
    return changed


def _strict_loads(raw: bytes) -> Any:
    """Reject duplicate keys and non-finite constants (test_baseline's loader).

    A plain json.loads would let a duplicate-key manifest load, and the
    load-modify-dump write would silently drop the duplicate — a reflow beyond
    the digest being repinned.
    """

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(raw, object_pairs_hook=reject_pairs, parse_constant=reject_constant)


def _validate_rows(rows: list[Any]) -> None:
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise StandardsError(f"pin_row_invalid: {index}")
        if not all(isinstance(row[key], str) for key in _ROW_KEYS):
            raise StandardsError(f"pin_row_invalid: {index}")
        path = str(row["path"])
        _check_row_path(path)
        if path in seen:
            # Stricter than _corpus_pins, which collapses duplicates silently:
            # a duplicate row is a structural surprise, not a pin.
            raise StandardsError(f"duplicate_pin_row: {path}")
        seen.add(path)


def _check_row_path(path: str) -> None:
    posix = PurePosixPath(path)
    windows = PureWindowsPath(path)
    if (
        not path
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or "\\" in path
        or ".." in posix.parts
    ):
        # The digest loop reads root/"standards"/path; a traversal or absolute
        # row would hash files outside the corpus.
        raise StandardsError(f"pin_path_escape: {path}")


def _regenerable_paths(root: Path, pinned: set[str]) -> set[str]:
    """Normative standards/ paths are regenerable; every other row is frozen.

    Structural rule via the same authority validate_manifest uses — no string
    prefixes on row paths. A pinned machine file inside a current version dir
    that standards-manifest forgot to list classifies frozen, so editing its
    bytes is refused until the manifest gap is fixed: the failure points at
    the real defect.
    """
    regenerable: set[str] = set()
    for entry in load_manifest(root).standards:
        for relative in entry.normative:
            if not relative.startswith("standards/"):
                continue  # The parity validator carries no pin (manifest.py).
            corpus_path = relative.removeprefix("standards/")
            regenerable.add(corpus_path)
            if corpus_path not in pinned:
                raise StandardsError(f"normative_not_in_corpus_manifest: {relative}")
    return regenerable


def _check_coverage(root: Path, pinned: set[str]) -> None:
    """Rows == machine files on disk, both directions (test_baseline's set)."""
    corpus = root / "standards"
    on_disk = {
        str(path.relative_to(corpus))
        for path in corpus.rglob("*.json")
        if path.name not in _MANIFESTS
    }
    unpinned = sorted(on_disk - pinned)
    if unpinned:
        # repin cannot invent source provenance; author the rows first.
        raise StandardsError(f"corpus_file_unpinned: {unpinned[0]}")
    absent = sorted(pinned - on_disk)
    if absent:
        raise StandardsError(f"pinned_file_absent: {absent[0]}")
