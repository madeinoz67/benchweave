"""Read side-effect schema vectors (issue #445, OTDP 0.2.3).

The S20 coherence conditional's own arms, over the active corpus's
reference-controller example mutated into the amended-plugin shape
(invented reference names throughout — ``battery_voltage``/``led_state``
are the corpus's own synthetic names):

- **M-A expressiveness**: a descriptor whose readable parameters declare
  ``read_policy.side_effect: "state_change"`` with the read verb raised to
  ``state_change`` validates against the 0.2.3 schema (the field is
  expressible and coherent);
- **M-B coherence refusal**: the same body with the verb reverted to
  ``none`` is refused, with a failing instance location under
  ``$.operations`` — the conditional's ``then`` arm, discriminated from
  the closed-vocabulary unknown-key error class at ``$.parameters``;
- **the dead-shape control**: the amended body pinned ``0.2.2`` is refused
  by the 0.2.2 schema (``read_policy`` is closed there) — the PATCH class
  premise set is empty both ways: nothing 0.2.2-admissible carries the
  field, so nothing 0.2.3 newly refuses;
- **the per-pin control**: the plain 0.2.2 body validates against the
  0.2.2 schema unchanged — the design's per-pin reading (CON-1/#215),
  resolved the way the #443 decoder vectors resolved it: what stays
  admissible under 0.2.2 is the pre-amendment shape, and the amended body
  under the 0.2.2 schema is the refusal arm above;
- **one-directionality**: a verb over-classified to ``state_change`` with
  no parameter declaring it stays valid (conservative classification is
  legal — the write-minimum rule's dual, one direction only).

What this does NOT catch: gateway procedure admission (the
``state_changing_read:`` seam lives in ``tests/control/``) and the
corpus-example census (the devices suite) — this file pins the schema
conditional alone.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


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


def _amended_shape(version_dir: Path) -> dict[str, Any]:
    """The amended-plugin shape: two declaring parameters, raised verb.

    Built from the corpus's own reference-controller example (synthetic
    names) so every surrounding field is schema-real; the mutation touches
    only the two layers S20 connects.
    """
    body: dict[str, Any] = json.loads(
        (version_dir / "examples" / "reference-controller.json").read_text(
            encoding="utf-8"
        )
    )
    for parameter in body["parameters"]:
        if parameter["name"] in ("battery_voltage", "led_state"):
            parameter.setdefault("read_policy", {})["side_effect"] = "state_change"
    body["operations"]["read"]["side_effect"] = "state_change"
    return body


def test_amended_shape_validates_under_active_schema() -> None:
    """M-A: the declaring shape with a raised verb is expressible."""
    active = _active_otdp_dir()
    body = _amended_shape(active)
    assert _validator_for(active).is_valid(body)


def test_incoherent_verb_refused_at_operations_path() -> None:
    """M-B: a ``none`` verb over declaring parameters is refused by the
    conditional — with the failing location under ``$.operations``, not
    the closed-vocabulary error class at ``$.parameters``."""
    active = _active_otdp_dir()
    body = _amended_shape(active)
    body["operations"]["read"]["side_effect"] = "none"
    validator = _validator_for(active)
    assert not validator.is_valid(body)
    paths = [error.json_path for error in validator.iter_errors(body)]
    assert any(path.startswith("$.operations") for path in paths), paths


def test_amended_body_refused_by_prior_pin_schema() -> None:
    """The dead-shape control: the same body pinned 0.2.2 is refused by
    the 0.2.2 schema — the PATCH premise set is empty both ways."""
    active = _active_otdp_dir()
    prior = active.parent / "0.2.2"
    body = _amended_shape(active)
    body["otdp_version"] = "0.2.2"
    assert not _validator_for(prior).is_valid(body)


def test_prior_pin_plain_body_validates_unchanged() -> None:
    """The per-pin control: the plain 0.2.2 body validates against the
    0.2.2 schema (per-pin admission holds; CON-1/#215)."""
    prior = _active_otdp_dir().parent / "0.2.2"
    body = json.loads(
        (prior / "examples" / "reference-controller.json").read_text(encoding="utf-8")
    )
    assert _validator_for(prior).is_valid(body)


def test_overclassified_verb_stays_valid() -> None:
    """One-directionality: raising the verb without any declaring
    parameter is conservative over-classification — legal by design."""
    active = _active_otdp_dir()
    body = json.loads(
        (active / "examples" / "reference-controller.json").read_text(encoding="utf-8")
    )
    body["operations"]["read"]["side_effect"] = "state_change"
    assert _validator_for(active).is_valid(body)
