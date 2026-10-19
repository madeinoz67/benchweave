"""The class-reference pattern pages (Landing 3 of the class-reference
program; gateway issues #462 rows 1-2; design record §7 Landing 3, §7A L3;
the L11 output page per the 2026-10-18 dc_psu design record).

The class-page pattern-library compositions are built from the §E.1
partials the renderer already ships: host composition, no renderer
change, no new contract rows (the record's §2.6 rule). The §E.1
partials, templates and the contract harness are untouched by any of
the slices; the class-page composers now number five (analyser,
dc_psu, dmm, oscilloscope, function_generator).

RENDER-TIME EXPANSION (disclosed): the production expander is Landing 2's,
unreleased at this slice. The analyser page's data was produced by a
throwaway render-time expansion of the committed corpus pair —
standards/plugin-ui-class-reference/0.3.0/class-logic_analyser.json
expanded against standards/otdp/0.2.3/examples/class-logic_analyser.json —
and the module is the committed artifact. The dc_psu output page (L11)
follows the same shape against
standards/plugin-ui-class-reference/0.3.0/class-dc_psu.json ×
standards/otdp/0.2.3/examples/class-dc_psu.json; the dmm readings page
(L12) against class-dmm.json × class-dmm.json — the third composer, the
observation-pure class (design record 2026-10-19). For every class page,
a corpus edit reddens the drift guards (tests/ui_html/
test_classref_dc_psu.py, test_classref_dmm.py) until the page data is
regenerated, with the mockup-consistency arms pinning the mockup side;
presentation values are fixture choices in the fixtures.py sense
(corpus-shaped, fixture-documented), while structural strings and counts
are corpus-derived and test-pinned.

Derivation decisions (each disclosed):
- n_lanes 2 (ch1, ch2), n_groups 1 (label D1-D2, radix hex, first declared
  member the LSB) — the §3.1/§3.2 chunking arithmetic over the descriptor's
  two digital_input channels.
- n_decoders 3: one decoder lane per descriptor-pinned decoder whose line
  roles resolve onto declared channels; the resolution evidence is the
  descriptor's own pinned vectors (i2c scl/sda, spi clk/cs, uart rx).
  onewire_link pins no resolving vector, so it renders no lane.
- The Run section follows the reference's controls plan: arm = staging
  (L2: the required numeric the action schema leaves after the
  host-supplied fields — max_duration_ms, schema minimum 1, no maximum),
  abort and trigger = L1 buttons (abort renders as ONE action — never a
  confirm subtree; the D7 forbid). The layout block's Run section names
  arm + abort; trigger joins from the capture page's binding_slots.
- The boundless maximum renders the empty attribute — an ABSENT bound,
  never an invented one (A02).
"""

from __future__ import annotations

from typing import cast

from benchweave_ui_html.data import (
    AlertBubbleData,
    ButtonData,
    ModeBannerData,
    ModeEntry,
    NumericInputData,
    ReadingData,
    Severity,
    TableData,
    TableDataRow,
)
from benchweave_ui_html.decimate import LaneState
from benchweave_ui_html.env import ENV
from benchweave_ui_html.lanes import (
    ComposedLanes,
    Cursor,
    DecoderEvent,
    LanesDeclaration,
    LaneSpec,
    compose_lanes,
)
from benchweave_ui_html.partials import (
    render_alert_bubble,
    render_button,
    render_data_table,
    render_lanes,
    render_mode_banner,
    render_numeric_input,
    render_plot,
    render_reading,
)
from benchweave_ui_html.plot import ComposedPlot, TraceSpec, compose_plot

#: The mode banner (§E.1 placement: first component of the page). The
#: pattern library's own disclosure — one entry, the SIMULATED literal the
#: mode-banner fixture carries.
_MODE = ModeBannerData(
    modes=(ModeEntry("simulated", "SIMULATED PRESENTATION DATA"),)
)

#: The staged configuration evidence line (fixture-documented: the
#: vectors' canonical cfg-1/acq-1 identity names, not a live binding).
_STAGED_CONFIG_TEXT = "Staged configuration · cfg-1"

