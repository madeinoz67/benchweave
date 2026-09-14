import type { Meta, StoryObj } from "@storybook/react-vite";

import { AdminOverview } from "./AdminOverview";
import { adminFixture } from "./fixtures";

const meta = { title: "Administrative compositions/Overview", component: AdminOverview, args: { fixture: adminFixture } } satisfies Meta<typeof AdminOverview>;
export default meta;
type Story = StoryObj<typeof meta>;

export const LayeredPrecision: Story = {};
