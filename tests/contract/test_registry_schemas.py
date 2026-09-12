# tests/contract/test_registry_schemas.py
"""Registry schema validators: strict load + vendored-schema validation."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from benchweave.content.json_document import DocumentRejected
from benchweave.registry.schemas import (
    RegistryRejected,
    load_lock_document,
    load_manifest_document,
    load_status_document,
)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_manifest() -> dict[str, Any]:
    return {
        "manifest_version": "1.0.0",
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
            "otdp_versions": ["0.3.0"],
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
                {"path": "LICENSE", "role": "licence", "bytes": 1, "sha256": "b" * 64}
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


def _dump(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def test_manifest_valid_roundtrip() -> None:
    raw = _dump(_valid_manifest())
    loaded = load_manifest_document(raw, _digest(raw), max_bytes=1_000_000)
    assert loaded.content["package_id"] == "benchweave/dc-psu-profile"


def test_manifest_unknown_field_rejected() -> None:
    doc = _valid_manifest()
    doc["surprise"] = 1
    raw = _dump(doc)
    with pytest.raises(RegistryRejected) as exc:
        load_manifest_document(raw, _digest(raw), max_bytes=1_000_000)
    assert exc.value.reason == "schema_invalid"
    # Wave-1 item 8: the message is diagnostic — it carries the first sorted
    # error's JSON path so a schema rejection points at its subject. For an
    # unknown top-level property jsonschema's additionalProperties error
    # sits at the document root ($); the exact-path pin is on the bad-uri
    # test below, whose first error carries a real property path.
    assert "first failing path: $" in str(exc.value)


@pytest.mark.parametrize(
    "bad_url",
    [
        # Fails both the schema's ^https:// pattern and the uri format:
        "not-a-url",
        # Passes the ^https:// pattern — ONLY the live format check (rfc3987
        # behind jsonschema's FormatChecker) can reject it:
        "https://bad uri",
    ],
)
def test_manifest_bad_uri_rejected_by_format_check(bad_url: str) -> None:
    """Final-fix 4a: with rfc3987 as a runtime dep the uri format assertion
    actually fires (before it was registered-but-inert and these passed)."""
    doc = _valid_manifest()
    doc["support_url"] = bad_url
    raw = _dump(doc)
    with pytest.raises(RegistryRejected) as exc:
        load_manifest_document(raw, _digest(raw), max_bytes=1_000_000)
    assert exc.value.reason == "schema_invalid"
    # Wave-1 item 8, exact-path pin: the first sorted error's JSON path
    # (``$.support_url``) rides the rejection message.
    assert "$.support_url" in str(exc.value)


def test_manifest_kind_conditional_enforced() -> None:
    doc = _valid_manifest()  # profile must carry zero device targets and >=1 profile id
    doc["device_targets"] = [
        {
            "manufacturer": "x",
            "model": "y",
            "aliases": [],
            "firmware": {"policy": "commissioning_required", "versions": []},
            "transports": ["sim"],
            "profile_ids": [],
            "descriptor_ids": ["d"],
        }
    ]
    raw = _dump(doc)
    with pytest.raises(RegistryRejected) as exc:
        load_manifest_document(raw, _digest(raw), max_bytes=1_000_000)
    assert exc.value.reason == "schema_invalid"


def test_status_and_lock_loaders() -> None:
    status = {
        "status_version": "1.0.0",
        "release": {
            "registry_id": "origin-main",
            "package_id": "benchweave/dc-psu-profile",
            "version": "1.0.0",
            "manifest_sha256": "a" * 64,
        },
        "sequence": 1,
        "updated_at": "2026-09-11T00:00:00Z",
        "expires_at": "2027-09-11T00:00:00Z",
        "lifecycle": "published",
        "reason": "initial release",
        "support_state": "maintained",
        "support_contact": "https://example.invalid/support",
        "reviews": [],
        "advisories": [],
    }
    raw = _dump(status)
    assert load_status_document(raw, _digest(raw), max_bytes=100_000).content["sequence"] == 1

    lock = {
        "lock_version": "1.0.0",
        "created_at": "2026-09-11T00:00:00Z",
        "roots": [
            {
                "registry_id": "origin-main",
                "package_id": "benchweave/sim-psu",
                "version": "1.0.0",
                "manifest_sha256": "a" * 64,
            }
        ],
        "packages": [
            {
                "registry_id": "origin-main",
                "package_id": "benchweave/sim-psu",
                "version": "1.0.0",
                "manifest_sha256": "a" * 64,
            }
        ],
        "approval": {
            "principal_id": "op",
            "approved_at": "2026-09-11T00:00:00Z",
            "policy_id": "poc",
            "policy_version": "1",
        },
    }
    raw_lock = _dump(lock)
    loaded_lock = load_lock_document(raw_lock, _digest(raw_lock), max_bytes=100_000)
    assert loaded_lock.content["lock_version"] == "1.0.0"


def test_digest_mismatch_still_rejected_by_content_layer() -> None:
    raw = _dump(_valid_manifest())
    with pytest.raises(DocumentRejected):
        load_manifest_document(raw, "0" * 64, max_bytes=1_000_000)
