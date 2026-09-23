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


# ---------------------------------------------------------------------------
# 0.2.1 extension (gateway #147, PR-B content folded into PR A by the
# design record's build-time amendment): the SDK checker over the corpus
# example set and the shared provider lattice. The agreement property lives
# here because only the parent sees both sides — the corpus bytes from this
# tree, the checker from the pinned submodule.
# ---------------------------------------------------------------------------

EXAMPLES = ROOT / "standards" / "otdp" / "0.2.2" / "examples"


def _example_descriptor_names() -> list[str]:
    """Every descriptor-shaped active-version example (carries ``otdp_version``).

    Vectors files and the provider contract itself are filtered by content,
    not by name, so a new example kind joins the sweep without an edit here.
    """
    names = [
        path.name
        for path in sorted(EXAMPLES.glob("*.json"))
        if "otdp_version" in json.loads(path.read_text())
    ]
    assert names, "the active example set has no descriptors"
    return names


def _sdk_check(path: Path) -> tuple[int, str]:
    """Run the submodule's check CLI; (exit_code, first output line)."""
    from benchweave_sdk.cli import cli as sdk_cli
    from click.testing import CliRunner

    result = CliRunner().invoke(sdk_cli, ["check", str(path)])
    first = result.output.splitlines()[0] if result.output.strip() else ""
    return int(result.exit_code), first


@pytest.mark.parametrize("name", _example_descriptor_names())
def test_sdk_checker_accepts_the_021_example_set(name: str) -> None:
    """Every descriptor-shaped corpus example checks clean, in place.

    The provider example's pin resolves descriptor-relative to its sibling
    contract; the class examples' pins resolve beside the version dir. A
    corpus example the pinned SDK refuses is corpus/check drift caught at
    the parent, which is the point of housing this sweep here.
    """
    exit_code, output = _sdk_check(EXAMPLES / name)
    assert exit_code == 0, f"{name}: {output}"


def test_example_sweep_bites_on_a_mismatched_pin(tmp_path: Path) -> None:
    """The sweep has teeth: a corrupted example pin is refused, not waved through.

    The control arm the sweep needs so green means something: the corpus
    reference pair copied verbatim checks clean, the same pair with the
    provider digest pointed at the wrong bytes refuses with the pin prefix.
    """
    package = tmp_path / "mismatch-control"
    package.mkdir()
    (package / "reference-provider.json").write_bytes(
        (EXAMPLES / "reference-provider.json").read_bytes()
    )
    descriptor = json.loads((EXAMPLES / "reference-hid-meter.json").read_text())
    (package / "descriptor.json").write_text(json.dumps(descriptor, indent=2))
    exit_code, output = _sdk_check(package / "descriptor.json")
    assert exit_code == 0, output

    sabotaged = json.loads(json.dumps(descriptor))
    sabotaged["transport"]["provider"]["sha256"] = "b" * 64
    (package / "descriptor.json").write_text(json.dumps(sabotaged, indent=2))
    exit_code, output = _sdk_check(package / "descriptor.json")
    assert exit_code == 1
    assert "provider_contract_hash_mismatch:" in output


# --- the shared provider lattice: 4 valid variants + 8 single faults ---


def _base_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    """The corpus reference descriptor/contract pair as writable copies."""
    descriptor = json.loads((EXAMPLES / "reference-hid-meter.json").read_text())
    contract = json.loads((EXAMPLES / "reference-provider.json").read_text())
    return descriptor, contract


def _minimal_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    descriptor, contract = _base_pair()
    descriptor["capabilities"] = ["identify"]
    descriptor["operations"] = {"identify": descriptor["operations"]["identify"]}
    descriptor["parameters"] = []
    return descriptor, contract


