import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AdminOverview } from "./AdminOverview";
import { adminFixture } from "./fixtures";

describe("AdminOverview", () => {
  it("uses explicit admission and approval states", () => {
    render(<AdminOverview fixture={adminFixture} />);

    expect(screen.getByRole("heading", { name: "Administration" })).toBeVisible();
    expect(screen.getByText("Admitted")).toBeVisible();
    expect(screen.getAllByText("Pending independent approval")).toHaveLength(2);
  });
});
