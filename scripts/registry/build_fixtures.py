# scripts/registry/build_fixtures.py
"""Deterministically build the WP06 fixture registry catalogue.

Output is byte-reproducible: fixed zip timestamps, sorted members, canonical
JSON, static committed keys. Re-running must leave ``git diff`` empty.

The committed keys under ``fixtures/registry/keys/`` are test-only signing
material; regenerating them invalidates every committed signature.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, TypedDict

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[2]
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
RELEASED_AT = "2026-09-11T00:00:00Z"
STATUS_EXPIRES = "2027-09-11T00:00:00Z"

#: Payload member basename -> manifest ``payload.files[].role``. Every member
#: the builder can emit must be listed here; an unlisted file fails the build
#: loudly rather than shipping an unroleable payload entry.
ROLE_BY_SUFFIX: dict[str, str] = {
    "LICENSE": "licence",
    "CHANGELOG.md": "documentation",
    "MIGRATION.md": "documentation",
    "simulated.md": "documentation",
    "dc-psu.json": "profile",
    "sim-psu.json": "descriptor",
    "sim-controller.json": "descriptor",
    "plugin.py": "implementation",
    "__init__.py": "implementation",
    "sbom.json": "sbom",
    "build-provenance.json": "build_provenance",
    "dependency-lock.json": "dependency_lock",
}


class ReleaseEntry(TypedDict):
    """One catalogue.json lattice row: the honest inventory for tests."""

    origin: str
    registry_id: str
    package_id: str
    version: str
    manifest_sha256: str
    payload_sha256: str
    status_sequence: int


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_bytes(members: list[tuple[str, bytes]]) -> bytes:
    """ZIP_STORED throughout: zlib-independent reproducibility (final-fix 3a)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for path, data in sorted(members):
            info = zipfile.ZipInfo(path, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, data)
    return buf.getvalue()


def _payload(zip_data: bytes, members: list[tuple[str, bytes]]) -> dict[str, Any]:
    return {
        "sha256": _sha(zip_data),
        "bytes": len(zip_data),
        "media_type": "application/zip",
        "files": [
            {
                "path": p,
                "role": ROLE_BY_SUFFIX[p.rsplit("/", 1)[-1]],
                "bytes": len(b),
                "sha256": _sha(b),
            }
            for p, b in sorted(members)
        ],
    }


def _device_target(model: str, descriptor_id: str) -> dict[str, Any]:
    return {
        "manufacturer": "BenchWeave",
        "model": model,
        "aliases": [],
        "firmware": {"policy": "commissioning_required", "versions": []},
        "transports": ["sim"],
        "profile_ids": ["otdp:dc_psu:1.0.0"],
        "descriptor_ids": [descriptor_id],
    }


def _dep(registry_id: str, package_id: str, sha: str) -> dict[str, Any]:
    return {"registry_id": registry_id, "package_id": package_id, "version": "1.0.0",
            "manifest_sha256": sha}


