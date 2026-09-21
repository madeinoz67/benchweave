import type { Severity } from "../components/feedback/severity";
import type { PlotTrace } from "../components/plots/EngineeringPlot";
import type { PreviewDocument, PreviewScenario, PreviewSeverity } from "../preview/api";

export interface WorkbenchReading {
  id: string;
  label: string;
  value: string;
  unit: string | null;
  severity: Severity;
  freshness: string;
  quality: string;
}

export interface DeviceWorkbenchFixture {
  simulation: boolean;
  device: { id: string; title: string; connected: boolean };
  lease: { owner: string; expiresInSeconds: number };
  readings: readonly WorkbenchReading[];
  stagedVoltage: number;
  message: string;
  traces: readonly PlotTrace[];
}

const voltageTrend = Array.from({ length: 60 }, (_, index) => [index - 59, 12 + Math.sin(index / 7) * 0.06 + index * 0.001] as const);
const currentTrend = Array.from({ length: 60 }, (_, index) => [index - 59, 1.7 + Math.sin(index / 8) * 0.08 + index * 0.004] as const);

export const warningWorkbench: DeviceWorkbenchFixture = {
  simulation: true,
  device: { id: "psu-01", title: "DC supply", connected: true },
  lease: { owner: "operator@example.invalid", expiresInSeconds: 42 },
  readings: [
    { id: "voltage", label: "Voltage", value: "12.04", unit: "V", severity: "success", freshness: "84 ms", quality: "Verified" },
    { id: "current", label: "Current", value: "1.92", unit: "A", severity: "warning", freshness: "84 ms", quality: "Near limit" },
    { id: "power", label: "Power", value: "23.1", unit: "W", severity: "success", freshness: "84 ms", quality: "In range" },
  ],
  stagedVoltage: 12,
  message: "Current approaching configured limit",
  traces: [
    { id: "voltage", label: "Voltage", unit: "V", values: voltageTrend },
    { id: "current", label: "Current", unit: "A", values: currentTrend },
  ],
};

const severityFor = (severity: PreviewSeverity): Severity => severity === "trip" ? "critical" : severity;
const displayValue = (value: boolean | number | string | null): string => value === null ? "—" : typeof value === "boolean" ? (value ? "On" : "Off") : String(value);
/** The house prettifier for id-shaped labels (binding ids, variable ids):
 *  split on separator characters, capitalise each part. */
export const titleFor = (bindingId: string): string => bindingId.split(/[._-]/).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");

export function scenarioToWorkbenchFixture(scenario: PreviewScenario, preview: PreviewDocument): DeviceWorkbenchFixture {
  const numeric = scenario.observations.filter((observation): observation is typeof observation & { value: number } => typeof observation.value === "number");
  const voltage = numeric.find((observation) => observation.unit === "V")?.value ?? 0;
  return {
    simulation: true,
    device: { id: preview.plugin_id, title: titleFor(preview.plugin_id), connected: scenario.id !== "disconnected" },
    lease: { owner: scenario.lease_state === "held" ? "Simulated controller" : scenario.lease_state, expiresInSeconds: 0 },
    readings: scenario.observations.map((observation) => ({
      id: observation.binding_id,
      label: titleFor(observation.binding_id),
      value: displayValue(observation.value),
      unit: observation.unit,
      severity: severityFor(scenario.expected_severity),
      freshness: observation.freshness_ms === null ? "Unavailable" : `${observation.freshness_ms} ms`,
      quality: observation.quality,
    })),
    stagedVoltage: voltage,
    message: scenario.description,
    traces: numeric.map((observation) => ({ id: observation.binding_id, label: titleFor(observation.binding_id), unit: observation.unit ?? "", values: [[-1, observation.value], [0, observation.value]] })),
  };
}

export interface AdminFixture {
  packages: readonly { id: string; revision: string; status: string }[];
  approvals: readonly { id: string; scope: string; status: string }[];
}

export const adminFixture: AdminFixture = {
  packages: [{ id: "benchweave.fnirsi.dps150", revision: "0.1.0", status: "Admitted" }],
  approvals: [{ id: "approval-17", scope: "Bench A configuration", status: "Pending independent approval" }],
};
