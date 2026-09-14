import { describe, expect, it, vi } from "vitest";
import { decodePreview, fetchPreview, requestSimulatedAction } from "./api";

const scenario = { id: "normal", title: "Normal", description: "Nominal simulated state", timestamp_strategy: "fixed", observations: [{ binding_id: "voltage", value: 12.04, unit: "V", quality: "good", freshness_ms: 20, provenance: "synthetic" }], permissions: ["controller"], lease_state: "held", approval_state: "not_required", unavailable_panels: [], expected_severity: "neutral", request_outcomes: [], baseline: true };
const document = { api_version: 1, renderer_version: "1.0.0", simulation: true, plugin_id: "example.psu", pages: [], scenarios: [scenario] };

describe("preview API boundary", () => {
  it("decodes version one", () => expect(decodePreview(document).scenarios[0]?.observations[0]?.value).toBe(12.04));
  it("accepts the canonical advisory severity", () => expect(decodePreview({ ...document, scenarios: [{ ...scenario, expected_severity: "advisory" }] }).scenarios[0]?.expected_severity).toBe("advisory"));
  it("rejects incompatible versions", () => expect(() => decodePreview({ ...document, api_version: 2 })).toThrow(/preview_api_version/));
  it("rejects duplicate scenarios", () => expect(() => decodePreview({ ...document, scenarios: [scenario, scenario] })).toThrow(/preview_duplicate_scenario/));
  it("rejects non-finite observations", () => expect(() => decodePreview({ ...document, scenarios: [{ ...scenario, observations: [{ ...scenario.observations[0], value: Number.NaN }] }] })).toThrow(/preview_non_finite/));
  it("fetches no-store and posts simulated requests", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => document }).mockResolvedValueOnce({ ok: true, json: async () => ({ binding_id: "voltage", outcome: "accepted", message: "Simulated request accepted" }) });
    await fetchPreview("", fetcher);
    const receipt = await requestSimulatedAction("", "normal", "voltage", 12.5, fetcher);
    expect(fetcher).toHaveBeenNthCalledWith(1, "/api/v1/preview", expect.objectContaining({ cache: "no-store" }));
    expect(fetcher).toHaveBeenNthCalledWith(2, "/api/v1/scenarios/normal/requests", expect.objectContaining({ method: "POST" }));
    expect(receipt.message).toBe("Simulated request accepted");
  });
});
