import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  DigitalLanesPlot,
  type Lane,
  type LaneGroup,
} from "./DigitalLanesPlot";
import type { LaneState } from "./lane-reduction";

const AXIS = { start: 0, step: 1e-6 };

function states(...runs: [LaneState, number][]): LaneState[] {
  return runs.flatMap(([state, count]) => Array.from({ length: count }, () => state));
}

/** The canonical capture fixture: 1000 samples at 1 MHz covering all four
 * wire states in stable runs (the acquisition line's pre-committed numbers:
 * Acquired 1000 samples · plotted 12 at 1 MHz). */
const capture: Lane[] = [
  {
    id: "ch1",
    label: "CH1",
    axis: AXIS,
    states: states(["0", 300], ["1", 200], ["x", 250], ["z", 250]),
  },
  { id: "ch2", label: "CH2", axis: AXIS, states: states(["1", 1000]) },
  { id: "ch3", label: "CH3", axis: AXIS, states: states(["0", 1000]) },
  { id: "ch4", label: "CH4", axis: AXIS, states: states(["z", 1000]) },
];

/** The design's pinned bus fixture: members [a,b,c] with states [1,0,1] —
 * first declared member is the LSB, so bits 0 and 2 set → 0x5. */
const busLanes: Lane[] = [
  { id: "a", label: "A", axis: AXIS, states: states(["1", 100]) },
  { id: "b", label: "B", axis: AXIS, states: states(["0", 100]) },
  { id: "c", label: "C", axis: AXIS, states: states(["1", 100]) },
];

const busGroup: LaneGroup = {
  id: "bus-a",
  label: "Bus A",
  member_ids: ["a", "b", "c"],
};

const busProps = { title: "Bus", x: { label: "Time", unit: "s" }, lanes: busLanes };

function baseProps() {
  return {
    title: "Logic capture",
    x: { label: "Time", unit: "s" },
    lanes: capture,
  };
}

