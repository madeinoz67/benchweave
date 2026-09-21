import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, afterEach } from "vitest";

// No echarts mock in this file: these assertions run the REAL renderer
// against the component's output, closing the setOption-mock blind spot —
// a payload can record an option echarts then fails to draw (FC1).
import { EngineeringPlot, type PlotTrace, type TraceHint } from "./EngineeringPlot";

const traces: PlotTrace[] = [
  { id: "a", label: "Channel A", unit: "V", values: [[0, 0], [1, 1]] },
  { id: "b", label: "Channel B", unit: "V", values: [[0, 1], [1, 0]] },
];

function canvasSvg(container: HTMLElement): Element {
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

  it("redraws the SVG with the flipped theme's accent (FC6, real renderer)", async () => {
    // Metric D at the FC1 bar: the theme tokens are keyed to the DOM
    // (light accent #0b7181, dark accent #42cee2) and the flip must reach
    // the drawn pixels through a fresh render, not just a recorded option.
    vi.stubGlobal("getComputedStyle", (element: Element) => ({
      getPropertyValue: (name: string) => {
        const theme = element.closest("[data-theme]")?.getAttribute("data-theme") ?? "light";
        if (name === "--bw-accent") return theme === "dark" ? "#42cee2" : "#0b7181";
        if (name === "--bw-text-muted") return theme === "dark" ? "#9fb4bd" : "#5b6a73";
        return "";
      },
    }));
    const { container } = render(
      <div data-theme="light">
        <EngineeringPlot
          kind="time_series"
          title="Theme flip"
          x={{ label: "Time", unit: "s" }}
          traces={traces}
        />
      </div>,
    );
    expect(canvasSvg(container).innerHTML).toContain("#0b7181");

    container.firstElementChild!.setAttribute("data-theme", "dark");
    await waitFor(() => expect(canvasSvg(container).innerHTML).toContain("#42cee2"));
    expect(canvasSvg(container).innerHTML).not.toContain("#0b7181");
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});
