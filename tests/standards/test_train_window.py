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
# Owner revisit 2026-09-23: the 48h starting figure -> 24h, after one window ran
# and its observed cost was latency (a queued fold-after-release), not churn.
FLOOR_SECONDS = 24 * 3600
T0 = "2026-09-20T12:00:00+08:00"


def test_second_bump_inside_the_floor_is_refused() -> None:
    entries = (
        BumpEntry("otdp", "0.2.0", 1_000_000_000),
        BumpEntry("otdp", "0.2.1", 1_000_000_000 + 4 * 3600 + 480),
    )
    violations = window_violations(entries, FLOOR_SECONDS)
    assert len(violations) == 1
    assert violations[0].startswith("train_window_violation: otdp 0.2.0 -> 0.2.1")
    assert "4.13h" in violations[0]


def test_bump_exactly_at_the_floor_passes() -> None:
    entries = (
        BumpEntry("otdp", "0.2.0", 1_000_000_000),
        BumpEntry("otdp", "0.2.1", 1_000_000_000 + FLOOR_SECONDS),
    )
    assert window_violations(entries, FLOOR_SECONDS) == ()


def test_per_standard_windows_are_independent() -> None:
    entries = (
        BumpEntry("otdp", "0.2.0", 1_000_000_000),
        BumpEntry("registry", "0.1.2", 1_000_000_000 + 3600),
        BumpEntry("registry", "0.1.3", 1_000_000_000 + 2 * 3600),
    )
    violations = window_violations(entries, FLOOR_SECONDS)
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
    check_train_windows(repo, FLOOR_SECONDS)  # one bump: clean
    _commit(
        repo,
        "2026-09-20T15:55:00+08:00",  # 1h after 0.2.0 — inside the floor
        ("standards/otdp/0.2.1/x.schema.json", "{}\n"),
    )
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp"):
        check_train_windows(repo, FLOOR_SECONDS)


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
        check_train_windows(repo, FLOOR_SECONDS)


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
    check_train_windows(repo, FLOOR_SECONDS)  # clean
    _commit(
        repo,
        "2026-09-20T14:00:00+08:00",  # 1h after 0.2.0: the pair the floor binds
        ("standards/otdp/0.2.1/x.schema.json", "{}\n"),
    )
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp"):
        check_train_windows(repo, FLOOR_SECONDS)


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
    check_train_windows(repo, FLOOR_SECONDS)  # clean: one bump, no self-pair


def test_same_commit_double_version_is_a_zero_gap_violation(tmp_path: Path) -> None:
    # Two version directories of one standard in a single commit is the
    # most extreme window violation (0h by GOVERNANCE's "each new version
    # directory"); it must refuse, not collapse to the last-listed version.
    repo = _scratch_repo(tmp_path)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _commit(
        repo,
        "2026-09-22T12:00:00+08:00",
        ("standards/otdp/0.2.0/a.json", "{}\n"),
        ("standards/otdp/0.3.0/a.json", "{}\n"),
    )
    with pytest.raises(TrainWindowError, match="otdp 0.2.0 -> 0.3.0"):
        check_train_windows(repo, FLOOR_SECONDS)


def test_delete_and_readd_does_not_reanchor_the_clock(tmp_path: Path) -> None:
    # A landed violation must survive the module being dropped and re-added
    # (revert + re-land is ordinary GitHub flow); the anchor is the FIRST
    # arrival of the module, not the newest add git happens to list.
    repo = _scratch_repo(tmp_path)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _commit(repo, "2026-09-22T12:00:00+08:00", ("standards/otdp/0.2.0/x.json", "{}\n"))
    _commit(repo, "2026-09-22T13:00:00+08:00", ("standards/otdp/0.2.1/x.json", "{}\n"))
    with pytest.raises(TrainWindowError, match="otdp 0.2.0 -> 0.2.1"):
        check_train_windows(repo, FLOOR_SECONDS)
    module = repo / "src/benchweave/standards/train_window.py"
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "rm", "-q", str(module.relative_to(repo))],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-m", "rm"],
        check=True, capture_output=True,
        env={**os.environ, "GIT_AUTHOR_DATE": "2026-09-22T15:00:00+08:00",
             "GIT_COMMITTER_DATE": "2026-09-22T15:00:00+08:00"},
    )
    _commit(repo, "2026-09-22T16:00:00+08:00",
            ("src/benchweave/standards/train_window.py", "# re-landed\n"))
    with pytest.raises(TrainWindowError, match="otdp 0.2.0 -> 0.2.1"):
        check_train_windows(repo, FLOOR_SECONDS)


def test_shallow_clone_of_a_violating_repo_refuses_to_judge(tmp_path: Path) -> None:
    # A depth-1 clone grafts every standards file onto HEAD as Added; the
    # surviving per-standard version reads as admission and launders the
    # violation clean. The collector must detect a shallow repository and
    # refuse rather than judge.
    repo = _scratch_repo(tmp_path)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _commit(repo, "2026-09-23T12:00:00+08:00", ("standards/otdp/0.2.0/x.json", "{}\n"))
    _commit(repo, "2026-09-23T13:00:00+08:00", ("standards/otdp/0.2.1/x.json", "{}\n"))
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--no-local", str(repo), str(shallow)],
        check=True, capture_output=True,
    )
    (shallow / "src/benchweave/standards").mkdir(parents=True, exist_ok=True)
    (shallow / "src/benchweave/standards/train_window.py").write_text("# present\n")
    with pytest.raises(TrainWindowError, match="train_window_history_unreadable"):
        collect_bump_entries(shallow)


def test_real_tree_post_anchor_sequence_is_clean() -> None:
    # The real tree correctly collects zero post-anchor bumps (the anchor is
    # this module's arrival in THIS repository's history). The scratch family
    # above carries the non-vacuity burden; this row pins the deployment
    # state — grandfathering by mechanism, not a silent empty read.
    entries = collect_bump_entries(ROOT)
    assert window_violations(entries, FLOOR_SECONDS) == ()
    assert check_train_windows(ROOT, FLOOR_SECONDS) == ()


def test_dev_directory_addition_is_invisible_to_the_window(tmp_path: Path) -> None:
    # The -dev stage's arm-D differential (devstage design record §9),
    # pinned in-suite: the identical history with the change in a dev head
    # is clean, while the pure-semver version-directory bump inside the
    # same closed window fires. This pins the zero-collector-changes claim
    # (§4.5) mechanically — a future _VERSION_PATH edit that starts
    # counting dev directories would reprice authoring as releasing.
    repo = _scratch_repo(tmp_path)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _commit(repo, "2026-09-23T12:00:00+08:00", ("standards/otdp/0.2.0/x.json", "{}\n"))
    # The dev head opens 1h after 0.2.0 — inside the closed window:
    _commit(repo, "2026-09-23T13:00:00+08:00", ("standards/otdp/0.2.1-dev/x.json", "{}\n"))
    entries = collect_bump_entries(repo)
    assert [entry.version for entry in entries] == ["0.2.0"], (
        "a dev-directory addition must not collect as a bump"
    )
    check_train_windows(repo, FLOOR_SECONDS)  # clean: the head is invisible
    # The control half: the same landing as a real version directory fires.
    _commit(repo, "2026-09-23T13:30:00+08:00", ("standards/otdp/0.2.1/x.json", "{}\n"))
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp 0.2.0 -> 0.2.1"):
        check_train_windows(repo, FLOOR_SECONDS)