#: The controls plan (§6 README; expect.controls): arm = staging, abort and
#: trigger = button. Display labels are fixture choices — the reference
#: authors structure, not data (D2).
_ARM_NUMERIC = NumericInputData(
    label="Max duration",
    unit="ms",
    value="10000",  # the vectors' canonical arm example
    minimum="1",  # the action schema's own minimum
    maximum="",  # no schema maximum — the absent bound (A02)
    step="1",  # the schema type's integer step, type-derived
    input_id="bw-classref-arm-duration",
)
_ARM_BUTTON = ButtonData(label="Arm acquisition", variant="primary")
_ABORT_BUTTON = ButtonData(label="Abort acquisition", variant="destructive")
_TRIGGER_BUTTON = ButtonData(label="Force trigger", variant="primary")


def _channel_states(index: int, acquired: int) -> tuple[LaneState, ...]:
    """Fixture-documented state sequences in the fetch vector's vocabulary:
    ch1 carries the four-state shape (0, 1, x, z); ch2 the binary shape
    (1, 0 alternating)."""
    if index == 0:
        quarter = acquired // 4
        return cast(
            tuple[LaneState, ...],
            ("0",) * quarter + ("1",) * quarter + ("x",) * quarter + ("z",) * quarter,
        )
    quarter = acquired // 4
    return cast(
        tuple[LaneState, ...],
        ("1",) * quarter + ("0",) * quarter + ("1",) * quarter + ("0",) * quarter,
    )


#: The µs scale the fixture documents (1 MHz — the configure vector's
#: rate). acquired 24 samples over 24 µs; 12 drawn columns.
_ACQUIRED = 24
_COLUMNS = 12
_RATE_HZ = 1_000_000.0

#: Decoder events (µs positions fixture-documented inside the 24 µs
#: window); payloads are the descriptor vectors' own texts, rendered
#: verbatim (§E.4.6: never re-encoded).
_I2C_EVENTS = (
    DecoderEvent(0.0000005, 0.0000015, "Start"),
    DecoderEvent(0.0000020, 0.0000040, "Address write: 50"),
    DecoderEvent(0.0000045, 0.0000055, "ACK"),
    DecoderEvent(0.0000060, 0.0000080, "Data write: 12"),
    DecoderEvent(0.0000100, 0.0000110, "Stop"),
)
_SPI_EVENTS = (
    DecoderEvent(0.0000010, 0.0000030, "FF"),
    DecoderEvent(0.0000050, 0.0000070, "3A"),
    DecoderEvent(0.0000090, 0.0000110, "A8"),
    DecoderEvent(0.0000130, 0.0000135, "CS# was deasserted during this data word!"),
)
_UART_EVENTS = (
    DecoderEvent(0.0000020, 0.0000035, "55"),
    DecoderEvent(0.0000060, 0.0000075, "AA"),
)


def capture_lanes() -> ComposedLanes:
    """The capture view: two declared channel lanes at positions 0 and 1,
    the D1-D2 group (radix hex, first declared member the LSB), and the
    three resolving decoder lanes beneath (§E.4.6: annotation rows after
    the channel and bus rows, lane indices never renumbered)."""
    channels = (
        LaneSpec(0, "channel", "Reference channel 1", states=_channel_states(0, _ACQUIRED)),
        LaneSpec(1, "channel", "Reference channel 2", states=_channel_states(1, _ACQUIRED)),
    )
    group = LaneSpec(
        2,
        "group",
        "D1-D2",
        members=("ch1", "ch2"),
        bit_width=2,
        radix="hex",
    )
    decoders = (
        LaneSpec(
            3,
            "decoder",
            "i2c · scl=ch1 sda=ch2",
            source_channel="ch1",
            events=_I2C_EVENTS,
        ),
        LaneSpec(
            4,
            "decoder",
            "spi · clk=ch1 cs=ch2",
            source_channel="ch1",
            events=_SPI_EVENTS,
        ),
        LaneSpec(
            5,
            "decoder",
            "uart · rx=ch1",
            source_channel="ch1",
            events=_UART_EVENTS,
        ),
    )
    return compose_lanes(
        LanesDeclaration(
            title="Capture",
            description=(
                "The class-reference capture view: the descriptor's two "
                "declared channels, the D1-D2 group at radix hex, and the "
                "three resolving decoder lanes."
            ),
            lanes=channels + (group,) + decoders,
            acquired=_ACQUIRED,
            columns=_COLUMNS,
            axis_label="Capture time",
            axis_unit="s",
            sample_rate_hz=_RATE_HZ,
            trigger_s=0.000002,
            cursors=(Cursor(0.000005), Cursor(0.000009)),
        ),
        member_states={
            "ch1": _channel_states(0, _ACQUIRED),
            "ch2": _channel_states(1, _ACQUIRED),
        },
    )


