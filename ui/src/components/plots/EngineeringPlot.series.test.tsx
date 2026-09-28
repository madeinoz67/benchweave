import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// S3-A4/S3-A5 (design record §6, #242 slice 3): the set-derived series
// assignment — slot grammar, hide/reorder invariance, the 16-ceiling
// uniqueness, the legend slot disclosure, and the DAQ example-fixture proof.
// jsdom resolves no custom properties, so the component resolves the
// documented LIGHT-palette fallback literals (the same values themes.css
// pins, L3-checked by contract-coverage).
const setOption = vi.fn();
vi.mock("echarts/core", () => ({
  init: () => ({ setOption, resize: () => undefined, dispose: () => undefined }),
  use: () => undefined,
}));

import { EngineeringPlot, type PlotTrace } from "./EngineeringPlot";

const LIGHT_SERIES = ["#eb3b70", "#0c4298", "#9a7884", "#3b4473", "#648a68", "#6a5d85", "#772f31", "#837187"];

interface SeriesRow {
  id: string;
  symbol: string;
  lineStyle: { color: string; type: string };
}

function seriesRows(): SeriesRow[] {
  expect(setOption).toHaveBeenCalled();
  return setOption.mock.calls[0][0].series as SeriesRow[];
}

function renderPlot(traces: readonly PlotTrace[], hints?: Map<string, { colorRole?: "accent" | "muted"; visible?: boolean }>) {
  return render(
    <EngineeringPlot
      kind="time_series"
      title="Assignment"
      x={{ label: "Time", unit: "s" }}
      traces={traces}
      hints={hints}
    />,
  );
}

const trace = (id: string): PlotTrace => ({ id, label: id, unit: "V", values: [[0, 0], [1, 1]] });

