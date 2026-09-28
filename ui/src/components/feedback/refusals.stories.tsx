import type { Meta, StoryObj } from "@storybook/react-vite";

import { REFUSALS, RefusalMessage, type RefusalCode } from "./refusals";

const meta = { title: "Feedback and recovery/RefusalMessage", component: RefusalMessage } satisfies Meta<typeof RefusalMessage>;
export default meta;
type Story = StoryObj<typeof meta>;

/** The no-response row is the presentation boundary's A06 face: no interface
 *  answer arrived, so whether anything was sent is UNKNOWN. */
export const NoResponse: Story = { args: { code: "no-response" } };
export const RateLimited: Story = { args: { code: "rate_limited" } };
export const Unavailable: Story = { args: { code: "unavailable" } };
export const NotFound: Story = { args: { code: "not_found" } };
export const PolicyDenied: Story = { args: { code: "policy_denied" } };

/** Every interface code's refusal, rendered from the same mapping the
 *  presentation boundary uses — the catalogue story. */
export const AllRefusals: Story = {
  args: { code: "no-response" },
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {(Object.keys(REFUSALS) as RefusalCode[]).map((code) => (
        <RefusalMessage key={code} code={code} />
      ))}
    </div>
  ),
};
