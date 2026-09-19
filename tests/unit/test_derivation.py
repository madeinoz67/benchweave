"""Derived-variable grammar, statics and evaluation over the vendored census.

The census (``standards/otdp/0.2.0/examples/derivation-vectors.json``) is the
normative machine truth for the OTDP 0.2.0 derived-variable feature
(measurement-model.md §8/M15, otdp-specification.md S19): every grammar,
static and evaluation row must agree with
``benchweave.measurement.derivation`` exactly — accept, reject with the
expected ``derivation_*:`` reason prefix, or byte-identical canonical JSON
for derived outputs. Determinism is pinned two ways: repeated derivation on
fresh inputs is stable, and replaying a recorded expression over the
recorded operand values (an independent arithmetic oracle) reproduces the
recorded values.
"""

from __future__ import annotations

import copy
import json
import sys
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
VECTORS = ROOT / "standards" / "otdp" / "0.2.0" / "examples" / "derivation-vectors.json"


def _census() -> dict[str, Any]:
    document = json.loads(VECTORS.read_bytes())
    assert isinstance(document, dict)
    return document


def _declaration(expression: str) -> dict[str, str]:
    """Wrap a bare expression as one declaration (the census harness shape)."""

    return {"id": "probe0", "quantity": "probe", "unit": "1", "expression": expression}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# --- grammar census -----------------------------------------------------------


def test_census_grammar_row_counts_meet_the_rule() -> None:
    rows = _census()["grammar"]
    accepts = [row for row in rows if row["expect"] == "accept"]
    rejects = [row for row in rows if row["expect"] == "reject"]
    assert len(rows) >= 30, "the census must carry at least 30 grammar rows"
    assert len(accepts) >= 15 and len(rejects) >= 15
    # Every reject row names its expected machine prefix.
    assert all(row["reason_prefix"].startswith("derivation_") for row in rejects)


@pytest.mark.parametrize("row", _census()["grammar"], ids=lambda row: row["id"])
def test_grammar_census(row: dict[str, Any]) -> None:
    declaration = _declaration(str(row["expression"]))
    if row["expect"] == "accept":
        check_derived_variables([declaration])
    else:
        with pytest.raises(DerivationRejected) as raised:
            check_derived_variables([declaration])
        assert str(raised.value).startswith(str(row["reason_prefix"])), str(raised.value)


# --- static census ------------------------------------------------------------


@pytest.mark.parametrize("row", _census()["static"], ids=lambda row: row["id"])
def test_static_census(row: dict[str, Any]) -> None:
    derived = row["derived"]
    if row["expect"] == "accept":
        check_derived_variables(derived)
    else:
        with pytest.raises(DerivationRejected) as raised:
            check_derived_variables(derived)
        assert str(raised.value).startswith(str(row["reason_prefix"])), str(raised.value)


def test_static_census_has_both_directions() -> None:
    rows = _census()["static"]
    assert any(row["expect"] == "accept" for row in rows)
    assert {
        str(row.get("reason_prefix")) for row in rows if row["expect"] == "reject"
    } >= {
        "derivation_duplicate_id:",
        "derivation_self_reference:",
        "derivation_cycle:",
        "derivation_shape:",
    }


# --- evaluation census ---------------------------------------------------------


@pytest.mark.parametrize("row", _census()["evaluation"], ids=lambda row: row["id"])
def test_evaluation_census(row: dict[str, Any]) -> None:
    dataset = copy.deepcopy(row["dataset"])
    if row["expect"] == "refused":
        with pytest.raises(DerivationRefused) as raised:
            derive_dataset_variables(dataset, row["derived"])
        assert str(raised.value).startswith(str(row["reason_prefix"])), str(raised.value)
        return
    output = derive_dataset_variables(dataset, row["derived"])
    original_count = len(row["dataset"]["variables"])
    appended = output["variables"][original_count:]
    assert [_canonical(variable) for variable in appended] == [
        _canonical(variable) for variable in row["expected"]
    ], f"derived variables disagree with the census expectation for {row['id']}"
    # The plugin-returned dataset object is never mutated (no-mutation pin,
    # design §7 item 5 — asserted on every evaluation row, not just one).
    assert dataset == row["dataset"], f"derivation mutated the input for {row['id']}"


