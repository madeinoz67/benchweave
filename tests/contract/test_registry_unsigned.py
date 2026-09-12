# tests/contract/test_registry_unsigned.py
"""Origin-level signature policy: dev-unsigned skips authenticity only.

The dev origin is built by the Task 2 publisher (fresh manifests under
registry id ``dev-local``) and resolved through the DESIGNED mixed-policy
origin map: a ``dev-unsigned`` dev origin (``root=None``, ``dev``
namespace) alongside the fail-closed signed ``origin-main`` — an unsigned
implementation over its signed production descriptor/profile closure. The
dev origin can no longer borrow a signed registry's identity:
``OriginConfig`` construction itself rejects a ``dev-unsigned`` origin
whose id is not ``dev-``-prefixed (or that carries a root), so the
single-entry ``origin-main`` + ``dev-unsigned`` impersonation is
structurally impossible, not merely untested.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
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
PUBLISH_DEV = REPO / "scripts" / "registry" / "publish_dev.py"
# Fixed admission/resolve clock, same date the WP06 contract suite freezes
# (never a hand-typed nanosecond literal — see the Task 1 review ruling).
NOW_NS = int(datetime(2026, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)
#: A fixed instant strictly before NOW_NS, for the dev expiry drill.
EXPIRED_AT = datetime(2026, 9, 11, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

MAIN_ROOT = load_trust_root("origin-main", REG / "keys" / "main.pub.pem")

ORIGIN_MAIN = "origin-main"
DEV_ID = "dev-local"
DEV_IMPL_PACKAGE = "dev/sim_psu"
DEV_IMPL_VERSION = "0.0.0"
ROOT_KEY: Key = (DEV_ID, DEV_IMPL_PACKAGE, DEV_IMPL_VERSION)
DESC_KEY: Key = (ORIGIN_MAIN, "benchweave/sim-psu-descriptor", "1.0.0")
PROFILE_KEY: Key = (ORIGIN_MAIN, "benchweave/dc-psu-profile", "1.0.0")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _publish(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Run the dev publisher exactly as a developer would, from the repo
    root (mirroring ``tests/integration/test_registry_dev_publish.py``)."""
    return subprocess.run(
        [sys.executable, str(PUBLISH_DEV), *args],
        cwd=REPO,
        capture_output=True,
    )


def _dev_reg(tmp_path: Path) -> Path:
    """A freshly published unsigned dev registry under ``tmp_path``."""
    reg = tmp_path / "reg"
    published = _publish("plugins/sim_psu", "--out", str(reg))
    assert published.returncode == 0, published.stderr.decode()
    return reg


