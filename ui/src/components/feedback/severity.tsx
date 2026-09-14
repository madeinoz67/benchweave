import {
  AlertCircle,
  CheckCircle2,
  CircleHelp,
  Info,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";

export type Severity = "neutral" | "success" | "advisory" | "warning" | "critical" | "trip";

export const assertiveSeverities: ReadonlySet<Severity> = new Set(["critical", "trip"]);
export const dismissibleSeverities: ReadonlySet<Severity> = new Set(["neutral", "success", "advisory"]);

export const severityLabels: Record<Severity, string> = {
  neutral: "Neutral",
  success: "Normal",
  advisory: "Advisory",
  warning: "Warning",
  critical: "Critical",
  trip: "Protective trip",
};

const icons = {
  neutral: CircleHelp,
  success: CheckCircle2,
  advisory: Info,
  warning: TriangleAlert,
  critical: AlertCircle,
  trip: ShieldAlert,
};

export function SeverityIcon({ severity }: { severity: Severity }) {
  const Icon = icons[severity];
  return <Icon aria-hidden="true" focusable="false" size={18} strokeWidth={2.25} />;
}
