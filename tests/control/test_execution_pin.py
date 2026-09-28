"""The execution per-document pin: routing, refusals, and the run guard.

#203 slice 6 (issue #220, design record
``.claude/deep-review/2026-09-28-issue220-execution-pin-design.md``): the
bench document's own ``contract_version`` classifies against the
dependency-policy block and routes all five execution documents to the
pinned corpus version's digest-verified schemas — the pin's bytes, never
the ambient composition's (CON-1's amendment).

Fixture provenance: ``tests/fixtures/lattice-execution-0.1.0/`` is
recovered BYTE-FROZEN from git history — ``git show
4743bd4:fixtures/execution/*`` (the #176 row-D demo lattice, the last
commit whose fixture lattice carried ``contract_version: "0.1.0"`` before
54a59fa promoted execution 0.2.0). F1a admits the eight files with ZERO
byte edits (the KILL arm: any in-tree lattice needing edits fires F1d's
control instead); every mutation in this module lives in ``tmp_path``
copies with the digest pins repointed (the per-pin suite's spool pattern),
never in the frozen tree. The 0.1.0 schemas the routing resolves are
digest-verified against their corpus-manifest rows at admission (the
mechanism's ``_versioned_schema_path``); the descriptors and the package
lock are operator documents with no corpus rows — their integrity rides
the lattice's own digest pins, and the extraction was byte-verified
against the git objects at recovery time.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from benchweave.control.documents import (
    AdmissionRejected,
    AdmittedDocuments,
    admit_documents,
    classify_descriptor_pin,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"
CORPUS = ROOT / "standards"
LATTICE_010 = ROOT / "tests" / "fixtures" / "lattice-execution-0.1.0"
NOW_WALL = "2026-09-11T00:00:00Z"

#: The run-activation harness's own limits shape (``QUOTA_LIMITS`` there);
#: the guard test needs only the keys the retaining quota and the worker
#: seam read.
QUOTA_LIMITS: dict[str, int] = {
    "max_json_bytes": 1048576,
    "max_page_size": 1000,
    "max_chunk_bytes": 65536,
    "max_lease_ms": 600000,
    "min_poll_ms": 100,
    "max_admission_ms": 5000,
    "max_dataset_bytes": 8 * 1024 * 1024,
    "max_event_batch": 64,
}


def _010_paths() -> dict[str, Path]:
    """The frozen lattice's paths, keyed as ``admit_documents`` takes them."""
    return {
        "procedure": LATTICE_010 / "procedure-voltage-check.json",
        "policy": LATTICE_010 / "safety-policy.json",
        "bench": LATTICE_010 / "bench.json",
        "binding": LATTICE_010 / "run-binding.json",
        "commissioning": LATTICE_010 / "commissioning.json",
        "psu": LATTICE_010 / "descriptor-sim-psu.json",
        "controller": LATTICE_010 / "descriptor-sim-controller.json",
    }


def _admit_010(**kwargs: Any) -> AdmittedDocuments:
    """Admit the frozen 0.1.0 lattice exactly as it sits on disk."""
    p = _010_paths()
    return admit_documents(
        procedure_path=p["procedure"],
        policy_path=p["policy"],
        bench_path=p["bench"],
        binding_path=p["binding"],
        commissioning_path=p["commissioning"],
        descriptor_paths={"psu": p["psu"], "controller": p["controller"]},
        now_wall=NOW_WALL,
        **kwargs,
    )


