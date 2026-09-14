import { Button } from "../components/actions/Button";
import { DataTable } from "../components/data/DataTable";
import { AlertBubble } from "../components/feedback/AlertBubble";
import { Panel } from "../components/surfaces/Panel";
import type { AdminFixture } from "./fixtures";
import "./compositions.css";

export function AdminOverview({ fixture }: { fixture: AdminFixture }) {
  return (
    <section className="bw-workbench" aria-labelledby="admin-title">
      <header className="bw-workbench__header"><div><span className="bw-eyebrow">Platform governance</span><h2 id="admin-title">Administration</h2></div><Button variant="secondary">View audit log</Button></header>
      <AlertBubble severity="advisory" title="Pending independent approval" message={`${fixture.approvals.length} controlled change requires review before activation.`} source="Bench A configuration" />
      <div className="bw-workbench__grid">
        <Panel title="Admitted packages" eyebrow="Registry and local admission" recessed>
          <DataTable caption="Admitted plugin packages" rows={fixture.packages} rowKey={(row) => row.id} columns={[
            { id: "package", header: "Package", cell: (row) => row.id },
            { id: "revision", header: "Revision", cell: (row) => row.revision },
            { id: "status", header: "Status", cell: (row) => row.status },
          ]} />
        </Panel>
        <Panel title="Controlled changes" eyebrow="Approval boundary" recessed>
          <DataTable caption="Pending controlled changes" rows={fixture.approvals} rowKey={(row) => row.id} columns={[
            { id: "scope", header: "Scope", cell: (row) => row.scope },
            { id: "status", header: "Status", cell: (row) => row.status },
          ]} />
        </Panel>
      </div>
    </section>
  );
}
