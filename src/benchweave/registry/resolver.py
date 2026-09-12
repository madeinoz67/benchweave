# src/benchweave/registry/resolver.py
"""Configured-origin package resolution: strict routing, authenticated closure.

Routing is namespace-based and exclusive: a release is served only by the
origin the caller names, and that origin must route the release's namespace
(``package_id.split("/")[0]``) — a dependency pinned to another registry is
rejected as ``cross_origin_fallback``, never redirected.

Payload bytes are returned as served — NOT digest-verified at resolve time;
the consumer must check them against ``manifest["payload"]["sha256"]`` (Task 6
admission owns that check).

Signature posture is per origin (``OriginConfig.signature_policy``). The
default ``"required"`` is fail-closed: manifests and statuses are verified
against the origin's trust root, and a missing signature file is
``bad_signature`` — never an OS error. ``"dev-unsigned"`` is the honest dev
posture: it skips exactly those two authenticity verifications (no signature
fetch at all, ``root`` is ``None``) while every integrity and
process-honesty check stays on — schema validation, the served-manifest
identity recheck, the status-release binding (``status_release_mismatch``:
a served status must name the requested release and pin the served
manifest's digest), dependency digest pinning, status expiry/future-time, and
monotonic sequences against the high-water view. A dev origin's status
bytes are unauthenticated by design: a local process that can write the
dev root can forge lifecycle state. That limitation is accepted and
documented, not hidden.
"""
from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from benchweave.registry.authenticity import (
    AuthenticityRejected,
    TrustRoot,
    check_status,
    verify_document,
)
from benchweave.registry.manifests import Key, check_closure
from benchweave.registry.schemas import (
    RegistryRejected,
    load_manifest_document,
    load_status_document,
)

#: Document budgets (bytes), sized for the contract-test fixture catalogue.
_MANIFEST_MAX_BYTES = 1_000_000
_STATUS_MAX_BYTES = 100_000


