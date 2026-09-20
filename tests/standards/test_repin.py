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
import os
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
REGENERABLE = "registry/0.1.1/examples/package-lock.json"
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


def _current_repo(tmp_path: Path) -> Path:
    """A tmp copy whose manifest is CURRENT whatever the working tree's
    state: mid-bump drift the copy inherits is normalized by one repin on
    the COPY (adversary F1 — the repo tree itself is never repinned from a
    test). A copy that refuses normalization (say, frozen-row drift)
    still fails loudly here: that state cannot be made current by repin,
    and the failure names a tree problem, not a test problem."""
    root = _repo(tmp_path)
    _repin()(root)
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


def test_repin_round_trip_is_byte_identical(tmp_path: Path) -> None:
    # Adversary F1: anchored on a normalized tmp copy, never the repo
    # tree — a no-op assertion against a drifted real ROOT is a writer
    # (it repins the working tree and masks its own failure on the
    # rerun), and an UN-normalized copy inherits working-tree drift and
    # fails for a reason that is not the behavior under test.
    root = _current_repo(tmp_path)
    before = _manifest_bytes(root)
    mtime = (root / CORPUS_MANIFEST).stat().st_mtime_ns
    assert _repin()(root) == []
    assert _manifest_bytes(root) == before
    assert (root / CORPUS_MANIFEST).stat().st_mtime_ns == mtime


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


def test_cli_repin_runs(tmp_path: Path) -> None:
    # Adversary F1: the CLI smoke runs against a normalized tmp copy —
    # cwd IS the command's root, so a cwd of the repo tree would repin it
    # on a drifted checkout, and an un-normalized copy would fail the
    # "already current" assert on inherited drift.
    root = _current_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "benchweave.standards", "repin"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "already current" in result.stdout


def test_tests_never_repin_the_repo_tree() -> None:
    """Adversary F1 guard: the suite must never invoke repin against the
    repo ROOT — on a drifted checkout a "no-op" test is a writer that can
    put an unreviewed pin move into the next ``git add -A``. The needles
    are regexes whose own source forms cannot match, so this guard cannot
    trip on itself."""
    source = Path(__file__).read_text(encoding="utf-8")
    assert not re.search(r"_repin\(\)\(\s*ROOT", source), (
        "repin must be invoked on tmp copies, never the repo ROOT"
    )
    assert not re.search(r"cwd\s*=\s*ROOT\b", source), (
        "the CLI smoke's cwd is the command's root"
    )


def test_drift_without_repin_still_fails_validation(tmp_path: Path) -> None:
    # RED-sanity control for the mechanism's necessity: with no repin, a
    # flipped normative byte re-exposes the drift failure repin exists to
    # clear. This is a control, not a repin behavior — it passes pre-fix by
    # design, which is the point.
    root = _repo(tmp_path)
    _flip(root, REGENERABLE)
    with pytest.raises(StandardsError, match="normative_hash_mismatch"):
        validate_manifest(load_manifest(root), root)


# --- adversary follow-up rows (PR #52): F2 canonical-write gate -------------------


def _non_canonical(name: str, document: Any) -> bytes:
    """Three hand-corrupted shapes that still parse: compact separators, a
    UTF-8 BOM, and CRLF line endings (adversary F2's reproducer set)."""
    if name == "compact":
        return json.dumps(document, separators=(",", ":")).encode()
    if name == "bom":
        return json.dumps(document, indent=2).encode("utf-8-sig")
    return (json.dumps(document, indent=2) + "\n").encode().replace(b"\n", b"\r\n")


@pytest.mark.parametrize("shape", ["compact", "bom", "crlf"])
def test_repin_refuses_to_write_a_non_canonical_manifest(
    tmp_path: Path, shape: str
) -> None:
    """F2: reads tolerate any parseable form; writes do not. A drifted
    digest in a compact/BOM/CRLF-shaped manifest must refuse rather than
    rewrite the whole file to canonical form — a reflow beyond the digest
    being repinned, visible only as a noisy diff."""
    root = _repo(tmp_path)
    _flip(root, REGENERABLE)
    document = json.loads(_manifest_bytes(root))
    shaped = _non_canonical(shape, document)
    (root / CORPUS_MANIFEST).write_bytes(shaped)

    with pytest.raises(StandardsError, match="corpus_manifest_not_canonical"):
        _repin()(root)
    assert _manifest_bytes(root) == shaped, "a refusal must not write"
    assert not list((root / "standards").glob("*.tmp")), "a refusal must not stage"


