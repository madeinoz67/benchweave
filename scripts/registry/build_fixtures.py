# scripts/registry/build_fixtures.py
"""Deterministically build the WP06 fixture registry catalogue.

Output is byte-reproducible: fixed zip timestamps, sorted members, canonical
JSON, static committed keys. Re-running must leave ``git diff`` empty.

The committed keys under ``fixtures/registry/keys/`` are test-only signing
material; regenerating them invalidates every committed signature.

The keyless builders (canonical JSON, reproducible payloads, manifest/status
documents, common members) live in ``registry_common`` so the keyless dev
publisher can share them without importing this module's signing stack.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from registry_common import (
    REPO,
    ReleaseEntry,
    _canonical,
    _common_members,
    _dep,
    _device_target,
    _impl_extras,
    _manifest,
    _payload,
    _profile_member,
    _sha,
    _status,
    _zip_bytes,
)


def _plugin_members(plugin_dir: str) -> list[tuple[str, bytes]]:
    return [
        ("plugin/__init__.py", (REPO / "plugins" / plugin_dir / "__init__.py").read_bytes()),
        ("plugin/plugin.py", (REPO / "plugins" / plugin_dir / "plugin.py").read_bytes()),
    ]


def _load_key(name: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(
        (REPO / "fixtures/registry/keys" / f"{name}.pem").read_bytes(), password=None
    )
    assert isinstance(key, Ed25519PrivateKey)
    return key


def _emit_release(
    out: Path,
    origin_dir: str,
    key: Ed25519PrivateKey,
    registry_id: str,
    package_id: str,
    kind: str,
    provides: dict[str, Any],
    device_targets: list[dict[str, Any]],
    deps: list[dict[str, Any]],
    members: list[tuple[str, bytes]],
) -> ReleaseEntry:
    """Build one release, resolving the digest chain in dependency order.

    The manifest embeds the payload digest (zip bytes never include the
    manifest) and the status pins the manifest digest — so: zip first, then
    manifest, then status. No fixed-point iteration is needed.
    """
    payload_zip = _zip_bytes(members)
    manifest = _manifest(
        registry_id,
        package_id,
        kind,
        provides=provides,
        device_targets=device_targets,
        deps=deps,
        payload=_payload(payload_zip, members),
    )
    mraw = _canonical(manifest)
    status = _status(registry_id, package_id, _sha(mraw), sequence=1)
    sraw = _canonical(status)
    d = out / origin_dir / package_id / "1.0.0"
    # Fresh dir per release: files a previous build left inside a reused
    # version dir must not survive into the new catalogue.
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / "manifest.json").write_bytes(mraw)
    (d / "manifest.sig").write_bytes(key.sign(mraw))
    (d / "status.json").write_bytes(sraw)
    (d / "status.sig").write_bytes(key.sign(sraw))
    (d / "payload.zip").write_bytes(payload_zip)
    return ReleaseEntry(
        origin=origin_dir,
        registry_id=registry_id,
        package_id=package_id,
        version="1.0.0",
        manifest_sha256=_sha(mraw),
        payload_sha256=_sha(payload_zip),
        status_sequence=1,
    )


def _prune_stale_release_dirs(out: Path, keep: set[Path]) -> None:
    """Remove release dirs not in the current build set (final-fix 3b).

    Renames/deletions upstream must not leave validly-signed ghosts under
    ``--out``. Descent is ancestor-aware rather than depth-based — package
    ids are multi-segment (``benchweave/sim-psu``) — so any directory on the
    path to a kept release is descended into, never removed, and any
    directory no kept release lives beneath is removed wholesale. ``keys/``
    and non-directory entries are never touched.
    """
    preserved = {out / "keys"}

    def kept_ancestor(path: Path) -> bool:
        return any(path == kept or path in kept.parents for kept in keep)

    def prune(level: Path) -> None:
        for child in sorted(level.iterdir()):
            if child in keep or child in preserved:
                continue
            if not child.is_dir():
                continue
            if kept_ancestor(child):
                prune(child)
            else:
                shutil.rmtree(child)

    for top in sorted(out.iterdir()):
        if top in preserved or not top.is_dir():
            continue
        prune(top)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    main_key = _load_key("main")
    originb_key = _load_key("originb")
    releases: list[ReleaseEntry] = []

    def emit(
        origin_dir: str,
        key: Ed25519PrivateKey,
        package_id: str,
        kind: str,
        provides: dict[str, Any],
        device_targets: list[dict[str, Any]],
        deps: list[dict[str, Any]],
        members: list[tuple[str, bytes]],
    ) -> None:
        releases.append(
            _emit_release(
                out,
                origin_dir,
                key,
                registry_id=origin_dir,
                package_id=package_id,
                kind=kind,
                provides=provides,
                device_targets=device_targets,
                deps=deps,
                members=members,
            )
        )

    def sha_of(origin: str, package_id: str) -> str:
        """Origin-scoped lookup: origin-b re-emits origin-main package ids."""
        return next(
            r["manifest_sha256"]
            for r in releases
            if r["origin"] == origin and r["package_id"] == package_id
        )

    # 1. profile — no dependencies.
    emit(
        "origin-main",
        main_key,
        "benchweave/dc-psu-profile",
        "profile",
        provides={"profile_ids": ["otdp:dc_psu:1.0.0"], "descriptor_ids": []},
        device_targets=[],
        deps=[],
        members=_common_members() + [_profile_member()],
    )
    pm_sha = sha_of("origin-main", "benchweave/dc-psu-profile")

    # 2. descriptors — deps pinned to the profile manifest sha.
    for name, src in (
        ("sim-psu", "descriptor-sim-psu.json"),
        ("sim-controller", "descriptor-sim-controller.json"),
    ):
        descriptor_id = f"benchweave:{name}:1.0.0"
        package_id = f"benchweave/{name}-descriptor"
        emit(
            "origin-main",
            main_key,
            package_id,
            "descriptor",
            provides={"profile_ids": [], "descriptor_ids": [descriptor_id]},
            device_targets=[_device_target(name, descriptor_id)],
            deps=[_dep("origin-main", "benchweave/dc-psu-profile", pm_sha)],
            members=_common_members()
            + [
                (
                    f"descriptors/{name}.json",
                    (REPO / "fixtures/execution" / src).read_bytes(),
                )
            ],
        )

    # 3. implementations — deps pinned to their descriptor's manifest sha.
    for pkg, plugin_dir, desc_pkg in (
        ("benchweave/sim-psu", "sim_psu", "benchweave/sim-psu-descriptor"),
        ("benchweave/sim-controller", "sim_controller", "benchweave/sim-controller-descriptor"),
    ):
        descriptor_id = f"benchweave:{pkg.rsplit('/', 1)[1]}:1.0.0"
        emit(
            "origin-main",
            main_key,
            pkg,
            "implementation",
            provides={"profile_ids": [], "descriptor_ids": [descriptor_id]},
            device_targets=[_device_target(pkg.rsplit("/", 1)[1], descriptor_id)],
            deps=[_dep("origin-main", desc_pkg, sha_of("origin-main", desc_pkg))],
            members=_common_members() + _impl_extras() + _plugin_members(plugin_dir),
        )

    # 4. origin-b collision: same benchweave/sim-psu identity, origin-b key.
    emit(
        "origin-b",
        originb_key,
        "benchweave/sim-psu",
        "implementation",
        provides={"profile_ids": [], "descriptor_ids": ["benchweave:sim-psu:1.0.0"]},
        device_targets=[_device_target("sim-psu-clone", "benchweave:sim-psu:1.0.0")],
        deps=[
            _dep("origin-main", "benchweave/sim-psu-descriptor",
                 sha_of("origin-main", "benchweave/sim-psu-descriptor"))
        ],
        members=_common_members() + _impl_extras() + _plugin_members("sim_psu"),
    )

    # 5. fault statuses: signed drop-in replacements targeting sim-psu-descriptor.
    desc_sha = sha_of("origin-main", "benchweave/sim-psu-descriptor")
    faults: list[tuple[str, dict[str, Any]]] = [
        ("revoked", {"lifecycle": "revoked", "reason": "fixture revocation"}),
        ("expired", {"expires": "2026-09-11T00:00:01Z"}),
        ("rollback-seq1", {"sequence": 1}),
        ("rollback-seq2", {"sequence": 2}),
    ]
    for fault_name, kwargs in faults:
        status = _status("origin-main", "benchweave/sim-psu-descriptor", desc_sha, **kwargs)
        fd = out / "faults" / fault_name / "benchweave/sim-psu-descriptor" / "1.0.0"
        if fd.exists():
            shutil.rmtree(fd)
        fd.mkdir(parents=True)
        sraw = _canonical(status)
        (fd / "status.json").write_bytes(sraw)
        (fd / "status.sig").write_bytes(main_key.sign(sraw))

    # Prune stale release dirs (and stale fault dirs) before the catalogue is
    # written: anything under --out that this build did not emit must go.
    keep: set[Path] = {
        out / entry["origin"] / entry["package_id"] / entry["version"] for entry in releases
    }
    keep |= {
        out / "faults" / fault_name / "benchweave/sim-psu-descriptor" / "1.0.0"
        for fault_name, _kwargs in faults
    }
    _prune_stale_release_dirs(out, keep)

    (out / "catalogue.json").write_bytes(_canonical({"releases": releases}))
    print(f"wrote {len(releases)} releases to {out}")


if __name__ == "__main__":
    main()
