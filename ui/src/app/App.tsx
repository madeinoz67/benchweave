import { useState } from "react";
import { Moon, Sun } from "lucide-react";

import { Button } from "../components/actions/Button";
import { DeviceWorkbench } from "../compositions/DeviceWorkbench";
import { warningWorkbench } from "../compositions/fixtures";
import "./app.css";

export function App() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = window.localStorage?.getItem("benchweave-theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  const nextTheme = theme === "light" ? "dark" : "light";
  const switchTheme = () => {
    window.localStorage?.setItem("benchweave-theme", nextTheme);
    setTheme(nextTheme);
  };

  return (
    <main className="bw-app" data-theme={theme}>
      <div className="bw-app__toolbar">
        <p className="bw-simulation-banner">Simulated presentation data</p>
        <Button variant="tertiary" onClick={switchTheme} aria-label={`Use ${nextTheme} theme`}>
          {theme === "light" ? <Moon size={17} aria-hidden="true" /> : <Sun size={17} aria-hidden="true" />}
          {nextTheme === "dark" ? "Dark" : "Light"}
        </Button>
      </div>
      <h1>BenchWeave UI workbench</h1>
      {/* The standalone demo keeps its illustrative limit; the preview passes
          none — a threshold is caller-supplied configuration, never a default. */}
      <DeviceWorkbench fixture={warningWorkbench} threshold={{ value: 1.9, label: "Current warning limit", severity: "warning" }} />
    </main>
  );
}