#: The composition wrapper (host composition markup — the layout
#: vocabulary's sections at the spans the reference block names; the
#: §E.1 panel instance is NOT used here because PanelData renders body
#: paragraphs only, and the section must carry the lanes partial).
_PAGE_TEMPLATE = """<div class="bw-classref-page">
{{ banner | safe }}
<div class="bw-classref-grid">
<section class="bw-classref-section" data-surface="raised" aria-label="Lanes">
<h3>Lanes</h3>
{{ lanes | safe }}
</section>
<section class="bw-classref-section" data-surface="raised" aria-label="Run">
<h3>Run</h3>
<p data-bw-staged-config>{{ staged_config }}</p>
{{ arm_numeric | safe }}
{{ arm_button | safe }}
{{ abort_button | safe }}
{{ trigger_button | safe }}
</section>
</div>
</div>"""


def render_capture_page() -> str:
    """The capture-page composition: mode banner, the Lanes section (the
    capture view), the Run section (staged-config evidence, the arm
    staging numeric and the three run buttons)."""
    return ENV.from_string(_PAGE_TEMPLATE).render(
        banner=render_mode_banner(_MODE),
        lanes=render_lanes(capture_lanes()),
        staged_config=_STAGED_CONFIG_TEXT,
        arm_numeric=render_numeric_input(_ARM_NUMERIC),
        arm_button=render_button(_ARM_BUTTON),
        abort_button=render_button(_ABORT_BUTTON),
        trigger_button=render_button(_TRIGGER_BUTTON),
    )


# --- the dc_psu output page (L11; design record 2026-10-18) ---------------------
#
# The composition's structure mirrors the reference's own layout block
# (readings 12 raised / trend 7 recessed / table 5 raised — the mockup's
# 5/7 ratio in the vocabulary's spans) and its counts derive from the
# committed corpus pair: one reading tile per (channel, quantity) of the
# OTDP example's declared source channels (2 × 3), one engineering plot
# over the measure dataset (the two-trace set is the disclosed author
# channel_hints choice), one data table with a row per pair. Tile values,
# severities and the table's quality wording are fixture choices in the
# fixtures.py sense (the mockup's own illustrative data); the labels and
# trace ids are corpus strings (channel labels × declared quantities).
# No control surface derives at birth: the output toggle is a named
# deviation and the staged setpoint idiom is cannot_derive — the page
# fabricates neither (the drift guard pins their absence).


def _psu_tiles() -> tuple[ReadingData, ...]:
    """One tile per (channel, quantity) pair of the OTDP example's source
    channels; the ch1 current tile renders the mockup's warning variant
    (structure renders the variant, data decides it)."""
    first: dict[str, tuple[str, str, Severity]] = {
        "voltage": ("12.04", "V", "success"),
        "current": ("1.92", "A", "warning"),
        "power": ("23.1", "W", "success"),
    }
    second: dict[str, tuple[str, str, Severity]] = {
        "voltage": ("12.00", "V", "success"),
        "current": ("1.50", "A", "success"),
        "power": ("18.0", "W", "success"),
    }
    channels = (("Reference channel 1", first), ("Reference channel 2", second))
    tiles: list[ReadingData] = []
    for label, quantities in channels:
        for quantity, (value, unit, severity) in quantities.items():
            tiles.append(
                ReadingData(
                    label=f"{label} · {quantity}",
                    severity=severity,
                    value=value,
                    unit=unit,
                )
            )
    return tuple(tiles)


#: The margin alert (cannot_derive margin-alert renders from host-observed
# conditions; the composition carries the mockup's illustrative one, not
# dismissible — a persistent condition, never an operator dismissal).
_PSU_ALERT = AlertBubbleData(
    severity="warning",
    title="Operating margin",
    message="Current approaching configured limit",
    live_region="status",
    dismissible=False,
)


def _psu_plot() -> ComposedPlot:
    """The trend: one time-series engineering plot over the measure
    dataset — voltage and current of the first declared channel (the
    mockup's two traces; the author channel_hints choice, disclosed)."""
    return compose_plot(
        title="Output",
        description=(
            "Output voltage and current over the trend window for the "
            "first declared source channel."
        ),
        traces=(
            TraceSpec(
                "Reference channel 1 · voltage",
                "V",
                samples=(12.04, 12.01, 11.98, 12.06, 12.03, 12.04),
                acquired=60,
            ),
            TraceSpec(
                "Reference channel 1 · current",
                "A",
                samples=(1.88, 1.90, 1.92, 1.91, 1.92, 1.92),
                acquired=60,
            ),
        ),
        hints={},
    )


