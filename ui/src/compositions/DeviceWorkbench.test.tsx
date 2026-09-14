import { fireEvent, render, screen } from "@testing-library/react";
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
    fireEvent.click(screen.getByRole("button", { name: "Apply staged set-point" }));
    expect(onRequestSetPoint).toHaveBeenCalledWith(12);
    expect(screen.queryByText(/set-point applied/i)).not.toBeInTheDocument();
  });
});
