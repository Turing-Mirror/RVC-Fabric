import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ToolWindow, toolFromHash } from "./components/ToolWindow";
import { applyAppearance } from "./lib/appearance";
import "./index.css";
import { invoke } from "@tauri-apps/api/core";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

// 主窗口和工具窗口（人声分离 / 训练音色 / 语音合成）用的是同一份前端，
// 靠地址后面的 `#/tool/<kind>` 分流。分不出来就是主窗口。
const tool = toolFromHash(window.location.hash);

// 工具窗口是另一个 webview，主窗口在 App 里做的那套外观设置它一点都不知道。
// 不在这儿补一次，用户设了深色 / 背景图之后，弹出来的工具窗还是浅色的。
if (tool) {
  void invoke<Record<string, unknown>>("config_get")
    .then(applyAppearance)
    .catch(() => {
      /* 浏览器预览里没有 shell */
    });
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ErrorBoundary>{tool ? <ToolWindow kind={tool} /> : <App />}</ErrorBoundary>
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
