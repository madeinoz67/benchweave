import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Panel } from "./Panel";

describe("Panel", () => {
  it("labels a raised region", () => {
    render(<Panel title="Output">Value</Panel>);

    expect(screen.getByRole("region", { name: "Output" })).toHaveAttribute(
      "data-surface",
      "raised",
    );
  });

  it("exposes recessed data surfaces", () => {
    render(
      <Panel title="Trend" recessed>
        Graph
      </Panel>,
    );

    expect(screen.getByRole("region", { name: "Trend" })).toHaveAttribute(
      "data-surface",
      "recessed",
    );
  });
});
