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
from benchweave.standards.manifest import load_manifest
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


# --- issue #146 slice 2: pinned-contract resolution at load (§2.1) -------------
#
# Derivations (from the corpus, not the plan's restatement): the contracts
# entry shape is the descriptor schema's `contracts` items (required
# {id, path, sha256}, closed); the catalog document shape is the vendored
# device-profile-catalog.schema.json (catalog_version/otdp_version consts,
# profiles minItems 1, actions with the five required fields); the
# measurement schema is identified by its `urn:otdp:measurement:` $id and
# `$defs/dataset` presence; the load-time $ref probe is design §2.1
# Amendment 1 MEDIUM-3 (R14) — the real catalog's dataset-producing
# output refs target the measurement schema's dataset def by urn and are
# the in-tree witness that resolution is SET-scoped, not
# document-scoped.

_ROOT = Path(__file__).resolve().parents[2]


def _active_otdp_root() -> Path:
    version = next(
        entry.version for entry in load_manifest(_ROOT).standards if entry.id == "otdp"
    )
    return _ROOT / "standards" / "otdp" / version


def _corpus_bytes(name: str) -> bytes:
    return (_active_otdp_root() / name).read_bytes()


def _synthetic_catalog() -> dict[str, Any]:
    """A minimal catalog-schema-valid catalog with NO cross-document refs —
    the fixture for the soft both-or-neither arm (the real corpus catalog's
    measurement refs make its half-pair refuse at load through the probe)."""
    return {
        "catalog_version": json.loads(_corpus_bytes("device-profile-catalog.json"))[
            "catalog_version"
        ],
        "otdp_version": json.loads(_corpus_bytes("device-profile-catalog.json"))[
            "otdp_version"
        ],
        "profiles": [
            {
                "id": "demo.profile/1.0.0",
                "title": "Demo profile",
                "channel_roles": ["source"],
                "required_actions": ["demo.act/1.0.0"],
                "optional_actions": [],
            }
        ],
        "actions": {
            "demo.act/1.0.0": {
                "description": "Synthetic action (invented fixture name).",
                "input_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "required": ["x"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
                "side_effect": "none",
                "lifecycle": "direct",
            }
        },
    }


