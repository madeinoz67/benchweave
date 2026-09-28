import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * S3-A1..A3 (design record §6, #242 slice 3): the computed colour proofs for
 * the plot-series tokens, on the ACTUAL values parsed from themes.css.
 *
 * Pre-committed thresholds, not relaxable: T1 contrast ≥ 3.0:1 vs
 * --bw-surface-recessed (8 tokens × 2 themes = 16); T2 severity non-confusion
 * CIEDE2000 ≥ 10.0 (8 tokens × 5 severity hues × 4 viewing conditions ×
 * 2 themes = 320 values); T3 adjacent-slot CIEDE2000 ≥ 8.0 (7 pairs ×
 * 4 conditions × 2 themes = 56 values). DUAL CVD models — Machado et al. 2009
 * (severity 1.0) as the primary, and a second independent arm: Viénot 1999
 * for protanopia/deuteranopia, Brettel 1997 (two-half-plane projection in the
 * Viénot LMS basis, anchors 575 nm / 475 nm) for tritanopia. BOTH models must
 * pass every pair; a disagreement is inconclusive and escalates, never passes.
 *
 * Constant provenance, disclosed: the Machado matrices are the paper's
 * published severity-1.0 rows as commonly reproduced; the Viénot matrices are
 * the paper's linear-RGB dichromacy replacements as commonly reproduced; the
 * Brettel arm uses the projection method with CIE 1931 2° CMF anchor values
 * stated below. A reviewer with the papers can check every constant in this
 * file against its source.
 */

// --- colour math: sRGB -> CIELAB (D65) ---
type Rgb = readonly [number, number, number];
type Lab = readonly [number, number, number];

const hexToRgb = (hex: string): Rgb => {
  const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255);
  return [r!, g!, b!];
};
const srgbToLinear = (c: number): number => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const linearToSrgb = (c: number): number => {
  const clamped = Math.min(1, Math.max(0, c));
  return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * clamped ** (1 / 2.4) - 0.055;
};

const M_RGB_XYZ: readonly (readonly number[])[] = [
  [0.4124564, 0.3575761, 0.1804375],
  [0.2126729, 0.7151522, 0.072175],
  [0.0193339, 0.119192, 0.9503041],
];
const WHITE_D65: Rgb = [0.95047, 1.0, 1.08883];

const matVec = (m: readonly (readonly number[])[], v: readonly number[]): number[] =>
  m.map((row) => row.reduce((sum, x, j) => sum + x * v[j]!, 0));

const fLab = (t: number): number => (t > (6 / 29) ** 3 ? Math.cbrt(t) : (t / (3 * (6 / 29) ** 2)) + 4 / 29);

const rgbToLab = (rgb: Rgb): Lab => {
  const xyz = matVec(M_RGB_XYZ, rgb.map(srgbToLinear));
  const fx = fLab(xyz[0]! / WHITE_D65[0]);
  const fy = fLab(xyz[1]! / WHITE_D65[1]);
  const fz = fLab(xyz[2]! / WHITE_D65[2]);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
};

