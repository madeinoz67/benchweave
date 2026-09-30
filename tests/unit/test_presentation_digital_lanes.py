"""digital_lanes vectors — issue #244 slice 1 acceptance A1.1 / A1.2.

Pre-committed counts (design record §6 A1.1): exactly 12 valid vectors and
the invalid set naming its finding code per vector. Schema-level refusals
(the 64-cap, the kind enum, the per-kind shape rules) surface as
``invalid_document`` through ``_schema_findings``; semantic refusals carry
``invalid_plot`` / ``unresolved_reference`` through ``_plot_findings``.

The refusal delta is reproduced in-tree: the predecessor's frozen schema
refuses a ``digital_lanes`` plot at the kind enum while the 0.3.0 grammar
admits it (#62 evidence shape).
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from benchweave.presentation.contracts import ValidationReport, validate_presentation

type JsonObject = dict[str, Any]
type Specimen = tuple[JsonObject, dict[str, JsonObject], list[JsonObject], JsonObject]

ROOT = Path(__file__).resolve().parents[2]
PREDECESSOR = ROOT / "standards/plugin-ui/0.2.0"
CURRENT = ROOT / "standards/plugin-ui/0.3.0"


def _active_preview_wire() -> Path:
    """The served wire schema, DERIVED from the manifest's active row (the
    TS fork-catcher's mirror): the path can never lag a bump again."""
    manifest = json.loads((ROOT / "standards/standards-manifest.json").read_bytes())
    active = str(
        next(row["version"] for row in manifest["standards"] if row["id"] == "plugin-ui-preview")
    )
    return ROOT / f"standards/plugin-ui-preview/{active}/preview-document.schema.json"


PREVIEW_WIRE = _active_preview_wire()


def encode(value: object) -> bytes:
    return json.dumps(value).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load(name: str) -> JsonObject:
    document: JsonObject = json.loads((ROOT / "standards/otdp/0.2.0" / name).read_bytes())
    return document


def schema_documents(directory: Path) -> dict[str, JsonObject]:
    documents: dict[str, JsonObject] = {}
    for source in (ROOT / "standards/otdp/0.2.0", directory):
        for path in source.glob("*.schema.json"):
            document = json.loads(path.read_bytes())
            documents[document["$id"]] = document
    documents["catalog"] = load("device-profile-catalog.json")
    return documents


def _channel(identifier: str) -> JsonObject:
    return {"id": identifier, "type": "string", "unit": None, "shape": "vector"}


def _observation_target(variables: list[JsonObject]) -> JsonObject:
    # The class descriptor declares no parameters, so an observation target
    # is a capability_mismatch on its own — that finding is tolerated by the
    # code-naming assertions below and never the named defect.
    return {
        "id": "reading",
        "kind": "observation",
        "parameter_id": "voltage_measured",
        "variables": variables,
    }


def specimen(
    *,
    y_ids: Sequence[str] = ("ch1", "ch2", "ch3", "ch4"),
    x_var: JsonObject | None = None,
    plot_extra: JsonObject | None = None,
) -> Specimen:
    """A valid digital_lanes bundle: logic capture + decode event targets."""
    descriptor = load("examples/class-logic_analyser.json")
    documents = schema_documents(CURRENT)
    time = {"id": "time", "type": "number", "unit": "s", "shape": "vector", "axis_role": "x"}
    capture: JsonObject = {
        "id": "capture",
        "kind": "dataset",
        "action_id": "otdp.logic_analyser.fetch/1.0.0",
        "profile_ids": descriptor["profiles"],
        "measurement_schema_id": "urn:otdp:measurement:0.2.0",
        "variables": [time, *(_channel(i) for i in y_ids)]
        + ([x_var] if x_var is not None else []),
    }
    events: JsonObject = {
        "id": "events",
        "kind": "dataset",
        "action_id": "otdp.logic_analyser.decode/1.0.0",
        "profile_ids": descriptor["profiles"],
        "measurement_schema_id": "urn:otdp:measurement:0.2.0",
        "variables": [
            {"id": "start_s", "type": "number", "unit": "s", "shape": "vector"},
            {"id": "end_s", "type": "number", "unit": "s", "shape": "vector"},
            _channel("payload_hex"),
            _channel("status"),
        ],
    }
    plot: JsonObject = {
        "kind": "digital_lanes",
        "binding_id": "logic",
        "x": "time",
        "y": list(y_ids),
    }
    plot.update(plot_extra or {})
    manifest: JsonObject = {
        "contract_version": "0.3.0",
        "plugin_id": descriptor["id"],
        "descriptor_sha256": digest(encode(descriptor)),
        "bindings": [
            {"id": "logic", "kind": "dataset", "target_id": "capture"},
            {"id": "uart", "kind": "dataset", "target_id": "events"},
        ],
        "pages": [
            {
                "id": "lanes",
                "kind": "dataset",
                "title": "Lanes",
                "bindings": ["logic", "uart"],
                "required": True,
                "plots": [plot],
            }
        ],
    }
    return descriptor, documents, [capture, events], manifest