def _spool_and_repin(
    tmp_path: Path,
    source: Path,
    documents: dict[str, dict[str, Any]],
    descriptors: dict[str, dict[str, Any]],
) -> dict[str, Path]:
    """Write a mutated copy of ``source`` lattice and repoint EVERY digest
    pin, in dependency order (the per-pin suite's ``_lattice`` pattern).

    ``documents`` carries the five contract documents (any of them possibly
    mutated), ``descriptors`` the two device bodies. All bytes are rewritten
    with ``indent=2`` — the lattice's own pins are recomputed against the
    rewritten bytes, so only mutations the pins cannot see (none here) would
    be lost. The frozen tree is never touched.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    raws: dict[str, bytes] = {}

    def write(key: str, filename: str, document: dict[str, Any]) -> None:
        path = tmp_path / filename
        path.write_text(json.dumps(document, indent=2))
        paths[key] = path
        raws[key] = path.read_bytes()

    for device_id, document in descriptors.items():
        path = tmp_path / f"descriptor-{device_id}.json"
        path.write_text(json.dumps(document, indent=2))
        paths[device_id] = path

    write("policy", "safety-policy.json", documents["policy"])
    lock_path = tmp_path / "package-lock.json"
    lock_path.write_bytes((source / "package-lock.json").read_bytes())
    paths["package_lock"] = lock_path
    raws["package_lock"] = lock_path.read_bytes()
    write("procedure", "procedure.json", documents["procedure"])

    bench = documents["bench"]
    for device in bench["devices"]:
        device_id = str(device["id"])
        descriptor = json.loads(paths[device_id].read_bytes())
        device["descriptor"]["id"] = descriptor["id"]
        device["descriptor"]["version"] = descriptor["descriptor_version"]
        device["descriptor"]["sha256"] = hashlib.sha256(
            paths[device_id].read_bytes()
        ).hexdigest()
    bench["policy"]["sha256"] = hashlib.sha256(raws["policy"]).hexdigest()
    bench["package_lock"]["sha256"] = hashlib.sha256(
        lock_path.read_bytes()
    ).hexdigest()
    write("bench", "bench.json", bench)

    commissioning = documents["commissioning"]
    for name in ("bench", "policy", "package_lock"):
        commissioning[name]["sha256"] = hashlib.sha256(raws[name]).hexdigest()
    for reference in commissioning["procedure_refs"]:
        if (
            reference["id"] == documents["procedure"]["id"]
            and reference["version"] == documents["procedure"]["version"]
        ):
            reference["sha256"] = hashlib.sha256(raws["procedure"]).hexdigest()
    write("commissioning", "commissioning.json", commissioning)

    binding = documents["binding"]
    for name in ("procedure", "bench", "policy", "package_lock", "commissioning"):
        binding[name]["sha256"] = hashlib.sha256(raws[name]).hexdigest()
    write("binding", "run-binding.json", binding)
    return paths


def _mutated_lattice(
    tmp_path: Path,
    source: Path,
    *,
    psu: dict[str, Any] | None = None,
    procedure: dict[str, Any] | None = None,
    documents_restamp: str | None = None,
) -> dict[str, Path]:
    """A repinned copy of ``source`` lattice with optional mutations.

    ``psu`` replaces the psu descriptor body; ``procedure`` replaces the
    procedure body; ``documents_restamp`` rewrites every contract document's
    ``contract_version`` (the F1c converse arm's const-only restamp).
    """
    documents = {
        key: json.loads((source / name).read_bytes())
        for key, name in (
            ("procedure", "procedure-voltage-check.json"),
            ("policy", "safety-policy.json"),
            ("bench", "bench.json"),
            ("binding", "run-binding.json"),
            ("commissioning", "commissioning.json"),
        )
    }
    descriptors = {
        device_id: json.loads(
            (source / f"descriptor-sim-{device_id}.json").read_bytes()
        )
        for device_id in ("psu", "controller")
    }
    if psu is not None:
        descriptors["psu"] = psu
    if procedure is not None:
        documents["procedure"] = procedure
    if documents_restamp is not None:
        for document in documents.values():
            if isinstance(document, dict) and "contract_version" in document:
                document["contract_version"] = documents_restamp
    paths = _spool_and_repin(tmp_path, source, documents, descriptors)
    return paths


def _mutated_010(tmp_path: Path, **kwargs: Any) -> dict[str, Path]:
    """The recovered 0.1.0 lattice, mutated and repinned (test copies only)."""
    return _mutated_lattice(tmp_path, LATTICE_010, **kwargs)


def _admit_paths(paths: dict[str, Path], **kwargs: Any) -> AdmittedDocuments:
    return admit_documents(
        procedure_path=paths["procedure"],
        policy_path=paths["policy"],
        bench_path=paths["bench"],
        binding_path=paths["binding"],
        commissioning_path=paths["commissioning"],
        descriptor_paths={
            device_id: paths[device_id] for device_id in ("psu", "controller")
        },
        now_wall=NOW_WALL,
        **kwargs,
    )


def _bench_with_contract_version(tmp_path: Path, version: object) -> Path:
    """The frozen bench with one mutated (or absent) ``contract_version``.

    Routing reads the bench FIRST, so the pin refusal fires before the
    digest lattice is ever consulted — the other four documents can stay
    frozen and pin-coherent.
    """
    bench = json.loads((LATTICE_010 / "bench.json").read_bytes())
    if version is None:
        bench.pop("contract_version", None)
    else:
        bench["contract_version"] = version
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "bench.json"
    path.write_text(json.dumps(bench, indent=2))
    return path


def _admit_with_bench(bench_path: Path, **kwargs: Any) -> AdmittedDocuments:
    p = _010_paths()
    return admit_documents(
        procedure_path=p["procedure"],
        policy_path=p["policy"],
        bench_path=bench_path,
        binding_path=p["binding"],
        commissioning_path=p["commissioning"],
        descriptor_paths={"psu": p["psu"], "controller": p["controller"]},
        now_wall=NOW_WALL,
        **kwargs,
    )


# --- F1a: the recovered lattice admits UNEDITED ---------------------------------


def test_f1a_recovered_lattice_admits_unedited() -> None:
    """F1a: the historical 0.1.0 lattice validates with ZERO byte edits while
    the gateway's active execution version is 0.2.0. RED at the merge base
    (fc55667): the module literal forced the 0.2.0 schemas and the const
    refused (see the commit message for the verbatim refusal). GREEN: the
    lattice admits, the routed version is the bench's own 0.1.0, and both
    descriptors classify served at their otdp 0.2.2 pins."""
    docs = _admit_010()
    assert docs.execution_version == "0.1.0"
    assert docs.bench["contract_version"] == "0.1.0"
    for device_id in ("psu", "controller"):
        pin = docs.pins[device_id]
        assert pin.otdp_version == "0.2.2"
        assert pin.status == "served"
        assert pin.conformance == "conforming"
        assert pin.acknowledgement is None


# --- F1b: the cross-constraint threading discriminator ---------------------------


def test_f1b_acked_below_floor_descriptor_admits_on_pinned_old_only(
    tmp_path: Path,
) -> None:
    """F1b: an ACKNOWLEDGED otdp-0.1.2 descriptor (retained, out-of-range —
    the #219 ack carrier) admits on the 0.1.0-pinned bench — no 0.1.0
    cross-constraint row exists (the honest negative). The SAME descriptor
    on the 0.2.0 sim lattice refuses ``cross_constraint_violation:`` (0.1.2
    outside >=0.2.0,<0.3.0). The first cell discriminates the routing bug
    that threads ``contracts.name`` (0.2.0) instead of the bench's pin: the
    old ambient behaviour would apply the 0.2.0 row here and refuse."""
    psu = json.loads((LATTICE_010 / "descriptor-sim-psu.json").read_bytes())
    psu["otdp_version"] = "0.1.2"

    # Cell 1 — the 0.1.0-pinned bench: the row is absent, the load stands.
    paths = _mutated_010(tmp_path / "pinned-old", psu=psu)
    docs = _admit_paths(paths, operator_acknowledgements={"psu": "0.1.2"})
    assert docs.execution_version == "0.1.0"
    assert docs.pins["psu"].conformance == "non-conforming"
    assert docs.pins["psu"].acknowledgement == {
        "otdp_version": "0.1.2",
        "recorded_at": NOW_WALL,
    }

    # Cell 2 — the same acked descriptor on the active sim lattice: refused.
    # The lattice is a repinned COPY of fixtures/execution/ (the digest
    # lattice must verify cleanly BEFORE the cross-constraint row fires —
    # it runs after every device admitted).
    psu_active = json.loads((FIXTURES / "descriptor-sim-psu.json").read_bytes())
    psu_active["otdp_version"] = "0.1.2"
    active_paths = _mutated_lattice(tmp_path / "active-020", FIXTURES, psu=psu_active)
    with pytest.raises(AdmissionRejected) as raised:
        _admit_paths(active_paths, operator_acknowledgements={"psu": "0.1.2"})
    message = str(raised.value)
    assert "cross_constraint_violation:" in message, message
    assert "otdp@0.1.2" in message, message


# --- F1c: anti-tolerance teeth — the pin's bytes, not a tolerant schema ----------


def _procedure_with_capture_step() -> dict[str, Any]:
    """The recovered procedure plus a 0.2.0-dialect capture step (the closed
    oneOf member 0.2.0 adds — kind const ``capture``, required
    ``timeout_ms``/``format``/``sample_count``/``max_bytes``,
    additionalProperties false; 0.1.0 carries no such branch), contract_version
    stamped "0.1.0" so the ROUTED schema is the one being tested."""
    procedure: dict[str, Any] = json.loads(
        (LATTICE_010 / "procedure-voltage-check.json").read_bytes()
    )
    procedure["steps"].append(
        {
            "id": "grab",
            "kind": "capture",
            "role": "dut",
            "format": "waveform_f64le",
            "sample_count": 8,
            "max_bytes": 4096,
            "timeout_ms": 500,
        }
    )
    return procedure


def test_f1c_capture_step_refuses_under_the_010_pin(tmp_path: Path) -> None:
    """The tooth: a 0.2.0-structure capture step stamped "0.1.0" refuses under
    the 0.1.0 pin — the ROUTED bytes validate, never a tolerant schema. A
    tolerant implementation (serving 0.2.0 bytes for a 0.1.0 pin) would let
    this cell admit."""
    paths = _mutated_010(tmp_path / "teeth", procedure=_procedure_with_capture_step())
    with pytest.raises(AdmissionRejected, match=r"^schema: procedure ") as raised:
        _admit_paths(paths)
    assert "$.steps" in str(raised.value), str(raised.value)


def test_f1c_converse_restamped_lattice_admits_under_020(tmp_path: Path) -> None:
    """The converse tooth: the F1a lattice re-stamped "0.2.0" (the const
    field only — 0.2.0 adds bounds and closed branches, removes nothing)
    validates under the 0.2.0 pin. Selection-by-pin holds in BOTH
    directions."""
    paths = _mutated_010(tmp_path / "converse", documents_restamp="0.2.0")
    docs = _admit_paths(paths)
    assert docs.execution_version == "0.2.0"
    assert docs.bench["contract_version"] == "0.2.0"


# --- F1d: the KILL arm — the in-tree lattice stays byte-unchanged ----------------


def test_f1d_in_tree_sim_lattice_admits_byte_unchanged() -> None:
    """F1d: the in-tree 0.2.0 sim lattice (``fixtures/execution/``) admits
    byte-unchanged under the routing mechanism. KILL fires if ANY in-tree
    lattice needs an edit to admit."""
    docs = admit_documents(
        procedure_path=FIXTURES / "procedure-voltage-check.json",
        policy_path=FIXTURES / "safety-policy.json",
        bench_path=FIXTURES / "bench.json",
        binding_path=FIXTURES / "run-binding.json",
        commissioning_path=FIXTURES / "commissioning.json",
        descriptor_paths={
            "psu": FIXTURES / "descriptor-sim-psu.json",
            "controller": FIXTURES / "descriptor-sim-controller.json",
        },
        now_wall=NOW_WALL,
    )
    assert docs.execution_version == "0.2.0"


# --- F2: the refused classes carry the VR-37 fields ------------------------------


def test_f2a_never_carried_version_refuses_version_unknown(tmp_path: Path) -> None:
    """F2a: ``contract_version: "0.3.0"`` — never carried — refuses
    ``version_unknown:`` with all five VR-37 fields inline."""
    bench_path = _bench_with_contract_version(tmp_path, "0.3.0")
    with pytest.raises(AdmissionRejected) as raised:
        _admit_with_bench(bench_path)
    message = str(raised.value)
    assert message.startswith("version_unknown:"), message
    for field in (
        "standard: execution",
        "pinned: 0.3.0",
        "supported: >=0.1.0,<0.3.0",
        "move-to: 0.2.0",
        "migration guidance pending",
    ):
        assert field in message, f"VR-37 field {field!r} missing: {message}"


def test_f2b_retired_version_refuses_retired_identifier(tmp_path: Path) -> None:
    """F2b: ``contract_version: "1.0.0"`` — used and dead — refuses with the
    DISTINCT ``retired_identifier:`` prefix, the next-minor re-target hint,
    and the five VR-37 fields."""
    bench_path = _bench_with_contract_version(tmp_path, "1.0.0")
    with pytest.raises(AdmissionRejected) as raised:
        _admit_with_bench(bench_path)
    message = str(raised.value)
    assert message.startswith("retired_identifier:"), message
    assert "used and dead" in message, message
    assert "the next minor is 1.1.0" in message, message
    for field in (
        "standard: execution",
        "pinned: 1.0.0",
        "supported: >=0.1.0,<0.3.0",
        "move-to: 0.2.0",
    ):
        assert field in message, f"VR-37 field {field!r} missing: {message}"


def test_f2c_out_of_range_refuses_with_no_ack_path(tmp_path: Path) -> None:
    """F2c (no current non-conforming instance — exercised via a
    copied-standards policy fixture): the execution range narrowed below
    0.1.0 makes the RETAINED 0.1.0 out-of-range; the lattice refuses
    ``standard_nonconforming:`` + VR-37 — and no operator acknowledgement
    input changes that (E2's posture: an ack authorises an otdp-window
    load, never the execution runtime interface)."""
    root = tmp_path / "root"
    root.mkdir()
    shutil.copytree(CORPUS, root / "standards")
    manifest_path = root / "standards" / "standards-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["dependency_policy"]["standards"]["execution"]["range"] = ">=0.2.0,<0.3.0"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    bench_path = _bench_with_contract_version(tmp_path / "f2c", "0.1.0")
    with pytest.raises(AdmissionRejected) as raised:
        _admit_with_bench(
            bench_path,
            contracts=root / "standards" / "execution" / "0.2.0",
            operator_acknowledgements={"psu": "0.1.0", "controller": "0.1.0"},
        )
    message = str(raised.value)
    assert message.startswith("standard_nonconforming:"), message
    for field in (
        "standard: execution",
        "pinned: 0.1.0",
        "supported: >=0.2.0,<0.3.0",
        "move-to: 0.2.0",
    ):
        assert field in message, f"VR-37 field {field!r} missing: {message}"


def test_f2d_malformed_pin_falls_to_the_composition_const(tmp_path: Path) -> None:
    """F2d: a malformed pin (``"0.1"``) or an absent ``contract_version``
    never classifies — the composition posture validates the lattice against
    the threaded 0.2.0 schemas and THEIR OWN const error names it (the
    OTDP no-pin posture, mirrored). The five documents decode in admission
    order, so the PROCEDURE names the disagreement first; the composition
    const is the design's quoted ``was expected '0.2.0'``."""
    bench_path = _bench_with_contract_version(tmp_path / "malformed", "0.1")
    with pytest.raises(AdmissionRejected) as raised:
        _admit_with_bench(bench_path)
    message = str(raised.value)
    assert message.startswith("schema: "), message
    assert "$.contract_version" in message, message
    assert "'0.2.0' was expected" in message, message

    absent_path = _bench_with_contract_version(tmp_path / "absent", None)
    with pytest.raises(AdmissionRejected) as raised_absent:
        _admit_with_bench(absent_path)
    message_absent = str(raised_absent.value)
    assert message_absent.startswith("schema: "), message_absent
    assert "$.contract_version" in message_absent, message_absent
    assert "'0.2.0' was expected" in message_absent, message_absent


# --- Risk 2: the double-read TOCTOU is self-defending ----------------------------


def test_r2_swap_between_routing_and_validating_reads_never_admits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk 2: the routing read and the validating read are two reads of one
    path. A concurrent swap between them must never admit bytes under a
    version they do not declare — the routed schema's own
    ``contract_version`` const refuses the swapped content (the pin lives
    in the validated bytes). The swap here is deterministic: the wrapper
    performs it between the two reads by construction, no threads."""
    import benchweave.control.documents as documents_module

    original = documents_module._decode
    state = {"swapped": False}
    routing_bytes = (LATTICE_010 / "bench.json").read_bytes()
    active_bytes = (FIXTURES / "bench.json").read_bytes()

    def swap_after_routing(
        path: Path, logical: str, *args: Any, **kwargs: Any
    ) -> tuple[dict[str, Any], str]:
        result = original(path, logical, *args, **kwargs)
        if logical == "bench" and not state["swapped"] and len(args) == 0:
            # The routing read (no schema argument): now swap the bytes to a
            # 0.2.0 bench before the validating read happens.
            state["swapped"] = True
            path.write_bytes(active_bytes)
        return result

    monkeypatch.setattr(documents_module, "_decode", swap_after_routing)
    bench_path = tmp_path / "bench.json"
    bench_path.write_bytes(routing_bytes)
    with pytest.raises(AdmissionRejected) as raised:
        _admit_with_bench(bench_path)
    message = str(raised.value)
    assert message.startswith("schema: bench "), message
    assert "$.contract_version" in message, message
    # The refusal names the ROUTED version's const: the routing read
    # selected 0.1.0, the swapped bytes declare 0.2.0, and the 0.1.0
    # schema's own const refuses them — no admission whose routed version
    # differs from the validated document's const can exist.
    assert "'0.1.0' was expected" in message, message
    assert state["swapped"] is True


# --- Risk 4: the classification cache is keyed by standard -----------------------


def test_r4_same_pin_string_under_both_standards_classifies_distinctly() -> None:
    """Risk 4: the corpus-state tokens are standard-independent, so an otdp
    and an execution classification of the SAME pin string must not share a
    cache entry. otdp never carried 1.0.0 (unknown); execution RETIRED
    1.0.0. The otdp call runs first — a key missing ``standard`` would
    return its cached row for the execution call and fail the second
    assert."""
    from benchweave.control.documents import _classify_execution_pin

    otdp_record = classify_descriptor_pin("1.0.0")
    execution_record = _classify_execution_pin("1.0.0")
    assert otdp_record.status == "unknown", otdp_record
    assert execution_record.status == "retired", execution_record
    assert "otdp" in str(otdp_record.note), otdp_record.note
    assert "execution" in str(execution_record.note), execution_record.note


def test_r4_execution_dev_label_without_a_head_is_never_carried() -> None:
    """Totality (design §1.1): a dev-shaped execution label classifies
    against ``declared_dev_head(corpus, "execution")`` — None today — and
    refuses as never-carried, never crashes."""
    from benchweave.control.documents import _classify_execution_pin

    record = _classify_execution_pin("0.3.0-dev")
    assert record.status == "unknown", record
    assert "declared dev head" in str(record.note), record.note


# --- F4: the version-literal ratchet holds ---------------------------------------


def test_f4_version_literal_ratchet_holds() -> None:
    """F4 (standing): ``scripts/standards/count_version_literals.py`` reports
    at most the committed baseline (12 at this slice's base) — the slice
    adds routing, not literals."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "standards" / "count_version_literals.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
