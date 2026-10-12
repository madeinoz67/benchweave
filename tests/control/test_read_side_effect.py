"""The read side-effect surface at admission and projection (issue #445).

The CTL-7 mirror family's read row (``state_changing_read:``) and the
CON-10 projection gain (``read_side_effect`` / ``state_changing_reads``),
exercised through the execution fixture lattice the way
``test_capture_admission.py`` exercises the capture family:

- the refusal arm — a read step bound to a device whose read verb declares
  ``side_effect: state_change`` is refused with the typed prefix, whatever
  parameter it reads (the design's F2: the VERB flag is the trigger —
  faithful to the execution contract's exclusion of state-changing core
  reads from procedures);
- the over-classification arm — a verb flipped to ``state_change`` with no
  parameter declaring it is refused equally (the disclosed, intended cost);
- the no-over-blocking control — the committed ``none``-verb fixture set
  still admits unchanged (the ``model`` read step on the controller);
- the projection arms — the admitted view carries the verb flag and the
  sorted per-parameter set, and omits both keys for a device with no read
  verb (absent means ``none``).

The declaring mutations pin the controller to OTDP 0.2.3 — under 0.2.2's
closed ``read_policy`` the field is an unknown keyword, which is the
design's dead-shape proof premise (nothing 0.2.2-admissible is affected).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from _harness import Graph, readmit_mutated

from benchweave.control.documents import AdmissionRejected


def _pin_023(descriptor: dict[str, Any]) -> None:
    descriptor["otdp_version"] = "0.2.3"


def _declare_state_changing_reads(controller: dict[str, Any]) -> None:
    """The amended-plugin shape: two mutating reads, one clean verb."""
    controller["operations"]["read"]["side_effect"] = "state_change"
    for parameter in controller["parameters"]:
        if parameter["name"] in ("uptime_s", "identity_model"):
            parameter["read_policy"]["side_effect"] = "state_change"


def _strip_read_steps(graph: Graph) -> None:
    graph["procedure"]["steps"] = [
        step for step in graph["procedure"]["steps"] if step.get("kind") != "read"
    ]


def test_state_changing_read_refused(tmp_path: Path) -> None:
    """A read step on a state-changing-verb device is refused (CTL-7 row)."""

    def mutate(graph: Graph) -> None:
        controller = graph["descriptors"]["controller"]
        _pin_023(controller)
        _declare_state_changing_reads(controller)

    with pytest.raises(AdmissionRejected, match="state_changing_read:"):
        readmit_mutated(tmp_path, mutate)


def test_overclassified_verb_refused_equally(tmp_path: Path) -> None:
    """The clean parameter's read is refused too when only the verb
    over-classifies — the disclosed cost of the one-directional maximum
    (the design's risk 1; the interim remedy is a local invoke action)."""

    def mutate(graph: Graph) -> None:
        controller = graph["descriptors"]["controller"]
        _pin_023(controller)
        controller["operations"]["read"]["side_effect"] = "state_change"
        # No parameter declares side_effect: the verb alone must refuse.

    with pytest.raises(AdmissionRejected, match="state_changing_read:"):
        readmit_mutated(tmp_path, mutate)


def test_none_verb_read_step_still_admits(tmp_path: Path) -> None:
    """The no-over-blocking control: the committed fixture set (read verb
    ``none``, the ``model`` read step on the controller) admits unchanged."""

    docs = readmit_mutated(tmp_path, lambda graph: None)
    assert "controller" in docs.descriptors


def test_projection_carries_read_side_effect_facts(tmp_path: Path) -> None:
    """The CON-10 view carries the verb flag and the sorted declaring set."""

    def mutate(graph: Graph) -> None:
        controller = graph["descriptors"]["controller"]
        _pin_023(controller)
        _declare_state_changing_reads(controller)
        _strip_read_steps(graph)

    docs = readmit_mutated(tmp_path, mutate)
    view = docs.descriptors["controller"]
    assert view["read_side_effect"] == "state_change"
    assert view["state_changing_reads"] == ["identity_model", "uptime_s"]


def test_projection_defaults_for_none_verb(tmp_path: Path) -> None:
    """A ``none`` verb projects the flag with an empty set (always a list)."""

    def mutate(graph: Graph) -> None:
        controller = graph["descriptors"]["controller"]
        _pin_023(controller)
        _strip_read_steps(graph)

    docs = readmit_mutated(tmp_path, mutate)
    view = docs.descriptors["controller"]
    assert view["read_side_effect"] == "none"
    assert view["state_changing_reads"] == []


def test_projection_omits_keys_without_read_verb(tmp_path: Path) -> None:
    """No read capability ⇒ no read keys in the view (absent means none)."""

    def mutate(graph: Graph) -> None:
        controller = graph["descriptors"]["controller"]
        _pin_023(controller)
        controller["capabilities"].remove("read")
        controller["operations"].pop("read")
        _strip_read_steps(graph)

    docs = readmit_mutated(tmp_path, mutate)
    view = docs.descriptors["controller"]
    assert "read_side_effect" not in view
    assert "state_changing_reads" not in view


def test_refusal_message_names_step_device_and_set(tmp_path: Path) -> None:
    """The refusal is greppable: step id, device, and the declaring set."""

    def mutate(graph: Graph) -> None:
        controller = graph["descriptors"]["controller"]
        _pin_023(controller)
        _declare_state_changing_reads(controller)

    with pytest.raises(AdmissionRejected) as record:
        readmit_mutated(tmp_path, mutate)
    message = str(record.value)
    assert message.startswith("state_changing_read: step 'model'")
    assert "'controller'" in message
    assert "invoke action" in message
    assert "identity_model" in message and "uptime_s" in message
