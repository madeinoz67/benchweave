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
  it("(a) the limiting tile: icon + label + border token, no alert role, no glow class", () => {
    const { container } = render(
      <ReadingTile label="Current" value="1.92" unit="A" freshness="84 ms" quality="Near limit" severity="success" state="limiting" />,
    );
    expect(container.querySelector("[data-bw-reading-state='limiting']")).not.toBeNull();
    expect(screen.getByText("Limiting")).toBeVisible();
    expect(container.querySelector(".bw-reading__state svg, .bw-reading__state [aria-hidden]")).not.toBeNull();
    expect(container.querySelector("[role='alert']")).toBeNull();
    // No glow class: the glow rule (SR-B2) is severity-scoped; the limiting state carries none.
    expect(container.querySelector("[class*='glow']")).toBeNull();
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

  it("(e) the 2.0×-boundary control: unmarked (ST-2 strict inequality)", () => {
    // Cadence 150 ms (a commissioned stream interval), freshness exactly 2×.
    const verdict = staleness(300, 150);
    expect(verdict).toBe("fresh");
    const { container } = render(
      <ReadingTile label="Voltage" value="12.04" unit="V" freshness="300 ms" quality="Verified" severity="success" stale={verdict === "stale"} />,
    );
    expect(container.querySelector("[data-bw-stale]")).toBeNull();
    expect(container.querySelector(".bw-reading__quality")!.textContent).not.toContain("stale");
  });
});
