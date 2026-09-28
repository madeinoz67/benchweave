/** Contract §B.4 staleness — the ST-2 predicate as a pure function (no
 *  React, property-tested). ST-1: the cadence is the descriptor's own
 *  committed value (`stream_limits.min_interval_ms` for streaming
 *  observations, the parameter's `max_age_ms` for polled reads), supplied by
 *  the host — never invented, never a renderer default. ST-3: no known
 *  cadence ⇒ NO verdict (the reading is not stale; that asserts freshness
 *  nowhere); `freshness_ms: null` likewise renders no verdict. */
export type StalenessVerdict = "stale" | "fresh" | "no-verdict";

export function staleness(
  freshnessMs: number | null,
  cadenceMs: number | null | undefined,
): StalenessVerdict {
  if (cadenceMs === null || cadenceMs === undefined) return "no-verdict";
  if (freshnessMs === null) return "no-verdict";
  // ST-2: strictly greater than 2× — equality is NOT stale.
  return freshnessMs > 2 * cadenceMs ? "stale" : "fresh";
}
