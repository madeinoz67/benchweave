import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModeBanner } from "./ModeBanner";

describe("ModeBanner (contract §D)", () => {
  it("renders every mode with its exact fixed wording in the contract's fixed order", () => {
    const { container } = render(<ModeBanner modes={["no-policy", "simulated", "no-lease", "no-gateway"]} />);
    const banner = screen.getByLabelText("Presentation mode");
    expect(banner).toHaveAttribute("data-bw-mode-banner");
    const entries = [...banner.querySelectorAll("[data-bw-mode]")];
    expect(entries.map((entry) => entry.getAttribute("data-bw-mode"))).toEqual(["simulated", "no-gateway", "no-lease", "no-policy"]);
    // Byte-exact fixed wording — the `simulated` string is pinned by SDK
    // console, TUI and test output and must not drift.
    expect(entries.map((entry) => entry.textContent)).toEqual([
      "SIMULATED PRESENTATION DATA",
      "NO GATEWAY · LOCAL PRESENTATION ONLY",
      "NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED",
      "NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE",
    ]);
    expect(container.querySelector("[data-bw-mode-banner] [data-bw-mode='simulated']")).not.toBeNull();
  });

  it("renders only the active modes", () => {
    render(<ModeBanner modes={["no-gateway"]} />);
    expect(screen.getByText("NO GATEWAY · LOCAL PRESENTATION ONLY")).toBeVisible();
    expect(screen.queryByText("SIMULATED PRESENTATION DATA")).not.toBeInTheDocument();
  });

  it("renders nothing for an empty mode list — absence asserts full-authority presentation", () => {
    const { container } = render(<ModeBanner modes={[]} />);
    expect(container.querySelector("[data-bw-mode-banner]")).toBeNull();
  });

  it("has no dismiss affordance — the banner is non-dismissible", () => {
    const { container } = render(<ModeBanner modes={["simulated"]} />);
    expect(container.querySelector("button")).toBeNull();
  });
});
