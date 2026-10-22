"""Sync-completion pacing (#451, GOVERNANCE G-5): the release train's rule.

Arms: the pure sync-completion judgement (the missing-predecessor refusal,
per-standard scope), and a scratch-repository family that drives the REAL
collector and lock reader end-to-end with controlled SDK locks — non-empty
collection, the missing-predecessor refusal, the compliant-bump pass (wall
time no longer matters), the admission and reset-class exemptions, the
pre-anchor grandfather, the same-commit stacking refusal, the unreadable
lock and uninitialized submodule refusals, and the real-tree grandfather
row. The scratch family is what makes a passing real-tree row non-vacuous:
the real tree correctly collects zero post-anchor bumps, and only the
scratch arms prove the collector can collect at all.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from benchweave.standards.train_window import (
    BumpEntry,
    TrainWindowError,
    check_train_windows,
    collect_bump_entries,
)

ROOT = Path(__file__).resolve().parents[2]
# The module's G-5 marker literal, pinned here as the contract the scratch
# fixtures stand in for: the anchor is the FIRST commit whose module path
# contains this literal (the amendment's own arrival, oldest match). If the
# module's ANCHOR_MARKER moves without this line, every scratch anchor fails
# to resolve and the suite refuses loudly instead of silently re-anchoring.
ANCHOR_MARKER = "train_window:g5-sync-completion-anchor"
T0 = "2026-09-20T12:00:00+08:00"


def _run(repo: Path, *arguments: str, date: str | None = None) -> str:
    """One git invocation, user identity on every commit-capable call."""
    environment = dict(os.environ)
    if date is not None:
        environment["GIT_AUTHOR_DATE"] = date
        environment["GIT_COMMITTER_DATE"] = date
    completed = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return completed.stdout


def _commit(
    repo: Path,
    date: str,
    *paths_contents: tuple[str, str],
    sdk_pin: str | None = None,
) -> str:
    """Commit the named paths only — never `add -A`: the SDK clone under
    `packages/sdk` is a nested repository whose gitlink is pinned
    deliberately (`sdk_pin`), never by an accidental staging sweep."""
    for relative, content in paths_contents:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        _run(repo, "add", relative)
    if sdk_pin is not None:
        _run(repo, "update-index", "--add", "--cacheinfo", f"160000,{sdk_pin},packages/sdk")
    _run(repo, "commit", "-m", "w", date=date)
    return _run(repo, "rev-parse", "HEAD").strip()


def _scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "scratch"
    repo.mkdir()
    _run(repo, "init", "-q")
    return repo


def _anchor(repo: Path, date: str = T0) -> None:
    """The stand-in carries the G-5 marker: the anchor is the first commit
    whose module path contains it, exactly as in the real tree."""
    _commit(
        repo,
        date,
        ("src/benchweave/standards/train_window.py", f"# {ANCHOR_MARKER}\n"),
    )


def _sdk_repo(
    tmp_path: Path,
    date: str,
    *carried: dict[str, list[str]],
    yanked: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[Path, list[str]]:
    """A mini SDK repository whose i-th commit's standards-lock.json carries
    ``carried[i]`` (standard -> versions). Returns (path, commit shas)."""
    sdk = tmp_path / "sdk-src"
    sdk.mkdir(exist_ok=True)
    _run(sdk, "init", "-q")
    shas: list[str] = []
    for mapping in carried:
        rows = [
            {
                "id": standard,
                "version": version,
                "yanked": (standard, version) in yanked,
            }
            for standard, versions in sorted(mapping.items())
            for version in versions
        ]
        sha = _commit(
            sdk,
            date,
            ("standards-lock.json", json.dumps({"standards": rows})),
        )
        shas.append(sha)
    return sdk, shas


def _attach_sdk(repo: Path, sdk: Path) -> None:
    """Clone the mini SDK into the parent at ``packages/sdk`` — the object
    store ``git -C packages/sdk show`` reads. The gitlink itself is pinned
    per commit by ``_commit(sdk_pin=...)``."""
    (repo / "packages").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "-q", "--no-local", str(sdk), str(repo / "packages/sdk")],
        check=True,
        capture_output=True,
    )


def test_judgement_refuses_a_lock_lacking_the_predecessor() -> None:
    from benchweave.standards.train_window import sync_completion_violations

    entries = (BumpEntry("otdp", "0.2.1", "c" * 40, "0.2.0"),)
    messages = sync_completion_violations(entries, lambda _commit_sha: frozenset())
    assert len(messages) == 1
    assert messages[0].startswith("train_window_violation: otdp 0.2.0 -> 0.2.1")
    assert "SDK lock" in messages[0]


def test_judgement_passes_when_the_lock_carries_the_predecessor() -> None:
    from benchweave.standards.train_window import sync_completion_violations

    entries = (BumpEntry("otdp", "0.2.1", "c" * 40, "0.2.0"),)
    carried = frozenset({("otdp", "0.2.0")})
    assert sync_completion_violations(entries, lambda _commit_sha: carried) == ()


def test_per_standard_scope_is_independent() -> None:
    from benchweave.standards.train_window import sync_completion_violations

    entries = (
        BumpEntry("otdp", "0.2.1", "a" * 40, "0.2.0"),
        BumpEntry("registry", "0.1.3", "b" * 40, "0.1.2"),
    )
    # registry's predecessor is carried, otdp's is not: one line, otdp only.
    carried = frozenset({("registry", "0.1.2")})
    messages = sync_completion_violations(entries, lambda _commit_sha: carried)
    assert len(messages) == 1
    assert messages[0].startswith("train_window_violation: otdp")
    assert "registry" not in messages[0]


def test_the_anchor_marker_literal_is_pinned_to_the_module_contract() -> None:
    from benchweave.standards.train_window import ANCHOR_MARKER as module_marker

    # The module's constant and the literal the fixtures stand in with are
    # one contract; either moving alone breaks every scratch anchor loudly.
    assert module_marker == ANCHOR_MARKER
    assert ANCHOR_MARKER == "train_window:g5-sync-completion-anchor"


def test_a_judged_bump_whose_lock_lacks_the_predecessor_refuses(tmp_path: Path) -> None:
    # The rule's core arm: the SDK lock pinned at the bump commit carries no
    # row for the previous released version — the bump must be refused, by a
    # typed message in the train_window_ family.
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(tmp_path, T0, {"otdp": []})
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))  # admission
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",  # the judged bump
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
        sdk_pin=shas[0],
    )
    entries = collect_bump_entries(repo)
    # Non-vacuity: the collector reads file paths and derives version dirs.
    assert [entry.version for entry in entries] == ["0.2.0"]
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp 0.1.0 -> 0.2.0"):
        check_train_windows(repo)


def test_compliant_bumps_pass_regardless_of_wall_time(tmp_path: Path) -> None:
    # G-5's affirmative half: pacing is the SDK leg, not the clock. Two
    # bumps an hour apart both pass when each commit's lock already carries
    # its predecessor — the #97 24-hour floor is what this rule retires.
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(
        tmp_path, T0, {"otdp": ["0.1.0"]}, {"otdp": ["0.1.0", "0.2.0"]}
    )
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))  # admission
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-20T13:00:00+08:00",  # 1h after admission
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
        sdk_pin=shas[0],
    )
    check_train_windows(repo)  # lock carries 0.1.0: clean
    _commit(
        repo,
        "2026-09-20T14:00:00+08:00",  # 1h after 0.2.0 — inside the retired floor
        ("standards/otdp/0.2.1/x.schema.json", "{}\n"),
        sdk_pin=shas[1],
    )
    assert check_train_windows(repo) == ()  # lock carries 0.2.0: clean


def test_a_yanked_predecessor_row_still_counts_as_carried(tmp_path: Path) -> None:
    # A yanked row is post-sync state: the release ledger the rule prices
    # was already paid, so the pin to the yanked predecessor still passes.
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(
        tmp_path, T0, {"otdp": ["0.1.0"]}, yanked=frozenset({("otdp", "0.1.0")})
    )
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
        sdk_pin=shas[0],
    )
    assert check_train_windows(repo) == ()


def test_admission_needs_no_lock_carriage(tmp_path: Path) -> None:
    # A standard's first version has no predecessor to require — the
    # exemption holds with no SDK checkout attached at all.
    repo = _scratch_repo(tmp_path)
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    assert collect_bump_entries(repo) == ()
    assert check_train_windows(repo) == ()


def test_reset_class_commit_is_exempt_and_opens_a_fresh_wing(tmp_path: Path) -> None:
    # One commit adding dirs for three or more standards reads as a reset:
    # exempt from carriage (the lock never carries what lands together), and
    # each standard's next non-exempt bump is judged afresh.
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(tmp_path, T0, {"otdp": []})
    _anchor(repo)
    _commit(
        repo,
        T0,
        ("standards/otdp/0.1.0/x.schema.json", "{}\n"),
        ("standards/registry/0.1.0/x.schema.json", "{}\n"),
        ("standards/interface/0.1.0/x.schema.json", "{}\n"),
    )  # admissions
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",  # reset-class: three standards, one commit
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
        ("standards/registry/0.1.1/x.schema.json", "{}\n"),
        ("standards/interface/0.1.1/x.schema.json", "{}\n"),
        sdk_pin=shas[0],
    )
    assert collect_bump_entries(repo) == ()  # exempt: no entries
    assert check_train_windows(repo) == ()
    # The fresh wing: otdp's next non-exempt bump IS judged, against a lock
    # that carries nothing — it refuses, proving the reset did not swallow
    # the rule for good.
    _commit(
        repo,
        "2026-09-21T13:00:00+08:00",
        ("standards/otdp/0.2.1/x.schema.json", "{}\n"),
        sdk_pin=shas[0],
    )
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp 0.2.0 -> 0.2.1"):
        check_train_windows(repo)


def test_pre_anchor_bumps_are_grandfathered_and_post_anchor_judged(
    tmp_path: Path,
) -> None:
    # The anchor's falsifier: the same non-compliant bump passes BEFORE the
    # amendment's marker lands and refuses after — judgement moves forward
    # at the anchor rather than retroactively over grandfathered history.
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(tmp_path, T0, {"otdp": []})
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))  # admission
    _commit(
        repo,
        "2026-09-20T13:00:00+08:00",  # non-compliant bump, PRE-anchor
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
    )
    _anchor(repo, "2026-09-20T18:00:00+08:00")  # the amendment arrives later
    _attach_sdk(repo, sdk)
    assert collect_bump_entries(repo) == ()  # grandfathered by mechanism
    assert check_train_windows(repo) == ()
    # Post-anchor: 0.2.1's predecessor 0.2.0 is not in the lock → refused.
    _commit(
        repo,
        "2026-09-20T19:00:00+08:00",
        ("standards/otdp/0.2.1/x.schema.json", "{}\n"),
        sdk_pin=shas[0],
    )
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp 0.2.0 -> 0.2.1"):
        check_train_windows(repo)


def test_straddled_version_dir_counts_once(tmp_path: Path) -> None:
    # The real corpus straddled a version directory across two commits 26
    # seconds apart; it is one bump at its earliest commit, not a
    # double-judged pair.
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(tmp_path, T0, {"otdp": ["0.1.0"]})
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",
        ("standards/otdp/0.2.0/a.json", "{}\n"),
        sdk_pin=shas[0],
    )
    _commit(
        repo,
        "2026-09-21T12:00:26+08:00",
        ("standards/otdp/0.2.0/b.json", "{}\n"),
        sdk_pin=shas[0],
    )
    entries = collect_bump_entries(repo)
    assert [entry.version for entry in entries] == ["0.2.0"]
    assert check_train_windows(repo) == ()  # one entry, predecessor carried


def test_same_commit_double_version_refuses_the_stack(tmp_path: Path) -> None:
    # Two version dirs of one standard in a single commit: the higher one's
    # predecessor is the lower one, which no lock at that commit can carry —
    # the stacking refusal, not a collapse onto one entry.
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(tmp_path, T0, {"otdp": ["0.1.0"]})
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",
        ("standards/otdp/0.2.0/a.json", "{}\n"),
        ("standards/otdp/0.3.0/a.json", "{}\n"),
        sdk_pin=shas[0],
    )
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp 0.2.0 -> 0.3.0"):
        check_train_windows(repo)


def test_delete_and_readd_does_not_reanchor(tmp_path: Path) -> None:
    # A landed refusal must survive the module being dropped and re-added
    # (revert + re-land is ordinary GitHub flow); the anchor is the FIRST
    # marker arrival, not the newest one.
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(tmp_path, T0, {"otdp": []})
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",
        ("standards/otdp/0.2.0/x.json", "{}\n"),
        sdk_pin=shas[0],
    )
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp 0.1.0 -> 0.2.0"):
        check_train_windows(repo)
    module = repo / "src/benchweave/standards/train_window.py"
    _run(
        repo,
        "rm", "-q", str(module.relative_to(repo)),
        date="2026-09-21T13:00:00+08:00",
    )
    _run(
        repo, "commit", "-m", "rm",
        date="2026-09-21T13:00:00+08:00",
    )
    _anchor(repo, "2026-09-21T14:00:00+08:00")  # re-landed
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp 0.1.0 -> 0.2.0"):
        check_train_windows(repo)  # still refused: the anchor did not move


def test_an_unreadable_pinned_lock_refuses_to_judge(tmp_path: Path) -> None:
    # The orphaned-pin class: a gitlink whose object the clone does not
    # hold. The carriage state cannot be read, so the verdict must refuse —
    # never a laundered pass out of a missing object.
    repo = _scratch_repo(tmp_path)
    sdk, _shas = _sdk_repo(tmp_path, T0, {"otdp": ["0.1.0"]})
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
        sdk_pin="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",  # absent object
    )
    with pytest.raises(TrainWindowError, match="train_window_history_unreadable"):
        check_train_windows(repo)


def test_an_uninitialized_sdk_checkout_refuses_by_name(tmp_path: Path) -> None:
    # A pinned gitlink with no initialized submodule: refused by name with
    # the remediation, and carrying no SHAs — a superproject HEAD must never
    # be misattributed as submodule state (the check.py posture).
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(tmp_path, T0, {"otdp": ["0.1.0"]})
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",
        ("standards/otdp/0.2.0/x.schema.json", "{}\n"),
        sdk_pin=shas[0],
    )
    (repo / "packages" / "sdk").mkdir(parents=True)  # plain-clone-before-init
    with pytest.raises(TrainWindowError) as excinfo:
        check_train_windows(repo)
    message = str(excinfo.value)
    assert message.startswith("train_window_history_unreadable")
    assert "not initialized" in message
    assert "git submodule update --init packages/sdk" in message
    assert not re.search(r"[0-9a-f]{40}", message), message


def test_shallow_clone_refuses_to_judge(tmp_path: Path) -> None:
    # A depth-1 graft lists every standards file as Added at one timestamp;
    # the collector detects it and refuses rather than judge from nothing.
    repo = _scratch_repo(tmp_path)
    sdk, shas = _sdk_repo(tmp_path, T0, {"otdp": []})
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",
        ("standards/otdp/0.2.0/x.json", "{}\n"),
        sdk_pin=shas[0],
    )
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "--no-local", str(repo), str(shallow)],
        check=True,
        capture_output=True,
    )
    with pytest.raises(TrainWindowError, match="train_window_history_unreadable"):
        collect_bump_entries(shallow)


def test_dev_directory_addition_is_invisible_to_the_window(tmp_path: Path) -> None:
    # The -dev stage's arm: a dev-head directory is staging, not a version —
    # it must not collect as a bump (authoring is not releasing), while the
    # identical landing as a real version directory is judged.
    repo = _scratch_repo(tmp_path)
    # One SDK state serves both pins: its lock carries 0.1.0 but not 0.2.0,
    # which is what the compliant bump needs and what the control refuses on.
    sdk, shas = _sdk_repo(tmp_path, T0, {"otdp": ["0.1.0"]})
    _anchor(repo)
    _commit(repo, T0, ("standards/otdp/0.1.0/x.schema.json", "{}\n"))
    _attach_sdk(repo, sdk)
    _commit(
        repo,
        "2026-09-21T12:00:00+08:00",
        ("standards/otdp/0.2.0/x.json", "{}\n"),
        sdk_pin=shas[0],
    )
    _commit(
        repo,
        "2026-09-21T13:00:00+08:00",  # inside any wall-clock floor
        ("standards/otdp/0.2.1-dev/x.json", "{}\n"),
        sdk_pin=shas[0],
    )
    entries = collect_bump_entries(repo)
    assert [entry.version for entry in entries] == ["0.2.0"], (
        "a dev-directory addition must not collect as a bump"
    )
    assert check_train_windows(repo) == ()  # the head is invisible
    # The control half: the same landing as a real version directory fires
    # (its predecessor 0.2.0 is absent from the lock pinned there).
    _commit(
        repo,
        "2026-09-21T14:00:00+08:00",
        ("standards/otdp/0.2.1/x.json", "{}\n"),
        sdk_pin=shas[0],
    )
    with pytest.raises(TrainWindowError, match="train_window_violation: otdp 0.2.0 -> 0.2.1"):
        check_train_windows(repo)


def test_real_tree_post_anchor_sequence_is_clean() -> None:
    # The real tree's post-anchor deployment state, pinned: the anchor is
    # this amendment's own arrival (#451, first marker commit fe9dc169,
    # committer ts 1791819485). otdp 0.2.3's earliest landing (1f27c92d,
    # ts 1791810199) predates the anchor and is grandfathered by mechanism;
    # registry 0.1.3's bump (9135626, ts 1791873156) is the tree's first
    # judged post-anchor bump and is compliant — the standards-lock.json
    # pinned at that commit's gitlink (b17f0214) carries registry 0.1.2.
    # The L5 bump (2026-10-16, gateway issue #463) adds two more judged
    # post-anchor entries, both compliant (each carries its from-
    # predecessor note: plugin-ui 0.3.1->0.4.0 via MIGRATION.md, the
    # classref family 0.1.0->0.2.0 via the 0.2.0 README).
    # The interface 0.1.1 bump (2026-10-17, gateway issue #450) joins the
    # judged set compliant: the SDK lock at its gitlink (fca9c415, v0.15.0)
    # carries interface 0.1.0 — the predecessor's SDK leg was complete, so
    # the G-5 sync-completion pacing holds. The L11 bump
    # (2026-10-18, slot L11) adds the family's 0.2.0->0.3.0 entry the
    # same way (the 0.3.0 README's from-predecessor note). The
    # composed-action-class bump (2026-10-22, gateway issue #541) adds the
    # family's 0.3.0->0.4.0 entry the same way (the 0.4.0 README's
    # from-predecessor note).
    # The scratch family above carries the non-vacuity burden; this row
    # pins the deployment state — the judged set's shape, and a
    # non-compliant future bump still refuses by name below.
    entries = collect_bump_entries(ROOT)
    assert [(entry.standard, entry.version, entry.predecessor) for entry in entries] == [
        ("interface", "0.1.1", "0.1.0"),
        ("plugin-ui", "0.4.0", "0.3.1"),
        ("registry", "0.1.3", "0.1.2"),
        ("plugin-ui-class-reference", "0.2.0", "0.1.0"),
        ("plugin-ui-class-reference", "0.3.0", "0.2.0"),
        ("plugin-ui-class-reference", "0.4.0", "0.3.0"),
    ]
    assert check_train_windows(ROOT) == ()
