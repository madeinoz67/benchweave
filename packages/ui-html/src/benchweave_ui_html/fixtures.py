"""The canonical fixtures (G1b design record §1.1): one instance per row's
needs, values taken from the contract's own canonical literals.

The contract rows are normative and the fixtures follow them: §E.1's Notes
carry the canonical values (reading-tile quality ``steady`` freshness
``2 s``; confirm-action's exact armed literals incl. ``PSU-07 output``; the
plot 100→2 voltage decimation; the lanes 1000→12 capture at 1 MHz), and
§E.2.6/§E.4.6 name their canonical markers (``UART-REF · 115200 8N1``).
The React compositions are semantic reference only — the rows are the
authority (design record O3).
"""

from __future__ import annotations

from benchweave_ui_html.data import (
    AlertBubbleData,
    ButtonData,
    ConfirmActionData,
    ModeBannerData,
    ModeEntry,
    NumericInputData,
    PanelData,
    ReadingData,
    RotaryControlData,
    TableData,
    TableDataRow,
)


def button() -> ButtonData:
    """§E.1 ``button``: an enabled primary button with a text label (the
    Notes column: destructive/protective always carry a text label — the
    canonical fixture is primary, also labelled)."""
    return ButtonData(label="Energise output", variant="primary", busy=False)


def numeric_input() -> NumericInputData:
    """§E.1 ``numeric-input``: the canonical staged-value field."""
    return NumericInputData(
        label="Supply voltage", unit="V", value="12.5", minimum="0", maximum="24", step="0.1"
    )


def rotary_control() -> RotaryControlData:
    """§E.1 ``rotary-control``: the canonical dial, mid-range, staged."""
    return RotaryControlData(
        label="Supply voltage", now="12.5", minimum="0", maximum="24", unit="V"
    )


def reading() -> ReadingData:
    """§E.1 ``reading-tile``: the canonical tile WITH the §B.3 limiting state
    and the §E.3 set evidence (the row's Notes: the enforcement fixture
    renders the canonical tile WITH the state and set evidence — the
    mode-banner all-modes precedent). Quality ``steady``, freshness ``2 s``
    are the contract's own canonical literals; the set value is a documented
    fixture choice (the contract pins the ``Set {value} {unit}`` shape, not
    the value)."""
    return ReadingData(
        label="Supply voltage",
        severity="neutral",
        value="12.5",
        unit="V",
        state="limiting",
        state_label="Limiting",
        set_value="12.0",
        set_unit="V",
    )


def reading_without_state() -> ReadingData:
    """The §E.3 measured-role fixture: the plain tile, no state, no set line
    (the mutation control for ``data-bw-reading-state`` constructs the state
    dropped; this is the plain measured shape)."""
    return ReadingData(
        label="Supply voltage", severity="neutral", value="12.5", unit="V"
    )


def alert_bubble() -> AlertBubbleData:
    """§E.1 ``alert-bubble``: a dismissible advisory (the row requires the
    dismiss affordance's ``aria-label="Dismiss"``, so the canonical §E.1
    fixture is a dismissible severity)."""
    return AlertBubbleData(
        severity="advisory",
        title="Configuration note",
        message="Profile values were loaded from the staged descriptor.",
        live_region="status",
        dismissible=True,
        source="settings",
        aria_label="Advisory",
    )


def panel() -> PanelData:
    """§E.1 ``panel``: a raised actionable group with the optional eyebrow."""
    return PanelData(
        title="Output group",
        surface="raised",
        eyebrow="Channel A",
        body=("Two outputs are available in this group.",),
    )


def data_table() -> TableData:
    """§E.1 ``data-table``: a small table with caption and stable row keys."""
    return TableData(
        caption="Recent observations",
        headers=("Parameter", "Value", "Unit"),
        rows=(
            TableDataRow("obs-1", ("Supply voltage", "12.5", "V")),
            TableDataRow("obs-2", ("Current",  "0.8", "A")),
        ),
    )


MODES: tuple[ModeEntry, ...] = (
    ModeEntry("simulated", "SIMULATED PRESENTATION DATA"),
    ModeEntry("no-gateway", "NO GATEWAY · LOCAL PRESENTATION ONLY"),
    ModeEntry("no-lease", "NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED"),
    ModeEntry("no-policy", "NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE"),
)


def mode_banner() -> ModeBannerData:
    """§E.1 ``mode-banner``: the all-modes banner (the enforcement fixture
    renders all four; a page renders only its active modes). Wordings are
    §D.1's fixed literals — the §D.1 rows assert them from their own cells,
    so any contract edit reds those rows before this fixture could drift."""
    return ModeBannerData(modes=MODES)


def confirm_action() -> ConfirmActionData:
    """§E.1 ``confirm-action``: the armed canonical fixture carrying the
    contract's own literals — effect ``the output will be energised``, value
    ``12.5 V``, target ``PSU-07 output`` (the contract's canonical invented
    name), confirm ``Confirm: Energise output``, dismissal ``Cancel``."""
    return ConfirmActionData(
        initial_label="Energise output",
        armed=True,
        armed_text="the output will be energised: 12.5 V to PSU-07 output. Confirm to proceed.",
        confirm_label="Energise output",
    )