def _psu_table() -> TableData:
    """One row per (channel, quantity) pair — the tiles' own derivation;
    the quality column carries the mockup's wording."""
    rows = []
    for tile in _psu_tiles():
        quality = "Near limit" if tile.severity == "warning" else "Verified"
        rows.append(
            TableDataRow(
                key=tile.label,
                cells=(tile.label, f"{tile.value} {tile.unit}", quality),
            )
        )
    return TableData(
        caption="Output readings",
        headers=("Channel", "Reading", "Quality"),
        rows=tuple(rows),
    )


_OUTPUT_TEMPLATE = """<div class="bw-classref-page">
{{ banner | safe }}
<div class="bw-classref-grid">
<section class="bw-classref-section" data-bw-section-id="readings"
  data-surface="raised" data-bw-span="12" aria-label="Readings">
<h3>Readings</h3>
<div class="bw-readings-grid">
{% for tile in tiles %}{{ tile | safe }}
{% endfor %}</div>
</section>
</div>
{{ alert | safe }}
<div class="bw-classref-grid">
<section class="bw-classref-section" data-bw-section-id="trend"
  data-surface="recessed" data-bw-span="7" aria-label="Trend">
<h3>Trend</h3>
{{ plot | safe }}
</section>
<section class="bw-classref-section" data-bw-section-id="table"
  data-surface="raised" data-bw-span="5" aria-label="Table">
<h3>Table</h3>
{{ table | safe }}
</section>
</div>
</div>"""


def output_readings() -> tuple[ReadingData, ...]:
    """The composition's reading tiles (the drift guard's count arm)."""
    return _psu_tiles()


def render_output_page() -> str:
    """The dc_psu output-page composition: mode banner, the Readings
    section (one §E.1 tile per channel/quantity pair), the margin alert,
    the Trend section (one engineering plot) and the Table section (one
    §E.1 data table) — the reference layout block's own surfaces and
    spans."""
    return ENV.from_string(_OUTPUT_TEMPLATE).render(
        banner=render_mode_banner(_MODE),
        tiles=[render_reading(tile) for tile in _psu_tiles()],
        alert=render_alert_bubble(_PSU_ALERT),
        plot=render_plot(_psu_plot()),
        table=render_data_table(_psu_table()),
    )


# --- the dmm readings page (L12; design record 2026-10-19) ----------------------
#
# The observation-pure class, third composer, same standing shape. The
# composition mirrors the dmm reference's own layout block (readings 12
# raised / trend 7 recessed / table 5 raised — the dc_psu ratio; the
# class's difference is content, not geometry) and its counts derive
# from the committed corpus pair: one reading tile per (channel,
# quantity) of the OTDP example's declared measure channels (2 x 1),
# one engineering plot over the measure dataset (one trace per declared
# channel — both channel traces, no author hint subset), one data table
# with a row per pair. Tile values, severities and the table's quality
# wording are fixture choices in the fixtures.py sense (the mockup's
# own illustrative data); the labels and trace ids are corpus strings
# (channel labels x declared quantities). No control surface derives at
# birth: the function/range/aperture/autozero selection is cannot_derive
# (function-selection) and the page fabricates none (the drift guard
# pins the absence). The dashed range-bound overlay is cannot_derive
# (range-overlay) and composes nothing here.


def _dmm_tiles() -> tuple[ReadingData, ...]:
    """One tile per (channel, quantity) pair of the OTDP example's
    measure channels; the ch2 tile renders the mockup's warning variant
    (structure renders the variant, data decides it)."""
    first: dict[str, tuple[str, str, Severity]] = {
        "voltage": ("11.982", "V", "success"),
    }
    second: dict[str, tuple[str, str, Severity]] = {
        "voltage": ("0.304", "V", "warning"),
    }
    channels = (("Reference channel 1", first), ("Reference channel 2", second))
    tiles: list[ReadingData] = []
    for label, quantities in channels:
        for quantity, (value, unit, severity) in quantities.items():
            tiles.append(
                ReadingData(
                    label=f"{label} · {quantity}",
                    severity=severity,
                    value=value,
                    unit=unit,
                )
            )
    return tuple(tiles)


#: The range-margin alert (cannot_derive range-margin-alert renders from
#: host-observed conditions; the composition carries the mockup's
#: illustrative one, not dismissible — a persistent condition).
_DMM_ALERT = AlertBubbleData(
    severity="warning",
    title="Range margin",
    message="Reading approaching configured range limit",
    live_region="status",
    dismissible=False,
)


