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

// Tell the shell the UI came up. Without this the shell cannot distinguish
// "window is blank" from "window is fine but the user is looking at an empty
// page", and shell.log is what a bug report is built from.
//
// rAF alone was not enough: a webview whose window is occluded, minimised or
// started to tray may never get a frame, and the shell then logged a 白屏
// warning about a UI that was in fact running. The timer is the floor.
let told = false;
const tellShell = () => {
  if (told) return;
  told = true;
  void invoke("ui_ready").catch(() => {});
};
requestAnimationFrame(tellShell);
setTimeout(tellShell, 1500);
