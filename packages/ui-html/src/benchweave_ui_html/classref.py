"""The class-reference capture page (Landing 3 of the class-reference
program; gateway issues #462 rows 1-2; design record §7 Landing 3, §7A L3).

One pattern-library page — ``class-capture`` — composes the capture-page
composition the reference describes from the §E.1 partials the renderer
already ships: host composition, no renderer change, no new contract rows
(the record's §2.6 rule). The §E.1 partials, templates and the contract
harness are untouched by this slice.

RENDER-TIME EXPANSION (disclosed): the production expander is Landing 2's,
unreleased at this slice. This module's data was produced by a throwaway
render-time expansion of the committed corpus pair —
standards/plugin-ui-class-reference/0.2.0/class-logic_analyser.json
expanded against standards/otdp/0.2.3/examples/class-logic_analyser.json —
and the module is the committed artifact. The drift guard
(tests/ui_html/test_classref_page.py) re-derives the page's structure from
those corpus files, so a corpus edit reddens the page data until it is
regenerated. Presentation timing, cursor/trigger positions and the state
sequences are fixture choices in the fixtures.py sense (corpus-shaped,
fixture-documented); the structural strings and the lane/group/decoder
derivation are corpus-derived and test-pinned.

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
    ButtonData,
    ModeBannerData,
    ModeEntry,
    NumericInputData,
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
    render_button,
    render_lanes,
    render_mode_banner,
    render_numeric_input,
)

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


__all__ = [
    "capture_lanes",
    "render_capture_page",
]
