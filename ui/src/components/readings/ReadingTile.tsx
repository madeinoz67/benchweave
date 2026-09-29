import { ArrowUpToLine } from "lucide-react";

import { SeverityIcon, severityLabels } from "../feedback/severity";
import type { Severity } from "../feedback/severity";
import "../feedback/alert-bubble.css";
import "./reading-tile.css";

/** The closed §B.3 reading-state set (one key today; the mode-banner shape). */
export type ReadingState = "limiting";

const stateLabels: Record<ReadingState, string> = {
  limiting: "Limiting",
};

export interface ReadingTileProps {
  label: string;
  value: string | number;
  unit: string | null;
  freshness: string;
  quality: string;
  severity: Severity;
  /** §E.3: gateway-observed device-set value — never derived from a staged input. */
  set?: { value: string | number; unit: string | null };
  /** §B.3: a reading state — significant, not abnormal; composes with any severity. */
  state?: ReadingState;
  /** §B.4 ST-4: the computed staleness verdict (ST-2 via staleness.ts). */
  stale?: boolean;
}

export function ReadingTile({ label, value, unit, freshness, quality, severity, set, state, stale }: ReadingTileProps) {
  return (
    <section
      className="bw-reading"
      data-severity={severity}
      data-bw-reading-state={state}
      data-bw-stale={stale ? "true" : undefined}
      aria-label={label}
    >
      <header className="bw-reading__header">
        <span>{label}</span>
        <span className="bw-reading__severity"><SeverityIcon severity={severity} />{severityLabels[severity]}</span>
      </header>
      <div className="bw-reading__value">
        {value}{unit ? <small> {unit}</small> : null}
        {set ? (
          <span className="bw-reading__set" data-bw-reading-role="set">
            Set {set.value}{set.unit ? ` ${set.unit}` : ""}
          </span>
        ) : null}
      </div>
      <div className="bw-reading__quality">
        {quality} · {freshness}{stale ? <span className="bw-reading__stale-marker"> · stale</span> : null}
      </div>
      {state ? (
        <div className="bw-reading__state">
          <ArrowUpToLine size={16} aria-hidden="true" focusable="false" />
          {stateLabels[state]}
          {/* §B.3 announcement: entry announces once via a status live region,
              coalesced; the region mounts WITH the state (the mount is the
              entry) and unmounts silently on exit. */}
          <p className="bw-visually-hidden" role="status">{`${label} ${stateLabels[state]}`}</p>
        </div>
      ) : null}
      {stale ? (
        /* §B.4 ST-4 announcement: the fresh→stale transition announces once
           via a status live region, coalesced; exit is silent. */
        <p className="bw-visually-hidden" role="status">{`${label} stale`}</p>
      ) : null}
    </section>
  );
}
