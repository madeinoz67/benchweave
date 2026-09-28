import { readFileSync } from "node:fs";
import { fireEvent, render, within, type RenderResult } from "@testing-library/react";
import { createElement, type ReactElement } from "react";
import { describe, expect, it } from "vitest";

import { Button } from "./components/actions/Button";
import { ConfirmAction } from "./components/actions/ConfirmAction";
import { DataTable, type DataColumn } from "./components/data/DataTable";
import { AlertBubble } from "./components/feedback/AlertBubble";
import { ModeBanner } from "./components/feedback/ModeBanner";
import { RefusalMessage, type RefusalCode } from "./components/feedback/refusals";
import { NumericInput } from "./components/inputs/NumericInput";
import { RotaryControl } from "./components/instruments/RotaryControl";
import { EngineeringPlot, type PlotTrace, type TraceHint } from "./components/plots/EngineeringPlot";
import { ReadingTile } from "./components/readings/ReadingTile";
import { Panel } from "./components/surfaces/Panel";

// Kept as .ts (the designed filename, referenced by the contract's authoring
// rule and drift obligation 12) with createElement fixtures rather than JSX,
// which would force a .tsx rename.

/**
 * L2 — generated renderer pins over the normative contract
 * (../docs/internal/ui-contract.md). One assertion is generated per
 * contract-required attribute, role, class hook and required-text item of
 * each enforced component row, asserted on the reference renderer's canonical
 * rendering — plus the §C.2 disabled-reason labels and the §C.3 refusal rows'
 * required message elements, rendered key by key and code by code.
 *
 * A contract row whose component id has no fixture below fails the test:
 * rows cannot appear without implementations (red by construction).
 */

const CONTRACT = readFileSync("../docs/internal/ui-contract.md", "utf8");

/** Parse the pipe table under an exact heading, fail-closed (missing heading,
 *  missing table, wrong header cells, empty body all throw). */
function contractTable(heading: string, expectedHeader: readonly string[]): string[][] {
  const lines = CONTRACT.split("\n");
  const headingIndex = lines.findIndex((line) => line.trim() === heading);
  if (headingIndex < 0) throw new Error(`contract section missing: ${heading}`);
  const rows: string[][] = [];
  for (let i = headingIndex + 1; i < lines.length && !lines[i].trim().startsWith("#"); i += 1) {
    if (lines[i].trim().startsWith("|")) rows.push(lines[i].trim().replace(/^\|/, "").replace(/\|$/, "").split("|"));
  }
  if (rows.length < 3) throw new Error(`no parsable table under ${heading}`);
  expect(rows[0].map((cell) => cell.trim())).toEqual([...expectedHeader]);
  return rows.slice(2).map((row) => row.map((cell) => cell.trim()));
}

const literal = (cell: string): string => cell.replace(/^`/, "").replace(/`$/, "");

