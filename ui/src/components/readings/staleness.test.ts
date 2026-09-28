import { describe, expect, it } from "vitest";

import { staleness } from "./staleness";

/** S1-A5 (design record §6): the ST-2 property grid with the four pre-committed
 *  predicate mutants. Cadence ∈ {100, 1000} ms × freshness ∈ {0.5×, 1.9×,
 *  2.0×, 2.1×, 10×} plus `null` freshness plus no-cadence. The true predicate:
 *  2.0× NOT stale (strict >); 2.1× and 10× stale; 0.5×/1.9× fresh; null →
 *  no-verdict; no-cadence → no-verdict (ST-3's honest negative — first-class). */
const CADENCES = [100, 1000] as const;
const MULTIPLES = [0.5, 1.9, 2.0, 2.1, 10] as const;

const truePredicate = (freshnessMs: number | null, cadenceMs: number | null | undefined) =>
  staleness(freshnessMs, cadenceMs);

describe("ST-2 staleness predicate: the property grid", () => {
  it.each(CADENCES)("cadence %i ms: all 10 cells correct", (cadence) => {
    for (const multiple of MULTIPLES) {
      const verdict = truePredicate(Math.round(cadence * multiple), cadence);
      const expected = multiple > 2 ? "stale" : "fresh";
      expect(verdict, `${cadence}ms cadence × ${multiple}×`).toBe(expected);
    }
    // 2.0× explicitly NOT stale — the strict-inequality boundary cell.
    expect(truePredicate(2 * cadence, cadence), `equality at ${cadence}ms`).toBe("fresh");
    expect(truePredicate(2.1 * cadence, cadence), `just-over at ${cadence}ms`).toBe("stale");
    expect(truePredicate(10 * cadence, cadence), `10× at ${cadence}ms`).toBe("stale");
    expect(truePredicate(0.5 * cadence, cadence), `half at ${cadence}ms`).toBe("fresh");
    expect(truePredicate(1.9 * cadence, cadence), `1.9× at ${cadence}ms`).toBe("fresh");
  });

  it("null freshness ⇒ no verdict (ST-3: not stale; asserts freshness nowhere)", () => {
    for (const cadence of CADENCES) {
      expect(truePredicate(null, cadence)).toBe("no-verdict");
    }
  });

  it("no cadence ⇒ no verdict (ST-3 honest negative — first-class acceptance row)", () => {
    for (const multiple of MULTIPLES) {
      expect(truePredicate(Math.round(1000 * multiple), null)).toBe("no-verdict");
      expect(truePredicate(Math.round(1000 * multiple), undefined)).toBe("no-verdict");
    }
    expect(truePredicate(null, null)).toBe("no-verdict");
  });
});

describe("ST-2 mutants: every mutant reds ≥ 1 cell the true predicate passes", () => {
  // The four pre-committed mutants, asserted against the grid they must fail on.
  const cells: Array<[number | null, number | null | undefined]> = [];
  for (const cadence of CADENCES) {
    for (const multiple of MULTIPLES) cells.push([Math.round(cadence * multiple), cadence]);
    cells.push([null, cadence]);
    for (const multiple of MULTIPLES) cells.push([Math.round(1000 * multiple), null]);
  }

  it("mutant >= (non-strict) reds on the 2.0× boundary cells", () => {
    const mutant = (f: number | null, c: number | null | undefined) => {
      if (c === null || c === undefined || f === null) return "no-verdict";
      return f >= 2 * c ? "stale" : "fresh";
    };
    let reds = 0;
    for (const [f, c] of cells) {
      if (mutant(f, c) !== truePredicate(f, c)) reds += 1;
    }
    expect(reds, "the >= mutant must diverge on the 2.0× cells").toBeGreaterThanOrEqual(1);
    expect(mutant(200, 100), "the exact boundary cell diverges").toBe("stale");
    expect(truePredicate(200, 100)).toBe("fresh");
  });

  it("mutant 3× for 2× reds on the 2.1× cells", () => {
    const mutant = (f: number | null, c: number | null | undefined) => {
      if (c === null || c === undefined || f === null) return "no-verdict";
      return f > 3 * c ? "stale" : "fresh";
    };
    let reds = 0;
    for (const [f, c] of cells) {
      if (mutant(f, c) !== truePredicate(f, c)) reds += 1;
    }
    expect(reds, "the 3× mutant must diverge on the 2.1× cells").toBeGreaterThanOrEqual(1);
    expect(mutant(210, 100), "2.1× diverges").toBe("fresh");
    expect(truePredicate(210, 100)).toBe("stale");
  });

  it("mutant cadence/freshness swapped reds on sub-threshold cells", () => {
    const mutant = (f: number | null, c: number | null | undefined) => {
      if (c === null || c === undefined || f === null) return "no-verdict";
      return c > 2 * f ? "stale" : "fresh";
    };
    let reds = 0;
    for (const [f, c] of cells) {
      if (mutant(f, c) !== truePredicate(f, c)) reds += 1;
    }
    expect(reds, "the swap mutant must diverge (stale cells become fresh)").toBeGreaterThanOrEqual(1);
    expect(mutant(1000, 100), "10× diverges under the swap").toBe("fresh");
    expect(truePredicate(1000, 100)).toBe("stale");
  });

  it("mutant no-cadence→fresh reds on the no-cadence cells (ST-3 negated)", () => {
    const mutant = (f: number | null, c: number | null | undefined) => {
      if (c === null || c === undefined) return "fresh";
      if (f === null) return "no-verdict";
      return f > 2 * c ? "stale" : "fresh";
    };
    let reds = 0;
    for (const [f, c] of cells) {
      if (mutant(f, c) !== truePredicate(f, c)) reds += 1;
    }
    expect(reds, "fabricating fresh on no-cadence diverges everywhere ST-3 governs").toBeGreaterThanOrEqual(1);
    expect(mutant(10000, null), "the honest negative becomes a lie").toBe("fresh");
    expect(truePredicate(10000, null)).toBe("no-verdict");
  });
});
