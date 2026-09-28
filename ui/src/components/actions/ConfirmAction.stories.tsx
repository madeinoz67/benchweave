import type { Meta, StoryObj } from "@storybook/react-vite";

import { ConfirmAction } from "./ConfirmAction";

const meta = {
  title: "Actions/ConfirmAction",
  component: ConfirmAction,
  args: {
    label: "Energise output",
    effect: "the output will be energised",
    value: { amount: 12.5, unit: "V" },
    target: "PSU-07 output",
    onConfirm: () => undefined,
  },
} satisfies Meta<typeof ConfirmAction>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Idle: Story = {};
export const DisabledNoAuthority: Story = { args: { disabled: true, disabledReason: { key: "no-authority" } } };
export const DisabledProtectionActive: Story = { args: { disabled: true, disabledReason: { key: "protection-active" } } };
export const WithoutValue: Story = { args: { value: undefined } };
