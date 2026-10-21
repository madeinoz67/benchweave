"""The mockup banner stamps agree with the ui-html package version.

Every class mockup carries a banner line naming the token set it was drawn
against (``GATEWAY STYLE TOKENS · benchweave-ui-html X.Y.Z``). Those files
live under ``docs/internal/ui-styleguide-mockups/``, a tree the docs
version-literal ratchet deliberately excludes, so no existing lane reddens
when a package bump leaves a stale stamp behind. The stamp would then claim
a token set the mockup was not drawn against, and nothing would discover it.

This arm is the missing detector: it globs the mockup tree, extracts every
stamp, and requires each one to equal the installed distribution's version.
It reds at the bump commit itself, inside the ordinary FAST lane, before a
release cut can carry a stale claim to a published page.

What this arm does NOT catch, by design: a mockup whose banner markup omits
the stamp entirely (an agreement check is satisfied vacuously by omission),
and a stamp that names a *different* product. Presence and shape checking on
the banner markup is added only once that markup is stable.
"""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

MOCKUP_DIR = Path(__file__).resolve().parents[2] / "docs" / "internal" / "ui-styleguide-mockups"

#: The banner idiom every class mockup carries, in each of its theme blocks.
STAMP_RE = re.compile(r"benchweave-ui-html\s+(\d+\.\d+\.\d+)")


def test_every_mockup_banner_stamp_matches_the_package_version() -> None:
    mockups = sorted(MOCKUP_DIR.glob("*.html"))

    # A vacuous pass is the failure mode this guard exists to prevent: a moved
    # or renamed tree would otherwise silence every assertion below.
    assert mockups, f"no mockups found under {MOCKUP_DIR}"

    version = importlib.metadata.version("benchweave-ui-html")
    stamps: list[tuple[str, str]] = []
    for mockup in mockups:
        for found in STAMP_RE.findall(mockup.read_text(encoding="utf-8")):
            stamps.append((mockup.name, found))

    assert stamps, f"no benchweave-ui-html stamps found across {len(mockups)} mockups"

    stale = sorted({f"{name}: {found}" for name, found in stamps if found != version})
    assert not stale, (
        "mockup banner stamps disagree with benchweave-ui-html "
        f"{version}; re-stamp the banner in each file: {stale}"
    )
