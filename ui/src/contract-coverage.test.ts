import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * L1/L3 pins over the normative renderer-neutral contract
 * (../docs/internal/ui-contract.md).
 *
 * L1 — fixture pins: every row the design record's §6 enumeration names must
 * be present and parsable from the contract's tables. A table that does not
 * parse (missing heading, missing table, wrong column schema, no rows) fails
 * closed — it can never present as a pass.
 *
 * L3 — contract↔CSS value equality: every pinned token value equals the
 * value parsed from ui/src/styles/tokens.css and themes.css, in both themes,
 * in both directions. The "executable mirror" rule made mechanical.
 *
 * The enumeration this fixture covers (design record §6, pre-committed):
 * definition rows 5+15+4+3+3+6+9 = 45 (disabled-reason, refusal, mode,
 * safety rules, state rules, severities, icons), 8 component rows,
 * 14 colour tokens × 2 themes + 6 spacing + 2 radius + 2 fonts, 9 icon rows.
 * The two --bw-shadow-* rows are a pinned superset closing the
 * "extra unpinned token" finding: every theme-varying colour in themes.css
 * is contract-pinned.
 */

const CONTRACT = readFileSync("../docs/internal/ui-contract.md", "utf8");

/** Parse the first pipe table under an exact heading; fail closed on any
 *  malformation. Returns the body rows (header and separator excluded). */
function parseTable(heading: string, expectedHeader: readonly string[]): string[][] {
  const lines = CONTRACT.split("\n");
  const headingIndex = lines.findIndex((line) => line.trim() === heading);
  if (headingIndex < 0) throw new Error(`contract section missing: ${heading}`);

  let tableStart = -1;
  for (let i = headingIndex + 1; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (line.startsWith("|")) {
      tableStart = i;
      break;
    }
    // A deeper heading before any table means the table is gone.
    if (line.startsWith("#")) break;
  }
  if (tableStart < 0) throw new Error(`no table under heading: ${heading}`);

  const rows: string[][] = [];
  for (let i = tableStart; i < lines.length && lines[i].trim().startsWith("|"); i += 1) {
    rows.push(lines[i].trim().replace(/^\|/, "").replace(/\|$/, "").split("|"));
  }
  if (rows.length < 3) throw new Error(`table under ${heading} is not a table (needs header, separator, rows)`);

  const header = rows[0].map((cell) => cell.trim());
  expect(header, `column schema drift under ${heading}`).toEqual([...expectedHeader]);
  return rows.slice(2).map((row) => row.map((cell) => cell.trim()));
}

/** Strip surrounding backticks from a contract cell value. */
const literal = (cell: string): string => cell.replace(/^`/, "").replace(/`$/, "");

function contractCell(table: string[][], row: number, column: number): string {
  const cells = table[row];
  if (cells === undefined || cells[column] === undefined) {
    throw new Error(`row ${row} / column ${column} unparsable`);
  }
  return cells[column];
}

/** Extract `--name: value;` custom properties from a CSS rule block whose
 *  selector contains the given selector fragment. */
function cssBlock(source: string, selector: string): Map<string, string> {
  const properties = new Map<string, string>();
  const blockPattern = /([^{}]*)\{([^{}]*)\}/g;
  for (const match of source.matchAll(blockPattern)) {
    if (!match[1]!.includes(selector)) continue;
    for (const declaration of match[2]!.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
      properties.set(`--${declaration[1]}`, declaration[2]!.trim());
    }
  }
  return properties;
}

