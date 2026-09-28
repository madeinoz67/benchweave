import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DeviceWorkbench } from "./DeviceWorkbench";
import { warningWorkbench } from "./fixtures";

vi.mock("echarts/core", () => ({
  init: () => ({ setOption: () => undefined, resize: () => undefined, dispose: () => undefined }),
  use: () => undefined,
}));

describe("DeviceWorkbench", () => {
  it("keeps simulation and warning state visible while emitting staged request intent", () => {
    const onRequestSetPoint = vi.fn();
    render(<DeviceWorkbench fixture={warningWorkbench} onRequestSetPoint={onRequestSetPoint} />);

    expect(screen.getByText("SIMULATED")).toBeVisible();
    expect(screen.getByText("Current approaching configured limit")).toBeVisible();
    // R-ENERGISE-1: the fixture's output is energised, so applying the staged
    // set-point is energy-sourcing — the first click only STAGES, and the
    // confirm step states the effect, the exact value with unit, and the
    // target before the second explicit action fires the request.
    fireEvent.click(screen.getByRole("button", { name: "Apply staged set-point" }));
    expect(onRequestSetPoint).not.toHaveBeenCalled();
    expect(screen.getByText(/the set-point of the energised output will change/)).toBeVisible();
    expect(screen.getByText(/12 V to PSU-01 output/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Confirm: Apply staged set-point" }));
    expect(onRequestSetPoint).toHaveBeenCalledWith(12);
    expect(screen.queryByText(/set-point applied/i)).not.toBeInTheDocument();
  });

  it("de-energises in one action, with no confirm step (R-DEENERGISE-1)", () => {
    const onRequestOutputOff = vi.fn();
    render(<DeviceWorkbench fixture={warningWorkbench} onRequestOutputOff={onRequestOutputOff} />);

    const deEnergise = screen.getByRole("button", { name: "De-energise output" });
    expect(deEnergise).toBeEnabled();
    fireEvent.click(deEnergise);
    expect(onRequestOutputOff).toHaveBeenCalledTimes(1);
    // No confirm step ever appears for the energy-removing action.
    expect(screen.queryByText(/Confirm: De-energise/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/will be de-energised/i)).not.toBeInTheDocument();
  });

  it("confirms the energise action with the exact value and target (R-ENERGISE-1)", () => {
    const onRequestOutputOn = vi.fn();
    render(<DeviceWorkbench fixture={{ ...warningWorkbench, output: { energised: false, trip: false } }} onRequestOutputOn={onRequestOutputOn} />);

    fireEvent.click(screen.getByRole("button", { name: "Energise output" }));
    expect(onRequestOutputOn).not.toHaveBeenCalled();
    expect(screen.getByText(/the output will be energised/)).toBeVisible();
    expect(screen.getByText(/12 V to PSU-01 output/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Confirm: Energise output" }));
    expect(onRequestOutputOn).toHaveBeenCalledWith(12);
  });

  it("applies a set-point on a de-energised output without a confirm step", () => {
    const onRequestSetPoint = vi.fn();
    render(<DeviceWorkbench fixture={{ ...warningWorkbench, output: { energised: false, trip: false } }} onRequestSetPoint={onRequestSetPoint} />);

    fireEvent.click(screen.getByRole("button", { name: "Apply staged set-point" }));
    expect(onRequestSetPoint).toHaveBeenCalledWith(12);
    expect(screen.queryByText(/Confirm: Apply staged set-point/)).not.toBeInTheDocument();
  });
});

describe("DeviceWorkbench armed guard (the guard holds at fire time)", () => {
  it("disables an armed energise confirm when the trip arrives mid-flight, and does not dispatch", () => {
    const onRequestOutputOn = vi.fn();
    const { rerender } = render(
      <DeviceWorkbench fixture={{ ...warningWorkbench, output: { energised: false, trip: false } }} onRequestOutputOn={onRequestOutputOn} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Energise output" }));
    rerender(
      <DeviceWorkbench fixture={{ ...warningWorkbench, output: { energised: false, trip: true } }} onRequestOutputOn={onRequestOutputOn} />,
    );
    const confirm = screen.getByRole("button", { name: "Confirm: Energise output" });
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAttribute("data-bw-disabled-reason", "protection-active");
    // The armed confirm's own reason wrapper carries the required visible label.
    within(confirm.closest(".bw-button__reason") as HTMLElement).getByText("Protection trip active");
    fireEvent.click(confirm);
    expect(onRequestOutputOn).not.toHaveBeenCalled();
  });

  it("presents protection-active — not no-authority — when trip and missing authority combine", () => {
    const { rerender } = render(
      <DeviceWorkbench
        fixture={{ ...warningWorkbench, output: { energised: false, trip: false } }}
        requestEnabled
        onRequestOutputOn={() => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Energise output" }));
    rerender(
      <DeviceWorkbench
        fixture={{ ...warningWorkbench, output: { energised: false, trip: true } }}
        requestEnabled={false}
        onRequestOutputOn={() => undefined}
      />,
    );
    const confirm = screen.getByRole("button", { name: "Confirm: Energise output" });
    expect(confirm).toHaveAttribute("data-bw-disabled-reason", "protection-active");
    expect(screen.queryByText("No lease or policy authority")).not.toBeInTheDocument();
  });
});
