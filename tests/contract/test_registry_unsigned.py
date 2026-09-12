"""Origin-level signature policy: dev-unsigned skips authenticity only."""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

from benchweave.registry.admission import (
    AdmissionLimits,
    AdmissionRejected,
    Approval,
    admit,
)
from benchweave.registry.authenticity import (
    AuthenticityRejected,
    TrustRoot,
    load_trust_root,
)
from benchweave.registry.manifests import Key
from benchweave.registry.resolver import (
    LocalDirectorySource,
    OriginConfig,
    ResolvedClosure,
    Resolver,
)
from benchweave.registry.schemas import RegistryRejected

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures" / "registry"
# Fixed admission/resolve clock, same date the WP06 contract suite freezes.
NOW_NS = int(datetime(2026, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)

MAIN_ROOT = load_trust_root("origin-main", REG / "keys" / "main.pub.pem")

# The dev origin serves a byte-for-byte copy of the signed origin-main tree
# with the *.sig files stripped, and its manifests self-declare registry_id
# "origin-main" — the identity recheck and the dependency pins both key on
# that id, so the dev copy resolves under the same id (rewriting manifests to
# a fresh dev id is the publisher's job, not the resolver's).
DEV_ID = "origin-main"
ROOT_KEY: Key = (DEV_ID, "benchweave/sim-psu", "1.0.0")
DESC_KEY: Key = (DEV_ID, "benchweave/sim-psu-descriptor", "1.0.0")
PROFILE_KEY: Key = (DEV_ID, "benchweave/dc-psu-profile", "1.0.0")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_dev_origin(tmp_path: Path) -> Path:
    """Copy the signed origin-main tree and strip the .sig files => a dev origin."""
    dev = tmp_path / "dev-origin"
    shutil.copytree(REG / "origin-main", dev)
    for sig in dev.rglob("*.sig"):
        sig.unlink()
    return dev


def _resolver(
    source_root: Path,
    *,
    policy: Literal["required", "dev-unsigned"] = "dev-unsigned",
    root: TrustRoot | None = None,
) -> Resolver:
    return Resolver(
        {
            DEV_ID: OriginConfig(
                registry_id=DEV_ID,
                root=root,
                source=LocalDirectorySource(source_root),
                namespaces=("benchweave",),
                signature_policy=policy,
            )
        }
    )


def _limits() -> AdmissionLimits:
    return AdmissionLimits(
        max_archive_bytes=1_000_000, max_files=100, max_unpacked_bytes=1_000_000
    )


def _approval() -> Approval:
    return Approval(
        principal_id="benchweave-test",
        approved_at="2026-09-12T00:00:00Z",
        policy_id="local-policy",
        policy_version="1.0.0",
    )


def _admit(
    closure: ResolvedClosure,
    work: Path,
) -> None:
    admit(
        closure,
        cache_root=work / "cache",
        lock_path=work / "packages.lock.json",
        limits=_limits(),
        approval=_approval(),
        now_ns=NOW_NS,
        roots={DEV_ID: None},
    )


def test_dev_unsigned_closure_resolves(tmp_path: Path) -> None:
    dev = _build_dev_origin(tmp_path)
    high_water: dict[Key, int] = {}
    closure = _resolver(dev).resolve(
        DEV_ID, "benchweave/sim-psu", "1.0.0", now_ns=NOW_NS, high_water=high_water
    )
    assert {r.package_id for r in closure.releases} == {
        "benchweave/sim-psu",
        "benchweave/sim-psu-descriptor",
        "benchweave/dc-psu-profile",
    }
    for release in closure.releases:
        assert release.registry_id == DEV_ID
        assert release.version == "1.0.0"
        assert release.manifest and release.status and release.payload
        # No signature was fetched under dev-unsigned.
        assert release.manifest_sig == b""
        assert release.status_sig == b""
        # Digests and identity stay live: the manifest bytes are the copied
        # fixture bytes, pinned by the manifest sha — unmutated.
        fixture = dev / release.package_id / "1.0.0" / "manifest.json"
        assert release.manifest_sha256 == _sha(fixture.read_bytes())
    # Sequence honesty stays live: every release pinned its status sequence.
    assert high_water == {ROOT_KEY: 1, DESC_KEY: 1, PROFILE_KEY: 1}


def test_unsigned_bytes_under_required_origin_reject(tmp_path: Path) -> None:
    dev = _build_dev_origin(tmp_path)
    with pytest.raises(AuthenticityRejected) as exc:
        _resolver(dev, policy="required", root=MAIN_ROOT).resolve(
            DEV_ID, "benchweave/sim-psu", "1.0.0", now_ns=NOW_NS, high_water={}
        )
    # A missing signature file under `required` is bad_signature, never an
    # OS error (and never misread as an unknown release).
    assert exc.value.reason == "bad_signature"


def test_required_with_none_root_rejects_at_config(tmp_path: Path) -> None:
    with pytest.raises(RegistryRejected) as exc:
        _resolver(tmp_path, policy="required", root=None)
    assert exc.value.reason == "invalid_origin_config"


def test_default_policy_is_required() -> None:
    config = OriginConfig(
        registry_id=DEV_ID,
        root=MAIN_ROOT,
        source=LocalDirectorySource(REG / "origin-main"),
        namespaces=("benchweave",),
    )
    assert config.signature_policy == "required"
    # Byte-identical WP06 behaviour: the signed fixture tree resolves exactly
    # as before, signatures attached.
    high_water: dict[Key, int] = {}
    closure = Resolver({DEV_ID: config}).resolve(
        DEV_ID, "benchweave/sim-psu", "1.0.0", now_ns=NOW_NS, high_water=high_water
    )
    assert len(closure.releases) == 3
    assert all(r.manifest_sig and r.status_sig for r in closure.releases)
    assert high_water == {ROOT_KEY: 1, DESC_KEY: 1, PROFILE_KEY: 1}


def test_tampered_dev_payload_rejects_at_admission(tmp_path: Path) -> None:
    dev = _build_dev_origin(tmp_path)
    closure = _resolver(dev).resolve(
        DEV_ID, "benchweave/sim-psu", "1.0.0", now_ns=NOW_NS, high_water={}
    )
    releases = []
    for release in closure.releases:
        if (release.registry_id, release.package_id, release.version) == ROOT_KEY:
            payload = release.payload[:-1] + bytes([release.payload[-1] ^ 1])
            release = replace(release, payload=payload)
        releases.append(release)
    with pytest.raises(AdmissionRejected) as exc:
        _admit(ResolvedClosure(releases=tuple(releases)), tmp_path)
    # Integrity without authenticity: no signature was ever checked, and the
    # payload still fails its declared digest at admission.
    assert exc.value.reason == "payload_digest_mismatch"
    assert not (tmp_path / "cache").exists()


def test_dev_rollback_rejects_via_persisted_high_water(tmp_path: Path) -> None:
    """The persisted rollback gate stays armed on the dev path.

    First install replays the descriptor's sequence-2 status (a writable dev
    root makes the rollback drill possible without keys) and persists the
    high-water map. The origin then rolls back to sequence 1: a fresh resolver
    session — empty in-memory expectations — cannot catch it; only the
    persisted ``<cache_root>/high-water.json`` layer does.
    """
    dev = _build_dev_origin(tmp_path)
    resolver = _resolver(dev)
    desc_status = dev / "benchweave" / "sim-psu-descriptor" / "1.0.0" / "status.json"
    fault = REG / "faults" / "rollback-seq2" / DESC_KEY[1] / DESC_KEY[2] / "status.json"

    desc_status.write_bytes(fault.read_bytes())
    closure = resolver.resolve(
        DEV_ID, "benchweave/sim-psu", "1.0.0", now_ns=NOW_NS, high_water={}
    )
    _admit(closure, tmp_path)

    water_path = tmp_path / "cache" / "high-water.json"
    assert water_path.is_file()
    rows = {
        (row["registry_id"], row["package_id"], row["version"]): row["sequence"]
        for row in json.loads(water_path.read_bytes())["releases"]
    }
    assert rows[DESC_KEY] == 2

    rolled_fault = REG / "faults" / "rollback-seq1" / DESC_KEY[1] / DESC_KEY[2] / "status.json"
    desc_status.write_bytes(rolled_fault.read_bytes())
    rolled = resolver.resolve(
        DEV_ID, "benchweave/sim-psu", "1.0.0", now_ns=NOW_NS, high_water={}
    )
    with pytest.raises(AdmissionRejected) as exc:
        _admit(rolled, tmp_path)
    assert exc.value.reason == "stale_sequence"