def _dmm_plot() -> ComposedPlot:
    """The trend: one time-series engineering plot over the measure
    dataset — one trace per declared measure channel (both channel
    traces; the mockup's two, no subset choice to disclose)."""
    return compose_plot(
        title="Readings",
        description=(
            "Both declared measure channels' voltage readings over the "
            "trend window."
        ),
        traces=(
            TraceSpec(
                "Reference channel 1 · voltage",
                "V",
                samples=(11.981, 11.983, 11.980, 11.982, 11.984, 11.982),
                acquired=60,
            ),
            TraceSpec(
                "Reference channel 2 · voltage",
                "V",
                samples=(0.296, 0.300, 0.304, 0.303, 0.304, 0.304),
                acquired=60,
            ),
        ),
        hints={},
    )


def _dmm_table() -> TableData:
    """One row per (channel, quantity) pair — the tiles' own derivation;
    the quality column carries the mockup's wording."""
    rows = []
    for tile in _dmm_tiles():
        quality = "Near limit" if tile.severity == "warning" else "Verified"
        rows.append(
            TableDataRow(
                key=tile.label,
                cells=(tile.label, f"{tile.value} {tile.unit}", quality),
            )
        )
    return TableData(
        caption="Channel readings",
        headers=("Channel", "Reading", "Quality"),
        rows=tuple(rows),
    )


_READINGS_TEMPLATE = """<div class="bw-classref-page">
{{ banner | safe }}
<div class="bw-classref-grid">
<section class="bw-classref-section" data-bw-section-id="readings"
  data-surface="raised" data-bw-span="12" aria-label="Readings">
<h3>Readings</h3>
<div class="bw-readings-grid">
{% for tile in tiles %}{{ tile | safe }}
{% endfor %}</div>
</section>
</div>
{{ alert | safe }}
<div class="bw-classref-grid">
<section class="bw-classref-section" data-bw-section-id="trend"
  data-surface="recessed" data-bw-span="7" aria-label="Trend">
<h3>Trend</h3>
{{ plot | safe }}
</section>
<section class="bw-classref-section" data-bw-section-id="table"
  data-surface="raised" data-bw-span="5" aria-label="Table">
<h3>Table</h3>
{{ table | safe }}
</section>
</div>
</div>"""


def dmm_readings() -> tuple[ReadingData, ...]:
    """The composition's reading tiles (the drift guard's count arm)."""
    return _dmm_tiles()


def render_dmm_readings_page() -> str:
    """The dmm readings-page composition: mode banner, the Readings
    section (one §E.1 tile per channel/quantity pair), the range-margin
    alert, the Trend section (one engineering plot) and the Table
    section (one §E.1 data table) — the reference layout block's own
    surfaces and spans."""
    return ENV.from_string(_READINGS_TEMPLATE).render(
        banner=render_mode_banner(_MODE),
        tiles=[render_reading(tile) for tile in _dmm_tiles()],
        alert=render_alert_bubble(_DMM_ALERT),
        plot=render_plot(_dmm_plot()),
        table=render_data_table(_dmm_table()),
    )



# --- the oscilloscope capture page (L13; design record 2026-10-19) -------------
#
# The capture class's own geometry, fourth composer, same standing shape:
# the traces section (the analyser's capture geometry — plot recessed and
# dominant, span 12) and the run section (raised, span 12), mirroring the
# reference layout block's surfaces and spans. The counts derive from the
# committed corpus pair: one waveform plot over the capture dataset (one
# trace per (channel, declared quantity) of the OTDP example's declared
# analogue channels — 2 x 1), and one run control per DECLARED run action
# of the example (3: arm staging + abort + trigger buttons — the example
# declares all five actions; a trigger-less descriptor renders its ghost
# at expansion). Trace values and the acquisition numbers are fixture
# choices in the fixtures.py sense (the mockup's own illustrative data);
# the labels and trace ids are corpus strings (channel labels x declared
# quantities). The acquisition disclosure (§E.2.5) is exercised with the
# class's own numbers — the capture-context strip lands by use (RC-L5-1's
# second idiom: no contract row, no motion). No control surface derives
# beyond the ladder's: acquisition settings are cannot_derive
# (acquisition-settings; configure is preset-mediated at birth) and the
# page fabricates no settings face; the trigger marker and cursor readout
# are cannot_derive (host-knowledge seam) and compose nothing here; the
# capture page carries NO data table — a table of waveform samples is not
# a surface this class presents (the drift guard pins the absence).

