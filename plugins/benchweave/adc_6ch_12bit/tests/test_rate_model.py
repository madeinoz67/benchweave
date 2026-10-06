# author: Stephen Eaton
"""A4 model honesty: the rate-model doc's tables regenerate from constants.

The doc's numeric table cells are parsed and compared cell-by-cell
against values recomputed from the frame constants (the codec's
``frame_bytes``) and the two conversion terms. A hand-edited doc cell
fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from adc_wire import codec

#: firmware-measured (v1 polled path: config-write + EOC busy-wait +
#: read + loop overhead on top of the ADC time) — the contributor's
#: bench, cited as provenance in the design record §6
T_CONV_POLLED_US = 31.6
#: COMPUTED (fold M4), the vendor's own numbers: CyclesMode5 sample time
#: 55.5 cycles + the 12.5-cycle conversion = 68 ADC cycles at
#: ADCCLK = PCLK2/8 = 6 MHz. No hand-typed constant.
_SAMPLE_CYCLES_MODE5 = 55.5
_CONV_CYCLES = 12.5
_ADCCLK_MHZ = 48.0 / 8
T_CONV_ADC_US = (_SAMPLE_CYCLES_MODE5 + _CONV_CYCLES) / _ADCCLK_MHZ

DOC = Path(__file__).resolve().parents[1] / "docs" / "rate-model.md"


def sps(n_active: int, avg: int, baud: int, slim: bool, t_conv_us: float) -> float:
    """The design §6 rate formula."""
    frame = codec.frame_bytes(n_active, slim)
    wire_us = frame * 10 / baud * 1e6
    total_us = n_active * max(avg, 1) * t_conv_us + wire_us
    return 1e6 / total_us


def _table_rows(section: str) -> list[list[str]]:
    text = DOC.read_text(encoding="utf-8")
    body = text.split(f"## {section}", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in body.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 8 and cells[0].isdigit():
            rows.append(cells)
    return rows


def test_single_channel_table_regenerates() -> None:
    # (n_active, avg, baud, slim, t_conv, operator): "sum" = serial
    # (v1/v2-without-DMA), "max" = pipelined (fold M4)
    cases = {
        "0": (1, 0, 2_000_000, False, T_CONV_POLLED_US, "sum"),
        "1": (1, 0, 2_000_000, False, T_CONV_POLLED_US, "sum"),
        "2": (1, 0, 2_000_000, False, T_CONV_ADC_US, "max"),
        "3": (1, 0, 3_000_000, False, T_CONV_ADC_US, "max"),
        "4": (1, 0, 3_000_000, True, T_CONV_ADC_US, "max"),
        "5": (1, 0, 3_000_000, True, T_CONV_POLLED_US, "sum"),
    }
    for row in _table_rows("Single channel"):
        row_id = row[0]
        frame, baud = int(row[3]), int(row[4])
        wire, total, got_sps = float(row[5]), float(row[6]), int(row[7])
        n_active, avg, baud_exp, slim, t_conv_exp, op = cases[row_id]
        assert frame == codec.frame_bytes(n_active, slim), row_id
        assert baud == baud_exp, row_id
        assert float(row[2]) == pytest.approx(t_conv_exp, abs=0.005), row_id
        wire_exp = codec.frame_bytes(n_active, slim) * 10 / baud_exp * 1e6
        conv_total = n_active * max(avg, 1) * t_conv_exp
        total_exp = max(conv_total, wire_exp) if op == "max" else conv_total + wire_exp
        assert wire == pytest.approx(wire_exp, abs=0.005), row_id
        assert total == pytest.approx(total_exp, abs=0.005), row_id
        got = 1e6 / total_exp
        assert got_sps == round(got), row_id


def test_six_channel_table_regenerates() -> None:
    cases = {
        "6": (6, 0, 2_000_000, False, T_CONV_POLLED_US, "sum"),
        "7": (6, 0, 3_000_000, False, T_CONV_ADC_US, "max"),
    }
    for row in _table_rows("Six channels"):
        row_id = row[0]
        frame, baud = int(row[3]), int(row[4])
        wire, total, got_sps = float(row[5]), float(row[6]), int(row[7])
        n_active, avg, baud_exp, slim, t_conv_exp, op = cases[row_id]
        assert frame == codec.frame_bytes(6, slim), row_id
        assert baud == baud_exp, row_id
        assert float(row[2]) == pytest.approx(t_conv_exp, abs=0.005), row_id
        wire_exp = codec.frame_bytes(6, slim) * 10 / baud_exp * 1e6
        conv_total = 6 * max(avg, 1) * t_conv_exp
        total_exp = max(conv_total, wire_exp) if op == "max" else conv_total + wire_exp
        assert wire == pytest.approx(wire_exp, abs=0.005), row_id
        assert total == pytest.approx(total_exp, abs=0.005), row_id
        assert got_sps == round(1e6 / total_exp), row_id


def test_wire_ceiling_table_regenerates() -> None:
    cases = {
        "8": (23, 2_000_000),
        "9": (13, 2_000_000),
        "10": (23, 3_000_000),
        "11": (13, 3_000_000),
    }
    for row in _table_rows("Wire ceilings"):
        row_id, frame, baud, got = row[0], int(row[1]), int(row[2]), int(row[3])
        frame_exp, baud_exp = cases[row_id]
        assert frame == frame_exp and baud == baud_exp, row_id
        assert got == round(1e6 / (frame * 10 / baud * 1e6)), row_id
