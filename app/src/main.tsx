import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ToolWindow, toolFromHash } from "./components/ToolWindow";
import { Overlay } from "./components/Overlay";
import { I18nProvider } from "./i18n";
import { applyAppearance } from "./lib/appearance";
import "./index.css";
import { invoke } from "@tauri-apps/api/core";

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

// 右键一律不弹菜单。
//
// 这是个桌面软件，不是网页。WebView2 默认那套「重新加载 / 另存为图片 / 检查」
// 在这里没有一条是用户想要的，而它一弹出来就把「这其实是个浏览器」这件事写在
// 了脸上。
//
// 软件自己那些藏在右键里的功能（改名、删除、看作者主页）也一并取消了 ——
// 藏在右键里等于没做，绝大多数人根本不会去点。它们现在是模型卡片上「使用」
// 旁边那个「…」按钮，看得见才用得上。
//
// 输入框留着：那里的剪切 / 复制 / 粘贴是系统给的，删掉是纯粹的损失。
window.addEventListener("contextmenu", (e) => {
  const el = e.target as HTMLElement | null;
  if (el?.closest("input, textarea, [contenteditable='true']")) return;
  e.preventDefault();
});

// 主窗口和工具窗口（人声分离 / 训练音色 / 语音转换）用的是同一份前端，
// 靠地址后面的 `#/tool/<kind>` 分流。分不出来就是主窗口。
const tool = toolFromHash(window.location.hash);

// 悬浮窗也走同一份前端，但它不是工具窗：透明底、置顶、只显示状态。
const overlay = window.location.hash === "#/tool/overlay";

if (overlay) {
  // 这一条决定窗口是不是真的透明。html 平时带着不透明的 --bg（背景图那一层要
  // 有地方待，见 index.css 的注释），悬浮窗里那块底色会把「透明窗口」这件事
  // 直接作废 —— 用户看到的是一个纯色小方块盖在游戏上。
  document.documentElement.setAttribute("data-window", "overlay");
} else if (tool) {
  // 工具窗口是另一个 webview，主窗口在 App 里做的那套外观设置它一点都不知道。
  // 不在这儿补一次，用户设了深色 / 背景图之后，弹出来的工具窗还是浅色的。
  // 悬浮窗不参与：它是一块自带配色的深色药丸，跟着主题走反而会在浅色下变白，
  // 压到亮画面上就看不见了。
  void invoke<Record<string, unknown>>("config_get")
    .then(applyAppearance)
    .catch(() => {
      /* 浏览器预览里没有 shell */
    });
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <I18nProvider>
      <ErrorBoundary>
        {overlay ? <Overlay /> : tool ? <ToolWindow kind={tool} /> : <App />}
      </ErrorBoundary>
    </I18nProvider>
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
