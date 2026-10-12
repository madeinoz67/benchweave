"""The device presentation page: through the gateway's OWN validator
(G2b, design §2.4 device pages — GW-21/22/23, SW-41's parity rule).

The page resolves the plugin's presentation attachment from ADMITTED
documents (envelope, manifest, binding catalogue, assets — all
content-addressed), validates through
``presentation.admission.validate_attachment`` — the same bytes the SDK
host uses — and renders the manifest's pages: unavailable required
panels render the ``panel_unavailable`` refusal, unavailable optional
panels render unavailable, and readings tiles populate ONLY from
gateway-reported observations (GW-22: in G2 there is no observation
lane, so tiles render ``Unavailable`` — never a submitted or fabricated
value). Staleness (GW-23) computes from the observation's OWN timestamp
through ``staleness.staleness`` — pinned here at the composition seam,
because no live observation exists to drive it on a page.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from benchweave_ui_html.staleness import staleness
from starlette.testclient import TestClient
from ui_gateway_support import NOW_ISO, build_ui_gateway, live_session

from benchweave.content.store import ContentStore
from benchweave.interfaces.ui_presentation import (
    compose_device_presentation,
    reading_staleness,
)
from benchweave.state.store import Store

ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_UI = next(
    entry["version"]
    for entry in json.loads(
        (ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
    )["standards"]
    if entry["id"] == "plugin-ui"
)


def _encode(value: object) -> bytes:
    return json.dumps(value).encode()


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Any:
    data_dir = tmp_path_factory.mktemp("ui-present")
    app = build_ui_gateway(data_dir, name="presentation")
    store = Store.open(
        str(data_dir / "state-presentation.sqlite"), check_same_thread=False
    )
    content = ContentStore(store)
    session = live_session(app)
    with TestClient(app, base_url="http://testserver:8125") as client:
        # The fixture bench's device (startup admission).
        devices, _ = app.state.ui_operations.device_list(
            _identity_for("ui-shell", {"stg:observe"}), "sim-bench", limit=10, cursor=None
        )
        yield SimpleNamespace(
            app=app, client=client, session=session, content=content,
            device=devices[0],
        )
    store.close()


def _identity_for(principal: str, scopes: set[str]) -> Any:
    from benchweave.interfaces.identity import Identity

    return Identity(
        principal=principal, audience="stg", scopes=frozenset(scopes), expires_at=2**31
    )


def _descriptor(gateway: SimpleNamespace) -> tuple[bytes, dict[str, Any]]:
    """The page device's OWN descriptor bytes, fetched through the seam
    (``document_get`` on the projection's pinned digest — the same bytes
    the page resolves the attachment for)."""
    operations = gateway.app.state.ui_operations
    document = operations.document_get(
        _identity_for("ui-shell", {"stg:observe"}),
        str(gateway.device["descriptor"]["sha256"]),
    )
    import base64

    raw = base64.b64decode(document["original_utf8_base64"])
    return raw, json.loads(raw)


def _admit_attachment(
    content: ContentStore,
    descriptor_raw: bytes,
    *,
    pages: list[dict[str, Any]] | None = None,
) -> str:
    """Admit envelope + manifest + catalogue as documents; return the
    envelope's digest. The default manifest carries one readings page and
    one optional custom panel; ``pages`` overrides."""
    descriptor_digest = _digest(descriptor_raw)
    manifest = {
        "contract_version": _PLUGIN_UI,
        "plugin_id": json.loads(descriptor_raw)["id"],
        "descriptor_sha256": descriptor_digest,
        "bindings": [
            {"id": "reading", "kind": "observation", "target_id": "voltage"}
        ],
        "pages": pages
        if pages is not None
        else [
            {
                "id": "readings",
                "title": "Readings",
                "kind": "readings",
                "bindings": ["reading"],
                "required": True,
            },
            {
                "id": "custom",
                "title": "Custom",
                "kind": "custom_panel",
                "panel_id": "custom/1.0.0",
                "bindings": [],
                "required": False,
            },
        ],
    }
    manifest_raw = _encode(manifest)
    catalogue = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": descriptor_digest,
        "targets": [
            {
                "id": "voltage",
                "kind": "observation",
                "parameter_id": "output_voltage",
                "variables": [
                    {
                        "id": "time",
                        "type": "number",
                        "unit": "s",
                        "shape": "scalar",
                        "axis_role": "receipt_time",
                    },
                    {
                        "id": "value",
                        "type": "number",
                        "unit": "V",
                        "shape": "scalar",
                        "axis_role": "value",
                    },
                ],
            }
        ],
    }
    envelope = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": descriptor_digest,
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": _digest(manifest_raw)},
    }
    envelope_raw = _encode(envelope)
    for raw, parsed, schema in (
        (manifest_raw, manifest, f"https://benchweave.dev/contracts/plugin-ui/{_PLUGIN_UI}/ui-manifest.schema.json"),
        (_encode(catalogue), catalogue, f"https://benchweave.dev/contracts/plugin-ui/{_PLUGIN_UI}/binding-catalogue.schema.json"),
        (envelope_raw, envelope, f"https://benchweave.dev/contracts/plugin-ui/{_PLUGIN_UI}/presentation-envelope.schema.json"),
    ):
        content.put_document(raw, _digest(raw), parsed, schema, NOW_ISO)
    return _digest(envelope_raw)


# --- the honest absence ----------------------------------------------------------


def test_device_without_attachment_renders_absence(gateway: SimpleNamespace) -> None:
    """The fixture devices carry no presentation attachment — the page
    says so instead of inventing panels."""
    response = gateway.client.get(
        f"/ui/benches/sim-bench/devices/{gateway.device['device_id']}",
        cookies={"bw_session": gateway.session.session_id},
    )
    assert response.status_code == 200
    assert "data-bw-device-page" in response.text
    assert "data-bw-presentation-absent" in response.text


# --- the validated attachment ----------------------------------------------------


def test_valid_attachment_renders_pages_with_unavailable_readings(
    gateway: SimpleNamespace,
) -> None:
    descriptor_raw, _ = _descriptor(gateway)
    _admit_attachment(gateway.content, descriptor_raw)
    response = gateway.client.get(
        f"/ui/benches/sim-bench/devices/{gateway.device['device_id']}",
        cookies={"bw_session": gateway.session.session_id},
    )
    assert response.status_code == 200
    page = response.text
    assert "data-bw-presentation-pages" in page
    # The readings page renders its tile — GW-22: only gateway-reported
    # observations populate tiles; G2 has no observation lane, so the
    # value is Unavailable, never a fabricated or submitted number.
    assert "data-bw-presentation-page-readings" in page
    tile_mark = page.find('data-bw-presentation-page-readings')
    assert "Unavailable" in page[tile_mark:], "the unobserved tile renders Unavailable"
    # The optional custom panel renders unavailable (SW-41).
    assert "data-bw-presentation-page-custom" in page
    assert "data-bw-panel-unavailable-note" in page


def test_required_unavailable_panel_renders_the_panel_unavailable_refusal(
    gateway: SimpleNamespace,
) -> None:
    descriptor_raw, _ = _descriptor(gateway)
    _admit_attachment(
        gateway.content,
        descriptor_raw,
        pages=[
            {
                "id": "must",
                "title": "Must",
                "kind": "custom_panel",
                "panel_id": "custom/1.0.0",
                "bindings": [],
                "required": True,
            }
        ],
    )
    response = gateway.client.get(
        f"/ui/benches/sim-bench/devices/{gateway.device['device_id']}",
        cookies={"bw_session": gateway.session.session_id},
    )
    assert response.status_code == 200
    # SW-41 as a refusal: the required panel the host lacks fails
    # panel_unavailable — the validator's own finding, rendered.
    assert 'data-bw-panel-unavailable="must"' in response.text


# --- GW-23: staleness from the observation's own timestamp -----------------------


def test_reading_staleness_is_the_contract_predicate() -> None:
    """The composition's staleness IS ``staleness.staleness`` — ST-2's
    strict boundary, computed from the observation's age, never the
    page's."""
    assert reading_staleness(1000.0, 2000.0) == "fresh"
    assert reading_staleness(2000.0, 2000.0) == "fresh"  # equality is not stale
    assert reading_staleness(2000.1, 2000.0) == "stale"
    assert reading_staleness(None, 2000.0) == "no-verdict"  # no observation
    assert reading_staleness(1000.0, None) == "no-verdict"  # no cadence
    assert reading_staleness(1000.0, 0.0) == "stale"  # fresh-acquisition-only
    assert reading_staleness is staleness or reading_staleness(1.0, 2.0) == staleness(
        1.0, 2.0
    )


