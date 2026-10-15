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
import re
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
from benchweave.vendoring import corpus_root

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
    from benchweave.interfaces.ui_presentation import _presentation_documents
    from benchweave.standards.manifest import (
        load_dependency_policy_from_corpus,
        retained_versions_from_corpus,
    )
    from benchweave.vendoring import corpus_root

    corpus = corpus_root()
    policy = load_dependency_policy_from_corpus(corpus)
    row = policy.standards["otdp"]
    carried = tuple(
        version
        for version in retained_versions_from_corpus(corpus, "otdp")
        if row.in_range(version)
    )
    assert carried, "the corpus carries OTDP versions at all"
    documents = _presentation_documents()
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
    from benchweave.interfaces.ui_presentation import (
        _install_plugin_ui_schemas,
        _serve_otdp_documents,
    )
    from benchweave.vendoring import corpus_root

    planted_id = f"{_SCHEMA_PREFIX}/ui-manifest.schema.json"
    planted_raw = json.dumps({"$id": planted_id, "planted": True}).encode()
    planted_dir = tmp_path / "otdp" / "9.9.9"
    planted_dir.mkdir(parents=True)
    (planted_dir / "planted-catalog.json").write_bytes(planted_raw)
    documents: dict[str, dict[str, Any]] = {}
    # The walk's contract carries the digest rows it verifies against —
    # hand-built for the planted file (this arm exercises the ordering
    # guard, not the gate).
    _serve_otdp_documents(
        documents,
        planted_dir,
        "otdp/9.9.9",
        {"otdp/9.9.9/planted-catalog.json": _digest(planted_raw)},
    )
    # The alias install is real — without the ordering guard the planted
    # document would sit at the manifest schema's key:
    assert documents[planted_id].get("planted") is True
    # pins=None is the absent-manifest tolerance — this arm does not
    # exercise the gate.
    _install_plugin_ui_schemas(documents, corpus_root(), None)
    assert documents[planted_id].get("planted") is None
    assert "catalogue" in documents[planted_id]["$defs"]


# --- the #446 slice-1 fold: the corpus digest gate (adversary F1) -----------------
#
# F1 (MEDIUM): the corpus walk json.loads'd whatever the tree carried — no
# digest verification. The refute reproduced three shapes: (a) a tampered
# but manifest-recorded file served silently; (b) an unrecorded planted file
# served; (c) blast radius — a planted examples/ document carrying the
# daq.fetch output-schema urn DISPLACED the real schema at that urn. The SDK
# host refuses all three at load (#215 F1's ``vendored_digest_mismatch``);
# SW-41 parity says the gateway refuses at build with the typed
# ``corpus_pin_mismatch`` finding.

_HIJACK_URN = "urn:otdp:action:daq.fetch:1.0.0:output"


@pytest.fixture()
def cold_gate_cache() -> Any:
    """The gate arms build from a /tmp corpus copy: clear the document
    cache around each arm so a warm REAL-corpus entry can neither satisfy
    nor shadow the patched-root build, and the tampered-tree arms leave
    nothing behind for the real-corpus arms."""
    from benchweave.interfaces.ui_presentation import _presentation_documents_cached

    _presentation_documents_cached.cache_clear()
    yield
    _presentation_documents_cached.cache_clear()


