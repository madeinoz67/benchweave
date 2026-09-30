/**
 * §E.4.4 — edge-preserving lane decimation, a NORMATIVE pure function.
 *
 * Reduction keeps EVERY transition: a drawn column always contains every
 * state change of the acquired states it covers, as an edge (a column
 * boundary, or the single interior pre/post pair) or a glitch mark (any
 * column covering more than one transition). Sample-dropping reduction
 * (LTTB-style point selection) is NON-CONFORMING for this kind — a dropped
 * transition is detected by the property test, which recomputes survival
 * independently of this implementation.
 */

/** The four-state logic alphabet carried verbatim on the OTDP wire. */
export type LaneState = "0" | "1" | "x" | "z";

/** One drawn column of a reduced lane. */
export interface LaneColumn {
  /** Inclusive first sample index the column covers. */
  first: number;
  /** Exclusive last sample index (the columns partition [0, states.length)). */
  last: number;
  /** The state drawn across the column when it carries no interior transition. */
  state: LaneState;
  /** Transitions strictly inside the column (both endpoints covered). */
  transitions: number;
  /** §E.4.4: a column covering more than one interior transition renders a
   * multi-edge/glitch mark. */
  glitch: boolean;
  /** Exactly one interior transition: the column draws the pre/post edge. */
  edge?: { from: LaneState; to: LaneState };
}

/**
 * Reduce one lane's acquired states to `columns` drawn columns.
 *
 * Boundaries fall on the transition-faithful grid: a transition at index t
 * is a column boundary whenever the bucket sizes allow, and any transition
 * that lands strictly inside a column is carried by that column — as its
 * `edge` pair when it is the only one, as the `glitch` mark otherwise.
 */
export function reduceLane(states: readonly LaneState[], columns: number): LaneColumn[] {
  if (states.length === 0) return [];
  if (columns < 1) throw new Error("lane_columns_invalid: at least one column required");
  // More columns than samples helps nothing: one column per sample is the
  // finest drawable grid.
  const target = Math.min(columns, states.length);
  const out: LaneColumn[] = [];
  for (let b = 0; b < target; b += 1) {
    const first = Math.floor((b * states.length) / target);
    let last = Math.floor(((b + 1) * states.length) / target);
    // The grid can theoretically produce an empty bucket at the tail; fold
    // it forward so the columns stay a partition of non-empty spans.
    if (b === target - 1) last = states.length;
    if (last <= first) continue;
    let transitions = 0;
    let single = -1;
    for (let t = first; t + 1 < last; t += 1) {
      if (states[t] !== states[t + 1]) {
        transitions += 1;
        single = t;
      }
    }
    const column: LaneColumn = {
      first,
      last,
      state: states[first]!,
      transitions,
      glitch: transitions > 1,
    };
    if (transitions === 1) {
      column.edge = { from: states[single]!, to: states[single + 1]! };
    }
    out.push(column);
  }
  return out;
}
