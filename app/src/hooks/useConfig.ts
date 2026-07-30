import { useCallback, useEffect, useRef, useState } from "react";
import { getConfig, setConfig, type Config } from "../lib/config";

/**
 * Settings state. Writes are optimistic so sliders feel live, then reconciled
 * with whatever the backend actually persisted.
 *
 * Cold keys come back in `needs_restart`; the page shows a standing notice
 * instead of silently doing nothing, which is what the old placeholder UI did.
 */
export function useConfig() {
  const [cfg, setCfg] = useState<Config>({});
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [restartKeys, setRestartKeys] = useState<string[]>([]);
  const pending = useRef<Config>({});
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    getConfig()
      .then((c) => {
        if (alive) {
          setCfg(c);
          setLoaded(true);
        }
      })
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const flush = useCallback(async () => {
    const patch = pending.current;
    pending.current = {};
    if (!Object.keys(patch).length) return;
    try {
      const out = await setConfig(patch);
      setCfg(out.config);
      if (out.needs_restart.length) {
        setRestartKeys((prev) =>
          Array.from(new Set([...prev, ...out.needs_restart])),
        );
      }
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  /** Coalesce rapid changes (slider drags) into one write. */
  const set = useCallback(
    (key: string, value: unknown, immediate = false) => {
      setCfg((c) => ({ ...c, [key]: value }));
      pending.current[key] = value;
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void flush(), immediate ? 0 : 220);
    },
    [flush],
  );

  const clearRestartNotice = useCallback(() => setRestartKeys([]), []);

  const num = useCallback(
    (k: string, fallback = 0) => {
      const v = cfg[k];
      return typeof v === "number" ? v : Number(v ?? fallback) || fallback;
    },
    [cfg],
  );
  const str = useCallback(
    (k: string, fallback = "") => {
      const v = cfg[k];
      return typeof v === "string" ? v : fallback;
    },
    [cfg],
  );
  const bool = useCallback((k: string) => cfg[k] === true, [cfg]);

  return { cfg, loaded, error, set, num, str, bool, restartKeys, clearRestartNotice };
}
