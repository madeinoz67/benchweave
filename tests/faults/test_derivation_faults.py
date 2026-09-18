"""Fault-injection arm for derived-variable evaluation.

Elementwise failure semantics under repeated evaluation, structural
refusals, and the mutation boundary: the evaluator must degrade in-band
(null/partial/invalid, never NaN/Infinity), refuse structural lies loudly,
and leave the caller's dataset untouched however often it runs.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.measurement.derivation import (
    DerivationRefused,
    DerivationRejected,
    check_derived_variables,
    derive_dataset_variables,
)

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "standards" / "otdp" / "0.1.2" / "examples" / "derivation-vectors.json"


def _dataset(variables: list[dict[str, Any]], axes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "dataset_id": "dataset-faults",
        "kind": "scalar_set",
        "configuration_id": None,
        "acquisition_id": None,
        "started_at": None,
        "clock": {
            "domain_id": "faults",
            "timestamp_source": "host",
            "synchronisation": "unknown",
            "uncertainty_s": None,
        },
        "axes": axes if axes is not None else [],
        "variables": variables,
        "trigger": {"source": "immediate", "time_relative_s": None},
        "status": "complete",
        "context": {},
    }


def _operand(
    vid: str,
    values: list[object],
    unit: str = "V",
    dimensions: list[str] | None = None,
    status: str = "valid",
    status_reason: str | None = None,
) -> dict[str, Any]:
    variable: dict[str, Any] = {
        "id": vid,
        "quantity": "voltage",
        "unit": unit,
        "channel_ids": [f"ch-{vid}"],
        "dtype": "float64",
        "dimensions": dimensions if dimensions is not None else [],
        "values": values,
        "uncertainty": {"status": "unknown"},
        "calibration": {"status": "unknown"},
        "status": status,
    }
    if status_reason is not None:
        variable["status_reason"] = status_reason
    return variable


def _derived(did: str, expression: str, unit: str = "V") -> dict[str, str]:
    return {"id": did, "quantity": "voltage", "unit": unit, "expression": expression}


def test_mixed_element_failures_join_deterministically() -> None:
    """Null operand, division by zero and non-finite in one variable.

    One surviving element keeps the status partial; the reason names every
    cause, deterministically ordered.
    """

    dataset = _dataset(
        [
            _operand("num", [1.0, 1.0, 1e308, None]),
            _operand("den", [2.0, 0.0, 1e-10, 3.0]),
        ]
    )
    output = derive_dataset_variables(dataset, [_derived("ratio", "num / den")])
    ratio = output["variables"][2]
    assert ratio["values"][0] == 0.5
    assert ratio["values"][1] is None  # division by zero
    assert ratio["values"][2] is None  # 1e308 / 1e-10 overflows to non-finite
    assert ratio["values"][3] is None  # null operand propagation
    assert ratio["status"] == "partial"
    reasons = ratio["status_reason"]
    assert "derivation_division_by_zero: num / den" in reasons
    assert "derivation_non_finite_result: num / den" in reasons
    assert "derivation_null_operand: num" in reasons


def test_mixed_failure_reason_order_is_stable_across_runs() -> None:
    dataset = _dataset(
        [
            _operand("num", [1.0, 1.0, None]),
            _operand("den", [0.0, 2.0, 3.0]),
        ]
    )
    first = derive_dataset_variables(dataset, [_derived("ratio", "num / den")])
    for _ in range(4):
        again = derive_dataset_variables(copy.deepcopy(dataset), [_derived("ratio", "num / den")])
        assert json.dumps(again, sort_keys=True) == json.dumps(first, sort_keys=True)


def test_overflow_in_numerator_nulls_the_element() -> None:
    dataset = _dataset(
        [
            _operand("big", [1e308]),
            _operand("two", [2.0]),
        ]
    )
    output = derive_dataset_variables(dataset, [_derived("huge", "big * two")])
    huge = output["variables"][2]
    assert huge["values"] == [None]
    assert huge["status"] == "invalid"
    assert "derivation_non_finite_result: big * two" in huge["status_reason"]


def test_missing_operand_emits_empty_values_not_a_fabricated_null() -> None:
    dataset = _dataset([_operand("present", [1.0])])
    output = derive_dataset_variables(dataset, [_derived("ghost_sum", "present + absent")])
    derived = output["variables"][1]
    assert derived["values"] == []
    assert derived["dimensions"] == []
    assert derived["channel_ids"] == []
    assert derived["status"] == "invalid"
    assert derived["status_reason"] == "derivation_operand_missing: absent"


def test_reevaluating_an_already_derived_dataset_refuses() -> None:
    """Deriving twice over the same output is a collision, not an idempotence.

    The declaration order rule makes the first pass append; a second pass
    over the appended dataset finds the id already present and refuses —
    replay goes through the recorded marker, not a re-append.
    """

    dataset = _dataset([_operand("v", [2.0])])
    once = derive_dataset_variables(dataset, [_derived("d", "v * 2")])
    with pytest.raises(DerivationRefused, match="derivation_id_collision:"):
        derive_dataset_variables(once, [_derived("d", "v * 2")])
    # The first output is itself stable evidence: deriving from the ORIGINAL
    # again reproduces it exactly (fixed point over the operand records).
    twice = derive_dataset_variables(dataset, [_derived("d", "v * 2")])
    assert json.dumps(twice, sort_keys=True) == json.dumps(once, sort_keys=True)


def test_nested_aliasing_never_leaks_into_the_input() -> None:
    shared_values = [1.0, 2.0]
    a = _operand("a", shared_values)
    b = _operand("b", shared_values)  # aliased element list
    dataset = _dataset([a, b])
    snapshot = copy.deepcopy(dataset)
    output = derive_dataset_variables(dataset, [_derived("s", "a + b")])
    assert dataset == snapshot
    assert output["variables"][0]["values"] is shared_values  # copied list, same elements
    assert output["variables"][2]["values"] == [2.0, 4.0]


def test_derived_from_derived_ordering_survives_repeated_evaluation() -> None:
    dataset = _dataset([_operand("a", [10.0]), _operand("b", [4.0])])
    derived = [_derived("first", "a + b"), _derived("half", "first / 2")]
    outputs = [derive_dataset_variables(copy.deepcopy(dataset), derived) for _ in range(5)]
    first = json.dumps(outputs[0], sort_keys=True)
    assert all(json.dumps(output, sort_keys=True) == first for output in outputs[1:])
    assert [variable["values"] for variable in outputs[0]["variables"][2:]] == [
        [14.0],
        [7.0],
    ]
    # The derived-from-derived variable carries the union provenance of the
    # whole operand chain, not just its immediate operand.
    assert outputs[0]["variables"][3]["channel_ids"] == ["ch-a", "ch-b"]


@pytest.mark.parametrize("row", _census_refusals(), ids=lambda row: row["id"])
def test_census_refusals_carry_machine_prefixes(row: dict[str, Any]) -> None:
    dataset = copy.deepcopy(row["dataset"])
    with pytest.raises(DerivationRefused) as raised:
        derive_dataset_variables(dataset, row["derived"])
    assert str(raised.value).startswith(str(row["reason_prefix"])), str(raised.value)
    assert dataset == row["dataset"]  # refusals never mutate either


def _census_refusals() -> list[dict[str, Any]]:
    document = json.loads(VECTORS.read_bytes())
    return [row for row in document["evaluation"] if row["expect"] == "refused"]


def test_static_checks_run_before_any_evaluation_read() -> None:
    """A grammar failure refuses before the dataset is even inspected."""

    with pytest.raises(DerivationRejected) as raised:
        check_derived_variables([_derived("bad", "v +")])
    assert str(raised.value).startswith("derivation_grammar:")
