import type { Meta, StoryObj } from "@storybook/react-vite";

import { Button } from "./Button";

const meta = { title: "Actions/Button", component: Button, args: { children: "Apply staged value" } } satisfies Meta<typeof Button>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = { args: { variant: "primary" } };
export const Secondary: Story = {};
export const Busy: Story = { args: { busy: true, children: "Submitting request" } };
export const PermissionDisabled: Story = { args: { disabled: true, title: "Controller permission required" } };
export const Protective: Story = { args: { variant: "protective", children: "Disable output" } };
