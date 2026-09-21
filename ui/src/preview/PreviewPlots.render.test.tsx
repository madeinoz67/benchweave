import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// No echarts mock in this file: metric B's bar is the real renderer (FC1) —
// an option payload recorded by a mock proves nothing about figures drawn.
import { PreviewPlots } from "./PreviewPlots";
import type { PlotView, PreviewScenario } from "./api";

const view: PlotView = {
  page_id: "readings",
  kind: "time_series",
  binding_id: "voltage",
  title: "Readings",
  x: { label: "time", unit: "s" },
  channels: [{ variable_id: "value", label: "value", unit: "V", color_role: "muted" }],
};

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

/** jsdom resolves no custom properties; supply the muted token so the muted
 *  hint resolves to a literal distinct from every pass-1 default (C4). */
function stubMutedToken(value: string) {
  vi.stubGlobal("getComputedStyle", () => ({
    getPropertyValue: (name: string) => (name === "--bw-text-muted" ? value : ""),
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PreviewPlots real rendering (metric B)", () => {
  it("renders exactly one real figure per declared plot view, hint-coloured", () => {
    stubMutedToken("#777777");
    const { container } = render(<PreviewPlots views={[view]} scenario={scenario} />);

    expect(container.querySelectorAll("figure.bw-plot")).toHaveLength(1);
    const svg = container.querySelector(".bw-plot__canvas svg");
    expect(svg, "echarts rendered an SVG into the canvas").toBeTruthy();
    // The legend row is the disclosure key (the projected wire label passes
    // through verbatim); the muted token must reach the drawn pixels, not
    // just the option payload.
    expect(screen.getByText("value · V")).toBeVisible();
    // R4: the muted colour must be pinned at the TRACE, not just anywhere in
    // the SVG — axis-label text shares the token colour, so a bare
    // innerHTML-contains check is satisfiable by non-trace pixels. A line
    // series path carries its resolved colour as the stroke attribute.
    expect(container.querySelector('path[stroke="#777777"]')).not.toBeNull();
  });

  it("renders zero figures when the document declares no plots (the mechanism is the only path)", () => {
    const { container } = render(<PreviewPlots views={[]} scenario={scenario} />);
    expect(container.querySelectorAll("figure.bw-plot")).toHaveLength(0);
  });

  it("renders the snapshot disclosure and the no-data row through real echarts (R3)", () => {
    // PT-5's FC1-shaped gap: the feature's distinguishing claims — the
    // standing disclosure line and the no-data row for an unfeedable
    // declared plot — leave mock-only territory and are asserted on a real
    // rendered figure (structure, axes, legend all drawn; no series data).
    const waveform: PlotView = {
      page_id: "waveform",
      kind: "waveform",
      binding_id: "capture",
      title: "Waveform",
      x: { label: "time", unit: "s" },
      channels: [{ variable_id: "signal", label: "signal", unit: "V" }],
    };
    const detached: PreviewScenario = { ...scenario, observations: [] };
    const { container } = render(<PreviewPlots views={[waveform]} scenario={detached} />);

    expect(container.querySelectorAll("figure.bw-plot")).toHaveLength(1);
    expect(container.querySelector(".bw-plot__canvas svg")).toBeTruthy();
    expect(
      screen.getByText("Preview scenarios carry one simulated value per observed target — not observation history."),
    ).toBeVisible();
    expect(screen.getByText("No preview data for this scenario")).toBeVisible();
    expect(screen.getByText("signal · V")).toBeVisible();
  });
});
