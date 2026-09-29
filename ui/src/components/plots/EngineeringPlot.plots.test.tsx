import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// S2 (#243 design record §6 slice 2) — PAYLOAD-ASSEMBLY pins. This file
// MOCKS echarts: the ssr-* spans below are this mock's own echo of the
// option object, NOT draw evidence. The G-render rule's draw claims live in
// EngineeringPlot.render.test.tsx (real echarts) — axes drawn, reference
// lines drawn inside and outside extent, the hidden-axis case, the carrier,
// the refusal, the disclosure DOM. What this file pins is what the payload
// ASSERTS: axis bindings, per-item styles, the refusal unit list, the marker
// vocabulary — claims a real renderer could draw wrongly but not claims
// about drawing itself.
const setOption = vi.fn();
const charts: Array<{ getOption: () => Record<string, unknown>; setOption: (o: Record<string, unknown>) => void; dispose: () => void }> = [];
vi.mock("echarts/core", () => ({
  init: (element: HTMLElement) => {
    // The SSR canvas: echarts would render an SVG; in jsdom we mount a
    // minimal stand-in that echoes the option's DRAWN TEXT (axis names,
    // mark-line labels) into the DOM — exactly what the real-render arm
    // needs, so a payload lie cannot pass a draw claim.
    const chart = {
      getOption: () => lastOption,
      setOption: (option: Record<string, unknown>) => {
        lastOption = option;
        const yAxes = option.yAxis as Array<{ name?: string }>;
        for (const axis of yAxes ?? []) {
          if (axis.name) {
            const tag = document.createElement("span");
            tag.className = "ssr-axis-name";
            tag.textContent = axis.name;
            element.appendChild(tag);
          }
        }
        const series = option.series as Array<{ markLine?: { data?: Array<Record<string, unknown>> }; name?: string }>;
        for (const entry of series ?? []) {
          for (const mark of entry.markLine?.data ?? []) {
            const yAxisIndex = (mark as { yAxisIndex?: number }).yAxisIndex;
            const label = ((mark as { label?: { formatter?: string } }).label?.formatter) ?? ((entry.markLine as { label?: { formatter?: string } })?.label?.formatter ?? entry.name);
            if (label) {
              const tag = document.createElement("span");
              tag.className = "ssr-markline-label";
              tag.dataset.yAxisIndex = String(yAxisIndex ?? 0);
              tag.textContent = label;
              element.appendChild(tag);
            }
            // Per-item styling wins (the reference lines); the entry-level
            // markLine.lineStyle carries the threshold's style — exactly the
            // echarts precedence the component relies on.
            const entryStyle = (entry.markLine as { lineStyle?: { color: string; type: string } } | undefined)?.lineStyle;
            const lineStyle = (mark as { lineStyle?: { color: string; type: string } }).lineStyle ?? entryStyle;
            if (lineStyle) {
              const tag = document.createElement("span");
              tag.className = "ssr-markline-style";
              tag.dataset.color = lineStyle.color;
              tag.dataset.type = lineStyle.type;
              element.appendChild(tag);
            }
          }
        }
      },
      resize: () => undefined,
      dispose: () => undefined,
    };
    charts.push(chart);
    return chart;
  },
  use: () => undefined,
}));
let lastOption: Record<string, unknown> = {};

import { EngineeringPlot, type PlotTrace } from "./EngineeringPlot";

const trace = (id: string, unit: string, values: readonly (readonly [number, number])[] = [[0, 1], [1, 2]]): PlotTrace => ({ id, label: id.toUpperCase(), unit, values });

beforeEach(() => {
  setOption.mockClear();
  charts.length = 0;
  lastOption = {};
});
afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPlot(overrides: Partial<React.ComponentProps<typeof EngineeringPlot>> = {}) {
  return render(
    <EngineeringPlot
      kind="time_series"
      title="Axes"
      x={{ label: "Time", unit: "s" }}
      traces={[trace("volt", "V"), trace("amp", "A")]}
      {...overrides}
    />,
  );
}

