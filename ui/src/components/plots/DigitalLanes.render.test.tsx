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
