import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The mock captures every setOption payload so trace styling is asserted on the
// real option object echarts would receive, never on rendered pixels. jsdom's
// getComputedStyle returns no custom properties, so the component resolves the
// documented fallback literals: accent #0b7181, alert #a96608 — and a MISSING
// text-muted token makes a muted hint fall back to the pass-1 default (C4).
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
    markLine?: { lineStyle: { color: string } };
  }>;
}

function seriesOf(id: string) {
  const row = series().find((entry) => entry.id === id);
  expect(row, `trace ${id} present in option payload`).toBeDefined();
  return row!;
}

function plot(hints?: Map<string, TraceHint>, extra?: { threshold?: boolean }) {
  render(
    <EngineeringPlot
      kind="waveform"
      title="Plot"
      x={{ label: "Time", unit: "s" }}
      traces={traces}
      hints={hints}
      threshold={extra?.threshold ? { value: 1.2, label: "Warning limit", severity: "warning" } : undefined}
    />,
  );
}

/** Stub the theme so --bw-text-muted resolves; every other token stays absent
 *  (falling back to the documented literals). */
function stubMutedToken(value: string) {
  vi.stubGlobal("getComputedStyle", () => ({
    getPropertyValue: (name: string) => (name === "--bw-text-muted" ? value : ""),
  }));
}

beforeEach(() => {
  setOption.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
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

  it("an accent hint on a non-index-0 trace loses silently to index 0's default claim", () => {
    // C1 ruling: pass-1 index-0 accent is the FIRST claim. A later accent
    // hint reverts to its own pass-1 default — uniqueness and no-cascade both
    // hold; the hint loses silently.
    plot(new Map([["b", { colorRole: "accent" }]]));

    expect(seriesOf("a").lineStyle.color).toBe("#0b7181");
    expect(seriesOf("b").lineStyle.color).toBe("#a96608");
    expect(seriesOf("c").lineStyle.color).toBe("#a96608");
  });

  it("resolves the muted role to the theme's text-muted token when present", () => {
    stubMutedToken("#777777");
    plot(new Map([["c", { colorRole: "muted" }]]));

    expect(seriesOf("c").lineStyle.color).toBe("#777777");
    expect(seriesOf("a").lineStyle.color).toBe("#0b7181");
    expect(seriesOf("b").lineStyle.color).toBe("#a96608");
  });

  it("falls back to the pass-1 default when the theme lacks the muted token", () => {
    // C4: jsdom resolves no custom properties; a missing token must fall back
    // to the trace's pass-1 default, never paint a light-theme literal.
    plot(new Map([["c", { colorRole: "muted" }]]));

    expect(seriesOf("c").lineStyle.color).toBe("#a96608");
    expect(seriesOf("c").itemStyle.color).toBe("#a96608");
  });

  it("mutes index 0 and accents a later trace: exactly one accent, on the hinted trace", () => {
    // The sanctioned emphasis composition (C1 ruling): muting index 0 releases
    // its claim, so the accent hint on trace c wins.
    stubMutedToken("#777777");
    plot(new Map([["a", { colorRole: "muted" }], ["c", { colorRole: "accent" }]]));

    expect(seriesOf("a").lineStyle.color).toBe("#777777");
    expect(seriesOf("b").lineStyle.color).toBe("#a96608");
    expect(seriesOf("c").lineStyle.color).toBe("#0b7181");
  });

  it("lets only the earliest accent hint win when index 0 is muted", () => {
    stubMutedToken("#777777");
    plot(
      new Map([
        ["a", { colorRole: "muted" }],
        ["b", { colorRole: "accent" }],
        ["c", { colorRole: "accent" }],
      ]),
    );

    expect(seriesOf("b").lineStyle.color).toBe("#0b7181");
    expect(seriesOf("c").lineStyle.color).toBe("#a96608");
  });

  it("never renders more than one visible accent-coloured series, for any hints map", () => {
    // C1 invariant, table-driven: uniqueness of the emphasis colour holds for
    // every composition, including hinted-vs-hinted collisions.
    const cases: Array<Record<string, TraceHint>> = [
      {},
      { b: { colorRole: "accent" } },
      { b: { colorRole: "accent" }, c: { colorRole: "accent" } },
      { a: { colorRole: "accent" }, b: { colorRole: "accent" }, c: { colorRole: "accent" } },
      { a: { colorRole: "muted" }, b: { colorRole: "accent" } },
      { a: { colorRole: "muted" }, b: { colorRole: "accent" }, c: { colorRole: "accent" } },
      { a: { colorRole: "muted" }, b: { visible: false }, c: { colorRole: "accent" } },
      { b: { colorRole: "muted" }, c: { visible: false } },
    ];
    for (const hints of cases) {
      setOption.mockClear();
      plot(new Map(Object.entries(hints)));
      const accents = series().filter((entry) => entry.lineStyle.color === "#0b7181");
      expect(
        accents.map((entry) => entry.id),
        `hints ${JSON.stringify(hints)}`,
      ).toHaveLength(1);
    }
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
    const visible = screen.getByText("Channel A · V").closest("li");
    expect(visible).not.toHaveAttribute("data-hidden");
  });

  it("discloses hidden channels accessibly in the legend, not only visually", () => {
    // C3: the struck-through styling is visual-only; the legend row's
    // accessible name must carry the hidden state while the trace itself
    // stays excluded from the chart description (design rule 3).
    render(
      <EngineeringPlot
        kind="waveform"
        title="Accessible disclosure"
        x={{ label: "Time", unit: "s" }}
        traces={traces}
        hints={new Map([["b", { visible: false }]])}
      />,
    );

    const hidden = screen.getByText("Channel B · V").closest("li");
    expect(hidden).not.toBeNull();
    expect(hidden).toHaveAttribute("data-hidden", "true");
    expect(hidden).toHaveAccessibleName(/hidden/i);
    const shown = screen.getAllByRole("listitem").filter((item) => item !== hidden);
    expect(shown).toHaveLength(2);
    for (const item of shown) {
      expect(item.textContent).not.toMatch(/hidden/i);
    }
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
    expect(carrier!.markLine!.lineStyle.color).toBe("#a96608");
  });

  it("renders the threshold carrier-independently when every trace is hidden", () => {
    // C2: all-visible:false is schema-legal and validator-clean; the limit
    // line must not vanish with the series — it renders on a carrier series
    // instead of being silently dropped.
    const hints = new Map(traces.map((trace) => [trace.id, { visible: false } as TraceHint]));
    render(
      <EngineeringPlot
        kind="time_series"
        title="All hidden"
        x={{ label: "Time", unit: "s" }}
        traces={traces}
        threshold={{ value: 1.2, label: "Warning limit", severity: "warning" }}
        hints={hints}
      />,
    );

    expect(series()).toHaveLength(1);
    const carrier = series()[0];
    expect(carrier.markLine).toBeDefined();
    expect(carrier.markLine!.lineStyle.color).toBe("#a96608");
    // The plot discloses that all channels are presentation-hidden: the
    // description names no traces, and every legend row discloses its state.
    expect(screen.getByRole("img", { name: "All hidden" }).textContent).toBe("");
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    for (const row of rows) {
      expect(row).toHaveAccessibleName(/hidden/i);
    }
  });
});
