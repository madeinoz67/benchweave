"""The cross-instance continuity instrument (issue #172 — row 1's rig).

The measurement rig for the #159 record's row 1: a two-instance harness
(dev-rig-a dispatches, dev-rig-b streams + carries a bench signal + the
protective write path) measuring the four frozen axes on both dispatch
arms, the consistency controls around ``T_acq_min``, and the classifier
that turns trial ledgers into arm verdicts. Every seam the axes read is a
production object (``_RunMonitor``/``retain``, ``_MonitoringPlugin``,
``_MonitoringClock``/``RunStreamHost``, ``read_signal_values``,
``ProtectionEngine``, ``OTDPBridge``'s per-instance lock); what is built
here is fixtures and bookkeeping, never a second mechanism.

Two rules live in this file's ancestry and they are NOT the same rule
(design §0):

* the FROZEN decision rule (#159 §6) — evaluated against COMMISSIONED
  bounds ``G1/G2/P/TB`` that do not exist (A02). The classifier in
  ``_continuity_rule`` implements it verbatim; every bound the table
  tests feed it is synthetic table data, and a missing bound reads
  UNDERPOWERED, never a default;
* the INSTRUMENT's own acceptance rule (design §5) — whose denominator
  is the rig's own dispatch duration and the matched control, explicitly
  NOT ``G1/G2/P/TB`` and never citable as a commissioning.

Check-6 honesty (design §3 row 6): the bit-identical ``TestClock``
fault-suite gate is defined only "under the host's wait primitive",
which does not exist on this tree — NOTHING lands for check 6 here, and
no baseline is faked against today's synchronous ``wait_ns``.

Design record:
``.claude/deep-review/2026-09-26-issue172-continuity-instrument-design.md``
(verdict BUILD; frozen parent: #159 §6).
"""

from __future__ import annotations

from _continuity_rule import Arm, TrialRecord, classify, emit_trial_log

# --- check 1: the classifier table (frozen #159 §6, verbatim) -----------------------
#
# The grid enumerates (breach count 0-5 x splittable x spread x bounds
# present x controls asserted) over SYNTHETIC table data — every bound is
# table data, labelled as such, never a commissioned G1/G2/P/TB. Each cell
# must yield exactly one arm (the single-enum return is the totality
# mechanism; the test asserts it across the grid); the 2-of-5/tight/
# bounds/controls cell must read INCONCLUSIVE; a None bound reads
# UNDERPOWERED; equality-at-bound is not a breach.

_BOUNDS = {"X1": 100.0, "X2": 100.0, "X3": 100.0, "X4": 100.0}


def _table_trial(
    *,
    value_ms: float,
    t_acq_controls: bool = True,
    device_class: str = "buffered",
    tightening_admitted: bool = False,
    splitting_admitted: bool = False,
    unsplittable_class: bool = True,
) -> TrialRecord:
    """One synthetic table trial: all four axes at one value (the grid
    varies the breach count by how many trials sit above the bound, not by
    per-axis structure — per-axis structure is covered by the dedicated
    cells below)."""
    return TrialRecord(
        trial=0,
        arm="non_capture",
        device_class=device_class,
        axes_ms={"X1": value_ms, "X2": value_ms, "X3": value_ms, "X4": value_ms},
        t_acq_controls=t_acq_controls,
        tightening_admitted=tightening_admitted,
        splitting_admitted=splitting_admitted,
        unsplittable_class=unsplittable_class,
        parameterization={"fixture": "classifier-table", "value_ms": value_ms},
        command="pytest tests/integration/test_cross_instance_continuity.py"
        " -k classifier (synthetic table data — no rig dispatch)",
    )


def _t_acq_series(breach_values: list[float], *, clean: float = 90.0) -> list[TrialRecord]:
    """Five T_acq_min trials (both controls asserted) whose breach count is
    len([v for v in breach_values]) — the values above the bound of 100.

    Breach values must stay within 25% of the bound of the clean value or
    the series is loose by the rule's own trial-quality gate (the grid's
    tight arm uses 105 against 90: range 15, tight for bound 100)."""
    return [
        _table_trial(value_ms=value, t_acq_controls=True)
        for value in [*breach_values, *[clean] * (5 - len(breach_values))]
    ]


