import type { Meta, StoryObj } from "@storybook/react-vite";

import type { PlotView, PreviewScenario } from "./api";
import { PreviewPlots } from "./PreviewPlots";

// A manifest-shaped panel: the views below are exactly what the SDK's
// plot_views projection emits for a readings page with a hinted time-series
// plot (issue #67). Values are honest single-point snapshots — the standing
// disclosure in the panel says so.
const hintedView: PlotView = {
  page_id: "readings",
  kind: "time_series",
  binding_id: "voltage",
  title: "Readings",
  x: { label: "time", unit: "s" },
  channels: [{ variable_id: "value", label: "value", unit: "V", color_role: "muted" }],
};

const unhintedView: PlotView = {
  page_id: "readings",
  kind: "time_series",
  binding_id: "voltage",
  title: "Readings",
  x: { label: "time", unit: "s" },
  channels: [{ variable_id: "value", label: "value", unit: "V" }],
};

const waveformView: PlotView = {
  page_id: "waveform",
  kind: "waveform",
  binding_id: "capture",
  title: "Waveform",
  x: { label: "time", unit: "s" },
  channels: [
    { variable_id: "trace01", label: "trace01", unit: "V" },
    { variable_id: "trace02", label: "trace02", unit: "V", color_role: "muted" },
  ],
};

const scenario: PreviewScenario = {
  id: "normal",
  title: "Normal",
  description: "Nominal simulated state",
  timestamp_strategy: "relative",
  observations: [
    { binding_id: "voltage", value: 12.5, unit: "V", quality: "simulated", freshness_ms: 0, provenance: "SDK generated baseline" },
  ],
  permissions: ["observer"],
  lease_state: "held",
  approval_state: "not_required",
  unavailable_panels: [],
  expected_severity: "neutral",
  request_outcomes: [],
  baseline: true,
};

const meta = {
  title: "Preview/Declared plots",
  component: PreviewPlots,
  args: { views: [hintedView, waveformView], scenario },
} satisfies Meta<typeof PreviewPlots>;
export default meta;
type Story = StoryObj<typeof meta>;

export const HintedManifestPlot: Story = { args: { views: [hintedView] } };
export const UnhintedManifestPlot: Story = { args: { views: [unhintedView] } };
export const WaveformWithoutPreviewData: Story = { args: { views: [waveformView] } };
export const PageWithBoth: Story = {};
