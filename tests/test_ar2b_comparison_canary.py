"""AR-2b plant: the #457 comparison canary (deliberate, never merged).

A deliberately UNLISTED failing test, Windows-gated and wincore-marked so
it runs in the per-PR windows evidence lane ONLY: the pytest step stays
forgiven (its continue-on-error) while the expected-failures comparison
step must RED the job naming this id — the wire-level proof that the lane
sees new Windows breakage (#457's hole). The win-core manifest counts are
refreshed in the same commit so ``gates`` stays green; this file and that
refresh revert together before the final head. Lineage: the AR-2 plant of
PR #341 proved the evidence surfaces; this one proves the strict half.
"""

from __future__ import annotations

import sys

import pytest


@pytest.mark.wincore
@pytest.mark.skipif(sys.platform != "win32", reason="AR-2b plant: Windows lane only")
def test_ar2b_comparison_canary_deliberate_windows_red() -> None:
    assert False, "AR-2b plant: deliberate unlisted Windows red (issue 457)"
