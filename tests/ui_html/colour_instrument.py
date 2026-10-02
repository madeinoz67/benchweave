"""The computed-colour instrument — the stdlib port of the maths in
``ui/src/series-colors.test.ts`` (G1c design record §1.3).

Every constant is carried VERBATIM from the TS source, including the four
#258-fold corrections already in it: the CIE 1931 575 nm y-bar 0.9152 (the
earlier 0.9917 was y-bar at ~558 nm), the Brettel half-plane selector on the
L/M-side excess ``q · (w × e_S)`` (NOT the raw S coordinate), CIEDE2000's
Sharma et al. 2005 eq. (14) mean hue (halve, THEN add ±360 — porting the
pre-fold post-halving form is exactly the bug the 33-row reference table
catches), and the neutral-severity comparator ``--bw-text-muted`` with
``--bw-border`` pinned alongside.

Hand-rolled stdlib on purpose (record §1.1, the UR-11 ruling): the thresholds
were pre-committed and the palette was selected against THIS instrument, and
the #258 fold proved ΔE00 implementations diverge precisely on the mean-hue
wraparound and the half-plane selector — substituting a library would swap
the instrument out from under the thresholds and make the Sharma-table pin
meaningless. Zero new dependencies, runtime or test-time.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from benchweave_ui_html import artifacts
from benchweave_ui_html.tokens import css_block

#: The token source: the package's vendored themes.css (G1e, UR-10) — the
#: file's bytes are the TS test's bytes, moved verbatim at the cutover and
#: pinned by the assets inventory (artifacts.THEMES_CSS is the one
#: definition; this module rides it — one path, never two).
THEMES_CSS: Final[Path] = artifacts.THEMES_CSS

type Rgb = tuple[float, float, float]
type Lab = tuple[float, float, float]
type Mat = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]

_HEX6: Final = re.compile(r"^#[0-9a-f]{6}$")


# --- colour math: sRGB -> CIELAB (D65) ---
def hex_to_rgb(hex_value: str) -> Rgb:
    """``[1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)``."""
    channels = [int(hex_value[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return channels[0], channels[1], channels[2]


def srgb_to_linear(c: float) -> float:
    """The sRGB transfer: the 0.04045 / 12.92 breakpoint, 1.055 / 2.4 above."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    """The inverse transfer, with the [0, 1] clamp on the input."""
    clamped = min(1.0, max(0.0, c))
    return 12.92 * clamped if clamped <= 0.0031308 else 1.055 * clamped ** (1 / 2.4) - 0.055


M_RGB_XYZ: Final[Mat] = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.072175),
    (0.0193339, 0.119192, 0.9503041),
)
WHITE_D65: Final[Rgb] = (0.95047, 1.0, 1.08883)


def _mat_vec(m: Mat, v: Sequence[float]) -> tuple[float, float, float]:
    out = [sum(x * v[j] for j, x in enumerate(row)) for row in m]
    return out[0], out[1], out[2]


def _f_lab(t: float) -> float:
    """The CIELAB f function with the (6/29)^3 breakpoint."""
    return math.cbrt(t) if t > (6 / 29) ** 3 else (t / (3 * (6 / 29) ** 2)) + 4 / 29


def rgb_to_lab(rgb: Rgb) -> Lab:
    xyz = _mat_vec(M_RGB_XYZ, [srgb_to_linear(c) for c in rgb])
    fx = _f_lab(xyz[0] / WHITE_D65[0])
    fy = _f_lab(xyz[1] / WHITE_D65[1])
    fz = _f_lab(xyz[2] / WHITE_D65[2])
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def ciede2000(lab1: Lab, lab2: Lab) -> float:
    """CIEDE2000 (kL = kC = kH = 1), the Sharma et al. 2005 formulation.

    The mean hue is eq. (14): (h1'+h2')/2 when |h1'-h2'| <= 180; otherwise
    (h1'+h2'+360)/2 when h1'+h2' < 360, and (h1'+h2'-360)/2 above. (Adding
    ±360 AFTER halving — the pre-#258-fold form — is wrong by 180 degrees
    exactly on the wraparound pairs of the reference table.)
    """
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar**7 / (Cbar**7 + 25**7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = math.hypot(a1p, b1)
    C2p = math.hypot(a2p, b2)

    def h(a: float, b: float) -> float:
        # JS: ``x % 360 + (x % 360 < 0 ? 360 : 0)`` — the JS remainder keeps
        # the dividend's sign; Python's ``%`` with a positive modulus is
        # already non-negative, so the direct modulo is provably equal.
        return 0.0 if a == 0 and b == 0 else math.degrees(math.atan2(b, a)) % 360.0

    h1p = h(a1p, b1)
    h2p = h(a2p, b2)
    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = 0.0
    if C1p * C2p != 0:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin((dhp * math.pi) / 360)
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hbp = h1p + h2p
    if C1p * C2p != 0:
        if abs(h1p - h2p) <= 180:
            hbp = (h1p + h2p) / 2
        elif h1p + h2p < 360:
            hbp = (h1p + h2p + 360) / 2
        else:
            hbp = (h1p + h2p - 360) / 2
    T = (
        1
        - 0.17 * math.cos(((hbp - 30) * math.pi) / 180)
        + 0.24 * math.cos((2 * hbp * math.pi) / 180)
        + 0.32 * math.cos(((3 * hbp + 6) * math.pi) / 180)
        - 0.2 * math.cos(((4 * hbp - 63) * math.pi) / 180)
    )
    d_theta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    RC = 2 * math.sqrt(Cbp**7 / (Cbp**7 + 25**7))
    SL = 1 + (0.015 * (Lbp - 50) ** 2) / math.sqrt(20 + (Lbp - 50) ** 2)
    SC = 1 + 0.045 * Cbp
    SH = 1 + 0.015 * Cbp * T
    RT = -math.sin((2 * d_theta * math.pi) / 180) * RC
    return math.sqrt(
        (dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH)
    )


def _luminance(hex_value: str) -> float:
    lin = [srgb_to_linear(c) for c in hex_to_rgb(hex_value)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(hex1: str, hex2: str) -> float:
    """WCAG 2.x relative-luminance contrast ratio, (hi + 0.05) / (lo + 0.05)."""
    hi, lo = sorted((_luminance(hex1), _luminance(hex2)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# --- CVD models, all in linear RGB ---
# Machado, Oliveira & Fernandes (2009), severity 1.0, Table II as commonly
# reproduced.
MACHADO: Final[dict[str, Mat]] = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.01182, 0.04294, 0.968881),
    ),
    "tritanopia": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.3039),
    ),
}
# Viénot, Brettel & Mollon (1999), linear-RGB dichromacy replacements as
# commonly reproduced.
VIENOT: Final[dict[str, Mat]] = {
    "protanopia": (
        (0.567, 0.433, 0.0),
        (0.558, 0.442, 0.0),
        (0.0, 0.0, 1.0),
    ),
    "deuteranopia": (
        (0.625, 0.375, 0.0),
        (0.7, 0.3, 0.0),
        (0.0, 0.0, 1.0),
    ),
}

# Brettel, Viénot & Mollon (1997): two-half-plane projection in the Viénot
# LMS basis. Anchor LMS vectors from CIE 1931 2° CMFs (575 nm:
# x̄ 0.8425 ȳ 0.9917 z̄ 0.0000; 475 nm: x̄ 0.1421 ȳ 0.1126 z̄ 1.0419 — the
# ȳ values as cited by the TS source's provenance comment) converted through
# XYZ → linear RGB → LMS; the 575 nm ȳ actually carried is the corrected
# 5 nm-table value 0.9152 below.
M_LMS: Final[Mat] = (
    (17.8824, 43.5181, 4.9359),
    (3.4557, 27.1554, 3.867),
    (0.0295, 0.1843, 1.467),
)
M_XYZ_RGB: Final[Mat] = (
    (3.2404542, -1.5371385, -0.4985314),
    (-0.969266, 1.8760108, 0.041556),
    (0.0556434, -0.2040259, 1.0572252),
)


def _cramer_inverse(m: Mat) -> Mat:
    """Cramer's rule inverse of M_LMS (the TS computes it once, closed over)."""
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return (
        ((e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det),
        ((f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det),
        ((d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det),
    )


M_RGB_LMS_INVERSE: Final[Mat] = _cramer_inverse(M_LMS)

W_LMS: Final[tuple[float, float, float]] = _mat_vec(M_LMS, (1.0, 1.0, 1.0))


def _anchor_lms(xyz: Sequence[float]) -> tuple[float, float, float]:
    return _mat_vec(M_LMS, _mat_vec(M_XYZ_RGB, xyz))


# CIE 1931 2° 5 nm table rows at the Brettel anchors (575 nm, 475 nm): the
# 575 nm ȳ is the 5 nm table value 0.9152 (the earlier 0.9917 was wrong —
# that is ȳ(≈558 nm); bracketing by the 570/580 rows is pinned in the proofs).
CMF_575: Final[tuple[float, float, float]] = (0.8425, 0.9152, 0.0)
CMF_475: Final[tuple[float, float, float]] = (0.1421, 0.1126, 1.0419)
A575: Final[tuple[float, float, float]] = _anchor_lms(CMF_575)
A475: Final[tuple[float, float, float]] = _anchor_lms(CMF_475)

# w × e_S with e_S = (0, 0, 1) is (wy, -wx, 0).
_HALF_PLANE_NORMAL: Final[tuple[float, float, float]] = (W_LMS[1], -W_LMS[0], 0.0)


def brettel_tritan(rgb: Rgb) -> Rgb:
    """Brettel tritanopia: project along the S fundamental axis onto the half
    plane (span of white and the 575/475 nm anchor).

    The half is selected by the sign of q·(w × e_S) — the L/M-side excess
    over the neutral plane spanned by white and the S axis (NOT the raw S
    coordinate: the neutral plane tilts in LMS, so an S-threshold misassigns
    the anchors — #258 fold, pinned by the anchor fixed-point proof). Solving
    q − λ·e_S = α·W + β·A reduces to a 2×2 system on the first two rows (the
    third fixes λ).
    """
    lin = [srgb_to_linear(c) for c in rgb]
    q = _mat_vec(M_LMS, lin)
    side = q[0] * _HALF_PLANE_NORMAL[0] + q[1] * _HALF_PLANE_NORMAL[1]
    anchor = A575 if side >= 0 else A475
    d2 = W_LMS[0] * anchor[1] - W_LMS[1] * anchor[0]
    alpha = (q[0] * anchor[1] - q[1] * anchor[0]) / d2
    beta = (W_LMS[0] * q[1] - W_LMS[1] * q[0]) / d2
    lms_proj = (
        alpha * W_LMS[0] + beta * anchor[0],
        alpha * W_LMS[1] + beta * anchor[1],
        alpha * W_LMS[2] + beta * anchor[2],
    )
    lin_proj = _mat_vec(M_RGB_LMS_INVERSE, lms_proj)
    return (
        linear_to_srgb(lin_proj[0]),
        linear_to_srgb(lin_proj[1]),
        linear_to_srgb(lin_proj[2]),
    )


def simulate_linear(rgb: Rgb, matrix: Mat) -> Rgb:
    lin = _mat_vec(matrix, [srgb_to_linear(c) for c in rgb])
    return (
        linear_to_srgb(lin[0]),
        linear_to_srgb(lin[1]),
        linear_to_srgb(lin[2]),
    )


CONDITIONS: Final[tuple[str, ...]] = ("normal", "deuteranopia", "protanopia", "tritanopia")


def labs_for(hex_value: str, condition: str) -> tuple[Lab, Lab]:
    """The two independent model arms per condition: primary = Machado;
    secondary = Viénot (prot/deut) or Brettel (trit). Normal is
    model-independent (both arms identical)."""
    rgb = hex_to_rgb(hex_value)
    if condition == "normal":
        lab = rgb_to_lab(rgb)
        return (lab, lab)
    second = brettel_tritan(rgb) if condition == "tritanopia" else simulate_linear(
        rgb, VIENOT[condition]
    )
    return (rgb_to_lab(simulate_linear(rgb, MACHADO[condition])), rgb_to_lab(second))


def de2000(hex1: str, hex2: str, condition: str) -> tuple[float, float]:
    """(primary, secondary) ΔE00 between two token values under a condition.

    BOTH arms are asserted by every proof — the record's underpowered
    direction: a dual-arm disagreement on any pair is inconclusive for that
    pair and escalates (a one-arm failure is a RED, which IS the escalation;
    the suite never passes a disagreement).
    """
    a1, a2 = labs_for(hex1, condition)
    b1, b2 = labs_for(hex2, condition)
    return (ciede2000(a1, b1), ciede2000(a2, b2))


# --- the tokens under test, parsed from themes.css (same bytes as the TS) ---
def theme_tokens(selector: str) -> dict[str, str]:
    """``themeTokens`` ported: declarations from every rule block whose
    selector contains the fragment. The regex shape is G1a's landed
    ``css_block`` (the same port, record §1.1 — skeleton ownership); reading
    the file fails loud here so a missing themes.css is a collection-time
    error, never a silent skip."""
    if not THEMES_CSS.is_file():
        raise FileNotFoundError(
            f"themes.css not found at {THEMES_CSS} (the package's vendored "
            "asset — G1e's re-point landed; a missing file is a packaging "
            "defect, never a silent skip)"
        )
    return css_block(THEMES_CSS.read_text(encoding="utf-8"), selector)


LIGHT: Final[dict[str, str]] = theme_tokens('data-theme="light"')
DARK: Final[dict[str, str]] = theme_tokens('data-theme="dark"')
THEMES: Final[tuple[tuple[str, dict[str, str]], ...]] = (("light", LIGHT), ("dark", DARK))

SEVERITY_HUE_TOKENS: Final[tuple[str, ...]] = (
    "--bw-advisory",
    "--bw-warning",
    "--bw-critical",
    "--bw-trip",
    "--bw-success",
)


def series_of(tokens: Mapping[str, str]) -> list[str]:
    out: list[str] = []
    for i in range(8):
        value = tokens.get(f"--bw-series-{i + 1}")
        if value is None or _HEX6.match(value) is None:
            msg = f"--bw-series-{i + 1} missing or malformed in themes.css"
            raise ValueError(msg)
        out.append(value)
    return out


def severity_of(tokens: Mapping[str, str]) -> list[str]:
    out: list[str] = []
    for name in SEVERITY_HUE_TOKENS:
        value = tokens.get(name)
        if value is None:
            raise ValueError(f"{name} missing from themes.css")
        out.append(value)
    return out


def severity_all(tokens: Mapping[str, str]) -> list[str]:
    """The 7-comparator set (#243 fold rows 1+11): the five severity HUES
    plus the neutral severity's actual rendering — --bw-text-muted — plus
    --bw-border (measured safe, pinned anyway). The pathological
    byte-identical-to-muted case is caught BY this census, not by accident."""
    out = severity_of(tokens)
    neutral_muted = tokens.get("--bw-text-muted")
    if neutral_muted is None:
        raise ValueError("--bw-text-muted missing (the neutral severity's rendering)")
    border = tokens.get("--bw-border")
    if border is None:
        raise ValueError("--bw-border missing")
    return [*out, neutral_muted, border]
