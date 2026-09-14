import type { Meta, StoryObj } from "@storybook/react-vite";

import { DeviceWorkbench } from "./DeviceWorkbench";
import { warningWorkbench } from "./fixtures";

const meta = { title: "Operator compositions/Device workbench", component: DeviceWorkbench, args: { fixture: warningWorkbench } } satisfies Meta<typeof DeviceWorkbench>;
export default meta;
type Story = StoryObj<typeof meta>;

export const LayeredPrecision: Story = {};
