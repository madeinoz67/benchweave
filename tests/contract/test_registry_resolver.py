# tests/contract/test_registry_resolver.py
"""Resolver: strict origin routing, collision safety, authenticated closure."""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchweave.registry.authenticity import AuthenticityRejected, load_trust_root
from benchweave.registry.manifests import Key
from benchweave.registry.resolver import (
    LocalDirectorySource,
    OriginConfig,
    PackageSource,
    Resolver,
)
from benchweave.registry.schemas import RegistryRejected

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures/registry"
NOW = int(datetime(2026, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)

MAIN_ROOT = load_trust_root("origin-main", REG / "keys" / "main.pub.pem")
DESC_KEY: Key = ("origin-main", "benchweave/sim-psu-descriptor", "1.0.0")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _sign_with_main(raw: bytes) -> bytes:
    key = serialization.load_pem_private_key((REG / "keys/main.pem").read_bytes(), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    return key.sign(raw)


@dataclass
class _OverlaySource:
    """In-test PackageSource: fixture catalogue plus per-release overrides.

    ``manifests``/``statuses`` map ``(package_id, version)`` to a re-signed
    ``(raw, signature)`` pair; ``missing`` forces FileNotFoundError.
    """

    base: LocalDirectorySource
    manifests: dict[tuple[str, str], tuple[bytes, bytes]] = field(default_factory=dict)
    statuses: dict[tuple[str, str], tuple[bytes, bytes]] = field(default_factory=dict)
    missing: frozenset[tuple[str, str]] = frozenset()

    def _check(self, package_id: str, version: str) -> None:
        if (package_id, version) in self.missing:
            raise FileNotFoundError(f"{package_id}/{version}")

    def manifest_bytes(self, package_id: str, version: str) -> tuple[bytes, str]:
        self._check(package_id, version)
        pair = self.manifests.get((package_id, version))
        if pair is None:
            return self.base.manifest_bytes(package_id, version)
        return pair[0], _sha(pair[0])

    def status_bytes(self, package_id: str, version: str) -> tuple[bytes, str]:
        self._check(package_id, version)
        pair = self.statuses.get((package_id, version))
        if pair is None:
            return self.base.status_bytes(package_id, version)
        return pair[0], _sha(pair[0])

    def payload_bytes(
        self, package_id: str, version: str, *, max_archive_bytes: int | None = None
    ) -> bytes:
        self._check(package_id, version)
        return self.base.payload_bytes(package_id, version, max_archive_bytes=max_archive_bytes)

    def manifest_signature(self, package_id: str, version: str) -> bytes:
        pair = self.manifests.get((package_id, version))
        if pair is None:
            return self.base.manifest_signature(package_id, version)
        return pair[1]

    def status_signature(self, package_id: str, version: str) -> bytes:
        pair = self.statuses.get((package_id, version))
        if pair is None:
            return self.base.status_signature(package_id, version)
        return pair[1]


def _origins(
    source: PackageSource | None = None,
    *,
    include_origin_b: bool = False,
) -> dict[str, OriginConfig]:
    origins: dict[str, OriginConfig] = {
        "origin-main": OriginConfig(
            registry_id="origin-main",
            root=MAIN_ROOT,
            source=source if source is not None else LocalDirectorySource(REG / "origin-main"),
            namespaces=("benchweave",),
        )
    }
    if include_origin_b:
        # Carries benchweave/sim-psu but routes no namespace: present, never used.
        origins["origin-b"] = OriginConfig(
            registry_id="origin-b",
            root=load_trust_root("origin-b", REG / "keys/originb.pub.pem"),
            source=LocalDirectorySource(REG / "origin-b"),
            namespaces=(),
        )
    return origins


def _fault_status(fault: str) -> tuple[bytes, bytes]:
    d = REG / "faults" / fault / DESC_KEY[1] / DESC_KEY[2]
    return (d / "status.json").read_bytes(), (d / "status.sig").read_bytes()


def test_resolve_full_closure() -> None:
    high_water: dict[Key, int] = {}
    closure = Resolver(_origins()).resolve(
        "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water=high_water
    )
    catalogue = {
        row["package_id"]: row
        for row in json.loads((REG / "catalogue.json").read_bytes())["releases"]
        if row["registry_id"] == "origin-main"
    }
    assert {r.package_id for r in closure.releases} == {
        "benchweave/sim-psu",
        "benchweave/sim-psu-descriptor",
        "benchweave/dc-psu-profile",
    }
    for release in closure.releases:
        assert release.registry_id == "origin-main"
        assert release.version == "1.0.0"
        assert release.manifest_sha256 == catalogue[release.package_id]["manifest_sha256"]
        assert release.manifest and release.status and release.payload
        assert release.manifest_sig and release.status_sig
    assert high_water == {
        ("origin-main", "benchweave/sim-psu", "1.0.0"): 1,
        DESC_KEY: 1,
        ("origin-main", "benchweave/dc-psu-profile", "1.0.0"): 1,
    }


def test_second_resolve_identical_digests() -> None:
    def digests(resolver: Resolver) -> list[tuple[str, str]]:
        closure = resolver.resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
        return sorted((r.package_id, r.manifest_sha256) for r in closure.releases)

    assert digests(Resolver(_origins())) == digests(Resolver(_origins()))


def test_collision_never_redirects() -> None:
    closure = Resolver(_origins(include_origin_b=True)).resolve(
        "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
    )
    assert {r.registry_id for r in closure.releases} == {"origin-main"}
    sim_psu = next(r for r in closure.releases if r.package_id == "benchweave/sim-psu")
    main_manifest = (REG / "origin-main/benchweave/sim-psu/1.0.0/manifest.json").read_bytes()
    clone_manifest = (REG / "origin-b/benchweave/sim-psu/1.0.0/manifest.json").read_bytes()
    assert sim_psu.manifest_sha256 == _sha(main_manifest)
    assert sim_psu.manifest_sha256 != _sha(clone_manifest)


def test_cross_origin_fallback_rejected() -> None:
    honest = REG / "origin-main/benchweave/sim-psu/1.0.0/manifest.json"
    manifest: dict[str, Any] = json.loads(honest.read_bytes())
    manifest["dependencies"][0]["registry_id"] = "origin-b"
    mutated = _canonical(manifest)
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        manifests={("benchweave/sim-psu", "1.0.0"): (mutated, _sign_with_main(mutated))},
    )
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins(source, include_origin_b=True)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "cross_origin_fallback"


def test_unrouted_namespace() -> None:
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins()).resolve(
            "elsewhere", "other/thing", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "unrouted_namespace"


def test_stale_sequence_via_resolver() -> None:
    # Replay: the descriptor publishes sequence 2 and resolve() pins it.
    seq2_raw, seq2_sig = _fault_status("rollback-seq2")
    overlay = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        statuses={("benchweave/sim-psu-descriptor", "1.0.0"): (seq2_raw, seq2_sig)},
    )
    replayed: dict[Key, int] = {}
    Resolver(_origins(overlay)).resolve(
        "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water=replayed
    )
    assert replayed[DESC_KEY] == 2
    # Rollback: sequence 1 replays against the map the caller persisted at 2.
    seq1_raw, seq1_sig = _fault_status("rollback-seq1")
    rolled_back = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        statuses={("benchweave/sim-psu-descriptor", "1.0.0"): (seq1_raw, seq1_sig)},
    )
    with pytest.raises(AuthenticityRejected) as exc:
        Resolver(_origins(rolled_back)).resolve(
            "origin-main",
            "benchweave/sim-psu",
            "1.0.0",
            now_ns=NOW,
            high_water={DESC_KEY: 2},
        )
    assert exc.value.reason == "stale_sequence"


