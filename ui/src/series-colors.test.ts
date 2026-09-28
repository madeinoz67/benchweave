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
  let hbp = h1p + h2p;
  if (C1p * C2p !== 0) {
    hbp = (h1p + h2p) / 2;
    if (Math.abs(h1p - h2p) > 180) hbp += hbp < 180 ? 360 : -360;
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
const A575 = anchorLms([0.8425, 0.9917, 0.0]);
const A475 = anchorLms([0.1421, 0.1126, 1.0419]);

/** Brettel tritanopia: project along the S fundamental axis onto the half
 *  plane (span of white and the 575/475 nm anchor), chosen by the sign of the
 *  S excess over the neutral axis. Solving q − λ·e_S = α·W + β·A reduces to a
 *  2×2 system on the first two rows (the third fixes λ). */
const brettelTritan = (rgb: Rgb): Rgb => {
  const lin = rgb.map(srgbToLinear);
  const q = matVec(M_LMS, lin);
  const w = W_LMS;
  const axisS = q[0]! * (w[2]! / w[0]!);
  const anchor = q[2]! >= axisS ? A575 : A475;
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
  it("reports the measured margins (the design record's §7 candidates, run under the dual arm, do not all clear — documented in the increment report)", () => {
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
      expect(worst, `${name} worst dual-model severity distance`).toBeGreaterThanOrEqual(10.0);
    }
  });
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
