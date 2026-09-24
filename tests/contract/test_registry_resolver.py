# tests/contract/test_registry_resolver.py
"""Resolver: strict origin routing, collision safety, authenticated closure."""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchweave.host.plugin import SimulationInfo
from benchweave.registry.activation import ActivationRejected
from benchweave.registry.authenticity import AuthenticityRejected, load_trust_root
from benchweave.registry.manifests import Key
from benchweave.registry.otdp_loading import load_otdp_plugin
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

# The private signing keys are not committed (only their .pub.pem halves are);
# CI materialises them from repository secrets, and fork PRs receive none.
# Tests that must SIGN skip without them — never fail — so a fresh clone's
# `uv run pytest -q` stays truthful. Everything reading the committed,
# already-signed fixtures still runs.
requires_signing_keys = pytest.mark.skipif(
    not all(
        (REG / "keys" / name).is_file() and (REG / "keys" / name).stat().st_size > 0
        for name in ("main.pem", "originb.pem")
    ),
    reason="requires the private fixture signing keys under fixtures/registry/keys/",
)


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


def _restatus(package_id: str, version: str, manifest_sha: str) -> tuple[bytes, bytes]:
    """Re-pin a release's status to a mutated manifest's digest (re-signed).

    A served status is bound to the release it accompanies
    (``status_release_mismatch``): a test that serves a MUTATED manifest must
    serve the status re-pinned to that manifest's digest, or the binding
    rejects before the behavior under test is reached.
    """
    d = REG / "origin-main" / package_id / version
    status = json.loads((d / "status.json").read_bytes())
    status["release"]["manifest_sha256"] = manifest_sha
    raw = _canonical(status)
    return raw, _sign_with_main(raw)


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


@requires_signing_keys
def test_cross_origin_fallback_rejected() -> None:
    honest = REG / "origin-main/benchweave/sim-psu/1.0.0/manifest.json"
    manifest: dict[str, Any] = json.loads(honest.read_bytes())
    manifest["dependencies"][0]["registry_id"] = "origin-b"
    mutated = _canonical(manifest)
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        manifests={("benchweave/sim-psu", "1.0.0"): (mutated, _sign_with_main(mutated))},
        statuses={
            ("benchweave/sim-psu", "1.0.0"): _restatus(
                "benchweave/sim-psu", "1.0.0", _sha(mutated)
            )
        },
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


@requires_signing_keys
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


@requires_signing_keys
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
        statuses={
            ("benchweave/sim-psu", "1.0.0"): _restatus(
                "benchweave/sim-psu", "1.0.0", _sha(impl_raw)
            ),
            ("benchweave/sim-psu-descriptor", "1.0.0"): _restatus(
                "benchweave/sim-psu-descriptor", "1.0.0", _sha(desc_raw)
            ),
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


def test_root_served_status_release_mismatch() -> None:
    # A mis-serving origin returns sim-controller's genuine, validly-signed
    # status.json+status.sig pair for the sim-psu request: both signature
    # checks pass (the bytes are real and main-signed), so the resolver must
    # bind the served status to the release it accompanies — its release
    # block must name the requested key AND pin the served manifest digest —
    # before any lifecycle or sequence gate can trust it. Without the
    # binding, a swapped "published" status dodges a real revocation.
    controller = REG / "origin-main/benchweave/sim-controller/1.0.0"
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        statuses={
            ("benchweave/sim-psu", "1.0.0"): (
                (controller / "status.json").read_bytes(),
                (controller / "status.sig").read_bytes(),
            )
        },
    )
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins(source)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "status_release_mismatch"


@requires_signing_keys
def test_status_manifest_pin_mismatch() -> None:
    # Identity-correct status whose release block pins a DIFFERENT manifest
    # digest (re-signed with main, so authenticity passes): a status is bound
    # to the release bytes it accompanies, not just to the release's name
    # (contract §6/§10).
    status = json.loads(
        (REG / "origin-main/benchweave/sim-psu/1.0.0/status.json").read_bytes()
    )
    status["release"]["manifest_sha256"] = _sha(b"not the served manifest")
    raw = _canonical(status)
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        statuses={("benchweave/sim-psu", "1.0.0"): (raw, _sign_with_main(raw))},
    )
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins(source)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "status_release_mismatch"


