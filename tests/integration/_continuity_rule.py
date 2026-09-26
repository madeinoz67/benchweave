"""The frozen row-1 decision rule, made executable (issue #172, check 1).

``classify`` implements #159 §6 VERBATIM — it never adjusts it. Every
clause below carries its inline §6 citation so a record amendment visibly
orphans the table test in ``test_cross_instance_continuity.py`` (the
design's §2.8 discipline: the citation map IS the drift tripwire).

Two inputs are qualification facts the CALLER declares, never something
this module establishes (design §2.8, finding F-C): the per-dispatch
tightening/splitting outcomes and the non-compositional class labels.
Bounds are explicit inputs; a ``None`` bound is the ABSENCE of a
commissioning (A02) and reads UNDERPOWERED — it never defaults.

Check-6 note (design §3 row 6): nothing in this module fakes a
bit-identical ``TestClock`` baseline — that gate is defined only under
the host's wait primitive, which does not exist on this tree, and stays
pinned for the reopen (#159 §4 CTL-8).

Clock domains are pinned per axis by the frozen rule (#159 §6 axes
clause, critique C5): X1/X3/X4 absolute milliseconds on the monotonic
clock; X2 the wall-derived ``max(host-computed age, device-reported
age)`` envelope. ``AXIS_CLOCK_DOMAINS`` is the one place the mapping
lives; ``emit_trial_log`` stamps every figure row with it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

#: The frozen axes (#159 §6 "Axes" clause). Order is the rule's own.
AXES: tuple[str, ...] = ("X1", "X2", "X3", "X4")

#: Each axis's clock domain (#159 §6: "each pinning its clock domain",
#: critique C5 — X1/X3/X4 absolute ms on the monotonic clock; X2 the
#: wall-derived envelope ``read_signal_values`` computes).
AXIS_CLOCK_DOMAINS: dict[str, str] = {
    "X1": "monotonic",
    "X2": "wall",
    "X3": "monotonic",
    "X4": "monotonic",
}


class Arm(Enum):
    """The four arms of #159 §6's total classification, in precedence
    order (critique C1: the prior draft left the modal outcome
    unclassified). A single enum member is the return — totality and
    single-valuedness hold by construction, which is what the table
    test pins."""

    UNDERPOWERED = "underpowered"
    FIRE = "fire"
    KILL = "kill"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class TrialRecord:
    """One measured trial (a fresh rig on a fresh store) plus the declared
    qualification facts the classifier consumes.

    ``axes_ms`` carries the measured axis values in absolute milliseconds
    (missing keys = unmeasured on this trial; an axis measured by NO
    trial is the single-instance clause's input). ``t_acq_controls`` is
    the CONJUNCTIVE §6 consistency-control outcome (short-T failed AND
    split refused) — a consistency check, never the authority (#159 §6
    ``T_acq_min`` authority clause, critique C4/F3). ``tightening_admitted``
    / ``splitting_admitted`` / ``unsplittable_class`` are the declared
    per-dispatch and per-class qualification facts (F-C). ``command`` and
    ``parameterization`` are the provenance fields check 3 shape-checks.
    """

    trial: int
    arm: str
    device_class: str
    axes_ms: dict[str, float]
    t_acq_controls: bool
    tightening_admitted: bool
    splitting_admitted: bool
    unsplittable_class: bool
    parameterization: dict[str, Any] = field(default_factory=dict)
    command: str = ""


def classify(trials: Sequence[TrialRecord], bounds: Mapping[str, float | None]) -> Arm:
    """Turn a trial ledger plus a bounds mapping into exactly one arm.

    Bounds are ``float | None`` per axis: ``None`` is the absence of a
    commissioning, and the §6 denominator clause makes any absence an
    UNDERPOWERED reading — a missing bound for ANY axis blocks that axis's
    decision, it does not default (A02).
    """
    measured: dict[str, list[float]] = {}
    for trial in trials:
        for axis, value in trial.axes_ms.items():
            measured.setdefault(axis, []).append(value)

    # §6 arm 1 — UNDERPOWERED: "any axis missing its commissioned bound;
    # single-instance rig (X2-X4 unmeasurable); or any axis's trial range
    # >25% of its own bound."
    if any(bounds.get(axis) is None for axis in AXES):
        return Arm.UNDERPOWERED
    if any(axis not in measured for axis in AXES):
        # The single-instance-rig clause: an axis no trial measured.
        return Arm.UNDERPOWERED
    for axis in AXES:
        bound = bounds[axis]
        assert bound is not None  # narrowed by the None check above
        values = measured[axis]
        if max(values) - min(values) > 0.25 * bound:
            return Arm.UNDERPOWERED

    # §6 arm 2 — FIRE: "at T_acq_min (both controls asserted), any axis
    # breaches its bound in >=3 of 5 trials." The breach comparator is
    # STRICTLY greater than (critique C10): equality passes.
    t_acq = [trial for trial in trials if trial.t_acq_controls]
    if len(t_acq) >= 5:
        for axis in AXES:
            bound = bounds[axis]
            assert bound is not None
            breaches = sum(
                1 for trial in t_acq if trial.axes_ms.get(axis, float("-inf")) > bound
            )
            if breaches >= 3:
                return Arm.FIRE

    # §6 arm 3 — KILL: "across >=2 device classes x >=5 dispatches each
    # (including >=1 non-compositional, un-splittable class — critique
    # C4/F3), every dispatch admits T-tightening or splitting until all
    # axes fit their bounds. T_acq_min dispatches are KILL-exempt by
    # construction (their controls assert neither tightening nor splitting
    # is available), so FIRE and KILL cannot arm on the same set."
    counted = [trial for trial in trials if not trial.t_acq_controls]
    by_class: dict[str, list[TrialRecord]] = {}
    for trial in counted:
        by_class.setdefault(trial.device_class, []).append(trial)
    qualifying = {
        label: group
        for label, group in by_class.items()
        if len(group) >= 5
        and all(t.tightening_admitted or t.splitting_admitted for t in group)
    }
    if len(qualifying) >= 2 and any(
        group[0].unsplittable_class for group in qualifying.values()
    ):
        return Arm.KILL

    # §6 arm 4 — INCONCLUSIVE: "everything else, including 2-of-5 and
    # 1-of-5 breach series with tight spread and commissioned bounds."
    return Arm.INCONCLUSIVE


def emit_trial_log(records: Sequence[TrialRecord]) -> dict[str, Any]:
    """Consolidate trial records into the provenance-carrying JSON (check 3).

    One row per numeric figure (trial x axis) plus one row per declared
    control outcome; every row carries ``command`` and ``parameterization``
    so the shape test can enforce the machine-checkable half of "every
    record-quoted figure cites a reproducing command and parameterization"
    (#159 §6 machine check 3). Quoting-into-prose discipline stays
    review-rubric territory (the design's deferral).
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        for axis in AXES:
            if axis not in record.axes_ms:
                continue
            rows.append(
                {
                    "trial": record.trial,
                    "arm": record.arm,
                    "device_class": record.device_class,
                    "axis": axis,
                    "value_ms": record.axes_ms[axis],
                    "clock_domain": AXIS_CLOCK_DOMAINS[axis],
                    "command": record.command,
                    "parameterization": dict(record.parameterization),
                }
            )
        rows.append(
            {
                "trial": record.trial,
                "arm": record.arm,
                "device_class": record.device_class,
                "figure": "t_acq_controls",
                "value": record.t_acq_controls,
                "command": record.command,
                "parameterization": dict(record.parameterization),
            }
        )
    return {"rows": rows}


def write_trial_log(path: Any, records: Iterable[TrialRecord]) -> dict[str, Any]:
    """Emit and write the consolidated log as JSON under the trial dir.

    The measurement tests write one log per run and print the path; the
    future measurement record quotes from this artifact (hand-
    transcription into prose is out of scope by design).
    """
    import json

    log = emit_trial_log(list(records))
    path.write_text(json.dumps(log, indent=2, sort_keys=True))
    return log
