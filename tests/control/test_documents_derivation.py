"""RED control A: descriptor-derived-variable admission is load-bearing.

``control/documents.py _check_descriptor`` must run the grammar/static
checks on ``derived_variables`` at admission: a malformed expression cannot
reach a run. Every rejection carries the machine prefix
``schema: descriptor[<device_id>] derivation:`` followed by the
``derivation_*:`` reason (design §3 seam 1). With the admission call
disabled these tests fail — the malformed descriptors are admitted.
"""

from __future__ import annotations

from typing import Any

import pytest

from benchweave.control.documents import AdmissionRejected

from conftest import readmit_mutated


def _with_derived(derived: list[dict[str, Any]]) -> Any:
    def mutate(graph: dict[str, Any]) -> None:
        graph["descriptors"]["psu"]["derived_variables"] = derived

    return mutate


def _declaration(
    did: str = "rail_offset",
    expression: str = "voltage - 4.5",
    **overrides: Any,
) -> dict[str, Any]:
    declaration: dict[str, Any] = {
        "id": did,
        "quantity": "voltage",
        "unit": "V",
        "expression": expression,
    }
    declaration.update(overrides)
    return declaration


def test_admission_accepts_a_well_formed_declaration(tmp_path: Any) -> None:
    docs = readmit_mutated(tmp_path, _with_derived([_declaration()]))
    assert docs.descriptors["psu"]["derived_variables"] == [_declaration()]


@pytest.mark.parametrize(
    ("derived", "prefix"),
    [
        ([_declaration(expression="voltage +")], "derivation_grammar:"),
        ([_declaration(expression="")], "derivation_grammar:"),
        ([_declaration(expression="voltage / current *")], "derivation_grammar:"),
        ([_declaration(), _declaration()], "derivation_duplicate_id:"),
        ([_declaration(expression="rail_offset + voltage")], "derivation_self_reference:"),
        (
            [
                _declaration(did="second", expression="first + 1"),
                _declaration(did="first", expression="voltage + 1"),
            ],
            "derivation_cycle:",
        ),
        ([_declaration(expression="42")], "derivation_grammar:"),
        ([{"id": "broken", "quantity": "voltage", "unit": "V"}], "derivation_shape:"),
        ([_declaration(did="1st")], "derivation_shape:"),
        (["not-an-object"], "derivation_shape:"),
    ],
)
def test_admission_rejects_malformed_declarations(
    tmp_path: Any, derived: list[dict[str, Any]], prefix: str
) -> None:
    with pytest.raises(AdmissionRejected) as raised:
        readmit_mutated(tmp_path, _with_derived(derived))
    message = str(raised.value)
    assert message.startswith("schema: descriptor[psu] derivation: "), message
    assert prefix in message, message


def test_admission_rejects_a_non_list_array(tmp_path: Any) -> None:
    with pytest.raises(AdmissionRejected) as raised:
        readmit_mutated(tmp_path, _with_derived("voltage - 4.5"))  # type: ignore[arg-type]
    message = str(raised.value)
    assert message.startswith("schema: descriptor[psu] derivation: "), message
    assert "derivation_shape:" in message, message


def test_admission_ignores_descriptors_without_the_array(tmp_path: Any) -> None:
    docs = readmit_mutated(tmp_path, lambda graph: None)
    assert "derived_variables" not in docs.descriptors["psu"]