def test_repin_noop_tolerates_a_non_canonical_manifest(tmp_path: Path) -> None:
    """F2 boundary: a non-canonical manifest whose digests are all current
    is a read, not a write — no-op, zero bytes, no quiet canonicalization."""
    root = _repo(tmp_path)
    shaped = _non_canonical("compact", json.loads(_manifest_bytes(root)))
    (root / CORPUS_MANIFEST).write_bytes(shaped)

    assert _repin()(root) == []
    assert _manifest_bytes(root) == shaped


# --- adversary follow-up rows (PR #52): F3 staging, F4 symlink, F5 refusals -------


def test_staging_name_is_process_unique(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F3: the staging sibling embeds the pid — two concurrent repin
    processes never share a .tmp file (the observed race truncated the
    manifest to transiently-empty bytes). Captured at the os.replace seam,
    so the property is pinned deterministically rather than by racing in
    CI; the pid is per-process, which is the real concurrent-caller shape
    (the CLI), not threads."""
    root = _repo(tmp_path)
    _flip(root, REGENERABLE)
    captured: list[str] = []
    real_replace = os.replace

    def spy(src: str, dst: str) -> None:  # pragma: no cover - thin seam
        captured.append(src)
        real_replace(src, dst)

    monkeypatch.setattr("benchweave.standards.repin.os.replace", spy)
    _repin()(root)

    assert captured, "the spy must have seen the replace"
    assert str(os.getpid()) in Path(captured[0]).name, (
        "the staging name must embed the pid (unique per concurrent process)"
    )
    assert not list((root / "standards").glob("*.tmp")), "no staging left behind"


def test_repin_refuses_a_symlinked_pinned_file(tmp_path: Path) -> None:
    """F4: a pinned path that is a symlink hashes whatever it points at —
    a resolution-level escape the lexical traversal check cannot see
    (its comment claimed that scope; the scope lives here instead).
    Refused regardless of drift, before any read of the target."""
    root = _repo(tmp_path)
    outside = tmp_path / "outside-the-corpus.json"
    outside.write_bytes(root.joinpath("standards", REGENERABLE).read_bytes())
    linked = root / "standards" / REGENERABLE
    linked.unlink()
    linked.symlink_to(outside)
    raw = _manifest_bytes(root)

    with pytest.raises(StandardsError, match="pinned_path_symlink"):
        _repin()(root)
    assert _manifest_bytes(root) == raw
    assert not list((root / "standards").glob("*.tmp"))


def test_repin_refuses_a_pinned_directory(tmp_path: Path) -> None:
    """F5: a pinned path that is a directory fails as a refusal, not an
    uncaught IsADirectoryError traceback (a *.json-named directory still
    matches the coverage scan, so the failure lands in the digest loop)."""
    root = _repo(tmp_path)
    victim = root / "standards" / REGENERABLE
    victim.unlink()
    victim.mkdir()
    raw = _manifest_bytes(root)

    with pytest.raises(StandardsError, match="pinned_path_unreadable"):
        _repin()(root)
    assert _manifest_bytes(root) == raw


def test_repin_refuses_a_missing_standards_manifest(tmp_path: Path) -> None:
    """F5: the classifier's authority (standards-manifest.json) missing is
    a refusal, not an uncaught FileNotFoundError traceback."""
    root = _repo(tmp_path)
    (root / "standards/standards-manifest.json").unlink()
    raw = _manifest_bytes(root)

    with pytest.raises(StandardsError, match="standards_manifest_absent"):
        _repin()(root)
    assert _manifest_bytes(root) == raw
