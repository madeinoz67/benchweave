# tests/contract/test_registry_semantics.py
"""Registry contract §10 semantic admission over schema-valid manifest closures."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.registry.manifests import check_closure
from benchweave.registry.schemas import RegistryRejected

REPO = Path(__file__).resolve().parents[2]
ORIGIN_MAIN = REPO / "fixtures" / "registry" / "origin-main"

Key = tuple[str, str, str]


def _load(package_id: str) -> dict[str, Any]:
    raw = (ORIGIN_MAIN / package_id / "1.0.0" / "manifest.json").read_bytes()
    manifest: dict[str, Any] = json.loads(raw)
    return manifest


def _key(manifest: dict[str, Any]) -> Key:
    return (manifest["registry_id"], manifest["package_id"], manifest["version"])


def _base_closure() -> dict[Key, dict[str, Any]]:
    """``benchweave/sim-psu`` plus its transitive dependency closure, keyed by release."""
    manifests: dict[Key, dict[str, Any]] = {}
    for package_id in (
        "benchweave/sim-psu",
        "benchweave/sim-psu-descriptor",
        "benchweave/dc-psu-profile",
    ):
        manifest = _load(package_id)
        manifests[_key(manifest)] = manifest
    return manifests


def test_valid_closure_admitted() -> None:
    # The pristine catalogue closure must pass: sim-psu and sim-psu-descriptor
    # both provide "benchweave:sim-psu:1.0.0", joined by a direct dependency
    # edge (implementation re-expresses its depended-upon descriptor's id).
    check_closure(_base_closure())  # no raise


def test_missing_dependency() -> None:
    manifests = _base_closure()
    impl = manifests[_key(_load("benchweave/sim-psu"))]
    impl["dependencies"][0]["package_id"] = "benchweave/absent-descriptor"
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "missing_dependency"


def test_duplicate_package() -> None:
    manifests = _base_closure()
    other_version = _load("benchweave/sim-psu-descriptor")
    other_version["version"] = "0.9.0"  # distinct map key, same (registry, package)
    manifests[_key(other_version)] = other_version
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "duplicate_package"


def test_cycle() -> None:
    manifests = _base_closure()
    descriptor = manifests[_key(_load("benchweave/sim-psu-descriptor"))]
    descriptor["dependencies"][0]["package_id"] = "benchweave/sim-psu"  # points back at impl
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "cycle"


def test_conflicting_provided_id() -> None:
    manifests = _base_closure()
    rogue = _load("benchweave/sim-psu-descriptor")
    rogue["package_id"] = "benchweave/rogue-descriptor"  # unrelated package, same provides
    manifests[_key(rogue)] = rogue
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "conflict"


def test_wrapper_descriptor_sharing_implementation_id_conflicts() -> None:
    """§11: the id-sharing exemption is ownership-direction-only.

    A wrapper DESCRIPTOR that depends on the implementation (and on the
    original descriptor, so every sharing pair is edge-joined) and
    re-expresses their descriptor id is NOT an exemption: only the dependent
    being an implementation re-expressing its depended-upon descriptor's id
    is. Wrappers need distinct ids. Today's either-direction edge exemption
    would admit this closure.
    """
    manifests = _base_closure()
    wrapper = _load("benchweave/sim-psu-descriptor")
    wrapper["package_id"] = "benchweave/sim-psu-wrapper"
    # Depend on BOTH the original descriptor and the implementation, so
    # every id-sharing pair is edge-joined: under the old either-direction
    # exemption this closure admits; under the ownership-direction rule the
    # wrapper (a descriptor, not an implementation) can never own the id.
    wrapper["dependencies"].extend(
        [
            {
                "registry_id": "origin-main",
                "package_id": "benchweave/sim-psu-descriptor",
                "version": "1.0.0",
                "manifest_sha256": "0" * 64,
            },
            {
                "registry_id": "origin-main",
                "package_id": "benchweave/sim-psu",
                "version": "1.0.0",
                "manifest_sha256": "0" * 64,
            },
        ]
    )
    manifests[_key(wrapper)] = wrapper
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "conflict"


def test_cross_kind_same_string_provides_do_not_conflict() -> None:
    """Profile ids and descriptor ids are separate namespaces (§11).

    A package providing the string "benchweave:sim-psu:1.0.0" as a PROFILE
    id does not collide with the descriptor packages providing the same
    string as a DESCRIPTOR id: the per-kind provider maps are distinct, so
    cross-kind equality is not conflated into a conflict.
    """
    manifests = _base_closure()
    stranger = _load("benchweave/dc-psu-profile")
    stranger["package_id"] = "benchweave/stranger-profile"
    stranger["provides"] = {
        "profile_ids": ["benchweave:sim-psu:1.0.0"],
        "descriptor_ids": [],
    }
    manifests[_key(stranger)] = stranger
    check_closure(manifests)  # no raise


def test_path_unsafe() -> None:
    manifests = _base_closure()
    impl = manifests[_key(_load("benchweave/sim-psu"))]
    impl["payload"]["files"][0]["path"] = "../outside.txt"
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "path_unsafe"


def test_duplicate_path() -> None:
    manifests = _base_closure()
    impl = manifests[_key(_load("benchweave/sim-psu"))]
    impl["payload"]["files"][0]["path"] = "LICENSE"  # second entry already carries LICENSE
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "duplicate_path"


def test_case_fold_collision() -> None:
    manifests = _base_closure()
    impl = manifests[_key(_load("benchweave/sim-psu"))]
    impl["payload"]["files"].append(
        {
            "path": "license",
            "role": "documentation",
            "bytes": 1,
            "sha256": "c" * 64,
        }
    )
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "case_fold_collision"


def test_invalid_spdx() -> None:
    manifests = _base_closure()
    impl = manifests[_key(_load("benchweave/sim-psu"))]
    impl["licence"]["spdx_expression"] = "some prose licence statement"  # not an expression
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "invalid_spdx"


def test_mutable_source_revision() -> None:
    manifests = _base_closure()
    impl = manifests[_key(_load("benchweave/sim-psu"))]
    impl["source"]["revision"] = "main"
    with pytest.raises(RegistryRejected) as exc:
        check_closure(manifests)
    assert exc.value.reason == "mutable_source_revision"
