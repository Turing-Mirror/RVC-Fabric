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
  const [lastError, setLastError] = useState("");
  const pitchRef = useRef(15);
  const formantRef = useRef(1.2);
  const modeRef = useRef<OutputMode>("vc");
  const hotTimer = useRef<number | null>(null);
  const startingRef = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const st = await getEngineStatus();
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
    meterLevel: Number(status.meter_level ?? 0),
    threshold: Number(status.threshold_meter ?? 0.25),
  };
}
