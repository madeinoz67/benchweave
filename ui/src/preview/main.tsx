import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { PreviewApp } from "./PreviewApp";
import "../styles/tokens.css";
import "../styles/themes.css";
import "../styles/globals.css";
import "../app/app.css";

const root = document.getElementById("root");
if (root === null) throw new Error("BenchWeave preview root element is unavailable");
createRoot(root).render(<StrictMode><PreviewApp /></StrictMode>);
