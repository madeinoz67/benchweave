"""Admitted multi-module adapters execute only pinned code and resources."""

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
from benchweave.state.store import Store

ENTRY = (
    b"from .helper import VALUE\nfrom importlib.resources import files\n"
    b"def create_plugin():\n"
    b'    return type("Adapter", (), {"value": VALUE, '
    b'"resource": files(__package__).joinpath("data.txt").read_text()})()\n'
)


def bundle(tmp_path: Path, payload: dict[str, bytes] | None = None) -> tuple[dict[str, Any], str]:
    payload = payload or {
        "src/example/__init__.py": b"",
        "src/example/plugin.py": ENTRY,
        "src/example/helper.py": b'VALUE = "one"\n',
        "src/example/data.txt": b"resource",
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


def load(tmp_path: Path, manifest: dict[str, Any], digest: str) -> OTDPBridge:
    from benchweave.registry.otdp_loading import load_otdp_plugin

    return load_otdp_plugin(
        tmp_path,
        manifest,
        digest,
        entry_relpath="src/example/plugin.py",
        descriptor={},
        services=SimpleNamespace(monotonic=lambda: 0.0),
        simulation=SimulationInfo(True, "test"),
    )


def test_package_imports_and_resources_are_version_isolated(tmp_path: Path) -> None:
    manifest, digest = bundle(tmp_path)
    first = load(tmp_path, manifest, digest)
    payload = {
        "src/example/__init__.py": b"",
        "src/example/plugin.py": ENTRY,
        "src/example/helper.py": b'VALUE = "two"\n',
        "src/example/data.txt": b"second",
    }
    manifest2, digest2 = bundle(tmp_path, payload)
    second = load(tmp_path, manifest2, digest2)
    assert first._adapter.value == "one"
    assert second._adapter.value == "two"
    assert first._adapter.resource == "resource"
    assert second._adapter.resource == "second"
    first.plugin_close()
    second.plugin_close()


@pytest.mark.parametrize(
    "path", ["src/example/plugin.py", "src/example/helper.py", "src/example/data.txt"]
)
def test_all_inventory_bytes_verified_before_execution(tmp_path: Path, path: str) -> None:
    manifest, digest = bundle(tmp_path)
    (tmp_path / digest / path).write_text("tampered")
    with pytest.raises(ActivationRejected, match="file_hash_mismatch"):
        load(tmp_path, manifest, digest)


def test_symlink_resource_rejected(tmp_path: Path) -> None:
    manifest, digest = bundle(tmp_path)
    resource = tmp_path / digest / "src/example/data.txt"
    resource.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(b"resource")
    resource.symlink_to(outside)
    with pytest.raises(ActivationRejected, match="unsafe_bundle_path"):
        load(tmp_path, manifest, digest)


def test_uninventoried_relative_import_does_not_execute(tmp_path: Path) -> None:
    manifest, digest = bundle(
        tmp_path,
        {
            "src/example/__init__.py": b"",
            "src/example/plugin.py": b"from . import stray\ndef create_plugin(): return stray\n",
        },
    )
    (tmp_path / digest / "src/example/stray.py").write_text('raise AssertionError("executed")')
    with pytest.raises(ImportError):
        load(tmp_path, manifest, digest)


def test_local_absolute_dependency_is_not_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, digest = bundle(
        tmp_path,
        {
            "src/example/__init__.py": b"",
            "src/example/plugin.py": b"import stray\ndef create_plugin(): return stray\n",
        },
    )
    (tmp_path / "stray.py").write_text('raise AssertionError("executed")')
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ImportError):
        load(tmp_path, manifest, digest)


def test_manifest_identity_cannot_be_forged(tmp_path: Path) -> None:
    manifest, digest = bundle(tmp_path)
    manifest["changed"] = True
    with pytest.raises(ActivationRejected, match="manifest_hash_mismatch"):
        load(tmp_path, manifest, digest)


def test_shadowed_stdlib_dependency_is_not_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, digest = bundle(
        tmp_path,
        {
            "src/example/__init__.py": b"",
            "src/example/plugin.py": b"import colorsys\ndef create_plugin(): return colorsys\n",
        },
    )
    monkeypatch.delitem(sys.modules, "colorsys", raising=False)
    (tmp_path / "colorsys.py").write_text('raise AssertionError("executed")')
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ImportError):
        load(tmp_path, manifest, digest)


def test_close_releases_importer_and_modules(tmp_path: Path) -> None:
    manifest, digest = bundle(tmp_path)
    before = set(sys.modules)
    plugin = load(tmp_path, manifest, digest)
    added = set(sys.modules) - before
    assert any(name.startswith("_benchweave_otdp_") for name in added)
    plugin.plugin_close()
    assert not any(name in sys.modules for name in added if name.startswith("_benchweave_otdp_"))


# --- issue #43 slice 1: the composing services ride the real load path (A11) ---

