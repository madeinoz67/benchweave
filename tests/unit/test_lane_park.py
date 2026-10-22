"""scripts/lane_park.sh — the parked-lane ACK-or-stop bound.

Design record: ``.claude/deep-review/2026-10-21-issue517-parked-lane-stop-bound.md``
(tracker: madeinoz67/benchweave#517). The acceptance rows T1-T4 named by that
record map to the ``test_t*`` functions below.

Determinism: every commit is stamped through GIT_COMMITTER_DATE /
GIT_AUTHOR_DATE relative to the arm epoch parsed from ``PARK.intent`` — no
wall-clock assertion, no sleep, anywhere in this module.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "lane_park.sh"

# Verdict exit codes (the contract a wake shell asserts on).
QUIESCENT = 0
ACTIVE = 1
STRUCTURAL = 2

# A fixed past epoch for the scratch repo's initial commit: any real arm epoch
# orders strictly after it by construction.
_BASE_EPOCH = 1_700_000_000


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    assert SCRIPT.exists(), f"lane_park.sh missing at {SCRIPT}"
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _git(repo: Path, *args: str, dates: int | None = None) -> str:
    env = None
    if dates is not None:
        stamp = f"{dates} +0000"
        env = {
            **os.environ,
            "GIT_COMMITTER_DATE": stamp,
            "GIT_AUTHOR_DATE": stamp,
        }
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout


class _Scratch:
    """A scratch repo with one lane worktree on branch ``fix/<lane>``."""

    def __init__(self, root: Path, lane: str = "drill-lane") -> None:
        self.lane = lane
        self.branch = f"fix/{lane}"
        self.repo = root / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "park-drill@invalid")
        _git(self.repo, "config", "user.name", "Park Drill")
        (self.repo / "README.md").write_text("scratch park repo\n")
        _git(self.repo, "add", "README.md")
        _git(self.repo, "commit", "-m", "init", dates=_BASE_EPOCH)
        self.worktree = root / "wt"
        _git(self.repo, "worktree", "add", str(self.worktree), "-b", self.branch)

    # -- lane-side actions ---------------------------------------------------

    def commit(self, ts: int, message: str) -> None:
        _git(self.worktree, "commit", "--allow-empty", "-m", message, dates=ts)

    def ack(self) -> None:
        (self.worktree / "PARK-ACK").write_text(
            f"ack_epoch={int(time.time())} lane={self.lane}\n"
        )

    # -- orchestrator-side actions --------------------------------------------

    def arm(self, minutes: str = "15") -> subprocess.CompletedProcess[str]:
        return _run("arm", str(self.worktree), self.lane, minutes)

    def arm_epoch(self) -> int:
        text = (self.worktree / "PARK.intent").read_text()
        found = re.search(r"^armed_epoch=(\d+)$", text, re.M)
        assert found, f"no armed_epoch in PARK.intent:\n{text}"
        return int(found.group(1))

    def check(self) -> subprocess.CompletedProcess[str]:
        return _run("check", str(self.worktree))

    def head(self) -> str:
        return _git(self.worktree, "rev-parse", "HEAD").strip()


@pytest.fixture()
def park(tmp_path: Path) -> _Scratch:
    return _Scratch(tmp_path)


def test_t1_deaf_writer_committing_after_arm_is_active(park: _Scratch) -> None:
    """Acceptance T1: an ACKing lane that keeps committing after arm is ACTIVE.

    The lane ACKs (isolating the commits compare — the no-ACK half of the
    conjunction has its own arm below), then commits twice after the arm
    epoch. The record's RED rule pins this shape: disable the
    commits-since-arm compare and the verdict flips to QUIESCENT.
    """
    armed = park.arm()
    assert armed.returncode == 0, armed.stderr
    t0 = park.arm_epoch()
    park.ack()
    park.commit(t0 + 120, "deaf commit 1")
    park.commit(t0 + 240, "deaf commit 2")
    check = park.check()
    assert check.returncode == ACTIVE, check.stdout + check.stderr
    assert "ACTIVE" in check.stdout
    assert "commit" in check.stdout


def test_t2_ack_and_no_commits_is_quiescent(park: _Scratch) -> None:
    """Acceptance T2: ACK present and only pre-arm commits read QUIESCENT."""
    park.commit(int(time.time()) - 300, "pre-arm work")
    armed = park.arm()
    assert armed.returncode == 0, armed.stderr
    park.ack()
    check = park.check()
    assert check.returncode == QUIESCENT, check.stdout + check.stderr
    assert "QUIESCENT" in check.stdout


def test_check_active_without_ack(park: _Scratch) -> None:
    """Fail-closed arm: a silent-but-idle lane is still ACTIVE (no ACK)."""
    assert park.arm().returncode == 0
    check = park.check()
    assert check.returncode == ACTIVE
    assert "PARK-ACK" in check.stdout


def test_arm_refuses_rearm_while_bound(park: _Scratch) -> None:
    """The bound never extends: a second arm while PARK.intent exists refuses."""
    assert park.arm().returncode == 0
    first_epoch = park.arm_epoch()
    rearm = park.arm()
    assert rearm.returncode == STRUCTURAL
    assert park.arm_epoch() == first_epoch


def test_t3_fold_removes_worktree_and_preserves_ref(park: _Scratch) -> None:
    """Acceptance T3: fold removes the worktree and archives the branch ref."""
    assert park.arm().returncode == 0
    park.ack()
    tip = park.head()
    fold = _run("fold", str(park.worktree), park.lane)
    assert fold.returncode == 0, fold.stdout + fold.stderr
    listing = _git(park.repo, "worktree", "list")
    assert str(park.worktree) not in listing
    assert not park.worktree.exists()
    found = re.search(r"archived=(\S+)", fold.stdout)
    assert found, f"no archived= ref in fold output:\n{fold.stdout}"
    ref = found.group(1)
    assert ref.startswith("archive/parked/")
    assert _git(park.repo, "rev-parse", f"{ref}^{{commit}}").strip() == tip
    # the live lane branch is gone — run close leaves no live branches behind
    gone = subprocess.run(
        ["git", "-C", str(park.repo), "rev-parse", "--verify", park.branch],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert gone.returncode != 0
    # resume: the archived ref is a usable worktree base (Drill B's intact branch)
    resumed = park.repo.parent / "resumed"
    _git(park.repo, "worktree", "add", str(resumed), ref)
    assert _git(resumed, "rev-parse", "HEAD").strip() == tip


def test_t4_fold_succeeds_with_mid_write_partial_file(park: _Scratch) -> None:
    """Acceptance T4: fold force-removes a worktree carrying mid-write debris."""
    assert park.arm().returncode == 0
    readme = park.worktree / "README.md"
    with readme.open("a") as handle:  # mid-write: appended, no trailing newline
        handle.write("partial-write-no-newline")
    (park.worktree / "scratch.partial").write_text("untracked mid-write debris")
    fold = _run("fold", str(park.worktree), park.lane)
    assert fold.returncode == 0, fold.stdout + fold.stderr
    assert not park.worktree.exists()


def test_enforce_names_the_next_actions(park: _Scratch) -> None:
    """The wake verb mirrors check's verdict and names TaskStop + fold."""
    assert park.arm().returncode == 0
    t0 = park.arm_epoch()
    park.commit(t0 + 60, "still working")
    enforce = _run("enforce", str(park.worktree), park.lane)
    assert enforce.returncode == ACTIVE
    combined = enforce.stdout + enforce.stderr
    assert "TaskStop" in combined
    assert "fold" in combined