def test_classifier_grid_total_and_single_valued() -> None:
    """Every grid cell yields exactly one arm: the return IS a single enum
    member (totality by construction), asserted cell by cell so a clause
    edit that empties a cell's mapping is visible here. The modal cell —
    2-of-5 breaches, tight spread, bounds present, controls asserted — is
    INCONCLUSIVE, never FIRE or KILL (#159 §6 arm 4 names it)."""
    for breach_count in range(6):
        values = [105.0] * breach_count
        for spread in ("tight", "loose"):
            # tight: every trial at the same value (range 0); loose: the
            # range exceeds 25% of the axis's own bound (140-90=50 > 25).
            trials = _t_acq_series(values)
            if spread == "loose":
                wide = list(trials)
                wide[0] = _table_trial(value_ms=140.0)
                wide[4] = _table_trial(value_ms=90.0)  # range 50 > 25% of 100
                trials = wide
            for bounds in (_BOUNDS, {**_BOUNDS, "X2": None}):
                arm = classify(trials, bounds)
                assert isinstance(arm, Arm), f"non-arm return {arm!r}"
                assert arm in (
                    Arm.UNDERPOWERED,
                    Arm.FIRE,
                    Arm.KILL,
                    Arm.INCONCLUSIVE,
                )
                # The pinned cells:
                if spread == "tight" and bounds is _BOUNDS:
                    if breach_count >= 3:
                        # §6 arm 2: at T_acq_min (both controls asserted),
                        # any axis breaching in >=3 of 5 trials fires.
                        assert arm is Arm.FIRE, f"{breach_count}-of-5: {arm}"
                    else:
                        # 0/1/2-of-5 with tight spread and commissioned
                        # bounds: INCONCLUSIVE (arm 4 names 2-of-5 and
                        # 1-of-5 explicitly).
                        assert arm is Arm.INCONCLUSIVE, f"{breach_count}-of-5: {arm}"
                if spread == "loose":
                    # §6 arm 1: trial range > 25% of the axis's own bound
                    # reads UNDERPOWERED — decide nothing.
                    assert arm is Arm.UNDERPOWERED, f"loose spread: {arm}"
                if bounds["X2"] is None:
                    # §6 denominator clause: a missing bound for ANY axis
                    # blocks that axis's decision; it never defaults.
                    assert arm is Arm.UNDERPOWERED, f"missing X2 bound: {arm}"


def test_classifier_two_of_five_is_inconclusive() -> None:
    """The RED-pinned modal cell on its own (§6 arm 4: "everything else,
    including 2-of-5 and 1-of-5 breach series with tight spread and
    commissioned bounds")."""
    trials = _t_acq_series([105.0, 105.0])
    assert classify(trials, _BOUNDS) is Arm.INCONCLUSIVE


def test_classifier_equality_at_bound_is_not_a_breach() -> None:
    """§6 breach comparator: strictly greater than; equality passes. Five
    trials exactly AT the bound breach nothing — INCONCLUSIVE, not FIRE."""
    at_bound = [_table_trial(value_ms=100.0) for _ in range(5)]
    assert classify(at_bound, _BOUNDS) is Arm.INCONCLUSIVE


def test_classifier_kill_needs_two_classes_five_dispatches_unsplittable() -> None:
    """§6 arm 3: KILL requires >=2 device classes x >=5 dispatches each,
    including >=1 non-compositional un-splittable class, where every
    counted dispatch admits T-tightening or splitting."""
    compliant = dict(t_acq_controls=False, tightening_admitted=True)

    def killable(cls: str, *, unsplittable: bool) -> list[TrialRecord]:
        return [
            _table_trial(
                value_ms=10.0,
                device_class=cls,
                unsplittable_class=unsplittable,
                **compliant,
            )
            for _ in range(5)
        ]

    both = [*killable("buffered", unsplittable=True), *killable("unbuffered", unsplittable=False)]
    assert classify(both, _BOUNDS) is Arm.KILL
    # Without the un-splittable class (critique C4/F3's guard): not KILL.
    all_splittable = [
        *killable("buffered", unsplittable=False),
        *killable("unbuffered", unsplittable=False),
    ]
    assert classify(all_splittable, _BOUNDS) is Arm.INCONCLUSIVE
    # One class only: not KILL.
    assert classify(killable("buffered", unsplittable=True), _BOUNDS) is Arm.INCONCLUSIVE
    # A counted dispatch that admits neither tightening nor splitting
    # blocks the KILL (the exposure survives somewhere).
    blocked = killable("buffered", unsplittable=True)
    blocked[2] = _table_trial(value_ms=10.0, device_class="buffered", t_acq_controls=False)
    with_unblocked = [*blocked, *killable("unbuffered", unsplittable=False)]
    assert classify(with_unblocked, _BOUNDS) is Arm.INCONCLUSIVE