def test_unknown_release() -> None:
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins()).resolve(
            "origin-main", "benchweave/absent", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "unknown_release"


def test_wrong_origin_signature_rejected() -> None:
    # Honest manifest bytes, signature made with the other origin's key: the
    # resolver must verify against the routing origin's trust root.
    raw = (REG / "origin-main/benchweave/sim-psu/1.0.0/manifest.json").read_bytes()
    wrong_key = serialization.load_pem_private_key(
        (REG / "keys/originb.pem").read_bytes(), password=None
    )
    assert isinstance(wrong_key, Ed25519PrivateKey)
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        manifests={("benchweave/sim-psu", "1.0.0"): (raw, wrong_key.sign(raw))},
    )
    with pytest.raises(AuthenticityRejected) as exc:
        Resolver(_origins(source)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "bad_signature"


def test_cycle_fixture_caught_by_pin_conflict() -> None:
    # Re-sign the descriptor with a back-edge to its dependent and re-pin that
    # digest in the dependent. A resolver-level cycle can never carry
    # consistent pins — each manifest's bytes embed the digest of the next
    # manifest in the cycle, so a consistent cycle would be a mutual-hash
    # fixed point — and the back-edge necessarily pins a digest that
    # disagrees with the re-signed root it revisits. The §10 pin-conflict
    # guard therefore rejects during the BFS, one check before admission;
    # ``cycle`` admission itself is pinned at the semantics level
    # (tests/contract/test_registry_semantics.py::test_cycle).
    sim_dir = REG / "origin-main/benchweave/sim-psu/1.0.0"
    impl: dict[str, Any] = json.loads((sim_dir / "manifest.json").read_bytes())
    desc: dict[str, Any] = json.loads(
        (REG / "origin-main/benchweave/sim-psu-descriptor/1.0.0/manifest.json").read_bytes()
    )
    desc["dependencies"].append(
        {
            "registry_id": "origin-main",
            "package_id": "benchweave/sim-psu",
            "version": "1.0.0",
            "manifest_sha256": _sha((sim_dir / "manifest.json").read_bytes()),
        }
    )
    desc_raw = _canonical(desc)
    impl["dependencies"][0]["manifest_sha256"] = _sha(desc_raw)
    impl_raw = _canonical(impl)
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        manifests={
            ("benchweave/sim-psu", "1.0.0"): (impl_raw, _sign_with_main(impl_raw)),
            ("benchweave/sim-psu-descriptor", "1.0.0"): (desc_raw, _sign_with_main(desc_raw)),
        },
    )
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins(source)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "digest_disagreement"


