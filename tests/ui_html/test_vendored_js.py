"""The vendored JS pair + the generic host script (G2a, design §2.6).

``htmx.min.js`` and ``sse.js`` are byte-identical copies of the standalone
host's vetted pair (the I1 landing's bytes — same library version, recorded
at copy time below). ``bw-host.js`` is first-authored here (generic host
script: htmx bootstrap, ``data-*``-driven SSE connect, per-frame swap
coalescing, live-region announcements, theme handling) and is pinned by its
inventory row, not by an external authority.

RED control: every arm in this file failed before the assets landed (the
files were absent, the inventory named only the three stylesheets) — the
census arms, not a hope, are what prove the vendoring.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchweave_ui_html import assets

#: The standalone host's vetted pair (sha256 of the bytes at the I1
#: landing, recorded in its own inventory; matched byte-for-byte here).
STANDALONE_VETTED_SHA256: dict[str, str] = {
    "htmx.min.js": "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447",
    "sse.js": "8eed8df4df350126be9dc4fa2496e6eb9890e32f6202a29746e3c3c0e7004c13",
}

#: The complete vendored set after G2a: the three G1e stylesheets plus the
#: JS pair plus the host script. The inventory is a census — this set is
#: what "complete" means, and a missing row or file reds below.
EXPECTED_ASSET_NAMES: frozenset[str] = frozenset(
    {"tokens.css", "themes.css", "globals.css", "htmx.min.js", "sse.js", "bw-host.js"}
)


def test_js_pair_is_the_standalone_vetted_pair() -> None:
    """The two library bytes are MOVES, never edits: the sha256 literals
    above are the standalone host's own inventory values, so an asset edit
    that re-pins the inventory to match still reds here (the visible
    editorial-diff freeze, the LAST_REACT_BUILD_SHA256 arm's shape)."""
    for name, expected in STANDALONE_VETTED_SHA256.items():
        data = (assets.ASSETS_DIR / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, name


def test_bw_host_script_is_present_static_and_eval_free() -> None:
    """The host script exists, is non-trivial, and carries no ``eval`` —
    the CSP posture (``script-src 'self'`` with ``allowEval=false``) must
    survive the script's own body, not just the page templates."""
    source = (assets.ASSETS_DIR / "bw-host.js").read_text(encoding="utf-8")
    assert len(source) > 200, "bw-host.js is suspiciously small"
    assert "eval(" not in source
    # The generic-contract hooks the templates rely on (G2c consumes the
    # stream hooks; the announce hook is the live-region machinery).
    assert "data-bw-stream" in source
    assert "data-bw-announce" in source


def test_the_inventory_is_the_complete_six_asset_census() -> None:
    """The committed inventory names exactly the expected set, every row
    matches the bytes on disk (regenerated, not trusted), and the directory
    holds nothing outside the inventory."""
    inventory = json.loads(
        (assets.ASSETS_DIR / assets.INVENTORY_NAME).read_text(encoding="utf-8")
    )
    rows = {row["path"]: row for row in inventory["assets"]}
    assert set(rows) == EXPECTED_ASSET_NAMES
    for name, row in rows.items():
        data = (assets.ASSETS_DIR / name).read_bytes()
        assert row["size"] == len(data), name
        assert row["sha256"] == hashlib.sha256(data).hexdigest(), name
    on_disk = {
        entry.name
        for entry in assets.ASSETS_DIR.iterdir()
        if entry.name != assets.INVENTORY_NAME
    }
    assert on_disk == EXPECTED_ASSET_NAMES
    # The exhaustive verifier agrees with the census (the package-side
    # arm; the host-side wiring refusal is pinned in tests/interfaces_ui/).
    assert assets.verify_vendored_assets() == []


def test_no_nested_directories_under_assets() -> None:
    """The assets tree stays flat: the G1e census precedent (a nested tree
    is smuggling surface the byte-pin never covered)."""
    for entry in assets.ASSETS_DIR.iterdir():
        assert entry.is_file(), f"unexpected directory: {entry}"
        assert Path(entry).name == entry.name