class PackageSource(Protocol):
    """Byte-level access to one origin's release files.

    ``payload_bytes`` may be handed ``max_archive_bytes`` by the resolver
    (threaded from :class:`OriginConfig`); sources that can cheaply know a
    payload's size MUST reject before reading it into memory.
    """

    def manifest_bytes(self, package_id: str, version: str) -> tuple[bytes, str]: ...

    def status_bytes(self, package_id: str, version: str) -> tuple[bytes, str]: ...

    def payload_bytes(
        self, package_id: str, version: str, *, max_archive_bytes: int | None = None
    ) -> bytes: ...

    def manifest_signature(self, package_id: str, version: str) -> bytes: ...

    def status_signature(self, package_id: str, version: str) -> bytes: ...


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalDirectorySource:
    """Serve the committed catalogue layout ``<root>/<package_id>/<version>/``."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _read(self, package_id: str, version: str, filename: str) -> bytes:
        return (self._root / package_id / version / filename).read_bytes()

    def _pair(self, package_id: str, version: str, filename: str) -> tuple[bytes, str]:
        raw = self._read(package_id, version, filename)
        return raw, _sha256(raw)

    def manifest_bytes(self, package_id: str, version: str) -> tuple[bytes, str]:
        return self._pair(package_id, version, "manifest.json")

    def status_bytes(self, package_id: str, version: str) -> tuple[bytes, str]:
        return self._pair(package_id, version, "status.json")

    def payload_bytes(
        self,
        package_id: str,
        version: str,
        *,
        max_archive_bytes: int | None = None,
    ) -> bytes:
        path = self._root / package_id / version / "payload.zip"
        if max_archive_bytes is not None and path.stat().st_size > max_archive_bytes:
            # Size-gated on stat alone: an oversized archive is refused
            # before it is ever read into memory. Admission's own limit
            # stays as the second, independent gate.
            raise RegistryRejected("archive_too_large")
        return self._read(package_id, version, "payload.zip")

    def manifest_signature(self, package_id: str, version: str) -> bytes:
        return self._read(package_id, version, "manifest.sig")

    def status_signature(self, package_id: str, version: str) -> bytes:
        return self._read(package_id, version, "status.sig")


@dataclass(frozen=True)
class OriginConfig:
    registry_id: str
    #: Trust root that authenticates this origin's documents; ``None`` is
    #: valid ONLY under ``signature_policy="dev-unsigned"``.
    root: TrustRoot | None
    source: PackageSource
    namespaces: tuple[str, ...]
    #: Optional origin-level payload cap handed to the source's
    #: ``payload_bytes`` so an oversized archive is refused before it is
    #: read into memory; ``None`` (the default) defers to admission's limit.
    max_archive_bytes: int | None = None
    #: Signature posture: ``"required"`` (the fail-closed default) verifies
    #: manifest and status signatures against ``root``; ``"dev-unsigned"``
    #: skips exactly those two authenticity checks.
    signature_policy: Literal["required", "dev-unsigned"] = "required"

    def __post_init__(self) -> None:
        """Identity fence: refuse an inverted posture at construction.

        ``required`` needs a trust root to authenticate with, and
        ``dev-unsigned`` is reserved for ``dev-``-prefixed origins that
        carry none — so config assembly can never silently ship an
        unsigned origin under a signed registry's identity
        (:class:`RegistryRejected` ``invalid_origin_config``, itself a
        :class:`ValueError`). The resolver's map-level check is the same
        rule one layer up (belt and braces).
        """
        if self.signature_policy == "required":
            if self.root is None:
                raise RegistryRejected("invalid_origin_config")
        elif self.root is not None or not self.registry_id.startswith("dev-"):
            raise RegistryRejected("invalid_origin_config")


@dataclass(frozen=True)
class ResolvedRelease:
    manifest: dict[str, Any]
    manifest_sha256: str
    status: dict[str, Any]
    payload: bytes
    manifest_sig: bytes
    status_sig: bytes
    registry_id: str
    package_id: str
    version: str


@dataclass(frozen=True)
class ResolvedClosure:
    releases: tuple[ResolvedRelease, ...]


class Resolver:
    """Resolve dependency closures from configured origins under strict routing."""

    def __init__(self, origins: Mapping[str, OriginConfig]) -> None:
        for cfg in origins.values():
            if cfg.signature_policy == "required" and cfg.root is None:
                # Fail-closed: an origin that must authenticate has no root
                # to authenticate with.
                raise RegistryRejected("invalid_origin_config")
        self._origins: dict[str, OriginConfig] = dict(origins)

    def _origin_for(self, registry_id: str, package_id: str) -> OriginConfig:
        namespace = package_id.split("/")[0]
        if not any(namespace in o.namespaces for o in self._origins.values()):
            raise RegistryRejected("unrouted_namespace")
        origin = self._origins.get(registry_id)
        if origin is None or namespace not in origin.namespaces:
            raise RegistryRejected("cross_origin_fallback")
        return origin

    def resolve(
        self,
        registry_id: str,
        package_id: str,
        version: str,
        *,
        now_ns: int,
        high_water: MutableMapping[Key, int],
    ) -> ResolvedClosure:
        start: Key = (registry_id, package_id, version)
        # Queue entries carry the manifest digest pinned by the dependent (None for the root).
        queue: deque[tuple[Key, str | None]] = deque([(start, None)])
        manifests: dict[Key, dict[str, Any]] = {}
        digests: dict[Key, str] = {}
        releases: list[ResolvedRelease] = []
        while queue:
            key, pinned = queue.popleft()
            if key in manifests:
                # A revisited key is only sound when every dependent agrees on
                # the digest: digest disagreements are errors, never last-wins.
                if pinned is not None and pinned != digests[key]:
                    raise RegistryRejected("digest_disagreement")
                continue
            release, manifest = self._resolve_release(
                key, pinned=pinned, is_root=key == start, now_ns=now_ns, high_water=high_water
            )
            manifests[key] = manifest
            digests[key] = release.manifest_sha256
            releases.append(release)
            for dep in manifest["dependencies"]:
                dep_key: Key = (dep["registry_id"], dep["package_id"], dep["version"])
                queue.append((dep_key, dep["manifest_sha256"]))
        check_closure(manifests)
        return ResolvedClosure(releases=tuple(releases))

    def _resolve_release(
        self,
        key: Key,
        *,
        pinned: str | None,
        is_root: bool,
        now_ns: int,
        high_water: MutableMapping[Key, int],
    ) -> tuple[ResolvedRelease, dict[str, Any]]:
        registry_id, package_id, version = key
        origin = self._origin_for(registry_id, package_id)
        source = origin.source
        root = origin.root  # TrustRoot under `required` (validated at __init__)
        try:
            raw, digest = source.manifest_bytes(package_id, version)
            manifest_doc = load_manifest_document(
                raw, pinned if pinned is not None else digest, max_bytes=_MANIFEST_MAX_BYTES
            )
            if origin.signature_policy == "dev-unsigned":
                # Honest dev posture: no signature fetch, no verify call —
                # the release records the absence instead of faking bytes.
                manifest_sig = b""
            else:
                if root is None:
                    # Unreachable past __init__ validation; keeps the verify
                    # call below typed against a real root.
                    raise RegistryRejected("invalid_origin_config")
                try:
                    manifest_sig = source.manifest_signature(package_id, version)
                except FileNotFoundError as exc:
                    # A missing signature is bad authenticity, not a missing
                    # release: under `required` the signature is part of the
                    # release, never an optional extra file.
                    raise AuthenticityRejected("bad_signature") from exc
                verify_document(manifest_doc, manifest_sig, root)
            # The signature proves the bytes are authentic, not that they are
            # the release asked for: recheck the manifest's self-declared
            # identity against the requested key (contract §6/§10).
            declared = (
                manifest_doc.content["registry_id"],
                manifest_doc.content["package_id"],
                manifest_doc.content["version"],
            )
            if declared != key:
                raise RegistryRejected("identity_mismatch")
            status_raw, status_digest = source.status_bytes(package_id, version)
            status_doc = load_status_document(
                status_raw, status_digest, max_bytes=_STATUS_MAX_BYTES
            )
            if origin.signature_policy == "dev-unsigned":
                status_sig = b""
            else:
                if root is None:
                    raise RegistryRejected("invalid_origin_config")
                try:
                    status_sig = source.status_signature(package_id, version)
                except FileNotFoundError as exc:
                    raise AuthenticityRejected("bad_signature") from exc
                verify_document(status_doc, status_sig, root)
            # The status signature proves the bytes are authentic, not that
            # they describe THIS release: bind the served status to the
            # release it accompanies — its release block must name the
            # requested key AND pin the served manifest digest (contract
            # §6/§10). A validly-signed status swapped between release
            # directories rejects as ``status_release_mismatch`` here, so a
            # foreign "published" status cannot mask a real revocation.
            status_release = status_doc.content["release"]
            if (
                status_release["registry_id"],
                status_release["package_id"],
                status_release["version"],
            ) != key or status_release["manifest_sha256"] != manifest_doc.sha256:
                raise RegistryRejected("status_release_mismatch")
            payload = source.payload_bytes(
                package_id, version, max_archive_bytes=origin.max_archive_bytes
            )
        except FileNotFoundError as exc:
            reason = "unknown_release" if is_root else "missing_dependency"
            raise RegistryRejected(reason) from exc
        sequence = check_status(
            status_doc.content, root=origin.root, now_ns=now_ns, high_water=high_water
        )
        high_water[key] = sequence
        release = ResolvedRelease(
            manifest=manifest_doc.content,
            manifest_sha256=manifest_doc.sha256,
            status=status_doc.content,
            payload=payload,
            manifest_sig=manifest_sig,
            status_sig=status_sig,
            registry_id=registry_id,
            package_id=package_id,
            version=version,
        )
        return release, manifest_doc.content
