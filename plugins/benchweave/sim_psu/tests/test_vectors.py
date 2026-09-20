"""Replay the plugin-owned synthetic vectors against the installed package."""

import json
from importlib.resources import files
from unittest.mock import Mock

import pytest
from benchweave_sim_psu.plugin import create_plugin

from benchweave.host import OperationRequest, OperationStatus, OperationVerb

PACKAGE = "benchweave_sim_psu"
VECTORS = json.loads(files(PACKAGE).joinpath("vectors.json").read_text())["vectors"]


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["name"])
def test_vector(vector):
    now_ns = 0
    services = Mock()
    plugin = create_plugin(lambda: "2026-09-11T00:00:00Z", lambda: now_ns)
    assert plugin.simulation.simulated is True
    plugin.plugin_open(services)

    def dispatch(entry, deadline):
        request = OperationRequest(
            "replay-op", OperationVerb(entry["verb"]), dict(entry.get("arguments", {}))
        )
        result = plugin.dispatch(request, deadline_ns=deadline)
        assert result.operation_id == request.operation_id
        return result

    try:
        for entry in vector.get("setup", []):
            dispatch(entry, 10**9)
        now_ns += int(vector.get("advance_ns", 0))
        result = dispatch(vector["request"], 10**12)
        expected = vector["expect"]
        if expected["status"] == "ok":
            assert result.status is OperationStatus.OK
            if "data_value" in expected:
                assert result.data.value == expected["data_value"]
            if "data_manufacturer" in expected:
                assert result.data.manufacturer == expected["data_manufacturer"]
            if "error_entry_code" in expected:
                assert expected["error_entry_code"] in [x.code for x in result.data.entries]
        else:
            assert result.status is OperationStatus.ERROR
            assert result.error.code.value == expected["error_code"]
            assert result.error.dispatch_state.value == expected["dispatch_state"]
    finally:
        plugin.plugin_close()
    assert services.mock_calls == []


def test_packaged_descriptor():
    descriptor = json.loads(files(PACKAGE).joinpath("descriptor.json").read_text())
    assert descriptor["id"] == "dev.benchweave.sim-psu"
    assert descriptor["profiles"] == ["otdp.dc_psu/1.0.0"]
