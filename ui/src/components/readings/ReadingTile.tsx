import { SeverityIcon, severityLabels } from "../feedback/severity";
import type { Severity } from "../feedback/severity";
import "../feedback/alert-bubble.css";
import "./reading-tile.css";

export interface ReadingTileProps {
  label: string;
  value: string | number;
  unit: string | null;
  freshness: string;
  quality: string;
  severity: Severity;
}

export function ReadingTile({ label, value, unit, freshness, quality, severity }: ReadingTileProps) {
  return (
    <section className="bw-reading" data-severity={severity} aria-label={label}>
      <header className="bw-reading__header">
        <span>{label}</span>
        <span className="bw-reading__severity"><SeverityIcon severity={severity} />{severityLabels[severity]}</span>
      </header>
      <div className="bw-reading__value">{value}{unit ? <small> {unit}</small> : null}</div>
      <div className="bw-reading__quality">{quality} · {freshness}</div>
    </section>
  );
}
