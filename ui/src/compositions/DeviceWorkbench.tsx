import { useState } from "react";
import { Activity, Cable, Clock3, ShieldCheck } from "lucide-react";

import { Button } from "../components/actions/Button";
import { ConfirmAction } from "../components/actions/ConfirmAction";
import type { DisabledReason } from "../components/actions/disabledReasons";
import { DataTable } from "../components/data/DataTable";
import { AlertBubble } from "../components/feedback/AlertBubble";
import { NumericInput } from "../components/inputs/NumericInput";
import { RotaryControl } from "../components/instruments/RotaryControl";
import { EngineeringPlot } from "../components/plots/EngineeringPlot";
import { ReadingTile } from "../components/readings/ReadingTile";
import { Panel } from "../components/surfaces/Panel";
import type { DeviceWorkbenchFixture } from "./fixtures";
import "./compositions.css";

export interface DeviceWorkbenchProps {
  fixture: DeviceWorkbenchFixture;
  onRequestSetPoint?(value: number): void;
  onRequestOutputOn?(value: number): void;
  onRequestOutputOff?(): void;
  requestEnabled?: boolean;
  /** A threshold is caller-supplied configuration, never a workbench default:
   *  the preview passes none (simulated snapshot data has no qualified limit),
   *  and the gateway demo supplies its own. */
  threshold?: { value: number; label: string; severity: "warning" | "critical" };
}

export function DeviceWorkbench({
  fixture,
  onRequestSetPoint = () => undefined,
  onRequestOutputOn = () => undefined,
  onRequestOutputOff = () => undefined,
  requestEnabled = true,
  threshold,
}: DeviceWorkbenchProps) {
  const [stagedVoltage, setStagedVoltage] = useState(fixture.stagedVoltage);
  const outputTarget = `${fixture.device.id.toUpperCase()} output`;
  // R-PROTECT-1: while a protective trip is active, energy-sourcing actions
  // are disabled with reason `protection-active` — the guard's reason wins
  // over the authority reason, because the trip is the present blocker.
  // R-DEENERGISE-1: the de-energise action carries NO guard at all — never
  // confirmed, never gated, whatever the trip or authority state.
  const energiseGuard: DisabledReason | undefined = fixture.output.trip
    ? { key: "protection-active" }
    : requestEnabled
      ? undefined
      : { key: "no-authority" };
  // R-ENERGISE-1: changing the set-point of a CURRENTLY-ENERGISED output is
  // energy-sourcing and takes the confirm step; on a de-energised output the
  // staged value is inert, so the apply is a single action.
  const setPointIsEnergising = fixture.output.energised;
  return (
    <section className="bw-workbench" aria-labelledby="device-workbench-title">
      <header className="bw-workbench__header">
        <div><span className="bw-eyebrow">Device overview</span><h2 id="device-workbench-title">{fixture.device.title} · {fixture.device.id.toUpperCase()}</h2></div>
        <div className="bw-status-cluster">
          {fixture.simulation ? <span className="bw-badge" data-tone="advisory">SIMULATED</span> : null}
          <span className="bw-badge" data-tone="success"><Cable size={14} aria-hidden="true" />{fixture.device.connected ? "Connected" : "Disconnected"}</span>
        </div>
      </header>

      <div className="bw-authority-strip">
        <span><ShieldCheck size={16} aria-hidden="true" />Controller lease</span>
        <strong>{fixture.lease.owner}</strong>
        <span><Clock3 size={16} aria-hidden="true" />Renews in {fixture.lease.expiresInSeconds} s</span>
      </div>

      <div className="bw-readings-grid">{fixture.readings.map((reading) => <ReadingTile key={reading.id} {...reading} />)}</div>
      <AlertBubble severity="warning" title="Operating margin" message={fixture.message} source={`${fixture.device.id.toUpperCase()} · current`} />

      <div className="bw-workbench__grid">
        <Panel title="Output control" eyebrow="Staged configuration">
          <div className="bw-setpoint">
            <RotaryControl label="Voltage set-point" value={stagedVoltage} unit="V" min={0} max={15} step={0.1} onStage={setStagedVoltage} />
            <div className="bw-setpoint__entry">
              <NumericInput label="Precise voltage" value={stagedVoltage} unit="V" min={0} max={15} step={0.1} onChange={setStagedVoltage} />
              {setPointIsEnergising ? (
                <ConfirmAction
                  label="Apply staged set-point"
                  effect="the set-point of the energised output will change"
                  value={{ amount: stagedVoltage, unit: "V" }}
                  target={outputTarget}
                  disabled={energiseGuard !== undefined}
                  disabledReason={energiseGuard}
                  onConfirm={() => onRequestSetPoint(stagedVoltage)}
                />
              ) : (
                <Button variant="primary" disabled={energiseGuard !== undefined} disabledReason={energiseGuard} onClick={() => onRequestSetPoint(stagedVoltage)}>Apply staged set-point</Button>
              )}
              <small>Request remains subject to authority, policy and device verification.</small>
            </div>
            <div className="bw-output-actions">
              <ConfirmAction
                label="Energise output"
                effect="the output will be energised"
                value={{ amount: stagedVoltage, unit: "V" }}
                target={outputTarget}
                disabled={energiseGuard !== undefined}
                disabledReason={energiseGuard}
                onConfirm={() => onRequestOutputOn(stagedVoltage)}
              />
              <Button variant="destructive" onClick={onRequestOutputOff}>De-energise output</Button>
            </div>
          </div>
        </Panel>
        <Panel title="Output activity" eyebrow="Last 60 seconds" recessed>
          <EngineeringPlot kind="time_series" title="Output activity" x={{ label: "Receipt time", unit: "s" }} traces={fixture.traces} threshold={threshold} />
        </Panel>
      </div>

      <Panel title="Channels" eyebrow="Current gateway observations" recessed>
        <DataTable caption="Channel readings" rows={fixture.readings} rowKey={(row) => row.id} columns={[
          { id: "channel", header: "Quantity", cell: (row) => row.label },
          { id: "reading", header: "Reading", cell: (row) => `${row.value}${row.unit ? ` ${row.unit}` : ""}` },
          { id: "quality", header: "Quality", cell: (row) => `${row.quality} · ${row.freshness}${row.stale ? " · stale" : ""}` },
        ]} rowAttributes={(row): Record<string, string> => (row.stale ? { "data-bw-stale": "true", className: "bw-table-row--stale" } : ({} as Record<string, string>))} />
      </Panel>
      <footer className="bw-workbench__footer"><Activity size={15} aria-hidden="true" />Gateway observations only · no independent hardware safety claim</footer>
    </section>
  );
}