def test_classifier_refuses_to_arm_fire_and_kill_on_the_same_set() -> None:
    """§6 arm 3's construction clause: "T_acq_min dispatches are KILL-exempt
    by construction (their controls assert neither tightening nor splitting
    is available), so FIRE and KILL cannot arm on the same set." Two
    discriminating forms, both over tight data (a loose series reads
    UNDERPOWERED by the rule's own trial-quality gate):

    1. PRECEDENCE: a set whose FIRE predicate (3-of-5 T_acq breaches) AND
       KILL predicate (>=2 classes x >=5 admitting dispatches, one
       un-splittable) are both satisfiable resolves to exactly ONE arm —
       FIRE, the higher-precedence one.
    2. EXEMPTION: T_acq trials marked splitting-admitted (the adversarial
       double marking) NEVER count toward KILL's per-class dispatch
       minimums — with only one genuine non-T_acq class the set reads
       INCONCLUSIVE, not KILL."""
    fire_side = _t_acq_series([105.0, 105.0, 105.0])  # 3-of-5 breaches
    kill_side = [
        *[
            _table_trial(
                value_ms=90.0,
                device_class="unbuffered",
                t_acq_controls=False,
                splitting_admitted=True,
                unsplittable_class=True,
            )
            for _ in range(5)
        ],
        *[
            _table_trial(
                value_ms=90.0,
                device_class="third",
                t_acq_controls=False,
                tightening_admitted=True,
                unsplittable_class=False,
            )
            for _ in range(5)
        ],
    ]
    arm = classify([*fire_side, *kill_side], _BOUNDS)
    assert arm is Arm.FIRE, f"both-predicate input must resolve to exactly FIRE, got {arm}"

    double_marked = [
        _table_trial(
            value_ms=90.0,
            t_acq_controls=True,
            splitting_admitted=True,
            device_class="buffered",
            unsplittable_class=True,
        )
        for _ in range(5)
    ]
    one_real_class = [
        _table_trial(
            value_ms=90.0,
            device_class="unbuffered",
            t_acq_controls=False,
            splitting_admitted=True,
            unsplittable_class=True,
        )
        for _ in range(5)
    ]
    arm = classify([*double_marked, *one_real_class], _BOUNDS)
    assert arm is Arm.INCONCLUSIVE, (
        f"T_acq dispatches must never count toward KILL's class minimums: {arm}"
    )


def test_classifier_absent_axis_reads_underpowered() -> None:
    """§6 arm 1's single-instance clause: an axis NO trial measured (the
    single-instance rig cannot measure X2-X4) reads UNDERPOWERED even with
    every bound present."""
    partial = [
        TrialRecord(
            trial=1,
            arm="non_capture",
            device_class="buffered",
            axes_ms={"X1": 50.0},
            t_acq_controls=True,
            tightening_admitted=False,
            splitting_admitted=False,
            unsplittable_class=True,
            parameterization={"fixture": "classifier-table"},
            command="pytest -k classifier (synthetic table data)",
        )
    ]
    assert classify(partial, _BOUNDS) is Arm.UNDERPOWERED


# --- check 3: the provenance emitter's shape ---------------------------------------


def test_emit_trial_log_every_numeric_row_carries_command_and_parameterization() -> None:
    """The machine-enforceable half of "every record-quoted figure cites a
    reproducing command": each numeric row in the emitted log carries both
    ``command`` and ``parameterization`` (quoting-into-prose discipline
    stays review-rubric territory — the design's check-3 deferral)."""
    records = _t_acq_series([140.0, 140.0])
    log = emit_trial_log(records)
    rows = log["rows"]
    assert rows, "the emitted log carries no rows"
    numeric_rows = [row for row in rows if isinstance(row.get("value_ms"), (int, float))]
    assert numeric_rows, "no numeric rows to shape-check"
    for row in numeric_rows:
        assert isinstance(row.get("command"), str) and row["command"], row
        assert isinstance(row.get("parameterization"), dict), row
        assert row["parameterization"], row
    # Axis identity and clock domain ride every figure row (the domain pin
    # is #159 §6's critique-C5 clause).
    for row in numeric_rows:
        assert row["axis"] in ("X1", "X2", "X3", "X4"), row
        assert row["clock_domain"] in ("monotonic", "wall"), row