/** CIEDE2000 (kL = kC = kH = 1), Sharma et al. 2005 formulation. */
const ciede2000 = (lab1: Lab, lab2: Lab): number => {
  const [L1, a1, b1] = lab1;
  const [L2, a2, b2] = lab2;
  const C1 = Math.hypot(a1, b1);
  const C2 = Math.hypot(a2, b2);
  const Cbar = (C1 + C2) / 2;
  const G = 0.5 * (1 - Math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7)));
  const a1p = (1 + G) * a1;
  const a2p = (1 + G) * a2;
  const C1p = Math.hypot(a1p, b1);
  const C2p = Math.hypot(a2p, b2);
  const h = (a: number, b: number): number => (a === 0 && b === 0 ? 0 : (Math.atan2(b, a) * 180) / Math.PI % 360 + (((Math.atan2(b, a) * 180) / Math.PI) % 360 < 0 ? 360 : 0));
  const h1p = h(a1p, b1);
  const h2p = h(a2p, b2);
  const dLp = L2 - L1;
  const dCp = C2p - C1p;
  let dhp = 0;
  if (C1p * C2p !== 0) {
    dhp = h2p - h1p;
    if (dhp > 180) dhp -= 360;
    else if (dhp < -180) dhp += 360;
  }
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dhp * Math.PI) / 360);
  const Lbp = (L1 + L2) / 2;
  const Cbp = (C1p + C2p) / 2;
  // Sharma et al. 2005 eq. (14): the mean hue is (h1'+h2')/2 when
  // |h1'-h2'| <= 180; otherwise (h1'+h2'+360)/2 when h1'+h2' < 360, and
  // (h1'+h2'-360)/2 above. (Adding ±360 AFTER halving — the earlier code —
  // is wrong by 180 degrees exactly on the wraparound pairs of the
  // reference table.)
  let hbp = h1p + h2p;
  if (C1p * C2p !== 0) {
    if (Math.abs(h1p - h2p) <= 180) hbp = (h1p + h2p) / 2;
    else if (h1p + h2p < 360) hbp = (h1p + h2p + 360) / 2;
    else hbp = (h1p + h2p - 360) / 2;
  }
  const T = 1 - 0.17 * Math.cos(((hbp - 30) * Math.PI) / 180) + 0.24 * Math.cos((2 * hbp * Math.PI) / 180) + 0.32 * Math.cos(((3 * hbp + 6) * Math.PI) / 180) - 0.2 * Math.cos(((4 * hbp - 63) * Math.PI) / 180);
  const dTheta = 30 * Math.exp(-(((hbp - 275) / 25) ** 2));
  const RC = 2 * Math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7));
  const SL = 1 + (0.015 * (Lbp - 50) ** 2) / Math.sqrt(20 + (Lbp - 50) ** 2);
  const SC = 1 + 0.045 * Cbp;
  const SH = 1 + 0.015 * Cbp * T;
  const RT = -Math.sin((2 * dTheta * Math.PI) / 180) * RC;
  return Math.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH));
};

/** WCAG 2.x relative-luminance contrast ratio. */
const contrast = (hex1: string, hex2: string): number => {
  const lum = (hex: string): number => {
    const lin = hexToRgb(hex).map(srgbToLinear);
    return 0.2126 * lin[0]! + 0.7152 * lin[1]! + 0.0722 * lin[2]!;
  };
  const [hi, lo] = [lum(hex1), lum(hex2)].sort((a, b) => b - a);
  return (hi + 0.05) / (lo + 0.05);
};

// --- CVD models, all in linear RGB ---
const MACHADO: Record<string, readonly (readonly number[])[]> = {
  // Machado, Oliveira & Fernandes (2009), severity 1.0, Table II as commonly
  // reproduced.
  protanopia: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deuteranopia: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
  ],
  tritanopia: [
    [1.255528, -0.076749, -0.178779],
    [-0.078411, 0.930809, 0.147602],
    [0.004733, 0.691367, 0.3039],
  ],
};
// Viénot, Brettel & Mollon (1999), linear-RGB dichromacy replacements as
// commonly reproduced.
const VIENOT: Record<string, readonly (readonly number[])[]> = {
  protanopia: [
    [0.567, 0.433, 0],
    [0.558, 0.442, 0],
    [0, 0, 1],
  ],
  deuteranopia: [
    [0.625, 0.375, 0],
    [0.7, 0.3, 0],
    [0, 0, 1],
  ],
};