describe("S2-A3 axes: one y-axis per distinct unit (real-render)", () => {
  it("V+A fixture: two y-axis names in the SVG (V and A); voltage binds axis 1, current axis 2", () => {
    const { container } = renderPlot();
    const names = [...container.querySelectorAll(".ssr-axis-name")].map((n) => n.textContent);
    expect(names).toEqual(["V", "A"]);
    const series = lastOption.series as Array<{ id: string; yAxisIndex: number }>;
    expect(series.find((s) => s.id === "volt")!.yAxisIndex).toBe(0);
    expect(series.find((s) => s.id === "amp")!.yAxisIndex).toBe(1);
  });

  it("first-declaration order: axis 1 = the earliest declared trace's unit", () => {
    renderPlot({ traces: [trace("amp", "A"), trace("volt", "V")] });
    const names = [...document.querySelectorAll(".ssr-axis-name")].map((n) => n.textContent);
    expect(names).toEqual(["A", "V"]);
  });

  it("single-unit fixture: exactly one y-axis", () => {
    const { container } = renderPlot({ traces: [trace("a", "V"), trace("b", "V")] });
    expect(container.querySelectorAll(".ssr-axis-name")).toHaveLength(1);
  });
});

describe("S2-A4 the >2-unit refusal (real-render)", () => {
  it("draws NO series and renders the refusal note naming the units", () => {
    const { container } = renderPlot({ traces: [trace("v", "V"), trace("a", "A"), trace("w", "W")] });
    expect(lastOption.series ?? []).toHaveLength(0);
    const note = container.querySelector(".bw-plot__refusal");
    expect(note).not.toBeNull();
    expect(note!.textContent).toContain("more than two distinct units");
    expect(note!.textContent).toContain("V, A, W");
  });

  it("the refusal note carries role=status (visible, not tooltip-only)", () => {
    const { container } = renderPlot({ traces: [trace("v", "V"), trace("a", "A"), trace("w", "W")] });
    expect(container.querySelector(".bw-plot__refusal")!.getAttribute("role")).toBe("status");
  });
});

describe("S2-A4 reference lines (real-render)", () => {
  it("renders labelled, in the border token, dotted — never a severity hue", () => {
    const { container } = renderPlot({ referenceLines: [{ value: 2, label: "Current limit · 2 A" }] });
    const label = [...container.querySelectorAll(".ssr-markline-label")].find((n) => n.textContent?.includes("Current limit"));
    expect(label).toBeDefined();
    const styles = [...container.querySelectorAll(".ssr-markline-style")].map((n) => ({ color: (n as HTMLElement).dataset.color!, type: (n as HTMLElement).dataset.type! }));
    const dotted = styles.find((s) => s.type === "dotted");
    expect(dotted, "the reference line renders dotted").toBeDefined();
    expect(dotted!.color).toBe("#c3cfd5"); // the light border fallback — the border token
    const severityHues = ["#2476b8", "#a96608", "#b63830", "#a92858", "#177158"];
    expect(severityHues).not.toContain(dotted!.color);
    const seriesTokens = ["#253421", "#8e7588", "#2f3300", "#00379d", "#7e002d", "#746084", "#5a1538", "#183058"];
    expect(seriesTokens).not.toContain(dotted!.color);
  });

  it("distinctness: the severity threshold keeps its dashed severity hue alongside a dotted reference line", () => {
    const { container } = renderPlot({
      threshold: { value: 3, label: "Warning limit", severity: "warning" },
      referenceLines: [{ value: 2, label: "Current limit · 2 A" }],
    });
    const styles = [...container.querySelectorAll(".ssr-markline-style")].map((n) => ({ color: (n as HTMLElement).dataset.color, type: (n as HTMLElement).dataset.type }));
    const dashed = styles.find((s) => s.type === "dashed");
    const dotted = styles.find((s) => s.type === "dotted");
    expect(dashed, "the threshold renders dashed").toBeDefined();
    expect(dotted, "the reference line renders dotted").toBeDefined();
    expect(dashed!.color).not.toBe(dotted!.color);
    expect(dashed!.color).toBe("#a96608"); // the warning severity fallback
    expect(dotted!.color).toBe("#c3cfd5"); // the border token fallback
  });

  it("carrier: a reference line whose target traces are all hidden still renders", () => {
    const { container } = renderPlot({
      traces: [trace("volt", "V")],
      hints: new Map([["volt", { visible: false }]]),
      referenceLines: [{ value: 2, label: "Current limit · 2 A" }],
    });
    const label = [...container.querySelectorAll(".ssr-markline-label")].find((n) => n.textContent?.includes("Current limit"));
    expect(label, "hiding data must not launder away a configured limit").toBeDefined();
  });
});

