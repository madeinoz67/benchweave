"""The catalogue mirror's authority pin (issue #224 slice 2, B2 plant 2's
second half).

``scripts/website/check_mirror_authority.py`` byte-compares the committed
mirror against the registry index at the commit its pin names (an immutable
SHA) — the synchronous gateway-side gate the render guard cannot cover: a
hand-edit to a non-rendering mirror field, a mirror advanced without its
pin, or a pin advanced without its mirror. CI runs the fetch path in the
``gates`` job; these arms run the comparison offline (``--expected``) and
the fail-closed behaviour through an unreachable URL (``--index-url``) —
no test requires the network.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "website" / "check_mirror_authority.py"
MIRROR = ROOT / "website" / "plugins-index.json"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_committed_mirror_agrees_with_its_authority() -> None:
    """Green pin: the committed mirror equals the authority bytes (offline
    seam: the mirror itself is the expected file — CI's fetch path is the
    same comparison against the registry's raw index)."""
    result = _run("--expected", str(MIRROR))
    assert result.returncode == 0, result.stderr
    assert "mirror matches" in result.stdout


def test_hand_edited_mirror_refuses_the_authority_pin(tmp_path: Path) -> None:
    """B2 plant 2, authority half: a hand-edit to ANY mirror field — even one
    the render guard cannot see — refuses with its machine prefix. The
    mirror is copied to a sandbox and edited there; the committed tree is
    never written."""
    sandbox = tmp_path / "repo"
    (sandbox / "website").mkdir(parents=True)
    shutil.copy2(MIRROR, sandbox / "website" / MIRROR.name)
    shutil.copy2(ROOT / "website" / "plugins-index.ref", sandbox / "website" / "plugins-index.ref")
    mirror = sandbox / "website" / MIRROR.name
    document = json.loads(mirror.read_text(encoding="utf-8"))
    document["rows"][0]["timestamp_recommended"] = not document["rows"][0]["timestamp_recommended"]
    mirror.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    result = _run("--root", str(sandbox), "--expected", str(MIRROR))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "mirror_authority_drift:" in result.stderr


def test_fetch_failure_fails_closed() -> None:
    """A network failure is indistinguishable from a missing mirror — fail
    closed with the same prefix (the design's one-retry rule)."""
    result = _run("--index-url", "http://127.0.0.1:1/index.json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "mirror_authority_drift:" in result.stderr


def test_a_mistyped_or_rewritten_ref_fails_closed() -> None:
    """A 404 (rewritten history or a mistyped pin) refuses — the immutable
    SHA is the structural guarantee, and its absence is loud."""
    result = _run("--index-url", "file:///nonexistent-registry-index.json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "mirror_authority_drift:" in result.stderr


def test_a_malformed_pin_refuses(tmp_path: Path) -> None:
    """The pin must be a full commit SHA: a moving-branch pin would make the
    authority a moving target and refuses."""
    sandbox = tmp_path / "repo"
    (sandbox / "website").mkdir(parents=True)
    shutil.copy2(MIRROR, sandbox / "website" / MIRROR.name)
    (sandbox / "website" / "plugins-index.ref").write_text(
        "refs/heads/main\n", encoding="utf-8"
    )
    result = _run("--root", str(sandbox))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "mirror_authority_drift:" in result.stderr
    assert "not a full commit SHA" in result.stderr
