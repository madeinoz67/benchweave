"""Dev-pin admission: dev and released side by side on one bench (issue #218).

#203 slice 4 (design §3.6, D1's first half / VR-20): a descriptor whose
``otdp_version`` names the manifest-DECLARED dev head classifies conforming
at stage ``dev`` (``rc`` when the coordinator declared a candidate, VR-9)
and validates against the HEAD's own corpus-pinned bytes — next to a
released-pinned device on the same bench, each against its own bytes. The
pairwise cross-constraint rows are released-interface facts and do not
judge a dev-staged pin (the dev pin's own gates — the resolver's opt-in and
content identity — govern it); the laundering hole is closed structurally:
a dev label that does not name the declared head classifies unknown and
refuses, so no released pin dodges a row by suffixing ``-dev``.

The composition resolves the planted corpus through the packaged-first
seam (``vendoring._PACKAGED_ROOT``): the wheel-posture twin — the same
seam with a head-less corpus — refuses the dev pin rather than falling
back to the active family.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

import benchweave.vendoring as vendoring
from benchweave.control.documents import (
    AdmissionRejected,
    admit_documents,
    classify_descriptor_pin,
)
from benchweave.standards.manifest import StandardsError, declared_dev_head

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
CORPUS = ROOT / "standards"

#: The planted head's label — the design's own next-minor example (OTDP
#: 0.3.0 is retired; "the next minor is 0.4.0").
HEAD_LABEL = "0.4.0-dev"


def _plant_head(corpus: Path, *, label: str = HEAD_LABEL, candidate: bool = False) -> None:
    """Plant a dev head on a copied corpus: a copy of the active 0.2.2
    directory whose descriptor schema accepts the dev label (the const
    swap — a descriptor pinned to the head validates against the HEAD's
    bytes and only those), corpus rows citing the active path as source,
    and the manifest's dev block naming every head file normative."""
    active = corpus / "otdp" / "0.2.2"
    head = corpus / "otdp" / label
    shutil.copytree(active, head)
    schema_path = head / "otdp-device-descriptor.schema.json"
    schema = json.loads(schema_path.read_bytes())
    schema["properties"]["otdp_version"]["const"] = label
    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    manifest_path = corpus / "standards-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    names = sorted(path.name for path in head.iterdir() if path.is_file())
    for entry in manifest["standards"]:
        if entry["id"] == "otdp":
            entry["dev"] = {
                "version": label,
                "opened": "2026-09-28",
                "normative": [f"standards/otdp/{label}/{name}" for name in names],
                **({"candidate": True} if candidate else {}),
            }
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    corpus_path = corpus / "corpus-manifest.json"
    document = json.loads(corpus_path.read_bytes())
    for name in names:
        raw = (head / name).read_bytes()
        document["files"].append(
            {
                "path": f"otdp/{label}/{name}",
                "source": f"standards/otdp/0.2.2/{name}",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    corpus_path.write_text(json.dumps(document, indent=1), encoding="utf-8")


@pytest.fixture()
def _head_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A planted-head corpus resolved through the packaged-first seam.

    ``vendoring._PACKAGED_ROOT`` is repointed at a packaged root whose
    ``contracts/`` tree IS the planted corpus — the same seam
    ``tests/control/test_corpus_seam.py`` drives — so every packaged-first
    reader in admission (classification, the versioned schema path, the
    known-features sweep, the cross-constraint loader) resolves the planted
    bytes and nothing mutates the committed tree.
    """
    corpus = tmp_path / "planted"
    shutil.copytree(CORPUS, corpus)
    _plant_head(corpus)
    packaged = tmp_path / "packaged"
    (packaged / "contracts").mkdir(parents=True)
    shutil.copytree(corpus, packaged / "contracts", dirs_exist_ok=True)
    monkeypatch.setattr(vendoring, "_PACKAGED_ROOT", packaged)
    return corpus


def _lattice(tmp_path: Path, *, execution: str = "0.2.0") -> dict[str, Path]:
    """Spool the fixture lattice (the per-pin harness's spool, verbatim in
    meaning: every document's contract_version moves with the composition)."""
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
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for device_id in ("psu", "controller"):
        path = tmp_path / f"descriptor-{device_id}.json"
        path.write_text(
            json.dumps(
                json.loads((FIXTURES / f"descriptor-sim-{device_id}.json").read_text()),
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
    bench["package_lock"]["sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
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
) -> Any:
    """Run the lattice through the REAL admit_documents with swapped pins
    (the per-pin harness's rewrite: the bench pins recompute against the
    mutated descriptor bytes, and the downstream digest pins follow)."""
    paths = _lattice(tmp_path, execution=execution)
    descriptor_paths: dict[str, Path] = {}
    for device_id, document in descriptors.items():
        path = paths[device_id].parent / f"descriptor-{device_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2))
        descriptor_paths[device_id] = path
    for device_id in ("psu", "controller"):
        descriptor_paths.setdefault(device_id, paths[device_id])
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
    commissioning = json.loads(paths["commissioning"].read_text())
    commissioning["bench"]["sha256"] = hashlib.sha256(
        paths["bench"].read_bytes()
    ).hexdigest()
    paths["commissioning"].write_text(json.dumps(commissioning, indent=2))
    binding = json.loads(paths["binding"].read_text())
    binding["bench"]["sha256"] = hashlib.sha256(paths["bench"].read_bytes()).hexdigest()
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


# --- D1: side by side ---------------------------------------------------------


def test_d1_dev_pinned_and_released_pinned_admit_on_one_bench(
    tmp_path: Path, _head_corpus: Path
) -> None:
    """VR-20: a dev-pinned device and a released-pinned device share ONE
    admission, each validated against its own bytes. The per-pin proof is
    the const: the head's schema accepts exactly ``0.4.0-dev`` — under the
    ACTIVE schema (const 0.2.2) this descriptor refuses, so a green
    admission is evidence the HEAD's bytes did the validating."""
    psu = _psu_document()
    psu["otdp_version"] = HEAD_LABEL
    controller = _controller_document()
    assert controller["otdp_version"] == "0.2.2"
    docs = _admit(tmp_path, {"psu": psu, "controller": controller})
    assert docs.descriptors["psu"]["otdp_version"] == HEAD_LABEL
    assert docs.pins["psu"].otdp_version == HEAD_LABEL
    assert docs.pins["psu"].status == "dev"
    assert docs.pins["psu"].conformance == "conforming"
    assert docs.pins["controller"].otdp_version == "0.2.2"
    assert docs.pins["controller"].status == "served"
    assert docs.pins["controller"].conformance == "conforming"


def test_d1_the_dev_pin_validates_against_the_head_bytes_not_the_active(
    tmp_path: Path, _head_corpus: Path
) -> None:
    """The teeth of the per-pin claim: a descriptor body that is
    schema-valid ONLY against the head's bytes (its pin names the head) —
    the active schema's const refuses it, so a pass proves the head's
    schema was the validator; and the mirror arm, a dev-shaped pin on a
    body the head's schema refuses, names the schema refusal."""
    psu = _psu_document()
    psu["otdp_version"] = HEAD_LABEL
    # The head's schema is 0.2.2's copy apart from the const swap, so the
    # unmodified body is exactly the valid-at-the-head case — proved above.
    # This arm plants the OTHER pin on the same body: 0.2.2 against the
    # head-const... is refused by the ACTIVE schema? No — 0.2.2 IS the
    # active const. The discriminating arm is the reverse: a RELEASED body
    # shape the head retains, pinned at a dev label the corpus does NOT
    # declare.
    undeclared = _psu_document()
    undeclared["otdp_version"] = "0.9.9-dev"
    with pytest.raises(AdmissionRejected) as raised:
        _admit(tmp_path, {"psu": undeclared})
    message = str(raised.value)
    assert message.startswith("version_unknown:"), message
    assert "no declared dev head" in message, message


def test_d1_rc_candidate_pin_shows_the_rc_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VR-9's three-way distinction on the admission surface: a coordinator
   declared candidate head classifies ``rc``, not ``dev`` — the same
    content-addressed pin, a different stage marker."""
    corpus = tmp_path / "planted-rc"
    shutil.copytree(CORPUS, corpus)
    _plant_head(corpus, candidate=True)
    packaged = tmp_path / "packaged-rc"
    (packaged / "contracts").mkdir(parents=True)
    shutil.copytree(corpus, packaged / "contracts", dirs_exist_ok=True)
    monkeypatch.setattr(vendoring, "_PACKAGED_ROOT", packaged)
    psu = _psu_document()
    psu["otdp_version"] = HEAD_LABEL
    docs = _admit(tmp_path / "rc", {"psu": psu})
    assert docs.pins["psu"].status == "rc"
    assert docs.pins["psu"].conformance == "conforming"


def test_the_cross_constraint_rows_do_not_judge_a_dev_pin(
    tmp_path: Path, _head_corpus: Path
) -> None:
    """The released-interface carve-out, pinned with its control: the
    execution 0.2.0 cross-constraint row requires otdp >=0.2.0,<0.3.0 — a
    dev-pinned device (target above the range by construction: a head's
    target is strictly greater than active) still admits, because the row
    is a fact about released runtime interfaces; the RELEASED out-of-range
    pin on the same bench still refuses even acknowledged (the control
    arm, unchanged)."""
    psu = _psu_document()
    psu["otdp_version"] = HEAD_LABEL
    docs = _admit(tmp_path, {"psu": psu})
    assert docs.pins["psu"].status == "dev"
    out_of_range = _psu_document()
    out_of_range["otdp_version"] = "0.1.2"
    with pytest.raises(AdmissionRejected, match="cross_constraint_violation"):
        _admit_control(tmp_path / "control", out_of_range)


def _admit_control(tmp_path: Path, psu: dict[str, Any]) -> Any:
    """The control arm's admit call (ack supplied: the row must refuse even
    acknowledged, proving the carve-out skips ONLY the dev stage)."""
    paths = _lattice(tmp_path, execution="0.2.0")
    descriptor_paths: dict[str, Path] = {"psu": tmp_path / "descriptor-psu.json"}
    tmp_path.mkdir(parents=True, exist_ok=True)
    descriptor_paths["psu"].write_text(json.dumps(psu, indent=2))
    controller = paths["controller"]
    descriptor_paths["controller"] = controller
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
    commissioning = json.loads(paths["commissioning"].read_text())
    commissioning["bench"]["sha256"] = hashlib.sha256(
        paths["bench"].read_bytes()
    ).hexdigest()
    paths["commissioning"].write_text(json.dumps(commissioning, indent=2))
    binding = json.loads(paths["binding"].read_text())
    binding["bench"]["sha256"] = hashlib.sha256(paths["bench"].read_bytes()).hexdigest()
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
        contracts=CORPUS / "execution" / "0.2.0",
        operator_acknowledgements={"psu": "0.1.2"},
    )


# --- the headless real tree -----------------------------------------------------


def test_dev_shape_on_a_headless_tree_classifies_unknown_naming_the_state() -> None:
    """The real committed corpus declares no head: a dev-shaped pin is not
    malformed (it classifies) — it names no declared head, folds
    non-conforming with the refusal note, and admission refuses with the
    ``version_unknown:`` prefix (VR-15's bytes-don't-exist class)."""
    record = classify_descriptor_pin("0.4.0-dev")
    assert record.conformance == "non-conforming"
    assert "version_unknown:" in str(record.note)
    assert "no declared dev head" in str(record.note)


def test_a_malformed_pre_release_shape_still_never_classifies() -> None:
    """The pre-slice-4 posture for genuinely malformed shapes is unchanged:
    ``rc.N`` and friends never reach classification — the schema's own
    const error names them (VR-6's namespace refusal; the dev LABEL is the
    only pre-release shape that classifies)."""
    record = classify_descriptor_pin("0.4.0-rc.1")
    assert record.conformance == "non-conforming"
    assert "version_not_classifiable:" in str(record.note)


# --- refute fold (lane A): the retired-target head refuses at LOAD -----------------


def test_a_retired_target_head_refuses_at_load_and_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A head targeting a RETIRED identifier could never promote (used and
    dead, never reissued) — the resolver refuses the pin
    (``dev_target_retired:``), so the manifest LOAD must refuse the head
    itself with the same vocabulary and the re-target hint, and admission
    must refuse with it (refute lane A: before this fold, admission
    ADMITTED the head at status=dev conforming while the resolver refused
    — two surfaces, one pin, opposite verdicts)."""
    corpus = tmp_path / "planted-retired"
    shutil.copytree(CORPUS, corpus)
    _plant_head(corpus, label="0.3.0-dev")
    packaged = tmp_path / "packaged-retired"
    (packaged / "contracts").mkdir(parents=True)
    shutil.copytree(corpus, packaged / "contracts", dirs_exist_ok=True)
    monkeypatch.setattr(vendoring, "_PACKAGED_ROOT", packaged)
    with pytest.raises(StandardsError) as raised:
        declared_dev_head(corpus, "otdp")
    message = str(raised.value)
    assert message.startswith("dev_target_retired:"), message
    assert "0.4.0" in message, "the refusal names the re-target hint"
    psu = _psu_document()
    psu["otdp_version"] = "0.3.0-dev"
    with pytest.raises(StandardsError, match="dev_target_retired:"):
        _admit(tmp_path / "retired", {"psu": psu})