def _gate_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A /tmp copy of the real corpus with the seam's ``corpus_root``
    monkeypatched at it — every arm edits the COPY, never the committed
    tree."""
    import shutil

    from benchweave.interfaces import ui_presentation
    from benchweave.vendoring import corpus_root

    corpus = tmp_path / "standards"
    shutil.copytree(corpus_root(), corpus)
    monkeypatch.setattr(ui_presentation, "corpus_root", lambda: corpus)
    return corpus


def _highest_carried_otdp_version() -> str:
    from benchweave.standards.manifest import (
        load_dependency_policy_from_corpus,
        retained_versions_from_corpus,
    )
    from benchweave.vendoring import corpus_root

    corpus = corpus_root()
    policy = load_dependency_policy_from_corpus(corpus)
    row = policy.standards["otdp"]
    carried = [
        version
        for version in retained_versions_from_corpus(corpus, "otdp")
        if row.in_range(version)
    ]
    assert carried, "the corpus carries OTDP versions at all"
    return carried[-1]


def test_tampered_recorded_corpus_file_refuses_the_document_set_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cold_gate_cache: Any
) -> None:
    """F1 shape (a): a manifest-RECORDED corpus document edited in place
    (manifest untouched) refuses the build with the typed digest finding —
    the tampered catalog never silently becomes the profile map an
    invoke-kind target resolves against. RED pre-gate: the walk served
    the tampered bytes."""
    from benchweave.interfaces.ui_presentation import _presentation_documents
    from benchweave.standards.manifest import StandardsError

    corpus = _gate_corpus(tmp_path, monkeypatch)
    version = _highest_carried_otdp_version()
    target = corpus / "otdp" / version / "device-profile-catalog.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    document["tampered_marker"] = "edited-in-place"
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(
        StandardsError,
        match=(
            rf"corpus_pin_mismatch: otdp/{version}/device-profile-catalog\.json "
            r"hashes to [0-9a-f]{64} but the manifest pins [0-9a-f]{64}"
        ),
    ):
        _presentation_documents()


def test_unrecorded_planted_corpus_file_refuses_the_document_set_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cold_gate_cache: Any
) -> None:
    """F1 shape (b): a planted file the corpus manifest does not record
    refuses the build — the walk serves recorded bytes only. RED pre-gate:
    the planted file was served like any other."""
    from benchweave.interfaces.ui_presentation import _presentation_documents
    from benchweave.standards.manifest import StandardsError

    corpus = _gate_corpus(tmp_path, monkeypatch)
    version = _highest_carried_otdp_version()
    planted = corpus / "otdp" / version / "examples" / "zz-planted.json"
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text(json.dumps({"planted": True}), encoding="utf-8")
    with pytest.raises(
        StandardsError,
        match=(
            rf"corpus_pin_mismatch: otdp/{version}/examples/zz-planted\.json "
            r"is present in the corpus tree but not recorded by the corpus "
            r"manifest"
        ),
    ):
        _presentation_documents()


def test_planted_action_urn_hijack_refuses_instead_of_displacing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cold_gate_cache: Any
) -> None:
    """F1 shape (c), the blast radius: a planted examples/ document whose
    ``$id`` names the daq.fetch OUTPUT-schema urn used to DISPLACE the real
    schema at that urn (the sorted walk visits zz-* last, so the planted
    $id alias overwrote the catalog's subschema expansion) — an
    attachment's documents would then resolve plugin-authored bytes. The
    gate refuses the build before any displacement can install. RED
    pre-gate: the hijack installed."""
    from benchweave.interfaces.ui_presentation import _presentation_documents
    from benchweave.standards.manifest import StandardsError

    corpus = _gate_corpus(tmp_path, monkeypatch)
    version = _highest_carried_otdp_version()
    hijack = corpus / "otdp" / version / "examples" / "zz-hijack.json"
    hijack.parent.mkdir(parents=True, exist_ok=True)
    hijack.write_text(
        json.dumps({"$id": _HIJACK_URN, "hijacked": True}), encoding="utf-8"
    )
    with pytest.raises(
        StandardsError,
        match=rf"corpus_pin_mismatch: otdp/{version}/examples/zz-hijack\.json",
    ):
        _presentation_documents()


# --- the L4 class-reference fallback (design record 2026-10-15 §1) ---------------
#
# A class-shaped descriptor with NO admitted envelope derives its default
# presentation read-time: the attachment triple composes from (descriptor ×
# corpus reference), validates through the UNCHANGED validate_attachment,
# and renders visibly host-derived (data-bw-presentation-derived + the
# disclosure). Unknown classes fail OPEN — the no-attachment note
# byte-identical to the pre-L4 render (the committed baseline). Fail-closed
# derivations render their typed classref_* finding, never a partial page.

_F1 = Path(__file__).resolve().parents[1] / "presentation" / "classref_fixtures"


def _f1_descriptor_raw(tag: str = "f1") -> bytes:
    return (_F1 / f"descriptor-{tag}.json").read_bytes()


def _vendor_catalog_map() -> dict[str, bytes]:
    raw = (_F1 / "vendor-catalog.json").read_bytes()
    return {hashlib.sha256(raw).hexdigest(): raw}


def _admit_vendor_catalog(gateway: SimpleNamespace) -> None:
    """Admit the fixture vendor catalog into the composition store by
    digest — the admission-store resolution the fallback reads (the same
    shape plugin admission produces for pinned contract documents)."""
    raw = (_F1 / "vendor-catalog.json").read_bytes()
    gateway.content.put_document(
        raw,
        hashlib.sha256(raw).hexdigest(),
        json.loads(raw),
        "urn:x:classref-vendor-catalog",
        NOW_ISO,
    )


def test_classref_descriptor_without_attachment_derives_presentation(
    gateway: SimpleNamespace,
) -> None:
    """B1 (F1 arm, state level): the class-shaped descriptor with no
    admitted envelope composes the derived presentation — 3/3 pages per
    the reference (capture + configuration + device-features), valid=True
    through the unchanged validator, visibly derived."""
    _admit_vendor_catalog(gateway)
    state = compose_device_presentation(gateway.content, _f1_descriptor_raw("f1"))
    assert state.absence is None
    assert state.derived is True
    assert state.valid is True, state.findings
    assert [page.page_id for page in state.pages] == [
        "capture",
        "configuration",
        "device-features",
    ]


def test_f2_derives_the_full_lane_inventory(gateway: SimpleNamespace) -> None:
    """B1 (F2 arm): the 32-channel descriptor derives 32 channel
    variables and the four lane groups the reference's chunking arithmetic
    yields (4 full groups, zero remainder)."""
    _admit_vendor_catalog(gateway)
    state = compose_device_presentation(gateway.content, _f1_descriptor_raw("f2"))
    assert state.absence is None and state.derived is True and state.valid
    capture = next(page for page in state.pages if page.page_id == "capture")
    plot = capture.plots[0]
    assert len(plot["y"]) == 32
    assert [group["label"] for group in plot["lane_groups"]] == [
        "D1-D8",
        "D9-D16",
        "D17-D24",
        "D25-D32",
    ]


def test_derived_pages_render_the_host_derived_marker(
    gateway: SimpleNamespace,
) -> None:
    """B1's render arm: the derived state renders the
    data-bw-presentation-derived marker and the visible disclosure beside
    the pages — the masquerade guard (R2)."""
    _admit_vendor_catalog(gateway)
    state = compose_device_presentation(gateway.content, _f1_descriptor_raw("f1"))
    html = _render_device_page(state)
    assert "data-bw-presentation-derived" in html
    assert "Default class presentation" in html
    assert "no plugin attachment" in html


def test_unknown_class_fails_open_to_the_pre_l4_absence_note(
    gateway: SimpleNamespace,
) -> None:
    """B3: an unknown-class descriptor (no profile with a corpus
    reference) renders today's no-attachment note BYTE-IDENTICAL to the
    committed pre-L4 baseline — the fail-open arm never invents
    obligations the descriptor does not create."""
    descriptor = json.loads(_f1_descriptor_raw("f1"))
    descriptor["id"] = "dev.example.scalar"
    descriptor["profiles"] = ["otdp.dc_psu/1.0.0"]
    descriptor["channels"] = []
    descriptor["actions"] = {}
    descriptor["contracts"] = []
    state = compose_device_presentation(gateway.content, json.dumps(descriptor).encode())
    assert state.absence == "no-attachment"
    assert state.derived is False
    html = _render_device_page(state)
    match = re.search(
        r'<p class="bw-presentation-absent"[^>]*>.*?</p>', html, re.DOTALL
    )
    assert match is not None
    assert match.group(0).encode() == (
        _F1.parent.parent / "interfaces_ui" / "baselines" / "l4-no-attachment-note.html"
    ).read_bytes()


def test_refused_derivation_renders_the_typed_finding(
    gateway: SimpleNamespace,
) -> None:
    """The fail-closed arm: a derivation refusal renders its typed
    classref_* finding (the vendor catalog is not admitted here — the
    gateway resolves pinned vendor catalogs from the admission store),
    never a partial page."""
    descriptor_raw = _f1_descriptor_raw("f1")
    state = compose_device_presentation(
        gateway.content, descriptor_raw, vendor_catalogs={}
    )
    assert state.absence is None
    assert state.valid is False
    assert state.pages == ()
    assert any(
        code == "classref_unknown_action" for code, _path, _message in state.findings
    )


def _schema_invalid_reference_corpus(tmp_path: Path) -> Path:
    """A byte-identical corpus copy whose reference document is pin-valid
    but fails its own schema (``slots`` deleted, pin re-pointed): the
    selection walk's schema gate fires on it (the probe's P1a shape)."""
    import shutil

    probe = tmp_path / "standards"
    shutil.copytree(corpus_root(), probe)
    relpath = "plugin-ui-class-reference/0.1.0/class-logic_analyser.json"
    document = json.loads((probe / relpath).read_bytes())
    del document["slots"]
    raw = json.dumps(document, indent=2).encode()
    (probe / relpath).write_bytes(raw)
    manifest_path = probe / "corpus-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for row in manifest["files"]:
        if str(row["path"]) == relpath:
            row["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
    return probe


def test_schema_invalid_reference_renders_the_typed_finding(
    gateway: SimpleNamespace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A schema-invalid corpus reference renders the typed finding list
    (the fail-closed table's posture) — never an escape that 500s the
    page, never the silent absence."""
    import benchweave.interfaces.ui_presentation as ui_presentation

    probe = _schema_invalid_reference_corpus(tmp_path)
    monkeypatch.setattr(ui_presentation, "corpus_root", lambda: probe)
    state = compose_device_presentation(gateway.content, _f1_descriptor_raw("f1"))
    assert state.absence is None
    assert state.valid is False
    assert state.pages == ()
    assert any(
        code == "classref_invalid_reference"
        for code, _path, _message in state.findings
    )


