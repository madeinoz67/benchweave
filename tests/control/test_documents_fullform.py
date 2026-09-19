"""Full-form OTDP descriptor admission: projection-gate controls (issue #63).

The descriptor gate validates the ACTIVE vendored OTDP descriptor schema,
applies the S01/S02 semantic mirrors (the SDK checks, pinned equivalent by
the census in ``tests/sdk/test_descriptor_equivalence.py``), validates the
gateway-owned ``x-stg-issued-inputs`` extension, and projects the slim
execution view binding/semantics/coordinator read. Every control runs
through the REAL ``admit_documents`` over the fixture lattice — never the
projection function directly — so the pin lattice is exercised.

The full-form base document is sim_scope's descriptor (the in-tree
full-form exemplar) swapped into the psu slot with the bench pin repointed;
the tree's own conversion to full-form is the next slice.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from _harness import ROOT, Graph, readmit_mutated

from benchweave.control.documents import AdmissionRejected

SIM_SCOPE_DESCRIPTOR = (
    ROOT / "plugins" / "benchweave" / "sim_scope" / "src" / "benchweave_sim_scope"
    / "descriptor.json"
)


def _swap_in_sim_scope(graph: dict[str, Any]) -> None:
    """Replace the psu descriptor with sim_scope's, bench pin repointed."""
    scope = json.loads(SIM_SCOPE_DESCRIPTOR.read_text())
    graph["descriptors"]["psu"] = scope
    device = next(d for d in graph["bench"]["devices"] if d["id"] == "psu")
    device["descriptor"]["id"] = scope["id"]
    device["descriptor"]["version"] = scope["descriptor_version"]


def _mutated_scope(
    mutate: Callable[[dict[str, Any]], None]
) -> Callable[[Graph], None]:
    def mutate_graph(graph: Graph) -> None:
        _swap_in_sim_scope(graph)
        mutate(graph["descriptors"]["psu"])

    return mutate_graph


def test_full_form_descriptor_admits_and_projects(tmp_path: Path) -> None:
    """sim_scope's descriptor — zero byte changes — is execution-admissible."""
    docs = readmit_mutated(tmp_path, _swap_in_sim_scope)
    view = docs.descriptors["psu"]
    assert view["id"] == "dev.benchweave.sim-scope"
    assert view["version"] == "1.0.0"  # projected from descriptor_version
    assert view["profiles"] == ["otdp.oscilloscope/1.0.0"]
    assert view["parameters"][0] == "ch1_probe_ratio"  # names, not objects
    assert all(isinstance(name, str) for name in view["parameters"])
    assert {action["action_id"] for action in view["actions"]} == {
        "otdp.oscilloscope.configure/1.0.0",
        "otdp.oscilloscope.arm/1.0.0",
        "otdp.oscilloscope.trigger/1.0.0",
        "otdp.oscilloscope.fetch/1.0.0",
        "otdp.oscilloscope.abort/1.0.0",
    }
    # No issued-inputs declaration on sim_scope: no action carries `issued`.
    assert all("issued" not in action for action in view["actions"])


def test_issued_map_names_declared_action(tmp_path: Path) -> None:
    """A well-formed issued map projects onto the declared action only."""

    def mutate(descriptor: dict[str, Any]) -> None:
        descriptor["x-stg-issued-inputs"] = {
            "otdp.oscilloscope.configure/1.0.0": ["probe_token"]
        }

    docs = readmit_mutated(tmp_path, _mutated_scope(mutate))
    actions = {a["action_id"]: a for a in docs.descriptors["psu"]["actions"]}
    assert actions["otdp.oscilloscope.configure/1.0.0"]["issued"] == ["probe_token"]
    assert "issued" not in actions["otdp.oscilloscope.arm/1.0.0"]


def test_issued_map_unknown_action_refused(tmp_path: Path) -> None:
    def mutate(descriptor: dict[str, Any]) -> None:
        descriptor["x-stg-issued-inputs"] = {
            "otdp.dc_psu.configure/1.0.0": ["configuration_id"]
        }

    with pytest.raises(
        AdmissionRejected, match=r"schema: descriptor\[psu\] issued_map:"
    ):
        readmit_mutated(tmp_path, _mutated_scope(mutate))


def test_issued_map_fields_must_be_strings(tmp_path: Path) -> None:
    def mutate(descriptor: dict[str, Any]) -> None:
        descriptor["x-stg-issued-inputs"] = {
            "otdp.oscilloscope.configure/1.0.0": [123]
        }

    with pytest.raises(
        AdmissionRejected, match=r"schema: descriptor\[psu\] issued_map:"
    ):
        readmit_mutated(tmp_path, _mutated_scope(mutate))


def test_duplicate_parameter_name_refused(tmp_path: Path) -> None:
    """The S01 mirror: duplicate names are refused, never silently deduped."""

    def mutate(descriptor: dict[str, Any]) -> None:
        descriptor["parameters"].append(copy.deepcopy(descriptor["parameters"][0]))

    with pytest.raises(
        AdmissionRejected, match=r"schema: descriptor\[psu\] S01: parameter names"
    ):
        readmit_mutated(tmp_path, _mutated_scope(mutate))


def test_reversed_range_refused(tmp_path: Path) -> None:
    """The S02 mirror fires on the array-form bounds the 0.2.0 schema admits.

    (The SDK's own S02 branch checks a dict form the schema no longer
    admits; the mirror checks both, and the array branch is the live one.)
    """

    def mutate(descriptor: dict[str, Any]) -> None:
        for parameter in descriptor["parameters"]:
            if parameter["name"] == "ch1_offset_v":
                parameter["range"] = [10.0, -10.0]

    with pytest.raises(
        AdmissionRejected, match=r"schema: descriptor\[psu\] S02: parameter bounds"
    ):
        readmit_mutated(tmp_path, _mutated_scope(mutate))


def test_stale_otdp_version_refused(tmp_path: Path) -> None:
    """The schema's otdp_version const enforces corpus alignment (dps150's
    actual condition): a 0.1.0 declaration is a schema refusal, not a
    gateway constant."""

    def mutate(descriptor: dict[str, Any]) -> None:
        descriptor["otdp_version"] = "0.1.0"

    with pytest.raises(
        AdmissionRejected, match=r"schema: descriptor\[psu\] \$.otdp_version"
    ):
        readmit_mutated(tmp_path, _mutated_scope(mutate))