def _scope_traces() -> tuple[TraceSpec, ...]:
    """One trace per (channel, quantity) of the OTDP example's analogue
    channels — both channel voltage waveforms (2 x 1 derived from the
    corpus pair; no subset choice to disclose). The acquired counts are
    the mockup's own acquisition numbers (fixture data)."""
    return (
        TraceSpec(
            "Reference channel 1 · voltage",
            "V",
            samples=(0.0, 3.0, 3.0, -3.0, -3.0, 0.0, 3.0, 3.0, -3.0, -3.0, 0.0),
            acquired=4096,
        ),
        TraceSpec(
            "Reference channel 2 · voltage",
            "V",
            samples=(0.0, 2.1, 3.0, 2.1, 0.0, -2.1, -3.0, -2.1, 0.0, 2.1, 3.0),
            acquired=4096,
        ),
    )


#: The partial-capture alert (cannot_derive partial-capture-alert renders
#: from host-observed conditions; the composition carries the mockup's
#: illustrative one, not dismissible — a persistent condition).
_SCOPE_ALERT = AlertBubbleData(
    severity="warning",
    title="Partial capture",
    message="Acquisition truncated — partial dataset",
    live_region="status",
    dismissible=False,
)

#: The run controls (expect.controls: arm staging L2, abort/trigger
#: button L1). Display labels and faces are fixture choices — the
#: reference authors structure, not data (D2); the face set is the
#: design's §2 mockup contract (Arm primary; Trigger and Abort
#: secondary).
_SCOPE_ARM_NUMERIC = NumericInputData(
    label="Max duration",
    unit="ms",
    value="10000",  # fixture choice — the analyser composer's own
    minimum="1",  # the action schema's own minimum
    maximum="",  # no schema maximum — the absent bound (A02)
    step="1",  # the schema type's integer step, type-derived
    input_id="bw-classref-scope-arm-duration",
)
_SCOPE_ARM_BUTTON = ButtonData(label="Arm acquisition", variant="primary")
_SCOPE_TRIGGER_BUTTON = ButtonData(label="Force trigger", variant="secondary")
_SCOPE_ABORT_BUTTON = ButtonData(label="Abort acquisition", variant="secondary")


def _scope_plot() -> ComposedPlot:
    """The capture plot: one waveform engineering plot over the capture
    dataset — both declared channel traces (the mockup's two). The
    per-trace acquisition disclosure renders because the drawn samples
    are fewer than acquired (the §E.2.5 strip lands by use)."""
    return compose_plot(
        title="Capture",
        description=(
            "Both declared analogue channels' voltage waveforms over the "
            "acquisition window."
        ),
        traces=_scope_traces(),
        hints={},
        rate="1 MS/s",
    )


_SCOPE_CAPTURE_TEMPLATE = """<div class="bw-classref-page">
{{ banner | safe }}
<div class="bw-classref-grid">
<section class="bw-classref-section" data-bw-section-id="traces"
  data-surface="recessed" data-bw-span="12" aria-label="Traces">
<h3>Traces</h3>
{{ plot | safe }}
</section>
</div>
<div class="bw-classref-grid">
<section class="bw-classref-section" data-bw-section-id="run"
  data-surface="raised" data-bw-span="12" aria-label="Run">
<h3>Run</h3>
<p data-bw-staged-config>{{ staged_config }}</p>
{{ arm_numeric | safe }}
{{ arm_button | safe }}
{{ trigger_button | safe }}
{{ abort_button | safe }}
</section>
</div>
{{ alert | safe }}
</div>"""


def render_oscilloscope_capture_page() -> str:
    """The oscilloscope capture-page composition: mode banner, the Traces
    section (one engineering waveform plot over the capture dataset),
    the Run section (staged-config evidence, the arm staging numeric and
    the three run buttons) and the partial-capture alert — the reference
    layout block's own surfaces and spans."""
    return ENV.from_string(_SCOPE_CAPTURE_TEMPLATE).render(
        banner=render_mode_banner(_MODE),
        plot=render_plot(_scope_plot()),
        staged_config=_STAGED_CONFIG_TEXT,
        arm_numeric=render_numeric_input(_SCOPE_ARM_NUMERIC),
        arm_button=render_button(_SCOPE_ARM_BUTTON),
        trigger_button=render_button(_SCOPE_TRIGGER_BUTTON),
        abort_button=render_button(_SCOPE_ABORT_BUTTON),
        alert=render_alert_bubble(_SCOPE_ALERT),
    )


