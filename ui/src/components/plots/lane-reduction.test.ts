import { describe, expect, it } from "vitest";

import {
  reduceLane,
  type LaneState,
} from "./lane-reduction";

/** Deterministic PRNG so the property arm is reproducible run to run. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const STATES: readonly LaneState[] = ["0", "1", "x", "z"];

function randomStates(random: () => number, length: number): LaneState[] {
  const states: LaneState[] = [];
  for (let i = 0; i < length; i += 1) states.push(STATES[Math.floor(random() * 4)]!);
  return states;
}

/** The §E.4.4 property, recomputed INDEPENDENTLY of the reducer: every
 * transition in the acquired states must survive to the drawn output — as
 * a column-boundary edge, a column's single-interior edge, or a glitch
 * mark — and every column covering more than one transition carries the
 * glitch mark. */
interface Survival {
  survived: number;
  total: number;
  missing: number[];
  unmarkedMultiEdge: number[];
  /** Fold F3a: glitch is EXACTLY (interior transitions > 1) — a marked
   * single-edge column destroys the edge information the mark replaces. */
  overmarkedSingleEdge: number[];
  /** Fold F3b: a single-edge column's from/to are the ACTUAL neighbouring
   * states — a swap time-reverses the drawn edge. */
  reversedEdges: number[];
}

function checkSurvival(states: readonly LaneState[], out: ReturnType<typeof reduceLane>): Survival {
  const total = states.length - 1;
  const missing: number[] = [];
  let survived = 0;
  // Column lookup by covered sample index.
  const columnAt = new Map<number, number>();
  out.forEach((column, index) => {
    for (let s = column.first; s < column.last; s += 1) columnAt.set(s, index);
  });
  for (let t = 0; t < total; t += 1) {
    if (states[t] === states[t + 1]) continue; // not a transition
    const owner = columnAt.get(t);
    if (owner === undefined) {
      missing.push(t);
      continue;
    }
    const column = out[owner]!;
    if (t + 1 === column.last) survived += 1; // boundary edge between columns
    else if (column.glitch || column.edge) survived += 1;
    else missing.push(t);
  }
  const unmarkedMultiEdge = out
    .map((column, index) => ({ column, index }))
    .filter(({ column }) => interiorTransitions(states, column) > 1 && !column.glitch)
    .map(({ index }) => index);
  const overmarkedSingleEdge = out
    .map((column, index) => ({ column, index }))
    .filter(({ column }) => column.glitch && interiorTransitions(states, column) <= 1)
    .map(({ index }) => index);
  const reversedEdges: number[] = [];
  out.forEach((column, index) => {
    const interior = interiorTransitions(states, column);
    if (interior === 1 && column.edge) {
      for (let s = column.first; s + 1 < column.last; s += 1) {
        if (states[s] !== states[s + 1]) {
          if (column.edge.from !== states[s] || column.edge.to !== states[s + 1]) {
            reversedEdges.push(index);
          }
          break;
        }
      }
    }
  });
  return {
    survived,
    total: transitions(states),
    missing,
    unmarkedMultiEdge,
    overmarkedSingleEdge,
    reversedEdges,
  };
}

function interiorTransitions(
  states: readonly LaneState[],
  column: { first: number; last: number },
): number {
  let count = 0;
  for (let t = column.first; t + 1 < column.last; t += 1) {
    if (states[t] !== states[t + 1]) count += 1;
  }
  return count;
}

function transitions(states: readonly LaneState[]): number {
  let count = 0;
  for (let t = 0; t + 1 < states.length; t += 1) {
    if (states[t] !== states[t + 1]) count += 1;
  }
  return count;
}

describe("lane reduction — the §E.4.4 normative property", () => {
  it("keeps EVERY transition across ≥200 random arrays and widths 1..64", () => {
    const random = mulberry32(0x2445220);
    let checked = 0;
    for (let run = 0; run < 240; run += 1) {
      const length = 2 + Math.floor(random() * 4999);
      const columns = 1 + Math.floor(random() * 64);
      const states = randomStates(random, length);
      const out = reduceLane(states, columns);
      const survival = checkSurvival(states, out);
      expect(
        survival.missing,
        `run ${run}: len ${length} cols ${columns} — transitions ${survival.missing.join(",")} did not survive`,
      ).toEqual([]);
      expect(
        survival.unmarkedMultiEdge,
        `run ${run}: multi-transition columns without the glitch mark`,
      ).toEqual([]);
      expect(
        survival.overmarkedSingleEdge,
        `run ${run}: single-edge columns carrying the glitch mark`,
      ).toEqual([]);
      expect(
        survival.reversedEdges,
        `run ${run}: single-edge columns whose from/to are reversed`,
      ).toEqual([]);
      expect(survival.survived).toBe(survival.total);
      checked += 1;
    }
    expect(checked).toBeGreaterThanOrEqual(200);
  });

  it("covers every sample exactly once (a partition, never a drop)", () => {
    const random = mulberry32(0x2445221);
    for (let run = 0; run < 60; run += 1) {
      const length = 2 + Math.floor(random() * 500);
      const columns = 1 + Math.floor(random() * 64);
      const states = randomStates(random, length);
      const out = reduceLane(states, columns);
      expect(out[0]!.first).toBe(0);
      expect(out[out.length - 1]!.last).toBe(states.length);
      for (let i = 1; i < out.length; i += 1) {
        expect(out[i]!.first, "columns are contiguous").toBe(out[i - 1]!.last);
      }
      out.forEach((column) => {
        expect(column.last, "no empty columns").toBeGreaterThan(column.first);
      });
    }
  });

  it("marks EVERY column of the adversarial 0101… fixture as glitch (sub-column spacing)", () => {
    const states: LaneState[] = Array.from({ length: 257 }, (_, i) => (i % 2 === 0 ? "0" : "1"));
    const out = reduceLane(states, 16);
    expect(out).toHaveLength(16);
    out.forEach((column) => {
      expect(column.glitch, `column [${column.first},${column.last}) covers >1 transition`).toBe(true);
    });
    const survival = checkSurvival(states, out);
    expect(survival.missing).toEqual([]);
    expect(survival.survived).toBe(survival.total);
  });

  it("permutation null: 50 permuted copies of the adversarial fixture survive identically", () => {
    const random = mulberry32(0x2445222);
    const base: LaneState[] = Array.from({ length: 257 }, (_, i) => (i % 2 === 0 ? "0" : "1"));
    const baseSurvival = checkSurvival(base, reduceLane(base, 16));
    expect(baseSurvival.survived).toBe(baseSurvival.total);
    expect(baseSurvival.total).toBe(base.length - 1);
    for (let run = 0; run < 50; run += 1) {
      const permuted = [...base];
      // Fisher-Yates with the seeded PRNG: ordering changes, multiset does not
      // — and with it the transition COUNT, so the invariant is the survival
      // RATE (every transition of THIS array survives), never the base's
      // absolute count.
      for (let i = permuted.length - 1; i > 0; i -= 1) {
        const j = Math.floor(random() * (i + 1));
        [permuted[i], permuted[j]] = [permuted[j]!, permuted[i]!];
      }
      const survival = checkSurvival(permuted, reduceLane(permuted, 16));
      expect(survival.missing, `permutation ${run}`).toEqual([]);
      expect(survival.unmarkedMultiEdge, `permutation ${run}`).toEqual([]);
      expect(survival.survived, `permutation ${run}: every transition of this ordering survives`).toBe(survival.total);
    }
  });
});
