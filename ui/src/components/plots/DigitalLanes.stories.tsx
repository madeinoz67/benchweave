import type { Meta, StoryObj } from "@storybook/react-vite";

import { DigitalLanesPlot, type Lane } from "./DigitalLanesPlot";
import type { LaneState } from "./lane-reduction";

const AXIS = { start: 0, step: 1e-6 };

function states(...runs: [LaneState, number][]): LaneState[] {
  return runs.flatMap(([state, count]) => Array.from({ length: count }, () => state));
}

/** A deterministic four-state capture: a burst, a bus trio and a floating line. */
const lanes: Lane[] = [
  { id: "ch1", label: "CH1", axis: AXIS, states: states(["0", 300], ["1", 200], ["x", 250], ["z", 250]) },
  { id: "ch2", label: "CH2", axis: AXIS, states: states(["1", 1000]) },
  { id: "ch3", label: "CH3", axis: AXIS, states: states(["0", 1000]) },
  { id: "ch4", label: "CH4", axis: AXIS, states: states(["z", 600], ["0", 400]) },
];

const meta = {
  title: "Plots and datasets/Digital lanes",
  component: DigitalLanesPlot,
  args: { title: "Logic capture", x: { label: "Time", unit: "s" }, lanes, columns: 24 },
} satisfies Meta<typeof DigitalLanesPlot>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Capture: Story = {};

export const BusGroup: Story = {
  args: {
    lanes: [
      { id: "a", label: "A", axis: AXIS, states: states(["1", 100]) },
      { id: "b", label: "B", axis: AXIS, states: states(["0", 100]) },
      { id: "c", label: "C", axis: AXIS, states: states(["1", 100]) },
    ],
    groups: [{ id: "bus-a", label: "Bus A", member_ids: ["a", "b", "c"] }],
    columns: 8,
  },
};

export const Triggered: Story = {
  args: { triggerTime: 5.5e-6, cursors: [{ sample: 3 }, { sample: 10 }] },
};

export const HiddenLane: Story = {
  args: { hints: new Map([["ch4", { visible: false }]]) },
};

export const GlitchBurst: Story = {
  args: {
    lanes: [
      {
        id: "ch1",
        label: "CH1",
        axis: AXIS,
        states: Array.from({ length: 257 }, (_, i): LaneState => (i % 2 === 0 ? "0" : "1")),
      },
    ],
    columns: 8,
  },
};
