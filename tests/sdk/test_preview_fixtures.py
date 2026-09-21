"""Deterministic SDK preview fixtures are closed, finite and serialisable."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / "packages/sdk/src"
FIXTURE_SCHEMA = ROOT / "standards/plugin-ui-preview/0.1.1/fixture.schema.json"
DOCUMENT_SCHEMA = ROOT / "standards/plugin-ui-preview/0.1.1/preview-document.schema.json"
sys.path.insert(0, str(SDK))


def preview_models() -> ModuleType:
    return importlib.import_module("benchweave_sdk.preview_models")


def fixtures_module() -> ModuleType:
    return importlib.import_module("benchweave_sdk.fixtures")


def catalogue() -> dict[str, object]:
    return {
        "contract_version": "0.1.0",
        "targets": [
            {
                "id": "voltage",
                "kind": "observation",
                "parameter_id": "voltage",
                "variables": [
                    {
                        "id": "value",
                        "type": "number",
                        "unit": "V",
                        "shape": "scalar",
                        "axis_role": "value",
                    }
                ],
            }
        ],
    }


def author_fixture(binding_id: str = "voltage", unit: str | None = "V") -> dict[str, object]:
    return {
        "contract_version": "0.1.1",
        "id": "high-load",
        "title": "High load",
        "description": "Synthetic high-load state",
        "timestamp_strategy": "fixed",
        "bindings": [
            {
                "id": binding_id,
                "value": 12.0,
                "unit": unit,
                "quality": "simulated",
                "freshness_ms": 0,
                "provenance": "Author fixture",
            }
        ],
        "permissions": ["observer"],
        "lease_state": "none",
        "approval_state": "not_required",
        "unavailable_panels": [],
        "expected_severity": "warning",
        "request_outcomes": [],
    }


def test_fixture_schema_is_closed_and_versioned() -> None:
    schema = json.loads(FIXTURE_SCHEMA.read_bytes())

    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == (
        "https://benchweave.dev/contracts/plugin-ui-preview/0.1.1/fixture.schema.json"
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


@pytest.mark.parametrize("scenario_id", sorted(fixtures_module().BASELINE_IDS))
def test_baseline_scenarios_are_always_generated(scenario_id: str) -> None:
    fixtures = fixtures_module()

    scenarios = fixtures.generate_baselines(catalogue(), {"pages": [], "plugin_id": "test.plugin"})

    assert scenario_id in {row.id for row in scenarios}


def test_author_fixture_rejects_unknown_binding(tmp_path: Path) -> None:
    fixtures = fixtures_module()
    (tmp_path / "high-load.json").write_text(
        json.dumps(author_fixture(binding_id="not-declared")), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="preview_unknown_binding"):
        fixtures.load_author_fixtures(tmp_path, catalogue())


def test_author_fixture_rejects_wrong_unit(tmp_path: Path) -> None:
    fixtures = fixtures_module()
    (tmp_path / "high-load.json").write_text(json.dumps(author_fixture(unit="A")), encoding="utf-8")

    with pytest.raises(ValueError, match="preview_unit_mismatch"):
        fixtures.load_author_fixtures(tmp_path, catalogue())


def test_preview_model_is_built_from_the_validated_candidate(tmp_path: Path) -> None:
    presentation = importlib.import_module("benchweave_sdk.presentation")
    scaffold = importlib.import_module("benchweave_sdk.scaffold")
    fixtures = fixtures_module()
    project = tmp_path / "plugin"
    scaffold.create_project(project, "example_plugin")
    presentation.create_ui_resources(project, "example_plugin")
    package = project / "src/example_plugin"

    candidate = presentation.load_validated_preview_inputs(
        package / "presentation.json",
        package / "descriptor.json",
        package,
        package / "binding-catalogue.json",
        firmware="1.0.0",
        features=frozenset(),
        panels=frozenset(),
    )
    model = fixtures.build_preview_model(candidate)

    assert model.plugin_id == "dev.example.example-plugin"
    assert model.simulation is True
    assert len(model.scenarios) == 11
    author_ids = {scenario.id for scenario in model.scenarios if not scenario.baseline}
    assert author_ids == {"example-normal", "example-warning"}
    assert [view.kind for view in model.plot_views] == ["time_series"]

    assert fixtures.__file__ is not None
    inventory = json.loads(
        (Path(fixtures.__file__).with_name("preview_assets") / "inventory.json").read_bytes()
    )
    assert model.renderer_version == inventory["renderer_version"]


def test_served_preview_document_conforms_to_wire_schema(tmp_path: Path) -> None:
    presentation = importlib.import_module("benchweave_sdk.presentation")
    scaffold = importlib.import_module("benchweave_sdk.scaffold")
    fixtures = fixtures_module()
    project = tmp_path / "plugin"
    scaffold.create_project(project, "example_plugin")
    presentation.create_ui_resources(project, "example_plugin")
    package = project / "src/example_plugin"
    candidate = presentation.load_validated_preview_inputs(
        package / "presentation.json",
        package / "descriptor.json",
        package,
        package / "binding-catalogue.json",
        firmware="1.0.0",
        features=frozenset(),
        panels=frozenset(),
    )
    document = fixtures.build_preview_model(candidate).to_document()

    schema = json.loads(DOCUMENT_SCHEMA.read_bytes())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(document))

    # The scaffold declares one hinted time-series plot; its projection must
    # ride the served document and validate (metric F, Python side).
    assert document["plot_views"], "the scaffold plot must project into the served document"
    assert document["plot_views"][0]["kind"] == "time_series"
    assert document["plot_views"][0]["channels"][0]["color_role"] == "muted"

    poisoned = json.loads(json.dumps(document))
    poisoned["scenarios"][0]["expected_severity"] = "catastrophic"
    assert list(validator.iter_errors(poisoned))

    poisoned_plot = json.loads(json.dumps(document))
    poisoned_plot["plot_views"][0]["channels"][0]["color_role"] = "critical"
    assert list(validator.iter_errors(poisoned_plot))


# --- plot_views projection and previewability relaxation (issue #67) ---
#
# The corpus shapes mirror the presentation-manifest/specimen bundles the
# gateway validator already admits: the receipt-time observation target of
# tests/unit/test_presentation_manifest.py and the oscilloscope dataset
# targets of tests/unit/test_presentation_specimens.py.


def preview_candidate(
    pages: list[dict[str, object]],
    targets: list[dict[str, object]],
    bindings: list[dict[str, object]] | None = None,
) -> object:
    """Build the frozen validated-input value directly from corpus shapes.

    In production only ``load_validated_preview_inputs`` constructs this after
    a clean validation report; the tests hand the projection the same frozen
    type over shapes that validator admits, so the projection's reads-only
    contract is exercised without re-running validation. ``bindings``
    overrides the default one-binding-per-target derivation (the
    divergent-id pin uses it).
    """
    presentation = importlib.import_module("benchweave_sdk.presentation")
    derived = [
        {"id": str(row["id"]), "kind": "observation", "target_id": str(row["id"])}
        if row.get("kind") == "observation"
        else {"id": f"{row['id']}-capture", "kind": "dataset", "target_id": str(row["id"])}
        for row in targets
    ]
    return presentation.ValidatedPreviewInputs(
        envelope={"contract_version": "0.2.0"},
        manifest={
            "contract_version": "0.2.0",
            "plugin_id": "dev.example.plugin",
            "bindings": bindings if bindings is not None else derived,
            "pages": pages,
        },
        binding_catalogue={"contract_version": "0.2.0", "targets": targets},
        resource_root=Path("."),
    )


VOLTAGE_TARGET: dict[str, object] = {
    "id": "voltage",
    "kind": "observation",
    "parameter_id": "voltage_measured",
    "variables": [
        {
            "id": "time",
            "type": "number",
            "unit": "s",
            "shape": "scalar",
            "axis_role": "receipt_time",
        },
        {"id": "value", "type": "number", "unit": "V", "shape": "scalar", "axis_role": "value"},
    ],
}


def waveform_target(y_names: list[str]) -> dict[str, object]:
    return {
        "id": "waveform",
        "kind": "dataset",
        "action_id": "otdp.oscilloscope.fetch/1.0.0",
        "profile_ids": ["otdp.oscilloscope/1.0.0"],
        "measurement_schema_id": "urn:otdp:measurement:0.2.0",
        "variables": [
            {"id": "time", "type": "number", "shape": "vector", "unit": "s", "axis_role": "x"},
            *(
                {"id": name, "type": "number", "shape": "vector", "unit": "V", "axis_role": "y"}
                for name in y_names
            ),
        ],
    }


def time_series_page(
    hints: list[dict[str, object]] | None = None, binding_id: str = "voltage"
) -> list[dict[str, object]]:
    plot: dict[str, object] = {
        "kind": "time_series",
        "binding_id": binding_id,
        "x": "time",
        "y": ["value"],
    }
    if hints is not None:
        plot["channel_hints"] = hints
    return [
        {
            "id": "readings",
            "title": "Readings",
            "kind": "readings",
            "bindings": [binding_id],
            "required": True,
            "plots": [plot],
        }
    ]


def waveform_page(y_names: list[str]) -> list[dict[str, object]]:
    return [
        {
            "id": "waveform",
            "title": "Waveform",
            "kind": "dataset",
            "bindings": ["waveform-capture"],
            "required": True,
            "plots": [
                {
                    "kind": "waveform",
                    "binding_id": "waveform-capture",
                    "x": "time",
                    "y": list(y_names),
                }
            ],
        }
    ]


def test_projection_covers_the_manifest_corpus_shapes() -> None:
    """Metric A: one view per declared plot over four manifest shapes, exact."""
    fixtures = fixtures_module()
    expected: dict[str, list[dict[str, object]]] = {
        "time_series": [
            {
                "page_id": "readings",
                "kind": "time_series",
                "binding_id": "voltage",
                "title": "Readings",
                "x": {"label": "time", "unit": "s"},
                "channels": [{"variable_id": "value", "label": "value", "unit": "V"}],
            }
        ],
        "waveform_1y": [
            {
                "page_id": "waveform",
                "kind": "waveform",
                "binding_id": "waveform",
                "title": "Waveform",
                "x": {"label": "time", "unit": "s"},
                "channels": [{"variable_id": "signal", "label": "signal", "unit": "V"}],
            }
        ],
        "waveform_2y": [
            {
                "page_id": "waveform",
                "kind": "waveform",
                "binding_id": "waveform",
                "title": "Waveform",
                "x": {"label": "time", "unit": "s"},
                "channels": [
                    {"variable_id": "trace01", "label": "trace01", "unit": "V"},
                    {"variable_id": "trace02", "label": "trace02", "unit": "V"},
                ],
            }
        ],
    }
    plain_candidate = preview_candidate(time_series_page(), [VOLTAGE_TARGET])
    signal_target = waveform_target(["signal"])
    trace_target = waveform_target(["trace01", "trace02"])
    cases: list[tuple[str, object, dict[str, list[dict[str, object]]]]] = [
        ("time_series", plain_candidate, expected),
        ("waveform_1y", preview_candidate(waveform_page(["signal"]), [signal_target]), expected),
        (
            "waveform_2y",
            preview_candidate(waveform_page(["trace01", "trace02"]), [trace_target]),
            expected,
        ),
    ]
    for name, candidate, _expected in cases:
        views = fixtures.project_plot_views(candidate)
        assert [view.to_document() for view in views] == expected[name], name


def test_projection_merges_channel_hints_and_changes_nothing_else() -> None:
    """Metric A pair 4 vs 1: the hinted twin differs only in the hint fields."""
    fixtures = fixtures_module()
    unhinted = fixtures.project_plot_views(preview_candidate(time_series_page(), [VOLTAGE_TARGET]))
    hinted_page = time_series_page([{"variable_id": "value", "color_role": "muted"}])
    hinted = fixtures.project_plot_views(preview_candidate(hinted_page, [VOLTAGE_TARGET]))
    assert [view.to_document() for view in hinted] == [
        {
            "page_id": "readings",
            "kind": "time_series",
            "binding_id": "voltage",
            "title": "Readings",
            "x": {"label": "time", "unit": "s"},
            "channels": [
                {"variable_id": "value", "label": "value", "unit": "V", "color_role": "muted"}
            ],
        }
    ]
    assert hinted[0].to_document() != unhinted[0].to_document()
    hinted_channel = hinted[0].to_document()["channels"][0]
    hinted_without_hint = {
        **hinted[0].to_document(),
        "channels": [
            {key: value for key, value in hinted_channel.items() if key != "color_role"}
        ],
    }
    assert hinted_without_hint == unhinted[0].to_document()


def test_projection_titles_multi_plot_pages_by_index() -> None:
    fixtures = fixtures_module()
    pages = [
        {
            "id": "readings",
            "title": "Readings",
            "kind": "readings",
            "bindings": ["voltage"],
            "required": True,
            "plots": [
                {"kind": "time_series", "binding_id": "voltage", "x": "time", "y": ["value"]},
                {"kind": "time_series", "binding_id": "voltage", "x": "time", "y": ["value"]},
            ],
        }
    ]
    views = fixtures.project_plot_views(preview_candidate(pages, [VOLTAGE_TARGET]))
    assert [view.title for view in views] == ["Readings (1/2)", "Readings (2/2)"]


def test_projection_resolves_the_join_key_to_the_target_id() -> None:
    """Divergent-ids pin: manifest binding 'reading' -> target 'voltage'.

    Preview observations speak target ids (baselines and author fixtures
    alike), so the projected view's join key is the bound TARGET id — the
    manifest binding's own id would ship a dead join for every plugin whose
    binding ids diverge from target ids. The rest of the committed corpus
    uses equal ids; this pins the namespace contract and proves the join
    feeds end to end.
    """
    fixtures = fixtures_module()
    pages = time_series_page(binding_id="reading")
    candidate = preview_candidate(
        pages,
        [VOLTAGE_TARGET],
        bindings=[{"id": "reading", "kind": "observation", "target_id": "voltage"}],
    )
    views = fixtures.project_plot_views(candidate)
    assert [view.binding_id for view in views] == ["voltage"]
    # The join feeds: the scenario side keys the same target id, so the
    # renderer's find-by-binding_id resolves against baseline observations.
    model = fixtures.build_preview_model(candidate)
    normal = next(row for row in model.scenarios if row.id == "normal")
    assert views[0].binding_id in {row.binding_id for row in normal.observations}


def test_two_variable_observation_target_builds_a_preview() -> None:
    """Metric E(i): the contract's canonical time-series target is previewable.

    The receipt-time + value observation target is the shape the presentation
    validator admits for a valid time-series plot; before the relaxation the
    preview refused it (preview_unsupported_shape killed the whole build).
    """
    fixtures = fixtures_module()
    model = fixtures.build_preview_model(preview_candidate(time_series_page(), [VOLTAGE_TARGET]))
    normal = next(row for row in model.scenarios if row.id == "normal")
    # Baselines speak the observation's VALUE variable: one synthetic reading
    # per observation target, keyed by the target id the wire joins on.
    assert [(row.binding_id, row.unit, row.value) for row in normal.observations] == [
        ("voltage", "V", 0.0)
    ]
    assert model.plot_views and model.plot_views[0].binding_id == "voltage"


def test_dataset_target_no_longer_kills_the_preview() -> None:
    """Metric E(ii): vector targets are skipped for baselines, still projected."""
    fixtures = fixtures_module()
    candidate = preview_candidate(waveform_page(["signal"]), [waveform_target(["signal"])])
    model = fixtures.build_preview_model(candidate)
    normal = next(row for row in model.scenarios if row.id == "normal")
    assert [row.binding_id for row in normal.observations] == []
    # Disclosed degradation, not a silent drop: the declared plot still
    # projects and the renderer owes its no-data disclosure.
    assert [view.kind for view in model.plot_views] == ["waveform"]


def test_author_fixture_referencing_dataset_binding_still_refuses(tmp_path: Path) -> None:
    """Metric E(iii): the snapshot data model cannot express dataset bindings."""
    fixtures = fixtures_module()
    fixture = author_fixture()
    fixture["contract_version"] = "0.1.1"
    fixture["bindings"] = [dict(fixture["bindings"][0], id="waveform")]  # type: ignore[index]
    (tmp_path / "high-load.json").write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="preview_unsupported_shape"):
        fixtures.load_author_fixtures(tmp_path, {"targets": [waveform_target(["signal"])]})
