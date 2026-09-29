import type { Meta, StoryObj } from "@storybook/react-vite";

import { EngineeringPlot } from "./EngineeringPlot";

const meta = { title: "Plots and datasets/EngineeringPlot Palette", component: EngineeringPlot } satisfies Meta<typeof EngineeringPlot>;
export default meta;
type Story = StoryObj<typeof meta>;

const trace = (id: string): PlotTrace => ({ id, label: id.toUpperCase(), unit: "V", values: [[0, 0], [1, 1]] });
import type { PlotTrace } from "./EngineeringPlot";

/** The whole series palette with the >8 dash-wrap visible: 16 declared
 *  channels — slots 1-8 dash-1, slots 9-16 dash-2 reusing the colours and
 *  symbols. This story is the designer's only static surface for both. */
export const SixteenTrace: Story = {
  args: {
    kind: "time_series",
    title: "Sixteen-trace palette (dash wrap at 8)",
    x: { label: "Time", unit: "s" },
    traces: Array.from({ length: 16 }, (_, i) => trace(`id${String(i + 1).padStart(2, "0")}`)),
  },
};

import type { PlotTrace as Trace } from "./EngineeringPlot";

/** Slice 2: provenance markers + the acquisition disclosure on one plot. */
export const ProvenanceAndAcquisition: Story = {
  args: {
    kind: "time_series",
    title: "Provenance and acquisition",
    x: { label: "Time", unit: "s" },
    traces: [
      { id: "id01", label: "MEAS", unit: "V", values: [[0, 1], [1, 2]] },
      { id: "id02", label: "DER", unit: "V", values: [[0, 2], [1, 3]], provenance: { kind: "derived", detail: "P = V × I" } },
      { id: "id03", label: "AVG", unit: "V", values: [[0, 3], [1, 4]], provenance: { kind: "device-averaged", detail: "8" } },
      { id: "id04", label: "DSP", unit: "V", values: [[0, 4], [1, 5]], provenance: { kind: "display-processed", detail: "median 100 ms" } },
    ] as Trace[],
    acquisition: new Map([["id01", { acquired: 1000, plotted: 25, rate: "40 Hz" }]]),
  },
};

/** Slice 2: the >2-unit refusal. */
export const UnitRefusal: Story = {
  args: {
    kind: "time_series",
    title: "Three units — refused",
    x: { label: "Time", unit: "s" },
    traces: [
      { id: "id01", label: "VOLT", unit: "V", values: [[0, 1], [1, 2]] },
      { id: "id02", label: "AMP", unit: "A", values: [[0, 1], [1, 2]] },
      { id: "id03", label: "WATT", unit: "W", values: [[0, 1], [1, 2]] },
    ] as Trace[],
  },
};
