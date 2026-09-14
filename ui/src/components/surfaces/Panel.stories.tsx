import type { Meta, StoryObj } from "@storybook/react-vite";

import { Panel } from "./Panel";

const meta = {
  title: "Foundations/Panel",
  component: Panel,
  args: { title: "Output", eyebrow: "DC power supply", children: "12.04 V" },
} satisfies Meta<typeof Panel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Raised: Story = {};
export const Recessed: Story = { args: { title: "Voltage trend", eyebrow: "Last 60 seconds", recessed: true, children: "Plot surface" } };
