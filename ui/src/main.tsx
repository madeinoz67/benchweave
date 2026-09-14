import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import "./styles/tokens.css";
import "./styles/themes.css";
import "./styles/globals.css";

const root = document.getElementById("root");

if (root === null) {
  throw new Error("BenchWeave UI root element is unavailable");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
