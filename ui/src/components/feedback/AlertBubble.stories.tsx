import type { Meta, StoryObj } from "@storybook/react-vite";

import { AlertBubble } from "./AlertBubble";

const meta = { title: "Feedback and recovery/Alert bubble", component: AlertBubble, args: { severity: "advisory", title: "Evidence note", message: "This reading uses simulated presentation data.", source: "PSU-01 · voltage", onDismiss: () => undefined } } satisfies Meta<typeof AlertBubble>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Advisory: Story = {};
export const Warning: Story = { args: { severity: "warning", title: "Approaching limit", message: "Current is within 5% of its configured limit", onDismiss: undefined } };
export const Critical: Story = { args: { severity: "critical", title: "Limit exceeded", message: "Output voltage exceeds 12.60 V", onDismiss: undefined } };
export const ProtectiveTrip: Story = { args: { severity: "trip", title: "Protection tripped", message: "Output is inhibited. Reconcile the bench before recovery.", onDismiss: undefined } };
