import { useState } from "react";
import { Activity, Cable, Clock3, ShieldCheck } from "lucide-react";

import { Button } from "../components/actions/Button";
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
  requestEnabled?: boolean;
}

export function DeviceWorkbench({ fixture, onRequestSetPoint = () => undefined, requestEnabled = true }: DeviceWorkbenchProps) {
  const [stagedVoltage, setStagedVoltage] = useState(fixture.stagedVoltage);
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
      <AlertBubble severity="warning" title="Operating margin" message={fixture.message} source="PSU-01 · current" />

      <div className="bw-workbench__grid">
        <Panel title="Output set-point" eyebrow="Staged configuration">
          <div className="bw-setpoint">
            <RotaryControl label="Voltage set-point" value={stagedVoltage} unit="V" min={0} max={15} step={0.1} onStage={setStagedVoltage} />
            <div className="bw-setpoint__entry">
              <NumericInput label="Precise voltage" value={stagedVoltage} unit="V" min={0} max={15} step={0.1} onChange={setStagedVoltage} />
              <Button variant="primary" disabled={!requestEnabled} onClick={() => onRequestSetPoint(stagedVoltage)}>Apply staged set-point</Button>
              <small>Request remains subject to authority, policy and device verification.</small>
            </div>
          </div>
        </Panel>
        <Panel title="Output activity" eyebrow="Last 60 seconds" recessed>
          <EngineeringPlot kind="time_series" title="Output activity" x={{ label: "Receipt time", unit: "s" }} traces={fixture.traces} threshold={{ value: 1.9, label: "Current warning limit", severity: "warning" }} />
        </Panel>
      </div>

      <Panel title="Channels" eyebrow="Current gateway observations" recessed>
        <DataTable caption="Channel readings" rows={fixture.readings} rowKey={(row) => row.id} columns={[
          { id: "channel", header: "Quantity", cell: (row) => row.label },
          { id: "reading", header: "Reading", cell: (row) => `${row.value}${row.unit ? ` ${row.unit}` : ""}` },
          { id: "quality", header: "Quality", cell: (row) => `${row.quality} · ${row.freshness}` },
        ]} />
      </Panel>
      <footer className="bw-workbench__footer"><Activity size={15} aria-hidden="true" />Gateway observations only · no independent hardware safety claim</footer>
    </section>
  );
}