def validate(specimen: Specimen) -> ValidationReport:
    descriptor, documents, targets, manifest = specimen
    descriptor_raw = encode(descriptor)
    manifest["descriptor_sha256"] = digest(descriptor_raw)
    manifest["plugin_id"] = descriptor["id"]
    manifest_raw = encode(manifest)
    catalogue = {
        "contract_version": "0.3.0",
        "descriptor_sha256": digest(descriptor_raw),
        "targets": targets,
    }
    envelope = {
        "contract_version": "0.3.0",
        "descriptor_sha256": digest(descriptor_raw),
        "resource_root": "ui",
        "manifest": {"path": "manifest.json", "sha256": digest(manifest_raw)},
    }
    return validate_presentation(
        encode(envelope),
        descriptor_raw=descriptor_raw,
        resources={"manifest.json": manifest_raw},
        binding_catalogue=catalogue,
        schema_documents=documents,
        supported_features=frozenset(),
        supported_panels=frozenset(),
        firmware="1.0",
    )


def codes(report: ValidationReport) -> set[str]:
    return {finding.code for finding in report.findings}


def _decoder(source: str = "ch1", binding: str = "uart", settings: bool = False) -> JsonObject:
    lane: JsonObject = {
        "id": "uart-lane",
        "decoder": "UART-REF",
        "source_channel_ids": [source],
        "binding_id": binding,
    }
    if settings:
        lane["settings"] = {"baud": 115200, "frame": "8N1"}
    return {"decoder_lanes": [lane]}


def _hints(*pairs: tuple[str, bool]) -> JsonObject:
    return {"channel_hints": [{"variable_id": p, "visible": v} for p, v in pairs]}


VALID: tuple[tuple[str, Callable[[], Specimen]], ...] = (
    ("minimal_2_lane", lambda: specimen(y_ids=("ch1", "ch2"))),
    (
        "boundary_64_lanes",
        lambda: specimen(
            y_ids=tuple(f"ch{i}" for i in range(1, 65)),
            plot_extra=_hints(*((f"ch{i}", i % 2 == 0) for i in range(1, 65))),
        ),
    ),
    (
        "group_hex_default",
        lambda: specimen(
            plot_extra={"lane_groups": [{"id": "bus-a", "member_ids": ["ch1", "ch2"]}]}
        ),
    ),
    (
        "group_hex_explicit",
        lambda: specimen(
            plot_extra={
                "lane_groups": [
                    {"id": "bus-a", "member_ids": ["ch1", "ch2"], "radix": "hex"}
                ]
            }
        ),
    ),
    (
        "group_decimal",
        lambda: specimen(
            plot_extra={
                "lane_groups": [
                    {"id": "bus-a", "member_ids": ["ch1", "ch2"], "radix": "decimal"}
                ]
            }
        ),
    ),
    (
        "group_default_collapsed",
        lambda: specimen(
            plot_extra={
                "lane_groups": [
                    {
                        "id": "bus-a",
                        "label": "Bus A",
                        "member_ids": ["ch1", "ch2"],
                        "default_collapsed": True,
                    }
                ]
            }
        ),
    ),
    ("decoder_lane", lambda: specimen(plot_extra=_decoder())),
    ("decoder_lane_settings", lambda: specimen(plot_extra=_decoder(settings=True))),
    (
        "hints_visible_only",
        lambda: specimen(y_ids=("ch1", "ch2"), plot_extra=_hints(("ch1", True), ("ch2", False))),
    ),
    (
        "x_integer_seconds",
        lambda: specimen(
            y_ids=("ch1", "ch2"),
            x_var={"id": "ticks", "type": "integer", "unit": "s", "shape": "vector"},
            plot_extra={"x": "ticks"},
        ),
    ),
    (
        "two_groups",
        lambda: specimen(
            plot_extra={
                "lane_groups": [
                    {"id": "bus-a", "member_ids": ["ch1", "ch2"]},
                    {"id": "bus-b", "member_ids": ["ch3", "ch4"], "radix": "decimal"},
                ]
            }
        ),
    ),
    (
        "combined",
        lambda: specimen(
            plot_extra={
                "lane_groups": [{"id": "bus-a", "member_ids": ["ch1", "ch2"]}],
                **_decoder(settings=True),
                **_hints(("ch4", False)),
            }
        ),
    ),
)


def _mutate(
    change: Callable[[Specimen], None],
) -> Callable[[], Specimen]:
    def build() -> Specimen:
        bundle = specimen()
        change(bundle)
        return bundle

    return build


