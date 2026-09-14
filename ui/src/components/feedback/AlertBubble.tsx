import { SeverityIcon, assertiveSeverities, dismissibleSeverities } from "./severity";
import type { Severity } from "./severity";
import "./alert-bubble.css";

export interface AlertBubbleProps {
  severity: Severity;
  title: string;
  message: string;
  source?: string;
  onDismiss?(): void;
}

export function AlertBubble({ severity, title, message, source, onDismiss }: AlertBubbleProps) {
  const dismissible = dismissibleSeverities.has(severity) && onDismiss !== undefined;
  return (
    <aside
      className="bw-alert-bubble"
      data-severity={severity}
      role={assertiveSeverities.has(severity) ? "alert" : "status"}
    >
      <SeverityIcon severity={severity} />
      <div className="bw-alert-bubble__content">
        <strong>{title}</strong>
        <p>{message}</p>
        {source ? <small>{source}</small> : null}
      </div>
      {dismissible ? (
        <button type="button" onClick={onDismiss} aria-label="Dismiss">×</button>
      ) : null}
    </aside>
  );
}
