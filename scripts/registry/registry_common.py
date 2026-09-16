# scripts/registry/registry_common.py
"""Keyless registry-release builders shared by the fixture and dev publishers.

Every helper here is deterministic and cryptographic-free: canonical JSON,
SHA-256 digests, ZIP_STORED reproducible payloads, and the manifest/status
document builders with FIXED dates (no clock, no key, no network). The
signing half of the fixture publisher stays in ``build_fixtures`` (it is the
only consumer of the committed test keys), so the keyless dev loop
(``publish_dev``) can import this module alone and never transitively load
``cryptography``.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any, TypedDict

REPO = Path(__file__).resolve().parents[2]
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
RELEASED_AT = "2026-09-11T00:00:00Z"
STATUS_EXPIRES = "2027-09-11T00:00:00Z"

#: Payload member basename -> manifest ``payload.files[].role``. Every member
#: the builders can emit must be listed here; an unlisted file fails the build
#: loudly rather than shipping an unroleable payload entry.
ROLE_BY_SUFFIX: dict[str, str] = {
    "LICENSE": "licence",
    "CHANGELOG.md": "documentation",
    "MIGRATION.md": "documentation",
    "simulated.md": "documentation",
    "dc-psu.json": "profile",
    "sim-psu.json": "descriptor",
    "sim-controller.json": "descriptor",
    "plugin.py": "implementation",
    "__init__.py": "implementation",
    "sbom.json": "sbom",
    "build-provenance.json": "build_provenance",
    "dependency-lock.json": "dependency_lock",
}


class ReleaseEntry(TypedDict):
    """One catalogue.json lattice row: the honest inventory for tests."""

    origin: str
    registry_id: str
    package_id: str
    version: str
    manifest_sha256: str
    payload_sha256: str
    status_sequence: int


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_bytes(members: list[tuple[str, bytes]]) -> bytes:
    """ZIP_STORED throughout: zlib-independent reproducibility (final-fix 3a)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for path, data in sorted(members):
            info = zipfile.ZipInfo(path, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, data)
    return buf.getvalue()


def _payload(zip_data: bytes, members: list[tuple[str, bytes]]) -> dict[str, Any]:
    return {
        "sha256": _sha(zip_data),
        "bytes": len(zip_data),
        "media_type": "application/zip",
        "files": [
            {
                "path": p,
                "role": ROLE_BY_SUFFIX[p.rsplit("/", 1)[-1]],
                "bytes": len(b),
                "sha256": _sha(b),
            }
            for p, b in sorted(members)
        ],
    }


def _device_target(model: str, descriptor_id: str) -> dict[str, Any]:
    return {
        "manufacturer": "BenchWeave",
        "model": model,
        "aliases": [],
        "firmware": {"policy": "commissioning_required", "versions": []},
        "transports": ["sim"],
        "profile_ids": ["otdp:dc_psu:1.0.0"],
        "descriptor_ids": [descriptor_id],
    }


def _dep(registry_id: str, package_id: str, sha: str) -> dict[str, Any]:
    return {"registry_id": registry_id, "package_id": package_id, "version": "1.0.0",
            "manifest_sha256": sha}