def _resolver(
    reg_root: Path,
    *,
    policy: Literal["required", "dev-unsigned"] = "required",
) -> Resolver:
    """The designed mixed-policy origin map; the helper default is fail-closed.

    The dev origin's policy defaults to ``required`` (dev-posture tests opt
    in explicitly) and under ``required`` it carries the main root so the
    construction itself is well-formed.
    """
    return Resolver(
        {
            DEV_ID: OriginConfig(
                registry_id=DEV_ID,
                root=MAIN_ROOT if policy == "required" else None,
                source=LocalDirectorySource(reg_root / DEV_ID),
                namespaces=("dev",),
                signature_policy=policy,
            ),
            ORIGIN_MAIN: OriginConfig(
                registry_id=ORIGIN_MAIN,
                root=MAIN_ROOT,
                source=LocalDirectorySource(REG / ORIGIN_MAIN),
                namespaces=("benchweave",),
            ),
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


def _admit(closure: ResolvedClosure, work: Path) -> None:
    admit(
        closure,
        cache_root=work / "cache",
        lock_path=work / "packages.lock.json",
        limits=_limits(),
        approval=_approval(),
        now_ns=NOW_NS,
        roots={DEV_ID: None, ORIGIN_MAIN: MAIN_ROOT},
    )


def test_dev_unsigned_closure_resolves(tmp_path: Path) -> None:
    reg = _dev_reg(tmp_path)
    high_water: dict[Key, int] = {}
    closure = _resolver(reg, policy="dev-unsigned").resolve(
        DEV_ID, DEV_IMPL_PACKAGE, DEV_IMPL_VERSION, now_ns=NOW_NS, high_water=high_water
    )
    # The designed dev closure: the unsigned implementation over its two
    # signed origin-main dependencies.
    assert {r.package_id for r in closure.releases} == {
        DEV_IMPL_PACKAGE,
        "benchweave/sim-psu-descriptor",
        "benchweave/dc-psu-profile",
    }
    impl = next(r for r in closure.releases if r.package_id == DEV_IMPL_PACKAGE)
    # No signature was fetched for the dev release; the origin-main
    # dependencies stay signature-verified.
    assert impl.manifest_sig == b""
    assert impl.status_sig == b""
    for release in closure.releases:
        if release.registry_id == ORIGIN_MAIN:
            assert release.manifest_sig and release.status_sig
    # Digests and identity stay live: the dev manifest bytes are the
    # publisher's fresh output, pinned by the manifest sha.
    published = reg / DEV_ID / DEV_IMPL_PACKAGE / DEV_IMPL_VERSION / "manifest.json"
    assert impl.manifest_sha256 == _sha(published.read_bytes())
    # Sequence honesty stays live across the whole mixed closure.
    assert high_water == {ROOT_KEY: 1, DESC_KEY: 1, PROFILE_KEY: 1}


def test_unsigned_bytes_under_required_origin_reject(tmp_path: Path) -> None:
    reg = _dev_reg(tmp_path)
    with pytest.raises(AuthenticityRejected) as exc:
        _resolver(reg).resolve(  # fail-closed default
            DEV_ID, DEV_IMPL_PACKAGE, DEV_IMPL_VERSION, now_ns=NOW_NS, high_water={}
        )
    # A missing signature file under `required` is bad_signature, never an
    # OS error (and never misread as an unknown release).
    assert exc.value.reason == "bad_signature"


def test_required_with_none_root_rejects_at_config() -> None:
    with pytest.raises(RegistryRejected) as exc:
        OriginConfig(
            registry_id=DEV_ID,
            root=None,
            source=LocalDirectorySource(REG / "origin-main"),
            namespaces=("dev",),
            signature_policy="required",
        )
    assert exc.value.reason == "invalid_origin_config"


def test_dev_unsigned_fence_rejects_signed_identity_impersonation() -> None:
    """The fence: dev-unsigned is structurally reserved for dev- identities.

    A single-entry ``origin-main`` dev-unsigned origin — the impersonation
    the earlier revision of this file accidentally blessed — must be
    impossible to CONSTRUCT, so config assembly can never silently ship an
    inverted origin (cross-vendor audit Important).
    """
    with pytest.raises(ValueError):
        OriginConfig(
            registry_id=ORIGIN_MAIN,
            root=None,
            source=LocalDirectorySource(REG / "origin-main"),
            namespaces=("benchweave",),
            signature_policy="dev-unsigned",
        )


def test_dev_unsigned_fence_rejects_root_on_dev_unsigned() -> None:
    # dev-unsigned WITH a root is an inverted posture (nothing to verify
    # against, yet authenticity is claimed by carrying a root): reject at
    # construction, one violation at a time.
    with pytest.raises(ValueError):
        OriginConfig(
            registry_id=DEV_ID,
            root=MAIN_ROOT,
            source=LocalDirectorySource(REG / "origin-main"),
            namespaces=("dev",),
            signature_policy="dev-unsigned",
        )


def test_default_policy_is_required() -> None:
    config = OriginConfig(
        registry_id=ORIGIN_MAIN,
        root=MAIN_ROOT,
        source=LocalDirectorySource(REG / ORIGIN_MAIN),
        namespaces=("benchweave",),
    )
    assert config.signature_policy == "required"
    # Byte-identical WP06 behaviour: the signed fixture tree resolves exactly
    # as before, signatures attached.
    high_water: dict[Key, int] = {}
    closure = Resolver({ORIGIN_MAIN: config}).resolve(
        ORIGIN_MAIN, "benchweave/sim-psu", "1.0.0", now_ns=NOW_NS, high_water=high_water
    )
    assert len(closure.releases) == 3
    assert all(r.manifest_sig and r.status_sig for r in closure.releases)
    assert high_water == {
        (ORIGIN_MAIN, "benchweave/sim-psu", "1.0.0"): 1,
        DESC_KEY: 1,
        PROFILE_KEY: 1,
    }


def test_tampered_dev_payload_rejects_at_admission(tmp_path: Path) -> None:
    reg = _dev_reg(tmp_path)
    closure = _resolver(reg, policy="dev-unsigned").resolve(
        DEV_ID, DEV_IMPL_PACKAGE, DEV_IMPL_VERSION, now_ns=NOW_NS, high_water={}
    )
    releases = []
    for release in closure.releases:
        if (release.registry_id, release.package_id, release.version) == ROOT_KEY:
            payload = release.payload[:-1] + bytes([release.payload[-1] ^ 1])
            release = replace(release, payload=payload)
        releases.append(release)
    with pytest.raises(AdmissionRejected) as exc:
        _admit(ResolvedClosure(releases=tuple(releases)), tmp_path)
    # Integrity without authenticity: no signature was ever checked for the
    # dev release, and the payload still fails its declared digest at admission.
    assert exc.value.reason == "payload_digest_mismatch"
    assert not (tmp_path / "cache").exists()


def test_dev_rollback_rejects_via_persisted_high_water(tmp_path: Path) -> None:
    """The persisted rollback gate stays armed on the dev path.

    The dev root is writable without keys, so the rollback drill runs on the
    dev release itself: first install replays a hand-bumped sequence-2
    status and persists the high-water map; the origin then rolls back to
    the published sequence 1. A fresh resolver session — empty in-memory
    expectations — cannot catch it; only the persisted
    ``<cache_root>/high-water.json`` layer does.
    """
    reg = _dev_reg(tmp_path)
    status_path = reg / DEV_ID / DEV_IMPL_PACKAGE / DEV_IMPL_VERSION / "status.json"
    status = json.loads(status_path.read_bytes())
    status["sequence"] = 2
    status_path.write_bytes(_canonical(status))

    resolver = _resolver(reg, policy="dev-unsigned")
    closure = resolver.resolve(
        DEV_ID, DEV_IMPL_PACKAGE, DEV_IMPL_VERSION, now_ns=NOW_NS, high_water={}
    )
    _admit(closure, tmp_path)

    water_path = tmp_path / "cache" / "high-water.json"
    assert water_path.is_file()
    rows = {
        (row["registry_id"], row["package_id"], row["version"]): row["sequence"]
        for row in json.loads(water_path.read_bytes())["releases"]
    }
    assert rows[ROOT_KEY] == 2

    status["sequence"] = 1
    status_path.write_bytes(_canonical(status))
    rolled = resolver.resolve(
        DEV_ID, DEV_IMPL_PACKAGE, DEV_IMPL_VERSION, now_ns=NOW_NS, high_water={}
    )
    with pytest.raises(AdmissionRejected) as exc:
        _admit(rolled, tmp_path)
    assert exc.value.reason == "stale_sequence"


def test_dev_status_swap_rejects_status_release_mismatch(tmp_path: Path) -> None:
    """Wave-1 item 10: the direct dev-path pin for the status-release binding.

    Two publisher-built dev releases of one package; the 0.0.0 status file
    is dropped onto the 0.1.0 release. Both statuses are honest unsigned
    documents — no signature layer exists to refuse the swap, so only the
    binding (the status must name the release it rides AND pin the served
    manifest's digest) rejects it."""
    reg = tmp_path / "reg"
    for version in ("0.0.0", "0.1.0"):
        published = _publish("plugins/sim_psu", "--out", str(reg), "--version", version)
        assert published.returncode == 0, published.stderr.decode()
    older = reg / DEV_ID / DEV_IMPL_PACKAGE / "0.0.0" / "status.json"
    target = reg / DEV_ID / DEV_IMPL_PACKAGE / "0.1.0" / "status.json"
    shutil.copy2(older, target)
    with pytest.raises(RegistryRejected) as exc:
        _resolver(reg, policy="dev-unsigned").resolve(
            DEV_ID, DEV_IMPL_PACKAGE, "0.1.0", now_ns=NOW_NS, high_water={}
        )
    assert exc.value.reason == "status_release_mismatch"


def test_expired_dev_status_rejects(tmp_path: Path) -> None:
    """F4: expiry stays enforced on unsigned dev statuses.

    The dev root is writable, so a stale status is served by simply writing
    one — no signature exists to re-verify, the process-honesty gate itself
    must refuse it.
    """
    reg = _dev_reg(tmp_path)
    status_path = reg / DEV_ID / DEV_IMPL_PACKAGE / DEV_IMPL_VERSION / "status.json"
    status = json.loads(status_path.read_bytes())
    status["expires_at"] = EXPIRED_AT  # strictly before the fixed NOW_NS
    status_path.write_bytes(_canonical(status))
    with pytest.raises(AuthenticityRejected) as exc:
        _resolver(reg, policy="dev-unsigned").resolve(
            DEV_ID, DEV_IMPL_PACKAGE, DEV_IMPL_VERSION, now_ns=NOW_NS, high_water={}
        )
    assert exc.value.reason == "expired_status"