def test_evaluation_census_row_count_meets_the_rule() -> None:
    rows = _census()["evaluation"]
    assert len(rows) >= 12
    assert sum(1 for row in rows if row["expect"] == "refused") >= 5


# --- determinism and replay ----------------------------------------------------


def test_repeated_derivation_is_deterministic() -> None:
    for row in _census()["evaluation"]:
        if row["expect"] != "derived":
            continue
        first = derive_dataset_variables(copy.deepcopy(row["dataset"]), row["derived"])
        for _ in range(3):
            again = derive_dataset_variables(copy.deepcopy(row["dataset"]), row["derived"])
            assert _canonical(again) == _canonical(first), row["id"]


def test_recorded_outputs_replay_exactly() -> None:
    """Replay: the recorded expression over the recorded operand values.

    The oracle is deliberately independent of the module under test: Python
    arithmetic shares the census grammar's precedence and associativity, so
    evaluating the expression text with the operand values bound to names
    must reproduce the recorded binary64 results element for element. This
    is test-side only — the module itself contains no string-to-code path.
    """

    for row in _census()["evaluation"]:
        if row["expect"] != "derived":
            continue
        variables = {variable["id"]: variable for variable in row["dataset"]["variables"]}
        for expected in row["expected"]:
            marker = expected.get("derivation")
            if marker is None or any(
                operand not in variables for operand in marker["operand_ids"]
            ):
                # Derived-from-derived rows replay through their operand
                # chain, already pinned by the census expectation itself.
                continue
            length = len(next(
                variables[operand]["values"]
                for operand in marker["operand_ids"]
                if variables[operand]["values"]
            ))
            for index in range(length):
                environment = {
                    operand: (
                        variables[operand]["values"][index]
                        if index < len(variables[operand]["values"])
                        else None
                    )
                    for operand in marker["operand_ids"]
                }
                # Nulls propagate before arithmetic; a null operand element
                # pins a null recorded element.
                if any(value is None for value in environment.values()):
                    assert expected["values"][index] is None, (row["id"], expected["id"])
                    continue
                try:
                    replayed = eval(  # noqa: S307 — test-side oracle over corpus text
                        marker["expression"], {"__builtins__": {}}, dict(environment)
                    )
                except ZeroDivisionError:
                    # Python raises where the evaluator nulls: the recorded
                    # element must be the in-band loss.
                    assert expected["values"][index] is None, (row["id"], expected["id"])
                    continue
                recorded = expected["values"][index]
                if recorded is None:
                    continue  # non-finite losses are pinned by status
                assert replayed == recorded, (row["id"], expected["id"], index)


# --- module-local edges the census cannot express compactly --------------------


def test_nesting_boundary_is_exactly_32() -> None:
    check_derived_variables([_declaration("(" * 32 + "x0" + ")" * 32)])
    with pytest.raises(DerivationRejected, match="derivation_grammar:"):
        check_derived_variables([_declaration("(" * 33 + "x0" + ")" * 33)])


def test_length_boundary_is_exactly_256() -> None:
    exact = "x0" + " + 1" * 63 + "  "  # 2 + 252 + 2 trailing spaces = 256
    assert len(exact) == 256
    check_derived_variables([_declaration(exact)])
    over = exact + " "
    assert len(over) == 257
    with pytest.raises(DerivationRejected, match="derivation_grammar:"):
        check_derived_variables([_declaration(over)])


def _dataset(variables: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "dataset_id": "dataset-local",
        "kind": "scalar_set",
        "configuration_id": None,
        "acquisition_id": None,
        "started_at": None,
        "clock": {
            "domain_id": "local",
            "timestamp_source": "host",
            "synchronisation": "unknown",
            "uncertainty_s": None,
        },
        "axes": [],
        "variables": variables,
        "trigger": {"source": "immediate", "time_relative_s": None},
        "status": "complete",
        "context": {},
    }


