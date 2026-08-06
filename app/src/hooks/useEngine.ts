import { useCallback, useEffect, useRef, useState } from "react";
import {
  ensureEngine,
  getEngineStatus,
  getProvisionStatus,
  listDevices,
  setHot,
  startVc,
  statusSub,
  statusTitle,
  stopVc,
  type EngineStatus,
  type ProvisionStatus,
} from "../lib/engine";
import type { OutputMode } from "../components/Dock";
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
      setStatus(st);
      if (st.state === "error" && st.error) {
        setLastError(String(st.error));
      } else if (st.state === "running" || st.state === "idle") {
        // Clear sticky errors once engine is healthy again
        setLastError((prev) => (prev && st.state === "running" ? "" : prev));
        if (st.state === "idle" && st.worker_alive) {
          setLastError("");
        }
      }
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
  const starting =
    startingRef.current || status.state === "starting" || busy;

  const toggleRun = useCallback(async () => {
    if (provision.need_provision || provision.runtime_ready === false) {
      setLastError(
        String(provision.message || t("s.6aa0d5bedd")),
      );
      return;
    }
    // 实时推理链路（rtrvc）加载 hubert_base.pt + rmvpe.pt；缺了会在引擎里炸。
    // 停变声不需要查；只有要「开启」时才引导补全。
    const stopping =
      running || status.state === "starting" || startingRef.current;
    if (!stopping) {
      try {
        const { ensureEngineCoreOrPrompt } = await import("../lib/downloadModels");
        const ok = await ensureEngineCoreOrPrompt(
          "实时变声需要引擎资源（hubert / rmvpe / ffmpeg，约 720 MB）。请先下载补全，完成后再点「开启变声」。",
        );
        if (!ok) {
          setLastError("请先补全引擎资源，再开启变声");
          return;
        }
      } catch {
        /* 预览模式忽略 */
      }
    }
    setBusy(true);
    setLastError("");
    try {
      if (running || status.state === "starting" || startingRef.current) {
        startingRef.current = false;
        const st = await stopVc(true);
        setStatus(st);
      } else {
        startingRef.current = true;
        try {
          await setHot({
            pitch: pitchRef.current,
            formant: formantRef.current,
            function: modeRef.current,
          });
        } catch {
          /* worker may still be coming up */
        }
        const st = await startVc();
        setStatus(st);
        if (st.state === "error" && st.error) {
          setLastError(String(st.error));
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

  const sub =
    lastError ||
    (provision.need_provision
      ? String(provision.message || t("s.d725011356"))
      : statusSub(status));

  return {
    status,
    provision,
    running,
    starting,
    busy,
    lastError,
    toggleRun,
    onPitch,
    onFormant,
    onMode,
    syncParams,
    refresh,
    refreshProvision,
    reloadDevices,
    devicesBusy,
    title: statusTitle(status),
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
