"""The G1d mutation controls (design record §6, "behavioural teeth"): each
arm applies ONE behavioural mutation — through monkeypatched module
attributes, so the real checker path runs — and asserts the mutation reds
ITS row's checker and no other of the ten.

m1 delete the fire-time guard re-check in ``attempt_fire`` → R-PROTECT-1
m2 ``>=`` for ``>`` in the staleness predicate → ST-2
m3 apply the trip guard to the de-energise control → R-DEENERGISE-1
m4 derive the tile's set line from the staged input → R-ENERGISE-1
m5 dismissal sets the acknowledged bit → SR-B3
m6 drop the stale marker while keeping ``data-bw-stale`` → ST-4
m7 loosen the toast severity type to admit warning → SR-B1

Each mutation changes BEHAVIOUR (guards, dispatch, transitions), never
markup literals alone — the G1b kill rule's own discrimination. The checkers
read the mutated module attributes at call time (``compositions.attempt_fire``,
``staleness.staleness``, ``compositions.render_workbench``,
``compositions.ToastData``), so a monkeypatched mutant is the mutation.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Literal

import pytest
from _pytest.monkeypatch import MonkeyPatch
from benchweave_ui_html import artifacts, compositions, staleness

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "internal" / "ui-contract.md"


def _all_checker_messages() -> dict[str, list[str]]:
    """Run all ten composition checkers against the real contract rows."""
    from benchweave_ui_html.grammar import parse_contract
    from benchweave_ui_html.manifest import MANIFEST

    contract = parse_contract(CONTRACT.read_text(encoding="utf-8"), MANIFEST)
    rows = {row.row_id: row for table in contract.tables for row in table.body}
    return {
        key: checker(rows[f"{slug}::{key}"])
        for slug, keys in (
            ("b-2-state-rules", ("SR-B1", "SR-B2", "SR-B3")),
            ("b-4-staleness", ("ST-1", "ST-2", "ST-3", "ST-4")),
            ("c-1-safety-rules", ("R-ENERGISE-1", "R-DEENERGISE-1", "R-PROTECT-1")),
        )
        for key in (keys)
        if (checker := artifacts._COMPOSITION_RULE_CHECKERS.get(key)) is not None
    }


def _assert_exactly_one_red(target: str) -> None:
    messages = _all_checker_messages()
    assert messages[target], f"the mutation must red {target}"
    for key, value in messages.items():
        if key != target:
            assert not value, (key, value)


def test_no_mutation_all_ten_checkers_green() -> None:
    """The healthy population: all ten behaviour rows green (the control the
    mutation arms are read against)."""
    messages = _all_checker_messages()
    assert len(messages) == 10, sorted(messages)
    for key, value in messages.items():
        assert not value, (key, value)


def test_m1_fire_time_guard_deletion_reds_r_protect(monkeypatch: MonkeyPatch) -> None:
    """m1: attempt_fire without the guard re-check dispatches while
    armed+tripped — R-PROTECT-1 reds."""

    def mutant_fire(
        state: compositions.WorkbenchState, action: compositions.ActionKey
    ) -> compositions.FireResult:
        if action == "de-energise":
            return compositions.Dispatched("de-energise", None)
        if action == "set-point" and not state.output.energised:
            return compositions.Dispatched("set-point", state.staged_value)
        if state.confirm != "armed" or state.armed_action != action:
            return compositions.Refused("not-armed")
        return compositions.Dispatched(action, state.staged_value)

    monkeypatch.setattr(compositions, "attempt_fire", mutant_fire)
    _assert_exactly_one_red("R-PROTECT-1")


def test_m2_boundary_geq_reds_st_2(monkeypatch: MonkeyPatch) -> None:
    """m2: a >= boundary makes equality stale — ST-2 reds at 150/150."""

    def mutant_staleness(
        freshness_ms: float | None, max_age_ms: float | None
    ) -> staleness.StalenessVerdict:
        if max_age_ms is None or freshness_ms is None:
            return "no-verdict"
        if freshness_ms < 0 or max_age_ms < 0:
            return "no-verdict"
        return "stale" if freshness_ms >= max_age_ms else "fresh"

    monkeypatch.setattr(staleness, "staleness", mutant_staleness)
    _assert_exactly_one_red("ST-2")


def test_m3_trip_guard_on_deenergise_reds_r_deenergise(
    monkeypatch: MonkeyPatch,
) -> None:
    """m3: gating the off action under the trip — R-DEENERGISE-1 reds."""
    real_fire = compositions.attempt_fire

    def mutant_fire(
        state: compositions.WorkbenchState, action: compositions.ActionKey
    ) -> compositions.FireResult:
        if action == "de-energise":
            guard = compositions.energise_guard(state)
            if guard is not None:
                return compositions.Refused(guard)
        return real_fire(state, action)

    monkeypatch.setattr(compositions, "attempt_fire", mutant_fire)
    _assert_exactly_one_red("R-DEENERGISE-1")


def test_m4_set_line_from_staged_input_reds_r_energise(
    monkeypatch: MonkeyPatch,
) -> None:
    """m4: deriving the tile's set line from the staged input — the
    laundering witness inside R-ENERGISE-1's set-point arm reds."""
    real_render = compositions.render_workbench

    def mutant_render(state: compositions.WorkbenchState) -> str:
        html = real_render(state)
        for reading in state.readings:
            if reading.set_value is not None:
                html = html.replace(
                    f"Set {reading.set_value} ", f"Set {state.staged_value:g} "
                )
        return html

    monkeypatch.setattr(compositions, "render_workbench", mutant_render)
    _assert_exactly_one_red("R-ENERGISE-1")


