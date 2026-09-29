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

  it("redraws the SVG with the flipped theme's series token (FC6, real renderer)", async () => {
    // Metric D at the FC1 bar: the theme tokens are keyed to the DOM
    // (light series-1 #253421, dark series-1 #00744a — evolved with #242
    // slice 3: pass-1 slot-1 is the series-1 token) and the flip must reach
    // the drawn pixels through a fresh render, not just a recorded option.
    vi.stubGlobal("getComputedStyle", (element: Element) => ({
      getPropertyValue: (name: string) => {
        const theme = element.closest("[data-theme]")?.getAttribute("data-theme") ?? "light";
        if (name === "--bw-series-1") return theme === "dark" ? "#00744a" : "#253421";
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
    expect(canvasSvg(container).innerHTML).toContain("#253421");

    container.firstElementChild!.setAttribute("data-theme", "dark");
    await waitFor(() => expect(canvasSvg(container).innerHTML).toContain("#00744a"));
    expect(canvasSvg(container).innerHTML).not.toContain("#253421");
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- #243 slice 2: REAL-render arms (the G-render rule — the draw claims
// the payload-mock file cannot make). These run the real echarts SVG. ---
const volt: PlotTrace = { id: "v", label: "VOLT", unit: "V", values: [[0, 0.1], [1, 0.6]] };
const amp: PlotTrace = { id: "a", label: "AMP", unit: "A", values: [[0, 0.2], [1, 0.8]] };

describe("EngineeringPlot real rendering — slice 2 axes", () => {
  it("draws a second named y-axis for a two-unit plot (the A axis exists)", () => {
    const { container } = render(
      <EngineeringPlot kind="time_series" title="Dual unit" x={{ label: "Time", unit: "s" }} traces={[volt, amp]} />,
    );
    const svg = canvasSvg(container);
    expect(svg.textContent).toContain("V");
    expect(svg.textContent).toContain("A");
  });

  it("filters an axis whose every bound trace is presentation-hidden (no ghost axis)", () => {
    // Real echarts draws the axis NAME into the SVG (the series name is
    // tooltip-only): the control below shows the A axis name present with
    // the trace visible; the filtered case must drop it.
    const control = render(
      <EngineeringPlot kind="time_series" title="Both visible" x={{ label: "Time", unit: "s" }} traces={[volt, amp]} />,
    );
    const controlSvg = canvasSvg(control.container);
    const axisNames = [...controlSvg.querySelectorAll("text")].map((t) => t.textContent).filter((t) => t === "A" || t === "V");
    expect(axisNames, "the control draws both unit axes").toContain("A");
    expect(axisNames).toContain("V");
    control.unmount();
    const { container } = render(
      <EngineeringPlot
        kind="time_series"
        title="A hidden"
        x={{ label: "Time", unit: "s" }}
        traces={[volt, amp]}
        hints={new Map([["a", { visible: false }]])}
      />,
    );
    const svg = canvasSvg(container);
    const names = [...svg.querySelectorAll("text")].map((t) => t.textContent).filter((t) => t === "A" || t === "V");
    expect(names, "the hidden unit's axis does not render").not.toContain("A");
    expect(names, "the visible unit's axis stays").toContain("V");
  });
});

describe("EngineeringPlot real rendering — slice 2 reference lines", () => {
  it("draws an out-of-extent reference line (the unexceeded limit — traces max 0.6, line at 2)", () => {
    const { container } = render(
      <EngineeringPlot
        kind="time_series"
        title="Limit above"
        x={{ label: "Time", unit: "s" }}
        traces={[volt]}
        referenceLines={[{ value: 2, label: "Current limit · 2 A" }]}
      />,
    );
    expect(canvasSvg(container).textContent).toContain("Current limit · 2 A");
  });

  it("draws an in-extent reference line", () => {
    const { container } = render(
      <EngineeringPlot
        kind="time_series"
        title="Limit inside"
        x={{ label: "Time", unit: "s" }}
        traces={[volt]}
        referenceLines={[{ value: 0.4, label: "Current limit · 0.4 A" }]}
      />,
    );
    expect(canvasSvg(container).textContent).toContain("Current limit · 0.4 A");
  });

  it("binds a limit to its target axis: an A-unit limit outside the V extent draws on a V+A plot", () => {
    const { container } = render(
      <EngineeringPlot
        kind="time_series"
        title="Cross extent"
        x={{ label: "Time", unit: "s" }}
        traces={[volt, amp]}
        referenceLines={[{ value: 8, label: "Amp clamp · 8 A", unit: "A" }]}
      />,
    );
    expect(canvasSvg(container).textContent).toContain("Amp clamp · 8 A");
  });

  it("multi-line all-hidden carrier: BOTH reference-line labels draw when every trace is hidden", () => {
    const { container } = render(
      <EngineeringPlot
        kind="time_series"
        title="All hidden two limits"
        x={{ label: "Time", unit: "s" }}
        traces={[volt, amp]}
        hints={new Map([["v", { visible: false }], ["a", { visible: false }]])}
        referenceLines={[{ value: 2, label: "Low limit · 2 V", unit: "V" }, { value: 8, label: "High clamp · 8 A", unit: "A" }]}
      />,
    );
    const svg = canvasSvg(container);
    expect(svg.textContent).toContain("Low limit · 2 V");
    expect(svg.textContent).toContain("High clamp · 8 A");
  });
});

describe("EngineeringPlot real rendering — slice 2 refusal + disclosure", () => {
  it("the >2-unit refusal draws NO series and renders the note (real renderer)", () => {
    const watt: PlotTrace = { id: "w", label: "WATT", unit: "W", values: [[0, 0.3], [1, 0.5]] };
    const { container } = render(
      <EngineeringPlot kind="time_series" title="Three units" x={{ label: "Time", unit: "s" }} traces={[volt, amp, watt]} />,
    );
    expect(container.querySelector(".bw-plot__refusal")).not.toBeNull();
    expect(container.querySelector(".bw-plot__refusal")!.textContent).toContain("more than two distinct units");
    // No canvas SVG is drawn at all: the effect returns before echarts.init.
    expect(container.querySelector(".bw-plot__canvas svg")).toBeNull();
  });

  it("the disclosure renders outside the canvas on the real renderer", () => {
    const decimated: PlotTrace = { id: "v", label: "VOLT", unit: "V", values: [[0, 0.1], [1, 0.6]] };
    const { container } = render(
      <EngineeringPlot
        kind="time_series"
        title="Decimated"
        x={{ label: "Time", unit: "s" }}
        traces={[decimated]}
        acquisition={new Map([["v", { acquired: 100 }]])}
      />,
    );
    const disclosure = container.querySelector(".bw-plot__acquisition");
    expect(disclosure).not.toBeNull();
    expect(disclosure!.textContent).toContain("Acquired 100 samples · plotted 2");
  });
});
