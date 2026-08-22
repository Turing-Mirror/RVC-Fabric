import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { QrDialog } from "./QrDialog";
import { openHelpSection } from "../lib/helpNav";
import { copyText } from "../lib/clipboard";
import qqGroup from "../assets/qq_group.jpg";
import { t } from "../i18n/t";

/**
 * 链路自检：把「听不到」从 dock 上的一句红字，变成一张逐项可核对的清单。
 *
 * 事实来自 Rust 的 link_check（毫秒级、只读）；判定在这里 —— 壳子报事实、
 * 界面出结论。状态标签沿用数据集体检那套**等宽文字**（通过/异常/提示），
 * 不用任何图形符号。
 *
 * 麦克风电平那一行是交互式的：点「检测麦克风」后请用户说几句话，
 * 复用设置页的 mic-test 通道，第一次越过 -45 dBFS 即通过并自动收麦。
 */
export type LinkCheckResult = {
  version: string;
  gpu: string;
  runtime_ready: boolean;
  engine_alive: boolean;
  engine_state: string;
  engine_error: string;
  vbcable_installed: boolean;
  cfg_input: string;
  cfg_output: string;
  default_output: string;
  input_devices: string[];
  output_devices: string[];
  diag_latest: string;
};

type Level = "ok" | "bad" | "info";
type Row = {
  id: string;
  title: string;
  level: Level;
  detail: string;
  actionLabel?: string;
  action?: () => void;
};

type MicState = "idle" | "running" | "ok" | "bad" | "info";

const HEARD_DB = -45;

