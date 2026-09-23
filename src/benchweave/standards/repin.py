"""Recompute corpus-manifest sha256 rows from the on-disk corpus (repin).

The one mechanical writer of corpus-manifest pins: it rewrites existing rows'
digests and nothing else. Rows themselves — path, source, order, count — stay
hand-authored under governance review (``standards/GOVERNANCE.md``), because a
machine cannot know reset-import vs supersession-copy provenance.
Superseded-version rows are verified against their pinned digests and never
rewritten, so the command cannot launder an in-place edit of a retained
version into a clean manifest. A dev head's rows are regenerable like the
active rows' (the edit -> repin loop is the accumulation flow); rows with no
manifest-declared owner — superseded versions, orphaned dev rows — are
frozen. Every structural refusal fires before any
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
# The lineage amendment (governor re-check ruling 2026-09-23): the optional
# string a dev-stage promotion's rows carry naming the pre-dev active
# version's corresponding path — the predecessor edge the deleted staging
# directory cannot carry on its own.
_OPTIONAL_ROW_KEYS = frozenset({"lineage"})
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
    raw = manifest_path.read_bytes()
    try:
        document = _strict_loads(raw)
    except ValueError as exc:
        raise StandardsError(f"corpus_manifest_invalid: {exc}") from exc
    # The byte form of the manifest AS LOADED (before any digest mutation):
    # the write-path gate compares the raw bytes against this, never against
    # a dump of the already-mutated document.
    canonical_input = (json.dumps(document, indent=2) + "\n").encode()
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
        corpus_file = root / "standards" / path
        if corpus_file.is_symlink():
            # Adversary F4: a symlinked pinned file hashes whatever it
            # points at — a resolution-level escape the lexical traversal
            # check cannot see. The corpus is committed vendored content;
            # a symlink is a structural surprise, refused before the
            # target is read, regardless of drift.
            raise StandardsError(f"pinned_path_symlink: {path}")
        try:
            digest = hashlib.sha256(corpus_file.read_bytes()).hexdigest()
        except OSError as exc:
            # Adversary F5: a directory (or unreadable file) at a pinned
            # path is a refusal, not a traceback — it still matches the
            # coverage scan, so the failure would land mid-loop otherwise.
            raise StandardsError(
                f"pinned_path_unreadable: {path} ({exc.__class__.__name__})"
            ) from exc
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

    if raw != canonical_input:
        # Adversary F2: reads tolerate any parseable form; writes do not.
        # Serializing a compact/BOM/CRLF-shaped manifest back to canonical
        # form is a whole-file reflow beyond the digest being repinned —
        # corruption this command refuses to launder. Restore the file
        # (e.g. git checkout), then repin.
        raise StandardsError(
            "corpus_manifest_not_canonical: writes require the canonical "
            "indent-2 + trailing-newline byte form (a BOM, CRLF, or "
            "alternate serialization is hand corruption) — restore the "
            "file, then repin"
        )

    staged = manifest_path.parent / f"{manifest_path.name}.{os.getpid()}.tmp"
    try:
        staged.write_bytes((json.dumps(document, indent=2) + "\n").encode())
        os.chmod(staged, manifest_path.stat().st_mode)
        os.replace(staged, manifest_path)
    finally:
        # Post-replace this is a no-op; a failed replace must not leave
        # staging behind (adversary F3's cleanup half).
        staged.unlink(missing_ok=True)
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
        keys = set(row) if isinstance(row, dict) else set()
        allowed = _ROW_KEYS | _OPTIONAL_ROW_KEYS
        if not isinstance(row, dict) or not keys >= _ROW_KEYS or not keys <= allowed:
            # Exact keys, plus the lineage amendment's optional string: the
            # pre-dev predecessor edge a dev-stage promotion records on its
            # rows (governor re-check ruling 2026-09-23). No other key may
            # ride a row — the row shape stays closed-world.
            raise StandardsError(f"pin_row_invalid: {index}")
        if not all(isinstance(row[key], str) for key in keys):
            raise StandardsError(f"pin_row_invalid: {index}")
        path = str(row["path"])
        _check_row_path(path)
        lineage = row.get("lineage")
        if lineage is not None:
            _check_row_path(str(lineage))
            if any(part.endswith("-dev") for part in PurePosixPath(str(lineage)).parts):
                # Lineage names the pre-dev RELEASED edge; the dev edge is
                # what source carries. A -dev lineage is a field confusion,
                # refused outright rather than walked terminally here (the
                # derived-dir guard applies the same terminal to it as
                # defense in depth).
                raise StandardsError(
                    f"pin_row_lineage_invalid: {path}: {lineage} "
                    "(lineage names the pre-dev released edge; the dev edge is source's)"
                )
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
        # LEXICAL traversal only: a traversal or absolute row would make the
        # digest loop address files outside the corpus by PATH. It does not
        # see resolution-level escapes — a symlinked pinned file still
        # hashes its target; that guard is pinned_path_symlink in the
        # digest loop (adversary F4).
        raise StandardsError(f"pin_path_escape: {path}")


def _regenerable_paths(root: Path, pinned: set[str]) -> set[str]:
    """Normative standards/ paths are regenerable; every other row is frozen.

    Structural rule via the same authority validate_manifest uses — no string
    prefixes on row paths. A pinned machine file inside a current version dir
    that standards-manifest forgot to list classifies frozen, so editing its
    bytes is refused until the manifest gap is fixed: the failure points at
    the real defect. A dev head's paths join the regenerable set the same way
    (devstage §4.1): dev rows follow the edit -> repin loop until the head is
    promoted or abandoned — dev rows without the block classify frozen, which
    is the orphan-teardown catch, not a gap.
    """
    regenerable: set[str] = set()
    try:
        manifest = load_manifest(root)
    except FileNotFoundError as exc:
        # Adversary F5: the classifier's own authority missing is a
        # refusal, not a traceback — there is nothing to classify against.
        raise StandardsError(
            "standards_manifest_absent: standards/standards-manifest.json"
        ) from exc
    for entry in manifest.standards:
        relatives = list(entry.normative)
        if entry.dev is not None:
            relatives.extend(entry.dev.normative)
        for relative in relatives:
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
        path.relative_to(corpus).as_posix()  # manifest rows are '/'-separated (#138)
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
