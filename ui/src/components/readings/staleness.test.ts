import { describe, expect, it } from "vitest";

import { staleness } from "./staleness";

/** S1-A5 as folded (#243 S1 review, row 2 — the owner-worded premise): the
 *  corpus semantics. `max_age_ms` is the polled read-acceptance window —
 *  stale iff freshness_ms > max_age_ms (1×, STRICT: the descriptor's own
 *  disavowal boundary). Streaming `min_interval_ms` is a rate CAP (spec
 *  §158): silence is healthy, so a stream-cadence source renders NO verdict
 *  at all — the missed-data signal is the gap event, never silence-inference.
 *  The grid: maxAge ∈ {0, 1, 100, 1000} ms × freshness ∈ {0.5×, 1.9×, 2.0×,
 *  2.1×, 10×} plus null freshness plus no-cadence. At max_age 0 everything
 *  ≥ 1 ms is stale — zero-age means fresh-acquisition-only (the 7-of-9
 *  corpus case). Garbage inputs (non-finite/negative age, negative cadence)
 *  → no-verdict (row 11): never a fabricated fresh. */
const AGES = [0, 1, 100, 1000] as const;
const MULTIPLES = [0.5, 1.9, 2.0, 2.1, 10] as const;

describe("ST-2 staleness predicate (folded semantics): the property grid", () => {
  it.each(AGES)("max_age %i ms: all multiple cells correct (1×, strict)", (maxAge) => {
    for (const multiple of MULTIPLES) {
      if (maxAge === 0) break; // at zero age the multiples collapse to 0; the dedicated zero-age `it` below carries those cells
      const freshness = Math.round(maxAge * multiple);
      const verdict = staleness(freshness, maxAge);
      const expected = multiple > 1 ? "stale" : "fresh";
      expect(verdict, `max_age ${maxAge}ms × ${multiple}× (${freshness}ms)`).toBe(expected);
    }
    // The strict-inequality boundary: equality is NOT stale at any positive
    // age (at 0 the dedicated zero-age `it` carries the cells).
    if (maxAge > 0) {
      expect(staleness(maxAge, maxAge), `equality at ${maxAge}ms`).toBe("fresh");
      // 1.9× is stale under 1× semantics (it was fresh under the dead 2× rule).
      expect(staleness(Math.round(maxAge * 1.9), maxAge)).toBe("stale");
    }
  });

  it("max_age 0: everything ≥ 1 ms is stale (zero-age = fresh-acquisition-only)", () => {
    expect(staleness(0, 0)).toBe("fresh");
    expect(staleness(1, 0)).toBe("stale");
    expect(staleness(84, 0)).toBe("stale");
    expect(staleness(10000, 0)).toBe("stale");
  });

  it("null freshness ⇒ no verdict (asserts freshness nowhere)", () => {
    for (const maxAge of AGES) expect(staleness(null, maxAge)).toBe("no-verdict");
  });

  it("no cadence ⇒ no verdict — the honest negative covering ALL stream-cadence sources", () => {
    for (const multiple of MULTIPLES) {
      expect(staleness(Math.round(1000 * multiple), null)).toBe("no-verdict");
      expect(staleness(Math.round(1000 * multiple), undefined)).toBe("no-verdict");
    }
    expect(staleness(null, null)).toBe("no-verdict");
  });

  it("garbage inputs ⇒ no verdict (row 11: NaN→fresh is the lie class)", () => {
    expect(staleness(Number.NaN, 100)).toBe("no-verdict");
    expect(staleness(Number.POSITIVE_INFINITY, 100)).toBe("no-verdict");
    expect(staleness(-5, 100)).toBe("no-verdict");
    expect(staleness(100, -1)).toBe("no-verdict");
    expect(staleness(100, Number.NaN)).toBe("no-verdict");
    // max_age 0 is VALID semantics, not garbage.
    expect(staleness(1, 0)).toBe("stale");
  });
});

describe("ST-2 mutants: every mutant reds ≥ 1 cell the true predicate passes", () => {
  const cells: Array<[number | null, number | null | undefined]> = [];
  for (const maxAge of AGES) {
    for (const multiple of MULTIPLES) cells.push([Math.round(maxAge * multiple), maxAge]);
    cells.push([null, maxAge]);
    for (const multiple of MULTIPLES) cells.push([Math.round(1000 * multiple), null]);
  }
  const clean = (f: number | null, c: number | null | undefined): f is number =>
    f !== null && Number.isFinite(f) && f >= 0 && c !== null && c !== undefined && Number.isFinite(c) && c >= 0;

  const mutants: Record<string, (f: number | null, c: number | null | undefined) => string> = {
    ">=": (f, c) => (!clean(f, c) || f === null ? "no-verdict" : f >= c! ? "stale" : "fresh"),
    "2× for 1×": (f, c) => (!clean(f, c) || f === null ? "no-verdict" : f > 2 * c! ? "stale" : "fresh"),
    swapped: (f, c) => (!clean(f, c) || f === null ? "no-verdict" : c! > f ? "stale" : "fresh"),
    "no-cadence→fresh": (f, c) => (c === null || c === undefined || !Number.isFinite(c) || c < 0 ? "fresh" : f === null || !Number.isFinite(f) || f < 0 ? "no-verdict" : f > c ? "stale" : "fresh"),
  };
  const namedCell: Record<string, [number | null, number | null | undefined, string, string]> = {
    ">=": [100, 100, "stale", "fresh"],
    "2× for 1×": [190, 100, "fresh", "stale"],
    swapped: [50, 100, "stale", "fresh"],
    "no-cadence→fresh": [10000, null, "fresh", "no-verdict"],
  };

  for (const [name, mutant] of Object.entries(mutants)) {
    it(`mutant ${name} reds ≥ 1 cell`, () => {
      let reds = 0;
      for (const [f, c] of cells) {
        if (mutant(f, c) !== staleness(f, c)) reds += 1;
      }
      expect(reds, `the ${name} mutant must diverge`).toBeGreaterThanOrEqual(1);
      const [f, c, mutantVerdict, trueVerdict] = namedCell[name]!;
      expect(mutant(f, c), `named cell ${f}/${c}`).toBe(mutantVerdict);
      expect(staleness(f, c), `named cell ${f}/${c} true predicate`).toBe(trueVerdict);
    });
  }
});
