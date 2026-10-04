"""The G3b runs control surface (issue #304, design record §2.4/§2.5,
acceptance arms E–J) — the run half of GW-10's eight.

Pure-function arms first (this file's opening block — the trip
predicate's matrix and the energy classifier's, with the record's
disclosed boundaries pinned), then the route arms over a REAL composed
gateway with a MUTABLE injected clock, each behavior proven RED before
its implementation (the verbatim failure text rides the commit message
and the run report).
"""

from __future__ import annotations

import json
from typing import Any

from g3b_lattice import author_g3b_lattice

from benchweave.interfaces.ui_control import energy_sourcing, trip_active

_FIXTURES_PROCEDURE = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "fixtures"
    / "execution"
    / "procedure-voltage-check.json"
)


def _event(kind: str, sequence: int) -> dict[str, Any]:
    return {"kind": kind, "sequence": sequence, "at": "2026-10-03T00:00:00Z"}


# --- §2.5: the trip predicate (GW-43/54's wire-honest core) -----------------------


def test_no_trip_lifecycle_events_composes_no_protection() -> None:
    """Boundary (c): retention dropped (or never carried) any
    trip-lifecycle row — no verdict, never protection-active."""
    assert trip_active([]) is False
    assert trip_active([_event("run_changed", 1), _event("lease_changed", 2)]) is False


def test_newest_trip_lifecycle_event_decides() -> None:
    """Newest → oldest by sequence: the newest trip-lifecycle row's kind
    decides — a ``trip`` is protection-active; a ``bench_changed`` (the
    only wire shadow an applied trip_reset has) clears it."""
    assert trip_active([_event("trip", 5)]) is True
    assert trip_active([_event("trip", 5), _event("bench_changed", 7)]) is False
    assert trip_active([_event("bench_changed", 3), _event("trip", 5)]) is True
    assert trip_active([_event("trip", 5), _event("bench_changed", 7), _event("trip", 9)]) is True


def test_trip_predicate_is_order_agnostic() -> None:
    """The verdict keys on sequence, never list order — an adapter may
    hand the rows in either direction."""
    rows = [_event("run_changed", 1), _event("trip", 5), _event("bench_changed", 7)]
    assert trip_active(rows) is False
    assert trip_active(list(reversed(rows))) is False
    rows = [_event("bench_changed", 7), _event("run_changed", 1), _event("trip", 9)]
    assert trip_active(rows) is True
    assert trip_active(list(reversed(rows))) is True


def test_boundary_b_admin_change_after_a_trip_clears() -> None:
    """Disclosed boundary (b): an admin configuration activation after a
    trip also emits ``bench_changed`` and therefore ALSO clears the
    marker — the closed event def has no channel for the change kind
    (the record §2.5b err-clear boundary, pinned as disclosed)."""
    rows = [_event("trip", 5), _event("bench_changed", 7)]
    assert trip_active(rows) is False


# --- GW-52: the energy classification ---------------------------------------------


def _variant(tmp_path: Any, name: str, **kwargs: Any) -> dict[str, Any]:
    directory, _binding_sha = author_g3b_lattice(tmp_path, name=name, **kwargs)
    procedure_path = directory / "procedure-voltage-check.json"
    parsed: dict[str, Any] = json.loads(procedure_path.read_text())
    return parsed


def test_enable_true_is_energy_sourcing(tmp_path: Any) -> None:
    """R-ENERGISE-1's enabling clause: any ``invoke`` step whose input
    carries ``enabled: true`` makes the procedure energy-sourcing."""
    assert energy_sourcing(json.loads(_FIXTURES_PROCEDURE.read_text())) is True
    assert energy_sourcing(_variant(tmp_path, "energise", enabled=True)) is True


def test_explicit_false_is_de_energising(tmp_path: Any) -> None:
    """An explicit ``enabled: false`` is the de-energising class (the
    record's own shape: manual + explicit false)."""
    assert energy_sourcing(_variant(tmp_path, "deenergise", enabled=False)) is False


def test_absent_enable_field_is_de_energising(tmp_path: Any) -> None:
    """A procedure with no enable-true step (including the enable step
    with the field absent) is the de-energising class."""
    assert energy_sourcing(_variant(tmp_path, "absent", enabled="absent")) is False


def test_nested_enable_steps_are_classified(tmp_path: Any) -> None:
    """The scan recurses into ``if.then`` / ``repeat.steps`` bodies — an
    author cannot hide an enable from the classifier by nesting it."""
    base = json.loads(_FIXTURES_PROCEDURE.read_text())
    nested = {
        "id": "wrap",
        "kind": "if",
        "predicate": {"sample": "voltage", "minimum": 0.0, "maximum": 1.0},
        "then": [step for step in base["steps"] if step.get("id") == "enable"],
        "else": [],
    }
    procedure = dict(base)
    procedure["steps"] = [nested]
    assert energy_sourcing(procedure) is True
    looped = dict(base)
    looped["steps"] = [
        {
            "id": "loop",
            "kind": "repeat",
            "count": 1,
            "steps": [step for step in base["steps"] if step.get("id") == "enable"],
        }
    ]
    assert energy_sourcing(looped) is True


def test_the_setpoint_clause_is_not_derived() -> None:
    """Disclosed boundary (G3-D2): a WRITE step raising a setpoint of a
    currently-energised output is NOT classified — the clause needs live
    device state the documents do not carry, and the classifier errs
    only by rule change, never silently."""
    write_only = {
        "id": "p",
        "version": "0.1.0",
        "mode": "manual",
        "steps": [
            {
                "id": "raise",
                "kind": "write",
                "role": "supply",
                "parameter": "voltage_setpoint_v",
                "value": 5.5,
                "timeout_ms": 500,
            }
        ],
    }
    assert energy_sourcing(write_only) is False
