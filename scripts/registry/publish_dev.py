# scripts/registry/publish_dev.py
"""Deterministically publish a plugin directory into a local unsigned dev registry.

The keyless developer loop (unsigned-dev-plugins design, fork A): point this
at a plugin directory and get a resolvable release tree under registry id
``dev-local`` — publish → resolve(``dev-unsigned``) → admit → ``load_plugin``
with ZERO signing keys. The publisher writes ``manifest.json``,
``status.json`` and ``payload.zip`` and never any ``.sig`` file; the release
is consumed through an ``OriginConfig(signature_policy="dev-unsigned")``
origin, which skips exactly the two authenticity verifications while every
integrity, identity, expiry and sequence gate stays live.

Honest dev posture: a dev origin's status bytes are unauthenticated by
design — a local process that can write the dev root can forge lifecycle
state. That limitation is accepted and documented here, not hidden. The
default dependency pins come from the signed origin-main catalogue
(``fixtures/registry/catalogue.json``), so the normal dev closure is an
unsigned implementation over signed production descriptor/profile, and those
dependencies remain signature-verified at resolve time. A descriptor
override is published unsigned alongside under the same dev origin, with the
implementation's dependency repinned to the dev descriptor's digest.

Output is byte-reproducible for identical inputs: canonical JSON, ZIP_STORED
payloads with fixed timestamps, sorted members, and FIXED status dates
mirroring ``build_fixtures`` (``RELEASED_AT``/``STATUS_EXPIRES``) — no clock
is read, no key is touched, no network is consulted. Nothing is written
until every release has been built in memory, so a bad input leaves no
partial output tree.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from build_fixtures import (
    ROLE_BY_SUFFIX,
    _canonical,
    _common_members,
    _device_target,
    _impl_extras,
    _manifest,
    _payload,
    _sha,
    _status,
    _zip_bytes,
)

REPO = Path(__file__).resolve().parents[2]

#: The dev origin's registry id (design decision 2: identity, not a flag).
DEV_REGISTRY_ID = "dev-local"

#: The signed origin the default dependency pins come from.
ORIGIN_MAIN = "origin-main"

#: The one profile the fixture device targets reference.
PROFILE_PACKAGE = "benchweave/dc-psu-profile"

#: Dev iteration version (strict numeric semver; bump by flag).
DEFAULT_VERSION = "0.0.0"

#: Strict numeric semver, mirroring the vendored manifest schema pattern.
_VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class PublishError(ValueError):
    """Publishing refused; the message names the offending input."""


def _origin_main_pin(package_id: str) -> dict[str, Any]:
    """The committed origin-main dependency pin for ``package_id``.

    Pins come from the fixture catalogue — the same digests a signed install
    resolves — so the dev closure rides verified production releases unless a
    descriptor override repins the descriptor leg.
    """
    catalogue = json.loads((REPO / "fixtures" / "registry" / "catalogue.json").read_bytes())
    for row in catalogue["releases"]:
        if row["registry_id"] == ORIGIN_MAIN and row["package_id"] == package_id:
            return {
                "registry_id": ORIGIN_MAIN,
                "package_id": package_id,
                "version": row["version"],
                "manifest_sha256": row["manifest_sha256"],
            }
    raise PublishError(
        f"no origin-main pin for {package_id!r} in fixtures/registry/catalogue.json"
    )


def _build_release(
    *,
    package_id: str,
    kind: str,
    provides: dict[str, Any],
    device_targets: list[dict[str, Any]],
    deps: list[dict[str, Any]],
    members: list[tuple[str, bytes]],
    version: str,
) -> dict[str, bytes]:
    """Build one unsigned dev release in memory: zip → manifest → status.

    Digest chain in dependency order (mirroring ``build_fixtures``): the
    manifest embeds the payload digest, the status pins the manifest digest.
    The builder helpers hardcode version ``1.0.0``; the dev release overrides
    it with the publisher's version in both documents.
    """
    payload_zip = _zip_bytes(members)
    manifest = _manifest(
        DEV_REGISTRY_ID,
        package_id,
        kind,
        provides=provides,
        device_targets=device_targets,
        deps=deps,
        payload=_payload(payload_zip, members),
    )
    manifest["version"] = version
    manifest_raw = _canonical(manifest)
    status = _status(DEV_REGISTRY_ID, package_id, _sha(manifest_raw), sequence=1)
    status["release"]["version"] = version
    return {
        "manifest.json": manifest_raw,
        "status.json": _canonical(status),
        "payload.zip": payload_zip,
    }


def _dep_sort_key(dep: dict[str, Any]) -> tuple[str, str]:
    return (dep["registry_id"], dep["package_id"])


def publish(
    plugin_dir_arg: Path,
    descriptor_arg: Path | None,
    out: Path,
    version: str,
) -> list[Path]:
    """Publish the plugin (and any descriptor override) under ``out``.

    Returns the release directories written, in dependency order (the
    descriptor override first, then the implementation). Every release is
    built and digest-chained in memory before the first byte hits disk.
    """
    if _VERSION_PATTERN.fullmatch(version) is None:
        raise PublishError(f"version {version!r} is not strict numeric semver (X.Y.Z)")
    plugin_dir = plugin_dir_arg.resolve()
    if not plugin_dir.is_dir():
        raise PublishError(f"plugin directory not found: {plugin_dir_arg}")
    for entry in ("plugin.py", "__init__.py"):
        if not (plugin_dir / entry).is_file():
            raise PublishError(f"plugin entry missing: {plugin_dir / entry}")
    dirname = plugin_dir.name
    dashed = dirname.replace("_", "-")
    descriptor_member = f"descriptors/{dashed}.json"
    if ROLE_BY_SUFFIX.get(f"{dashed}.json") != "descriptor":
        raise PublishError(f"no descriptor payload role for {dashed}.json")

    profile_pin = _origin_main_pin(PROFILE_PACKAGE)
    descriptor_id = f"benchweave:{dashed}:1.0.0"
    releases: list[tuple[str, dict[str, bytes]]] = []

    if descriptor_arg is not None:
        descriptor_path = descriptor_arg.resolve()
        if not descriptor_path.is_file():
            raise PublishError(f"descriptor override not found: {descriptor_arg}")
        dev_desc_package = f"dev/{dashed}-descriptor"
        dev_desc = _build_release(
            package_id=dev_desc_package,
            kind="descriptor",
            provides={"profile_ids": [], "descriptor_ids": [descriptor_id]},
            device_targets=[_device_target(dashed, descriptor_id)],
            deps=[profile_pin],
            members=_common_members()
            + [(descriptor_member, descriptor_path.read_bytes())],
            version=version,
        )
        releases.append((dev_desc_package, dev_desc))
        descriptor_pin: dict[str, Any] = {
            "registry_id": DEV_REGISTRY_ID,
            "package_id": dev_desc_package,
            "version": version,
            "manifest_sha256": _sha(dev_desc["manifest.json"]),
        }
    else:
        descriptor_pin = _origin_main_pin(f"benchweave/{dashed}-descriptor")

    impl_package = f"dev/{dirname}"
    impl = _build_release(
        package_id=impl_package,
        kind="implementation",
        provides={"profile_ids": [], "descriptor_ids": [descriptor_id]},
        device_targets=[_device_target(dirname, descriptor_id)],
        deps=sorted((profile_pin, descriptor_pin), key=_dep_sort_key),
        members=_common_members()
        + _impl_extras()
        + [
            ("plugin/__init__.py", (plugin_dir / "__init__.py").read_bytes()),
            ("plugin/plugin.py", (plugin_dir / "plugin.py").read_bytes()),
        ],
        version=version,
    )
    releases.append((impl_package, impl))

    written: list[Path] = []
    for package_id, files in releases:
        release_dir = out / DEV_REGISTRY_ID / package_id / version
        # Fresh dir per release: a previous dev publish must not leak files
        # into the new one (the fixture builder's discipline).
        if release_dir.exists():
            shutil.rmtree(release_dir)
        release_dir.mkdir(parents=True)
        for name in ("manifest.json", "status.json", "payload.zip"):
            (release_dir / name).write_bytes(files[name])
        written.append(release_dir)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin_dir", type=Path, help="plugin directory, e.g. plugins/sim_psu")
    parser.add_argument(
        "--descriptor",
        type=Path,
        default=None,
        help="descriptor override path; published unsigned as dev/<name>-descriptor "
        "and the implementation's dependency is repinned to it",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".dev-registry"),
        help="output root (default: .dev-registry)",
    )
    parser.add_argument(
        "--version", default=DEFAULT_VERSION, help="release version (default: 0.0.0)"
    )
    args = parser.parse_args()
    try:
        written = publish(args.plugin_dir, args.descriptor, args.out, args.version)
    except PublishError as exc:
        print(f"publish_dev: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    for release_dir in written:
        print(f"published {release_dir}")


if __name__ == "__main__":
    main()
