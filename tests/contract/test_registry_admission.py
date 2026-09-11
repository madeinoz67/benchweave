# tests/contract/test_registry_admission.py
"""Admission: lifecycle gates, verified extraction, package lock, local record."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from benchweave.registry.admission import (
    AdmissionLimits,
    AdmissionRejected,
    Admitted,
    Approval,
    admit,
)
from benchweave.registry.authenticity import AuthenticityRejected, load_trust_root
from benchweave.registry.resolver import (
    LocalDirectorySource,
    OriginConfig,
    PackageSource,
    ResolvedClosure,
    Resolver,
)
from benchweave.registry.schemas import load_lock_document

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "fixtures/registry"
NOW = int(datetime(2026, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)
AFTER_EXPIRY_NS = int(datetime(2027, 9, 12, tzinfo=UTC).timestamp() * 1_000_000_000)
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)

MAIN_ROOT = load_trust_root("origin-main", REG / "keys" / "main.pub.pem")
LOCK_MAX_BYTES = 1_000_000


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
    """In-test PackageSource: fixture catalogue plus re-signed status overrides."""

    base: LocalDirectorySource
    statuses: dict[tuple[str, str], tuple[bytes, bytes]] = field(default_factory=dict)

    def manifest_bytes(self, package_id: str, version: str) -> tuple[bytes, str]:
        raw = self.base.manifest_bytes(package_id, version)[0]
        return raw, _sha(raw)

    def status_bytes(self, package_id: str, version: str) -> tuple[bytes, str]:
        pair = self.statuses.get((package_id, version))
        if pair is None:
            raw = self.base.status_bytes(package_id, version)[0]
            return raw, _sha(raw)
        return pair[0], _sha(pair[0])

    def payload_bytes(self, package_id: str, version: str) -> bytes:
        return self.base.payload_bytes(package_id, version)

    def manifest_signature(self, package_id: str, version: str) -> bytes:
        return self.base.manifest_signature(package_id, version)

    def status_signature(self, package_id: str, version: str) -> bytes:
        pair = self.statuses.get((package_id, version))
        if pair is None:
            return self.base.status_signature(package_id, version)
        return pair[1]


def _resolve(source: PackageSource | None = None) -> ResolvedClosure:
    origins: dict[str, OriginConfig] = {
        "origin-main": OriginConfig(
            registry_id="origin-main",
            root=MAIN_ROOT,
            source=source if source is not None else LocalDirectorySource(REG / "origin-main"),
            namespaces=("benchweave",),
        )
    }
    return Resolver(origins).resolve(
        "origin-main", "benchweave/sim-psu", "1.0.0", now_ns=NOW, high_water={}
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
    *,
    now_ns: int = NOW,
    limits: AdmissionLimits | None = None,
) -> Admitted:
    return admit(
        closure,
        cache_root=work / "cache",
        lock_path=work / "packages.lock.json",
        limits=limits if limits is not None else _limits(),
        approval=_approval(),
        now_ns=now_ns,
        roots={"origin-main": MAIN_ROOT},
    )


def _drop_in_fault(origin: Path, fault: str) -> None:
    """Copy the committed origin tree, then overlay a fault status drop-in."""
    shutil.copytree(REG / "origin-main", origin)
    fault_dir = REG / "faults" / fault / "benchweave/sim-psu-descriptor/1.0.0"
    target = origin / "benchweave/sim-psu-descriptor/1.0.0"
    shutil.copy2(fault_dir / "status.json", target / "status.json")
    shutil.copy2(fault_dir / "status.sig", target / "status.sig")


def _members_of(payload: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return [(info.filename, archive.read(info.filename)) for info in archive.infolist()]


def _zip_bytes(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in members:
            info = zipfile.ZipInfo(path, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return buf.getvalue()


def _with_sim_psu_payload(
    closure: ResolvedClosure,
    members: list[tuple[str, bytes]],
    *,
    fix_entry_sizes: bool,
) -> ResolvedClosure:
    """Rebuild sim-psu with a new archive and an archive-consistent manifest.

    The archive-level declaration (sha256 and bytes) is always fixed up, so the
    failure under test sits at the member layer unless a test breaks it there.
    """
    releases = []
    for release in closure.releases:
        if release.package_id != "benchweave/sim-psu":
            releases.append(release)
            continue
        payload = _zip_bytes(members)
        manifest = json.loads(_canonical(release.manifest))
        manifest["payload"]["sha256"] = _sha(payload)
        manifest["payload"]["bytes"] = len(payload)
        if fix_entry_sizes:
            sizes = {path: len(data) for path, data in members}
            for entry in manifest["payload"]["files"]:
                entry["bytes"] = sizes[entry["path"]]
        releases.append(replace(release, manifest=manifest, payload=payload))
    return ResolvedClosure(releases=tuple(releases))


def _sim_psu(closure: ResolvedClosure) -> Any:
    return next(r for r in closure.releases if r.package_id == "benchweave/sim-psu")


def test_admit_happy_path(tmp_path: Path) -> None:
    closure = _resolve()
    admitted = _admit(closure, tmp_path)
    shas = {r.package_id: r.manifest_sha256 for r in closure.releases}

    # Lock: written bytes are canonical, digest-pinned and schema-valid.
    lock_bytes = admitted.lock_path.read_bytes()
    assert lock_bytes == _canonical(json.loads(lock_bytes))
    assert _sha(lock_bytes) == admitted.lock_sha256
    lock = load_lock_document(lock_bytes, _sha(lock_bytes), max_bytes=LOCK_MAX_BYTES)
    assert lock.content["lock_version"] == "1.0.0"
    assert lock.content["created_at"] == "2026-09-11T00:00:00Z"
    assert lock.content["roots"] == [
        {
            "registry_id": "origin-main",
            "package_id": "benchweave/sim-psu",
            "version": "1.0.0",
            "manifest_sha256": shas["benchweave/sim-psu"],
        }
    ]
    assert lock.content["packages"] == [
        {
            "registry_id": r.registry_id,
            "package_id": r.package_id,
            "version": r.version,
            "manifest_sha256": r.manifest_sha256,
        }
        for r in sorted(
            closure.releases, key=lambda r: (r.registry_id, r.package_id, r.version)
        )
    ]
    assert lock.content["approval"] == {
        "principal_id": "benchweave-test",
        "approved_at": "2026-09-12T00:00:00Z",
        "policy_id": "local-policy",
        "policy_version": "1.0.0",
    }

    # Cache: one content-addressed directory per release, payload extracted.
    cache_root = tmp_path / "cache"
    assert sorted(p.name for p in cache_root.iterdir()) == sorted(shas.values())
    plugin = cache_root / shas["benchweave/sim-psu"] / "plugin" / "plugin.py"
    assert plugin.read_bytes() == (REPO / "plugins/sim_psu/plugin.py").read_bytes()

    # Local admission record binds lock digest, manifest digests, cache paths.
    record_path = tmp_path / "packages.lock.admission.json"
    assert record_path.is_file()
    record = json.loads(record_path.read_bytes())
    assert record["lock_sha256"] == admitted.lock_sha256
    assert record["manifest_sha256s"] == list(admitted.manifest_sha256s)
    assert record["cache_paths"] == [str(cache_root / s) for s in admitted.manifest_sha256s]

    # manifest_sha256s is the sorted, stable tuple Task 8 reuses.
    assert admitted.manifest_sha256s == tuple(sorted(shas.values()))
    # Re-admission of the same closure is idempotent and byte-identical.
    again = _admit(closure, tmp_path)
    assert again.lock_sha256 == admitted.lock_sha256
    assert again.manifest_sha256s == admitted.manifest_sha256s


def test_lock_deterministic_across_admissions(tmp_path: Path) -> None:
    closure = _resolve()
    first = _admit(closure, tmp_path / "a")
    second = _admit(closure, tmp_path / "b")
    assert first.lock_sha256 == second.lock_sha256
    assert first.lock_path.read_bytes() == second.lock_path.read_bytes()


def test_revoked_rejected_before_any_cache(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    _drop_in_fault(origin, "revoked")
    closure = _resolve(LocalDirectorySource(origin))
    with pytest.raises(AdmissionRejected) as exc:
        _admit(closure, tmp_path)
    assert exc.value.reason == "revoked"
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "packages.lock.json").exists()


def test_yanked_rejected_before_any_cache(tmp_path: Path) -> None:
    status = json.loads(
        (REG / "origin-main/benchweave/sim-psu-descriptor/1.0.0/status.json").read_bytes()
    )
    status["lifecycle"] = "yanked"
    status["reason"] = "fixture yank"
    raw = _canonical(status)
    source = _OverlaySource(
        base=LocalDirectorySource(REG / "origin-main"),
        statuses={("benchweave/sim-psu-descriptor", "1.0.0"): (raw, _sign_with_main(raw))},
    )
    closure = _resolve(source)
    with pytest.raises(AdmissionRejected) as exc:
        _admit(closure, tmp_path)
    assert exc.value.reason == "yanked"
    assert not (tmp_path / "cache").exists()


def test_expired_rejected_at_resolve_layer(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    _drop_in_fault(origin, "expired")
    # Layering: the resolver's own check_status rejects before admission runs.
    with pytest.raises(AuthenticityRejected) as exc:
        _resolve(LocalDirectorySource(origin))
    assert exc.value.reason == "expired_status"


def test_expired_status_rechecked_at_admission(tmp_path: Path) -> None:
    closure = _resolve()  # statuses are unexpired at NOW
    # Re-admission honesty: admit later than the statuses' expiry.
    with pytest.raises(AdmissionRejected) as exc:
        _admit(closure, tmp_path, now_ns=AFTER_EXPIRY_NS)
    assert exc.value.reason == "expired_status"
    assert not (tmp_path / "cache").exists()


def test_tampered_payload_digest_mismatch_cache_untouched(tmp_path: Path) -> None:
    closure = _resolve()
    releases = []
    for release in closure.releases:
        if release.package_id != "benchweave/sim-psu":
            releases.append(release)
            continue
        payload = release.payload[:-1] + bytes([release.payload[-1] ^ 1])
        releases.append(replace(release, payload=payload))
    with pytest.raises(AdmissionRejected) as exc:
        _admit(ResolvedClosure(releases=tuple(releases)), tmp_path)
    assert exc.value.reason == "payload_digest_mismatch"
    assert not (tmp_path / "cache").exists()


def test_extra_zip_member_rejected(tmp_path: Path) -> None:
    closure = _resolve()
    members = _members_of(_sim_psu(closure).payload) + [("extra.txt", b"unsigned\n")]
    mutated = _with_sim_psu_payload(closure, members, fix_entry_sizes=False)
    with pytest.raises(AdmissionRejected) as exc:
        _admit(mutated, tmp_path)
    assert exc.value.reason == "extra_file"
    assert not (tmp_path / "cache").exists()


def test_member_hash_mismatch_rejected(tmp_path: Path) -> None:
    closure = _resolve()
    members = [
        (path, data + b"# tampered\n") if path == "plugin/plugin.py" else (path, data)
        for path, data in _members_of(_sim_psu(closure).payload)
    ]
    mutated = _with_sim_psu_payload(closure, members, fix_entry_sizes=True)
    with pytest.raises(AdmissionRejected) as exc:
        _admit(mutated, tmp_path)
    assert exc.value.reason == "file_hash_mismatch"
    assert not (tmp_path / "cache").exists()


def test_missing_member_rejected(tmp_path: Path) -> None:
    closure = _resolve()
    members = [(p, d) for p, d in _members_of(_sim_psu(closure).payload) if p != "LICENSE"]
    mutated = _with_sim_psu_payload(closure, members, fix_entry_sizes=False)
    with pytest.raises(AdmissionRejected) as exc:
        _admit(mutated, tmp_path)
    assert exc.value.reason == "file_hash_mismatch"
    assert not (tmp_path / "cache").exists()


def test_limits_all_ones_archive_too_large_before_extraction(tmp_path: Path) -> None:
    closure = _resolve()
    tight = AdmissionLimits(max_archive_bytes=1, max_files=1, max_unpacked_bytes=1)
    with pytest.raises(AdmissionRejected) as exc:
        _admit(closure, tmp_path, limits=tight)
    assert exc.value.reason == "archive_too_large"
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "packages.lock.json").exists()


def test_file_count_limit_before_extraction(tmp_path: Path) -> None:
    closure = _resolve()
    tight = AdmissionLimits(max_archive_bytes=1_000_000, max_files=1, max_unpacked_bytes=1_000_000)
    with pytest.raises(AdmissionRejected) as exc:
        _admit(closure, tmp_path, limits=tight)
    assert exc.value.reason == "too_many_files"
    assert not (tmp_path / "cache").exists()


def test_unpacked_limit_before_extraction(tmp_path: Path) -> None:
    closure = _resolve()
    tight = AdmissionLimits(max_archive_bytes=1_000_000, max_files=100, max_unpacked_bytes=1)
    with pytest.raises(AdmissionRejected) as exc:
        _admit(closure, tmp_path, limits=tight)
    assert exc.value.reason == "unpacked_too_large"
    assert not (tmp_path / "cache").exists()
