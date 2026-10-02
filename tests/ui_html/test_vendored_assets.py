"""The vendored-asset inventory (G1e, UR-10): the last React build's three
stylesheets, moved verbatim into the package and byte-pinned.

- the live tree verifies (every asset's sha256 recomputed against
  ``assets/inventory.json`` — the preview-assets inventory shape);
- a corrupted COPY reds with the refusal name (the RED control: the
  mechanism must detect, not assume);
- the census is exhaustive — an un-inventoried file in the directory
  refuses, and an absent asset refuses.

The three sha256 literals below pin the bytes as the LAST REACT BUILD's
bytes (the parent-commit ``ui/src/styles/`` shas, recorded at landing):
an asset edit that re-pins the inventory to match still reds here — the
freeze is editorial, a visible diff in this file, never a quiet re-pin.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from benchweave_ui_html import assets

#: The parent-commit ``ui/src/styles/`` sha256s (the last React build's
#: bytes; recorded in the G1e landing commit message and matched by the
#: SDK standalone host's own vendored copies).
LAST_REACT_BUILD_SHA256: dict[str, str] = {
    "tokens.css": "76353723fd3e12653c154c6bf3d0cfd967545dbcd1ede49ab89b90f30747468a",
    "themes.css": "197eda5ad9d8bcf8c827599589afaa229928096508608862da249628623a317f",
    "globals.css": "3666401981bf801c14eefa89313841a617fd09941f43d1a005d885ae49a319e6",
}


def _copy_tree(tmp_path: Path, name: str = "assets") -> Path:
    root = tmp_path / name
    shutil.copytree(assets.ASSETS_DIR, root)
    return root


def test_the_live_tree_verifies() -> None:
    assert assets.verify_vendored_assets() == []


def test_the_vendored_bytes_are_the_last_react_builds_bytes() -> None:
    """sha256 literals vs the shipped bytes — moved, never edited. A match
    between the assets and a re-pinned inventory still reds here unless
    this file's literals move too (the visible-editorial-diff freeze)."""
    for name, expected in LAST_REACT_BUILD_SHA256.items():
        data = (assets.ASSETS_DIR / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected, name


def test_a_corrupted_copy_reds_with_the_refusal_name(tmp_path: Path) -> None:
    """The RED control: a corrupted COPY (one byte changed in themes.css)
    must refuse by name — a verifier that cannot detect is decorative."""
    root = _copy_tree(tmp_path)
    target = root / "themes.css"
    doctored = bytearray(target.read_bytes())
    doctored[0] = doctored[0] ^ 0x20
    target.write_bytes(bytes(doctored))
    refusals = assets.verify_vendored_assets(root)
    assert refusals == ["vendored_asset_mismatch:themes.css (sha256)"], refusals


def test_an_absent_asset_reds_by_name(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    (root / "globals.css").unlink()
    refusals = assets.verify_vendored_assets(root)
    assert refusals == ["vendored_asset_absent:globals.css"], refusals


def test_the_inventory_is_an_exhaustive_census(tmp_path: Path) -> None:
    """Missing entry and extra file both refuse — the inventory names
    everything in the directory or it is wrong (a sample is not a census).
    Limit, named: a coherent SHRINK (row and file deleted together)
    verifies — internal consistency is all this function can see; the
    canonical three-file set is pinned by the sha-literals arm above."""
    # Extra file, no inventory row.
    root = _copy_tree(tmp_path)
    (root / "smuggled.css").write_text("/* not inventoried */\n", encoding="utf-8")
    assert assets.verify_vendored_assets(root) == ["vendored_asset_unlisted:smuggled.css"]

    # Missing entry, file still present: the file is unlisted.
    root = _copy_tree(tmp_path, "assets-row-deleted")
    inventory = json.loads((root / assets.INVENTORY_NAME).read_text(encoding="utf-8"))
    inventory["assets"] = [row for row in inventory["assets"] if row["path"] != "tokens.css"]
    (root / assets.INVENTORY_NAME).write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )
    assert assets.verify_vendored_assets(root) == ["vendored_asset_unlisted:tokens.css"]


def test_a_missing_inventory_reds_fail_closed(tmp_path: Path) -> None:
    root = _copy_tree(tmp_path)
    (root / assets.INVENTORY_NAME).unlink()
    assert assets.verify_vendored_assets(root) == [
        f"vendored_inventory_absent:{assets.INVENTORY_NAME}"
    ]
