import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmAction } from "./ConfirmAction";

describe("ConfirmAction (contract §C.1 R-ENERGISE-1)", () => {
  const props = {
    label: "Energise output",
    effect: "the output will be energised",
    value: { amount: 12.5, unit: "V" },
    target: "PSU-07 output",
    onConfirm: vi.fn(),
  };

  it("stages on the first action and fires only on the second explicit action", () => {
    const onConfirm = vi.fn();
    render(<ConfirmAction {...props} onConfirm={onConfirm} />);

    fireEvent.click(screen.getByRole("button", { name: "Energise output" }));
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm: Energise output" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("states the effect, the exact value with unit, and the target in the confirm step", () => {
    render(<ConfirmAction {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Energise output" }));
    const text = screen.getByText(/the output will be energised/);
    expect(text).toBeVisible();
    expect(text.textContent).toContain("12.5 V");
    expect(text.textContent).toContain("PSU-07 output");
  });

  it("cancel disarms without firing", () => {
    const onConfirm = vi.fn();
    render(<ConfirmAction {...props} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button", { name: "Energise output" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.queryByText(/the output will be energised/)).not.toBeInTheDocument();
  });

  it("carries the disabled reason onto the initial control (R-PROTECT-1 shape)", () => {
    render(<ConfirmAction {...props} disabled disabledReason={{ key: "protection-active" }} />);
    const button = screen.getByRole("button", { name: "Energise output" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("data-bw-disabled-reason", "protection-active");
    expect(screen.getByText("Protection trip active")).toBeVisible();
  });
});