def test_missing_dependency_file() -> None:
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        missing=frozenset({("benchweave/sim-psu-descriptor", "1.0.0")}),
    )
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins(source)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "missing_dependency"


def test_root_served_manifest_identity_mismatch() -> None:
    # A mis-serving origin returns sim-controller's genuine, validly-signed
    # manifest+sig pair for the sim-psu request: signature verification alone
    # passes, so the resolver must recheck the served manifest's self-declared
    # registry_id/package_id/version against the requested key.
    controller = REG / "origin-main/benchweave/sim-controller/1.0.0"
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        manifests={
            ("benchweave/sim-psu", "1.0.0"): (
                (controller / "manifest.json").read_bytes(),
                (controller / "manifest.sig").read_bytes(),
            )
        },
    )
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins(source)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "identity_mismatch"


def test_dependency_digest_disagreement_rejected() -> None:
    # Two dependents pin the same release key at different digests: the first
    # edge resolves against the true digest, and the revisit must compare the
    # disagreeing pin against the stored release instead of skipping it.
    sim_dir = REG / "origin-main/benchweave/sim-psu/1.0.0"
    impl: dict[str, Any] = json.loads((sim_dir / "manifest.json").read_bytes())
    impl["dependencies"].append(
        {
            "registry_id": "origin-main",
            "package_id": "benchweave/sim-psu-descriptor",
            "version": "1.0.0",
            "manifest_sha256": _sha(b"disagreeing pin"),
        }
    )
    impl_raw = _canonical(impl)
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        manifests={("benchweave/sim-psu", "1.0.0"): (impl_raw, _sign_with_main(impl_raw))},
    )
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins(source)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "digest_disagreement"


def test_payload_size_limit_rejects_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final-fix 1c: an origin-level archive cap refuses on stat alone.

    The oversized payload is never read into memory — the read seam explodes
    if the source reaches for ``payload.zip`` before rejecting.
    """
    origin = tmp_path / "origin"
    shutil.copytree(REG / "origin-main", origin)
    (origin / "benchweave/sim-psu/1.0.0/payload.zip").write_bytes(b"\x00" * 5000)
    source = LocalDirectorySource(origin)

    def _no_payload_read(package_id: str, version: str, filename: str) -> bytes:
        assert filename != "payload.zip", "oversized payload read into memory"
        return (origin / package_id / version / filename).read_bytes()

    monkeypatch.setattr(source, "_read", _no_payload_read)
    origins: dict[str, OriginConfig] = {
        "origin-main": OriginConfig(
            registry_id="origin-main",
            root=MAIN_ROOT,
            source=source,
            namespaces=("benchweave",),
            max_archive_bytes=1_000,
        )
    }
    with pytest.raises(RegistryRejected) as exc:
        Resolver(origins).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "archive_too_large"