describe("S2-A2 acquisition disclosure + provenance markers", () => {
  it("discloses decimation outside the canvas; the drawn count is the renderer's own (values.length), never the caller's claim", () => {
    const { container, unmount } = renderPlot({
      traces: [trace("volt", "V", [[0, 1], [1, 2], [2, 3], [3, 4]])],
      acquisition: new Map([["volt", { acquired: 1000 }]]),
    });
    const disclosure = container.querySelector(".bw-plot__acquisition");
    expect(disclosure).not.toBeNull();
    expect(disclosure!.getAttribute("data-bw-acquisition")).toBe("");
    expect(disclosure!.textContent).toContain("Acquired 1000 samples · plotted 4");
    expect(disclosure!.textContent).not.toContain("at ");
    unmount();
    // Folded row 6 RED seed (probe A5): a caller claiming plotted == acquired
    // on a DECIMATED values array — the disclosure MUST still render, because
    // the renderer counts what it drew.
    const liar = renderPlot({
      traces: [trace("volt", "V", [[0, 1], [1, 2]])],
      acquisition: new Map([["volt", { acquired: 100, plotted: 100 }]]),
    });
    expect(liar.container.querySelector(".bw-plot__acquisition"), "the supplied plotted is not trusted").not.toBeNull();
    expect(liar.container.querySelector(".bw-plot__acquisition")!.textContent).toContain("plotted 2");
    unmount();
    liar.unmount();
    const control = renderPlot({
      traces: [trace("volt", "V", [[0, 1], [1, 2]])],
      acquisition: new Map([["volt", { acquired: 2 }]]),
    });
    expect(control.container.querySelector(".bw-plot__acquisition")).toBeNull();
  });

  it("provenance markers: derived, device-averaged, display-processed; measured unmarked", () => {
    const { container } = renderPlot({
      traces: [
        { ...trace("meas", "V"), provenance: undefined },
        { ...trace("der", "V"), provenance: { kind: "derived", detail: "P = V × I" } },
        { ...trace("avg", "V"), provenance: { kind: "device-averaged", detail: "8" } },
        { ...trace("dsp", "V"), provenance: { kind: "display-processed", detail: "median 100 ms" } },
      ],
    });
    const markers = [...container.querySelectorAll(".bw-plot__legend-provenance")].map((n) => n.textContent);
    expect(markers).toEqual([
      "derived · P = V × I · uncertainty unknown",
      "device averaging 8",
      "display processing: median 100 ms",
    ]);
    // measured renders NO marker and NO provenance attribute.
    const measured = [...container.querySelectorAll("li")].find((li) => li.textContent?.startsWith("MEAS"));
    expect(measured!.getAttribute("data-bw-trace-provenance")).toBeNull();
    expect(measured!.querySelector(".bw-plot__legend-provenance")).toBeNull();
    // data-bw-trace-provenance carries the kind on marked traces.
    const derived = [...container.querySelectorAll("li")].find((li) => li.textContent?.startsWith("DER"))!;
    expect(derived.getAttribute("data-bw-trace-provenance")).toBe("derived");
  });

  it("no two kinds share marker vocabulary (device averaging ≠ display processing prefixes)", () => {
    const { container } = renderPlot({
      traces: [
        { ...trace("avg", "V"), provenance: { kind: "device-averaged", detail: "8" } },
        { ...trace("dsp", "V"), provenance: { kind: "display-processed", detail: "median 100 ms" } },
      ],
    });
    const markers = [...container.querySelectorAll(".bw-plot__legend-provenance")].map((n) => n.textContent);
    expect(markers[0]).toContain("device averaging");
    expect(markers[0]).not.toContain("display processing");
    expect(markers[1]).toContain("display processing");
    expect(markers[1]).not.toContain("device averaging");
  });
});
