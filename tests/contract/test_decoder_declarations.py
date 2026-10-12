"""Decoder-declaration corpus arms (issue #443, OTDP 0.2.3).

Three surfaces, all corpus-side:

- **Schema vectors** against ``otdp-decoder.schema.json``: the minimal
  positive shape plus the refusals the schema itself carries (closed
  surface, three-component version, option default/values type pairing).
  The PD2/PD4/PD5 semantic rules are pinned by the devices suite's
  mutation rows in ``tests/contracts/test_architecture.py`` — this file
  does not duplicate that checker.
- **The real-extraction declarations** (i2c, spi, uart — from the public
  sigrok decoder corpus's class surfaces — plus onewire_link as the
  genericity control from outside the extraction set) validate and carry
  the declared class/row counts the design's acceptance metrics name.
- **Per-pin exactness**: the retained 0.2.2 descriptor validates against
  the 0.2.2 schema (no ``decoders`` key there) while the 0.2.3 descriptor
  carrying ``decoders`` validates against the 0.2.3 schema and is refused
  by the 0.2.2 schema — M-D's both-ways reading, derived from the
  standards manifest so a future bump re-points these arms by itself.

What this does NOT catch: gateway admission semantics for decoder pins
(slice 2's mirror), binary-class emission (deferred), and stacking
(deferred) — all named deferrals in the design record.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]

# The class/row/binary counts below are the extraction's own measurements
# over the source PD class surfaces; they pin the translation (design §9
# M-A/M-B) so a re-extraction that drops a class fails here by count.
DECLARATION_COUNTS: dict[str, tuple[int, int, int | None]] = {
    "decoder-i2c.json": (11, 3, 4),
    "decoder-spi.json": (7, 7, 2),
    "decoder-uart.json": (18, 10, 3),
    "decoder-onewire-link.json": (5, 3, None),
}


def _active_otdp_dir() -> Path:
    """The manifest-active OTDP corpus directory, never a hand-listed path."""
    manifest = json.loads(
        (ROOT / "standards" / "standards-manifest.json").read_text(encoding="utf-8")
    )
    entry = next(item for item in manifest["standards"] if item["id"] == "otdp")
    version = entry["version"]
    assert isinstance(version, str) and version
    return ROOT / "standards" / "otdp" / version


def _decoder_schema() -> dict[str, Any]:
    document = json.loads(
        (_active_otdp_dir() / "otdp-decoder.schema.json").read_text(encoding="utf-8")
    )
    assert isinstance(document, dict)
    return document


def _minimal_declaration() -> dict[str, Any]:
    return {
        "id": "reference_minimal",
        "version": "1.0.0",
        "name": "Minimal",
        "channels": [],
        "options": [
            {"id": "shift", "default": "left", "values": ["left", "right"]},
            {"id": "width", "default": 8},
        ],
        "annotations": [{"id": "frame", "label": "Frame"}],
        "annotation_rows": [
            {"id": "frames", "label": "Frames", "annotation_ids": ["frame"]}
        ],
    }


def _valid(document: dict[str, Any]) -> bool:
    return not list(Draft202012Validator(_decoder_schema()).iter_errors(document))


def test_minimal_declaration_validates() -> None:
    assert _valid(_minimal_declaration())


def test_missing_required_field_is_refused() -> None:
    for key in ("id", "version", "name", "channels", "options", "annotations"):
        document = _minimal_declaration()
        document.pop(key)
        assert not _valid(document), key


def test_additional_property_is_refused() -> None:
    assert not _valid({**_minimal_declaration(), "inputs": ["i2c"]})


def test_two_component_version_is_refused() -> None:
    assert not _valid({**_minimal_declaration(), "version": "1.0"})


def test_uppercase_decoder_id_is_refused() -> None:
    assert not _valid({**_minimal_declaration(), "id": "Reference-Capital"})


def test_option_value_type_disagreeing_with_default_is_refused() -> None:
    document = _minimal_declaration()
    document["options"][0]["values"] = [1, 2]
    assert not _valid(document)


def test_boolean_default_with_number_values_is_refused() -> None:
    document = _minimal_declaration()
    document["options"].append(
        {"id": "invert", "default": False, "values": [0, 1]},
    )
    assert not _valid(document)


def test_free_numeric_option_without_values_is_valid() -> None:
    document = _minimal_declaration()
    document["options"].append({"id": "depth", "default": 4})
    assert _valid(document)


def test_real_extraction_declarations_validate_and_count() -> None:
    examples = _active_otdp_dir() / "examples"
    for name, (classes, rows, binaries) in DECLARATION_COUNTS.items():
        document = json.loads((examples / name).read_text(encoding="utf-8"))
        assert _valid(document), name
        assert len(document["annotations"]) == classes, name
        assert len(document["annotation_rows"]) == rows, name
        if binaries is None:
            assert "binary" not in document, name
        else:
            assert len(document["binary"]) == binaries, name
        # F2: rows reference classes by id, so every row member resolves.
        annotation_ids = {a["id"] for a in document["annotations"]}
        for row in document["annotation_rows"]:
            assert set(row["annotation_ids"]) <= annotation_ids, (name, row["id"])


def test_extraction_and_control_shape_spread_is_real() -> None:
    """M-A/M-B's underpowered guard: the four declarations span the shape
    axes the schema must not encode (required-channel count 0/1/2, free and
    float-valued options, binary present and absent). If a future edit
    collapses the spread, the genericity claim stops being certified by
    this set and the widening obligation in the design record opens."""
    examples = _active_otdp_dir() / "examples"
    required_counts = {
        name: len(json.loads((examples / name).read_text(encoding="utf-8"))["channels"])
        for name in DECLARATION_COUNTS
    }
    assert sorted(required_counts.values()) == [0, 1, 1, 2]
    uart = json.loads((examples / "decoder-uart.json").read_text(encoding="utf-8"))
    stop_bits = next(o for o in uart["options"] if o["id"] == "stop_bits")
    assert isinstance(stop_bits["default"], float)
    spi = json.loads((examples / "decoder-spi.json").read_text(encoding="utf-8"))
    wordsize = next(o for o in spi["options"] if o["id"] == "wordsize")
    assert "values" not in wordsize


def test_declarations_are_pinned_by_the_example_descriptor() -> None:
    """PD1's descriptor half, corpus-side: the declaring example pins every
    declaration with the digest of the bytes on disk."""
    import hashlib

    descriptor = json.loads(
        (_active_otdp_dir() / "examples" / "class-logic_analyser.json").read_text(
            encoding="utf-8"
        )
    )
    pins = descriptor.get("decoders", [])
    assert {pin["id"] for pin in pins} == {
        "i2c",
        "onewire_link",
        "spi",
        "uart",
    }
    for pin in pins:
        pinned_bytes = (
            _active_otdp_dir() / "examples" / pin["path"]
        ).read_bytes()
        assert hashlib.sha256(pinned_bytes).hexdigest() == pin["sha256"], pin["id"]
        document = json.loads(pinned_bytes)
        assert document["id"] == pin["id"]


def test_decode_annotated_vector_classes_resolve_per_pin() -> None:
    """M-C's resolution arm: every ``class`` value of every
    decode_annotated vector resolves against the pinned declaration of the
    decoder the vector names — the corpus evidence a generic renderer needs
    zero decoder-specific code to draw every declared row."""
    examples = _active_otdp_dir() / "examples"
    descriptor = json.loads(
        (examples / "class-logic_analyser.json").read_text(encoding="utf-8")
    )
    declarations = {
        pin["id"]: json.loads((examples / pin["path"]).read_text(encoding="utf-8"))
        for pin in descriptor["decoders"]
    }
    vectors = json.loads(
        (examples / "class-action-vectors.json").read_text(encoding="utf-8")
    )["vectors"]
    annotated = [
        v
        for v in vectors
        if v["request"]["arguments"]["action_id"]
        == "otdp.logic_analyser.decode_annotated/1.0.0"
    ]
    assert annotated, "no decode_annotated vectors in the corpus"
    for vector in annotated:
        decoder = vector["request"]["arguments"]["input"]["decoder"]
        declaration = declarations[decoder]
        annotation_ids = {a["id"] for a in declaration["annotations"]}
        dataset = vector["result"]["data"]["result"]
        assert dataset["kind"] == "event_log"
        variable_ids = {variable["id"] for variable in dataset["variables"]}
        assert {"start_s", "end_s", "class", "text"} <= variable_ids, vector["id"]
        class_variable = next(
            variable for variable in dataset["variables"] if variable["id"] == "class"
        )
        unresolved = [
            value for value in class_variable["values"] if value not in annotation_ids
        ]
        assert not unresolved, (vector["id"], unresolved)
        context = dataset.get("context", {})
        assert context.get("decoder_id") == f"{decoder}/{declaration['version']}"
        assert context.get("channel_map") == vector["request"]["arguments"]["input"][
            "channel_map"
        ]


def test_per_pin_descriptor_exactness_across_the_bump() -> None:
    """M-D's per-pin arm: a 0.2.2-pinned descriptor and the 0.2.3 descriptor
    each validate against their OWN version's schema, and the 0.2.3 body is
    refused by the 0.2.2 schema (``decoders`` is additional there) — the
    bump refuses nothing that was valid and admits the new field only
    through the new pin."""
    active = _active_otdp_dir()
    version = active.name
    assert version != "0.2.2", "the active version must have advanced past 0.2.2"
    retained = ROOT / "standards" / "otdp" / "0.2.2"
    schema_retained = json.loads(
        (retained / "otdp-device-descriptor.schema.json").read_text(encoding="utf-8")
    )
    schema_active = json.loads(
        (active / "otdp-device-descriptor.schema.json").read_text(encoding="utf-8")
    )
    document_retained = json.loads(
        (retained / "examples" / "class-logic_analyser.json").read_text(encoding="utf-8")
    )
    document_active = json.loads(
        (active / "examples" / "class-logic_analyser.json").read_text(encoding="utf-8")
    )
    validator_retained = Draft202012Validator(schema_retained)
    validator_active = Draft202012Validator(schema_active)
    assert not list(validator_retained.iter_errors(document_retained))
    assert not list(validator_active.iter_errors(document_active))
    assert list(validator_retained.iter_errors(document_active)), (
        "the 0.2.2 schema must refuse the decoders field the 0.2.3 pin admits"
    )
