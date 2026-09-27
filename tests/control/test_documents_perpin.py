"""Per-pin descriptor admission: the Q6 classification table (issue #217).

#203 slice 3 (design §3.3): ``_project_full_form`` resolves the descriptor's
own ``otdp_version`` pin BEFORE schema validation and classifies it against
the dependency-policy block — served (retained ∧ in-range ∧ ¬yanked) →
conforming against the pin's own bytes; retained ∧ in-range ∧ yanked →
conforming with a deprecation warning naming the derived move-to; retained ∧
out-of-range → NON-conforming (full operation behind a recorded per-device
operator acknowledgement, VR-14/16/18); not retained → refused with the
VR-37 fields under ``retired_identifier:`` / ``version_unknown:`` — never a
raw const dump.

The ack arm runs on an execution/0.1.0 composition deliberately: the
committed cross-constraint row (execution 0.2.0 requires otdp >=0.2.0,<0.3.0)
refuses a 0.1.x device on an execution/0.2.0 bench even WITH an
acknowledgement — the bench's runtime interface is a compatibility fact no
operator ack overrides. Execution 0.1.0 carries no row (the honest negative
recorded in cross-constraints.json's note), so the non-conforming class is
reachable there and only there in the seed corpus.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchweave.control.documents import (
    AdmissionRejected,
    AdmittedDocuments,
    admit_documents,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
CORPUS = ROOT / "standards"
EXECUTION_010 = CORPUS / "execution" / "0.1.0"


def _lattice(tmp_path: Path, *, execution: str = "0.2.0") -> dict[str, Path]:
    """Spool the fixture lattice; return writable paths for the five documents.

    ``execution`` rewrites every ``contract_version`` so the lattice validates
    against that version's corpus directory (the 0.1.0 schemas are the
    0.2.0 ones minus later additions; the fixture documents use none of the
    added shapes — pinned by the arm that builds this).
    """
    names = {
        "procedure": "procedure-voltage-check.json",
        "policy": "safety-policy.json",
        "bench": "bench.json",
        "binding": "run-binding.json",
        "commissioning": "commissioning.json",
    }
    documents = {
        key: json.loads((FIXTURES / filename).read_text())
        for key, filename in names.items()
    }
    for document in documents.values():
        if isinstance(document, dict) and "contract_version" in document:
            document["contract_version"] = execution
    paths: dict[str, Path] = {}
    for device_id in ("psu", "controller"):
        path = tmp_path / f"descriptor-{device_id}.json"
        path.write_text(
            json.dumps(
                json.loads(
                    (FIXTURES / f"descriptor-sim-{device_id}.json").read_text()
                ),
                indent=2,
            )
        )
        paths[device_id] = path
    policy_path = tmp_path / "safety-policy.json"
    policy_path.write_text(json.dumps(documents["policy"], indent=2))
    lock_path = tmp_path / "package-lock.json"
    lock_path.write_bytes((FIXTURES / "package-lock.json").read_bytes())

    bench = documents["bench"]
    for device in bench["devices"]:
        raw = paths[str(device["id"])].read_bytes()
        descriptor = json.loads(raw)
        device["descriptor"]["id"] = descriptor["id"]
        device["descriptor"]["version"] = descriptor.get(
            "descriptor_version", descriptor.get("version")
        )
        device["descriptor"]["sha256"] = hashlib.sha256(raw).hexdigest()
    bench["policy"]["sha256"] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    bench["package_lock"]["sha256"] = hashlib.sha256(
        lock_path.read_bytes()
    ).hexdigest()
    bench_path = tmp_path / "bench.json"
    bench_path.write_text(json.dumps(bench, indent=2))

    procedure_path = tmp_path / "procedure.json"
    procedure_path.write_text(json.dumps(documents["procedure"], indent=2))
    commissioning = documents["commissioning"]
    for name, path in (
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lock_path),
    ):
        commissioning[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for reference in commissioning["procedure_refs"]:
        reference["sha256"] = hashlib.sha256(
            procedure_path.read_bytes()
        ).hexdigest()
    commissioning_path = tmp_path / "commissioning.json"
    commissioning_path.write_text(json.dumps(commissioning, indent=2))

    binding = documents["binding"]
    for name, path in (
        ("procedure", procedure_path),
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lock_path),
        ("commissioning", commissioning_path),
    ):
        binding[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    binding_path = tmp_path / "run-binding.json"
    binding_path.write_text(json.dumps(binding, indent=2))
    return {
        "procedure": procedure_path,
        "policy": policy_path,
        "bench": bench_path,
        "binding": binding_path,
        "commissioning": commissioning_path,
        **paths,
    }


def _admit(
    tmp_path: Path,
    descriptors: dict[str, dict[str, Any]],
    *,
    execution: str = "0.2.0",
    operator_acknowledgements: dict[str, str] | None = None,
) -> AdmittedDocuments:
    """Run the lattice through the REAL admit_documents with swapped pins.

    ``execution`` selects the composition end to end: every document's
    ``contract_version`` and the ``contracts`` corpus directory move together
    (a 0.1.0 lattice against 0.2.0 schemas is a const refusal, not an arm).
    ``descriptors`` replaces device bodies in-place (spool rewrite) so the
    bench pin digests recompute against the mutated bytes exactly the way
    the census harness does.
    """
    paths = _lattice(tmp_path, execution=execution)
    descriptor_paths: dict[str, Path] = {}
    for device_id, document in descriptors.items():
        path = paths[device_id].parent / f"descriptor-{device_id}.json"
        path.write_text(json.dumps(document, indent=2))
        descriptor_paths[device_id] = path
    for device_id in ("psu", "controller"):
        descriptor_paths.setdefault(device_id, paths[device_id])
    # Repoint the bench pins at the (possibly rewritten) bytes.
    bench = json.loads(paths["bench"].read_text())
    for device in bench["devices"]:
        raw = descriptor_paths[str(device["id"])].read_bytes()
        descriptor = json.loads(raw)
        device["descriptor"]["id"] = descriptor["id"]
        device["descriptor"]["version"] = descriptor.get(
            "descriptor_version", descriptor.get("version")
        )
        device["descriptor"]["sha256"] = hashlib.sha256(raw).hexdigest()
    paths["bench"].write_text(json.dumps(bench, indent=2))
    # The commissioning and binding pin the bench by digest: recompute.
    commissioning = json.loads(paths["commissioning"].read_text())
    commissioning["bench"]["sha256"] = hashlib.sha256(
        paths["bench"].read_bytes()
    ).hexdigest()
    paths["commissioning"].write_text(json.dumps(commissioning, indent=2))
    binding = json.loads(paths["binding"].read_text())
    binding["bench"]["sha256"] = hashlib.sha256(
        paths["bench"].read_bytes()
    ).hexdigest()
    binding["commissioning"]["sha256"] = hashlib.sha256(
        paths["commissioning"].read_bytes()
    ).hexdigest()
    paths["binding"].write_text(json.dumps(binding, indent=2))
    return admit_documents(
        procedure_path=paths["procedure"],
        policy_path=paths["policy"],
        bench_path=paths["bench"],
        binding_path=paths["binding"],
        commissioning_path=paths["commissioning"],
        descriptor_paths=descriptor_paths,
        contracts=CORPUS / "execution" / execution,
        operator_acknowledgements=operator_acknowledgements,
    )


def _psu_document() -> dict[str, Any]:
    psu: dict[str, Any] = json.loads(
        (FIXTURES / "descriptor-sim-psu.json").read_text()
    )
    return psu


def _controller_document() -> dict[str, Any]:
    controller: dict[str, Any] = json.loads(
        (FIXTURES / "descriptor-sim-controller.json").read_text()
    )
    return controller


# --- C1: the mixed bench ------------------------------------------------------


def test_c1_two_pins_admit_in_one_gateway_process(tmp_path: Path) -> None:
    """C1: a 0.2.0-pinned and a 0.2.2-pinned device share ONE admission.

    Each validates against its own bytes (VR-13): the psu slot re-pins 0.2.0
    (a served version), the controller stays at the active 0.2.2, and the
    admission record carries both pins with their conformance classes
    (VR-46's admission surface)."""
    psu = _psu_document()
    psu["otdp_version"] = "0.2.0"
    controller = _controller_document()
    assert controller["otdp_version"] == "0.2.2"
    docs = _admit(tmp_path, {"psu": psu, "controller": controller})
    assert docs.descriptors["psu"]["otdp_version"] == "0.2.0"
    assert docs.descriptors["controller"]["otdp_version"] == "0.2.2"
    assert docs.pins["psu"].otdp_version == "0.2.0"
    assert docs.pins["psu"].conformance == "conforming"
    assert docs.pins["controller"].otdp_version == "0.2.2"
    assert docs.pins["controller"].conformance == "conforming"


def test_c1_per_pin_bytes_not_active_bytes(tmp_path: Path) -> None:
    """Serving-by-pin, not serving-by-active (the A2 reverse arm's admission
    twin): a provider declaration is schema-legal at 0.2.2 and unknown at
    0.2.0, so the provider-bearing corpus example RE-PINNED to 0.2.0 must
    refuse at the pin's own schema. The contract is spooled beside the
    descriptor so the provider pin itself resolves — under the ACTIVE-only
    validator this body is schema-clean (0.2.2 admits the provider key) and
    refuses only at the gateway-only admission row, which is not a ``schema:``
    refusal; that behavioural difference is what makes this arm RED before
    the mechanism and GREEN after."""
    meter = json.loads(
        (CORPUS / "otdp" / "0.2.2" / "examples" / "reference-hid-meter.json").read_text()
    )
    meter["otdp_version"] = "0.2.0"
    (tmp_path / "reference-provider.json").write_bytes(
        (CORPUS / "otdp" / "0.2.2" / "examples" / "reference-provider.json").read_bytes()
    )
    with pytest.raises(AdmissionRejected, match=r"schema: descriptor\[psu\] \$") as raised:
        _admit(tmp_path, {"psu": meter})
    assert "provider" in str(raised.value), str(raised.value)


# --- the Q6 classification table ------------------------------------------------


def test_served_pin_classifies_conforming(tmp_path: Path) -> None:
    psu = _psu_document()
    psu["otdp_version"] = "0.2.0"
    docs = _admit(tmp_path, {"psu": psu})
    pin = docs.pins["psu"]
    assert pin.conformance == "conforming"
    assert pin.note is None
    assert pin.acknowledgement is None


def test_yanked_pin_conforms_with_deprecation_warning_naming_the_move_to(
    tmp_path: Path,
) -> None:
    """Q6 row 2 (the Q10 ruling): 0.2.1 is retained, in-interval, yanked —
    the pin stays conforming, validates against 0.2.1's own bytes, and the
    admission record carries the deprecation warning naming 0.2.2 as the
    derived move-to (highest served version >= the pin)."""
    psu = _psu_document()
    psu["otdp_version"] = "0.2.1"
    docs = _admit(tmp_path, {"psu": psu})
    pin = docs.pins["psu"]
    assert pin.conformance == "conforming"
    assert pin.deprecated is True
    assert "yanked" in str(pin.note)
    assert "0.2.2" in str(pin.note)


def test_c4_out_of_range_pin_is_nonconforming_and_requires_an_ack(
    tmp_path: Path,
) -> None:
    """Q6 row 3 / VR-14/VR-18: a retained but out-of-range pin (0.1.2) is
    NON-conforming — never silently conforming — and without a recorded
    operator acknowledgement admission refuses. The refusal carries the
    ``standard_nonconforming:`` classification and the five VR-37 fields."""
    psu = _psu_document()
    psu["otdp_version"] = "0.1.2"
    with pytest.raises(AdmissionRejected) as raised:
        _admit(tmp_path, {"psu": psu}, execution="0.1.0")
    message = str(raised.value)
    assert message.startswith("operator_ack_required:"), message
    assert "standard_nonconforming:" in message, message
    for field in (
        "standard: otdp",
        "pinned: 0.1.2",
        "supported: >=0.2.0,<0.3.0",
        "move-to:",
        "migration guidance pending",
    ):
        assert field in message, f"VR-37 field {field!r} missing: {message}"


def test_c4_acknowledged_out_of_range_pin_admits_flagged(tmp_path: Path) -> None:
    """VR-18's second half: with the acknowledgement recorded, the
    non-conforming device ADMITS (full operation) and the flag shows on the
    admission record — class ``non-conforming``, the acknowledgement itself
    recorded against the pin it covers. Runs on the execution/0.1.0
    composition: the 0.2.0 bench's cross-constraint row refuses pre-0.2.0
    devices outright (pinned in test_documents_cross_constraint.py)."""
    psu = _psu_document()
    psu["otdp_version"] = "0.1.2"
    docs = _admit(
        tmp_path,
        {"psu": psu},
        execution="0.1.0",
        operator_acknowledgements={"psu": "0.1.2"},
    )
    pin = docs.pins["psu"]
    assert pin.conformance == "non-conforming"
    assert pin.acknowledgement == {"otdp_version": "0.1.2", "recorded_at": None}
    assert docs.descriptors["psu"]["conformance"] == "non-conforming"
    # The other device stays conforming and un-acked: the ack is per-device.
    assert docs.pins["controller"].conformance == "conforming"
    assert docs.pins["controller"].acknowledgement is None


def test_c4_an_ack_naming_a_different_pin_does_not_apply(tmp_path: Path) -> None:
    """The acknowledgement binds the pin it names (Q6: per-device, so one
    ack cannot blanket a bench of unknown pairings) — an ack recorded for
    0.1.1 does not authorise a 0.1.2 device."""
    psu = _psu_document()
    psu["otdp_version"] = "0.1.2"
    with pytest.raises(AdmissionRejected, match=r"^operator_ack_required:"):
        _admit(
            tmp_path,
            {"psu": psu},
            execution="0.1.0",
            operator_acknowledgements={"psu": "0.1.1"},
        )


def test_c4_retired_identifier_refuses_with_vr37(tmp_path: Path) -> None:
    """Q6 row 4 / VR-15: a retired identifier (0.3.0 — used and dead, never
    reissued) refuses with its OWN prefix, distinct from the never-carried
    ``version_unknown:``, carrying the VR-37 fields and the re-target hint
    (OTDP's next minor skips the number)."""
    psu = _psu_document()
    psu["otdp_version"] = "0.3.0"
    with pytest.raises(AdmissionRejected) as raised:
        _admit(tmp_path, {"psu": psu})
    message = str(raised.value)
    assert message.startswith("retired_identifier:"), message
    assert "0.4.0" in message, message
    # All five VR-37 fields, not a sample (review fold R2).
    for field in (
        "standard: otdp",
        "pinned: 0.3.0",
        "supported: >=0.2.0,<0.3.0",
        "move-to:",
        "migration guidance pending",
    ):
        assert field in message, f"VR-37 field {field!r} missing: {message}"


def test_never_carried_pin_refuses_version_unknown(tmp_path: Path) -> None:
    """The three-way split (dependency.py's convergence note): unknown means
    THIS corpus never carried the version — the publish-or-widen
    remediation, distinct from both retired and the non-conforming class."""
    psu = _psu_document()
    psu["otdp_version"] = "9.9.9"
    with pytest.raises(AdmissionRejected) as raised:
        _admit(tmp_path, {"psu": psu})
    message = str(raised.value)
    assert message.startswith("version_unknown:"), message
    assert "never carried" in message, message
    # All five VR-37 fields, not a sample (review fold R2).
    for field in (
        "standard: otdp",
        "pinned: 9.9.9",
        "supported: >=0.2.0,<0.3.0",
        "move-to:",
        "migration guidance pending",
    ):
        assert field in message, f"VR-37 field {field!r} missing: {message}"


def test_malformed_pin_still_refuses_at_the_schema(tmp_path: Path) -> None:
    """A malformed pin (pre-release suffix) never reaches classification —
    the schema's own const error names it honestly (the SDK's no-pin
    posture, mirrored: classification orders only parseable pins)."""
    psu = _psu_document()
    psu["otdp_version"] = "0.3.0-dev"
    with pytest.raises(AdmissionRejected, match=r"schema: descriptor\[psu\]"):
        _admit(tmp_path, {"psu": psu})


# --- the classifier as a pure surface -------------------------------------------


def test_classify_descriptor_pin_is_pure_over_committed_state() -> None:
    """The classification the API-view derivation reuses: total, non-raising
    (refused classes fold to ``non-conforming`` with the refusal note — a
    stored device whose pin later retired must read, never crash), and a
    function of the committed policy block plus the pin only."""
    from benchweave.control.documents import classify_descriptor_pin

    served = classify_descriptor_pin("0.2.0")
    assert (served.conformance, served.deprecated) == ("conforming", False)
    yanked = classify_descriptor_pin("0.2.1")
    assert (yanked.conformance, yanked.deprecated) == ("conforming", True)
    assert "0.2.2" in str(yanked.note)
    nonconforming = classify_descriptor_pin("0.1.2")
    assert nonconforming.conformance == "non-conforming"
    assert "supported: >=0.2.0,<0.3.0" in str(nonconforming.note)
    retired = classify_descriptor_pin("0.3.0")
    assert retired.conformance == "non-conforming"
    assert "retired_identifier:" in str(retired.note)
    unknown = classify_descriptor_pin("9.9.9")
    assert unknown.conformance == "non-conforming"
    assert "version_unknown:" in str(unknown.note)
    malformed = classify_descriptor_pin("0.3.0-dev")
    assert malformed.conformance == "non-conforming"
    assert "version_not_classifiable:" in str(malformed.note)


def test_vr37_text_matches_the_resolver_vocabulary() -> None:
    """The gateway's VR-37 inline text is the resolver's format (the
    deliberate vocabulary convergence, dependency.py's module docstring):
    standard; pinned; supported; move-to; migration."""
    from benchweave.control.documents import classify_descriptor_pin
    from benchweave.standards.dependency import _vr37
    from benchweave.standards.manifest import load_dependency_policy

    root = ROOT
    policy = load_dependency_policy(root)
    row = policy.standards["otdp"]
    expected = _vr37(policy, "otdp", "0.1.2", row, root)
    assert classify_descriptor_pin("0.1.2").note == (
        "standard_nonconforming: " + expected
    )
    # Review fold R9: the same text-equality pin on the refusal arms — the
    # VR-37 segment of the retired and unknown notes is the resolver's
    # formatting, verbatim, not a paraphrase.
    from benchweave.control.documents import classify_descriptor_pin as classify

    for pin in ("0.3.0", "9.9.9"):
        note = str(classify(pin).note)
        assert note.endswith(
            _vr37(policy, "otdp", pin, row, root)
        ), f"{pin}: {note}"


# --- the unexercised edges (review fold R11) --------------------------------------


def _corpus_copy(tmp_path: Path, name: str) -> Path:
    """A mutable copy of the committed corpus (the cross-constraint arm's
    pattern)."""
    import shutil

    corpus = tmp_path / name
    shutil.copytree(CORPUS, corpus)
    return corpus


def _set_otdp_policy(corpus: Path, **fields: object) -> None:
    """Rewrite the policy block's otdp row (merge over the committed row)."""
    manifest = json.loads((corpus / "standards-manifest.json").read_text())
    row = manifest["dependency_policy"]["standards"]["otdp"]
    row.update(fields)
    (corpus / "standards-manifest.json").write_text(json.dumps(manifest, indent=1))


def test_r11_yanked_and_out_of_range_is_nonconforming(tmp_path: Path) -> None:
    """The design table's row-3 precedence: a pin that is BOTH yanked-listed
    and out of range classifies NON-conforming (the range check precedes the
    yank consult), never conforming-with-warning. Crafted policy: 0.1.2
    (retained, below the range floor) also named yanked — the loader's
    cross-checks would refuse this block at validation time, so the arm
    builds it directly and pins the classifier's ORDER."""
    from benchweave.control.documents import classify_descriptor_pin

    corpus = _corpus_copy(tmp_path, "yanked-out-of-range")
    _set_otdp_policy(
        corpus,
        yanked={"0.1.2": {"reason": "synthetic double status", "since": "2026-09-27"}},
    )
    record = classify_descriptor_pin("0.1.2", corpus=corpus)
    assert record.conformance == "non-conforming"
    assert str(record.note).startswith("standard_nonconforming:")
    assert record.deprecated is False


def test_r11_the_exclusive_upper_bound_is_out_of_range(tmp_path: Path) -> None:
    """Half-open interval: a pin at EXACTLY the exclusive upper bound
    (0.3.0 with range <0.3.0) is out of range even when the corpus carries
    its bytes and the identifier is NOT retired — crafted corpus with
    0.3.0 rows present and the retirement list emptied, so the out-of-range
    class is what fires (not retired_identifier, not version_unknown)."""
    import hashlib
    import shutil

    from benchweave.control.documents import classify_descriptor_pin

    corpus = _corpus_copy(tmp_path, "upper-bound")
    shutil.copytree(corpus / "otdp" / "0.2.2", corpus / "otdp" / "0.3.0")
    manifest_path = corpus / "corpus-manifest.json"
    corpus_manifest = json.loads(manifest_path.read_text())
    existing = {row["path"] for row in corpus_manifest["files"]}
    for path in sorted((corpus / "otdp" / "0.3.0").rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(corpus).as_posix()
        if relative not in existing:
            corpus_manifest["files"].append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    manifest_path.write_text(json.dumps(corpus_manifest, indent=1))
    _set_otdp_policy(corpus, retired=[])

    record = classify_descriptor_pin("0.3.0", corpus=corpus)
    assert record.conformance == "non-conforming"
    assert str(record.note).startswith("standard_nonconforming:")
    assert "supported: >=0.2.0,<0.3.0" in str(record.note)