def _operand(
    vid: str, value: object, unit: str = "V", channels: list[str] | None = None
) -> dict[str, Any]:
    return {
        "id": vid,
        "quantity": "voltage",
        "unit": unit,
        "channel_ids": channels if channels is not None else ["ch1"],
        "dtype": "float64",
        "dimensions": [],
        "values": [value],
        "uncertainty": {"status": "unknown"},
        "calibration": {"status": "unknown"},
        "status": "valid",
    }


def test_number_side_of_plus_is_not_unit_checked() -> None:
    """The residual, pinned: only identifier-leaf +/- operands are compared.

    A numeric literal carries no unit to compare, so ``v - 4.5`` is admitted
    and evaluated; M15 states the residual rather than pretending a unit
    algebra exists.
    """

    output = derive_dataset_variables(
        _dataset([_operand("v", 5.0)]),
        [{"id": "rail", "quantity": "voltage", "unit": "V", "expression": "v - 4.5"}],
    )
    rail = output["variables"][1]
    assert rail["values"] == [0.5]
    assert rail["status"] == "valid"


def test_honest_marker_on_existing_variable_passes_the_liar_check() -> None:
    truthful = _operand("sum_ok", 3.0, channels=["ch1", "ch2"])
    truthful["derivation"] = {
        "kind": "expression",
        "expression": "p1 + p2",
        "operand_ids": ["p2", "p1"],  # order-insensitive agreement
    }
    output = derive_dataset_variables(
        _dataset([_operand("p1", 1.0), _operand("p2", 2.0), truthful]),
        [{"id": "extra", "quantity": "voltage", "unit": "V", "expression": "p1 - p2"}],
    )
    assert [variable["id"] for variable in output["variables"]] == [
        "p1",
        "p2",
        "sum_ok",
        "extra",
    ]


def test_malformed_dataset_variables_refuses() -> None:
    with pytest.raises(DerivationRefused, match="derivation_dataset_malformed:"):
        derive_dataset_variables(
            {"variables": "not-a-list"},
            [{"id": "d", "quantity": "q", "unit": "1", "expression": "x0"}],
        )
    with pytest.raises(DerivationRefused, match="derivation_dataset_malformed:"):
        derive_dataset_variables(
            {"variables": ["not-an-object"]},
            [{"id": "d", "quantity": "q", "unit": "1", "expression": "x0"}],
        )


def test_empty_declaration_list_is_a_no_op() -> None:
    dataset = _dataset([_operand("v", 1.0)])
    output = derive_dataset_variables(dataset, [])
    assert output["variables"] == dataset["variables"]


# --- the float64 conversion boundary is pinned below ----------------------------------------


# --- the float64 conversion boundary (mechanism-critic B1/B2) -------------------


# --- liar-check bounds and duplicate-id datasets (refute RB4) ------------------


def test_marker_with_empty_operand_ids_refuses() -> None:
    """The liar-check enforces its own schema bounds: operand_ids minItems 1."""

    constant = _operand("constant", 3.0)
    constant["derivation"] = {
        "kind": "expression",
        "expression": "42",
        "operand_ids": [],
    }
    with pytest.raises(DerivationRefused, match="derivation_marker_mismatch:"):
        derive_dataset_variables(
            _dataset([constant]),
            [{"id": "d", "quantity": "q", "unit": "1", "expression": "constant + 1"}],
        )


def test_marker_with_duplicate_operand_ids_refuses() -> None:
    """The liar-check enforces its own schema bounds: operand_ids uniqueItems."""

    a = _operand("a1", 1.0)
    forged = _operand("sum_ok", 2.0)
    forged["derivation"] = {
        "kind": "expression",
        "expression": "a1 + a1",
        "operand_ids": ["a1", "a1"],
    }
    with pytest.raises(DerivationRefused, match="derivation_marker_mismatch:"):
        derive_dataset_variables(
            _dataset([a, forged]),
            [{"id": "d", "quantity": "q", "unit": "1", "expression": "a1 + 1"}],
        )


