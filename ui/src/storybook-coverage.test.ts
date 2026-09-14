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

  it("publishes the normative tokens and a portable light/dark mock-up", () => {
    const guide = readFileSync("../docs/internal/ui-styleguide.md", "utf8");
    const mockup = readFileSync("../docs/internal/ui-styleguide-mockup.html", "utf8");

    for (const section of [
      "### Colour palette",
      "### Spacing and layout",
      "### Radius, borders and elevation",
      "### Typography",
      "### Controls, icons and targets",
      "### Motion",
    ]) {
      expect(guide).toContain(section);
    }

    expect(mockup).toContain('aria-label="Light theme mock-up"');
    expect(mockup).toContain('aria-label="Dark theme mock-up"');
    expect(mockup).toContain('aria-label="Voltage and current waveform"');
  });
});
