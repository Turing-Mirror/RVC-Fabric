import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  ensureEngine,
  getEngineStatus,
  getProvisionStatus,
  isLoadPhase,
  listDevices,
  loadProgress,
  setHot,
  startVc,
  statusSub,
  statusTitle,
  stopVc,
  type EngineStatus,
  type ProvisionStatus,
} from "../lib/engine";
import type { OutputMode } from "../components/Dock";
import { getConfig } from "../lib/config";
import { t } from "../i18n/t";

export function useEngine() {
  const [status, setStatus] = useState<EngineStatus>({});
  const [provision, setProvision] = useState<ProvisionStatus>({});
  const [busy, setBusy] = useState(false);
  // Read by the adaptive poll without making it a dependency.
  const stateRef = useRef<string>("idle");
  const [lastError, setLastError] = useState("");
  // What the next start will send. Seeded from the saved config via
  // `syncParams`, not guessed: these used to default to 15 / 1.2 and were only
  // ever written when the user dragged a slider, so a first 开启变声 pushed a
  // +15 semitone shift while the dock read +0 — and overwrote the parameters
  // the selected voice's own profile had just applied. 0 / 0 is the neutral
  // value, so a missed sync is now a no-op instead of a surprise.
  const pitchRef = useRef(0);
  const formantRef = useRef(0);
  const modeRef = useRef<OutputMode>("vc");
  const hotTimer = useRef<number | null>(null);
  const startingRef = useRef(false);
  // 用户**亲手**按下「开启变声」的次数。
  //
  // `starting` 不能当这个用：开机预热引擎、导入推理库的时候后端一样会报
  // starting，界面上没人按过任何东西。首次引导挂在 starting 上，结果软件一
  // 启动就弹出来了 —— 用户报的就是这个。这个计数只在 toggleRun 真的走开启
  // 分支时才加，托盘和快捷键也走同一条路，所以它们也算数。
  const [userStarts, setUserStarts] = useState(0);
  const [swapHint, setSwapHint] = useState(false);
  const progressRef = useRef<number | null>(null);

  // 运行时是不是已经补全了。用 ref 是因为轮询回调要读它，又不能让它进依赖 ——
  // 进了依赖每次翻转都会重建定时器。
  const runtimeReadyRef = useRef<boolean | undefined>(undefined);

  /**
   * 重新问一次运行时状态；补全完成的那一刻自动把引擎拉起来。
   *
   * 以前这个只在挂载时问一次。于是「下载 → 解压 → 装好」之后，
   * `provision.runtime_ready` 还停在 false，「开启变声」照样被
   * `toggleRun` 开头那道闸拦下来说「运行时未就绪」—— 用户唯一的出路是重启
   * 软件，因为重启才会重新问一次。装完就该能用，不该要重启。
   */
  const refreshProvision = useCallback(async () => {
    try {
      const p = await getProvisionStatus();
      setProvision(p);
      const wasReady = runtimeReadyRef.current;
      runtimeReadyRef.current = p.runtime_ready;
      // false → true 的那一下：worker 还从来没起来过，现在可以起了。
      if (wasReady === false && p.runtime_ready !== false) {
        setLastError("");
        const st = await ensureEngine();
        setStatus(st);
      }
      return p;
    } catch {
      return undefined;
    }
  }, []);

  const refresh = useCallback(async () => {
    // 运行时还没就绪时，顺带盯着它 —— 补全是在另一个组件里跑的，装完那一刻
    // 没有事件通知这里。就绪之后就不再问了，免得每秒一次白跑文件检查。
    if (runtimeReadyRef.current === false) {
      void refreshProvision();
    }
    try {
      const raw = await getEngineStatus();
      const state = String(raw.state || "idle");
      // 假启动：后端已把 starting 摊成 idle，前端 startingRef 也要松掉，
      // 否则底栏主按钮仍显示「启动中」且点不动。
      if (state !== "starting" && startingRef.current) {
        startingRef.current = false;
      }
      const st: EngineStatus =
        state === "starting" &&
        raw.worker_alive === false &&
        !startingRef.current
          ? { ...raw, state: "idle" } // 没有活 worker 的 starting 是陈旧 status
          : raw;
      stateRef.current = String(st.state || "idle");
      progressRef.current = loadProgress(st);
      if (
        String(st.message_code || "") === "vc.swapping" ||
        String(st.message_code || "") === "vc.swap_failed" ||
        String(st.message_code || "") === "vc.running" ||
        (st.state !== "running" && st.state !== "starting")
      ) {
        setSwapHint(false);
      }
      setStatus(st);
      if (st.state === "error" && st.error) {
        setLastError(String(st.error));
      } else if (st.state === "running") {
        setLastError("");
      }
      // idle 不要清 lastError：start 失败后 worker 可能马上被一条 set
      // 写回 idle，这里一清底栏就变回「引擎就绪」，像没点过。
    } catch (e) {
      setLastError(String(e));
    }
  }, [refreshProvision]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getProvisionStatus();
        if (!cancelled) setProvision(p);
        // 记下开局状态。refresh 的轮询靠它决定要不要继续盯着运行时。
        runtimeReadyRef.current = p.runtime_ready;
        // Only ensure worker when Runtime is complete
        if (p.runtime_ready !== false) {
          const st = await ensureEngine();
          if (!cancelled) setStatus(st);
        } else {
          const st = await getEngineStatus();
          if (!cancelled) {
            setStatus(st);
            setLastError(String(p.message || t("s.14b8f39742")));
          }
        }
      } catch (e) {
        if (!cancelled) setLastError(String(e));
      }
    })();
    // Adaptive poll. A fixed 400ms meant ~9000 status.json reads an hour even
    // with the window hidden in the tray and nothing running. The Tk shell used
    // 1s normally and only sped up to ~300ms while converting, because the mic
    // meter is the sole thing that needs to be live.
    let id = 0;
    let currentMs = 0;
    const pick = () =>
      document.visibilityState === "hidden"
        ? 2000
        : stateRef.current === "starting" || progressRef.current != null
          ? 250
          : stateRef.current === "running"
            ? 400
            : 1000;
    const arm = () => {
      const ms = pick();
      if (ms === currentMs && id) return;
      currentMs = ms;
      if (id) window.clearInterval(id);
      id = window.setInterval(() => {
        void refresh();
        arm(); // re-evaluate after each tick
      }, ms);
    };
    arm();
    document.addEventListener("visibilitychange", arm);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", arm);
      if (id) window.clearInterval(id);
      if (hotTimer.current) window.clearTimeout(hotTimer.current);
    };
  }, [refresh]);

  const running = status.state === "running";

  // 「已自动降低精度」那句话，用完即弃。
  const [notice, setNotice] = useState("");
  // 「要放宽延迟吗」那个询问。null = 没在问。
  const [tearAsk, setTearAsk] = useState<
    null | { message: string; blockTime: number }
  >(null);

  // 撕裂判定：把心跳里的累计欠载数喂给壳，壳按增速判断。
  //
  // 判定状态（窗口、冷却）全在 Rust 那边，这里只负责传数和显示结果 ——
  // 放前端的话换页、重渲染都会把状态弄丢。
  const tearAsked = useRef(false);
  useEffect(() => {
    if (!running) {
      tearAsked.current = false;
      try {
        void invoke("tearing_reset").catch(() => undefined);
      } catch {
        /* not in Tauri */
      }
      return;
    }
    const n = Number(status.underrun || 0);
    try {
      void invoke<{ action?: string; message?: string; block_time?: number }>(
        "tearing_step",
        { underrun: n },
      )
        .then((r) => {
          if (!r || r.action === "none") return;
          if (r.action === "lowered") {
            // 已经做完了，只是告诉他一声。不打断，声音没断过。
            setNotice(String(r.message || ""));
            return;
          }
          if (r.action === "ask_block") {
            // 这一步要停流重开，问过再动。一次会话只问一次 —— 他说了不要，
            // 就别每隔十几秒再弹一遍。
            if (tearAsked.current) return;
            tearAsked.current = true;
            setTearAsk({
              message: String(r.message || ""),
              blockTime: Number(r.block_time || 0),
            });
          }
        })
        .catch(() => undefined);
    } catch {
      /* not in Tauri */
    }
  }, [running, status.underrun]);
  const bootCode =
    String(status.message_code || "") === "engine.starting" ||
    String(status.message_code || "") === "engine.importing";
  // 导入推理库不是「变声启动中」：底栏按钮仍应是「开启变声」。
  const starting =
    startingRef.current ||
    (status.state === "starting" && !bootCode) ||
    busy;

  const toggleRun = useCallback(async (opts?: { dspId?: string }) => {
    if (provision.need_provision || provision.runtime_ready === false) {
      setLastError(
        String(provision.message || t("s.6aa0d5bedd")),
      );
      return;
    }
    // 开机导入推理库时 status 也会是 starting。那一下点按钮必须是「开启」，
    // 不能被当成「停止」把还没发出去的 start 吃掉。
    const stopping = running || startingRef.current;
    let dspOnly = Boolean(opts?.dspId?.trim());
    let dspId = String(opts?.dspId || "").trim();
    if (!stopping) {
      try {
        const cfg = await getConfig();
        if (!dspOnly) {
          // `dsp_active` 是后端 `config::wants_dsp` 的结论，前端不再自己推。
          //
          // 这里以前是「dsp_enabled 或 dsp_preset 非空」—— 比后端那套松：
          // 配置里剩一个旧预设名就算纯 DSP，于是下面 `activateDsp` 会在开启
          // 前把 pth_path 清掉、让引擎丢掉模型。用户明明选好了音色，一点
          // 「开启变声」就被抹掉，只能反复切模型碰运气。
          dspOnly = Boolean(cfg.dsp_active);
          dspId = dspOnly ? String(cfg.dsp_preset || "").trim() : "";
        }
        if (!dspOnly) {
          const pth = String(cfg.pth_path || cfg.last_model_path || "").trim();
          const last = String(cfg.last_model || "").trim();
          if (!pth && !last) {
            setLastError(t("msg.vc.need_model"));
            return;
          }
        }
      } catch {
        /* 预览模式：没有配置就让后面的 start 自己报 */
      }
    }
    if (!stopping && !dspOnly) {
      try {
        const { ensureEngineCoreOrPrompt } = await import("../lib/downloadModels");
        const ok = await ensureEngineCoreOrPrompt(t("s.vcNeedEngineCore"));
        if (!ok) {
          setLastError(t("s.vcNeedEngineCoreShort"));
          return;
        }
      } catch {
        /* 预览模式忽略 */
      }
    }
    setBusy(true);
    setLastError("");
    try {
      if (stopping) {
        startingRef.current = false;
        // 软停：只停音频流，worker 进程留下。force 会杀掉整棵 Python，
        // 下次开启还要再冷启动 torch/CUDA。
        const st = await stopVc(false);
        setStatus(st);
      } else {
        startingRef.current = true;
        setUserStarts((n) => n + 1);
        if (dspOnly && dspId) {
          // 每次纯 DSP 开启都重新落盘一次：inuse 若漏了 dsp_enabled，
          // worker 会当成没选音色，报 Please choose the .pth file。
          const { activateDsp } = await import("../lib/engine");
          await activateDsp(dspId);
        }
        // 不再在 start 前推 function=vc：那条 set 会跟 start 抢槽，失败时
        // 还会把 error 盖成「参数已应用」。音高由 start 读 inuse、成功后再热补。
        const st = await startVc();
        setStatus(st);
        if (st.state === "error" && st.error) {
          setLastError(String(st.error));
        } else if (st.state !== "running") {
          setLastError(String(st.error || st.message || t("msg.vc.need_model")));
        } else {
          setLastError("");
        }
      }
    } catch (e) {
      setLastError(String(e));
      await refresh();
    } finally {
      startingRef.current = false;
      setBusy(false);
    }
  }, [running, refresh, provision, status.state]);

  /**
   * Ask the worker to re-enumerate audio devices.
   *
   * 「重载设备列表」 was wired to `refresh()`, which only re-reads status.json —
   * it never asked the worker for anything. The lists therefore stayed empty
   * until the worker happened to enumerate on its own (part of the 20–40 s
   * cold start), and clicking the button only appeared to work because by then
   * enough time had passed.
   */
  const [devicesBusy, setDevicesBusy] = useState(false);
  const reloadDevices = useCallback(async () => {
    setDevicesBusy(true);
    try {
      const st = await listDevices();
      setStatus(st);
      if (st.state === "error" && st.error) setLastError(String(st.error));
    } catch (e) {
      setLastError(String(e));
    } finally {
      setDevicesBusy(false);
    }
  }, []);

  const scheduleHot = useCallback((patch: Parameters<typeof setHot>[0]) => {
    if (hotTimer.current) window.clearTimeout(hotTimer.current);
    hotTimer.current = window.setTimeout(() => {
      void setHot(patch).catch(() => {
        /* ignore when idle without worker */
      });
    }, 80);
  }, []);

  const onPitch = useCallback(
    (v: number) => {
      pitchRef.current = v;
      scheduleHot({ pitch: v });
    },
    [scheduleHot],
  );

  const onFormant = useCallback(
    (v: number) => {
      formantRef.current = v;
      scheduleHot({ formant: v });
    },
    [scheduleHot],
  );

  const onMode = useCallback(
    (m: OutputMode) => {
      modeRef.current = m;
      scheduleHot({ function: m });
    },
    [scheduleHot],
  );

  /**
   * Adopt values that changed outside the sliders — the saved config on start,
   * and the selected voice's profile on every switch. Does not push anything to
   * the worker: the caller already did, or `voices_select` wrote them.
   */
  const syncParams = useCallback(
    (p: { pitch?: number; formant?: number; mode?: OutputMode }) => {
      if (p.pitch != null && Number.isFinite(p.pitch)) pitchRef.current = p.pitch;
      if (p.formant != null && Number.isFinite(p.formant)) {
        formantRef.current = p.formant;
      }
      if (p.mode) modeRef.current = p.mode;
    },
    [],
  );

  const noteSwap = useCallback(() => {
    setSwapHint(true);
  }, []);

  const hinted: EngineStatus =
    swapHint && !isLoadPhase(status)
      ? {
          ...status,
          message_code: "vc.swapping",
          message: status.message || t("msg.vc.swapping"),
          progress:
            loadProgress(status) != null ? status.progress : 15,
        }
      : status;

  const sub =
    lastError ||
    (provision.need_provision
      ? String(provision.message || t("s.d725011356"))
      : statusSub(hinted));

  return {
    status,
    provision,
    running,
    starting: starting || swapHint,
    /** 用户亲手按下「开启变声」的次数。预热和自动重启不计。 */
    userStarts,
    busy,
    progress: loadProgress(hinted),
    noteSwap,
    lastError,
    toggleRun,
    onPitch,
    onFormant,
    onMode,
    syncParams,
    refresh,
    refreshProvision,
    notice,
    dismissNotice: () => setNotice(""),
    tearAsk,
    // 用户点了「保持现状」：关掉就好，这一轮会话不会再问第二次。
    dismissTearAsk: () => setTearAsk(null),
    // 用户点了「放宽延迟」。block_time 是冷参数，改完要停流重开。
    applyTearAsk: async () => {
      const bt = tearAsk?.blockTime || 0;
      setTearAsk(null);
      if (bt <= 0) return;
      try {
        await invoke("config_set", { patch: { block_time: bt } });
      } catch {
        /* 改不动就维持现状，别把用户卡在一个弹不掉的框里 */
      }
    },
    reloadDevices,
    devicesBusy,
    title: statusTitle(hinted),
    sub,
    // Worker writes `input_db` (dBFS) and carries the gate as `threhold`
    // (upstream spelling). Map both with the Tk shell's formula so the meter
    // reads identically: frac = (clamp(db, -60, 0) + 60) / 60.
    micDb: status.input_db === undefined || status.input_db === null
      ? null
      : Number(status.input_db),
    thresholdDb: Number(status.threhold ?? -60),
  };
}
