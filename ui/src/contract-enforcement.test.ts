import { readFileSync } from "node:fs";
import { render, within, type RenderResult } from "@testing-library/react";
import { createElement, type ReactElement } from "react";
import { describe, expect, it } from "vitest";

import { Button } from "./components/actions/Button";
import { DataTable, type DataColumn } from "./components/data/DataTable";
import { AlertBubble } from "./components/feedback/AlertBubble";
import { NumericInput } from "./components/inputs/NumericInput";
import { RotaryControl } from "./components/instruments/RotaryControl";
import { EngineeringPlot, type PlotTrace, type TraceHint } from "./components/plots/EngineeringPlot";
import { ReadingTile } from "./components/readings/ReadingTile";
import { Panel } from "./components/surfaces/Panel";

/**
 * L2 — generated renderer pins over the normative contract's §E.1 component
 * rows (../docs/internal/ui-contract.md). One assertion is generated per
 * contract-required attribute, role, class hook and required-text item of
 * each enforced row, asserted on the reference renderer's canonical
 * rendering.
 *
 * A contract row whose component id has no fixture below fails the test:
 * rows cannot appear without implementations (red by construction).
 */

const CONTRACT = readFileSync("../docs/internal/ui-contract.md", "utf8");

function componentRows(): Array<{
  component: string;
  attributes: string[];
  roles: string[];
  classHooks: string[];
  requiredText: string[];
}> {
  const lines = CONTRACT.split("\n");
  const headingIndex = lines.findIndex((line) => line.trim() === "### §E.1 Components");
  if (headingIndex < 0) throw new Error("contract section missing: ### §E.1 Components");
  const expectedHeader = ["Component", "Root element", "Required attributes", "Required roles", "Required class hooks", "Required text", "Notes"];
  const rows: string[][] = [];
  for (let i = headingIndex + 1; i < lines.length && !lines[i].trim().startsWith("#"); i += 1) {
    if (lines[i].trim().startsWith("|")) rows.push(lines[i].trim().replace(/^\|/, "").replace(/\|$/, "").split("|"));
  }
  if (rows.length < 3) throw new Error("no parsable table under ### §E.1 Components");
  expect(rows[0].map((cell) => cell.trim())).toEqual(expectedHeader);
  return rows.slice(2).map((row) => {
    const cells = row.map((cell) => cell.trim());
    // The item separator is the SPACED ` ~ `; the contains-operator `~=`
    // is unspaced, so splitting on " ~ " keeps `name~=substring` intact.
    const items = (cell: string): string[] =>
      cell.replace(/^`/, "").replace(/`$/, "").split(" ~ ").map((item) => item.trim()).filter((item) => item !== "" && item !== "—");
    return {
      component: cells[0]!.replace(/^`/, "").replace(/`$/, ""),
      attributes: items(cells[2]!),
      roles: items(cells[3]!),
      classHooks: items(cells[4]!),
      requiredText: items(cells[5]!),
    };
  });
}

/** One element in the container satisfies the attribute item:
 *  `name` (present), `name=value` (exact), `name~=substring` (contains). */
function satisfiesAttribute(container: HTMLElement, item: string): boolean {
  const exact = item.match(/^([\w-]+)=(.+)$/);
  if (exact) return container.querySelector(`[${exact[1]}="${exact[2]}"]`) !== null;
  const contains = item.match(/^([\w-]+)~=(.+)$/);
  if (contains) {
    for (const element of container.querySelectorAll(`[${contains[1]}]`)) {
      if (element.getAttribute(contains[1]!)?.includes(contains[2]!)) return true;
    }
    return false;
  }
  return container.querySelector(`[${item}]`) !== null;
}

const plotTraces: PlotTrace[] = [
  { id: "voltage", label: "Output voltage", unit: "V", values: [[0, 0], [1, 1]] },
  { id: "current", label: "Output current", unit: "A", values: [[0, 0], [1, 0.5]] },
];
const plotHints: ReadonlyMap<string, TraceHint> = new Map([["current", { visible: false }]]);

