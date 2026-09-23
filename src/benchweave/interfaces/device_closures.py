"""Run-time resolution of a bench device's commissioned OTDP closure (issue #167).

The design of record (``.claude/deep-review/2026-09-23-issue167-run-engine-
activation-design.md``, Decision 1) pins the authority chain: a run may
construct a bridge for an adapter-mode bench device only from the bench's
**admitted closure**, and the linkage is the bench device's declared
``generation`` — the activation record the admin act wrote for exactly that
generation is the commissioning evidence (A11: a downloaded package is data
until commissioned locally; the closure WAS commissioned by the admin act).

This module resolves that chain WITHOUT inventing a second admission path
(the design's DON'T-BUILD line): it reads the admitted state the admin flow
already produced —

* the activation record ``<records_dir>/<bench_id>/activation-<n>.json``
  (``registry.activation.activate``), binding the commissioned generation to
  the package-lock digest;
* the package lock at the session's ``lock_path``, whose ``packages[]`` rows
  carry every closure release's coordinates and manifest digest;
* each release's manifest bytes, read through the resolver's own origin
  sources and digest-verified against the lock row (the manifest re-read is
  pinned by the lock, not re-trusted: admission verified authenticity when
  the closure was admitted, and the digest pin makes any registry drift a
  hard mismatch — the resolver itself cannot be reused here because its
  strictly-advancing high-water fence refuses a second resolve of the same
  release sequences, by design);
* the admission cache at ``<cache_root>/<manifest_sha256>/`` (the loader
  re-verifies every payload byte against the manifest inventory anyway).

A device whose generation has NO activation record returns ``None`` — that
is the demo-lattice declarative fallback's discriminator, not an error: the
startup-admitted generation was never commissioned through the registry
admin act, so its devices keep the committed sim plugins (disclosed loudly
by the caller). An INCONSISTENT commissioned state (record without lock,
lock digest drift, a closure that does not serve the device's pinned
descriptor digest, a missing cache) raises
:class:`ClosureResolutionError` — the run refuses rather than silently
substituting a different device implementation than the one commissioned.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from benchweave.interfaces.bootstrap import RegistrySession

#: Manifest inventory roles the resolution reads.
_DESCRIPTOR_ROLE = "descriptor"
_IMPLEMENTATION_ROLE = "implementation"


class ClosureResolutionError(ValueError):
    """The commissioned state is inconsistent; the message names the break.

    Every message is machine-prefixed (``closure_*``) so a refused run's
    poison-guard log line is greppable.
    """


@dataclass(frozen=True)
class DeviceClosure:
    """One commissioned device's bridge construction inputs."""

    cache_root: Path
    manifest: dict[str, Any]
    manifest_sha256: str
    entry_relpath: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _module_components(path: str, code_paths: set[str]) -> list[str]:
    """The dotted module a payload file implements, its package chain stripped.

    Mirrors the bundle loader's walk exactly: the contiguous ``__init__.py``
    chain above the file is walked to its TOP, that top directory becomes
    the import root, and the module is everything below it plus the stem —
    ``plugin/plugin.py`` (with ``plugin/__init__.py``) implements module
    ``plugin``; ``a/b/c.py`` over packages ``a``/``a/b`` implements ``b.c``.
    """
    pure = PurePosixPath(path)
    directories = list(pure.parts[:-1])
    top = len(directories)
    while top > 0 and str(PurePosixPath(*directories[:top]) / "__init__.py") in code_paths:
        top -= 1
    if pure.stem == "__init__":
        return directories[top + 1:]
    return [*directories[top + 1:], pure.stem]


def _entry_relpath(entry_point: str, manifest: dict[str, Any]) -> str:
    """Derive the payload entry file from the descriptor's entry point.

    The OTDP spec pins the form ``package.module:create_plugin``; the bundle
    loader imports a module whose dotted path is the file's package-stripped
    position. The derivation therefore matches the entry module's trailing
    components against every implementation file's module path and requires
    exactly ONE match — a payload whose layout makes the entry ambiguous is
    a packaging defect, refused loudly rather than guessed.
    """
    module, separator, _factory = entry_point.partition(":")
    if not separator or not module:
        raise ClosureResolutionError(
            f"closure_entry_invalid: entry point {entry_point!r} is not module:factory"
        )
    files = manifest["payload"]["files"]
    code_paths = {
        str(file["path"])
        for file in files
        if file.get("role") == _IMPLEMENTATION_ROLE and str(file["path"]).endswith(".py")
    }
    components = module.split(".")
    matches: list[str] = []
    for path in sorted(code_paths):
        file_module = _module_components(path, code_paths)
        if file_module and file_module == components[-len(file_module):]:
            matches.append(path)
    if len(matches) != 1:
        raise ClosureResolutionError(
            "closure_entry_ambiguous: entry point "
            f"{entry_point!r} matches implementation files {matches} — exactly one is required"
        )
    return matches[0]