def test_unserved_corpus_fails_open_to_the_absence_note(
    gateway: SimpleNamespace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A corpus whose family state cannot even be read (no standards
    manifest — the vendor-install arm) renders the honest absence note,
    the same posture the fallback held pre-L4: the corpus-level state
    raise fails OPEN like the per-file selection it wraps, never an
    escape to the page's 500 handler (adversary lane B B2)."""
    import benchweave.interfaces.ui_presentation as ui_presentation

    monkeypatch.setattr(ui_presentation, "corpus_root", lambda: tmp_path)
    state = compose_device_presentation(gateway.content, _f1_descriptor_raw("f1"))
    assert state.absence == "no-attachment"
    assert state.derived is False
    assert state.valid is False
    assert state.pages == ()
    assert state.findings == ()


def test_schema_invalid_reference_route_renders_findings_never_500(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route-level arm: a schema-invalid reference on a class-shaped
    device renders the finding list at 200 — the unhandled escape this
    fold closes made ``device_page`` 500."""
    import benchweave.interfaces.ui_presentation as ui_presentation

    app = build_ui_gateway(tmp_path, name="f1ref-route")
    store = Store.open(
        str(tmp_path / "state-f1ref-route.sqlite"), check_same_thread=False
    )
    content = ContentStore(store)
    session = live_session(app)
    bench, device = "bench-f1ref", "dev-f1ref"
    descriptor_raw = _f1_descriptor_raw("f1")
    store.put_bench(bench, 1, "{}", "{}", "seed", NOW_ISO)
    store.put_device(
        device, bench, 1, "[]", descriptor_raw.decode(), "commissioned",
        "seed", NOW_ISO,
    )
    content.put_document(
        descriptor_raw,
        hashlib.sha256(descriptor_raw).hexdigest(),
        json.loads(descriptor_raw),
        "urn:stg:seed-descriptor",
        NOW_ISO,
    )
    probe = _schema_invalid_reference_corpus(tmp_path)
    monkeypatch.setattr(ui_presentation, "corpus_root", lambda: probe)
    with TestClient(app, base_url="http://testserver:8125",
                    raise_server_exceptions=False) as client:
        response = client.get(
            f"/ui/benches/{bench}/devices/{device}",
            cookies={"bw_session": session.session_id},
        )
    store.close()
    assert response.status_code == 200, response.text[:400]
    assert "classref_invalid_reference" in response.text


def _render_device_page(state: Any) -> str:
    """The device template rendered the route's way (the same environment
    and context shape ui.py's page closure passes; the class-shaped device
    has no fixture bench row, so the render-level arms drive the shared
    template directly)."""
    from benchweave.interfaces.ui import _ENV

    return str(
        _ENV.get_template("device.j2").render(
            title="Device d",
            device={
                "device_id": "d",
                "identity_state": "idle",
                "generation": 1,
                "descriptor": {"sha256": "ab"},
                "profiles": ["otdp.logic_analyser/1.0.0"],
            },
            presentation=state,
            mode_banner=None,
            csrf_token="t",
            gateway_id="gw",
            principal="op",
            scopes=["stg:observe"],
            session_warning=None,
        )
    )


# --- L4 capability b: the layout block on the production host --------------------
#
# The manifest's plugin-ui-class-reference:layout block composes §E.1
# partials host-side: sections as bw-panels with the declared surface and
# span, tiles INSIDE their declared sections in DOM order, plot skeletons
# at plot_ref positions, text verbatim, and every control DISABLED with
# reason no-authority (the G2 read-only scope line — zero enabled
# controls). No-block manifests compose byte-identically to pre-L4 (the
# committed baseline); a schema-invalid block renders the typed
# classref_layout_invalid refusal, never a partial page.


_SIM_PSU_DESCRIPTOR = ROOT / "fixtures" / "execution" / "descriptor-sim-psu.json"


def _layout_content(tmp_path: Path) -> tuple[Any, Any]:
    """A FRESH store per layout test (the shared module gateway carries
    every earlier test's attachments for the same descriptor digest —
    the composition resolves catalogues[0] and a stale default-attachment
    catalogue would shadow the layout fixture's own)."""
    from benchweave.content.store import ContentStore
    from benchweave.state.store import Store

    store = Store.open(str(tmp_path / "state-layout.sqlite"), check_same_thread=False)
    content = ContentStore(store)
    return content, store


def _admit_layout_attachment(
    content: Any, *, layout_pages: list[dict[str, Any]]
) -> None:
    """A readings-page attachment carrying the namespaced layout block —
    the canonical validator is extension-blind, so this manifest passes
    check unchanged and the FAMILY schema is the block's only authority."""
    descriptor_raw = _SIM_PSU_DESCRIPTOR.read_bytes()
    descriptor_digest = hashlib.sha256(descriptor_raw).hexdigest()
    manifest = {
        "contract_version": _PLUGIN_UI,
        "plugin_id": json.loads(descriptor_raw)["id"],
        "descriptor_sha256": descriptor_digest,
        "bindings": [
            {"id": "reading", "kind": "observation", "target_id": "voltage"}
        ],
        "pages": [
            {
                "id": "readings",
                "title": "Readings",
                "kind": "readings",
                "bindings": ["reading"],
                "required": True,
            }
        ],
        "extensions": {
            "plugin-ui-class-reference:layout": {
                "contract_version": "0.1.0",
                "pages": layout_pages,
            }
        },
    }
    manifest_raw = json.dumps(manifest).encode()
    catalogue = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": descriptor_digest,
        "targets": [
            {
                "id": "voltage",
                "kind": "observation",
                "parameter_id": "output_voltage_v",
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
        "manifest": {"path": "manifest.json", "sha256": hashlib.sha256(manifest_raw).hexdigest()},
    }
    prefix = f"https://benchweave.dev/contracts/plugin-ui/{_PLUGIN_UI}"
    for raw, parsed, schema in (
        (json.dumps(envelope).encode(), envelope, f"{prefix}/presentation-envelope.schema.json"),
        (manifest_raw, manifest, f"{prefix}/ui-manifest.schema.json"),
        (json.dumps(catalogue).encode(), catalogue, f"{prefix}/binding-catalogue.schema.json"),
    ):
        content.put_document(raw, hashlib.sha256(raw).hexdigest(), parsed, schema, NOW_ISO)


_LAYOUT_PAGES = [
    {
        "page_id": "readings",
        "sections": [
            {
                "id": "vitals",
                "title": "Vitals",
                "surface": "recessed",
                "span": 6,
                "children": [
                    {"binding_id": "reading", "kind": "reading-tile"},
                    {"body": "Author text, verbatim"},
                    {"binding_id": "reading", "kind": "data-table"},
                ],
            },
            {
                "id": "ops",
                "title": "Ops",
                "surface": "raised",
                "span": 6,
                "children": [{"binding_id": "arm", "kind": "button"}],
            },
        ],
    }
]


def _layout_state(tmp_path: Path) -> Any:
    content, _store = _layout_content(tmp_path)
    descriptor_raw = _SIM_PSU_DESCRIPTOR.read_bytes()
    _admit_layout_attachment(content, layout_pages=_LAYOUT_PAGES)
    return compose_device_presentation(content, descriptor_raw)


def test_layout_sections_render_bw_panels_with_surface_and_span(
    tmp_path: Path,
) -> None:
    """B4: both declared sections render as bw-panel with the declared
    data-surface and grid span (2/2)."""
    state = _layout_state(tmp_path)
    assert state.valid is True, state.findings
    page = next(p for p in state.pages if p.page_id == "readings")
    assert len(page.sections) == 2
    html = _render_device_page(state)
    assert html.count('class="bw-panel bw-presentation__section"') == 2
    assert 'data-surface="recessed"' in html
    assert 'data-surface="raised"' in html
    assert 'style="grid-column: span 6"' in html


def test_layout_tiles_render_inside_declared_sections_in_dom_order(
    tmp_path: Path,
) -> None:
    """B4's DOM-order arm: the tile renders INSIDE the vitals section,
    before the text and the table node — declared order, not a flat
    re-render."""
    state = _layout_state(tmp_path)
    html = _render_device_page(state)
    vitals_at = html.index('data-bw-section-id="vitals"')
    ops_at = html.index('data-bw-section-id="ops"')
    tile_at = html.index('class="bw-reading"', vitals_at)
    text_at = html.index("Author text, verbatim", vitals_at)
    table_at = html.index('class="bw-data-table"', vitals_at)
    assert vitals_at < tile_at < text_at < table_at < ops_at


def test_layout_controls_render_disabled_no_authority(
    tmp_path: Path,
) -> None:
    """B5: every control node renders disabled with reason no-authority
    and the visible §C.2 label — and the page carries ZERO enabled
    controls (no enabled button, no input element at all)."""
    state = _layout_state(tmp_path)
    html = _render_device_page(state)
    # 2x: the disabled button element + its §C.2 label span.
    assert html.count('data-bw-disabled-reason="no-authority"') == 2
    assert "<input" not in html
    for fragment in _iter_fragments(html, "<button"):
        assert "disabled" in fragment.split(">")[0], fragment[:120]


def _iter_fragments(html: str, marker: str) -> list[str]:
    out: list[str] = []
    at = 0
    while True:
        at = html.find(marker, at)
        if at == -1:
            return out
        out.append(html[at : html.index("</button>", at) + len("</button>")])
        at += 1


def test_layout_plot_skeleton_at_ref_and_out_of_range_note(
    gateway: SimpleNamespace,
) -> None:
    """plot_ref places the page's plot skeleton at the referenced
    position; a plot_ref naming a plot the page does not declare renders
    the honest note, never silence."""
    from benchweave.interfaces.ui_presentation import (
        PresentationPage,
        compose_layout_sections,
    )
    page = PresentationPage(
        page_id="p",
        title="P",
        kind="dataset",
        required=True,
        available=True,
        refused=False,
        plots=(
            {
                "kind": "digital_lanes",
                "y": ["d0", "d1"],
                "lane_groups": [
                    {"label": "D1-D2", "member_ids": ["d0", "d1"], "radix": "hex"}
                ],
                "decoder_lanes": [],
            },
        ),
    )
    sections = compose_layout_sections(
        page,
        [
            {
                "id": "lanes",
                "title": "Lanes",
                "surface": "raised",
                "span": 12,
                "children": [{"plot_index": 0}, {"plot_index": 3}],
            }
        ],
        {},
        {},
    )
    assert len(sections) == 1
    html = str(sections[0].html)
    assert html.count('data-bw-lane-kind="channel"') == 2
    assert html.count('data-bw-lane-kind="group"') == 1
    assert "plot 3 is not declared on this page" in html


def test_derived_capture_renders_the_lane_group_skeleton(
    gateway: SimpleNamespace,
) -> None:
    """B1's skeleton arm: the derived capture page's Lanes section renders
    the lane-group skeleton equal to the derived inventory — F1: 2 channel
    rows + 1 group row."""
    _admit_vendor_catalog(gateway)
    state = compose_device_presentation(gateway.content, _f1_descriptor_raw("f1"))
    capture = next(p for p in state.pages if p.page_id == "capture")
    assert len(capture.sections) == 2
    lanes_html = str(capture.sections[0].html)
    assert lanes_html.count('data-bw-lane-kind="channel"') == 2
    assert lanes_html.count('data-bw-lane-kind="group"') == 1


def test_f2_derived_skeleton_is_32_channels_plus_4_groups(
    gateway: SimpleNamespace,
) -> None:
    """B1's F2 skeleton arm: 32 channel rows + 4 group rows."""
    _admit_vendor_catalog(gateway)
    state = compose_device_presentation(gateway.content, _f1_descriptor_raw("f2"))
    capture = next(p for p in state.pages if p.page_id == "capture")
    lanes_html = str(capture.sections[0].html)
    assert lanes_html.count('data-bw-lane-kind="channel"') == 32
    assert lanes_html.count('data-bw-lane-kind="group"') == 4


def test_no_block_manifest_composes_byte_identical_to_pre_l4(
    tmp_path: Path,
) -> None:
    """B6's first clause: a manifest without the layout block composes the
    presentation region BYTE-IDENTICAL to the committed pre-L4 baseline —
    the layout pass adds nothing when the block is absent. Fresh store on
    purpose: the shared module store's F1-fold attachments would shadow
    the default one at the resolution seam (the class
    test_re_admitted_identical_attachment pins)."""
    content, _store = _layout_content(tmp_path)
    descriptor_raw = _SIM_PSU_DESCRIPTOR.read_bytes()
    _admit_attachment(content, descriptor_raw)
    state = compose_device_presentation(content, descriptor_raw)
    assert state.absence is None
    page = _render_device_page(state)
    start = page.index('<div class="bw-presentation" data-bw-presentation-pages>')
    end = page.index("</section>", start)
    region = page[start:end]
    baseline = (
        Path(__file__).resolve().parents[1]
        / "interfaces_ui"
        / "baselines"
        / "l4-no-block-presentation.html"
    ).read_bytes()
    assert region.encode() == baseline


def test_invalid_layout_block_renders_classref_layout_invalid(
    gateway: SimpleNamespace,
) -> None:
    """B6's second clause: a schema-invalid block renders the typed
    classref_layout_invalid refusal, never a partial page."""
    descriptor_raw, _document = _descriptor(gateway)
    descriptor_digest = hashlib.sha256(descriptor_raw).hexdigest()
    manifest = {
        "contract_version": _PLUGIN_UI,
        "plugin_id": json.loads(descriptor_raw)["id"],
        "descriptor_sha256": descriptor_digest,
        "bindings": [],
        "pages": [
            {
                "id": "readings",
                "title": "Readings",
                "kind": "readings",
                "bindings": [],
                "required": True,
            }
        ],
        "extensions": {
            "plugin-ui-class-reference:layout": {
                "contract_version": "9.9.9",
                "pages": [],
            }
        },
    }
    manifest_raw = json.dumps(manifest).encode()
    catalogue = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": descriptor_digest,
        "targets": [],
    }
    envelope = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": descriptor_digest,
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": hashlib.sha256(manifest_raw).hexdigest()},
    }
    prefix = f"https://benchweave.dev/contracts/plugin-ui/{_PLUGIN_UI}"
    for raw, parsed, schema in (
        (json.dumps(envelope).encode(), envelope, f"{prefix}/presentation-envelope.schema.json"),
        (manifest_raw, manifest, f"{prefix}/ui-manifest.schema.json"),
        (json.dumps(catalogue).encode(), catalogue, f"{prefix}/binding-catalogue.schema.json"),
    ):
        gateway.content.put_document(raw, hashlib.sha256(raw).hexdigest(), parsed, schema, NOW_ISO)
    state = compose_device_presentation(gateway.content, descriptor_raw)
    assert state.pages == ()
    assert any(
        code == "classref_layout_invalid" for code, _path, _message in state.findings
    )


def test_dual_invalid_manifest_renders_canonical_and_layout_findings(
    gateway: SimpleNamespace,
) -> None:
    """A manifest invalid BOTH canonically and in its layout block renders
    the full finding list (canonical + layout) — the layout check must not
    mask the canonical findings (adversary lane A F4)."""
    descriptor_raw, _document = _descriptor(gateway)
    descriptor_digest = hashlib.sha256(descriptor_raw).hexdigest()
    manifest = {
        "contract_version": _PLUGIN_UI,
        "plugin_id": json.loads(descriptor_raw)["id"],
        "descriptor_sha256": descriptor_digest,
        "bindings": 17,
        "pages": [
            {
                "id": "readings",
                "title": "Readings",
                "kind": "readings",
                "bindings": [],
                "required": True,
            }
        ],
        "extensions": {
            "plugin-ui-class-reference:layout": {
                "contract_version": "9.9.9",
                "pages": [],
            }
        },
    }
    manifest_raw = json.dumps(manifest).encode()
    catalogue = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": descriptor_digest,
        "targets": [],
    }
    envelope = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": descriptor_digest,
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": hashlib.sha256(manifest_raw).hexdigest()},
    }
    prefix = f"https://benchweave.dev/contracts/plugin-ui/{_PLUGIN_UI}"
    for raw, parsed, schema in (
        (json.dumps(envelope).encode(), envelope, f"{prefix}/presentation-envelope.schema.json"),
        (manifest_raw, manifest, f"{prefix}/ui-manifest.schema.json"),
        (json.dumps(catalogue).encode(), catalogue, f"{prefix}/binding-catalogue.schema.json"),
    ):
        gateway.content.put_document(raw, hashlib.sha256(raw).hexdigest(), parsed, schema, NOW_ISO)
    state = compose_device_presentation(gateway.content, descriptor_raw)
    codes = [code for code, _path, _message in state.findings]
    assert state.valid is False
    assert state.pages == ()
    assert "classref_layout_invalid" in codes, codes
    assert len(codes) >= 2, (
        "the layout finding must not mask the canonical findings"
    )


