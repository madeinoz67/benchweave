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
});
