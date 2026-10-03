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
from benchweave.interfaces.ui_presentation import reading_staleness
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