def test_populate_tiles_reaches_section_tiles(
    tmp_path: Path,
) -> None:
    """The #369 join through the layout: populate_tiles populates a tile
    re-homed INTO a declared section — the reading-tile join's semantics
    hold at the re-homed position (CON-5's read-only composition rule)."""

    from benchweave.interfaces.ui_readings import RetainedReading, populate_tiles

    state = _layout_state(tmp_path)
    page = next(p for p in state.pages if p.page_id == "readings")
    section = page.sections[0]
    assert section.nodes and section.nodes[0].tile is not None
    tile = section.nodes[0].tile
    assert tile.parameter_id == "output_voltage_v"
    reading = RetainedReading(
        parameter="output_voltage",
        value=12.5,
        unit="V",
        observed_at="2026-10-15T00:00:00Z",
        age_ms_at_land=0,
        quality="valid",
        source="device",
        run_id="run-1",
        stored_at="2026-10-15T00:00:01Z",
    )
    populated = populate_tiles(
        state,
        {"output_voltage_v": reading},
        {"parameters": [{"name": "output_voltage_v"}]},
        now_epoch_ms=1_800_000_000_000,
    )
    populated_section = next(
        p for p in populated.pages if p.page_id == "readings"
    ).sections[0]
    populated_tile = populated_section.nodes[0].tile
    assert populated_tile is not None and populated_tile is not tile
    assert populated_tile.value == "12.5"
    assert populated_tile.stale_verdict == "no-verdict"


