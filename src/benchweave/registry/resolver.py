# src/benchweave/registry/resolver.py
"""Configured-origin package resolution: strict routing, authenticated closure.

Routing is namespace-based and exclusive: a release is served only by the
origin the caller names, and that origin must route the release's namespace
(``package_id.split("/")[0]``) — a dependency pinned to another registry is
rejected as ``cross_origin_fallback``, never redirected.
"""
from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from benchweave.registry.authenticity import TrustRoot, check_status, verify_document
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
    """Byte-level access to one origin's release files."""

    def manifest_bytes(self, package_id: str, version: str) -> tuple[bytes, str]: ...

    def status_bytes(self, package_id: str, version: str) -> tuple[bytes, str]: ...

    def payload_bytes(self, package_id: str, version: str) -> bytes: ...

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

    def payload_bytes(self, package_id: str, version: str) -> bytes:
        return self._read(package_id, version, "payload.zip")

    def manifest_signature(self, package_id: str, version: str) -> bytes:
        return self._read(package_id, version, "manifest.sig")

    def status_signature(self, package_id: str, version: str) -> bytes:
        return self._read(package_id, version, "status.sig")


@dataclass(frozen=True)
class OriginConfig:
    registry_id: str
    root: TrustRoot
    source: PackageSource
    namespaces: tuple[str, ...]


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
        releases: list[ResolvedRelease] = []
        while queue:
            key, pinned = queue.popleft()
            if key in manifests:
                continue
            release, manifest = self._resolve_release(
                key, pinned=pinned, is_root=key == start, now_ns=now_ns, high_water=high_water
            )
            manifests[key] = manifest
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
        try:
            raw, digest = source.manifest_bytes(package_id, version)
            manifest_doc = load_manifest_document(
                raw, pinned if pinned is not None else digest, max_bytes=_MANIFEST_MAX_BYTES
            )
            manifest_sig = source.manifest_signature(package_id, version)
            verify_document(manifest_doc, manifest_sig, origin.root)
            status_raw, status_digest = source.status_bytes(package_id, version)
            status_doc = load_status_document(
                status_raw, status_digest, max_bytes=_STATUS_MAX_BYTES
            )
            status_sig = source.status_signature(package_id, version)
            verify_document(status_doc, status_sig, origin.root)
            payload = source.payload_bytes(package_id, version)
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