def test_marker_with_unparseable_expression_refuses_as_a_forged_marker() -> None:
    """Wave-3 finding 4: marker-liar failures are uniform.

    A recorded marker whose expression fails to parse is a forged record —
    DerivationRefused under derivation_marker_mismatch:, not a
    DerivationRejected grammar error (the declaration path's family).
    """

    a = _operand("a7", 1.0)
    forged = _operand("bad_marker", 2.0)
    forged["derivation"] = {
        "kind": "expression",
        "expression": "a7 +",
        "operand_ids": ["a7"],
    }
    with pytest.raises(DerivationRefused, match="derivation_marker_mismatch:"):
        derive_dataset_variables(
            _dataset([a, forged]),
            [{"id": "d", "quantity": "q", "unit": "1", "expression": "a7 + 1"}],
        )


def test_duplicate_dataset_variable_ids_refuse_derivation() -> None:
    """A duplicate-id dataset (M01 violation) refuses derivation reads.

    Silent last-duplicate-wins operand resolution would launder which
    variable fed the computation — the same stance the derived-id
    collision refusal takes for derived ids, mirrored for pre-existing
    duplicates.
    """

    twin_a = _operand("v1", 1.0)
    twin_b = _operand("v1", 9.0)  # same id, different values
    with pytest.raises(DerivationRefused, match="derivation_duplicate_variable:"):
        derive_dataset_variables(
            _dataset([twin_a, twin_b]),
            [{"id": "d", "quantity": "q", "unit": "1", "expression": "v1 + 1"}],
        )


@pytest.mark.parametrize(
    ("element", "readable"),
    [
        (None, True),  # the unavailable marker, propagates as null
        (42, True),  # small int: exactly binary64
        (2**53, True),  # the exact-representability boundary itself
        (2**53 + 1, False),  # the first int binary64 silently rounds (B2)
        (int(sys.float_info.max), False),  # far past the boundary, though finite
        (10**400, False),  # raises OverflowError on float() unguarded (B1)
        (True, False),  # bool is not a float64 element
        ("7", False),  # strings are data, not numbers
        (float("nan"), False),  # never NaN (measurement-model.md section 3)
        (float("inf"), False),  # never Infinity
        (0.5, True),  # ordinary finite float
    ],
    ids=[
        "null", "small-int", "two-pow-53", "two-pow-53-plus-1",
        "max-float-int", "huge-int", "bool", "string", "nan", "inf", "float",
    ],
)
def test_element_boundary_table(element: object, readable: bool) -> None:
    """Every element class either derives exactly or refuses TYPED.

    The guard must be total (no untyped exception — an OverflowError from
    ``float(10**400)`` would escape the executor's typed handling and skip
    the protective transition) and exact (an int beyond 2^53 would be
    silently rounded by the conversion, laundering a representation change
    through a "valid" result).
    """

    dataset = _dataset([_operand("probe", element)])
    declaration = [
        {"id": "d", "quantity": "probe", "unit": "1", "expression": "probe + 0"}
    ]
    if not readable:
        with pytest.raises(DerivationRefused, match="derivation_dtype_mismatch:"):
            derive_dataset_variables(dataset, declaration)
        return
    output = derive_dataset_variables(dataset, declaration)
    derived = output["variables"][1]
    if element is None:
        assert derived["values"] == [None]
        assert derived["status"] == "invalid"
        return
    expected: object = element if isinstance(element, float) else float(int(str(element))) + 0.0
    assert derived["values"] == [expected]
    assert derived["status"] == "valid"


def test_uncertainty_and_calibration_are_structurally_unknown() -> None:
    output = derive_dataset_variables(
        _dataset([_operand("v", 2.0)]),
        [{"id": "d", "quantity": "voltage", "unit": "V", "expression": "v * 2"}],
    )
    derived = output["variables"][1]
    assert derived["uncertainty"] == {"status": "unknown"}
    assert derived["calibration"] == {"status": "unknown"}
    assert derived["dtype"] == "float64"
    assert derived["derivation"] == {
        "kind": "expression",
        "expression": "v * 2",
        "operand_ids": ["v"],
    }
