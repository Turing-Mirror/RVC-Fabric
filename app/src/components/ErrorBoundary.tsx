import { Component, type CSSProperties, type ErrorInfo, type ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import { t } from "../i18n/t";

type Props = { children: ReactNode };
type State = { error: Error | null; stack: string };

/**
 * Last line of defence against a blank window.
 *
 * The inline guard in index.html catches a bundle that never loads or never
 * runs. This catches the other half: a bundle that runs and then throws during
 * render, which React answers by unmounting the whole tree — leaving a page
 * that is blank for a completely different reason.
 *
 * Both paths write to shell.log, so a user report carries the cause either way.
 */
const ebBtn: CSSProperties = {
  fontSize: 13,
  padding: "6px 12px",
  borderRadius: 6,
  border: "1px solid var(--line, #cfd6dd)",
  background: "transparent",
  color: "var(--ink, #1e242b)",
  cursor: "pointer",
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, stack: "" };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // WebKit's `error.stack` omits the message, so a stack alone tells you
    // where but never what. Always lead with name + message.
    const head = `${error.name}: ${error.message}`;
    const stack = `${head}\n${error.stack ?? ""}\n${info.componentStack ?? ""}`;
    this.setState({ stack });
    // Fire-and-forget: if the shell is unreachable there is nothing better to
    // do, and throwing here would replace one blank screen with another.
    void invoke("ui_log", { line: t("s.1db2e283ac", { v0: stack }) }).catch(() => {});
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        style={{
          position: "fixed",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 10,
          padding: "0 56px",
          background: "var(--bg, #f4f6f8)",
          color: "var(--ink-muted, #5d6874)",
          userSelect: "text",
        }}
      >
        <div style={{ fontSize: 17, color: "var(--ink, #1e242b)" }}>{t("s.61f43bf584")}</div>
        <div>{t("s.d851b62cf4")}</div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            type="button"
            onClick={() => {
              void invoke("diagnostics_build", { withPerf: false }).catch(() => {});
            }}
            style={ebBtn}
          >
            {t("s.8b720e5330")}
          </button>
          <button
            type="button"
            onClick={() => {
              // close_action=ask 要靠已经卸掉的 App 弹窗，这里必须直接退。
              void invoke("close_finish", { toTray: false }).catch(() => {});
            }}
            style={ebBtn}
          >
            {t("window.close")}
          </button>
        </div>
        <pre
          style={{
            margin: 0,
            maxHeight: "46vh",
            overflow: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
            fontSize: 12,
            color: "var(--meta, #8a949e)",
          }}
        >
          {this.state.stack || String(this.state.error)}
        </pre>
      </div>
    );
  }
}
