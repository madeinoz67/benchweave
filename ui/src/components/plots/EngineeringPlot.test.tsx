import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("echarts/core", () => ({
  init: () => ({ setOption: () => undefined, resize: () => undefined, dispose: () => undefined }),
  use: () => undefined,
}));

import { EngineeringPlot } from "./EngineeringPlot";

describe("EngineeringPlot", () => {
  it("exposes trace identity, axes and units outside colour", () => {
    render(
      <EngineeringPlot
        kind="waveform"
        title="Output waveform"
        x={{ label: "Time", unit: "s" }}
        traces={[{ id: "ch1", label: "Channel 1", unit: "V", values: [[0, 0], [0.001, 3.3]] }]}
      />,
    );

    expect(screen.getByRole("img", { name: "Output waveform" })).toHaveAccessibleDescription(
      "Time in s; Channel 1 in V",
    );
    expect(screen.getByText("Channel 1 · V")).toBeVisible();
  });
});
