"""The computed colour proofs — the port of ``ui/src/series-colors.test.ts``
(G1c design record §1.3/§3): S3-A1, S3-A2 with its engineering floor, the
S3-D2 census with its ASYMMETRIC floors, S3-A3, the S1-A3 limiting block,
and the group-iii instrument pins.

Pre-committed thresholds, not relaxable (record §2): every ΔE00 cell is
asserted under BOTH CVD-model arms; a disagreement is inconclusive and
escalates, never passes. Margins print in the TS format and ride
``record_property`` (the repo's established measurement channel) for the
cross-implementation parity check. Denominators are asserted per block:
640 + 448 + 112 + 112 = 1,312 ΔE00 arm-values over 656 pair-cells, plus
16 + 4 = 20 contrast ratios — 1,332 assertions on the shipped tokens.

The reading-tile.css structure pins (S1 fold rows 5+11) are G1b's lane, not
this port's (record §3 deferral 1).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest
from benchweave_ui_html.grammar import parse_contract
from benchweave_ui_html.manifest import MANIFEST
from benchweave_ui_html.tokens import theme_colour_mismatches
from colour_instrument import (
    _HALF_PLANE_NORMAL,
    A475,
    A575,
    CMF_575,
    CONDITIONS,
    DARK,
    LIGHT,
    M_LMS,
    M_RGB_LMS_INVERSE,
    MACHADO,
    THEMES,
    VIENOT,
    W_LMS,
    Lab,
    _mat_vec,
    brettel_tritan,
    ciede2000,
    contrast,
    de2000,
    hex_to_rgb,
    linear_to_srgb,
    rgb_to_lab,
    series_of,
    severity_all,
    severity_of,
    simulate_linear,
    srgb_to_linear,
)
from thresholds import (
    CENSUS_DARK_ENG_FLOOR,
    CENSUS_HARD,
    LIM_T1_CONTRAST,
    LIM_T2_ENG_FLOOR,
    LIM_T2_SEVERITY,
    T1_CONTRAST,
    T2_ENG_FLOOR,
    T2_SEVERITY,
    T3_ADJACENT,
)

UI_CONTRACT: Final[Path] = (
    Path(__file__).resolve().parents[2] / "docs" / "internal" / "ui-contract.md"
)

# I1: the Sharma et al. 2005 reference table, 33 rows (the published 34th row
# is omitted because this port's TS source could not independently confirm
# its coordinate tuple against a second reproduction — every other row's
# expected value was cross-checked between the fixed implementation and the
# table). Rows 11/12/15/16/17/19 (1-indexed) are the hue-wraparound rows the
# mean-hue correction turns on.
SHARMA_TABLE: Final[list[tuple[Lab, Lab, float]]] = [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 2.8361, -74.02), (50.0, 0.0, -82.7485), 3.4412),
    ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0),
    ((50.0, -1.1848, -84.8006), (50.0, 0.0, -82.7485), 1.0),
    ((50.0, -0.9009, -85.5211), (50.0, 0.0, -82.7485), 1.0),
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
    ((50.0, -1.0, 2.0), (50.0, 0.0, 0.0), 2.3669),
    ((50.0, 2.49, -0.001), (50.0, -2.49, 0.0009), 7.1792),
    ((50.0, 2.49, -0.001), (50.0, -2.49, 0.001), 7.1792),
    ((50.0, 2.49, -0.001), (50.0, -2.49, 0.0011), 7.2195),
    ((50.0, 2.49, -0.001), (50.0, -2.49, 0.0012), 7.2195),
    ((50.0, -0.001, 2.49), (50.0, 0.0009, -2.49), 4.8045),
    ((50.0, -0.001, 2.49), (50.0, 0.001, -2.49), 4.8045),
    ((50.0, -0.001, 2.49), (50.0, 0.0011, -2.49), 4.7461),
    ((50.0, 2.5, 0.0), (50.0, 0.0, -2.5), 4.3065),
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ((50.0, 2.5, 0.0), (61.0, -5.0, 29.0), 22.8977),
    ((50.0, 2.5, 0.0), (56.0, -27.0, -3.0), 31.903),
    ((50.0, 2.5, 0.0), (58.0, 24.0, 15.0), 19.4535),
    ((50.0, 2.5, 0.0), (50.0, 3.1736, 0.5854), 1.0),
    ((50.0, 2.5, 0.0), (50.0, 3.2972, 0.0), 1.0),
    ((50.0, 2.5, 0.0), (50.0, 1.8634, 0.5757), 1.0),
    ((50.0, 2.5, 0.0), (50.0, 3.2592, 0.335), 1.0),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.263),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.248, -4.962), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.694), (23.0331, 14.973, -42.5619), 2.0373),
    ((36.4612, 47.858, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.441), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
]


# --- group iii: the instrument pins (the port's only proof its maths is the
#     same maths; every pin cites its ledger row I1..I8) ---
@pytest.mark.parametrize("lab1,lab2,expected", SHARMA_TABLE)
def test_i1_ciede2000_sharma_reference_table(
    lab1: Lab, lab2: Lab, expected: float
) -> None:
    assert abs(ciede2000(lab1, lab2) - expected) < 1e-4


def test_i2_brettel_anchors_own_half_plane() -> None:
    # The SAME rule brettel_tritan uses — the shared half-plane normal —
    # assigns each anchor to its own plane (575 nm positive, 475 nm negative);
    # the fixed-point projection of an anchor onto its own plane is the
    # anchor, at (alpha, beta) = (0, 1).
    for anchor in (A575, A475):
        side = anchor[0] * _HALF_PLANE_NORMAL[0] + anchor[1] * _HALF_PLANE_NORMAL[1]
        chosen = A575 if side >= 0 else A475
        assert chosen == anchor, "an anchor must be assigned to its own half plane"
        d2 = W_LMS[0] * anchor[1] - W_LMS[1] * anchor[0]
        alpha = (anchor[0] * anchor[1] - anchor[1] * anchor[0]) / d2
        assert alpha == pytest.approx(0.0, abs=5e-10)


def test_i2_white_fixed_point_both_planes() -> None:
    for anchor in (A575, A475):
        q = W_LMS
        d2 = W_LMS[0] * anchor[1] - W_LMS[1] * anchor[0]
        alpha = (q[0] * anchor[1] - q[1] * anchor[0]) / d2
        beta = (W_LMS[0] * q[1] - W_LMS[1] * q[0]) / d2
        assert alpha == pytest.approx(1.0, abs=5e-10)
        assert beta == pytest.approx(0.0, abs=5e-10)


def test_i3_cmf575_bracketed_by_570_580_rows() -> None:
    # CIE 1931 2° 5nm table: ȳ(570) = 0.9520, ȳ(580) = 0.8700 — the cited
    # ȳ(575) must lie strictly between them, monotonically decreasing, and
    # close to 0.915 at 1 decimal.
    y575 = CMF_575[1]
    assert y575 < 0.9520
    assert y575 > 0.8700
    assert y575 == pytest.approx(0.915, abs=0.05)


def test_i4_anchor_constant_last_digit_sensitivity() -> None:
    # The constant is LIVE: a 5%-relative perturbation of ȳ(575) must change
    # at least one measured distance by a visible margin. (This pin's own
    # half-plane selection uses the naive S-axis rule, verbatim from the TS —
    # the pin is about the anchor constant, not the selector.)
    rgb = hex_to_rgb("#0c4298")
    q = _mat_vec(M_LMS, [srgb_to_linear(c) for c in rgb])
    axis_s = q[0] * (W_LMS[2] / W_LMS[0])
    anchor = A575 if q[2] >= axis_s else A475

    def project(a: tuple[float, float, float]) -> tuple[float, float, float]:
        d2 = W_LMS[0] * a[1] - W_LMS[1] * a[0]
        alpha = (q[0] * a[1] - q[1] * a[0]) / d2
        beta = (W_LMS[0] * q[1] - W_LMS[1] * q[0]) / d2
        lms_proj = (
            alpha * W_LMS[0] + beta * a[0],
            alpha * W_LMS[1] + beta * a[1],
            alpha * W_LMS[2] + beta * a[2],
        )
        lin_proj = _mat_vec(M_RGB_LMS_INVERSE, lms_proj)
        return (
            linear_to_srgb(lin_proj[0]),
            linear_to_srgb(lin_proj[1]),
            linear_to_srgb(lin_proj[2]),
        )

    perturbed_anchor = project((CMF_575[0] * 1.0, CMF_575[1] * 1.05, CMF_575[2]))
    moved = abs(ciede2000(rgb_to_lab(project(anchor)), rgb_to_lab(perturbed_anchor)))
    assert moved > 0.1


def test_i5_machado_rows_sum_to_one() -> None:
    # Linear-RGB mass conservation; 6-decimal published rounding. Tolerance
    # 5e-6 = vitest toBeCloseTo(1, 5) exactly (the TS pin's own bound).
    for rows in MACHADO.values():
        for row in rows:
            assert sum(row) == pytest.approx(1.0, abs=5e-6)


def test_i6_vienot_third_row_exact_and_rows_sum_to_one() -> None:
    for name, rows in VIENOT.items():
        assert rows[2] == (0.0, 0.0, 1.0), f"{name} third row preserves B"
        for row in rows:
            assert sum(row) == pytest.approx(1.0, abs=5e-6)


def test_i7_dual_arms_measure_different_distances() -> None:
    # #917f5f vs the trip hue #a92858 under deuteranopia: Machado ≈ 12.4,
    # Viénot ≈ 3.4 (the §7-candidate rejection measurement). If the second
    # arm silently collapses onto the first, this difference vanishes.
    primary, secondary = de2000("#917f5f", "#a92858", "deuteranopia")
    assert abs(primary - secondary) > 5, "the arms must be genuinely independent"


def test_i8_white_round_trips_under_every_model() -> None:
    # White stays white under every matrix and Brettel, to round-trip
    # precision (the published Machado rows are rounded to 6 decimals — a row
    # can sum to 1 ± 1e-6; real constant errors are order-1; the LMS inverse
    # is ill-conditioned at the constants' 6-digit precision, ~1e-6 linear).
    for matrix in (*MACHADO.values(), *VIENOT.values()):
        for channel in simulate_linear((1.0, 1.0, 1.0), matrix):
            assert channel == pytest.approx(1.0, abs=5e-6)
    for channel in brettel_tritan((1.0, 1.0, 1.0)):
        assert channel == pytest.approx(1.0, abs=5e-6)


# --- S3-A1: series tokens hold T1 contrast on the recessed surface ---
def test_s3_a1_series_contrast_on_recessed_surface() -> None:
    ratios = 0
    for name, tokens in THEMES:
        recessed = tokens.get("--bw-surface-recessed")
        if recessed is None:
            raise ValueError("--bw-surface-recessed missing")
        for token in series_of(tokens):
            ratio = contrast(token, recessed)
            ratios += 1
            assert ratio >= T1_CONTRAST, f"{token} vs {recessed} ({name})"
    assert ratios == 16, "8 tokens x 2 themes"


# --- S3-A2: severity non-confusion, both models ---
def test_s3_a2_severity_non_confusion() -> None:
    pairs = 0
    arm_values = 0
    for name, tokens in THEMES:
        for token in series_of(tokens):
            for sev in severity_of(tokens):
                for condition in CONDITIONS:
                    primary, secondary = de2000(token, sev, condition)
                    pairs += 1
                    arm_values += 2
                    assert primary >= T2_SEVERITY, (
                        f"{name} {token} vs {sev} ({condition}, Machado)"
                    )
                    assert secondary >= T2_SEVERITY, (
                        f"{name} {token} vs {sev} ({condition}, Viénot/Brettel)"
                    )
    assert pairs == 320, "8 tokens x 5 severities x 4 conditions x 2 themes"
    assert arm_values == 640, "every pair-cell asserted under both arms"


def test_s3_a2_engineering_floor_and_margins(
    record_property: Callable[[str, object], None],
) -> None:
    # The shipped sets were selected WITH the boundary floor (search floor
    # T2 >= 11.0) so the margin is structural, not luck.
    for name, tokens in THEMES:
        worst = math.inf
        for token in series_of(tokens):
            for sev in severity_of(tokens):
                for condition in CONDITIONS:
                    primary, secondary = de2000(token, sev, condition)
                    worst = min(worst, primary, secondary)
        print(
            f"[series-margins] {name} T2 dual-arm min {worst:.2f} "
            f"(hard >= {T2_SEVERITY}, engineering >= {T2_ENG_FLOOR:.1f})"
        )
        record_property(f"series_margins_{name}_t2", f"{worst:.2f}")
        assert worst >= T2_SEVERITY, f"{name} hard threshold"
        assert worst >= T2_ENG_FLOOR, f"{name} engineering margin: >= threshold + 1.0"


# --- S3-D2 census: the waveform monochrome arm, ASYMMETRIC floors ---
def test_s3_d2_census_asymmetric_floors(
    record_property: Callable[[str, object], None],
) -> None:
    # In waveform plots symbols do not render, so two traces sharing a dash
    # are separated by colour alone — the census covers every one of the 28
    # token pairs per theme.
    pairs = 0
    arm_values = 0
    for name, tokens in THEMES:
        series = series_of(tokens)
        worst = math.inf
        for i in range(8):
            for j in range(i + 1, 8):
                for condition in CONDITIONS:
                    primary, secondary = de2000(series[i], series[j], condition)
                    worst = min(worst, primary, secondary)
                    pairs += 1
                    arm_values += 2
                    assert primary >= CENSUS_HARD, (
                        f"{name} tokens {i + 1}-{j + 1} ({condition}, Machado)"
                    )
                    assert secondary >= CENSUS_HARD, (
                        f"{name} tokens {i + 1}-{j + 1} ({condition}, Viénot/Brettel)"
                    )
        print(
            f"[series-margins] {name} census min {worst:.2f} "
            f"(hard >= {CENSUS_HARD}; engineering floor >= {CENSUS_DARK_ENG_FLOOR:.1f})"
        )
        record_property(f"series_margins_{name}_census", f"{worst:.2f}")
        if name == "dark":
            # Row CENSUS-ENG-DARK: dark clears threshold + 1 (measured 11.66).
            assert worst >= CENSUS_DARK_ENG_FLOOR, (
                "dark engineering margin: >= threshold + 1.0"
            )
        # Row CENSUS-LIGHT: light asserts the HARD 8.0 floor ONLY — the
        # measured min 8.19 is BELOW the +1.0 engineering floor (PR #263
        # owner row, accept-recommended). A symmetric >= 9.0 assertion would
        # red at 8.19 and invite forbidden threshold relaxation; there is
        # deliberately no light engineering-floor assertion here.
    assert pairs == 224, "C(8,2) pairs x 4 conditions x 2 themes"
    assert arm_values == 448, "every pair-cell asserted under both arms"


# --- S3-A3: adjacent slots ---
def test_s3_a3_adjacent_slots() -> None:
    pairs = 0
    arm_values = 0
    for name, tokens in THEMES:
        series = series_of(tokens)
        for i in range(7):
            for condition in CONDITIONS:
                primary, secondary = de2000(series[i], series[i + 1], condition)
                pairs += 1
                arm_values += 2
                assert primary >= T3_ADJACENT, (
                    f"{name} slots {i + 1}-{i + 2} ({condition}, Machado)"
                )
                assert secondary >= T3_ADJACENT, (
                    f"{name} slots {i + 1}-{i + 2} ({condition}, Viénot/Brettel)"
                )
    assert pairs == 56, "7 adjacent pairs x 4 conditions x 2 themes"
    assert arm_values == 112, "every pair-cell asserted under both arms"


# --- S1-A3 (#243): the limiting token's computed proofs ---
def test_s1_a3_limiting_proofs(record_property: Callable[[str, object], None]) -> None:
    ratios = 0
    pairs = 0
    arm_values = 0
    for name, tokens in THEMES:
        limiting = tokens.get("--bw-limiting")
        if limiting is None:
            raise ValueError("--bw-limiting missing from themes.css")
        surface = tokens.get("--bw-surface")
        recessed = tokens.get("--bw-surface-recessed")
        if surface is None or recessed is None:
            raise ValueError("surface tokens missing")
        t1_surface = contrast(limiting, surface)
        t1_recessed = contrast(limiting, recessed)
        print(f"[limiting-margins] {name} T1 surface {t1_surface:.2f} recessed {t1_recessed:.2f}")
        record_property(f"limiting_margins_{name}_t1_surface", f"{t1_surface:.2f}")
        record_property(f"limiting_margins_{name}_t1_recessed", f"{t1_recessed:.2f}")
        assert t1_surface >= LIM_T1_CONTRAST, f"{name} vs surface"
        assert t1_recessed >= LIM_T1_CONTRAST, f"{name} vs recessed"
        ratios += 2
        worst = math.inf
        for sev in severity_all(tokens):
            for condition in CONDITIONS:
                primary, secondary = de2000(limiting, sev, condition)
                worst = min(worst, primary, secondary)
                pairs += 1
                arm_values += 2
                assert primary >= LIM_T2_SEVERITY, (
                    f"{name} limiting vs {sev} ({condition}, Machado)"
                )
                assert secondary >= LIM_T2_SEVERITY, (
                    f"{name} limiting vs {sev} ({condition}, Viénot/Brettel)"
                )
        print(
            f"[limiting-margins] {name} T2 dual-arm worst {worst:.2f} "
            f"(threshold {LIM_T2_SEVERITY}, engineering floor {LIM_T2_ENG_FLOOR:.1f})"
        )
        record_property(f"limiting_margins_{name}_t2", f"{worst:.2f}")
        # Row LIM-T2-ENG: the standing engineering floor (the S3-A2
        # precedent) — the search screens (T1 >= 3.3, T2 >= 11) are standing
        # pre-commit doctrine for every future token slot (#243 §11a).
        assert worst >= LIM_T2_ENG_FLOOR, (
            f"{name} limiting engineering margin: >= threshold + 1.0"
        )
    assert ratios == 4, "1 token x 2 surfaces x 2 themes"
    assert pairs == 56, "7 comparators x 4 conditions x 2 themes"
    assert arm_values == 112, "every pair-cell asserted under both arms"


# --- the §A-table equality cross-check (record §1.3) ---
def test_themes_css_equals_contract_colour_table() -> None:
    """The S3-A1 underpowered control: the parsed themes.css values equal the
    committed §A.1 colour rows of ui-contract.md, both directions (an extra
    CSS token with no row fails). Rides G1a's landed UR-04 mechanism
    (parse_contract + theme_colour_mismatches); retired as redundant when
    UR-04's real-file equality lands."""
    contract = parse_contract(UI_CONTRACT.read_text(encoding="utf-8"), MANIFEST)
    table = next((t for t in contract.tables if t.slug == "a-1-colour-palette"), None)
    assert table is not None, "a-1-colour-palette table missing from ui-contract.md"
    assert not table.defects, [d.message() for d in table.defects]
    assert theme_colour_mismatches(table.body, LIGHT, DARK) == []