# --- isolation: another bench's namespace ---------------------------------------


def test_device_page_under_wrong_bench_is_not_found(gateway: SimpleNamespace) -> None:
    """I02's cross-bench read arm: the device exists, but not on THAT
    bench — the seam's own bench-scoped lookup renders not_found as
    unavailable-to-caller (never an existence leak)."""
    response = gateway.client.get(
        f"/ui/benches/other-bench/devices/{gateway.device['device_id']}",
        cookies={"bw_session": gateway.session.session_id},
    )
    assert response.status_code == 404
    assert 'data-bw-refusal-code="not_found"' in response.text
    assert "unavailable to this caller" in response.text


# --- the F1 fold at the consumer: admission ordering picks the CURRENT attachment


def test_re_admitted_identical_attachment_does_not_shadow_the_newer_one(
    gateway: SimpleNamespace,
) -> None:
    """The lane's repro at the PAGE level: admit attachment v1 (page id
    readings-v1), admit attachment v2 (page id readings-v2 — a new digest,
    a new admission), re-admit v1's IDENTICAL bytes — the device page
    still renders v2. A same-digest re-admission is idempotent (the F1
    ruling); under INSERT OR REPLACE it shadowed v2 and the page regressed
    to the stale attachment."""
    descriptor_raw, _ = _descriptor(gateway)
    # v1: a readings page with id readings-v1.
    _admit_attachment(
        gateway.content,
        descriptor_raw,
        pages=[
            {
                "id": "readings-v1",
                "title": "Readings v1",
                "kind": "readings",
                "bindings": ["reading"],
                "required": True,
            }
        ],
    )
    # v2: different manifest bytes -> a new digest -> a new admission.
    _admit_attachment(
        gateway.content,
        descriptor_raw,
        pages=[
            {
                "id": "readings-v2",
                "title": "Readings v2",
                "kind": "readings",
                "bindings": ["reading"],
                "required": True,
            }
        ],
    )
    # Re-admit v1's exact bytes (same manifest shape -> same digests).
    _admit_attachment(
        gateway.content,
        descriptor_raw,
        pages=[
            {
                "id": "readings-v1",
                "title": "Readings v1",
                "kind": "readings",
                "bindings": ["reading"],
                "required": True,
            }
        ],
    )
    response = gateway.client.get(
        f"/ui/benches/sim-bench/devices/{gateway.device['device_id']}",
        cookies={"bw_session": gateway.session.session_id},
    )
    assert response.status_code == 200
    page = response.text
    assert "data-bw-presentation-page-readings-v2" in page, (
        "the re-admitted identical v1 shadowed the newer v2 attachment"
    )
    assert "data-bw-presentation-page-readings-v1" not in page


