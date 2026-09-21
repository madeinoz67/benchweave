import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The mock captures every setOption payload so trace styling is asserted on
// the real option object echarts would receive, never on rendered pixels.
// jsdom's getComputedStyle returns no custom properties, so pass-1 fallback
// literals apply unless a token is explicitly stubbed.
const setOption = vi.fn();
const initChart = vi.fn(() => ({ setOption, resize: () => undefined, dispose: () => undefined }));
vi.mock("echarts/core", () => ({
  init: () => initChart(),
  use: () => undefined,
}));

import { plotTraces, PreviewPlots } from "./PreviewPlots";
import type { PlotChannelView, PlotView, PreviewScenario } from "./api";

const channel = (overrides: Partial<PlotChannelView> = {}): PlotChannelView => ({
  variable_id: "value",
  label: "value",
  unit: "V",
  ...overrides,
});

const view = (channels: readonly PlotChannelView[]): PlotView => ({
  page_id: "readings",
  kind: "time_series",
  binding_id: "voltage",
  title: "Readings",
  x: { label: "time", unit: "s" },
  channels,
});

const scenario: PreviewScenario = {
  id: "normal",
  title: "Normal",
  description: "Nominal simulated state",
  timestamp_strategy: "relative",
  observations: [
    {
      binding_id: "voltage",
      value: 12.5,
      unit: "V",
      quality: "simulated",
      freshness_ms: 0,
      provenance: "SDK generated baseline",
    },
  ],
  permissions: ["observer"],
  lease_state: "held",
  approval_state: "not_required",
  unavailable_panels: [],
  expected_severity: "neutral",
  request_outcomes: [],
  baseline: true,
};

function stubMutedToken(value: string) {
  vi.stubGlobal("getComputedStyle", () => ({
    getPropertyValue: (name: string) => (name === "--bw-text-muted" ? value : ""),
  }));
}

