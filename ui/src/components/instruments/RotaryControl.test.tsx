import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RotaryControl } from "./RotaryControl";

describe("RotaryControl", () => {
  it("stages a bounded value and never claims to apply it", () => {
    const onStage = vi.fn();
    render(<RotaryControl label="Voltage set-point" value={12} unit="V" min={0} max={15} step={0.1} onStage={onStage} />);

    fireEvent.keyDown(screen.getByRole("slider", { name: "Voltage set-point" }), { key: "ArrowUp" });

    expect(onStage).toHaveBeenCalledWith(12.1);
    expect(screen.queryByText(/applied/i)).not.toBeInTheDocument();
    expect(screen.getByText("Staged")).toBeVisible();
  });
});
