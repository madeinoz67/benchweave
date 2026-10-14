"""The registry 0.1.3 `configuration` role arms (issue #447, slice 3 rider).

The release-manifest inventory's ``role`` enum gains ``configuration`` —
an opaque, digest-pinned configuration asset (an FPGA image, a calibration
blob) that previously had no honest inventory role. The arms:

- **the role admits post-motion**: a manifest carrying a file row with
  ``role: "configuration"`` validates under the ACTIVE registry schema
  (RED pre-motion: refused ``schema_invalid`` — the enum is closed);
- **the closed-enum control**: a role outside the enum refuses both
  before and after the motion (the enum stays closed; one added value is
  additive, not an opening);
- **the additive control**: a manifest with NO configuration-role row
  validates unchanged (refused-none: nothing previously valid is
  refused, the PATCH class premise).

What this does NOT catch: registry admission semantics (signature,
lifecycle — untouched by an enum extension), the OTDP-side mirrors, and
the fixture lattice (whose manifests stay 0.1.1 and valid unchanged).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from benchweave.registry.schemas import RegistryRejected, load_manifest_document

REPO = Path(__file__).resolve().parents[2]
_MANIFEST = json.loads((REPO / "standards" / "standards-manifest.json").read_bytes())
ACTIVE_VERSION = next(
    entry["version"] for entry in _MANIFEST["standards"] if entry["id"] == "registry"
)
ACTIVE_DIR = REPO / "standards" / "registry" / ACTIVE_VERSION

#: A complete, schema-valid example — the base for every arm (the ACTIVE
#: copy; byte-identical to the 0.1.2 example it supersedes, per
#: copy-never-move).
_BASE: dict[str, Any] = json.loads(
    (ACTIVE_DIR / "examples" / "release-manifest.json").read_bytes()
)

_IMAGE_ROW: dict[str, Any] = {
    "path": "assets/reference-image.bin",
    "role": "configuration",
    "bytes": 2684,
    "sha256": hashlib.sha256(
        b"BW-SYNTHETIC-IMAGE-v1" + bytes(range(64)) * 4
    ).hexdigest(),
}


def _valid(raw: dict[str, Any]) -> bool:
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    try:
        load_manifest_document(
            encoded, hashlib.sha256(encoded).hexdigest(), max_bytes=1_000_000
        )
    except RegistryRejected:
        return False
    return True


def test_configuration_role_admits_under_active_schema() -> None:
    """The rider's acceptance arm: an inventory row with
    ``role: "configuration"`` validates (RED pre-motion, disclosed:
    ``schema_invalid`` — the closed enum had no such value)."""
    mutant = copy.deepcopy(_BASE)
    mutant["payload"]["files"].append(dict(_IMAGE_ROW))
    assert _valid(mutant)


def test_unknown_role_still_refuses() -> None:
    """The closed-enum control: a role outside the enum refuses both
    before and after the motion."""
    mutant = copy.deepcopy(_BASE)
    mutant["payload"]["files"].append({**_IMAGE_ROW, "role": "widget"})
    assert not _valid(mutant)


def test_manifest_without_the_role_validates_unchanged() -> None:
    """The additive control: no configuration row, no refusal — nothing
    previously valid is refused."""
    assert _valid(copy.deepcopy(_BASE))


def test_role_required_on_every_row() -> None:
    """A configuration-path row WITHOUT the role still refuses — the
    role is required on every inventory file; the motion adds a value,
    not an exemption."""
    mutant = copy.deepcopy(_BASE)
    mutant["payload"]["files"].append(
        {key: value for key, value in _IMAGE_ROW.items() if key != "role"}
    )
    assert not _valid(mutant)
