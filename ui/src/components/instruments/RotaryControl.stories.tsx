import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";

import { NumericInput } from "../inputs/NumericInput";
import { RotaryControl } from "./RotaryControl";

const meta = { title: "Instrument controls/Rotary control", component: RotaryControl, args: { label: "Voltage set-point", value: 12, unit: "V", min: 0, max: 15, step: 0.1, onStage: () => undefined } } satisfies Meta<typeof RotaryControl>;
export default meta;
type Story = StoryObj<typeof meta>;

export const KeyboardOperation: Story = { render: (args) => { const [value, setValue] = useState(args.value); return <div style={{ display: "flex", alignItems: "center", gap: "2rem" }}><RotaryControl {...args} value={value} onStage={setValue} /><NumericInput label={args.label} value={value} unit={args.unit} min={args.min} max={args.max} step={args.step} onChange={setValue} /></div>; } };