def _write_package(
    tmp_path: Path,
    name: str,
    descriptor: dict[str, Any],
    contract: dict[str, Any] | None,
    *,
    recompute_digest: bool = True,
) -> Path:
    """Write ``<tmp>/<name>/`` holding the descriptor and its pinned contract.

    Mirrors the SDK lane's builder: the pin digest is recomputed from the
    bytes actually written unless the fixture deliberately faults it.
    """
    package = tmp_path / name
    package.mkdir(parents=True)
    if contract is not None:
        raw = (json.dumps(contract, indent=2) + "\n").encode()
        (package / descriptor["transport"]["provider"]["path"]).write_bytes(raw)
        if recompute_digest:
            descriptor["transport"]["provider"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (package / "descriptor.json").write_text(json.dumps(descriptor, indent=2) + "\n")
    return package / "descriptor.json"


def _valid_minimal(tmp_path: Path) -> Path:
    descriptor, contract = _minimal_pair()
    return _write_package(tmp_path, "minimal", descriptor, contract)


def _valid_with_class_profiles(tmp_path: Path) -> Path:
    descriptor, contract = _minimal_pair()
    catalog = json.loads(
        (ROOT / "standards" / "otdp" / "0.2.2" / "device-profile-catalog.json").read_text()
    )
    profile_id = sorted(profile["id"] for profile in catalog["profiles"])[0]
    descriptor["required_features"] += [
        "otdp.profile_actions/0.1.0",
        "otdp.measurement/0.1.0",
        profile_id,
    ]
    return _write_package(tmp_path, "class-profiles", descriptor, contract)


def _valid_with_x_settings(tmp_path: Path) -> Path:
    descriptor, contract = _minimal_pair()
    descriptor["transport"]["settings"]["x-report-timeout"] = 30
    return _write_package(tmp_path, "x-settings", descriptor, contract)


def _valid_corpus_reference(tmp_path: Path) -> Path:
    # The corpus example's pin covers the corpus bytes; writing them verbatim
    # is the only way the example's own digest verifies.
    package = tmp_path / "corpus-reference"
    package.mkdir()
    (package / "reference-provider.json").write_bytes(
        (EXAMPLES / "reference-provider.json").read_bytes()
    )
    (package / "descriptor.json").write_bytes(
        (EXAMPLES / "reference-hid-meter.json").read_bytes()
    )
    return package / "descriptor.json"


VALID_LATTICE: dict[str, Callable[[Path], Path]] = {
    "minimal_provider": _valid_minimal,
    "provider_with_class_profile_features": _valid_with_class_profiles,
    "provider_with_x_settings": _valid_with_x_settings,
    "corpus_reference_descriptor": _valid_corpus_reference,
}

Fault = tuple[dict[str, Any], dict[str, Any] | None, str]


def _fault_feature_not_required() -> Fault:
    descriptor, contract = _minimal_pair()
    feature = descriptor["transport"]["provider"]["feature_id"]
    descriptor["required_features"].remove(feature)
    return descriptor, contract, "provider_feature_missing:"


def _fault_orphan_transport_feature() -> Fault:
    descriptor, _ = _minimal_pair()
    del descriptor["transport"]["provider"]
    return descriptor, None, "provider_transport_undeclared:"


def _fault_unknown_otdp_feature() -> Fault:
    descriptor, contract = _minimal_pair()
    descriptor["required_features"].append("otdp.core/9.9.9")
    return descriptor, contract, "unknown_otdp_feature:"


def _fault_provider_on_serial() -> Fault:
    # The transport arms are closed objects, so the oneOf refuses a provider
    # on serial: the schema owns this fault (a "Contract validation failed"
    # refusal, not a census prefix).
    descriptor, contract = _minimal_pair()
    descriptor["transport"] = {
        "type": "serial",
        "connection_key": "power_meter",
        "settings": {
            "baud": 115200,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
            "rtscts": False,
            "max_frame_bytes": 128,
        },
        "provider": descriptor["transport"]["provider"],
    }
    return descriptor, contract, "Contract validation failed"


def _fault_without_adapter_mode() -> Fault:
    # Custom transport requires adapter mode (specification section 6.4); the
    # census's placement row names it even on the schema-refused document.
    descriptor, contract = _minimal_pair()
    descriptor["integration"] = {"mode": "declarative"}
    descriptor["required_features"].remove("otdp.adapter/0.1.0")
    return descriptor, contract, "provider_transport_undeclared:"


def _fault_escaping_pin_path() -> Fault:
    descriptor, _ = _minimal_pair()
    descriptor["transport"]["provider"]["path"] = "../outside-provider.json"
    return descriptor, None, "provider_contract_missing:"


def _fault_wrong_pin_digest() -> Fault:
    descriptor, contract = _minimal_pair()
    descriptor["transport"]["provider"]["sha256"] = "a" * 64
    return descriptor, contract, "provider_contract_hash_mismatch:"


def _fault_provider_extra_property() -> Fault:
    descriptor, contract = _minimal_pair()
    descriptor["transport"]["provider"]["vendor_extra"] = "not sanctioned"
    return descriptor, contract, "Contract validation failed"


FAULT_LATTICE: dict[str, Callable[[], Fault]] = {
    "feature_id_absent_from_required_features": _fault_feature_not_required,
    "orphan_otdp_transport_feature": _fault_orphan_transport_feature,
    "unknown_otdp_id": _fault_unknown_otdp_feature,
    "provider_on_non_custom_transport": _fault_provider_on_serial,
    "provider_without_adapter_mode": _fault_without_adapter_mode,
    "escaping_pin_path": _fault_escaping_pin_path,
    "wrong_pin_sha256": _fault_wrong_pin_digest,
    "provider_object_with_additional_properties": _fault_provider_extra_property,
}


@pytest.mark.parametrize("build", list(VALID_LATTICE.values()), ids=list(VALID_LATTICE))
def test_provider_lattice_valid_slots_check_clean(
    tmp_path: Path, build: Callable[[Path], Path]
) -> None:
    """Metric 1, valid half: the four valid variants check clean (4/4)."""
    exit_code, output = _sdk_check(build(tmp_path))
    assert exit_code == 0, output


@pytest.mark.parametrize("name", list(FAULT_LATTICE), ids=list(FAULT_LATTICE))
def test_provider_lattice_fault_slots_refuse_with_named_prefixes(
    tmp_path: Path, name: str
) -> None:
    """Metric 1, fault half: 8/8 refuse, five with census prefixes, three at
    the schema surface ("Contract validation failed" — the honest mapping the
    record's Metric-1 amendment pins)."""
    descriptor, contract, expected = FAULT_LATTICE[name]()
    slot = _write_package(tmp_path, name, descriptor, contract, recompute_digest=False)
    exit_code, output = _sdk_check(slot)
    assert exit_code == 1, f"{name}: unexpectedly clean"
    assert expected in output, f"{name}: expected {expected!r}, got {output!r}"


def test_bomd_provider_document_is_digest_governed(tmp_path: Path) -> None:
    """EN-3 disposition (RedTeam wave, routed here): a BOM'd or UTF-16
    provider document is ADMITTED when the pin covers its bytes, and refused
    with the pin prefix when it does not — on both encodings alike.

    This mirrors the corpus statement, not a wider claim: the pin is over
    the raw bytes read from disk (transport-providers.md section 2 —
    "digest-pinned"; the design record's PKG rows — "hashed from disk,
    never fetched"), so the digest, never the encoding, is the refusal
    surface. The gateway's increment-3 admission must decide its own
    posture against this KNOWINGLY, the same disclosed-divergence posture
    as the symlink question.
    """
    descriptor, contract = _minimal_pair()
    plain = (json.dumps(contract, indent=2) + "\n").encode()
    variants = {
        "utf8-bom": b"\xef\xbb\xbf" + plain,
        "utf16": plain.decode().encode("utf-16"),
    }
    for label, raw in variants.items():
        package = tmp_path / label
        package.mkdir()
        (package / "reference-provider.json").write_bytes(raw)
        pinned = json.loads(json.dumps(descriptor))
        pinned["transport"]["provider"]["sha256"] = hashlib.sha256(raw).hexdigest()
        (package / "descriptor.json").write_text(json.dumps(pinned, indent=2))
        exit_code, output = _sdk_check(package / "descriptor.json")
        assert exit_code == 0, f"{label}, pinned bytes: {output}"

        mismatched = json.loads(json.dumps(descriptor))
        mismatched["transport"]["provider"]["sha256"] = hashlib.sha256(plain).hexdigest()
        (package / "descriptor.json").write_text(json.dumps(mismatched, indent=2))
        exit_code, output = _sdk_check(package / "descriptor.json")
        assert exit_code == 1, f"{label}, mismatched pin: unexpectedly clean"
        assert "provider_contract_hash_mismatch:" in output, output