def _contracts_descriptor(
    payload: dict[str, bytes],
    *,
    digests: dict[str, str] | None = None,
    capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """A raw descriptor whose contracts pin the given bundle files."""
    digests = digests if digests is not None else {}
    return {
        "id": "dev.local.contracts-fixture",
        "descriptor_version": "1.0.0",
        "capabilities": capabilities
        if capabilities is not None
        else ["identify", "invoke"],
        "contracts": [
            {
                "id": f"contract-{index}",
                "path": path,
                "sha256": digests.get(
                    path, hashlib.sha256(data).hexdigest()
                ),
            }
            for index, (path, data) in enumerate(sorted(payload.items()))
        ],
    }


def _load_with_contracts(
    tmp_path: Path,
    contract_files: dict[str, bytes],
    descriptor: dict[str, Any],
) -> OTDPBridge:
    """Load a real bundle whose payload carries the contract files, against
    the given (contracts-pinning) descriptor — the REAL activation path."""
    from benchweave.registry.otdp_loading import load_otdp_plugin

    payload = {
        "src/example/__init__.py": b"",
        "src/example/plugin.py": ENTRY,
        "src/example/helper.py": b'VALUE = "one"\n',
        "src/example/data.txt": b"resource",
        **contract_files,
    }
    manifest, digest = bundle(tmp_path, payload)
    return load_otdp_plugin(
        tmp_path,
        manifest,
        digest,
        entry_relpath="src/example/plugin.py",
        descriptor=descriptor,
        services=SimpleNamespace(monotonic=lambda: 0.0),
        simulation=SimulationInfo(True, "test"),
    )


def test_r9_contract_digest_mismatch_refused_at_load(tmp_path: Path) -> None:
    """R9: pinned catalog bytes that do not hash to the declared sha256
    refuse the LOAD (ActivationRejected, zero bridges constructed)."""
    catalog = _corpus_bytes("device-profile-catalog.json")
    measurement = _corpus_bytes("otdp-measurement.schema.json")
    files = {"contracts/catalog.json": catalog, "contracts/measurement.json": measurement}
    digest_of = {"contracts/catalog.json": hashlib.sha256(measurement).hexdigest()}
    with pytest.raises(ActivationRejected, match="contract_hash_mismatch"):
        _load_with_contracts(
            tmp_path, files, _contracts_descriptor(files, digests=digest_of)
        )


def test_r14_external_ref_catalog_refused_at_load(tmp_path: Path) -> None:
    """R14: a digest-matching catalog whose embedded schema carries one
    external/unresolvable $ref refuses at LOAD — without the probe the same
    catalog would pass load and poison at first dispatch instead."""
    catalog = json.loads(_corpus_bytes("device-profile-catalog.json"))
    first = next(iter(catalog["actions"]))
    catalog["actions"][first]["output_schema"] = {
        "$ref": "https://example.invalid/unresolvable"
    }
    measurement = _corpus_bytes("otdp-measurement.schema.json")
    files = {
        "contracts/catalog.json": json.dumps(catalog).encode(),
        "contracts/measurement.json": measurement,
    }
    with pytest.raises(ActivationRejected, match="contract_ref_unresolvable"):
        _load_with_contracts(tmp_path, files, _contracts_descriptor(files))


def test_r16_real_catalog_without_measurement_refuses_at_load(tmp_path: Path) -> None:
    """R16 (catalog half of the both-or-neither pair): the REAL corpus
    catalog pinned without the measurement schema refuses at LOAD — its
    twelve measurement-urn output refs are unresolvable in the pinned set
    (the probe's arm; Amendment 1 MEDIUM-3)."""
    files = {"contracts/catalog.json": _corpus_bytes("device-profile-catalog.json")}
    with pytest.raises(ActivationRejected, match="contract_ref_unresolvable"):
        _load_with_contracts(tmp_path, files, _contracts_descriptor(files))


def test_r16_multi_catalog_refused_at_load(tmp_path: Path) -> None:
    """R16 (NIT-2): two catalog-shaped pinned contracts refuse at load —
    overlapping action_ids would let merge order silently pick the
    input_schema that gates I4; the precedence question is closed by
    refusal, not resolution."""
    measurement = _corpus_bytes("otdp-measurement.schema.json")
    files = {
        "contracts/catalog-a.json": json.dumps(_synthetic_catalog()).encode(),
        "contracts/catalog-b.json": json.dumps(_synthetic_catalog()).encode(),
        "contracts/measurement.json": measurement,
    }
    with pytest.raises(ActivationRejected, match="contract_multi_catalog"):
        _load_with_contracts(tmp_path, files, _contracts_descriptor(files))


def test_r16_unknown_contract_shape_refused_at_load(tmp_path: Path) -> None:
    """R16 (C01/M14's unknown-contract edge): a pinned contract that is
    neither the measurement schema nor a catalog-schema-valid document
    refuses at load — unknown required contracts are rejected, never
    treated as opaque success."""
    measurement = _corpus_bytes("otdp-measurement.schema.json")
    files = {
        "contracts/other.json": b'{"kind": "a-third-contract-shape"}',
        "contracts/measurement.json": measurement,
    }
    with pytest.raises(ActivationRejected, match="contract_schema"):
        _load_with_contracts(tmp_path, files, _contracts_descriptor(files))


def test_r7_measurement_without_catalog_constructs_no_controller(
    tmp_path: Path,
) -> None:
    """R7 (the soft half of both-or-neither): a cleanly-resolving
    measurement schema pinned without any catalog LOADS (no integrity
    failure) but constructs no class surface — the bridge carries no
    dataset controller, so invoke is a verb-level UNSUPPORTED (design §2.1:
    a half-declared class surface grants no class surface)."""
    files = {"contracts/measurement.json": _corpus_bytes("otdp-measurement.schema.json")}
    plugin = _load_with_contracts(tmp_path, files, _contracts_descriptor(files))
    try:
        assert plugin._dataset is None
    finally:
        plugin.plugin_close()


def test_resolved_pair_constructs_the_dataset_controller(tmp_path: Path) -> None:
    """The complete pair — the real corpus catalog and measurement schema,
    pinned at their true digests — resolves through the REAL load path and
    the bridge carries the dataset controller (capability ∧ contracts
    resolved, design §2.2's table)."""
    files = {
        "contracts/catalog.json": _corpus_bytes("device-profile-catalog.json"),
        "contracts/measurement.json": _corpus_bytes("otdp-measurement.schema.json"),
    }
    plugin = _load_with_contracts(tmp_path, files, _contracts_descriptor(files))
    try:
        assert plugin._dataset is not None
    finally:
        plugin.plugin_close()


def test_resolved_pair_without_invoke_capability_constructs_no_controller(
    tmp_path: Path,
) -> None:
    """Design §2.2's table, the capability row: the same resolved pair on a
    descriptor that does NOT declare the invoke capability constructs no
    controller — the class surface is invoke's, not a side effect of
    pinning contracts."""
    files = {
        "contracts/catalog.json": _corpus_bytes("device-profile-catalog.json"),
        "contracts/measurement.json": _corpus_bytes("otdp-measurement.schema.json"),
    }
    plugin = _load_with_contracts(
        tmp_path, files, _contracts_descriptor(files, capabilities=["identify"])
    )
    try:
        assert plugin._dataset is None
    finally:
        plugin.plugin_close()


def test_contract_path_outside_the_bundle_is_soft_unresolved(tmp_path: Path) -> None:
    """A pin whose path the verified inventory does not carry is the SOFT
    'unresolved contracts' arm (§2.2's table row, R16's verb-level row):
    no bytes exist to disagree with anything, so the load proceeds with NO
    class surface — invoke refuses UNSUPPORTED at the verb — and
    resolution never reads the filesystem (Amendment 1 NIT-1's no-re-read
    rule). The hard arms are bytes that ARE present and lie: digest
    mismatch, unparsable, schema-invalid, unresolvable $ref."""
    measurement = _corpus_bytes("otdp-measurement.schema.json")
    files = {"contracts/measurement.json": measurement}
    descriptor = _contracts_descriptor({"contracts/measurement.json": measurement})
    descriptor["contracts"].append(
        {
            "id": "contract-absent",
            "path": "contracts/not-in-bundle.json",
            "sha256": hashlib.sha256(b"absent").hexdigest(),
        }
    )
    plugin = _load_with_contracts(tmp_path, files, descriptor)
    try:
        assert plugin._dataset is None
    finally:
        plugin.plugin_close()


def test_unparsable_contract_refused_at_load(tmp_path: Path) -> None:
    files = {"contracts/broken.json": b"{not json"}
    with pytest.raises(ActivationRejected, match="contract_unparsable"):
        _load_with_contracts(tmp_path, files, _contracts_descriptor(files))


# --- fix wave F2: the probe roots where the runtime validators root --------------


def _two_action_catalog() -> dict[str, Any]:
    """A catalog whose action A references sibling action B by a valid
    DOCUMENT-root pointer — resolvable against the catalog document (the
    document-rooted probe passes it) but unresolvable at the runtime root,
    where I4 validates against the per-action SUBSCHEMA alone. The
    sibling's id carries no slash: a JSON Pointer splits on '/', so a
    slashed id would fail under ANY rooting (an escape-level accident,
    not the rooting defect this fixture isolates)."""
    catalog = _synthetic_catalog()
    catalog["actions"]["demo_sibling"] = {
        "description": "The referenced sibling (invented fixture name).",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "side_effect": "none",
        "lifecycle": "direct",
    }
    catalog["actions"]["demo.act/1.0.0"]["input_schema"] = {
        "type": "object",
        "properties": {
            "x": {"$ref": "#/actions/demo_sibling/input_schema"},
        },
    }
    return catalog


def test_f2_same_document_relative_ref_refused_at_load(tmp_path: Path) -> None:
    """F2 fixture 1: a document-root pointer that walks outside the action
    subschema passes the document-rooted probe but raises PointerToNowhere
    at first dispatch (the I4 validator's root is the action schema). The
    corrected probe refuses it at LOAD."""
    measurement = _corpus_bytes("otdp-measurement.schema.json")
    files = {
        "contracts/catalog.json": json.dumps(_two_action_catalog()).encode(),
        "contracts/measurement.json": measurement,
    }
    with pytest.raises(ActivationRejected, match="contract_ref_unresolvable"):
        _load_with_contracts(tmp_path, files, _contracts_descriptor(files))


def test_f2_dangling_dynamic_ref_refused_at_load(tmp_path: Path) -> None:
    """F2 fixture 2: a dangling ``$dynamicRef`` (no matching dynamic anchor
    or def anywhere in the pinned set) is not walked by the ``$ref``-only
    probe and raises NoSuchAnchor/_WrappedReferencingError at first
    dispatch. The corrected probe walks ``$dynamicRef`` too and refuses at
    LOAD."""
    catalog = _synthetic_catalog()
    catalog["actions"]["demo.act/1.0.0"]["input_schema"] = {
        "type": "object",
        "$dynamicRef": "#/$defs/absent",
    }
    measurement = _corpus_bytes("otdp-measurement.schema.json")
    files = {
        "contracts/catalog.json": json.dumps(catalog).encode(),
        "contracts/measurement.json": measurement,
    }
    with pytest.raises(ActivationRejected, match="contract_ref_unresolvable"):
        _load_with_contracts(tmp_path, files, _contracts_descriptor(files))


def test_f2_legitimate_dynamic_ref_pair_still_loads(tmp_path: Path) -> None:
    """The probe's dynamic walk must not refuse LEGAL dynamic references:
    a recursive ``$dynamicAnchor``/``$dynamicRef`` pair (the 2020-12
    recursive-schema idiom) fully in-bundle resolves and the pair loads."""
    catalog = _synthetic_catalog()
    catalog["actions"]["demo.act/1.0.0"]["input_schema"] = {
        "type": "object",
        "$defs": {
            "node": {
                "$dynamicAnchor": "payload",
                "type": "object",
                "properties": {"next": {"$dynamicRef": "#payload"}},
            }
        },
        "properties": {"root": {"$dynamicRef": "#payload"}},
    }
    measurement = _corpus_bytes("otdp-measurement.schema.json")
    files = {
        "contracts/catalog.json": json.dumps(catalog).encode(),
        "contracts/measurement.json": measurement,
    }
    plugin = _load_with_contracts(tmp_path, files, _contracts_descriptor(files))
    try:
        assert plugin._dataset is not None
    finally:
        plugin.plugin_close()


def test_f3_self_contained_catalog_without_measurement_is_soft(tmp_path: Path) -> None:
    """F3 — the catalog half of the both-or-neither pair, pinned: a
    SELF-CONTAINED catalog (every reference resolvable at its per-action
    runtime root — here none at all) pinned without the measurement schema
    resolves cleanly, refuses nothing at load, and constructs NO class
    surface: the bridge loads with `_dataset is None` and invoke stays a
    verb-level UNSUPPORTED. The real corpus catalog cannot express this
    arm (its measurement-urn refs refuse at load through the probe), so
    the synthetic ref-free catalog is the arm's only in-tree witness."""
    files = {"contracts/catalog.json": json.dumps(_synthetic_catalog()).encode()}
    plugin = _load_with_contracts(tmp_path, files, _contracts_descriptor(files))
    try:
        assert plugin._dataset is None
    finally:
        plugin.plugin_close()


def test_f4_degenerate_measurement_dataset_required_refused_at_load(
    tmp_path: Path,
) -> None:
    """F4: a pinned measurement schema whose ``$defs/dataset`` declares an
    EMPTY (or absent) required set degenerates the dataset-shape detector —
    ``frozenset() <= set(anything)`` matches every object, so every dict
    result would poison as a "dataset". Present bytes that lie: the pair
    refuses at LOAD."""
    degenerate = {
        "$id": "urn:otdp:measurement:degenerate",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": {"dataset": {"type": "object"}},
    }
    files = {
        "contracts/catalog.json": json.dumps(_synthetic_catalog()).encode(),
        "contracts/measurement.json": json.dumps(degenerate).encode(),
    }
    with pytest.raises(ActivationRejected, match="contract_measurement_degenerate"):
        _load_with_contracts(tmp_path, files, _contracts_descriptor(files))