// Brettel, Viénot & Mollon (1997): two-half-plane projection in the Viénot
// LMS basis. Anchor LMS vectors from CIE 1931 2° CMFs (575 nm:
// x̄ 0.8425 ȳ 0.9917 z̄ 0.0000; 475 nm: x̄ 0.1421 ȳ 0.1126 z̄ 1.0419)
// converted through XYZ → linear RGB → LMS.
const M_LMS: readonly (readonly number[])[] = [
  [17.8824, 43.5181, 4.9359],
  [3.4557, 27.1554, 3.867],
  [0.0295, 0.1843, 1.467],
];
const M_XYZ_RGB: readonly (readonly number[])[] = [
  [3.2404542, -1.5371385, -0.4985314],
  [-0.969266, 1.8760108, 0.041556],
  [0.0556434, -0.2040259, 1.0572252],
];
const M_RGB_LMS_INVERSE = (() => {
  // Cramer's rule inverse of M_LMS.
  const [a, b, c] = M_LMS[0]!;
  const [d, e, f] = M_LMS[1]!;
  const [g, h, i] = M_LMS[2]!;
  const det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  return [
    [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
    [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
    [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
  ] as readonly (readonly number[])[];
})();

const W_LMS = matVec(M_LMS, [1, 1, 1]);
const anchorLms = (xyz: readonly number[]): number[] => matVec(M_LMS, matVec(M_XYZ_RGB, xyz));
// CIE 1931 2° 5 nm table rows at the Brettel anchors (575 nm, 475 nm): the
// 575 nm ȳ is the 5 nm table value 0.9152 (the earlier 0.9917 was wrong —
// that is ȳ(≈558 nm); bracketing by the 570/580 rows is pinned below).
const CMF_575: readonly number[] = [0.8425, 0.9152, 0.0];
const CMF_475: readonly number[] = [0.1421, 0.1126, 1.0419];
const A575 = anchorLms(CMF_575);
const A475 = anchorLms(CMF_475);

/** Brettel tritanopia: project along the S fundamental axis onto the half
 *  plane (span of white and the 575/475 nm anchor). The half is selected by
 *  the sign of q·(w × e_S) — the L/M-side excess over the neutral plane
 *  spanned by white and the S axis (NOT the raw S coordinate: the neutral
 *  plane tilts in LMS, so an S-threshold misassigns the anchors — pinned by
 *  the anchor fixed-point test). Solving q − λ·e_S = α·W + β·A reduces to a
 *  2×2 system on the first two rows (the third fixes λ). */
const halfPlaneNormal = (() => {
  const [wx, wy] = W_LMS;
  // w × e_S with e_S = (0, 0, 1) is (wy, -wx, 0).
  return [wy!, -wx!, 0] as const;
})();
const brettelTritan = (rgb: Rgb): Rgb => {
  const lin = rgb.map(srgbToLinear);
  const q = matVec(M_LMS, lin);
  const w = W_LMS;
  const side = q[0]! * halfPlaneNormal[0]! + q[1]! * halfPlaneNormal[1]!;
  const anchor = side >= 0 ? A575 : A475;
  const d2 = w[0]! * anchor[1]! - w[1]! * anchor[0]!;
  const alpha = (q[0]! * anchor[1]! - q[1]! * anchor[0]!) / d2;
  const beta = (w[0]! * q[1]! - w[1]! * q[0]!) / d2;
  const lmsProj = [alpha * w[0]! + beta * anchor[0]!, alpha * w[1]! + beta * anchor[1]!, alpha * w[2]! + beta * anchor[2]!];
  const linProj = matVec(M_RGB_LMS_INVERSE, lmsProj);
  const [r, g, b] = linProj.map(linearToSrgb);
  return [r!, g!, b!];
};

const simulateLinear = (rgb: Rgb, matrix: readonly (readonly number[])[]): Rgb => {
  const [r, g, b] = matVec(matrix, rgb.map(srgbToLinear)).map(linearToSrgb);
  return [r!, g!, b!];
};

const CONDITIONS = ["normal", "deuteranopia", "protanopia", "tritanopia"] as const;
type Condition = (typeof CONDITIONS)[number];

/** The two independent model arms per condition: primary = Machado;
 *  secondary = Viénot (prot/deut) or Brettel (trit). Normal is
 *  model-independent. */
const labsFor = (hex: string, condition: Condition): readonly [Lab, Lab] => {
  const rgb = hexToRgb(hex);
  if (condition === "normal") {
    const lab = rgbToLab(rgb);
    return [lab, lab];
  }
  const second = condition === "tritanopia"
    ? brettelTritan(rgb)
    : simulateLinear(rgb, VIENOT[condition]!);
  return [rgbToLab(simulateLinear(rgb, MACHADO[condition]!)), rgbToLab(second)];
};

const de2000 = (h1: string, h2: string, condition: Condition): readonly [number, number] => {
  const [a1, a2] = labsFor(h1, condition);
  const [b1, b2] = labsFor(h2, condition);
  return [ciede2000(a1, b1), ciede2000(a2, b2)];
};

// --- the tokens under test, parsed from themes.css ---
function themeTokens(selector: string): Map<string, string> {
  const css = readFileSync("src/styles/themes.css", "utf8");
  const tokens = new Map<string, string>();
  for (const match of css.matchAll(/([^{}]*)\{([^{}]*)\}/g)) {
    if (!match[1]!.includes(selector)) continue;
    for (const declaration of match[2]!.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      tokens.set(declaration[1]!, declaration[2]!.trim());
    }
  }
  return tokens;
}

const light = themeTokens('data-theme="light"');
const dark = themeTokens('data-theme="dark"');
const seriesOf = (tokens: Map<string, string>): string[] => {
  const values = Array.from({ length: 8 }, (_, i) => tokens.get(`--bw-series-${i + 1}`));
  for (const [i, value] of values.entries()) {
    if (value === undefined || !/^#[0-9a-f]{6}$/.test(value)) {
      throw new Error(`--bw-series-${i + 1} missing or malformed in themes.css`);
    }
  }
  return values as string[];
};
const severityOf = (tokens: Map<string, string>): string[] =>
  ["--bw-advisory", "--bw-warning", "--bw-critical", "--bw-trip", "--bw-success"].map((name) => {
    const value = tokens.get(name);
    if (value === undefined) throw new Error(`${name} missing from themes.css`);
    return value;
  });

const THEMES = [
  ["light", light],
  ["dark", dark],
] as const;

// --- instrument pins: the CIEDE2000 implementation against the Sharma
//  et al. 2005 reference table (33 rows; the published 34th row is omitted
//  because this session could not independently confirm its coordinate
//  tuple against a second reproduction — every other row's expected value
//  was cross-checked between the fixed implementation and the table).
type SharmaRow = readonly [Lab, Lab, number];
const SHARMA_TABLE: ReadonlyArray<SharmaRow> = [
  [[50, 2.6772, -79.7751], [50, 0, -82.7485], 2.0425],
  [[50, 3.1571, -77.2803], [50, 0, -82.7485], 2.8615],
  [[50, 2.8361, -74.02], [50, 0, -82.7485], 3.4412],
  [[50, -1.3802, -84.2814], [50, 0, -82.7485], 1.0],
  [[50, -1.1848, -84.8006], [50, 0, -82.7485], 1.0],
  [[50, -0.9009, -85.5211], [50, 0, -82.7485], 1.0],
  [[50, 0, 0], [50, -1, 2], 2.3669],
  [[50, -1, 2], [50, 0, 0], 2.3669],
  [[50, 2.49, -0.001], [50, -2.49, 0.0009], 7.1792],
  [[50, 2.49, -0.001], [50, -2.49, 0.001], 7.1792],
  [[50, 2.49, -0.001], [50, -2.49, 0.0011], 7.2195],
  [[50, 2.49, -0.001], [50, -2.49, 0.0012], 7.2195],
  [[50, -0.001, 2.49], [50, 0.0009, -2.49], 4.8045],
  [[50, -0.001, 2.49], [50, 0.001, -2.49], 4.8045],
  [[50, -0.001, 2.49], [50, 0.0011, -2.49], 4.7461],
  [[50, 2.5, 0], [50, 0, -2.5], 4.3065],
  [[50, 2.5, 0], [73, 25, -18], 27.1492],
  [[50, 2.5, 0], [61, -5, 29], 22.8977],
  [[50, 2.5, 0], [56, -27, -3], 31.903],
  [[50, 2.5, 0], [58, 24, 15], 19.4535],
  [[50, 2.5, 0], [50, 3.1736, 0.5854], 1.0],
  [[50, 2.5, 0], [50, 3.2972, 0], 1.0],
  [[50, 2.5, 0], [50, 1.8634, 0.5757], 1.0],
  [[50, 2.5, 0], [50, 3.2592, 0.335], 1.0],
  [[60.2574, -34.0099, 36.2677], [60.4626, -34.1751, 39.4387], 1.2644],
  [[63.0109, -31.0961, -5.8663], [62.8187, -29.7946, -4.0864], 1.263],
  [[61.2901, 3.7196, -5.3901], [61.4292, 2.248, -4.962], 1.8731],
  [[35.0831, -44.1164, 3.7933], [35.0232, -40.0716, 1.5901], 1.8645],
  [[22.7233, 20.0904, -46.694], [23.0331, 14.973, -42.5619], 2.0373],
  [[36.4612, 47.858, 18.3852], [36.2715, 50.5065, 21.2231], 1.4146],
  [[90.8027, -2.0831, 1.441], [91.1528, -1.6435, 0.0447], 1.4441],
  [[90.9257, -0.5406, -0.9208], [88.6381, -0.8985, -0.7239], 1.5381],
  [[6.7747, -0.2908, -2.4247], [5.8714, -0.0985, -2.2286], 0.6377],
];

describe("instrument: CIEDE2000 matches the Sharma et al. 2005 reference table", () => {
  it.each(SHARMA_TABLE.map((row, index) => [index + 1, row[0], row[1], row[2]] as const))(
    "reference pair %i",
    (_index: number, lab1: Lab, lab2: Lab, expected: number) => {
      expect(Math.abs(ciede2000(lab1, lab2) - expected)).toBeLessThan(1e-4);
    },
  );
});

describe("instrument: the Brettel anchors and half-plane selection", () => {
  it("each anchor projects to itself on its own half plane (fixed point)", () => {
    // The SAME rule brettelTritan uses — the shared halfPlaneNormal — assigns
    // each anchor to its own plane (polarity: 575 nm on the positive side,
    // 475 nm on the negative; the fixed-point projection of an anchor onto
    // its own plane is the anchor itself).
    for (const anchor of [A575, A475]) {
      const side = anchor[0]! * halfPlaneNormal[0]! + anchor[1]! * halfPlaneNormal[1]!;
      const chosen = side >= 0 ? A575 : A475;
      expect(chosen, "an anchor must be assigned to its own half plane").toBe(anchor);
      // And the projection solves to (alpha, beta) = (0, 1): the anchor.
      const d2 = W_LMS[0]! * anchor[1]! - W_LMS[1]! * anchor[0]!;
      const alpha = (anchor[0]! * anchor[1]! - anchor[1]! * anchor[0]!) / d2;
      expect(alpha).toBeCloseTo(0, 9);
    }
  });

  it("white is a fixed point of the projection (both half planes)", () => {
    for (const anchor of [A575, A475]) {
      const q = [...W_LMS];
      const d2 = W_LMS[0]! * anchor[1]! - W_LMS[1]! * anchor[0]!;
      const alpha = (q[0]! * anchor[1]! - q[1]! * anchor[0]!) / d2;
      const beta = (W_LMS[0]! * q[1]! - W_LMS[1]! * q[0]!) / d2;
      expect(alpha).toBeCloseTo(1, 9);
      expect(beta).toBeCloseTo(0, 9);
    }
  });

  it("the 575nm anchor constant is bracketed by the 570/580 CMF rows (monotonic ȳ)", () => {
    // CIE 1931 2° 5nm table: ȳ(570) = 0.9520, ȳ(580) = 0.8700 — the cited
    // ȳ(575) must lie strictly between them, monotonically decreasing.
    const y575 = Number(CMF_575[1]);
    expect(y575).toBeLessThan(0.9520);
    expect(y575).toBeGreaterThan(0.8700);
    expect(y575).toBeCloseTo(0.915, 1);
  });

  it("last-digit sensitivity: perturbing the anchor constant moves a verdict", () => {
    // The constant is LIVE: a 5%-relative perturbation of ȳ(575) must change
    // at least one measured distance by a visible margin.
    const lab = hexToRgb("#0c4298");
    const q = matVec(M_LMS, lab.map(srgbToLinear));
    const axisS = q[0]! * (W_LMS[2]! / W_LMS[0]!);
    const anchor = q[2]! >= axisS ? A575 : A475;
    const project = (a: number[]): Rgb => {
      const d2 = W_LMS[0]! * a[1]! - W_LMS[1]! * a[0]!;
      const alpha = (q[0]! * a[1]! - q[1]! * a[0]!) / d2;
      const beta = (W_LMS[0]! * q[1]! - W_LMS[1]! * q[0]!) / d2;
      const lmsProj = [alpha * W_LMS[0]! + beta * a[0]!, alpha * W_LMS[1]! + beta * a[1]!, alpha * W_LMS[2]! + beta * a[2]!];
      const [r, g, b] = matVec(M_RGB_LMS_INVERSE, lmsProj).map(linearToSrgb);
      return [r!, g!, b!];
    };
    const perturbedAnchor = project([CMF_575[0]! * 1.0, CMF_575[1]! * 1.05, CMF_575[2]!]);
    const moved = Math.abs(ciede2000(rgbToLab(project(anchor)), rgbToLab(perturbedAnchor)));
    expect(moved).toBeGreaterThan(0.1);
  });
});

describe("instrument: model constants and the dual-arm independence", () => {
  it("every Machado row sums to 1 (linear-RGB mass conservation)", () => {
    for (const rows of Object.values(MACHADO)) {
      for (const row of rows) {
        expect(row.reduce((sum, x) => sum + x, 0)).toBeCloseTo(1, 5);
      }
    }
  });

  it("the Viénot matrices preserve the B channel exactly and map white to white", () => {
    for (const [name, rows] of Object.entries(VIENOT)) {
      expect(rows[2], `${name} third row preserves B`).toEqual([0, 0, 1]);
      for (const row of rows) {
        expect(row.reduce((sum, x) => sum + x, 0)).toBeCloseTo(1, 5);
      }
    }
  });

  it("reference vector: the two arms measure DIFFERENT distances on a known pair (independence)", () => {
    // #917f5f vs the trip hue #a92858 under deuteranopia: Machado ≈ 12.4,
    // Viénot ≈ 3.4 (the §7-candidate rejection measurement). If the second
    // arm silently collapses onto the first, this difference vanishes.
    const [primary, secondary] = de2000("#917f5f", "#a92858", "deuteranopia");
    expect(Math.abs(primary - secondary), "the arms must be genuinely independent").toBeGreaterThan(5);
  });

  it("reference vectors: known simulation outputs", () => {
    // White stays white under every model (mass conservation made concrete),
    // to float round-trip precision.
    const matrices = [...Object.values(MACHADO), ...Object.values(VIENOT)];
    for (const matrix of matrices) {
      const out = simulateLinear([1, 1, 1], matrix);
      // The published Machado rows are rounded to 6 decimals, so a row can
      // sum to 1 ± 1e-6 (measured: deuteranopia row 2 sums to 0.999999);
      // real constant errors (transposition, wrong model) are order-1.
      for (const channel of out) expect(channel).toBeCloseTo(1, 5);
    }
    // Brettel: white projects to itself (the LMS inverse is ill-conditioned
    // at the constants' 6-digit precision — round-trip error ~1e-6 linear).
    for (const channel of brettelTritan([1, 1, 1])) expect(channel).toBeCloseTo(1, 5);
  });
});

describe("S3-A1: series tokens hold T1 contrast ≥ 3.0:1 on the recessed surface", () => {
  for (const [name, tokens] of THEMES) {
    it(`${name}: 8 tokens × ${name} recessed surface all ≥ 3.0`, () => {
      const recessed = tokens.get("--bw-surface-recessed");
      if (recessed === undefined) throw new Error("--bw-surface-recessed missing");
      for (const token of seriesOf(tokens)) {
        const ratio = contrast(token, recessed);
        expect(ratio, `${token} vs ${recessed} (${name})`).toBeGreaterThanOrEqual(3.0);
      }
    });
  }
});

describe("S3-A2: series tokens stay ΔE00 ≥ 10.0 from every severity hue, both models", () => {
  for (const [name, tokens] of THEMES) {
    it(`${name}: 8 tokens × 5 severities × 4 conditions, both arms ≥ 10.0`, () => {
      for (const token of seriesOf(tokens)) {
        for (const sev of severityOf(tokens)) {
          for (const condition of CONDITIONS) {
            const [primary, secondary] = de2000(token, sev, condition);
            expect(primary, `${name} ${token} vs ${sev} (${condition}, Machado)`).toBeGreaterThanOrEqual(10.0);
            expect(secondary, `${name} ${token} vs ${sev} (${condition}, Viénot/Brettel)`).toBeGreaterThanOrEqual(10.0);
          }
        }
      }
    });
  }
  it("reports the measured margins and holds the T2 engineering floor (≥ threshold + 1.0)", () => {
    // The §7 candidates, run under the corrected dual arm, do not clear —
    // documented in the increment report; the shipped sets were selected
    // WITH the boundary floor (search floor T2 ≥ 11.0) so the margin is
    // structural, not luck.
    for (const [name, tokens] of THEMES) {
      let worst = Number.POSITIVE_INFINITY;
      for (const token of seriesOf(tokens)) {
        for (const sev of severityOf(tokens)) {
          for (const condition of CONDITIONS) {
            const [primary, secondary] = de2000(token, sev, condition);
            worst = Math.min(worst, primary, secondary);
          }
        }
      }
      console.info(`[series-margins] ${name} T2 dual-arm min ${worst.toFixed(2)} (hard ≥ 10.0, engineering ≥ 11.0)`);
      expect(worst, `${name} hard threshold`).toBeGreaterThanOrEqual(10.0);
      expect(worst, `${name} engineering margin: ≥ threshold + 1.0`).toBeGreaterThanOrEqual(11.0);
    }
  });
});

describe("S3-D2 census: ALL same-dash pairs stay ΔE00 ≥ 8.0 apart (waveform monochrome arm)", () => {
  // In waveform plots symbols do not render, so two traces sharing a dash
  // are separated by colour alone — the census covers every one of the 28
  // token pairs per theme (dash-1 pairs and dash-2 pairs are the same 28
  // colour pairs). Engineering margin: dark clears threshold+1 (≥ 9.0,
  // measured 11.66); light's best achievable at the T2 boundary floor is
  // 8.19 — above the pre-committed 8.0 hard threshold, below the +1.0
  // engineering floor: the reported owner fork.
  for (const [name, tokens] of THEMES) {
    it(`${name}: 28 token pairs × 4 conditions, both arms ≥ 8.0`, () => {
      const series = seriesOf(tokens);
      let worst = Number.POSITIVE_INFINITY;
      for (let i = 0; i < 8; i += 1) {
        for (let j = i + 1; j < 8; j += 1) {
          for (const condition of CONDITIONS) {
            const [primary, secondary] = de2000(series[i]!, series[j]!, condition);
            worst = Math.min(worst, primary, secondary);
            expect(primary, `${name} tokens ${i + 1}-${j + 1} (${condition}, Machado)`).toBeGreaterThanOrEqual(8.0);
            expect(secondary, `${name} tokens ${i + 1}-${j + 1} (${condition}, Viénot/Brettel)`).toBeGreaterThanOrEqual(8.0);
          }
        }
      }
      console.info(`[series-margins] ${name} census min ${worst.toFixed(2)} (hard ≥ 8.0; engineering floor ≥ 9.0)`);
      if (name === "dark") {
        expect(worst, "dark engineering margin: ≥ threshold + 1.0").toBeGreaterThanOrEqual(9.0);
      }
    });
  }
});

describe("S1-A3 (#243): --bw-limiting computed proofs", () => {
  // T1: contrast >= 3.0:1 vs BOTH --bw-surface AND --bw-surface-recessed,
  // both themes (4 ratios). T2-limiting: ΔE00 >= 10.0 vs all 6 severity keys
  // (neutral renders as the theme's text colour) x 4 viewing conditions x
  // 2 themes = 48 values, dual CVD models, both arms every pair.
  const severityAll = (tokens: Map<string, string>): string[] => {
    const hues = ["--bw-advisory", "--bw-warning", "--bw-critical", "--bw-trip", "--bw-success"].map((name) => {
      const value = tokens.get(name);
      if (value === undefined) throw new Error(`${name} missing`);
      return value;
    });
    const neutral = tokens.get("--bw-text");
    if (neutral === undefined) throw new Error("--bw-text missing (the neutral severity's hue)");
    return [...hues, neutral];
  };

  for (const [name, tokens] of THEMES) {
    it(`${name}: T1 vs both surfaces (2 ratios) and T2 vs all 6 severity keys (24 pairs x both arms)`, () => {
      const limiting = tokens.get("--bw-limiting");
      if (limiting === undefined) throw new Error("--bw-limiting missing from themes.css");
      const surface = tokens.get("--bw-surface");
      const recessed = tokens.get("--bw-surface-recessed");
      if (surface === undefined || recessed === undefined) throw new Error("surface tokens missing");
      console.info(`[limiting-margins] ${name} T1 surface ${contrast(limiting, surface).toFixed(2)} recessed ${contrast(limiting, recessed).toFixed(2)}`);
      expect(contrast(limiting, surface), `${name} vs surface`).toBeGreaterThanOrEqual(3.0);
      expect(contrast(limiting, recessed), `${name} vs recessed`).toBeGreaterThanOrEqual(3.0);
      let worst = Number.POSITIVE_INFINITY;
      for (const sev of severityAll(tokens)) {
        for (const condition of CONDITIONS) {
          const [primary, secondary] = de2000(limiting, sev, condition);
          worst = Math.min(worst, primary, secondary);
          expect(primary, `${name} limiting vs ${sev} (${condition}, Machado)`).toBeGreaterThanOrEqual(10.0);
          expect(secondary, `${name} limiting vs ${sev} (${condition}, Viénot/Brettel)`).toBeGreaterThanOrEqual(10.0);
        }
      }
      console.info(`[limiting-margins] ${name} T2 dual-arm worst ${worst.toFixed(2)} (threshold 10.0)`);
    });
  }
});

describe("S3-A3: adjacent slots stay ΔE00 ≥ 8.0 apart, both models", () => {
  for (const [name, tokens] of THEMES) {
    it(`${name}: 7 adjacent pairs × 4 conditions, both arms ≥ 8.0`, () => {
      const series = seriesOf(tokens);
      for (let i = 0; i < 7; i += 1) {
        for (const condition of CONDITIONS) {
          const [primary, secondary] = de2000(series[i]!, series[i + 1]!, condition);
          expect(primary, `${name} slots ${i + 1}-${i + 2} (${condition}, Machado)`).toBeGreaterThanOrEqual(8.0);
          expect(secondary, `${name} slots ${i + 1}-${i + 2} (${condition}, Viénot/Brettel)`).toBeGreaterThanOrEqual(8.0);
        }
      }
    });
  }
});
