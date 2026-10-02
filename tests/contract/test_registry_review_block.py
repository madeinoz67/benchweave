"""Registry 0.1.2 review-block arms (issue #223 slice 1, design §3.2/F1).

The enum arm keeps every 0.1.1 manifest valid under the active schema (A7's
outcome-neutrality), and the review block is required exactly when
``manifest_version`` is 0.1.2 — the same conditional pattern the schema already
uses for ``kind``. The gateway never consults ``review`` (CR-13); these tests
pin the SCHEMA's behavior, not admission semantics.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchweave.registry.schemas import RegistryRejected, load_manifest_document

REPO = Path(__file__).resolve().parents[2]
_MANIFEST = json.loads((REPO / "standards" / "standards-manifest.json").read_bytes())
ACTIVE_VERSION = next(
    entry["version"] for entry in _MANIFEST["standards"] if entry["id"] == "registry"
)
ACTIVE_DIR = REPO / "standards" / "registry" / ACTIVE_VERSION

#: A complete, schema-valid 0.1.1 example — the base for every arm.
_BASE: dict[str, object] = json.loads(
    (ACTIVE_DIR / "examples" / "release-manifest.json").read_bytes()
)

_REVIEW_BLOCK: dict[str, object] = {
    "checklist_id": "review-checklist",
    "checklist_version": "1",
    "reviewer_id": "madeinoz67",
    "outcome": "accepted",
    "record_sha256": "a" * 64,
}


def _valid(raw: dict[str, object]) -> bool:
    import hashlib

    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    try:
        load_manifest_document(encoded, hashlib.sha256(encoded).hexdigest(), max_bytes=1_000_000)
    except RegistryRejected:
        return False
    return True


def test_active_registry_version_is_0_1_2() -> None:
    assert (ACTIVE_DIR.name) == "0.1.2", (
        f"the publishing lane's review block requires the 0.1.2 corpus (active is "
        f"{ACTIVE_DIR.name})"
    )


def test_0_1_1_manifest_stays_valid_under_the_active_schema() -> None:
    """A7's enum arm: the 0.1.1 example validates unchanged (byte-identical outcome)."""
    assert _BASE["manifest_version"] == "0.1.1"
    assert _valid(_BASE)


def test_0_1_2_without_review_block_is_refused() -> None:
    mutant = copy.deepcopy(_BASE)
    mutant["manifest_version"] = "0.1.2"
    assert not _valid(mutant)


def test_0_1_2_with_wellformed_review_block_is_valid() -> None:
    upgraded = copy.deepcopy(_BASE)
    upgraded["manifest_version"] = "0.1.2"
    upgraded["review"] = dict(_REVIEW_BLOCK)
    assert _valid(upgraded)


@pytest.mark.parametrize(
    "field", ["checklist_id", "checklist_version", "reviewer_id", "outcome", "record_sha256"]
)
def test_review_block_is_closed_and_complete(field: str) -> None:
    """Every review field is required and the block admits no extras."""
    missing = copy.deepcopy(_BASE)
    missing["manifest_version"] = "0.1.2"
    missing["review"] = {k: v for k, v in _REVIEW_BLOCK.items() if k != field}
    assert not _valid(missing), field

    extra = copy.deepcopy(_BASE)
    extra["manifest_version"] = "0.1.2"
    extra["review"] = {**_REVIEW_BLOCK, "notes": "extra key refuses"}
    assert not _valid(extra)


def test_review_outcome_enum_is_closed() -> None:
    mutant = copy.deepcopy(_BASE)
    mutant["manifest_version"] = "0.1.2"
    mutant["review"] = {**_REVIEW_BLOCK, "outcome": "rubber-stamped"}
    assert not _valid(mutant)


def test_record_sha256_is_hex64() -> None:
    mutant = copy.deepcopy(_BASE)
    mutant["manifest_version"] = "0.1.2"
    mutant["review"] = {**_REVIEW_BLOCK, "record_sha256": "not-hex"}
    assert not _valid(mutant)


# --- A7: the full fixture catalogue admits under the active schema ----------------


def test_full_catalogue_admits_under_the_active_schema(tmp_path: Path) -> None:
    """Every published 0.1.1 fixture release validates and admits unchanged.

    A7's catalogue half: the enum arm is outcome-neutral by construction and
    this pins it on the whole committed lattice — the same resolve/admit
    construction as the replay harness, over every release in the committed
    catalogue.
    """
    from benchweave.registry.admission import (
        AdmissionLimits,
        Approval,
        admit,
    )
    from benchweave.registry.authenticity import load_trust_root
    from benchweave.registry.resolver import (
        LocalDirectorySource,
        OriginConfig,
        Resolver,
    )

    reg = REPO / "fixtures" / "registry"
    catalogue = json.loads((reg / "catalogue.json").read_bytes())
    published = [
        row
        for row in catalogue["releases"]
        if row["origin"] in ("origin-main", "origin-b")
    ]
    assert len(published) >= 5  # profile + 2 descriptors + 2 implementations
    now_ns = 1_800_000_000_000_000_000
    expected_digests = {
        (row["origin"], row["package_id"], row["version"]): row["manifest_sha256"]
        for row in published
    }
    def public_key(origin: str) -> Path:
        name = "main" if origin == "origin-main" else "originb"
        return reg / "keys" / f"{name}.pub.pem"

    # Both origins configured together: origin-b's closure rides origin-main
    # dependencies (the reuse harness's include_origin_b shape).
    origins = {
        origin: OriginConfig(
            registry_id=origin,
            root=load_trust_root(origin, public_key(origin)),
            source=LocalDirectorySource(reg / origin),
            namespaces=("benchweave",),
        )
        for origin in ("origin-main", "origin-b")
    }
    for origin in ("origin-main", "origin-b"):
        releases = [row for row in published if row["origin"] == origin]
        if not releases:
            continue
        seen: set[tuple[str, str, str]] = set()
        for row in releases:
            key = (origin, row["package_id"], row["version"])
            if key in seen:
                continue  # origin-b re-emits sim-psu; one admission per key
            seen.add(key)
            closure = Resolver(origins).resolve(
                origin, row["package_id"], row["version"], now_ns=now_ns, high_water={}
            )
            admitted = admit(
                closure,
                cache_root=tmp_path / "cache" / origin,
                lock_path=tmp_path / f"{origin}.lock.json",
                limits=AdmissionLimits(
                    max_archive_bytes=1_000_000, max_files=100, max_unpacked_bytes=1_000_000
                ),
                approval=Approval(
                    principal_id="a7-catalogue",
                    approved_at="2026-10-01T00:00:00Z",
                    policy_id="a7",
                    policy_version="1.0.0",
                ),
                now_ns=now_ns,
                roots={
                    name: load_trust_root(name, public_key(name))
                    for name in ("origin-main", "origin-b")
                },
            )
            for release in closure.releases:
                assert (
                    release.manifest["manifest_version"] == "0.1.1"
                )  # the served catalogue stays 0.1.1 manifests
                assert (
                    release.manifest_sha256
                    == expected_digests[
                        (release.registry_id, release.package_id, release.version)
                    ]
                ), "byte-identical outcome: the admitted digest equals the catalogue pin"
            assert admitted.manifest_sha256s  # non-empty closure admitted
