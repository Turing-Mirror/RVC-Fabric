import { useEffect, useRef, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { getEngineStatus } from "../lib/engine";
import { currentVoice } from "../lib/voices";
import { displayVoiceName } from "../lib/voiceDisplay";
import { useI18n } from "../i18n";

/**
 * 悬浮窗：麦克风电平 + 当前音色名。
 *
 * 用户开着游戏、在会议里、在直播，主窗口被挡住或者最小化了。这时候他需要知道的
 * 只有两件事：**麦有没有进声音**、**用的是哪个音色**。托盘图标给不了这两样，
 * 主窗口最小 880×640，太大。
 *
 * 参照的是 KOOK / TeamSpeak 的说话指示器，但只借行为不借布局 —— 那两个是频道
 * 成员列表，主语是「别人」；这里主语只有用户自己一个，摆成列表是照抄。
 *
 * **一个功能按钮都不放。** 在游戏里误点一下换音色要停流重开，声音当场断一两秒。
 * 唯一的按钮是关闭，而且悬停才出现：这扇窗没有任务栏图标也没有标题栏，不给关闭
 * 就真的关不掉了。
 *
 * 底不是透明的，是一块深色药丸。窗口本身透明，药丸负责让白字在任何画面上都读得
 * 出来 —— 直接把字放在全透明的窗上，压到浅色画面就没了。
 */
/** 引擎跑着时的轮询间隔。worker 每 80ms 写一次状态，10 Hz 刚好跟得上。 */
const LIVE_MS = 100;
/** 引擎停着时的间隔。那份状态文件此刻没人在写，读快了纯属空转。 */
const IDLE_MS = 1000;
/** 低于门限持续这么久就整体变淡。 */
const QUIET_MS = 2500;

export function Overlay() {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [level, setLevel] = useState(0);
  const [gate, setGate] = useState(0.25);
  const [live, setLive] = useState(false);
  const [hover, setHover] = useState(false);
  // 安静一段时间就整体变淡。一个一直保持全亮的置顶方块压在游戏画面上很烦，
  // 而说话的那一刻它必须立刻亮回来 —— 淡的是不透明度，不是内容。
  const [quiet, setQuiet] = useState(true);
  const quietAt = useRef(0);

  useEffect(() => {
    let stop = false;
    let timer = 0;

    const tick = async () => {
      if (stop) return;
      let running = false;
      try {
        const s = await getEngineStatus();
        running = s.state === "running" || s.state === "vc";
        const lv = Number(s.meter_level ?? 0);
        const g = Number(s.threshold_meter ?? 0.25);
        const level = Number.isFinite(lv) ? Math.min(1, Math.max(0, lv)) : 0;
        const gate = Number.isFinite(g) ? g : 0.25;
        setLive(running);
        setLevel(level);
        setGate(gate);
        const now = Date.now();
        if (running && level >= gate) quietAt.current = now;
        setQuiet(now - quietAt.current > QUIET_MS);
      } catch {
        setLive(false);
      }
      if (stop) return;
      // 节奏跟着引擎走：跑着的时候要 10 Hz 电平条才像活的，停着的时候那个状态
      // 文件根本没人在写，一秒一次都算勤快。间隔从这一轮**刚读到**的状态算，
      // 不从 state —— state 要下一次渲染才更新，拿它定时会永远慢一拍。
      timer = window.setTimeout(tick, running ? LIVE_MS : IDLE_MS);
    };

    void tick();
    return () => {
      stop = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    void currentVoice()
      .then((c) => {
        if (c.model) setName(displayVoiceName(c.model as Record<string, unknown>));
      })
      .catch(() => {});
  }, []);

  const over = live && level >= gate;
  const label = name.trim() || t("overlay.noVoice");

  return (
    <div
      data-tauri-drag-region
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="h-screen w-screen select-none cursor-grab active:cursor-grabbing"
      style={{
        opacity: hover || !quiet ? 1 : 0.45,
        transition: "opacity .18s var(--ease)",
      }}
    >
      <div
        data-tauri-drag-region
        className="flex h-full items-center gap-2.5 rounded-[13px] px-3"
        style={{ background: "rgba(16, 19, 24, 0.74)" }}
      >
        <span
          aria-hidden
          className="flex-none rounded-full"
          style={{
            width: 9,
            height: 9,
            background: over ? "#3ddc84" : live ? "#6c7784" : "#4a525c",
            boxShadow: over ? "0 0 0 3px rgba(61, 220, 132, 0.22)" : "none",
            transition: "background .12s linear, box-shadow .12s linear",
          }}
        />
        <div data-tauri-drag-region className="min-w-0 flex-1">
          <div
            className="truncate text-[12.5px] font-semibold leading-tight"
            style={{ color: "#eef2f7" }}
            title={label}
          >
            {label}
          </div>
          {/* 电平条。宽度用 transform 画，不用 width —— 每秒十次改 width 会
              一直触发布局，改 transform 只在合成器里走。 */}
          <div
            className="mt-1 h-[3px] overflow-hidden rounded-full"
            style={{ background: "rgba(238, 242, 247, 0.16)" }}
          >
            <div
              className="h-full origin-left rounded-full"
              style={{
                transform: `scaleX(${live ? level : 0})`,
                background: over ? "#3ddc84" : "#8b95a1",
                transition: "transform .08s linear, background .12s linear",
              }}
            />
          </div>
        </div>
        {hover ? (
          <button
            type="button"
            aria-label={t("overlay.close")}
            title={t("overlay.close")}
            onClick={() => void getCurrentWindow().close()}
            className="flex-none cursor-pointer rounded-full border-0 bg-transparent p-0 text-[15px] leading-none"
            style={{ color: "#9aa4b0", width: 16, height: 16 }}
          >
            ×
          </button>
        ) : null}
      </div>
    </div>
  );
}
