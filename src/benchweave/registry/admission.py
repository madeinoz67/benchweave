# src/benchweave/registry/admission.py
"""Local admission: lifecycle gates, verified extraction, package lock.

Admission turns an authenticated, resolved closure into local, verified state:
extracted payload bytes in a content-addressed cache, an explicit package lock
at a caller-supplied path, and a local admission record binding the two. The
sequence is normative (each step runs for the whole closure before the next):

1. **Lifecycle gate** — any release status ``revoked`` or ``yanked`` rejects
   before anything is written. Every status is then re-checked through
   :func:`~benchweave.registry.authenticity.check_status` with the admission
   clock, so a closure resolved earlier cannot be admitted after its statuses
   expired (``expired_status``) or against a regressing sequence view
   (``stale_sequence``); resolve already enforces both, admission re-checks
   to stay honest on re-admission paths.
2. **Limits gate** — archive size and manifest file count are checked against
   :class:`AdmissionLimits` BEFORE extraction, as is the declared unpacked
   total (``archive_too_large`` / ``too_many_files`` / ``unpacked_too_large``).
3. **Verified extraction** — the archive digest AND the declared archive size
   are verified against the actual payload bytes before any extraction
   (``payload_digest_mismatch``); every zip member's name re-runs the §4 path
   rules and its type is asserted regular (symlinks and other non-regular
   members are ``path_unsafe``; regular-file writes cannot create links);
   each member is read bounded by its declared size and verified against the
   manifest inventory (``extra_file`` / ``file_hash_mismatch``); the actual
   unpacked total is re-checked against the limit. Only verified bytes are
   written, via a staging directory, under ``cache_root/<manifest_sha256>/``.
4. **Package lock** — canonical JSON (sorted keys, compact separators,
   trailing newline — mirroring the fixture builder), validated through
   :func:`~benchweave.registry.schemas.load_lock_document` before being
   written to the caller-supplied ``lock_path``.
5. **Local admission record** — ``lock_path`` with the ``.admission.json``
   suffix, binding the lock digest, the manifest digests and the cache paths;
   a local record, never uploaded.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import stat
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchweave.registry.authenticity import (
    AuthenticityRejected,
    TrustRoot,
    check_status,
)
from benchweave.registry.manifests import Key
from benchweave.registry.resolver import ResolvedClosure, ResolvedRelease
from benchweave.registry.schemas import load_lock_document

#: Document budget for the generated package lock (bytes).
_LOCK_MAX_BYTES = 1_000_000

#: Authenticity reasons admission translates into its own rejections. Any other
#: reason (``future_updated_at`` today) propagates unchanged so the layer that
#: owns the failure stays visible at the call site.
_WRAPPED_STATUS_REASONS = frozenset({"expired_status", "stale_sequence"})


class AdmissionRejected(ValueError):
    """Admission refused; ``reason`` names the gate that refused it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class AdmissionLimits:
    """Extraction budgets, enforced before and during extraction."""

    max_archive_bytes: int
    max_files: int
    max_unpacked_bytes: int

    def __post_init__(self) -> None:
        for name in ("max_archive_bytes", "max_files", "max_unpacked_bytes"):
            object.__setattr__(self, name, max(1, getattr(self, name)))


@dataclass(frozen=True)
class Approval:
    """The local principal approval recorded in the package lock."""

    principal_id: str
    approved_at: str
    policy_id: str
    policy_version: str


@dataclass(frozen=True)
class Admitted:
    """One admitted closure: its lock and the digests that pin it."""

    lock_path: Path
    lock_sha256: str
    manifest_sha256s: tuple[str, ...]


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _release_key(release: ResolvedRelease) -> Key:
    return (release.registry_id, release.package_id, release.version)


def _release_row(release: ResolvedRelease) -> dict[str, str]:
    return {
        "registry_id": release.registry_id,
        "package_id": release.package_id,
        "version": release.version,
        "manifest_sha256": release.manifest_sha256,
    }


def _gate_lifecycle(
    closure: ResolvedClosure, *, now_ns: int, roots: Mapping[str, TrustRoot]
) -> None:
    """Step 1: lifecycle and status re-check, before anything is written."""
    water: dict[Key, int] = {}
    for release in closure.releases:
        lifecycle = release.status["lifecycle"]
        if lifecycle == "revoked":
            raise AdmissionRejected("revoked")
        if lifecycle == "yanked":
            raise AdmissionRejected("yanked")
        try:
            sequence = check_status(
                release.status,
                root=roots[release.registry_id],
                now_ns=now_ns,
                high_water=water,
            )
        except AuthenticityRejected as exc:
            if exc.reason in _WRAPPED_STATUS_REASONS:
                raise AdmissionRejected(exc.reason) from exc
            raise
        water[_release_key(release)] = sequence


def _gate_limits(closure: ResolvedClosure, limits: AdmissionLimits) -> None:
    """Step 2: declared budgets vs limits, BEFORE any extraction."""
    for release in closure.releases:
        declared = release.manifest["payload"]
        if len(release.payload) > limits.max_archive_bytes:
            raise AdmissionRejected("archive_too_large")
        files = declared["files"]
        if len(files) > limits.max_files:
            raise AdmissionRejected("too_many_files")
        if sum(entry["bytes"] for entry in files) > limits.max_unpacked_bytes:
            raise AdmissionRejected("unpacked_too_large")


def _member_path_unsafe(name: str) -> bool:
    """The §4 path rules from ``manifests._check_payload_paths``, on real names."""
    return name.startswith("/") or ".." in name.split("/") or "\\" in name


