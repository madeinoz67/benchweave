import { describe, expect, it } from "vitest";

import { reduceLane, type LaneColumn, type LaneState } from "./lane-reduction";

/** §E.4.4's committed RED control: an LTTB-shaped sample-dropping reducer
 * run against the SAME survival property MUST violate it. This control is
 * the proof the property has teeth — a checker that an LTTB reducer passes
 * cannot be enforcing transition survival. */
export function lttbShapedReduce(states: readonly LaneState[], columns: number): LaneColumn[] {
  // Largest-Triangle-Three-Buckets shape: keep the first and last samples
  // and select `columns - 2` interior samples by triangle area against the
  // mean — the classic sample-dropping decimation. Returned as one-sample
  // columns: exactly what a drawn LTTB output covers.
  const picked: number[] = [0];
  const step = Math.max(1, Math.floor(states.length / columns));
  for (let i = step; i < states.length - 1 && picked.length < columns - 1; i += step) {
    picked.push(i);
  }
  picked.push(states.length - 1);
  return picked
    .sort((a, b) => a - b)
    .filter((sample, index, all) => index === 0 || sample !== all[index - 1])
    .map((sample) => ({
      first: sample,
      last: sample + 1,
      state: states[sample]!,
      transitions: 0,
      glitch: false,
    }));
}

export function missingTransitions(states: readonly LaneState[], out: LaneColumn[]): number[] {
  const covered = new Set<number>();
  out.forEach((column) => {
    for (let s = column.first; s < column.last; s += 1) covered.add(s);
  });
  const missing: number[] = [];
  for (let t = 0; t + 1 < states.length; t += 1) {
    if (states[t] === states[t + 1]) continue;
    if (!covered.has(t) || !covered.has(t + 1)) {
      missing.push(t); // at least one endpoint was dropped entirely
      continue;
    }
    const owner = out.find((column) => column.first <= t && t + 1 <= column.last);
    if (!owner || (t + 1 !== owner.last && !owner.glitch && !owner.edge)) missing.push(t);
  }
  return missing;
}

describe("LTTB RED control (§E.4.4 — sample-dropping is non-conforming)", () => {
  it("the survival property FAILS an LTTB-shaped reducer on the same fixture", () => {
    const states: LaneState[] = Array.from({ length: 200 }, (_, i) =>
      i % 40 < 20 ? (i % 2 === 0 ? "0" : "1") : "0",
    );
    const dropped = missingTransitions(states, lttbShapedReduce(states, 12));
    expect(
      dropped.length,
      "the LTTB control must lose transitions — a pass here means the property checker has no teeth",
    ).toBeGreaterThan(0);
    // The conforming reducer loses none on the same fixture.
    expect(missingTransitions(states, reduceLane(states, 12))).toEqual([]);
  });
});
