import type { Meta, StoryObj } from "@storybook/react-vite";

import { EngineeringPlot } from "./EngineeringPlot";

const voltage = Array.from({ length: 80 }, (_, index) => [index / 10000, Math.sin(index / 6) * 1.65] as const);
const digital = Array.from({ length: 80 }, (_, index) => [index / 10000, index % 20 < 10 ? 2.5 : -2.5] as const);

const meta = { title: "Plots and datasets/Engineering plot", component: EngineeringPlot, args: { kind: "waveform", title: "Output waveform", x: { label: "Time", unit: "s" }, traces: [{ id: "ch1", label: "Channel 1", unit: "V", values: voltage }] } } satisfies Meta<typeof EngineeringPlot>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Waveform: Story = {};
export const MultiTrace: Story = { args: { traces: [{ id: "ch1", label: "Channel 1", unit: "V", values: voltage }, { id: "ch2", label: "Channel 2", unit: "V", values: digital }] } };
export const ThresholdCrossing: Story = { args: { kind: "time_series", threshold: { value: 1.2, label: "Warning limit", severity: "warning" } } };