def _manifest(
    registry_id: str,
    package_id: str,
    kind: str,
    provides: dict[str, Any],
    device_targets: list[dict[str, Any]],
    deps: list[dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    impl = kind == "implementation"
    return {
        "manifest_version": "1.0.0",
        "registry_id": registry_id,
        "package_id": package_id,
        "version": "1.0.0",
        "kind": kind,
        "display_name": package_id.rsplit("/", 1)[1],
        "summary": f"BenchWeave fixture {kind} ({package_id})",
        "released_at": RELEASED_AT,
        "tags": ["benchweave", kind],
        "publisher_id": "benchweave-fixtures",
        "maintainers": [{"name": "BenchWeave", "contact": "https://example.invalid/support"}],
        "support_url": "https://example.invalid/support",
        "issues_url": "https://example.invalid/issues",
        "licence": {"spdx_expression": "MIT", "file": "LICENSE"},
        "source": {"url": "https://example.invalid/src", "revision": "0" * 40},
        "compatibility": {
            "otdp_versions": ["0.3.0"],
            "adapter_api_versions": ["1.1"] if impl else [],
            "stg_versions": ["1.5"],
            "runtimes": (
                [{"os": "macos", "architecture": "arm64", "python_version": "3.13"}]
                if impl
                else []
            ),
            "host_provider_ids": [],
        },
        "device_targets": device_targets,
        "provides": provides,
        "dependencies": deps,
        "permissions": [],
        "payload": payload,
        "evidence": [
            {
                "level": "simulated",
                "report_path": "evidence/simulated.md",
                "tested_at": RELEASED_AT,
                "target": "synthetic",
                "result": "passed",
                "limitations": ["simulation-only fixture"],
            }
        ],
        "changelog_path": "CHANGELOG.md",
        "migration_notes_path": "MIGRATION.md",
        "limitations": ["WP06 fixture catalogue; not a real release"],
    }


def _status(
    registry_id: str,
    package_id: str,
    manifest_sha: str,
    *,
    sequence: int = 1,
    lifecycle: str = "published",
    reason: str = "initial release",
    expires: str = STATUS_EXPIRES,
) -> dict[str, Any]:
    return {
        "status_version": "1.0.0",
        "release": {
            "registry_id": registry_id,
            "package_id": package_id,
            "version": "1.0.0",
            "manifest_sha256": manifest_sha,
        },
        "sequence": sequence,
        "updated_at": RELEASED_AT,
        "expires_at": expires,
        "lifecycle": lifecycle,
        "reason": reason,
        "support_state": "maintained",
        "support_contact": "https://example.invalid/support",
        "reviews": [],
        "advisories": [],
    }


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


def _common_members() -> list[tuple[str, bytes]]:
    return [
        ("LICENSE", b"MIT (fixture)\n"),
        ("CHANGELOG.md", b"# 1.0.0\n- fixture release\n"),
        ("MIGRATION.md", b"# Migration\n\nNone.\n"),
        ("evidence/simulated.md", b"# Simulated evidence\n\nStructural + simulated only.\n"),
    ]


def _impl_extras() -> list[tuple[str, bytes]]:
    return [
        ("sbom.json", _canonical({"sbom_version": "1", "components": []})),
        ("build-provenance.json",
         _canonical({"inputs": [], "toolchain": "fixture", "output": "payload.zip"})),
        ("dependency-lock.json",
         _canonical({"lock_version": "py-fixture", "dependencies": []})),
    ]


def _profile_member() -> tuple[str, bytes]:
    """Structural dc_psu profile derived from the vendored OTDP class contract
    (``docs/otdp-v0.3.0/examples/class-dc_psu.json``): class identity, the
    three profile actions with their class-contract properties, and one
    conformance vector per action. Kept small — a fixture, not a device model.
    """
    profile = {
        "profile_id": "otdp:dc_psu:1.0.0",
        "class": "dc_psu",
        "actions": ["configure", "output", "measure"],
        "action_contracts": {
            "configure": {"timeout_ms": 30000, "side_effect": "state_change"},
            "output": {"timeout_ms": 30000, "side_effect": "state_change"},
            "measure": {"timeout_ms": 30000, "side_effect": "none"},
        },
        "conformance_vectors": [
            {
                "action": "configure",
                "given": {
                    "configuration_id": "cfg-1",
                    "channel": "ch1",
                    "ovp_v": 6.0,
                    "ocp_a": 0.6,
                    "voltage_v": 5.0,
                    "current_limit_a": 0.5,
                },
                "expect": {"configuration_id": "cfg-1", "applied": True},
            },
            {
                "action": "output",
                "given": {"channel": "ch1", "enabled": True},
                "expect": {"channel": "ch1", "enabled": True},
            },
            {
                "action": "measure",
                "given": {"configuration_id": "cfg-1", "channels": ["ch1"]},
                "expect": {"variables": ["voltage", "current", "power"]},
            },
        ],
    }
    return ("profiles/dc-psu.json", _canonical(profile))


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
