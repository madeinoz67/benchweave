import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("echarts/core", () => ({
  init: () => ({ setOption: () => undefined, resize: () => undefined, dispose: () => undefined }),
  use: () => undefined,
}));

import { App } from "./App";

describe("App", () => {
  it("identifies the mock-up as simulated", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "BenchWeave UI workbench" })).toBeVisible();
    expect(screen.getByText("Simulated presentation data")).toBeVisible();
  });

  it("lets the operator switch to the matched dark theme", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));

    expect(screen.getByRole("main")).toHaveAttribute("data-theme", "dark");
    expect(screen.getByRole("button", { name: "Use light theme" })).toBeVisible();
  });
});
