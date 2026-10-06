"""AR-D1: the migrated project loads and serves on the standalone host.

Composes the seam the way ``benchweave_sdk_server.cli._build_seam`` does
(the mock-transport branch, no scenario), builds the real app, and asserts
through a TestClient: the index serves with the authored presentation,
``host_info`` answers ``mode=standalone`` with the descriptor digest, and
device operations answer. The invalid-presentation arm pins the load gate's
refusal through the same real path (``standalone_plugin_invalid:``).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from benchweave_sdk_server.seam import StandaloneSeam
from benchweave_sdk_server.security import GuardPolicy
from benchweave_sdk_server.session import (
    PluginLoadError,
    load_plugin_project,
    mock_plugin_session,
)
from benchweave_sdk_server.web import build_app
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PROJECT_ROOT / "src" / "adc_6ch_12bit"
DESCRIPTOR_SHA256 = hashlib.sha256((PACKAGE_DIR / "descriptor.json").read_bytes()).hexdigest()

#: The per-launch credentials the guards check (a test launch of the host).
BEARER = "proof-bearer"
CSRF = "proof-csrf"


def _client() -> TestClient:
    plugin = load_plugin_project(PROJECT_ROOT)
    seam = StandaloneSeam(mock_plugin_session(plugin), transport_kind="mock")
    app = build_app(
        seam,
        policy=GuardPolicy.complete(
            bound_host="127.0.0.1", bound_port=8477, bearer_token=BEARER, csrf_token=CSRF
        ),
    )
    return TestClient(app, base_url="http://127.0.0.1:8477")


def test_index_serves_with_authored_presentation() -> None:
    with _client() as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Channel readings" in response.text


def test_page_route_serves_the_dataset_page() -> None:
    with _client() as client:
        response = client.get("/pages/readings")
    assert response.status_code == 200
    assert "Channel readings" in response.text


def test_host_info_answers_standalone_with_descriptor_digest() -> None:
    with _client() as client:
        response = client.post(
            "/v1/host_info", json={}, headers={"Authorization": f"Bearer {BEARER}"}
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "standalone"
    assert data["plugin"]["package"] == "adc_6ch_12bit"
    assert data["plugin"]["descriptor_sha256"] == DESCRIPTOR_SHA256
    assert data["transport"] == "mock"


def test_device_operations_reachable() -> None:
    with _client() as client:
        headers = {"Authorization": f"Bearer {BEARER}"}
        discover = client.post("/v1/device_discover", json={}, headers=headers)
        assert discover.status_code == 200
        devices = discover.json()["data"]["devices"]
        # The mock session's device id is the descriptor's connection_key.
        assert [row["id"] for row in devices] == ["adc_board"]


def test_invalid_presentation_copy_refused_by_load_gate(tmp_path: Path) -> None:
    """The refusal arm: a corrupted presentation copy must refuse through
    the real gate, never load as a degraded-but-silent layout."""
    project = tmp_path / "invalid-copy"
    (project / "src").mkdir(parents=True)
    shutil.copytree(PACKAGE_DIR, project / "src" / "adc_6ch_12bit")
    envelope_path = project / "src" / "adc_6ch_12bit" / "presentation.json"
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["manifest"]["sha256"] = "0" * 64  # bytes drifted from the stamp
    envelope_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(PluginLoadError) as raised:
        load_plugin_project(project)
    message = str(raised.value)
    assert message.startswith("standalone_plugin_invalid:")
    assert "preview_invalid_presentation" in message
