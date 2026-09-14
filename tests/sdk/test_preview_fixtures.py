"""Deterministic SDK preview fixtures are closed, finite and serialisable."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / "packages/sdk/src"
FIXTURE_SCHEMA = ROOT / "contracts/plugin-ui-preview-v1/fixture.schema.json"
sys.path.insert(0, str(SDK))


def preview_models():  # type: ignore[no-untyped-def]
    return importlib.import_module("benchweave_sdk.preview_models")


def test_fixture_schema_is_closed_and_versioned() -> None:
    schema = json.loads(FIXTURE_SCHEMA.read_bytes())

    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == (
        "https://benchweave.dev/contracts/plugin-ui-preview/1/fixture.schema.json"
    )
    assert schema["additionalProperties"] is False


def test_preview_scenario_serialises_as_an_immutable_document() -> None:
    models = preview_models()
    scenario = models.PreviewScenario(
        id="normal",
        title="Normal",
        description="Nominal simulated state",
        timestamp_strategy="fixed",
        observations=(),
        permissions=frozenset({"observer"}),
        lease_state="none",
        approval_state="not_required",
        unavailable_panels=(),
        expected_severity="neutral",
        request_outcomes=(),
        baseline=True,
    )

    assert scenario.to_document() == {
        "id": "normal",
        "title": "Normal",
        "description": "Nominal simulated state",
        "timestamp_strategy": "fixed",
        "observations": [],
        "permissions": ["observer"],
        "lease_state": "none",
        "approval_state": "not_required",
        "unavailable_panels": [],
        "expected_severity": "neutral",
        "request_outcomes": [],
        "baseline": True,
    }
    with pytest.raises(AttributeError):
        scenario.title = "Changed"


def test_preview_observation_rejects_non_finite_values() -> None:
    models = preview_models()
    observation = models.PreviewObservation(
        binding_id="voltage",
        value=float("nan"),
        unit="V",
        quality="simulated",
        freshness_ms=0,
        provenance="SDK baseline",
    )

    with pytest.raises(ValueError, match="finite"):
        observation.to_document()