# --- L4 capability c: the panel registry ------------------------------------------
#
# PANELS is the gateway-owned panel registry; SUPPORTED_PANELS derives from
# it (frozenset(PANELS)) so registry/declaration drift is unrepresentable.
# A class_panel page naming the registered panel validates (panel_unavailable
# gone) and renders the host composition; an unregistered panel keeps the
# SW-41 refusal; the registry's corpus pin guards the family version it
# renders against (R4).

_PANEL_ID = "benchweave.classref-logic-analyser/0.1.0"


def test_panel_id_pattern_conflict() -> None:
    """The registration-id note the panel registry cites (panels.py's
    comment names this test): the design record's example id
    'benchweave/classref-logic-analyser/0.1.0' carries TWO slashes, and
    the ui-manifest schema's own panel_id pattern — the shape the design
    names as binding — admits exactly one. The schema's PATTERN (read
    digest-verified from the corpus) refuses the two-slash form and
    admits the pattern-conforming dot-form the registry registers."""
    from benchweave.presentation.panels import PANELS

    corpus = corpus_root()
    pins = {
        str(row["path"]): str(row["sha256"])
        for row in json.loads((corpus / "corpus-manifest.json").read_bytes())["files"]
    }
    relpath = f"plugin-ui/{_PLUGIN_UI}/ui-manifest.schema.json"
    raw = (corpus / relpath).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pins[relpath], (
        "the schema the pattern is read from must be the pinned bytes"
    )
    schema = json.loads(raw)
    pattern = schema["$defs"]["page"]["properties"]["panel_id"]["pattern"]
    assert pattern.count("/") == 1, "the pattern itself carries exactly one slash"
    two_slash = "benchweave/classref-logic-analyser/0.1.0"
    dot_form = "benchweave.classref-logic-analyser/0.1.0"
    assert re.fullmatch(pattern, two_slash) is None, (
        "the design's two-slash example id is schema-refused on any "
        "class_panel page"
    )
    assert re.fullmatch(pattern, dot_form) is not None, (
        "the registered dot-form conforms to the schema's pattern"
    )
    assert dot_form in PANELS and two_slash not in PANELS