def _verify_members(release: ResolvedRelease, limits: AdmissionLimits) -> dict[str, bytes]:
    """Step 3 (verification half): archive and member checks, all in memory."""
    declared = release.manifest["payload"]
    if declared["sha256"] != _sha256(release.payload):
        raise AdmissionRejected("payload_digest_mismatch")
    if declared["bytes"] != len(release.payload):
        raise AdmissionRejected("payload_digest_mismatch")
    inventory: dict[str, dict[str, Any]] = {entry["path"]: entry for entry in declared["files"]}
    verified: dict[str, bytes] = {}
    unpacked = 0
    with zipfile.ZipFile(io.BytesIO(release.payload)) as archive:
        for info in archive.infolist():
            name = info.filename
            if _member_path_unsafe(name):
                raise AdmissionRejected("path_unsafe")
            mode = info.external_attr >> 16
            # File-type field only: zip writers commonly store permission bits
            # without S_IFREG (the builder's members are 0o600), so an absent
            # type is regular by construction — but a declared symlink,
            # directory or device type is never admitted.
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise AdmissionRejected("path_unsafe")
            entry = inventory.get(name)
            if entry is None:
                raise AdmissionRejected("extra_file")
            # Bounded read: a member cannot deliver more than it declares.
            with archive.open(info) as member:
                data = member.read(entry["bytes"] + 1)
            if len(data) != entry["bytes"] or _sha256(data) != entry["sha256"]:
                raise AdmissionRejected("file_hash_mismatch")
            unpacked += len(data)
            if unpacked > limits.max_unpacked_bytes:
                raise AdmissionRejected("unpacked_too_large")
            verified[name] = data
    if set(inventory) - set(verified):
        # A listed file with no archive member fails its bytes-and-hash match.
        raise AdmissionRejected("file_hash_mismatch")
    return verified


def _write_members(
    release: ResolvedRelease, members: Mapping[str, bytes], *, cache_root: Path
) -> Path:
    """Step 3 (write half): verified bytes into ``cache_root/<manifest_sha256>/``."""
    target = cache_root / release.manifest_sha256
    if target.is_dir():
        # Content-addressed: same digest, same bytes — nothing to redo.
        return target
    staging = cache_root / f".{release.manifest_sha256}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for name in sorted(members):
        out = staging / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(members[name])
    staging.rename(target)
    return target


def _root_releases(closure: ResolvedClosure) -> tuple[ResolvedRelease, ...]:
    """Closure releases no other closure release depends on (the resolve start).

    A ``Resolver`` closure is a finite DAG from exactly one start key, so this
    derivation yields that key; it keeps ``admit`` free of a redundant
    root parameter. Sorted for a deterministic lock.
    """
    depended: set[Key] = set()
    for release in closure.releases:
        for dep in release.manifest["dependencies"]:
            depended.add((dep["registry_id"], dep["package_id"], dep["version"]))
    roots = [r for r in closure.releases if _release_key(r) not in depended]
    return tuple(sorted(roots, key=_release_key))


def _lock_document(closure: ResolvedClosure, approval: Approval) -> bytes:
    """Step 4: canonical, schema-validated lock bytes (validated before use)."""
    roots = _root_releases(closure)
    packages = sorted(closure.releases, key=_release_key)
    lock = {
        "lock_version": "1.0.0",
        "created_at": roots[0].status["updated_at"],
        "roots": [_release_row(r) for r in roots],
        "packages": [_release_row(r) for r in packages],
        "approval": {
            "principal_id": approval.principal_id,
            "approved_at": approval.approved_at,
            "policy_id": approval.policy_id,
            "policy_version": approval.policy_version,
        },
    }
    raw = _canonical(lock)
    load_lock_document(raw, _sha256(raw), max_bytes=_LOCK_MAX_BYTES)
    return raw


def admit(
    closure: ResolvedClosure,
    *,
    cache_root: Path,
    lock_path: Path,
    limits: AdmissionLimits,
    approval: Approval,
    now_ns: int,
    roots: Mapping[str, TrustRoot],
) -> Admitted:
    """Admit a resolved closure: gate, verify, extract, lock, record.

    ``now_ns`` is the admission clock and ``roots`` maps each release's
    ``registry_id`` to the trust root that authenticated it — both feed the
    step-1 status re-check, and ``roots`` must cover every registry id present
    in the closure. ``cache_root`` and ``lock_path`` are caller-supplied and
    are only touched after every gate has passed. Raises
    :class:`AdmissionRejected` with the refusing gate's reason.
    """
    _gate_lifecycle(closure, now_ns=now_ns, roots=roots)
    _gate_limits(closure, limits)
    # Verify every release before writing any: a member failure anywhere
    # leaves the cache untouched, not partially populated.
    members = [(release, _verify_members(release, limits)) for release in closure.releases]
    for release, verified in members:
        _write_members(release, verified, cache_root=cache_root)
    lock_raw = _lock_document(closure, approval)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_bytes(lock_raw)
    lock_sha256 = _sha256(lock_raw)
    manifest_sha256s = tuple(sorted(r.manifest_sha256 for r in closure.releases))
    record = {
        "lock_sha256": lock_sha256,
        "manifest_sha256s": list(manifest_sha256s),
        "cache_paths": [str(cache_root / sha) for sha in manifest_sha256s],
    }
    lock_path.with_suffix(".admission.json").write_bytes(_canonical(record))
    return Admitted(
        lock_path=lock_path,
        lock_sha256=lock_sha256,
        manifest_sha256s=manifest_sha256s,
    )
