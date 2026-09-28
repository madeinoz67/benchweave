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
  /** Output state for the safety behaviours (contract §C.1): `trip` disables
   *  energy-sourcing actions with reason `protection-active` (R-PROTECT-1);
   *  `energised` makes a set-point change energy-sourcing (R-ENERGISE-1). */
  output: { energised: boolean; trip: boolean };
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
  output: { energised: true, trip: false },
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
    // Output-state derivation, disclosed with its edges: a scenario whose
    // expected severity is `trip` is the protective-trip scenario
    // (R-PROTECT-1's guard fires on it); a POSITIVE voltage reading derives an
    // energised output (R-ENERGISE-1's set-point confirm fires on it) — the
    // mechanism is `voltage > 0`, not "non-zero", so a negative bipolar
    // reading derives de-energised. `voltage` itself is the FIRST V-unit
    // observation in scenario order (order-dependent when several exist), and
    // the severity mapping is uniform across a scenario's readings (every
    // reading shares expected_severity — the preview document has no
    // per-observation severity). The preview document has no dedicated
    // output-state field, so the workbench derives both from the observations
    // it already carries.
    output: { energised: voltage > 0, trip: scenario.expected_severity === "trip" },
  };
}

/** S2-A2 proof fixtures (issue #242 slice 2): a bench PSU workbench page and a
 *  multi-channel DAQ page, INVENTED identities. Each carries an energy-sourcing
 *  action (output / excitation on) and an energy-removing action (output /
 *  excitation off) — the vacuous-pass control for the five proof properties. */
export const psuProofFixture: DeviceWorkbenchFixture = {
  simulation: false,
  device: { id: "psu-07", title: "Bench supply", connected: true },
  lease: { owner: "bench-operator@example.invalid", expiresInSeconds: 120 },
  readings: [
    { id: "voltage", label: "Voltage", value: "12.04", unit: "V", severity: "success", freshness: "120 ms", quality: "Verified" },
    { id: "current", label: "Current", value: "1.92", unit: "A", severity: "success", freshness: "120 ms", quality: "Verified" },
    { id: "power", label: "Power", value: "23.1", unit: "W", severity: "success", freshness: "120 ms", quality: "Verified" },
  ],
  stagedVoltage: 12.5,
  message: "Output within the commissioned envelope",
  traces: [
    { id: "voltage", label: "Voltage", unit: "V", values: voltageTrend },
    { id: "current", label: "Current", unit: "A", values: currentTrend },
  ],
  output: { energised: true, trip: false },
};

export const daqProofFixture: DeviceWorkbenchFixture = {
  simulation: false,
  device: { id: "daq-47", title: "Multi-channel logger", connected: true },
  lease: { owner: "bench-operator@example.invalid", expiresInSeconds: 120 },
  readings: [
    { id: "ch1", label: "Channel 1", value: "4.98", unit: "V", severity: "success", freshness: "95 ms", quality: "Verified" },
    { id: "ch2", label: "Channel 2", value: "1.02", unit: "V", severity: "success", freshness: "95 ms", quality: "Verified" },
    { id: "ch3", label: "Channel 3", value: "0.24", unit: "V", severity: "success", freshness: "95 ms", quality: "Verified" },
    { id: "ch4", label: "Channel 4", value: "-0.11", unit: "V", severity: "success", freshness: "95 ms", quality: "Verified" },
    { id: "excitation", label: "Excitation", value: "On", unit: null, severity: "success", freshness: "95 ms", quality: "Verified" },
  ],
  stagedVoltage: 5,
  message: "Excitation output within the commissioned envelope",
  // Six declared channels: the S3-A5 example-fixture proof draws exactly
  // these six traces and asserts six distinct series tokens.
  traces: [
    { id: "ch1", label: "Channel 1", unit: "V", values: [[-1, 4.98], [0, 4.98]] },
    { id: "ch2", label: "Channel 2", unit: "V", values: [[-1, 1.02], [0, 1.02]] },
    { id: "ch3", label: "Channel 3", unit: "V", values: [[-1, 0.24], [0, 0.24]] },
    { id: "ch4", label: "Channel 4", unit: "V", values: [[-1, -0.11], [0, -0.11]] },
    { id: "ch5", label: "Channel 5", unit: "V", values: [[-1, 3.3], [0, 3.3]] },
    { id: "ch6", label: "Channel 6", unit: "V", values: [[-1, 0.5], [0, 0.5]] },
  ],
  output: { energised: true, trip: false },
};

export interface AdminFixture {
  packages: readonly { id: string; revision: string; status: string }[];
  approvals: readonly { id: string; scope: string; status: string }[];
}

export const adminFixture: AdminFixture = {
  packages: [{ id: "benchweave.fnirsi.dps150", revision: "0.1.0", status: "Admitted" }],
  approvals: [{ id: "approval-17", scope: "Bench A configuration", status: "Pending independent approval" }],
};
