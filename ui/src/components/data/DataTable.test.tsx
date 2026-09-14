import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTable } from "./DataTable";

describe("DataTable", () => {
  it("renders captioned engineering data with column headers", () => {
    render(
      <DataTable
        caption="Channel readings"
        rows={[{ id: "ch1", voltage: "12.04 V" }]}
        rowKey={(row) => row.id}
        columns={[
          { id: "channel", header: "Channel", cell: (row) => row.id },
          { id: "voltage", header: "Voltage", cell: (row) => row.voltage },
        ]}
      />,
    );

    expect(screen.getByRole("table", { name: "Channel readings" })).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "Voltage" })).toBeVisible();
    expect(screen.getByText("12.04 V")).toBeVisible();
  });
});
