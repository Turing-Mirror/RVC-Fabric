import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn, HelpMark } from "./ui";
import { t } from "../i18n/t";

type MicEvent = {
  phase: "start" | "level" | "done" | "error";
  /** 峰值 dBFS。-90 = 一片安静。 */
  peak?: number;
  sec?: number;
  message?: string;
};

/** 电平条的下限。低于这个的一律画成空条 —— 再往下都是底噪，画出来只会晃。 */
const FLOOR_DB = -60;

function barPercent(db: number | undefined): number {
  if (db === undefined || !Number.isFinite(db)) return 0;
  const clamped = Math.max(FLOOR_DB, Math.min(0, db));
  return Math.round(((clamped - FLOOR_DB) / -FLOOR_DB) * 100);
}

/**
 * 麦克风测试。
 *
 * 在这之前，验证「输入设备选对了没有」的唯一办法是把整个引擎起起来对着麦说话。
 * 引擎冷启动要二三十秒，失败原因又有十几种 —— 用户分不清是麦的问题还是引擎的
 * 问题，只能反复重试。这里直接开设备读电平：不起引擎、不占 GPU、不留录音。
 *
 * 排版沿用设备卡里那几行的样式，不引入新的视觉元素。
 */
export function MicTest({ deviceReady }: { deviceReady: boolean }) {
  const [busy, setBusy] = useState(false);
  const [peak, setPeak] = useState<number | undefined>(undefined);
  const [msg, setMsg] = useState("");
  const [bad, setBad] = useState(false);
  // 事件回调里要读「现在还在测吗」，用 ref —— 闭包里的 state 是订阅那一刻的值。
  const running = useRef(false);

  useEffect(() => {
    let disposed = false;
    let un: (() => void) | undefined;
    // 浏览器预览里没有 `window.__TAURI_INTERNALS__`，listen 是**同步抛**的，
    // 挂在后面的 .catch() 根本轮不到 —— 异常一路冒到 ErrorBoundary，整个设置页
    // 变成一行红字。跟 SettingsPage 里 safeInvoke 那段注释是同一个坑。
    try {
      void listen<MicEvent>("mic-test", (ev) => {
        const p = ev.payload;
        if (p.phase === "level") {
          setPeak(p.peak);
          return;
        }
        if (p.phase === "start") {
          setPeak(undefined);
          if (p.message) setMsg(p.message);
          return;
        }
        // done / error：测试结束，把结论留在原地，不清空。
        running.current = false;
        setBusy(false);
        setPeak(undefined);
        setBad(p.phase === "error");
        if (p.message) setMsg(p.message);
      })
        .then((fn) => {
          if (disposed) fn();
          else un = fn;
        })
        .catch(() => {
          /* 事件总线不在 */
        });
    } catch {
      /* 浏览器预览：没有 shell，就没有电平可听 */
    }
    return () => {
      disposed = true;
      un?.();
      // 组件卸载（换标签页 / 换页）时把麦收回去。留着的话用户离开设置页之后
      // 麦还开着，指示灯亮了半分钟才自己灭，看着像软件在偷听。
      if (running.current) {
        running.current = false;
        try {
          void invoke("mic_test_stop").catch(() => undefined);
        } catch {
          /* not in Tauri */
        }
      }
    };
  }, []);

  const start = () => {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setBad(false);
    setPeak(undefined);
    setMsg(t("s.micTestOpening"));
    try {
      void invoke("mic_test_start").catch((e) => {
        // 命令本身失败（起不来 worker、Runtime 缺失）走这里；设备层面的失败
        // 是 error 事件。两条路都得把状态收回来，否则按钮永远停在「停止」。
        running.current = false;
        setBusy(false);
        setBad(true);
        setMsg(String(e));
      });
    } catch (e) {
      running.current = false;
      setBusy(false);
      setBad(true);
      setMsg(String(e));
    }
  };

  const stop = () => {
    try {
      void invoke("mic_test_stop").catch(() => undefined);
    } catch {
      /* not in Tauri */
    }
  };

  return (
    <div className="flex items-start gap-3 flex-wrap">
      <span className="w-[108px] shrink-0 text-[13px] leading-tight flex items-center gap-[9px] pt-1">
        <span>{t("s.micTest")}</span>
        <HelpMark title={t("s.micTestDesc")} />
      </span>
      <div className="flex-1 min-w-[220px]">
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="relative h-1.5 w-[140px] shrink-0 overflow-hidden rounded-sm bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
            <div
              className="absolute inset-y-0 left-0 rounded-sm bg-[var(--accent)] transition-[width] duration-75"
              style={{ width: `${busy ? barPercent(peak) : 0}%` }}
            />
          </div>
          {busy ? (
            <Btn onClick={stop}>{t("s.micTestStop")}</Btn>
          ) : (
            <Btn onClick={start} disabled={!deviceReady}>
              {t("s.micTestStart")}
            </Btn>
          )}
        </div>
        {msg ? (
          <p
            className={[
              "m-0 mt-1.5 text-[12.5px] leading-relaxed whitespace-pre-line",
              bad ? "text-[#b8534f]" : "text-[var(--help)]",
            ].join(" ")}
          >
            {msg}
          </p>
        ) : null}
      </div>
    </div>
  );
}
