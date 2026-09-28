import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { disabledReasonLabel, type DisabledReasonKey } from "../components/actions/disabledReasons";
import { ModeBanner } from "../components/feedback/ModeBanner";
import { DeviceWorkbench } from "./DeviceWorkbench";
import { daqProofFixture, psuProofFixture, type DeviceWorkbenchFixture } from "./fixtures";

vi.mock("echarts/core", () => ({
  init: () => ({ setOption: () => undefined, resize: () => undefined, dispose: () => undefined }),
  use: () => undefined,
}));

/** S2-A2 (design record §6): the five safety properties, asserted on BOTH
 *  example-fixture pages — a bench PSU workbench and a multi-channel DAQ,
 *  invented identities. Each page composes the ModeBanner (contract §D) with
 *  the DeviceWorkbench, mirroring how App and PreviewApp compose a page. */
function renderPage(fixture: DeviceWorkbenchFixture, requestEnabled = true) {
  return render(
    <main>
      <ModeBanner modes={["simulated"]} />
      <DeviceWorkbench
        fixture={fixture}
        requestEnabled={requestEnabled}
        onRequestSetPoint={() => undefined}
        onRequestOutputOn={() => undefined}
        onRequestOutputOff={() => undefined}
      />
    </main>,
  );
}

/** Property (e): every disabled control carries its reason's required visible
 *  label. The required text per key comes from the renderer's label map —
 *  which the contract-enforcement test independently pins, key by key, against
 *  the contract's §C.2 table — so this property checks the label is present
 *  and matches the declared key, without restating the texts a third time. */
function expectEveryDisabledControlLabelled() {
  const disabled = document.querySelectorAll("[data-bw-disabled-reason]");
  expect(disabled.length).toBeGreaterThan(0);
  for (const control of disabled) {
    const key = control.getAttribute("data-bw-disabled-reason") as DisabledReasonKey;
    const wrap = control.closest(".bw-button__reason");
    expect(wrap, `control with reason ${key} has a reason wrapper`).not.toBeNull();
    const label = wrap!.querySelector("[data-bw-disabled-label]");
    expect(label, `control with reason ${key} carries a visible label`).not.toBeNull();
    // Visible, not merely present (inline-style hides caught; the CSS-class
    // residual is disclosed in the contract tests).
    expect(label!, `control with reason ${key} carries a VISIBLE label`).toBeVisible();
    expect(label!.textContent).toBe(disabledReasonLabel({ key }));
  }
}

describe.each([
  ["PSU workbench page", psuProofFixture],
  ["DAQ workbench page", daqProofFixture],
] as const)("safety proof: %s", (name, fixture) => {
  it("(vacuous-pass control) contains an energy-sourcing and an energy-removing action", () => {
    renderPage(fixture);
    expect(screen.getByRole("button", { name: "Energise output" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "De-energise output" })).toBeInTheDocument();
  });

  it("(a) the energise confirm text states the exact values, unit and target", () => {
    renderPage(fixture);
    fireEvent.click(screen.getByRole("button", { name: "Energise output" }));
    const text = screen.getByText(/the output will be energised/);
    expect(text.textContent).toContain(`${fixture.stagedVoltage} V`);
    expect(text.textContent).toContain(`${fixture.device.id.toUpperCase()} output`);
  });

  it("(b) de-energise is one action with no confirm step", () => {
    const off = vi.fn();
    render(
      <main>
        <ModeBanner modes={["simulated"]} />
        <DeviceWorkbench fixture={fixture} onRequestOutputOff={off} />
      </main>,
    );
    fireEvent.click(screen.getByRole("button", { name: "De-energise output" }));
    expect(off).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/Confirm: De-energise/i)).not.toBeInTheDocument();
  });

  it("(c) energise is disabled with protection-active while a protective trip is active (R-PROTECT-1)", () => {
    renderPage({ ...fixture, output: { ...fixture.output, trip: true } });
    const energise = screen.getByRole("button", { name: "Energise output" });
    expect(energise).toBeDisabled();
    expect(energise).toHaveAttribute("data-bw-disabled-reason", "protection-active");
    // The trip guard never reaches the energy-REMOVING action (R-DEENERGISE-1).
    expect(screen.getByRole("button", { name: "De-energise output" })).toBeEnabled();
  });

  it("(d) the ModeBanner is present with the exact fixed wording", () => {
    renderPage(fixture);
    const banner = screen.getByLabelText("Presentation mode");
    expect(banner).toHaveAttribute("data-bw-mode-banner");
    expect(within(banner).getByText("SIMULATED PRESENTATION DATA")).toBeVisible();
  });

  it("(e) every disabled control carries its reason's required visible label", () => {
    // Trip render: energise + energised-set-point-apply disabled protection-active.
    const { unmount } = renderPage({ ...fixture, output: { ...fixture.output, trip: true } });
    expectEveryDisabledControlLabelled();
    unmount();
    // No-authority render: the same controls disabled no-authority.
    renderPage(fixture, false);
    expectEveryDisabledControlLabelled();
  });
});
