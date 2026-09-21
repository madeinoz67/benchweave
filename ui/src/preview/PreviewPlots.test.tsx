import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The mock captures every setOption payload so trace styling is asserted on
// the real option object echarts would receive, never on rendered pixels.
// jsdom's getComputedStyle returns no custom properties, so pass-1 fallback
// literals apply unless a token is explicitly stubbed.
const setOption = vi.fn();
vi.mock("echarts/core", () => ({
  init: () => ({ setOption, resize: () => undefined, dispose: () => undefined }),
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
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("plotTraces (pure join)", () => {
  it("joins one single-point trace per channel from the scenario snapshot", () => {
    const join = plotTraces(view([channel(), channel({ variable_id: "ripple", label: "ripple" })]), scenario);
    expect(join.feedable).toBe(true);
    expect(join.traces).toEqual([
      { id: "value", label: "Value", unit: "V", values: [[0, 12.5]] },
      { id: "ripple", label: "Ripple", unit: "V", values: [[0, 12.5]] },
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
      screen.getByText("Preview scenarios carry one simulated value per binding — not observation history."),
    ).toBeVisible();
  });

  it("renders figure structure with a visible no-data row for unfeedable plots", () => {
    // C2's no-laundering principle applied to whole plots: "no data rendered"
    // must not be laundered into "no plot declared".
    const waveform = view([channel()]) as PlotView & { kind: "waveform" };
    const detached: PreviewScenario = { ...scenario, observations: [] };
    const { container } = render(<PreviewPlots views={[waveform]} scenario={detached} />);
    expect(container.querySelectorAll("figure.bw-plot")).toHaveLength(1);
    expect(screen.getByText("Value · V")).toBeVisible();
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
});
