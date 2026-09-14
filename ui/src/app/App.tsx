import { DeviceWorkbench } from "../compositions/DeviceWorkbench";
import { warningWorkbench } from "../compositions/fixtures";
import "./app.css";

export function App() {
  return (
    <main className="bw-app" data-theme="light">
      <p className="bw-simulation-banner">Simulated presentation data</p>
      <h1>BenchWeave UI workbench</h1>
      <DeviceWorkbench fixture={warningWorkbench} />
    </main>
  );
}
