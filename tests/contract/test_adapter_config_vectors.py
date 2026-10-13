"""Adapter-configuration schema vectors (issue #447, OTDP 0.2.3).

The ``integration.adapter.configuration`` field's own schema arms, over the
active corpus's class-logic_analyser example mutated into the
image-carrying shape (invented reference names throughout — the image id
``bench_image`` and the file ``reference-analyzer-image.bin`` are this
slice's synthetic fixture names):

- **M-A expressiveness**: a descriptor whose adapter declares
  ``configuration.files = [{id, path, sha256}]`` validates against the
  0.2.3 schema (the field is expressible; RED side, disclosed in the RED
  commit: the same body refused against the pre-change tree with the
  schema error naming ``$.integration.adapter`` — ``additionalProperties``);
- **the dead-shape control**: the amended body pinned ``0.2.2`` is
  refused by the 0.2.2 schema — the PATCH class premise set is empty both
  ways: nothing 0.2.2-admissible carries the field, so nothing 0.2.3
  newly refuses;
- **the per-pin control**: the plain 0.2.2 body validates against the
  0.2.2 schema unchanged (per-pin admission holds; CON-1/#215);
- **shape negatives**: an empty ``files`` array (``minItems 1``), a
  byte-identical duplicate entry (``uniqueItems``), a bad ``id`` pattern,
  a bad ``sha256`` pattern, an unknown key inside a triple, and a scalar
  sibling of ``files`` — each refuses, the last naming the FILES ONLY
  design (a scalar map is a secrets/host-locality channel the shape must
  not express; design §2.3).

What this does NOT catch: the resolution posture (relative-POSIX,
no-follow, containment) — schema shape only here, the posture is S21 plus
the mirrors (``tests/control/test_adapter_configuration.py`` pins the
admission mirror, ``tests/integration/test_adapter_configuration_loading.py``
pins the loader inventory resolution) — and the corpus-example census
(the devices suite).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]

#: Real digest of the synthetic image bytes the mirrors and fixtures pin.
#: Deterministic invented bytes — not any product's image.
IMAGE_BYTES = b"BW-SYNTHETIC-IMAGE-v1" + bytes(range(64)) * 4
IMAGE_SHA256 = hashlib.sha256(IMAGE_BYTES).hexdigest()

TRIPLE: dict[str, str] = {
    "id": "bench_image",
    "path": "reference-analyzer-image.bin",
    "sha256": IMAGE_SHA256,
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


def _validator_for(version_dir: Path) -> Draft202012Validator:
    schema = json.loads(
        (version_dir / "otdp-device-descriptor.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema)


def _configured_shape(version_dir: Path) -> dict[str, Any]:
    """The image-carrying shape: the corpus's own class-logic_analyser
    fixture plus one declared configuration triple (synthetic names)."""
    body: dict[str, Any] = json.loads(
        (version_dir / "examples" / "class-logic_analyser.json").read_text(
            encoding="utf-8"
        )
    )
    body["integration"]["adapter"]["configuration"] = {"files": [dict(TRIPLE)]}
    return body


def test_configured_shape_validates_under_active_schema() -> None:
    """M-A: the configuration-carrying shape is expressible."""
    active = _active_otdp_dir()
    assert _validator_for(active).is_valid(_configured_shape(active))


def test_configured_body_refused_by_prior_pin_schema() -> None:
    """The dead-shape control: the same body pinned 0.2.2 is refused by
    the 0.2.2 schema — the PATCH premise set is empty both ways."""
    active = _active_otdp_dir()
    prior = active.parent / "0.2.2"
    body = _configured_shape(active)
    body["otdp_version"] = "0.2.2"
    validator = _validator_for(prior)
    assert not validator.is_valid(body)
    paths = [error.json_path for error in validator.iter_errors(body)]
    assert any(path.startswith("$.integration.adapter") for path in paths), paths


def test_prior_pin_plain_body_validates_unchanged() -> None:
    """The per-pin control: the plain 0.2.2 body validates against the
    0.2.2 schema (per-pin admission holds; CON-1/#215)."""
    prior = _active_otdp_dir().parent / "0.2.2"
    body = json.loads(
        (prior / "examples" / "class-logic_analyser.json").read_text(encoding="utf-8")
    )
    assert _validator_for(prior).is_valid(body)


def test_empty_files_refuses() -> None:
    """``minItems 1``: a configuration that configures nothing is dead
    weight — the refusal names the files array."""
    active = _active_otdp_dir()
    body = _configured_shape(active)
    body["integration"]["adapter"]["configuration"]["files"] = []
    validator = _validator_for(active)
    assert not validator.is_valid(body)
    paths = [error.json_path for error in validator.iter_errors(body)]
    assert any("configuration" in path and "files" in path for path in paths), paths


def test_byte_identical_duplicate_refuses() -> None:
    """``uniqueItems``: two identical triples refuse (id/path uniqueness
    beyond byte-identity is S21 semantic, mirrored — not a schema arm)."""
    active = _active_otdp_dir()
    body = _configured_shape(active)
    body["integration"]["adapter"]["configuration"]["files"] = [
        dict(TRIPLE),
        dict(TRIPLE),
    ]
    assert not _validator_for(active).is_valid(body)


def test_distinct_triples_stay_valid() -> None:
    """Two DISTINCT triples stay valid — uniqueness refuses only the
    byte-identical pair at the schema layer."""
    active = _active_otdp_dir()
    body = _configured_shape(active)
    second = dict(TRIPLE, id="bench_overlay", path="reference-analyzer-overlay.bin")
    body["integration"]["adapter"]["configuration"]["files"] = [dict(TRIPLE), second]
    assert _validator_for(active).is_valid(body)


def test_bad_id_pattern_refuses() -> None:
    """``id`` uses the corpus snake_case pattern (``^[a-z][a-z0-9_]*$``)."""
    active = _active_otdp_dir()
    body = _configured_shape(active)
    body["integration"]["adapter"]["configuration"]["files"] = [
        dict(TRIPLE, id="Bench-Image")
    ]
    assert not _validator_for(active).is_valid(body)


def test_bad_sha256_pattern_refuses() -> None:
    active = _active_otdp_dir()
    body = _configured_shape(active)
    body["integration"]["adapter"]["configuration"]["files"] = [
        dict(TRIPLE, sha256="not-hex")
    ]
    assert not _validator_for(active).is_valid(body)


def test_unknown_key_inside_triple_refuses() -> None:
    """The triple is exactly ``{id, path, sha256}`` — the contracts item
    shape verbatim, closed."""
    active = _active_otdp_dir()
    body = _configured_shape(active)
    body["integration"]["adapter"]["configuration"]["files"] = [
        {**TRIPLE, "description": "extra"}
    ]
    assert not _validator_for(active).is_valid(body)


def test_scalar_sibling_of_files_refuses() -> None:
    """FILES ONLY: a free-form scalar map beside ``files`` refuses — the
    shape cannot express a secrets or host-locality channel (§2.3)."""
    active = _active_otdp_dir()
    body = _configured_shape(active)
    configuration = body["integration"]["adapter"]["configuration"]
    configuration["settings"] = {"gain": 4}
    assert not _validator_for(active).is_valid(body)


def test_configuration_optional_unchanged_admits() -> None:
    """The no-regression control: the same fixture WITHOUT the field
    still validates (the field is optional; nothing that validated before
    can carry it — the dead-shape proof's forward direction)."""
    active = _active_otdp_dir()
    body = json.loads(
        (active / "examples" / "class-logic_analyser.json").read_text(encoding="utf-8")
    )
    validator = _validator_for(active)
    assert validator.is_valid(body)
    untouched = copy.deepcopy(body)
    assert validator.is_valid(untouched)
