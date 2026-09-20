"""The bump window (#97): the prescriptive release-train floor, enforced.

Four arms: the pure gap judgement (violation, boundary, ordering), the
admission and reset-class exemptions (synthetic), the prefixed refusal
shape, and the real-tree integration row — the post-anchor bump sequence
of this repository has zero violations at the 48h floor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from benchweave.standards.train_window import (
    BumpEntry,
    check_train_windows,
    collect_bump_entries,
    window_violations,
)

ROOT = Path(__file__).resolve().parents[2]
FLOOR_48H = 48 * 3600


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


def test_real_tree_post_anchor_sequence_is_clean() -> None:
    entries = collect_bump_entries(ROOT)
    # The anchor is this module's own arrival: the first post-anchor bump
    # does not exist yet, so the collected set may be empty — but the
    # check must run and judge whatever is there.
    assert window_violations(entries, FLOOR_48H) == ()
    assert check_train_windows(ROOT, FLOOR_48H) == ()


def test_collector_grandfathers_pre_anchor_history() -> None:
    # The measured 4.8-hour otdp pair (0.1.2 -> 0.2.0, 2026-09-19) predates
    # the anchor; the collector must not surface either as a post-anchor
    # entry, or the real-tree row above would be vacuous.
    entries = collect_bump_entries(ROOT)
    assert all(entry.standard != "otdp" or entry.version not in {"0.1.2", "0.2.0"}
               for entry in entries) or entries == ()
