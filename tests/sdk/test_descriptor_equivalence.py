"""Gateway admission vs ``benchweave-sdk check`` over the in-tree corpus.

CON-10's equivalence pin: over {sim_psu, sim_controller, sim_scope, dps150}
x {clean, id-pattern violation, profiles scalar, actions-as-list, duplicate
parameter name, reversed range, issued-map unknown action} — 28 cells;
dps150's core-only shape (no actions/profiles keys) is the interesting
boundary: the actions-as-list and issued-map mutations add the minimal
object/map to it.

- a descriptor the SDK check refuses is never gateway-admissible
  (check-clean is a necessary condition for admission), and
- outside the two sanctioned gateway-stricter cells below, the gates agree
  in both directions.

The sanctioned asymmetric cell, gateway-strictly-stricter, pinned as
such (a symmetric-everywhere census would be unbuildable without
editing standards bytes — the extension contract is what makes check
ignore x- keys):

- issued-map unknown action: x- keys are ignorable OTDP metadata by
  contract, so check stays clean while the gateway refuses
  (``issued_map:``) — the gateway owns the extension's semantics.

Reversed range is both-refuse since benchweave-sdk v0.1.0: S02 was dead
there (it checked a dict form the 0.2.0 schema no longer admits) until
the repair taught it the array form the schema does admit, agreeing with
the gateway mirror.

The gateway leg runs through the REAL ``admit_documents`` over the
fixture lattice (never the projection function directly), so the pin
lattice is exercised; the SDK leg runs the check CLI in-process (the
syspath-prepend precedent, ``test_presentation_cli.py``).
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from benchweave.control.documents import AdmissionRejected, AdmittedDocuments, admit_documents

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "execution"

CORPUS: dict[str, Path] = {
    "sim_psu": ROOT / "plugins/benchweave/sim_psu/src/benchweave_sim_psu/descriptor.json",
    "sim_controller": ROOT
    / "plugins/benchweave/sim_controller/src/benchweave_sim_controller/descriptor.json",
    "sim_scope": ROOT / "plugins/benchweave/sim_scope/src/benchweave_sim_scope/descriptor.json",
    "dps150": ROOT
    / "plugins/fnirsi/dps150/src/benchweave_fnirsi_dps150/descriptor.json",
}
#: Which bench slot each corpus descriptor is swapped into (pin repointed).
SLOT: dict[str, str] = {
    "sim_psu": "psu",
    "sim_controller": "controller",
    "sim_scope": "psu",
    "dps150": "controller",  # core-only, like sim_controller
}

Mutation = Callable[[dict[str, Any]], None]


def _reverse_primary_range(descriptor: dict[str, Any]) -> None:
    """Reverse one parameter's bounds: the first that carries a range, else
    the first numeric parameter with a reversed range attached (dps150's
    read-only parameters carry none)."""
    for parameter in descriptor["parameters"]:
        if "range" in parameter:
            parameter["range"] = [parameter["range"][1], parameter["range"][0]]
            return
    for parameter in descriptor["parameters"]:
        if parameter["type"] in ("float", "int"):
            parameter["range"] = [1.0, 0.0]
            return


#: name -> (expectation, mutator). Expectation is one of both-clean,
#: both-refuse, gateway-stricter.
MUTATIONS: dict[str, tuple[str, Mutation]] = {
    "clean": ("both-clean", lambda d: None),
    "id-pattern": (
        "both-refuse",
        lambda d: d.__setitem__("id", "descriptor-sim-psu"),  # no dot segment
    ),
    "profiles-scalar": (
        "both-refuse",
        lambda d: d.__setitem__("profiles", "otdp.dc_psu/1.0.0"),
    ),
    "actions-as-list": (
        "both-refuse",
        lambda d: d.__setitem__("actions", [{"action_id": "otdp.dc_psu.configure/1.0.0"}]),
    ),
    # S01 layering (measured 2026-09-20, issue #85): duplicate names are
    # the mirror's live branch — the 0.2.0 schema does not enforce
    # parameter-name uniqueness, so this shape passes the schema and is
    # refused by the gateway's S01 mirror proper. The caps/ops-set half of
    # S01 is schema-shadowed on 0.2.0: the schema's `not` conditional at
    # $.operations refuses an operation policy whose capability is absent
    # BEFORE the mirror runs, so that shape census-pins as a schema
    # refusal, never as an S01 mirror refusal
    # (test_s01_layering_on_020_documents pins both directions).
    "duplicate-parameter-name": (
        "both-refuse",
        lambda d: d["parameters"].append(copy.deepcopy(d["parameters"][0])),
    ),
    "reversed-range": ("both-refuse", _reverse_primary_range),
    "issued-map-unknown-action": (
        "gateway-stricter",
        lambda d: d.__setitem__(
            "x-stg-issued-inputs", {"no.such.action/1.0.0": ["configuration_id"]}
        ),
    ),
}


@pytest.fixture(autouse=True)
def sdk_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "packages/sdk/src"))


def _admit(
    tmp_path: Path, slot: str, descriptor: dict[str, Any]
) -> tuple[bool, str]:
    """Run one descriptor through the REAL admit_documents, pins repointed."""
    filenames = {
        "procedure": "procedure-voltage-check.json",
        "policy": "safety-policy.json",
        "bench": "bench.json",
        "binding": "run-binding.json",
        "commissioning": "commissioning.json",
    }
    graph = {
        name: json.loads((FIXTURES / filename).read_text())
        for name, filename in filenames.items()
    }
    descriptors = {
        device_id: json.loads(path.read_text())
        for device_id, path in (
            ("psu", FIXTURES / "descriptor-sim-psu.json"),
            ("controller", FIXTURES / "descriptor-sim-controller.json"),
        )
    }
    descriptors[slot] = copy.deepcopy(descriptor)

    descriptor_paths: dict[str, Path] = {}
    for device_id, doc in descriptors.items():
        path = tmp_path / f"descriptor-{device_id}.json"
        path.write_text(json.dumps(doc, indent=2))
        descriptor_paths[device_id] = path
    policy_path = tmp_path / "safety-policy.json"
    policy_path.write_text(json.dumps(graph["policy"], indent=2))
    lock_path = tmp_path / "package-lock.json"
    lock_path.write_bytes((FIXTURES / "package-lock.json").read_bytes())

    bench = graph["bench"]
    for device in bench["devices"]:
        raw = descriptor_paths[str(device["id"])].read_bytes()
        doc = json.loads(raw)
        device["descriptor"]["id"] = doc["id"]
        device["descriptor"]["version"] = doc.get(
            "descriptor_version", doc.get("version")
        )
        device["descriptor"]["sha256"] = hashlib.sha256(raw).hexdigest()
    bench["policy"]["sha256"] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    bench["package_lock"]["sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    bench_path = tmp_path / "bench.json"
    bench_path.write_text(json.dumps(bench, indent=2))

    procedure_path = tmp_path / "procedure.json"
    procedure_path.write_text(json.dumps(graph["procedure"], indent=2))
    commissioning = graph["commissioning"]
    for name, path in (
        ("bench", bench_path),
        ("policy", policy_path),
        ("package_lock", lock_path),
    ):
        commissioning[name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for reference in commissioning["procedure_refs"]:
        reference["sha256"] = hashlib.sha256(procedure_path.read_bytes()).hexdigest()
    commissioning_path = tmp_path / "commissioning.json"
    commissioning_path.write_text(json.dumps(commissioning, indent=2))

    binding = graph["binding"]
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

    try:
        admit_documents(
            procedure_path=procedure_path,
            policy_path=policy_path,
            bench_path=bench_path,
            binding_path=binding_path,
            commissioning_path=commissioning_path,
            descriptor_paths=descriptor_paths,
        )
    except AdmissionRejected as exc:
        return False, str(exc)
    return True, ""


def _admitted_view(tmp_path: Path, slot: str, descriptor: dict[str, Any]) -> AdmittedDocuments:
    """Admit and return the documents; for the clean-cell shape assertion."""
    admitted, message = _admit(tmp_path, slot, descriptor)
    assert admitted, message
    docs = admit_documents(
        procedure_path=tmp_path / "procedure.json",
        policy_path=tmp_path / "safety-policy.json",
        bench_path=tmp_path / "bench.json",
        binding_path=tmp_path / "run-binding.json",
        commissioning_path=tmp_path / "commissioning.json",
        descriptor_paths={
            "psu": tmp_path / "descriptor-psu.json",
            "controller": tmp_path / "descriptor-controller.json",
        },
    )
    return docs



@pytest.mark.parametrize("corpus", sorted(CORPUS))
@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_gateway_admission_matches_sdk_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corpus: str,
    mutation: str,
) -> None:
    expectation, mutate = MUTATIONS[mutation]
    descriptor = json.loads(CORPUS[corpus].read_text())
    mutate(descriptor)

    gateway_admitted, gateway_message = _admit(tmp_path, SLOT[corpus], descriptor)

    check_path = tmp_path / f"check-{corpus}-{mutation}.json"
    check_path.write_text(json.dumps(descriptor, indent=2))
    cli = importlib.import_module("benchweave_sdk.cli")
    exit_code: int = cli.main(["check", str(check_path)])
    sdk_clean = exit_code == 0

    # Necessary condition, every cell: a check-refused descriptor is never
    # gateway-admissible.
    assert not (gateway_admitted and not sdk_clean), (
        f"{corpus}/{mutation}: gateway admitted a check-dirty descriptor "
        f"(sdk exit {exit_code})"
    )
    if expectation == "both-clean":
        assert sdk_clean and gateway_admitted, (
            f"{corpus}/{mutation}: expected both-clean, got sdk_clean={sdk_clean} "
            f"gateway={gateway_admitted} ({gateway_message})"
        )
    elif expectation == "both-refuse":
        assert not sdk_clean and not gateway_admitted, (
            f"{corpus}/{mutation}: expected both-refuse, got sdk_clean={sdk_clean} "
            f"gateway={gateway_admitted} ({gateway_message})"
        )
    else:  # gateway-stricter: sdk clean by contract/mechanism, gateway refuses
        assert sdk_clean, f"{corpus}/{mutation}: sdk unexpectedly dirty"
        assert not gateway_admitted, f"{corpus}/{mutation}: gateway unexpectedly admitted"
        assert "issued_map:" in gateway_message or "S02:" in gateway_message, (
            f"{corpus}/{mutation}: refusal is not the sanctioned stricter layer: "
            f"{gateway_message}"
        )


def test_s01_layering_on_020_documents(tmp_path: Path) -> None:
    """Which gateway layer each S01 half fires on (issue #85 census note).

    The caps/ops-set half of the S01 mirror is schema-shadowed on 0.2.0:
    the vendored schema's ``not`` conditional at ``$.operations`` refuses
    an operation policy whose capability is absent before the mirror runs.
    Duplicate parameter names pass the schema (it does not enforce name
    uniqueness — the census cell above) and are refused by the S01 mirror
    proper. A test that means to exercise the mirror itself mutates a
    duplicate name, never a caps/ops removal.
    """
    base = json.loads(CORPUS["sim_psu"].read_text())

    caps = copy.deepcopy(base)
    caps["capabilities"].remove("invoke")
    admitted, message = _admit(tmp_path, "psu", caps)
    assert not admitted and message.startswith("schema: descriptor[psu] $"), (
        f"caps/ops removal must be refused by the schema layer: {message}"
    )

    duplicate = copy.deepcopy(base)
    duplicate["parameters"].append(copy.deepcopy(duplicate["parameters"][0]))
    admitted, message = _admit(tmp_path, "psu", duplicate)
    assert not admitted and "S01: parameter names must be unique" in message, (
        f"duplicate names must reach the S01 mirror: {message}"
    )


def test_clean_cells_project_the_execution_view(tmp_path: Path) -> None:
    """The three clean corpus descriptors admit and project the consumer view."""
    for corpus, slot in SLOT.items():
        descriptor = json.loads(CORPUS[corpus].read_text())
        docs = _admitted_view(tmp_path, slot, descriptor)
        view = docs.descriptors[slot]
        assert view["id"] == descriptor["id"]
        assert view["version"] == descriptor["descriptor_version"]
        assert view["profiles"] == descriptor.get("profiles", [])
        assert view["parameters"] == [p["name"] for p in descriptor["parameters"]]
        assert {a["action_id"] for a in view["actions"]} == set(
            descriptor.get("actions", {})
        )