describe("contract L1: fixture rows present and parsable", () => {
  it("§A.1 pins the colour palette (14 enumerated + 2 shadow inputs)", () => {
    const rows = parseTable("### §A.1 Colour palette", ["Token", "Light", "Dark", "Use"]);
    expect(rows.length).toBe(16);
    const tokens = rows.map((row) => literal(row[0]!));
    // The 14 enumerated rows (moved verbatim from the guide).
    for (const token of [
      "--bw-canvas",
      "--bw-surface",
      "--bw-surface-recessed",
      "--bw-text",
      "--bw-text-muted",
      "--bw-border",
      "--bw-accent",
      "--bw-accent-contrast",
      "--bw-focus",
      "--bw-advisory",
      "--bw-warning",
      "--bw-critical",
      "--bw-trip",
      "--bw-success",
    ]) {
      expect(tokens).toContain(token);
    }
    // The pinned superset: the two elevation-shadow colour inputs.
    expect(tokens).toContain("--bw-shadow-dark");
    expect(tokens).toContain("--bw-shadow-light");
    for (const row of rows) {
      expect(literal(row[1]!), `${literal(row[0]!)} light`).toMatch(/^#[0-9a-f]{6}$/);
      expect(literal(row[2]!), `${literal(row[0]!)} dark`).toMatch(/^#[0-9a-f]{6}$/);
      expect(contractCell([row], 0, 3)).not.toBe("");
    }
  });

  it("§A.2 pins the six spacing tokens", () => {
    const rows = parseTable("### §A.2 Spacing and layout", ["Token", "Value", "Typical use"]);
    const tokens = rows.map((row) => literal(row[0]!));
    expect(tokens).toEqual(["--bw-space-1", "--bw-space-2", "--bw-space-3", "--bw-space-4", "--bw-space-5", "--bw-space-6"]);
  });

  it("§A.3 pins the two radius tokens", () => {
    const rows = parseTable("### §A.3 Radius", ["Token", "Value", "Use"]);
    const tokens = rows.map((row) => literal(row[0]!));
    expect(tokens).toEqual(["--bw-radius-control", "--bw-radius-panel"]);
  });

  it("§A.4 pins the two font tokens", () => {
    const rows = parseTable("### §A.4 Typography fonts", ["Token", "Value", "Use"]);
    const tokens = rows.map((row) => literal(row[0]!));
    expect(tokens).toEqual(["--bw-font-ui", "--bw-font-data"]);
  });

  it("§B.1 pins the six severities with dismissal classes and live regions", () => {
    const rows = parseTable("### §B.1 Severities", ["Severity key", "Meaning", "Dismissal class", "Live region"]);
    const expected: Record<string, [string, string]> = {
      neutral: ["dismissible", "status"],
      success: ["dismissible", "status"],
      advisory: ["dismissible", "status"],
      warning: ["persistent-until-acknowledged-or-resolved", "status"],
      critical: ["persistent-until-resolved", "alert"],
      trip: ["non-dismissible-while-active", "alert"],
    };
    expect(rows.length).toBe(6);
    for (const row of rows) {
      const key = literal(row[0]!);
      const expectedClasses = expected[key];
      if (expectedClasses === undefined) throw new Error(`unexpected severity key: ${key}`);
      expect(literal(row[2]!), key).toBe(expectedClasses[0]);
      expect(literal(row[3]!), key).toBe(expectedClasses[1]);
      expect(contractCell([row], 0, 1)).not.toBe("");
    }
  });

  it("§B.2 pins the three state rules", () => {
    const rows = parseTable("### §B.2 State rules", ["Rule id", "Requirement"]);
    const ids = rows.map((row) => literal(row[0]!));
    expect(ids).toEqual(["SR-B1", "SR-B2", "SR-B3"]);
    for (const row of rows) expect(contractCell([row], 0, 1)).not.toBe("");
  });

  it("§C.1 pins the three safety rules", () => {
    const rows = parseTable("### §C.1 Safety rules", ["Rule id", "Requirement"]);
    const ids = rows.map((row) => literal(row[0]!));
    expect(ids).toEqual(["R-ENERGISE-1", "R-DEENERGISE-1", "R-PROTECT-1"]);
    for (const row of rows) expect(contractCell([row], 0, 1)).not.toBe("");
  });

  it("§C.2 pins the five-key disabled-reason enum with required label text", () => {
    const rows = parseTable("### §C.2 Disabled-reason enum", ["Key", "Required label text", "Parameter"]);
    const expected: Record<string, string> = {
      "capability-absent": "Not available on this device",
      "device-state": "Device must be {state}",
      "protection-active": "Protection trip active",
      "invalid-staged-input": "Staged value is invalid",
      "no-authority": "No lease or policy authority",
    };
    expect(rows.length).toBe(5);
    for (const row of rows) {
      const key = literal(row[0]!);
      const label = expected[key];
      if (label === undefined) throw new Error(`unexpected disabled-reason key: ${key}`);
      expect(literal(row[1]!), key).toBe(label);
    }
  });

  it("§C.3 pins the refusal mapping over all 14 interface codes plus no-response", () => {
    const rows = parseTable("### §C.3 Refusal mapping", ["Code", "Severity", "What happened", "Sent status", "Operator action"]);
    const expected: Record<string, [string, string]> = {
      invalid_request: ["warning", "NO"],
      unauthenticated: ["warning", "NO"],
      forbidden: ["warning", "NO"],
      not_found: ["advisory", "NO"],
      conflict: ["warning", "NO"],
      policy_denied: ["warning", "NO"],
      not_ready: ["advisory", "NO"],
      gone: ["advisory", "NO"],
      cursor_expired: ["advisory", "NO"],
      event_gap: ["warning", "NO"],
      payload_too_large: ["warning", "NO"],
      rate_limited: ["advisory", "NO"],
      unavailable: ["critical", "NO"],
      internal_error: ["warning", "NO"],
      "no-response": ["critical", "UNKNOWN"],
    };
    expect(rows.length).toBe(15);
    for (const row of rows) {
      const code = literal(row[0]!);
      const pair = expected[code];
      if (pair === undefined) throw new Error(`unexpected refusal code: ${code}`);
      expect(literal(row[1]!), code).toBe(pair[0]);
      expect(literal(row[3]!), `${code} sent status`).toBe(pair[1]);
      expect(contractCell([row], 0, 2), `${code} what happened`).not.toBe("");
      expect(contractCell([row], 0, 4), `${code} operator action`).not.toBe("");
    }
    // not_found wording must not leak existence.
    const notFound = rows.find((row) => literal(row[0]!) === "not_found");
    expect(notFound![2]).not.toContain("does not exist");
  });

  it("§D.1 pins the four mode-banner modes with fixed wording", () => {
    const rows = parseTable("### §D.1 Modes", ["Mode", "Fixed wording", "Fires when"]);
    const expected: Record<string, string> = {
      simulated: "SIMULATED PRESENTATION DATA",
      "no-gateway": "NO GATEWAY · LOCAL PRESENTATION ONLY",
      "no-lease": "NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED",
      "no-policy": "NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE",
    };
    expect(rows.length).toBe(4);
    for (const row of rows) {
      const mode = literal(row[0]!);
      const wording = expected[mode];
      if (wording === undefined) throw new Error(`unexpected mode: ${mode}`);
      expect(literal(row[1]!), mode).toBe(wording);
      expect(contractCell([row], 0, 2)).not.toBe("");
    }
  });

  it("§E.1 pins the 8 slice-1 component rows", () => {
    const rows = parseTable(
      "### §E.1 Components",
      ["Component", "Root element", "Required attributes", "Required roles", "Required class hooks", "Required text", "Notes"],
    );
    const ids = rows.map((row) => literal(row[0]!));
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
    // Every row must carry the full column set (no emptied cells except text/notes).
    for (const row of rows) {
      for (const column of [1, 2, 3, 4]) {
        expect(contractCell([row], 0, column), `${literal(row[0]!)} column ${column}`).not.toBe("");
      }
    }
  });

  it("§F.1 pins the 9 icon rows (6 severity + 3 state)", () => {
    const rows = parseTable("### §F.1 Icons", ["Icon key", "Class", "Shape description", "Reference binding"]);
    const expected: Record<string, [string, string]> = {
      neutral: ["severity", "CircleHelp"],
      success: ["severity", "CheckCircle2"],
      advisory: ["severity", "Info"],
      warning: ["severity", "TriangleAlert"],
      critical: ["severity", "AlertCircle"],
      trip: ["severity", "ShieldAlert"],
      busy: ["state", "none today"],
      hidden: ["state", "none today"],
      staged: ["state", "none today"],
    };
    expect(rows.length).toBe(9);
    for (const row of rows) {
      const key = literal(row[0]!);
      const pair = expected[key];
      if (pair === undefined) throw new Error(`unexpected icon key: ${key}`);
      expect(literal(row[1]!), key).toBe(pair[0]);
      expect(literal(row[3]!), key).toBe(pair[1]);
      expect(contractCell([row], 0, 2), `${key} shape`).not.toBe("");
    }
  });

  it("covers the §6 enumeration arithmetic (45 definition rows)", () => {
    const disabled = parseTable("### §C.2 Disabled-reason enum", ["Key", "Required label text", "Parameter"]).length;
    const refusal = parseTable("### §C.3 Refusal mapping", ["Code", "Severity", "What happened", "Sent status", "Operator action"]).length;
    const modes = parseTable("### §D.1 Modes", ["Mode", "Fixed wording", "Fires when"]).length;
    const safety = parseTable("### §C.1 Safety rules", ["Rule id", "Requirement"]).length;
    const stateRules = parseTable("### §B.2 State rules", ["Rule id", "Requirement"]).length;
    const severities = parseTable("### §B.1 Severities", ["Severity key", "Meaning", "Dismissal class", "Live region"]).length;
    const icons = parseTable("### §F.1 Icons", ["Icon key", "Class", "Shape description", "Reference binding"]).length;
    // 5+15+4+3+3+6+9 = 45 (design record §6). Icons are counted once here and
    // pinned as their own family above.
    expect(disabled + refusal + modes + safety + stateRules + severities + icons).toBe(45);
  });
});

describe("contract L3: contract↔CSS value equality", () => {
  const themesCss = readFileSync("src/styles/themes.css", "utf8");
  const tokensCss = readFileSync("src/styles/tokens.css", "utf8");
  const light = cssBlock(themesCss, 'data-theme="light"');
  const dark = cssBlock(themesCss, 'data-theme="dark"');
  const root = cssBlock(tokensCss, ":root");

  it("every colour token equals the parsed theme value, both themes, both directions", () => {
    const rows = parseTable("### §A.1 Colour palette", ["Token", "Light", "Dark", "Use"]);
    const pinned = new Set<string>();
    for (const row of rows) {
      const token = literal(row[0]!);
      pinned.add(token);
      const contractLight = literal(row[1]!);
      const contractDark = literal(row[2]!);
      expect(light.get(token), `${token} missing from themes.css light block`).toBeDefined();
      expect(dark.get(token), `${token} missing from themes.css dark block`).toBeDefined();
      expect(light.get(token), `${token} light: contract vs CSS`).toBe(contractLight);
      expect(dark.get(token), `${token} dark: contract vs CSS`).toBe(contractDark);
    }
    // Reverse direction: every theme-varying colour in themes.css is pinned.
    for (const token of light.keys()) {
      expect(pinned, `themes.css light token ${token} is not contract-pinned`).toContain(token);
    }
    for (const token of dark.keys()) {
      expect(pinned, `themes.css dark token ${token} is not contract-pinned`).toContain(token);
    }
  });

  it("spacing, radius and font tokens equal the parsed tokens.css values, both directions", () => {
    const spacing = parseTable("### §A.2 Spacing and layout", ["Token", "Value", "Typical use"]);
    const radius = parseTable("### §A.3 Radius", ["Token", "Value", "Use"]);
    const fonts = parseTable("### §A.4 Typography fonts", ["Token", "Value", "Use"]);
    const rows = [...spacing, ...radius, ...fonts];
    const pinned = new Set<string>();
    for (const row of rows) {
      const token = literal(row[0]!);
      pinned.add(token);
      expect(root.get(token), `${token} missing from tokens.css`).toBeDefined();
      expect(root.get(token), `${token}: contract vs tokens.css`).toBe(literal(row[1]!));
    }
    // Reverse direction: every --bw-space-*, --bw-radius-* and --bw-font-*
    // custom property in tokens.css is pinned.
    for (const token of root.keys()) {
      if (/^--bw-(space|radius|font)-/.test(token) || token === "--bw-font-ui" || token === "--bw-font-data") {
        expect(pinned, `tokens.css token ${token} is not contract-pinned`).toContain(token);
      }
    }
  });
});