def test_m5_dismissal_acknowledges_reds_sr_b3(monkeypatch: MonkeyPatch) -> None:
    """m5: dismissal also setting the acknowledged bit — SR-B3 reds."""
    real_reduce = compositions.reduce

    def mutant_reduce(
        state: compositions.WorkbenchState, event: compositions.WorkbenchEvent
    ) -> compositions.WorkbenchState:
        following = real_reduce(state, event)
        if isinstance(event, compositions.DismissMessage):
            following = dataclasses.replace(
                following,
                messages=tuple(
                    dataclasses.replace(message, acknowledged=True)
                    if message.id == event.message_id
                    else message
                    for message in following.messages
                ),
            )
        return following

    monkeypatch.setattr(compositions, "reduce", mutant_reduce)
    _assert_exactly_one_red("SR-B3")


def test_m6_marker_drop_keeping_attribute_reds_st_4(monkeypatch: MonkeyPatch) -> None:
    """m6: dropping the stale marker span while keeping data-bw-stale —
    ST-4 reds (a stale reading never renders without its marker)."""
    real_render = compositions.render_workbench

    def mutant_render(state: compositions.WorkbenchState) -> str:
        return real_render(state).replace(
            '<span class="bw-reading__stale-marker">stale</span>', ""
        )

    monkeypatch.setattr(compositions, "render_workbench", mutant_render)
    _assert_exactly_one_red("ST-4")


def test_m7_loosened_toast_type_reds_sr_b1(monkeypatch: MonkeyPatch) -> None:
    """m7: loosening the toast severity type to admit warning — SR-B1 reds
    (the transient channel is typed shut; the checker reflects on the
    annotation, so the loosened Literal is the detected mechanism)."""

    @dataclasses.dataclass(frozen=True)
    class MutantToastData:
        severity: Literal["neutral", "success", "advisory", "warning"]
        text: str

    monkeypatch.setattr(compositions, "ToastData", MutantToastData)
    messages = _all_checker_messages()
    assert messages["SR-B1"], "the loosened toast type must red SR-B1"
    for key, value in messages.items():
        if key != "SR-B1":
            assert not value, (key, value)


@pytest.mark.parametrize(
    ("arm", "target"),
    [
        ("m1", "R-PROTECT-1"),
        ("m2", "ST-2"),
        ("m3", "R-DEENERGISE-1"),
        ("m4", "R-ENERGISE-1"),
        ("m5", "SR-B3"),
        ("m6", "ST-4"),
        ("m7", "SR-B1"),
    ],
)
def test_mutation_control_coverage(arm: str, target: str) -> None:
    """The record's §6 control table is pinned: each arm exists as a test
    above and names its target row (an arm losing its target renames here
    visibly)."""
    assert any(name.startswith(f"test_{arm}_") for name in globals())
    assert target in _all_checker_messages()