function componentRows(): Array<{
  component: string;
  attributes: string[];
  roles: string[];
  classHooks: string[];
  requiredText: string[];
}> {
  return contractTable(
    "### §E.1 Components",
    ["Component", "Root element", "Required attributes", "Required roles", "Required class hooks", "Required text", "Notes"],
  ).map((row) => {
    const items = (cell: string): string[] =>
      literal(cell).split(" ~ ").map((item) => item.trim()).filter((item) => item !== "" && item !== "—");
    return {
      component: literal(row[0]!),
      attributes: items(row[2]!),
      roles: items(row[3]!),
      classHooks: items(row[4]!),
      requiredText: items(row[5]!),
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
 *  component, as a RenderResult so a fixture can include its arming
 *  interaction (the confirm-action row's required text lives in the ARMED
 *  step). Slice 2 adds mode-banner and confirm-action. */
const element = (component: typeof Button | typeof AlertBubble | typeof DataTable | typeof ModeBanner | typeof NumericInput | typeof RotaryControl | typeof EngineeringPlot | typeof ReadingTile | typeof Panel | typeof ConfirmAction | typeof RefusalMessage | "p", props: Record<string, unknown>, ...children: unknown[]): ReactElement =>
  createElement(component as never, props as never, ...((children ?? []) as never[]));

const fixtures: Record<string, () => RenderResult> = {
  button: () => render(element(Button, { variant: "secondary" }, "Apply staged set-point")),
  "numeric-input": () => render(element(NumericInput, { label: "Precise voltage", value: 1.5, unit: "V", min: 0, max: 15, step: 0.1, onChange: () => undefined })),
  "rotary-control": () => render(element(RotaryControl, { label: "Voltage set-point", value: 1.5, unit: "V", min: 0, max: 15, step: 0.1, onStage: () => undefined })),
  "reading-tile": () => render(element(ReadingTile, { label: "Output voltage", value: 12.1, unit: "V", freshness: "2 s", quality: "steady", severity: "warning" })),
  "alert-bubble": () => render(element(AlertBubble, { severity: "advisory", title: "Operating margin", message: "Approaching the configured limit.", source: "PSU-01", onDismiss: () => undefined })),
  "engineering-plot": () => render(element(EngineeringPlot, { kind: "time_series", title: "Output activity", x: { label: "Receipt time", unit: "s" }, traces: plotTraces, hints: plotHints })),
  "data-table": () => render(element(DataTable, { caption: "Channel readings", rows: tableRows, columns: tableColumns, rowKey: (row: TableRow) => row.id })),
  panel: () => render(element(Panel, { title: "Output set-point", eyebrow: "Staged configuration" }, element("p", {}, "Staged configuration content."))),
  // §D: the enforcement fixture renders ALL FOUR modes so every fixed wording
  // is pinned; a page renders only its active modes.
  "mode-banner": () => render(element(ModeBanner, { modes: ["simulated", "no-gateway", "no-lease", "no-policy"] })),
  // R-ENERGISE-1's required text (effect, value+unit, target) lives in the
  // ARMED confirm step, so the fixture stages the action first.
  "confirm-action": () => {
    const rendered = render(
      element(ConfirmAction, {
        label: "Energise output",
        effect: "the output will be energised",
        value: { amount: 12.5, unit: "V" },
        target: "PSU-07 output",
        onConfirm: () => undefined,
      }),
    );
    fireEvent.click(rendered.getByRole("button", { name: "Energise output" }));
    return rendered;
  },
};

describe("contract L2: the reference renderer enforces every component row", () => {
  const rows = componentRows();

  it("parses the 10 component rows and has a fixture for each", () => {
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
      "mode-banner",
      "confirm-action",
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
      const rendered = fixtures[row.component]!();
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

describe("contract L2: the reference renderer enforces §C.2 disabled-reason labels", () => {
  const table = contractTable("### §C.2 Disabled-reason enum", ["Key", "Required label text", "Parameter"]);

  it("parses the five-key enum", () => {
    expect(table.length).toBe(5);
  });

  for (const row of table) {
    const key = literal(row[0]!);
    const template = literal(row[1]!);
    it(`renders ${key} with its required visible label`, () => {
      const { container } = render(element(Button, { disabled: true, disabledReason: { key, state: "idle" } }, "Act"));
      const control = container.querySelector("[data-bw-disabled-reason]");
      expect(control, `${key}: reason attribute not rendered`).not.toBeNull();
      expect(control!.getAttribute("data-bw-disabled-reason")).toBe(key);
      const label = container.querySelector("[data-bw-disabled-label]");
      expect(label, `${key}: visible label not rendered beside the control`).not.toBeNull();
      // The device-state key's template carries the {state} slot; the
      // canonical blocking state from the contract is `idle`.
      expect(label!.textContent).toBe(template.replace("{state}", "idle"));
    });
  }
});

describe("contract L2: the reference renderer enforces §C.3 refusal rendering", () => {
  const table = contractTable(
    "### §C.3 Refusal mapping",
    ["Code", "Severity", "What happened", "Sent status", "Operator action"],
  );

  it("parses all 14 interface codes plus the no-response row", () => {
    expect(table.length).toBe(15);
  });

  for (const row of table) {
    const code = literal(row[0]!);
    const severity = literal(row[1]!);
    const whatHappened = literal(row[2]!);
    const sent = literal(row[3]!);
    const operatorAction = literal(row[4]!);
    it(`renders the ${code} refusal with its required message elements`, () => {
      const { container } = render(element(RefusalMessage, { code: code as RefusalCode }));
      const bubble = container.querySelector(".bw-alert-bubble");
      expect(bubble, `${code}: refusal not rendered`).not.toBeNull();
      expect(bubble!.getAttribute("data-severity")).toBe(severity);
      const text = container.textContent ?? "";
      expect(text, `${code}: what happened not rendered`).toContain(whatHappened);
      expect(text, `${code}: operator action not rendered`).toContain(operatorAction);
      // The sent-status element: NO renders "nothing was sent"; UNKNOWN (A06)
      // renders that it is unknown whether anything was sent.
      const sentElement = sent === "NO" ? "Nothing was sent." : "It is unknown whether anything was sent";
      expect(text, `${code}: sent status not rendered`).toContain(sentElement);
    });
  }
});