export function LinkCheckDialog({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<LinkCheckResult | null>(null);
  const [err, setErr] = useState("");
  const [micState, setMicState] = useState<MicState>("idle");
  const [micNote, setMicNote] = useState("");
  const [copied, setCopied] = useState(false);
  const [qr, setQr] = useState(false);
  const micRunning = useRef(false);

  const load = async () => {
    setErr("");
    try {
      setData(await invoke<LinkCheckResult>("link_check"));
    } catch (e) {
      setErr(String(e));
    }
  };
  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // —— 麦克风检测：借设置页 mic-test 的事件通道 ——
  useEffect(() => {
    let un: (() => void) | undefined;
    let disposed = false;
    try {
      void listen<{ phase: string; peak?: number; message?: string }>(
        "mic-test",
        (ev) => {
          const p = ev.payload;
          if (p.phase === "level" && typeof p.peak === "number") {
            if (p.peak >= HEARD_DB && micRunning.current) {
              // 听见了：立刻收麦，别让用户多喊。
              micRunning.current = false;
              setMicState("ok");
              setMicNote(t("s.lcMicOk"));
              void invoke("mic_test_stop").catch(() => undefined);
            }
            return;
          }
          if (p.phase === "error") {
            micRunning.current = false;
            setMicState("bad");
            setMicNote(p.message || t("s.micErrOpen"));
          }
        },
      ).then((fn) => {
        if (disposed) fn();
        else un = fn;
      });
    } catch {
      /* 浏览器预览没有事件总线 */
    }
    return () => {
      disposed = true;
      un?.();
      if (micRunning.current) {
        micRunning.current = false;
        try {
          void invoke("mic_test_stop").catch(() => undefined);
        } catch {
          /* not in Tauri */
        }
      }
    };
  }, []);

  const startMic = () => {
    if (micRunning.current) return;
    micRunning.current = true;
    setMicState("running");
    setMicNote(t("s.lcMicAsking"));
    void invoke("mic_test_start").catch((e) => {
      micRunning.current = false;
      setMicState("info");
      setMicNote(String(e));
    });
    // 超时兜底：8 秒没听见就收麦并按「未检测到」处理。
    window.setTimeout(() => {
      if (!micRunning.current) return;
      micRunning.current = false;
      void invoke("mic_test_stop").catch(() => undefined);
      setMicState("bad");
      setMicNote(t("s.lcMicSilent"));
    }, 8000);
  };

  const rows: Row[] = [];
  if (data) {
    const out = data.cfg_output.trim();
    const inp = data.cfg_input.trim();
    const outLc = out.toLowerCase();
    const inpLc = inp.toLowerCase();

    rows.push({
      id: "runtime",
      title: t("s.lcRuntime"),
      level: data.runtime_ready ? "ok" : "bad",
      detail: data.runtime_ready ? t("s.lcRuntimeOk") : t("s.lcRuntimeBad"),
      actionLabel: data.runtime_ready ? undefined : t("s.lcSeeHelp"),
      action: () => openHelpSection("firstrun"),
    });

    rows.push({
      id: "cable",
      title: t("s.lcCable"),
      level: data.vbcable_installed ? "ok" : "bad",
      detail: data.vbcable_installed ? t("s.lcCableOk") : t("s.lcCableBad"),
      actionLabel: data.vbcable_installed ? undefined : t("s.lcSeeInstall"),
      action: () => openHelpSection("vbcable"),
    });

    if (!out) {
      rows.push({
        id: "output",
        title: t("s.lcOutput"),
        level: "bad",
        detail: t("s.lcOutputNone"),
        actionLabel: t("s.lcSeeWiring"),
        action: () => openHelpSection("wiring"),
      });
    } else if (outLc.includes("cable output")) {
      rows.push({
        id: "output",
        title: t("s.lcOutput"),
        level: "bad",
        detail: t("s.lcOutputReversed"),
        actionLabel: t("s.lcSeeWiring"),
        action: () => openHelpSection("wiring"),
      });
    } else if (outLc.includes("cable")) {
      rows.push({
        id: "output",
        title: t("s.lcOutput"),
        level: "ok",
        detail: t("s.lcOutputOk", { v0: out }),
      });
    } else {
      rows.push({
        id: "output",
        title: t("s.lcOutput"),
        level: "info",
        detail: t("s.lcOutputPhysical", { v0: out }),
        actionLabel: t("s.lcSeeWiring"),
        action: () => openHelpSection("wiring"),
      });
    }

    if (!inp) {
      rows.push({
        id: "input",
        title: t("s.lcInput"),
        level: "bad",
        detail: t("s.lcInputNone"),
        actionLabel: t("s.lcSeeWiring"),
        action: () => openHelpSection("wiring"),
      });
    } else if (inpLc.includes("cable")) {
      rows.push({
        id: "input",
        title: t("s.lcInput"),
        level: "bad",
        detail: t("s.lcInputWrong", { v0: inp }),
        actionLabel: t("s.lcSeeWiring"),
        action: () => openHelpSection("wiring"),
      });
    } else {
      rows.push({
        id: "input",
        title: t("s.lcInput"),
        level: "ok",
        detail: t("s.lcInputOk", { v0: inp }),
      });
    }

    if (!data.engine_alive || !data.default_output) {
      rows.push({
        id: "default",
        title: t("s.lcDefault"),
        level: "info",
        detail: t("s.lcDefaultUnknown"),
        actionLabel: t("s.lcOpenSound"),
        action: () => void invoke("open_sound_settings").catch(() => undefined),
      });
    } else if (data.default_output.toLowerCase().includes("cable")) {
      rows.push({
        id: "default",
        title: t("s.lcDefault"),
        level: "bad",
        detail: t("s.lcDefaultCable", { v0: data.default_output }),
        actionLabel: t("s.lcOpenSound"),
        action: () => void invoke("open_sound_settings").catch(() => undefined),
      });
    } else {
      rows.push({
        id: "default",
        title: t("s.lcDefault"),
        level: "ok",
        detail: t("s.lcDefaultOk", { v0: data.default_output }),
      });
    }
  }

  const hasBad = rows.some((r) => r.level === "bad") || micState === "bad";

  const helpText = async () => {
    let summary = "";
    try {
      summary = await invoke<string>("diagnostics_summary_text");
    } catch {
      /* 摘要拿不到就只发自检结果 */
    }
    const line = (r: Row) =>
      `  ${r.title}：${r.level === "ok" ? t("s.lcOk") : r.level === "bad" ? t("s.lcBad") : t("s.lcInfo")}`;
    const micLine =
      micState === "idle" || micState === "running"
        ? ""
        : `  ${t("s.lcMic")}：${
            micState === "ok"
              ? t("s.lcOk")
              : micState === "bad"
                ? t("s.lcBad")
                : t("s.lcInfo")
          }\n`;
    const text = [
      t("s.lcHelpTitle"),
      summary,
      t("s.lcHelpChecks"),
      ...rows.map(line),
      micLine.trimEnd(),
      data?.engine_error ? t("s.lcHelpError", { v0: data.engine_error }) : "",
      data?.diag_latest ? t("s.lcHelpDiag", { v0: data.diag_latest }) : "",
    ]
      .filter((s) => s && s.trim())
      .join("\n");
    await copyText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
    setQr(true);
  };

  const levelLabel = (l: Level) =>
    l === "ok" ? t("s.lcOk") : l === "bad" ? t("s.lcBad") : t("s.lcInfo");
  const levelClass = (l: Level) =>
    l === "ok"
      ? "text-[var(--accent)]"
      : l === "bad"
        ? "text-[#b8534f]"
        : "text-[var(--meta)]";

  return (
    <div
      className="fixed inset-0 z-[90] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[620px] max-h-[82vh] overflow-auto rounded-[var(--r)] bg-[var(--surface)] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 mb-4">
          <h3 className="m-0 text-[16px] font-semibold">{t("s.lcTitle")}</h3>
          <Btn onClick={onClose}>{t("s.6c14bd7f6f")}</Btn>
        </div>

        {err ? (
          <p className="m-0 mb-3 text-[12.5px] text-[#b8534f]">{err}</p>
        ) : null}

        {!data && !err ? (
          <p className="m-0 text-[12.5px] text-[var(--meta)]">{t("s.f950213ab7")}</p>
        ) : null}

        {rows.length ? (
          <div className="flex flex-col">
            {rows.map((r, i) => (
              <div
                key={r.id}
                className={[
                  "py-2.5",
                  i > 0 ? "border-t border-[var(--hairline)]" : "",
                ].join(" ")}
              >
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="font-mono text-[11px] shrink-0 w-[36px] text-right">
                    <span className={levelClass(r.level)}>{levelLabel(r.level)}</span>
                  </span>
                  <span className="text-[13.5px] font-medium">{r.title}</span>
                  {r.actionLabel && r.action ? (
                    <Btn onClick={r.action}>{r.actionLabel}</Btn>
                  ) : null}
                </div>
                <div className="mt-1 ml-[48px] text-[12.5px] text-[var(--ink-muted)] leading-relaxed">
                  {r.detail}
                </div>
              </div>
            ))}

            {/* 麦克风电平：交互检查行 */}
            <div className="py-2.5 border-t border-[var(--hairline)]">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="font-mono text-[11px] shrink-0 w-[36px] text-right">
                  <span
                    className={
                      micState === "ok"
                        ? "text-[var(--accent)]"
                        : micState === "bad"
                          ? "text-[#b8534f]"
                          : "text-[var(--meta)]"
                    }
                  >
                    {micState === "ok"
                      ? t("s.lcOk")
                      : micState === "bad"
                        ? t("s.lcBad")
                        : t("s.lcInfo")}
                  </span>
                </span>
                <span className="text-[13.5px] font-medium">{t("s.lcMic")}</span>
                {micState === "running" ? (
                  <Btn
                    onClick={() => {
                      micRunning.current = false;
                      void invoke("mic_test_stop").catch(() => undefined);
                      setMicState("idle");
                      setMicNote("");
                    }}
                  >
                    {t("s.44e681a374")}
                  </Btn>
                ) : data?.runtime_ready ? (
                  <Btn onClick={startMic}>{t("s.lcMicRun")}</Btn>
                ) : null}
              </div>
              <div className="mt-1 ml-[48px] text-[12.5px] text-[var(--ink-muted)] leading-relaxed">
                {micState === "idle" || micState === "running"
                  ? micNote || t("s.lcMicIdle")
                  : micNote}
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-4 pt-3 border-t border-[var(--hairline)] flex items-center gap-2.5 flex-wrap">
          <span className="text-[12px] text-[var(--meta)]">{t("s.lcHint")}</span>
          <div className="ml-auto flex items-center gap-2.5">
            <Btn onClick={() => void load()}>{t("s.38108eaa1d")}</Btn>
            {hasBad ? (
              <Btn primary onClick={() => void helpText()}>
                {copied ? t("s.errCopied") : t("s.lcHelpBtn")}
              </Btn>
            ) : null}
          </div>
        </div>
      </div>
      {qr ? (
        <QrDialog src={qqGroup} label={t("s.lcQrLabel")} onClose={() => setQr(false)} />
      ) : null}
    </div>
  );
}
