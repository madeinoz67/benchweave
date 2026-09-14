import { readdirSync } from "node:fs";
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
});
