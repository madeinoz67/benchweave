import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("identifies the mock-up as simulated", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "BenchWeave UI workbench" })).toBeVisible();
    expect(screen.getByText("Simulated presentation data")).toBeVisible();
  });
});
