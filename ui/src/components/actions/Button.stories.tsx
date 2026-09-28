import type { Meta, StoryObj } from "@storybook/react-vite";

import { Button } from "./Button";

const meta = { title: "Actions/Button", component: Button, args: { children: "Apply staged value" } } satisfies Meta<typeof Button>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = { args: { variant: "primary" } };
export const Secondary: Story = {};
export const Busy: Story = { args: { busy: true, children: "Submitting request" } };
/** The contract's §C.2 disabled reasons, each rendering its required visible
 *  label beside the control. `no-authority` absorbs the earlier
 *  permission-disabled state (guide rule: controlled actions present their
 *  missing authority as this reason). */
export const DisabledNoAuthority: Story = { args: { disabled: true, disabledReason: { key: "no-authority" }, children: "Apply staged value" } };
export const DisabledProtectionActive: Story = { args: { disabled: true, disabledReason: { key: "protection-active" }, children: "Energise output" } };
export const DisabledCapabilityAbsent: Story = { args: { disabled: true, disabledReason: { key: "capability-absent" }, children: "Run sweep" } };
export const DisabledInvalidStagedInput: Story = { args: { disabled: true, disabledReason: { key: "invalid-staged-input" }, children: "Apply staged value" } };
export const DisabledDeviceState: Story = { args: { disabled: true, disabledReason: { key: "device-state", state: "idle" }, children: "Energise output" } };
export const Protective: Story = { args: { variant: "protective", children: "Disable output" } };
