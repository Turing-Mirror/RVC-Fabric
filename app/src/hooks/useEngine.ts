import { useCallback, useEffect, useRef, useState } from "react";
import {
  ensureEngine,
  getEngineStatus,
  getProvisionStatus,
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
  const pitchRef = useRef(15);
  const formantRef = useRef(1.2);
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
            setLastError(String(p.message || "Runtime 未就绪"));
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
        String(provision.message || "Runtime 未就绪，请先补全运行时"),
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

  const sub =
    lastError ||
    (provision.need_provision
      ? String(provision.message || "需补全 Runtime")
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
    refresh,
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
