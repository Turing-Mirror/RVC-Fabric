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

  const refresh = useCallback(async () => {
    try {
      const st = await getEngineStatus();
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
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getProvisionStatus();
        if (!cancelled) setProvision(p);
        // Only ensure worker when Runtime is complete
        if (p.runtime_ready !== false) {
          const st = await ensureEngine();
          if (!cancelled) setStatus(st);
        } else {
          const st = await getEngineStatus();
          if (!cancelled) {
            setStatus(st);
            setLastError(String(p.message || "运行时未就绪"));
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
        String(provision.message || "运行时未就绪，请先补全运行时"),
      );
      return;
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
      ? String(provision.message || "需补全运行时")
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
