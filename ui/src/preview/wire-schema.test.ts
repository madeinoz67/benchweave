import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import schema from "../../../standards/plugin-ui-preview/0.1.0/preview-document.schema.json";
import { decodePreview } from "./api";

// The wire document is contract-first: this schema is the single source both
// sides are pinned to (the Python emitter validates against it in
// tests/sdk/test_preview_fixtures.py). These checks prove the TypeScript
// decoder agrees with the schema on valid and invalid documents alike.
const sample: unknown = {
  api_version: 1,
  plugin_id: "dev.example.plugin",
  renderer_version: "0.1.0",
  pages: [{ id: "readings", title: "Readings", kind: "readings", bindings: ["voltage"], required: true }],
  scenarios: [
    {
      id: "normal",
      title: "Normal",
      description: "Nominal simulated state",
      timestamp_strategy: "relative",
      observations: [
        {
          binding_id: "voltage",
          value: 12.5,
          unit: "V",
          quality: "simulated",
          freshness_ms: 0,
          provenance: "SDK generated baseline",
        },
      ],
      permissions: ["controller", "observer"],
      lease_state: "held",
      approval_state: "not_required",
      unavailable_panels: [],
      expected_severity: "neutral",
      request_outcomes: [
        { binding_id: "voltage", outcome: "permission_rejected", message: "Simulated permission rejection" },
      ],
      baseline: true,
    },
  ],
  simulation: true,
};

const compile = () => {
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  return ajv.compile(schema as object);
};

describe("preview wire schema conformance", () => {
  it("accepts a schema-valid document and the decoder accepts it too", () => {
    const validate = compile();
    expect(validate(sample)).toBe(true);
    const decoded = decodePreview(sample);
    expect(decoded.scenarios[0]?.expected_severity).toBe("neutral");
    expect(decoded.simulation).toBe(true);
  });

  it("rejects an unknown severity on both sides", () => {
    const validate = compile();
    const poisoned = structuredClone(sample) as { scenarios: Array<{ expected_severity: string }> };
    poisoned.scenarios[0].expected_severity = "catastrophic";
    expect(validate(poisoned)).toBe(false);
    expect(() => decodePreview(poisoned)).toThrow(/preview_invalid_severity/);
  });

  it("rejects a non-simulation document on both sides", () => {
    const validate = compile();
    const poisoned = structuredClone(sample) as { simulation: boolean };
    poisoned.simulation = false;
    expect(validate(poisoned)).toBe(false);
    expect(() => decodePreview(poisoned)).toThrow(/preview_invalid_document/);
  });
});
