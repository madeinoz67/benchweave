import type { Meta, StoryObj } from "@storybook/react-vite";

import { DataTable } from "./DataTable";

const meta = { title: "Plots and datasets/Data table", component: DataTable, args: { caption: "Channel readings", rows: [{ id: "ch1", voltage: "12.04 V", current: "1.92 A", quality: "Verified" }, { id: "ch2", voltage: "5.01 V", current: "0.24 A", quality: "Stale · 4.2 s" }], rowKey: (row: { id: string }) => row.id, columns: [{ id: "channel", header: "Channel", cell: (row: { id: string }) => row.id }, { id: "voltage", header: "Voltage", cell: (row: { voltage: string }) => row.voltage }, { id: "current", header: "Current", cell: (row: { current: string }) => row.current }, { id: "quality", header: "Quality", cell: (row: { quality: string }) => row.quality }] } } satisfies Meta<typeof DataTable>;
export default meta;
type Story = StoryObj<typeof meta>;

export const ChannelReadings: Story = {};
