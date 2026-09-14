import { useEffect, useMemo, useState } from "react";
import { AlertBubble } from "../components/feedback/AlertBubble";
import { DeviceWorkbench } from "../compositions/DeviceWorkbench";
import { scenarioToWorkbenchFixture } from "../compositions/fixtures";
import { fetchPreview, requestSimulatedAction, type PreviewDocument, type SimulatedReceipt } from "./api";

export interface PreviewAppProps { apiBase?: string }

export function PreviewApp({ apiBase = "" }: PreviewAppProps) {
  const [preview, setPreview] = useState<PreviewDocument | null>(null);
  const [scenarioId, setScenarioId] = useState("");
  const [receipt, setReceipt] = useState<SimulatedReceipt | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchPreview(apiBase).then((loaded) => { if (!controller.signal.aborted) { setPreview(loaded); setScenarioId(loaded.scenarios[0]?.id ?? ""); } }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => controller.abort();
  }, [apiBase]);

  const scenario = preview?.scenarios.find((candidate) => candidate.id === scenarioId);
  const fixture = useMemo(() => preview && scenario ? scenarioToWorkbenchFixture(scenario, preview) : null, [preview, scenario]);
  const canRequest = Boolean(scenario?.permissions.includes("controller") && scenario.lease_state === "held" && scenario.approval_state !== "denied");

  if (error) return <main className="bw-preview"><AlertBubble severity="critical" title="Preview unavailable" message={error} source="SDK preview" /></main>;
  if (!preview || !scenario || !fixture) return <main className="bw-preview" aria-busy="true">Loading simulated preview…</main>;

  const requestSetPoint = async (value: number) => {
    const binding = scenario.observations.find((observation) => observation.unit === "V")?.binding_id ?? scenario.observations[0]?.binding_id;
    if (!binding) return;
    try { setReceipt(await requestSimulatedAction(apiBase, scenario.id, binding, value)); }
    catch (reason) { setReceipt({ binding_id: binding, outcome: "error", message: reason instanceof Error ? reason.message : String(reason) }); }
  };

  return <main className="bw-preview">
    <header className="bw-preview__header">
      <div><span className="bw-eyebrow">SDK preview · API v{preview.api_version}</span><h1>{preview.plugin_id}</h1></div>
      <strong className="bw-badge" data-tone="advisory">SIMULATED PRESENTATION DATA</strong>
      <label>Preview scenario<select value={scenario.id} onChange={(event) => { setScenarioId(event.target.value); setReceipt(null); }}>{preview.scenarios.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
    </header>
    <p>{scenario.title} · {scenario.description}</p>
    {scenario.unavailable_panels.length ? <AlertBubble severity="warning" title="Panels unavailable" message={scenario.unavailable_panels.join(", ")} source="SDK preview" /> : null}
    {receipt ? <AlertBubble severity={receipt.outcome === "accepted" ? "success" : "warning"} title={receipt.outcome === "accepted" ? "Simulated request accepted" : "Simulated request rejected"} message={receipt.message} source={receipt.binding_id} /> : null}
    {!canRequest ? <p role="status">Controls are read-only for this simulated authority state.</p> : null}
    <DeviceWorkbench key={scenario.id} fixture={fixture} requestEnabled={canRequest} onRequestSetPoint={requestSetPoint} />
  </main>;
}
