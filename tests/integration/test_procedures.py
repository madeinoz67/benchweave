"""WP05 admission of the executable fixture document set.

Proves the three admission properties this slice owns: the fixture corpus
admits through schema validation plus the full digest pin lattice, any byte
tamper surfaces as a machine-matchable ``digest_mismatch``, and any structural
drift (unknown fields, duplicate keys, nonfinite numbers) surfaces as
``schema`` — inherited from the exact-byte decoder and the vendored
execution-v1.0.0 schemas. No semantic checks (profiles, policy envelope) are
exercised here; those belong to later admission stages.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from benchweave.control.documents import AdmissionRejected, AdmittedDocuments, admit_documents

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "execution"
DESCRIPTORS = {
    "psu": FIXTURES / "descriptor-sim-psu.json",
    "controller": FIXTURES / "descriptor-sim-controller.json",
}


def admit() -> AdmittedDocuments:
    return admit_documents(
        procedure_path=FIXTURES / "procedure-voltage-check.json",
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=FIXTURES / "run-binding.json",
        commissioning_path=FIXTURES / "commissioning.json",
        descriptor_paths=DESCRIPTORS,
    )


def _admit_tampered_procedure(text: str, tmp_path: Path) -> None:
    tampered = tmp_path / "procedure.json"
    tampered.write_text(text)
    admit_documents(
        procedure_path=tampered,
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=FIXTURES / "run-binding.json",
        commissioning_path=FIXTURES / "commissioning.json",
        descriptor_paths=DESCRIPTORS,
    )


def test_fixtures_admit() -> None:
    docs = admit()
    assert docs.procedure["id"] == "voltage-check"
    assert docs.binding["request_id"] == "req-voltage-check-1"


def test_digest_mismatch_rejected(tmp_path: Path) -> None:
    tampered = tmp_path / "procedure.json"
    tampered.write_text((FIXTURES / "procedure-voltage-check.json").read_text()
                        .replace('"voltage_v": 5.0', '"voltage_v": 5.1'))
    with pytest.raises(AdmissionRejected, match="digest_mismatch"):
        admit_documents(
            procedure_path=tampered,
            policy_path=FIXTURES / "safety-policy.json",
            bench_path=FIXTURES / "bench.json",
            binding_path=FIXTURES / "run-binding.json",
            commissioning_path=FIXTURES / "commissioning.json",
            descriptor_paths=DESCRIPTORS,
        )


def test_unknown_field_rejected_as_schema_error(tmp_path: Path) -> None:
    original = (FIXTURES / "procedure-voltage-check.json").read_text()
    with pytest.raises(AdmissionRejected, match=r"^schema:"):
        _admit_tampered_procedure(original[:-1] + ',"unexpected": 1}', tmp_path)


def test_duplicate_key_rejected_by_decoder(tmp_path: Path) -> None:
    original = (FIXTURES / "procedure-voltage-check.json").read_text()
    with pytest.raises(AdmissionRejected, match="schema: .*duplicate_key"):
        _admit_tampered_procedure(
            original.replace('"id": "voltage-check",', '"id": "voltage-check", "id": "clone",'),
            tmp_path,
        )


def test_nonfinite_number_rejected_by_decoder(tmp_path: Path) -> None:
    original = (FIXTURES / "procedure-voltage-check.json").read_text()
    with pytest.raises(AdmissionRejected, match="schema: .*nonfinite_number"):
        _admit_tampered_procedure(
            original.replace('"voltage_v": 5.0', '"voltage_v": 1e999'), tmp_path
        )


def test_missing_descriptor_pin_rejected() -> None:
    with pytest.raises(AdmissionRejected, match="pin_absent"):
        admit_documents(
            procedure_path=FIXTURES / "procedure-voltage-check.json",
            policy_path=FIXTURES / "safety-policy.json",
            bench_path=FIXTURES / "bench.json",
            binding_path=FIXTURES / "run-binding.json",
            commissioning_path=FIXTURES / "commissioning.json",
            descriptor_paths={"psu": DESCRIPTORS["psu"]},
        )
