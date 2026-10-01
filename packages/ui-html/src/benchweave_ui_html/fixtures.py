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

from typing import cast

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
from benchweave_ui_html.decimate import LaneState
from benchweave_ui_html.lanes import (
    ComposedLanes,
    Cursor,
    DecoderEvent,
    LanesDeclaration,
    LaneSpec,
    compose_lanes,
)
from benchweave_ui_html.plot import (
    ChannelHint,
    ComposedPlot,
    ReferenceLine,
    ThresholdLine,
    TraceSpec,
    compose_plot,
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


# --- §E.1 engineering-plot: the canonical 100→2 voltage decimation ---------------


def engineering_plot() -> ComposedPlot:
    """§E.1 ``engineering-plot``: the canonical fixture — the voltage trace
    decimated 100→2 (derived provenance so the marked-kind attribute
    renders), the reference channel presentation-hidden (the hidden-marker
    wording and aria-label), one unit (V)."""
    return compose_plot(
        title="Supply rail",
        description=(
            "Supply rail voltage over the acquisition window; the reference "
            "channel is hidden by presentation preference."
        ),
        traces=(
            TraceSpec(
                "voltage",
                "V",
                samples=(0.0, 12.5),
                provenance="derived",
                derivation="rail ÷ divider ratio",
            ),
            TraceSpec("voltage-ref", "V", samples=(0.0, 0.0)),
        ),
        hints={"voltage-ref": ChannelHint(visible=False)},
        acquired=100,
    )


def slots16_plot() -> ComposedPlot:
    """§E.2.1's canonical 16-id declared set — the uniqueness-at-the-ceiling
    fixture (16 distinct colour/dash and symbol/dash pairs)."""
    return compose_plot(
        title="Sixteen channels",
        description="Sixteen declared channels, all visible.",
        traces=tuple(
            TraceSpec(f"ch-{index:02d}", "V", samples=(0.0, 1.0)) for index in range(16)
        ),
        hints={},
        acquired=2,
    )


def hint_accent_loses_plot() -> ComposedPlot:
    """§E.2.0 accent, the losing case: pass-1 slot 1 among visible traces is
    the FIRST claim, so the accent hint on the second channel loses
    silently and keeps its slot colour."""
    return compose_plot(
        title="Accent loses",
        description="An accent hint on a non-slot-1 channel loses to slot 1.",
        traces=(TraceSpec("alpha", "V"), TraceSpec("beta", "V")),
        hints={"beta": ChannelHint(color_role="accent")},
    )


def hint_accent_wins_plot() -> ComposedPlot:
    """§E.2.0 accent, the winning case: slot 1 is hidden (its claim
    released) — among visible traces hinting accent, the earliest in trace
    order wins the emphasis; the other reverts to its slot colour."""
    return compose_plot(
        title="Accent wins",
        description="With slot 1 hidden, the earliest visible accent hint wins.",
        traces=(TraceSpec("alpha", "V"), TraceSpec("beta", "V"), TraceSpec("gamma", "V")),
        hints={
            "alpha": ChannelHint(visible=False),
            "beta": ChannelHint(color_role="accent"),
            "gamma": ChannelHint(color_role="accent"),
        },
    )


def hint_muted_plot(*, theme_resolves_muted: bool = True) -> ComposedPlot:
    """§E.2.0 muted: the hinted channel repaints ``--bw-text-muted`` and
    releases its emphasis claim (no cascade — the sibling keeps series-2,
    never promoted to series-1); the token-less fallback keeps the slot
    colour (which still claims if it is slot 1)."""
    return compose_plot(
        title="Muted",
        description="A muted hint repaints and releases the emphasis claim.",
        traces=(TraceSpec("alpha", "V"), TraceSpec("beta", "V")),
        hints={"alpha": ChannelHint(color_role="muted")},
        theme_resolves_muted=theme_resolves_muted,
    )


def hint_hidden_plot() -> ComposedPlot:
    """§E.2.0 ``visible: false``: the hidden channel's SLOT never moves —
    styles resolve over the full declared set before visibility filters, so
    hiding never restyles its siblings."""
    return compose_plot(
        title="Hidden channel",
        description="The middle channel is hidden; no sibling is restyled.",
        traces=(TraceSpec("alpha", "V"), TraceSpec("beta", "V"), TraceSpec("gamma", "V")),
        hints={"beta": ChannelHint(visible=False)},
    )


def no_hint_plot() -> ComposedPlot:
    """§E.2.0 ``(no hint)``: both channels keep their §E.2.1 slot facts."""
    return compose_plot(
        title="No hints",
        description="Two channels, no hints.",
        traces=(TraceSpec("alpha", "V"), TraceSpec("beta", "V")),
        hints={},
    )


# --- §E.2.3 y-axis fixtures --------------------------------------------------------


def one_unit_plot() -> ComposedPlot:
    """§E.2.3 one distinct unit: trimmed-unit grouping makes ``V`` and
    `` V`` ONE unit; a single axis named with the unit. The unitless
    sub-fixture lives in ``unitless_plot``."""
    return compose_plot(
        title="One unit",
        description="Three voltage traces; one y-axis named V.",
        traces=(TraceSpec("v1", "V"), TraceSpec("v2", "V"), TraceSpec("v3", " V")),
        hints={},
    )


def unitless_plot() -> ComposedPlot:
    """§E.2.3 the unitless group: a unit empty after trimming is a legal
    single group whose axis renders unnamed."""
    return compose_plot(
        title="Unitless",
        description="Two unitless traces; one unnamed axis.",
        traces=(TraceSpec("n1", ""), TraceSpec("n2", "  ")),
        hints={},
    )


def two_unit_plot() -> ComposedPlot:
    """§E.2.3 two distinct units: first-declaration order (axis 1 = the
    earliest declared trace's unit), every trace on its own unit's axis."""
    return compose_plot(
        title="Two units",
        description="Voltage and current; two named y-axes.",
        traces=(TraceSpec("voltage", "V"), TraceSpec("current", "A")),
        hints={},
    )


def three_unit_refusal_plot() -> ComposedPlot:
    """§E.2.3 more than two distinct units: the plot draws NO traces and
    renders the refusal note (the manifest admits the declaration)."""
    return compose_plot(
        title="Three units",
        description="V, A and W declared; the plot refuses.",
        traces=(TraceSpec("voltage", "V"), TraceSpec("current", "A"), TraceSpec("power", "W")),
        hints={},
    )


def hidden_axis_plot() -> ComposedPlot:
    """§E.2.3 the fourth condition: every trace bound to an axis is
    presentation-hidden ⇒ that axis does not render; the surviving trace's
    binding is remapped onto the surviving axis (renumbered, never
    reshuffled)."""
    return compose_plot(
        title="Hidden axis",
        description="The voltage axis's only trace is hidden; the current axis survives.",
        traces=(TraceSpec("voltage", "V"), TraceSpec("current", "A")),
        hints={"voltage": ChannelHint(visible=False)},
    )


# --- §E.2.4 reference lines ---------------------------------------------------------


def reference_line_plot() -> ComposedPlot:
    """§E.2.4: a reference line (meaning · value · unit, border token,
    dotted, on its own unit's axis) beside a severity threshold (severity
    hue, dashed) — the distinctness fixture."""
    return compose_plot(
        title="Reference lines",
        description="A current-limit reference line and a warning threshold.",
        traces=(TraceSpec("voltage", "V"), TraceSpec("current", "A", samples=(0.0, 1.0))),
        hints={},
        ref_lines=(ReferenceLine("Current limit", "2", "A", ("current",)),),
        thresholds=(ThresholdLine("warning", "1.5", "A"),),
    )


def reference_line_hidden_target_plot() -> ComposedPlot:
    """§E.2.4 Carrier: the reference line's only target trace is
    presentation-hidden and the line STILL renders (hiding data must not
    launder away a configured limit)."""
    return compose_plot(
        title="Carrier",
        description="The current channel is hidden; the limit line remains.",
        traces=(TraceSpec("voltage", "V"), TraceSpec("current", "A")),
        hints={"current": ChannelHint(visible=False)},
        ref_lines=(ReferenceLine("Current limit", "2", "A", ("current",)),),
    )


# --- §E.2.5 acquisition fixtures ------------------------------------------------------


def acquisition_decimated_plot() -> ComposedPlot:
    """§E.2.5 when required: a VISIBLE trace draws 2 of 100 acquired — the
    disclosure renders with the computed drawn count."""
    return compose_plot(
        title="Decimated",
        description="A visible trace decimated 100 to 2.",
        traces=(TraceSpec("voltage", "V", samples=(0.0, 12.5)),),
        hints={},
        acquired=100,
    )


def acquisition_not_required_plot() -> ComposedPlot:
    """§E.2.5 the negative arm: the visible trace drew everything it
    acquired (3 of 3), and only a HIDDEN trace is decimated — hidden traces
    draw nothing, so they disclose nothing; no disclosure renders."""
    return compose_plot(
        title="Nothing to disclose",
        description="The visible trace is undecimated; the hidden one drew 2 of 3.",
        traces=(
            TraceSpec("voltage", "V", samples=(0.0, 1.0, 2.0)),
            TraceSpec("reference", "V", samples=(0.0, 1.0)),
        ),
        hints={"reference": ChannelHint(visible=False)},
        acquired=3,
    )


# --- §E.2.6 provenance fixtures --------------------------------------------------------


def provenance_plot() -> ComposedPlot:
    """§E.2.6: one trace per kind — measured (neither attribute nor marker),
    derived (the §8 structural unknown rendered), device-averaged (the
    applied depth from the observed echo — 8, a fixture-documented echo
    value, never a default), display-processed (with its source trace still
    rendered in the same plot)."""
    return compose_plot(
        title="Provenance",
        description="One trace per provenance kind.",
        traces=(
            TraceSpec("measured-rail", "V"),
            TraceSpec(
                "derived-rail",
                "V",
                provenance="derived",
                derivation="rail ÷ divider ratio",
            ),
            TraceSpec(
                "averaged-rail",
                "V",
                provenance="device-averaged",
                averaging_depth=8,
            ),
            TraceSpec(
                "smoothed-rail",
                "V",
                provenance="display-processed",
                processing_name="moving-average",
                processing_window="100 ms",
            ),
            TraceSpec("smoothed-rail-source", "V"),
        ),
        hints={},
    )


# --- §E.1 digital-lanes: the canonical 1000→12 capture at 1 MHz -------------------


def _clk_states() -> tuple[LaneState, ...]:
    """1000 samples alternating fast enough that most drawn columns cover
    more than one transition (the glitch-mark fixture)."""
    return cast(
        tuple[LaneState, ...], tuple("10"[index % 2] for index in range(1000))
    )


def _data_states() -> tuple[LaneState, ...]:
    """1 … x … 0 … z — the four-state fixture (§E.4.2)."""
    return cast(
        tuple[LaneState, ...],
        (("1",) * 300) + (("x",) * 200) + (("0",) * 300) + (("z",) * 200),
    )


def digital_lanes() -> ComposedLanes:
    """§E.1 ``digital-lanes``: the canonical capture — 1000 samples drawn
    as 12 columns at 1 MHz (the contract's own canonical literals), with a
    glitch-bearing clock, the four-state data channel, a bus group, a
    decoder with in-window / fully-outside / zero-width events, a hidden
    channel, a no-events decoder lane (the awaiting-render note), a
    non-null trigger and two cursors 7 µs apart."""
    return compose_lanes(
        LanesDeclaration(
            title="Logic capture",
            description=(
                "A 1000-sample capture drawn as 12 columns at 1 MHz; the "
                "auxiliary channel is hidden by presentation preference."
            ),
            lanes=(
                LaneSpec(0, "channel", "clk", states=_clk_states()),
                LaneSpec(1, "channel", "data", states=_data_states()),
                LaneSpec(
                    2,
                    "group",
                    "bus[1:0]",
                    members=("data", "aux"),
                    bit_width=2,
                ),
                LaneSpec(
                    3,
                    "decoder",
                    "UART-REF · 115200 8N1",
                    source_channel="data",
                    events=(
                        DecoderEvent(0.0001, 0.0002, "0x55"),
                        DecoderEvent(0.0004, 0.0005, "0xAA"),
                        DecoderEvent(0.0030, 0.0031, "0xFF"),  # fully outside
                        DecoderEvent(0.0006, 0.0006, "0x00"),  # zero-width
                    ),
                ),
                LaneSpec(
                    4,
                    "channel",
                    "aux",
                    states=cast(
                        tuple[LaneState, ...], tuple("0" for _ in range(1000))
                    ),
                    hidden=True,
                ),
                LaneSpec(5, "decoder", "CRC · poly 0x31", source_channel="clk"),
            ),
            acquired=1000,
            columns=12,
            axis_label="Capture time",
            axis_unit="s",
            sample_rate_hz=1_000_000.0,
            trigger_s=0.0005,
            cursors=(Cursor(0.0002), Cursor(0.000207)),
        ),
        member_states={
            "clk": _clk_states(),
            "data": _data_states(),
            "aux": cast(tuple[LaneState, ...], tuple("0" for _ in range(1000))),
        },
    )


def bus_member_order_lanes(*, swapped: bool = False) -> ComposedLanes:
    """§E.4.3 Member order: lo stable-1 and hi stable-0, grouped (lo, hi) —
    the first declared member is the LSB, so (lo, hi) renders 1 and the
    swapped declaration renders 2 (bus values are a pure function of member
    states and member order)."""
    stable_lo = cast(tuple[LaneState, ...], tuple("1" for _ in range(24)))
    stable_hi = cast(tuple[LaneState, ...], tuple("0" for _ in range(24)))
    members = ("hi", "lo") if swapped else ("lo", "hi")
    return compose_lanes(
        LanesDeclaration(
            title="Bus order",
            description="Two stable channels on one bus lane.",
            lanes=(
                LaneSpec(0, "channel", "lo", states=stable_lo),
                LaneSpec(1, "channel", "hi", states=stable_hi),
                LaneSpec(2, "group", "bus", members=members, bit_width=2),
            ),
            acquired=24,
            columns=4,
            axis_label="Samples",
            axis_unit="samples",
        ),
        member_states={"lo": stable_lo, "hi": stable_hi},
    )


def bus_decimal_lanes() -> ComposedLanes:
    """§E.4.3 Radix: the per-group decimal opt-in."""
    stable = cast(tuple[LaneState, ...], tuple("1" for _ in range(24)))
    return compose_lanes(
        LanesDeclaration(
            title="Bus decimal",
            description="A decimal bus.",
            lanes=(
                LaneSpec(0, "channel", "lo", states=stable),
                LaneSpec(1, "channel", "hi", states=stable),
                LaneSpec(2, "group", "bus", members=("lo", "hi"), bit_width=2, radix="decimal"),
            ),
            acquired=24,
            columns=4,
            axis_label="Samples",
            axis_unit="samples",
        ),
        member_states={"lo": stable, "hi": stable},
    )


def null_trigger_lanes() -> ComposedLanes:
    """§E.4.5 Trigger, the null arm: a null trigger renders no marker and
    no position is fabricated."""
    stable = cast(tuple[LaneState, ...], tuple("1" for _ in range(24)))
    return compose_lanes(
        LanesDeclaration(
            title="No trigger",
            description="A capture with no trigger.",
            lanes=(LaneSpec(0, "channel", "clk", states=stable),),
            acquired=24,
            columns=4,
            axis_label="Samples",
            axis_unit="samples",
        ),
    )


def sample_mode_cursor_lanes() -> ComposedLanes:
    """§E.4.5 Cursors, sample-index mode: the raw difference in the host's
    unit — ``Δt = 7 samples``, never alongside the scaled form."""
    stable = cast(tuple[LaneState, ...], tuple("1" for _ in range(100)))
    return compose_lanes(
        LanesDeclaration(
            title="Sample cursors",
            description="Two cursors seven samples apart.",
            lanes=(LaneSpec(0, "channel", "clk", states=stable),),
            acquired=100,
            columns=4,
            axis_label="Samples",
            axis_unit="samples",
            sample_rate_hz=1_000_000.0,
            cursors=(Cursor(0.000010), Cursor(0.000017)),
        ),
    )


def hidden_source_decoder_lanes() -> ComposedLanes:
    """§E.4.6 Never orphan: the decoder's source channel is hidden — the
    events render nothing, orphan onto no neighbour, and the row discloses
    the wait visibly."""
    stable = cast(tuple[LaneState, ...], tuple("1" for _ in range(100)))
    return compose_lanes(
        LanesDeclaration(
            title="Hidden source",
            description="The decode source is hidden; the row waits.",
            lanes=(
                LaneSpec(0, "channel", "data", states=stable, hidden=True),
                LaneSpec(
                    1,
                    "decoder",
                    "UART-REF · 115200 8N1",
                    source_channel="data",
                    events=(DecoderEvent(0.00001, 0.00002, "0x55"),),
                ),
            ),
            acquired=100,
            columns=4,
            axis_label="Samples",
            axis_unit="samples",
            sample_rate_hz=1_000_000.0,
        ),
    )
