"""The bump window (#97): the prescriptive release-train floor, enforced.

Arms: the pure gap judgement (violation, boundary, per-standard), and a
scratch-repository family that drives the REAL collector end-to-end with
controlled committer dates — non-empty collection, the inside-floor refusal,
the admission and reset-class exemptions, and the real-tree grandfather row.
The scratch family is what makes a passing real-tree row non-vacuous: the
real tree correctly collects zero post-anchor bumps, and only the scratch
arms prove the collector can collect at all.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from benchweave.standards.train_window import (
    BumpEntry,
    TrainWindowError,
    check_train_windows,
    collect_bump_entries,
    window_violations,
)

ROOT = Path(__file__).resolve().parents[2]
FLOOR_48H = 48 * 3600
T0 = "2026-09-20T12:00:00+08:00"


def test_second_bump_inside_the_floor_is_refused() -> None:
    entries = (
        BumpEntry("otdp", "0.2.0", 1_000_000_000),
        BumpEntry("otdp", "0.2.1", 1_000_000_000 + 4 * 3600 + 480),
    )
    violations = window_violations(entries, FLOOR_48H)
    assert len(violations) == 1
    assert violations[0].startswith("train_window_violation: otdp 0.2.0 -> 0.2.1")
    assert "4.13h" in violations[0]


def test_bump_exactly_at_the_floor_passes() -> None:
    entries = (
        BumpEntry("otdp", "0.2.0", 1_000_000_000),
        BumpEntry("otdp", "0.2.1", 1_000_000_000 + FLOOR_48H),
    )
    assert window_violations(entries, FLOOR_48H) == ()


def test_per_standard_windows_are_independent() -> None:
    entries = (
        BumpEntry("otdp", "0.2.0", 1_000_000_000),
        BumpEntry("registry", "0.1.2", 1_000_000_000 + 3600),
        BumpEntry("registry", "0.1.3", 1_000_000_000 + 2 * 3600),
    )
    violations = window_violations(entries, FLOOR_48H)
    assert len(violations) == 1
    assert violations[0].startswith("train_window_violation: registry")


def _commit(repo: Path, date: str, *paths_contents: tuple[str, str]) -> None:
    for relative, content in paths_contents:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    env_dates = {
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-m", "w"],
        check=True,
        capture_output=True,
        env={**os.environ, **env_dates},
    )


def _scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "scratch"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    # The anchor: this module's own arrival, in-history for the scratch repo.
    _commit(
        repo,
        T0,
        ("src/benchweave/standards/train_window.py", "# anchor stand-in\n"),
    )
    return repo


def test_collector_reads_file_paths_and_refuses_inside_floor(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _commit(
        repo,
        "2026-09-20T14:55:00+08:00",  # 2.92h after admission: the first
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),  # non-admission bump —
    )  # it opens the window, nothing precedes it in the entry sequence
    entries = collect_bump_entries(repo)
    # Non-vacuity: the collector must read the FILE paths git emits and
    # derive their version directories — a return of () here is the dead
    # collector, not a clean window.
    assert [entry.version for entry in entries] == ["0.2.0"]
    check_train_windows(repo, FLOOR_48H)  # one bump: clean
    _commit(
        repo,
        "2026-09-20T15:55:00+08:00",  # 1h after 0.2.0 — inside the floor
        ("standards/otdp/0.2.1/x.schema.json", "{}\n"),
    )
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp"):
        check_train_windows(repo, FLOOR_48H)


def test_admission_is_exempt_and_newest_bump_is_judged(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _commit(
        repo,
        "2026-09-23T12:00:00+08:00",  # outside the floor: admission -> 0.2.0 is clean
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
    )
    _commit(
        repo,
        "2026-09-23T13:00:00+08:00",  # 1h after 0.2.0: the newest pair is judged
        ("standards/otdp/0.2.1/x.schema.json", "{}\n"),
    )
    with pytest.raises(TrainWindowError, match="otdp 0.2.0 -> 0.2.1"):
        check_train_windows(repo, FLOOR_48H)


def test_reset_class_commit_opens_fresh_windows(tmp_path: Path) -> None:
    repo = _scratch_repo(tmp_path)
    _commit(
        repo,
        T0,
        ("standards/otdp/0.1.0/x.schema.json", "{}\n"),
        ("standards/registry/0.1.0/x.schema.json", "{}\n"),
        ("standards/interface/0.1.0/x.schema.json", "{}\n"),
    )
    _commit(
        repo,
        "2026-09-20T13:00:00+08:00",  # 1h after the reset-class commit: the
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),  # reset opened fresh
    )  # windows — this bump starts otdp's, it is not judged against the reset
    check_train_windows(repo, FLOOR_48H)  # clean
    _commit(
        repo,
        "2026-09-20T14:00:00+08:00",  # 1h after 0.2.0: the pair the floor binds
        ("standards/otdp/0.2.1/x.schema.json", "{}\n"),
    )
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp"):
        check_train_windows(repo, FLOOR_48H)


def test_straddled_version_dir_counts_once(tmp_path: Path) -> None:
    # The real corpus straddled otdp 0.1.2 across two commits 26 seconds
    # apart; a version directory is one bump at its earliest commit, not a
    # zero-gap self-pair.
    repo = _scratch_repo(tmp_path)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _commit(repo, "2026-09-21T12:00:00+08:00", ("standards/otdp/0.2.0/a.json", "{}\n"))
    _commit(repo, "2026-09-21T12:00:26+08:00", ("standards/otdp/0.2.0/b.json", "{}\n"))
    entries = collect_bump_entries(repo)
    assert [entry.version for entry in entries] == ["0.2.0"]
    check_train_windows(repo, FLOOR_48H)  # clean: one bump, no self-pair


def test_real_tree_post_anchor_sequence_is_clean() -> None:
    # The real tree correctly collects zero post-anchor bumps (the anchor is
    # this module's arrival in THIS repository's history). The scratch family
    # above carries the non-vacuity burden; this row pins the deployment
    # state — grandfathering by mechanism, not a silent empty read.
    entries = collect_bump_entries(ROOT)
    assert window_violations(entries, FLOOR_48H) == ()
    assert check_train_windows(ROOT, FLOOR_48H) == ()
