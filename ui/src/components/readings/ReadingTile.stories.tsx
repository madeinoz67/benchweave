import type { Meta, StoryObj } from "@storybook/react-vite";

import { ReadingTile } from "./ReadingTile";

const meta = { title: "Readings and state/Reading tile", component: ReadingTile, args: { label: "Output voltage", value: "12.04", unit: "V", freshness: "84 ms", quality: "Verified", severity: "success" } } satisfies Meta<typeof ReadingTile>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Normal: Story = {};
export const Advisory: Story = { args: { severity: "advisory", quality: "Synthetic evidence" } };
export const Warning: Story = { args: { severity: "warning", value: "12.42", quality: "Near limit" } };
export const Critical: Story = { args: { severity: "critical", value: "13.21", quality: "Limit exceeded" } };
export const ProtectiveTrip: Story = { args: { severity: "trip", value: "Unknown", unit: null, quality: "Output inhibited" } };
