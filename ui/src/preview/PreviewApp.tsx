import { useEffect, useMemo, useState } from "react";
import { AlertBubble } from "../components/feedback/AlertBubble";
import { ModeBanner } from "../components/feedback/ModeBanner";
import { RefusalMessage, type RefusalCode } from "../components/feedback/refusals";
import { DeviceWorkbench } from "../compositions/DeviceWorkbench";
import { scenarioToWorkbenchFixture } from "../compositions/fixtures";
import { fetchPreview, PreviewRefusalError, PreviewTransportError, requestSimulatedAction, type PreviewDocument, type SimulatedReceipt } from "./api";
import { PreviewPlots } from "./PreviewPlots";

export interface PreviewAppProps { apiBase?: string }

export function PreviewApp({ apiBase }: PreviewAppProps) {
  const resolvedApiBase = apiBase ?? new URLSearchParams(window.location.search).get("apiBase") ?? "";
  const [preview, setPreview] = useState<PreviewDocument | null>(null);
  const [scenarioId, setScenarioId] = useState("");
  const [receipt, setReceipt] = useState<SimulatedReceipt | null>(null);
  const [refusal, setRefusal] = useState<RefusalCode | null>(null);
  /** A definitive server refusal (readable error body — sent-NO territory). */
  const [serverRefusal, setServerRefusal] = useState<string | null>(null);
  /** The server answered but the receipt could not be read: the outcome is
   *  UNKNOWN (A06) — not "rejected", and not the no-response row either. */
  const [unknownOutcome, setUnknownOutcome] = useState(false);
  const [role, setRole] = useState("controller");
  const [theme, setTheme] = useState("dark");
  const [error, setError] = useState<Error | null>(null);

  const clearBoundary = () => { setReceipt(null); setRefusal(null); setServerRefusal(null); setUnknownOutcome(false); };

  useEffect(() => {
    const controller = new AbortController();
    fetchPreview(resolvedApiBase).then((loaded) => { if (!controller.signal.aborted) { setPreview(loaded); setScenarioId(loaded.scenarios[0]?.id ?? ""); } }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason : new Error(String(reason))); });
    return () => controller.abort();
  }, [resolvedApiBase]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const scenario = preview?.scenarios.find((candidate) => candidate.id === scenarioId);
  const fixture = useMemo(() => preview && scenario ? scenarioToWorkbenchFixture(scenario, preview) : null, [preview, scenario]);
  const canRequest = Boolean(
    (role === "controller" || role === "administrator")
    && scenario?.permissions.includes("controller")
    && scenario.lease_state === "held"
    && scenario.approval_state !== "denied"
    && scenario.request_outcomes.length > 0,
  );

  // The document boundary, honestly split: a network failure or undecodable
  // response is the contract's no-response refusal (nothing usable arrived —
  // UNKNOWN whether anything was sent, A06); a decode failure of an otherwise
  // accepted document keeps the plain critical alert (an answer arrived that
  // the client could not read — a client defect, not an interface refusal).
  if (error) return <main className="bw-preview">
    <ModeBanner modes={["simulated"]} />
    {error instanceof PreviewTransportError
      ? <RefusalMessage code="no-response" />
      : <AlertBubble severity="critical" title="Preview unavailable" message={error.message} source="SDK preview" />}
  </main>;
  if (!preview || !scenario || !fixture) return <main className="bw-preview" aria-busy="true"><ModeBanner modes={["simulated"]} />Loading simulated preview…</main>;

  const outputBinding = scenario.observations.find((observation) => observation.unit === "V")?.binding_id ?? scenario.observations[0]?.binding_id;
  const sendRequest = async (value: boolean | number) => {
    if (!outputBinding) return;
    clearBoundary();
    try { setReceipt(await requestSimulatedAction(resolvedApiBase, scenario.id, outputBinding, value)); }
    catch (reason: unknown) {
      if (reason instanceof PreviewTransportError) { setRefusal("no-response"); return; }
      if (reason instanceof PreviewRefusalError) { setServerRefusal(reason.message); return; }
      setUnknownOutcome(true);
    }
  };

  return <main className="bw-preview">
    <ModeBanner modes={["simulated"]} />
    <header className="bw-preview__header">
      <div><span className="bw-eyebrow">SDK preview · API v{preview.api_version}</span><h1>{preview.plugin_id}</h1></div>
      <label>Preview scenario<select value={scenario.id} onChange={(event) => { setScenarioId(event.target.value); clearBoundary(); }}>{preview.scenarios.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      <label>Simulated role<select value={role} onChange={(event) => { setRole(event.target.value); clearBoundary(); }}><option value="observer">Observer</option><option value="controller">Controller</option><option value="administrator">Administrator</option></select></label>
      <label>Preview theme<select value={theme} onChange={(event) => setTheme(event.target.value)}><option value="dark">Dark</option><option value="light">Light</option></select></label>
    </header>
    <p>{scenario.title} · {scenario.description}</p>
    {scenario.unavailable_panels.length ? <AlertBubble severity="warning" title="Panels unavailable" message={scenario.unavailable_panels.join(", ")} source="SDK preview" /> : null}
    {refusal ? <RefusalMessage code={refusal} /> : null}
    {serverRefusal ? <AlertBubble severity="warning" title="Request refused" message={`${serverRefusal} Nothing was sent.`} source="SDK preview" /> : null}
    {unknownOutcome ? <AlertBubble severity="warning" title="Request outcome unknown" message="The server answered but the receipt could not be read; whether anything was sent is unknown — reconcile before retrying." source="SDK preview" /> : null}
    {receipt ? <AlertBubble severity={receipt.outcome === "accepted" ? "success" : "warning"} title={receipt.outcome === "accepted" ? "Simulated request accepted" : "Simulated request rejected"} message={receipt.message} source={receipt.binding_id} /> : null}
    {!canRequest ? <p role="status">Energy-sourcing controls are read-only for this simulated authority state; de-energising stays available.</p> : null}
    <DeviceWorkbench
      key={scenario.id}
      fixture={fixture}
      requestEnabled={canRequest}
      onRequestSetPoint={(value) => { void sendRequest(value); }}
      onRequestOutputOn={() => { void sendRequest(true); }}
      onRequestOutputOff={() => { void sendRequest(false); }}
    />
    <PreviewPlots views={preview.plot_views} scenario={scenario} />
  </main>;
}
