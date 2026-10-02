"""The vendored style assets and their inventory (G1e, UR-10).

The three stylesheets the contract's §A token rows assert against —
``tokens.css``, ``themes.css``, ``globals.css`` — are the LAST React
build's bytes, moved verbatim from ``ui/src/styles/`` into the wheel's
packaged tree at the React cutover and byte-pinned by
``assets/inventory.json`` (the preview-assets/corpus-manifest shape:
``api_version`` plus per-asset ``path``/``sha256``/``size``).

``verify_vendored_assets`` is the package-side integrity check. The HOST
CALL — a host verifies the inventory before serving the assets — lands
with the hosts (G2's gateway host; PRD 11's standalone), the same
enforcement-by-host shape as obligation 25: the function and its tests
ship now, the wiring rides the host designs that inherit it.

The census is exhaustive, not a sample: every entry in the assets
directory — files AND directories — must be inventoried and every
inventoried path must exist, so a hand-edited asset, a dropped asset, a
smuggled extra file, or a nested un-pinned tree all refuse by name.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

#: The package's vendored-asset directory (inside the packaged tree, so
#: the wheel ships the assets as package data — no dependency motion).
ASSETS_DIR: Final[Path] = Path(__file__).resolve().parent / "assets"

#: The byte-pin inventory (see module docstring for the shape).
INVENTORY_NAME: Final[str] = "inventory.json"


def _refusals_for(assets_dir: Path) -> list[str]:
    inventory_path = assets_dir / INVENTORY_NAME
    if not inventory_path.is_file():
        return [f"vendored_inventory_absent:{INVENTORY_NAME}"]
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"vendored_inventory_unreadable:{INVENTORY_NAME} ({exc})"]
    if not isinstance(inventory, dict) or not isinstance(inventory.get("assets"), list):
        return [f"vendored_inventory_malformed:{INVENTORY_NAME} (assets list missing)"]
    if inventory.get("api_version") != 1:
        # B-F3 fold: an api_version this verifier does not implement is not
        # a shape it can verify — refuse rather than best-effort-parse rows
        # it may be misreading.
        return [f"vendored_inventory_api_version:{inventory.get('api_version')!s}"]

    listed: set[str] = set()
    refusals: list[str] = []
    for entry in inventory["assets"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            refusals.append(f"vendored_inventory_malformed:{INVENTORY_NAME} (bad row)")
            continue
        rel = entry["path"]
        # Defensive: inventory paths are plain names beside the inventory —
        # a traversal or nested path would read outside the asset set. This
        # guard does NOT catch a wrong-but-plain path pointing at a file the
        # packager never shipped; the census arm below does.
        if rel != Path(rel).name:
            refusals.append(f"vendored_asset_path_unsafe:{rel}")
            continue
        listed.add(rel)
        asset = assets_dir / rel
        expected_sha = entry.get("sha256")
        expected_size = entry.get("size")
        if not asset.is_file():
            refusals.append(f"vendored_asset_absent:{rel}")
            continue
        data = asset.read_bytes()
        if expected_size is not None and len(data) != expected_size:
            refusals.append(f"vendored_asset_mismatch:{rel} (size)")
            continue
        actual_sha = hashlib.sha256(data).hexdigest()
        if expected_sha != actual_sha:
            refusals.append(f"vendored_asset_mismatch:{rel} (sha256)")

    # The exhaustive-census arm: an un-inventoried entry in the directory is
    # a disagreement — the inventory names everything or it is wrong. ANY
    # entry refuses (B-F4 fold: directories included — a nested tree is
    # smuggling surface the byte-pin never covered, not packaging noise).
    for extra in sorted(p.name for p in assets_dir.iterdir() if p.name != INVENTORY_NAME):
        if extra not in listed:
            refusals.append(f"vendored_asset_unlisted:{extra}")
    return refusals


def verify_vendored_assets(assets_dir: Path | None = None) -> list[str]:
    """Verify the vendored assets against the inventory; ``[]`` = verified.

    Returns one refusal string per defect, by name
    (``vendored_asset_mismatch:<path>``, ``vendored_asset_absent:<path>``,
    ``vendored_asset_unlisted:<path>`` and the inventory-level
    ``vendored_inventory_*`` names above) — a host serves the assets only
    when this returns empty. Reading the bytes from disk (never trusting a
    cached digest) is the point: the check must notice what is actually
    shipped, not what was true at build time.
    """
    return _refusals_for(ASSETS_DIR if assets_dir is None else assets_dir)
