"""The composition state machine (G1d design record §1.1): a reducer over a
frozen workbench state, a scene renderer that composes the G1b partials at
each state, and a fire path that re-evaluates the guards server-side before
any dispatch exists to call — the TS tests' model (injected callbacks,
rerender with mutated fixture) ported with the React runtime replaced by
pure functions.

Import direction keeps UR-11: ``compositions`` → ``partials``/``fixtures``/
``data`` → jinja2 — never pytest. The runtime dep set stays exactly
{jinja2, markupsafe}.

Disclosed honestly: compositions prove the PRESENTATION state machine —
what renders at each state and what the fire path permits. Host wiring
(routes, leases, real run_check/run_start) is G2/G3's seam; nothing here
claims it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from benchweave_ui_html import staleness as staleness_module
from benchweave_ui_html.data import (
    AlertBubbleData,
    ButtonData,
    ConfirmActionData,
    ModeBannerData,
    ModeEntry,
    NumericInputData,
    ReadingData,
    RotaryControlData,
    Severity,
    TableData,
    TableDataRow,
)
from benchweave_ui_html.env import ENV

#: SR-B1's toast restriction is unrepresentable-bad-state, not
#: policy-checked: the transient channel's severity type admits exactly the
#: three confirmation severities (the m7 mutation loosens this Literal and
#: the SR-B1 checker reflects on it).
ToastSeverity = Literal["neutral", "success", "advisory"]

ActionKey = Literal["energise", "set-point", "de-energise"]
ArmableAction = Literal["energise", "set-point"]
ConfirmState = Literal["idle", "armed"]
MessageCondition = Literal["static", "trip", "authority"]


# ---------------------------------------------------------------------------
# The state


@dataclass(frozen=True)
class OutputState:
    """The output's two guard inputs (contract §C.1): ``trip`` disables
    energy-sourcing actions with reason ``protection-active`` (R-PROTECT-1);
    ``energised`` makes a set-point change energy-sourcing (R-ENERGISE-1)."""

    energised: bool
    trip: bool


@dataclass(frozen=True)
class MessageState:
    """One state message: the severity bubble plus the two bits SR-B3
    separates — dismissal (presentation) and acknowledgement (an authorised
    act on the underlying condition, which stays set independently)."""

    id: str
    severity: Severity
    title: str
    text: str
    condition: MessageCondition = "static"
    source: str | None = None
    active: bool = True
    dismissed: bool = False
    acknowledged: bool = False


@dataclass(frozen=True)
class ReadingSlot:
    """One reading with its §B.4 cadence pair: the verdict is COMPUTED from
    ``staleness.staleness(freshness_ms, max_age_ms)`` — never a caller-
    supplied boolean (ST-3's two-channels rule)."""

    id: str
    label: str
    value: str
    unit: str | None
    severity: Severity
    quality: str
    freshness_ms: float | None
    max_age_ms: float | None
    state: Literal["limiting"] | None = None
    set_value: str | None = None
    set_unit: str | None = None

    @property
    def freshness_text(self) -> str:
        """``Unavailable`` when ``freshness_ms`` is null (ST-3), else the
        rendered freshness string."""
        if self.freshness_ms is None:
            return "Unavailable"
        return f"{self.freshness_ms:g} ms"

    def verdict(self) -> staleness_module.StalenessVerdict:
        return staleness_module.staleness(self.freshness_ms, self.max_age_ms)


@dataclass(frozen=True)
class WorkbenchState:
    """The frozen composition state: what renders now, and what the fire
    path would permit. ``last_transition`` is the announcement ledger — the
    reading ids whose fresh→stale crossing the LAST transition announced
    (ST-4: the announcement belongs to the crossing render alone)."""

    device_id: str
    device_title: str
    connected: bool
    lease_owner: str
    lease_expires_s: int
    simulation: bool
    output: OutputState
    authority: bool
    staged_value: float
    confirm: ConfirmState = "idle"
    armed_action: ArmableAction | None = None
    messages: tuple[MessageState, ...] = ()
    readings: tuple[ReadingSlot, ...] = ()
    last_transition: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# The events


@dataclass(frozen=True)
class Arm:
    """The first press of an energy-sourcing control: stages intent only."""

    action: ArmableAction = "energise"


@dataclass(frozen=True)
class Cancel:
    """The confirm subtree's dismissal control."""


@dataclass(frozen=True)
class TripArrives:
    """A protective trip becomes active."""


@dataclass(frozen=True)
class TripClears:
    """The protective trip departs."""


@dataclass(frozen=True)
class AuthorityLost:
    """The controller lease / policy authority is lost."""


@dataclass(frozen=True)
class AuthorityRegained:
    """Authority returns."""


@dataclass(frozen=True)
class ReadingWentStale:
    """Time passes past a reading's read-acceptance window (the model of the
    acquisition going quiet on a polled binding)."""

    reading_id: str


@dataclass(frozen=True)
class DismissMessage:
    message_id: str


@dataclass(frozen=True)
class AcknowledgeAttempt:
    message_id: str


@dataclass(frozen=True)
class Unrelated:
    """Any other state tick: a re-render with nothing changed (SR-B1's
    persistence arm; ST-4's steady-render arm)."""


WorkbenchEvent = (
    Arm
    | Cancel
    | TripArrives
    | TripClears
    | AuthorityLost
    | AuthorityRegained
    | ReadingWentStale
    | DismissMessage
    | AcknowledgeAttempt
    | Unrelated
)


def _refire(messages: tuple[MessageState, ...], condition: str) -> tuple[MessageState, ...]:
    """A condition's messages become active (and re-render even if they were
    previously dismissed — SR-B3's 're-renders on the next transition')."""
    return tuple(
        replace(message, active=True, dismissed=False)
        if message.condition == condition
        else message
        for message in messages
    )


def _settle(messages: tuple[MessageState, ...], condition: str) -> tuple[MessageState, ...]:
    return tuple(
        replace(message, active=False) if message.condition == condition else message
        for message in messages
    )


def _reading_went_stale(
    state: WorkbenchState, reading_id: str
) -> WorkbenchState:
    """The ST-1/ST-3 boundary: a reading with NO commissioned window can
    never cross — the event is a no-op on it (silence never infers staleness
    on a stream-cadence source). A reading already stale does not re-announce
    (coalesced, once)."""
    crossed: list[str] = []
    readings: list[ReadingSlot] = []
    for reading in state.readings:
        if reading.id != reading_id or reading.max_age_ms is None:
            readings.append(reading)
            continue
        bumped = replace(reading, freshness_ms=reading.max_age_ms + 1)
        if reading.verdict() != "stale" and bumped.verdict() == "stale":
            crossed.append(reading.id)
        readings.append(bumped)
    return replace(state, readings=tuple(readings), last_transition=tuple(crossed))


def reduce(state: WorkbenchState, event: WorkbenchEvent) -> WorkbenchState:
    """The pure transition function: an event IS a state transition followed
    by a re-render. Every event other than the crossing itself renders the
    announcement ledger empty (the crossing render announces, once)."""
    if isinstance(event, Arm):
        return replace(state, confirm="armed", armed_action=event.action)
    if isinstance(event, Cancel):
        return replace(state, confirm="idle", armed_action=None)
    if isinstance(event, TripArrives):
        return replace(
            state,
            output=OutputState(state.output.energised, True),
            messages=_refire(state.messages, "trip"),
            last_transition=(),
        )
    if isinstance(event, TripClears):
        return replace(
            state,
            output=OutputState(state.output.energised, False),
            messages=_settle(state.messages, "trip"),
            last_transition=(),
        )
    if isinstance(event, AuthorityLost):
        return replace(
            state,
            authority=False,
            messages=_refire(state.messages, "authority"),
            last_transition=(),
        )
    if isinstance(event, AuthorityRegained):
        return replace(
            state,
            authority=True,
            messages=_settle(state.messages, "authority"),
            last_transition=(),
        )
    if isinstance(event, ReadingWentStale):
        return _reading_went_stale(state, event.reading_id)
    if isinstance(event, DismissMessage):
        # SR-B3: dismissal removes the bubble; the condition bit and the
        # acknowledged bit are untouched (m5's mutant sets acknowledged here
        # and the SR-B3 checker reds).
        return replace(
            state,
            messages=tuple(
                replace(message, dismissed=True)
                if message.id == event.message_id
                else message
                for message in state.messages
            ),
            last_transition=(),
        )
    if isinstance(event, AcknowledgeAttempt):
        if not state.authority:
            # Refused: acknowledgement is an authorised act, never a side
            # effect of anything else — the state is returned unchanged.
            return state
        return replace(
            state,
            messages=tuple(
                replace(message, acknowledged=True)
                if message.id == event.message_id
                else message
                for message in state.messages
            ),
            last_transition=(),
        )
    if isinstance(event, Unrelated):
        # SR-B1 persistence: messages, dismissal and acknowledgement bits
        # survive the re-render; only the announcement ledger clears.
        return replace(state, last_transition=())
    raise TypeError(f"unknown workbench event: {event!r}")


# ---------------------------------------------------------------------------
# The guards and the fire path


#: The guard reasons the workbench renders, with their §C.2 visible labels
#: (the renderer's own knowledge — the TS disabledReasons map's twin; pinned
#: key-by-key against the contract's §C.2 table by the composition tests).
GUARD_LABELS: dict[str, str] = {
    "protection-active": "Protection trip active",
    "no-authority": "No lease or policy authority",
}


def energise_guard(state: WorkbenchState) -> str | None:
    """The energy-sourcing guard (R-PROTECT-1): ``protection-active`` while a
    protective trip is active — the trip is the present blocker, so it wins
    over ``no-authority`` when both hold."""
    if state.output.trip:
        return "protection-active"
    if not state.authority:
        return "no-authority"
    return None


@dataclass(frozen=True)
class Dispatched:
    action: ActionKey
    value: float | None


@dataclass(frozen=True)
class Refused:
    reason: str


FireResult = Dispatched | Refused


def attempt_fire(state: WorkbenchState, action: ActionKey) -> FireResult:
    """The fire path: the operator presses the action's dispatch control NOW,
    and the guards are RE-EVALUATED against ``state`` at fire time — before
    any dispatch callback exists to call (§E.1 confirm-action Notes; m1's
    mutant deletes this re-check and R-PROTECT-1 reds).

    R-DEENERGISE-1: the off action is never confirmed, never gated — nothing
    in the presentation stands between the operator and de-energising (A04).
    """
    if action == "de-energise":
        return Dispatched("de-energise", None)
    guard = energise_guard(state)
    if guard is not None:
        return Refused(guard)
    if action == "set-point" and not state.output.energised:
        # On a de-energised output the staged value is inert: one action,
        # no confirm subtree (R-ENERGISE-1).
        return Dispatched("set-point", state.staged_value)
    if state.confirm != "armed" or state.armed_action != action:
        # The initial control only stages intent; the confirm is a second
        # explicit action.
        return Refused("not-armed")
    return Dispatched(action, state.staged_value)


# ---------------------------------------------------------------------------
# The transient toast channel (SR-B1)


@dataclass(frozen=True)
class ToastData:
    """The transient channel's data: the severity type is the restriction
    (neutral/success/advisory only — warning, critical and trip must remain
    present in the affected context)."""

    severity: ToastSeverity
    text: str


def render_toast(data: ToastData) -> str:
    return ENV.get_template("toast.j2").render(data=data)


# ---------------------------------------------------------------------------
# The canonical scenes (psu-07 / daq-47 — the contract's own invented
# identities, ported from ui/src/compositions/fixtures.ts)


def psu_scene() -> WorkbenchState:
    """The bench-supply scene: three readings (voltage with §E.3 set
    evidence, current in the §B.3 limiting state, power), a staged 12.5 V,
    the margin warning plus the authority advisory, output energised."""
    return WorkbenchState(
        device_id="psu-07",
        device_title="Bench supply",
        connected=True,
        lease_owner="bench-operator@example.invalid",
        lease_expires_s=120,
        simulation=True,
        output=OutputState(energised=True, trip=False),
        authority=True,
        staged_value=12.5,
        messages=(
            MessageState(
                id="margin",
                severity="warning",
                title="Operating margin",
                text="Current approaching configured limit",
                condition="static",
                source="PSU-07 · current",
            ),
            MessageState(
                id="lease-note",
                severity="advisory",
                title="Controller lease",
                text="Lease renews shortly; actions re-authorise on renewal",
                condition="authority",
            ),
        ),
        readings=(
            ReadingSlot(
                id="voltage",
                label="Voltage",
                value="12.04",
                unit="V",
                severity="success",
                quality="Verified",
                freshness_ms=120.0,
                max_age_ms=150.0,
                set_value="12.5",
                set_unit="V",
            ),
            ReadingSlot(
                id="current",
                label="Current",
                value="1.92",
                unit="A",
                severity="success",
                quality="Near limit",
                freshness_ms=120.0,
                max_age_ms=150.0,
                state="limiting",
            ),
            ReadingSlot(
                id="power",
                label="Power",
                value="23.1",
                unit="W",
                severity="success",
                quality="Verified",
                freshness_ms=120.0,
                max_age_ms=150.0,
            ),
        ),
    )


def daq_scene() -> WorkbenchState:
    """The multi-channel logger scene: four channel readings plus the
    excitation on/off reading (a unitless value), staged 5 V."""
    return WorkbenchState(
        device_id="daq-47",
        device_title="Multi-channel logger",
        connected=True,
        lease_owner="bench-operator@example.invalid",
        lease_expires_s=120,
        simulation=True,
        output=OutputState(energised=True, trip=False),
        authority=True,
        staged_value=5.0,
        messages=(
            MessageState(
                id="margin",
                severity="warning",
                title="Operating margin",
                text="Excitation output within the commissioned envelope",
                condition="static",
                source="DAQ-47 · excitation",
            ),
        ),
        readings=(
            ReadingSlot(
                id="ch1",
                label="Channel 1",
                value="4.98",
                unit="V",
                severity="success",
                quality="Verified",
                freshness_ms=95.0,
                max_age_ms=150.0,
            ),
            ReadingSlot(
                id="ch2",
                label="Channel 2",
                value="1.02",
                unit="V",
                severity="success",
                quality="Verified",
                freshness_ms=95.0,
                max_age_ms=150.0,
            ),
            ReadingSlot(
                id="excitation",
                label="Excitation",
                value="On",
                unit=None,
                severity="success",
                quality="Verified",
                freshness_ms=95.0,
                max_age_ms=None,  # stream-cadence: no window, no verdict (ST-1)
            ),
        ),
    )


# ---------------------------------------------------------------------------
# The scene renderer


def _reading_tile(reading: ReadingSlot) -> ReadingData:
    return ReadingData(
        label=reading.label,
        severity=reading.severity,
        value=reading.value,
        unit=reading.unit or "",
        quality=reading.quality,
        freshness=reading.freshness_text,
        state=reading.state,
        state_label=reading.state.capitalize() if reading.state else None,
        set_value=reading.set_value,
        set_unit=reading.set_unit,
        stale_verdict=reading.verdict(),
    )


@dataclass(frozen=True)
class _MessageBubble:
    """One rendered message: the alert-bubble partial's data plus the
    composition-level Acknowledge control flag (SR-B3: acknowledgement is a
    separately labelled act; the bubble's own Dismiss serves the dismissible
    severities only)."""

    data: AlertBubbleData
    acknowledge: bool
    title: str


@dataclass(frozen=True)
class _Announcement:
    reading_id: str
    text: str


@dataclass(frozen=True)
class _WorkbenchView:
    device_id: str
    device_title: str
    connected: bool
    lease_owner: str
    lease_expires_s: int
    mode_banner: ModeBannerData
    announcements: tuple[_Announcement, ...]
    tiles: tuple[ReadingData, ...]
    bubbles: tuple[_MessageBubble, ...]
    rotary: RotaryControlData
    numeric: NumericInputData
    setpoint_confirm: ConfirmActionData | None
    setpoint_button: ButtonData
    energise: ConfirmActionData
    deenergise: ButtonData
    table: TableData


def _message_bubble(message: MessageState) -> _MessageBubble:
    return _MessageBubble(
        data=AlertBubbleData(
            severity=message.severity,
            title=message.title,
            message=message.text,
            live_region="alert" if message.severity in ("critical", "trip") else "status",
            dismissible=message.severity in ("neutral", "success", "advisory"),
            source=message.source,
            aria_label=message.title,
        ),
        acknowledge=message.severity == "warning",
        title=message.title,
    )


def _channels_table(state: WorkbenchState) -> TableData:
    rows = []
    for reading in state.readings:
        verdict = reading.verdict()
        quality = f"{reading.quality} · {reading.freshness_text}"
        if verdict == "stale":
            quality = f"{quality} · stale"
        rows.append(
            TableDataRow(
                key=reading.id,
                cells=(
                    reading.label,
                    f"{reading.value} {reading.unit}" if reading.unit else reading.value,
                    quality,
                ),
                stale=verdict == "stale",
            )
        )
    return TableData(
        caption="Channel readings",
        headers=("Quantity", "Reading", "Quality"),
        rows=tuple(rows),
    )


def render_workbench(state: WorkbenchState) -> str:
    """Render the workbench scene at ``state`` — the G1b partials composed
    by ``workbench.j2`` over the mode banner, the announcement ledger, the
    readings grid, the anchored message panel, the output-control panel and
    the channels table."""
    guard = energise_guard(state)
    guard_label = GUARD_LABELS[guard] if guard is not None else None
    staged = f"{state.staged_value:g}"
    target = f"{state.device_id.upper()} output"
    banner = ModeBannerData(
        modes=(
            (ModeEntry("simulated", "SIMULATED PRESENTATION DATA"),)
            if state.simulation
            else ()
        )
    )
    labels = {reading.id: reading.label for reading in state.readings}
    view = _WorkbenchView(
        device_id=state.device_id.upper(),
        device_title=state.device_title,
        connected=state.connected,
        lease_owner=state.lease_owner,
        lease_expires_s=state.lease_expires_s,
        mode_banner=banner,
        announcements=tuple(
            _Announcement(
                reading_id=reading_id,
                text=f"{labels.get(reading_id, reading_id)} reading went stale",
            )
            for reading_id in state.last_transition
        ),
        tiles=tuple(_reading_tile(reading) for reading in state.readings),
        bubbles=tuple(
            _message_bubble(message)
            for message in state.messages
            if message.active and not message.dismissed
        ),
        rotary=RotaryControlData(
            label="Voltage set-point", now=staged, minimum="0", maximum="24", unit="V"
        ),
        numeric=NumericInputData(
            label="Precise voltage",
            unit="V",
            value=staged,
            minimum="0",
            maximum="24",
            step="0.1",
        ),
        setpoint_confirm=(
            ConfirmActionData(
                initial_label="Apply staged set-point",
                armed=state.confirm == "armed" and state.armed_action == "set-point",
                armed_text=(
                    "the set-point of the energised output will change: "
                    f"{staged} V to {target}. Confirm to proceed."
                ),
                confirm_label="Apply staged set-point",
                guard_reason=guard,
                guard_label=guard_label,
            )
            if state.output.energised
            else None
        ),
        setpoint_button=ButtonData(
            label="Apply staged set-point",
            variant="primary",
            disabled_reason=guard,
            disabled_label=guard_label,
        ),
        energise=ConfirmActionData(
            initial_label="Energise output",
            armed=state.confirm == "armed" and state.armed_action == "energise",
            armed_text=(
                f"the output will be energised: {staged} V to {target}. Confirm to proceed."
            ),
            confirm_label="Energise output",
            guard_reason=guard,
            guard_label=guard_label,
        ),
        deenergise=ButtonData(label="De-energise output", variant="destructive"),
        table=_channels_table(state),
    )
    return ENV.get_template("workbench.j2").render(view=view)


__all__ = [
    "AcknowledgeAttempt",
    "ActionKey",
    "Arm",
    "AuthorityLost",
    "AuthorityRegained",
    "Cancel",
    "Dispatched",
    "DismissMessage",
    "FireResult",
    "GUARD_LABELS",
    "MessageState",
    "OutputState",
    "ReadingSlot",
    "ReadingWentStale",
    "Refused",
    "ToastData",
    "ToastSeverity",
    "TripArrives",
    "TripClears",
    "Unrelated",
    "WorkbenchEvent",
    "WorkbenchState",
    "attempt_fire",
    "daq_scene",
    "energise_guard",
    "psu_scene",
    "reduce",
    "render_toast",
    "render_workbench",
]