interface TableRow {
  id: string;
  label: string;
  value: string;
  quality: string;
}
const tableRows: TableRow[] = [
  { id: "voltage", label: "Output voltage", value: "12.1 V", quality: "steady · 2 s" },
];
const tableColumns: DataColumn<TableRow>[] = [
  { id: "quantity", header: "Quantity", cell: (row) => row.label },
  { id: "reading", header: "Reading", cell: (row) => row.value },
  { id: "quality", header: "Quality", cell: (row) => row.quality },
];

/** The enforced-row fixture: the canonical rendering of every enforced
 *  component. Slice 2 grows this with mode-banner and confirm-action. */
const fixtures: Record<string, () => ReactElement> = {
  button: () => createElement(Button, { variant: "secondary" }, "Apply staged set-point"),
  "numeric-input": () =>
    createElement(NumericInput, { label: "Precise voltage", value: 1.5, unit: "V", min: 0, max: 15, step: 0.1, onChange: () => undefined }),
  "rotary-control": () =>
    createElement(RotaryControl, { label: "Voltage set-point", value: 1.5, unit: "V", min: 0, max: 15, step: 0.1, onStage: () => undefined }),
  "reading-tile": () =>
    createElement(ReadingTile, { label: "Output voltage", value: 12.1, unit: "V", freshness: "2 s", quality: "steady", severity: "warning" }),
  "alert-bubble": () =>
    createElement(AlertBubble, {
      severity: "advisory",
      title: "Operating margin",
      message: "Approaching the configured limit.",
      source: "PSU-01",
      onDismiss: () => undefined,
    }),
  "engineering-plot": () =>
    createElement(EngineeringPlot, {
      kind: "time_series",
      title: "Output activity",
      x: { label: "Receipt time", unit: "s" },
      traces: plotTraces,
      hints: plotHints,
    }),
  "data-table": () => createElement(DataTable, { caption: "Channel readings", rows: tableRows, columns: tableColumns, rowKey: (row: TableRow) => row.id }),
  panel: () =>
    createElement(Panel, { title: "Output set-point", eyebrow: "Staged configuration" }, createElement("p", undefined, "Staged configuration content.")),
};

describe("contract L2: the reference renderer enforces every component row", () => {
  const rows = componentRows();

  it("parses the 8 slice-1 component rows and has a fixture for each", () => {
    const ids = rows.map((row) => row.component);
    for (const component of [
      "button",
      "numeric-input",
      "rotary-control",
      "reading-tile",
      "alert-bubble",
      "engineering-plot",
      "data-table",
      "panel",
    ]) {
      expect(ids).toContain(component);
    }
    // Red by construction: a contract row without an implementation fixture.
    for (const row of rows) {
      expect(fixtures[row.component], `component row ${row.component} has no enforcement fixture`).toBeDefined();
    }
  });

  for (const row of rows) {
    it(`renders ${row.component} with every contract-required attribute, role, class hook and text`, () => {
      const rendered: RenderResult = render(fixtures[row.component]!());
      const container = rendered.container;

      for (const attribute of row.attributes) {
        expect(
          satisfiesAttribute(container, attribute),
          `${row.component}: required attribute "${attribute}" not rendered`,
        ).toBe(true);
      }
      for (const role of row.roles) {
        expect(() => within(container).getByRole(role), `${row.component}: required role "${role}" not rendered`).not.toThrow();
      }
      for (const classHook of row.classHooks) {
        expect(
          container.querySelector(`.${classHook}`),
          `${row.component}: required class hook "${classHook}" not rendered`,
        ).not.toBeNull();
      }
      for (const text of row.requiredText) {
        expect(container.textContent, `${row.component}: required text "${text}" not rendered`).toContain(text);
      }
    });
  }
});