def _retyped(identifier: str, **fields: str) -> Callable[[Specimen], None]:
    def change(bundle: Specimen) -> None:
        row = next(r for r in bundle[2][0]["variables"] if r["id"] == identifier)
        row.update(fields)

    return change


def _analog_specimen(lane_groups: bool = False) -> Specimen:
    """A time_series plot on numeric-scalar axes — a clean analog base, so
    the analog vector's ONLY defect is the lane_groups carry (repairing it
    turns the specimen green; fold row A2)."""
    descriptor = load("examples/class-logic_analyser.json")
    documents = schema_documents(CURRENT)
    readings: JsonObject = {
        "id": "readings",
        "kind": "dataset",
        "action_id": "otdp.logic_analyser.fetch/1.0.0",
        "profile_ids": descriptor["profiles"],
        "measurement_schema_id": "urn:otdp:measurement:0.2.0",
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
    plot: JsonObject = {"kind": "time_series", "binding_id": "logic", "x": "time", "y": ["value"]}
    if lane_groups:
        # Two member ids keep the group schema-valid on its own — the ONLY
        # defect is the analog kind carrying it (the semantic layer never
        # runs: the schema refuses first).
        plot["lane_groups"] = [{"id": "bus-a", "member_ids": ["time", "value"]}]
    manifest: JsonObject = {
        "contract_version": "0.3.0",
        "plugin_id": descriptor["id"],
        "descriptor_sha256": digest(encode(descriptor)),
        "bindings": [{"id": "logic", "kind": "dataset", "target_id": "readings"}],
        "pages": [
            {
                "id": "readings",
                "kind": "dataset",
                "title": "Readings",
                "bindings": ["logic"],
                "required": True,
                "plots": [plot],
            }
        ],
    }
    return descriptor, documents, [readings], manifest


def _observation_bound() -> Callable[[Specimen], None]:
    def change(bundle: Specimen) -> None:
        manifest = bundle[3]
        y_ids = list(manifest["pages"][0]["plots"][0]["y"])
        manifest["bindings"][0] = {"id": "logic", "kind": "observation", "target_id": "reading"}
        manifest["pages"][0]["bindings"] = ["logic"]
        variables = [bundle[2][0]["variables"][0]] + [_channel(i) for i in y_ids]
        bundle[2].append(_observation_target(variables))

    return change


def _decoder_on_observation() -> Callable[[Specimen], None]:
    def change(bundle: Specimen) -> None:
        manifest = bundle[3]
        bundle[2].append(_observation_target(list(bundle[2][0]["variables"])))
        manifest["bindings"].append({"id": "obs", "kind": "observation", "target_id": "reading"})
        manifest["pages"][0]["bindings"].append("obs")
        manifest["pages"][0]["plots"][0].update(_decoder(binding="obs"))

    return change


INVALID: tuple[tuple[str, Callable[[], Specimen], str], ...] = (
    (
        "lanes_65",
        lambda: specimen(y_ids=tuple(f"ch{i}" for i in range(1, 66))),
        "invalid_document",
    ),
    (
        "analog_plot_carrying_lane_groups",
        lambda: _analog_specimen(lane_groups=True),
        "invalid_document",
    ),
    (
        "lanes_plot_carrying_color_role",
        lambda: specimen(
            y_ids=("ch1", "ch2"),
            plot_extra={"channel_hints": [{"variable_id": "ch1", "color_role": "accent"}]},
        ),
        "invalid_document",
    ),
    (
        "duplicate_ids",
        lambda: specimen(
            y_ids=("ch1", "ch2"),
            plot_extra={"lane_groups": [{"id": "ch1", "member_ids": ["ch1", "ch2"]}]},
        ),
        "invalid_document",
    ),
    ("non_string_y_type", _mutate(_retyped("ch1", type="number")), "invalid_plot"),
    ("scalar_y_shape", _mutate(_retyped("ch1", shape="scalar")), "invalid_plot"),
    (
        "x_in_y",
        lambda: specimen(y_ids=("ch1", "ch2"), plot_extra={"y": ["time", "ch1"]}),
        "invalid_plot",
    ),
    ("observation_kind_binding", _mutate(_observation_bound()), "invalid_plot"),
    (
        "group_member_outside_y",
        lambda: specimen(
            y_ids=("ch1", "ch2"),
            plot_extra={"lane_groups": [{"id": "bus-a", "member_ids": ["ch1", "ch9"]}]},
        ),
        "unresolved_reference",
    ),
    (
        "decoder_source_outside_y",
        lambda: specimen(y_ids=("ch1", "ch2"), plot_extra=_decoder(source="ch9")),
        "unresolved_reference",
    ),
    (
        "decoder_binding_absent",
        lambda: specimen(y_ids=("ch1", "ch2"), plot_extra=_decoder(binding="ghost")),
        "unresolved_reference",
    ),
    (
        "decoder_binding_non_dataset",
        _mutate(_decoder_on_observation()),
        "unresolved_reference",
    ),
    (
        "decoder_binding_on_capture_action",
        lambda: specimen(y_ids=("ch1", "ch2"), plot_extra=_decoder(binding="logic")),
        "unresolved_reference",
    ),
    (
        "single_member_group",
        lambda: specimen(
            y_ids=("ch1", "ch2"),
            plot_extra={"lane_groups": [{"id": "bus-a", "member_ids": ["ch1"]}]},
        ),
        "invalid_document",
    ),
    (
        "group_member_double_claimed",
        lambda: specimen(
            plot_extra={
                "lane_groups": [
                    {"id": "bus-a", "member_ids": ["ch1", "ch2"]},
                    {"id": "bus-b", "member_ids": ["ch1", "ch3"]},
                ]
            }
        ),
        "invalid_plot",
    ),
)


@pytest.mark.parametrize(("name", "build"), VALID, ids=[row[0] for row in VALID])
def test_valid_lanes_vector(name: str, build: Callable[[], Specimen]) -> None:
    report = validate(build())
    assert report.valid, (name, report.findings)


@pytest.mark.parametrize(
    ("name", "build", "expected"), INVALID, ids=[row[0] for row in INVALID]
)
def test_invalid_lanes_vector_names_its_code(
    name: str, build: Callable[[], Specimen], expected: str
) -> None:
    report = validate(build())
    assert not report.valid, name
    assert expected in codes(report), (name, expected, report.findings)


def test_vector_counts_match_the_precommitted_counts() -> None:
    assert len(VALID) == 12
    assert len(INVALID) >= 10


def _ui_validator(directory: Path, version: str) -> Draft202012Validator:
    documents = schema_documents(directory)
    registry = Registry().with_resources(
        (value["$id"], Resource.from_contents(value))
        for value in documents.values()
        if isinstance(value, dict) and "$id" in value
    )
    return Draft202012Validator(
        documents[f"https://benchweave.dev/contracts/plugin-ui/{version}/ui-manifest.schema.json"],
        registry=registry,
    )


def test_refusal_delta_predecessor_refuses_the_new_kind() -> None:
    """The reproduced refusal delta (#62 shape): the frozen 0.2.0 schema
    refuses a digital_lanes plot at the kind enum; 0.3.0 admits the same
    plot."""
    descriptor = load("examples/class-logic_analyser.json")
    manifest: JsonObject = {
        "contract_version": "0.2.0",
        "plugin_id": descriptor["id"],
        "descriptor_sha256": "0" * 64,
        "bindings": [{"id": "logic", "kind": "dataset", "target_id": "capture"}],
        "pages": [
            {
                "id": "lanes",
                "kind": "dataset",
                "title": "Lanes",
                "bindings": ["logic"],
                "required": True,
                "plots": [
                    {
                        "kind": "digital_lanes",
                        "binding_id": "logic",
                        "x": "time",
                        "y": ["ch1", "ch2"],
                    }
                ],
            }
        ],
    }
    assert not _ui_validator(PREDECESSOR, "0.2.0").is_valid(manifest)
    manifest["contract_version"] = "0.3.0"
    assert _ui_validator(CURRENT, "0.3.0").is_valid(manifest)


def test_analog_vector_repairs_green() -> None:
    """Fold A2: the analog vector's base specimen is valid — the vector's
    single defect is the lane_groups carry, so repairing it turns green."""
    assert validate(_analog_specimen(lane_groups=False)).valid


def test_preview_wire_refuses_empty_lane_labels() -> None:
    """Fold A6: lane_group and decoder_lane labels carry minLength 1 — the
    channel-label precedent in the same wire; an empty string is refused."""
    schema = json.loads(PREVIEW_WIRE.read_bytes())
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/plot_view"})
    base: JsonObject = {
        "page_id": "lanes",
        "kind": "digital_lanes",
        "binding_id": "logic",
        "title": "Lanes",
        "x": {"label": "t", "unit": "s"},
        "channels": [
            {"variable_id": "ch1", "label": "CH1", "unit": None},
            {"variable_id": "ch2", "label": "CH2", "unit": None},
        ],
    }
    group = dict(base, lane_groups=[{"id": "bus-a", "label": "", "member_ids": ["ch1", "ch2"]}])
    decoder = dict(
        base,
        decoder_lanes=[
            {
                "id": "uart-lane",
                "label": "",
                "decoder": "UART-REF",
                "source_channel_ids": ["ch1"],
                "binding_id": "logic",
            }
        ],
    )
    assert validator.is_valid(base)
    assert not validator.is_valid(group), "an empty lane_group label is refused"
    assert not validator.is_valid(decoder), "an empty decoder_lane label is refused"
