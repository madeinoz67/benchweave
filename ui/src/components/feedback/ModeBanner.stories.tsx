import type { Meta, StoryObj } from "@storybook/react-vite";

import { ModeBanner } from "./ModeBanner";

const meta = { title: "Feedback and recovery/ModeBanner", component: ModeBanner } satisfies Meta<typeof ModeBanner>;
export default meta;
type Story = StoryObj<typeof meta>;

export const SimulatedOnly: Story = { args: { modes: ["simulated"] } };
export const NoGatewayOnly: Story = { args: { modes: ["no-gateway"] } };
export const NoLeaseOnly: Story = { args: { modes: ["no-lease"] } };
export const NoPolicyOnly: Story = { args: { modes: ["no-policy"] } };
export const AllModes: Story = { args: { modes: ["simulated", "no-gateway", "no-lease", "no-policy"] } };
/** Absence of the banner asserts full-authority presentation — the empty list
 *  renders nothing, and this story is that state's visible record. */
export const NoActiveModes: Story = { args: { modes: [] } };
