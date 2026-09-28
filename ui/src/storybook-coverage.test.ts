import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("Storybook catalogue", () => {
  it("contains every initial vertical-slice component group", () => {
    const stories = readdirSync("src", { recursive: true, encoding: "utf8" })
      .filter((path) => path.endsWith(".stories.tsx"))
      .join("\n");

    for (const group of [
      "components/surfaces",
      "components/actions",
      "components/inputs",
      "components/instruments",
      "components/feedback",
      "components/readings",
      "components/plots",
      "components/data",
      "compositions",
    ]) {
      expect(stories).toContain(group);
    }
  });

  it("publishes the normative contract and a portable light/dark mock-up", () => {
    const contract = readFileSync("../docs/internal/ui-contract.md", "utf8");
    const mockup = readFileSync("../docs/internal/ui-styleguide-mockup.html", "utf8");

    for (const section of [
      "## §A Tokens",
      "### §A.1 Colour palette",
      "### §A.2 Spacing and layout",
      "### §A.3 Radius",
      "### §A.4 Typography fonts",
      "## §B States and severity model",
      "### §B.1 Severities",
      "### §B.2 State rules",
      "## §C Safety rules (definition rows)",
      "### §C.1 Safety rules",
      "### §C.2 Disabled-reason enum",
      "### §C.3 Refusal mapping",
      "## §D Mode banner",
      "### §D.1 Modes",
      "## §E Per-component contracts",
      "### §E.1 Components",
      "## §F Icon set",
      "### §F.1 Icons",
    ]) {
      expect(contract).toContain(section);
    }

    expect(mockup).toContain('aria-label="Light theme mock-up"');
    expect(mockup).toContain('aria-label="Dark theme mock-up"');
    expect(mockup).toContain('aria-label="Voltage and current waveform"');
  });
});
