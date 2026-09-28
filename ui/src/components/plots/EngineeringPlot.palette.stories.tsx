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
