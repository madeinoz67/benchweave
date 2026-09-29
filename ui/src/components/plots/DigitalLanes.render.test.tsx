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

  it("renders a VISIBLE awaiting-render note for declared decoder lanes (fold P2: never a silent blank)", () => {
    const { container } = render(
      <DigitalLanesPlot
        {...busProps}
        columns={4}
        groups={[busGroup]}
        decoderLanes={[
          { id: "uart-lane", decoder: "UART-REF", source_channel_ids: ["a"], binding_id: "logic" },
        ]}
      />,
    );
    const note = container.querySelector(".bw-lanes__decoder-note");
    expect(note, "the placeholder renders").toBeTruthy();
    expect(note!.getAttribute("role")).toBe("status");
    expect(note!.textContent).toContain("UART-REF");
    expect(note!.textContent).toContain("awaiting decoder rendering");
  });

  it("renders the axis label and unit VISIBLY beneath the canvas (fold P3)", () => {
    const { container } = render(<DigitalLanesPlot {...baseProps()} columns={4} />);
    const axis = container.querySelector(".bw-lanes__axis");
    expect(axis, "the visible axis label renders").toBeTruthy();
    expect(axis!.textContent).toContain("Time");
    expect(axis!.textContent).toContain("s");
    expect(container.querySelector(".bw-lanes__canvas")!.contains(axis!)).toBe(false);
  });

  it("hatches the unknown bus on the PATTERN geometry with NO numeric text in the row (fold P4)", () => {
    // Every member x/z: the bus row carries hatched cells (pattern-filled
    // rects) and NOT ONE numeric bus value.
    const unknown: Lane[] = [
      { id: "u1", label: "U1", axis: AXIS, states: states(["x", 100]) },
      { id: "u2", label: "U2", axis: AXIS, states: states(["z", 100]) },
    ];
    const { container } = render(
      <DigitalLanesPlot
        title="Unknown bus"
        x={{ label: "Time", unit: "s" }}
        lanes={unknown}
        columns={4}
        groups={[{ id: "bus-u", label: "Bus U", member_ids: ["u1", "u2"] }]}
      />,
    );
    const groupRow = container.querySelector('[data-bw-lane-kind="group"]')!;
    const hatched = groupRow.querySelectorAll('rect[data-bw-state="x"]');
    expect(hatched.length).toBe(4);
    hatched.forEach((cell) => expect(cell.getAttribute("fill")).toContain("url(#"));
    expect(groupRow.textContent).not.toContain("0x");
  });

  it("pins the OPPOSITE-half geometry of states 0 and 1 (fold addendum a)", () => {
    const mixed: Lane[] = [
      { id: "m", label: "M", axis: AXIS, states: states(["1", 50], ["0", 50]) },
    ];
    const { container } = render(
      <DigitalLanesPlot title="Halves" x={{ label: "Time", unit: "s" }} lanes={mixed} columns={2} />,
    );
    const high = container.querySelector('rect[data-bw-state="1"]')!;
    const low = container.querySelector('rect[data-bw-state="0"]')!;
    expect(high).toBeTruthy();
    expect(low).toBeTruthy();
    const highY = Number(high.getAttribute("y"));
    const lowY = Number(low.getAttribute("y"));
    const highH = Number(high.getAttribute("height"));
    expect(highY, "state 1 occupies the upper half").toBeLessThan(lowY);
    expect(lowY - highY, "the halves are structurally opposite and equal").toBe(highH);
  });

  it("zero-pads the bus width to the member bit-width in nibbles (addendum b: 2 and 4 nibbles)", () => {
    const five = Array.from({ length: 5 }, (_, i): Lane => ({
      id: `b${i}`,
      label: `B${i}`,
      axis: AXIS,
      states: states(["1", 100]),
    }));
    const thirteen = Array.from({ length: 13 }, (_, i): Lane => ({
      id: `c${i}`,
      label: `C${i}`,
      axis: AXIS,
      states: states(["1", 100]),
    }));
    const fiveBus = render(
      <DigitalLanesPlot
        title="Five"
        x={{ label: "Time", unit: "s" }}
        lanes={five}
        columns={2}
        groups={[{ id: "bus5", member_ids: five.map((lane) => lane.id) }]}
      />,
    );
    expect(fiveBus.container.querySelector('[data-bw-lane-kind="group"]')!.textContent).toContain("0x1f");
    const thirteenBus = render(
      <DigitalLanesPlot
        title="Thirteen"
        x={{ label: "Time", unit: "s" }}
        lanes={thirteen}
        columns={2}
        groups={[{ id: "bus13", member_ids: thirteen.map((lane) => lane.id) }]}
      />,
    );
    expect(thirteenBus.container.querySelector('[data-bw-lane-kind="group"]')!.textContent).toContain("0x1fff");
  });

  it("maps the trigger marker's x position from the trigger time (addendum c)", () => {
    const indexed: Lane[] = [{ id: "t", label: "T", axis: { start: 0, step: 1 }, states: states(["1", 100]) }];
    const { container } = render(
      <DigitalLanesPlot title="Trigger" x={{ label: "Sample index", unit: "samples" }} lanes={indexed} columns={4} triggerTime={50} />,
    );
    const trigger = container.querySelector("[data-bw-trigger] line")!;
    const x = Number(trigger.getAttribute("x1"));
    // 96 + (50/99) * 544 = 370.7474… — the marker sits at its sample.
    expect(x).toBeCloseTo(370.747, 2);
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

describe("decoder-lane rendering (§E.4.6, A3.1 — slice 3)", () => {
  const DECODER_AXIS = { start: 0, step: 1e-6 };
  const SAMPLES = 1200;
  const sourceLane: Lane = {
    id: "ch1",
    label: "CH1",
    axis: DECODER_AXIS,
    states: states(["1", SAMPLES]),
  };
  /** The pre-committed A3.1 fixture: two UART-REF events at [0, 0.0001]
   *  and [0.001, 0.0011] seconds — sample boundaries 0, 100, 1000, 1100. */
  const decoderLane = {
    id: "uart-lane",
    decoder: "UART-REF",
    settings: { baud: 115200, frame: "8N1" },
    source_channel_ids: ["ch1"],
    binding_id: "logic",
    events: [
      { start_s: 0, end_s: 0.0001, payload_hex: "55", status: "ok" },
      { start_s: 0.001, end_s: 0.0011, payload_hex: "AA", status: "ok" },
    ],
  };
  const xAt = (sample: number) => 96 + (sample / (SAMPLES - 1)) * 544;

  function renderDecoder(hints?: ReadonlyMap<string, { visible?: boolean }>) {
    return render(
      <DigitalLanesPlot
        title="Decoded"
        x={{ label: "Time", unit: "s" }}
        lanes={[sourceLane]}
        columns={8}
        decoderLanes={[decoderLane]}
        hints={hints}
      />,
    );
  }

  it("renders annotation spans beneath the source lane at the EXACT sample extents", () => {
    const { container } = renderDecoder();
    const decoderRow = container.querySelector('[data-bw-lane-kind="decoder"]');
    expect(decoderRow, "the decoder row renders").toBeTruthy();
    const sourceRow = container.querySelector('[data-bw-lane-kind="channel"]')!;
    const decoderY = Number(decoderRow!.querySelector("rect, line, text")!.getAttribute("y") ?? decoderRow!.querySelector("[data-bw-span]")!.getAttribute("y"));
    expect(
      Number(sourceRow.querySelector("rect")!.getAttribute("y")) < decoderY,
      "the decoder row sits beneath its source channel",
    ).toBe(true);
    const spans = [...decoderRow!.querySelectorAll("[data-bw-span]")].map(
      (span) => span.querySelector("rect")!,
    );
    expect(spans).toHaveLength(2);
    expect(Number(spans[0]!.getAttribute("x"))).toBeCloseTo(xAt(0), 2);
    expect(Number(spans[0]!.getAttribute("width"))).toBeCloseTo(xAt(100) - xAt(0), 2);
    expect(Number(spans[1]!.getAttribute("x"))).toBeCloseTo(xAt(1000), 2);
    expect(Number(spans[1]!.getAttribute("width"))).toBeCloseTo(xAt(1100) - xAt(1000), 2);
  });

  it("carries the payload text on the span (the wire's hex encoding, verbatim)", () => {
    const { container } = renderDecoder();
    const spans = container.querySelectorAll("[data-bw-span]");
    expect(spans[0]!.textContent).toContain("55");
    expect(spans[1]!.textContent).toContain("AA");
  });

  it("renders the disclosure line naming the decoder and its settings verbatim", () => {
    const { container } = renderDecoder();
    expect(container.textContent).toContain("UART-REF · 115200 8N1");
  });

  it("waits visibly when the source channel is hidden — the span does NOT render, no orphan", () => {
    const { container } = renderDecoder(new Map([["ch1", { visible: false }]]));
    expect(container.querySelectorAll("[data-bw-span]")).toHaveLength(0);
    expect(container.textContent).not.toContain("55");
    expect(container.textContent).not.toContain("AA");
    const waiting = container.querySelector("[data-bw-waiting]");
    expect(waiting, "the waiting disclosure renders").toBeTruthy();
    expect(waiting!.textContent).toContain("waiting");
    expect(waiting!.textContent).toContain("hidden");
  });
});
