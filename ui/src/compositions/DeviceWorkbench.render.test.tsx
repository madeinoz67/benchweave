import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

// No echarts mock in this file: the threshold claim is about what the REAL
// renderer draws in the preview (FC1's bar — a payload recorded by a mock
// proves nothing about the mark line actually rendering or not).
import { DeviceWorkbench } from "./DeviceWorkbench";
import { warningWorkbench } from "./fixtures";

describe("DeviceWorkbench real rendering", () => {
  it("draws no fabricated threshold on the preview workbench plot (R1b)", () => {
    // PreviewApp renders the workbench with NO threshold: the preview must
    // not paint a warning limit beside the never-fabricating declared plots
    // — "no limit plotted" is the honest render for simulated snapshot data
    // whose limits nobody qualified. The gateway demo (App.tsx) supplies its
    // own; here the prop is absent by default.
    const { container } = render(<DeviceWorkbench fixture={warningWorkbench} />);

    const svg = container.querySelector(".bw-plot__canvas svg");
    expect(svg, "echarts rendered an SVG into the workbench plot").toBeTruthy();
    expect(svg!.textContent).not.toContain("Current warning limit");
    expect(screen.queryByText(/warning limit/i)).toBeNull();
    // Dashed pass-1 trace styles are legitimate without a threshold; the
    // distinguishing absence is the LABEL — a threshold always draws its
    // label through real echarts (the FC1-carrier proof), so textContent is
    // the honest arm here.
  });

  it("still draws the workbench traces without the threshold", () => {
    const { container } = render(<DeviceWorkbench fixture={warningWorkbench} />);
    const svg = container.querySelector(".bw-plot__canvas svg");
    expect(svg).toBeTruthy();
    expect(container.querySelectorAll(".bw-plot__legend li").length).toBe(
      warningWorkbench.traces.length,
    );
  });
});