def test_supported_panels_derive_from_the_registry_mechanically() -> None:
    """B7's mechanical arm: SUPPORTED_PANELS == frozenset(PANELS) by
    construction — the validator consumes the derived value, so a registry
    entry is servable the moment it exists and a declaration can never
    name a panel the registry lacks."""
    from benchweave.interfaces.ui_presentation import SUPPORTED_PANELS
    from benchweave.presentation.panels import PANELS

    assert frozenset(PANELS) == SUPPORTED_PANELS
    assert _PANEL_ID in SUPPORTED_PANELS


def test_registered_class_panel_validates_and_renders(
    tmp_path: Path,
) -> None:
    """B7: a class_panel page with the registered id validates clean (the
    panel_unavailable finding is GONE) and renders the host composition —
    the run-group's disabled §E.1 buttons and the lane rails from the
    bound dataset."""

    content, _store = _layout_content(tmp_path)
    descriptor_raw = _SIM_PSU_DESCRIPTOR.read_bytes()
    digest = hashlib.sha256(descriptor_raw).hexdigest()
    manifest = {
        "contract_version": _PLUGIN_UI,
        "plugin_id": json.loads(descriptor_raw)["id"],
        "descriptor_sha256": digest,
        "bindings": [
            {"id": "capture", "kind": "dataset", "target_id": "capture"},
            {"id": "arm", "kind": "procedure", "target_id": "arm"},
        ],
        "pages": [
            {
                "id": "capture-panel",
                "title": "Capture",
                "kind": "class_panel",
                "panel_id": _PANEL_ID,
                "bindings": ["capture", "arm"],
                "required": True,
            }
        ],
    }
    manifest_raw = json.dumps(manifest).encode()
    catalogue = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": digest,
        "targets": [
            {
                "id": "capture",
                "kind": "dataset",
                "action_id": "otdp.dc_psu.measure/1.0.0",
                "profile_ids": ["otdp.dc_psu/1.0.0"],
                "measurement_schema_id": "urn:otdp:measurement:0.2.2",
                "variables": [
                    {
                        "id": "t",
                        "type": "number",
                        "unit": "s",
                        "shape": "vector",
                        "axis_role": "x",
                    },
                    {
                        "id": "v",
                        "type": "number",
                        "unit": "V",
                        "shape": "vector",
                        "axis_role": "value",
                    },
                ],
            },
            {
                "id": "arm",
                "kind": "procedure",
                "action_id": "otdp.dc_psu.output/1.0.0",
                "profile_ids": ["otdp.dc_psu/1.0.0"],
                "input_schema_id": "urn:otdp:action:dc_psu.output:1.0.0:input",
            },
        ],
    }
    envelope = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": digest,
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": hashlib.sha256(manifest_raw).hexdigest()},
    }
    prefix = f"https://benchweave.dev/contracts/plugin-ui/{_PLUGIN_UI}"
    for raw, parsed, schema in (
        (json.dumps(envelope).encode(), envelope, f"{prefix}/presentation-envelope.schema.json"),
        (manifest_raw, manifest, f"{prefix}/ui-manifest.schema.json"),
        (json.dumps(catalogue).encode(), catalogue, f"{prefix}/binding-catalogue.schema.json"),
    ):
        content.put_document(raw, hashlib.sha256(raw).hexdigest(), parsed, schema, NOW_ISO)
    state = compose_device_presentation(content, descriptor_raw)
    assert state.absence is None
    assert state.valid is True, state.findings
    page = next(p for p in state.pages if p.page_id == "capture-panel")
    assert page.available is True
    assert page.panel is not None
    html = str(page.panel)
    assert 'data-bw-disabled-reason="no-authority"' in html
    assert "No lease or policy authority" in html
    assert 'data-bw-lane-kind="channel"' in html
    assert _PANEL_ID in html


