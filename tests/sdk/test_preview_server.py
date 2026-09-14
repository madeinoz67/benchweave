"""The SDK preview server is loopback-first, bounded and deterministic."""

from __future__ import annotations

import importlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SDK = Path(__file__).resolve().parents[2] / "packages/sdk/src"
sys.path.insert(0, str(SDK))


def model():  # type: ignore[no-untyped-def]
    models = importlib.import_module("benchweave_sdk.preview_models")
    scenario = models.PreviewScenario(
        id="request-rejected",
        title="Request rejected",
        description="Simulated rejection",
        timestamp_strategy="fixed",
        observations=(),
        permissions=frozenset({"observer"}),
        lease_state="none",
        approval_state="not_required",
        unavailable_panels=(),
        expected_severity="warning",
        request_outcomes=(
            models.SimulatedReceipt(
                "voltage", "permission_rejected", "Simulated permission rejection"
            ),
        ),
        baseline=True,
    )
    return models.PreviewModel(
        plugin_id="dev.example.plugin",
        renderer_version="0.1.0",
        pages=(),
        scenarios=(scenario,),
    )


def get_json(url: str) -> dict[str, object] | list[object]:
    with urllib.request.urlopen(url, timeout=2) as response:
        assert response.headers["Content-Type"] == "application/json; charset=utf-8"
        assert response.headers.get("Access-Control-Allow-Origin") is None
        return json.loads(response.read())


def test_server_exposes_versioned_preview_and_scenarios(tmp_path: Path) -> None:
    server_module = importlib.import_module("benchweave_sdk.preview_server")
    (tmp_path / "index.html").write_text("<h1>preview</h1>", encoding="utf-8")

    with server_module.PreviewServer(model(), tmp_path) as address:
        preview = get_json(address.url + "/api/v1/preview")
        scenarios = get_json(address.url + "/api/v1/scenarios")
        health = get_json(address.url + "/healthz")

    assert preview["simulation"] is True
    assert preview["api_version"] == 1
    assert scenarios == [
        {"id": "request-rejected", "title": "Request rejected", "baseline": True}
    ]
    assert health == {"ready": True, "api_version": 1}


def test_server_returns_configured_simulated_receipt(tmp_path: Path) -> None:
    server_module = importlib.import_module("benchweave_sdk.preview_server")
    (tmp_path / "index.html").write_text("preview", encoding="utf-8")

    with server_module.PreviewServer(model(), tmp_path) as address:
        request = urllib.request.Request(
            address.url + "/api/v1/scenarios/request-rejected/requests",
            data=json.dumps({"binding_id": "voltage", "value": 13.0}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            receipt = json.loads(response.read())

    assert receipt["outcome"] == "permission_rejected"
    assert receipt["simulated"] is True


@pytest.mark.parametrize("host", ["0.0.0.0", "::"])
def test_wildcard_listener_is_always_rejected(host: str) -> None:
    server_module = importlib.import_module("benchweave_sdk.preview_server")

    with pytest.raises(ValueError, match="preview_unsafe_listener"):
        server_module.validate_listener(host, allow_network=True)


def test_non_loopback_listener_requires_explicit_acknowledgement() -> None:
    server_module = importlib.import_module("benchweave_sdk.preview_server")

    with pytest.raises(ValueError, match="preview_network_acknowledgement_required"):
        server_module.validate_listener("192.0.2.10", allow_network=False)
    server_module.validate_listener("192.0.2.10", allow_network=True)


def test_server_does_not_serve_paths_outside_asset_root(tmp_path: Path) -> None:
    server_module = importlib.import_module("benchweave_sdk.preview_server")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("preview", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not served", encoding="utf-8")

    with (
        server_module.PreviewServer(model(), assets) as address,
        pytest.raises(urllib.error.HTTPError) as error,
    ):
        urllib.request.urlopen(address.url + "/../secret.txt", timeout=2)

    assert error.value.code == 404
