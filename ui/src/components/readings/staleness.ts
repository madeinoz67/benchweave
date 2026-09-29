/** Contract §B.4 staleness — the ST-2 predicate as a pure function (no
 *  React, property-tested). ST-1 (folded semantics, per the corpus): the
 *  cadence is the POLLED parameter's `max_age_ms` — the descriptor's own
 *  read-acceptance window (its disavowal boundary). For streaming
 *  observations `stream_limits.min_interval_ms` is a rate CAP (spec §158):
 *  silence is healthy, so a stream-cadence source supplies NO cadence here
 *  and renders no staleness verdict — the missed-data signal is the gap
 *  event, never silence-inference. ST-3: no cadence ⇒ NO verdict (asserts
 *  freshness nowhere); `freshness_ms: null` likewise. Garbage inputs
 *  (non-finite or negative age, non-finite or negative cadence) also render
 *  no verdict — a fabricated `fresh` is the lie class. `max_age_ms: 0` is
 *  VALID semantics (fresh-acquisition-only): everything ≥ 1 ms is stale. */
export type StalenessVerdict = "stale" | "fresh" | "no-verdict";

export function staleness(
  freshnessMs: number | null,
  maxAgeMs: number | null | undefined,
): StalenessVerdict {
  if (maxAgeMs === null || maxAgeMs === undefined) return "no-verdict";
  if (!Number.isFinite(maxAgeMs) || maxAgeMs < 0) return "no-verdict";
  if (freshnessMs === null) return "no-verdict";
  if (!Number.isFinite(freshnessMs) || freshnessMs < 0) return "no-verdict";
  // ST-2: strictly greater than the read-acceptance window — equality is
  // not stale (the boundary IS the descriptor's own disavowal line).
  return freshnessMs > maxAgeMs ? "stale" : "fresh";
}
