import { useCallback, useEffect, useRef, useState } from "react";
import {
  ensureEngine,
  getEngineStatus,
  setHot,
  startVc,
  statusSub,
  statusTitle,
  stopVc,
  type EngineStatus,
} from "../lib/engine";
import type { OutputMode } from "../components/Dock";

export function useEngine() {
  const [status, setStatus] = useState<EngineStatus>({});
  const [busy, setBusy] = useState(false);
  const [lastError, setLastError] = useState("");
  const pitchRef = useRef(15);
  const formantRef = useRef(1.2);
  const modeRef = useRef<OutputMode>("vc");
  const hotTimer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const st = await getEngineStatus();
      setStatus(st);
      if (st.error) setLastError(String(st.error));
    } catch (e) {
      setLastError(String(e));
    }
  }, []);

  // Poll status + ensure worker once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const st = await ensureEngine();
        if (!cancelled) setStatus(st);
      } catch (e) {
        if (!cancelled) setLastError(String(e));
      }
    })();
    const id = window.setInterval(() => {
      void refresh();
    }, 400);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      if (hotTimer.current) window.clearTimeout(hotTimer.current);
    };
  }, [refresh]);

  const running = status.state === "running";
  const starting = status.state === "starting" || busy;

  const toggleRun = useCallback(async () => {
    setBusy(true);
    setLastError("");
    try {
      if (running || starting) {
        const st = await stopVc(true);
        setStatus(st);
      } else {
        // Push current hot params before start (worker may already be idle)
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
        }
      }
    } catch (e) {
      setLastError(String(e));
      await refresh();
    } finally {
      setBusy(false);
    }
  }, [running, starting, refresh]);

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

  return {
    status,
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
    sub: lastError || statusSub(status),
    meterLevel: Number(status.meter_level ?? 0),
    threshold: Number(status.threshold_meter ?? 0.25),
  };
}
