import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "./index.css";
import { invoke } from "@tauri-apps/api/core";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);

// Tell the shell the UI actually painted. Without this the shell cannot
// distinguish "window is blank" from "window is fine but the user is looking
// at an empty page", and shell.log is what a bug report is built from.
requestAnimationFrame(() => {
  void invoke("ui_ready").catch(() => {});
});
