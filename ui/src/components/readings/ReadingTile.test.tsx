import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReadingTile } from "./ReadingTile";

describe("ReadingTile", () => {
  it("shows severity, value, unit, quality and freshness as text", () => {
    render(<ReadingTile label="Output voltage" value="13.21" unit="V" freshness="84 ms" quality="Verified" severity="critical" />);

    const reading = screen.getByRole("region", { name: "Output voltage" });
    expect(reading).toHaveAttribute("data-severity", "critical");
    expect(reading).toHaveTextContent("13.21 V");
    expect(reading).toHaveTextContent("Critical");
    expect(reading).toHaveTextContent("Verified · 84 ms");
  });
});
