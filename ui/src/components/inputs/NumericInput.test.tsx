import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NumericInput } from "./NumericInput";

describe("NumericInput", () => {
  it("labels a staged bounded value with its unit", () => {
    const onChange = vi.fn();
    render(<NumericInput label="Voltage set-point" value={12} unit="V" min={0} max={15} step={0.1} onChange={onChange} />);

    const input = screen.getByRole("spinbutton", { name: "Voltage set-point" });
    expect(input).toHaveAccessibleDescription("Staged value; use Apply to request the change");
    expect(screen.getByText("V")).toBeVisible();
    fireEvent.change(input, { target: { value: "18" } });
    expect(onChange).toHaveBeenCalledWith(15);
  });
});