# --- the function_generator configuration page (L14; design record 2026-10-19) --
#
# The pure-source class, fifth composer, same standing shape — and the
# first class whose pattern page composes the CONFIGURATION page: no
# measurement action exists, so no observation binds and no plot
# template names an over-slot; the page set owns Configuration and
# Device features only (RC-L14-2), the reference authors zero layout
# blocks and zero numeric literals. The counts derive from the committed
# corpus pair: two function cards (one per (channel, declared quantity)
# of the OTDP example's declared source channels — 2 x 1), one settings
# data table whose field-row set is the catalog's configure input
# schema minus the identity fields the composition carries elsewhere
# (configuration_id on the staged-configuration evidence, channel on
# the cards), and one alert carrying the mockup's own wording. Card
# values and the preview paint are fixture choices in the fixtures.py
# sense (the mockup's illustrative data); the card labels and the field
# names are corpus strings. No control surface derives at birth and NO
# idiom presents as a contract component: the output toggle and the
# waveform upload are declared deviations (the directional section C.1
# presentation; the pattern-narrowed channel and the artifact-selection
# inputs), the preview is a runtime join against the effective
# configuration (no dataset action exists for a plot arm to bind — the
# canvas lands as paint, never bw-plot), and the preset scaffold is
# commissioned evidence (A02) — the drift guards pin the absence of
# every fabricated control (bw-rotary, bw-confirm, bw-button, <button>,
# bw-plot) and of any reading tile (a requested value is not a reading).

#: The per-channel function cards — one per (channel, declared
#: quantity) of the example's declared source channels. Labels are the
#: descriptor's own channel labels (corpus strings); values and states
#: are fixture choices (the mockup's illustrative data).
_FG_CARDS: tuple[dict[str, str], ...] = (
    {
        "label": "Reference channel 1",
        "function": "sine",
        "value": "1 kHz · 2.5 Vpp · +125 mV",
        "state": "50 Ω LOAD · OUTPUT ON",
    },
    {
        "label": "Reference channel 2",
        "function": "square",
        "value": "10 kHz · 5 Vpp · 25% duty",
        "state": "50 Ω LOAD · OUTPUT OFF",
    },
)

#: The load-convention alert (cannot_derive load-convention-alert
#: renders from host-observed conditions; the composition carries the
#: mockup's illustrative one, not dismissible — a persistent condition).
_FG_ALERT = AlertBubbleData(
    severity="warning",
    title="Load convention",
    message=(
        "voltage is specified at the declared 50 Ω load; "
        "high-impedance operation changes the delivered amplitude"
    ),
    live_region="status",
    dismissible=False,
)

#: The settings table's field rows: one row per configure input-schema
#: property minus the identity fields ({configuration_id, channel}) the
#: composition carries elsewhere — the committed artifact of the
#: schema derivation (Kind from the property's own shape: enum ->
#: selection, string -> text, numeric otherwise; Notes from the
#: schema's allOf conditions), the catalog's own strings verbatim. A
#: catalog edit reddens the drift guard until this data is regenerated.
_FG_SETTINGS_ROWS: tuple[TableDataRow, ...] = (
    TableDataRow(key="function", cells=("function", "selection", "—")),
    TableDataRow(key="frequency_hz", cells=("frequency_hz", "numeric", "—")),
    TableDataRow(key="amplitude_vpp", cells=("amplitude_vpp", "numeric", "—")),
    TableDataRow(key="offset_v", cells=("offset_v", "numeric", "—")),
    TableDataRow(key="phase_deg", cells=("phase_deg", "numeric", "—")),
    TableDataRow(key="load_ohm", cells=("load_ohm", "numeric", "—")),
    TableDataRow(
        key="duty_cycle",
        cells=("duty_cycle", "numeric", "required when function is square or pulse"),
    ),
    TableDataRow(
        key="waveform_id",
        cells=("waveform_id", "text", "required when function is arbitrary"),
    ),
)

_FG_TABLE = TableData(
    caption="Configure fields",
    headers=("Field", "Kind", "Notes"),
    rows=_FG_SETTINGS_ROWS,
)

