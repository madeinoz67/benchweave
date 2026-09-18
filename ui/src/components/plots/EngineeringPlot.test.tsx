import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// The mock captures every setOption payload so trace styling is asserted on the
// real option object echarts would receive, never on rendered pixels. jsdom's
// getComputedStyle returns no custom properties, so the component resolves the
// documented fallback literals: accent #0b7181, alert #a96608, muted #5b6a73.
const setOption = vi.fn();
vi.mock("echarts/core", () => ({
  init: () => ({ setOption, resize: () => undefined, dispose: () => undefined }),
  use: () => undefined,
}));

import { EngineeringPlot, type PlotTrace, type TraceHint } from "./EngineeringPlot";

const traces: PlotTrace[] = [
  { id: "a", label: "Channel A", unit: "V", values: [[0, 0], [1, 1]] },
  { id: "b", label: "Channel B", unit: "V", values: [[0, 1], [1, 0]] },
  { id: "c", label: "Channel C", unit: "V", values: [[0, 0.5], [1, 0.5]] },
];

function series() {
  expect(setOption).toHaveBeenCalled();
  return setOption.mock.calls[0][0].series as Array<{
    id: string;
    symbol: string;
    lineStyle: { color: string; type: string };
    itemStyle: { color: string };
  }>;
}

function seriesOf(id: string) {
  const row = series().find((entry) => entry.id === id);
  expect(row, `trace ${id} present in option payload`).toBeDefined();
  return row!;
}

beforeEach(() => {
  setOption.mockClear();
});

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

  it("assigns index-derived styles when no hints are supplied (inertness)", () => {
    render(
      <EngineeringPlot kind="waveform" title="Untinted" x={{ label: "Time", unit: "s" }} traces={traces} />,
    );

    // Pass-1 defaults pinned against literal expectations: index 0 takes the
    // accent token, every other index the threshold-severity token; symbol and
    // line style alternate on index % 2.
    expect(seriesOf("a")).toMatchObject({
      symbol: "circle",
      lineStyle: { color: "#0b7181", type: "solid" },
      itemStyle: { color: "#0b7181" },
    });
    expect(seriesOf("b")).toMatchObject({
      symbol: "diamond",
      lineStyle: { color: "#a96608", type: "dashed" },
      itemStyle: { color: "#a96608" },
    });
    expect(seriesOf("c")).toMatchObject({
      symbol: "circle",
      lineStyle: { color: "#a96608", type: "solid" },
      itemStyle: { color: "#a96608" },
    });
  });

  it("biases hinted traces to the hinted role while others keep pass-1 styles", () => {
    const hints = new Map<string, TraceHint>([["b", { colorRole: "accent" }]]);
    render(
      <EngineeringPlot
        kind="waveform"
        title="Hinted"
        x={{ label: "Time", unit: "s" }}
        traces={traces}
        hints={hints}
      />,
    );

    expect(seriesOf("b").lineStyle.color).toBe("#0b7181");
    expect(seriesOf("b").itemStyle.color).toBe("#0b7181");
    expect(seriesOf("a")).toMatchObject({
      symbol: "circle",
      lineStyle: { color: "#0b7181", type: "solid" },
      itemStyle: { color: "#0b7181" },
    });
    expect(seriesOf("c")).toMatchObject({
      symbol: "circle",
      lineStyle: { color: "#a96608", type: "solid" },
      itemStyle: { color: "#a96608" },
    });
  });

  it("resolves the muted role to the text-muted token", () => {
    const hints = new Map<string, TraceHint>([["c", { colorRole: "muted" }]]);
    render(
      <EngineeringPlot
        kind="waveform"
        title="Muted"
        x={{ label: "Time", unit: "s" }}
        traces={traces}
        hints={hints}
      />,
    );

    expect(seriesOf("c").lineStyle.color).toBe("#5b6a73");
    expect(seriesOf("a").lineStyle.color).toBe("#0b7181");
    expect(seriesOf("b").lineStyle.color).toBe("#a96608");
  });

  it("lets the earliest accent hint win; later accent hints revert to pass-1", () => {
    const hints = new Map<string, TraceHint>([
      ["b", { colorRole: "accent" }],
      ["c", { colorRole: "accent" }],
    ]);
    render(
      <EngineeringPlot
        kind="waveform"
        title="Collision"
        x={{ label: "Time", unit: "s" }}
        traces={traces}
        hints={hints}
      />,
    );

    expect(seriesOf("b").lineStyle.color).toBe("#0b7181");
    expect(seriesOf("c").lineStyle.color).toBe("#a96608");
  });

  it("filters hidden traces after style resolution so surviving indices never shift", () => {
    const hints = new Map<string, TraceHint>([["b", { visible: false }]]);
    render(
      <EngineeringPlot
        kind="waveform"
        title="Hidden middle channel"
        x={{ label: "Time", unit: "s" }}
        traces={traces}
        hints={hints}
      />,
    );

    const rendered = series();
    expect(rendered.map((entry) => entry.id)).toEqual(["a", "c"]);
    // a and c keep exactly the styles they carry in the no-hints control.
    expect(rendered[0]).toMatchObject({
      symbol: "circle",
      lineStyle: { color: "#0b7181", type: "solid" },
      itemStyle: { color: "#0b7181" },
    });
    expect(rendered[1]).toMatchObject({
      symbol: "circle",
      lineStyle: { color: "#a96608", type: "solid" },
      itemStyle: { color: "#a96608" },
    });
    // The accessible description drops the hidden channel; the HTML legend
    // discloses it as a struck-through row instead.
    expect(screen.getByRole("img", { name: "Hidden middle channel" })).toHaveAccessibleDescription(
      "Time in s; Channel A in V; Channel C in V",
    );
    const hidden = screen.getByText("Channel B · V").closest("li");
    expect(hidden).not.toBeNull();
    expect(hidden).toHaveAttribute("data-hidden", "true");
    const visible = screen.getByText("Channel A · V").closest("li");
    expect(visible).not.toHaveAttribute("data-hidden");
  });

  it("keeps the threshold mark line when a non-index-0 trace is hidden", () => {
    const hints = new Map<string, TraceHint>([["b", { visible: false }]]);
    render(
      <EngineeringPlot
        kind="time_series"
        title="Threshold survives"
        x={{ label: "Time", unit: "s" }}
        traces={traces}
        threshold={{ value: 1.2, label: "Warning limit", severity: "warning" }}
        hints={hints}
      />,
    );

    const carrier = series().find((entry) => entry.markLine !== undefined);
    expect(carrier).toBeDefined();
    expect(carrier!.id).toBe("a");
    expect(carrier!.markLine.lineStyle.color).toBe("#a96608");
  });
});