# --- issue #446 slice 1: the gateway document-set parity fix ----------------------
#
# The device page's validator drew its schema documents from the ACTIVE
# plugin-ui schemas alone (four documents): the presentation checker's
# profile map was empty and OTDP action-schema urns were unresolvable, so
# EVERY invoke-kind target — including the in-tree sim_scope attachment's
# own configuration target — composed INVALID on the gateway while the
# same bytes validated on the SDK host (SW-41's parity rule; the issue
# #446 design record's arm C). The composition must serve the document set
# the SDK's schemas() serves: the carried OTDP corpus joined with the
# plugin-ui schemas.

_SIM_SCOPE_PLUGIN = (
    ROOT / "plugins" / "benchweave" / "sim_scope" / "src" / "benchweave_sim_scope"
)
_SCHEMA_PREFIX = f"https://benchweave.dev/contracts/plugin-ui/{_PLUGIN_UI}"
_CORPUS_ARM_ACTION = "otdp.oscilloscope.arm/1.0.0"
_LA34_CAPTURE_ACTION = "vendor.la34.capture/1.0.0"


@pytest.fixture(scope="module")
def sim_scope_attachment(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """The plugin's SHIPPED presentation attachment — envelope, manifest,
    binding catalogue and the manifest's assets, admitted into a bare
    content store exactly as the device page would find them (content-
    addressed rows, descriptor-pinned)."""
    store = Store.open(
        str(tmp_path_factory.mktemp("sim-scope-446") / "state.sqlite"),
        check_same_thread=False,
    )
    content = ContentStore(store)
    descriptor_raw = (_SIM_SCOPE_PLUGIN / "descriptor.json").read_bytes()
    manifest_raw = (_SIM_SCOPE_PLUGIN / "ui" / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    for raw, schema in (
        (
            (_SIM_SCOPE_PLUGIN / "presentation.json").read_bytes(),
            f"{_SCHEMA_PREFIX}/presentation-envelope.schema.json",
        ),
        (manifest_raw, f"{_SCHEMA_PREFIX}/ui-manifest.schema.json"),
        (
            (_SIM_SCOPE_PLUGIN / "binding-catalogue.json").read_bytes(),
            f"{_SCHEMA_PREFIX}/binding-catalogue.schema.json",
        ),
    ):
        content.put_document(raw, _digest(raw), json.loads(raw), schema, NOW_ISO)
    for asset in manifest["assets"]:
        raw = (_SIM_SCOPE_PLUGIN / "ui" / str(asset["path"])).read_bytes()
        content.put_document(raw, _digest(raw), json.loads(raw), str(asset["id"]), NOW_ISO)
    yield SimpleNamespace(content=content, descriptor_raw=descriptor_raw)
    store.close()


def test_sim_scope_attachment_composes_valid(sim_scope_attachment: Any) -> None:
    """M-D (the design's arm C): the in-tree sim_scope attachment — whose
    only target is an invoke-kind configuration target bound to the corpus
    oscilloscope profile — composes VALID through the gateway's own
    validator, the verdict the SDK host gives the same bytes. RED on the
    pre-fix tree: the four-schema document set left capability_mismatch
    and unresolved_reference on targets.configure."""
    state = compose_device_presentation(
        sim_scope_attachment.content, sim_scope_attachment.descriptor_raw
    )
    assert state.absence is None
    assert state.valid, state.findings
    assert [(page.page_id, page.available) for page in state.pages] == [
        ("settings", True)
    ]


def _la34_descriptor(actions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """A synthetic invoke-capable descriptor (invented identity): the
    corpus oscilloscope class surface plus whatever actions the arm
    plants."""
    return {
        "otdp_version": "0.2.2",
        "descriptor_version": "1.0.0",
        "id": "dev.la34.corner-scope",
        "display_name": "LA34 corner scope (synthetic)",
        "identity": {"firmware_policy": "any", "supported_firmware": ["la-1.0.0"]},
        "capabilities": ["invoke"],
        "profiles": ["otdp.oscilloscope/1.0.0"],
        "actions": actions,
    }


def _descriptor_action(action_id: str) -> dict[str, Any]:
    return {
        "binding": {"kind": "adapter", "key": action_id},
        "input_constraints": {},
        "timeout_ms": 1000,
        "side_effect": "state_change",
        "cancellable": True,
        "retry": "never",
    }


def _admit_procedure_attachment(
    content: ContentStore, descriptor: dict[str, Any], action_id: str
) -> bytes:
    """Admit a minimal invoke-kind attachment around one procedure target
    (the lightest schema-valid invoke shape: action_id + profile_ids +
    input_schema_id) bound to the corpus oscilloscope profile; return the
    descriptor bytes."""
    descriptor_raw = _encode(descriptor)
    descriptor_digest = _digest(descriptor_raw)
    manifest = {
        "contract_version": _PLUGIN_UI,
        "plugin_id": descriptor["id"],
        "descriptor_sha256": descriptor_digest,
        "bindings": [{"id": "act", "kind": "procedure", "target_id": "act"}],
        "pages": [
            {
                "id": "controls",
                "title": "Controls",
                "kind": "configuration",
                "bindings": ["act"],
                "required": True,
            }
        ],
    }
    manifest_raw = _encode(manifest)
    catalogue = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": descriptor_digest,
        "targets": [
            {
                "id": "act",
                "kind": "procedure",
                "action_id": action_id,
                "profile_ids": ["otdp.oscilloscope/1.0.0"],
                "input_schema_id": "urn:otdp:action:oscilloscope.arm:1.0.0:input",
            }
        ],
    }
    catalogue_raw = _encode(catalogue)
    envelope = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": descriptor_digest,
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": _digest(manifest_raw)},
    }
    for raw, schema in (
        (_encode(envelope), f"{_SCHEMA_PREFIX}/presentation-envelope.schema.json"),
        (manifest_raw, f"{_SCHEMA_PREFIX}/ui-manifest.schema.json"),
        (catalogue_raw, f"{_SCHEMA_PREFIX}/binding-catalogue.schema.json"),
    ):
        content.put_document(raw, _digest(raw), json.loads(raw), schema, NOW_ISO)
    return descriptor_raw


def test_invoke_target_bound_to_a_corpus_profile_composes_valid(
    tmp_path: Path,
) -> None:
    """The general case behind #446 (the design's arm D at the composition
    seam): an invoke-kind target whose profile rows and action schema come
    from the trusted-host corpus composes VALID — binding stays profile-
    sourced with zero plugin-pinned documents. RED on the pre-fix tree."""
    store = Store.open(str(tmp_path / "state.sqlite"), check_same_thread=False)
    content = ContentStore(store)
    try:
        descriptor = _la34_descriptor(
            {_CORPUS_ARM_ACTION: _descriptor_action(_CORPUS_ARM_ACTION)}
        )
        descriptor_raw = _admit_procedure_attachment(content, descriptor, _CORPUS_ARM_ACTION)
        state = compose_device_presentation(content, descriptor_raw)
        assert state.absence is None
        assert state.valid, state.findings
    finally:
        store.close()


def test_target_action_present_in_no_validated_profile_refuses(
    tmp_path: Path,
) -> None:
    """M-B, the negative control that must SURVIVE the fix: the action
    exists in descriptor.actions and the bound profile is corpus-carried,
    but NO validated profile supplies the action — binding stays profile-
    sourced (capability_mismatch), never descriptor-actions-sourced."""
    store = Store.open(str(tmp_path / "state.sqlite"), check_same_thread=False)
    content = ContentStore(store)
    try:
        actions = {
            _CORPUS_ARM_ACTION: _descriptor_action(_CORPUS_ARM_ACTION),
            _LA34_CAPTURE_ACTION: _descriptor_action(_LA34_CAPTURE_ACTION),
        }
        descriptor = _la34_descriptor(actions)
        descriptor_raw = _admit_procedure_attachment(content, descriptor, _LA34_CAPTURE_ACTION)
        state = compose_device_presentation(content, descriptor_raw)
        assert state.valid is False
        assert any(
            code == "capability_mismatch" and path == "targets.act"
            for code, path, _message in state.findings
        )
    finally:
        store.close()


def test_presentation_documents_serve_the_carried_otdp_corpus() -> None:
    """The composition's document set is the SDK host's: every CARRIED OTDP
    version's documents (yanked-but-carried included — an explicit pin to a
    yanked-in-interval version stays conforming and needs its bytes
    offline), path-keyed, $id-aliased, with the per-action subschema
    expansion. RED on the pre-fix tree (the set carried plugin-ui schemas
    only)."""
    import benchweave.interfaces.ui_presentation as presentation_module
    from benchweave.standards.manifest import (
        load_dependency_policy_from_corpus,
        retained_versions_from_corpus,
    )
    from benchweave.vendoring import corpus_root

    # The RED commit precedes the mechanism: getattr (with a documented
    # default) keeps this file mypy-clean while the builder is absent —
    # the assertion below is the RED failure — and the FEAT commit that
    # lands _presentation_documents restores the static import.
    presentation_documents = getattr(presentation_module, "_presentation_documents", None)
    assert presentation_documents is not None, (
        "the composition module serves no document-set builder "
        "(pre-fix: the active plugin-ui schemas only)"
    )

    corpus = corpus_root()
    policy = load_dependency_policy_from_corpus(corpus)
    row = policy.standards["otdp"]
    carried = tuple(
        version
        for version in retained_versions_from_corpus(corpus, "otdp")
        if row.in_range(version)
    )
    assert carried, "the corpus carries OTDP versions at all"
    documents = presentation_documents()
    for version in carried:
        assert f"otdp/{version}/device-profile-catalog.json" in documents
        assert f"urn:otdp:measurement:{version}" in documents
    # The profile map the invoke-branch target check reads (the checker's
    # documents-driven comprehension) is regenerable from the served set:
    profiles = {
        profile["id"]: profile
        for document in documents.values()
        for profile in (document.get("profiles") or [])
        if isinstance(profile, dict) and "id" in profile
    }
    oscilloscope = profiles["otdp.oscilloscope/1.0.0"]
    assert _CORPUS_ARM_ACTION in (
        oscilloscope.get("required_actions", [])
        + oscilloscope.get("optional_actions", [])
    )
    # The action-schema expansion (an unversioned urn shared across
    # carried versions — highest carried version's rows, the SDK's
    # last-wins) and the plugin-ui schemas, still keyed by $id:
    assert "urn:otdp:action:oscilloscope.configure:1.0.0:input" in documents
    manifest_schema = documents[f"{_SCHEMA_PREFIX}/ui-manifest.schema.json"]
    assert "catalogue" in manifest_schema["$defs"]


def test_a_served_document_cannot_shadow_a_plugin_ui_schema_id(
    tmp_path: Path,
) -> None:
    """The composition's namespace guard (design risk 1's poisoning
    vector): a served document's $id alias may not displace a plugin-ui
    schema. The OTDP install happens first; the plugin-ui schemas install
    LAST and overwrite — a fabricated colliding $id loses the key, so the
    attachment keeps validating against the true schema bytes."""
    import benchweave.interfaces.ui_presentation as presentation_module
    from benchweave.vendoring import corpus_root

    # Same getattr posture as the served-set arm: the helpers are absent on
    # the pre-fix tree and the FEAT commit restores the static imports.
    serve_otdp_documents = getattr(presentation_module, "_serve_otdp_documents", None)
    install_plugin_ui_schemas = getattr(
        presentation_module, "_install_plugin_ui_schemas", None
    )
    assert serve_otdp_documents is not None and install_plugin_ui_schemas is not None, (
        "the composition module exposes no served-document install seam "
        "(pre-fix: the active plugin-ui schemas only)"
    )

    planted_id = f"{_SCHEMA_PREFIX}/ui-manifest.schema.json"
    planted_dir = tmp_path / "otdp" / "9.9.9"
    planted_dir.mkdir(parents=True)
    (planted_dir / "planted-catalog.json").write_text(
        json.dumps({"$id": planted_id, "planted": True})
    )
    documents: dict[str, dict[str, Any]] = {}
    serve_otdp_documents(documents, planted_dir, "otdp/9.9.9")
    # The alias install is real — without the ordering guard the planted
    # document would sit at the manifest schema's key:
    assert documents[planted_id].get("planted") is True
    install_plugin_ui_schemas(documents, corpus_root())
    assert documents[planted_id].get("planted") is None
    assert "catalogue" in documents[planted_id]["$defs"]