beforeEach(() => {
  setOption.mockClear();
  initChart.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("plotTraces (pure join)", () => {
  it("joins one single-point trace per channel from the scenario snapshot", () => {
    const join = plotTraces(view([channel(), channel({ variable_id: "ripple", label: "ripple" })]), scenario);
    expect(join.feedable).toBe(true);
    expect(join.traces).toEqual([
      { id: "value", label: "value", unit: "V", values: [[0, 12.5]] },
      { id: "ripple", label: "ripple", unit: "V", values: [[0, 12.5]] },
    ]);
  });

  it("carries hint fields onto the hints map and omits the map when no channel is hinted", () => {
    const hinted = plotTraces(view([channel({ color_role: "muted" }), channel({ variable_id: "ripple", visible: false })]), scenario);
    expect(hinted.hints).toEqual(
      new Map([
        ["value", { colorRole: "muted" }],
        ["ripple", { visible: false }],
      ]),
    );
    const unhinted = plotTraces(view([channel()]), scenario);
    expect(unhinted.hints).toBeUndefined();
  });

  it("is not feedable without a finite numeric observation for the binding", () => {
    const disconnected: PreviewScenario = {
      ...scenario,
      observations: [{ ...scenario.observations[0], value: null }],
    };
    const join = plotTraces(view([channel()]), disconnected);
    expect(join.feedable).toBe(false);
    expect(join.traces[0]?.values).toEqual([]);
    const missing = plotTraces(view([channel({ variable_id: "value" })]), {
      ...scenario,
      observations: [],
    });
    expect(missing.feedable).toBe(false);
  });
});

describe("PreviewPlots panel", () => {
  it("renders the standing snapshot disclosure beside every panel", () => {
    render(<PreviewPlots views={[view([channel()])]} scenario={scenario} />);
    expect(
      screen.getByText("Preview scenarios carry one simulated value per observed target — not observation history."),
    ).toBeVisible();
  });

  it("renders figure structure with a visible no-data row for unfeedable plots", () => {
    // C2's no-laundering principle applied to whole plots: "no data rendered"
    // must not be laundered into "no plot declared".
    const waveform = view([channel()]) as PlotView & { kind: "waveform" };
    const detached: PreviewScenario = { ...scenario, observations: [] };
    const { container } = render(<PreviewPlots views={[waveform]} scenario={detached} />);
    expect(container.querySelectorAll("figure.bw-plot")).toHaveLength(1);
    expect(screen.getByText("value · V")).toBeVisible();
    expect(screen.getByText("No preview data for this scenario")).toBeVisible();
    expect(setOption).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("status", { name: /threshold/i })).toBeNull();
  });

  it("never passes a threshold: manifest plots carry none and none is fabricated", () => {
    render(<PreviewPlots views={[view([channel()])]} scenario={scenario} />);
    const payload = setOption.mock.calls[0][0];
    const markLines = payload.series.filter((series: { markLine?: unknown }) => series.markLine !== undefined);
    expect(markLines).toEqual([]);
  });

  it("transports a muted hint to the drawn trace colour (metric C, hinted direction)", () => {
    stubMutedToken("#777777");
    render(<PreviewPlots views={[view([channel({ color_role: "muted" })])]} scenario={scenario} />);
    const series = setOption.mock.calls[0][0].series as Array<{ id: string; lineStyle: { color: string } }>;
    expect(series[0].lineStyle.color).toBe("#777777");
  });

  it("resolves the pass-1 accent when the same channel carries no hint (metric C, unhinted direction)", () => {
    stubMutedToken("#777777");
    render(<PreviewPlots views={[view([channel()])]} scenario={scenario} />);
    const series = setOption.mock.calls[0][0].series as Array<{ id: string; lineStyle: { color: string } }>;
    expect(series[0].lineStyle.color).toBe("#0b7181");
  });

  it("renders nothing when the decoded document carries no plot views", () => {
    const { container } = render(<PreviewPlots views={[]} scenario={scenario} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("does not re-init chart instances on parent re-renders with unchanged data (R2)", () => {
    // Role/theme/receipt changes re-render PreviewApp; the joined traces must
    // keep referential stability so EngineeringPlot's effect (deps include
    // traces) does not dispose and re-init every echarts instance per
    // unrelated state change.
    const views = [view([channel()])];
    const { rerender } = render(<PreviewPlots views={views} scenario={scenario} />);
    expect(initChart).toHaveBeenCalledTimes(1);
    rerender(<PreviewPlots views={views} scenario={scenario} />);
    rerender(<PreviewPlots views={views} scenario={scenario} />);
    expect(initChart).toHaveBeenCalledTimes(1);
    // Data changes still re-render: a different scenario re-inits.
    rerender(<PreviewPlots views={views} scenario={{ ...scenario, id: "trip" }} />);
    expect(initChart).toHaveBeenCalledTimes(2);
  });

  it("uses collision-safe keys for views whose page ids and titles contain ':' (R2)", () => {
    // Manifest ids may contain ':' (the schema id pattern allows it), so
    // `${page_id}:${title}` is separator-collidable: page "a" title "b:c"
    // collides with page "a:b" title "c". React logs a duplicate-key error
    // and drops a sibling.
    const colliding: readonly PlotView[] = [
      { ...view([channel()]), page_id: "a", title: "b:c" },
      { ...view([channel()]), page_id: "a:b", title: "c" },
    ];
    const errors: string[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      errors.push(args.map(String).join(" "));
    });
    try {
      const { container } = render(<PreviewPlots views={colliding} scenario={scenario} />);
      expect(errors.filter((line) => /same key/i.test(line))).toEqual([]);
      expect(container.querySelectorAll("figure.bw-plot")).toHaveLength(2);
    } finally {
      spy.mockRestore();
    }
  });

  it("prefers the projected channel label and falls back to prettifying the id (R2)", () => {
    const join = plotTraces(
      view([
        channel({ label: "Line voltage" }),
        channel({ variable_id: "ripple", label: "" }),
      ]),
      scenario,
    );
    expect(join.traces.map((trace) => trace.label)).toEqual(["Line voltage", "Ripple"]);
  });
});
