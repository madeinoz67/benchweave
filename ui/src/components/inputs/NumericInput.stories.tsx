import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";

import { NumericInput } from "./NumericInput";

const meta = { title: "Inputs/Numeric input", component: NumericInput, args: { label: "Voltage set-point", value: 12, unit: "V", min: 0, max: 15, step: 0.1, onChange: () => undefined } } satisfies Meta<typeof NumericInput>;
export default meta;
type Story = StoryObj<typeof meta>;

export const StagedValue: Story = { render: (args) => { const [value, setValue] = useState(args.value); return <NumericInput {...args} value={value} onChange={setValue} />; } };
export const Minimum: Story = { args: { value: 0 } };
export const Maximum: Story = { args: { value: 15 } };