def test_unregistered_panel_keeps_the_sw41_refusal(
    tmp_path: Path,
) -> None:
    """B7's negative arm: an unregistered panel id keeps today's posture —
    the validator's panel_unavailable finding and the required page's
    refusal render, never the composition."""
    content, _store = _layout_content(tmp_path)
    descriptor_raw = _SIM_PSU_DESCRIPTOR.read_bytes()
    digest = hashlib.sha256(descriptor_raw).hexdigest()
    manifest = {
        "contract_version": _PLUGIN_UI,
        "plugin_id": json.loads(descriptor_raw)["id"],
        "descriptor_sha256": digest,
        "bindings": [],
        "pages": [
            {
                "id": "must",
                "title": "Must",
                "kind": "custom_panel",
                "panel_id": "custom/1.0.0",
                "bindings": [],
                "required": True,
            }
        ],
    }
    manifest_raw = json.dumps(manifest).encode()
    catalogue = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": digest,
        "targets": [],
    }
    envelope = {
        "contract_version": _PLUGIN_UI,
        "descriptor_sha256": digest,
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": hashlib.sha256(manifest_raw).hexdigest()},
    }
    prefix = f"https://benchweave.dev/contracts/plugin-ui/{_PLUGIN_UI}"
    for raw, parsed, schema in (
        (json.dumps(envelope).encode(), envelope, f"{prefix}/presentation-envelope.schema.json"),
        (manifest_raw, manifest, f"{prefix}/ui-manifest.schema.json"),
        (json.dumps(catalogue).encode(), catalogue, f"{prefix}/binding-catalogue.schema.json"),
    ):
        content.put_document(raw, hashlib.sha256(raw).hexdigest(), parsed, schema, NOW_ISO)
    state = compose_device_presentation(content, descriptor_raw)
    assert state.valid is False
    assert any(code == "panel_unavailable" for code, _p, _m in state.findings)
    required_page = next(p for p in state.pages if p.page_id == "must")
    assert required_page.refused is True
    assert required_page.panel is None