CAPTURE_ENTRY = (
    b"class Recording:\n"
    b"    services = None\n"
    b"    async def open(self, descriptor, services, context):\n"
    b"        self.services = services\n"
    b"    async def close(self, context):\n"
    b"        pass\n"
    b"def create_plugin():\n"
    b"    return Recording()\n"
)


def _capture_services(tmp_path: Path) -> tuple[Store, tuple[Any, Any]]:
    import hashlib
    import json

    from benchweave.content.capture_services import build_capture_services
    from benchweave.content.capture_store import CaptureStagingStore
    from benchweave.content.store import ContentStore
    from benchweave.host.services import QuotaLimits
    from benchweave.state.store import Store

    store = Store.open(tmp_path / "load-capture.db")
    content = ContentStore(store)
    raw = {
        "id": "dev.local.load-path",
        "descriptor_version": "1.0.0",
        "integration": {
            "adapter": {
                "permissions": ["scoped_transport", "artifact_writer"]
            }
        },
    }
    blob = json.dumps(raw, sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    content.put_document(blob, digest, raw, "otdp-descriptor", "2026-09-22T00:00:00Z")
    writer = CaptureStagingStore(store, max_capture_bytes=64, max_dataset_bytes=64)
    return store, build_capture_services(
        descriptor_digest=digest,
        content=content,
        writer=writer,
        clock=lambda: 0.0,
        wall=lambda: "2026-09-22T00:00:00Z",
        quota=QuotaLimits(
            max_dataset_bytes=64, max_evidence_entries=10, max_event_batch=5
        ),
        context_key="load-path-session",
    )


def test_the_real_load_path_hands_the_adapter_the_capture_bundle(tmp_path: Path) -> None:
    """A11: the caller of load_otdp_plugin constructs via
    build_capture_services and passes services=bundle, capture=controller —
    plugin_open hands the adapter the bundle, the ONLY mechanism that
    reaches it at open."""
    from benchweave.registry.otdp_loading import load_otdp_plugin

    payload = {
        "src/example/__init__.py": b"",
        "src/example/plugin.py": CAPTURE_ENTRY,
    }
    manifest, digest = bundle(tmp_path, payload)
    store, (services, controller) = _capture_services(tmp_path)
    assert controller is not None
    try:
        plugin = load_otdp_plugin(
            tmp_path,
            manifest,
            digest,
            entry_relpath="src/example/plugin.py",
            descriptor={},
            services=services,
            simulation=SimulationInfo(True, "test"),
            capture=controller,
        )
        plugin.plugin_open(object())
        received = plugin._adapter.services
        assert received is services
        for member in (
            "monotonic",
            "utc_now",
            "transfer",
            "close_transport",
            "record_evidence",
            "artifact_append",
            "artifact_finalise",
            "artifact_abort",
        ):
            assert hasattr(received, member), member  # the 8-member bundle
        plugin.plugin_close()
    finally:
        store.close()


def test_the_load_path_hands_over_the_scoped_shape_without_permission(tmp_path: Path) -> None:
    from benchweave.registry.otdp_loading import load_otdp_plugin

    payload = {
        "src/example/__init__.py": b"",
        "src/example/plugin.py": CAPTURE_ENTRY,
    }
    manifest, digest = bundle(tmp_path, payload)
    store, (services, controller) = _capture_services(tmp_path)
    assert controller is not None
    # A raw descriptor WITHOUT artifact_writer: the factory returns the
    # five-member shape and no controller.
    import hashlib
    import json

    from benchweave.content.capture_services import build_capture_services
    from benchweave.content.capture_store import CaptureStagingStore
    from benchweave.content.store import ContentStore
    from benchweave.host.services import QuotaLimits

    content = ContentStore(store)
    raw = {
        "id": "dev.local.load-path",
        "descriptor_version": "1.0.0",
        "integration": {"adapter": {"permissions": ["scoped_transport"]}},
    }
    blob = json.dumps(raw, sort_keys=True).encode()
    negative_digest = hashlib.sha256(blob).hexdigest()
    content.put_document(blob, negative_digest, raw, "otdp-descriptor", "t")
    scoped, no_controller = build_capture_services(
        descriptor_digest=negative_digest,
        content=content,
        writer=CaptureStagingStore(store, max_capture_bytes=64, max_dataset_bytes=64),
        clock=lambda: 0.0,
        wall=lambda: "t",
        quota=QuotaLimits(max_dataset_bytes=64, max_evidence_entries=10, max_event_batch=5),
        context_key="load-path-session",
    )
    assert no_controller is None
    try:
        plugin = load_otdp_plugin(
            tmp_path,
            manifest,
            digest,
            entry_relpath="src/example/plugin.py",
            descriptor={},
            services=scoped,
            simulation=SimulationInfo(True, "test"),
        )
        plugin.plugin_open(object())
        received = plugin._adapter.services
        assert received is scoped
        for member in ("artifact_append", "artifact_finalise", "artifact_abort"):
            assert not hasattr(received, member), member  # structural absence
        plugin.plugin_close()
    finally:
        store.close()