def _manifest(
    registry_id: str,
    package_id: str,
    kind: str,
    provides: dict[str, Any],
    device_targets: list[dict[str, Any]],
    deps: list[dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    impl = kind == "implementation"
    return {
        "manifest_version": "0.1.0",
        "registry_id": registry_id,
        "package_id": package_id,
        "version": "1.0.0",
        "kind": kind,
        "display_name": package_id.rsplit("/", 1)[1],
        "summary": f"BenchWeave fixture {kind} ({package_id})",
        "released_at": RELEASED_AT,
        "tags": ["benchweave", kind],
        "publisher_id": "benchweave-fixtures",
        "maintainers": [{"name": "BenchWeave", "contact": "https://example.invalid/support"}],
        "support_url": "https://example.invalid/support",
        "issues_url": "https://example.invalid/issues",
        "licence": {"spdx_expression": "MIT", "file": "LICENSE"},
        "source": {"url": "https://example.invalid/src", "revision": "0" * 40},
        "compatibility": {
            "otdp_versions": ["0.1.0"],
            "adapter_api_versions": ["0.1.0"] if impl else [],
            "stg_versions": ["1.5"],
            "runtimes": (
                [{"os": "macos", "architecture": "arm64", "python_version": "3.13"}]
                if impl
                else []
            ),
            "host_provider_ids": [],
        },
        "device_targets": device_targets,
        "provides": provides,
        "dependencies": deps,
        "permissions": [],
        "payload": payload,
        "evidence": [
            {
                "level": "simulated",
                "report_path": "evidence/simulated.md",
                "tested_at": RELEASED_AT,
                "target": "synthetic",
                "result": "passed",
                "limitations": ["simulation-only fixture"],
            }
        ],
        "changelog_path": "CHANGELOG.md",
        "migration_notes_path": "MIGRATION.md",
        "limitations": ["WP06 fixture catalogue; not a real release"],
    }


def _status(
    registry_id: str,
    package_id: str,
    manifest_sha: str,
    *,
    sequence: int = 1,
    lifecycle: str = "published",
    reason: str = "initial release",
    expires: str = STATUS_EXPIRES,
) -> dict[str, Any]:
    return {
        "status_version": "0.1.0",
        "release": {
            "registry_id": registry_id,
            "package_id": package_id,
            "version": "1.0.0",
            "manifest_sha256": manifest_sha,
        },
        "sequence": sequence,
        "updated_at": RELEASED_AT,
        "expires_at": expires,
        "lifecycle": lifecycle,
        "reason": reason,
        "support_state": "maintained",
        "support_contact": "https://example.invalid/support",
        "reviews": [],
        "advisories": [],
    }


def _common_members() -> list[tuple[str, bytes]]:
    return [
        ("LICENSE", b"MIT (fixture)\n"),
        ("CHANGELOG.md", b"# 1.0.0\n- fixture release\n"),
        ("MIGRATION.md", b"# Migration\n\nNone.\n"),
        ("evidence/simulated.md", b"# Simulated evidence\n\nStructural + simulated only.\n"),
    ]


def _impl_extras() -> list[tuple[str, bytes]]:
    return [
        ("sbom.json", _canonical({"sbom_version": "1", "components": []})),
        ("build-provenance.json",
         _canonical({"inputs": [], "toolchain": "fixture", "output": "payload.zip"})),
        ("dependency-lock.json",
         _canonical({"lock_version": "py-fixture", "dependencies": []})),
    ]


def _profile_member() -> tuple[str, bytes]:
    """Structural dc_psu profile derived from the vendored OTDP class contract
    (``standards/otdp/0.1.0/examples/class-dc_psu.json``): class identity, the
    three profile actions with their class-contract properties, and one
    conformance vector per action. Kept small — a fixture, not a device model.
    """
    profile = {
        "profile_id": "otdp:dc_psu:1.0.0",
        "class": "dc_psu",
        "actions": ["configure", "output", "measure"],
        "action_contracts": {
            "configure": {"timeout_ms": 30000, "side_effect": "state_change"},
            "output": {"timeout_ms": 30000, "side_effect": "state_change"},
            "measure": {"timeout_ms": 30000, "side_effect": "none"},
        },
        "conformance_vectors": [
            {
                "action": "configure",
                "given": {
                    "configuration_id": "cfg-1",
                    "channel": "ch1",
                    "ovp_v": 6.0,
                    "ocp_a": 0.6,
                    "voltage_v": 5.0,
                    "current_limit_a": 0.5,
                },
                "expect": {"configuration_id": "cfg-1", "applied": True},
            },
            {
                "action": "output",
                "given": {"channel": "ch1", "enabled": True},
                "expect": {"channel": "ch1", "enabled": True},
            },
            {
                "action": "measure",
                "given": {"configuration_id": "cfg-1", "channels": ["ch1"]},
                "expect": {"variables": ["voltage", "current", "power"]},
            },
        ],
    }
    return ("profiles/dc-psu.json", _canonical(profile))
