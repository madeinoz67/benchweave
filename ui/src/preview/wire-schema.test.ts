import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import schema from "../../../standards/plugin-ui-preview/0.1.1/preview-document.schema.json";
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
  plot_views: [
    {
      page_id: "readings",
      kind: "time_series",
      binding_id: "voltage",
      title: "Readings",
      x: { label: "time", unit: "s" },
      channels: [
        { variable_id: "value", label: "value", unit: "V", color_role: "muted" },
      ],
    },
  ],
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

  it("decodes plot_views with hints intact and keeps the field optional", () => {
    const validate = compile();
    expect(validate(sample)).toBe(true);
    const decoded = decodePreview(sample);
    expect(decoded.plot_views).toHaveLength(1);
    expect(decoded.plot_views[0]).toEqual({
      page_id: "readings",
      kind: "time_series",
      binding_id: "voltage",
      title: "Readings",
      x: { label: "time", unit: "s" },
      channels: [{ variable_id: "value", label: "value", unit: "V", color_role: "muted" }],
    });
    // Optional at root: a document without plot_views stays valid and decodes
    // to an empty list (older documents mean "no plots").
    const bare = structuredClone(sample) as { plot_views?: unknown };
    delete bare.plot_views;
    expect(validate(bare)).toBe(true);
    expect(decodePreview(bare).plot_views).toEqual([]);
  });

  it("rejects a poisoned plot_views color_role on both sides", () => {
    const validate = compile();
    const poisoned = structuredClone(sample) as { plot_views: Array<{ channels: Array<{ color_role: string }> }> };
    poisoned.plot_views[0].channels[0].color_role = "critical";
    expect(validate(poisoned)).toBe(false);
    expect(() => decodePreview(poisoned)).toThrow(/preview_invalid_plot_channel/);
  });

  it("rejects an extra channel key on both sides", () => {
    const validate = compile();
    const poisoned = structuredClone(sample) as { plot_views: Array<{ channels: Array<Record<string, unknown>> }> };
    poisoned.plot_views[0].channels[0] = {
      variable_id: "value",
      label: "value",
      unit: "V",
      threshold: 3.3,
    };
    expect(validate(poisoned)).toBe(false);
    expect(() => decodePreview(poisoned)).toThrow(/preview_invalid_plot_channel/);
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