#: The preview paint (host composition, never a §E.1 plot): two traces
#: over one canvas — the sine solid, the square dashed — the mockup's
#: own geometry, currentColor so each theme tints it.
_FG_PREVIEW_SVG = (
    '<svg viewBox="0 0 460 150" role="img" '
    'aria-label="Painted preview of the two configured output waveforms">'
    '<path d="M0 82C30 30 60 30 90 82S150 134 180 82 '
    '240 30 270 82 330 134 360 82 420 30 450 82" '
    'fill="none" stroke="currentColor" stroke-width="2.5"/>'
    '<path d="M0 58H45V106H135V58H225V106H315V58H405V106H460" '
    'fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-dasharray="8 5"/></svg>'
)

#: The staged-output card's §C.1 directional lines (painted idiom, the
#: mockup's own wording): the enable arm's armed line names effect and
#: target (stage-then-confirm); the disable arm is one ungated action.
_FG_ARMED_LINE = (
    "ENABLE · REFERENCE CHANNEL 1 · EFFECT: OUTPUT ON AT THE STAGED "
    "CONFIGURATION"
)
_FG_UNGATED_LINE = "DISABLE · REFERENCE CHANNEL 1 · ONE ACTION · NO CONFIRMATION"

_FG_CONFIGURATION_TEMPLATE = """<div class="bw-classref-page">
{{ banner | safe }}
<div class="bw-classref-grid">
<section class="bw-classref-section" data-bw-section-id="cards"
  data-surface="raised" data-bw-span="12" aria-label="Function cards">
<h3>Function cards</h3>
<div class="bw-fg-cards">
{% for card in cards %}<article class="fncard card">
<span class="fn-label">{{ card.label }} · {{ card.function | upper }}</span>
<div class="fn-value">{{ card.value }}</div>
<span class="fn-state">{{ card.state }}</span>
</article>
{% endfor %}</div>
</section>
</div>
{{ alert | safe }}
<div class="bw-classref-grid">
<section class="bw-classref-section settings" data-bw-section-id="settings"
  data-surface="raised" data-bw-span="5" aria-label="Settings">
<h3>Settings</h3>
{{ table | safe }}
</section>
<section class="bw-classref-section" data-bw-section-id="preview"
  data-surface="recessed" data-bw-span="7" aria-label="Preview">
<div class="plot waveform-preview">
<div class="plot-head"><span>PREVIEW · CONFIGURED OUTPUT</span>
<span>— SINE CH1&nbsp;&nbsp; -- SQUARE CH2</span></div>
{{ preview_svg }}
<div class="acq">Preview joins the effective configuration · illustrative</div>
</div>
</section>
</div>
<div class="bw-classref-grid">
<section class="bw-classref-section" data-bw-section-id="preset"
  data-surface="raised" data-bw-span="6" aria-label="Preset">
<article class="preset-card card"><span class="eyebrow">Preset</span>
<div class="preset-line">FUNCTION · SINE / 1 kHz / 2.5 Vpp</div>
<span class="staged">PRESET · APPLY REQUIRED</span></article>
</section>
<section class="bw-classref-section" data-bw-section-id="output"
  data-surface="raised" data-bw-span="6" aria-label="Output">
<article class="output-control card"><span class="eyebrow">Output</span>
<div class="armed-line">{{ armed_line }}</div>
<span class="staged">STAGED · CONFIRM REQUIRED</span>
<div class="ungated">{{ ungated_line }}</div>
</article>
</section>
</div>
</div>"""


def render_function_generator_configuration_page() -> str:
    """The function_generator configuration-page composition: mode
    banner, the Function-cards section (one hook-less card per declared
    source channel — requested values, never readings), the
    load-convention alert, the Settings section (one §E.1 data table
    over the configure schema's field rows) beside the hook-less
    waveform-preview panel, and the preset and staged-output idiom
    cards — the pure-source class's two derivable contract surfaces
    carrying the composition, everything else painted host-side."""
    return ENV.from_string(_FG_CONFIGURATION_TEMPLATE).render(
        banner=render_mode_banner(_MODE),
        cards=_FG_CARDS,
        alert=render_alert_bubble(_FG_ALERT),
        table=render_data_table(_FG_TABLE),
        preview_svg=_FG_PREVIEW_SVG,
        armed_line=_FG_ARMED_LINE,
        ungated_line=_FG_UNGATED_LINE,
    )


__all__ = [
    "capture_lanes",
    "dmm_readings",
    "output_readings",
    "render_capture_page",
    "render_dmm_readings_page",
    "render_function_generator_configuration_page",
    "render_oscilloscope_capture_page",
    "render_output_page",
]