beforeEach(() => {
  setOption.mockClear();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("S3-A4: set-derived slot assignment (§E.2.1)", () => {
  it("assigns slots by bytewise-sorted declared id set, not display order", () => {
    // Declared in deliberately unsorted display order: the sorted set
    // {aa, b, z} gives aa→slot 0, b→slot 1, z→slot 2 — the rendered style
    // follows the SORT, not the position in the list.
    renderPlot([trace("z"), trace("b"), trace("aa")]);
    const byId = new Map(seriesRows().map((row) => [row.id, row]));
    expect(byId.get("aa")).toMatchObject({ symbol: "circle", lineStyle: { color: LIGHT_SERIES[0], type: "solid" } });
    expect(byId.get("b")).toMatchObject({ symbol: "rect", lineStyle: { color: LIGHT_SERIES[1], type: "solid" } });
    expect(byId.get("z")).toMatchObject({ symbol: "triangle", lineStyle: { color: LIGHT_SERIES[2], type: "solid" } });
  });

  it("splits dash-1/dash-2 at slot 8 and wraps the colour and symbol at 8", () => {
    const ids = ["i01", "i02", "i03", "i04", "i05", "i06", "i07", "i08", "i09", "i10", "i11", "i12", "i13", "i14", "i15", "i16"];
    renderPlot(ids.map(trace));
    const rows = new Map(seriesRows().map((row) => [row.id, row]));
    expect(rows.get("i01")).toMatchObject({ symbol: "circle", lineStyle: { color: LIGHT_SERIES[0]!, type: "solid" } });
    // Slot 7 is the saltire — the 8th shape is a custom SVG path (the chart
    // library lacks the shape), so the payload carries "path://…".
    expect(rows.get("i08")!.symbol).toMatch(/^path:\/\//);
    expect(rows.get("i08")).toMatchObject({ lineStyle: { color: LIGHT_SERIES[7]!, type: "solid" } });
    // Slot 8 (the 9th id) wraps to series-1 with dash-2.
    expect(rows.get("i09")).toMatchObject({ symbol: "circle", lineStyle: { color: LIGHT_SERIES[0]!, type: "dashed" } });
    expect(rows.get("i16")!.symbol).toMatch(/^path:\/\//);
    expect(rows.get("i16")).toMatchObject({ lineStyle: { color: LIGHT_SERIES[7]!, type: "dashed" } });
  });

  it("16 declared ids produce 16 distinct (colour, dash) and 16 distinct (symbol, dash) pairs — the uniqueness ceiling", () => {
    // The ceiling is CITED from plugin-ui $defs/plot y.maxItems: 16 — the
    // wire cannot carry a 17th declared channel; the component's behaviour
    // beyond the ceiling is documented below (a 17th id would collide with
    // slot 8's pair), and is unreachable through any conforming document.
    const ids = Array.from({ length: 16 }, (_, i) => `id${String(i + 1).padStart(2, "0")}`);
    renderPlot(ids.map(trace));
    const rows = seriesRows();
    const styleOf = (row: SeriesRow) => `${row.lineStyle.color}|${row.lineStyle.type}`;
    const symbolOf = (row: SeriesRow) => `${row.symbol}|${row.lineStyle.type}`;
    expect(new Set(rows.map(styleOf)).size).toBe(16);
    expect(new Set(rows.map(symbolOf)).size).toBe(16);
  });

  it("a 17th declared id would collide with slot 8's pair (over-ceiling is the wire schema's refusal, not the renderer's)", () => {
    // Documented behaviour: the formula (i mod 8, i < 8) maps i=16 onto the
    // same (colour, dash) as i=8. Unreachable through a conforming document
    // (plugin-ui caps declared channels at 16); pinned so the ceiling is
    // stated as the uniqueness BOUND, not an accident.
    const ids = Array.from({ length: 17 }, (_, i) => `id${String(i + 1).padStart(2, "0")}`);
    renderPlot(ids.map(trace));
    const rows = seriesRows();
    const styleOf = (row: SeriesRow) => `${row.lineStyle.color}|${row.lineStyle.type}`;
    expect(new Set(rows.map(styleOf)).size).toBe(16);
  });

  it("hiding a channel never restyles its siblings (invariance)", () => {
    const traces = [trace("a"), trace("b"), trace("c"), trace("d")];
    const { unmount } = renderPlot(traces);
    const control = new Map(seriesRows().map((row) => [row.id, row]));
    unmount();
    setOption.mockClear();
    renderPlot(traces, new Map([["b", { visible: false }], ["c", { visible: false }]]));
    const survived = seriesRows();
    // a and d keep byte-identical style objects to the no-hints control.
    for (const id of ["a", "d"]) {
      const row = survived.find((entry) => entry.id === id);
      expect(row).toBeDefined();
      expect(row).toEqual(control.get(id));
    }
  });

  it("reordering the declared list restyles nothing (invariance)", () => {
    const traces = [trace("a"), trace("b"), trace("c")];
    const { unmount } = renderPlot(traces);
    const control = new Map(seriesRows().map((row) => [row.id, row]));
    unmount();
    setOption.mockClear();
    renderPlot([trace("c"), trace("a"), trace("b")]);
    for (const id of ["a", "b", "c"]) {
      expect(seriesRows().find((entry) => entry.id === id)).toEqual(control.get(id));
    }
  });

  it("discloses each legend row's series slot (data-bw-series-slot)", () => {
    renderPlot([trace("z"), trace("b"), trace("aa")]);
    const slotOf = (label: string) => screen.getByText(label).closest("li")!.getAttribute("data-bw-series-slot");
    expect(slotOf("aa · V")).toBe("1");
    expect(slotOf("b · V")).toBe("2");
    expect(slotOf("z · V")).toBe("3");
    // Slot numbers wrap at 8 (the 9th id discloses slot 1 again — its series
    // token), while its dash distinguishes it.
    const ids = Array.from({ length: 9 }, (_, i) => `id${String(i + 1).padStart(2, "0")}`);
    const { unmount } = renderPlot(ids.map(trace));
    const ninth = screen.getByText("id09 · V").closest("li")!;
    expect(ninth.getAttribute("data-bw-series-slot")).toBe("1");
    expect(ninth.getAttribute("data-line")).toBe("dashed");
    unmount();
  });
});

describe("S3-A5: severity-hue discipline on the DAQ example fixture", () => {
  it("6 channels draw 6 distinct series tokens, zero invented colours, and the threshold keeps its severity colour", async () => {
    const { daqProofFixture } = await import("../../compositions/fixtures");
    // The DAQ page's own six declared channels (the example fixture this
    // proof is about — S3-A2's vacuous-pass control enumerated in the
    // fixture), rendered with a threshold.
    expect(daqProofFixture.traces).toHaveLength(6);
    render(
      <EngineeringPlot
        kind="time_series"
        title="DAQ channels"
        x={{ label: "Time", unit: "s" }}
        traces={daqProofFixture.traces}
        threshold={{ value: 5.5, label: "Over-range limit", severity: "warning" }}
      />,
    );
    const rows = seriesRows();
    const colours = rows.map((row) => row.lineStyle.color);
    // Six distinct series tokens — all from the pinned palette, none invented.
    expect(new Set(colours).size).toBe(6);
    for (const colour of colours) {
      expect(LIGHT_SERIES).toContain(colour);
    }
    // Severity-hue discipline: a severity-neutral series NEVER resolves to a
    // severity hue (advisory/warning/critical/trip/success light values).
    const severityHues = ["#2476b8", "#a96608", "#b63830", "#a92858", "#177158"];
    for (const colour of colours) {
      expect(severityHues).not.toContain(colour);
    }
    // The threshold mark line KEEPS its severity colour.
    const carrier = rows.find((row) => (row as { markLine?: { lineStyle: { color: string } } }).markLine !== undefined);
    expect(carrier).toBeDefined();
    expect((carrier as unknown as { markLine: { lineStyle: { color: string } } }).markLine.lineStyle.color).toBe("#a96608");
  });
});
