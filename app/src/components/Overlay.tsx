import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { getEngineStatus, startVc, stopVc, setHot } from "../lib/engine";
import { listen } from "@tauri-apps/api/event";
import { currentVoice } from "../lib/voices";
import { displayVoiceName } from "../lib/voiceDisplay";
import { useI18n } from "../i18n";
import { playbackActive, playbackClock, type VoicePlaybackStatus } from "../lib/audioPlayback";

/**
 * 悬浮窗：变声状态与正在语音输出的音频。
 *
 * 用户开着游戏、在会议里、在直播，主窗口被挡住或者最小化了。这时需要看到
 * 麦克风状态、当前音色和语音音频的播放进度。托盘图标给不了这些信息，
 * 主窗口最小 880×640，太大。
 *
 * 参照的是 KOOK / TeamSpeak 的说话指示器，但只借行为不借布局 —— 那两个是频道
 * 成员列表，主语是「别人」；这里主语只有用户自己一个，摆成列表是照抄。
 *
 * 悬停时显示启停和原声切换；控件区域不参与窗口拖动。
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
  const [bypass, setBypass] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [audio, setAudio] = useState<VoicePlaybackStatus | null>(null);
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
      let audioPlaying = false;
      try {
        const s = await getEngineStatus();
        running = s.state === "running" || s.state === "vc";
        const lv = Number(s.meter_level ?? 0);
        const g = Number(s.threshold_meter ?? 0.25);
        const level = Number.isFinite(lv) ? Math.min(1, Math.max(0, lv)) : 0;
        const gate = Number.isFinite(g) ? g : 0.25;
        setLive(running);
        setBypass(s.function === "im");
        setLevel(level);
        setGate(gate);
        const now = Date.now();
        if (running && level >= gate) quietAt.current = now;
        setQuiet(now - quietAt.current > QUIET_MS);
      } catch {
        setLive(false);
      }
      try {
        const playback = await invoke<VoicePlaybackStatus>("audio_voice_status");
        audioPlaying = playbackActive(playback);
        if (!stop) setAudio(playback);
      } catch {
        if (!stop) setAudio(null);
      }
      if (stop) return;
      // 节奏跟着引擎走：跑着的时候要 10 Hz 电平条才像活的，停着的时候那个状态
      // 文件根本没人在写，一秒一次都算勤快。间隔从这一轮**刚读到**的状态算，
      // 不从 state —— state 要下一次渲染才更新，拿它定时会永远慢一拍。
      timer = window.setTimeout(tick, running || audioPlaying ? LIVE_MS : IDLE_MS);
    };

    void tick();
    return () => {
      stop = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const audioActive = playbackActive(audio);
  useEffect(() => {
    void invoke("overlay_audio_layout", { active: audioActive }).catch(() => {});
  }, [audioActive]);

  useEffect(() => {
    let stopped = false;
    let reading = false;
    let pending = false;
    let selectionKey = "";
    const refresh = async () => {
      if (stopped) return;
      if (reading) { pending = true; return; }
      reading = true;
      try {
        const c = await currentVoice();
        if (!stopped) setName(c.dsp_name || (c.model ? displayVoiceName(c.model as Record<string, unknown>) : ""));
      } catch { /* The engine may be restarting. */ }
      finally {
        reading = false;
        if (pending) { pending = false; void refresh(); }
      }
    };
    void refresh();
    const unlisten = [listen("voices-changed", () => void refresh()),
      listen<{ config?: Record<string, unknown> }>("config-changed", (ev) => {
        const cfg = ev.payload.config;
        if (!cfg) return;
        const key = JSON.stringify([cfg.pth_path, cfg.dsp_enabled, cfg.dsp_preset]);
        if (selectionKey !== key) { selectionKey = key; void refresh(); }
      })];
    return () => {
      stopped = true;
      for (const off of unlisten) void off.then((fn) => fn()).catch(() => {});
    };
  }, []);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try { await fn(); } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };

  const over = live && level >= gate;
  const label = name.trim() || t("overlay.noVoice");
  const audioProgress = audio && audio.length_frames > 0
    ? Math.min(1, audio.played_frames / audio.length_frames) : 0;
  const iconButtonClass =
    "inline-flex h-4 w-4 flex-none items-center justify-center p-0 text-[15px] leading-none";

  return (
    <div
      data-tauri-drag-region
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="h-screen w-screen select-none cursor-grab active:cursor-grabbing"
      style={{
        opacity: hover || audioActive || !quiet ? 1 : 0.45,
        transition: "opacity .18s var(--ease)",
      }}
    >
      <div
        data-tauri-drag-region
        className="flex h-full flex-col overflow-hidden rounded-[13px]"
        style={{ background: "rgba(16, 19, 24, 0.74)" }}
      >
        <div data-tauri-drag-region className="flex h-[52px] flex-none items-center gap-2.5 px-3">
          <span
            aria-hidden
            data-tauri-drag-region
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
              data-tauri-drag-region
              className="truncate text-[12.5px] font-semibold leading-tight"
              style={{ color: "#eef2f7" }}
              title={error || label}
            >
              {error || label}
            </div>
            {/* 电平条使用 transform，避免每次更新宽度时触发布局。 */}
            <div
              data-tauri-drag-region
              className="mt-1 h-[3px] overflow-hidden rounded-full"
              style={{ background: "rgba(238, 242, 247, 0.16)" }}
            >
              <div
                data-tauri-drag-region
                className="h-full origin-left rounded-full"
                style={{
                  transform: `scaleX(${live ? level : 0})`,
                  background: over ? "#3ddc84" : "#8b95a1",
                  transition: "transform .08s linear, background .12s linear",
                }}
              />
            </div>
          </div>
          <div className={`flex items-center gap-1 transition-opacity ${hover || busy ? "opacity-100" : "opacity-0 focus-within:opacity-100"}`} onPointerDown={(e) => e.stopPropagation()}>
            <button type="button" disabled={busy} title={t(live ? "dock.stop" : "dock.start")}
              aria-label={t(live ? "dock.stop" : "dock.start")}
              className={`${iconButtonClass} cursor-pointer border-0 bg-transparent text-white disabled:opacity-40`}
              onClick={() => void act(() => live ? stopVc() : startVc())}>{live ? "■" : "▷"}</button>
            <button type="button" disabled={busy || !live} title={t(bypass ? "dock.modeVc" : "dock.modeBypass")}
              aria-label={t(bypass ? "dock.modeVc" : "dock.modeBypass")}
              className={`${iconButtonClass} cursor-pointer border-0 bg-transparent text-white disabled:opacity-40`}
              onClick={() => void act(() => setHot({ function: bypass ? "vc" : "im" }))}>↔</button>
            <button type="button" aria-label={t("overlay.close")} title={t("overlay.close")}
              onClick={() => void getCurrentWindow().close()}
              className={`${iconButtonClass} cursor-pointer rounded-full border-0 bg-transparent`}
              style={{ color: "#9aa4b0" }}>×</button>
          </div>
        </div>
        {audioActive && audio ? <div data-tauri-drag-region
          className="flex h-[44px] flex-none items-center gap-2 border-t px-3"
          style={{ borderColor: "rgba(238, 242, 247, 0.14)" }}>
          <div data-tauri-drag-region className="min-w-0 flex-1" title={audio.name}>
            <div data-tauri-drag-region className="flex items-center gap-1.5 text-[11px] text-white">
              <span data-tauri-drag-region className="min-w-0 flex-1 truncate">{audio.name}</span>
              {audio.active_count > 1 ? <span data-tauri-drag-region className="flex-none text-[#b5bec9]"
                title={t("audio.morePlaying", { count: audio.active_count - 1 })}>+{audio.active_count - 1}</span> : null}
              <span data-tauri-drag-region className="flex-none tabular-nums text-[#b5bec9]">
                {playbackClock(audio.played_frames, audio.sample_rate)} / {playbackClock(audio.length_frames, audio.sample_rate)}
              </span>
            </div>
            <div data-tauri-drag-region className="mt-1 h-[3px] overflow-hidden rounded-full"
              role="progressbar" aria-label={audio.name} aria-valuemin={0} aria-valuemax={audio.length_frames}
              aria-valuenow={Math.min(audio.played_frames, audio.length_frames)}
              style={{ background: "rgba(238, 242, 247, 0.16)" }}>
              <div data-tauri-drag-region className="h-full origin-left rounded-full bg-[#b5bec9]"
                style={{ transform: `scaleX(${audioProgress})`, transition: "transform .1s linear" }} />
            </div>
          </div>
          <div className={`flex flex-none items-center gap-1 transition-opacity ${hover || busy ? "opacity-100" : "opacity-0 focus-within:opacity-100"}`}
            onPointerDown={(e) => e.stopPropagation()}>
            <button type="button" disabled={busy} aria-label={t(audio.state === "paused" ? "audio.resume" : "audio.pause")}
              title={t(audio.state === "paused" ? "audio.resume" : "audio.pause")}
              className={`${iconButtonClass} cursor-pointer border-0 bg-transparent text-white disabled:opacity-40`}
              onClick={() => void act(() => invoke<VoicePlaybackStatus>("audio_voice_pause", { paused: audio.state !== "paused", instanceId: audio.instance_id }).then(setAudio))}>
              {audio.state === "paused" ? "▷" : "Ⅱ"}
            </button>
            <button type="button" disabled={busy} aria-label={t("audio.stop")} title={t("audio.stop")}
              className={`${iconButtonClass} cursor-pointer border-0 bg-transparent text-white disabled:opacity-40`}
              onClick={() => void act(() => invoke<VoicePlaybackStatus>("audio_voice_stop_instance", { instanceId: audio.instance_id }).then(setAudio))}>■</button>
          </div>
        </div> : null}
      </div>
    </div>
  );
}
