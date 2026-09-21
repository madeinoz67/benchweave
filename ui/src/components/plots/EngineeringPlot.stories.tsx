import type { Meta, StoryObj } from "@storybook/react-vite";

import { EngineeringPlot, type TraceHint } from "./EngineeringPlot";

const voltage = Array.from({ length: 80 }, (_, index) => [index / 10000, Math.sin(index / 6) * 1.65] as const);
const digital = Array.from({ length: 80 }, (_, index) => [index / 10000, index % 20 < 10 ? 2.5 : -2.5] as const);
const ripple = Array.from({ length: 80 }, (_, index) => [index / 10000, Math.sin(index / 1.5) * 0.08] as const);

const traces = [
  { id: "ch1", label: "Channel 1", unit: "V", values: voltage },
  { id: "ch2", label: "Channel 2", unit: "V", values: digital },
  { id: "ch3", label: "Channel 3", unit: "V", values: ripple },
];

const meta = { title: "Plots and datasets/Engineering plot", component: EngineeringPlot, args: { kind: "waveform", title: "Output waveform", x: { label: "Time", unit: "s" }, traces: [{ id: "ch1", label: "Channel 1", unit: "V", values: voltage }] } } satisfies Meta<typeof EngineeringPlot>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Waveform: Story = {};
export const MultiTrace: Story = { args: { traces } };
export const ThresholdCrossing: Story = { args: { kind: "time_series", threshold: { value: 1.2, label: "Warning limit", severity: "warning" } } };
export const HintedMuted: Story = {
  args: {
    traces,
    hints: new Map<string, TraceHint>([["ch3", { colorRole: "muted" }]]),
  },
};
// The sanctioned emphasis composition: muting index 0 releases its accent
// claim, so the accent hint on ch3 wins — exactly one emphasised trace.
export const SanctionedEmphasis: Story = {
  args: {
    traces,
    hints: new Map<string, TraceHint>([["ch1", { colorRole: "muted" }], ["ch3", { colorRole: "accent" }]]),
  },
};
export const HiddenChannel: Story = {
  args: {
    traces,
    hints: new Map<string, TraceHint>([["ch2", { visible: false }]]),
  },
};
export const AllHiddenWithThreshold: Story = {
  args: {
    kind: "time_series",
    traces,
    threshold: { value: 1.2, label: "Warning limit", severity: "warning" },
    hints: new Map<string, TraceHint>(traces.map((trace) => [trace.id, { visible: false }])),
  },
};
