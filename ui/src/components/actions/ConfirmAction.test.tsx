import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmAction } from "./ConfirmAction";
import type { DisabledReason } from "./disabledReasons";

const props = {
  label: "Energise output",
  effect: "the output will be energised",
  value: { amount: 12.5, unit: "V" },
  target: "PSU-07 output",
  onConfirm: vi.fn(),
};

describe("ConfirmAction (contract §C.1 R-ENERGISE-1)", () => {

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

describe("ConfirmAction armed guard (R-PROTECT-1 holds at FIRE time)", () => {
  function armedThenGuarded(guard: { disabled?: boolean; disabledReason?: DisabledReason }) {
    const onConfirm = vi.fn();
    const initial = render(
      <ConfirmAction {...props} onConfirm={onConfirm} />,
    );
    fireEvent.click(initial.getByRole("button", { name: "Energise output" }));
    initial.rerender(
      <ConfirmAction {...props} {...guard} onConfirm={onConfirm} />,
    );
    return { initial, onConfirm };
  }

  it("disables the armed Confirm when the guard arrives, and does not dispatch on click", () => {
    const { initial, onConfirm } = armedThenGuarded({ disabled: true, disabledReason: { key: "protection-active" } });
    const confirm = initial.getByRole("button", { name: "Confirm: Energise output" });
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAttribute("data-bw-disabled-reason", "protection-active");
    expect(initial.getAllByText("Protection trip active").length).toBe(2);
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("keeps Cancel enabled under the guard — the staged intent is never silently discarded", () => {
    const { initial } = armedThenGuarded({ disabled: true, disabledReason: { key: "no-authority" } });
    expect(initial.getByRole("button", { name: "Cancel" })).toBeEnabled();
    expect(initial.getAllByText("No lease or policy authority").length).toBe(2);
  });

  it("re-enables the armed Confirm when the guard departs", () => {
    const { initial, onConfirm } = armedThenGuarded({ disabled: true, disabledReason: { key: "protection-active" } });
    initial.rerender(<ConfirmAction {...props} onConfirm={onConfirm} />);
    expect(initial.getByRole("button", { name: "Confirm: Energise output" })).toBeEnabled();
  });

  it("renders the armed presentation from initiallyArmed (the story/test seam)", () => {
    render(<ConfirmAction {...props} initiallyArmed />);
    expect(screen.getByText(/the output will be energised/)).toBeVisible();
  });
});