describe("DigitalLanesPlot real rendering (§E.4, A2.1)", () => {
  it("renders one lane row per declared channel with every label present", () => {
    const { container } = render(<DigitalLanesPlot {...baseProps()} columns={12} />);
    const rows = container.querySelectorAll("[data-bw-lane]");
    expect(rows).toHaveLength(4);
    for (const lane of capture) {
      expect(container.textContent).toContain(lane.label);
    }
    rows.forEach((row) => expect(row.getAttribute("data-bw-lane-kind")).toBe("channel"));
  });

  it("renders the four states as STRUCTURALLY distinct geometry, not colour variants", () => {
    const { container } = render(<DigitalLanesPlot {...baseProps()} columns={12} />);
    // 0 and 1 are rects in opposite band halves (state on the attribute).
    const low = container.querySelector('rect[data-bw-state="0"]');
    const high = container.querySelector('rect[data-bw-state="1"]');
    expect(low, "state 0 draws a rect").toBeTruthy();
    expect(high, "state 1 draws a rect").toBeTruthy();
    // x is a PATTERN-filled rect; z is a LINE at mid-band — distinct element
    // kinds, assertable without any colour.
    const unknown = container.querySelector('rect[data-bw-state="x"]');
    const float = container.querySelector('line[data-bw-state="z"]');
    expect(unknown, "state x draws a pattern-filled rect").toBeTruthy();
    expect(unknown!.getAttribute("fill")).toContain("url(#");
    expect(float, "state z draws a mid-level line").toBeTruthy();
    expect(float!.tagName.toLowerCase()).toBe("line");
  });

  it("renders a group's bus value in hex with the pinned LSB order ([1,0,1] → 0x5)", () => {
    // ch2=1 (first declared = bit 0), ch3=0 (bit 1), ch4=1 (bit 2) → 0b101.
    const { container } = render(<DigitalLanesPlot {...busProps} columns={4} groups={[busGroup]} />);
    const groupRow = container.querySelector('[data-bw-lane-kind="group"]');
    expect(groupRow, "the bus lane renders").toBeTruthy();
    expect(groupRow!.textContent).toContain("0x5");
  });

  it("discriminates the LSB order on an ASYMMETRIC trio ([1,1,0] → 0x3, not the MSB mirror 0x6)", () => {
    // The design's [1,0,1] fixture is palindromic — it pins the VALUE but
    // cannot distinguish LSB-first from MSB-first. This trio can: first
    // declared member is the LSB, so bits 0 and 1 set → 0x3.
    const asymmetric: Lane[] = [
      { id: "a", label: "A", axis: AXIS, states: states(["1", 100]) },
      { id: "b", label: "B", axis: AXIS, states: states(["1", 100]) },
      { id: "c", label: "C", axis: AXIS, states: states(["0", 100]) },
    ];
    const { container } = render(
      <DigitalLanesPlot
        title="Bus"
        x={{ label: "Time", unit: "s" }}
        lanes={asymmetric}
        columns={4}
        groups={[{ id: "bus-b", label: "Bus B", member_ids: ["a", "b", "c"] }]}
      />,
    );
    const row = container.querySelector('[data-bw-lane-kind="group"]')!;
    expect(row.textContent).toContain("0x3");
    expect(row.textContent).not.toContain("0x6");
  });

  it("renders the group in decimal when the radix opts in", () => {
    const { container } = render(
      <DigitalLanesPlot {...busProps} columns={4} groups={[{ ...busGroup, radix: "decimal" as const }]} />,
    );
    expect(container.querySelector('[data-bw-lane-kind="group"]')!.textContent).toContain("5");
  });

  it("renders the trigger marker ONLY from a non-null trigger time", () => {
    const withTrigger = render(<DigitalLanesPlot {...baseProps()} columns={4} triggerTime={5e-6} />);
    expect(withTrigger.container.querySelector("[data-bw-trigger]")).toBeTruthy();
    expect(withTrigger.container.textContent).toContain("trigger");
    const without = render(<DigitalLanesPlot {...baseProps()} columns={4} triggerTime={null} />);
    expect(without.container.querySelector("[data-bw-trigger]")).toBeNull();
  });

  it("renders cursors with the exact Δt arithmetic (samples 3 and 10 at 1 µs step → Δt = 7 µs)", () => {
    const { container } = render(
      <DigitalLanesPlot {...baseProps()} columns={4} cursors={[{ sample: 3 }, { sample: 10 }]} />,
    );
    expect(container.querySelectorAll("[data-bw-cursor]")).toHaveLength(2);
    expect(container.textContent).toContain("Δt = 7 µs");
  });

  it("renders Δt in the view's axis mode — sample-index mode reads in samples, no double unit (fold F2)", () => {
    const { container } = render(
      <DigitalLanesPlot
        title="Indexed"
        x={{ label: "Sample index", unit: "samples" }}
        lanes={capture}
        columns={4}
        cursors={[{ sample: 3 }, { sample: 10 }]}
      />,
    );
    expect(container.textContent).toContain("Δt = 7 samples");
    expect(container.textContent).not.toContain("µs");
  });

  it("renders the §E.2.5 acquisition line outside the canvas with the pre-committed numbers", () => {
    const { container } = render(<DigitalLanesPlot {...baseProps()} columns={12} />);
    const line = container.querySelector(".bw-plot__acquisition");
    expect(line).toBeTruthy();
    expect(container.querySelector(".bw-lanes__canvas")!.contains(line!)).toBe(false);
    expect(line!.textContent).toBe("Acquired 1000 samples · plotted 12 at 1 MHz");
  });

  it("renders a hidden lane COLLAPSED with its label retained and the hidden disclosure", () => {
    const { container } = render(
      <DigitalLanesPlot
        {...baseProps()}
        columns={4}
        hints={new Map([["ch2", { visible: false }]])}
      />,
    );
    const rows = container.querySelectorAll("[data-bw-lane]");
    expect(rows, "all four lanes still render").toHaveLength(4);
    const hiddenRow = container.querySelector("[data-hidden]");
    expect(hiddenRow).toBeTruthy();
    expect(hiddenRow!.getAttribute("aria-label")).toBe("CH2 (hidden by presentation preference)");
    expect(hiddenRow!.textContent).toContain("CH2");
    expect(container.textContent).toContain("hidden");
  });

  it("hatches a bus cell whose member CHANGED mid-column (fold F1: no fabricated stable value)", () => {
    // One member, 260x1 / 260x0 / 260x1, columns=4 → boundaries 195/390/585:
    // the transitions at 260 and 520 are INTERIOR to columns [195,390) and
    // [390,585) — those bus cells must hatch; the stable cells show 0x1.
    const member: Lane = {
      id: "m",
      label: "M",
      axis: AXIS,
      states: states(["1", 260], ["0", 260], ["1", 260]),
    };
    const { container } = render(
      <DigitalLanesPlot
        title="Bus transition"
        x={{ label: "Time", unit: "s" }}
        lanes={[member]}
        columns={4}
        groups={[{ id: "bus-t", label: "Bus T", member_ids: ["m"] }]}
      />,
    );
    const groupRow = container.querySelector('[data-bw-lane-kind="group"]')!;
    const cells = groupRow.querySelectorAll("[data-bw-column], .bw-lanes__group");
    // The bus row's own geometry: 4 cells — hatched carry data-bw-state="x".
    const hatched = groupRow.querySelectorAll('rect[data-bw-state="x"]');
    expect(hatched.length, "the two transition columns hatch").toBe(2);
    expect(groupRow.textContent).not.toContain("0x0");
    expect(groupRow.textContent).toContain("0x1");
  });

  it("hatches EVERY bus cell over a noisy member (fold F1: multi-edge member)", () => {
    const noisy: Lane = {
      id: "n",
      label: "N",
      axis: AXIS,
      states: states(...Array.from({ length: 257 }, (_, i): [LaneState, number] => [i % 2 === 0 ? "0" : "1", 1])),
    };
    const steady: Lane = { id: "s", label: "S", axis: AXIS, states: states(["1", 100]) };
    const { container } = render(
      <DigitalLanesPlot
        title="Noisy bus"
        x={{ label: "Time", unit: "s" }}
        lanes={[noisy, steady]}
        columns={8}
        groups={[{ id: "bus-n", label: "Bus N", member_ids: ["n", "s"] }]}
      />,
    );
    const groupRow = container.querySelector('[data-bw-lane-kind="group"]')!;
    const busCells = groupRow.querySelectorAll("g.bw-lanes__group, rect[data-bw-state]");
    // The noisy member makes every column unstable: the whole bus hatches.
    expect(groupRow.querySelectorAll('rect[data-bw-state="x"]').length).toBe(8);
    expect(busCells.length).toBeGreaterThan(0);
  });

  it("consumes default_collapsed: the declared members render collapsed into the bus (fold F4)", () => {
    const { container } = render(
      <DigitalLanesPlot
        {...busProps}
        columns={4}
        groups={[{ ...busGroup, default_collapsed: true }]}
      />,
    );
    // The bus lane renders beside the members, and every declared member
    // renders with the hidden-lane treatment (collapsed band, label retained).
    expect(container.querySelector('[data-bw-lane-kind="group"]')).toBeTruthy();
    const hiddenRows = container.querySelectorAll("[data-hidden]");
    expect(hiddenRows).toHaveLength(3);
    hiddenRows.forEach((row) => expect(row.getAttribute("data-bw-lane-kind")).toBe("channel"));
    expect(container.textContent).toContain("A");
  });

  it("pins DECLARATION order with non-sorted ids (fold F5: a sort-by-id renderer reds)", () => {
    // The other fixtures are accidentally id-sorted, so declared order was
    // unpinned — this trio is deliberately unordered.
    const unordered: Lane[] = [
      { id: "ch3", label: "C3", axis: AXIS, states: states(["1", 60]) },
      { id: "ch1", label: "C1", axis: AXIS, states: states(["0", 60]) },
      { id: "ch2", label: "C2", axis: AXIS, states: states(["z", 60]) },
    ];
    const { container } = render(
      <DigitalLanesPlot title="Unordered" x={{ label: "Time", unit: "s" }} lanes={unordered} columns={4} />,
    );
    const rows = container.querySelectorAll("[data-bw-lane]");
    expect(rows).toHaveLength(3);
    expect(rows[0]!.getAttribute("data-bw-lane")).toBe("0");
    expect(rows[0]!.textContent).toContain("C3");
    expect(rows[1]!.getAttribute("data-bw-lane")).toBe("1");
    expect(rows[1]!.textContent).toContain("C1");
    expect(rows[2]!.getAttribute("data-bw-lane")).toBe("2");
    expect(rows[2]!.textContent).toContain("C2");
  });

  it("carries the glitch mark on multi-transition columns", () => {
    // 0101 at sub-column spacing: every column covers more than one transition.
    const dense: Lane[] = [
      { id: "ch1", label: "CH1", axis: AXIS, states: states(...Array.from({ length: 257 }, (_, i): [LaneState, number] => [i % 2 === 0 ? "0" : "1", 1])) },
    ];
    const { container } = render(<DigitalLanesPlot lanes={dense} title="Dense" x={{ label: "Time", unit: "s" }} columns={8} />);
    const glitches = container.querySelectorAll("[data-bw-glitch]");
    expect(glitches.length).toBeGreaterThan(0);
    glitches.forEach((mark) => expect(mark.classList.contains("bw-lanes__glitch")).toBe(true));
  });
});
