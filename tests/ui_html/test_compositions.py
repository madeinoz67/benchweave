"""The composition state machine's unit suite (G1d design record §3 slice 1):
the TS proof bodies — ``safety-proof.test.tsx``, ``reading-states-proof.test.tsx``,
``DeviceWorkbench.test.tsx`` and ``staleness.test.ts`` — ported
assertion-for-assertion onto ``compositions.py`` (the React runtime replaced
by pure functions; the injected callbacks by ``attempt_fire``).

The ten contract-row checkers (slice 2) drive this same machinery through
``RuleProofArtifact`` entries; this file pins the machinery itself.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import get_args, get_type_hints

import pytest
from benchweave_ui_html import compositions
from benchweave_ui_html.assertions import Element, RenderedComponent
from benchweave_ui_html.compositions import (
    AcknowledgeAttempt,
    AuthorityLost,
    AuthorityRegained,
    Cancel,
    DismissMessage,
    Dispatched,
    ReadingWentStale,
    Refused,
    TripArrives,
    TripClears,
    Unrelated,
    reduce,
)
from benchweave_ui_html.staleness import staleness

# --- the scenes (psu-07 / daq-47, the contract's own invented identities) ----


def psu() -> compositions.WorkbenchState:
    return compositions.psu_scene()


def daq() -> compositions.WorkbenchState:
    return compositions.daq_scene()


def control_button(rendered: RenderedComponent, label: str) -> Element:
    """The first button whose element text carries ``label``."""
    matches = [
        element
        for element in rendered.elements
        if element.tag == "button"
        and label in element_text(rendered, element)
    ]
    assert matches, f"no button carries the label {label!r}"
    return matches[0]


def element_text(rendered: RenderedComponent, element: Element) -> str:
    """The element's subtree text — matched by IDENTITY, never ``index()``
    (twin controls share tag+attrs, so dataclass equality would resolve to
    the wrong sibling's text)."""
    for candidate, text in zip(rendered.elements, rendered._element_texts, strict=True):
        if candidate is element:
            return text
    raise AssertionError("element not in render")


def message_visible(scene: compositions.WorkbenchState, message_id: str) -> bool:
    rendered = RenderedComponent(compositions.render_workbench(scene))
    message = next(m for m in scene.messages if m.id == message_id)
    bubbles = rendered.texts_of_elements(class_hook="bw-alert-bubble__content")
    return any(message.text in text for text in bubbles)


def stale_voltage_scene(
    *, freshness: float | None, max_age: float | None
) -> compositions.WorkbenchState:
    """The PSU scene with the voltage reading's cadence pair replaced."""
    scene = psu()
    voltage = dataclasses.replace(scene.readings[0], freshness_ms=freshness, max_age_ms=max_age)
    return dataclasses.replace(scene, readings=(voltage, *scene.readings[1:]))


def de_energised(scene: compositions.WorkbenchState) -> compositions.WorkbenchState:
    return dataclasses.replace(
        scene, output=compositions.OutputState(energised=False, trip=scene.output.trip)
    )


# --- ST-2: the predicate (ported from staleness.test.ts) ----------------------


def test_staleness_boundary_is_strictly_greater() -> None:
    # The e-folded control: equality is fresh, one ms more is stale.
    assert staleness(150, 150) == "fresh"
    assert staleness(151, 150) == "stale"
    assert staleness(149, 150) == "fresh"


def test_staleness_zero_window_is_fresh_acquisition_only() -> None:
    assert staleness(1, 0) == "stale"
    assert staleness(0, 0) == "fresh"


def test_staleness_garbage_renders_no_verdict() -> None:
    assert staleness(None, 150) == "no-verdict"  # freshness_ms: null
    assert staleness(120, None) == "no-verdict"  # no window supplied
    assert staleness(float("nan"), 150) == "no-verdict"
    assert staleness(float("inf"), 150) == "no-verdict"
    assert staleness(-1, 150) == "no-verdict"
    assert staleness(120, float("nan")) == "no-verdict"
    assert staleness(120, float("inf")) == "no-verdict"
    assert staleness(120, -1) == "no-verdict"


# --- reduce: the transition model ----------------------------------------------


def test_arm_and_cancel_stage_intent_only() -> None:
    armed = reduce(psu(), compositions.Arm("energise"))
    assert armed.confirm == "armed"
    assert armed.armed_action == "energise"
    cancelled = reduce(armed, Cancel())
    assert cancelled.confirm == "idle"
    assert cancelled.armed_action is None


def test_trip_and_authority_transitions() -> None:
    tripped = reduce(psu(), TripArrives())
    assert tripped.output.trip is True
    assert reduce(tripped, TripClears()).output.trip is False
    assert reduce(psu(), AuthorityLost()).authority is False
    assert reduce(reduce(psu(), AuthorityLost()), AuthorityRegained()).authority is True


def test_unrelated_rerender_persists_messages_and_clears_announcements() -> None:
    crossed = reduce(psu(), ReadingWentStale("voltage"))
    assert crossed.last_transition == ("voltage",)
    steady = reduce(crossed, Unrelated())
    # SR-B1 persistence: the warning message survives an unrelated re-render.
    assert steady.messages == crossed.messages
    # ST-4 coalescing: the announcement belongs to the crossing render alone.
    assert steady.last_transition == ()


def test_every_non_crossing_event_clears_the_announcement_ledger() -> None:
    """The reduce docstring's contract (fold A2): the crossing render
    announces ONCE — every other event renders the ledger empty, so the
    announcement cannot re-fire on a later interaction."""
    crossed = reduce(psu(), ReadingWentStale("voltage"))
    assert crossed.last_transition == ("voltage",)
    assert reduce(crossed, compositions.Arm("energise")).last_transition == ()
    assert reduce(crossed, Cancel()).last_transition == ()
    no_auth = reduce(psu(), AuthorityLost())
    crossed_no_auth = reduce(no_auth, ReadingWentStale("voltage"))
    assert crossed_no_auth.last_transition == ("voltage",)
    refused = reduce(crossed_no_auth, AcknowledgeAttempt("margin"))
    assert refused.authority is False
    assert refused.last_transition == ()


# --- attempt_fire: R-ENERGISE-1 / R-DEENERGISE-1 / R-PROTECT-1 ----------------


@pytest.mark.parametrize("scene_factory", [psu, daq])
def test_vacuous_pass_control_both_scenes_carry_the_two_actions(
    scene_factory: Callable[[], compositions.WorkbenchState],
) -> None:
    """Both scenes render an energy-sourcing and an energy-removing action —
    the control that kills empty-page passes (TS: the vacuous-pass control)."""
    rendered = RenderedComponent(compositions.render_workbench(scene_factory()))
    labels = [element_text(rendered, e) for e in rendered.elements if e.tag == "button"]
    assert any("Energise output" in text for text in labels)
    assert any("De-energise output" in text for text in labels)


@pytest.mark.parametrize("scene_factory", [psu, daq])
def test_energise_requires_the_second_explicit_action(
    scene_factory: Callable[[], compositions.WorkbenchState],
) -> None:
    """Arm the energise control ⇒ no dispatch; the confirm text states the
    effect, the exact value with unit, and the target; the second explicit
    action dispatches with the staged value (R-ENERGISE-1)."""
    scene = scene_factory()
    unarmed = de_energised(scene)
    # The first press only stages: firing while un-armed never dispatches.
    assert isinstance(compositions.attempt_fire(unarmed, "energise"), Refused)
    armed = reduce(unarmed, compositions.Arm("energise"))
    rendered = RenderedComponent(compositions.render_workbench(armed))
    confirm_text = rendered.texts_of_elements(class_hook="bw-confirm__text")
    assert any(
        "the output will be energised" in text
        and f"{scene.staged_value:g} V" in text
        and f"{scene.device_id.upper()} output" in text
        for text in confirm_text
    ), confirm_text
    fired = compositions.attempt_fire(armed, "energise")
    assert fired == Dispatched("energise", scene.staged_value)


def test_setpoint_change_on_energised_output_is_energy_sourcing() -> None:
    """R-ENERGISE-1: on an energised output the apply arms a confirm whose
    text states the set-point effect; the confirm dispatches the staged value."""
    scene = psu()
    assert scene.output.energised
    assert isinstance(compositions.attempt_fire(scene, "set-point"), Refused)
    armed = reduce(scene, compositions.Arm("set-point"))
    rendered = RenderedComponent(compositions.render_workbench(armed))
    confirm_text = rendered.texts_of_elements(class_hook="bw-confirm__text")
    assert any(
        "the set-point of the energised output will change" in text
        and f"{scene.staged_value:g} V" in text
        for text in confirm_text
    ), confirm_text
    assert compositions.attempt_fire(armed, "set-point") == Dispatched(
        "set-point", scene.staged_value
    )


def test_setpoint_on_deenergised_output_applies_in_one_action() -> None:
    """On a de-energised output the staged value is inert: one action, no
    confirm subtree (TS: 'applies a set-point on a de-energised output
    without a confirm step')."""
    scene = de_energised(psu())
    assert compositions.attempt_fire(scene, "set-point") == Dispatched(
        "set-point", psu().staged_value
    )
    rendered = RenderedComponent(compositions.render_workbench(scene))
    assert "Confirm: Apply staged set-point" not in rendered.text_content


@pytest.mark.parametrize("guard_state", ["healthy", "trip", "no-authority", "both"])
def test_deenergise_dispatches_in_one_action_in_every_guard_state(guard_state: str) -> None:
    """R-DEENERGISE-1: the off action is never confirmed, never gated —
    nothing stands between the operator and de-energising (A04)."""
    scene = psu()
    scene = dataclasses.replace(
        scene,
        output=compositions.OutputState(
            scene.output.energised, trip=guard_state in ("trip", "both")
        ),
        authority=guard_state not in ("no-authority", "both"),
    )
    assert compositions.attempt_fire(scene, "de-energise") == Dispatched("de-energise", None)
    rendered = RenderedComponent(compositions.render_workbench(scene))
    assert "Confirm: De-energise" not in rendered.text_content
    assert "will be de-energised" not in rendered.text_content
    # The control is never disabled by any guard reason.
    de_button = control_button(rendered, "De-energise output")
    assert "disabled" not in de_button.attrs
    assert "data-bw-disabled-reason" not in de_button.attrs


def test_trip_disables_energise_with_protection_active() -> None:
    """R-PROTECT-1: trip ⇒ the energise control renders disabled with the
    reason and its §C.2 visible label; de-energise stays enabled."""
    tripped = reduce(psu(), TripArrives())
    rendered = RenderedComponent(compositions.render_workbench(tripped))
    energise = control_button(rendered, "Energise output")
    assert "disabled" in energise.attrs
    assert energise.attrs.get("data-bw-disabled-reason") == "protection-active"
    de = control_button(rendered, "De-energise output")
    assert "disabled" not in de.attrs
    assert compositions.energise_guard(tripped) == "protection-active"


def test_guard_while_armed_holds_at_fire_time() -> None:
    """The §E.1 confirm-action Notes' fire-time rule (the TS `armed guard`
    describe block): arm, the trip arrives ⇒ the ARMED confirm button itself
    is disabled with protection-active + the visible label, the fire REFUSES
    without dispatch; no auto-disarm, Cancel stays enabled, the departing
    guard re-enables and the fire then dispatches."""
    scene = psu()
    armed = reduce(de_energised(scene), compositions.Arm("energise"))
    guarded = reduce(armed, TripArrives())
    # No auto-disarm: the armed state survives the guard.
    assert guarded.confirm == "armed"
    rendered = RenderedComponent(compositions.render_workbench(guarded))
    confirm = control_button(rendered, "Confirm: Energise output")
    assert "disabled" in confirm.attrs
    assert confirm.attrs.get("data-bw-disabled-reason") == "protection-active"
    labels = rendered.texts_of_elements_with_attribute("data-bw-disabled-label")
    assert "Protection trip active" in labels, labels
    cancel = control_button(rendered, "Cancel")
    assert "disabled" not in cancel.attrs
    # The fire path re-checks the guard against current state and refuses.
    assert compositions.attempt_fire(guarded, "energise") == Refused("protection-active")
    # The departing guard re-enables and the fire then dispatches.
    cleared = reduce(guarded, TripClears())
    rendered_cleared = RenderedComponent(compositions.render_workbench(cleared))
    assert "disabled" not in control_button(rendered_cleared, "Confirm: Energise output").attrs
    assert compositions.attempt_fire(cleared, "energise") == Dispatched(
        "energise", scene.staged_value
    )


def test_combined_trip_and_no_authority_presents_protection_active() -> None:
    armed = reduce(de_energised(psu()), compositions.Arm("energise"))
    guarded = reduce(reduce(armed, TripArrives()), AuthorityLost())
    rendered = RenderedComponent(compositions.render_workbench(guarded))
    confirm = control_button(rendered, "Confirm: Energise output")
    assert confirm.attrs.get("data-bw-disabled-reason") == "protection-active"
    assert "No lease or policy authority" not in rendered.texts_of_elements_with_attribute(
        "data-bw-disabled-label"
    )
    assert compositions.attempt_fire(guarded, "energise") == Refused("protection-active")


def test_no_authority_disables_with_its_own_label() -> None:
    no_auth = reduce(psu(), AuthorityLost())
    rendered = RenderedComponent(compositions.render_workbench(no_auth))
    energise = control_button(rendered, "Energise output")
    assert energise.attrs.get("data-bw-disabled-reason") == "no-authority"
    assert "No lease or policy authority" in rendered.texts_of_elements_with_attribute(
        "data-bw-disabled-label"
    )
    armed = reduce(no_auth, compositions.Arm("energise"))
    assert compositions.attempt_fire(armed, "energise") == Refused("no-authority")


@pytest.mark.parametrize("guard_state", ["trip", "no-authority"])
def test_every_disabled_control_carries_its_reasons_visible_label(guard_state: str) -> None:
    """Property (e), both renders: every [data-bw-disabled-reason] element's
    key has its key's visible label text rendered (data-bw-disabled-label)."""
    scene = psu()
    if guard_state == "trip":
        scene = reduce(scene, TripArrives())
    else:
        scene = reduce(scene, AuthorityLost())
    rendered = RenderedComponent(compositions.render_workbench(scene))
    keys = [
        str(element.attrs["data-bw-disabled-reason"])
        for element in rendered.elements
        if "data-bw-disabled-reason" in element.attrs
    ]
    assert keys, "the guard renders must carry disabled controls"
    labels = rendered.texts_of_elements_with_attribute("data-bw-disabled-label")
    for key in set(keys):
        assert compositions.GUARD_LABELS[key] in labels, (key, labels)


# --- the scene render: banner, triad, messages --------------------------------


def test_mode_banner_renders_the_fixed_wording() -> None:
    rendered = RenderedComponent(compositions.render_workbench(psu()))
    assert "SIMULATED PRESENTATION DATA" in rendered.text_content
    assert rendered.texts_of_elements(attribute=("data-bw-mode", "simulated"))


def test_set_line_reads_gateway_observed_set_not_the_staged_input() -> None:
    """The laundering witness (TS b-laundering): staged 13.0 while the tile's
    set evidence still reads the gateway-observed 12.5 — a renderer that
    derives the set line from the staged input reds here."""
    scene = dataclasses.replace(psu(), staged_value=13.0)
    rendered = RenderedComponent(compositions.render_workbench(scene))
    set_lines = rendered.texts_of_elements(class_hook="bw-reading__set")
    assert "Set 12.5 V" in set_lines, set_lines
    assert "Set 13.0 V" not in set_lines
    # The staged value lives ONLY in the staging input: no tile value carries it.
    value_texts = rendered.texts_of_elements(class_hook="bw-reading__value")
    assert not any("13" in text for text in value_texts), value_texts


def test_staged_pins_live_only_in_the_staging_inputs() -> None:
    """§E.3: the staged value's pins are the staging inputs; no reading tile
    carries a staged marker."""
    rendered = RenderedComponent(compositions.render_workbench(psu()))
    help_text = rendered.texts_of_elements(class_hook="bw-numeric__help")
    assert any("Staged value; use Apply to request the change" in text for text in help_text)
    for tile_text in rendered.texts_of_elements(class_hook="bw-reading"):
        assert "staged" not in tile_text.lower()


# --- SR-B1: anchoring, persistence, the typed toast channel --------------------


def test_warning_message_is_anchored_in_its_panel_across_rerender() -> None:
    scene = psu()
    rendered = RenderedComponent(compositions.render_workbench(scene))
    warning = next(m for m in scene.messages if m.severity == "warning")
    # Anchored in its affected context: the panel's subtree text carries the
    # message (containment via text attribution).
    panel_texts = rendered.texts_of_elements(class_hook="bw-panel__body")
    assert any(warning.text in text for text in panel_texts)
    # Persistence across an unrelated re-render.
    rerendered = RenderedComponent(compositions.render_workbench(reduce(scene, Unrelated())))
    assert any(
        warning.text in text
        for text in rerendered.texts_of_elements(class_hook="bw-panel__body")
    )


def test_toast_severity_type_admits_only_neutral_success_advisory() -> None:
    """SR-B1's toast restriction is unrepresentable-bad-state: the
    ``ToastData.severity`` annotation is the mechanism, and the checker
    reflects on it (m7 loosens the type and must red)."""
    hints = get_type_hints(compositions.ToastData)
    assert set(get_args(hints["severity"])) == {"neutral", "success", "advisory"}
    for severity in ("neutral", "success", "advisory"):
        html = compositions.render_toast(compositions.ToastData(severity=severity, text="Applied"))
        assert f'data-severity="{severity}"' in html


@pytest.mark.parametrize("severity", ["warning", "critical", "trip"])
def test_warning_critical_trip_render_anchored_never_transient(severity: str) -> None:
    """warning/critical/trip messages render anchored in their context and no
    toast element carries them (the transient channel is typed shut)."""
    scene = psu()
    message = dataclasses.replace(scene.messages[0], severity=severity)  # type: ignore[arg-type]
    scene = dataclasses.replace(scene, messages=(message,))
    rendered = RenderedComponent(compositions.render_workbench(scene))
    assert not any("data-bw-toast" in element.attrs for element in rendered.elements)
    panel_texts = rendered.texts_of_elements(class_hook="bw-panel__body")
    assert any(message.text in text for text in panel_texts)


# --- SR-B2: glow vocabulary -----------------------------------------------------


def _single_reading_scene(severity: str) -> compositions.WorkbenchState:
    return dataclasses.replace(
        psu(),
        readings=(
            compositions.ReadingSlot(
                id="voltage",
                label="Supply voltage",
                value="12.04",
                unit="V",
                severity=severity,  # type: ignore[arg-type]
                quality="Verified",
                freshness_ms=120.0,
                max_age_ms=150.0,
            ),
        ),
    )


@pytest.mark.parametrize("severity", ["warning", "critical", "trip"])
def test_abnormal_states_carry_icon_label_border_and_text(severity: str) -> None:
    scene = _single_reading_scene(severity)
    rendered = RenderedComponent(compositions.render_workbench(scene))
    tile = next(
        element
        for element in rendered.elements
        if "bw-reading" in element.class_tokens
        and element.attrs.get("data-severity") == severity
    )
    # border hook: the tile root carries data-severity (the CSS border/glow
    # selector derives from it).
    assert tile.attrs.get("data-severity") == severity
    # icon: the §F.1 severity icon renders inside the tile's severity span
    # (the span's subtree text carries no svg, so assert an svg inside the
    # tile's element range right after the span — presence is the pin).
    severity_span = next(
        element
        for element in rendered.elements
        if "bw-reading__severity" in element.class_tokens
    )
    span_seen = False
    icons_after_span = False
    for candidate in rendered.elements:
        if candidate is severity_span:
            span_seen = True
            continue
        if span_seen and candidate.tag == "svg":
            icons_after_span = True
            break
        if span_seen and "bw-reading__" in (candidate.attrs.get("class") or ""):
            break  # the next tile's fields begin; the icon window has closed
    assert icons_after_span, "the abnormal reading must carry an icon"
    # explicit label: the severity name renders in the severity span.
    assert severity in element_text(rendered, severity_span)
    # text: the reading's own label renders on the affected reading.
    assert "Supply voltage" in element_text(rendered, tile)


@pytest.mark.parametrize("severity", ["neutral", "success"])
def test_normal_and_success_render_no_glow_vocabulary(severity: str) -> None:
    scene = _single_reading_scene(severity)
    rendered = RenderedComponent(compositions.render_workbench(scene))
    assert not any("data-bw-glow" in element.attrs for element in rendered.elements)
    assert not any(
        "glow" in token for element in rendered.elements for token in element.class_tokens
    )


# --- SR-B3: dismissal is not acknowledgement ------------------------------------


def test_dismissal_removes_the_bubble_but_not_the_condition() -> None:
    scene = psu()
    advisory = next(m for m in scene.messages if m.severity == "advisory")
    # Fire the advisory's condition (authority), then dismiss it.
    fired = reduce(scene, AuthorityLost())
    assert message_visible(fired, advisory.id)
    dismissed = reduce(fired, DismissMessage(advisory.id))
    assert not message_visible(dismissed, advisory.id)
    # The condition bit stays set and the acknowledged bit stays clear —
    # dismissal is not acknowledgement.
    stored = next(m for m in dismissed.messages if m.id == advisory.id)
    assert stored.active is True
    assert stored.acknowledged is False
    # The next transition of its condition re-renders it.
    refired = reduce(reduce(dismissed, AuthorityRegained()), AuthorityLost())
    assert message_visible(refired, advisory.id)


def test_acknowledge_without_authority_is_refused() -> None:
    scene = reduce(psu(), AuthorityLost())
    warning = next(m for m in scene.messages if m.severity == "warning")
    attempted = reduce(scene, AcknowledgeAttempt(warning.id))
    stored = next(m for m in attempted.messages if m.id == warning.id)
    assert stored.acknowledged is False  # refused: not authorised
    # With authority the separately-labelled act succeeds.
    authorised = reduce(psu(), AcknowledgeAttempt(warning.id))
    stored = next(m for m in authorised.messages if m.id == warning.id)
    assert stored.acknowledged is True


def test_acknowledge_control_is_separately_labelled_from_dismiss() -> None:
    rendered = RenderedComponent(compositions.render_workbench(psu()))
    buttons = [element_text(rendered, e) for e in rendered.elements if e.tag == "button"]
    assert any("Acknowledge" in text for text in buttons)
    assert any("Dismiss" in text for text in buttons)
    # Never the same control: no button carries both labels.
    for text in buttons:
        assert not ("Acknowledge" in text and "Dismiss" in text), text


# --- §B.4 through the rendered tile ---------------------------------------------


def test_stale_tile_carries_dimming_attribute_and_marker() -> None:
    scene = stale_voltage_scene(freshness=301.0, max_age=150.0)
    rendered = RenderedComponent(compositions.render_workbench(scene))
    tile = next(
        e
        for e in rendered.elements
        if "bw-reading" in e.class_tokens and e.attrs.get("data-bw-stale") == "true"
    )
    assert "bw-reading--stale" in tile.class_tokens
    markers = rendered.texts_of_elements(class_hook="bw-reading__stale-marker")
    assert any("stale" in marker for marker in markers)


def test_fresh_tile_is_unmarked() -> None:
    scene = stale_voltage_scene(freshness=120.0, max_age=150.0)
    rendered = RenderedComponent(compositions.render_workbench(scene))
    assert not any("data-bw-stale" in e.attrs for e in rendered.elements)
    assert not any(
        "stale" in t for t in rendered.texts_of_elements(class_hook="bw-reading__quality")
    )


def test_no_cadence_renders_no_verdict_anywhere() -> None:
    scene = stale_voltage_scene(freshness=120.0, max_age=None)
    rendered = RenderedComponent(compositions.render_workbench(scene))
    assert not any("data-bw-stale" in e.attrs for e in rendered.elements)
    assert "stale" not in rendered.text_content.lower().replace("staged", "")
    # Even after the reading's source goes quiet (the transition event):
    after = reduce(scene, ReadingWentStale("voltage"))
    rendered_after = RenderedComponent(compositions.render_workbench(after))
    assert not any("data-bw-stale" in e.attrs for e in rendered_after.elements)
    assert after.last_transition == ()


def test_null_freshness_renders_unavailable() -> None:
    scene = stale_voltage_scene(freshness=None, max_age=150.0)
    rendered = RenderedComponent(compositions.render_workbench(scene))
    assert "Unavailable" in rendered.text_content
    assert not any("data-bw-stale" in e.attrs for e in rendered.elements)


def test_device_quality_string_renders_verbatim_with_separate_marker() -> None:
    base = stale_voltage_scene(freshness=301.0, max_age=150.0)
    scene = dataclasses.replace(
        base,
        readings=(dataclasses.replace(base.readings[0], quality="device-good"),),
    )
    rendered = RenderedComponent(compositions.render_workbench(scene))
    quality = rendered.texts_of_elements(class_hook="bw-reading__quality")
    assert any("device-good" in text for text in quality), quality
    markers = rendered.texts_of_elements(class_hook="bw-reading__stale-marker")
    assert markers and "stale" in markers[0]
    # Two channels: the quality string itself never carries the marker text.
    assert "device-goodstale" not in rendered.text_content.replace(" ", "")


def test_table_row_carries_the_stale_arm() -> None:
    scene = stale_voltage_scene(freshness=301.0, max_age=150.0)
    rendered = RenderedComponent(compositions.render_workbench(scene))
    stale_rows = [
        e for e in rendered.elements if e.tag == "tr" and e.attrs.get("data-bw-stale") == "true"
    ]
    assert stale_rows
    assert all("bw-table-row--stale" in e.class_tokens for e in stale_rows)
    assert "stale" in element_text(rendered, stale_rows[0])
    fresh_rows = [
        e for e in rendered.elements if e.tag == "tr" and "data-bw-stale" not in e.attrs
    ]
    for row in fresh_rows:
        assert "stale" not in element_text(rendered, row)


def test_fresh_to_stale_transition_announces_once() -> None:
    scene = stale_voltage_scene(freshness=120.0, max_age=150.0)
    crossed = reduce(scene, ReadingWentStale("voltage"))
    rendered = RenderedComponent(compositions.render_workbench(crossed))
    announcements = rendered.texts_of_elements(class_hook="bw-workbench__announcements")
    assert len(announcements) == 1, announcements
    assert "stale" in announcements[0]
    # Absent on the steady stale re-render and on the duplicate event.
    steady = RenderedComponent(compositions.render_workbench(reduce(crossed, Unrelated())))
    assert steady.texts_of_elements(class_hook="bw-workbench__announcements") == []
    duplicate = RenderedComponent(
        compositions.render_workbench(reduce(crossed, ReadingWentStale("voltage")))
    )
    assert duplicate.texts_of_elements(class_hook="bw-workbench__announcements") == []