def test_panel_corpus_pin_mismatch_renders_the_honest_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R4's falsifier mechanised: a panel whose corpus pin names a family
    version the gateway does not serve renders the honest version note,
    NEVER the composition (the panel and the corpus bytes it interprets
    must move in one reviewable unit)."""
    from benchweave.presentation import panels

    content, _store = _layout_content(tmp_path)
    monkeypatch.setattr(
        panels, "served_family_version", lambda _corpus: "9.9.9"
    )
    context = panels.PanelContext(
        panel_id=_PANEL_ID,
        page_id="capture-panel",
        title="Capture",
        bindings=("arm",),
        bindings_index={"arm": {"kind": "procedure", "target_id": "arm"}},
        targets={"arm": {"kind": "procedure"}},
    )
    markup = panels.panel_markup(_PANEL_ID, context, corpus_path=corpus_root())
    assert markup is not None
    html = str(markup)
    assert "0.1.0" in html and "9.9.9" in html
    assert 'data-bw-disabled-reason="no-authority"' not in html


def test_panel_corpus_pin_guard_runs_without_an_explicit_corpus_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The None arm of ``corpus_path`` is not an exemption: the R4 guard
    runs against the served corpus (``corpus_root()``) even when the
    caller passes None — a corpus_path=None call that skipped the pin
    check would render the composition against reference bytes whose
    version it never checked (adversary lane B B5)."""
    from benchweave.presentation import panels

    monkeypatch.setattr(panels, "served_family_version", lambda _corpus: "9.9.9")
    context = panels.PanelContext(
        panel_id=_PANEL_ID,
        page_id="capture-panel",
        title="Capture",
        bindings=("arm",),
        bindings_index={"arm": {"kind": "procedure", "target_id": "arm"}},
        targets={"arm": {"kind": "procedure"}},
    )
    markup = panels.panel_markup(_PANEL_ID, context, corpus_path=None)
    assert markup is not None
    html = str(markup)
    assert "9.9.9" in html, "the None arm must run the pin guard, not skip it"
    assert 'data-bw-disabled-reason="no-authority"' not in html
