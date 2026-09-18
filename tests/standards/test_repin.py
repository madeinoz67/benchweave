"""repin is the only mechanical writer of corpus-manifest sha256 rows.

Pins the pre-committed acceptance rule of the #46 design record: a single
regenerable edit moves exactly 1 of 78 rows (one manifest line, 64 hex
chars) with every other byte identical; the no-op run writes nothing; each
structural surprise refuses fail-closed with its exact prefix and leaves the
manifest byte-identical; and the output is byte-identical to the #45
hand-splice incumbent.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from benchweave.standards.manifest import (
    StandardsError,
    load_manifest,
    validate_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS_MANIFEST = "standards/corpus-manifest.json"
# One regenerable (normative) row and one frozen (superseded otdp/0.1.0) row.
REGENERABLE = "registry/0.1.0/examples/package-lock.json"
FROZEN = "otdp/0.1.0/device-profile-catalog.json"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _repin() -> Any:
    # Imported lazily so a missing module fails every test individually at the
    # call site instead of erroring the whole file at collection — the RED run
    # must show per-test failures, not a collection error.
    from benchweave.standards.repin import repin_manifest

    return repin_manifest


def _repo(tmp_path: Path) -> Path:
    """A faithful tmp repo: the real ``standards/`` tree plus the parity validator.

    repin's post-write self-check runs ``validate_manifest``, which checks every
    normative path — including the non-standards parity validator under
    ``src/`` — so a copy of ``standards/`` alone cannot pass a successful repin.
    """
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "standards", root / "standards")
    validator = root / "src/benchweave/presentation/contracts.py"
    validator.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "src/benchweave/presentation/contracts.py", validator)
    return root


def _manifest_bytes(root: Path) -> bytes:
    return (root / CORPUS_MANIFEST).read_bytes()


def _refused_without_write(root: Path, raw: bytes, prefix: str) -> None:
    with pytest.raises(StandardsError, match=prefix):
        _repin()(root)
    assert _manifest_bytes(root) == raw, "a refusal must not write"
    assert not list((root / "standards").glob("*.tmp")), "a refusal must not stage"


def _flip(root: Path, row_path: str) -> None:
    target = root / "standards" / row_path
    target.write_bytes(target.read_bytes() + b"\n")


def test_repin_round_trip_is_byte_identical() -> None:
    before = _manifest_bytes(ROOT)
    mtime = (ROOT / CORPUS_MANIFEST).stat().st_mtime_ns
    assert _repin()(ROOT) == []
    assert _manifest_bytes(ROOT) == before
    assert (ROOT / CORPUS_MANIFEST).stat().st_mtime_ns == mtime


def test_repin_updates_exactly_the_edited_row(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    raw = _manifest_bytes(root)
    before = json.loads(raw)
    _flip(root, REGENERABLE)

    changed = _repin()(root)

    assert changed == [REGENERABLE]
    after_raw = _manifest_bytes(root)
    after = json.loads(after_raw)
    new_digest = next(r["sha256"] for r in after["files"] if r["path"] == REGENERABLE)
    assert _HEX64.match(new_digest), f"not a 64-hex digest: {new_digest}"
    before_lines = raw.splitlines(keepends=True)
    after_lines = after_raw.splitlines(keepends=True)
    assert len(before_lines) == len(after_lines), "any reflow beyond one line is a kill"
    diff = [i for i, (a, b) in enumerate(zip(before_lines, after_lines, strict=True)) if a != b]
    assert len(diff) == 1, f"expected exactly one changed line, got {diff}"
    old_line, changed_line = before_lines[diff[0]], after_lines[diff[0]]
    old_digest = next(r["sha256"] for r in before["files"] if r["path"] == REGENERABLE)
    assert old_digest.encode() in old_line
    assert new_digest.encode() in changed_line
    assert b'"sha256"' in changed_line
    # Digest-only change within the line: every other byte of the line equal.
    assert old_line.replace(old_digest.encode(), b"") == changed_line.replace(
        new_digest.encode(), b""
    )
    assert not list((root / "standards").glob("*.tmp")), "write must not leave staging"
    # Parsed before/after: only the one digest moved; order, provenance and
    # identity are byte-preserved.
    assert [r["path"] for r in after["files"]] == [r["path"] for r in before["files"]]
    assert [r["source"] for r in after["files"]] == [r["source"] for r in before["files"]]
    assert after["identity"] == before["identity"]
    for old_row, new_row in zip(before["files"], after["files"], strict=True):
        if old_row["path"] == REGENERABLE:
            assert new_row["sha256"] != old_row["sha256"]
        else:
            assert new_row == old_row


def test_repin_matches_the_hand_splice(tmp_path: Path) -> None:
    # The #45 incumbent method, reproduced in-test: recompute the digest and
    # string-replace it in the raw bytes. repin must be byte-identical to it.
    root = _repo(tmp_path)
    raw = _manifest_bytes(root)
    _flip(root, REGENERABLE)
    new_digest = hashlib.sha256((root / "standards" / REGENERABLE).read_bytes()).hexdigest()
    old_digest = next(
        r["sha256"] for r in json.loads(raw)["files"] if r["path"] == REGENERABLE
    )
    assert raw.count(old_digest.encode()) == 1, "control assumes the digest is unique"
    splice = raw.replace(old_digest.encode(), new_digest.encode())

    _repin()(root)

    assert _manifest_bytes(root) == splice


def test_repin_refuses_frozen_row_edit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    raw = _manifest_bytes(root)
    _flip(root, FROZEN)
    _refused_without_write(root, raw, "frozen_row_changed")


def test_repin_refuses_unpinned_machine_file(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    raw = _manifest_bytes(root)
    (root / "standards/otdp/0.1.1/examples/stray-vectors.json").write_text(
        "{}\n", encoding="utf-8"
    )
    _refused_without_write(root, raw, "corpus_file_unpinned")


def test_repin_refuses_pinned_file_absent(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    raw = _manifest_bytes(root)
    (root / "standards" / REGENERABLE).unlink()
    _refused_without_write(root, raw, "pinned_file_absent")


def test_repin_refuses_duplicate_rows(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    document = json.loads(_manifest_bytes(root))
    document["files"].append(dict(document["files"][0]))
    (root / CORPUS_MANIFEST).write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    _refused_without_write(root, _manifest_bytes(root), "duplicate_pin_row")


def test_repin_refuses_normative_row_missing(tmp_path: Path) -> None:
    # The bump-flow ordering guard: a file listed in standards-manifest without
    # a corpus row is a manifest-authoring gap, refused before any digest work.
    root = _repo(tmp_path)
    raw = _manifest_bytes(root)
    (root / "standards/otdp/0.1.1/examples/extra-vectors.json").write_text(
        "{}\n", encoding="utf-8"
    )
    governance = json.loads((root / "standards/standards-manifest.json").read_bytes())
    entry = next(e for e in governance["standards"] if e["id"] == "otdp")
    entry["normative"].append("standards/otdp/0.1.1/examples/extra-vectors.json")
    (root / "standards/standards-manifest.json").write_text(
        json.dumps(governance, indent=2) + "\n", encoding="utf-8"
    )
    _refused_without_write(root, raw, "normative_not_in_corpus_manifest")


def test_repin_refuses_duplicate_key_manifest(tmp_path: Path) -> None:
    # A duplicate JSON key would be silently dropped by a load-modify-dump
    # round trip — a reflow beyond the digest being repinned. Strict load.
    root = _repo(tmp_path)
    lines = _manifest_bytes(root).splitlines(keepends=True)
    sha_line = next(i for i, line in enumerate(lines) if b'"sha256"' in line)
    lines.insert(sha_line + 1, lines[sha_line])
    (root / CORPUS_MANIFEST).write_bytes(b"".join(lines))
    _refused_without_write(root, _manifest_bytes(root), "corpus_manifest_invalid")


def test_cli_repin_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "benchweave.standards", "repin"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "already current" in result.stdout


def test_drift_without_repin_still_fails_validation(tmp_path: Path) -> None:
    # RED-sanity control for the mechanism's necessity: with no repin, a
    # flipped normative byte re-exposes the drift failure repin exists to
    # clear. This is a control, not a repin behavior — it passes pre-fix by
    # design, which is the point.
    root = _repo(tmp_path)
    _flip(root, REGENERABLE)
    with pytest.raises(StandardsError, match="normative_hash_mismatch"):
        validate_manifest(load_manifest(root), root)
