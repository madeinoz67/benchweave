import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AlertBubble } from "./AlertBubble";

describe("AlertBubble", () => {
  it("makes a protective trip persistent and assertive", () => {
    render(<AlertBubble severity="trip" title="Protection tripped" message="Output is inhibited." onDismiss={vi.fn()} />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Protection tripped");
    expect(alert).toHaveAttribute("data-severity", "trip");
    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument();
  });

  it("allows low-consequence advisory messages to be dismissed", () => {
    render(<AlertBubble severity="advisory" title="Evidence note" message="Synthetic source." onDismiss={vi.fn()} />);

    expect(screen.getByRole("status")).toBeVisible();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeVisible();
  });
});
