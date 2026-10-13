"""Adapter-configuration loader arms (issue #447).

``load_otdp_plugin``'s inventory resolution of the descriptor's
``configuration.files`` — beside the ``resolve_otdp_contracts`` seam
(issue #146 posture: integrity failures refuse before any plugin import)
— pinned through the same bundle harness ``test_otdp_loading.py`` uses:

- the positive control: a triple resolving against the verified
  inventory constructs the bridge;
- ``adapter_config_not_in_bundle:`` — a triple whose path the verified
  inventory does not carry refuses before import (S21's inventory-presence
  clause, load-enforced);
- ``adapter_config_inventory_conflict:`` — the double-pin drift: the
  descriptor pins X, the manifest inventory pins Y for the same path.
  The inventory bytes are manifest-verified before resolution runs, so
  this refusal IS the descriptor-vs-manifest disagreement — the design's
  M-C drift arm, at the loader (the §14 addendum's fire-point reading);
- the altered-bytes control: tampered config bytes refuse through the
  inventory verification's generic ``file_hash_mismatch`` BEFORE the
  resolution and before any plugin code runs (M-B's before-import
  property; the typed ``adapter_config_hash_mismatch:`` prefix is the
  admission mirror's refusal, tests/control/).

The RED side (disclosed in the RED commit): pre-change a descriptor
carrying ``configuration`` loads cleanly at this seam — the field does
not exist, nothing checks it — which is M-B's own RED wording, and it is
what the refusal arms observed before the mechanism existed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from benchweave.host.otdp_bridge import OTDPBridge
from benchweave.host.plugin import SimulationInfo
from benchweave.registry.activation import ActivationRejected

#: The benign factory: constructs a bare adapter, the test_otdp_loading
#: shape — used by the arms that expect a constructed bridge.
BENIGN_ENTRY = b"def create_plugin():\n    return type('Adapter', (), {})()\n"

#: The entry module raises if it is ever executed — the before-import
#: property is proved by absence: when the gate works, the refusal fires
#: while this code has not run.
RAISING_ENTRY = (
    b"def create_plugin():\n"
    b'    raise AssertionError("executed")\n'
)

IMAGE_BYTES = b"BW-SYNTHETIC-IMAGE-v1" + bytes(range(64)) * 4
IMAGE_SHA256 = hashlib.sha256(IMAGE_BYTES).hexdigest()


def bundle(
    tmp_path: Path,
    descriptor: dict[str, Any],
    payload: dict[str, bytes] | None = None,
) -> tuple[dict[str, Any], str]:
    payload = payload or {
        "src/example/__init__.py": b"",
        "src/example/plugin.py": BENIGN_ENTRY,
        "src/example/assets/image.bin": IMAGE_BYTES,
    }
    manifest = {
        "payload": {
            "files": [
                {
                    "path": path,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "role": "implementation" if path.endswith(".py") else "resource",
                }
                for path, data in payload.items()
            ]
        }
    }
    digest = hashlib.sha256(
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    for path, data in payload.items():
        dest = tmp_path / digest / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return manifest, digest


def _descriptor(path: str, sha256: str = IMAGE_SHA256) -> dict[str, Any]:
    return {
        "integration": {
            "mode": "adapter",
            "adapter": {
                "configuration": {
                    "files": [{"id": "bench_image", "path": path, "sha256": sha256}]
                }
            },
        }
    }


def load(
    tmp_path: Path,
    manifest: dict[str, Any],
    digest: str,
    descriptor: dict[str, Any],
) -> OTDPBridge:
    from benchweave.registry.otdp_loading import load_otdp_plugin

    return load_otdp_plugin(
        tmp_path,
        manifest,
        digest,
        entry_relpath="src/example/plugin.py",
        descriptor=descriptor,
        services=SimpleNamespace(monotonic=lambda: 0.0),
        simulation=SimulationInfo(True, "test"),
    )


def test_configuration_triple_resolves_from_verified_inventory(tmp_path: Path) -> None:
    """The positive control: the triple resolves; the bridge constructs."""
    descriptor = _descriptor("src/example/assets/image.bin")
    manifest, digest = bundle(tmp_path, descriptor)
    bridge = load(tmp_path, manifest, digest, descriptor)
    bridge.plugin_close()


def test_triple_outside_inventory_refused_before_import(tmp_path: Path) -> None:
    """S21's inventory-presence clause at the loader: the path the
    verified inventory does not carry refuses before any plugin code."""
    descriptor = _descriptor("src/example/assets/missing.bin")
    manifest, digest = bundle(tmp_path, descriptor)
    with pytest.raises(ActivationRejected, match="adapter_config_not_in_bundle:"):
        load(tmp_path, manifest, digest, descriptor)


def test_double_pin_drift_refused_before_import(tmp_path: Path) -> None:
    """M-C's double-pin drift: descriptor pins X, manifest pins Y. The
    inventory bytes are already manifest-verified, so the disagreement is
    descriptor-vs-manifest by construction; it refuses, never resolves."""
    descriptor = _descriptor("src/example/assets/image.bin", sha256="a" * 64)
    manifest, digest = bundle(tmp_path, descriptor)
    with pytest.raises(ActivationRejected, match="adapter_config_inventory_conflict:"):
        load(tmp_path, manifest, digest, descriptor)


def test_altered_config_bytes_refuse_before_plugin_code(tmp_path: Path) -> None:
    """M-B's before-import property at the loader: altered bytes refuse
    through the inventory verification before the resolution runs — the
    entry module raises AssertionError if ever executed, so the typed
    ActivationRejected proves the plugin never ran."""
    descriptor = _descriptor("src/example/assets/image.bin")
    manifest, digest = bundle(
        tmp_path,
        descriptor,
        payload={
            "src/example/__init__.py": b"",
            "src/example/plugin.py": RAISING_ENTRY,
            "src/example/assets/image.bin": IMAGE_BYTES,
        },
    )
    (tmp_path / digest / "src/example/assets/image.bin").write_bytes(b"tampered")
    with pytest.raises(ActivationRejected, match="file_hash_mismatch"):
        load(tmp_path, manifest, digest, descriptor)


def test_configuration_absent_loads_unchanged(tmp_path: Path) -> None:
    """No-regression: a descriptor without the field loads exactly as
    before (the mirror and the loader are no-ops on absence)."""
    manifest, digest = bundle(
        tmp_path,
        {},
        payload={
            "src/example/__init__.py": b"",
            "src/example/plugin.py": b"def create_plugin():\n    return object()\n",
        },
    )
    bridge = load(tmp_path, manifest, digest, {})
    bridge.plugin_close()


def test_malformed_configuration_shape_load_refused(tmp_path: Path) -> None:
    """Defense-in-depth at the loader: a malformed shape (not the
    schema-guaranteed one) refuses rather than type-errors — present
    bytes that lie refuse the load, the resolve_otdp_contracts posture."""
    descriptor = {
        "integration": {"adapter": {"configuration": {"files": ["not-an-object"]}}}
    }
    manifest, digest = bundle(tmp_path, descriptor)
    with pytest.raises(ActivationRejected, match="adapter_config_invalid:"):
        load(tmp_path, manifest, digest, descriptor)


def test_sys_path_never_carries_the_bundle(tmp_path: Path) -> None:
    """The loader's standing posture holds with the new resolution in
    place: the cache root never lands on sys.path."""
    descriptor = _descriptor("src/example/assets/image.bin")
    manifest, digest = bundle(tmp_path, descriptor)
    before = list(sys.path)
    bridge = load(tmp_path, manifest, digest, descriptor)
    bridge.plugin_close()
    assert sys.path == before
