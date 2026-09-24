"""Website version-stamp contract (issue #188, design 2026-09-24, CON-13).

`website/index.html` is the one public surface that states corpus and SDK
versions in prose. The stamp contract (design §2, invariants CON-13): the
source carries `{{stg-<key>}}` tokens and never a version literal — every
version claim renders from the standards manifest at assembly time, so a
bump moves no website byte and a stale claim is structurally impossible.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "website" / "index.html"
SEMVER_RE = re.compile(r"\d+\.\d+\.\d+")


def _hand_stamped_versions(text: str) -> list[str]:
    """Every three-component version literal as `<line>:<literal>` (1-based)."""
    return [
        f"{number}:{match}"
        for number, line in enumerate(text.splitlines(), start=1)
        for match in SEMVER_RE.findall(line)
    ]


def test_source_carries_no_version_literals() -> None:
    """T2, the issue #188 RED vehicle: version claims are stamp tokens.

    A three-component literal in the source is a hand-stamped claim that no
    bump train moves and no gate sees (the design's root cause: the site's
    link checker resolves against copy-never-move history, so a stale-version
    href passes). The full test set lands with the implementation commit.
    """
    hits = _hand_stamped_versions(SOURCE.read_text(encoding="utf-8"))
    assert not hits, (
        "hand-stamped version literal(s) in website/index.html — version claims "
        "are {{stg-*}} tokens derived at assembly (CON-13): " + ", ".join(hits)
    )
