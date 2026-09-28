import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("preserves native disabled and busy semantics", () => {
    render(<Button variant="protective" busy disabled>Disable output</Button>);

    const button = screen.getByRole("button", { name: "Disable output" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAttribute("data-variant", "protective");
  });

  it("carries the contract's disabled reason and its required visible label (§C.2)", () => {
    const { container } = render(
      <Button disabled disabledReason={{ key: "protection-active" }}>Energise output</Button>,
    );
    const button = screen.getByRole("button", { name: "Energise output" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("data-bw-disabled-reason", "protection-active");
    const label = container.querySelector("[data-bw-disabled-label]");
    expect(label).not.toBeNull();
    expect(label!.textContent).toBe("Protection trip active");
  });

  it("does not render a reason attribute or label for an enabled control", () => {
    const { container } = render(<Button disabledReason={{ key: "no-authority" }}>Act</Button>);
    expect(container.querySelector("[data-bw-disabled-reason]")).toBeNull();
    expect(container.querySelector("[data-bw-disabled-label]")).toBeNull();
  });
});
