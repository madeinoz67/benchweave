import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReadingTile } from "../components/readings/ReadingTile";
import { staleness } from "../components/readings/staleness";
import { DeviceWorkbench } from "./DeviceWorkbench";
import { psuProofFixture } from "./fixtures";

vi.mock("echarts/core", () => ({
  init: () => ({ setOption: () => undefined, resize: () => undefined, dispose: () => undefined }),
  use: () => undefined,
}));

/** S1-A6 (#243 design record §6): the five composition properties on the PSU
 *  fixture — the limiting tile, the setpoint triad tile, the stale variant,
 *  the fresh control, and the 2.0×-boundary control. Each variant is present
 *  in the fixture definitions (the vacuous-pass control). */
describe("S1-A6 composition proof: reading states, triad, staleness", () => {
  it("(a) the limiting tile: icon + label + border token, no alert role, no glow (fold row 11: the glow claim is the CSS pin, not a class-name ghost)", () => {
    const { container } = render(
      <ReadingTile label="Current" value="1.92" unit="A" freshness="84 ms" quality="Near limit" severity="success" state="limiting" />,
    );
    expect(container.querySelector("[data-bw-reading-state='limiting']")).not.toBeNull();
    expect(screen.getByText("Limiting")).toBeVisible();
    expect(container.querySelector(".bw-reading__state svg, .bw-reading__state [aria-hidden]")).not.toBeNull();
    expect(container.querySelector("[role='alert']")).toBeNull();
    // The no-glow claim is pinned structurally in series-colors.test.ts (the
    // limiting CSS block contains no box-shadow); a class-name glob here could
    // only ever pass vacuously.
  });

  it("(a-composed, fold row 6) limiting + warning: BOTH render — the state takes the border, the severity keeps its glow rights", () => {
    const { container } = render(
      <ReadingTile label="Current" value="1.92" unit="A" freshness="84 ms" quality="Near limit" severity="warning" state="limiting" />,
    );
    const tile = container.querySelector(".bw-reading");
    expect(tile!.getAttribute("data-severity")).toBe("warning");
    expect(tile!.getAttribute("data-bw-reading-state")).toBe("limiting");
    expect(screen.getByText("Limiting")).toBeVisible();
    expect(container.querySelector(".bw-reading__severity")!.textContent).toContain("Warning");
  });

  it("(a-announce, fold row 3) the limiting state mounts a status live region; absent without the state", () => {
    const { container } = render(
      <ReadingTile label="Current" value="1.92" unit="A" freshness="84 ms" quality="Near limit" severity="success" state="limiting" />,
    );
    const status = container.querySelector('[role="status"]');
    expect(status).not.toBeNull();
    expect(status!.textContent).toContain("Limiting");
    const plain = render(<ReadingTile label="Current" value="1.92" unit="A" freshness="84 ms" quality="Verified" severity="success" />);
    expect(plain.container.querySelector('[role="status"]')).toBeNull();
  });

  it("(b-laundering, fold row 7) the fixture set (12.5) differs from the staged value (13.0) — a set-from-staged mutant renders differently", () => {
    // Discriminating witness: the composition renders staged 13.0 in the
    // input while the tile's set text reads 12.5. A renderer that derives
    // the set value from the staged input renders "Set 13.0 V" and this reds.
    const { container } = render(
      <ReadingTile label="Voltage" value="12.04" unit="V" freshness="120 ms" quality="Verified" severity="success" set={{ value: "12.5", unit: "V" }} />,
    );
    expect(container.querySelector(".bw-reading__set")!.textContent).toBe("Set 12.5 V");
    const workbench = render(<DeviceWorkbench fixture={{ ...psuProofFixture, stagedVoltage: 13.0 }} />);
    const input = workbench.container.querySelector("input[type='number']") as HTMLInputElement;
    expect(Number(input.value)).toBe(13.0);
    // The set evidence on the tile still reads the gateway-observed 12.5.
    expect(workbench.container.querySelector(".bw-reading__set")!.textContent).toBe("Set 12.5 V");
  });

  it("(b) the setpoint tile: measured primary + Set 12.5 V adjacent + staged value ONLY in the input", () => {
    const { container } = render(
      <ReadingTile label="Voltage" value="12.04" unit="V" freshness="120 ms" quality="Verified" severity="success" set={{ value: "12.5", unit: "V" }} />,
    );
    const setLine = container.querySelector(".bw-reading__set");
    expect(setLine).not.toBeNull();
    expect(setLine!.textContent).toBe("Set 12.5 V");
    // The staged value lives ONLY in the staging input: the workbench's
    // numeric input carries the Staged labelling (§E.3's staged row), and no
    // tile in the composition carries a staged marker.
    const workbench = render(<DeviceWorkbench fixture={psuProofFixture} />);
    const input = workbench.container.querySelector(".bw-numeric__help");
    expect(input!.textContent).toContain("Staged value; use Apply to request the change");
    for (const tile of workbench.container.querySelectorAll(".bw-reading")) {
      expect(tile.textContent, "no tile carries a staged marker").not.toMatch(/staged/i);
    }
  });

  it("(c) the stale variant: dimmed + stale marker + data-bw-stale", () => {
    const { container } = render(
      <ReadingTile label="Voltage" value="12.04" unit="V" freshness="301 ms" quality="Verified" severity="success" stale />,
    );
    const tile = container.querySelector(".bw-reading");
    expect(tile!.getAttribute("data-bw-stale")).toBe("true");
    expect(container.querySelector(".bw-reading__quality")!.textContent).toContain("stale");
  });

  it("(d) the fresh control: unmarked", () => {
    const { container } = render(
      <ReadingTile label="Voltage" value="12.04" unit="V" freshness="120 ms" quality="Verified" severity="success" />,
    );
    expect(container.querySelector("[data-bw-stale]")).toBeNull();
    expect(container.querySelector(".bw-reading__quality")!.textContent).not.toContain("stale");
  });

  it("(e-folded) the equality-boundary control: freshness == max_age is NOT stale (ST-2 strict 1×)", () => {
    // Folded semantics: max_age 150 ms (the polled read-acceptance window);
    // freshness exactly at the window is inside — one ms more is stale.
    const verdict = staleness(150, 150);
    expect(verdict).toBe("fresh");
    expect(staleness(151, 150)).toBe("stale");
    const { container } = render(
      <ReadingTile label="Voltage" value="12.04" unit="V" freshness="150 ms" quality="Verified" severity="success" stale={verdict === "stale"} />,
    );
    expect(container.querySelector("[data-bw-stale]")).toBeNull();
    expect(container.querySelector(".bw-reading__quality")!.textContent).not.toContain("stale");
  });

  it("(narrow reading, fold row 8) the device quality string renders verbatim; the stale marker is a SEPARATE element", () => {
    const { container } = render(
      <ReadingTile label="Voltage" value="12.04" unit="V" freshness="301 ms" quality="device-good" severity="success" stale />,
    );
    const qualityLine = container.querySelector(".bw-reading__quality")!;
    // The quality string itself is untouched — never concatenated or edited.
    expect(qualityLine.textContent).toContain("device-good · 301 ms");
    // The marker is its own span (bw-reading__stale-marker), a second channel.
    const marker = qualityLine.querySelector(".bw-reading__stale-marker");
    expect(marker).not.toBeNull();
    expect(marker!.textContent).toContain("stale");
  });

  it("(table, fold row 4) the Channels table row carries the stale marker + attribute + dimming class", () => {
    const staleFixture = {
      ...psuProofFixture,
      readings: psuProofFixture.readings.map((reading, index) => (index === 0 ? { ...reading, stale: true } : reading)),
    };
    const { container } = render(<DeviceWorkbench fixture={staleFixture} />);
    const staleRow = container.querySelector("tr[data-bw-stale='true']");
    expect(staleRow, "the stale row carries the attribute").not.toBeNull();
    expect(staleRow!.className).toContain("bw-table-row--stale");
    expect(staleRow!.textContent).toContain("stale");
    const freshRows = container.querySelectorAll("tr:not([data-bw-stale])");
    for (const row of freshRows) expect(row.textContent).not.toContain("stale");
  });
});