def commissioned_device_closure(
    session: RegistrySession | None,
    bench_id: str,
    device: dict[str, Any],
    descriptor: dict[str, Any],
) -> DeviceClosure | None:
    """Resolve the commissioned closure for one bench device, or ``None``.

    ``None`` means "no admin act commissioned a closure for this device's
    declared generation" — the caller's declarative-fallback discriminator.
    Everything else about the commissioned state is verified or raises.
    ``descriptor`` is the device's RAW full-form descriptor document (the
    same bytes the bench pins by digest); its ``integration.adapter``
    block names the entry point the payload must serve.
    """
    if session is None:
        return None
    generation = device.get("generation")
    if not isinstance(generation, int) or generation < 1:
        raise ClosureResolutionError(
            f"closure_generation_invalid: bench {bench_id} device "
            f"{device.get('id')!r} declares no usable generation"
        )
    record_path = session.records_dir / bench_id / f"activation-{generation}.json"
    if not record_path.is_file():
        # Not commissioned by an admin act at this generation: the honest
        # None — the declarative fallback's discriminator.
        return None
    record = json.loads(record_path.read_bytes())
    if not session.lock_path.is_file():
        raise ClosureResolutionError(
            f"closure_lock_absent: activation record {record_path} exists but "
            f"the admitted package lock {session.lock_path} does not"
        )
    lock_raw = session.lock_path.read_bytes()
    if _sha256(lock_raw) != str(record.get("lock_sha256")):
        raise ClosureResolutionError(
            "closure_lock_drift: the session's current package lock is not the "
            f"one commissioned for bench {bench_id} generation {generation}"
        )
    lock = json.loads(lock_raw)
    rows: dict[tuple[str, str, str], dict[str, Any]] = {
        (str(row["registry_id"]), str(row["package_id"]), str(row["version"])): row
        for row in lock.get("packages", [])
    }
    if not rows:
        raise ClosureResolutionError(
            f"closure_lock_empty: the admitted lock {session.lock_path} names no packages"
        )
    manifests: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, row in sorted(rows.items()):
        registry_id, package_id, version = key
        source = session.resolver.origin_source(registry_id)
        if source is None:
            raise ClosureResolutionError(
                f"closure_origin_unknown: lock row {key} names an origin the "
                "session does not route"
            )
        # The registry chain pins RAW served-byte digests (load_document
        # verifies expected_sha256 over the exact bytes — CON-1's exact-byte
        # decoder); a content-identical manifest formatted differently from
        # the canonical form admits, so the resolution compares the SERVED
        # raw digest (F4), never a canonical re-encode that only coincides
        # with the pin when registries format canonically.
        raw, served_digest = source.manifest_bytes(package_id, version)
        manifest = json.loads(raw)
        if served_digest != str(row.get("manifest_sha256")):
            raise ClosureResolutionError(
                "closure_manifest_drift: the served manifest for "
                f"{key} does not match the admitted lock's pinned digest"
            )
        manifests[key] = manifest

    descriptor_digest = str(device["descriptor"]["sha256"])

    def serves_descriptor(manifest: dict[str, Any]) -> bool:
        return any(
            str(file.get("sha256")) == descriptor_digest
            for file in manifest["payload"]["files"]
            if file.get("role") == _DESCRIPTOR_ROLE
        )

    serving = {key for key, manifest in manifests.items() if serves_descriptor(manifest)}
    if not serving:
        raise ClosureResolutionError(
            "closure_descriptor_absent: the admitted closure serves no payload "
            f"descriptor digest {descriptor_digest[:12]}… pinned by bench "
            f"{bench_id} device {device.get('id')!r}"
        )
    implementations: set[tuple[str, str, str]] = set()
    for key, manifest in manifests.items():
        if manifest.get("kind") != _IMPLEMENTATION_ROLE:
            continue
        if key in serving:
            implementations.add(key)
            continue
        for dependency in manifest.get("dependencies", []):
            dep_key = (
                str(dependency["registry_id"]),
                str(dependency["package_id"]),
                str(dependency["version"]),
            )
            if dep_key in serving:
                implementations.add(key)
    if len(implementations) != 1:
        raise ClosureResolutionError(
            "closure_implementation_ambiguous: expected exactly one "
            f"implementation release serving the descriptor, found {sorted(implementations)}"
        )
    impl_key = next(iter(implementations))
    manifest = manifests[impl_key]
    manifest_sha256 = str(rows[impl_key]["manifest_sha256"])
    cache_dir = session.cache_root / manifest_sha256
    if not cache_dir.is_dir():
        raise ClosureResolutionError(
            "closure_cache_absent: the admitted cache directory "
            f"{cache_dir} for {impl_key} is missing"
        )
    entry_point = str(
        ((descriptor.get("integration") or {}).get("adapter") or {}).get("entry_point") or ""
    )
    if not entry_point:
        raise ClosureResolutionError(
            "closure_entry_absent: the device descriptor declares no "
            "integration.adapter.entry_point"
        )
    return DeviceClosure(
        cache_root=session.cache_root,
        manifest=manifest,
        manifest_sha256=manifest_sha256,
        entry_relpath=_entry_relpath(entry_point, manifest),
    )
