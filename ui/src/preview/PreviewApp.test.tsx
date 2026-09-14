import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PreviewApp } from "./PreviewApp";

vi.mock("echarts/core", () => ({ init: () => ({ setOption: () => undefined, resize: () => undefined, dispose: () => undefined }), use: () => undefined }));

const observation = { binding_id: "voltage", value: 12.04, unit: "V", quality: "good", freshness_ms: 84, provenance: "synthetic" };
const normal = { id: "normal", title: "Normal", description: "Nominal simulated state", timestamp_strategy: "fixed", observations: [observation], permissions: ["controller"], lease_state: "held", approval_state: "not_required", unavailable_panels: [], expected_severity: "success", request_outcomes: [{ binding_id: "voltage", outcome: "accepted", message: "Simulated request accepted" }], baseline: true };
const trip = { ...normal, id: "trip", title: "Protective trip", description: "Simulated protective trip", permissions: [], lease_state: "none", expected_severity: "trip" };
const preview = { api_version: 1, plugin_id: "example.psu", renderer_version: "1.0.0", pages: [], scenarios: [normal, trip], simulation: true };

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("PreviewApp", () => {
  it("uses the development renderer API base from the page query", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => preview });
    vi.stubGlobal("fetch", fetcher);
    window.history.replaceState({}, "", "/?apiBase=http%3A%2F%2F127.0.0.1%3A49152");

    render(<PreviewApp />);

    await screen.findByText("SIMULATED PRESENTATION DATA");
    expect(fetcher).toHaveBeenCalledWith("http://127.0.0.1:49152/api/v1/preview", expect.any(Object));
  });

  it("keeps simulation labelling across scenario selection", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => preview }));
    render(<PreviewApp />);
    expect(await screen.findByText("SIMULATED PRESENTATION DATA")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Preview scenario"), { target: { value: "trip" } });
    expect(screen.getByText("Protective trip · Simulated protective trip")).toBeVisible();
    expect(screen.getByText("SIMULATED PRESENTATION DATA")).toBeVisible();
    expect(screen.getByText(/Controls are read-only/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Apply staged set-point" })).toBeDisabled();
  });

  it("switches host theme and gates controls by simulated role", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => preview }));
    render(<PreviewApp />);
    await screen.findByText("SIMULATED PRESENTATION DATA");
    fireEvent.change(screen.getByLabelText("Preview theme"), { target: { value: "light" } });
    expect(document.documentElement.dataset.theme).toBe("light");
    fireEvent.change(screen.getByLabelText("Simulated role"), { target: { value: "observer" } });
    expect(screen.getByRole("button", { name: "Apply staged set-point" })).toBeDisabled();
  });

  it("shows a simulated receipt without changing the observation", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => preview }).mockResolvedValueOnce({ ok: true, json: async () => ({ binding_id: "voltage", outcome: "accepted", message: "Simulated request accepted" }) });
    vi.stubGlobal("fetch", fetcher);
    render(<PreviewApp />);
    expect((await screen.findAllByText("12.04"))[0]).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Apply staged set-point" }));
    await waitFor(() => expect(screen.getAllByText("Simulated request accepted").length).toBeGreaterThan(0));
    expect(screen.getAllByText("12.04").length).toBeGreaterThan(0);
  });
});
