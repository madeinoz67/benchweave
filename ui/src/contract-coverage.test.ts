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
 * definition rows 5+15+4+3+3+6+10+1+4+3 = 54 (slice 1) + 4+4+3+4 = 15
 * (slice 2) = 69 (#243) + 4+4+4+3+4 = 19 (#244 S2) = 88, 11 component rows, 25 colour tokens × 2 themes + 6
 * spacing + 2 radius + 2 fonts, 10 icon rows.
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
  const body = rows.slice(2).map((row) => row.map((cell) => cell.trim()));
  // A body row whose cell count differs from the header's is a parse failure,
  // not a silently mis-parsed row (an appended or dropped cell must never
  // present as a pass).
  for (const row of body) {
    expect(row.length, `row under ${heading} has ${row.length} cells, header has ${expectedHeader.length}`).toBe(expectedHeader.length);
  }
  return body;
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
  it("§A.1 pins the colour palette (14 enumerated + --bw-limiting + 8 series slots + 2 shadow inputs)", () => {
    const rows = parseTable("### §A.1 Colour palette", ["Token", "Light", "Dark", "Use"]);
    expect(rows.length).toBe(25);
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
    // The 8 series slots (issue #242 slice 3; values carry the computed
    // proofs in series-colors.test.ts).
    for (const token of ["--bw-series-1", "--bw-series-2", "--bw-series-3", "--bw-series-4", "--bw-series-5", "--bw-series-6", "--bw-series-7", "--bw-series-8"]) {
      expect(tokens).toContain(token);
    }
    // The limiting reading-state token (§B.3; computed proofs in
    // series-colors.test.ts).
    expect(tokens).toContain("--bw-limiting");
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

  it("§E.1 pins the 11 component rows and their full cell content", () => {
    const rows = parseTable(
      "### §E.1 Components",
      ["Component", "Root element", "Required attributes", "Required roles", "Required class hooks", "Required text", "Notes"],
    );
    // Exact arity: a truncated collection (e.g. an interleaved non-pipe line
    // mid-table) reds here, not only downstream on id loss.
    expect(rows.length, "§E.1 exact row count").toBe(11);
    const ids = rows.map((row) => literal(row[0]!));
    for (const component of [
      "button",
      "numeric-input",
      "rotary-control",
      "reading-tile",
      "alert-bubble",
      "engineering-plot",
      "digital-lanes",
      "data-table",
      "panel",
      "mode-banner",
      "confirm-action",
    ]) {
      expect(ids).toContain(component);
    }
    // Load-bearing cell content (review fold row 1): every item of every
    // pinned column of every row, so a WEAKENED cell — an attribute, role,
    // class hook or required-text item dropped while the row stays — reds L1,
    // not just row removal. Full-content pin, matching how L1 pins every
    // other contract table. Additions stay legal (superset); the map updates
    // deliberately with the contract.
    const loadBearing: Record<string, { attributes: string[]; roles: string[]; classHooks: string[]; requiredText: string[] }> = {
      button: { attributes: ["data-variant", "aria-busy"], roles: ["button"], classHooks: ["bw-button"], requiredText: [] },
      "numeric-input": {
        attributes: ["type=number", "min", "max", "step", "aria-describedby", "for"],
        roles: [],
        classHooks: ["bw-numeric", "bw-numeric__label", "bw-numeric__field", "bw-numeric__unit", "bw-numeric__help"],
        requiredText: ["Staged value; use Apply to request the change"],
      },
      "rotary-control": {
        attributes: ["type=button", "aria-label", "aria-valuemin", "aria-valuemax", "aria-valuenow", "aria-valuetext~=staged"],
        roles: ["slider"],
        classHooks: ["bw-rotary", "bw-rotary__knob", "bw-rotary__value", "bw-rotary__state"],
        requiredText: ["Staged"],
      },
      "reading-tile": {
        attributes: ["data-severity", "aria-label", "data-bw-reading-state"],
        roles: ["region"],
        classHooks: ["bw-reading", "bw-reading__header", "bw-reading__severity", "bw-reading__value", "bw-reading__set", "bw-reading__state", "bw-reading__quality"],
        requiredText: ["steady · 2 s"],
      },
      "alert-bubble": {
        attributes: ["data-severity", "aria-label=Dismiss"],
        roles: ["status"],
        classHooks: ["bw-alert-bubble", "bw-alert-bubble__content"],
        requiredText: [],
      },
      "engineering-plot": {
        attributes: [
          "role=img",
          "aria-label",
          "aria-describedby",
          "aria-label=Traces",
          "aria-label~=(hidden by presentation preference)",
          "data-line",
          "data-bw-series-slot",
          "data-bw-trace-provenance",
          "data-bw-acquisition",
          "data-hidden",
        ],
        roles: ["img"],
        classHooks: ["bw-plot", "bw-plot__canvas", "bw-plot__legend", "bw-visually-hidden", "bw-plot__acquisition"],
        requiredText: ["hidden", "Acquired 100 samples · plotted 2"],
      },
      "data-table": {
        attributes: ["scope=col"],
        roles: ["table"],
        classHooks: ["bw-table-wrap", "bw-data-table"],
        requiredText: [],
      },
      panel: {
        attributes: ["data-surface", "aria-label"],
        roles: ["region"],
        classHooks: ["bw-panel", "bw-panel__header", "bw-panel__title", "bw-panel__body"],
        requiredText: [],
      },
      "mode-banner": {
        attributes: ["data-bw-mode-banner", "data-bw-mode", "aria-label=Presentation mode"],
        roles: ["region"],
        classHooks: ["bw-mode-banner", "bw-mode-banner__entry"],
        requiredText: [
          "SIMULATED PRESENTATION DATA",
          "NO GATEWAY · LOCAL PRESENTATION ONLY",
          "NO CONTROLLER LEASE · ACTIONS CANNOT BE AUTHORISED",
          "NO POLICY ENGINE · POLICY CHECKS UNAVAILABLE",
        ],
      },
      "confirm-action": {
        attributes: ["data-bw-confirm=armed", "aria-expanded"],
        roles: [],
        classHooks: ["bw-confirm", "bw-confirm__step", "bw-confirm__text"],
        requiredText: ["the output will be energised", "12.5 V", "PSU-07 output", "Confirm to proceed.", "Confirm: Energise output", "Cancel"],
      },
      "digital-lanes": {
        attributes: ["role=img", "aria-label", "aria-describedby", "data-bw-lane", "data-bw-lane-kind", "data-bw-state", "data-bw-glitch", "data-bw-trigger", "data-bw-cursor", "data-hidden"],
        roles: ["img"],
        classHooks: ["bw-lanes", "bw-lanes__canvas", "bw-lanes__lane", "bw-lanes__label", "bw-lanes__group", "bw-lanes__glitch", "bw-plot__acquisition"],
        requiredText: ["hidden", "Acquired 1000 samples · plotted 12 at 1 MHz"],
      },
    };
    // Same item split as the L2 parser: spaced " ~ " separator, "—" is empty.
    const items = (cell: string): string[] =>
      cell.replace(/^`/, "").replace(/`$/, "").split(" ~ ").map((item) => item.trim()).filter((item) => item !== "" && item !== "—");
    for (const [component, expected] of Object.entries(loadBearing)) {
      const row = rows.find((candidate) => literal(candidate[0]!) === component);
      if (row === undefined) throw new Error(`§E.1 row missing: ${component}`);
      for (const item of expected.attributes) {
        expect(items(row[2]!), `${component}: attribute cell must contain "${item}"`).toContain(item);
      }
      for (const role of expected.roles) {
        expect(items(row[3]!), `${component}: role cell must contain "${role}"`).toContain(role);
      }
      for (const hook of expected.classHooks) {
        expect(items(row[4]!), `${component}: class-hook cell must contain "${hook}"`).toContain(hook);
      }
      for (const text of expected.requiredText) {
        expect(items(row[5]!), `${component}: required-text cell must contain "${text}"`).toContain(text);
      }
    }
    // Every row must carry the full column set (no emptied cells except text/notes).
    for (const row of rows) {
      for (const column of [1, 2, 3, 4]) {
        expect(contractCell([row], 0, column), `${literal(row[0]!)} column ${column}`).not.toBe("");
      }
    }
  });

  it("§F.1 pins the 10 icon rows (6 severity + 4 state)", () => {
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
    expect(rows.length).toBe(10);
    expected.limiting = ["state", "ArrowUpToLine"];
    for (const row of rows) {
      const key = literal(row[0]!);
      const pair = expected[key];
      if (pair === undefined) throw new Error(`unexpected icon key: ${key}`);
      expect(literal(row[1]!), key).toBe(pair[0]);
      expect(literal(row[3]!), key).toBe(pair[1]);
      expect(contractCell([row], 0, 2), `${key} shape`).not.toBe("");
    }
  });

  it("§E.2.0 pins the four pass-2 composition rows", () => {
    const rows = parseTable("#### §E.2.0 Pass-2 composition (channel_hints)", ["Hint", "Effect"]);
    expect(rows.length).toBe(4);
    expect(literal(rows[0]![0]!)).toBe("color_role: \"accent\"");
    expect(literal(rows[1]![0]!)).toBe("color_role: \"muted\"");
    expect(literal(rows[2]![0]!)).toBe("visible: false");
    for (const row of rows) {
      expect(contractCell([row], 0, 1), `${literal(row[0]!)} effect`).not.toBe("");
    }
  });

  it("§E.2.1 pins the 16-row slot mapping exactly", () => {
    const rows = parseTable("#### §E.2.1 Slot mapping", ["Slot i", "Colour", "Dash", "Symbol"]);
    expect(rows.length).toBe(16);
    rows.forEach((row, i) => {
      expect(literal(row[0]!)).toBe(String(i));
      expect(literal(row[1]!), `slot ${i} colour`).toBe(`--bw-series-${i % 8 + 1}`);
      expect(literal(row[2]!), `slot ${i} dash`).toBe(`dash-${i < 8 ? 1 : 2}`);
      expect(literal(row[3]!), `slot ${i} symbol`).toBe(`symbol-${i % 8 + 1}`);
    });
  });

  it("§E.2.2 pins the two dash keys and the eight symbol shapes", () => {
    const rows = parseTable("#### §E.2.2 Sequences", ["Key", "Shape description", "Reference binding"]);
    expect(rows.length).toBe(10);
    expect(literal(rows[0]![0]!)).toBe("dash-1");
    expect(literal(rows[1]![0]!)).toBe("dash-2");
    for (let i = 0; i < 8; i += 1) {
      expect(literal(rows[i + 2]![0]!), `symbol row ${i}`).toBe(`symbol-${i + 1}`);
      expect(contractCell([rows[i + 2]!], 0, 1), `symbol-${i + 1} shape`).not.toBe("");
      expect(contractCell([rows[i + 2]!], 0, 2), `symbol-${i + 1} binding`).not.toBe("");
    }
  });

  it("§B.3 pins the reading-states table (1 row)", () => {
    const rows = parseTable("### §B.3 Reading states", ["State key", "Meaning", "Rendering", "Announcement"]);
    expect(rows.length).toBe(1);
    expect(literal(rows[0]![0]!)).toBe("limiting");
    for (const column of [1, 2, 3]) expect(contractCell([rows[0]!], 0, column), "limiting row").not.toBe("");
  });

  it("§B.4 pins the staleness rules (ST-1..4)", () => {
    const rows = parseTable("### §B.4 Staleness", ["Rule id", "Requirement"]);
    expect(rows.map((row) => literal(row[0]!))).toEqual(["ST-1", "ST-2", "ST-3", "ST-4"]);
    for (const row of rows) expect(contractCell([row], 0, 1), literal(row[0]!)).not.toBe("");
  });

  it("§E.3 pins the setpoint triad (measured/set/staged)", () => {
    const rows = parseTable("### §E.3 Setpoint presentation (reading-tile sub-rows)", ["Role", "Placement", "Required labelling", "Never"]);
    expect(rows.map((row) => literal(row[0]!))).toEqual(["measured", "set", "staged"]);
    for (const row of rows) for (const column of [1, 2, 3]) expect(contractCell([row], 0, column), literal(row[0]!)).not.toBe("");
  });

  it("§E.2.3 pins the y-axis assignment rows (4)", () => {
    const rows = parseTable("#### §E.2.3 Y-axis assignment", ["Condition", "Rendering"]);
    expect(rows.length).toBe(4);
    for (const row of rows) {
      expect(contractCell([row], 0, 0), "condition").not.toBe("");
      expect(contractCell([row], 0, 1), "rendering").not.toBe("");
    }
    expect(literal(rows[2]![0]!).startsWith("More than two")).toBe(true);
  });

  it("§E.2.4 pins the reference-line rows (4)", () => {
    const rows = parseTable("#### §E.2.4 Reference lines", ["Property", "Requirement"]);
    expect(rows.map((row) => literal(row[0]!))).toEqual(["Labelling", "Neutrality", "Distinctness", "Carrier"]);
    for (const row of rows) expect(contractCell([row], 0, 1), literal(row[0]!)).not.toBe("");
  });

  it("§E.2.5 pins the acquisition-disclosure rows (3)", () => {
    const rows = parseTable("#### §E.2.5 Acquisition disclosure", ["Property", "Requirement"]);
    expect(rows.map((row) => literal(row[0]!))).toEqual(["When required", "Placement", "Wording"]);
    for (const row of rows) expect(contractCell([row], 0, 1), literal(row[0]!)).not.toBe("");
  });

  it("§E.2.6 pins the four provenance kinds", () => {
    const rows = parseTable("#### §E.2.6 Trace provenance", ["Provenance", "Required marker", "Disclosure", "Constraint"]);
    expect(rows.map((row) => literal(row[0]!))).toEqual(["measured", "derived", "device-averaged", "display-processed"]);
    for (const row of rows) for (const column of [1, 2, 3]) expect(contractCell([row], 0, column), literal(row[0]!)).not.toBe("");
  });

  it("covers the §6 enumeration arithmetic (88 definition rows)", () => {
    const disabled = parseTable("### §C.2 Disabled-reason enum", ["Key", "Required label text", "Parameter"]).length;
    const refusal = parseTable("### §C.3 Refusal mapping", ["Code", "Severity", "What happened", "Sent status", "Operator action"]).length;
    const modes = parseTable("### §D.1 Modes", ["Mode", "Fixed wording", "Fires when"]).length;
    const safety = parseTable("### §C.1 Safety rules", ["Rule id", "Requirement"]).length;
    const stateRules = parseTable("### §B.2 State rules", ["Rule id", "Requirement"]).length;
    const severities = parseTable("### §B.1 Severities", ["Severity key", "Meaning", "Dismissal class", "Live region"]).length;
    const icons = parseTable("### §F.1 Icons", ["Icon key", "Class", "Shape description", "Reference binding"]).length;
    const readingStates = parseTable("### §B.3 Reading states", ["State key", "Meaning", "Rendering", "Announcement"]).length;
    const stalenessRules = parseTable("### §B.4 Staleness", ["Rule id", "Requirement"]).length;
    const triad = parseTable("### §E.3 Setpoint presentation (reading-tile sub-rows)", ["Role", "Placement", "Required labelling", "Never"]).length;
    const axes = parseTable("#### §E.2.3 Y-axis assignment", ["Condition", "Rendering"]).length;
    const refLines = parseTable("#### §E.2.4 Reference lines", ["Property", "Requirement"]).length;
    const acquisition = parseTable("#### §E.2.5 Acquisition disclosure", ["Property", "Requirement"]).length;
    const provenance = parseTable("#### §E.2.6 Trace provenance", ["Provenance", "Required marker", "Disclosure", "Constraint"]).length;
    const lanesLayout = parseTable("#### §E.4.1 Lane layout", ["Property", "Requirement"]).length;
    const lanesStates = parseTable("#### §E.4.2 State rendering", ["Property", "Requirement"]).length;
    const lanesBuses = parseTable("#### §E.4.3 Groups and buses", ["Property", "Requirement"]).length;
    const lanesDecimation = parseTable("#### §E.4.4 Edge-preserving decimation (NORMATIVE)", ["Property", "Requirement"]).length;
    const lanesAxis = parseTable("#### §E.4.5 Time axis", ["Property", "Requirement"]).length;
    // 5+15+4+3+3+6+10+1+4+3 = 54 (slice 1) + 4+4+3+4 = 15 (slice 2) = 69
    // (#243); + 4+4+4+3+4 = 19 (#244 S2 §E.4.1-4.5) = 88.
    expect(disabled + refusal + modes + safety + stateRules + severities + icons + readingStates + stalenessRules + triad + axes + refLines + acquisition + provenance + lanesLayout + lanesStates + lanesBuses + lanesDecimation + lanesAxis).toBe(88);
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
