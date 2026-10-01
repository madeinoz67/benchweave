"""Plain-data component models (UR-01: "plain data, never host objects").

One frozen dataclass per component family; the renderers (``partials.py``)
take these in and emit HTML strings. Closed enumerations are ``Literal``
aliases so a bad state is unrepresentable rather than validated at render
time — the values are the contract's own keys (§B.1 severities, §E.1 button
variants, §C.2 disabled reasons).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: §B.1 severity keys (the closed enum; renderers use names, never colour alone).
Severity = Literal["neutral", "success", "advisory", "warning", "critical", "trip"]

#: §E.1 button row Notes: the five variants.
ButtonVariant = Literal["primary", "secondary", "tertiary", "destructive", "protective"]


@dataclass(frozen=True)
class ButtonData:
    """§E.1 ``button``: a native button with its variant and busy state.

    ``disabled_reason``/``disabled_label`` carry §C.2's disabled-reason
    shape (the visible label renders beside the control, never aria-only);
    both ``None`` for an enabled canonical fixture.
    """

    label: str
    variant: ButtonVariant = "primary"
    busy: bool = False
    disabled_reason: str | None = None
    disabled_label: str | None = None


#: §D.1 mode keys (the fixed banner order).
ModeKey = Literal["simulated", "no-gateway", "no-lease", "no-policy"]

#: §E.1 panel row: ``data-surface`` values.
SurfaceKind = Literal["raised", "recessed"]

#: §B.3 reading states (``limiting`` is the one key the table pins).
ReadingState = Literal["limiting"]

#: §B.1 live regions: ``alert`` for critical/trip, else ``status``.
LiveRegion = Literal["status", "alert"]


@dataclass(frozen=True)
class NumericInputData:
    """§E.1 ``numeric-input``: labelled number field with bounds and staged help."""

    label: str
    unit: str
    value: str
    minimum: str
    maximum: str
    step: str
    input_id: str = "bw-numeric-field"
    help_id: str = "bw-numeric-help"
    help_text: str = "Staged value; use Apply to request the change"


@dataclass(frozen=True)
class RotaryControlData:
    """§E.1 ``rotary-control``: a dial that stages intent; ``aria-valuetext``
    reads "``{value} {unit}``, staged" (the row's contains-item)."""

    label: str
    now: str
    minimum: str
    maximum: str
    unit: str


@dataclass(frozen=True)
class ReadingData:
    """§E.1 ``reading-tile``: value, unit, quality line, and — per the row's
    Notes — the optional §B.3 state and §E.3 set evidence the canonical
    fixture renders WITH (the all-modes precedent)."""

    label: str
    severity: Severity
    value: str
    unit: str
    quality: str = "steady"
    freshness: str = "2 s"
    state: ReadingState | None = None
    state_label: str | None = None
    set_value: str | None = None
    set_unit: str | None = None


@dataclass(frozen=True)
class AlertBubbleData:
    """§E.1 ``alert-bubble`` + §B.1 rows: severity, live region, dismissal."""

    severity: Severity
    title: str
    message: str
    live_region: LiveRegion = "status"
    dismissible: bool = True
    source: str | None = None
    aria_label: str | None = None


@dataclass(frozen=True)
class PanelData:
    """§E.1 ``panel``: surface, title, optional eyebrow, body lines."""

    title: str
    surface: SurfaceKind = "raised"
    label: str | None = None
    eyebrow: str | None = None
    body: tuple[str, ...] = ()


@dataclass(frozen=True)
class TableDataRow:
    key: str
    cells: tuple[str, ...]


@dataclass(frozen=True)
class TableData:
    """§E.1 ``data-table``: caption, scoped column headers, stable row keys."""

    caption: str
    headers: tuple[str, ...]
    rows: tuple[TableDataRow, ...]


@dataclass(frozen=True)
class ModeEntry:
    """One §D.1 banner entry: the mode key and its fixed wording."""

    key: ModeKey
    wording: str


@dataclass(frozen=True)
class ModeBannerData:
    """§E.1 ``mode-banner``: the entries, in §D.1's fixed order (the canonical
    fixture carries all four — the all-modes precedent)."""

    modes: tuple[ModeEntry, ...]


@dataclass(frozen=True)
class ConfirmActionData:
    """§E.1 ``confirm-action``: the armed confirm-step pattern (§C.1
    R-ENERGISE-1's presentation shape; the guard-at-fire-time behaviour is
    G1d's, this is the structural row)."""

    initial_label: str
    armed: bool
    armed_text: str
    confirm_label: str


@dataclass(frozen=True)
class RefusalData:
    """§C.3 rows: the code's severity, what-happened text, sent status
    (``UNKNOWN`` for ``no-response`` — decision A06), and operator action."""

    code: str
    severity: Severity
    what_happened: str
    sent_status: str
    operator_action: str


@dataclass(frozen=True)
class DisabledLabelData:
    """§C.2 rows: the disabled-reason key and its required visible label."""

    reason: str
    label: str