@requires_signing_keys
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
        statuses={
            ("benchweave/sim-psu", "1.0.0"): _restatus(
                "benchweave/sim-psu", "1.0.0", _sha(impl_raw)
            )
        },
    )
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins(source)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "digest_disagreement"


@pytest.mark.parametrize("fetch", ["manifest_signature", "status_signature"])
def test_unreadable_signature_is_bad_signature(
    monkeypatch: pytest.MonkeyPatch, fetch: str
) -> None:
    """Wave-1 item 7: a `.sig` the process cannot READ (PermissionError) is
    bad authenticity at BOTH fetch sites, same as a missing one — never an
    OS error leaking to the caller."""

    def _denied(self: LocalDirectorySource, package_id: str, version: str) -> bytes:
        raise PermissionError(f"{package_id}/{version} {fetch} unreadable")

    monkeypatch.setattr(LocalDirectorySource, fetch, _denied)
    with pytest.raises(AuthenticityRejected) as exc:
        Resolver(_origins()).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "bad_signature"


@requires_signing_keys
def test_pretty_printed_manifest_refused_as_not_canonical() -> None:
    """Row G (issue #176, design F4): a content-identical manifest
    re-serialized non-canonically — pretty-printed, with its status
    re-pinned and re-signed to the new raw bytes so every raw-digest pin
    agrees — refuses at RESOLUTION with ``manifest_not_canonical`` naming
    the package. The pin lattice (status rows, lock dependencies, catalogue,
    cache directory, loader check) is keyed by ONE digest and is only
    coherent when admissible manifest bytes ARE the canonical serialization;
    without this check the release resolves and admits cleanly and the
    mismatch surfaces only later, at ``load_otdp_plugin``, as a misleading
    ``manifest_hash_mismatch``."""
    pretty = json.dumps(
        json.loads((REG / "origin-main/benchweave/sim-psu/1.0.0/manifest.json").read_bytes()),
        indent=2,
    )
    raw = pretty.encode()
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        manifests={("benchweave/sim-psu", "1.0.0"): (raw, _sign_with_main(raw))},
        statuses={
            ("benchweave/sim-psu", "1.0.0"): _restatus(
                "benchweave/sim-psu", "1.0.0", _sha(raw)
            )
        },
    )
    with pytest.raises(RegistryRejected) as exc:
        Resolver(_origins(source)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert exc.value.reason == "manifest_not_canonical"
    assert "benchweave/sim-psu" in str(exc.value)


def test_every_in_tree_fixture_manifest_is_canonical() -> None:
    """Row G collateral guard (G-R2): every in-tree fixture manifest serves
    the canonical serialization — the builder's only emission form — so the
    resolver's canonicality refusal moves no fixture bytes beyond the
    row-D lattice rebuild."""
    manifests = sorted(REG.glob("origin-*/benchweave/*/*/manifest.json"))
    assert len(manifests) == 6
    for path in manifests:
        raw = path.read_bytes()
        assert raw == _canonical(json.loads(raw)), str(path)


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


def _g2_oracle_canonical(obj: dict[str, Any]) -> bytes:
    """gF2's ONE canonical-bytes oracle (issue #176 council fold wave).

    The resolver's inline formula (``Resolver._resolve_release``) and the
    loader's re-hash (``load_otdp_plugin``) are two independent copies of
    this serialization. The agreement pin below asserts BOTH enforcement
    sites against THIS helper only — never against each other — so a silent
    divergence between the production copies fails the pin from one side or
    the other. Used only by ``test_canonical_form_agreement_pin``; the
    production formula sites are deliberately not touched (helper
    extraction is a deferral row).
    """
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def test_canonical_form_agreement_pin(tmp_path: Path) -> None:
    """gF2 (issue #176 council fold wave): both canonical-form enforcement
    sites accept exactly the oracle's bytes and refuse a re-serialization
    divergence.

    The resolver refuses each divergence at RESOLUTION with
    ``manifest_not_canonical`` (the canonicality check runs before
    signature verification, so these arms need no signing keys); the loader
    accepts the oracle digest — moving past ``manifest_hash_mismatch`` to
    the missing cache contents — and refuses a divergence digest with
    ``manifest_hash_mismatch``. The release-manifest schema carries no
    float field (``payload.bytes`` is an integer), so the non-ASCII probe
    rides the ``summary`` string field: a literal em-dash that canonical
    form must ASCII-escape.
    """
    fixture_raw = (REG / "origin-main/benchweave/sim-psu/1.0.0/manifest.json").read_bytes()
    probe = json.loads(fixture_raw)
    probe["summary"] = "Probe manifest — non-canonical serialization pin"
    oracle = _g2_oracle_canonical(probe)
    assert oracle != fixture_raw  # the probe is not the fixture's bytes
    assert b"\xe2\x80\x94" not in oracle  # ASCII-escaped: no literal em-dash byte

    # Three content-identical divergences, each refused at resolve.
    divergences: dict[str, bytes] = {
        "pretty": json.dumps(probe, indent=2).encode(),
        "literal-non-ascii": (
            json.dumps(probe, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode(),
        "missing-trailing-newline": oracle[:-1],
    }
    assert json.loads(divergences["literal-non-ascii"]) == probe
    for label, raw in divergences.items():
        assert raw != oracle, label
        source = _OverlaySource(
            base=LocalDirectorySource(REG / "origin-main"),
            manifests={("benchweave/sim-psu", "1.0.0"): (raw, b"unused")},
        )
        with pytest.raises(RegistryRejected) as resolve_exc:
            Resolver(_origins(source)).resolve(
                "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
            )
        assert resolve_exc.value.reason == "manifest_not_canonical", label
        assert "benchweave/sim-psu" in str(resolve_exc.value), label

    # Resolver accept: the oracle bytes pass canonicality — the serve stops
    # later, at signature verification over the fixture's original .sig
    # (never re-signed to the probe), never at manifest_not_canonical.
    fixture_sig = (REG / "origin-main/benchweave/sim-psu/1.0.0/manifest.sig").read_bytes()
    accepted = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        manifests={("benchweave/sim-psu", "1.0.0"): (oracle, fixture_sig)},
    )
    with pytest.raises(AuthenticityRejected) as signature_exc:
        Resolver(_origins(accepted)).resolve(
            "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
        )
    assert signature_exc.value.reason == "bad_signature"  # canonicality already passed

    # Loader accept: the re-hash agrees with the oracle — the load moves
    # past the digest gate to the missing cache contents.
    with pytest.raises(ActivationRejected) as cache_exc:
        load_otdp_plugin(
            tmp_path,
            probe,
            hashlib.sha256(oracle).hexdigest(),
            entry_relpath="src/example/plugin.py",
            descriptor={},
            services=SimpleNamespace(monotonic=lambda: 0.0),
            simulation=SimulationInfo(True, "g2"),
        )
    assert cache_exc.value.reason == "file_hash_mismatch"

    # Loader refuse: a divergence digest convention fails the re-hash gate.
    with pytest.raises(ActivationRejected) as gate_exc:
        load_otdp_plugin(
            tmp_path,
            probe,
            hashlib.sha256(divergences["pretty"]).hexdigest(),
            entry_relpath="src/example/plugin.py",
            descriptor={},
            services=SimpleNamespace(monotonic=lambda: 0.0),
            simulation=SimulationInfo(True, "g2"),
        )
    assert gate_exc.value.reason == "manifest_hash_mismatch"
