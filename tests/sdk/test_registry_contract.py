"""The vendored registry contract admits the ``skill`` payload-file role.

First SDK test module to consume the registry standard. The schema key and
the document's ``manifest_version`` both resolve from the COMMITTED lock
(the ``tests/test_version_constants.py`` pattern, SDK side), so the RED
state fails on the role enum against whatever version the lock pins — never
on a stale hard-coded key (issue #71 design record section 5.1, risk R5).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# The SDK lives in the submodule; expose it to this workspace test module
# (same bootstrap as tests/sdk/test_sdk.py) before importing from it.
SDK_SRC = Path(__file__).resolve().parents[2] / "packages/sdk/src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from benchweave_sdk.validation import validate  # noqa: E402

SDK_ROOT = Path(__file__).resolve().parents[2] / "packages/sdk"
LOCK = json.loads((SDK_ROOT / "standards-lock.json").read_text(encoding="utf-8"))

#: The skill payload entry under test: an agent-facing skill document in the
#: cross-harness SKILL.md convention (design section 1.2; invented fixture
#: path — no real plugin project is named).
SKILL_ENTRY: dict[str, Any] = {
    "path": "skills/drive-device/SKILL.md",
    "role": "skill",
    "bytes": 1,
    "sha256": "c" * 64,
}


def _registry_standard() -> dict[str, Any]:
    return next(s for s in LOCK["standards"] if s["id"] == "registry")


def _manifest_schema_key() -> str:
    registry_files = _registry_standard()["files"]
    entry = next(f for f in registry_files if f["path"].endswith("release-manifest.schema.json"))
    return str(entry["path"])


def _manifest(role: str) -> dict[str, Any]:
    """The tests/contract/test_registry_schemas.py manifest shape, lock-versioned.

    ``manifest_version`` follows the lock's registry version (never a
    literal), so the document is always valid-for-version and only the role
    enum can reject it. Kind stays ``profile`` deliberately: the skill role
    is kind-agnostic by design (explicit non-change; risk R6), and a profile
    manifest carrying it pins that reading.
    """
    return {
        "manifest_version": _registry_standard()["version"],
        "registry_id": "origin-main",
        "package_id": "benchweave/dc-psu-profile",
        "version": "1.0.0",
        "kind": "profile",
        "display_name": "DC PSU profile",
        "summary": "dc_psu class and action definitions",
        "released_at": "2026-09-11T00:00:00Z",
        "tags": ["dc", "psu"],
        "publisher_id": "benchweave-fixtures",
        "maintainers": [{"name": "BenchWeave", "contact": "https://example.invalid/support"}],
        "support_url": "https://example.invalid/support",
        "issues_url": "https://example.invalid/issues",
        "licence": {"spdx_expression": "MIT", "file": "LICENSE"},
        "source": {"url": "https://example.invalid/src", "revision": "0" * 40},
        "compatibility": {
            "otdp_versions": ["0.1.0"],
            "adapter_api_versions": [],
            "stg_versions": ["1.5"],
            "runtimes": [],
            "host_provider_ids": [],
        },
        "device_targets": [],
        "provides": {"profile_ids": ["otdp:dc_psu:1.0.0"], "descriptor_ids": []},
        "dependencies": [],
        "permissions": [],
        "payload": {
            "sha256": "a" * 64,
            "bytes": 1,
            "media_type": "application/zip",
            "files": [
                {"path": "LICENSE", "role": "licence", "bytes": 1, "sha256": "b" * 64},
                {**SKILL_ENTRY, "role": role},
            ],
        },
        "evidence": [
            {
                "level": "structural",
                "report_path": "evidence/structural.md",
                "tested_at": "2026-09-11T00:00:00Z",
                "target": "synthetic",
                "result": "passed",
                "limitations": [],
            }
        ],
        "changelog_path": "CHANGELOG.md",
        "migration_notes_path": "MIGRATION.md",
        "limitations": [],
    }


def test_registry_manifest_skill_role_validates() -> None:
    validate(_manifest("skill"), _manifest_schema_key())


def test_registry_manifest_unknown_role_refused() -> None:
    """The control: the enum stays closed — an unmodelled role is refused."""
    with pytest.raises(ValueError) as exc:
        validate(_manifest("workbench_guide"), _manifest_schema_key())
    message = str(exc.value)
    assert "Contract validation failed:" in message
    assert "is not one of" in message
    assert "workbench_guide" in message


def test_registry_standard_version_is_0_1_1() -> None:
    """Sweep sentinel: the committed lock pins registry 0.1.1 post-sync."""
    assert _registry_standard()["version"] == "0.1.1"
