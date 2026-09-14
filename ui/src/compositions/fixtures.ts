import type { Severity } from "../components/feedback/severity";
import type { PlotTrace } from "../components/plots/EngineeringPlot";

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

export interface AdminFixture {
  packages: readonly { id: string; revision: string; status: string }[];
  approvals: readonly { id: string; scope: string; status: string }[];
}

export const adminFixture: AdminFixture = {
  packages: [{ id: "benchweave.fnirsi.dps150", revision: "0.1.0", status: "Admitted" }],
  approvals: [{ id: "approval-17", scope: "Bench A configuration", status: "Pending independent approval" }],
};
