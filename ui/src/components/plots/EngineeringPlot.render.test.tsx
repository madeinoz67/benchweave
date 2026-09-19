import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

// No echarts mock in this file: these assertions run the REAL renderer
// against the component's output, closing the setOption-mock blind spot —
// a payload can record an option echarts then fails to draw (FC1).
import { EngineeringPlot, type PlotTrace, type TraceHint } from "./EngineeringPlot";

const traces: PlotTrace[] = [
  { id: "a", label: "Channel A", unit: "V", values: [[0, 0], [1, 1]] },
  { id: "b", label: "Channel B", unit: "V", values: [[0, 1], [1, 0]] },
];

function canvasSvg(container: HTMLElement): SVGSVGElement {
  const svg = container.querySelector(".bw-plot__canvas svg");
  expect(svg, "echarts rendered an SVG into the canvas").toBeTruthy();
  return svg!;
}

describe("EngineeringPlot real rendering", () => {
  it("draws the threshold label through real echarts when every channel is hidden", () => {
    // Threshold 1.2 sits OUTSIDE the [0,1] extent the carrier's data would
    // default to: only a threshold value that participates in the y-axis
    // extent can draw here (FC1 — falsified with the repo's own echarts:
    // an empty-data carrier rendered a 1146-byte SVG with no mark line).
    const hints = new Map(traces.map((trace) => [trace.id, { visible: false } as TraceHint]));
    const { container } = render(
      <EngineeringPlot
        kind="time_series"
        title="All hidden"
        x={{ label: "Time", unit: "s" }}
        traces={traces}
        threshold={{ value: 1.2, label: "Warning limit", severity: "warning" }}
        hints={hints}
      />,
    );

    expect(canvasSvg(container).textContent).toContain("Warning limit");
  });

  it("draws series lines through real echarts on the visible control", () => {
    const { container } = render(
      <EngineeringPlot
        kind="time_series"
        title="Visible control"
        x={{ label: "Time", unit: "s" }}
        traces={traces}
        threshold={{ value: 0.5, label: "Warning limit", severity: "warning" }}
      />,
    );

    expect(canvasSvg(container).textContent).toContain("Warning limit");
  });
});
