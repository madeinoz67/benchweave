"""RED control A: descriptor-derived-variable admission is load-bearing.

``control/documents.py _check_descriptor`` must run the grammar/static
checks on ``derived_variables`` at admission: a malformed expression cannot
reach a run. Every rejection carries the machine prefix
``schema: descriptor[<device_id>] derivation:`` followed by the
``derivation_*:`` reason (design §3 seam 1). With the admission call
disabled these tests fail — the malformed descriptors are admitted.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from _harness import FIXTURES, readmit_mutated

from benchweave.control.documents import AdmissionRejected


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
        # RB1/RB3: Unicode digit-class characters the OTDP schema pattern
        # [0-9] excludes — str.isdigit() admits them (superscript two then
        # crashes float(); Arabic-Indic digits silently evaluate).
        ([_declaration(expression="voltage + ²")], "derivation_grammar:"),
        ([_declaration(expression="voltage + ٣")], "derivation_grammar:"),
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


def _poisoned_fixtures(tmp_path: Any) -> Any:
    """A self-consistent fixture lattice whose psu descriptor is poisoned.

    The descriptor carries a Unicode-digit expression; the bench pin is
    recomputed so the lattice's own digest verification passes — the poison
    is semantic (derivation grammar), not a broken pin.
    """

    import hashlib
    import shutil

    fixtures = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    descriptor_path = fixtures / "descriptor-sim-psu.json"
    descriptor = json.loads(descriptor_path.read_text())
    descriptor["derived_variables"] = [
        {
            "id": "rail_offset",
            "quantity": "voltage",
            "unit": "V",
            "expression": "voltage + ²",
        }
    ]
    descriptor_path.write_text(json.dumps(descriptor, indent=2))
    # Re-pin the lattice in dependency order so the poison is semantic only:
    # descriptor -> bench.devices -> commissioning.bench -> binding.
    bench_path = fixtures / "bench.json"
    bench = json.loads(bench_path.read_text())
    for device in bench["devices"]:
        if str(device["id"]) == "psu":
            device["descriptor"]["sha256"] = hashlib.sha256(
                descriptor_path.read_bytes()
            ).hexdigest()
    bench_path.write_text(json.dumps(bench, indent=2))
    bench_sha = hashlib.sha256(bench_path.read_bytes()).hexdigest()

    commissioning_path = fixtures / "commissioning.json"
    commissioning = json.loads(commissioning_path.read_text())
    commissioning["bench"]["sha256"] = bench_sha
    commissioning_path.write_text(json.dumps(commissioning, indent=2))

    binding_path = fixtures / "run-binding.json"
    binding = json.loads(binding_path.read_text())
    binding["bench"]["sha256"] = bench_sha
    binding["commissioning"]["sha256"] = hashlib.sha256(
        commissioning_path.read_bytes()
    ).hexdigest()
    binding_path.write_text(json.dumps(binding, indent=2))
    return fixtures


def test_recovery_surfaces_a_poisoned_descriptor_instead_of_raising(
    tmp_path: Any, caplog: Any
) -> None:
    """RB1: one bad stored descriptor must not kill gateway construction.

    ``_recovery_documents`` runs at app construction; a derivation-
    unparseable stored descriptor previously raised a bare ValueError
    there (startup failure). Recovery must surface the rejection and
    construct anyway: no runs are recovered for an unadmittable lattice,
    the reason is logged, and the dangling-request reconciliation (which
    needs no documents) still runs.
    """

    import logging

    from benchweave.interfaces.app import _recover_interrupted_runs
    from benchweave.state.store import Store

    fixtures = _poisoned_fixtures(tmp_path)
    store = Store.open(tmp_path / "recovery.db")
    try:
        with caplog.at_level(logging.ERROR):
            recovered = _recover_interrupted_runs(
                store,
                fixtures,
                emit_keep=16,
                now_iso=lambda: "2026-09-19T00:00:00Z",
            )
        assert recovered == []
        joined = "\n".join(record.getMessage() for record in caplog.records)
        assert "recovery_admission_rejected" in joined, joined
        assert "derivation_grammar" in joined, joined
    finally:
        store.close()


def test_recovery_surfaces_a_structurally_broken_lattice_instead_of_raising(
    tmp_path: Any, caplog: Any
) -> None:
    """Wave-3 finding 2: containment covers the WHOLE lattice read.

    A truncated run-binding.json is not an AdmissionRejected — it is a
    JSONDecodeError from the pre-try lattice read, and it killed gateway
    construction exactly like the poisoned descriptor did. "One poisoned
    stored document must never kill gateway startup" covers structurally
    broken bytes too: logged, surfaced, recovery skipped, gateway
    constructs.
    """

    import logging

    from benchweave.interfaces.app import _recover_interrupted_runs
    from benchweave.state.store import Store

    fixtures = _poisoned_fixtures(tmp_path)
    (fixtures / "run-binding.json").write_text('{"contract_version": "0.1.0", "')  # truncated
    store = Store.open(tmp_path / "recovery-broken.db")
    try:
        with caplog.at_level(logging.ERROR):
            recovered = _recover_interrupted_runs(
                store,
                fixtures,
                emit_keep=16,
                now_iso=lambda: "2026-09-19T00:00:00Z",
            )
        assert recovered == []
        joined = "\n".join(record.getMessage() for record in caplog.records)
        assert "recovery_admission_rejected" in joined, joined
    finally:
        store.close()