describe("S2-A5 provenance composition proof (DAQ fixture)", () => {
  it("(c) a display-processed trace renders its marker AND its source remains present in the same plot", async () => {
    const { daqProofFixture } = await import("./fixtures");
    const processed = daqProofFixture.plotProvenance!.processed;
    expect(processed.kind).toBe("display-processed");
    const source = daqProofFixture.traces.find((t) => t.id === processed.sourceId);
    expect(source, "the source trace is still declared in the same plot").toBeDefined();
    // The marker vocabulary never crosses kinds.
    expect(processed.detail).toContain("median");
    expect(processed.detail).not.toContain("averaging");
  });

  it("(e) a derived trace's displayed precision never exceeds its source's", async () => {
    const { daqProofFixture } = await import("./fixtures");
    const derived = daqProofFixture.plotProvenance!.derived;
    expect(derived.kind).toBe("derived");
    // The derivation expression is disclosed and the uncertainty-unknown
    // marker is part of the required text (checked in the plots pins); here
    // the composition property: the derived trace exists alongside measured
    // sources of equal-or-greater precision (values at one decimal).
    const power = daqProofFixture.traces.find((t) => t.id === derived.id);
    expect(power).toBeDefined();
    for (const [x, y] of power!.values) {
      const decimals = String(y).split(".")[1]?.length ?? 0;
      expect(decimals, "derived display precision <= 1 (its sources' precision)").toBeLessThanOrEqual(1);
      void x;
    }
  });
});
